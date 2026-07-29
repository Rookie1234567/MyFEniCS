#!/usr/bin/env python3
"""Produce one immutable, reference-blind Task035e local h/p marking.

This module is the deliberately narrow bridge between live 59-goal DWR
evidence and :mod:`benchmarks.task035e_transition_producer`.  It never reads a
sealed reference or a hidden-auditor result.  A successful result contains
canonical current-leaf IDs that may be passed, unchanged, as repeated
``--target-id`` arguments to the transition producer.

The global live-DWR report alone contains one signed estimator per goal for
the *whole* shadow system and cannot identify a cell.  When that report is
supplied directly, this producer writes a hash-bound ``controlled_negative``.
The positive path requires the observer's actual cellwise partition plus the
separately hash-bound structural-cost model built by
``task035e_cellwise_authority``.  It never repeats global eta on every cell or
uses a geometry-only error heuristic.

The success path is intentionally available only for the closed
``CELLWISE_DWR_AUTHORITY_SCHEMA`` contract.  That authority must contain:

* all 59 fixed N=8 current and shadow goal values;
* one actual global live-DWR report;
* a complete, signed contribution partition over every current leaf; and
* per-leaf structural cost estimates.

Signed cell contributions must close back to every global eta.  Absolute
normalized magnitudes are used only for deterministic multi-goal Dörfler
ranking; they never replace the signed estimator identity.
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

from benchmarks.task035e_cellwise_authority import (
    CELLWISE_DWR_AUTHORITY_SCHEMA,
    CellwiseAuthorityError,
    validate_structural_cost_model,
)
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
    blind_tolerance,
)
from src.adaptivity.task035e_actual_dwr import (
    ACTUAL_DWR_SCHEMA,
    CELLWISE_DWR_PARTITION_SCHEMA,
)
from src.adaptivity.task035e_hp_transition import (
    canonical_hp_cell_target_id,
    hp_transition_action_payload,
)
from src.adaptivity.task035e_plan_transition import (
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


GOAL_MARKING_SCHEMA = "task035e.reference-blind-goal-marking.v1"
GOAL_MARKING_RECEIPT_SCHEMA = (
    "task035e.reference-blind-goal-marking-write-receipt.v1"
)
GOAL_MARKING_ALGORITHM_ID = (
    "task035e.equal-59-goal-cost-aware-doerfler-v1"
)
DEFAULT_DOERFLER_THETA = 0.5
_MINIMUM_GLOBAL_NORMALIZED_SIGNAL = 0.5
_MINIMUM_ELIGIBLE_EQUAL_WEIGHT_BENEFIT = (
    _MINIMUM_GLOBAL_NORMALIZED_SIGNAL / len(FORMAL_GOAL_IDS)
)
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ACTION_KINDS = frozenset({"p-up", "h-refine"})
_SHADOW_BY_ACTION = {"p-up": "p-shadow", "h-refine": "h-shadow"}
_FORMAL_H = frozenset({15.0, 20.0})
_FORBIDDEN_PATH_PARTS = frozenset(
    {
        "reference_certifier",
        "hidden_auditor",
        "sealed_reference",
        "sealed-reference",
    }
)
_FORBIDDEN_CONTENT_TOKENS = frozenset(
    {
        "hidden_reference",
        "sealed_reference",
        "reference_value",
        "reference_field",
        "candidate_vs_reference",
        "reference_error_map",
        "hidden_auditor",
    }
)
_GLOBAL_DWR_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "source_sha",
        "shadow_kind",
        "request_sha256",
        "shadow_plan_identity",
        "layout_identity",
        "operator_identity",
        "implementation_identity",
        "shadow_primal_gate",
        "current_primal_in_shadow",
        "shadow_rhs",
        "shadow_action_on_current",
        "enriched_current_residual",
        "goal_inventory",
        "goals",
        "aggregate_identities",
        "algebra",
        "capability_credit",
        "ordinary_default_changed",
        "report_sha256",
    }
)
_GLOBAL_DWR_OPTIONAL_FIELDS = frozenset(
    {"active_interior_affine_complement"}
)
_CELLWISE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "producer_role",
        "source_sha",
        "mpi_size",
        "trial_id",
        "cycle_index",
        "action_kind",
        "current_plan_file_sha256",
        "current_plan_content_sha256",
        "current_state_sha256",
        "current_leaf_catalog_sha256",
        "current_degree_plan_sha256",
        "current_watchdog_record_sha256",
        "shadow_watchdog_record_sha256",
        "current_output_file_sha256",
        "shadow_output_file_sha256",
        "current_output_sha256",
        "shadow_output_sha256",
        "live_shadow_evidence_file_sha256",
        "live_shadow_evidence_payload_sha256",
        "current_goal_values",
        "current_goal_sha256",
        "shadow_goal_values",
        "shadow_goal_sha256",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "ordered_goal_ids",
        "global_actual_dwr_report",
        "localization",
        "structural_cost_model",
        "actual_cellwise_residual_adjoint_pairing",
        "signed_not_absolute",
        "synthetic",
        "reference_derived",
        "hidden_auditor_consumed",
        "ordinary_default_changed",
        "authority_sha256",
    }
)
_LOCALIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "method",
        "method_detail",
        "complete_current_leaf_partition",
        "global_signed_closure_verified",
        "actual_cellwise_residual_adjoint_pairing",
        "global_eta_evenly_distributed",
        "endpoint_delta_consumed",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "ordered_goal_ids",
        "current_plan_identity",
        "shadow_plan_identity",
        "row_designation_identity",
        "residual_partition_catalog_sha256",
        "adjoint_partition_catalog_sha256",
        "maximum_global_signed_closure_error",
        "rows",
        "python_full_vector_gather_used",
        "native_fixed_size_hash_metadata_reduction",
        "native_leaf_goal_scalar_reduction",
        "partition_sha256",
    }
)
_LOCALIZATION_AFFINE_FIELDS = frozenset(
    {
        "active_interior_affine_complement_present",
        "active_full_gradient_goal_count",
    }
)
_CELL_ROW_FIELDS = frozenset(
    {
        "target_id",
        "current_leaf_key",
        "current_leaf_box",
        "current_leaf_degree",
        "assigned_reduced_row_count",
        "assigned_trace_row_count",
        "assigned_auxiliary_row_count",
        "local_residual_partition_sha256",
        "local_adjoint_partition_sha256",
        "signed_dwr_contribution",
        "row_sha256",
    }
)
_CELL_ROW_AFFINE_FIELDS = frozenset(
    {
        "assigned_active_interior_row_count",
        "local_affine_complement_partition_sha256",
        "reduced_trace_auxiliary_contribution",
        "active_interior_affine_complement_contribution",
    }
)
_COST_FIELDS = (
    "estimated_added_active_dofs",
    "estimated_added_rows",
    "estimated_added_matrix_nnz",
    "estimated_added_factor_nnz",
    "estimated_added_solver_peak_bytes",
)


class GoalMarkingError(ValueError):
    """Raised when a marking input or output identity is invalid."""


@dataclass(frozen=True, slots=True)
class GoalMarkingWriteReceipt:
    """Identity and classification of one immutable marking artifact."""

    path: Path
    file_sha256: str
    marking_sha256: str
    status: str
    classification: str
    canonical_target_ids: tuple[str, ...]
    byte_count: int


def _reject_nonfinite(value: str) -> None:
    raise GoalMarkingError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GoalMarkingError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _json_sha256(value: Any, *, namespace: str | None = None) -> str:
    digest = hashlib.sha256()
    if namespace is not None:
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


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GoalMarkingError(f"{label} must be one lowercase SHA-256")
    return value


def _source_sha(value: Any) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise GoalMarkingError(
            "source SHA must be one 40-character lowercase Git SHA"
        )
    return value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GoalMarkingError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise GoalMarkingError(f"{label} must be a JSON array")
    return value


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalMarkingError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise GoalMarkingError(f"{label} must be finite")
    return result


def _nonnegative_integer(value: Any, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise GoalMarkingError(f"{label} must be a nonnegative integer")
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    lowered = {part.lower() for part in resolved.parts}
    if lowered & _FORBIDDEN_PATH_PARTS:
        raise GoalMarkingError(f"{label} crosses a forbidden layer")
    return resolved


def _private_regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise GoalMarkingError(f"{label} must not be a symlink")
    resolved = _safe_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise GoalMarkingError(f"{label} is not readable: {resolved}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise GoalMarkingError(f"{label} must be a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise GoalMarkingError(f"{label} must use mode 0600")
    return resolved


def _strict_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoalMarkingError(f"cannot read strict {label}: {path}") from exc
    return _mapping(value, label=label)


def _reject_reference_leak(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if lowered in {
                "reference_solution_consumed",
                "hidden_auditor_consumed",
            }:
                if item is not False:
                    raise GoalMarkingError(
                        f"blind authority sets forbidden flag {key}=true"
                    )
            elif any(token in lowered for token in _FORBIDDEN_CONTENT_TOKENS):
                raise GoalMarkingError(
                    f"forbidden reference/evaluator field at {path}.{key}"
                )
            _reject_reference_leak(item, path=f"{path}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_reference_leak(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in _FORBIDDEN_PATH_PARTS):
            raise GoalMarkingError(
                f"forbidden reference/evaluator value at {path}"
            )


def _load_bound_private_json(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[Mapping[str, Any], Path, str]:
    expected = _sha256(expected_sha256, label=f"{label} file SHA-256")
    resolved = _private_regular_file(path, label=label)
    observed = _file_sha256(resolved)
    if observed != expected:
        raise GoalMarkingError(f"{label} file SHA-256 mismatch")
    payload = _strict_json(resolved, label=label)
    _reject_reference_leak(payload)
    return payload, resolved, observed


def _current_state(
    plan: Mapping[str, Any],
    *,
    source_sha: str,
) -> Any:
    base = _mapping(plan.get("base_config"), label="current plan base_config")
    raw_h = base.get("mesh_target_size")
    if isinstance(raw_h, bool) or not isinstance(raw_h, (int, float)):
        raise GoalMarkingError("current plan mesh_target_size is not numeric")
    h_nm = float(raw_h)
    if not any(abs(h_nm - expected) <= 1.0e-12 for expected in _FORMAL_H):
        raise GoalMarkingError(
            "current plan is not a formal Task035e Path A/B base family"
        )
    try:
        state = rebuild_hp_transition_state_from_solver_plan(
            target_stage4_config(degree=6, h_nm=h_nm),
            current_plan=plan,
            comm_size=8,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        raise GoalMarkingError(
            f"current solver plan cannot be replayed: {exc}"
        ) from exc
    if state.source_sha != source_sha:
        raise GoalMarkingError(
            "current solver plan source differs from verified clean SHA"
        )
    return state


def _validate_global_dwr(
    raw: Mapping[str, Any],
    *,
    source_sha: str,
    action_kind: str,
    current_cycle_index: int,
) -> tuple[Mapping[str, float], str]:
    if (
        not _GLOBAL_DWR_FIELDS.issubset(set(raw))
        or not set(raw).issubset(
            _GLOBAL_DWR_FIELDS | _GLOBAL_DWR_OPTIONAL_FIELDS
        )
    ):
        raise GoalMarkingError(
            "global actual DWR report has unknown or missing fields"
        )
    observed_report_sha = _sha256(
        raw.get("report_sha256"),
        label="actual DWR report SHA-256",
    )
    unsigned = dict(raw)
    unsigned.pop("report_sha256")
    expected_report_sha = _json_sha256(
        unsigned,
        namespace="task035e.actual-live-shadow-dwr-report.v1",
    )
    inventory = _mapping(
        raw.get("goal_inventory"),
        label="actual DWR goal inventory",
    )
    plan_identity = _mapping(
        raw.get("shadow_plan_identity"),
        label="actual DWR shadow plan identity",
    )
    algebra = _mapping(raw.get("algebra"), label="actual DWR algebra")
    capability = _mapping(
        raw.get("capability_credit"),
        label="actual DWR capability",
    )
    affine = (
        _mapping(
            raw.get("active_interior_affine_complement"),
            label="actual DWR affine complement",
        )
        if "active_interior_affine_complement" in raw
        else None
    )
    expected_shadow = _SHADOW_BY_ACTION[action_kind]
    if (
        observed_report_sha != expected_report_sha
        or raw.get("schema_version") != ACTUAL_DWR_SCHEMA
        or raw.get("status") != "actual_live_shadow_dwr_pass"
        or raw.get("pass") is not True
        or raw.get("source_sha") != source_sha
        or raw.get("shadow_kind") != expected_shadow
        or raw.get("ordinary_default_changed") is not False
        or inventory.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
        or inventory.get("formal_goal_inventory_sha256")
        != FORMAL_GOAL_INVENTORY_SHA256
        or tuple(inventory.get("ordered_goal_ids", ())) != FORMAL_GOAL_IDS
        or plan_identity.get("provenance_cycle_index")
        != current_cycle_index + 1
        or algebra.get("endpoint_goal_delta_consumed") is not False
        or algebra.get("reference_solution_consumed") is not False
        or capability.get("actual_enriched_residual_complete") is not True
        or capability.get("actual_59_goal_adjoint_complete") is not True
        or capability.get("actual_signed_dwr_complete") is not True
        or (
            affine is not None
            and (
                affine.get("present") is not True
                or capability.get(
                    "static_condensation_affine_complement_complete"
                )
                is not True
            )
        )
        or capability.get("accuracy_credit") is not False
    ):
        raise GoalMarkingError(
            "global actual DWR identity, cycle, role, or capability differs"
        )
    rows = _sequence(raw.get("goals"), label="actual DWR goals")
    if (
        len(rows) != len(FORMAL_GOAL_IDS)
        or tuple(
            _mapping(row, label="actual DWR goal row").get("goal_id")
            for row in rows
        )
        != FORMAL_GOAL_IDS
    ):
        raise GoalMarkingError(
            "global actual DWR does not contain the ordered 59 goals"
        )
    signed: dict[str, float] = {}
    for goal_id, raw_row in zip(FORMAL_GOAL_IDS, rows, strict=True):
        row = _mapping(raw_row, label=f"actual DWR goal {goal_id}")
        signed[goal_id] = _finite(
            row.get("signed_eta_real_zH_r"),
            label=f"global signed eta {goal_id}",
        )
        if (
            row.get("actual_adjoint_solve_complete") is not True
            or row.get("endpoint_goal_delta_consumed") is not False
        ):
            raise GoalMarkingError(
                f"global actual DWR goal {goal_id} is not actual/signed"
            )
    return signed, observed_report_sha


def _goal_vector(
    raw: Any,
    *,
    observed_sha256: Any,
    label: str,
) -> GoalVector:
    mapping = _mapping(raw, label=label)
    try:
        values = {
            goal_id: _finite(
                mapping.get(goal_id),
                label=f"{label} {goal_id}",
            )
            for goal_id in FORMAL_GOAL_IDS
        }
        if set(mapping) != set(FORMAL_GOAL_IDS):
            raise GoalMarkingError(
                f"{label} does not contain exactly 59 formal goals"
            )
        result = GoalVector.from_mapping(values)
    except ValueError as exc:
        raise GoalMarkingError(str(exc)) from exc
    if result.sha256 != _sha256(
        observed_sha256,
        label=f"{label} SHA-256",
    ):
        raise GoalMarkingError(f"{label} SHA-256 mismatch")
    return result


def _signed_goal_mapping(raw: Any, *, label: str) -> dict[str, float]:
    mapping = _mapping(raw, label=label)
    if set(mapping) != set(FORMAL_GOAL_IDS):
        raise GoalMarkingError(f"{label} must contain exactly 59 goals")
    return {
        goal_id: _finite(mapping[goal_id], label=f"{label} {goal_id}")
        for goal_id in FORMAL_GOAL_IDS
    }


def _cell_row_unsigned(row: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(row)
    unsigned.pop("row_sha256", None)
    return unsigned


def _validate_cellwise_authority(
    raw: Mapping[str, Any],
    *,
    authority_file_sha256: str,
    plan_file_sha256: str,
    plan_content_sha256: str,
    source_sha: str,
    action_kind: str,
    state: Any,
) -> dict[str, Any]:
    if set(raw) != _CELLWISE_FIELDS:
        raise GoalMarkingError(
            "cellwise DWR authority has unknown or missing fields"
        )
    observed_authority_sha = _sha256(
        raw.get("authority_sha256"),
        label="cellwise DWR authority SHA-256",
    )
    unsigned = dict(raw)
    unsigned.pop("authority_sha256")
    expected_authority_sha = _json_sha256(
        unsigned,
        namespace=CELLWISE_DWR_AUTHORITY_SCHEMA,
    )
    if observed_authority_sha != expected_authority_sha:
        raise GoalMarkingError("cellwise DWR authority SHA-256 mismatch")
    for name in (
        "current_watchdog_record_sha256",
        "shadow_watchdog_record_sha256",
        "current_output_file_sha256",
        "shadow_output_file_sha256",
        "current_output_sha256",
        "shadow_output_sha256",
        "live_shadow_evidence_file_sha256",
        "live_shadow_evidence_payload_sha256",
    ):
        _sha256(raw.get(name), label=name)
    identity = (
        raw.get("schema_version") == CELLWISE_DWR_AUTHORITY_SCHEMA,
        raw.get("status") == "cellwise_59_goal_dwr_pass",
        raw.get("pass") is True,
        raw.get("producer_role")
        == "live_cellwise_residual_adjoint_localizer",
        raw.get("source_sha") == source_sha,
        raw.get("mpi_size") == 8,
        raw.get("cycle_index") == state.cycle_index,
        raw.get("action_kind") == action_kind,
        raw.get("current_plan_file_sha256") == plan_file_sha256,
        raw.get("current_plan_content_sha256") == plan_content_sha256,
        raw.get("current_state_sha256") == state.state_sha256,
        raw.get("current_leaf_catalog_sha256")
        == state.audit["leaf_catalog_sha256"],
        raw.get("current_degree_plan_sha256")
        == state.audit["cell_degree_plan_sha256"],
        raw.get("formal_goal_count") == len(FORMAL_GOAL_IDS),
        raw.get("formal_goal_inventory_sha256")
        == FORMAL_GOAL_INVENTORY_SHA256,
        tuple(raw.get("ordered_goal_ids", ())) == FORMAL_GOAL_IDS,
        raw.get("actual_cellwise_residual_adjoint_pairing") is True,
        raw.get("signed_not_absolute") is True,
        raw.get("synthetic") is False,
        raw.get("reference_derived") is False,
        raw.get("hidden_auditor_consumed") is False,
        raw.get("ordinary_default_changed") is False,
    )
    if not all(identity):
        raise GoalMarkingError(
            "cellwise DWR authority identity, MPI8, cycle, or blind role differs"
        )
    current = _goal_vector(
        raw.get("current_goal_values"),
        observed_sha256=raw.get("current_goal_sha256"),
        label="current goal values",
    )
    shadow = _goal_vector(
        raw.get("shadow_goal_values"),
        observed_sha256=raw.get("shadow_goal_sha256"),
        label="shadow goal values",
    )
    global_signed, global_report_sha = _validate_global_dwr(
        _mapping(
            raw.get("global_actual_dwr_report"),
            label="embedded global actual DWR report",
        ),
        source_sha=source_sha,
        action_kind=action_kind,
        current_cycle_index=state.cycle_index,
    )
    localization = _mapping(
        raw.get("localization"),
        label="cellwise localization",
    )
    localization_fields = set(localization)
    affine_localization = bool(
        localization_fields & _LOCALIZATION_AFFINE_FIELDS
    )
    if (
        not _LOCALIZATION_FIELDS.issubset(localization_fields)
        or not localization_fields.issubset(
            _LOCALIZATION_FIELDS | _LOCALIZATION_AFFINE_FIELDS
        )
        or (
            affine_localization
            and not _LOCALIZATION_AFFINE_FIELDS.issubset(
                localization_fields
            )
        )
    ):
        raise GoalMarkingError(
            "cellwise localization has unknown or missing fields"
        )
    localization_unsigned = dict(localization)
    observed_partition_sha = _sha256(
        localization_unsigned.pop("partition_sha256", None),
        label="cellwise localization partition SHA-256",
    )
    current_plan_identity = _mapping(
        localization.get("current_plan_identity"),
        label="cellwise current plan identity",
    )
    row_designation = _mapping(
        localization.get("row_designation_identity"),
        label="cellwise row designation identity",
    )
    row_designation_unsigned = dict(row_designation)
    observed_designation_sha = _sha256(
        row_designation_unsigned.pop("designation_sha256", None),
        label="cellwise row designation SHA-256",
    )
    if (
        observed_partition_sha
        != _json_sha256(
            localization_unsigned,
            namespace=CELLWISE_DWR_PARTITION_SCHEMA,
        )
        or localization.get("schema_version")
        != CELLWISE_DWR_PARTITION_SCHEMA
        or localization.get("status")
        != "cellwise_signed_dwr_partition_pass"
        or localization.get("pass") is not True
        or localization.get("method")
        not in {
            "element_residual_adjoint_pairing",
            (
                "reduced_residual_adjoint_plus_active_interior_"
                "affine_complement"
            ),
        }
        or localization.get("complete_current_leaf_partition") is not True
        or localization.get("global_signed_closure_verified") is not True
        or localization.get("actual_cellwise_residual_adjoint_pairing")
        is not True
        or (
            affine_localization
            and (
                localization.get(
                    "active_interior_affine_complement_present"
                )
                is not True
                or type(
                    localization.get("active_full_gradient_goal_count")
                )
                is not int
                or localization["active_full_gradient_goal_count"] <= 0
            )
        )
        or localization.get("global_eta_evenly_distributed") is not False
        or localization.get("endpoint_delta_consumed") is not False
        or localization.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
        or localization.get("formal_goal_inventory_sha256")
        != FORMAL_GOAL_INVENTORY_SHA256
        or tuple(localization.get("ordered_goal_ids", ()))
        != FORMAL_GOAL_IDS
        or localization.get("python_full_vector_gather_used") is not False
        or observed_designation_sha
        != _json_sha256(
            row_designation_unsigned,
            namespace="task035e.actual-dwr-row-designation.v1",
        )
        or current_plan_identity.get("file_sha256") != plan_file_sha256
        or current_plan_identity.get("forest_leaf_catalog_sha256")
        != state.audit["leaf_catalog_sha256"]
        or current_plan_identity.get("cell_degree_plan_sha256")
        != state.audit["cell_degree_plan_sha256"]
    ):
        raise GoalMarkingError(
            "cellwise localization is not a complete signed partition"
        )
    raw_rows = _sequence(
        localization.get("rows"),
        label="cellwise localization rows",
    )
    target_by_id = {
        canonical_hp_cell_target_id(cell.key): cell.key
        for cell in state.forest.leaves
    }
    if len(raw_rows) != len(target_by_id):
        raise GoalMarkingError(
            "cellwise localization does not cover every current leaf"
        )
    rows: dict[str, dict[str, Any]] = {}
    signed_sums = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    absolute_sums = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    residual_partition_hashes: list[str] = []
    adjoint_partition_hashes: list[str] = []
    for index, raw_row in enumerate(raw_rows):
        row = _mapping(raw_row, label=f"cellwise row {index}")
        row_fields = set(row)
        if (
            not _CELL_ROW_FIELDS.issubset(row_fields)
            or not row_fields.issubset(
                _CELL_ROW_FIELDS | _CELL_ROW_AFFINE_FIELDS
            )
            or (
                affine_localization
                and not _CELL_ROW_AFFINE_FIELDS.issubset(row_fields)
            )
        ):
            raise GoalMarkingError(
                f"cellwise row {index} has unknown or missing fields"
            )
        target_id = row.get("target_id")
        if not isinstance(target_id, str) or target_id not in target_by_id:
            raise GoalMarkingError(
                f"cellwise row {index} targets a non-current leaf"
            )
        if target_id in rows:
            raise GoalMarkingError(
                f"cellwise localization duplicates target {target_id}"
            )
        observed_row_sha = _sha256(
            row.get("row_sha256"),
            label=f"cellwise row {index} SHA-256",
        )
        expected_row_sha = _json_sha256(
            _cell_row_unsigned(row),
            namespace="task035e.cellwise-signed-dwr-row.v1",
        )
        if observed_row_sha != expected_row_sha:
            raise GoalMarkingError(
                f"cellwise row {index} SHA-256 mismatch"
            )
        residual_partition_hashes.append(
            _sha256(
                row.get("local_residual_partition_sha256"),
                label=f"cellwise row {index} residual partition",
            )
        )
        adjoint_partition_hashes.append(
            _sha256(
                row.get("local_adjoint_partition_sha256"),
                label=f"cellwise row {index} adjoint partition",
            )
        )
        if affine_localization:
            _sha256(
                row.get("local_affine_complement_partition_sha256"),
                label=f"cellwise row {index} affine partition",
            )
        contribution = _signed_goal_mapping(
            row.get("signed_dwr_contribution"),
            label=f"cellwise row {index} signed contribution",
        )
        if affine_localization:
            reduced_contribution = _signed_goal_mapping(
                row.get("reduced_trace_auxiliary_contribution"),
                label=f"cellwise row {index} reduced contribution",
            )
            affine_contribution = _signed_goal_mapping(
                row.get(
                    "active_interior_affine_complement_contribution"
                ),
                label=f"cellwise row {index} affine contribution",
            )
            for goal_id in FORMAL_GOAL_IDS:
                component_sum = (
                    reduced_contribution[goal_id]
                    + affine_contribution[goal_id]
                )
                scale = max(
                    abs(contribution[goal_id]),
                    abs(component_sum),
                    1.0,
                )
                if (
                    abs(contribution[goal_id] - component_sum)
                    > 1.0e-12 * scale
                ):
                    raise GoalMarkingError(
                        "cellwise reduced plus affine contribution "
                        f"does not close for {goal_id}"
                    )
        rows[target_id] = {
            "target_id": target_id,
            "key": target_by_id[target_id],
            "contribution": contribution,
            "row_sha256": observed_row_sha,
        }
        for goal_id in FORMAL_GOAL_IDS:
            signed_sums[goal_id] += contribution[goal_id]
            absolute_sums[goal_id] += abs(contribution[goal_id])
    if set(rows) != set(target_by_id):
        raise GoalMarkingError(
            "cellwise localization leaf inventory differs from current plan"
        )
    total_reduced_rows = sum(
        _nonnegative_integer(
            _mapping(raw_row, label="cellwise row").get(
                "assigned_reduced_row_count"
            ),
            label="cellwise assigned reduced rows",
        )
        for raw_row in raw_rows
    )
    total_trace_rows = sum(
        _nonnegative_integer(
            _mapping(raw_row, label="cellwise row").get(
                "assigned_trace_row_count"
            ),
            label="cellwise assigned trace rows",
        )
        for raw_row in raw_rows
    )
    total_auxiliary_rows = sum(
        _nonnegative_integer(
            _mapping(raw_row, label="cellwise row").get(
                "assigned_auxiliary_row_count"
            ),
            label="cellwise assigned auxiliary rows",
        )
        for raw_row in raw_rows
    )
    total_active_interior_rows = (
        sum(
            _nonnegative_integer(
                _mapping(raw_row, label="cellwise row").get(
                    "assigned_active_interior_row_count"
                ),
                label="cellwise assigned active-interior rows",
            )
            for raw_row in raw_rows
        )
        if affine_localization
        else None
    )
    if (
        total_reduced_rows != row_designation.get("total_reduced_rows")
        or total_trace_rows
        != row_designation.get("independent_trace_rows")
        or total_auxiliary_rows
        != row_designation.get("appended_auxiliary_rows")
        or total_trace_rows + total_auxiliary_rows != total_reduced_rows
        or (
            affine_localization
            and total_active_interior_rows
            != row_designation.get("active_interior_rows")
        )
        or localization.get("residual_partition_catalog_sha256")
        != _json_sha256(
            residual_partition_hashes,
            namespace=(
                "task035e.actual-dwr.residual-partition-catalog.v1"
            ),
        )
        or localization.get("adjoint_partition_catalog_sha256")
        != _json_sha256(
            adjoint_partition_hashes,
            namespace=(
                "task035e.actual-dwr.adjoint-partition-catalog.v1"
            ),
        )
    ):
        raise GoalMarkingError(
            "cellwise row counts or partition catalogs do not close"
        )
    closure_failures = []
    for goal_id in FORMAL_GOAL_IDS:
        scale = max(
            abs(global_signed[goal_id]),
            absolute_sums[goal_id],
            1.0,
        )
        tolerance = max(1.0e-13, 1.0e-10 * scale)
        if abs(signed_sums[goal_id] - global_signed[goal_id]) > tolerance:
            closure_failures.append(goal_id)
    if closure_failures:
        raise GoalMarkingError(
            "cellwise signed contributions do not close global eta for "
            f"{closure_failures[:3]}"
        )
    try:
        structural_cost_rows, structural_eligibility = (
            validate_structural_cost_model(
                _mapping(
                    raw.get("structural_cost_model"),
                    label="structural cost model",
                ),
                action_kind=action_kind,
                dwr_rows={
                    str(
                        _mapping(row, label="cellwise row")["target_id"]
                    ): _mapping(row, label="cellwise row")
                    for row in raw_rows
                },
            )
        )
    except CellwiseAuthorityError as exc:
        raise GoalMarkingError(str(exc)) from exc
    for target_id in rows:
        rows[target_id]["costs"] = structural_cost_rows[target_id]
        rows[target_id]["structurally_eligible"] = (
            structural_eligibility[target_id]
        )
    return {
        "authority_file_sha256": authority_file_sha256,
        "authority_sha256": observed_authority_sha,
        "current": current,
        "shadow": shadow,
        "global_signed": global_signed,
        "global_report_sha256": global_report_sha,
        "structural_cost_model_sha256": raw[
            "structural_cost_model"
        ]["model_sha256"],
        "rows": rows,
    }


def _fixed_goal_weights() -> dict[str, float]:
    weight = 1.0 / len(FORMAL_GOAL_IDS)
    return {goal_id: weight for goal_id in FORMAL_GOAL_IDS}


def _negative_payload(
    *,
    source_sha: str,
    state: Any,
    action_kind: str,
    theta: float,
    plan_file_sha256: str,
    plan_content_sha256: str,
    authority_file_sha256: str,
    authority_schema: str,
    global_report_sha256: str | None,
    classification: str,
    message: str,
    missing_evidence: Sequence[str],
) -> dict[str, Any]:
    unsigned = {
        "schema_version": GOAL_MARKING_SCHEMA,
        "status": "goal_marking_controlled_negative",
        "classification": classification,
        "pass": False,
        "source_sha": source_sha,
        "mpi_size": 8,
        "cycle_index": state.cycle_index,
        "action_kind": action_kind,
        "doerfler_theta": theta,
        "minimum_global_normalized_signal": (
            _MINIMUM_GLOBAL_NORMALIZED_SIGNAL
        ),
        "minimum_eligible_equal_weight_benefit": (
            _MINIMUM_ELIGIBLE_EQUAL_WEIGHT_BENEFIT
        ),
        "algorithm_id": GOAL_MARKING_ALGORITHM_ID,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "fixed_equal_goal_weights": _fixed_goal_weights(),
        "current_plan_file_sha256": plan_file_sha256,
        "current_plan_content_sha256": plan_content_sha256,
        "current_state_sha256": state.state_sha256,
        "current_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "current_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
        "dwr_authority_file_sha256": authority_file_sha256,
        "dwr_authority_schema": authority_schema,
        "global_actual_dwr_report_sha256": global_report_sha256,
        "signed_closure_used_for_ranking": False,
        "absolute_contributions_used_only_for_ranking": True,
        "ranking": [],
        "canonical_target_ids": [],
        "selected_signed_dwr_delta": None,
        "selected_signed_dwr_delta_sha256": None,
        "transition_producer_arguments": None,
        "blocker": {
            "code": classification,
            "message": message,
            "missing_evidence": list(missing_evidence),
        },
        "reference_derived": False,
        "hidden_auditor_consumed": False,
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "marking_sha256": _json_sha256(
            unsigned,
            namespace=GOAL_MARKING_SCHEMA,
        ),
    }


def _eligible(state: Any, *, action_kind: str, target_id: str) -> bool:
    key_by_id = {
        canonical_hp_cell_target_id(cell.key): cell.key
        for cell in state.forest.leaves
    }
    key = key_by_id[target_id]
    if action_kind == "p-up":
        return int(state.cell_degree_by_key[key]) < 6
    return int(key.level) < 2


def _positive_payload(
    *,
    source_sha: str,
    state: Any,
    action_kind: str,
    theta: float,
    plan_file_sha256: str,
    plan_content_sha256: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    current: GoalVector = evidence["current"]
    shadow: GoalVector = evidence["shadow"]
    rows: Mapping[str, Mapping[str, Any]] = evidence["rows"]
    tolerances = {
        goal_id: blind_tolerance(
            goal_id,
            current.by_id,
            shadow.by_id,
        )
        for goal_id in FORMAL_GOAL_IDS
    }
    weights = _fixed_goal_weights()
    global_normalized = {
        goal_id: abs(evidence["global_signed"][goal_id])
        / tolerances[goal_id]
        for goal_id in FORMAL_GOAL_IDS
    }
    global_maximum = max(global_normalized.values(), default=0.0)
    # The source-bound structural authority owns singleton-action
    # eligibility; its replay validator enforces the zero-cost ineligible
    # contract.  Retain an independent p/level bound here, while the selected
    # set receives a full transition preflight below.
    eligible_rows = {
        target_id: row
        for target_id, row in rows.items()
        if (
            row["structurally_eligible"]
            and _eligible(
                state,
                action_kind=action_kind,
                target_id=target_id,
            )
        )
    }
    if not eligible_rows:
        return _negative_payload(
            source_sha=source_sha,
            state=state,
            action_kind=action_kind,
            theta=theta,
            plan_file_sha256=plan_file_sha256,
            plan_content_sha256=plan_content_sha256,
            authority_file_sha256=evidence["authority_file_sha256"],
            authority_schema=CELLWISE_DWR_AUTHORITY_SCHEMA,
            global_report_sha256=evidence["global_report_sha256"],
            classification="NO_ELIGIBLE_LOCAL_TARGETS",
            message=(
                "the current p/level bounds admit no target for the requested "
                f"{action_kind} lane"
            ),
            missing_evidence=(),
        )
    benefit_by_id = {
        target_id: sum(
            weights[goal_id]
            * abs(row["contribution"][goal_id])
            / tolerances[goal_id]
            for goal_id in FORMAL_GOAL_IDS
        )
        for target_id, row in eligible_rows.items()
    }
    total_benefit = sum(benefit_by_id.values())
    if not math.isfinite(total_benefit):
        raise GoalMarkingError("eligible normalized benefit is non-finite")
    verification_only = bool(
        global_maximum <= _MINIMUM_GLOBAL_NORMALIZED_SIGNAL
    )
    if (
        not verification_only
        and total_benefit <= _MINIMUM_ELIGIBLE_EQUAL_WEIGHT_BENEFIT
    ):
        return _negative_payload(
            source_sha=source_sha,
            state=state,
            action_kind=action_kind,
            theta=theta,
            plan_file_sha256=plan_file_sha256,
            plan_content_sha256=plan_content_sha256,
            authority_file_sha256=evidence["authority_file_sha256"],
            authority_schema=CELLWISE_DWR_AUTHORITY_SCHEMA,
            global_report_sha256=evidence["global_report_sha256"],
            classification="NO_ELIGIBLE_LOCAL_SIGNAL",
            message=(
                "global DWR is above budget but no eligible current leaf has "
                "a positive localized contribution"
            ),
            missing_evidence=(),
        )
    cost_totals = {
        name: sum(row["costs"][name] for row in eligible_rows.values())
        for name in _COST_FIELDS
    }
    ranking = []
    for target_id, row in eligible_rows.items():
        cost_fraction = sum(
            row["costs"][name] / cost_totals[name]
            for name in _COST_FIELDS
        ) / len(_COST_FIELDS)
        if cost_fraction <= 0.0:
            if benefit_by_id[target_id] > 0.0:
                raise GoalMarkingError(
                    f"{target_id} has localized benefit but no attributable "
                    "structural cost"
                )
            efficiency = 0.0
        else:
            efficiency = benefit_by_id[target_id] / cost_fraction
        ranking.append(
            {
                "target_id": target_id,
                "maximum_normalized_absolute_dwr": max(
                    abs(row["contribution"][goal_id])
                    / tolerances[goal_id]
                    for goal_id in FORMAL_GOAL_IDS
                ),
                "normalized_equal_weight_benefit": (
                    benefit_by_id[target_id]
                ),
                "normalized_structural_cost_fraction": cost_fraction,
                "benefit_per_normalized_structural_cost": efficiency,
                "estimated_structural_cost": dict(row["costs"]),
                "cellwise_row_sha256": row["row_sha256"],
            }
        )
    if verification_only:
        # A weak lane still needs one actual endpoint before it can become a
        # freeze input.  Select exactly one deterministic verification-only
        # action from the complete eligible catalog.  It is deliberately not
        # a production Dörfler choice: the controller independently decides
        # whether any verified action is strong enough to execute.
        ranking.sort(
            key=lambda row: (
                -row["maximum_normalized_absolute_dwr"],
                row["estimated_structural_cost"][
                    "estimated_added_solver_peak_bytes"
                ],
                row["estimated_structural_cost"][
                    "estimated_added_factor_nnz"
                ],
                row["estimated_structural_cost"][
                    "estimated_added_matrix_nnz"
                ],
                row["estimated_structural_cost"][
                    "estimated_added_rows"
                ],
                row["estimated_structural_cost"][
                    "estimated_added_active_dofs"
                ],
                row["cellwise_row_sha256"],
                row["target_id"],
            )
        )
    else:
        ranking.sort(
            key=lambda row: (
                -row["benefit_per_normalized_structural_cost"],
                -row["normalized_equal_weight_benefit"],
                row["target_id"],
            )
        )
    required = theta * total_benefit
    accumulated = 0.0
    selected_ranked: list[str] = []
    if verification_only:
        selected_ranked.append(ranking[0]["target_id"])
        accumulated = ranking[0]["normalized_equal_weight_benefit"]
    else:
        for row in ranking:
            if row["normalized_equal_weight_benefit"] <= 0.0:
                continue
            selected_ranked.append(row["target_id"])
            accumulated += row["normalized_equal_weight_benefit"]
            if accumulated + 1.0e-15 >= required:
                break
    if not selected_ranked:
        raise GoalMarkingError(
            "positive cellwise benefit did not produce a Dörfler target"
        )
    key_by_id = {
        canonical_hp_cell_target_id(cell.key): cell.key
        for cell in state.forest.leaves
    }
    selected = tuple(
        canonical_hp_cell_target_id(key)
        for key in sorted(key_by_id[target_id] for target_id in selected_ranked)
    )
    selected_signed_dwr_delta = {
        goal_id: sum(
            rows[target_id]["contribution"][goal_id]
            for target_id in selected
        )
        for goal_id in FORMAL_GOAL_IDS
    }
    if set(selected_signed_dwr_delta) != set(FORMAL_GOAL_IDS) or not all(
        math.isfinite(value)
        for value in selected_signed_dwr_delta.values()
    ):
        raise GoalMarkingError(
            "selected signed DWR delta is not one finite 59-goal vector"
        )
    selected_signed_dwr_delta_sha = _json_sha256(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": list(selected),
            "signed_dwr_delta": selected_signed_dwr_delta,
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )
    preflight_id = _json_sha256(
        {
            "source_sha": source_sha,
            "cycle_index": state.cycle_index,
            "action_kind": action_kind,
            "canonical_target_ids": list(selected),
        },
        namespace="task035e.goal-marking-transition-preflight.v1",
    )
    try:
        if action_kind == "p-up":
            hp_transition_action_payload(
                state,
                action_id=f"marking.preflight.{preflight_id[:16]}",
                kind="p-up",
                degree_deltas={
                    key_by_id[target_id]: 1 for target_id in selected
                },
            )
        else:
            hp_transition_action_payload(
                state,
                action_id=f"marking.preflight.{preflight_id[:16]}",
                kind="h-refine",
                degree_deltas={},
                requested_split_keys=tuple(
                    key_by_id[target_id] for target_id in selected
                ),
                maximum_level=2,
            )
    except ValueError as exc:
        raise GoalMarkingError(
            "selected target set is not a valid Task035e transition: "
            f"{exc}"
        ) from exc
    unsigned = {
        "schema_version": GOAL_MARKING_SCHEMA,
        "status": (
            "goal_marking_verification_only_selected"
            if verification_only
            else "goal_marking_targets_selected"
        ),
        "classification": (
            "REFERENCE_BLIND_VERIFICATION_ONLY"
            if verification_only
            else "REFERENCE_BLIND_LOCAL_MARKING_PASS"
        ),
        "pass": True,
        "source_sha": source_sha,
        "mpi_size": 8,
        "cycle_index": state.cycle_index,
        "action_kind": action_kind,
        "doerfler_theta": theta,
        "minimum_global_normalized_signal": (
            _MINIMUM_GLOBAL_NORMALIZED_SIGNAL
        ),
        "minimum_eligible_equal_weight_benefit": (
            _MINIMUM_ELIGIBLE_EQUAL_WEIGHT_BENEFIT
        ),
        "algorithm_id": GOAL_MARKING_ALGORITHM_ID,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "fixed_equal_goal_weights": weights,
        "current_plan_file_sha256": plan_file_sha256,
        "current_plan_content_sha256": plan_content_sha256,
        "current_state_sha256": state.state_sha256,
        "current_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "current_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
        "dwr_authority_file_sha256": evidence[
            "authority_file_sha256"
        ],
        "dwr_authority_schema": CELLWISE_DWR_AUTHORITY_SCHEMA,
        "dwr_authority_sha256": evidence["authority_sha256"],
        "structural_cost_model_sha256": evidence[
            "structural_cost_model_sha256"
        ],
        "global_actual_dwr_report_sha256": evidence[
            "global_report_sha256"
        ],
        "current_goal_sha256": current.sha256,
        "shadow_goal_sha256": shadow.sha256,
        "global_maximum_normalized_signed_dwr": global_maximum,
        "signed_cellwise_closure_verified": True,
        "signed_closure_used_for_ranking": False,
        "absolute_contributions_used_only_for_ranking": True,
        "eligible_normalized_benefit": total_benefit,
        "required_doerfler_benefit": required,
        "selected_doerfler_benefit": accumulated,
        "selected_ranking_order": selected_ranked,
        "ranking": ranking,
        "canonical_target_ids": list(selected),
        "selected_signed_dwr_delta": selected_signed_dwr_delta,
        "selected_signed_dwr_delta_sha256": (
            selected_signed_dwr_delta_sha
        ),
        "transition_preflight": {
            "pass": True,
            "preflight_id": preflight_id,
            "p_down_selected": False,
            "first_two_cycle_no_p_down_preserved": True,
        },
        "transition_producer_arguments": {
            "action_kind": action_kind,
            "canonical_target_ids": list(selected),
        },
        "blocker": None,
        "reference_derived": False,
        "hidden_auditor_consumed": False,
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "marking_sha256": _json_sha256(
            unsigned,
            namespace=GOAL_MARKING_SCHEMA,
        ),
    }


def _atomic_mode_0600(path: Path, payload: bytes) -> str:
    if os.path.lexists(path):
        raise FileExistsError(f"refusing to overwrite immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def produce_goal_marking(
    *,
    current_plan_path: Path,
    current_plan_file_sha256: str,
    dwr_authority_path: Path,
    dwr_authority_file_sha256: str,
    source_sha: str,
    action_kind: str,
    output_path: Path,
    doerfler_theta: float = DEFAULT_DOERFLER_THETA,
) -> GoalMarkingWriteReceipt:
    """Validate, mark, and atomically write one immutable blind artifact."""

    source = _source_sha(source_sha)
    kind = str(action_kind)
    if kind not in _ACTION_KINDS:
        raise GoalMarkingError("action_kind must be p-up or h-refine")
    theta = _finite(doerfler_theta, label="Dörfler theta")
    if not 0.0 < theta <= 1.0:
        raise GoalMarkingError("Dörfler theta must be in (0, 1]")
    plan, plan_path, plan_file_sha = _load_bound_private_json(
        current_plan_path,
        current_plan_file_sha256,
        label="current plan",
    )
    authority, authority_path, authority_file_sha = (
        _load_bound_private_json(
            dwr_authority_path,
            dwr_authority_file_sha256,
            label="DWR authority",
        )
    )
    output = _safe_path(output_path, label="marking output")
    if len({plan_path, authority_path, output}) != 3:
        raise GoalMarkingError(
            "current plan, DWR authority, and marking output must differ"
        )
    if os.path.lexists(output):
        raise FileExistsError(
            f"refusing to overwrite immutable output: {output}"
        )
    state = _current_state(plan, source_sha=source)
    plan_content_sha = _json_sha256(plan)
    schema = authority.get("schema_version")
    if schema == ACTUAL_DWR_SCHEMA:
        _global_signed, global_report_sha = _validate_global_dwr(
            authority,
            source_sha=source,
            action_kind=kind,
            current_cycle_index=state.cycle_index,
        )
        payload = _negative_payload(
            source_sha=source,
            state=state,
            action_kind=kind,
            theta=theta,
            plan_file_sha256=plan_file_sha,
            plan_content_sha256=plan_content_sha,
            authority_file_sha256=authority_file_sha,
            authority_schema=ACTUAL_DWR_SCHEMA,
            global_report_sha256=global_report_sha,
            classification="CELLWISE_DWR_EVIDENCE_MISSING",
            message=(
                "the actual live DWR report contains only one signed eta per "
                "goal for the whole shadow system and cannot identify local "
                "transition targets"
            ),
            missing_evidence=(
                "complete current-leaf contribution partition",
                "signed per-leaf contribution for all 59 goals",
                "per-leaf residual and adjoint partition identities",
                "per-leaf active-row/NNZ/factor/peak cost estimates",
            ),
        )
    elif schema == CELLWISE_DWR_AUTHORITY_SCHEMA:
        evidence = _validate_cellwise_authority(
            authority,
            authority_file_sha256=authority_file_sha,
            plan_file_sha256=plan_file_sha,
            plan_content_sha256=plan_content_sha,
            source_sha=source,
            action_kind=kind,
            state=state,
        )
        payload = _positive_payload(
            source_sha=source,
            state=state,
            action_kind=kind,
            theta=theta,
            plan_file_sha256=plan_file_sha,
            plan_content_sha256=plan_content_sha,
            evidence=evidence,
        )
    else:
        raise GoalMarkingError(
            "DWR authority must be an actual global live-DWR report or the "
            "closed cellwise 59-goal authority"
        )
    encoded = (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    file_sha = _atomic_mode_0600(output, encoded)
    return GoalMarkingWriteReceipt(
        path=output,
        file_sha256=file_sha,
        marking_sha256=str(payload["marking_sha256"]),
        status=str(payload["status"]),
        classification=str(payload["classification"]),
        canonical_target_ids=tuple(payload["canonical_target_ids"]),
        byte_count=len(encoded),
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-plan", type=Path, required=True)
    parser.add_argument("--current-plan-sha256", required=True)
    parser.add_argument("--dwr-authority", type=Path, required=True)
    parser.add_argument("--dwr-authority-sha256", required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument(
        "--action-kind",
        choices=tuple(sorted(_ACTION_KINDS)),
        required=True,
    )
    parser.add_argument(
        "--doerfler-theta",
        type=float,
        default=DEFAULT_DOERFLER_THETA,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = produce_goal_marking(
            current_plan_path=args.current_plan,
            current_plan_file_sha256=args.current_plan_sha256,
            dwr_authority_path=args.dwr_authority,
            dwr_authority_file_sha256=args.dwr_authority_sha256,
            source_sha=args.verified_clean_sha,
            action_kind=args.action_kind,
            output_path=args.output,
            doerfler_theta=args.doerfler_theta,
        )
    except (
        FileExistsError,
        GoalMarkingError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "schema_version": GOAL_MARKING_RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": GOAL_MARKING_RECEIPT_SCHEMA,
                "status": "completed",
                "artifact_status": receipt.status,
                "classification": receipt.classification,
                "path": str(receipt.path),
                "file_sha256": receipt.file_sha256,
                "marking_sha256": receipt.marking_sha256,
                "canonical_target_ids": list(
                    receipt.canonical_target_ids
                ),
                "byte_count": receipt.byte_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CELLWISE_DWR_AUTHORITY_SCHEMA",
    "DEFAULT_DOERFLER_THETA",
    "GOAL_MARKING_ALGORITHM_ID",
    "GOAL_MARKING_RECEIPT_SCHEMA",
    "GOAL_MARKING_SCHEMA",
    "GoalMarkingError",
    "GoalMarkingWriteReceipt",
    "main",
    "produce_goal_marking",
]
