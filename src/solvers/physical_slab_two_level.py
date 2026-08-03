from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from typing import Any, Callable, Sequence

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.geometry.tetra_mesh_audit import canonical_owned_cell_ids


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


def build_active_trace_floquet_basis(
    condensed: Any,
    function_space: Any,
    config: Any,
    floquet_data: Any,
    fine_operator: PETSc.Mat,
) -> tuple[SparseCoarseVector, ...]:
    """Build the fixed 75D Floquet basis directly in active trace rows."""

    active_original = np.asarray(
        condensed.trace_constraints.owned_active_original_dofs,
        dtype=PETSc.IntType,
    )
    active_ids = np.asarray(
        [
            condensed.trace_constraints.original_to_active[int(original)]
            for original in active_original
        ],
        dtype=PETSc.IntType,
    )
    centers = np.linspace(
        float(config.domain_z_min), float(config.domain_z_max), 25
    )
    spacing = float(centers[1] - centers[0])
    field = fem.Function(function_space)
    candidates: list[PETSc.Vec] = []
    try:
        for center in centers:
            for component in range(3):

                def value(x, center=center, component=component):
                    envelope = np.maximum(
                        1.0 - np.abs(x[2] - center) / spacing, 0.0
                    )
                    phase = np.exp(
                        1j
                        * (
                            complex(config.kx) * x[0]
                            + complex(config.ky) * x[1]
                        )
                    )
                    values = np.zeros((3, x.shape[1]), dtype=PETSc.ScalarType)
                    values[component, :] = envelope * phase
                    return values

                field.interpolate(value)
                floquet_data.mpc.homogenize(field)
                vector = fine_operator.createVecRight()
                vector.setValues(
                    active_ids,
                    field.x.petsc_vec.getValues(active_original),
                )
                vector.assemble()
                for accepted in candidates:
                    vector.axpy(-np.conjugate(accepted.dot(vector)), accepted)
                norm = float(vector.norm())
                if norm <= 1.0e-10:
                    vector.destroy()
                    raise RuntimeError("active Floquet coarse vector became singular")
                vector.scale(1.0 / norm)
                candidates.append(vector)
        compressed = tuple(compress_petsc_vector(vector) for vector in candidates)
    finally:
        for vector in candidates:
            vector.destroy()
    return compressed


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


def _trace_slab_rows_and_incidence(
    canonical_ids: Sequence[int],
    records: Sequence[Any],
    recovery_maps: Sequence[Any],
    constraints: Any,
    slab_intervals: Sequence[tuple[float, float]],
) -> tuple[list[np.ndarray], list[tuple[int, int]]]:
    local_rows = [set() for _ in slab_intervals]
    incidence: list[tuple[int, int]] = []
    for canonical_id, record, recovery in zip(
        canonical_ids, records, recovery_maps, strict=True
    ):
        cell_rows: set[int] = set()
        for original in recovery.trace_original_dofs:
            active_ids, coefficients = constraints.expansion_by_original[int(original)]
            cell_rows.update(
                int(active)
                for active, coefficient in zip(active_ids, coefficients, strict=True)
                if coefficient != 0
            )
        incidence.extend((active, int(canonical_id)) for active in cell_rows)
        z_min = float(np.min(record.coordinates[:, 2]))
        z_max = float(np.max(record.coordinates[:, 2]))
        for slab, (low, high) in enumerate(slab_intervals):
            if z_max >= low and z_min <= high:
                local_rows[slab].update(cell_rows)
    return [
        np.asarray(sorted(rows), dtype=PETSc.IntType) for rows in local_rows
    ], incidence


def _support_multiset_sha256(supports: Sequence[tuple[int, ...]]) -> str:
    ordered = sorted(
        tuple(sorted(int(cell) for cell in support)) for support in supports
    )
    digest = hashlib.sha256()
    digest.update(len(ordered).to_bytes(8, "little"))
    for support in ordered:
        payload = np.asarray(support, dtype="<i8").tobytes()
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return digest.hexdigest()


