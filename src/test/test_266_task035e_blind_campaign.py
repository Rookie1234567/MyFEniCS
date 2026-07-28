from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Callable
from types import SimpleNamespace
from unittest import mock

import pytest

from benchmarks import task035e_blind_campaign as blind_campaign
from benchmarks.task035e_blind_campaign import (
    BlindCampaignError,
    BlindCampaignIdentity,
    BlindPathIdentity,
    CampaignEvidenceError,
    CampaignIdentityDrift,
    CommandExecution,
    SubprocessCommandRunner,
    HeavyStageBusy,
    PreparedStage,
    SingleHeavyLock,
    StageArtifactBinding,
    StageExecutionContext,
    StageResult,
    WatchdogLaunchSpec,
    build_campaign_stage_dag,
    build_watchdog_argv,
    initialize_campaign,
    run_campaign,
    validate_watchdog_argv,
)


SOURCE_SHA = "a" * 40
ABI_SHA = "b" * 64


def test_subprocess_runner_passes_explicit_activation_environment(
    tmp_path: Path,
) -> None:
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    record = attempt_dir / "watchdog.json"
    attempt = SimpleNamespace(
        attempt_dir=attempt_dir,
        record_process=mock.Mock(),
    )
    process = SimpleNamespace(
        pid=os.getpid(),
        wait=mock.Mock(return_value=0),
        kill=mock.Mock(),
    )
    with mock.patch.object(
        blind_campaign.subprocess,
        "Popen",
        return_value=process,
    ) as popen:
        execution = SubprocessCommandRunner()(
            ("python", "--record", str(record)),
            attempt=attempt,
            invocation_index=0,
            argv_sha256="c" * 64,
        )
    assert execution.exit_code == 0
    environment = popen.call_args.kwargs["env"]
    assert environment == dict(os.environ)
    assert environment is not os.environ


