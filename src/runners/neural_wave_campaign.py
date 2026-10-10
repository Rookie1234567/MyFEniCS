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

from src.io.neural_wave_campaign import ROOT, ARTIFACTS, digest, profile_paths
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


def window(spec=None):
    profile = profile_paths(spec or {})
    data = json.loads(profile["window"].read_text())
    budget = {31: 86400, 32: 57600, 33: 43200, 34: 57600, 35: 14400, 36: 21600, 38:28800}.get((spec or {}).get("campaign_version"), 172800)
    if data["budget_s"] != budget or not data["single_window"]:
        raise ValueError("V30_SINGLE_48H_WINDOW_IDENTITY_FAILED")
    if abs(data["deadline_monotonic"] - data["origin_monotonic"] - budget) > 1e-5:
        raise ValueError("V30_TIMEBASE_INCONSISTENT")
    return data


def stage_deadline(spec, allocation, campaign):
    """Preserve the original window and leave time for full frozen-field gates."""
    if spec.get("campaign_version") in (36, 38):
        return min(allocation["deadline_monotonic"], campaign["deadline_monotonic"]-1800), 1800
    if spec.get("campaign_version") == 35:
        deadline = min(allocation["deadline_monotonic"], campaign["deadline_monotonic"]-1800)
        if spec["role"] in ("space_unlabelled", "space_oracle"):
            root = profile_paths(spec)["root"]
            path = root / "numeric_window.json"
            if not path.exists():
                if spec["role"] != "space_unlabelled":
                    raise ValueError("UNLABELLED_NUMERIC_WINDOW_MUST_PRECEDE_ORACLE")
                atomic_json(path, dict(origin_monotonic=allocation["origin_monotonic"],
                                       deadline_monotonic=allocation["origin_monotonic"]+7200,
                                       shared_formal_limit_seconds=7200, never_reset=True))
            numeric = json.loads(path.read_text())
            deadline = min(deadline,numeric["deadline_monotonic"])
        return deadline, 1800
    if spec.get("campaign_version") == 34:
        reserve = 7200 if spec["role"] in (
            "DETERMINISTIC_COMPLEX_WAVE_BACKFIT", "LEARNED_COMPLEX_WAVE_BACKFIT"
        ) else 1800
        return min(allocation["deadline_monotonic"],
                   campaign["deadline_monotonic"] - reserve), reserve
    if spec.get("campaign_version") == 33:
        reserve = 5400 if spec["role"] in (
            "DETERMINISTIC_WAVE_BACKFIT", "LEARNED_VARPRO_BACKFIT"
        ) else 1800
        return min(allocation["deadline_monotonic"],
                   campaign["deadline_monotonic"] - reserve), reserve
    training = spec["role"] in (
        "LEARNED_WAVE_GREEDY",
        "FIXED_WAVE_GREEDY_CONTROL",
    )
    # Both routes receive the same common cost node. Subsequent continuation
    # must also leave the FE rebuild/checker and final delivery within the one
    # original 48h window; this is no new window or solver success condition.
    # Reserve 3600s for independent reconstruction/physics plus the mandatory
    # final 1800s publication/save margin. The original campaign never resets.
    if spec.get("campaign_version") in (31, 32):
        training = spec["role"] in (
            "LEARNED_WAVE_BLOCK_GREEDY",
            "FIXED_WAVE_BLOCK_GREEDY",
            "FIXED_MULTISCALE_WAVE_BLOCK",
            "LEARNED_MULTISCALE_WAVE_BLOCK",
        )
        reserve = 7200 if training else 3600
    else:
        reserve = 5400 if training else 1800
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


def worker_stop_time(spec, deadline):
    training = spec["role"] in (
        "FIXED_WAVE_BLOCK_GREEDY",
        "LEARNED_WAVE_BLOCK_GREEDY",
        "FIXED_MULTISCALE_WAVE_BLOCK",
        "LEARNED_MULTISCALE_WAVE_BLOCK",
    )
    # Reserve the same 30 minutes inside each 6h ceiling for frozen q60,
    # independent field/checker cost. This is not extra training time.
    reserve = 1800 if spec.get("campaign_version") in (31, 32) and training else 150
    return deadline - reserve


