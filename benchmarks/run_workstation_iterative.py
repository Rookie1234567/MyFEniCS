from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import platform
import resource
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from dolfinx import fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.postprocessing.rta_3d import compute_volume_absorption_3d
from src.solvers.condensed_dtn import (
    condensed_rhs,
    create_matrix_free_condensed_operator,
    extract_petsc_condensed_blocks,
    matrix_storage_bytes,
    recover_petsc_auxiliary,
    relative_action_error,
)
from src.solvers.dtn_port_3d import (
    _assign_fe_solution_from_augmented,
    _incident_projection_onto_top_mode,
    _port_power_metrics,
)
from src.solvers.physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    SparseGalerkinTwoLevelPc,
    certify_fixed_linear_preconditioner,
    compress_petsc_vector,
    gather_global_subdomain_indices,
)
from src.solvers.mpc_form_action import create_mpc_form_operator
from src.solvers.local_slab_solver import IluLocalSlabSolver
from src.solvers.neural_local_pc import (
    FrozenNumpyMlp,
    IluNeuralCorrectionSlabSolver,
    NeuralLocalSlabSolver,
)
from src.solvers.batched_reduced_smoother import (
    FrozenLinearReducedMap,
    IluLinearReducedCorrectionSlabSolver,
)
from src.solvers.solve_vector_maxwell import _json_default
from src.solvers.stage4_runtime import (
    RuntimeStage4System,
    assemble_target_stage4_system,
    stage4_physical_model,
)
from benchmarks.neural_pc.petsc_capture import LocalSlabCapture


TINY = np.finfo(float).tiny
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPOSITORY_ROOT / "benchmarks" / "configs" / "workstation_p2.json"
QUALIFIED_H_NM = (5.0, 3.0, 2.0)


def _git_output(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPOSITORY_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _runtime_metadata(command: str) -> dict[str, Any]:
    dirty_override = os.environ.get("BENCHMARK_GIT_DIRTY")
    verified_clean_sha = os.environ.get("BENCHMARK_VERIFIED_CLEAN_SHA")
    commit_sha = os.environ.get("BENCHMARK_COMMIT_SHA") or _git_output(
        "rev-parse", "HEAD"
    )
    branch = os.environ.get("BENCHMARK_BRANCH") or _git_output(
        "branch", "--show-current"
    )
    if commit_sha is None or branch is None:
        raise RuntimeError("cannot verify benchmark source identity and cleanliness")
    if verified_clean_sha is not None:
        verified_clean_sha = verified_clean_sha.strip().lower()
        if len(verified_clean_sha) != 40 or any(
            character not in "0123456789abcdef" for character in verified_clean_sha
        ):
            raise RuntimeError("clean-source attestation must be a full Git SHA")
        if commit_sha.lower() != verified_clean_sha:
            raise RuntimeError(
                "clean-source attestation does not match mounted HEAD: "
                f"expected {verified_clean_sha}, mounted {commit_sha}"
            )
        full_dirty = False
        tracked_source_dirty = False
        tracked_source_verification = "host_git_clean_attestation"
    else:
        full_status = _git_output("status", "--short")
        tracked_status = _git_output("status", "--short", "--untracked-files=no")
        if full_status is None or tracked_status is None:
            raise RuntimeError(
                "cannot verify benchmark source identity and cleanliness"
            )
        full_dirty = bool(full_status)
        tracked_source_dirty = bool(tracked_status)
        tracked_source_verification = "git_status_untracked_files_no"
    return {
        "commit_sha": commit_sha,
        "branch": branch,
        "git_dirty": (
            dirty_override.lower() in {"1", "true", "yes"}
            if dirty_override is not None
            else full_dirty
        ),
        "tracked_source_dirty": tracked_source_dirty,
        "tracked_source_verification": tracked_source_verification,
        "verified_clean_sha": verified_clean_sha,
        "command": command,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "container_image": os.environ.get(
            "BENCHMARK_CONTAINER_IMAGE",
            os.environ.get("TASK031_CONTAINER_IMAGE", "unknown"),
        ),
        "container_digest": os.environ.get(
            "BENCHMARK_CONTAINER_DIGEST",
            os.environ.get("TASK031_IMAGE_DIGEST", "unknown"),
        ),
        "host_environment_id": os.environ.get("BENCHMARK_HOST_ID", platform.node()),
        "provenance": "clean_rerun",
        "kernel": platform.release(),
        "python": platform.python_version(),
        "numpy": np.__version__,
    }


def _qualification_deviations(args: argparse.Namespace, mpi_size: int) -> list[str]:
    expected = {
        "coarse_slabs": 24,
        "num_slabs": 16,
        "overlap_layers": 0.25,
        "absorption_shift": 0.1,
        "ilu_levels": 1,
        "restart": 100,
        "ksp_type": "fgmres",
        "smoother_ksp_type": "gmres",
        "selective_diagonal_boundary_slabs": 0,
        "max_it": 3000,
        "rtol": 1.0e-6,
    }
    deviations = [
        f"{name}={getattr(args, name)!r}, expected {value!r}"
        for name, value in expected.items()
        if getattr(args, name) != value
    ]
    if not any(np.isclose(args.h_nm, value) for value in QUALIFIED_H_NM):
        deviations.append(f"h_nm={args.h_nm!r}, expected one of {QUALIFIED_H_NM!r}")
    if args.theta_deg != 80.0:
        deviations.append(f"theta_deg={args.theta_deg!r}, expected 80.0")
    if args.lambda_nm != 13.5:
        deviations.append(f"lambda_nm={args.lambda_nm!r}, expected 13.5")
    if mpi_size != 4:
        deviations.append(f"mpi_size={mpi_size!r}, expected 4")
    if args.post_smooth:
        deviations.append("post_smooth=True, expected False")
    if args.subdomain_local_shift:
        deviations.append("subdomain_local_shift=True, expected False")
    if args.factor_only_storage:
        deviations.append("factor_only_storage=True, expected False")
    if args.certify_pc:
        deviations.append("certify_pc=True, expected False")
    if args.compact_lifecycle:
        deviations.append("compact_lifecycle=True, expected False")
    if args.matrix_free_fine:
        deviations.append("matrix_free_fine=True, expected False")
    if args.neural_capture_dir:
        deviations.append("neural_capture_dir is enabled for research data export")
    if args.neural_checkpoint_root:
        deviations.append(
            f"neural local backend {args.neural_lane!r} is enabled for research"
        )
    if args.linear_reduced_checkpoint_root:
        deviations.append(
            f"linear reduced backend {args.linear_reduced_mode!r} is enabled for research"
        )
    return deviations


def _write_json(path: Path, payload: Any) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: Any) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
        stream.write("\n")


