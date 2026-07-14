"""Task030 H(curl) research infrastructure and failed candidate prototypes.

Only the active/master map, nonmatching transfer/cache, transfer validation,
and exact condensed Galerkin builder listed in ``__all__`` are validated
research-infrastructure surfaces. The Jacobi, p/h multilevel, shifted-matrix,
and all-mode Woodbury components remain negative research candidates. They
are intentionally absent from the ordinary ``src.solvers`` package API and
may only be imported explicitly by the Task030 research runner and tests.

This module does not provide a production p/h multigrid solver.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np
import scipy.linalg as sla
from mpi4py import MPI
from petsc4py import PETSc

from .condensed_dtn import gather_small_petsc_matrix


TINY = np.finfo(float).tiny


VALIDATED_INFRASTRUCTURE_API = (
    "ActiveDofMap",
    "NonmatchingTransfer",
    "CondensedGalerkinCoarse",
    "build_active_dof_map",
    "build_nonmatching_active_transfer",
    "save_nonmatching_transfer_cache",
    "load_nonmatching_transfer_cache",
    "validate_transfer_action_against_interpolation",
    "build_condensed_galerkin_coarse",
)

RESEARCH_ONLY_CANDIDATE_API = (
    "CanonicalScreenBaseline",
    "load_canonical_screen_baseline",
    "classify_screen_candidate",
    "DampedJacobiSmoother",
    "build_absorption_shifted_matrix",
    "GalerkinMultilevelPc",
    "ModalWoodburyPc",
)

__all__ = list(VALIDATED_INFRASTRUCTURE_API)


@dataclass(frozen=True)
class CanonicalScreenBaseline:
    reference_path: Path
    canonical_path: Path
    sha256: str
    iteration: int
    true_relative_residual: float
    peak_rss_gb: float
    full_true_relative_residual: float
    total_iterations: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_canonical_screen_baseline(
    reference_path: Path,
    *,
    repository_root: Path,
    iteration: int = 100,
) -> CanonicalScreenBaseline:
    """Load and certify the pinned Case031 screen baseline.

    The comparison residual is deliberately read from the canonical history.
    A copied scalar in a Task030 config is not accepted as evidence.
    """

    reference_path = reference_path.resolve()
    repository_root = repository_root.resolve()
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    relative = Path(str(reference["canonical_record"]))
    canonical_path = (repository_root / relative).resolve()
    try:
        canonical_path.relative_to(repository_root)
    except ValueError as exc:
        raise ValueError("canonical baseline must stay inside the repository") from exc
    expected_hash = str(reference["sha256"]).lower()
    actual_hash = _sha256_file(canonical_path)
    if actual_hash != expected_hash:
        raise RuntimeError(
            "canonical baseline SHA-256 mismatch: "
            f"expected={expected_hash}, actual={actual_hash}"
        )
    record = json.loads(canonical_path.read_text(encoding="utf-8"))
    matching = [
        row
        for row in record.get("history", [])
        if int(row.get("iteration", -1)) == iteration
    ]
    if len(matching) != 1:
        raise RuntimeError(
            f"canonical baseline needs exactly one history row at iteration={iteration}"
        )
    row = matching[0]
    residual = float(row["true_relative_residual"])
    peak = float(
        record.get(
            "peak_total_rss_including_rta_gb",
            record.get("final_peak_total_gb", row.get("monitor_peak_total_gb")),
        )
    )
    full_residual = float(record["full_augmented_true_residual"])
    if not all(
        np.isfinite(value) and value > 0.0 for value in (residual, peak, full_residual)
    ):
        raise RuntimeError("canonical baseline contains invalid positive metrics")
    return CanonicalScreenBaseline(
        reference_path=reference_path,
        canonical_path=canonical_path,
        sha256=actual_hash,
        iteration=int(iteration),
        true_relative_residual=residual,
        peak_rss_gb=peak,
        full_true_relative_residual=full_residual,
        total_iterations=int(record["iterations"]),
    )


def classify_screen_candidate(
    *,
    true_residual: float,
    peak_rss_gb: float,
    baseline: CanonicalScreenBaseline,
) -> dict[str, Any]:
    residual_ratio = float(true_residual) / baseline.true_relative_residual
    rss_ratio = float(peak_rss_gb) / baseline.peak_rss_gb
    strong = residual_ratio <= 0.5 or (residual_ratio <= 0.7 and rss_ratio <= 0.8)
    memory_positive = rss_ratio <= 0.7 and residual_ratio <= 1.1
    weak = residual_ratio <= 0.8 and rss_ratio <= 1.1
    negative = residual_ratio > 1.25 or (rss_ratio > 1.2 and residual_ratio > 0.5)
    if strong:
        classification = "strong_positive"
    elif memory_positive:
        classification = "memory_positive"
    elif weak:
        classification = "weak_positive"
    elif negative:
        classification = "negative"
    else:
        classification = "neutral"
    return {
        "classification": classification,
        "residual_ratio_to_baseline": residual_ratio,
        "rss_ratio_to_baseline": rss_ratio,
        "strong_positive": strong,
        "memory_positive": memory_positive,
        "weak_positive": weak,
        "negative": negative,
    }


@dataclass(frozen=True)
class ActiveDofMap:
    local_full_dofs: np.ndarray
    local_active_ids: np.ndarray
    active_to_full_global: np.ndarray
    active_to_owner: np.ndarray
    global_active_size: int
    local_active_size: int
    global_full_size: int
    local_full_size: int
    local_active_offset: int


def build_active_dof_map(
    function_space: Any,
    local_slave_dofs: np.ndarray,
) -> ActiveDofMap:
    """Compress owned MPC-independent DoFs into a contiguous PETSc map."""

    index_map = function_space.dofmap.index_map
    block_size = int(function_space.dofmap.index_map_bs)
    if block_size != 1:
        raise NotImplementedError(
            "Task030 active map currently requires scalar H(curl) dofmaps"
        )
    comm = function_space.mesh.comm
    local_full_size = int(index_map.size_local)
    global_full_size = int(index_map.size_global)
    slaves = np.asarray(local_slave_dofs, dtype=np.int64)
    owned_slaves = np.unique(slaves[(slaves >= 0) & (slaves < local_full_size)])
    active_mask = np.ones(local_full_size, dtype=bool)
    active_mask[owned_slaves] = False
    local_full_dofs = np.flatnonzero(active_mask).astype(PETSc.IntType)
    counts = np.asarray(comm.allgather(local_full_dofs.size), dtype=np.int64)
    offset = int(np.sum(counts[: comm.rank]))
    local_active_ids = np.arange(
        offset, offset + local_full_dofs.size, dtype=PETSc.IntType
    )
    full_start = int(index_map.local_range[0])
    local_full_global = local_full_dofs.astype(np.int64) + full_start
    packets = comm.allgather(
        (
            local_active_ids.astype(np.int64),
            local_full_global,
            np.full(local_full_dofs.size, comm.rank, dtype=np.int32),
        )
    )
    global_active_size = int(np.sum(counts))
    active_to_full_global = np.empty(global_active_size, dtype=np.int64)
    active_to_owner = np.empty(global_active_size, dtype=np.int32)
    for active_ids, full_globals, owners in packets:
        active_to_full_global[active_ids] = full_globals
        active_to_owner[active_ids] = owners
    if np.unique(active_to_full_global).size != global_active_size:
        raise RuntimeError("active DoF map contains duplicate full global DoFs")
    return ActiveDofMap(
        local_full_dofs=local_full_dofs,
        local_active_ids=local_active_ids,
        active_to_full_global=active_to_full_global,
        active_to_owner=active_to_owner,
        global_active_size=global_active_size,
        local_active_size=int(local_full_dofs.size),
        global_full_size=global_full_size,
        local_full_size=local_full_size,
        local_active_offset=offset,
    )


@dataclass
class NonmatchingTransfer:
    matrix: PETSc.Mat
    active_map: ActiveDofMap
    validation: dict[str, Any]
    owners: tuple[Any, ...]

    def destroy(self) -> None:
        self.matrix.destroy()
        self.owners = ()


def save_nonmatching_transfer_cache(
    transfer: NonmatchingTransfer,
    directory: Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a validated distributed transfer as one CSR file per rank."""

    matrix = transfer.matrix
    comm = matrix.getComm().tompi4py()
    directory = Path(directory)
    if comm.rank == 0:
        directory.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    local_rows, local_cols = matrix.getLocalSize()
    global_rows, global_cols = matrix.getSize()
    indptr, indices, values = matrix.getValuesCSR()
    np.savez_compressed(
        directory / f"transfer_rank_{comm.rank:04d}.npz",
        local_rows=np.asarray(local_rows, dtype=np.int64),
        local_cols=np.asarray(local_cols, dtype=np.int64),
        indptr=np.asarray(indptr, dtype=PETSc.IntType),
        indices=np.asarray(indices, dtype=PETSc.IntType),
        values=np.asarray(values, dtype=PETSc.ScalarType),
    )
    comm.barrier()
    if comm.rank == 0:
        manifest = {
            "format": "task030_distributed_petsc_aij_csr_v1",
            "mpi_size": comm.size,
            "global_rows": int(global_rows),
            "global_cols": int(global_cols),
            "validation": transfer.validation,
            "metadata": metadata or {},
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    comm.barrier()


def load_nonmatching_transfer_cache(
    directory: Path,
    *,
    coarse_space: Any,
    coarse_local_slave_dofs: np.ndarray,
    expected_fine_global_dofs: int,
) -> NonmatchingTransfer:
    """Load a transfer cache and fail closed on MPI/shape/active-map drift."""

    comm = coarse_space.mesh.comm
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if int(manifest["mpi_size"]) != comm.size:
        raise RuntimeError("transfer cache MPI size mismatch")
    active = build_active_dof_map(coarse_space, coarse_local_slave_dofs)
    if int(manifest["global_rows"]) != int(expected_fine_global_dofs):
        raise RuntimeError("transfer cache fine dimension mismatch")
    if int(manifest["global_cols"]) != active.global_active_size:
        raise RuntimeError("transfer cache active coarse dimension mismatch")
    with np.load(directory / f"transfer_rank_{comm.rank:04d}.npz") as payload:
        local_rows = int(payload["local_rows"])
        local_cols = int(payload["local_cols"])
        if local_cols != active.local_active_size:
            raise RuntimeError("transfer cache local active ownership mismatch")
        matrix = PETSc.Mat().createAIJ(
            size=(
                (local_rows, int(manifest["global_rows"])),
                (local_cols, int(manifest["global_cols"])),
            ),
            csr=(
                np.asarray(payload["indptr"], dtype=PETSc.IntType),
                np.asarray(payload["indices"], dtype=PETSc.IntType),
                np.asarray(payload["values"], dtype=PETSc.ScalarType),
            ),
            comm=comm,
        )
    matrix.assemble()
    validation = dict(manifest["validation"])
    validation["cache_status"] = "loaded"
    return NonmatchingTransfer(
        matrix=matrix,
        active_map=active,
        validation=validation,
        owners=(),
    )


def _identity_mpc_call(mpc: Any | None, name: str, function: Any) -> None:
    if mpc is not None:
        getattr(mpc, name)(function)


def build_nonmatching_active_transfer(
    *,
    fine_space: Any,
    coarse_space: Any,
    fine_local_slave_dofs: np.ndarray,
    coarse_local_slave_dofs: np.ndarray,
    fine_mpc: Any | None = None,
    coarse_mpc: Any | None = None,
    padding: float = 1.0e-10,
    relative_drop_tolerance: float = 1.0e-13,
    progress: Callable[[int, int], None] | None = None,
) -> NonmatchingTransfer:
    """Build an active-column H(curl) transfer by certified nonmatching interpolation.

    This setup is intentionally expensive but unambiguous. It is the reference
    implementation used to validate later batched/topological builders.
    """

    from dolfinx import fem

    communicator_relation = MPI.Comm.Compare(
        fine_space.mesh.comm, coarse_space.mesh.comm
    )
    if communicator_relation not in (MPI.IDENT, MPI.CONGRUENT):
        raise ValueError("fine and coarse spaces must use the same communicator")
    comm = fine_space.mesh.comm
    fine_map = fine_space.dofmap.index_map
    if int(fine_space.dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "Task030 transfer currently requires scalar H(curl) dofmaps"
        )
    fine_transfer_space = (
        fine_mpc.function_space if fine_mpc is not None else fine_space
    )
    coarse_transfer_space = (
        coarse_mpc.function_space if coarse_mpc is not None else coarse_space
    )
    active = build_active_dof_map(coarse_transfer_space, coarse_local_slave_dofs)
    fine_local = int(fine_map.size_local)
    fine_global = int(fine_map.size_global)
    matrix = PETSc.Mat().createAIJ(
        size=(
            (fine_local, fine_global),
            (active.local_active_size, active.global_active_size),
        ),
        nnz=32,
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    fine_function = fem.Function(fine_transfer_space)
    coarse_function = fem.Function(coarse_transfer_space)
    tdim = fine_transfer_space.mesh.topology.dim
    cell_map = fine_transfer_space.mesh.topology.index_map(tdim)
    cells = np.arange(cell_map.size_local + cell_map.num_ghosts, dtype=np.int32)
    interpolation_data = fem.create_interpolation_data(
        fine_transfer_space, coarse_transfer_space, cells, padding=padding
    )
    row_start = int(fine_map.local_range[0])
    fine_owned_slaves = np.unique(
        np.asarray(fine_local_slave_dofs, dtype=np.int64)[
            (np.asarray(fine_local_slave_dofs, dtype=np.int64) >= 0)
            & (np.asarray(fine_local_slave_dofs, dtype=np.int64) < fine_local)
        ]
    )
    started = time.perf_counter()
    column_norm_min = float("inf")
    column_norm_max = 0.0
    local_nnz = 0
    coarse_start = int(coarse_transfer_space.dofmap.index_map.local_range[0])
    for active_id, (full_global, owner) in enumerate(
        zip(active.active_to_full_global, active.active_to_owner, strict=True)
    ):
        coarse_function.x.array[:] = 0.0
        if comm.rank == int(owner):
            local_dof = int(full_global) - coarse_start
            if not 0 <= local_dof < active.local_full_size:
                raise RuntimeError("active DoF owner/full-global map is inconsistent")
            coarse_function.x.array[local_dof] = PETSc.ScalarType(1.0)
        coarse_function.x.scatter_forward()
        coarse_norm_before_backsub = float(coarse_function.x.petsc_vec.norm())
        _identity_mpc_call(coarse_mpc, "backsubstitution", coarse_function)
        coarse_function.x.scatter_forward()
        coarse_norm_after_backsub = float(coarse_function.x.petsc_vec.norm())
        fine_function.x.array[:] = 0.0
        fine_function.interpolate_nonmatching(
            coarse_function, cells, interpolation_data
        )
        fine_function.x.scatter_forward()
        fine_norm_before_homogenize = float(fine_function.x.petsc_vec.norm())
        _identity_mpc_call(fine_mpc, "homogenize", fine_function)
        fine_norm_after_homogenize = float(fine_function.x.petsc_vec.norm())
        owned_values = np.asarray(
            fine_function.x.array[:fine_local], dtype=PETSc.ScalarType
        )
        if fine_owned_slaves.size:
            owned_values = owned_values.copy()
            owned_values[fine_owned_slaves] = 0.0
        local_sq = float(np.vdot(owned_values, owned_values).real)
        norm = float(np.sqrt(comm.allreduce(local_sq, op=MPI.SUM)))
        if not np.isfinite(norm) or norm <= 1.0e-12:
            matrix.destroy()
            raise RuntimeError(
                f"nonmatching transfer column {active_id} is zero; "
                f"coarse_norm_before_backsub={coarse_norm_before_backsub:.6e}, "
                f"coarse_norm_after_backsub={coarse_norm_after_backsub:.6e}, "
                f"fine_norm_before_homogenize={fine_norm_before_homogenize:.6e}, "
                f"fine_norm_after_homogenize={fine_norm_after_homogenize:.6e}"
            )
        column_norm_min = min(column_norm_min, norm)
        column_norm_max = max(column_norm_max, norm)
        threshold = relative_drop_tolerance * norm
        positions = np.flatnonzero(np.abs(owned_values) > threshold)
        if positions.size:
            rows = positions.astype(PETSc.IntType) + row_start
            matrix.setValues(
                rows,
                np.asarray([active_id], dtype=PETSc.IntType),
                owned_values[positions].reshape(-1, 1),
            )
            local_nnz += int(positions.size)
        if progress is not None:
            progress(active_id + 1, active.global_active_size)
    matrix.assemble()
    build_s = time.perf_counter() - started

    rng = np.random.default_rng(20260713)
    coarse_test = matrix.createVecRight()
    fine_test = matrix.createVecLeft()
    fine_probe = matrix.createVecLeft()
    coarse_adjoint = matrix.createVecRight()
    c_start, c_end = coarse_test.getOwnershipRange()
    f_start, f_end = fine_probe.getOwnershipRange()
    coarse_test.getArray()[:] = rng.standard_normal(
        c_end - c_start
    ) + 1j * rng.standard_normal(c_end - c_start)
    fine_probe.getArray()[:] = rng.standard_normal(
        f_end - f_start
    ) + 1j * rng.standard_normal(f_end - f_start)
    matrix.mult(coarse_test, fine_test)
    matrix.multHermitian(fine_probe, coarse_adjoint)
    lhs = fine_probe.dot(fine_test)
    rhs = coarse_adjoint.dot(coarse_test)
    adjoint_error = float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), TINY))
    for vector in (coarse_test, fine_test, fine_probe, coarse_adjoint):
        vector.destroy()
    validation = {
        "kind": "active_column_nonmatching_hcurl_interpolation",
        "fine_global_dofs": fine_global,
        "coarse_full_global_dofs": active.global_full_size,
        "coarse_active_global_dofs": active.global_active_size,
        "coarse_removed_slave_dofs": active.global_full_size
        - active.global_active_size,
        "matrix_global_rows": int(matrix.getSize()[0]),
        "matrix_global_cols": int(matrix.getSize()[1]),
        "matrix_nnz": int(comm.allreduce(local_nnz, op=MPI.SUM)),
        "column_norm_min": float(comm.allreduce(column_norm_min, op=MPI.MIN)),
        "column_norm_max": float(comm.allreduce(column_norm_max, op=MPI.MAX)),
        "adjoint_identity_relative_error": adjoint_error,
        "build_s": build_s,
        "status": "passed" if adjoint_error <= 1.0e-12 else "failed",
    }
    if validation["status"] != "passed":
        matrix.destroy()
        raise RuntimeError(
            "nonmatching transfer failed Hermitian-adjoint identity: "
            f"error={adjoint_error:.6e}"
        )
    return NonmatchingTransfer(
        matrix=matrix,
        active_map=active,
        validation=validation,
        owners=(fine_function, coarse_function, interpolation_data),
    )


