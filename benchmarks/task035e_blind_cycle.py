#!/usr/bin/env python3
"""Advance one pure Task035e blind cycle from external hash-bound evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping, Sequence

from benchmarks.task035e_internal_gate_authority import (
    InternalGateAuthorityError,
    validate_internal_gate_authority,
)
from src.adaptivity.blind_controller import (
    FIXED_ORDER_KEYS,
    FORMAL_FIELD_COMPLEX_NAMES,
    FORMAL_FIELD_SCALAR_NAMES,
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    FORMAL_TOTAL_NAMES,
    BlindCycleInput,
    BlindCycleResult,
    BlindTrial,
    ComplexDatum,
    GoalVector,
    InternalGates,
    OrderDatum,
    ShadowCatalog,
    ShadowCost,
    ShadowVerification,
    StabilityRepeatVerification,
    advance_blind_trial,
    build_shadow_action,
    h_level3_saturation_authority_from_payload,
    p6_saturation_authority_from_payload,
)
from src.adaptivity.blind_controller.manifest import (
    build_cycle_manifest,
    cycle_manifest_sha256,
)
from src.adaptivity.blind_controller.shadows import (
    _replay_h_level3_saturation_authority_from_payload,
    _replay_p6_saturation_authority_from_payload,
)
from src.adaptivity.blind_controller.state_machine import (
    StructuralInventory,
    stability_repeat_verification_from_payload,
    validate_internal_certificate_payload,
)


CANDIDATE_OUTPUT_SCHEMA = "task035e.frozen-candidate-outputs.v1"
SHADOW_BUNDLE_SCHEMA = "task035e.blind-external-shadow-bundle.v4"
CYCLE_BINDING_SCHEMA = "task035e.blind-cycle-binding.v1"
CYCLE_EVIDENCE_SCHEMA = "task035e.blind-cycle-evidence.v1"
TRIAL_STATE_SCHEMA = "task035e.blind-trial-replay-state.v1"
STRUCTURAL_INVENTORY_SCHEMA = "task035e.structural-inventory.v1"
REFERENCE_ISOLATION_REPORT_SCHEMA = "task035e.reference-leak-check.v1"
REFERENCE_ISOLATION_ARTIFACT_SCHEMA = (
    "task035e.reference-leak-check-artifact.v1"
)
FORMAL_BLIND_ENTRYPOINTS = (
    "benchmarks/task035e_campaign_bootstrap.py",
    "benchmarks/task035e_initial_space.py",
    "benchmarks/task035e_trial_metadata.py",
    "benchmarks/task035e_transition_producer.py",
    "benchmarks/task035e_candidate_output.py",
    "benchmarks/task035e_live_shadow_bridge.py",
    "benchmarks/task035e_cellwise_authority.py",
    "benchmarks/task035e_goal_marking.py",
    "benchmarks/task035e_shadow_bundle.py",
    "benchmarks/task035e_blind_bindings.py",
    "benchmarks/task035e_internal_gate_authority.py",
    "benchmarks/task035e_blind_campaign.py",
    "benchmarks/task035e_campaign_stages.py",
    "benchmarks/task035e_campaign_handlers.py",
    "benchmarks/task035e_p7_saturation_bridge.py",
    "benchmarks/task035e_blind_cycle.py",
)
REFERENCE_ISOLATION_MANIFEST_STATE = "estimate"

_SHA256_KEYS = (
    "mesh_forest_sha256",
    "degree_map_sha256",
    "plan_file_sha256",
    "plan_content_sha256",
    "plan_solver_content_sha256",
    "state_sha256",
    "solution_snapshot_sha256",
    "complete_output_sha256",
    "full_residual_sha256",
    "candidate_record_file_sha256",
    "current_snapshot_file_sha256",
    "resource_inventory_sha256",
)
_FORBIDDEN_PATH_PARTS = (
    "ref" + "erence_certifier",
    "hid" + "den_auditor",
    "sealed_" + "reference",
)


class BlindCycleArtifactError(ValueError):
    """Raised when external blind-cycle evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class BlindCycleWriteReceipt:
    evidence_path: Path
    evidence_file_sha256: str
    evidence_payload_sha256: str
    trial_state_path: Path
    trial_state_file_sha256: str
    trial_state_payload_sha256: str
    cycle_index: int
    status: str
    controlled_negative: bool
    trial_advanced: bool


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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BlindCycleArtifactError(f"{label} must be a lowercase SHA-256")
    return value