def _rss_mb(*, peak: bool) -> float:
    if not peak:
        status = Path("/proc/self/status")
        if status.exists():
            for line in status.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _memory_fields(prefix: str) -> dict[str, float]:
    comm = MPI.COMM_WORLD
    current = float(comm.allreduce(_rss_mb(peak=False), op=MPI.SUM)) / 1024.0
    peak = float(comm.allreduce(_rss_mb(peak=True), op=MPI.SUM)) / 1024.0
    return {
        f"{prefix}_current_total_gb": current,
        f"{prefix}_peak_total_gb": peak,
    }


def _vector_storage_bytes(vector: PETSc.Vec) -> int:
    return int(vector.getSize()) * np.dtype(PETSc.ScalarType).itemsize


def _object_ledger(
    *,
    system: RuntimeStage4System,
    blocks=None,
    rhs: PETSc.Vec | None = None,
    operator: PETSc.Mat | None = None,
    coarse_context: SparseGalerkinTwoLevelPc | None = None,
    smoother: DistributedPhysicalSlabSmoother | None = None,
    ksp_type: str | None = None,
    restart: int | None = None,
    solution_vectors: int = 0,
    augmented_buffer_reused: bool = False,
) -> dict[str, Any]:
    """Record live solver objects and transparent storage estimates.

    PETSc matrix ``memory`` is preferred when available. Vector and Krylov
    entries are mathematical payload estimates, not allocator measurements;
    simultaneous RSS/cgroup sampling remains the peak-memory authority.
    """

    objects: list[dict[str, Any]] = []

    def add_matrix(name: str, matrix: PETSc.Mat) -> None:
        objects.append(
            {
                "name": name,
                "kind": "matrix",
                "shape": list(matrix.getSize()),
                "estimated_bytes": int(matrix_storage_bytes(matrix)),
            }
        )

    def add_vector(name: str, vector: PETSc.Vec) -> None:
        objects.append(
            {
                "name": name,
                "kind": "vector",
                "global_size": int(vector.getSize()),
                "estimated_bytes": _vector_storage_bytes(vector),
            }
        )

    if blocks is not None:
        for name in ("F", "C", "D", "H"):
            matrix = getattr(blocks, name)
            if matrix is not None:
                add_matrix(name, matrix)
        add_vector("b_fe", blocks.b_fe)
        add_vector("b_aux", blocks.b_aux)
    if rhs is not None:
        add_vector("condensed_rhs", rhs)
    if operator is not None:
        objects.append(
            {
                "name": "condensed_shell",
                "kind": "matrix_shell",
                "shape": list(operator.getSize()),
                "estimated_bytes": 0,
            }
        )
    if coarse_context is not None:
        objects.append(
            {
                "name": "sparse_coarse_basis_and_work",
                "kind": "host_sparse",
                "estimated_bytes": int(coarse_context.basis_storage_bytes),
            }
        )
    if smoother is not None:
        diagnostics = smoother.diagnostics
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        index_bytes = np.dtype(PETSc.IntType).itemsize
        factor_bytes = int(
            diagnostics["global_stored_factor_nnz"] * (scalar_bytes + index_bytes)
            + diagnostics["global_factor_rows"] * index_bytes
        )
        objects.append(
            {
                "name": "owned_slab_factors",
                "kind": "local_factors",
                "factor_nnz": diagnostics["global_stored_factor_nnz"],
                "estimated_bytes": factor_bytes,
            }
        )
    if solution_vectors:
        objects.append(
            {
                "name": "explicit_solution_work_vectors",
                "kind": "vector_group",
                "count": int(solution_vectors),
                "global_size_each": int(system.n_fe),
                "estimated_bytes": int(solution_vectors)
                * int(system.n_fe)
                * np.dtype(PETSc.ScalarType).itemsize,
            }
        )
    krylov_vectors = None
    if ksp_type in {"gmres", "fgmres"} and restart is not None:
        # PETSc work vectors include the Arnoldi basis. FGMRES additionally
        # retains a preconditioned basis; this is a payload model, not RSS.
        krylov_vectors = int(restart) + 2
        if ksp_type == "fgmres":
            krylov_vectors += int(restart) + 1
        objects.append(
            {
                "name": "outer_krylov_payload_model",
                "kind": "vector_group_estimate",
                "ksp_type": ksp_type,
                "restart": int(restart),
                "count": krylov_vectors,
                "global_size_each": int(system.n_fe),
                "estimated_bytes": krylov_vectors
                * int(system.n_fe)
                * np.dtype(PETSc.ScalarType).itemsize,
            }
        )
    total = sum(int(item["estimated_bytes"]) for item in objects)
    return {
        "objects": objects,
        "estimated_live_payload_bytes": total,
        "estimated_live_payload_gib": total / 1024.0**3,
        "krylov_vector_count_model": krylov_vectors,
        "augmented_buffer_reused": bool(augmented_buffer_reused),
        "semantics": (
            "payload ledger only; external simultaneous worker RSS and cgroup "
            "current/peak are authoritative for Task31 memory qualification"
        ),
    }


