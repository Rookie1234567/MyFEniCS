"""Cell-local physical H(curl) error norms and deterministic Dörfler marking."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np


def _vector_values(name: str, values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"{name} must have shape (npoints, 3)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    return array


def attribute_points_to_axis_aligned_cells(
    points_nm: np.ndarray,
    axis_breakpoints_nm: tuple[np.ndarray, np.ndarray, np.ndarray],
    cell_bounds_nm: np.ndarray,
    *,
    relative_tolerance: float = 1.0e-12,
) -> np.ndarray:
    """Map points to actual axis-aligned leaves on a shared Cartesian lattice.

    Each ``cell_bounds_nm[row]`` has shape ``(2, 3)`` with lower and upper
    coordinates.  A coarse leaf may span several intervals on the union axes;
    every covered microbox is assigned to that same actual cell row.
    """

    points = np.asarray(points_nm, dtype=np.float64)
    bounds = np.asarray(cell_bounds_nm, dtype=np.float64)
    tolerance = float(relative_tolerance)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("points_nm must be a finite array with shape (npoints, 3)")
    if bounds.ndim != 3 or bounds.shape[1:] != (2, 3) or bounds.shape[0] == 0:
        raise ValueError("cell_bounds_nm must have shape (ncells, 2, 3)")
    if not np.all(np.isfinite(bounds)) or np.any(bounds[:, 1, :] <= bounds[:, 0, :]):
        raise ValueError("cell bounds must be finite with positive widths")
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("relative_tolerance must be finite and nonnegative")
    if len(axis_breakpoints_nm) != 3:
        raise ValueError("axis_breakpoints_nm must contain x, y, and z axes")

    axes: list[np.ndarray] = []
    for name, values in zip(("x", "y", "z"), axis_breakpoints_nm, strict=True):
        axis = np.asarray(values, dtype=np.float64)
        if (
            axis.ndim != 1
            or axis.size < 2
            or not np.all(np.isfinite(axis))
            or np.any(np.diff(axis) <= 0.0)
        ):
            raise ValueError(f"{name} breakpoints must be finite and strictly increasing")
        axes.append(axis)

    lattice_shape = tuple(axis.size - 1 for axis in axes)
    owners = np.full(lattice_shape, -1, dtype=np.int64)

    def breakpoint_index(axis: np.ndarray, coordinate: float) -> int:
        insertion = int(np.searchsorted(axis, coordinate))
        candidates = [index for index in (insertion - 1, insertion) if 0 <= index < axis.size]
        if not candidates:
            raise ValueError("cell bound lies outside the shared Cartesian axes")
        index = min(candidates, key=lambda candidate: abs(float(axis[candidate]) - coordinate))
        scale = max(1.0, abs(coordinate), abs(float(axis[index])))
        if abs(float(axis[index]) - coordinate) > tolerance * scale:
            raise ValueError("cell bound is absent from the shared Cartesian axes")
        return index

    for cell_index, cell_bounds in enumerate(bounds):
        slices = []
        for dimension, axis in enumerate(axes):
            lower = breakpoint_index(axis, float(cell_bounds[0, dimension]))
            upper = breakpoint_index(axis, float(cell_bounds[1, dimension]))
            if upper <= lower:
                raise ValueError("cell bounds do not span a positive lattice region")
            slices.append(slice(lower, upper))
        region = owners[tuple(slices)]
        if np.any(region >= 0):
            raise ValueError("actual cell boxes overlap on the shared Cartesian lattice")
        region[...] = cell_index

    if np.any(owners < 0):
        missing_count = int(np.count_nonzero(owners < 0))
        raise ValueError(
            f"actual cell boxes leave {missing_count} shared Cartesian microboxes uncovered"
        )

    point_intervals = tuple(
        np.searchsorted(axis, points[:, dimension], side="right") - 1
        for dimension, axis in enumerate(axes)
    )
    for dimension, (intervals, axis) in enumerate(zip(point_intervals, axes, strict=True)):
        if np.any((intervals < 0) | (intervals >= axis.size - 1)):
            raise ValueError(f"sample point falls outside the shared {('x', 'y', 'z')[dimension]} domain")
    return owners[point_intervals]


def physical_g_difference_metrics(
    reference_electric: np.ndarray,
    candidate_electric: np.ndarray,
    reference_curl_electric: np.ndarray,
    candidate_curl_electric: np.ndarray,
    weights_nm3: np.ndarray,
    *,
    k0_per_nm: float,
    incident_g_norm_floor: float,
) -> dict[str, float | bool | None]:
    """Measure a full-volume ``E + curl(E)/k0`` difference without phase fitting."""

    ref_e = _vector_values("reference_electric", reference_electric)
    cand_e = _vector_values("candidate_electric", candidate_electric)
    ref_curl = _vector_values("reference_curl_electric", reference_curl_electric)
    cand_curl = _vector_values("candidate_curl_electric", candidate_curl_electric)
    weights = np.asarray(weights_nm3, dtype=np.float64)
    if any(values.shape != ref_e.shape for values in (cand_e, ref_curl, cand_curl)):
        raise ValueError("all electric and curl arrays must have matching shapes")
    if weights.ndim != 1 or weights.size != ref_e.shape[0]:
        raise ValueError("weights_nm3 must have one value per sample")
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("weights_nm3 must be finite and positive")
    k0 = float(k0_per_nm)
    floor = float(incident_g_norm_floor)
    if not np.isfinite(k0) or k0 <= 0.0:
        raise ValueError("k0_per_nm must be finite and positive")
    if not np.isfinite(floor) or floor < 0.0:
        raise ValueError("incident_g_norm_floor must be finite and nonnegative")

    def norm(electric: np.ndarray, curl: np.ndarray) -> float:
        density = np.sum(
            np.abs(electric) ** 2 + np.abs(curl / k0) ** 2,
            axis=1,
        )
        return float(np.sqrt(np.dot(weights, density)))

    reference_norm = norm(ref_e, ref_curl)
    candidate_norm = norm(cand_e, cand_curl)
    difference_norm = norm(cand_e - ref_e, cand_curl - ref_curl)
    raw_defined = reference_norm > 0.0
    raw_relative = difference_norm / reference_norm if raw_defined else None
    denominator = max(reference_norm, floor)
    floor_relative = difference_norm / denominator if denominator > 0.0 else None
    return {
        "reference_g_norm": reference_norm,
        "candidate_g_norm": candidate_norm,
        "difference_g_norm": difference_norm,
        "relative_to_reference": raw_relative,
        "relative_to_reference_defined": raw_defined,
        "relative_with_incident_floor": floor_relative,
        "incident_g_norm_floor": floor,
    }


def accumulate_physical_g_cell_contributions(
    reference_electric: np.ndarray,
    candidate_electric: np.ndarray,
    reference_curl_electric: np.ndarray,
    candidate_curl_electric: np.ndarray,
    weights_nm3: np.ndarray,
    point_local_cell_indices: np.ndarray,
    *,
    cell_global_ids: np.ndarray,
    k0_per_nm: float,
) -> np.ndarray:
    """Integrate squared ``G`` field differences and sum them by actual mesh cell.

    ``point_local_cell_indices`` maps each common-volume Gauss point to a row
    of ``cell_global_ids``.  The caller obtains that map from the actual mesh
    leaves; the axes used by the common quadrature do not define solver cells.
    """

    ref_e = _vector_values("reference_electric", reference_electric)
    cand_e = _vector_values("candidate_electric", candidate_electric)
    ref_curl = _vector_values("reference_curl_electric", reference_curl_electric)
    cand_curl = _vector_values("candidate_curl_electric", candidate_curl_electric)
    weights = np.asarray(weights_nm3, dtype=np.float64)
    local_cells = np.asarray(point_local_cell_indices)
    global_ids = np.asarray(cell_global_ids, dtype=np.int64)
    if any(values.shape != ref_e.shape for values in (cand_e, ref_curl, cand_curl)):
        raise ValueError("all electric and curl arrays must have matching shapes")
    if weights.shape != (ref_e.shape[0],) or not np.all(np.isfinite(weights)):
        raise ValueError("weights_nm3 must be a finite vector with one entry per point")
    if np.any(weights <= 0.0):
        raise ValueError("weights_nm3 must be positive")
    if local_cells.shape != weights.shape or local_cells.dtype.kind not in "iu":
        raise ValueError("point_local_cell_indices must be an integer per sample")
    if global_ids.ndim != 1 or np.unique(global_ids).size != global_ids.size:
        raise ValueError("cell_global_ids must be a unique one-dimensional array")
    if local_cells.size and (local_cells.min() < 0 or local_cells.max() >= global_ids.size):
        raise ValueError("point_local_cell_indices are outside cell_global_ids")
    k0 = float(k0_per_nm)
    if not np.isfinite(k0) or k0 <= 0.0:
        raise ValueError("k0_per_nm must be finite and positive")

    electric_delta = cand_e - ref_e
    curl_delta = (cand_curl - ref_curl) / k0
    density = np.sum(np.abs(electric_delta) ** 2 + np.abs(curl_delta) ** 2, axis=1)
    contributions = np.bincount(
        local_cells.astype(np.int64, copy=False),
        weights=weights * density,
        minlength=global_ids.size,
    ).astype(np.float64, copy=False)
    if contributions.shape != global_ids.shape or not np.all(np.isfinite(contributions)):
        raise FloatingPointError("cell G contributions are not finite or have invalid shape")
    return contributions


def dorfler_mark_physical_g(
    cell_global_ids: np.ndarray,
    contributions: np.ndarray,
    *,
    theta: float = 0.5,
    tie_relative_tolerance: float = 1.0e-10,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return the smallest stable cell set capturing ``theta`` of G-error².

    Contributions are ordered descending, with global cell ID as a stable
    secondary key.  Cells within ``tie_relative_tolerance`` of the cutoff are
    included together so tiny summation differences cannot arbitrarily split
    a symmetric tie.
    """

    ids = np.asarray(cell_global_ids, dtype=np.int64)
    values = np.asarray(contributions, dtype=np.float64)
    theta_value = float(theta)
    tie_tolerance = float(tie_relative_tolerance)
    if ids.ndim != 1 or values.shape != ids.shape:
        raise ValueError("cell IDs and contributions must be matching one-dimensional arrays")
    if np.unique(ids).size != ids.size:
        raise ValueError("cell_global_ids must be unique")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("Dörfler contributions must be finite and nonnegative")
    if not np.isfinite(theta_value) or not 0.0 < theta_value <= 1.0:
        raise ValueError("theta must lie in (0, 1]")
    if not np.isfinite(tie_tolerance) or tie_tolerance < 0.0:
        raise ValueError("tie_relative_tolerance must be finite and nonnegative")

    total = float(np.sum(values, dtype=np.float64))
    if total == 0.0:
        marked = np.empty(0, dtype=np.int64)
        minimal_count = 0
        cutoff_normalized = 0.0
        tie_count = 0
        captured = 0.0
    else:
        order = np.lexsort((ids, -values))
        normalized = values[order] / total
        minimal_count = int(np.searchsorted(np.cumsum(normalized), theta_value, side="left") + 1)
        cutoff_normalized = float(normalized[minimal_count - 1])
        count = minimal_count
        cutoff_tolerance = max(
            tie_tolerance * abs(cutoff_normalized),
            64.0 * np.finfo(np.float64).eps,
        )
        while count < len(order) and cutoff_normalized - float(normalized[count]) <= cutoff_tolerance:
            count += 1
        chosen = order[:count]
        marked = np.sort(ids[chosen])
        tie_count = count - minimal_count
        captured = float(np.sum(values[chosen], dtype=np.float64) / total)

    digest = hashlib.sha256(marked.astype("<i8", copy=False).tobytes()).hexdigest()
    return marked, {
        "theta": theta_value,
        "total_g_error_squared": total,
        "marked_g_error_squared": float(captured * total),
        "captured_fraction": captured,
        "count": int(marked.size),
        "minimal_count_before_tie_expansion": minimal_count,
        "cutoff_tie_expansion_count": tie_count,
        "cutoff_normalized_contribution": cutoff_normalized,
        "tie_policy": f"include_within_relative_{tie_tolerance:g}_of_cutoff",
        "marked_global_cell_ids_sha256": digest,
    }
