"""Task040 L1a: one-cell fixed p6/LOR Maxwell action reference.

This is a research-only local mechanism check.  It assembles one p6
``curlcurl + M`` tensor and an independently assembled six-by-six-by-six p1
low-order-refined tensor.  It has no mesh, PETSc, MPI, source, or solver
integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import basix
import basix.ufl
import numpy as np
from scipy.linalg import eigh
from scipy.sparse import coo_matrix, csr_matrix

from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.hcurl_fixed_lor import FixedP6LORReferenceComplex
from src.solvers.hcurl_fixed_lor_transfer import (
    FixedP6LORReferenceTransfer,
    build_fixed_p6_lor_reference_transfer,
)

__all__ = (
    "FixedP6LORReferenceAction",
    "build_fixed_p6_lor_reference_action",
)


_N = 6
_N1 = _N + 1
_VERTICES = _N1**3
_EDGES = 3 * _N * _N1**2
_CELLS = _N**3
_LOCAL_EDGES = 12
_TINY = np.finfo(np.float64).tiny
_ORIENTATION_TOL = 2.0e-12
_ACTION_TOL = 1.0e-10
_ADJOINT_TOL = 2.0e-11
_TRANSFER_TOL = 2.0e-10

Key3 = tuple[int, int, int]


@dataclass(frozen=True)
class FixedP6LORReferenceAction:
    """Fixed one-cell p6 and six-by-six-by-six p1 action data."""

    transfer: FixedP6LORReferenceTransfer
    p6_operator: np.ndarray
    lor_operator: csr_matrix
    T1: np.ndarray
    cell_rows: np.ndarray
    cell_signs: np.ndarray
    cell_local_tensor: np.ndarray
    audit: dict[str, Any]

    def apply_p6(self, vector: np.ndarray) -> np.ndarray:
        """Apply the dense p6 reference action."""

        values = _as_vector(vector, _EDGES)
        return np.asarray(self.p6_operator @ values)

    def apply_lor_streamed(self, vector: np.ndarray) -> np.ndarray:
        """Apply the LOR action by streaming twelve-entry cell tensors."""

        values = _as_vector(vector, _EDGES)
        result = np.zeros(_EDGES, dtype=np.complex128)
        for rows, signs in zip(self.cell_rows, self.cell_signs, strict=True):
            local_input = signs.astype(np.float64) * values[rows]
            local_output = self.cell_local_tensor @ local_input
            result[rows] += signs.astype(np.float64) * local_output
        return result

    def apply_galerkin(self, vector: np.ndarray) -> np.ndarray:
        """Apply ``T1ᴴ p6_operator T1`` in LOR coordinates."""

        values = _as_vector(vector, _EDGES)
        p6_values = self.T1 @ values
        return np.asarray(self.T1.conj().T @ (self.p6_operator @ p6_values))


def _as_vector(vector: np.ndarray, size: int) -> np.ndarray:
    values = np.asarray(vector, dtype=np.complex128)
    if values.shape != (size,):
        raise ValueError(f"expected a vector of shape {(size,)}, got {values.shape}")
    return values


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(actual) - np.asarray(expected))
        / max(float(np.linalg.norm(np.asarray(expected))), _TINY)
    )


def _probe(size: int, offset: float) -> np.ndarray:
    indices = np.arange(size, dtype=np.float64)
    return np.sin(0.013 * (indices + 1.0) + offset) + 1j * np.cos(
        0.017 * (indices + 2.0) - offset
    )


def _edge_endpoint_map(
    reference: FixedP6LORReferenceComplex,
) -> dict[tuple[Key3, Key3], tuple[int, int]]:
    result: dict[tuple[Key3, Key3], tuple[int, int]] = {}
    axis_step = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
    for row, key in enumerate(reference.edge_keys):
        axis, i, j, k = key
        start = (int(i), int(j), int(k))
        step = axis_step[axis]
        end = tuple(start[index] + step[index] for index in range(3))
        result[(start, end)] = (row, 1)
        result[(end, start)] = (row, -1)
    return result


def _local_orientation_audit(
    element,
    edge_topology,
    geometry: np.ndarray,
) -> dict[str, Any]:
    interpolation = np.asarray(element.interpolation_matrix, dtype=np.float64)
    points = np.asarray(element.points, dtype=np.float64)
    if interpolation.shape != (int(element.dim), 3 * len(points)):
        raise RuntimeError("unexpected p1 N1curl interpolation matrix shape")
    entity_dofs = element.entity_dofs[1]
    if len(entity_dofs) != _LOCAL_EDGES or any(
        len(dofs) != 1 for dofs in entity_dofs
    ):
        raise RuntimeError("p1 N1curl does not expose twelve one-DoF edges")
    maximum_error = 0.0
    for component in range(3):
        values = np.zeros((3, len(points)), dtype=np.float64)
        values[component, :] = 1.0
        coefficients = interpolation @ values.reshape(-1)
        for edge_index, (start, end) in enumerate(edge_topology):
            dof = int(entity_dofs[edge_index][0])
            edge_vector = geometry[end] - geometry[start]
            maximum_error = max(
                maximum_error,
                abs(float(coefficients[dof]) - float(edge_vector[component])),
            )
    return {
        "constant_field_max_error": float(maximum_error),
        "edge_count": len(entity_dofs),
        "pass": bool(maximum_error <= _ORIENTATION_TOL),
    }


def _build_cell_maps(
    reference: FixedP6LORReferenceComplex,
    element,
    edge_topology,
    geometry: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    endpoint_map = _edge_endpoint_map(reference)
    entity_dofs = element.entity_dofs[1]
    rows = np.empty((_CELLS, _LOCAL_EDGES), dtype=np.int64)
    signs = np.empty((_CELLS, _LOCAL_EDGES), dtype=np.int8)
    for cell_index, (i, j, k) in enumerate(reference.cell_keys):
        base = np.asarray((i, j, k), dtype=np.int64)
        local_vertices = base + np.rint(geometry).astype(np.int64)
        for edge_index, (start_local, end_local) in enumerate(edge_topology):
            dof = int(entity_dofs[edge_index][0])
            start = tuple(int(value) for value in local_vertices[start_local])
            end = tuple(int(value) for value in local_vertices[end_local])
            try:
                row, sign = endpoint_map[(start, end)]
            except KeyError as exc:
                raise RuntimeError("p1 cell edge is absent from L0a edge map") from exc
            rows[cell_index, dof] = row
            signs[cell_index, dof] = sign
    sorted_rows = np.sort(rows, axis=1)
    if not np.all(sorted_rows[:, 1:] != sorted_rows[:, :-1]):
        raise RuntimeError("a p1 cell has duplicate canonical edge rows")
    coverage = np.bincount(rows.ravel(), minlength=_EDGES)
    covered = int(np.count_nonzero(coverage))
    missing = int(np.count_nonzero(coverage == 0))
    edge_axis = np.asarray(
        ["xyz".index(key[0]) for key in reference.edge_keys],
        dtype=np.int64,
    )
    interpolation = np.asarray(element.interpolation_matrix, dtype=np.float64)
    points = np.asarray(element.points, dtype=np.float64)
    constant_field_max_error = 0.0
    for component in range(3):
        values = np.zeros((3, len(points)), dtype=np.float64)
        values[component, :] = 1.0
        local_coefficients = interpolation @ values.reshape(-1)
        for cell_rows, cell_signs in zip(rows, signs, strict=True):
            mapped = cell_signs.astype(np.float64) * local_coefficients / _N
            expected = (
                edge_axis[cell_rows] == component
            ).astype(np.float64) / _N
            constant_field_max_error = max(
                constant_field_max_error,
                float(np.max(np.abs(mapped - expected))),
            )
    return rows, signs, {
        "cell_count": len(reference.cell_keys),
        "local_dof_count": int(element.dim),
        "covered": covered,
        "missing": missing,
        "coverage_min": int(coverage.min()),
        "coverage_max": int(coverage.max()),
        "pass": bool(covered == _EDGES and missing == 0),
        "constant_field_max_error": float(constant_field_max_error),
        "constant_field_pass": bool(
            constant_field_max_error <= _ORIENTATION_TOL
        ),
    }


def _assemble_lor(
    cell_rows: np.ndarray,
    cell_signs: np.ndarray,
    local_tensor: np.ndarray,
) -> csr_matrix:
    shape = (len(cell_rows), _LOCAL_EDGES, _LOCAL_EDGES)
    global_rows = np.broadcast_to(cell_rows[:, :, None], shape).reshape(-1)
    global_cols = np.broadcast_to(cell_rows[:, None, :], shape).reshape(-1)
    sign_product = (
        cell_signs[:, :, None].astype(np.float64)
        * cell_signs[:, None, :].astype(np.float64)
    )
    values = (sign_product[:, :, :] * local_tensor[None, :, :]).reshape(-1)
    matrix = coo_matrix(
        (values, (global_rows, global_cols)),
        shape=(_EDGES, _EDGES),
        dtype=np.complex128,
    ).tocsr()
    matrix.sum_duplicates()
    return matrix


def _hermitian_relative(matrix: np.ndarray) -> float:
    dense = np.asarray(matrix)
    return float(
        np.linalg.norm(dense - dense.conj().T)
        / max(float(np.linalg.norm(dense)), _TINY)
    )


def _readonly(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


def build_fixed_p6_lor_reference_action() -> FixedP6LORReferenceAction:
    """Build and audit the fixed one-cell p6/LOR Maxwell mechanism."""

    started = perf_counter()
    transfer = build_fixed_p6_lor_reference_transfer()
    cell_type = basix.CellType.hexahedron
    hcurl_p6 = basix.ufl.element("N1curl", "hexahedron", _N).basix_element
    hcurl_p1 = basix.ufl.element("N1curl", "hexahedron", 1).basix_element
    geometry = np.asarray(basix.geometry(cell_type), dtype=np.float64)
    edge_topology = basix.topology(cell_type)[1]
    orientation = _local_orientation_audit(hcurl_p1, edge_topology, geometry)
    cell_rows, cell_signs, cell_audit = _build_cell_maps(
        transfer.reference,
        hcurl_p1,
        edge_topology,
        geometry,
    )

    spec = AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=1.0,
        mass_coefficient_by_tag={0: 1.0},
    )
    p6_factory = AffineIsotropicMaxwellTensorFactory(hcurl_p6, spec)
    p1_factory = AffineIsotropicMaxwellTensorFactory(hcurl_p1, spec)
    p6_operator = np.asarray(
        p6_factory.tensor(tag=0, widths=(1.0, 1.0, 1.0)),
        dtype=np.complex128,
    )
    local_tensor = np.asarray(
        p1_factory.tensor(tag=0, widths=(1.0 / _N,) * 3),
        dtype=np.complex128,
    )
    tensor_factory = {
        "p6": {
            "quadrature_degree": int(p6_factory.audit["quadrature_degree"]),
            "quadrature_point_count": int(
                p6_factory.audit["quadrature_point_count"]
            ),
            "identity_sha256": str(p6_factory.audit["identity_sha256"]),
            "reference_component_bytes": int(
                p6_factory.audit["reference_component_bytes"]
            ),
            "total_build_seconds": float(
                p6_factory.audit["total_build_seconds"]
            ),
        },
        "p1": {
            "quadrature_degree": int(p1_factory.audit["quadrature_degree"]),
            "quadrature_point_count": int(
                p1_factory.audit["quadrature_point_count"]
            ),
            "identity_sha256": str(p1_factory.audit["identity_sha256"]),
            "reference_component_bytes": int(
                p1_factory.audit["reference_component_bytes"]
            ),
            "total_build_seconds": float(
                p1_factory.audit["total_build_seconds"]
            ),
        },
    }
    del p6_factory, p1_factory
    lor_operator = _assemble_lor(cell_rows, cell_signs, local_tensor)
    T1 = np.linalg.solve(
        transfer.R1,
        np.eye(_EDGES, dtype=np.float64),
    )
    T0 = np.linalg.solve(
        transfer.R0,
        np.eye(_VERTICES, dtype=np.float64),
    )

    lor_dense = lor_operator.toarray()
    lor_hermitian = _hermitian_relative(lor_dense)
    B = T1.conj().T @ (p6_operator @ T1)
    B_hermitian = _hermitian_relative(B)
    x = _probe(_EDGES, 0.13)
    y = _probe(_EDGES, 0.37)
    Tx = T1 @ x
    Ty = T1 @ y
    B_x = B @ x
    galerkin_x = T1.conj().T @ (p6_operator @ Tx)
    B_apply_relative = _relative(galerkin_x, B_x)
    B_y = B @ y
    p6_Ty = p6_operator @ Ty
    B_sesquilinear_left = np.vdot(x, B_y)
    B_sesquilinear_right = np.vdot(Tx, p6_Ty)
    B_sesquilinear_relative = abs(
        B_sesquilinear_left - B_sesquilinear_right
    ) / max(
        float(np.linalg.norm(x) * np.linalg.norm(B_y)),
        float(np.linalg.norm(Tx) * np.linalg.norm(p6_Ty)),
        _TINY,
    )
    generalized = np.asarray(
        eigh(B, lor_dense, check_finite=True, eigvals_only=True),
        dtype=np.float64,
    )
    dense_oracle_transient = int(B.nbytes + lor_dense.nbytes + T0.nbytes)
    del B, lor_dense

    streamed = np.asarray(
        _streamed_apply(cell_rows, cell_signs, local_tensor, x)
    )
    streamed_y = np.asarray(
        _streamed_apply(cell_rows, cell_signs, local_tensor, y)
    )
    csr_result = np.asarray(lor_operator @ x)
    streamed_repeat = np.asarray(
        _streamed_apply(cell_rows, cell_signs, local_tensor, x)
    )
    alpha = 0.7 - 0.2j
    beta = -0.4 + 0.3j
    streamed_linear = np.asarray(
        _streamed_apply(
            cell_rows,
            cell_signs,
            local_tensor,
            alpha * x + beta * y,
        )
    )
    streamed_adjoint_error = abs(
        np.vdot(streamed, y) - np.vdot(x, streamed_y)
    ) / max(
        float(np.linalg.norm(streamed) * np.linalg.norm(y)),
        float(np.linalg.norm(x) * np.linalg.norm(streamed_y)),
        _TINY,
    )
    identity = np.eye(_EDGES, dtype=np.float64)
    t1_left = _relative(T1 @ transfer.R1, identity)
    t1_right = _relative(transfer.R1 @ T1, identity)
    lor_gradient = transfer.reference.gradient_incidence
    inverse_commuting = _relative(
        T1 @ lor_gradient.toarray(),
        transfer.p6_discrete_gradient @ T0,
    )
    del T0
    p6_hermitian = _hermitian_relative(p6_operator)
    finite = bool(
        np.all(np.isfinite(p6_operator))
        and np.all(np.isfinite(lor_operator.data))
        and np.all(np.isfinite(local_tensor))
        and np.all(np.isfinite(T1))
        and np.all(np.isfinite(generalized))
    )
    generalized_positive = bool(
        generalized.size == _EDGES
        and np.all(np.isfinite(generalized))
        and float(generalized[0]) > 0.0
        and float(generalized[-1]) > 0.0
    )
    checks = {
        "shapes": bool(
            p6_operator.shape == (_EDGES, _EDGES)
            and lor_operator.shape == (_EDGES, _EDGES)
            and T1.shape == (_EDGES, _EDGES)
            and cell_rows.shape == (_CELLS, _LOCAL_EDGES)
            and cell_signs.shape == (_CELLS, _LOCAL_EDGES)
            and local_tensor.shape == (_LOCAL_EDGES, _LOCAL_EDGES)
        ),
        "finite": finite,
        "hermitian": bool(
            p6_hermitian <= _ACTION_TOL and lor_hermitian <= _ACTION_TOL
        ),
        "orientation": bool(
            orientation["pass"]
            and cell_audit["pass"]
            and cell_audit["constant_field_pass"]
        ),
        "streamed_vs_csr": _relative(streamed, csr_result) <= _ACTION_TOL,
        "streamed_repeat": _relative(streamed_repeat, streamed) <= _ACTION_TOL,
        "streamed_linearity": _relative(
            streamed_linear,
            alpha * streamed + beta * streamed_y,
        )
        <= _ACTION_TOL,
        "streamed_adjoint": float(streamed_adjoint_error) <= _ADJOINT_TOL,
        "T1_inverse": max(t1_left, t1_right) <= _TRANSFER_TOL,
        "inverse_commuting": inverse_commuting <= _TRANSFER_TOL,
        "B_hermitian": B_hermitian <= _ACTION_TOL,
        "B_apply": B_apply_relative <= _ACTION_TOL,
        "B_sesquilinear": B_sesquilinear_relative <= _ACTION_TOL,
        "reference_transfer_pass": bool(transfer.audit["pass"]),
        "generalized_spectrum": generalized_positive,
    }
    if not all(checks.values()):
        raise RuntimeError(f"fixed p6/LOR action audit failed: {checks}")

    audit = {
        "schema_version": "task040.fixed-lor.l1a.v1",
        "status": "fixed_p6_reference_mechanism_qualified",
        "pass": True,
        "scope": "research_local_only_reference_mechanism_not_lor_solver",
        "operator": "curlcurl_plus_tau_mass",
        "tau": 1.0,
        "p6_widths": (1.0, 1.0, 1.0),
        "p1_widths": (1.0 / _N, 1.0 / _N, 1.0 / _N),
        "counts": {
            "p6_dofs": _EDGES,
            "lor_edges": _EDGES,
            "lor_cells": _CELLS,
            "local_p1_edges": _LOCAL_EDGES,
            "lor_nnz": int(lor_operator.nnz),
        },
        "orientation": orientation,
        "cell_mapping": cell_audit,
        "tensor_factory": tensor_factory,
        "operator_shapes": {
            "p6": tuple(map(int, p6_operator.shape)),
            "lor": tuple(map(int, lor_operator.shape)),
            "T1": tuple(map(int, T1.shape)),
            "cell_rows": tuple(map(int, cell_rows.shape)),
            "cell_signs": tuple(map(int, cell_signs.shape)),
            "cell_local_tensor": tuple(map(int, local_tensor.shape)),
        },
        "hermitian_relative": {
            "p6": p6_hermitian,
            "lor": lor_hermitian,
            "B_transient": B_hermitian,
        },
        "streamed_action": {
            "vs_csr_relative": _relative(streamed, csr_result),
            "repeat_relative": _relative(streamed_repeat, streamed),
            "linearity_relative": _relative(
                streamed_linear,
                alpha * streamed + beta * streamed_y,
            ),
            "adjoint_relative": float(streamed_adjoint_error),
        },
        "galerkin_action": {
            "B_apply_relative": B_apply_relative,
            "B_sesquilinear_relative": float(B_sesquilinear_relative),
        },
        "T1": {
            "left_inverse_relative": t1_left,
            "right_inverse_relative": t1_right,
            "inverse_commuting_relative": inverse_commuting,
        },
        "generalized_spectrum": {
            "min": float(generalized[0]),
            "max": float(generalized[-1]),
            "ratio": float(generalized[-1] / generalized[0]),
            "count": len(generalized),
        },
        "checks": checks,
        "bytes": {
            "p6_operator": int(p6_operator.nbytes),
            "lor_data": int(lor_operator.data.nbytes),
            "lor_indices": int(lor_operator.indices.nbytes),
            "lor_indptr": int(lor_operator.indptr.nbytes),
            "csr_total": int(
                lor_operator.data.nbytes
                + lor_operator.indices.nbytes
                + lor_operator.indptr.nbytes
            ),
            "dense_retained": int(
                p6_operator.nbytes
                + T1.nbytes
                + transfer.R0.nbytes
                + transfer.R1.nbytes
                + transfer.p6_discrete_gradient.nbytes
            ),
            "dense_oracle_transient": dense_oracle_transient,
            "T1": int(T1.nbytes),
            "cell_rows": int(cell_rows.nbytes),
            "cell_signs": int(cell_signs.nbytes),
            "cell_local_tensor": int(local_tensor.nbytes),
        },
        "structure": {
            "max_local_rows": _EDGES,
            "full_side_factor_count": 0,
            "full_cross_section_factor_count": 0,
            "global_direct_factor_count": 0,
            "coarse_factor_count": 0,
        },
        "wall_seconds": float(perf_counter() - started),
        "petsc": False,
        "dolfinx": False,
        "mpi": False,
        "global_factor": False,
        "allgather": False,
    }
    _readonly(p6_operator)
    _readonly(T1)
    _readonly(cell_rows)
    _readonly(cell_signs)
    _readonly(local_tensor)
    lor_operator.data.setflags(write=False)
    lor_operator.indices.setflags(write=False)
    lor_operator.indptr.setflags(write=False)
    return FixedP6LORReferenceAction(
        transfer=transfer,
        p6_operator=p6_operator,
        lor_operator=lor_operator,
        T1=T1,
        cell_rows=cell_rows,
        cell_signs=cell_signs,
        cell_local_tensor=local_tensor,
        audit=audit,
    )


def _streamed_apply(
    cell_rows: np.ndarray,
    cell_signs: np.ndarray,
    local_tensor: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    result = np.zeros(_EDGES, dtype=np.complex128)
    for rows, signs in zip(cell_rows, cell_signs, strict=True):
        sign_values = signs.astype(np.float64)
        local = local_tensor @ (sign_values * values[rows])
        result[rows] += sign_values * local
    return result
