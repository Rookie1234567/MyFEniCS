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
    task41_diagnostic_diffraction_inventory,
    validate_saved_a6_packet,
)
from src.runners.task41_p0_checker import _task41_a2_diagnostic_inventory_from_data
from src.runners import task41_p0_contract
from src.runners.task40_v10_campaign import FixedCampaignWindow
from src.runners.workflow_timebase import clock_sample
from scripts.task40_v20_service_workflow import _run_task41_p0_saved_output_service


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
    destination = tmp_path / "continuation" / "numerical_output"

    manifest = _link_saved_output(source, destination)

    assert [row["name"] for row in manifest] == ["field.bin", "orders.json"]
    assert all(row["same_inode"] for row in manifest)
    assert (destination / "field.bin").read_bytes() == (source / "field.bin").read_bytes()


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
        "runtime": {"runtime_prefix": sys.prefix, "abi_receipt_sha256": abi_sha},
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
        lambda _command, **_kwargs: "task41extra_phi90_p50x50_g17x20\n",
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
    contract = {
        "source": {"sha": "a" * 40},
        "case": {"run_id": "task41extra_g13_p6_phi90_iterative_a2"},
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
        "run_id": "task41extra_g13_p6_phi90_iterative_a2",
    }
    (run_root / "task40_v10_p6_candidate_summary.json").write_text(json.dumps(worker), encoding="utf-8")
    (run_root / "run_summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    original, _, _, evidence = _validate_original_attempt(run_root, contract, "f" * 64)
    assert original["result_classification"] == "WORKER_FAILED"
    assert evidence["worker_summary"]["sha256"]

    worker["result_classification"] = "PASS"
    (run_root / "task40_v10_p6_candidate_summary.json").write_text(json.dumps(worker), encoding="utf-8")
    with pytest.raises(ValueError, match="not the preserved postprocessing-only failure"):
        _validate_original_attempt(run_root, contract, "f" * 64)