def _private_file(path: Path, payload: bytes = b"{}\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(tmp_path: Path) -> BlindCampaignIdentity:
    plan_a = _private_file(tmp_path / "inputs" / "plan-a.json", b'{"a":1}\n')
    plan_b = _private_file(tmp_path / "inputs" / "plan-b.json", b'{"b":1}\n')
    authority_a = _private_file(
        tmp_path / "inputs" / "authority-a.json",
        b'{"authority":"a"}\n',
    )
    authority_b = _private_file(
        tmp_path / "inputs" / "authority-b.json",
        b'{"authority":"b"}\n',
    )
    config_a = _private_file(
        tmp_path / "inputs" / "config-a.json",
        b'{"config":"a"}\n',
    )
    config_b = _private_file(
        tmp_path / "inputs" / "config-b.json",
        b'{"config":"b"}\n',
    )
    return BlindCampaignIdentity(
        source_sha=SOURCE_SHA,
        abi_sha256=ABI_SHA,
        paths=(
            BlindPathIdentity(
                path_id="A",
                trial_id="task035e-blind-path-a",
                nominal_h_nm=20.0,
                initial_plan_path=plan_a,
                initial_plan_sha256=_sha(plan_a),
                initial_space_authority_path=authority_a,
                initial_space_authority_sha256=_sha(authority_a),
                qualified_solver_config_path=config_a,
                qualified_solver_config_sha256=_sha(config_a),
            ),
            BlindPathIdentity(
                path_id="B",
                trial_id="task035e-blind-path-b",
                nominal_h_nm=15.0,
                initial_plan_path=plan_b,
                initial_plan_sha256=_sha(plan_b),
                initial_space_authority_path=authority_b,
                initial_space_authority_sha256=_sha(authority_b),
                qualified_solver_config_path=config_b,
                qualified_solver_config_sha256=_sha(config_b),
            ),
        ),
    )


def _fake_heavy_argv(
    context: StageExecutionContext,
    attempt: object,
) -> tuple[str, ...]:
    cycle = context.stage.cycle_index
    assert cycle is not None
    role = {
        "current_solve": "current",
        "p_shadow_discovery": "p-shadow",
        "h_shadow_discovery": "h-shadow",
        "p_selected_shadow_verification": "p-shadow",
        "h_selected_shadow_verification": "h-shadow",
        "internal_gate_deferred_or_final": "current",
    }[context.stage.stage_name]
    argv = [
        sys.executable,
        "-m",
        "benchmarks.run_task033_full3d_watchdog",
        "--degree",
        "6",
        "--h-nm",
        f"{context.nominal_h_nm:g}",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_variable_p_condensed",
        "--stage4-raw-tensor-cache",
        "--stage4-local-h-refinement-plan",
        "/tmp/fake-plan.json",
        "--stage4-local-h-refinement-plan-sha256",
        context.input_plan_sha256,
        "--task035e-blind-candidate-gate",
        "--task035e-blind-trial-id",
        context.trial_id,
        "--task035e-blind-cycle-index",
        str(cycle),
        "--task035e-blind-output-role",
        role,
        "--artifact-root",
        str(attempt.attempt_dir / "watchdog-artifacts"),
        "--run-dir",
        str(attempt.attempt_dir / "watchdog-run"),
        "--record",
        str(attempt.attempt_dir / "watchdog-record.json"),
        "--verified-clean-sha",
        context.source_sha,
    ]
    if context.stage.stage_name == "internal_gate_deferred_or_final":
        argv.extend(
            (
                "--task035e-current-snapshot-manifest",
                "/tmp/task035e-fake-snapshot.json",
                "--task035e-current-snapshot-manifest-sha256",
                "c" * 64,
                "--task035e-internal-probe-kind",
                "algebraic",
            )
        )
    elif not (role == "current" and cycle == 0):
        argv.extend(
            (
                "--task035e-current-snapshot-manifest",
                "/tmp/task035e-fake-snapshot.json",
                "--task035e-current-snapshot-manifest-sha256",
                "c" * 64,
                "--task035e-transition-action",
                "/tmp/task035e-fake-action.json",
                "--task035e-transition-action-sha256",
                "d" * 64,
            )
        )
    return tuple(argv)


class _FakePreparer:
    def __init__(
        self,
        *,
        freeze_cycle: int = 0,
        saturation: str = "verified",
        h_saturation: str = "verified",
        fail_stage_once: str | None = None,
        internal_probe_batch: bool = False,
        reverse_internal_probes: bool = False,
        two_start_mismatch: bool = False,
        controlled_stop_stage: str | None = None,
    ) -> None:
        self.freeze_cycle = freeze_cycle
        self.saturation = saturation
        self.h_saturation = h_saturation
        self.fail_stage_once = fail_stage_once
        self.internal_probe_batch = internal_probe_batch
        self.reverse_internal_probes = reverse_internal_probes
        self.two_start_mismatch = two_start_mismatch
        self.controlled_stop_stage = controlled_stop_stage
        self.calls: list[str] = []
        self._failed = False

    def __call__(
        self,
        context: StageExecutionContext,
        attempt: object,
    ) -> PreparedStage:
        argv = (
            _fake_heavy_argv(context, attempt)
            if context.stage.heavy
            else None
        )
        argvs: tuple[tuple[str, ...], ...] = ()
        if context.stage.stage_name == (
            "internal_gate_deferred_or_final"
        ) and not self.internal_probe_batch:
            argv = None
        elif (
            context.stage.stage_name
            == "internal_gate_deferred_or_final"
        ):
            commands = []
            for probe in (
                "algebraic",
                "dtn",
                "postprocess",
                "serial_mpi1",
            ):
                command = list(_fake_heavy_argv(context, attempt))
                probe_index = command.index(
                    "--task035e-internal-probe-kind"
                )
                command[probe_index + 1] = probe
                if probe == "serial_mpi1":
                    mpi_index = command.index("--mpi-size")
                    command[mpi_index + 1] = "1"
                record_index = command.index("--record")
                command[record_index + 1] = str(
                    attempt.attempt_dir
                    / f"watchdog-{probe}.json"
                )
                commands.append(tuple(command))
            if self.reverse_internal_probes:
                commands.reverse()
            argvs = tuple(commands)
            argv = None

        def execute(
            attempt: object,
            command_receipts: tuple[object, ...],
        ) -> StageResult:
            stage_id = context.stage.stage_id
            self.calls.append(stage_id)
            if (
                self.fail_stage_once == stage_id
                and not self._failed
            ):
                self._failed = True
                attempt.record_process(
                    99_999_999,
                    invocation_index=0,
                    argv_sha256="e" * 64,
                    linux_start_ticks="fake-interrupted",
                )
                raise RuntimeError("simulated interrupted stage")
            artifact = attempt.write_artifact(
                "result.json",
                {
                    "stage_id": stage_id,
                    "source_sha": context.source_sha,
                    "abi_sha256": context.abi_sha256,
                    "input_plan_sha256": context.input_plan_sha256,
                },
            )
            next_plan = None
            artifact_role = (
                context.stage.stage_name.replace("-", "_") + "_result"
            )
            if context.stage.stage_name == "two_start_comparison":
                artifact_role = "two_start_comparison"
            elif context.stage.stage_name == "candidate_freeze":
                artifact_role = "candidate_freeze"
            lane_decision = "continue"
            freeze_requested = False
            saturation = "not_applicable"
            h_saturation = "not_applicable"
            status = "completed"
            classification = "fake_stage_completed"
            if stage_id == self.controlled_stop_stage:
                status = "controlled_negative"
                classification = "formal_stage_blocker"
                lane_decision = "controlled_negative"
                artifact_role = "stage_blocker"
            if context.stage.stage_name == "transition_or_pkeep":
                next_plan = _sha(artifact)
                artifact_role = "current_plan"
            if (
                context.stage.stage_name == "cycle_advance"
                and context.stage.cycle_index == self.freeze_cycle
            ):
                lane_decision = "freeze_ready"
                freeze_requested = True
                saturation = self.saturation
                h_saturation = self.h_saturation
            if (
                context.stage.stage_name == "two_start_comparison"
                and self.two_start_mismatch
            ):
                status = "controlled_negative"
                classification = "two_start_outputs_differ"
                lane_decision = "controlled_negative"
            return StageResult(
                status=status,
                classification=classification,
                input_plan_sha256=context.input_plan_sha256,
                artifacts=(
                    StageArtifactBinding.from_file(
                        artifact_role,
                        artifact,
                    ),
                ),
                command_receipt_file_sha256s=tuple(
                    receipt.receipt_file_sha256
                    for receipt in command_receipts
                ),
                next_plan_sha256=next_plan,
                lane_decision=lane_decision,
                freeze_requested=freeze_requested,
                p6_saturation=saturation,
                h_level3_saturation=h_saturation,
            )

        return PreparedStage(
            execute=execute,
            argv=argv,
            argvs=argvs,
            allow_controlled_resource_stop=(
                context.stage.stage_id == self.controlled_stop_stage
            ),
        )


class _FakeCommandRunner:
    def __init__(
        self,
        *,
        exit_code: int = 0,
        write_watchdog_on_nonzero: bool = False,
    ) -> None:
        self.exit_code = exit_code
        self.write_watchdog_on_nonzero = write_watchdog_on_nonzero
        self.calls: list[tuple[str, int, str]] = []

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        attempt: object,
        invocation_index: int,
        argv_sha256: str,
    ) -> CommandExecution:
        self.calls.append(
            (
                attempt.context.stage.stage_id,
                invocation_index,
                argv_sha256,
            )
        )
        pid = 90_000_000 + invocation_index
        start_ticks = f"fake-{invocation_index}"
        attempt.record_process(
            pid,
            invocation_index=invocation_index,
            argv_sha256=argv_sha256,
            linux_start_ticks=start_ticks,
        )
        stdout = attempt.write_artifact(
            f"invocation-{invocation_index:03d}.stdout",
            b"fake stdout\n",
        )
        stderr = attempt.write_artifact(
            f"invocation-{invocation_index:03d}.stderr",
            b"",
        )
        record_index = argv.index("--record")
        record = Path(argv[record_index + 1])
        watchdog = None
        if self.exit_code == 0 or self.write_watchdog_on_nonzero:
            watchdog = attempt.write_artifact(
                record.name,
                b'{"status":"completed"}\n',
            )
            assert watchdog == record
        return CommandExecution(
            pid=pid,
            linux_start_ticks=start_ticks,
            exit_code=self.exit_code,
            stdout_path=stdout,
            stderr_path=stderr,
            watchdog_record_path=watchdog,
        )