def validate_transfer_action_against_interpolation(
    transfer: NonmatchingTransfer,
    *,
    fine_space: Any,
    coarse_space: Any,
    fine_local_slave_dofs: np.ndarray,
    fine_mpc: Any | None = None,
    coarse_mpc: Any | None = None,
    padding: float = 1.0e-10,
) -> float:
    """Compare the assembled matrix with a fresh nonmatching interpolation."""

    from dolfinx import fem

    comm = fine_space.mesh.comm
    rng = np.random.default_rng(20260714 + comm.rank)
    fine_transfer_space = (
        fine_mpc.function_space if fine_mpc is not None else fine_space
    )
    coarse_transfer_space = (
        coarse_mpc.function_space if coarse_mpc is not None else coarse_space
    )
    coarse = fem.Function(coarse_transfer_space)
    coarse.x.array[:] = 0.0
    coarse.x.array[transfer.active_map.local_full_dofs] = rng.standard_normal(
        transfer.active_map.local_active_size
    ) + 1j * rng.standard_normal(transfer.active_map.local_active_size)
    coarse.x.scatter_forward()
    _identity_mpc_call(coarse_mpc, "backsubstitution", coarse)
    coarse.x.scatter_forward()
    fine_reference = fem.Function(fine_transfer_space)
    tdim = fine_transfer_space.mesh.topology.dim
    cell_map = fine_transfer_space.mesh.topology.index_map(tdim)
    cells = np.arange(cell_map.size_local + cell_map.num_ghosts, dtype=np.int32)
    data = fem.create_interpolation_data(
        fine_transfer_space, coarse_transfer_space, cells, padding=padding
    )
    fine_reference.interpolate_nonmatching(coarse, cells, data)
    fine_reference.x.scatter_forward()
    _identity_mpc_call(fine_mpc, "homogenize", fine_reference)
    active_vector = transfer.matrix.createVecRight()
    active_vector.getArray()[:] = coarse.x.array[transfer.active_map.local_full_dofs]
    actual = transfer.matrix.createVecLeft()
    transfer.matrix.mult(active_vector, actual)
    fine_local = fine_transfer_space.dofmap.index_map.size_local
    expected = np.asarray(
        fine_reference.x.array[:fine_local], dtype=PETSc.ScalarType
    ).copy()
    slaves = np.asarray(fine_local_slave_dofs, dtype=np.int64)
    slaves = slaves[(slaves >= 0) & (slaves < fine_local)]
    expected[slaves] = 0.0
    delta = actual.getArray(readonly=True) - expected
    numerator = np.sqrt(comm.allreduce(float(np.vdot(delta, delta).real), op=MPI.SUM))
    denominator = np.sqrt(
        comm.allreduce(float(np.vdot(expected, expected).real), op=MPI.SUM)
    )
    error = float(numerator / max(denominator, TINY))
    actual.destroy()
    active_vector.destroy()
    return error


