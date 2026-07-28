from __future__ import annotations

import hashlib
import json

import pytest

from src.adaptivity.task035e_hp_transition import (
    build_initial_hp_transition_state,
    hp_transition_action_payload,
)
from src.adaptivity.task035e_initial_space import (
    INITIAL_SPACE_ALGORITHM_SHA256,
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    build_next_solver_plan,
    canonical_solver_content_sha256,
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _initial():
    cfg = target_stage4_config(degree=6, h_nm=20.0)
    initial = build_task035e_initial_space_plan(
        cfg,
        path_id="A",
        source_sha=_SOURCE_SHA,
        comm_size=8,
    )
    state = build_initial_hp_transition_state(
        initial.forest,
        initial.cell_degree_by_key,
        source_sha=_SOURCE_SHA,
        algorithm_sha256=INITIAL_SPACE_ALGORITHM_SHA256,
    )
    return cfg, initial, state


def _rehash_transition_provenance(
    plan: dict[str, object],
) -> dict[str, object]:
    result = json.loads(json.dumps(plan))
    provenance = result["provenance"]
    assert isinstance(provenance, dict)
    provenance.pop("transition_provenance_sha256", None)
    provenance["transition_provenance_sha256"] = _json_sha256(provenance)
    return result


def test_h_action_becomes_true_level_two_solver_plan() -> None:
    cfg, initial, state = _initial()
    target = next(
        cell.key
        for cell in state.forest.leaves
        if cell.key.level == 1
    )
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.h.first",
        kind="h-refine",
        degree_deltas={},
        requested_split_keys=(target,),
        maximum_level=2,
    )
    result = build_next_solver_plan(
        cfg,
        current_plan=initial.plan_payload(),
        state=state,
        action=action,
    )

    plan = dict(result.plan_payload)
    assert result.audit["pass"] is True
    assert result.audit["action_kind"] == "h-refine"
    assert result.audit["actual_maximum_level"] == 2
    assert result.audit["refinement_stage_count"] == 2
    assert plan["multilevel_audit"]["true_multilevel"] is True
    assert set(plan["multilevel_audit"]["leaf_level_counts"]) == {
        "0",
        "1",
        "2",
    }
    assert plan["variable_trace_from_cell_degrees"] is True
    assert len(plan["cell_interior_degrees"]) == len(
        result.next_state.forest.leaves
    )
    provenance = plan["provenance"]
    assert provenance["transition_action_sha256"] == (
        action["action_sha256"]
    )
    assert provenance["transition_action_id"] == action["action_id"]
    assert provenance["transition_action_kind"] == action["kind"]
    assert provenance["transition_action_cycle_index"] == (
        action["cycle_index"]
    )
    assert provenance["transition_action_source_sha"] == (
        action["source_sha"]
    )
    assert provenance["transition_action_target_ids"] == (
        action["canonical_target_ids"]
    )
    assert provenance["from_leaf_catalog_sha256"] == state.audit[
        "leaf_catalog_sha256"
    ]
    assert provenance["from_cell_degree_plan_sha256"] == state.audit[
        "cell_degree_plan_sha256"
    ]
    assert provenance["next_leaf_catalog_sha256"] == (
        result.next_state.audit["leaf_catalog_sha256"]
    )
    assert provenance["next_cell_degree_plan_sha256"] == (
        result.next_state.audit["cell_degree_plan_sha256"]
    )
    assert provenance["stage_action_sha256s"] == [
        action["action_sha256"]
    ]
    assert provenance["next_stage_prefix_sha256"] == (
        result.next_state.audit["stage_prefix_sha256"]
    )
    unhashed_provenance = dict(provenance)
    observed_provenance_sha = unhashed_provenance.pop(
        "transition_provenance_sha256"
    )
    assert observed_provenance_sha == _json_sha256(unhashed_provenance)
    solver_content = dict(plan)
    solver_content.pop("provenance")
    assert provenance[
        "next_plan_canonical_solver_content_sha256"
    ] == _json_sha256(solver_content)
    assert result.audit["next_plan_content_sha256"] == _json_sha256(
        plan
    )
    rebuilt = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=plan,
    )
    assert rebuilt.state_sha256 == result.next_state.state_sha256
    assert rebuilt.stage_action_sha256s == (
        action["action_sha256"],
    )


