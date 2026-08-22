"""Pure contracts for the V5 LA0 failed-class diagnostic."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task038_full3d_n2_la0 as runner
from benchmarks import task038_full3d_n2_la0_checker as checker


ROOT = Path(__file__).parents[2]
RUNNER_PATH = ROOT / "benchmarks" / "run_task038_full3d_n2_la0.py"
CHECKER_PATH = ROOT / "benchmarks" / "task038_full3d_n2_la0_checker.py"


def _worker_args(extra: list[str] | None = None) -> list[str]:
    args = [
        "--stage",
        "la0",
        "--case",
        "p6-h10-mpi1",
        "--input",
        "input.dat",
        "--raw-dir",
        "raw",
        "--record",
        "record.json",
        "--marker-dir",
        "markers",
        "--expected-source-sha",
        "a" * 40,
        "--expected-mpi-size",
        "1",
    ]
    return args + (extra or [])


def test_failed_class_selection_and_hashes_are_deterministic() -> None:
    digest = "b" * 64
    assert runner.failed_class_selection_key(digest, 3) == (3, digest)
    assert runner.failed_class_selection_key(digest, 3) == runner.failed_class_selection_key(digest, 3)
    matrix = np.diag(np.asarray([2.0, 3.0], dtype=np.complex128))
    assert runner.sha256_path is not None
    payload = np.ascontiguousarray(matrix).view(np.uint8)
    assert runner.hashlib.sha256(payload).hexdigest() == runner.hashlib.sha256(payload).hexdigest()


def test_fixed_rhs_and_cli_reject_physical_inputs() -> None:
    args = runner._parse_worker(_worker_args())
    assert args.expected_mpi_size == 1
    np.testing.assert_array_equal(
        runner.fixed_rhs(3),
        np.asarray([0.125 + 0.25j, 1.125 + 0.25j, 2.125 + 0.25j]),
    )
    for option in ("--physical-rhs", "--residual"):
        with pytest.raises(SystemExit):
            runner._parse_worker(_worker_args([option, "forbidden"]))


def test_source_identity_is_copied_for_future_negative_and_success_records() -> None:
    runtime = {
        "source_identity": {
            "expected_sha": "c" * 40,
            "source_git_sha": "c" * 40,
            "tracked_status": "",
        }
    }
    expected = {
        "expected_sha": "c" * 40,
        "source_git_sha": "c" * 40,
        "tracked_status": "",
    }
    assert runner.top_level_source_identity(runtime, "c" * 40) == expected
    assert runner.top_level_source_identity(runtime, "c" * 40) == expected
    assert runner.top_level_source_identity({}, "c" * 40)["source_git_sha"] is None


def test_checker_fails_closed_without_complete_identity_or_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"schema": checker.LA0_SCHEMA}) + "\n", encoding="utf-8")
    result = checker.check_record(path, expected_sha="d" * 40, raw_dir=tmp_path)
    assert result["passed"] is False
    assert result["errors"]


def test_checker_fails_closed_on_physical_or_residual_input_flags(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    record = {
        "schema": checker.LA0_SCHEMA,
        "stage": "la0_single_failed_class",
        "case": "p6-h10-mpi1",
        "mpi_size": 1,
        "degree": 6,
        "mesh_target_nm": 10.0,
        "classification": "LA0_FAILED_TO_REPRODUCE_V1_CLASS",
        "source_identity": {
            "expected_sha": "e" * 40,
            "source_git_sha": "e" * 40,
            "tracked_status": "",
        },
        "runtime": {
            "source_identity": {
                "expected_sha": "e" * 40,
                "source_git_sha": "e" * 40,
                "tracked_status": "",
            }
        },
        "markers": {"ledger": []},
        "fixed_diagnostic": {
            "solve_gate": checker.LA0_SOLVE_LIMIT,
            "source_independent": True,
            "physical_rhs_accepted": True,
            "residual_input_accepted": True,
        },
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = checker.check_record(path, expected_sha="e" * 40, raw_dir=tmp_path)
    assert result["passed"] is False
    assert any("physical RHS" in error or "residual input" in error for error in result["errors"])


def test_checker_requires_first_failed_class_identity_and_frozen_residual() -> None:
    order = ["a" * 64, "b" * 64]
    failed = {
        "digest": order[1],
        "slot": 1,
        "representative_rank": 0,
        "representative_cell": {
            "cell_key": [0, 0, 0],
            "tag": 3,
            "widths": [1.0, 1.0, 1.0],
            "row_count": 2,
            "canonical_free_row_descriptor_sha256": "c" * 64,
        },
        "rows": 2,
        "registration_error": "fixed local factor solve residual exceeds limit",
        "reproduction_verified": True,
        "registration_trace": {
            "class_order": order,
            "class_order_sha256": checker._class_order_sha256(order),
            "successful_slots": [0],
            "failed_slot": 1,
            "first_failure": True,
            "order_rule": checker.LA0_FAILURE_ORDER_RULE,
        },
    }
    errors: list[str] = []
    checker._check_failed_class_identity(failed, 2, errors)
    assert errors == []
    failed["digest"] = "d" * 64
    errors = []
    checker._check_failed_class_identity(failed, 2, errors)
    assert any("digest/slot" in error for error in errors)


def test_worker_zero_exit_requires_verified_reproduction() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "capture[\"reproduction_verified\"] = _capture_reproduces_v1(capture)" in source
    assert "capture is not None and capture[\"reproduction_verified\"]" in source
    assert runner.LA0_OLD_N2_V1_RESIDUAL == 1.0426245523812324e-11


def test_la1_pack_triangular_paths_and_repeat_are_fixed() -> None:
    matrix = np.asarray(
        [[4.0 + 0.0j, 1.0 - 0.5j], [1.0 + 0.5j, 3.0 + 0.0j]],
        dtype=np.complex128,
    )
    rhs = runner.fixed_rhs(2)
    packed, lower, roundtrip, exact, raw_factor_sha256 = runner._la1_pack(matrix)
    assert packed.shape == (3,)
    assert packed.dtype == np.complex128
    assert exact is True
    assert roundtrip == 0.0
    assert len(raw_factor_sha256) == 64
    np.testing.assert_allclose(lower @ lower.conj().T, matrix, rtol=0.0, atol=1e-14)
    s0 = runner._la1_s0(lower, rhs)
    s1 = runner._la1_s1(lower, rhs)
    s2 = runner._la1_s2(matrix, rhs)
    s3 = runner._la1_s3(lower, matrix, rhs)
    np.testing.assert_allclose(s0, s1, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(s1, s2, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(s1, s3, rtol=1e-13, atol=1e-13)
    metrics = runner._la1_diagnostics(matrix, rhs)
    assert metrics["repeat"]["S3_exact"] is True
    assert metrics["decision"]["path"] in {"T", "R", "C", "A", "P", "close"}


def test_la1_decision_tree_has_only_frozen_paths() -> None:
    base = {
        "finite": True,
        "factor_finite": True,
        "matrix_rhs_identity": True,
        "hermitian_defect": 0.0,
        "lambda_min": 1.0,
        "factorization_residual": 0.0,
        "packed_roundtrip_relative": 0.0,
        "packed_roundtrip_exact": True,
        "packed_reconstruction_hash_equal": True,
        "kappa2": 1.0e12,
        "paths": {
            "S0": {"relative_residual": 2.0e-11, "normalized_backward_error": 1.0e-12, "finite": True},
            "S1": {"relative_residual": 2.0e-11, "normalized_backward_error": 1.0e-12, "finite": True},
            "S2": {"relative_residual": 2.0e-11, "normalized_backward_error": 1.0e-12, "finite": True},
            "S3": {"relative_residual": 2.0e-11, "normalized_backward_error": 1.0e-12, "finite": True},
        },
        "repeat": {"S0_exact": True, "S1_exact": True, "S3_exact": True},
    }
    assert runner._la1_decision(base)["path"] == "C"
    reproducible = json.loads(json.dumps(base))
    reproducible["paths"]["S1"]["relative_residual"] = 5.0e-12
    assert runner._la1_decision(reproducible)["path"] == "T"
    reproducible["repeat"]["S0_exact"] = False
    assert runner._la1_decision(reproducible)["path"] == "close"
    refine = json.loads(json.dumps(base))
    refine["paths"]["S2"]["relative_residual"] = 2.0e-2
    refine["paths"]["S3"]["relative_residual"] = 5.0e-12
    assert runner._la1_decision(refine)["path"] == "R"
    assembly = json.loads(json.dumps(base))
    assembly["hermitian_defect"] = 2.0e-11
    assert runner._la1_decision(assembly)["path"] == "A"
    packing = json.loads(json.dumps(base))
    packing["packed_roundtrip_relative"] = 1.0e-10
    assert runner._la1_decision(packing)["path"] == "P"
    packing["paths"]["S1"]["relative_residual"] = 5.0e-12
    assert runner._la1_decision(packing)["path"] == "T"
    close = json.loads(json.dumps(base))
    close["kappa2"] = 1.0
    assert runner._la1_decision(close)["path"] == "close"


def test_la1_diagnostic_marker_is_explicit_before_failure() -> None:
    expected = (
        "preflight",
        "mesh_space_mpc",
        "subdomain_inventory",
        "local_factor_build",
        "linear_algebra_diagnostic",
        "failure",
    )
    assert checker.LA0_MARKERS == expected
    source = RUNNER_PATH.read_text(encoding="utf-8")
    ledger_source = source[
        source.index("def _marker_ledger") : source.index("def _write_record")
    ]
    assert ledger_source.index('"linear_algebra_diagnostic"') < ledger_source.index('"failure"')


def test_la1_s3_has_two_triangular_solves_and_no_refinement_loop() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_la1_s3"
    )
    assert not any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(function))
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "solve_triangular"
        for node in ast.walk(function)
    ) == 2


def test_la1_checker_recomputes_all_paths_independently() -> None:
    matrix = np.asarray(
        [[4.0 + 0.0j, 1.0 - 0.5j], [1.0 + 0.5j, 3.0 + 0.0j]],
        dtype=np.complex128,
    )
    rhs = runner.fixed_rhs(2)
    worker_facts = runner._la1_diagnostics(matrix, rhs)
    checker_facts = checker._la1_recompute(matrix, rhs)
    errors: list[str] = []
    checker._check_la1_recorded(worker_facts, checker_facts, errors)
    assert errors == []


def test_la0_has_no_refinement_loop_or_prohibited_numeric_path() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "one_refinement_work_vectors_bytes" in source
    assert "for refinement" not in source
    for forbidden in (
        "FullspacePhysicalAction",
        "createAIJ",
        "assemble_matrix",
        "Schur",
        "allgather(",
        "build_candidate_a",
        "build_candidate_c",
    ):
        assert forbidden not in source
    assert "LA0_SOLVE_LIMIT = 1.0e-11" in source


def test_checker_is_independent_and_read_only() -> None:
    tree = ast.parse(CHECKER_PATH.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not imports.intersection({"dolfinx", "petsc4py", "mpi4py", "slepc4py"})
    assert "run_task038_full3d_n2" not in CHECKER_PATH.read_text(encoding="utf-8")
    assert "allgather(" not in CHECKER_PATH.read_text(encoding="utf-8")
