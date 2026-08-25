"""Small Route-A local interlevel spectral oracle.

The bounded retained audit payload is one P63, B3, B6@P63, and the two endpoint
eigenvectors per material class.  The dense B6 and G63 arrays are audit-only
workspaces and are released by the builder.  No MPI, PETSc, global transfer,
or Krylov object is built.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from scipy.linalg import eigh, eigvalsh

from .fullspace_lor_interlevel_route_selection import (
    CONDITION_LIMIT,
    ENDPOINT_RESIDUAL_LIMIT,
    HERMITIAN_LIMIT,
    LAMBDA_MAX_LIMIT,
    LAMBDA_MIN_LIMIT,
    ROUTE_A_RANK,
)
from .fullspace_lor_memory_hierarchy import (
    LocalInterlevelEdgeTransfer,
    build_local_interlevel_edge_transfer,
)
from .fullspace_lor_memory_hierarchy_runtime import _OwnerPacketTransfer
from .fullspace_lor_transfer import (
    _assemble_lor_matrix,
    _gll_nodes,
)


ROUTE_A_METHOD = "lor_edge_geometric_mg_6_3_1_spectral_v2"
P63_FINE_DEGREE = 6
P63_COARSE_DEGREE = 3
SPECTRUM_DRIVER = "scipy.linalg.eigh:gvd"
RANK_EPS_FACTOR = np.finfo(np.float64).eps


@dataclass(frozen=True)
class RouteASpectralResult:
    """Facts plus the minimal retained arrays for one local material class."""

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


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_route_a_class_identity(
    *, class_name: str, widths: tuple[float, float, float],
    curl_coefficient: float, mass_coefficient: float,
    material_role: str = "unspecified",
) -> dict[str, Any]:
    """Return the single exact identity payload used by worker and adapter."""

    material_identity = {
        "class_name": str(class_name),
        "material_role": str(material_role),
        "form": "curl_coefficient*curlcurl_plus_mass_coefficient*mass",
        "curl_coefficient": float(curl_coefficient),
        "mass_coefficient": float(mass_coefficient),
        "curl_coefficient_float64_hex": float(curl_coefficient).hex(),
        "mass_coefficient_float64_hex": float(mass_coefficient).hex(),
        "scalar_dtype": "complex128",
    }
    geometry_identity = {
        "cell": "reference_hexahedron_affine",
        "jacobian_diagonal": [float(value) for value in widths],
        "widths": [float(value) for value in widths],
        "widths_float64_hex": [float(value).hex() for value in widths],
    }
    identity = {
        "material_coefficient_identity": material_identity,
        "geometry_jacobian_identity": geometry_identity,
    }
    return {"class_identity": identity, "class_digest": _digest(identity)}


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


def route_a_spectrum_gate(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen local Route-A numerical gates to already-derived facts."""

    failures: list[str] = []
    numeric_names = (
        "rank",
        "hermitian_defect_b3",
        "hermitian_defect_g63",
        "minimum_eigenvalue_b3",
        "minimum_eigenvalue_g63",
        "lambda_min",
        "lambda_max",
        "spectral_condition",
        "endpoint_residual_min",
        "endpoint_residual_max",
    )
    numeric: dict[str, float] = {}
    fallback = {
        "rank": math.nan,
        "hermitian_defect_b3": math.inf,
        "hermitian_defect_g63": math.inf,
        "minimum_eigenvalue_b3": -math.inf,
        "minimum_eigenvalue_g63": -math.inf,
        "lambda_min": -math.inf,
        "lambda_max": math.inf,
        "spectral_condition": math.inf,
        "endpoint_residual_min": math.inf,
        "endpoint_residual_max": math.inf,
    }
    for name in numeric_names:
        value = facts.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            failures.append(f"{name} non-finite")
            numeric[name] = fallback[name]
        else:
            numeric[name] = float(value)
    if numeric["rank"] != ROUTE_A_RANK:
        failures.append("rank")
    if numeric["hermitian_defect_b3"] > HERMITIAN_LIMIT:
        failures.append("B3 Hermitian defect")
    if numeric["hermitian_defect_g63"] > HERMITIAN_LIMIT:
        failures.append("G63 Hermitian defect")
    if numeric["minimum_eigenvalue_b3"] <= 0.0:
        failures.append("B3 strict SPD")
    if numeric["minimum_eigenvalue_g63"] <= 0.0:
        failures.append("G63 strict SPD")
    if numeric["lambda_min"] < LAMBDA_MIN_LIMIT:
        failures.append("lambda_min")
    if numeric["lambda_max"] > LAMBDA_MAX_LIMIT:
        failures.append("lambda_max")
    if numeric["spectral_condition"] > CONDITION_LIMIT:
        failures.append("spectral condition")
    if numeric["endpoint_residual_min"] > ENDPOINT_RESIDUAL_LIMIT:
        failures.append("smallest endpoint residual")
    if numeric["endpoint_residual_max"] > ENDPOINT_RESIDUAL_LIMIT:
        failures.append("largest endpoint residual")
    if facts.get("finite") is not True:
        failures.append("finite")
    return {"passed": not failures, "failures": tuple(failures)}


