from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from typing import Any, Callable, Sequence

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
from mpi4py import MPI
from petsc4py import PETSc

from .borrowed_local_audit import (
    BorrowedLocalExactAuditor,
    BorrowedSlabLayout,
)
from .local_slab_solver import LocalBackendPlan, LocalCsrOperator, LocalSlabSolver


TINY = np.finfo(float).tiny


def certify_fixed_linear_preconditioner(
    preconditioner: Any,
    template: PETSc.Vec,
) -> dict[str, float | int]:
    """Certify linearity, repeatability, and an MPI-invariant action signature.

    The input vectors are deterministic functions of their global indices, so
    the action norm and checksum can be compared across MPI decompositions.
    This is intentionally an opt-in research certificate; it does not change
    the preconditioner action or the ordinary workstation profile.
    """

    start, end = template.getOwnershipRange()
    indices = np.arange(start, end, dtype=np.float64)
    x = template.duplicate()
    y = template.duplicate()
    combined = template.duplicate()
    probe = template.duplicate()
    px = template.duplicate()
    px_repeated = template.duplicate()
    py = template.duplicate()
    p_combined = template.duplicate()
    expected = template.duplicate()
    difference = template.duplicate()
    alpha = PETSc.ScalarType(0.37 - 0.19j)
    beta = PETSc.ScalarType(-0.23 + 0.41j)
    try:
        x.getArray()[:] = np.sin(0.17 * (indices + 1.0)) + 1j * np.cos(
            0.11 * (indices + 2.0)
        )
        y.getArray()[:] = np.cos(0.07 * (indices + 3.0)) - 1j * np.sin(
            0.13 * (indices + 4.0)
        )
        probe.getArray()[:] = np.cos(0.05 * (indices + 5.0)) + 1j * np.sin(
            0.09 * (indices + 6.0)
        )
        x.copy(combined)
        combined.scale(alpha)
        combined.axpy(beta, y)

        preconditioner.apply(None, x, px)
        preconditioner.apply(None, x, px_repeated)
        preconditioner.apply(None, y, py)
        preconditioner.apply(None, combined, p_combined)

        px.copy(expected)
        expected.scale(alpha)
        expected.axpy(beta, py)
        p_combined.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        linearity_error = float(difference.norm()) / max(float(expected.norm()), TINY)

        px_repeated.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), px)
        determinism_error = float(difference.norm()) / max(float(px.norm()), TINY)
        checksum = complex(probe.dot(px))
        return {
            "linearity_relative_error": linearity_error,
            "determinism_relative_error": determinism_error,
            "action_norm": float(px.norm()),
            "action_checksum_real": float(checksum.real),
            "action_checksum_imag": float(checksum.imag),
            "global_size": int(template.getSize()),
        }
    finally:
        for vector in (
            difference,
            expected,
            p_combined,
            py,
            px_repeated,
            px,
            probe,
            combined,
            y,
            x,
        ):
            vector.destroy()