def _linear_residual(matrix: PETSc.Mat, rhs: PETSc.Vec, solution: PETSc.Vec) -> float:
    residual = rhs.duplicate()
    matrix.mult(solution, residual)
    residual.axpy(PETSc.ScalarType(-1.0), rhs)
    value = float(residual.norm()) / max(float(rhs.norm()), TINY)
    residual.destroy()
    return value


def _complete_physical_slabs(
    system: RuntimeStage4System,
    *,
    num_slabs: int,
    overlap_layers: float,
) -> tuple[np.ndarray, ...]:
    msh = system.mesh_data.mesh
    tdim = msh.topology.dim
    cells = np.arange(msh.topology.index_map(tdim).size_local, dtype=np.int32)
    midpoints = mesh.compute_midpoints(msh, tdim, cells)
    z_min = float(system.cfg.domain_z_min)
    z_max = float(system.cfg.domain_z_max)
    edges = np.linspace(z_min, z_max, num_slabs + 1)
    width = (z_max - z_min) / num_slabs
    index_map = system.V.dofmap.index_map
    local_pieces: list[np.ndarray] = []
    for slab in range(num_slabs):
        low = edges[slab] - overlap_layers * width
        high = edges[slab + 1] + overlap_layers * width
        selected = cells[(midpoints[:, 2] >= low) & (midpoints[:, 2] <= high)]
        if selected.size:
            local_dofs = np.unique(
                np.concatenate(
                    [system.V.dofmap.cell_dofs(int(cell)) for cell in selected]
                )
            )
            global_dofs = index_map.local_to_global(local_dofs).astype(
                PETSc.IntType, copy=False
            )
        else:
            global_dofs = np.empty(0, dtype=PETSc.IntType)
        local_pieces.append(global_dofs)
    return gather_global_subdomain_indices(local_pieces)


