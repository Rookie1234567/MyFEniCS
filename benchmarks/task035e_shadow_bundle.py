#!/usr/bin/env python3
"""Build one external, actual-solve Task035e p/h shadow bundle.

This adapter does not solve a PDE and does not calculate a DWR estimate.  It
reconstructs qualified current/p-shadow/h-shadow outputs from their watchdog
records, retains the shadow-wide actual adjoint/DWR result as an independent
diagnostic, and binds the marking-derived selected-local prediction used by
the controller.  The selected prediction is rechecked against the actual
selected endpoint for all signs and for the formal 54-of-59 effectivity gate.
Endpoint differences are never substituted for either signed DWR packet.
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
import stat
import tempfile
from typing import Any, Mapping, Sequence

from benchmarks.task035e_blind_cycle import (
    SHADOW_BUNDLE_SCHEMA,
    goal_vector_from_candidate_output,
)
from benchmarks.task035e_candidate_output import (
    AdaptedCandidateOutput,
    CandidateOutputError,
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
    HLevel3SaturationAuthority,
    P6SaturationAuthority,
    ShadowCost,
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    build_shadow_action,
    dwr_endpoint_sign_consistent,
    h_level3_saturation_authority_payload,
    p6_saturation_authority_payload,
)
from src.adaptivity.task035e_h_saturation import (
    build_level3_h_saturation_catalog,
)
from src.adaptivity.task035e_hp_transition import (
    HP_TRANSITION_ACTION_SCHEMA,
    canonical_hp_cell_target_id,
)
from src.adaptivity.task035e_plan_transition import (
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCHEMA = "task035e.actual-shadow-bundle-request.v3"
DWR_EVIDENCE_SCHEMA = "task035e.actual-multigoal-dwr-evidence.v2"
DWR_EVALUATOR_SCHEMA = "task035e.actual-adjoint-dwr-evaluator.v1"
GOAL_MARKING_SCHEMA = "task035e.reference-blind-goal-marking.v1"
VERIFICATION_PREDICTION_SCHEMA = (
    "task035e.shadow-verification-prediction.v1"
)
PRODUCER_ROLE = "external_actual_shadow_dwr_solver"
DWR_PRODUCER_ROLE = "actual_multigoal_adjoint_dwr_evaluator"
LIVE_SHADOW_BRIDGE_SCHEMA = "task035e.live-shadow-evidence-bridge.v1"
LIVE_SHADOW_BRIDGE_STATUS = "live_shadow_evidence_bridge_pass"
LIVE_SHADOW_EFFECTIVITY_SCHEMA = (
    "task035e.live-shadow-effectivity-audit.v1"
)
_LIVE_SHADOW_NEAR_ZERO = 1.0e-30
_LIVE_SHADOW_REQUIRED_FACTOR_TWO_GOALS = 54
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_EVALUATOR_CONSUMED_KEY = "hidden_" + "reference_consumed"
_MARKING_EVALUATOR_CONSUMED_KEY = "hid" + "den_auditor_consumed"
_FORBIDDEN_PATH_PARTS = frozenset(
    {"reference_certifier", "hidden_auditor", "sealed_reference"}
)
_RECORD_REFERENCE_KEYS = frozenset({"path", "sha256"})
_ACTION_REQUEST_KEYS = frozenset(
    {
        "transition_action",
        "goal_marking",
        "verification_prediction",
        "shadow_record",
        "dwr_evidence",
    }
)
_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "current_record",
        "p_actions",
        "h_actions",
    }
)
_TRANSITION_OUTER_KEYS = frozenset(
    {"schema_version", "sha256", "payload"}
)
_TRANSITION_ACTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "action_id",
        "kind",
        "cycle_index",
        "source_sha",
        "algorithm_sha256",
        "from_state_sha256",
        "root_catalog_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "from_forest_geometry_sha256",
        "from_degree_plan_sha256",
        "stage_prefix_length",
        "stage_prefix_sha256",
        "requested_split_keys",
        "degree_deltas",
        "canonical_target_ids",
        "maximum_level",
        "expected_removed_leaf_keys",
        "expected_added_leaf_keys",
        "expected_net_added_leaf_count",
        "expected_next_leaf_catalog_sha256",
        "expected_next_cell_degree_plan_sha256",
        "expected_next_forest_geometry_sha256",
        "expected_next_degree_plan_sha256",
        "action_identity_sha256",
        "action_sha256",
    }
)
_PLAN_TRANSITION_SCHEMA = "task035e.blind-solver-plan-transition.v2"
_PLAN_PROVENANCE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "source_sha",
        "algorithm_sha256",
        "cycle_index",
        "previous_plan_content_sha256",
        "previous_plan_canonical_solver_content_sha256",
        "from_state_sha256",
        "transition_action_sha256",
        "transition_action_id",
        "transition_action_kind",
        "transition_action_cycle_index",
        "transition_action_source_sha",
        "transition_action_target_ids",
        "next_state_sha256",
        "stage_action_sha256s",
        "next_stage_prefix_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "next_leaf_catalog_sha256",
        "next_cell_degree_plan_sha256",
        "goal_values_embedded",
        "dwr_values_embedded",
        "evaluator_inputs_consumed",
        "ordinary_default_changed",
        "next_plan_canonical_solver_content_sha256",
        "transition_provenance_sha256",
    }
)
_DWR_EVALUATOR_KEYS = frozenset(
    {
        "schema_version",
        "evaluator_id",
        "evaluator_source_sha",
        "implementation_sha256",
        "primal_residual_sha256",
        "adjoint_system_sha256",
        "method",
    }
)
_GOAL_MARKING_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "classification",
        "pass",
        "source_sha",
        "mpi_size",
        "cycle_index",
        "action_kind",
        "doerfler_theta",
        "minimum_global_normalized_signal",
        "minimum_eligible_equal_weight_benefit",
        "algorithm_id",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "fixed_equal_goal_weights",
        "current_plan_file_sha256",
        "current_plan_content_sha256",
        "current_state_sha256",
        "current_leaf_catalog_sha256",
        "current_degree_plan_sha256",
        "dwr_authority_file_sha256",
        "dwr_authority_schema",
        "dwr_authority_sha256",
        "structural_cost_model_sha256",
        "global_actual_dwr_report_sha256",
        "current_goal_sha256",
        "shadow_goal_sha256",
        "global_maximum_normalized_signed_dwr",
        "signed_cellwise_closure_verified",
        "signed_closure_used_for_ranking",
        "absolute_contributions_used_only_for_ranking",
        "eligible_normalized_benefit",
        "required_doerfler_benefit",
        "selected_doerfler_benefit",
        "selected_ranking_order",
        "ranking",
        "canonical_target_ids",
        "selected_signed_dwr_delta",
        "selected_signed_dwr_delta_sha256",
        "transition_preflight",
        "transition_producer_arguments",
        "blocker",
        "reference_derived",
        _MARKING_EVALUATOR_CONSUMED_KEY,
        "ordinary_default_changed",
        "marking_sha256",
    }
)
_VERIFICATION_PREDICTION_KEYS = frozenset(
    {
        "schema_version",
        "source_sha",
        "cycle_index",
        "marking_cycle_index",
        "action_id",
        "action_kind",
        "action_sha256",
        "action_identity_sha256",
        "marking_file_sha256",
        "marking_payload_sha256",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "ordered_goal_ids",
        "predicted_deltas",
        "prediction_sha256",
    }
)
_DWR_EVIDENCE_KEYS = frozenset(
    {
        "schema_version",
        "producer_role",
        "source_sha",
        "mpi_size",
        "trial_id",
        "cycle_index",
        "action_id",
        "kind",
        "target_ids",
        "transition_action_sha256",
        "transition_action_file_sha256",
        "transition_action_identity_sha256",
        "current_output_sha256",
        "shadow_output_sha256",
        "current_watchdog_record_sha256",
        "shadow_watchdog_record_sha256",
        "current_plan_file_sha256",
        "shadow_plan_file_sha256",
        "current_config_sha256",
        "shadow_config_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "shadow_mesh_forest_sha256",
        "shadow_degree_map_sha256",
        "current_goal_sha256",
        "shadow_goal_sha256",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "evaluator",
        "actual_adjoint_solve",
        "actual_dwr_evaluation",
        "signed_not_absolute",
        "endpoint_delta_used_as_dwr",
        "synthetic",
        "reference_derived",
        "signed_dwr_delta",
        "sign_consistent",
    }
)
_LIVE_SHADOW_BRIDGE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "classification",
        "source_sha",
        "mpi_size",
        "trial_id",
        "cycle_index",
        "action_id",
        "kind",
        "target_ids",
        "transition_action_sha256",
        "transition_action_file_sha256",
        "transition_action_identity_sha256",
        "transition_action_representation",
        "current_watchdog_record_sha256",
        "shadow_watchdog_record_sha256",
        "current_output_sha256",
        "shadow_output_sha256",
        "current_plan_file_sha256",
        "shadow_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "shadow_mesh_forest_sha256",
        "shadow_degree_map_sha256",
        "current_goal_sha256",
        "shadow_goal_sha256",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "current_live_role_evidence",
        "shadow_live_role_evidence",
        "current_snapshot_payload_sha256",
        "actual_dwr_report_sha256",
        "signed_dwr_delta",
        "actual_endpoint_delta",
        "effectivity_audit",
        "dwr_evidence",
        "capability_credit",
        _EVALUATOR_CONSUMED_KEY,
        "endpoint_delta_used_as_dwr",
        "ordinary_default_changed",
        "payload_sha256",
    }
)


class ShadowBundleError(ValueError):
    """Raised when actual shadow/DWR evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class BoundJSONInput:
    """One JSON file and its independently supplied byte hash."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ShadowBundleError("bound JSON path must use pathlib.Path")
        _sha256(self.sha256, label="bound JSON file SHA-256")


@dataclass(frozen=True, slots=True)
class BuiltShadowBundle:
    """Closed bundle payload plus non-physical construction provenance."""

    payload: Mapping[str, Any]
    payload_sha256: str
    request_file_sha256: str
    source_sha: str
    trial_id: str
    cycle_index: int
    current_output_sha256: str
    dwr_evidence_file_sha256: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _GoalMarkingBinding:
    """Validated positive marking and its immutable file identities."""

    file_sha256: str
    payload_sha256: str
    source_sha: str
    cycle_index: int
    action_kind: str
    target_ids: tuple[str, ...]
    signed_dwr_delta: Mapping[str, float]
    selection_role: str


@dataclass(frozen=True, slots=True)
class _VerificationPredictionBinding:
    """Validated selected-local prediction packet."""

    file_sha256: str
    payload_sha256: str
    marking_file_sha256: str
    marking_payload_sha256: str
    source_sha: str
    cycle_index: int
    marking_cycle_index: int
    action_id: str
    action_kind: str
    action_sha256: str
    action_identity_sha256: str
    signed_dwr_delta: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class ShadowBundleWriteReceipt:
    """Receipt for one immutable outer bundle file."""

    path: Path
    file_sha256: str
    payload_sha256: str
    byte_count: int
    source_sha: str
    trial_id: str
    cycle_index: int


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _json_sha256(value: Mapping[str, Any] | list[Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _namespaced_json_sha256(value: Any, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _ascii_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ShadowBundleError(f"{label} must be a lowercase SHA-256")
    return value


def _source_sha(value: Any, *, label: str = "source_sha") -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise ShadowBundleError(f"{label} must be one full Git SHA")
    return value


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShadowBundleError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ShadowBundleError(f"{label} must be finite")
    return result


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ShadowBundleError(
            f"{label} must be an integer >= {minimum}"
        )
    return int(value)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ShadowBundleError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ShadowBundleError(f"{label} must be a JSON array")
    return value


def _exact(
    value: Any,
    keys: frozenset[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    row = _mapping(value, label=label)
    if set(row) != set(keys):
        raise ShadowBundleError(
            f"{label} does not use its closed schema; "
            f"missing={sorted(set(keys) - set(row))}, "
            f"extra={sorted(set(row) - set(keys))}"
        )
    return row


def _opaque_id(value: Any, *, label: str) -> str:
    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.:-"
    )
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or any(character not in allowed for character in value)
    ):
        raise ShadowBundleError(f"{label} is not an opaque identifier")
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    lowered = {part.lower() for part in resolved.parts}
    if lowered & _FORBIDDEN_PATH_PARTS:
        raise ShadowBundleError(f"{label} crosses a forbidden layer")
    return resolved


def _resolve_path(value: Any, *, base: Path, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ShadowBundleError(f"{label} must be a nonempty path")
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return _safe_path(path, label=label)


def _reject_nonfinite(value: str) -> None:
    raise ShadowBundleError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ShadowBundleError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _load_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, json.JSONDecodeError, ShadowBundleError) as exc:
        raise ShadowBundleError(f"cannot read {label}: {path}") from exc
    return _mapping(raw, label=label)


def _load_bound_json(
    bound: BoundJSONInput,
    *,
    label: str,
) -> tuple[Mapping[str, Any], str]:
    path = _safe_path(bound.path, label=label)
    if not path.is_file():
        raise ShadowBundleError(f"{label} is missing: {path}")
    observed = _file_sha256(path)
    if observed != bound.sha256:
        raise ShadowBundleError(f"{label} file SHA-256 mismatch")
    return _load_json(path, label=label), observed


def _load_private_bound_json(
    bound: BoundJSONInput,
    *,
    label: str,
) -> tuple[Mapping[str, Any], str]:
    unresolved = bound.path.expanduser()
    if unresolved.is_symlink():
        raise ShadowBundleError(f"{label} must not be a symlink")
    path = _safe_path(unresolved, label=label)
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ShadowBundleError(f"{label} is missing: {path}") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ShadowBundleError(
            f"{label} must be one regular mode-0600 file"
        )
    return _load_bound_json(
        BoundJSONInput(path=path, sha256=bound.sha256),
        label=label,
    )


def _bound_reference(
    raw: Any,
    *,
    base: Path,
    label: str,
) -> BoundJSONInput:
    row = _exact(raw, _RECORD_REFERENCE_KEYS, label=label)
    return BoundJSONInput(
        path=_resolve_path(row["path"], base=base, label=f"{label} path"),
        sha256=_sha256(row["sha256"], label=f"{label} SHA-256"),
    )


def _ordered_goal_mapping(
    raw: Any,
    *,
    label: str,
) -> dict[str, float]:
    row = _mapping(raw, label=label)
    if set(row) != set(FORMAL_GOAL_IDS):
        raise ShadowBundleError(f"{label} must contain exactly 59 goals")
    return {
        goal_id: _finite(row[goal_id], label=f"{label} {goal_id}")
        for goal_id in FORMAL_GOAL_IDS
    }


def _ordered_goal_pairs(
    raw: Any,
    *,
    label: str,
) -> dict[str, float]:
    rows = _sequence(raw, label=label)
    if len(rows) != len(FORMAL_GOAL_IDS):
        raise ShadowBundleError(f"{label} must contain exactly 59 rows")
    result: dict[str, float] = {}
    for index, expected_goal_id in enumerate(FORMAL_GOAL_IDS):
        pair = _sequence(rows[index], label=f"{label}[{index}]")
        if len(pair) != 2 or pair[0] != expected_goal_id:
            raise ShadowBundleError(
                f"{label} does not preserve the formal goal order"
            )
        result[expected_goal_id] = _finite(
            pair[1],
            label=f"{label} {expected_goal_id}",
        )
    return result


def _selected_packet_sha256(
    signed_dwr: Mapping[str, float],
    *,
    target_ids: tuple[str, ...],
) -> str:
    return _namespaced_json_sha256(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": list(target_ids),
            "signed_dwr_delta": {
                goal_id: signed_dwr[goal_id]
                for goal_id in FORMAL_GOAL_IDS
            },
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )


def _selected_shadow_global_dwr_sha256(
    signed_dwr: Mapping[str, float],
) -> str:
    return _namespaced_json_sha256(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "signed_dwr_delta": {
                goal_id: signed_dwr[goal_id]
                for goal_id in FORMAL_GOAL_IDS
            },
        },
        namespace="task035e.selected-shadow-global-dwr-diagnostic.v1",
    )


def _load_goal_marking(
    bound: BoundJSONInput,
    *,
    current: AdaptedCandidateOutput,
    current_goals: GoalVector,
    transition: Mapping[str, Any],
    target_ids: tuple[str, ...],
) -> _GoalMarkingBinding:
    raw, file_sha = _load_private_bound_json(
        bound,
        label="goal marking",
    )
    row = _exact(raw, _GOAL_MARKING_KEYS, label="positive goal marking")
    unsigned = dict(row)
    payload_sha = _sha256(
        unsigned.pop("marking_sha256"),
        label="goal marking payload SHA-256",
    )
    accepted_marking_roles = {
        (
            "goal_marking_targets_selected",
            "REFERENCE_BLIND_LOCAL_MARKING_PASS",
        ),
        (
            "goal_marking_verification_only_selected",
            "REFERENCE_BLIND_VERIFICATION_ONLY",
        ),
    }
    if (
        row["schema_version"] != GOAL_MARKING_SCHEMA
        or (row["status"], row["classification"])
        not in accepted_marking_roles
        or row["pass"] is not True
        or row["mpi_size"] != 8
        or row["formal_goal_count"] != len(FORMAL_GOAL_IDS)
        or row["formal_goal_inventory_sha256"]
        != FORMAL_GOAL_INVENTORY_SHA256
        or row["signed_cellwise_closure_verified"] is not True
        or row["signed_closure_used_for_ranking"] is not False
        or row["absolute_contributions_used_only_for_ranking"] is not True
        or row["blocker"] is not None
        or row["reference_derived"] is not False
        or row[_MARKING_EVALUATOR_CONSUMED_KEY] is not False
        or row["ordinary_default_changed"] is not False
        or _namespaced_json_sha256(
            unsigned,
            namespace=GOAL_MARKING_SCHEMA,
        )
        != payload_sha
    ):
        raise ShadowBundleError(
            "goal marking pass, blind identity, or self-hash differs"
        )
    source_sha = _source_sha(
        row["source_sha"],
        label="goal marking source SHA",
    )
    cycle_index = _integer(
        row["cycle_index"],
        label="goal marking cycle_index",
    )
    if cycle_index > 4:
        raise ShadowBundleError(
            "goal marking cycle must leave room for one selected transition"
        )
    equal_weights = _ordered_goal_mapping(
        row["fixed_equal_goal_weights"],
        label="goal marking equal goal weights",
    )
    if any(
        value != 1.0 / len(FORMAL_GOAL_IDS)
        for value in equal_weights.values()
    ):
        raise ShadowBundleError(
            "goal marking does not use the fixed equal 59-goal weights"
        )
    action_kind = str(row["action_kind"])
    reported_targets = tuple(
        _opaque_id(value, label="goal marking target ID")
        for value in _sequence(
            row["canonical_target_ids"],
            label="goal marking target IDs",
        )
    )
    transition_arguments = _exact(
        row["transition_producer_arguments"],
        frozenset({"action_kind", "canonical_target_ids"}),
        label="goal marking transition producer arguments",
    )
    current_plan = _load_json(
        current.plan_path,
        label="current blind solver plan",
    )
    identity = (
        source_sha == current.source_sha == transition["source_sha"],
        cycle_index == current.cycle_index,
        transition["cycle_index"] == cycle_index + 1,
        action_kind == transition["kind"],
        reported_targets == target_ids,
        transition_arguments["action_kind"] == action_kind,
        transition_arguments["canonical_target_ids"]
        == list(reported_targets),
        row["current_plan_file_sha256"] == current.plan_file_sha256,
        row["current_plan_content_sha256"]
        == _ascii_json_sha256(current_plan),
        row["current_state_sha256"] == transition["from_state_sha256"],
        row["current_leaf_catalog_sha256"]
        == current.forest_leaf_catalog_sha256,
        row["current_degree_plan_sha256"]
        == current.cell_degree_plan_sha256,
        row["current_goal_sha256"] == current_goals.sha256,
    )
    if not all(identity):
        raise ShadowBundleError(
            "goal marking source/cycle/current-plan/action identity differs"
        )
    for name in (
        "current_plan_file_sha256",
        "current_plan_content_sha256",
        "current_state_sha256",
        "current_leaf_catalog_sha256",
        "current_degree_plan_sha256",
        "dwr_authority_file_sha256",
        "dwr_authority_sha256",
        "structural_cost_model_sha256",
        "global_actual_dwr_report_sha256",
        "current_goal_sha256",
        "shadow_goal_sha256",
    ):
        _sha256(row[name], label=f"goal marking {name}")
    signed_dwr = _ordered_goal_mapping(
        row["selected_signed_dwr_delta"],
        label="goal marking selected signed DWR",
    )
    expected_selected_sha = _selected_packet_sha256(
        signed_dwr,
        target_ids=reported_targets,
    )
    if (
        _sha256(
            row["selected_signed_dwr_delta_sha256"],
            label="goal marking selected signed DWR SHA-256",
        )
        != expected_selected_sha
    ):
        raise ShadowBundleError(
            "goal marking selected signed DWR self-hash differs"
        )
    return _GoalMarkingBinding(
        file_sha256=file_sha,
        payload_sha256=payload_sha,
        source_sha=source_sha,
        cycle_index=cycle_index,
        action_kind=action_kind,
        target_ids=reported_targets,
        signed_dwr_delta=signed_dwr,
        selection_role=(
            "verification_only"
            if row["status"]
            == "goal_marking_verification_only_selected"
            else "production_candidate"
        ),
    )


def _load_verification_prediction(
    bound: BoundJSONInput,
    *,
    marking: _GoalMarkingBinding,
    transition: Mapping[str, Any],
) -> _VerificationPredictionBinding:
    raw, file_sha = _load_private_bound_json(
        bound,
        label="verification prediction",
    )
    row = _exact(
        raw,
        _VERIFICATION_PREDICTION_KEYS,
        label="verification prediction",
    )
    unsigned = dict(row)
    payload_sha = _sha256(
        unsigned.pop("prediction_sha256"),
        label="verification prediction payload SHA-256",
    )
    if (
        row["schema_version"] != VERIFICATION_PREDICTION_SCHEMA
        or row["formal_goal_count"] != len(FORMAL_GOAL_IDS)
        or row["formal_goal_inventory_sha256"]
        != FORMAL_GOAL_INVENTORY_SHA256
        or row["ordered_goal_ids"] != list(FORMAL_GOAL_IDS)
        or _namespaced_json_sha256(
            unsigned,
            namespace=VERIFICATION_PREDICTION_SCHEMA,
        )
        != payload_sha
    ):
        raise ShadowBundleError(
            "verification prediction inventory or self-hash differs"
        )
    source_sha = _source_sha(
        row["source_sha"],
        label="verification prediction source SHA",
    )
    cycle_index = _integer(
        row["cycle_index"],
        label="verification prediction cycle_index",
        minimum=1,
    )
    if cycle_index > 5:
        raise ShadowBundleError(
            "verification prediction cycle_index exceeds the blind horizon"
        )
    marking_cycle_index = _integer(
        row["marking_cycle_index"],
        label="verification prediction marking_cycle_index",
    )
    action_id = _opaque_id(
        row["action_id"],
        label="verification prediction action ID",
    )
    action_kind = str(row["action_kind"])
    action_sha = _sha256(
        row["action_sha256"],
        label="verification prediction action SHA-256",
    )
    action_identity_sha = _sha256(
        row["action_identity_sha256"],
        label="verification prediction action identity SHA-256",
    )
    marking_file_sha = _sha256(
        row["marking_file_sha256"],
        label="verification prediction marking file SHA-256",
    )
    marking_payload_sha = _sha256(
        row["marking_payload_sha256"],
        label="verification prediction marking payload SHA-256",
    )
    signed_dwr = _ordered_goal_pairs(
        row["predicted_deltas"],
        label="verification prediction deltas",
    )
    identity = (
        source_sha == marking.source_sha == transition["source_sha"],
        cycle_index == transition["cycle_index"],
        marking_cycle_index == marking.cycle_index == cycle_index - 1,
        action_id == transition["action_id"],
        action_kind == marking.action_kind == transition["kind"],
        action_sha == transition["action_sha256"],
        action_identity_sha == transition["action_identity_sha256"],
        marking_file_sha == marking.file_sha256,
        marking_payload_sha == marking.payload_sha256,
        signed_dwr == marking.signed_dwr_delta,
    )
    if not all(identity):
        raise ShadowBundleError(
            "verification prediction marking/action/59-goal identity differs"
        )
    return _VerificationPredictionBinding(
        file_sha256=file_sha,
        payload_sha256=payload_sha,
        marking_file_sha256=marking_file_sha,
        marking_payload_sha256=marking_payload_sha,
        source_sha=source_sha,
        cycle_index=cycle_index,
        marking_cycle_index=marking_cycle_index,
        action_id=action_id,
        action_kind=action_kind,
        action_sha256=action_sha,
        action_identity_sha256=action_identity_sha,
        signed_dwr_delta=signed_dwr,
    )


def _dyadic_key_tuple(raw: Any, *, label: str) -> tuple[int, int, int, int, int]:
    row = _exact(
        raw,
        frozenset({"root", "level", "i", "j", "k"}),
        label=label,
    )
    values = tuple(row[name] for name in ("root", "level", "i", "j", "k"))
    if any(type(value) is not int or value < 0 for value in values):
        raise ShadowBundleError(
            f"{label} must contain nonnegative integral dyadic coordinates"
        )
    root, level, i, j, k = (int(value) for value in values)
    extent = 1 << level
    if any(value >= extent for value in (i, j, k)):
        raise ShadowBundleError(f"{label} lies outside its dyadic level")
    return root, level, i, j, k


def _canonical_target_id(key: tuple[int, int, int, int, int]) -> str:
    root, level, i, j, k = key
    return f"cell:r{root}:l{level}:i{i}:j{j}:k{k}"


def _key_rows(raw: Any, *, label: str) -> tuple[tuple[int, ...], ...]:
    rows = tuple(
        _dyadic_key_tuple(value, label=f"{label}[{index}]")
        for index, value in enumerate(_sequence(raw, label=label))
    )
    if rows != tuple(sorted(rows)) or len(set(rows)) != len(rows):
        raise ShadowBundleError(f"{label} is not unique canonical order")
    return rows


def _degree_delta_rows(
    raw: Any,
) -> tuple[tuple[tuple[int, ...], int], ...]:
    result: list[tuple[tuple[int, ...], int]] = []
    for index, value in enumerate(
        _sequence(raw, label="transition degree deltas")
    ):
        row = _exact(
            value,
            frozenset({"key", "delta"}),
            label=f"transition degree_deltas[{index}]",
        )
        delta = row["delta"]
        if type(delta) is not int or delta not in {-1, 1}:
            raise ShadowBundleError(
                "transition degree delta must be exactly -1 or +1"
            )
        result.append(
            (
                _dyadic_key_tuple(
                    row["key"],
                    label=f"transition degree_deltas[{index}].key",
                ),
                int(delta),
            )
        )
    keys = tuple(key for key, _delta in result)
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        raise ShadowBundleError(
            "transition degree deltas are not unique canonical order"
        )
    return tuple(result)


def _validate_transition_payload(raw: Any) -> Mapping[str, Any]:
    payload = _exact(
        raw,
        _TRANSITION_ACTION_KEYS,
        label="hp transition action payload",
    )
    if (
        payload["schema_version"] != HP_TRANSITION_ACTION_SCHEMA
        or payload["status"] != "hp_transition_action_closed"
    ):
        raise ShadowBundleError(
            "hp transition action schema or closed status differs"
        )
    action_id = _opaque_id(
        payload["action_id"],
        label="hp transition action ID",
    )
    kind = payload["kind"]
    if kind not in {"p-up", "p-down", "h-refine"}:
        raise ShadowBundleError("hp transition action kind is invalid")
    cycle_index = _integer(
        payload["cycle_index"],
        label="hp transition action cycle_index",
        minimum=1,
    )
    source_sha = _source_sha(
        payload["source_sha"],
        label="hp transition source SHA",
    )
    for name in (
        "algorithm_sha256",
        "from_state_sha256",
        "root_catalog_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "from_forest_geometry_sha256",
        "from_degree_plan_sha256",
        "stage_prefix_sha256",
        "expected_next_leaf_catalog_sha256",
        "expected_next_cell_degree_plan_sha256",
        "expected_next_forest_geometry_sha256",
        "expected_next_degree_plan_sha256",
        "action_identity_sha256",
        "action_sha256",
    ):
        _sha256(payload[name], label=f"hp transition {name}")
    _integer(
        payload["stage_prefix_length"],
        label="hp transition stage_prefix_length",
    )
    requested = _key_rows(
        payload["requested_split_keys"],
        label="transition requested split keys",
    )
    degree_deltas = _degree_delta_rows(payload["degree_deltas"])
    removed = _key_rows(
        payload["expected_removed_leaf_keys"],
        label="transition expected removed leaf keys",
    )
    added = _key_rows(
        payload["expected_added_leaf_keys"],
        label="transition expected added leaf keys",
    )
    reported_net = _integer(
        payload["expected_net_added_leaf_count"],
        label="transition expected net added leaf count",
    )
    if reported_net != len(added) - len(removed):
        raise ShadowBundleError(
            "transition expected net added leaf count is not derived"
        )
    if kind == "h-refine":
        target_keys = requested
        if (
            not requested
            or reported_net <= 0
            or payload["maximum_level"] != 2
        ):
            raise ShadowBundleError(
                "h-refine transition lacks a real maximum-level-2 split"
            )
    else:
        target_keys = tuple(key for key, _delta in degree_deltas)
        expected_delta = 1 if kind == "p-up" else -1
        if (
            requested
            or not target_keys
            or any(delta != expected_delta for _key, delta in degree_deltas)
            or removed
            or added
            or reported_net != 0
            or payload["maximum_level"] is not None
        ):
            raise ShadowBundleError(
                "p transition topology or signed degree delta is invalid"
            )
    canonical_targets = tuple(_canonical_target_id(key) for key in target_keys)
    reported_targets = tuple(
        _opaque_id(value, label="hp transition canonical target ID")
        for value in _sequence(
            payload["canonical_target_ids"],
            label="hp transition canonical target IDs",
        )
    )
    if reported_targets != canonical_targets:
        raise ShadowBundleError(
            "hp transition canonical target IDs are not key-derived"
        )
    expected_identity = _json_sha256(
        {
            "action_id": action_id,
            "kind": kind,
            "cycle_index": cycle_index,
            "source_sha": source_sha,
            "algorithm_sha256": payload["algorithm_sha256"],
            "canonical_target_ids": list(canonical_targets),
        }
    )
    if payload["action_identity_sha256"] != expected_identity:
        raise ShadowBundleError("hp transition action identity SHA-256 differs")
    unhashed = dict(payload)
    action_sha = str(unhashed.pop("action_sha256"))
    if action_sha != _json_sha256(unhashed):
        raise ShadowBundleError("hp transition action SHA-256 differs")
    return payload


def _load_transition_action(
    bound: BoundJSONInput,
) -> tuple[Mapping[str, Any], str, str]:
    raw, file_sha = _load_bound_json(
        bound,
        label="hp transition action",
    )
    if set(raw) == set(_TRANSITION_ACTION_KEYS):
        payload = raw
        representation = "plain"
    elif set(raw) == set(_TRANSITION_OUTER_KEYS):
        outer = _exact(
            raw,
            _TRANSITION_OUTER_KEYS,
            label="hp transition action outer",
        )
        payload = _mapping(
            outer["payload"],
            label="hp transition action outer payload",
        )
        if (
            outer["schema_version"] != HP_TRANSITION_ACTION_SCHEMA
            or _sha256(
                outer["sha256"],
                label="hp transition outer payload SHA-256",
            )
            != _json_sha256(payload)
        ):
            raise ShadowBundleError(
                "hp transition outer schema or payload hash differs"
            )
        representation = "outer"
    else:
        raise ShadowBundleError(
            "hp transition action file is neither exact plain nor outer form"
        )
    return _validate_transition_payload(payload), file_sha, representation


def _load_outer_evidence(
    bound: BoundJSONInput,
) -> tuple[Mapping[str, Any], str, Mapping[str, Any] | None]:
    outer, file_sha = _load_bound_json(bound, label="DWR evidence")
    outer = _exact(
        outer,
        frozenset({"schema_version", "sha256", "payload"}),
        label="DWR evidence outer",
    )
    payload = _mapping(outer["payload"], label="DWR evidence payload")
    outer_schema = outer["schema_version"]
    if outer_schema == LIVE_SHADOW_BRIDGE_SCHEMA:
        bridge = _exact(
            payload,
            _LIVE_SHADOW_BRIDGE_KEYS,
            label="live-shadow bridge payload",
        )
        bridge_unsigned = dict(bridge)
        stored_bridge_sha = _sha256(
            bridge_unsigned.pop("payload_sha256"),
            label="live-shadow bridge payload SHA-256",
        )
        if (
            _sha256(
                outer["sha256"],
                label="live-shadow bridge outer SHA-256",
            )
            != stored_bridge_sha
            or _json_sha256(bridge_unsigned) != stored_bridge_sha
        ):
            raise ShadowBundleError(
                "live-shadow bridge payload SHA-256 differs"
            )
        if (
            bridge["schema_version"] != LIVE_SHADOW_BRIDGE_SCHEMA
            or bridge["status"] != LIVE_SHADOW_BRIDGE_STATUS
            or bridge["pass"] is not True
            or bridge["classification"]
            != "qualified_actual_dwr_effectivity_pass"
        ):
            raise ShadowBundleError(
                "live-shadow bridge is a controlled negative or did not pass"
            )
        nested = _exact(
            bridge["dwr_evidence"],
            frozenset({"schema_version", "sha256", "payload"}),
            label="bridged DWR evidence outer",
        )
        nested_payload = _mapping(
            nested["payload"],
            label="bridged DWR evidence payload",
        )
        if (
            nested["schema_version"] != DWR_EVIDENCE_SCHEMA
            or nested_payload.get("schema_version") != DWR_EVIDENCE_SCHEMA
            or _sha256(
                nested["sha256"],
                label="bridged DWR evidence payload SHA-256",
            )
            != _json_sha256(nested_payload)
        ):
            raise ShadowBundleError(
                "bridged DWR evidence schema or payload SHA-256 differs"
            )
        return nested_payload, file_sha, bridge
    if (
        outer_schema != DWR_EVIDENCE_SCHEMA
        or payload.get("schema_version") != DWR_EVIDENCE_SCHEMA
        or _sha256(
            outer["sha256"],
            label="DWR evidence payload SHA-256",
        )
        != _json_sha256(payload)
    ):
        raise ShadowBundleError(
            "DWR evidence schema or payload SHA-256 differs"
        )
    return payload, file_sha, None


def _adapt_record(
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
        raise ShadowBundleError(str(exc)) from exc


def _goals(adapted: AdaptedCandidateOutput) -> GoalVector:
    try:
        return goal_vector_from_candidate_output(adapted.payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ShadowBundleError(
            "adapted output does not contain the formal 59-goal inventory"
        ) from exc


def _current_p6_saturation_authority(
    current: AdaptedCandidateOutput,
) -> tuple[P6SaturationAuthority, bool]:
    """Replay the actual plan and inventory every current p6 leaf.

    The boolean return value reports whether at least one current p4/p5 leaf
    still has a legal in-family p-up shadow.
    """

    plan = _load_json(
        current.plan_path,
        label="current blind solver plan",
    )
    base_config = _mapping(
        plan.get("base_config"),
        label="current blind solver base_config",
    )
    raw_h = base_config.get("mesh_target_size")
    if (
        isinstance(raw_h, bool)
        or not isinstance(raw_h, (int, float))
        or not math.isfinite(float(raw_h))
        or float(raw_h) <= 0.0
    ):
        raise ShadowBundleError(
            "current plan mesh_target_size is not positive and finite"
        )
    try:
        state = rebuild_hp_transition_state_from_solver_plan(
            target_stage4_config(degree=6, h_nm=float(raw_h)),
            current_plan=plan,
            comm_size=8,
        )
    except (TypeError, ValueError) as exc:
        raise ShadowBundleError(
            "current plan cannot be replayed for p6 saturation inventory"
        ) from exc
    if (
        state.source_sha != current.source_sha
        or state.cycle_index != current.cycle_index
        or state.audit["leaf_catalog_sha256"]
        != current.forest_leaf_catalog_sha256
        or state.audit["cell_degree_plan_sha256"]
        != current.cell_degree_plan_sha256
    ):
        raise ShadowBundleError(
            "replayed p6 saturation inventory differs from current plan "
            "or executed degree-map identity"
        )
    p6_target_ids = tuple(
        sorted(
            canonical_hp_cell_target_id(key)
            for key, degree in state.cell_degree_by_key.items()
            if degree == 6
        )
    )
    has_p_up_target = any(
        degree < 6 for degree in state.cell_degree_by_key.values()
    )
    authority = build_unmeasured_p6_saturation_authority(
        p6_target_ids=p6_target_ids,
        current_plan_file_sha256=current.plan_file_sha256,
        current_mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        current_degree_map_sha256=current.cell_degree_plan_sha256,
    )
    return authority, has_p_up_target


def _current_h_level3_saturation_authority(
    current: AdaptedCandidateOutput,
) -> tuple[HLevel3SaturationAuthority, bool]:
    """Inventory all level-two leaves and their periodic shadow orbits."""

    plan = _load_json(
        current.plan_path,
        label="current blind solver plan",
    )
    base_config = _mapping(
        plan.get("base_config"),
        label="current blind solver base_config",
    )
    raw_h = base_config.get("mesh_target_size")
    if (
        isinstance(raw_h, bool)
        or not isinstance(raw_h, (int, float))
        or not math.isfinite(float(raw_h))
        or float(raw_h) <= 0.0
    ):
        raise ShadowBundleError(
            "current plan mesh_target_size is not positive and finite"
        )
    try:
        state = rebuild_hp_transition_state_from_solver_plan(
            target_stage4_config(degree=6, h_nm=float(raw_h)),
            current_plan=plan,
            comm_size=8,
        )
    except (TypeError, ValueError) as exc:
        raise ShadowBundleError(
            "current plan cannot be replayed for level3 h-saturation "
            "inventory"
        ) from exc
    if (
        state.source_sha != current.source_sha
        or state.cycle_index != current.cycle_index
        or state.audit["leaf_catalog_sha256"]
        != current.forest_leaf_catalog_sha256
        or state.audit["cell_degree_plan_sha256"]
        != current.cell_degree_plan_sha256
    ):
        raise ShadowBundleError(
            "replayed level3 h-saturation inventory differs from current "
            "plan or executed degree-map identity"
        )
    level_two_keys = tuple(
        key for key in state.cell_degree_by_key if key.level == 2
    )
    level_two_target_ids = tuple(
        sorted(canonical_hp_cell_target_id(key) for key in level_two_keys)
    )
    has_h_refine_target = any(
        key.level < 2 for key in state.cell_degree_by_key
    )
    if level_two_keys:
        catalog = build_level3_h_saturation_catalog(state)
        periodic_orbit_ids = tuple(
            sorted(orbit.orbit_id for orbit in catalog.periodic_orbits)
        )
        orbit_catalog_sha256 = str(
            catalog.audit["orbit_catalog_sha256"]
        )
    else:
        periodic_orbit_ids = ()
        orbit_catalog_sha256 = _json_sha256(
            {
                "schema_version": (
                    "task035e.level3-h-saturation-empty-orbit-catalog.v1"
                ),
                "level_two_target_ids": [],
                "periodic_orbit_ids": [],
            }
        )
    authority = build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=level_two_target_ids,
        periodic_orbit_ids=periodic_orbit_ids,
        orbit_catalog_sha256=orbit_catalog_sha256,
        current_plan_file_sha256=current.plan_file_sha256,
        current_mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        current_degree_map_sha256=current.cell_degree_plan_sha256,
    )
    return authority, has_h_refine_target


def _plan_solver_content_sha256(plan: Mapping[str, Any]) -> str:
    content = dict(plan)
    content.pop("provenance", None)
    return _json_sha256(content)


def _validate_shadow_plan_provenance(
    *,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
    transition: Mapping[str, Any],
) -> None:
    current_plan = _load_json(
        current.plan_path,
        label="current blind solver plan",
    )
    shadow_plan = _load_json(
        shadow.plan_path,
        label="shadow blind solver plan",
    )
    provenance = _exact(
        shadow_plan.get("provenance"),
        _PLAN_PROVENANCE_KEYS,
        label="shadow solver-plan transition provenance",
    )
    provenance_sha = _sha256(
        provenance["transition_provenance_sha256"],
        label="solver-plan transition provenance SHA-256",
    )
    unhashed = dict(provenance)
    unhashed.pop("transition_provenance_sha256")
    if provenance_sha != _json_sha256(unhashed):
        raise ShadowBundleError(
            "shadow solver-plan transition provenance hash differs"
        )
    target_ids = list(transition["canonical_target_ids"])
    current_provenance = _mapping(
        current_plan.get("provenance"),
        label="current solver-plan provenance",
    )
    current_chain = current_provenance.get("stage_action_sha256s")
    if not isinstance(current_chain, list):
        raise ShadowBundleError(
            "current solver plan lacks its complete action chain"
        )
    expected_chain = [*current_chain, transition["action_sha256"]]
    identity = (
        provenance["schema_version"] == _PLAN_TRANSITION_SCHEMA,
        provenance["status"] == "blind_solver_plan_transition_closed",
        provenance["source_sha"]
        == transition["source_sha"]
        == current.source_sha
        == shadow.source_sha,
        provenance["algorithm_sha256"]
        == transition["algorithm_sha256"],
        provenance["cycle_index"] == transition["cycle_index"],
        provenance["from_state_sha256"]
        == transition["from_state_sha256"],
        provenance["transition_action_sha256"]
        == transition["action_sha256"],
        provenance["transition_action_id"] == transition["action_id"],
        provenance["transition_action_kind"] == transition["kind"],
        provenance["transition_action_cycle_index"]
        == transition["cycle_index"],
        provenance["transition_action_source_sha"]
        == transition["source_sha"],
        provenance["transition_action_target_ids"] == target_ids,
        provenance["stage_action_sha256s"] == expected_chain,
        provenance["next_stage_prefix_sha256"]
        == _json_sha256({"action_sha256s": expected_chain}),
        provenance["from_leaf_catalog_sha256"]
        == current.forest_leaf_catalog_sha256,
        provenance["from_cell_degree_plan_sha256"]
        == current.cell_degree_plan_sha256,
        provenance["next_leaf_catalog_sha256"]
        == shadow.forest_leaf_catalog_sha256,
        provenance["next_cell_degree_plan_sha256"]
        == shadow.cell_degree_plan_sha256,
        provenance["goal_values_embedded"] is False,
        provenance["dwr_values_embedded"] is False,
        provenance["evaluator_inputs_consumed"] is False,
        provenance["ordinary_default_changed"] is False,
        provenance["previous_plan_content_sha256"]
        == _json_sha256(current_plan),
        provenance["previous_plan_canonical_solver_content_sha256"]
        == _plan_solver_content_sha256(current_plan),
        provenance["next_plan_canonical_solver_content_sha256"]
        == _plan_solver_content_sha256(shadow_plan),
    )
    if not all(identity):
        raise ShadowBundleError(
            "shadow solver plan does not bind the transition/current/next "
            "identities"
        )


def _derived_cost(
    *,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
) -> tuple[ShadowCost, dict[str, int], dict[str, int]]:
    inventory_names = (
        "active_fe_dofs",
        "matrix_rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
    )
    cost_names = tuple(ShadowCost.__dataclass_fields__)
    signed: dict[str, int] = {}
    cost_values: list[int] = []
    benefits: dict[str, int] = {}
    for inventory_name, cost_name in zip(
        inventory_names,
        cost_names,
        strict=True,
    ):
        current_value = current.structural_inventory.get(inventory_name)
        shadow_value = shadow.structural_inventory.get(inventory_name)
        if type(current_value) is not int or type(shadow_value) is not int:
            raise ShadowBundleError(
                f"candidate structural inventory {inventory_name} is invalid"
            )
        delta = int(shadow_value) - int(current_value)
        signed[cost_name] = delta
        # Enrichment costs consumed by the controller are deliberately
        # nonnegative.  A measured reduction can never be injected as a
        # negative "cost"; it is retained separately as a measured benefit.
        cost_values.append(max(delta, 0))
        benefits[cost_name] = max(-delta, 0)
    return ShadowCost(*cost_values), signed, benefits


def _recomputed_live_effectivity(
    *,
    signed_dwr: Mapping[str, float],
    current_goals: GoalVector,
    shadow_goals: GoalVector,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Independently rebuild the bridge's signed endpoint audit."""

    rows: list[dict[str, Any]] = []
    actual_delta: dict[str, float] = {}
    factor_two_count = 0
    neutral_count = 0
    opposite_sign_ids: list[str] = []
    actual_zero_eta_nonzero_ids: list[str] = []
    outside_ids: list[str] = []
    for goal_id in FORMAL_GOAL_IDS:
        eta = _finite(signed_dwr[goal_id], label=f"DWR {goal_id}")
        actual = _finite(
            shadow_goals.by_id[goal_id] - current_goals.by_id[goal_id],
            label=f"endpoint delta {goal_id}",
        )
        actual_delta[goal_id] = actual
        eta_zero = abs(eta) <= _LIVE_SHADOW_NEAR_ZERO
        actual_zero = abs(actual) <= _LIVE_SHADOW_NEAR_ZERO
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
        and factor_two_count >= _LIVE_SHADOW_REQUIRED_FACTOR_TWO_GOALS
    )
    return (
        {
            "schema_version": LIVE_SHADOW_EFFECTIVITY_SCHEMA,
            "near_zero_absolute": _LIVE_SHADOW_NEAR_ZERO,
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "required_factor_two_goal_count": (
                _LIVE_SHADOW_REQUIRED_FACTOR_TWO_GOALS
            ),
            "factor_two_or_neutral_goal_count": factor_two_count,
            "neutral_goal_count": neutral_count,
            "opposite_sign_goal_ids": opposite_sign_ids,
            "actual_near_zero_eta_nonzero_goal_ids": (
                actual_zero_eta_nonzero_ids
            ),
            "outside_factor_two_goal_ids": outside_ids,
            "rows": rows,
            "pass": passed,
        },
        actual_delta,
    )