def test_p_action_keeps_forest_and_changes_only_explained_degrees() -> None:
    cfg, initial, state = _initial()
    target = next(
        key
        for key, degree in state.cell_degree_by_key.items()
        if degree == 4
    )
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.p.first",
        kind="p-up",
        degree_deltas={target: 1},
    )
    result = build_next_solver_plan(
        cfg,
        current_plan=initial.plan_payload(),
        state=state,
        action=action,
    )

    assert result.audit["action_kind"] == "p-up"
    assert result.audit["actual_maximum_level"] == 1
    assert result.audit["refinement_stage_count"] == 1
    assert (
        result.next_state.cell_degree_by_key[target]
        == state.cell_degree_by_key[target] + 1
    )
    assert (
        result.next_state.forest.audit["leaf_catalog_sha256"]
        == state.forest.audit["leaf_catalog_sha256"]
    )
    provenance = result.plan_payload["provenance"]
    assert provenance["goal_values_embedded"] is False
    assert provenance["dwr_values_embedded"] is False
    assert provenance["evaluator_inputs_consumed"] is False
    assert provenance["from_leaf_catalog_sha256"] == (
        provenance["next_leaf_catalog_sha256"]
    )
    assert (
        provenance["from_cell_degree_plan_sha256"]
        != provenance["next_cell_degree_plan_sha256"]
    )


def test_p_keep_preserves_solver_content_but_advances_closed_chain() -> None:
    cfg, initial, state = _initial()
    current_plan = initial.plan_payload()
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.p-keep.stability-repeat",
        kind="p-keep",
        degree_deltas={},
    )
    result = build_next_solver_plan(
        cfg,
        current_plan=current_plan,
        state=state,
        action=action,
    )

    next_plan = dict(result.plan_payload)
    assert action["canonical_target_ids"] == []
    assert result.audit["action_kind"] == "p-keep"
    assert result.audit["canonical_target_ids"] == []
    assert result.audit["checks"][
        "p_keep_solver_content_unchanged"
    ] is True
    assert canonical_solver_content_sha256(
        next_plan
    ) == canonical_solver_content_sha256(current_plan)
    assert result.audit[
        "previous_plan_canonical_solver_content_sha256"
    ] == result.audit["next_plan_canonical_solver_content_sha256"]
    assert result.audit["previous_plan_content_sha256"] != result.audit[
        "next_plan_content_sha256"
    ]
    assert result.next_state.forest is state.forest
    assert dict(result.next_state.cell_degree_by_key) == dict(
        state.cell_degree_by_key
    )
    assert result.next_state.state_sha256 != state.state_sha256
    assert result.next_state.stage_action_sha256s == (
        action["action_sha256"],
    )
    replayed = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=next_plan,
    )
    assert replayed.state_sha256 == result.next_state.state_sha256
    assert replayed.stage_action_sha256s == (
        action["action_sha256"],
    )


