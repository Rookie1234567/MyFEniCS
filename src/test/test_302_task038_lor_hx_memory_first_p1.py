"""Focused P1 memory-first cadence, shard, and pair-contract tests."""

from __future__ import annotations

import hashlib
import ast
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task038_full3d_lor_hx_memory_first_checker import (
    CASES,
    SUITE_ORDER,
    check_pair,
    check_record,
    check_records,
)
from src.solvers.fullspace_memory_first_krylov import (
    CHECKPOINT_INTERVAL,
    MANDATORY_FIRST_CHECKPOINT,
    run_restart20_cycles,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA = "a" * 40
HASH = "b" * 64
OPERATOR_HASH = "c" * 64
PHYSICAL_HASH = "d" * 64


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_descriptor(path: Path, values: np.ndarray) -> dict[str, Any]:
    return {
        "relative_path": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _write_role(
    raw: Path,
    role: str,
    semantic_role: str,
    values: np.ndarray,
    mpi_size: int,
    key_prefix: str = "key",
) -> dict[str, Any]:
    keys = np.asarray([f"{key_prefix}-{index}" for index in range(values.size)], dtype="<U64")
    shards: list[dict[str, Any]] = []
    for rank in range(mpi_size):
        selected = np.arange(rank, values.size, mpi_size, dtype=np.int64)
        rank_keys = keys[selected]
        rank_values = np.asarray(values[selected], dtype=np.complex128)
        key_path = raw / f"{role}.rank{rank}.keys.npy"
        value_path = raw / f"{role}.rank{rank}.values.npy"
        np.save(key_path, rank_keys, allow_pickle=False)
        np.save(value_path, rank_values, allow_pickle=False)
        shards.append(
            {
                "rank": rank,
                "role": semantic_role,
                "keys": _array_descriptor(key_path, rank_keys),
                "values": _array_descriptor(value_path, rank_values),
            }
        )
    return {"role": semantic_role, "shards": shards}


def _write_pc_layout(
    raw: Path,
    name: str,
    values: np.ndarray,
    mpi_size: int,
    semantic_role: str,
) -> dict[str, Any]:
    shards: list[dict[str, Any]] = []
    chunks = np.array_split(np.asarray(values, dtype=np.complex128), mpi_size)
    start = 0
    for rank, chunk in enumerate(chunks):
        path = raw / f"{name}.rank{rank}.values.npy"
        np.save(path, chunk, allow_pickle=False)
        stop = start + chunk.size
        shards.append(
            {
                "rank": rank,
                "ownership_range": [start, stop],
                "local_size": int(chunk.size),
                "global_size": int(values.size),
                "values": _array_descriptor(path, chunk),
            }
        )
        start = stop
    return {"role": semantic_role, "shards": shards}


def _write_checkpoint(
    raw: Path, mpi_size: int, explicit_true_residual: float = 0.0
) -> dict[str, Any]:
    directory = raw / "checkpoint-200"
    directory.mkdir()
    for rank in range(mpi_size):
        np.save(
            directory / f"solution_rank{rank}.npy",
            np.asarray([rank + 0.0j], dtype=np.complex128),
            allow_pickle=False,
        )
    manifest = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 200,
        "explicit_true_residual": float(explicit_true_residual),
        "input_identity_sha256": HASH,
        "operator_identity_sha256": OPERATOR_HASH,
        "physical_model_sha256": PHYSICAL_HASH,
        "source_sha": SOURCE_SHA,
        "mpi_size": mpi_size,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "iteration": 200,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha(manifest_path),
        "explicit_true_residual": float(explicit_true_residual),
    }


def _refresh_descriptor(raw: Path, descriptor: dict[str, Any]) -> None:
    path = raw / descriptor["relative_path"]
    values = np.load(path, allow_pickle=False)
    descriptor["bytes"] = path.stat().st_size
    descriptor["sha256"] = _sha(path)
    descriptor["dtype"] = str(values.dtype)
    descriptor["shape"] = list(values.shape)


def _mutate_canonical(
    record: dict[str, Any], role: str, rank: int, delta: complex
) -> None:
    raw = Path(record["raw_dir"])
    descriptor = record["canonical_artifacts"][role]["shards"][rank]["values"]
    path = raw / descriptor["relative_path"]
    values = np.asarray(np.load(path, allow_pickle=False), dtype=np.complex128)
    values[0] += delta
    np.save(path, values, allow_pickle=False)
    _refresh_descriptor(raw, descriptor)


def _synthetic_record(
    tmp_path: Path,
    case: str = "p2-mpi1",
    source_name: str = "random",
    *,
    action_delta: float = 0.0,
    source_sha: str = SOURCE_SHA,
) -> Path:
    degree, mpi_size = CASES[case]
    root = tmp_path / f"{case.replace('-', '_')}_{source_name}_{source_sha[:4]}_{action_delta}"
    raw = root / "raw"
    record_path = root / "record.json"
    raw.mkdir(parents=True)
    base = np.asarray([1.0 + 0.1j, -2.0 + 0.2j, 0.5 - 0.3j, 3.0 + 0.0j], dtype=np.complex128)
    solution = np.asarray([0.2 + 0.1j, -0.5 + 0.2j, 0.25 + 0.0j, 0.75 - 0.1j])
    action = np.asarray([1.0 + action_delta + 0.1j, -2.0 + 0.2j, 0.5 - 0.3j, 3.0], dtype=np.complex128)
    true_residual = base - action
    explicit_residual = float(np.linalg.norm(true_residual) / np.linalg.norm(base))
    artifacts = {
        "source": _write_role(raw, "source", "primal", base, mpi_size, "source-key"),
        "rhs": _write_role(raw, "rhs", "dual", base, mpi_size, "dual-key"),
        "final_solution": _write_role(raw, "final_solution", "primal", solution, mpi_size, "solution-key"),
        "final_action": _write_role(raw, "final_action", "dual", action, mpi_size, "dual-key"),
        "final_true_residual": _write_role(raw, "final_true_residual", "dual", true_residual, mpi_size, "dual-key"),
    }
    first = np.asarray([1.0, 0.0, 2.0, 0.0], dtype=np.complex128)
    second = np.asarray([0.0, 1.0, 0.0, 2.0], dtype=np.complex128)
    alpha = 0.375 + 0.25j
    beta = -0.625 + 0.5j
    combined = alpha * first + beta * second
    pc_values = {
        "pc_input_residual_before": base,
        "pc_input_residual_after": base,
        "pc_input_first_before": first,
        "pc_input_first_after": first,
        "pc_input_second_before": second,
        "pc_input_second_after": second,
        "pc_input_combined_before": combined,
        "pc_input_combined_after": combined,
        "pc_output_first": first,
        "pc_output_second": second,
        "pc_output_combined": combined,
        "pc_output_repeat": combined,
    }
    pc_artifacts = {
        name: _write_pc_layout(raw, name, values, mpi_size, "dual" if name.startswith("pc_input") else "primal")
        for name, values in pc_values.items()
    }
    checkpoint = _write_checkpoint(raw, mpi_size, explicit_residual)
    resource = {
        "process_tree_rss_bytes": 1024,
        "process_tree_swap_bytes": 0,
        "all_status_readable": True,
        "scope": "rank_process_tree_diagnostic_excludes_launcher",
    }
    cycle_template = {
        "cycle_index": 9,
        "start_iteration": 180,
        "end_iteration": 200,
        "iterations": 20,
        "reason": -3,
        "reported_final_residual": 0.0,
        "explicit_true_residual": explicit_residual,
        "matvec_count": 20,
        "pc_apply_count": 20,
        "ksp_destroyed": True,
        "resource": resource,
    }
    cycles = [
        {
            **cycle_template,
            "cycle_index": index,
            "start_iteration": index * 20,
            "end_iteration": (index + 1) * 20,
        }
        for index in range(10)
    ]
    rank_facts = [
        {
            "rank": rank,
            "runtime": {
                "qualified_activation": "1",
                "mpi_size": mpi_size,
                "petsc_scalar_type": "complex128",
                "petsc_int_type": "int32",
            },
            "matvec_count": 20,
            "pc_apply_count": 20,
            "explicit_action_count": 11,
            "iterations": 200,
            "reason": -3,
            "constraint": {
                "slave_constraint_absolute": 0.0,
                "slave_rows_local": 0,
                "slave_master_complete": True,
            },
            "cycle_ledger": cycles,
        }
        for rank in range(mpi_size)
    ]
    record = {
        "schema": "task038.lor-native-complex-hx.memory-first-p1-record.v1",
        "stage": "p1",
        "scope": "memory_first_positive_krylov_suite",
        "case": case,
        "degree": degree,
        "h_nm": 50.0,
        "source_name": source_name,
        "variant": "sequential-v1",
        "mpi_size": mpi_size,
        "source": {
            "expected_sha": source_sha,
            "commit_sha_start": source_sha,
            "commit_sha_end": source_sha,
            "branch": BRANCH,
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            "qualified_activation": "1",
            "mpi_size": mpi_size,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "command": [
            "/qualified/python",
            "-m",
            "benchmarks.run_task038_full3d_lor_hx_memory_first",
            "--stage",
            "p1",
            "--case",
            case,
            "--source",
            source_name,
            "--raw-dir",
            str(raw.resolve()),
            "--record",
            str(record_path.resolve()),
            "--expected-source-sha",
            source_sha,
            "--expected-mpi-size",
            str(mpi_size),
        ],
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 20,
            "max_it": 2000,
            "residual_limit": 1.0e-8,
            "residual_replacement": True,
            "checkpoint_interval": 200,
            "first_checkpoint_iteration": None,
            "additive_v2": False,
        },
        "provenance": {
            "input_identity_sha256": HASH,
            "operator_identity_sha256": OPERATOR_HASH,
            "physical_model_sha256": PHYSICAL_HASH,
        },
        "provenance_basis": {
            "partition_invariant": True,
            "excludes": ["case_mpi_label", "mpi_size", "owner_local_counts", "rank_local_audit"],
        },
        "source_facts": {
            "name": source_name,
            "formula": {
                "random": "analytic deterministic pseudo-random edge field from fixed noninteger trigonometric frequencies and phases",
                "gradient": "grad(sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz))",
                "curl": "curl((0,0,sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz)))",
                "checkerboard": "R4 fixed 8-cycle field: (high_x*high_y*high_z, high_y*high_z, high_z*high_x)",
            }[source_name],
        },
        "old_authorities": {
            "old_l2_record_sha256": "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3",
            "old_l2_one_apply_rho": 1.7348663090876784,
            "old_l2_classification": "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE",
            "old_k1_80_step": "FAIL",
            "additive_v2": "CLOSED",
        },
        "pc_legality": {
            "direction_construction": "PETSc_global_row_parity",
            "alpha": [alpha.real, alpha.imag],
            "beta": [beta.real, beta.imag],
            "first_global_norm": float(np.linalg.norm(first)),
            "second_global_norm": float(np.linalg.norm(second)),
            "combined_global_norm": float(np.linalg.norm(combined)),
            "linearity_relative": 0.0,
            "repeat_relative": 0.0,
            "finite": True,
            "input_unchanged": True,
            "slave_constraint_absolute": 0.0,
            "slave_rows_local": 0,
            "slave_local_indices_by_rank": {str(rank): [] for rank in range(mpi_size)},
            "slave_master_complete": True,
            "phase_application": "finalized_floquet_mpc_once",
            "high_order_global_aij": False,
            "global_direct_coarse": False,
            "global_numeric_allgather": False,
            "global_dense_transfer": False,
            "pc_artifacts": pc_artifacts,
        },
        "one_apply": {
            "rho": 0.1,
            "rho_status": "diagnostic_only_not_a_gate",
            "finite": True,
        },
        "cycles": cycles,
        "checkpoint_status": {
            "20": {"status": "measured_no_checkpoint"},
            "80": {"status": "measured_no_checkpoint"},
            "200": {"status": "measured", "checkpoint": checkpoint},
            "500": {"status": "not_reached"},
            "1000": {"status": "not_reached"},
            "2000": {"status": "not_reached"},
        },
        "checkpoint_facts": [checkpoint],
        "final": {
            "iterations": 200,
            "reason": -3,
            "explicit_true_residual": explicit_residual,
            "finite": True,
        },
        "rank_facts": rank_facts,
        "count_ranges": {
            "matvec_count": {"min": 20, "max": 20},
            "pc_apply_count": {"min": 20, "max": 20},
            "explicit_action_count": {"min": 11, "max": 11},
            "iterations": {"min": 200, "max": 200},
        },
        "production": {
            "variant": "sequential-v1",
            "high_order_global_aij": False,
            "global_direct_coarse": False,
            "global_numeric_allgather": False,
            "global_dense_transfer": False,
            "metadata_allgather": True,
            "metadata_allgather_scope": "rank_runtime_cycle_scalar_and_artifact_facts_only",
            "process_tree_resource_scope": "rank_root_diagnostic_excludes_launcher",
        },
        "fixture_audit": {
            "variant": "sequential-v1",
            "high_order_global_aij": False,
            "global_numeric_allgather": False,
            "global_transfer_matrix": False,
            "phase_application": "finalized_floquet_mpc_once",
            "slave_master_complete": True,
        },
        "hx_audit": {
            "variant": "sequential-v1",
            "global_direct_coarse": False,
            "global_numeric_allgather": False,
            "global_transfer_matrix": False,
            "high_order_aij": False,
        },
        "forbidden": {
            "additive_v2": False,
            "high_order_global_aij": False,
            "global_direct_coarse": False,
            "global_numeric_allgather": False,
            "global_dense_transfer": False,
        },
        "canonical_artifacts": artifacts,
        "status": "facts_written_no_worker_classification",
    }
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record_path


def test_p1_production_cadence_is_200_while_p0_default_is_20(tmp_path: Path) -> None:
    assert MANDATORY_FIRST_CHECKPOINT == 20
    assert CHECKPOINT_INTERVAL == 200
    size = 64
    matrix = PETSc.Mat().createAIJ([size, size], nnz=1, comm=PETSc.COMM_SELF)
    matrix.setUp()
    for index in range(size):
        matrix.setValue(index, index, 1.0 + 0.01 * index)
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.array[:] = np.linspace(1.0, 2.0, size) + 0.25j
    p1_checkpoints: list[int] = []

    def action(vector: PETSc.Vec) -> PETSc.Vec:
        result = matrix.createVecLeft()
        matrix.mult(vector, result)
        return result

    def precondition(vector: PETSc.Vec) -> PETSc.Vec:
        return vector.copy()

    try:
        result = run_restart20_cycles(
            rhs,
            action,
            precondition,
            max_it=200,
            residual_limit=0.0,
            resource_sample=lambda: {
                "process_tree_rss_bytes": 1,
                "process_tree_swap_bytes": 0,
                "all_status_readable": True,
                "scope": "rank_process_tree_diagnostic_excludes_launcher",
            },
            start_iteration=0,
            checkpoint_writer=lambda iteration, _solution, _residual: p1_checkpoints.append(iteration) or {"iteration": iteration},
            first_checkpoint_iteration=None,
            checkpoint_interval=200,
            stop_on_true_residual=False,
        )
        assert p1_checkpoints and 20 not in p1_checkpoints
        assert all(iteration % 200 == 0 for iteration in p1_checkpoints)
        assert result["settings"]["first_checkpoint_iteration"] is None
    finally:
        rhs.destroy()
        matrix.destroy()


def test_p1_checker_accepts_sharded_record_and_all_rank_constraint(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi2", "random")
    result = check_record(record)
    assert result["passed"] is True, result


def test_p1_pair_dynamic_bound_and_source_provenance(tmp_path: Path) -> None:
    left = _synthetic_record(tmp_path, "p2-mpi1", "random")
    right = _synthetic_record(tmp_path, "p2-mpi2", "random", action_delta=1.0)
    result = check_pair(left, right)
    assert result["passed"] is False
    assert result["contract_errors"] == []
    assert any("rho" in item for item in result["gate_failures"])
    wrong_source = _synthetic_record(tmp_path, "p2-mpi2", "random", source_sha="e" * 40)
    pair = check_pair(left, wrong_source)
    assert any("source SHA mismatch" in item for item in pair["contract_errors"])


def test_p1_pair_final_action_aligns_rhs_by_dual_keys(tmp_path: Path) -> None:
    left = _synthetic_record(tmp_path, "p2-mpi1", "random")
    right = _synthetic_record(tmp_path, "p2-mpi2", "random")
    payload = json.loads(left.read_text(encoding="utf-8"))
    raw = Path(payload["raw_dir"])
    section = payload["canonical_artifacts"]["final_action"]["shards"][0]
    key_descriptor = section["keys"]
    value_descriptor = section["values"]
    key_path = raw / key_descriptor["relative_path"]
    value_path = raw / value_descriptor["relative_path"]
    keys = np.load(key_path, allow_pickle=False)
    values = np.load(value_path, allow_pickle=False)
    permutation = np.asarray([1, 0, 2, 3])
    np.save(key_path, keys[permutation], allow_pickle=False)
    np.save(value_path, values[permutation], allow_pickle=False)
    _refresh_descriptor(raw, key_descriptor)
    _refresh_descriptor(raw, value_descriptor)
    left.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_pair(left, right)
    assert result["contract_errors"] == [], result
    assert result["metrics"]["final_action"] == 0.0, result


def test_p1_aggregate_requires_exact_frozen_order_and_preserves_numeric_gates(tmp_path: Path) -> None:
    paths = [
        _synthetic_record(tmp_path, case, source)
        for case in CASES
        for source in ("random", "gradient", "curl", "checkerboard")
    ]
    result = check_records(paths)
    assert result["passed"] is True, result
    assert len(result["pairs"]) == 8
    assert all(
        "metrics" in pair
        and "dynamic_action_bound" in pair
        and "left_identity" in pair
        and "right_identity" in pair
        for pair in result["pairs"].values()
    )
    missing = check_records(paths[:-1])
    assert missing["passed"] is False
    assert any("exactly the frozen 16-case" in item for item in missing["contract_errors"])


def test_p1_forbidden_numeric_allgather_and_all_rank_slave_are_not_silent(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi2", "random")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["fixture_audit"]["global_numeric_allgather"] = True
    record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_record(record)
    assert any("global_numeric_allgather" in item for item in result["contract_errors"])


def test_p1_hx_forbidden_audit_is_not_omitted(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi1", "random")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["hx_audit"]["high_order_aij"] = True
    payload["hx_audit"]["global_transfer_matrix"] = True
    record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_record(record)
    assert any("high_order_global_aij" in item for item in result["contract_errors"])
    assert any("global_dense_transfer" in item for item in result["contract_errors"])


def test_p1_cycle_final_and_checkpoint_cadence_close_fail_closed(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi1", "random")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["cycles"][-1]["end_iteration"] = 199
    record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_record(record)
    assert any("cycle ledger" in item or "final iteration" in item for item in result["contract_errors"])

    cadence_record = _synthetic_record(tmp_path / "cadence", "p2-mpi1", "random")
    cadence = json.loads(cadence_record.read_text(encoding="utf-8"))
    cadence["checkpoint_status"]["200"]["status"] = "measured_no_checkpoint"
    cadence_record.write_text(json.dumps(cadence) + "\n", encoding="utf-8")
    cadence_result = check_record(cadence_record)
    assert any("checkpoint boundary" in item for item in cadence_result["contract_errors"])


def test_p1_nested_process_tree_resource_facts_are_checked(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi1", "random")
    payload = json.loads(record.read_text(encoding="utf-8"))
    nested = {
        "rss_bytes": 1024,
        "swap_bytes": 0,
        "all_status_readable": True,
    }
    for cycle in payload["cycles"]:
        cycle["resource"] = {
            "process_tree": nested,
            "scope": "rank_process_tree_diagnostic_excludes_launcher",
        }
    for fact in payload["rank_facts"]:
        for cycle in fact["cycle_ledger"]:
            cycle["resource"] = {
                "process_tree": nested,
                "scope": "rank_process_tree_diagnostic_excludes_launcher",
            }
    record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_record(record)
    assert result["passed"] is True, result


def test_p1_worker_pc_scalar_cannot_override_raw_legality(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi2", "random")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["pc_legality"]["linearity_relative"] = 0.5
    record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_record(record)
    assert any("stored PC fact linearity_relative" in item for item in result["contract_errors"])


def test_p1_raw_pc_output_and_final_residual_are_authoritative(tmp_path: Path) -> None:
    record = _synthetic_record(tmp_path, "p2-mpi1", "random")
    payload = json.loads(record.read_text(encoding="utf-8"))
    pc_descriptor = payload["pc_legality"]["pc_artifacts"]["pc_output_combined"]["shards"][0]["values"]
    pc_path = Path(payload["raw_dir"]) / pc_descriptor["relative_path"]
    pc_values = np.asarray(np.load(pc_path, allow_pickle=False), dtype=np.complex128)
    pc_values[0] += 0.25
    np.save(pc_path, pc_values, allow_pickle=False)
    _refresh_descriptor(Path(payload["raw_dir"]), pc_descriptor)
    record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    residual_result = check_record(record)
    assert any("raw PC linearity" in item or "stored PC fact linearity" in item for item in residual_result["gate_failures"] + residual_result["contract_errors"])

    residual_record = _synthetic_record(tmp_path / "residual", "p2-mpi1", "random")
    payload = json.loads(residual_record.read_text(encoding="utf-8"))
    _mutate_canonical(payload, "final_true_residual", 0, 0.5)
    residual_record.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_record(residual_record)
    assert any("RHS minus final action" in item for item in result["contract_errors"])


def test_p1_pair_rhs_gate_is_independent_of_stored_facts(tmp_path: Path) -> None:
    left = _synthetic_record(tmp_path, "p2-mpi1", "random")
    right = _synthetic_record(tmp_path, "p2-mpi2", "random")
    payload = json.loads(right.read_text(encoding="utf-8"))
    _mutate_canonical(payload, "source", 0, 1.0e-10)
    _mutate_canonical(payload, "rhs", 0, 1.0e-10)
    _mutate_canonical(payload, "final_true_residual", 0, 1.0e-10)
    payload["final"]["explicit_true_residual"] = float(
        1.0e-10 / np.linalg.norm(np.asarray([1.0 + 0.1j, -2.0 + 0.2j, 0.5 - 0.3j, 3.0], dtype=np.complex128) + np.asarray([1.0e-10, 0.0, 0.0, 0.0]))
    )
    right.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = check_pair(left, right)
    assert any("pair source identity" in item for item in result["gate_failures"])
    assert any("pair RHS identity" in item for item in result["gate_failures"])


def test_p1_mpi2_metadata_smoke_is_all_rank_and_natural() -> None:
    comm = MPI.COMM_WORLD
    facts = comm.allgather({"rank": comm.rank, "slave_constraint_absolute": 0.0})
    assert [fact["rank"] for fact in facts] == list(range(comm.size))
    assert all(fact["slave_constraint_absolute"] <= 1.0e-12 for fact in facts)


def test_p1_checker_import_surface_and_fixed_case_contract() -> None:
    checker_path = Path(__file__).parents[2] / "benchmarks" / "task038_full3d_lor_hx_memory_first_checker.py"
    tree = ast.parse(checker_path.read_text(encoding="utf-8"))
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not imported.intersection({"petsc4py", "mpi4py", "dolfinx", "src", "benchmarks"})
    assert len(SUITE_ORDER) == 16
    assert tuple(CASES) == ("p2-mpi1", "p2-mpi2", "p3-mpi1", "p3-mpi2")
