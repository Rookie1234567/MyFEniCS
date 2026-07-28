from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    GoalVector,
    InternalGates,
    ShadowCatalog,
    ShadowCost,
    ShadowVerification,
    StabilityRepeatVerification,
    advance_blind_trial,
    build_measured_h_level3_saturation_authority,
    build_shadow_action,
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    h_level3_saturation_authority_from_payload,
    h_level3_saturation_authority_payload,
    p6_saturation_authority_from_payload,
    p6_saturation_authority_payload,
)
from src.adaptivity.blind_controller.state_machine import (
    BlindCycleInput,
    BlindCycleResult,
    BlindTrial,
    StructuralInventory,
)


def _sha(character: str) -> str:
    return character * 64


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _p6_saturation(
    *,
    plan_file_sha256: str = _sha("8"),
    mesh_forest_sha256: str = _sha("1"),
    degree_map_sha256: str = _sha("2"),
    p6_target_ids: tuple[str, ...] = (),
) -> object:
    return build_unmeasured_p6_saturation_authority(
        p6_target_ids=p6_target_ids,
        current_plan_file_sha256=plan_file_sha256,
        current_mesh_forest_sha256=mesh_forest_sha256,
        current_degree_map_sha256=degree_map_sha256,
    )


def _h_saturation(
    *,
    plan_file_sha256: str = _sha("8"),
    mesh_forest_sha256: str = _sha("1"),
    degree_map_sha256: str = _sha("2"),
    level_two_target_ids: tuple[str, ...] = (),
    periodic_orbit_ids: tuple[str, ...] = (),
    orbit_catalog_sha256: str = _sha("e"),
) -> object:
    return build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=level_two_target_ids,
        periodic_orbit_ids=periodic_orbit_ids,
        orbit_catalog_sha256=orbit_catalog_sha256,
        current_plan_file_sha256=plan_file_sha256,
        current_mesh_forest_sha256=mesh_forest_sha256,
        current_degree_map_sha256=degree_map_sha256,
    )


def _measured_h_saturation(*, normalized_max: float) -> object:
    targets = ["cell:r0:l2:i0:j0:k0"]
    orbits = ["h3-orbit-000000-abc123"]
    status = "measured_pass" if normalized_max <= 0.5 else "measured_fail"
    coverage = {
        "schema_version": "task035e.level3-h-saturation-coverage.v1",
        "status": f"level3_h_saturation_{status}",
        "formal_h_saturation_status": status,
        "measured_pass": status == "measured_pass",
        "measured_fail": status == "measured_fail",
        "freezing_credit": False,
        "controller_consumption_eligible": True,
        "state_sha256": _sha("f"),
        "catalog_sha256": _sha("d"),
        "orbit_catalog_sha256": _sha("e"),
        "level_two_target_ids": targets,
        "level_two_target_ids_sha256": _canonical_sha(
            {"canonical_target_ids": targets}
        ),
        "expected_orbit_ids": orbits,
        "expected_orbit_ids_sha256": _canonical_sha(
            {"canonical_orbit_ids": orbits}
        ),
        "covered_target_ids": targets,
        "covered_target_ids_sha256": _canonical_sha(
            {"canonical_target_ids": targets}
        ),
        "covered_orbit_ids": orbits,
        "covered_orbit_ids_sha256": _canonical_sha(
            {"canonical_orbit_ids": orbits}
        ),
        "expected_orbit_count": 1,
        "observed_orbit_count": 1,
        "missing_orbit_ids": [],
        "all_level_two_orbits_covered": True,
        "all_orbit_evidence_formally_complete": True,
        "saturation_normalized_limit": 0.5,
        "normalized_max": normalized_max,
        "orbit_evidence_sha256s": {orbits[0]: _sha("c")},
        "failing_goal_count": int(status == "measured_fail"),
        "failing_rows": [],
        "production_plan_mutated": False,
        "production_level_three_selectable": False,
        "production_level_three_rows_numbered": False,
        "classification_note": "test fixture",
    }
    coverage["coverage_sha256"] = _canonical_sha(coverage)
    return build_measured_h_level3_saturation_authority(
        coverage_payload=coverage,
        independent_measured_evidence_sha256=coverage["coverage_sha256"],
        current_plan_file_sha256=_sha("8"),
        current_mesh_forest_sha256=_sha("1"),
        current_degree_map_sha256=_sha("2"),
    )


