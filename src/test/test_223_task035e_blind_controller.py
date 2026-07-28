from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest

from benchmarks.task035e_reference_leak_checker import (
    scan_blind_controller,
    validate_blind_input_manifest,
)
from src.adaptivity.blind_controller import (
    FIXED_GOAL_IDS,
    FORMAL_FIELD_GOAL_IDS,
    FORMAL_GOAL_IDS,
    FORMAL_TOTAL_GOAL_IDS,
    GoalVector,
    InternalGates,
    ShadowCatalog,
    ShadowCost,
    ShadowVerification,
    StabilityRepeatVerification,
    advance_blind_trial,
    blind_tolerance,
    build_cycle_manifest,
    build_shadow_action,
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    compare_frozen_paths,
    freeze_candidate,
)
from src.adaptivity.blind_controller.contracts import normalized_goal_distance
from src.adaptivity.blind_controller.state_machine import (
    BlindCycleInput,
    BlindCycleResult,
    BlindTrial,
    StructuralInventory,
)
from src.adaptivity.hidden_auditor.contracts import CandidateFreezeReceipt


def _sha(character: str) -> str:
    return character * 64


def _resource_authority() -> dict[str, object]:
    return {
        "schema_version": "task035e.resource-authority.v1",
        "active_dofs": 50_000,
        "rows": 30_000,
        "matrix_nnz": 20_000_000,
        "factor_nnz": 100_000_000,
        "solver_peak_bytes": 6_000_000_000,
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }


def _resource_authority_sha256() -> str:
    payload = _resource_authority()
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _p6_saturation(
    *,
    plan_file_sha256: str = _sha("d"),
    mesh_forest_sha256: str = _sha("1"),
    degree_map_sha256: str = _sha("2"),
) -> object:
    return build_unmeasured_p6_saturation_authority(
        p6_target_ids=(),
        current_plan_file_sha256=plan_file_sha256,
        current_mesh_forest_sha256=mesh_forest_sha256,
        current_degree_map_sha256=degree_map_sha256,
    )


def _h_saturation(
    *,
    plan_file_sha256: str = _sha("d"),
    mesh_forest_sha256: str = _sha("1"),
    degree_map_sha256: str = _sha("2"),
) -> object:
    return build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=(),
        periodic_orbit_ids=(),
        orbit_catalog_sha256=_sha("e"),
        current_plan_file_sha256=plan_file_sha256,
        current_mesh_forest_sha256=mesh_forest_sha256,
        current_degree_map_sha256=degree_map_sha256,
    )


def _goals(offset_scale: float = 0.0) -> GoalVector:
    values = {}
    for index, goal_id in enumerate(FORMAL_GOAL_IDS):
        base, unit = _goal_base_and_unit(goal_id)
        values[goal_id] = base + offset_scale * unit * (1 + index % 3)
    return GoalVector.from_mapping(values)


def _goal_base_and_unit(goal_id: str) -> tuple[float, float]:
    if goal_id.endswith(":power"):
        return 1.0e-3, 5.0e-7
    if goal_id in FIXED_GOAL_IDS:
        return 0.1, 1.0e-4
    if goal_id in FORMAL_TOTAL_GOAL_IDS:
        return 0.4, 8.0e-5
    if "interface_" in goal_id:
        return 1.0 if goal_id.startswith("scalar/") else 0.25, 1.0e-2
    if goal_id in FORMAL_FIELD_GOAL_IDS:
        return 1.0 if goal_id.startswith("scalar/") else 0.25, 1.5e-2
    raise AssertionError(f"unclassified formal goal: {goal_id}")


