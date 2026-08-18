"""Lightweight parent/watchdog entry point for the Task39 V3-7 worker.

This module is intentionally safe to import before spawning MPI: it imports no
solver, ``mpi4py``, ``petsc4py``, or V3-7 orchestration code.  Numerical setup
starts only in the child ``benchmarks.task039_v3_7_orchestration --worker``;
the parent delegates sampling and complete-process-tree termination to the
reviewed Task38 launcher.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.watchdog_process_control import terminate_process_tree
from src.io.execution_plan import ExecutionPlan
from src.io.input_validation import load_and_resolve
from src.runners.task038_launcher import _run_worker, _write_bootstrap


V3_7_PROFILE_ID = "task039.v3_7.hybrid_iterative.p6-h5.v1"
V3_7_WATCHDOG_AUTH_FLAG = "--launched-by-task038-watchdog"
V3_7_DIRECT_PRODUCER_SHA = "5bfab734a9ca053b69fa1f3f20d907aacbf8b07f"
V3_7_DIRECT_RUN_ROOT = Path(
    "results/task039_5nm_v3_1deg_s5_hybrid_direct_m480/"
    "task039_v3_hybrid_direct_p6h5_m480_mpi8__hybrid_direct__mpi8__M480/"
    "20260815T111156.797076Z"
)
V3_7_WARNING_GIB = 170.0
V3_7_CRITICAL_GIB = 195.0
V3_7_ABSOLUTE_HARD_BYTES = 224_000_000_000
V3_7_POLL_SECONDS = 0.25
V3_7_QEP_ONLY_WORKER_MODULE = "benchmarks.task039_qep_only"
V3_7_CANDIDATE_B_FLAG = "--candidate-b-only"
V3_7_CANDIDATE_C_FLAG = "--candidate-c-only"
V3_7_CANDIDATE_D_FLAG = "--candidate-d-only"
V3_7_CANDIDATE_D_QUALIFIED_FLAG = "--candidate-d-qualified"
V3_7_CANDIDATE_E_FLAG = "--candidate-e-side-only"
V3_8_CANDIDATE_D_QUALIFIED_METHOD = "hybrid_iterative_exact_side_case_qualification"
V5_H4_SETUP_ONLY_FLAG = "--v5-h4-setup-only"
V5_H4_SETUP_ONLY_METHOD = "task039_v5_h4_exact_side_setup_only"


def _validate_resolved_identity(
    payload: Mapping[str, Any], *, v5_h4_setup_only: bool = False
) -> None:
    if v5_h4_setup_only:
        method = payload.get("method", {})
        if payload.get("model_id") != "task039_5nm_v4_1deg_s5_hybrid_iterative_m480":
            raise ValueError("V5 h4 setup-only requires the fixed h4 model")
        if method.get("kind") != "hybrid_iterative":
            raise ValueError("V5 h4 setup-only requires hybrid_iterative")
        return
    if payload.get("dimension") != 3 or payload.get("model_id") != (
        "task039_5nm_v3_1deg_s5_hybrid_direct_m480"
    ):
        raise ValueError("V3-7 requires the official 1-degree h5 Hybrid-direct model")
    incidence = payload.get("incidence")
    discretization = payload.get("discretization")
    boundary = payload.get("boundary")
    method = payload.get("method")
    execution = payload.get("execution")
    if not all(
        isinstance(section, Mapping)
        for section in (incidence, discretization, boundary, method, execution)
    ):
        raise ValueError("V3-7 resolved identity sections are incomplete")
    expected = (
        (incidence["wavelength_nm"], 5.0),
        (incidence["grazing_angle_deg"], 1.0),
        (incidence["azimuth_deg"], 0.0),
        (incidence["polarization"], "s"),
        (discretization["nedelec_degree"], 6),
        (discretization["visualization_degree"], 6),
        (discretization["mesh_target_nm"], 5.0),
        (method["kind"], "hybrid_direct"),
        (method["requested_modes_per_direction"], 480),
        (method["propagation_model"], "full3d_uniform_cg"),
        (method["traction_model"], "full3d_one_cell_exact_schur"),
        (boundary["vertical_boundary"], "dtn_port"),
        (boundary["dtn_order_policy"], "auto_propagating"),
        (boundary["dtn_assembly"], "auxiliary"),
        (boundary["use_pml"], False),
        (execution["mpi_size"], 8),
        (execution["warning_memory_gib"], V3_7_WARNING_GIB),
        (execution["terminate_memory_gib"], V3_7_CRITICAL_GIB),
        (execution["absolute_terminate_memory_bytes"], V3_7_ABSOLUTE_HARD_BYTES),
        (execution["require_zero_swap"], True),
    )
    if any(actual != required for actual, required in expected):
        raise ValueError("V3-7 official physical/discrete identity is not exact")
    inventory = payload.get("derived", {}).get("external_mode_inventory", {})
    keys = inventory.get("keys") if isinstance(inventory, Mapping) else None
    if not isinstance(keys, list) or len(keys) != 600:
        raise ValueError("V3-7 requires the exact 600-key external inventory")


def _watchdog_policy(
    payload: Mapping[str, Any], *, v5_h4_setup_only: bool = False
) -> dict[str, Any]:
    _validate_resolved_identity(payload, v5_h4_setup_only=v5_h4_setup_only)
    return {
        "warning_memory_gib": V3_7_WARNING_GIB,
        "critical_memory_gib": V3_7_CRITICAL_GIB,
        "critical_action": "record_checkpoint_only",
        "absolute_terminate_memory_bytes": V3_7_ABSOLUTE_HARD_BYTES,
        "absolute_hard_stop_action": "terminate_complete_process_tree",
        "require_zero_swap": True,
        "poll_interval_seconds": V3_7_POLL_SECONDS,
        "hard_stop_gib": V3_7_ABSOLUTE_HARD_BYTES / 2**30,
    }


def _check_direct_producer(run_root: Path) -> None:
    manifest_path = run_root.resolve() / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"V3-7 direct producer manifest is unavailable: {run_root}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V3-7 direct producer manifest is unreadable") from exc
    if not isinstance(manifest, Mapping) or any(
        (
            manifest.get("model_id") != "task039_5nm_v3_1deg_s5_hybrid_direct_m480",
            manifest.get("method") != "hybrid_direct",
            manifest.get("mpi_size") != 8,
            manifest.get("source_sha") != V3_7_DIRECT_PRODUCER_SHA,
        )
    ):
        raise ValueError(
            "V3-7 direct producer identity is not the fixed h5/M480/MPI8 run"
        )


def load_v3_7_official_payload(
    input_path: str | Path, *, v5_h4_setup_only: bool = False
) -> dict[str, Any]:
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    if v5_h4_setup_only:
        from benchmarks.task039_v4_h4_hybrid_direct import (
            validate_v4_h4_specification,
        )

        validate_v4_h4_specification(specification)
    _validate_resolved_identity(payload, v5_h4_setup_only=v5_h4_setup_only)
    return payload


def build_v3_7_execution_plan(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    qep_only: bool = False,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the explicit MPI8 child argv without importing the worker."""

    payload = load_v3_7_official_payload(input_path, v5_h4_setup_only=v5_h4_setup_only)
    policy = _watchdog_policy(payload, v5_h4_setup_only=v5_h4_setup_only)
    executable = str(Path(os.path.abspath(python_executable or sys.executable)))
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    if (
        sum(
            (
                bool(qep_only),
                bool(candidate_b_only),
                bool(candidate_c_only),
                bool(candidate_d_only),
                bool(candidate_d_qualified),
                bool(candidate_e_side_only),
                bool(v5_h4_setup_only),
            )
        )
        > 1
    ):
        raise ValueError(
            "QEP-only, Candidate-B-only, Candidate-C-only, Candidate-D-only, Candidate-D-qualified, Candidate-E-side-only, and V5 h4 setup-only routes are exclusive"
        )
    worker_module = (
        V3_7_QEP_ONLY_WORKER_MODULE
        if qep_only
        else "benchmarks.task039_v3_7_orchestration"
    )
    argv = [
        str(mpiexec),
        "-n",
        "8",
        executable,
        "-m",
        worker_module,
        "--worker",
        "--input",
        str(Path(input_path).resolve()),
        "--run-directory",
        str(Path(run_directory).resolve()),
        "--source-sha",
        source_sha,
        V3_7_WATCHDOG_AUTH_FLAG,
    ]
    if candidate_b_only:
        argv.append(V3_7_CANDIDATE_B_FLAG)
    if candidate_c_only:
        argv.append(V3_7_CANDIDATE_C_FLAG)
    if candidate_d_only:
        argv.append(V3_7_CANDIDATE_D_FLAG)
    if candidate_d_qualified:
        argv.append(V3_7_CANDIDATE_D_QUALIFIED_FLAG)
    if candidate_e_side_only:
        argv.append(V3_7_CANDIDATE_E_FLAG)
    if v5_h4_setup_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
            )
        ):
            raise ValueError("V5 h4 setup-only requires the shared packet arguments")
        argv.extend(
            [
                V5_H4_SETUP_ONLY_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
            ]
        )
    if candidate_d_qualified:
        method = V3_8_CANDIDATE_D_QUALIFIED_METHOD
    elif candidate_d_only:
        method = "USER_AUTHORIZED_EXPERIMENTAL_HYBRIDIZED_DIRECT_SIDE_CANDIDATE_D"
    elif candidate_e_side_only:
        method = "hybrid_iterative_candidate_e_side_only"
    elif v5_h4_setup_only:
        method = V5_H4_SETUP_ONLY_METHOD
    elif candidate_c_only:
        method = "hybrid_iterative_candidate_c1_only"
    elif candidate_b_only:
        method = "hybrid_iterative_candidate_b_only"
    elif qep_only:
        method = "positive_branch_qep_only"
    else:
        method = "hybrid_iterative_v3_7_diagnostic"
    return {
        "argv": argv,
        "shell": False,
        "launcher": "benchmarks.task039_v3_7_watchdog -> src.runners.task038_launcher",
        "watchdog": policy,
        "worker_contract": {
            "mpi_size": 8,
            "profile_id": (
                "task039.v5.h4.exact-side.setup-only.v1"
                if v5_h4_setup_only
                else V3_7_PROFILE_ID
            ),
            "method": method,
            "hard_stop_authority": "process_tree_rss_bytes",
            "critical_checkpoint_only": True,
            "swap_policy": "immediate_complete_process_tree_termination",
        },
    }