def _exact_seqaij_fingerprint(matrix: PETSc.Mat) -> str:
    """Return an exact, canonical fingerprint for a sequential AIJ matrix."""

    indptr, indices, values = matrix.getValuesCSR()
    digest = hashlib.sha256()
    digest.update(np.asarray(matrix.getSize(), dtype=np.int64).tobytes())
    digest.update(np.asarray(indptr, dtype=np.int64).tobytes())
    digest.update(np.asarray(indices, dtype=np.int64).tobytes())
    digest.update(np.asarray(values, dtype=PETSc.ScalarType).tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class SparseCoarseVector:
    indices: np.ndarray
    values: np.ndarray
    slab: int
    eigenvalue: float
    eigenpair_residual: float

    def __post_init__(self) -> None:
        indices = np.asarray(self.indices, dtype=PETSc.IntType)
        values = np.asarray(self.values, dtype=PETSc.ScalarType)
        if indices.ndim != 1 or values.ndim != 1 or indices.size != values.size:
            raise ValueError(
                "sparse coarse indices and values must be matching 1D arrays"
            )
        if indices.size and np.any(indices[1:] <= indices[:-1]):
            raise ValueError("sparse coarse indices must be strictly increasing")
        if not np.all(np.isfinite(values)):
            raise ValueError("sparse coarse values must be finite")
        object.__setattr__(self, "indices", indices)
        object.__setattr__(self, "values", values)

    @property
    def storage_bytes(self) -> int:
        return int(self.indices.nbytes + self.values.nbytes)


def compress_petsc_vector(
    vector: PETSc.Vec,
    *,
    slab: int = -1,
    eigenvalue: float = float("nan"),
    relative_threshold: float = 1.0e-14,
) -> SparseCoarseVector:
    """Store a distributed coarse vector using only its local nonzero entries."""

    comm = vector.getComm().tompi4py()
    start, _end = vector.getOwnershipRange()
    values = np.asarray(vector.getArray(readonly=True), dtype=PETSc.ScalarType)
    local_scale = float(np.max(np.abs(values), initial=0.0))
    scale = max(float(comm.allreduce(local_scale, op=MPI.MAX)), TINY)
    local_indices = np.flatnonzero(np.abs(values) > relative_threshold * scale).astype(
        PETSc.IntType
    )
    indices = np.asarray(local_indices + start, dtype=PETSc.IntType)
    compressed = values[local_indices].copy()
    norm = float(
        np.sqrt(comm.allreduce(float(np.vdot(compressed, compressed).real), op=MPI.SUM))
    )
    if norm <= 1.0e-12:
        raise ValueError("cannot compress a numerically zero coarse vector")
    return SparseCoarseVector(
        indices=indices,
        values=compressed / norm,
        slab=slab,
        eigenvalue=eigenvalue,
        eigenpair_residual=0.0,
    )


class SparseGalerkinTwoLevelPc:
    def __init__(
        self,
        operator: PETSc.Mat,
        smoother: Any,
        basis: Sequence[SparseCoarseVector],
        *,
        post_smooth: bool = False,
        post_smooth_weight: float = 1.0,
        condition_limit: float = 1.0e10,
        coarse_progress: Callable[[int, int], None] | None = None,
        coarse_matrix: np.ndarray | None = None,
        setup_progress: Callable[[str], None] | None = None,
    ) -> None:
        if not basis:
            raise ValueError("two-level PC requires a non-empty coarse basis")
        self.operator = operator
        self.comm = operator.getComm().tompi4py()
        self.ownership_start, self.ownership_end = operator.getOwnershipRange()
        self.smoother = smoother
        self._basis_count = len(basis)
        self._setup_progress = setup_progress
        self._report_setup("basis_csc_started")
        self._basis_matrix = self._build_basis_matrix(basis)
        self._report_setup("basis_csc_finished")
        self._report_setup("basis_adjoint_started")
        self._basis_transpose = self._basis_matrix.transpose(copy=False)
        self._conjugated_work = np.empty(
            self.ownership_end - self.ownership_start, dtype=np.complex128
        )
        self._report_setup("basis_adjoint_finished")
        self._coarse_progress = coarse_progress
        self.post_smooth = bool(post_smooth)
        self.post_smooth_weight = float(post_smooth_weight)
        if not np.isfinite(self.post_smooth_weight) or self.post_smooth_weight <= 0.0:
            raise ValueError("post_smooth_weight must be finite and positive")
        self.condition_limit = float(condition_limit)
        self.residual = operator.createVecLeft()
        self.correction = operator.createVecRight()
        self.coarse_matrix_cache_hit = coarse_matrix is not None
        if coarse_matrix is None:
            self._coarse = self._factor_coarse_operator()
            self.coarse_action_relative_error = None
        else:
            self._coarse = np.asarray(coarse_matrix, dtype=np.complex128).copy()
            if self._coarse.shape != (self._basis_count, self._basis_count):
                raise ValueError(
                    "cached coarse matrix shape does not match the coarse basis"
                )
            self._report_setup("cached_coarse_svd_started")
            self._certify_coarse_operator(self._coarse)
            self._report_setup("cached_coarse_svd_finished")
            self.coarse_action_relative_error = self._coarse_action_error(self._coarse)
            if self.coarse_action_relative_error > 1.0e-10:
                self.correction.destroy()
                self.residual.destroy()
                raise RuntimeError(
                    "cached coarse matrix failed true-action certification: "
                    f"error={self.coarse_action_relative_error:.6e}"
                )
        self._coarse_lu = sla.lu_factor(self._coarse)
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self.smoother_elapsed_s = 0.0
        self.coarse_elapsed_s = 0.0
        self._destroyed = False

    def _report_setup(self, stage: str) -> None:
        if self._setup_progress is not None:
            self._setup_progress(stage)

    def set_smoother(self, smoother: Any) -> None:
        self.smoother = smoother

    def _local_array(self, vector: PETSc.Vec) -> np.ndarray:
        start, end = vector.getOwnershipRange()
        if (start, end) != (self.ownership_start, self.ownership_end):
            raise RuntimeError("coarse vector ownership does not match the operator")
        return vector.getArray(readonly=True)

    def _local_positions(self, basis: SparseCoarseVector) -> np.ndarray:
        if basis.indices.size and (
            basis.indices[0] < self.ownership_start
            or basis.indices[-1] >= self.ownership_end
        ):
            raise RuntimeError("sparse basis contains nonlocal global indices")
        return basis.indices - self.ownership_start

    def _build_basis_matrix(self, basis: Sequence[SparseCoarseVector]) -> sp.csc_matrix:
        local_size = self.ownership_end - self.ownership_start
        indptr = np.zeros(len(basis) + 1, dtype=np.int64)
        local_indices: list[np.ndarray] = []
        local_values: list[np.ndarray] = []
        for column, vector in enumerate(basis):
            positions = np.asarray(self._local_positions(vector), dtype=PETSc.IntType)
            local_indices.append(positions)
            local_values.append(np.asarray(vector.values, dtype=PETSc.ScalarType))
            indptr[column + 1] = indptr[column] + positions.size
        if indptr[-1]:
            indices = np.concatenate(local_indices)
            values = np.concatenate(local_values)
        else:
            indices = np.empty(0, dtype=PETSc.IntType)
            values = np.empty(0, dtype=PETSc.ScalarType)
        matrix = sp.csc_matrix(
            (values, indices, indptr), shape=(local_size, len(basis)), copy=False
        )
        matrix.sort_indices()
        return matrix

    def _set_basis_vector(self, target: PETSc.Vec, column: int) -> None:
        target.set(0.0)
        first = int(self._basis_matrix.indptr[column])
        last = int(self._basis_matrix.indptr[column + 1])
        target.getArray()[self._basis_matrix.indices[first:last]] = (
            self._basis_matrix.data[first:last]
        )

    def _basis_dots(self, vector: PETSc.Vec) -> np.ndarray:
        values = self._local_array(vector)
        np.conjugate(values, out=self._conjugated_work)
        products = np.asarray(
            self._basis_transpose.dot(self._conjugated_work), dtype=np.complex128
        )
        np.conjugate(products, out=products)
        self.comm.Allreduce(MPI.IN_PLACE, products, op=MPI.SUM)
        return products

    def _coarse_action_error(self, coarse: np.ndarray) -> float:
        rng = np.random.default_rng(20260711)
        coefficients = rng.standard_normal(
            self._basis_count
        ) + 1j * rng.standard_normal(self._basis_count)
        vector = self.operator.createVecRight()
        action = self.operator.createVecLeft()
        self._report_setup("cached_coarse_basis_combination_started")
        vector.getArray()[:] = self._basis_matrix.dot(coefficients)
        self._report_setup("cached_coarse_basis_combination_finished")
        self._report_setup("cached_coarse_true_action_started")
        self.operator.mult(vector, action)
        self._report_setup("cached_coarse_true_action_finished")
        self._report_setup("cached_coarse_projection_started")
        actual = self._basis_dots(action)
        self._report_setup("cached_coarse_projection_finished")
        expected = coarse @ coefficients
        error = float(
            np.linalg.norm(actual - expected) / max(np.linalg.norm(expected), TINY)
        )
        action.destroy()
        vector.destroy()
        return error

    def _factor_coarse_operator(self) -> np.ndarray:
        dimension = self._basis_count
        coarse = np.empty((dimension, dimension), dtype=np.complex128)
        vector = self.operator.createVecRight()
        action = self.operator.createVecLeft()
        for column in range(dimension):
            self._set_basis_vector(vector, column)
            self.operator.mult(vector, action)
            coarse[:, column] = self._basis_dots(action)
            if self._coarse_progress is not None:
                self._coarse_progress(column + 1, dimension)
        action.destroy()
        vector.destroy()
        self._certify_coarse_operator(coarse)
        return coarse

    def _certify_coarse_operator(self, coarse: np.ndarray) -> None:
        dimension = coarse.shape[0]
        singular_values = np.linalg.svd(coarse, compute_uv=False)
        self.coarse_smallest_singular_value = float(singular_values[-1])
        self.coarse_largest_singular_value = float(singular_values[0])
        tolerance = max(coarse.shape) * np.finfo(float).eps * singular_values[0]
        self.coarse_rank = int(np.count_nonzero(singular_values > tolerance))
        self.coarse_condition = float(
            self.coarse_largest_singular_value
            / max(self.coarse_smallest_singular_value, TINY)
        )
        if (
            self.coarse_rank != dimension
            or self.coarse_condition > self.condition_limit
        ):
            raise RuntimeError(
                "fixed coarse operator failed rank/conditioning gate: "
                f"rank={self.coarse_rank}/{dimension}, condition={self.coarse_condition:.6e}"
            )

    @property
    def coarse_matrix(self) -> np.ndarray:
        return self._coarse.copy()

    def _update_residual(self, source: PETSc.Vec, approximation: PETSc.Vec) -> None:
        self.operator.mult(approximation, self.residual)
        self.residual.aypx(-1.0, source)

    def apply(
        self, _pc: PETSc.PC | None, source: PETSc.Vec, approximation: PETSc.Vec
    ) -> None:
        started = time.perf_counter()
        if self.smoother is None:
            raise RuntimeError("two-level PC smoother has not been configured")
        approximation.set(0.0)
        smoother_started = time.perf_counter()
        self.smoother.solve(source, approximation)
        self.smoother_elapsed_s += time.perf_counter() - smoother_started
        self._update_residual(source, approximation)
        coarse_started = time.perf_counter()
        rhs = self._basis_dots(self.residual)
        coefficients = sla.lu_solve(self._coarse_lu, rhs)
        approximation.getArray()[:] += self._basis_matrix.dot(coefficients)
        self.coarse_elapsed_s += time.perf_counter() - coarse_started
        if self.post_smooth:
            self._update_residual(source, approximation)
            self.correction.set(0.0)
            smoother_started = time.perf_counter()
            self.smoother.solve(self.residual, self.correction)
            self.smoother_elapsed_s += time.perf_counter() - smoother_started
            approximation.axpy(
                PETSc.ScalarType(self.post_smooth_weight), self.correction
            )
        self.apply_count += 1
        self.apply_elapsed_s += time.perf_counter() - started

    @property
    def basis_storage_bytes(self) -> int:
        local = int(
            self._basis_matrix.data.nbytes
            + self._basis_matrix.indices.nbytes
            + self._basis_matrix.indptr.nbytes
            + self._conjugated_work.nbytes
        )
        return int(self.comm.allreduce(local, op=MPI.SUM))

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        self.correction.destroy()
        self.residual.destroy()
        self._basis_matrix = None
        self._basis_transpose = None
        self._conjugated_work = None
        self._destroyed = True


def gather_global_subdomain_indices(
    local_subdomains: Sequence[np.ndarray],
    *,
    comm: MPI.Comm = MPI.COMM_WORLD,
) -> tuple[np.ndarray, ...]:
    """Merge rank-local pieces into complete, replicated global subdomains."""

    normalized = tuple(
        np.unique(np.asarray(indices, dtype=PETSc.IntType))
        for indices in local_subdomains
    )
    counts = comm.allgather(len(normalized))
    if len(set(counts)) != 1:
        raise ValueError(
            "all ranks must provide the same number of physical subdomain slots"
        )
    rank_packets = comm.allgather(normalized)
    result: list[np.ndarray] = []
    for subdomain in range(len(normalized)):
        pieces = [
            packet[subdomain] for packet in rank_packets if packet[subdomain].size
        ]
        if not pieces:
            raise ValueError(f"physical subdomain {subdomain} is globally empty")
        result.append(
            np.unique(np.concatenate(pieces)).astype(PETSc.IntType, copy=False)
        )
    return tuple(result)


def balanced_subdomain_owners(
    subdomains: Sequence[np.ndarray], comm_size: int
) -> tuple[int, ...]:
    """Assign complete subdomains by a deterministic largest-first row balance."""

    if comm_size <= 0:
        raise ValueError("MPI communicator size must be positive")
    loads = np.zeros(comm_size, dtype=np.int64)
    owners = np.empty(len(subdomains), dtype=np.int32)
    order = sorted(
        range(len(subdomains)),
        key=lambda index: (-np.asarray(subdomains[index]).size, index),
    )
    for index in order:
        owner = int(np.argmin(loads))
        owners[index] = owner
        loads[owner] += np.asarray(subdomains[index]).size
    return tuple(int(value) for value in owners)


@dataclass
class _OwnedSubdomainFactor:
    subdomain: int
    owner_rank: int
    backend_plan: LocalBackendPlan
    local_solver_type: str
    indices: np.ndarray
    union_positions: np.ndarray
    weights: np.ndarray
    matrix: PETSc.Mat | None
    ksp: PETSc.KSP | None
    factor_matrix: PETSc.Mat | None
    diagonal_inverse: np.ndarray | None
    matrix_nnz: int
    factor_nnz: int
    factorization_s: float
    ilu_factor_constructed: bool
    ilu_apply_count: int
    exact_fingerprint: str
    rhs: PETSc.Vec
    solution: PETSc.Vec
    local_backend: LocalSlabSolver | None = None


class _DistributedPhysicalSlabPcContext:
    def __init__(self, smoother: DistributedPhysicalSlabSmoother) -> None:
        self.smoother: DistributedPhysicalSlabSmoother | None = smoother

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.smoother is None:
            raise RuntimeError("distributed physical-slab PC has been destroyed")
        self.smoother._apply_once(source, target)


class DistributedPhysicalSlabSmoother:
    """Owner-computes additive Schwarz over complete physical MPI subdomains.

    ``Mat.createSubMatrices`` lets every rank request a different collection of
    sequential submatrices. Each complete slab is therefore factored once on a
    deterministic owner rank. One distributed-to-sequential scatter gathers all
    source entries needed by that rank, and the reverse scatter adds overlapping
    corrections back to the distributed vector.
    """

    def __init__(
        self,
        matrix: PETSc.Mat,
        subdomains: Sequence[np.ndarray],
        *,
        ilu_levels: int,
        local_ksp_iterations: int = 1,
        local_ksp_type: str = "gmres",
        smoother_iterations: int = 1,
        smoother_ksp_type: str = "gmres",
        action_operator: PETSc.Mat | None = None,
        diagonal_shift: PETSc.Vec | None = None,
        factor_only_storage: bool = False,
        local_solver_types: Sequence[str] | None = None,
        interpolation: str = "basic",
        assembly_order: str = "combined",
        progress: Callable[[int, int], None] | None = None,
        local_operator_observer: Callable[[int, LocalCsrOperator], None] | None = None,
        local_sample_observer: Callable[
            [int, np.ndarray, np.ndarray, str], None
        ]
        | None = None,
        local_solver_factory: Callable[
            [
                int,
                LocalCsrOperator,
                Callable[[np.ndarray], np.ndarray] | None,
            ],
            LocalSlabSolver,
        ]
        | None = None,
        local_backend_plan_resolver: Callable[[int], LocalBackendPlan] | None = None,
    ) -> None:
        if not subdomains:
            raise ValueError("distributed physical-slab smoother needs subdomains")
        if smoother_iterations < 1:
            raise ValueError("smoother_iterations must be positive")
        if local_ksp_iterations < 1:
            raise ValueError("local_ksp_iterations must be positive")
        if factor_only_storage and local_ksp_iterations != 1:
            raise ValueError("factor_only_storage requires local_ksp_iterations=1")
        if local_ksp_type not in {"gmres", "richardson"}:
            raise ValueError("local_ksp_type must be 'gmres' or 'richardson'")
        if smoother_ksp_type not in {"gmres", "richardson"}:
            raise ValueError("smoother_ksp_type must be 'gmres' or 'richardson'")
        if smoother_iterations > 1 and action_operator is None:
            raise ValueError("multiple smoothing steps require an action operator")
        if interpolation not in {"basic", "partition"}:
            raise ValueError("interpolation must be 'basic' or 'partition'")
        if assembly_order not in {"combined", "two_color"}:
            raise ValueError("assembly_order must be 'combined' or 'two_color'")
        if local_solver_types is None:
            local_solver_types = ("ilu",) * len(subdomains)
        if len(local_solver_types) != len(subdomains):
            raise ValueError("local_solver_types must match the subdomain count")
        if any(kind not in {"ilu", "jacobi"} for kind in local_solver_types):
            raise ValueError("local_solver_types entries must be 'ilu' or 'jacobi'")

        self.comm = matrix.getComm().tompi4py()
        self.rank = int(self.comm.rank)
        self.comm_size = int(self.comm.size)
        self.global_size = int(matrix.getSize()[0])
        self.interpolation = interpolation
        self.assembly_order = assembly_order
        self.local_ksp_iterations = int(local_ksp_iterations)
        self.local_ksp_type = local_ksp_type
        self.smoother_iterations = int(smoother_iterations)
        self.smoother_ksp_type = smoother_ksp_type
        self.factor_only_storage = bool(factor_only_storage)
        self.local_solver_types = tuple(local_solver_types)
        self.local_operator_observer = local_operator_observer
        self.local_sample_observer = local_sample_observer
        self.local_solver_factory = local_solver_factory
        self.local_backend_plan_resolver = local_backend_plan_resolver
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self._destroyed = False
        self.destroy_diagnostics: list[dict[str, Any]] = []
        self._inner_ksp: PETSc.KSP | None = None
        self._inner_pc_context: _DistributedPhysicalSlabPcContext | None = None
        self._action_operator = action_operator
        self._borrowed_auditors: list[BorrowedLocalExactAuditor] = []

        global_diagonal_shift: np.ndarray | None = None
        self.subdomain_local_diagonal_shift = diagonal_shift is not None
        if diagonal_shift is not None:
            if diagonal_shift.getSize() != self.global_size:
                raise ValueError("diagonal_shift size does not match smoother matrix")
            shift_start, shift_end = diagonal_shift.getOwnershipRange()
            packet = (
                int(shift_start),
                int(shift_end),
                np.asarray(
                    diagonal_shift.getArray(readonly=True),
                    dtype=PETSc.ScalarType,
                ).copy(),
            )
            global_diagonal_shift = np.empty(self.global_size, dtype=PETSc.ScalarType)
            for packet_start, packet_end, values in self.comm.allgather(packet):
                global_diagonal_shift[packet_start:packet_end] = values

        normalized: list[np.ndarray] = []
        multiplicity = np.zeros(self.global_size, dtype=np.int32)
        for subdomain, raw in enumerate(subdomains):
            indices = np.unique(np.asarray(raw, dtype=PETSc.IntType))
            if indices.size == 0:
                raise ValueError(f"physical subdomain {subdomain} is empty")
            if indices[0] < 0 or indices[-1] >= self.global_size:
                raise ValueError(f"physical subdomain {subdomain} is out of range")
            normalized.append(indices)
            multiplicity[indices] += 1
        if np.any(multiplicity == 0):
            raise ValueError(
                "distributed physical-slab subdomains do not cover every global dof"
            )

        self.subdomain_owners = balanced_subdomain_owners(normalized, self.comm_size)
        self.local_subdomains = tuple(
            index
            for index, owner in enumerate(self.subdomain_owners)
            if owner == self.rank
        )
        local_indices = [normalized[index] for index in self.local_subdomains]
        if local_indices:
            self._union_indices = np.unique(np.concatenate(local_indices)).astype(
                PETSc.IntType, copy=False
            )
        else:
            self._union_indices = np.empty(0, dtype=PETSc.IntType)

        template = matrix.createVecRight()
        self._gathered_source = PETSc.Vec().createSeq(
            self._union_indices.size, comm=PETSc.COMM_SELF
        )
        target_count = 2 if assembly_order == "two_color" else 1
        self._gathered_targets = [
            self._gathered_source.duplicate() for _ in range(target_count)
        ]
        global_is = PETSc.IS().createGeneral(self._union_indices, comm=PETSc.COMM_SELF)
        local_is = PETSc.IS().createStride(
            self._union_indices.size, first=0, step=1, comm=PETSc.COMM_SELF
        )
        self._scatter = PETSc.Scatter().create(
            template, global_is, self._gathered_source, local_is
        )
        local_is.destroy()
        global_is.destroy()
        template.destroy()

        self._factors: list[_OwnedSubdomainFactor] = []

        def build_factor(
            subdomain: int, indices: np.ndarray, submatrix: PETSc.Mat
        ) -> _OwnedSubdomainFactor:
            backend_plan = (
                LocalBackendPlan(
                    identity=self.local_solver_types[subdomain],
                    requires_ilu_factor=True,
                    requires_portable_operator=(
                        self.local_operator_observer is not None
                        or self.local_solver_factory is not None
                    ),
                    allows_fallback=self.local_solver_factory is not None,
                )
                if self.local_backend_plan_resolver is None
                else self.local_backend_plan_resolver(subdomain)
            )
            if not isinstance(backend_plan, LocalBackendPlan):
                raise TypeError("local backend plan resolver returned an invalid plan")
            if not backend_plan.requires_ilu_factor and self.local_solver_factory is None:
                raise ValueError("a no-ILU backend plan requires a local solver factory")
            if global_diagonal_shift is not None:
                submatrix_diagonal = submatrix.createVecLeft()
                submatrix.getDiagonal(submatrix_diagonal)
                submatrix_diagonal.getArray()[:] += global_diagonal_shift[indices]
                submatrix.setDiagonal(submatrix_diagonal)
                submatrix.assemble()
                submatrix_diagonal.destroy()
            union_positions = np.searchsorted(self._union_indices, indices).astype(
                PETSc.IntType, copy=False
            )
            if np.any(self._union_indices[union_positions] != indices):
                raise RuntimeError("subdomain indices are absent from the rank union")
            if interpolation == "partition":
                weights = np.asarray(
                    1.0 / multiplicity[indices], dtype=PETSc.ScalarType
                )
            else:
                weights = np.ones(indices.size, dtype=PETSc.ScalarType)
            rhs = submatrix.createVecRight()
            solution = submatrix.createVecLeft()
            exact_fingerprint = _exact_seqaij_fingerprint(submatrix)
            local_solver_type = self.local_solver_types[subdomain]
            matrix_nnz = int(submatrix.getInfo()["nz_used"])
            portable_operator = None
            if (
                self.local_operator_observer is not None
                or backend_plan.requires_portable_operator
            ):
                indptr, column_indices, values = submatrix.getValuesCSR()
                portable_operator = LocalCsrOperator(
                    shape=tuple(int(value) for value in submatrix.getSize()),
                    indptr=np.asarray(indptr, dtype=np.int64).copy(),
                    indices=np.asarray(column_indices, dtype=np.int64).copy(),
                    values=np.asarray(values, dtype=np.complex128).copy(),
                    metadata={
                        "slab_id": int(subdomain),
                        "owner_rank": self.rank,
                        "global_dof_indices": indices.astype(np.int64).tolist(),
                        "local_solver_type": local_solver_type,
                        "factor_only_storage": self.factor_only_storage,
                    },
                )
                if self.local_operator_observer is not None:
                    self.local_operator_observer(subdomain, portable_operator)
            factor_matrix: PETSc.Mat | None = None
            retained_matrix: PETSc.Mat | None = None
            retained_ksp: PETSc.KSP | None = None
            diagonal_inverse: np.ndarray | None = None
            factor_nnz = 0
            factorization_s = 0.0
            ilu_factor_constructed = False
            if local_solver_type == "jacobi" and backend_plan.requires_ilu_factor:
                diagonal = submatrix.createVecLeft()
                submatrix.getDiagonal(diagonal)
                values = np.asarray(
                    diagonal.getArray(readonly=True), dtype=PETSc.ScalarType
                )
                scale = float(np.max(np.abs(values), initial=0.0))
                if np.any(np.abs(values) <= max(scale, TINY) * 1.0e-14):
                    diagonal.destroy()
                    raise RuntimeError("selective Jacobi slab has a zero diagonal")
                diagonal_inverse = np.asarray(1.0 / values, dtype=PETSc.ScalarType)
                factor_nnz = int(values.size)
                diagonal.destroy()
                submatrix.destroy()
            elif backend_plan.requires_ilu_factor:
                factor_started = time.perf_counter()
                ksp = PETSc.KSP().create(PETSc.COMM_SELF)
                ksp.setOperators(submatrix)
                if self.local_ksp_iterations == 1:
                    ksp.setType("preonly")
                else:
                    ksp.setType(self.local_ksp_type)
                    if self.local_ksp_type == "gmres":
                        ksp.setGMRESRestart(self.local_ksp_iterations)
                    ksp.setNormType(PETSc.KSP.NormType.NONE)
                    ksp.setTolerances(max_it=self.local_ksp_iterations)
                pc = ksp.getPC()
                pc.setType("ilu")
                pc.setFactorLevels(int(ilu_levels))
                pc.setFactorOrdering("rcm")
                ksp.setUp()
                factorization_s = time.perf_counter() - factor_started
                factor_nnz = int(pc.getFactorMatrix().getInfo()["nz_used"])
                ilu_factor_constructed = True
                retained_matrix = submatrix
                retained_ksp = ksp
                if self.factor_only_storage:
                    factor_matrix = pc.getFactorMatrix()
                    factor_matrix.incRef()
                    ksp.destroy()
                    submatrix.destroy()
                    retained_ksp = None
                    retained_matrix = None
            owned_factor = _OwnedSubdomainFactor(
                subdomain=subdomain,
                owner_rank=self.rank,
                backend_plan=backend_plan,
                local_solver_type=local_solver_type,
                indices=indices,
                union_positions=union_positions,
                weights=weights,
                matrix=retained_matrix,
                ksp=retained_ksp,
                factor_matrix=factor_matrix,
                diagonal_inverse=diagonal_inverse,
                matrix_nnz=matrix_nnz,
                factor_nnz=factor_nnz,
                factorization_s=factorization_s,
                ilu_factor_constructed=ilu_factor_constructed,
                ilu_apply_count=0,
                exact_fingerprint=exact_fingerprint,
                rhs=rhs,
                solution=solution,
            )
            if self.local_solver_factory is not None:
                assert portable_operator is not None

                def baseline_action(source: np.ndarray) -> np.ndarray:
                    if not owned_factor.ilu_factor_constructed:
                        raise RuntimeError("hidden ILU fallback is unavailable")
                    owned_factor.rhs.getArray()[:] = source
                    owned_factor.solution.set(0.0)
                    if owned_factor.factor_matrix is not None:
                        owned_factor.factor_matrix.solve(
                            owned_factor.rhs, owned_factor.solution
                        )
                    elif owned_factor.diagonal_inverse is not None:
                        owned_factor.solution.getArray()[:] = (
                            owned_factor.diagonal_inverse
                            * owned_factor.rhs.getArray(readonly=True)
                        )
                    else:
                        assert owned_factor.ksp is not None
                        owned_factor.ksp.solve(owned_factor.rhs, owned_factor.solution)
                    owned_factor.ilu_apply_count += 1
                    return np.asarray(
                        owned_factor.solution.getArray(readonly=True),
                        dtype=np.complex128,
                    ).copy()

                owned_factor.local_backend = self.local_solver_factory(
                    subdomain,
                    portable_operator,
                    baseline_action if backend_plan.allows_fallback else None,
                )
                if (
                    not backend_plan.allows_fallback
                    and owned_factor.local_backend.diagnostics.get("identity")
                    != backend_plan.identity
                ):
                    raise RuntimeError("local backend identity violates the resolved plan")
            if not backend_plan.requires_ilu_factor:
                submatrix.destroy()
            return owned_factor

        local_factor_count = len(local_indices)
        factor_counts = self.comm.allgather(local_factor_count)
        uneven_owner_counts = len(set(factor_counts)) != 1

        if uneven_owner_counts:
            empty_indices = np.empty(0, dtype=PETSc.IntType)
            for slot in range(max(factor_counts)):
                has_factor = slot < local_factor_count
                indices = local_indices[slot] if has_factor else empty_indices
                extraction_set = PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
                submatrix = matrix.createSubMatrices([extraction_set])[0]
                extraction_set.destroy()
                if has_factor:
                    self._factors.append(
                        build_factor(self.local_subdomains[slot], indices, submatrix)
                    )
                else:
                    submatrix.destroy()
        elif self.factor_only_storage:
            for subdomain, indices in zip(
                self.local_subdomains, local_indices, strict=True
            ):
                extraction_set = PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
                submatrix = matrix.createSubMatrices([extraction_set])[0]
                extraction_set.destroy()
                self._factors.append(build_factor(subdomain, indices, submatrix))
        else:
            extraction_sets = [
                PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
                for indices in local_indices
            ]
            submatrices = matrix.createSubMatrices(extraction_sets)
            for index_set in extraction_sets:
                index_set.destroy()
            for subdomain, indices, submatrix in zip(
                self.local_subdomains,
                local_indices,
                submatrices,
                strict=True,
            ):
                self._factors.append(build_factor(subdomain, indices, submatrix))
        self.comm.Barrier()
        if progress is not None:
            progress(len(normalized), len(normalized))

        local_rows = sum(factor.indices.size for factor in self._factors)
        local_nnz = sum(factor.matrix_nnz for factor in self._factors)
        local_factor_nnz = sum(factor.factor_nnz for factor in self._factors)
        self.global_factor_rows = int(self.comm.allreduce(local_rows, op=MPI.SUM))
        self.global_factor_nnz = int(self.comm.allreduce(local_nnz, op=MPI.SUM))
        self.global_stored_factor_nnz = int(
            self.comm.allreduce(local_factor_nnz, op=MPI.SUM)
        )
        self.maximum_owner_rows = int(self.comm.allreduce(local_rows, op=MPI.MAX))
        self.minimum_owner_rows = int(self.comm.allreduce(local_rows, op=MPI.MIN))
        fingerprint_packets = self.comm.allgather(
            [
                (int(factor.subdomain), factor.exact_fingerprint)
                for factor in self._factors
            ]
        )
        self.factor_fingerprints = sorted(
            (item for packet in fingerprint_packets for item in packet),
            key=lambda item: item[0],
        )
        unique_fingerprints = {fingerprint for _, fingerprint in self.factor_fingerprints}
        self.unique_factor_classes = len(unique_fingerprints)
        self.exact_duplicate_factor_count = (
            len(self.factor_fingerprints) - self.unique_factor_classes
        )

        if self.smoother_iterations > 1:
            self._inner_pc_context = _DistributedPhysicalSlabPcContext(self)
            self._inner_ksp = PETSc.KSP().create(matrix.getComm())
            self._inner_ksp.setOperators(action_operator)
            self._inner_ksp.setType(self.smoother_ksp_type)
            if self.smoother_ksp_type == "gmres":
                self._inner_ksp.setGMRESRestart(self.smoother_iterations)
            self._inner_ksp.setNormType(PETSc.KSP.NormType.NONE)
            self._inner_ksp.setTolerances(max_it=self.smoother_iterations)
            inner_pc = self._inner_ksp.getPC()
            inner_pc.setType("python")
            inner_pc.setPythonContext(self._inner_pc_context)
            self._inner_ksp.setUp()

    def _apply_once(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        started = time.perf_counter()
        target.set(0.0)
        self._gathered_source.set(0.0)
        self._scatter.scatter(
            source,
            self._gathered_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        gathered_source = self._gathered_source.getArray(readonly=True)
        for gathered_target in self._gathered_targets:
            gathered_target.set(0.0)
        gathered_target_arrays = [
            gathered_target.getArray() for gathered_target in self._gathered_targets
        ]
        for factor in self._factors:
            source_values = np.asarray(
                gathered_source[factor.union_positions], dtype=np.complex128
            )
            factor.rhs.getArray()[:] = source_values
            factor.solution.set(0.0)
            if factor.local_backend is not None:
                factor.local_backend.solve(source_values, factor.solution.getArray())
            elif factor.factor_matrix is not None:
                factor.factor_matrix.solve(factor.rhs, factor.solution)
                factor.ilu_apply_count += 1
            elif factor.diagonal_inverse is not None:
                factor.solution.getArray()[:] = factor.diagonal_inverse * source_values
                factor.ilu_apply_count += 1
            else:
                assert factor.ksp is not None
                factor.ksp.solve(factor.rhs, factor.solution)
                factor.ilu_apply_count += 1
            if self.local_sample_observer is not None:
                self.local_sample_observer(
                    factor.subdomain,
                    np.asarray(factor.rhs.getArray(readonly=True), dtype=np.complex128).copy(),
                    np.asarray(
                        factor.solution.getArray(readonly=True), dtype=np.complex128
                    ).copy(),
                    factor.local_solver_type,
                )
            color = factor.subdomain % 2 if self.assembly_order == "two_color" else 0
            gathered_target_arrays[color][factor.union_positions] += (
                factor.weights * factor.solution.getArray(readonly=True)
            )
        for gathered_target in self._gathered_targets:
            self._scatter.scatter(
                gathered_target,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        self.apply_count += 1
        self.apply_elapsed_s += time.perf_counter() - started

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._inner_ksp is None:
            self._apply_once(source, target)
            return
        target.set(0.0)
        self._inner_ksp.solve(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        local_backend_diagnostics = []
        for factor in self._factors:
            backend = (
                dict(factor.local_backend.diagnostics)
                if factor.local_backend is not None
                else {
                    "identity": factor.local_solver_type,
                    "apply_count": factor.ilu_apply_count,
                }
            )
            exact_identity = backend.get("identity") == "sparse_lu_teacher"
            local_backend_diagnostics.append(
                {
                    "subdomain": factor.subdomain,
                    "owner_rank": factor.owner_rank,
                    "backend_identity": backend.get("identity"),
                    "requires_ilu_factor": factor.backend_plan.requires_ilu_factor,
                    "allows_fallback": factor.backend_plan.allows_fallback,
                    "ilu_factor_constructed": factor.ilu_factor_constructed,
                    "ilu_factor_nnz": factor.factor_nnz,
                    "ilu_factor_storage_estimate": (
                        factor.factor_nnz
                        * (np.dtype(PETSc.ScalarType).itemsize + np.dtype(PETSc.IntType).itemsize)
                        + factor.indices.size * np.dtype(PETSc.IntType).itemsize
                    )
                    if factor.ilu_factor_constructed
                    else 0,
                    "ilu_apply_count": factor.ilu_apply_count,
                    "exact_factor_constructed": exact_identity,
                    "exact_factor_nnz": (
                        int(backend.get("factor_nnz", 0)) if exact_identity else 0
                    ),
                    "exact_factor_storage_bytes": (
                        int(backend.get("factor_storage_bytes", 0))
                        if exact_identity
                        else 0
                    ),
                    "matrix_nnz": factor.matrix_nnz,
                    "operator_fingerprint": factor.exact_fingerprint,
                    "factorization_s": (
                        float(backend.get("factorization_s", 0.0))
                        if exact_identity
                        else factor.factorization_s
                    ),
                    "exact_apply_count": (
                        int(backend.get("solve_count", 0)) if exact_identity else 0
                    ),
                    "apply_elapsed_s": (
                        float(backend.get("solve_elapsed_s", 0.0))
                        if exact_identity
                        else 0.0
                    ),
                    "apply_mean_s": (
                        float(backend.get("solve_mean_s", 0.0))
                        if exact_identity
                        else 0.0
                    ),
                    "apply_p95_s": (
                        float(backend.get("solve_p95_s", 0.0))
                        if exact_identity
                        else 0.0
                    ),
                    "destroyed": bool(backend.get("destroyed", False)),
                    **backend,
                }
            )
        global_backend_diagnostics = sorted(
            (
                item
                for packet in self.comm.allgather(local_backend_diagnostics)
                for item in packet
            ),
            key=lambda item: item["subdomain"],
        )
        return {
            "subdomain_owners": list(self.subdomain_owners),
            "local_subdomains": list(self.local_subdomains),
            "interpolation": self.interpolation,
            "assembly_order": self.assembly_order,
            "local_ksp_iterations": self.local_ksp_iterations,
            "local_ksp_type": self.local_ksp_type,
            "smoother_iterations": self.smoother_iterations,
            "smoother_ksp_type": self.smoother_ksp_type,
            "subdomain_local_diagonal_shift": self.subdomain_local_diagonal_shift,
            "factor_only_storage": self.factor_only_storage,
            "local_solver_types": list(self.local_solver_types),
            "local_solver_type_counts": {
                kind: self.local_solver_types.count(kind) for kind in ("ilu", "jacobi")
            },
            "global_factor_rows": self.global_factor_rows,
            "global_factor_nnz": self.global_factor_nnz,
            "global_stored_factor_nnz": self.global_stored_factor_nnz,
            # Explicit alias retained beside the historical field so no-ILU
            # profiles cannot be misread as having no exact/learned storage.
            "global_stored_ilu_factor_nnz": self.global_stored_factor_nnz,
            "maximum_owner_rows": self.maximum_owner_rows,
            "minimum_owner_rows": self.minimum_owner_rows,
            "factor_fingerprints": [
                {"subdomain": subdomain, "sha256": fingerprint}
                for subdomain, fingerprint in self.factor_fingerprints
            ],
            "unique_factor_classes": self.unique_factor_classes,
            "exact_duplicate_factor_count": self.exact_duplicate_factor_count,
            "one_level_apply_count": self.apply_count,
            "one_level_mean_apply_s": self.apply_elapsed_s / max(self.apply_count, 1),
            "local_backend_diagnostics": local_backend_diagnostics,
            "global_backend_diagnostics": global_backend_diagnostics,
            "exact_backend_count": sum(
                item["exact_factor_constructed"] for item in global_backend_diagnostics
            ),
            "ilu_factor_constructed_count": sum(
                item["ilu_factor_constructed"] for item in global_backend_diagnostics
            ),
            "global_ilu_apply_count": sum(
                item["ilu_apply_count"] for item in global_backend_diagnostics
            ),
            "global_exact_apply_count": sum(
                item["exact_apply_count"] for item in global_backend_diagnostics
            ),
            "hidden_fallback_count": sum(
                bool(item["allows_fallback"]) and item["exact_factor_constructed"]
                for item in global_backend_diagnostics
            ),
            "borrowed_auditor_count": len(self._borrowed_auditors),
        }

    def create_borrowed_exact_auditor(self) -> BorrowedLocalExactAuditor:
        if self._destroyed:
            raise RuntimeError("distributed physical-slab smoother has been destroyed")
        if self._action_operator is None:
            raise RuntimeError("borrowed exact audit requires an action operator")
        layouts = {
            factor.subdomain: BorrowedSlabLayout(
                slab_id=factor.subdomain,
                owner_rank=factor.owner_rank,
                union_positions=factor.union_positions,
            )
            for factor in self._factors
        }
        auditor = BorrowedLocalExactAuditor(
            action_operator=self._action_operator,
            union_scatter=self._scatter,
            union_size=self._union_indices.size,
            slab_owners=self.subdomain_owners,
            local_layouts=layouts,
        )
        self._borrowed_auditors.append(auditor)
        return auditor

    def destroy(self) -> None:
        if self._destroyed:
            return
        for auditor in self._borrowed_auditors:
            auditor.destroy()
        self._borrowed_auditors = []
        if self._inner_ksp is not None:
            self._inner_ksp.destroy()
            self._inner_ksp = None
        if self._inner_pc_context is not None:
            self._inner_pc_context.smoother = None
            self._inner_pc_context = None
        local_destroy_diagnostics = []
        for factor in self._factors:
            if factor.local_backend is not None:
                factor.local_backend.destroy()
                backend = dict(factor.local_backend.diagnostics)
            else:
                backend = {"identity": factor.local_solver_type, "destroyed": True}
            local_destroy_diagnostics.append(
                {
                    "subdomain": factor.subdomain,
                    "owner_rank": factor.owner_rank,
                    "backend_identity": backend.get("identity"),
                    "destroyed": bool(backend.get("destroyed", True)),
                }
            )
            factor.solution.destroy()
            factor.rhs.destroy()
            if factor.factor_matrix is not None:
                factor.factor_matrix.destroy()
            if factor.ksp is not None:
                factor.ksp.destroy()
            if factor.matrix is not None:
                factor.matrix.destroy()
        self._factors = []
        self._scatter.destroy()
        for gathered_target in self._gathered_targets:
            gathered_target.destroy()
        self._gathered_targets = []
        self._gathered_source.destroy()
        self.destroy_diagnostics = sorted(
            (
                item
                for packet in self.comm.allgather(local_destroy_diagnostics)
                for item in packet
            ),
            key=lambda item: item["subdomain"],
        )
        self._destroyed = True
