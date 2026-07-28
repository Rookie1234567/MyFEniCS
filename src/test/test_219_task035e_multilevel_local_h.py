from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile

from mpi4py import MPI
import numpy as np
import pytest

from src.adaptivity.stage4_local_h import (
    Stage4LocalHContext,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
    stage4_multilevel_local_h_refinement_plan_payload,
)
from src.common.config_3d import target_stage4_config


_STAGE_ONE = (
    (0.0, 0.0, 120.0, 16.5, 12.5, 130.0),
    (33.5, 12.5, 60.0, 50.0, 25.0, 120.0),
)
_STAGE_TWO = (
    (0.0, 0.0, 120.0, 8.25, 6.25, 125.0),
    (41.75, 18.75, 90.0, 50.0, 25.0, 120.0),
)


def _shared_plan_path(
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


def _payload(
    *,
    stages=(_STAGE_ONE, _STAGE_TWO),
    trace_degree: int = 4,
    overrides=None,
    variable_trace_from_cell_degrees: bool = False,
) -> dict[str, object]:
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    return stage4_multilevel_local_h_refinement_plan_payload(
        cfg,
        stages,
        comm_size=MPI.COMM_WORLD.size,
        trace_degree=trace_degree,
        cell_interior_degree=6,
        provenance={
            "purpose": "Task035e multilevel component fixture",
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        },
        cell_interior_degree_overrides=overrides,
        variable_trace_from_cell_degrees=(
            variable_trace_from_cell_degrees
        ),
    )


def test_incremental_plan_records_one_stage_without_claiming_two_levels() -> None:
    payload = _payload(stages=(_STAGE_ONE,))

    assert payload["refinement_stage_count"] == 1
    assert payload["maximum_level"] == 2
    audit = payload["multilevel_audit"]
    assert audit["actual_maximum_level"] == 1
    assert audit["true_multilevel"] is False
    assert audit["user_mark_component_count"] == 2
    assert audit["spatially_separated_user_patches"] is True
    assert audit["leaf_level_counts"]["1"] > 0
    assert "2" not in audit["leaf_level_counts"]
    assert sum(
        row["count"]
        for row in audit["leaf_inventory"]["leaf_size_histogram"]
    ) == payload["expected_forest"]["leaf_cell_count"]


def test_two_stage_plan_is_deterministic_and_audits_closure() -> None:
    first = _payload()
    second = _payload()

    assert first == second
    assert first["refinement_stage_count"] == 2
    audit = first["multilevel_audit"]
    assert audit["actual_maximum_level"] == 2
    assert audit["true_multilevel"] is True
    assert audit["user_mark_component_count"] == 2
    assert audit["spatially_separated_user_patches"] is True
    assert set(audit["leaf_level_counts"]) == {"0", "1", "2"}
    assert audit["maximum_adjacent_level_jump"] == 1
    assert audit["strong_2_to_1_balance"] is True
    assert audit["material_interface_hanging_face_count"] == 0
    assert all(
        row["matching"]
        for row in audit["periodic_boundary_audit"].values()
    )
    assert any(
        stage["closure_added_leaves"]
        for stage in first["refinement_stages"]
    )
    material_count = sum(
        row["count"]
        for row in audit["leaf_inventory"][
            "material_level_histogram"
        ]
    )
    assert material_count == first["expected_forest"]["leaf_cell_count"]


def test_two_stage_carrier_supports_p4_p5_p6_interiors_and_constraints() -> None:
    p4_box = (0.0, 0.0, 120.0, 4.125, 3.125, 122.5)
    p5_box = (4.125, 0.0, 120.0, 8.25, 3.125, 122.5)
    payload = _payload(overrides={p4_box: 4, p5_box: 5})
    path = _shared_plan_path(
        payload,
        name=f"multilevel-p456-mpi{MPI.COMM_WORLD.size}",
    )
    cfg = target_stage4_config(degree=6, h_nm=100.0)
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

    assert context.audit["true_multilevel"] is True
    assert context.audit["maximum_level"] == 2
    assert context.audit["refinement_stage_count"] == 2
    assert context.audit["cell_interior_degree_counts"]["p4"] == 1
    assert context.audit["cell_interior_degree_counts"]["p5"] == 1
    assert authority.degree_plan.audit["cell_degree_counts"]["p4"] == 1
    assert authority.degree_plan.audit["cell_degree_counts"]["p5"] == 1
    assert authority.audit["active_fe_dof_gate_pass"] is True
    assert set(
        authority.trace_constraints.audit["constraint_kinds"]
    ) == {"floquet", "hanging"}


def test_two_stage_cell_degrees_drive_true_variable_exact_sequence_trace() -> None:
    seed_payload = _payload()
    seed_path = _shared_plan_path(
        seed_payload,
        name=f"multilevel-variable-trace-seed-mpi{MPI.COMM_WORLD.size}",
    )
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    seed_mesh = build_stage4_local_h_mesh_data(
        cfg,
        seed_path,
        comm=MPI.COMM_WORLD,
    )
    seed_context = seed_mesh.local_h_context
    assert isinstance(seed_context, Stage4LocalHContext)
    degree_by_box = {
        cell.box: 4 + int(cell.key.level)
        for cell in seed_context.forest.leaves
    }
    payload = _payload(
        overrides=degree_by_box,
        variable_trace_from_cell_degrees=True,
    )
    path = _shared_plan_path(
        payload,
        name=f"multilevel-variable-trace-mpi{MPI.COMM_WORLD.size}",
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

    physical = authority.audit["physical_trace"]
    degree = authority.degree_plan.audit
    constraints = authority.trace_constraints.audit
    assert context.audit["variable_trace_from_cell_degrees"] is True
    assert physical["variable_trace_opt_in"] is True
    assert set(physical["trace_degree_values"]) == {4, 5, 6}
    assert degree["schema_version"] == (
        "task035e.local-h-variable-exact-sequence-plan.v1"
    )
    assert degree["cell_driven_variable_trace_component_complete"] is True
    assert degree["combined_hp_space_construction_complete"] is False
    assert degree["compiled_cell_tensor_binding_complete"] is False
    assert degree[
        "inactive_high_order_trace_rows_globally_numbered"
    ] is False
    assert constraints["local_variable_trace_implemented"] is True
    assert constraints["selective_trace_action"] == (
        "cell_driven_p4_p5_p6_exact_sequence_trace"
    )
    assert authority.audit["active_fe_dof_gate_pass"] is True
    assert authority.audit["active_fe_dof_hard_gate_active"] is False
    assert authority.audit["active_fe_dof_gate_limit"] is None
    assert authority.audit["active_fe_dof_advisory_target"] == 90_000


def test_multilevel_plan_fails_closed_on_stage_or_geometry_drift() -> None:
    payload = _payload()
    payload["refinement_stages"][1]["closure_added_leaves"] = []
    path = _shared_plan_path(
        payload,
        name=f"multilevel-tamper-mpi{MPI.COMM_WORLD.size}",
    )
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    with pytest.raises(ValueError, match="identity drifted"):
        build_stage4_local_h_mesh_data(
            cfg,
            path,
            comm=MPI.COMM_WORLD,
        )

    clean_path = _shared_plan_path(
        _payload(),
        name=f"multilevel-geometry-mpi{MPI.COMM_WORLD.size}",
    )
    with pytest.raises(ValueError, match="base geometry differs"):
        build_stage4_local_h_mesh_data(
            replace(cfg, mesh_target_size=15.0),
            clean_path,
            comm=MPI.COMM_WORLD,
        )
