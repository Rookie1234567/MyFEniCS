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
    stage4_local_h_root_forest_catalog,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    _cell_physical_entity_keys,
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


def _h100_context(
    *,
    trace_degree: int = 5,
    cell_interior_degree_overrides=None,
    selected_p6_face_geometry_keys=(),
):
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
        cell_interior_degree_overrides=(
            cell_interior_degree_overrides
        ),
        selected_p6_face_geometry_keys=(
            selected_p6_face_geometry_keys
        ),
    )
    override_label = (
        "uniform"
        if cell_interior_degree_overrides is None
        else "variable-interior"
    )
    trace_label = (
        "uniform-trace"
        if not selected_p6_face_geometry_keys
        else "selective-p6-face"
    )
    path = _shared_plan_path(
        payload,
        name=(
            f"h100-p{trace_degree}-{override_label}-"
            f"{trace_label}-mpi{MPI.COMM_WORLD.size}"
        ),
    )
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        path,
        comm=MPI.COMM_WORLD,
    )
    context = mesh_data.local_h_context
    assert isinstance(context, Stage4LocalHContext)
    return cfg, path, mesh_data, context


def _h100_plan_payload(*, comm_size: int) -> dict[str, object]:
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    return stage4_local_h_refinement_plan_payload(
        cfg,
        ((0.0, 0.0, 120.0, 16.5, 12.5, 130.0),),
        comm_size=comm_size,
        trace_degree=5,
        cell_interior_degree=6,
        provenance={
            "purpose": "generic deterministic component fixture",
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        },
    )


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


def test_component_plan_payload_is_deterministic_without_case_record() -> None:
    frozen = _h100_plan_payload(comm_size=8)
    rebuilt = _h100_plan_payload(comm_size=8)

    assert "cell_interior_degrees" not in frozen
    assert rebuilt == frozen
    assert frozen["base_config"]["identity_sha256"] == (
        "1429f346ba84a7b5439b68e591da665d49557354c184a29d4a82aadaf8292999"
    )
    assert frozen["expected_forest"] == {
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 3,
            "user": 1,
        },
        "hanging_face_catalog_sha256": (
            "4a4feaced4b9174f2d7f162f32ed2d10b"
            "ee33c85799848b39e21b25f9a74a1f3"
        ),
        "hanging_patch_count": 8,
        "leaf_catalog_sha256": (
            "92866e325b1744dbdbf0b3379d21079d"
            "83fda4f4ce51340f31678a2eda09bafb"
        ),
        "leaf_cell_count": 52,
        "root_catalog_sha256": (
            "0cfc18e59084d149e86bcc6431faf05fe"
            "52d29e0e3b7fff69a88633f3c818555"
        ),
        "root_cell_count": 24,
    }


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


