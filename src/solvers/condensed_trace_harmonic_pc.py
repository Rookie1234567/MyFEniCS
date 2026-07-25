"""Opt-in trace-harmonic block-Schur preconditioner research prototype.

This module deliberately does not register an ordinary solver default.  It
implements a nonoverlapping block-LDU action for condensed trace systems whose
local trace interiors communicate only through a declared interface.  The
fine operator is never globally factored: local dense block LUs and a small
replicated dense interface-Schur LU are retained and fully inventoried.

The PETSc implementation is an analytic/MPI qualification prototype.  Setup
gathers only the declared block and interface submatrices to block owners.
Apply currently replicates full work vectors; that limitation is reported
explicitly and must be removed before a large production PDE run.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Sequence

from mpi4py import MPI
import numpy as np
import scipy.linalg as sla
from petsc4py import PETSc


TINY = np.finfo(float).tiny


def _index_array(values: Sequence[int] | np.ndarray, *, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=PETSc.IntType)
    if result.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional index array")
    if result.size == 0:
        raise ValueError(f"{name} must not be empty")
    if np.any(result < 0):
        raise ValueError(f"{name} must contain only nonnegative indices")
    if np.any(result[1:] <= result[:-1]):
        raise ValueError(f"{name} must be strictly increasing")
    result = result.copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class TraceHarmonicPartition:
    """Disjoint local trace interiors plus a nonempty interface/coarse set."""

    local_blocks: tuple[np.ndarray, ...]
    interface_rows: np.ndarray
    block_owners: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not self.local_blocks:
            raise ValueError("trace-harmonic partition requires local blocks")
        blocks = tuple(
            _index_array(block, name=f"local_blocks[{number}]")
            for number, block in enumerate(self.local_blocks)
        )
        interface = _index_array(self.interface_rows, name="interface_rows")
        combined = np.concatenate((*blocks, interface))
        if np.unique(combined).size != combined.size:
            raise ValueError("trace-harmonic partition index sets must be disjoint")
        owners = self.block_owners
        if owners is not None:
            owners = tuple(int(owner) for owner in owners)
            if len(owners) != len(blocks):
                raise ValueError("block_owners must have one entry per local block")
            if any(owner < 0 for owner in owners):
                raise ValueError("block owners must be nonnegative")
        object.__setattr__(self, "local_blocks", blocks)
        object.__setattr__(self, "interface_rows", interface)
        object.__setattr__(self, "block_owners", owners)

    def validate_cover(self, matrix_rows: int) -> None:
        """Fail closed unless every matrix row occurs exactly once."""

        if matrix_rows <= 0:
            raise ValueError("matrix_rows must be positive")
        combined = np.sort(
            np.concatenate((*self.local_blocks, self.interface_rows))
        )
        expected = np.arange(matrix_rows, dtype=PETSc.IntType)
        if not np.array_equal(combined, expected):
            missing = np.setdiff1d(expected, combined, assume_unique=True)
            outside = combined[combined >= matrix_rows]
            raise ValueError(
                "trace-harmonic partition must cover every matrix row exactly "
                f"once; missing={missing.tolist()}, outside={outside.tolist()}"
            )

    def owners_for_size(self, comm_size: int) -> tuple[int, ...]:
        """Return explicit owners or a deterministic cubic-work assignment."""

        if comm_size <= 0:
            raise ValueError("comm_size must be positive")
        if self.block_owners is not None:
            if any(owner >= comm_size for owner in self.block_owners):
                raise ValueError("block owner is outside the communicator")
            return self.block_owners
        loads = [0 for _ in range(comm_size)]
        owners: list[int] = []
        for block in self.local_blocks:
            owner = min(range(comm_size), key=lambda rank: (loads[rank], rank))
            owners.append(owner)
            loads[owner] += int(block.size) ** 3
        return tuple(owners)

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema_version": "task035b.trace-harmonic-partition.v1",
            "local_block_count": len(self.local_blocks),
            "local_block_dimensions": [
                int(block.size) for block in self.local_blocks
            ],
            "interface_dimension": int(self.interface_rows.size),
            "declared_block_owners": (
                None
                if self.block_owners is None
                else [int(owner) for owner in self.block_owners]
            ),
            "nonoverlapping": True,
            "all_rows_must_be_covered": True,
            "cross_block_coupling_allowed": False,
        }


def _checked_lu(
    matrix: np.ndarray,
    *,
    name: str,
    condition_limit: float,
) -> tuple[tuple[np.ndarray, np.ndarray], float]:
    matrix = np.asarray(matrix, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"{name} must be square")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} must contain only finite values")
    condition = float(np.linalg.cond(matrix))
    if not np.isfinite(condition) or condition > condition_limit:
        raise RuntimeError(
            f"{name} failed the condition gate: condition={condition:.6e}, "
            f"limit={condition_limit:.6e}"
        )
    return sla.lu_factor(matrix, check_finite=True), condition


def _cross_block_audit_dense(
    operator: np.ndarray,
    partition: TraceHarmonicPartition,
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> dict[str, Any]:
    scale = max(float(np.linalg.norm(operator)), TINY)
    threshold = float(absolute_tolerance + relative_tolerance * scale)
    maximum = 0.0
    count = 0
    for left, rows in enumerate(partition.local_blocks):
        for right, columns in enumerate(partition.local_blocks):
            if left == right:
                continue
            values = np.abs(operator[np.ix_(rows, columns)])
            maximum = max(maximum, float(np.max(values, initial=0.0)))
            count += int(np.count_nonzero(values > threshold))
    return {
        "gate_pass": count == 0,
        "forbidden_entry_count": count,
        "maximum_forbidden_coupling": maximum,
        "threshold": threshold,
        "matrix_frobenius_norm": scale,
        "relative_tolerance": float(relative_tolerance),
        "absolute_tolerance": float(absolute_tolerance),
    }


class DenseTraceHarmonicBlockSchur:
    """Exact dense reference for the declared trace-harmonic block structure."""

    def __init__(
        self,
        operator: np.ndarray,
        partition: TraceHarmonicPartition,
        *,
        relative_coupling_tolerance: float = 1.0e-14,
        absolute_coupling_tolerance: float = 0.0,
        condition_limit: float = 1.0e12,
    ) -> None:
        started = time.perf_counter()
        matrix = np.asarray(operator, dtype=np.complex128)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("trace-harmonic operator must be square")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("trace-harmonic operator must be finite")
        partition.validate_cover(matrix.shape[0])
        coupling = _cross_block_audit_dense(
            matrix,
            partition,
            relative_tolerance=relative_coupling_tolerance,
            absolute_tolerance=absolute_coupling_tolerance,
        )
        if not coupling["gate_pass"]:
            raise RuntimeError(
                "trace-harmonic block-Schur requires zero direct coupling "
                "between different local blocks; "
                f"count={coupling['forbidden_entry_count']}, "
                f"maximum={coupling['maximum_forbidden_coupling']:.6e}, "
                f"threshold={coupling['threshold']:.6e}"
            )
        if not np.isfinite(condition_limit) or condition_limit <= 1.0:
            raise ValueError("condition_limit must be finite and greater than one")

        gamma = partition.interface_rows
        self._operator = matrix.copy()
        self.partition = partition
        self._local_lu: list[tuple[np.ndarray, np.ndarray]] = []
        self._local_conditions: list[float] = []
        self._lower_couplings: list[np.ndarray] = []
        self._harmonic_extensions: list[np.ndarray] = []
        coarse = matrix[np.ix_(gamma, gamma)].copy()
        for number, block in enumerate(partition.local_blocks):
            local = matrix[np.ix_(block, block)]
            upper = matrix[np.ix_(block, gamma)]
            lower = matrix[np.ix_(gamma, block)]
            factor, condition = _checked_lu(
                local,
                name=f"local trace block {number}",
                condition_limit=condition_limit,
            )
            harmonic = -sla.lu_solve(factor, upper, check_finite=True)
            coarse += lower @ harmonic
            self._local_lu.append(factor)
            self._local_conditions.append(condition)
            self._lower_couplings.append(lower.copy())
            self._harmonic_extensions.append(harmonic)
        self._coarse = coarse
        self._coarse_lu, self._coarse_condition = _checked_lu(
            coarse,
            name="trace-harmonic interface Schur",
            condition_limit=condition_limit,
        )
        self._coupling_audit = coupling
        self._setup_seconds = float(time.perf_counter() - started)
        self._apply_count = 0
        self._apply_seconds = 0.0

    @property
    def coarse_matrix(self) -> np.ndarray:
        return self._coarse.copy()

    @property
    def harmonic_extensions(self) -> tuple[np.ndarray, ...]:
        return tuple(extension.copy() for extension in self._harmonic_extensions)

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        source = np.asarray(rhs, dtype=np.complex128)
        if source.ndim != 1 or source.size != self._operator.shape[0]:
            raise ValueError("trace-harmonic right-hand side has the wrong size")
        if not np.all(np.isfinite(source)):
            raise ValueError("trace-harmonic right-hand side must be finite")
        started = time.perf_counter()
        gamma = self.partition.interface_rows
        coarse_rhs = source[gamma].copy()
        local_initial: list[np.ndarray] = []
        for block, factor, lower in zip(
            self.partition.local_blocks,
            self._local_lu,
            self._lower_couplings,
            strict=True,
        ):
            initial = sla.lu_solve(factor, source[block], check_finite=True)
            local_initial.append(initial)
            coarse_rhs -= lower @ initial
        interface_solution = sla.lu_solve(
            self._coarse_lu, coarse_rhs, check_finite=True
        )
        result = np.empty_like(source)
        result[gamma] = interface_solution
        for block, initial, harmonic in zip(
            self.partition.local_blocks,
            local_initial,
            self._harmonic_extensions,
            strict=True,
        ):
            result[block] = initial + harmonic @ interface_solution
        self._apply_count += 1
        self._apply_seconds += float(time.perf_counter() - started)
        return result

    def explicit_relative_residual(self, rhs: np.ndarray) -> float:
        source = np.asarray(rhs, dtype=np.complex128)
        solution = self.solve(source)
        residual = self._operator @ solution - source
        return float(np.linalg.norm(residual) / max(np.linalg.norm(source), TINY))

    @property
    def diagnostics(self) -> dict[str, Any]:
        local_lu_bytes = [
            int(factor[0].nbytes + factor[1].nbytes)
            for factor in self._local_lu
        ]
        coarse_lu_bytes = int(
            self._coarse_lu[0].nbytes + self._coarse_lu[1].nbytes
        )
        return {
            "schema_version": "task035b.dense-trace-harmonic-block-schur-pc.v1",
            "strategy": "nonoverlapping_trace_harmonic_exact_block_ldu",
            "partition": self.partition.audit,
            "cross_block_coupling_gate": dict(self._coupling_audit),
            "setup_seconds": self._setup_seconds,
            "apply_count": self._apply_count,
            "apply_seconds": self._apply_seconds,
            "local_dense_factor_count": len(self._local_lu),
            "local_dense_factor_dimensions": [
                int(block.size) for block in self.partition.local_blocks
            ],
            "local_dense_factor_bytes": local_lu_bytes,
            "local_dense_factor_bytes_total": int(sum(local_lu_bytes)),
            "local_dense_factor_conditions": list(self._local_conditions),
            "coarse_dimension": int(self.partition.interface_rows.size),
            "coarse_condition": self._coarse_condition,
            "coarse_dense_matrix_entries": int(self._coarse.size),
            "coarse_dense_matrix_bytes": int(self._coarse.nbytes),
            "coarse_dense_lu_bytes_per_replica": coarse_lu_bytes,
            "coarse_dense_lu_replica_count": 1,
            "global_sparse_direct_factor_count": 0,
            "global_sparse_direct_factor_nnz": 0,
            "global_fine_sparse_factor_nnz": 0,
            "mumps_symbolic_or_numeric_created": False,
            "fine_operator_factor_free": True,
            "global_fine_factor_free": True,
            "no_global_sparse_direct_factor": True,
            "strictly_factorless": False,
            "strictly_factorless_reason": (
                "local dense trace-block LUs and one dense interface-Schur LU "
                "are retained"
            ),
            "all_factor_storage_disclosed": True,
            "ordinary_default_changed": False,
        }


@dataclass
class _OwnedBlockFactor:
    number: int
    rows: np.ndarray
    lower: np.ndarray
    harmonic: np.ndarray
    factor: tuple[np.ndarray, np.ndarray]
    condition: float


def _assemble_ordered_rows(
    row_order: np.ndarray,
    columns: int,
    packets: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    name: str,
) -> np.ndarray:
    result = np.empty((row_order.size, columns), dtype=np.complex128)
    covered = np.zeros(row_order.size, dtype=bool)
    for rows, values in packets:
        rows = np.asarray(rows, dtype=PETSc.IntType)
        values = np.asarray(values, dtype=np.complex128)
        if values.shape != (rows.size, columns):
            raise RuntimeError(f"{name} packet has an inconsistent shape")
        if rows.size == 0:
            continue
        positions = np.searchsorted(row_order, rows)
        if np.any(positions >= row_order.size) or not np.array_equal(
            row_order[positions], rows
        ):
            raise RuntimeError(f"{name} packet contains undeclared rows")
        if np.any(covered[positions]):
            raise RuntimeError(f"{name} packet contains multiply owned rows")
        result[positions, :] = values
        covered[positions] = True
    if not np.all(covered):
        raise RuntimeError(f"{name} did not receive every declared row")
    return result


def _owned_submatrix_rows(
    operator: PETSc.Mat,
    requested_rows: np.ndarray,
    columns: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    start, end = operator.getOwnershipRange()
    rows = requested_rows[
        (requested_rows >= int(start)) & (requested_rows < int(end))
    ]
    if rows.size == 0:
        values = np.empty((0, columns.size), dtype=np.complex128)
    else:
        values = np.asarray(
            operator.getValues(rows, columns), dtype=np.complex128
        ).copy()
    return rows.copy(), values


class PetscTraceHarmonicBlockSchurPc:
    """Distributed PETSc Python-PC context for trace-harmonic block LDU."""

    def __init__(
        self,
        operator: PETSc.Mat,
        partition: TraceHarmonicPartition,
        *,
        relative_coupling_tolerance: float = 1.0e-14,
        absolute_coupling_tolerance: float = 0.0,
        condition_limit: float = 1.0e12,
    ) -> None:
        started = time.perf_counter()
        rows, columns = operator.getSize()
        if rows != columns:
            raise ValueError("trace-harmonic PETSc operator must be square")
        partition.validate_cover(rows)
        if not np.isfinite(condition_limit) or condition_limit <= 1.0:
            raise ValueError("condition_limit must be finite and greater than one")
        self.operator = operator
        self.partition = partition
        self.comm = operator.getComm().tompi4py()
        self.rank = int(self.comm.rank)
        self.comm_size = int(self.comm.size)
        self.matrix_rows = int(rows)
        self.ownership_start, self.ownership_end = operator.getOwnershipRange()
        self.block_owners = partition.owners_for_size(self.comm_size)
        self._destroyed = False
        self._owned_factors: dict[int, _OwnedBlockFactor] = {}
        self._explicit_residual_reports: list[dict[str, Any]] = []
        self.apply_count = 0
        self.apply_seconds = 0.0
        self.vector_collective_seconds = 0.0
        self.block_solve_seconds = 0.0
        self.coarse_solve_seconds = 0.0

        self._cross_block_audit = self._audit_cross_block_coupling(
            relative_tolerance=relative_coupling_tolerance,
            absolute_tolerance=absolute_coupling_tolerance,
        )
        if not self._cross_block_audit["gate_pass"]:
            audit = self._cross_block_audit
            raise RuntimeError(
                "trace-harmonic block-Schur requires zero direct coupling "
                "between different local blocks; "
                f"count={audit['forbidden_entry_count']}, "
                f"maximum={audit['maximum_forbidden_coupling']:.6e}, "
                f"threshold={audit['threshold']:.6e}"
            )

        gamma = partition.interface_rows
        gamma_rows, local_gg = _owned_submatrix_rows(operator, gamma, gamma)
        gamma_packet = self.comm.allgather((gamma_rows, local_gg))
        coarse = _assemble_ordered_rows(
            gamma,
            gamma.size,
            gamma_packet,
            name="interface-interface block",
        )
        coarse_contribution = np.zeros_like(coarse)
        for number, (block, owner) in enumerate(
            zip(partition.local_blocks, self.block_owners, strict=True)
        ):
            local_block_rows, local_ii = _owned_submatrix_rows(
                operator, block, block
            )
            _upper_rows, local_i_gamma = _owned_submatrix_rows(
                operator, block, gamma
            )
            local_gamma_rows, local_gamma_i = _owned_submatrix_rows(
                operator, gamma, block
            )
            packets = self.comm.gather(
                (
                    local_block_rows,
                    local_ii,
                    local_i_gamma,
                    local_gamma_rows,
                    local_gamma_i,
                ),
                root=owner,
            )
            if self.rank == owner:
                assert packets is not None
                interior_packets = [
                    (packet[0], packet[1]) for packet in packets
                ]
                upper_packets = [
                    (packet[0], packet[2]) for packet in packets
                ]
                lower_packets = [
                    (packet[3], packet[4]) for packet in packets
                ]
                interior = _assemble_ordered_rows(
                    block,
                    block.size,
                    interior_packets,
                    name=f"local block {number}",
                )
                upper = _assemble_ordered_rows(
                    block,
                    gamma.size,
                    upper_packets,
                    name=f"local-to-interface block {number}",
                )
                lower = _assemble_ordered_rows(
                    gamma,
                    block.size,
                    lower_packets,
                    name=f"interface-to-local block {number}",
                )
                factor, condition = _checked_lu(
                    interior,
                    name=f"local PETSc trace block {number}",
                    condition_limit=condition_limit,
                )
                harmonic = -sla.lu_solve(
                    factor, upper, check_finite=True
                )
                coarse_contribution += lower @ harmonic
                self._owned_factors[number] = _OwnedBlockFactor(
                    number=number,
                    rows=block,
                    lower=lower,
                    harmonic=harmonic,
                    factor=factor,
                    condition=condition,
                )
        self.comm.Allreduce(
            MPI.IN_PLACE, coarse_contribution, op=MPI.SUM
        )
        coarse += coarse_contribution
        self._coarse_matrix = coarse
        self._coarse_lu, self._coarse_condition = _checked_lu(
            coarse,
            name="PETSc trace-harmonic interface Schur",
            condition_limit=condition_limit,
        )
        self._setup_seconds = float(time.perf_counter() - started)

    def _audit_cross_block_coupling(
        self,
        *,
        relative_tolerance: float,
        absolute_tolerance: float,
    ) -> dict[str, Any]:
        if relative_tolerance < 0.0 or absolute_tolerance < 0.0:
            raise ValueError("cross-block coupling tolerances must be nonnegative")
        matrix_norm = float(
            self.operator.norm(PETSc.NormType.FROBENIUS)
        )
        threshold = float(
            absolute_tolerance
            + relative_tolerance * max(matrix_norm, TINY)
        )
        block_membership = np.full(self.matrix_rows, -1, dtype=np.int64)
        for number, block in enumerate(self.partition.local_blocks):
            block_membership[block] = number
        local_count = 0
        local_maximum = 0.0
        start, end = self.operator.getOwnershipRange()
        for row in range(int(start), int(end)):
            row_block = int(block_membership[row])
            if row_block < 0:
                continue
            columns, values = self.operator.getRow(row)
            columns = np.asarray(columns, dtype=PETSc.IntType)
            values = np.asarray(values, dtype=np.complex128)
            other_block = (
                (block_membership[columns] >= 0)
                & (block_membership[columns] != row_block)
            )
            magnitudes = np.abs(values[other_block])
            local_count += int(np.count_nonzero(magnitudes > threshold))
            local_maximum = max(
                local_maximum, float(np.max(magnitudes, initial=0.0))
            )
        count = int(self.comm.allreduce(local_count, op=MPI.SUM))
        maximum = float(self.comm.allreduce(local_maximum, op=MPI.MAX))
        return {
            "gate_pass": count == 0,
            "forbidden_entry_count": count,
            "maximum_forbidden_coupling": maximum,
            "threshold": threshold,
            "matrix_frobenius_norm": matrix_norm,
            "relative_tolerance": float(relative_tolerance),
            "absolute_tolerance": float(absolute_tolerance),
        }

    def _gather_vector(self, vector: PETSc.Vec) -> np.ndarray:
        start, end = vector.getOwnershipRange()
        if vector.getSize() != self.matrix_rows:
            raise ValueError("trace-harmonic vector has the wrong global size")
        packet = (
            int(start),
            int(end),
            np.asarray(
                vector.getArray(readonly=True), dtype=np.complex128
            ).copy(),
        )
        full = np.empty(self.matrix_rows, dtype=np.complex128)
        for packet_start, packet_end, values in self.comm.allgather(packet):
            full[packet_start:packet_end] = values
        return full

    def apply(
        self,
        _pc: PETSc.PC | None,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self._destroyed:
            raise RuntimeError("trace-harmonic preconditioner has been destroyed")
        started = time.perf_counter()
        collective_started = time.perf_counter()
        source_values = self._gather_vector(source)
        self.vector_collective_seconds += float(
            time.perf_counter() - collective_started
        )

        gamma = self.partition.interface_rows
        coarse_rhs_contribution = np.zeros(gamma.size, dtype=np.complex128)
        local_initial: dict[int, np.ndarray] = {}
        block_started = time.perf_counter()
        for number, factor in self._owned_factors.items():
            initial = sla.lu_solve(
                factor.factor,
                source_values[factor.rows],
                check_finite=True,
            )
            local_initial[number] = initial
            coarse_rhs_contribution += factor.lower @ initial
        self.comm.Allreduce(
            MPI.IN_PLACE, coarse_rhs_contribution, op=MPI.SUM
        )
        self.block_solve_seconds += float(time.perf_counter() - block_started)

        coarse_started = time.perf_counter()
        interface_solution = sla.lu_solve(
            self._coarse_lu,
            source_values[gamma] - coarse_rhs_contribution,
            check_finite=True,
        )
        self.coarse_solve_seconds += float(time.perf_counter() - coarse_started)

        block_started = time.perf_counter()
        block_result = np.zeros(self.matrix_rows, dtype=np.complex128)
        for number, factor in self._owned_factors.items():
            block_result[factor.rows] = (
                local_initial[number]
                + factor.harmonic @ interface_solution
            )
        self.comm.Allreduce(MPI.IN_PLACE, block_result, op=MPI.SUM)
        block_result[gamma] = interface_solution
        self.block_solve_seconds += float(time.perf_counter() - block_started)
        local_start, local_end = target.getOwnershipRange()
        target.getArray()[:] = block_result[local_start:local_end]
        self.apply_count += 1
        self.apply_seconds += float(time.perf_counter() - started)

    def certify_explicit_residual(
        self,
        source: PETSc.Vec,
        *,
        tolerance: float = 1.0e-11,
    ) -> dict[str, Any]:
        """Apply the PC and certify ``||A M^-1 r-r||/||r||`` explicitly."""

        if tolerance <= 0.0 or not np.isfinite(tolerance):
            raise ValueError("explicit residual tolerance must be finite and positive")
        solution = self.operator.createVecRight()
        action = self.operator.createVecLeft()
        residual = self.operator.createVecLeft()
        try:
            self.apply(None, source, solution)
            self.operator.mult(solution, action)
            action.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), source)
            numerator = float(residual.norm())
            denominator = float(source.norm())
            relative = numerator / max(denominator, TINY)
            report = {
                "schema_version": (
                    "task035b.trace-harmonic-explicit-residual.v1"
                ),
                "residual_definition": "norm(A_times_Minv_r_minus_r)/norm(r)",
                "numerator": numerator,
                "denominator": denominator,
                "relative_residual": relative,
                "tolerance": float(tolerance),
                "pass": bool(relative <= tolerance),
                "global_sparse_direct_factor_nnz": 0,
                "mumps_symbolic_or_numeric_created": False,
            }
            self._explicit_residual_reports.append(report)
            return dict(report)
        finally:
            residual.destroy()
            action.destroy()
            solution.destroy()

    @property
    def diagnostics(self) -> dict[str, Any]:
        rank_local_factor_bytes = int(
            sum(
                factor.factor[0].nbytes + factor.factor[1].nbytes
                for factor in self._owned_factors.values()
            )
        )
        local_factor_bytes_by_rank = [
            int(value)
            for value in self.comm.allgather(rank_local_factor_bytes)
        ]
        rank_local_factor_count = len(self._owned_factors)
        factor_count_by_rank = [
            int(value)
            for value in self.comm.allgather(rank_local_factor_count)
        ]
        local_conditions = [
            (number, factor.condition)
            for number, factor in self._owned_factors.items()
        ]
        conditions_by_rank = self.comm.allgather(local_conditions)
        conditions = [0.0 for _ in self.partition.local_blocks]
        for packet in conditions_by_rank:
            for number, condition in packet:
                conditions[number] = float(condition)
        coarse_lu_bytes = int(
            self._coarse_lu[0].nbytes + self._coarse_lu[1].nbytes
        )
        full_vector_bytes = self.matrix_rows * np.dtype(np.complex128).itemsize
        return {
            "schema_version": "task035b.petsc-trace-harmonic-block-schur-pc.v1",
            "strategy": (
                "owner_computes_nonoverlapping_trace_harmonic_exact_block_ldu"
            ),
            "partition": self.partition.audit,
            "resolved_block_owners": list(self.block_owners),
            "cross_block_coupling_gate": dict(self._cross_block_audit),
            "setup_seconds": self._setup_seconds,
            "apply_count": self.apply_count,
            "apply_seconds": self.apply_seconds,
            "vector_collective_seconds": self.vector_collective_seconds,
            "block_solve_seconds": self.block_solve_seconds,
            "coarse_solve_seconds": self.coarse_solve_seconds,
            "local_dense_factor_count": len(self.partition.local_blocks),
            "local_dense_factor_count_by_rank": factor_count_by_rank,
            "local_dense_factor_dimensions": [
                int(block.size) for block in self.partition.local_blocks
            ],
            "local_dense_factor_conditions": conditions,
            "local_dense_factor_bytes_by_rank": local_factor_bytes_by_rank,
            "local_dense_factor_bytes_total": int(
                sum(local_factor_bytes_by_rank)
            ),
            "coarse_dimension": int(self.partition.interface_rows.size),
            "coarse_condition": self._coarse_condition,
            "coarse_dense_matrix_entries": int(self._coarse_matrix.size),
            "coarse_dense_matrix_bytes_per_replica": int(
                self._coarse_matrix.nbytes
            ),
            "coarse_dense_lu_bytes_per_replica": coarse_lu_bytes,
            "coarse_dense_lu_replica_count": self.comm_size,
            "replicated_full_vector_workspace": True,
            "replicated_full_vector_bytes_per_vector_per_rank": (
                full_vector_bytes
            ),
            "prototype_apply_replicated_full_vectors": 2,
            "prototype_rank_workspace_upper_bound_bytes": (
                2 * full_vector_bytes
            ),
            "production_scalability_gate": (
                "not_passed_full_vector_replication_must_be_replaced_by_"
                "interface_and_owner_neighborhood_exchange"
            ),
            "explicit_residual_reports": [
                dict(report) for report in self._explicit_residual_reports
            ],
            "global_sparse_direct_factor_count": 0,
            "global_sparse_direct_factor_nnz": 0,
            "global_fine_sparse_factor_nnz": 0,
            "mumps_symbolic_or_numeric_created": False,
            "fine_operator_factor_free": True,
            "global_fine_factor_free": True,
            "no_global_sparse_direct_factor": True,
            "strictly_factorless_preconditioner": False,
            "strictly_factorless": False,
            "strictly_factorless_reason": (
                "owner-local dense trace-block LUs and a replicated dense "
                "interface-Schur LU are retained"
            ),
            "all_factor_storage_disclosed": True,
            "ordinary_default_changed": False,
            "formal_pde_status": "not_run",
        }

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        self._owned_factors.clear()
        self._explicit_residual_reports.clear()
        self._destroyed = True


def configure_trace_harmonic_block_schur_ksp(
    ksp: PETSc.KSP,
    operator: PETSc.Mat,
    partition: TraceHarmonicPartition,
    *,
    restart: int = 40,
    relative_tolerance: float = 1.0e-10,
    absolute_tolerance: float = 1.0e-12,
    maximum_iterations: int = 200,
    relative_coupling_tolerance: float = 1.0e-14,
    absolute_coupling_tolerance: float = 0.0,
    condition_limit: float = 1.0e12,
) -> PetscTraceHarmonicBlockSchurPc:
    """Programmatically attach the opt-in trace-harmonic Python PC.

    No PETSc options database is consulted.  The function intentionally does
    not alter any repository or runner default.
    """

    if restart <= 0 or maximum_iterations <= 0:
        raise ValueError("restart and maximum_iterations must be positive")
    if relative_tolerance <= 0.0 or absolute_tolerance <= 0.0:
        raise ValueError("KSP tolerances must be positive")
    context = PetscTraceHarmonicBlockSchurPc(
        operator,
        partition,
        relative_coupling_tolerance=relative_coupling_tolerance,
        absolute_coupling_tolerance=absolute_coupling_tolerance,
        condition_limit=condition_limit,
    )
    ksp.setOperators(operator)
    ksp.setType(PETSc.KSP.Type.FGMRES)
    ksp.setGMRESRestart(int(restart))
    ksp.setTolerances(
        rtol=float(relative_tolerance),
        atol=float(absolute_tolerance),
        divtol=1.0e8,
        max_it=int(maximum_iterations),
    )
    ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
    ksp.setInitialGuessNonzero(False)
    ksp.setConvergenceHistory(length=int(maximum_iterations) + 1, reset=True)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.PYTHON)
    pc.setPythonContext(context)
    return context


def trace_harmonic_block_schur_contract() -> dict[str, Any]:
    """Return the typed, JSON-safe capability and non-promotion contract."""

    return {
        "schema_version": "task035b.trace-harmonic-block-schur-contract.v1",
        "configured_programmatically": True,
        "raw_petsc_options_accepted": False,
        "ordinary_default_changed": False,
        "opt_in_only": True,
        "formal_pde_status": "not_run",
        "qualification_scope": "dense_analytic_and_small_petsc_mpi",
        "strategy": "nonoverlapping_trace_harmonic_exact_block_ldu",
        "fundamentally_distinct_from_closed_lanes": [
            "point_jacobi",
            "generic_asm_overlap_ilu",
            "physical_z_slab_ilu",
            "diagonal_lifted_dtn_trace_galerkin",
        ],
        "global_sparse_direct_factor_count": 0,
        "global_sparse_direct_factor_nnz": 0,
        "mumps_symbolic_or_numeric_created": False,
        "fine_operator_factor_free": True,
        "strictly_factorless": False,
        "retained_factors": [
            "owner_local_dense_trace_block_lu",
            "small_replicated_dense_interface_schur_lu",
        ],
        "inactive_modes_enter_matrix": False,
        "prototype_limitation": (
            "apply_replicates_full_vectors; production neighborhood exchange "
            "not yet implemented"
        ),
        "candidate_promotion": False,
        "heavy_pde_rerun": False,
    }


__all__ = [
    "DenseTraceHarmonicBlockSchur",
    "PetscTraceHarmonicBlockSchurPc",
    "TraceHarmonicPartition",
    "configure_trace_harmonic_block_schur_ksp",
    "trace_harmonic_block_schur_contract",
]
