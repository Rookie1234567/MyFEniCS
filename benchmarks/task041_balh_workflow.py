"""Narrow Task041 side-BAL_H profile and packet contract helpers.

This module owns only the new profile identity and command boundary.  Both
BAL_H consumer routes run through the reviewed Task041 worker; the candidate
entry point remains a thin delegation to that worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.io.input_validation import (
    TASK041_BALH_2NM_CELL_CONDENSED_MODEL_ID,
    TASK041_BALH_2NM_MODEL_ID,
    TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID,
    TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID,
    TASK041_BALH_CANDIDATE_MODEL_IDS,
    TASK041_BALH_MPI_SIZE,
    TASK041_BALH_TRANSFER_OPTIMIZATION_PROFILE,
    TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID,
    TASK041_BALH_W0P7NM_P6_PILOT_P4_TARGET_SCOPE,
    task041_balh_case,
    task041_balh_profile_errors,
    task041_balh_service_contract,
)
from src.io.resolved_config import resolved_config_sha256

TASK041_BALH_MODE_PREP_PROFILE = "task041.side_balh.mode_prep.v1"
TASK041_BALH_MODE_PREP_PHASE = "mode-prep"
TASK041_BALH_EXACT_CONSUMER_PROFILE = "task041.side_balh.exact_consumer.v1"
TASK041_BALH_EXACT_CONSUMER_SCHEMA = "task041.side_balh.exact_consumer.v1"
TASK041_BALH_CANDIDATE_CONSUMER_PROFILE = "task041.side_balh.candidate_consumer.v1"
TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA = "task041.side_balh.candidate_consumer.v1"
TASK041_BALH_CANDIDATE_PHASE = "candidate-consumer"
TASK041_BALH_CONSUMER_PHASE = "consumer"
TASK041_BALH_5NM_CANDIDATE_MODEL_ID = (
    "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8"
)
TASK041_BALH_2NM_CANDIDATE_MODEL_ID = TASK041_BALH_2NM_MODEL_ID
TASK041_BALH_TIME_STOP_OVERRIDE_REASON = (
    "user_authorized_single_candidate_time_override"
)
TASK041_SCHUR_SPEED_V2_PROFILE = "task041_schur_speed_v2"
TASK041_SCHUR_SPEED_V2_WARNING_FRACTION = 0.90
TASK041_SCHUR_SPEED_V2_S0_S1_S3_BUDGET_SECONDS = 21600.0
TASK041_SCHUR_SPEED_V2_S2_BUDGET_SECONDS = 7200.0
TASK041_SCHUR_SPEED_V2_S4_BUDGET_SECONDS = 172800.0
TASK041_SCHUR_SPEED_V2_BATCH_BUDGET_SECONDS = 201600.0
_TASK041_SCHUR_SPEED_V2_MEMORY_CAPS = {
    "task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8": 9159106560,
    "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8": 53221163008,
}
_TASK041_SCHUR_SPEED_V2_ACTIVE_PHASES = {
    "task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8": "S2",
    "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8": "S4",
}
TASK041_SCHUR_SPEED_V2_LEDGER_NAME = (
    "task041_schur_speed_v2_compute_wall_ledger.json"
)
TASK041_REPRESENTATIVE_RHS_SCOPE = "representative_rhs"
TASK041_SEQUENTIAL_COMPONENT_SCHEDULE = "sequential_component"
TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE = "common_layout_equivalence"
TASK041_P4_BACKEND_PAIR_MODE = "p4_backend_pair"
TASK041_P4_BACKEND_PAIR_CONTRACT_KIND = "task041_fixed_eight_rhs_p4_backend_pair"
TASK041_P4_REFINEMENT_TARGET_TOLERANCE = 5.0e-13
TASK041_P4_REGISTERED_5NM_TARGET_SCOPE = (
    "registered_5nm_cell_condensed_formal_consumer_target"
)
TASK041_P4_REGISTERED_2NM_TARGET_SCOPE = (
    "registered_2nm_cell_condensed_formal_consumer_target"
)
TASK041_P4_W0P7_PILOT_TARGET_SCOPE = (
    TASK041_BALH_W0P7NM_P6_PILOT_P4_TARGET_SCOPE
)
TASK041_V8_SWAP_OBSERVE_CONTINUE = "task041_v8_swap_observe_continue"
TASK041_V8_REVIEW_PATH = (
    "docs/task041_mpi1_shortwave_hybrid_capacity/review_report_v8.md"
)
TASK041_REPRESENTATIVE_RHS_SCHEMA = "task041.representative_rhs_manifest.v1"
TASK041_REPRESENTATIVE_RHS_COUNT = 8
TASK041_REPRESENTATIVE_RHS_MODE_COUNT = 480
_TASK041_REPRESENTATIVE_RHS_EXPECTED = (
    ("bottom", "positive", 227, 207, 207),
    ("bottom", "positive", 35, 15, 15),
    ("bottom", "negative", 691, 671, 191),
    ("bottom", "negative", 513, 493, 13),
    ("top", "positive", 330, 310, 310),
    ("top", "positive", 32, 12, 12),
    ("top", "negative", 686, 666, 186),
    ("top", "negative", 513, 493, 13),
)


def task041_p4_registered_formal_target_scope(model_id: str) -> str | None:
    """Return a target scope only for the registered condensed formal cases."""

    return {
        TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID: (
            TASK041_P4_REGISTERED_5NM_TARGET_SCOPE
        ),
        TASK041_BALH_2NM_CELL_CONDENSED_MODEL_ID: (
            TASK041_P4_REGISTERED_2NM_TARGET_SCOPE
        ),
        TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID: (
            TASK041_P4_W0P7_PILOT_TARGET_SCOPE
        ),
    }.get(str(model_id))


def task041_v8_resource_policy_binding(
    model_id: str, policy: str | None
) -> dict[str, Any] | None:
    """Bind the one V8 observe-only swap policy to its Task041 run and review."""

    if policy is None:
        return None
    if policy != TASK041_V8_SWAP_OBSERVE_CONTINUE:
        raise ValueError(f"unsupported Task041 resource policy: {policy}")
    if model_id not in {
        TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID,
        TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID,
        TASK041_BALH_2NM_CELL_CONDENSED_MODEL_ID,
        TASK041_BALH_2NM_CANDIDATE_MODEL_ID,
        TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID,
    } or task041_balh_service_contract(model_id) is None:
        raise ValueError(
            "V8 resource policy is limited to registered Task041 "
            "cell-condensed consumers"
        )
    review_path = Path(__file__).resolve().parents[1] / TASK041_V8_REVIEW_PATH
    if not review_path.is_file():
        raise ValueError("Task041 V8 review source is missing")
    return {
        "policy": policy,
        "model_id": model_id,
        "review_path": TASK041_V8_REVIEW_PATH,
        "review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "swap_semantics": "observe_only_continue",
    }


def task041_is_explicit_p4_backend_pair(
    *,
    model_id: str,
    profile_id: str | None,
    scope: str | None,
    side_setup_schedule: str | None,
    comparison_mode: str | None,
) -> bool:
    """Match only the reviewed old 5 nm fixed-eight-RHS pair tuple."""

    return bool(
        model_id == TASK041_BALH_5NM_CANDIDATE_MODEL_ID
        and profile_id == TASK041_SCHUR_SPEED_V2_PROFILE
        and scope == TASK041_REPRESENTATIVE_RHS_SCOPE
        and side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
        and comparison_mode == TASK041_P4_BACKEND_PAIR_MODE
    )


def task041_is_explicit_top_causal_replay(
    *,
    enabled: bool,
    model_id: str,
    profile_id: str | None,
    scope: str | None,
    side_setup_schedule: str | None,
    comparison_mode: str | None,
) -> bool:
    """Allow the top-only replay only inside the reviewed fixed-eight contract."""

    return bool(
        enabled is True
        and task041_is_explicit_p4_backend_pair(
            model_id=model_id,
            profile_id=profile_id,
            scope=scope,
            side_setup_schedule=side_setup_schedule,
            comparison_mode=comparison_mode,
        )
    )


def task041_p4_refinement_target_binding(
    *,
    model_id: str,
    refinement_target_tolerance: float | None,
    p4_backend_pair_side: str | None,
    profile_id: str | None = None,
    scope: str | None = None,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
) -> dict[str, Any] | None:
    """Bind the reviewed target to the registered 5 nm formal or pair path."""

    if p4_backend_pair_side not in {None, "bottom", "top"}:
        raise ValueError("p4_backend_pair_side must be bottom, top, or None")
    if refinement_target_tolerance is None:
        if p4_backend_pair_side is not None:
            raise ValueError("a selected pair side requires the P4 refinement target")
        return None
    if (
        isinstance(refinement_target_tolerance, bool)
        or not isinstance(refinement_target_tolerance, (int, float))
        or float(refinement_target_tolerance)
        != TASK041_P4_REFINEMENT_TARGET_TOLERANCE
    ):
        raise ValueError("only the reviewed P4 target 5e-13 is supported")
    if p4_backend_pair_side is None:
        registered_formal_scope = (
            task041_p4_registered_formal_target_scope(model_id)
        )
        registered_cell_condensed_formal = (
            registered_formal_scope is not None
            and profile_id is None
            and scope is None
            and side_setup_schedule is None
            and comparison_mode is None
        )
        v2_candidate_formal = (
            model_id == TASK041_BALH_5NM_CANDIDATE_MODEL_ID
            and profile_id == TASK041_SCHUR_SPEED_V2_PROFILE
            and scope is None
            and side_setup_schedule is None
            and comparison_mode is None
        )
        if not (registered_cell_condensed_formal or v2_candidate_formal):
            raise ValueError(
                "the formal P4 target is limited to a registered cell-condensed consumer"
            )
        return {
            "scope": (
                registered_formal_scope
                if registered_cell_condensed_formal
                else "registered_5nm_formal_consumer_target"
            ),
            "tolerance": TASK041_P4_REFINEMENT_TARGET_TOLERANCE,
            "selected_side": None,
        }
    if not task041_is_explicit_p4_backend_pair(
        model_id=model_id,
        profile_id=profile_id,
        scope=scope,
        side_setup_schedule=side_setup_schedule,
        comparison_mode=comparison_mode,
    ):
        raise ValueError(
            "the selected-side P4 target requires the explicit 5 nm representative fixed-eight pair"
        )
    return {
        "scope": "fixed_eight_rhs_selected_side_common_input_diagnostic",
        "tolerance": TASK041_P4_REFINEMENT_TARGET_TOLERANCE,
        "selected_side": p4_backend_pair_side,
    }


def task041_p4_backend_pair_identity(
    *,
    model_id: str,
    profile_id: str | None,
    scope: str | None,
    side_setup_schedule: str | None,
    comparison_mode: str | None,
    rhs_probe_binding: Mapping[str, Any],
) -> dict[str, Any]:
    if not task041_is_explicit_p4_backend_pair(
        model_id=model_id,
        profile_id=profile_id,
        scope=scope,
        side_setup_schedule=side_setup_schedule,
        comparison_mode=comparison_mode,
    ):
        raise ValueError("incomplete Task041 fixed-eight-RHS backend-pair identity")
    path = rhs_probe_binding.get("path")
    manifest_sha256 = rhs_probe_binding.get("sha256")
    if (
        not isinstance(path, str)
        or not Path(path).is_absolute()
        or not _valid_sha(manifest_sha256, 64)
    ):
        raise ValueError("backend-pair identity requires its bound RHS manifest")
    return {
        "contract_kind": TASK041_P4_BACKEND_PAIR_CONTRACT_KIND,
        "model_id": model_id,
        "profile_id": profile_id,
        "scope": scope,
        "side_setup_schedule": side_setup_schedule,
        "comparison_mode": comparison_mode,
        "rhs_manifest_path": path,
        "rhs_manifest_sha256": manifest_sha256,
        "rhs_count": TASK041_REPRESENTATIVE_RHS_COUNT,
    }


def task041_validate_p4_backend_pair_identity(
    identity: Mapping[str, Any],
    *,
    outer_profile_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(identity, Mapping):
        raise TypeError("fixed-eight-RHS backend-pair identity must be a mapping")
    try:
        expected = task041_p4_backend_pair_identity(
            model_id=identity["model_id"],
            profile_id=identity["profile_id"],
            scope=identity["scope"],
            side_setup_schedule=identity["side_setup_schedule"],
            comparison_mode=identity["comparison_mode"],
            rhs_probe_binding={
                "path": identity["rhs_manifest_path"],
                "sha256": identity["rhs_manifest_sha256"],
            },
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid fixed-eight-RHS backend-pair identity") from exc
    if dict(identity) != expected:
        raise ValueError("fixed-eight-RHS backend-pair identity is not canonical")
    if outer_profile_contract is not None and any(
        outer_profile_contract.get(key) != expected[key]
        for key in ("model_id", "profile_id", "scope")
    ):
        raise ValueError("outer profile contract does not match pair identity")
    return expected


def task041_review_v5_ledger_path(repository_root: str | Path) -> Path:
    """Resolve the canonical V5 path from the existing registered service contract."""

    contract = task041_balh_service_contract(
        TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID
    )
    ledger = contract.get("ledger") if isinstance(contract, Mapping) else None
    relative = ledger.get("path") if isinstance(ledger, Mapping) else None
    if (
        not isinstance(relative, str)
        or ledger.get("schema") != "task041.review_v5.r1_load_ledger.v1"
    ):
        raise ValueError("registered Task041 V5 ledger path is unavailable")
    return (Path(repository_root) / relative).resolve()


def task041_schur_speed_v2_contract(
    model_id: str,
    *,
    scope: str | None = None,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
    top_causal_replay: bool = False,
    p4_correction_replay: bool = False,
    p4_response_correction_steps: int = 0,
    p4_refinement_target_tolerance: float | None = None,
    p4_backend_pair_side: str | None = None,
) -> dict[str, Any]:
    """Return the explicit S1/S2/S3/S4 budget contract for one candidate."""

    case = _require_case(model_id)
    if model_id not in TASK041_BALH_CANDIDATE_MODEL_IDS or case["route"] != "balh":
        raise ValueError("task041_schur_speed_v2 requires a BAL_H candidate")
    if case.get("p4_inverse_backend") == "cell_condensed":
        raise ValueError(
            "task041_schur_speed_v2 is not a public contract for cell-condensed cases"
        )
    if scope not in {None, TASK041_REPRESENTATIVE_RHS_SCOPE}:
        raise ValueError(f"unsupported Task041 performance scope: {scope!r}")
    if side_setup_schedule not in {None, TASK041_SEQUENTIAL_COMPONENT_SCHEDULE}:
        raise ValueError(
            f"unsupported Task041 side setup schedule: {side_setup_schedule!r}"
        )
    if (
        side_setup_schedule is not None
        and scope != TASK041_REPRESENTATIVE_RHS_SCOPE
    ):
        raise ValueError(
            "sequential_component requires the representative_rhs scope"
        )
    if comparison_mode not in {
        None,
        TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
        TASK041_P4_BACKEND_PAIR_MODE,
    }:
        raise ValueError(
            f"unsupported Task041 comparison mode: {comparison_mode!r}"
        )
    p4_backend_pair = task041_is_explicit_p4_backend_pair(
        model_id=model_id,
        profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
        scope=scope,
        side_setup_schedule=side_setup_schedule,
        comparison_mode=comparison_mode,
    )
    if comparison_mode == TASK041_P4_BACKEND_PAIR_MODE and not p4_backend_pair:
        raise ValueError(
            "p4_backend_pair requires the complete 5 nm representative_rhs "
            "sequential_component fixed-eight-RHS contract"
        )
    if (
        isinstance(p4_response_correction_steps, bool)
        or not isinstance(p4_response_correction_steps, int)
        or p4_response_correction_steps not in (0, 1)
    ):
        raise ValueError("P4 response correction steps must be 0 or 1")
    if p4_response_correction_steps and (
        not top_causal_replay
        or p4_correction_replay
        or not p4_backend_pair
    ):
        raise ValueError(
            "P4 response correction requires the explicit 5 nm top-causal "
            "p4_backend_pair diagnostic and cannot be combined with frozen-Q replay"
        )
    p4_refinement_target_binding: dict[str, Any] | None = None
    if p4_refinement_target_tolerance is not None or p4_backend_pair_side is not None:
        if top_causal_replay or p4_correction_replay or p4_response_correction_steps:
            raise ValueError(
                "the P4 refinement target is mutually exclusive with existing causal/fixed-step diagnostics"
            )
        p4_refinement_target_binding = task041_p4_refinement_target_binding(
            model_id=model_id,
            refinement_target_tolerance=p4_refinement_target_tolerance,
            p4_backend_pair_side=p4_backend_pair_side,
            profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
            scope=scope,
            side_setup_schedule=side_setup_schedule,
            comparison_mode=comparison_mode,
        )
    if top_causal_replay and not task041_is_explicit_top_causal_replay(
        enabled=top_causal_replay,
        model_id=model_id,
        profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
        scope=scope,
        side_setup_schedule=side_setup_schedule,
        comparison_mode=comparison_mode,
    ):
        raise ValueError(
            "top_causal_replay requires the complete 5 nm representative_rhs "
            "sequential_component p4_backend_pair contract"
        )
    if p4_correction_replay and (
        top_causal_replay
        or not task041_is_explicit_top_causal_replay(
            enabled=True,
            model_id=model_id,
            profile_id=TASK041_SCHUR_SPEED_V2_PROFILE,
            scope=scope,
            side_setup_schedule=side_setup_schedule,
            comparison_mode=comparison_mode,
        )
    ):
        raise ValueError(
            "p4_correction_replay requires the explicit 5 nm representative_rhs "
            "sequential_component p4_backend_pair contract and is distinct "
            "from the multi-node top_causal_replay"
        )
    if comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE and (
        model_id != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
        or scope != TASK041_REPRESENTATIVE_RHS_SCOPE
        or side_setup_schedule != TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    ):
        raise ValueError(
            f"{comparison_mode} requires the 5 nm representative_rhs "
            "sequential_component contract"
        )
    try:
        memory_cap = int(_TASK041_SCHUR_SPEED_V2_MEMORY_CAPS[str(model_id)])
    except KeyError as exc:
        raise ValueError(
            "task041_schur_speed_v2 is registered only for the two BAL_H candidates"
        ) from exc
    active_phase = _TASK041_SCHUR_SPEED_V2_ACTIVE_PHASES[str(model_id)]
    phase_budgets = {
        "shared_S0_S1_S3": TASK041_SCHUR_SPEED_V2_S0_S1_S3_BUDGET_SECONDS,
        "S2": TASK041_SCHUR_SPEED_V2_S2_BUDGET_SECONDS,
        "S4": TASK041_SCHUR_SPEED_V2_S4_BUDGET_SECONDS,
    }
    active_budget_group = (
        "shared_S0_S1_S3" if scope == TASK041_REPRESENTATIVE_RHS_SCOPE else active_phase
    )
    ledger = {
        "schema": "task041.compute_wall_ledger.v2",
        "filename": TASK041_SCHUR_SPEED_V2_LEDGER_NAME,
    }
    time_stop = {
        "consumer_enforced": True,
        "disable_time_stop_inherited": False,
        "mutually_exclusive_with": (
            "--task041-balh-candidate-disable-time-stop"
        ),
    }
    contract = {
        "profile_id": TASK041_SCHUR_SPEED_V2_PROFILE,
        "model_id": str(model_id),
        "scope": scope or "formal_consumer",
        "side_setup_schedule": side_setup_schedule,
        "comparison_mode": comparison_mode,
        "budget_group": active_budget_group,
        "memory_cap_bytes": memory_cap,
        "memory_cap_source": "review_report_v2_section_5_explicit_cap",
        "memory_gate_source": "simultaneous_process_tree_rss",
        "warning_fraction": TASK041_SCHUR_SPEED_V2_WARNING_FRACTION,
        "warning_memory_bytes": int(
            memory_cap * TASK041_SCHUR_SPEED_V2_WARNING_FRACTION
        ),
        "swap_limit_bytes": 0,
        "phase_budgets_seconds": phase_budgets,
        "active_consumer_phase": active_budget_group,
        "active_consumer_budget_seconds": phase_budgets[active_budget_group],
        "batch_budget_seconds": TASK041_SCHUR_SPEED_V2_BATCH_BUDGET_SECONDS,
        "producer": {
            "mode": "reused",
            "invocation": "not_run",
            "time_stop_enforced": True,
            "qep": "not_run",
        },
        "time_stop": {
            **time_stop,
        },
        "ledger": ledger,
        "budget_semantics": (
            "S0/S1/S3 share 21600 seconds; S2 and S4 are separate review phases; "
            "the batch value is the cumulative stop budget across these groups"
        ),
    }
    if p4_backend_pair:
        registered_memory_cap = int(contract["memory_cap_bytes"])
        registered_memory_cap_source = str(contract["memory_cap_source"])
        pair_memory_cap = registered_memory_cap
        ledger_contract = task041_balh_service_contract(
            TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID
        )
        v5_ledger = ledger_contract.get("ledger") if ledger_contract is not None else None
        if not isinstance(v5_ledger, Mapping) or not isinstance(
            v5_ledger.get("path"), str
        ):
            raise ValueError("registered Task041 V5 ledger path is unavailable")
        contract.update(
            {
                "registered_memory_cap_bytes": registered_memory_cap,
                "registered_memory_cap_source": registered_memory_cap_source,
                "memory_cap_bytes": pair_memory_cap,
                "memory_cap_source": (
                    "review_report_v2_section_5_explicit_cap"
                ),
                "warning_memory_bytes": int(
                    pair_memory_cap * TASK041_SCHUR_SPEED_V2_WARNING_FRACTION
                ),
                "compute_wall_unlimited": True,
                "contract_kind": TASK041_P4_BACKEND_PAIR_CONTRACT_KIND,
                "time_stop": {
                    **time_stop,
                    "consumer_enforced": False,
                    "consumer_timeout_seconds": None,
                    "scope": "explicit_5nm_fixed_eight_rhs_backend_pair",
                },
                "ledger": dict(v5_ledger),
                "budget_semantics": (
                    "fixed RHS V2 budget fields are historical identity only; "
                    "the pair has no elapsed wall stop"
                ),
            }
        )
    if top_causal_replay:
        contract["top_causal_replay"] = True
    if p4_response_correction_steps:
        contract["p4_response_correction"] = {
            "schema": "task041.p4_response_correction.strategy.v1",
            "requested_steps": 1,
            "scope": "top_manifest_responses",
            "selection": "existing_top_causal_manifest_selection",
            "backends": ["full", "cell_condensed"],
            "max_corrections_per_p4_call": 1,
        }
    if p4_refinement_target_tolerance is not None:
        contract["p4_refinement_target"] = {
            "schema": "task041.p4_refinement_target.strategy.v1",
            "tolerance": float(p4_refinement_target_tolerance),
            "scope": p4_refinement_target_binding["scope"],
            "selected_side": p4_backend_pair_side,
            "max_corrections_per_p4_call": 2,
            "original_gates_unchanged": True,
        }
    if p4_correction_replay:
        contract["p4_correction_replay"] = {
            "schema": "task041.p4_correction_replay.contract.v1",
            "scope": "top_pc1_frozen_q1_q2",
            "max_corrections": 2,
            "pc_action": "not_run",
            "default_path_unchanged": True,
        }
    return contract


def task041_balh_time_stop_override_record(enabled: bool) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "enforced": not bool(enabled),
        "scope": (
            "task041_5nm_balh_candidate_single_invocation"
            if enabled
            else "default_task041_time_contract"
        ),
        "reason": (
            TASK041_BALH_TIME_STOP_OVERRIDE_REASON
            if enabled
            else "default_task041_time_contract"
        ),
        "producer_time_stop_unchanged": True,
    }


def _valid_sha(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def load_task041_representative_rhs_manifest(
    path: str | Path,
) -> dict[str, Any]:
    """Load the one fixed, reviewed eight-RHS probe manifest."""

    manifest_path = Path(path)
    if not manifest_path.is_absolute():
        raise ValueError("representative RHS manifest must be an absolute path")
    raw = manifest_path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise TypeError("representative RHS manifest must be a JSON object")
    if payload.get("schema") != TASK041_REPRESENTATIVE_RHS_SCHEMA:
        raise ValueError("unsupported representative RHS manifest schema")
    if payload.get("scope") != TASK041_REPRESENTATIVE_RHS_SCOPE:
        raise ValueError("representative RHS manifest has the wrong scope")
    if payload.get("model_id") != TASK041_BALH_5NM_CANDIDATE_MODEL_ID:
        raise ValueError("representative RHS probe is limited to the 5 nm BAL_H candidate")
    if payload.get("profile_id") != TASK041_SCHUR_SPEED_V2_PROFILE:
        raise ValueError("representative RHS probe requires task041_schur_speed_v2")
    if int(payload.get("mode_count", -1)) != TASK041_REPRESENTATIVE_RHS_MODE_COUNT:
        raise ValueError("representative RHS probe requires 480 modes per direction")
    if int(payload.get("mpi_size", -1)) != TASK041_BALH_MPI_SIZE:
        raise ValueError("representative RHS probe requires MPI8")
    budget = payload.get("budget")
    if not isinstance(budget, Mapping) or (
        budget.get("group") != "shared_S0_S1_S3"
        or float(budget.get("phase_limit_seconds", -1.0))
        != TASK041_SCHUR_SPEED_V2_S0_S1_S3_BUDGET_SECONDS
        or float(budget.get("batch_limit_seconds", -1.0))
        != TASK041_SCHUR_SPEED_V2_BATCH_BUDGET_SECONDS
        or int(budget.get("memory_cap_bytes", -1))
        != _TASK041_SCHUR_SPEED_V2_MEMORY_CAPS[
            TASK041_BALH_5NM_CANDIDATE_MODEL_ID
        ]
        or budget.get("swap_limit_bytes") != 0
        or budget.get("time_stop_override") is not False
    ):
        raise ValueError("representative RHS budget binding is invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != TASK041_REPRESENTATIVE_RHS_COUNT:
        raise ValueError("representative RHS manifest must contain exactly eight entries")
    signature = tuple(
        (
            str(entry["side"]),
            str(entry["branch"]),
            int(entry["audit_index"]),
            int(entry["formal_column"]),
            int(entry["branch_ordinal"]),
        )
        for entry in entries
    )
    if signature != _TASK041_REPRESENTATIVE_RHS_EXPECTED:
        raise ValueError("representative RHS entries do not match the reviewed fixed order")
    packet_binding = payload.get("packet_binding")
    if not isinstance(packet_binding, Mapping) or not _valid_sha(
        packet_binding.get("packet_manifest_sha256"), 64
    ) or not _valid_sha(packet_binding.get("packet_identity_sha256"), 64):
        raise ValueError("representative RHS packet binding is incomplete")
    source_audit = payload.get("source_audit")
    if not isinstance(source_audit, Mapping) or not _valid_sha(
        source_audit.get("rhs_audit_sha256"), 64
    ) or not _valid_sha(source_audit.get("source_git_sha"), 40):
        raise ValueError("representative RHS source audit binding is incomplete")
    return {
        **dict(payload),
        "path": str(manifest_path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _require_case(model_id: str) -> Mapping[str, Any]:
    case = task041_balh_case(model_id)
    if case is None:
        raise ValueError(f"unknown Task041 side BAL_H model: {model_id!r}")
    return case


def task041_balh_route(model_id: str) -> str:
    """Return the explicit consumer route encoded by one registered model."""

    return str(_require_case(model_id)["route"])


def task041_balh_transfer_optimization_profile(
    model_id: str,
) -> str | None:
    """Return the case-owned low-level transfer switch, if one is registered.

    This value is consumed only by the side inverse/owner-transfer builder.
    It is deliberately separate from the public ``task041_schur_speed_v2``
    budget contract and therefore does not activate that contract by itself.
    """

    profile = _require_case(model_id).get("transfer_optimization_profile")
    if profile not in {None, TASK041_BALH_TRANSFER_OPTIMIZATION_PROFILE}:
        raise ValueError(
            f"unsupported Task041 transfer optimization profile: {profile}"
        )
    return profile


def task041_balh_cpu_list(model_id: str) -> str:
    """Return the explicit CPU list for the registered BAL_H case."""

    return str(_require_case(model_id).get("cpu_set", "0-7"))


def task041_balh_registered_rank_cpu_map(model_id: str) -> tuple[int, ...]:
    """Expand the registered MPI8 CPU range as its historical default map."""

    cpu_set = task041_balh_cpu_list(model_id)
    bounds = cpu_set.split("-")
    if len(bounds) != 2 or not all(value.isdecimal() for value in bounds):
        raise ValueError("registered Task041 CPU set must be one numeric range")
    first, last = (int(value) for value in bounds)
    if first < 0 or last < first:
        raise ValueError("registered Task041 CPU range is invalid")
    cpus = tuple(range(first, last + 1))
    from benchmarks.task041_rank_numa import normalize_expected_rank_cpus

    try:
        return normalize_expected_rank_cpus(
            cpus, expected_mpi_size=TASK041_BALH_MPI_SIZE
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "registered Task041 CPU range must provide one CPU for each MPI8 rank"
        ) from exc


def task041_parse_expected_rank_cpus(value: str | Sequence[int] | None) -> tuple[int, ...] | None:
    """Parse a public comma-separated CPU map without inferring from placement."""

    if value is None:
        return None
    if isinstance(value, str):
        tokens = value.split(",")
        if not tokens or any(not token.strip().isdecimal() for token in tokens):
            raise ValueError("expected rank CPUs must be comma-separated nonnegative integers")
        parsed: Sequence[int] = tuple(int(token.strip()) for token in tokens)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        parsed = value
    else:
        raise TypeError("expected rank CPUs must be a sequence of integers")
    from benchmarks.task041_rank_numa import normalize_expected_rank_cpus

    try:
        return normalize_expected_rank_cpus(
            parsed, expected_mpi_size=TASK041_BALH_MPI_SIZE
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid expected rank CPU map: {exc}") from exc


def task041_fixed_h6_modal_gmres_binding(
    model_id: str,
    *,
    enabled: bool,
    candidate: bool,
    mpi_size: int,
    mode_count: int,
    p4_inverse_backend: str | None,
    p4_refinement_target_tolerance: float | None,
    task041_resource_policy: str | None,
    expected_rank_cpus: Sequence[int] | None = None,
    modal_feedback_method: str | None = None,
    modal_solver_policy: str | None = None,
) -> dict[str, Any] | None:
    """Bind the default-off fixed-H6 route to registered V9 cases."""

    if not isinstance(enabled, bool):
        raise TypeError("fixed_h6_modal_gmres_research must be a boolean")
    if modal_feedback_method not in (None, "fixed_physical_balh_once"):
        raise ValueError("unsupported Task041 modal feedback method")
    if modal_feedback_method is not None and not enabled:
        raise ValueError(
            "modal_feedback_method requires explicit fixed-H6 research opt-in"
        )
    if modal_solver_policy not in (
        None,
        "task041_v12_bounded_inexact_modal",
        "task041_v12_bounded_inexact_modal_once_backup",
    ):
        raise ValueError("unsupported Task041 modal solver policy")
    if modal_solver_policy is not None and (
        not enabled
        or modal_feedback_method is not None
        or model_id != TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID
    ):
        raise ValueError(
            "the V12 modal policy requires pure fixed-H6 on the registered W0.7 pilot"
        )
    if not enabled:
        if model_id == TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID:
            raise ValueError("the W0.7 reduced pilot requires fixed-H6 research")
        if expected_rank_cpus is not None:
            raise ValueError(
                "expected_rank_cpus is only accepted with fixed-H6 research"
            )
        return None
    allowed_targets = {
        TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID: None,
        TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID: (
            TASK041_P4_REFINEMENT_TARGET_TOLERANCE
        ),
        TASK041_BALH_2NM_CELL_CONDENSED_MODEL_ID: (
            TASK041_P4_REFINEMENT_TARGET_TOLERANCE
        ),
        TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID: (
            TASK041_P4_REFINEMENT_TARGET_TOLERANCE
        ),
    }
    if model_id not in allowed_targets:
        raise ValueError(
            "fixed-H6 research is limited to registered Task041 "
            "cell-condensed cases"
        )
    if modal_feedback_method is not None and (
        model_id != TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID
    ):
        raise ValueError(
            "fixed_physical_balh_once is limited to the registered W0.7 pilot"
        )
    case = task041_balh_case(model_id)
    service_contract = task041_balh_service_contract(model_id)
    expected_target = allowed_targets[model_id]
    actual_target = p4_refinement_target_tolerance
    target_matches = (
        actual_target is None
        if expected_target is None
        else isinstance(actual_target, (int, float))
        and not isinstance(actual_target, bool)
        and float(actual_target) == expected_target
    )
    if (
        candidate is not True
        or case is None
        or case.get("route") != "balh"
        or case.get("p4_inverse_backend") != "cell_condensed"
        or p4_inverse_backend != "cell_condensed"
        or service_contract is None
        or isinstance(mpi_size, bool)
        or mpi_size != TASK041_BALH_MPI_SIZE
        or isinstance(mode_count, bool)
        or mode_count != case.get("mode_count")
        or task041_resource_policy != TASK041_V8_SWAP_OBSERVE_CONTINUE
        or not target_matches
    ):
        target_label = "None" if expected_target is None else "5e-13"
        raise ValueError(
            f"fixed-H6 research requires the registered candidate case, MPI8, "
            f"cell_condensed P4 and target {target_label}"
        )
    if expected_rank_cpus is None:
        raise ValueError(
            "fixed-H6 research requires an explicit frozen expected_rank_cpus map"
        )
    supplied_cpus = task041_parse_expected_rank_cpus(expected_rank_cpus)
    if supplied_cpus is None:
        raise ValueError(
            "fixed-H6 research requires an explicit frozen expected_rank_cpus map"
        )
    binding = {
        "method": "fixed_h6_modal_gmres_research",
        "model_id": model_id,
        "wavelength_nm": float(case["wavelength_nm"]),
        "mesh_target_nm": float(case["mesh_target_nm"]),
        "mode_count": int(case["mode_count"]),
        "mpi_size": TASK041_BALH_MPI_SIZE,
        "p4_inverse_backend": "cell_condensed",
        "p4_refinement_target_tolerance": expected_target,
        "p4_refinement_target_scope": (
            task041_p4_registered_formal_target_scope(model_id)
        ),
        "task041_resource_policy": TASK041_V8_SWAP_OBSERVE_CONTINUE,
        "expected_rank_cpus": list(supplied_cpus),
        "rank_cpu_map_source": "explicit_frozen_expected_rank_cpus",
    }
    if modal_feedback_method is not None:
        binding["modal_feedback_method"] = modal_feedback_method
    if modal_solver_policy is not None:
        from src.solvers.hybrid_fem_modal_block_ldu import (
            resolve_task041_modal_solver_policy,
        )

        binding["modal_solver_policy"] = resolve_task041_modal_solver_policy(
            modal_solver_policy
        )
    return binding


def task041_fixed_h6_packet_source_binding(
    fixed_h6_binding: Mapping[str, Any] | None,
    *,
    producer_packet_root: str | Path | None,
    legacy_native_packet_descriptor: str | Path | None,
) -> dict[str, Any] | None:
    """Bind one registered fixed-H6 source route without validating packet shards."""

    if fixed_h6_binding is None:
        return None
    if not isinstance(fixed_h6_binding, Mapping) or fixed_h6_binding.get(
        "method"
    ) != "fixed_h6_modal_gmres_research":
        raise ValueError("fixed-H6 packet source requires its registered binding")
    producer_source = producer_packet_root is not None
    legacy_source = legacy_native_packet_descriptor is not None
    model_id = str(fixed_h6_binding.get("model_id", ""))
    if model_id == TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID:
        case = task041_balh_case(model_id)
        if (
            not isinstance(case, Mapping)
            or case.get("producer_mode") != "fresh"
            or legacy_source
        ):
            raise ValueError(
                "the registered W0.7 pilot allows only its fresh producer or a validated producer root"
            )
        if producer_source:
            root = Path(producer_packet_root).resolve()
            root_files = {
                "mode_prep_summary": root / "mode_prep_summary.json",
                "packet_identity": root / "packet_identity.json",
                "selected_mode_packet_manifest": (
                    root / "selected_mode_packet" / "manifest.json"
                ),
            }
            parent_files = {
                "supervisor_summary": root.parent / "supervisor_summary.json",
                "selected_mode_manifest": root.parent / "selected_mode_manifest.json",
            }
            bound_files: dict[str, dict[str, str]] = {}
            for name, path in {**root_files, **parent_files}.items():
                resolved_path = path.resolve()
                if not resolved_path.is_file():
                    raise ValueError(
                        "the W0.7 fresh producer or validated producer root is "
                        f"incomplete; missing {name}: {resolved_path}"
                    )
                bound_files[name] = {
                    "path": str(resolved_path),
                    "sha256": hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
                }
            return {
                "source_type": "validated_producer_root",
                "producer_root": str(root),
                "files": bound_files,
            }
        return {"source_type": "fresh_registered_producer"}
    if producer_source == legacy_source:
        raise ValueError(
            "fixed-H6 research requires exactly one producer root or legacy descriptor"
        )
    if producer_source:
        return None
    if model_id != TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID:
        raise ValueError(
            "fixed-H6 legacy-native packets are limited to the registered 5 nm case"
        )
    descriptor = Path(legacy_native_packet_descriptor).resolve()
    if not descriptor.is_file():
        raise ValueError("fixed-H6 legacy packet descriptor is missing")
    return {
        "source_type": "legacy_native_packet_descriptor",
        "descriptor_path": str(descriptor),
        "descriptor_sha256": hashlib.sha256(descriptor.read_bytes()).hexdigest(),
    }


def task041_fixed_h6_producer_execution_binding(
    packet_source_binding: Mapping[str, Any] | None,
    registered_producer: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Describe W0.7 producer work for this invocation from its bound source route."""

    if not isinstance(packet_source_binding, Mapping) or packet_source_binding.get(
        "source_type"
    ) != "validated_producer_root":
        return None
    if (
        not isinstance(registered_producer, Mapping)
        or registered_producer.get("mode") != "fresh"
        or str(packet_source_binding.get("producer_root", "")) == ""
    ):
        raise ValueError(
            "validated producer-root execution requires the registered fresh W0.7 producer contract"
        )
    return {
        **dict(registered_producer),
        "mode": "reused",
        "invocation": "not_run_in_current_invocation",
        "qep": "not_run_in_current_invocation",
        "source_type": "validated_producer_root",
    }


