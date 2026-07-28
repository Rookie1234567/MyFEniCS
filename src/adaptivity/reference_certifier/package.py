"""Hash-bound, atomically written Task035e hidden reference packages."""

from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .contracts import (
    ASSEMBLY_MODE,
    ELEMENT_FAMILY,
    INCIDENT_POLARIZATION,
    LINEAR_SOLVER,
    ComplexValue,
    fixed_order_inventory,
)
from .convergence import (
    CertificationGateSummary,
    CertificationPolicy,
    QUALIFIED,
    REFERENCE_CERTIFICATION_FAILED,
    REFERENCE_CERTIFICATION_INCOMPLETE,
    ReferenceCertification,
    ThreePointConvergence,
)


SEALED_REFERENCE_PACKAGE_SCHEMA = "task035e.sealed-hidden-reference-package.v1"
SEALED_REFERENCE_PACKAGE_KIND = "task035e_hidden_reference"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")

_TOP_KEYS = frozenset(
    {
        "schema_version",
        "package_kind",
        "fixed_order_contract",
        "runs",
        "certification",
        "campaign_binding_sha256",
        "seal",
    }
)
_FIXED_ORDER_KEYS = frozenset({"N", "n", "ports", "m", "inventory"})
_ORDER_IDENTITY_KEYS = frozenset({"port", "m", "n"})
_IDENTITY_KEYS = frozenset(
    {
        "geometry_sha256",
        "material_sha256",
        "incident_sha256",
        "dtn_definition_sha256",
        "postprocessing_sha256",
        "source_sha",
        "element_family",
        "degree",
        "assembly_mode",
        "linear_solver",
        "mpi_size",
        "incident_polarization",
    }
)
_RUN_GATE_KEYS = frozenset(
    {
        "completed",
        "full_explicit_true_residual",
        "energy_balance_error",
        "closure_volume_error",
        "official_postprocessing_passed",
        "swap_peak_bytes",
        "minimum_memory_headroom_fraction",
        "controlled_resource_stop",
        "failure_reason",
    }
)
_SCALAR_KEYS = frozenset({"name", "value", "category"})
_COMPLEX_KEYS = frozenset({"name", "value", "category"})
_COMPLEX_VALUE_KEYS = frozenset({"real", "imag"})
_DIFFRACTION_ORDER_KEYS = frozenset(
    {
        "port",
        "m",
        "n",
        "propagating",
        "kz",
        "admittance",
        "normalization_identity",
        "total_power",
        "co_polarized_amplitude",
        "cross_polarized_power",
        "cross_polarized_amplitude",
    }
)
_RUN_KEYS = frozenset(
    {
        "h_nm",
        "identity",
        "gate",
        "evidence_sha256",
        "scalar_observations",
        "complex_observations",
        "diffraction_orders",
    }
)
_POLICY_KEYS = frozenset(
    {
        "residual_limit",
        "energy_balance_limit",
        "closure_volume_limit",
        "minimum_h5_memory_headroom_fraction",
        "fine_difference_ratio_limit",
        "maximum_fit_condition_number",
        "maximum_fit_relative_residual",
        "maximum_complex_ratio_imaginary_fraction",
        "maximum_fitted_q",
        "explained_oscillatory_output_ids",
    }
)
_CERTIFICATION_GATE_KEYS = frozenset(
    {
        *(field.name for field in fields(CertificationGateSummary)),
        "passed",
    }
)
_STORED_VALUE_KEYS = frozenset({"kind", "value"})
_CONVERGENCE_KEYS = frozenset(field.name for field in fields(ThreePointConvergence))
_CERTIFICATION_KEYS = frozenset(
    {
        "status",
        "qualified",
        "reasons",
        "policy",
        "gates",
        "convergence",
    }
)
_SEAL_KEYS = frozenset({"algorithm", "sealed_payload_sha256"})


def _object_schema(
    properties: Mapping[str, Any],
    *,
    required: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required or properties),
        "properties": dict(properties),
    }


_NUMBER_OR_NULL = {"type": ["number", "null"]}
_STRING_OR_NULL = {"type": ["string", "null"]}
_COMPLEX_VALUE_SCHEMA = _object_schema(
    {
        "real": {"type": "number"},
        "imag": {"type": "number"},
    }
)
_STORED_VALUE_SCHEMA = _object_schema(
    {
        "kind": {"enum": ["real", "complex"]},
        "value": {
            "oneOf": [
                {"type": "number"},
                _COMPLEX_VALUE_SCHEMA,
            ]
        },
    }
)

