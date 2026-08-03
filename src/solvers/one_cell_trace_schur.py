"""Research-only exact one-cell endpoint Schur correctness oracle.

The full endpoint Schur square is never formed.  This module keeps sparse
port/interior blocks and one factorization of the axial-interior block, then
applies the exact two-port operator to a small number of trace columns.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Sequence

import numpy as np
from dolfinx import fem
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import AssemblyTimeCondensedSystem


RESEARCH_STATUS = "research_only_correctness_oracle"


def _int_array(values: Iterable[int]) -> np.ndarray:
    return np.asarray(tuple(values), dtype=PETSc.IntType)


def _array_sha256(values: np.ndarray) -> str:
    array = np.asarray(values)
    payload = np.ascontiguousarray(array).view(np.uint8)
    return hashlib.sha256(payload).hexdigest()


def _replicated_dense_columns(matrix: PETSc.Mat) -> np.ndarray:
    """Gather one distributed dense matrix collectively, preserving columns."""

    first, last = map(int, matrix.getOwnershipRange())
    packets = (
        matrix.getComm()
        .tompi4py()
        .allgather(
            (
                first,
                last,
                np.asarray(
                    matrix.getDenseArray(readonly=True), dtype=np.complex128
                ).copy(),
            )
        )
    )
    rows, columns = map(int, matrix.getSize())
    result = np.empty((rows, columns), dtype=np.complex128)
    covered = np.zeros(rows, dtype=bool)
    for start, stop, values in packets:
        result[int(start) : int(stop), :] = values
        covered[int(start) : int(stop)] = True
    if not np.all(covered):
        raise RuntimeError("Dense Schur action ownership did not close.")
    return result


@dataclass(frozen=True)
class EndpointActiveRows:
    """Research-only canonical endpoint identities in active numbering."""

    left_original: np.ndarray
    right_original: np.ndarray
    left_active: np.ndarray
    right_active: np.ndarray
    interior_active: np.ndarray
    left_original_sha256: str
    right_original_sha256: str
    left_active_sha256: str
    right_active_sha256: str
    interior_active_sha256: str

    @property
    def port_active(self) -> np.ndarray:
        return np.concatenate((self.left_active, self.right_active))

    def to_record(self) -> dict[str, Any]:
        return {
            "left_original_rows": int(len(self.left_original)),
            "right_original_rows": int(len(self.right_original)),
            "left_active_rows": int(len(self.left_active)),
            "right_active_rows": int(len(self.right_active)),
            "axial_internal_active_rows": int(len(self.interior_active)),
            "left_original_sha256": self.left_original_sha256,
            "right_original_sha256": self.right_original_sha256,
            "left_active_sha256": self.left_active_sha256,
            "right_active_sha256": self.right_active_sha256,
            "axial_internal_active_sha256": self.interior_active_sha256,
            "left_right_disjoint": bool(
                not np.intersect1d(
                    self.left_active,
                    self.right_active,
                    assume_unique=True,
                ).size
            ),
        }


def _owned_original_rows_on_facets(
    V: Any,
    facets: np.ndarray,
) -> np.ndarray:
    """Return globally unique original DoFs on a distributed facet closure."""

    local = np.unique(
        np.asarray(
            fem.locate_dofs_topological(
                V,
                V.mesh.topology.dim - 1,
                np.asarray(facets, dtype=np.int32),
                remote=True,
            ),
            dtype=np.int64,
        )
    )
    index_map = V.dofmap.index_map
    owned = local[(local >= 0) & (local < int(index_map.size_local))]
    global_owned = np.asarray(
        index_map.local_to_global(owned.astype(np.int32)),
        dtype=np.int64,
    )
    packets = V.mesh.comm.allgather(global_owned)
    return np.asarray(
        sorted({int(value) for packet in packets for value in packet}),
        dtype=PETSc.IntType,
    )


def identify_endpoint_active_rows(
    V: Any,
    condensed: AssemblyTimeCondensedSystem,
    *,
    left_facets: np.ndarray,
    right_facets: np.ndarray,
) -> EndpointActiveRows:
    """Identify the oracle's left, right, and axial-interior active rows."""

    left_original = _owned_original_rows_on_facets(V, left_facets)
    right_original = _owned_original_rows_on_facets(V, right_facets)
    if np.intersect1d(
        left_original,
        right_original,
        assume_unique=True,
    ).size:
        raise RuntimeError("The one-cell left and right original trace rows overlap.")

    constraints = condensed.trace_constraints

    def expanded(original_rows: np.ndarray) -> np.ndarray:
        active: set[int] = set()
        for original in original_rows:
            expansion = constraints.expansion_by_original.get(int(original))
            if expansion is None:
                raise RuntimeError(
                    f"Endpoint row {int(original)} is not a condensed trace row."
                )
            active.update(int(value) for value in expansion[0])
        return np.asarray(sorted(active), dtype=PETSc.IntType)

    left_active = expanded(left_original)
    right_active = expanded(right_original)
    overlap = np.intersect1d(
        left_active,
        right_active,
        assume_unique=True,
    )
    if len(overlap):
        raise RuntimeError(
            "Floquet reduction mixed the left and right z-face row sets: "
            f"{overlap[:8].tolist()}."
        )
    all_active = np.arange(condensed.active_rows, dtype=PETSc.IntType)
    port_active = np.concatenate((left_active, right_active))
    interior_active = np.setdiff1d(
        all_active,
        port_active,
        assume_unique=True,
    ).astype(PETSc.IntType, copy=False)
    if (
        len(left_active) + len(right_active) + len(interior_active)
        != condensed.active_rows
    ):
        raise RuntimeError("One-cell active row accounting does not close.")
    return EndpointActiveRows(
        left_original=left_original,
        right_original=right_original,
        left_active=left_active,
        right_active=right_active,
        interior_active=interior_active,
        left_original_sha256=_array_sha256(left_original.astype(np.int64)),
        right_original_sha256=_array_sha256(right_original.astype(np.int64)),
        left_active_sha256=_array_sha256(left_active.astype(np.int64)),
        right_active_sha256=_array_sha256(right_active.astype(np.int64)),
        interior_active_sha256=_array_sha256(interior_active.astype(np.int64)),
    )


