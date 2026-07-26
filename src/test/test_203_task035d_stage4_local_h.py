from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.stage4_local_h import (
    Stage4LocalHContext,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
    stage4_local_h_refinement_plan_payload,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)
from src.solvers.dtn_port_3d import (
    _combine_owned_entries,
    _vec_nonzero_owned_entries,
)


def _shared_plan_path(
    payload: dict[str, object],
    *,
    name: str,
) -> Path:
    comm = MPI.COMM_WORLD
    root = (
        tempfile.mkdtemp(prefix=f"task035d-{name}-")
        if comm.rank == 0
        else None
    )
    root = comm.bcast(root, root=0)
    path = Path(root) / f"{name}.json"
    if comm.rank == 0:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    comm.Barrier()
    return path


def _h100_context(*, trace_degree: int = 5):
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    marked = ((0.0, 0.0, 120.0, 16.5, 12.5, 130.0),)
    payload = stage4_local_h_refinement_plan_payload(
        cfg,
        marked,
        comm_size=MPI.COMM_WORLD.size,
        trace_degree=trace_degree,
        cell_interior_degree=6,
        provenance={
            "purpose": "Task035d production adapter component fixture",
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        },
    )
    path = _shared_plan_path(
        payload,
        name=f"h100-p{trace_degree}-mpi{MPI.COMM_WORLD.size}",
    )
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        path,
        comm=MPI.COMM_WORLD,
    )
    context = mesh_data.local_h_context
    assert isinstance(context, Stage4LocalHContext)
    return cfg, path, mesh_data, context


def test_h100_plan_builds_real_periodic_local_h_carrier() -> None:
    _cfg, _path, mesh_data, context = _h100_context()
    comm = MPI.COMM_WORLD

    assert context.audit["pass"] is True
    assert context.audit["root_cell_count"] == 24
    assert context.audit["leaf_cell_count"] == 52
    assert context.audit["hanging_patch_count"] == 8
    assert context.forest.audit["closure_split_counts"] == {
        "user": 1,
        "periodic": 3,
        "material": 0,
        "balance": 0,
    }
    assert mesh_data.mesh_spacing_mode_resolved == "balanced_dyadic_local_h"
    assert context.carrier.audit["checks"][
        "all_artificial_exterior_is_hanging"
    ]
    assert (
        context.carrier.audit["physical_exterior_facet_count"]
        < context.carrier.audit["topological_exterior_facet_count"]
    )
    local_tags = tuple(
        map(int, np.unique(mesh_data.facet_tags.values))
    )
    tags = {
        value
        for packet in comm.allgather(local_tags)
        for value in packet
    }
    assert tags == {11, 12, 13, 14, 15, 16}


def test_h100_production_reduction_removes_hanging_and_floquet_rows() -> None:
    _cfg, _path, _mesh_data, context = _h100_context()
    authority = build_stage4_local_h_reduction_authority(
        context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )

    assert authority.audit["pass"] is True
    assert authority.audit["active_fe_dof_gate_pass"] is True
    assert authority.audit["hanging_slave_rows"] > 0
    assert authority.audit["periodic_slave_rows"] > 0
    assert (
        authority.audit["actual_full3d_equivalent_active_fe_dofs"]
        < authority.audit["raw_broken_active_fe_dofs"]
        <= 90_000
    )
    assert set(
        authority.trace_constraints.audit["constraint_kinds"]
    ) == {"floquet", "hanging"}
    assert (
        authority.trace_constraints.audit[
            "hanging_or_floquet_slave_rows_globally_numbered"
        ]
        is False
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 partition-specific owner-routing regression",
)
def test_h15_mpi2_accepts_rank_local_hanging_patches() -> None:
    cfg = target_stage4_config(degree=6, h_nm=15.0)
    plan = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "cases"
        / "097_goal_oriented_exact_sequence_hp_adaptivity"
        / "records"
        / "h15_top_air_local_h_plan_v1.json"
    )
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        plan,
        comm=MPI.COMM_WORLD,
    )
    context = mesh_data.local_h_context
    assert isinstance(context, Stage4LocalHContext)
    authority = build_stage4_local_h_reduction_authority(
        context,
        phase_x=cfg.floquet_phase_x,
        phase_y=cfg.floquet_phase_y,
    )
    trace = authority.audit["trace_constraints"]
    routing = trace["owner_routed_trace_cache_audit"]

    assert context.carrier.audit["cross_rank_hanging_patch_count"] == 0
    assert trace["cross_rank_hanging_relation_count"] == 0
    assert sum(routing["request_counts_by_rank"]) > 0
    assert sum(trace["remote_entity_lookup_counts_by_rank"]) > 0
    assert trace["pde_launch_ownership_gate"] is True
    assert (
        authority.audit["actual_full3d_equivalent_active_fe_dofs"]
        == 82_925
    )