def _constant(value: str) -> Callable[[], str]:
    return lambda: value


def test_dag_and_run_are_path_a_first_with_private_evidence(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    dag = build_campaign_stage_dag(identity)
    assert dag[0].stage_id == "path-a-bootstrap-initial_plan"
    first_b = next(
        index for index, stage in enumerate(dag) if stage.path_id == "B"
    )
    assert all(stage.path_id == "A" for stage in dag[:first_b])
    assert any(stage.stage_name == "p_shadow_discovery" for stage in dag)
    assert any(stage.stage_name == "h_shadow_discovery" for stage in dag)
    assert any(stage.stage_name == "cellwise_partition" for stage in dag)
    assert any(stage.stage_name == "goal_marking" for stage in dag)
    assert any(
        stage.stage_name == "p_selected_shadow_verification" for stage in dag
    )
    assert any(
        stage.stage_name == "h_selected_shadow_verification" for stage in dag
    )
    assert any(stage.stage_name == "shadow_bundle" for stage in dag)
    assert any(
        stage.stage_name == "internal_gate_deferred_or_final"
        for stage in dag
    )
    assert any(stage.stage_name == "isolation_audit" for stage in dag)
    assert any(stage.stage_name == "cycle_binding" for stage in dag)
    assert any(stage.stage_name == "cycle_advance" for stage in dag)
    assert any(stage.stage_name == "transition_or_pkeep" for stage in dag)

    preparer = _FakePreparer(freeze_cycle=0)
    root = tmp_path / "campaign"
    report = run_campaign(
        root,
        identity,
        prepare_stage=preparer,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )

    assert report["status"] == "completed"
    assert report["lane_status"] == {
        "A": "freeze_ready",
        "B": "freeze_ready",
    }
    assert report["finalization_status"] == "frozen"
    assert report["path_a_completed_before_path_b"] is True
    first_b_call = next(
        index
        for index, stage_id in enumerate(preparer.calls)
        if stage_id.startswith("path-b-")
    )
    assert all(
        stage_id.startswith("path-a-")
        for stage_id in preparer.calls[:first_b_call]
    )
    first_final_call = next(
        index
        for index, stage_id in enumerate(preparer.calls)
        if stage_id.startswith("campaign-final-")
    )
    assert all(
        stage_id.startswith("path-b-")
        for stage_id in preparer.calls[first_b_call:first_final_call]
    )
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    evidence_files = tuple(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith(".campaign-run")
    )
    assert evidence_files
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in evidence_files
    )


