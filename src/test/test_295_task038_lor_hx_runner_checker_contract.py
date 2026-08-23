"""Pure contracts for the thin L1 LOR/HX runner and checker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks import task038_full3d_lor_hx_checker as checker
from benchmarks import run_task038_full3d_lor_hx as runner


def _identity_record(case: str, status: str) -> dict:
    degree = int(case[1])
    mpi_size = int(case[-1])
    runtime = {
        "qualified_activation": "1",
        "mpi_size": mpi_size,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "sys_executable": "/repo/.venv/bin/python",
    }
    topology_audit = {
        "owner_local_maps": True,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "mpc_slave_master": "finalized_mpc_homogenize_backsubstitution",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
        "slave_master_complete": True,
    }
    record = {
        "schema": checker.SCHEMA,
        "stage": "l1",
        "case": case,
        "degree": degree,
        "mpi_size": mpi_size,
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "branch": checker.BRANCH,
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            **runtime,
        },
        "rank_facts": [
            {"rank": rank, "runtime": {**runtime}}
            for rank in range(mpi_size)
        ],
        "canonical_mpi_identity": {
            "status": status,
            "production_numeric_allgather": False,
            "audit": {"topology_audit": topology_audit} if degree in {2, 3} else {},
        },
        "forbidden": {
            "global_numeric_allgather": False,
            "global_aij_in_production": False,
            "global_schur": False,
            "global_direct_coarse": False,
            "per_rank_full_basis_replication": False,
            "production_dense_transfer": False,
        },
        "production": {
            "global_transfer_matrix": False,
            "local_tensor_action": True,
            "owner_local_maps": True,
            "numeric_allgather": False,
            "retained_dense_transfer_bytes": 0,
            "local_dense_oracle_only": True,
        },
    }
    return record


def _canonical_arrays() -> dict[str, np.ndarray]:
    source_key = "0123456789abcdef" * 4
    action_key = "fedcba9876543210" * 4
    values = {
        "canonical_source": (source_key, 1.0 + 2.0j),
        "canonical_mapped_source": (source_key, 1.0 + 2.0j),
        "canonical_action": (action_key, 3.0 + 4.0j),
        "canonical_mapped_action": (action_key, 3.0 + 4.0j),
        "canonical_repeat": (action_key, 3.0 + 4.0j),
    }
    arrays: dict[str, np.ndarray] = {}
    for name, (key, value) in values.items():
        arrays[f"{name}_keys"] = np.asarray([key], dtype="<U64")
        arrays[f"{name}_values"] = np.asarray([value], dtype=np.complex128)
    arrays["canonical_lor_keys"] = np.asarray([7], dtype=np.uint32)
    arrays["canonical_lor_values"] = np.asarray([5.0 + 6.0j], dtype=np.complex128)
    return arrays


def _reference_arrays(degree: int = 2) -> tuple[dict[str, np.ndarray], dict]:
    block = degree * (degree + 1) ** 2
    edge_count = 3 * block
    dense = np.eye(edge_count, dtype=np.complex128)
    arrays = {
        "high_to_lor": dense,
        "lor_to_high": dense.copy(),
        "probe": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_forward_1": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_forward_2": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_inverse_1": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_inverse_2": np.arange(edge_count, dtype=np.float64) + 1j,
    }
    shapes = (
        (degree, degree + 1, degree + 1),
        (degree + 1, degree, degree + 1),
        (degree + 1, degree + 1, degree),
    )
    for axis, shape in enumerate(shapes):
        group = np.arange(axis * block, (axis + 1) * block, dtype=np.int32)
        arrays[f"reference_group_{axis}"] = group
        arrays[f"reference_forward_tensor_{axis}"] = np.eye(block, dtype=np.complex128).reshape(
            (block,) + shape
        )
        arrays[f"reference_inverse_tensor_{axis}"] = np.eye(block, dtype=np.complex128).reshape(
            (block,) + shape
        )
    record = {
        "degree": degree,
        "production": {"retained_dense_transfer_bytes": 0},
    }
    return arrays, record


def _write_record(tmp_path: Path, name: str, record: dict) -> Path:
    raw = tmp_path / f"{name}.raw"
    raw.mkdir()
    artifacts = []
    for artifact_name, array in record.pop("_arrays", {}).items():
        path = raw / f"{artifact_name}.npy"
        np.save(path, array, allow_pickle=False)
        artifacts.append(
            {
                "name": artifact_name,
                "relative_path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "dtype": str(array.dtype),
                "shape": list(array.shape),
            }
        )
    record["raw_dir"] = str(raw)
    record["artifacts"] = artifacts
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_l1_checker_requires_exact_five_cases_and_accepts_p6_na(tmp_path: Path) -> None:
    p6 = _identity_record("p6-mpi1", "not_applicable_by_frozen_case")
    assert checker._identity_errors(p6) == []
    p2 = _identity_record("p2-mpi1", "measured")
    result = checker.check_records([])
    assert result["passed"] is False
    assert checker._identity_errors(p2) == []
    bad_production = {
        **p2,
        "production": {**p2["production"], "owner_local_maps": False},
    }
    assert any("owner_local_maps" in error for error in checker._identity_errors(bad_production))
    bad_topology = json.loads(json.dumps(p2))
    bad_topology["canonical_mpi_identity"]["audit"]["topology_audit"]["slave_master_complete"] = False
    assert any("slave_master_complete" in error for error in checker._identity_errors(bad_topology))
    bad_rank = json.loads(json.dumps(p2))
    bad_rank["rank_facts"][0]["runtime"]["petsc_int_type"] = "int64"
    assert any("rank fact PETSc ABI" in error for error in checker._identity_errors(bad_rank))
    duplicate = _identity_record("p2-mpi1", "measured")
    duplicate_path = _write_record(tmp_path, "duplicate", duplicate)
    result = checker.check_records([duplicate_path, duplicate_path])
    assert result["records"][0]["raw_record_sha256"] == hashlib.sha256(
        duplicate_path.read_bytes()
    ).hexdigest()
    assert result["records"][0]["source_sha"] == "a" * 40
    assert any("duplicate cases" in error for error in result["errors"])
    assert any("aggregate missing cases" in error for error in result["errors"])


def test_l1_stage_markers_are_per_rank_append_only_and_flush(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    runner._append_stage_marker(raw_dir, "paths_ready", 1)
    runner._append_stage_marker(raw_dir, "source_identity_closed", 1)
    marker_path = raw_dir / "stage-rank1.jsonl"
    lines = marker_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["stage"] for line in lines] == [
        "paths_ready",
        "source_identity_closed",
    ]
    assert all(json.loads(line)["rank"] == 1 for line in lines)
    assert all(isinstance(json.loads(line)["time"], float) for line in lines)


def test_l1_checker_canonical_internal_and_mpi_mutations_fail() -> None:
    record = _identity_record("p2-mpi1", "measured")
    arrays = _canonical_arrays()
    assert checker._canonical_identity(record, arrays)["errors"] == []
    arrays["canonical_mapped_source_keys"] = np.asarray(
        ["f" * 64], dtype="<U64"
    )
    assert checker._canonical_identity(record, arrays)["errors"]
    arrays = _canonical_arrays()
    arrays["canonical_mapped_action_values"][0] += 1.0e-6
    assert checker._canonical_identity(record, arrays)["errors"]
    arrays = _canonical_arrays()
    arrays["canonical_lor_values"][0] += 1.0e-6
    assert not np.allclose(
        arrays["canonical_lor_values"], _canonical_arrays()["canonical_lor_values"], rtol=0.0, atol=1.0e-12
    )


def test_l1_checker_reconstructs_reference_axis_blocks_and_catches_mutation() -> None:
    arrays, record = _reference_arrays()
    checked = checker._check_reference_factor(record, arrays)
    assert not checked["errors"]
    arrays["reference_forward_tensor_1"] = arrays["reference_forward_tensor_1"].copy()
    arrays["reference_forward_tensor_1"][0, 0, 0, 0] += 1.0e-4
    checked = checker._check_reference_factor(record, arrays)
    assert any("packed reference action" in error for error in checked["errors"])


def test_l1_checker_gates_hermitian_before_generalized_spectrum() -> None:
    degree = 2
    edge_count = 3 * degree * (degree + 1) ** 2
    identity = np.eye(edge_count, dtype=np.complex128)
    zero = np.zeros(edge_count, dtype=np.complex128)
    arrays = {
        "high_to_lor": identity.copy(),
        "lor_to_high": identity.copy(),
        "probe": np.arange(edge_count, dtype=np.float64) + 1j,
        "local_probe_forward_1": np.arange(edge_count, dtype=np.float64) + 1j,
        "local_probe_forward_2": np.arange(edge_count, dtype=np.float64) + 1j,
        "local_probe_roundtrip": np.arange(edge_count, dtype=np.float64) + 1j,
        "high_matrix": identity.copy(),
        "lor_matrix": identity.copy(),
        "high_gradient_edge": zero.copy(),
        "lor_gradient": identity.copy(),
        "h1_transfer": zero.copy(),
        "lor_curl_incidence": np.zeros((edge_count, edge_count), dtype=np.complex128),
        "high_curl_face": np.zeros((edge_count, edge_count), dtype=np.complex128),
    }
    checked = checker._check_local_algebra({"degree": degree}, arrays)
    assert not checked["errors"]
    arrays["high_matrix"] = identity.copy()
    arrays["high_matrix"][0, 1] = 1.0e-3
    checked = checker._check_local_algebra({"degree": degree}, arrays)
    assert any("Hermitian/SPD prerequisite" in error for error in checked["errors"])
    assert "spectral_lambda_min" not in checked


def test_l1_checker_cross_mpi_keys_and_values_are_real_pair_gates(tmp_path: Path) -> None:
    left = _identity_record("p2-mpi1", "measured")
    left["_arrays"] = _canonical_arrays()
    right = _identity_record("p2-mpi2", "measured")
    right["_arrays"] = _canonical_arrays()
    left_path = _write_record(tmp_path, "left", left)
    right_path = _write_record(tmp_path, "right", right)
    metrics, errors = checker._compare_canonical_records(left_path, right_path)
    assert not errors
    assert metrics["source_mpi_relative"] <= 1.0e-12
    right_mutated = _identity_record("p2-mpi2", "measured")
    right_mutated["_arrays"] = _canonical_arrays()
    right_mutated["_arrays"]["canonical_action_values"][0] += 1.0e-4
    right_mutated_path = _write_record(tmp_path, "right_mutated", right_mutated)
    _metrics, errors = checker._compare_canonical_records(left_path, right_mutated_path)
    assert any("action canonical MPI relative" in error for error in errors)
    right_lor_mutated = _identity_record("p2-mpi2", "measured")
    right_lor_mutated["_arrays"] = _canonical_arrays()
    right_lor_mutated["_arrays"]["canonical_lor_values"][0] += 1.0e-4
    right_lor_path = _write_record(tmp_path, "right_lor_mutated", right_lor_mutated)
    _metrics, errors = checker._compare_canonical_records(left_path, right_lor_path)
    assert any("owner-LOR canonical MPI relative" in error for error in errors)