def _factor(matrix: PETSc.Mat) -> PETSc.KSP:
    ksp = PETSc.KSP().create(matrix.getComm())
    ksp.setType(PETSc.KSP.Type.PREONLY)
    ksp.setErrorIfNotConverged(True)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.LU)
    pc.setFactorSolverType("mumps")
    ksp.setOperators(matrix)
    pc.setFactorSetUpSolverType()
    try:
        pc.getFactorMatrix().setMumpsIcntl(14, 100)
    except PETSc.Error:
        pass
    ksp.setUp()
    return ksp


def _partition_sparse_matrix(
    matrix: PETSc.Mat,
    port: np.ndarray,
    interior: np.ndarray,
) -> tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat, PETSc.Mat]:
    """Copy a distributed AIJ into stable port/interior numberings."""

    port_map = {int(old): new for new, old in enumerate(port)}
    interior_map = {int(old): new for new, old in enumerate(interior)}
    first, last = matrix.getOwnershipRange()
    local_port = port[(port >= first) & (port < last)]
    local_interior = interior[(interior >= first) & (interior < last)]

    def create(
        local_rows: int,
        global_rows: int,
        local_columns: int,
        global_columns: int,
    ) -> PETSc.Mat:
        result = PETSc.Mat().createAIJ(
            size=(
                (local_rows, global_rows),
                (local_columns, global_columns),
            ),
            comm=matrix.getComm(),
        )
        result.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
        return result

    A_pp = create(len(local_port), len(port), len(local_port), len(port))
    A_pi = create(len(local_port), len(port), len(local_interior), len(interior))
    A_ip = create(len(local_interior), len(interior), len(local_port), len(port))
    A_ii = create(
        len(local_interior),
        len(interior),
        len(local_interior),
        len(interior),
    )
    try:
        for old_row in range(first, last):
            columns, values = matrix.getRow(old_row)
            if old_row in port_map:
                new_row = port_map[old_row]
                row_blocks = (
                    (A_pp, port_map),
                    (A_pi, interior_map),
                )
            elif old_row in interior_map:
                new_row = interior_map[old_row]
                row_blocks = (
                    (A_ip, port_map),
                    (A_ii, interior_map),
                )
            else:
                raise RuntimeError(f"Active row {old_row} belongs to neither P nor I.")
            for block, column_map in row_blocks:
                selected = [
                    (column_map[int(column)], value)
                    for column, value in zip(columns, values, strict=True)
                    if int(column) in column_map
                ]
                if selected:
                    block.setValues(
                        _int_array([new_row]),
                        _int_array(item[0] for item in selected),
                        np.asarray(
                            [item[1] for item in selected],
                            dtype=PETSc.ScalarType,
                        ).reshape(1, -1),
                    )
        for block in (A_pp, A_pi, A_ip, A_ii):
            block.assemble()
        return A_pp, A_pi, A_ip, A_ii
    except Exception:
        for block in (A_pp, A_pi, A_ip, A_ii):
            block.destroy()
        raise


