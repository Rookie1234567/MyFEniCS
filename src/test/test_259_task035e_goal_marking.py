from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from benchmarks.task035e_goal_marking import (
    CELLWISE_DWR_AUTHORITY_SCHEMA,
    GoalMarkingError,
    main,
    produce_goal_marking,
)
from benchmarks.task035e_cellwise_authority import (
    STRUCTURAL_COST_MODEL_SCHEMA,
    STRUCTURAL_COST_ROW_SCHEMA,
)
from benchmarks.task035e_transition_producer import write_transition_bundle
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
)
from src.adaptivity.task035e_actual_dwr import ACTUAL_DWR_SCHEMA
from src.adaptivity.task035e_hp_transition import (
    canonical_hp_cell_target_id,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _json_sha256(value: object, *, namespace: str | None = None) -> str:
    digest = hashlib.sha256()
    if namespace is not None:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(_canonical_bytes(value))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_private(path: Path, payload: object) -> str:
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return _file_sha256(path)


@pytest.fixture(scope="module")
def initial() -> tuple[dict[str, object], object]:
    config = target_stage4_config(degree=6, h_nm=20.0)
    plan = build_task035e_initial_space_plan(
        config,
        path_id="A",
        source_sha=_SOURCE_SHA,
        comm_size=8,
    ).plan_payload()
    state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=plan,
        comm_size=8,
    )
    return plan, state


def _global_dwr(
    *,
    state: object,
    action_kind: str = "p-up",
    eta: float = 1.0e-6,
) -> dict[str, object]:
    signed = {
        goal_id: eta if goal_id == FORMAL_GOAL_IDS[0] else 0.0
        for goal_id in FORMAL_GOAL_IDS
    }
    unsigned = {
        "schema_version": ACTUAL_DWR_SCHEMA,
        "status": "actual_live_shadow_dwr_pass",
        "pass": True,
        "source_sha": _SOURCE_SHA,
        "shadow_kind": (
            "p-shadow" if action_kind == "p-up" else "h-shadow"
        ),
        "request_sha256": "1" * 64,
        "shadow_plan_identity": {
            "provenance_cycle_index": state.cycle_index + 1,
        },
        "layout_identity": {},
        "operator_identity": {},
        "implementation_identity": {},
        "shadow_primal_gate": {},
        "current_primal_in_shadow": {},
        "shadow_rhs": {},
        "shadow_action_on_current": {},
        "enriched_current_residual": {},
        "goal_inventory": {
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        },
        "goals": [
            {
                "goal_id": goal_id,
                "signed_eta_real_zH_r": signed[goal_id],
                "actual_adjoint_solve_complete": True,
                "endpoint_goal_delta_consumed": False,
            }
            for goal_id in FORMAL_GOAL_IDS
        ],
        "aggregate_identities": {},
        "algebra": {
            "endpoint_goal_delta_consumed": False,
            "reference_solution_consumed": False,
        },
        "capability_credit": {
            "actual_enriched_residual_complete": True,
            "actual_59_goal_adjoint_complete": True,
            "actual_signed_dwr_complete": True,
            "accuracy_credit": False,
        },
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "report_sha256": _json_sha256(
            unsigned,
            namespace="task035e.actual-live-shadow-dwr-report.v1",
        ),
    }


def _cellwise_row(
    *,
    key: object,
    box: tuple[float, ...],
    degree: int,
    target_id: str,
    first_goal_contribution: float,
    salt: int,
) -> dict[str, object]:
    unsigned = {
        "target_id": target_id,
        "current_leaf_key": [
            key.root,
            key.level,
            key.i,
            key.j,
            key.k,
        ],
        "current_leaf_box": list(box),
        "current_leaf_degree": degree,
        "assigned_reduced_row_count": 1,
        "assigned_trace_row_count": 1,
        "assigned_auxiliary_row_count": 0,
        "local_residual_partition_sha256": f"{salt + 1:064x}",
        "local_adjoint_partition_sha256": f"{salt + 1000:064x}",
        "signed_dwr_contribution": {
            goal_id: (
                first_goal_contribution
                if goal_id == FORMAL_GOAL_IDS[0]
                else 0.0
            )
            for goal_id in FORMAL_GOAL_IDS
        },
    }
    return {
        **unsigned,
        "row_sha256": _json_sha256(
            unsigned,
            namespace="task035e.cellwise-signed-dwr-row.v1",
        ),
    }


