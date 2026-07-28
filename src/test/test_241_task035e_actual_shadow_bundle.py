from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace
from typing import Any

import pytest

from benchmarks import task035e_blind_cycle as blind_cycle
from benchmarks.task035e_candidate_output import adapt_candidate_output
from benchmarks.task035e_shadow_bundle import (
    DWR_EVALUATOR_SCHEMA,
    DWR_EVIDENCE_SCHEMA,
    DWR_PRODUCER_ROLE,
    GOAL_MARKING_SCHEMA,
    REQUEST_SCHEMA,
    VERIFICATION_PREDICTION_SCHEMA,
    BoundJSONInput,
    ShadowBundleError,
    _current_h_level3_saturation_authority,
    _current_p6_saturation_authority,
    build_shadow_bundle,
    main,
    write_shadow_bundle,
)
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
    ShadowCost,
    build_shadow_action,
)
from src.adaptivity.task035e_hp_transition import (
    HP_TRANSITION_ACTION_SCHEMA,
    canonical_hp_cell_target_id,
    hp_transition_action_payload,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    build_next_solver_plan,
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config
from src.test.test_232_task035e_candidate_output import (
    SOURCE_SHA,
    _rewrite_record,
    _write_candidate_run,
)
from benchmarks.task035e_candidate_output import CandidateWatchdogInput


P_DEGREE_SHA = "8" * 64
H_FOREST_SHA = "9" * 64
H_DEGREE_SHA = "a" * 64


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _namespaced_sha(value: object, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return _file_sha(path)


def _write_private_json(path: Path, value: object) -> str:
    file_sha = _write_json(path, value)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return file_sha


def _upgrade_to_replayable_cycle3_plan(
    record_input: CandidateWatchdogInput,
) -> CandidateWatchdogInput:
    """Replace the legacy minimal fixture plan with a real p4 cycle-3 plan."""

    config = target_stage4_config(degree=6, h_nm=20.0)
    plan = dict(
        build_task035e_initial_space_plan(
            config,
            path_id="A",
            source_sha=SOURCE_SHA,
            comm_size=8,
        ).plan_payload()
    )
    state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=plan,
        comm_size=8,
    )
    for cycle_index in range(1, 4):
        action = hp_transition_action_payload(
            state,
            action_id=f"fixture-cycle{cycle_index}-p-keep",
            kind="p-keep",
            degree_deltas={},
        )
        transition = build_next_solver_plan(
            config,
            current_plan=plan,
            state=state,
            action=action,
            comm_size=8,
        )
        plan = dict(transition.plan_payload)
        state = transition.next_state

    record = json.loads(record_input.path.read_text(encoding="utf-8"))
    run_dir = record_input.path.parent
    plan_path = run_dir / "blind-plan.json"
    plan_sha = _write_json(plan_path, plan)
    summary_path = run_dir / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    local_h = summary["stage4_local_h_constraint_audit"]
    mesh = local_h["mesh"]
    degree = local_h["degree_plan"]
    forest_sha = str(state.audit["leaf_catalog_sha256"])
    degree_sha = str(state.audit["cell_degree_plan_sha256"])
    mesh["plan_file_sha256"] = plan_sha
    mesh["forest"]["leaf_catalog_sha256"] = forest_sha
    mesh["carrier"]["leaf_catalog_sha256"] = forest_sha
    mesh["cell_interior_degree_plan_sha256"] = degree_sha
    degree["cell_degree_plan_sha256"] = degree_sha
    _write_json(summary_path, summary)

    plan_gate = record["task035e_blind_candidate_launch_gate"]["plan"]
    plan_gate["expected_file_sha256"] = plan_sha
    plan_gate["observed_file_sha256"] = plan_sha
    record["solver_summary"] = summary
    record["solver_summary_sha256"] = _file_sha(summary_path)
    _write_json(record_input.path, record)
    return CandidateWatchdogInput(
        record_input.path,
        _file_sha(record_input.path),
    )


def _set_role(record: Any, authority_role: str) -> Any:
    def mutate(payload: dict[str, object]) -> None:
        payload["task035e_blind_candidate"]["output_role"] = authority_role

    return _rewrite_record(record, mutate)


def _key(root: int, level: int, i: int, j: int, k: int) -> dict[str, int]:
    return {"root": root, "level": level, "i": i, "j": j, "k": k}


def _transition_payload(
    *,
    current: Any,
    action_id: str,
    kind: str,
    target_root: int,
    next_forest_sha: str,
    next_degree_sha: str,
) -> dict[str, object]:
    target = _key(target_root, 0, 0, 0, 0)
    target_id = f"cell:r{target_root}:l0:i0:j0:k0"
    if kind == "p-up":
        requested: list[dict[str, int]] = []
        degree_deltas = [{"key": target, "delta": 1}]
        removed: list[dict[str, int]] = []
        added: list[dict[str, int]] = []
        net_added = 0
        maximum_level = None
    else:
        requested = [target]
        degree_deltas = []
        removed = [target]
        added = [
            _key(target_root, 1, i, j, k)
            for i in range(2)
            for j in range(2)
            for k in range(2)
        ]
        added.sort(key=lambda row: tuple(row.values()))
        net_added = 7
        maximum_level = 2
    payload: dict[str, object] = {
        "schema_version": HP_TRANSITION_ACTION_SCHEMA,
        "status": "hp_transition_action_closed",
        "action_id": action_id,
        "kind": kind,
        "cycle_index": current.cycle_index + 1,
        "source_sha": current.source_sha,
        "algorithm_sha256": "b" * 64,
        "from_state_sha256": "c" * 64,
        "root_catalog_sha256": "d" * 64,
        "from_leaf_catalog_sha256": current.forest_leaf_catalog_sha256,
        "from_cell_degree_plan_sha256": current.cell_degree_plan_sha256,
        "from_forest_geometry_sha256": "e" * 64,
        "from_degree_plan_sha256": "f" * 64,
        "stage_prefix_length": current.cycle_index,
        "stage_prefix_sha256": "0" * 64,
        "requested_split_keys": requested,
        "degree_deltas": degree_deltas,
        "canonical_target_ids": [target_id],
        "maximum_level": maximum_level,
        "expected_removed_leaf_keys": removed,
        "expected_added_leaf_keys": added,
        "expected_net_added_leaf_count": net_added,
        "expected_next_leaf_catalog_sha256": next_forest_sha,
        "expected_next_cell_degree_plan_sha256": next_degree_sha,
        "expected_next_forest_geometry_sha256": "1" * 64,
        "expected_next_degree_plan_sha256": "2" * 64,
    }
    payload["action_identity_sha256"] = _canonical_sha(
        {
            "action_id": action_id,
            "kind": kind,
            "cycle_index": current.cycle_index + 1,
            "source_sha": current.source_sha,
            "algorithm_sha256": "b" * 64,
            "canonical_target_ids": [target_id],
        }
    )
    payload["action_sha256"] = _canonical_sha(payload)
    return payload


def _marking_and_prediction(
    *,
    root: Path,
    current: Any,
    transition: dict[str, object],
) -> tuple[Path, str, Path, str, dict[str, float]]:
    target_ids = list(transition["canonical_target_ids"])
    predicted = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    selected_packet_sha = _namespaced_sha(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": target_ids,
            "signed_dwr_delta": predicted,
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )
    current_goals = blind_cycle.goal_vector_from_candidate_output(
        current.payload
    )
    current_plan = json.loads(
        current.plan_path.read_text(encoding="utf-8")
    )
    unsigned_marking: dict[str, object] = {
        "schema_version": GOAL_MARKING_SCHEMA,
        "status": "goal_marking_targets_selected",
        "classification": "REFERENCE_BLIND_LOCAL_MARKING_PASS",
        "pass": True,
        "source_sha": current.source_sha,
        "mpi_size": 8,
        "cycle_index": current.cycle_index,
        "action_kind": transition["kind"],
        "doerfler_theta": 0.5,
        "minimum_global_normalized_signal": 1.0e-6,
        "minimum_eligible_equal_weight_benefit": 1.0e-12,
        "algorithm_id": "fixture_equal_weight_cost_aware_doerfler",
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "fixed_equal_goal_weights": {
            goal_id: 1.0 / len(FORMAL_GOAL_IDS)
            for goal_id in FORMAL_GOAL_IDS
        },
        "current_plan_file_sha256": current.plan_file_sha256,
        "current_plan_content_sha256": _canonical_sha(current_plan),
        "current_state_sha256": transition["from_state_sha256"],
        "current_leaf_catalog_sha256": (
            current.forest_leaf_catalog_sha256
        ),
        "current_degree_plan_sha256": current.cell_degree_plan_sha256,
        "dwr_authority_file_sha256": "4" * 64,
        "dwr_authority_schema": "task035e.cellwise-dwr-authority.v2",
        "dwr_authority_sha256": "5" * 64,
        "structural_cost_model_sha256": "6" * 64,
        "global_actual_dwr_report_sha256": "7" * 64,
        "current_goal_sha256": current_goals.sha256,
        "shadow_goal_sha256": "8" * 64,
        "global_maximum_normalized_signed_dwr": 1.0,
        "signed_cellwise_closure_verified": True,
        "signed_closure_used_for_ranking": False,
        "absolute_contributions_used_only_for_ranking": True,
        "eligible_normalized_benefit": 1.0,
        "required_doerfler_benefit": 0.5,
        "selected_doerfler_benefit": 1.0,
        "selected_ranking_order": target_ids,
        "ranking": [
            {
                "target_id": target_id,
                "benefit_per_normalized_structural_cost": 1.0,
            }
            for target_id in target_ids
        ],
        "canonical_target_ids": target_ids,
        "selected_signed_dwr_delta": predicted,
        "selected_signed_dwr_delta_sha256": selected_packet_sha,
        "transition_preflight": {
            "pass": True,
            "preflight_id": "fixture",
            "p_down_selected": False,
            "first_two_cycle_no_p_down_preserved": True,
        },
        "transition_producer_arguments": {
            "action_kind": transition["kind"],
            "canonical_target_ids": target_ids,
        },
        "blocker": None,
        "reference_derived": False,
        "hidden_auditor_consumed": False,
        "ordinary_default_changed": False,
    }
    marking = {
        **unsigned_marking,
        "marking_sha256": _namespaced_sha(
            unsigned_marking,
            namespace=GOAL_MARKING_SCHEMA,
        ),
    }
    marking_path = root / "goal-marking.json"
    marking_file_sha = _write_private_json(marking_path, marking)
    unsigned_prediction: dict[str, object] = {
        "schema_version": VERIFICATION_PREDICTION_SCHEMA,
        "source_sha": current.source_sha,
        "cycle_index": transition["cycle_index"],
        "marking_cycle_index": current.cycle_index,
        "action_id": transition["action_id"],
        "action_kind": transition["kind"],
        "action_sha256": transition["action_sha256"],
        "action_identity_sha256": transition["action_identity_sha256"],
        "marking_file_sha256": marking_file_sha,
        "marking_payload_sha256": marking["marking_sha256"],
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        "predicted_deltas": [
            [goal_id, predicted[goal_id]]
            for goal_id in FORMAL_GOAL_IDS
        ],
    }
    prediction = {
        **unsigned_prediction,
        "prediction_sha256": _namespaced_sha(
            unsigned_prediction,
            namespace=VERIFICATION_PREDICTION_SCHEMA,
        ),
    }
    prediction_path = root / "verification-prediction.json"
    prediction_file_sha = _write_private_json(prediction_path, prediction)
    return (
        marking_path,
        marking_file_sha,
        prediction_path,
        prediction_file_sha,
        predicted,
    )


def _rewrite_shadow_candidate(
    record: Any,
    *,
    current: Any,
    transition: dict[str, object],
    next_forest_sha: str,
    next_degree_sha: str,
    increments: tuple[int, int, int, int, int, int],
) -> Any:
    record_path = record.path
    summary_path = record_path.parent / "run_summary.json"
    plan_path = record_path.parent / "blind-plan.json"
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    current_plan = json.loads(current.plan_path.read_text(encoding="utf-8"))
    current_chain = list(
        current_plan["provenance"]["stage_action_sha256s"]
    )
    next_chain = [*current_chain, transition["action_sha256"]]
    next_plan_without_provenance = {
        "expected_forest": {"leaf_catalog_sha256": next_forest_sha},
        "cell_interior_degree_plan_sha256": next_degree_sha,
    }
    provenance: dict[str, object] = {
        "schema_version": "task035e.blind-solver-plan-transition.v2",
        "status": "blind_solver_plan_transition_closed",
        "source_sha": current.source_sha,
        "algorithm_sha256": transition["algorithm_sha256"],
        "cycle_index": transition["cycle_index"],
        "previous_plan_content_sha256": _canonical_sha(current_plan),
        "previous_plan_canonical_solver_content_sha256": _canonical_sha(
            {
                key: value
                for key, value in current_plan.items()
                if key != "provenance"
            }
        ),
        "from_state_sha256": transition["from_state_sha256"],
        "transition_action_sha256": transition["action_sha256"],
        "transition_action_id": transition["action_id"],
        "transition_action_kind": transition["kind"],
        "transition_action_cycle_index": transition["cycle_index"],
        "transition_action_source_sha": transition["source_sha"],
        "transition_action_target_ids": transition["canonical_target_ids"],
        "next_state_sha256": "3" * 64,
        "stage_action_sha256s": next_chain,
        "next_stage_prefix_sha256": _canonical_sha(
            {"action_sha256s": next_chain}
        ),
        "from_leaf_catalog_sha256": current.forest_leaf_catalog_sha256,
        "from_cell_degree_plan_sha256": current.cell_degree_plan_sha256,
        "next_leaf_catalog_sha256": next_forest_sha,
        "next_cell_degree_plan_sha256": next_degree_sha,
        "goal_values_embedded": False,
        "dwr_values_embedded": False,
        "evaluator_inputs_consumed": False,
        "ordinary_default_changed": False,
        "next_plan_canonical_solver_content_sha256": _canonical_sha(
            next_plan_without_provenance
        ),
    }
    provenance["transition_provenance_sha256"] = _canonical_sha(provenance)
    next_plan = {
        **next_plan_without_provenance,
        "provenance": provenance,
    }
    _write_json(plan_path, next_plan)
    plan_sha = _file_sha(plan_path)

    (
        raw_active_inc,
        active_inc,
        row_inc,
        nnz_inc,
        factor_inc,
        peak_inc,
    ) = increments
    local_h = summary["stage4_local_h_constraint_audit"]
    mesh = local_h["mesh"]
    degree = local_h["degree_plan"]
    mesh["plan_file_sha256"] = plan_sha
    mesh["forest"]["leaf_catalog_sha256"] = next_forest_sha
    mesh["carrier"]["leaf_catalog_sha256"] = next_forest_sha
    mesh["cell_interior_degree_plan_sha256"] = next_degree_sha
    degree["cell_degree_plan_sha256"] = next_degree_sha
    summary["num_raw_broken_active_fe_dofs"] += raw_active_inc
    summary["num_actual_conforming_active_fe_dofs"] += active_inc
    degree["active_rows"] = summary["num_raw_broken_active_fe_dofs"]
    summary["matrix_stats"]["matrix_rows"] += row_inc
    summary["matrix_stats"]["matrix_cols"] += row_inc
    summary["matrix_stats"]["matrix_nnz_used"] += nnz_inc
    factor = summary["stage4_dtn_factor_inventory"]["matrix_stats"]
    factor["matrix_rows"] += row_inc
    factor["matrix_nnz_used"] += factor_inc
    _write_json(summary_path, summary)

    raw["task035e_blind_candidate_launch_gate"]["plan"].update(
        {
            "expected_file_sha256": plan_sha,
            "observed_file_sha256": plan_sha,
        }
    )
    raw["calibration"]["exact_rows"] = summary["matrix_stats"]["matrix_rows"]
    raw["calibration"]["exact_assembled_nnz"] = summary["matrix_stats"][
        "matrix_nnz_used"
    ]
    raw["matrix_inventory"]["final"] = summary["matrix_stats"]
    raw["task035e_blind_candidate_launch_gate"]["live_resource_gate"][
        "maximum_job_memory_authority_bytes"
    ] += peak_inc
    raw["solver_summary"] = summary
    raw["solver_summary_sha256"] = _file_sha(summary_path)
    _write_json(record_path, raw)
    return type(record)(record_path, _file_sha(record_path))


def _dwr_outer(
    *,
    current: Any,
    shadow: Any,
    action_id: str,
    kind: str,
    transition: dict[str, object],
    transition_file_sha: str,
    **overrides: object,
) -> dict[str, object]:
    current_goals = blind_cycle.goal_vector_from_candidate_output(
        current.payload
    )
    shadow_goals = blind_cycle.goal_vector_from_candidate_output(
        shadow.payload
    )
    # The physical endpoints happen to be identical in this compact fixture,
    # while the independent adjoint evaluator predicts a small signed change.
    # This directly proves that the bundle producer does not replace DWR by the
    # endpoint delta.
    predicted = {
        goal_id: (index % 3 + 1) * 1.0e-8
        for index, goal_id in enumerate(FORMAL_GOAL_IDS)
    }
    payload: dict[str, object] = {
        "schema_version": DWR_EVIDENCE_SCHEMA,
        "producer_role": DWR_PRODUCER_ROLE,
        "source_sha": SOURCE_SHA,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "action_id": action_id,
        "kind": kind,
        "target_ids": transition["canonical_target_ids"],
        "transition_action_sha256": transition["action_sha256"],
        "transition_action_file_sha256": transition_file_sha,
        "transition_action_identity_sha256": transition[
            "action_identity_sha256"
        ],
        "current_output_sha256": current.output_sha256,
        "shadow_output_sha256": shadow.output_sha256,
        "current_watchdog_record_sha256": current.record_sha256,
        "shadow_watchdog_record_sha256": shadow.record_sha256,
        "current_plan_file_sha256": current.plan_file_sha256,
        "shadow_plan_file_sha256": shadow.plan_file_sha256,
        "current_config_sha256": current.config_sha256,
        "shadow_config_sha256": shadow.config_sha256,
        "current_mesh_forest_sha256": current.forest_leaf_catalog_sha256,
        "current_degree_map_sha256": current.cell_degree_plan_sha256,
        "shadow_mesh_forest_sha256": shadow.forest_leaf_catalog_sha256,
        "shadow_degree_map_sha256": shadow.cell_degree_plan_sha256,
        "current_goal_sha256": current_goals.sha256,
        "shadow_goal_sha256": shadow_goals.sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "evaluator": {
            "schema_version": DWR_EVALUATOR_SCHEMA,
            "evaluator_id": "variable_p_nested_actual_dwr",
            "evaluator_source_sha": SOURCE_SHA,
            "implementation_sha256": "5" * 64,
            "primal_residual_sha256": "6" * 64,
            "adjoint_system_sha256": "7" * 64,
            "method": "signed_residual_weighted_adjoint",
        },
        "actual_adjoint_solve": True,
        "actual_dwr_evaluation": True,
        "signed_not_absolute": True,
        "endpoint_delta_used_as_dwr": False,
        "synthetic": False,
        "reference_derived": False,
        "signed_dwr_delta": predicted,
        "sign_consistent": True,
    }
    payload.update(overrides)
    return {
        "schema_version": DWR_EVIDENCE_SCHEMA,
        "sha256": _canonical_sha(payload),
        "payload": payload,
    }


def _fixture(
    tmp_path: Path,
    *,
    dwr_overrides: dict[str, object] | None = None,
) -> tuple[BoundJSONInput, dict[str, Any]]:
    current_record = _upgrade_to_replayable_cycle3_plan(
        _write_candidate_run(tmp_path / "current")
    )
    current = adapt_candidate_output(current_record)
    p_transition = _transition_payload(
        current=current,
        action_id="p-up-cell-1",
        kind="p-up",
        target_root=1,
        next_forest_sha=current.forest_leaf_catalog_sha256,
        next_degree_sha=P_DEGREE_SHA,
    )
    h_transition = _transition_payload(
        current=current,
        action_id="h-refine-root-9",
        kind="h-refine",
        target_root=9,
        next_forest_sha=H_FOREST_SHA,
        next_degree_sha=H_DEGREE_SHA,
    )
    p_record = _rewrite_shadow_candidate(
        _set_role(
            _write_candidate_run(tmp_path / "p-shadow"),
            "blind_p_shadow_solve",
        ),
        current=current,
        transition=p_transition,
        next_forest_sha=current.forest_leaf_catalog_sha256,
        next_degree_sha=P_DEGREE_SHA,
        increments=(20, 20, 10, 100, 200, 1024),
    )
    h_record = _rewrite_shadow_candidate(
        _set_role(
            _write_candidate_run(tmp_path / "h-shadow"),
            "blind_h_shadow_solve",
        ),
        current=current,
        transition=h_transition,
        next_forest_sha=H_FOREST_SHA,
        next_degree_sha=H_DEGREE_SHA,
        increments=(40, 40, 20, 200, 400, -1024),
    )
    p_shadow = adapt_candidate_output(p_record, output_role="p-shadow")
    h_shadow = adapt_candidate_output(h_record, output_role="h-shadow")

    p_transition_path = tmp_path / "transitions" / "p-action.json"
    p_transition_file_sha = _write_json(
        p_transition_path,
        p_transition,
    )
    h_transition_path = tmp_path / "transitions" / "h-action.json"
    h_transition_outer = {
        "schema_version": HP_TRANSITION_ACTION_SCHEMA,
        "sha256": _canonical_sha(h_transition),
        "payload": h_transition,
    }
    h_transition_file_sha = _write_json(
        h_transition_path,
        h_transition_outer,
    )
    (
        p_marking_path,
        p_marking_sha,
        p_prediction_path,
        p_prediction_sha,
        p_prediction,
    ) = _marking_and_prediction(
        root=tmp_path / "p-selected",
        current=current,
        transition=p_transition,
    )
    (
        h_marking_path,
        h_marking_sha,
        h_prediction_path,
        h_prediction_sha,
        _h_prediction,
    ) = _marking_and_prediction(
        root=tmp_path / "h-selected",
        current=current,
        transition=h_transition,
    )

    p_outer = _dwr_outer(
        current=current,
        shadow=p_shadow,
        action_id="p-up-cell-1",
        kind="p-up",
        transition=p_transition,
        transition_file_sha=p_transition_file_sha,
        **(dwr_overrides or {}),
    )
    h_outer = _dwr_outer(
        current=current,
        shadow=h_shadow,
        action_id="h-refine-root-9",
        kind="h-refine",
        transition=h_transition,
        transition_file_sha=h_transition_file_sha,
    )
    p_dwr_path = tmp_path / "evidence" / "p-dwr.json"
    h_dwr_path = tmp_path / "evidence" / "h-dwr.json"
    p_dwr_sha = _write_json(p_dwr_path, p_outer)
    h_dwr_sha = _write_json(h_dwr_path, h_outer)

    def action(
        *,
        record: Any,
        dwr_path: Path,
        dwr_sha: str,
        transition_path: Path,
        transition_file_sha: str,
        marking_path: Path,
        marking_file_sha: str,
        prediction_path: Path,
        prediction_file_sha: str,
    ) -> dict[str, object]:
        return {
            "transition_action": {
                "path": str(transition_path),
                "sha256": transition_file_sha,
            },
            "goal_marking": {
                "path": str(marking_path),
                "sha256": marking_file_sha,
            },
            "verification_prediction": {
                "path": str(prediction_path),
                "sha256": prediction_file_sha,
            },
            "shadow_record": {
                "path": str(record.path),
                "sha256": record.sha256,
            },
            "dwr_evidence": {
                "path": str(dwr_path),
                "sha256": dwr_sha,
            },
        }

    request = {
        "schema_version": REQUEST_SCHEMA,
        "current_record": {
            "path": str(current_record.path),
            "sha256": current_record.sha256,
        },
        "p_actions": [
            action(
                record=p_record,
                dwr_path=p_dwr_path,
                dwr_sha=p_dwr_sha,
                transition_path=p_transition_path,
                transition_file_sha=p_transition_file_sha,
                marking_path=p_marking_path,
                marking_file_sha=p_marking_sha,
                prediction_path=p_prediction_path,
                prediction_file_sha=p_prediction_sha,
            )
        ],
        "h_actions": [
            action(
                record=h_record,
                dwr_path=h_dwr_path,
                dwr_sha=h_dwr_sha,
                transition_path=h_transition_path,
                transition_file_sha=h_transition_file_sha,
                marking_path=h_marking_path,
                marking_file_sha=h_marking_sha,
                prediction_path=h_prediction_path,
                prediction_file_sha=h_prediction_sha,
            )
        ],
    }
    request_path = tmp_path / "shadow-request.json"
    request_sha = _write_json(request_path, request)
    return BoundJSONInput(request_path, request_sha), {
        "current": current,
        "request": request,
        "p_dwr_path": p_dwr_path,
        "p_transition_path": p_transition_path,
        "p_transition": p_transition,
        "p_shadow_record": p_record,
        "p_marking_path": p_marking_path,
        "p_prediction_path": p_prediction_path,
        "p_prediction": p_prediction,
        "h_marking_path": h_marking_path,
        "h_marking_sha": h_marking_sha,
    }


def test_shadow_action_allows_prediction_magnitude_to_differ_from_endpoint() -> None:
    current = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    shadow_values = {goal_id: 1.0 for goal_id in FORMAL_GOAL_IDS}
    shadow = GoalVector.from_mapping(shadow_values)
    predicted = {goal_id: 0.5 for goal_id in FORMAL_GOAL_IDS}
    action = build_shadow_action(
        action_id="p-up-cell-1",
        kind="p-up",
        target_ids=("cell:1",),
        current=current,
        shadow=shadow,
        signed_dwr_delta=predicted,
        cost=ShadowCost(1, 1, 1, 1, 1),
        sign_consistent=True,
        transition_action_sha256="1" * 64,
        transition_action_file_sha256="2" * 64,
        transition_action_identity_sha256="3" * 64,
        next_mesh_forest_sha256="4" * 64,
        next_degree_map_sha256="5" * 64,
    )
    assert dict(action.signed_dwr_delta) != {
        goal_id: 1.0 for goal_id in FORMAL_GOAL_IDS
    }

    opposite = dict(predicted)
    opposite[FORMAL_GOAL_IDS[0]] = -0.5
    with pytest.raises(ValueError, match="sign_consistent differs"):
        build_shadow_action(
            action_id="p-up-cell-2",
            kind="p-up",
            target_ids=("cell:2",),
            current=current,
            shadow=shadow,
            signed_dwr_delta=opposite,
            cost=ShadowCost(1, 1, 1, 1, 1),
            sign_consistent=True,
            transition_action_sha256="1" * 64,
            transition_action_file_sha256="2" * 64,
            transition_action_identity_sha256="3" * 64,
            next_mesh_forest_sha256="4" * 64,
            next_degree_map_sha256="5" * 64,
        )
    inconsistent = build_shadow_action(
        action_id="p-up-cell-3",
        kind="p-up",
        target_ids=("cell:3",),
        current=current,
        shadow=shadow,
        signed_dwr_delta=opposite,
        cost=ShadowCost(1, 1, 1, 1, 1),
        sign_consistent=False,
        transition_action_sha256="1" * 64,
        transition_action_file_sha256="2" * 64,
        transition_action_identity_sha256="3" * 64,
        next_mesh_forest_sha256="4" * 64,
        next_degree_map_sha256="5" * 64,
    )
    assert inconsistent.sign_consistent is False


def test_p6_saturation_inventory_is_replayed_from_mixed_p5_p6_plan(
    tmp_path: Path,
) -> None:
    config = target_stage4_config(degree=6, h_nm=20.0)
    initial_plan = dict(
        build_task035e_initial_space_plan(
            config,
            path_id="A",
            source_sha=SOURCE_SHA,
            comm_size=8,
        ).plan_payload()
    )
    initial_state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=initial_plan,
        comm_size=8,
    )
    target_key = sorted(initial_state.cell_degree_by_key)[0]
    assert initial_state.cell_degree_by_key[target_key] == 5
    action = hp_transition_action_payload(
        initial_state,
        action_id="fixture-p6-saturation-p-up",
        kind="p-up",
        degree_deltas={target_key: 1},
    )
    transition = build_next_solver_plan(
        config,
        current_plan=initial_plan,
        state=initial_state,
        action=action,
        comm_size=8,
    )
    plan_path = tmp_path / "mixed-plan.json"
    plan_file_sha = _write_json(
        plan_path,
        dict(transition.plan_payload),
    )
    state = transition.next_state
    authority, has_p_up_target = _current_p6_saturation_authority(
        SimpleNamespace(
            plan_path=plan_path,
            plan_file_sha256=plan_file_sha,
            source_sha=SOURCE_SHA,
            cycle_index=1,
            forest_leaf_catalog_sha256=state.audit[
                "leaf_catalog_sha256"
            ],
            cell_degree_plan_sha256=state.audit[
                "cell_degree_plan_sha256"
            ],
        )
    )

    assert has_p_up_target is True
    assert authority.status == "unknown"
    assert authority.coverage_complete is False
    assert authority.normalized_max is None
    assert authority.p6_target_ids == (
        canonical_hp_cell_target_id(target_key),
    )
    h_authority, has_h_refine_target = (
        _current_h_level3_saturation_authority(
            SimpleNamespace(
                plan_path=plan_path,
                plan_file_sha256=plan_file_sha,
                source_sha=SOURCE_SHA,
                cycle_index=1,
                forest_leaf_catalog_sha256=state.audit[
                    "leaf_catalog_sha256"
                ],
                cell_degree_plan_sha256=state.audit[
                    "cell_degree_plan_sha256"
                ],
            )
        )
    )
    assert h_authority.production_maximum_level == 2
    assert h_authority.shadow_maximum_level == 3
    assert h_authority.selectable_as_production is False
    assert has_h_refine_target is True


