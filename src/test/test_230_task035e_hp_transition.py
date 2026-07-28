from __future__ import annotations

import copy
import json

import pytest

from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
)
from src.adaptivity.task035e_hp_transition import (
    build_initial_hp_transition_state,
    canonical_hp_cell_target_id,
    close_hp_transition,
    hp_transition_action_payload,
    rebuild_hp_transition_state,
)


_SOURCE_SHA = "a" * 40
_ALGORITHM_SHA = "b" * 64


def _rehash_action(action: dict[str, object]) -> dict[str, object]:
    import hashlib

    result = copy.deepcopy(action)
    result.pop("action_sha256", None)
    result["action_sha256"] = hashlib.sha256(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    return result


def _boxes(
    nx: int,
    ny: int,
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        (
            float(ix),
            float(iy),
            0.0,
            float(ix + 1),
            float(iy + 1),
            1.0,
        )
        for iy in range(ny)
        for ix in range(nx)
    )


def _initial_state():
    forest = build_root_dyadic_hexa_forest(
        _boxes(3, 3),
        [1] * 9,
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )
    degrees = {cell.key: 4 for cell in forest.leaves}
    return build_initial_hp_transition_state(
        forest,
        degrees,
        source_sha=_SOURCE_SHA,
        algorithm_sha256=_ALGORITHM_SHA,
    )


def test_same_forest_p_up_and_down_are_prefix_bound() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    p_up = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.center",
        kind="p-up",
        degree_deltas={center: 1},
    )
    raised = close_hp_transition(initial, p_up)

    assert p_up["canonical_target_ids"] == [
        "cell:r4:l0:i0:j0:k0"
    ]
    assert p_up["from_leaf_catalog_sha256"] == initial.audit[
        "leaf_catalog_sha256"
    ]
    assert p_up["from_cell_degree_plan_sha256"] == initial.audit[
        "cell_degree_plan_sha256"
    ]
    assert p_up["expected_next_leaf_catalog_sha256"] == raised.audit[
        "leaf_catalog_sha256"
    ]
    assert p_up["expected_next_cell_degree_plan_sha256"] == raised.audit[
        "cell_degree_plan_sha256"
    ]
    assert raised.forest is initial.forest
    assert raised.cell_degree_by_key[center] == 5
    assert raised.cycle_index == 1
    assert raised.stage_action_sha256s == (p_up["action_sha256"],)
    assert raised.audit["transition"]["checks"]["stage_prefix_valid"] is True
    assert raised.audit["pde_solve_complete"] is False
    assert raised.audit["d4_shadow_verification_complete"] is False
    assert all(
        row["measurement_status"] == "not_measured"
        for row in raised.audit["structural_cost"].values()
    )
    json.dumps(dict(raised.audit), sort_keys=True)

    p_down = hp_transition_action_payload(
        raised,
        action_id="cycle2.p-down.center",
        kind="p-down",
        degree_deltas={center: -1},
    )
    lowered = close_hp_transition(raised, p_down)
    assert lowered.cell_degree_by_key[center] == 4
    assert lowered.cycle_index == 2
    assert lowered.audit["stage_prefix_sha256"] != (
        raised.audit["stage_prefix_sha256"]
    )


def test_p_keep_advances_only_cycle_action_chain_and_state_identity() -> None:
    initial = _initial_state()
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-keep.stability-repeat",
        kind="p-keep",
        degree_deltas={},
    )
    repeated = close_hp_transition(initial, action)

    assert action["canonical_target_ids"] == []
    assert action["requested_split_keys"] == []
    assert action["degree_deltas"] == []
    assert action["maximum_level"] is None
    assert repeated.forest is initial.forest
    assert dict(repeated.cell_degree_by_key) == dict(
        initial.cell_degree_by_key
    )
    for name in (
        "leaf_catalog_sha256",
        "cell_degree_plan_sha256",
        "forest_geometry_sha256",
        "degree_plan_sha256",
    ):
        assert repeated.audit[name] == initial.audit[name]
    assert repeated.cycle_index == initial.cycle_index + 1
    assert repeated.stage_action_sha256s == (action["action_sha256"],)
    assert repeated.audit["stage_prefix_sha256"] != initial.audit[
        "stage_prefix_sha256"
    ]
    assert repeated.state_sha256 != initial.state_sha256
    assert repeated.audit["transition"]["action_kind"] == "p-keep"
    assert repeated.audit["transition"]["canonical_target_ids"] == []


