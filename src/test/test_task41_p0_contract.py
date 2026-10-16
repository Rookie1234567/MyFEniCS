from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from src.runners.task40_v10_campaign import _utc_ns
from src.runners.workflow_timebase import clock_sample
from src.runners.task41_p0_contract import (
    TASK41_A1_COMPARISON_BINDING_RELATIVE,
    TASK41_A1_COMPARISON_BINDING_SCHEMA,
    TASK41_A2_CONTROLLER_RELATIVE,
    TASK41_A2_INPUT_RELATIVE,
    TASK41_A2_RUN_ID,
    TASK41_A2_WINDOW_RELATIVE,
    TASK41_BRANCH,
    TASK41_CLOSEOUT_SECONDS,
    TASK41_HOST_RESERVE_BYTES,
    TASK41_INPUT_RELATIVE,
    TASK41_MODEL_ID,
    TASK41_NUMERICAL_SECONDS,
    TASK41_P0_CONTRACT_SCHEMA,
    TASK41_P0_WINDOW_SCHEMA,
    TASK41_RUN_ID,
    TASK41_TASK_MEMORY_MAX_BYTES,
    TASK41_TOTAL_SECONDS,
    TASK41_WINDOW_RELATIVE,
    Task41ContractError,
    contract_relative_path,
    load_task41_p0_fixed_window,
    prepare_task41_p0,
    require_task41_p0_contract,
)


def _utc_z(nanoseconds: int) -> str:
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + f".{fraction:09d}Z"


