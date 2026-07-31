"""Exact one-z-cell discrete Bloch audit helpers for Task036.

This module is deliberately an audit path, not a propagation replacement.
It assembles no full-interface dense square.  The only dense objects retained
are rectangular endpoint mode columns and projected ``M x M`` blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Sequence

import numpy as np
from dolfinx import cpp, fem
from mpi4py import MPI
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import (
    _DistributedTwoDimensionalEvaluator,
)
from .hcurl_assembly_time_condensation import AssemblyTimeCondensedSystem


def _int_array(values: Iterable[int]) -> np.ndarray:
    return np.asarray(tuple(values), dtype=PETSc.IntType)


def _array_sha256(values: np.ndarray) -> str:
    array = np.asarray(values)
    payload = np.ascontiguousarray(array).view(np.uint8)
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class EndpointActiveRows:
    """Canonical endpoint identities in the active condensed numbering."""

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
    """Partition active rows into left port, right port, and axial interior."""

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
        len(left_active)
        + len(right_active)
        + len(interior_active)
        != condensed.active_rows
    ):
        raise RuntimeError("One-cell active row accounting does not close.")
    return EndpointActiveRows(
        left_original=left_original,
        right_original=right_original,
        left_active=left_active,
        right_active=right_active,
        interior_active=interior_active,
        left_original_sha256=_array_sha256(
            left_original.astype(np.int64)
        ),
        right_original_sha256=_array_sha256(
            right_original.astype(np.int64)
        ),
        left_active_sha256=_array_sha256(left_active.astype(np.int64)),
        right_active_sha256=_array_sha256(right_active.astype(np.int64)),
        interior_active_sha256=_array_sha256(
            interior_active.astype(np.int64)
        ),
    )


class EndpointModeLifter:
    """Lift a canonical 2D tangential trace through one real 3D H(curl) layer."""

    def __init__(self, V: Any, *, axis_scale_nm: float) -> None:
        self.V = V
        msh = V.mesh
        self.target = fem.Function(V)
        self.cells = np.arange(
            msh.topology.index_map(msh.topology.dim).size_local,
            dtype=np.int32,
        )
        self.points = np.asarray(
            cpp.fem.interpolation_coords(
                V.element._cpp_object,
                msh.geometry._cpp_object,
                self.cells,
            ),
            dtype=np.float64,
        )
        self.padding = 1.0e-10 * max(float(axis_scale_nm), 1.0)
        self.evaluator: _DistributedTwoDimensionalEvaluator | None = None
        self.point_cell_keys: np.ndarray | None = None

    def _keys(
        self,
        evaluator: _DistributedTwoDimensionalEvaluator,
    ) -> np.ndarray:
        coordinates = self.points
        points = (
            np.asarray(coordinates.T, dtype=np.float64)
            if coordinates.shape[0] == 3
            else np.asarray(coordinates, dtype=np.float64)
        )
        return np.asarray(
            [
                evaluator._cell_key(float(point[0]), float(point[1]))
                for point in points
            ],
            dtype=np.int64,
        ).reshape(-1, 2)

    def lift(self, source: fem.Function) -> fem.Function:
        if self.evaluator is None:
            self.evaluator = _DistributedTwoDimensionalEvaluator(
                source,
                padding=self.padding,
            )
            self.point_cell_keys = self._keys(self.evaluator)
        else:
            self.evaluator.set_source(source)
        assert self.point_cell_keys is not None
        values = self.evaluator.evaluate_points(
            self.points,
            cell_keys=self.point_cell_keys,
        )

        def cached(x: np.ndarray) -> np.ndarray:
            if (
                np.asarray(x).shape != self.points.shape
                or not np.allclose(
                    x,
                    self.points,
                    rtol=0.0,
                    atol=1.0e-13,
                )
            ):
                raise RuntimeError(
                    "One-cell H(curl) interpolation points changed ordering."
                )
            return values

        self.target.x.array[:] = 0.0
        self.target.interpolate(cached, self.cells)
        self.target.x.scatter_forward()
        return self.target


def _active_values_for_port(
    field: fem.Function,
    condensed: AssemblyTimeCondensedSystem,
    port_rows: np.ndarray,
) -> np.ndarray:
    """Replicate endpoint root values in a frozen active-row order."""

    constraints = condensed.trace_constraints
    requested = {int(value) for value in port_rows}
    originals: list[int] = []
    active: list[int] = []
    for original in constraints.owned_active_original_dofs:
        reduced = int(constraints.original_to_active[int(original)])
        if reduced in requested:
            originals.append(int(original))
            active.append(reduced)
    vector = field.x.petsc_vec
    values = (
        np.asarray(
            vector.getValues(_int_array(originals)),
            dtype=np.complex128,
        )
        if originals
        else np.empty(0, dtype=np.complex128)
    )
    packets = field.function_space.mesh.comm.allgather(
        (
            np.asarray(active, dtype=np.int64),
            values,
        )
    )
    position = {int(row): index for index, row in enumerate(port_rows)}
    result = np.empty(len(port_rows), dtype=np.complex128)
    seen = np.zeros(len(port_rows), dtype=bool)
    for rows, packet_values in packets:
        for row, value in zip(rows, packet_values, strict=True):
            index = position[int(row)]
            if seen[index]:
                raise RuntimeError("An endpoint active row has two owners.")
            result[index] = value
            seen[index] = True
    if not np.all(seen):
        raise RuntimeError(
            "Endpoint lift did not populate every independent active row."
        )
    return result


def lifted_endpoint_columns(
    sources: Sequence[fem.Function],
    lifter: EndpointModeLifter,
    condensed: AssemblyTimeCondensedSystem,
    rows: EndpointActiveRows,
    *,
    mpc: Any,
    constraint_data: Any | None = None,
    constraint_residuals: list[dict[str, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return rectangular left/right endpoint columns for canonical traces."""

    left = np.empty((len(rows.left_active), len(sources)), dtype=np.complex128)
    right = np.empty(
        (len(rows.right_active), len(sources)),
        dtype=np.complex128,
    )
    for column, source in enumerate(sources):
        field = lifter.lift(source)
        if constraint_residuals is not None:
            if constraint_data is None:
                raise ValueError(
                    "Constraint residual collection requires raw Floquet data."
                )
            constraint_residuals.append(
                _mpc_constraint_relative_residual(field, constraint_data)
            )
        mpc.homogenize(field)
        field.x.scatter_forward()
        left[:, column] = _active_values_for_port(
            field,
            condensed,
            rows.left_active,
        )
        right[:, column] = _active_values_for_port(
            field,
            condensed,
            rows.right_active,
        )
    return left, right


