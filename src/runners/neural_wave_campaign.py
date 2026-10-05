"""Thin V30 stage wiring using the existing isolated terminal and watchdog."""

from datetime import datetime, timezone
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
from time import monotonic

from src.io.neural_wave_campaign import ROOT, DESIGN, WINDOW, ARTIFACTS, digest
from src.solvers.neural_wave_greedy import atomic_json


def source_gate():
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    if branch != "task42extra_feinn_5nm" or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT
    ):
        raise RuntimeError("V30_REQUIRES_CLEAN_COMMITTED_CANONICAL_SOURCE")
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def window():
    data = json.loads(WINDOW.read_text())
    if data["budget_s"] != 172800 or not data["single_window"]:
        raise ValueError("V30_SINGLE_48H_WINDOW_IDENTITY_FAILED")
    if abs(data["deadline_monotonic"] - data["origin_monotonic"] - 172800) > 1e-5:
        raise ValueError("V30_TIMEBASE_INCONSISTENT")
    return data


def stage_deadline(spec, allocation, campaign):
    """Preserve the original window and leave time for full frozen-field gates."""
    training = spec["role"] in (
        "LEARNED_WAVE_GREEDY",
        "FIXED_WAVE_GREEDY_CONTROL",
    )
    # Both routes receive the same common cost node. Subsequent continuation
    # must also leave the FE rebuild/checker and final delivery within the one
    # original 48h window; this is no new window or solver success condition.
    reserve = 10800 if training else 1800
    return min(
        allocation["deadline_monotonic"], campaign["deadline_monotonic"] - reserve
    ), reserve


def timing_fields(allocation, attempt_identity, now):
    """Separate inherited route span from additive actual attempt wall time."""
    origin = attempt_identity["origin_monotonic"]
    if not allocation["origin_monotonic"] <= origin <= now:
        raise ValueError("V30_ATTEMPT_COST_TIMEBASE_INCONSISTENT")
    span = now - allocation["origin_monotonic"]
    return dict(
        launch_to_summary_seconds=span,
        launch_to_summary_semantics="inherited allocation span including prior runs and pauses; not additive attempt cost",
        inherited_route_allocation_span_seconds=span,
        actual_attempt_elapsed_seconds=now - origin,
    )


def durable(spec, *, origin, attempt=1):
    from src.runners.durable_terminal import launch_tmux
    from src.runners.feinn_resources import admission
    from src.runners.w1_admission_scope import capture_scope

    source_gate()
    campaign = window()
    if campaign["deadline_monotonic"] - monotonic() <= 2400:
        raise TimeoutError("V30_FINAL_RESERVE_REACHED")
    stage = spec["stage"]
    root = ROOT / "tmp/task42extra/v30"
    allocation = root / "allocations" / f"{stage}.json"
    allocation.parent.mkdir(parents=True, exist_ok=True)
    if allocation.exists():
        original = json.loads(allocation.read_text())
        if attempt == 1:
            raise RuntimeError(
                "EXISTING_STAGE: inspect/reconnect; never start duplicate"
            )
        prior = root / "durable" / f"{stage}_attempt{attempt - 1}" / "run_summary.json"
        if (
            not prior.exists()
            or not json.loads(prior.read_text())["descendants_cleared"]
        ):
            raise ValueError("RECOVERY_REQUIRES_PRIOR_TREE_CLEARED")
        repairs = root / "repair_journal.jsonl"
        if not repairs.exists() or not repairs.read_text().strip():
            raise ValueError("RECOVERY_REQUIRES_FAILURE_CHANGE_TEST_EVIDENCE")
    else:
        if attempt != 1:
            raise ValueError("NO_INITIAL_STAGE_FOR_RECOVERY")
        original = dict(
            origin_monotonic=origin,
            deadline_monotonic=min(
                origin + spec["max_seconds"], campaign["deadline_monotonic"] - 1800
            ),
            max_seconds=spec["max_seconds"],
            stage=stage,
            input_sha256=spec["input_sha256"],
        )
        atomic_json(allocation, original)
    directory = root / "durable" / f"{stage}_attempt{attempt}"
    if directory.exists():
        raise RuntimeError("EXISTING_DURABLE_NAMESPACE: reconnect same job")
    directory.mkdir(parents=True)
    atomic_json(directory / "attempt_identity.json", dict(
        stage=stage, attempt=attempt, origin_monotonic=origin,
        inherited_route_origin_monotonic=original["origin_monotonic"],
        inherited_deadline_monotonic=original["deadline_monotonic"],
        scope="actual attempt including imports, observation and supervision; no budget reset",
    ))
    # This outer observation captures the originally permitted cpuset only.
    # The launcher performs stability and a fresh final observation before exec.
    facts = admission(
        2 * 2**30,
        observation_sink=lambda v: atomic_json(directory / "outer_admission.json", v),
    )
    scope = capture_scope(facts)
    env = dict(
        TASK42EXTRA_WAVE_NAMESPACE=str(directory.relative_to(ROOT)),
        TASK42EXTRA_WAVE_ALLOCATION=str(allocation.relative_to(ROOT)),
    )
    command = [
        "bash",
        "-lc",
        "source scripts/activate_task42extra.sh "
        + spec["mode"]
        + " && "
        + "export "
        + " ".join(key + "=" + shlex.quote(value) for key, value in env.items())
        + " && exec python scripts/run_case.py "
        + shlex.quote(spec["input"]),
    ]
    return launch_tmux(
        directory,
        f"wave-{stage}-{attempt}",
        command,
        ROOT,
        management_supervised=True,
        allowed_scope=scope,
    )


