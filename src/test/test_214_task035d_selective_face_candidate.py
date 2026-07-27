from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from mpi4py import MPI

from src.adaptivity.stage4_local_h import (
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
)
from src.adaptivity.selective_face_root_transfer import (
    build_selective_face_root_transfer,
)
from src.common.config_3d import target_stage4_config


ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)
CANDIDATE_ID = "h15_grating_top_selective_p6_faces_v1"
PLAN = (
    CASE_DIR
    / "records"
    / "h15_grating_top_selective_p6_faces_plan_v1.json"
)
BASE_PLAN = CASE_DIR / "records" / "h15_top_air_local_h_plan_v1.json"


def _generator_module():
    path = CASE_DIR / "generate_local_h_production_authority.py"
    spec = importlib.util.spec_from_file_location(
        "task035d_selective_face_authority_generator",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the Task035d authority generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selective_face_plan_is_exact_h15_base_plus_ten_faces() -> None:
    generator = _generator_module()
    generated = generator.build_plan_payload(CANDIDATE_ID)
    tracked = json.loads(PLAN.read_text(encoding="utf-8"))
    base = json.loads(BASE_PLAN.read_text(encoding="utf-8"))

    assert generated == tracked
    assert tracked["marked_root_boxes"] == base["marked_root_boxes"]
    assert tracked["expected_forest"] == base["expected_forest"]
    assert tracked["trace_degree"] == 5
    assert tracked["cell_interior_degree"] == 6
    assert tuple(
        tuple(map(int, key))
        for key in tracked["selected_p6_face_geometry_keys"]
    ) == generator.SELECTIVE_P6_FACE_GEOMETRY_KEYS
    assert tracked["provenance"][
        "goal_oriented_selection_credit_before_run"
    ] is False
    assert tracked["ordinary_default_changed"] is False


def test_selective_face_candidate_has_only_200_new_physical_rows() -> None:
    cfg = target_stage4_config(degree=6, h_nm=15.0)
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        PLAN,
        comm=MPI.COMM_WORLD,
    )
    context = mesh_data.local_h_context
    assert context is not None
    reduction = build_stage4_local_h_reduction_authority(
        context,
        phase_x=cfg.floquet_phase_x,
        phase_y=cfg.floquet_phase_y,
    )
    physical = reduction.audit["physical_trace"]
    degree = reduction.audit["degree_plan"]

    assert reduction.audit["raw_broken_active_fe_dofs"] == 84_375
    assert reduction.audit["raw_broken_trace_rows"] == 24_075
    assert reduction.audit["hanging_slave_rows"] == 1_250
    assert reduction.audit["periodic_slave_rows"] == 4_235
    assert (
        reduction.audit["actual_full3d_equivalent_active_fe_dofs"]
        == 83_125
    )
    assert reduction.audit["independent_trace_rows"] == 18_590
    assert physical["trace_degree_values"] == [5, 6]
    assert physical["selected_p6_face_count"] == 10
    assert physical["selected_p6_periodic_orbit_count"] == 0
    assert physical["selective_trace_full3d_dof_delta"] == 200
    assert degree["local_variable_trace_implemented"] is True
    assert degree["cell_degree_counts"] == {"p4": 0, "p5": 0, "p6": 134}
    assert reduction.trace_constraints.audit[
        "hanging_or_floquet_slave_rows_globally_numbered"
    ] is False
    assert reduction.audit["active_fe_dof_gate_pass"] is True


def test_actual_ten_face_full_closure_transfer_and_shared_edges_close() -> None:
    cfg = target_stage4_config(degree=6, h_nm=15.0)
    coarse_mesh = build_stage4_local_h_mesh_data(
        cfg,
        BASE_PLAN,
        comm=MPI.COMM_WORLD,
    )
    enriched_mesh = build_stage4_local_h_mesh_data(
        cfg,
        PLAN,
        comm=MPI.COMM_WORLD,
    )
    assert coarse_mesh.local_h_context is not None
    assert enriched_mesh.local_h_context is not None
    coarse = build_stage4_local_h_reduction_authority(
        coarse_mesh.local_h_context,
        phase_x=cfg.floquet_phase_x,
        phase_y=cfg.floquet_phase_y,
    )
    enriched = build_stage4_local_h_reduction_authority(
        enriched_mesh.local_h_context,
        phase_x=cfg.floquet_phase_x,
        phase_y=cfg.floquet_phase_y,
    )
    assert coarse.trace_constraints is not None
    assert enriched.trace_constraints is not None
    transfer = build_selective_face_root_transfer(
        coarse.trace_constraints.authority,
        enriched.trace_constraints.authority,
        auxiliary_rows=80,
    )
    audit = transfer.audit
    assert audit["pass"] is True
    assert transfer.trace_injection.shape == (18_590, 18_390)
    assert transfer.total_injection.shape == (18_670, 18_470)
    assert (
        audit["affected_root_row_count"]
        - audit["affected_coarse_column_count"]
        == 200
    )
    assert (
        audit["selected_patch_injection_rank"]
        == audit["affected_coarse_column_count"]
    )
    assert audit["face_generator_rank"] == 200
    support = audit["selected_face_root_support_catalog"]
    assert len(support) == 10
    assert sum(
        row["constrained_physical_closure_rows"] for row in support
    ) > 0
    assert all(
        row["physical_closure_rows"] == 80
        and row["independent_root_support_rows"]
        - row["local_injection_rank"]
        == 20
        and row["local_complement_dimension"] == 20
        for row in support
    )
    assert audit["face_generator_global_cross_error_max"] <= 2.0e-10
    assert audit["face_generator_projector_error_max"] <= 2.0e-10
    assert 1.0 <= audit["face_generator_gram_condition_number"] <= 1.0e8