class DampedJacobiSmoother:
    """Fixed-step complex Jacobi/Richardson smoother with O(n) storage."""

    def __init__(
        self,
        matrix: PETSc.Mat,
        *,
        steps: int,
        omega: float,
    ) -> None:
        if steps < 1:
            raise ValueError("Jacobi steps must be positive")
        if not np.isfinite(omega) or omega <= 0.0:
            raise ValueError("Jacobi omega must be finite and positive")
        self.matrix = matrix
        self.steps = int(steps)
        self.omega = float(omega)
        diagonal = matrix.createVecLeft()
        matrix.getDiagonal(diagonal)
        values = diagonal.getArray(readonly=True)
        scale = float(
            matrix.getComm()
            .tompi4py()
            .allreduce(float(np.max(np.abs(values), initial=0.0)), op=MPI.MAX)
        )
        if np.any(np.abs(values) <= 1.0e-14 * max(scale, TINY)):
            diagonal.destroy()
            raise RuntimeError("Jacobi smoother found a numerically zero diagonal")
        self.inverse_diagonal = diagonal.copy()
        self.inverse_diagonal.getArray()[:] = 1.0 / values
        diagonal.destroy()
        self.residual = matrix.createVecLeft()
        self.correction = matrix.createVecRight()
        self.apply_count = 0
        self.apply_elapsed_s = 0.0

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        started = time.perf_counter()
        target.set(0.0)
        for _ in range(self.steps):
            self.matrix.mult(target, self.residual)
            self.residual.aypx(PETSc.ScalarType(-1.0), source)
            self.correction.pointwiseMult(self.inverse_diagonal, self.residual)
            target.axpy(PETSc.ScalarType(self.omega), self.correction)
        self.apply_count += 1
        self.apply_elapsed_s += time.perf_counter() - started

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "kind": "damped_complex_jacobi",
            "steps": self.steps,
            "omega": self.omega,
            "apply_count": self.apply_count,
            "mean_apply_s": self.apply_elapsed_s / max(self.apply_count, 1),
            "storage_bytes": int(
                3
                * self.inverse_diagonal.getLocalSize()
                * np.dtype(PETSc.ScalarType).itemsize
            ),
        }

    def destroy(self) -> None:
        self.correction.destroy()
        self.residual.destroy()
        self.inverse_diagonal.destroy()


