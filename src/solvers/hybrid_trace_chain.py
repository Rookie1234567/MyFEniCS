"""Matrix-free full finite-element trace-chain action for Hybrid stages."""

from __future__ import annotations

from typing import Any

from mpi4py import MPI
import numpy as np
from scipy.linalg import lu_factor, lu_solve
from petsc4py import PETSc


def solve_block_tridiagonal_recursive(
    diagonal_blocks: Any,
    lower_blocks: Any,
    upper_blocks: Any,
    rhs_blocks: Any,
) -> tuple[np.ndarray, dict[str, int]]:
    """Solve a complex, non-Hermitian block-tridiagonal system by Schur recursion.

    ``diagonal_blocks`` contains ``D_i``; ``lower_blocks`` and
    ``upper_blocks`` contain ``L_i`` and ``U_i`` between adjacent blocks.
    ``rhs_blocks`` is a sequence of ``(block_size, n_rhs)`` arrays.  The
    returned solution is stacked in block order.  Only LU factors and the
    recursively updated right-hand sides remain resident.
    """

    diagonal = tuple(np.asarray(block, dtype=np.complex128) for block in diagonal_blocks)
    lower = tuple(np.asarray(block, dtype=np.complex128) for block in lower_blocks)
    upper = tuple(np.asarray(block, dtype=np.complex128) for block in upper_blocks)
    if not diagonal:
        raise ValueError("At least one diagonal block is required.")
    block_count = len(diagonal)
    if len(lower) != block_count - 1 or len(upper) != block_count - 1:
        raise ValueError("Lower and upper block counts must be block_count - 1.")
    block_size = diagonal[0].shape[0]
    if any(block.shape != (block_size, block_size) for block in diagonal):
        raise ValueError("Diagonal blocks must be square and equally sized.")
    if any(block.shape != (block_size, block_size) for block in (*lower, *upper)):
        raise ValueError("Off-diagonal blocks must match the diagonal block size.")
    rhs = tuple(np.asarray(block, dtype=np.complex128) for block in rhs_blocks)
    if len(rhs) != block_count:
        raise ValueError("One RHS block is required for every diagonal block.")
    rhs_columns = rhs[0].shape[1] if rhs[0].ndim == 2 else 1
    rhs = tuple(block.reshape(block_size, rhs_columns) for block in rhs)
    if any(block.shape != (block_size, rhs_columns) for block in rhs):
        raise ValueError("RHS blocks must have a common block-row shape.")

    factors: list[tuple[np.ndarray, np.ndarray]] = []
    reduced_rhs: list[np.ndarray] = [rhs[0].copy()]
    factors.append(lu_factor(diagonal[0].copy(), overwrite_a=True, check_finite=False))
    for index in range(1, block_count):
        previous_factor = factors[index - 1]
        x_block = lu_solve(
            previous_factor,
            upper[index - 1],
            check_finite=False,
        )
        schur = diagonal[index] - lower[index - 1] @ x_block
        z_block = lu_solve(
            previous_factor,
            reduced_rhs[index - 1],
            check_finite=False,
        )
        reduced_rhs.append(rhs[index] - lower[index - 1] @ z_block)
        factors.append(lu_factor(schur, overwrite_a=True, check_finite=False))

    solution: list[np.ndarray] = [np.empty_like(reduced_rhs[0]) for _ in range(block_count)]
    solution[-1] = lu_solve(
        factors[-1],
        reduced_rhs[-1],
        check_finite=False,
    )
    for index in range(block_count - 2, -1, -1):
        solution[index] = lu_solve(
            factors[index],
            reduced_rhs[index] - upper[index] @ solution[index + 1],
            check_finite=False,
        )
    return np.vstack(solution), {
        "block_count": block_count,
        "block_size": block_size,
        "rhs_columns": rhs_columns,
    }


