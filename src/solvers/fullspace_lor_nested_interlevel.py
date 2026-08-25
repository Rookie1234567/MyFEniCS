"""Local Route-B nested 6->2 spectral oracle.

This module is deliberately limited to one-cell ``(6, 2)`` material classes.
It retains only the nested transfer and the two coarse-shaped audit arrays;
the fine matrix and the Galerkin product are transient dense workspaces.
No mesh, MPI, PETSc, Krylov, or global transfer object is constructed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from scipy.linalg import eigh, eigvalsh

from .fullspace_lor_interlevel_spectral import build_route_a_class_identity
from .fullspace_lor_memory_hierarchy import build_local_interlevel_edge_transfer
from .fullspace_lor_transfer import _assemble_lor_matrix, _gll_nodes


NESTED_METHOD = "lor_edge_geometric_mg_6_2_1_nested_v1"
NESTED_FINE_DEGREE = 6
NESTED_COARSE_DEGREE = 2
NESTED_EDGE_SHAPE = (882, 54)
NESTED_RANK = 54
NESTED_HERMITIAN_LIMIT = 1.0e-12
NESTED_ENDPOINT_LIMIT = 1.0e-10
NESTED_LAMBDA_MIN_LIMIT = 0.50
NESTED_LAMBDA_MAX_LIMIT = 2.00
NESTED_CONDITION_LIMIT = 4.00
NESTED_ENERGY_LIMIT = 1.0e-9
NESTED_SPECTRUM_DRIVER = "scipy.linalg.eigh:gvd"


@dataclass(frozen=True)
class NestedSpectralResult:
    """Immutable facts and the bounded retained payload for one class."""

    audit: MappingProxyType
    retained: MappingProxyType


def _positive(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _freeze_array(value: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(value, dtype=np.complex128)
    result.setflags(write=False)
    return result


def _relative_hermitian_defect(matrix: np.ndarray) -> float:
    return float(
        np.linalg.norm(matrix - matrix.conj().T)
        / max(np.linalg.norm(matrix), np.finfo(float).tiny)
    )


def _endpoint_residual(
    matrix: np.ndarray,
    mass: np.ndarray,
    eigenvalue: float,
    vector: np.ndarray,
) -> float:
    residual = matrix @ vector - eigenvalue * (mass @ vector)
    denominator = max(
        np.linalg.norm(matrix @ vector),
        abs(eigenvalue) * np.linalg.norm(mass @ vector),
        np.finfo(float).tiny,
    )
    return float(np.linalg.norm(residual) / denominator)


def nested_spectrum_gate(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen Route-B local spectral gates without defaults."""

    failures: list[str] = []
    finite_names = (
        "sigma_min", "sigma_max", "hermitian_defect_b2", "hermitian_defect_g62",
        "minimum_eigenvalue_b2", "minimum_eigenvalue_g62", "lambda_min",
        "lambda_max", "spectral_condition", "endpoint_residual_min",
        "endpoint_residual_max", "nested_energy_relative",
    )
    values: dict[str, float] = {}
    for name in finite_names:
        value = facts.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            failures.append(f"{name} non-finite")
        else:
            values[name] = float(value)
    if facts.get("rank") != NESTED_RANK:
        failures.append(f"rank != {NESTED_RANK}")
    if facts.get("strict_spd_b2") is not True:
        failures.append("B2 strict SPD")
    if facts.get("strict_spd_g62") is not True:
        failures.append("G62 strict SPD")
    if values.get("hermitian_defect_b2", math.inf) > NESTED_HERMITIAN_LIMIT:
        failures.append("B2 Hermitian defect")
    if values.get("hermitian_defect_g62", math.inf) > NESTED_HERMITIAN_LIMIT:
        failures.append("G62 Hermitian defect")
    if values.get("minimum_eigenvalue_b2", -math.inf) <= 0.0:
        failures.append("B2 strict SPD minimum")
    if values.get("minimum_eigenvalue_g62", -math.inf) <= 0.0:
        failures.append("G62 strict SPD minimum")
    if values.get("lambda_min", -math.inf) < NESTED_LAMBDA_MIN_LIMIT:
        failures.append("lambda_min")
    if values.get("lambda_max", math.inf) > NESTED_LAMBDA_MAX_LIMIT:
        failures.append("lambda_max")
    if values.get("spectral_condition", math.inf) > NESTED_CONDITION_LIMIT:
        failures.append("spectral condition")
    for name in ("endpoint_residual_min", "endpoint_residual_max"):
        if values.get(name, math.inf) > NESTED_ENDPOINT_LIMIT:
            failures.append(name)
    if values.get("nested_energy_relative", math.inf) > NESTED_ENERGY_LIMIT:
        failures.append("nested energy")
    if facts.get("finite") is not True:
        failures.append("finite")
    return {"passed": not failures, "failures": tuple(failures)}