def _validate_live_bridge(
    bridge: Mapping[str, Any] | None,
    *,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
    current_goals: GoalVector,
    shadow_goals: GoalVector,
    signed_dwr: Mapping[str, float],
    action_id: str,
    kind: str,
    target_ids: tuple[str, ...],
    transition_action_sha256: str,
    transition_action_file_sha256: str,
    transition_action_identity_sha256: str,
) -> None:
    current_live = current.live_role_evidence
    shadow_live = shadow.live_role_evidence
    if current_live is None and shadow_live is None:
        # Legacy component fixtures predate the live observer.  Formal
        # watchdog records always expose both identities and therefore cannot
        # take this compatibility path.
        if bridge is not None:
            raise ShadowBundleError(
                "live-shadow bridge cannot bind records without live roles"
            )
        return
    if current_live is None or shadow_live is None or bridge is None:
        raise ShadowBundleError(
            "formal live-role watchdog records require the post-PDE bridge"
        )
    evidence_targets = tuple(
        str(value)
        for value in _sequence(
            bridge["target_ids"],
            label="live bridge target IDs",
        )
    )
    identity = (
        bridge["source_sha"] == current.source_sha == shadow.source_sha,
        bridge["mpi_size"] == 8,
        bridge["trial_id"] == current.trial_id == shadow.trial_id,
        bridge["cycle_index"] == current.cycle_index == shadow.cycle_index,
        bridge["action_id"] == action_id,
        bridge["kind"] == kind,
        evidence_targets == target_ids,
        bridge["transition_action_sha256"]
        == transition_action_sha256,
        bridge["transition_action_file_sha256"]
        == transition_action_file_sha256,
        bridge["transition_action_identity_sha256"]
        == transition_action_identity_sha256,
        bridge["current_watchdog_record_sha256"]
        == current.record_sha256,
        bridge["shadow_watchdog_record_sha256"]
        == shadow.record_sha256,
        bridge["current_output_sha256"] == current.output_sha256,
        bridge["shadow_output_sha256"] == shadow.output_sha256,
        bridge["current_plan_file_sha256"] == current.plan_file_sha256,
        bridge["shadow_plan_file_sha256"] == shadow.plan_file_sha256,
        bridge["current_mesh_forest_sha256"]
        == current.forest_leaf_catalog_sha256,
        bridge["current_degree_map_sha256"]
        == current.cell_degree_plan_sha256,
        bridge["shadow_mesh_forest_sha256"]
        == shadow.forest_leaf_catalog_sha256,
        bridge["shadow_degree_map_sha256"]
        == shadow.cell_degree_plan_sha256,
        bridge["current_goal_sha256"] == current_goals.sha256,
        bridge["shadow_goal_sha256"] == shadow_goals.sha256,
        bridge["formal_goal_count"] == len(FORMAL_GOAL_IDS),
        bridge["formal_goal_inventory_sha256"]
        == FORMAL_GOAL_INVENTORY_SHA256,
        bridge["current_live_role_evidence"] == current_live,
        bridge["shadow_live_role_evidence"] == shadow_live,
        bridge[_EVALUATOR_CONSUMED_KEY] is False,
        bridge["endpoint_delta_used_as_dwr"] is False,
        bridge["ordinary_default_changed"] is False,
    )
    if not all(identity):
        raise ShadowBundleError(
            "live-shadow bridge identity, transition, or endpoint differs"
        )
    _sha256(
        bridge["current_snapshot_payload_sha256"],
        label="current snapshot payload SHA-256",
    )
    _sha256(
        bridge["actual_dwr_report_sha256"],
        label="actual DWR report SHA-256",
    )
    bridge_dwr = _mapping(
        bridge["signed_dwr_delta"],
        label="live bridge signed DWR mapping",
    )
    if set(bridge_dwr) != set(FORMAL_GOAL_IDS) or any(
        _finite(bridge_dwr[goal_id], label=f"bridge DWR {goal_id}")
        != signed_dwr[goal_id]
        for goal_id in FORMAL_GOAL_IDS
    ):
        raise ShadowBundleError(
            "live-shadow bridge DWR differs from its nested evidence"
        )
    expected_effectivity, expected_actual = _recomputed_live_effectivity(
        signed_dwr=signed_dwr,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
    )
    actual_row = _mapping(
        bridge["actual_endpoint_delta"],
        label="live bridge endpoint delta",
    )
    if (
        set(actual_row) != set(FORMAL_GOAL_IDS)
        or any(
            _finite(
                actual_row[goal_id],
                label=f"bridge endpoint delta {goal_id}",
            )
            != expected_actual[goal_id]
            for goal_id in FORMAL_GOAL_IDS
        )
        or _canonical(bridge["effectivity_audit"])
        != _canonical(expected_effectivity)
        or expected_effectivity["pass"] is not True
    ):
        raise ShadowBundleError(
            "live-shadow bridge effectivity audit differs or did not pass"
        )
    capability = _exact(
        bridge["capability_credit"],
        frozenset(
            {
                "hash_bound_live_adjoint_complete",
                "post_pde_endpoint_binding_complete",
                "shadow_endpoint_effectivity_complete",
                "accuracy_credit",
            }
        ),
        label="live bridge capability credit",
    )
    if (
        capability["hash_bound_live_adjoint_complete"] is not True
        or capability["post_pde_endpoint_binding_complete"] is not True
        or capability["shadow_endpoint_effectivity_complete"] is not True
        or capability["accuracy_credit"] is not False
    ):
        raise ShadowBundleError(
            "live-shadow bridge capability credit is invalid"
        )