def solve_block_tridiagonal_recursive_mpi(
    diagonal_blocks: Any,
    lower_blocks: Any,
    upper_blocks: Any,
    rhs_blocks: Any,
    *,
    comm: Any = MPI.COMM_WORLD,
) -> tuple[np.ndarray, dict[str, int]]:
    """Solve a block-tridiagonal system with MPI-sharded Schur columns."""
    diagonal = tuple(np.asarray(block, dtype=np.complex128) for block in diagonal_blocks)
    lower = tuple(np.asarray(block, dtype=np.complex128) for block in lower_blocks)
    upper = tuple(np.asarray(block, dtype=np.complex128) for block in upper_blocks)
    if not diagonal:
        raise ValueError("At least one diagonal block is required.")
    block_count = len(diagonal)
    if len(lower) != block_count - 1 or len(upper) != block_count - 1:
        raise ValueError("Lower and upper block counts must be block_count - 1.")
    block_size = int(diagonal[0].shape[0])
    if any(block.shape != (block_size, block_size) for block in diagonal):
        raise ValueError("Diagonal blocks must be square and equally sized.")
    if any(block.shape != (block_size, block_size) for block in (*lower, *upper)):
        raise ValueError("Off-diagonal blocks must match the diagonal block size.")
    if block_size % comm.size:
        raise ValueError("Block columns must divide evenly across MPI ranks.")
    rhs = tuple(np.asarray(block, dtype=np.complex128) for block in rhs_blocks)
    if len(rhs) != block_count:
        raise ValueError("One RHS block is required for every diagonal block.")
    rhs_columns = rhs[0].shape[1] if rhs[0].ndim == 2 else 1
    rhs = tuple(block.reshape(block_size, rhs_columns) for block in rhs)
    if any(block.shape != (block_size, rhs_columns) for block in rhs):
        raise ValueError("RHS blocks must have a common block-row shape.")
    columns_per_rank = block_size // comm.size
    start = comm.rank * columns_per_rank
    stop = start + columns_per_rank
    factors: list[tuple[np.ndarray, np.ndarray]] = []
    reduced_rhs: list[np.ndarray] | None = None
    lu: np.ndarray | None = None
    pivots: np.ndarray | None = None
    def broadcast_factor(error: str | None) -> None:
        nonlocal lu, pivots
        state = comm.bcast(error, root=0)
        if state is not None:
            raise RuntimeError("MPI block factorization failed: " + state)
        if comm.rank != 0:
            lu = np.empty((block_size, block_size), dtype=np.complex128, order="F")
            pivots = np.empty(block_size, dtype=np.int32)
        comm.Bcast(lu, root=0)
        comm.Bcast(pivots, root=0)
    factor_error = None
    if comm.rank == 0:
        try:
            lu, pivots = lu_factor(
                diagonal[0].copy(), overwrite_a=True, check_finite=False
            )
            lu = np.array(lu, dtype=np.complex128, order="F", copy=True)
            pivots = np.asarray(pivots, dtype=np.int32)
            factors.append((lu, pivots))
            reduced_rhs = [rhs[0].copy()]
        except Exception as exc:
            factor_error = f"{type(exc).__name__}: {exc}"
    broadcast_factor(factor_error)
    for index in range(1, block_count):
        local_error = None
        try:
            local_x = np.array(
                lu_solve(
                    (lu, pivots),
                    upper[index - 1][:, start:stop],
                    check_finite=False,
                ),
                dtype=np.complex128,
                order="F",
                copy=True,
            )
            local_product = np.asarray(
                lower[index - 1] @ local_x,
                dtype=np.complex128,
                order="F",
            )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
            local_product = None
        errors = comm.allgather(local_error)
        if any(error is not None for error in errors):
            raise RuntimeError("MPI block column solve failed: " + str(errors))
        if comm.rank == 0:
            x_block = np.empty(
                (block_size, block_size), dtype=np.complex128, order="F"
            )
            recvbuf = x_block.ravel(order="F")
        else:
            recvbuf = None
        comm.Gather(local_product.ravel(order="F"), recvbuf, root=0)
        factor_error = None
        if comm.rank == 0:
            try:
                schur = diagonal[index] - x_block
                reduced_rhs.append(
                    rhs[index]
                    - lower[index - 1]
                    @ lu_solve(factors[-1], reduced_rhs[-1], check_finite=False)
                )
                lu, pivots = lu_factor(schur, overwrite_a=True, check_finite=False)
                lu = np.array(lu, dtype=np.complex128, order="F", copy=True)
                pivots = np.asarray(pivots, dtype=np.int32)
                factors.append((lu, pivots))
            except Exception as exc:
                factor_error = f"{type(exc).__name__}: {exc}"
        broadcast_factor(factor_error)
    solution = None
    solve_error = None
    if comm.rank == 0:
        try:
            solution_blocks = [np.empty_like(reduced_rhs[0]) for _ in range(block_count)]
            solution_blocks[-1] = lu_solve(
                factors[-1], reduced_rhs[-1], check_finite=False
            )
            for index in range(block_count - 2, -1, -1):
                solution_blocks[index] = lu_solve(
                    factors[index],
                    reduced_rhs[index] - upper[index] @ solution_blocks[index + 1],
                    check_finite=False,
                )
            solution = np.vstack(solution_blocks)
        except Exception as exc:
            solve_error = f"{type(exc).__name__}: {exc}"
    solve_error = comm.bcast(solve_error, root=0)
    if solve_error is not None:
        raise RuntimeError("MPI block backsolve failed: " + solve_error)
    solution = comm.bcast(solution, root=0)
    return solution, {
        "block_count": block_count,
        "block_size": block_size,
        "rhs_columns": rhs_columns,
        "column_shards": comm.size,
        "columns_per_rank": columns_per_rank,
    }


