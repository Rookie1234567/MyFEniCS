"""PETSc owner-local full-side coupled action for Task040 V3-2.

This carrier performs the five block-elimination steps needed by the V3-2
mechanism oracle without constructing ``PetscInterfaceSchurOracle`` or a
full-side direct factor.  It retains exactly three interior ``A_II`` factors,
the three ``A_I,Gamma`` coupling matrices, owner-local Gamma ``Z/Y`` rows,
and PETSc work vectors.  The only numeric collective in ``apply`` is the
small ``Y^H r_Gamma`` reduction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse

__all__ = (
    "PetscCoupledFullSideAction",
    "build_petsc_coupled_full_side_action",
)


def _row_hash(rows: np.ndarray) -> str:
    value = np.ascontiguousarray(np.asarray(rows, dtype=np.int64))
    return hashlib.sha256(value.tobytes()).hexdigest()


def _matrix_hash(matrix: np.ndarray) -> str:
    value = np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128))
    return hashlib.sha256(value.tobytes()).hexdigest()


def _support_values(support: Mapping[str, Any] | Sequence[int]) -> np.ndarray:
    values = support["active_support"] if isinstance(support, Mapping) else support
    rows = np.asarray(values, dtype=np.int64).reshape(-1)
    if rows.size != np.unique(rows).size:
        raise ValueError("Gamma support rows must be unique")
    return rows


def _make_scatter(
    parent: PETSc.Vec, source_is: PETSc.IS, target: PETSc.Vec
) -> PETSc.Scatter:
    first, last = map(int, target.getOwnershipRange())
    positions = PETSc.IS().createStride(
        last - first,
        first=first,
        step=1,
        comm=parent.getComm(),
    )
    try:
        return PETSc.Scatter().create(parent, source_is, target, positions)
    finally:
        positions.destroy()


class PetscCoupledFullSideAction:
    """Owner-local PETSc implementation of the V3-2 block-Schur action.

    For ``A = [[E, C], [D, B]]`` with ``B`` block diagonal over the three
    interiors, one apply executes::

        x0 = (0, B^-1 b_I)
        q  = b - F x0
        c  = E_joint^-1 Y^H R_Gamma q
        lambda = Z c
        dx_Ig = -A_Ig,Gamma lambda solved by the same A_Ig,Ig factor
        dx = (lambda, dx_I0, dx_I1, dx_I2)

    ``E_joint`` is loaded from the augmented packet; this carrier never
    constructs an interface Schur oracle.  Gamma row order is supplied by
    ``gamma_rows_local`` and is used for the cached Gamma IS/scatter, so the
    group input order is not treated as a canonical order.
    """

    def __init__(
        self,
        *,
        bare_f: PETSc.Mat,
        group_rows: Sequence[np.ndarray],
        lower_support: Mapping[str, Any] | Sequence[int],
        upper_support: Mapping[str, Any] | Sequence[int],
        gamma_rows_local: np.ndarray,
        local_z: np.ndarray,
        local_y: np.ndarray,
        joint_matrix: np.ndarray,
        factor_solver_type: str = "mumps",
    ) -> None:
        if not isinstance(bare_f, PETSc.Mat):
            raise TypeError("coupled full-side action requires a PETSc matrix")
        if bare_f.getSize()[0] != bare_f.getSize()[1]:
            raise ValueError("coupled full-side bare F must be square")
        if str(bare_f.getType()).lower() == "python":
            raise ValueError("coupled full-side action requires explicit bare F")
        if len(group_rows) != 3:
            raise ValueError("coupled full-side action requires three groups")

        self._bare_f = bare_f
        self._comm = bare_f.getComm().tompi4py()
        self._parent = bare_f.createVecRight()
        self._destroyed = False
        self._apply_count = 0
        self._factors: list[ResearchExactFactorInverse] = []
        self._couplings: list[PETSc.Mat] = []
        self._interior_scatters: list[PETSc.Scatter] = []
        self._interior_rhs: list[PETSc.Vec] = []
        self._interior_solution: list[PETSc.Vec] = []
        self._gamma_scatter: PETSc.Scatter | None = None
        self._gamma_rhs: PETSc.Vec | None = None
        self._gamma_correction: PETSc.Vec | None = None
        self._base: PETSc.Vec | None = None
        self._residual: PETSc.Vec | None = None
        self._joint_svd: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._joint_shape: tuple[int, int] = (0, 0)
        self._joint_rank = 0
        self._joint_condition = float("nan")
        self._joint_singular_values: tuple[float, ...] = ()
        self._gamma_global_rows = 0
        self._gamma_rows_local = np.empty(0, dtype=np.int64)
        self._gamma_owner_order_sha256 = _row_hash(self._gamma_rows_local)
        self._joint_sha256 = _matrix_hash(np.empty((0, 0), dtype=np.complex128))
        self._interior_rows_local: tuple[tuple[int, ...], ...] = ()
        self._cross_interior_max = 0.0
        self._cross_interior_norms: tuple[dict[str, Any], ...] = ()
        self._basis_span = 0
        self._parent_ownership_range = tuple(map(int, self._parent.getOwnershipRange()))
        self._joint = np.asarray(joint_matrix)
        self._local_z = np.asarray(local_z)
        self._local_y = np.asarray(local_y)
        self._factor_solver_type = str(factor_solver_type)

        try:
            self._prepare(
                group_rows,
                lower_support,
                upper_support,
                gamma_rows_local,
            )
        except Exception:
            self.destroy()
            raise

    def _prepare(
        self,
        group_rows: Sequence[np.ndarray],
        lower_support: Mapping[str, Any] | Sequence[int],
        upper_support: Mapping[str, Any] | Sequence[int],
        gamma_rows_local: np.ndarray,
    ) -> None:
        comm = self._comm
        parent_first, parent_last = map(int, self._parent.getOwnershipRange())
        parent_size = int(self._parent.getSize())
        local_ready = True
        try:
            local_groups = [
                np.asarray(rows, dtype=np.int64).reshape(-1) for rows in group_rows
            ]
            gamma_rows = np.asarray(gamma_rows_local, dtype=PETSc.IntType).reshape(-1)
            local_z = self._local_z
            local_y = self._local_y
            local_ready = (
                all(np.unique(rows).size == rows.size for rows in local_groups)
                and np.unique(gamma_rows).size == gamma_rows.size
                and local_z.dtype == np.dtype(np.complex128)
                and local_y.dtype == np.dtype(np.complex128)
                and local_z.ndim == 2
                and local_y.shape == local_z.shape
                and local_z.shape[0] == gamma_rows.size
                and local_z.shape[1] > 0
                and np.isfinite(local_z).all()
                and np.isfinite(local_y).all()
                and self._joint.dtype == np.dtype(np.complex128)
                and self._joint.ndim == 2
                and self._joint.shape[0] == self._joint.shape[1]
                and self._joint.shape[0] == local_z.shape[1]
                and np.isfinite(self._joint).all()
                and all(
                    np.all((rows >= parent_first) & (rows < parent_last))
                    for rows in local_groups
                )
                and np.all((gamma_rows >= 0) & (gamma_rows < parent_size))
            )
        except Exception:
            local_ready = False
            local_groups = []
            gamma_rows = np.empty(0, dtype=np.int64)
        if not bool(comm.allreduce(bool(local_ready), op=MPI.LAND)):
            raise ValueError("coupled PETSc local rows/basis have incompatible shapes")

        spans = int(self._local_z.shape[1])
        span_min = int(comm.allreduce(spans, op=MPI.MIN))
        span_max = int(comm.allreduce(spans, op=MPI.MAX))
        if span_min != span_max:
            raise ValueError("coupled PETSc basis spans differ across ranks")
        joint_sha256 = _matrix_hash(self._joint)
        if len(set(comm.allgather(joint_sha256))) != 1:
            raise ValueError("coupled E_joint differs across MPI ranks")

        lower_local = _support_values(lower_support)
        upper_local = _support_values(upper_support)
        lower_parts = comm.allgather(lower_local.tolist())
        upper_parts = comm.allgather(upper_local.tolist())
        lower = np.asarray(
            [row for part in lower_parts for row in part], dtype=np.int64
        )
        upper = np.asarray(
            [row for part in upper_parts for row in part], dtype=np.int64
        )
        if np.unique(lower).size != lower.size or np.unique(upper).size != upper.size:
            raise ValueError("Gamma support rows are duplicated across owners")
        if not np.all(
            (lower_local >= parent_first) & (lower_local < parent_last)
        ) or not np.all((upper_local >= parent_first) & (upper_local < parent_last)):
            raise ValueError("Gamma supports must be owner-local")
        if np.intersect1d(lower, upper).size:
            raise ValueError("lower and upper Gamma supports overlap")
        gamma_union = np.union1d(lower, upper)
        local_gamma = np.concatenate((lower_local, upper_local))
        if (
            np.unique(local_gamma).size != local_gamma.size
            or set(map(int, gamma_rows)) != set(map(int, local_gamma))
            or np.any(gamma_rows < parent_first)
            or np.any(gamma_rows >= parent_last)
        ):
            raise ValueError("Gamma owner rows do not match local supports")
        gamma_parts = comm.allgather(gamma_rows.tolist())
        global_gamma_rows = np.asarray(
            [row for part in gamma_parts for row in part], dtype=np.int64
        )
        if (
            global_gamma_rows.size != gamma_union.size
            or np.unique(global_gamma_rows).size != global_gamma_rows.size
            or set(map(int, global_gamma_rows)) != set(map(int, gamma_union))
        ):
            raise ValueError("Gamma owner rows do not cover lower/upper supports")

        group_parts = [comm.allgather(rows.tolist()) for rows in local_groups]
        global_groups = [
            np.asarray([row for part in parts for row in part], dtype=np.int64)
            for parts in group_parts
        ]
        if any(rows.size != np.unique(rows).size for rows in global_groups):
            raise ValueError("group owner rows are duplicated across owners")
        group_sets = [set(map(int, rows)) for rows in global_groups]
        expected_gamma = [
            set(map(int, lower)),
            set(map(int, gamma_union)),
            set(map(int, upper)),
        ]
        if any(
            (group_sets[index] & set(map(int, gamma_union))) != expected_gamma[index]
            for index in range(3)
        ):
            raise ValueError("group Gamma coverage does not match lower/upper supports")
        gamma_set = set(map(int, gamma_union))
        interior_sets = [rows - gamma_set for rows in group_sets]
        if any(
            interior_sets[left] & interior_sets[right]
            for left in range(3)
            for right in range(left + 1, 3)
        ):
            raise ValueError("group interiors overlap")
        if len(gamma_set.union(*interior_sets)) != parent_size:
            raise ValueError("Gamma plus group interiors do not cover bare F")

        interior_rows = [
            np.asarray(
                [row for row in local_groups[index] if int(row) not in gamma_set],
                dtype=PETSc.IntType,
            )
            for index in range(3)
        ]
        interior_is = [
            PETSc.IS().createGeneral(rows, comm=self._bare_f.getComm())
            for rows in interior_rows
        ]
        gamma_is = PETSc.IS().createGeneral(gamma_rows, comm=self._bare_f.getComm())
        try:
            cross_interior_norms = []
            for left in range(3):
                for right in range(3):
                    if left == right:
                        continue
                    cross = self._bare_f.createSubMatrix(
                        interior_is[left], interior_is[right]
                    )
                    try:
                        norm = float(cross.norm(PETSc.NormType.FROBENIUS))
                        local_nnz = int(
                            round(
                                float(
                                    cross.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"]
                                )
                            )
                        )
                    finally:
                        cross.destroy()
                    global_nnz = int(comm.allreduce(local_nnz, op=MPI.SUM))
                    max_local_nnz = int(comm.allreduce(local_nnz, op=MPI.MAX))
                    cross_interior_norms.append(
                        {
                            "direction": f"{left}->{right}",
                            "norm": float(comm.allreduce(norm, op=MPI.MAX)),
                            "nnz": global_nnz,
                            "max_local_nnz": max_local_nnz,
                        }
                    )
            cross_interior_max = max(
                (item["norm"] for item in cross_interior_norms),
                default=0.0,
            )
            if cross_interior_max > 1.0e-12:
                raise ValueError("bare F has cross-group interior coupling")

            for index in range(3):
                a_ii = None
                factor = None
                coupling = None
                try:
                    a_ii = self._bare_f.createSubMatrix(
                        interior_is[index], interior_is[index]
                    )
                    coupling = self._bare_f.createSubMatrix(
                        interior_is[index], gamma_is
                    )
                    factor = ResearchExactFactorInverse(
                        a_ii,
                        factor_solver_type=self._factor_solver_type,
                        factor_only_storage=True,
                    )
                    factor.release_borrowed_matrix()
                    self._factors.append(factor)
                    factor = None
                    self._couplings.append(coupling)
                    coupling = None
                    template = self._factors[-1].operator.createVecRight()
                    self._interior_rhs.append(template.duplicate())
                    self._interior_solution.append(template)
                    self._interior_scatters.append(
                        _make_scatter(self._parent, interior_is[index], template)
                    )
                finally:
                    if coupling is not None:
                        coupling.destroy()
                    if factor is not None:
                        factor.destroy()
                    if a_ii is not None:
                        a_ii.destroy()

            if not self._factors or self._factors[0].operator is None:
                raise RuntimeError("coupled PETSc factors have no operator")
            self._gamma_rhs = self._couplings[0].createVecRight()
            if self._gamma_rhs.getLocalSize() != gamma_rows.size:
                raise ValueError("Gamma Vec ownership differs from Z/Y rows")
            self._gamma_correction = self._gamma_rhs.duplicate()
            self._gamma_scatter = _make_scatter(self._parent, gamma_is, self._gamma_rhs)
            self._base = self._parent.duplicate()
            self._residual = self._parent.duplicate()
        finally:
            gamma_is.destroy()
            for index_is in interior_is:
                index_is.destroy()

        u, singular_values, vh = np.linalg.svd(self._joint, full_matrices=False)
        tolerance = np.finfo(float).eps * max(self._joint.shape) * singular_values[0]
        rank = int(np.count_nonzero(singular_values > tolerance))
        if rank != self._joint.shape[0]:
            raise ValueError("coupled E_joint is numerically singular")
        self._joint_svd = (u, singular_values, vh)
        self._joint_shape = tuple(int(item) for item in self._joint.shape)
        self._joint_rank = rank
        self._joint_condition = float(singular_values[0] / singular_values[-1])
        self._joint_singular_values = tuple(float(item) for item in singular_values)
        self._joint_sha256 = joint_sha256
        if not np.isfinite(self._joint_condition) or self._joint_condition > 1.0e12:
            raise ValueError("coupled E_joint condition exceeds 1e12")
        self._gamma_global_rows = int(global_gamma_rows.size)
        self._gamma_rows_local = gamma_rows.copy()
        self._gamma_owner_order_sha256 = _row_hash(global_gamma_rows)
        self._interior_rows_local = tuple(
            tuple(int(row) for row in rows) for rows in interior_rows
        )
        self._cross_interior_max = cross_interior_max
        self._cross_interior_norms = tuple(cross_interior_norms)
        self._basis_span = span_min

    def _check_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("coupled PETSc full-side action is destroyed")

    def _check_parent_layout(self, vector: PETSc.Vec) -> None:
        if (
            vector.getSize() != self._parent.getSize()
            or vector.getLocalSize() != self._parent.getLocalSize()
            or tuple(map(int, vector.getOwnershipRange()))
            != tuple(map(int, self._parent.getOwnershipRange()))
        ):
            raise ValueError("coupled PETSc Vec has the wrong owner layout")

    def _solve_joint(self, rhs: np.ndarray) -> np.ndarray:
        u, singular_values, vh = self._joint_svd
        projected = u.conj().T @ rhs
        return vh.conj().T @ (projected / singular_values)

    def _base_correction(self, source: PETSc.Vec) -> None:
        self._base.set(0.0)
        for scatter, rhs, solution, factor in zip(
            self._interior_scatters,
            self._interior_rhs,
            self._interior_solution,
            self._factors,
            strict=True,
        ):
            scatter.scatter(
                source,
                rhs,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            factor.solve(rhs, solution)
            scatter.scatter(
                solution,
                self._base,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        self._base.assemble()

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the full-side coupled correction into ``target``."""

        self._check_live()
        self._check_parent_layout(source)
        self._check_parent_layout(target)
        self._base_correction(source)
        self._bare_f.mult(self._base, self._residual)
        self._residual.scale(PETSc.ScalarType(-1.0))
        self._residual.axpy(PETSc.ScalarType(1.0), source)

        self._gamma_scatter.scatter(
            self._residual,
            self._gamma_rhs,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        local_rhs = self._local_y.conj().T @ np.asarray(
            self._gamma_rhs.array, dtype=np.complex128
        )
        rhs = np.empty_like(local_rhs)
        self._comm.Allreduce(local_rhs, rhs, op=MPI.SUM)
        coefficients = self._solve_joint(rhs)
        self._gamma_correction.array[:] = np.asarray(
            self._local_z @ coefficients, dtype=PETSc.ScalarType
        )
        self._gamma_correction.assemble()

        target.set(0.0)
        self._gamma_scatter.scatter(
            self._gamma_correction,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        for index, (coupling, rhs, solution, factor) in enumerate(
            zip(
                self._couplings,
                self._interior_rhs,
                self._interior_solution,
                self._factors,
                strict=True,
            )
        ):
            coupling.mult(self._gamma_correction, rhs)
            rhs.scale(PETSc.ScalarType(-1.0))
            factor.solve(rhs, solution)
            self._interior_scatters[index].scatter(
                solution,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.axpy(PETSc.ScalarType(1.0), self._base)
        target.assemble()
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        factor_ready = 0 if self._destroyed else len(self._factors)
        return {
            "schema": "task040.v3_2.petsc_full_side_coupled.v1",
            "packet_dependent": True,
            "gamma_global_rows": self._gamma_global_rows,
            "gamma_rows_local": self._gamma_rows_local.size,
            "gamma_rows_local_sha256": _row_hash(self._gamma_rows_local),
            "gamma_owner_order_sha256": self._gamma_owner_order_sha256,
            "gamma_order_owner_local": True,
            "basis_span": self._basis_span,
            "interior_rows_local": [len(rows) for rows in self._interior_rows_local],
            "ownership_range": list(self._parent_ownership_range),
            "cross_interior_coupling_max": self._cross_interior_max,
            "cross_interior_coupling_norms": list(self._cross_interior_norms),
            "cross_interior_coupling_pass": self._cross_interior_max <= 1.0e-12,
            "joint_shape": list(self._joint_shape),
            "joint_sha256": self._joint_sha256,
            "joint_rank": self._joint_rank,
            "joint_condition": self._joint_condition,
            "joint_singular_values": list(self._joint_singular_values),
            "cross_section_group_factor_count": factor_ready,
            "exact_interface_schur_oracle_object_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "reduced_dense_factor_count": 0 if self._destroyed else 1,
            "nested_ksp_count": 0,
            "normal_equations": False,
            "fe_numeric_allgather": False,
            "basis_owner_local": True,
            "basis_replication_verified": False,
            "factor_count_ready": factor_ready,
            "factor_count_after_cleanup": 0 if self._destroyed else None,
            "apply_count": self._apply_count,
            "reduced_dense_factor_retained": bool(
                not self._destroyed and self._joint_svd is not None
            ),
            "group_factors_retained": factor_ready > 0,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._gamma_scatter is not None:
            self._gamma_scatter.destroy()
            self._gamma_scatter = None
        for scatter in reversed(self._interior_scatters):
            scatter.destroy()
        self._interior_scatters.clear()
        for vector in (
            self._gamma_correction,
            self._gamma_rhs,
            self._base,
            self._residual,
        ):
            if vector is not None:
                vector.destroy()
        self._gamma_correction = None
        self._gamma_rhs = None
        self._base = None
        self._residual = None
        if self._parent is not None:
            self._parent.destroy()
            self._parent = None
        for vector in reversed(self._interior_solution):
            vector.destroy()
        for vector in reversed(self._interior_rhs):
            vector.destroy()
        self._interior_solution.clear()
        self._interior_rhs.clear()
        for matrix in reversed(self._couplings):
            matrix.destroy()
        self._couplings.clear()
        for factor in reversed(self._factors):
            factor.destroy()
        self._factors.clear()
        self._joint_svd = None
        self._joint = np.empty((0, 0), dtype=np.complex128)
        self._local_z = np.empty((0, 0), dtype=np.complex128)
        self._local_y = np.empty((0, 0), dtype=np.complex128)
        self._bare_f = None
        self._destroyed = True


def build_petsc_coupled_full_side_action(
    **kwargs: Any,
) -> PetscCoupledFullSideAction:
    """Build the explicit opt-in Task040 PETSc coupled carrier."""

    return PetscCoupledFullSideAction(**kwargs)