def _action(
    *,
    action_id: str,
    kind: str,
    target: str,
    current: GoalVector,
    strength: float,
    next_mesh_forest_sha256: str = _sha("1"),
    next_degree_map_sha256: str = _sha("2"),
) -> object:
    current_values = current.by_id
    shadow_values = {}
    for goal_id in FORMAL_GOAL_IDS:
        _, unit = _goal_base_and_unit(goal_id)
        delta = strength * unit
        shadow_values[goal_id] = current_values[goal_id] + delta
    shadow = GoalVector.from_mapping(shadow_values)
    deltas = {
        goal_id: shadow_values[goal_id] - current_values[goal_id]
        for goal_id in FORMAL_GOAL_IDS
    }
    if kind in {"p-down", "h-coarsen"}:
        cost = ShadowCost(-10, -5, -100, -200, -1024)
    elif kind == "keep":
        cost = ShadowCost(0, 0, 0, 0, 0)
    else:
        cost = ShadowCost(10, 5, 100, 200, 1024)
    return build_shadow_action(
        action_id=action_id,
        kind=kind,
        target_ids=(target,),
        current=current,
        shadow=shadow,
        signed_dwr_delta=deltas,
        cost=cost,
        sign_consistent=True,
        transition_action_sha256=_sha("a"),
        transition_action_file_sha256=_sha("b"),
        transition_action_identity_sha256=_sha("c"),
        next_mesh_forest_sha256=next_mesh_forest_sha256,
        next_degree_map_sha256=next_degree_map_sha256,
        actual_added_leaf_count=7 if kind == "h-refine" else 0,
    )


def _catalog(
    current: GoalVector,
    *,
    strength: float,
    next_mesh_forest_sha256: str = _sha("1"),
    next_degree_map_sha256: str = _sha("2"),
    current_plan_file_sha256: str = _sha("d"),
    current_mesh_forest_sha256: str = _sha("1"),
    current_degree_map_sha256: str = _sha("2"),
) -> ShadowCatalog:
    return ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(
            _action(
                action_id=f"p-{strength}",
                kind="p-up",
                target="cell:1",
                current=current,
                strength=strength,
                next_mesh_forest_sha256=next_mesh_forest_sha256,
                next_degree_map_sha256=next_degree_map_sha256,
            ),
        ),
        h_actions=(
            _action(
                action_id=f"h-{strength}",
                kind="h-refine",
                target="root:9",
                current=current,
                strength=strength,
                next_mesh_forest_sha256=next_mesh_forest_sha256,
                next_degree_map_sha256=next_degree_map_sha256,
            ),
        ),
        p6_saturation=_p6_saturation(
            plan_file_sha256=current_plan_file_sha256,
            mesh_forest_sha256=current_mesh_forest_sha256,
            degree_map_sha256=current_degree_map_sha256,
        ),
        h_level3_saturation=_h_saturation(
            plan_file_sha256=current_plan_file_sha256,
            mesh_forest_sha256=current_mesh_forest_sha256,
            degree_map_sha256=current_degree_map_sha256,
        ),
    )


def _gates(*, final: bool) -> InternalGates:
    return InternalGates(
        full_explicit_residual=1.0e-11,
        energy_closure_error=2.0e-12,
        absorption_volume=0.4,
        floquet_residual_pass=True,
        hanging_residual_pass=True,
        serial_mpi_identity_pass=final,
        multilevel_mesh_pass=final,
        separated_patch_count=2 if final else 0,
        all_local_levels_present=final,
        algebraic_budget_fraction=0.05 if final else 1.0,
        dtn_budget_fraction=0.05 if final else 1.0,
        postprocess_budget_fraction=0.05 if final else 1.0,
    )