def audit_nested_spectrum(
    p62: np.ndarray,
    b2: np.ndarray,
    b6p: np.ndarray,
    *,
    class_identity: Mapping[str, Any],
) -> NestedSpectralResult:
    """Independently derive the fixed ``P62`` generalized spectrum."""

    p62 = np.asarray(p62, dtype=np.complex128)
    b2 = np.asarray(b2, dtype=np.complex128)
    b6p = np.asarray(b6p, dtype=np.complex128)
    if p62.shape != NESTED_EDGE_SHAPE:
        raise ValueError(f"P62 shape {p62.shape} != {NESTED_EDGE_SHAPE}")
    if b2.shape != (NESTED_RANK, NESTED_RANK):
        raise ValueError("B2 shape is not closed")
    if b6p.shape != NESTED_EDGE_SHAPE:
        raise ValueError("B6P shape is not closed")
    if not all(np.all(np.isfinite(value)) for value in (p62, b2, b6p)):
        raise ValueError("nested audit arrays must be finite")

    g62 = p62.conj().T @ b6p
    singular = np.linalg.svd(p62, compute_uv=False)
    sigma_max = float(singular[0])
    sigma_min = float(singular[-1])
    rank_threshold = max(p62.shape) * np.finfo(np.float64).eps * sigma_max
    rank = int(np.count_nonzero(singular > rank_threshold))
    b2_eigenvalues = eigvalsh(b2, check_finite=True)
    g62_eigenvalues = eigvalsh(g62, check_finite=True)
    eigenvalues, eigenvectors = eigh(g62, b2, driver="gvd", check_finite=True)
    lambda_min = float(eigenvalues[0])
    lambda_max = float(eigenvalues[-1])
    spectral_condition = (
        float(lambda_max / lambda_min) if lambda_min > 0.0 else None
    )
    residual_min = _endpoint_residual(g62, b2, lambda_min, eigenvectors[:, 0])
    residual_max = _endpoint_residual(g62, b2, lambda_max, eigenvectors[:, -1])
    finite = bool(
        np.all(np.isfinite(singular))
        and np.all(np.isfinite(b2_eigenvalues))
        and np.all(np.isfinite(g62_eigenvalues))
        and np.isfinite(lambda_min)
        and np.isfinite(lambda_max)
        and spectral_condition is not None
        and np.isfinite(spectral_condition)
        and np.isfinite(residual_min)
        and np.isfinite(residual_max)
    )
    facts: dict[str, Any] = {
        "method": NESTED_METHOD,
        "class_digest": str(class_identity["class_digest"]),
        "material_coefficient_identity": dict(class_identity["material_coefficient_identity"]),
        "geometry_jacobian_identity": dict(class_identity["geometry_jacobian_identity"]),
        "rank": rank,
        "rank_threshold": float(rank_threshold),
        "sigma_min": sigma_min,
        "sigma_max": sigma_max,
        "hermitian_defect_b2": _relative_hermitian_defect(b2),
        "hermitian_defect_g62": _relative_hermitian_defect(g62),
        "minimum_eigenvalue_b2": float(b2_eigenvalues[0]),
        "minimum_eigenvalue_g62": float(g62_eigenvalues[0]),
        "strict_spd_b2": bool(b2_eigenvalues[0] > 0.0),
        "strict_spd_g62": bool(g62_eigenvalues[0] > 0.0),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "spectral_condition": spectral_condition,
        "endpoint_residual_min": residual_min,
        "endpoint_residual_max": residual_max,
        "nested_energy_relative": float(
            np.linalg.norm(g62 - b2) / max(np.linalg.norm(b2), np.finfo(float).tiny)
        ),
        "finite": finite,
        "eigensolver": NESTED_SPECTRUM_DRIVER,
        "p62_shape": [*NESTED_EDGE_SHAPE],
        "p62_nnz": int(np.count_nonzero(p62)),
        "b2_shape": [NESTED_RANK, NESTED_RANK],
        "b6p_shape": [*NESTED_EDGE_SHAPE],
        "nested_tiled_geometric": True,
        "generic_high_polynomial_reconstruction": False,
        "b6_dense_audit_only": True,
        "b6_dense_retained": False,
        "g62_dense_audit_only": True,
        "g62_dense_retained": False,
        "retained_payload_roles": [
            "p62", "b2", "b6p", "eigenvector_min", "eigenvector_max"
        ],
    }
    gate = nested_spectrum_gate(facts)
    facts["gate_passed"] = bool(gate["passed"])
    facts["gate_failures"] = list(gate["failures"])
    retained = MappingProxyType(
        {
            "p62": _freeze_array(p62),
            "b2": _freeze_array(b2),
            "b6p": _freeze_array(b6p),
            "eigenvector_min": _freeze_array(eigenvectors[:, 0]),
            "eigenvector_max": _freeze_array(eigenvectors[:, -1]),
        }
    )
    return NestedSpectralResult(MappingProxyType(facts), retained)