def test_resume_revalidates_receipts_and_does_not_rerun_completed_stage(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "campaign"
    first = _FakePreparer(freeze_cycle=0)
    partial = run_campaign(
        root,
        identity,
        prepare_stage=first,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
        maximum_new_stages=5,
    )
    assert partial["status"] == "partial"
    assert len(first.calls) == 5
    assert not any(stage.startswith("path-b-") for stage in first.calls)

    second = _FakePreparer(freeze_cycle=0)
    resumed = run_campaign(
        root,
        identity,
        prepare_stage=second,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    assert resumed["status"] == "completed"
    assert len(resumed["reused_stage_ids"]) >= 5
    assert not set(first.calls).intersection(second.calls)

    third = _FakePreparer(freeze_cycle=0)
    replay = run_campaign(
        root,
        identity,
        prepare_stage=third,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    assert replay["status"] == "completed"
    assert third.calls == []


def test_interrupted_attempt_is_preserved_and_new_attempt_is_used(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "campaign"
    failing = _FakePreparer(
        freeze_cycle=0,
        fail_stage_once="path-a-bootstrap-initial_plan",
    )
    with pytest.raises(RuntimeError, match="simulated interrupted"):
        run_campaign(
            root,
            identity,
            prepare_stage=failing,
            source_sha_provider=_constant(SOURCE_SHA),
            abi_sha256_provider=_constant(ABI_SHA),
            heavy_lock_path=tmp_path / "host-heavy.lock",
            command_runner=_FakeCommandRunner(),
        )

    succeeding = _FakePreparer(freeze_cycle=0)
    result = run_campaign(
        root,
        identity,
        prepare_stage=succeeding,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    assert result["status"] == "completed"
    stage_root = (
        root
        / "attempts"
        / "0000-path-a-bootstrap-initial_plan"
    )
    assert (stage_root / "attempt-000001" / "interrupted.json").is_file()
    assert (
        stage_root
        / "attempt-000001"
        / "invocation-000.process.json"
    ).is_file()
    assert (stage_root / "attempt-000002" / "intent.json").is_file()


def test_source_abi_plan_mode_symlink_and_artifact_drift_fail_closed(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "campaign"
    initialize_campaign(root, identity)
    with pytest.raises(CampaignIdentityDrift, match="source SHA"):
        run_campaign(
            root,
            identity,
            prepare_stage=_FakePreparer(),
            source_sha_provider=_constant("c" * 40),
            abi_sha256_provider=_constant(ABI_SHA),
            heavy_lock_path=tmp_path / "host-heavy.lock",
            command_runner=_FakeCommandRunner(),
        )
    with pytest.raises(CampaignIdentityDrift, match="ABI"):
        run_campaign(
            root,
            identity,
            prepare_stage=_FakePreparer(),
            source_sha_provider=_constant(SOURCE_SHA),
            abi_sha256_provider=_constant("d" * 64),
            heavy_lock_path=tmp_path / "host-heavy.lock",
            command_runner=_FakeCommandRunner(),
        )

    plan_a = identity.paths[0].initial_plan_path
    plan_a.chmod(0o644)
    with pytest.raises(CampaignEvidenceError, match="0600"):
        initialize_campaign(root, identity)
    plan_a.chmod(0o600)

    linked = tmp_path / "linked-plan.json"
    linked.symlink_to(plan_a)
    linked_identity = BlindCampaignIdentity(
        source_sha=SOURCE_SHA,
        abi_sha256=ABI_SHA,
        paths=(
            BlindPathIdentity(
                path_id="A",
                trial_id="linked-a",
                nominal_h_nm=20.0,
                initial_plan_path=linked,
                initial_plan_sha256=_sha(plan_a),
                initial_space_authority_path=(
                    identity.paths[0].initial_space_authority_path
                ),
                initial_space_authority_sha256=(
                    identity.paths[0].initial_space_authority_sha256
                ),
                qualified_solver_config_path=(
                    identity.paths[0].qualified_solver_config_path
                ),
                qualified_solver_config_sha256=(
                    identity.paths[0].qualified_solver_config_sha256
                ),
            ),
            identity.paths[1],
        ),
    )
    with pytest.raises(CampaignEvidenceError, match="symlink"):
        initialize_campaign(tmp_path / "linked-campaign", linked_identity)

    clean_root = tmp_path / "artifact-drift"
    run_campaign(
        clean_root,
        identity,
        prepare_stage=_FakePreparer(freeze_cycle=0),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    artifact = next(
        path
        for path in (clean_root / "attempts").rglob("result.json")
        if "path-a-bootstrap" in path.as_posix()
    )
    artifact.write_bytes(b"tampered\n")
    artifact.chmod(0o600)
    with pytest.raises(CampaignEvidenceError, match="SHA-256 differs"):
        run_campaign(
            clean_root,
            identity,
            prepare_stage=_FakePreparer(freeze_cycle=0),
            source_sha_provider=_constant(SOURCE_SHA),
            abi_sha256_provider=_constant(ABI_SHA),
            heavy_lock_path=tmp_path / "host-heavy.lock",
            command_runner=_FakeCommandRunner(),
        )


def test_watchdog_builder_enforces_mpi8_and_final_mpi1_only(
    tmp_path: Path,
) -> None:
    plan = _private_file(tmp_path / "plan.json", b'{"plan":1}\n')
    base = dict(
        python_executable=Path(sys.executable),
        source_sha=SOURCE_SHA,
        path_id="A",
        nominal_h_nm=20.0,
        trial_id="task035e-blind-path-a",
        cycle_index=0,
        output_role="current",
        plan_path=plan,
        plan_sha256=_sha(plan),
        artifact_root=tmp_path / "artifacts",
        tensor_cache_directory=tmp_path / "cache",
        run_dir=tmp_path / "run",
        record_path=tmp_path / "record.json",
    )
    mpi8 = build_watchdog_argv(WatchdogLaunchSpec(**base))
    assert mpi8[:3] == (
        sys.executable,
        "-m",
        "benchmarks.run_task033_full3d_watchdog",
    )
    assert "--mpi-size" in mpi8
    assert mpi8[mpi8.index("--mpi-size") + 1] == "8"
    assert validate_watchdog_argv(mpi8) == mpi8

    with pytest.raises(BlindCampaignError, match="MPI2"):
        build_watchdog_argv(WatchdogLaunchSpec(**base, mpi_size=2))

    snapshot = _private_file(tmp_path / "snapshot.json", b'{"snapshot":1}\n')
    serial_base = {
        **base,
        "mpi_size": 1,
        "internal_probe_kind": "serial_mpi1",
        "final_internal_gate": True,
        "current_snapshot_path": snapshot,
        "current_snapshot_sha256": _sha(snapshot),
    }
    serial = build_watchdog_argv(WatchdogLaunchSpec(**serial_base))
    assert serial[serial.index("--mpi-size") + 1] == "1"
    assert (
        serial[serial.index("--task035e-internal-probe-kind") + 1]
        == "serial_mpi1"
    )
    with pytest.raises(BlindCampaignError, match="final internal Gate"):
        build_watchdog_argv(
            WatchdogLaunchSpec(
                **{**serial_base, "final_internal_gate": False}
            )
        )

    wrong = list(mpi8)
    wrong[2] = "benchmarks.some_other_runner"
    with pytest.raises(BlindCampaignError, match="only the qualified"):
        validate_watchdog_argv(wrong)


def test_single_heavy_lock_is_nonblocking_and_host_scoped(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "one-heavy.lock"
    with SingleHeavyLock(lock_path):
        with pytest.raises(HeavyStageBusy):
            with SingleHeavyLock(lock_path):
                pass
    with SingleHeavyLock(lock_path):
        pass


def test_unknown_p6_saturation_blocks_freeze_and_stops_lane(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "campaign"
    result = run_campaign(
        root,
        identity,
        prepare_stage=_FakePreparer(
            freeze_cycle=0,
            saturation="unknown",
        ),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    assert result["lane_status"] == {
        "A": "controlled_negative",
        "B": "controlled_negative",
    }
    receipts = tuple((root / "receipts").glob("*.json"))
    payloads = [json.loads(path.read_text())["payload"] for path in receipts]
    blocked = [
        row
        for row in payloads
        if row["classification"]
        == "freeze_blocked_p6_saturation_unknown"
    ]
    assert len(blocked) == 2
    assert all(row["status"] == "controlled_negative" for row in blocked)


def test_unknown_h_level3_saturation_blocks_forged_freeze(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "campaign"
    result = run_campaign(
        root,
        identity,
        prepare_stage=_FakePreparer(
            freeze_cycle=0,
            saturation="verified",
            h_saturation="unknown",
        ),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    assert result["lane_status"] == {
        "A": "controlled_negative",
        "B": "controlled_negative",
    }
    receipts = tuple((root / "receipts").glob("*.json"))
    payloads = [
        json.loads(path.read_text())["payload"] for path in receipts
    ]
    blocked = [
        row
        for row in payloads
        if row["classification"]
        == "freeze_blocked_h_level3_saturation_unknown"
    ]
    assert len(blocked) == 2
    assert all(
        row["p6_saturation"] == "verified"
        and row["h_level3_saturation"] == "unknown"
        and row["status"] == "controlled_negative"
        for row in blocked
    )


def test_final_internal_probe_batch_is_ordered_and_all_commands_are_bound(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "campaign"
    runner = _FakeCommandRunner()
    report = run_campaign(
        root,
        identity,
        prepare_stage=_FakePreparer(internal_probe_batch=True),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "host-heavy.lock",
        command_runner=runner,
        maximum_new_stages=11,
    )
    assert report["status"] == "partial"
    internal_receipt = next(
        path
        for path in (root / "receipts").glob("*.json")
        if "internal_gate_deferred_or_final" in path.name
    )
    payload = json.loads(internal_receipt.read_text())["payload"]
    assert len(payload["command_argv_sha256s"]) == 4
    internal_calls = [
        row
        for row in runner.calls
        if row[0].endswith("internal_gate_deferred_or_final")
    ]
    assert [row[1] for row in internal_calls] == [0, 1, 2, 3]
    assert [row[2] for row in internal_calls] == payload[
        "command_argv_sha256s"
    ]

    with pytest.raises(
        BlindCampaignError,
        match="closed ordered four-probe inventory",
    ):
        run_campaign(
            tmp_path / "reversed",
            identity,
            prepare_stage=_FakePreparer(
                internal_probe_batch=True,
                reverse_internal_probes=True,
            ),
            source_sha_provider=_constant(SOURCE_SHA),
            abi_sha256_provider=_constant(ABI_SHA),
            heavy_lock_path=tmp_path / "host-heavy-2.lock",
            command_runner=_FakeCommandRunner(),
            maximum_new_stages=11,
        )


def test_command_receipt_drift_and_nonzero_exit_fail_closed(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    failed_root = tmp_path / "failed"
    with pytest.raises(
        Exception,
        match="exited with 9",
    ):
        run_campaign(
            failed_root,
            identity,
            prepare_stage=_FakePreparer(),
            source_sha_provider=_constant(SOURCE_SHA),
            abi_sha256_provider=_constant(ABI_SHA),
            heavy_lock_path=tmp_path / "failed-heavy.lock",
            command_runner=_FakeCommandRunner(exit_code=9),
        )
    current_attempt = (
        failed_root
        / "attempts"
        / "0001-path-a-cycle-0-current_solve"
        / "attempt-000001"
    )
    command_receipt = json.loads(
        (current_attempt / "invocation-000.receipt.json").read_text()
    )["payload"]
    assert command_receipt["exit_code"] == 9
    assert command_receipt["expected_watchdog_record"] is None
    assert not (
        failed_root
        / "receipts"
        / "0001-path-a-cycle-0-current_solve.json"
    ).exists()

    root = tmp_path / "drift"
    run_campaign(
        root,
        identity,
        prepare_stage=_FakePreparer(internal_probe_batch=True),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "drift-heavy.lock",
        command_runner=_FakeCommandRunner(),
        maximum_new_stages=11,
    )
    internal_attempt = next(
        path
        for path in (root / "attempts").glob(
            "*internal_gate_deferred_or_final/attempt-000001"
        )
    )
    stdout = internal_attempt / "invocation-002.stdout"
    stdout.write_bytes(b"tampered\n")
    stdout.chmod(0o600)
    with pytest.raises(
        CampaignEvidenceError,
        match="SHA-256 differs",
    ):
        run_campaign(
            root,
            identity,
            prepare_stage=_FakePreparer(internal_probe_batch=True),
            source_sha_provider=_constant(SOURCE_SHA),
            abi_sha256_provider=_constant(ABI_SHA),
            heavy_lock_path=tmp_path / "drift-heavy.lock",
            command_runner=_FakeCommandRunner(),
            maximum_new_stages=0,
        )


def test_controlled_resource_stop_receipt_replays_and_advances_next_path(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    root = tmp_path / "controlled-stop"
    stage_id = "path-a-cycle-0-current_solve"
    first = run_campaign(
        root,
        identity,
        prepare_stage=_FakePreparer(controlled_stop_stage=stage_id),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "controlled-stop-heavy.lock",
        command_runner=_FakeCommandRunner(
            exit_code=2,
            write_watchdog_on_nonzero=True,
        ),
        maximum_new_stages=2,
    )
    assert first["status"] == "partial"
    assert first["lane_status"]["A"] == "controlled_negative"

    resumed_preparer = _FakePreparer(freeze_cycle=0)
    resumed = run_campaign(
        root,
        identity,
        prepare_stage=resumed_preparer,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "controlled-stop-heavy.lock",
        command_runner=_FakeCommandRunner(),
        maximum_new_stages=1,
    )
    assert resumed["status"] == "partial"
    assert stage_id in resumed["reused_stage_ids"]
    assert resumed["executed_stage_ids"] == [
        "path-b-bootstrap-initial_plan"
    ]


def test_campaign_finalization_waits_for_both_paths_and_mismatch_stops_freeze(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    partial_root = tmp_path / "one-path"
    partial_preparer = _FakePreparer(freeze_cycle=0)
    partial = run_campaign(
        partial_root,
        identity,
        prepare_stage=partial_preparer,
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "one-path-heavy.lock",
        command_runner=_FakeCommandRunner(),
        maximum_new_stages=14,
    )
    assert partial["status"] == "partial"
    assert partial["lane_status"]["A"] == "freeze_ready"
    assert partial["finalization_status"] == "not_run_lane_not_ready"
    assert not any(
        stage_id.startswith("campaign-final-")
        for stage_id in partial_preparer.calls
    )
    assert not tuple(
        (partial_root / "receipts").glob("*campaign-final*.json")
    )

    mismatch_root = tmp_path / "mismatch"
    mismatch = run_campaign(
        mismatch_root,
        identity,
        prepare_stage=_FakePreparer(
            freeze_cycle=0,
            two_start_mismatch=True,
        ),
        source_sha_provider=_constant(SOURCE_SHA),
        abi_sha256_provider=_constant(ABI_SHA),
        heavy_lock_path=tmp_path / "mismatch-heavy.lock",
        command_runner=_FakeCommandRunner(),
    )
    assert mismatch["lane_status"] == {
        "A": "freeze_ready",
        "B": "freeze_ready",
    }
    assert mismatch["finalization_status"] == "controlled_negative"
    comparison = next(
        path
        for path in (mismatch_root / "receipts").glob("*.json")
        if "two_start_comparison" in path.name
    )
    comparison_payload = json.loads(
        comparison.read_text()
    )["payload"]
    assert comparison_payload["status"] == "controlled_negative"
    assert comparison_payload["classification"] == (
        "two_start_outputs_differ"
    )
    assert not any(
        "candidate_freeze" in path.name
        for path in (mismatch_root / "receipts").glob("*.json")
    )


def test_formal_campaign_source_has_no_protected_layer_import_tokens() -> None:
    import benchmarks.task035e_blind_campaign as campaign

    source = Path(campaign.__file__).read_text(encoding="utf-8").lower()
    protected = (
        "reference_certifier",
        "hidden_auditor",
        "sealed_reference",
        "sealed-reference",
    )
    for token in protected:
        assert f"import {token}" not in source
        assert f"from {token}" not in source
