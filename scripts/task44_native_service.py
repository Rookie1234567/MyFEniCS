"""Task44-only service binding around the public runner and shared watchdog."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GIB = 1024**3
HOST_RESERVE_BYTES = 384 * GIB
INITIAL_CAP_BYTES = 128 * GIB
JOB_BUFFER_BYTES = 8 * GIB
BRANCH = "task44_sixlayer_surrogate_0p7nm"


def verify_task44_root(repo_root: Path, environ: Mapping[str, str]) -> None:
    if environ.get("MYFENICS_NATIVE_COMPLEX_ENV") != "1":
        raise RuntimeError("Task44 execution requires the native complex ABI activation")
    if environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") is not None:
        raise RuntimeError("Task44 native execution rejects a stale WSL activation marker")
    configured = environ.get("MYFENICS_TASK44_ROOT")
    if not configured or Path(configured).resolve(strict=True) != repo_root.resolve(strict=True):
        raise RuntimeError("MYFENICS_TASK44_ROOT does not identify this Task44 worktree")


def _run(argv: list[str], *, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            argv, cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "")
        raise RuntimeError(f"command failed: {argv[0]}: {detail or exc}") from exc


def _active_units() -> list[str]:
    output = _run([
        "systemctl", "--user", "list-units", "--type=service", "--state=running",
        "--no-legend", "--no-pager",
    ])
    return sorted({line.split()[0] for line in output.splitlines() if line.split()})


def _unit_facts(unit: str) -> dict[str, Any]:
    output = _run([
        "systemctl", "--user", "show", unit, "--no-pager",
        "-p", "ControlGroup", "-p", "MemoryMax", "-p", "MemorySwapMax",
        "-p", "ActiveState", "-p", "CPUAffinity", "-p", "MainPID",
        "-p", "InvocationID", "-p", "Restart", "-p", "KillMode",
    ])
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    if set(values) != {
        "ControlGroup", "MemoryMax", "MemorySwapMax", "ActiveState", "CPUAffinity",
        "MainPID", "InvocationID", "Restart", "KillMode",
    }:
        raise RuntimeError(f"systemd returned incomplete properties for {unit}")
    cgroup = Path("/sys/fs/cgroup") / values["ControlGroup"].lstrip("/")
    try:
        memory_current = int((cgroup / "memory.current").read_text().strip())
        memory_max = int((cgroup / "memory.max").read_text().strip())
        swap_current = int((cgroup / "memory.swap.current").read_text().strip())
        swap_max_text = (cgroup / "memory.swap.max").read_text().strip()
        swap_max = None if swap_max_text == "max" else int(swap_max_text)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read dedicated cgroup for {unit}: {exc}") from exc
    if values["MemoryMax"] == "infinity" or values["MemorySwapMax"] == "infinity":
        raise RuntimeError(f"Task44 service {unit} has an unlimited memory property")
    return {
        "unit": unit,
        "active_state": values["ActiveState"],
        "main_pid": int(values["MainPID"]),
        "invocation_id": values["InvocationID"],
        "restart": values["Restart"],
        "kill_mode": values["KillMode"],
        "cpu_affinity": values["CPUAffinity"],
        "control_group": values["ControlGroup"],
        "memory_max_bytes": int(values["MemoryMax"]),
        "memory_current_bytes": memory_current,
        "cgroup_memory_max_bytes": memory_max,
        "swap_max_bytes": int(values["MemorySwapMax"]),
        "cgroup_swap_max_bytes": swap_max,
        "swap_current_bytes": swap_current,
    }


def _parse_cpu_list(value: str) -> set[int]:
    result: set[int] = set()
    for token in value.replace(",", " ").split():
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise RuntimeError(f"invalid CPU affinity range: {token}")
            result.update(range(start, end + 1))
        else:
            result.add(int(token))
    return result


def _pid_start_ticks(pid: int) -> int:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    return int(stat[stat.rfind(")") + 2 :].split()[19])


def _write_service_identity(
    unit: str, repo_root: Path, expected_cpus: set[int], cap_bytes: int
) -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import current_cgroup_path

    facts = _unit_facts(unit)
    own_cpus = set(os.sched_getaffinity(0))
    own_cgroup = current_cgroup_path(os.getpid())
    expected_cgroup = Path("/sys/fs/cgroup") / facts["control_group"].lstrip("/")
    if (
        facts["main_pid"] != os.getpid()
        or not facts["invocation_id"]
        or facts["active_state"] != "active"
        or facts["restart"] != "no"
        or facts["kill_mode"] != "control-group"
        or facts["memory_max_bytes"] != cap_bytes
        or facts["cgroup_memory_max_bytes"] != cap_bytes
        or facts["swap_max_bytes"] != 0
        or facts["cgroup_swap_max_bytes"] != 0
        or facts["swap_current_bytes"] != 0
        or _parse_cpu_list(facts["cpu_affinity"]) != expected_cpus
        or own_cpus != expected_cpus
        or own_cgroup is None
        or expected_cgroup.resolve(strict=True) != own_cgroup.resolve(strict=True)
    ):
        raise RuntimeError(f"Task44 service process identity does not match its unit: {facts}")
    receipt = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "service_unit": unit,
        "main_pid": os.getpid(),
        "main_pid_start_ticks": _pid_start_ticks(os.getpid()),
        "invocation_id": facts["invocation_id"],
        "control_group": facts["control_group"],
        "active_state": facts["active_state"],
        "memory_max_bytes": facts["memory_max_bytes"],
        "memory_swap_max_bytes": facts["swap_max_bytes"],
        "restart": facts["restart"],
        "kill_mode": facts["kill_mode"],
        "cpu_affinity": sorted(expected_cpus),
        "actual_process_cpu_affinity": sorted(own_cpus),
        "working_directory": str(repo_root),
    }
    path = repo_root / "benchmarks/artifacts/task44_native_services" / unit / "service_identity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _task44_services(units: list[str]) -> list[dict[str, Any]]:
    return [
        _unit_facts(unit)
        for unit in units
        if unit.startswith("task44-sample-") and unit.endswith(".service")
    ]


def _numerical_processes() -> list[dict[str, Any]]:
    text = _run(["ps", "-eo", "pid=,ppid=,comm=,args="])
    marker = re.compile(r"python|mpiexec|mpirun|dolfinx|petsc|slepc|gmsh|fenics|pytest", re.IGNORECASE)
    result = []
    for line in text.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) < 3:
            continue
        command = fields[3] if len(fields) == 4 else fields[2]
        if marker.search(f"{fields[2]} {command}"):
            try:
                status = Path(f"/proc/{fields[0]}/status").read_text(encoding="utf-8")
                allowed = next(
                    (line.split(":", 1)[1].strip() for line in status.splitlines()
                     if line.startswith("Cpus_allowed_list:")),
                    None,
                )
            except OSError:
                allowed = None
            result.append({
                "pid": int(fields[0]), "ppid": int(fields[1]),
                "comm": fields[2], "command": command[:240],
                "cpus_allowed_list": allowed,
            })
    return result


def _input_facts(path: Path, repo_root: Path) -> dict[str, Any]:
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized

    resolved_path = path.resolve(strict=True)
    resolved_path.relative_to(repo_root.resolve(strict=True))
    spec = load_and_resolve(resolved_path)
    config = simulation_config_3d_from_normalized(spec.as_jsonable())
    execution = spec.execution
    if (
        spec.identity.get("model_id") != "task44_sixlayer_0p7nm"
        or len(config.grating_layers) != 6
        or execution.get("mpi_size") != 1
        or execution.get("timeout_seconds") != 0
    ):
        raise RuntimeError("input does not satisfy the six-layer, MPI1, no-timeout Task44 contract")
    thread_variables = (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
    )
    threads = {name: os.environ.get(name) for name in thread_variables}
    if any(value != "1" for value in threads.values()):
        raise RuntimeError(f"Task44 requires every math thread count to be 1: {threads}")
    return {
        "path": str(resolved_path),
        "sha256": spec.input_sha256,
        "model_id": spec.identity["model_id"],
        "run_id": spec.identity["run_id"],
        "layer_count": len(config.grating_layers),
        "mpi_size": execution["mpi_size"],
        "timeout_seconds": execution["timeout_seconds"],
        "thread_controls": threads,
    }


def _admission_facts(cap_bytes: int, max_concurrent: int) -> dict[str, Any]:
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        memory_envelope,
    )

    units = _active_units()
    services = _task44_services(units)
    if len(services) + 1 > max_concurrent:
        raise RuntimeError(
            f"starting a sample would exceed the concurrency limit {max_concurrent}; "
            f"running Task44 services: {[row['unit'] for row in services]}"
        )
    if any(
        row["active_state"] != "active"
        or row["memory_max_bytes"] != row["cgroup_memory_max_bytes"]
        or row["swap_max_bytes"] != 0
        or row["cgroup_swap_max_bytes"] != 0
        for row in services
    ):
        raise RuntimeError("an active Task44 neighbor has unreadable or unqualified cgroup limits")
    envelope = memory_envelope(
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        host_reserve_bytes=HOST_RESERVE_BYTES,
        task_cgroup_reserve_bytes=0,
        require_cgroup_memory_details=True,
    )
    caps = [row["memory_max_bytes"] for row in services] + [cap_bytes]
    currents = [row["memory_current_bytes"] for row in services] + [0]
    buffers = [max(JOB_BUFFER_BYTES, int(cap * 0.05)) for cap in caps]
    uncommitted = sum(max(cap - current, 0) for cap, current in zip(caps, currents))
    host_required = HOST_RESERVE_BYTES + uncommitted + sum(buffers)
    cgroup_required = uncommitted + sum(buffers)
    host_available = int(envelope["host_mem_available_bytes"])
    cgroup_available = int(envelope["task_cgroup_available_bytes"])
    result = {
        "host_mem_available_bytes": host_available,
        "host_reserve_bytes": HOST_RESERVE_BYTES,
        "task_cgroup_available_bytes": cgroup_available,
        "active_task44_services": services,
        "planned_cap_bytes": cap_bytes,
        "planned_and_active_buffers_bytes": buffers,
        "uncommitted_job_capacity_bytes": uncommitted,
        "required_host_available_bytes": host_required,
        "required_cgroup_available_bytes": cgroup_required,
        "host_headroom_after_reserve_bytes": host_available - host_required,
        "cgroup_headroom_after_job_budgets_bytes": cgroup_available - cgroup_required,
        "memory_envelope": envelope,
    }
    if host_available < host_required or cgroup_available < cgroup_required:
        raise RuntimeError("host reserve, job buffers, or ancestor cgroup headroom gate failed")
    return result


def _exact_service_guard(
    unit: str, cap_bytes: int, max_concurrent: int, expected_cpus: set[int]
) -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import cgroup_snapshot, current_cgroup_path

    try:
        units = _active_units()
        services = _task44_services(units)
        facts = _unit_facts(unit)
        own_cgroup = current_cgroup_path(os.getpid())
        expected_cgroup = Path("/sys/fs/cgroup") / facts["control_group"].lstrip("/")
        snapshot = cgroup_snapshot(os.getpid())
        failures = []
        if facts["active_state"] != "active":
            failures.append("unit_not_active")
        if own_cgroup is None or own_cgroup.resolve(strict=True) != expected_cgroup.resolve(strict=True):
            failures.append("service_cgroup_identity_mismatch")
        if facts["memory_max_bytes"] != cap_bytes or facts["cgroup_memory_max_bytes"] != cap_bytes:
            failures.append("service_memory_max_mismatch")
        if facts["swap_max_bytes"] != 0 or facts["cgroup_swap_max_bytes"] != 0:
            failures.append("service_swap_max_mismatch")
        if facts["swap_current_bytes"] != 0 or snapshot.get("swap_current_bytes") != 0:
            failures.append("service_swap_nonzero_or_unreadable")
        if snapshot.get("readable") is not True or snapshot.get("dedicated_job_cgroup") is not True:
            failures.append("service_cgroup_unreadable_or_not_dedicated")
        active_names = {row["unit"] for row in services}
        if unit not in active_names or len(services) > max_concurrent:
            failures.append("task44_concurrency_gate_failed")
        if _parse_cpu_list(facts["cpu_affinity"]) != expected_cpus:
            failures.append("service_cpu_affinity_property_mismatch")
        actual_affinities: dict[str, list[int]] = {}
        service_pids = (
            {
                int(pid)
                for path in expected_cgroup.rglob("cgroup.procs")
                for pid in path.read_text(encoding="ascii").split()
            }
            if own_cgroup is not None
            else set()
        )
        for pid in service_pids:
            try:
                actual = set(os.sched_getaffinity(pid))
            except (ProcessLookupError, PermissionError, OSError):
                failures.append(f"service_pid_affinity_unreadable:{pid}")
                continue
            actual_affinities[str(pid)] = sorted(actual)
            if actual != expected_cpus:
                failures.append(f"service_pid_affinity_mismatch:{pid}")
        return {
            "stop": bool(failures),
            "reason": "MONITORING_FAILED" if failures else None,
            "failures": failures,
            "unit": unit,
            "service": facts,
            "cgroup_snapshot": snapshot,
            "active_user_services": units,
            "active_task44_services": services,
            "expected_cpu_affinity": sorted(expected_cpus),
            "service_pid_affinities": actual_affinities,
        }
    except Exception as exc:  # noqa: BLE001 - any monitor error must fail closed.
        return {
            "stop": True,
            "reason": "MONITORING_FAILED",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }


def _source_facts(repo_root: Path) -> dict[str, Any]:
    branch = _run(["git", "branch", "--show-current"], cwd=repo_root)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    status = _run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=repo_root)
    if branch != BRANCH or status:
        raise RuntimeError("Task44 formal service requires a clean worktree on the exact execution branch")
    return {"branch": branch, "source_sha": sha, "worktree_clean": True}


def preflight(
    input_path: Path, *, max_concurrent: int, cap_bytes: int,
    cpu_affinity: set[int],
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    verify_task44_root(repo_root, os.environ)
    from src.runners.task038_launcher import _environment_identity

    environment = _environment_identity()
    if environment["runtime_profile"] != "native_linux_complex":
        raise RuntimeError("native environment identity did not resolve to native Linux complex runtime")
    native = environment.get("native_complex_identity") or {}
    if "complex128" not in str(native.get("petsc_scalar_type")) or native.get("mpi_size") != 1:
        raise RuntimeError("Task44 requires complex128 PETSc and a one-rank native MPI identity")
    if not cpu_affinity or not cpu_affinity.issubset(os.sched_getaffinity(0)):
        raise RuntimeError("selected Task44 CPU affinity is empty or outside the current allowed CPU set")
    source = _source_facts(repo_root)
    inputs = _input_facts(input_path, repo_root)
    neighbors = _numerical_processes()
    resources = _admission_facts(cap_bytes, max_concurrent)
    return {
        "status": "preflight_pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(repo_root),
        "source": source,
        "input": inputs,
        "environment": environment,
        "active_user_services": _active_units(),
        "numerical_neighbor_processes": neighbors,
        "resources": resources,
        "max_concurrent": max_concurrent,
        "service_memory_max_bytes": cap_bytes,
        "service_memory_swap_max_bytes": 0,
        "selected_cpu_affinity": sorted(cpu_affinity),
    }


def run_service(
    input_path: Path, *, unit: str, max_concurrent: int, cap_bytes: int,
    cpu_affinity: set[int], smoke: bool = False,
) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    verify_task44_root(repo_root, os.environ)
    source = _source_facts(repo_root)
    inputs = _input_facts(input_path, repo_root)
    identity = _write_service_identity(unit, repo_root, cpu_affinity, cap_bytes)
    guard = _exact_service_guard(unit, cap_bytes, max_concurrent, cpu_affinity)
    if guard["stop"]:
        raise RuntimeError(f"Task44 exact-service startup gate failed: {guard}")
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        supervise,
    )
    from src.runners.physical_v14_budget import V14_TIME_POLICY_OBSERVE_ONLY
    from src.runners.task038_launcher import _environment_identity

    artifacts = repo_root / "benchmarks/artifacts/task44_native_services" / unit
    watchdog_directory = artifacts / "watchdog"
    print(
        f"Task44 service unit={unit} supervisor_pid={os.getpid()} "
        f"input_sha256={inputs['sha256']} source_sha={source['source_sha']}",
        flush=True,
    )
    command = [
        sys.executable,
        str(repo_root / "scripts/run_case.py"),
        str(inputs["path"]),
    ]
    if smoke:
        command.append("--dry-run")
    summary = supervise(
        command,
        watchdog_directory,
        wall_seconds=86400.0,
        interval=5.0,
        grace_seconds=10.0,
        hard_stop_immediate=True,
        time_policy=V14_TIME_POLICY_OBSERVE_ONLY,
        memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        pss_sampling_policy="disabled_by_profile",
        tree_cap_bytes=cap_bytes,
        allow_physical_pressure_tree_cap=True,
        require_job_cgroup_zero_swap=True,
        require_cgroup_memory_details=True,
        host_reserve_bytes=HOST_RESERVE_BYTES,
        task_cgroup_reserve_bytes=JOB_BUFFER_BYTES,
        external_guard=lambda: _exact_service_guard(
            unit, cap_bytes, max_concurrent, cpu_affinity
        ),
        worker_environment={
            "MYFENICS_NATIVE_COMPLEX_ENV": "1",
            "MYFENICS_TASK44_ROOT": str(repo_root),
        },
        source_state={
            **source,
            "service_unit": unit,
            "service_identity": identity,
            "input_path": inputs["path"],
            "input_sha256": inputs["sha256"],
            "execution_mode": "public_runner_dry_run_smoke" if smoke else "public_runner_full3d",
            "native_environment": _environment_identity(),
            "time_policy": "observe_only; no wall-time termination",
        },
    )
    summary["task44_service"] = {
        "service_unit": unit,
        "input": inputs,
        "source": source,
        "service_gate_start": guard,
        "resource_authority_samples": str(watchdog_directory / "resources.jsonl"),
        "runner_log": str(watchdog_directory / "worker.log"),
        "wall_time_termination": "disabled_by_time_policy_observe_only",
        "smoke": smoke,
    }
    (artifacts / "service_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Task44 service finished unit={unit} classification={summary.get('classification')} "
        f"elapsed_seconds={summary.get('elapsed_seconds')}",
        flush=True,
    )
    return 0 if summary.get("classification") == "COMPLETED" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--cpu-affinity", required=True)
    parser.add_argument("--max-concurrent", type=int, choices=(1, 2), default=1)
    parser.add_argument("--cap-bytes", type=int, default=INITIAL_CAP_BYTES)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cpu_affinity = _parse_cpu_list(args.cpu_affinity)
        if args.preflight:
            result = preflight(
                args.input, max_concurrent=args.max_concurrent, cap_bytes=args.cap_bytes,
                cpu_affinity=cpu_affinity,
            )
            print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
            return 0
        if args.cap_bytes != INITIAL_CAP_BYTES:
            raise RuntimeError("Task44 initial service cap must not exceed 128 GiB")
        return run_service(
            args.input,
            unit=args.unit,
            max_concurrent=args.max_concurrent,
            cap_bytes=args.cap_bytes,
            cpu_affinity=cpu_affinity,
            smoke=args.smoke,
        )
    # Convert any uncaught gate failure to a clear service exit.
    except Exception as exc:  # noqa: BLE001
        print(f"Task44 service gate failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
