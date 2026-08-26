"""Floquet-carrier envelope helpers for high-frequency H(curl) Maxwell research.

This module is research-only.  It contains pure NumPy reference algebra plus
small UFL form helpers.  It does not alter any production solver defaults.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

_TWO_PI = 2.0 * np.pi


__all__ = (
    "FloquetCarrier",
    "FloquetLattice2D",
    "carrier_phase",
    "carrier_phase_gram",
    "carrier_phase_rank_report",
    "cross_carrier_phase",
    "floquet_compatibility_error",
    "greedy_independent_carriers",
    "make_floquet_carrier",
    "maxwell_block_density",
    "naive_memory_envelope",
    "naive_uniform_refinement_multiplier",
    "rectangular_carrier_family",
    "shifted_curl_value",
    "ufl_cross_carrier_phase",
    "ufl_maxwell_block_integrand",
    "ufl_shifted_curl",
)


def _real_vector2(value: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (2,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite length-2 vector")
    return array


def _complex_vector3(value: Sequence[complex], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.complex128)
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite length-3 vector")
    return array


@dataclass(frozen=True)
class FloquetLattice2D:
    """Two-dimensional periodic lattice embedded in the x/y plane."""

    a1: tuple[float, float]
    a2: tuple[float, float]

    def direct_matrix(self) -> np.ndarray:
        a1 = _real_vector2(self.a1, "a1")
        a2 = _real_vector2(self.a2, "a2")
        matrix = np.column_stack((a1, a2))
        determinant = float(np.linalg.det(matrix))
        if abs(determinant) <= 1.0e-14 * max(np.linalg.norm(matrix) ** 2, 1.0):
            raise ValueError("periodic lattice vectors are linearly dependent")
        return matrix

    def reciprocal_matrix(self) -> np.ndarray:
        """Return columns b1,b2 satisfying a_i dot b_j = 2*pi delta_ij."""

        direct = self.direct_matrix()
        return _TWO_PI * np.linalg.inv(direct).T

    def reciprocal_vectors(self) -> tuple[np.ndarray, np.ndarray]:
        matrix = self.reciprocal_matrix()
        return matrix[:, 0].copy(), matrix[:, 1].copy()


@dataclass(frozen=True)
class FloquetCarrier:
    """One Bloch-compatible carrier wave.

    ``kappa`` may have a complex z component to represent an evanescent
    carrier.  The x/y components should equal k_B + m*b1 + n*b2.
    """

    m: int
    n: int
    kappa: tuple[complex, complex, complex]
    label: str = ""

    def vector(self) -> np.ndarray:
        return _complex_vector3(self.kappa, "carrier kappa")


def make_floquet_carrier(
    lattice: FloquetLattice2D,
    bloch_k_t: Sequence[float],
    m: int,
    n: int,
    *,
    beta: complex = 0.0,
    label: str = "",
) -> FloquetCarrier:
    """Construct kappa=(k_B+m*b1+n*b2, beta)."""

    bloch = _real_vector2(bloch_k_t, "bloch_k_t")
    b1, b2 = lattice.reciprocal_vectors()
    transverse = bloch + int(m) * b1 + int(n) * b2
    kappa = (complex(transverse[0]), complex(transverse[1]), complex(beta))
    return FloquetCarrier(int(m), int(n), kappa, label)


def rectangular_carrier_family(
    lattice: FloquetLattice2D,
    bloch_k_t: Sequence[float],
    m_values: Sequence[int],
    n_values: Sequence[int],
    *,
    beta_by_order: dict[tuple[int, int], complex] | None = None,
) -> tuple[FloquetCarrier, ...]:
    """Create a deterministic rectangular family ordered by (m,n)."""

    beta_by_order = dict(beta_by_order or {})
    carriers = [
        make_floquet_carrier(
            lattice,
            bloch_k_t,
            m,
            n,
            beta=beta_by_order.get((int(m), int(n)), 0.0),
            label=f"m{int(m):+d}_n{int(n):+d}",
        )
        for m in sorted({int(value) for value in m_values})
        for n in sorted({int(value) for value in n_values})
    ]
    return tuple(carriers)


def floquet_compatibility_error(
    carrier: FloquetCarrier,
    lattice: FloquetLattice2D,
    bloch_k_t: Sequence[float],
) -> float:
    """Return the largest x/y Bloch multiplier mismatch."""

    bloch = _real_vector2(bloch_k_t, "bloch_k_t")
    kappa_t = carrier.vector()[:2]
    errors = []
    for direct in (np.asarray(lattice.a1), np.asarray(lattice.a2)):
        carrier_multiplier = np.exp(1j * np.dot(kappa_t, direct))
        bloch_multiplier = np.exp(1j * np.dot(bloch, direct))
        errors.append(abs(carrier_multiplier - bloch_multiplier))
    return float(max(errors, default=0.0))


def carrier_phase(points: np.ndarray, kappa: Sequence[complex]) -> np.ndarray:
    """Evaluate exp(i*kappa dot x) for points with final dimension three."""

    point_array = np.asarray(points, dtype=float)
    if point_array.ndim == 0 or point_array.shape[-1] != 3:
        raise ValueError("points must have final dimension three")
    wavevector = _complex_vector3(kappa, "kappa")
    exponent = np.tensordot(point_array, wavevector, axes=([-1], [0]))
    return np.exp(1j * exponent)


def cross_carrier_phase(
    points: np.ndarray,
    trial_kappa: Sequence[complex],
    test_kappa: Sequence[complex],
) -> np.ndarray:
    """Return exp(i*(k_trial-conj(k_test)) dot x)."""

    trial = _complex_vector3(trial_kappa, "trial_kappa")
    test = _complex_vector3(test_kappa, "test_kappa")
    return carrier_phase(points, trial - np.conjugate(test))


def shifted_curl_value(
    envelope_value: np.ndarray,
    envelope_curl: np.ndarray,
    kappa: Sequence[complex],
) -> np.ndarray:
    """Evaluate curl(u)+i*kappa cross u pointwise."""

    value = np.asarray(envelope_value, dtype=np.complex128)
    curl = np.asarray(envelope_curl, dtype=np.complex128)
    if value.shape != curl.shape or value.shape[-1] != 3:
        raise ValueError("envelope_value and envelope_curl must share (...,3) shape")
    wavevector = _complex_vector3(kappa, "kappa")
    broadcast = np.broadcast_to(wavevector, value.shape)
    return curl + 1j * np.cross(broadcast, value)


def maxwell_block_density(
    *,
    point: Sequence[float],
    trial_value: Sequence[complex],
    trial_curl: Sequence[complex],
    test_value: Sequence[complex],
    test_curl: Sequence[complex],
    trial_kappa: Sequence[complex],
    test_kappa: Sequence[complex],
    mu_inv: complex,
    epsilon: complex,
    k0: float,
) -> complex:
    """Pointwise carrier block density for isotropic material coefficients."""

    x = np.asarray(point, dtype=float)
    if x.shape != (3,) or not np.all(np.isfinite(x)):
        raise ValueError("point must be a finite length-3 vector")
    u = _complex_vector3(trial_value, "trial_value")
    curl_u = _complex_vector3(trial_curl, "trial_curl")
    v = _complex_vector3(test_value, "test_value")
    curl_v = _complex_vector3(test_curl, "test_curl")
    shifted_u = shifted_curl_value(u, curl_u, trial_kappa)
    shifted_v = shifted_curl_value(v, curl_v, test_kappa)
    phase = complex(cross_carrier_phase(x, trial_kappa, test_kappa))
    curl_term = complex(mu_inv) * np.dot(shifted_u, np.conjugate(shifted_v))
    mass_term = (float(k0) ** 2) * complex(epsilon) * np.dot(
        u, np.conjugate(v)
    )
    return phase * (curl_term - mass_term)


def carrier_phase_gram(
    points: np.ndarray,
    weights: Sequence[float],
    carriers: Sequence[FloquetCarrier],
) -> np.ndarray:
    """Mass-normalized Gram matrix of sampled carrier phases."""

    point_array = np.asarray(points, dtype=float)
    weight_array = np.asarray(weights, dtype=float)
    if point_array.ndim != 2 or point_array.shape[1] != 3:
        raise ValueError("points must have shape (n,3)")
    if weight_array.shape != (point_array.shape[0],):
        raise ValueError("weights must have one entry per point")
    if np.any(weight_array < 0.0) or not np.all(np.isfinite(weight_array)):
        raise ValueError("weights must be finite and non-negative")
    if not carriers:
        return np.zeros((0, 0), dtype=np.complex128)
    phase_matrix = np.column_stack(
        [carrier_phase(point_array, carrier.vector()) for carrier in carriers]
    )
    weighted = np.sqrt(weight_array)[:, None] * phase_matrix
    gram = weighted.conj().T @ weighted
    diagonal = np.sqrt(np.maximum(np.real(np.diag(gram)), 0.0))
    if np.any(diagonal <= 1.0e-30):
        raise ValueError("at least one carrier has zero sampled norm")
    return gram / diagonal[:, None] / diagonal[None, :]


def carrier_phase_rank_report(
    points: np.ndarray,
    weights: Sequence[float],
    carriers: Sequence[FloquetCarrier],
    *,
    relative_tolerance: float = 1.0e-10,
) -> dict[str, Any]:
    """Report numerical rank/conditioning of the sampled phase family."""

    gram = carrier_phase_gram(points, weights, carriers)
    if gram.size == 0:
        return {
            "carrier_count": 0,
            "numerical_rank": 0,
            "condition": None,
            "singular_values": [],
            "relative_tolerance": float(relative_tolerance),
        }
    singular_values = np.linalg.svd(gram, compute_uv=False)
    scale = float(singular_values[0])
    threshold = float(relative_tolerance) * max(scale, 1.0)
    retained = singular_values[singular_values > threshold]
    condition = float(retained[0] / retained[-1]) if retained.size else None
    return {
        "carrier_count": len(carriers),
        "numerical_rank": int(retained.size),
        "condition": condition,
        "singular_values": [float(value) for value in singular_values],
        "relative_tolerance": float(relative_tolerance),
    }


def greedy_independent_carriers(
    points: np.ndarray,
    weights: Sequence[float],
    carriers: Sequence[FloquetCarrier],
    *,
    relative_tolerance: float = 1.0e-8,
) -> tuple[tuple[FloquetCarrier, ...], dict[str, Any]]:
    """Deterministically retain sampled carrier columns with new information."""

    point_array = np.asarray(points, dtype=float)
    weight_array = np.asarray(weights, dtype=float)
    if point_array.ndim != 2 or point_array.shape[1] != 3:
        raise ValueError("points must have shape (n,3)")
    if weight_array.shape != (point_array.shape[0],):
        raise ValueError("weights must have one entry per point")
    weighted_columns = [
        np.sqrt(weight_array) * carrier_phase(point_array, carrier.vector())
        for carrier in carriers
    ]
    basis: list[np.ndarray] = []
    selected: list[FloquetCarrier] = []
    residual_ratios: list[float] = []
    for carrier, raw_column in zip(carriers, weighted_columns):
        norm = float(np.linalg.norm(raw_column))
        if norm <= 1.0e-30:
            residual_ratios.append(0.0)
            continue
        column = raw_column.astype(np.complex128, copy=True)
        for vector in basis:
            column -= vector * np.vdot(vector, column)
        for vector in basis:
            column -= vector * np.vdot(vector, column)
        residual_ratio = float(np.linalg.norm(column) / norm)
        residual_ratios.append(residual_ratio)
        if residual_ratio > float(relative_tolerance):
            basis.append(column / np.linalg.norm(column))
            selected.append(carrier)
    return tuple(selected), {
        "input_count": len(carriers),
        "selected_count": len(selected),
        "relative_tolerance": float(relative_tolerance),
        "residual_ratios": residual_ratios,
        "selected_labels": [
            carrier.label or f"({carrier.m},{carrier.n})" for carrier in selected
        ],
    }


def naive_uniform_refinement_multiplier(
    reference_wavelength: float,
    target_wavelength: float,
    *,
    dimension: int = 3,
) -> float:
    """Return (lambda_ref/lambda_target)^dimension."""

    reference = float(reference_wavelength)
    target = float(target_wavelength)
    if reference <= 0.0 or target <= 0.0:
        raise ValueError("wavelengths must be positive")
    if int(dimension) <= 0:
        raise ValueError("dimension must be positive")
    return float((reference / target) ** int(dimension))


def naive_memory_envelope(
    reference_memory_gib: float,
    reference_wavelength: float,
    target_wavelength: float,
    *,
    dimension: int = 3,
) -> float:
    """Linear-in-DoF memory envelope under uniform wavelength refinement."""

    memory = float(reference_memory_gib)
    if memory < 0.0:
        raise ValueError("reference memory must be non-negative")
    return memory * naive_uniform_refinement_multiplier(
        reference_wavelength, target_wavelength, dimension=dimension
    )


def ufl_shifted_curl(envelope: Any, kappa: Sequence[complex]) -> Any:
    """Return the UFL expression curl(u)+i*kappa cross u."""

    import ufl

    wavevector = _complex_vector3(kappa, "kappa")
    constant = ufl.as_vector(tuple(complex(value) for value in wavevector))
    return ufl.curl(envelope) + 1j * ufl.cross(constant, envelope)


def ufl_cross_carrier_phase(
    spatial_coordinate: Any,
    trial_kappa: Sequence[complex],
    test_kappa: Sequence[complex],
) -> Any:
    """Return UFL exp(i*(k_trial-conj(k_test)) dot x)."""

    import ufl

    trial = _complex_vector3(trial_kappa, "trial_kappa")
    test = _complex_vector3(test_kappa, "test_kappa")
    delta = trial - np.conjugate(test)
    argument = sum(
        complex(delta[index]) * spatial_coordinate[index] for index in range(3)
    )
    return ufl.exp(1j * argument)


def ufl_maxwell_block_integrand(
    *,
    trial_envelope: Any,
    test_envelope: Any,
    spatial_coordinate: Any,
    trial_kappa: Sequence[complex],
    test_kappa: Sequence[complex],
    mu_inv: Any,
    epsilon: Any,
    k0: Any,
) -> Any:
    """Create one carrier-to-carrier isotropic Maxwell volume integrand."""

    import ufl

    shifted_trial = ufl_shifted_curl(trial_envelope, trial_kappa)
    shifted_test = ufl_shifted_curl(test_envelope, test_kappa)
    phase = ufl_cross_carrier_phase(
        spatial_coordinate, trial_kappa, test_kappa
    )
    return phase * (
        mu_inv * ufl.inner(shifted_trial, shifted_test)
        - (k0**2) * epsilon * ufl.inner(trial_envelope, test_envelope)
    )
