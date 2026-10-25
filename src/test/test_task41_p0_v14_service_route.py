from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners import task41_p0_contract as contract_module
from src.runners import task41_p0_v14_candidate_io as v14_io
from src.runners import task41_p0_v4_volume_only_audit as v4_audit
from src.solvers import task41_v4_volume_only_audit as donor_solver
from scripts import task40_v20_service_workflow as service_workflow


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def test_v14_refinement_binding_accepts_immutable_v1_and_explicit_v2_only():
    scope = contract_module.TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE
    historical = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v1",
        "internal_rhs_strategy": "same_lu_rhs_solve",
    }
    explicit = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v2",
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "refinement_strategy": contract_module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
    }
    assert v14_io._v14_refinement_binding(
        {"execution_scope": scope, "numerical_strategy": historical}
    ) == (contract_module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY, 2)
    assert v14_io._v14_refinement_binding(
        {"execution_scope": scope, "numerical_strategy": explicit}
    ) == (contract_module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY, 2)

    wrong_strategy = {**explicit, "refinement_max_steps": 1}
    with pytest.raises(ValueError, match="fixed two-step"):
        v14_io._v14_refinement_binding(
            {"execution_scope": scope, "numerical_strategy": wrong_strategy}
        )
    unbounded_scope = {**scope, "full_owner": True}
    with pytest.raises(ValueError, match="bounded same-LU"):
        v14_io._v14_refinement_binding(
            {"execution_scope": unbounded_scope, "numerical_strategy": explicit}
        )


def test_v14_checker_reads_old_v1_and_new_v2_refinement_serializations():
    from src.runners.task41_p0_v14_saved_rhs_checker import (
        _serialized_refinement_binding_matches,
    )

    scope = contract_module.TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE
    expected = {
        "refinement_strategy": contract_module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
    }
    old_source = {
        **expected,
        "consumer_contract": {
            "execution_scope": scope,
            "numerical_strategy": {
                "schema": "task41.p0.b0.internal_rhs_strategy.v1",
                "internal_rhs_strategy": "same_lu_rhs_solve",
            },
        },
    }
    assert _serialized_refinement_binding_matches(old_source, {})
    assert _serialized_refinement_binding_matches(
        old_source, {"max_correction_steps": 2}
    )
    assert not _serialized_refinement_binding_matches(
        old_source, {"max_correction_steps": 1}
    )
    assert not _serialized_refinement_binding_matches(
        old_source, {"refinement_strategy": expected["refinement_strategy"]}
    )

    new_source = {
        **expected,
        "consumer_contract": {
            "execution_scope": scope,
            "numerical_strategy": {
                "schema": "task41.p0.b0.internal_rhs_strategy.v2",
                "internal_rhs_strategy": "same_lu_rhs_solve",
                **expected,
            },
        },
    }
    assert _serialized_refinement_binding_matches(new_source, expected)
    assert _serialized_refinement_binding_matches(
        new_source, {
            "refinement_strategy": expected["refinement_strategy"],
            "max_correction_steps": 2,
        }
    )
    assert not _serialized_refinement_binding_matches(new_source, {})



def test_v14_decimal_residual_metrics_cover_all_450_rows_with_rounding_bound():
    matrix = np.zeros((450, 450), dtype=np.complex128)
    matrix[0, 0], matrix[0, 1] = 1.0 + 2.0j, 3.0 - 1.0j
    matrix[1, 0], matrix[1, 1] = -2.0 + 0.5j, 0.25 + 1.0j
    rhs = np.zeros(450, dtype=np.complex128)
    rhs[0], rhs[1] = 7.0 + 3.0j, -4.0 + 2.0j
    state = np.zeros(450, dtype=np.complex128)
    state[0], state[1] = 1.0 + 1.0j, 2.0 - 1.0j
    from src.runners import task41_p0_v14_saved_rhs_checker as checker

    precision_50 = checker._decimal_residual_metrics(matrix, rhs, state, precision=50)
    precision_80 = checker._decimal_residual_metrics(matrix, rhs, state, precision=80)
    assert precision_50["row_count"] == precision_80["row_count"] == 450
    assert len(precision_50["row_residuals"]) == len(precision_80["row_residuals"]) == 450
    assert precision_50["row_residuals"][0] == {
        "row": 0, "real": "3", "imag": "5"
    }
    row1_precision_50 = precision_50["row_residuals"][1]
    row1_precision_80 = precision_80["row_residuals"][1]
    assert row1_precision_50["row"] == row1_precision_80["row"] == 1
    assert Decimal(row1_precision_50["real"]) == Decimal(row1_precision_80["real"]) == -3
    assert Decimal(row1_precision_50["imag"]) == Decimal(row1_precision_80["imag"]) == Decimal("1.75")
    row449 = precision_50["row_residuals"][449]
    assert row449["row"] == 449
    assert Decimal(row449["real"]) == Decimal(row449["imag"]) == 0
    assert precision_50["absolute_inf_row"] == 0
    assert precision_50["unit_roundoff_decimal"] == "5E-50"
    assert precision_80["unit_roundoff_decimal"] == "5E-80"
    assert precision_50["rounding_mode"] == precision_80["rounding_mode"] == "ROUND_HALF_EVEN"
    precision_delta = abs(
        Decimal(precision_50["absolute_l2"]) - Decimal(precision_80["absolute_l2"])
    )
    paired_bound = (
        Decimal(precision_50["conservative_decimal_arithmetic_bound"])
        + Decimal(precision_80["conservative_decimal_arithmetic_bound"])
    )
    assert precision_delta <= paired_bound
    assert Decimal(precision_50["conservative_decimal_arithmetic_bound"]) > 0


