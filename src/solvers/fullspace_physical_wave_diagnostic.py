"""Small, pure-numpy pieces for the Review V15 wave-subspace diagnostic.

This module deliberately stops at the F1 algebra/oracle boundary.  It does not
construct a mesh, a form, a PETSc object, a Krylov solver, or a physical field.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

import numpy as np


V15_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
V15_PROFILE = "p6/h10/13.5nm/s/grazing1/phi0"
V15_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
V15_PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
V15_MODE_MANIFEST_SHA256 = (
    "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
)
V15_SELECTOR_SCHEMA = "task038.v15.floquet-selection.v1"
V15_SELECTOR_POLICY = (
    "eligible_class_filter__normalized_abs_beta_ascending__mode_index_tiebreak"
)
V15_WAVELENGTH_NM = 13.5
V15_SELECTOR_PAYLOAD_SHA256 = (
    "7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3"
)
V15_SELECTED_MODE_INDICES = (
    38,
    39,
    72,
    73,
    76,
    77,
    32,
    33,
    36,
    37,
    40,
    41,
    0,
    1,
    42,
    43,
    46,
    47,
    2,
    3,
    6,
    7,
    74,
    75,
    34,
    35,
    66,
    67,
    70,
    71,
    26,
    27,
)


def _complex_value(value: Any, name: str) -> complex:
    if isinstance(value, Mapping):
        if set(value) != {"real", "imag"}:
            raise ValueError(f"{name} must have exactly real/imag keys")
        result = complex(value["real"], value["imag"])
    else:
        try:
            result = complex(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} is not complex-valued") from exc
    if not np.isfinite(result.real) or not np.isfinite(result.imag):
        raise ValueError(f"{name} is non-finite")
    return result


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not a number") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} is non-finite")
    return result


def _mode_facts(rows: Sequence[Mapping[str, Any]], wavelength_nm: float) -> list[dict[str, Any]]:
    wavelength = _finite_float(wavelength_nm, "wavelength_nm")
    if wavelength <= 0:
        raise ValueError("wavelength_nm must be positive")
    k0_value = 2.0 * np.pi / wavelength
    if k0_value <= 0:
        raise ValueError("k0 must be positive")
    facts: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        try:
            index = row["mode_index"]
            classification = row["classification"]
            side = row["side"]
            polarization = row["polarization"]
            beta = _complex_value(row["beta"], "beta")
            refractive_index = _complex_value(row["refractive_index"], "refractive_index")
        except KeyError as exc:
            raise ValueError(f"mode row is missing {exc.args[0]}") from exc
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("mode_index must be a non-negative integer")
        if index in seen:
            raise ValueError(f"duplicate mode_index {index}")
        if classification not in {"propagating", "near-cutoff", "evanescent"}:
            raise ValueError("unsupported mode classification")
        if side not in {"top", "bottom"} or polarization not in {"s", "p"}:
            raise ValueError("unsupported mode side or polarization")
        denominator = abs(refractive_index) * k0_value
        if denominator <= 0:
            raise ValueError("mode eta denominator must be positive")
        eta = abs(beta) / denominator
        if not np.isfinite(eta):
            raise ValueError("mode eta is non-finite")
        seen.add(index)
        facts.append(
            {
                "mode_index": index,
                "classification": classification,
                "side": side,
                "polarization": polarization,
                "eta": float(eta),
            }
        )
    return facts


def _selector_payload(
    selected_indices: Sequence[int], source_manifest_sha256: str
) -> tuple[dict, str]:
    payload = {
        "schema": V15_SELECTOR_SCHEMA,
        "source_mode_manifest_sha256": source_manifest_sha256,
        "policy": V15_SELECTOR_POLICY,
        "eligible_classifications": ["near-cutoff", "propagating"],
        "selected_mode_indices": list(selected_indices),
        "rank": len(selected_indices),
    }
    payload_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return payload, hashlib.sha256(payload_bytes).hexdigest()


def select_v15_modes(
    rows: Sequence[Mapping[str, Any]],
    *,
    wavelength_nm: float = V15_WAVELENGTH_NM,
    mode_manifest_sha256: str,
) -> dict[str, Any]:
    """Recompute the fixed V15 eligible-mode ordering and selection.

    The ordering, eligibility, counts, selected indices, and canonical
    authority payload are recomputed from the supplied rows.  The payload is
    serialized with the frozen V15 JSON rules before its authority digest is
    checked.
    """

    if len(rows) != 80:
        raise ValueError("the exact V15 profile requires 80 mode rows")
    if mode_manifest_sha256 != V15_MODE_MANIFEST_SHA256:
        raise ValueError("unexpected mode manifest SHA256")
    facts = _mode_facts(rows, wavelength_nm)
    if {fact["mode_index"] for fact in facts} != set(range(80)):
        raise ValueError("exact profile mode indices must be 0..79")
    eligible = [
        fact for fact in facts if fact["classification"] in {"propagating", "near-cutoff"}
    ]
    ordered = sorted(eligible, key=lambda fact: (fact["eta"], fact["mode_index"]))
    if len(ordered) < len(V15_SELECTED_MODE_INDICES):
        raise ValueError("fewer than 32 eligible modes")
    selected = ordered[: len(V15_SELECTED_MODE_INDICES)]
    selected_indices = tuple(fact["mode_index"] for fact in selected)
    authority_match = selected_indices == V15_SELECTED_MODE_INDICES
    if not authority_match:
        raise ValueError("V15 selector indices do not match the frozen authority")
    selector_payload, selector_payload_sha256 = _selector_payload(
        selected_indices, mode_manifest_sha256
    )
    if selector_payload_sha256 != V15_SELECTOR_PAYLOAD_SHA256:
        raise ValueError("V15 selector payload SHA does not match the frozen authority")
    selected_facts = [dict(fact) for fact in selected]
    return {
        "schema": V15_SELECTOR_SCHEMA,
        "mode_manifest_sha256": mode_manifest_sha256,
        "wavelength_nm": float(wavelength_nm),
        "k0_nm_inv": float(2.0 * np.pi / float(wavelength_nm)),
        "mode_count": len(facts),
        "eligible_count": len(eligible),
        "eligible_order": [fact["mode_index"] for fact in ordered],
        "selected_mode_indices": list(selected_indices),
        "selected_rank": len(selected),
        "selected_classification_counts": dict(
            Counter(fact["classification"] for fact in selected)
        ),
        "selected_side_counts": dict(Counter(fact["side"] for fact in selected)),
        "selected_polarization_counts": dict(Counter(fact["polarization"] for fact in selected)),
        "selector_rule": V15_SELECTOR_POLICY,
        "selector_payload": selector_payload,
        "selector_payload_sha256": selector_payload_sha256,
        "authority_match": authority_match,
        "selected_facts": selected_facts,
        "mode_facts": facts,
    }


def hermitian_dot(left: Any, right: Any, comm: Any = None) -> complex:
    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    if left_array.shape != right_array.shape:
        raise ValueError("inner-product operands have different shapes")
    if not np.all(np.isfinite(left_array)) or not np.all(np.isfinite(right_array)):
        raise ValueError("inner-product operand is non-finite")
    value = complex(np.vdot(left_array, right_array))
    if comm is not None:
        value = complex(comm.allreduce(value))
    return value


def global_norm(vector: Any, comm: Any = None) -> float:
    value = hermitian_dot(vector, vector, comm)
    if value.real < 0 or abs(value.imag) > 1e-10 * max(1.0, abs(value.real)):
        raise ValueError("global norm is not a finite real value")
    result = float(np.sqrt(value.real))
    if not np.isfinite(result):
        raise ValueError("global norm is non-finite")
    return result


def relative_error(actual: Any, expected: Any, comm: Any = None) -> float:
    numerator = global_norm(np.asarray(actual) - np.asarray(expected), comm)
    denominator = global_norm(expected, comm)
    if denominator == 0:
        return numerator
    return numerator / denominator


def two_pass_mgs_append(
    q: Any, column: Any, comm: Any = None
) -> tuple[np.ndarray, np.ndarray, float]:
    """Orthogonalize one column against existing Q with two MGS passes."""

    q_array = np.ascontiguousarray(np.asarray(q, dtype=np.complex128))
    vector = np.ascontiguousarray(np.asarray(column, dtype=np.complex128)).copy()
    if q_array.ndim != 2 or vector.ndim != 1 or q_array.shape[0] != vector.size:
        raise ValueError("MGS Q and column shapes are incompatible")
    if not np.all(np.isfinite(q_array)) or not np.all(np.isfinite(vector)):
        raise ValueError("MGS Q or column is non-finite")
    coefficients = np.zeros(q_array.shape[1], dtype=np.complex128)
    for _ in range(2):
        for basis_index in range(q_array.shape[1]):
            coefficient = hermitian_dot(q_array[:, basis_index], vector, comm)
            vector -= coefficient * q_array[:, basis_index]
            coefficients[basis_index] += coefficient
    norm = global_norm(vector, comm)
    if norm <= np.finfo(float).eps:
        raise ValueError("dependent MGS column")
    return vector / norm, coefficients, norm


def two_pass_mgs(columns: Sequence[Any], comm: Any = None) -> tuple[np.ndarray, np.ndarray]:
    """Two-pass modified Gram-Schmidt, retaining Q and R only."""

    if not columns:
        raise ValueError("at least one column is required")
    vectors = [np.ascontiguousarray(column, dtype=np.complex128) for column in columns]
    shape = vectors[0].shape
    if len(shape) != 1 or any(vector.shape != shape for vector in vectors):
        raise ValueError("MGS columns must be equally sized vectors")
    if any(not np.all(np.isfinite(vector)) for vector in vectors):
        raise ValueError("MGS column is non-finite")
    q = np.empty((shape[0], len(vectors)), dtype=np.complex128)
    r = np.zeros((len(vectors), len(vectors)), dtype=np.complex128)
    for column_index, original in enumerate(vectors):
        normalized, coefficients, norm = two_pass_mgs_append(
            q[:, :column_index], original, comm
        )
        if column_index:
            r[:column_index, column_index] = coefficients
        r[column_index, column_index] = norm
        q[:, column_index] = normalized
    return q, r


def project_onto_q(q: Any, residual: Any, comm: Any = None) -> dict[str, Any]:
    q_array = np.asarray(q, dtype=np.complex128)
    residual_array = np.asarray(residual, dtype=np.complex128)
    if q_array.ndim != 2 or residual_array.ndim != 1 or q_array.shape[0] != residual_array.size:
        raise ValueError("Q/residual shapes are incompatible")
    if not np.all(np.isfinite(q_array)) or not np.all(np.isfinite(residual_array)):
        raise ValueError("Q or residual is non-finite")
    coefficients = np.asarray(
        [hermitian_dot(q_array[:, i], residual_array, comm) for i in range(q_array.shape[1])],
        dtype=np.complex128,
    )
    projected = q_array @ coefficients
    perpendicular = residual_array - projected
    residual_norm = global_norm(residual_array, comm)
    perpendicular_norm = global_norm(perpendicular, comm)
    rho = perpendicular_norm / residual_norm if residual_norm else perpendicular_norm
    captured = 1.0 - rho * rho
    return {
        "coefficients": coefficients,
        "projected": projected,
        "perpendicular": perpendicular,
        "rho": float(rho),
        "captured_energy": float(captured),
    }


__all__ = [
    "V15_BRANCH",
    "V15_INPUT_SHA256",
    "V15_MODE_MANIFEST_SHA256",
    "V15_PHYSICAL_MODEL_SHA256",
    "V15_PROFILE",
    "V15_SELECTOR_POLICY",
    "V15_WAVELENGTH_NM",
    "V15_SELECTED_MODE_INDICES",
    "V15_SELECTOR_PAYLOAD_SHA256",
    "V15_SELECTOR_SCHEMA",
    "global_norm",
    "hermitian_dot",
    "project_onto_q",
    "relative_error",
    "select_v15_modes",
    "two_pass_mgs",
    "two_pass_mgs_append",
]
