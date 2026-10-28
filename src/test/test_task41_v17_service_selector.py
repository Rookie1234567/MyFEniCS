"""V17 command and Python service-route entry, without prepare or execution."""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from scripts import task40_v20_service_workflow as workflow
from src.runners import task41_p0_checker as checker
from src.runners import task41_p0_contract as contract_module
from src.runners import task41_p0_v4_volume_only_audit as worker


def _v17_contract(root: Path) -> tuple[dict[str, object], Path]:
    strategy = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v2",
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "refinement_strategy": contract_module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
    }
    path = root / contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE
    return {
        "case": {"model_id": contract_module.TASK41_MODEL_ID},
        "execution_scope": contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE,
        "numerical_strategy": strategy,
    }, path


def _write_valid_v17_contract_fixture(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_sha: str = "1" * 40,
) -> tuple[Path, dict[str, Any], str, Any]:
    """Create synthetic authorization/window files only under pytest tmp_path."""
    case = contract_module._task41_case("B0")
    input_path = root / case["input_relative"]
    input_path.parent.mkdir(parents=True, exist_ok=True)
    repository_input = Path(__file__).resolve().parents[2] / case["input_relative"]
    input_path.write_bytes(repository_input.read_bytes())

    runtime = root / "qualified-runtime"
    python_path = runtime / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)
    abi_receipt = root / "abi_receipt.json"
    abi_receipt.write_text('{"fixture":"qualified native receipt shape"}\n', encoding="utf-8")
    jit_cache = root / "jit-cache"
    jit_cache.mkdir()

    config = contract_module._task41_saved_diagnostics_instance(
        contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE
    )
    prior_ledger_path = root / config["prior_ledger_relative"]
    prior_window_path = root / config["prior_window_relative"]
    prior_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    prior_window_path.parent.mkdir(parents=True, exist_ok=True)
    prior_ledger_path.write_bytes(b"synthetic frozen parent ledger\n")
    prior_window_path.write_text(
        json.dumps({"accounting_path": str(prior_ledger_path.resolve())}),
        encoding="utf-8",
    )
    anchor = dict(contract_module.clock_sample(include_boot_id=True))
    authorization = {
        "schema": contract_module.TASK41_B0_SAVED_DIAGNOSTICS_AUTH_SCHEMA,
        "authorization": config["authorization"],
        "source_at_entry": source_sha,
        "preparation_started_utc": contract_module._utc_text_from_ns(
            int(anchor["utc_ns"])
        ),
        "total_seconds": config["total_seconds"],
        "numerical_seconds": config["numerical_seconds"],
        "closeout_seconds": contract_module.TASK41_CLOSEOUT_SECONDS,
        "scope": config["scope"],
        "prior_window_path": str(config["prior_window_relative"]),
        "prior_window_sha256": hashlib.sha256(prior_window_path.read_bytes()).hexdigest(),
        "prior_ledger_path": str(config["prior_ledger_relative"]),
        "prior_ledger_sha256": contract_module.sha256_file(prior_ledger_path),
    }
    authorization_path = root / config["authorization_relative"]
    authorization_path.parent.mkdir(parents=True, exist_ok=True)
    authorization_path.write_text(
        json.dumps(authorization, sort_keys=True), encoding="utf-8"
    )

    def fake_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("branch", "--show-current"):
            return contract_module.TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args}")

    monkeypatch.setattr(contract_module, "_git", fake_git)
    monkeypatch.setattr(
        contract_module,
        "_check_task41_native_receipt",
        lambda path, *_args: contract_module.sha256_file(path),
    )
    monkeypatch.setattr(
        contract_module,
        "verify_task41_b0_saved_surface_donor",
        lambda *_args, **_kwargs: None,
    )
    prepared = contract_module.prepare_task41_p0(
        current_root=root,
        case_id="B0",
        b0_saved_diagnostics_instance=(
            contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE
        ),
        runtime_prefix=runtime,
        abi_receipt=abi_receipt,
        jit_cache=jit_cache,
    )
    contract_path = root / prepared["contract_path"]
    contract, digest = contract_module.require_task41_p0_contract(
        contract_path,
        expected_sha256=prepared["contract_sha256"],
        current_root=root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    fixed_window = contract_module.load_task41_p0_fixed_window(
        contract, current_root=root, require_current_boot=False
    )
    return contract_path, contract, digest, fixed_window


def test_v17_contract_command_contains_only_its_named_selector() -> None:
    command = contract_module._task41_p0_service_command(
        case_input="input/b0.dat",
        contract_path="contract.json",
        saved_diagnostics_enabled=True,
        saved_diagnostics_instance=(
            contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE
        ),
        v17_output_directory="results/model/window/selected_incident_replay/attempt01",
    )
    assert command == [
        "bash",
        "scripts/run_case_in_user_service.sh",
        "input/b0.dat",
        "--task41-p0-execution-contract",
        "contract.json",
        "--task41-p0-b0-v17-selected-two-cell-replay",
        "--v16-manifest",
        str(contract_module.TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE),
        "--v16-manifest-sha256",
        contract_module.TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        "--output-dir",
        "results/model/window/selected_incident_replay/attempt01",
    ]
    assert contract_module._task41_p0_service_command(
        case_input="input/b0.dat",
        contract_path="contract.json",
        saved_diagnostics_enabled=True,
        saved_diagnostics_instance=contract_module.TASK41_B0_V16_SAVED_VECTOR_INSTANCE,
    ) is None


def test_v17_python_selector_is_consumed_once_and_forwarded_with_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        workflow,
        "_run_task41_p0_service",
        lambda **kwargs: captured.update(kwargs) or 23,
    )
    contract_path = tmp_path / "contract.json"
    input_path = tmp_path / "b0.dat"
    output_path = tmp_path / "selected_incident_replay" / "attempt01"
    token = "--task41-p0-b0-v17-selected-two-cell-replay"
    manifest_relative = contract_module.TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE
    manifest_sha256 = contract_module.TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256
    common = {
        "unit": "task41-v17-selector-fixture.service",
        "runtime_prefix": tmp_path / ".venv",
        "abi_receipt": tmp_path / "abi.json",
        "jit_cache": tmp_path / "jit",
        "repo_root": tmp_path,
    }

    assert workflow.run_service(
        **common,
        case_args=[
            str(input_path), token,
            "--task41-p0-execution-contract", str(contract_path),
            "--v16-manifest", str(manifest_relative),
            "--v16-manifest-sha256", manifest_sha256,
            "--output-dir", str(output_path),
        ],
    ) == 23
    assert captured["case_args"] == [
        str(input_path),
        "--v16-manifest", str(manifest_relative),
        "--v16-manifest-sha256", manifest_sha256,
        "--output-dir", str(output_path),
    ]
    assert captured["contract_path"] == contract_path
    assert captured["v17_selected_two_cell_selector"] is True
    parsed_manifest, parsed_sha, parsed_output, parsed_producer = workflow._parse_task41_p0_v17_service_args(
        captured["case_args"], repo_root=tmp_path
    )
    assert parsed_manifest == (tmp_path / manifest_relative).resolve()
    assert parsed_sha == manifest_sha256
    assert parsed_output == output_path.resolve()
    assert parsed_producer is None
    bad_args = list(captured["case_args"])
    bad_args[2] = "results/other/manifest.json"
    with pytest.raises(ValueError, match="manifest path or SHA-256 differs"):
        workflow._parse_task41_p0_v17_service_args(bad_args, repo_root=tmp_path)

    with pytest.raises(ValueError, match="requires its Task41 P0 execution contract"):
        workflow.run_service(**common, case_args=[str(input_path), token])
    with pytest.raises(ValueError, match="may appear only once"):
        workflow.run_service(
            **common,
            case_args=[
                str(input_path), token, token,
                "--task41-p0-execution-contract", str(contract_path),
            ],
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        workflow.run_service(
            **common,
            case_args=[
                str(input_path), token, "--task41-p0-b0-v15-full-acceptance",
                "--task41-p0-execution-contract", str(contract_path),
            ],
        )


def test_v17_scope_guard_requires_exact_case_scope_strategy_and_window(
    tmp_path: Path,
) -> None:
    payload, expected_window = _v17_contract(tmp_path)
    validate = workflow._validate_task41_p0_v17_selector_scope
    assert validate(
        selector=True,
        case_id="B0",
        contract=payload,
        contract_window=expected_window,
        repo_root=tmp_path,
    ) is True

    for bad_case, bad_contract, bad_window in (
        ("A1", payload, expected_window),
        ("B0", {**payload, "execution_scope": {"kind": "wrong"}}, expected_window),
        ("B0", payload, tmp_path / "wrong-window.json"),
        ("B0", {**payload, "numerical_strategy": {"internal_rhs_strategy": "wrong"}}, expected_window),
    ):
        with pytest.raises(ValueError, match="exact contract and explicit service selector"):
            validate(
                selector=True,
                case_id=bad_case,
                contract=bad_contract,
                contract_window=bad_window,
                repo_root=tmp_path,
            )

    with pytest.raises(ValueError, match="exact contract and explicit service selector"):
        validate(
            selector=False,
            case_id="B0",
            contract=payload,
            contract_window=expected_window,
            repo_root=tmp_path,
        )


def test_v17_real_contract_and_manifest_loaders_reject_bad_hash_and_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    contract_path, contract, contract_sha, _fixed_window = _write_valid_v17_contract_fixture(
        root, monkeypatch
    )
    with pytest.raises(ValueError):
        contract_module.require_task41_p0_contract(
            contract_path,
            expected_sha256="0" * 64,
            current_root=root,
            check_current_source=False,
            require_clean_source=False,
            case_id="B0",
        )

    wrong_scope = copy.deepcopy(contract)
    wrong_scope["execution_scope"] = {"kind": "wrong_scope"}
    contract_path.write_text(
        json.dumps(wrong_scope, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    wrong_scope_sha = contract_module.sha256_file(contract_path)
    with pytest.raises(ValueError):
        contract_module.require_task41_p0_contract(
            contract_path,
            expected_sha256=wrong_scope_sha,
            current_root=root,
            check_current_source=False,
            require_clean_source=False,
            case_id="B0",
        )

    results_root = root / "results" / contract_module.TASK41_MODEL_ID
    manifest_path = results_root / contract_module.TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE.relative_to(
        Path("results") / contract_module.TASK41_MODEL_ID
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest path, size, or SHA-256 differs"):
        checker.load_task41_p0_b0_v16_saved_vector_manifest(
            manifest_path,
            "0" * 64,
            repo_root=root,
            include_saved_array_replay=False,
            include_row_incidence=False,
        )
    assert contract_sha != wrong_scope_sha


def test_v17_report_acquisition_skips_worker_for_verified_completed_receipt(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "producer" / "task41_p0_v17_selected_two_cell_worker.json"
    report_path.parent.mkdir()
    report_path.write_text("{}\n", encoding="utf-8")
    payload = {"schema": "fixture-completed-producer-report"}
    worker_calls: list[str] = []
    worker_source = inspect.getsource(workflow._run_task41_p0_saved_output_service)
    assert "_task41_p0_v17_acquire_worker_report(" in worker_source

    result = workflow._task41_p0_v17_acquire_worker_report(
        producer_report_path=report_path,
        producer_report_payload=payload,
        consumer_report_path=tmp_path / "consumer" / "worker.json",
        run_worker=lambda: worker_calls.append("called") or pytest.fail("worker must not rerun"),
    )
    assert result == (report_path, payload, None, True)
    assert worker_calls == []

    consumer_report_path = tmp_path / "new-attempt" / "worker.json"
    watchdog = {"classification": "COMPLETED", "leader_exit_code": 0}
    generated = {"schema": "fixture-new-worker-report"}
    result = workflow._task41_p0_v17_acquire_worker_report(
        producer_report_path=None,
        producer_report_payload=None,
        consumer_report_path=consumer_report_path,
        run_worker=lambda: worker_calls.append("called") or (watchdog, generated),
    )
    assert result == (consumer_report_path, generated, watchdog, False)
    assert worker_calls == ["called"]


def test_v17_readonly_producer_loader_uses_real_contract_and_window_loaders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    producer_path, producer, producer_sha, fixed_window = _write_valid_v17_contract_fixture(
        root, monkeypatch
    )
    consumer = copy.deepcopy(producer)
    consumer_source_sha = "2" * 40
    consumer["source"]["sha"] = consumer_source_sha
    service_relative = contract_module._task41_case("B0")["service_relative"]
    consumer["evidence"]["service_directory"] = str(
        service_relative / f"service_source_{consumer_source_sha}"
    )
    consumer_path = root / contract_module.contract_relative_path(
        consumer_source_sha,
        "B0",
        saved_diagnostics_instance=contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE,
    )
    consumer_path.parent.mkdir(parents=True, exist_ok=True)
    consumer_path.write_text(
        json.dumps(consumer, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    consumer, consumer_sha = contract_module.require_task41_p0_contract(
        consumer_path,
        current_root=root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    consumer_window = contract_module.load_task41_p0_fixed_window(
        consumer, current_root=root, require_current_boot=False
    )
    assert consumer_window.sha256 == fixed_window.sha256
    assert producer["source"]["sha"] != consumer["source"]["sha"]

    results_root = root / "results" / contract_module.TASK41_MODEL_ID
    replay_parent = (
        results_root / "task41_p0_saved_diagnostics_6h" / fixed_window.sha256
        / "selected_incident_replay"
    )
    replay_parent.mkdir(parents=True, exist_ok=True)
    producer_output = replay_parent / "attempt01"
    producer_output.mkdir()
    consumer_output = replay_parent / "attempt02"
    producer_relative = str(producer_path.relative_to(root))
    producer_binding = {
        "path": producer_relative,
        "sha256": producer_sha,
        "source_sha": producer["source"]["sha"],
        "fixed_window_sha256": fixed_window.sha256,
    }
    callback = {
        "status": "COMPLETED_SELECTED_TWO_CELL_CANDIDATE_AND_RHS_REPLAY",
        "classification": "LOCAL_REPLAY_COMPLETED",
    }
    progress_path = producer_output / "task41_p0_v17_progress.json"
    progress_payload = {
        "schema": "task41.p0.b0.v17.selected_two_cell_progress.v2",
        "run_identity": {"fixed_window_sha256": fixed_window.sha256},
        "producer_execution_binding": producer_binding,
        "consumer_execution_bindings": [producer_binding],
        "latest_consumer_execution_binding": producer_binding,
        "selected_two_cell_candidate_callback": callback,
    }
    progress_path.write_text(json.dumps(progress_payload), encoding="utf-8")
    progress_sha = contract_module.sha256_file(progress_path)
    report_path = producer_output / "task41_p0_v17_selected_two_cell_worker.json"
    report_payload = {
        "schema": "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1",
        "status": "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY",
        "consumer_contract_sha256": producer_sha,
        "consumer_window_sha256": fixed_window.sha256,
        "selected_two_cell_candidate_callback": callback,
        "official_result": False,
        "scientific_qualified": False,
        "full_owner_unlocked": False,
    }
    report_path.write_text(json.dumps(report_payload), encoding="utf-8")
    report_sha = contract_module.sha256_file(report_path)

    loaded_producer, loaded_progress, loaded_report = workflow._task41_p0_v17_readonly_producer_inputs(
        producer_binding={
            "contract_path": producer_path,
            "contract_sha256": producer_sha,
            "progress_path": progress_path,
            "progress_sha256": progress_sha,
            "report_path": report_path,
            "report_sha256": report_sha,
        },
        consumer_contract=consumer,
        consumer_contract_sha256=consumer_sha,
        window_sha256=fixed_window.sha256,
        repo_root=root,
        consumer_output_path=consumer_output,
    )
    assert loaded_producer == producer
    assert loaded_progress == progress_payload
    assert loaded_report == report_payload

    progress_path.write_text(json.dumps({**progress_payload, "tampered": True}))
    with pytest.raises(ValueError, match="progress path, size, or SHA-256 differs"):
        workflow._task41_p0_v17_readonly_producer_inputs(
            producer_binding={
                "contract_path": producer_path,
                "contract_sha256": producer_sha,
                "progress_path": progress_path,
                "progress_sha256": progress_sha,
                "report_path": report_path,
                "report_sha256": report_sha,
            },
            consumer_contract=consumer,
            consumer_contract_sha256=consumer_sha,
            window_sha256=fixed_window.sha256,
            repo_root=root,
            consumer_output_path=consumer_output,
        )


def test_v17_service_worker_checker_command_chain_and_receipt_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "v16_manifest.json"
    consumer_contract = tmp_path / "consumer_contract.json"
    output = tmp_path / "selected_incident_replay" / "attempt01"
    pre_admission = tmp_path / "attempt01.service" / "task41_p0_v17_pre_admission.json"
    worker_report = output / "task41_p0_v17_selected_two_cell_worker.json"
    checker_result = output.with_name("attempt01.service") / "task41_p0_v17_independent_check.json"
    ffcx = tmp_path / "libffcx.c"
    for path, content in (
        (manifest, "manifest"),
        (consumer_contract, "contract"),
        (ffcx, "source"),
    ):
        path.write_text(content, encoding="utf-8")

    worker_command = workflow._task41_p0_v17_worker_command(
        python="/qualified/python",
        manifest_path=manifest,
        manifest_sha256="a" * 64,
        consumer_contract_path=consumer_contract,
        consumer_contract_sha256="b" * 64,
        pre_admission_path=pre_admission,
        pre_admission_sha256="c" * 64,
        output_directory=output,
        ffcx_c_source_path=ffcx,
    )
    assert worker_command[1:4] == [
        "-m", "src.runners.task41_p0_v4_volume_only_audit",
        "--v17-selected-two-cell-replay",
    ]
    assert worker_command[4:] == [
        "--v16-saved-vector-manifest", str(manifest),
        "--v16-saved-vector-manifest-sha256", "a" * 64,
        "--v17-consumer-contract", str(consumer_contract),
        "--v17-consumer-contract-sha256", "b" * 64,
        "--v17-pre-admission", str(pre_admission),
        "--v17-pre-admission-sha256", "c" * 64,
        "--output-dir", str(output),
        "--selected-active-row", "1622464",
        "--geometry-policy", "mesh_actual_exact",
        "--raw-tensor-evaluator", "actual_qmetric_blocked_gram",
        "--ffcx-c-source", str(ffcx),
    ]

    worker_calls: list[Any] = []
    monkeypatch.setattr(
        worker,
        "_run_v17_selected_two_cell_replay",
        lambda args: worker_calls.append(args) or {"status": "worker-fixture"},
    )
    assert worker.main(worker_command[3:]) == 0
    assert len(worker_calls) == 1
    assert worker_calls[0].selected_active_row == 1_622_464
    worker_receipt = {
        "schema": "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1",
        "status": "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY",
        "consumer_contract_sha256": "b" * 64,
        "consumer_window_sha256": "c" * 64,
        "official_result": False,
        "scientific_qualified": False,
        "full_owner_unlocked": False,
    }
    worker_watchdog = {"classification": "COMPLETED", "leader_exit_code": 0}
    assert workflow._task41_p0_v17_worker_completed(
        worker_watchdog,
        worker_receipt,
        contract_sha256="b" * 64,
        window_sha256="c" * 64,
    )
    assert not workflow._task41_p0_v17_worker_completed(
        worker_watchdog,
        {**worker_receipt, "full_owner_unlocked": True},
        contract_sha256="b" * 64,
        window_sha256="c" * 64,
    )

    checker_command = workflow._task41_p0_v17_checker_command(
        python="/qualified/python",
        worker_report_path=worker_report,
        worker_report_sha256="d" * 64,
        manifest_path=manifest,
        manifest_sha256="a" * 64,
        contract_path=consumer_contract,
        contract_sha256="b" * 64,
        producer_contract_path=consumer_contract,
        producer_contract_sha256="b" * 64,
        progress_path=output / "task41_p0_v17_progress.json",
        progress_sha256="e" * 64,
        output_path=checker_result,
    )
    assert checker_command[1:4] == [
        "-m", "src.runners.task41_p0_checker", "--v17-selected-two-cell-check"
    ]
    assert checker_command[checker_command.index("--v17-producer-contract") + 1] == str(consumer_contract)
    assert checker_command[checker_command.index("--v17-progress-sha256") + 1] == "e" * 64
    checker_calls: list[dict[str, Any]] = []
    checker_result.parent.mkdir(parents=True)
    monkeypatch.setattr(
        checker,
        "check_task41_p0_b0_v17_selected_two_cell_report",
        lambda **kwargs: checker_calls.append(kwargs) or {
            "schema": "task41.p0.b0.v17.selected_two_cell_independent_check.v1",
            "status": "LOCAL_REPLAY_COMPLETED",
            "check_completed": True,
            "data_integrity": True,
            "official_result": False,
            "scientific_qualified": False,
            "full_owner_unlocked": False,
            "errors": [],
        },
    )
    assert checker.main(checker_command[3:]) == 0
    assert len(checker_calls) == 1
    assert checker_calls[0]["report_path"] == worker_report
    assert checker_calls[0]["manifest_path"] == manifest
    assert workflow._task41_p0_v17_checker_completed(
        {"classification": "COMPLETED", "leader_exit_code": 0},
        {
            "schema": "task41.p0.b0.v17.selected_two_cell_independent_check.v1",
            "status": "LOCAL_REPLAY_UNBOUND",
            "check_completed": True,
            "data_integrity": True,
            "official_result": False,
            "scientific_qualified": False,
            "full_owner_unlocked": False,
            "errors": [],
        },
    )
    assert not workflow._task41_p0_v17_checker_completed(
        {"classification": "COMPLETED", "leader_exit_code": 0},
        {
            "schema": "task41.p0.b0.v17.selected_two_cell_independent_check.v1",
            "status": "LOCAL_REPLAY_COMPLETED",
            "check_completed": True,
            "data_integrity": True,
            "official_result": True,
            "scientific_qualified": False,
            "full_owner_unlocked": False,
            "errors": [],
        },
    )


def test_v17_service_and_watchdog_register_both_supervised_stages() -> None:
    service_source = inspect.getsource(workflow._run_task41_p0_saved_output_service)
    assert "_task41_p0_v17_worker_command(" in service_source
    assert "_task41_p0_v17_worker_completed(" in service_source
    assert "_task41_p0_v17_checker_command(" in service_source
    assert "_task41_p0_v17_checker_authorization(" in service_source
    assert "_task41_p0_v17_checker_completed(" in service_source
    assert 'campaign_phase="numeric"' in service_source
    assert 'campaign_phase="closeout"' in service_source
    assert "fail-closed until its selected-cell worker is connected" not in service_source

    from benchmarks import subreaper_watchdog

    watchdog_source = inspect.getsource(
        subreaper_watchdog._validate_campaign_closeout_authorization
    )
    assert "task41_p0_b0_v17_selected_two_cell_checker" in watchdog_source
    assert "TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE" in watchdog_source
    assert "authorized_hashes[str(campaign.path.resolve(strict=True))] != window_sha" in watchdog_source


def test_v17_checker_authorization_hashes_every_canonical_input(tmp_path: Path) -> None:
    paths = [tmp_path / "contract.json", tmp_path / "window.json", tmp_path / "worker.json"]
    for index, path in enumerate(paths):
        path.write_text(f"fixture-{index}", encoding="utf-8")
    from src.runners.task41_p0_contract import sha256_file

    authorization = workflow._task41_p0_v17_checker_authorization(
        command=["/qualified/python", "-m", "checker"],
        input_paths=paths + [paths[0]],
        window_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_sha="c" * 40,
        source_branch=contract_module.TASK41_BRANCH,
        sha256_file=sha256_file,
    )
    assert authorization["input_paths"] == [str(path.resolve()) for path in paths]
    assert authorization["input_sha256s"] == [sha256_file(path) for path in paths]
    assert authorization["checker_kind"] == "task41_p0_b0_v17_selected_two_cell_checker"
    assert authorization["source_clean"] is True


def test_outer_service_dispatch_passes_v17_mode_to_saved_service() -> None:
    source = Path(workflow.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_task41_p0_service"
    )
    call = next(
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_task41_p0_saved_output_service"
    )
    kw = next(item for item in call.keywords if item.arg == "b0_v17_selected_two_cell_mode")
    assert isinstance(kw.value, ast.Name)
    assert kw.value.id == "b0_v17_selected_two_cell_mode"


def test_v17_saved_service_route_reaches_donor_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    contract_path, contract, contract_sha, fixed_window = (
        _write_valid_v17_contract_fixture(root, monkeypatch)
    )
    model_root = root / "results" / contract_module.TASK41_MODEL_ID
    manifest_path = (
        root / contract_module.TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    fixture_root = model_root / "v17_service_route_fixture"

    def record(name: str, content: bytes) -> dict[str, object]:
        path = fixture_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    report_names = (
        "v9_audit",
        "v15_audit",
        "v15_checkpoint",
        "v15_checker",
        "v9_run_manifest",
        "v15_run_manifest",
        "v15_candidate_summary",
    )
    producer_reports: dict[str, object] = {}
    for name in report_names:
        payload = (
            {
                "existing_evidence_bytes": 0,
                "prior_new_evidence_bytes": 0,
                "new_evidence_bytes": 0,
            }
            if name == "v15_audit"
            else {"fixture": name}
        )
        encoded = json.dumps(payload, sort_keys=True).encode()
        producer_reports[name] = record(f"reports/{name}.json", encoded)

    arrays: dict[str, object] = {}
    for name in ("y9", "g9", "y15", "g15"):
        arrays[name] = [
            record(f"arrays/{name}_column{column}.bin", f"{name}-{column}".encode())
            for column in range(2)
        ]
    active_rows = record("arrays/active_original_rows.bin", b"fixture-map")
    active_rows.update({
        "shape": [5_688_000],
        "dtype": np.dtype(np.int64).str,
    })
    manifest = {
        "schema": "task41.p0.b0.v16.saved_vector_manifest.v1",
        "rows": 5_752_120,
        "trace_rows": 5_688_000,
        "columns": [0, 1],
        "producer_reports": producer_reports,
        "arrays": arrays,
        "metadata_pending": True,
        "metadata_source": {
            "active_original_rows": active_rows,
            "active_original_rows_file_sha256": active_rows["sha256"],
            "active_original_rows_values_sha256": "a" * 64,
        },
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    monkeypatch.setattr(
        contract_module,
        "TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256",
        manifest_sha,
    )
    monkeypatch.setattr(
        workflow,
        "_task41_p0_v17_readonly_producer_inputs",
        lambda **_kwargs: (contract, {}, None),
    )

    class DonorLoaderReached(Exception):
        pass

    def stop_at_donor_loader(**_kwargs: object) -> None:
        raise DonorLoaderReached

    monkeypatch.setattr(checker, "_task41_p0_v16_v3_donor_index", stop_at_donor_loader)
    output_root = (
        model_root / "task41_p0_saved_diagnostics_6h" / fixed_window.sha256
        / "selected_incident_replay" / "attempt01"
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    source_sha = str(contract["source"]["sha"])
    environment = {
        "TASK41_P0_V17_SELECTED_TWO_CELL_REPLAY": "1",
        "TASK41_P0_CHECKER_SOURCE_SHA": source_sha,
    }

    with pytest.raises(DonorLoaderReached):
        workflow._run_task41_p0_saved_output_service(
            unit="fixture.service",
            runtime_prefix=tmp_path / "runtime",
            environment=environment,
            window=fixed_window,
            contract=contract,
            contract_path=contract_path,
            contract_sha=contract_sha,
            case_id="B0",
            run_root=manifest_path.parent,
            output_root=output_root,
            consumer_source_sha=source_sha,
            checker_only=True,
            checker_snapshot_path=None,
            checker_snapshot_sha256=None,
            b0_v17_selected_two_cell_mode=True,
            v17_manifest_path=manifest_path,
            v17_manifest_sha256=manifest_sha,
            v17_producer_binding={"fixture": "hash-bound-inputs-mocked"},
            input_path=root / contract_module._task41_case("B0")["input_relative"],
            activation_command=["fixture-activation"],
            activation_identity="fixture-activation",
            preflight={"status": "fixture"},
            preflight_command=["fixture-preflight"],
            cgroup_start={"status": "fixture"},
            service_entry_accounting={"status": "fixture"},
            service_start_sample={"status": "fixture"},
            repo_root=root,
            supervise=lambda **_kwargs: pytest.fail(
                "V17 route must stop at its mocked donor loader before launching work"
            ),
            sha256_file=contract_module.sha256_file,
        )


def test_v17_callback_persistence_is_reopened_by_real_checker_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    model_id = contract_module.TASK41_MODEL_ID
    results_root = root / "results" / model_id
    source_sha = "1" * 40
    selected_active_row = 3
    selected_original_row = 7
    selected_cells = (7873, 8014)
    scope = copy.deepcopy(contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE)
    scope["selected_active_row"] = selected_active_row
    scope["selected_original_row"] = selected_original_row
    monkeypatch.setattr(contract_module, "TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE", scope)
    contract_path, contract, contract_sha, fixed_window = _write_valid_v17_contract_fixture(
        root, monkeypatch, source_sha=source_sha
    )
    window_sha = fixed_window.sha256
    window_relative = contract_module.TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE
    output = (
        results_root / "task41_p0_saved_diagnostics_6h" / window_sha
        / "selected_incident_replay" / "attempt01"
    )
    service_directory = output.with_name(output.name + ".service")
    output.mkdir(parents=True)
    service_directory.mkdir()

    manifest_relative = Path("fixture/v16_manifest.json")
    contract_manifest_relative = Path("results") / model_id / manifest_relative

    donor_manifest_sha = "f" * 64
    source_index_sha = "e" * 64
    v9_report_path = results_root / "fixture" / "v9_compact.json"
    v9_report_path.parent.mkdir(parents=True)
    v9_report = {
        "schema": "task41.p0.b0.v9.compact_volume_identity.v1",
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "donor_manifest_sha256": donor_manifest_sha,
        "candidate_full_action_gate": {"status": "fixture-bound"},
        "candidate_evaluator_identity": "fixture-actual-qmetric",
        "candidate_evaluator_cache_identity": "fixture-frozen-cache",
    }
    v9_report_path.write_text(json.dumps(v9_report), encoding="utf-8")
    v9_report_sha = hashlib.sha256(v9_report_path.read_bytes()).hexdigest()
    manifest = {
        "schema": "task41.p0.b0.v16.saved_vector_manifest.v1",
        "rows": 32,
        "trace_rows": 432,
        "columns": [0, 1],
        "producer_reports": {
            "v9_audit": {
                "path": str(v9_report_path.relative_to(results_root)),
                "sha256": v9_report_sha,
            }
        },
    }
    manifest_path = results_root / manifest_relative
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    metadata_relative = Path("fixtures/v17_selected_metadata.json")
    metadata_path = root / metadata_relative
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_source = {
        "schema": "fixture-v17-selected-metadata",
        "cells": list(selected_cells),
    }
    metadata_path.write_text(json.dumps(metadata_source), encoding="utf-8")
    metadata_sha = hashlib.sha256(metadata_path.read_bytes()).hexdigest()

    active_original_rows = np.arange(4000, 4432, dtype=np.int64)
    active_original_rows[selected_active_row] = selected_original_row
    metadata_cells: list[dict[str, Any]] = []
    fresh_cells: list[dict[str, Any]] = []
    for ordinal, cell_index in enumerate(selected_cells):
        coordinates = np.arange(24, dtype=np.float64).reshape(8, 3) + ordinal * 50.0
        coordinate_sha = worker._task41_p0_v17_array_sha256(
            coordinates.astype("<f8", copy=False)
        )
        local_position = 453 + ordinal
        interior_positions = np.arange(450, dtype=np.int64)
        trace_positions = np.arange(450, 882, dtype=np.int64)
        if ordinal:
            trace_positions[[3, 4]] = trace_positions[[4, 3]]
        local_position = int(trace_positions[3])
        original_rows = np.empty(882, dtype=np.int64)
        original_rows[:450] = 1000 + ordinal * 1500 + np.arange(450)
        original_rows[trace_positions] = (
            2000 + ordinal * 1500 + np.arange(432)
        )
        original_rows[local_position] = selected_original_row
        trace_original_rows = original_rows[trace_positions]
        active_ids = np.arange(432, dtype=np.int64)
        cell_meta = {
            "cell_id": cell_index,
            "cell_tag": 1,
            "cell_permutation": 0,
            "local_position": local_position,
            "actual_coordinate_sha256": coordinate_sha,
            "coordinates": coordinates,
            "active_ids": active_ids,
        }
        metadata_cells.append(cell_meta)
        fresh_cells.append({
            **cell_meta,
            "cell_index": cell_index,
            "geometry_dofs": np.arange(8, dtype=np.int32),
            "actual_geometry_coordinates": coordinates,
            "local_dofs": np.arange(882, dtype=np.int32),
            "original_rows": original_rows,
            "interior_positions": interior_positions,
            "trace_positions": trace_positions,
            "interior_original_rows": original_rows[interior_positions],
            "trace_original_rows": trace_original_rows,
            "trace_expansion_data": np.ones(432, dtype=np.complex128),
            "trace_expansion_indices": np.arange(432, dtype=np.int32),
            "trace_expansion_indptr": np.arange(433, dtype=np.int32),
            "selected_local_trace_rows": np.asarray([3], dtype=np.int32),
            "selected_trace_coefficients": np.asarray([1.0 + 0.0j], dtype=np.complex128),
        })
    metadata = {
        "schema": "task41.p0.b0.v17.selected_cell_metadata.v1",
        "source_metadata_sha256": metadata_sha,
        "selected_active_row": selected_active_row,
        "selected_original_row": selected_original_row,
        "incident_cell_order": list(selected_cells),
        "cells": metadata_cells,
    }

    storage_rows = 5000
    donor_columns: list[dict[str, Any]] = []
    for column_index in range(2):
        known = np.zeros(storage_rows, dtype=np.complex128)
        native_rhs = np.zeros(storage_rows, dtype=np.complex128)
        native_volume_rhs = np.zeros(storage_rows, dtype=np.complex128)
        for ordinal in range(2):
            rhs_row = 1000 + ordinal * 1500
            native_rhs[rhs_row] = 1.0 + 0.5j
            native_volume_rhs[rhs_row] = 1.0 + 0.5j
        if column_index == 0:
            native_rhs[1000] = 0.0 + 0.0j
            native_volume_rhs[1000] = 0.0 + 0.0j
        donor_columns.append({
            "column": column_index,
            "active_original_rows": active_original_rows.copy(),
            "known_field": known,
            "native_rhs": native_rhs,
            "native_volume_rhs": native_volume_rhs,
            "b_alpha_rows": np.empty(0, dtype=np.int64),
            "b_alpha_values": np.empty(0, dtype=np.complex128),
        })
    donor_manifest_path = results_root / "fixture" / "donor" / "manifest.json"
    donor_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    donor_manifest_path.write_text("{}", encoding="utf-8")
    donor = {
        "manifest_path": str(donor_manifest_path),
        "manifest_sha256": donor_manifest_sha,
        "source_index_sha256": source_index_sha,
        "run_name": checker.TASK41_P0_B0_V16_V3_DONOR_RUN_NAME,
        "columns": donor_columns,
    }

    saved_vectors = {
        name: (np.zeros(32, dtype=np.complex128), np.zeros(32, dtype=np.complex128))
        for name in ("y9", "g9", "y15", "g15")
    }

    monkeypatch.setattr(worker, "ROOT", root)
    monkeypatch.setattr(worker, "TASK41_P0_V17_ACTIVE_ROW", selected_active_row)
    monkeypatch.setattr(worker, "TASK41_P0_V17_ORIGINAL_ROW", selected_original_row)
    monkeypatch.setattr(worker, "TASK41_P0_V17_V16_MANIFEST_RELATIVE", manifest_relative)
    monkeypatch.setattr(worker, "TASK41_P0_V17_V16_MANIFEST_SHA256", manifest_sha)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V16_ROWS", 32)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V16_TRACE_ROWS", 432)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V16_STORAGE_ROWS", storage_rows)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V17_SELECTED_ROW", selected_active_row)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW", selected_original_row)
    monkeypatch.setattr(
        checker, "TASK41_P0_B0_V17_SELECTED_LOCAL_POSITION",
        {cell["cell_id"]: cell["local_position"] for cell in metadata_cells},
    )
    monkeypatch.setattr(checker, "TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE", metadata_relative)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V17_SELECTED_METADATA_SHA256", metadata_sha)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256", donor_manifest_sha)
    monkeypatch.setattr(checker, "TASK41_P0_B0_V3_VECTOR_INDEX_SHA256", source_index_sha)
    monkeypatch.setattr(checker, "__file__", str(root / "src/runners/task41_p0_checker.py"))
    monkeypatch.setattr(contract_module, "TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE", scope)
    monkeypatch.setattr(contract_module, "TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE", window_relative)
    monkeypatch.setattr(contract_module, "TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE", contract_manifest_relative)
    monkeypatch.setattr(contract_module, "TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256", manifest_sha)
    monkeypatch.setattr(worker, "ROOT", root)
    monkeypatch.setattr(checker, "task41_raw_artifact_limit_bytes", lambda _contract: 16 * 1024**3)
    monkeypatch.setattr(contract_module, "task41_raw_artifact_limit_bytes", lambda _contract: 16 * 1024**3)
    monkeypatch.setattr(
        checker,
        "load_task41_p0_b0_v16_saved_vector_manifest",
        lambda *_args, **_kwargs: (manifest, saved_vectors, None),
    )
    monkeypatch.setattr(
        checker,
        "load_task41_p0_b0_v17_selected_cell_metadata",
        lambda **_kwargs: metadata,
    )
    monkeypatch.setattr(
        checker,
        "load_task41_p0_b0_v17_v3_selected_donor",
        lambda **_kwargs: donor,
    )

    class FixtureCandidateEvaluator:
        identity = "fixture-actual-qmetric"
        cache_identity = "fixture-frozen-cache"

        def validate_compiled_form(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def prepare(self) -> None:
            return None

    tensor = np.zeros((882, 882), dtype=np.complex128)
    tensor[np.arange(450), np.arange(450)] = 1.0
    tensor[450 + np.arange(432), 450 + np.arange(432)] = 2.0
    from src.solvers import hcurl_assembly_time_condensation as hcurl

    monkeypatch.setattr(
        hcurl,
        "_cell_integral_kernels",
        lambda *_args, **_kwargs: {0: object()},
    )
    monkeypatch.setattr(
        hcurl,
        "_tabulate_volume_audit_path",
        lambda *_args, **_kwargs: {
            "raw_tensor": tensor.copy(),
            "oriented_tensor": tensor.copy(),
        },
    )
    monkeypatch.setattr(worker, "_task41_v12_curl_mass_integral_profile", lambda *_args: {})

    progress_events: list[dict[str, Any]] = []
    progress_path = output / "task41_p0_v17_progress.json"
    callback = lambda: worker._run_v17_selected_two_cell_candidate_callback(
        consumer_contract=contract,
        consumer_contract_sha256=contract_sha,
        consumer_contract_path=contract_path,
        fixed_window=fixed_window,
        v16_metadata=metadata,
        v16_metadata_path=metadata_path,
        v16_metadata_sha256=metadata_sha,
        v16_saved_vector_manifest=manifest,
        v16_saved_vector_manifest_path=manifest_path,
        v16_saved_vector_manifest_sha256=manifest_sha,
        saved_vectors=saved_vectors,
        donor=donor,
        fresh_metadata={
            "selected_active_row": selected_active_row,
            "selected_original_row": selected_original_row,
            "selected_cell_indices": list(selected_cells),
            "active_original_rows": active_original_rows,
            "interior_positions": np.arange(450, dtype=np.int64),
            "trace_positions": np.arange(450, 882, dtype=np.int64),
            "incidents": fresh_cells,
        },
        element=SimpleNamespace(space_dimension=882),
        combined_form=object(),
        kernels={0: object()},
        candidate_evaluator=FixtureCandidateEvaluator(),
        output_directory=output,
        results_root=results_root,
        sha256_file=contract_module.sha256_file,
        allocation_gate=lambda *_args, **_kwargs: None,
        persist_array=lambda name, value: worker._persist_array(
            output, name, value, sha256_file=contract_module.sha256_file
        ),
        progress=progress_events.append,
            checkpoint=lambda name, payload: worker._task41_p0_v17_checkpoint_progress(
                progress_path, name, payload
            ),
    )

    worker_report_path = output / "task41_p0_v17_selected_two_cell_worker.json"
    worker_command = workflow._task41_p0_v17_worker_command(
        python="/qualified/python",
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        consumer_contract_path=contract_path,
        consumer_contract_sha256=contract_sha,
        pre_admission_path=service_directory / "task41_p0_v17_pre_admission.json",
        pre_admission_sha256="a" * 64,
        output_directory=output,
        ffcx_c_source_path=root / "fixture_ffcx.c",
    )

    def fixture_worker_with_real_callback(args: Any) -> dict[str, Any]:
        assert args.selected_active_row == selected_active_row
        callback_payload = callback()
        receipt = {
            "schema": "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1",
            "status": "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY",
            "consumer_contract_sha256": contract_sha,
            "consumer_window_sha256": window_sha,
            "official_result": False,
            "scientific_qualified": False,
            "full_owner_unlocked": False,
            "selected_two_cell_candidate_callback": callback_payload,
        }
        worker._write_json_atomic(worker_report_path, receipt)
        return receipt

    monkeypatch.setattr(worker, "_run_v17_selected_two_cell_replay", fixture_worker_with_real_callback)
    assert worker.main(worker_command[3:]) == 0
    assert json.loads(capsys.readouterr().out)["selected_two_cell_candidate_callback"]["status"] == (
        "COMPLETED_SELECTED_TWO_CELL_CANDIDATE_AND_RHS_REPLAY"
    )
    assert all(
        (output / record["path"].split("/")[-1]).is_file()
        for cell in json.loads(worker_report_path.read_text())["selected_two_cell_candidate_callback"]["cells"]
        for record in cell["candidate_artifacts"].values()
    )
    persisted_progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert persisted_progress["schema"] == "task41.p0.b0.v17.selected_two_cell_progress.v2"
    assert persisted_progress["latest_consumer_execution_binding"]["sha256"] == contract_sha
    assert persisted_progress["selected_two_cell_candidate_callback"] == (
        json.loads(worker_report_path.read_text(encoding="utf-8"))[
            "selected_two_cell_candidate_callback"
        ]
    )

    checker_output = service_directory / "task41_p0_v17_independent_check.json"
    checker_command = workflow._task41_p0_v17_checker_command(
        python="/qualified/python",
        worker_report_path=worker_report_path,
        worker_report_sha256=contract_module.sha256_file(worker_report_path),
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        producer_contract_path=contract_path,
        producer_contract_sha256=contract_sha,
        progress_path=output / "task41_p0_v17_progress.json",
        progress_sha256=contract_module.sha256_file(output / "task41_p0_v17_progress.json"),
        output_path=checker_output,
    )
    assert checker.main(checker_command[3:]) == 0
    checked = json.loads(checker_output.read_text(encoding="utf-8"))
    assert checked["check_completed"] is True
    assert checked["data_integrity"] is True
    assert checked["status"] == "LOCAL_REPLAY_COMPLETED"
    assert checked["official_result"] is False
    assert checked["full_owner_unlocked"] is False
    assert checked["new_npy_artifact_count"] > 0
    assert progress_events
    callback_payload = json.loads(worker_report_path.read_text(encoding="utf-8"))[
        "selected_two_cell_candidate_callback"
    ]
    referenced_npy: dict[Path, int] = {}

    def collect_npy_records(value: Any) -> None:
        if isinstance(value, dict):
            if {"path", "bytes", "sha256", "shape", "dtype"}.issubset(value):
                artifact_path = Path(value["path"]).resolve(strict=True)
                previous = referenced_npy.setdefault(artifact_path, int(value["bytes"]))
                assert previous == int(value["bytes"])
            for nested in value.values():
                collect_npy_records(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_npy_records(nested)

    collect_npy_records(callback_payload)
    assert checked["new_npy_artifact_count"] == len(referenced_npy)
    assert checked["new_npy_evidence_bytes_checked"] == sum(referenced_npy.values())
    for column in checked["independent_columns"]:
        for cell_index in selected_cells:
            step_checks = column["rhs_step_checks_by_cell"][str(cell_index)]
            if column["column"] == 0 and cell_index == selected_cells[0]:
                assert step_checks == []
            else:
                assert len(step_checks) == 1
                assert step_checks[0]["zero_residual_stop_exactly_recomputed"] is True

    def assert_checker_rejects(mutated: dict[str, Any], label: str) -> dict[str, Any]:
        bad_report_path = output / f"{label}_worker.json"
        worker._write_json_atomic(bad_report_path, mutated)
        bad_output = service_directory / f"{label}_independent_check.json"
        bad_command = workflow._task41_p0_v17_checker_command(
            python="/qualified/python",
            worker_report_path=bad_report_path,
            worker_report_sha256=contract_module.sha256_file(bad_report_path),
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha,
            contract_path=contract_path,
            contract_sha256=contract_sha,
            producer_contract_path=contract_path,
            producer_contract_sha256=contract_sha,
            progress_path=output / "task41_p0_v17_progress.json",
            progress_sha256=contract_module.sha256_file(output / "task41_p0_v17_progress.json"),
            output_path=bad_output,
        )
        assert checker.main(bad_command[3:]) == 2
        return json.loads(bad_output.read_text(encoding="utf-8"))

    bad_hash_report = copy.deepcopy(
        json.loads(worker_report_path.read_text(encoding="utf-8"))
    )
    bad_hash_report["selected_two_cell_candidate_callback"]["cells"][0][
        "fresh_map_artifacts"
    ]["trace_positions"]["sha256"] = "0" * 64
    bad_hash_result = assert_checker_rejects(bad_hash_report, "bad_hash")
    assert bad_hash_result["check_completed"] is False
    assert bad_hash_result["data_integrity"] is False

    incomplete_coverage_report = copy.deepcopy(
        json.loads(worker_report_path.read_text(encoding="utf-8"))
    )
    del incomplete_coverage_report["selected_two_cell_candidate_callback"]["cells"][0][
        "fresh_map_artifacts"
    ]["active_ids"]
    incomplete_coverage_result = assert_checker_rejects(
        incomplete_coverage_report, "incomplete_coverage"
    )
    assert incomplete_coverage_result["check_completed"] is False
    assert incomplete_coverage_result["data_integrity"] is False

    with monkeypatch.context() as cap_patch:
        cap_patch.setattr(
            checker,
            "TASK41_P0_B0_V17_NEW_NPY_EVIDENCE_LIMIT_BYTES",
            checked["new_npy_evidence_bytes_checked"] - 1,
        )
        over_cap_result = assert_checker_rejects(
            json.loads(worker_report_path.read_text(encoding="utf-8")),
            "over_total_npy_cap",
        )
    assert over_cap_result["check_completed"] is False
    assert over_cap_result["data_integrity"] is False

    rhs_record = callback_payload["cells"][0]["columns"][0]["rhs_artifacts"].get(
        "step1_residual"
    )
    if rhs_record is None:
        rhs_record = callback_payload["cells"][1]["columns"][0]["rhs_artifacts"][
            "step1_residual"
        ]
    residual_path = Path(rhs_record["path"])
    original_residual_bytes = residual_path.read_bytes()
    residual = np.load(residual_path, allow_pickle=False)
    residual = residual.copy()
    residual[0] += 1.0 + 0.0j
    try:
        with residual_path.open("wb") as stream:
            np.save(stream, residual, allow_pickle=False)
        tampered_step_result = assert_checker_rejects(
            json.loads(worker_report_path.read_text(encoding="utf-8")),
            "tampered_rhs_step",
        )
        assert tampered_step_result["check_completed"] is False
        assert tampered_step_result["data_integrity"] is False
    finally:
        residual_path.write_bytes(original_residual_bytes)