def _source_sha(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BlindCycleArtifactError("source_sha must be one full Git SHA")
    return value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BlindCycleArtifactError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise BlindCycleArtifactError(f"{label} must be a JSON array")
    return value


def _exact(
    value: Any,
    keys: set[str] | frozenset[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    row = _mapping(value, label=label)
    if set(row) != set(keys):
        raise BlindCycleArtifactError(f"{label} does not use its closed schema")
    return row


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BlindCycleArtifactError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise BlindCycleArtifactError(f"{label} must be finite")
    return result


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise BlindCycleArtifactError(
            f"{label} must be an integer >= {minimum}"
        )
    return int(value)


def _safe_path(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    lowered = {part.lower() for part in resolved.parts}
    if any(token in lowered for token in _FORBIDDEN_PATH_PARTS):
        raise BlindCycleArtifactError(f"{label} crosses a forbidden layer")
    return resolved


def _load_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlindCycleArtifactError(f"cannot read {label}: {path}") from exc
    return _mapping(value, label=label)


def _load_bound_json(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[Mapping[str, Any], str]:
    resolved = _safe_path(path, label=label)
    expected = _sha256(expected_sha256, label=f"{label} file SHA-256")
    if not resolved.is_file():
        raise BlindCycleArtifactError(f"{label} is missing: {resolved}")
    observed = _file_sha256(resolved)
    if observed != expected:
        raise BlindCycleArtifactError(f"{label} file SHA-256 mismatch")
    return _load_json(resolved, label=label), observed


def _load_bound_outer(
    path: Path,
    expected_sha256: str,
    *,
    schema: str,
    label: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any], str]:
    outer, file_sha = _load_bound_json(
        path,
        expected_sha256,
        label=label,
    )
    outer = _exact(
        outer,
        {"schema_version", "sha256", "payload"},
        label=f"{label} outer",
    )
    payload = _mapping(outer["payload"], label=f"{label} payload")
    if (
        outer["schema_version"] != schema
        or payload.get("schema_version") != schema
        or _sha256(outer["sha256"], label=f"{label} payload SHA-256")
        != _json_sha256(payload)
    ):
        raise BlindCycleArtifactError(f"{label} schema or self-hash differs")
    return outer, payload, file_sha


def _load_isolation_audit(
    path: Path,
    expected_file_sha256: str,
    *,
    source_sha: str,
    manifest_sha256: str,
) -> tuple[Mapping[str, Any], str, str]:
    outer, file_sha = _load_bound_json(
        path,
        expected_file_sha256,
        label="reference-isolation report",
    )
    outer = _exact(
        outer,
        {"schema_version", "producer", "sha256", "payload"},
        label="reference-isolation report outer",
    )
    producer = _exact(
        outer["producer"],
        {"source", "file_sha256"},
        label="reference-isolation report producer",
    )
    root = Path(__file__).resolve().parents[1]
    checker_relative = "benchmarks/task035e_reference_leak_checker.py"
    checker_path = (root / checker_relative).resolve()
    if (
        producer["source"] != checker_relative
        or producer["file_sha256"] != _file_sha256(checker_path)
    ):
        raise BlindCycleArtifactError(
            "reference-isolation producer source differs"
        )
    payload = _exact(
        outer["payload"],
        {
            "schema",
            "schema_version",
            "manifest_sha256",
            "source_sha",
            "pass",
            "status",
            "exit_code",
            "exit_code_bits",
            "checks",
        },
        label="reference-isolation report payload",
    )
    payload_sha = _sha256(
        outer["sha256"],
        label="reference-isolation report payload SHA-256",
    )
    if payload_sha != _json_sha256(payload):
        raise BlindCycleArtifactError(
            "reference-isolation report self-hash differs"
        )
    if (
        outer["schema_version"] != REFERENCE_ISOLATION_ARTIFACT_SCHEMA
        or payload["schema"] != REFERENCE_ISOLATION_REPORT_SCHEMA
        or payload["schema_version"] != REFERENCE_ISOLATION_REPORT_SCHEMA
        or payload["source_sha"] != source_sha
        or payload["manifest_sha256"] != manifest_sha256
        or payload["pass"] is not True
        or payload["status"] != "reference_isolation_pass"
        or payload["exit_code"] != 0
    ):
        raise BlindCycleArtifactError(
            "reference-isolation report identity or pass differs"
        )
    exit_bits = _exact(
        payload["exit_code_bits"],
        {
            "static_leak",
            "manifest_leak_or_schema_error",
            "dynamic_access",
        },
        label="reference-isolation exit bits",
    )
    if any(type(value) is not bool or value for value in exit_bits.values()):
        raise BlindCycleArtifactError(
            "reference-isolation report contains a failing exit bit"
        )
    checks = _exact(
        payload["checks"],
        {"static", "manifest", "dynamic"},
        label="reference-isolation checks",
    )
    static = _exact(
        checks["static"],
        {
            "pass",
            "scanned_file_count",
            "controller_file_count",
            "source_entrypoint_file_count",
            "source_entrypoints",
            "transitive_file_count",
            "import_edge_count",
            "findings",
        },
        label="reference-isolation static check",
    )
    entries = _sequence(
        static["source_entrypoints"],
        label="reference-isolation source entrypoints",
    )
    expected_entries = []
    for relative in FORMAL_BLIND_ENTRYPOINTS:
        entry_path = (root / relative).resolve()
        try:
            entry_path.relative_to(root)
        except ValueError as exc:
            raise BlindCycleArtifactError(
                "formal blind entrypoint escapes the repository"
            ) from exc
        expected_entries.append(
            {
                "source": relative,
                "file_sha256": _file_sha256(entry_path),
            }
        )
    if (
        static["pass"] is not True
        or static["findings"] != []
        or static["source_entrypoint_file_count"] != len(expected_entries)
        or list(entries) != expected_entries
        or type(static["scanned_file_count"]) is not int
        or type(static["controller_file_count"]) is not int
        or static["scanned_file_count"]
        < static["controller_file_count"] + len(expected_entries)
    ):
        raise BlindCycleArtifactError(
            "reference-isolation static entrypoint coverage differs"
        )
    manifest = _exact(
        checks["manifest"],
        {"pass", "schema", "additional_properties", "issues"},
        label="reference-isolation manifest check",
    )
    if (
        manifest["pass"] is not True
        or manifest["schema"] != "task035e.blind-input-manifest.v1"
        or manifest["additional_properties"] is not False
        or manifest["issues"] != []
    ):
        raise BlindCycleArtifactError(
            "reference-isolation manifest validation differs"
        )
    dynamic = _mapping(
        checks["dynamic"],
        label="reference-isolation dynamic check",
    )
    if (
        dynamic.get("pass") is not True
        or dynamic.get("status") != "audit_pass"
        or dynamic.get("violations") != []
    ):
        raise BlindCycleArtifactError(
            "reference-isolation dynamic audit differs"
        )
    return MappingProxyType(dict(payload)), file_sha, payload_sha


def _complex(value: Any, *, label: str) -> ComplexDatum:
    row = _exact(value, {"real", "imag"}, label=label)
    return ComplexDatum(
        _finite(row["real"], label=f"{label}.real"),
        _finite(row["imag"], label=f"{label}.imag"),
    )


def _goal_vector_and_applicability_audit(
    payload: Mapping[str, Any],
) -> tuple[GoalVector, tuple[dict[str, Any], ...]]:
    payload = _exact(
        payload,
        {
            "schema_version",
            "orders",
            "scalar_observations",
            "complex_observations",
            "full_explicit_true_residual",
        },
        label="candidate output",
    )
    if payload["schema_version"] != CANDIDATE_OUTPUT_SCHEMA:
        raise BlindCycleArtifactError("candidate output schema differs")
    indexed: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    for raw in _sequence(payload["orders"], label="candidate orders"):
        row = _exact(
            raw,
            {
                "port",
                "m",
                "n",
                "propagating",
                "total_power",
                "co_polarized_amplitude",
                "cross_polarized_power",
                "cross_polarized_amplitude",
                "kz",
                "admittance",
                "normalization_identity",
            },
            label="candidate order",
        )
        identity = (
            str(row["port"]),
            _integer(row["m"], label="order m", minimum=-10_000),
            _integer(row["n"], label="order n", minimum=-10_000),
        )
        if identity in indexed:
            raise BlindCycleArtifactError("candidate order is duplicated")
        indexed[identity] = row
    orders = []
    applicability: list[dict[str, Any]] = []
    for identity in FIXED_ORDER_KEYS:
        if identity not in indexed:
            raise BlindCycleArtifactError(
                f"candidate misses formal order {identity}"
            )
        row = indexed[identity]
        normalization = row["normalization_identity"]
        if (
            not isinstance(normalization, str)
            or not normalization.startswith("sha256:")
        ):
            raise BlindCycleArtifactError(
                "candidate normalization identity is invalid"
            )
        propagating = row["propagating"]
        if type(propagating) is not bool:
            raise BlindCycleArtifactError(
                "candidate order propagating must be boolean"
            )
        if propagating:
            total_power = _finite(
                row["total_power"],
                label="formal propagating order total_power",
            )
            cross_power = _finite(
                row["cross_polarized_power"],
                label="formal propagating order cross_power",
            )
            if total_power < 0.0 or cross_power < 0.0:
                raise BlindCycleArtifactError(
                    "propagating order powers must be nonnegative"
                )
            total_state = "finite_nonnegative"
            cross_state = "finite_nonnegative"
            mapping = "physical_power_coordinate"
        else:
            if (
                row["total_power"] is not None
                or row["cross_polarized_power"] is not None
            ):
                raise BlindCycleArtifactError(
                    "evanescent order powers must be null"
                )
            total_power = 0.0
            cross_power = 0.0
            total_state = "null_not_applicable"
            cross_state = "null_not_applicable"
            mapping = "explicit_not_applicable_to_formal_zero"
        power_goal_id = (
            f"{identity[0]}:m{identity[1]}:n{identity[2]}:power"
        )
        applicability.append(
            {
                "goal_id": power_goal_id,
                "port": identity[0],
                "m": identity[1],
                "n": identity[2],
                "propagating": propagating,
                "power_applicable": propagating,
                "input_total_power_state": total_state,
                "input_cross_power_state": cross_state,
                "formal_power_value": total_power,
                "mapping": mapping,
            }
        )
        orders.append(
            OrderDatum(
                port=identity[0],
                m=identity[1],
                n=identity[2],
                propagating=propagating,
                power=total_power,
                co_amplitude=_complex(
                    row["co_polarized_amplitude"],
                    label="co amplitude",
                ),
                cross_power=cross_power,
                cross_amplitude=_complex(
                    row["cross_polarized_amplitude"],
                    label="cross amplitude",
                ),
                kz=_complex(row["kz"], label="kz"),
                admittance=_complex(row["admittance"], label="admittance"),
                normalization_sha256=normalization.removeprefix("sha256:"),
            )
        )
    scalar_rows: dict[str, float] = {}
    for raw in _sequence(
        payload["scalar_observations"],
        label="scalar observations",
    ):
        row = _exact(raw, {"name", "value"}, label="scalar observation")
        name = str(row["name"])
        if name in scalar_rows:
            raise BlindCycleArtifactError("scalar observation is duplicated")
        scalar_rows[name] = _finite(row["value"], label=f"scalar {name}")
    complex_rows: dict[str, ComplexDatum] = {}
    for raw in _sequence(
        payload["complex_observations"],
        label="complex observations",
    ):
        row = _exact(raw, {"name", "value"}, label="complex observation")
        name = str(row["name"])
        if name in complex_rows:
            raise BlindCycleArtifactError("complex observation is duplicated")
        complex_rows[name] = _complex(
            row["value"],
            label=f"complex {name}",
        )
    try:
        goals = GoalVector.from_orders(
            tuple(orders),
            totals={name: scalar_rows[name] for name in FORMAL_TOTAL_NAMES},
            field_scalars={
                name: scalar_rows[name]
                for name in FORMAL_FIELD_SCALAR_NAMES
            },
            field_complex={
                name: complex_rows[name]
                for name in FORMAL_FIELD_COMPLEX_NAMES
            },
        )
    except KeyError as exc:
        raise BlindCycleArtifactError(
            f"candidate output misses one formal observation: {exc}"
        ) from exc
    if (
        len(goals.values) != 59
        or tuple(row.goal_id for row in goals.values) != FORMAL_GOAL_IDS
    ):
        raise BlindCycleArtifactError(
            "candidate goal vector does not preserve the 59-goal contract"
        )
    return goals, tuple(applicability)


def goal_vector_from_candidate_output(
    payload: Mapping[str, Any],
) -> GoalVector:
    """Strictly derive the 59 formal goals from one candidate-output payload."""

    goals, _applicability = _goal_vector_and_applicability_audit(payload)
    return goals


def candidate_order_applicability_audit(
    payload: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    """Expose how propagating and evanescent power coordinates were mapped."""

    _goals, applicability = _goal_vector_and_applicability_audit(payload)
    return tuple(MappingProxyType(dict(row)) for row in applicability)


def _shadow_action(
    raw: Any,
    *,
    current: GoalVector,
    mesh_forest_sha256: str,
    degree_map_sha256: str,
) -> Any:
    row = _exact(
        raw,
        {
            "action_id",
            "kind",
            "target_ids",
            "current_goal_sha256",
            "shadow_goals",
            "signed_dwr_delta",
            "cost",
            "sign_consistent",
            "actual_added_leaf_count",
            "transition_action_sha256",
            "transition_action_file_sha256",
            "transition_action_identity_sha256",
            "next_mesh_forest_sha256",
            "next_degree_map_sha256",
            "action_sha256",
            "external_evidence",
        },
        label="shadow action",
    )
    if row["current_goal_sha256"] != current.sha256:
        raise BlindCycleArtifactError(
            "shadow action current endpoint differs"
        )
    shadow_values = _mapping(
        row["shadow_goals"],
        label="shadow goal mapping",
    )
    dwr = _mapping(
        row["signed_dwr_delta"],
        label="signed DWR mapping",
    )
    if set(shadow_values) != set(FORMAL_GOAL_IDS):
        raise BlindCycleArtifactError(
            "shadow endpoint misses the complete 59-goal inventory"
        )
    if set(dwr) != set(FORMAL_GOAL_IDS):
        raise BlindCycleArtifactError(
            "missing DWR is a controlled-negative input failure"
        )
    targets = _sequence(row["target_ids"], label="shadow target IDs")
    if type(row["sign_consistent"]) is not bool:
        raise BlindCycleArtifactError(
            "shadow action sign_consistent must be boolean"
        )
    for name in ("action_id", "kind"):
        if not isinstance(row[name], str) or not row[name]:
            raise BlindCycleArtifactError(
                f"shadow action {name} must be nonempty"
            )
    if any(not isinstance(value, str) or not value for value in targets):
        raise BlindCycleArtifactError(
            "shadow target IDs must be nonempty strings"
        )
    shadow = GoalVector.from_mapping(
        {
            goal_id: _finite(
                shadow_values[goal_id],
                label=f"shadow goal {goal_id}",
            )
            for goal_id in FORMAL_GOAL_IDS
        }
    )
    cost_row = _exact(
        row["cost"],
        {
            "added_active_dofs",
            "added_rows",
            "added_matrix_nnz",
            "added_factor_nnz",
            "added_solver_peak_bytes",
        },
        label="shadow cost",
    )
    cost = ShadowCost(
        *(
            _integer(
                cost_row[name],
                label=f"cost {name}",
                minimum=-10**30,
            )
            for name in ShadowCost.__dataclass_fields__
        )
    )
    evidence_keys = {
            "actual_shadow_solve",
            "actual_dwr_evaluation",
            "shadow_output_sha256",
            "dwr_evidence_sha256",
            "transition_action_sha256",
            "transition_action_file_sha256",
            "transition_action_identity_sha256",
            "transition_action_representation",
            "current_watchdog_record_sha256",
            "shadow_watchdog_record_sha256",
            "current_plan_file_sha256",
            "shadow_plan_file_sha256",
            "from_leaf_catalog_sha256",
            "from_cell_degree_plan_sha256",
            "next_leaf_catalog_sha256",
            "next_cell_degree_plan_sha256",
            "goal_marking_file_sha256",
            "goal_marking_payload_sha256",
            "goal_marking_selection_role",
            "verification_prediction_file_sha256",
            "verification_prediction_payload_sha256",
            "verification_prediction_marking_file_sha256",
            "verification_prediction_marking_payload_sha256",
            "selected_shadow_global_dwr_sha256",
            "signed_structural_delta",
            "measured_structural_benefit",
    }
    evidence_raw = _mapping(
        row["external_evidence"],
        label="external shadow evidence",
    )
    if set(evidence_raw) != evidence_keys:
        raise BlindCycleArtifactError(
            "external shadow evidence does not use its closed schema"
        )
    evidence = evidence_raw
    if (
        evidence["actual_shadow_solve"] is not True
        or evidence["actual_dwr_evaluation"] is not True
    ):
        raise BlindCycleArtifactError(
            "shadow/DWR evidence is not an external actual solve"
        )
    for name in (
        "shadow_output_sha256",
        "dwr_evidence_sha256",
        "transition_action_sha256",
        "transition_action_file_sha256",
        "transition_action_identity_sha256",
        "current_watchdog_record_sha256",
        "shadow_watchdog_record_sha256",
        "current_plan_file_sha256",
        "shadow_plan_file_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "next_leaf_catalog_sha256",
        "next_cell_degree_plan_sha256",
        "goal_marking_file_sha256",
        "goal_marking_payload_sha256",
        "verification_prediction_file_sha256",
        "verification_prediction_payload_sha256",
        "verification_prediction_marking_file_sha256",
        "verification_prediction_marking_payload_sha256",
        "selected_shadow_global_dwr_sha256",
    ):
        _sha256(evidence[name], label=name)
    if (
        evidence["goal_marking_file_sha256"]
        != evidence["verification_prediction_marking_file_sha256"]
        or evidence["goal_marking_payload_sha256"]
        != evidence["verification_prediction_marking_payload_sha256"]
    ):
        raise BlindCycleArtifactError(
            "shadow prediction is not bound to the supplied goal marking"
        )
    if evidence["goal_marking_selection_role"] not in {
        "production_candidate",
        "verification_only",
    }:
        raise BlindCycleArtifactError(
            "shadow goal-marking selection role is invalid"
        )
    if evidence["transition_action_representation"] not in {"plain", "outer"}:
        raise BlindCycleArtifactError(
            "transition action representation is not closed"
        )
    if (
        evidence["from_leaf_catalog_sha256"] != mesh_forest_sha256
        or evidence["from_cell_degree_plan_sha256"]
        != degree_map_sha256
    ):
        raise BlindCycleArtifactError(
            "external shadow evidence current plan identity differs"
        )
    action_transition_identity = (
        row["transition_action_sha256"]
        == evidence["transition_action_sha256"],
        row["transition_action_file_sha256"]
        == evidence["transition_action_file_sha256"],
        row["transition_action_identity_sha256"]
        == evidence["transition_action_identity_sha256"],
        row["next_mesh_forest_sha256"]
        == evidence["next_leaf_catalog_sha256"],
        row["next_degree_map_sha256"]
        == evidence["next_cell_degree_plan_sha256"],
    )
    if not all(action_transition_identity):
        raise BlindCycleArtifactError(
            "shadow action transition identity differs from validated evidence"
        )
    if row["kind"] == "p-up" and (
        row["next_mesh_forest_sha256"] != mesh_forest_sha256
        or row["next_degree_map_sha256"] == degree_map_sha256
    ):
        raise BlindCycleArtifactError(
            "p-up shadow does not preserve topology and change degree identity"
        )
    if (
        row["kind"] == "h-refine"
        and row["next_mesh_forest_sha256"] == mesh_forest_sha256
    ):
        raise BlindCycleArtifactError(
            "h-refine shadow does not change mesh-forest identity"
        )
    for name in (
        "transition_action_sha256",
        "transition_action_file_sha256",
        "transition_action_identity_sha256",
        "next_mesh_forest_sha256",
        "next_degree_map_sha256",
    ):
        _sha256(row[name], label=f"shadow action {name}")
    signed_cost = _exact(
        evidence["signed_structural_delta"],
        set(ShadowCost.__dataclass_fields__),
        label="signed measured structural delta",
    )
    measured_benefit = _exact(
        evidence["measured_structural_benefit"],
        set(ShadowCost.__dataclass_fields__),
        label="measured structural benefit",
    )
    for name in ShadowCost.__dataclass_fields__:
        signed_value = _integer(
            signed_cost[name],
            label=f"signed measured structural delta {name}",
            minimum=-(10**30),
        )
        benefit_value = _integer(
            measured_benefit[name],
            label=f"measured structural benefit {name}",
        )
        if (
            cost_row[name] != max(signed_value, 0)
            or benefit_value != max(-signed_value, 0)
        ):
            raise BlindCycleArtifactError(
                "shadow cost is not derived from measured inventories"
            )
    action = build_shadow_action(
        action_id=row["action_id"],
        kind=row["kind"],
        target_ids=tuple(str(value) for value in targets),
        current=current,
        shadow=shadow,
        signed_dwr_delta={
            goal_id: _finite(dwr[goal_id], label=f"DWR {goal_id}")
            for goal_id in FORMAL_GOAL_IDS
        },
        cost=cost,
        sign_consistent=bool(row["sign_consistent"]),
        transition_action_sha256=str(row["transition_action_sha256"]),
        transition_action_file_sha256=str(
            row["transition_action_file_sha256"]
        ),
        transition_action_identity_sha256=str(
            row["transition_action_identity_sha256"]
        ),
        next_mesh_forest_sha256=str(row["next_mesh_forest_sha256"]),
        next_degree_map_sha256=str(row["next_degree_map_sha256"]),
        actual_added_leaf_count=_integer(
            row["actual_added_leaf_count"],
            label="actual_added_leaf_count",
        ),
    )
    if row["action_sha256"] != action.action_sha256:
        raise BlindCycleArtifactError(
            "shadow action is not bound to its signed-goal content"
        )
    return action


def _shadow_catalog(
    payload: Mapping[str, Any],
    *,
    current: GoalVector,
    source_sha: str,
    trial_id: str,
    cycle_index: int,
    mesh_forest_sha256: str,
    degree_map_sha256: str,
    plan_file_sha256: str,
    complete_output_sha256: str,
) -> ShadowCatalog:
    payload = _exact(
        payload,
        {
            "schema_version",
            "producer_role",
            "source_sha",
            "mpi_size",
            "trial_id",
            "cycle_index",
            "mesh_forest_sha256",
            "degree_map_sha256",
            "complete_output_sha256",
            "current_goal_sha256",
            "actual_shadow_solves",
            "actual_dwr_evaluations",
            "synthetic",
            "reference_derived",
            "p6_saturation",
            "h_level3_saturation",
            "p_actions",
            "h_actions",
        },
        label="shadow bundle payload",
    )
    identity = (
        payload["schema_version"] == SHADOW_BUNDLE_SCHEMA,
        payload["producer_role"] == "external_actual_shadow_dwr_solver",
        payload["source_sha"] == source_sha,
        payload["mpi_size"] == 8,
        payload["trial_id"] == trial_id,
        payload["cycle_index"] == cycle_index,
        payload["mesh_forest_sha256"] == mesh_forest_sha256,
        payload["degree_map_sha256"] == degree_map_sha256,
        payload["complete_output_sha256"] == complete_output_sha256,
        payload["current_goal_sha256"] == current.sha256,
        payload["actual_shadow_solves"] is True,
        payload["actual_dwr_evaluations"] is True,
        payload["synthetic"] is False,
        payload["reference_derived"] is False,
    )
    if not all(identity):
        raise BlindCycleArtifactError(
            "shadow bundle identity or external-evidence role differs"
        )
    try:
        p6_saturation = p6_saturation_authority_from_payload(
            _mapping(
                payload["p6_saturation"],
                label="p6 saturation authority",
            ),
            expected_plan_file_sha256=plan_file_sha256,
            expected_mesh_forest_sha256=mesh_forest_sha256,
            expected_degree_map_sha256=degree_map_sha256,
        )
        h_level3_saturation = h_level3_saturation_authority_from_payload(
            _mapping(
                payload["h_level3_saturation"],
                label="level3 h-saturation authority",
            ),
            expected_plan_file_sha256=plan_file_sha256,
            expected_mesh_forest_sha256=mesh_forest_sha256,
            expected_degree_map_sha256=degree_map_sha256,
        )
        return ShadowCatalog(
            current_goal_sha256=current.sha256,
            p_actions=tuple(
                _shadow_action(
                    row,
                    current=current,
                    mesh_forest_sha256=mesh_forest_sha256,
                    degree_map_sha256=degree_map_sha256,
                )
                for row in _sequence(
                    payload["p_actions"],
                    label="p shadow actions",
                )
            ),
            h_actions=tuple(
                _shadow_action(
                    row,
                    current=current,
                    mesh_forest_sha256=mesh_forest_sha256,
                    degree_map_sha256=degree_map_sha256,
                )
                for row in _sequence(
                    payload["h_actions"],
                    label="h shadow actions",
                )
            ),
            p6_saturation=p6_saturation,
            h_level3_saturation=h_level3_saturation,
        )
    except ValueError as exc:
        if isinstance(exc, BlindCycleArtifactError):
            raise
        raise BlindCycleArtifactError(str(exc)) from exc


def _trial_metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    trial = _exact(
        payload,
        {
            "trial_id",
            "algorithm_id",
            "initial_path_id",
            "initial_mesh_forest_sha256",
            "physical_identity_sha256",
            "maximum_cycles",
        },
        label="trial metadata",
    )
    _sha256(
        trial["initial_mesh_forest_sha256"],
        label="initial mesh forest SHA-256",
    )
    _sha256(
        trial["physical_identity_sha256"],
        label="physical identity SHA-256",
    )
    maximum_cycles = _integer(
        trial["maximum_cycles"],
        label="maximum_cycles",
        minimum=1,
    )
    if maximum_cycles > 6:
        raise BlindCycleArtifactError("maximum_cycles exceeds six")
    for name in ("trial_id", "algorithm_id", "initial_path_id"):
        if not isinstance(trial[name], str) or not trial[name]:
            raise BlindCycleArtifactError(f"{name} must be nonempty")
    return trial


def _load_cycle_binding(
    path: Path,
    expected_sha256: str,
) -> tuple[Mapping[str, Any], str, str]:
    outer, payload, file_sha = _load_bound_outer(
        path,
        expected_sha256,
        schema=CYCLE_BINDING_SCHEMA,
        label="cycle binding",
    )
    payload = _exact(
        payload,
        {
            "schema_version",
            "trial",
            "source_sha",
            "mpi_size",
            "cycle_index",
            "mesh_forest_sha256",
            "degree_map_sha256",
            "plan_file_sha256",
            "plan_content_sha256",
            "plan_solver_content_sha256",
            "state_sha256",
            "solution_snapshot_sha256",
            "complete_output_sha256",
            "full_residual_sha256",
            "candidate_record_file_sha256",
            "candidate_output_file_sha256",
            "current_snapshot_file_sha256",
            "shadow_bundle_file_sha256",
            "reference_isolation_report_file_sha256",
            "resource_inventory",
            "resource_inventory_sha256",
            "internal_gates",
            "transition",
        },
        label="cycle binding payload",
    )
    _trial_metadata(_mapping(payload["trial"], label="trial metadata"))
    _source_sha(payload["source_sha"])
    if payload["mpi_size"] != 8:
        raise BlindCycleArtifactError("formal blind cycle requires MPI8")
    cycle_index = _integer(
        payload["cycle_index"],
        label="cycle_index",
    )
    if cycle_index > 5:
        raise BlindCycleArtifactError("cycle_index exceeds five")
    for name in (
        *_SHA256_KEYS,
        "candidate_output_file_sha256",
        "shadow_bundle_file_sha256",
        "reference_isolation_report_file_sha256",
    ):
        _sha256(payload[name], label=name)
    inventory = _exact(
        payload["resource_inventory"],
        set(StructuralInventory.__dataclass_fields__),
        label="structural inventory",
    )
    inventory_payload = {
        "schema_version": "task035e.resource-authority.v1",
        **{
            name: _integer(inventory[name], label=name)
            for name in StructuralInventory.__dataclass_fields__
        },
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }
    if payload["resource_inventory_sha256"] != _json_sha256(
        inventory_payload
    ):
        raise BlindCycleArtifactError(
            "resource authority content SHA-256 differs"
        )
    try:
        authority = validate_internal_gate_authority(
            _mapping(
                payload["internal_gates"],
                label="internal-Gate authority",
            ),
            expected_source_sha=str(payload["source_sha"]),
            expected_trial_id=str(
                _mapping(payload["trial"], label="trial metadata")[
                    "trial_id"
                ]
            ),
            expected_cycle_index=cycle_index,
            expected_candidate_record_file_sha256=str(
                payload["candidate_record_file_sha256"]
            ),
            expected_candidate_output_file_sha256=str(
                payload["candidate_output_file_sha256"]
            ),
            expected_candidate_output_payload_sha256=str(
                payload["complete_output_sha256"]
            ),
            expected_plan_file_sha256=str(payload["plan_file_sha256"]),
            expected_plan_payload_sha256=str(
                payload["plan_content_sha256"]
            ),
            expected_mesh_forest_sha256=str(
                payload["mesh_forest_sha256"]
            ),
            expected_degree_map_sha256=str(payload["degree_map_sha256"]),
            expected_snapshot_file_sha256=str(
                payload["current_snapshot_file_sha256"]
            ),
            expected_snapshot_payload_sha256=str(
                payload["solution_snapshot_sha256"]
            ),
            expected_snapshot_full_residual_sha256=str(
                payload["full_residual_sha256"]
            ),
        )
        InternalGates(**dict(authority["gates"]))
    except (InternalGateAuthorityError, TypeError, ValueError) as exc:
        raise BlindCycleArtifactError(str(exc)) from exc
    transition = _exact(
        payload["transition"],
        {
            "previous_trial_state_file_sha256",
            "previous_cycle_certificate_sha256",
            "executed_action_verifications",
            "stability_repeat_verification",
        },
        label="transition binding",
    )
    for name in (
        "previous_trial_state_file_sha256",
        "previous_cycle_certificate_sha256",
    ):
        if transition[name] is not None:
            _sha256(transition[name], label=name)
    if not isinstance(transition["executed_action_verifications"], list):
        raise BlindCycleArtifactError(
            "executed_action_verifications must be an array"
        )
    return payload, str(outer["sha256"]), file_sha


def _verification_rows(
    transition: Mapping[str, Any],
) -> tuple[ShadowVerification, ...]:
    result = []
    for raw in transition["executed_action_verifications"]:
        row = _exact(
            raw,
            {
                "action_id",
                "action_sha256",
                "transition_action_sha256",
                "transition_action_file_sha256",
                "transition_action_identity_sha256",
                "next_mesh_forest_sha256",
                "next_degree_map_sha256",
                "next_plan_file_sha256",
                "next_plan_content_sha256",
                "next_state_sha256",
                "before_output_sha256",
                "after_output_sha256",
                "predicted_deltas",
                "actual_deltas",
            },
            label="executed action verification",
        )

        def packet(name: str) -> tuple[tuple[str, float], ...]:
            values = _mapping(row[name], label=name)
            if set(values) != set(FORMAL_GOAL_IDS):
                raise BlindCycleArtifactError(
                    f"{name} misses the complete 59-goal inventory"
                )
            return tuple(
                (
                    goal_id,
                    _finite(values[goal_id], label=f"{name} {goal_id}"),
                )
                for goal_id in FORMAL_GOAL_IDS
            )

        result.append(
            ShadowVerification(
                action_id=str(row["action_id"]),
                action_sha256=_sha256(
                    row["action_sha256"],
                    label="verification action SHA-256",
                ),
                transition_action_sha256=_sha256(
                    row["transition_action_sha256"],
                    label="verification transition action SHA-256",
                ),
                transition_action_file_sha256=_sha256(
                    row["transition_action_file_sha256"],
                    label="verification transition action file SHA-256",
                ),
                transition_action_identity_sha256=_sha256(
                    row["transition_action_identity_sha256"],
                    label="verification transition action identity SHA-256",
                ),
                next_mesh_forest_sha256=_sha256(
                    row["next_mesh_forest_sha256"],
                    label="verification next mesh forest SHA-256",
                ),
                next_degree_map_sha256=_sha256(
                    row["next_degree_map_sha256"],
                    label="verification next degree map SHA-256",
                ),
                next_plan_file_sha256=_sha256(
                    row["next_plan_file_sha256"],
                    label="verification next plan file SHA-256",
                ),
                next_plan_content_sha256=_sha256(
                    row["next_plan_content_sha256"],
                    label="verification next plan content SHA-256",
                ),
                next_state_sha256=_sha256(
                    row["next_state_sha256"],
                    label="verification next state SHA-256",
                ),
                before_output_sha256=_sha256(
                    row["before_output_sha256"],
                    label="verification before output SHA-256",
                ),
                after_output_sha256=_sha256(
                    row["after_output_sha256"],
                    label="verification after output SHA-256",
                ),
                predicted_deltas=packet("predicted_deltas"),
                actual_deltas=packet("actual_deltas"),
            )
        )
    return tuple(result)


def _stability_repeat_row(
    transition: Mapping[str, Any],
) -> StabilityRepeatVerification | None:
    raw = transition["stability_repeat_verification"]
    if raw is None:
        return None
    try:
        return stability_repeat_verification_from_payload(
            _mapping(raw, label="stability-repeat verification")
        )
    except (TypeError, ValueError) as exc:
        raise BlindCycleArtifactError(str(exc)) from exc


def _result_payload(result: BlindCycleResult) -> dict[str, Any]:
    return {
        "goals": [
            [row.goal_id, row.value] for row in result.goals.values
        ],
        "internal_certificate": dict(result.internal_certificate),
        "internal_certificate_sha256": (
            result.internal_certificate_sha256
        ),
    }


def _result_from_payload(payload: Any) -> BlindCycleResult:
    row = _exact(
        payload,
        {
            "goals",
            "internal_certificate",
            "internal_certificate_sha256",
        },
        label="trial cycle result",
    )
    goal_rows = _sequence(row["goals"], label="trial result goals")
    if (
        len(goal_rows) != len(FORMAL_GOAL_IDS)
        or any(
            not isinstance(value, list) or len(value) != 2
            for value in goal_rows
        )
        or tuple(value[0] for value in goal_rows) != FORMAL_GOAL_IDS
    ):
        raise BlindCycleArtifactError(
            "trial result goals do not use the complete canonical inventory"
        )
    goals = GoalVector.from_mapping(
        {
            str(value[0]): _finite(
                value[1],
                label=f"trial goal {value[0]}",
            )
            for value in goal_rows
        }
    )
    certificate = _mapping(
        row["internal_certificate"],
        label="internal certificate",
    )
    validate_internal_certificate_payload(certificate)
    certificate_sha = _sha256(
        row["internal_certificate_sha256"],
        label="internal certificate SHA-256",
    )
    if _json_sha256(certificate) != certificate_sha:
        raise BlindCycleArtifactError(
            "internal certificate self-hash differs"
        )
    bindings = tuple(
        tuple(str(value) for value in binding)
        for binding in certificate["selected_action_bindings"]
    )
    repeat_raw = certificate["stability_repeat_verification"]
    repeat = (
        None
        if repeat_raw is None
        else stability_repeat_verification_from_payload(
            _mapping(
                repeat_raw,
                label="trial stability-repeat verification",
            )
        )
    )
    p6_saturation = _replay_p6_saturation_authority_from_payload(
        _mapping(
            certificate["p6_saturation"],
            label="p6 saturation authority",
        )
    )
    h_level3_saturation = (
        _replay_h_level3_saturation_authority_from_payload(
            _mapping(
                certificate["h_level3_saturation"],
                label="level3 h-saturation authority",
            )
        )
    )
    return BlindCycleResult(
        cycle_index=int(certificate["cycle_index"]),
        accepted_current_state=bool(certificate["accepted_current_state"]),
        status=str(certificate["status"]),
        reasons=tuple(str(value) for value in certificate["reasons"]),
        selected_action_ids=tuple(binding[0] for binding in bindings),
        selected_action_bindings=bindings,
        p_shadow_maximum=float(certificate["p_shadow_maximum"]),
        h_shadow_maximum=float(certificate["h_shadow_maximum"]),
        p_enrichment_action_count=int(
            certificate["p_enrichment_action_count"]
        ),
        h_enrichment_action_count=int(
            certificate["h_enrichment_action_count"]
        ),
        stable_from_previous=bool(certificate["stable_from_previous"]),
        stable_streak=int(certificate["stable_streak"]),
        freeze_ready=bool(certificate["freeze_ready"]),
        goals=goals,
        mesh_forest_sha256=str(certificate["mesh_forest_sha256"]),
        degree_map_sha256=str(certificate["degree_map_sha256"]),
        plan_file_sha256=str(certificate["plan_file_sha256"]),
        plan_content_sha256=str(certificate["plan_content_sha256"]),
        plan_solver_content_sha256=str(
            certificate["plan_solver_content_sha256"]
        ),
        state_sha256=str(certificate["state_sha256"]),
        solution_snapshot_sha256=str(
            certificate["solution_snapshot_sha256"]
        ),
        watchdog_record_file_sha256=str(
            certificate["watchdog_record_file_sha256"]
        ),
        complete_output_sha256=str(certificate["complete_output_sha256"]),
        full_residual_sha256=str(certificate["full_residual_sha256"]),
        adjoint_bundle_sha256=str(certificate["adjoint_bundle_sha256"]),
        shadow_catalog_sha256=str(certificate["shadow_catalog_sha256"]),
        p6_saturation=p6_saturation,
        h_level3_saturation=h_level3_saturation,
        executed_verification_sha256=str(
            certificate["executed_verification_sha256"]
        ),
        stability_repeat_verification=repeat,
        stability_repeat_verification_sha256=str(
            certificate["stability_repeat_verification_sha256"]
        ),
        internal_certificate=MappingProxyType(dict(certificate)),
        internal_certificate_sha256=certificate_sha,
        resource_inventory_sha256=str(
            certificate["resource_inventory_sha256"]
        ),
    )


def _trial_state_outer(trial: BlindTrial) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": TRIAL_STATE_SCHEMA,
        "trial": {
            "trial_id": trial.trial_id,
            "algorithm_id": trial.algorithm_id,
            "source_sha": trial.source_sha,
            "initial_path_id": trial.initial_path_id,
            "initial_mesh_forest_sha256": (
                trial.initial_mesh_forest_sha256
            ),
            "physical_identity_sha256": trial.physical_identity_sha256,
            "maximum_cycles": trial.maximum_cycles,
        },
        "results": [_result_payload(result) for result in trial.results],
        "cycle_chain_root_sha256": trial.cycle_chain_root_sha256,
    }
    return {
        "schema_version": TRIAL_STATE_SCHEMA,
        "sha256": _json_sha256(payload),
        "payload": payload,
    }


def load_trial_state(
    path: Path,
    expected_sha256: str,
) -> BlindTrial:
    """Independently reload and validate one replayable trial state."""

    _outer, payload, _file_sha = _load_bound_outer(
        path,
        expected_sha256,
        schema=TRIAL_STATE_SCHEMA,
        label="trial state",
    )
    payload = _exact(
        payload,
        {
            "schema_version",
            "trial",
            "results",
            "cycle_chain_root_sha256",
        },
        label="trial state payload",
    )
    trial_row = _exact(
        payload["trial"],
        {
            "trial_id",
            "algorithm_id",
            "source_sha",
            "initial_path_id",
            "initial_mesh_forest_sha256",
            "physical_identity_sha256",
            "maximum_cycles",
        },
        label="trial state metadata",
    )
    trial = BlindTrial(
        trial_id=str(trial_row["trial_id"]),
        algorithm_id=str(trial_row["algorithm_id"]),
        source_sha=_source_sha(trial_row["source_sha"]),
        initial_path_id=str(trial_row["initial_path_id"]),
        initial_mesh_forest_sha256=_sha256(
            trial_row["initial_mesh_forest_sha256"],
            label="initial mesh forest SHA-256",
        ),
        physical_identity_sha256=_sha256(
            trial_row["physical_identity_sha256"],
            label="physical identity SHA-256",
        ),
        maximum_cycles=_integer(
            trial_row["maximum_cycles"],
            label="maximum_cycles",
            minimum=1,
        ),
        results=tuple(
            _result_from_payload(row)
            for row in _sequence(payload["results"], label="trial results")
        ),
    )
    if payload["cycle_chain_root_sha256"] != trial.cycle_chain_root_sha256:
        raise BlindCycleArtifactError("trial cycle-chain root differs")
    return trial


def _evidence_outer(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CYCLE_EVIDENCE_SCHEMA,
        "sha256": _json_sha256(payload),
        "payload": dict(payload),
    }


def load_cycle_evidence(
    path: Path,
    expected_sha256: str,
) -> Mapping[str, Any]:
    """Independently reload one cycle decision or controlled-negative."""

    _outer, payload, _file_sha = _load_bound_outer(
        path,
        expected_sha256,
        schema=CYCLE_EVIDENCE_SCHEMA,
        label="cycle evidence",
    )
    payload = _exact(
        payload,
        {
            "schema_version",
            "classification",
            "status",
            "cycle_index",
            "source_sha",
            "mpi_size",
            "input_bindings",
            "goal_sha256",
            "shadow_catalog_sha256",
            "order_applicability_audit",
            "order_applicability_audit_sha256",
            "reference_isolation_manifest_sha256",
            "reference_isolation_report_payload_sha256",
            "trial_before_chain_sha256",
            "trial_after_chain_sha256",
            "trial_state_payload_sha256",
            "result_certificate",
            "result_certificate_sha256",
            "stability_repeat_verification_sha256",
            "controlled_negative",
            "failure",
        },
        label="cycle evidence payload",
    )
    if payload["mpi_size"] != 8:
        raise BlindCycleArtifactError("cycle evidence MPI identity differs")
    if payload["schema_version"] != CYCLE_EVIDENCE_SCHEMA:
        raise BlindCycleArtifactError("cycle evidence schema differs")
    _source_sha(payload["source_sha"])
    cycle = _integer(payload["cycle_index"], label="cycle_index")
    if cycle > 5:
        raise BlindCycleArtifactError("cycle evidence index exceeds five")
    if not isinstance(payload["status"], str) or not payload["status"]:
        raise BlindCycleArtifactError("cycle evidence status must be nonempty")
    bindings = _exact(
        payload["input_bindings"],
        {
            "cycle_binding_file_sha256",
            "cycle_binding_payload_sha256",
            "candidate_record_file_sha256",
            "candidate_output_file_sha256",
            "current_snapshot_file_sha256",
            "shadow_bundle_file_sha256",
            "reference_isolation_report_file_sha256",
            "prior_trial_state_file_sha256",
        },
        label="cycle evidence input bindings",
    )
    for name, value in bindings.items():
        if name == "prior_trial_state_file_sha256" and value is None:
            continue
        _sha256(value, label=name)
    for name in (
        "trial_before_chain_sha256",
        "trial_after_chain_sha256",
        "trial_state_payload_sha256",
    ):
        _sha256(payload[name], label=name)
    for name in ("goal_sha256", "shadow_catalog_sha256"):
        if payload[name] is not None:
            _sha256(payload[name], label=name)
    for name in (
        "order_applicability_audit_sha256",
        "reference_isolation_manifest_sha256",
        "reference_isolation_report_payload_sha256",
    ):
        if payload[name] is not None:
            _sha256(payload[name], label=name)
    applicability = payload["order_applicability_audit"]
    if applicability is None:
        if payload["order_applicability_audit_sha256"] is not None:
            raise BlindCycleArtifactError(
                "absent applicability audit has a non-null hash"
            )
    else:
        rows = _sequence(
            applicability,
            label="order applicability audit",
        )
        if len(rows) != len(FIXED_ORDER_KEYS):
            raise BlindCycleArtifactError(
                "order applicability audit misses the fixed N=8 inventory"
            )
        normalized_rows = []
        for raw, identity in zip(rows, FIXED_ORDER_KEYS, strict=True):
            row = _exact(
                raw,
                {
                    "goal_id",
                    "port",
                    "m",
                    "n",
                    "propagating",
                    "power_applicable",
                    "input_total_power_state",
                    "input_cross_power_state",
                    "formal_power_value",
                    "mapping",
                },
                label="order applicability row",
            )
            expected_goal = (
                f"{identity[0]}:m{identity[1]}:n{identity[2]}:power"
            )
            propagating = row["propagating"]
            value = _finite(
                row["formal_power_value"],
                label="formal power value",
            )
            if (
                (row["port"], row["m"], row["n"]) != identity
                or row["goal_id"] != expected_goal
                or type(propagating) is not bool
                or row["power_applicable"] is not propagating
                or value < 0.0
            ):
                raise BlindCycleArtifactError(
                    "order applicability identity or value differs"
                )
            if propagating:
                expected = (
                    "finite_nonnegative",
                    "finite_nonnegative",
                    "physical_power_coordinate",
                )
            else:
                expected = (
                    "null_not_applicable",
                    "null_not_applicable",
                    "explicit_not_applicable_to_formal_zero",
                )
                if value != 0.0:
                    raise BlindCycleArtifactError(
                        "evanescent formal power is not deterministic zero"
                    )
            if (
                row["input_total_power_state"],
                row["input_cross_power_state"],
                row["mapping"],
            ) != expected:
                raise BlindCycleArtifactError(
                    "order applicability mapping semantics differ"
                )
            normalized_rows.append(dict(row))
        if payload["order_applicability_audit_sha256"] != _json_sha256(
            normalized_rows
        ):
            raise BlindCycleArtifactError(
                "order applicability audit hash differs"
            )
    if payload["failure"] is not None and not isinstance(
        payload["failure"],
        str,
    ):
        raise BlindCycleArtifactError("cycle evidence failure must be text")
    certificate = payload["result_certificate"]
    if certificate is not None:
        certificate = _mapping(
            certificate,
            label="cycle result certificate",
        )
        validate_internal_certificate_payload(certificate)
        certificate_sha = _sha256(
            payload["result_certificate_sha256"],
            label="result certificate SHA-256",
        )
        if certificate_sha != _json_sha256(
            certificate
        ):
            raise BlindCycleArtifactError(
                "cycle result certificate hash differs"
            )
        if (
            certificate["cycle_index"] != cycle
            or certificate["status"] != payload["status"]
            or certificate["goal_sha256"] != payload["goal_sha256"]
            or certificate["shadow_catalog_sha256"]
            != payload["shadow_catalog_sha256"]
            or certificate["stability_repeat_verification_sha256"]
            != payload["stability_repeat_verification_sha256"]
        ):
            raise BlindCycleArtifactError(
                "cycle result certificate and evidence differ"
            )
        if (
            applicability is None
            or payload["reference_isolation_manifest_sha256"] is None
            or payload["reference_isolation_report_payload_sha256"] is None
        ):
            raise BlindCycleArtifactError(
                "passing cycle lacks applicability/isolation evidence"
            )
    elif (
        payload["result_certificate_sha256"] is not None
        or payload["stability_repeat_verification_sha256"] is not None
    ):
        raise BlindCycleArtifactError(
            "absent result certificate has a non-null result/repeat hash"
        )
    if certificate is None:
        if not isinstance(payload["failure"], str) or not payload["failure"]:
            raise BlindCycleArtifactError(
                "input-rejected evidence must explain its failure"
            )
    elif payload["failure"] is not None:
        raise BlindCycleArtifactError(
            "cycle result evidence cannot also claim an input failure"
        )
    controlled = payload["controlled_negative"]
    if type(controlled) is not bool:
        raise BlindCycleArtifactError(
            "controlled_negative must be boolean"
        )
    if payload["classification"] == "controlled_negative":
        if controlled is not True or (
            certificate is not None
            and certificate["accepted_current_state"] is not False
        ):
            raise BlindCycleArtifactError(
                "controlled-negative classification is inconsistent"
            )
    elif payload["classification"] == "blind_cycle_decision":
        if (
            controlled is not False
            or certificate is None
            or certificate["accepted_current_state"] is not True
        ):
            raise BlindCycleArtifactError(
                "passing cycle-decision classification is inconsistent"
            )
    else:
        raise BlindCycleArtifactError("cycle evidence classification differs")
    return MappingProxyType(dict(payload))


def _atomic_pair(
    evidence_path: Path,
    state_path: Path,
    evidence: Mapping[str, Any],
    state: Mapping[str, Any],
) -> None:
    destinations = (
        _safe_path(evidence_path, label="cycle evidence output"),
        _safe_path(state_path, label="trial state output"),
    )
    if destinations[0] == destinations[1]:
        raise BlindCycleArtifactError(
            "cycle evidence and state paths must differ"
        )
    if any(path.exists() for path in destinations):
        raise FileExistsError("refusing to overwrite blind cycle artifacts")
    encoded = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
        for value in (evidence, state)
    )
    temporaries: list[Path] = []
    linked: list[Path] = []
    try:
        for path, content in zip(destinations, encoded, strict=True):
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
            )
            temporary = Path(name)
            temporaries.append(temporary)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, path in zip(
            temporaries,
            destinations,
            strict=True,
        ):
            os.link(temporary, path)
            linked.append(path)
        for temporary in temporaries:
            temporary.unlink()
        for directory in {path.parent for path in destinations}:
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except Exception:
        for path in linked:
            path.unlink(missing_ok=True)
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
        raise


def _initial_trial(
    binding: Mapping[str, Any],
) -> BlindTrial:
    trial = _trial_metadata(
        _mapping(binding["trial"], label="trial metadata")
    )
    return BlindTrial(
        trial_id=str(trial["trial_id"]),
        algorithm_id=str(trial["algorithm_id"]),
        source_sha=_source_sha(binding["source_sha"]),
        initial_path_id=str(trial["initial_path_id"]),
        initial_mesh_forest_sha256=_sha256(
            trial["initial_mesh_forest_sha256"],
            label="initial mesh forest SHA-256",
        ),
        physical_identity_sha256=_sha256(
            trial["physical_identity_sha256"],
            label="physical identity SHA-256",
        ),
        maximum_cycles=int(trial["maximum_cycles"]),
    )


def _validate_trial_binding(
    binding: Mapping[str, Any],
    trial: BlindTrial,
    *,
    prior_state_file_sha256: str | None,
) -> None:
    metadata = _trial_metadata(
        _mapping(binding["trial"], label="trial metadata")
    )
    expected = {
        "trial_id": trial.trial_id,
        "algorithm_id": trial.algorithm_id,
        "initial_path_id": trial.initial_path_id,
        "initial_mesh_forest_sha256": trial.initial_mesh_forest_sha256,
        "physical_identity_sha256": trial.physical_identity_sha256,
        "maximum_cycles": trial.maximum_cycles,
    }
    if dict(metadata) != expected or binding["source_sha"] != trial.source_sha:
        raise BlindCycleArtifactError(
            "cycle binding and replay trial identity differ"
        )
    transition = _mapping(binding["transition"], label="transition")
    cycle = int(binding["cycle_index"])
    if cycle == 0:
        if (
            prior_state_file_sha256 is not None
            or transition["previous_trial_state_file_sha256"] is not None
            or transition["previous_cycle_certificate_sha256"] is not None
            or transition["executed_action_verifications"]
            or transition["stability_repeat_verification"] is not None
        ):
            raise BlindCycleArtifactError(
                "cycle zero cannot consume a prior transition"
            )
        return
    if prior_state_file_sha256 is None or not trial.results:
        raise BlindCycleArtifactError(
            "nonzero cycle requires one replayable prior state"
        )
    if (
        transition["previous_trial_state_file_sha256"]
        != prior_state_file_sha256
        or transition["previous_cycle_certificate_sha256"]
        != trial.results[-1].internal_certificate_sha256
    ):
        raise BlindCycleArtifactError(
            "transition is not bound to the prior state/action certificate"
        )
    expected_bindings = {
        row[0]: row[1:]
        for row in trial.results[-1].selected_action_bindings
    }
    verifications = _verification_rows(transition)
    repeat = _stability_repeat_row(transition)
    observed = {row.action_id: row for row in verifications}
    if len(observed) != len(verifications):
        raise BlindCycleArtifactError(
            "executed verification inventory contains duplicate actions"
        )
    previous = trial.results[-1]
    if expected_bindings:
        if repeat is not None:
            raise BlindCycleArtifactError(
                "selected action cannot use a stability-repeat verification"
            )
        if set(observed) != set(expected_bindings):
            raise BlindCycleArtifactError(
                "executed verification inventory differs from selected action"
            )
    else:
        if observed:
            raise BlindCycleArtifactError(
                "stability-repeat cycle cannot use shadow verification"
            )
        repeat_required = (
            previous.accepted_current_state and not previous.freeze_ready
        )
        if repeat_required and repeat is None:
            raise BlindCycleArtifactError(
                "accepted no-action cycle requires a p-keep stability repeat"
            )
        if not repeat_required and repeat is not None:
            raise BlindCycleArtifactError(
                "stability-repeat verification is unexpected"
            )
        if repeat is not None:
            current_identity = SimpleNamespace(
                mesh_forest_sha256=str(binding["mesh_forest_sha256"]),
                degree_map_sha256=str(binding["degree_map_sha256"]),
                plan_file_sha256=str(binding["plan_file_sha256"]),
                plan_content_sha256=str(binding["plan_content_sha256"]),
                plan_solver_content_sha256=str(
                    binding["plan_solver_content_sha256"]
                ),
                state_sha256=str(binding["state_sha256"]),
                solution_snapshot_sha256=str(
                    binding["solution_snapshot_sha256"]
                ),
                watchdog_record_file_sha256=str(
                    binding["candidate_record_file_sha256"]
                ),
            )
            if not repeat.validates_transition(
                previous_result=previous,
                current_cycle=current_identity,
            ):
                raise BlindCycleArtifactError(
                    "stability-repeat transition/plan binding differs"
                )
    for action_id, verification in observed.items():
        (
            action_sha,
            predicted_delta_sha,
            transition_action_sha,
            transition_action_file_sha,
            transition_action_identity_sha,
            next_mesh_forest_sha,
            next_degree_map_sha,
        ) = expected_bindings[action_id]
        if (
            verification.action_sha256 != action_sha
            or verification.predicted_delta_sha256 != predicted_delta_sha
            or verification.transition_action_sha256
            != transition_action_sha
            or verification.transition_action_file_sha256
            != transition_action_file_sha
            or verification.transition_action_identity_sha256
            != transition_action_identity_sha
            or verification.next_mesh_forest_sha256
            != next_mesh_forest_sha
            or verification.next_degree_map_sha256 != next_degree_map_sha
            or verification.next_mesh_forest_sha256
            != binding["mesh_forest_sha256"]
            or verification.next_degree_map_sha256
            != binding["degree_map_sha256"]
            or verification.next_plan_file_sha256
            != binding["plan_file_sha256"]
            or verification.next_plan_content_sha256
            != binding["plan_content_sha256"]
            or verification.next_state_sha256 != binding["state_sha256"]
            or verification.before_output_sha256
            != trial.results[-1].complete_output_sha256
            or verification.after_output_sha256
            != binding["complete_output_sha256"]
        ):
            raise BlindCycleArtifactError(
                "executed verification transition/next-plan binding differs"
            )


def _cycle_isolation_manifest(
    binding: Mapping[str, Any],
    *,
    shadow_bundle_file_sha256: str,
    catalog: ShadowCatalog,
) -> dict[str, Any]:
    trial = _mapping(binding["trial"], label="trial metadata")
    return build_cycle_manifest(
        trial_id=str(trial["trial_id"]),
        algorithm_id=str(trial["algorithm_id"]),
        source_sha=str(binding["source_sha"]),
        initial_path_id=str(trial["initial_path_id"]),
        maximum_cycles=int(trial["maximum_cycles"]),
        cycle_index=int(binding["cycle_index"]),
        state=REFERENCE_ISOLATION_MANIFEST_STATE,
        mesh_forest_sha256=str(binding["mesh_forest_sha256"]),
        degree_map_sha256=str(binding["degree_map_sha256"]),
        solution_snapshot_sha256=str(
            binding["solution_snapshot_sha256"]
        ),
        goal_inventory_sha256=FORMAL_GOAL_INVENTORY_SHA256,
        full_residual_sha256=str(binding["full_residual_sha256"]),
        adjoint_bundle_sha256=shadow_bundle_file_sha256,
        p_shadow_bundle_sha256=(
            shadow_bundle_file_sha256 if catalog.p_actions else None
        ),
        h_shadow_bundle_sha256=(
            shadow_bundle_file_sha256 if catalog.h_actions else None
        ),
        resource_inventory_sha256=str(
            binding["resource_inventory_sha256"]
        ),
    )


def run_blind_cycle(
    *,
    candidate_output_path: Path,
    candidate_output_sha256: str,
    shadow_bundle_path: Path,
    shadow_bundle_sha256: str,
    cycle_binding_path: Path,
    cycle_binding_sha256: str,
    reference_isolation_report_path: Path,
    reference_isolation_report_sha256: str,
    evidence_output_path: Path,
    trial_state_output_path: Path,
    prior_trial_state_path: Path | None = None,
    prior_trial_state_sha256: str | None = None,
    preserve_controlled_negative: bool = True,
) -> BlindCycleWriteReceipt:
    """Advance one cycle, or seal an input failure without claiming a pass."""

    binding, binding_payload_sha, binding_file_sha = _load_cycle_binding(
        cycle_binding_path,
        cycle_binding_sha256,
    )
    cycle_index = int(binding["cycle_index"])
    if (prior_trial_state_path is None) != (
        prior_trial_state_sha256 is None
    ):
        raise BlindCycleArtifactError(
            "prior trial-state path and SHA-256 must be paired"
        )
    prior_state_file_sha = None
    if prior_trial_state_path is None:
        trial = _initial_trial(binding)
    else:
        prior_state_file_sha = _sha256(
            prior_trial_state_sha256,
            label="prior trial-state SHA-256",
        )
        trial = load_trial_state(
            prior_trial_state_path,
            prior_state_file_sha,
        )
    _validate_trial_binding(
        binding,
        trial,
        prior_state_file_sha256=prior_state_file_sha,
    )
    if cycle_index != len(trial.results):
        raise BlindCycleArtifactError(
            "cycle binding is not contiguous with replay state"
        )
    before_chain = trial.cycle_chain_root_sha256
    input_bindings = {
        "cycle_binding_file_sha256": binding_file_sha,
        "cycle_binding_payload_sha256": binding_payload_sha,
        "candidate_output_file_sha256": str(
            binding["candidate_output_file_sha256"]
        ),
        "candidate_record_file_sha256": str(
            binding["candidate_record_file_sha256"]
        ),
        "current_snapshot_file_sha256": str(
            binding["current_snapshot_file_sha256"]
        ),
        "shadow_bundle_file_sha256": str(
            binding["shadow_bundle_file_sha256"]
        ),
        "reference_isolation_report_file_sha256": _sha256(
            str(binding["reference_isolation_report_file_sha256"]),
            label="reference-isolation report file SHA-256",
        ),
        "prior_trial_state_file_sha256": prior_state_file_sha,
    }
    result: BlindCycleResult | None = None
    failure: str | None = None
    goal_sha: str | None = None
    catalog_sha: str | None = None
    applicability_audit: tuple[dict[str, Any], ...] | None = None
    applicability_audit_sha: str | None = None
    isolation_manifest_sha: str | None = None
    isolation_report_payload_sha: str | None = None
    advanced = False
    try:
        if (
            binding["reference_isolation_report_file_sha256"]
            != reference_isolation_report_sha256
        ):
            raise BlindCycleArtifactError(
                "reference-isolation report is not bound by cycle binding"
            )
        if binding["candidate_output_file_sha256"] != candidate_output_sha256:
            raise BlindCycleArtifactError(
                "candidate output is not bound by the cycle manifest"
            )
        candidate, candidate_file_sha = _load_bound_json(
            candidate_output_path,
            candidate_output_sha256,
            label="candidate output",
        )
        input_bindings["candidate_output_file_sha256"] = candidate_file_sha
        goals, applicability_audit = _goal_vector_and_applicability_audit(
            candidate
        )
        applicability_audit_sha = _json_sha256(list(applicability_audit))
        goal_sha = goals.sha256
        complete_output_sha = _json_sha256(candidate)
        if binding["complete_output_sha256"] != complete_output_sha:
            raise BlindCycleArtifactError(
                "candidate output payload SHA differs from cycle binding"
            )
        if binding["shadow_bundle_file_sha256"] != shadow_bundle_sha256:
            raise BlindCycleArtifactError(
                "shadow bundle is not bound by the cycle manifest"
            )
        _outer, shadow_payload, shadow_file_sha = _load_bound_outer(
            shadow_bundle_path,
            shadow_bundle_sha256,
            schema=SHADOW_BUNDLE_SCHEMA,
            label="external shadow bundle",
        )
        input_bindings["shadow_bundle_file_sha256"] = shadow_file_sha
        catalog = _shadow_catalog(
            shadow_payload,
            current=goals,
            source_sha=str(binding["source_sha"]),
            trial_id=trial.trial_id,
            cycle_index=cycle_index,
            mesh_forest_sha256=str(binding["mesh_forest_sha256"]),
            degree_map_sha256=str(binding["degree_map_sha256"]),
            plan_file_sha256=str(binding["plan_file_sha256"]),
            complete_output_sha256=complete_output_sha,
        )
        catalog_sha = catalog.sha256
        isolation_manifest = _cycle_isolation_manifest(
            binding,
            shadow_bundle_file_sha256=shadow_file_sha,
            catalog=catalog,
        )
        isolation_manifest_sha = cycle_manifest_sha256(
            isolation_manifest
        )
        (
            _isolation_report,
            isolation_report_file_sha,
            isolation_report_payload_sha,
        ) = _load_isolation_audit(
            reference_isolation_report_path,
            reference_isolation_report_sha256,
            source_sha=str(binding["source_sha"]),
            manifest_sha256=isolation_manifest_sha,
        )
        input_bindings[
            "reference_isolation_report_file_sha256"
        ] = isolation_report_file_sha
        inventory = StructuralInventory(
            **dict(
                _mapping(
                    binding["resource_inventory"],
                    label="resource inventory",
                )
            )
        )
        authority = validate_internal_gate_authority(
            _mapping(
                binding["internal_gates"],
                label="internal-Gate authority",
            ),
            expected_source_sha=str(binding["source_sha"]),
            expected_trial_id=trial.trial_id,
            expected_cycle_index=cycle_index,
            expected_candidate_record_file_sha256=str(
                binding["candidate_record_file_sha256"]
            ),
            expected_candidate_output_file_sha256=candidate_file_sha,
            expected_candidate_output_payload_sha256=complete_output_sha,
            expected_plan_file_sha256=str(binding["plan_file_sha256"]),
            expected_plan_payload_sha256=str(
                binding["plan_content_sha256"]
            ),
            expected_mesh_forest_sha256=str(
                binding["mesh_forest_sha256"]
            ),
            expected_degree_map_sha256=str(binding["degree_map_sha256"]),
            expected_snapshot_file_sha256=str(
                binding["current_snapshot_file_sha256"]
            ),
            expected_snapshot_payload_sha256=str(
                binding["solution_snapshot_sha256"]
            ),
            expected_snapshot_full_residual_sha256=str(
                binding["full_residual_sha256"]
            ),
        )
        gates = InternalGates(**dict(authority["gates"]))
        if not math.isclose(
            float(candidate["full_explicit_true_residual"]),
            gates.full_explicit_residual,
            rel_tol=0.0,
            abs_tol=1.0e-18,
        ):
            raise BlindCycleArtifactError(
                "candidate residual and InternalGates differ"
            )
        transition = _mapping(binding["transition"], label="transition")
        cycle_input = BlindCycleInput(
            cycle_index=cycle_index,
            mesh_forest_sha256=str(binding["mesh_forest_sha256"]),
            degree_map_sha256=str(binding["degree_map_sha256"]),
            plan_file_sha256=str(binding["plan_file_sha256"]),
            plan_content_sha256=str(binding["plan_content_sha256"]),
            plan_solver_content_sha256=str(
                binding["plan_solver_content_sha256"]
            ),
            state_sha256=str(binding["state_sha256"]),
            solution_snapshot_sha256=str(
                binding["solution_snapshot_sha256"]
            ),
            watchdog_record_file_sha256=str(
                binding["candidate_record_file_sha256"]
            ),
            complete_output_sha256=complete_output_sha,
            full_residual_sha256=str(binding["full_residual_sha256"]),
            adjoint_bundle_sha256=shadow_file_sha,
            resource_inventory_sha256=str(
                binding["resource_inventory_sha256"]
            ),
            goals=goals,
            shadows=catalog,
            inventory=inventory,
            gates=gates,
            executed_action_verifications=_verification_rows(transition),
            stability_repeat_verification=_stability_repeat_row(
                transition
            ),
        )
        trial = advance_blind_trial(trial, cycle_input)
        result = trial.results[-1]
        advanced = True
    except (BlindCycleArtifactError, TypeError, ValueError) as exc:
        if not preserve_controlled_negative:
            raise BlindCycleArtifactError(str(exc)) from exc
        failure = str(exc)

    state_outer = _trial_state_outer(trial)
    state_payload_sha = str(state_outer["sha256"])
    if result is None:
        classification = "controlled_negative"
        status = "input_rejected_controlled_negative"
        controlled_negative = True
    elif not result.accepted_current_state:
        classification = "controlled_negative"
        status = result.status
        controlled_negative = True
    else:
        classification = "blind_cycle_decision"
        status = result.status
        controlled_negative = False
    evidence_payload: dict[str, Any] = {
        "schema_version": CYCLE_EVIDENCE_SCHEMA,
        "classification": classification,
        "status": status,
        "cycle_index": cycle_index,
        "source_sha": str(binding["source_sha"]),
        "mpi_size": 8,
        "input_bindings": input_bindings,
        "goal_sha256": goal_sha,
        "shadow_catalog_sha256": catalog_sha,
        "order_applicability_audit": (
            None
            if applicability_audit is None
            else list(applicability_audit)
        ),
        "order_applicability_audit_sha256": applicability_audit_sha,
        "reference_isolation_manifest_sha256": isolation_manifest_sha,
        "reference_isolation_report_payload_sha256": (
            isolation_report_payload_sha
        ),
        "trial_before_chain_sha256": before_chain,
        "trial_after_chain_sha256": trial.cycle_chain_root_sha256,
        "trial_state_payload_sha256": state_payload_sha,
        "result_certificate": (
            None if result is None else dict(result.internal_certificate)
        ),
        "result_certificate_sha256": (
            None
            if result is None
            else result.internal_certificate_sha256
        ),
        "stability_repeat_verification_sha256": (
            None
            if result is None
            else result.stability_repeat_verification_sha256
        ),
        "controlled_negative": controlled_negative,
        "failure": failure,
    }
    evidence_outer = _evidence_outer(evidence_payload)
    _atomic_pair(
        evidence_output_path,
        trial_state_output_path,
        evidence_outer,
        state_outer,
    )
    evidence_file_sha = _file_sha256(evidence_output_path.resolve())
    state_file_sha = _file_sha256(trial_state_output_path.resolve())
    load_cycle_evidence(evidence_output_path, evidence_file_sha)
    reloaded = load_trial_state(trial_state_output_path, state_file_sha)
    if reloaded.cycle_chain_root_sha256 != trial.cycle_chain_root_sha256:
        raise BlindCycleArtifactError(
            "post-write trial replay validation differs"
        )
    return BlindCycleWriteReceipt(
        evidence_path=evidence_output_path.resolve(),
        evidence_file_sha256=evidence_file_sha,
        evidence_payload_sha256=str(evidence_outer["sha256"]),
        trial_state_path=trial_state_output_path.resolve(),
        trial_state_file_sha256=state_file_sha,
        trial_state_payload_sha256=state_payload_sha,
        cycle_index=cycle_index,
        status=status,
        controlled_negative=controlled_negative,
        trial_advanced=advanced,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--candidate-output-sha256", required=True)
    parser.add_argument("--shadow-bundle", type=Path, required=True)
    parser.add_argument("--shadow-bundle-sha256", required=True)
    parser.add_argument("--cycle-binding", type=Path, required=True)
    parser.add_argument("--cycle-binding-sha256", required=True)
    parser.add_argument(
        "--reference-isolation-report",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--reference-isolation-report-sha256",
        required=True,
    )
    parser.add_argument("--prior-trial-state", type=Path)
    parser.add_argument("--prior-trial-state-sha256")
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--trial-state-output", type=Path, required=True)
    parser.add_argument(
        "--reject-incomplete-without-evidence",
        action="store_true",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = run_blind_cycle(
            candidate_output_path=args.candidate_output,
            candidate_output_sha256=args.candidate_output_sha256,
            shadow_bundle_path=args.shadow_bundle,
            shadow_bundle_sha256=args.shadow_bundle_sha256,
            cycle_binding_path=args.cycle_binding,
            cycle_binding_sha256=args.cycle_binding_sha256,
            reference_isolation_report_path=(
                args.reference_isolation_report
            ),
            reference_isolation_report_sha256=(
                args.reference_isolation_report_sha256
            ),
            evidence_output_path=args.evidence_output,
            trial_state_output_path=args.trial_state_output,
            prior_trial_state_path=args.prior_trial_state,
            prior_trial_state_sha256=args.prior_trial_state_sha256,
            preserve_controlled_negative=(
                not args.reject_incomplete_without_evidence
            ),
        )
    except (BlindCycleArtifactError, FileExistsError, OSError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": receipt.status,
                "cycle_index": receipt.cycle_index,
                "controlled_negative": receipt.controlled_negative,
                "trial_advanced": receipt.trial_advanced,
                "evidence_file_sha256": receipt.evidence_file_sha256,
                "trial_state_file_sha256": (
                    receipt.trial_state_file_sha256
                ),
            },
            sort_keys=True,
        )
    )
    return 3 if receipt.controlled_negative else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BlindCycleArtifactError",
    "BlindCycleWriteReceipt",
    "candidate_order_applicability_audit",
    "goal_vector_from_candidate_output",
    "load_cycle_evidence",
    "load_trial_state",
    "main",
    "run_blind_cycle",
]
