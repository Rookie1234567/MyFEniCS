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

from src.geometry.task41_phi90_profile import TASK41_B0_GEOMETRY_IDENTITY
from src.runners.task40_v10_campaign import _utc_ns
from src.runners.workflow_timebase import clock_sample
from src.runners.task41_p0_contract import (
    TASK41_A1_COMPARISON_BINDING_RELATIVE,
    TASK41_A1_COMPARISON_BINDING_SCHEMA,
    TASK41_A2_CONTROLLER_RELATIVE,
    TASK41_A2_INPUT_RELATIVE,
    TASK41_A2_RUN_ID,
    TASK41_A2_WINDOW_RELATIVE,
    TASK41_B0_BOOTSTRAP_TREATMENT,
    TASK41_B0_COMPARISON_GROUP,
    TASK41_B0_PRECONDITIONER,
    TASK41_B0_T0_BASIS,
    TASK41_B0_T0_SOURCE_SHA,
    TASK41_B0_T0_UTC,
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
    if case_id == "B0":
        repository_input = Path(__file__).resolve().parents[2] / case_spec["input_relative"]
        shutil.copyfile(repository_input, input_path)
    else:
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
    t0_ns = _utc_ns(TASK41_B0_T0_UTC) if case_id == "B0" else current["utc_ns"]
    entry_source = TASK41_B0_T0_SOURCE_SHA if case_id == "B0" else "b" * 40
    accounting = controller_root / "campaign_accounting_v10.jsonl"
    window_payload = {
        "schema": TASK41_P0_WINDOW_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "source_sha": entry_source,
        "t0_utc": TASK41_B0_T0_UTC if case_id == "B0" else _utc_z(t0_ns),
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
    if case_id == "B0":
        window_payload.update(
            {
                "t0_basis": TASK41_B0_T0_BASIS,
                "bootstrap_utc_elapsed_seconds": (
                    int(current["utc_ns"]) - t0_ns
                )
                / 1e9,
                "bootstrap_boottime_elapsed_seconds": None,
                "bootstrap_time_treatment": TASK41_B0_BOOTSTRAP_TREATMENT,
            }
        )
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
    if case_id == "B0":
        contract["case"].update(
            {
                "profile_identity": TASK41_B0_PRECONDITIONER,
                "solver_stage": "TASK41_B0",
                "comparison_group": TASK41_B0_COMPARISON_GROUP,
                "geometry_identity": TASK41_B0_GEOMETRY_IDENTITY,
            }
        )
        contract["preparation"] = {
            "existing_surface_donor": contract_module.TASK41_B0_SAVED_SURFACE_DONOR,
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


@pytest.mark.parametrize("case_id", ["A1", "B0"])
def test_task41_prepare_keeps_first_t0_after_validation_failure_and_source_change(
    tmp_path, monkeypatch, case_id
):
    import src.runners.task41_p0_contract as contract_module

    repo_root = Path(__file__).resolve().parents[2]
    case_spec = contract_module._task41_case(case_id)
    input_relative = case_spec["input_relative"]
    input_path = tmp_path / input_relative
    input_path.parent.mkdir(parents=True)
    original_input = repo_root.joinpath(input_relative).read_bytes()
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
    if case_id == "B0":
        monkeypatch.setattr(
            contract_module,
            "verify_task41_b0_saved_surface_donor",
            lambda *_args, **_kwargs: {"status": "fixture metadata accepted"},
        )
    prepare_args = {
        "runtime_prefix": runtime,
        "abi_receipt": abi_receipt,
        "jit_cache": jit_cache,
        "current_root": tmp_path,
        "case_id": case_id,
    }
    with pytest.raises(Task41ContractError, match="could not be resolved"):
        prepare_task41_p0(**prepare_args)

    window_path = tmp_path / case_spec["window_relative"]
    first_window_bytes = window_path.read_bytes()
    first_window_sha = hashlib.sha256(first_window_bytes).hexdigest()
    first_window_payload = json.loads(first_window_bytes)
    assert first_window_payload["source_sha"] == git_state["sha"]
    if case_id == "B0":
        expected_t0_ns = _utc_ns(TASK41_B0_T0_UTC)
        assert first_window_payload["t0_utc"] == _utc_z(expected_t0_ns)
        assert first_window_payload["t0_basis"] == TASK41_B0_T0_BASIS
        assert first_window_payload["bootstrap_utc_elapsed_seconds"] == (
            first_window_payload["anchor"]["utc_ns"] - expected_t0_ns
        ) / 1e9

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


@pytest.mark.parametrize("case_id", ["A1", "B0"])
def test_task41_launcher_and_service_pass_real_window_resources_and_checker_authority(
    tmp_path, monkeypatch, request, capsys, case_id
):
    import benchmarks.subreaper_watchdog as watchdog
    import benchmarks.task034_wsl_resources as resources
    import scripts.run_case as run_case
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
    service_relative = fixture_relative / "service_base"
    if case_id == "B0":
        monkeypatch.setattr(
            contract_module, "TASK41_B0_CONTROLLER_RELATIVE", controller_relative
        )
        monkeypatch.setattr(
            contract_module, "TASK41_B0_WINDOW_RELATIVE", window_relative
        )
        monkeypatch.setattr(
            contract_module, "TASK41_B0_SERVICE_RELATIVE", service_relative
        )
    else:
        monkeypatch.setattr(contract_module, "TASK41_CONTROLLER_RELATIVE", controller_relative)
        monkeypatch.setattr(contract_module, "TASK41_WINDOW_RELATIVE", window_relative)
        monkeypatch.setattr(contract_module, "TASK41_A1_SERVICE_RELATIVE", service_relative)
    case_spec = contract_module._task41_case(case_id)
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

    input_path = repo_root / case_spec["input_relative"]
    specification = load_and_resolve(input_path)
    payload_errors = task41_payload_errors(specification.as_jsonable())
    assert not payload_errors
    qualified_interpreter = Path(sys.executable).resolve()
    runtime_prefix = fixture_root / "runtime_prefix"
    qualified_python = runtime_prefix / "bin/python"
    qualified_python.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(qualified_interpreter, qualified_python)
    monkeypatch.setattr(sys, "executable", str(qualified_python))
    assert qualified_python.resolve() == Path(sys.executable).resolve()
    abi_receipt = fixture_root / "abi_receipt.json"
    abi_receipt.parent.mkdir(parents=True, exist_ok=True)
    abi_receipt.write_text('{"fixture":"qualified native receipt shape"}\n', encoding="utf-8")
    jit_cache = tmp_path / "jit-cache"
    jit_cache.mkdir()
    accounting_path = repo_root / controller_relative / "campaign_accounting_v10.jsonl"
    anchor = clock_sample(include_boot_id=True)
    t0_ns = (
        _utc_ns(TASK41_B0_T0_UTC)
        if case_id == "B0"
        else int(anchor["utc_ns"])
    )
    entry_source_sha = TASK41_B0_T0_SOURCE_SHA if case_id == "B0" else source_sha
    window_payload = {
        "schema": TASK41_P0_WINDOW_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "source_sha": entry_source_sha,
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
    if case_id == "B0":
        window_payload.update(
            {
                "t0_basis": TASK41_B0_T0_BASIS,
                "bootstrap_utc_elapsed_seconds": (
                    int(anchor["utc_ns"]) - t0_ns
                )
                / 1e9,
                "bootstrap_boottime_elapsed_seconds": None,
                "bootstrap_time_treatment": TASK41_B0_BOOTSTRAP_TREATMENT,
            }
        )
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
            "input_path": str(case_spec["input_relative"]),
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
            "entry_source_sha": entry_source_sha,
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
                case_spec["service_relative"]
                / f"service_source_{source_sha}"
            ),
        },
    }
    if case_id == "B0":
        contract["case"].update(
            {
                "profile_identity": case_spec["profile_identity"],
                "solver_stage": case_spec["solver_stage"],
                "comparison_group": case_spec["comparison_group"],
                "geometry_identity": TASK41_B0_GEOMETRY_IDENTITY,
            }
        )
        contract["preparation"] = {
            "existing_surface_donor": contract_module.TASK41_B0_SAVED_SURFACE_DONOR,
        }
    contract_path = repo_root / contract_module.contract_relative_path(
        source_sha, case_id
    )
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
            "process_tree_swap_gate_enforced": True,
            "sampled_process_tree_swap_peak_bytes": 0,
            "job_cgroup_swap_gate_enforced": True,
            "job_cgroup_swap": {"passed": True},
        }

    monkeypatch.setattr(watchdog, "supervise", capture_supervise)
    timestamp = f"task41-fixture-{uuid4().hex}"
    run_case_return_code = run_case.main(
        [
            str(input_path),
            "--task41-p0-execution-contract",
            str(contract_path),
        ]
    )
    launch_result = json.loads(capsys.readouterr().out)
    assert run_case_return_code == 0
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
            if case_id in {"A2", "B0"}:
                (run_root / "task40_v10_p6_candidate_summary.json").write_text(
                    "{}\n", encoding="utf-8"
                )
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


@pytest.mark.parametrize("case_id", ["A1", "A2", "B0", "B0_V3"])
def test_task41_watchdog_authorizes_checker_kind_and_command_for_bound_case(
    tmp_path, monkeypatch, case_id
):
    import benchmarks.subreaper_watchdog as watchdog
    import src.runners.task41_p0_contract as contract_module

    is_v3 = case_id == "B0_V3"
    if is_v3:
        case_id = "B0"
    if case_id == "A2":
        binding_path, binding = _write_a1_comparison_binding_fixture(tmp_path)
    contract_path, contract = _write_contract(tmp_path, case_id=case_id)
    if is_v3:
        _adopt_v3_window_fixture(tmp_path, contract, monkeypatch)
    qualified_python = Path(sys.executable).absolute()
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
        if case_id in {"A2", "B0"}
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
    checker_kind = contract_module.task41_p0_checker_kind_for_case(case_id)
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


