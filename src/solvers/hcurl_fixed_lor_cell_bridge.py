"""Task040 L2a: one-cell p6/LOR trace Schur bridge.

This is a deliberately local mechanism.  It uses one affine hexahedral cell,
Basix p6 orientation data, and the fixed six-by-six-by-six LOR reference.  No
mesh, PETSc object, MPI route, global matrix, or global factor is constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import basix
import basix.ufl
import numpy as np
from scipy.linalg import lu_factor, lu_solve

from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.hcurl_fixed_lor import build_fixed_p6_lor_reference_complex
from src.solvers.hcurl_fixed_lor_action import (
    _assemble_lor,
    _build_cell_maps,
)
from src.solvers.hcurl_fixed_lor_transfer import (
    build_fixed_p6_lor_reference_transfer,
)

__all__ = (
    "FixedP6LORCellBridge",
    "build_fixed_p6_lor_cell_bridge",
)


_P6_DEGREE = 6
_LOR_SUBDIVISION = 6
_P6_DOF = 882
_TRACE_DOF = 432
_INTERIOR_DOF = 450
_LOR_DOF = 882
_TINY = np.finfo(np.float64).tiny
_SUPPORT_TOL = 2.0e-12
_ACTION_TOL = 1.0e-10


def _as_vector(vector: np.ndarray, size: int) -> np.ndarray:
    values = np.asarray(vector, dtype=np.complex128)
    if values.shape != (size,):
        raise ValueError(f"expected shape {(size,)}, got {values.shape}")
    return values


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(actual) - np.asarray(expected))
        / max(float(np.linalg.norm(np.asarray(expected))), _TINY)
    )


def _probe(size: int, offset: float) -> np.ndarray:
    index = np.arange(size, dtype=np.float64)
    return np.sin(0.013 * (index + 1.0) + offset) + 1j * np.cos(
        0.017 * (index + 2.0) - offset
    )


def _pair(value: complex) -> tuple[float, float]:
    scalar = complex(value)
    return float(scalar.real), float(scalar.imag)


def _widths(value: tuple[float, float, float]) -> tuple[float, float, float]:
    widths = tuple(float(item) for item in value)
    if len(widths) != 3 or not np.all(np.isfinite(widths)) or any(
        item <= 0.0 for item in widths
    ):
        raise ValueError("widths must be three finite positive values")
    return widths


def _cell_info(value: int | np.ndarray) -> int:
    info = np.asarray(value).reshape(-1)
    if info.size != 1:
        raise ValueError("cell_info must contain exactly one Basix cell id")
    integer = int(info[0])
    if integer < 0:
        raise ValueError("cell_info must be nonnegative")
    return integer


def _p6_partition(element) -> tuple[np.ndarray, np.ndarray]:
    entity_dofs = element.entity_dofs
    entity_trace = np.concatenate(
        [
            np.asarray(dofs, dtype=np.int32)
            for dimension in range(3)
            for dofs in entity_dofs[dimension]
        ]
    )
    interior = np.asarray(entity_dofs[3][0], dtype=np.int32)
    all_rows = np.arange(int(element.dim), dtype=np.int32)
    trace = np.setdiff1d(all_rows, interior, assume_unique=True)
    if trace.size != _TRACE_DOF or interior.size != _INTERIOR_DOF:
        raise RuntimeError(
            "Basix p6 N1curl partition is not trace=432/interior=450: "
            f"{trace.size}/{interior.size}"
        )
    if not np.array_equal(np.sort(entity_trace), trace):
        raise RuntimeError("Basix entity trace DoFs disagree with condensation")
    if len(np.unique(trace)) != len(trace) or len(np.unique(interior)) != len(
        interior
    ):
        raise RuntimeError("p6 entity DoF partition contains duplicates")
    if np.intersect1d(trace, interior).size or not np.array_equal(
        np.sort(np.concatenate((trace, interior))), all_rows
    ):
        raise RuntimeError("p6 trace/interior partition is incomplete")
    return trace, interior


def _lor_partition(reference) -> tuple[np.ndarray, np.ndarray]:
    boundary: list[int] = []
    interior: list[int] = []
    for row, (axis, i, j, k) in enumerate(reference.edge_keys):
        if axis == "x":
            on_boundary = j in (0, _LOR_SUBDIVISION) or k in (
                0,
                _LOR_SUBDIVISION,
            )
        elif axis == "y":
            on_boundary = i in (0, _LOR_SUBDIVISION) or k in (
                0,
                _LOR_SUBDIVISION,
            )
        else:
            on_boundary = i in (0, _LOR_SUBDIVISION) or j in (
                0,
                _LOR_SUBDIVISION,
            )
        (boundary if on_boundary else interior).append(row)
    boundary_rows = np.asarray(boundary, dtype=np.int32)
    interior_rows = np.asarray(interior, dtype=np.int32)
    if boundary_rows.size != _TRACE_DOF or interior_rows.size != _INTERIOR_DOF:
        raise RuntimeError(
            "canonical LOR boundary/interior partition is not 432/450: "
            f"{boundary_rows.size}/{interior_rows.size}"
        )
    if len(np.unique(np.concatenate((boundary_rows, interior_rows)))) != _LOR_DOF:
        raise RuntimeError("canonical LOR partition is incomplete")
    return boundary_rows, interior_rows


def _coefficient_transform(element, info: int) -> np.ndarray:
    dimension = int(element.dim)
    transform = np.empty((dimension, dimension), dtype=np.float64)
    for column in range(dimension):
        basis = np.zeros(dimension, dtype=np.float64)
        basis[column] = 1.0
        element.T_apply(basis, 1, info)
        transform[:, column] = basis
    if not np.all(np.isfinite(transform)):
        raise RuntimeError("Basix coefficient transform is not finite")
    return transform


def _orient_tensor(
    element, tensor: np.ndarray, info: int
) -> np.ndarray:
    dimension = int(tensor.shape[0])

    def transform_part(part: np.ndarray) -> np.ndarray:
        element.T_apply(part.ravel(), dimension, info)
        transpose = np.ascontiguousarray(part.T)
        element.T_apply(transpose.ravel(), dimension, info)
        return np.ascontiguousarray(transpose.T)

    real_oriented = transform_part(
        np.ascontiguousarray(tensor.real, dtype=np.float64)
    )
    imag_oriented = transform_part(
        np.ascontiguousarray(tensor.imag, dtype=np.float64)
    )
    return np.asarray(real_oriented + 1j * imag_oriented, dtype=np.complex128)


def _interior_schur(
    tensor: np.ndarray,
    trace: np.ndarray,
    interior: np.ndarray,
    offset: float,
) -> tuple[np.ndarray, float]:
    a_ii = np.asarray(tensor[np.ix_(interior, interior)], dtype=np.complex128)
    a_it = np.asarray(tensor[np.ix_(interior, trace)], dtype=np.complex128)
    a_ti = np.asarray(tensor[np.ix_(trace, interior)], dtype=np.complex128)
    a_tt = np.asarray(tensor[np.ix_(trace, trace)], dtype=np.complex128)
    factor = lu_factor(a_ii, check_finite=True)
    recovery = lu_solve(factor, a_it, check_finite=True)
    schur = np.ascontiguousarray(a_tt - a_ti @ recovery)
    probe = _probe(len(interior), offset)
    rhs = a_ii @ probe
    recovered = lu_solve(factor, rhs, check_finite=True)
    solve_relative = _relative(recovered, probe)
    if not np.all(np.isfinite(schur)) or not np.isfinite(solve_relative):
        raise RuntimeError("interior Schur construction is not finite")
    return schur, solve_relative


def _readonly(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


@dataclass
class FixedP6LORCellBridge:
    """Local oriented p6 trace and mapped LOR trace Schur operators."""

    fine_trace_operator: np.ndarray | None
    lor_trace_operator: np.ndarray | None
    trace_transfer: np.ndarray | None
    p6_trace_rows: np.ndarray | None
    lor_boundary_rows: np.ndarray | None
    audit: dict[str, Any]
    _lor_trace_lu: tuple[np.ndarray, np.ndarray] | None = field(
        repr=False, default=None
    )
    _trace_transfer_lu: tuple[np.ndarray, np.ndarray] | None = field(
        repr=False, default=None
    )
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def _require_alive(self) -> None:
        if self._destroyed:
            raise RuntimeError("fixed p6/LOR cell bridge is destroyed")

    def apply_fine_trace_schur(self, vector: np.ndarray) -> np.ndarray:
        """Apply the oriented p6 trace Schur complement."""

        self._require_alive()
        values = _as_vector(vector, _TRACE_DOF)
        assert self.fine_trace_operator is not None
        return np.asarray(self.fine_trace_operator @ values)

    def apply_mapped_lor_trace(self, vector: np.ndarray) -> np.ndarray:
        """Apply ``R_tᴴ S_l R_t`` in oriented p6 trace coordinates."""

        self._require_alive()
        values = _as_vector(vector, _TRACE_DOF)
        assert self.trace_transfer is not None
        assert self.lor_trace_operator is not None
        mapped = self.trace_transfer @ values
        return np.asarray(
            self.trace_transfer.conj().T
            @ (self.lor_trace_operator @ mapped)
        )

    def solve_mapped_lor_trace(self, rhs: np.ndarray) -> np.ndarray:
        """Solve the mapped LOR trace operator using only local factors."""

        self._require_alive()
        values = _as_vector(rhs, _TRACE_DOF)
        assert self._lor_trace_lu is not None
        assert self._trace_transfer_lu is not None
        lor_rhs = lu_solve(
            self._trace_transfer_lu,
            values,
            trans=2,
            check_finite=True,
        )
        lor_solution = lu_solve(
            self._lor_trace_lu,
            lor_rhs,
            check_finite=True,
        )
        return np.asarray(
            lu_solve(self._trace_transfer_lu, lor_solution, check_finite=True)
        )

    def destroy(self) -> None:
        """Release retained local trace arrays and factors exactly once."""

        if self._destroyed:
            return
        self.fine_trace_operator = None
        self.lor_trace_operator = None
        self.trace_transfer = None
        self.p6_trace_rows = None
        self.lor_boundary_rows = None
        self._lor_trace_lu = None
        self._trace_transfer_lu = None
        self._destroyed = True


def build_fixed_p6_lor_cell_bridge(
    widths: tuple[float, float, float],
    *,
    curl_coefficient: complex,
    mass_coefficient: complex,
    cell_info: int | np.ndarray,
) -> FixedP6LORCellBridge:
    """Build one fixed p6/LOR affine cell trace bridge."""

    started = perf_counter()
    physical_widths = _widths(widths)
    info_value = _cell_info(cell_info)
    curl = complex(curl_coefficient)
    mass = complex(mass_coefficient)
    if not np.isfinite(curl.real + 1j * curl.imag) or not np.isfinite(
        mass.real + 1j * mass.imag
    ):
        raise ValueError("Maxwell coefficients must be finite")

    p6 = basix.ufl.element("N1curl", "hexahedron", _P6_DEGREE).basix_element
    p1 = basix.ufl.element("N1curl", "hexahedron", 1).basix_element
    p6_trace, p6_interior = _p6_partition(p6)
    reference = build_fixed_p6_lor_reference_complex()
    lor_boundary, lor_interior = _lor_partition(reference)
    geometry = np.asarray(basix.geometry(basix.CellType.hexahedron), dtype=np.float64)
    topology = basix.topology(basix.CellType.hexahedron)[1]
    cell_rows, cell_signs, cell_mapping_audit = _build_cell_maps(
        reference,
        p1,
        topology,
        geometry,
    )

    spec = AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=curl,
        mass_coefficient_by_tag={0: mass},
    )
    p6_factory = AffineIsotropicMaxwellTensorFactory(p6, spec)
    p1_factory = AffineIsotropicMaxwellTensorFactory(p1, spec)
    p6_raw = np.asarray(
        p6_factory.tensor(tag=0, widths=physical_widths),
        dtype=np.complex128,
    )
    p1_local = np.asarray(
        p1_factory.tensor(
            tag=0,
            widths=tuple(value / _LOR_SUBDIVISION for value in physical_widths),
        ),
        dtype=np.complex128,
    )
    transient_bytes = int(p6_raw.nbytes + p1_local.nbytes)
    del p6_factory, p1_factory

    coefficient_transform = _coefficient_transform(p6, info_value)
    oriented_p6 = _orient_tensor(p6, p6_raw, info_value)
    transient_bytes += int(
        coefficient_transform.nbytes + oriented_p6.nbytes
    )
    orientation_mixing = max(
        float(np.max(np.abs(coefficient_transform[np.ix_(p6_trace, p6_interior)]))),
        float(np.max(np.abs(coefficient_transform[np.ix_(p6_interior, p6_trace)]))),
    )
    orientation_change = float(
        np.max(np.abs(coefficient_transform - np.eye(_P6_DOF)))
    )
    orientation_tensor_relative = _relative(
        oriented_p6,
        coefficient_transform @ p6_raw @ coefficient_transform.T,
    )
    p6_schur, p6_interior_solve = _interior_schur(
        oriented_p6,
        p6_trace,
        p6_interior,
        0.11,
    )

    lor_full = _assemble_lor(cell_rows, cell_signs, p1_local)
    transient_bytes += int(
        lor_full.data.nbytes + lor_full.indices.nbytes + lor_full.indptr.nbytes
    )
    lor_dense = np.asarray(lor_full.toarray(), dtype=np.complex128)
    transient_bytes += int(lor_dense.nbytes)
    lor_schur, lor_interior_solve = _interior_schur(
        lor_dense,
        lor_boundary,
        lor_interior,
        0.17,
    )

    transfer = build_fixed_p6_lor_reference_transfer()
    r1 = np.asarray(transfer.R1, dtype=np.complex128)
    transient_bytes += int(r1.nbytes)
    oriented_r1 = r1 @ coefficient_transform.T
    cross_block = r1[np.ix_(lor_boundary, p6_interior)]
    cross_block_max = float(np.max(np.abs(cross_block)))
    trace_transfer = np.ascontiguousarray(
        oriented_r1[np.ix_(lor_boundary, p6_trace)]
    )
    transfer_rank = int(np.linalg.matrix_rank(trace_transfer))
    if transfer_rank != _TRACE_DOF:
        raise RuntimeError("oriented p6 trace transfer is rank deficient")
    if orientation_mixing > _SUPPORT_TOL:
        raise RuntimeError("Basix cell orientation mixes p6 trace and interior")
    if cross_block_max > _SUPPORT_TOL:
        raise RuntimeError(
            "LOR boundary to p6 interior transfer is not structurally zero"
        )
    if orientation_tensor_relative > _ACTION_TOL:
        raise RuntimeError("p6 tensor orientation does not match T A T^T")

    trace_transfer_lu = lu_factor(trace_transfer, check_finite=True)
    lor_trace_lu = lu_factor(lor_schur, check_finite=True)
    trace_probe = _probe(_TRACE_DOF, 0.29)
    mapped_probe = trace_transfer.conj().T @ (
        lor_schur @ (trace_transfer @ trace_probe)
    )
    mapped_solution = lu_solve(
        trace_transfer_lu,
        mapped_probe,
        trans=2,
        check_finite=True,
    )
    mapped_solution = lu_solve(lor_trace_lu, mapped_solution, check_finite=True)
    mapped_solution = lu_solve(
        trace_transfer_lu,
        mapped_solution,
        check_finite=True,
    )
    mapped_solve_relative = _relative(mapped_solution, trace_probe)
    fine_probe = p6_schur @ trace_probe
    fine_vs_mapped_relative = _relative(fine_probe, mapped_probe)
    if not np.isfinite(mapped_solve_relative) or mapped_solve_relative > _ACTION_TOL:
        raise RuntimeError("mapped LOR trace solve residual is not qualified")

    retained_bytes = int(
        p6_schur.nbytes
        + lor_schur.nbytes
        + trace_transfer.nbytes
        + sum(array.nbytes for array in lor_trace_lu)
        + sum(array.nbytes for array in trace_transfer_lu)
    )
    finite = bool(
        np.all(np.isfinite(p6_schur))
        and np.all(np.isfinite(lor_schur))
        and np.all(np.isfinite(trace_transfer))
        and np.isfinite(
            [
                cross_block_max,
                orientation_mixing,
                orientation_tensor_relative,
                p6_interior_solve,
                lor_interior_solve,
                mapped_solve_relative,
                fine_vs_mapped_relative,
            ]
        ).all()
    )
    checks = {
        "finite": finite,
        "p6_partition": len(p6_trace) == _TRACE_DOF
        and len(p6_interior) == _INTERIOR_DOF,
        "lor_partition": len(lor_boundary) == _TRACE_DOF
        and len(lor_interior) == _INTERIOR_DOF,
        "r1_boundary_interior_support": cross_block_max <= _SUPPORT_TOL,
        "orientation_trace_interior_block": orientation_mixing <= _SUPPORT_TOL,
        "orientation_tensor": orientation_tensor_relative <= _ACTION_TOL,
        "trace_transfer_rank": transfer_rank == _TRACE_DOF,
        "cell_mapping": bool(
            cell_mapping_audit["pass"]
            and cell_mapping_audit["constant_field_pass"]
        ),
        "reference_transfer": bool(transfer.audit["pass"]),
        "interior_solve": max(p6_interior_solve, lor_interior_solve)
        <= _ACTION_TOL,
        "mapped_trace_solve": mapped_solve_relative <= _ACTION_TOL,
    }
    audit = {
        "schema_version": "task040.fixed-lor.l2a.v1",
        "status": "fixed_p6_lor_cell_trace_bridge_qualified",
        "pass": bool(all(checks.values())),
        "scope": "component_mechanism_only_not_5nm_signal",
        "operator": "oriented_p6_trace_schur_and_mapped_lor_trace",
        "cell": {
            "widths": physical_widths,
            "cell_info": info_value,
            "material_class": "axis_aligned_affine_isotropic",
            "curl_coefficient": _pair(curl),
            "mass_coefficient": _pair(mass),
            "ordinary_defaults_unchanged": True,
            "physics_unchanged": True,
        },
        "partitions": {
            "p6_dofs": _P6_DOF,
            "p6_trace": _TRACE_DOF,
            "p6_interior": _INTERIOR_DOF,
            "p6_trace_unique": bool(len(np.unique(p6_trace)) == _TRACE_DOF),
            "p6_interior_unique": bool(
                len(np.unique(p6_interior)) == _INTERIOR_DOF
            ),
            "p6_disjoint_complete": bool(
                not np.intersect1d(p6_trace, p6_interior).size
                and np.array_equal(
                    np.sort(np.concatenate((p6_trace, p6_interior))),
                    np.arange(_P6_DOF, dtype=np.int32),
                )
            ),
            "lor_dofs": _LOR_DOF,
            "lor_boundary": _TRACE_DOF,
            "lor_interior": _INTERIOR_DOF,
            "lor_disjoint_complete": bool(
                len(np.unique(np.concatenate((lor_boundary, lor_interior))))
                == _LOR_DOF
            ),
            "p6_trace_source": "Basix entity_dofs dimensions 0,1,2",
            "lor_boundary_source": "canonical LOR edge keys on box boundary",
        },
        "lor_cell_mapping": cell_mapping_audit,
        "orientation": {
            "nonzero_cell_info": bool(info_value != 0),
            "changed_entries_max": orientation_change,
            "trace_interior_mixing_max": orientation_mixing,
            "tensor_TAT_relative": orientation_tensor_relative,
            "transform_semantics": "Basix T_apply followed by T A T^T",
        },
        "transfer": {
            "R1_shape": tuple(map(int, r1.shape)),
            "trace_shape": tuple(map(int, trace_transfer.shape)),
            "trace_rank": transfer_rank,
            "boundary_p6_interior_max_abs": cross_block_max,
            "formula": "R_t = R1[lor_boundary,p6_trace] T_trace^T",
        },
        "operators": {
            "p6_raw_shape": tuple(map(int, p6_raw.shape)),
            "lor_raw_shape": tuple(map(int, lor_dense.shape)),
            "p6_trace_schur_shape": tuple(map(int, p6_schur.shape)),
            "lor_trace_schur_shape": tuple(map(int, lor_schur.shape)),
            "mapped_formula": "R_t^H S_l R_t",
            "local_interior_factor_rows": {
                "p6": _INTERIOR_DOF,
                "lor": _INTERIOR_DOF,
            },
            "max_local_factor_rows": _INTERIOR_DOF,
        },
        "solve_audit": {
            "p6_interior_relative": p6_interior_solve,
            "lor_interior_relative": lor_interior_solve,
            "mapped_trace_relative": mapped_solve_relative,
        },
        "diagnostics": {
            "fine_vs_mapped_trace_relative": fine_vs_mapped_relative,
            "not_a_positive_signal": True,
        },
        "checks": checks,
        "lifecycle": {
            "selected_transient_array_bytes_not_peak": transient_bytes,
            "retained_trace_bridge_bytes": retained_bytes,
            "full_cell_transient_released_before_return": True,
            "destroy_supported": True,
        },
        "forbidden_objects": {
            "global_F": False,
            "global_AIJ": False,
            "global_factor": False,
            "numeric_allgather": False,
            "full_basis_replication": False,
            "petsc": False,
            "mpi": False,
            "dolfinx": False,
        },
        "wall_seconds": float(perf_counter() - started),
    }
    if not audit["pass"]:
        raise RuntimeError(f"fixed p6/LOR cell bridge audit failed: {checks}")

    for array in (
        p6_schur,
        lor_schur,
        trace_transfer,
        p6_trace,
        lor_boundary,
        *lor_trace_lu,
        *trace_transfer_lu,
    ):
        _readonly(array)
    del (
        p6_raw,
        p1_local,
        oriented_p6,
        coefficient_transform,
        transfer,
        r1,
        oriented_r1,
        lor_full,
        lor_dense,
        cell_rows,
        cell_signs,
        reference,
        p6,
        p1,
    )
    return FixedP6LORCellBridge(
        fine_trace_operator=p6_schur,
        lor_trace_operator=lor_schur,
        trace_transfer=trace_transfer,
        p6_trace_rows=p6_trace,
        lor_boundary_rows=lor_boundary,
        audit=audit,
        _lor_trace_lu=lor_trace_lu,
        _trace_transfer_lu=trace_transfer_lu,
    )