def _verification(
    binding: tuple[str, str, str, str, str, str, str, str],
    *,
    before_output_sha256: str,
    after_output_sha256: str,
    before_goals: GoalVector,
    after_goals: GoalVector,
    next_plan_file_sha256: str = _sha("d"),
    next_plan_content_sha256: str = _sha("e"),
    next_state_sha256: str = _sha("f"),
) -> ShadowVerification:
    (
        action_id,
        action_sha256,
        _dwr_sha256,
        transition_action_sha256,
        transition_action_file_sha256,
        transition_action_identity_sha256,
        next_mesh_forest_sha256,
        next_degree_map_sha256,
    ) = binding
    previous = before_goals.by_id
    current = after_goals.by_id
    actual = tuple(
        (goal_id, current[goal_id] - previous[goal_id])
        for goal_id in FORMAL_GOAL_IDS
    )
    return ShadowVerification(
        action_id=action_id,
        action_sha256=action_sha256,
        transition_action_sha256=transition_action_sha256,
        transition_action_file_sha256=transition_action_file_sha256,
        transition_action_identity_sha256=(
            transition_action_identity_sha256
        ),
        next_mesh_forest_sha256=next_mesh_forest_sha256,
        next_degree_map_sha256=next_degree_map_sha256,
        next_plan_file_sha256=next_plan_file_sha256,
        next_plan_content_sha256=next_plan_content_sha256,
        next_state_sha256=next_state_sha256,
        before_output_sha256=before_output_sha256,
        after_output_sha256=after_output_sha256,
        predicted_deltas=actual,
        actual_deltas=actual,
    )


def _cycle(
    index: int,
    goals: GoalVector,
    *,
    strength: float,
    final: bool,
    verifications: tuple[ShadowVerification, ...] = (),
    stability_repeat: StabilityRepeatVerification | None = None,
    mesh_forest_character: str = "1",
    solved_state_character: str | None = None,
    plan_file_character: str = "d",
    plan_content_character: str = "e",
    plan_solver_content_character: str = "c",
    state_character: str = "f",
    watchdog_character: str | None = None,
    complete_output_character: str | None = None,
) -> BlindCycleInput:
    snapshot_character = (
        str(3 + index)
        if solved_state_character is None
        else solved_state_character
    )
    record_character = watchdog_character or str((index + 5) % 10)
    output_character = complete_output_character or snapshot_character
    return BlindCycleInput(
        cycle_index=index,
        mesh_forest_sha256=_sha(mesh_forest_character),
        degree_map_sha256=_sha("2"),
        plan_file_sha256=_sha(plan_file_character),
        plan_content_sha256=_sha(plan_content_character),
        plan_solver_content_sha256=_sha(plan_solver_content_character),
        state_sha256=_sha(state_character),
        solution_snapshot_sha256=_sha(snapshot_character),
        watchdog_record_file_sha256=_sha(record_character),
        complete_output_sha256=_sha(output_character),
        full_residual_sha256=_sha("7"),
        adjoint_bundle_sha256=_sha("8"),
        resource_inventory_sha256=_resource_authority_sha256(),
        goals=goals,
        shadows=_catalog(
            goals,
            strength=strength,
            next_mesh_forest_sha256=_sha(mesh_forest_character),
            next_degree_map_sha256=_sha("2"),
            current_plan_file_sha256=_sha(plan_file_character),
            current_mesh_forest_sha256=_sha(mesh_forest_character),
        ),
        inventory=StructuralInventory(
            active_dofs=50_000,
            rows=30_000,
            matrix_nnz=20_000_000,
            factor_nnz=100_000_000,
            solver_peak_bytes=6_000_000_000,
        ),
        gates=_gates(final=final),
        executed_action_verifications=verifications,
        stability_repeat_verification=stability_repeat,
    )


def _stability_repeat(
    previous: BlindCycleResult,
    *,
    next_plan_file_character: str,
    next_plan_content_character: str,
    next_state_character: str,
    next_snapshot_character: str,
    next_watchdog_character: str,
) -> StabilityRepeatVerification:
    return StabilityRepeatVerification(
        action_id=f"cycle{previous.cycle_index + 1}.p-keep.repeat",
        action_kind="p-keep",
        action_sha256=_sha("a"),
        action_file_sha256=_sha("b"),
        action_identity_sha256=_sha("c"),
        from_state_sha256=previous.state_sha256,
        next_state_sha256=_sha(next_state_character),
        previous_plan_file_sha256=previous.plan_file_sha256,
        previous_plan_content_sha256=previous.plan_content_sha256,
        previous_plan_solver_content_sha256=(
            previous.plan_solver_content_sha256
        ),
        next_plan_file_sha256=_sha(next_plan_file_character),
        next_plan_content_sha256=_sha(next_plan_content_character),
        next_plan_solver_content_sha256=(
            previous.plan_solver_content_sha256
        ),
        previous_mesh_forest_sha256=previous.mesh_forest_sha256,
        next_mesh_forest_sha256=previous.mesh_forest_sha256,
        previous_degree_map_sha256=previous.degree_map_sha256,
        next_degree_map_sha256=previous.degree_map_sha256,
        before_solution_snapshot_sha256=(
            previous.solution_snapshot_sha256
        ),
        after_solution_snapshot_sha256=_sha(next_snapshot_character),
        before_watchdog_record_file_sha256=(
            previous.watchdog_record_file_sha256
        ),
        after_watchdog_record_file_sha256=_sha(
            next_watchdog_character
        ),
    )


