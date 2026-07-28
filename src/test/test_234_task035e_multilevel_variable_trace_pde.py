from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile

from mpi4py import MPI
import numpy as np
import pytest

from src.adaptivity.stage4_local_h import (
    Stage4LocalHContext,
    build_stage4_local_h_mesh_data,
    stage4_multilevel_local_h_refinement_plan_payload,
)
from src.adaptivity.task035e_multigoal_snapshot import (
    write_task035e_multigoal_snapshot,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


_STAGE_ONE = (
    (0.0, 0.0, 120.0, 16.5, 12.5, 130.0),
    (33.5, 12.5, 60.0, 50.0, 25.0, 120.0),
)
_STAGE_TWO = (
    (0.0, 0.0, 120.0, 8.25, 6.25, 125.0),
    (41.75, 18.75, 90.0, 50.0, 25.0, 120.0),
)
_DIAGNOSTIC_SOURCE_SHA = "f" * 40


def _shared_json(
    payload: dict[str, object],
    *,
    name: str,
) -> Path:
    comm = MPI.COMM_WORLD
    root = (
        tempfile.mkdtemp(prefix=f"task035e-{name}-")
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


def _plan_payload(
    *,
    degree_overrides=None,
    variable_trace: bool = False,
) -> dict[str, object]:
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    provenance_core: dict[str, object] = {
        "schema_version": "task035e.blind-initial-provenance.v1",
        "status": "blind_initial_provenance_closed",
        "source_sha": _DIAGNOSTIC_SOURCE_SHA,
        "purpose": (
            "Task035e opt-in compiled multilevel variable-trace "
            "component fixture"
        ),
        "accuracy_credit": False,
        "formal_candidate": False,
        "ordinary_default_changed": False,
    }
    provenance = {
        **provenance_core,
        "provenance_sha256": hashlib.sha256(
            json.dumps(
                provenance_core,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("ascii")
        ).hexdigest(),
    }
    return stage4_multilevel_local_h_refinement_plan_payload(
        cfg,
        (_STAGE_ONE, _STAGE_TWO),
        comm_size=MPI.COMM_WORLD.size,
        trace_degree=4,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=degree_overrides,
        variable_trace_from_cell_degrees=variable_trace,
    )


@pytest.mark.skipif(
    os.environ.get(
        "MYFENICS_RUN_TASK035E_MULTILEVEL_VARIABLE_TRACE_PDE_FIXTURE"
    )
    != "1",
    reason=(
        "explicit opt-in Task035e multilevel local-h plus variable-trace "
        "Stage4 PDE fixture"
    ),
)
def test_multilevel_p456_variable_trace_closes_compiled_stage4_path() -> None:
    """Qualify the component path without granting candidate accuracy credit."""

    comm = MPI.COMM_WORLD
    if comm.size not in {1, 8}:
        pytest.skip("Task035e PDE fixture qualifies serial and MPI8 only")

    base = replace(
        target_stage4_config(degree=6, h_nm=100.0),
        case_name=(
            "task035e_multilevel_p456_variable_trace_"
            f"h100_mpi{comm.size}"
        ),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        direct_release_base_after_augmentation=True,
        direct_release_solver_before_postprocess=True,
        full3d_reference_export=False,
        unique_output=False,
    )

    seed_path = _shared_json(
        _plan_payload(),
        name=f"multilevel-variable-trace-seed-mpi{comm.size}",
    )
    seed_mesh = build_stage4_local_h_mesh_data(
        base,
        seed_path,
        comm=comm,
    )
    seed_context = seed_mesh.local_h_context
    assert isinstance(seed_context, Stage4LocalHContext)
    assert seed_context.audit["true_multilevel"] is True
    degree_by_box = {
        cell.box: 4 + int(cell.key.level)
        for cell in seed_context.forest.leaves
    }
    assert set(degree_by_box.values()) == {4, 5, 6}

    plan_path = _shared_json(
        _plan_payload(
            degree_overrides=degree_by_box,
            variable_trace=True,
        ),
        name=f"multilevel-p456-variable-trace-mpi{comm.size}",
    )
    mesh_data = build_stage4_local_h_mesh_data(
        base,
        plan_path,
        comm=comm,
    )
    context = mesh_data.local_h_context
    assert isinstance(context, Stage4LocalHContext)
    assert context.audit["true_multilevel"] is True
    assert context.audit["maximum_level"] == 2
    assert context.audit["variable_trace_from_cell_degrees"] is True

    cfg = replace(
        base,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        stage4_local_h_refinement_plan=str(plan_path),
    )
    plan_sha256 = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    captured: dict[str, object] = {}

    def live_observer(view) -> None:
        reduction = view.reduction
        build = reduction.build_audit
        degree = reduction.degree_plan.audit
        system = reduction.system.build_audit
        constraints = build["trace_constraints"]

        assert view.A.getSize()[0] > 0
        assert view.A.getSize()[0] == view.b.getSize()
        assert view.A.getSize()[1] == view.x.getSize()
        assert view.ksp.getConvergedReason() > 0
        assert view.recovered._destroyed is False
        assert set(degree["trace_degree_values"]) == {4, 5, 6}
        assert all(
            int(degree["cell_degree_counts"][f"p{value}"]) > 0
            for value in (4, 5, 6)
        )
        assert degree[
            "cell_driven_variable_trace_component_complete"
        ] is True
        assert degree[
            "inactive_high_order_trace_rows_globally_numbered"
        ] is False
        assert build["inactive_p6_rows_globally_numbered"] is False
        assert system["inactive_p6_rows_globally_numbered"] is False
        assert system["compiled_p6_tensor_builder"] is True
        assert system[
            "compiled_trace_constraint_binding_complete"
        ] is True
        assert system[
            "trace_constraint_cell_tensor_binding_complete"
        ] is True
        assert set(constraints["constraint_kinds"]) == {
            "floquet",
            "hanging",
        }
        preallocation = system["trace_preallocation"]
        assert preallocation["base_graph_preallocation"] == "exact"
        assert preallocation[
            "new_nonzero_allocation_error_enabled"
        ] is True
        assert (
            int(preallocation["active_rows"])
            == reduction.system.active_trace_rows
        )
        assert view.recovered.audit[
            "trace_constraint_recovery"
        ]["pass"] is True
        assert (
            view.recovered.active_full_solution.getSize()
            == reduction.system.entity_map.active_rows
        )
        assert (
            view.full_active_residual[
                "linear_system_relative_residual"
            ]
            <= 1.0e-9
        )
        assert view.port_operator_audit["pass"] is True
        snapshot = write_task035e_multigoal_snapshot(
            view,
            artifact_directory=(
                plan_path.parent / "task035e_current_snapshot"
            ),
            source_sha=_DIAGNOSTIC_SOURCE_SHA,
            trial_id="h100-component-fixture",
            cycle_index=0,
            expected_plan_sha256=plan_sha256,
            allow_serial_test_fixture=comm.size == 1,
        )
        captured["recovered"] = view.recovered
        captured["compiled"] = True
        captured["snapshot"] = snapshot

    summary = run_stage4b_block_grating_3d_case(
        cfg,
        plan_path.parent / "solve",
        variable_p_live_observer=live_observer,
        mesh_data_override=mesh_data,
    )

    assert summary["case_status"] == "completed"
    assert summary["stage4_local_h_active"] is True
    assert summary["stage4_variable_p_active"] is True
    assert summary["stage4_full3d_assembly_backend_actual"] == (
        ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    assert summary[
        "stage4_assembly_time_cell_static_condensation"
    ] is True
    assert summary["linear_system_relative_residual"] <= 1.0e-9
    assert summary["matrix_stats"]["matrix_mallocs"] == 0.0
    assert summary["variable_p_live_observer_requested"] is True
    assert summary["variable_p_live_observer_invoked"] is True
    assert captured["compiled"] is True
    snapshot = captured["snapshot"]
    assert snapshot.manifest_payload_sha256
    assert snapshot.manifest_path.is_file()

    audit = summary["cell_static_condensation"]
    degree = audit["degree_plan"]
    assert audit["local_h"]["mesh"]["true_multilevel"] is True
    assert audit["local_h"]["mesh"]["maximum_level"] == 2
    assert audit["full_p6_global_matrix_allocated"] is False
    assert audit["inactive_p6_rows_globally_numbered"] is False
    assert set(degree["trace_degree_values"]) == {4, 5, 6}
    assert all(
        int(degree["cell_degree_counts"][f"p{value}"]) > 0
        for value in (4, 5, 6)
    )
    assert set(
        audit["trace_constraints"]["constraint_kinds"]
    ) == {"floquet", "hanging"}
    assert audit["recovery"]["trace_constraint_recovery"]["pass"] is True
    assert audit["condensed_system"][
        "trace_preallocation"
    ]["base_graph_preallocation"] == "exact"
    assert (
        summary["matrix_stats"]["matrix_rows"]
        == summary["num_active_condensed_dofs"]
    )
    for name in (
        "R_total",
        "T_total",
        "A_volume_total",
        "A_balance",
        "energy_closure_error_port_volume",
    ):
        assert np.isfinite(float(summary[name]))

    recovered = captured["recovered"]
    assert recovered._destroyed is True