def _cellwise_authority(
    *,
    plan: dict[str, object],
    plan_file_sha256: str,
    state: object,
    action_kind: str = "p-up",
    eta: float = 1.0e-6,
    contribution_scale: float = 1.0,
    omit_last_row: bool = False,
) -> dict[str, object]:
    global_dwr = _global_dwr(
        state=state,
        action_kind=action_kind,
        eta=eta,
    )
    target_ids = tuple(
        canonical_hp_cell_target_id(cell.key)
        for cell in state.forest.leaves
    )
    preferred = tuple(
        canonical_hp_cell_target_id(key)
        for key, degree in sorted(state.cell_degree_by_key.items())
        if degree == 4
    )
    assert len(preferred) >= 2
    contributions = {
        target_id: 0.0 for target_id in target_ids
    }
    contributions[preferred[0]] = 0.8 * eta * contribution_scale
    contributions[preferred[1]] = 0.2 * eta * contribution_scale
    rows = [
        _cellwise_row(
            key=cell.key,
            box=cell.box,
            degree=state.cell_degree_by_key[cell.key],
            target_id=target_id,
            first_goal_contribution=contributions[target_id],
            salt=index,
        )
        for index, (target_id, cell) in enumerate(
            zip(target_ids, state.forest.leaves, strict=True)
        )
    ]
    if omit_last_row:
        rows.pop()
    goal_values = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    goal_sha = GoalVector.from_mapping(goal_values).sha256
    designation_unsigned = {
        "schema_version": (
            "task035e.actual-dwr-current-leaf-row-designation.v1"
        ),
        "status": "actual_reduced_rows_designated_once",
        "pass": True,
        "current_leaf_count": len(rows),
        "shadow_leaf_count": len(rows),
        "independent_trace_rows": len(rows),
        "appended_auxiliary_rows": 0,
        "total_reduced_rows": len(rows),
    }
    designation = {
        **designation_unsigned,
        "designation_sha256": _json_sha256(
            designation_unsigned,
            namespace="task035e.actual-dwr-row-designation.v1",
        ),
    }
    localization_unsigned = {
        "schema_version": "task035e.cellwise-signed-dwr-partition.v1",
        "status": "cellwise_signed_dwr_partition_pass",
        "pass": True,
        "method": "element_residual_adjoint_pairing",
        "method_detail": "fixture owner-local row partition",
        "complete_current_leaf_partition": True,
        "global_signed_closure_verified": True,
        "actual_cellwise_residual_adjoint_pairing": True,
        "global_eta_evenly_distributed": False,
        "endpoint_delta_consumed": False,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        "current_plan_identity": {
            "file_sha256": plan_file_sha256,
            "forest_leaf_catalog_sha256": state.audit[
                "leaf_catalog_sha256"
            ],
            "cell_degree_plan_sha256": state.audit[
                "cell_degree_plan_sha256"
            ],
        },
        "shadow_plan_identity": {"file_sha256": "6" * 64},
        "row_designation_identity": designation,
        "residual_partition_catalog_sha256": _json_sha256(
            [
                row["local_residual_partition_sha256"]
                for row in rows
            ],
            namespace=(
                "task035e.actual-dwr.residual-partition-catalog.v1"
            ),
        ),
        "adjoint_partition_catalog_sha256": _json_sha256(
            [
                row["local_adjoint_partition_sha256"]
                for row in rows
            ],
            namespace=(
                "task035e.actual-dwr.adjoint-partition-catalog.v1"
            ),
        ),
        "maximum_global_signed_closure_error": 0.0,
        "rows": rows,
        "python_full_vector_gather_used": False,
        "native_fixed_size_hash_metadata_reduction": True,
        "native_leaf_goal_scalar_reduction": True,
    }
    localization = {
        **localization_unsigned,
        "partition_sha256": _json_sha256(
            localization_unsigned,
            namespace="task035e.cellwise-signed-dwr-partition.v1",
        ),
    }
    cost_rows = []
    for index, row in enumerate(rows):
        costs = {
            "estimated_added_active_dofs": 10 + index,
            "estimated_added_rows": 20 + index,
            "estimated_added_matrix_nnz": 30 + index,
            "estimated_added_factor_nnz": 40 + index,
        }
        costs["estimated_added_solver_peak_bytes"] = (
            20 * costs["estimated_added_matrix_nnz"]
            + 20 * costs["estimated_added_factor_nnz"]
            + 72 * costs["estimated_added_rows"]
        )
        cost_unsigned = {
            "schema_version": STRUCTURAL_COST_ROW_SCHEMA,
            "target_id": row["target_id"],
            "eligible": True,
            "ineligibility": None,
            "topology": {"fixture": True},
            "weights": {
                "active": 1 + index,
                "rows": 2 + index,
                "matrix_nnz": 3 + index,
                "factor_nnz": 4 + index,
            },
            "dwr_row_sha256": row["row_sha256"],
            "apportioned_cost": costs,
        }
        cost_rows.append(
            {
                **cost_unsigned,
                "row_sha256": _json_sha256(
                    cost_unsigned,
                    namespace=STRUCTURAL_COST_ROW_SCHEMA,
                ),
            }
        )
    cost_fields = tuple(cost_rows[0]["apportioned_cost"])
    global_cost = {
        name: sum(row["apportioned_cost"][name] for row in cost_rows)
        for name in cost_fields
    }
    global_cost["estimated_added_solver_peak_bytes"] += 8
    measured = {
        "raw_active_fe_dofs": global_cost[
            "estimated_added_active_dofs"
        ],
        "active_fe_dofs": global_cost["estimated_added_active_dofs"],
        "matrix_rows": global_cost["estimated_added_rows"],
        "matrix_nnz": global_cost["estimated_added_matrix_nnz"],
        "factor_nnz": global_cost["estimated_added_factor_nnz"],
        "solver_peak_bytes": 123,
    }
    current_inventory = {
        "raw_active_fe_dofs": 1000,
        "active_fe_dofs": 900,
        "matrix_rows": 800,
        "matrix_nnz": 10_000,
        "factor_nnz": 50_000,
        "solver_peak_bytes": 1_000_000,
    }
    shadow_inventory = {
        name: current_inventory[name] + measured[name]
        for name in current_inventory
    }
    matrix_bytes = (
        20 * measured["matrix_nnz"]
        + 4 * (measured["matrix_rows"] + 1)
    )
    factor_bytes = (
        20 * measured["factor_nnz"]
        + 4 * (measured["matrix_rows"] + 1)
    )
    vector_bytes = 64 * measured["matrix_rows"]
    cost_unsigned = {
        "schema_version": STRUCTURAL_COST_MODEL_SCHEMA,
        "status": "action_specific_structural_cost_model_pass",
        "pass": True,
        "action_kind": action_kind,
        "measurement_classification": {
            "endpoint_inventories": "measured",
            "per_leaf_peak": (
                "derived_only_from_apportioned_matrix_factor_vector_bytes"
            ),
        },
        "current_inventory": current_inventory,
        "shadow_inventory": shadow_inventory,
        "measured_global_delta": measured,
        "peak_proxy_components": {
            "matrix_csr_bytes": matrix_bytes,
            "factor_csr_bytes": factor_bytes,
            "simultaneous_vector_bytes": vector_bytes,
            "petsc_scalar_bytes": 16,
            "petsc_int_bytes": 4,
            "simultaneous_attributable_vector_count": 4,
            "unallocated_csr_terminal_pointer_bytes": 8,
        },
        "integer_apportionment": {
            "weights_are_leaf_count": False,
            "weights_are_eta": False,
            "eligible_only": True,
        },
        "common_cost_exclusion": {
            "measured_solver_job_peak_delta_bytes": 123,
            "solver_job_peak_distributed_to_leaves": False,
        },
        "global_apportioned_cost": global_cost,
        "rows": cost_rows,
        "row_catalog_sha256": _json_sha256(
            [row["row_sha256"] for row in cost_rows],
            namespace="task035e.structural-cost-row-catalog.v1",
        ),
        "closure": {
            name: {
                "expected": value,
                "apportioned": (
                    value - 8
                    if name == "estimated_added_solver_peak_bytes"
                    else value
                ),
                "unallocated": (
                    8
                    if name == "estimated_added_solver_peak_bytes"
                    else 0
                ),
                "closed": True,
            }
            for name, value in global_cost.items()
        },
    }
    structural_cost_model = {
        **cost_unsigned,
        "model_sha256": _json_sha256(
            cost_unsigned,
            namespace=STRUCTURAL_COST_MODEL_SCHEMA,
        ),
    }
    unsigned = {
        "schema_version": CELLWISE_DWR_AUTHORITY_SCHEMA,
        "status": "cellwise_59_goal_dwr_pass",
        "pass": True,
        "producer_role": "live_cellwise_residual_adjoint_localizer",
        "source_sha": _SOURCE_SHA,
        "mpi_size": 8,
        "trial_id": "fixture-trial",
        "cycle_index": state.cycle_index,
        "action_kind": action_kind,
        "current_plan_file_sha256": plan_file_sha256,
        "current_plan_content_sha256": _json_sha256(plan),
        "current_state_sha256": state.state_sha256,
        "current_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "current_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
        "current_watchdog_record_sha256": "2" * 64,
        "shadow_watchdog_record_sha256": "3" * 64,
        "current_output_file_sha256": "4" * 64,
        "shadow_output_file_sha256": "5" * 64,
        "current_output_sha256": "4" * 64,
        "shadow_output_sha256": "5" * 64,
        "live_shadow_evidence_file_sha256": "6" * 64,
        "live_shadow_evidence_payload_sha256": "7" * 64,
        "current_goal_values": goal_values,
        "current_goal_sha256": goal_sha,
        "shadow_goal_values": goal_values,
        "shadow_goal_sha256": goal_sha,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        "global_actual_dwr_report": global_dwr,
        "localization": localization,
        "structural_cost_model": structural_cost_model,
        "actual_cellwise_residual_adjoint_pairing": True,
        "signed_not_absolute": True,
        "synthetic": False,
        "reference_derived": False,
        "hidden_auditor_consumed": False,
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "authority_sha256": _json_sha256(
            unsigned,
            namespace=CELLWISE_DWR_AUTHORITY_SCHEMA,
        ),
    }