def _mpc_constraint_relative_residual(
    field: fem.Function,
    constraint_data: Any,
) -> dict[str, float]:
    """Check a physical lift directly against sparse oriented MPC rows."""

    field.x.scatter_forward()
    slaves = np.asarray(
        constraint_data.slave_local_dofs,
        dtype=np.int64,
    )
    original = np.asarray(
        field.x.array[slaves],
        dtype=np.complex128,
    ).copy()
    index_map = field.function_space.dofmap.index_map
    block_size = int(field.function_space.dofmap.index_map_bs)
    if block_size != 1:
        raise NotImplementedError(
            "Task036 direct Floquet-row audit requires scalar DoF numbering."
        )
    owned = int(index_map.size_local)
    local_field_norm_squared = float(
        np.vdot(field.x.array[:owned], field.x.array[:owned]).real
    )
    ownership_start, ownership_stop = map(int, index_map.local_range)
    packets = field.function_space.mesh.comm.allgather(
        (
            ownership_start,
            ownership_stop,
            np.asarray(
                field.x.array[:owned],
                dtype=np.complex128,
            ).copy(),
        )
    )
    global_values = np.empty(
        int(index_map.size_global),
        dtype=np.complex128,
    )
    filled = np.zeros(len(global_values), dtype=bool)
    for start, stop, values in packets:
        global_values[int(start) : int(stop)] = values
        filled[int(start) : int(stop)] = True
    if not np.all(filled):
        raise RuntimeError("Direct Floquet closure global values do not close.")
    masters = np.asarray(
        constraint_data.master_global_dofs,
        dtype=np.int64,
    )
    coefficients = np.asarray(
        constraint_data.coefficients,
        dtype=np.complex128,
    )
    offsets = np.asarray(constraint_data.offsets, dtype=np.int64)
    if len(offsets) != len(slaves) + 1:
        raise RuntimeError("Direct Floquet closure offset count differs.")
    reconstructed = np.asarray(
        [
            np.dot(
                coefficients[offsets[row] : offsets[row + 1]],
                global_values[masters[offsets[row] : offsets[row + 1]]],
            )
            for row in range(len(slaves))
        ],
        dtype=np.complex128,
    )
    local_numerator = float(
        np.vdot(
            reconstructed - original,
            reconstructed - original,
        ).real
    )
    local_original = float(np.vdot(original, original).real)
    local_reconstructed = float(
        np.vdot(reconstructed, reconstructed).real
    )
    comm = field.function_space.mesh.comm
    numerator = float(comm.allreduce(local_numerator, op=MPI.SUM))
    original_norm = float(
        np.sqrt(comm.allreduce(local_original, op=MPI.SUM))
    )
    reconstructed_norm = float(
        np.sqrt(comm.allreduce(local_reconstructed, op=MPI.SUM))
    )
    field_norm = float(
        np.sqrt(comm.allreduce(local_field_norm_squared, op=MPI.SUM))
    )
    difference_norm = float(np.sqrt(numerator))
    relative = difference_norm / max(
        original_norm,
        reconstructed_norm,
        field_norm,
        1.0e-300,
    )
    return {
        "global_normwise_relative": float(relative),
        "difference_l2": difference_norm,
        "original_slave_l2": original_norm,
        "reconstructed_slave_l2": reconstructed_norm,
        "original_full_owned_l2": field_norm,
    }


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
    """Copy a distributed AIJ into stable P/I block numberings.

    PETSc 3.19's optimized ``MatCreateSubMatrix_MPIAIJ_SameRowColDist`` can
    reject a legitimate sparse endpoint selection when one MPI partition has
    a different off-diagonal ordering.  Explicit sparse reinsertion is small
    for the one-cell audit and keeps empty-rank ownership unambiguous.
    """

    port_map = {int(old): new for new, old in enumerate(port)}
    interior_map = {
        int(old): new for new, old in enumerate(interior)
    }
    first, last = matrix.getOwnershipRange()
    local_port = port[(port >= first) & (port < last)]
    local_interior = interior[
        (interior >= first) & (interior < last)
    ]

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
        result.setOption(
            PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,
            False,
        )
        return result

    A_pp = create(
        len(local_port),
        len(port),
        len(local_port),
        len(port),
    )
    A_pi = create(
        len(local_port),
        len(port),
        len(local_interior),
        len(interior),
    )
    A_ip = create(
        len(local_interior),
        len(interior),
        len(local_port),
        len(port),
    )
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
                p_columns = [
                    (port_map[int(column)], value)
                    for column, value in zip(
                        columns,
                        values,
                        strict=True,
                    )
                    if int(column) in port_map
                ]
                i_columns = [
                    (interior_map[int(column)], value)
                    for column, value in zip(
                        columns,
                        values,
                        strict=True,
                    )
                    if int(column) in interior_map
                ]
                if p_columns:
                    A_pp.setValues(
                        _int_array([new_row]),
                        _int_array(item[0] for item in p_columns),
                        np.asarray(
                            [item[1] for item in p_columns],
                            dtype=PETSc.ScalarType,
                        ).reshape(1, -1),
                    )
                if i_columns:
                    A_pi.setValues(
                        _int_array([new_row]),
                        _int_array(item[0] for item in i_columns),
                        np.asarray(
                            [item[1] for item in i_columns],
                            dtype=PETSc.ScalarType,
                        ).reshape(1, -1),
                    )
            elif old_row in interior_map:
                new_row = interior_map[old_row]
                p_columns = [
                    (port_map[int(column)], value)
                    for column, value in zip(
                        columns,
                        values,
                        strict=True,
                    )
                    if int(column) in port_map
                ]
                i_columns = [
                    (interior_map[int(column)], value)
                    for column, value in zip(
                        columns,
                        values,
                        strict=True,
                    )
                    if int(column) in interior_map
                ]
                if p_columns:
                    A_ip.setValues(
                        _int_array([new_row]),
                        _int_array(item[0] for item in p_columns),
                        np.asarray(
                            [item[1] for item in p_columns],
                            dtype=PETSc.ScalarType,
                        ).reshape(1, -1),
                    )
                if i_columns:
                    A_ii.setValues(
                        _int_array([new_row]),
                        _int_array(item[0] for item in i_columns),
                        np.asarray(
                            [item[1] for item in i_columns],
                            dtype=PETSc.ScalarType,
                        ).reshape(1, -1),
                    )
            else:
                raise RuntimeError(
                    f"Active row {old_row} belongs to neither P nor I."
                )
        for block in (A_pp, A_pi, A_ip, A_ii):
            block.assemble()
        return A_pp, A_pi, A_ip, A_ii
    except Exception:
        for block in (A_pp, A_pi, A_ip, A_ii):
            block.destroy()
        raise