def test_six_cycle_machine_selects_verifies_and_freezes() -> None:
    trial = BlindTrial(
        trial_id="path-a",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256=_sha("a"),
        physical_identity_sha256=_sha("e"),
    )
    first_goals = _goals()
    trial = advance_blind_trial(
        trial,
        _cycle(0, first_goals, strength=0.6, final=False),
    )
    first = trial.results[-1]
    assert first.status == "accepted_action_selected"
    assert first.selected_action_ids == ("p-0.6",)
    assert (
        "single_lane_policy_without_combined_shadow_selected_p"
        in first.reasons
    )
    assert first.freeze_ready is False

    second_goals = _catalog(first_goals, strength=0.6).p_actions[0].shadow
    second_output = _sha("4")
    trial = advance_blind_trial(
        trial,
        _cycle(
            1,
            second_goals,
            strength=0.1,
            final=True,
            verifications=tuple(
                _verification(
                    binding,
                    before_output_sha256=first.complete_output_sha256,
                    after_output_sha256=second_output,
                    before_goals=first.goals,
                    after_goals=second_goals,
                )
                for binding in first.selected_action_bindings
            ),
        ),
    )
    assert trial.results[-1].stable_streak == 1
    assert trial.results[-1].freeze_ready is False
    second = trial.results[-1]

    third_goals = second_goals
    trial = advance_blind_trial(
        trial,
        _cycle(
            2,
            third_goals,
            strength=0.1,
            final=True,
            solved_state_character="5",
            complete_output_character="4",
            plan_file_character="a",
            plan_content_character="b",
            state_character="c",
            watchdog_character="7",
            stability_repeat=_stability_repeat(
                second,
                next_plan_file_character="a",
                next_plan_content_character="b",
                next_state_character="c",
                next_snapshot_character="5",
                next_watchdog_character="7",
            ),
        ),
    )
    endpoint = trial.results[-1]
    assert endpoint.stable_streak == 2
    assert endpoint.freeze_ready is True

    second_trial = BlindTrial(
        trial_id="path-b",
        algorithm_id=trial.algorithm_id,
        source_sha=trial.source_sha,
        initial_path_id="coarse-b",
        initial_mesh_forest_sha256=_sha("b"),
        physical_identity_sha256=trial.physical_identity_sha256,
    )
    second_trial = advance_blind_trial(
        second_trial,
        _cycle(
            0,
            first_goals,
            strength=0.6,
            final=False,
            mesh_forest_character="b",
        ),
    )
    second_first = second_trial.results[-1]
    second_trial = advance_blind_trial(
        second_trial,
        _cycle(
            1,
            second_goals,
            strength=0.1,
            final=True,
            mesh_forest_character="b",
            verifications=tuple(
                _verification(
                    binding,
                    before_output_sha256=second_first.complete_output_sha256,
                    after_output_sha256=second_output,
                    before_goals=second_first.goals,
                    after_goals=second_goals,
                )
                for binding in second_first.selected_action_bindings
            ),
        ),
    )
    second_path_middle = second_trial.results[-1]
    second_trial = advance_blind_trial(
        second_trial,
        _cycle(
            2,
            third_goals,
            strength=0.1,
            final=True,
            mesh_forest_character="b",
            solved_state_character="5",
            complete_output_character="4",
            plan_file_character="a",
            plan_content_character="b",
            state_character="c",
            watchdog_character="7",
            stability_repeat=_stability_repeat(
                second_path_middle,
                next_plan_file_character="a",
                next_plan_content_character="b",
                next_state_character="c",
                next_snapshot_character="5",
                next_watchdog_character="7",
            ),
        ),
    )
    path_gate = compare_frozen_paths(trial, second_trial)
    assert path_gate["pass"] is True
    frozen = freeze_candidate(
        trial,
        two_path_gate=path_gate,
        physical_identity_sha256=_sha("e"),
        resource_authority=_resource_authority(),
    )
    assert frozen.output_sha256 == _sha("4")
    assert len(frozen.frozen_payload_sha256) == 64
    assert (
        CandidateFreezeReceipt.from_mapping(
            asdict(frozen)
        ).frozen_payload_sha256
        == frozen.frozen_payload_sha256
    )


