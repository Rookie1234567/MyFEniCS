"""Bounded full-882-row point-chunk and modal-batch boundary action.

This helper applies one axis-aligned p6 hexahedron face to a saved local
coefficient vector. It keeps both tangential components and every native row,
uses the actual Basix cell orientation, and streams modal output as one scalar
per selected original mode. It does not construct a mode-by-face coefficient
matrix or a mode-square operator.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


_CELL_DOFS = 882
_MAX_POINT_CHUNK = 256
_MAX_MODE_BATCH = 64


def _complex_values(values: Sequence[Any], length: int, label: str) -> np.ndarray:
    out = np.asarray(
        [complex(value["real"], value["imag"]) if isinstance(value, Mapping) else complex(value)
         for value in values],
        dtype=np.complex128,
    )
    if out.shape != (length,) or not np.isfinite(out).all():
        raise ValueError(f"{label} must contain {length} finite complex values")
    return out


def _apply_dof_orientation(dof_element: Any, vector: np.ndarray, cell_info: Any) -> None:
    """Apply the caller's real cell permutation to one complete native vector."""
    transform = getattr(dof_element, "T_apply", None)
    if not callable(transform):
        raise ValueError("the actual finite element must provide T_apply")
    transform(vector, cell_info, 1)


def full882_chunked_boundary_action(
    *,
    element: Any,
    dof_element: Any,
    cell_info: Any,
    coordinates: np.ndarray,
    side: str,
    modes: Sequence[Mapping[str, Any]],
    selected_indices: Sequence[int],
    mode_alpha: np.ndarray,
    local_coefficients: np.ndarray,
    quadrature_degree: int = 30,
    point_chunk_size: int = 64,
    mode_batch_size: int = 16,
) -> dict[str, Any]:
    """Compute ``B alpha`` and selected ``D x`` actions with fixed-size blocks.

    ``B_jm = integral(phi_j dot -traction_m * exp(+i k_m dot x))`` and
    ``D_mj = conj(integral(phi_j dot e_m * exp(+i k_m dot x))) / H_m``.
    The physical tangential Piola factors are ``(dy, dx)`` for the reference
    ``(x, y)`` components. The cell origin is included directly in every
    phase evaluation; no fitted phase correction is used.

    The result contains one full 882-entry ``B alpha`` vector and one scalar
    ``D x`` result per selected original mode. At no point is a
    ``mode_count x 882`` or ``mode_count x mode_count`` array formed.
    """
    import basix

    if side not in ("top", "bottom"):
        raise ValueError("side must be top or bottom")
    for value, label, upper in (
        (quadrature_degree, "quadrature_degree", 256),
        (point_chunk_size, "point_chunk_size", _MAX_POINT_CHUNK),
        (mode_batch_size, "mode_batch_size", _MAX_MODE_BATCH),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
            raise ValueError(f"{label} must be an integer in [1, {upper}]")
    if int(getattr(element, "degree", -1)) != 6 or int(getattr(element, "dim", -1)) != _CELL_DOFS:
        raise ValueError("full native p6 N1E element with exactly 882 rows is required")

    xyz = np.asarray(coordinates, dtype=np.float64)
    if xyz.shape != (8, 3) or not np.isfinite(xyz).all():
        raise ValueError("coordinates must be the saved finite eight-vertex cell")
    lower, upper = xyz.min(axis=0), xyz.max(axis=0)
    extent = upper - lower
    if np.any(extent <= 0):
        raise ValueError("cell extents must be positive")
    normalized = (xyz - lower) / extent
    rounded = np.rint(normalized)
    distinct_nodes = np.unique(rounded.astype(np.int8), axis=0)
    if (not np.allclose(normalized, rounded, rtol=0.0, atol=2e-12)
            or len(distinct_nodes) != 8):
        raise ValueError("the saved representative cell must be axis-aligned affine")
    del normalized, rounded, distinct_nodes
    dx, dy, dz = (float(v) for v in extent)
    zref = 0.0 if side == "bottom" else 1.0

    alpha = np.asarray(mode_alpha)
    if alpha.shape != (len(modes),) or alpha.dtype != np.complex128 or not np.isfinite(alpha).all():
        raise ValueError("mode_alpha must be finite complex128 in frozen manifest order")
    coeff = np.asarray(local_coefficients)
    if coeff.shape != (_CELL_DOFS,) or coeff.dtype != np.complex128 or not np.isfinite(coeff).all():
        raise ValueError("local_coefficients must be finite complex128 on all 882 native rows")
    indices = np.asarray(selected_indices, dtype=np.int64)
    if (indices.ndim != 1 or indices.size == 0 or np.any(indices < 0)
            or np.any(indices >= len(modes)) or len(np.unique(indices)) != len(indices)):
        raise ValueError("selected_indices must be nonempty unique indices in the frozen inventory")
    if any(modes[int(i)].get("side") != side for i in indices):
        raise ValueError("all selected modes must belong to the requested physical side")
    alpha_selected = np.asarray(alpha[indices], dtype=np.complex128)
    conjugated_coefficients = np.conjugate(coeff)

    k = np.empty((len(indices), 3), dtype=np.complex128)
    electric = np.empty((len(indices), 2), dtype=np.complex128)
    traction = np.empty((len(indices), 2), dtype=np.complex128)
    h = np.empty(len(indices), dtype=np.float64)
    for local_i, original_i in enumerate(indices):
        row = modes[int(original_i)]
        k[local_i] = _complex_values(row.get("k_vector", ()), 3, "k_vector")
        electric[local_i] = _complex_values(row.get("e_vector", ()), 3, "e_vector")[:2]
        traction[local_i] = _complex_values(row.get("traction_vector", ()), 3, "traction_vector")[:2]
        h[local_i] = float(row.get("projection_denominator", np.nan))
    if not np.isfinite(h).all() or np.any(h <= 0):
        raise ValueError("each selected mode must have a finite positive original H denominator")

    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, quadrature_degree)
    rule = np.asarray(rule, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if (rule.ndim != 2 or rule.shape[1] != 2 or weights.shape != (len(rule),)
            or not np.isfinite(rule).all() or not np.isfinite(weights).all()):
        raise ValueError("Basix quadrilateral rule is malformed")

    b_alpha = np.zeros(_CELL_DOFS, dtype=np.complex128)
    d_action = np.zeros(len(indices), dtype=np.complex128)
    indices_out = indices.copy()
    fixed_helper_owned_bytes_upper = int(
        xyz.nbytes + lower.nbytes + upper.nbytes + extent.nbytes
        + k.nbytes + electric.nbytes + traction.nbytes + h.nbytes
        + alpha_selected.nbytes + conjugated_coefficients.nbytes
        + indices.nbytes + indices_out.nbytes + rule.nbytes + weights.nbytes
        + b_alpha.nbytes + d_action.nbytes
        + 8 * 3 * 16  # per-mode complex-vector parse scratch, conservatively
        + 8 * 3 * (16 + 8) + 512  # geometry validation scratch upper bound
    )
    basis_tabulations = 0
    mode_batch_passes = 0
    max_basis_chunk_bytes = 0
    max_phase_chunk_bytes = 0
    max_point_count = min(point_chunk_size, len(rule))
    max_mode_count = min(mode_batch_size, len(indices))
    complex_bytes = np.dtype(np.complex128).itemsize
    real_bytes = np.dtype(np.float64).itemsize
    # Bound helper-owned chunk arrays at the configured maxima. The Basix
    # tabulation term assumes complex128 for all three value components, even
    # when the returned table is real; geometry construction includes both
    # the physical point result and its short-lived expression temporary.
    point_chunk_bytes_upper = int(
        max_point_count * _CELL_DOFS * 3 * complex_bytes
        + max_point_count * _CELL_DOFS * 2 * complex_bytes
        + _CELL_DOFS * complex_bytes  # last orientation row_values copy
        + max_point_count * 3 * real_bytes  # reference points
        + 2 * max_point_count * 3 * real_bytes  # physical points + expression temporary
        + max_point_count * 2 * complex_bytes  # field values
        + 2 * max_point_count * complex_bytes  # accumulated traction weights
    )
    mode_batch_bytes_upper = int(
        max_point_count * max_mode_count * complex_bytes  # phase block
        + 2 * max_mode_count * complex_bytes  # traction factors
        + 4 * max_mode_count * complex_bytes  # D outputs and one arithmetic temporary
        + max_point_count * complex_bytes  # modal contraction result
    )
    boundary_accumulation_bytes_upper = int(
        max_point_count * complex_bytes  # weighted quadrature values
        + 2 * _CELL_DOFS * complex_bytes  # moment and scaled-moment vectors
    )
    max_owned_chunk_bytes = point_chunk_bytes_upper + max(
        mode_batch_bytes_upper, boundary_accumulation_bytes_upper
    )
    for point_start in range(0, len(rule), point_chunk_size):
        point_stop = min(point_start + point_chunk_size, len(rule))
        qrule = rule[point_start:point_stop]
        qweights = weights[point_start:point_stop]
        reference_points = np.column_stack((qrule, np.full(len(qrule), zref)))
        tabulated = np.asarray(element.tabulate(0, reference_points)[0])
        if tabulated.shape != (len(qrule), _CELL_DOFS, 3) or not np.isfinite(tabulated).all():
            raise ValueError("Basix full-882 tangential tabulation has the wrong shape or nonfinite values")
        # Copy only this fixed point chunk. Applying T to each point/component
        # makes the same local orientation act on both primal evaluation and
        # dual accumulation, without forming a dense transformation matrix.
        basis = np.ascontiguousarray(tabulated[:, :, :2], dtype=np.complex128)
        for q in range(len(qrule)):
            for component in (0, 1):
                row_values = np.ascontiguousarray(basis[q, :, component])
                _apply_dof_orientation(dof_element, row_values, cell_info)
                basis[q, :, component] = row_values
        physical_points = lower + reference_points * extent
        field_values = np.einsum(
            "qjc,j->qc", basis, conjugated_coefficients, optimize=False
        )
        weighted_traction_x = np.zeros(len(qrule), dtype=np.complex128)
        weighted_traction_y = np.zeros(len(qrule), dtype=np.complex128)

        for mode_start in range(0, len(indices), mode_batch_size):
            mode_stop = min(mode_start + mode_batch_size, len(indices))
            block = slice(mode_start, mode_stop)
            phases = k[block] @ physical_points.T
            phases *= 1j
            with np.errstate(over="raise", invalid="raise"):
                np.exp(phases, out=phases)
            if not np.isfinite(phases).all():
                raise FloatingPointError("nonfinite actual top/bottom phase")
            factor_x = np.empty(mode_stop - mode_start, dtype=np.complex128)
            factor_y = np.empty(mode_stop - mode_start, dtype=np.complex128)
            np.multiply(alpha_selected[block], traction[block, 0], out=factor_x)
            np.multiply(alpha_selected[block], traction[block, 1], out=factor_y)
            factor_x *= -1.0
            factor_y *= -1.0
            weighted_traction_x += np.einsum(
                "mq,m->q", phases, factor_x, optimize=False
            )
            weighted_traction_y += np.einsum(
                "mq,m->q", phases, factor_y, optimize=False
            )

            d_x = np.einsum(
                "mq,q,q,m->m", phases, qweights, field_values[:, 0], electric[block, 0],
                optimize=False,
            )
            d_y = np.einsum(
                "mq,q,q,m->m", phases, qweights, field_values[:, 1], electric[block, 1],
                optimize=False,
            )
            d_total = dy * d_x
            d_total += dx * d_y
            np.conjugate(d_total, out=d_total)
            d_total /= h[block]
            d_action[block] += d_total
            mode_batch_passes += 1
            max_phase_chunk_bytes = max(max_phase_chunk_bytes, int(phases.nbytes))
            del phases, factor_x, factor_y, d_x, d_y, d_total

        b_alpha += dy * (basis[:, :, 0].T @ (qweights * weighted_traction_x))
        b_alpha += dx * (basis[:, :, 1].T @ (qweights * weighted_traction_y))
        basis_tabulations += 1
        max_basis_chunk_bytes = max(max_basis_chunk_bytes, int(basis.nbytes))
        del (tabulated, basis, row_values, reference_points, physical_points,
             field_values, weighted_traction_x, weighted_traction_y, qrule, qweights)

    if not np.isfinite(b_alpha).all() or not np.isfinite(d_action).all():
        raise FloatingPointError("nonfinite full-882 boundary action")
    return {
        "side": side,
        "selected_indices": indices_out,
        "b_alpha": b_alpha,
        "d_action": d_action,
        "work": {
            "full_native_row_count": _CELL_DOFS,
            "tangential_components": [0, 1],
            "quadrature_degree": quadrature_degree,
            "quadrature_point_count": int(len(rule)),
            "point_chunk_size": point_chunk_size,
            "point_chunk_count": int((len(rule) + point_chunk_size - 1) // point_chunk_size),
            "mode_batch_size": mode_batch_size,
            "mode_batch_passes": mode_batch_passes,
            "selected_mode_count": int(len(indices)),
            "basis_tabulations": basis_tabulations,
            "max_basis_chunk_bytes": max_basis_chunk_bytes,
            "max_phase_chunk_bytes": max_phase_chunk_bytes,
            "max_point_mode_chunk_array_bytes_upper": max_owned_chunk_bytes,
            "fixed_helper_owned_array_bytes_upper": fixed_helper_owned_bytes_upper,
            "conservative_helper_owned_array_bytes_upper": (
                fixed_helper_owned_bytes_upper + max_owned_chunk_bytes
            ),
            "memory_scope": (
                "conservative bound for arrays owned by this helper only; excludes input mode objects, "
                "caller-owned alpha/coefficients, Python/runtime, internal Basix/NumPy/BLAS allocations, "
                "PETSc, and process-tree RSS"
            ),
            "full_mode_by_face_map_retained": False,
            "mode_square_matrix_allocated": False,
            "phase_formula": "exp(+i*(kx*x + ky*y + kz*z)) at actual mapped quadrature points",
            "h_convention": "D_m = conj(integral(phi dot e_m exp(+i*k_m dot x) dS)) / H_m",
            "piola_tangential_area_factors": [dy, dx],
        },
    }