# This published schema is intentionally strict.  Runtime validation below is
# independent of a third-party jsonschema package and checks the same closed
# object boundaries before verifying the seal.
SEALED_REFERENCE_PACKAGE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": (
        "https://myfenics.local/schema/task035e-sealed-hidden-reference-package-v1.json"
    ),
    **_object_schema(
        {
            "schema_version": {"const": SEALED_REFERENCE_PACKAGE_SCHEMA},
            "package_kind": {"const": SEALED_REFERENCE_PACKAGE_KIND},
            "fixed_order_contract": _object_schema(
                {
                    "N": {"const": 8},
                    "n": {"const": 0},
                    "ports": {
                        "const": ["top", "bottom"],
                    },
                    "m": {
                        "const": [0, -1, -2, -3, -4, -5, -6, -7],
                    },
                    "inventory": {
                        "type": "array",
                        "minItems": 16,
                        "maxItems": 16,
                        "items": _object_schema(
                            {
                                "port": {"enum": ["top", "bottom"]},
                                "m": {"type": "integer"},
                                "n": {"const": 0},
                            }
                        ),
                    },
                }
            ),
            "runs": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": _object_schema(
                    {
                        "h_nm": {"enum": [10.0, 7.5, 5.0]},
                        "identity": _object_schema(
                            {
                                key: (
                                    {"type": "integer"}
                                    if key in {"degree", "mpi_size"}
                                    else {"type": "string"}
                                )
                                for key in _IDENTITY_KEYS
                            }
                        ),
                        "gate": _object_schema(
                            {
                                "completed": {"type": "boolean"},
                                "full_explicit_true_residual": (_NUMBER_OR_NULL),
                                "energy_balance_error": _NUMBER_OR_NULL,
                                "closure_volume_error": _NUMBER_OR_NULL,
                                "official_postprocessing_passed": {"type": "boolean"},
                                "swap_peak_bytes": {
                                    "type": "integer",
                                    "minimum": 0,
                                },
                                "minimum_memory_headroom_fraction": (_NUMBER_OR_NULL),
                                "controlled_resource_stop": {"type": "boolean"},
                                "failure_reason": _STRING_OR_NULL,
                            }
                        ),
                        "evidence_sha256": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{64}$",
                        },
                        "scalar_observations": {
                            "type": "array",
                            "items": _object_schema(
                                {
                                    "name": {"type": "string"},
                                    "value": {"type": "number"},
                                    "category": {"type": "string"},
                                }
                            ),
                        },
                        "complex_observations": {
                            "type": "array",
                            "items": _object_schema(
                                {
                                    "name": {"type": "string"},
                                    "value": _COMPLEX_VALUE_SCHEMA,
                                    "category": {"type": "string"},
                                }
                            ),
                        },
                        "diffraction_orders": {
                            "type": "array",
                            "items": _object_schema(
                                {
                                    "port": {"type": "string"},
                                    "m": {"type": "integer"},
                                    "n": {"type": "integer"},
                                    "propagating": {"type": "boolean"},
                                    "kz": _COMPLEX_VALUE_SCHEMA,
                                    "admittance": _COMPLEX_VALUE_SCHEMA,
                                    "normalization_identity": {"type": "string"},
                                    "total_power": _NUMBER_OR_NULL,
                                    "co_polarized_amplitude": (_COMPLEX_VALUE_SCHEMA),
                                    "cross_polarized_power": (_NUMBER_OR_NULL),
                                    "cross_polarized_amplitude": (
                                        _COMPLEX_VALUE_SCHEMA
                                    ),
                                }
                            ),
                        },
                    }
                ),
            },
            "certification": _object_schema(
                {
                    "status": {"type": "string"},
                    "qualified": {"type": "boolean"},
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "policy": _object_schema(
                        {
                            key: (
                                {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                                if key == "explained_oscillatory_output_ids"
                                else {"type": "number"}
                            )
                            for key in _POLICY_KEYS
                        }
                    ),
                    "gates": _object_schema(
                        {key: {"type": "boolean"} for key in _CERTIFICATION_GATE_KEYS}
                    ),
                    "convergence": {
                        "type": "array",
                        "items": _object_schema(
                            {
                                "output_id": {"type": "string"},
                                "category": {"type": "string"},
                                "value_kind": {"enum": ["real", "complex"]},
                                "h10_value": _STORED_VALUE_SCHEMA,
                                "h7p5_value": _STORED_VALUE_SCHEMA,
                                "h5_value": _STORED_VALUE_SCHEMA,
                                "d_10_7p5": {"type": "number"},
                                "d_7p5_5": {"type": "number"},
                                "difference_ratio_fine_over_coarse": (_NUMBER_OR_NULL),
                                "monotonic": {"type": "boolean"},
                                "sign_oscillation": {"type": "boolean"},
                                "fine_difference_significantly_smaller": {
                                    "type": "boolean"
                                },
                                "fit_stable": {"type": "boolean"},
                                "fit_reason": {"type": "string"},
                                "fitted_q": _NUMBER_OR_NULL,
                                "fitted_q_positive": {"type": "boolean"},
                                "fit_condition_number": _NUMBER_OR_NULL,
                                "fit_relative_residual": _NUMBER_OR_NULL,
                                "reference_center": _STORED_VALUE_SCHEMA,
                                "extrapolated_center": {
                                    "oneOf": [
                                        _STORED_VALUE_SCHEMA,
                                        {"type": "null"},
                                    ]
                                },
                                "h5_to_extrapolated_center": (_NUMBER_OR_NULL),
                                "reference_uncertainty": {"type": "number"},
                                "trend": {"type": "string"},
                            }
                        ),
                    },
                }
            ),
            "campaign_binding_sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "seal": _object_schema(
                {
                    "algorithm": {"const": "sha256"},
                    "sealed_payload_sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                }
            ),
        }
    ),
}


