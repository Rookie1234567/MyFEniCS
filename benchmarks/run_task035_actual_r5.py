from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
    _source_provenance,
    _stage_peaks,
)
from benchmarks.task034_wsl_resources import effective_memory_limit
from src.solvers.solve_vector_maxwell import _json_default


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/task035/actual_global_r5"
GIB = 1024**3


def _parse_theta_schedule(value: str) -> tuple[float, ...]:
    try:
        schedule = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "theta schedule must be comma-separated floating-point values"
        ) from exc
    if not schedule or any(not 0.0 < item <= 1.0 for item in schedule):
        raise argparse.ArgumentTypeError(
            "every theta schedule value must lie in (0, 1]"
        )
    return schedule


def _parse_grazing_angles(value: str) -> tuple[float, ...]:
    try:
        angles = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "grazing angles must be comma-separated floating-point values"
        ) from exc
    if (
        not angles
        or any(not 0.0 < item < 90.0 for item in angles)
        or len(set(angles)) != len(angles)
    ):
        raise argparse.ArgumentTypeError("grazing angles must be unique and in (0, 90)")
    return angles


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_from_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _memory_snapshot() -> dict[str, Any]:
    effective = effective_memory_limit()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "effective_limit": effective,
        "artifact_filesystem_free_bytes": shutil.disk_usage(
            DEFAULT_ARTIFACT_ROOT.parent
        ).free,
    }


