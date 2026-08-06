from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.geometry.tetra_mesh_audit import canonical_owned_cell_ids, owned_cell_geometry
from src.solvers.hcurl_assembly_time_condensation import _cell_trace_expansion
from src.solvers.static_factor_reuse import (
    _canonical_global_row_ids_fingerprint,
    _exact_reuse_necessary_prefix,
)
from src.solvers.static_fullspace_slab_oracle import FullSpaceSlabCellRecord
from src.solvers.static_local_schur_action import (
    iter_owned_constrained_schur_contributions,
)


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
    """Fingerprint only the shifted local numeric SeqAIJ matrix."""

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
    centers = np.linspace(float(config.domain_z_min), float(config.domain_z_max), 25)
    spacing = float(centers[1] - centers[0])
    field = fem.Function(function_space)
    candidates: list[PETSc.Vec] = []
    try:
        for center in centers:
            for component in range(3):

                def value(x, center=center, component=component):
                    envelope = np.maximum(1.0 - np.abs(x[2] - center) / spacing, 0.0)
                    phase = np.exp(
                        1j * (complex(config.kx) * x[0] + complex(config.ky) * x[1])
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


@dataclass(frozen=True)
class OwnerLocalSlabPlan:
    """Rank-local slab rows and owned-cell routing metadata for M2a."""

    comm: MPI.Comm = field(repr=False)
    active_rows: int
    slab_owners: tuple[int, ...]
    owner_rows: tuple[np.ndarray, ...]
    local_cell_indices_by_slab: tuple[tuple[int, ...], ...]
    slab_row_counts: tuple[int, ...]
    partition_weights_by_slab: tuple[np.ndarray, ...]
    ras_core_masks_by_slab: tuple[np.ndarray, ...]
    interface_masks_by_slab: tuple[np.ndarray, ...]
    ras_core_sum_error: float
    interface_row_count: int


def _owner_from_scalar_row_counts(
    row_counts: np.ndarray, comm_size: int
) -> tuple[int, ...]:
    loads = np.zeros(comm_size, dtype=np.int64)
    owners = np.empty(len(row_counts), dtype=np.int32)
    for slab in sorted(
        range(len(row_counts)),
        key=lambda index: (-int(row_counts[index]), index),
    ):
        owner = int(np.argmin(loads))
        owners[slab] = owner
        loads[owner] += int(row_counts[slab])
    return tuple(int(value) for value in owners)


def build_owner_local_slab_plan(
    condensed: Any,
    mesh: Any,
    *,
    domain_z: tuple[float, float],
    num_slabs: int,
    overlap_fraction: float,
) -> OwnerLocalSlabPlan:
    """Route complete slab row sets to owners without using ``condensed.matrix``."""

    z_min, z_max = (float(value) for value in domain_z)
    if not z_min < z_max or num_slabs < 1 or overlap_fraction < 0.0:
        raise ValueError("invalid physical slab domain, count, or overlap")
    records = owned_cell_geometry(mesh)
    recovery_maps = condensed.cell_recovery_maps
    comm = condensed.comm
    local_alignment_error = len(records) != len(recovery_maps)
    if comm.allreduce(local_alignment_error, op=MPI.LOR):
        raise RuntimeError("owned cell geometry and recovery maps are not aligned")
    layout = condensed.create_active_vector()
    active_start, active_end = layout.getOwnershipRange()
    ownership_ranges = tuple(comm.allgather((int(active_start), int(active_end))))
    layout.destroy()
    width = (z_max - z_min) / num_slabs
    intervals = tuple(
        (
            z_min + slab * width - overlap_fraction * width,
            z_min + (slab + 1) * width + overlap_fraction * width,
        )
        for slab in range(num_slabs)
    )
    local_seed_masks: dict[int, int] = {}
    local_query_rows: set[int] = set()
    for cell_index, (record, recovery) in enumerate(
        zip(records, recovery_maps, strict=True)
    ):
        cell_rows = set()
        for original in recovery.trace_original_dofs:
            active_ids, coefficients = (
                condensed.trace_constraints.expansion_by_original[int(original)]
            )
            cell_rows.update(
                int(active)
                for active, coefficient in zip(active_ids, coefficients, strict=True)
                if coefficient != 0
            )
        local_query_rows.update(cell_rows)
        z_cell_min = float(np.min(record.coordinates[:, 2]))
        z_cell_max = float(np.max(record.coordinates[:, 2]))
        cell_mask = 0
        for slab, (low, high) in enumerate(intervals):
            if cell_rows and z_cell_max >= low and z_cell_min <= high:
                cell_mask |= 1 << slab
        for row in cell_rows:
            local_seed_masks[row] = local_seed_masks.get(row, 0) | cell_mask

    def row_owner(row: int) -> int:
        for rank, (_start, end) in enumerate(ownership_ranges):
            if row < end:
                return rank
        raise RuntimeError("active row is outside its PETSc ownership ranges")

    seed_packets: list[list[tuple[int, int]]] = [[] for _ in range(comm.size)]
    for row in sorted(local_query_rows):
        seed_packets[row_owner(row)].append((row, local_seed_masks.get(row, 0)))
    received_seed_packets = comm.alltoall(seed_packets)
    owned_row_masks: dict[int, int] = {}
    query_sources = [set() for _ in range(comm.size)]
    for source, packet in enumerate(received_seed_packets):
        for row, seed_mask in packet:
            owned_row_masks[row] = owned_row_masks.get(row, 0) | int(seed_mask)
            query_sources[source].add(int(row))
    row_counts_local = np.zeros(num_slabs, dtype=np.int64)
    for mask in owned_row_masks.values():
        for slab in range(num_slabs):
            row_counts_local[slab] += (mask >> slab) & 1
    covered_rows = int(
        comm.allreduce(
            sum(int(mask != 0) for mask in owned_row_masks.values()),
            op=MPI.SUM,
        )
    )
    if covered_rows != int(condensed.active_rows):
        raise RuntimeError("owned row masks do not cover all active trace rows")
    row_counts = np.asarray(comm.allreduce(row_counts_local, op=MPI.SUM))
    owners = _owner_from_scalar_row_counts(row_counts, comm.size)
    response_packets: list[list[tuple[int, int, int]]] = [[] for _ in range(comm.size)]
    for source, rows in enumerate(query_sources):
        for row in sorted(rows):
            response_packets[source].append(
                (
                    int(row),
                    int(owned_row_masks.get(row, 0)),
                    int(owned_row_masks.get(row, 0)).bit_count(),
                )
            )
    owner_slab_masks = [0 for _ in range(comm.size)]
    for slab, owner in enumerate(owners):
        owner_slab_masks[owner] |= 1 << slab
    for owner, slab_mask in enumerate(owner_slab_masks):
        for row, mask in owned_row_masks.items():
            if int(mask) & slab_mask:
                response_packets[owner].append(
                    (int(row), int(mask), int(mask).bit_count())
                )
    received_responses = comm.alltoall(response_packets)
    local_row_masks: dict[int, int] = {}
    local_row_multiplicities: dict[int, int] = {}
    for packet in received_responses:
        for row, mask, row_multiplicity in packet:
            local_row_masks[int(row)] = local_row_masks.get(int(row), 0) | int(mask)
            local_row_multiplicities[int(row)] = int(row_multiplicity)
    local_cells_by_slab = [[] for _ in intervals]
    for cell_index, recovery in enumerate(recovery_maps):
        cell_rows = set()
        for original in recovery.trace_original_dofs:
            active_ids, coefficients = (
                condensed.trace_constraints.expansion_by_original[int(original)]
            )
            cell_rows.update(
                int(active)
                for active, coefficient in zip(active_ids, coefficients, strict=True)
                if coefficient != 0
            )
        cell_mask = 0
        for row in cell_rows:
            cell_mask |= local_row_masks.get(row, 0)
        for slab in range(num_slabs):
            if cell_mask & (1 << slab):
                local_cells_by_slab[slab].append(cell_index)
    empty = np.empty(0, dtype=PETSc.IntType)
    owner_rows: list[np.ndarray] = []
    for slab, owner in enumerate(owners):
        if comm.rank == owner:
            rows = np.asarray(
                sorted(
                    row for row, mask in local_row_masks.items() if mask & (1 << slab)
                ),
                dtype=PETSc.IntType,
            )
        else:
            rows = empty.copy()
        owner_rows.append(rows)
    owned_invalid = any(
        owners[slab] == comm.rank and int(rows.size) != int(row_counts[slab])
        for slab, rows in enumerate(owner_rows)
    )
    if comm.allreduce(owned_invalid, op=MPI.LOR):
        raise RuntimeError("slab owner did not receive its active row closure")
    partition_weights_by_slab: list[np.ndarray] = []
    ras_core_masks_by_slab: list[np.ndarray] = []
    interface_masks_by_slab: list[np.ndarray] = []
    for slab, owner in enumerate(owners):
        if comm.rank != owner:
            partition_weights_by_slab.append(empty.copy())
            ras_core_masks_by_slab.append(np.empty(0, dtype=np.bool_))
            interface_masks_by_slab.append(np.empty(0, dtype=np.bool_))
            continue
        rows = owner_rows[slab]
        counts = np.asarray(
            [local_row_multiplicities[int(row)] for row in rows],
            dtype=np.int32,
        )
        partition_weights_by_slab.append(
            np.asarray(1.0 / counts, dtype=PETSc.ScalarType)
        )
        masks = [int(local_row_masks[int(row)]) for row in rows]
        slab_bit = 1 << slab
        ras_core_masks_by_slab.append(
            np.asarray(
                [
                    bool(mask & slab_bit) and (mask & -mask) == slab_bit
                    for mask in masks
                ],
                dtype=np.bool_,
            )
        )
        interface_masks_by_slab.append(np.asarray(counts > 1, dtype=np.bool_))

    ras_core_sum = condensed.create_active_vector()
    ras_core_sum.set(0.0)
    for slab, owner in enumerate(owners):
        if comm.rank == owner:
            rows = owner_rows[slab]
            values = np.asarray(ras_core_masks_by_slab[slab], dtype=PETSc.ScalarType)
            ras_core_sum.setValues(rows, values, addv=PETSc.InsertMode.ADD_VALUES)
    ras_core_sum.assemble()
    local_core_error = (
        np.asarray(ras_core_sum.getArray(readonly=True), dtype=PETSc.ScalarType) - 1.0
    )
    ras_core_sum_error = float(
        comm.allreduce(float(np.max(np.abs(local_core_error), initial=0.0)), op=MPI.MAX)
    )
    ras_core_sum.destroy()
    interface_row_count = int(
        comm.allreduce(
            sum(int(mask.bit_count() > 1) for mask in owned_row_masks.values()),
            op=MPI.SUM,
        )
    )
    if ras_core_sum_error > 1.0e-12:
        raise RuntimeError("RAS core masks do not form a unity sum")
    return OwnerLocalSlabPlan(
        comm=comm,
        active_rows=int(condensed.active_rows),
        slab_owners=owners,
        owner_rows=tuple(owner_rows),
        local_cell_indices_by_slab=tuple(
            tuple(int(cell) for cell in cells) for cells in local_cells_by_slab
        ),
        slab_row_counts=tuple(int(value) for value in row_counts),
        partition_weights_by_slab=tuple(partition_weights_by_slab),
        ras_core_masks_by_slab=tuple(ras_core_masks_by_slab),
        interface_masks_by_slab=tuple(interface_masks_by_slab),
        ras_core_sum_error=ras_core_sum_error,
        interface_row_count=interface_row_count,
    )


_CANONICAL_CELL_ID_HASH_ALGORITHM = (
    "task037.fullspace-slab-cell-ids-order.v1|dtype=<i8|order=C|count=u64"
)


def _canonical_cell_id_sequence_sha256(values: Sequence[int] | np.ndarray) -> str:
    canonical = np.asarray(values, dtype="<i8")
    digest = hashlib.sha256()
    digest.update(_CANONICAL_CELL_ID_HASH_ALGORITHM.encode("ascii"))
    digest.update(b"\0")
    digest.update(np.asarray([canonical.size], dtype="<u8").tobytes())
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _pack_slab_trace_expansion(expansion: sp.csr_matrix) -> tuple:
    return (
        tuple(int(value) for value in expansion.shape),
        np.asarray(expansion.data, dtype=np.complex128).copy(),
        np.asarray(expansion.indices).copy(),
        np.asarray(expansion.indptr).copy(),
    )


def _unpack_slab_trace_expansion(packet: tuple) -> sp.csr_matrix:
    shape, data, indices, indptr = packet
    return sp.csr_matrix(
        (data, indices, indptr),
        shape=tuple(int(value) for value in shape),
    )


def collect_owner_local_fullspace_slab_cells(
    condensed: Any,
    plan: OwnerLocalSlabPlan,
    mesh: Any,
    slab: int,
) -> tuple[tuple[FullSpaceSlabCellRecord, ...], dict[str, Any]]:
    """Collect one owner-local slab's sparse full-space cell records."""

    if slab < 0 or slab >= len(plan.slab_owners):
        raise ValueError("slab index is out of range")
    retained = condensed.retained_fullspace_slab_blocks_by_class
    if retained is None:
        raise ValueError("full-space slab blocks are not retained")
    comm = plan.comm
    owner = int(plan.slab_owners[slab])
    canonical_ids, _records, _ordered_keys = canonical_owned_cell_ids(mesh)
    local_cell_indices = plan.local_cell_indices_by_slab[slab]
    local_blocks = {}
    local_descriptors = []
    for cell_index in local_cell_indices:
        recovery = condensed.cell_recovery_maps[int(cell_index)]
        class_key = recovery.class_key
        block = retained.get(class_key)
        if block is None:
            raise RuntimeError(
                f"retained full-space block is missing class {class_key!r}"
            )
        local_blocks.setdefault(class_key, block)
        active_ids, expansion, _identity = _cell_trace_expansion(
            recovery.trace_original_dofs,
            condensed.trace_constraints,
        )
        local_descriptors.append(
            (
                int(canonical_ids[int(cell_index)]),
                class_key,
                np.asarray(active_ids, dtype=PETSc.IntType),
                _pack_slab_trace_expansion(expansion),
            )
        )
    payload = (local_blocks, tuple(local_descriptors))
    global_cell_count = int(
        comm.allreduce(len(local_cell_indices), op=MPI.SUM)
    )
    condensed_trace_matrix_materialized = bool(
        comm.allreduce(
            condensed.matrix is not None,
            op=MPI.LOR,
        )
    )
    packets = comm.gather(payload, root=owner)

    cells: tuple[FullSpaceSlabCellRecord, ...] = ()
    audit = None
    owner_error = None
    if comm.rank == owner:
        block_by_class = {}
        descriptors = []
        for source_blocks, source_descriptors in packets:
            for class_key, block in source_blocks.items():
                block_by_class.setdefault(class_key, block)
            descriptors.extend(source_descriptors)
        descriptors.sort(key=lambda descriptor: descriptor[0])
        try:
            owner_rows = np.asarray(plan.owner_rows[slab], dtype=PETSc.IntType)
            collected = []
            for canonical_id, class_key, active_ids, expansion_packet in descriptors:
                block = block_by_class.get(class_key)
                if block is None:
                    raise RuntimeError(
                        f"owner is missing full-space block for class {class_key!r}"
                    )
                owner_positions = np.searchsorted(owner_rows, active_ids)
                if np.any(owner_positions >= owner_rows.size):
                    raise RuntimeError(
                        "cell active rows are outside the slab owner rows"
                    )
                if owner_positions.size and not np.array_equal(
                    owner_rows[owner_positions],
                    active_ids,
                ):
                    raise RuntimeError(
                        "cell active rows are not contained in slab owner rows"
                    )
                collected.append(
                    FullSpaceSlabCellRecord(
                        block=block,
                        canonical_cell_id=int(canonical_id),
                        trace_expansion=_unpack_slab_trace_expansion(
                            expansion_packet
                        ),
                        active_positions=np.asarray(
                            owner_positions,
                            dtype=np.int64,
                        ),
                    )
                )
            cells = tuple(collected)
            expansion_nnz = sum(
                int(cell.trace_expansion.nnz) for cell in cells
            )
            expansion_bytes = sum(
                int(cell.trace_expansion.data.nbytes)
                + int(cell.trace_expansion.indices.nbytes)
                + int(cell.trace_expansion.indptr.nbytes)
                for cell in cells
            )
            audit = {
                "slab": int(slab),
                "owner": owner,
                "global_cell_count": global_cell_count,
                "owner_cell_count": int(len(cells)),
                "owner_active_row_count": int(owner_rows.size),
                "owner_active_row_hash": _canonical_global_row_ids_fingerprint(
                    owner_rows
                ),
                "unique_block_count": int(len(block_by_class)),
                "cell_canonical_id_hash": _canonical_cell_id_sequence_sha256(
                    [descriptor[0] for descriptor in descriptors]
                ),
                "cell_canonical_id_hash_algorithm": (
                    _CANONICAL_CELL_ID_HASH_ALGORITHM
                ),
                "sparse_expansion_nnz": int(expansion_nnz),
                "sparse_expansion_bytes": int(expansion_bytes),
                "condensed_trace_matrix_materialized": (
                    condensed_trace_matrix_materialized
                ),
            }
        except Exception as error:
            owner_error = f"{type(error).__name__}: {error}"
    owner_error = comm.bcast(owner_error, root=owner)
    if owner_error is not None:
        raise RuntimeError(owner_error)
    audit = comm.bcast(audit, root=owner)
    return cells, audit


def _route_owner_slab_cells(
    condensed: Any,
    plan: OwnerLocalSlabPlan,
    slab: int,
    consume: Callable[[int, np.ndarray, np.ndarray], None],
) -> dict[str, int]:
    comm = plan.comm
    owner = plan.slab_owners[slab]
    cells = plan.local_cell_indices_by_slab[slab]
    local_payload_max = 0
    owner_payload_max = 0
    rounds = 0
    round_index = 0
    while comm.allreduce(round_index < len(cells), op=MPI.LOR):
        has_cell = round_index < len(cells)
        payload = None
        if has_cell:
            cell_index, active_ids, block = next(
                iter_owned_constrained_schur_contributions(
                    condensed,
                    (cells[round_index],),
                )
            )
            payload_bytes = int(active_ids.nbytes + block.nbytes)
            local_payload_max = max(local_payload_max, payload_bytes)
            payload = (cell_index, active_ids, block)
        packets = comm.gather(payload, root=owner)
        if comm.rank == owner:
            round_owner_bytes = 0
            for packet in packets:
                if packet is not None:
                    cell_index, active_ids, block = packet
                    round_owner_bytes += int(active_ids.nbytes + block.nbytes)
                    consume(cell_index, active_ids, block)
            owner_payload_max = max(owner_payload_max, round_owner_bytes)
        rounds += 1
        round_index += 1
    return {
        "communication_rounds": rounds,
        "global_contribution_count": int(comm.allreduce(len(cells), op=MPI.SUM)),
        "max_sender_payload_bytes": int(comm.allreduce(local_payload_max, op=MPI.MAX)),
        "max_owner_payload_bytes": int(comm.allreduce(owner_payload_max, op=MPI.MAX)),
    }


def assemble_owner_local_slab_matrix(
    condensed: Any,
    plan: OwnerLocalSlabPlan,
    slab: int,
) -> tuple[PETSc.Mat | None, dict[str, Any]]:
    """Route one slab's cell blocks and assemble only on its deterministic owner."""

    if slab < 0 or slab >= len(plan.slab_owners):
        raise ValueError("slab index is out of range")
    owner = plan.slab_owners[slab]
    owner_rows = plan.owner_rows[slab]
    matrix = None
    if plan.comm.rank == owner:
        size = int(owner_rows.size)
        matrix = PETSc.Mat().createAIJ(
            size=(size, size),
            comm=PETSc.COMM_SELF,
        )
        matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)

        def consume(_cell_index, active_ids, block):
            owner_positions = np.searchsorted(owner_rows, active_ids)
            in_range = owner_positions < owner_rows.size
            candidate = np.flatnonzero(in_range)
            selected_cell_positions = candidate[
                owner_rows[owner_positions[candidate]] == active_ids[candidate]
            ]
            if selected_cell_positions.size == 0:
                raise RuntimeError("cell support is outside its slab owner rows")
            selected_owner_positions = np.asarray(
                owner_positions[selected_cell_positions], dtype=PETSc.IntType
            )
            local_block = np.ascontiguousarray(
                block[np.ix_(selected_cell_positions, selected_cell_positions)]
            )
            matrix.setValues(
                selected_owner_positions,
                selected_owner_positions,
                local_block,
                addv=PETSc.InsertMode.ADD_VALUES,
            )

    else:

        def consume(_cell_index, _active_ids, _block):
            return None

    route_audit = _route_owner_slab_cells(condensed, plan, slab, consume)
    if plan.comm.rank == owner:
        assert matrix is not None
        matrix.assemble()
        info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
        audit = {
            "owner_rank": int(owner),
            "owner_local_row_count": int(owner_rows.size),
            "matrix_nnz_used": int(info["nz_used"]),
            "matrix_nnz_allocated": int(info["nz_allocated"]),
            "matrix_allocation_ratio": float(
                info["nz_allocated"] / max(info["nz_used"], 1)
            ),
            "matrix_fingerprint": _exact_seqaij_fingerprint(matrix),
            "dynamic_allocation": True,
            **route_audit,
        }
    else:
        audit = None
    return matrix, plan.comm.bcast(audit, root=owner)