def build_absorption_shifted_matrix(
    matrix: PETSc.Mat, absorption_shift: float
) -> tuple[PETSc.Mat, float]:
    """Return F with the reviewed diagonal-magnitude complex absorption shift."""

    diagonal = matrix.createVecLeft()
    matrix.getDiagonal(diagonal)
    absolute = np.abs(diagonal.getArray(readonly=True))
    comm = matrix.getComm().tompi4py()
    scale = float(comm.allreduce(float(absolute.max(initial=0.0)), op=MPI.MAX))
    shifted_diagonal = diagonal.copy()
    shifted_diagonal.getArray()[:] += (
        -1j * float(absorption_shift) * np.maximum(absolute, 1.0e-12 * scale)
    )
    shifted = matrix.copy()
    shifted.setDiagonal(shifted_diagonal)
    shifted.assemble()
    shifted_diagonal.destroy()
    diagonal.destroy()
    return shifted, scale


@dataclass
class CondensedGalerkinCoarse:
    matrix: PETSc.Mat
    diagnostics: dict[str, Any]
    owned_matrices: tuple[PETSc.Mat, ...]

    def destroy(self) -> None:
        self.matrix.destroy()
        for matrix in self.owned_matrices:
            matrix.destroy()
        self.owned_matrices = ()


