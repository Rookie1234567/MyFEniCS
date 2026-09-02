"""Task040 L1b: fixed p6/LOR x-y periodic reference mechanism.

This is a small NumPy/SciPy reference for one unit box.  It quotients only
the x and y boundaries, applies the two fixed Bloch phases once, and keeps
the full-to-quotient maps explicit.  It is not a PETSc, MPI, DOLFINx, or
production LOR solver.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from scipy.linalg import eigh
from scipy.sparse import csr_matrix

from src.solvers.hcurl_fixed_lor import FixedP6LORReferenceComplex
from src.solvers.hcurl_fixed_lor_action import (
    FixedP6LORReferenceAction,
    build_fixed_p6_lor_reference_action,
)

__all__ = (
    "FixedP6LORXYFloquetReferenceAction",
    "build_fixed_p6_lor_xy_floquet_reference_action",
)


_N = 6
_N1 = _N + 1
_FULL_VERTICES = _N1**3
_REDUCED_VERTICES = _N * _N * _N1
_FULL_EDGES = 3 * _N * _N1**2
_REDUCED_EDGES = 2 * _N * _N * _N1 + _N * _N * _N
_PHASE_X = complex(np.exp(0.17j))
_PHASE_Y = complex(np.exp(-0.09j))
_ORIENTATION_TOL = 2.0e-12
_ACTION_TOL = 1.0e-10
_ADJOINT_TOL = 2.0e-11
_COMMUTING_TOL = 2.0e-10
_TINY = np.finfo(np.float64).tiny

Key3 = tuple[int, int, int]
EdgeKey = tuple[str, int, int, int]


@dataclass(frozen=True)
class FixedP6LORXYFloquetReferenceAction:
    """Fixed p6/LOR action data after an x-y Bloch quotient."""

    l1a_action: FixedP6LORReferenceAction
    Q0: csr_matrix
    Q1: csr_matrix
    G_reduced: csr_matrix
    full_vertex_to_reduced_row: np.ndarray
    full_vertex_phase: np.ndarray
    full_edge_to_reduced_row: np.ndarray
    full_edge_phase: np.ndarray
    reduced_lor_operator: csr_matrix
    audit: dict[str, Any]

    def lift_vertices(self, vector: np.ndarray) -> np.ndarray:
        """Lift reduced vertex values to full vertices with Bloch phases."""

        return np.asarray(self.Q0 @ _as_vector(vector, _REDUCED_VERTICES))

    def lift_edges(self, vector: np.ndarray) -> np.ndarray:
        """Lift reduced LOR edge values to full edge values."""

        return np.asarray(self.Q1 @ _as_vector(vector, _REDUCED_EDGES))

    def restrict_vertices(self, vector: np.ndarray) -> np.ndarray:
        """Apply the conjugate-transpose vertex quotient map."""

        return np.asarray(self.Q0.conj().T @ _as_vector(vector, _FULL_VERTICES))

    def restrict_edges(self, vector: np.ndarray) -> np.ndarray:
        """Apply the conjugate-transpose edge quotient map."""

        return np.asarray(self.Q1.conj().T @ _as_vector(vector, _FULL_EDGES))

    def apply_lor_streamed(self, vector: np.ndarray) -> np.ndarray:
        """Apply the reduced LOR action by streamed signed cell scatters."""

        values = _as_vector(vector, _REDUCED_EDGES)
        result = np.zeros(_REDUCED_EDGES, dtype=np.complex128)
        rows = self.l1a_action.cell_rows
        signs = self.l1a_action.cell_signs.astype(np.float64)
        tensor = self.l1a_action.cell_local_tensor
        for cell_rows, cell_signs in zip(rows, signs, strict=True):
            reduced_rows = self.full_edge_to_reduced_row[cell_rows]
            phases = self.full_edge_phase[cell_rows]
            local_input = cell_signs * phases * values[reduced_rows]
            local_output = tensor @ local_input
            result[reduced_rows] += np.conj(phases) * cell_signs * local_output
        return result

    def apply_galerkin(self, vector: np.ndarray) -> np.ndarray:
        """Apply ``Q1ᴴ T1ᴴ Ap T1 Q1`` without forming a reduced dense matrix."""

        values = _as_vector(vector, _REDUCED_EDGES)
        full_edges = self.Q1 @ values
        p6_values = self.l1a_action.T1 @ full_edges
        p6_output = self.l1a_action.p6_operator @ p6_values
        full_output = self.l1a_action.T1.conj().T @ p6_output
        return np.asarray(self.Q1.conj().T @ full_output)


def _as_vector(vector: np.ndarray, size: int) -> np.ndarray:
    values = np.asarray(vector, dtype=np.complex128)
    if values.shape != (size,):
        raise ValueError(f"expected vector shape {(size,)}, got {values.shape}")
    return values


def _vertex_id(i: int, j: int, k: int) -> int:
    return int(i + _N1 * (j + _N1 * k))


def _reduced_vertex_id(i: int, j: int, k: int) -> int:
    return int((i % _N) + _N * ((j % _N) + _N * k))


def _phase(i: int, j: int) -> complex:
    return (_PHASE_X if i == _N else 1.0 + 0.0j) * (
        _PHASE_Y if j == _N else 1.0 + 0.0j
    )


def _edge_axis_ranges(axis: str, reduced: bool) -> tuple[range, range, range]:
    if axis == "x":
        return range(_N), range(_N if reduced else _N1), range(_N1)
    if axis == "y":
        return range(_N if reduced else _N1), range(_N), range(_N1)
    if axis == "z":
        return range(_N if reduced else _N1), range(_N if reduced else _N1), range(_N)
    raise ValueError(f"unknown edge axis {axis!r}")


def _edge_key_order(reduced: bool) -> tuple[EdgeKey, ...]:
    keys: list[EdgeKey] = []
    for axis in ("x", "y", "z"):
        i_range, j_range, k_range = _edge_axis_ranges(axis, reduced)
        for k in k_range:
            for j in j_range:
                for i in i_range:
                    keys.append((axis, i, j, k))
    return tuple(keys)


def _build_quotient_map(
    reference: FixedP6LORReferenceComplex,
) -> tuple[csr_matrix, csr_matrix, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    full_vertex_rows = np.empty(_FULL_VERTICES, dtype=np.int64)
    full_vertex_phase = np.empty(_FULL_VERTICES, dtype=np.complex128)
    for k in range(_N1):
        for j in range(_N1):
            for i in range(_N1):
                row = _vertex_id(i, j, k)
                full_vertex_rows[row] = _reduced_vertex_id(i, j, k)
                full_vertex_phase[row] = _phase(i, j)
    vertex_rows = np.arange(_FULL_VERTICES, dtype=np.int64)
    Q0 = csr_matrix(
        (full_vertex_phase, (vertex_rows, full_vertex_rows)),
        shape=(_FULL_VERTICES, _REDUCED_VERTICES),
        dtype=np.complex128,
    )

    reduced_keys = _edge_key_order(reduced=True)
    reduced_columns = {key: index for index, key in enumerate(reduced_keys)}
    full_edge_rows = np.empty(_FULL_EDGES, dtype=np.int64)
    full_edge_phase = np.empty(_FULL_EDGES, dtype=np.complex128)
    edge_rows = np.arange(_FULL_EDGES, dtype=np.int64)
    edge_columns = np.empty(_FULL_EDGES, dtype=np.int64)
    for row, (axis, i, j, k) in enumerate(reference.edge_keys):
        key = (axis, i % _N, j % _N, k)
        try:
            column = reduced_columns[key]
        except KeyError as exc:
            raise RuntimeError(f"edge quotient key is missing: {key!r}") from exc
        edge_columns[row] = column
        full_edge_rows[row] = column
        full_edge_phase[row] = _phase(i, j)
    Q1 = csr_matrix(
        (full_edge_phase, (edge_rows, edge_columns)),
        shape=(_FULL_EDGES, _REDUCED_EDGES),
        dtype=np.complex128,
    )
    return (
        Q0,
        Q1,
        full_vertex_rows,
        full_vertex_phase,
        full_edge_rows,
        full_edge_phase,
    )


def _build_reduced_gradient() -> csr_matrix:
    rows: list[int] = []
    columns: list[int] = []
    values: list[complex] = []
    row = 0
    for axis in ("x", "y", "z"):
        i_range, j_range, k_range = _edge_axis_ranges(axis, reduced=True)
        direction = {"x": 0, "y": 1, "z": 2}[axis]
        for k in k_range:
            for j in j_range:
                for i in i_range:
                    start = [i, j, k]
                    end = list(start)
                    end[direction] += 1
                    end[0] %= _N
                    end[1] %= _N
                    start_id = _reduced_vertex_id(*start)
                    end_id = _reduced_vertex_id(*end)
                    rows.extend((row, row))
                    columns.extend((start_id, end_id))
                    end_phase = 1.0 + 0.0j
                    if axis == "x" and i == _N - 1:
                        end_phase = _PHASE_X
                    elif axis == "y" and j == _N - 1:
                        end_phase = _PHASE_Y
                    values.extend((-1.0 + 0.0j, end_phase))
                    row += 1
    return csr_matrix(
        (np.asarray(values), (rows, columns)),
        shape=(_REDUCED_EDGES, _REDUCED_VERTICES),
        dtype=np.complex128,
    )


def _orientation_error(reference: Any, edge_rows: np.ndarray) -> float:
    reduced_keys = [
        (axis, i, j, k)
        for axis, ni, nj, nk in (
            ("x", _N, _N, _N1),
            ("y", _N, _N, _N1),
            ("z", _N, _N, _N),
        )
        for k in range(nk)
        for j in range(nj)
        for i in range(ni)
    ]
    for full_row, key in enumerate(reference.edge_keys):
        axis, i, j, k = key
        reduced_row = int(edge_rows[full_row])
        if not 0 <= reduced_row < len(reduced_keys):
            return 1.0
        reduced_axis, ri, rj, rk = reduced_keys[reduced_row]
        if axis != reduced_axis or k != rk:
            return 1.0
        if axis == "x":
            valid = ri == i and rj == j % _N
        elif axis == "y":
            valid = ri == i % _N and rj == j
        else:
            valid = ri == i % _N and rj == j % _N
        if not valid:
            return 1.0
    return 0.0


def _readonly_csr(matrix: csr_matrix) -> csr_matrix:
    matrix.sum_duplicates()
    matrix.sort_indices()
    matrix.data.setflags(write=False)
    matrix.indices.setflags(write=False)
    matrix.indptr.setflags(write=False)
    return matrix


def _readonly(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(actual) - np.asarray(expected))
        / max(float(np.linalg.norm(np.asarray(expected))), _TINY)
    )


def _hermitian_relative(matrix: np.ndarray) -> float:
    values = np.asarray(matrix)
    return float(
        np.linalg.norm(values - values.conj().T)
        / max(float(np.linalg.norm(values)), _TINY)
    )


def _adjoint_relative(actual_x: np.ndarray, actual_y: np.ndarray, x, y) -> float:
    return float(
        abs(np.vdot(actual_x, y) - np.vdot(x, actual_y))
        / max(
            float(np.linalg.norm(actual_x) * np.linalg.norm(y)),
            float(np.linalg.norm(x) * np.linalg.norm(actual_y)),
            _TINY,
        )
    )


def _probe(size: int, offset: float) -> np.ndarray:
    indices = np.arange(size, dtype=np.float64)
    return np.sin(0.013 * (indices + 1.0) + offset) + 1j * np.cos(
        0.017 * (indices + 2.0) - offset
    )


def _sparse_norm(matrix: csr_matrix) -> float:
    return float(np.linalg.norm(np.asarray(matrix.data, dtype=np.complex128)))


def _sparse_commuting_audit(
    full_image: csr_matrix, quotient_image: csr_matrix
) -> dict[str, float]:
    difference = (full_image - quotient_image).tocsr()
    difference.eliminate_zeros()
    absolute = _sparse_norm(difference)
    source_norm = _sparse_norm(full_image)
    output_norm = _sparse_norm(quotient_image)
    return {
        "absolute": absolute,
        "source_norm": source_norm,
        "output_norm": output_norm,
        "relative": absolute / max(source_norm, output_norm, _TINY),
    }


def _phase_samples(
    full_vertex_phase: np.ndarray,
) -> tuple[dict[str, dict[str, Any]], float]:
    samples: dict[str, dict[str, Any]] = {}
    maximum = 0.0
    for i, j in ((0, 0), (_N, 0), (0, _N), (_N, _N)):
        actual = complex(full_vertex_phase[_vertex_id(i, j, 0)])
        expected = complex(
            np.exp(0.17j * (i == _N) - 0.09j * (j == _N))
        )
        error = abs(actual - expected)
        maximum = max(maximum, float(error))
        samples[f"({i},{j})"] = {
            "actual": actual,
            "expected": expected,
            "absolute_error": float(error),
        }
    return samples, maximum


def _action_audit(
    q1: csr_matrix,
    reduced_lor_operator: csr_matrix,
    l1a_action: FixedP6LORReferenceAction,
) -> dict[str, Any]:
    x = _probe(_REDUCED_EDGES, 0.13)
    y = _probe(_REDUCED_EDGES, 0.37)
    direct_x = _streamed_apply_from_parts(q1, l1a_action, x)
    direct_y = _streamed_apply_from_parts(q1, l1a_action, y)
    congruence_x = np.asarray(reduced_lor_operator @ x)
    repeat_x = _streamed_apply_from_parts(q1, l1a_action, x)
    alpha, beta = 0.7 - 0.2j, -0.4 + 0.3j
    linear = _streamed_apply_from_parts(
        q1, l1a_action, alpha * x + beta * y
    )
    galerkin = _apply_galerkin_from_parts(q1, l1a_action, x)
    galerkin_y = _apply_galerkin_from_parts(q1, l1a_action, y)
    rayleigh = complex(np.vdot(x, galerkin)) / complex(np.vdot(x, congruence_x))
    full_x = np.asarray(q1 @ x)
    independent_galerkin = np.asarray(
        q1.conj().T
        @ (
            l1a_action.T1.conj().T
            @ (l1a_action.p6_operator @ (l1a_action.T1 @ full_x))
        )
    )
    return {
        "direct_vs_congruence_relative": _relative(direct_x, congruence_x),
        "repeat_relative": _relative(repeat_x, direct_x),
        "linearity_relative": _relative(linear, alpha * direct_x + beta * direct_y),
        "adjoint_relative": _adjoint_relative(direct_x, direct_y, x, y),
        "galerkin_relative": _relative(galerkin, independent_galerkin),
        "galerkin_adjoint_relative": _adjoint_relative(galerkin, galerkin_y, x, y),
        "rayleigh_real": float(rayleigh.real),
        "rayleigh_imag_relative": float(
            abs(rayleigh.imag) / max(abs(rayleigh), _TINY)
        ),
    }


def _streamed_apply_from_parts(
    q1: csr_matrix,
    l1a_action: FixedP6LORReferenceAction,
    values: np.ndarray,
) -> np.ndarray:
    """Reference implementation of the required q/conjugate-q scatter."""

    reduced = _as_vector(values, _REDUCED_EDGES)
    result = np.zeros(_REDUCED_EDGES, dtype=np.complex128)
    full_rows = np.asarray(q1.indices, dtype=np.int64)
    phases = np.asarray(q1.data, dtype=np.complex128)
    rows = l1a_action.cell_rows
    signs = l1a_action.cell_signs.astype(np.float64)
    tensor = l1a_action.cell_local_tensor
    for cell_rows, cell_signs in zip(rows, signs, strict=True):
        reduced_rows = full_rows[cell_rows]
        local_input = cell_signs * phases[cell_rows] * reduced[reduced_rows]
        local_output = tensor @ local_input
        result[reduced_rows] += (
            np.conj(phases[cell_rows]) * cell_signs * local_output
        )
    return result


def _apply_galerkin_from_parts(
    q1: csr_matrix,
    l1a_action: FixedP6LORReferenceAction,
    values: np.ndarray,
) -> np.ndarray:
    full_values = np.asarray(q1 @ _as_vector(values, _REDUCED_EDGES))
    p6_values = l1a_action.T1 @ full_values
    p6_output = l1a_action.p6_operator @ p6_values
    return np.asarray(
        q1.conj().T @ (l1a_action.T1.conj().T @ p6_output)
    )


def build_fixed_p6_lor_xy_floquet_reference_action() -> (
    FixedP6LORXYFloquetReferenceAction
):
    """Build the fixed x/y-periodic p6/LOR reference action."""

    started = perf_counter()
    l1a_action = build_fixed_p6_lor_reference_action()
    reference = l1a_action.transfer.reference
    Q0, Q1, vertex_rows, vertex_phase, edge_rows, edge_phase = _build_quotient_map(
        reference
    )
    G_reduced = _build_reduced_gradient()
    Q0 = _readonly_csr(Q0)
    Q1 = _readonly_csr(Q1)
    G_reduced = _readonly_csr(G_reduced)
    full_gradient = reference.gradient_incidence.astype(np.complex128)
    quotient_gradient = _sparse_commuting_audit(
        (full_gradient @ Q0).tocsr(), (Q1 @ G_reduced).tocsr()
    )
    reduced_lor_operator = _readonly_csr(
        (Q1.conj().T @ l1a_action.lor_operator @ Q1).tocsr()
    )
    action_metrics = _action_audit(Q1, reduced_lor_operator, l1a_action)
    phase_samples, phase_max = _phase_samples(vertex_phase)
    orientation_max = _orientation_error(reference, edge_rows)
    q0_phase_magnitude_error = float(np.max(np.abs(np.abs(Q0.data) - 1.0)))
    q1_phase_magnitude_error = float(np.max(np.abs(np.abs(Q1.data) - 1.0)))

    q1_dense = np.asarray(Q1.toarray(), dtype=np.complex128)
    tq = l1a_action.T1 @ q1_dense
    galerkin_dense = q1_dense.conj().T @ (
        l1a_action.T1.conj().T @ (l1a_action.p6_operator @ tq)
    )
    lor_dense = np.asarray(reduced_lor_operator.toarray(), dtype=np.complex128)
    eigenvalues = np.asarray(
        eigh(galerkin_dense, lor_dense, check_finite=True, eigvals_only=True),
        dtype=np.float64,
    )
    dense_oracle_transient = int(
        q1_dense.nbytes + tq.nbytes + galerkin_dense.nbytes + lor_dense.nbytes
    )
    galerkin_hermitian = _hermitian_relative(galerkin_dense)
    lor_hermitian = _hermitian_relative(lor_dense)
    spectrum = {
        "finite": bool(np.all(np.isfinite(eigenvalues))),
        "positive": bool(
            eigenvalues.size == _REDUCED_EDGES
            and np.all(eigenvalues > 0.0)
        ),
        "min": float(eigenvalues[0]),
        "max": float(eigenvalues[-1]),
        "count": int(eigenvalues.size),
        "ratio": float(eigenvalues[-1] / eigenvalues[0]),
    }
    rayleigh_spectrum_range_tolerance = float(
        256.0
        * np.finfo(float).eps
        * max(1.0, spectrum["min"], spectrum["max"])
    )
    del q1_dense, tq, galerkin_dense, lor_dense, eigenvalues

    samples = {
        "phase_x": _PHASE_X,
        "phase_y": _PHASE_Y,
        "vertex": phase_samples,
    }
    checks = {
        "phase": phase_max <= _ORIENTATION_TOL,
        "phase_magnitude": max(
            q0_phase_magnitude_error, q1_phase_magnitude_error
        )
        <= _ORIENTATION_TOL,
        "orientation": orientation_max <= _ORIENTATION_TOL,
        "quotient_gradient": quotient_gradient["relative"] <= _COMMUTING_TOL,
        "one_nnz_per_Q0_row": bool(np.all(np.diff(Q0.indptr) == 1)),
        "one_nnz_per_Q1_row": bool(np.all(np.diff(Q1.indptr) == 1)),
        "coverage": bool(
            np.unique(vertex_rows).size == _REDUCED_VERTICES
            and np.unique(edge_rows).size == _REDUCED_EDGES
        ),
        "action": action_metrics["direct_vs_congruence_relative"] <= _ACTION_TOL,
        "repeat": action_metrics["repeat_relative"] <= _ACTION_TOL,
        "linearity": action_metrics["linearity_relative"] <= _ACTION_TOL,
        "adjoint": action_metrics["adjoint_relative"] <= _ADJOINT_TOL,
        "galerkin": action_metrics["galerkin_relative"] <= _ACTION_TOL,
        "galerkin_adjoint": action_metrics["galerkin_adjoint_relative"]
        <= _ADJOINT_TOL,
        "hermitian": max(lor_hermitian, galerkin_hermitian) <= _ACTION_TOL,
        "spectrum": spectrum["finite"] and spectrum["positive"],
        "rayleigh": bool(
            np.isfinite(action_metrics["rayleigh_real"])
            and np.isfinite(action_metrics["rayleigh_imag_relative"])
            and action_metrics["rayleigh_imag_relative"] <= 1.0e-10
            and spectrum["min"] - rayleigh_spectrum_range_tolerance
            <= action_metrics["rayleigh_real"]
            <= spectrum["max"] + rayleigh_spectrum_range_tolerance
        ),
        "structure": bool(
            _FULL_VERTICES == 343
            and _REDUCED_VERTICES == 252
            and _FULL_EDGES == 882
            and _REDUCED_EDGES == 720
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"fixed p6 x-y periodic audit failed: {checks}")

    retained_bytes = sum(
        int(array.nbytes)
        for array in (
            Q0.data,
            Q0.indices,
            Q0.indptr,
            Q1.data,
            Q1.indices,
            Q1.indptr,
            G_reduced.data,
            G_reduced.indices,
            G_reduced.indptr,
            reduced_lor_operator.data,
            reduced_lor_operator.indices,
            reduced_lor_operator.indptr,
            vertex_rows,
            vertex_phase,
            edge_rows,
            edge_phase,
        )
    )
    audit = {
        "schema_version": "task040.fixed-lor.l1b.v1",
        "status": "fixed_p6_xy_floquet_reference_mechanism_qualified",
        "scope": "research_local_only_periodic_reference_mechanism_not_lor_solver",
        "pass": True,
        "unit_box": True,
        "periodic_axes": ("x", "y"),
        "phase": samples,
        "phase_max_absolute_error": phase_max,
        "phase_magnitude_max_error": max(
            q0_phase_magnitude_error, q1_phase_magnitude_error
        ),
        "phase_magnitude_max_error_by_map": {
            "Q0": q0_phase_magnitude_error,
            "Q1": q1_phase_magnitude_error,
        },
        "orientation_max_absolute_error": orientation_max,
        "counts": {
            "full_vertices": _FULL_VERTICES,
            "reduced_vertices": _REDUCED_VERTICES,
            "full_edges": _FULL_EDGES,
            "reduced_edges": _REDUCED_EDGES,
            "reduced_edge_axes": {"x": 252, "y": 252, "z": 216},
        },
        "shapes": {
            "Q0": tuple(map(int, Q0.shape)),
            "Q1": tuple(map(int, Q1.shape)),
            "G_full": tuple(map(int, reference.gradient_incidence.shape)),
            "G_reduced": tuple(map(int, G_reduced.shape)),
            "reduced_lor_operator": tuple(map(int, reduced_lor_operator.shape)),
        },
        "coverage": {
            "Q0_one_nnz_per_full_row": bool(np.all(np.diff(Q0.indptr) == 1)),
            "Q1_one_nnz_per_full_row": bool(np.all(np.diff(Q1.indptr) == 1)),
            "Q0_reduced_columns": int(np.unique(vertex_rows).size),
            "Q1_reduced_columns": int(np.unique(edge_rows).size),
                "corner_phase_once": bool(
                    abs(vertex_phase[_vertex_id(_N, _N, 0)] - _PHASE_X * _PHASE_Y)
                <= _ORIENTATION_TOL
            ),
        },
        "quotient_gradient_commuting": quotient_gradient,
        "action": action_metrics,
        "hermitian_relative": {
            "reduced_lor": lor_hermitian,
            "reduced_galerkin_transient": galerkin_hermitian,
        },
        "spectrum": spectrum,
        "rayleigh_spectrum_range_tolerance": rayleigh_spectrum_range_tolerance,
        "checks": checks,
        "bytes": {
            "retained_periodic_maps": retained_bytes,
            "dense_oracle_transient": dense_oracle_transient,
        },
        "structure": {
            "max_local_rows": _REDUCED_EDGES,
            "full_side_factor_count": 0,
            "full_cross_section_factor_count": 0,
            "global_direct_factor_count": 0,
            "coarse_factor_count": 0,
        },
        "max_local_rows": _REDUCED_EDGES,
        "petsc": False,
        "dolfinx": False,
        "mpi": False,
        "allgather": False,
        "global_factor": False,
        "wall_seconds": float(perf_counter() - started),
    }
    _readonly(vertex_rows)
    _readonly(vertex_phase)
    _readonly(edge_rows)
    _readonly(edge_phase)
    return FixedP6LORXYFloquetReferenceAction(
        l1a_action=l1a_action,
        Q0=Q0,
        Q1=Q1,
        G_reduced=G_reduced,
        full_vertex_to_reduced_row=vertex_rows,
        full_vertex_phase=vertex_phase,
        full_edge_to_reduced_row=edge_rows,
        full_edge_phase=edge_phase,
        reduced_lor_operator=reduced_lor_operator,
        audit=audit,
    )