def _fixed_floquet_hat_basis(
    system: RuntimeStage4System,
    matrix: PETSc.Mat,
    *,
    coarse_slabs: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[Any]:
    centers = np.linspace(
        float(system.cfg.domain_z_min),
        float(system.cfg.domain_z_max),
        coarse_slabs + 1,
    )
    spacing = float(centers[1] - centers[0])
    total = len(centers) * 3
    candidates: list[PETSc.Vec] = []
    field = fem.Function(system.V)
    for center in centers:
        for component in range(3):

            def value(x, center=center, component=component):
                envelope = np.maximum(1.0 - np.abs(x[2] - center) / spacing, 0.0)
                phase = np.exp(
                    1j * (complex(system.cfg.kx) * x[0] + complex(system.cfg.ky) * x[1])
                )
                values = np.zeros((3, x.shape[1]), dtype=PETSc.ScalarType)
                values[component, :] = envelope * phase
                return values

            field.interpolate(value)
            system.floquet_data.mpc.homogenize(field)
            vector = matrix.createVecRight()
            vector.getArray()[:] = field.x.petsc_vec.getArray(readonly=True)[
                : vector.getLocalSize()
            ]
            for accepted in candidates:
                vector.axpy(-np.conjugate(accepted.dot(vector)), accepted)
            norm = float(vector.norm())
            if norm <= 1e-10:
                vector.destroy()
                raise RuntimeError("fixed Floquet coarse vector became singular")
            vector.scale(1.0 / norm)
            candidates.append(vector)
            if progress is not None:
                progress(len(candidates), total)
    sparse = [compress_petsc_vector(vector) for vector in candidates]
    for vector in candidates:
        vector.destroy()
    return sparse


def _absorption_diagonal_shift(
    matrix: PETSc.Mat, absorption_shift: float
) -> tuple[PETSc.Vec, float]:
    diagonal = matrix.createVecLeft()
    matrix.getDiagonal(diagonal)
    absolute = np.abs(diagonal.getArray(readonly=True))
    scale = float(MPI.COMM_WORLD.allreduce(float(absolute.max(initial=0)), op=MPI.MAX))
    difference = diagonal.duplicate()
    difference.getArray()[:] = (
        -1j * absorption_shift * np.maximum(absolute, 1e-12 * scale)
    )
    diagonal.destroy()
    return difference, scale


def _shifted_matrix(matrix: PETSc.Mat, difference: PETSc.Vec) -> PETSc.Mat:
    shifted = matrix.copy()
    shifted_diagonal = shifted.createVecLeft()
    shifted.getDiagonal(shifted_diagonal)
    shifted_diagonal.axpy(PETSc.ScalarType(1.0), difference)
    shifted.setDiagonal(shifted_diagonal)
    shifted.assemble()
    shifted_diagonal.destroy()
    return shifted


class _DiagonalShiftContext:
    def __init__(self, matrix: PETSc.Mat, diagonal_shift: PETSc.Vec) -> None:
        self.matrix = matrix
        self.diagonal_shift = diagonal_shift
        self.destroyed = False

    def mult(self, _mat: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.matrix.mult(source, target)
        target.getArray()[:] += self.diagonal_shift.getArray(
            readonly=True
        ) * source.getArray(readonly=True)

    def destroy(self, _mat: PETSc.Mat | None = None) -> None:
        if not self.destroyed:
            self.diagonal_shift.destroy()
            self.destroyed = True


def _shifted_action(matrix: PETSc.Mat, difference: PETSc.Vec) -> PETSc.Mat:
    action = PETSc.Mat().createPython(
        matrix.getSizes(),
        context=_DiagonalShiftContext(matrix, difference),
        comm=matrix.getComm(),
    )
    action.setUp()
    return action


def _combined_augmented_vector(
    system: RuntimeStage4System,
    u_fe: PETSc.Vec,
    u_aux: PETSc.Vec,
    *,
    target: PETSc.Vec | None = None,
) -> PETSc.Vec:
    result = system.b_petsc.duplicate() if target is None else target
    if result.getSize() != system.n_fe + system.n_aux:
        raise ValueError("augmented target has the wrong global size")
    result.set(0.0)
    row_start, row_end = result.getOwnershipRange()
    fe_end = min(row_end, system.n_fe)
    if fe_end > row_start:
        indices = np.arange(row_start, fe_end, dtype=PETSc.IntType)
        result.setValues(indices, u_fe.getValues(indices))
    aux_start = max(row_start, system.n_fe)
    if row_end > aux_start:
        indices = np.arange(aux_start, row_end, dtype=PETSc.IntType)
        result.setValues(indices, u_aux.getValues(indices - system.n_fe))
    result.assemble()
    return result


def _full_augmented_residual(
    blocks,
    u_fe: PETSc.Vec,
    u_aux: PETSc.Vec,
    *,
    fine_operator: PETSc.Mat | None = None,
) -> float:
    fine_operator = blocks.require_f() if fine_operator is None else fine_operator
    fe_residual = fine_operator.createVecLeft()
    fe_work = blocks.C.createVecLeft()
    aux_residual = blocks.D.createVecLeft()
    aux_work = blocks.H.createVecLeft()
    fine_operator.mult(u_fe, fe_residual)
    blocks.C.mult(u_aux, fe_work)
    fe_residual.axpy(1.0, fe_work)
    fe_residual.axpy(-1.0, blocks.b_fe)
    blocks.D.mult(u_fe, aux_residual)
    blocks.H.mult(u_aux, aux_work)
    aux_residual.axpy(1.0, aux_work)
    aux_residual.axpy(-1.0, blocks.b_aux)
    numerator = np.hypot(float(fe_residual.norm()), float(aux_residual.norm()))
    denominator = max(
        np.hypot(float(blocks.b_fe.norm()), float(blocks.b_aux.norm())), TINY
    )
    for vector in (fe_residual, fe_work, aux_residual, aux_work):
        vector.destroy()
    return float(numerator / denominator)


def _official_rta(
    system: RuntimeStage4System,
    augmented_solution: PETSc.Vec,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    if MPI.COMM_WORLD.rank == 0:
        output_dir.mkdir(parents=True, exist_ok=True)
    MPI.COMM_WORLD.barrier()
    field = _assign_fe_solution_from_augmented(
        augmented_solution, system.floquet_data, system.n_aux
    )
    auxiliary = np.empty(system.n_aux, dtype=np.complex128)
    start, end = augmented_solution.getOwnershipRange()
    local_start = max(start, system.n_fe)
    local_end = min(end, system.n_fe + system.n_aux)
    packet = (
        local_start - system.n_fe,
        local_end - system.n_fe,
        np.asarray(
            augmented_solution.getValues(
                np.arange(local_start, local_end, dtype=PETSc.IntType)
            ),
            dtype=np.complex128,
        ),
    )
    for packet_start, packet_end, values in MPI.COMM_WORLD.allgather(packet):
        auxiliary[packet_start:packet_end] = values
    incident = [
        _incident_projection_onto_top_mode(mode, system.cfg) for mode in system.modes
    ]
    port = _port_power_metrics(system.cfg, system.modes, auxiliary, incident)
    volume = compute_volume_absorption_3d(
        system.mesh_data,
        system.cfg,
        field,
        output_dir,
        incident_power=float(port["incident_power_code_units"]),
        port_metrics=port,
        probe_metrics=None,
    )
    return {
        "R_total": port.get("R_total"),
        "T_total": port.get("T_total"),
        "A_volume_total": volume.get("A_volume_total"),
        "R_plus_T_plus_A_volume": float(
            port.get("R_plus_T", 0.0) + volume.get("A_volume_total", 0.0)
        ),
        "energy_closure_error": volume.get("energy_closure_error_port_volume"),
        **_memory_fields("rta"),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    runtime_metadata = _runtime_metadata(args.exact_command)
    case = args.case_label or f"workstation_p2_h{args.h_nm:g}".replace(".", "p")
    heavy_dir = Path(args.results_dir) / case
    record_path = Path(args.record)
    memory_stage_path = record_path.with_name(record_path.stem + "_memory_stages.jsonl")
    if comm.rank == 0:
        memory_stage_path.unlink(missing_ok=True)
    comm.barrier()
    deviations = _qualification_deviations(args, comm.size)
    qualified_profile = not deviations
    if deviations:
        PETSc.Sys.Print(
            "WARNING: this run is outside the qualified Task28 production profile: "
            + "; ".join(deviations)
        )
    _write_json(
        record_path.with_name(record_path.stem + "_parameters.json"),
        vars(args),
    )
    system = assemble_target_stage4_system(
        h_nm=args.h_nm,
        output_dir=heavy_dir,
        degree=2,
        config_overrides={
            "incident_theta_deg": args.theta_deg,
            "lambda0": args.lambda_nm,
        },
    )
    memory_checkpoints: list[dict[str, Any]] = []

    def checkpoint(stage: str, **extra: Any) -> None:
        row = {
            "case": case,
            "stage": stage,
            "elapsed_s": time.perf_counter() - started,
            **_memory_fields("checkpoint"),
            **extra,
        }
        memory_checkpoints.append(row)
        _write_json(record_path.with_name(record_path.stem + "_progress.json"), row)
        _append_jsonl(
            memory_stage_path, row
        )

    def progress(stage: str, completed: int, total: int) -> None:
        checkpoint(stage, completed=completed, total=total)

    checkpoint("stage4_system_assembled", matrix_stats=system.matrix_stats)
    blocks = extract_petsc_condensed_blocks(
        system.A_petsc,
        system.b_petsc,
        n_fe=system.n_fe,
        n_aux=system.n_aux,
    )
    checkpoint(
        "condensed_blocks_extracted",
        object_ledger=_object_ledger(system=system, blocks=blocks),
    )
    system.A_petsc.destroy()
    if args.compact_lifecycle:
        system.b_petsc.destroy()
        checkpoint(
            "compact_augmented_rhs_released",
            released_objects=["A_augmented", "b_augmented"],
            retained_reusable_augmented_buffer="system.x_petsc",
        )
    rhs = condensed_rhs(blocks)
    assembled_f = blocks.require_f()
    fine_operator = assembled_f
    fine_operator_context = None
    fine_action_relative_error = None
    if args.matrix_free_fine:
        fine_operator, fine_operator_context = create_mpc_form_operator(
            system.bilinear_form,
            system.floquet_data.mpc,
            assembled_f,
        )
        action_test = assembled_f.createVecRight()
        start, end = action_test.getOwnershipRange()
        indices = np.arange(start, end, dtype=float)
        action_test.getArray()[:] = np.sin(0.17 * (indices + 1.0)) + 1j * np.cos(
            0.11 * (indices + 2.0)
        )
        fine_action_relative_error = relative_action_error(
            assembled_f, fine_operator, action_test
        )
        action_test.destroy()
        if fine_action_relative_error > 1.0e-11:
            raise RuntimeError(
                "MPC form fine action failed assembled-F certification: "
                f"{fine_action_relative_error:.6e} > 1e-11"
            )
        checkpoint(
            "matrix_free_fine_action_certified",
            fine_action_relative_error=fine_action_relative_error,
        )
    operator, operator_context = create_matrix_free_condensed_operator(
        blocks, fine_operator=fine_operator
    )
    checkpoint(
        "condensed_operator_ready",
        object_ledger=_object_ledger(
            system=system, blocks=blocks, rhs=rhs, operator=operator
        ),
    )

    basis = _fixed_floquet_hat_basis(
        system,
        operator,
        coarse_slabs=args.coarse_slabs,
        progress=lambda done, total: progress("coarse_basis", done, total),
    )
    checkpoint("coarse_basis_ready", coarse_dimension=len(basis))
    coarse_context = SparseGalerkinTwoLevelPc(
        operator,
        None,
        basis,
        post_smooth=args.post_smooth,
        coarse_progress=lambda done, total: progress("coarse_operator", done, total),
        setup_progress=lambda stage: progress(stage, 0, len(basis)),
    )
    checkpoint(
        "coarse_operator_ready",
        object_ledger=_object_ledger(
            system=system,
            blocks=blocks,
            rhs=rhs,
            operator=operator,
            coarse_context=coarse_context,
        ),
    )
    diagonal_shift, diagonal_scale = _absorption_diagonal_shift(
        assembled_f, args.absorption_shift
    )
    action = _shifted_action(fine_operator, diagonal_shift)
    shifted = (
        None
        if args.subdomain_local_shift
        else _shifted_matrix(assembled_f, diagonal_shift)
    )
    slabs = _complete_physical_slabs(
        system,
        num_slabs=args.num_slabs,
        overlap_layers=args.overlap_layers,
    )
    boundary_count = int(args.selective_diagonal_boundary_slabs)
    if boundary_count < 0 or 2 * boundary_count >= args.num_slabs:
        raise ValueError(
            "selective_diagonal_boundary_slabs must be nonnegative and leave an ILU core"
        )
    local_solver_types = tuple(
        "jacobi"
        if slab < boundary_count or slab >= args.num_slabs - boundary_count
        else "ilu"
        for slab in range(args.num_slabs)
    )
    local_capture = None
    if args.neural_capture_dir:
        local_capture = LocalSlabCapture(
            Path(args.neural_capture_dir),
            rank=comm.rank,
            maximum_samples_per_slab=args.neural_capture_limit,
            sample_stride=args.neural_capture_stride,
            run_metadata={
                "branch": runtime_metadata.get("branch"),
                "git_commit": runtime_metadata.get("git_commit"),
                "h_nm": float(args.h_nm),
                "degree": 2,
                "wavelength_nm": float(args.lambda_nm),
                "theta_deg": float(args.theta_deg),
                "mpi_size": int(comm.size),
            },
        )
    local_solver_factory = None
    if args.neural_checkpoint_root and args.linear_reduced_checkpoint_root:
        raise ValueError("neural and linear-reduced local backends are mutually exclusive")
    if args.neural_checkpoint_root:
        checkpoint_root = Path(args.neural_checkpoint_root)
        enabled_slabs = (
            None
            if args.neural_enabled_slabs is None
            else {int(value) for value in args.neural_enabled_slabs.split(",") if value}
        )

        def local_solver_factory(subdomain, portable_operator, fallback_action):
            fallback = IluLocalSlabSolver(
                portable_operator.shape[0], fallback_action
            )
            if enabled_slabs is not None and int(subdomain) not in enabled_slabs:
                return fallback
            checkpoint_dir = checkpoint_root / f"slab_{int(subdomain):03d}"
            rank_checkpoint_dir = (
                checkpoint_root
                / f"rank_{int(comm.rank):04d}"
                / f"slab_{int(subdomain):03d}"
            )
            if not checkpoint_dir.is_dir() and rank_checkpoint_dir.is_dir():
                checkpoint_dir = rank_checkpoint_dir
            model = FrozenNumpyMlp.load(
                checkpoint_dir,
                expected_operator_fingerprint=portable_operator.fingerprint,
            )
            if args.neural_lane == "nn_only":
                return NeuralLocalSlabSolver(
                    portable_operator,
                    model,
                    fallback=fallback,
                    residual_ratio_limit=args.neural_residual_limit,
                )
            return IluNeuralCorrectionSlabSolver(
                portable_operator,
                model,
                fallback,
                residual_ratio_limit=args.neural_residual_limit,
            )
    elif args.linear_reduced_checkpoint_root:
        checkpoint_root = Path(args.linear_reduced_checkpoint_root)
        enabled_slabs = (
            None
            if args.linear_reduced_enabled_slabs is None
            else {int(value) for value in args.linear_reduced_enabled_slabs.split(",") if value}
        )

        def local_solver_factory(subdomain, portable_operator, fallback_action):
            fallback = IluLocalSlabSolver(portable_operator.shape[0], fallback_action)
            if enabled_slabs is not None and int(subdomain) not in enabled_slabs:
                return fallback
            checkpoint_dir = checkpoint_root / f"slab_{int(subdomain):03d}"
            model = FrozenLinearReducedMap.load(
                checkpoint_dir,
                expected_operator_fingerprint=portable_operator.fingerprint,
            )
            return IluLinearReducedCorrectionSlabSolver(
                portable_operator,
                model,
                fallback,
                shadow=args.linear_reduced_mode == "shadow",
            )
    smoother = DistributedPhysicalSlabSmoother(
        assembled_f if shifted is None else shifted,
        slabs,
        ilu_levels=args.ilu_levels,
        local_ksp_iterations=1,
        local_ksp_type="gmres",
        smoother_iterations=2,
        smoother_ksp_type=args.smoother_ksp_type,
        action_operator=action,
        diagonal_shift=diagonal_shift if args.subdomain_local_shift else None,
        factor_only_storage=args.factor_only_storage,
        local_solver_types=local_solver_types,
        interpolation="basic",
        assembly_order="two_color",
        progress=lambda done, total: progress("slab_factorization", done, total),
        local_operator_observer=(
            local_capture.observe_operator if local_capture is not None else None
        ),
        local_sample_observer=(
            local_capture.observe_sample if local_capture is not None else None
        ),
        local_solver_factory=local_solver_factory,
    )
    if shifted is not None:
        shifted.destroy()
    coarse_context.set_smoother(smoother)
    if args.matrix_free_fine:
        blocks.release_f()
        checkpoint(
            "assembled_f_released",
            released_objects=["assembled_F"],
            fine_action_relative_error=fine_action_relative_error,
        )
    checkpoint(
        "slab_factors_ready",
        slab_diagnostics=smoother.diagnostics,
        object_ledger=_object_ledger(
            system=system,
            blocks=blocks,
            rhs=rhs,
            operator=operator,
            coarse_context=coarse_context,
            smoother=smoother,
        ),
    )
    pc_certificate = None
    if args.certify_pc or args.ksp_type != "fgmres":
        certificate_template = operator.createVecRight()
        try:
            pc_certificate = certify_fixed_linear_preconditioner(
                coarse_context, certificate_template
            )
        finally:
            certificate_template.destroy()
        if pc_certificate["linearity_relative_error"] > 1.0e-11:
            raise RuntimeError(
                "fixed-PC linearity gate failed: "
                f"{pc_certificate['linearity_relative_error']:.6e} > 1e-11"
            )
        if pc_certificate["determinism_relative_error"] > 1.0e-13:
            raise RuntimeError(
                "fixed-PC determinism gate failed: "
                f"{pc_certificate['determinism_relative_error']:.6e} > 1e-13"
            )
        checkpoint("pc_action_certified", pc_action_certificate=pc_certificate)
    pc_apply_count_before_solve = coarse_context.apply_count
    smoother_apply_count_before_solve = smoother.apply_count
    operator_apply_count_before_solve = operator_context.apply_count
    solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution = operator.createVecRight()
    history: list[dict[str, Any]] = []
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(operator)
    ksp.setType(args.ksp_type)
    if args.ksp_type in {"fgmres", "gmres"}:
        ksp.setGMRESRestart(args.restart)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        pc_side = "right"
    else:
        ksp.setPCSide(PETSc.PC.Side.LEFT)
        pc_side = "left"
    ksp.setTolerances(rtol=args.rtol, atol=0.0, max_it=args.max_it)
    ksp.getPC().setType(PETSc.PC.Type.PYTHON)
    ksp.getPC().setPythonContext(coarse_context)
    ksp.setUp()
    checkpoint(
        "outer_ksp_ready",
        ksp_type=args.ksp_type,
        pc_side=pc_side,
        object_ledger=_object_ledger(
            system=system,
            blocks=blocks,
            rhs=rhs,
            operator=operator,
            coarse_context=coarse_context,
            smoother=smoother,
            ksp_type=args.ksp_type,
            restart=args.restart,
            solution_vectors=2,
            augmented_buffer_reused=args.compact_lifecycle,
        ),
    )
    rhs_norm = float(rhs.norm())
    solve_started = time.perf_counter()

    def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
        if iteration == 0 or iteration % args.monitor_stride == 0:
            current_solution = current.buildSolution(monitor_solution)
            row = {
                "case": case,
                "stage": "outer_krylov_solve",
                "iteration": int(iteration),
                "reported_relative_residual": float(residual_norm)
                / max(rhs_norm, TINY),
                "true_relative_residual": _linear_residual(
                    operator, rhs, current_solution
                ),
                "elapsed_s": time.perf_counter() - solve_started,
                **_memory_fields("monitor"),
            }
            history.append(row)
            _write_json(record_path.with_name(record_path.stem + "_progress.json"), row)
            _append_jsonl(
                memory_stage_path, row
            )

    ksp.setMonitor(monitor)
    ksp.solve(rhs, solution)
    solve_s = time.perf_counter() - solve_started
    checkpoint(
        "outer_krylov_solved",
        iterations=int(ksp.getIterationNumber()),
        ksp_reason=int(ksp.getConvergedReason()),
    )
    condensed_residual = _linear_residual(operator, rhs, solution)
    auxiliary = recover_petsc_auxiliary(blocks, solution)
    augmented = _combined_augmented_vector(
        system,
        solution,
        auxiliary,
        target=system.x_petsc if args.compact_lifecycle else None,
    )
    full_residual = _full_augmented_residual(
        blocks, solution, auxiliary, fine_operator=fine_operator
    )
    checkpoint(
        "true_residuals_verified",
        condensed_true_residual=condensed_residual,
        full_augmented_true_residual=full_residual,
    )
    ksp_reason = int(ksp.getConvergedReason())
    iterations = int(ksp.getIterationNumber())
    reported_relative_residual = float(ksp.getResidualNorm()) / max(rhs_norm, TINY)
    slab_diagnostics = smoother.diagnostics
    pc_apply_count = coarse_context.apply_count - pc_apply_count_before_solve
    operator_apply_count = operator_context.apply_count - operator_apply_count_before_solve
    smoother_apply_count = smoother.apply_count - smoother_apply_count_before_solve
    result = {
        "benchmark_id": f"l3_iterative_h{args.h_nm:g}".replace(".", "p"),
        "case": case,
        "profile": args.profile,
        "status": "pass" if qualified_profile else "experimental_unqualified",
        "qualified_profile": qualified_profile,
        "qualification_deviations": deviations,
        "resolved_config": args.resolved_config,
        "physical_model": stage4_physical_model(system.cfg),
        "artifact_root": str(Path(args.results_dir)),
        "artifact_directory": str(heavy_dir),
        "record_path": str(record_path),
        "metadata": runtime_metadata,
        "ordinary_default_changed": False,
        "h_nm": args.h_nm,
        "mpi_size": comm.size,
        "n_fe": system.n_fe,
        "n_aux": system.n_aux,
        "coarse_dimension": len(basis),
        "coarse_slabs": args.coarse_slabs,
        "coarse_rank": coarse_context.coarse_rank,
        "coarse_condition": coarse_context.coarse_condition,
        "coarse_action_relative_error": coarse_context.coarse_action_relative_error,
        "num_slabs": args.num_slabs,
        "overlap_layers": args.overlap_layers,
        "absorption_shift": args.absorption_shift,
        "shift_diagonal_scale": diagonal_scale,
        "ilu_levels": args.ilu_levels,
        "smoother_iterations": 2,
        "smoother_ksp_type": args.smoother_ksp_type,
        "selective_diagonal_boundary_slabs": boundary_count,
        "post_smooth": args.post_smooth,
        "subdomain_local_shift": args.subdomain_local_shift,
        "factor_only_storage": args.factor_only_storage,
        "matrix_free_fine": args.matrix_free_fine,
        "fine_action_relative_error": fine_action_relative_error,
        "fine_form_apply_count": (
            fine_operator_context.apply_count
            if fine_operator_context is not None
            else None
        ),
        "compact_lifecycle": args.compact_lifecycle,
        "ksp_type": args.ksp_type,
        "pc_side": pc_side,
        "restart": args.restart,
        "rtol": args.rtol,
        "max_it": args.max_it,
        "ksp_reason": ksp_reason,
        "iterations": iterations,
        "reported_relative_residual": reported_relative_residual,
        "condensed_true_residual": condensed_residual,
        "full_augmented_true_residual": full_residual,
        "solve_s": solve_s,
        "total_s": time.perf_counter() - started,
        "pc_apply_count": pc_apply_count,
        "pc_certification_apply_count": pc_apply_count_before_solve,
        "one_level_apply_count": smoother_apply_count,
        "operator_apply_count": operator_apply_count,
        "operator_setup_apply_count": operator_apply_count_before_solve,
        "pc_action_certificate": pc_certificate,
        "slab_diagnostics": slab_diagnostics,
        "history": history,
        "memory_checkpoints": memory_checkpoints,
        "object_ledger_at_solve": _object_ledger(
            system=system,
            blocks=blocks,
            rhs=rhs,
            operator=operator,
            coarse_context=coarse_context,
            smoother=smoother,
            ksp_type=args.ksp_type,
            restart=args.restart,
            solution_vectors=2,
            augmented_buffer_reused=args.compact_lifecycle,
        ),
        **_memory_fields("final"),
    }
    if args.compact_lifecycle:
        auxiliary.destroy()
        monitor_solution.destroy()
        solution.destroy()
        ksp.destroy()
        coarse_context.destroy()
        smoother.destroy()
        action.destroy()
        operator.destroy()
        if args.matrix_free_fine:
            fine_operator.destroy()
        rhs.destroy()
        blocks.destroy()
        checkpoint(
            "solver_stack_released_before_rta",
            released_objects=[
                "u_auxiliary",
                "monitor_solution",
                "condensed_solution",
                "outer_ksp",
                "coarse_context",
                "slab_smoother_and_factors",
                "shifted_action",
                "condensed_shell_and_work",
                "condensed_rhs",
                "F_C_D_H_and_block_rhs",
            ],
            retained_objects=["augmented_solution", "mesh", "space", "MPC", "modes"],
        )
        result.update(_memory_fields("after_solver_release"))
    if full_residual <= args.rta_threshold:
        result["official_rta"] = _official_rta(
            system, augmented, output_dir=heavy_dir / "rta"
        )
        result["peak_total_rss_including_rta_gb"] = max(
            result["final_peak_total_gb"],
            result["official_rta"]["rta_peak_total_gb"],
        )
        checkpoint("official_rta_complete", official_rta=result["official_rta"])
    result["memory_checkpoints"] = memory_checkpoints
    if local_capture is not None:
        local_capture.write_manifest()
        result["neural_local_capture"] = local_capture.diagnostics
    _write_json(record_path, result)
    PETSc.Sys.Print(json.dumps(result, indent=2, default=_json_default))
    augmented.destroy()
    if not args.compact_lifecycle:
        auxiliary.destroy()
        monitor_solution.destroy()
        solution.destroy()
        ksp.destroy()
        coarse_context.destroy()
        smoother.destroy()
        action.destroy()
        operator.destroy()
        if args.matrix_free_fine:
            fine_operator.destroy()
        rhs.destroy()
        blocks.destroy()
        system.b_petsc.destroy()
        system.x_petsc.destroy()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="显式 opt-in 的 p=2 workstation 物理分片两级迭代 benchmark"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--h-nm", type=float, default=None)
    parser.add_argument("--theta-deg", type=float, default=None)
    parser.add_argument("--lambda-nm", type=float, default=None)
    parser.add_argument("--coarse-slabs", type=int, default=None)
    parser.add_argument("--num-slabs", type=int, default=None)
    parser.add_argument("--overlap-layers", type=float, default=None)
    parser.add_argument("--absorption-shift", type=float, default=None)
    parser.add_argument("--ilu-levels", type=int, default=None)
    parser.add_argument(
        "--ksp-type",
        choices=("fgmres", "gmres", "tfqmr", "bcgs"),
        default="fgmres",
    )
    parser.add_argument(
        "--smoother-ksp-type",
        choices=("gmres", "richardson"),
        default="gmres",
    )
    parser.add_argument("--restart", type=int, default=None)
    parser.add_argument("--selective-diagonal-boundary-slabs", type=int, default=0)
    parser.add_argument("--max-it", type=int, default=None)
    parser.add_argument("--rtol", type=float, default=None)
    parser.add_argument("--rta-threshold", type=float, default=None)
    parser.add_argument("--monitor-stride", type=int, default=None)
    parser.add_argument("--post-smooth", action="store_true")
    parser.add_argument("--subdomain-local-shift", action="store_true")
    parser.add_argument("--factor-only-storage", action="store_true")
    parser.add_argument("--certify-pc", action="store_true")
    parser.add_argument("--compact-lifecycle", action="store_true")
    parser.add_argument("--matrix-free-fine", action="store_true")
    parser.add_argument("--neural-capture-dir")
    parser.add_argument("--neural-capture-limit", type=int, default=128)
    parser.add_argument("--neural-capture-stride", type=int, default=10)
    parser.add_argument("--neural-checkpoint-root")
    parser.add_argument(
        "--neural-enabled-slabs",
        help="comma-separated slab ids; omit to require checkpoints for every slab",
    )
    parser.add_argument(
        "--neural-lane", choices=("nn_only", "ilu_correction"), default="ilu_correction"
    )
    parser.add_argument("--neural-residual-limit", type=float, default=0.95)
    parser.add_argument("--linear-reduced-checkpoint-root")
    parser.add_argument("--linear-reduced-enabled-slabs")
    parser.add_argument(
        "--linear-reduced-mode", choices=("shadow", "active"), default="shadow"
    )
    parser.add_argument("--case-label")
    parser.add_argument("--record", required=True)
    parser.add_argument("--results-dir", default=None)
    args = parser.parse_args()
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    defaults = {
        "h_nm": 5.0,
        "theta_deg": config["theta_deg"],
        "lambda_nm": config["lambda_nm"],
        "coarse_slabs": config["coarse_slabs"],
        "num_slabs": config["num_physical_slabs"],
        "overlap_layers": config["overlap_layers"],
        "absorption_shift": config["absorption_shift"],
        "ilu_levels": config["ilu_levels"],
        "restart": config["restart"],
        "max_it": config["max_it"],
        "rtol": config["rtol"],
        "rta_threshold": config["rta_threshold"],
        "monitor_stride": config["monitor_stride"],
        "results_dir": config["artifact_root"],
    }
    for name, value in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    args.profile = config["profile"]
    args.resolved_config = {
        **config,
        "h_nm": args.h_nm,
        "theta_deg": args.theta_deg,
        "lambda_nm": args.lambda_nm,
        "coarse_slabs": args.coarse_slabs,
        "num_physical_slabs": args.num_slabs,
        "overlap_layers": args.overlap_layers,
        "absorption_shift": args.absorption_shift,
        "ilu_levels": args.ilu_levels,
        "restart": args.restart,
        "max_it": args.max_it,
        "rtol": args.rtol,
        "rta_threshold": args.rta_threshold,
        "monitor_stride": args.monitor_stride,
        "artifact_root": args.results_dir,
        "post_smooth": args.post_smooth,
        "subdomain_local_shift": args.subdomain_local_shift,
        "factor_only_storage": args.factor_only_storage,
        "certify_pc": args.certify_pc,
        "compact_lifecycle": args.compact_lifecycle,
        "matrix_free_fine": args.matrix_free_fine,
        "neural_capture_dir": args.neural_capture_dir,
        "neural_capture_limit": args.neural_capture_limit,
        "neural_capture_stride": args.neural_capture_stride,
        "neural_checkpoint_root": args.neural_checkpoint_root,
        "neural_enabled_slabs": args.neural_enabled_slabs,
        "neural_lane": args.neural_lane,
        "neural_residual_limit": args.neural_residual_limit,
        "linear_reduced_checkpoint_root": args.linear_reduced_checkpoint_root,
        "linear_reduced_enabled_slabs": args.linear_reduced_enabled_slabs,
        "linear_reduced_mode": args.linear_reduced_mode,
        "ksp_type": args.ksp_type,
        "smoother_ksp_type": args.smoother_ksp_type,
        "selective_diagonal_boundary_slabs": args.selective_diagonal_boundary_slabs,
    }
    args.exact_command = os.environ.get(
        "BENCHMARK_EXACT_COMMAND",
        f"mpiexec -n {MPI.COMM_WORLD.size} " + shlex.join([sys.executable, *sys.argv]),
    )
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