def test_initial_and_multicycle_plans_rebuild_without_in_memory_state() -> None:
    cfg, initial, state = _initial()
    initial_plan = initial.plan_payload()
    rebuilt_initial = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=initial_plan,
    )
    assert rebuilt_initial.state_sha256 == state.state_sha256
    initial_provenance = initial_plan["provenance"]
    assert initial_provenance["stage_action_sha256s"] == []
    assert initial_provenance["initial_state_sha256"] == state.state_sha256
    assert initial_provenance["stage_prefix_sha256"] == state.audit[
        "stage_prefix_sha256"
    ]

    first_target = next(
        key
        for key, degree in rebuilt_initial.cell_degree_by_key.items()
        if degree == 4
    )
    first_action = hp_transition_action_payload(
        rebuilt_initial,
        action_id="cycle0.p.replay-first",
        kind="p-up",
        degree_deltas={first_target: 1},
    )
    first = build_next_solver_plan(
        cfg,
        current_plan=initial_plan,
        state=rebuilt_initial,
        action=first_action,
    )
    replayed_first = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=first.plan_payload,
    )
    second_action = hp_transition_action_payload(
        replayed_first,
        action_id="cycle1.p.replay-second",
        kind="p-down",
        degree_deltas={first_target: -1},
    )
    second = build_next_solver_plan(
        cfg,
        current_plan=first.plan_payload,
        state=replayed_first,
        action=second_action,
    )
    replayed_second = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=second.plan_payload,
    )

    assert replayed_second.state_sha256 == second.next_state.state_sha256
    assert replayed_second.stage_action_sha256s == (
        first_action["action_sha256"],
        second_action["action_sha256"],
    )
    assert second.plan_payload["provenance"][
        "next_stage_prefix_sha256"
    ] == replayed_second.audit["stage_prefix_sha256"]


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("stage_action_sha256s", "does not end at its action"),
        ("next_stage_prefix_sha256", "stage prefix drifted"),
        ("next_state_sha256", "state identity drifted"),
    ),
)
def test_rebuild_rejects_rehashed_chain_prefix_or_state_tamper(
    field: str,
    message: str,
) -> None:
    cfg, initial, state = _initial()
    target = next(
        key
        for key, degree in state.cell_degree_by_key.items()
        if degree == 4
    )
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.p.rebuild-tamper",
        kind="p-up",
        degree_deltas={target: 1},
    )
    result = build_next_solver_plan(
        cfg,
        current_plan=initial.plan_payload(),
        state=state,
        action=action,
    )
    tampered = json.loads(json.dumps(dict(result.plan_payload)))
    provenance = tampered["provenance"]
    if field == "stage_action_sha256s":
        provenance[field] = ["0" * 64]
    else:
        provenance[field] = "0" * 64
    tampered = _rehash_transition_provenance(tampered)

    with pytest.raises(ValueError, match=message):
        rebuild_hp_transition_state_from_solver_plan(
            cfg,
            current_plan=tampered,
        )


def test_bridge_rejects_plan_state_drift() -> None:
    cfg, initial, state = _initial()
    target = next(
        key
        for key, degree in state.cell_degree_by_key.items()
        if degree == 4
    )
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.p.drift",
        kind="p-up",
        degree_deltas={target: 1},
    )
    tampered = json.loads(initial.canonical_plan_json)
    tampered["cell_interior_degrees"][0]["degree"] = (
        5
        if tampered["cell_interior_degrees"][0]["degree"] == 4
        else 4
    )
    with pytest.raises(ValueError, match="degree maps differ"):
        build_next_solver_plan(
            cfg,
            current_plan=tampered,
            state=state,
            action=action,
        )


@pytest.mark.parametrize(
    "field",
    ("expected_forest", "cell_interior_degree_plan_sha256"),
)
def test_bridge_rejects_plan_execution_authority_drift(field: str) -> None:
    cfg, initial, state = _initial()
    target = next(
        key
        for key, degree in state.cell_degree_by_key.items()
        if degree == 4
    )
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.p.execution-authority-drift",
        kind="p-up",
        degree_deltas={target: 1},
    )
    tampered = json.loads(initial.canonical_plan_json)
    if field == "expected_forest":
        tampered[field]["leaf_catalog_sha256"] = "0" * 64
    else:
        tampered[field] = "0" * 64
    with pytest.raises(ValueError, match="authority differs"):
        build_next_solver_plan(
            cfg,
            current_plan=tampered,
            state=state,
            action=action,
        )


def test_bridge_is_formally_mpi8_only() -> None:
    cfg, initial, state = _initial()
    target = next(
        key
        for key, degree in state.cell_degree_by_key.items()
        if degree == 4
    )
    action = hp_transition_action_payload(
        state,
        action_id="cycle0.p.mpi",
        kind="p-up",
        degree_deltas={target: 1},
    )
    with pytest.raises(ValueError, match="MPI8"):
        build_next_solver_plan(
            cfg,
            current_plan=initial.plan_payload(),
            state=state,
            action=action,
            comm_size=1,
        )