def build_condensed_galerkin_coarse(
    *,
    F: PETSc.Mat,
    C: PETSc.Mat,
    D: PETSc.Mat,
    H: PETSc.Mat,
    transfer: PETSc.Mat,
) -> CondensedGalerkinCoarse:
    """Build P^H(F-C H^-1 D)P with explicit complex-Hermitian restriction.

    The reviewed Stage4 auxiliary block has H=I. We assert that contract
    instead of silently replacing a general H inverse.
    """

    started = time.perf_counter()
    h_dense = gather_small_petsc_matrix(H)
    if not np.allclose(h_dense, np.eye(H.getSize()[0]), rtol=0.0, atol=1.0e-13):
        raise NotImplementedError(
            "Task030 Galerkin builder currently requires verified H=I"
        )
    hermitian = PETSc.Mat().createHermitianTranspose(transfer)
    f_times_p = F.matMult(transfer)
    coarse = hermitian.matMult(f_times_p)
    ph_c = hermitian.matMult(C)
    d_p = D.matMult(transfer)
    port = ph_c.matMult(d_p)
    coarse.axpy(
        PETSc.ScalarType(-1.0),
        port,
        structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
    )
    coarse.assemble()
    info = coarse.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    diagnostics = {
        "kind": "exact_condensed_galerkin_P_H_A_P",
        "rows": int(coarse.getSize()[0]),
        "cols": int(coarse.getSize()[1]),
        "nnz": int(info.get("nz_used", 0.0)),
        "setup_s": time.perf_counter() - started,
        "uses_hermitian_restriction": True,
        "includes_all_modal_dofs": int(H.getSize()[0]),
    }
    return CondensedGalerkinCoarse(
        matrix=coarse,
        diagnostics=diagnostics,
        owned_matrices=(hermitian, f_times_p, ph_c, d_p, port),
    )