def _validate_dwr_evidence(
    raw: Mapping[str, Any],
    *,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
    current_goals: GoalVector,
    shadow_goals: GoalVector,
    action_id: str,
    kind: str,
    target_ids: tuple[str, ...],
    transition_action_sha256: str,
    transition_action_file_sha256: str,
    transition_action_identity_sha256: str,
    live_bridge: Mapping[str, Any] | None,
) -> tuple[dict[str, float], bool]:
    row = _exact(raw, _DWR_EVIDENCE_KEYS, label="DWR evidence payload")
    evaluator = _exact(
        row["evaluator"],
        _DWR_EVALUATOR_KEYS,
        label="DWR evaluator identity",
    )
    _opaque_id(evaluator["evaluator_id"], label="DWR evaluator ID")
    evaluator_source = _source_sha(
        evaluator["evaluator_source_sha"],
        label="DWR evaluator source SHA",
    )
    for name in (
        "implementation_sha256",
        "primal_residual_sha256",
        "adjoint_system_sha256",
    ):
        _sha256(evaluator[name], label=f"DWR evaluator {name}")
    if (
        evaluator["schema_version"] != DWR_EVALUATOR_SCHEMA
        or evaluator_source != current.source_sha
        or evaluator["method"] != "signed_residual_weighted_adjoint"
    ):
        raise ShadowBundleError(
            "DWR evaluator identity, source, or method differs"
        )

    evidence_targets = tuple(
        _opaque_id(value, label="DWR target ID")
        for value in _sequence(row["target_ids"], label="DWR target IDs")
    )
    identity = (
        row["schema_version"] == DWR_EVIDENCE_SCHEMA,
        row["producer_role"] == DWR_PRODUCER_ROLE,
        row["source_sha"] == current.source_sha == shadow.source_sha,
        row["mpi_size"] == 8,
        row["trial_id"] == current.trial_id == shadow.trial_id,
        row["cycle_index"] == current.cycle_index == shadow.cycle_index,
        row["action_id"] == action_id,
        row["kind"] == kind,
        evidence_targets == target_ids,
        row["transition_action_sha256"] == transition_action_sha256,
        row["transition_action_file_sha256"]
        == transition_action_file_sha256,
        row["transition_action_identity_sha256"]
        == transition_action_identity_sha256,
        row["current_output_sha256"] == current.output_sha256,
        row["shadow_output_sha256"] == shadow.output_sha256,
        row["current_watchdog_record_sha256"] == current.record_sha256,
        row["shadow_watchdog_record_sha256"] == shadow.record_sha256,
        row["current_plan_file_sha256"] == current.plan_file_sha256,
        row["shadow_plan_file_sha256"] == shadow.plan_file_sha256,
        row["current_config_sha256"] == current.config_sha256,
        row["shadow_config_sha256"] == shadow.config_sha256,
        row["current_mesh_forest_sha256"]
        == current.forest_leaf_catalog_sha256,
        row["current_degree_map_sha256"]
        == current.cell_degree_plan_sha256,
        row["shadow_mesh_forest_sha256"]
        == shadow.forest_leaf_catalog_sha256,
        row["shadow_degree_map_sha256"]
        == shadow.cell_degree_plan_sha256,
        row["current_goal_sha256"] == current_goals.sha256,
        row["shadow_goal_sha256"] == shadow_goals.sha256,
        row["formal_goal_count"] == len(FORMAL_GOAL_IDS),
        row["formal_goal_inventory_sha256"]
        == FORMAL_GOAL_INVENTORY_SHA256,
        row["actual_adjoint_solve"] is True,
        row["actual_dwr_evaluation"] is True,
        row["signed_not_absolute"] is True,
        row["endpoint_delta_used_as_dwr"] is False,
        row["synthetic"] is False,
        row["reference_derived"] is False,
    )
    if not all(identity):
        raise ShadowBundleError(
            "DWR evidence identity, MPI8, cycle, transition, or role differs"
        )
    _source_sha(row["source_sha"])
    _sha256(
        row["transition_action_sha256"],
        label="transition action SHA-256",
    )
    for name in (
        "transition_action_file_sha256",
        "transition_action_identity_sha256",
        "current_plan_file_sha256",
        "shadow_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "shadow_mesh_forest_sha256",
        "shadow_degree_map_sha256",
    ):
        _sha256(row[name], label=name)
    dwr_raw = _mapping(
        row["signed_dwr_delta"],
        label="signed DWR mapping",
    )
    if set(dwr_raw) != set(FORMAL_GOAL_IDS):
        raise ShadowBundleError(
            "actual DWR evidence does not contain all 59 formal goals"
        )
    signed_dwr = {
        goal_id: _finite(dwr_raw[goal_id], label=f"DWR {goal_id}")
        for goal_id in FORMAL_GOAL_IDS
    }
    computed_sign = dwr_endpoint_sign_consistent(
        signed_dwr,
        current=current_goals,
        shadow=shadow_goals,
    )
    if type(row["sign_consistent"]) is not bool:
        raise ShadowBundleError("DWR sign_consistent must be boolean")
    if row["sign_consistent"] is not computed_sign:
        raise ShadowBundleError(
            "DWR sign_consistent differs from prediction/endpoint content"
        )
    _validate_live_bridge(
        live_bridge,
        current=current,
        shadow=shadow,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        signed_dwr=signed_dwr,
        action_id=action_id,
        kind=kind,
        target_ids=target_ids,
        transition_action_sha256=transition_action_sha256,
        transition_action_file_sha256=transition_action_file_sha256,
        transition_action_identity_sha256=(
            transition_action_identity_sha256
        ),
    )
    return signed_dwr, computed_sign


