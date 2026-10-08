import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.solvers import task40_v18_ny8_operator_reuse as reuse


PROFILE = reuse.V18_NY8_PROFILE
SOURCE_SHA = "b" * 40
NEW_SOURCE_SHA = "c" * 40
INPUT_SHA = "1" * 64
PHYSICAL_SHA = "2" * 64
MODE_SHA = "3" * 64
ABI = {"receipt_sha256": "a" * 64, "scalar": "complex128", "integer": "int32"}


class _Matrix:
    shape = (2, 2)
    nnz = 3

    def __init__(self, q):
        self.q = q


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    for relative in reuse.OPERATOR_SOURCE_DEPENDENCIES:
        dependency = root / relative
        dependency.parent.mkdir(parents=True, exist_ok=True)
        dependency.write_bytes(f"dependency:{relative}".encode())

    monkeypatch.setattr(
        "src.runners.task40_v10_output_checker._registered_v15_profile_inventory",
        lambda _identity: {"identity": PROFILE, "q_count": 8, "mode_count": 532},
    )
    monkeypatch.setattr(
        "src.runners.task40_v10_output_checker._verify_v18_ny8_operator_qualification",
        lambda _summary, _inventory: {"passed": True, "status": "PASS"},
    )
    monkeypatch.setattr(
        "src.solvers.task40_v10_p6_mumps._sparse_content_sha256",
        lambda matrix: hashlib.sha256(f"q-matrix-{matrix.q}".encode()).hexdigest(),
    )

    matrices = {q: _Matrix(q) for q in range(8)}
    factor_inputs = []
    for q in range(8):
        matrix_sha = hashlib.sha256(f"q-matrix-{q}".encode()).hexdigest()
        factor_inputs.append(
            {
                "q": q,
                "shape": [2, 2],
                "nnz": 3,
                "input_identity_unchanged": True,
                "caller_input_sha256_before": matrix_sha,
                "caller_input_sha256_after": matrix_sha,
                "factor_csr_sha256_before": matrix_sha,
                "factor_csr_sha256_after": matrix_sha,
            }
        )
    factor_snapshot = {
        "max_simultaneous_factors": 8,
        "factors_live_count_current": 8,
        "all_q_numeric_factors_strict_true_residual_passed": True,
        "factor_inputs": factor_inputs,
    }
    operator = {
        "schema": "test.operator.v1",
        "passed": True,
        "mode_identities_covered_once": True,
        "original_H_mode_count": 532,
    }
    error = {
        "type": "ValueError",
        "message": "V15 candidate budget must contain both twist-sector lift terms",
    }
    old_root = root / "results" / "old-run"
    old_root.mkdir(parents=True)
    for name, value in (
        ("source_sha.txt", SOURCE_SHA),
        ("input_sha256.txt", INPUT_SHA),
        ("physical_model_sha256.txt", PHYSICAL_SHA),
    ):
        (old_root / name).write_text(value + "\n", encoding="ascii")

    summary = {
        "status": "FAILED",
        "result_classification": "WORKER_FAILED",
        "source_sha": SOURCE_SHA,
        "profile": PROFILE,
        "abi": ABI,
        "error": error,
        "periodic_inventory_expectations": {
            "name": PROFILE,
            "q_count": 8,
            "mode_count": 532,
            "all_q_required": True,
        },
        "reference_audit_snapshot": {
            "complete_operator_qualification": operator,
            "factor_audit_before_destroy": factor_snapshot,
        },
    }
    summary_path = old_root / "task40_v10_p6_candidate_summary.json"
    summary_sha = _write_json(summary_path, summary)
    manifest = {
        "status": "finished",
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
        "source_sha": SOURCE_SHA,
        "input_sha256": INPUT_SHA,
        "physical_model_sha256": PHYSICAL_SHA,
        "solver": {"preconditioner": PROFILE},
    }
    manifest_path = old_root / "run_manifest.json"
    manifest_sha = _write_json(manifest_path, manifest)

    old_attempt = {
        "run_root": str(old_root.relative_to(root)),
        "source_sha": SOURCE_SHA,
        "profile_identity": PROFILE,
        "input_sha256": INPUT_SHA,
        "physical_model_sha256": PHYSICAL_SHA,
        "target_mode_sha256": MODE_SHA,
        "abi_identity": ABI,
        "mode_count": 532,
        "candidate_summary_path": str(summary_path.relative_to(root)),
        "candidate_summary_sha256": summary_sha,
        "run_manifest_path": str(manifest_path.relative_to(root)),
        "run_manifest_sha256": manifest_sha,
        "error": error,
        "exit_status": 4,
        "factor_inputs": factor_inputs,
        "factor_audit_before_destroy": factor_snapshot,
        "complete_operator_qualification": operator,
        "complete_operator_qualification_sha256": reuse._json_sha256(operator),
    }
    dependencies = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in reuse.OPERATOR_SOURCE_DEPENDENCIES
    }
    new_attempt = {
        "source_sha": NEW_SOURCE_SHA,
        "profile_identity": PROFILE,
        "input_sha256": INPUT_SHA,
        "physical_model_sha256": PHYSICAL_SHA,
        "target_mode_sha256": MODE_SHA,
        "abi_identity": ABI,
        "source_dependency_sha256": dependencies,
    }
    receipt = {
        "schema": "task40extra.review_v18_ny8_operator_reuse_receipt.v1",
        "original_attempt": old_attempt,
        "new_attempt": new_attempt,
    }
    receipt_path = root / "receipt.json"
    receipt_sha = _write_json(receipt_path, receipt)
    return SimpleNamespace(
        root=root,
        matrices=matrices,
        summary_path=summary_path,
        summary=summary,
        receipt=receipt,
        receipt_path=receipt_path,
        receipt_sha=receipt_sha,
    )


