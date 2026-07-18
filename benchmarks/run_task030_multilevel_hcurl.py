from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import time
from typing import Any

import numpy as np
from dolfinx import mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.condensed_dtn import (
    condensed_rhs,
    create_matrix_free_condensed_operator,
    extract_petsc_condensed_blocks,
)
from src.solvers.hcurl_multilevel import (
    DampedJacobiSmoother,
    GalerkinMultilevelPc,
    ModalWoodburyPc,
    build_absorption_shifted_matrix,
    build_active_dof_map,
    build_condensed_galerkin_coarse,
    build_nonmatching_active_transfer,
    load_canonical_screen_baseline,
    load_nonmatching_transfer_cache,
    classify_screen_candidate,
    save_nonmatching_transfer_cache,
    validate_transfer_action_against_interpolation,
)
from src.solvers.physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    gather_global_subdomain_indices,
)
from src.solvers.stage4_runtime import assemble_target_stage4_system

from benchmarks.run_workstation_iterative import _complete_physical_slabs


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = (
    REPOSITORY_ROOT / "benchmarks" / "cases" / "060_multilevel_hcurl_iterative_solver"
)
DEFAULT_CONFIG = CASE_ROOT / "config.json"


def _write_json(path: Path, payload: Any) -> None:
    if MPI.COMM_WORLD.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _rss_gb() -> dict[str, float]:
    comm = MPI.COMM_WORLD
    local_peak_mb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0
    total = float(comm.allreduce(local_peak_mb, op=MPI.SUM)) / 1024.0
    maximum = float(comm.allreduce(local_peak_mb, op=MPI.MAX)) / 1024.0
    return {"peak_total_rss_gb": total, "peak_max_rank_rss_gb": maximum}


def _linear_residual(matrix: PETSc.Mat, rhs: PETSc.Vec, solution: PETSc.Vec) -> float:
    residual = rhs.duplicate()
    matrix.mult(solution, residual)
    residual.axpy(PETSc.ScalarType(-1.0), rhs)
    value = float(residual.norm()) / max(float(rhs.norm()), np.finfo(float).tiny)
    residual.destroy()
    return value


def _complete_midpoint_groups(
    system: Any,
    *,
    axes: tuple[int, ...],
) -> tuple[np.ndarray, ...]:
    """Build complete tensor-cell patches keyed by selected midpoint axes."""

    msh = system.mesh_data.mesh
    tdim = msh.topology.dim
    cell_map = msh.topology.index_map(tdim)
    cells = np.arange(cell_map.size_local, dtype=np.int32)
    midpoints = mesh.compute_midpoints(msh, tdim, cells)
    local: dict[tuple[float, ...], list[int]] = {}
    for cell, midpoint in zip(cells, midpoints, strict=True):
        key = tuple(round(float(midpoint[axis]), 10) for axis in axes)
        local.setdefault(key, []).append(int(cell))
    packets = MPI.COMM_WORLD.allgather(tuple(local))
    keys = sorted({key for packet in packets for key in packet})
    index_map = system.V.dofmap.index_map
    pieces: list[np.ndarray] = []
    for key in keys:
        selected = local.get(key, [])
        if selected:
            local_dofs = np.unique(
                np.concatenate([system.V.dofmap.cell_dofs(cell) for cell in selected])
            )
            global_dofs = index_map.local_to_global(local_dofs.astype(np.int32)).astype(
                PETSc.IntType, copy=False
            )
        else:
            global_dofs = np.empty(0, dtype=PETSc.IntType)
        pieces.append(global_dofs)
    return gather_global_subdomain_indices(pieces)