def task041_balh_membind_node(model_id: str) -> str | None:
    """Return the rank-executable NUMA node binding for explicit V6 cases."""

    node = _require_case(model_id).get("membind_node")
    return None if node is None else str(int(node))


def _physical_contract(normalized: Mapping[str, Any]) -> dict[str, Any]:
    """Project only physical/discrete facts shared by exact and BAL_H lanes."""

    return {
        "geometry": {
            key: normalized["geometry"][key]
            for key in (
                "geometry_kind",
                "period_x_nm",
                "period_y_nm",
                "z_min_nm",
                "z_max_nm",
                "interface_z_nm",
                "air_height_nm",
                "substrate_thickness_nm",
                "grating_width_x_nm",
                "grating_width_y_nm",
                "grating_height_nm",
            )
        },
        "materials": {
            key: normalized["materials"][key]
            for key in (
                "n_air",
                "mu_r",
                "n_substrate",
                "n_grating",
                "substrate_name",
                "grating_name",
            )
        },
        "incidence": {
            key: normalized["incidence"][key]
            for key in (
                "wavelength_nm",
                "grazing_angle_deg",
                "azimuth_deg",
                "polarization",
            )
        },
        "discretization": {
            key: normalized["discretization"][key]
            for key in (
                "nedelec_degree",
                "mesh_target_nm",
                "mesh_cell_type",
                "mesh_spacing_mode",
                "assembly_backend",
                "floquet_constraint_mode",
            )
        },
        "boundary": {
            key: normalized["boundary"][key]
            for key in (
                "use_floquet_x",
                "use_floquet_y",
                "vertical_boundary",
                "scattering_background",
                "dtn_order_policy",
                "dtn_assembly",
                "use_pml",
            )
        },
        "method": {
            key: normalized["method"][key]
            for key in (
                "bottom_interface_nm",
                "top_interface_nm",
                "requested_modes_per_direction",
                "propagation_model",
                "traction_model",
            )
        },
    }


