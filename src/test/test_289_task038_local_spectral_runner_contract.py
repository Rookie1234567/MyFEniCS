"""Pure contracts for the thin N1 local-spectral evidence layer."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task038_full3d_local_spectral_checker import check_worker_record
from benchmarks.run_task038_full3d_local_spectral import N1_CASES, _parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descriptor(raw: Path, path: Path, count: int) -> dict[str, object]:
    return {
        "relative_path": str(path.relative_to(raw)),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "packet_count": count,
        "dtype": "complex128",
        "key_encoding": "canonical_key_json_bytes",
    }


def _synthetic_record(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    canonical = raw / "canonical"
    canonical.mkdir(parents=True)
    keys = np.asarray(["key-a", "key-b"], dtype="U")
    source = np.asarray([1.0 + 2.0j, 2.0 + 1.0j], dtype=np.complex128)
    action = np.asarray([2.0 + 0.0j, 3.0 + 1.0j], dtype=np.complex128)
    shard = canonical / "rank0000.npz"
    np.savez(
        shard,
        key_json=keys,
        source=source,
        action=action,
        source_repeat=source,
        action_repeat=action,
    )
    shard_descriptor = _descriptor(raw, shard, len(keys))
    manifest = {
        "schema": "task038.n1.local-spectral-canonical-source-action.v1",
        "role": "full_space_source_action_owner_local_shards",
        "key_encoding": "canonical_key_json_bytes",
        "dtype": "complex128",
        "mpi_size": 1,
        "global_packet_count": 2,
        "per_rank_shards": [shard_descriptor],
        "numeric_allgather": False,
    }
    manifest_path = canonical / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    manifest_descriptor = _descriptor(raw, manifest_path, 2)

    facts = {
        "schema": "task038.n1.local-spectral-raw-facts.v1",
        "mode_cap": 8,
        "regional_rank_cap": 16,
        "source_packet_count": 2,
        "class_count": 1,
        "rank_facts": [
            {
                "rank": 0,
                "owned_patch_count": 1,
                "local_mode_count": 8,
                "mode_digest": "mode",
                "repeat_mode_digest": "mode",
                "mode_repeat_exact": True,
                "patch_audit": {
                    "class_count": 1,
                    "owner_factor_count": 1,
                    "B0_hermitian_relative_defect": 1.0e-14,
                    "M_local_hermitian_relative_defect": 1.0e-14,
                    "B0_min_eigenvalue": 1.0,
                    "M_local_min_eigenvalue": 1.0,
                    "gradient_rank_min": 3,
                    "gradient_m_gram_relative_defect_max": 1.0e-14,
                    "projected_eigen_residual_max": 1.0e-14,
                    "fixed_solve_residual_max": 1.0e-14,
                    "pou_closure_relative_error": 1.0e-14,
                    "restriction_prolongation_adjoint_relative_error_max": 1.0e-14,
                    "dense_workspace_released": True,
                    "forbidden_objects": {
                        "global_numeric_allgather": False,
                        "global_aij": False,
                        "global_schur": False,
                        "static_condensation": False,
                        "trace_harmonic_backend": False,
                        "per_patch_retained_dense_block": False,
                    },
                },
                "regional_audit": {
                    "global_numeric_allgather": False,
                    "regional_dense_row_operator_materialized": False,
                    "regional_projected_eigen_residual_max": 1.0e-14,
                    "regional_mass_orthogonality_max": 1.0e-14,
                },
                "regional_records": {},
            }
        ],
    }
    facts_path = raw / "facts.json"
    facts_path.write_text(json.dumps(facts, sort_keys=True) + "\n")
    facts_descriptor = _descriptor(raw, facts_path, 0)

    ufl = canonical / "ufl_action.npz"
    np.savez(ufl, key_json=keys, action=action)
    ufl_descriptor = _descriptor(raw, ufl, 2)
    input_path = tmp_path / "full3d_iterative_example.dat"
    input_path.write_text("synthetic input\n")
    source_sha = "a" * 40
    record = {
        "schema": "task038.full3d.iterative.local-spectral-record.v1",
        "stage": "n1",
        "profile": "local_spectral_cell_patch_regional_oracle_v1",
        "case": "p2-mpi1",
        "degree": 2,
        "mesh_target_nm": 50.0,
        "mpi_size": 1,
        "raw_dir": str(raw),
        "input": {
            "path": str(input_path),
            "sha256": _sha256(input_path),
            "bytes": input_path.stat().st_size,
        },
        "source": {
            "branch": "codex/20260820-task38-extra-full3d-iterative-0p7nm",
            "expected_sha": source_sha,
            "commit_sha_start": source_sha,
            "commit_sha_end": source_sha,
            "tracked_status_start": "",
            "tracked_status_end": "",
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            "qualified_activation": "1",
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "sys_executable": "/repo/.venv/bin/python",
        },
        "model": {
            "wavelength_nm": 13.5,
            "incident_theta_deg": 21.131,
            "incident_phi_deg": 33.690,
            "source_key_identity": "physical canonical cell/row key",
        },
        "local_spectral": {
            "selected_mode_count_max": 8,
            "facts_artifact": facts_descriptor,
        },
        "source_action": {
            "role": "full_space_source_action_owner_local_shards",
            "manifest": {"file": manifest_descriptor},
        },
        "serial_assembled_oracle": {
            "status": "measured",
            "artifact": ufl_descriptor,
        },
        "forbidden": {
            "global_numeric_allgather": False,
            "global_aij_in_production": False,
            "global_schur": False,
            "global_factor": False,
            "per_rank_full_basis_replication": False,
        },
    }
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n")
    return record_path


def test_frozen_cases_and_required_cli_contract():
    assert set(N1_CASES) == {"p2-mpi1", "p2-mpi2", "p3-mpi1", "p3-mpi2"}
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--case", "p2-mpi1"])
    args = parser.parse_args(
        [
            "--case",
            "p2-mpi1",
            "--input",
            "input.dat",
            "--raw-dir",
            "raw",
            "--record",
            "record.json",
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "1",
        ]
    )
    assert args.expected_source_sha == "a" * 40


def test_checker_passes_synthetic_record_and_rejects_identity_mutations(tmp_path):
    record_path = _synthetic_record(tmp_path)
    result = check_worker_record(record_path)
    assert result["status"] == "PASS", result
    record = json.loads(record_path.read_text())
    record["model"]["wavelength_nm"] = 14.0
    record_path.write_text(json.dumps(record))
    result = check_worker_record(record_path)
    assert result["status"] == "FAIL"
    assert any("wavelength" in error for error in result["errors"])


def test_checker_fails_closed_for_missing_role_and_malformed_npz(tmp_path):
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text())
    record["source_action"]["role"] = ""
    record_path.write_text(json.dumps(record))
    result = check_worker_record(record_path)
    assert result["status"] == "FAIL"
    assert any("role" in error for error in result["errors"])

    record_path = _synthetic_record(tmp_path / "malformed")
    record = json.loads(record_path.read_text())
    shard = Path(record["raw_dir"]) / "canonical" / "rank0000.npz"
    np.savez(shard, key_json=np.asarray(["key-a"], dtype="U"), source=np.asarray([1.0j]))
    result = check_worker_record(record_path)
    assert result["status"] == "FAIL"
    assert result["errors"]


def test_runner_checker_are_thin_and_checker_has_no_solver_runtime_imports():
    root = Path(__file__).parents[2]
    runner_source = (root / "benchmarks/run_task038_full3d_local_spectral.py").read_text()
    checker_source = (root / "benchmarks/task038_full3d_local_spectral_checker.py").read_text()
    assert "build_candidate_a" not in runner_source
    assert "build_candidate_c" not in runner_source
    assert "FixedSecondOrder" not in runner_source
    assert "physical_slab_two_level" not in runner_source
    tree = ast.parse(checker_source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert not any(
        name.startswith(("src.", "petsc4py", "dolfinx", "mpi4py", "slepc4py"))
        for name in imported
    )
    assert "np.load" in checker_source
    assert "regional_projector_diagnostic" in checker_source