def _inputs(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
    *,
    authority_builder,
) -> tuple[Path, str, Path, str, object]:
    plan, state = initial
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    authority = authority_builder(
        plan=plan,
        plan_file_sha256=plan_sha,
        state=state,
    )
    authority_path = tmp_path / "dwr-authority.json"
    authority_sha = _write_private(authority_path, authority)
    return plan_path, plan_sha, authority_path, authority_sha, state


def test_global_dwr_without_cellwise_partition_is_controlled_negative(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    plan, state = initial
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    dwr_path = tmp_path / "global-dwr.json"
    dwr_sha = _write_private(dwr_path, _global_dwr(state=state))
    output = tmp_path / "marking.json"

    receipt = produce_goal_marking(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        dwr_authority_path=dwr_path,
        dwr_authority_file_sha256=dwr_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        output_path=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert receipt.status == "goal_marking_controlled_negative"
    assert receipt.classification == "CELLWISE_DWR_EVIDENCE_MISSING"
    assert receipt.canonical_target_ids == ()
    assert payload["canonical_target_ids"] == []
    assert payload["selected_signed_dwr_delta"] is None
    assert payload["selected_signed_dwr_delta_sha256"] is None
    assert payload["transition_producer_arguments"] is None
    assert payload["blocker"]["code"] == "CELLWISE_DWR_EVIDENCE_MISSING"
    assert len(payload["blocker"]["missing_evidence"]) == 4
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert _file_sha256(output) == receipt.file_sha256


def test_cellwise_equal_weight_doerfler_targets_feed_transition_producer(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    plan_path, plan_sha, authority_path, authority_sha, state = _inputs(
        tmp_path,
        initial,
        authority_builder=_cellwise_authority,
    )
    output = tmp_path / "marking.json"
    receipt = produce_goal_marking(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        dwr_authority_path=authority_path,
        dwr_authority_file_sha256=authority_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        output_path=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert receipt.status == "goal_marking_targets_selected"
    assert receipt.classification == "REFERENCE_BLIND_LOCAL_MARKING_PASS"
    assert len(receipt.canonical_target_ids) == 1
    assert payload["selected_doerfler_benefit"] >= (
        payload["required_doerfler_benefit"]
    )
    assert payload["transition_preflight"]["pass"] is True
    assert payload["transition_preflight"]["p_down_selected"] is False
    assert payload["transition_producer_arguments"] == {
        "action_kind": "p-up",
        "canonical_target_ids": list(receipt.canonical_target_ids),
    }
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    localized = {
        row["target_id"]: row["signed_dwr_contribution"]
        for row in authority["localization"]["rows"]
    }
    expected_selected_signed = {
        goal_id: sum(
            localized[target_id][goal_id]
            for target_id in receipt.canonical_target_ids
        )
        for goal_id in FORMAL_GOAL_IDS
    }
    assert (
        payload["selected_signed_dwr_delta"]
        == expected_selected_signed
    )
    assert payload["selected_signed_dwr_delta_sha256"] == _json_sha256(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": list(receipt.canonical_target_ids),
            "signed_dwr_delta": expected_selected_signed,
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )
    selected_id = receipt.canonical_target_ids[0]
    selected_key = next(
        key
        for key in state.cell_degree_by_key
        if canonical_hp_cell_target_id(key) == selected_id
    )
    assert state.cell_degree_by_key[selected_key] == 4

    transition = write_transition_bundle(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        source_sha=_SOURCE_SHA,
        action_kind=payload["transition_producer_arguments"]["action_kind"],
        canonical_target_ids=payload[
            "transition_producer_arguments"
        ]["canonical_target_ids"],
        action_path=tmp_path / "action.json",
        next_plan_path=tmp_path / "next-plan.json",
    )
    action = json.loads(transition.action_path.read_text(encoding="utf-8"))
    assert action["canonical_target_ids"] == [selected_id]
    assert action["kind"] == "p-up"


def test_marking_is_byte_deterministic_and_canonical(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    plan_path, plan_sha, authority_path, authority_sha, state = _inputs(
        tmp_path,
        initial,
        authority_builder=_cellwise_authority,
    )
    paths = (tmp_path / "first.json", tmp_path / "second.json")
    receipts = [
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=authority_path,
            dwr_authority_file_sha256=authority_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=path,
            doerfler_theta=1.0,
        )
        for path in paths
    ]
    assert paths[0].read_bytes() == paths[1].read_bytes()
    assert receipts[0].marking_sha256 == receipts[1].marking_sha256
    selected_keys = tuple(
        sorted(
            key
            for key in state.cell_degree_by_key
            if canonical_hp_cell_target_id(key)
            in set(receipts[0].canonical_target_ids)
        )
    )
    assert len(selected_keys) == 2
    assert receipts[0].canonical_target_ids == tuple(
        canonical_hp_cell_target_id(key) for key in selected_keys
    )


def test_below_budget_signal_selects_verification_only_fallback(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    def builder(**kwargs):
        return _cellwise_authority(**kwargs, eta=0.0)

    plan_path, plan_sha, authority_path, authority_sha, _state = _inputs(
        tmp_path,
        initial,
        authority_builder=builder,
    )
    output = tmp_path / "no-signal.json"
    receipt = produce_goal_marking(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        dwr_authority_path=authority_path,
        dwr_authority_file_sha256=authority_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        output_path=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert receipt.classification == "REFERENCE_BLIND_VERIFICATION_ONLY"
    assert payload["status"] == "goal_marking_verification_only_selected"
    assert len(payload["canonical_target_ids"]) == 1
    assert set(payload["selected_signed_dwr_delta"]) == set(
        FORMAL_GOAL_IDS
    )
    assert isinstance(payload["selected_signed_dwr_delta_sha256"], str)
    assert payload["blocker"] is None
    assert payload["global_maximum_normalized_signed_dwr"] == 0.0


def test_h_refine_marking_feeds_transition_producer(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    def builder(**kwargs):
        return _cellwise_authority(**kwargs, action_kind="h-refine")

    plan_path, plan_sha, authority_path, authority_sha, _state = _inputs(
        tmp_path,
        initial,
        authority_builder=builder,
    )
    output = tmp_path / "h-marking.json"
    receipt = produce_goal_marking(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        dwr_authority_path=authority_path,
        dwr_authority_file_sha256=authority_sha,
        source_sha=_SOURCE_SHA,
        action_kind="h-refine",
        output_path=output,
    )
    assert receipt.canonical_target_ids
    transition = write_transition_bundle(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        source_sha=_SOURCE_SHA,
        action_kind="h-refine",
        canonical_target_ids=receipt.canonical_target_ids,
        action_path=tmp_path / "h-action.json",
        next_plan_path=tmp_path / "h-next-plan.json",
    )
    action = json.loads(transition.action_path.read_text(encoding="utf-8"))
    assert action["kind"] == "h-refine"
    assert action["maximum_level"] == 2


@pytest.mark.parametrize(
    ("builder", "match"),
    (
        (
            lambda **kwargs: _cellwise_authority(
                **kwargs,
                contribution_scale=2.0,
            ),
            "do not close global eta",
        ),
        (
            lambda **kwargs: _cellwise_authority(
                **kwargs,
                omit_last_row=True,
            ),
            "cover every current leaf",
        ),
    ),
)
def test_cellwise_partition_fails_closed_without_publishing(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
    builder,
    match: str,
) -> None:
    plan_path, plan_sha, authority_path, authority_sha, _state = _inputs(
        tmp_path,
        initial,
        authority_builder=builder,
    )
    output = tmp_path / "must-not-exist.json"
    with pytest.raises(GoalMarkingError, match=match):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=authority_path,
            dwr_authority_file_sha256=authority_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=output,
        )
    assert not output.exists()


def test_tampered_cellwise_authority_hash_is_rejected(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    plan, state = initial
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    authority = _cellwise_authority(
        plan=plan,
        plan_file_sha256=plan_sha,
        state=state,
    )
    authority["current_output_sha256"] = "f" * 64
    authority_path = tmp_path / "tampered-authority.json"
    authority_sha = _write_private(authority_path, authority)

    with pytest.raises(GoalMarkingError, match="authority SHA-256 mismatch"):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=authority_path,
            dwr_authority_file_sha256=authority_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=tmp_path / "must-not-exist.json",
        )


def test_reference_leak_and_non_private_input_are_rejected(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    plan, state = initial
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    leaking = _global_dwr(state=state)
    leaking["hidden_reference_values"] = {"R": 0.5}
    leaking_path = tmp_path / "leaking.json"
    leaking_sha = _write_private(leaking_path, leaking)

    with pytest.raises(GoalMarkingError, match="forbidden"):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=leaking_path,
            dwr_authority_file_sha256=leaking_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=tmp_path / "unused.json",
        )

    clean_path = tmp_path / "public-mode.json"
    clean_sha = _write_private(clean_path, _global_dwr(state=state))
    clean_path.chmod(0o644)
    with pytest.raises(GoalMarkingError, match="mode 0600"):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=clean_path,
            dwr_authority_file_sha256=clean_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=tmp_path / "also-unused.json",
        )


def test_refuses_overwrite_and_p_down_lane(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
) -> None:
    plan, state = initial
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    dwr_path = tmp_path / "global-dwr.json"
    dwr_sha = _write_private(dwr_path, _global_dwr(state=state))
    output = tmp_path / "immutable.json"
    output.write_text("keep", encoding="utf-8")
    before = output.read_bytes()

    with pytest.raises(FileExistsError, match="overwrite"):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=dwr_path,
            dwr_authority_file_sha256=dwr_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=output,
        )
    assert output.read_bytes() == before
    with pytest.raises(GoalMarkingError, match="p-up or h-refine"):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=dwr_path,
            dwr_authority_file_sha256=dwr_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-down",
            output_path=tmp_path / "p-down.json",
        )


def test_cli_writes_machine_readable_controlled_negative(
    tmp_path: Path,
    initial: tuple[dict[str, object], object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan, state = initial
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    dwr_path = tmp_path / "global-dwr.json"
    dwr_sha = _write_private(dwr_path, _global_dwr(state=state))
    output = tmp_path / "cli-marking.json"

    code = main(
        [
            "--current-plan",
            str(plan_path),
            "--current-plan-sha256",
            plan_sha,
            "--dwr-authority",
            str(dwr_path),
            "--dwr-authority-sha256",
            dwr_sha,
            "--verified-clean-sha",
            _SOURCE_SHA,
            "--action-kind",
            "p-up",
            "--output",
            str(output),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)
    assert code == 0
    assert stdout["status"] == "completed"
    assert stdout["artifact_status"] == (
        "goal_marking_controlled_negative"
    )
    assert stdout["classification"] == "CELLWISE_DWR_EVIDENCE_MISSING"
    assert output.is_file()