def _action_row(
    raw: Any,
    *,
    base: Path,
    lane: str,
    current: AdaptedCandidateOutput,
    current_goals: GoalVector,
) -> tuple[dict[str, Any], str]:
    row = _exact(raw, _ACTION_REQUEST_KEYS, label=f"{lane} action request")
    transition_bound = _bound_reference(
        row["transition_action"],
        base=base,
        label="hp transition action",
    )
    transition, transition_file_sha, transition_representation = (
        _load_transition_action(transition_bound)
    )
    action_id = str(transition["action_id"])
    kind = str(transition["kind"])
    expected_kind = "p-up" if lane == "p" else "h-refine"
    if kind != expected_kind:
        raise ShadowBundleError(
            f"{lane} action must use kind {expected_kind}"
        )
    target_ids = tuple(
        _opaque_id(value, label="shadow target ID")
        for value in _sequence(
            transition["canonical_target_ids"],
            label="hp transition canonical target IDs",
        )
    )
    transition_sha = str(transition["action_sha256"])
    marking_bound = _bound_reference(
        row["goal_marking"],
        base=base,
        label="goal marking",
    )
    marking = _load_goal_marking(
        marking_bound,
        current=current,
        current_goals=current_goals,
        transition=transition,
        target_ids=target_ids,
    )
    prediction_bound = _bound_reference(
        row["verification_prediction"],
        base=base,
        label="verification prediction",
    )
    prediction = _load_verification_prediction(
        prediction_bound,
        marking=marking,
        transition=transition,
    )
    shadow_record = _bound_reference(
        row["shadow_record"],
        base=base,
        label="shadow watchdog record",
    )
    shadow = _adapt_record(
        shadow_record,
        output_role=f"{lane}-shadow",
    )
    if (
        shadow.source_sha != current.source_sha
        or shadow.trial_id != current.trial_id
        or shadow.cycle_index != current.cycle_index
    ):
        raise ShadowBundleError(
            "current and shadow records do not share source/trial/cycle"
        )
    transition_identity = (
        transition["source_sha"]
        == current.source_sha
        == shadow.source_sha,
        transition["cycle_index"] == current.cycle_index + 1,
        transition["from_leaf_catalog_sha256"]
        == current.forest_leaf_catalog_sha256,
        transition["from_cell_degree_plan_sha256"]
        == current.cell_degree_plan_sha256,
        transition["expected_next_leaf_catalog_sha256"]
        == shadow.forest_leaf_catalog_sha256,
        transition["expected_next_cell_degree_plan_sha256"]
        == shadow.cell_degree_plan_sha256,
    )
    if not all(transition_identity):
        raise ShadowBundleError(
            "hp transition does not bind current/next plan identities or cycle"
        )
    _validate_shadow_plan_provenance(
        current=current,
        shadow=shadow,
        transition=transition,
    )
    shadow_goals = _goals(shadow)
    dwr_bound = _bound_reference(
        row["dwr_evidence"],
        base=base,
        label="DWR evidence",
    )
    dwr_payload, dwr_file_sha, live_bridge = _load_outer_evidence(dwr_bound)
    selected_shadow_global_dwr, _global_sign_consistent = (
        _validate_dwr_evidence(
            dwr_payload,
            current=current,
            shadow=shadow,
            current_goals=current_goals,
            shadow_goals=shadow_goals,
            action_id=action_id,
            kind=str(kind),
            target_ids=target_ids,
            transition_action_sha256=transition_sha,
            transition_action_file_sha256=transition_file_sha,
            transition_action_identity_sha256=str(
                transition["action_identity_sha256"]
            ),
            live_bridge=live_bridge,
        )
    )
    selected_prediction_effectivity, _selected_actual_delta = (
        _recomputed_live_effectivity(
            signed_dwr=prediction.signed_dwr_delta,
            current_goals=current_goals,
            shadow_goals=shadow_goals,
        )
    )
    sign_consistent = dwr_endpoint_sign_consistent(
        prediction.signed_dwr_delta,
        current=current_goals,
        shadow=shadow_goals,
    )
    if (
        sign_consistent is not True
        or selected_prediction_effectivity["pass"] is not True
    ):
        raise ShadowBundleError(
            "selected-local verification prediction did not pass the "
            "59-goal sign/effectivity gate"
        )
    cost, signed_structural_delta, measured_structural_benefit = _derived_cost(
        current=current,
        shadow=shadow,
    )
    added_leaves = int(transition["expected_net_added_leaf_count"])
    try:
        action = build_shadow_action(
            action_id=action_id,
            kind=str(kind),
            target_ids=target_ids,
            current=current_goals,
            shadow=shadow_goals,
            signed_dwr_delta=prediction.signed_dwr_delta,
            cost=cost,
            sign_consistent=sign_consistent,
            transition_action_sha256=transition_sha,
            transition_action_file_sha256=transition_file_sha,
            transition_action_identity_sha256=str(
                transition["action_identity_sha256"]
            ),
            next_mesh_forest_sha256=(
                shadow.forest_leaf_catalog_sha256
            ),
            next_degree_map_sha256=shadow.cell_degree_plan_sha256,
            actual_added_leaf_count=added_leaves,
        )
    except ValueError as exc:
        raise ShadowBundleError(str(exc)) from exc
    return (
        {
            "action_id": action.action_id,
            "kind": action.kind,
            "target_ids": list(action.target_ids),
            "current_goal_sha256": current_goals.sha256,
            "shadow_goals": {
                goal_id: shadow_goals.by_id[goal_id]
                for goal_id in FORMAL_GOAL_IDS
            },
            "signed_dwr_delta": {
                goal_id: prediction.signed_dwr_delta[goal_id]
                for goal_id in FORMAL_GOAL_IDS
            },
            "cost": {
                name: getattr(cost, name)
                for name in ShadowCost.__dataclass_fields__
            },
            "sign_consistent": sign_consistent,
            "actual_added_leaf_count": added_leaves,
            "transition_action_sha256": action.transition_action_sha256,
            "transition_action_file_sha256": (
                action.transition_action_file_sha256
            ),
            "transition_action_identity_sha256": (
                action.transition_action_identity_sha256
            ),
            "next_mesh_forest_sha256": action.next_mesh_forest_sha256,
            "next_degree_map_sha256": action.next_degree_map_sha256,
            "action_sha256": action.action_sha256,
            "external_evidence": {
                "actual_shadow_solve": True,
                "actual_dwr_evaluation": True,
                "shadow_output_sha256": shadow.output_sha256,
                "dwr_evidence_sha256": dwr_file_sha,
                "goal_marking_file_sha256": marking.file_sha256,
                "goal_marking_payload_sha256": marking.payload_sha256,
                "goal_marking_selection_role": marking.selection_role,
                "verification_prediction_file_sha256": (
                    prediction.file_sha256
                ),
                "verification_prediction_payload_sha256": (
                    prediction.payload_sha256
                ),
                "verification_prediction_marking_file_sha256": (
                    prediction.marking_file_sha256
                ),
                "verification_prediction_marking_payload_sha256": (
                    prediction.marking_payload_sha256
                ),
                "selected_shadow_global_dwr_sha256": (
                    _selected_shadow_global_dwr_sha256(
                        selected_shadow_global_dwr
                    )
                ),
                "transition_action_sha256": transition_sha,
                "transition_action_file_sha256": transition_file_sha,
                "transition_action_identity_sha256": transition[
                    "action_identity_sha256"
                ],
                "transition_action_representation": (
                    transition_representation
                ),
                "current_watchdog_record_sha256": current.record_sha256,
                "shadow_watchdog_record_sha256": shadow.record_sha256,
                "current_plan_file_sha256": current.plan_file_sha256,
                "shadow_plan_file_sha256": shadow.plan_file_sha256,
                "from_leaf_catalog_sha256": (
                    current.forest_leaf_catalog_sha256
                ),
                "from_cell_degree_plan_sha256": (
                    current.cell_degree_plan_sha256
                ),
                "next_leaf_catalog_sha256": (
                    shadow.forest_leaf_catalog_sha256
                ),
                "next_cell_degree_plan_sha256": (
                    shadow.cell_degree_plan_sha256
                ),
                "signed_structural_delta": signed_structural_delta,
                "measured_structural_benefit": (
                    measured_structural_benefit
                ),
            },
        },
        dwr_file_sha,
    )