def test_actual_shadow_bundle_is_blind_cycle_compatible_and_immutable(
    tmp_path: Path,
) -> None:
    request, context = _fixture(tmp_path)
    built = build_shadow_bundle(request)
    current = context["current"]
    current_goals = blind_cycle.goal_vector_from_candidate_output(
        current.payload
    )
    built_p_action = built.payload["p_actions"][0]
    global_dwr = json.loads(
        context["p_dwr_path"].read_text(encoding="utf-8")
    )["payload"]["signed_dwr_delta"]
    assert built_p_action["signed_dwr_delta"] == context["p_prediction"]
    assert built_p_action["signed_dwr_delta"] != global_dwr
    catalog = blind_cycle._shadow_catalog(
        built.payload,
        current=current_goals,
        source_sha=SOURCE_SHA,
        trial_id=current.trial_id,
        cycle_index=3,
        mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        degree_map_sha256=current.cell_degree_plan_sha256,
        plan_file_sha256=current.plan_file_sha256,
        complete_output_sha256=current.output_sha256,
    )
    assert len(catalog.p_actions) == 1
    assert len(catalog.h_actions) == 1
    assert (
        catalog.h_level3_saturation.authority_sha256
        == built.payload["h_level3_saturation"]["authority_sha256"]
    )
    assert built.payload["trial_id"] == current.trial_id
    assert catalog.p_actions[0].target_ids == (
        "cell:r1:l0:i0:j0:k0",
    )
    p_evidence = built.payload["p_actions"][0]["external_evidence"]
    assert p_evidence["goal_marking_file_sha256"] == _file_sha(
        context["p_marking_path"]
    )
    assert p_evidence["verification_prediction_file_sha256"] == _file_sha(
        context["p_prediction_path"]
    )
    prediction_payload = json.loads(
        context["p_prediction_path"].read_text(encoding="utf-8")
    )
    assert p_evidence["verification_prediction_payload_sha256"] == (
        prediction_payload["prediction_sha256"]
    )
    assert p_evidence["verification_prediction_marking_file_sha256"] == (
        p_evidence["goal_marking_file_sha256"]
    )
    assert p_evidence["verification_prediction_marking_payload_sha256"] == (
        p_evidence["goal_marking_payload_sha256"]
    )
    assert p_evidence["selected_shadow_global_dwr_sha256"] != (
        p_evidence["verification_prediction_payload_sha256"]
    )
    assert catalog.p_actions[0].transition_action_sha256 == (
        p_evidence["transition_action_sha256"]
    )
    assert catalog.p_actions[0].transition_action_file_sha256 == (
        p_evidence["transition_action_file_sha256"]
    )
    assert catalog.p_actions[0].transition_action_identity_sha256 == (
        p_evidence["transition_action_identity_sha256"]
    )
    assert catalog.p_actions[0].next_mesh_forest_sha256 == (
        p_evidence["next_leaf_catalog_sha256"]
    )
    assert catalog.p_actions[0].next_degree_map_sha256 == (
        p_evidence["next_cell_degree_plan_sha256"]
    )
    assert catalog.p_actions[0].cost == ShadowCost(
        20,
        10,
        100,
        200,
        1024,
    )
    assert catalog.h_actions[0].cost == ShadowCost(
        40,
        20,
        200,
        400,
        0,
    )
    h_evidence = built.payload["h_actions"][0]["external_evidence"]
    assert h_evidence["signed_structural_delta"][
        "added_solver_peak_bytes"
    ] == -1024
    assert h_evidence["measured_structural_benefit"][
        "added_solver_peak_bytes"
    ] == 1024
    assert dict(catalog.p_actions[0].signed_dwr_delta) == (
        context["p_prediction"]
    )
    assert all(
        value == 0.0
        for value in (
            catalog.p_actions[0].shadow.by_id[goal_id]
            - catalog.p_actions[0].current.by_id[goal_id]
            for goal_id in FORMAL_GOAL_IDS
        )
    )

    output = tmp_path / "actual-shadow-bundle.json"
    receipt = write_shadow_bundle(output, built)
    assert receipt.file_sha256 == _file_sha(output)
    assert stat.S_IMODE(output.stat().st_mode) == (
        stat.S_IRUSR | stat.S_IWUSR
    )
    with pytest.raises(FileExistsError):
        write_shadow_bundle(output, built)


