"""T3b launcher, provenance, worker-copy, and resource contracts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.task034_wsl_resources import (
    _read_smaps_rollup,
    process_tree_smaps_sample,
)
from scripts.run_case import main as run_case_main
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.execution_plan import CONTRACT_PROBE_ADAPTER, build_execution_plan
from src.io.resolved_config import canonical_json_bytes, resolved_config_bytes
from src.runners import task038_launcher as launcher
from src.runners.task038_input_worker import validate_worker_contract
from src.runners.task038_launcher import _run_worker, _swap_bytes, launch_specification


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/full3d_direct_example.dat"
TASK039_DIRECT = ROOT / "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat"
TASK039_H5_DIRECT = ROOT / "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat"
TASK039_V4_H4_DIRECT = (
    ROOT / "input/official/task039/5nm_p6h4_v4_1deg_full3d_direct_mpi8.dat"
)
TASK039_V4_H4_ITERATIVE = (
    ROOT / "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
)
SOURCE_SHA = "a" * 40
REQUIRED_FILES = {
    "input_original.dat",
    "resolved_config.json",
    "run_manifest.json",
    "input_sha256.txt",
    "physical_model_sha256.txt",
    "source_sha.txt",
    "run_summary.json",
}


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)


def _input(tmp_path: Path, **updates):
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in updates.items():
        pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=\s*.*$")
        text, count = pattern.subn(f"{key} = {_toml_value(value)}", text)
        assert count == 1, key
    path = tmp_path / "case.dat"
    path.write_text(text, encoding="utf-8")
    return load_and_resolve(path)


class _FakeProcess:
    def __init__(self, returncode=None):
        self.pid = 4242
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self):
        if self.returncode is None:
            self.returncode = -15
        return self.returncode


class _SequenceProcess:
    def __init__(self, polls_before_exit=1):
        self.pid = 4343
        self.returncode = None
        self._poll_count = 0
        self._polls_before_exit = polls_before_exit

    def poll(self):
        if self._poll_count < self._polls_before_exit:
            self._poll_count += 1
            return None
        self.returncode = 0
        return self.returncode

    def wait(self):
        self.returncode = 0
        return self.returncode


def _authority(*, memory=1024, swap=0):
    return {
        "memory_authority_bytes": memory,
        "process_tree": {
            "rss_bytes": memory,
            "swap_bytes": swap,
            "pids": [4242],
            "all_status_readable": True,
        },
        "job_cgroup": {
            "dedicated_job_cgroup": False,
            "memory_current_bytes": None,
            "swap_current_bytes": None,
        },
    }


def _unreadable_authority():
    authority = _authority()
    authority["process_tree"]["all_status_readable"] = False
    return authority


def _authority_with_smaps(*, rss=1024, pss=1024, uss=512, complete=True):
    authority = _authority(memory=rss)
    authority["process_tree"]["smaps"] = {
        "complete": complete,
        "pss_bytes": pss if complete else None,
        "uss_bytes": uss if complete else None,
        "readable_pid_count": 1 if complete else 0,
        "pid_count": 1,
    }
    return authority


def _task039_spec(tmp_path):
    return replace(
        load_and_resolve(TASK039_DIRECT),
        expected_output_parent=tmp_path / "results",
    )


def _task039_v4_h4_spec(tmp_path):
    return replace(
        load_and_resolve(TASK039_V4_H4_DIRECT),
        expected_output_parent=tmp_path / "results",
    )


def _fake_launch(specification, tmp_path, *, process, sample, **kwargs):
    calls = {}

    def popen(argv, **popen_kwargs):
        calls["argv"] = argv
        calls["kwargs"] = popen_kwargs
        return process

    terminated = []

    def terminate(member):
        terminated.append(member)
        member.returncode = -9
        return {"requested": True}

    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        timestamp=kwargs.pop("timestamp", "20260812T000000.000000Z"),
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=popen,
        sample_factory=lambda _pid: sample,
        terminate_factory=terminate,
        monotonic=kwargs.pop("monotonic", lambda: 0.0),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    return result, calls, terminated


def test_public_cli_modes_are_thin_and_side_effect_free(tmp_path, capsys, monkeypatch):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))

    def fail_subprocess(*_args, **_kwargs):
        pytest.fail("validate/dry-run started a subprocess")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    monkeypatch.setattr(subprocess, "Popen", fail_subprocess)
    assert run_case_main([str(specification.source_path), "--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"
    assert run_case_main([str(specification.source_path), "--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["physical_model_sha256"] == specification.physical_model_sha256
    assert not (tmp_path / "results").exists()

    with pytest.raises(SystemExit):
        run_case_main([str(specification.source_path), "--validate-only", "--dry-run"])
    with pytest.raises(SystemExit):
        run_case_main([str(specification.source_path), "--unknown"])
    with pytest.raises(SystemExit):
        run_case_main([])


def test_public_script_bootstraps_repository_root_without_pythonpath():
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_case.py",
            "input/templates/full3d_direct_example.dat",
            "--validate-only",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "valid"


def test_launcher_bootstrap_is_byte_exact_and_probe_is_not_numerical(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    result, calls, terminated = _fake_launch(
        specification,
        tmp_path,
        process=_FakeProcess(0),
        sample=_authority(),
    )
    run_directory = Path(result["run_directory"])
    assert result["result_classification"] == "contract_probe_pass"
    assert not terminated
    assert set(path.name for path in run_directory.iterdir()) >= REQUIRED_FILES
    assert (
        run_directory / "input_original.dat"
    ).read_bytes() == specification.raw_input_bytes
    assert (
        run_directory / "input_sha256.txt"
    ).read_text().strip() == specification.input_sha256
    manifest = json.loads((run_directory / "run_manifest.json").read_bytes())
    summary = json.loads((run_directory / "run_summary.json").read_bytes())
    assert manifest["status"] == "finished"
    assert manifest["result_classification"] == "contract_probe_pass"
    assert manifest["resolved_method_adapter"] == CONTRACT_PROBE_ADAPTER
    assert manifest["numerical_output_directory"] == str(
        run_directory / "numerical_output"
    )
    assert summary["result_classification"] == "contract_probe_pass"
    assert summary["numerical_output_directory"] == str(
        run_directory / "numerical_output"
    )
    assert not (run_directory / "numerical_output").exists()
    assert calls["kwargs"]["shell"] is False
    assert isinstance(calls["argv"], list)
    assert calls["argv"][5] == "src.runners.task038_input_worker"

    with pytest.raises(ValueError, match="collision"):
        _fake_launch(
            specification,
            tmp_path,
            process=_FakeProcess(0),
            sample=_authority(),
        )


def test_worker_popen_uses_task38_source_root_as_cwd(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    captured = {}

    def popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakeProcess(0)

    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        timestamp="20260812T000001.250000Z",
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=popen,
        sample_factory=lambda _pid: _authority(),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    assert result["result_classification"] == "contract_probe_pass"
    assert captured["kwargs"]["cwd"] == Path(__file__).resolve().parents[2]


def test_public_full3d_adapter_is_connected_but_worker_result_is_not_numeric_pass(
    tmp_path,
):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))

    class _CompletedProcess(_FakeProcess):
        pass

    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        timestamp="20260812T000001.000000Z",
        popen_factory=lambda *_args, **_kwargs: _CompletedProcess(0),
        sample_factory=lambda _pid: _authority(),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    assert result["result_classification"] == "worker_exit0"
    assert result["exit_status"] == 0
    summary = json.loads(Path(result["summary"]).read_bytes())
    assert summary["result_classification"] == "worker_exit0"
    manifest = json.loads(Path(result["manifest"]).read_bytes())
    assert manifest["resolved_method_adapter"] == "task038.full3d_direct"


def test_future_normal_worker_exit_is_not_a_numerical_pass(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    run_directory = tmp_path / "worker-run"
    run_directory.mkdir()
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
    )
    plan = replace(plan, adapter_available=True)
    process = _FakeProcess(0)
    result = _run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=lambda argv, **kwargs: process,
        sample_factory=lambda _pid: _authority(),
        terminate_factory=lambda _process: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    assert result["result_classification"] == "worker_exit0"


@pytest.mark.parametrize("source_sha", ("", "not-a-commit"))
def test_source_sha_is_fail_closed_before_output_creation(tmp_path, source_sha):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    with pytest.raises(InputError, match="source SHA"):
        launch_specification(specification, source_sha=source_sha)
    assert not (tmp_path / "results").exists()


def test_swap_uses_process_tree_and_only_dedicated_cgroup():
    ignored_cgroup = _authority()
    ignored_cgroup["job_cgroup"] = {
        "dedicated_job_cgroup": False,
        "swap_current_bytes": 99,
    }
    assert _swap_bytes(ignored_cgroup) == 0
    dedicated_cgroup = _authority()
    dedicated_cgroup["job_cgroup"] = {
        "dedicated_job_cgroup": True,
        "swap_current_bytes": 99,
    }
    assert _swap_bytes(dedicated_cgroup) == 99


def test_zero_swap_requires_all_authoritative_samples_to_be_zero(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    run_directory = tmp_path / "worker-run"
    run_directory.mkdir()
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
    )
    plan = replace(plan, adapter_available=True)
    process = _FakeProcess(None)
    samples = iter((_authority(swap=0), _authority(swap=1)))

    def terminate(member):
        member.returncode = -9
        return {"requested": True}

    result = _run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=lambda argv, **kwargs: process,
        sample_factory=lambda _pid: next(samples),
        terminate_factory=terminate,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    assert result["resource_authority"]["zero_swap_observed"] is False


def test_launcher_popen_error_finalizes_manifest(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))

    def fail_popen(*_args, **_kwargs):
        raise OSError("mpiexec unavailable")

    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        timestamp="20260812T000001.500000Z",
        contract_probe=True,
        popen_factory=fail_popen,
    )
    assert result["result_classification"] == "worker_launch_error"
    manifest = json.loads(Path(result["manifest"]).read_bytes())
    assert manifest["status"] == "finished"
    assert manifest["end_time"] is not None


def test_unreadable_resource_sample_is_not_zero_swap_authority(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    result, _calls, _terminated = _fake_launch(
        specification,
        tmp_path,
        process=_FakeProcess(0),
        sample=_unreadable_authority(),
        timestamp="20260812T000001.750000Z",
    )
    authority = result["resource_authority"]
    assert authority["status"] == "not_available"
    assert authority["zero_swap_observed"] is None


@pytest.mark.parametrize(
    ("relative_input", "warning_gib", "terminate_gib"),
    (
        ("5nm_p6h7p5_full3d_direct_mpi8.dat", 170.0, 195.0),
        ("5nm_p6h10_hybrid_iterative_m480_solver_only_mpi1.dat", 45.0, 48.0),
        ("5nm_p6h10_full3d_direct_mpi8.dat", 180.0, 220.0),
    ),
)
def test_task039_budget_uses_profile_execution_limits(
    monkeypatch, relative_input, warning_gib, terminate_gib
):
    monkeypatch.setattr(
        launcher,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 256 * 1024**3},
    )
    monkeypatch.setattr(
        launcher,
        "cgroup_snapshot",
        lambda _scope: {"memory_limit_bytes": None},
    )
    specification = load_and_resolve(ROOT / "input/official/task039" / relative_input)
    budget = launcher._task039_memory_budget(specification.execution)
    assert budget["configured_warning_memory_gib"] == warning_gib
    assert budget["configured_terminate_memory_gib"] == terminate_gib
    assert budget["effective_terminate_memory_gib"] == pytest.approx(
        min(terminate_gib, 0.90 * 256.0)
    )
    assert budget["warning_memory_gib"]["value"] == warning_gib


def test_task039_h5_absolute_budget_uses_contract_bytes_and_critical_checkpoint(
    monkeypatch,
):
    monkeypatch.setattr(
        launcher,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 256 * 1024**3},
    )
    monkeypatch.setattr(
        launcher,
        "cgroup_snapshot",
        lambda _scope: {"memory_limit_bytes": None},
    )
    specification = load_and_resolve(TASK039_H5_DIRECT)
    budget = launcher._task039_memory_budget(specification.execution)

    assert budget["memory_termination_policy"] == "absolute_bytes"
    assert budget["configured_critical_memory_gib"] == 195.0
    assert budget["absolute_terminate_memory_bytes"] == 224_000_000_000
    assert budget["effective_terminate_memory_gib"] == pytest.approx(
        224_000_000_000 / 1024**3
    )
    assert budget["hard_stop_memory_gib"]["classification"] == "contract"


def _run_h5_worker(
    tmp_path: Path,
    specification,
    sample,
    *,
    poll_interval=0.0,
    terminated=None,
):
    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        contract_probe=False,
        task039_trace_audit=False,
    )
    process = _SequenceProcess()
    run_directory = tmp_path / "h5-worker"
    run_directory.mkdir()
    terminated = [] if terminated is None else terminated
    result = launcher._run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=lambda *_args, **_kwargs: process,
        sample_factory=lambda _pid: sample,
        terminate_factory=lambda member: (
            terminated.append(member)
            or setattr(member, "returncode", -9)
            or {"requested": True}
        ),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=poll_interval,
    )
    return result, terminated


def _run_v7_full_worker_with_fake_clock(
    tmp_path: Path,
    monkeypatch,
    clock_values,
    *,
    memory=8 * 1024**3,
):
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution: {
            "configured_warning_memory_gib": 170.0,
            "configured_critical_memory_gib": 195.0,
            "effective_terminate_memory_gib": 195.0,
            "absolute_terminate_memory_bytes": 224_000_000_000,
        },
    )
    specification = replace(
        load_and_resolve(TASK039_V4_H4_ITERATIVE),
        expected_output_parent=tmp_path / "results",
    )
    run_directory = tmp_path / "v7-full-worker"
    run_directory.mkdir()
    process = _FakeProcess()
    terminated = []
    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        method="task039_v7_h4_exact_side_full_formal",
        contract_probe=False,
        task039_trace_audit=False,
    )

    def popen(_argv, **_kwargs):
        marker_path = (
            run_directory / "numerical_output" / "memory_stage_markers.raw.jsonl"
        )
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(
            "".join(
                json.dumps(marker) + "\n"
                for marker in (
                    {
                        "stage": "outer_solve_begin",
                        "status": "begin",
                        "elapsed_seconds": 1.0,
                    },
                    {
                        "stage": "outer_solve_progress",
                        "status": "running",
                        "elapsed_seconds": 2.0,
                        "detail": {"multimetric_max_true_residual": 1.0},
                    },
                    {
                        "stage": "outer_solve_progress",
                        "status": "running",
                        "elapsed_seconds": 3.0,
                        "detail": {"multimetric_max_true_residual": 0.5},
                    },
                )
            ),
            encoding="utf-8",
        )
        return process

    clock = iter(clock_values)
    result = launcher._run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=popen,
        sample_factory=lambda _pid: _authority(memory=memory),
        terminate_factory=lambda member: (
            terminated.append(member)
            or setattr(member, "returncode", -15)
            or {"requested": True}
        ),
        monotonic=lambda: next(clock),
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    return result, terminated


def test_v7_full_timeout_extends_once_after_outer_progress_decreases(
    tmp_path, monkeypatch
):
    result, terminated = _run_v7_full_worker_with_fake_clock(
        tmp_path,
        monkeypatch,
        (0.0, 1.0, 21601.0, 21602.0, 28801.0),
    )
    telemetry = result["resource_authority"]["v7_h4_exact_side_full_formal_telemetry"]
    decision = telemetry["authority"]["timeout_policy"]["decision"]
    assert result["result_classification"] == "timeout"
    assert len(terminated) == 1
    assert decision["status"] == "extended_once"
    assert decision["effective_timeout_seconds"] == 28800
    assert telemetry["authority"]["timeout_policy"]["hard_stop_bytes"] == 100262797312
    assert telemetry["authority"]["timeout_policy"]["peak_swap_bytes"] == 0


def test_v7_full_timeout_decision_distinguishes_memory_stop(tmp_path, monkeypatch):
    result, terminated = _run_v7_full_worker_with_fake_clock(
        tmp_path,
        monkeypatch,
        (0.0, 1.0, 2.0),
        memory=100262797312,
    )
    decision = result["resource_authority"]["v7_h4_exact_side_full_formal_telemetry"][
        "authority"
    ]["timeout_policy"]["decision"]
    assert result["result_classification"] == "memory_terminate"
    assert len(terminated) == 1
    assert decision["status"] == "not_reached_due_to_memory_terminate"
    assert decision["classification"] == "memory_terminate"


def test_v8_layer_block_launcher_emits_explicit_telemetry(tmp_path):
    specification = replace(
        load_and_resolve(TASK039_V4_H4_ITERATIVE),
        expected_output_parent=tmp_path / "results",
    )
    run_directory = tmp_path / "v8-layer-block-worker"
    run_directory.mkdir()
    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        method="task039_v8_h4_layer_block_reconstruction",
        contract_probe=False,
        task039_trace_audit=False,
    )
    result = launcher._run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=lambda *_args, **_kwargs: _FakeProcess(0),
        sample_factory=lambda _pid: _authority(memory=1024, swap=0),
        terminate_factory=lambda _member: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    telemetry = result["resource_authority"][
        "v8_h4_layer_block_reconstruction_telemetry"
    ]
    assert telemetry["method"] == "task039_v8_h4_layer_block_reconstruction"
    assert telemetry["profile"] == "task039.v8.h4.layer_block_reconstruction.v1"
    assert telemetry["absolute_terminate_memory_bytes"] == 224_000_000_000
    assert telemetry["method_override"][
        "effective_absolute_terminate_memory_bytes"
    ] == (224_000_000_000)
    assert telemetry["gate_contract"]["exact_factor_count"] == 0
    assert telemetry["gate_contract"]["global_direct_factor_count"] == 0
    assert telemetry["gate_contract"]["qep_count"] == 0
    assert telemetry["gate_contract"]["outer_ksp_count"] == 0
    assert telemetry["require_zero_swap"] is True


def test_v8_layer_sweep_launcher_keeps_parent_intervals_separate(tmp_path):
    specification = replace(
        load_and_resolve(TASK039_V4_H4_ITERATIVE),
        expected_output_parent=tmp_path / "results",
    )
    run_directory = tmp_path / "v8-layer-sweep-worker"
    run_directory.mkdir()
    diagnostic_directory = run_directory / "numerical_output"
    diagnostic_directory.mkdir()
    (diagnostic_directory / "v3_v7_diagnostic.json").write_text(
        json.dumps(
            {
                "schema": "wrong-schema",
                "method": "task039_v8_h4_layer_sweep_bottom",
                "source_sha": "b" * 40,
                "gate": {"numerical_holdout_gate_pass": True},
            }
        ),
        encoding="utf-8",
    )
    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        method="task039_v8_h4_layer_sweep_bottom",
        source_sha="a" * 40,
        contract_probe=False,
        task039_trace_audit=False,
    )
    result = launcher._run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=lambda *_args, **_kwargs: _FakeProcess(0),
        sample_factory=lambda _pid: _authority(memory=1024, swap=0),
        terminate_factory=lambda _member: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    telemetry = result["resource_authority"]["v8_h4_layer_sweep_bottom_telemetry"]
    assert telemetry["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert telemetry["construction_interval_summary"]["status"] == "not_available"
    assert telemetry["retained_interval_summary"]["status"] == "not_available"
    assert telemetry["overall"]["pass"] is False
    assert telemetry["numerical_status"] == "not_available"
    assert telemetry["worker_record_status"] == "identity_mismatch"
    assert telemetry["method_interval_role"] == (
        "evidence_only_checkpoint; not a substitute for the overall intervals"
    )
    assert set(telemetry["method_intervals"]) == {"J1", "F1", "FB1", "FB2", "FB4"}
    assert all(
        item["role"] == "evidence_only_checkpoint"
        for item in telemetry["method_intervals"].values()
    )


@pytest.mark.parametrize(
    "numerical_pass", [True, False], ids=["pass", "numerical-fail"]
)
def test_v8_layer_sweep_launcher_measures_overall_and_method_intervals(
    tmp_path, numerical_pass
):
    specification = replace(
        load_and_resolve(TASK039_V4_H4_ITERATIVE),
        expected_output_parent=tmp_path / "results",
    )
    run_directory = tmp_path / ("v8-layer-sweep-measured-" + str(numerical_pass))
    run_directory.mkdir()
    diagnostic_directory = run_directory / "numerical_output"
    diagnostic_directory.mkdir()
    source_sha = "c" * 40
    methods = ("J1", "F1", "FB1", "FB2", "FB4")
    (diagnostic_directory / "v3_v7_diagnostic.json").write_text(
        json.dumps(
            {
                "schema": "task039.v8.h4.layer_sweep.bottom_component.v1",
                "method": "task039_v8_h4_layer_sweep_bottom",
                "source_sha": source_sha,
                "gate": {"numerical_holdout_gate_pass": numerical_pass},
            }
        ),
        encoding="utf-8",
    )
    marker_path = diagnostic_directory / "memory_stage_markers.raw.jsonl"
    marker_batches = {
        1: ["v8_layer_sweep_bottom_construction_begin"],
        2: [],
        3: [
            marker
            for method in methods
            for marker in (
                f"v8_layer_sweep_bottom_{method}_woodbury_begin",
                f"v8_layer_sweep_bottom_{method}_woodbury_ready",
            )
        ],
        4: [
            marker
            for method in methods
            for marker in (
                f"v8_layer_sweep_bottom_{method}_cleanup",
                f"v8_layer_sweep_bottom_{method}_complete",
            )
        ]
        + [
            "v8_layer_sweep_bottom_construction_end",
            *(
                ["v8_layer_sweep_bottom_retained_apply_state_ready"]
                if numerical_pass
                else []
            ),
        ],
        5: (["v8_layer_sweep_bottom_retained_state_release"] if numerical_pass else []),
    }
    sample_memory = (
        10 * 2**30,
        44 * 2**30,
        20 * 2**30,
        20 * 2**30,
        20 * 2**30,
    )
    sample_calls = 0

    def popen(_argv, **_kwargs):
        return _SequenceProcess(polls_before_exit=4)

    def sample_factory(_pid):
        nonlocal sample_calls
        sample_calls += 1
        with marker_path.open("a", encoding="utf-8") as stream:
            for marker in marker_batches[sample_calls]:
                stream.write(
                    json.dumps(
                        {
                            "stage": marker,
                            "status": "end",
                            "elapsed_seconds": float(sample_calls),
                        }
                    )
                    + "\n"
                )
        return _authority(memory=sample_memory[sample_calls - 1], swap=0)

    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        method="task039_v8_h4_layer_sweep_bottom",
        source_sha=source_sha,
        contract_probe=False,
        task039_trace_audit=False,
    )
    result = launcher._run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=popen,
        sample_factory=sample_factory,
        terminate_factory=lambda _process: {"requested": True},
        monotonic=iter(float(index) for index in range(11)).__next__,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    telemetry = result["resource_authority"]["v8_h4_layer_sweep_bottom_telemetry"]
    assert telemetry["worker_record_status"] == "measured"
    assert telemetry["numerical_gate_pass"] is numerical_pass
    assert telemetry["overall"]["numerical_gate_pass"] is numerical_pass
    assert telemetry["overall"]["construction_pass"] is True
    assert telemetry["construction_interval_summary"]["status"] == "measured"
    assert (
        telemetry["construction_interval_summary"]["peak_process_tree_rss_bytes"]
        == 44 * 2**30
    )
    assert set(telemetry["method_intervals"]) == set(methods)
    assert all(
        interval["construction"]["status"] == "measured"
        and interval["retained"]["status"] == "measured"
        for interval in telemetry["method_intervals"].values()
    )
    method_peaks = [
        interval["construction"]["peak_process_tree_rss_bytes"]
        for interval in telemetry["method_intervals"].values()
    ]
    assert max(method_peaks) == 20 * 2**30
    assert telemetry["construction_interval_summary"][
        "peak_process_tree_rss_bytes"
    ] > max(method_peaks)
    assert telemetry["zero_swap_observed"] is True
    assert telemetry["overall_peak_swap_bytes"] == 0
    if numerical_pass:
        assert telemetry["retained_interval_summary"]["status"] == "measured"
        assert telemetry["retained_interval_summary"]["pass"] is True
        assert telemetry["overall"]["pass"] is True
        assert result["result_classification"] == "worker_exit0"
    else:
        assert telemetry["retained_interval_summary"]["status"] == "not_available"
        assert telemetry["overall"]["pass"] is False
        assert telemetry["overall"]["status"] == (
            "numerical_gate_failed_retained_not_run"
        )


def test_v9_bare_f_launcher_binds_worker_identity_and_retained_not_run(tmp_path):
    specification = replace(
        load_and_resolve(TASK039_V4_H4_ITERATIVE),
        expected_output_parent=tmp_path / "results",
    )
    run_directory = tmp_path / "v9-bare-f-worker"
    diagnostic_directory = run_directory / "numerical_output"
    diagnostic_directory.mkdir(parents=True)
    source_sha = "d" * 40
    (diagnostic_directory / "v3_v7_diagnostic.json").write_text(
        json.dumps(
            {
                "schema": launcher.V9_H4_BARE_F_SIDE_SCHEMA,
                "method": launcher.V9_H4_BARE_F_SIDE_METHOD,
                "source_sha": source_sha,
                "gate": {"numerical_holdout_gate_pass": True},
            }
        ),
        encoding="utf-8",
    )
    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        method=launcher.V9_H4_BARE_F_SIDE_METHOD,
        source_sha=source_sha,
        contract_probe=False,
        task039_trace_audit=False,
    )
    result = launcher._run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=lambda *_args, **_kwargs: _FakeProcess(0),
        sample_factory=lambda _pid: _authority(memory=1024, swap=0),
        terminate_factory=lambda _member: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    telemetry = result["resource_authority"]["v9_h4_bare_f_side_telemetry"]
    assert telemetry["method"] == launcher.V9_H4_BARE_F_SIDE_METHOD
    assert telemetry["profile"] == launcher.V9_H4_BARE_F_SIDE_SCHEMA
    assert telemetry["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert telemetry["construction_interval_summary"]["status"] == "not_available"
    assert telemetry["retained_interval_summary"]["status"] == "not_run"
    assert telemetry["retained_interval_summary"]["pass"] is None
    assert telemetry["numerical_gate_pass"] is True
    assert telemetry["overall"]["pass"] is None
    assert telemetry["overall"]["retained_pass"] is None
    assert telemetry["overall"]["resource_gate"] == "pending_retained_candidate"
    assert telemetry["gate_contract"]["full_side_exact_factor_count"] == 0
    assert telemetry["gate_contract"]["global_direct_factor_count"] == 0
    assert telemetry["gate_contract"]["nested_ksp_count"] == 0


def test_task039_h5_critical_checkpoint_does_not_stop_before_absolute_hard_stop(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        launcher,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 256 * 1024**3},
    )
    monkeypatch.setattr(
        launcher,
        "cgroup_snapshot",
        lambda _scope: {"memory_limit_bytes": None},
    )
    specification = load_and_resolve(TASK039_H5_DIRECT)
    result, terminated = _run_h5_worker(
        tmp_path,
        specification,
        _authority(memory=195 * 1024**3),
    )

    assert terminated == []
    assert result["exit_status"] == 0
    authority = result["resource_authority"]
    assert authority["critical_checkpoint_crossed"] is True
    assert authority["absolute_terminate_memory_bytes"] == 224_000_000_000


@pytest.mark.parametrize(
    ("memory", "swap", "classification"),
    (
        (224_000_000_000, 0, "memory_terminate"),
        (224_000_000_000, 1, "swap_policy_violation"),
    ),
)
def test_task039_h5_absolute_hard_stop_and_swap_precedence(
    monkeypatch, tmp_path, memory, swap, classification
):
    monkeypatch.setattr(
        launcher,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 256 * 1024**3},
    )
    monkeypatch.setattr(
        launcher,
        "cgroup_snapshot",
        lambda _scope: {"memory_limit_bytes": None},
    )
    specification = load_and_resolve(TASK039_H5_DIRECT)
    result, terminated = _run_h5_worker(
        tmp_path,
        specification,
        _authority(memory=memory, swap=swap),
    )

    assert result["result_classification"] == classification
    assert terminated


def test_task039_h5_absolute_policy_rejects_slow_poll_before_worker_launch(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        launcher,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 256 * 1024**3},
    )
    monkeypatch.setattr(
        launcher,
        "cgroup_snapshot",
        lambda _scope: {"memory_limit_bytes": None},
    )
    specification = load_and_resolve(TASK039_H5_DIRECT)
    plan = SimpleNamespace(
        argv=("/opt/fake-worker",),
        contract_probe=False,
        task039_trace_audit=False,
    )
    run_directory = tmp_path / "slow-poll"
    run_directory.mkdir()

    def fail_popen(*_args, **_kwargs):
        pytest.fail("worker must not launch with poll_interval > 0.25")

    with pytest.raises(InputError, match="poll_interval"):
        launcher._run_worker(
            plan,
            specification,
            run_directory,
            popen_factory=fail_popen,
            sample_factory=lambda _pid: _authority(),
            terminate_factory=lambda _process: {"requested": True},
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: None,
            poll_interval=0.3,
        )


def test_smaps_rollup_requires_pss_rss_and_private_fields(tmp_path):
    path = tmp_path / "smaps_rollup"
    path.write_text(
        "\n".join(
            (
                "Rss: 100 kB",
                "Pss: 60 kB",
                "Private_Clean: 10 kB",
                "Private_Dirty: 20 kB",
                "Private_Hugetlb: 3 kB",
            )
        ),
        encoding="utf-8",
    )
    row = _read_smaps_rollup(path)
    assert row is not None
    assert row["pss_mb"] == pytest.approx(60 / 1024)
    assert row["uss_mb"] == pytest.approx(33 / 1024)
    path.write_text("Rss: 100 kB\nPss: 60 kB\nPrivate_Clean: 10 kB\n")
    assert _read_smaps_rollup(path) is None


def test_process_tree_smaps_aggregation_requires_all_pids(monkeypatch):
    rows = {
        11: {"pss_mb": 2.0, "uss_mb": 1.0},
        12: {"pss_mb": 3.0, "uss_mb": 1.5},
    }
    monkeypatch.setattr(
        "benchmarks.task034_wsl_resources._read_smaps_rollup",
        lambda path: rows.get(int(path.parts[2])),
    )
    sample = process_tree_smaps_sample((11, 12))
    assert sample["complete"] is True
    assert sample["pss_bytes"] == int(5 * 1024**2)
    assert sample["uss_bytes"] == int(2.5 * 1024**2)
    incomplete = process_tree_smaps_sample((11, 13))
    assert incomplete["complete"] is False
    assert incomplete["pss_bytes"] is None
    assert incomplete["uss_bytes"] is None


def test_task039_default_sampler_requests_smaps_without_changing_fake_sampler(
    monkeypatch, tmp_path
):
    specification = _task039_spec(tmp_path)
    captured = {}

    def fake_worker(_plan, _specification, _run_directory, **kwargs):
        captured.update(kwargs)
        return {
            "exit_status": 0,
            "result_classification": "contract_probe_pass",
            "termination": None,
            "resource_authority": {"status": "not_sampled"},
        }

    monkeypatch.setattr(launcher, "_run_worker", fake_worker)
    launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=lambda *_args, **_kwargs: _FakeProcess(0),
    )
    sampler = captured["sample_factory"]
    assert sampler.keywords == {"include_smaps": True}


def test_task039_launcher_tracks_independent_smaps_peaks(monkeypatch, tmp_path):
    specification = _task039_spec(tmp_path)
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution=None: {
            "configured_warning_memory_gib": 180.0,
            "effective_terminate_memory_gib": 220.0,
        },
    )
    samples = iter(
        (
            _authority_with_smaps(pss=10 * 1024**2, uss=30 * 1024**2),
            _authority_with_smaps(pss=20 * 1024**2, uss=25 * 1024**2),
            _authority_with_smaps(complete=False),
        )
    )
    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=lambda *_args, **_kwargs: _SequenceProcess(2),
        sample_factory=lambda _pid: next(samples),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    authority = result["resource_authority"]
    assert authority["peak_pss_mb"] == pytest.approx(20.0)
    assert authority["peak_uss_mb"] == pytest.approx(30.0)
    assert authority["smaps_attempted_sample_count"] == 3
    assert authority["smaps_complete_sample_count"] == 2
    assert authority["telemetry_status"] == "measured"
    assert "different samples" in authority["peak_semantics"]


def test_task039_v4_h4_aligns_progress_status_and_order(tmp_path):
    specification = _task039_v4_h4_spec(tmp_path)

    def popen(argv, **_kwargs):
        output_directory = Path(argv[argv.index("--expected-output-directory") + 1])
        progress = output_directory / "numerical_output" / "progress_3d.jsonl"
        progress.parent.mkdir(parents=True, exist_ok=True)
        progress.write_text(
            "".join(
                json.dumps(
                    {"stage": stage, "status": status, "elapsed_seconds": elapsed}
                )
                + "\n"
                for stage, status, elapsed in (
                    ("factor_destroy", "begin", 1.0),
                    ("factor_destroy", "end", 2.0),
                )
            ),
            encoding="utf-8",
        )
        return _FakeProcess(0)

    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        timestamp="20260812T000000.000000Z",
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=popen,
        sample_factory=lambda _pid: _authority(),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    telemetry = result["resource_authority"]["v4_h4_formal_telemetry"]
    assert telemetry["raw_marker_path"].endswith("numerical_output/progress_3d.jsonl")
    assert telemetry["progress_path"] == telemetry["raw_marker_path"]
    assert telemetry["memory_stages_path"].endswith("memory_stages.jsonl")
    assert telemetry["aligned_stage_count"] == 2
    budget = result["resource_authority"]["task039_memory_budget"]
    assert budget["configured_warning_memory_gib"] == 170.0
    assert budget["configured_critical_memory_gib"] == 195.0
    assert result["resource_authority"]["critical_checkpoint_crossed"] is False
    assert (
        result["resource_authority"]["absolute_terminate_memory_bytes"]
        == 224_000_000_000
    )
    assert result["resource_authority"]["require_zero_swap"] is True
    rows = [
        json.loads(line)
        for line in Path(telemetry["memory_stages_path"]).read_text().splitlines()
    ]
    assert [(row["stage"], row["status"], row["stage_index"]) for row in rows] == [
        ("factor_destroy", "begin", 0),
        ("factor_destroy", "end", 1),
    ]


def test_task039_v5_setup_only_stream_aligns_all_markers(tmp_path):
    specification = replace(
        load_and_resolve(TASK039_V4_H4_ITERATIVE),
        expected_output_parent=tmp_path / "results",
    )
    run_directory = tmp_path / "v5-setup"
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
    )
    plan = replace(plan, method="task039_v5_h4_exact_side_setup_only")
    markers = (
        "bottom_F_ready",
        "bottom_factor_setup_begin",
        "bottom_factor_ready",
        "bottom_woodbury_ready",
        "bottom_construction_cleanup",
        "top_F_ready",
        "top_factor_setup_begin",
        "top_factor_ready",
        "top_woodbury_ready",
        "top_construction_cleanup",
        "both_side_actions_ready",
        "modal_schur_build_begin",
        "modal_schur_ready",
        "outer_ksp_setup_ready",
        "all_setup_objects_cleanup",
    )

    def popen(_argv, **_kwargs):
        marker_path = run_directory / "numerical_output/memory_stage_markers.raw.jsonl"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(
            "".join(
                json.dumps({"stage": marker, "status": "end", "elapsed_seconds": index})
                + "\n"
                for index, marker in enumerate(markers)
            ),
            encoding="utf-8",
        )
        return _FakeProcess(0)

    result = _run_worker(
        plan,
        specification,
        run_directory,
        popen_factory=popen,
        sample_factory=lambda _pid: _authority(),
        terminate_factory=lambda _process: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    telemetry = result["resource_authority"]["v5_h4_setup_only_telemetry"]
    rows = [
        json.loads(line)
        for line in Path(telemetry["memory_stages_path"]).read_text().splitlines()
    ]
    assert telemetry["aligned_stage_count"] == len(markers)
    assert [row["stage"] for row in rows] == list(markers)
    assert rows[-1]["stage"] == "all_setup_objects_cleanup"
    assert rows[-1]["stage_index"] == len(markers) - 1


def test_task039_pss_uss_do_not_trigger_memory_termination(monkeypatch, tmp_path):
    specification = _task039_spec(tmp_path)
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution=None: {
            "configured_warning_memory_gib": 180.0,
            "effective_terminate_memory_gib": 1.0,
        },
    )
    terminated = []
    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=lambda *_args, **_kwargs: _SequenceProcess(),
        sample_factory=lambda _pid: _authority_with_smaps(
            rss=1024,
            pss=10 * 1024**3,
            uss=9 * 1024**3,
        ),
        terminate_factory=lambda process: terminated.append(process),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    assert result["exit_status"] == 0
    assert terminated == []
    assert result["resource_authority"]["peak_pss_mb"] == pytest.approx(10 * 1024)


def test_task039_zero_complete_smaps_is_incomplete_not_zero(monkeypatch, tmp_path):
    specification = _task039_spec(tmp_path)
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution=None: {
            "configured_warning_memory_gib": 180.0,
            "effective_terminate_memory_gib": 220.0,
        },
    )
    result = launch_specification(
        specification,
        source_sha=SOURCE_SHA,
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=lambda *_args, **_kwargs: _FakeProcess(0),
        sample_factory=lambda _pid: _authority_with_smaps(complete=False),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    authority = result["resource_authority"]
    assert authority["peak_pss_mb"] is None
    assert authority["peak_uss_mb"] is None
    assert authority["smaps_attempted_sample_count"] == 1
    assert authority["smaps_complete_sample_count"] == 0
    assert authority["telemetry_status"] == "incomplete"


def test_ordinary_task38_resource_output_has_no_smaps_fields(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    result, _calls, _terminated = _fake_launch(
        specification,
        tmp_path,
        process=_FakeProcess(0),
        sample=_authority(),
    )
    authority = result["resource_authority"]
    assert "peak_pss_mb" not in authority
    assert "telemetry_status" not in authority


def test_worker_checks_raw_copy_execution_and_input_path(tmp_path):
    specification = _input(tmp_path, results_root=str(tmp_path / "results"))
    result, _calls, _terminated = _fake_launch(
        specification,
        tmp_path,
        process=_FakeProcess(0),
        sample=_authority(),
        timestamp="20260812T000002.000000Z",
    )
    run_directory = Path(result["run_directory"])
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        adapter_identity=CONTRACT_PROBE_ADAPTER,
        contract_probe=True,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
    )
    kwargs = {
        "resolved_config": plan.expected_resolved_config,
        "manifest": plan.expected_manifest,
        "expected_input_sha256": specification.input_sha256,
        "expected_physical_model_sha256": specification.physical_model_sha256,
        "expected_source_sha": SOURCE_SHA,
        "expected_mpi_size": specification.execution["mpi_size"],
        "expected_method": specification.method["kind"],
        "expected_adapter": CONTRACT_PROBE_ADAPTER,
        "expected_output_directory": run_directory,
        "expected_resolved_config_sha256": hashlib.sha256(
            resolved_config_bytes(specification)
        ).hexdigest(),
        "actual_mpi_size": specification.execution["mpi_size"],
        "contract_probe": True,
    }
    assert validate_worker_contract(**kwargs) == []
    (run_directory / "input_original.dat").write_bytes(b"changed")
    assert any(
        "input_original.dat SHA mismatch" in error
        for error in validate_worker_contract(**kwargs)
    )

    resolved = json.loads((run_directory / "resolved_config.json").read_bytes())
    resolved["execution"]["mpi_size"] = 1
    resolved_bytes = canonical_json_bytes(resolved) + b"\n"
    (run_directory / "resolved_config.json").write_bytes(resolved_bytes)
    kwargs["expected_resolved_config_sha256"] = hashlib.sha256(
        resolved_bytes
    ).hexdigest()
    errors = validate_worker_contract(**kwargs)
    assert any("resolved config MPI size mismatch" in error for error in errors)


@pytest.mark.parametrize(
    ("updates", "expected", "memory", "swap"),
    (
        ({}, "worker_nonzero", 1024, 0),
        ({"timeout_seconds": 1}, "timeout", 1024, 0),
        (
            {"warning_memory_gib": 0.001, "terminate_memory_gib": 0.002},
            "memory_terminate",
            3 * 1024**3,
            0,
        ),
        ({}, "swap_policy_violation", 1024, 1),
    ),
)
def test_launcher_classifies_exit_timeout_memory_and_swap(
    tmp_path, updates, expected, memory, swap
):
    specification = _input(
        tmp_path,
        results_root=str(tmp_path / expected),
        **updates,
    )
    process = _FakeProcess(7 if expected == "worker_nonzero" else None)
    clock = iter((0.0, 2.0, 4.0))
    result, _calls, terminated = _fake_launch(
        specification,
        tmp_path,
        process=process,
        sample=_authority(memory=memory, swap=swap),
        timestamp=f"20260812T00000{len(expected)}.000000Z",
        monotonic=lambda: next(clock),
    )
    assert result["result_classification"] == expected
    if expected == "worker_nonzero":
        assert not terminated
    else:
        assert terminated