def test_v14_exact_suffix_drives_two_supervised_workers_and_records_numeric_rejection(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "repo"
    results_root = repo_root / "results" / contract_module.TASK41_MODEL_ID
    results_root.mkdir(parents=True)
    run_root = results_root / "donor_attempt"
    numerical_output = run_root / "numerical_output"
    numerical_output.mkdir(parents=True)

    input_path = repo_root / "case.dat"
    input_path.write_text("synthetic input\n", encoding="utf-8")
    donor_contract_path = (
        repo_root / "benchmarks" / "artifacts" / "task41extra" / "p0_b0_controller"
        / "execution_contract_source_donor.json"
    )
    _write_json(donor_contract_path, {"source": {"sha": "1" * 40}})

    donor_bytes = donor_solver.TASK41_V4_DONOR_NPY_BYTES
    donor_records = []
    for index in range(141):
        size = donor_bytes - 140 if index == 0 else 1
        path = numerical_output / f"donor_{index:03d}.npy"
        path.touch()
        with path.open("r+b") as stream:
            stream.truncate(size)
        donor_records.append({
            "path": str(path.relative_to(run_root)),
            "shape": [1],
            "dtype": "complex128",
            "bytes": size,
        })
    manifest_path = run_root / "run_manifest.json"
    _write_json(manifest_path, {"arrays": donor_records})
    summary_path = run_root / "task40_v10_p6_candidate_summary.json"
    _write_json(summary_path, {
        "b0_recovery_evidence": {
            "manifest": {
                "path": manifest_path.name,
                "bytes": manifest_path.stat().st_size,
                "sha256": donor_solver.TASK41_V4_DONOR_MANIFEST_SHA256,
            }
        }
    })

    v9_run_root = results_root / "task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna" / "20261022T052401.200732Z"
    v9_numerical = v9_run_root / "numerical_output"
    v9_numerical.mkdir(parents=True)
    action_path = v9_numerical / "saved_full_action.npy"
    reduced_rhs_path = v9_numerical / "saved_reduced_rhs.npy"
    action_path.write_bytes(b"action-array")
    reduced_rhs_path.write_bytes(b"rhs-array")
    compact_path = v9_run_root / "task41_p0_b0_v9_compact_volume_audit.json"
    compact_sha = v4_audit.TASK41_P0_V11_V9_COMPACT_REPORT_SHA256
    _write_json(compact_path, {
        "schema": "task41.p0.b0.v9.compact_volume_identity.v1",
        "completed": True,
        "status": "GATE_FAILED",
        "official_result": False,
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "donor_manifest_sha256": donor_solver.TASK41_V4_DONOR_MANIFEST_SHA256,
        "candidate_full_action_gate": {
            "status": "GATE_FAILED",
            "full_action_artifact": {
                "path": str(action_path), "bytes": action_path.stat().st_size,
                "sha256": "2" * 64,
            },
            "full_reduced_rhs_artifact": {
                "path": str(reduced_rhs_path), "bytes": reduced_rhs_path.stat().st_size,
                "sha256": "3" * 64,
            },
        },
        "existing_evidence_bytes": donor_bytes,
        "prior_new_evidence_bytes": 0,
        "new_evidence_bytes": 0,
        "cumulative_evidence_bytes": donor_bytes,
    })

    producer_report_path = results_root / "attempt03" / "task41_p0_v11_selected_trace_candidate_replay.json"
    checker_path = results_root / "attempt03" / "task41_p0_v11_independent_check.json"
    accepted_receipt_path = results_root / "attempt03" / "task41_p0_v11_service_receipt.json"
    _write_json(producer_report_path, {
        "consumer_window_sha256": v14_io.V14_SOURCE_WINDOW_SHA256,
        "v9_compact_report_path": str(compact_path),
        "v9_compact_report_sha256": compact_sha,
        "v11_selected_trace_candidate_replay": {
            "metadata_window_sha256": "c" * 64,
        },
    })
    _write_json(checker_path, {"accepted": True})
    _write_json(accepted_receipt_path, {"accepted": True})

    new_window_sha = "a" * 64
    window_path = repo_root / "controller" / "synthetic_window.json"
    accounting_path = repo_root / "controller" / "synthetic_accounting.jsonl"
    _write_json(window_path, {"synthetic": True})
    accounting_path.write_text("", encoding="utf-8")
    contract_path = repo_root / "consumer_contract.json"
    raw_policy = {
        "scope": "task41_b0_v3_recovery_evidence",
        "raw_artifact_limit_bytes": 16 << 30,
        "free_space_floor_bytes": 2 << 30,
        "authorization": "user_20261019_16gib_evidence_only",
        "new_evidence_limit_bytes": 512 * 1024**2,
    }
    contract = {
        "schema": contract_module.TASK41_P0_CONTRACT_SCHEMA,
        "task_id": "Task41 P0 synthetic route",
        "branch": "synthetic-v14-route",
        "source": {"sha": "4" * 40},
        "case": {
            "model_id": contract_module.TASK41_MODEL_ID,
            "run_id": contract_module.TASK41_B0_RUN_ID,
            "input_path": str(input_path),
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        },
        "window": {"path": str(window_path), "sha256": new_window_sha},
        "runtime": {"abi_receipt_sha256": "5" * 64},
        "resources": {
            "task_memory_max_bytes": 8 << 30,
            "host_reserve_bytes": 1 << 30,
            "memory_swap_max_bytes": 0,
        },
        "execution_scope": contract_module.TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
        "evidence": {"raw_disk_policy": raw_policy},
    }
    _write_json(contract_path, contract)
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    prior_window_sha = "c" * 64
    for old_sha in {v14_io.V14_SOURCE_WINDOW_SHA256, prior_window_sha}:
        (results_root / "task41_p0_saved_diagnostics_6h" / old_sha).mkdir(parents=True)

    accepted_hashes = {
        producer_report_path.resolve(): v14_io.V14_V11_REPORT_SHA256,
        checker_path.resolve(): v14_io.V14_ACCEPTED_CHECKER_SHA256,
        accepted_receipt_path.resolve(): v14_io.V14_ACCEPTED_RECEIPT_SHA256,
        donor_contract_path.resolve(): v14_io.V14_DONOR_CONTRACT_SHA256,
        manifest_path.resolve(): donor_solver.TASK41_V4_DONOR_MANIFEST_SHA256,
        compact_path.resolve(): compact_sha,
    }

    def sha256_file(path: Path) -> str:
        resolved = Path(path).resolve()
        if resolved in accepted_hashes:
            return accepted_hashes[resolved]
        return hashlib.sha256(resolved.read_bytes()).hexdigest()

    verifier_calls = []

    def registered_contract_verifier(path, **kwargs):
        verifier_calls.append((Path(path).resolve(), kwargs))
        return ({"source": {"sha": "1" * 40}}, v14_io.V14_DONOR_CONTRACT_SHA256)

    monkeypatch.setattr(contract_module, "require_task41_p0_contract", registered_contract_verifier)
    monkeypatch.setattr(
        service_workflow.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=(16 << 30)),
    )

    output_root = (
        results_root / "task41_p0_saved_diagnostics_6h" / new_window_sha
        / "selected_incident_replay" / "attempt01"
    )
    suffix = [
        "--task41-p0-saved-b0-evidence-audit",
        "--donor-contract", str(donor_contract_path),
        "--donor-contract-sha256", v14_io.V14_DONOR_CONTRACT_SHA256,
        "--summary", str(summary_path),
        "--numerical-output", str(numerical_output),
        "--output-dir", str(output_root),
        "--v14-saved-rhs-candidate",
        "--v11-report", str(producer_report_path),
        "--v11-report-sha256", v14_io.V14_V11_REPORT_SHA256,
        "--accepted-checker", str(checker_path),
        "--accepted-checker-sha256", v14_io.V14_ACCEPTED_CHECKER_SHA256,
        "--accepted-receipt", str(accepted_receipt_path),
        "--accepted-receipt-sha256", v14_io.V14_ACCEPTED_RECEIPT_SHA256,
        "--donor-summary-sha256", hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    ]
    parsed = service_workflow._parse_task41_p0_v14_candidate_suffix(suffix)
    assert len(suffix) == 26
    assert parsed == (
        producer_report_path.resolve(), v14_io.V14_V11_REPORT_SHA256,
        checker_path.resolve(), v14_io.V14_ACCEPTED_CHECKER_SHA256,
        accepted_receipt_path.resolve(), v14_io.V14_ACCEPTED_RECEIPT_SHA256,
        hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    )

    supervisor_calls = []

    def fake_supervise(command, directory, **kwargs):
        supervisor_calls.append((command, Path(directory), kwargs))
        module_name = command[2]
        if module_name == "src.runners.task41_p0_v14_saved_rhs_candidate":
            candidate_dir = Path(command[command.index("--output-dir") + 1])
            candidate_dir.mkdir(parents=True, exist_ok=True)
            extension_mode = "--v14-saved-star-extension" in command
            _write_json(candidate_dir / "task41_p0_v14_saved_rhs_candidate.json", {
                "schema": v14_io.V14_CANDIDATE_REPORT_SCHEMA,
                "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
                "official_result": False,
                "scientific_qualified": False,
                "consumer_contract_sha256": contract_sha,
                "consumer_window_sha256": new_window_sha,
                "producer_report_sha256": v14_io.V14_V11_REPORT_SHA256,
                "star_producer_report_sha256": (
                    v14_io.V14_V8_STAR_REPORT_SHA256 if extension_mode else None
                ),
                "scope": {"stage": "saved_star_extension" if extension_mode else "initial_screen"},
            })
        elif module_name == "src.runners.task41_p0_v14_saved_rhs_checker":
            output_path = Path(command[command.index("--output") + 1])
            extension_mode = "--v14-saved-star-extension" in command
            if "--decimal-residual-recheck-only" in command:
                _write_json(output_path, {
                    "schema": "task41.p0.v14.saved_rhs_decimal_residual_recheck.v1",
                    "stage": "saved_star_extension" if extension_mode else "initial_screen",
                    "status": "LOCAL_CANDIDATE_PASS" if extension_mode else "INCONCLUSIVE",
                    "classification": "DECIMAL_SUPPLEMENTAL_INDEPENDENT_CHECK",
                    "check_completed": True,
                    "official_result": False,
                    "scientific_qualified": False,
                    "candidate_passed": True if extension_mode else None,
                    "conditional_star_coverage_unlocked": False,
                    "saved_coverage_ready": extension_mode,
                    "full_owner_unlocked": False,
                    "getrs_invoked": 0,
                    "getrs_added": 0,
                    "prior_check_status": "INCONCLUSIVE",
                    "candidate_report_sha256": command[
                        command.index("--candidate-report-sha256") + 1
                    ],
                    "review_contract_sha256": command[
                        command.index("--review-contract-sha256") + 1
                    ],
                    "fixed_window_sha256": new_window_sha,
                    "rhs_count": 4,
                    "state_count": 8,
                    "rows_per_state": 450,
                })
            else:
                _write_json(output_path, {
                    "schema": v14_io.V14_CANDIDATE_CHECK_SCHEMA,
                    "status": "INCONCLUSIVE" if extension_mode else "LOCAL_CANDIDATE_REJECTED",
                    "check_completed": True,
                    "candidate_passed": None if extension_mode else False,
                    "saved_coverage_ready": False,
                    "official_result": False,
                    "scientific_qualified": False,
                    "candidate_report_sha256": command[
                        command.index("--candidate-report-sha256") + 1
                    ],
                })
        else:
            raise AssertionError(f"unexpected supervised module: {module_name}")
        return {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "observed_child_pids": [12345],
            "descendants_cleared": True,
        }

    consumer_sha = "6" * 40
    environment = {
        "TASK41_P0_CHECKER_SOURCE_SHA": consumer_sha,
        "TASK41_P0_SAVED_B0_EVIDENCE_AUDIT": "1",
    }
    window = SimpleNamespace(
        path=window_path,
        sha256=new_window_sha,
        accounting_path=accounting_path,
        cutoff_seconds=300.0,
    )
    result = service_workflow._run_task41_p0_saved_output_service(
        unit="synthetic-v14-service",
        runtime_prefix=repo_root / ".venv",
        environment=environment,
        window=window,
        contract=contract,
        contract_path=contract_path,
        contract_sha=contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=output_root,
        consumer_source_sha=consumer_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_evidence_audit_mode=True,
        b0_v14_saved_rhs_candidate_mode=True,
        v14_producer_report_path=parsed[0],
        v14_producer_report_sha256=parsed[1],
        v14_accepted_checker_path=parsed[2],
        v14_accepted_checker_sha256=parsed[3],
        v14_accepted_receipt_path=parsed[4],
        v14_accepted_receipt_sha256=parsed[5],
        v14_donor_summary_sha256=parsed[6],
        donor_contract_path=donor_contract_path,
        donor_contract_sha256=v14_io.V14_DONOR_CONTRACT_SHA256,
        donor_summary_path=summary_path,
        donor_numerical_output=numerical_output,
        input_path=input_path,
        activation_command=["activate", "synthetic"],
        activation_identity="synthetic-qualified-activation",
        preflight={"passed": True},
        preflight_command=["python", "-m", "synthetic_preflight"],
        cgroup_start={"dedicated_job_cgroup": True},
        service_entry_accounting={"synthetic": True},
        service_start_sample=service_workflow.clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=sha256_file,
    )

    assert result == 0
    assert len(supervisor_calls) == 2
    assert [call[0][2] for call in supervisor_calls] == [
        "src.runners.task41_p0_v14_saved_rhs_candidate",
        "src.runners.task41_p0_v14_saved_rhs_checker",
    ]
    assert all(call[2]["campaign_window_path"] == window_path for call in supervisor_calls)
    assert all(call[2]["campaign_window_sha256"] == new_window_sha for call in supervisor_calls)
    assert all(call[2]["campaign_accounting_path"] == accounting_path for call in supervisor_calls)
    assert len(verifier_calls) == 1
    assert verifier_calls[0][0] == donor_contract_path.resolve()
    assert verifier_calls[0][1]["expected_sha256"] == v14_io.V14_DONOR_CONTRACT_SHA256

    receipt_path = output_root.with_name(output_root.name + ".service") / "task41_p0_service_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["result_classification"] == "V14_LOCAL_CANDIDATE_REJECTED"
    assert receipt["required_checker_status"] == "INDEPENDENT_CHECK_COMPLETED"
    assert receipt["v14_candidate_worker_attempted"] is True
    assert receipt["v14_candidate_worker_started"] is True
    assert receipt["v14_candidate_worker_completed"] is True
    assert receipt["numerical_work_started"] is True
    assert receipt["v14_candidate_passed"] is False
    assert receipt["conditional_star_coverage_unlocked"] is False
    assert receipt["official_result"] is False
    assert receipt["scientific_qualified"] is False


    # The supplemental service route consumes the saved candidate/check only and
    # supervises the Decimal checker; it must never launch the candidate worker.
    source_consumer_contract_path = results_root / "attempt01" / "source_consumer_contract.json"
    _write_json(source_consumer_contract_path, {
        "schema": contract_module.TASK41_P0_CONTRACT_SCHEMA,
        "source": {"sha": "7" * 40},
        "window": {"path": str(window_path), "sha256": new_window_sha},
    })
    source_consumer_contract_sha = hashlib.sha256(
        source_consumer_contract_path.read_bytes()
    ).hexdigest()
    saved_candidate_path = results_root / "attempt01" / "candidate" / "task41_p0_v14_saved_rhs_candidate.json"
    saved_candidate_payload = {
        "schema": v14_io.V14_CANDIDATE_REPORT_SCHEMA,
        "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
        "official_result": False,
        "scientific_qualified": False,
        "consumer_contract_path": str(source_consumer_contract_path),
        "consumer_contract_sha256": source_consumer_contract_sha,
        "consumer_window_sha256": new_window_sha,
        "scope": {
            "stage": "initial_screen",
            "cells": list(v14_io.V14_CELLS),
            "columns": list(v14_io.V14_COLUMNS),
            "full_owner": False,
        },
        "candidate_rhs": [],
        "getrs_count": 0,
    }
    saved_candidate_sha = hashlib.sha256(
        json.dumps(saved_candidate_payload, sort_keys=True).encode()
    ).hexdigest()
    _write_json(saved_candidate_path, saved_candidate_payload)
    saved_candidate_sha = hashlib.sha256(saved_candidate_path.read_bytes()).hexdigest()
    prior_check_path = results_root / "attempt01" / "task41_p0_v14_saved_rhs_candidate_independent_check.json"
    _write_json(prior_check_path, {
        "schema": v14_io.V14_CANDIDATE_CHECK_SCHEMA,
        "status": "INCONCLUSIVE",
        "check_completed": True,
        "candidate_passed": None,
        "official_result": False,
        "scientific_qualified": False,
        "candidate_report_path": str(saved_candidate_path.resolve()),
        "candidate_report_sha256": saved_candidate_sha,
        "consumer_contract_sha256": source_consumer_contract_sha,
        "consumer_window_sha256": new_window_sha,
    })
    prior_check_sha = hashlib.sha256(prior_check_path.read_bytes()).hexdigest()
    decimal_output_root = (
        results_root / "task41_p0_saved_diagnostics_6h" / new_window_sha
        / "selected_incident_replay" / "attempt02"
    )
    decimal_suffix = [
        *suffix[:10], str(decimal_output_root), *suffix[11:],
        "--v14-decimal-residual-recheck-only",
        "--source-consumer-contract", str(source_consumer_contract_path),
        "--source-consumer-contract-sha256", source_consumer_contract_sha,
        "--candidate-report", str(saved_candidate_path),
        "--candidate-report-sha256", saved_candidate_sha,
        "--prior-independent-check", str(prior_check_path),
        "--prior-independent-check-sha256", prior_check_sha,
    ]
    parsed_decimal = service_workflow._parse_task41_p0_v14_decimal_recheck_suffix(
        decimal_suffix
    )
    assert len(decimal_suffix) == 39
    assert parsed_decimal[:7] == parsed
    assert parsed_decimal[7:] == (
        source_consumer_contract_path.resolve(), source_consumer_contract_sha,
        saved_candidate_path.resolve(), saved_candidate_sha,
        prior_check_path.resolve(), prior_check_sha,
    )

    decimal_result = service_workflow._run_task41_p0_saved_output_service(
        unit="synthetic-v14-decimal-checker-only-service",
        runtime_prefix=repo_root / ".venv",
        environment=environment,
        window=window,
        contract=contract,
        contract_path=contract_path,
        contract_sha=contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=decimal_output_root,
        consumer_source_sha=consumer_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_evidence_audit_mode=True,
        b0_v14_saved_rhs_candidate_mode=True,
        b0_v14_decimal_residual_recheck_only_mode=True,
        v14_source_consumer_contract_path=parsed_decimal[7],
        v14_source_consumer_contract_sha256=parsed_decimal[8],
        v14_saved_candidate_report_path=parsed_decimal[9],
        v14_saved_candidate_report_sha256=parsed_decimal[10],
        v14_prior_independent_check_path=parsed_decimal[11],
        v14_prior_independent_check_sha256=parsed_decimal[12],
        v14_producer_report_path=parsed_decimal[0],
        v14_producer_report_sha256=parsed_decimal[1],
        v14_accepted_checker_path=parsed_decimal[2],
        v14_accepted_checker_sha256=parsed_decimal[3],
        v14_accepted_receipt_path=parsed_decimal[4],
        v14_accepted_receipt_sha256=parsed_decimal[5],
        v14_donor_summary_sha256=parsed_decimal[6],
        donor_contract_path=donor_contract_path,
        donor_contract_sha256=v14_io.V14_DONOR_CONTRACT_SHA256,
        donor_summary_path=summary_path,
        donor_numerical_output=numerical_output,
        input_path=input_path,
        activation_command=["activate", "synthetic"],
        activation_identity="synthetic-qualified-activation",
        preflight={"passed": True},
        preflight_command=["python", "-m", "synthetic_preflight"],
        cgroup_start={"dedicated_job_cgroup": True},
        service_entry_accounting={"synthetic": True},
        service_start_sample=service_workflow.clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=sha256_file,
    )
    assert decimal_result == 0
    assert len(supervisor_calls) == 3
    decimal_command, decimal_watchdog_dir, decimal_watchdog_args = supervisor_calls[-1]
    assert decimal_command[2] == "src.runners.task41_p0_v14_saved_rhs_checker"
    assert "--decimal-residual-recheck-only" in decimal_command
    assert "src.runners.task41_p0_v14_saved_rhs_candidate" not in decimal_command
    assert decimal_watchdog_dir.name == "v14_decimal_residual_checker_watchdog"
    assert decimal_watchdog_args["campaign_window_path"] == window_path
    assert decimal_watchdog_args["campaign_window_sha256"] == new_window_sha
    decimal_receipt_path = (
        decimal_output_root.with_name(decimal_output_root.name + ".service")
        / "task41_p0_service_receipt.json"
    )
    decimal_receipt = json.loads(decimal_receipt_path.read_text(encoding="utf-8"))
    assert decimal_receipt["result_classification"] == "V14_DECIMAL_SUPPLEMENTAL_INCONCLUSIVE"
    assert decimal_receipt["required_checker_status"] == "DECIMAL_SUPPLEMENTAL_CHECK_COMPLETED"
    assert decimal_receipt["v14_candidate_worker_attempted"] is False
    assert decimal_receipt["v14_candidate_worker_started"] is False
    assert decimal_receipt["v14_candidate_worker_completed"] is False
    assert decimal_receipt["numerical_work_started"] is False
    assert decimal_receipt["getrs_added"] == 0
    assert decimal_receipt["conditional_star_coverage_unlocked"] is False
    assert decimal_receipt["full_owner_unlocked"] is False
    assert decimal_receipt["official_result"] is False
    assert decimal_receipt["scientific_qualified"] is False



    # The saved-star route accepts attempt paths by binding and SHA rather than
    # pinning attempt01/03 names, and carries all five inputs into both workers.
    v8_star_report_path = results_root / "v8-producer" / "saved_star_report.json"
    _write_json(v8_star_report_path, {"schema": "synthetic-v8"})
    accepted_hashes[v8_star_report_path.resolve()] = v14_io.V14_V8_STAR_REPORT_SHA256
    prior_root = (
        results_root / "task41_p0_saved_diagnostics_6h" / new_window_sha
        / "selected_incident_replay" / "attempt99"
    )
    prior_candidate_path = prior_root / "candidate" / "prior_candidate.json"
    prior_checker_path = prior_root / "prior_checker.json"
    prior_decimal_path = prior_root / "prior_decimal.json"
    prior_receipt_path = prior_root.with_name("attempt99.service") / "prior_receipt.json"
    for path, name in (
        (prior_candidate_path, "candidate"),
        (prior_checker_path, "checker"),
        (prior_decimal_path, "decimal"),
        (prior_receipt_path, "receipt"),
    ):
        _write_json(path, {"synthetic": name})
    extension_inputs = [
        "--v14-saved-star-extension",
        "--v8-star-report", str(v8_star_report_path),
        "--v8-star-report-sha256", v14_io.V14_V8_STAR_REPORT_SHA256,
        "--prior-candidate-report", str(prior_candidate_path),
        "--prior-candidate-report-sha256", sha256_file(prior_candidate_path),
        "--prior-checker", str(prior_checker_path),
        "--prior-checker-sha256", sha256_file(prior_checker_path),
        "--prior-decimal-report", str(prior_decimal_path),
        "--prior-decimal-report-sha256", sha256_file(prior_decimal_path),
        "--prior-service-receipt", str(prior_receipt_path),
        "--prior-service-receipt-sha256", sha256_file(prior_receipt_path),
    ]
    parsed_extension = service_workflow._parse_task41_p0_v14_candidate_suffix(
        [*suffix, *extension_inputs]
    )
    extension_output_root = (
        results_root / "task41_p0_saved_diagnostics_6h" / new_window_sha
        / "selected_incident_replay" / "attempt04"
    )
    extension_result = service_workflow._run_task41_p0_saved_output_service(
        unit="synthetic-v14-star-extension-service",
        runtime_prefix=repo_root / ".venv",
        environment=environment,
        window=window,
        contract=contract,
        contract_path=contract_path,
        contract_sha=contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=extension_output_root,
        consumer_source_sha=consumer_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_evidence_audit_mode=True,
        b0_v14_saved_rhs_candidate_mode=True,
        b0_v14_saved_star_extension_mode=True,
        v14_producer_report_path=parsed_extension[0],
        v14_producer_report_sha256=parsed_extension[1],
        v14_accepted_checker_path=parsed_extension[2],
        v14_accepted_checker_sha256=parsed_extension[3],
        v14_accepted_receipt_path=parsed_extension[4],
        v14_accepted_receipt_sha256=parsed_extension[5],
        v14_donor_summary_sha256=parsed_extension[6],
        v14_v8_star_report_path=parsed_extension[7],
        v14_v8_star_report_sha256=parsed_extension[8],
        v14_prior_candidate_report_path=parsed_extension[9],
        v14_prior_candidate_report_sha256=parsed_extension[10],
        v14_prior_checker_path=parsed_extension[11],
        v14_prior_checker_sha256=parsed_extension[12],
        v14_prior_decimal_report_path=parsed_extension[13],
        v14_prior_decimal_report_sha256=parsed_extension[14],
        v14_prior_service_receipt_path=parsed_extension[15],
        v14_prior_service_receipt_sha256=parsed_extension[16],
        donor_contract_path=donor_contract_path,
        donor_contract_sha256=v14_io.V14_DONOR_CONTRACT_SHA256,
        donor_summary_path=summary_path,
        donor_numerical_output=numerical_output,
        input_path=input_path,
        activation_command=["activate", "synthetic"],
        activation_identity="synthetic-qualified-activation",
        preflight={"passed": True},
        preflight_command=["python", "-m", "synthetic_preflight"],
        cgroup_start={"dedicated_job_cgroup": True},
        service_entry_accounting={"synthetic": True},
        service_start_sample=service_workflow.clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=sha256_file,
    )
    assert extension_result == 0
    candidate_command = supervisor_calls[-2][0]
    extension_checker_command = supervisor_calls[-1][0]
    assert "--v14-saved-star-extension" in candidate_command
    assert "--v14-saved-star-extension" in extension_checker_command
    extension_receipt_path = (
        extension_output_root.with_name(extension_output_root.name + ".service")
        / "task41_p0_service_receipt.json"
    )
    extension_receipt = json.loads(extension_receipt_path.read_text(encoding="utf-8"))
    assert extension_receipt["result_classification"] == "V14_LOCAL_CANDIDATE_INCONCLUSIVE"
    assert extension_receipt["v14_saved_star_extension"] is True
    assert extension_receipt["saved_star_coverage_ready"] is False
    assert extension_receipt["conditional_star_coverage_unlocked"] is False
    assert extension_receipt["full_owner_unlocked"] is False

    # Run the parameterized Decimal supplemental route for that exact extension
    # output; it is checker-only and must not invoke the candidate worker again.
    extension_candidate_path = extension_output_root / "candidate" / "task41_p0_v14_saved_rhs_candidate.json"
    extension_candidate_sha = sha256_file(extension_candidate_path)
    extension_check_path = extension_output_root / "task41_p0_v14_saved_rhs_candidate_independent_check.json"
    extension_check_sha = sha256_file(extension_check_path)
    extension_decimal_output = (
        results_root / "task41_p0_saved_diagnostics_6h" / new_window_sha
        / "selected_incident_replay" / "attempt05"
    )
    extension_decimal_suffix = [
        *suffix[:10], str(extension_decimal_output), *suffix[11:],
        "--v14-decimal-residual-recheck-only",
        "--source-consumer-contract", str(source_consumer_contract_path),
        "--source-consumer-contract-sha256", source_consumer_contract_sha,
        "--candidate-report", str(extension_candidate_path),
        "--candidate-report-sha256", extension_candidate_sha,
        "--prior-independent-check", str(extension_check_path),
        "--prior-independent-check-sha256", extension_check_sha,
        *extension_inputs,
    ]
    parsed_extension_decimal = service_workflow._parse_task41_p0_v14_decimal_recheck_suffix(
        extension_decimal_suffix
    )
    extension_decimal_result = service_workflow._run_task41_p0_saved_output_service(
        unit="synthetic-v14-star-extension-decimal-service",
        runtime_prefix=repo_root / ".venv",
        environment=environment,
        window=window,
        contract=contract,
        contract_path=contract_path,
        contract_sha=contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=extension_decimal_output,
        consumer_source_sha=consumer_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_evidence_audit_mode=True,
        b0_v14_saved_rhs_candidate_mode=True,
        b0_v14_decimal_residual_recheck_only_mode=True,
        b0_v14_saved_star_extension_mode=True,
        v14_source_consumer_contract_path=parsed_extension_decimal[7],
        v14_source_consumer_contract_sha256=parsed_extension_decimal[8],
        v14_saved_candidate_report_path=parsed_extension_decimal[9],
        v14_saved_candidate_report_sha256=parsed_extension_decimal[10],
        v14_prior_independent_check_path=parsed_extension_decimal[11],
        v14_prior_independent_check_sha256=parsed_extension_decimal[12],
        v14_producer_report_path=parsed_extension_decimal[0],
        v14_producer_report_sha256=parsed_extension_decimal[1],
        v14_accepted_checker_path=parsed_extension_decimal[2],
        v14_accepted_checker_sha256=parsed_extension_decimal[3],
        v14_accepted_receipt_path=parsed_extension_decimal[4],
        v14_accepted_receipt_sha256=parsed_extension_decimal[5],
        v14_donor_summary_sha256=parsed_extension_decimal[6],
        v14_v8_star_report_path=parsed_extension_decimal[13],
        v14_v8_star_report_sha256=parsed_extension_decimal[14],
        v14_prior_candidate_report_path=parsed_extension_decimal[15],
        v14_prior_candidate_report_sha256=parsed_extension_decimal[16],
        v14_prior_checker_path=parsed_extension_decimal[17],
        v14_prior_checker_sha256=parsed_extension_decimal[18],
        v14_prior_decimal_report_path=parsed_extension_decimal[19],
        v14_prior_decimal_report_sha256=parsed_extension_decimal[20],
        v14_prior_service_receipt_path=parsed_extension_decimal[21],
        v14_prior_service_receipt_sha256=parsed_extension_decimal[22],
        donor_contract_path=donor_contract_path,
        donor_contract_sha256=v14_io.V14_DONOR_CONTRACT_SHA256,
        donor_summary_path=summary_path,
        donor_numerical_output=numerical_output,
        input_path=input_path,
        activation_command=["activate", "synthetic"],
        activation_identity="synthetic-qualified-activation",
        preflight={"passed": True},
        preflight_command=["python", "-m", "synthetic_preflight"],
        cgroup_start={"dedicated_job_cgroup": True},
        service_entry_accounting={"synthetic": True},
        service_start_sample=service_workflow.clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=sha256_file,
    )
    assert extension_decimal_result == 0
    extension_decimal_command = supervisor_calls[-1][0]
    assert extension_decimal_command[2] == "src.runners.task41_p0_v14_saved_rhs_checker"
    assert "--decimal-residual-recheck-only" in extension_decimal_command
    assert "--v14-saved-star-extension" in extension_decimal_command
    assert "src.runners.task41_p0_v14_saved_rhs_candidate" not in extension_decimal_command
    extension_decimal_receipt_path = (
        extension_decimal_output.with_name(extension_decimal_output.name + ".service")
        / "task41_p0_service_receipt.json"
    )
    extension_decimal_receipt = json.loads(extension_decimal_receipt_path.read_text(encoding="utf-8"))
    assert extension_decimal_receipt["result_classification"] == "V14_SAVED_COVERAGE_DECIMAL_PASS_NOT_GLOBAL"
    assert extension_decimal_receipt["saved_star_coverage_ready"] is True
    assert extension_decimal_receipt["conditional_star_coverage_unlocked"] is False
    assert extension_decimal_receipt["full_owner_unlocked"] is False
    assert extension_decimal_receipt["v14_candidate_worker_attempted"] is False
    assert extension_decimal_receipt["getrs_added"] == 0