@pytest.mark.parametrize(
    ("degree_deltas", "requested_split_keys", "maximum_level", "match"),
    (
        (
            {DyadicHexKey(4, 0, 0, 0, 0): 1},
            (),
            None,
            "empty splits/deltas and null maximum_level",
        ),
        (
            {},
            (DyadicHexKey(4, 0, 0, 0, 0),),
            None,
            "empty splits/deltas and null maximum_level",
        ),
        (
            {},
            (),
            2,
            "empty splits/deltas and null maximum_level",
        ),
    ),
)
def test_p_keep_rejects_any_numerical_target_or_refinement(
    degree_deltas: dict[DyadicHexKey, int],
    requested_split_keys: tuple[DyadicHexKey, ...],
    maximum_level: int | None,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        hp_transition_action_payload(
            _initial_state(),
            action_id="cycle1.p-keep.invalid",
            kind="p-keep",
            degree_deltas=degree_deltas,
            requested_split_keys=requested_split_keys,
            maximum_level=maximum_level,
        )


def test_state_can_be_rebuilt_only_with_complete_bound_action_chain() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.rebuild",
        kind="p-up",
        degree_deltas={center: 1},
    )
    closed = close_hp_transition(initial, action)

    rebuilt = rebuild_hp_transition_state(
        closed.forest,
        closed.cell_degree_by_key,
        source_sha=closed.source_sha,
        algorithm_sha256=closed.algorithm_sha256,
        cycle_index=closed.cycle_index,
        stage_action_sha256s=closed.stage_action_sha256s,
        expected_state_sha256=closed.state_sha256,
        expected_stage_prefix_sha256=closed.audit[
            "stage_prefix_sha256"
        ],
    )

    assert rebuilt.state_sha256 == closed.state_sha256
    assert rebuilt.stage_action_sha256s == closed.stage_action_sha256s
    assert rebuilt.audit["status"] == (
        "hp_transition_rebuilt_component_state"
    )
    with pytest.raises(ValueError, match="prefix length"):
        rebuild_hp_transition_state(
            closed.forest,
            closed.cell_degree_by_key,
            source_sha=closed.source_sha,
            algorithm_sha256=closed.algorithm_sha256,
            cycle_index=closed.cycle_index,
            stage_action_sha256s=(),
            expected_state_sha256=closed.state_sha256,
            expected_stage_prefix_sha256=closed.audit[
                "stage_prefix_sha256"
            ],
        )
    with pytest.raises(ValueError, match="stage prefix drifted"):
        rebuild_hp_transition_state(
            closed.forest,
            closed.cell_degree_by_key,
            source_sha=closed.source_sha,
            algorithm_sha256=closed.algorithm_sha256,
            cycle_index=closed.cycle_index,
            stage_action_sha256s=closed.stage_action_sha256s,
            expected_state_sha256=closed.state_sha256,
            expected_stage_prefix_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="state identity drifted"):
        rebuild_hp_transition_state(
            closed.forest,
            closed.cell_degree_by_key,
            source_sha=closed.source_sha,
            algorithm_sha256=closed.algorithm_sha256,
            cycle_index=closed.cycle_index,
            stage_action_sha256s=closed.stage_action_sha256s,
            expected_state_sha256="0" * 64,
            expected_stage_prefix_sha256=closed.audit[
                "stage_prefix_sha256"
            ],
        )


def test_initial_state_rebuild_is_deterministic_and_empty_prefix_bound() -> None:
    initial = _initial_state()
    rebuilt = rebuild_hp_transition_state(
        initial.forest,
        initial.cell_degree_by_key,
        source_sha=initial.source_sha,
        algorithm_sha256=initial.algorithm_sha256,
        cycle_index=0,
        stage_action_sha256s=[],
        expected_state_sha256=initial.state_sha256,
        expected_stage_prefix_sha256=initial.audit[
            "stage_prefix_sha256"
        ],
    )

    assert rebuilt.state_sha256 == initial.state_sha256
    assert rebuilt.stage_action_sha256s == ()
    assert rebuilt.audit["status"] == (
        "hp_transition_initial_component_state"
    )


def test_one_real_h_stage_inherits_parent_then_allows_child_p_one() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    enriched_child = center.children()[0]
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.h-refine.center-child-p-up",
        kind="h-refine",
        requested_split_keys=(center,),
        degree_deltas={enriched_child: 1},
        maximum_level=2,
    )
    refined = close_hp_transition(initial, action)

    assert action["canonical_target_ids"] == [
        canonical_hp_cell_target_id(center)
    ]
    assert refined.forest.audit["leaf_cell_count"] == 16
    assert refined.forest.audit["strong_2_to_1_balance"] is True
    assert all(
        row["matching"]
        for row in refined.forest.audit["periodic_boundary_audit"].values()
    )
    assert refined.cell_degree_by_key[enriched_child] == 5
    assert all(
        refined.cell_degree_by_key[child] == (
            5 if child == enriched_child else 4
        )
        for child in center.children()
    )
    leaf_transition = refined.audit["transition"]["leaf_transition"]
    assert leaf_transition["removed_leaf_keys"] == [center.to_dict()]
    assert len(leaf_transition["added_leaf_keys"]) == 8
    assert leaf_transition["net_added_leaf_count"] == 7
    assert leaf_transition["every_removed_leaf_explained"] is True
    assert leaf_transition["every_added_leaf_explained"] is True
    assert refined.audit["capability_scope"] == (
        "topology_and_degree_transition_component_only"
    )