def build_owner_local_slab_diagonal(
    condensed: Any,
) -> tuple[PETSc.Vec, dict[str, float | int]]:
    """Build the exact distributed diagonal from the same cell contributions."""

    diagonal = condensed.create_active_vector()
    diagonal.set(0.0)
    for _cell_index, active_ids, block in iter_owned_constrained_schur_contributions(
        condensed
    ):
        values = np.diag(block)
        diagonal.setValues(active_ids, values, addv=PETSc.InsertMode.ADD_VALUES)
    diagonal.assemble()
    values = diagonal.getArray(readonly=True)
    local_max = float(np.max(np.abs(values))) if values.size else 0.0
    return diagonal, {
        "rank_local_diagonal_rows": int(diagonal.getLocalSize()),
        "global_diagonal_max_abs": float(
            condensed.comm.allreduce(local_max, op=MPI.MAX)
        ),
    }


def extract_owner_local_slab_diagonal(
    diagonal: PETSc.Vec,
    plan: OwnerLocalSlabPlan,
    slab: int,
) -> tuple[np.ndarray | None, dict[str, int]]:
    """Route only one slab owner's diagonal rows, never a full diagonal."""

    comm = plan.comm
    owner = plan.slab_owners[slab]
    ranges = tuple(comm.allgather(tuple(map(int, diagonal.getOwnershipRange()))))
    requests = [np.empty(0, dtype=PETSc.IntType) for _ in range(comm.size)]
    if comm.rank == owner:
        rows = plan.owner_rows[slab]
        for rank, (start, end) in enumerate(ranges):
            requests[rank] = rows[(rows >= start) & (rows < end)].copy()
    incoming = comm.alltoall(requests)
    local_start, _local_end = diagonal.getOwnershipRange()
    local_values = diagonal.getArray(readonly=True)
    responses = [np.empty(0, dtype=PETSc.ScalarType) for _ in range(comm.size)]
    for source, request in enumerate(incoming):
        if request.size:
            responses[source] = np.asarray(
                local_values[np.asarray(request, dtype=np.int64) - local_start],
                dtype=PETSc.ScalarType,
            ).copy()
    returned = comm.alltoall(responses)
    if comm.rank == owner:
        rows = plan.owner_rows[slab]
        values = np.empty(rows.size, dtype=PETSc.ScalarType)
        for source, request in enumerate(requests):
            if request.size:
                positions = np.searchsorted(rows, request)
                values[positions] = returned[source]
    else:
        values = None
    return values, {
        "owner_rank": int(owner),
        "owner_local_row_count": int(plan.slab_row_counts[slab]),
    }