def audit_route_a_spectrum(
    p63: np.ndarray,
    b3: np.ndarray,
    b6p: np.ndarray,
    *,
    class_identity: Mapping[str, Any],
) -> RouteASpectralResult:
    """Derive Route-A spectrum facts from bounded dense audit arrays."""

    p63 = np.asarray(p63, dtype=np.complex128)
    b3 = np.asarray(b3, dtype=np.complex128)
    b6p = np.asarray(b6p, dtype=np.complex128)
    if p63.ndim != 2 or b3.shape != (p63.shape[1], p63.shape[1]):
        raise ValueError("P63/B3 shapes are not closed")
    if b6p.shape != p63.shape:
        raise ValueError("B6P shape is not closed")
    if not np.all(np.isfinite(p63)) or not np.all(np.isfinite(b3)) or not np.all(np.isfinite(b6p)):
        raise ValueError("Route-A audit arrays must be finite")

    g63 = p63.conj().T @ b6p
    singular_values = np.linalg.svd(p63, compute_uv=False)
    sigma_max = float(singular_values[0])
    sigma_min = float(singular_values[-1])
    rank_threshold = max(p63.shape) * RANK_EPS_FACTOR * sigma_max
    rank = int(np.count_nonzero(singular_values > rank_threshold))
    b3_eigenvalues = eigvalsh(b3, check_finite=True)
    g63_eigenvalues = eigvalsh(g63, check_finite=True)
    eigenvalues, eigenvectors = eigh(
        g63,
        b3,
        driver="gvd",
        check_finite=True,
    )
    lambda_min = float(eigenvalues[0])
    lambda_max = float(eigenvalues[-1])
    spectral_condition = (
        float(lambda_max / lambda_min) if lambda_min > 0.0 else None
    )
    residual_min = _endpoint_residual(
        g63, b3, lambda_min, eigenvectors[:, 0]
    )
    residual_max = _endpoint_residual(
        g63, b3, lambda_max, eigenvectors[:, -1]
    )
    finite = bool(
        np.all(np.isfinite(singular_values))
        and np.all(np.isfinite(b3_eigenvalues))
        and np.all(np.isfinite(g63_eigenvalues))
        and np.isfinite(lambda_min)
        and np.isfinite(lambda_max)
        and np.isfinite(residual_min)
        and np.isfinite(residual_max)
    )
    facts: dict[str, Any] = {
        "method": ROUTE_A_METHOD,
        "class_digest": str(class_identity["class_digest"]),
        "material_coefficient_identity": dict(class_identity["material_coefficient_identity"]),
        "geometry_jacobian_identity": dict(class_identity["geometry_jacobian_identity"]),
        "rank": rank,
        "rank_threshold": float(rank_threshold),
        "sigma_min": sigma_min,
        "sigma_max": sigma_max,
        "hermitian_defect_b3": _relative_hermitian_defect(b3),
        "hermitian_defect_g63": _relative_hermitian_defect(g63),
        "minimum_eigenvalue_b3": float(b3_eigenvalues[0]),
        "minimum_eigenvalue_g63": float(g63_eigenvalues[0]),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "spectral_condition": spectral_condition,
        "endpoint_residual_min": residual_min,
        "endpoint_residual_max": residual_max,
        "finite": finite,
        "eigensolver": SPECTRUM_DRIVER,
        "p63_shape": [int(value) for value in p63.shape],
        "b3_shape": [int(value) for value in b3.shape],
        "b6p_shape": [int(value) for value in b6p.shape],
        "b6_dense_audit_only": True,
        "b6_dense_retained": False,
        "g63_dense_audit_only": True,
        "retained_payload_roles": [
            "p63", "b3", "b6p", "eigenvector_min", "eigenvector_max"
        ],
    }
    gate = route_a_spectrum_gate(facts)
    facts["gate_passed"] = bool(gate["passed"])
    facts["gate_failures"] = list(gate["failures"])
    retained = MappingProxyType(
        {
            "p63": _freeze_array(p63),
            "b3": _freeze_array(b3),
            "b6p": _freeze_array(b6p),
            "eigenvector_min": _freeze_array(eigenvectors[:, 0]),
            "eigenvector_max": _freeze_array(eigenvectors[:, -1]),
        }
    )
    return RouteASpectralResult(MappingProxyType(facts), retained)


