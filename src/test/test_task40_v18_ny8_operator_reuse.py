import hashlib
import json
from pathlib import Path
import subprocess
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


def _v19_factor_audit(q_count=8, *, refactors_per_q=2):
    build_count = q_count * refactors_per_q
    factor_inputs = []
    factor_tests = []
    build_history = []
    for build_index in range(build_count):
        q = build_index % q_count
        matrix_sha = hashlib.sha256(f"q-matrix-{q}".encode()).hexdigest()
        residual = 2.0e-15
        factor_inputs.append({
            "build_index": build_index,
            "q": q,
            "shape": [2, 2],
            "nnz": 3,
            "input_identity_unchanged": True,
            "caller_input_sha256_before": matrix_sha,
            "caller_input_sha256_after": matrix_sha,
            "factor_csr_sha256_before": matrix_sha,
            "factor_csr_sha256_after": matrix_sha,
        })
        factor_tests.append({
            "q": q,
            "relative_true_residual": residual,
            "strict_limit": 1.0e-10,
            "strict_passed": True,
            "admission_passed": True,
            "factor_lifecycle_strategy": "ONE_Q_REFACTOR_V19",
        })
        build_history.append({
            "build_index": build_index,
            "q": q,
            "factor_probe_mat_solve_count": 1,
            "factor_probe_passed": True,
            "probe_true_residual_relative": residual,
        })
    rhs_categories = (
        "pc_initial_rhs_mat_solve_count",
        "pc_augmentation_rhs_mat_solve_count",
        "startup_rhs_mat_solve_count",
        "other_validation_rhs_mat_solve_count",
    )
    invoked = {name: 0 for name in (*rhs_categories, "factor_probe_mat_solve_count")}
    completed = dict(invoked)
    failed = dict(invoked)
    invoked["other_validation_rhs_mat_solve_count"] = q_count
    invoked["factor_probe_mat_solve_count"] = build_count
    completed.update(invoked)
    rhs_completed = {name: 0 for name in rhs_categories}
    rhs_completed["other_validation_rhs_mat_solve_count"] = q_count
    q_counts = {str(q): 1 for q in range(q_count)}
    return {
        "factor_lifecycle_strategy": "ONE_Q_REFACTOR_V19",
        "all_q_required": list(range(q_count)),
        "input_q_coverage": list(range(q_count)),
        "all_q_source_csr_covered": True,
        "all_q_symbolic_covered": True,
        "all_q_fresh_factor_probe_covered": True,
        "all_q_solve_coverage": True,
        "solve_q_coverage": list(range(q_count)),
        "all_q_factors_simultaneously_resident": False,
        "all_q_factors_retained_simultaneously": False,
        "all_q_factors_reused": False,
        "all_q_numeric_factors_strict_true_residual_passed": True,
        "max_simultaneous_factors": 1,
        "max_simultaneous_matrices": 1,
        "factors_live_count_current": 1,
        "matrices_live_count_current": 1,
        "factor_inputs": factor_inputs,
        "factor_tests": factor_tests,
        "factor_build_history": build_history,
        "numeric_factor_build_count": build_count,
        "numeric_factor_build_attempt_count": build_count,
        "cache_miss_count": build_count,
        "q_rhs_solve_counts": q_counts,
        "q_rhs_mat_solve_invoked_counts": dict(q_counts),
        "mat_solve_invoked_count_by_category": invoked,
        "mat_solve_completed_count_by_category": completed,
        "mat_solve_failed_count_by_category": failed,
        "rhs_mat_solve_count_by_category": rhs_completed,
        "rhs_mat_solve_count": q_count,
        "calls": q_count,
        "factor_probe_mat_solve_count": build_count,
        "factor_probe_mat_solve_completed_count": build_count,
        "backend_mat_solve_invoked_total": build_count + q_count,
        "backend_mat_solve_completed_total": build_count + q_count,
        "backend_mat_solve_failed_total": 0,
        "mat_solve_total_identity_passed": True,
    }


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
    assert facts["independent_operator_checker"]["passed"] is True


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