def _write_contract(root: Path, case_id: str = "A1") -> tuple[Path, dict]:
    import src.runners.task41_p0_contract as contract_module

    case_spec = contract_module._task41_case(case_id)
    input_path = root / case_spec["input_relative"]
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_bytes(f"fixed Task41 {case_id} contract test DAT\n".encode())
    runtime = root / "qualified-runtime"
    (runtime / "bin").mkdir(parents=True)
    python_path = runtime / "bin/python"
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)
    abi_receipt = root / "abi_receipt.json"
    jit_cache = root / "jit-cache"
    jit_cache.mkdir()
    abi_receipt.write_text('{"abi":"test"}\n', encoding="utf-8")
    controller_root = root / case_spec["controller_relative"]
    controller_root.mkdir(parents=True, exist_ok=True)
    current = clock_sample(include_boot_id=True)
    t0_ns = current["utc_ns"]
    entry_source = "b" * 40
    accounting = controller_root / "campaign_accounting_v10.jsonl"
    window_payload = {
        "schema": TASK41_P0_WINDOW_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "source_sha": entry_source,
        "t0_utc": _utc_z(t0_ns),
        "numerical_deadline_utc": _utc_z(
            t0_ns + int(TASK41_NUMERICAL_SECONDS * 1_000_000_000)
        ),
        "deadline_utc": _utc_z(t0_ns + int(TASK41_TOTAL_SECONDS * 1_000_000_000)),
        "total_seconds": TASK41_TOTAL_SECONDS,
        "numerical_seconds": TASK41_NUMERICAL_SECONDS,
        "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        "anchor": current,
        "accounting_path": str(accounting.resolve()),
    }
    window_path = root / case_spec["window_relative"]
    window_path.parent.mkdir(parents=True, exist_ok=True)
    window_path.write_text(
        json.dumps(window_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    contract = {
        "schema": TASK41_P0_CONTRACT_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "branch": TASK41_BRANCH,
        "source": {"sha": "c" * 40},
        "case": {
            "input_path": str(case_spec["input_relative"]),
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "model_id": TASK41_MODEL_ID,
            "run_id": case_spec["run_id"],
            "physical_model_sha256": "d" * 64,
            "resolved_config_sha256": "e" * 64,
            "method": case_spec["method"],
            "mpi_size": 1,
        },
        "runtime": {
            "profile": "native_linux",
            "runtime_prefix": str(runtime),
            "abi_receipt_path": str(abi_receipt),
            "abi_receipt_sha256": hashlib.sha256(abi_receipt.read_bytes()).hexdigest(),
            "jit_cache": str(jit_cache),
            "mpi_ranks": 1,
            "math_threads": 1,
        },
        "window": {
            "path": str(case_spec["window_relative"]),
            "sha256": window_sha,
            "entry_source_sha": entry_source,
        },
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "time": {
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        },
        "evidence": {
            "service_directory": str(
                case_spec["service_relative"] / f"service_source_{'c' * 40}"
            ),
        },
    }
    contract_path = root / contract_relative_path("c" * 40, case_id)
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return contract_path, contract


def test_task41_window_keeps_original_t0_and_entry_source_for_new_attempt(tmp_path):
    contract_path, contract = _write_contract(tmp_path)
    loaded, digest = require_task41_p0_contract(
        contract_path, current_root=tmp_path
    )
    window = load_task41_p0_fixed_window(
        loaded, current_root=tmp_path, require_current_boot=False
    )
    assert digest == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert contract["source"]["sha"] != contract["window"]["entry_source_sha"]
    assert window.t0_utc_ns == _utc_ns(window.payload["t0_utc"])
    assert window.total_seconds == TASK41_TOTAL_SECONDS
    assert window.cutoff_seconds == TASK41_NUMERICAL_SECONDS
    assert window.closeout_seconds == TASK41_CLOSEOUT_SECONDS
    assert window.accounting_path == Path(window.payload["accounting_path"])


def test_task41_window_hash_change_fails_closed(tmp_path):
    contract_path, contract = _write_contract(tmp_path)
    window_path = tmp_path / contract["window"]["path"]
    payload = json.loads(window_path.read_text(encoding="utf-8"))
    payload["closeout_seconds"] = TASK41_CLOSEOUT_SECONDS - 1
    window_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded, _ = require_task41_p0_contract(contract_path, current_root=tmp_path)
    with pytest.raises(ValueError, match="window hash changed"):
        load_task41_p0_fixed_window(
            loaded, current_root=tmp_path, require_current_boot=False
        )


def test_task41_prepare_keeps_first_t0_after_validation_failure_and_source_change(
    tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as contract_module

    repo_root = Path(__file__).resolve().parents[2]
    input_path = tmp_path / TASK41_INPUT_RELATIVE
    input_path.parent.mkdir(parents=True)
    original_input = repo_root.joinpath(TASK41_INPUT_RELATIVE).read_bytes()
    input_path.write_bytes(b"invalid DAT\n")
    runtime = tmp_path / "native-runtime"
    python_path = runtime / "bin/python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)
    abi_receipt = tmp_path / "native-abi.json"
    abi_receipt.write_text(
        json.dumps(
            {
                "status": "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION",
                "runtime_profile": "native_linux",
                "prefix": str(runtime.resolve()),
                "PETSc": {"scalar_dtype": "complex128", "int_dtype": "int32"},
                "MPI": {"size": 1, "rank": 0},
            }
        ),
        encoding="utf-8",
    )
    jit_cache = tmp_path / "jit"
    jit_cache.mkdir()
    git_state = {"sha": "a" * 40}

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return git_state["sha"]
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(contract_module, "_git", fake_git)
    prepare_args = {
        "runtime_prefix": runtime,
        "abi_receipt": abi_receipt,
        "jit_cache": jit_cache,
        "current_root": tmp_path,
    }
    with pytest.raises(Task41ContractError, match="could not be resolved"):
        prepare_task41_p0(**prepare_args)

    window_path = tmp_path / TASK41_WINDOW_RELATIVE
    first_window_bytes = window_path.read_bytes()
    first_window_sha = hashlib.sha256(first_window_bytes).hexdigest()
    first_window_payload = json.loads(first_window_bytes)
    assert first_window_payload["source_sha"] == git_state["sha"]

    input_path.write_bytes(original_input)
    git_state["sha"] = "b" * 40
    prepared_b = prepare_task41_p0(**prepare_args)
    assert window_path.read_bytes() == first_window_bytes
    assert prepared_b["window_sha256"] == first_window_sha
    assert prepared_b["window_entry_source_sha"] == "a" * 40
    assert prepared_b["contract_source_sha"] == "b" * 40
    contract_b = json.loads((tmp_path / prepared_b["contract_path"]).read_text())
    assert contract_b["window"]["entry_source_sha"] == "a" * 40

    git_state["sha"] = "c" * 40
    prepared_c = prepare_task41_p0(**prepare_args)
    assert window_path.read_bytes() == first_window_bytes
    assert prepared_c["contract_path"] != prepared_b["contract_path"]
    assert prepared_c["window_sha256"] == first_window_sha
    assert prepared_c["contract_source_sha"] == "c" * 40


def test_task41_launcher_and_service_pass_real_window_resources_and_checker_authority(
    tmp_path, monkeypatch, request
):
    import benchmarks.subreaper_watchdog as watchdog
    import benchmarks.task034_wsl_resources as resources
    import scripts.task40_v20_service_workflow as service
    import src.runners.task038_launcher as launcher
    import src.runners.task41_p0_contract as contract_module
    from src.geometry.task41_phi90_profile import task41_payload_errors
    from src.io.execution_plan import resolved_config_bytes
    from src.io.input_validation import load_and_resolve

    repo_root = Path(__file__).resolve().parents[2]
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    assert subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == TASK41_BRANCH
    fixture_id = f"test-callchain-{os.getpid()}-{uuid4().hex}"
    fixture_relative = (
        Path("benchmarks/artifacts/task41extra_phi90_p50x50_g17x20")
        / "test_fixtures"
        / fixture_id
    )
    fixture_root = repo_root / fixture_relative
    request.addfinalizer(lambda: shutil.rmtree(fixture_root, ignore_errors=True))
    controller_relative = fixture_relative / "controller"
    window_relative = controller_relative / "execution_window.json"
    monkeypatch.setattr(contract_module, "TASK41_CONTROLLER_RELATIVE", controller_relative)
    monkeypatch.setattr(contract_module, "TASK41_WINDOW_RELATIVE", window_relative)
    monkeypatch.setattr(
        contract_module, "TASK41_A1_SERVICE_RELATIVE", fixture_relative / "service_base"
    )
    monkeypatch.setattr(
        contract_module,
        "_git",
        lambda _root, *args: (
            source_sha
            if args == ("rev-parse", "HEAD")
            else TASK41_BRANCH
            if args == ("branch", "--show-current")
            else ""
            if args == ("status", "--porcelain", "--untracked-files=normal")
            else (_ for _ in ()).throw(AssertionError(f"unexpected git query: {args}"))
        ),
    )

    input_path = repo_root / TASK41_INPUT_RELATIVE
    specification = load_and_resolve(input_path)
    payload_errors = task41_payload_errors(specification.as_jsonable())
    assert not payload_errors
    runtime_prefix = Path(sys.prefix).resolve()
    assert (runtime_prefix / "bin/python").resolve() == Path(sys.executable).resolve()
    abi_receipt = fixture_root / "abi_receipt.json"
    abi_receipt.parent.mkdir(parents=True)
    abi_receipt.write_text('{"fixture":"qualified native receipt shape"}\n', encoding="utf-8")
    jit_cache = tmp_path / "jit-cache"
    jit_cache.mkdir()
    accounting_path = repo_root / controller_relative / "campaign_accounting_v10.jsonl"
    anchor = clock_sample(include_boot_id=True)
    t0_ns = int(anchor["utc_ns"])
    window_payload = {
        "schema": TASK41_P0_WINDOW_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "source_sha": source_sha,
        "t0_utc": _utc_z(t0_ns),
        "numerical_deadline_utc": _utc_z(
            t0_ns + int(TASK41_NUMERICAL_SECONDS * 1_000_000_000)
        ),
        "deadline_utc": _utc_z(t0_ns + int(TASK41_TOTAL_SECONDS * 1_000_000_000)),
        "total_seconds": TASK41_TOTAL_SECONDS,
        "numerical_seconds": TASK41_NUMERICAL_SECONDS,
        "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        "anchor": anchor,
        "accounting_path": str(accounting_path.resolve()),
    }
    window_path = repo_root / window_relative
    contract_root = repo_root / controller_relative
    contract_root.mkdir(parents=True, exist_ok=True)
    window_path.write_text(
        json.dumps(window_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    contract = {
        "schema": TASK41_P0_CONTRACT_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "branch": TASK41_BRANCH,
        "source": {"sha": source_sha},
        "case": {
            "input_path": str(TASK41_INPUT_RELATIVE),
            "input_sha256": specification.input_sha256,
            "model_id": specification.identity["model_id"],
            "run_id": specification.identity["run_id"],
            "physical_model_sha256": specification.physical_model_sha256,
            "resolved_config_sha256": hashlib.sha256(
                resolved_config_bytes(specification)
            ).hexdigest(),
            "method": specification.method["kind"],
            "mpi_size": specification.execution["mpi_size"],
        },
        "runtime": {
            "profile": "native_linux",
            "runtime_prefix": str(runtime_prefix),
            "abi_receipt_path": str(abi_receipt.resolve()),
            "abi_receipt_sha256": hashlib.sha256(abi_receipt.read_bytes()).hexdigest(),
            "jit_cache": str(jit_cache.resolve()),
            "mpi_ranks": 1,
            "math_threads": 1,
        },
        "window": {
            "path": str(window_relative),
            "sha256": window_sha,
            "entry_source_sha": source_sha,
        },
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "time": {
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        },
        "evidence": {
            "service_directory": str(
                fixture_relative / "service_base"
                / f"service_source_{source_sha}"
            ),
        },
    }
    contract_path = repo_root / contract_module.contract_relative_path(source_sha)
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    for key, value in {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path.resolve()),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_EXECUTION_WINDOW_PATH": str(window_path.resolve()),
        "TASK41_P0_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK41_P0_TASK_MEMORY_MAX_BYTES": str(TASK41_TASK_MEMORY_MAX_BYTES),
        "TASK41_P0_HOST_RESERVE_BYTES": str(TASK41_HOST_RESERVE_BYTES),
        "TASK41_P0_MEMORY_SWAP_MAX_BYTES": "0",
        "TASK41_P0_EXPECTED_SOURCE_SHA": source_sha,
    }.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda _root, expected: {
            "source_sha": expected,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    monkeypatch.setattr(launcher, "current_cgroup_path", lambda: "/test/myfenics-case-fixture.service")
    monkeypatch.setattr(launcher, "_is_v28_user_service_cgroup", lambda _path: True)
    captured_calls: list[dict[str, Any]] = []
    window = contract_module.load_task41_p0_fixed_window(
        contract, current_root=repo_root, require_current_boot=True
    )

    def capture_supervise(command, watchdog_directory, **kwargs):
        call = {"command": list(command), "watchdog_directory": Path(watchdog_directory), **kwargs}
        captured_calls.append(call)
        if kwargs.get("campaign_phase", "numeric") == "closeout":
            validated = watchdog._validate_campaign_closeout_authorization(
                command=list(command),
                campaign=window,
                authorization=kwargs["campaign_phase_authorization"],
                worker_environment=kwargs["worker_environment"],
            )
            call["validated_authorization"] = validated
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text(
                json.dumps(
                    {"checker_passed": True, "full_pass": True, "official_result": True}
                )
                + "\n",
                encoding="utf-8",
            )
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "memory_scope": "fixture-only synthetic provider",
            "launch_envelope": {"fixture": True},
        }

    monkeypatch.setattr(watchdog, "supervise", capture_supervise)
    timestamp = f"task41-fixture-{uuid4().hex}"
    launch_result = launcher.launch_specification(
        specification,
        source_sha=source_sha,
        timestamp=timestamp,
        task41_p0_execution_contract=contract_path,
        task41_p0_contract_sha256=contract_sha,
    )
    numeric_call = next(call for call in captured_calls if "campaign_phase" not in call)
    numeric_environment = numeric_call["worker_environment"]
    assert numeric_call["campaign_window_path"] == window.path
    assert numeric_call["campaign_window_sha256"] == window.sha256
    assert numeric_call["campaign_accounting_path"] == window.accounting_path
    assert numeric_call["tree_cap_bytes"] == TASK41_TASK_MEMORY_MAX_BYTES
    assert numeric_call["host_reserve_bytes"] == TASK41_HOST_RESERVE_BYTES
    assert numeric_call["task_cgroup_reserve_bytes"] == 0
    assert numeric_call["require_job_cgroup_zero_swap"] is True
    assert numeric_call["require_cgroup_memory_details"] is True
    assert numeric_call["memory_policy"] == watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY
    assert numeric_call["pss_sampling_policy"] == "disabled_by_profile"
    assert numeric_environment["TASK41_P0_CONTRACT_SHA256"] == contract_sha
    assert numeric_environment["TASK41_P0_EXECUTION_WINDOW_SHA256"] == window_sha
    assert "PHYSICAL_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS" not in numeric_environment
    assert all(
        numeric_environment[name] == "1"
        for name in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"
        )
    )
    assert launch_result["exit_status"] == 0
    assert Path(launch_result["manifest"]).is_file()
    request.addfinalizer(
        lambda: shutil.rmtree(Path(launch_result["run_directory"]), ignore_errors=True)
    )

    monkeypatch.setattr(
        service,
        "_activation_environment",
        lambda *_args, **_kwargs: (
            {
                **os.environ,
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
                "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
                "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
                "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": contract["runtime"]["abi_receipt_sha256"],
                "TASK40_V29_STRICT_FACTOR_ONLY": "1",
            },
            "fixture native activation",
            0,
            "",
        ),
    )
    monkeypatch.setattr(
        service,
        "_abi_preflight",
        lambda *_args, **_kwargs: (
            ["fixture preflight"], 0,
            json.dumps({"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1}),
            "",
        ),
    )
    monkeypatch.setattr(
        resources,
        "cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_limit_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "swap_current_bytes": 0,
            "memory_current_bytes": 4096,
        },
    )

    service_output_root = Path(contract["evidence"]["service_directory"])
    service_output_root = (repo_root / service_output_root).resolve()

    def fake_check_output(command, **_kwargs):
        if command[:3] == ["git", "branch", "--show-current"]:
            return f"{TASK41_BRANCH}\n"
        if command[:2] == ["git", "status"]:
            return ""
        raise AssertionError(f"unexpected check_output command: {command}")

    run_case_environment: dict[str, str] = {}

    def fake_subprocess_run(command, *args, **kwargs):
        if command[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(stdout=f"{source_sha}\n", stderr="", returncode=0)
        if command[:3] == ["git", "branch", "--show-current"]:
            return SimpleNamespace(stdout=f"{TASK41_BRANCH}\n", stderr="", returncode=0)
        if command[:2] == ["git", "status"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if len(command) >= 2 and command[1] == "scripts/run_case.py":
            run_case_environment.update(kwargs.get("env", {}))
            run_root = repo_root / "results" / TASK41_MODEL_ID / fixture_id / "synthetic_launcher_result"
            request.addfinalizer(lambda: shutil.rmtree(run_root, ignore_errors=True))
            numerical_output = run_root / "numerical_output"
            numerical_output.mkdir(parents=True)
            summary_path = run_root / "run_summary.json"
            manifest_path = run_root / "run_manifest.json"
            numerical_summary_path = numerical_output / "run_summary.json"
            summary_path.write_text("{}\n", encoding="utf-8")
            manifest_path.write_text(
                json.dumps({"numerical_output_directory": str(numerical_output)}) + "\n",
                encoding="utf-8",
            )
            numerical_summary_path.write_text("{}\n", encoding="utf-8")
            kwargs["stdout"].write(
                json.dumps(
                    {
                        "run_directory": str(run_root),
                        "manifest": str(manifest_path),
                        "summary": str(summary_path),
                        "result_classification": "worker_exit0",
                    }
                )
                + "\n"
            )
            return SimpleNamespace(returncode=0)
        raise AssertionError(f"unexpected subprocess command: {command}")

    monkeypatch.setattr(service.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(service.subprocess, "check_output", fake_check_output)
    return_code = service.run_service(
        unit="task41-callchain-fixture",
        runtime_prefix=runtime_prefix,
        abi_receipt=abi_receipt,
        jit_cache=jit_cache,
        case_args=[
            str(input_path),
            "--task41-p0-execution-contract",
            str(contract_path),
        ],
        repo_root=repo_root,
    )
    assert return_code == 0
    assert "TASK40_V29_STRICT_FACTOR_ONLY" not in run_case_environment
    assert run_case_environment["TASK41_P0_STRICT_EXECUTION"] == "1"
    assert run_case_environment["TASK41_P0_CONTRACT_PATH"] == str(contract_path.resolve())
    assert run_case_environment["TASK41_P0_CONTRACT_SHA256"] == contract_sha
    assert run_case_environment["TASK41_P0_EXECUTION_WINDOW_PATH"] == str(window.path)
    assert run_case_environment["TASK41_P0_EXECUTION_WINDOW_SHA256"] == window_sha
    closeout_call = next(call for call in captured_calls if call.get("campaign_phase") == "closeout")
    assert closeout_call["wall_seconds"] == TASK41_CLOSEOUT_SECONDS
    assert closeout_call["campaign_window_path"] == window.path
    assert closeout_call["campaign_window_sha256"] == window_sha
    assert closeout_call["tree_cap_bytes"] == TASK41_TASK_MEMORY_MAX_BYTES
    assert closeout_call["host_reserve_bytes"] == TASK41_HOST_RESERVE_BYTES
    assert closeout_call["campaign_phase_authorization"]["source_sha"] == source_sha
    assert closeout_call["validated_authorization"] == closeout_call["campaign_phase_authorization"]
    assert closeout_call["command"][1:3] == ["-m", "src.runners.task41_p0_checker"]
    receipt = json.loads(
        (service_output_root / "task41_p0_service_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["required_checker_status"] == "passed"
    assert receipt["required_checker_command"] == closeout_call["command"]
    assert receipt["required_checker_authorization"] == closeout_call["validated_authorization"]


def _record_file(root: Path, path: Path, content: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": str(path.relative_to(root)),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _write_a1_comparison_binding_fixture(root: Path) -> tuple[Path, dict]:
    source_sha = "a" * 40
    physical_sha = "d" * 64
    a1_input = root / TASK41_INPUT_RELATIVE
    a1_input.parent.mkdir(parents=True)
    a1_input.write_bytes(b"registered A1 input fixture\n")
    input_sha = hashlib.sha256(a1_input.read_bytes()).hexdigest()
    run_root = (
        root / "results" / TASK41_MODEL_ID
        / f"{TASK41_RUN_ID}__full3d_direct__mpi1__Mna" / "20261016T123737.790458Z"
    )
    resolved_content = b'{"fixture":"resolved A1 configuration"}\n'
    resolved_sha = hashlib.sha256(resolved_content).hexdigest()
    manifest = {
        "model_id": TASK41_MODEL_ID,
        "run_id": TASK41_RUN_ID,
        "method": "full3d_direct",
        "mpi_size": 1,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
    }
    manifest_path = run_root / "run_manifest.json"
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode() + b"\n"
    numerical_path = run_root / "numerical_output" / "run_summary.json"
    numerical_bytes = json.dumps(
        {"case_status": "completed", "official_result": True}, sort_keys=True
    ).encode() + b"\n"
    resolved_path = run_root / "resolved_config.json"
    run_manifest = _record_file(root, manifest_path, manifest_bytes)
    numerical_summary = _record_file(root, numerical_path, numerical_bytes)
    resolved_config = _record_file(root, resolved_path, resolved_content)
    checker_dir = (
        root / "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a1"
        / f"service_source_{source_sha}"
    )
    checker_path = checker_dir / "task41_p0_checker_result.json"
    checker_payload = {
        "schema": "task41.p0.direct_checker.v1",
        "status": "PASS",
        "checker_passed": True,
        "full_pass": True,
        "official_result": True,
        "run_id": TASK41_RUN_ID,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
    }
    checker_record = _record_file(
        root, checker_path, json.dumps(checker_payload, sort_keys=True).encode() + b"\n"
    )
    checker_record["schema"] = "task41.p0.direct_checker.v1"
    artifact_names = (
        "full_solution", "native_a6_residual", "airbox_fields",
        "full3d_samples_archive", "full3d_samples_metadata", "modal_amplitudes",
        "port_power_metrics", "volume_absorption", "diffraction_orders",
        "mesh_h5", "mesh_xdmf",
    )
    artifacts = {}
    for name in artifact_names:
        extension = ".npz" if name in {
            "full_solution", "airbox_fields", "full3d_samples_archive", "modal_amplitudes"
        } else ".json"
        artifact_path = run_root / "numerical_output" / f"{name}{extension}"
        record = _record_file(root, artifact_path, f"{name} fixture bytes".encode())
        if name == "full_solution":
            record.update(array_key="recovered_field", rank=0)
        artifacts[name] = record
    binding = {
        "schema": TASK41_A1_COMPARISON_BINDING_SCHEMA,
        "status": "PASS",
        "task_id": TASK41_MODEL_ID,
        "comparison_group": "task41extra_phi90_p50x50_g17x20_g13_a1a2",
        "a1": {
            "run_id": TASK41_RUN_ID,
            "model_id": TASK41_MODEL_ID,
            "method": "full3d_direct",
            "mpi_size": 1,
            "source_sha": source_sha,
            "input_path": str(TASK41_INPUT_RELATIVE),
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "resolved_config_sha256": resolved_sha,
            "run_root": str(run_root.relative_to(root)),
            "run_manifest": run_manifest,
            "numerical_summary": numerical_summary,
            "resolved_config": resolved_config,
            "required_checker": checker_record,
            "discrete_identity": {
                "mesh_sha256": "1" * 64,
                "mode_manifest_sha256": "2" * 64,
                "ordered_mode_key_sha256": "3" * 64,
                "mode_count": 168,
                "full_fe_rows": 934764,
                "mpc_map_status": "NOT_RECORDED",
                "mpc_map_sha256": None,
                "same_discrete_comparison_ready": False,
            },
            "abi_identity": {
                "scalar_type": "complex128", "int_type": "int32", "mpi_size": 1
            },
            "comparison_artifacts": artifacts,
        },
    }
    binding_path = root / TASK41_A1_COMPARISON_BINDING_RELATIVE
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return binding_path, binding


def test_task41_a2_contract_reopens_and_hash_binds_a1_evidence(tmp_path):
    binding_path, binding = _write_a1_comparison_binding_fixture(tmp_path)
    contract_path, contract = _write_contract(tmp_path, case_id="A2")
    contract["comparison"] = {
        "a1_binding_path": str(TASK41_A1_COMPARISON_BINDING_RELATIVE),
        "a1_binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
        "same_discrete_comparison_ready": False,
    }
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    loaded, _ = require_task41_p0_contract(contract_path, current_root=tmp_path)
    assert loaded["case"]["run_id"] == TASK41_A2_RUN_ID
    assert loaded["comparison"]["same_discrete_comparison_ready"] is False
    assert binding["a1"]["discrete_identity"]["mpc_map_status"] == "NOT_RECORDED"

    binding_path.write_bytes(binding_path.read_bytes() + b" ")
    with pytest.raises(Task41ContractError, match="binding SHA-256 differs"):
        require_task41_p0_contract(contract_path, current_root=tmp_path)


def test_task41_a2_contract_rejects_missing_binding_or_fabricated_mpc_hash(tmp_path):
    binding_path, binding = _write_a1_comparison_binding_fixture(tmp_path)
    contract_path, contract = _write_contract(tmp_path, case_id="A2")
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Task41ContractError, match="omits its immutable A1 comparison binding"):
        require_task41_p0_contract(contract_path, current_root=tmp_path)

    discrete = binding["a1"]["discrete_identity"]
    discrete["mpc_map_status"] = "NOT_RECORDED"
    discrete["mpc_map_sha256"] = "4" * 64
    binding_path.write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    contract["comparison"] = {
        "a1_binding_path": str(TASK41_A1_COMPARISON_BINDING_RELATIVE),
        "a1_binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
        "same_discrete_comparison_ready": False,
    }
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(Task41ContractError, match="missing MPC map identity"):
        require_task41_p0_contract(contract_path, current_root=tmp_path)


@pytest.mark.parametrize("case_id", ["A1", "A2"])
def test_task41_watchdog_authorizes_checker_kind_and_command_for_bound_case(
    tmp_path, monkeypatch, case_id
):
    import benchmarks.subreaper_watchdog as watchdog
    import src.runners.task41_p0_contract as contract_module

    if case_id == "A2":
        binding_path, binding = _write_a1_comparison_binding_fixture(tmp_path)
    contract_path, contract = _write_contract(tmp_path, case_id=case_id)
    qualified_python = Path(sys.executable).resolve()
    contract["runtime"]["runtime_prefix"] = str(qualified_python.parent.parent)
    if case_id == "A2":
        contract["comparison"] = {
            "a1_binding_path": str(TASK41_A1_COMPARISON_BINDING_RELATIVE),
            "a1_binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
            "same_discrete_comparison_ready": binding["a1"]["discrete_identity"][
                "same_discrete_comparison_ready"
            ],
        }
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    window_path = tmp_path / contract["window"]["path"]
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    case = contract["case"]
    run_root = (
        tmp_path / "results" / TASK41_MODEL_ID
        / f"{case['run_id']}__attempt"
    )
    numerical_directory = run_root / "numerical_output"
    numerical_directory.mkdir(parents=True)
    input_path = tmp_path / case["input_path"]
    summary_path = run_root / "run_summary.json"
    manifest_path = run_root / "run_manifest.json"
    numerical_summary_path = (
        run_root / "task40_v10_p6_candidate_summary.json"
        if case_id == "A2"
        else numerical_directory / "run_summary.json"
    )
    for path in (summary_path, manifest_path, numerical_summary_path):
        path.write_text("{}\n", encoding="utf-8")
    output_path = (
        tmp_path / contract["evidence"]["service_directory"]
        / "task41_p0_checker_result.json"
    ).resolve()
    command = [
        str(qualified_python),
        "-m",
        "src.runners.task41_p0_checker",
        "--input",
        str(input_path.resolve()),
        "--summary",
        str(summary_path.resolve()),
        "--manifest",
        str(manifest_path.resolve()),
        "--numerical-output",
        str(numerical_directory.resolve()),
        "--contract",
        str(contract_path.resolve()),
        "--contract-sha256",
        contract_sha,
        "--output",
        str(output_path),
    ]
    input_paths = [
        input_path.resolve(),
        summary_path.resolve(),
        manifest_path.resolve(),
        numerical_summary_path.resolve(),
    ]
    source_sha = contract["source"]["sha"]
    checker_kind = (
        "task41_p0_a2_independent_p6_iterative_checker"
        if case_id == "A2"
        else "task41_p0_independent_full_a6_checker"
    )
    authorization = {
        "schema": "task41.p0.closeout_checker_authorization.v1",
        "phase": "closeout",
        "purpose": "registered_read_only_required_checker",
        "checker_kind": checker_kind,
        "command_sha256": hashlib.sha256(
            json.dumps(command, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        "input_paths": [str(path) for path in input_paths],
        "input_sha256s": [hashlib.sha256(path.read_bytes()).hexdigest() for path in input_paths],
        "expected_channel_count": None,
        "campaign_window_sha256": window_sha,
        "task41_contract_sha256": contract_sha,
        "source_sha": source_sha,
        "source_branch": TASK41_BRANCH,
        "source_clean": True,
    }
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(watchdog.sys, "executable", str(qualified_python))
    monkeypatch.setattr(
        contract_module,
        "_git",
        lambda _root, *args: (
            source_sha
            if args == ("rev-parse", "HEAD")
            else TASK41_BRANCH
            if args == ("branch", "--show-current")
            else ""
            if args == ("status", "--porcelain", "--untracked-files=normal")
            else (_ for _ in ()).throw(AssertionError(f"unexpected git query: {args}"))
        ),
    )

    def fake_git_run(command, **_kwargs):
        outputs = {
            ("git", "rev-parse", "HEAD"): f"{source_sha}\n",
            ("git", "branch", "--show-current"): f"{TASK41_BRANCH}\n",
            ("git", "status", "--porcelain", "--untracked-files=normal"): "",
        }
        return SimpleNamespace(returncode=0, stdout=outputs[tuple(command)], stderr="")

    monkeypatch.setattr(watchdog.subprocess, "run", fake_git_run)
    environment = {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path.resolve()),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
    }
    campaign = SimpleNamespace(path=window_path.resolve(), sha256=window_sha)
    validated = watchdog._validate_campaign_closeout_authorization(
        command=command,
        campaign=campaign,
        authorization=authorization,
        worker_environment=environment,
    )
    assert validated == authorization

    wrong_case_authorization = dict(authorization)
    wrong_case_authorization["checker_kind"] = (
        "task41_p0_independent_full_a6_checker"
        if case_id == "A2"
        else "task41_p0_a2_independent_p6_iterative_checker"
    )
    with pytest.raises(ValueError, match="registered Task41 checker for its contract case"):
        watchdog._validate_campaign_closeout_authorization(
            command=command,
            campaign=campaign,
            authorization=wrong_case_authorization,
            worker_environment=environment,
        )


def test_task41_a2_worker_runtime_uses_service_window_and_strict_resource_view(
    tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as contract_module
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.io.execution_plan import resolved_config_bytes
    from src.io.input_validation import load_and_resolve
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task40_v10_worker import (
        _candidate_contract,
        _task41_a2_runtime_configuration,
    )

    repo_root = Path(__file__).resolve().parents[2]
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    contract_path, task_contract = _write_contract(tmp_path, case_id="A2")
    actual_input = repo_root / TASK41_A2_INPUT_RELATIVE
    fixture_input = tmp_path / TASK41_A2_INPUT_RELATIVE
    fixture_input.parent.mkdir(parents=True, exist_ok=True)
    fixture_input.write_bytes(actual_input.read_bytes())
    specification = load_and_resolve(fixture_input)
    task_contract["source"]["sha"] = source_sha
    task_contract["case"].update(
        {
            "input_sha256": specification.input_sha256,
            "model_id": specification.identity["model_id"],
            "physical_model_sha256": specification.physical_model_sha256,
            "resolved_config_sha256": hashlib.sha256(
                resolved_config_bytes(specification)
            ).hexdigest(),
            "method": specification.method["kind"],
            "mpi_size": specification.execution["mpi_size"],
        }
    )
    from src.runners.task41_p0_contract import TASK41_A2_SERVICE_RELATIVE

    task_contract["evidence"]["service_directory"] = str(
        TASK41_A2_SERVICE_RELATIVE / f"service_source_{source_sha}"
    )
    binding_path = tmp_path / TASK41_A1_COMPARISON_BINDING_RELATIVE
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text("{}\n", encoding="utf-8")
    binding_sha = hashlib.sha256(binding_path.read_bytes()).hexdigest()
    task_contract["comparison"] = {
        "a1_binding_path": str(TASK41_A1_COMPARISON_BINDING_RELATIVE),
        "a1_binding_sha256": binding_sha,
        "same_discrete_comparison_ready": False,
    }

    def fake_git(_root, *args):
        return {
            ("rev-parse", "HEAD"): source_sha,
            ("branch", "--show-current"): TASK41_BRANCH,
            ("status", "--porcelain", "--untracked-files=normal"): "",
        }[tuple(args)]

    monkeypatch.setattr(contract_module, "_git", fake_git)
    monkeypatch.setattr(
        contract_module,
        "require_task41_a1_comparison_binding",
        lambda *_args, **_kwargs: (
            {
                "a1": {
                    "physical_model_sha256": specification.physical_model_sha256,
                    "discrete_identity": {"same_discrete_comparison_ready": False},
                }
            },
            binding_sha,
        ),
    )
    contract_path = tmp_path / contract_relative_path(source_sha, "A2")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        json.dumps(task_contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    window_path = tmp_path / task_contract["window"]["path"]
    window_sha = task_contract["window"]["sha256"]
    for key, value in {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path.resolve()),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_EXECUTION_WINDOW_PATH": str(window_path.resolve()),
        "TASK41_P0_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK41_P0_TASK_MEMORY_MAX_BYTES": str(TASK41_TASK_MEMORY_MAX_BYTES),
        "TASK41_P0_HOST_RESERVE_BYTES": str(TASK41_HOST_RESERVE_BYTES),
        "TASK41_P0_MEMORY_SWAP_MAX_BYTES": "0",
        "PHYSICAL_WATCHDOG_MEMORY_POLICY": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        "PHYSICAL_WATCHDOG_PSS_POLICY": "disabled_by_profile",
        "PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH": str(tmp_path / "unused_task40_ledger.json"),
        "PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX": "0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("TASK40_V10_CAMPAIGN_WINDOW", raising=False)

    from src.runners.task41_p0_contract import load_task41_p0_fixed_window

    loaded_contract, _ = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha,
        current_root=tmp_path,
        case_id="A2",
    )
    window = load_task41_p0_fixed_window(loaded_contract, current_root=tmp_path)
    window.observe(label="test_service_worker_entry")

    profile_contract = profile_facts(TASK41_G13_A2_PRECONDITIONER)
    runtime_contract, resource_overrides = _task41_a2_runtime_configuration(
        profile_contract
    )
    runtime = _V14Runtime(
        tmp_path / "runtime",
        "TASK41_A2",
        runtime_contract,
        root=tmp_path,
        source_sha=source_sha,
        batch_identity="task41_p0_a2_g13_a2_p6_reference",
        evidence_prefix="task41_runtime_fixture",
        require_zero_swap=True,
        **resource_overrides,
    )
    candidate = _candidate_contract(
        specification.as_jsonable(),
        profile_contract,
        runtime,
        profile_identity=TASK41_G13_A2_PRECONDITIONER,
        task41_source_sha=source_sha,
        current_root=tmp_path,
    )

    assert all(candidate["checks"].values())
    assert candidate["worker_reserved_seconds"] > 0.0
    assert runtime._ledger_path is None
    assert runtime.fixed_process_tree_cap_bytes == TASK41_TASK_MEMORY_MAX_BYTES
    assert runtime.host_reserve_bytes_override == TASK41_HOST_RESERVE_BYTES
    assert runtime.task_cgroup_reserve_bytes_override == 0
    assert runtime.require_cgroup_memory_details is True
    assert runtime.require_zero_swap is True