def build_nested_material_class(
    *,
    class_name: str = "unit_positive_reference",
    widths: tuple[float, float, float] = (1.0, 1.0, 1.0),
    curl_coefficient: float = 1.0,
    mass_coefficient: float = 1.0,
    material_role: str = "unspecified",
    p62: np.ndarray | None = None,
) -> NestedSpectralResult:
    """Build one exact positive ``B6/B2`` class and audit its nested spectrum."""

    widths = tuple(_positive(value, "width") for value in widths)
    if len(widths) != 3:
        raise ValueError("exactly three widths are required")
    curl_coefficient = _positive(curl_coefficient, "curl_coefficient")
    mass_coefficient = _positive(mass_coefficient, "mass_coefficient")
    identity_and_digest = build_route_a_class_identity(
        class_name=class_name,
        widths=widths,
        curl_coefficient=curl_coefficient,
        mass_coefficient=mass_coefficient,
        material_role=material_role,
    )
    if p62 is None:
        p62 = build_local_interlevel_edge_transfer(6, 2).edge_transfer
    p62 = np.asarray(p62, dtype=np.complex128)
    if p62.shape != NESTED_EDGE_SHAPE or not np.all(np.isfinite(p62)):
        raise ValueError("P62 shape/finite facts are not closed")
    b6 = _assemble_lor_matrix(
        6, _gll_nodes(6), widths,
        curl_coefficient=curl_coefficient,
        mass_coefficient=mass_coefficient,
    )
    b2 = _assemble_lor_matrix(
        2, _gll_nodes(2), widths,
        curl_coefficient=curl_coefficient,
        mass_coefficient=mass_coefficient,
    )
    b6p = b6 @ p62
    result = audit_nested_spectrum(
        p62,
        b2,
        b6p,
        class_identity={
            **identity_and_digest["class_identity"],
            "class_digest": identity_and_digest["class_digest"],
        },
    )
    del b6, b2, b6p
    return result


__all__ = [
    "NESTED_CONDITION_LIMIT",
    "NESTED_EDGE_SHAPE",
    "NESTED_ENERGY_LIMIT",
    "NESTED_ENDPOINT_LIMIT",
    "NESTED_HERMITIAN_LIMIT",
    "NESTED_LAMBDA_MAX_LIMIT",
    "NESTED_LAMBDA_MIN_LIMIT",
    "NESTED_METHOD",
    "NESTED_RANK",
    "NestedSpectralResult",
    "audit_nested_spectrum",
    "build_nested_material_class",
    "nested_spectrum_gate",
]