class SealedReferencePackageError(ValueError):
    """Raised when a hidden package fails schema or hash verification."""


@dataclass(frozen=True, slots=True)
class SealedPackageReceipt:
    """Non-secret write receipt; it contains no reference values."""

    path: Path
    sealed_payload_sha256: str
    campaign_binding_sha256: str
    byte_count: int
    qualified: bool
    status: str


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _complex_payload(value: ComplexValue) -> dict[str, float]:
    return {"real": value.real, "imag": value.imag}


def _identity_payload(identity: Any) -> dict[str, Any]:
    return {
        "geometry_sha256": identity.geometry_sha256,
        "material_sha256": identity.material_sha256,
        "incident_sha256": identity.incident_sha256,
        "dtn_definition_sha256": identity.dtn_definition_sha256,
        "postprocessing_sha256": identity.postprocessing_sha256,
        "source_sha": identity.source_sha,
        "element_family": identity.element_family,
        "degree": identity.degree,
        "assembly_mode": identity.assembly_mode,
        "linear_solver": identity.linear_solver,
        "mpi_size": identity.mpi_size,
        "incident_polarization": identity.incident_polarization,
    }


def _run_payload(run: Any) -> dict[str, Any]:
    gate = run.gate
    return {
        "h_nm": run.h_nm,
        "identity": _identity_payload(run.identity),
        "gate": {
            "completed": gate.completed,
            "full_explicit_true_residual": (gate.full_explicit_true_residual),
            "energy_balance_error": gate.energy_balance_error,
            "closure_volume_error": gate.closure_volume_error,
            "official_postprocessing_passed": (gate.official_postprocessing_passed),
            "swap_peak_bytes": gate.swap_peak_bytes,
            "minimum_memory_headroom_fraction": (gate.minimum_memory_headroom_fraction),
            "controlled_resource_stop": gate.controlled_resource_stop,
            "failure_reason": gate.failure_reason,
        },
        "evidence_sha256": run.evidence_sha256,
        "scalar_observations": [
            {
                "name": row.name,
                "value": row.value,
                "category": row.category,
            }
            for row in run.scalar_observations
        ],
        "complex_observations": [
            {
                "name": row.name,
                "value": _complex_payload(row.value),
                "category": row.category,
            }
            for row in run.complex_observations
        ],
        "diffraction_orders": [
            {
                "port": row.port,
                "m": row.m,
                "n": row.n,
                "propagating": row.propagating,
                "kz": _complex_payload(row.kz),
                "admittance": _complex_payload(row.admittance),
                "normalization_identity": row.normalization_identity,
                "total_power": row.total_power,
                "co_polarized_amplitude": _complex_payload(row.co_polarized_amplitude),
                "cross_polarized_power": row.cross_polarized_power,
                "cross_polarized_amplitude": _complex_payload(
                    row.cross_polarized_amplitude
                ),
            }
            for row in sorted(
                run.diffraction_orders,
                key=lambda value: (
                    0 if value.port == "top" else 1,
                    -value.m,
                    value.n,
                ),
            )
        ],
    }