def build_route_a_material_class(
    *,
    class_name: str = "unit_positive_reference",
    widths: tuple[float, float, float] = (1.0, 1.0, 1.0),
    curl_coefficient: float = 1.0,
    mass_coefficient: float = 1.0,
    material_role: str = "unspecified",
    p63: np.ndarray | None = None,
) -> RouteASpectralResult:
    """Build one exact positive local class and audit its 6<-3 spectrum."""

    if not isinstance(class_name, str) or not class_name:
        raise ValueError("class_name must be non-empty")
    widths = tuple(_positive(value, "width") for value in widths)
    if len(widths) != 3:
        raise ValueError("exactly three widths are required")
    curl_coefficient = _positive(curl_coefficient, "curl_coefficient")
    mass_coefficient = _positive(mass_coefficient, "mass_coefficient")
    identity_and_digest = build_route_a_class_identity(
        class_name=class_name, widths=widths,
        curl_coefficient=curl_coefficient, mass_coefficient=mass_coefficient,
        material_role=material_role,
    )
    class_identity = identity_and_digest["class_identity"]
    if p63 is None:
        p63 = build_local_interlevel_edge_transfer(6, 3).edge_transfer
    p63 = np.asarray(p63, dtype=np.complex128)
    if p63.shape != (882, 144) or not np.all(np.isfinite(p63)):
        raise ValueError("P63 shape/finite facts are not closed")
    b6 = _assemble_lor_matrix(
        6,
        _gll_nodes(6),
        widths,
        curl_coefficient=curl_coefficient,
        mass_coefficient=mass_coefficient,
    )
    b3 = _assemble_lor_matrix(
        3,
        _gll_nodes(3),
        widths,
        curl_coefficient=curl_coefficient,
        mass_coefficient=mass_coefficient,
    )
    b6p = b6 @ p63
    result = audit_route_a_spectrum(
        p63,
        b3,
        b6p,
        class_identity={
            **class_identity,
            "class_digest": identity_and_digest["class_digest"],
        },
    )
    del b6, b3, b6p
    return result


class RouteAProbeExtension:
    """Level-6/3 owner-packet probe bridge; levels remain caller-owned."""

    def __init__(
        self,
        level6: Any,
        level3: Any,
        local_transfer: LocalInterlevelEdgeTransfer,
        *,
        owns_level3: bool = False,
        owns_level6_wrapper: bool = False,
        foundation_caller_owned: bool = False,
    ) -> None:
        if (int(level6.degree), int(level3.degree)) != (6, 3):
            raise ValueError("Route-A probe extension is fixed at levels 6 and 3")
        self.levels = (level6, level3)
        self._transfer = _OwnerPacketTransfer(level6, level3, local_transfer)
        self._owns_level3 = bool(owns_level3)
        self._owns_level6_wrapper = bool(owns_level6_wrapper)
        self._destroyed = False
        self.audit = MappingProxyType(
            {
                "method": ROUTE_A_METHOD,
                "levels": [6, 3],
                "pair": [6, 3],
                "owner_packet_route": True,
                "global_high_order_aij": False,
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "p1_global_direct_factor": False,
                "p1_built": False,
                "smoother_built": False,
                "ksp_created": False,
                "physical_solve": False,
                "recovery": False,
                "owns_level3": self._owns_level3,
                "owns_level6_wrapper": self._owns_level6_wrapper,
                "foundation_caller_owned": bool(foundation_caller_owned),
            }
        )

    def apply_primal(self, source: Any) -> Any:
        if self._destroyed:
            raise RuntimeError("Route-A probe extension has been destroyed")
        return self._transfer.apply_primal(source)

    def apply_adjoint(self, source: Any) -> Any:
        if self._destroyed:
            raise RuntimeError("Route-A probe extension has been destroyed")
        return self._transfer.apply_adjoint(source)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        level6, level3 = self.levels
        self._transfer = None
        if self._owns_level3:
            level3.destroy()
        if self._owns_level6_wrapper:
            level6.destroy()
        self.levels = ()
        self._owns_level3 = False
        self._owns_level6_wrapper = False