def owner_local_slab_diagonal_shift(
    diagonal: PETSc.Vec,
    plan: OwnerLocalSlabPlan,
    slab: int,
    global_scale: float,
) -> tuple[np.ndarray | None, dict[str, int]]:
    """Return the existing exact complex diagonal shift on one slab owner."""

    values, audit = extract_owner_local_slab_diagonal(diagonal, plan, slab)
    if values is not None:
        values = -1j * 0.1 * np.maximum(np.abs(values), 1.0e-12 * float(global_scale))
    return values, audit


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
    canonical_global_row_ids_fingerprint: str
    exact_reuse_necessary_prefix: str
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

    def _initialize_apply_state(
        self,
        local_indices: Sequence[np.ndarray],
        template: PETSc.Vec,
    ) -> None:
        if local_indices:
            self._union_indices = np.unique(np.concatenate(local_indices)).astype(
                PETSc.IntType, copy=False
            )
        else:
            self._union_indices = np.empty(0, dtype=PETSc.IntType)
        self._gathered_source = PETSc.Vec().createSeq(
            self._union_indices.size, comm=PETSc.COMM_SELF
        )
        target_count = 2 if self.assembly_order == "two_color" else 1
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

    def _build_owned_factor(
        self,
        subdomain: int,
        indices: np.ndarray,
        submatrix: PETSc.Mat,
        *,
        diagonal_shift: np.ndarray | None,
        multiplicity: np.ndarray | None,
        partition_weights: np.ndarray | None = None,
    ) -> _OwnedSubdomainFactor:
        if diagonal_shift is not None:
            submatrix_diagonal = submatrix.createVecLeft()
            submatrix.getDiagonal(submatrix_diagonal)
            submatrix_diagonal.getArray()[:] += diagonal_shift
            submatrix.setDiagonal(submatrix_diagonal)
            submatrix.assemble()
            submatrix_diagonal.destroy()
        union_positions = np.searchsorted(self._union_indices, indices).astype(
            PETSc.IntType, copy=False
        )
        if np.any(self._union_indices[union_positions] != indices):
            raise RuntimeError("subdomain indices are absent from the rank union")
        if self.interpolation == "partition":
            if partition_weights is not None:
                weights = np.asarray(partition_weights, dtype=PETSc.ScalarType)
                if weights.size != indices.size:
                    raise RuntimeError("partition weights are not owner-row aligned")
            elif multiplicity is not None:
                weights = np.asarray(
                    1.0 / multiplicity[indices], dtype=PETSc.ScalarType
                )
            else:
                raise RuntimeError("partition interpolation needs row weights")
        else:
            weights = np.ones(indices.size, dtype=PETSc.ScalarType)
        rhs = submatrix.createVecRight()
        solution = submatrix.createVecLeft()
        exact_fingerprint = _exact_seqaij_fingerprint(submatrix)
        canonical_global_row_ids_sha256 = _canonical_global_row_ids_fingerprint(
            indices
        )
        exact_reuse_necessary_prefix_sha256 = _exact_reuse_necessary_prefix(
            canonical_global_row_ids_sha256, exact_fingerprint
        )
        local_solver_type = self.local_solver_types[subdomain]
        matrix_nnz = int(submatrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"])
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
            pc.setFactorLevels(int(self.ilu_levels))
            pc.setFactorOrdering("rcm")
            ksp.setUp()
            factor_nnz = int(
                pc.getFactorMatrix().getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"]
            )
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
            canonical_global_row_ids_fingerprint=canonical_global_row_ids_sha256,
            exact_reuse_necessary_prefix=exact_reuse_necessary_prefix_sha256,
            rhs=rhs,
            solution=solution,
        )

    def _report_first_submatrix(
        self,
        setup_observer: Callable[[str, dict[str, Any]], None] | None,
        submatrix: PETSc.Mat | None,
        has_factor: bool,
        cached_payload: dict[str, Any] | None = None,
    ) -> None:
        if setup_observer is None or self._first_submatrix_reported:
            return
        self._first_submatrix_reported = True
        payload = {
            "global_matrix_rows": self.global_size,
            "global_subdomain_count": self._global_subdomain_count,
            "rank_local_has_first_submatrix": has_factor,
            "rank_local_first_submatrix_rows": None,
            "rank_local_first_submatrix_cols": None,
            "rank_local_first_submatrix_nnz": None,
        }
        if cached_payload is not None:
            payload.update(cached_payload)
        elif has_factor and submatrix is not None:
            payload.update(
                {
                    "rank_local_first_submatrix_rows": int(submatrix.getSize()[0]),
                    "rank_local_first_submatrix_cols": int(submatrix.getSize()[1]),
                    "rank_local_first_submatrix_nnz": int(
                        submatrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"]
                    ),
                }
            )
        setup_observer("first_owned_slab_submatrix_allocated", payload)

    def _report_first_factor(
        self,
        setup_observer: Callable[[str, dict[str, Any]], None] | None,
        factor: _OwnedSubdomainFactor | None,
        cached_payload: dict[str, Any] | None = None,
    ) -> None:
        if setup_observer is None or self._first_factor_reported:
            return
        self._first_factor_reported = True
        payload = {
            "rank_local_has_first_factor": factor is not None,
            "rank_local_first_factor_subdomain": (
                None if factor is None else int(factor.subdomain)
            ),
            "rank_local_first_factor_rows": (
                None if factor is None else int(factor.indices.size)
            ),
            "rank_local_first_factor_matrix_nnz": (
                None if factor is None else int(factor.matrix_nnz)
            ),
            "rank_local_first_factor_nnz": (
                None if factor is None else int(factor.factor_nnz)
            ),
        }
        if cached_payload is not None:
            payload.update(cached_payload)
        setup_observer(
            "first_owned_slab_factor_ready",
            payload,
        )

    def _finalize_factor_inventory(
        self,
        global_subdomain_count: int,
        progress: Callable[[int, int], None] | None,
        setup_observer: Callable[[str, dict[str, Any]], None] | None,
    ) -> None:
        self.comm.Barrier()
        if progress is not None:
            progress(global_subdomain_count, global_subdomain_count)
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
                (
                    int(factor.subdomain),
                    factor.exact_fingerprint,
                    factor.canonical_global_row_ids_fingerprint,
                    factor.exact_reuse_necessary_prefix,
                )
                for factor in self._factors
            ]
        )
        factor_records = sorted(
            (item for packet in fingerprint_packets for item in packet),
            key=lambda item: item[0],
        )
        self.factor_fingerprints = [
            (subdomain, shifted_matrix_sha256)
            for (
                subdomain,
                shifted_matrix_sha256,
                _row_ids_sha256,
                _prefix_sha256,
            ) in factor_records
        ]
        self.factor_reuse_fingerprints = [
            {
                "subdomain": subdomain,
                "row_ids_sha256": row_ids_sha256,
                "shifted_matrix_sha256": shifted_matrix_sha256,
                "necessary_prefix_sha256": prefix_sha256,
            }
            for (
                subdomain,
                shifted_matrix_sha256,
                row_ids_sha256,
                prefix_sha256,
            ) in factor_records
        ]
        unique_fingerprints = {
            fingerprint for _, fingerprint in self.factor_fingerprints
        }
        self.unique_factor_classes = len(unique_fingerprints)
        self.exact_duplicate_factor_count = (
            len(self.factor_fingerprints) - self.unique_factor_classes
        )
        self.numeric_local_matrix_unique_classes = self.unique_factor_classes
        self.numeric_local_matrix_duplicate_count = self.exact_duplicate_factor_count
        prefix_groups: dict[str, list[int]] = {}
        for (
            subdomain,
            _shifted_matrix_sha256,
            _row_ids_sha256,
            prefix_sha256,
        ) in factor_records:
            prefix_groups.setdefault(prefix_sha256, []).append(subdomain)
        self.exact_reuse_necessary_prefix_groups = [
            {
                "prefix_sha256": prefix_sha256,
                "subdomains": sorted(subdomains),
            }
            for prefix_sha256, subdomains in sorted(prefix_groups.items())
        ]
        self.exact_reuse_necessary_prefix_unique_classes = len(prefix_groups)
        self.exact_reuse_candidate_count = sum(
            max(len(subdomains) - 1, 0) for subdomains in prefix_groups.values()
        )
        self.exact_reuse_qualified_count = 0
        qualification_status = (
            "not_evaluated_after_necessary_condition_stop"
            if self.exact_reuse_candidate_count == 0
            else "not_evaluated_pending_necessary_prefix_candidates"
        )
        self.exact_reuse_qualification_status = qualification_status
        self.exact_reuse_deferred_checks = {
            name: qualification_status
            for name in (
                "material_cell_class_identity",
                "diagonal_shift_identity",
                "factor_ordering",
                "factor_values_or_deterministic_factor_fingerprint",
            )
        }
        if setup_observer is not None:
            setup_observer(
                "all_slab_factors_ready",
                {
                    "global_factor_rows": self.global_factor_rows,
                    "global_factor_nnz": self.global_factor_nnz,
                    "global_stored_factor_nnz": self.global_stored_factor_nnz,
                    "global_unique_factor_classes": self.unique_factor_classes,
                    "global_exact_duplicate_factor_count": (
                        self.exact_duplicate_factor_count
                    ),
                    "global_numeric_local_matrix_duplicate_count": (
                        self.numeric_local_matrix_duplicate_count
                    ),
                    "global_exact_reuse_necessary_prefix_unique_classes": (
                        self.exact_reuse_necessary_prefix_unique_classes
                    ),
                    "global_exact_reuse_candidate_count": (
                        self.exact_reuse_candidate_count
                    ),
                    "global_exact_reuse_qualified_count": (
                        self.exact_reuse_qualified_count
                    ),
                    "global_exact_reuse_qualification_status": (
                        self.exact_reuse_qualification_status
                    ),
                    "rank_local_factor_count": len(self._factors),
                    "rank_local_factor_rows": int(local_rows),
                    "rank_local_factor_nnz": int(local_nnz),
                    "rank_local_stored_factor_nnz": int(local_factor_nnz),
                },
            )

    def _initialize_inner_ksp(self, action_operator: PETSc.Mat | None) -> None:
        if self.smoother_iterations <= 1:
            return
        if action_operator is None:
            raise ValueError("multiple smoothing steps require an action operator")
        self._inner_pc_context = _DistributedPhysicalSlabPcContext(self)
        self._inner_ksp = PETSc.KSP().create(action_operator.getComm())
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
        setup_observer: Callable[[str, dict[str, Any]], None] | None = None,
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
        self.ilu_levels = int(ilu_levels)
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
        self._first_submatrix_reported = False
        self._first_factor_reported = False
        self._global_subdomain_count = len(subdomains)

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
        template = matrix.createVecRight()
        self._initialize_apply_state(local_indices, template)
        template.destroy()

        self._factors: list[_OwnedSubdomainFactor] = []

        def build_factor(
            subdomain: int, indices: np.ndarray, submatrix: PETSc.Mat
        ) -> _OwnedSubdomainFactor:
            return self._build_owned_factor(
                subdomain,
                indices,
                submatrix,
                diagonal_shift=(
                    None
                    if global_diagonal_shift is None
                    else global_diagonal_shift[indices]
                ),
                multiplicity=multiplicity,
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
                    if slot == 0:
                        self._report_first_submatrix(setup_observer, submatrix, True)
                    factor = build_factor(
                        self.local_subdomains[slot], indices, submatrix
                    )
                    if slot == 0:
                        self._report_first_factor(setup_observer, factor)
                    self._factors.append(factor)
                else:
                    submatrix.destroy()
                    if slot == 0:
                        self._report_first_submatrix(setup_observer, None, False)
                        self._report_first_factor(setup_observer, None)
        elif self.factor_only_storage:
            for slot, (subdomain, indices) in enumerate(
                zip(self.local_subdomains, local_indices, strict=True)
            ):
                extraction_set = PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
                submatrix = matrix.createSubMatrices([extraction_set])[0]
                extraction_set.destroy()
                if slot == 0:
                    self._report_first_submatrix(setup_observer, submatrix, True)
                factor = build_factor(subdomain, indices, submatrix)
                if slot == 0:
                    self._report_first_factor(setup_observer, factor)
                self._factors.append(factor)
        else:
            extraction_sets = [
                PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
                for indices in local_indices
            ]
            submatrices = matrix.createSubMatrices(extraction_sets)
            for index_set in extraction_sets:
                index_set.destroy()
            for slot, (subdomain, indices, submatrix) in enumerate(
                zip(
                    self.local_subdomains,
                    local_indices,
                    submatrices,
                    strict=True,
                )
            ):
                if slot == 0:
                    self._report_first_submatrix(setup_observer, submatrix, True)
                factor = build_factor(subdomain, indices, submatrix)
                if slot == 0:
                    self._report_first_factor(setup_observer, factor)
                self._factors.append(factor)
        if not self._first_submatrix_reported:
            self._report_first_submatrix(setup_observer, None, False)
        if not self._first_factor_reported:
            self._report_first_factor(setup_observer, None)
        self._finalize_factor_inventory(len(normalized), progress, setup_observer)

        self._initialize_inner_ksp(action_operator)

    @classmethod
    def from_owner_local_plan(
        cls,
        condensed: Any,
        plan: OwnerLocalSlabPlan,
        *,
        ilu_levels: int,
        interpolation: str = "basic",
        precomputed_diagonal_shift: PETSc.Vec | None = None,
        two_step_action_operator: PETSc.Mat | None = None,
        progress: Callable[[int, int], None] | None = None,
        setup_observer: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> DistributedPhysicalSlabSmoother:
        """Build the fixed M2b factor-only smoother without a global matrix."""

        if int(ilu_levels) != 0:
            raise ValueError("owner-local M2b setup requires ILU(0)")
        smoother = cls.__new__(cls)
        smoother._initialize_owner_local_plan(
            condensed,
            plan,
            interpolation=interpolation,
            precomputed_diagonal_shift=precomputed_diagonal_shift,
            two_step_action_operator=two_step_action_operator,
            progress=progress,
            setup_observer=setup_observer,
        )
        return smoother

    def _initialize_owner_local_plan(
        self,
        condensed: Any,
        plan: OwnerLocalSlabPlan,
        *,
        interpolation: str,
        precomputed_diagonal_shift: PETSc.Vec | None,
        two_step_action_operator: PETSc.Mat | None,
        progress: Callable[[int, int], None] | None,
        setup_observer: Callable[[str, dict[str, Any]], None] | None,
    ) -> None:
        if int(plan.active_rows) != int(condensed.active_rows):
            raise ValueError("owner-local plan size does not match condensed system")
        self.comm = plan.comm
        self.rank = int(self.comm.rank)
        self.comm_size = int(self.comm.size)
        self.global_size = int(condensed.active_rows)
        self.ilu_levels = 0
        if interpolation not in {"basic", "partition"}:
            raise ValueError("interpolation must be 'basic' or 'partition'")
        self.interpolation = interpolation
        self.assembly_order = (
            "two_color" if two_step_action_operator is not None else "combined"
        )
        self.local_ksp_iterations = 1
        self.local_ksp_type = "gmres"
        self.smoother_iterations = 2 if two_step_action_operator is not None else 1
        self.smoother_ksp_type = "gmres"
        self.factor_only_storage = True
        self.local_solver_types = ("ilu",) * len(plan.slab_owners)
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self._destroyed = False
        self._inner_ksp = None
        self._inner_pc_context = None
        self._first_submatrix_reported = False
        self._first_factor_reported = False
        self._global_subdomain_count = len(plan.slab_owners)
        self.partition_weight_sum_error: float | None = None
        self.partition_weight_min: float | None = None
        self.partition_weight_max: float | None = None
        self.subdomain_local_diagonal_shift = True
        self.subdomain_owners = tuple(plan.slab_owners)
        self.local_subdomains = tuple(
            slab for slab, owner in enumerate(plan.slab_owners) if owner == self.rank
        )
        local_indices = [plan.owner_rows[slab] for slab in self.local_subdomains]
        template = condensed.create_active_vector()
        self._initialize_apply_state(local_indices, template)
        template.destroy()
        self._factors = []
        first_submatrix_payload = None
        first_factor_payload = None

        if precomputed_diagonal_shift is None:
            diagonal, _diagonal_audit = build_owner_local_slab_diagonal(condensed)
            diagonal_source = diagonal
        else:
            diagonal = None
            diagonal_source = precomputed_diagonal_shift
            if diagonal_source.getSize() != self.global_size:
                raise ValueError("precomputed diagonal shift size does not match plan")
        try:
            for slab, owner in enumerate(plan.slab_owners):
                slab_matrix, _slab_audit = assemble_owner_local_slab_matrix(
                    condensed, plan, slab
                )
                if precomputed_diagonal_shift is None:
                    slab_shift, _shift_audit = owner_local_slab_diagonal_shift(
                        diagonal_source,
                        plan,
                        slab,
                        _diagonal_audit["global_diagonal_max_abs"],
                    )
                else:
                    slab_shift, _shift_audit = extract_owner_local_slab_diagonal(
                        diagonal_source, plan, slab
                    )
                if self.rank == owner:
                    if setup_observer is not None and first_submatrix_payload is None:
                        first_submatrix_payload = {
                            "rank_local_has_first_submatrix": True,
                            "rank_local_first_submatrix_rows": int(
                                slab_matrix.getSize()[0]
                            ),
                            "rank_local_first_submatrix_cols": int(
                                slab_matrix.getSize()[1]
                            ),
                            "rank_local_first_submatrix_nnz": int(
                                slab_matrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"]
                            ),
                        }
                    factor = self._build_owned_factor(
                        slab,
                        plan.owner_rows[slab],
                        slab_matrix,
                        diagonal_shift=slab_shift,
                        multiplicity=None,
                        partition_weights=(
                            plan.partition_weights_by_slab[slab]
                            if self.interpolation == "partition"
                            else None
                        ),
                    )
                    if setup_observer is not None and first_factor_payload is None:
                        first_factor_payload = {
                            "rank_local_has_first_factor": True,
                            "rank_local_first_factor_subdomain": int(factor.subdomain),
                            "rank_local_first_factor_rows": int(factor.indices.size),
                            "rank_local_first_factor_matrix_nnz": int(
                                factor.matrix_nnz
                            ),
                            "rank_local_first_factor_nnz": int(factor.factor_nnz),
                        }
                    self._factors.append(factor)
        finally:
            if diagonal is not None:
                diagonal.destroy()
        if self.interpolation == "partition":
            local_weights = [
                plan.partition_weights_by_slab[slab] for slab in self.local_subdomains
            ]
            local_weight_values = (
                np.concatenate(local_weights) if local_weights else np.empty(0)
            )
            local_invalid_weights = False
            if local_weight_values.size:
                real_weights = np.real(local_weight_values)
                local_invalid_weights = bool(
                    not np.all(np.isfinite(real_weights))
                    or np.any(real_weights <= 0.0)
                    or np.any(real_weights > 1.0)
                )
            if self.comm.allreduce(local_invalid_weights, op=MPI.LOR):
                raise RuntimeError("partition weights are not finite in (0, 1]")
            weight_sums = condensed.create_active_vector()
            weight_sums.set(0.0)
            for slab in self.local_subdomains:
                weight_sums.setValues(
                    plan.owner_rows[slab],
                    plan.partition_weights_by_slab[slab],
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            weight_sums.assemble()
            local_weight_error = (
                np.asarray(weight_sums.getArray(readonly=True), dtype=PETSc.ScalarType)
                - 1.0
            )
            local_weight_error_max = (
                float(np.max(np.abs(local_weight_error)))
                if local_weight_error.size
                else 0.0
            )
            self.partition_weight_sum_error = float(
                self.comm.allreduce(local_weight_error_max, op=MPI.MAX)
            )
            weight_sums.destroy()
            local_min = (
                float(np.min(np.real(local_weight_values)))
                if local_weight_values.size
                else 1.0
            )
            local_max = (
                float(np.max(np.real(local_weight_values)))
                if local_weight_values.size
                else 0.0
            )
            self.partition_weight_min = float(
                self.comm.allreduce(local_min, op=MPI.MIN)
            )
            self.partition_weight_max = float(
                self.comm.allreduce(local_max, op=MPI.MAX)
            )
            if self.partition_weight_sum_error > 1.0e-12:
                raise RuntimeError("partition weights do not form a unity sum")
        self._report_first_submatrix(
            setup_observer,
            None,
            first_submatrix_payload is not None,
            cached_payload=first_submatrix_payload,
        )
        self._report_first_factor(
            setup_observer,
            None,
            cached_payload=first_factor_payload,
        )
        self._finalize_factor_inventory(len(plan.slab_owners), progress, setup_observer)
        self._initialize_inner_ksp(two_step_action_operator)

    def _solve_owned_factor(
        self,
        factor: _OwnedSubdomainFactor,
        gathered_source: np.ndarray,
    ) -> None:
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

    def _apply_once(
        self,
        source: PETSc.Vec,
        target: PETSc.Vec,
        *,
        excluded_subdomain: int | None = None,
        record_telemetry: bool = True,
    ) -> None:
        started = time.perf_counter() if record_telemetry else 0.0
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
            if factor.subdomain == excluded_subdomain:
                continue
            self._solve_owned_factor(factor, gathered_source)
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
        if record_telemetry:
            self.apply_count += 1
            self.apply_elapsed_s += time.perf_counter() - started

    def _diagnostic_one_level_apply(
        self,
        source: PETSc.Vec,
        target: PETSc.Vec,
        *,
        excluded_subdomain: int | None = None,
    ) -> None:
        """Apply one level for diagnostics without changing telemetry."""

        self._apply_once(
            source,
            target,
            excluded_subdomain=excluded_subdomain,
            record_telemetry=False,
        )

    def _diagnostic_owner_local_ilu(
        self,
        source: PETSc.Vec,
        subdomain: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return one owner-local shifted ILU RHS and unweighted correction."""

        self._gathered_source.set(0.0)
        self._scatter.scatter(
            source,
            self._gathered_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        owner = int(self.subdomain_owners[subdomain])
        if self.rank != owner:
            empty = np.empty(0, dtype=PETSc.ScalarType)
            return empty, empty.copy()
        factor = next(
            factor for factor in self._factors if factor.subdomain == subdomain
        )
        self._solve_owned_factor(
            factor,
            self._gathered_source.getArray(readonly=True),
        )
        rhs = np.asarray(
            factor.rhs.getArray(readonly=True), dtype=PETSc.ScalarType
        ).copy()
        correction = np.asarray(
            factor.solution.getArray(readonly=True), dtype=PETSc.ScalarType
        ).copy()
        return rhs, correction

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._inner_ksp is None:
            self._apply_once(source, target)
            return
        target.set(0.0)
        self._inner_ksp.solve(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        diagnostics = {
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
            "factor_fingerprints_semantics": (
                "shifted_local_matrix_numeric_only_not_exact_reuse_qualified"
            ),
            "unique_factor_classes": self.unique_factor_classes,
            "exact_duplicate_factor_count": self.exact_duplicate_factor_count,
            "numeric_local_matrix_unique_classes": (
                self.numeric_local_matrix_unique_classes
            ),
            "numeric_local_matrix_duplicate_count": (
                self.numeric_local_matrix_duplicate_count
            ),
            "factor_reuse_fingerprints": self.factor_reuse_fingerprints,
            "exact_reuse_necessary_prefix_groups": (
                self.exact_reuse_necessary_prefix_groups
            ),
            "exact_reuse_necessary_prefix_unique_classes": (
                self.exact_reuse_necessary_prefix_unique_classes
            ),
            "exact_reuse_candidate_count": self.exact_reuse_candidate_count,
            "exact_reuse_qualified_count": self.exact_reuse_qualified_count,
            "exact_reuse_qualification_status": self.exact_reuse_qualification_status,
            "exact_reuse_deferred_checks": self.exact_reuse_deferred_checks,
            "one_level_apply_count": self.apply_count,
            "one_level_mean_apply_s": self.apply_elapsed_s / max(self.apply_count, 1),
        }
        if self.interpolation == "partition":
            diagnostics.update(
                {
                    "partition_weight_sum_error": self.partition_weight_sum_error,
                    "partition_weight_min": self.partition_weight_min,
                    "partition_weight_max": self.partition_weight_max,
                }
            )
        return diagnostics

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
