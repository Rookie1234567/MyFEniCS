from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, Sequence

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
from mpi4py import MPI
from petsc4py import PETSc


TINY = np.finfo(float).tiny


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
    indices: np.ndarray
    union_positions: np.ndarray
    weights: np.ndarray
    matrix: PETSc.Mat
    ksp: PETSc.KSP
    rhs: PETSc.Vec
    solution: PETSc.Vec


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
        action_operator: PETSc.Mat | None = None,
        interpolation: str = "basic",
        assembly_order: str = "combined",
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        if not subdomains:
            raise ValueError("distributed physical-slab smoother needs subdomains")
        if smoother_iterations < 1:
            raise ValueError("smoother_iterations must be positive")
        if local_ksp_iterations < 1:
            raise ValueError("local_ksp_iterations must be positive")
        if local_ksp_type not in {"gmres", "richardson"}:
            raise ValueError("local_ksp_type must be 'gmres' or 'richardson'")
        if smoother_iterations > 1 and action_operator is None:
            raise ValueError("multiple smoothing steps require an action operator")
        if interpolation not in {"basic", "partition"}:
            raise ValueError("interpolation must be 'basic' or 'partition'")
        if assembly_order not in {"combined", "two_color"}:
            raise ValueError("assembly_order must be 'combined' or 'two_color'")

        self.comm = matrix.getComm().tompi4py()
        self.rank = int(self.comm.rank)
        self.comm_size = int(self.comm.size)
        self.global_size = int(matrix.getSize()[0])
        self.interpolation = interpolation
        self.assembly_order = assembly_order
        self.local_ksp_iterations = int(local_ksp_iterations)
        self.local_ksp_type = local_ksp_type
        self.smoother_iterations = int(smoother_iterations)
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self._destroyed = False
        self._inner_ksp: PETSc.KSP | None = None
        self._inner_pc_context: _DistributedPhysicalSlabPcContext | None = None

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

        extraction_sets = [
            PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
            for indices in local_indices
        ]
        submatrices = matrix.createSubMatrices(extraction_sets)
        for index_set in extraction_sets:
            index_set.destroy()

        self._factors: list[_OwnedSubdomainFactor] = []
        for subdomain, indices, submatrix in zip(
            self.local_subdomains,
            local_indices,
            submatrices,
            strict=True,
        ):
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
            self._factors.append(
                _OwnedSubdomainFactor(
                    subdomain=subdomain,
                    indices=indices,
                    union_positions=union_positions,
                    weights=weights,
                    matrix=submatrix,
                    ksp=ksp,
                    rhs=rhs,
                    solution=solution,
                )
            )
        self.comm.Barrier()
        if progress is not None:
            progress(len(normalized), len(normalized))

        local_rows = sum(factor.indices.size for factor in self._factors)
        local_nnz = sum(
            int(factor.matrix.getInfo()["nz_used"]) for factor in self._factors
        )
        self.global_factor_rows = int(self.comm.allreduce(local_rows, op=MPI.SUM))
        self.global_factor_nnz = int(self.comm.allreduce(local_nnz, op=MPI.SUM))
        self.maximum_owner_rows = int(self.comm.allreduce(local_rows, op=MPI.MAX))
        self.minimum_owner_rows = int(self.comm.allreduce(local_rows, op=MPI.MIN))

        if self.smoother_iterations > 1:
            self._inner_pc_context = _DistributedPhysicalSlabPcContext(self)
            self._inner_ksp = PETSc.KSP().create(matrix.getComm())
            self._inner_ksp.setOperators(action_operator)
            self._inner_ksp.setType("gmres")
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
            factor.rhs.getArray()[:] = gathered_source[factor.union_positions]
            factor.solution.set(0.0)
            factor.ksp.solve(factor.rhs, factor.solution)
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
        return {
            "subdomain_owners": list(self.subdomain_owners),
            "local_subdomains": list(self.local_subdomains),
            "interpolation": self.interpolation,
            "assembly_order": self.assembly_order,
            "local_ksp_iterations": self.local_ksp_iterations,
            "local_ksp_type": self.local_ksp_type,
            "smoother_iterations": self.smoother_iterations,
            "global_factor_rows": self.global_factor_rows,
            "global_factor_nnz": self.global_factor_nnz,
            "maximum_owner_rows": self.maximum_owner_rows,
            "minimum_owner_rows": self.minimum_owner_rows,
            "one_level_apply_count": self.apply_count,
            "one_level_mean_apply_s": self.apply_elapsed_s / max(self.apply_count, 1),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._inner_ksp is not None:
            self._inner_ksp.destroy()
            self._inner_ksp = None
        if self._inner_pc_context is not None:
            self._inner_pc_context.smoother = None
            self._inner_pc_context = None
        for factor in self._factors:
            factor.solution.destroy()
            factor.rhs.destroy()
            factor.ksp.destroy()
            factor.matrix.destroy()
        self._factors = []
        self._scatter.destroy()
        for gathered_target in self._gathered_targets:
            gathered_target.destroy()
        self._gathered_targets = []
        self._gathered_source.destroy()
        self._destroyed = True
