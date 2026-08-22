"""Focused FC0 certification-v2 contracts; no mesh or formal run."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks import task038_full3d_local_factor_certification_checker as checker
from src.solvers.fullspace_local_factor_certification import (
    CERTIFICATION_SCHEMA,
    FACTOR_BYTES_LIMIT,
    MAX_LOCAL_ROWS,
    ORDINARY_RESIDUAL_LIMIT,
    certify_dense_factor,
    fixed_rhs,
    gate_passes,
    gamma_n,
    gate_limits,
    summarize_certificates,
)
from src.solvers.fullspace_local_spectral import _PackedCholesky


ROOT = Path(__file__).parents[2]


def test_gamma_and_frozen_max_row_limits_are_exact() -> None:
    assert np.finfo(np.float64).eps == 2.220446049250313e-16
    assert gamma_n(882) == 1.9584334154391596e-13
    limits = gate_limits(882)
    assert limits["hermitian_defect"] == 1.5667467323513277e-12
    assert limits["factorization_relative_error"] == 3.1334934647026553e-12
    assert limits["normalized_backward_error"] == 3.1334934647026553e-12
    assert limits["factor_bytes"] == FACTOR_BYTES_LIMIT == 6_230_448
    assert MAX_LOCAL_ROWS == 882
    eps = np.finfo(np.float64).eps
    assert gamma_n(1) == eps / (1.0 - eps)


def test_gate_boundaries_and_bad_local_algebra_fail_closed() -> None:
    assert gate_passes(1.0, 1.0) is True
    assert gate_passes(np.nextafter(1.0, np.inf), 1.0) is False
    assert gate_passes(float("nan"), 1.0) is False
    with np.testing.assert_raises(np.linalg.LinAlgError):
        checker._independent_certificate(
            np.asarray([[1.0, 2.0], [2.0, 1.0]], dtype=np.complex128),
            fixed_rhs(2),
        )
    with np.testing.assert_raises(ValueError):
        checker._independent_certificate(
            np.asarray([[np.nan + 0.0j]], dtype=np.complex128), fixed_rhs(1)
        )


def test_certificate_uses_fixed_rhs_and_exact_two_production_solves() -> None:
    matrix = np.asarray(
        [[5.0 + 0.0j, 0.5 - 0.25j], [0.5 + 0.25j, 3.0 + 0.0j]],
        dtype=np.complex128,
    )
    rhs = fixed_rhs(2)
    factor = _PackedCholesky(matrix)
    calls = []

    def solve(value: np.ndarray) -> np.ndarray:
        calls.append(value.copy())
        return factor.solve(value)

    result = certify_dense_factor(
        matrix, solve, packed=factor.packed, lower=factor.lower(), rhs=rhs
    )
    assert len(calls) == 2
    assert all(np.array_equal(value, rhs) for value in calls)
    assert result["schema"] == CERTIFICATION_SCHEMA
    assert result["triangular_repeat_exact"] is True
    assert result["packed_roundtrip_exact"] is True
    assert result["gate_pass"] is True
    with np.testing.assert_raises(ValueError):
        certify_dense_factor(
            matrix,
            solve,
            packed=factor.packed,
            lower=factor.lower(),
            rhs=rhs + 1.0,
        )


def test_historical_relative_miss_does_not_stop_class_aggregation() -> None:
    first = {"gate_pass": False, "packed_bytes": 48, "ordinary_relative_residual": 5.0e-11}
    second = {"gate_pass": True, "packed_bytes": 48, "ordinary_relative_residual": 1.0e-14}
    summary = summarize_certificates((first, second))
    assert summary["processed_class_count"] == 2
    assert summary["all_class_certificates_pass"] is False
    assert summary["dense_class_max_live"] == 1


def test_checker_recomputes_and_fails_closed_on_missing_class(tmp_path: Path) -> None:
    record = {
        "schema": checker.SCHEMA,
        "case": "p6-h10-mpi1",
        "degree": 6,
        "mesh_target_nm": 10.0,
        "mpi_size": 1,
        "class_order": ["a" * 64],
        "class_order_sha256": "not-the-hash",
        "classes": [],
        "summary": {"dense_class_max_live": 1, "dense_workspace_released": True},
        "lifecycle": {
            "modes_built": False,
            "regional_built": False,
            "top_built": False,
            "physical_action_built": False,
            "rho_run": False,
        },
    }
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    result = checker.check_record(path, "a" * 40)
    assert result["passed"] is False
    assert result["errors"]


def test_checker_recomputes_small_complete_record_and_detects_mutation(tmp_path: Path) -> None:
    input_path = tmp_path / "input.dat"
    input_path.write_bytes(b"frozen-input")
    matrix = np.asarray(
        [[4.0 + 0.0j, 0.25 - 0.5j], [0.25 + 0.5j, 3.0 + 0.0j]],
        dtype=np.complex128,
    )
    rhs = fixed_rhs(2)
    matrix_path = tmp_path / "B.npy"
    rhs_path = tmp_path / "rhs.npy"
    np.save(matrix_path, matrix, allow_pickle=False)
    np.save(rhs_path, rhs, allow_pickle=False)
    metrics = checker._independent_certificate(matrix, rhs)

    def descriptor(path: Path, array: np.ndarray) -> dict[str, object]:
        return {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }
    source = {
        "expected_sha": "a" * 40,
        "source_git_sha": "a" * 40,
        "tracked_status": "",
    }
    raw_path = tmp_path / "watchdog.raw.json"
    compact_path = tmp_path / "watchdog.compact.json"
    raw_path.write_text(
        json.dumps({
            "samples": [{"authority": {"process_tree": {"swap_bytes": 0}}}],
            "worker_returncode": 0,
        }),
        encoding="utf-8",
    )
    compact_payload = {
        "worker_returncode": 0,
        "process_tree_swap_gate": True,
        "process_tree_peak_memory_authority_bytes": 1,
        "termination": {"method": "already_exited"},
        "no_orphan_claim": True,
        "stop_reason": "natural_exit",
        "natural_exit": True,
        "authority_complete": True,
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    }
    compact_path.write_text(
        json.dumps(compact_payload),
        encoding="utf-8",
    )
    record = {
        "schema": checker.SCHEMA,
        "case": "p6-h10-mpi1",
        "degree": 6,
        "mesh_target_nm": 10.0,
        "profile": "full3d_scalable_v1",
        "mpi_size": 1,
        "source_identity": source,
        "runtime": {
            "source_identity": source,
            "qualified_activation": "1",
            "mpi_size": 1,
            "scalar_dtype": "complex128",
            "int_dtype": "int32",
            "sys_executable": "/repo/.venv/bin/python",
        },
        "input": {"path": str(input_path), "file_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()},
        "class_order": ["b" * 64],
        "class_order_sha256": hashlib.sha256(json.dumps(["b" * 64], separators=(",", ":")).encode()).hexdigest(),
        "class_order_repeat": ["b" * 64],
        "class_order_repeat_sha256": hashlib.sha256(json.dumps(["b" * 64], separators=(",", ":")).encode()).hexdigest(),
        "class_order_repeat_exact": True,
        "certification_schema": checker.CERT_SCHEMA,
        "threshold_contract": {
            "eps64": checker.EPS64,
            "ordinary_relative_residual": checker.ORDINARY_RESIDUAL_LIMIT,
            "kappa2": checker.KAPPA_LIMIT,
            "factor_bytes": checker.FACTOR_BYTES_LIMIT,
            "total_factor_bytes": checker.TOTAL_FACTOR_BYTES_LIMIT,
        },
        "classes": [{
            "digest": "b" * 64,
            "slot": 0,
            "representative_rank": 0,
            "factor_owner_rank": 0,
            "representative_cell": {
                "cell_key": [0, 0, 0],
                "tag": 1,
                "widths": [1.0, 1.0, 1.0],
                "row_count": 2,
                "canonical_free_row_descriptor_sha256": "c" * 64,
            },
            "matrix": descriptor(matrix_path, matrix),
            "rhs": descriptor(rhs_path, rhs),
            "metrics": metrics,
        }],
        "summary": {
            "processed_class_count": 1,
            "class_count": 1,
            "class_order": ["b" * 64],
            "class_order_sha256": hashlib.sha256(json.dumps(["b" * 64], separators=(",", ":")).encode()).hexdigest(),
            "class_order_repeat": ["b" * 64],
            "class_order_repeat_sha256": hashlib.sha256(json.dumps(["b" * 64], separators=(",", ":")).encode()).hexdigest(),
            "class_order_repeat_exact": True,
            "class_count_within_limit": True,
            "class_order_sorted_unique": True,
            "all_classes_processed": True,
            "duplicate_class_count": 0,
            "missing_class_count": 0,
            "global_factor_count": 1,
            "factor_owner_closure": {
                "mpi_size": 1,
                "owner_rank_set": [0],
                "unique_factor_count": 1,
                "duplicate_factor_count": 0,
            },
            "all_class_certificates_pass": True,
            "total_factor_bytes": metrics["packed_bytes"],
            "total_factor_bytes_limit": checker.TOTAL_FACTOR_BYTES_LIMIT,
            "all_class_factor_bytes_within_global_limit": True,
            "overall_gate_pass": True,
            "dense_class_max_live": 1,
            "dense_workspace_released": True,
        },
        "lifecycle": {
            "modes_built": False,
            "regional_built": False,
            "top_built": False,
            "physical_action_built": False,
            "rho_run": False,
            "forbidden": {"global_aij": False, "global_schur": False, "global_factor": False, "numeric_allgather": False},
        },
        "resource_contract": {
            "status": "measured",
            "raw_path": str(raw_path),
            "compact_path": str(compact_path),
        },
    }
    record_path = tmp_path / "complete.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result = checker.check_record(record_path, "a" * 40)
    assert result["passed"] is True, result["errors"]
    assert result["worst"]["factor_bytes"] == {
        "digest": "b" * 64,
        "slot": 0,
        "rows": 2,
        "value": float(metrics["packed_bytes"]),
        "limit": float(checker.FACTOR_BYTES_LIMIT),
    }
    mutation = json.loads(record_path.read_text(encoding="utf-8"))
    mutation["class_order_repeat_exact"] = False
    record_path.write_text(json.dumps(mutation), encoding="utf-8")
    assert checker.check_record(record_path, "a" * 40)["passed"] is False
    mutation["class_order_repeat_exact"] = True
    mutation["threshold_contract"]["kappa2"] = 1.0
    record_path.write_text(json.dumps(mutation), encoding="utf-8")
    assert checker.check_record(record_path, "a" * 40)["passed"] is False
    mutation["threshold_contract"]["kappa2"] = checker.KAPPA_LIMIT
    mutation["classes"][0]["representative_cell"]["row_count"] = 1
    record_path.write_text(json.dumps(mutation), encoding="utf-8")
    assert checker.check_record(record_path, "a" * 40)["passed"] is False
    record_path.write_text(json.dumps(record), encoding="utf-8")
    matrix[0, 0] += 0.5
    np.save(matrix_path, matrix, allow_pickle=False)
    assert checker.check_record(record_path, "a" * 40)["passed"] is False


def test_fc0_sources_do_not_open_forbidden_numerical_paths() -> None:
    runner_source = (ROOT / "benchmarks" / "run_task038_full3d_local_factor_certification.py").read_text(encoding="utf-8")
    checker_source = (ROOT / "benchmarks" / "task038_full3d_local_factor_certification_checker.py").read_text(encoding="utf-8")
    assert "build_real_local_spectral_patches" not in runner_source
    assert "FullspacePhysicalAction" not in runner_source
    assert "global_aij" in runner_source
    assert "yield str(digest), metadata, matrix" in runner_source
    assert "representatives: list" not in runner_source
    assert "_prepare_paths" in runner_source and "_watchdog_main" in runner_source
    assert "allgather(" not in checker_source
    assert "mpi4py" not in checker_source
    ast.parse(runner_source)
    ast.parse(checker_source)


def test_checker_has_one_cli_entrypoint_and_no_solver_import() -> None:
    path = ROOT / "benchmarks" / "task038_full3d_local_factor_certification_checker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mains = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "main"]
    assert len(mains) == 1
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(node.module and node.module.startswith("src.solvers") for node in imports)
    assert ORDINARY_RESIDUAL_LIMIT == 1.0e-10


def test_old_negative_compact_hashes_are_unchanged() -> None:
    expected = {
        "n2_local_spectral_setup_mpi1_v1.json": "d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40",
        "n2_local_spectral_setup_mpi1_v2.json": "d88330f2c9b038946c8f0b15e22b5850e6812c868366fa50f04e1e9b3962f763",
    }
    records = ROOT / "docs" / "task038_extra_full3d_iterative_0p7nm" / "outcomes" / "records"
    for name, digest in expected.items():
        assert hashlib.sha256((records / name).read_bytes()).hexdigest() == digest