def build_trace_aware_physical_slab_partition(
    condensed: Any,
    mesh: Any,
    *,
    domain_z: tuple[float, float],
    num_slabs: int,
    overlap_fraction: float,
) -> tuple[tuple[np.ndarray, ...], dict[str, Any]]:
    """Build physical-z slabs from condensed trace support, excluding auxiliaries."""

    z_min, z_max = (float(value) for value in domain_z)
    if not z_min < z_max or num_slabs < 1 or overlap_fraction < 0.0:
        raise ValueError("invalid physical slab domain, count, or overlap")
    canonical_ids, records, _ = canonical_owned_cell_ids(mesh)
    recovery_maps = condensed.cell_recovery_maps
    comm = condensed.matrix.getComm().tompi4py()
    if comm.allreduce(len(records) != len(recovery_maps), MPI.LOR):
        raise RuntimeError("canonical cell geometry is not aligned with recovery maps")
    active_rows = int(condensed.active_rows)
    local_invalid = any(
        int(active) < 0 or int(active) >= active_rows
        for recovery in recovery_maps
        for original in recovery.trace_original_dofs
        for active in condensed.trace_constraints.expansion_by_original[int(original)][
            0
        ]
    )
    if comm.allreduce(local_invalid, MPI.LOR):
        raise RuntimeError("trace expansion produced an out-of-range or auxiliary row")
    width = (z_max - z_min) / num_slabs
    slab_intervals = tuple(
        (
            z_min + slab * width - overlap_fraction * width,
            z_min + (slab + 1) * width + overlap_fraction * width,
        )
        for slab in range(num_slabs)
    )
    local_subdomains, local_incidence = _trace_slab_rows_and_incidence(
        canonical_ids,
        records,
        recovery_maps,
        condensed.trace_constraints,
        slab_intervals,
    )
    subdomains = gather_global_subdomain_indices(local_subdomains, comm=comm)
    union = np.unique(np.concatenate(subdomains))
    if not np.array_equal(union, np.arange(active_rows, dtype=PETSc.IntType)):
        raise RuntimeError("physical slabs do not cover every active trace row")
    packets = comm.gather(local_incidence, root=0)
    audit = None
    if comm.rank == 0:
        supports_by_row = [set() for _ in range(active_rows)]
        for packet in packets:
            for row, canonical_id in packet:
                supports_by_row[row].add(canonical_id)
        multiplicity = np.zeros(active_rows, dtype=np.int64)
        for subdomain in subdomains:
            multiplicity[subdomain] += 1
        supports = [tuple(sorted(support)) for support in supports_by_row]
        audit = {
            "active_rows": active_rows,
            "appended_rows": int(condensed.appended_rows),
            "auxiliary_rows_in_subdomains": 0,
            "coverage_pass": True,
            "union_rows": int(union.size),
            "out_of_range_rows": 0,
            "slab_row_counts": [int(rows.size) for rows in subdomains],
            "multiplicity_histogram": {
                str(value): int(np.count_nonzero(multiplicity == value))
                for value in sorted(set(multiplicity.tolist()))
            },
            "max_multiplicity": int(np.max(multiplicity)),
            "multiplicity_gt_one_rows": int(np.count_nonzero(multiplicity > 1)),
            "multiplicity_eq_one_rows": int(np.count_nonzero(multiplicity == 1)),
            "global_support_hash": _support_multiset_sha256(supports),
            "per_slab_support_hashes": [
                _support_multiset_sha256([supports[int(row)] for row in subdomain])
                for subdomain in subdomains
            ],
        }
    return subdomains, comm.bcast(audit, root=0)


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
    exact_fingerprint: str
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
        smoother_ksp_type: str = "gmres",
        action_operator: PETSc.Mat | None = None,
        diagonal_shift: PETSc.Vec | None = None,
        factor_only_storage: bool = False,
        local_solver_types: Sequence[str] | None = None,
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
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self._destroyed = False
        self._inner_ksp: PETSc.KSP | None = None
        self._inner_pc_context: _DistributedPhysicalSlabPcContext | None = None

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
            factor_matrix: PETSc.Mat | None = None
            retained_matrix: PETSc.Mat | None = None
            retained_ksp: PETSc.KSP | None = None
            diagonal_inverse: np.ndarray | None = None
            if local_solver_type == "jacobi":
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
            else:
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
                factor_nnz = int(pc.getFactorMatrix().getInfo()["nz_used"])
                retained_matrix = submatrix
                retained_ksp = ksp
                if self.factor_only_storage:
                    factor_matrix = pc.getFactorMatrix()
                    factor_matrix.incRef()
                    ksp.destroy()
                    submatrix.destroy()
                    retained_ksp = None
                    retained_matrix = None
            return _OwnedSubdomainFactor(
                subdomain=subdomain,
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
                exact_fingerprint=exact_fingerprint,
                rhs=rhs,
                solution=solution,
            )

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
            factor.rhs.getArray()[:] = gathered_source[factor.union_positions]
            factor.solution.set(0.0)
            if factor.factor_matrix is not None:
                factor.factor_matrix.solve(factor.rhs, factor.solution)
            elif factor.diagonal_inverse is not None:
                factor.solution.getArray()[:] = (
                    factor.diagonal_inverse * factor.rhs.getArray(readonly=True)
                )
            else:
                assert factor.ksp is not None
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
        self._destroyed = True