@pytest.mark.parametrize(
    ("location", "field", "value"),
    (
        ("request", "mesh_forest_sha256", "0" * 64),
        ("action", "target_ids", ["cell:r0:l0:i0:j0:k0"]),
        (
            "action",
            "cost",
            {
                "added_active_dofs": 0,
                "added_rows": 0,
                "added_matrix_nnz": 0,
                "added_factor_nnz": 0,
                "added_solver_peak_bytes": 0,
            },
        ),
    ),
)
def test_shadow_bundle_rejects_self_reported_plan_target_or_cost(
    tmp_path: Path,
    location: str,
    field: str,
    value: object,
) -> None:
    request, context = _fixture(tmp_path)
    raw = context["request"]
    target = raw if location == "request" else raw["p_actions"][0]
    target[field] = value
    request_sha = _write_json(request.path, raw)
    with pytest.raises(ShadowBundleError, match="closed schema"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))


def test_shadow_bundle_rejects_rehashed_target_substitution(
    tmp_path: Path,
) -> None:
    request, context = _fixture(tmp_path)
    transition_path = context["p_transition_path"]
    transition = context["p_transition"]
    transition["canonical_target_ids"] = ["cell:r2:l0:i0:j0:k0"]
    transition["action_identity_sha256"] = _canonical_sha(
        {
            "action_id": transition["action_id"],
            "kind": transition["kind"],
            "cycle_index": transition["cycle_index"],
            "source_sha": transition["source_sha"],
            "algorithm_sha256": transition["algorithm_sha256"],
            "canonical_target_ids": transition["canonical_target_ids"],
        }
    )
    transition.pop("action_sha256")
    transition["action_sha256"] = _canonical_sha(transition)
    transition_file_sha = _write_json(transition_path, transition)
    context["request"]["p_actions"][0]["transition_action"]["sha256"] = (
        transition_file_sha
    )
    request_sha = _write_json(request.path, context["request"])
    with pytest.raises(ShadowBundleError, match="key-derived"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))