def test_h100_true_variable_cell_interiors_remove_p6_rows() -> None:
    p5_box = (0.0, 0.0, 120.0, 8.25, 6.25, 125.0)
    _cfg, _path, _mesh_data, uniform_context = _h100_context()
    _cfg, path, _mesh_data, mixed_context = _h100_context(
        cell_interior_degree_overrides={p5_box: 5},
    )
    uniform = build_stage4_local_h_reduction_authority(
        uniform_context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    mixed = build_stage4_local_h_reduction_authority(
        mixed_context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["cell_interior_degrees"]) == 52
    assert mixed_context.audit["variable_cell_interior_degree"] is True
    assert mixed.degree_plan.audit["cell_degree_counts"] == {
        "p4": 0,
        "p5": 1,
        "p6": 51,
    }
    assert mixed.degree_plan.cell_degree_by_box[p5_box] == 5
    assert len(
        mixed.degree_plan.audit[
            "geometry_canonical_entity_degree_sha256"
        ]
    ) == 64
    assert (
        mixed.degree_plan.audit[
            "runtime_global_entity_id_order_partition_independent"
        ]
        is False
    )
    assert (
        mixed.degree_plan.entity_map.active_trace_rows
        == uniform.degree_plan.entity_map.active_trace_rows
    )
    assert (
        uniform.degree_plan.entity_map.active_rows
        - mixed.degree_plan.entity_map.active_rows
        == 210
    )
    assert (
        uniform.audit["actual_full3d_equivalent_active_fe_dofs"]
        - mixed.audit["actual_full3d_equivalent_active_fe_dofs"]
        == 210
    )
    assert (
        mixed.degree_plan.audit["inactive_p6_rows"]
        == uniform.degree_plan.audit["inactive_p6_rows"] + 210
    )
    assert (
        mixed.degree_plan.audit[
            "cell_interior_p6_modes_globally_numbered_when_inactive"
        ]
        is False
    )
    assert (
        mixed.audit["hanging_slave_rows"]
        == uniform.audit["hanging_slave_rows"]
    )
    assert (
        mixed.audit["periodic_slave_rows"]
        == uniform.audit["periodic_slave_rows"]
    )
    assert mixed.audit["active_fe_dof_gate_pass"] is True


def test_h100_selective_nonhanging_p6_face_enters_stage4_authority() -> None:
    _cfg, _path, _mesh_data, base_context = _h100_context()
    base = build_stage4_local_h_reduction_authority(
        base_context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    physical = base.trace_constraints.authority
    constrained_face_keys = {
        row.entity_geometry_key
        for relation in (
            *physical.hanging_relations,
            *physical.periodic_relations,
        )
        for row in (*relation.slave_rows, *relation.master_rows)
        if row.entity_dimension == 2
    }
    selected = next(
        entity.geometry_key
        for entity in physical.entities
        if entity.dimension == 2
        and entity.geometry_key not in constrained_face_keys
    )
    _cfg, path, _mesh_data, selected_context = _h100_context(
        selected_p6_face_geometry_keys=(selected,),
    )
    enriched = build_stage4_local_h_reduction_authority(
        selected_context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["selected_p6_face_geometry_keys"] == [
        list(selected)
    ]
    assert selected_context.audit["selected_p6_face_count"] == 1
    assert enriched.degree_plan.audit["trace_degree_values"] == [5, 6]
    assert enriched.degree_plan.audit["selected_p6_face_count"] == 1
    assert (
        enriched.degree_plan.audit["local_variable_trace_implemented"]
        is True
    )
    assert enriched.trace_constraints.audit[
        "local_variable_trace_implemented"
    ] is True
    assert (
        enriched.degree_plan.entity_map.active_rows
        - base.degree_plan.entity_map.active_rows
        == 20
    )
    assert (
        enriched.trace_constraints.independent_trace_rows
        - base.trace_constraints.independent_trace_rows
        == 20
    )
    assert (
        enriched.audit["actual_full3d_equivalent_active_fe_dofs"]
        - base.audit["actual_full3d_equivalent_active_fe_dofs"]
        == 20
    )
    assert enriched.audit["active_fe_dof_gate_pass"] is True


def test_selective_trace_only_plan_preserves_the_root_mesh() -> None:
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    forest = stage4_local_h_root_forest_catalog(
        cfg,
        comm_size=MPI.COMM_WORLD.size,
    )
    bounds = forest.domain_bounds
    origin = np.asarray(bounds[:3], dtype=np.float64)
    extent = np.asarray(
        [
            bounds[axis + 3] - bounds[axis]
            for axis in range(3)
        ],
        dtype=np.float64,
    )
    tolerance = max(float(np.max(extent)), 1.0) * 1.0e-11
    face_incidence: dict[tuple[int, ...], int] = {}
    for box in forest.root_boxes:
        for key in _cell_physical_entity_keys(
            box,
            origin=origin,
            tolerance=tolerance,
        )[2]:
            face_incidence[key] = face_incidence.get(key, 0) + 1
    selected = next(
        key for key, count in sorted(face_incidence.items())
        if count == 2
    )
    payload = stage4_local_h_refinement_plan_payload(
        cfg,
        (),
        comm_size=MPI.COMM_WORLD.size,
        trace_degree=5,
        cell_interior_degree=6,
        provenance={
            "purpose": "zero-h selective-trace component fixture",
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        },
        selected_p6_face_geometry_keys=(selected,),
    )
    assert payload["zero_h_selective_trace_only"] is True
    assert payload["marked_root_boxes"] == []
    path = _shared_plan_path(
        payload,
        name=f"h100-zero-h-selective-trace-mpi{MPI.COMM_WORLD.size}",
    )
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        path,
        comm=MPI.COMM_WORLD,
    )
    context = mesh_data.local_h_context
    assert isinstance(context, Stage4LocalHContext)
    authority = build_stage4_local_h_reduction_authority(
        context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    assert len(context.forest.leaves) == len(context.forest.root_boxes)
    assert context.audit["maximum_level"] == 0
    assert context.audit["hanging_patch_count"] == 0
    assert context.audit["zero_h_selective_trace_only"] is True
    assert context.audit["full3d_equivalent_dof_gate_limit"] is None
    assert authority.degree_plan.audit["selected_p6_face_count"] == 1
    assert authority.degree_plan.audit["trace_degree_values"] == [5, 6]
    assert authority.audit["active_fe_dof_hard_gate_active"] is False
    assert authority.audit["active_fe_dof_gate_limit"] is None
    assert authority.audit["active_fe_dof_gate_pass"] is True


def test_empty_local_h_plan_without_selective_trace_remains_rejected() -> None:
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    with pytest.raises(
        ValueError,
        match="selective-trace-only plan is active",
    ):
        stage4_local_h_refinement_plan_payload(
            cfg,
            (),
            comm_size=MPI.COMM_WORLD.size,
            trace_degree=5,
            cell_interior_degree=6,
            provenance={
                "purpose": "ordinary-empty-plan negative fixture",
                "accuracy_credit": False,
                "ordinary_default_changed": False,
            },
        )


def test_local_h_variable_interior_plan_fails_closed() -> None:
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    marked = ((0.0, 0.0, 120.0, 16.5, 12.5, 130.0),)
    provenance = {
        "purpose": "negative component fixture",
        "accuracy_credit": False,
    }
    with pytest.raises(ValueError, match="not one forest leaf"):
        stage4_local_h_refinement_plan_payload(
            cfg,
            marked,
            comm_size=MPI.COMM_WORLD.size,
            trace_degree=5,
            cell_interior_degree=6,
            provenance=provenance,
            cell_interior_degree_overrides={
                (99.0, 99.0, 99.0, 100.0, 100.0, 100.0): 5
            },
        )
    with pytest.raises(ValueError, match="trace_degree <= degree"):
        stage4_local_h_refinement_plan_payload(
            cfg,
            marked,
            comm_size=MPI.COMM_WORLD.size,
            trace_degree=5,
            cell_interior_degree=6,
            provenance=provenance,
            cell_interior_degree_overrides={
                (0.0, 0.0, 120.0, 8.25, 6.25, 125.0): 4
            },
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 partition-specific owner-routing regression",
)
def test_mpi2_accepts_rank_local_hanging_patches() -> None:
    cfg, _plan, _mesh_data, context = _h100_context()
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
        < authority.audit["raw_broken_active_fe_dofs"]
    )
    assert authority.audit["active_fe_dof_gate_pass"] is True


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