class PairedEndpointSchurAction:
    """Run two real endpoint Schur actions concurrently on MPI4 subgroups."""

    def __init__(
        self,
        bottom_action: Any,
        bottom_transfer: Any,
        bottom_root: int,
        top_action: Any,
        top_transfer: Any,
        top_root: int,
        world: Any = MPI.COMM_WORLD,
    ) -> None:
        self.bottom_action = bottom_action
        self.bottom_transfer = bottom_transfer
        self.bottom_root = int(bottom_root)
        self.top_action = top_action
        self.top_transfer = top_transfer
        self.top_root = int(top_root)
        self.world = world
        transfer = bottom_transfer if bottom_transfer is not None else top_transfer
        if transfer is None:
            raise ValueError("At least one paired endpoint transfer is required.")
        self.plane_size = int(getattr(transfer, "source_size"))
        self.retained_rows = self.plane_size
        self.canonical_sign = 1
        self._destroyed = False

    @staticmethod
    def _local_apply(action: Any, transfer: Any, columns: np.ndarray) -> np.ndarray | None:
        if action is None:
            return None
        mapped = transfer.primal(columns)
        output = action.apply_trace_columns(mapped)
        return transfer.dual(output)

    def apply_pair(
        self, bottom_columns: np.ndarray, top_columns: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        if self._destroyed:
            raise RuntimeError("The paired endpoint action has been destroyed.")
        bottom_columns = np.asarray(bottom_columns, dtype=np.complex128)
        top_columns = np.asarray(top_columns, dtype=np.complex128)
        if bottom_columns.shape != top_columns.shape:
            raise ValueError("Paired endpoint columns must have equal shapes.")
        # Both subgroup computations happen before either WORLD broadcast.
        bottom_local = self._local_apply(
            self.bottom_action, self.bottom_transfer, bottom_columns
        )
        top_local = self._local_apply(
            self.top_action, self.top_transfer, top_columns
        )
        bottom_out = np.empty_like(bottom_columns)
        top_out = np.empty_like(top_columns)
        if self.world.rank == self.bottom_root:
            bottom_out[:, :] = bottom_local
        self.world.Bcast(bottom_out, root=self.bottom_root)
        if self.world.rank == self.top_root:
            top_out[:, :] = top_local
        self.world.Bcast(top_out, root=self.top_root)
        return bottom_out, top_out

    def apply_diagonal_pair(self, basis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.apply_pair(basis, basis)

    def destroy(self) -> None:
        if self._destroyed:
            return
        for action in (self.bottom_action, self.top_action):
            if action is not None:
                action.destroy()
        self._destroyed = True


class FullFeTraceChainAction:
    """Apply the ten-cell raw-outward FE trace chain without a global matrix.

    The input is either ``(11 * plane_size, n_columns)`` or
    ``(11, plane_size, n_columns)``.  ``cell_action`` is one shared two-port
    action.  The transfer objects provide ``primal`` and ``dual`` methods;
    endpoint actions may expose either ``apply_columns`` or the existing
    ``apply_trace_columns`` name.  The chain also exposes compact five-block
    materialization and a streamed explicit trace AIJ builder.
    """

    def __init__(
        self,
        cell_action: Any,
        cell_transfer: Any,
        bottom_action: Any = None,
        bottom_transfer: Any = None,
        top_action: Any = None,
        top_transfer: Any = None,
        *,
        cell_count: int = 10,
        paired_endpoints: PairedEndpointSchurAction | None = None,
    ) -> None:
        self.cell_action = cell_action
        self.cell_transfer = cell_transfer
        self.paired_endpoints = paired_endpoints
        self.bottom_action = bottom_action
        self.bottom_transfer = bottom_transfer
        self.top_action = top_action
        self.top_transfer = top_transfer
        if paired_endpoints is not None:
            self.bottom_action = paired_endpoints.bottom_action
            self.top_action = paired_endpoints.top_action
        self.cell_count = int(cell_count)
        if self.cell_count != 10:
            raise ValueError("Stage 1 requires exactly ten cells.")
        self.plane_size = int(getattr(cell_action, "left_rows"))
        if self.plane_size <= 0 or int(getattr(cell_action, "right_rows")) != self.plane_size:
            raise ValueError("The two-port action must have equal FE endpoint rows.")
        if int(getattr(cell_transfer, "target_size")) != int(
            getattr(cell_action, "right_rows")
        ):
            raise ValueError("The cell transfer target does not match the right port.")

        endpoint_actions = (
            (bottom_action, top_action)
            if paired_endpoints is None
            else (paired_endpoints.bottom_action, paired_endpoints.top_action)
        )
        for endpoint_action in endpoint_actions:
            if endpoint_action is None:
                continue
            canonical_sign = getattr(endpoint_action, "canonical_sign", None)
            if canonical_sign is not None and canonical_sign != 1:
                raise ValueError(
                    "Stage 1 endpoint actions must use raw-outward canonical_sign=+1."
                )

        def action_rows(action: Any) -> int:
            for name in ("retained_rows", "left_rows", "port_rows"):
                if hasattr(action, name):
                    return int(getattr(action, name))
            raise ValueError("An endpoint action does not expose its row count.")

        endpoint_transfers = (
            ((bottom_transfer, bottom_action), (top_transfer, top_action))
            if paired_endpoints is None
            else (
                (paired_endpoints.bottom_transfer, paired_endpoints.bottom_action),
                (paired_endpoints.top_transfer, paired_endpoints.top_action),
            )
        )
        for transfer, action in endpoint_transfers:
            if transfer is None or action is None:
                continue
            if int(getattr(transfer, "source_size")) != self.plane_size:
                raise ValueError("An endpoint transfer source does not match the FE plane.")
            if int(getattr(transfer, "target_size")) != action_rows(action):
                raise ValueError("An endpoint transfer target does not match its action.")
        self.plane_count = self.cell_count + 1
        self.global_size = self.plane_count * self.plane_size
        if int(getattr(cell_transfer, "source_size")) != self.plane_size:
            raise ValueError("The cell transfer source size does not match the FE plane.")
        self._destroyed = False
        self.dense_global_formed = False
        self.cell_action_instances = 1
        self.explicit_trace_telemetry: dict[str, Any] = {}

    @staticmethod
    def _apply_action(action: Any, values: np.ndarray) -> np.ndarray:
        method = getattr(action, "apply_columns", None)
        if method is None:
            method = action.apply_trace_columns
        result = np.asarray(method(values), dtype=np.complex128)
        if result.ndim == 1:
            result = result[:, None]
        return result

    def apply_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the chain to replicated FE-plane columns."""

        columns = np.asarray(values, dtype=np.complex128)
        packed = columns.ndim in (1, 2)
        if packed:
            if columns.ndim == 1:
                columns = columns[:, None]
            if columns.shape[0] != self.global_size:
                raise ValueError(
                    f"Chain columns must have {self.global_size} rows, "
                    f"got {columns.shape}."
                )
            columns = columns.reshape(
                self.plane_count, self.plane_size, columns.shape[1]
            )
        elif columns.ndim == 3 and columns.shape[:2] == (
            self.plane_count,
            self.plane_size,
        ):
            pass
        else:
            raise ValueError(
                "Chain columns must have shape "
                f"({self.global_size}, n) or "
                f"({self.plane_count}, {self.plane_size}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The FE trace-chain action has been destroyed.")

        count = columns.shape[2]
        result = np.zeros_like(columns)
        for cell in range(self.cell_count):
            right = self.cell_transfer.primal(columns[cell + 1, :, :])
            port_input = np.vstack((columns[cell], right))
            port_output = self._apply_action(self.cell_action, port_input)
            left_rows = self.plane_size
            result[cell] += port_output[:left_rows]
            result[cell + 1] += self.cell_transfer.dual(port_output[left_rows:, :])

        if self.paired_endpoints is not None:
            bottom_output, top_output = self.paired_endpoints.apply_pair(
                columns[0, :, :], columns[self.cell_count, :, :]
            )
            result[0] += bottom_output
            result[self.cell_count] += top_output
        else:
            for action, transfer, plane in (
                (self.bottom_action, self.bottom_transfer, 0),
                (self.top_action, self.top_transfer, self.cell_count),
            ):
                endpoint_input = transfer.primal(columns[plane, :, :])
                endpoint_output = self._apply_action(action, endpoint_input)
                result[plane] += transfer.dual(endpoint_output)
        return result.reshape(self.global_size, count) if packed else result

    @staticmethod
    def _replicated_vector(vector: Any) -> np.ndarray:
        first, last = map(int, vector.getOwnershipRange())
        packets = vector.getComm().tompi4py().allgather(
            (first, last, np.asarray(vector.getArray(readonly=True)).copy())
        )
        values = np.empty(int(vector.getSize()), dtype=np.complex128)
        for start, stop, local in packets:
            values[int(start) : int(stop)] = local
        return values

    def mult(self, _mat: Any, x: Any, y: Any) -> None:
        """PETSc MatPython ``mult`` adapter for one replicated column."""

        values = self._replicated_vector(x)
        output = self.apply_columns(values[:, None])[:, 0]
        first, last = map(int, y.getOwnershipRange())
        y.getArray()[:] = output[first:last]
        y.assemble()

    def build_compact_trace_blocks(
        self,
        *,
        column_block_size: int = 16,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        """Materialize the five unique 1200-row trace operators."""

        if self._destroyed:
            raise RuntimeError("The FE trace-chain action has been destroyed.")
        block_size = int(column_block_size)
        if block_size <= 0:
            raise ValueError("column_block_size must be positive.")
        p = self.plane_size
        cell_left_left = np.zeros((p, p), dtype=np.complex128)
        right_diagonal = np.zeros((p, p), dtype=np.complex128)
        lower = np.zeros((p, p), dtype=np.complex128)
        upper = np.zeros((p, p), dtype=np.complex128)
        max_volume = max(int(cell_left_left.size), int(right_diagonal.size))
        for start in range(0, p, block_size):
            stop = min(start + block_size, p)
            basis = np.zeros((p, stop - start), dtype=np.complex128)
            basis[start:stop, :] = np.eye(stop - start, dtype=np.complex128)
            right_input = self.cell_transfer.primal(basis)
            port_input = np.zeros((2 * p, 2 * (stop - start)), dtype=np.complex128)
            port_input[:p, : stop - start] = basis
            port_input[p:, stop - start :] = right_input
            port_output = self._apply_action(self.cell_action, port_input)
            right_output = self.cell_transfer.dual(port_output[p:, :])
            cell_left_left[:, start:stop] = port_output[:p, : stop - start]
            upper[:, start:stop] = port_output[:p, stop - start :]
            lower[:, start:stop] = right_output[:, : stop - start]
            right_diagonal[:, start:stop] = right_output[:, stop - start :]
            max_volume = max(
                max_volume,
                int(port_input.size),
                int(port_output.size),
                int(right_output.size),
            )
        endpoint_diagonals: dict[int, np.ndarray] = {}
        if self.paired_endpoints is not None:
            basis = np.eye(p, dtype=np.complex128)
            bottom_diagonal, top_diagonal = (
                self.paired_endpoints.apply_diagonal_pair(basis)
            )
            endpoint_diagonals = {
                0: bottom_diagonal,
                self.cell_count: top_diagonal,
            }
        else:
            endpoint_specs = (
                (self.bottom_action, self.bottom_transfer, 0),
                (self.top_action, self.top_transfer, self.cell_count),
            )
            for action, transfer, plane in endpoint_specs:
                endpoint_diagonal = np.zeros((p, p), dtype=np.complex128)
                for start in range(0, p, block_size):
                    stop = min(start + block_size, p)
                    basis = np.zeros((p, stop - start), dtype=np.complex128)
                    basis[start:stop, :] = np.eye(stop - start, dtype=np.complex128)
                    endpoint_input = transfer.primal(basis)
                    endpoint_output = self._apply_action(action, endpoint_input)
                    endpoint_diagonal[:, start:stop] = transfer.dual(endpoint_output)
                    max_volume = max(
                        max_volume,
                        int(endpoint_input.size),
                        int(endpoint_output.size),
                    )
                endpoint_diagonals[plane] = endpoint_diagonal
        blocks = {
            "bottom_diagonal": cell_left_left + endpoint_diagonals[0],
            "middle_diagonal": cell_left_left + right_diagonal,
            "top_diagonal": right_diagonal + endpoint_diagonals[self.cell_count],
            "lower": lower,
            "upper": upper,
        }
        del (
            cell_left_left,
            right_diagonal,
            lower,
            upper,
            endpoint_diagonals,
        )
        return blocks, {
            "block_size": block_size,
            "plane_rows": self.plane_size,
            "unique_operator_blocks": 5,
            "local_dense_block_volume_complex_entries": max_volume,
            "global_dense_formed": False,
        }

    def build_explicit_trace_matrix(
        self,
        *,
        column_block_size: int = 16,
        comm: Any = None,
    ) -> tuple[PETSc.Mat, dict[str, Any]]:
        """Build the trace-only AIJ matrix by streamed column blocks.

        Only one-cell and endpoint Schur actions are applied.  Columns are
        grouped within one plane so that each temporary dense block covers
        the at-most three neighboring output planes of the banded chain.
        """

        if self._destroyed:
            raise RuntimeError("The FE trace-chain action has been destroyed.")
        block_size = int(column_block_size)
        if block_size <= 0:
            raise ValueError("column_block_size must be positive.")
        matrix_comm = PETSc.COMM_WORLD if comm is None else comm
        comm_size = matrix_comm.getSize()
        if comm_size == 1:
            first_row, last_row = 0, self.global_size
            preallocation = 3 * self.plane_size
            preallocation_mode = "serial_three_band_scalar"
            allocated_nnz = self.global_size * 3 * self.plane_size
        else:
            ownership_probe = PETSc.Mat().createAIJ(
                size=(self.global_size, self.global_size),
                nnz=0,
                comm=matrix_comm,
            )
            ownership_probe.setUp()
            first_row, last_row = map(
                int, ownership_probe.getOwnershipRange()
            )
            ownership_probe.destroy()
            diagonal_nnz = np.empty(last_row - first_row, dtype=PETSc.IntType)
            offdiagonal_nnz = np.empty(last_row - first_row, dtype=PETSc.IntType)
            for local_row, row in enumerate(range(first_row, last_row)):
                plane = row // self.plane_size
                support = np.concatenate(
                    [
                        np.arange(
                            support_plane * self.plane_size,
                            (support_plane + 1) * self.plane_size,
                            dtype=PETSc.IntType,
                        )
                        for support_plane in range(
                            max(0, plane - 1),
                            min(self.plane_count, plane + 2),
                        )
                    ]
                )
                diagonal_nnz[local_row] = np.count_nonzero(
                    (support >= first_row) & (support < last_row)
                )
                offdiagonal_nnz[local_row] = len(support) - int(
                    diagonal_nnz[local_row]
                )
            preallocation = (diagonal_nnz, offdiagonal_nnz)
            preallocation_mode = "mpi_owned_three_band_arrays"
            allocated_nnz = int(
                matrix_comm.tompi4py().allreduce(
                    int(np.sum(diagonal_nnz + offdiagonal_nnz))
                )
            )
        matrix = PETSc.Mat().createAIJ(
            size=(self.global_size, self.global_size),
            nnz=preallocation,
            comm=matrix_comm,
        )
        try:
            compact_blocks, compact_telemetry = self.build_compact_trace_blocks(
                column_block_size=block_size
            )
            bottom_diagonal = compact_blocks["bottom_diagonal"]
            middle_diagonal = compact_blocks["middle_diagonal"]
            top_diagonal = compact_blocks["top_diagonal"]
            lower = compact_blocks["lower"]
            upper = compact_blocks["upper"]

            def insert_block(
                row_start: int,
                col_start: int,
                block: np.ndarray,
            ) -> None:
                row_stop = row_start + block.shape[0]
                local_start = max(row_start, first_row)
                local_stop = min(row_stop, last_row)
                if local_start >= local_stop:
                    return
                matrix.setValues(
                    np.arange(local_start, local_stop, dtype=PETSc.IntType),
                    np.arange(
                        col_start,
                        col_start + block.shape[1],
                        dtype=PETSc.IntType,
                    ),
                    block[local_start - row_start : local_stop - row_start],
                )

            for plane in range(self.plane_count):
                diagonal = (
                    bottom_diagonal
                    if plane == 0
                    else top_diagonal
                    if plane == self.cell_count
                    else middle_diagonal
                )
                insert_block(
                    plane * self.plane_size,
                    plane * self.plane_size,
                    diagonal,
                )
                if plane < self.cell_count:
                    insert_block(
                        plane * self.plane_size,
                        (plane + 1) * self.plane_size,
                        upper,
                    )
                    insert_block(
                        (plane + 1) * self.plane_size,
                        plane * self.plane_size,
                        lower,
                    )
            matrix.assemble()
            info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
            stored_nnz = int(info.get("nz_used", 0.0))
            record = {
                "rows": int(self.global_size),
                "nnz": stored_nnz,
                "stored_nnz": stored_nnz,
                "allocated_nnz": int(allocated_nnz),
                "matrix_type": str(matrix.getType()),
                "local_dense_block_volume_complex_entries": int(
                    compact_telemetry[
                        "local_dense_block_volume_complex_entries"
                    ]
                ),
                "local_dense_block_scope": (
                    "maximum single replicated dense block per rank; "
                    "units are complex entries, not bytes or total local peak"
                ),
                "column_block_size": block_size,
                "preallocation_mode": preallocation_mode,
                "comm_size": int(comm_size),
                "global_dense_formed": False,
                "compact_blocks": compact_telemetry,
            }
            self.explicit_trace_telemetry = dict(record)
            return matrix, record
        except Exception:
            matrix.destroy()
            raise

    def destroy(self, _obj: Any = None) -> None:
        """Release the three owned actions once; transfers are non-owning."""

        if self._destroyed:
            return
        seen: set[int] = set()
        actions = [self.cell_action]
        if self.paired_endpoints is None:
            actions.extend((self.bottom_action, self.top_action))
        for action in actions:
            if id(action) in seen:
                continue
            seen.add(id(action))
            destroy = getattr(action, "destroy", None)
            if destroy is not None:
                destroy()
        if self.paired_endpoints is not None:
            self.paired_endpoints.destroy()
        self._destroyed = True