def v3_7_execution_dry_run(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    qep_only: bool = False,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    plan = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        qep_only=qep_only,
        candidate_b_only=candidate_b_only,
        candidate_c_only=candidate_c_only,
        candidate_d_only=candidate_d_only,
        candidate_d_qualified=candidate_d_qualified,
        candidate_e_side_only=candidate_e_side_only,
        v5_h4_setup_only=v5_h4_setup_only,
        selected_mode_packet_manifest=selected_mode_packet_manifest,
        selected_mode_packet_identity=selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
    )
    if plan["argv"][1:3] != ["-n", "8"]:
        raise ValueError("V3-7 execution plan is not fixed to MPI8")
    return plan


def launch_v3_7_with_task038_watchdog(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    sample_factory: Callable[[int], dict[str, Any]] = resource_authority_sample,
    terminate_factory: Callable[[Any], dict[str, Any]] = terminate_process_tree,
    qep_only: bool = False,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Run one authenticated V3-7 child through Task38's watchdog."""

    load_v3_7_official_payload(input_path, v5_h4_setup_only=v5_h4_setup_only)
    if not v5_h4_setup_only:
        _check_direct_producer(V3_7_DIRECT_RUN_ROOT)
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha.lower()
    ):
        raise ValueError("V3-7 source_sha must be a full hexadecimal commit SHA")
    specification = load_and_resolve(input_path)
    plan_payload = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
        qep_only=qep_only,
        candidate_b_only=candidate_b_only,
        candidate_c_only=candidate_c_only,
        candidate_d_only=candidate_d_only,
        candidate_d_qualified=candidate_d_qualified,
        candidate_e_side_only=candidate_e_side_only,
        v5_h4_setup_only=v5_h4_setup_only,
        selected_mode_packet_manifest=selected_mode_packet_manifest,
        selected_mode_packet_identity=selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
    )
    run_dir = Path(run_directory).resolve()
    if run_dir.exists():
        raise ValueError(f"V3-7 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    start_time = datetime.now(timezone.utc).isoformat()
    manifest, _resolved_sha = _write_bootstrap(
        specification,
        run_dir,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_watchdog",
        start_time=start_time,
    )
    executable = Path(os.path.abspath(python_executable or sys.executable))
    plan = ExecutionPlan(
        argv=tuple(plan_payload["argv"]),
        shell=False,
        executable=executable,
        worker_module=plan_payload["argv"][5],
        method=plan_payload["worker_contract"]["method"],
        mpi_size=8,
        requested_modes=480,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_watchdog",
        adapter_available=True,
        contract_probe=False,
        task039_trace_audit=False,
        expected_output_directory=run_dir,
        expected_resolved_config=run_dir / "resolved_config.json",
        expected_manifest=run_dir / "run_manifest.json",
    )
    result = _run_worker(
        plan,
        specification,
        run_dir,
        popen_factory=popen_factory,
        sample_factory=sample_factory,
        terminate_factory=terminate_factory,
        monotonic=time.monotonic,
        sleep=time.sleep,
        poll_interval=V3_7_POLL_SECONDS,
    )
    manifest.update(
        {
            "end_time": datetime.now(timezone.utc).isoformat(),
            "exit_status": result["exit_status"],
            "result_classification": result["result_classification"],
            "status": "finished",
        }
    )
    summary = {
        "status": "finished",
        "run_id": manifest["run_id"],
        "output_directory": str(run_dir),
        "numerical_output_directory": str(run_dir / "numerical_output"),
        **result,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"run_directory": str(run_dir), **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--python-executable")
    parser.add_argument("--mpiexec-command")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qep-only", action="store_true")
    parser.add_argument("--candidate-b-only", action="store_true")
    parser.add_argument("--candidate-c-only", action="store_true")
    parser.add_argument("--candidate-d-only", action="store_true")
    parser.add_argument("--candidate-d-qualified", action="store_true")
    parser.add_argument("--candidate-e-side-only", action="store_true")
    parser.add_argument("--v5-h4-setup-only", action="store_true")
    parser.add_argument("--selected-mode-packet-manifest")
    parser.add_argument("--selected-mode-packet-identity")
    parser.add_argument("--selected-mode-packet-manifest-sha256")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(
            json.dumps(
                v3_7_execution_dry_run(
                    args.input,
                    args.run_directory,
                    source_sha=args.source_sha,
                    python_executable=args.python_executable,
                    qep_only=args.qep_only,
                    candidate_b_only=args.candidate_b_only,
                    candidate_c_only=args.candidate_c_only,
                    candidate_d_only=args.candidate_d_only,
                    candidate_d_qualified=args.candidate_d_qualified,
                    candidate_e_side_only=args.candidate_e_side_only,
                    v5_h4_setup_only=args.v5_h4_setup_only,
                    selected_mode_packet_manifest=args.selected_mode_packet_manifest,
                    selected_mode_packet_identity=args.selected_mode_packet_identity,
                    selected_mode_packet_manifest_sha256=args.selected_mode_packet_manifest_sha256,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    result = launch_v3_7_with_task038_watchdog(
        args.input,
        args.run_directory,
        source_sha=args.source_sha,
        python_executable=args.python_executable,
        mpiexec_command=args.mpiexec_command,
        qep_only=args.qep_only,
        candidate_b_only=args.candidate_b_only,
        candidate_c_only=args.candidate_c_only,
        candidate_d_only=args.candidate_d_only,
        candidate_d_qualified=args.candidate_d_qualified,
        candidate_e_side_only=args.candidate_e_side_only,
        v5_h4_setup_only=args.v5_h4_setup_only,
        selected_mode_packet_manifest=args.selected_mode_packet_manifest,
        selected_mode_packet_identity=args.selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=args.selected_mode_packet_manifest_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("exit_status") == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "V3_7_ABSOLUTE_HARD_BYTES",
    "V3_7_DIRECT_RUN_ROOT",
    "V3_7_CANDIDATE_C_FLAG",
    "V3_7_CANDIDATE_D_FLAG",
    "V3_7_CANDIDATE_D_QUALIFIED_FLAG",
    "V3_7_CANDIDATE_E_FLAG",
    "V3_7_QEP_ONLY_WORKER_MODULE",
    "V3_8_CANDIDATE_D_QUALIFIED_METHOD",
    "build_v3_7_execution_plan",
    "launch_v3_7_with_task038_watchdog",
    "load_v3_7_official_payload",
    "main",
    "v3_7_execution_dry_run",
]