def test_shadow_bundle_rejects_shadow_plan_tamper(tmp_path: Path) -> None:
    request, context = _fixture(tmp_path)
    shadow = adapt_candidate_output(
        context["p_shadow_record"],
        output_role="p-shadow",
    )
    shadow.plan_path.write_text(
        shadow.plan_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(ShadowBundleError, match="SHA-256 mismatch"):
        build_shadow_bundle(request)


def test_shadow_bundle_rejects_prediction_tamper_and_wrong_action(
    tmp_path: Path,
) -> None:
    request, context = _fixture(tmp_path)
    prediction_path = context["p_prediction_path"]
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    prediction["predicted_deltas"][0][1] = 1.0
    prediction_file_sha = _write_private_json(prediction_path, prediction)
    context["request"]["p_actions"][0]["verification_prediction"][
        "sha256"
    ] = prediction_file_sha
    request_sha = _write_json(request.path, context["request"])
    with pytest.raises(ShadowBundleError, match="self-hash differs"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))

    request, context = _fixture(tmp_path / "wrong-action")
    prediction_path = context["p_prediction_path"]
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    prediction["action_id"] = "wrong-selected-action"
    unsigned = dict(prediction)
    unsigned.pop("prediction_sha256")
    prediction["prediction_sha256"] = _namespaced_sha(
        unsigned,
        namespace=VERIFICATION_PREDICTION_SCHEMA,
    )
    prediction_file_sha = _write_private_json(prediction_path, prediction)
    context["request"]["p_actions"][0]["verification_prediction"][
        "sha256"
    ] = prediction_file_sha
    request_sha = _write_json(request.path, context["request"])
    with pytest.raises(ShadowBundleError, match="marking/action"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))