def test_verification_inventory_and_internal_gate_fail_closed() -> None:
    trial = BlindTrial(
        trial_id="path-b",
        algorithm_id="multilevel-hp-v1",
        source_sha="b" * 40,
        initial_path_id="coarse-b",
        initial_mesh_forest_sha256=_sha("b"),
        physical_identity_sha256=_sha("e"),
    )
    trial = advance_blind_trial(
        trial,
        _cycle(0, _goals(), strength=2.0, final=False),
    )
    failed = advance_blind_trial(
        trial,
        _cycle(
            1,
            _goals(0.1),
            strength=0.1,
            final=True,
            verifications=(),
        ),
    ).results[-1]
    assert failed.accepted_current_state is False
    assert failed.status == "rejected_fail_closed"
    assert "executed_action_verification_inventory_mismatch" in failed.reasons


@pytest.mark.parametrize(
    ("mutator", "mesh_character", "expected_reason"),
    (
        (
            lambda row: replace(
                row,
                transition_action_sha256=_sha("f"),
            ),
            "1",
            "executed_action_verification_binding_failed",
        ),
        (
            lambda row: replace(
                row,
                next_mesh_forest_sha256=_sha("6"),
            ),
            "6",
            "executed_action_next_plan_identity_failed",
        ),
    ),
)
def test_executed_action_requires_selected_transition_and_next_plan_identity(
    mutator: Callable[[ShadowVerification], ShadowVerification],
    mesh_character: str,
    expected_reason: str,
) -> None:
    trial = BlindTrial(
        trial_id="transition-bound",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256=_sha("a"),
        physical_identity_sha256=_sha("e"),
    )
    first_goals = _goals()
    trial = advance_blind_trial(
        trial,
        _cycle(0, first_goals, strength=0.6, final=False),
    )
    first = trial.results[-1]
    next_goals = _catalog(first_goals, strength=0.6).p_actions[0].shadow
    verification = _verification(
        first.selected_action_bindings[0],
        before_output_sha256=first.complete_output_sha256,
        after_output_sha256=_sha("4"),
        before_goals=first.goals,
        after_goals=next_goals,
    )
    tampered = mutator(verification)
    result = advance_blind_trial(
        trial,
        _cycle(
            1,
            next_goals,
            strength=0.1,
            final=True,
            verifications=(tampered,),
            mesh_forest_character=mesh_character,
        ),
    ).results[-1]

    assert result.accepted_current_state is False
    assert result.freeze_ready is False
    assert expected_reason in result.reasons


