from __future__ import annotations

import argparse
import json
import resource
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
    recover_petsc_auxiliary,
)
from src.solvers.dtn_port_3d import (
    _assign_fe_solution_from_augmented,
    _incident_projection_onto_top_mode,
    _port_power_metrics,
)
from src.solvers.physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    SparseGalerkinTwoLevelPc,
    compress_petsc_vector,
    gather_global_subdomain_indices,
)
from src.solvers.solve_vector_maxwell import _json_default
from src.solvers.stage4_runtime import (
    RuntimeStage4System,
    assemble_target_stage4_system,
)


TINY = np.finfo(float).tiny


def _write_json(path: Path, payload: Any) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


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


def _shifted_matrix(
    matrix: PETSc.Mat, absorption_shift: float
) -> tuple[PETSc.Mat, PETSc.Vec, float]:
    diagonal = matrix.createVecLeft()
    matrix.getDiagonal(diagonal)
    absolute = np.abs(diagonal.getArray(readonly=True))
    scale = float(MPI.COMM_WORLD.allreduce(float(absolute.max(initial=0)), op=MPI.MAX))
    shifted_diagonal = diagonal.copy()
    shifted_diagonal.getArray()[:] += (
        -1j * absorption_shift * np.maximum(absolute, 1e-12 * scale)
    )
    shifted = matrix.copy()
    shifted.setDiagonal(shifted_diagonal)
    shifted.assemble()
    diagonal.destroy()
    return shifted, shifted_diagonal, scale


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


def _shifted_action(matrix: PETSc.Mat, shifted: PETSc.Mat) -> PETSc.Mat:
    original = matrix.createVecLeft()
    difference = shifted.createVecLeft()
    matrix.getDiagonal(original)
    shifted.getDiagonal(difference)
    difference.axpy(PETSc.ScalarType(-1.0), original)
    original.destroy()
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
) -> PETSc.Vec:
    result = system.b_petsc.duplicate()
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