def test_shadow_bundle_rejects_wrong_marking_prediction_hash_and_mode(
    tmp_path: Path,
) -> None:
    request, context = _fixture(tmp_path)
    context["request"]["p_actions"][0]["goal_marking"] = {
        "path": str(context["h_marking_path"]),
        "sha256": context["h_marking_sha"],
    }
    request_sha = _write_json(request.path, context["request"])
    with pytest.raises(ShadowBundleError, match="goal marking.*identity"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))

    request, context = _fixture(tmp_path / "wrong-hash")
    context["request"]["p_actions"][0]["verification_prediction"][
        "sha256"
    ] = "0" * 64
    request_sha = _write_json(request.path, context["request"])
    with pytest.raises(ShadowBundleError, match="file SHA-256 mismatch"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))

    request, context = _fixture(tmp_path / "wrong-mode")
    context["p_prediction_path"].chmod(
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IRGRP
        | stat.S_IROTH
    )
    with pytest.raises(ShadowBundleError, match="mode-0600"):
        build_shadow_bundle(request)


def test_shadow_bundle_rechecks_selected_prediction_against_actual_endpoint(
    tmp_path: Path,
) -> None:
    request, context = _fixture(tmp_path)
    marking_path = context["p_marking_path"]
    marking = json.loads(marking_path.read_text(encoding="utf-8"))
    selected = {goal_id: 1.0e-3 for goal_id in FORMAL_GOAL_IDS}
    marking["selected_signed_dwr_delta"] = selected
    marking["selected_signed_dwr_delta_sha256"] = _namespaced_sha(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": marking["canonical_target_ids"],
            "signed_dwr_delta": selected,
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )
    unsigned_marking = dict(marking)
    unsigned_marking.pop("marking_sha256")
    marking["marking_sha256"] = _namespaced_sha(
        unsigned_marking,
        namespace=GOAL_MARKING_SCHEMA,
    )
    marking_file_sha = _write_private_json(marking_path, marking)
    context["request"]["p_actions"][0]["goal_marking"]["sha256"] = (
        marking_file_sha
    )

    prediction_path = context["p_prediction_path"]
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    prediction["marking_file_sha256"] = marking_file_sha
    prediction["marking_payload_sha256"] = marking["marking_sha256"]
    prediction["predicted_deltas"] = [
        [goal_id, selected[goal_id]] for goal_id in FORMAL_GOAL_IDS
    ]
    unsigned_prediction = dict(prediction)
    unsigned_prediction.pop("prediction_sha256")
    prediction["prediction_sha256"] = _namespaced_sha(
        unsigned_prediction,
        namespace=VERIFICATION_PREDICTION_SCHEMA,
    )
    prediction_file_sha = _write_private_json(
        prediction_path,
        prediction,
    )
    context["request"]["p_actions"][0]["verification_prediction"][
        "sha256"
    ] = prediction_file_sha
    request_sha = _write_json(request.path, context["request"])
    with pytest.raises(ShadowBundleError, match="sign/effectivity gate"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"reference_derived": True}, "identity"),
        ({"synthetic": True}, "identity"),
        ({"endpoint_delta_used_as_dwr": True}, "identity"),
        ({"actual_adjoint_solve": False}, "identity"),
        ({"sign_consistent": False}, "sign_consistent differs"),
    ),
)
def test_shadow_bundle_rejects_nonactual_or_misreported_dwr(
    tmp_path: Path,
    override: dict[str, object],
    message: str,
) -> None:
    request, _context = _fixture(tmp_path, dwr_overrides=override)
    with pytest.raises(ShadowBundleError, match=message):
        build_shadow_bundle(request)


def test_shadow_bundle_rejects_role_and_hash_drift(tmp_path: Path) -> None:
    request, context = _fixture(tmp_path)
    raw = context["request"]
    raw["p_actions"][0]["shadow_record"] = raw["current_record"]
    request_sha = _write_json(request.path, raw)
    with pytest.raises(ShadowBundleError, match="authority is invalid"):
        build_shadow_bundle(BoundJSONInput(request.path, request_sha))

    request, context = _fixture(tmp_path / "tamper")
    context["p_dwr_path"].write_text(
        context["p_dwr_path"].read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(ShadowBundleError, match="file SHA-256 mismatch"):
        build_shadow_bundle(request)


def test_shadow_bundle_cli_writes_nonphysical_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request, _context = _fixture(tmp_path)
    output = tmp_path / "bundle.json"
    assert main(
        [
            "--request",
            str(request.path),
            "--request-sha256",
            request.sha256,
            "--output",
            str(output),
        ]
    ) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "completed"
    assert receipt["source_sha"] == SOURCE_SHA
    assert "orders" not in receipt