def _build_target_space(
    *, h_nm: float, degree: int, output_dir: Path, label: str
) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    cfg = target_stage4_config(degree=degree, h_nm=h_nm)
    cfg.case_name = label
    mesh_started = time.perf_counter()
    mesh_data = build_airbox_mesh_3d(cfg, output_dir)
    mesh_s = float(comm.allreduce(time.perf_counter() - mesh_started, op=MPI.MAX))
    space_started = time.perf_counter()
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    space_s = float(comm.allreduce(time.perf_counter() - space_started, op=MPI.MAX))
    messages: list[str] = []
    mpc_started = time.perf_counter()
    floquet = build_double_floquet_mpc(V, mesh_data, cfg, messages.append)
    mpc_s = float(comm.allreduce(time.perf_counter() - mpc_started, op=MPI.MAX))
    active = build_active_dof_map(V, floquet.local_slave_dofs)
    metadata = {
        "label": label,
        "h_nm": float(h_nm),
        "degree": int(degree),
        "mesh_cells_resolved": list(mesh_data.mesh_cells_resolved),
        "mesh_spacing_mode_resolved": mesh_data.mesh_spacing_mode_resolved,
        "mesh_axis_cell_stats": mesh_data.mesh_axis_cell_stats,
        "material_plane_alignment": mesh_data.material_plane_alignment,
        "global_full_dofs": active.global_full_size,
        "global_active_dofs": active.global_active_size,
        "global_slave_dofs": active.global_full_size - active.global_active_size,
        "floquet_constraint_mode": floquet.constraint_mode_resolved,
        "max_masters_per_slave": int(floquet.max_masters_per_slave),
        "mesh_s": mesh_s,
        "space_s": space_s,
        "floquet_s": mpc_s,
        "total_s": float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX)),
        **_rss_gb(),
    }
    return cfg, mesh_data, V, floquet, metadata


