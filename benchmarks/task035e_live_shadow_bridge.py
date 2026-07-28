#!/usr/bin/env python3
"""Bind one live Task035e shadow adjoint to its solved PDE endpoints.

The live shadow observer evaluates the signed DWR estimator while the PETSc
factorization is still available.  The current and shadow watchdog records,
however, are finalized only after that callback returns.  This post-PDE bridge
closes the resulting identity gap:

* it independently rebuilds both qualified 59-goal endpoints;
* it binds the executed h/p transition and both solver plans;
* it accepts ``eta`` only from the hash-bound live adjoint artifact;
* it uses ``J_shadow - J_current`` only for estimator effectivity;
* it emits a controlled negative when fewer than 54 of 59 goals are neutral
  or within a factor of two, or when any non-negligible sign is reversed.

No PDE is solved here and no hidden reference is opened.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from benchmarks.task035e_blind_cycle import (
    goal_vector_from_candidate_output,
)
from benchmarks.task035e_candidate_output import (
    AdaptedCandidateOutput,
    CandidateOutputError,
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from benchmarks.task035e_shadow_bundle import (
    BoundJSONInput,
    DWR_EVALUATOR_SCHEMA,
    DWR_EVIDENCE_SCHEMA,
    DWR_PRODUCER_ROLE,
    _load_transition_action,
    _validate_shadow_plan_provenance,
)
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    dwr_endpoint_sign_consistent,
)
from src.adaptivity.task035e_actual_dwr import ACTUAL_DWR_SCHEMA
from src.adaptivity.task035e_shadow_observer import (
    SHADOW_EVALUATION_SCHEMA,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE_SHADOW_BRIDGE_SCHEMA = "task035e.live-shadow-evidence-bridge.v1"
LIVE_SHADOW_BRIDGE_FAILURE_SCHEMA = (
    "task035e.live-shadow-evidence-bridge-failure.v1"
)
LIVE_SHADOW_BRIDGE_STATUS = "live_shadow_evidence_bridge_pass"
LIVE_SHADOW_BRIDGE_NEGATIVE_STATUS = (
    "live_shadow_evidence_bridge_controlled_negative"
)
NEAR_ZERO_ABSOLUTE = 1.0e-30
REQUIRED_FACTOR_TWO_GOALS = 54
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_EVALUATOR_CONSUMED_KEY = "hidden_" + "reference_consumed"
_FORBIDDEN_PATH_PARTS = frozenset(
    {"reference_certifier", "hidden_auditor", "sealed_reference"}
)


class LiveShadowBridgeError(ValueError):
    """Raised when post-PDE identity or live-adjoint evidence is invalid."""


@dataclass(frozen=True, slots=True)
class BuiltLiveShadowBridge:
    """One immutable pass or controlled-negative bridge payload."""

    payload: Mapping[str, Any]
    payload_sha256: str
    passed: bool
    classification: str


@dataclass(frozen=True, slots=True)
class LiveShadowBridgeWriteReceipt:
    """Non-physical receipt for an immutable bridge artifact."""

    path: Path
    file_sha256: str
    payload_sha256: str
    passed: bool
    classification: str
    byte_count: int


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LiveShadowBridgeError(
                "bridge payload contains a non-finite float"
            )
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise LiveShadowBridgeError(
        f"bridge payload contains unsupported {type(value).__name__}"
    )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _namespaced_json_sha256(value: Any, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(_canonical_bytes(value))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveShadowBridgeError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise LiveShadowBridgeError(f"{label} must be a JSON array")
    return value


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiveShadowBridgeError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise LiveShadowBridgeError(f"{label} must be finite")
    return result


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LiveShadowBridgeError(f"{label} must be a lowercase SHA-256")
    return value


def _source_sha(value: Any, *, label: str = "source SHA") -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise LiveShadowBridgeError(f"{label} must be one full Git SHA")
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if {part.lower() for part in resolved.parts} & _FORBIDDEN_PATH_PARTS:
        raise LiveShadowBridgeError(f"{label} crosses a forbidden layer")
    return resolved


def _load_bound_json(
    bound: BoundJSONInput,
    *,
    label: str,
) -> tuple[Mapping[str, Any], str]:
    path = _safe_path(bound.path, label=label)
    if not path.is_file():
        raise LiveShadowBridgeError(f"{label} is missing: {path}")
    observed = _file_sha256(path)
    if observed != bound.sha256:
        raise LiveShadowBridgeError(
            f"{label} file SHA-256 mismatch: "
            f"expected {bound.sha256}, observed {observed}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveShadowBridgeError(f"cannot read {label}: {path}") from exc
    return _mapping(payload, label=label), observed


def _adapt(
    bound: BoundJSONInput,
    *,
    output_role: str,
) -> AdaptedCandidateOutput:
    try:
        return adapt_candidate_output(
            CandidateWatchdogInput(bound.path, bound.sha256),
            output_role=output_role,
        )
    except CandidateOutputError as exc:
        raise LiveShadowBridgeError(str(exc)) from exc


def _require_live_reference(
    adapted: AdaptedCandidateOutput,
    *,
    role: str,
) -> Mapping[str, Any]:
    row = adapted.live_role_evidence
    if row is None:
        raise LiveShadowBridgeError(
            f"{role} watchdog does not expose hash-bound live-role evidence"
        )
    if row.get("role") != role:
        raise LiveShadowBridgeError(
            f"{role} live-role evidence metadata has a different role"
        )
    _sha256(row.get("sha256"), label=f"{role} live evidence SHA-256")
    _sha256(
        row.get("payload_sha256"),
        label=f"{role} live payload SHA-256",
    )
    return row


def _load_current_snapshot_reference(
    current: AdaptedCandidateOutput,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    reference = _require_live_reference(current, role="current")
    bound = BoundJSONInput(
        Path(reference["path"]),
        reference["sha256"],
    )
    payload, _ = _load_bound_json(bound, label="current live snapshot")
    unsigned = dict(payload)
    stored = _sha256(
        unsigned.pop("manifest_payload_sha256", None),
        label="current snapshot payload SHA-256",
    )
    observed = _namespaced_json_sha256(
        unsigned,
        namespace="task035e.multigoal-current-manifest.v1",
    )
    plan = _mapping(
        payload.get("plan_identity"),
        label="current snapshot plan identity",
    )
    if (
        stored != observed
        or stored != reference["payload_sha256"]
        or payload.get("schema_version")
        != "task035e.multigoal-current-live-snapshot.v1"
        or payload.get("status") != "multigoal_current_live_snapshot_pass"
        or payload.get("pass") is not True
        or payload.get("source_sha") != current.source_sha
        or payload.get("trial_id") != current.trial_id
        or payload.get("cycle_index") != current.cycle_index
        or payload.get("mpi_size") != 8
        or payload.get("formal_mpi8_qualified") is not True
        or payload.get("role") != "current_blind_state"
        or plan.get("file_sha256") != current.plan_file_sha256
        or payload.get("ordinary_default_changed") is not False
    ):
        raise LiveShadowBridgeError(
            "current live snapshot self-hash or solve identity differs"
        )
    return payload, reference


def _validate_actual_dwr_report(
    raw: Any,
    *,
    shadow: AdaptedCandidateOutput,
    shadow_kind: str,
) -> tuple[Mapping[str, Any], dict[str, float], Mapping[str, str]]:
    report = _mapping(raw, label="actual DWR report")
    unsigned = dict(report)
    stored_report_sha = _sha256(
        unsigned.pop("report_sha256", None),
        label="actual DWR report SHA-256",
    )
    observed_report_sha = _namespaced_json_sha256(
        unsigned,
        namespace="task035e.actual-live-shadow-dwr-report.v1",
    )
    plan = _mapping(
        report.get("shadow_plan_identity"),
        label="actual DWR shadow-plan identity",
    )
    inventory = _mapping(
        report.get("goal_inventory"),
        label="actual DWR goal inventory",
    )
    aggregate = _mapping(
        report.get("aggregate_identities"),
        label="actual DWR aggregate identities",
    )
    implementation = _mapping(
        report.get("implementation_identity"),
        label="actual DWR implementation identity",
    )
    residual = _mapping(
        report.get("enriched_current_residual"),
        label="actual DWR enriched residual",
    )
    capability = _mapping(
        report.get("capability_credit"),
        label="actual DWR capability credit",
    )
    for name in (
        "implementation_sha256",
        "primal_residual_sha256",
        "adjoint_system_sha256",
    ):
        _sha256(aggregate.get(name), label=f"actual DWR {name}")
    expected_adjoint_sha = _namespaced_json_sha256(
        {
            "shadow_plan_identity": plan,
            "layout_identity": report.get("layout_identity"),
            "operator_identity": report.get("operator_identity"),
        },
        namespace="task035e.actual-dwr-adjoint-system.v1",
    )
    if (
        stored_report_sha != observed_report_sha
        or report.get("schema_version") != ACTUAL_DWR_SCHEMA
        or report.get("status") != "actual_live_shadow_dwr_pass"
        or report.get("pass") is not True
        or report.get("source_sha") != shadow.source_sha
        or report.get("shadow_kind") != shadow_kind
        or plan.get("file_sha256") != shadow.plan_file_sha256
        or plan.get("forest_leaf_catalog_sha256")
        != shadow.forest_leaf_catalog_sha256
        or plan.get("cell_degree_plan_sha256")
        != shadow.cell_degree_plan_sha256
        or inventory.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
        or inventory.get("formal_goal_inventory_sha256")
        != FORMAL_GOAL_INVENTORY_SHA256
        or tuple(inventory.get("ordered_goal_ids", ())) != FORMAL_GOAL_IDS
        or implementation.get("implementation_sha256")
        != aggregate["implementation_sha256"]
        or residual.get("partition_bound_sha256")
        != aggregate["primal_residual_sha256"]
        or expected_adjoint_sha != aggregate["adjoint_system_sha256"]
        or capability.get("actual_enriched_residual_complete") is not True
        or capability.get("actual_59_goal_adjoint_complete") is not True
        or capability.get("actual_signed_dwr_complete") is not True
        or report.get("ordinary_default_changed") is not False
    ):
        raise LiveShadowBridgeError(
            "actual DWR report identity, plan, or capability differs"
        )
    goal_rows = _sequence(report.get("goals"), label="actual DWR goals")
    if len(goal_rows) != len(FORMAL_GOAL_IDS):
        raise LiveShadowBridgeError(
            "actual DWR report does not contain all 59 goal rows"
        )
    signed: dict[str, float] = {}
    for expected_goal_id, raw_row in zip(
        FORMAL_GOAL_IDS,
        goal_rows,
        strict=True,
    ):
        row = _mapping(raw_row, label=f"actual DWR goal {expected_goal_id}")
        if row.get("goal_id") != expected_goal_id:
            raise LiveShadowBridgeError(
                "actual DWR goal rows are not in the frozen order"
            )
        unsigned_row = dict(row)
        stored_row_sha = _sha256(
            unsigned_row.pop("goal_evidence_sha256", None),
            label=f"actual DWR goal {expected_goal_id} evidence SHA-256",
        )
        observed_row_sha = _namespaced_json_sha256(
            unsigned_row,
            namespace="task035e.actual-dwr.per-goal.v1",
        )
        eta = _finite(
            row.get("signed_eta_real_zH_r"),
            label=f"actual DWR eta {expected_goal_id}",
        )
        if (
            stored_row_sha != observed_row_sha
            or row.get("actual_adjoint_solve_complete") is not True
            or row.get("endpoint_goal_delta_consumed") is not False
            or type(row.get("ksp_converged_reason")) is not int
            or row["ksp_converged_reason"] <= 0
            or _finite(
                row.get("adjoint_true_relative_residual"),
                label=f"adjoint residual {expected_goal_id}",
            )
            > _finite(
                row.get("adjoint_relative_tolerance"),
                label=f"adjoint tolerance {expected_goal_id}",
            )
        ):
            raise LiveShadowBridgeError(
                f"actual DWR goal evidence failed for {expected_goal_id}"
            )
        signed[expected_goal_id] = eta
    return report, signed, {
        "implementation_sha256": str(aggregate["implementation_sha256"]),
        "primal_residual_sha256": str(
            aggregate["primal_residual_sha256"]
        ),
        "adjoint_system_sha256": str(aggregate["adjoint_system_sha256"]),
        "report_sha256": stored_report_sha,
    }


def _load_live_shadow(
    bound: BoundJSONInput,
    *,
    shadow: AdaptedCandidateOutput,
    current: AdaptedCandidateOutput,
    current_reference: Mapping[str, str],
    shadow_kind: str,
) -> tuple[
    Mapping[str, Any],
    dict[str, float],
    Mapping[str, str],
    Mapping[str, str],
]:
    reference = _require_live_reference(shadow, role=shadow_kind)
    if (
        bound.path.resolve() != Path(reference["path"]).resolve()
        or bound.sha256 != reference["sha256"]
    ):
        raise LiveShadowBridgeError(
            "explicit live-shadow artifact differs from watchdog authority"
        )
    payload, file_sha = _load_bound_json(
        bound,
        label="live shadow evaluation",
    )
    unsigned = dict(payload)
    stored = _sha256(
        unsigned.pop("payload_sha256", None),
        label="live shadow payload SHA-256",
    )
    observed = _namespaced_json_sha256(
        unsigned,
        namespace="task035e.live-shadow-evaluation-payload.v1",
    )
    current_snapshot = _mapping(
        payload.get("current_snapshot"),
        label="live shadow current snapshot binding",
    )
    if (
        file_sha != reference["sha256"]
        or stored != observed
        or stored != reference["payload_sha256"]
        or payload.get("schema_version") != SHADOW_EVALUATION_SCHEMA
        or payload.get("status")
        != "live_shadow_59_goal_actual_dwr_pass"
        or payload.get("pass") is not True
        or payload.get("source_sha") != current.source_sha
        or payload.get("source_sha") != shadow.source_sha
        or payload.get("trial_id") != current.trial_id
        or payload.get("trial_id") != shadow.trial_id
        or payload.get("cycle_index") != current.cycle_index
        or payload.get("cycle_index") != shadow.cycle_index
        or payload.get("shadow_kind") != shadow_kind
        or payload.get("mpi_size") != 8
        or payload.get("formal_mpi8_qualified") is not True
        or payload.get("diagnostic_serial_fixture") is not False
        or payload.get("shadow_plan_file_sha256")
        != shadow.plan_file_sha256
        or current_snapshot.get("manifest_file_sha256")
        != current_reference["sha256"]
        or Path(str(current_snapshot.get("manifest_path"))).resolve()
        != Path(current_reference["path"]).resolve()
        or current_snapshot.get("current_plan_file_sha256")
        != current.plan_file_sha256
        or payload.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
        or payload.get("formal_goal_inventory_sha256")
        != FORMAL_GOAL_INVENTORY_SHA256
        or payload.get(_EVALUATOR_CONSUMED_KEY) is not False
        or payload.get("endpoint_delta_used_as_dwr") is not False
        or payload.get("ordinary_default_changed") is not False
    ):
        raise LiveShadowBridgeError(
            "live shadow self-hash, source, trial, cycle, or plan differs"
        )
    report, signed, evaluator = _validate_actual_dwr_report(
        payload.get("actual_dwr"),
        shadow=shadow,
        shadow_kind=shadow_kind,
    )
    signed_outer = _mapping(
        payload.get("signed_dwr_delta"),
        label="live shadow signed DWR mapping",
    )
    if set(signed_outer) != set(FORMAL_GOAL_IDS) or any(
        _finite(
            signed_outer[goal_id],
            label=f"live shadow eta {goal_id}",
        )
        != signed[goal_id]
        for goal_id in FORMAL_GOAL_IDS
    ):
        raise LiveShadowBridgeError(
            "live shadow DWR mapping differs from per-goal adjoint evidence"
        )
    return payload, signed, evaluator, reference


def _effectivity_audit(
    *,
    signed_eta: Mapping[str, float],
    current_values: Mapping[str, float],
    shadow_values: Mapping[str, float],
) -> tuple[dict[str, Any], dict[str, float]]:
    actual_delta: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    factor_two_count = 0
    neutral_count = 0
    opposite_sign_ids: list[str] = []
    actual_zero_eta_nonzero_ids: list[str] = []
    outside_ids: list[str] = []
    for goal_id in FORMAL_GOAL_IDS:
        eta = _finite(signed_eta[goal_id], label=f"DWR eta {goal_id}")
        actual = _finite(
            float(shadow_values[goal_id]) - float(current_values[goal_id]),
            label=f"endpoint delta {goal_id}",
        )
        actual_delta[goal_id] = actual
        eta_zero = abs(eta) <= NEAR_ZERO_ABSOLUTE
        actual_zero = abs(actual) <= NEAR_ZERO_ABSOLUTE
        if eta_zero and actual_zero:
            classification = "both_near_zero_neutral"
            effectivity: float | None = None
            within = True
            sign_ok = True
            neutral_count += 1
        elif actual_zero:
            classification = "actual_near_zero_eta_nonzero"
            effectivity = None
            within = False
            sign_ok = False
            actual_zero_eta_nonzero_ids.append(goal_id)
        else:
            effectivity = eta / actual
            sign_ok = eta_zero or effectivity >= 0.0
            within = (
                math.isfinite(effectivity)
                and 0.5 <= abs(effectivity) <= 2.0
            )
            if not sign_ok:
                classification = "opposite_sign"
                opposite_sign_ids.append(goal_id)
            elif within:
                classification = "within_factor_two"
            else:
                classification = "outside_factor_two"
        if within:
            factor_two_count += 1
        else:
            outside_ids.append(goal_id)
        rows.append(
            {
                "goal_id": goal_id,
                "signed_eta": eta,
                "actual_endpoint_delta": actual,
                "effectivity": effectivity,
                "classification": classification,
                "sign_consistent": sign_ok,
                "within_factor_two_or_neutral": within,
            }
        )
    passed = (
        not opposite_sign_ids
        and not actual_zero_eta_nonzero_ids
        and factor_two_count >= REQUIRED_FACTOR_TWO_GOALS
    )
    audit = {
        "schema_version": "task035e.live-shadow-effectivity-audit.v1",
        "near_zero_absolute": NEAR_ZERO_ABSOLUTE,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "required_factor_two_goal_count": REQUIRED_FACTOR_TWO_GOALS,
        "factor_two_or_neutral_goal_count": factor_two_count,
        "neutral_goal_count": neutral_count,
        "opposite_sign_goal_ids": opposite_sign_ids,
        "actual_near_zero_eta_nonzero_goal_ids": (
            actual_zero_eta_nonzero_ids
        ),
        "outside_factor_two_goal_ids": outside_ids,
        "rows": rows,
        "pass": passed,
    }
    return audit, actual_delta


def build_live_shadow_bridge(
    *,
    current_record: BoundJSONInput,
    shadow_record: BoundJSONInput,
    transition_action: BoundJSONInput,
    live_shadow_evidence: BoundJSONInput,
) -> BuiltLiveShadowBridge:
    """Build one post-PDE DWR/effectivity bridge without solving a PDE."""

    current = _adapt(current_record, output_role="current")
    transition, transition_file_sha, transition_representation = (
        _load_transition_action(transition_action)
    )
    kind = transition.get("kind")
    shadow_kind_by_action = {
        "p-up": "p-shadow",
        "h-refine": "h-shadow",
    }
    shadow_kind = shadow_kind_by_action.get(kind)
    if shadow_kind is None:
        raise LiveShadowBridgeError(
            "live bridge accepts only p-up or h-refine transitions"
        )
    shadow = _adapt(shadow_record, output_role=shadow_kind)
    if (
        current.source_sha != shadow.source_sha
        or current.trial_id != shadow.trial_id
        or current.cycle_index != shadow.cycle_index
        or transition.get("source_sha") != current.source_sha
        or transition.get("cycle_index") != current.cycle_index + 1
        or transition.get("from_leaf_catalog_sha256")
        != current.forest_leaf_catalog_sha256
        or transition.get("from_cell_degree_plan_sha256")
        != current.cell_degree_plan_sha256
        or transition.get("expected_next_leaf_catalog_sha256")
        != shadow.forest_leaf_catalog_sha256
        or transition.get("expected_next_cell_degree_plan_sha256")
        != shadow.cell_degree_plan_sha256
    ):
        raise LiveShadowBridgeError(
            "transition does not bind current/shadow source, cycle, or plans"
        )
    _validate_shadow_plan_provenance(
        current=current,
        shadow=shadow,
        transition=transition,
    )
    current_snapshot, current_live_reference = (
        _load_current_snapshot_reference(current)
    )
    (
        _live_payload,
        signed_eta,
        evaluator,
        shadow_live_reference,
    ) = _load_live_shadow(
        live_shadow_evidence,
        shadow=shadow,
        current=current,
        current_reference=current_live_reference,
        shadow_kind=shadow_kind,
    )
    current_goals = goal_vector_from_candidate_output(current.payload)
    shadow_goals = goal_vector_from_candidate_output(shadow.payload)
    effectivity, actual_delta = _effectivity_audit(
        signed_eta=signed_eta,
        current_values=current_goals.by_id,
        shadow_values=shadow_goals.by_id,
    )
    sign_consistent = dwr_endpoint_sign_consistent(
        signed_eta,
        current=current_goals,
        shadow=shadow_goals,
    )
    target_ids = tuple(
        str(value)
        for value in _sequence(
            transition.get("canonical_target_ids"),
            label="transition target IDs",
        )
    )
    dwr_payload = {
        "schema_version": DWR_EVIDENCE_SCHEMA,
        "producer_role": DWR_PRODUCER_ROLE,
        "source_sha": current.source_sha,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "action_id": transition["action_id"],
        "kind": kind,
        "target_ids": list(target_ids),
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
        "current_mesh_forest_sha256": (
            current.forest_leaf_catalog_sha256
        ),
        "current_degree_map_sha256": current.cell_degree_plan_sha256,
        "shadow_mesh_forest_sha256": (
            shadow.forest_leaf_catalog_sha256
        ),
        "shadow_degree_map_sha256": shadow.cell_degree_plan_sha256,
        "current_goal_sha256": current_goals.sha256,
        "shadow_goal_sha256": shadow_goals.sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": (
            FORMAL_GOAL_INVENTORY_SHA256
        ),
        "evaluator": {
            "schema_version": DWR_EVALUATOR_SCHEMA,
            "evaluator_id": "task035e_live_shadow_actual_dwr",
            "evaluator_source_sha": current.source_sha,
            "implementation_sha256": evaluator[
                "implementation_sha256"
            ],
            "primal_residual_sha256": evaluator[
                "primal_residual_sha256"
            ],
            "adjoint_system_sha256": evaluator[
                "adjoint_system_sha256"
            ],
            "method": "signed_residual_weighted_adjoint",
        },
        "actual_adjoint_solve": True,
        "actual_dwr_evaluation": True,
        "signed_not_absolute": True,
        "endpoint_delta_used_as_dwr": False,
        "synthetic": False,
        "reference_derived": False,
        "signed_dwr_delta": {
            goal_id: signed_eta[goal_id] for goal_id in FORMAL_GOAL_IDS
        },
        "sign_consistent": sign_consistent,
    }
    dwr_outer = {
        "schema_version": DWR_EVIDENCE_SCHEMA,
        "sha256": _json_sha256(dwr_payload),
        "payload": dwr_payload,
    }
    passed = bool(effectivity["pass"])
    classification = (
        "qualified_actual_dwr_effectivity_pass"
        if passed
        else "controlled_negative_effectivity"
    )
    bridge_unsigned = {
        "schema_version": LIVE_SHADOW_BRIDGE_SCHEMA,
        "status": (
            LIVE_SHADOW_BRIDGE_STATUS
            if passed
            else LIVE_SHADOW_BRIDGE_NEGATIVE_STATUS
        ),
        "pass": passed,
        "classification": classification,
        "source_sha": current.source_sha,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "action_id": transition["action_id"],
        "kind": kind,
        "target_ids": list(target_ids),
        "transition_action_sha256": transition["action_sha256"],
        "transition_action_file_sha256": transition_file_sha,
        "transition_action_identity_sha256": transition[
            "action_identity_sha256"
        ],
        "transition_action_representation": transition_representation,
        "current_watchdog_record_sha256": current.record_sha256,
        "shadow_watchdog_record_sha256": shadow.record_sha256,
        "current_output_sha256": current.output_sha256,
        "shadow_output_sha256": shadow.output_sha256,
        "current_plan_file_sha256": current.plan_file_sha256,
        "shadow_plan_file_sha256": shadow.plan_file_sha256,
        "current_mesh_forest_sha256": (
            current.forest_leaf_catalog_sha256
        ),
        "current_degree_map_sha256": current.cell_degree_plan_sha256,
        "shadow_mesh_forest_sha256": (
            shadow.forest_leaf_catalog_sha256
        ),
        "shadow_degree_map_sha256": shadow.cell_degree_plan_sha256,
        "current_goal_sha256": current_goals.sha256,
        "shadow_goal_sha256": shadow_goals.sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": (
            FORMAL_GOAL_INVENTORY_SHA256
        ),
        "current_live_role_evidence": dict(current_live_reference),
        "shadow_live_role_evidence": dict(shadow_live_reference),
        "current_snapshot_payload_sha256": current_snapshot[
            "manifest_payload_sha256"
        ],
        "actual_dwr_report_sha256": evaluator["report_sha256"],
        "signed_dwr_delta": {
            goal_id: signed_eta[goal_id] for goal_id in FORMAL_GOAL_IDS
        },
        "actual_endpoint_delta": {
            goal_id: actual_delta[goal_id] for goal_id in FORMAL_GOAL_IDS
        },
        "effectivity_audit": effectivity,
        "dwr_evidence": dwr_outer,
        "capability_credit": {
            "hash_bound_live_adjoint_complete": True,
            "post_pde_endpoint_binding_complete": True,
            "shadow_endpoint_effectivity_complete": passed,
            "accuracy_credit": False,
        },
        _EVALUATOR_CONSUMED_KEY: False,
        "endpoint_delta_used_as_dwr": False,
        "ordinary_default_changed": False,
    }
    payload_sha = _json_sha256(bridge_unsigned)
    payload = {**bridge_unsigned, "payload_sha256": payload_sha}
    return BuiltLiveShadowBridge(
        payload=payload,
        payload_sha256=payload_sha,
        passed=passed,
        classification=classification,
    )


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                _canonical(payload),
                stream,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_live_shadow_bridge(
    path: Path | str,
    built: BuiltLiveShadowBridge,
) -> LiveShadowBridgeWriteReceipt:
    """Write one immutable mode-0600 bridge outer object."""

    output = _safe_path(Path(path), label="bridge output")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite bridge output: {output}")
    outer = {
        "schema_version": LIVE_SHADOW_BRIDGE_SCHEMA,
        "sha256": built.payload_sha256,
        "payload": dict(built.payload),
    }
    _atomic_write(output, outer)
    replay, observed = _load_bound_json(
        BoundJSONInput(output, _file_sha256(output)),
        label="written live-shadow bridge",
    )
    if replay != _canonical(outer):
        raise LiveShadowBridgeError("written bridge replay differs")
    return LiveShadowBridgeWriteReceipt(
        path=output,
        file_sha256=observed,
        payload_sha256=built.payload_sha256,
        passed=built.passed,
        classification=built.classification,
        byte_count=output.stat().st_size,
    )


def _failure_outer(message: str) -> Mapping[str, Any]:
    payload = {
        "schema_version": LIVE_SHADOW_BRIDGE_FAILURE_SCHEMA,
        "status": "live_shadow_evidence_bridge_input_failure",
        "pass": False,
        "classification": "controlled_input_identity_failure",
        "error": message,
        "accuracy_credit": False,
    }
    return {
        "schema_version": LIVE_SHADOW_BRIDGE_FAILURE_SCHEMA,
        "sha256": _json_sha256(payload),
        "payload": payload,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-record", type=Path, required=True)
    parser.add_argument("--current-record-sha256", required=True)
    parser.add_argument("--shadow-record", type=Path, required=True)
    parser.add_argument("--shadow-record-sha256", required=True)
    parser.add_argument("--transition-action", type=Path, required=True)
    parser.add_argument("--transition-action-sha256", required=True)
    parser.add_argument("--live-shadow-evidence", type=Path, required=True)
    parser.add_argument("--live-shadow-evidence-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        built = build_live_shadow_bridge(
            current_record=BoundJSONInput(
                args.current_record,
                args.current_record_sha256,
            ),
            shadow_record=BoundJSONInput(
                args.shadow_record,
                args.shadow_record_sha256,
            ),
            transition_action=BoundJSONInput(
                args.transition_action,
                args.transition_action_sha256,
            ),
            live_shadow_evidence=BoundJSONInput(
                args.live_shadow_evidence,
                args.live_shadow_evidence_sha256,
            ),
        )
        receipt = write_live_shadow_bridge(args.output, built)
    except Exception as exc:
        try:
            output = _safe_path(args.output, label="bridge failure output")
            if not output.exists():
                _atomic_write(output, _failure_outer(str(exc)))
        except Exception:
            pass
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": (
                    "completed"
                    if receipt.passed
                    else "controlled_negative"
                ),
                "classification": receipt.classification,
                "path": str(receipt.path),
                "file_sha256": receipt.file_sha256,
                "payload_sha256": receipt.payload_sha256,
                "byte_count": receipt.byte_count,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt.passed else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BuiltLiveShadowBridge",
    "LIVE_SHADOW_BRIDGE_FAILURE_SCHEMA",
    "LIVE_SHADOW_BRIDGE_NEGATIVE_STATUS",
    "LIVE_SHADOW_BRIDGE_SCHEMA",
    "LIVE_SHADOW_BRIDGE_STATUS",
    "LiveShadowBridgeError",
    "LiveShadowBridgeWriteReceipt",
    "NEAR_ZERO_ABSOLUTE",
    "REQUIRED_FACTOR_TWO_GOALS",
    "build_live_shadow_bridge",
    "main",
    "write_live_shadow_bridge",
]