def _v19_certificate_fixture(tmp_path, monkeypatch, *, result_status):
    root = tmp_path / "repo-v19"
    root.mkdir()
    checker_relative = "src/runners/task40_v10_output_checker.py"
    checker_path = root / checker_relative
    checker_path.parent.mkdir(parents=True)
    old_checker_source = (
        "def _verify_v18_ny8_operator_qualification(summary, profile_inventory):\n"
        "    return {'passed': True}\n\n"
        "def _verify_v18_packet_operator_qualification_binding(packet_identity, checked_operator):\n"
        "    return {'passed': True}\n\n"
        "def verify_v10_output_bundle(packet_json):\n"
        "    return {'status': 'PASS'}\n"
    ).encode()
    current_checker_source = (
        old_checker_source.replace(
            b"def verify_v10_output_bundle(packet_json):\n    return {'status': 'PASS'}\n",
            b"def verify_v10_output_bundle(packet_json):\n"
            b"    lifecycle = _verify_v19_one_q_factor_lifecycle(packet_json)\n"
            b"    return {'status': 'PASS', 'v19_lifecycle': lifecycle}\n",
        )
        + b"\ndef _verify_v19_one_q_factor_lifecycle(audit):\n    return {'passed': True}\n"
        + b"\ndef _verify_v19_run_lifecycle_binding(manifest):\n    return {'passed': True}\n"
    )
    checker_path.write_bytes(old_checker_source)
    subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Task40 fixture"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "task40-fixture@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "add", checker_relative], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "qualified V18 checker"], check=True)
    operator_checker_source_sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    checker_path.write_bytes(current_checker_source)
    changed = {
        checker_relative: (
            "v19_factor_lifecycle_checker_route_only",
            "V19 adds one-q lifecycle audit validation; both frozen V18 operator-checker functions remain unchanged.",
        ),
        "src/runners/task40_v10_worker.py": (
            "worker_resource_and_mat_solve_accounting_only",
            "The V19 worker change adds lifecycle dispatch, live admission, and counters; it does not assemble q matrices.",
        ),
        "src/solvers/task40_v10_p6_mumps.py": (
            "factor_lifecycle_only",
            "The V19 change adds the one-q factor lifecycle; every candidate q CSR is freshly compared by content hash.",
        ),
        "src/solvers/task40_v10_p6_yorbit.py": (
            "factor_lifecycle_and_capability_routing_only",
            "The V19 change routes factor creation and capability reporting; fresh all-q CSR hashes bind the same operator.",
        ),
        "src/solvers/task40_v18_ny8_operator_reuse.py": (
            "certificate_validation_only",
            "The V19 change validates the prior certificate and does not participate in FE or q-matrix assembly.",
        ),
    }
    current_dependencies = {}
    qualified_dependencies = {}
    for relative in reuse.CERTIFICATE_SOURCE_DEPENDENCIES:
        dependency = root / relative
        dependency.parent.mkdir(parents=True, exist_ok=True)
        content = (
            current_checker_source
            if relative == checker_relative
            else f"current:{relative}".encode()
        )
        dependency.write_bytes(content)
        current_hash = hashlib.sha256(content).hexdigest()
        current_dependencies[relative] = current_hash
        if relative in changed:
            qualified_dependencies[relative] = hashlib.sha256(
                f"qualified:{relative}".encode()
            ).hexdigest()
        else:
            qualified_dependencies[relative] = current_hash

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
    operator = {
        "schema": "test.operator.v1",
        "passed": True,
        "mode_identities_covered_once": True,
        "original_H_mode_count": 532,
    }
    # Two builds per q ensure validators accept repeated one-slot refactors.
    factor_snapshot = _v19_factor_audit()

    baseline_path = root / "input" / "b0_v18.dat"
    current_path = root / "input" / "b0_v19.dat"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        'model_id = "task40extra_nonseparable_0p7nm"\n'
        'run_id = "task40extra_0p7nm_b0_p6_reference_v18_ny8"\n'
        '[solver]\n'
        f'preconditioner = "{PROFILE}"\n'
        'stage = "B0_CANDIDATE"\n'
        'task40_reference_pc_strategy = "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"\n'
        'task40_q_assembly_strategy = "ROW_TILE_BOUNDED_CSR_V17"\n',
        encoding="utf-8",
    )
    current_path.write_text(
        'model_id = "task40extra_nonseparable_0p7nm"\n'
        'run_id = "task40extra_0p7nm_b0_p6_reference_v19_ny8"\n'
        '[solver]\n'
        f'preconditioner = "{PROFILE}"\n'
        'stage = "B0_CANDIDATE"\n'
        'task40_reference_pc_strategy = "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"\n'
        'task40_q_assembly_strategy = "ROW_TILE_BOUNDED_CSR_V17"\n'
        'task40_factor_lifecycle_strategy = "ONE_Q_REFACTOR_V19"\n',
        encoding="utf-8",
    )
    baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    current_input_sha = hashlib.sha256(current_path.read_bytes()).hexdigest()
    old_source_sha = SOURCE_SHA
    old_root = root / "results" / "qualified-v18-run"
    old_root.mkdir(parents=True)
    for name, value in (
        ("source_sha.txt", old_source_sha),
        ("input_sha256.txt", baseline_sha),
        ("physical_model_sha256.txt", PHYSICAL_SHA),
    ):
        (old_root / name).write_text(value + "\n", encoding="ascii")
    summary = {
        "status": result_status,
        "result_classification": (
            "B0_Y8_P6_REFERENCE_INVERSE_PASS" if result_status == "PASS" else "WORKER_FAILED"
        ),
        "source_sha": old_source_sha,
        "profile": PROFILE,
        "abi": ABI,
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
        "exit_status": 0 if result_status == "PASS" else 4,
        "result_classification": "worker_exit0" if result_status == "PASS" else "WORKER_FAILED",
        "source_sha": old_source_sha,
        "input_sha256": baseline_sha,
        "physical_model_sha256": PHYSICAL_SHA,
        "run_id": "task40extra_0p7nm_b0_p6_reference_v18_ny8",
        "solver": {"preconditioner": PROFILE, "stage": "B0_CANDIDATE"},
    }
    manifest_path = old_root / "run_manifest.json"
    manifest_sha = _write_json(manifest_path, manifest)

    source_receipt_path = root / "v18-source-receipt.json"
    source_operator_dependencies = {
        relative: qualified_dependencies[relative]
        for relative in reuse.OPERATOR_SOURCE_DEPENDENCIES
    }
    source_receipt = {
        "schema": "task40extra.review_v18_ny8_operator_reuse_receipt.v1",
        "new_attempt": {
            "source_sha": old_source_sha,
            "profile_identity": PROFILE,
            "input_sha256": baseline_sha,
            "physical_model_sha256": PHYSICAL_SHA,
            "target_mode_sha256": MODE_SHA,
            "abi_identity": ABI,
            "source_dependency_sha256": source_operator_dependencies,
        },
    }
    source_receipt_sha = _write_json(source_receipt_path, source_receipt)
    changed_assessments = {
        relative: {
            "classification": classification,
            "reason": reason,
            "operator_semantics_unchanged": True,
        }
        for relative, (classification, reason) in changed.items()
    }
    changed_assessments[checker_relative].update(
        lifecycle_checker_change_only=True,
        operator_checker_functions_unchanged=True,
    )
    qualified_attempt = {
        "run_root": str(old_root.relative_to(root)),
        "source_sha": old_source_sha,
        "profile_identity": PROFILE,
        "input_sha256": baseline_sha,
        "physical_model_sha256": PHYSICAL_SHA,
        "target_mode_sha256": MODE_SHA,
        "abi_identity": ABI,
        "mode_count": 532,
        "candidate_summary_path": str(summary_path.relative_to(root)),
        "candidate_summary_sha256": summary_sha,
        "run_manifest_path": str(manifest_path.relative_to(root)),
        "run_manifest_sha256": manifest_sha,
        "complete_operator_qualification_sha256": reuse._json_sha256(operator),
        "operator_source_receipt_path": str(source_receipt_path.relative_to(root)),
        "operator_source_receipt_sha256": source_receipt_sha,
        "source_dependency_sha256": source_operator_dependencies,
        "operator_checker_path": "src/runners/task40_v10_output_checker.py",
        "operator_checker_source_sha": operator_checker_source_sha,
        "operator_checker_sha256": hashlib.sha256(old_checker_source).hexdigest(),
    }
    receipt = {
        "schema": "task40extra.review_v19_ny8_operator_reuse_receipt.v1",
        "qualified_attempt": qualified_attempt,
        "new_attempt": {
            "source_sha": NEW_SOURCE_SHA,
            "profile_identity": PROFILE,
            "input_sha256": current_input_sha,
            "physical_model_sha256": PHYSICAL_SHA,
            "target_mode_sha256": MODE_SHA,
            "abi_identity": ABI,
            "source_dependency_sha256": current_dependencies,
            "dependency_change_assessment": changed_assessments,
            "input_equivalence": {
                "baseline_input_path": str(baseline_path.relative_to(root)),
                "baseline_input_sha256": baseline_sha,
                "current_input_path": str(current_path.relative_to(root)),
                "current_input_sha256": current_input_sha,
                "field_differences": [
                    "run_id", "solver.task40_factor_lifecycle_strategy"
                ],
            },
        },
    }
    receipt_path = root / "v19-receipt.json"
    receipt_sha = _write_json(receipt_path, receipt)
    return SimpleNamespace(
        root=root,
        matrices=matrices,
        receipt=receipt,
        receipt_path=receipt_path,
        receipt_sha=receipt_sha,
        result_status=result_status,
    )