def build_shadow_bundle(
    request_input: BoundJSONInput,
) -> BuiltShadowBundle:
    """Build a blind-cycle-compatible bundle from actual external evidence."""

    request, request_sha = _load_bound_json(
        request_input,
        label="shadow bundle request",
    )
    request = _exact(request, _REQUEST_KEYS, label="shadow bundle request")
    if request["schema_version"] != REQUEST_SCHEMA:
        raise ShadowBundleError("shadow bundle request schema differs")
    request_base = request_input.path.resolve().parent
    current_bound = _bound_reference(
        request["current_record"],
        base=request_base,
        label="current watchdog record",
    )
    current = _adapt_record(current_bound, output_role="current")
    current_goals = _goals(current)
    p6_saturation, has_p_up_target = (
        _current_p6_saturation_authority(current)
    )
    h_level3_saturation, has_h_refine_target = (
        _current_h_level3_saturation_authority(current)
    )
    p_rows: list[dict[str, Any]] = []
    h_rows: list[dict[str, Any]] = []
    dwr_hashes: list[str] = []
    for lane, source, destination in (
        ("p", request["p_actions"], p_rows),
        ("h", request["h_actions"], h_rows),
    ):
        actions = _sequence(source, label=f"{lane} action requests")
        if not actions:
            if lane == "p" and not has_p_up_target:
                continue
            if lane == "h" and not has_h_refine_target:
                continue
            raise ShadowBundleError(
                f"formal bundle requires at least one {lane} action"
            )
        for raw in actions:
            action, dwr_sha = _action_row(
                raw,
                base=request_base,
                lane=lane,
                current=current,
                current_goals=current_goals,
            )
            destination.append(action)
            dwr_hashes.append(dwr_sha)
    action_ids = [
        str(row["action_id"]) for row in (*p_rows, *h_rows)
    ]
    if len(set(action_ids)) != len(action_ids):
        raise ShadowBundleError("shadow action IDs are not globally unique")
    payload: dict[str, Any] = {
        "schema_version": SHADOW_BUNDLE_SCHEMA,
        "producer_role": PRODUCER_ROLE,
        "source_sha": current.source_sha,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "mesh_forest_sha256": current.forest_leaf_catalog_sha256,
        "degree_map_sha256": current.cell_degree_plan_sha256,
        "complete_output_sha256": current.output_sha256,
        "current_goal_sha256": current_goals.sha256,
        "actual_shadow_solves": True,
        "actual_dwr_evaluations": True,
        "synthetic": False,
        "reference_derived": False,
        "p6_saturation": p6_saturation_authority_payload(
            p6_saturation
        ),
        "h_level3_saturation": h_level3_saturation_authority_payload(
            h_level3_saturation
        ),
        "p_actions": p_rows,
        "h_actions": h_rows,
    }
    return BuiltShadowBundle(
        payload=payload,
        payload_sha256=_json_sha256(payload),
        request_file_sha256=request_sha,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
        current_output_sha256=current.output_sha256,
        dwr_evidence_file_sha256=tuple(dwr_hashes),
    )