@dataclass
class ProjectedTwoPortSchur:
    """Small projected blocks plus resource-safe construction telemetry."""

    S_LL: np.ndarray
    S_LR: np.ndarray
    S_RL: np.ndarray
    S_RR: np.ndarray
    port_rows: int
    interior_rows: int
    interior_matrix_nnz: int
    dense_interface_square_formed: bool = False

    def destroy(self) -> None:
        return None


@dataclass
class OneCellTwoPortSchurAction:
    """Resource-bounded action of the exact full endpoint Schur operator.

    The endpoint Schur matrix itself is never formed.  The object retains the
    sparse ``P/I`` blocks and one factor of ``A_ii`` and applies

    ``(A_pp - A_pi A_ii^-1 A_ip) X``

    to a small set of replicated endpoint columns.  This is an audit helper;
    it does not replace the production Hybrid propagation operator.
    """

    A_pp: PETSc.Mat
    A_pi: PETSc.Mat
    A_ip: PETSc.Mat
    A_ii: PETSc.Mat
    factor: PETSc.KSP
    left_rows: int
    right_rows: int
    interior_rows: int
    interior_matrix_nnz: int
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
                np.asarray(
                    vector.getArray(readonly=True),
                    dtype=np.complex128,
                ).copy(),
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

    def apply_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the exact endpoint Schur to replicated endpoint columns."""

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

        port_vector = self.A_pp.createVecRight()
        interior_rhs = self.A_ip.createVecLeft()
        interior_solution = self.A_ii.createVecRight()
        port_action = self.A_pp.createVecLeft()
        port_correction = self.A_pi.createVecLeft()
        result = np.empty_like(columns)
        try:
            first, last = map(int, port_vector.getOwnershipRange())
            for column in range(columns.shape[1]):
                port_vector.getArray()[:] = np.asarray(
                    columns[first:last, column],
                    dtype=PETSc.ScalarType,
                )
                port_vector.assemble()
                self.A_ip.mult(port_vector, interior_rhs)
                self.factor.solve(interior_rhs, interior_solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError(
                        "The one-cell interior Schur solve did not converge."
                    )
                self.A_pp.mult(port_vector, port_action)
                self.A_pi.mult(interior_solution, port_correction)
                port_action.axpy(
                    PETSc.ScalarType(-1.0),
                    port_correction,
                )
                result[:, column] = self._replicated_values(port_action)
        finally:
            for obj in (
                port_correction,
                port_action,
                interior_solution,
                interior_rhs,
                port_vector,
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


def build_one_cell_two_port_schur_action(
    matrix: PETSc.Mat,
    rows: EndpointActiveRows,
) -> OneCellTwoPortSchurAction:
    """Factor the axial-interior block without forming a dense port square."""

    A_pp, A_pi, A_ip, A_ii = _partition_sparse_matrix(
        matrix,
        rows.port_active,
        rows.interior_active,
    )
    factor = None
    try:
        factor = _factor(A_ii)
        nnz = int(
            A_ii.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM).get(
                "nz_used",
                0.0,
            )
        )
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
        )
    except Exception:
        for obj in (factor, A_ii, A_ip, A_pi, A_pp):
            if obj is not None:
                obj.destroy()
        raise


def build_projected_two_port_schur(
    matrix: PETSc.Mat,
    rows: EndpointActiveRows,
    *,
    right_left: np.ndarray,
    right_right: np.ndarray,
    petrov_left: np.ndarray,
    petrov_right: np.ndarray,
) -> ProjectedTwoPortSchur:
    """Apply the second Schur only to modal columns and Petrov-project it."""

    mode_count = int(right_left.shape[1])
    expected = {
        right_left.shape,
        right_right.shape,
        petrov_left.shape,
        petrov_right.shape,
    }
    if len(expected) != 2:
        # The first dimensions differ between the two endpoint row sets, while
        # each endpoint's right/Petrov pair must agree.
        if right_left.shape != petrov_left.shape or (
            right_right.shape != petrov_right.shape
        ):
            raise ValueError("Right and Petrov endpoint column shapes differ.")
    if (
        right_right.shape[1] != mode_count
        or petrov_left.shape[1] != mode_count
        or petrov_right.shape[1] != mode_count
    ):
        raise ValueError("All endpoint bases must use the same mode count.")

    action = build_one_cell_two_port_schur_action(matrix, rows)
    try:
        R_values = np.zeros(
            (action.port_rows, 2 * mode_count),
            dtype=np.complex128,
        )
        R_values[: len(rows.left_active), :mode_count] = right_left
        R_values[len(rows.left_active) :, mode_count:] = right_right
        W_values = np.zeros_like(R_values)
        W_values[: len(rows.left_active), :mode_count] = petrov_left
        W_values[len(rows.left_active) :, mode_count:] = petrov_right
        projected = W_values.conj().T @ action.apply_columns(R_values)
        S_LL = projected[:mode_count, :mode_count].copy()
        S_LR = projected[:mode_count, mode_count:].copy()
        S_RL = projected[mode_count:, :mode_count].copy()
        S_RR = projected[mode_count:, mode_count:].copy()
        return ProjectedTwoPortSchur(
            S_LL=S_LL,
            S_LR=S_LR,
            S_RL=S_RL,
            S_RR=S_RR,
            port_rows=action.port_rows,
            interior_rows=action.interior_rows,
            interior_matrix_nnz=action.interior_matrix_nnz,
        )
    finally:
        action.destroy()


def compose_projected_two_port_schur(
    left: ProjectedTwoPortSchur,
    right: ProjectedTwoPortSchur,
) -> tuple[ProjectedTwoPortSchur, dict[str, float]]:
    """Compose adjacent projected ports by a stable internal Schur solve."""

    shapes = {
        left.S_LL.shape,
        left.S_LR.shape,
        left.S_RL.shape,
        left.S_RR.shape,
        right.S_LL.shape,
        right.S_LR.shape,
        right.S_RL.shape,
        right.S_RR.shape,
    }
    if len(shapes) != 1:
        raise ValueError("Projected two-port block shapes differ.")
    shape = next(iter(shapes))
    if len(shape) != 2 or shape[0] != shape[1]:
        raise ValueError("Projected two-port blocks must be square.")
    pivot = left.S_RR + right.S_LL
    condition = float(np.linalg.cond(pivot))
    if not np.isfinite(condition) or condition > 1.0e12:
        raise RuntimeError(
            "Projected port composition pivot is ill-conditioned: "
            f"cond={condition:.6e}."
        )
    solved_left = np.linalg.solve(pivot, left.S_RL)
    solved_right = np.linalg.solve(pivot, right.S_LR)
    residual = max(
        float(
            np.linalg.norm(pivot @ solved_left - left.S_RL, ord="fro")
            / max(np.linalg.norm(left.S_RL, ord="fro"), 1.0e-30)
        ),
        float(
            np.linalg.norm(pivot @ solved_right - right.S_LR, ord="fro")
            / max(np.linalg.norm(right.S_LR, ord="fro"), 1.0e-30)
        ),
    )
    result = ProjectedTwoPortSchur(
        S_LL=left.S_LL - left.S_LR @ solved_left,
        S_LR=-left.S_LR @ solved_right,
        S_RL=-right.S_RL @ solved_left,
        S_RR=right.S_RR - right.S_RL @ solved_right,
        port_rows=left.port_rows,
        interior_rows=(
            left.interior_rows + right.interior_rows + shape[0]
        ),
        interior_matrix_nnz=(
            left.interior_matrix_nnz + right.interior_matrix_nnz
        ),
    )
    return result, {
        "pivot_condition": condition,
        "pivot_solve_relative_residual": residual,
        "pivot_smallest_singular_value": float(
            np.linalg.svd(pivot, compute_uv=False)[-1]
        ),
    }


def scalar_cg_sign_fixture(q: complex) -> dict[str, float]:
    """Validate the outward-flux polynomial on the p1 analytic cell."""

    q = complex(q)
    a = 1.0 - q * q / 3.0
    b = -1.0 - q * q / 6.0
    cosine = -a / b
    root = cosine + np.lib.scimath.sqrt(cosine * cosine - 1.0)
    other = cosine - np.lib.scimath.sqrt(cosine * cosine - 1.0)
    lam = root if abs(root) <= 1.0 + 1.0e-12 else other
    polynomial = b + 2.0 * a * lam + b * lam * lam
    f_left = a + b * lam
    f_right = b + a * lam
    balance = f_right + lam * f_left
    wrong_balance = f_right - lam * f_left
    scale = max(abs(a), abs(b), 1.0e-30)
    return {
        "lambda_real": float(lam.real),
        "lambda_imag": float(lam.imag),
        "polynomial_relative_residual": float(abs(polynomial) / scale),
        "outward_flux_balance_relative_residual": float(
            abs(balance) / scale
        ),
        "wrong_sign_negative_control_relative_residual": float(
            abs(wrong_balance) / scale
        ),
    }


def _relative_matrix_residual(
    K0: np.ndarray,
    K1: np.ndarray,
    K2: np.ndarray,
    multipliers: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    lam = np.asarray(multipliers, dtype=np.complex128)
    residual = K0 + K1 * lam[np.newaxis, :] + K2 * (
        lam * lam
    )[np.newaxis, :]
    column_scale = (
        np.linalg.norm(K0, axis=0)
        + np.abs(lam) * np.linalg.norm(K1, axis=0)
        + np.abs(lam) ** 2 * np.linalg.norm(K2, axis=0)
    )
    rho = np.linalg.norm(residual, axis=0) / np.maximum(
        column_scale,
        1.0e-30,
    )
    return residual, rho


def _group_residual_reports(
    residual: np.ndarray,
    rho: np.ndarray,
    column_scale: np.ndarray,
    groups: Sequence[Sequence[int]] | None,
) -> list[dict[str, Any]]:
    """Summarize fixed Petrov-coordinate residuals by certified mode group."""

    if groups is None:
        return []
    reports: list[dict[str, Any]] = []
    mode_count = residual.shape[0]
    for group_values in groups:
        indices = np.asarray(tuple(group_values), dtype=np.int64)
        if not len(indices):
            continue
        if np.any(indices < 0) or np.any(indices >= mode_count):
            raise ValueError("A Bloch residual group index is out of range.")
        columns = residual[:, indices]
        scale = max(
            float(np.linalg.norm(column_scale[indices])),
            1.0e-30,
        )
        inside = columns[indices, :]
        outside_rows = np.setdiff1d(
            np.arange(mode_count, dtype=np.int64),
            indices,
            assume_unique=True,
        )
        outside = columns[outside_rows, :]
        reports.append(
            {
                "indices": indices.tolist(),
                "max_rho": float(np.max(rho[indices], initial=0.0)),
                "total_relative": float(
                    np.linalg.norm(columns, ord="fro") / scale
                ),
                "inside_group_relative": float(
                    np.linalg.norm(inside, ord="fro") / scale
                ),
                "outside_group_leakage_relative": float(
                    np.linalg.norm(outside, ord="fro") / scale
                ),
                "coordinate_contract": (
                    "fixed_coordinate_group_diagnostic; not claimed invariant "
                    "under a general non-normal basis rotation"
                ),
            }
        )
    return reports


def _connected_mixing_components(
    residual: np.ndarray,
    column_scale: np.ndarray,
    *,
    edge_threshold: float = 1.0e-8,
) -> dict[str, Any]:
    """Locate stable off-diagonal residual blocks above a frozen threshold."""

    mode_count = residual.shape[0]
    normalized = np.abs(residual) / np.maximum(
        column_scale[np.newaxis, :],
        1.0e-30,
    )
    np.fill_diagonal(normalized, 0.0)
    adjacency = (normalized > edge_threshold) | (
        normalized.T > edge_threshold
    )
    seen = np.zeros(mode_count, dtype=bool)
    components: list[dict[str, Any]] = []
    for root in range(mode_count):
        if seen[root]:
            continue
        stack = [root]
        seen[root] = True
        nodes: list[int] = []
        while stack:
            node = stack.pop()
            nodes.append(node)
            neighbours = np.flatnonzero(adjacency[node])
            for neighbour_value in neighbours:
                neighbour = int(neighbour_value)
                if not seen[neighbour]:
                    seen[neighbour] = True
                    stack.append(neighbour)
        if len(nodes) > 1:
            block = normalized[np.ix_(nodes, nodes)]
            components.append(
                {
                    "indices": sorted(nodes),
                    "max_normalized_edge": float(
                        np.max(block, initial=0.0)
                    ),
                }
            )
    return {
        "edge_threshold": float(edge_threshold),
        "component_count": len(components),
        "components": components,
        "global_max_offdiagonal_normalized": float(
            np.max(normalized, initial=0.0)
        ),
    }


def _significant_residual_summary(
    rho: np.ndarray,
    weights: Sequence[float] | None,
) -> dict[str, Any]:
    if weights is None:
        return {}
    values = np.asarray(weights, dtype=np.float64)
    if values.shape != rho.shape or np.any(values < 0.0):
        raise ValueError("Significant weights have the wrong shape.")
    order = np.argsort(values)[::-1]
    cumulative = np.cumsum(values[order])
    cutoff = (
        len(order)
        if not len(order) or cumulative[-1] <= 0.0
        else int(
            np.searchsorted(
                cumulative,
                (1.0 - 1.0e-8) * cumulative[-1],
                side="left",
            )
            + 1
        )
    )
    significant = order[:cutoff]
    return {
        "weight_definition": (
            "max independently resolved exact-Petrov cell-side directional "
            "amplitude squared; indices retain 1-1e-8 of total weight"
        ),
        "weights": values.tolist(),
        "significant_mode_indices": significant.tolist(),
        "significant_max_rho": float(
            np.max(rho[significant], initial=0.0)
        ),
        "weighted_rho": float(
            np.sqrt(
                np.sum(values * rho * rho)
                / max(np.sum(values), 1.0e-30)
            )
        ),
    }


def bloch_residual_metrics(
    schur: ProjectedTwoPortSchur,
    forward_multipliers: Sequence[complex],
    *,
    backward_multipliers: Sequence[complex] | None = None,
    negative_trace_coordinates: np.ndarray | None = None,
    significant_weights: Sequence[float] | None = None,
    backward_significant_weights: Sequence[float] | None = None,
    forward_groups: Sequence[Sequence[int]] | None = None,
    backward_groups: Sequence[Sequence[int]] | None = None,
) -> dict[str, Any]:
    """Return forward/reverse polynomial residual and cross-mode leakage."""

    forward = np.asarray(forward_multipliers, dtype=np.complex128)
    mode_count = schur.S_LL.shape[0]
    if forward.shape != (mode_count,):
        raise ValueError("Forward multiplier count differs from Schur size.")
    K0 = schur.S_RL
    K1 = schur.S_RR + schur.S_LL
    K2 = schur.S_LR
    residual, rho = _relative_matrix_residual(K0, K1, K2, forward)
    column_scale = (
        np.linalg.norm(K0, axis=0)
        + np.abs(forward) * np.linalg.norm(K1, axis=0)
        + np.abs(forward) ** 2 * np.linalg.norm(K2, axis=0)
    )
    diagonal = np.diag(np.diag(residual))
    offdiagonal = residual - diagonal
    operator_scale = max(
        np.linalg.norm(K0, ord="fro")
        + np.linalg.norm(K1 * forward[np.newaxis, :], ord="fro")
        + np.linalg.norm(
            K2 * (forward * forward)[np.newaxis, :],
            ord="fro",
        ),
        1.0e-30,
    )
    result: dict[str, Any] = {
        "forward": {
            "max_rho": float(np.max(rho, initial=0.0)),
            "median_rho": float(np.median(rho)),
            "rho": rho.tolist(),
            "projected_total_relative": float(
                np.linalg.norm(residual, ord="fro") / operator_scale
            ),
            "projected_diagonal_relative": float(
                np.linalg.norm(diagonal, ord="fro") / operator_scale
            ),
            "projected_offdiagonal_ratio": float(
                np.linalg.norm(offdiagonal, ord="fro") / operator_scale
            ),
            "group_residuals": _group_residual_reports(
                residual,
                rho,
                column_scale,
                forward_groups,
            ),
            "connected_mixing": _connected_mixing_components(
                residual,
                column_scale,
            ),
        }
    }
    result["forward"].update(
        _significant_residual_summary(rho, significant_weights)
    )
    wrong_forward = (
        schur.S_RL
        + (schur.S_RR - schur.S_LL) * forward[np.newaxis, :]
        - schur.S_LR * (forward * forward)[np.newaxis, :]
    )
    result["forward"]["wrong_outward_sign_negative_control_relative"] = float(
        np.linalg.norm(wrong_forward, ord="fro") / operator_scale
    )
    if backward_multipliers is not None:
        backward = np.asarray(
            backward_multipliers,
            dtype=np.complex128,
        )
        coordinates = np.asarray(
            negative_trace_coordinates,
            dtype=np.complex128,
        )
        if backward.shape != (mode_count,) or coordinates.shape != (
            mode_count,
            mode_count,
        ):
            raise ValueError("Backward multiplier/trace shapes are inconsistent.")
        reverse_K0 = schur.S_LR @ coordinates
        reverse_K1 = (schur.S_LL + schur.S_RR) @ coordinates
        reverse_K2 = schur.S_RL @ coordinates
        reverse_residual, reverse_rho = _relative_matrix_residual(
            reverse_K0,
            reverse_K1,
            reverse_K2,
            backward,
        )
        reverse_diagonal = np.diag(np.diag(reverse_residual))
        reverse_column_scale = (
            np.linalg.norm(reverse_K0, axis=0)
            + np.abs(backward) * np.linalg.norm(reverse_K1, axis=0)
            + np.abs(backward) ** 2 * np.linalg.norm(reverse_K2, axis=0)
        )
        reverse_scale = max(
            np.linalg.norm(reverse_K0, ord="fro")
            + np.linalg.norm(
                reverse_K1 * backward[np.newaxis, :],
                ord="fro",
            )
            + np.linalg.norm(
                reverse_K2 * (backward * backward)[np.newaxis, :],
                ord="fro",
            ),
            1.0e-30,
        )
        result["backward"] = {
            "max_rho": float(np.max(reverse_rho, initial=0.0)),
            "median_rho": float(np.median(reverse_rho)),
            "rho": reverse_rho.tolist(),
            "projected_total_relative": float(
                np.linalg.norm(reverse_residual, ord="fro")
                / reverse_scale
            ),
            "projected_offdiagonal_ratio": float(
                np.linalg.norm(
                    reverse_residual - reverse_diagonal,
                    ord="fro",
                )
                / reverse_scale
            ),
            "group_residuals": _group_residual_reports(
                reverse_residual,
                reverse_rho,
                reverse_column_scale,
                backward_groups,
            ),
            "connected_mixing": _connected_mixing_components(
                reverse_residual,
                reverse_column_scale,
            ),
        }
        result["backward"].update(
            _significant_residual_summary(
                reverse_rho,
                backward_significant_weights,
            )
        )
        wrong_reverse = (
            reverse_K0
            + (
                (schur.S_LL - schur.S_RR) @ coordinates
            )
            * backward[np.newaxis, :]
            - reverse_K2 * (backward * backward)[np.newaxis, :]
        )
        result["backward"][
            "wrong_outward_sign_negative_control_relative"
        ] = float(np.linalg.norm(wrong_reverse, ord="fro") / reverse_scale)
    return result


__all__ = [
    "EndpointActiveRows",
    "EndpointModeLifter",
    "OneCellTwoPortSchurAction",
    "ProjectedTwoPortSchur",
    "bloch_residual_metrics",
    "build_one_cell_two_port_schur_action",
    "build_projected_two_port_schur",
    "compose_projected_two_port_schur",
    "identify_endpoint_active_rows",
    "lifted_endpoint_columns",
    "scalar_cg_sign_fixture",
]
