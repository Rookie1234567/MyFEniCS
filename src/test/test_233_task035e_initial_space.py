from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json

import pytest

from src.adaptivity.stage4_local_h import (
    stage4_multilevel_local_h_forest_catalog,
)
from src.adaptivity.task035e_initial_space import (
    INITIAL_SPACE_ALGORITHM_SHA256,
    build_task035e_initial_space_plan,
)
from src.common.config_3d import target_stage4_config


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _json_sha256(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


@pytest.mark.parametrize(("path_id", "h_nm"), (("A", 20.0), ("B", 15.0)))
def test_initial_space_is_deterministic_complete_and_replayable(
    path_id: str,
    h_nm: float,
) -> None:
    cfg = target_stage4_config(degree=6, h_nm=h_nm)
    first = build_task035e_initial_space_plan(
        cfg,
        path_id=path_id,
        source_sha=_SOURCE_SHA,
    )
    second = build_task035e_initial_space_plan(
        cfg,
        path_id=path_id,
        source_sha=_SOURCE_SHA,
    )

    assert first.canonical_plan_json == second.canonical_plan_json
    assert dict(first.audit) == dict(second.audit)
    assert first.audit["algorithm_sha256"] == (
        INITIAL_SPACE_ALGORITHM_SHA256
    )
    assert first.audit["plan_payload_sha256"] == hashlib.sha256(
        first.canonical_plan_json.encode("ascii")
    ).hexdigest()
    authority = dict(first.audit)
    authority_sha = authority.pop("authority_sha256")
    assert authority_sha == _json_sha256(authority)

    payload = first.plan_payload()
    assert payload["schema_version"] == (
        "task035e.stage4-multilevel-local-h-refinement-plan.v1"
    )
    assert payload["refinement_stage_count"] == 1
    assert payload["maximum_level"] == 2
    assert payload["trace_degree"] == 4
    assert payload["cell_interior_degree"] == 6
    assert payload["variable_trace_from_cell_degrees"] is True
    assert payload["ordinary_default_changed"] is False
    multilevel = payload["multilevel_audit"]
    assert multilevel["actual_maximum_level"] == 1
    assert multilevel["true_multilevel"] is False
    assert multilevel["user_mark_component_count"] == 2
    assert multilevel["spatially_separated_user_patches"] is True
    assert multilevel["strong_2_to_1_balance"] is True
    assert all(
        row["matching"]
        for row in multilevel["periodic_boundary_audit"].values()
    )

    degree_rows = payload["cell_interior_degrees"]
    assert len(degree_rows) == len(first.forest.leaves)
    assert len(first.cell_degree_by_key) == len(first.forest.leaves)
    assert set(first.cell_degree_by_key) == set(first.forest.leaf_by_key)
    assert set(first.cell_degree_by_key.values()) == {4, 5}
    assert first.audit["cell_degree_counts"]["p4"] > 0
    assert first.audit["cell_degree_counts"]["p5"] > 0
    assert first.audit["cell_degree_counts"]["p6"] == 0
    assert first.audit["complete_cell_degree_map"] is True
    assert first.audit["inactive_p6_requested_by_initial_map"] is False
    assert payload["cell_interior_degree_plan_sha256"] == _json_sha256(
        [
            {
                "box": [*row["lower"], *row["upper"]],
                "degree": row["degree"],
            }
            for row in degree_rows
        ]
    )

    stages = tuple(
        tuple(
            (*row["lower"], *row["upper"])
            for row in stage["marked_leaves"]
        )
        for stage in payload["refinement_stages"]
    )
    rebuilt = stage4_multilevel_local_h_forest_catalog(
        cfg,
        stages,
        comm_size=8,
    )
    assert rebuilt.audit["leaf_catalog_sha256"] == (
        first.audit["leaf_catalog_sha256"]
    )
    assert rebuilt.audit["hanging_face_catalog_sha256"] == (
        payload["expected_forest"]["hanging_face_catalog_sha256"]
    )


@pytest.mark.parametrize(("path_id", "h_nm"), (("A", 20.0), ("B", 15.0)))
def test_initial_space_guards_ports_and_material_interfaces_at_p5(
    path_id: str,
    h_nm: float,
) -> None:
    plan = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=h_nm),
        path_id=path_id,
        source_sha=_SOURCE_SHA,
    )
    guards = plan.audit["guard_cells"]

    assert plan.audit["all_guard_cells_at_least_p5"] is True
    assert all(row["degree"] == 5 for row in guards)
    assert any("physical_z_port" in row["reasons"] for row in guards)
    assert any("material_interface" in row["reasons"] for row in guards)
    assert plan.audit["pde_solve_complete"] is False
    assert plan.audit["pde_accuracy_credit"] is False
    assert plan.audit["true_multilevel_claimed"] is False
    assert plan.audit["multilevel_ready_maximum_level"] == 2


def test_two_starting_paths_are_independent_but_share_one_frozen_algorithm() -> None:
    path_a = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        path_id="A",
        source_sha=_SOURCE_SHA,
    )
    path_b = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=15.0),
        path_id="B",
        source_sha=_SOURCE_SHA,
    )

    assert path_a.audit["algorithm_sha256"] == path_b.audit[
        "algorithm_sha256"
    ]
    assert path_a.audit["config_identity_sha256"] != path_b.audit[
        "config_identity_sha256"
    ]
    assert path_a.audit["root_catalog_sha256"] != path_b.audit[
        "root_catalog_sha256"
    ]
    assert path_a.audit["plan_payload_sha256"] != path_b.audit[
        "plan_payload_sha256"
    ]
    assert path_a.audit["patch_boxes"] != path_b.audit["patch_boxes"]

    for plan in (path_a, path_b):
        provenance = plan.plan_payload()["provenance"]
        closed = dict(provenance)
        digest = closed.pop("provenance_sha256")
        assert digest == _json_sha256(closed)
        assert provenance["solved_field_inputs_consumed"] is False
        assert provenance["goal_value_inputs_consumed"] is False
        assert provenance["dwr_inputs_consumed"] is False
        assert provenance["error_map_inputs_consumed"] is False


def test_initial_planner_has_a_narrow_physics_only_input_surface() -> None:
    assert tuple(
        inspect.signature(
            build_task035e_initial_space_plan
        ).parameters
    ) == ("cfg", "path_id", "source_sha", "comm_size")

    with pytest.raises(ValueError, match="Path A requires"):
        build_task035e_initial_space_plan(
            target_stage4_config(degree=6, h_nm=15.0),
            path_id="A",
            source_sha=_SOURCE_SHA,
        )
    with pytest.raises(ValueError, match="MPI8-bound"):
        build_task035e_initial_space_plan(
            target_stage4_config(degree=6, h_nm=20.0),
            path_id="A",
            source_sha=_SOURCE_SHA,
            comm_size=4,
        )
    with pytest.raises(ValueError, match="13.5 nm"):
        build_task035e_initial_space_plan(
            replace(
                target_stage4_config(degree=6, h_nm=20.0),
                lambda0=14.0,
            ),
            path_id="A",
            source_sha=_SOURCE_SHA,
        )
    with pytest.raises(ValueError, match="source_sha"):
        build_task035e_initial_space_plan(
            target_stage4_config(degree=6, h_nm=20.0),
            path_id="A",
            source_sha="dirty",
        )


def test_plan_payload_returns_an_independent_copy() -> None:
    plan = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        path_id="A",
        source_sha=_SOURCE_SHA,
    )
    changed = plan.plan_payload()
    changed["trace_degree"] = 6

    assert plan.plan_payload()["trace_degree"] == 4