def _goals(value: float = 1.0) -> GoalVector:
    return GoalVector.from_mapping(
        {goal_id: value for goal_id in FORMAL_GOAL_IDS}
    )


def _action(
    *,
    action_id: str,
    kind: str,
    current: GoalVector,
    endpoint_delta: float,
    dwr_delta: float,
    cost_scale: int = 1,
) -> object:
    shadow = GoalVector.from_mapping(
        {
            goal_id: current.by_id[goal_id] + endpoint_delta
            for goal_id in FORMAL_GOAL_IDS
        }
    )
    sign_consistent = endpoint_delta * dwr_delta >= 0.0
    return build_shadow_action(
        action_id=action_id,
        kind=kind,
        target_ids=(
            "cell:1" if kind == "p-up" else "root:9",
        ),
        current=current,
        shadow=shadow,
        signed_dwr_delta={
            goal_id: dwr_delta for goal_id in FORMAL_GOAL_IDS
        },
        cost=ShadowCost(
            10 * cost_scale,
            5 * cost_scale,
            100 * cost_scale,
            200 * cost_scale,
            1024 * cost_scale,
        ),
        sign_consistent=sign_consistent,
        transition_action_sha256=_sha("8"),
        transition_action_file_sha256=_sha("9"),
        transition_action_identity_sha256=_sha("a"),
        next_mesh_forest_sha256=_sha("1"),
        next_degree_map_sha256=_sha("2"),
        actual_added_leaf_count=7 if kind == "h-refine" else 0,
    )


def _cycle(
    catalog: ShadowCatalog,
    *,
    cycle_index: int = 0,
    mesh_forest_sha256: str | None = None,
    degree_map_sha256: str | None = None,
    plan_file_sha256: str | None = None,
    plan_content_sha256: str | None = None,
    plan_solver_content_sha256: str | None = None,
    state_sha256: str | None = None,
    solution_snapshot_sha256: str | None = None,
    watchdog_record_file_sha256: str | None = None,
    complete_output_sha256: str | None = None,
    goals: GoalVector | None = None,
    verifications: tuple[ShadowVerification, ...] = (),
    stability_repeat: StabilityRepeatVerification | None = None,
) -> BlindCycleInput:
    current_goals = goals or _goals()
    current_mesh_sha = mesh_forest_sha256 or _sha("1")
    current_degree_sha = degree_map_sha256 or _sha("2")
    current_plan_sha = plan_file_sha256 or _sha("8")
    current_h_saturation = catalog.h_level3_saturation
    if (
        current_h_saturation.current_plan_file_sha256
        == current_plan_sha
        and current_h_saturation.current_mesh_forest_sha256
        == current_mesh_sha
        and current_h_saturation.current_degree_map_sha256
        == current_degree_sha
    ):
        rebound_h_saturation = current_h_saturation
    else:
        rebound_h_saturation = _h_saturation(
            plan_file_sha256=current_plan_sha,
            mesh_forest_sha256=current_mesh_sha,
            degree_map_sha256=current_degree_sha,
            level_two_target_ids=(
                current_h_saturation.level_two_target_ids
            ),
            periodic_orbit_ids=(
                current_h_saturation.periodic_orbit_ids
            ),
            orbit_catalog_sha256=(
                current_h_saturation.orbit_catalog_sha256
            ),
        )
    catalog = replace(
        catalog,
        p6_saturation=_p6_saturation(
            plan_file_sha256=current_plan_sha,
            mesh_forest_sha256=current_mesh_sha,
            degree_map_sha256=current_degree_sha,
            p6_target_ids=catalog.p6_saturation.p6_target_ids,
        ),
        h_level3_saturation=rebound_h_saturation,
    )
    return BlindCycleInput(
        cycle_index=cycle_index,
        mesh_forest_sha256=current_mesh_sha,
        degree_map_sha256=current_degree_sha,
        plan_file_sha256=current_plan_sha,
        plan_content_sha256=plan_content_sha256 or _sha("9"),
        plan_solver_content_sha256=(
            plan_solver_content_sha256 or _sha("b")
        ),
        state_sha256=state_sha256 or _sha("a"),
        solution_snapshot_sha256=solution_snapshot_sha256 or _sha("3"),
        watchdog_record_file_sha256=(
            watchdog_record_file_sha256 or _sha("c")
        ),
        complete_output_sha256=complete_output_sha256 or _sha("4"),
        full_residual_sha256=_sha("5"),
        adjoint_bundle_sha256=_sha("6"),
        resource_inventory_sha256=_sha("7"),
        goals=current_goals,
        shadows=catalog,
        inventory=StructuralInventory(
            active_dofs=10_000,
            rows=10_000,
            matrix_nnz=1_000_000,
            factor_nnz=10_000_000,
            solver_peak_bytes=1024**3,
        ),
        gates=InternalGates(
            full_explicit_residual=1.0e-12,
            energy_closure_error=1.0e-12,
            absorption_volume=0.25,
            floquet_residual_pass=True,
            hanging_residual_pass=True,
            serial_mpi_identity_pass=True,
            multilevel_mesh_pass=True,
            separated_patch_count=2,
            all_local_levels_present=True,
            algebraic_budget_fraction=0.05,
            dtn_budget_fraction=0.05,
            postprocess_budget_fraction=0.05,
        ),
        executed_action_verifications=verifications,
        stability_repeat_verification=stability_repeat,
    )