@dataclass
class OneCellTwoPortSchurAction:
    """Research-only action of the exact full endpoint Schur operator."""

    A_pp: PETSc.Mat
    A_pi: PETSc.Mat
    A_ip: PETSc.Mat
    A_ii: PETSc.Mat
    factor: PETSc.KSP
    left_rows: int
    right_rows: int
    interior_rows: int
    interior_matrix_nnz: int
    port_active: np.ndarray
    interior_active: np.ndarray
    dense_interface_square_formed: bool = False
    _destroyed: bool = False

    @property
    def port_rows(self) -> int:
        return int(self.left_rows + self.right_rows)

    @staticmethod
    def _replicated_values(vector: PETSc.Vec) -> np.ndarray:
        comm = vector.getComm().tompi4py()
        first, last = map(int, vector.getOwnershipRange())
        packets = comm.allgather(
            (
                first,
                last,
                np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy(),
            )
        )
        result = np.empty(int(vector.getSize()), dtype=np.complex128)
        filled = np.zeros(len(result), dtype=bool)
        for start, stop, values in packets:
            result[int(start) : int(stop)] = values
            filled[int(start) : int(stop)] = True
        if not np.all(filled):
            raise RuntimeError("Two-port Schur action ownership did not close.")
        return result

    def recover_homogeneous_columns(self, port_values: np.ndarray) -> np.ndarray:
        """Recover eliminated active interiors for a zero cell RHS."""

        columns = np.asarray(port_values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns[:, None]
        if columns.ndim != 2 or columns.shape[0] != self.port_rows:
            raise ValueError(
                "Homogeneous recovery columns must have shape "
                f"({self.port_rows}, n), got {columns.shape}."
            )
        if self._destroyed:
            raise RuntimeError("The two-port Schur action has been destroyed.")
        port_vector = self.A_pp.createVecRight()
        interior_rhs = self.A_ip.createVecLeft()
        interior_solution = self.A_ii.createVecRight()
        recovered = np.zeros(
            (
                len(self.port_active) + len(self.interior_active),
                columns.shape[1],
            ),
            dtype=np.complex128,
        )
        try:
            first, last = map(int, port_vector.getOwnershipRange())
            recovered[self.port_active, :] = columns
            for column in range(columns.shape[1]):
                port_vector.getArray()[:] = np.asarray(
                    columns[first:last, column], dtype=PETSc.ScalarType
                )
                port_vector.assemble()
                self.A_ip.mult(port_vector, interior_rhs)
                self.factor.solve(interior_rhs, interior_solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError(
                        "The homogeneous interior recovery did not converge."
                    )
                recovered[self.interior_active, column] = -self._replicated_values(
                    interior_solution
                )
        finally:
            interior_solution.destroy()
            interior_rhs.destroy()
            port_vector.destroy()
        return recovered

    def apply_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the exact endpoint Schur without forming its dense square."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.port_rows:
            raise ValueError(
                "Two-port Schur columns must have shape "
                f"({self.port_rows}, n), got {columns.shape}."
            )
        if self._destroyed:
            raise RuntimeError("The two-port Schur action has been destroyed.")

        dense_port = None
        interior_rhs = None
        interior_solution = None
        port_action = None
        port_correction = None
        try:
            first, last = map(int, self.A_pp.getOwnershipRangeColumn())
            dense_port = PETSc.Mat().createDense(
                size=((last - first, self.port_rows), columns.shape[1]),
                comm=self.A_pp.getComm(),
            )
            dense_port.getDenseArray()[:, :] = columns[first:last, :]
            dense_port.assemble()
            interior_rhs = self.A_ip.matMult(dense_port)
            interior_solution = interior_rhs.duplicate(copy=False)
            self.factor.matSolve(interior_rhs, interior_solution)
            if int(self.factor.getConvergedReason()) < 0:
                raise RuntimeError(
                    "The one-cell interior Schur solve did not converge."
                )
            port_action = self.A_pp.matMult(dense_port)
            port_correction = self.A_pi.matMult(interior_solution)
            port_action.axpy(PETSc.ScalarType(-1.0), port_correction)
            return _replicated_dense_columns(port_action)
        finally:
            for obj in (
                port_correction,
                port_action,
                interior_solution,
                interior_rhs,
                dense_port,
            ):
                if obj is not None:
                    obj.destroy()

    def apply_adjoint_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the Hermitian-transpose endpoint Schur to columns."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.port_rows:
            raise ValueError(
                "Adjoint two-port Schur columns must have shape "
                f"({self.port_rows}, n), got {columns.shape}."
            )
        if self._destroyed:
            raise RuntimeError("The two-port Schur action has been destroyed.")

        port_input = self.A_pp.createVecLeft()
        port_action = self.A_pp.createVecRight()
        interior_rhs = self.A_pi.createVecRight()
        transpose_rhs = self.A_ii.createVecRight()
        transpose_solution = self.A_ii.createVecLeft()
        correction = self.A_ip.createVecRight()
        result = np.empty_like(columns)
        try:
            first, last = map(int, port_input.getOwnershipRange())
            for column in range(columns.shape[1]):
                port_input.getArray()[:] = np.asarray(
                    columns[first:last, column], dtype=PETSc.ScalarType
                )
                port_input.assemble()
                self.A_pp.multHermitian(port_input, port_action)
                self.A_pi.multHermitian(port_input, interior_rhs)
                transpose_rhs.getArray()[:] = np.conj(
                    interior_rhs.getArray(readonly=True)
                )
                transpose_rhs.assemble()
                self.factor.solveTranspose(
                    transpose_rhs,
                    transpose_solution,
                )
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError(
                        "The Hermitian-transpose interior Schur solve did not converge."
                    )
                transpose_solution.getArray()[:] = np.conj(
                    transpose_solution.getArray(readonly=True)
                )
                transpose_solution.assemble()
                self.A_ip.multHermitian(transpose_solution, correction)
                port_action.axpy(PETSc.ScalarType(-1.0), correction)
                result[:, column] = self._replicated_values(port_action)
        finally:
            for obj in (
                correction,
                transpose_solution,
                transpose_rhs,
                interior_rhs,
                port_action,
                port_input,
            ):
                obj.destroy()
        return result

    def destroy(self) -> None:
        if self._destroyed:
            return
        for obj in (
            self.factor,
            self.A_ii,
            self.A_ip,
            self.A_pi,
            self.A_pp,
        ):
            obj.destroy()
        self._destroyed = True


def endpoint_cauchy_columns(
    action: OneCellTwoPortSchurAction,
    state_columns: np.ndarray,
    adjoint_state_columns: np.ndarray,
    *,
    multipliers: Sequence[complex],
    adjoint_multipliers: Sequence[complex],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract research-oracle endpoint electric and traction columns."""

    electric_state = np.asarray(state_columns, dtype=np.complex128)
    adjoint_state = np.asarray(adjoint_state_columns, dtype=np.complex128)
    state_rows = action.left_rows + action.interior_rows
    if electric_state.ndim == 1:
        electric_state = electric_state[:, None]
    if adjoint_state.ndim == 1:
        adjoint_state = adjoint_state[:, None]
    if electric_state.shape[0] != state_rows or adjoint_state.shape[0] != state_rows:
        raise ValueError("Full augmented states have the wrong row count.")
    electric_left = electric_state[: action.left_rows, :]
    adjoint_left = adjoint_state[: action.left_rows, :]
    if electric_left.shape != adjoint_left.shape:
        raise ValueError("Endpoint Cauchy columns have inconsistent shapes.")
    count = electric_left.shape[1]
    lam = np.asarray(multipliers, dtype=np.complex128)
    nu = np.asarray(adjoint_multipliers, dtype=np.complex128)
    if lam.shape != (count,) or nu.shape != (count,):
        raise ValueError("Endpoint Cauchy multiplier counts differ.")
    electric = np.vstack((electric_left, electric_left * lam[None, :]))
    adjoint = np.vstack((adjoint_left, adjoint_left * nu[None, :]))
    port_input = action.A_pp.createVecRight()
    port_action = action.A_pp.createVecLeft()
    interior_input = action.A_pi.createVecRight()
    port_correction = action.A_pi.createVecLeft()
    adjoint_port_input = action.A_pp.createVecLeft()
    adjoint_port_action = action.A_pp.createVecRight()
    adjoint_interior_input = action.A_ip.createVecLeft()
    adjoint_port_correction = action.A_ip.createVecRight()
    traction = np.empty_like(electric)
    adjoint_traction = np.empty_like(adjoint)
    try:
        primal_port_first, primal_port_last = map(int, port_input.getOwnershipRange())
        adjoint_port_first, adjoint_port_last = map(
            int, adjoint_port_input.getOwnershipRange()
        )
        primal_interior_first, primal_interior_last = map(
            int, interior_input.getOwnershipRange()
        )
        adjoint_interior_first, adjoint_interior_last = map(
            int, adjoint_interior_input.getOwnershipRange()
        )
        for column in range(count):
            port_input.getArray()[:] = np.asarray(
                electric[primal_port_first:primal_port_last, column],
                dtype=PETSc.ScalarType,
            )
            port_input.assemble()
            interior_input.getArray()[:] = np.asarray(
                electric_state[
                    action.left_rows + primal_interior_first : action.left_rows
                    + primal_interior_last,
                    column,
                ],
                dtype=PETSc.ScalarType,
            )
            interior_input.assemble()
            action.A_pp.mult(port_input, port_action)
            action.A_pi.mult(interior_input, port_correction)
            port_action.axpy(PETSc.ScalarType(1.0), port_correction)
            traction[:, column] = action._replicated_values(port_action)

            adjoint_port_input.getArray()[:] = np.asarray(
                adjoint[adjoint_port_first:adjoint_port_last, column],
                dtype=PETSc.ScalarType,
            )
            adjoint_port_input.assemble()
            adjoint_interior_input.getArray()[:] = np.asarray(
                nu[column]
                * adjoint_state[
                    action.left_rows + adjoint_interior_first : action.left_rows
                    + adjoint_interior_last,
                    column,
                ],
                dtype=PETSc.ScalarType,
            )
            adjoint_interior_input.assemble()
            action.A_pp.multHermitian(adjoint_port_input, adjoint_port_action)
            action.A_ip.multHermitian(adjoint_interior_input, adjoint_port_correction)
            adjoint_port_action.axpy(PETSc.ScalarType(1.0), adjoint_port_correction)
            adjoint_traction[:, column] = action._replicated_values(adjoint_port_action)
    finally:
        for obj in (
            adjoint_port_correction,
            adjoint_interior_input,
            adjoint_port_action,
            adjoint_port_input,
            port_correction,
            interior_input,
            port_action,
            port_input,
        ):
            obj.destroy()
    return electric, traction, adjoint, adjoint_traction


def endpoint_cauchy_balance(
    action: OneCellTwoPortSchurAction,
    state_columns: np.ndarray,
    adjoint_state_columns: np.ndarray,
    *,
    multipliers: Sequence[complex],
    adjoint_multipliers: Sequence[complex],
) -> dict[str, float]:
    """Pair oracle endpoint Cauchy data and report normalized balances."""

    electric, traction, adjoint, adjoint_traction = endpoint_cauchy_columns(
        action,
        state_columns,
        adjoint_state_columns,
        multipliers=multipliers,
        adjoint_multipliers=adjoint_multipliers,
    )
    left = action.left_rows
    lam = np.asarray(multipliers, dtype=np.complex128)
    nu = np.asarray(adjoint_multipliers, dtype=np.complex128)
    count = electric.shape[1]
    primal_balance = traction[left:, :] + traction[:left, :] * lam[None, :]
    adjoint_balance = (
        adjoint_traction[left:, :] + adjoint_traction[:left, :] * nu[None, :]
    )
    green_left = np.sum(np.conj(adjoint) * traction, axis=0)
    green_right = np.sum(
        np.conj(adjoint_traction) * electric,
        axis=0,
    )
    scale = max(
        float(np.linalg.norm(adjoint) * np.linalg.norm(traction)),
        float(np.linalg.norm(adjoint_traction) * np.linalg.norm(electric)),
        1.0e-30,
    )
    return {
        "primal_outward_balance_relative": float(
            np.linalg.norm(primal_balance)
            / max(float(np.linalg.norm(traction)), 1.0e-30)
        ),
        "adjoint_outward_balance_relative": float(
            np.linalg.norm(adjoint_balance)
            / max(float(np.linalg.norm(adjoint_traction)), 1.0e-30)
        ),
        "green_pairing_relative": float(
            np.linalg.norm(green_left - green_right) / scale
        ),
        "columns": int(count),
    }


def build_one_cell_two_port_schur_action(
    matrix: PETSc.Mat,
    rows: EndpointActiveRows,
) -> OneCellTwoPortSchurAction:
    """Build the research-only exact action without a dense port square."""

    A_pp, A_pi, A_ip, A_ii = _partition_sparse_matrix(
        matrix,
        rows.port_active,
        rows.interior_active,
    )
    factor = None
    try:
        factor = _factor(A_ii)
        nnz = int(A_ii.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM).get("nz_used", 0.0))
        return OneCellTwoPortSchurAction(
            A_pp=A_pp,
            A_pi=A_pi,
            A_ip=A_ip,
            A_ii=A_ii,
            factor=factor,
            left_rows=len(rows.left_active),
            right_rows=len(rows.right_active),
            interior_rows=len(rows.interior_active),
            interior_matrix_nnz=nnz,
            port_active=np.asarray(rows.port_active, dtype=PETSc.IntType).copy(),
            interior_active=np.asarray(
                rows.interior_active, dtype=PETSc.IntType
            ).copy(),
        )
    except Exception:
        for obj in (factor, A_ii, A_ip, A_pi, A_pp):
            if obj is not None:
                obj.destroy()
        raise
