from __future__ import annotations

import numpy as np
import pytest

from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
)
from src.adaptivity.task035e_local_shadows import (
    build_h_shadow_geometry,
    build_local_shadow_catalog,
    close_h_refine_balance_budget_targets,
    evaluate_nested_shadow_system,
)


def _boxes(nx: int, ny: int) -> tuple[tuple[float, ...], ...]:
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


def test_actual_h_shadow_records_requested_and_closure_splits() -> None:
    forest = build_root_dyadic_hexa_forest(
        _boxes(3, 3),
        [1] * 9,
        periodic_axes=("x", "y"),
    )
    first = build_h_shadow_geometry(
        forest,
        (DyadicHexKey(0, 0, 0, 0, 0),),
    )
    assert first.audit["pass"] is True
    assert first.net_added_leaf_count == 28
    assert len(first.requested_split_keys) == 1
    assert len(first.closure_split_keys) == 3
    assert first.audit["leaf_level_counts"] == {"0": 5, "1": 32}

    second = build_h_shadow_geometry(
        first.forest,
        (DyadicHexKey(0, 1, 0, 0, 0),),
    )
    assert second.audit["pass"] is True
    assert second.audit["leaf_level_counts"]["2"] > 0
    assert second.audit["maximum_adjacent_level_jump"] == 1
    assert second.audit["strong_2_to_1_balance"] is True
    assert all(
        row["matching"]
        for row in second.audit["periodic_boundary_audit"].values()
    )


def test_blind_shadow_windows_are_bounded_rotating_and_order_independent() -> None:
    targets = tuple(f"cell:r0:l1:i{index}:j0:k0" for index in range(160))
    p0 = build_local_shadow_catalog(
        targets,
        lane="p",
        path_id="A",
        cycle_index=0,
    )
    p1 = build_local_shadow_catalog(
        tuple(reversed(targets)),
        lane="p",
        path_id="A",
        cycle_index=1,
    )
    h0 = build_local_shadow_catalog(
        targets,
        lane="h",
        path_id="A",
        cycle_index=0,
    )
    h1 = build_local_shadow_catalog(
        targets,
        lane="h",
        path_id="A",
        cycle_index=1,
    )

    assert len(p0.selected_target_ids) == 8
    assert len(p1.selected_target_ids) == 8
    assert set(p0.selected_target_ids).isdisjoint(p1.selected_target_ids)
    assert len(h0.selected_target_ids) == 4
    assert len(h1.selected_target_ids) == 4
    assert set(h0.selected_target_ids).isdisjoint(h1.selected_target_ids)
    assert p0.ordered_target_ids == p1.ordered_target_ids
    assert p0.audit["hidden_reference_consumed"] is False
    assert p0.audit["solved_field_consumed"] is False
    assert p0.audit["accuracy_credit"] is False
    assert p0.audit["eligible_target_count"] == 160

    replay = build_local_shadow_catalog(
        tuple(reversed(targets)),
        lane="p",
        path_id="A",
        cycle_index=0,
    )
    assert replay.selected_target_ids == p0.selected_target_ids
    assert replay.audit["catalog_sha256"] == p0.audit["catalog_sha256"]


def test_h_shadow_balance_budget_uses_closed_leaf_cost() -> None:
    forest = build_root_dyadic_hexa_forest(
        _boxes(3, 3),
        [1] * 9,
        periodic_axes=("x", "y"),
    )
    requested = tuple(
        DyadicHexKey(root, 0, 0, 0, 0)
        for root in (0, 4, 8)
    )
    selected, audit = close_h_refine_balance_budget_targets(
        forest,
        requested,
        maximum_level=2,
        maximum_net_added_leaf_count=28,
    )

    assert selected
    assert audit["pass"] is True
    assert audit["considered_target_count"] == 3
    assert audit["final_net_added_leaf_count"] <= 28
    assert audit["selected_target_count"] < len(requested)
    assert audit["hidden_reference_consumed"] is False
    assert audit["solved_field_consumed"] is False
    assert audit["accuracy_credit"] is False
    replay, replay_audit = close_h_refine_balance_budget_targets(
        forest,
        requested,
        maximum_level=2,
        maximum_net_added_leaf_count=28,
    )
    assert replay == selected
    assert (
        replay_audit["closure_budget_sha256"]
        == audit["closure_budget_sha256"]
    )


