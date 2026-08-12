"""T3b launcher, provenance, worker-copy, and resource contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.run_case import main as run_case_main
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.execution_plan import CONTRACT_PROBE_ADAPTER, build_execution_plan
from src.io.resolved_config import canonical_json_bytes, resolved_config_bytes
from src.runners.task038_input_worker import validate_worker_contract
from src.runners.task038_launcher import _run_worker, _swap_bytes, launch_specification


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/full3d_direct_example.dat"
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