def _stability_repeat(
    previous: BlindCycleResult,
    *,
    plan_file_sha256: str,
    plan_content_sha256: str,
    state_sha256: str,
    snapshot_sha256: str,
    watchdog_sha256: str,
) -> StabilityRepeatVerification:
    return StabilityRepeatVerification(
        action_id="cycle1.p-keep.stability-repeat",
        action_kind="p-keep",
        action_sha256=_sha("d"),
        action_file_sha256=_sha("e"),
        action_identity_sha256=_sha("f"),
        from_state_sha256=previous.state_sha256,
        next_state_sha256=state_sha256,
        previous_plan_file_sha256=previous.plan_file_sha256,
        previous_plan_content_sha256=previous.plan_content_sha256,
        previous_plan_solver_content_sha256=(
            previous.plan_solver_content_sha256
        ),
        next_plan_file_sha256=plan_file_sha256,
        next_plan_content_sha256=plan_content_sha256,
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
        after_solution_snapshot_sha256=snapshot_sha256,
        before_watchdog_record_file_sha256=(
            previous.watchdog_record_file_sha256
        ),
        after_watchdog_record_file_sha256=watchdog_sha256,
    )


def _advance(catalog: ShadowCatalog) -> object:
    return advance_blind_trial(
        BlindTrial(
            trial_id="failclosed",
            algorithm_id="multilevel-hp-v1",
            source_sha="a" * 40,
            initial_path_id="coarse-a",
            initial_mesh_forest_sha256=_sha("a"),
            physical_identity_sha256=_sha("b"),
        ),
        _cycle(catalog),
    ).results[-1]


def test_zero_dwr_large_solved_endpoint_is_not_neutral_or_freezeable() -> None:
    current = _goals()
    p_action = _action(
        action_id="p-zero-dwr-large-endpoint",
        kind="p-up",
        current=current,
        endpoint_delta=1.0e-3,
        dwr_delta=0.0,
    )
    h_action = _action(
        action_id="h-neutral",
        kind="h-refine",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(p_action,),
        h_actions=(h_action,),
        p6_saturation=_p6_saturation(),
        h_level3_saturation=_h_saturation(),
    )

    assert p_action.maximum_normalized_signed_dwr_delta == 0.0
    assert p_action.maximum_normalized_endpoint_delta > 0.5
    assert catalog.maximum_normalized_signed_dwr_delta("p") == 0.0
    assert catalog.maximum_normalized_endpoint_delta("p") > 0.5

    result = _advance(catalog)
    assert result.freeze_ready is False
    assert result.selected_action_ids == (p_action.action_id,)
    assert result.p_shadow_signed_dwr_maximum == 0.0
    assert result.p_shadow_endpoint_maximum == pytest.approx(
        p_action.maximum_normalized_endpoint_delta
    )
    assert result.p_shadow_maximum == pytest.approx(
        p_action.maximum_normalized_endpoint_delta
    )


