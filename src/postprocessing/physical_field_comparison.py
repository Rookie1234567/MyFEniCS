"""Shared, mesh-aware quadrature and metrics for physical field comparisons.

The quadrature partition is built from the union of coordinate breakpoints of
every mesh in a comparison.  This keeps piecewise-polynomial field evaluation
inside one element per box even when reference and candidate meshes have
different partitions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

_AXIS_NAMES = ("x", "y", "z")
_RULE_VERSION = "common-volume-tensor-gauss-v1"


@dataclass(frozen=True)
class CommonVolumeQuadrature:
    """Tensor Gauss rule over the common Cartesian partition, with lengths in nm."""

    points_nm: np.ndarray
    weights_nm3: np.ndarray
    axis_breakpoints_nm: tuple[np.ndarray, np.ndarray, np.ndarray]
    gauss_order: int
    subdivisions_per_interval: int
    rule_sha256: str

    @property
    def point_count(self) -> int:
        return int(self.weights_nm3.size)

    @property
    def partition_box_count(self) -> int:
        return int(
            np.prod(
                [
                    (len(axis) - 1) * self.subdivisions_per_interval
                    for axis in self.axis_breakpoints_nm
                ]
            )
        )


def _coerce_axes(axis_set: Sequence[Sequence[float]] | Mapping[str, Sequence[float]]) -> tuple[np.ndarray, ...]:
    if isinstance(axis_set, Mapping):
        try:
            raw = tuple(axis_set[name] for name in _AXIS_NAMES)
        except KeyError as exc:
            raise ValueError("axis mapping must contain x, y, and z") from exc
    else:
        if len(axis_set) != 3:
            raise ValueError("an axis set must contain exactly x, y, and z arrays")
        raw = tuple(axis_set)

    axes: list[np.ndarray] = []
    for name, values in zip(_AXIS_NAMES, raw, strict=True):
        axis = np.asarray(values, dtype=np.float64)
        if axis.ndim != 1 or axis.size < 2:
            raise ValueError(f"{name} axis must be one-dimensional with at least two points")
        if not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0.0):
            raise ValueError(f"{name} axis must be finite and strictly increasing")
        axes.append(axis)
    return tuple(axes)


def _merge_breakpoints(
    axes_by_mesh: Sequence[tuple[np.ndarray, ...]], *, relative_tolerance: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    merged_axes: list[np.ndarray] = []
    for axis_index, name in enumerate(_AXIS_NAMES):
        vectors = [axes[axis_index] for axes in axes_by_mesh]
        lower = float(vectors[0][0])
        upper = float(vectors[0][-1])
        scale = max(1.0, abs(lower), abs(upper))
        tolerance = relative_tolerance * scale
        for vector in vectors[1:]:
            if abs(float(vector[0]) - lower) > tolerance or abs(float(vector[-1]) - upper) > tolerance:
                raise ValueError(f"all comparison meshes must share the same {name} domain")

        sorted_values = np.sort(np.concatenate(vectors))
        unique = [float(sorted_values[0])]
        for value in sorted_values[1:]:
            number = float(value)
            local_tolerance = relative_tolerance * max(1.0, abs(number), abs(unique[-1]))
            if number - unique[-1] > local_tolerance:
                unique.append(number)

        values = np.asarray(unique, dtype=np.float64)
        endpoint_tolerance = relative_tolerance * scale
        if values.size < 2 or abs(values[0] - lower) > endpoint_tolerance or abs(values[-1] - upper) > endpoint_tolerance:
            raise ValueError(f"could not construct a valid common {name} partition")
        # Use the first mesh's exact outer coordinates as the shared domain.
        values[0] = lower
        values[-1] = upper
        if np.any(np.diff(values) <= 0.0):
            raise ValueError(f"merged {name} breakpoints are not strictly increasing")
        merged_axes.append(values)
    return tuple(merged_axes)


def build_common_volume_quadrature(
    mesh_axes: Sequence[Sequence[Sequence[float]] | Mapping[str, Sequence[float]]],
    *,
    gauss_order: int = 8,
    subdivisions_per_interval: int = 1,
    breakpoint_relative_tolerance: float = 1.0e-12,
) -> CommonVolumeQuadrature:
    """Build a shared high-order volume rule over the union of mesh breakpoints.

    ``mesh_axes`` contains one ``(x, y, z)`` axis triple (or named mapping) for
    each mesh being compared, including every reference mesh.  Each resulting
    Cartesian box lies within one interval from every supplied mesh.  Further
    subdivision changes only the integration rule and never changes a solve
    mesh.
    """

    if not mesh_axes:
        raise ValueError("at least one mesh axis set is required")
    if int(gauss_order) != gauss_order or gauss_order < 1:
        raise ValueError("gauss_order must be a positive integer")
    if int(subdivisions_per_interval) != subdivisions_per_interval or subdivisions_per_interval < 1:
        raise ValueError("subdivisions_per_interval must be a positive integer")
    if not np.isfinite(breakpoint_relative_tolerance) or breakpoint_relative_tolerance < 0.0:
        raise ValueError("breakpoint_relative_tolerance must be finite and nonnegative")

    normalized = [_coerce_axes(axis_set) for axis_set in mesh_axes]
    common_axes = _merge_breakpoints(
        normalized, relative_tolerance=float(breakpoint_relative_tolerance)
    )

    one_d_nodes: list[np.ndarray] = []
    one_d_weights: list[np.ndarray] = []
    reference_nodes, reference_weights = np.polynomial.legendre.leggauss(int(gauss_order))
    for axis in common_axes:
        split_points = [axis[0]]
        for left, right in pairwise(axis):
            split_points.extend(
                np.linspace(left, right, int(subdivisions_per_interval) + 1, dtype=np.float64)[1:].tolist()
            )
        split_axis = np.asarray(split_points, dtype=np.float64)
        interval_nodes = []
        interval_weights = []
        for left, right in pairwise(split_axis):
            half_width = 0.5 * (right - left)
            midpoint = 0.5 * (right + left)
            interval_nodes.append(midpoint + half_width * reference_nodes)
            interval_weights.append(half_width * reference_weights)
        one_d_nodes.append(np.concatenate(interval_nodes))
        one_d_weights.append(np.concatenate(interval_weights))

    x_nodes, y_nodes, z_nodes = one_d_nodes
    x_weights, y_weights, z_weights = one_d_weights
    xx, yy, zz = np.meshgrid(x_nodes, y_nodes, z_nodes, indexing="ij", copy=False)
    points = np.column_stack((xx.reshape(-1), yy.reshape(-1), zz.reshape(-1)))
    weights = np.einsum("i,j,k->ijk", x_weights, y_weights, z_weights, optimize=True).reshape(-1)

    digest = hashlib.sha256()
    digest.update(_RULE_VERSION.encode("ascii"))
    digest.update(np.asarray([int(gauss_order), int(subdivisions_per_interval)], dtype="<i8").tobytes())
    for axis in common_axes:
        canonical_axis = np.asarray(axis, dtype="<f8")
        digest.update(np.asarray([canonical_axis.size], dtype="<i8").tobytes())
        digest.update(canonical_axis.tobytes())

    return CommonVolumeQuadrature(
        points_nm=points,
        weights_nm3=weights,
        axis_breakpoints_nm=common_axes,
        gauss_order=int(gauss_order),
        subdivisions_per_interval=int(subdivisions_per_interval),
        rule_sha256=digest.hexdigest(),
    )


def weighted_vector_field_metrics(
    reference_values: np.ndarray,
    candidate_values: np.ndarray,
    weights: np.ndarray,
    *,
    reference_norm_floor: float = 0.0,
) -> dict[str, float | bool | None]:
    """Compute physical L2 field metrics without any fitted phase rotation."""

    reference = np.asarray(reference_values, dtype=np.complex128)
    candidate = np.asarray(candidate_values, dtype=np.complex128)
    quadrature_weights = np.asarray(weights, dtype=np.float64)
    if reference.ndim != 2 or candidate.shape != reference.shape:
        raise ValueError("reference and candidate fields must have matching (npoints, ncomponents) shapes")
    if quadrature_weights.ndim != 1 or quadrature_weights.size != reference.shape[0]:
        raise ValueError("weights must have one entry per field sample")
    if not np.all(np.isfinite(reference)) or not np.all(np.isfinite(candidate)):
        raise ValueError("field samples must be finite")
    if not np.all(np.isfinite(quadrature_weights)) or np.any(quadrature_weights <= 0.0):
        raise ValueError("quadrature weights must be finite and positive")
    if not np.isfinite(reference_norm_floor) or reference_norm_floor < 0.0:
        raise ValueError("reference_norm_floor must be finite and nonnegative")

    difference = candidate - reference

    def l2(values: np.ndarray) -> float:
        density = np.sum(np.abs(values) ** 2, axis=1)
        return float(np.sqrt(np.dot(quadrature_weights, density)))

    reference_norm = l2(reference)
    candidate_norm = l2(candidate)
    difference_norm = l2(difference)
    reference_defined = reference_norm > 0.0
    relative_to_reference = difference_norm / reference_norm if reference_defined else None
    denominator = max(reference_norm, float(reference_norm_floor))
    relative_to_reference_or_floor = difference_norm / denominator if denominator > 0.0 else None
    return {
        "reference_l2": reference_norm,
        "candidate_l2": candidate_norm,
        "difference_l2": difference_norm,
        "relative_to_reference": relative_to_reference,
        "relative_to_reference_defined": reference_defined,
        "relative_to_reference_or_floor": relative_to_reference_or_floor,
        "reference_norm_floor": float(reference_norm_floor),
    }


def scattered_field_samples(total_values: np.ndarray, fixed_background_values: np.ndarray) -> np.ndarray:
    """Subtract one explicitly supplied background field, with no fitted phase."""

    total = np.asarray(total_values, dtype=np.complex128)
    background = np.asarray(fixed_background_values, dtype=np.complex128)
    if total.shape != background.shape:
        raise ValueError("total and fixed background samples must have identical shapes")
    if not np.all(np.isfinite(total)) or not np.all(np.isfinite(background)):
        raise ValueError("total and fixed background samples must be finite")
    return total - background


def magnetic_field_from_electric_curl(
    curl_e_code: np.ndarray,
    *,
    magnetic_field_scale_A_per_m: float,
    k0_per_nm: float,
    mu_r: complex,
) -> np.ndarray:
    """Convert the solver's code-unit curl(E) to physical H in A/m."""

    curl_values = np.asarray(curl_e_code, dtype=np.complex128)
    mu = complex(mu_r)
    scale = float(magnetic_field_scale_A_per_m)
    wave_number = float(k0_per_nm)
    if curl_values.ndim != 2 or curl_values.shape[1] != 3:
        raise ValueError("curl_e_code must have shape (npoints, 3)")
    if not np.all(np.isfinite(curl_values)):
        raise ValueError("curl_e_code must be finite")
    if not np.isfinite(scale) or not np.isfinite(wave_number) or wave_number <= 0.0:
        raise ValueError("magnetic scale must be finite and k0_per_nm must be positive")
    if not np.isfinite(mu.real) or not np.isfinite(mu.imag) or abs(mu) == 0.0:
        raise ValueError("mu_r must be finite and nonzero")
    return (scale / (1j * wave_number * mu)) * curl_values