def test_two_start_rejects_reused_cycle_chain() -> None:
    trial = BlindTrial(
        trial_id="path-a",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256=_sha("a"),
        physical_identity_sha256=_sha("e"),
    )
    first_goals = _goals()
    trial = advance_blind_trial(
        trial,
        _cycle(0, first_goals, strength=0.1, final=True),
    )
    first = trial.results[-1]
    trial = advance_blind_trial(
        trial,
        _cycle(
            1,
            first_goals,
            strength=0.1,
            final=True,
            solved_state_character="4",
            plan_file_character="a",
            plan_content_character="b",
            state_character="c",
            watchdog_character="6",
            stability_repeat=_stability_repeat(
                first,
                next_plan_file_character="a",
                next_plan_content_character="b",
                next_state_character="c",
                next_snapshot_character="4",
                next_watchdog_character="6",
            ),
        ),
    )
    middle = trial.results[-1]
    trial = advance_blind_trial(
        trial,
        _cycle(
            2,
            first_goals,
            strength=0.1,
            final=True,
            solved_state_character="5",
            plan_file_character="4",
            plan_content_character="5",
            state_character="6",
            watchdog_character="7",
            stability_repeat=_stability_repeat(
                middle,
                next_plan_file_character="4",
                next_plan_content_character="5",
                next_state_character="6",
                next_snapshot_character="5",
                next_watchdog_character="7",
            ),
        ),
    )
    copied = BlindTrial(
        trial_id="path-b",
        algorithm_id=trial.algorithm_id,
        source_sha=trial.source_sha,
        initial_path_id="coarse-b",
        initial_mesh_forest_sha256=_sha("b"),
        physical_identity_sha256=trial.physical_identity_sha256,
        results=trial.results,
    )
    with pytest.raises(ValueError, match="reused one cycle evidence chain"):
        compare_frozen_paths(trial, copied)


def test_internal_gate_types_and_shadow_lanes_fail_closed() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        InternalGates(
            full_explicit_residual=-1.0,
            energy_closure_error=0.0,
            absorption_volume=0.0,
            floquet_residual_pass=True,
            hanging_residual_pass=True,
            serial_mpi_identity_pass=True,
            multilevel_mesh_pass=True,
            separated_patch_count=2,
            all_local_levels_present=True,
            algebraic_budget_fraction=0.0,
            dtn_budget_fraction=0.0,
            postprocess_budget_fraction=0.0,
        )
    goals = _goals()
    keep = _action(
        action_id="p-keep-only",
        kind="keep",
        target="cell:0",
        current=goals,
        strength=0.0,
    )
    h_refine = _action(
        action_id="h-real",
        kind="h-refine",
        target="root:0",
        current=goals,
        strength=0.1,
    )
    with pytest.raises(ValueError, match="real p-up"):
        ShadowCatalog(
            current_goal_sha256=goals.sha256,
            p_actions=(keep,),
            h_actions=(h_refine,),
            p6_saturation=_p6_saturation(),
            h_level3_saturation=_h_saturation(),
        )


def test_first_two_cycles_do_not_select_down_actions() -> None:
    goals = _goals()
    down = _action(
        action_id="p-down-0",
        kind="p-down",
        target="cell:4",
        current=goals,
        strength=2.0,
    )
    keep = _action(
        action_id="h-keep-0",
        kind="keep",
        target="root:0",
        current=goals,
        strength=0.1,
    )
    p_up = _action(
        action_id="p-up-weak",
        kind="p-up",
        target="cell:5",
        current=goals,
        strength=0.1,
    )
    h_refine = _action(
        action_id="h-refine-weak",
        kind="h-refine",
        target="root:5",
        current=goals,
        strength=0.1,
    )
    cycle = BlindCycleInput(
        cycle_index=0,
        mesh_forest_sha256=_sha("1"),
        degree_map_sha256=_sha("2"),
        plan_file_sha256=_sha("7"),
        plan_content_sha256=_sha("8"),
        plan_solver_content_sha256=_sha("a"),
        state_sha256=_sha("9"),
        solution_snapshot_sha256=_sha("3"),
        watchdog_record_file_sha256=_sha("b"),
        complete_output_sha256=_sha("3"),
        full_residual_sha256=_sha("4"),
        adjoint_bundle_sha256=_sha("5"),
        resource_inventory_sha256=_sha("6"),
        goals=goals,
        shadows=ShadowCatalog(
            current_goal_sha256=goals.sha256,
            p_actions=(p_up, down),
            h_actions=(h_refine, keep),
            p6_saturation=_p6_saturation(
                plan_file_sha256=_sha("7"),
            ),
            h_level3_saturation=_h_saturation(
                plan_file_sha256=_sha("7"),
            ),
        ),
        inventory=StructuralInventory(40_000, 20_000, 100, 100, 100),
        gates=_gates(final=False),
    )
    trial = advance_blind_trial(
        BlindTrial(
            trial_id="down-check",
            algorithm_id="multilevel-hp-v1",
            source_sha="c" * 40,
            initial_path_id="coarse-a",
            initial_mesh_forest_sha256=_sha("a"),
            physical_identity_sha256=_sha("e"),
        ),
        cycle,
    )

    assert trial.results[-1].selected_action_ids == ()
    assert "both_shadow_lanes_inside_freeze_threshold" in (
        trial.results[-1].reasons
    )