def test_v14_saved_star_extension_exact_suffix_binds_all_inputs(tmp_path):
    paths = {}
    for name in (
        "producer", "accepted_checker", "accepted_receipt", "v8_star",
        "prior_candidate", "prior_checker", "prior_decimal", "prior_receipt",
        "source_contract", "current_candidate", "current_checker",
    ):
        path = tmp_path / f"{name}.json"
        _write_json(path, {"name": name})
        paths[name] = path

    base = [
        "--task41-p0-saved-b0-evidence-audit",
        "--donor-contract", str(paths["source_contract"]),
        "--donor-contract-sha256", "d" * 64,
        "--summary", str(paths["source_contract"]),
        "--numerical-output", str(tmp_path),
        "--output-dir", str(tmp_path / "attempt01"),
        "--v14-saved-rhs-candidate",
        "--v11-report", str(paths["producer"]),
        "--v11-report-sha256", "1" * 64,
        "--accepted-checker", str(paths["accepted_checker"]),
        "--accepted-checker-sha256", "2" * 64,
        "--accepted-receipt", str(paths["accepted_receipt"]),
        "--accepted-receipt-sha256", "3" * 64,
        "--donor-summary-sha256", "4" * 64,
    ]
    extension = [
        "--v14-saved-star-extension",
        "--v8-star-report", str(paths["v8_star"]),
        "--v8-star-report-sha256", v14_io.V14_V8_STAR_REPORT_SHA256,
        "--prior-candidate-report", str(paths["prior_candidate"]),
        "--prior-candidate-report-sha256", "5" * 64,
        "--prior-checker", str(paths["prior_checker"]),
        "--prior-checker-sha256", "6" * 64,
        "--prior-decimal-report", str(paths["prior_decimal"]),
        "--prior-decimal-report-sha256", "7" * 64,
        "--prior-service-receipt", str(paths["prior_receipt"]),
        "--prior-service-receipt-sha256", "8" * 64,
    ]
    parsed = service_workflow._parse_task41_p0_v14_candidate_suffix([*base, *extension])
    assert len([*base, *extension]) == 47
    assert parsed[:7] == (
        paths["producer"].resolve(), "1" * 64,
        paths["accepted_checker"].resolve(), "2" * 64,
        paths["accepted_receipt"].resolve(), "3" * 64, "4" * 64,
    )
    assert parsed[7:] == (
        paths["v8_star"].resolve(), v14_io.V14_V8_STAR_REPORT_SHA256,
        paths["prior_candidate"].resolve(), "5" * 64,
        paths["prior_checker"].resolve(), "6" * 64,
        paths["prior_decimal"].resolve(), "7" * 64,
        paths["prior_receipt"].resolve(), "8" * 64,
    )

    decimal = [
        "--v14-decimal-residual-recheck-only",
        "--source-consumer-contract", str(paths["source_contract"]),
        "--source-consumer-contract-sha256", "9" * 64,
        "--candidate-report", str(paths["current_candidate"]),
        "--candidate-report-sha256", "a" * 64,
        "--prior-independent-check", str(paths["current_checker"]),
        "--prior-independent-check-sha256", "b" * 64,
    ]
    parsed_decimal = service_workflow._parse_task41_p0_v14_decimal_recheck_suffix(
        [*base, *decimal, *extension]
    )
    assert len([*base, *decimal, *extension]) == 60
    assert parsed_decimal[:7] == parsed[:7]
    assert parsed_decimal[7:13] == (
        paths["source_contract"].resolve(), "9" * 64,
        paths["current_candidate"].resolve(), "a" * 64,
        paths["current_checker"].resolve(), "b" * 64,
    )
    assert parsed_decimal[13:] == parsed[7:]