def _run_baseline(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    baseline = load_canonical_screen_baseline(
        REPOSITORY_ROOT / config["baseline_reference"],
        repository_root=REPOSITORY_ROOT,
    )
    result = {
        "status": "passed",
        "reference_path": str(baseline.reference_path.relative_to(REPOSITORY_ROOT)),
        "canonical_path": str(baseline.canonical_path.relative_to(REPOSITORY_ROOT)),
        "sha256": baseline.sha256,
        "screen_iteration": baseline.iteration,
        "screen_true_relative_residual": baseline.true_relative_residual,
        "peak_rss_gb": baseline.peak_rss_gb,
        "full_true_relative_residual": baseline.full_true_relative_residual,
        "total_iterations": baseline.total_iterations,
    }
    _write_json(Path(args.record), result)
    return result


def _run_hierarchy(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    del config
    comm = MPI.COMM_WORLD
    artifact_root = Path(args.artifact_root)
    fine = _build_target_space(
        h_nm=args.fine_h_nm,
        degree=args.fine_degree,
        output_dir=artifact_root / "fine_space",
        label="task030_fine_space",
    )
    coarse = _build_target_space(
        h_nm=args.coarse_h_nm,
        degree=args.coarse_degree,
        output_dir=artifact_root / "coarse_space",
        label="task030_coarse_space",
    )
    _fine_cfg, fine_mesh_data, fine_space, fine_floquet, fine_metadata = fine
    _coarse_cfg, coarse_mesh_data, coarse_space, coarse_floquet, coarse_metadata = (
        coarse
    )
    result: dict[str, Any] = {
        "record_type": "task030_hierarchy_probe",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mpi_size": comm.size,
        "fine": fine_metadata,
        "coarse": coarse_metadata,
        "ordinary_default_changed": False,
        "status": "inventory_only",
        **_rss_gb(),
    }
    if args.build_transfer:
        progress_path = Path(args.record).with_name(
            Path(args.record).stem + "_progress.json"
        )

        def progress(completed: int, total: int) -> None:
            if (
                completed == 1
                or completed == total
                or completed % args.progress_stride == 0
            ):
                _write_json(
                    progress_path,
                    {
                        "stage": "nonmatching_transfer",
                        "completed": completed,
                        "total": total,
                        **_rss_gb(),
                    },
                )

        transfer = build_nonmatching_active_transfer(
            fine_space=fine_space,
            coarse_space=coarse_space,
            fine_local_slave_dofs=fine_floquet.local_slave_dofs,
            coarse_local_slave_dofs=coarse_floquet.local_slave_dofs,
            fine_mpc=fine_floquet.mpc,
            coarse_mpc=coarse_floquet.mpc,
            progress=progress,
        )
        action_error = validate_transfer_action_against_interpolation(
            transfer,
            fine_space=fine_space,
            coarse_space=coarse_space,
            fine_local_slave_dofs=fine_floquet.local_slave_dofs,
            fine_mpc=fine_floquet.mpc,
            coarse_mpc=coarse_floquet.mpc,
        )
        result["transfer"] = {
            **transfer.validation,
            "fresh_action_relative_error": action_error,
            **_rss_gb(),
        }
        result["status"] = (
            "passed"
            if transfer.validation["status"] == "passed" and action_error <= 1.0e-12
            else "failed"
        )
        if result["status"] == "passed":
            save_nonmatching_transfer_cache(
                transfer,
                Path(args.cache_dir),
                metadata={
                    "fine": fine_metadata,
                    "coarse": coarse_metadata,
                    "fresh_action_relative_error": action_error,
                },
            )
            result["transfer"]["cache_dir"] = str(Path(args.cache_dir))
        transfer.destroy()
    _write_json(Path(args.record), result)
    del fine_mesh_data, coarse_mesh_data
    return result


def _run_screen(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    baseline = load_canonical_screen_baseline(
        REPOSITORY_ROOT / config["baseline_reference"],
        repository_root=REPOSITORY_ROOT,
    )
    started = time.perf_counter()
    artifact_root = Path(args.artifact_root) / args.candidate
    system = assemble_target_stage4_system(
        h_nm=args.h_nm,
        output_dir=artifact_root / "fine_system",
        degree=2,
    )
    blocks = extract_petsc_condensed_blocks(
        system.A_petsc,
        system.b_petsc,
        n_fe=system.n_fe,
        n_aux=system.n_aux,
    )
    system.A_petsc.destroy()
    system.b_petsc.destroy()
    system.x_petsc.destroy()
    rhs = condensed_rhs(blocks)
    operator, operator_context = create_matrix_free_condensed_operator(blocks)

    coarse_tuple = _build_target_space(
        h_nm=args.coarse_h_nm,
        degree=1,
        output_dir=artifact_root / "coarse_space",
        label=f"task030_{args.candidate}_coarse",
    )
    _cfg, coarse_mesh_data, coarse_space, coarse_floquet, coarse_metadata = coarse_tuple
    transfer = load_nonmatching_transfer_cache(
        Path(args.cache_dir),
        coarse_space=coarse_floquet.mpc.function_space,
        coarse_local_slave_dofs=coarse_floquet.local_slave_dofs,
        expected_fine_global_dofs=system.n_fe,
        expected_fine_local_dofs=int(blocks.F.getLocalSize()[0]),
    )
    coarse_data = build_condensed_galerkin_coarse(
        F=blocks.F,
        C=blocks.C,
        D=blocks.D,
        H=blocks.H,
        transfer=transfer.matrix,
    )
    coarse_ksp = PETSc.KSP().create(comm)
    coarse_ksp.setOperators(coarse_data.matrix)
    coarse_ksp.setType("preonly")
    coarse_pc = coarse_ksp.getPC()
    coarse_pc.setType("lu")
    coarse_pc.setFactorSolverType("mumps")
    coarse_setup_started = time.perf_counter()
    coarse_ksp.setUp()
    coarse_setup_s = time.perf_counter() - coarse_setup_started

    shifted, shift_scale = build_absorption_shifted_matrix(
        blocks.F, args.absorption_shift
    )
    smoother_started = time.perf_counter()
    if args.candidate.startswith("jacobi"):
        smoother: Any = DampedJacobiSmoother(
            shifted, steps=args.smoother_steps, omega=args.jacobi_omega
        )
        subdomain_kind = "none"
    else:
        if args.candidate.startswith("layer"):
            subdomains = _complete_midpoint_groups(system, axes=(2,))
            subdomain_kind = "one_exact_mesh_layer_per_patch"
        elif args.candidate.startswith("column"):
            subdomains = _complete_midpoint_groups(system, axes=(0, 1))
            subdomain_kind = "vertical_tensor_columns"
        elif args.candidate.startswith("cell"):
            subdomains = _complete_midpoint_groups(system, axes=(0, 1, 2))
            subdomain_kind = "single_cell_patches"
        elif args.candidate.startswith("slab"):
            subdomains = _complete_physical_slabs(
                system,
                num_slabs=args.num_slabs,
                overlap_layers=args.overlap_layers,
            )
            subdomain_kind = "equal_physical_z_slabs"
        else:
            raise ValueError(f"unsupported Task030 screen candidate: {args.candidate}")
        smoother = DistributedPhysicalSlabSmoother(
            shifted,
            subdomains,
            ilu_levels=args.ilu_levels,
            local_ksp_iterations=1,
            smoother_iterations=args.inner_smoother_iterations,
            action_operator=(shifted if args.inner_smoother_iterations > 1 else None),
            interpolation=args.patch_interpolation,
            assembly_order="two_color",
        )
    smoother_setup_s = time.perf_counter() - smoother_started
    multilevel = GalerkinMultilevelPc(
        fine_operator=operator,
        transfer=transfer.matrix,
        coarse_ksp=coarse_ksp,
        smoother=smoother,
        post_smooth=args.post_smooth,
        coarse_damping=args.coarse_damping,
    )
    context: Any = multilevel
    modal_context: ModalWoodburyPc | None = None
    if args.woodbury:
        modal_context = ModalWoodburyPc(
            base_solver=multilevel,
            C=blocks.C,
            D=blocks.D,
            H=blocks.H,
        )
        context = modal_context

    solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution = operator.createVecRight()
    history: list[dict[str, Any]] = []
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(operator)
    ksp.setType("fgmres")
    ksp.setGMRESRestart(args.restart)
    ksp.setPCSide(PETSc.PC.Side.RIGHT)
    ksp.setTolerances(rtol=1.0e-12, atol=0.0, max_it=args.max_it)
    ksp.getPC().setType(PETSc.PC.Type.PYTHON)
    ksp.getPC().setPythonContext(context)
    rhs_norm = float(rhs.norm())
    solve_started = time.perf_counter()

    def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
        if iteration == 0 or iteration % args.monitor_stride == 0:
            current_solution = current.buildSolution(monitor_solution)
            row = {
                "iteration": int(iteration),
                "reported_relative_residual": float(residual_norm)
                / max(rhs_norm, np.finfo(float).tiny),
                "true_relative_residual": _linear_residual(
                    operator, rhs, current_solution
                ),
                "elapsed_s": time.perf_counter() - solve_started,
                **_rss_gb(),
            }
            history.append(row)
            _write_json(
                Path(args.record).with_name(Path(args.record).stem + "_progress.json"),
                row,
            )

    ksp.setMonitor(monitor)
    ksp.solve(rhs, solution)
    solve_s = time.perf_counter() - solve_started
    true_residual = _linear_residual(operator, rhs, solution)
    if int(ksp.getIterationNumber()) >= 100:
        classification = classify_screen_candidate(
            true_residual=true_residual,
            peak_rss_gb=_rss_gb()["peak_total_rss_gb"],
            baseline=baseline,
        )
    else:
        classification = {
            "classification": "smoke_only_not_baseline_comparable",
            "residual_ratio_to_baseline": None,
            "rss_ratio_to_baseline": None,
            "strong_positive": False,
            "memory_positive": False,
            "weak_positive": False,
            "negative": False,
        }
    result = {
        "record_type": "task030_h5_candidate_screen",
        "candidate": args.candidate,
        "woodbury": bool(args.woodbury),
        "h_nm": args.h_nm,
        "coarse_h_nm": args.coarse_h_nm,
        "mpi_size": comm.size,
        "n_fe": system.n_fe,
        "n_aux": system.n_aux,
        "max_it": args.max_it,
        "restart": args.restart,
        "ksp_reason": int(ksp.getConvergedReason()),
        "iterations": int(ksp.getIterationNumber()),
        "reported_relative_residual": float(ksp.getResidualNorm())
        / max(rhs_norm, np.finfo(float).tiny),
        "condensed_true_residual": true_residual,
        "baseline_iteration": baseline.iteration,
        "baseline_true_residual": baseline.true_relative_residual,
        "baseline_peak_rss_gb": baseline.peak_rss_gb,
        **classification,
        "absorption_shift": args.absorption_shift,
        "shift_diagonal_scale": shift_scale,
        "subdomain_kind": subdomain_kind,
        "post_smooth": args.post_smooth,
        "coarse_damping": args.coarse_damping,
        "transfer": transfer.validation,
        "coarse_inventory": coarse_metadata,
        "coarse_operator": coarse_data.diagnostics,
        "coarse_direct_setup_s": coarse_setup_s,
        "smoother_setup_s": smoother_setup_s,
        "smoother": smoother.diagnostics,
        "multilevel": multilevel.diagnostics,
        "modal_woodbury": modal_context.diagnostics if modal_context else None,
        "history": history,
        "solve_s": solve_s,
        "total_s": time.perf_counter() - started,
        "operator_apply_count": operator_context.apply_count,
        "ordinary_default_changed": False,
        **_rss_gb(),
    }
    _write_json(Path(args.record), result)
    ksp.destroy()
    if modal_context is not None:
        modal_context.destroy()
    multilevel.destroy()
    smoother.destroy()
    shifted.destroy()
    coarse_ksp.destroy()
    coarse_data.destroy()
    transfer.destroy()
    monitor_solution.destroy()
    solution.destroy()
    operator.destroy()
    rhs.destroy()
    blocks.destroy()
    del coarse_mesh_data
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Task030 low-memory multilevel H(curl) benchmark runner"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument(
        "--record", default=str(CASE_ROOT / "records" / "baseline_contract.json")
    )
    hierarchy = subparsers.add_parser("hierarchy")
    hierarchy.add_argument("--fine-h-nm", type=float, default=5.0)
    hierarchy.add_argument("--fine-degree", type=int, default=2)
    hierarchy.add_argument("--coarse-h-nm", type=float, default=10.0)
    hierarchy.add_argument("--coarse-degree", type=int, default=1)
    hierarchy.add_argument("--build-transfer", action="store_true")
    hierarchy.add_argument("--progress-stride", type=int, default=50)
    hierarchy.add_argument(
        "--artifact-root", default="benchmarks/artifacts/cases/060/hierarchy"
    )
    hierarchy.add_argument(
        "--record", default="benchmarks/artifacts/cases/060/hierarchy_contract.json"
    )
    hierarchy.add_argument(
        "--cache-dir",
        default="benchmarks/artifacts/cases/060/transfer_cache_h5p2_h10p1_mpi4",
    )
    screen = subparsers.add_parser("screen")
    screen.add_argument(
        "--candidate",
        choices=("jacobi_ph", "layer_ph", "column_ph", "cell_ph", "slab_ph"),
        required=True,
    )
    screen.add_argument("--woodbury", action="store_true")
    screen.add_argument("--h-nm", type=float, default=5.0)
    screen.add_argument("--coarse-h-nm", type=float, default=10.0)
    screen.add_argument("--max-it", type=int, default=20)
    screen.add_argument("--restart", type=int, default=100)
    screen.add_argument("--monitor-stride", type=int, default=20)
    screen.add_argument("--absorption-shift", type=float, default=0.2)
    screen.add_argument("--smoother-steps", type=int, default=4)
    screen.add_argument("--jacobi-omega", type=float, default=0.6)
    screen.add_argument("--ilu-levels", type=int, default=0)
    screen.add_argument("--inner-smoother-iterations", type=int, default=1)
    screen.add_argument("--num-slabs", type=int, default=16)
    screen.add_argument("--overlap-layers", type=float, default=0.0)
    screen.add_argument(
        "--patch-interpolation", choices=("basic", "partition"), default="partition"
    )
    screen.add_argument(
        "--post-smooth", action=argparse.BooleanOptionalAction, default=True
    )
    screen.add_argument("--coarse-damping", type=float, default=1.0)
    screen.add_argument(
        "--cache-dir",
        default="benchmarks/artifacts/cases/060/transfer_cache_h5p2_h10p1_mpi4",
    )
    screen.add_argument(
        "--artifact-root", default="benchmarks/artifacts/cases/060/screens"
    )
    screen.add_argument("--record", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.command == "baseline":
        result = _run_baseline(config, args)
    elif args.command == "hierarchy":
        result = _run_hierarchy(config, args)
    else:
        result = _run_screen(config, args)
    if MPI.COMM_WORLD.rank == 0:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "screen":
        return 0
    return 0 if result.get("status") in {"passed", "inventory_only"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