def write_shadow_bundle(
    path: Path | str,
    built: BuiltShadowBundle,
    *,
    overwrite: bool = False,
) -> ShadowBundleWriteReceipt:
    """Atomically write one immutable, self-hashed, mode-0600 bundle."""

    if overwrite:
        raise ShadowBundleError("formal shadow bundles are immutable")
    destination = _safe_path(Path(path), label="shadow bundle output")
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite shadow bundle: {destination}"
        )
    if _json_sha256(built.payload) != built.payload_sha256:
        raise ShadowBundleError("shadow bundle changed after construction")
    outer = {
        "schema_version": SHADOW_BUNDLE_SCHEMA,
        "sha256": built.payload_sha256,
        "payload": built.payload,
    }
    encoded = (
        json.dumps(
            outer,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, destination)
        temporary_path.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return ShadowBundleWriteReceipt(
        path=destination,
        file_sha256=_file_sha256(destination),
        payload_sha256=built.payload_sha256,
        byte_count=len(encoded),
        source_sha=built.source_sha,
        trial_id=built.trial_id,
        cycle_index=built.cycle_index,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        built = build_shadow_bundle(
            BoundJSONInput(args.request, args.request_sha256)
        )
        receipt = write_shadow_bundle(args.output, built)
    except (FileExistsError, ShadowBundleError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": (
                        "task035e.shadow-bundle-producer-receipt.v1"
                    ),
                    "status": "failed",
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": (
                    "task035e.shadow-bundle-producer-receipt.v1"
                ),
                "status": "completed",
                "file_sha256": receipt.file_sha256,
                "payload_sha256": receipt.payload_sha256,
                "source_sha": receipt.source_sha,
                "trial_id": receipt.trial_id,
                "cycle_index": receipt.cycle_index,
                "byte_count": receipt.byte_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DWR_EVALUATOR_SCHEMA",
    "DWR_EVIDENCE_SCHEMA",
    "DWR_PRODUCER_ROLE",
    "GOAL_MARKING_SCHEMA",
    "REQUEST_SCHEMA",
    "VERIFICATION_PREDICTION_SCHEMA",
    "BoundJSONInput",
    "BuiltShadowBundle",
    "ShadowBundleError",
    "ShadowBundleWriteReceipt",
    "build_shadow_bundle",
    "main",
    "write_shadow_bundle",
]