def _full_augmented_residual(blocks, u_fe: PETSc.Vec, u_aux: PETSc.Vec) -> float:
    fe_residual = blocks.F.createVecLeft()
    fe_work = blocks.C.createVecLeft()
    aux_residual = blocks.D.createVecLeft()
    aux_work = blocks.H.createVecLeft()
    blocks.F.mult(u_fe, fe_residual)
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
    case = args.case_label or f"workstation_p2_h{args.h_nm:g}".replace(".", "p")
    heavy_dir = Path(args.results_dir) / case
    record_path = Path(args.record)
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
    blocks = extract_petsc_condensed_blocks(
        system.A_petsc,
        system.b_petsc,
        n_fe=system.n_fe,
        n_aux=system.n_aux,
    )
    system.A_petsc.destroy()
    rhs = condensed_rhs(blocks)
    operator, operator_context = create_matrix_free_condensed_operator(blocks)

    def progress(stage: str, completed: int, total: int) -> None:
        _write_json(
            record_path.with_name(record_path.stem + "_progress.json"),
            {
                "case": case,
                "stage": stage,
                "completed": completed,
                "total": total,
                "elapsed_s": time.perf_counter() - started,
                **_memory_fields("progress"),
            },
        )

    basis = _fixed_floquet_hat_basis(
        system,
        operator,
        coarse_slabs=args.coarse_slabs,
        progress=lambda done, total: progress("coarse_basis", done, total),
    )
    coarse_context = SparseGalerkinTwoLevelPc(
        operator,
        None,
        basis,
        coarse_progress=lambda done, total: progress("coarse_operator", done, total),
        setup_progress=lambda stage: progress(stage, 0, len(basis)),
    )
    shifted, shifted_diagonal, diagonal_scale = _shifted_matrix(
        blocks.F, args.absorption_shift
    )
    shifted_diagonal.destroy()
    action = _shifted_action(blocks.F, shifted)
    slabs = _complete_physical_slabs(
        system,
        num_slabs=args.num_slabs,
        overlap_layers=args.overlap_layers,
    )
    smoother = DistributedPhysicalSlabSmoother(
        shifted,
        slabs,
        ilu_levels=args.ilu_levels,
        local_ksp_iterations=1,
        local_ksp_type="gmres",
        smoother_iterations=2,
        action_operator=action,
        interpolation="basic",
        assembly_order="two_color",
        progress=lambda done, total: progress("slab_factorization", done, total),
    )
    shifted.destroy()
    coarse_context.set_smoother(smoother)
    solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution = operator.createVecRight()
    history: list[dict[str, Any]] = []
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(operator)
    ksp.setType("fgmres")
    ksp.setGMRESRestart(args.restart)
    ksp.setPCSide(PETSc.PC.Side.RIGHT)
    ksp.setTolerances(rtol=args.rtol, atol=0.0, max_it=args.max_it)
    ksp.getPC().setType(PETSc.PC.Type.PYTHON)
    ksp.getPC().setPythonContext(coarse_context)
    rhs_norm = float(rhs.norm())
    solve_started = time.perf_counter()

    def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
        if iteration == 0 or iteration % args.monitor_stride == 0:
            current_solution = current.buildSolution(monitor_solution)
            row = {
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

    ksp.setMonitor(monitor)
    ksp.solve(rhs, solution)
    solve_s = time.perf_counter() - solve_started
    condensed_residual = _linear_residual(operator, rhs, solution)
    auxiliary = recover_petsc_auxiliary(blocks, solution)
    augmented = _combined_augmented_vector(system, solution, auxiliary)
    full_residual = _full_augmented_residual(blocks, solution, auxiliary)
    result = {
        "case": case,
        "profile": "workstation_p2_fixed_coarse_physical_slab",
        "ordinary_default_changed": False,
        "h_nm": args.h_nm,
        "mpi_size": comm.size,
        "n_fe": system.n_fe,
        "n_aux": system.n_aux,
        "coarse_dimension": len(basis),
        "coarse_rank": coarse_context.coarse_rank,
        "coarse_condition": coarse_context.coarse_condition,
        "coarse_action_relative_error": coarse_context.coarse_action_relative_error,
        "num_slabs": args.num_slabs,
        "overlap_layers": args.overlap_layers,
        "absorption_shift": args.absorption_shift,
        "shift_diagonal_scale": diagonal_scale,
        "ilu_levels": args.ilu_levels,
        "smoother_iterations": 2,
        "restart": args.restart,
        "max_it": args.max_it,
        "ksp_reason": int(ksp.getConvergedReason()),
        "iterations": int(ksp.getIterationNumber()),
        "reported_relative_residual": float(ksp.getResidualNorm())
        / max(rhs_norm, TINY),
        "condensed_true_residual": condensed_residual,
        "full_augmented_true_residual": full_residual,
        "solve_s": solve_s,
        "total_s": time.perf_counter() - started,
        "pc_apply_count": coarse_context.apply_count,
        "operator_apply_count": operator_context.apply_count,
        "slab_diagnostics": smoother.diagnostics,
        "history": history,
        **_memory_fields("final"),
    }
    if full_residual <= args.rta_threshold:
        result["official_rta"] = _official_rta(
            system, augmented, output_dir=heavy_dir / "rta"
        )
        result["peak_total_rss_including_rta_gb"] = max(
            result["final_peak_total_gb"],
            result["official_rta"]["rta_peak_total_gb"],
        )
    _write_json(record_path, result)
    PETSc.Sys.Print(json.dumps(result, indent=2, default=_json_default))
    augmented.destroy()
    auxiliary.destroy()
    monitor_solution.destroy()
    solution.destroy()
    ksp.destroy()
    coarse_context.destroy()
    smoother.destroy()
    action.destroy()
    operator.destroy()
    rhs.destroy()
    blocks.destroy()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="显式 opt-in 的 p=2 workstation 物理分片两级迭代 benchmark"
    )
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--theta-deg", type=float, default=80.0)
    parser.add_argument("--lambda-nm", type=float, default=13.5)
    parser.add_argument("--coarse-slabs", type=int, default=24)
    parser.add_argument("--num-slabs", type=int, default=16)
    parser.add_argument("--overlap-layers", type=float, default=0.25)
    parser.add_argument("--absorption-shift", type=float, default=0.1)
    parser.add_argument("--ilu-levels", type=int, default=1)
    parser.add_argument("--restart", type=int, default=100)
    parser.add_argument("--max-it", type=int, default=3000)
    parser.add_argument("--rtol", type=float, default=1e-6)
    parser.add_argument("--rta-threshold", type=float, default=1.1e-6)
    parser.add_argument("--monitor-stride", type=int, default=50)
    parser.add_argument("--case-label")
    parser.add_argument("--record", required=True)
    parser.add_argument("--results-dir", default="benchmarks/artifacts")
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