def _validate_v19(fixture, *, expected_receipt_sha256=None):
    return reuse.reuse_ny8_operator_qualification_certificate(
        repo_root=fixture.root,
        receipt_path=fixture.receipt_path,
        candidate_q_matrices=fixture.matrices,
        profile=SimpleNamespace(name=PROFILE),
        source_sha=NEW_SOURCE_SHA,
        input_sha256=fixture.receipt["new_attempt"]["input_sha256"],
        physical_model_sha256=PHYSICAL_SHA,
        target_mode_sha256=MODE_SHA,
        abi_identity=ABI,
        expected_receipt_sha256=expected_receipt_sha256 or fixture.receipt_sha,
    )


@pytest.mark.parametrize("result_status", ["PASS", "FAILED"])
def test_v19_certificate_separates_run_result_from_operator_pass_and_checks_all_fresh_q(
    tmp_path, monkeypatch, result_status
):
    fixture = _v19_certificate_fixture(tmp_path, monkeypatch, result_status=result_status)

    operator, facts = _validate_v19(fixture)

    assert operator["passed"] is True
    assert facts["qualified_status"] == result_status
    assert facts["qualified_result_classification"] == (
        "B0_Y8_P6_REFERENCE_INVERSE_PASS" if result_status == "PASS" else "WORKER_FAILED"
    )
    assert facts["qualified_run_result_classification"] == (
        "worker_exit0" if result_status == "PASS" else "WORKER_FAILED"
    )
    assert facts["input_differences_are_run_id_and_factor_lifecycle_only"] is True
    assert facts["input_field_differences"] == [
        "run_id", "solver.task40_factor_lifecycle_strategy"
    ]
    assert facts["all_eight_fresh_q_hashes_match"] is True
    assert facts["qualified_run_manifest_sha256"] == fixture.receipt[
        "qualified_attempt"
    ]["run_manifest_sha256"]
    assert facts["qualified_run_result_classification"] != facts[
        "independent_operator_checker"
    ].get("status")
    assert facts["qualified_operator_checker_source_sha"] == fixture.receipt[
        "qualified_attempt"
    ]["operator_checker_source_sha"]
    assert facts["qualified_operator_checker_blob_sha256"] == fixture.receipt[
        "qualified_attempt"
    ]["operator_checker_sha256"]
    assert facts["original_operator_checker_functions_unchanged"] is True