def build_route_a_probe_extension(
    level6: Any,
    level3: Any,
    local_transfer: LocalInterlevelEdgeTransfer | None = None,
) -> RouteAProbeExtension:
    """Build only the level-6/3 owner-packet probe path."""

    if local_transfer is None:
        local_transfer = build_local_interlevel_edge_transfer(6, 3)
    return RouteAProbeExtension(level6, level3, local_transfer)


def _foundation_parent_axes(foundation: Any) -> tuple[np.ndarray, ...]:
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    plan = _stage4_axis_plan(foundation.cfg, foundation.high_mesh.comm.size)
    return tuple(
        np.asarray(axis, dtype=np.float64)
        for axis in (plan.x_values, plan.y_values, plan.z_values)
    )


def build_route_a_probe_extension_from_foundation(
    foundation: Any,
    local_transfer: LocalInterlevelEdgeTransfer | None = None,
) -> RouteAProbeExtension:
    """Build only the owned level-6/3 Route-A bridge from an S2 foundation."""

    if foundation is None or not hasattr(foundation, "low_matrix"):
        raise ValueError("Route-A probe requires an already-built S2 foundation")
    from .fullspace_lor_memory_hierarchy_runtime import _build_level, _build_level6

    level6 = _build_level6(foundation)
    level3 = None
    try:
        level3 = _build_level(foundation, 3, _foundation_parent_axes(foundation))
        return RouteAProbeExtension(
            level6,
            level3,
            build_local_interlevel_edge_transfer(6, 3)
            if local_transfer is None else local_transfer,
            owns_level3=True,
            owns_level6_wrapper=True,
            foundation_caller_owned=True,
        )
    except Exception:
        if level3 is not None:
            level3.destroy()
        level6.destroy()
        raise


def signed_permutation_similarity(
    p63: np.ndarray,
    b3: np.ndarray,
    b6p: np.ndarray,
    permutation: np.ndarray,
    signs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply a coarse signed permutation to P, B3, and B6P consistently."""

    p63 = np.asarray(p63, dtype=np.complex128)
    b3 = np.asarray(b3, dtype=np.complex128)
    b6p = np.asarray(b6p, dtype=np.complex128)
    permutation = np.asarray(permutation, dtype=np.int64)
    signs = np.asarray(signs, dtype=np.complex128)
    size = b3.shape[0]
    if permutation.shape != (size,) or signs.shape != (size,):
        raise ValueError("signed permutation shape is not closed")
    if not np.array_equal(np.sort(permutation), np.arange(size)):
        raise ValueError("signed permutation indices are not a permutation")
    if not np.all(np.abs(signs) == 1.0):
        raise ValueError("orientation signs must have unit magnitude")
    similarity = np.zeros((size, size), dtype=np.complex128)
    similarity[permutation, np.arange(size)] = signs
    return (
        p63 @ similarity,
        similarity.conj().T @ b3 @ similarity,
        b6p @ similarity,
    )


__all__ = [
    "ROUTE_A_METHOD",
    "RouteAProbeExtension",
    "RouteASpectralResult",
    "audit_route_a_spectrum",
    "build_route_a_material_class",
    "build_route_a_class_identity",
    "build_route_a_probe_extension",
    "build_route_a_probe_extension_from_foundation",
    "route_a_spectrum_gate",
    "signed_permutation_similarity",
]