def _append_progress(path: Path, stage: str, status: str) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _worker(args: argparse.Namespace) -> int:
    progress_path = args.run_dir / "progress_3d.jsonl"

    def progress(stage: str, status: str) -> None:
        _append_progress(progress_path, stage, status)

    if args.common_mesh_replay_record is not None:
        from src.adaptivity.target_common_mesh_angle_sweep import (
            run_target_common_mesh_angle_sweep,
        )

        result = run_target_common_mesh_angle_sweep(
            args.run_dir,
            replay_record=args.common_mesh_replay_record,
            replay_record_sha256=args.common_mesh_replay_sha256,
            grazing_angles_deg=args.common_mesh_grazing_angles,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            progress_observer=progress,
            replay_expected_theta=args.common_mesh_replay_theta,
            replay_expected_final_cells=args.common_mesh_replay_expected_final_cells,
            dof_ceiling=args.hp_dof_ceiling,
            accuracy_control_key=args.hp_accuracy_control_key,
        )
    elif args.dwr_adaptive_cycles:
        from src.adaptivity.target_dwr_adaptive_cycles import (
            run_target_dwr_adaptive_cycles,
        )

        result = run_target_dwr_adaptive_cycles(
            args.run_dir,
            marked_cycles=args.dwr_adaptive_cycles,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            theta_schedule=args.theta_schedule,
            polarization_kind=args.polarization_kind,
            marker_policy=args.dwr_marker_policy,
            full_boundary_synchronization=(
                not args.minimal_periodic_edge_closure
            ),
            progress_observer=progress,
        )
    elif args.uniform_refinement_levels:
        from src.adaptivity.target_uniform_tetra_control import (
            run_target_uniform_tetra_control,
        )

        result = run_target_uniform_tetra_control(
            args.run_dir,
            refinement_levels=args.uniform_refinement_levels,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            initial_h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            progress_observer=progress,
        )
    elif args.adaptive_marked_cycles:
        from src.adaptivity.target_r5_adaptive_cycles import (
            run_target_r5_adaptive_cycles,
        )

        result = run_target_r5_adaptive_cycles(
            args.run_dir,
            marked_cycles=args.adaptive_marked_cycles,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            progress_observer=progress,
        )
    else:
        from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5

        result = run_target_global_two_level_r5(
            args.run_dir,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            mesh_cell_type=args.mesh_cell_type,
            progress_observer=progress,
        )
    if MPI.COMM_WORLD.rank == 0:
        (args.run_dir / "actual_r5_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
    MPI.COMM_WORLD.barrier()
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task035 actual global two-level R5 target watchdog."
    )
    parser.add_argument("--coarse-degree", type=int, default=2)
    parser.add_argument("--enriched-degree", type=int, default=3)
    parser.add_argument("--h-nm", type=float, default=10.0)
    parser.add_argument("--theta", type=float, default=0.5)
    parser.add_argument("--polarization-kind", choices=("s", "p"), default="s")
    parser.add_argument(
        "--mesh-cell-type",
        choices=("hexahedron", "tetrahedron"),
        default="hexahedron",
    )
    parser.add_argument("--mpi-size", type=int, default=8)
    parser.add_argument("--adaptive-marked-cycles", type=int, default=0)
    parser.add_argument("--uniform-refinement-levels", type=int, default=0)
    parser.add_argument("--dwr-adaptive-cycles", type=int, default=0)
    parser.add_argument(
        "--dwr-marker-policy",
        choices=("combined_relative_R_T", "R_total", "T_total"),
        default="combined_relative_R_T",
    )
    parser.add_argument(
        "--minimal-periodic-edge-closure",
        action="store_true",
        help="research-only DWR refinement without the full periodic boundary sleeve",
    )
    parser.add_argument(
        "--theta-schedule",
        type=_parse_theta_schedule,
        help=("comma-separated DWR theta values; exactly one per marked cycle"),
    )
    parser.add_argument(
        "--common-mesh-replay-record",
        type=Path,
        help="accepted theta=0.7 DWR record whose marker deterministically rebuilds the mesh",
    )
    parser.add_argument(
        "--common-mesh-replay-sha256",
        help="required SHA256 authority for --common-mesh-replay-record",
    )
    parser.add_argument(
        "--common-mesh-grazing-angles",
        type=_parse_grazing_angles,
        default=(1.0, 5.0, 10.0),
        help="comma-separated grazing angles solved on the one replayed mesh",
    )
    parser.add_argument(
        "--common-mesh-replay-theta", type=float, default=0.7,
        help="DWR theta bound into the replay authority",
    )
    parser.add_argument(
        "--common-mesh-replay-expected-final-cells", type=int, default=1316,
        help="exact final global cell count bound into the replay authority",
    )
    parser.add_argument(
        "--hp-dof-ceiling", type=int,
        help="optional hard DoF ceiling for the enriched 10-degree candidate",
    )
    parser.add_argument(
        "--hp-accuracy-control-key",
        choices=("p4_h7p5",),
        help="qualified Task034 accuracy control for the enriched candidate",
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float)
    parser.add_argument("--terminate-gib", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK035_VERIFIED_CLEAN_SHA"),
    )
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(argv)
    if args.mpi_size < 1:
        parser.error("--mpi-size must be positive.")
    if args.coarse_degree < 1 or args.enriched_degree <= args.coarse_degree:
        parser.error("require 1 <= coarse-degree < enriched-degree.")
    if args.h_nm <= 0.0:
        parser.error("--h-nm must be positive.")
    if not 0.0 < args.theta <= 1.0:
        parser.error("--theta must lie in (0, 1].")
    if args.poll_interval < 0.05:
        parser.error("--poll-interval must be at least 0.05 seconds.")
    if args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be positive.")
    if args.adaptive_marked_cycles < 0:
        parser.error("--adaptive-marked-cycles must be non-negative.")
    if args.uniform_refinement_levels < 0:
        parser.error("--uniform-refinement-levels must be non-negative.")
    if args.dwr_adaptive_cycles < 0:
        parser.error("--dwr-adaptive-cycles must be non-negative.")
    active_cycles = sum(
        bool(value)
        for value in (
            args.adaptive_marked_cycles,
            args.uniform_refinement_levels,
            args.dwr_adaptive_cycles,
        )
    )
    if active_cycles > 1:
        parser.error(
            "R5 adaptive, DWR adaptive, and uniform control are mutually exclusive."
        )
    common_mesh_mode = args.common_mesh_replay_record is not None
    if common_mesh_mode != (args.common_mesh_replay_sha256 is not None):
        parser.error(
            "--common-mesh-replay-record and --common-mesh-replay-sha256 "
            "must be provided together."
        )
    if common_mesh_mode and active_cycles:
        parser.error(
            "common-mesh replay and adaptive/uniform cycle modes are mutually exclusive."
        )
    if args.theta_schedule is not None:
        if not args.dwr_adaptive_cycles:
            parser.error("--theta-schedule is valid only with --dwr-adaptive-cycles.")
        if len(args.theta_schedule) != args.dwr_adaptive_cycles:
            parser.error(
                "--theta-schedule must contain exactly one value per DWR marked cycle."
            )
    if args.minimal_periodic_edge_closure and not args.dwr_adaptive_cycles:
        parser.error(
            "--minimal-periodic-edge-closure requires --dwr-adaptive-cycles."
        )
    if (active_cycles or common_mesh_mode) and args.mesh_cell_type != "tetrahedron":
        parser.error(
            "adaptive/uniform refinement requires --mesh-cell-type tetrahedron."
        )
    if not 0.0 < args.common_mesh_replay_theta <= 1.0:
        parser.error("--common-mesh-replay-theta must lie in (0, 1].")
    if args.common_mesh_replay_expected_final_cells < 1:
        parser.error(
            "--common-mesh-replay-expected-final-cells must be positive."
        )
    hp_budget_mode = args.hp_dof_ceiling is not None
    if hp_budget_mode != (args.hp_accuracy_control_key is not None):
        parser.error(
            "--hp-dof-ceiling and --hp-accuracy-control-key must be provided together."
        )
    if hp_budget_mode:
        if args.hp_dof_ceiling < 1:
            parser.error("--hp-dof-ceiling must be positive.")
        if not common_mesh_mode:
            parser.error("hp budget evaluation requires common-mesh replay mode.")
        if args.common_mesh_grazing_angles != (10.0,):
            parser.error(
                "hp budget evaluation requires exactly --common-mesh-grazing-angles 10."
            )
    return args


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=15)