def _stored_value_payload(
    value: float | ComplexValue,
) -> dict[str, Any]:
    if isinstance(value, ComplexValue):
        return {
            "kind": "complex",
            "value": _complex_payload(value),
        }
    return {"kind": "real", "value": float(value)}


def _convergence_payload(row: ThreePointConvergence) -> dict[str, Any]:
    return {
        "output_id": row.output_id,
        "category": row.category,
        "value_kind": row.value_kind,
        "h10_value": _stored_value_payload(row.h10_value),
        "h7p5_value": _stored_value_payload(row.h7p5_value),
        "h5_value": _stored_value_payload(row.h5_value),
        "d_10_7p5": row.d_10_7p5,
        "d_7p5_5": row.d_7p5_5,
        "difference_ratio_fine_over_coarse": (row.difference_ratio_fine_over_coarse),
        "monotonic": row.monotonic,
        "sign_oscillation": row.sign_oscillation,
        "fine_difference_significantly_smaller": (
            row.fine_difference_significantly_smaller
        ),
        "fit_stable": row.fit_stable,
        "fit_reason": row.fit_reason,
        "fitted_q": row.fitted_q,
        "fitted_q_positive": row.fitted_q_positive,
        "fit_condition_number": row.fit_condition_number,
        "fit_relative_residual": row.fit_relative_residual,
        "reference_center": _stored_value_payload(row.reference_center),
        "extrapolated_center": (
            _stored_value_payload(row.extrapolated_center)
            if row.extrapolated_center is not None
            else None
        ),
        "h5_to_extrapolated_center": (row.h5_to_extrapolated_center),
        "reference_uncertainty": row.reference_uncertainty,
        "trend": row.trend,
    }


def _policy_payload(policy: CertificationPolicy) -> dict[str, Any]:
    return {
        "residual_limit": policy.residual_limit,
        "energy_balance_limit": policy.energy_balance_limit,
        "closure_volume_limit": policy.closure_volume_limit,
        "minimum_h5_memory_headroom_fraction": (
            policy.minimum_h5_memory_headroom_fraction
        ),
        "fine_difference_ratio_limit": (policy.fine_difference_ratio_limit),
        "maximum_fit_condition_number": (policy.maximum_fit_condition_number),
        "maximum_fit_relative_residual": (policy.maximum_fit_relative_residual),
        "maximum_complex_ratio_imaginary_fraction": (
            policy.maximum_complex_ratio_imaginary_fraction
        ),
        "maximum_fitted_q": policy.maximum_fitted_q,
        "explained_oscillatory_output_ids": list(
            policy.explained_oscillatory_output_ids
        ),
    }


def _gate_payload(gates: CertificationGateSummary) -> dict[str, bool]:
    payload = {
        field.name: bool(getattr(gates, field.name))
        for field in fields(CertificationGateSummary)
    }
    payload["passed"] = gates.passed
    return payload


def _fixed_order_payload() -> dict[str, Any]:
    inventory = fixed_order_inventory()
    return {
        "N": 8,
        "n": 0,
        "ports": ["top", "bottom"],
        "m": [0, -1, -2, -3, -4, -5, -6, -7],
        "inventory": [{"port": port, "m": m, "n": n} for port, m, n in inventory],
    }


def _campaign_binding_payload(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": [
            {
                "h_nm": run["h_nm"],
                "identity": run["identity"],
                "evidence_sha256": run["evidence_sha256"],
            }
            for run in runs
        ]
    }