def launch(spec):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import admission, envelope, Health, stable_window
    from src.runners.fresh_component_receiver import (
        bind_own_terminal_core,
        set_own_low_priority,
    )
    from src.runners.guarded_exec import ticks

    source = source_gate()
    if os.environ.get("TASK42EXTRA_ENV_MODE") != spec["mode"]:
        raise RuntimeError("V30_INDEPENDENT_ACTIVATION_MISMATCH")
    directory = ROOT / os.environ["TASK42EXTRA_WAVE_NAMESPACE"]
    terminal = json.loads((directory / "terminal_identity.json").read_text())
    allocation = json.loads(
        (ROOT / os.environ["TASK42EXTRA_WAVE_ALLOCATION"]).read_text()
    )
    attempt_identity = json.loads((directory / "attempt_identity.json").read_text())
    campaign = window()
    hard = (
        16
        if spec["role"]
        in (
            "checks",
            "fast_checks",
            "local_action_checks",
            "projection_checks",
            "screening_checks",
            "calibration",
            "verify",
            "LEARNED_WAVE_GREEDY",
            "FIXED_WAVE_GREEDY_CONTROL",
        )
        else 2
    ) * 2**30
    # Local FE moments/calibration is numerical; pure fixture tests have a 2GiB guard.
    artifact = ARTIFACTS / spec["stage"]
    artifact.mkdir(parents=True, exist_ok=True)
    lock_path = ROOT / "tmp/task42extra/numerical.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if shutil.disk_usage(ROOT).free < 50 * 2**30:
                raise RuntimeError("STORAGE_START_GATE_FAILED")
            stable_window(directory, hard, seconds=60)
            facts = admission(
                hard,
                candidate_scope=terminal["allowed_scope"],
                observation_sink=lambda v: atomic_json(directory / "admission.json", v),
            )
            set_own_low_priority()
            bind_own_terminal_core(terminal, facts["cpu"])
            os.sched_setaffinity(0, {int(facts["cpu"])})
            now = monotonic()
            deadline, reserve = stage_deadline(spec, allocation, campaign)
            if deadline - now <= 300:
                raise TimeoutError("V30_STAGE_SAVE_RESERVE_UNAVAILABLE")
            stamp = datetime.now(timezone.utc).isoformat()
            manifest = dict(
                spec=spec,
                source_sha=source,
                source_is_later_documentation_HEAD=False,
                binding_source_files={
                    path: digest(ROOT / path)
                    for path in (
                        "src/solvers/neural_wave_moments.py",
                        "src/solvers/neural_wave_factorized.py",
                        "src/solvers/neural_wave_qualification.py",
                        "src/solvers/neural_wave_reconstruction.py",
                        "src/postprocessing/neural_wave_audit.py",
                        "src/solvers/neural_wave_subspace.py",
                        "src/solvers/neural_wave_greedy.py",
                        "src/solvers/neural_wave_local_action.py",
                        "src/solvers/neural_wave_local_qualification.py",
                        "src/solvers/neural_wave_projection.py",
                        "src/solvers/neural_wave_projection_qualification.py",
                        "src/solvers/neural_wave_screening.py",
                        "src/solvers/neural_wave_screening_qualification.py",
                        "src/runners/neural_wave_campaign.py",
                        "src/runners/neural_wave_worker.py",
                        "src/io/neural_wave_campaign.py",
                        "src/runners/feinn_resources.py",
                        "src/runners/task042_shared.py",
                        "src/runners/durable_terminal.py",
                        "src/runners/guarded_exec.py",
                        "src/runners/fresh_component_receiver.py",
                        "src/runners/w1_admission_scope.py",
                        "src/solvers/feinn_native.py",
                        "src/solvers/feinn_reference.py",
                        "benchmarks/subreaper_watchdog.py",
                        "scripts/activate_task42extra.sh",
                        "scripts/launch_task42extra_durable.py",
                        "scripts/run_case.py",
                    )
                },
                utc=stamp,
                route_origin_monotonic=allocation["origin_monotonic"],
                actual_attempt_origin_monotonic=attempt_identity["origin_monotonic"],
                stage_deadline_monotonic=deadline,
                inherited_allocation_deadline_monotonic=allocation[
                    "deadline_monotonic"
                ],
                remaining_independent_verification_and_delivery_reserve_s=reserve,
                worker_stop_monotonic=deadline - 150,
                campaign=campaign,
                cpu=facts["cpu"],
                mpi_size=1,
                math_threads=1,
                cpu_only=True,
                rss_hard_bytes=hard,
                rss_warn_bytes=min(12 * 2**30, int(0.875 * hard)),
                own_swap_bytes_allowed=0,
                artifact=str(artifact.relative_to(ROOT)),
                input_sha256=spec["input_sha256"],
                design_sha256=digest(DESIGN),
                qualifying_moments_q60_sha256=(
                    digest(ARTIFACTS / "v30_wave_checks/moments_q60.npz")
                    if (ARTIFACTS / "v30_wave_checks/moments_q60.npz").exists()
                    else None
                ),
                material_table_sha256=digest(
                    ROOT / "input/materials/si_optical_constants_v1.json"
                ),
                terminal_identity_sha256=digest(directory / "terminal_identity.json"),
                python_executable=sys.executable,
                environment={
                    key: os.environ.get(key)
                    for key in (
                        "TASK42EXTRA_ENV_MODE",
                        "PYTHONPATH",
                        "LD_LIBRARY_PATH",
                        "OMP_NUM_THREADS",
                        "OPENBLAS_NUM_THREADS",
                        "CUDA_VISIBLE_DEVICES",
                    )
                },
                reference_used_for_training=False,
                features_reference_exposed=False,
                pde_only_solve=spec["role"]
                in ("LEARNED_WAVE_GREEDY", "FIXED_WAVE_GREEDY_CONTROL"),
                benchmark_previously_seen=True,
                production_initialization_allowed=False,
            )
            atomic_json(directory / "run_manifest.json", manifest)
            atomic_json(artifact / f"run_manifest_{directory.name}.json", manifest)
            shutil.copyfile(ROOT / spec["input"], directory / "input_original.dat")
            atomic_json(
                directory / "resolved_config.json", json.loads(DESIGN.read_text())
            )
            command = [
                sys.executable,
                "-m",
                "src.runners.guarded_exec",
                str(os.getpid()),
                str(ticks(os.getpid())),
                sys.executable,
                "-m",
                "src.runners.neural_wave_worker",
                str(directory.relative_to(ROOT)),
            ]
            result = supervise(
                command,
                directory / "supervised",
                wall_seconds=deadline - monotonic(),
                rss_hard_limit_bytes=hard,
                rss_warning_bytes=min(12 * 2**30, int(0.875 * hard)),
                hard_stop_immediate=True,
                source_state=manifest,
                memory_envelope_provider=lambda: envelope(hard),
                health_check=Health(directory, hard, [], artifact_root=ARTIFACTS),
                sampled_root_identity=terminal["server"],
            )
            result.update(timing_fields(allocation, attempt_identity, monotonic()))
            result["source_sha"] = source
            atomic_json(directory / "run_summary.json", result)
            return result
        except Exception as error:
            atomic_json(
                directory / "run_summary.json",
                dict(
                    classification="STARTUP_FAILED",
                    reason=repr(error),
                    source_sha=source,
                    descendants_cleared=True,
                    **timing_fields(allocation, attempt_identity, monotonic()),
                ),
            )
            raise