class GalerkinMultilevelPc:
    """Multiplicative fine smoothing plus exact coarse correction."""

    def __init__(
        self,
        *,
        fine_operator: PETSc.Mat,
        transfer: PETSc.Mat,
        coarse_ksp: PETSc.KSP,
        smoother: Any,
        post_smooth: bool,
        coarse_damping: float = 1.0,
    ) -> None:
        self.fine_operator = fine_operator
        self.transfer = transfer
        self.coarse_ksp = coarse_ksp
        self.smoother = smoother
        self.post_smooth = bool(post_smooth)
        self.coarse_damping = float(coarse_damping)
        self.residual = fine_operator.createVecLeft()
        self.coarse_rhs = transfer.createVecRight()
        self.coarse_solution = transfer.createVecRight()
        self.prolonged = transfer.createVecLeft()
        self.post_correction = fine_operator.createVecRight()
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self.smoother_elapsed_s = 0.0
        self.coarse_elapsed_s = 0.0
        self.transfer_elapsed_s = 0.0

    def _update_residual(self, source: PETSc.Vec, approximation: PETSc.Vec) -> None:
        self.fine_operator.mult(approximation, self.residual)
        self.residual.aypx(PETSc.ScalarType(-1.0), source)

    def solve(self, source: PETSc.Vec, approximation: PETSc.Vec) -> None:
        self.apply(None, source, approximation)

    def apply(
        self, _pc: PETSc.PC | None, source: PETSc.Vec, approximation: PETSc.Vec
    ) -> None:
        started = time.perf_counter()
        smoother_started = time.perf_counter()
        self.smoother.solve(source, approximation)
        self.smoother_elapsed_s += time.perf_counter() - smoother_started
        self._update_residual(source, approximation)
        transfer_started = time.perf_counter()
        self.transfer.multHermitian(self.residual, self.coarse_rhs)
        self.transfer_elapsed_s += time.perf_counter() - transfer_started
        self.coarse_solution.set(0.0)
        coarse_started = time.perf_counter()
        self.coarse_ksp.solve(self.coarse_rhs, self.coarse_solution)
        self.coarse_elapsed_s += time.perf_counter() - coarse_started
        transfer_started = time.perf_counter()
        self.transfer.mult(self.coarse_solution, self.prolonged)
        self.transfer_elapsed_s += time.perf_counter() - transfer_started
        approximation.axpy(PETSc.ScalarType(self.coarse_damping), self.prolonged)
        if self.post_smooth:
            self._update_residual(source, approximation)
            self.post_correction.set(0.0)
            smoother_started = time.perf_counter()
            self.smoother.solve(self.residual, self.post_correction)
            self.smoother_elapsed_s += time.perf_counter() - smoother_started
            approximation.axpy(PETSc.ScalarType(1.0), self.post_correction)
        self.apply_count += 1
        self.apply_elapsed_s += time.perf_counter() - started

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "kind": "multiplicative_galerkin_multilevel",
            "post_smooth": self.post_smooth,
            "coarse_damping": self.coarse_damping,
            "apply_count": self.apply_count,
            "mean_apply_s": self.apply_elapsed_s / max(self.apply_count, 1),
            "smoother_elapsed_s": self.smoother_elapsed_s,
            "coarse_elapsed_s": self.coarse_elapsed_s,
            "transfer_elapsed_s": self.transfer_elapsed_s,
        }

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.post_correction.destroy()
        self.prolonged.destroy()
        self.coarse_solution.destroy()
        self.coarse_rhs.destroy()
        self.residual.destroy()