def test_task41_refinement_requires_validated_full_owner_scope():
    from src.runners.task40_v10_worker import _task41_b0_require_full_owner_scope
    from src.runners.task41_p0_contract import (
        TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
        TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE,
    )

    assert _task41_b0_require_full_owner_scope(
        {"full_owner_scope_authorized": False}, refinement_max_steps=0
    ) is False
    root = Path(__file__).resolve().parents[2]
    accounting_path = root / "test-fixture" / "campaign_accounting.jsonl"
    run_directory = root / "results" / TASK41_MODEL_ID / "v15_guard_fixture"
    authority = {
        "execution_scope": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        "campaign_window_path": str(
            (root / TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE).resolve()
        ),
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "internal_rhs_refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "internal_rhs_refinement_max_steps": 2,
        "full_owner_quota_scope": "fixed_window_across_attempts",
        "full_owner_quota_claim_path": str(
            accounting_path.with_name(
                accounting_path.name + ".v15_full_owner_claim.json"
            )
        ),
        "actual_k_lu_identity_required": True,
        "campaign_accounting_path": str(accounting_path),
        "run_directory": str(run_directory),
    }
    assert _task41_b0_require_full_owner_scope(
        authority, refinement_max_steps=2, run_directory=run_directory
    ) is True
    with pytest.raises(ValueError, match="exact V15 full-acceptance contract"):
        _task41_b0_require_full_owner_scope(
            {"full_owner_scope_authorized": True},
            refinement_max_steps=2,
            run_directory=run_directory,
        )
    v14_authority = dict(
        authority,
        execution_scope=TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
    )
    with pytest.raises(ValueError, match="exact V15 full-acceptance contract"):
        _task41_b0_require_full_owner_scope(
            v14_authority, refinement_max_steps=2, run_directory=run_directory
        )
    for invalid in (True, 2.0):
        with pytest.raises(ValueError, match="strict integer"):
            _task41_b0_require_full_owner_scope(
                authority, refinement_max_steps=invalid, run_directory=run_directory
            )
    with pytest.raises(ValueError, match="0 or 2"):
        _task41_b0_require_full_owner_scope(
            authority, refinement_max_steps=1, run_directory=run_directory
        )


def test_task41_v15_owner_quota_is_claimed_once_and_audits_actual_k_lu(tmp_path):
    from types import SimpleNamespace

    from src.runners.task40_v10_worker import _task41_b0_build_v15_full_owner_once
    from src.runners.task41_p0_contract import (
        TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE,
    )

    accounting_path = tmp_path / "campaign" / "accounting.jsonl"
    window_path = tmp_path / TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE
    output_root = tmp_path / "results" / TASK41_MODEL_ID / "attempt-v15"
    output_root.mkdir(parents=True)
    accounting_path.parent.mkdir(parents=True)
    claim_path = accounting_path.with_name(
        accounting_path.name + ".v15_full_owner_claim.json"
    )
    authority = {
        "execution_scope": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        "campaign_window_path": str(window_path),
        "campaign_window_sha256": "a" * 64,
        "campaign_accounting_path": str(accounting_path),
        "full_owner_quota_claim_path": str(claim_path),
        "full_owner_quota_scope": "fixed_window_across_attempts",
        "model_id": TASK41_MODEL_ID,
        "run_directory": str(output_root.resolve()),
        "task41_contract_path": str(tmp_path / "contract.json"),
        "task41_contract_sha256": "b" * 64,
        "source_sha": "c" * 40,
        "input_sha256": "d" * 64,
    }
    generation = object()
    condensed = SimpleNamespace(
        actual_internal_matrix_identity_by_class={"class-0": generation},
        interior_lu_matrix_identity_by_class={"class-0": generation},
        retained_actual_internal_matrix_by_class={"class-0": object()},
        interior_lu_by_class={"class-0": object()},
    )
    built = {"condensed": condensed}
    calls = 0

    def owner_builder():
        nonlocal calls
        calls += 1
        return built

    owner, claim = _task41_b0_build_v15_full_owner_once(
        authority,
        run_directory=output_root,
        owner_builder=owner_builder,
        current_root=tmp_path,
    )
    assert owner is built
    assert claim["status"] == "BUILD_COMPLETED"
    assert claim["full_owner_build_count"] == 1
    assert claim["actual_k_lu_identity"][
        "actual_k_and_lu_share_generation_token_for_every_class"
    ] is True
    assert json.loads(claim_path.read_text(encoding="utf-8"))["status"] == "BUILD_COMPLETED"
    with pytest.raises(ValueError, match="quota is already consumed"):
        _task41_b0_build_v15_full_owner_once(
            authority,
            run_directory=output_root,
            owner_builder=owner_builder,
            current_root=tmp_path,
        )
    assert calls == 1


def test_task41_v15_owner_is_preserved_when_postbuild_identity_audit_fails(tmp_path):
    from src.runners.task40_v10_worker import _task41_b0_build_v15_full_owner_once
    from src.runners.task41_p0_contract import (
        TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE,
    )

    accounting_path = tmp_path / "campaign" / "accounting.jsonl"
    output_root = tmp_path / "results" / TASK41_MODEL_ID / "attempt-v15"
    output_root.mkdir(parents=True)
    claim_path = accounting_path.with_name(
        accounting_path.name + ".v15_full_owner_claim.json"
    )
    authority = {
        "execution_scope": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        "campaign_window_path": str(tmp_path / TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE),
        "campaign_window_sha256": "a" * 64,
        "campaign_accounting_path": str(accounting_path),
        "full_owner_quota_claim_path": str(claim_path),
        "full_owner_quota_scope": "fixed_window_across_attempts",
        "model_id": TASK41_MODEL_ID,
        "run_directory": str(output_root.resolve()),
        "task41_contract_path": str(tmp_path / "contract.json"),
        "task41_contract_sha256": "b" * 64,
        "source_sha": "c" * 40,
        "input_sha256": "d" * 64,
    }
    owner = {"condensed": object()}
    registered = []
    with pytest.raises(ValueError, match="retained actual K/LU identity maps"):
        _task41_b0_build_v15_full_owner_once(
            authority,
            run_directory=output_root,
            owner_builder=lambda: owner,
            owner_built_callback=registered.append,
            current_root=tmp_path,
        )
    assert registered == [owner]
    assert json.loads(claim_path.read_text(encoding="utf-8"))["status"] == "BUILD_STARTED"


@pytest.mark.parametrize("case_id", ("A2", "B0", "B0_V3"))
def test_task41_worker_runtime_uses_service_window_and_strict_resource_view(
    case_id, tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as contract_module
    from src.geometry.task41_phi90_profile import (
        TASK41_B0_PRECONDITIONER,
        TASK41_G13_A2_PRECONDITIONER,
    )
    from src.io.execution_plan import resolved_config_bytes
    from src.io.input_validation import load_and_resolve
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task40_v10_worker import (
        _candidate_contract,
        _task41_p0_runtime_configuration,
    )

    is_v3 = case_id == "B0_V3"
    if is_v3:
        case_id = "B0"
    repo_root = Path(__file__).resolve().parents[2]
    case_spec = contract_module._task41_case(case_id)
    profile_identity = (
        TASK41_G13_A2_PRECONDITIONER
        if case_id == "A2"
        else TASK41_B0_PRECONDITIONER
    )
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    contract_path, task_contract = _write_contract(tmp_path, case_id=case_id)
    if is_v3:
        _adopt_v3_window_fixture(tmp_path, task_contract, monkeypatch)
    input_relative = Path(case_spec["input_relative"])
    actual_input = repo_root / input_relative
    fixture_input = tmp_path / input_relative
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
    task_contract["evidence"]["service_directory"] = str(
        case_spec["service_relative"] / f"service_source_{source_sha}"
    )
    binding_sha = None
    if case_id == "A2":
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
    if case_id == "A2":
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
    contract_path = tmp_path / contract_relative_path(source_sha, case_id)
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
        case_id=case_id,
    )
    window = load_task41_p0_fixed_window(loaded_contract, current_root=tmp_path)
    window.observe(label="test_service_worker_entry")

    profile_contract = profile_facts(profile_identity)
    runtime_contract, resource_overrides = _task41_p0_runtime_configuration(
        profile_contract, case_id=case_id
    )
    batch_identity = (
        "task41_p0_a2_g13_a2_p6_reference"
        if case_id == "A2"
        else "task41_p0_b0_07nm_p6_reference"
    )
    runtime = _V14Runtime(
        tmp_path / "runtime",
        case_spec["solver_stage"],
        runtime_contract,
        root=tmp_path,
        source_sha=source_sha,
        batch_identity=batch_identity,
        evidence_prefix="task41_runtime_fixture",
        require_zero_swap=True,
        **resource_overrides,
    )
    task41_contract_binding = None
    if case_id == "B0":
        from src.runners.task038_full3d_iterative import _task41_b0_dispatch_binding

        task41_contract_binding = _task41_b0_dispatch_binding(
            specification.as_jsonable(),
            source_sha=source_sha,
            current_root=tmp_path,
        )
    candidate = _candidate_contract(
        specification.as_jsonable(),
        profile_contract,
        runtime,
        profile_identity=profile_identity,
        task41_source_sha=source_sha,
        task41_contract_binding=task41_contract_binding,
        current_root=tmp_path,
    )

    assert all(candidate["checks"].values())
    assert candidate["case_id"] == case_id
    assert candidate["run_id"] == case_spec["run_id"]
    assert runtime.stage == case_spec["solver_stage"]
    assert runtime.batch_identity == batch_identity
    assert candidate["worker_reserved_seconds"] > 0.0
    assert runtime._ledger_path is None
    assert runtime.fixed_process_tree_cap_bytes == TASK41_TASK_MEMORY_MAX_BYTES
    assert runtime.host_reserve_bytes_override == TASK41_HOST_RESERVE_BYTES
    assert runtime.task_cgroup_reserve_bytes_override == 0
    assert runtime.require_cgroup_memory_details is True
    assert runtime.require_zero_swap is True
    assert runtime_contract["resources"]["process_tree_rss_cap_bytes"] == TASK41_TASK_MEMORY_MAX_BYTES
    assert runtime_contract["resources"]["host_reserve_bytes"] == TASK41_HOST_RESERVE_BYTES
    assert runtime_contract["resources"]["memory_swap_max_bytes"] == 0
    assert candidate["campaign_window_path"] == str(window.path)
    assert candidate["campaign_window_sha256"] == window.sha256
    if is_v3:
        assert candidate["campaign_seconds"] == 86400
        assert 0 < candidate["worker_reserved_seconds"] <= 85200
    elif case_id == "B0":
        window_payload = json.loads(window.path.read_text(encoding="utf-8"))
        assert window_payload["t0_basis"] == TASK41_B0_T0_BASIS
        assert window_payload["t0_utc"] == TASK41_B0_T0_UTC
        assert window_payload["bootstrap_time_treatment"] == TASK41_B0_BOOTSTRAP_TREATMENT
        assert window_payload["bootstrap_utc_elapsed_seconds"] >= 0.0
        assert candidate["checks"]["explicit_dispatch_contract_binding"]
        assert candidate["checks"]["no_a1_or_a2_comparison_binding"]



