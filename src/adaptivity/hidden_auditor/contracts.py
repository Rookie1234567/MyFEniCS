"""Strict JSON contracts for the Task035e final hidden auditor.

The auditor is deliberately independent of :mod:`blind_controller`.  It
accepts only frozen JSON evidence, verifies every content binding, and exposes
no interface that a running adaptive controller can use as an oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Integral, Real
import re
from typing import Any, Mapping


FREEZE_RECEIPT_SCHEMA = "task035e.hidden-audit-freeze-receipt.v1"
CANDIDATE_BUNDLE_SCHEMA = "task035e.frozen-candidate-audit-bundle.v1"
CANDIDATE_OUTPUT_SCHEMA = "task035e.frozen-candidate-outputs.v1"
TWO_PATH_GATE_SCHEMA = "task035e.two-path-freeze-gate.v1"
HIDDEN_AUDIT_SCHEMA = "task035e.final-hidden-audit.v1"

FIXED_PORTS = ("top", "bottom")
FIXED_M = (0, -1, -2, -3, -4, -5, -6, -7)
FIXED_N = 0
FIXED_ORDER_KEYS = tuple(
    (port, m, FIXED_N) for port in FIXED_PORTS for m in FIXED_M
)
FIXED_GOAL_IDS = tuple(
    f"{port}:m{m}:n{n}:{quantity}"
    for port, m, n in FIXED_ORDER_KEYS
    for quantity in ("power", "co_amp_real", "co_amp_imag")
)
ORDER_GOAL_IDS = FIXED_GOAL_IDS
FORMAL_TOTAL_NAMES = (
    "R00_s",
    "R00_p",
    "R00_total",
    "R_total",
    "T_total",
    "A_closure",
    "A_volume",
)
BLIND_FORMAL_TOTAL_NAMES = (
    "R00_total",
    "R_total",
    "T_total",
    "A_closure",
    "A_volume",
)
FORMAL_FIELD_SCALAR_NAMES = (
    "interface_probe_l2",
    "volume_probe_l2",
)
FORMAL_FIELD_COMPLEX_NAMES = (
    "interface_probe_complex",
    "volume_probe_complex",
)
FORMAL_GOAL_IDS = (
    *ORDER_GOAL_IDS,
    *(f"scalar/{name}" for name in BLIND_FORMAL_TOTAL_NAMES),
    *(f"scalar/{name}" for name in FORMAL_FIELD_SCALAR_NAMES),
    *(
        f"complex/{name}/{component}"
        for name in FORMAL_FIELD_COMPLEX_NAMES
        for component in ("real", "imag")
    ),
)
FORMAL_GOAL_INVENTORY_SHA256 = hashlib.sha256(
    json.dumps(FORMAL_GOAL_IDS, separators=(",", ":")).encode("ascii")
).hexdigest()
EXPECTED_POWER_OUTPUT_IDS = frozenset(
    f"order/{port}/m{m}/n{n}/total_power"
    for port, m, n in FIXED_ORDER_KEYS
)
EXPECTED_AMPLITUDE_OUTPUT_IDS = frozenset(
    f"order/{port}/m{m}/n{n}/co_polarized_amplitude"
    for port, m, n in FIXED_ORDER_KEYS
)
EXPECTED_TOTAL_OUTPUT_IDS = frozenset(
    f"scalar/{name}" for name in FORMAL_TOTAL_NAMES
)
EXPECTED_FIELD_OUTPUT_IDS = frozenset(
    {
        "field/interface_field/relative_l2",
        "field/volume_field/relative_l2",
    }
)
EXPECTED_HARD_GATE_IDS = frozenset(
    {
        "full_explicit_true_residual",
        "energy_balance_R_plus_T_plus_Avolume",
        "Aclosure_vs_Avolume",
        "Avolume_nonnegative",
        "fixed_order_physical_metadata",
        "full_propagating_spectrum_audit",
    }
)
FULL_SPECTRUM_GATE_SCHEMA = (
    "task035e.full-propagating-spectrum-audit.v1"
)
FULL_SPECTRUM_QUANTITIES = (
    "total_power",
    "cross_polarized_power",
    "co_polarized_amplitude",
    "cross_polarized_amplitude",
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class HiddenAuditContractError(ValueError):
    """Raised when frozen or audit JSON violates a closed contract."""


def _validate_pure_json(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, Integral) and not isinstance(value, bool):
        return
    if isinstance(value, Real) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise HiddenAuditContractError(f"{path} must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_pure_json(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise HiddenAuditContractError(
                    f"{path} object keys must be strings"
                )
            _validate_pure_json(item, path=f"{path}.{key}")
        return
    raise HiddenAuditContractError(
        f"{path} must contain only JSON-native values"
    )


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the one canonical byte representation used by all bindings."""

    _validate_pure_json(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    """Hash one pure-JSON object using the Task035e canonical encoding."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def exact_mapping(
    value: Any,
    expected_keys: frozenset[str],
    *,
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HiddenAuditContractError(f"{path} must be an object")
    observed = set(value)
    if observed != expected_keys:
        missing = sorted(expected_keys - observed)
        extra = sorted(observed - expected_keys)
        raise HiddenAuditContractError(
            f"{path} keys differ; missing={missing}, extra={extra}"
        )
    return value


def require_sha256(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise HiddenAuditContractError(
            f"{path} must be a lowercase SHA-256"
        )
    return value


def require_source_sha(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise HiddenAuditContractError(
            f"{path} must be a lowercase 40- or 64-character source SHA"
        )
    return value


def finite_float(value: Any, *, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise HiddenAuditContractError(f"{path} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise HiddenAuditContractError(f"{path} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class CandidateFreezeReceipt:
    """Hash-bound authority proving that no candidate data can still change."""

    schema_version: str
    trial_id: str
    algorithm_id: str
    source_sha: str
    initial_path_id: str
    initial_mesh_forest_sha256: str
    cycle_chain_root_sha256: str
    cycle_index: int
    physical_identity_sha256: str
    mesh_forest_sha256: str
    degree_map_sha256: str
    output_sha256: str
    internal_certificate_sha256: str
    resource_inventory_sha256: str
    two_path_gate_sha256: str
    frozen_payload_sha256: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> CandidateFreezeReceipt:
        keys = frozenset(field_name for field_name in cls.__dataclass_fields__)
        row = exact_mapping(value, keys, path="freeze_receipt")
        if row["schema_version"] != FREEZE_RECEIPT_SCHEMA:
            raise HiddenAuditContractError(
                "freeze_receipt.schema_version is unsupported"
            )
        for name in ("trial_id", "algorithm_id", "initial_path_id"):
            if not isinstance(row[name], str) or not row[name].strip():
                raise HiddenAuditContractError(
                    f"freeze_receipt.{name} must be nonempty"
                )
        require_source_sha(row["source_sha"], path="freeze_receipt.source_sha")
        if (
            isinstance(row["cycle_index"], bool)
            or not isinstance(row["cycle_index"], Integral)
            or not 0 <= int(row["cycle_index"]) <= 5
        ):
            raise HiddenAuditContractError(
                "freeze_receipt.cycle_index must be in [0, 5]"
            )
        for name in (
            "initial_mesh_forest_sha256",
            "cycle_chain_root_sha256",
            "physical_identity_sha256",
            "mesh_forest_sha256",
            "degree_map_sha256",
            "output_sha256",
            "internal_certificate_sha256",
            "resource_inventory_sha256",
            "two_path_gate_sha256",
            "frozen_payload_sha256",
        ):
            require_sha256(row[name], path=f"freeze_receipt.{name}")
        unsigned = dict(row)
        observed_frozen_sha = unsigned.pop("frozen_payload_sha256")
        expected_frozen_sha = canonical_json_sha256(unsigned)
        if observed_frozen_sha != expected_frozen_sha:
            raise HiddenAuditContractError(
                "freeze_receipt frozen payload SHA-256 mismatch"
            )
        return cls(
            schema_version=str(row["schema_version"]),
            trial_id=str(row["trial_id"]),
            algorithm_id=str(row["algorithm_id"]),
            source_sha=str(row["source_sha"]),
            initial_path_id=str(row["initial_path_id"]),
            initial_mesh_forest_sha256=str(
                row["initial_mesh_forest_sha256"]
            ),
            cycle_chain_root_sha256=str(row["cycle_chain_root_sha256"]),
            cycle_index=int(row["cycle_index"]),
            physical_identity_sha256=str(row["physical_identity_sha256"]),
            mesh_forest_sha256=str(row["mesh_forest_sha256"]),
            degree_map_sha256=str(row["degree_map_sha256"]),
            output_sha256=str(row["output_sha256"]),
            internal_certificate_sha256=str(
                row["internal_certificate_sha256"]
            ),
            resource_inventory_sha256=str(
                row["resource_inventory_sha256"]
            ),
            two_path_gate_sha256=str(row["two_path_gate_sha256"]),
            frozen_payload_sha256=str(row["frozen_payload_sha256"]),
        )


@dataclass(frozen=True, slots=True)
class AuditItem:
    """One independently recomputed candidate-vs-reference comparison."""

    category: str
    output_id: str
    reference_value: Any
    candidate_value: Any
    actual_error: float | None
    tolerance: float | None
    reference_uncertainty: float | None
    applicable: bool
    passed: bool
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "output_id": self.output_id,
            "reference_value": self.reference_value,
            "candidate_value": self.candidate_value,
            "actual_error": self.actual_error,
            "tolerance": self.tolerance,
            "reference_uncertainty": self.reference_uncertainty,
            "applicable": self.applicable,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AuditGate:
    """One hard physical or numerical gate."""

    gate_id: str
    actual: Any
    limit: Any
    passed: bool
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "actual": self.actual,
            "limit": self.limit,
            "passed": self.passed,
            "reason": self.reason,
        }


_SPECTRUM_ACTUAL_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "reference_orders",
        "candidate_orders",
        "missing_candidate_orders",
        "unexpected_candidate_orders",
        "metadata_comparisons",
        "value_comparisons",
        "passed_value_count",
        "total_value_count",
    }
)
_SPECTRUM_IDENTITY_KEYS = frozenset({"port", "m", "n"})
_SPECTRUM_METADATA_COMPARISON_KEYS = frozenset(
    {"port", "m", "n", "reference", "candidate", "passed"}
)
_SPECTRUM_METADATA_KEYS = frozenset(
    {"kz", "admittance", "normalization_identity"}
)
_SPECTRUM_VALUE_COMPARISON_KEYS = frozenset(
    {
        "port",
        "m",
        "n",
        "quantity",
        "reference_value",
        "candidate_value",
        "actual_error",
        "tolerance",
        "reference_uncertainty",
        "passed",
    }
)
_SPECTRUM_COMPLEX_KEYS = frozenset({"real", "imag"})
_SPECTRUM_GATE_LIMIT = {
    "required_status": "completed_and_passed",
}


def _spectrum_order_key(
    identity: tuple[str, int, int],
) -> tuple[int, int, int]:
    return FIXED_PORTS.index(identity[0]), -identity[1], identity[2]


def _spectrum_identity(
    value: Any,
    *,
    path: str,
) -> tuple[str, int, int]:
    row = exact_mapping(value, _SPECTRUM_IDENTITY_KEYS, path=path)
    if row["port"] not in FIXED_PORTS:
        raise HiddenAuditContractError(f"{path}.port is unsupported")
    if (
        isinstance(row["m"], bool)
        or not isinstance(row["m"], Integral)
        or isinstance(row["n"], bool)
        or not isinstance(row["n"], Integral)
    ):
        raise HiddenAuditContractError(f"{path} m/n must be integers")
    return str(row["port"]), int(row["m"]), int(row["n"])


def _spectrum_identity_array(
    value: Any,
    *,
    path: str,
) -> tuple[tuple[str, int, int], ...]:
    if not isinstance(value, list):
        raise HiddenAuditContractError(f"{path} must be an array")
    result = tuple(
        _spectrum_identity(item, path=f"{path}[{index}]")
        for index, item in enumerate(value)
    )
    if len(result) != len(set(result)):
        raise HiddenAuditContractError(f"{path} contains duplicate orders")
    if result != tuple(sorted(result, key=_spectrum_order_key)):
        raise HiddenAuditContractError(f"{path} is not canonically sorted")
    return result


def _spectrum_complex(value: Any, *, path: str) -> complex:
    row = exact_mapping(value, _SPECTRUM_COMPLEX_KEYS, path=path)
    return complex(
        finite_float(row["real"], path=f"{path}.real"),
        finite_float(row["imag"], path=f"{path}.imag"),
    )


def _same_finite_float(
    observed: Any,
    expected: float,
    *,
    path: str,
) -> bool:
    value = finite_float(observed, path=path)
    return math.isclose(
        value,
        expected,
        rel_tol=2.0e-15,
        abs_tol=1.0e-18,
    )


def recompute_full_propagating_spectrum_gate(
    *,
    actual: Any,
    limit: Any,
) -> bool:
    """Validate and independently recompute the dynamic full-spectrum gate."""

    if limit != _SPECTRUM_GATE_LIMIT:
        raise HiddenAuditContractError(
            "full-spectrum gate limit contract was modified"
        )
    row = exact_mapping(
        actual,
        _SPECTRUM_ACTUAL_KEYS,
        path="full_spectrum.actual",
    )
    if row["schema_version"] != FULL_SPECTRUM_GATE_SCHEMA:
        raise HiddenAuditContractError(
            "full-spectrum gate schema is unsupported"
        )
    if row["status"] != "completed":
        raise HiddenAuditContractError(
            "full-spectrum gate did not complete"
        )
    reference_orders = _spectrum_identity_array(
        row["reference_orders"],
        path="full_spectrum.actual.reference_orders",
    )
    candidate_orders = _spectrum_identity_array(
        row["candidate_orders"],
        path="full_spectrum.actual.candidate_orders",
    )
    missing_orders = _spectrum_identity_array(
        row["missing_candidate_orders"],
        path="full_spectrum.actual.missing_candidate_orders",
    )
    unexpected_orders = _spectrum_identity_array(
        row["unexpected_candidate_orders"],
        path="full_spectrum.actual.unexpected_candidate_orders",
    )
    reference_set = set(reference_orders)
    candidate_set = set(candidate_orders)
    expected_missing = tuple(
        sorted(reference_set - candidate_set, key=_spectrum_order_key)
    )
    expected_unexpected = tuple(
        sorted(candidate_set - reference_set, key=_spectrum_order_key)
    )
    if missing_orders != expected_missing:
        raise HiddenAuditContractError(
            "full-spectrum missing-order inventory is not recomputable"
        )
    if unexpected_orders != expected_unexpected:
        raise HiddenAuditContractError(
            "full-spectrum unexpected-order inventory is not recomputable"
        )

    common_orders = tuple(
        sorted(reference_set & candidate_set, key=_spectrum_order_key)
    )
    metadata_rows = row["metadata_comparisons"]
    if not isinstance(metadata_rows, list):
        raise HiddenAuditContractError(
            "full-spectrum metadata comparisons must be an array"
        )
    observed_metadata_identities: list[tuple[str, int, int]] = []
    metadata_passed: list[bool] = []
    for index, value in enumerate(metadata_rows):
        path = f"full_spectrum.actual.metadata_comparisons[{index}]"
        item = exact_mapping(
            value,
            _SPECTRUM_METADATA_COMPARISON_KEYS,
            path=path,
        )
        identity = _spectrum_identity(
            {name: item[name] for name in ("port", "m", "n")},
            path=path,
        )
        observed_metadata_identities.append(identity)
        metadata_values = {}
        for side in ("reference", "candidate"):
            metadata = exact_mapping(
                item[side],
                _SPECTRUM_METADATA_KEYS,
                path=f"{path}.{side}",
            )
            if (
                not isinstance(metadata["normalization_identity"], str)
                or not metadata["normalization_identity"].strip()
            ):
                raise HiddenAuditContractError(
                    f"{path}.{side}.normalization_identity must be nonempty"
                )
            metadata_values[side] = (
                _spectrum_complex(
                    metadata["kz"],
                    path=f"{path}.{side}.kz",
                ),
                _spectrum_complex(
                    metadata["admittance"],
                    path=f"{path}.{side}.admittance",
                ),
                metadata["normalization_identity"],
            )
        recomputed = metadata_values["reference"] == metadata_values["candidate"]
        if not isinstance(item["passed"], bool) or item["passed"] is not recomputed:
            raise HiddenAuditContractError(
                f"{path}.passed is not recomputable"
            )
        metadata_passed.append(recomputed)
    if tuple(observed_metadata_identities) != common_orders:
        raise HiddenAuditContractError(
            "full-spectrum metadata comparison inventory is incomplete"
        )

    value_rows = row["value_comparisons"]
    if not isinstance(value_rows, list):
        raise HiddenAuditContractError(
            "full-spectrum value comparisons must be an array"
        )
    observed_value_keys: list[tuple[tuple[str, int, int], str]] = []
    value_passed: list[bool] = []
    for index, value in enumerate(value_rows):
        path = f"full_spectrum.actual.value_comparisons[{index}]"
        item = exact_mapping(
            value,
            _SPECTRUM_VALUE_COMPARISON_KEYS,
            path=path,
        )
        identity = _spectrum_identity(
            {name: item[name] for name in ("port", "m", "n")},
            path=path,
        )
        quantity = item["quantity"]
        if quantity not in FULL_SPECTRUM_QUANTITIES:
            raise HiddenAuditContractError(
                f"{path}.quantity is unsupported"
            )
        observed_value_keys.append((identity, str(quantity)))
        uncertainty = finite_float(
            item["reference_uncertainty"],
            path=f"{path}.reference_uncertainty",
        )
        if uncertainty < 0.0:
            raise HiddenAuditContractError(
                f"{path}.reference_uncertainty must be nonnegative"
            )
        if quantity in {"total_power", "cross_polarized_power"}:
            reference_value = finite_float(
                item["reference_value"],
                path=f"{path}.reference_value",
            )
            candidate_value = finite_float(
                item["candidate_value"],
                path=f"{path}.candidate_value",
            )
            if reference_value < 0.0 or candidate_value < 0.0:
                raise HiddenAuditContractError(
                    f"{path} power values must be nonnegative"
                )
            expected_error = abs(candidate_value - reference_value)
            expected_tolerance = max(
                1.0e-9,
                5.0e-4 * abs(reference_value),
                2.0 * uncertainty,
            )
        else:
            reference_value = _spectrum_complex(
                item["reference_value"],
                path=f"{path}.reference_value",
            )
            candidate_value = _spectrum_complex(
                item["candidate_value"],
                path=f"{path}.candidate_value",
            )
            expected_error = abs(candidate_value - reference_value)
            expected_tolerance = max(
                1.0e-6,
                1.0e-3 * abs(reference_value),
                2.0 * uncertainty,
            )
        if not _same_finite_float(
            item["actual_error"],
            expected_error,
            path=f"{path}.actual_error",
        ):
            raise HiddenAuditContractError(
                f"{path}.actual_error is not recomputable"
            )
        if not _same_finite_float(
            item["tolerance"],
            expected_tolerance,
            path=f"{path}.tolerance",
        ):
            raise HiddenAuditContractError(
                f"{path}.tolerance is not recomputable"
            )
        recomputed = expected_error <= expected_tolerance
        if not isinstance(item["passed"], bool) or item["passed"] is not recomputed:
            raise HiddenAuditContractError(
                f"{path}.passed is not recomputable"
            )
        value_passed.append(recomputed)
    expected_value_keys = tuple(
        (identity, quantity)
        for identity in common_orders
        for quantity in FULL_SPECTRUM_QUANTITIES
    )
    if tuple(observed_value_keys) != expected_value_keys:
        raise HiddenAuditContractError(
            "full-spectrum value comparison inventory is incomplete"
        )
    for name, expected in (
        ("passed_value_count", sum(value_passed)),
        ("total_value_count", len(value_passed)),
    ):
        observed = row[name]
        if (
            isinstance(observed, bool)
            or not isinstance(observed, Integral)
            or int(observed) != expected
        ):
            raise HiddenAuditContractError(
                f"full-spectrum {name} is not recomputable"
            )
    return bool(reference_orders) and all(
        (
            not missing_orders,
            not unexpected_orders,
            all(metadata_passed),
            all(value_passed),
        )
    )


@dataclass(frozen=True, slots=True)
class HiddenAuditReport:
    """Terminal audit result.  A failed report cannot be reopened for tuning."""

    status: str
    passed: bool
    terminal: bool
    candidate_frozen_payload_sha256: str
    candidate_output_sha256: str
    reference_sealed_payload_sha256: str
    reference_campaign_binding_sha256: str
    items: tuple[AuditItem, ...]
    gates: tuple[AuditGate, ...]

    def __post_init__(self) -> None:
        if self.terminal is not True:
            raise HiddenAuditContractError(
                "a final hidden audit report must be terminal"
            )
        for name in (
            "candidate_frozen_payload_sha256",
            "candidate_output_sha256",
            "reference_sealed_payload_sha256",
            "reference_campaign_binding_sha256",
        ):
            require_sha256(getattr(self, name), path=name)
        expected_items = {
            "order_power": EXPECTED_POWER_OUTPUT_IDS,
            "order_amplitude": EXPECTED_AMPLITUDE_OUTPUT_IDS,
            "total": EXPECTED_TOTAL_OUTPUT_IDS,
            "field": EXPECTED_FIELD_OUTPUT_IDS,
        }
        for category, expected_ids in expected_items.items():
            observed_ids = [
                item.output_id
                for item in self.items
                if item.category == category
            ]
            if (
                len(observed_ids) != len(set(observed_ids))
                or set(observed_ids) != set(expected_ids)
            ):
                raise HiddenAuditContractError(
                    f"hidden audit {category} inventory is incomplete"
                )
        if any(item.category not in expected_items for item in self.items):
            raise HiddenAuditContractError(
                "hidden audit contains an unsupported item category"
            )
        observed_gate_ids = [gate.gate_id for gate in self.gates]
        if (
            len(observed_gate_ids) != len(set(observed_gate_ids))
            or set(observed_gate_ids) != set(EXPECTED_HARD_GATE_IDS)
        ):
            raise HiddenAuditContractError(
                "hidden audit hard-gate inventory is incomplete"
            )
        spectrum_gate = next(
            gate
            for gate in self.gates
            if gate.gate_id == "full_propagating_spectrum_audit"
        )
        spectrum_recomputed = recompute_full_propagating_spectrum_gate(
            actual=spectrum_gate.actual,
            limit=spectrum_gate.limit,
        )
        if spectrum_gate.passed is not spectrum_recomputed:
            raise HiddenAuditContractError(
                "full-spectrum gate passed flag is not recomputable"
            )
        recomputed = all(item.passed for item in self.items) and all(
            gate.passed for gate in self.gates
        )
        if recomputed != self.passed:
            raise HiddenAuditContractError(
                "audit passed flag disagrees with its items and gates"
            )
        expected_status = (
            "REFERENCE_BLIND_HP_ACCURACY_PASS"
            if self.passed
            else "BLIND_STOP_FALSE_POSITIVE"
        )
        if self.status != expected_status:
            raise HiddenAuditContractError(
                "audit status disagrees with recomputed pass state"
            )

    def counts_payload(self) -> dict[str, int]:
        by_category = {
            category: tuple(
                item for item in self.items if item.category == category
            )
            for category in (
                "order_power",
                "order_amplitude",
                "total",
                "field",
            )
        }
        return {
            "fixed_order_inventory": len(FIXED_ORDER_KEYS),
            "power_passed": sum(
                item.passed for item in by_category["order_power"]
            ),
            "power_total": len(by_category["order_power"]),
            "power_applicable": sum(
                item.applicable for item in by_category["order_power"]
            ),
            "amplitude_passed": sum(
                item.passed for item in by_category["order_amplitude"]
            ),
            "amplitude_total": len(by_category["order_amplitude"]),
            "total_passed": sum(item.passed for item in by_category["total"]),
            "total_total": len(by_category["total"]),
            "field_passed": sum(item.passed for item in by_category["field"]),
            "field_total": len(by_category["field"]),
            "hard_gate_passed": sum(gate.passed for gate in self.gates),
            "hard_gate_total": len(self.gates),
        }


__all__ = [
    "BLIND_FORMAL_TOTAL_NAMES",
    "CANDIDATE_BUNDLE_SCHEMA",
    "CANDIDATE_OUTPUT_SCHEMA",
    "FIXED_GOAL_IDS",
    "FIXED_M",
    "FIXED_N",
    "FIXED_ORDER_KEYS",
    "FIXED_PORTS",
    "FORMAL_FIELD_COMPLEX_NAMES",
    "FORMAL_FIELD_SCALAR_NAMES",
    "FORMAL_GOAL_IDS",
    "FORMAL_GOAL_INVENTORY_SHA256",
    "FORMAL_TOTAL_NAMES",
    "FULL_SPECTRUM_GATE_SCHEMA",
    "FULL_SPECTRUM_QUANTITIES",
    "ORDER_GOAL_IDS",
    "EXPECTED_AMPLITUDE_OUTPUT_IDS",
    "EXPECTED_FIELD_OUTPUT_IDS",
    "EXPECTED_HARD_GATE_IDS",
    "EXPECTED_POWER_OUTPUT_IDS",
    "EXPECTED_TOTAL_OUTPUT_IDS",
    "FREEZE_RECEIPT_SCHEMA",
    "HIDDEN_AUDIT_SCHEMA",
    "TWO_PATH_GATE_SCHEMA",
    "AuditGate",
    "AuditItem",
    "CandidateFreezeReceipt",
    "HiddenAuditContractError",
    "HiddenAuditReport",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "exact_mapping",
    "finite_float",
    "require_sha256",
    "require_source_sha",
    "recompute_full_propagating_spectrum_gate",
]