@pytest.mark.parametrize(
    ("lane", "path_id", "cycle_index"),
    (("q", "A", 0), ("p", "C", 0), ("p", "A", 6)),
)
def test_blind_shadow_window_rejects_invalid_identity(
    lane: str,
    path_id: str,
    cycle_index: int,
) -> None:
    with pytest.raises(ValueError):
        build_local_shadow_catalog(
            ("cell:r0:l1:i0:j0:k0",),
            lane=lane,
            path_id=path_id,
            cycle_index=cycle_index,
        )


@pytest.mark.parametrize("action_kind", ["p-up", "h-refine"])
def test_signed_nested_shadow_matches_actual_linear_goal_delta(
    action_kind: str,
) -> None:
    fine_matrix = np.asarray(
        [
            [4.0 + 0.0j, 0.2 + 0.1j, 0.0],
            [0.2 - 0.1j, 3.0 + 0.0j, 0.3j],
            [0.0, -0.3j, 2.5 + 0.0j],
        ],
        dtype=np.complex128,
    )
    transfer = np.asarray(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.4, -0.2j],
        ],
        dtype=np.complex128,
    )
    current_matrix = transfer.conj().T @ fine_matrix @ transfer
    fine_rhs = np.asarray([1.0 + 0.2j, -0.3j, 0.4 + 0.1j])
    current_rhs = transfer.conj().T @ fine_rhs
    current_state = np.linalg.solve(current_matrix, current_rhs)
    gradients = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0j, 0.0],
            [0.2, -0.1j, 0.7],
        ],
        dtype=np.complex128,
    )
    evidence = evaluate_nested_shadow_system(
        action_kind=action_kind,
        goal_ids=("g0", "g1", "g2"),
        current_matrix=current_matrix,
        current_rhs=current_rhs,
        current_state=current_state,
        shadow_matrix=fine_matrix,
        shadow_rhs=fine_rhs,
        prolongation=transfer,
        shadow_goal_gradients=gradients,
    )

    assert evidence.audit["component_pass"] is True
    assert evidence.audit["formal_d4_effectivity_credit"] is False
    assert evidence.audit["independent_candidate_pde_bound"] is False
    assert evidence.audit["added_rows"] == 1
    assert evidence.audit["factor_two_fraction"] == 1.0
    assert all(
        row.algebraic_effectivity == pytest.approx(1.0)
        for row in evidence.goals
        if not row.safe_zero
    )


def test_signed_shadow_fails_component_gate_on_invalid_current_state() -> None:
    evidence = evaluate_nested_shadow_system(
        action_kind="h-refine",
        goal_ids=("g",),
        current_matrix=np.asarray([[1.0 + 0.0j]]),
        current_rhs=np.asarray([1.0 + 0.0j]),
        current_state=np.asarray([2.0 + 0.0j]),
        shadow_matrix=np.asarray(
            [[1.0 + 0.0j, 0.0], [0.0, 2.0 + 0.0j]]
        ),
        shadow_rhs=np.asarray([1.0 + 0.0j, 1.0 + 0.0j]),
        prolongation=np.asarray([[1.0 + 0.0j], [0.0 + 0.0j]]),
        shadow_goal_gradients=np.asarray(
            [[0.0 + 0.0j, 1.0 + 0.0j]]
        ),
    )

    assert evidence.audit["component_pass"] is False
    assert evidence.audit["current_equation_relative_residual"] > 0.0