@pytest.mark.parametrize("retry", [False, True])
def test_task41_v15_dispatch_binding_uses_verified_window_accounting_path(
    tmp_path, monkeypatch, retry
):
    import src.runners.task41_p0_contract as contract_module
    from src.geometry.task41_phi90_profile import TASK41_B0_PRECONDITIONER
    from src.io.execution_plan import resolved_config_bytes
    from src.io.input_validation import load_and_resolve
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task038_full3d_iterative import _task41_b0_dispatch_binding
    from src.runners.task40_v10_worker import (
        _candidate_contract,
        _task41_p0_runtime_configuration,
    )

    # Reuse the existing authorized V15 prepare fixture so this exercises the
    # real prepared contract/window shape, including its deliberate omission
    # of accounting_path from the contract's window projection.
    test_task41_v15_full_acceptance_prepare_binds_36h_scope_and_raw_policy(
        tmp_path, monkeypatch
    )
    contract_paths = list(
        (tmp_path / contract_module.TASK41_B0_CONTROLLER_RELATIVE).glob(
            "execution_contract_source_*_v15_full_two_column_acceptance_36h.json"
        )
    )
    assert len(contract_paths) == 1
    contract_path = contract_paths[0].resolve()
    if retry:
        retry_contract = json.loads(contract_path.read_text())
        retry_window = load_task41_p0_fixed_window(retry_contract, current_root=tmp_path)
        retry_contract["full_owner_retry_authorization"] = _v15_retry_fixture(
            tmp_path, retry_window.path, retry_window.accounting_path
        )[0]
        contract_path.write_text(json.dumps(retry_contract))
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    contract, _ = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha,
        current_root=tmp_path,
        case_id="B0",
    )
    assert "accounting_path" not in contract["window"]

    case_spec = contract_module._task41_case("B0")
    input_path = tmp_path / case_spec["input_relative"]
    specification = load_and_resolve(input_path)
    resolved = specification.as_jsonable()
    source_sha = contract["source"]["sha"]
    assert source_sha == "a" * 40
    assert contract["case"]["input_sha256"] == specification.input_sha256
    assert contract["case"]["resolved_config_sha256"] == hashlib.sha256(
        resolved_config_bytes(specification)
    ).hexdigest()

    expected_output_parent = Path(
        resolved["provenance"]["expected_output_parent"]
    )
    if not expected_output_parent.is_absolute():
        expected_output_parent = tmp_path / expected_output_parent
    expected_output_parent.mkdir(parents=True, exist_ok=True)
    run_directory = expected_output_parent / "v15-dispatch-binding-attempt"
    run_directory.mkdir()

    window = load_task41_p0_fixed_window(contract, current_root=tmp_path)
    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(contract_path))
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", contract_sha)
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_PATH", str(window.path.resolve()))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_SHA256", window.sha256)
    monkeypatch.setenv("TASK41_P0_V15_FULL_ACCEPTANCE", "1")
    monkeypatch.setenv(
        "TASK41_P0_V15_OUTPUT_DIRECTORY", str(run_directory.resolve())
    )
    monkeypatch.setenv(
        "TASK41_P0_TASK_MEMORY_MAX_BYTES",
        str(contract["resources"]["task_memory_max_bytes"]),
    )
    monkeypatch.setenv(
        "TASK41_P0_HOST_RESERVE_BYTES",
        str(contract["resources"]["host_reserve_bytes"]),
    )
    monkeypatch.setenv(
        "TASK41_P0_MEMORY_SWAP_MAX_BYTES",
        str(contract["resources"]["memory_swap_max_bytes"]),
    )
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_MEMORY_POLICY",
        "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PSS_POLICY", "disabled_by_profile")
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH",
        str(tmp_path / "unused_task40_ledger.json"),
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX", "0")
    monkeypatch.delenv("TASK40_V10_CAMPAIGN_WINDOW", raising=False)
    monkeypatch.chdir(tmp_path)

    binding = _task41_b0_dispatch_binding(
        resolved,
        source_sha=source_sha,
        current_root=tmp_path,
        run_directory=run_directory,
    )
    expected_claim = window.accounting_path.with_name(
        window.accounting_path.name + ".v15_full_owner_claim.json"
    ).resolve()
    if retry:
        expected_claim = expected_claim.with_name(expected_claim.name + ".authorized_retry_1.json")
    assert binding["full_owner_retry_authorization"] == contract.get("full_owner_retry_authorization")
    assert binding["full_owner_quota_claim_path"] == str(expected_claim)
    assert binding["run_directory"] == str(run_directory.resolve())

    from src.runners.task40_v10_campaign import CampaignAccount

    CampaignAccount(window).record_sample(
        label="test_task41_v15_dispatch_worker_entry", phase="numeric"
    )

    profile_contract = profile_facts(TASK41_B0_PRECONDITIONER)
    runtime_contract, resource_overrides = _task41_p0_runtime_configuration(
        profile_contract, case_id="B0"
    )
    runtime = _V14Runtime(
        tmp_path / "runtime",
        case_spec["solver_stage"],
        runtime_contract,
        root=tmp_path,
        source_sha=source_sha,
        batch_identity="task41_p0_b0_07nm_p6_reference",
        evidence_prefix="task41_v15_dispatch_contract_fixture",
        require_zero_swap=True,
        **resource_overrides,
    )

    import src.runners.task038_full3d_iterative as dispatch_module
    import src.runners.task40_v10_worker as worker_module

    def check_candidate(payload, candidate_binding):
        return _candidate_contract(
            payload, profile_contract, runtime,
            profile_identity=TASK41_B0_PRECONDITIONER,
            task41_source_sha=source_sha,
            task41_contract_binding=candidate_binding,
            run_directory=run_directory, current_root=tmp_path,
        )

    captured = {}
    def worker_entry(payload, output, **kwargs):
        assert Path(output).resolve() == run_directory.resolve()
        captured["payload"] = payload
        return check_candidate(payload, kwargs["task41_contract_binding"])

    monkeypatch.setattr(dispatch_module, "__file__", str(tmp_path / "src/runners/task038_full3d_iterative.py"))
    monkeypatch.setattr(worker_module, "run_task40_v10_p6_reference_worker", worker_entry)
    candidate = dispatch_module.run_full3d_iterative(
        resolved, run_directory, source_sha=source_sha
    )
    assert all(candidate["checks"].values())
    assert candidate["checks"]["v15_full_owner_dispatch_binding"] is True
    assert candidate["full_owner_quota_claim_path"] == str(expected_claim)
    assert captured["payload"]["solver"]["internal_rhs_strategy"] == "same_lu_rhs_solve"

    wrong_claim_binding = dict(
        binding,
        full_owner_quota_claim_path=str(tmp_path / "wrong-v15-owner-claim.json"),
    )
    with pytest.raises(ValueError, match="v15_full_owner_dispatch_binding"):
        check_candidate(captured["payload"], wrong_claim_binding)