def test_local_h_plan_rejects_live_geometry_drift() -> None:
    cfg, path, _mesh_data, _context = _h100_context()
    drifted = replace(cfg, mesh_target_size=15.0)

    with pytest.raises(ValueError, match="base geometry differs"):
        build_stage4_local_h_mesh_data(
            drifted,
            path,
            comm=MPI.COMM_WORLD,
        )


def test_dtn_significant_entry_cutoff_is_collective() -> None:
    comm = MPI.COMM_WORLD
    vector = PETSc.Vec().createMPI(4, comm=comm)
    reference = np.asarray(
        [1.0, 1.0e-14, 1.0e-12, 1.0e-14],
        dtype=np.complex128,
    )
    start, stop = map(int, vector.getOwnershipRange())
    vector.setValues(
        np.arange(start, stop, dtype=PETSc.IntType),
        reference[start:stop],
    )
    vector.assemble()
    try:
        rows, values = _vec_nonzero_owned_entries(vector)
        combined_rows, combined_values = _combine_owned_entries(
            (
                (rows, values),
                (
                    np.asarray([], dtype=PETSc.IntType),
                    np.asarray([], dtype=np.complex128),
                ),
            ),
            (1.0 + 0.0j, 0.0 + 0.0j),
            comm=comm,
        )
        gathered_rows = sorted(
            int(row)
            for packet in comm.allgather(tuple(map(int, rows)))
            for row in packet
        )
        gathered_combined = sorted(
            int(row)
            for packet in comm.allgather(
                tuple(map(int, combined_rows))
            )
            for row in packet
        )
        assert gathered_rows == [0, 2]
        assert gathered_combined == [0, 2]
        np.testing.assert_allclose(
            values,
            reference[np.asarray(rows, dtype=np.int64)],
        )
        np.testing.assert_allclose(
            combined_values,
            reference[np.asarray(combined_rows, dtype=np.int64)],
        )
    finally:
        vector.destroy()


@pytest.mark.skipif(
    os.environ.get("MYFENICS_RUN_TASK035D_LOCAL_H_PDE_FIXTURE") != "1",
    reason="explicit opt-in Task035d local-h Stage4 PDE fixture",
)
def test_h100_local_h_closes_full_stage4_path() -> None:
    cfg, path, _mesh_data, _context = _h100_context(trace_degree=4)
    solve_cfg = replace(
        cfg,
        case_name=f"task035d_local_h_h100_mpi{MPI.COMM_WORLD.size}",
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        stage4_local_h_refinement_plan=str(path),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        direct_release_base_after_augmentation=True,
        direct_release_solver_before_postprocess=True,
        full3d_reference_export=False,
        unique_output=False,
    )
    output = path.parent / "solve"
    summary = run_stage4b_block_grating_3d_case(solve_cfg, output)

    assert summary["case_status"] == "completed"
    assert summary["stage4_local_h_active"] is True
    assert summary["stage4_variable_p_active"] is True
    assert summary["linear_system_relative_residual"] <= 1.0e-9
    assert summary["num_actual_conforming_active_fe_dofs"] <= 90_000
    assert (
        summary["num_raw_broken_active_fe_dofs"]
        > summary["num_actual_conforming_active_fe_dofs"]
    )
    assert summary["matrix_stats"]["matrix_mallocs"] == 0.0
    audit = summary["cell_static_condensation"]
    assert set(audit["trace_constraints"]["constraint_kinds"]) == {
        "floquet",
        "hanging",
    }
    assert audit["full_p6_global_matrix_allocated"] is False
    assert audit["inactive_p6_rows_globally_numbered"] is False
    assert audit["recovery"]["trace_constraint_recovery"]["pass"] is True
    for name in (
        "R_total",
        "T_total",
        "A_volume_total",
        "A_balance",
        "energy_closure_error_port_volume",
    ):
        assert np.isfinite(float(summary[name]))