def test_real_controller_sources_and_manifest_pass_isolation_checker() -> None:
    package = (
        Path(__file__).resolve().parents[1]
        / "adaptivity"
        / "blind_controller"
    )
    source_root = Path(__file__).resolve().parents[2]
    static = scan_blind_controller(package, source_root=source_root)
    manifest = build_cycle_manifest(
        trial_id="path-a",
        algorithm_id="multilevel-hp-v1",
        source_sha="d" * 40,
        initial_path_id="coarse-a",
        maximum_cycles=6,
        cycle_index=0,
        state="initialized",
        mesh_forest_sha256=_sha("1"),
        degree_map_sha256=_sha("2"),
        solution_snapshot_sha256=_sha("3"),
        goal_inventory_sha256=_sha("4"),
        full_residual_sha256=_sha("5"),
        adjoint_bundle_sha256=_sha("6"),
        p_shadow_bundle_sha256=None,
        h_shadow_bundle_sha256=None,
        resource_inventory_sha256=_sha("7"),
    )

    assert static["pass"] is True, static["findings"]
    assert validate_blind_input_manifest(manifest)["pass"] is True


@pytest.mark.parametrize(
    "missing_goal",
    (
        "scalar/R_total",
        "scalar/interface_probe_l2",
        "complex/volume_probe_complex/imag",
    ),
)
def test_formal_goal_vector_rejects_missing_total_or_field(
    missing_goal: str,
) -> None:
    assert len(FIXED_GOAL_IDS) == 48
    assert len(FORMAL_GOAL_IDS) > len(FIXED_GOAL_IDS)
    incomplete = dict(_goals().by_id)
    incomplete.pop(missing_goal)

    with pytest.raises(ValueError, match="complete formal inventory"):
        GoalVector.from_mapping(incomplete)


def test_complex_amplitude_components_share_magnitude_tolerance() -> None:
    current = dict(_goals().by_id)
    shadow = dict(current)
    real_id = "top:m0:n0:co_amp_real"
    imag_id = "top:m0:n0:co_amp_imag"
    current[real_id] = 100.0
    shadow[real_id] = 100.0
    current[imag_id] = 0.0
    shadow[imag_id] = 0.05
    left = GoalVector.from_mapping(current)
    right = GoalVector.from_mapping(shadow)

    real_tolerance = blind_tolerance(real_id, left.by_id, right.by_id)
    imag_tolerance = blind_tolerance(imag_id, left.by_id, right.by_id)
    distances = normalized_goal_distance(left, right)

    assert real_tolerance == pytest.approx(0.1)
    assert imag_tolerance == pytest.approx(real_tolerance)
    assert distances[imag_id] == pytest.approx(0.5)


def test_internal_certificate_binds_complete_formal_inventory() -> None:
    trial = advance_blind_trial(
        BlindTrial(
            trial_id="formal-inventory",
            algorithm_id="multilevel-hp-v1",
            source_sha="f" * 40,
            initial_path_id="coarse-a",
            initial_mesh_forest_sha256=_sha("a"),
            physical_identity_sha256=_sha("e"),
        ),
        _cycle(0, _goals(), strength=0.1, final=False),
    )
    certificate = trial.results[-1].internal_certificate

    assert certificate["formal_goal_count"] == len(FORMAL_GOAL_IDS)
    assert len(certificate["formal_goal_inventory_sha256"]) == 64