def build_sealed_reference_package(
    certification: ReferenceCertification,
    *,
    require_qualified: bool = True,
) -> dict[str, Any]:
    """Build and self-verify a sealed evaluator package in memory."""

    if not isinstance(certification, ReferenceCertification):
        raise TypeError("certification must use ReferenceCertification")
    if require_qualified and not certification.qualified:
        raise SealedReferencePackageError(
            "refusing to seal an unqualified hidden reference package"
        )
    runs = [_run_payload(run) for run in certification.campaign.runs]
    campaign_binding_sha256 = _sha256_payload(_campaign_binding_payload(runs))
    payload: dict[str, Any] = {
        "schema_version": SEALED_REFERENCE_PACKAGE_SCHEMA,
        "package_kind": SEALED_REFERENCE_PACKAGE_KIND,
        "fixed_order_contract": _fixed_order_payload(),
        "runs": runs,
        "certification": {
            "status": certification.status,
            "qualified": certification.qualified,
            "reasons": list(certification.reasons),
            "policy": _policy_payload(certification.policy),
            "gates": _gate_payload(certification.gates),
            "convergence": [
                _convergence_payload(row) for row in certification.convergence
            ],
        },
        "campaign_binding_sha256": campaign_binding_sha256,
    }
    sealed_payload_sha256 = _sha256_payload(payload)
    package = {
        **payload,
        "seal": {
            "algorithm": "sha256",
            "sealed_payload_sha256": sealed_payload_sha256,
        },
    }
    validate_sealed_reference_package(package)
    return package


def _mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SealedReferencePackageError(f"{path} must be an object")
    return value


def _exact_keys(
    value: Any,
    expected: frozenset[str],
    *,
    path: str,
) -> Mapping[str, Any]:
    mapping = _mapping(value, path=path)
    observed = set(mapping)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise SealedReferencePackageError(
            f"{path} keys differ; missing={missing}, extra={extra}"
        )
    return mapping