def test_any_dwr_endpoint_sign_conflict_rejects_cycle_fail_closed() -> None:
    current = _goals()
    conflicting = _action(
        action_id="p-sign-conflict",
        kind="p-up",
        current=current,
        endpoint_delta=-1.0e-3,
        dwr_delta=1.0e-3,
    )
    neutral = _action(
        action_id="h-neutral",
        kind="h-refine",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    result = _advance(
        ShadowCatalog(
            current_goal_sha256=current.sha256,
            p_actions=(conflicting,),
            h_actions=(neutral,),
            p6_saturation=_p6_saturation(),
            h_level3_saturation=_h_saturation(),
        )
    )

    assert result.accepted_current_state is False
    assert result.status == "rejected_fail_closed"
    assert result.selected_action_ids == ()
    assert result.freeze_ready is False
    assert "shadow_dwr_endpoint_sign_conflict" in result.reasons
    assert "rejected_shadow_action:p-sign-conflict" in result.reasons


def test_independent_p_and_h_shadows_select_exactly_one_ranked_lane() -> None:
    current = _goals()
    p_action = _action(
        action_id="p-preferred",
        kind="p-up",
        current=current,
        endpoint_delta=1.0e-3,
        dwr_delta=1.0e-3,
        cost_scale=1,
    )
    h_action = _action(
        action_id="h-more-expensive",
        kind="h-refine",
        current=current,
        endpoint_delta=1.0e-3,
        dwr_delta=1.0e-3,
        cost_scale=2,
    )
    result = _advance(
        ShadowCatalog(
            current_goal_sha256=current.sha256,
            p_actions=(p_action,),
            h_actions=(h_action,),
            p6_saturation=_p6_saturation(),
            h_level3_saturation=_h_saturation(),
        )
    )

    assert result.selected_action_ids == ("p-preferred",)
    assert (
        "single_lane_policy_without_combined_shadow_selected_p"
        in result.reasons
    )


def test_no_action_transition_requires_fresh_pkeep_stability_repeat() -> None:
    current = _goals()
    p_neutral = _action(
        action_id="p-neutral",
        kind="p-up",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    h_neutral = _action(
        action_id="h-neutral",
        kind="h-refine",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(p_neutral,),
        h_actions=(h_neutral,),
        p6_saturation=_p6_saturation(),
        h_level3_saturation=_h_saturation(),
    )
    initial = BlindTrial(
        trial_id="failclosed",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256=_sha("a"),
        physical_identity_sha256=_sha("b"),
    )
    after_first = advance_blind_trial(initial, _cycle(catalog))
    assert after_first.results[-1].status == "accepted_no_safe_action"
    assert after_first.results[-1].selected_action_bindings == ()
    previous = after_first.results[-1]

    missing = advance_blind_trial(
        after_first,
        _cycle(catalog, cycle_index=1),
    )
    assert missing.results[-1].accepted_current_state is False
    assert "stability_repeat_verification_missing" in missing.results[-1].reasons

    plan_file_sha = _sha("d")
    plan_content_sha = _sha("e")
    state_sha = _sha("f")
    snapshot_sha = _sha("6")
    watchdog_sha = _sha("7")
    repeat = _stability_repeat(
        previous,
        plan_file_sha256=plan_file_sha,
        plan_content_sha256=plan_content_sha,
        state_sha256=state_sha,
        snapshot_sha256=snapshot_sha,
        watchdog_sha256=watchdog_sha,
    )
    repeated = advance_blind_trial(
        after_first,
        _cycle(
            catalog,
            cycle_index=1,
            plan_file_sha256=plan_file_sha,
            plan_content_sha256=plan_content_sha,
            state_sha256=state_sha,
            solution_snapshot_sha256=snapshot_sha,
            watchdog_record_file_sha256=watchdog_sha,
            complete_output_sha256=previous.complete_output_sha256,
            stability_repeat=repeat,
        ),
    )
    assert repeated.results[-1].accepted_current_state is True
    assert repeated.results[-1].stable_streak == 1
    assert repeated.results[-1].complete_output_sha256 == (
        previous.complete_output_sha256
    )


def test_stability_repeat_rejects_solver_drift_and_reused_execution_files() -> None:
    current = _goals()
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(
            _action(
                action_id="p-neutral",
                kind="p-up",
                current=current,
                endpoint_delta=0.0,
                dwr_delta=0.0,
            ),
        ),
        h_actions=(
            _action(
                action_id="h-neutral",
                kind="h-refine",
                current=current,
                endpoint_delta=0.0,
                dwr_delta=0.0,
            ),
        ),
        p6_saturation=_p6_saturation(),
        h_level3_saturation=_h_saturation(),
    )
    previous = advance_blind_trial(
        BlindTrial(
            trial_id="repeat-validation",
            algorithm_id="multilevel-hp-v1",
            source_sha="a" * 40,
            initial_path_id="coarse-a",
            initial_mesh_forest_sha256=_sha("a"),
            physical_identity_sha256=_sha("b"),
        ),
        _cycle(catalog),
    ).results[-1]
    repeat = _stability_repeat(
        previous,
        plan_file_sha256=_sha("d"),
        plan_content_sha256=_sha("e"),
        state_sha256=_sha("f"),
        snapshot_sha256=_sha("6"),
        watchdog_sha256=_sha("7"),
    )

    with pytest.raises(ValueError, match="canonical solver content"):
        replace(repeat, next_plan_solver_content_sha256=_sha("9"))
    with pytest.raises(ValueError, match="reused an immutable"):
        replace(
            repeat,
            after_solution_snapshot_sha256=(
                repeat.before_solution_snapshot_sha256
            ),
        )
    with pytest.raises(ValueError, match="reused an immutable"):
        replace(
            repeat,
            after_watchdog_record_file_sha256=(
                repeat.before_watchdog_record_file_sha256
            ),
        )


def test_selected_action_cannot_be_relabelled_as_stability_repeat() -> None:
    current = _goals()
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(
            _action(
                action_id="p-selected",
                kind="p-up",
                current=current,
                endpoint_delta=1.0e-3,
                dwr_delta=1.0e-3,
            ),
        ),
        h_actions=(
            _action(
                action_id="h-costly",
                kind="h-refine",
                current=current,
                endpoint_delta=1.0e-3,
                dwr_delta=1.0e-3,
                cost_scale=2,
            ),
        ),
        p6_saturation=_p6_saturation(),
        h_level3_saturation=_h_saturation(),
    )
    trial = advance_blind_trial(
        BlindTrial(
            trial_id="repeat-role-mix",
            algorithm_id="multilevel-hp-v1",
            source_sha="a" * 40,
            initial_path_id="coarse-a",
            initial_mesh_forest_sha256=_sha("a"),
            physical_identity_sha256=_sha("b"),
        ),
        _cycle(catalog),
    )
    previous = trial.results[-1]
    repeat = _stability_repeat(
        previous,
        plan_file_sha256=_sha("d"),
        plan_content_sha256=_sha("e"),
        state_sha256=_sha("f"),
        snapshot_sha256=_sha("6"),
        watchdog_sha256=_sha("7"),
    )
    rejected = advance_blind_trial(
        trial,
        _cycle(
            catalog,
            cycle_index=1,
            plan_file_sha256=_sha("d"),
            plan_content_sha256=_sha("e"),
            state_sha256=_sha("f"),
            solution_snapshot_sha256=_sha("6"),
            watchdog_record_file_sha256=_sha("7"),
            stability_repeat=repeat,
        ),
    ).results[-1]

    assert rejected.accepted_current_state is False
    assert (
        "selected_action_cannot_use_stability_repeat_verification"
        in rejected.reasons
    )


