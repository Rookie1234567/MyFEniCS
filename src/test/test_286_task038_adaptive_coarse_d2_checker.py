"""Small sharded-artifact contracts for the independent D2 checker."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import benchmarks.task038_full3d_adaptive_coarse_d2_checker as checker
from benchmarks.canonical_matrix_artifacts import (
    KEY_DIGEST_ALGORITHM,
    MATRIX_MANIFEST_SCHEMA,
    MATRIX_SHARD_SCHEMA,
)
from benchmarks.task038_full3d_adaptive_coarse_d2_checker import (
    CANONICAL_LIMIT,
    CHECKER_SCHEMA,
    PREFIXES,
    check_pair,
    check_worker_record,
)
from benchmarks.canonical_vector_artifacts import canonical_key_json_bytes


ROOT = Path(__file__).parents[2]
CHECKER_PATH = ROOT / "benchmarks" / "task038_full3d_adaptive_coarse_d2_checker.py"
_SHA = "a" * 40
_ITEMSIZE = np.dtype(np.complex128).itemsize


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stats(local: int, global_sum: int, global_max: int) -> dict[str, int]:
    return {"local": local, "global_sum": global_sum, "global_max": global_max}


def _write_matrix(
    root: Path,
    role: str,
    arrays: list[np.ndarray],
    row_starts: list[int],
) -> tuple[Path, str]:
    root.mkdir(parents=True)
    descriptors = []
    for rank, (values, row_start) in enumerate(zip(arrays, row_starts)):
        key_path = root / f"rank_{rank:04d}.keys.jsonl"
        value_path = root / f"rank_{rank:04d}.values.npy"
        key_path.write_bytes(
            b"".join(
                canonical_key_json_bytes(("row", row_start + row)) + b"\n"
                for row in range(values.shape[0])
            )
        )
        np.save(value_path, values, allow_pickle=False)
        descriptors.append(
            {
                "schema_version": MATRIX_SHARD_SCHEMA,
                "rank": rank,
                "key_filename": key_path.name,
                "value_filename": value_path.name,
                "key_file_bytes": key_path.stat().st_size,
                "value_file_bytes": value_path.stat().st_size,
                "key_file_sha256": _sha256(key_path),
                "value_file_sha256": _sha256(value_path),
                "key_digest_algorithm": KEY_DIGEST_ALGORITHM,
                "local_packet_count": values.shape[0],
                "local_duplicate_count": 0,
                "key_shape": [values.shape[0]],
                "key_dtype": "canonical-key-json-v1",
                "value_shape": list(values.shape),
                "value_dtype": "complex128",
            }
        )
    manifest = {
        "schema_version": MATRIX_MANIFEST_SCHEMA,
        "role": role,
        "mpi_size": len(arrays),
        "column_count": 64,
        "dtype": "complex128",
        "key_digest_algorithm": KEY_DIGEST_ALGORITHM,
        "global_packet_count": sum(values.shape[0] for values in arrays),
        "global_duplicate_count": 0,
        "per_rank_shards": descriptors,
        "extractor_audit": {
            "role": role,
            "numeric_allgather": False,
            "owner_local_streaming": True,
        },
    }
    manifest_path = root / "matrix.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path, _sha256(manifest_path)


def _write_case(root: Path, mpi_size: int) -> Path:
    raw = root / f"mpi{mpi_size}" / "raw"
    raw.mkdir(parents=True)
    rows = 128
    z_all = np.zeros((rows, 64), dtype=np.complex128)
    z_all[:64, :] = np.eye(64, dtype=np.complex128)
    operator = np.diag(np.arange(1, 65, dtype=np.float64).astype(np.complex128))
    operator[0, 1] = 0.25j
    az_all = z_all @ operator
    if mpi_size == 1:
        z_parts = [z_all]
        az_parts = [az_all]
        starts = [0]
    else:
        z_parts = [z_all[:64], z_all[64:]]
        az_parts = [az_all[:64], az_all[64:]]
        starts = [0, 64]
    for rank, (z_values, az_values) in enumerate(zip(z_parts, az_parts)):
        np.save(raw / f"Z.rank{rank:04d}.npy", z_values, allow_pickle=False)
        np.save(raw / f"AZ.rank{rank:04d}.npy", az_values, allow_pickle=False)
    e = operator
    np.save(raw / "E.npy", e, allow_pickle=False)
    z_manifest, z_sha = _write_matrix(
        raw / "canonical" / "Z", "full_fe", z_parts, starts
    )
    az_manifest, az_sha = _write_matrix(
        raw / "canonical" / "AZ", "full_fe_dual", az_parts, starts
    )
    input_path = raw / "resolved_input.dat"
    input_path.write_bytes(b"resolved p6 h10 synthetic input\n")
    mode_path = raw / "mode_manifest.json"
    mode_path.write_text('{"mode_count":80}\n', encoding="utf-8")
    watchdog_raw = raw / "watchdog.raw.json"
    watchdog_raw.write_text(
        json.dumps(
            {
                "schema": "task038.full3d.adaptive-coarse.d2-watchdog-raw.v1",
                "command": ["worker", f"mpi{mpi_size}"],
                "samples": [
                    {
                        "stage": "online_az_e",
                        "authority": {
                            "memory_authority_bytes": 100,
                            "job_no_swap": True,
                            "process_tree": {
                                "all_status_readable": True,
                                "swap_bytes": 0,
                            },
                        },
                    }
                ],
                "stop_reason": "natural_exit",
                "termination": {
                    "requested": False,
                    "method": "natural_exit",
                    "sigkill_required": False,
                },
                "worker_returncode": 0,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    watchdog_compact = raw / "watchdog.compact.json"
    watchdog_compact.write_text(
        json.dumps(
            {
                "schema": "task038.full3d.adaptive-coarse.d2-watchdog-compact.v1",
                "raw_sha256": _sha256(watchdog_raw),
                "command": ["worker", f"mpi{mpi_size}"],
                "stop_reason": "natural_exit",
                "worker_returncode": 0,
                "termination": {
                    "requested": False,
                    "method": "natural_exit",
                    "sigkill_required": False,
                },
                "stage_peak_memory_authority_bytes": {"online_az_e": 100},
                "process_tree_peak_memory_authority_bytes": 100,
                "process_tree_swap_gate": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    z_payload = rows * 64 * _ITEMSIZE
    az_payload = z_payload
    e_payload = e.nbytes * mpi_size
    metadata_global = 16 * mpi_size
    work_global = 0
    resident_total = z_payload + az_payload + e_payload + metadata_global
    prefix_audits = []
    for prefix in PREFIXES:
        z_logical = rows * prefix * _ITEMSIZE
        az_logical = z_logical
        e_logical = prefix * prefix * _ITEMSIZE * mpi_size
        hermitian = float(
            np.linalg.norm(operator[:prefix, :prefix] - operator[:prefix, :prefix].conj().T)
            / np.linalg.norm(operator[:prefix, :prefix])
        )
        prefix_audits.append(
            {
                "prefix": prefix,
                "finite": True,
                "z_orthogonality_defect": 0.0,
                "az_repeat_relative_frobenius": 0.0,
                "az_repeat_exact": True,
                "e_condition_number": float(np.linalg.cond(operator[:prefix, :prefix])),
                "e_hermitian_relative_defect": hermitian,
                "physical_consistency_relative": 0.0,
                "e_prefix_leading_relative": 0.0,
                "e_prefix_leading_exact": True,
                "logical_prefix_z_bytes": _stats(
                    z_logical // mpi_size, z_logical, z_logical // mpi_size
                ),
                "logical_prefix_az_bytes": _stats(
                    az_logical // mpi_size, az_logical, az_logical // mpi_size
                ),
                "logical_prefix_e_bytes": _stats(
                    e_logical // mpi_size, e_logical, e_logical // mpi_size
                ),
                "logical_prefix_bytes_provenance": "derived_exact_array_size",
                "logical_prefix_coarse_total_global_sum": z_logical
                + az_logical
                + e_logical
                + metadata_global,
                "resident_z_bytes": _stats(
                    z_payload // mpi_size, z_payload, z_payload // mpi_size
                ),
                "resident_az_bytes": _stats(
                    az_payload // mpi_size, az_payload, az_payload // mpi_size
                ),
                "resident_e_bytes": _stats(
                    e.nbytes, e_payload, e.nbytes
                ),
                "resident_metadata_bytes": _stats(16, metadata_global, 16),
                "resident_work_vector_bytes": _stats(0, work_global, 0),
                "resident_coarse_total_global_sum": resident_total,
                "resident_bytes_provenance": "exact_current_retained_objects",
                "rank64_z_az_hard_limit_bytes": checker.EXPECTED_RANK64_Z_AZ_BYTES,
                "total_coarse_retained_hard_limit_bytes": 424000000,
            }
        )
    def descriptor(path: Path) -> dict:
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        return {
            "path": str(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "shape": list(array.shape),
            "dtype": "complex128",
        }
    mode_descriptor = {
        "relative_path": "mode_manifest.json",
        "sha256": _sha256(mode_path),
        "bytes": mode_path.stat().st_size,
    }
    record = {
        "schema": "task038.full3d.adaptive-coarse.d2-record.v1",
        "classification": "worker_facts_pending_independent_checker",
        "stage": "d2",
        "case": f"p6-h10-mpi{mpi_size}",
        "degree": 6,
        "mesh_target_nm": 10.0,
        "profile": "full3d_scalable_v1",
        "mpi": {"size": mpi_size},
        "rank": 64,
        "prefixes": list(PREFIXES),
        "model": {
            "profile": "full3d_scalable_v1",
            "degree": 6,
            "mesh_target_nm": 10.0,
            "input_resolved_from_file": True,
        },
        "input": {
            "path": str(input_path),
            "file_sha256": _sha256(input_path),
            "resolved_config_sha256": "b" * 64,
            "resolved_config_bytes": 32,
        },
        "source_identity": {
            "expected_sha": _SHA,
            "source_git_sha": _SHA,
            "tracked_status": "",
        },
        "runtime": {
            "qualified_activation": "1",
            "sys_executable": str(ROOT / ".venv" / "bin" / "python"),
            "qualified_venv_bin_resolved": str(
                (ROOT / ".venv" / "bin").resolve()
            ),
            "mpi_size": mpi_size,
            "scalar_dtype": "complex128",
            "int_dtype": "int32",
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "petsc4py": str(ROOT / ".venv" / "lib" / "petsc4py.py"),
            "slepc4py": str(ROOT / ".venv" / "lib" / "slepc4py.py"),
            "dolfinx": str(ROOT / ".venv" / "lib" / "dolfinx.py"),
            "basix": str(ROOT / ".venv" / "lib" / "basix.py"),
            "mpi4py": str(ROOT / ".venv" / "lib" / "mpi4py.py"),
            "source_identity": {
                "expected_sha": _SHA,
                "source_git_sha": _SHA,
                "tracked_status": "",
            },
        },
        "mode_manifest": mode_descriptor,
        "artifacts": {
            "mode_manifest": dict(mode_descriptor),
            "E": descriptor(raw / "E.npy"),
            "canonical_matrices": {
                "Z": {
                    "role": "full_fe",
                    "manifest_relative_path": "canonical/Z/matrix.manifest.json",
                    "manifest_sha256": z_sha,
                    "global_packet_count": rows,
                    "mpi_size": mpi_size,
                },
                "AZ": {
                    "role": "full_fe_dual",
                    "manifest_relative_path": "canonical/AZ/matrix.manifest.json",
                    "manifest_sha256": az_sha,
                    "global_packet_count": rows,
                    "mpi_size": mpi_size,
                },
            },
        },
        "basis": {
            "audit": {
                "construction_workspace_released": True,
                "physical_action_applied": False,
                "az_e_not_built": True,
                "rank_prefix": 64,
                "rank_ladder": list(PREFIXES),
                "phase_application": "finalized_floquet_mpc_once",
                "numeric_allgather": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "factor_materialized": False,
            }
        },
        "coarse": {
            "audit": {
                "schema": "fullspace.adaptive-coarse.v1",
                "rank": 64,
                "small_numeric_collective": "scalars_and_r_by_r_allreduce_only",
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "factor_materialized": False,
                "numeric_allgather": False,
                "prefix_audits": prefix_audits,
            }
        },
        "operator": {
            "audit": {
                "schema": "task038.fullspace-physical-action.v1",
                "operator": "A_volume_plus_dynamic_DtN",
                "t4_transmission_included": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
                "volume_action": {
                    "schema": "task038.fullspace-mpc-form-action.v1",
                    "numeric_allgather": False,
                    "global_matrix_materialized": False,
                    "global_constraint_matrix_materialized": False,
                    "global_condensed_schur_materialized": False,
                    "cell_schur_matrix_materialized": False,
                    "slab_matrix_materialized": False,
                    "factor_count": 0,
                    "ksp_created": False,
                },
                "dtn_action": {
                    "schema": "fullspace-dtn.carrier.v1",
                    "numeric_allgather": False,
                    "global_aij_materialized": False,
                    "global_schur_materialized": False,
                    "trace_matrix_materialized": False,
                    "ksp_created": False,
                    "explicit_c_matrix_count": 0,
                    "explicit_d_matrix_count": 0,
                    "pde_solved": False,
                },
            },
            "t4_transmission_included": False,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "factor_materialized": False,
            "numeric_allgather": False,
        },
        "owner_local_arrays": {
            "Z": descriptor(raw / "Z.rank0000.npy"),
            "AZ": descriptor(raw / "AZ.rank0000.npy"),
            "ownership_range": [0, z_parts[0].shape[0]],
        },
        "resource_contract": {
            "status": "measured",
            "raw_path": str(watchdog_raw),
            "raw_sha256": _sha256(watchdog_raw),
            "compact_path": str(watchdog_compact),
            "compact_sha256": _sha256(watchdog_compact),
            "stop_reason": "natural_exit",
            "worker_returncode": 0,
            "process_tree_peak_memory_authority_bytes": 100,
            "process_tree_swap_gate": True,
        },
    }
    record_path = root / f"mpi{mpi_size}" / "record.json"
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return record_path


def _make_pair(tmp_path: Path) -> tuple[Path, Path]:
    return _write_case(tmp_path, 1), _write_case(tmp_path, 2)


def _refresh_record(path: Path, update: Callable[[dict], Any] | None = None) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if update is not None:
        update(record)
    path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


def test_d2_checker_passes_streaming_pair_and_writes_prefix_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    assert checker.EXPECTED_GLOBAL_ROWS == 173802
    assert checker.EXPECTED_CANONICAL_PACKET_COUNT == 173802
    monkeypatch.setattr(checker, "EXPECTED_GLOBAL_ROWS", 128)
    monkeypatch.setattr(checker, "EXPECTED_CANONICAL_PACKET_COUNT", 128)
    monkeypatch.setattr(checker, "EXPECTED_RANK64_Z_AZ_BYTES", 128 * 64 * _ITEMSIZE * 2)
    mpi1, mpi2 = _make_pair(tmp_path / "pass")
    result = check_pair(
        mpi1,
        mpi1.parent / "raw",
        mpi2,
        mpi2.parent / "raw",
        tmp_path / "pass" / "checks",
    )
    assert result["passed"] is True
    assert set(result["prefixes"]) == {str(prefix) for prefix in PREFIXES}
    assert all(
        (tmp_path / "pass" / "checks" / f"d2_adaptive_coarse_prefix_{prefix}.json").is_file()
        for prefix in PREFIXES
    )
    assert result["evidence_sha256"]


@pytest.mark.parametrize(
    "mutation",
    ("zhz", "e", "watchdog", "missing", "canonical", "case", "abi", "rows", "basis"),
)
def test_d2_checker_fail_closed_on_core_or_resource_mutations(
    tmp_path: Path, mutation: str, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / mutation
    mpi1, mpi2 = _make_pair(root)
    if mutation != "rows":
        monkeypatch.setattr(checker, "EXPECTED_GLOBAL_ROWS", 128)
        monkeypatch.setattr(checker, "EXPECTED_CANONICAL_PACKET_COUNT", 128)
        monkeypatch.setattr(
            checker,
            "EXPECTED_RANK64_Z_AZ_BYTES",
            128 * 64 * _ITEMSIZE * 2,
        )
    if mutation == "zhz":
        path = mpi1.parent / "raw" / "Z.rank0000.npy"
        values = np.lib.format.open_memmap(path, mode="r+")
        values[0, 0] += 0.1
        values.flush()
        del values
        _refresh_record(
            mpi1,
            lambda record: record["owner_local_arrays"]["Z"].update(
                {"sha256": _sha256(path)}
            ),
        )
    elif mutation == "e":
        path = mpi1.parent / "raw" / "E.npy"
        values = np.lib.format.open_memmap(path, mode="r+")
        values[0, 0] += 0.5
        values.flush()
        del values
        _refresh_record(
            mpi1,
            lambda record: record["artifacts"]["E"].update(
                {"sha256": _sha256(path)}
            ),
        )
    elif mutation == "watchdog":
        raw = mpi1.parent / "raw" / "watchdog.raw.json"
        payload = json.loads(raw.read_text(encoding="utf-8"))
        payload["samples"][0] = {"authority_error": "synthetic"}
        raw.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        compact = mpi1.parent / "raw" / "watchdog.compact.json"
        compact_payload = json.loads(compact.read_text(encoding="utf-8"))
        compact_payload["raw_sha256"] = _sha256(raw)
        compact_payload["process_tree_swap_gate"] = False
        compact.write_text(json.dumps(compact_payload, sort_keys=True) + "\n", encoding="utf-8")
        _refresh_record(
            mpi1,
            lambda record: record["resource_contract"].update(
                {
                    "raw_sha256": _sha256(raw),
                    "compact_sha256": _sha256(compact),
                    "process_tree_swap_gate": False,
                }
            ),
        )
    elif mutation == "missing":
        _refresh_record(
            mpi1,
            lambda record: record["coarse"]["audit"]["prefix_audits"][0].pop(
                "az_repeat_exact"
            ),
        )
    elif mutation == "case":
        _refresh_record(
            mpi1, lambda record: record.update({"case": "p6-h10-mpi2"})
        )
    elif mutation == "abi":
        _refresh_record(
            mpi1,
            lambda record: record["runtime"].update({"scalar_dtype": "float64"}),
        )
    elif mutation == "rows":
        pass
    elif mutation == "basis":
        _refresh_record(
            mpi1,
            lambda record: record["basis"]["audit"].update(
                {"physical_action_applied": True}
            ),
        )
    else:
        manifest_path = mpi2.parent / "raw" / "canonical" / "AZ" / "matrix.manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        descriptor = manifest["per_rank_shards"][0]
        values_path = manifest_path.parent / descriptor["value_filename"]
        values = np.lib.format.open_memmap(values_path, mode="r+")
        values[0, 0] += 0.01
        values.flush()
        del values
        descriptor["value_file_sha256"] = _sha256(values_path)
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        _refresh_record(
            mpi2,
            lambda record: record["artifacts"]["canonical_matrices"]["AZ"].update(
                {"manifest_sha256": _sha256(manifest_path)}
            ),
        )
    result = check_pair(
        mpi1,
        mpi1.parent / "raw",
        mpi2,
        mpi2.parent / "raw",
        root / "checks",
    )
    assert result["passed"] is False


def test_d2_checker_has_no_runtime_mpi_or_solver_imports_and_is_streaming():
    tree = ast.parse(CHECKER_PATH.read_text(encoding="utf-8"))
    forbidden = {"dolfinx", "petsc4py", "mpi4py"}
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imported & forbidden
    text = CHECKER_PATH.read_text(encoding="utf-8")
    assert "mmap" in text
    assert "compare_canonical_matrices" in text
    assert "createAIJ" not in text
    assert "assemble_matrix" not in text
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "allgather"
        for node in ast.walk(tree)
    )
    assert CHECKER_SCHEMA in text
    assert CANONICAL_LIMIT == 1.0e-12


def test_d2_checker_does_not_use_worker_status_as_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(checker, "EXPECTED_GLOBAL_ROWS", 128)
    monkeypatch.setattr(checker, "EXPECTED_CANONICAL_PACKET_COUNT", 128)
    monkeypatch.setattr(checker, "EXPECTED_RANK64_Z_AZ_BYTES", 128 * 64 * _ITEMSIZE * 2)
    mpi1, mpi2 = _make_pair(tmp_path / "status")
    for path in (mpi1, mpi2):
        _refresh_record(path, lambda record: record.update({"status": "false"}))
    result = check_pair(
        mpi1,
        mpi1.parent / "raw",
        mpi2,
        mpi2.parent / "raw",
        tmp_path / "status" / "checks",
    )
    assert result["passed"] is True
