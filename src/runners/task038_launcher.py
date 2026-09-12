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
from typing import Any, Callable, Mapping

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


def _git_argv(cwd: Path, *args: str) -> list[str]:
    """Use the canonical split-git worktree when this repository has one."""

    gitdir = cwd / ".git-codex"
    if gitdir.is_dir():
        return [
            "git",
            "--git-dir",
            str(gitdir),
            "--work-tree",
            str(cwd),
            *args,
        ]
    return ["git", *args]


def _source_sha(cwd: Path) -> str:
    try:
        completed = subprocess.run(
            _git_argv(cwd, "rev-parse", "HEAD"),
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
    status = subprocess.run(_git_argv(cwd, 'status', '--porcelain'), cwd=cwd,
                            check=True, capture_output=True, text=True).stdout
    if actual != expected_sha or status.strip():
        raise InputError('physical-intermediate formal launch requires exact clean source SHA')
    gitdir = subprocess.run(_git_argv(cwd, 'rev-parse', '--absolute-git-dir'), cwd=cwd,
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


V14_SHARED_WORKFLOW_SECONDS = 43_200.0


def _write_v14_ledger(path: Path, ledger: dict[str, Any]) -> None:
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('wb') as stream:
        stream.write(canonical_json_bytes(ledger) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _v14_shared_ledger_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "benchmarks"
        / "artifacts"
        / "task39extra"
        / "p4_schur_v14"
        / "review_v14"
        / "shared_workflow_ledger.json"
    )


def _reserve_v14_shared_budget(
    repo_root: Path,
    run_directory: Path,
    *,
    source_sha: str,
    stage: str,
    stage_budget: Mapping[str, Any],
    workflow_clock_start: Mapping[str, Any],
) -> dict[str, Any]:
    """Reserve one stage slice in the fixed batch ledger before launch."""

    path = _v14_shared_ledger_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ledger = json.loads(path.read_text(encoding="utf-8"))
        if ledger.get("batch_identity") != "review_v14":
            raise InputError("V14 shared ledger batch identity changed")
    else:
        ledger = {
            "schema": "task039extra.v14.shared-workflow-ledger.v1",
            "batch_identity": "review_v14",
            "total_budget_seconds": V14_SHARED_WORKFLOW_SECONDS,
            "elapsed_seconds": 0.0,
            "fresh_worker_count": 0,
            "unique_bug_replay_count": 0,
            "replay_policy": "one evidenced implementation-bug replay in the entire batch; no mathematical retry",
            "source_attempts": [],
            "stages": {},
        }
    for old_stage, old_record in ledger['stages'].items():
        if old_record.get('active_attempt') is not None:
            raise InputError(f'V14 attempt {old_stage} is unsettled; preserve and settle its evidence before another launch')
    elapsed = float(ledger.get("elapsed_seconds", 0.0))
    remaining = V14_SHARED_WORKFLOW_SECONDS - elapsed
    workflow_budget = float(stage_budget["workflow_seconds"])
    if remaining <= 0 or workflow_budget <= 0:
        raise InputError("V14 shared 43200-second budget is unavailable")
    stage_record = dict(ledger.get("stages", {}).get(stage, {}))
    attempts = list(stage_record.get("attempts", []))
    if len(attempts) >= 2:
        raise InputError(f"V14 stage {stage} has exhausted its one-replay allowance")
    if attempts and attempts[-1].get("source_sha") == source_sha:
        raise InputError(f"V14 stage {stage} cannot replay the same source SHA")
    replay = bool(attempts)
    replay_evidence = None
    if replay:
        if int(ledger['unique_bug_replay_count']) >= 1:
            raise InputError('V14 entire batch has exhausted its one implementation-bug replay')
        previous = attempts[-1]
        evidence_path = Path(previous['run_directory']) / 'implementation_bug_replay.json'
        if not evidence_path.is_file():
            raise InputError('V14 replay requires implementation_bug_replay.json in the failed attempt directory')
        evidence_bytes = evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes)
        expected = {'classification': 'IMPLEMENTATION_BUG', 'stage': stage,
                    'failed_source_sha': previous['source_sha'], 'fixed_source_sha': source_sha}
        if any(evidence.get(key) != value for key, value in expected.items()) or not evidence.get('bug_and_fix'):
            raise InputError('V14 bug replay evidence does not bind the failed and corrected attempt')
        replay_evidence = dict(path=str(evidence_path), sha256=hashlib.sha256(evidence_bytes).hexdigest(), **evidence)
    reservation = min(workflow_budget, remaining)
    attempt = {
        "source_sha": source_sha,
        "run_directory": str(run_directory),
        "status": "RESERVED",
        "attempt": len(attempts) + 1,
        "replay": replay,
        "replay_evidence": replay_evidence,
        "workflow_clock_start": dict(workflow_clock_start),
        "reserved_timestamp_ns": time.time_ns(),
        "reserved_seconds": reservation,
        "elapsed_before_seconds": elapsed,
    }
    attempts.append(attempt)
    stage_record.update({"attempts": attempts, "active_attempt": len(attempts) - 1})
    ledger["stages"] = dict(ledger.get("stages", {}))
    ledger["stages"][stage] = stage_record
    ledger["source_attempts"] = list(ledger.get("source_attempts", []))
    ledger["source_attempts"].append(
        {"stage": stage, "source_sha": source_sha, "attempt": len(attempts)}
    )
    ledger["fresh_worker_count"] = int(ledger.get("fresh_worker_count", 0)) + 1
    if replay:
        ledger["unique_bug_replay_count"] = int(
            ledger.get("unique_bug_replay_count", 0)
        ) + 1
    _write_v14_ledger(path, ledger)
    return {
        "path": str(path),
        "stage": stage,
        "attempt_index": len(attempts) - 1,
        "reserved_seconds": reservation,
        "elapsed_before_seconds": elapsed,
        "replay": replay,
    }


def _settle_v14_shared_budget(
    lease: Mapping[str, Any],
    *,
    status: str,
    authority: Mapping[str, Any] | None,
    parent_interval: Mapping[str, Any],
    parent_clock_end: Mapping[str, Any],
) -> None:
    """Settle a lease from the parent watchdog, including hard kills."""

    path = Path(str(lease["path"]))
    ledger = json.loads(path.read_text(encoding="utf-8"))
    stage = str(lease["stage"])
    stage_record = dict(ledger.get("stages", {}).get(stage, {}))
    attempts = list(stage_record.get("attempts", []))
    index = int(lease["attempt_index"])
    if not 0 <= index < len(attempts):
        raise InputError("V14 shared ledger lease disappeared before settlement")
    attempt = dict(attempts[index])
    if 'settled_seconds' in attempt:
        raise InputError('V14 attempt was already settled')
    settled = float(parent_interval['budget_seconds'])
    # Preserve UTC excursions captured by the frequent watchdog samples even
    # if UTC returns before the parent's final sample. Prefix/suffix include
    # preflight, evidence writing and cleanup outside the supervised worker.
    if authority is not None and authority.get('clock_start') and authority.get('clock_end'):
        from .workflow_timebase import checked_interval, CONSERVATIVE_REALTIME
        prefix = checked_interval(attempt['workflow_clock_start'], authority['clock_start'], policy=CONSERVATIVE_REALTIME)
        suffix = checked_interval(authority['clock_end'], parent_clock_end, policy=CONSERVATIVE_REALTIME)
        supervised = authority.get('workflow_clock_interval', {}).get('budget_seconds', authority['elapsed_seconds'])
        settled = max(settled, prefix['budget_seconds'] + float(supervised) + suffix['budget_seconds'])
    attempt.update(
        {
            "status": str(status),
            "settled_timestamp_ns": time.time_ns(),
            "settled_seconds": settled,
            "parent_workflow_clock_interval": dict(parent_interval),
            "reservation_exceeded_seconds": max(0.0, settled - float(lease['reserved_seconds'])),
            "watchdog_classification": None if authority is None else authority.get("classification"),
            "hard_kill_included": bool(
                authority is not None
                and authority.get("first_SIGKILL") is not None
            ),
        }
    )
    attempts[index] = attempt
    stage_record["attempts"] = attempts
    stage_record["active_attempt"] = None
    ledger["stages"][stage] = stage_record
    ledger["elapsed_seconds"] = float(ledger.get("elapsed_seconds", 0.0)) + settled
    _write_v14_ledger(path, ledger)


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

    from .workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME
    full_clock=ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
    workflow_started = monotonic()
    source = _validate_source_sha(
        source_sha
        if source_sha is not None
        else _source_sha(Path(__file__).resolve().parents[2])
    )
    from src.io.physical_intermediate_profile import PROFILES
    from src.io.physical_intermediate_profile import FAST_PROFILE, LIGHT_PROFILE, PACKED_PROFILE, JOINT_PROFILE, profile_facts
    from src.io.physical_balanced_profile import BALANCED_PROFILES, BOUNDED_PROFILES
    from src.io.physical_recursive_profile import RECURSIVE_PROFILES
    recursive = specification.solver.get('preconditioner') in RECURSIVE_PROFILES
    bounded = specification.solver.get('preconditioner') in BOUNDED_PROFILES
    balanced = recursive or bounded or specification.solver.get('preconditioner') in BALANCED_PROFILES
    schur_v14 = specification.solver.get('preconditioner') == 'physical_p4_schur_v14'
    packed = specification.solver.get('preconditioner') == PACKED_PROFILE
    if specification.solver.get('preconditioner') in (FAST_PROFILE, PACKED_PROFILE) and pc_profile is None:
        raise InputError('fast backend is currently qualified for seven-PC diagnostic mode only')

    physical_candidate = specification.solver.get('preconditioner') in PROFILES and not contract_probe
    joint = physical_candidate and specification.solver.get('preconditioner') == JOINT_PROFILE
    light = physical_candidate and specification.solver.get('preconditioner') in (LIGHT_PROFILE, JOINT_PROFILE)
    physical_resources = profile_facts(specification.solver['preconditioner'])['resources'] if physical_candidate else {}
    if pc_profile is not None and not physical_candidate:
        raise InputError('PC timing mode requires a physical reference run')
    schur_stage_budget = None
    if physical_candidate and specification.solver.get('preconditioner') == 'physical_p4_schur_v14':
        schur_stage_budget = physical_resources.get('stage_budgets', {}).get(
            specification.solver.get('stage')
        )
        if schur_stage_budget is None:
            raise InputError('V14 Schur stage has no reviewed watchdog budget')
    workflow_limit = (
        (2400 if packed else 1800)
        if pc_profile is not None
        else schur_stage_budget['workflow_seconds']
        if schur_stage_budget is not None
        else physical_resources.get('workflow_seconds', 7200)
    )
    solve_limit = (
        schur_stage_budget['solve_seconds']
        if schur_stage_budget is not None
        else physical_resources.get('solve_seconds', 3600)
    )
    v14_lease = None
    authority = None
    run_directory = None
    if schur_v14 and physical_candidate:
        run_directory = _timestamp_directory(specification, timestamp)
        v14_lease = _reserve_v14_shared_budget(
            Path(__file__).resolve().parents[2], run_directory,
            source_sha=source, stage=str(specification.solver['stage']),
            stage_budget=schur_stage_budget, workflow_clock_start=full_clock.start,
        )
    try:
        physical_source = (_physical_source_gate(Path(__file__).resolve().parents[2], source)
                           if physical_candidate else None)
        adapter = (
            CONTRACT_PROBE_ADAPTER
            if contract_probe
            else method_adapter_identity(str(specification.method["kind"]))
        )
        if run_directory is None:
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
        if light or balanced:
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

                    watchdog_kwargs = {}
                    if recursive or bounded:
                        watchdog_kwargs.update(stop_on_global_swap=True)
                    if pc_profile is not None:
                        watchdog_kwargs.update(
                            grace_seconds=60 if packed else 30,
                            hard_stop_immediate=True,
                            cooperative_performance_stop=packed,
                            worker_environment={
                                'PHYSICAL_PC_PROFILE': json.dumps(pc_profile),
                                'XDG_CACHE_HOME': pc_profile['cache_home'],
                            },
                        )
                    elif light or balanced:
                        watchdog_kwargs.update(
                            grace_seconds=60,
                            hard_stop_immediate=True,
                            cooperative_performance_stop=True,
                            worker_environment={'XDG_CACHE_HOME': str(cache_home.resolve())},
                            **(
                                {
                                    'timebase_guard': True,
                                    'timebase_policy': 'conservative_realtime',
                                }
                                if balanced
                                else {}
                            ),
                        )
                    if schur_v14:
                        watchdog_kwargs.update(
                            stop_on_global_swap=True,
                            grace_seconds=30,
                            hard_stop_immediate=True,
                            cooperative_performance_stop=False,
                            timebase_guard=True,
                            timebase_policy='conservative_realtime',
                            tree_cap_bytes=int(physical_resources['tree_cap_bytes']),
                        )
                    if v14_lease is not None:
                        watchdog_environment = dict(
                            watchdog_kwargs.get('worker_environment', {})
                        )
                        watchdog_environment.update(
                            PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH=v14_lease['path'],
                            PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX=str(
                                v14_lease['attempt_index']
                            ),
                        )
                        watchdog_kwargs['worker_environment'] = watchdog_environment
                    wall_budget = (
                        min(
                            workflow_limit - (monotonic() - workflow_started),
                            pc_profile['deadline_monotonic'] - monotonic(),
                        )
                        if pc_profile is not None
                        else workflow_limit
                        - (60 if joint else 0)
                        - (
                            full_clock.update(clock_sample())['budget_seconds']
                            if balanced or schur_v14
                            else monotonic() - workflow_started
                        )
                    )
                    if v14_lease is not None:
                        wall_budget = min(wall_budget, float(v14_lease['reserved_seconds']) - full_clock.seconds)
                        if wall_budget <= 0:
                            raise InputError('V14 preflight exhausted the stage or shared workflow budget')
                    authority = supervise(
                        list(plan.argv),
                        run_directory / 'watchdog',
                        wall_seconds=max(1e-9, wall_budget),
                        solve_seconds=(
                            None
                            if pc_profile is not None
                            else min(
                                solve_limit,
                                wall_budget
                                if v14_lease is not None
                                else solve_limit,
                            )
                        ),
                        phase_path=run_directory / 'workflow_phase.json',
                        cache_path=Path(pc_profile['cache_home']) if pc_profile is not None else cache_home if light or balanced else
                            Path(os.environ['XDG_CACHE_HOME']) if 'XDG_CACHE_HOME' in os.environ else None,
                        source_state=physical_source,
                        **watchdog_kwargs,
                    )
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
        if (balanced or schur_v14) and physical_candidate:
            result['workflow_clock_interval']=full_clock.update(clock_sample())
            if result['workflow_clock_interval']['budget_seconds'] > min(workflow_limit, float(v14_lease['reserved_seconds']) if v14_lease else workflow_limit):
                result['result_classification']='PERFORMANCE_CONTROLLED_STOP'
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
    finally:
        if v14_lease is not None:
            parent_end = clock_sample()
            _settle_v14_shared_budget(
                v14_lease,
                status=locals().get('result', {}).get(
                    'result_classification', 'PARENT_PREFLIGHT_OR_MONITORING_FAILURE'),
                authority=authority,
                parent_interval=full_clock.update(parent_end),
                parent_clock_end=parent_end,
            )



__all__ = ["launch_specification"]