def _adopt_v3_window_fixture(root, contract, monkeypatch):
    import src.runners.task41_p0_contract as module

    parent = root / module.TASK41_B0_WINDOW_RELATIVE
    parent_bytes = parent.read_bytes()
    parent_sha = hashlib.sha256(parent_bytes).hexdigest()
    monkeypatch.setattr(module, "TASK41_B0_PARENT_WINDOW_SHA256", parent_sha)
    anchor = clock_sample(include_boot_id=True)
    auth = {
        "schema": "task41.b0.v3.user_continuation_authorization.v1",
        "authorization": "user_explicit_24h_20261019",
        "source_at_entry": contract["source"]["sha"],
        "anchor": anchor,
        "pre_anchor_preparation_charge_seconds": 180,
        "parent_window_path": str(module.TASK41_B0_WINDOW_RELATIVE),
        "parent_window_sha256": parent_sha,
        "total_seconds": 86400, "numerical_seconds": 85200, "closeout_seconds": 1200,
        "old_service_inactive_and_descendants_absent": True,
    }
    (root / module.TASK41_B0_V3_AUTH_RELATIVE).write_text(json.dumps(auth))
    # Exercise the real prepare path until its unrelated ABI fixture rejection.
    with monkeypatch.context() as patch:
        patch.setattr(module, "_git", lambda _root, *args: (
            contract["source"]["sha"] if args == ("rev-parse", "HEAD")
            else TASK41_BRANCH if args == ("branch", "--show-current") else ""
        ))
        patch.setattr(module, "_check_task41_native_receipt", lambda *_args: (_ for _ in ()).throw(RuntimeError("fixture ABI boundary")))
        with pytest.raises(RuntimeError, match="fixture ABI boundary"):
            module.prepare_task41_p0(
                current_root=root, case_id="B0", b0_v3_continuation=True,
                runtime_prefix=contract["runtime"]["runtime_prefix"],
                abi_receipt=contract["runtime"]["abi_receipt_path"],
                jit_cache=contract["runtime"]["jit_cache"],
            )
    path = root / module.TASK41_B0_V3_WINDOW_RELATIVE
    payload = json.loads(path.read_text())
    contract["window"] = {
        "path": str(module.TASK41_B0_V3_WINDOW_RELATIVE),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entry_source_sha": payload["source_sha"],
    }
    contract["time"] = {"total_seconds":86400, "numerical_seconds":85200, "closeout_seconds":1200}
    assert parent.read_bytes() == parent_bytes
    return path


def test_task41_b0_default_window_route_remains_unchanged(tmp_path):
    import src.runners.task41_p0_contract as module

    _, contract = _write_contract(tmp_path, "B0")
    path, total_seconds, numerical_seconds, continuation = module.task41_window_spec(
        contract, tmp_path
    )
    assert path == (tmp_path / module.TASK41_B0_WINDOW_RELATIVE).resolve()
    assert total_seconds == module.TASK41_TOTAL_SECONDS
    assert numerical_seconds == module.TASK41_NUMERICAL_SECONDS
    assert continuation is False


def test_task41_v3_window_immutable_and_parent_bound(tmp_path, monkeypatch):
    import src.runners.task41_p0_contract as module
    path, contract = _write_contract(tmp_path, "B0")
    new_path = _adopt_v3_window_fixture(tmp_path, contract, monkeypatch)
    path.write_text(json.dumps(contract))
    loaded, _ = require_task41_p0_contract(path, current_root=tmp_path)
    window = load_task41_p0_fixed_window(loaded, current_root=tmp_path)
    assert window.total_seconds == 86400 and window.cutoff_seconds == 85200
    assert window.closeout_seconds == 1200 and window.bootstrap_seconds == 180
    assert window.accounting_path.name == "campaign_accounting_v3_24h.jsonl"
    frozen = new_path.read_bytes()
    reopened, _, _ = module._task41_window_for_contract(tmp_path, "B0", b0_v3_continuation=True)
    assert reopened.t0_utc_ns == window.t0_utc_ns and new_path.read_bytes() == frozen
    old_path = tmp_path / module.TASK41_B0_WINDOW_RELATIVE
    old_path.write_bytes(old_path.read_bytes()+b" ")
    with pytest.raises(module.Task41ContractError, match="preserved parent changed"):
        load_task41_p0_fixed_window(loaded, current_root=tmp_path)

@pytest.mark.parametrize(
    "authorization_state",
    (
        "missing",
        "wrong_parent_path",
        "wrong_parent_sha",
        "missing_parent_file",
        "missing_preparation_start",
        "invalid_preparation_start",
    ),
)
def test_task41_v6_prepare_rejects_missing_authorization_or_wrong_parent_before_window(
    tmp_path, monkeypatch, authorization_state
):
    import src.runners.task41_p0_contract as module

    _, fixture_contract = _write_contract(tmp_path, "B0")
    source_sha = fixture_contract["source"]["sha"]

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(module, "_git", fake_git)
    parent_path = tmp_path / module.TASK41_B0_V3_WINDOW_RELATIVE
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    parent_bytes = b"fixture V3 parent window"
    parent_sha = hashlib.sha256(parent_bytes).hexdigest()
    monkeypatch.setattr(module, "TASK41_B0_V3_WINDOW_SHA256", parent_sha)
    if authorization_state != "missing_parent_file":
        parent_path.write_bytes(parent_bytes)

    if authorization_state != "missing":
        auth = {
            "schema": module.TASK41_B0_V6_AUTH_SCHEMA,
            "authorization": module.TASK41_B0_V6_AUTHORIZATION,
            "source_at_entry": source_sha,
            "parent_window_path": str(module.TASK41_B0_V3_WINDOW_RELATIVE),
            "parent_window_sha256": parent_sha,
            "total_seconds": module.TASK41_B0_V6_TOTAL_SECONDS,
            "numerical_seconds": module.TASK41_B0_V6_NUMERICAL_SECONDS,
            "closeout_seconds": module.TASK41_CLOSEOUT_SECONDS,
        }
        if authorization_state != "missing_preparation_start":
            auth["preparation_started_utc"] = (
                "not-a-utc-timestamp"
                if authorization_state == "invalid_preparation_start"
                else "2026-10-20T10:21:59.261754681Z"
            )
        if authorization_state == "wrong_parent_path":
            auth["parent_window_path"] = str(module.TASK41_B0_WINDOW_RELATIVE)
        elif authorization_state == "wrong_parent_sha":
            auth["parent_window_sha256"] = "0" * 64
        auth_path = tmp_path / module.TASK41_B0_V6_AUTH_RELATIVE
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(auth), encoding="utf-8")

    monkeypatch.setattr(
        module,
        "clock_sample",
        lambda **_kwargs: pytest.fail("authorization rejection must precede any clock sample"),
    )
    window_path = tmp_path / module.TASK41_B0_V6_WINDOW_RELATIVE
    error = (
        "explicit authorization"
        if authorization_state == "missing"
        else "fields are incomplete"
        if authorization_state == "missing_preparation_start"
        else "preparation start must be a canonical UTC timestamp"
        if authorization_state == "invalid_preparation_start"
        else "preserved V3 parent identity"
    )
    with pytest.raises(Task41ContractError, match=error):
        prepare_task41_p0(
            current_root=tmp_path,
            case_id="B0",
            b0_v6_continuation=True,
            runtime_prefix=fixture_contract["runtime"]["runtime_prefix"],
            abi_receipt=fixture_contract["runtime"]["abi_receipt_path"],
            jit_cache=fixture_contract["runtime"]["jit_cache"],
        )
    assert not window_path.exists()