def test_v19_certificate_rejects_unreviewed_operator_dependency_change(tmp_path, monkeypatch):
    fixture = _v19_certificate_fixture(tmp_path, monkeypatch, result_status="PASS")
    relative = "src/solvers/task40_v10_p6_yorbit.py"
    fixture.receipt["new_attempt"]["dependency_change_assessment"].pop(relative)
    fixture.receipt_sha = _write_json(fixture.receipt_path, fixture.receipt)

    with pytest.raises(ValueError, match="assessment does not match actual source differences"):
        _validate_v19(fixture)


def test_v19_certificate_rejects_a_forged_historical_checker_hash(tmp_path, monkeypatch):
    fixture = _v19_certificate_fixture(tmp_path, monkeypatch, result_status="PASS")
    qualified = fixture.receipt["qualified_attempt"]
    qualified["operator_checker_sha256"] = fixture.receipt["new_attempt"][
        "source_dependency_sha256"]["src/runners/task40_v10_output_checker.py"]
    fixture.receipt_sha = _write_json(fixture.receipt_path, fixture.receipt)

    with pytest.raises(ValueError, match="frozen source/hash"):
        _validate_v19(fixture)


def test_v19_certificate_rejects_checker_changes_beyond_lifecycle_route(tmp_path, monkeypatch):
    fixture = _v19_certificate_fixture(tmp_path, monkeypatch, result_status="PASS")
    checker_path = fixture.root / "src/runners/task40_v10_output_checker.py"
    checker_path.write_bytes(
        checker_path.read_bytes() + b"\ndef unreviewed_checker_change():\n    return True\n"
    )

    with pytest.raises(ValueError, match="exceed the factor-lifecycle route"):
        _validate_v19(fixture)
