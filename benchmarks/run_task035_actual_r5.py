from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
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

    if args.fixed_trace_control_record is not None:
        from src.adaptivity.target_fixed_trace_candidate import (
            run_target_fixed_trace_candidate,
        )

        result = run_target_fixed_trace_candidate(
            args.run_dir,
            control_record=args.fixed_trace_control_record,
            control_sha256=args.fixed_trace_control_sha256,
            global_p6_baseline_record=(
                args.fixed_trace_global_p6_baseline_record
            ),
            global_p6_baseline_sha256=(
                args.fixed_trace_global_p6_baseline_sha256
            ),
            h_nm=args.h_nm,
            incident_theta_deg=80.0,
            polarization_kind=args.polarization_kind,
            trace_degree=args.fixed_trace_degree,
            interior_degree=args.fixed_interior_degree,
            progress_observer=progress,
        )
    elif args.regionwise_p_classifier_record is not None:
        from src.adaptivity.target_regionwise_p_candidate import (
            run_target_regionwise_p_candidate,
        )

        result = run_target_regionwise_p_candidate(
            args.run_dir,
            classifier_record=args.regionwise_p_classifier_record,
            classifier_sha256=args.regionwise_p_classifier_sha256,
            control_record=args.regionwise_p_control_record,
            control_sha256=args.regionwise_p_control_sha256,
            h_nm=args.h_nm,
            incident_theta_deg=80.0,
            polarization_kind=args.polarization_kind,
            trace_degree=args.regionwise_p_trace_degree,
            low_interior_degree=args.regionwise_p_low_interior_degree,
            high_cell_count=args.regionwise_p_high_cell_count,
            progress_observer=progress,
        )
    elif args.common_mesh_replay_record is not None:
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
    elif args.goal_dwr_only:
        from src.adaptivity.goal_weighted_two_level import (
            run_target_goal_weighted_two_level,
        )

        result = run_target_goal_weighted_two_level(
            args.run_dir,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            mesh_cell_type=args.mesh_cell_type,
            progress_observer=progress,
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
            reuse_single_mesh=args.single_mesh_pair,
            static_condensation_degrees=tuple(
                args.static_condensation_degree
            ),
            assembly_time_condensation_degrees=tuple(
                args.assembly_time_condensation_degree
            ),
            floquet_slave_elimination_degrees=tuple(
                args.floquet_slave_elimination_degree
            ),
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
    parser.add_argument(
        "--single-mesh-pair",
        action="store_true",
        help=(
            "build the fixed target mesh once and reuse that exact in-memory "
            "mesh for both global-p solves"
        ),
    )
    parser.add_argument(
        "--static-condensation-degree",
        type=int,
        action="append",
        default=[],
        help=(
            "research-only global-p pair degree whose cell-interior modes are "
            "exactly condensed; may be repeated"
        ),
    )
    parser.add_argument(
        "--assembly-time-condensation-degree",
        type=int,
        action="append",
        default=[],
        help=(
            "research-only global-p pair degree assembled directly into the "
            "cell-condensed Floquet-independent trace matrix; may be repeated"
        ),
    )
    parser.add_argument(
        "--floquet-slave-elimination-degree",
        type=int,
        action="append",
        default=[],
        help=(
            "research-only global-p pair degree whose embedded Floquet "
            "identity rows are physically removed after cell condensation; "
            "may be repeated"
        ),
    )
    parser.add_argument("--mpi-size", type=int, default=8)
    parser.add_argument("--adaptive-marked-cycles", type=int, default=0)
    parser.add_argument("--uniform-refinement-levels", type=int, default=0)
    parser.add_argument("--dwr-adaptive-cycles", type=int, default=0)
    parser.add_argument(
        "--goal-dwr-only",
        action="store_true",
        help=(
            "run one same-mesh R00/R/T goal-adjoint localization pair "
            "without refining the mesh"
        ),
    )
    parser.add_argument(
        "--dwr-marker-policy",
        choices=(
            "combined_relative_R_T",
            "tolerance_normalized_R_T",
            "R_total",
            "T_total",
        ),
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
    parser.add_argument(
        "--regionwise-p-classifier-record",
        type=Path,
        help="Task035b same-mesh p4/p5/p6 classifier authority",
    )
    parser.add_argument(
        "--regionwise-p-classifier-sha256",
        help="required SHA256 for --regionwise-p-classifier-record",
    )
    parser.add_argument(
        "--regionwise-p-control-record",
        type=Path,
        help="Task035b qualified same-mesh p5/p6 control watchdog record",
    )
    parser.add_argument(
        "--regionwise-p-control-sha256",
        help="required SHA256 for --regionwise-p-control-record",
    )
    parser.add_argument(
        "--regionwise-p-trace-degree",
        type=int,
        default=4,
        help="shared edge/face trace degree for the physical local-p candidate",
    )
    parser.add_argument(
        "--regionwise-p-low-interior-degree",
        type=int,
        default=4,
        help="cell-interior degree outside the selected high-cell set",
    )
    parser.add_argument(
        "--regionwise-p-high-cell-count",
        type=int,
        help="number of largest eta_p5p6 classifier cells retaining p6 interior",
    )
    parser.add_argument(
        "--fixed-trace-control-record",
        type=Path,
        help="qualified h10 p5/p6 authority for the h15 fixed-trace upper envelope",
    )
    parser.add_argument(
        "--fixed-trace-control-sha256",
        help="required SHA256 for --fixed-trace-control-record",
    )
    parser.add_argument(
        "--fixed-trace-global-p6-baseline-record",
        type=Path,
        help="qualified same-mesh h15 global-p6 resource baseline",
    )
    parser.add_argument(
        "--fixed-trace-global-p6-baseline-sha256",
        help="required SHA256 for the same-mesh global-p6 baseline",
    )
    parser.add_argument(
        "--fixed-trace-degree",
        type=int,
        default=5,
        help="shared edge/face trace degree for the fixed-trace candidate",
    )
    parser.add_argument(
        "--fixed-interior-degree",
        type=int,
        default=6,
        help="cell-interior degree retained on every candidate cell",
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
    regionwise_values = (
        args.regionwise_p_classifier_record,
        args.regionwise_p_classifier_sha256,
        args.regionwise_p_control_record,
        args.regionwise_p_control_sha256,
    )
    regionwise_mode = any(value is not None for value in regionwise_values)
    if regionwise_mode and not all(value is not None for value in regionwise_values):
        parser.error(
            "regionwise-p mode requires classifier/control records and both SHA256 values."
        )
    if regionwise_mode and (common_mesh_mode or active_cycles):
        parser.error(
            "regionwise-p, common-mesh, and adaptive/uniform modes are mutually exclusive."
        )
    fixed_trace_values = (
        args.fixed_trace_control_record,
        args.fixed_trace_control_sha256,
        args.fixed_trace_global_p6_baseline_record,
        args.fixed_trace_global_p6_baseline_sha256,
    )
    fixed_trace_mode = any(value is not None for value in fixed_trace_values)
    if fixed_trace_mode and not all(
        value is not None for value in fixed_trace_values
    ):
        parser.error(
            "fixed-trace mode requires SHA-bound h10 accuracy control and "
            "same-mesh h15 global-p6 baseline records."
        )
    if fixed_trace_mode and (
        common_mesh_mode or active_cycles or regionwise_mode
    ):
        parser.error(
            "fixed-trace, regionwise-p, common-mesh, and cycle modes "
            "are mutually exclusive."
        )
    if args.goal_dwr_only and (
        common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
    ):
        parser.error(
            "goal-DWR-only, regionwise-p, common-mesh, and cycle modes "
            "are mutually exclusive."
        )
    if args.single_mesh_pair and (
        common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
        or args.goal_dwr_only
    ):
        parser.error(
            "--single-mesh-pair is valid only for the plain global-p pair."
        )
    invalid_condensation_degrees = set(args.static_condensation_degree) - {
        args.coarse_degree,
        args.enriched_degree,
    }
    if invalid_condensation_degrees:
        parser.error(
            "--static-condensation-degree must equal coarse-degree or "
            "enriched-degree."
        )
    if args.static_condensation_degree and (
        common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
        or args.goal_dwr_only
        or args.mesh_cell_type != "hexahedron"
    ):
        parser.error(
            "Task035b static condensation is restricted to the plain "
            "fixed-target hexahedron global-p pair."
        )
    if not set(args.assembly_time_condensation_degree).issubset(
        set(args.static_condensation_degree)
    ):
        parser.error(
            "--assembly-time-condensation-degree must also be listed in "
            "--static-condensation-degree."
        )
    if not set(args.floquet_slave_elimination_degree).issubset(
        set(args.static_condensation_degree)
    ):
        parser.error(
            "--floquet-slave-elimination-degree must also be listed in "
            "--static-condensation-degree."
        )
    if not set(args.assembly_time_condensation_degree).issubset(
        set(args.floquet_slave_elimination_degree)
    ):
        parser.error(
            "--assembly-time-condensation-degree must also be listed in "
            "--floquet-slave-elimination-degree."
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
    if regionwise_mode:
        for value in (
            args.regionwise_p_classifier_sha256,
            args.regionwise_p_control_sha256,
        ):
            if len(value) != 64 or any(
                character not in "0123456789abcdefABCDEF" for character in value
            ):
                parser.error("regionwise-p authority SHA256 values must be 64 hex.")
        if (
            args.mpi_size != 8
            or args.mesh_cell_type != "hexahedron"
            or args.coarse_degree != 5
            or args.enriched_degree != 6
            or abs(args.h_nm - 10.0) > 1.0e-12
            or args.polarization_kind != "s"
        ):
            parser.error(
                "formal regionwise-p mode requires MPI8, hexa h10, p5/p6 "
                "controls, and s polarization."
            )
        if not (
            1
            <= args.regionwise_p_low_interior_degree
            <= args.regionwise_p_trace_degree
            < 6
        ):
            parser.error(
                "regionwise-p requires 1 <= low interior degree "
                "<= trace degree < 6."
            )
        if (
            args.regionwise_p_high_cell_count is not None
            and not 0 <= args.regionwise_p_high_cell_count <= 105
        ):
            parser.error(
                "--regionwise-p-high-cell-count must lie in [0, 105]."
            )
        if (
            args.regionwise_p_trace_degree == 5
            and args.regionwise_p_high_cell_count is None
        ):
            parser.error(
                "p5-trace regionwise-p requires an explicit high-cell count."
            )
    if fixed_trace_mode:
        value = args.fixed_trace_control_sha256
        if len(value) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            parser.error("fixed-trace control SHA256 must be 64 hex.")
        if (
            args.mpi_size != 8
            or args.mesh_cell_type != "hexahedron"
            or args.coarse_degree != 5
            or args.enriched_degree != 6
            or abs(args.h_nm - 15.0) > 1.0e-12
            or args.polarization_kind != "s"
            or args.fixed_trace_degree != 5
            or args.fixed_interior_degree != 6
        ):
            parser.error(
                "formal fixed-trace mode requires MPI8, hexa h15, p5/p6 "
                "controls, p5 trace, p6 interior, and s polarization."
            )
    if args.goal_dwr_only and (
        args.mpi_size != 8
        or args.mesh_cell_type != "hexahedron"
        or args.coarse_degree != 4
        or args.enriched_degree != 5
        or abs(args.h_nm - 10.0) > 1.0e-12
        or args.polarization_kind != "s"
    ):
        parser.error(
            "formal goal-DWR-only mode requires MPI8, hexa h10, p4/p5, "
            "and s polarization."
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
    resolved_config = summary.get("config") or {}
    return {
        "degree": entry["degree"],
        "h_nm": entry["h_nm"],
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "mpi_size": summary.get("mpi_size"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "mesh_cell_type_actual": summary.get("mesh_cell_type_actual"),
        "num_nedelec_dofs": summary.get("num_nedelec_dofs"),
        "nedelec_trace_degree_resolved": resolved_config.get(
            "nedelec_trace_degree_resolved"
        ),
        "nedelec_interior_degree_resolved": resolved_config.get(
            "nedelec_interior_degree_resolved"
        ),
        "matrix_stats": summary.get("matrix_stats"),
        "linear_system_relative_residual": summary.get(
            "linear_system_relative_residual"
        ),
        "R00_s": summary.get("R00_s"),
        "R00_p": summary.get("R00_p"),
        "R00_total": summary.get("R00_total"),
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_volume_total": summary.get("A_volume_total"),
        "energy_closure_error_port_volume": summary.get(
            "energy_closure_error_port_volume"
        ),
        "floquet_num_constraints": summary.get("floquet_num_constraints"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
        "stage4_dtn_ksp_setup_seconds": summary.get(
            "stage4_dtn_ksp_setup_seconds"
        ),
        "stage4_dtn_ksp_solve_seconds": summary.get(
            "stage4_dtn_ksp_solve_seconds"
        ),
        "stage4_dtn_factor_inventory": summary.get(
            "stage4_dtn_factor_inventory"
        ),
        "stage4_dtn_base_matrix_assembly_seconds": summary.get(
            "stage4_dtn_base_matrix_assembly_seconds"
        ),
        "stage4_dtn_assembly_time_total_build_seconds": summary.get(
            "stage4_dtn_assembly_time_total_build_seconds"
        ),
        "stage4_dtn_linear_solve_seconds": summary.get(
            "stage4_dtn_linear_solve_seconds"
        ),
        "timings_seconds": summary.get("timings_seconds"),
        "solver_objects_released_before_postprocess": summary.get(
            "solver_objects_released_before_postprocess"
        ),
        "solver_release_audit": summary.get("solver_release_audit"),
        "stage4_cell_static_condensation": summary.get(
            "stage4_cell_static_condensation"
        ),
        "stage4_assembly_time_cell_static_condensation": summary.get(
            "stage4_assembly_time_cell_static_condensation"
        ),
        "stage4_dtn_condensed_matrix_stats": summary.get(
            "stage4_dtn_condensed_matrix_stats"
        ),
        "stage4_floquet_slave_elimination": summary.get(
            "stage4_floquet_slave_elimination"
        ),
        "stage4_dtn_floquet_independent_matrix_stats": summary.get(
            "stage4_dtn_floquet_independent_matrix_stats"
        ),
        "cell_static_condensation": summary.get(
            "cell_static_condensation"
        ),
        "high_order_resource_audit": entry.get(
            "high_order_resource_audit"
        ),
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
    canonical_marking = r5.get("canonical_marking") or {}
    indicator_snapshot = r5.get("cell_indicator_snapshot") or {}
    solves = [result.get("coarse") or {}, result.get("enriched") or {}]
    summaries = [entry.get("summary") or {} for entry in solves]
    resource_audits = [
        entry.get("high_order_resource_audit") or {} for entry in solves
    ]
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
        "canonical_dorfler_target_captured": (
            isinstance(
                canonical_marking.get("captured_fraction"), (int, float)
            )
            and float(canonical_marking["captured_fraction"]) >= args.theta
        ),
        "complete_cell_indicator_snapshot": (
            indicator_snapshot.get("storage") == "inline_complete_vector"
            and indicator_snapshot.get("cell_count")
            == r5.get("owned_cell_contribution_count")
            and len(indicator_snapshot.get("canonical_cell_ids") or [])
            == indicator_snapshot.get("cell_count")
            and len(indicator_snapshot.get("indicator_values") or [])
            == indicator_snapshot.get("cell_count")
            and indicator_snapshot.get("mesh_geometry_sha256")
            == r5.get("mesh_geometry_sha256")
            and bool(
                indicator_snapshot.get(
                    "canonical_ids_and_values_sha256"
                )
            )
        ),
        "both_official_solves": all(
            summary.get("official_result") is True for summary in summaries
        ),
        "both_full_observable_vectors_present": all(
            all(
                isinstance(summary.get(name), (int, float))
                for name in (
                    "R00_total",
                    "R_total",
                    "T_total",
                    "A_volume_total",
                )
            )
            for summary in summaries
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
        "both_entity_dof_audits_pass": all(
            (audit.get("entity_dof_inventory") or {}).get("pass") is True
            for audit in resource_audits
        ),
        "same_actual_mesh_hashes": result.get("same_mesh_hashes") is True,
        "single_mesh_instance_when_requested": (
            not getattr(args, "single_mesh_pair", False)
            or result.get("single_in_memory_mesh_instance") is True
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    static_condensation_degrees = getattr(
        args, "static_condensation_degree", []
    )
    if static_condensation_degrees:
        requested = set(static_condensation_degrees)
        requested_entries = [
            entry
            for entry in solves
            if int(entry.get("degree", -1)) in requested
        ]
        checks.update(
            {
                "requested_static_condensation_active": (
                    len(requested_entries) == len(requested)
                    and all(
                        (entry.get("summary") or {}).get(
                            "stage4_cell_static_condensation"
                        )
                        is True
                        for entry in requested_entries
                    )
                ),
                "requested_condensed_rows_physically_measured": all(
                    (
                        (
                            entry.get("high_order_resource_audit") or {}
                        ).get("entity_dof_inventory")
                        or {}
                    ).get("static_condensation_projection_semantics", "").startswith(
                        "measured_active_rows"
                    )
                    for entry in requested_entries
                ),
                "requested_full_residual_audit_present": all(
                    isinstance(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "cell_static_condensation"
                                )
                                or {}
                            ).get("full_explicit_true_residual")
                            or {}
                        ).get("linear_system_relative_residual"),
                        (int, float),
                    )
                    for entry in requested_entries
                ),
            }
        )
    slave_elimination_degrees = getattr(
        args, "floquet_slave_elimination_degree", []
    )
    if slave_elimination_degrees:
        requested = set(slave_elimination_degrees)
        requested_entries = [
            entry
            for entry in solves
            if int(entry.get("degree", -1)) in requested
        ]
        checks.update(
            {
                "requested_floquet_slave_elimination_active": (
                    len(requested_entries) == len(requested)
                    and all(
                        (entry.get("summary") or {}).get(
                            "stage4_floquet_slave_elimination"
                        )
                        is True
                        for entry in requested_entries
                    )
                ),
                "requested_floquet_slave_rows_physically_removed": all(
                    (
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "cell_static_condensation"
                                )
                                or {}
                            ).get("floquet_slave_elimination")
                            or {}
                        ).get("status")
                        in {
                            "exact_identity_slave_rows_removed",
                            "exact_mpc_trace_expansion_built",
                        }
                    )
                    for entry in requested_entries
                ),
            }
        )
    assembly_time_degrees = getattr(
        args,
        "assembly_time_condensation_degree",
        [],
    )
    if assembly_time_degrees:
        requested = set(assembly_time_degrees)
        requested_entries = [
            entry
            for entry in solves
            if int(entry.get("degree", -1)) in requested
        ]
        checks.update(
            {
                "requested_assembly_time_condensation_active": (
                    len(requested_entries) == len(requested)
                    and all(
                        (entry.get("summary") or {}).get(
                            "stage4_assembly_time_cell_static_condensation"
                        )
                        is True
                        for entry in requested_entries
                    )
                ),
                "requested_full_matrices_never_allocated": all(
                    (
                        (
                            (entry.get("summary") or {}).get(
                                "cell_static_condensation"
                            )
                            or {}
                        ).get("full_global_matrix_allocated")
                        is False
                        and (
                            (
                                (entry.get("summary") or {}).get(
                                    "cell_static_condensation"
                                )
                                or {}
                            ).get("full_trace_matrix_allocated")
                            is False
                        )
                    )
                    for entry in requested_entries
                ),
                "requested_matrix_free_full_residual_present": all(
                    isinstance(
                        (
                            (
                                (
                                    (entry.get("summary") or {}).get(
                                        "cell_static_condensation"
                                    )
                                    or {}
                                ).get("full_explicit_true_residual")
                                or {}
                            ).get("eliminated_cell_interior_residual_norm")
                        ),
                        (int, float),
                    )
                    for entry in requested_entries
                ),
                "requested_mumps_workspace_is_explicit": all(
                    (
                        (entry.get("summary") or {})
                        .get("config", {})
                        .get("petsc_extra_options", {})
                        .get("mat_mumps_icntl_14")
                        == 100
                    )
                    for entry in requested_entries
                ),
                "requested_solver_objects_released_before_postprocess": all(
                    (entry.get("summary") or {}).get(
                        "solver_objects_released_before_postprocess"
                    )
                    is True
                    for entry in requested_entries
                ),
                "requested_heap_trim_succeeded": all(
                    (
                        (
                            (entry.get("summary") or {}).get(
                                "solver_release_audit"
                            )
                            or {}
                        ).get("process_heap_trim")
                        or {}
                    ).get("succeeded_on_all_ranks")
                    is True
                    for entry in requested_entries
                ),
                "requested_heap_trim_reduced_rss": all(
                    isinstance(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        ).get("sum_rss_before_mb"),
                        (int, float),
                    )
                    and isinstance(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        ).get("sum_rss_after_mb"),
                        (int, float),
                    )
                    and float(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        )["sum_rss_after_mb"]
                    )
                    < float(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        )["sum_rss_before_mb"]
                    )
                    for entry in requested_entries
                ),
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_goal_dwr(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    """Qualify one fixed-hexa p4/p5 multi-goal localization run."""

    coarse = (result.get("coarse") or {}).get("summary") or {}
    enriched = (result.get("enriched") or {}).get("summary") or {}
    dwr = result.get("DWR") or {}
    goals = dwr.get("goals") or {}
    combined_reports = [
        dwr.get("combined_relative_R_T") or {},
        dwr.get("tolerance_normalized_R_T") or {},
    ]
    r5 = result.get("R5_control") or {}
    target = result.get("target_identity") or {}
    goal_reports = [
        goals.get(name) or {}
        for name in ("R00_total", "R_total", "T_total")
    ]
    enriched_residual = (dwr.get("residual") or {}).get(
        "enriched_solution_relative_residual_recomputed"
    )
    r5_closure = (r5.get("correction_energy") or {}).get(
        "relative_closure_error"
    )

    def qualified_goal(report: dict[str, Any]) -> bool:
        effectivity = report.get("absolute_effectivity")
        closure = report.get("signed_goal_change_closure")
        return bool(
            report.get("finite_nonnegative_cell_contributions") is True
            and (report.get("marking") or {}).get("captured_fraction", 0.0)
            >= float(args.theta) - 1.0e-12
            and isinstance(effectivity, (int, float))
            and math.isfinite(float(effectivity))
            and abs(float(effectivity) - 1.0) <= 1.0e-8
            and isinstance(closure, (int, float))
            and math.isfinite(float(closure))
            and abs(float(closure)) <= 1.0e-9
            and bool(report.get("mesh_geometry_sha256"))
            and bool(report.get("marked_geometry_sha256"))
        )

    def qualified_marker(report: dict[str, Any]) -> bool:
        return bool(
            report.get("finite_nonnegative_cell_contributions") is True
            and (report.get("marking") or {}).get("captured_fraction", 0.0)
            >= float(args.theta) - 1.0e-12
            and bool(report.get("mesh_geometry_sha256"))
            and bool(report.get("marked_geometry_sha256"))
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
        "result_status": (
            result.get("status") == "target_goal_weighted_two_level_pass"
        ),
        "result_pass": result.get("pass") is True,
        "fixed_rectangular_hexa_h10_identity": (
            target.get("geometry") == "Task034 fixed rectangular block grating"
            and target.get("mesh_backend")
            == "boundary-fitted conforming hexahedron"
            and abs(float(target.get("h_nm", -1.0)) - 10.0) <= 1.0e-12
        ),
        "p4_p5_pair_identity": (
            (result.get("coarse") or {}).get("degree") == 4
            and (result.get("enriched") or {}).get("degree") == 5
        ),
        "both_official_solves": (
            coarse.get("official_result") is True
            and enriched.get("official_result") is True
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in (coarse, enriched)
        ),
        "same_actual_hexa_mesh_cell_count": (
            coarse.get("mesh_cell_type_actual") == "hexahedron"
            and enriched.get("mesh_cell_type_actual") == "hexahedron"
            and coarse.get("num_mesh_cells") == 252
            and enriched.get("num_mesh_cells") == 252
        ),
        "enriched_residual_recomputed_le_1e-9": (
            isinstance(enriched_residual, (int, float))
            and float(enriched_residual) <= 1.0e-9
        ),
        "actual_adjoint_qualification_pass": (
            (dwr.get("adjoint_qualification") or {}).get("pass") is True
        ),
        "all_R00_R_T_goal_reports_qualified": (
            len(goals) >= 3
            and all(qualified_goal(report) for report in goal_reports)
        ),
        "both_multi_goal_reports_qualified": all(
            qualified_marker(report) for report in combined_reports
        ),
        "tolerance_normalization_authority_bound": (
            (
                (dwr.get("tolerance_normalized_R_T") or {}).get(
                    "normalization_authority"
                )
                or {}
            ).get("independent_adjoint_goals")
            == ["R_total", "T_total"]
        ),
        "R5_control_energy_closure": (
            isinstance(r5_closure, (int, float))
            and float(r5_closure) <= 1.0e-10
        ),
        "algebraic_localization_rejected": (
            (dwr.get("rejected_localization") or {}).get("decision")
            == "controlled_negative_partition_dependent"
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
        ),
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
        report[args.dwr_marker_policy]
        if args.dwr_marker_policy
        in {"combined_relative_R_T", "tolerance_normalized_R_T"}
        else report["goals"][args.dwr_marker_policy]
        for report in dwr_reports
    ]

    def normalized_authority_is_bound(report: dict[str, Any]) -> bool:
        authority = report.get("normalization_authority") or {}
        tolerances = authority.get("absolute_error_tolerances") or {}
        return bool(
            authority.get("control_key") == "p4_h7p5"
            and authority.get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
            and authority.get("independent_adjoint_goals")
            == ["R_total", "T_total"]
            and set(tolerances)
            == {"R_total", "T_total", "A_volume_total"}
            and all(
                isinstance(value, (int, float)) and float(value) > 0.0
                for value in tolerances.values()
            )
        )

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
        "selected_multi_goal_normalization_bound": (
            args.dwr_marker_policy != "tolerance_normalized_R_T"
            or all(normalized_authority_is_bound(report) for report in marker_reports)
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


def _qualify_fixed_trace(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    candidate = result.get("candidate") or {}
    summary = candidate.get("summary") or {}
    resolved_config = summary.get("config") or {}
    resource_audit = candidate.get("high_order_resource_audit") or {}
    entity_audit = resource_audit.get("entity_dof_inventory") or {}
    cell_audit = summary.get("cell_static_condensation") or {}
    true_residual = cell_audit.get("full_explicit_true_residual") or {}
    matrix_stats = summary.get("matrix_stats") or {}
    orientation = summary.get("nedelec_orientation_factor_stats") or {}
    element_audit = result.get("element_audit") or {}
    dof_target = result.get("dof_target") or {}
    scalar_comparison = result.get("observable_comparison") or {}
    channel_comparison = result.get("diffraction_channel_comparison") or {}
    field_gate = result.get("selected_field_interface_error_gate") or {}
    control = result.get("control_authority") or {}
    global_p6_baseline = result.get("global_p6_baseline_authority") or {}
    same_mesh_baseline = result.get("same_mesh_global_p6_baseline") or {}
    resource_comparison = result.get("same_mesh_resource_comparison") or {}
    target_identity = result.get("target_identity") or {}
    accepted_statuses = {
        "actual_fixed_trace_candidate_pass",
        "actual_fixed_trace_controlled_negative",
    }
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status_is_positive_or_controlled_negative": (
            result.get("status") in accepted_statuses
        ),
        "execution_integrity_pass": result.get("pass") is True,
        "accuracy_classification_recorded": isinstance(
            result.get("candidate_accuracy_pass"),
            bool,
        ),
        "official_candidate": summary.get("official_result") is True,
        "fixed_rectangular_hexa_h15_identity": (
            target_identity.get("geometry")
            == "Task034 fixed rectangular block grating"
            and summary.get("mesh_cell_type_actual") == "hexahedron"
            and summary.get("num_mesh_cells") == 120
            and abs(float(candidate.get("h_nm", -1.0)) - 15.0) <= 1.0e-12
            and target_identity.get("trace_degree")
            == args.fixed_trace_degree
            and target_identity.get("interior_degree")
            == args.fixed_interior_degree
        ),
        "control_authority_hash_bound": (
            control.get("sha256") == args.fixed_trace_control_sha256
        ),
        "global_p6_baseline_hash_bound": (
            global_p6_baseline.get("sha256")
            == args.fixed_trace_global_p6_baseline_sha256
        ),
        "same_mesh_and_tag_hashes_match_global_p6": (
            same_mesh_baseline.get("pass") is True
            and same_mesh_baseline.get("checks")
            == {
                "partition_independent_mesh_sha256": True,
                "cell_tag_sha256": True,
                "facet_tag_sha256": True,
            }
        ),
        "exact_sequence_space": (
            element_audit.get("pass") is True
            and element_audit.get("both_high_and_low_exact_sequence_pass")
            is True
            and element_audit.get("trace_degree") == args.fixed_trace_degree
            and element_audit.get("interior_degree")
            == args.fixed_interior_degree
            and element_audit.get("low_interior_degree")
            == args.fixed_trace_degree
        ),
        "physical_p5_trace_p6_interior_space": (
            resolved_config.get("nedelec_trace_degree_resolved")
            == args.fixed_trace_degree
            and resolved_config.get("nedelec_interior_degree_resolved")
            == args.fixed_interior_degree
            and isinstance(element_audit.get("custom_dimension"), int)
            and isinstance(element_audit.get("standard_high_dimension"), int)
            and element_audit.get("custom_dimension")
            < element_audit.get("standard_high_dimension")
        ),
        "preferred_full3d_equivalent_dof_target": (
            summary.get("num_nedelec_dofs") == 74890
            and dof_target.get("active_full3d_equivalent_dofs") == 74890
            and dof_target.get("same_mesh_global_p6_dofs") == 84492
            and dof_target.get("minimum_le_90000") is True
            and dof_target.get("preferred_65000_to_75000") is True
            and dof_target.get("inactive_p6_trace_modes_physically_absent")
            is True
        ),
        "no_full_global_or_trace_matrix_allocated": (
            cell_audit.get("full_global_matrix_allocated") is False
            and cell_audit.get("full_trace_matrix_allocated") is False
            and cell_audit.get("inactive_max_p_rows_retained_in_matrix")
            is False
            and cell_audit.get("assembly_cost_avoided") is True
        ),
        "physically_reduced_matrix_rows": (
            isinstance(matrix_stats.get("matrix_rows"), int)
            and matrix_stats.get("matrix_rows") == cell_audit.get("matrix_rows")
            and matrix_stats.get("matrix_rows") < 74890
        ),
        "matrix_nnz_and_row_width_measured": (
            isinstance(matrix_stats.get("matrix_nnz_used"), (int, float))
            and matrix_stats.get("matrix_nnz_used", 0.0) > 0.0
            and isinstance(
                matrix_stats.get("matrix_average_nnz_per_row"),
                (int, float),
            )
            and isinstance(
                matrix_stats.get("matrix_maximum_nnz_per_row"),
                (int, float),
            )
        ),
        "factor_inventory_measured": (
            (summary.get("stage4_dtn_factor_inventory") or {}).get("available")
            is True
        ),
        "same_mesh_resource_comparison_measured": (
            resource_comparison.get("schema_version")
            == "task035b.fixed-trace-resource-comparison.v1"
            and (
                (resource_comparison.get("metrics") or {}).get(
                    "full3d_equivalent_dofs"
                )
                or {}
            ).get("global_p6")
            == 84492
            and (
                (resource_comparison.get("metrics") or {}).get("active_rows")
                or {}
            ).get("candidate")
            == matrix_stats.get("matrix_rows")
            and isinstance(
                (
                    (resource_comparison.get("metrics") or {}).get(
                        "factor_nnz"
                    )
                    or {}
                ).get("compression_ratio"),
                (int, float),
            )
        ),
        "solver_released_before_postprocess": (
            summary.get("direct_release_solver_before_postprocess") is True
            and summary.get("solver_objects_released_before_postprocess")
            is True
            and (summary.get("solver_release_audit") or {}).get(
                "petsc_garbage_cleanup_called"
            )
            is True
        ),
        "full_true_residual_le_1e-9": (
            isinstance(
                true_residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(true_residual["linear_system_relative_residual"])
            <= 1.0e-9
            and isinstance(
                summary.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
        ),
        "entity_dof_audit_pass": entity_audit.get("pass") is True,
        "periodic_trace_identity_pass": (
            summary.get("floquet_constraint_mode_resolved")
            == "topological_trace_p5"
            and summary.get("floquet_num_constraints", 0) > 0
            and summary.get("floquet_x_face_mismatch") == 0.0
            and summary.get("floquet_y_face_mismatch") == 0.0
            and summary.get("floquet_edge_corner_mismatch") == 0.0
            and summary.get("max_face_pairing_coordinate_error") == 0.0
        ),
        "exact_orientation_path": (
            orientation.get("uses_exact_basix_entity_transforms") is True
            and orientation.get("uses_local_moment_fit") is False
            and orientation.get("mapping_kind")
            == "distributed_exact_topological_trace_p5"
        ),
        "material_tag_geometry_alignment_pass": (
            (summary.get("mesh_material_plane_alignment") or {}).get(
                "all_aligned"
            )
            is True
            and set((summary.get("domain_tag_volumes") or {}))
            >= {"air", "substrate", "grating"}
        ),
        "scalar_same_code_comparison_recorded": (
            scalar_comparison.get("schema_version")
            == "task035b.cross-mesh-observable-comparison.v1"
            and isinstance(scalar_comparison.get("pass"), bool)
        ),
        "diffraction_power_and_amplitude_comparison_recorded": (
            channel_comparison.get("schema_version")
            == "task035b.cross-mesh-channel-comparison.v1"
            and channel_comparison.get("channel_count") == 80
            and isinstance(channel_comparison.get("pass"), bool)
        ),
        "selected_field_interface_comparison_recorded": (
            field_gate.get("status")
            == "measured_frozen_physical_gauss_probes"
            and field_gate.get("no_threshold_relaxation") is True
            and isinstance(field_gate.get("pass"), bool)
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_regionwise_p(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    candidate = result.get("candidate") or {}
    summary = candidate.get("summary") or {}
    resource_audit = candidate.get("high_order_resource_audit") or {}
    entity_audit = resource_audit.get("entity_dof_inventory") or {}
    cell_audit = summary.get("cell_static_condensation") or {}
    matrix_stats = summary.get("matrix_stats") or {}
    orientation = summary.get("nedelec_orientation_factor_stats") or {}
    field_gate = result.get("selected_field_interface_error_gate") or {}
    scalar_comparison = result.get("observable_comparison") or {}
    channel_comparison = result.get("diffraction_channel_comparison") or {}
    classifier = result.get("classifier_authority") or {}
    control = result.get("control_authority") or {}
    target_identity = result.get("target_identity") or {}
    expected_high_cells = getattr(
        args,
        "regionwise_p_high_cell_count",
        None,
    )
    if expected_high_cells is None:
        expected_high_cells = classifier.get("high_canonical_cell_count")
    active_dof_budget = classifier.get("active_full3d_equivalent_dofs")
    accepted_statuses = {
        "actual_regionwise_p_candidate_pass",
        "actual_regionwise_p_controlled_negative",
    }
    true_residual = cell_audit.get("full_explicit_true_residual") or {}
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status_is_positive_or_controlled_negative": (
            result.get("status") in accepted_statuses
        ),
        "execution_integrity_pass": result.get("pass") is True,
        "official_candidate": summary.get("official_result") is True,
        "fixed_rectangular_hexa_h10_identity": (
            target_identity.get("geometry")
            == "Task034 fixed rectangular block grating"
            and summary.get("mesh_cell_type_actual") == "hexahedron"
            and summary.get("num_mesh_cells") == 252
            and abs(float(candidate.get("h_nm", -1.0)) - 10.0) <= 1.0e-12
            and target_identity.get("trace_degree")
            == getattr(args, "regionwise_p_trace_degree", 4)
            and target_identity.get("low_interior_degree")
            == getattr(args, "regionwise_p_low_interior_degree", 4)
            and target_identity.get("high_interior_degree") == 6
        ),
        "classifier_authority_hash_bound": (
            classifier.get("sha256") == args.regionwise_p_classifier_sha256
        ),
        "control_authority_hash_bound": (
            control.get("sha256") == args.regionwise_p_control_sha256
        ),
        "regionwise_geometry_hash_bound": (
            cell_audit.get("regionwise_mesh_geometry_sha256")
            == target_identity.get("mesh_geometry_sha256")
        ),
        "regionwise_cell_classification_exact": (
            isinstance(expected_high_cells, int)
            and cell_audit.get("regionwise_interior_p_active") is True
            and cell_audit.get("regionwise_high_cell_count")
            == expected_high_cells
            and cell_audit.get("regionwise_low_cell_count")
            == 252 - expected_high_cells
        ),
        "active_full3d_equivalent_budget_le_90k": (
            isinstance(active_dof_budget, int)
            and active_dof_budget <= 90000
            and cell_audit.get("active_full3d_equivalent_dofs")
            == active_dof_budget
        ),
        "inactive_p6_rows_not_retained": (
            cell_audit.get("inactive_max_p_rows_retained_in_matrix") is False
        ),
        "no_full_global_or_trace_matrix_allocated": (
            cell_audit.get("full_global_matrix_allocated") is False
            and cell_audit.get("full_trace_matrix_allocated") is False
        ),
        "low_cells_use_direct_p4_kernel": (
            cell_audit.get("regionwise_low_cell_kernel_compiled_directly") is True
        ),
        "physically_reduced_matrix_rows": (
            isinstance(matrix_stats.get("matrix_rows"), int)
            and matrix_stats.get("matrix_rows") == cell_audit.get("matrix_rows")
            and isinstance(active_dof_budget, int)
            and matrix_stats.get("matrix_rows") < active_dof_budget
        ),
        "matrix_nnz_and_row_width_measured": (
            isinstance(matrix_stats.get("matrix_nnz_used"), (int, float))
            and matrix_stats.get("matrix_nnz_used", 0.0) > 0.0
            and isinstance(
                matrix_stats.get("matrix_average_nnz_per_row"), (int, float)
            )
            and isinstance(
                matrix_stats.get("matrix_maximum_nnz_per_row"), (int, float)
            )
        ),
        "factor_inventory_measured": (
            (summary.get("stage4_dtn_factor_inventory") or {}).get("available")
            is True
        ),
        "full_true_residual_le_1e-9": (
            isinstance(
                true_residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(true_residual["linear_system_relative_residual"]) <= 1.0e-9
            and isinstance(
                summary.get("linear_system_relative_residual"), (int, float)
            )
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
        ),
        "entity_dof_audit_pass": entity_audit.get("pass") is True,
        "periodic_trace_identity_pass": (
            summary.get("floquet_num_constraints", 0) > 0
            and summary.get("floquet_x_face_mismatch") == 0.0
            and summary.get("floquet_y_face_mismatch") == 0.0
            and summary.get("floquet_edge_corner_mismatch") == 0.0
            and summary.get("max_face_pairing_coordinate_error") == 0.0
        ),
        "exact_orientation_path": (
            orientation.get("uses_exact_basix_entity_transforms") is True
            and orientation.get("uses_local_moment_fit") is False
        ),
        "material_tag_geometry_alignment_pass": (
            (summary.get("mesh_material_plane_alignment") or {}).get(
                "all_aligned"
            )
            is True
            and set((summary.get("domain_tag_volumes") or {}))
            >= {"air", "substrate", "grating"}
        ),
        "scalar_same_code_comparison_recorded": (
            scalar_comparison.get("schema_version")
            == "task035b.regionwise-p-observable-comparison.v1"
            and isinstance(
                scalar_comparison.get("all_scalar_same_code_bands_pass"), bool
            )
            and isinstance(
                scalar_comparison.get(
                    "normalized_R_T_Aclosure_vector_pass"
                ),
                bool,
            )
        ),
        "diffraction_power_and_amplitude_comparison_recorded": (
            channel_comparison.get("channel_count") == 80
            and isinstance(channel_comparison.get("pass"), bool)
        ),
        "selected_field_interface_comparison_recorded": (
            field_gate.get("status")
            == "measured_common_native_visualization_points"
            and field_gate.get("no_threshold_relaxation") is True
            and isinstance(field_gate.get("pass"), bool)
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _select_qualifier(args: argparse.Namespace):
    """Select the formal record qualifier for the mutually exclusive mode."""

    if args.fixed_trace_control_record is not None:
        return _qualify_fixed_trace
    if args.regionwise_p_classifier_record is not None:
        return _qualify_regionwise_p
    if args.common_mesh_replay_record is not None:
        return _qualify_common_mesh_sweep
    if args.goal_dwr_only:
        return _qualify_goal_dwr
    if args.dwr_adaptive_cycles:
        return _qualify_dwr_adaptive
    if args.adaptive_marked_cycles:
        return _qualify_adaptive
    if args.uniform_refinement_levels:
        return _qualify_uniform
    return _qualify


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
    if args.regionwise_p_classifier_record is not None:
        for path_name, sha_name in (
            (
                "regionwise_p_classifier_record",
                "regionwise_p_classifier_sha256",
            ),
            ("regionwise_p_control_record", "regionwise_p_control_sha256"),
        ):
            authority_path = getattr(args, path_name)
            if not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            if not authority_path.is_file():
                raise SystemExit(
                    f"regionwise-p authority not found: {authority_path}"
                )
            expected_sha = getattr(args, sha_name).lower()
            actual_sha = _sha256(authority_path)
            if actual_sha != expected_sha:
                raise SystemExit(
                    f"regionwise-p authority SHA256 mismatch for {authority_path}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )
            setattr(args, path_name, authority_path.resolve())
            setattr(args, sha_name, expected_sha)
    if args.fixed_trace_control_record is not None:
        for path_name, sha_name in (
            (
                "fixed_trace_control_record",
                "fixed_trace_control_sha256",
            ),
            (
                "fixed_trace_global_p6_baseline_record",
                "fixed_trace_global_p6_baseline_sha256",
            ),
        ):
            authority_path = getattr(args, path_name)
            if not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            if not authority_path.is_file():
                raise SystemExit(
                    f"fixed-trace authority not found: {authority_path}"
                )
            expected_sha = getattr(args, sha_name).lower()
            actual_sha = _sha256(authority_path)
            if actual_sha != expected_sha:
                raise SystemExit(
                    "fixed-trace authority SHA256 mismatch for "
                    f"{authority_path}: expected {expected_sha}, got {actual_sha}"
                )
            setattr(args, path_name, authority_path.resolve())
            setattr(args, sha_name, expected_sha)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.fixed_trace_control_record is not None:
        run_label = (
            f"hexahedron_fixed_p{args.fixed_trace_degree}trace_"
            f"p{args.fixed_interior_degree}interior_h{args.h_nm:g}_"
            f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
        )
    elif args.regionwise_p_classifier_record is not None:
        run_label = (
            f"hexahedron_regionwise_p{args.regionwise_p_trace_degree}trace_"
            f"p{args.regionwise_p_low_interior_degree}low_p6high_"
            f"n{105 if args.regionwise_p_high_cell_count is None else args.regionwise_p_high_cell_count}_"
            f"h{args.h_nm:g}_"
            f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
        )
    else:
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
    elif args.goal_dwr_only:
        run_label += f"_goal_dwr_only_theta{args.theta:g}"
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
    elif args.single_mesh_pair:
        run_label += "_single_mesh_pair"
    if args.static_condensation_degree:
        run_label += "_condense_" + "-".join(
            f"p{degree}" for degree in args.static_condensation_degree
        )
    if args.assembly_time_condensation_degree:
        run_label += "_assembly_time_" + "-".join(
            f"p{degree}"
            for degree in args.assembly_time_condensation_degree
        )
    if args.floquet_slave_elimination_degree:
        run_label += "_independent_" + "-".join(
            f"p{degree}"
            for degree in args.floquet_slave_elimination_degree
        )
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
    if args.single_mesh_pair:
        command.append("--single-mesh-pair")
    for degree in args.static_condensation_degree:
        command.extend(["--static-condensation-degree", str(degree)])
    for degree in args.assembly_time_condensation_degree:
        command.extend(
            ["--assembly-time-condensation-degree", str(degree)]
        )
    for degree in args.floquet_slave_elimination_degree:
        command.extend(
            ["--floquet-slave-elimination-degree", str(degree)]
        )
    if args.fixed_trace_control_record is not None:
        command.extend(
            [
                "--fixed-trace-control-record",
                str(args.fixed_trace_control_record),
                "--fixed-trace-control-sha256",
                args.fixed_trace_control_sha256,
                "--fixed-trace-global-p6-baseline-record",
                str(args.fixed_trace_global_p6_baseline_record),
                "--fixed-trace-global-p6-baseline-sha256",
                args.fixed_trace_global_p6_baseline_sha256,
                "--fixed-trace-degree",
                str(args.fixed_trace_degree),
                "--fixed-interior-degree",
                str(args.fixed_interior_degree),
            ]
        )
    elif args.regionwise_p_classifier_record is not None:
        command.extend(
            [
                "--regionwise-p-classifier-record",
                str(args.regionwise_p_classifier_record),
                "--regionwise-p-classifier-sha256",
                args.regionwise_p_classifier_sha256,
                "--regionwise-p-control-record",
                str(args.regionwise_p_control_record),
                "--regionwise-p-control-sha256",
                args.regionwise_p_control_sha256,
                "--regionwise-p-trace-degree",
                str(args.regionwise_p_trace_degree),
                "--regionwise-p-low-interior-degree",
                str(args.regionwise_p_low_interior_degree),
            ]
        )
        if args.regionwise_p_high_cell_count is not None:
            command.extend(
                [
                    "--regionwise-p-high-cell-count",
                    str(args.regionwise_p_high_cell_count),
                ]
            )
    elif args.common_mesh_replay_record is not None:
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
    elif args.goal_dwr_only:
        command.append("--goal-dwr-only")
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
    qualifier = _select_qualifier(args)
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
            result.get("status")
            if args.fixed_trace_control_record is not None
            or args.regionwise_p_classifier_record is not None
            else "actual_common_mesh_angle_sweep_pass"
            if args.common_mesh_replay_record is not None
            else "target_goal_weighted_two_level_pass"
            if args.goal_dwr_only
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
            "task035b.fixed-trace-watchdog.v1"
            if args.fixed_trace_control_record is not None
            else "task035b.regionwise-p-watchdog.v1"
            if args.regionwise_p_classifier_record is not None
            else "task035.actual-common-mesh-angle-sweep-watchdog.v1"
            if args.common_mesh_replay_record is not None
            else "task035b.actual-goal-dwr-only-watchdog.v1"
            if args.goal_dwr_only
            else "task035.actual-dwr-adaptive-watchdog.v1"
            if args.dwr_adaptive_cycles
            else "task035.actual-r5-adaptive-watchdog.v1"
            if args.adaptive_marked_cycles
            else "task035.actual-uniform-tetra-watchdog.v1"
            if args.uniform_refinement_levels
            else "task035.actual-global-r5-watchdog.v1"
        ),
        "benchmark_id": (
            "task035b_target_fixed_trace_candidate"
            if args.fixed_trace_control_record is not None
            else "task035b_target_regionwise_p_candidate"
            if args.regionwise_p_classifier_record is not None
            else "task035_target_actual_common_mesh_angle_sweep"
            if args.common_mesh_replay_record is not None
            else "task035b_target_actual_goal_dwr_only"
            if args.goal_dwr_only
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
            if args.fixed_trace_control_record is not None
            or args.regionwise_p_classifier_record is not None
            or args.common_mesh_replay_record is not None
            or args.dwr_adaptive_cycles
            or args.adaptive_marked_cycles
            or args.uniform_refinement_levels
            or not result
            else _compact_solve(result["coarse"])
        ),
        "enriched": (
            None
            if args.fixed_trace_control_record is not None
            or args.regionwise_p_classifier_record is not None
            or args.common_mesh_replay_record is not None
            or args.dwr_adaptive_cycles
            or args.adaptive_marked_cycles
            or args.uniform_refinement_levels
            or not result
            else _compact_solve(result["enriched"])
        ),
        "official_observable_delta_l2": result.get("official_observable_delta_l2"),
        "R5": result.get("R5"),
        "common_mesh_identity": result.get("common_mesh_identity"),
        "same_mesh_hashes": result.get("same_mesh_hashes"),
        "single_in_memory_mesh_instance": result.get(
            "single_in_memory_mesh_instance"
        ),
        "reuse_single_mesh_requested": result.get(
            "reuse_single_mesh_requested"
        ),
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
    if args.fixed_trace_control_record is not None:
        candidate = result.get("candidate") or {}
        record.update(
            {
                "candidate_accuracy_pass": result.get(
                    "candidate_accuracy_pass"
                ),
                "element_audit": result.get("element_audit"),
                "control_authority": result.get("control_authority"),
                "global_p6_baseline_authority": result.get(
                    "global_p6_baseline_authority"
                ),
                "same_mesh_global_p6_baseline": result.get(
                    "same_mesh_global_p6_baseline"
                ),
                "same_mesh_resource_comparison": result.get(
                    "same_mesh_resource_comparison"
                ),
                "dof_target": result.get("dof_target"),
                "candidate": (
                    _compact_solve(candidate) if candidate else None
                ),
                "observable_comparison": result.get(
                    "observable_comparison"
                ),
                "diffraction_channel_comparison": result.get(
                    "diffraction_channel_comparison"
                ),
                "selected_field_interface_error_gate": result.get(
                    "selected_field_interface_error_gate"
                ),
            }
        )
    elif args.regionwise_p_classifier_record is not None:
        candidate = result.get("candidate") or {}
        record.update(
            {
                "candidate_accuracy_pass": result.get(
                    "candidate_accuracy_pass"
                ),
                "classifier_authority": result.get("classifier_authority"),
                "control_authority": result.get("control_authority"),
                "candidate": (
                    _compact_solve(candidate) if candidate else None
                ),
                "observable_comparison": result.get(
                    "observable_comparison"
                ),
                "diffraction_channel_comparison": result.get(
                    "diffraction_channel_comparison"
                ),
                "selected_field_interface_error_gate": result.get(
                    "selected_field_interface_error_gate"
                ),
            }
        )
    elif args.common_mesh_replay_record is not None:
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
    elif args.goal_dwr_only:
        record.update(
            {
                "goal_changes": result.get("goal_changes"),
                "DWR": result.get("DWR"),
                "R5_control": result.get("R5_control"),
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