def _list(value: Any, *, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SealedReferencePackageError(f"{path} must be an array")
    return value


def _finite_number_or_none(value: Any, *, path: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SealedReferencePackageError(f"{path} must be a finite number or null")
    if not math.isfinite(float(value)):
        raise SealedReferencePackageError(f"{path} must be finite")


def _validate_complex(value: Any, *, path: str) -> None:
    row = _exact_keys(value, _COMPLEX_VALUE_KEYS, path=path)
    _finite_number_or_none(row["real"], path=f"{path}.real")
    _finite_number_or_none(row["imag"], path=f"{path}.imag")
    if row["real"] is None or row["imag"] is None:
        raise SealedReferencePackageError(f"{path} components cannot be null")


def _validate_stored_value(value: Any, *, path: str) -> None:
    row = _exact_keys(value, _STORED_VALUE_KEYS, path=path)
    kind = row["kind"]
    if kind == "real":
        _finite_number_or_none(row["value"], path=f"{path}.value")
        if row["value"] is None:
            raise SealedReferencePackageError(f"{path}.value cannot be null")
    elif kind == "complex":
        _validate_complex(row["value"], path=f"{path}.value")
    else:
        raise SealedReferencePackageError(f"{path}.kind must be real or complex")


def _validate_identity(value: Any, *, path: str) -> None:
    row = _exact_keys(value, _IDENTITY_KEYS, path=path)
    for key in (
        "geometry_sha256",
        "material_sha256",
        "incident_sha256",
        "dtn_definition_sha256",
        "postprocessing_sha256",
    ):
        if not isinstance(row[key], str) or _SHA256_RE.fullmatch(row[key]) is None:
            raise SealedReferencePackageError(f"{path}.{key} is not SHA-256")
    if (
        not isinstance(row["source_sha"], str)
        or _SOURCE_SHA_RE.fullmatch(row["source_sha"]) is None
    ):
        raise SealedReferencePackageError(f"{path}.source_sha is invalid")
    for key in (
        "element_family",
        "assembly_mode",
        "linear_solver",
        "incident_polarization",
    ):
        if not isinstance(row[key], str):
            raise SealedReferencePackageError(f"{path}.{key} must be a string")
    for key in ("degree", "mpi_size"):
        if isinstance(row[key], bool) or not isinstance(row[key], int):
            raise SealedReferencePackageError(f"{path}.{key} must be an integer")
    expected_constants = {
        "element_family": ELEMENT_FAMILY,
        "degree": 6,
        "assembly_mode": ASSEMBLY_MODE,
        "linear_solver": LINEAR_SOLVER,
        "mpi_size": 8,
        "incident_polarization": INCIDENT_POLARIZATION,
    }
    for key, expected in expected_constants.items():
        if row[key] != expected:
            raise SealedReferencePackageError(f"{path}.{key} must equal {expected!r}")


def _validate_run(value: Any, *, path: str) -> None:
    row = _exact_keys(value, _RUN_KEYS, path=path)
    _finite_number_or_none(row["h_nm"], path=f"{path}.h_nm")
    _validate_identity(row["identity"], path=f"{path}.identity")
    gate = _exact_keys(row["gate"], _RUN_GATE_KEYS, path=f"{path}.gate")
    for key in (
        "completed",
        "official_postprocessing_passed",
        "controlled_resource_stop",
    ):
        if not isinstance(gate[key], bool):
            raise SealedReferencePackageError(f"{path}.gate.{key} must be boolean")
    for key in (
        "full_explicit_true_residual",
        "energy_balance_error",
        "closure_volume_error",
        "minimum_memory_headroom_fraction",
    ):
        _finite_number_or_none(
            gate[key],
            path=f"{path}.gate.{key}",
        )
    if (
        isinstance(gate["swap_peak_bytes"], bool)
        or not isinstance(gate["swap_peak_bytes"], int)
        or gate["swap_peak_bytes"] < 0
    ):
        raise SealedReferencePackageError(
            f"{path}.gate.swap_peak_bytes must be nonnegative integer"
        )
    if gate["failure_reason"] is not None and not isinstance(
        gate["failure_reason"], str
    ):
        raise SealedReferencePackageError(
            f"{path}.gate.failure_reason must be string or null"
        )
    evidence_sha256 = row["evidence_sha256"]
    if (
        not isinstance(evidence_sha256, str)
        or _SHA256_RE.fullmatch(evidence_sha256) is None
    ):
        raise SealedReferencePackageError(f"{path}.evidence_sha256 is invalid")
    for index, scalar in enumerate(
        _list(
            row["scalar_observations"],
            path=f"{path}.scalar_observations",
        )
    ):
        scalar_path = f"{path}.scalar_observations[{index}]"
        scalar_row = _exact_keys(
            scalar,
            _SCALAR_KEYS,
            path=scalar_path,
        )
        if not isinstance(scalar_row["name"], str) or not isinstance(
            scalar_row["category"], str
        ):
            raise SealedReferencePackageError(
                f"{scalar_path} name/category must be strings"
            )
        _finite_number_or_none(
            scalar_row["value"],
            path=f"{scalar_path}.value",
        )
    for index, observation in enumerate(
        _list(
            row["complex_observations"],
            path=f"{path}.complex_observations",
        )
    ):
        observation_path = f"{path}.complex_observations[{index}]"
        observation_row = _exact_keys(
            observation,
            _COMPLEX_KEYS,
            path=observation_path,
        )
        if not isinstance(observation_row["name"], str) or not isinstance(
            observation_row["category"], str
        ):
            raise SealedReferencePackageError(
                f"{observation_path} name/category must be strings"
            )
        _validate_complex(
            observation_row["value"],
            path=f"{observation_path}.value",
        )
    for index, order in enumerate(
        _list(
            row["diffraction_orders"],
            path=f"{path}.diffraction_orders",
        )
    ):
        order_path = f"{path}.diffraction_orders[{index}]"
        order_row = _exact_keys(
            order,
            _DIFFRACTION_ORDER_KEYS,
            path=order_path,
        )
        if not isinstance(order_row["port"], str):
            raise SealedReferencePackageError(f"{order_path}.port must be a string")
        for key in ("m", "n"):
            if isinstance(order_row[key], bool) or not isinstance(order_row[key], int):
                raise SealedReferencePackageError(
                    f"{order_path}.{key} must be an integer"
                )
        if not isinstance(order_row["propagating"], bool):
            raise SealedReferencePackageError(
                f"{order_path}.propagating must be boolean"
            )
        if not isinstance(order_row["normalization_identity"], str):
            raise SealedReferencePackageError(
                f"{order_path}.normalization_identity must be string"
            )
        for key in (
            "kz",
            "admittance",
            "co_polarized_amplitude",
            "cross_polarized_amplitude",
        ):
            _validate_complex(
                order_row[key],
                path=f"{order_path}.{key}",
            )
        for key in ("total_power", "cross_polarized_power"):
            _finite_number_or_none(
                order_row[key],
                path=f"{order_path}.{key}",
            )


def _validate_certification(value: Any, *, path: str) -> None:
    row = _exact_keys(value, _CERTIFICATION_KEYS, path=path)
    allowed_status = {
        QUALIFIED,
        REFERENCE_CERTIFICATION_FAILED,
        REFERENCE_CERTIFICATION_INCOMPLETE,
    }
    if row["status"] not in allowed_status:
        raise SealedReferencePackageError(f"{path}.status is unsupported")
    if not isinstance(row["qualified"], bool):
        raise SealedReferencePackageError(f"{path}.qualified must be boolean")
    if row["qualified"] != (row["status"] == QUALIFIED):
        raise SealedReferencePackageError(f"{path}.qualified disagrees with status")
    if not all(
        isinstance(reason, str)
        for reason in _list(row["reasons"], path=f"{path}.reasons")
    ):
        raise SealedReferencePackageError(f"{path}.reasons must contain strings")
    policy = _exact_keys(row["policy"], _POLICY_KEYS, path=f"{path}.policy")
    for key in _POLICY_KEYS - {"explained_oscillatory_output_ids"}:
        _finite_number_or_none(
            policy[key],
            path=f"{path}.policy.{key}",
        )
    if not all(
        isinstance(output_id, str)
        for output_id in _list(
            policy["explained_oscillatory_output_ids"],
            path=f"{path}.policy.explained_oscillatory_output_ids",
        )
    ):
        raise SealedReferencePackageError(
            f"{path}.policy explained output IDs must be strings"
        )
    gates = _exact_keys(
        row["gates"],
        _CERTIFICATION_GATE_KEYS,
        path=f"{path}.gates",
    )
    if not all(isinstance(value, bool) for value in gates.values()):
        raise SealedReferencePackageError(f"{path}.gates must contain booleans")
    if row["qualified"] != gates["passed"]:
        raise SealedReferencePackageError(
            f"{path}.gates.passed disagrees with qualified"
        )
    seen_output_ids: set[str] = set()
    for index, convergence in enumerate(
        _list(row["convergence"], path=f"{path}.convergence")
    ):
        convergence_path = f"{path}.convergence[{index}]"
        convergence_row = _exact_keys(
            convergence,
            _CONVERGENCE_KEYS,
            path=convergence_path,
        )
        output_id = convergence_row["output_id"]
        if not isinstance(output_id, str) or not output_id:
            raise SealedReferencePackageError(
                f"{convergence_path}.output_id must be nonempty string"
            )
        if output_id in seen_output_ids:
            raise SealedReferencePackageError(
                f"{convergence_path}.output_id is duplicated"
            )
        seen_output_ids.add(output_id)
        for key in (
            "category",
            "value_kind",
            "fit_reason",
            "trend",
        ):
            if not isinstance(convergence_row[key], str):
                raise SealedReferencePackageError(
                    f"{convergence_path}.{key} must be string"
                )
        for key in (
            "monotonic",
            "sign_oscillation",
            "fine_difference_significantly_smaller",
            "fit_stable",
            "fitted_q_positive",
        ):
            if not isinstance(convergence_row[key], bool):
                raise SealedReferencePackageError(
                    f"{convergence_path}.{key} must be boolean"
                )
        for key in (
            "d_10_7p5",
            "d_7p5_5",
            "difference_ratio_fine_over_coarse",
            "fitted_q",
            "fit_condition_number",
            "fit_relative_residual",
            "h5_to_extrapolated_center",
            "reference_uncertainty",
        ):
            _finite_number_or_none(
                convergence_row[key],
                path=f"{convergence_path}.{key}",
            )
        for key in (
            "h10_value",
            "h7p5_value",
            "h5_value",
            "reference_center",
        ):
            _validate_stored_value(
                convergence_row[key],
                path=f"{convergence_path}.{key}",
            )
        if convergence_row["extrapolated_center"] is not None:
            _validate_stored_value(
                convergence_row["extrapolated_center"],
                path=f"{convergence_path}.extrapolated_center",
            )


def validate_sealed_reference_package(
    package: Mapping[str, Any],
) -> None:
    """Fail closed on any schema, binding, or seal mismatch."""

    row = _exact_keys(package, _TOP_KEYS, path="$")
    if row["schema_version"] != SEALED_REFERENCE_PACKAGE_SCHEMA:
        raise SealedReferencePackageError("unsupported schema_version")
    if row["package_kind"] != SEALED_REFERENCE_PACKAGE_KIND:
        raise SealedReferencePackageError("unsupported package_kind")
    fixed = _exact_keys(
        row["fixed_order_contract"],
        _FIXED_ORDER_KEYS,
        path="$.fixed_order_contract",
    )
    if (
        fixed["N"] != 8
        or fixed["n"] != 0
        or fixed["ports"] != ["top", "bottom"]
        or fixed["m"] != [0, -1, -2, -3, -4, -5, -6, -7]
    ):
        raise SealedReferencePackageError("fixed N=8 order contract was modified")
    inventory_rows = _list(
        fixed["inventory"],
        path="$.fixed_order_contract.inventory",
    )
    observed_inventory = []
    for index, identity in enumerate(inventory_rows):
        identity_row = _exact_keys(
            identity,
            _ORDER_IDENTITY_KEYS,
            path=f"$.fixed_order_contract.inventory[{index}]",
        )
        observed_inventory.append(
            (
                identity_row["port"],
                identity_row["m"],
                identity_row["n"],
            )
        )
    if tuple(observed_inventory) != fixed_order_inventory():
        raise SealedReferencePackageError("fixed order inventory is not canonical")
    runs = _list(row["runs"], path="$.runs")
    if len(runs) != 3:
        raise SealedReferencePackageError("$.runs must contain three points")
    for index, run in enumerate(runs):
        _validate_run(run, path=f"$.runs[{index}]")
    if [run["h_nm"] for run in runs] != [10.0, 7.5, 5.0]:
        raise SealedReferencePackageError("$.runs must be ordered h10, h7.5, h5")
    _validate_certification(
        row["certification"],
        path="$.certification",
    )
    binding_sha = row["campaign_binding_sha256"]
    if not isinstance(binding_sha, str) or _SHA256_RE.fullmatch(binding_sha) is None:
        raise SealedReferencePackageError("campaign_binding_sha256 is invalid")
    expected_binding_sha = _sha256_payload(_campaign_binding_payload(runs))
    if binding_sha != expected_binding_sha:
        raise SealedReferencePackageError("campaign binding SHA-256 mismatch")
    seal = _exact_keys(row["seal"], _SEAL_KEYS, path="$.seal")
    if seal["algorithm"] != "sha256":
        raise SealedReferencePackageError("$.seal.algorithm must be sha256")
    seal_sha = seal["sealed_payload_sha256"]
    if not isinstance(seal_sha, str) or _SHA256_RE.fullmatch(seal_sha) is None:
        raise SealedReferencePackageError("sealed_payload_sha256 is invalid")
    unsigned_payload = dict(row)
    unsigned_payload.pop("seal")
    expected_seal_sha = _sha256_payload(unsigned_payload)
    if seal_sha != expected_seal_sha:
        raise SealedReferencePackageError("sealed payload SHA-256 mismatch")


def write_sealed_reference_package(
    path: Path | str,
    certification: ReferenceCertification,
    *,
    require_qualified: bool = True,
    overwrite: bool = False,
) -> SealedPackageReceipt:
    """Atomically write a mode-0600 package and return a non-secret receipt."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite sealed package: {destination}")
    package = build_sealed_reference_package(
        certification,
        require_qualified=require_qualified,
    )
    encoded = (
        json.dumps(
            package,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists() and not overwrite:
            raise FileExistsError(
                f"refusing to overwrite sealed package: {destination}"
            )
        os.replace(temporary_path, destination)
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    verified = read_sealed_reference_package(destination)
    seal = verified["seal"]
    return SealedPackageReceipt(
        path=destination,
        sealed_payload_sha256=seal["sealed_payload_sha256"],
        campaign_binding_sha256=verified["campaign_binding_sha256"],
        byte_count=len(encoded),
        qualified=verified["certification"]["qualified"],
        status=verified["certification"]["status"],
    )


def read_sealed_reference_package(path: Path | str) -> dict[str, Any]:
    """Load a package for the evaluator/auditor and verify it before use."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SealedReferencePackageError(
            f"cannot read sealed reference package: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise SealedReferencePackageError(
            "sealed reference package root must be an object"
        )
    validate_sealed_reference_package(payload)
    return payload


__all__ = [
    "SEALED_REFERENCE_PACKAGE_JSON_SCHEMA",
    "SEALED_REFERENCE_PACKAGE_KIND",
    "SEALED_REFERENCE_PACKAGE_SCHEMA",
    "SealedPackageReceipt",
    "SealedReferencePackageError",
    "build_sealed_reference_package",
    "read_sealed_reference_package",
    "validate_sealed_reference_package",
    "write_sealed_reference_package",
]
