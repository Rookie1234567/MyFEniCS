from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pytest

from src.runners.task41_p0_saved_output_continuation import (
    _link_saved_output,
    _require_service_envelope,
    _validate_original_attempt,
    _validate_original_solver_identity,
    _verify_linked_output_manifest,
    task41_diagnostic_diffraction_inventory,
    validate_saved_a6_packet,
    check_task41_p0_saved_output_continuation,
)
from src.runners.task41_p0_checker import _task41_a2_diagnostic_inventory_from_data
from src.runners import task41_p0_contract
from src.runners.task40_v10_campaign import FixedCampaignWindow
from src.runners.workflow_timebase import clock_sample
from scripts.task40_v20_service_workflow import (
    _run_task41_p0_saved_output_service,
    _task41_p0_checker_only_snapshot_identity,
    _run_task41_p0_service,
)


def _write_a6_packet(path: Path, *, stored_native_relative: float | None = None) -> None:
    rhs = np.asarray([2.0 + 0j, 1.0 + 0j, -3.0 + 0j], dtype=np.complex128)
    solution = np.asarray([1.0 + 2j, -0.5j, 0.25 + 0j], dtype=np.complex128)
    target_residual = np.asarray([1.0e-8, -2.0e-8, 0.5e-8], dtype=np.complex128)
    native_residual = np.asarray([-1.5e-8, 0.5e-8, 1.0e-8], dtype=np.complex128)
    values = {
        "full_physical_rhs_storage": rhs,
        "full_solution_storage": solution,
        "target_backend_applied_storage": rhs - target_residual,
        "target_backend_residual_storage": target_residual,
        "native_witness_applied_storage": rhs - native_residual,
        "native_witness_residual_storage": native_residual,
    }
    npz_path = path.with_suffix(".npz")
    names = {name: f"array_{index}" for index, name in enumerate(values)}
    np.savez(npz_path, **{names[name]: value for name, value in values.items()})
    rhs_norm = float(np.linalg.norm(rhs))
    target_relative = float(np.linalg.norm(target_residual) / rhs_norm)
    native_relative = float(np.linalg.norm(native_residual) / rhs_norm)
    record = {
        "schema": "task40extra.review_v10_b0_candidate_independent_A6_residual.v1",
        "limit": 1.0e-6,
        "identity": {
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        },
        "arrays": {"path": str(npz_path), "sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest()},
        "relative_residual": target_relative,
        "native_witness_relative_residual": (
            native_relative if stored_native_relative is None else stored_native_relative
        ),
    }
    for name, value in values.items():
        record[name] = {
            "array_key": names[name],
            "dtype": str(value.dtype),
            "shape": list(value.shape),
        }
    path.write_text(json.dumps(record), encoding="utf-8")


def test_saved_a6_packet_recomputes_target_and_native_residuals(tmp_path: Path) -> None:
    packet_path = tmp_path / "pre_release.json"
    _write_a6_packet(packet_path)

    solution, facts = validate_saved_a6_packet(
        packet_path,
        run_root=tmp_path,
        expected_source_sha="a" * 40,
        expected_input_sha256="b" * 64,
        expected_physical_model_sha256="c" * 64,
    )

    assert solution.shape == (3,)
    assert facts["packet_json_sha256"] == hashlib.sha256(packet_path.read_bytes()).hexdigest()
    assert all(row["passed"] for row in facts["residual_checks"])


def test_saved_a6_packet_rejects_changed_stored_native_residual(tmp_path: Path) -> None:
    packet_path = tmp_path / "post_release.json"
    _write_a6_packet(packet_path, stored_native_relative=0.0)

    with pytest.raises(ValueError, match="does not independently pass"):
        validate_saved_a6_packet(
            packet_path,
            run_root=tmp_path,
            expected_source_sha="a" * 40,
            expected_input_sha256="b" * 64,
            expected_physical_model_sha256="c" * 64,
        )


def test_continuation_hardlinks_preserve_saved_output_bytes(tmp_path: Path) -> None:
    source = tmp_path / "original" / "numerical_output"
    source.mkdir(parents=True)
    (source / "field.bin").write_bytes(b"saved field")
    (source / "orders.json").write_text('{"orders": []}\n', encoding="utf-8")
    nested_source = source / "E_3d_numerical.bp" / "part.0"
    nested_source.mkdir(parents=True)
    (nested_source / "mesh.bin").write_bytes(b"saved mesh")
    (source / "empty.bp").mkdir()
    destination = tmp_path / "continuation" / "numerical_output"

    manifest = _link_saved_output(source, destination)

    assert [row["name"] for row in manifest] == [
        "E_3d_numerical.bp/part.0/mesh.bin",
        "field.bin",
        "orders.json",
    ]
    assert all(row["same_inode"] for row in manifest)
    assert (destination / "field.bin").read_bytes() == (source / "field.bin").read_bytes()
    assert (destination / "E_3d_numerical.bp" / "part.0" / "mesh.bin").stat().st_ino == (
        nested_source / "mesh.bin"
    ).stat().st_ino
    assert (destination / "empty.bp").is_dir()
    verification = _verify_linked_output_manifest(
        {"numerical_output_path": str(source)},
        {
            "numerical_output_directory": str(destination),
            "numerical_output_manifest": manifest,
        },
    )
    assert verification["passed"] is True


def test_saved_output_hardlink_rejects_nested_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "original" / "numerical_output"
    nested = source / "E_3d_numerical.bp"
    nested.mkdir(parents=True)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside the producer output")
    (nested / "linked.bin").symlink_to(outside)

    with pytest.raises(ValueError, match="contains a symlink"):
        _link_saved_output(source, tmp_path / "continuation" / "numerical_output")


def test_saved_output_checker_wrapper_passes_keyword_only_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.runners.task41_p0_saved_output_continuation as continuation

    snapshot = tmp_path / "task41_p0_saved_output_checker_input.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    expected_result = tmp_path / "retry" / "task41_p0_saved_output_checker_result.json"
    calls: list[dict[str, object]] = []

    def keyword_only_checker(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"checker_passed": True}

    monkeypatch.setattr(continuation, "_check_comparison_outputs", keyword_only_checker)

    result = check_task41_p0_saved_output_continuation(
        snapshot,
        contract_path=tmp_path / "contract.json",
        contract_sha256="f" * 64,
        repo_root=tmp_path,
        result_path=expected_result,
    )

    assert result == {"checker_passed": True}
    assert len(calls) == 1
    assert calls[0]["receipt_path"] == snapshot.resolve()
    assert calls[0]["result_path"] == expected_result


def test_checker_only_service_reuses_authorized_snapshot_and_skips_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.task40_v20_service_workflow as service_workflow
    import src.runners.task41_p0_contract as contract_module
    import src.runners.task40_v10_campaign as campaign_module
    import benchmarks.subreaper_watchdog as watchdog_module
    import benchmarks.task034_wsl_resources as resource_module

    repo_root = tmp_path
    results_root = repo_root / "results" / "model"
    producer_run = results_root / "producer_run"
    snapshot_directory = results_root / "saved_output_attempt7_consumer_retry3"
    producer_run.mkdir(parents=True)
    snapshot_directory.mkdir(parents=True)
    input_path = repo_root / "task41.dat"
    input_path.write_bytes(b"fixed Task41 fixture input\n")
    contract_path = repo_root / "contract.json"
    contract_path.write_text("{}\n", encoding="utf-8")
    contract_sha = "f" * 64
    window_sha = "e" * 64
    abi_sha = "d" * 64
    producer_sha = "a" * 40
    consumer_sha = "b" * 40
    checker_sha = "c" * 40
    branch = "task41extra_phi90_p50x50_g17x20"
    snapshot_path = snapshot_directory / "task41_p0_saved_output_checker_input.json"
    snapshot_payload = {
        "schema": "task41.p0.saved_output_continuation.v1",
        "status": "OUTPUTS_READY",
        "producer": {
            "source_sha": producer_sha,
            "run_directory": str(producer_run),
        },
        "consumer": {
            "source_sha": consumer_sha,
            "run_directory": str(snapshot_directory),
        },
    }
    snapshot_path.write_text(json.dumps(snapshot_payload), encoding="utf-8")
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot_sha = hashlib.sha256(snapshot_bytes).hexdigest()
    old_receipt_path = snapshot_directory / "task41_p0_saved_output_continuation_receipt.json"
    old_receipt_path.write_bytes(b'{"status":"FAILED_RAW_EVIDENCE_RETAINED"}\n')
    old_receipt_bytes = old_receipt_path.read_bytes()
    output_root = results_root / "saved_output_attempt7_checker_retry1"
    window = FixedCampaignWindow(
        path=repo_root / "execution_window.json",
        sha256=window_sha,
        payload={"accounting_path": str(repo_root / "window_accounting.jsonl")},
        anchor={},
        t0_utc_ns=100,
        deadline_utc_ns=1_800_000_000_100,
        total_seconds=1800.0,
        bootstrap_seconds=0.0,
        closeout_seconds=600.0,
    )
    contract = {
        "task_id": "task41-p0",
        "branch": branch,
        "source": {"sha": producer_sha},
        "window": {"path": str(window.path), "sha256": window_sha},
        "case": {
            "model_id": "model",
            "run_id": "task41extra_g13_p6_phi90_iterative_a2",
            "input_path": str(input_path),
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        },
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": sys.prefix,
            "abi_receipt_path": str(repo_root / "abi.json"),
            "jit_cache": str(repo_root / "jit"),
            "abi_receipt_sha256": abi_sha,
        },
    }
    environment = {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
    }
    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(contract_path.resolve()))
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", contract_sha)
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_PATH", str(window.path))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_SHA256", window_sha)
    monkeypatch.setenv("TASK41_P0_EXPECTED_SOURCE_SHA", producer_sha)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_supervise(
        command: list[str], _directory: Path, **kwargs: object
    ) -> dict[str, object]:
        calls.append((command, kwargs))
        assert kwargs["campaign_phase"] == "closeout"
        assert kwargs["campaign_window_path"] == window.path
        assert kwargs["campaign_window_sha256"] == window_sha
        assert command[command.index("--saved-output-continuation-input") + 1] == str(snapshot_path)
        assert command[command.index("--output") + 1] == str(
            output_root / "task41_p0_saved_output_checker_result.json"
        )
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "checker_passed": True,
                    "producer_source_sha": producer_sha,
                    "consumer_source_sha": consumer_sha,
                    "checker_source_sha": checker_sha,
                    "checker_input_snapshot_sha256": snapshot_sha,
                }
            ),
            encoding="utf-8",
        )
        authorization = kwargs["campaign_phase_authorization"]
        assert authorization["source_sha"] == checker_sha
        assert authorization["input_paths"] == [str(snapshot_path)]
        assert authorization["input_sha256s"] == [snapshot_sha]
        watchdog_module._validate_campaign_closeout_authorization(
            command=command,
            campaign=window,
            authorization=authorization,
            worker_environment=kwargs["worker_environment"],
        )
        return {"classification": "COMPLETED", "leader_exit_code": 0}

    monkeypatch.setattr(
        contract_module,
        "require_task41_p0_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        contract_module,
        "load_task41_p0_fixed_window",
        lambda *_args, **_kwargs: window,
    )
    monkeypatch.setattr(
        contract_module, "task41_case_id_for_run_id", lambda _run_id: "A2"
    )
    monkeypatch.setattr(
        contract_module,
        "sha256_file",
        lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    )

    class FakeCampaignAccount:
        def __init__(self, _window: FixedCampaignWindow) -> None:
            pass

        def record_sample(self, *, label: str, phase: str) -> dict[str, str]:
            return {"label": label, "phase": phase, "window_sha256": window_sha}

    monkeypatch.setattr(campaign_module, "CampaignAccount", FakeCampaignAccount)
    monkeypatch.setattr(
        resource_module,
        "cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_limit_bytes": 1 << 30,
            "swap_current_bytes": 0,
            "memory_current_bytes": 1 << 20,
        },
    )
    monkeypatch.setattr(watchdog_module, "supervise", fake_supervise)
    monkeypatch.setattr(service_workflow, "_activation_environment", lambda *_a, **_k: (environment.copy(), ["activate"], 0, ""))
    monkeypatch.setattr(service_workflow, "_qualified_activation_identity", lambda _env: "task41-p0-test-abi")
    monkeypatch.setattr(
        service_workflow,
        "_abi_preflight",
        lambda *_args, **_kwargs: (
            ["python", "preflight"],
            0,
            json.dumps({"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1}),
            "",
        ),
    )
    monkeypatch.setattr(
        service_workflow.subprocess,
        "check_output",
        lambda command, **_kwargs: (
            branch + "\n" if command[-1] == "--show-current" else checker_sha + "\n"
        ),
    )
    def fake_git_run(command: list[str], **_kwargs: object) -> object:
        if command[1] == "merge-base":
            return type("GitResult", (), {"returncode": 0, "stdout": ""})()
        if command[1] == "rev-parse":
            return type("GitResult", (), {"returncode": 0, "stdout": checker_sha + "\n"})()
        if command[1] == "branch":
            return type("GitResult", (), {"returncode": 0, "stdout": branch + "\n"})()
        if command[1] == "status":
            return type("GitResult", (), {"returncode": 0, "stdout": ""})()
        raise AssertionError(f"unexpected Git command: {command}")

    monkeypatch.setattr(service_workflow.subprocess, "run", fake_git_run)
    monkeypatch.chdir(repo_root)

    with pytest.raises(ValueError, match="snapshot path/hash"):
        _task41_p0_checker_only_snapshot_identity(
            snapshot_path=snapshot_path,
            expected_sha256="0" * 64,
            contract=contract,
            checker_source_sha=checker_sha,
            repo_root=repo_root,
            sha256_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    result = _run_task41_p0_service(
        unit="task41-checker-only-test",
        runtime_prefix=Path(sys.prefix),
        abi_receipt=repo_root / "abi.json",
        jit_cache=repo_root / "jit",
        case_args=[
            "--task41-p0-saved-output-checker-only",
            "--checker-input",
            str(snapshot_path),
            "--checker-input-sha256",
            snapshot_sha,
            "--output-dir",
            str(output_root),
        ],
        contract_path=contract_path,
        repo_root=repo_root,
    )

    assert result == 0
    assert len(calls) == 1
    assert calls[0][1]["campaign_phase"] == "closeout"
    service_directory = output_root.with_name(output_root.name + ".service")
    service_receipt = json.loads(
        (service_directory / "task41_p0_service_receipt.json").read_text(encoding="utf-8")
    )
    assert service_receipt["status"] == "completed"
    assert service_receipt["mode"] == "checker_only"
    assert service_receipt["continuation_status"] == "outputs_ready_reused"
    assert "continuation_watchdog" not in service_receipt
    assert service_receipt["producer_source_sha"] == producer_sha
    assert service_receipt["consumer_source_sha"] == consumer_sha
    assert service_receipt["checker_source_sha"] == checker_sha
    assert service_receipt["required_checker_source_sha"] == checker_sha
    assert service_receipt["checker_input_snapshot_sha256"] == snapshot_sha
    assert not (snapshot_directory / "task41_p0_saved_output_checker_result.json").exists()
    assert snapshot_path.read_bytes() == snapshot_bytes
    assert old_receipt_path.read_bytes() == old_receipt_bytes


def test_service_binding_keeps_producer_contract_and_consumer_activation_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_sha = "f" * 64
    window_sha = "e" * 64
    abi_sha = "d" * 64
    producer_sha = "a" * 40
    consumer_sha = "b" * 40
    branch = "task41extra_phi90_p50x50_g17x20"
    contract_path = (tmp_path / "producer_contract.json").resolve()
    window_path = (tmp_path / "fixed_window.json").resolve()
    contract = {
        "branch": branch,
        "source": {"sha": producer_sha},
        "window": {"path": str(window_path), "sha256": window_sha},
        "resources": {"task_memory_max_bytes": 4096, "host_reserve_bytes": 1024},
        "runtime": {
            "runtime_prefix": str(Path(sys.executable).resolve().parents[1]),
            "abi_receipt_sha256": abi_sha,
        },
    }
    env = {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_EXECUTION_WINDOW_PATH": str(window_path),
        "TASK41_P0_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK41_P0_MEMORY_SWAP_MAX_BYTES": "0",
        "TASK41_P0_TASK_MEMORY_MAX_BYTES": "4096",
        "TASK41_P0_HOST_RESERVE_BYTES": "1024",
        "TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1",
        "TASK41_P0_CONSUMER_SOURCE_SHA": consumer_sha,
        "TASK41_P0_EXPECTED_SOURCE_SHA": producer_sha,
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": abi_sha,
        "PHYSICAL_WATCHDOG_PARENT_PID": str(os.getppid()),
    }
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.setattr(
        "src.runners.task41_p0_saved_output_continuation._source_identity",
        lambda _root: (consumer_sha, branch),
    )
    monkeypatch.setattr(
        "benchmarks.subreaper_watchdog.cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_limit_bytes": 4096,
            "swap_current_bytes": 0,
        },
    )
    _require_service_envelope(contract, contract_path, contract_sha, tmp_path)

    monkeypatch.setattr(
        task41_p0_contract,
        "require_task41_p0_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        task41_p0_contract,
        "_saved_output_consumer_source_sha",
        lambda *_args, **_kwargs: consumer_sha,
    )
    env.update(
        {
            "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
            "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        }
    )
    identity = task41_p0_contract.qualified_activation_identity(env)
    assert identity == f"task41_p0_native_complex:{abi_sha}"
    assert isinstance(identity, str)

    env["TASK41_P0_CONSUMER_SOURCE_SHA"] = "c" * 40
    with pytest.raises(RuntimeError, match="producer and consumer source identities"):
        _require_service_envelope(contract, contract_path, contract_sha, tmp_path)


def test_service_call_chain_uses_string_activation_and_one_frozen_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path
    results_root = repo_root / "results" / "model"
    run_root = results_root / "attempt7"
    run_root.mkdir(parents=True)
    output_root = results_root / "continuation"
    contract_sha = "f" * 64
    window = FixedCampaignWindow(
        path=repo_root / "execution_window.json",
        sha256="e" * 64,
        payload={"accounting_path": str(repo_root / "window_accounting.jsonl")},
        anchor={},
        t0_utc_ns=100,
        deadline_utc_ns=1_800_000_000_100,
        total_seconds=1800.0,
        bootstrap_seconds=0.0,
        closeout_seconds=600.0,
    )
    contract = {
        "task_id": "task41-p0",
        "case": {"model_id": "model", "input_sha256": "a" * 64},
        "source": {"sha": "b" * 40},
        "branch": "task41extra_phi90_p50x50_g17x20",
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {"abi_receipt_sha256": "c" * 64},
    }
    activation = f"task41_p0_native_complex:{contract['runtime']['abi_receipt_sha256']}"
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_supervise(command: list[str], directory: Path, **kwargs: object) -> dict[str, object]:
        calls.append((command, kwargs))
        assert kwargs["campaign_window_path"] == window.path
        assert kwargs["campaign_window_sha256"] == window.sha256
        assert kwargs["tree_cap_bytes"] == contract["resources"]["task_memory_max_bytes"]
        assert kwargs["host_reserve_bytes"] == contract["resources"]["host_reserve_bytes"]
        if len(calls) == 1:
            assert kwargs["wall_seconds"] == window.cutoff_seconds
            output_root.mkdir()
            snapshot = output_root / "task41_p0_saved_output_checker_input.json"
            snapshot.write_text(json.dumps({"status": "OUTPUTS_READY"}))
            (output_root / "task41_p0_saved_output_continuation_receipt.json").write_text(
                json.dumps({"status": "OUTPUTS_READY"})
            )
            assert command[command.index("--consumer-source-sha") + 1] == "d" * 40
            assert command[command.index("--contract-sha256") + 1] == contract_sha
        else:
            assert kwargs["wall_seconds"] == window.closeout_seconds
            output_path = Path(command[command.index("--output") + 1])
            snapshot = output_root / "task41_p0_saved_output_checker_input.json"
            output_path.write_text(
                json.dumps(
                    {
                        "checker_passed": True,
                        "checker_input_snapshot_sha256": hashlib.sha256(
                            snapshot.read_bytes()
                        ).hexdigest(),
                    }
                )
            )
            assert command[command.index("--saved-output-continuation-input") + 1] == str(snapshot)
            assert command[command.index("--contract-sha256") + 1] == contract_sha
            assert kwargs["campaign_phase_authorization"]["source_sha"] == "d" * 40
            assert kwargs["campaign_phase_authorization"]["checker_kind"] == (
                "task41_p0_saved_output_continuation_checker"
            )
        return {"classification": "COMPLETED", "leader_exit_code": 0}

    import scripts.task40_v20_service_workflow as service_workflow

    monkeypatch.setattr(
        service_workflow.subprocess,
        "check_output",
        lambda command, **_kwargs: (
            "task41extra_phi90_p50x50_g17x20\n"
            if command[-1] == "--show-current"
            else "d" * 40 + "\n"
        ),
    )
    result = _run_task41_p0_saved_output_service(
        unit="task41-test",
        runtime_prefix=repo_root / "runtime",
        environment={"TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1"},
        window=window,
        contract=contract,
        contract_path=repo_root / "contract.json",
        contract_sha=contract_sha,
        case_id="A2",
        run_root=run_root,
        output_root=output_root,
        consumer_source_sha="d" * 40,
        checker_only=False,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        input_path=repo_root / "input.dat",
        activation_command=["activate"],
        activation_identity=activation,
        preflight={"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1},
        preflight_command=["python", "preflight"],
        cgroup_start={"memory_limit_bytes": 1 << 30, "swap_current_bytes": 0},
        service_entry_accounting={"window_sha256": window.sha256},
        service_start_sample=clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
    )

    assert result == 0
    assert len(calls) == 2
    assert calls[0][1]["campaign_phase"] == "numeric"
    assert calls[1][1]["campaign_phase"] == "closeout"
    service_directory = output_root.with_name("continuation.service")
    assert calls[0][1]["phase_path"] == service_directory / "continuation_phase.json"
    assert calls[1][1]["phase_path"] == service_directory / "required_checker_phase.json"
    assert calls[0][1]["phase_path"] != calls[1][1]["phase_path"]
    assert calls[0][0][calls[0][0].index("--run-root") + 1] == str(run_root)
    assert calls[0][0][calls[0][0].index("--output-dir") + 1] == str(output_root)
    assert calls[1][0][calls[1][0].index("--output") + 1] == str(
        output_root / "task41_p0_saved_output_checker_result.json"
    )
    service_receipt = json.loads(
        (output_root.with_name("continuation.service") / "task41_p0_service_receipt.json")
        .read_text(encoding="utf-8")
    )
    assert service_receipt["producer_source_sha"] == "b" * 40
    assert service_receipt["consumer_source_sha"] == "d" * 40
    assert service_receipt["activation_identity"] == activation
    assert isinstance(service_receipt["activation_identity"], str)
    final_receipt = json.loads(
        (output_root / "task41_p0_saved_output_continuation_receipt.json")
        .read_text(encoding="utf-8")
    )
    checker_output = output_root / "task41_p0_saved_output_checker_result.json"
    checker_input = output_root / "task41_p0_saved_output_checker_input.json"
    assert final_receipt["status"] == "PASS"
    assert final_receipt["checker_input_snapshot_sha256"] == hashlib.sha256(
        checker_input.read_bytes()
    ).hexdigest()
    assert final_receipt["checker_result_sha256"] == hashlib.sha256(
        checker_output.read_bytes()
    ).hexdigest()


def test_task41_diffraction_inventory_checks_real_attempt7_snapshot() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "task41_p0_attempt7_diffraction_inventory.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    metrics = fixture["metrics"]
    orders = fixture["orders"]
    assert fixture["source_run_id"] == "task41extra_g13_p6_phi90_iterative_a2"
    assert len(orders) == 578

    runtime_gate = task41_diagnostic_diffraction_inventory(
        metrics, orders, expected_m_max=8, expected_n_max=8
    )
    checker_gate = _task41_a2_diagnostic_inventory_from_data(
        metrics, orders, expected_m_max=8, expected_n_max=8
    )
    assert runtime_gate["passed"] is True
    assert runtime_gate["expected_spatial_order_count"] == 289
    assert runtime_gate["expected_channel_count"] == 578
    assert checker_gate["passed"] is True

    missing = task41_diagnostic_diffraction_inventory(
        metrics, orders[:-1], expected_m_max=8, expected_n_max=8
    )
    assert missing["passed"] is False
    duplicate_orders = [*orders[:-1], orders[0]]
    duplicate = _task41_a2_diagnostic_inventory_from_data(
        metrics, duplicate_orders, expected_m_max=8, expected_n_max=8
    )
    assert duplicate["passed"] is False
    wrong_polarization = [*orders]
    wrong_polarization[0] = {**orders[0], "polarization": "x"}
    wrong_pol = _task41_a2_diagnostic_inventory_from_data(
        metrics, wrong_polarization, expected_m_max=8, expected_n_max=8
    )
    assert wrong_pol["passed"] is False
    wrong_bounds = _task41_a2_diagnostic_inventory_from_data(
        metrics, orders, expected_m_max=7, expected_n_max=8
    )
    assert wrong_bounds["passed"] is False


def test_only_the_known_saved_output_worker_failure_is_eligible(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "numerical_output").mkdir(parents=True)
    resolved_config = b'{"fixture":"Task41 frozen producer config"}\n'
    resolved_config_sha256 = hashlib.sha256(resolved_config).hexdigest()
    case = {
        "model_id": "task41extra_phi90_p50x50_g17x20",
        "run_id": "task41extra_g13_p6_phi90_iterative_a2",
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "resolved_config_sha256": resolved_config_sha256,
    }
    contract = {
        "source": {"sha": "a" * 40},
        "case": case,
        "window": {"sha256": "d" * 64},
        "comparison": {"a1_binding_sha256": "e" * 64},
    }
    worker = {
        "status": "FAILED",
        "result_classification": "WORKER_FAILED",
        "official_result": False,
        "error": {
            "type": "ValueError",
            "message": "Task41 A1 full field representation failed the saved E/H sample witness",
        },
        "numeric_gates_passed": True,
        "source_sha": "a" * 40,
        "run_id": "task41extra_g13_p6_phi90_iterative_a2",
        "identity_packet": {
            "input_sha256": case["input_sha256"],
            "physical_model_sha256": case["physical_model_sha256"],
            "source_sha": "a" * 40,
            "run_id": case["run_id"],
        },
        "profile": "task41extra_g13_p6_phi90_a2_y_orbit_reference_v1",
        "stage": "TASK41_A2",
        "q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "campaign_authority": {
            "task41_contract_sha256": "f" * 64,
            "campaign_window_sha256": "d" * 64,
            "a1_comparison_binding_sha256": "e" * 64,
        },
    }
    run_summary = {
        "status": "finished",
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
        "numerical_output_directory": str((run_root / "numerical_output").resolve()),
    }
    manifest = {
        "status": "finished",
        "result_classification": "WORKER_FAILED",
        "source_sha": "a" * 40,
        **case,
    }
    (run_root / "task40_v10_p6_candidate_summary.json").write_text(json.dumps(worker), encoding="utf-8")
    (run_root / "run_summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_root / "resolved_config.json").write_bytes(resolved_config)

    original, _, _, evidence = _validate_original_attempt(run_root, contract, "f" * 64)
    assert original["result_classification"] == "WORKER_FAILED"
    assert evidence["worker_summary"]["sha256"]
    identity = _validate_original_solver_identity(original, case)
    assert "resolved_config_sha256" not in identity

    manifest["resolved_config_sha256"] = "0" * 64
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="run manifest identity differs.*resolved_config_sha256"):
        _validate_original_attempt(run_root, contract, "f" * 64)

    manifest["resolved_config_sha256"] = resolved_config_sha256
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_root / "resolved_config.json").write_bytes(b'{"fixture":"changed"}\n')
    with pytest.raises(ValueError, match="resolved configuration differs"):
        _validate_original_attempt(run_root, contract, "f" * 64)

    (run_root / "resolved_config.json").write_bytes(resolved_config)

    worker["result_classification"] = "PASS"
    (run_root / "task40_v10_p6_candidate_summary.json").write_text(json.dumps(worker), encoding="utf-8")
    with pytest.raises(ValueError, match="not the preserved postprocessing-only failure"):
        _validate_original_attempt(run_root, contract, "f" * 64)
