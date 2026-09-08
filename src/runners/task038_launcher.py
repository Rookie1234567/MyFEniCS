"""Small Task38 provenance launcher and resource classification loop."""

from __future__ import annotations

import os
import json
import hashlib
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)

from src.io.execution_plan import (
    CONTRACT_PROBE_ADAPTER,
    ExecutionPlan,
    build_execution_plan,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.resolved_config import canonical_json_bytes, write_resolved_config
from src.io.run_specification import RunSpecification


PopenFactory = Callable[..., Any]
SampleFactory = Callable[[int], dict[str, Any]]
TerminateFactory = Callable[[Any], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_sha(cwd: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f"cannot determine git source SHA: {exc}") from exc
    value = completed.stdout.strip()
    if (
        len(value) != 40
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InputError("git source SHA is not a complete 40-character commit")
    return value


def _physical_source_gate(cwd: Path, expected_sha: str) -> dict:
    actual = _source_sha(cwd)
    status = subprocess.run(['git', 'status', '--porcelain'], cwd=cwd,
                            check=True, capture_output=True, text=True).stdout
    if actual != expected_sha or status.strip():
        raise InputError('physical-intermediate formal launch requires exact clean source SHA')
    gitdir = subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], cwd=cwd,
                            check=True, capture_output=True, text=True).stdout.strip()
    return {'source_sha': actual, 'tracked_and_nonignored_untracked_clean': True,
            'actual_git_directory': gitdir}


def _validate_source_sha(value: str) -> str:
    if (
        len(value) != 40
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InputError(
            "source SHA must be a complete 40-character lowercase hex value"
        )
    return value


def _environment_identity() -> dict[str, Any]:
    return {
        "python_executable": os.path.abspath(sys.executable),
        "platform": platform.platform(),
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _write_text_hash(path: Path, value: str) -> None:
    path.write_text(value + "\n", encoding="ascii")


def _timestamp_directory(
    specification: RunSpecification, timestamp: str | None
) -> Path:
    parent = Path(specification.expected_output_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    name = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = parent / name
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise InputError(f"Task38 output collision: {directory}") from exc
    return directory


def _base_manifest(
    specification: RunSpecification,
    *,
    run_directory: Path,
    source_sha: str,
    adapter_identity: str,
    start_time: str,
    resolved_sha: str,
) -> dict[str, Any]:
    snapshot = specification.as_jsonable()
    return {
        "model_id": snapshot["model_id"],
        "run_id": snapshot["run_id"],
        "comparison_group": snapshot["comparison_group"],
        "method": snapshot["method"]["kind"],
        "solver": snapshot["solver"],
        "mpi_size": snapshot["execution"]["mpi_size"],
        "requested_modes": snapshot["method"].get("requested_modes_per_direction"),
        "input_path": str(specification.source_path),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "source_sha": source_sha,
        "environment": _environment_identity(),
        "resolved_config_sha256": resolved_sha,
        "start_time": start_time,
        "end_time": None,
        "exit_status": None,
        "result_classification": "not_run",
        "status": "launching",
        "output_directory": str(run_directory),
        "numerical_output_directory": str(run_directory / "numerical_output"),
        "resolved_method_adapter": adapter_identity,
    }


def _initial_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "launching",
        "result_classification": "not_run",
        "exit_status": None,
        "run_id": manifest["run_id"],
        "output_directory": manifest["output_directory"],
        "numerical_output_directory": manifest["numerical_output_directory"],
        "resource_authority": {"status": "not_sampled"},
    }


def _write_bootstrap(
    specification: RunSpecification,
    run_directory: Path,
    *,
    source_sha: str,
    adapter_identity: str,
    start_time: str,
) -> tuple[dict[str, Any], str]:
    resolved_sha = write_resolved_config(
        specification, run_directory / "resolved_config.json"
    )
    (run_directory / "input_original.dat").write_bytes(specification.raw_input_bytes)
    _write_text_hash(run_directory / "input_sha256.txt", specification.input_sha256)
    _write_text_hash(
        run_directory / "physical_model_sha256.txt",
        specification.physical_model_sha256,
    )
    _write_text_hash(run_directory / "source_sha.txt", source_sha)
    manifest = _base_manifest(
        specification,
        run_directory=run_directory,
        source_sha=source_sha,
        adapter_identity=adapter_identity,
        start_time=start_time,
        resolved_sha=resolved_sha,
    )
    _write_json(run_directory / "run_manifest.json", manifest)
    _write_json(run_directory / "run_summary.json", _initial_summary(manifest))
    return manifest, resolved_sha


def _authority_readable(authority: dict[str, Any]) -> bool:
    process_tree = authority.get("process_tree", {})
    return bool(process_tree.get("all_status_readable"))


def _swap_bytes(authority: dict[str, Any]) -> int:
    process_tree = authority.get("process_tree", {})
    cgroup = authority.get("job_cgroup", {})
    dedicated_swap = (
        int(cgroup.get("swap_current_bytes") or 0)
        if cgroup.get("dedicated_job_cgroup")
        else 0
    )
    return max(
        int(process_tree.get("swap_bytes") or 0),
        dedicated_swap,
    )


def _run_worker(
    plan: ExecutionPlan,
    specification: RunSpecification,
    run_directory: Path,
    *,
    popen_factory: PopenFactory,
    sample_factory: SampleFactory,
    terminate_factory: TerminateFactory,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    poll_interval: float,
) -> dict[str, Any]:
    execution = specification.execution
    warning_limit = float(execution["warning_memory_gib"]) * 1024**3
    terminate_limit = float(execution["terminate_memory_gib"]) * 1024**3
    timeout = float(execution["timeout_seconds"])
    sample_count = 0
    peak_authority = 0
    peak_process_tree = 0
    peak_swap = 0
    zero_swap_observed = True
    warning_triggered = False
    termination: dict[str, Any] | None = None
    classification: str | None = None
    started = monotonic()
    stdout_path = run_directory / "worker_stdout.txt"
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = popen_factory(
            list(plan.argv),
            shell=False,
            cwd=Path(__file__).resolve().parents[2],
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        while True:
            authority = sample_factory(process.pid)
            if _authority_readable(authority):
                sample_count += 1
                memory = int(authority.get("memory_authority_bytes") or 0)
                process_tree_rss = int(
                    authority.get("process_tree", {}).get("rss_bytes") or 0
                )
                swap_bytes = _swap_bytes(authority)
                peak_authority = max(peak_authority, memory)
                peak_process_tree = max(peak_process_tree, process_tree_rss)
                peak_swap = max(peak_swap, swap_bytes)
                zero_swap_observed = zero_swap_observed and swap_bytes == 0
                warning_triggered = warning_triggered or memory >= warning_limit
                if execution["require_zero_swap"] and swap_bytes > 0:
                    termination = terminate_factory(process)
                    classification = "swap_policy_violation"
                elif memory >= terminate_limit:
                    termination = terminate_factory(process)
                    classification = "memory_terminate"
            if classification is not None:
                break
            if process.poll() is not None:
                break
            if monotonic() - started >= timeout:
                termination = terminate_factory(process)
                classification = "timeout"
                break
            sleep(poll_interval)
        if process.poll() is None:
            process.wait()
        exit_status = process.poll()

    if classification is None:
        if exit_status == 0 and plan.contract_probe:
            classification = "contract_probe_pass"
        else:
            classification = "worker_exit0" if exit_status == 0 else "worker_nonzero"
    return {
        "exit_status": exit_status,
        "result_classification": classification,
        "termination": termination,
        "resource_authority": {
            "status": "measured" if sample_count else "not_available",
            "sample_count": sample_count,
            "warning_triggered": warning_triggered,
            "process_tree_peak_rss_mb": peak_process_tree / 1024**2,
            "memory_authority_peak_mb": peak_authority / 1024**2,
            "process_tree_peak_swap_mb": peak_swap / 1024**2,
            "require_zero_swap": execution["require_zero_swap"],
            "zero_swap_observed": zero_swap_observed if sample_count else None,
        },
    }


def launch_specification(
    specification: RunSpecification,
    *,
    source_sha: str | None = None,
    timestamp: str | None = None,
    contract_probe: bool = False,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: PopenFactory = subprocess.Popen,
    sample_factory: SampleFactory = resource_authority_sample,
    terminate_factory: TerminateFactory = terminate_process_tree,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.25,
    pc_profile: dict | None = None,
) -> dict[str, Any]:
    """Launch one resolved input or fail closed before numerical execution."""

    workflow_started = monotonic()
    source = _validate_source_sha(
        source_sha
        if source_sha is not None
        else _source_sha(Path(__file__).resolve().parents[2])
    )
    from src.io.physical_intermediate_profile import PROFILES
    from src.io.physical_intermediate_profile import FAST_PROFILE, LIGHT_PROFILE, PACKED_PROFILE, profile_facts
    packed = specification.solver.get('preconditioner') == PACKED_PROFILE
    if specification.solver.get('preconditioner') in (FAST_PROFILE, PACKED_PROFILE) and pc_profile is None:
        raise InputError('fast backend is currently qualified for seven-PC diagnostic mode only')

    physical_candidate = specification.solver.get('preconditioner') in PROFILES and not contract_probe
    light = physical_candidate and specification.solver.get('preconditioner') == LIGHT_PROFILE
    physical_resources = profile_facts(specification.solver['preconditioner'])['resources'] if physical_candidate else {}
    if pc_profile is not None and not physical_candidate:
        raise InputError('PC timing mode requires a physical reference run')
    workflow_limit = (2400 if packed else 1800) if pc_profile is not None else physical_resources.get('workflow_seconds', 7200)
    solve_limit = physical_resources.get('solve_seconds', 3600)
    physical_source = (_physical_source_gate(Path(__file__).resolve().parents[2], source)
                       if physical_candidate else None)
    adapter = (
        CONTRACT_PROBE_ADAPTER
        if contract_probe
        else method_adapter_identity(str(specification.method["kind"]))
    )
    run_directory = _timestamp_directory(specification, timestamp)
    start_time = _now()
    manifest, _resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=source,
        adapter_identity=adapter,
        start_time=start_time,
    )
    if pc_profile is not None:
        from .physical_pc_profile import CHECKPOINT_MANIFEST_SHA, CHECKPOINT_SOLUTION_SHA, SCHEDULE
        from .physical_pc_profile import PACKED_CHECKPOINT_MANIFEST_SHA, PACKED_CHECKPOINT_SOLUTION_SHA, paired_schedule

        recovery = pc_profile.get('recovery_from', pc_profile.get('cache_recovery_from'))
        if pc_profile.get('r0_reference', {}).get('source_sha') == source:
            raise InputError('R1 requires a new clean source SHA')
        if recovery is not None and source == recovery['source_sha']:
            raise InputError('profile recovery requires a new clean source SHA')
        cache_home = run_directory/'jit_cache'
        cache_home.mkdir(exist_ok=False)
        cache_empty = not any(cache_home.iterdir())
        if not cache_empty:
            raise InputError('profile JIT cache must be independently empty before launch')
        pc_profile = dict(pc_profile, diagnostic_only=True,
            schedule=paired_schedule(pc_profile.get('checkpoint_available', True)) if packed else SCHEDULE,
            cache_home=str(cache_home.resolve()), cache_empty_before_launch=cache_empty,
            checkpoint_manifest_sha256=PACKED_CHECKPOINT_MANIFEST_SHA if packed else CHECKPOINT_MANIFEST_SHA,
            checkpoint_solution_sha256=PACKED_CHECKPOINT_SOLUTION_SHA if packed else CHECKPOINT_SOLUTION_SHA, source_sha=source,
            input_sha256=specification.input_sha256, resolved_config_sha256=_resolved_sha)
        diagnostic_path = run_directory/'pc_profile_config.json'
        _write_json(diagnostic_path, pc_profile)
        manifest['pc_profile'] = dict(config=diagnostic_path.name,
            sha256=hashlib.sha256(diagnostic_path.read_bytes()).hexdigest(), **pc_profile)
        _write_json(run_directory/'run_manifest.json', manifest)
    if light:
        cache_home = run_directory/'jit_cache'
        cache_home.mkdir(exist_ok=False)
        manifest['execution_cache'] = dict(path=str(cache_home.resolve()), empty_before_launch=not any(cache_home.iterdir()))
        _write_json(run_directory/'run_manifest.json', manifest)
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=source,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
        adapter_identity=adapter,
        contract_probe=contract_probe,
    )
    if not plan.adapter_available:
        result = {
            "exit_status": None,
            "result_classification": "adapter_unavailable",
            "resource_authority": {"status": "not_sampled"},
        }
    else:
        try:
            if physical_candidate:
                from benchmarks.subreaper_watchdog import supervise

                authority = supervise(list(plan.argv), run_directory / 'watchdog',
                    wall_seconds=max(1e-9, min(workflow_limit-(monotonic()-workflow_started),
                        pc_profile['deadline_monotonic']-monotonic()) if pc_profile is not None
                        else workflow_limit-(monotonic()-workflow_started)),
                    solve_seconds=None if pc_profile is not None else solve_limit,
                    phase_path=run_directory / 'workflow_phase.json',
                    cache_path=Path(pc_profile['cache_home']) if pc_profile is not None else cache_home if light else
                        Path(os.environ['XDG_CACHE_HOME']) if 'XDG_CACHE_HOME' in os.environ else None,
                    source_state=physical_source,
                    **(dict(grace_seconds=60 if packed else 30, hard_stop_immediate=True,
                            cooperative_performance_stop=packed,
                            worker_environment={'PHYSICAL_PC_PROFILE': json.dumps(pc_profile),
                                                'XDG_CACHE_HOME': pc_profile['cache_home']})
                       if pc_profile is not None else dict(grace_seconds=60, hard_stop_immediate=True,
                            cooperative_performance_stop=True,
                            worker_environment={'XDG_CACHE_HOME': str(cache_home.resolve())}) if light else {}))
                result = {'exit_status': authority['leader_exit_code'],
                    'result_classification': 'worker_exit0' if authority['classification'] == 'COMPLETED' else authority['classification'],
                    'resource_authority': authority}
                try:
                    source_after = _physical_source_gate(Path(__file__).resolve().parents[2], source)
                except (InputError, OSError, subprocess.CalledProcessError) as exc:
                    source_after = {'provenance_passed': False, 'error': str(exc)}
                    result['result_classification'] = 'EVIDENCE_INCOMPLETE'
                zero_swap = authority['job_swap_activity'] == 'zero_supported_by_zero_global_activity'
                result['job_swap_qualification'] = 'qualified_zero' if zero_swap else 'UNRESOLVED'
                if not zero_swap and result['result_classification'] == 'worker_exit0':
                    result['result_classification'] = 'EVIDENCE_INCOMPLETE'
                manifest['requested_legacy_resource_fields'] = {
                    key: specification.execution[key] for key in
                    ('warning_memory_gib', 'terminate_memory_gib', 'memory_limit_gb')}
                manifest['source_after'] = source_after
                manifest['effective_watchdog_authority'] = {
                    'launch_envelope': authority['launch_envelope'], 'warning_fraction': 0.85,
                    'workflow_seconds': workflow_limit, 'solve_seconds': None if pc_profile is not None else solve_limit,
                    'scope': authority['memory_scope'], 'legacy_resource_fields_enforced': False}
            else:
                result = _run_worker(
                    plan, specification, run_directory, popen_factory=popen_factory,
                    sample_factory=sample_factory, terminate_factory=terminate_factory,
                    monotonic=monotonic, sleep=sleep, poll_interval=poll_interval,
                )
        except OSError as exc:
            result = {
                "exit_status": None,
                "result_classification": "worker_launch_error",
                "error": str(exc),
                "resource_authority": {"status": "not_sampled"},
            }
    end_time = _now()
    if physical_candidate:
        result['full_workflow_monotonic_seconds'] = monotonic()-workflow_started
        if result['full_workflow_monotonic_seconds'] > workflow_limit:
            result['result_classification'] = 'PERFORMANCE_CONTROLLED_STOP'
    manifest.update(
        {
            "end_time": end_time,
            "exit_status": result["exit_status"],
            "result_classification": result["result_classification"],
            "status": "finished",
        }
    )
    summary = {
        "status": "finished",
        "run_id": manifest["run_id"],
        "output_directory": str(run_directory),
        "numerical_output_directory": str(run_directory / "numerical_output"),
        **result,
    }
    _write_json(run_directory / "run_manifest.json", manifest)
    _write_json(run_directory / "run_summary.json", summary)
    return {
        "run_directory": str(run_directory),
        "manifest": str(run_directory / "run_manifest.json"),
        "summary": str(run_directory / "run_summary.json"),
        **result,
    }


__all__ = ["launch_specification"]