def durable(spec, *, origin, attempt=1):
    from src.runners.durable_terminal import launch_tmux
    from src.runners.w1_admission_scope import capture_scope

    source_gate()
    profile = profile_paths(spec)
    campaign = window(spec)
    if campaign["deadline_monotonic"] - monotonic() <= profile["reserve"] + 600:
        raise TimeoutError("V30_FINAL_RESERVE_REACHED")
    stage = spec["stage"]
    root = profile["root"]
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
        scalar_continuation = False
        if spec.get("campaign_version") in (33, 34) and spec["role"] in (
            "DETERMINISTIC_WAVE_BACKFIT", "LEARNED_VARPRO_BACKFIT",
            "DETERMINISTIC_COMPLEX_WAVE_BACKFIT", "LEARNED_COMPLEX_WAVE_BACKFIT"
        ):
            route_artifact = profile["artifacts"] / stage
            result_file = route_artifact / "result.json"
            if result_file.exists():
                status = json.loads(result_file.read_text())["status"]
                if status.startswith("INDEPENDENT_VALIDATION_REQUESTED_"):
                    node = int(status[-1])
                    scalar = route_artifact / f"validation_scalars_{node}.json"
                    scalar_continuation = scalar.exists() and json.loads(
                        scalar.read_text()
                    )["boundary_sha256"] == digest(route_artifact / "basis/committed.json")
        if spec.get("campaign_version") == 32 and spec["role"] in (
            "FIXED_MULTISCALE_WAVE_BLOCK",
            "LEARNED_MULTISCALE_WAVE_BLOCK",
        ):
            route_artifact = profile["artifacts"] / stage
            result_file = route_artifact / "result.json"
            if result_file.exists():
                status = json.loads(result_file.read_text())["status"]
                if status.startswith("INDEPENDENT_VALIDATION_REQUESTED_"):
                    node = int(status[-1])
                    scalar = route_artifact / f"validation_scalars_{node}.json"
                    scalar_continuation = scalar.exists() and json.loads(
                        scalar.read_text()
                    )["boundary_sha256"] == digest(
                        route_artifact / "basis/committed.json"
                    )
        if not scalar_continuation and (
            not repairs.exists() or not repairs.read_text().strip()
        ):
            raise ValueError("RECOVERY_REQUIRES_FAILURE_CHANGE_TEST_EVIDENCE")
    else:
        if attempt != 1:
            raise ValueError("NO_INITIAL_STAGE_FOR_RECOVERY")
        original = dict(
            origin_monotonic=origin,
            deadline_monotonic=min(
                origin + spec["max_seconds"],
                campaign["deadline_monotonic"] - profile["reserve"],
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
    atomic_json(
        directory / "attempt_identity.json",
        dict(
            stage=stage,
            attempt=attempt,
            origin_monotonic=origin,
            inherited_route_origin_monotonic=original["origin_monotonic"],
            inherited_deadline_monotonic=original["deadline_monotonic"],
            scope="actual attempt including imports, observation and supervision; no budget reset",
        ),
    )
    # This outer observation captures the originally permitted cpuset only.
    # The launcher performs stability and a fresh final observation before exec.
    from src.runners.neural_wave_dependencies import fresh_admission

    try:
        facts = fresh_admission(
            directory, 2 * 2**30, prefix="outer_admission", reserve_s=64
        )
    except Exception as error:
        atomic_json(
            directory / "run_summary.json",
            dict(
                classification="RESOURCE_ADMISSION_REJECTED_BEFORE_TERMINAL",
                reason=repr(error),
                source_sha=source_gate(),
                worker_started=False,
                descendants_cleared=True,
                evidence_scope="outer observation before launch_tmux; no terminal/worker created",
                **timing_fields(
                    original,
                    json.loads((directory / "attempt_identity.json").read_text()),
                    monotonic(),
                ),
            ),
        )
        raise
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
        socket_directory=root / "sockets"
        if spec.get("campaign_version") in (32,33,34,35,36,38)
        else None,
    )


def launch(spec):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import envelope, Health, stable_window
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
    profile = profile_paths(spec)
    campaign = window(spec)
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
            "saved_field_audit",
            "block_checks",
            "block_reconstruct",
            "reconstruction_stability",
            "FIXED_WAVE_BLOCK_GREEDY",
            "LEARNED_WAVE_BLOCK_GREEDY",
            "multiscale_checks",
            "readout_repair_checks",
            "support_witness",
            "early_validate",
            "multiscale_reconstruct",
            "FIXED_MULTISCALE_WAVE_BLOCK",
            "LEARNED_MULTISCALE_WAVE_BLOCK",
            "backfit_anchor_checks",
            "backfit_math_checks",
            "backfit_reconstruct",
            "backfit_early_validate",
            "backfit_transfer_prepare",
            "backfit_transfer",
            "backfit_transfer_compare",
            "DETERMINISTIC_WAVE_BACKFIT",
            "LEARNED_VARPRO_BACKFIT",
            "complex_wave_checks",
            "complex_wave_calibration",
            "complex_reconstruct",
            "complex_early_validate",
            "complex_pilot_prepare",
            "complex_pilot_solve",
            "complex_pilot_compare",
            "DETERMINISTIC_COMPLEX_WAVE_BACKFIT",
            "LEARNED_COMPLEX_WAVE_BACKFIT",
            "space_unlabelled",
            "space_oracle",
            "space_compare",
            "blocked_oracle",
            "blocked_verify",
            "ftt_checks", "ftt_train", "ftt_reconstruct", "ftt_compare", "ftt_fit_compare",
        )
        else 2
    ) * 2**30
    # Local FE moments/calibration is numerical; pure fixture tests have a 2GiB guard.
    artifact = profile["artifacts"] / spec["stage"]
    artifact.mkdir(parents=True, exist_ok=True)
    lock_path = ROOT / "tmp/task42extra/numerical.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if shutil.disk_usage(ROOT).free < 50 * 2**30:
                raise RuntimeError("STORAGE_START_GATE_FAILED")
            from src.runners.neural_wave_dependencies import (
                fresh_admission,
                resource_observation_cost,
            )

            if spec.get("campaign_version") in (31, 32, 33, 34, 35, 36, 38):
                from src.runners.block_wave_admission import (
                    stable_window as qualified_stability,
                )

                qualified_stability(directory, hard, seconds=60)
            else:
                if resource_observation_cost() + 64 >= 1200:
                    raise RuntimeError("V30_RESOURCE_OBSERVATION_BUDGET_REACHED")
                stable_window(directory, hard, seconds=60)
            facts = fresh_admission(directory, hard, scope=terminal["allowed_scope"])
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
                        "src/runners/neural_wave_dependencies.py",
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
                    + (
                        (
                            "src/io/block_wave_campaign.py",
                            "src/runners/block_wave_admission.py",
                            "src/runners/block_wave_worker.py",
                            "src/solvers/neural_wave_block.py",
                            "src/solvers/neural_wave_block_reconstruction.py",
                            "src/solvers/neural_wave_block_qualification.py",
                            "src/postprocessing/neural_wave_roundoff.py",
                        )
                        if spec.get("campaign_version") in (31, 32, 33, 34, 35, 36)
                        else ()
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
                worker_stop_monotonic=worker_stop_time(spec, deadline),
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
                design_sha256=digest(profile["design"]),
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
                in (
                    "LEARNED_WAVE_GREEDY",
                    "FIXED_WAVE_GREEDY_CONTROL",
                    "LEARNED_WAVE_BLOCK_GREEDY",
                    "FIXED_WAVE_BLOCK_GREEDY",
                ),
                benchmark_previously_seen=True,
                production_initialization_allowed=False,
            )
            if spec.get("campaign_version") == 32:
                manifest["binding_source_files"].update(
                    {
                        path: digest(ROOT / path)
                        for path in (
                            "src/io/multiscale_wave_campaign.py",
                            "src/runners/multiscale_wave_worker.py",
                            "src/solvers/neural_wave_multiscale.py",
                            "src/solvers/neural_wave_multiscale_validation.py",
                            "src/postprocessing/neural_wave_support_audit.py",
                        )
                    }
                )
                manifest.update(
                    reference_used_for_validation=True,
                    continuation_uses_validation_scalars=True,
                    pde_only_solve=spec["role"]
                    in ("FIXED_MULTISCALE_WAVE_BLOCK", "LEARNED_MULTISCALE_WAVE_BLOCK"),
                )
            if spec.get("campaign_version") == 33:
                manifest["binding_source_files"].update({
                    path: digest(ROOT / path) for path in (
                        "src/io/backfit_wave_campaign.py",
                        "src/io/neural_wave_backfit_store.py",
                        "src/solvers/neural_wave_backfit.py",
                        "src/solvers/neural_wave_backfit_qualification.py",
                        "src/solvers/neural_wave_backfit_state.py",
                        "src/solvers/neural_wave_backfit_run.py",
                        "src/runners/backfit_wave_worker.py",
                        "src/solvers/neural_wave_multiscale.py",
                    )
                })
                manifest.update(reference_used_for_validation=True,
                                continuation_uses_validation_scalars=True,
                                pde_only_solve=spec["role"] in (
                                    "DETERMINISTIC_WAVE_BACKFIT", "LEARNED_VARPRO_BACKFIT"))
            if spec.get("campaign_version") == 34:
                from src.runners.complex_wave_worker import CHAIN

                manifest["binding_source_files"].update(
                    {path: digest(ROOT / path) for path in CHAIN})
                manifest.update(
                    wave_representation="oscillation+decay.v1",
                    reference_used_for_validation=True,
                    continuation_uses_validation_scalars=True,
                    pde_only_solve=spec["role"] in (
                        "DETERMINISTIC_COMPLEX_WAVE_BACKFIT", "LEARNED_COMPLEX_WAVE_BACKFIT"))
            if spec.get("campaign_version") == 36:
                from src.runners.blocked_oracle_worker import CHAIN
                from src.io.neural_space_campaign import POLICY
                manifest["binding_source_files"].update({p:digest(ROOT/p) for p in CHAIN})
                manifest.update(POLICY, reference_basis_selection=False)
            if spec.get("campaign_version") == 35:
                from src.runners.neural_space_worker import CHAIN
                from src.io.neural_space_campaign import POLICY
                manifest["binding_source_files"].update({p:digest(ROOT/p) for p in CHAIN})
                if spec["role"] == "space_oracle":
                    manifest.update(POLICY)
                else:
                    manifest.update(reference_used_for_training=False,
                                    pde_only_solve=spec["role"] == "space_unlabelled",
                                    pde_only_solver_qualified=False,
                                    official_candidate_results=False)
            if spec.get("campaign_version") == 38:
                from src.runners.ftt_worker import CHAIN
                from src.io.ftt_campaign import usage_flags
                manifest["binding_source_files"].update({p:digest(ROOT/p) for p in CHAIN})
                manifest.update(usage_flags(spec))
                manifest.update(model_schema="ftt-field.v1", model_kind=spec.get("model_kind"),
                    metric_kind=spec.get("metric_kind"), global_Gram_factor_count=0,
                    Gsolve_count=0, global_Maxwell_factor_count=0)
            atomic_json(directory / "run_manifest.json", manifest)
            atomic_json(artifact / f"run_manifest_{directory.name}.json", manifest)
            shutil.copyfile(ROOT / spec["input"], directory / "input_original.dat")
            atomic_json(
                directory / "resolved_config.json",
                json.loads(profile["design"].read_text()),
            )
            command = [
                sys.executable,
                "-m",
                "src.runners.guarded_exec",
                str(os.getpid()),
                str(ticks(os.getpid())),
                sys.executable,
                "-m",
                "src.runners.ftt_worker" if spec.get("campaign_version")==38 else "src.runners.neural_wave_worker",
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
                health_check=Health(
                    directory, hard, [], artifact_root=profile["artifacts"],
                    artifact_cap_bytes=(12 if spec.get("campaign_version") == 36 else 8 if spec.get("campaign_version") == 35 else 20)*2**30
                ),
                sampled_root_identity=terminal["server"],
            )
            result.update(timing_fields(allocation, attempt_identity, monotonic()))
            result["source_sha"] = source
            atomic_json(directory / "payload_summary.json", result)
            if spec["role"] == "LEARNED_WAVE_GREEDY":
                from src.runners.neural_wave_dependencies import followups

                result["serial_independent_dependencies"] = followups(
                    directory, manifest, terminal, result
                )
                result["actual_attempt_including_dependencies_seconds"] = (
                    monotonic() - attempt_identity["origin_monotonic"]
                )
                if any(
                    v["summary"]["classification"] != "COMPLETED"
                    or v["summary"]["leader_exit_code"] != 0
                    for v in result["serial_independent_dependencies"]
                ):
                    result["classification"] = "DEPENDENCY_WORKER_FAILED"
            atomic_json(directory / "run_summary.json", result)
            return result
        except Exception as error:
            payload = directory / "payload_summary.json"
            atomic_json(
                directory / "run_summary.json",
                dict(
                    classification="DEPENDENCY_PREPARATION_FAILED"
                    if payload.exists()
                    else "STARTUP_FAILED",
                    reason=repr(error),
                    source_sha=source,
                    descendants_cleared=True,
                    completed_payload_summary="payload_summary.json"
                    if payload.exists()
                    else None,
                    **timing_fields(allocation, attempt_identity, monotonic()),
                ),
            )
            raise