def _validate(fixture, *, expected_receipt_sha256=None):
    return reuse.reuse_v18_ny8_operator_qualification(
        repo_root=fixture.root,
        receipt_path=fixture.receipt_path,
        candidate_q_matrices=fixture.matrices,
        profile=SimpleNamespace(name=PROFILE),
        source_sha=NEW_SOURCE_SHA,
        input_sha256=INPUT_SHA,
        physical_model_sha256=PHYSICAL_SHA,
        target_mode_sha256=MODE_SHA,
        abi_identity=ABI,
        expected_receipt_sha256=expected_receipt_sha256 or fixture.receipt_sha,
    )


def test_reuse_requires_expected_receipt_hash_and_rechecks_original_attempt(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)

    operator, facts = _validate(fixture)

    assert operator["passed"] is True
    assert facts["receipt_sha256"] == facts["expected_receipt_sha256"]
    assert facts["original_candidate_summary_sha256"] == fixture.receipt[
        "original_attempt"
    ]["candidate_summary_sha256"]
    assert facts["original_status"] == "FAILED"
    assert facts["original_result_classification"] == "WORKER_FAILED"
    assert facts["old_attempt_failure_preserved"] is True
    assert facts["all_eight_fresh_q_hashes_match"] is True


def test_rejects_wrong_expected_receipt_hash(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="frozen expected SHA256"):
        _validate(fixture, expected_receipt_sha256="0" * 64)


def test_rejects_changed_original_candidate_summary_file(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    fixture.summary_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="original candidate summary SHA256"):
        _validate(fixture)


def test_rejects_original_factor_snapshot_missing_one_q(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    snapshot = fixture.summary["reference_audit_snapshot"]["factor_audit_before_destroy"]
    snapshot["factor_inputs"] = snapshot["factor_inputs"][:-1]
    summary_sha = _write_json(fixture.summary_path, fixture.summary)
    old_attempt = fixture.receipt["original_attempt"]
    old_attempt["candidate_summary_sha256"] = summary_sha
    old_attempt["factor_audit_before_destroy"] = snapshot
    old_attempt["factor_inputs"] = snapshot["factor_inputs"]
    fixture.receipt_sha = _write_json(fixture.receipt_path, fixture.receipt)

    with pytest.raises(ValueError, match="all eight q-factor inputs"):
        _validate(fixture)


def test_rejects_fresh_q_hash_mismatch(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "src.solvers.task40_v10_p6_mumps._sparse_content_sha256",
        lambda matrix: hashlib.sha256(f"wrong-q-matrix-{matrix.q}".encode()).hexdigest()
        if matrix.q == 3
        else hashlib.sha256(f"q-matrix-{matrix.q}".encode()).hexdigest(),
    )

    with pytest.raises(ValueError, match="q=3 CSR differs"):
        _validate(fixture)