def test_rejects_different_roots() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.center",
        kind="p-up",
        degree_deltas={center: 1},
    )
    other_forest = build_root_dyadic_hexa_forest(
        tuple(
            (
                box[0] + 10.0,
                box[1],
                box[2],
                box[3] + 10.0,
                box[4],
                box[5],
            )
            for box in _boxes(3, 3)
        ),
        [1] * 9,
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )
    with pytest.raises(ValueError, match="different roots"):
        close_hp_transition(
            initial,
            action,
            proposed_forest=other_forest,
        )


def test_rejects_two_degree_jump() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    with pytest.raises(ValueError, match=r"only change a degree by \+/-1"):
        hp_transition_action_payload(
            initial,
            action_id="cycle1.illegal-p2",
            kind="p-up",
            degree_deltas={center: 2},
        )


def test_rejects_non_inherited_child_degree() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.h-refine.center",
        kind="h-refine",
        requested_split_keys=(center,),
        degree_deltas={},
        maximum_level=2,
    )
    valid = close_hp_transition(initial, action)
    tampered = dict(valid.cell_degree_by_key)
    tampered[center.children()[0]] = 5
    with pytest.raises(ValueError, match="not inherited/action-explained"):
        close_hp_transition(
            initial,
            action,
            proposed_forest=valid.forest,
            proposed_cell_degree_by_key=tampered,
        )


@pytest.mark.parametrize("maximum_level", (1, 3))
def test_rejects_h_action_outside_two_level_contract(
    maximum_level: int,
) -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    with pytest.raises(ValueError, match="maximum_level=2"):
        hp_transition_action_payload(
            initial,
            action_id=f"cycle1.h.invalid-level-{maximum_level}",
            kind="h-refine",
            requested_split_keys=(center,),
            degree_deltas={},
            maximum_level=maximum_level,
        )


def test_rejects_fake_action_sha_and_stage_prefix() -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.center",
        kind="p-up",
        degree_deltas={center: 1},
    )
    fake_sha = copy.deepcopy(action)
    fake_sha["action_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="action SHA-256 is invalid"):
        close_hp_transition(initial, fake_sha)

    fake_prefix = copy.deepcopy(action)
    fake_prefix["stage_prefix_sha256"] = "f" * 64
    unhashed = dict(fake_prefix)
    unhashed.pop("action_sha256")
    import hashlib

    fake_prefix["action_sha256"] = hashlib.sha256(
        json.dumps(
            unhashed,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    with pytest.raises(ValueError, match="stage prefix"):
        close_hp_transition(initial, fake_prefix)


def test_canonical_targets_are_derived_only_from_closed_action_keys() -> None:
    initial = _initial_state()
    first = DyadicHexKey(2, 0, 0, 0, 0)
    second = DyadicHexKey(6, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.two-cells",
        kind="p-up",
        degree_deltas={second: 1, first: 1},
    )
    assert action["canonical_target_ids"] == [
        "cell:r2:l0:i0:j0:k0",
        "cell:r6:l0:i0:j0:k0",
    ]

    tampered = copy.deepcopy(action)
    tampered["canonical_target_ids"] = ["cell:r5:l0:i0:j0:k0"]
    with pytest.raises(ValueError, match="canonical target IDs drifted"):
        close_hp_transition(initial, _rehash_action(tampered))


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("from_leaf_catalog_sha256", "binding failed"),
        ("from_cell_degree_plan_sha256", "binding failed"),
        ("expected_next_leaf_catalog_sha256", "drifted"),
        ("expected_next_cell_degree_plan_sha256", "drifted"),
        ("action_identity_sha256", "action identity drifted"),
    ),
)
def test_rejects_rehashed_executed_identity_substitution(
    field: str,
    message: str,
) -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.center",
        kind="p-up",
        degree_deltas={center: 1},
    )
    action[field] = "0" * 64
    with pytest.raises(ValueError, match=message):
        close_hp_transition(initial, _rehash_action(action))


@pytest.mark.parametrize(
    "field",
    ("action_id", "kind", "cycle_index", "source_sha"),
)
def test_rejects_rehashed_action_identity_substitution(field: str) -> None:
    initial = _initial_state()
    center = DyadicHexKey(4, 0, 0, 0, 0)
    action = hp_transition_action_payload(
        initial,
        action_id="cycle1.p-up.center",
        kind="p-up",
        degree_deltas={center: 1},
    )
    replacements: dict[str, object] = {
        "action_id": "cycle1.p-up.other",
        "kind": "p-down",
        "cycle_index": 2,
        "source_sha": "f" * 40,
    }
    action[field] = replacements[field]
    with pytest.raises(ValueError):
        close_hp_transition(initial, _rehash_action(action))