def _sampler_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(name: str) -> float | None:
        values = [
            float(row[name]) for row in rows if isinstance(row.get(name), (int, float))
        ]
        return max(values) if values else None

    process_tree = maximum("mpi_process_tree_rss_mb")
    process_swap = maximum("mpi_process_tree_swap_mb")
    worker_counts = []
    for row in rows:
        try:
            workers = json.loads(str(row.get("worker_rank_rss_mb_json", "[]")))
        except json.JSONDecodeError:
            continue
        if isinstance(workers, list):
            worker_counts.append(len(workers))
    return {
        "sample_count": len(rows),
        "max_process_tree_rss_mb": process_tree,
        "max_process_tree_swap_mb": process_swap,
        "memory_authority_gib": (
            None if process_tree is None else process_tree / 1024.0
        ),
        "max_observed_worker_rank_count": max(worker_counts, default=0),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _compact_solve(entry: dict[str, Any]) -> dict[str, Any]:
    summary = entry["summary"]
    return {
        "degree": entry["degree"],
        "h_nm": entry["h_nm"],
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "mpi_size": summary.get("mpi_size"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "mesh_cell_type_actual": summary.get("mesh_cell_type_actual"),
        "num_nedelec_dofs": summary.get("num_nedelec_dofs"),
        "matrix_stats": summary.get("matrix_stats"),
        "linear_system_relative_residual": summary.get(
            "linear_system_relative_residual"
        ),
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_volume_total": summary.get("A_volume_total"),
        "energy_closure_error_port_volume": summary.get(
            "energy_closure_error_port_volume"
        ),
        "floquet_num_constraints": summary.get("floquet_num_constraints"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
    }


def _compact_adaptive_cycle(entry: dict[str, Any]) -> dict[str, Any]:
    actual = entry["actual_r5"]
    return {
        "cycle_index": entry["cycle_index"],
        "mesh_audit": entry["mesh_audit"],
        "coarse_observables": entry["coarse_observables"],
        "enriched_observables": entry["enriched_observables"],
        "official_observable_delta_l2": entry["official_observable_delta_l2"],
        "coarse_fixed_reference_error_l2": entry["coarse_fixed_reference_error_l2"],
        "enriched_fixed_reference_error_l2": entry["enriched_fixed_reference_error_l2"],
        "coarse": _compact_solve(actual["coarse"]),
        "enriched": _compact_solve(actual["enriched"]),
        "R5": actual["R5"],
        "elapsed_seconds": actual["elapsed_seconds"],
    }


def _compact_dwr_cycle(entry: dict[str, Any]) -> dict[str, Any]:
    result = entry["goal_dwr"]
    return {
        "cycle_index": entry["cycle_index"],
        "theta": entry.get("theta"),
        "mesh_audit": entry["mesh_audit"],
        "coarse_observables": entry["coarse_observables"],
        "enriched_observables": entry["enriched_observables"],
        "official_observable_delta_l2": entry["official_observable_delta_l2"],
        "coarse_fixed_reference_error_l2": entry["coarse_fixed_reference_error_l2"],
        "enriched_fixed_reference_error_l2": entry["enriched_fixed_reference_error_l2"],
        "marker": entry["marker"],
        "coarse": _compact_solve(result["coarse"]),
        "enriched": _compact_solve(result["enriched"]),
        "DWR": result["DWR"],
        "R5_control": result["R5_control"],
    }


def _compact_common_mesh_angle(entry: dict[str, Any]) -> dict[str, Any]:
    pair = entry["actual_r5_pair"]
    return {
        "grazing_angle_deg": entry["grazing_angle_deg"],
        "incident_theta_deg": entry["incident_theta_deg"],
        "target_identity": pair["target_identity"],
        "coarse": _compact_solve(pair["coarse"]),
        "enriched": _compact_solve(pair["enriched"]),
        "official_observable_delta_l2": pair["official_observable_delta_l2"],
        "R5": pair["R5"],
        "elapsed_seconds": pair["elapsed_seconds"],
        "ordinary_default_changed": pair["ordinary_default_changed"],
    }


def _qualify(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    r5 = result.get("R5") or {}
    energy = r5.get("correction_energy") or {}
    marking = r5.get("marking") or {}
    solves = [result.get("coarse") or {}, result.get("enriched") or {}]
    summaries = [entry.get("summary") or {} for entry in solves]
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_global_r5_pass",
        "formal_hierarchical_fe_r5": r5.get("formal_hierarchical_fe_r5") is True,
        "finite_cell_contributions": r5.get("finite_cell_contributions") is True,
        "nonnegative_cell_contributions": (
            r5.get("nonnegative_cell_contributions") is True
        ),
        "positive_correction_energy": (
            isinstance(r5.get("correction_energy_norm"), (int, float))
            and float(r5["correction_energy_norm"]) > 0.0
        ),
        "cell_energy_closure_le_1e-10": (
            isinstance(energy.get("relative_closure_error"), (int, float))
            and float(energy["relative_closure_error"]) <= 1.0e-10
        ),
        "dorfler_target_captured": (
            isinstance(marking.get("captured_fraction"), (int, float))
            and float(marking["captured_fraction"]) >= args.theta
        ),
        "both_official_solves": all(
            summary.get("official_result") is True for summary in summaries
        ),
        "requested_mesh_backend_used": all(
            summary.get("mesh_cell_type_actual") == args.mesh_cell_type
            for summary in summaries
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in summaries
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_adaptive(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    cycles = result.get("cycles") or []
    refinements = result.get("refinements") or []
    solves = [
        cycle["actual_r5"][level]["summary"]
        for cycle in cycles
        for level in ("coarse", "enriched")
    ]
    estimates = [cycle["actual_r5"]["R5"] for cycle in cycles]
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_r5_adaptive_cycles_pass",
        "result_pass": result.get("pass") is True,
        "requested_cycle_count_completed": (
            result.get("marked_cycles_completed") == args.adaptive_marked_cycles
            and len(cycles) == args.adaptive_marked_cycles + 1
        ),
        "fixed_reference_identity": (
            (result.get("fixed_observable_reference") or {}).get("identity")
            == "best_available_discrete_reference_for_case093"
        ),
        "fixed_reference_hash_bound": (
            (result.get("fixed_observable_reference") or {}).get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
        ),
        "all_fixed_reference_error_reductions_positive": (
            result.get("all_fixed_reference_error_reductions_positive") is True
        ),
        "all_refinement_audits_pass": bool(refinements)
        and all(entry.get("pass") is True for entry in refinements),
        "all_cycle_mesh_audits_pass": bool(cycles)
        and all(cycle["mesh_audit"].get("pass") is True for cycle in cycles),
        "all_official_solves": bool(solves)
        and all(summary.get("official_result") is True for summary in solves),
        "all_true_residuals_le_1e-9": bool(solves)
        and all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in solves
        ),
        "all_tetra_meshes": bool(solves)
        and all(
            summary.get("mesh_cell_type_actual") == "tetrahedron" for summary in solves
        ),
        "all_r5_energy_closures_le_1e-10": bool(estimates)
        and all(
            estimate["correction_energy"]["relative_closure_error"] <= 1.0e-10
            for estimate in estimates
        ),
        "all_dorfler_targets_captured": bool(estimates)
        and all(
            estimate["marking"]["captured_fraction"] >= args.theta
            for estimate in estimates
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_dwr_adaptive(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    cycles = result.get("cycles") or []
    refinements = result.get("refinements") or []
    solves = [
        cycle["goal_dwr"][level]["summary"]
        for cycle in cycles
        for level in ("coarse", "enriched")
    ]
    dwr_reports = [cycle["goal_dwr"]["DWR"] for cycle in cycles]
    goal_reports = [
        report["goals"][goal]
        for report in dwr_reports
        for goal in ("R_total", "T_total")
    ]
    marker_reports = [
        report["combined_relative_R_T"]
        if args.dwr_marker_policy == "combined_relative_R_T"
        else report["goals"][args.dwr_marker_policy]
        for report in dwr_reports
    ]
    requested_theta_schedule = tuple(
        args.theta_schedule or (float(args.theta),) * int(args.dwr_adaptive_cycles)
    )
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_dwr_adaptive_cycles_pass",
        "result_pass": result.get("pass") is True,
        "requested_cycle_count_completed": (
            result.get("marked_cycles_completed") == args.dwr_adaptive_cycles
            and len(cycles) == args.dwr_adaptive_cycles + 1
        ),
        "requested_marker_policy": result.get("marker_policy")
        == args.dwr_marker_policy,
        "requested_periodic_edge_closure_policy": result.get(
            "periodic_edge_closure_policy"
        )
        == (
            "minimal_periodic_mates_only"
            if getattr(args, "minimal_periodic_edge_closure", False)
            else "full_periodic_boundary_synchronization"
        ),
        "requested_theta_schedule": tuple(
            float(value) for value in result.get("theta_schedule", [])
        )
        == requested_theta_schedule,
        "all_cycle_theta_values_bound": bool(cycles)
        and all(isinstance(cycle.get("theta"), (int, float)) for cycle in cycles),
        "fixed_reference_identity": (
            (result.get("fixed_observable_reference") or {}).get("identity")
            == "best_available_discrete_reference_for_case093"
        ),
        "fixed_reference_hash_bound": (
            (result.get("fixed_observable_reference") or {}).get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
        ),
        "all_fixed_reference_error_reductions_positive": result.get(
            "all_fixed_reference_error_reductions_positive"
        )
        is True,
        "all_refinement_audits_pass": bool(refinements)
        and all(entry.get("pass") is True for entry in refinements),
        "all_cycle_mesh_audits_pass": bool(cycles)
        and all(cycle["mesh_audit"].get("pass") is True for cycle in cycles),
        "all_official_solves": bool(solves)
        and all(summary.get("official_result") is True for summary in solves),
        "all_true_residuals_le_1e-9": bool(solves)
        and all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in solves
        ),
        "all_tetra_meshes": bool(solves)
        and all(
            summary.get("mesh_cell_type_actual") == "tetrahedron" for summary in solves
        ),
        "all_actual_adjoint_qualifications_pass": bool(dwr_reports)
        and all(report["adjoint_qualification"]["pass"] for report in dwr_reports),
        "all_goal_effectivities_unity": bool(goal_reports)
        and all(
            abs(report["absolute_effectivity"] - 1.0) <= 1.0e-8
            for report in goal_reports
        ),
        "all_goal_marking_geometry_hashes_present": bool(goal_reports)
        and all(bool(report.get("marked_geometry_sha256")) for report in goal_reports),
        "all_selected_marker_geometry_hashes_match": bool(cycles)
        and all(
            bool(cycle["marker"].get("marked_geometry_sha256"))
            and cycle["marker"]["marked_geometry_sha256"]
            == report.get("marked_geometry_sha256")
            for cycle, report in zip(cycles, marker_reports, strict=True)
        ),
        "all_selected_marker_counts_match": bool(cycles)
        and all(
            cycle["marker"].get("marked_count", 0) > 0
            and cycle["marker"]["marked_count"] == report["marking"].get("count")
            for cycle, report in zip(cycles, marker_reports, strict=True)
        ),
        "all_dorfler_targets_captured": bool(marker_reports)
        and all(
            report["marking"]["captured_fraction"] >= float(cycle["theta"])
            for report, cycle in zip(marker_reports, cycles, strict=True)
        ),
        "algebraic_localization_rejected": bool(dwr_reports)
        and all(
            report["rejected_localization"]["decision"]
            == "controlled_negative_partition_dependent"
            for report in dwr_reports
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_uniform(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    refinements = result.get("refinements") or []
    pair = result.get("actual_r5_pair") or {}
    solves = [
        (pair.get(level) or {}).get("summary") or {} for level in ("coarse", "enriched")
    ]
    r5 = pair.get("R5") or {}
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_uniform_tetra_control_pass",
        "result_pass": result.get("pass") is True,
        "requested_uniform_levels_completed": (
            result.get("refinement_levels") == args.uniform_refinement_levels
            and len(refinements) == args.uniform_refinement_levels
        ),
        "all_parent_cells_uniformly_marked": bool(refinements)
        and all(
            entry.get("uniform_all_parent_cells_marked") is True
            for entry in refinements
        ),
        "all_refinement_audits_pass": bool(refinements)
        and all(entry.get("pass") is True for entry in refinements),
        "final_mesh_audit_pass": (result.get("final_mesh_audit") or {}).get("pass")
        is True,
        "fixed_reference_identity": (
            (result.get("fixed_observable_reference") or {}).get("identity")
            == "best_available_discrete_reference_for_case093"
        ),
        "fixed_reference_hash_bound": (
            (result.get("fixed_observable_reference") or {}).get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
        ),
        "both_official_solves": all(
            summary.get("official_result") is True for summary in solves
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in solves
        ),
        "both_tetra_meshes": all(
            summary.get("mesh_cell_type_actual") == "tetrahedron" for summary in solves
        ),
        "r5_energy_closure_le_1e-10": (
            (r5.get("correction_energy") or {}).get("relative_closure_error", 1.0)
            <= 1.0e-10
        ),
        "dorfler_target_captured": (
            (r5.get("marking") or {}).get("captured_fraction", 0.0) >= args.theta
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_common_mesh_sweep(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    angles = result.get("angle_results") or []
    replay = result.get("mesh_replay") or {}
    contract = replay.get("contract") or {}
    pairs = [entry.get("actual_r5_pair") or {} for entry in angles]
    summaries = [
        (pair.get(level) or {}).get("summary") or {}
        for pair in pairs
        for level in ("coarse", "enriched")
    ]
    requested = [float(value) for value in args.common_mesh_grazing_angles]
    hp_budget = result.get("hp_budget_evaluation")
    hp_budget_requested = getattr(args, "hp_dof_ceiling", None) is not None
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status")
        == "actual_common_mesh_angle_sweep_pass",
        "result_pass": result.get("pass") is True,
        "replay_pass": replay.get("pass") is True,
        "replay_record_hash_bound": (
            contract.get("record_sha256") == args.common_mesh_replay_sha256
        ),
        "replay_theta_bound": (
            contract.get("theta")
            == getattr(args, "common_mesh_replay_theta", 0.7)
        ),
        "replay_final_cell_count_bound": (
            (contract.get("final_mesh_identity") or {}).get("global_cell_count")
            == getattr(args, "common_mesh_replay_expected_final_cells", 1316)
        ),
        "single_in_memory_mesh_instance": (
            result.get("single_in_memory_mesh_instance") is True
            and replay.get("single_in_memory_mesh_instance") is True
        ),
        "requested_angles_completed": (
            [entry.get("grazing_angle_deg") for entry in angles] == requested
        ),
        "all_pairs_pass": bool(pairs)
        and all(pair.get("status") == "actual_global_r5_pass" for pair in pairs),
        "angle_identities_exact": bool(angles)
        and all(
            (pair.get("target_identity") or {}).get("grazing_angle_deg")
            == entry.get("grazing_angle_deg")
            and (pair.get("target_identity") or {}).get("incidence_theta_deg")
            == entry.get("incident_theta_deg")
            for entry, pair in zip(angles, pairs, strict=True)
        ),
        "all_official_solves": bool(summaries)
        and all(summary.get("official_result") is True for summary in summaries),
        "all_true_residuals_le_1e-9": bool(summaries)
        and all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in summaries
        ),
        "all_tetra_meshes": bool(summaries)
        and all(
            summary.get("mesh_cell_type_actual") == "tetrahedron"
            for summary in summaries
        ),
        "all_r5_energy_closures_le_1e-10": bool(pairs)
        and all(
            ((pair.get("R5") or {}).get("correction_energy") or {}).get(
                "relative_closure_error", 1.0
            )
            <= 1.0e-10
            for pair in pairs
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
            and all(pair.get("ordinary_default_changed") is False for pair in pairs)
        ),
    }
    if hp_budget_requested:
        checks.update(
            {
                "hp_budget_evaluation_present": isinstance(hp_budget, dict),
                "hp_dof_ceiling_bound": (
                    isinstance(hp_budget, dict)
                    and hp_budget.get("dof_ceiling") == args.hp_dof_ceiling
                ),
                "hp_accuracy_control_bound": (
                    isinstance(hp_budget, dict)
                    and (hp_budget.get("accuracy_control") or {}).get("key")
                    == args.hp_accuracy_control_key
                ),
                "hp_thresholds_not_relaxed": (
                    isinstance(hp_budget, dict)
                    and hp_budget.get("thresholds_relaxed") is False
                ),
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _run_parent(args: argparse.Namespace) -> int:
    effective = effective_memory_limit()
    if effective["effective_limit_bytes"] is None:
        raise SystemExit("Task035 effective WSL memory limit is unreadable.")
    if args.warning_gib is None:
        args.warning_gib = float(effective["warning_bytes"]) / GIB
    if args.terminate_gib is None:
        args.terminate_gib = float(effective["termination_bytes"]) / GIB
    if not 0.0 < args.warning_gib < args.terminate_gib:
        raise SystemExit("Require 0 < warning-gib < terminate-gib.")
    source_before = _source_provenance(args)
    preflight = _memory_snapshot()
    free_bytes = preflight["artifact_filesystem_free_bytes"]
    if free_bytes < 10 * GIB:
        raise SystemExit(
            "Task035 actual R5 requires at least 10 GiB free artifact space."
        )
    if args.common_mesh_replay_record is not None:
        replay_path = args.common_mesh_replay_record
        if not replay_path.is_absolute():
            replay_path = ROOT / replay_path
        if not replay_path.is_file():
            raise SystemExit(f"common-mesh replay record not found: {replay_path}")
        args.common_mesh_replay_record = replay_path.resolve()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_label = (
        f"{args.mesh_cell_type}_p{args.coarse_degree}_"
        f"p{args.enriched_degree}_h{args.h_nm:g}_"
        f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
    )
    if args.common_mesh_replay_record is not None:
        angle_label = "-".join(
            f"{value:g}" for value in args.common_mesh_grazing_angles
        )
        run_label += (
            f"_common_mesh_theta{args.common_mesh_replay_theta:g}_grazing{angle_label}"
        )
    elif args.dwr_adaptive_cycles:
        run_label += f"_dwr_{args.dwr_marker_policy}_{args.dwr_adaptive_cycles}"
        if args.minimal_periodic_edge_closure:
            run_label += "_minimal_periodic_edge_closure"
        if args.theta_schedule is not None:
            schedule_label = "-".join(f"{value:g}" for value in args.theta_schedule)
            run_label += f"_theta{schedule_label}"
    elif args.adaptive_marked_cycles:
        run_label += f"_adaptive{args.adaptive_marked_cycles}"
    elif args.uniform_refinement_levels:
        run_label += f"_uniform{args.uniform_refinement_levels}"
    run_dir = (args.run_dir or args.artifact_root / run_label).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    args.run_dir = run_dir
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    result_path = run_dir / "actual_r5_result.json"
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task035_actual_r5",
        "--worker",
        "--coarse-degree",
        str(args.coarse_degree),
        "--enriched-degree",
        str(args.enriched_degree),
        "--h-nm",
        str(args.h_nm),
        "--theta",
        str(args.theta),
        "--polarization-kind",
        args.polarization_kind,
        "--mesh-cell-type",
        args.mesh_cell_type,
        "--run-dir",
        str(run_dir),
    ]
    if args.common_mesh_replay_record is not None:
        command.extend(
            [
                "--common-mesh-replay-record",
                str(args.common_mesh_replay_record),
                "--common-mesh-replay-sha256",
                args.common_mesh_replay_sha256,
                "--common-mesh-grazing-angles",
                ",".join(
                    f"{value:g}" for value in args.common_mesh_grazing_angles
                ),
                "--common-mesh-replay-theta",
                str(args.common_mesh_replay_theta),
                "--common-mesh-replay-expected-final-cells",
                str(args.common_mesh_replay_expected_final_cells),
            ]
        )
        if args.hp_dof_ceiling is not None:
            command.extend(["--hp-dof-ceiling", str(args.hp_dof_ceiling)])
            command.extend(["--hp-accuracy-control-key", args.hp_accuracy_control_key])
    elif args.dwr_adaptive_cycles:
        command.extend(
            [
                "--dwr-adaptive-cycles",
                str(args.dwr_adaptive_cycles),
                "--dwr-marker-policy",
                args.dwr_marker_policy,
            ]
        )
        if args.minimal_periodic_edge_closure:
            command.append("--minimal-periodic-edge-closure")
        if args.theta_schedule is not None:
            command.extend(
                [
                    "--theta-schedule",
                    ",".join(f"{value:g}" for value in args.theta_schedule),
                ]
            )
    elif args.adaptive_marked_cycles:
        command.extend(["--adaptive-marked-cycles", str(args.adaptive_marked_cycles)])
    elif args.uniform_refinement_levels:
        command.extend(
            ["--uniform-refinement-levels", str(args.uniform_refinement_levels)]
        )
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    authority_readable = True
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            rss_mb = row.get("mpi_process_tree_rss_mb")
            swap_mb = row.get("mpi_process_tree_swap_mb")
            readable = isinstance(rss_mb, (int, float)) and isinstance(
                swap_mb, (int, float)
            )
            authority_readable &= readable
            rss_gib = None if not readable else float(rss_mb) / 1024.0
            if rss_gib is not None:
                warning_triggered |= rss_gib >= args.warning_gib
            if process.poll() is None and not readable:
                _terminate_process_group(process)
            elif (
                process.poll() is None
                and rss_gib is not None
                and rss_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                _terminate_process_group(process)
            elif process.poll() is None and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                _terminate_process_group(process)
            if process.poll() is not None:
                break
            time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {}
    )
    sampler = _sampler_summary(rows)
    if args.common_mesh_replay_record is not None:
        qualifier = _qualify_common_mesh_sweep
    elif args.dwr_adaptive_cycles:
        qualifier = _qualify_dwr_adaptive
    elif args.adaptive_marked_cycles:
        qualifier = _qualify_adaptive
    elif args.uniform_refinement_levels:
        qualifier = _qualify_uniform
    else:
        qualifier = _qualify
    qualification = qualifier(
        result,
        args=args,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        authority_readable=authority_readable,
        sampler=sampler,
    )
    head_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status_after = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    source_stable = head_after == source_before["commit_sha"] and not status_after
    qualification["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        qualification["failures"].append("source_stable_and_clean_after")
        qualification["pass"] = False
    if qualification["pass"]:
        status = (
            "actual_common_mesh_angle_sweep_pass"
            if args.common_mesh_replay_record is not None
            else "actual_dwr_adaptive_cycles_pass"
            if args.dwr_adaptive_cycles
            else "actual_r5_adaptive_cycles_pass"
            if args.adaptive_marked_cycles
            else "actual_uniform_tetra_control_pass"
            if args.uniform_refinement_levels
            else "actual_global_r5_pass"
        )
    else:
        status = "formal_not_pass"
    record = {
        "schema_version": (
            "task035.actual-common-mesh-angle-sweep-watchdog.v1"
            if args.common_mesh_replay_record is not None
            else "task035.actual-dwr-adaptive-watchdog.v1"
            if args.dwr_adaptive_cycles
            else "task035.actual-r5-adaptive-watchdog.v1"
            if args.adaptive_marked_cycles
            else "task035.actual-uniform-tetra-watchdog.v1"
            if args.uniform_refinement_levels
            else "task035.actual-global-r5-watchdog.v1"
        ),
        "benchmark_id": (
            "task035_target_actual_common_mesh_angle_sweep"
            if args.common_mesh_replay_record is not None
            else "task035_target_actual_dwr_adaptive_cycles"
            if args.dwr_adaptive_cycles
            else "task035_target_actual_r5_adaptive_cycles"
            if args.adaptive_marked_cycles
            else "task035_target_actual_uniform_tetra_control"
            if args.uniform_refinement_levels
            else "task035_target_actual_global_r5"
        ),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "command": command,
        "source": {
            **source_before,
            "head_after_sha": head_after,
            "status_after_before_record_write": status_after,
            "stable_and_clean_after": source_stable,
        },
        "resource_preflight": preflight,
        "resource_policy": {
            "one_heavy_case_at_a_time": True,
            "warning_gib": args.warning_gib,
            "termination_gib": args.terminate_gib,
            "timeout_seconds": args.timeout_seconds,
            "swap_allowed": False,
            "termination_scope": "complete_process_group",
        },
        "resource_authority": sampler,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "qualification": qualification,
        "target_identity": result.get("target_identity") if result else None,
        "coarse": (
            None
            if args.common_mesh_replay_record is not None
            or args.dwr_adaptive_cycles
            or args.adaptive_marked_cycles
            or args.uniform_refinement_levels
            or not result
            else _compact_solve(result["coarse"])
        ),
        "enriched": (
            None
            if args.common_mesh_replay_record is not None
            or args.dwr_adaptive_cycles
            or args.adaptive_marked_cycles
            or args.uniform_refinement_levels
            or not result
            else _compact_solve(result["enriched"])
        ),
        "official_observable_delta_l2": result.get("official_observable_delta_l2"),
        "R5": result.get("R5"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "actual_r5_result": _path_from_root(result_path),
            "actual_r5_result_sha256": _sha256(result_path),
            "memory_timeline": _path_from_root(timeline_path),
            "memory_timeline_sha256": _sha256(timeline_path),
            "progress": _path_from_root(progress_path),
            "progress_sha256": _sha256(progress_path),
            "stdout": _path_from_root(stdout_path),
            "stdout_sha256": _sha256(stdout_path),
        },
    }
    if args.common_mesh_replay_record is not None:
        record.update(
            {
                "common_mesh_replay": result.get("mesh_replay"),
                "hp_budget_evaluation": result.get("hp_budget_evaluation"),
                "common_mesh_identity": result.get("common_mesh_identity"),
                "single_in_memory_mesh_instance": result.get(
                    "single_in_memory_mesh_instance"
                ),
                "angle_results": [
                    _compact_common_mesh_angle(entry)
                    for entry in result.get("angle_results", [])
                ],
            }
        )
    elif args.dwr_adaptive_cycles:
        record.update(
            {
                "dwr_marker_policy": result.get("marker_policy"),
                "periodic_edge_closure_policy": result.get(
                    "periodic_edge_closure_policy"
                ),
                "theta_schedule": result.get("theta_schedule"),
                "marked_cycles_requested": result.get("marked_cycles_requested"),
                "marked_cycles_completed": result.get("marked_cycles_completed"),
                "fixed_observable_reference": result.get("fixed_observable_reference"),
                "initial_mesh_audit": result.get("initial_mesh_audit"),
                "cycles": [
                    _compact_dwr_cycle(entry) for entry in result.get("cycles", [])
                ],
                "refinements": result.get("refinements"),
                "observable_error_reductions": result.get(
                    "observable_error_reductions"
                ),
                "all_fixed_reference_error_reductions_positive": result.get(
                    "all_fixed_reference_error_reductions_positive"
                ),
                "internal_p_gap_is_gate": result.get("internal_p_gap_is_gate"),
            }
        )
    elif args.adaptive_marked_cycles:
        record.update(
            {
                "marked_cycles_requested": result.get("marked_cycles_requested"),
                "marked_cycles_completed": result.get("marked_cycles_completed"),
                "fixed_observable_reference": result.get("fixed_observable_reference"),
                "initial_mesh_audit": result.get("initial_mesh_audit"),
                "cycles": [
                    _compact_adaptive_cycle(entry) for entry in result.get("cycles", [])
                ],
                "refinements": result.get("refinements"),
                "observable_error_reductions": result.get(
                    "observable_error_reductions"
                ),
                "all_fixed_reference_error_reductions_positive": (
                    result.get("all_fixed_reference_error_reductions_positive")
                ),
                "internal_p_gap_is_gate": result.get("internal_p_gap_is_gate"),
            }
        )
    elif args.uniform_refinement_levels:
        pair = result.get("actual_r5_pair") or {}
        record.update(
            {
                "uniform_refinement_levels": result.get("refinement_levels"),
                "initial_mesh_audit": result.get("initial_mesh_audit"),
                "refinements": result.get("refinements"),
                "final_mesh_audit": result.get("final_mesh_audit"),
                "fixed_observable_reference": result.get("fixed_observable_reference"),
                "coarse_observables": result.get("coarse_observables"),
                "enriched_observables": result.get("enriched_observables"),
                "coarse_fixed_reference_error_l2": result.get(
                    "coarse_fixed_reference_error_l2"
                ),
                "enriched_fixed_reference_error_l2": result.get(
                    "enriched_fixed_reference_error_l2"
                ),
                "coarse": _compact_solve(pair["coarse"]) if pair else None,
                "enriched": _compact_solve(pair["enriched"]) if pair else None,
                "R5": pair.get("R5"),
            }
        )
    record_path = args.record or (run_dir / "watchdog_summary.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "memory_authority_gib": sampler["memory_authority_gib"],
                "record": _path_from_root(record_path),
                "failures": qualification["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if qualification["pass"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        if args.run_dir is None:
            raise SystemExit("--worker requires --run-dir.")
        return _worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
