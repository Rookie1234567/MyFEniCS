"""Reference algebra for a structured Floquet-background H(curl) preconditioner.

This module is research-only.  It implements a constant-coefficient,
fully-periodic Fourier reference operator and its analytic inverse.  The
production target is different: FFT only in the periodic x/y directions and
a bounded 1D z solve per transverse harmonic.  The fully-periodic kernel is a
small, dependency-light oracle for signs, Bloch shifts, transverse/longitudinal
splitting, and memory estimates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

_TWO_PI = 2.0 * np.pi

__all__ = (
    "PeriodicBox3D",
    "apply_periodic_background_inverse",
    "apply_periodic_background_operator",
    "bloch_fft_frequencies",
    "estimate_periodic_fft_working_set_bytes",
    "maxwell_fourier_symbol",
    "maxwell_symbol_inverse",
    "relative_l2_error",
    "transverse_longitudinal_projectors",
)


def _positive_float(value: float, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


def _real_vector3(value: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite length-3 vector")
    return array


def _complex_scalar(value: complex, name: str) -> complex:
    result = complex(value)
    if not np.isfinite(result.real) or not np.isfinite(result.imag):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class PeriodicBox3D:
    """Fully periodic reference box used by the lightweight Fourier oracle."""

    lengths: tuple[float, float, float]

    def validated_lengths(self) -> np.ndarray:
        validated = tuple(
            _positive_float(value, f"lengths[{index}]")
            for index, value in enumerate(self.lengths)
        )
        return np.asarray(validated, dtype=float)


def bloch_fft_frequencies(
    count: int,
    length: float,
    bloch_component: float = 0.0,
) -> np.ndarray:
    """Return FFT-ordered wave numbers ``k_B + 2*pi*n/L``.

    The returned order matches ``numpy.fft.fft``.  The unknown is interpreted
    as a periodic envelope while the reconstructed physical field carries the
    supplied Bloch phase.
    """

    if int(count) != count or int(count) <= 0:
        raise ValueError("count must be a positive integer")
    count = int(count)
    length = _positive_float(length, "length")
    bloch_component = float(bloch_component)
    if not np.isfinite(bloch_component):
        raise ValueError("bloch_component must be finite")
    spacing = length / count
    return bloch_component + _TWO_PI * np.fft.fftfreq(count, d=spacing)


def transverse_longitudinal_projectors(
    wavevector: Sequence[float],
    *,
    zero_tolerance: float = 1.0e-14,
) -> tuple[np.ndarray, np.ndarray]:
    """Return Euclidean transverse and longitudinal projectors for real ``k``."""

    k = _real_vector3(wavevector, "wavevector")
    tolerance = _positive_float(zero_tolerance, "zero_tolerance")
    norm_sq = float(np.dot(k, k))
    identity = np.eye(3, dtype=np.complex128)
    if norm_sq <= tolerance**2:
        # At k=0 the curl-curl symbol vanishes on every component, so the
        # mass term acts identically.  Choosing P_T=I, P_L=0 is deterministic.
        return identity, np.zeros((3, 3), dtype=np.complex128)
    longitudinal = np.outer(k, k).astype(np.complex128) / norm_sq
    transverse = identity - longitudinal
    return transverse, longitudinal


def maxwell_fourier_symbol(
    wavevector: Sequence[float],
    *,
    mu_inv: complex,
    epsilon: complex,
    k0: float,
    shift: complex = 0.0j,
) -> np.ndarray:
    r"""Return the homogeneous Fourier symbol.

    The convention is

    ``A = mu_inv * (|k|^2 I - k k^T) - k0^2 epsilon I + shift I``.

    ``shift`` belongs only to a preconditioner; the exact physical operator
    remains unshifted.
    """

    k = _real_vector3(wavevector, "wavevector")
    mu_inv = _complex_scalar(mu_inv, "mu_inv")
    epsilon = _complex_scalar(epsilon, "epsilon")
    shift = _complex_scalar(shift, "shift")
    k0 = _positive_float(k0, "k0")
    identity = np.eye(3, dtype=np.complex128)
    curl_curl = float(np.dot(k, k)) * identity - np.outer(k, k)
    return mu_inv * curl_curl - (k0**2) * epsilon * identity + shift * identity


def maxwell_symbol_inverse(
    wavevector: Sequence[float],
    *,
    mu_inv: complex,
    epsilon: complex,
    k0: float,
    shift: complex = 0.0j,
    singular_tolerance: float = 1.0e-13,
) -> np.ndarray:
    """Return the analytic inverse using transverse/longitudinal splitting."""

    k = _real_vector3(wavevector, "wavevector")
    mu_inv = _complex_scalar(mu_inv, "mu_inv")
    epsilon = _complex_scalar(epsilon, "epsilon")
    shift = _complex_scalar(shift, "shift")
    k0 = _positive_float(k0, "k0")
    tolerance = _positive_float(singular_tolerance, "singular_tolerance")
    transverse, longitudinal = transverse_longitudinal_projectors(k)
    k_sq = float(np.dot(k, k))
    transverse_eigenvalue = mu_inv * k_sq - (k0**2) * epsilon + shift
    longitudinal_eigenvalue = -(k0**2) * epsilon + shift
    scale = max(
        abs(transverse_eigenvalue),
        abs(longitudinal_eigenvalue),
        abs(mu_inv) * max(k_sq, 1.0),
        abs(k0**2 * epsilon),
        1.0,
    )
    if (
        abs(transverse_eigenvalue) <= tolerance * scale
        or abs(longitudinal_eigenvalue) <= tolerance * scale
    ):
        raise np.linalg.LinAlgError(
            "background Maxwell symbol is singular or too close to singular; "
            "use a nonzero absorbing shift for the preconditioner"
        )
    return transverse / transverse_eigenvalue + longitudinal / longitudinal_eigenvalue


def _validated_field(field: np.ndarray) -> np.ndarray:
    values = np.asarray(field, dtype=np.complex128)
    if values.ndim != 4 or values.shape[-1] != 3:
        raise ValueError("field must have shape (nx, ny, nz, 3)")
    if any(size <= 0 for size in values.shape[:3]) or not np.all(np.isfinite(values)):
        raise ValueError("field must be finite and have nonzero spatial dimensions")
    return values


def _frequency_axes(
    shape: Sequence[int],
    box: PeriodicBox3D,
    bloch: Sequence[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lengths = box.validated_lengths()
    bloch_vector = _real_vector3(bloch, "bloch")
    return tuple(
        bloch_fft_frequencies(
            int(shape[index]),
            float(lengths[index]),
            float(bloch_vector[index]),
        )
        for index in range(3)
    )


def apply_periodic_background_operator(
    field: np.ndarray,
    *,
    box: PeriodicBox3D,
    bloch: Sequence[float],
    mu_inv: complex,
    epsilon: complex,
    k0: float,
    shift: complex = 0.0j,
) -> np.ndarray:
    """Apply the fully-periodic constant-coefficient reference operator."""

    values = _validated_field(field)
    transformed = np.fft.fftn(values, axes=(0, 1, 2))
    output_hat = np.empty_like(transformed)
    axes = _frequency_axes(values.shape[:3], box, bloch)
    for ix, kx in enumerate(axes[0]):
        for iy, ky in enumerate(axes[1]):
            for iz, kz in enumerate(axes[2]):
                symbol = maxwell_fourier_symbol(
                    (kx, ky, kz),
                    mu_inv=mu_inv,
                    epsilon=epsilon,
                    k0=k0,
                    shift=shift,
                )
                output_hat[ix, iy, iz, :] = symbol @ transformed[ix, iy, iz, :]
    return np.fft.ifftn(output_hat, axes=(0, 1, 2))


def apply_periodic_background_inverse(
    field: np.ndarray,
    *,
    box: PeriodicBox3D,
    bloch: Sequence[float],
    mu_inv: complex,
    epsilon: complex,
    k0: float,
    shift: complex = 0.0j,
    singular_tolerance: float = 1.0e-13,
) -> np.ndarray:
    """Apply the analytic inverse of the fully-periodic reference operator."""

    values = _validated_field(field)
    transformed = np.fft.fftn(values, axes=(0, 1, 2))
    output_hat = np.empty_like(transformed)
    axes = _frequency_axes(values.shape[:3], box, bloch)
    for ix, kx in enumerate(axes[0]):
        for iy, ky in enumerate(axes[1]):
            for iz, kz in enumerate(axes[2]):
                inverse = maxwell_symbol_inverse(
                    (kx, ky, kz),
                    mu_inv=mu_inv,
                    epsilon=epsilon,
                    k0=k0,
                    shift=shift,
                    singular_tolerance=singular_tolerance,
                )
                output_hat[ix, iy, iz, :] = inverse @ transformed[ix, iy, iz, :]
    return np.fft.ifftn(output_hat, axes=(0, 1, 2))


def relative_l2_error(actual: np.ndarray, expected: np.ndarray) -> float:
    """Return ``||actual-expected||_2 / max(||expected||_2, tiny)``."""

    actual_array = np.asarray(actual, dtype=np.complex128)
    expected_array = np.asarray(expected, dtype=np.complex128)
    if actual_array.shape != expected_array.shape:
        raise ValueError("actual and expected must have identical shapes")
    numerator = float(np.linalg.norm(actual_array - expected_array))
    denominator = max(float(np.linalg.norm(expected_array)), 1.0e-30)
    return numerator / denominator


def estimate_periodic_fft_working_set_bytes(
    shape: Sequence[int],
    *,
    live_complex_vectors: int = 4,
    scalar_bytes: int = 16,
) -> int:
    """Estimate the dominant vector working set for the reference FFT apply.

    This deliberately excludes FFT-library plans, MPI transpose buffers,
    metadata, and the exact operator.  It is a lower-level payload estimate,
    not a process-RSS prediction.
    """

    if len(tuple(shape)) != 3:
        raise ValueError("shape must have three spatial dimensions")
    dimensions = tuple(int(value) for value in shape)
    if any(value <= 0 for value in dimensions):
        raise ValueError("shape dimensions must be positive")
    if (
        int(live_complex_vectors) != live_complex_vectors
        or int(live_complex_vectors) <= 0
    ):
        raise ValueError("live_complex_vectors must be a positive integer")
    if int(scalar_bytes) != scalar_bytes or int(scalar_bytes) <= 0:
        raise ValueError("scalar_bytes must be a positive integer")
    dofs = int(np.prod(dimensions)) * 3
    return dofs * int(live_complex_vectors) * int(scalar_bytes)