def _apply_solver_action(solver: Any, source: Any, target: Any) -> None:
    """Apply either a solve-style object or a PETSc Python-PC context."""

    solve = getattr(solver, "solve", None)
    if callable(solve):
        solve(source, target)
        return
    apply = getattr(solver, "apply", None)
    if callable(apply):
        apply(None, source, target)
        return
    raise TypeError(
        "base solver must provide solve(source, target) or apply(pc, source, target)"
    )


class ModalWoodburyPc:
    """All-mode Woodbury correction around a fixed linear FE inverse action."""

    def __init__(
        self,
        *,
        base_solver: Any,
        C: PETSc.Mat,
        D: PETSc.Mat,
        H: PETSc.Mat,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        self.base_solver = base_solver
        self.C = C
        self.D = D
        self.comm = C.getComm().tompi4py()
        self.n_aux = int(H.getSize()[0])
        response = C.createVecLeft()
        column = C.createVecLeft()
        modal = D.createVecLeft()
        local_rows = response.getLocalSize()
        self.response_local = np.empty((local_rows, self.n_aux), dtype=PETSc.ScalarType)
        h_dense = gather_small_petsc_matrix(H)
        d_response = np.empty((self.n_aux, self.n_aux), dtype=np.complex128)
        setup_started = time.perf_counter()
        for j in range(self.n_aux):
            C.getColumnVector(j, column)
            response.set(0.0)
            _apply_solver_action(base_solver, column, response)
            self.response_local[:, j] = response.getArray(readonly=True)
            D.mult(response, modal)
            d_response[:, j] = self._gather_modal(modal)
            if progress is not None:
                progress(j + 1, self.n_aux)
        self.small = h_dense - d_response
        singular_values = np.linalg.svd(self.small, compute_uv=False)
        self.small_condition = float(
            singular_values[0] / max(singular_values[-1], TINY)
        )
        self.small_lu = sla.lu_factor(self.small)
        self.setup_s = time.perf_counter() - setup_started
        modal.destroy()
        column.destroy()
        response.destroy()
        self.modal_rhs = D.createVecLeft()
        self.apply_count = 0
        self.apply_elapsed_s = 0.0
        self._destroyed = False

    def _gather_modal(self, vector: PETSc.Vec) -> np.ndarray:
        start, end = vector.getOwnershipRange()
        packet = (
            int(start),
            int(end),
            np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy(),
        )
        values = np.empty(vector.getSize(), dtype=np.complex128)
        for packet_start, packet_end, local in self.comm.allgather(packet):
            values[packet_start:packet_end] = local
        return values

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply(None, source, target)

    def apply(self, _pc: PETSc.PC | None, source: PETSc.Vec, target: PETSc.Vec) -> None:
        started = time.perf_counter()
        _apply_solver_action(self.base_solver, source, target)
        self.D.mult(target, self.modal_rhs)
        coefficients = sla.lu_solve(self.small_lu, self._gather_modal(self.modal_rhs))
        target.getArray()[:] += self.response_local @ coefficients
        self.apply_count += 1
        self.apply_elapsed_s += time.perf_counter() - started

    @property
    def diagnostics(self) -> dict[str, Any]:
        local_bytes = self.response_local.nbytes
        return {
            "kind": "all_mode_woodbury",
            "n_aux": self.n_aux,
            "small_condition": self.small_condition,
            "setup_s": self.setup_s,
            "response_storage_bytes": int(self.comm.allreduce(local_bytes, op=MPI.SUM)),
            "apply_count": self.apply_count,
            "mean_apply_s": self.apply_elapsed_s / max(self.apply_count, 1),
        }

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        self.modal_rhs.destroy()
        self.response_local = np.empty((0, 0), dtype=PETSc.ScalarType)
        self._destroyed = True