def test_selected_action_verification_binds_next_plan_content_and_state() -> None:
    current = _goals()
    p_selected = _action(
        action_id="p-selected",
        kind="p-up",
        current=current,
        endpoint_delta=1.0e-3,
        dwr_delta=1.0e-3,
    )
    h_costly = _action(
        action_id="h-costly",
        kind="h-refine",
        current=current,
        endpoint_delta=1.0e-3,
        dwr_delta=1.0e-3,
        cost_scale=2,
    )
    initial = BlindTrial(
        trial_id="selected-plan-binding",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256=_sha("a"),
        physical_identity_sha256=_sha("b"),
    )
    after_first = advance_blind_trial(
        initial,
        _cycle(
            ShadowCatalog(
                current_goal_sha256=current.sha256,
                p_actions=(p_selected,),
                h_actions=(h_costly,),
                p6_saturation=_p6_saturation(),
                h_level3_saturation=_h_saturation(),
            )
        ),
    )
    assert after_first.results[-1].selected_action_ids == ("p-selected",)

    next_goals = _goals(1.001)
    next_p = _action(
        action_id="p-neutral-next",
        kind="p-up",
        current=next_goals,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    next_h = _action(
        action_id="h-neutral-next",
        kind="h-refine",
        current=next_goals,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    next_catalog = ShadowCatalog(
        current_goal_sha256=next_goals.sha256,
        p_actions=(next_p,),
        h_actions=(next_h,),
        p6_saturation=_p6_saturation(),
        h_level3_saturation=_h_saturation(),
    )
    actual_deltas = tuple(
        (
            goal_id,
            next_goals.by_id[goal_id] - current.by_id[goal_id],
        )
        for goal_id in FORMAL_GOAL_IDS
    )

    def verification(plan_file_sha256: str) -> ShadowVerification:
        return ShadowVerification(
            action_id=p_selected.action_id,
            action_sha256=p_selected.action_sha256,
            transition_action_sha256=(
                p_selected.transition_action_sha256
            ),
            transition_action_file_sha256=(
                p_selected.transition_action_file_sha256
            ),
            transition_action_identity_sha256=(
                p_selected.transition_action_identity_sha256
            ),
            next_mesh_forest_sha256=p_selected.next_mesh_forest_sha256,
            next_degree_map_sha256=p_selected.next_degree_map_sha256,
            next_plan_file_sha256=plan_file_sha256,
            next_plan_content_sha256=_sha("c"),
            next_state_sha256=_sha("d"),
            before_output_sha256=_sha("4"),
            after_output_sha256=_sha("e"),
            predicted_deltas=p_selected.signed_dwr_delta,
            actual_deltas=actual_deltas,
        )

    accepted = advance_blind_trial(
        after_first,
        _cycle(
            next_catalog,
            cycle_index=1,
            plan_file_sha256=_sha("b"),
            plan_content_sha256=_sha("c"),
            state_sha256=_sha("d"),
            complete_output_sha256=_sha("e"),
            goals=next_goals,
            verifications=(verification(_sha("b")),),
        ),
    )
    assert accepted.results[-1].accepted_current_state is True

    rejected = advance_blind_trial(
        after_first,
        _cycle(
            next_catalog,
            cycle_index=1,
            plan_file_sha256=_sha("b"),
            plan_content_sha256=_sha("c"),
            state_sha256=_sha("d"),
            complete_output_sha256=_sha("e"),
            goals=next_goals,
            verifications=(verification(_sha("f")),),
        ),
    )
    assert rejected.results[-1].accepted_current_state is False
    assert (
        "executed_action_verification_binding_failed"
        in rejected.results[-1].reasons
    )


def test_mixed_p5_p6_unmeasured_saturation_blocks_freeze() -> None:
    current = _goals()
    p_neutral = _action(
        action_id="p-neutral-mixed",
        kind="p-up",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    h_neutral = _action(
        action_id="h-neutral-mixed",
        kind="h-refine",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    p6_targets = ("cell:r0:l0:i0:j0:k0",)
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(p_neutral,),
        h_actions=(h_neutral,),
        p6_saturation=_p6_saturation(
            p6_target_ids=p6_targets,
        ),
        h_level3_saturation=_h_saturation(),
    )
    trial = BlindTrial(
        trial_id="p6-saturation-fail-closed",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256=_sha("a"),
        physical_identity_sha256=_sha("b"),
    )
    trial = advance_blind_trial(trial, _cycle(catalog))
    first = trial.results[-1]
    assert first.status == "accepted_no_safe_action"
    assert first.p6_saturation.status == "unknown"
    assert first.p6_saturation.p6_target_ids == p6_targets
    assert "p6_saturation_unmeasured" in first.reasons
    assert "both_shadow_lanes_inside_freeze_threshold" not in first.reasons

    first_repeat = _stability_repeat(
        first,
        plan_file_sha256=_sha("d"),
        plan_content_sha256=_sha("e"),
        state_sha256=_sha("f"),
        snapshot_sha256=_sha("6"),
        watchdog_sha256=_sha("7"),
    )
    trial = advance_blind_trial(
        trial,
        _cycle(
            catalog,
            cycle_index=1,
            plan_file_sha256=_sha("d"),
            plan_content_sha256=_sha("e"),
            state_sha256=_sha("f"),
            solution_snapshot_sha256=_sha("6"),
            watchdog_record_file_sha256=_sha("7"),
            complete_output_sha256=first.complete_output_sha256,
            stability_repeat=first_repeat,
        ),
    )
    second = trial.results[-1]
    second_repeat = _stability_repeat(
        second,
        plan_file_sha256=_sha("1"),
        plan_content_sha256=_sha("2"),
        state_sha256=_sha("3"),
        snapshot_sha256=_sha("8"),
        watchdog_sha256=_sha("9"),
    )
    trial = advance_blind_trial(
        trial,
        _cycle(
            catalog,
            cycle_index=2,
            plan_file_sha256=_sha("1"),
            plan_content_sha256=_sha("2"),
            state_sha256=_sha("3"),
            solution_snapshot_sha256=_sha("8"),
            watchdog_record_file_sha256=_sha("9"),
            complete_output_sha256=first.complete_output_sha256,
            stability_repeat=second_repeat,
        ),
    )
    endpoint = trial.results[-1]
    assert endpoint.stable_streak == 2
    assert endpoint.status == "accepted_no_safe_action"
    assert endpoint.freeze_ready is False
    assert endpoint.internal_certificate["p6_saturation"]["status"] == (
        "unknown"
    )


def test_zero_p6_targets_are_vacuous_and_count_hash_tampering_fails() -> None:
    authority = _p6_saturation()
    assert authority.status == "measured_pass"
    assert authority.p6_target_count == 0
    assert authority.coverage_complete is True
    assert authority.freeze_passed is True

    payload = p6_saturation_authority_payload(authority)
    tampered_count = dict(payload)
    tampered_count["p6_target_count"] = 1
    with pytest.raises(ValueError, match="target count"):
        p6_saturation_authority_from_payload(tampered_count)

    tampered_hash = dict(payload)
    tampered_hash["p6_target_ids_sha256"] = _sha("f")
    with pytest.raises(ValueError, match="target inventory SHA"):
        p6_saturation_authority_from_payload(tampered_hash)


def test_measured_p6_loader_requires_independent_evidence_artifact() -> None:
    target_ids = ["cell:r0:l0:i0:j0:k0"]
    unknown = _p6_saturation(p6_target_ids=tuple(target_ids))
    payload = p6_saturation_authority_payload(unknown)
    target_sha = _canonical_sha({"canonical_target_ids": target_ids})
    payload.update(
        {
            "status": "measured_pass",
            "covered_target_count": 1,
            "covered_target_ids": target_ids,
            "covered_target_ids_sha256": target_sha,
            "coverage_complete": True,
            "normalized_max": 0.25,
            "evidence_kind": "independent_p7_shadow",
            "evidence_sha256": _sha("e"),
        }
    )
    unsigned = dict(payload)
    unsigned.pop("authority_sha256")
    payload["authority_sha256"] = _canonical_sha(unsigned)

    with pytest.raises(ValueError, match="independently loaded"):
        p6_saturation_authority_from_payload(payload)
    loaded = p6_saturation_authority_from_payload(
        payload,
        independent_measured_evidence_sha256=_sha("e"),
    )
    assert loaded.status == "measured_pass"
    assert loaded.freeze_passed is True


def test_level3_h_saturation_is_vacuous_unknown_or_independently_measured() -> None:
    vacuous = _h_saturation()
    assert vacuous.status == "measured_pass"
    assert vacuous.level_two_target_count == 0
    assert vacuous.periodic_orbit_count == 0
    assert vacuous.freeze_passed is True

    unknown = _h_saturation(
        level_two_target_ids=("cell:r0:l2:i0:j0:k0",),
        periodic_orbit_ids=("h3-orbit-000000-abc123",),
    )
    assert unknown.status == "unknown"
    assert unknown.coverage_complete is False
    assert unknown.normalized_max is None
    assert unknown.freeze_passed is False

    measured_pass = _measured_h_saturation(normalized_max=0.5)
    measured_fail = _measured_h_saturation(normalized_max=0.500001)
    assert measured_pass.status == "measured_pass"
    assert measured_pass.freeze_passed is True
    assert measured_fail.status == "measured_fail"
    assert measured_fail.freeze_passed is False

    payload = h_level3_saturation_authority_payload(measured_pass)
    with pytest.raises(ValueError, match="independently loaded"):
        h_level3_saturation_authority_from_payload(payload)
    replayed = h_level3_saturation_authority_from_payload(
        payload,
        independent_measured_evidence_sha256=(
            measured_pass.evidence_sha256
        ),
    )
    assert replayed == measured_pass

    tampered = dict(payload)
    tampered["covered_orbit_count"] = 0
    with pytest.raises(ValueError, match="covered_orbit_count"):
        h_level3_saturation_authority_from_payload(
            tampered,
            independent_measured_evidence_sha256=(
                measured_pass.evidence_sha256
            ),
        )


def test_no_ordinary_h_action_requires_level3_saturation_coverage() -> None:
    current = _goals()
    p_neutral = _action(
        action_id="p-neutral-h-saturation",
        kind="p-up",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    unknown = _h_saturation(
        level_two_target_ids=("cell:r0:l2:i0:j0:k0",),
        periodic_orbit_ids=("h3-orbit-000000-abc123",),
    )
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(p_neutral,),
        h_actions=(),
        p6_saturation=_p6_saturation(),
        h_level3_saturation=unknown,
    )

    result = _advance(catalog)

    assert result.accepted_current_state is True
    assert result.h_enrichment_action_count == 0
    assert result.freeze_ready is False
    assert "h_level3_saturation_unmeasured" in result.reasons
    assert "both_shadow_lanes_inside_freeze_threshold" not in result.reasons

    measured_catalog = replace(
        catalog,
        h_level3_saturation=_measured_h_saturation(
            normalized_max=0.25
        ),
    )
    measured_result = _advance(measured_catalog)
    assert measured_result.accepted_current_state is True
    assert "h_level3_saturation_unmeasured" not in measured_result.reasons
    assert "both_shadow_lanes_inside_freeze_threshold" in (
        measured_result.reasons
    )


def test_all_p6_without_p_action_is_accepted_but_cannot_freeze() -> None:
    current = _goals()
    h_neutral = _action(
        action_id="h-neutral-all-p6",
        kind="h-refine",
        current=current,
        endpoint_delta=0.0,
        dwr_delta=0.0,
    )
    catalog = ShadowCatalog(
        current_goal_sha256=current.sha256,
        p_actions=(),
        h_actions=(h_neutral,),
        p6_saturation=_p6_saturation(
            p6_target_ids=("cell:r0:l0:i0:j0:k0",),
        ),
        h_level3_saturation=_h_saturation(),
    )

    result = _advance(catalog)

    assert result.accepted_current_state is True
    assert result.status == "accepted_no_safe_action"
    assert result.selected_action_ids == ()
    assert result.freeze_ready is False
    assert result.p_enrichment_action_count == 0
    assert "p6_saturation_unmeasured" in result.reasons