@pytest.mark.parametrize("legacy_receipt", (False, True))
def test_task41_v6_prepare_freezes_once_and_reuses_approved_window(
    tmp_path, monkeypatch, legacy_receipt
):
    import src.runners.task41_p0_contract as module
    from src.runners.task41_p0_contract import launcher_values

    original_contract_path, fixture_contract = _write_contract(tmp_path, "B0")
    original_contract_path.unlink()
    source_sha = fixture_contract["source"]["sha"]

    parent_path = tmp_path / module.TASK41_B0_V3_WINDOW_RELATIVE
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    parent_path.write_bytes(b"fixture V3 parent window")
    parent_sha = hashlib.sha256(parent_path.read_bytes()).hexdigest()
    monkeypatch.setattr(module, "TASK41_B0_V3_WINDOW_SHA256", parent_sha)
    real_clock_sample = module.clock_sample
    frozen_anchor = real_clock_sample(include_boot_id=True)
    preparation_started_ns = int(frozen_anchor["utc_ns"]) - 37_654_321_987
    preparation_started_utc = module._utc_text_from_ns(preparation_started_ns)
    auth = {
        "schema": (
            module.TASK41_B0_V6_AUTH_LEGACY_SCHEMA
            if legacy_receipt
            else module.TASK41_B0_V6_AUTH_SCHEMA
        ),
        "authorization": module.TASK41_B0_V6_AUTHORIZATION,
        "source_at_entry": source_sha,
        "parent_window_path": str(module.TASK41_B0_V3_WINDOW_RELATIVE),
        "parent_window_sha256": parent_sha,
        "total_seconds": module.TASK41_B0_V6_TOTAL_SECONDS,
        "numerical_seconds": module.TASK41_B0_V6_NUMERICAL_SECONDS,
        "closeout_seconds": module.TASK41_CLOSEOUT_SECONDS,
    }
    if not legacy_receipt:
        auth["preparation_started_utc"] = preparation_started_utc
    auth_path = tmp_path / module.TASK41_B0_V6_AUTH_RELATIVE
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(json.dumps(auth), encoding="utf-8")

    git_state = {"sha": source_sha}

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return git_state["sha"]
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(module, "_git", fake_git)
    clock_samples = []

    def counted_clock_sample(*, include_boot_id):
        sample = dict(frozen_anchor)
        clock_samples.append(sample)
        return sample

    monkeypatch.setattr(module, "clock_sample", counted_clock_sample)
    monkeypatch.setattr(
        module,
        "_check_task41_native_receipt",
        lambda receipt_path, *_args: hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        module,
        "verify_task41_b0_saved_surface_donor",
        lambda *_args, **_kwargs: None,
    )
    kwargs = {
        "current_root": tmp_path,
        "case_id": "B0",
        "b0_v6_continuation": True,
        "runtime_prefix": fixture_contract["runtime"]["runtime_prefix"],
        "abi_receipt": fixture_contract["runtime"]["abi_receipt_path"],
        "jit_cache": fixture_contract["runtime"]["jit_cache"],
    }
    result = prepare_task41_p0(**kwargs)
    window_path = tmp_path / result["window_path"]
    frozen_window_bytes = window_path.read_bytes()
    window_payload = json.loads(frozen_window_bytes)
    expected_t0_utc = (
        _utc_z(int(frozen_anchor["utc_ns"]))
        if legacy_receipt
        else preparation_started_utc
    )
    expected_bootstrap_seconds = (
        0.0
        if legacy_receipt
        else (int(frozen_anchor["utc_ns"]) - preparation_started_ns) / 1e9
    )
    assert result["window_t0_utc"] == expected_t0_utc
    assert window_payload["t0_utc"] == expected_t0_utc
    assert window_payload["source_sha"] == source_sha
    assert window_payload["total_seconds"] == 86_400.0
    assert window_payload["numerical_seconds"] == 85_200.0
    assert window_payload["closeout_seconds"] == 1_200.0
    assert window_payload["anchor"] == clock_samples[0]
    assert window_payload["t0_basis"] == {
        "kind": (
            "user_approved_v6_24h_continuation"
            if legacy_receipt
            else module.TASK41_B0_V6_PREPARATION_T0_KIND
        )
    }
    assert window_payload["bootstrap_utc_elapsed_seconds"] == pytest.approx(
        expected_bootstrap_seconds
    )
    assert window_payload["bootstrap_boottime_elapsed_seconds"] is None
    assert window_payload["bootstrap_time_treatment"] == (
        "new_approved_window_anchor_is_t0"
        if legacy_receipt
        else module.TASK41_B0_V6_PREPARATION_BOOTSTRAP_TREATMENT
    )

    contract_path = tmp_path / result["contract_path"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["window"]["path"] == str(module.TASK41_B0_V6_WINDOW_RELATIVE)
    assert contract["window"]["entry_source_sha"] == source_sha
    assert contract["window"]["continuation_authorization_sha256"] == hashlib.sha256(
        auth_path.read_bytes()
    ).hexdigest()
    assert contract["window"]["parent_window_path"] == str(
        module.TASK41_B0_V3_WINDOW_RELATIVE
    )
    assert contract["window"]["parent_window_sha256"] == parent_sha
    assert contract["time"] == {
        "total_seconds": 86_400.0,
        "numerical_seconds": 85_200.0,
        "closeout_seconds": 1_200.0,
    }
    loaded, contract_sha = require_task41_p0_contract(
        contract_path, current_root=tmp_path
    )
    launch = launcher_values(contract_path, current_root=tmp_path)
    assert launch[4] == contract_sha
    assert launch[5] == str(window_path)
    assert launch[6] == hashlib.sha256(frozen_window_bytes).hexdigest()
    assert loaded["window"]["path"] == str(module.TASK41_B0_V6_WINDOW_RELATIVE)

    contract_path.unlink()
    samples_before_reuse = len(clock_samples)
    second_result = prepare_task41_p0(**kwargs)
    assert len(clock_samples) == samples_before_reuse + 1
    assert (tmp_path / second_result["window_path"]).read_bytes() == frozen_window_bytes
    assert second_result["window_t0_utc"] == result["window_t0_utc"]

    (tmp_path / second_result["contract_path"]).unlink()
    source_b_sha = "d" * 40
    git_state["sha"] = source_b_sha
    samples_before_source_b = len(clock_samples)
    source_b_result = prepare_task41_p0(**kwargs)
    assert len(clock_samples) == samples_before_source_b + 1
    assert (tmp_path / source_b_result["window_path"]).read_bytes() == frozen_window_bytes
    assert source_b_result["window_t0_utc"] == result["window_t0_utc"]

    source_b_contract_path = tmp_path / source_b_result["contract_path"]
    source_b_contract = json.loads(source_b_contract_path.read_text(encoding="utf-8"))
    assert source_b_contract["source"]["sha"] == source_b_sha
    assert source_b_contract["window"]["entry_source_sha"] == source_sha
    loaded_source_b, source_b_contract_sha = require_task41_p0_contract(
        source_b_contract_path, current_root=tmp_path
    )
    source_b_launch = launcher_values(source_b_contract_path, current_root=tmp_path)
    assert source_b_launch[4] == source_b_contract_sha
    assert source_b_launch[5] == str(window_path)
    assert source_b_launch[6] == hashlib.sha256(frozen_window_bytes).hexdigest()
    assert loaded_source_b["source"]["sha"] == source_b_sha

    if not legacy_receipt:
        tampered_bootstrap_payload = json.loads(json.dumps(window_payload))
        tampered_bootstrap_payload["bootstrap_utc_elapsed_seconds"] += 1.0
        tampered_bootstrap_bytes = (
            json.dumps(tampered_bootstrap_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        window_path.write_bytes(tampered_bootstrap_bytes)
        tampered_bootstrap_contract = json.loads(json.dumps(source_b_contract))
        tampered_bootstrap_contract["window"]["sha256"] = hashlib.sha256(
            tampered_bootstrap_bytes
        ).hexdigest()
        with pytest.raises(Task41ContractError, match="window clock, approval, or V3 parent changed"):
            load_task41_p0_fixed_window(tampered_bootstrap_contract, current_root=tmp_path)
        window_path.write_bytes(frozen_window_bytes)

    tampered_entry = json.loads(json.dumps(source_b_contract))
    tampered_entry["window"]["entry_source_sha"] = source_b_sha
    with pytest.raises(Task41ContractError, match="approved V3 parent and authorization"):
        module.task41_window_spec(tampered_entry, tmp_path)
    tampered_parent = json.loads(json.dumps(source_b_contract))
    tampered_parent["window"]["parent_window_sha256"] = "0" * 64
    with pytest.raises(Task41ContractError, match="approved V3 parent and authorization"):
        module.task41_window_spec(tampered_parent, tmp_path)


def test_task41_v9_prepare_fails_closed_without_new_user_window_authorization(
    tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as module

    contract_path, fixture_contract = _write_contract(tmp_path, "B0")
    contract_path.unlink()
    source_sha = fixture_contract["source"]["sha"]

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(
        module,
        "clock_sample",
        lambda **_kwargs: pytest.fail("missing V9 authorization must fail before clock sampling"),
    )
    with pytest.raises(Task41ContractError, match="new explicit user authorization"):
        prepare_task41_p0(
            current_root=tmp_path,
            case_id="B0",
            b0_v9_continuation=True,
            runtime_prefix=fixture_contract["runtime"]["runtime_prefix"],
            abi_receipt=fixture_contract["runtime"]["abi_receipt_path"],
            jit_cache=fixture_contract["runtime"]["jit_cache"],
        )
    assert not (tmp_path / module.TASK41_B0_V9_WINDOW_RELATIVE).exists()


def test_task41_v9_prepare_uses_new_window_and_binds_historical_cost_ledger_once(
    tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as module
    from src.runners.task41_p0_contract import launcher_values

    original_contract_path, fixture_contract = _write_contract(tmp_path, "B0")
    original_contract_path.unlink()
    source_sha = fixture_contract["source"]["sha"]
    controller = tmp_path / module.TASK41_B0_CONTROLLER_RELATIVE
    parent_cost_path = controller / "campaign_accounting_v6_24h.jsonl"
    parent_cost_path.write_bytes(b"V6 costs retained; unknown entries remain unknown\n")
    parent_window_path = tmp_path / module.TASK41_B0_V6_WINDOW_RELATIVE
    parent_window_path.write_text(
        json.dumps({"accounting_path": str(parent_cost_path.resolve())}),
        encoding="utf-8",
    )
    parent_window_sha = hashlib.sha256(parent_window_path.read_bytes()).hexdigest()
    monkeypatch.setattr(module, "TASK41_B0_V6_WINDOW_SHA256", parent_window_sha)
    parent_cost_sha = hashlib.sha256(parent_cost_path.read_bytes()).hexdigest()

    frozen_anchor = clock_sample(include_boot_id=True)
    preparation_started_ns = int(frozen_anchor["utc_ns"]) - 7_654_321_000
    preparation_started_utc = module._utc_text_from_ns(preparation_started_ns)
    authorization = {
        "schema": module.TASK41_B0_V9_AUTH_SCHEMA,
        "authorization": module.TASK41_B0_V9_AUTHORIZATION,
        "source_at_entry": source_sha,
        "parent_window_path": str(module.TASK41_B0_V6_WINDOW_RELATIVE),
        "parent_window_sha256": parent_window_sha,
        "parent_cost_ledger_path": str(
            module.TASK41_B0_V6_WINDOW_RELATIVE.parent
            / "campaign_accounting_v6_24h.jsonl"
        ),
        "parent_cost_ledger_sha256": parent_cost_sha,
        "total_seconds": module.TASK41_B0_V9_TOTAL_SECONDS,
        "numerical_seconds": module.TASK41_B0_V9_NUMERICAL_SECONDS,
        "closeout_seconds": module.TASK41_CLOSEOUT_SECONDS,
        "preparation_started_utc": preparation_started_utc,
    }
    authorization_path = tmp_path / module.TASK41_B0_V9_AUTH_RELATIVE
    authorization_path.parent.mkdir(parents=True, exist_ok=True)
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(
        module,
        "clock_sample",
        lambda **_kwargs: dict(frozen_anchor),
    )
    monkeypatch.setattr(
        module,
        "_check_task41_native_receipt",
        lambda receipt_path, *_args: hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        module,
        "verify_task41_b0_saved_surface_donor",
        lambda *_args, **_kwargs: None,
    )
    original_sha256_file = module.sha256_file
    ledger_hash_calls = []

    def counted_sha256_file(path):
        if Path(path).resolve() == parent_cost_path.resolve():
            ledger_hash_calls.append(1)
        return original_sha256_file(path)

    monkeypatch.setattr(module, "sha256_file", counted_sha256_file)
    result = prepare_task41_p0(
        current_root=tmp_path,
        case_id="B0",
        b0_v9_continuation=True,
        runtime_prefix=fixture_contract["runtime"]["runtime_prefix"],
        abi_receipt=fixture_contract["runtime"]["abi_receipt_path"],
        jit_cache=fixture_contract["runtime"]["jit_cache"],
    )
    window_path = tmp_path / result["window_path"]
    window_payload = json.loads(window_path.read_text(encoding="utf-8"))
    assert window_path == tmp_path / module.TASK41_B0_V9_WINDOW_RELATIVE
    assert window_payload["t0_utc"] == preparation_started_utc
    assert window_payload["source_sha"] == source_sha
    assert window_payload["total_seconds"] == 86_400.0
    assert window_payload["numerical_seconds"] == 85_200.0
    assert window_payload["accounting_path"].endswith("campaign_accounting_v9_24h.jsonl")
    assert window_payload["accounting_path"] != str(parent_cost_path.resolve())
    assert window_payload["parent_window_sha256"] == parent_window_sha
    assert window_payload["parent_cost_ledger_sha256"] == parent_cost_sha
    assert ledger_hash_calls == [1]

    contract_path = tmp_path / result["contract_path"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["window"]["path"] == str(module.TASK41_B0_V9_WINDOW_RELATIVE)
    assert contract["window"]["parent_window_path"] == str(
        module.TASK41_B0_V6_WINDOW_RELATIVE
    )
    assert contract["window"]["parent_cost_ledger_sha256"] == parent_cost_sha
    assert contract["numerical_strategy"]["internal_rhs_strategy"] == "same_lu_rhs_solve"
    loaded, contract_sha = require_task41_p0_contract(
        contract_path, current_root=tmp_path
    )
    launch = launcher_values(contract_path, current_root=tmp_path)
    assert launch[4] == contract_sha
    assert launch[5] == str(window_path)
    assert loaded["window"]["path"] == str(module.TASK41_B0_V9_WINDOW_RELATIVE)
    assert ledger_hash_calls == [1]


def test_task41_v6_service_cli_keeps_saved_volume_selector_first(monkeypatch, tmp_path):
    import scripts.task40_v20_service_workflow as workflow

    captured = {}

    def capture_service(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(workflow, "_run_task41_p0_service", capture_service)
    case_args = [
        "--task41-p0-saved-b0-volume-only-attribution",
        "--task41-p0-execution-contract",
        str(tmp_path / "task41-v6-contract.json"),
        "--donor-contract",
        "/evidence/donor-contract.json",
        "--donor-contract-sha256",
        "a" * 64,
        "--summary",
        "/evidence/donor-summary.json",
        "--numerical-output",
        "/evidence/donor-numerical-output.json",
        "--output-dir",
        "/evidence/v6-output",
        "--geometry-policy",
        "mesh_actual_exact",
        "--geometry-reference-report",
        "/evidence/geometry-reference.json",
        "--raw-tensor-evaluator",
        "actual_qmetric_blocked_gram",
        "--ffcx-c-source",
        "/evidence/ffcx-kernel.c",
    ]

    assert workflow.main(
        [
            "run-service",
            "--unit",
            "task41-v6-test.service",
            "--runtime-prefix",
            "/runtime",
            "--abi-receipt",
            "/runtime/abi.json",
            "--jit-cache",
            "/runtime/jit-cache",
            "--",
            *case_args,
        ]
    ) == 0
    assert captured["contract_path"] == (tmp_path / "task41-v6-contract.json").resolve()
    assert captured["case_args"] == case_args[:1] + case_args[3:]
    assert captured["case_args"][0] == "--task41-p0-saved-b0-volume-only-attribution"
    assert len(captured["case_args"]) == 19


def test_task41_v15_full_acceptance_prepare_binds_36h_scope_and_raw_policy(
    tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as module

    original_contract_path, fixture_contract = _write_contract(tmp_path, "B0")
    original_contract_path.unlink()
    source_sha = "a" * 40
    config = module._task41_saved_diagnostics_instance(
        module.TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE
    )

    prior_window_path = tmp_path / config["prior_window_relative"]
    prior_ledger_path = tmp_path / config["prior_ledger_relative"]
    prior_window_path.parent.mkdir(parents=True, exist_ok=True)
    prior_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    prior_ledger_path.write_bytes(b"frozen V14 accounting fixture\n")
    prior_window_path.write_text(
        json.dumps({"accounting_path": str(prior_ledger_path.resolve())}),
        encoding="utf-8",
    )

    preparation_started_ns = int(clock_sample(include_boot_id=True)["utc_ns"])
    preparation_started_utc = module._utc_text_from_ns(preparation_started_ns)
    authorization_payload = {
        "schema": module.TASK41_B0_SAVED_DIAGNOSTICS_AUTH_SCHEMA,
        "authorization": config["authorization"],
        "source_at_entry": source_sha,
        "preparation_started_utc": preparation_started_utc,
        "total_seconds": module.TASK41_B0_V15_FULL_ACCEPTANCE_TOTAL_SECONDS,
        "numerical_seconds": module.TASK41_B0_V15_FULL_ACCEPTANCE_NUMERICAL_SECONDS,
        "closeout_seconds": module.TASK41_CLOSEOUT_SECONDS,
        "scope": config["scope"],
        "prior_window_path": str(config["prior_window_relative"]),
        "prior_window_sha256": hashlib.sha256(prior_window_path.read_bytes()).hexdigest(),
        "prior_ledger_path": str(config["prior_ledger_relative"]),
        "prior_ledger_sha256": hashlib.sha256(prior_ledger_path.read_bytes()).hexdigest(),
    }
    authorization_path = tmp_path / config["authorization_relative"]
    authorization_path.parent.mkdir(parents=True, exist_ok=True)
    authorization_path.write_text(
        json.dumps(authorization_payload, sort_keys=True), encoding="utf-8"
    )

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    anchor = dict(clock_sample(include_boot_id=True))
    anchor["utc_ns"] = preparation_started_ns + 1_000_000_000
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "clock_sample", lambda **_kwargs: dict(anchor))
    monkeypatch.setattr(
        module,
        "_check_task41_native_receipt",
        lambda receipt_path, *_args: hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        module, "verify_task41_b0_saved_surface_donor", lambda *_args, **_kwargs: None
    )

    monkeypatch.setattr(module, "verify_task41_v15_frozen_jit_cache", lambda path: {
        "schema": "task41.v15.frozen_jit_preflight.v1", "jit_cache": str(path),
        "qualified_existing_files": [], "compile_attempted": False,
    })

    prepared = prepare_task41_p0(
        current_root=tmp_path,
        case_id="B0",
        b0_saved_diagnostics_instance=module.TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE,
        runtime_prefix=fixture_contract["runtime"]["runtime_prefix"],
        abi_receipt=fixture_contract["runtime"]["abi_receipt_path"],
        jit_cache=fixture_contract["runtime"]["jit_cache"],
    )

    window_path = tmp_path / prepared["window_path"]
    window = json.loads(window_path.read_text(encoding="utf-8"))
    assert window["source_sha"] == source_sha
    assert window["t0_utc"] == preparation_started_utc
    assert window["total_seconds"] == 129_600.0
    assert window["numerical_seconds"] == 128_400.0
    assert window["closeout_seconds"] == module.TASK41_CLOSEOUT_SECONDS
    assert (tmp_path / config["authorization_relative"]).read_bytes() == (
        authorization_path.read_bytes()
    )

    contract_path = tmp_path / prepared["contract_path"]
    contract, _contract_sha = require_task41_p0_contract(
        contract_path, current_root=tmp_path
    )
    assert prepared["service_command"] == [
        "bash", "scripts/run_case_in_user_service.sh", str(module.TASK41_B0_INPUT_RELATIVE),
        "--task41-p0-execution-contract", prepared["contract_path"],
        "--task41-p0-b0-v15-full-acceptance",
    ]
    assert prepared["saved_diagnostics_output_root"] is None
    assert contract["execution_scope"] == module.TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE
    assert contract["time"] == {
        "total_seconds": 129_600.0,
        "numerical_seconds": 128_400.0,
        "closeout_seconds": module.TASK41_CLOSEOUT_SECONDS,
    }
    assert contract["numerical_strategy"] == {
        "schema": "task41.p0.b0.internal_rhs_strategy.v2",
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "refinement_strategy": module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
    }
    assert contract["evidence"]["raw_disk_policy"] == {
        "scope": "task41_b0_v3_recovery_evidence",
        "raw_artifact_limit_bytes": 16 << 30,
        "free_space_floor_bytes": 2 << 30,
        "authorization": "user_20261019_16gib_evidence_only",
        "new_evidence_limit_bytes": module.TASK41_B0_V15_FULL_ACCEPTANCE_NEW_RAW_BYTES,
        "single_package_limit_bytes": module.TASK41_B0_V15_FULL_ACCEPTANCE_SINGLE_ARTIFACT_BYTES,
        "non_raw_output_reserve_bytes": module.TASK41_B0_V15_FULL_ACCEPTANCE_NON_RAW_RESERVE_BYTES,
        "raw_artifact_accounting": module.TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
            "raw_artifact_accounting"
        ],
        "monitoring_log_accounting": module.TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
            "monitoring_log_accounting"
        ],
        "raw_artifact_roots": module.TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS,
        "success_exit": "acceptance_only",
    }


def test_task41_v15_prepare_requires_existing_user_authorization_without_window_creation(
    tmp_path, monkeypatch
):
    import src.runners.task41_p0_contract as module

    original_contract_path, fixture_contract = _write_contract(tmp_path, "B0")
    original_contract_path.unlink()
    source_sha = fixture_contract["source"]["sha"]

    def fake_git(_root, *args):
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("branch", "--show-current"):
            return TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(
        module,
        "clock_sample",
        lambda **_kwargs: pytest.fail("missing V15 authorization must fail before T0 sampling"),
    )
    monkeypatch.setattr(
        module, "verify_task41_b0_saved_surface_donor", lambda *_args, **_kwargs: None
    )

    config = module._task41_saved_diagnostics_instance(
        module.TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE
    )
    with pytest.raises(Task41ContractError, match="requires an existing explicit user authorization"):
        prepare_task41_p0(
            current_root=tmp_path,
            case_id="B0",
            b0_saved_diagnostics_instance=module.TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE,
            runtime_prefix=fixture_contract["runtime"]["runtime_prefix"],
            abi_receipt=fixture_contract["runtime"]["abi_receipt_path"],
            jit_cache=fixture_contract["runtime"]["jit_cache"],
        )
    assert not (tmp_path / config["authorization_relative"]).exists()
    assert not (tmp_path / config["window_relative"]).exists()


def test_task41_v15_service_selector_is_consumed_and_requires_its_contract(
    monkeypatch, tmp_path
):
    import scripts.task40_v20_service_workflow as workflow

    captured = {}
    monkeypatch.setattr(
        workflow,
        "_run_task41_p0_service",
        lambda **kwargs: captured.update(kwargs) or 0,
    )
    contract_path = tmp_path / "v15-contract.json"
    input_path = tmp_path / "case.dat"
    args = [
        str(input_path),
        "--task41-p0-b0-v15-full-acceptance",
        "--task41-p0-execution-contract",
        str(contract_path),
    ]
    assert workflow.run_service(
        unit="task41-v15-selector-test.service",
        runtime_prefix=tmp_path / ".venv",
        abi_receipt=tmp_path / "abi.json",
        jit_cache=tmp_path / "jit",
        case_args=args,
        repo_root=tmp_path,
    ) == 0
    assert captured["case_args"] == [str(input_path)]
    assert captured["v15_full_acceptance_selector"] is True
    assert captured["contract_path"] == contract_path

    with pytest.raises(ValueError, match="requires its Task41 P0 execution contract"):
        workflow.run_service(
            unit="task41-v15-selector-without-contract.service",
            runtime_prefix=tmp_path / ".venv",
            abi_receipt=tmp_path / "abi.json",
            jit_cache=tmp_path / "jit",
            case_args=[str(input_path), "--task41-p0-b0-v15-full-acceptance"],
            repo_root=tmp_path,
        )

    with pytest.raises(ValueError, match="may appear only once"):
        workflow.run_service(
            unit="task41-v15-duplicate-selector.service",
            runtime_prefix=tmp_path / ".venv",
            abi_receipt=tmp_path / "abi.json",
            jit_cache=tmp_path / "jit",
            case_args=[
                str(input_path),
                "--task41-p0-b0-v15-full-acceptance",
                "--task41-p0-b0-v15-full-acceptance",
                "--task41-p0-execution-contract",
                str(contract_path),
            ],
            repo_root=tmp_path,
        )


def test_task41_v15_output_binding_propagates_the_actual_allocated_path(
    tmp_path
):
    from src.io.input_loader import InputError
    from src.runners.task038_launcher import _bind_task41_v15_output_directory

    allocated = tmp_path / "results" / TASK41_MODEL_ID / "attempt-from-launcher"
    allocated.mkdir(parents=True)
    process_environment = {"TASK41_P0_V15_FULL_ACCEPTANCE": "1"}
    actual = _bind_task41_v15_output_directory(
        allocated, environment=process_environment
    )
    assert actual == str(allocated.resolve())
    assert process_environment["TASK41_P0_V15_OUTPUT_DIRECTORY"] == actual

    worker_environment = {"TASK41_P0_V15_FULL_ACCEPTANCE": "1"}
    assert _bind_task41_v15_output_directory(
        allocated, environment=worker_environment
    ) == actual
    assert worker_environment["TASK41_P0_V15_OUTPUT_DIRECTORY"] == actual

    wrong_environment = {
        "TASK41_P0_V15_FULL_ACCEPTANCE": "1",
        "TASK41_P0_V15_OUTPUT_DIRECTORY": str(tmp_path / "wrong-output"),
    }
    with pytest.raises(InputError, match="does not resolve"):
        _bind_task41_v15_output_directory(allocated, environment=wrong_environment)
    with pytest.raises(InputError, match="exact service selector"):
        _bind_task41_v15_output_directory(allocated, environment={})

@pytest.mark.parametrize("product", ["compact", "partial", "absent"])
def test_task41_v15_prepared_contract_authorizes_actual_terminal_watchdog_without_physical_output(tmp_path, monkeypatch, product):
    import benchmarks.subreaper_watchdog as watchdog
    import src.runners.task41_p0_contract as module

    test_task41_v15_full_acceptance_prepare_binds_36h_scope_and_raw_policy(tmp_path, monkeypatch)
    paths = list((tmp_path / module.TASK41_B0_CONTROLLER_RELATIVE).glob(
        "execution_contract_source_*_v15_full_two_column_acceptance_36h.json"))
    assert len(paths) == 1
    contract_path = paths[0]
    contract, digest = module.require_task41_p0_contract(contract_path, current_root=tmp_path)
    run_root = tmp_path / "results" / module.TASK41_MODEL_ID / "launcher-allocated-fixture"
    run_root.mkdir(parents=True)
    summary = run_root / "task40_v10_p6_candidate_summary.json"
    manifest = run_root / "run_manifest.json"
    summary.write_text('{}\n')
    manifest.write_text('{}\n')
    inputs = [summary, manifest]
    if product != "absent":
        record = run_root / ("task41_p0_b0_v9_compact_volume_audit.json" if product == "compact"
                             else "task41_p0_b0_v15_terminal_sufficient_checkpoint.json")
        record.write_text('{}\n')
        inputs.append(record)
    output = tmp_path / contract["evidence"]["service_directory"] / "task41_p0_checker_result.json"
    python = Path(contract["runtime"]["runtime_prefix"]) / "bin/python"
    command = [str(python), "-m", "src.runners.task41_p0_checker", "--v15-terminal-audit",
               "--run-root", str(run_root), "--summary", str(summary), "--manifest", str(manifest),
               "--contract", str(contract_path), "--contract-sha256", digest, "--output", str(output)]
    environment = {"TASK41_P0_STRICT_EXECUTION": "1", "TASK41_P0_CONTRACT_PATH": str(contract_path),
                   "TASK41_P0_CONTRACT_SHA256": digest, "TASK41_P0_V15_FULL_ACCEPTANCE": "1"}
    window = SimpleNamespace(path=tmp_path / contract["window"]["path"], sha256=contract["window"]["sha256"])
    auth = {"schema": module.TASK41_P0_AUTH_SCHEMA, "phase": "closeout",
            "purpose": "registered_read_only_required_checker", "checker_kind": "task41_p0_b0_v15_terminal_checker",
            "command_sha256": hashlib.sha256(json.dumps(command, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
            "input_paths": [str(p) for p in inputs], "input_sha256s": [module.sha256_file(p) for p in inputs],
            "expected_channel_count": None, "campaign_window_sha256": window.sha256,
            "task41_contract_sha256": digest, "source_sha": contract["source"]["sha"],
            "source_branch": module.TASK41_BRANCH, "source_clean": True}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(watchdog.sys, "executable", str(python))
    def fake_git(command, **kwargs):
        value = {('git','rev-parse','HEAD'): contract['source']['sha'],
                 ('git','branch','--show-current'): module.TASK41_BRANCH,
                 ('git','status','--porcelain','--untracked-files=normal'): ''}[tuple(command)]
        return SimpleNamespace(returncode=0, stdout=value+'\n', stderr='')
    monkeypatch.setattr(watchdog.subprocess, "run", fake_git)
    assert watchdog._validate_campaign_closeout_authorization(
        command=command, campaign=window, authorization=auth, worker_environment=environment) == auth
    assert not (run_root / "numerical_output").exists()
    wrong = dict(environment, TASK41_P0_V15_FULL_ACCEPTANCE="0")
    with pytest.raises(ValueError, match="exact full-acceptance"):
        watchdog._validate_campaign_closeout_authorization(
            command=command, campaign=window, authorization=auth, worker_environment=wrong)
    inputs[0].write_text('{"changed":true}\n')
    with pytest.raises(ValueError):
        watchdog._validate_campaign_closeout_authorization(
            command=command, campaign=window, authorization=auth, worker_environment=environment)


def test_task41_v15_raw_inventory_counts_later_unique_backings_without_carrier(tmp_path, monkeypatch):
    import os
    import src.runners.task41_p0_contract as module
    from src.runners.task40_v10_worker import _task41_v15_existing_raw_inventory
    root = tmp_path / "results" / module.TASK41_MODEL_ID
    for name in module.TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS:
        (root / name).mkdir(parents=True)
    a = root / module.TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS[0] / "a.npy"
    a.write_bytes(b'abc')
    os.link(a, root / module.TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS[1] / "alias.npy")
    (root / "unrelated_carrier.npy").write_bytes(b'not in authorized scope')
    report = _task41_v15_existing_raw_inventory(tmp_path, frozen_through_v7_bytes=100)
    assert report['cumulative_bytes'] == 103
    assert sum(item['npy_count'] for item in report['roots']) == 1


@pytest.mark.parametrize("failure", (None, "numerical", "cleanup", "swap", "descendants", "missing_resource"))
def test_task41_v15_terminal_service_separates_numerical_and_resource_results(failure):
    from scripts.task40_v20_service_workflow import _task41_v15_terminal_decision

    authority = {
        "classification": "COMPLETED", "leader_exit_code": 0,
        "descendants_cleared": True, "remaining_child_pids": [],
        "process_tree_swap_gate_enforced": True, "sampled_process_tree_swap_peak_bytes": 0,
        "job_cgroup_swap_gate_enforced": True, "job_cgroup_swap": {"passed": True},
    }
    payload = {
        "audit_completed": True, "data_integrity": True, "official_result": False,
        "action_passed": True, "recovery_passed": True, "acceptance_qualified": True,
    }
    if failure == "numerical":
        payload.update(action_passed=False, recovery_passed=None, acceptance_qualified=False)
    elif failure == "cleanup":
        payload["acceptance_qualified"] = False
    elif failure == "swap":
        authority["sampled_process_tree_swap_peak_bytes"] = 4096
    elif failure == "descendants":
        authority.update(descendants_cleared=False, remaining_child_pids=[123])
    elif failure == "missing_resource":
        authority.pop("job_cgroup_swap_gate_enforced")
    result = _task41_v15_terminal_decision(authority, payload)
    assert result["acceptance_qualified"] is (failure is None)
    assert result["audit_completed"] is (failure in (None, "numerical", "cleanup"))
    assert result["official_result"] is False
    if failure == "numerical":
        assert result["result_classification"] == "SUPERVISED_NUMERICAL_FAIL"
    if failure == "cleanup":
        assert result["result_classification"] == "SUPERVISED_RESOURCE_OR_CLEANUP_FAILURE"


def test_task41_v15_frozen_jit_preflight_rejects_new_compile_and_missing_module(tmp_path, monkeypatch):
    import src.runners.task41_p0_contract as module
    import src.solvers.task41_actual_qmetric_blocked_gram as evaluator
    cache = tmp_path / "jit"
    directory = cache / "fenics"
    directory.mkdir(parents=True)
    stem = "libffcx_forms_2f92c03a20c09db3cb8f0382bec2294daa94ab16"
    with pytest.raises(Task41ContractError, match="no compile fallback"):
        module.verify_task41_v15_frozen_jit_cache(cache)
    for suffix, constant in ((".c", "EXPECTED_C_SOURCE_SHA256"),
                             (".c.cached", "EXPECTED_C_CACHE_SHA256"),
                             (".test.so", "EXPECTED_UFCX_MODULE_SHA256")):
        raw = ("qualified" + suffix).encode()
        (directory / (stem + suffix)).write_bytes(raw)
        monkeypatch.setattr(evaluator, constant, hashlib.sha256(raw).hexdigest())
    result = module.verify_task41_v15_frozen_jit_cache(cache)
    assert result["compile_attempted"] is False
    assert len(result["qualified_existing_files"]) == 3
    (directory / (stem + ".test.so")).write_bytes(b"unqualified rebuild")
    with pytest.raises(Task41ContractError, match="module hash differs"):
        module.verify_task41_v15_frozen_jit_cache(cache)


def _v15_retry_fixture(root, window_path, accounting_path):
    from src.runners.task41_p0_contract import TASK41_V15_RETRY_AUTH_RELATIVE
    old_run = root / "results" / TASK41_MODEL_ID / "failed-jit-run"
    old_run.mkdir(parents=True)
    summary = old_run / "task40_v10_p6_candidate_summary.json"
    summary.write_text(json.dumps({"source_sha": "c" * 40, "status": "FAILED",
        "error": {"message": "compiled FFCx module hash differs from frozen V6 profile"},
        "v15_cleanup": {"completed": True, "passed": True, "errors": []}}))
    old_claim = accounting_path.with_name(accounting_path.name + ".v15_full_owner_claim.json")
    old_claim.parent.mkdir(parents=True, exist_ok=True)
    old_claim.write_text(json.dumps({"status": "BUILD_STARTED", "full_owner_build_count": 1,
        "source_sha": "c" * 40, "window_sha256": hashlib.sha256(window_path.read_bytes()).hexdigest(),
        "output_directory": str(old_run)}))
    original_bytes = old_claim.read_bytes()
    auth = root / TASK41_V15_RETRY_AUTH_RELATIVE
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text(json.dumps({
        "schema": "task41.v15.one_additional_build_authorization.v1",
        "user_decision": "APPROVED", "approved_utc": "2026-10-25T22:49:00Z",
        "additional_builds": 1, "retry_sequence": 1, "success_exit": "acceptance_only",
        "fixed_window_unchanged": True, "window_path": str(window_path),
        "window_sha256": hashlib.sha256(window_path.read_bytes()).hexdigest(),
        "previous_claim_path": str(old_claim),
        "previous_claim_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "failed_run_directory": str(old_run),
        "failed_summary_sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
    }))
    return {"path": str(TASK41_V15_RETRY_AUTH_RELATIVE),
            "sha256": hashlib.sha256(auth.read_bytes()).hexdigest()}, old_claim, original_bytes


def test_task41_v15_authorized_retry_preserves_old_claim_and_is_single_use(tmp_path):
    from types import SimpleNamespace
    from src.runners.task41_p0_contract import (
        TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE, TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE,
        task41_v15_owner_claim_authority, Task41ContractError,
    )
    from src.runners.task40_v10_worker import _task41_b0_build_v15_full_owner_once
    window = tmp_path / TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE
    window.parent.mkdir(parents=True); window.write_text('{"fixture":"unchanged-window"}')
    accounting = window.parent / "accounting.jsonl"
    binding, old, old_bytes = _v15_retry_fixture(tmp_path, window, accounting)
    args = dict(root=tmp_path, accounting_path=accounting, window_path=window,
                window_sha256=hashlib.sha256(window.read_bytes()).hexdigest(), retry_binding=binding)
    quota = task41_v15_owner_claim_authority(**args)
    with pytest.raises(Task41ContractError, match="path/hash"):
        task41_v15_owner_claim_authority(**dict(args, retry_binding=dict(binding, sha256="0"*64)))
    with pytest.raises(Task41ContractError, match="claim/window"):
        task41_v15_owner_claim_authority(**dict(args, window_sha256="0"*64))
    old.write_bytes(old_bytes + b" ")
    with pytest.raises(Task41ContractError, match="claim/window"):
        task41_v15_owner_claim_authority(**args)
    old.write_bytes(old_bytes)
    output = tmp_path / "results" / TASK41_MODEL_ID / "retry-run"; output.mkdir()
    authority = {"execution_scope": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
        "campaign_window_path": str(window), "campaign_window_sha256": args["window_sha256"],
        "campaign_accounting_path": str(accounting), "full_owner_quota_claim_path": quota["claim_path"],
        "full_owner_retry_authorization": binding, "full_owner_quota_scope": "fixed_window_across_attempts",
        "model_id": TASK41_MODEL_ID, "run_directory": str(output),
        "task41_contract_path": str(tmp_path / "contract.json"), "task41_contract_sha256": "a"*64,
        "source_sha": "b"*40, "input_sha256": "c"*64}
    generation = object()
    owner = {"condensed": SimpleNamespace(
        actual_internal_matrix_identity_by_class={0:generation},
        interior_lu_matrix_identity_by_class={0:generation},
        retained_actual_internal_matrix_by_class={0:object()}, interior_lu_by_class={0:object()})}
    _, claim = _task41_b0_build_v15_full_owner_once(authority, run_directory=output,
        owner_builder=lambda:owner, current_root=tmp_path)
    assert claim["status"] == "BUILD_COMPLETED" and claim["full_owner_build_count"] == 2
    assert claim["full_owner_retry_authorization"] == binding
    assert old.read_bytes() == old_bytes
    other = output.with_name("renamed-attempt"); other.mkdir()
    with pytest.raises(ValueError, match="already consumed"):
        _task41_b0_build_v15_full_owner_once(dict(authority,run_directory=str(other)),
            run_directory=other,owner_builder=lambda:owner,current_root=tmp_path)
    assert old.read_bytes() == old_bytes


def test_task41_v15_actual_allocation_callback_reports_time_stop_before_memory_branch():
    """Execute the real nested callback, with only its expensive runtime replaced."""
    import ast
    import textwrap
    from types import SimpleNamespace
    import numpy as np
    import src.runners.task40_v10_worker as worker
    from src.runners.physical_p4_schur_v14 import V14ResourceStop

    tree = ast.parse(Path(worker.__file__).read_text())
    outer = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "run_task40_v10_p6_reference_worker")
    callback = next(n for n in ast.walk(outer) if isinstance(n, ast.FunctionDef)
                    and n.name == "allocation_gate")
    events, summary = [], {}
    runtime = SimpleNamespace(workflow_reserved_seconds=97244.77301950839,
        workflow_clock_interval=lambda: {"budget_seconds": 0.0},
        marker=lambda name, facts: events.append((name, facts)))
    namespace = {"np":np, "Mapping":dict, "Any":object,
                 "resource_stop":V14ResourceStop, "test_runtime":runtime,
                 "test_summary":summary}
    source = ("def make_callback():\n"
              "    allocation_gate_invocation_count = 0\n"
              "    V14ResourceStop = resource_stop\n"
              "    task41_v15_acceptance_only = True\n"
              "    runtime = test_runtime\n"
              "    summary = test_summary\n"
              + textwrap.indent(ast.unparse(callback), "    ")
              + "\n    return allocation_gate\n")
    exec(compile(source, worker.__file__, "exec"), namespace)
    gate = namespace["make_callback"]()
    facts = {"projected_remaining_class_build_seconds_upper":171107.65433076024,
             "measured_prefix_cache_misses":8, "prefix_records":[{"fixture":True}]}
    with pytest.raises(V14ResourceStop) as stopped:
        gate("mesh_actual_exact_full_admission", facts)
    assert stopped.value.classification == "TIME_ADMISSION_CONTROLLED_STOP"
    record = summary["v15_build_and_acceptance_time_admission"]
    assert record["total_projected_seconds"] == pytest.approx(206003.65433076024)
    assert record["remaining_numerical_seconds"] == 97244.77301950839
    assert record["measured_prefix"]["prefix_records"] == facts["prefix_records"]
    assert events[-1][0] == "task41_v15_build_and_acceptance_time_admission"
