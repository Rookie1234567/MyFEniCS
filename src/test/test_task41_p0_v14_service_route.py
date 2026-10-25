from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from src.runners import task41_p0_contract as contract_module
from src.runners import task41_p0_v14_candidate_io as v14_io
from src.runners import task41_p0_v4_volume_only_audit as v4_audit
from src.solvers import task41_v4_volume_only_audit as donor_solver
from scripts import task40_v20_service_workflow as service_workflow


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


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
            _write_json(candidate_dir / "task41_p0_v14_saved_rhs_candidate.json", {
                "schema": v14_io.V14_CANDIDATE_REPORT_SCHEMA,
                "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
                "official_result": False,
                "scientific_qualified": False,
                "consumer_contract_sha256": contract_sha,
                "consumer_window_sha256": new_window_sha,
                "producer_report_sha256": v14_io.V14_V11_REPORT_SHA256,
            })
        elif module_name == "src.runners.task41_p0_v14_saved_rhs_checker":
            output_path = Path(command[command.index("--output") + 1])
            _write_json(output_path, {
                "schema": v14_io.V14_CANDIDATE_CHECK_SCHEMA,
                "status": "LOCAL_CANDIDATE_REJECTED",
                "check_completed": True,
                "candidate_passed": False,
                "official_result": False,
                "scientific_qualified": False,
                "candidate_report_sha256": command[command.index("--candidate-report-sha256") + 1],
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