def _task041_balh_external_key_identity(
    normalized: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the consumer's canonical exterior-mode inventory identity."""

    from benchmarks.task041_exact_side_workflow import (
        _inventory_from_payload,
        _task041_canonical_mode_keys_sha256,
    )

    keys, count = _inventory_from_payload(normalized)
    return {
        "count": count,
        "sha256": _task041_canonical_mode_keys_sha256(keys),
    }


def build_task041_balh_packet_identity(
    specification: Any,
    normalized: Mapping[str, Any],
    source_sha: str,
    resolved_sha: str,
) -> dict[str, Any]:
    """Build the new strict MPI8 packet identity without rewriting old schemas."""

    from benchmarks.task039_v4_selected_mode_packet import (
        TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
    )

    failures = tuple(task041_balh_profile_errors(normalized))
    if failures:
        detail = "; ".join(f"{field}: {message}" for field, message in failures)
        raise ValueError("Task041 side BAL_H profile rejected: " + detail)
    model_id = str(normalized["model_id"])
    case = _require_case(model_id)
    if not _valid_sha(source_sha, 40) or not _valid_sha(resolved_sha, 64):
        raise ValueError("BAL_H packet source/resolved identities must be valid SHA values")
    input_sha = str(specification.input_sha256)
    physical_sha = str(specification.physical_model_sha256)
    if not _valid_sha(input_sha, 64) or not _valid_sha(physical_sha, 64):
        raise ValueError("BAL_H packet input/physical identities must be SHA256")
    mode_count = int(case["mode_count"])
    return {
        "schema": TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
        "scope": case["scope"],
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "resolved_sha256": resolved_sha,
        "physical_sha256": physical_sha,
        "wavelength_nm": normalized["incidence"]["wavelength_nm"],
        "model_id": model_id,
        "run_id": normalized["run_id"],
        "comparison_group": normalized["comparison_group"],
        "mesh": {
            "cell_type": normalized["discretization"]["mesh_cell_type"],
            "kind": normalized["method"]["propagation_model"],
            "mesh_target_nm": normalized["discretization"]["mesh_target_nm"],
            "nedelec_degree": normalized["discretization"]["nedelec_degree"],
            "spacing_mode": normalized["discretization"]["mesh_spacing_mode"],
        },
        "mode_count": mode_count,
        "mpi_size": TASK041_BALH_MPI_SIZE,
        "requested_modes_per_direction": mode_count,
        "dtn_order_policy": normalized["boundary"]["dtn_order_policy"],
        "external_keys": _task041_balh_external_key_identity(normalized),
        "cross_section_partition": "input_contiguous_v1",
        "consumer_route": case["route"],
        "physical_contract": _jsonable(_physical_contract(normalized)),
    }


def _mpi8_command(
    python_executable: str | Path,
    phase: str,
    input_path: str | Path,
    packet_manifest: str | Path | None,
    packet_identity: str | Path | None,
    packet_manifest_sha256: str | None,
    run_directory: str | Path,
    source_sha: str,
    packet_producer_source_sha: str | None,
    *,
    module: str,
    packet_origin: str | None = None,
    legacy_native_binding: str | Path | None = None,
    disable_time_stop: bool = False,
    performance_profile: str | None = None,
    task041_rhs_probe_manifest: str | Path | None = None,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
    top_causal_replay: bool = False,
    p4_correction_replay_from: str | Path | None = None,
    p4_response_correction_steps: int = 0,
    p4_refinement_target_tolerance: float | None = None,
    p4_backend_pair_side: str | None = None,
    cpu_list: str = "0-7",
    membind_node: str | None = None,
) -> list[str]:
    command = [
        "mpiexec",
        "-n",
        str(TASK041_BALH_MPI_SIZE),
        "--bind-to",
        "cpu-list:ordered",
        "--cpu-list",
        (
            "1-8"
            if comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
            else cpu_list
        ),
        "--report-bindings",
        str(python_executable),
        "-m",
        module,
        "--worker",
        "--phase",
        phase,
        "--input",
        str(input_path),
        "--run-directory",
        str(run_directory),
        "--source-sha",
        source_sha,
    ]
    if membind_node is not None:
        python_index = command.index(str(python_executable))
        command[python_index:python_index] = [
            "numactl",
            f"--membind={membind_node}",
        ]
    if packet_manifest is not None:
        command.extend(
            [
                "--packet-manifest",
                str(packet_manifest),
                "--packet-identity",
                str(packet_identity),
                "--packet-manifest-sha256",
                str(packet_manifest_sha256),
            ]
        )
    if packet_producer_source_sha is not None:
        if not _valid_sha(packet_producer_source_sha, 40):
            raise ValueError("packet_producer_source_sha must be a lowercase SHA1")
        command.extend(["--packet-producer-source-sha", packet_producer_source_sha])
    if (packet_origin is None) != (legacy_native_binding is None):
        raise ValueError("legacy packet origin and binding must be supplied together")
    if packet_origin is not None:
        command.extend(
            [
                "--packet-origin",
                packet_origin,
                "--legacy-native-binding",
                str(legacy_native_binding),
            ]
        )
    if disable_time_stop:
        command.append("--task041-balh-candidate-disable-time-stop")
    if performance_profile is not None:
        if performance_profile != TASK041_SCHUR_SPEED_V2_PROFILE:
            raise ValueError(
                f"unsupported Task041 performance profile: {performance_profile}"
            )
        command.extend(["--task041-performance-profile", performance_profile])
    if task041_rhs_probe_manifest is not None:
        command.extend(["--task041-rhs-probe", str(task041_rhs_probe_manifest)])
    if side_setup_schedule is not None:
        if (
            module != "benchmarks.task041_balh_workflow"
            or phase != TASK041_BALH_CANDIDATE_PHASE
        ):
            raise ValueError(
                "side setup schedule is limited to the BAL_H candidate worker"
            )
        command.extend(["--task041-side-setup-schedule", side_setup_schedule])
    if comparison_mode is not None:
        if (
            module != "benchmarks.task041_balh_workflow"
            or phase != TASK041_BALH_CANDIDATE_PHASE
            or comparison_mode
            not in {
                TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
                TASK041_P4_BACKEND_PAIR_MODE,
            }
        ):
            raise ValueError(
                "comparison mode is limited to the BAL_H candidate worker"
            )
        command.extend(["--task041-comparison-mode", comparison_mode])
    if top_causal_replay:
        command.append("--task041-top-causal-replay")
    if p4_correction_replay_from is not None:
        if (
            module != "benchmarks.task041_balh_workflow"
            or phase != TASK041_BALH_CANDIDATE_PHASE
            or top_causal_replay
        ):
            raise ValueError(
                "P4 correction replay is limited to its distinct BAL_H candidate route"
            )
        command.extend(
            [
                "--task041-p4-correction-replay-from",
                str(p4_correction_replay_from),
            ]
        )
    if (
        isinstance(p4_response_correction_steps, bool)
        or not isinstance(p4_response_correction_steps, int)
        or p4_response_correction_steps not in (0, 1)
    ):
        raise ValueError("P4 response correction steps must be 0 or 1")
    if p4_response_correction_steps:
        if (
            module != "benchmarks.task041_balh_workflow"
            or phase != TASK041_BALH_CANDIDATE_PHASE
            or comparison_mode != TASK041_P4_BACKEND_PAIR_MODE
            or not top_causal_replay
            or p4_correction_replay_from is not None
        ):
            raise ValueError(
                "P4 response correction requires the top-causal fixed-eight pair worker"
            )
        command.extend(
            [
                "--task041-p4-response-correction-steps",
                str(p4_response_correction_steps),
            ]
        )
    if p4_refinement_target_tolerance is not None or p4_backend_pair_side is not None:
        if module != "benchmarks.task041_balh_workflow" or phase != TASK041_BALH_CANDIDATE_PHASE:
            raise ValueError("P4 refinement target requires the Task041 BAL_H candidate worker")
        if p4_refinement_target_tolerance != TASK041_P4_REFINEMENT_TARGET_TOLERANCE:
            raise ValueError("P4 refinement target must be 5e-13")
        if p4_backend_pair_side is None:
            if (
                comparison_mode is not None
                or top_causal_replay
                or p4_correction_replay_from is not None
                or p4_response_correction_steps != 0
            ):
                raise ValueError("formal target cannot combine with pair/replay modes")
        else:
            if (
                comparison_mode != TASK041_P4_BACKEND_PAIR_MODE
                or top_causal_replay
                or p4_correction_replay_from is not None
                or p4_response_correction_steps != 0
                or p4_backend_pair_side not in {"bottom", "top"}
            ):
                raise ValueError("selected-side target requires its separate fixed-eight pair mode")
        command.extend(["--task041-p4-refinement-target-tolerance", "5e-13"])
        if p4_backend_pair_side is not None:
            command.extend(["--task041-p4-backend-pair-side", p4_backend_pair_side])
    return command


def build_task041_balh_mode_prep_command(
    python_executable: str | Path,
    specification: Any,
    run_directory: str | Path,
    source_sha: str,
    *,
    expected_rank_cpus: Sequence[int] | None = None,
) -> list[str]:
    normalized = specification.as_jsonable()
    failures = tuple(task041_balh_profile_errors(normalized))
    if failures:
        detail = "; ".join(f"{field}: {message}" for field, message in failures)
        raise ValueError("Task041 side BAL_H profile rejected: " + detail)
    if normalized["execution"]["mpi_size"] != TASK041_BALH_MPI_SIZE:
        raise ValueError("Task041 side BAL_H mode-prep requires MPI8")
    cpu_list = task041_balh_cpu_list(str(normalized["model_id"]))
    if expected_rank_cpus is not None:
        frozen_cpus = task041_parse_expected_rank_cpus(expected_rank_cpus)
        if frozen_cpus is None:
            raise ValueError("mode-prep expected_rank_cpus must be an explicit map")
        cpu_list = ",".join(str(cpu) for cpu in frozen_cpus)
    return _mpi8_command(
        python_executable,
        TASK041_BALH_MODE_PREP_PHASE,
        specification.source_path,
        None,
        None,
        None,
        run_directory,
        source_sha,
        None,
        module="benchmarks.task041_exact_side_workflow",
        cpu_list=cpu_list,
        membind_node=task041_balh_membind_node(str(normalized["model_id"])),
    )


def build_task041_balh_exact_consumer_command(
    python_executable: str | Path,
    specification: Any,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
    packet_producer_source_sha: str | None = None,
    packet_origin: str | None = None,
    legacy_native_binding: str | Path | None = None,
) -> list[str]:
    normalized = specification.as_jsonable()
    if task041_balh_route(str(normalized["model_id"])) != "exact":
        raise ValueError("BAL_H exact consumer command requires an exact profile")
    return _mpi8_command(
        python_executable,
        TASK041_BALH_CONSUMER_PHASE,
        specification.source_path,
        packet_manifest,
        packet_identity,
        packet_manifest_sha256,
        run_directory,
        source_sha,
        packet_producer_source_sha,
        module="benchmarks.task041_exact_side_workflow",
        packet_origin=packet_origin,
        legacy_native_binding=legacy_native_binding,
        cpu_list=task041_balh_cpu_list(str(normalized["model_id"])),
    )


def build_task041_balh_candidate_consumer_command(
    python_executable: str | Path,
    specification: Any,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
    packet_producer_source_sha: str | None = None,
    packet_origin: str | None = None,
    legacy_native_binding: str | Path | None = None,
    disable_time_stop: bool = False,
    performance_profile: str | None = None,
    task041_rhs_probe_manifest: str | Path | None = None,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
    top_causal_replay: bool = False,
    p4_correction_replay_from: str | Path | None = None,
    p4_response_correction_steps: int = 0,
    p4_refinement_target_tolerance: float | None = None,
    p4_backend_pair_side: str | None = None,
    task041_resource_policy: str | None = None,
    fixed_h6_modal_gmres_research: bool = False,
    modal_feedback_method: str | None = None,
    modal_solver_policy: str | None = None,
    expected_rank_cpus: Sequence[int] | None = None,
    packet_source_binding: Mapping[str, Any] | None = None,
) -> list[str]:
    normalized = specification.as_jsonable()
    if task041_balh_route(str(normalized["model_id"])) != "balh":
        raise ValueError("BAL_H candidate consumer command requires a candidate profile")
    if (
        disable_time_stop
        and str(normalized["model_id"]) != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    ):
        raise ValueError(
            "time-stop override is limited to the 5 nm BAL_H candidate profile"
        )
    target_binding = None
    if p4_refinement_target_tolerance is not None or p4_backend_pair_side is not None:
        target_binding = task041_p4_refinement_target_binding(
            model_id=str(normalized["model_id"]),
            refinement_target_tolerance=p4_refinement_target_tolerance,
            p4_backend_pair_side=p4_backend_pair_side,
            profile_id=performance_profile,
            scope=(
                TASK041_REPRESENTATIVE_RHS_SCOPE
                if task041_rhs_probe_manifest is not None
                else None
            ),
            side_setup_schedule=side_setup_schedule,
            comparison_mode=comparison_mode,
        )
    resource_policy_binding = task041_v8_resource_policy_binding(
        str(normalized["model_id"]), task041_resource_policy
    )
    fixed_h6_binding = task041_fixed_h6_modal_gmres_binding(
        str(normalized["model_id"]),
        enabled=fixed_h6_modal_gmres_research,
        candidate=True,
        mpi_size=int(specification.execution.get("mpi_size", -1)),
        mode_count=int(
            specification.method.get("requested_modes_per_direction", -1)
        ),
        p4_inverse_backend=str(
            task041_balh_case(str(normalized["model_id"])).get(
                "p4_inverse_backend", ""
            )
        )
        if task041_balh_case(str(normalized["model_id"])) is not None
        else None,
        p4_refinement_target_tolerance=p4_refinement_target_tolerance,
        task041_resource_policy=task041_resource_policy,
        expected_rank_cpus=expected_rank_cpus,
        modal_feedback_method=modal_feedback_method,
        modal_solver_policy=modal_solver_policy,
    )
    if packet_source_binding is not None:
        if (
            fixed_h6_binding is None
            or str(normalized["model_id"]) != TASK041_BALH_W0P7NM_P6_PILOT_MODEL_ID
            or not isinstance(packet_source_binding, Mapping)
            or packet_source_binding.get("source_type") != "validated_producer_root"
            or packet_origin is not None
            or legacy_native_binding is not None
        ):
            raise ValueError(
                "validated producer-root binding is limited to the registered W0.7 fixed-H6 consumer"
            )
        observed_source = task041_fixed_h6_packet_source_binding(
            fixed_h6_binding,
            producer_packet_root=packet_source_binding.get("producer_root"),
            legacy_native_packet_descriptor=None,
        )
        if observed_source != dict(packet_source_binding):
            raise ValueError(
                "candidate consumer producer-root binding does not match its files"
            )
        source_files = packet_source_binding.get("files")
        expected_identity = (
            source_files.get("packet_identity")
            if isinstance(source_files, Mapping)
            else None
        )
        expected_manifest = (
            source_files.get("selected_mode_packet_manifest")
            if isinstance(source_files, Mapping)
            else None
        )
        if (
            not isinstance(expected_identity, Mapping)
            or not isinstance(expected_manifest, Mapping)
            or Path(packet_identity).resolve()
            != Path(str(expected_identity.get("path", ""))).resolve()
            or Path(packet_manifest).resolve()
            != Path(str(expected_manifest.get("path", ""))).resolve()
            or packet_manifest_sha256 != expected_manifest.get("sha256")
        ):
            raise ValueError(
                "candidate consumer packet manifest/identity paths do not match the producer-root binding"
            )
    if fixed_h6_binding is not None and (
        expected_rank_cpus is None
        or disable_time_stop
        or performance_profile is not None
        or task041_rhs_probe_manifest is not None
        or side_setup_schedule is not None
        or comparison_mode is not None
        or top_causal_replay
        or p4_correction_replay_from is not None
        or p4_response_correction_steps != 0
        or p4_backend_pair_side is not None
    ):
        raise ValueError(
            "fixed-H6 research is limited to the registered formal candidate route"
        )
    if resource_policy_binding is not None and (
        performance_profile is not None
        or task041_rhs_probe_manifest is not None
        or side_setup_schedule is not None
        or comparison_mode is not None
        or top_causal_replay
        or p4_correction_replay_from is not None
        or p4_response_correction_steps != 0
        or p4_backend_pair_side is not None
    ):
        raise ValueError(
            "V8 resource policy is limited to a registered formal consumer"
        )
    if performance_profile is not None:
        if disable_time_stop:
            raise ValueError(
                "performance profile and time-stop override are mutually exclusive"
            )
        task041_schur_speed_v2_contract(
            str(normalized["model_id"]),
            scope=(
                TASK041_REPRESENTATIVE_RHS_SCOPE
                if task041_rhs_probe_manifest is not None
                else None
            ),
            side_setup_schedule=side_setup_schedule,
            comparison_mode=comparison_mode,
            top_causal_replay=top_causal_replay,
            p4_correction_replay=p4_correction_replay_from is not None,
            p4_response_correction_steps=p4_response_correction_steps,
            p4_refinement_target_tolerance=p4_refinement_target_tolerance,
            p4_backend_pair_side=p4_backend_pair_side,
        )
    elif (
        side_setup_schedule is not None
        or comparison_mode is not None
        or top_causal_replay
        or p4_correction_replay_from is not None
        or p4_response_correction_steps != 0
        or (
            (p4_refinement_target_tolerance is not None
             or p4_backend_pair_side is not None)
            and not (
                isinstance(target_binding, Mapping)
                and target_binding.get("scope")
                == task041_p4_registered_formal_target_scope(
                    str(normalized["model_id"])
                )
            )
        )
    ):
        raise ValueError(
            "Task041 comparison options require task041_schur_speed_v2"
        )
    if task041_rhs_probe_manifest is not None:
        if (
            str(normalized["model_id"]) != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
            or performance_profile != TASK041_SCHUR_SPEED_V2_PROFILE
            or disable_time_stop
        ):
            raise ValueError(
                "representative RHS probe requires the reused 5 nm task041_schur_speed_v2 candidate"
            )
        if not Path(task041_rhs_probe_manifest).is_absolute():
            raise ValueError("representative RHS manifest must be an absolute path")
    p4_backend_pair = bool(
        task041_rhs_probe_manifest is not None
        and task041_is_explicit_p4_backend_pair(
            model_id=str(normalized["model_id"]),
            profile_id=performance_profile,
            scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
            side_setup_schedule=side_setup_schedule,
            comparison_mode=comparison_mode,
        )
    )
    if top_causal_replay and not p4_backend_pair:
        raise ValueError(
            "top causal replay requires the explicit fixed-eight backend pair"
        )
    if p4_correction_replay_from is not None and (
        not p4_backend_pair or top_causal_replay
    ):
        raise ValueError(
            "P4 correction replay requires the fixed-eight pair and its own top-only mode"
        )
    if p4_response_correction_steps and not top_causal_replay:
        raise ValueError(
            "P4 response corrections require top_causal_replay"
        )
    command = _mpi8_command(
        python_executable,
        TASK041_BALH_CANDIDATE_PHASE,
        specification.source_path,
        packet_manifest,
        packet_identity,
        packet_manifest_sha256,
        run_directory,
        source_sha,
        packet_producer_source_sha,
        module="benchmarks.task041_balh_workflow",
        packet_origin=packet_origin,
        legacy_native_binding=legacy_native_binding,
        disable_time_stop=disable_time_stop,
        performance_profile=performance_profile,
        task041_rhs_probe_manifest=task041_rhs_probe_manifest,
        side_setup_schedule=side_setup_schedule,
        comparison_mode=comparison_mode,
        top_causal_replay=top_causal_replay,
        p4_correction_replay_from=p4_correction_replay_from,
        p4_response_correction_steps=p4_response_correction_steps,
        p4_refinement_target_tolerance=p4_refinement_target_tolerance,
        p4_backend_pair_side=p4_backend_pair_side,
        cpu_list=(
            "1-8"
            if p4_backend_pair
            else ",".join(
                str(cpu) for cpu in fixed_h6_binding["expected_rank_cpus"]
            )
            if fixed_h6_binding is not None
            else task041_balh_cpu_list(str(normalized["model_id"]))
        ),
        membind_node=(
            "0"
            if p4_backend_pair
            else task041_balh_membind_node(str(normalized["model_id"]))
        ),
    )
    if resource_policy_binding is not None:
        command.extend(
            ["--task041-resource-policy", str(resource_policy_binding["policy"])]
        )
    if fixed_h6_binding is not None:
        command.append("--task041-fixed-h6-modal-gmres-research")
        command.extend(
            [
                "--task041-expected-rank-cpus",
                ",".join(
                    str(cpu)
                    for cpu in fixed_h6_binding["expected_rank_cpus"]
                ),
            ]
        )
        if modal_feedback_method is not None:
            command.extend(
                ("--task041-modal-feedback-method", modal_feedback_method)
            )
        if modal_solver_policy is not None:
            command.extend(
                ("--task041-modal-solver-policy", modal_solver_policy)
            )
    if packet_source_binding is not None:
        command.extend(
            [
                "--task041-fixed-h6-packet-source-binding-json",
                json.dumps(
                    dict(packet_source_binding),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ]
        )
    return command


def task041_balh_exact_consumer_iterative_config() -> Any:
    from src.solvers.hybrid_fem_modal_block_ldu import HybridBlockLduIterativeConfig

    return HybridBlockLduIterativeConfig(
        ksp_type="fgmres",
        restart=32,
        max_it=2048,
        threshold=5.0e-9,
        initial_guess="zero",
        fixed_preconditioner=False,
    )


def task041_balh_candidate_consumer_iterative_config() -> Any:
    """Return the fixed outer FGMRES contract for the BAL_H candidate lane."""

    return task041_balh_exact_consumer_iterative_config()


def task041_balh_exact_consumer_profile(specification: Any) -> Any:
    normalized = specification.as_jsonable()
    case = _require_case(str(normalized["model_id"]))
    if case["route"] != "exact":
        raise ValueError("BAL_H exact profile requires an exact model")
    failures = tuple(task041_balh_profile_errors(normalized))
    if failures:
        detail = "; ".join(f"{field}: {message}" for field, message in failures)
        raise ValueError("Task041 side BAL_H profile rejected: " + detail)
    from benchmarks.task041_exact_side_workflow import _task041_consumer_profile

    base = _task041_consumer_profile()
    return replace(
        base,
        profile_id=TASK041_BALH_EXACT_CONSUMER_PROFILE,
        record_schema=TASK041_BALH_EXACT_CONSUMER_SCHEMA,
        qualification_schema=TASK041_BALH_EXACT_CONSUMER_SCHEMA,
        wavelength_nm=normalized["incidence"]["wavelength_nm"],
        requested_modes=case["mode_count"],
        candidate_modes=2 * case["mode_count"],
        mpi_size=TASK041_BALH_MPI_SIZE,
        h_nm=normalized["discretization"]["mesh_target_nm"],
        modal_h_nm=normalized["discretization"]["mesh_target_nm"],
        restart=32,
        max_it=2048,
        rtol=5.0e-9,
        preconditioner_identity="fixed_exact_side_lu_plus_dynamic_dtn_woodbury",
    )


def task041_balh_candidate_consumer_profile(specification: Any) -> Any:
    """Return the distinct, research-only candidate consumer profile."""

    normalized = specification.as_jsonable()
    case = _require_case(str(normalized["model_id"]))
    if case["route"] != "balh":
        raise ValueError("BAL_H candidate profile requires a candidate model")
    failures = tuple(task041_balh_profile_errors(normalized))
    if failures:
        detail = "; ".join(f"{field}: {message}" for field, message in failures)
        raise ValueError("Task041 side BAL_H candidate profile rejected: " + detail)
    from benchmarks.task041_exact_side_workflow import _task041_consumer_profile

    base = _task041_consumer_profile()
    return replace(
        base,
        profile_id=TASK041_BALH_CANDIDATE_CONSUMER_PROFILE,
        record_schema=TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA,
        qualification_schema=TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA,
        wavelength_nm=normalized["incidence"]["wavelength_nm"],
        requested_modes=case["mode_count"],
        candidate_modes=2 * case["mode_count"],
        mpi_size=TASK041_BALH_MPI_SIZE,
        h_nm=normalized["discretization"]["mesh_target_nm"],
        modal_h_nm=normalized["discretization"]["mesh_target_nm"],
        bottom_interface_nm=normalized["method"]["bottom_interface_nm"],
        top_interface_nm=normalized["method"]["top_interface_nm"],
        restart=32,
        max_it=2048,
        rtol=5.0e-9,
        preconditioner_identity="BAL_H_side_inverse_response_schur",
    )


def task041_balh_formal_physical_volume_context_factory(
    specification: Any,
    *,
    candidate: bool,
    resource_policy: str | None,
    refinement_target_tolerance: float | None,
    p4_inverse_backend: str,
    performance_profile: str | None = None,
    representative_rhs: bool = False,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
    top_causal_replay: bool = False,
    frozen_q_replay: bool = False,
    p4_response_correction_steps: int = 0,
    p4_backend_pair_side: str | None = None,
    a6_response_pair: bool = False,
) -> Any | None:
    """Select the fused volume only for the registered formal 5 nm consumer."""

    normalized = specification.as_jsonable()
    model_id = str(normalized.get("model_id", ""))
    if model_id != TASK041_BALH_5NM_CELL_CONDENSED_MODEL_ID:
        return None
    case = _require_case(model_id)
    if not (
        candidate is True
        and case["route"] == "balh"
        and resource_policy == TASK041_V8_SWAP_OBSERVE_CONTINUE
        and refinement_target_tolerance
        == TASK041_P4_REFINEMENT_TARGET_TOLERANCE
        and p4_inverse_backend == "cell_condensed"
        and performance_profile is None
        and representative_rhs is False
        and side_setup_schedule is None
        and comparison_mode is None
        and top_causal_replay is False
        and frozen_q_replay is False
        and p4_response_correction_steps == 0
        and p4_backend_pair_side is None
        and a6_response_pair is False
    ):
        return None
    from src.solvers.physical_balanced_fused_volume import (
        build_task041_fused_physical_volume_context,
    )

    return build_task041_fused_physical_volume_context


def task041_balh_consumer_identity_binding(
    producer_identity: Mapping[str, Any],
    specification: Any,
    consumer_source_sha: str,
) -> dict[str, Any]:
    """Bind a producer packet to a distinct consumer identity by physics/layout."""

    from benchmarks.task039_v4_selected_mode_packet import (
        TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
    )

    if not isinstance(producer_identity, Mapping):
        raise TypeError("Task041 side BAL_H producer identity must be a mapping")
    if not _valid_sha(consumer_source_sha, 40):
        raise ValueError("Task041 side BAL_H consumer source SHA must be lowercase SHA1")
    normalized = specification.as_jsonable()
    consumer_input_sha = str(specification.input_sha256)
    consumer_physical_sha = str(specification.physical_model_sha256)
    consumer_resolved_sha = resolved_config_sha256(specification)
    if not _valid_sha(consumer_input_sha, 64):
        raise ValueError("Task041 side BAL_H consumer input identity must be SHA256")
    if not _valid_sha(consumer_physical_sha, 64):
        raise ValueError(
            "Task041 side BAL_H consumer physical identity must be SHA256"
        )
    if not _valid_sha(consumer_resolved_sha, 64):
        raise ValueError(
            "Task041 side BAL_H consumer resolved identity must be SHA256"
        )
    model_id = str(normalized.get("model_id", ""))
    case = _require_case(model_id)
    failures = tuple(task041_balh_profile_errors(normalized))
    if failures:
        detail = "; ".join(f"{field}: {message}" for field, message in failures)
        raise ValueError("Task041 side BAL_H consumer profile rejected: " + detail)
    expected_physical = _jsonable(_physical_contract(normalized))
    consumer_external_keys = _task041_balh_external_key_identity(normalized)
    producer_external_keys = producer_identity.get("external_keys")
    checks = {
        "schema": producer_identity.get("schema")
        == TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
        "scope": producer_identity.get("scope") == case["scope"],
        "wavelength_nm": producer_identity.get("wavelength_nm")
        == case["wavelength_nm"],
        "mesh": producer_identity.get("mesh")
        == {
            "cell_type": "hexahedron",
            "kind": "full3d_uniform_cg",
            "mesh_target_nm": case["mesh_target_nm"],
            "nedelec_degree": 6,
            "spacing_mode": "boundary_fitted",
        },
        "mode_count": producer_identity.get("mode_count") == case["mode_count"],
        "mpi_size": producer_identity.get("mpi_size") == TASK041_BALH_MPI_SIZE,
        "external_keys": producer_external_keys == consumer_external_keys,
        "physical_contract": producer_identity.get("physical_contract")
        == expected_physical,
        "partition": producer_identity.get("cross_section_partition")
        == "input_contiguous_v1",
    }
    if not all(checks.values()):
        failed = ", ".join(key for key, passed in checks.items() if not passed)
        raise ValueError("Task041 side BAL_H producer/consumer binding mismatch: " + failed)
    return {
        "schema": "task041.side_balh.consumer_binding.v1",
        "pass": True,
        "producer_identity": _jsonable(dict(producer_identity)),
        "consumer_identity": {
            "schema": "task041.side_balh.consumer.identity.v1",
            "source_sha": consumer_source_sha,
            "input_sha256": consumer_input_sha,
            "resolved_sha256": consumer_resolved_sha,
            "physical_sha256": consumer_physical_sha,
            "wavelength_nm": normalized["incidence"]["wavelength_nm"],
            "model_id": model_id,
            "run_id": str(normalized.get("run_id", "")),
            "comparison_group": str(normalized.get("comparison_group", "")),
            "mesh": _jsonable(
                {
                    "cell_type": normalized["discretization"]["mesh_cell_type"],
                    "kind": normalized["method"]["propagation_model"],
                    "mesh_target_nm": normalized["discretization"]["mesh_target_nm"],
                    "nedelec_degree": normalized["discretization"]["nedelec_degree"],
                    "spacing_mode": normalized["discretization"]["mesh_spacing_mode"],
                }
            ),
            "mode_count": case["mode_count"],
            "mpi_size": TASK041_BALH_MPI_SIZE,
            "requested_modes_per_direction": case["mode_count"],
            "dtn_order_policy": normalized["boundary"]["dtn_order_policy"],
            "external_keys": consumer_external_keys,
            "cross_section_partition": "input_contiguous_v1",
            "physical_contract": expected_physical,
        },
        "equivalence": checks,
    }


def validate_balh_producer_packet(
    producer_root: str | Path,
    specification: Any,
    consumer_source_sha: str,
    *,
    require_public_supervisor_summary: bool = False,
    swap_observe_only: bool = False,
) -> dict[str, Any]:
    """Validate producer envelope, identity, lifecycle, and consumer binding.

    Shard payloads are read and checked by the existing consumer packet reader
    and hydration path; this function does not numerically validate every shard.
    """

    root = Path(producer_root).resolve()
    summary_path = root / "mode_prep_summary.json"
    identity_path = root / "packet_identity.json"
    manifest_path = root / "selected_mode_packet" / "manifest.json"
    supervisor_summary_path = root.parent / "supervisor_summary.json"
    if not summary_path.is_file() or not identity_path.is_file() or not manifest_path.is_file():
        raise ValueError("Task041 side BAL_H producer packet artifacts are incomplete")
    if require_public_supervisor_summary and not supervisor_summary_path.is_file():
        raise ValueError(
            "Task041 side BAL_H producer requires the completed public supervisor summary"
        )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if not isinstance(summary, Mapping) or not isinstance(identity, Mapping):
        raise TypeError("Task041 side BAL_H producer artifacts must be mappings")
    inherited_producer_phase: dict[str, Any] = {}
    supervisor_summary_sha: str | None = None
    producer_resource_qualified: bool | None = None
    if require_public_supervisor_summary:
        supervisor_summary = json.loads(
            supervisor_summary_path.read_text(encoding="utf-8")
        )
        if not isinstance(supervisor_summary, Mapping):
            raise ValueError("Task041 public supervisor summary must be a mapping")
        phase_results = supervisor_summary.get("phase_results")
        producer_phase = (
            phase_results.get("producer")
            if isinstance(phase_results, Mapping)
            else None
        )
        if not isinstance(producer_phase, Mapping):
            raise ValueError("Task041 public supervisor summary lacks producer phase")
        if supervisor_summary.get("source_sha") is None:
            raise ValueError("Task041 public supervisor source identity is missing")
        producer_phase_fields = (
            "returncode",
            "process_group_gone",
            "termination_reason",
            "rss_drop",
            "sample_count",
            "limits",
            "timeout_scope",
            "phase_wall_seconds",
            "workflow_wall_seconds",
            "peak_memory_authority_bytes",
            "peak_process_tree_rss_bytes",
            "peak_pss_bytes",
            "peak_uss_bytes",
            "peak_process_tree_swap_bytes",
            "peak_dedicated_cgroup_swap_bytes",
            "peak_swap_bytes",
        )
        inherited_producer_phase = {
            key: _jsonable(producer_phase.get(key))
            for key in producer_phase_fields
        }
        supervisor_summary_sha = hashlib.sha256(
            supervisor_summary_path.read_bytes()
        ).hexdigest()
        resource_fields = (
            "peak_memory_authority_bytes",
            "peak_process_tree_rss_bytes",
        ) + (() if swap_observe_only else ("peak_swap_bytes",))
        sample_count = producer_phase.get("sample_count")
        producer_resource_qualified = bool(
            isinstance(sample_count, int)
            and sample_count > 0
            and all(isinstance(producer_phase.get(key), int) for key in resource_fields)
        )
    if summary.get("classification") != "TASK041_MODE_PREP_PACKET_READY":
        raise ValueError("Task041 side BAL_H producer did not complete mode-prep")
    cleanup = summary.get("cleanup")
    if not isinstance(cleanup, Mapping) or cleanup.get("producer_scope_released") is not True:
        raise ValueError("Task041 side BAL_H producer scope was not released")
    producer_source_sha = summary.get("source_sha")
    if not _valid_sha(producer_source_sha, 40) or identity.get("source_sha") != producer_source_sha:
        raise ValueError("Task041 side BAL_H producer source identity mismatch")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    packet = summary.get("packet")
    if not isinstance(packet, Mapping) or packet.get("manifest_sha256") != manifest_sha:
        raise ValueError("Task041 side BAL_H producer manifest hash mismatch")
    from benchmarks.task039_v4_selected_mode_packet import _require_task041_identity

    _require_task041_identity(identity)
    if require_public_supervisor_summary:
        if supervisor_summary.get("source_sha") != producer_source_sha:
            raise ValueError("Task041 public supervisor source identity mismatch")
        supervisor_identity = supervisor_summary.get("identity")
        expected_supervisor_identity = {
            "model_id": identity["model_id"],
            "run_id": identity["run_id"],
            "input_sha256": identity["input_sha256"],
            "resolved_config_sha256": identity["resolved_sha256"],
            "physical_model_sha256": identity["physical_sha256"],
            "requested_modes": identity["mode_count"],
            "mpi_size": identity["mpi_size"],
        }
        if not isinstance(supervisor_identity, Mapping) or any(
            supervisor_identity.get(key) != value
            for key, value in expected_supervisor_identity.items()
        ):
            raise ValueError("Task041 public supervisor identity does not match producer")
        if (
            producer_phase.get("returncode") != 0
            or producer_phase.get("process_group_gone") is not True
            or producer_phase.get("termination_reason")
            in (
                {"absolute_memory_limit", "wall_timeout"}
                if swap_observe_only
                else {"absolute_memory_limit", "swap_detected", "wall_timeout"}
            )
        ):
            raise ValueError("Task041 public supervisor producer phase did not satisfy resource lifecycle")
        selected_mode_manifest_path = root.parent / "selected_mode_manifest.json"
        if not selected_mode_manifest_path.is_file():
            raise ValueError("Task041 public selected-mode manifest is missing")
        selected_mode_manifest = json.loads(
            selected_mode_manifest_path.read_text(encoding="utf-8")
        )
        if not isinstance(selected_mode_manifest, Mapping):
            raise ValueError("Task041 public selected-mode manifest is not a mapping")
        selected_path = selected_mode_manifest.get("path")
        if (
            not isinstance(selected_path, str)
            or not Path(selected_path).is_absolute()
            or Path(selected_path).resolve() != manifest_path
            or selected_mode_manifest.get("sha256") != manifest_sha
            or selected_mode_manifest.get("identity") != dict(identity)
        ):
            raise ValueError("Task041 public selected-mode manifest does not match producer")
        if not isinstance(supervisor_summary_sha, str):
            raise ValueError("Task041 public supervisor summary hash is unavailable")
    binding = task041_balh_consumer_identity_binding(
        identity, specification, consumer_source_sha
    )
    packet_inventory = {
        "file_count": sum(1 for path in manifest_path.parent.rglob("*") if path.is_file()),
        "bytes": sum(path.stat().st_size for path in manifest_path.parent.rglob("*") if path.is_file()),
    }
    compact_manifest = {
        "schema": "task041.public.selected_mode_manifest.v1",
        "path": str(manifest_path),
        "sha256": manifest_sha,
        "bytes": manifest_path.stat().st_size,
        "packet_directory_bytes": packet_inventory["bytes"],
        "packet_directory_file_count": packet_inventory["file_count"],
        "packet_directory": {
            "path": str(manifest_path.parent),
            **packet_inventory,
        },
        "identity": dict(identity),
        "source_sha": producer_source_sha,
        "producer_supervisor_summary": {
            "path": str(supervisor_summary_path),
            "sha256": supervisor_summary_sha,
            "producer_phase": inherited_producer_phase,
            "resource_qualified": producer_resource_qualified,
        },
        "consumer_binding": binding,
    }
    return {
        "summary": dict(summary),
        "identity": dict(identity),
        "identity_path": str(identity_path),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "manifest_bytes": manifest_path.stat().st_size,
        "packet_directory": packet_inventory,
        "packet_directory_bytes": packet_inventory["bytes"],
        "packet_directory_file_count": packet_inventory["file_count"],
        "compact_manifest": compact_manifest,
        "producer_source_sha": producer_source_sha,
        "consumer_binding": binding,
        "producer_supervisor_summary": str(supervisor_summary_path),
        "producer_supervisor_summary_sha256": supervisor_summary_sha,
        "selected_mode_manifest": (
            str(root.parent / "selected_mode_manifest.json")
            if require_public_supervisor_summary
            else None
        ),
        "selected_mode_manifest_sha256": (
            hashlib.sha256(
                (root.parent / "selected_mode_manifest.json").read_bytes()
            ).hexdigest()
            if require_public_supervisor_summary
            else None
        ),
        "producer_phase": inherited_producer_phase,
        "producer_resource_qualified": producer_resource_qualified,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("--phase", choices=(TASK041_BALH_CANDIDATE_PHASE,), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--packet-manifest", required=True)
    parser.add_argument("--packet-identity", required=True)
    parser.add_argument("--packet-manifest-sha256", required=True)
    parser.add_argument("--packet-producer-source-sha")
    parser.add_argument("--packet-origin")
    parser.add_argument("--legacy-native-binding")
    parser.add_argument("--task041-fixed-h6-packet-source-binding-json")
    parser.add_argument("--task041-rhs-probe")
    parser.add_argument(
        "--task041-side-setup-schedule",
        choices=(TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,),
    )
    parser.add_argument(
        "--task041-comparison-mode",
        choices=(
            TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
            TASK041_P4_BACKEND_PAIR_MODE,
        ),
    )
    parser.add_argument(
        "--task041-top-causal-replay",
        action="store_true",
        help="capture and replay only the selected top fixed-RHS causal nodes",
    )
    parser.add_argument(
        "--task041-p4-correction-replay-from",
        help="reuse the frozen PC1 Q1/Q2 and PC inputs from a G1 consumer root",
    )
    parser.add_argument(
        "--task041-p4-response-correction-steps",
        type=int,
        choices=(0, 1),
        default=0,
        help="apply at most one same-factor P4 correction in the top causal diagnostic",
    )
    parser.add_argument(
        "--task041-p4-refinement-target-tolerance",
        type=float,
        choices=(TASK041_P4_REFINEMENT_TARGET_TOLERANCE,),
        default=None,
    )
    parser.add_argument(
        "--task041-p4-backend-pair-side",
        choices=("bottom", "top"),
        default=None,
    )
    parser.add_argument(
        "--task041-resource-policy",
        choices=(TASK041_V8_SWAP_OBSERVE_CONTINUE,),
        default=None,
    )
    parser.add_argument(
        "--task041-fixed-h6-modal-gmres-research",
        action="store_true",
    )
    parser.add_argument(
        "--task041-modal-feedback-method",
        choices=("fixed_physical_balh_once",),
        default=None,
    )
    parser.add_argument(
        "--task041-modal-solver-policy",
        choices=(
            "task041_v12_bounded_inexact_modal",
            "task041_v12_bounded_inexact_modal_once_backup",
        ),
        default=None,
    )
    parser.add_argument("--task041-expected-rank-cpus")
    time_control = parser.add_mutually_exclusive_group()
    time_control.add_argument(
        "--task041-performance-profile",
        choices=(TASK041_SCHUR_SPEED_V2_PROFILE,),
    )
    time_control.add_argument(
        "--task041-balh-candidate-disable-time-stop", action="store_true"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    from benchmarks.task041_exact_side_workflow import run_task041_consumer

    packet_source_binding = None
    if args.task041_fixed_h6_packet_source_binding_json is not None:
        try:
            packet_source_binding = json.loads(
                args.task041_fixed_h6_packet_source_binding_json
            )
        except json.JSONDecodeError as exc:
            raise ValueError("fixed-H6 packet-source binding is not valid JSON") from exc
        if not isinstance(packet_source_binding, Mapping):
            raise ValueError("fixed-H6 packet-source binding must be a JSON object")

    return run_task041_consumer(
        input_path=args.input,
        packet_manifest=args.packet_manifest,
        packet_identity=args.packet_identity,
        packet_manifest_sha256=args.packet_manifest_sha256,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        packet_producer_source_sha=args.packet_producer_source_sha,
        packet_origin=args.packet_origin,
        legacy_native_binding=args.legacy_native_binding,
        packet_source_binding=packet_source_binding,
        candidate=True,
        disable_time_stop=args.task041_balh_candidate_disable_time_stop,
        performance_profile=args.task041_performance_profile,
        task041_rhs_probe_manifest=args.task041_rhs_probe,
        side_setup_schedule=args.task041_side_setup_schedule,
        comparison_mode=args.task041_comparison_mode,
        top_causal_replay=args.task041_top_causal_replay,
        p4_correction_replay_from=args.task041_p4_correction_replay_from,
        p4_response_correction_steps=args.task041_p4_response_correction_steps,
        p4_refinement_target_tolerance=args.task041_p4_refinement_target_tolerance,
        p4_backend_pair_side=args.task041_p4_backend_pair_side,
        task041_resource_policy=args.task041_resource_policy,
        fixed_h6_modal_gmres_research=(
            args.task041_fixed_h6_modal_gmres_research
        ),
        modal_feedback_method=args.task041_modal_feedback_method,
        modal_solver_policy=args.task041_modal_solver_policy,
        expected_rank_cpus=task041_parse_expected_rank_cpus(
            args.task041_expected_rank_cpus
        ),
    )


__all__ = [
    "TASK041_BALH_2NM_CANDIDATE_MODEL_ID",
    "TASK041_BALH_5NM_CANDIDATE_MODEL_ID",
    "TASK041_BALH_CANDIDATE_CONSUMER_PROFILE",
    "TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA",
    "TASK041_BALH_CANDIDATE_PHASE",
    "TASK041_BALH_CONSUMER_PHASE",
    "TASK041_BALH_EXACT_CONSUMER_PROFILE",
    "TASK041_BALH_EXACT_CONSUMER_SCHEMA",
    "TASK041_BALH_MODE_PREP_PHASE",
    "TASK041_BALH_MODE_PREP_PROFILE",
    "TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE",
    "TASK041_P4_BACKEND_PAIR_MODE",
    "TASK041_REPRESENTATIVE_RHS_COUNT",
    "TASK041_REPRESENTATIVE_RHS_MODE_COUNT",
    "TASK041_REPRESENTATIVE_RHS_SCOPE",
    "TASK041_SCHUR_SPEED_V2_LEDGER_NAME",
    "TASK041_SCHUR_SPEED_V2_PROFILE",
    "TASK041_SEQUENTIAL_COMPONENT_SCHEDULE",
    "build_task041_balh_candidate_consumer_command",
    "build_task041_balh_exact_consumer_command",
    "build_task041_balh_mode_prep_command",
    "build_task041_balh_packet_identity",
    "load_task041_representative_rhs_manifest",
    "task041_balh_candidate_consumer_iterative_config",
    "task041_balh_candidate_consumer_profile",
    "task041_balh_consumer_identity_binding",
    "task041_balh_cpu_list",
    "task041_balh_exact_consumer_iterative_config",
    "task041_balh_exact_consumer_profile",
    "task041_balh_membind_node",
    "task041_balh_registered_rank_cpu_map",
    "task041_balh_route",
    "task041_balh_time_stop_override_record",
    "task041_balh_transfer_optimization_profile",
    "task041_fixed_h6_modal_gmres_binding",
    "task041_fixed_h6_packet_source_binding",
    "task041_fixed_h6_producer_execution_binding",
    "task041_parse_expected_rank_cpus",
    "task041_schur_speed_v2_contract",
    "validate_balh_producer_packet",
]


if __name__ == "__main__":
    main()
