"""Pure contracts for the D1 adaptive-coarse runner and checker."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks import run_task038_full3d_adaptive_coarse as runner
from benchmarks import task038_full3d_adaptive_coarse_checker as checker


def _manifest(
    raw_dir: Path,
    artifact_name: str,
    vector_role: str,
    values: tuple[complex, ...],
    *,
    expected_mpi_size: int,
) -> dict:
    canonical = raw_dir / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    shards = []
    for rank, value in enumerate(values):
        key = {
            "tuple": [
                vector_role,
                1,
                [[rank, 0, 0]],
                0,
                ["test"],
                None,
                [1.0, 0.0],
            ]
        }
        key_bytes = json.dumps(key, sort_keys=True, separators=(",", ":")).encode()
        if vector_role == "full_fe":
            digest = hashlib.sha256(key_bytes).digest()
            value = complex(
                0.25 + 0.5 * int.from_bytes(digest[:8], "big") / float(1 << 64),
                -0.20 + 0.4 * int.from_bytes(digest[8:16], "big") / float(1 << 64),
            )
        line = {
            "schema_version": checker.SHARD_SCHEMA,
            "key": key,
            "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
            "value": [float(value.real), float(value.imag)],
        }
        shard_path = canonical / f"{artifact_name}.rank{rank:04d}.jsonl"
        shard_path.write_text(
            json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        shards.append(
            {
                "filename": shard_path.name,
                "packet_count": 1,
                "file_sha256": hashlib.sha256(shard_path.read_bytes()).hexdigest(),
                "local_duplicate_count": 0,
                "packet_finite": True,
                "dtype": "complex128",
                "schema_version": checker.SHARD_SCHEMA,
            }
        )
    manifest = {
        "schema_version": checker.MANIFEST_SCHEMA,
        "role": vector_role,
        "mpi_size": expected_mpi_size,
        "dtype": "complex128",
        "key_digest_algorithm": "sha256(canonical-key-json-v1)",
        "global_summed_packet_count": expected_mpi_size,
        "summed_local_duplicate_count": 0,
        "per_rank_shards": shards,
        "extractor_audit": {"role": vector_role},
    }
    manifest_path = canonical / f"{artifact_name}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "kind": (
            "physical_hcurl_primal_packet_manifest"
            if vector_role == "full_fe"
            else "physical_hcurl_dual_packet_manifest"
        ),
        "name": artifact_name,
        "role": vector_role,
        "relative_path": str(manifest_path.relative_to(raw_dir)),
        "bytes": manifest_path.stat().st_size,
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "packet_count": 2,
        "mpi_size": 2,
    }


def _synthetic_record(tmp_path: Path, *, case: str = "p2-mpi2") -> Path:
    degree = runner.D1_CASES[case]["degree"]
    mpi_size = runner.D1_CASES[case]["mpi_size"]
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    descriptors = {}
    for artifact_name in (
        "source",
        "B_slab0",
        "B_slab0_repeat",
        "M_slab0",
        "M_slab0_repeat",
        "B_slab1",
        "B_slab1_repeat",
        "M_slab1",
        "M_slab1_repeat",
    ):
        vector_role = "full_fe" if artifact_name == "source" else "full_fe_dual"
        descriptors[artifact_name] = _manifest(
            raw_dir,
            artifact_name,
            vector_role,
            tuple(1.0 + rank + (0.2 - 0.1j) for rank in range(mpi_size)),
            expected_mpi_size=mpi_size,
        )
    operators = {}
    for slab in ("slab0", "slab1"):
        operators[slab] = {
            name: {
                "action": descriptors[
                    f"{'M' if name == 'M_Gamma' else name}_slab{slab[-1]}"
                ],
                "repeat": descriptors[
                    f"{'M' if name == 'M_Gamma' else name}_slab{slab[-1]}_repeat"
                ],
                "worker_repeat_relative_l2": 0.0,
            }
            for name in ("B", "M_Gamma")
        }
    topology_audit = {
        "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
        "phase_application": "finalized_floquet_mpc_once",
        "bounded_material_class_collective": True,
        "numeric_allgather": False,
        "global_aij_materialized": False,
        "dense_interface_mass_materialized": False,
        "dense_interface_schur_materialized": False,
        "slab_factor_materialized": False,
        "slave_rows_excluded": True,
    }
    definition = {
        "schema": "fullspace.trace-harmonic-definition.v1",
        "profile": checker.D1_PROFILE,
        "slab_id": 0,
        "slab_partition": "owned_cells_from_cfg.interface_z",
        "auxiliary_form": "curl_curl_plus_k0_squared_abs_epsilon_mass",
        "coercive_coefficient": "k0**2*abs(epsilon_r(x))",
        "source_independent": True,
        "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
        "interface_mass": "broken_tangential_facet_mass_dS",
        "phase_application": "finalized_floquet_mpc_once",
        "slave_rows_excluded_from_action": True,
        "fixture_assembled_oracle": "p2_p3_only",
        "future_p6_backend": "owner_local_matrix_free",
        "global_numeric_allgather": False,
        "global_aij_materialized": False,
        "global_schur_materialized": False,
        "growing_factor_materialized": False,
    }
    record = {
        "schema_version": runner.D1_SCHEMA,
        "stage": "d1",
        "case": case,
        "degree": degree,
        "mpi_size": mpi_size,
        "profile": checker.D1_PROFILE,
        "mesh_target_nm": 50.0,
        "raw_dir": str(raw_dir),
        "source": {
            "branch": checker.D1_BRANCH,
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "tracked_status_start": "",
            "tracked_status_end": "",
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            "qualified_marker": "1",
            "sys_executable": "/repo/.venv/bin/python",
            "qualified_venv_bin_resolved": "/repo/.venv/bin",
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "model": {
            "wavelength_nm": 13.5,
            "incident_theta_deg": 21.131,
            "incident_phi_deg": 33.690,
            "source_formula": "complex_value=stable_sha256(canonical_full_fe_key)",
            "source_key_identity": "physical full_fe canonical key; no local row/rank/mpi-size input",
        },
        "topology": {
            "profile": "full3d_scalable_v1",
            "slab_count": 2,
            "global_facet_count": 2,
            "local_facet_count": 1,
            "canonical_sha256": "b" * 64,
            "owned_trace_rows": 2,
            "ghost_trace_rows": 0,
            "owner_closure": True,
            "neighbor_plan": {
                "forward_send_peers": [1],
                "forward_recv_peers": [1],
                "backward_send_peers": [1],
                "backward_recv_peers": [1],
                "lower_participant_ranks": [0],
                "upper_participant_ranks": [1],
            },
            "restriction_prolongation_adjoint_relative_error": 0.0,
            "floquet_phase_nontrivial": True,
            "interface_classifications": ["homogeneous", "nonhomogeneous"],
            "audit": topology_audit,
        },
        "definitions": {"slab0": definition, "slab1": {**definition, "slab_id": 1}},
        "artifacts": {"source": descriptors["source"], "operators": operators},
        "serial_algebra": {
            "status": "not_run",
            "boundary": "distributed_action_identity_only; serial assembled algebra is MPI1-only",
        },
        "resource": {
            "rank_max_current_rss_bytes": 1024,
            "rank_max_swap_used_bytes": 0,
        },
        "execution": {
            "ksp_created": False,
            "slepc_used": False,
            "global_numeric_allgather": False,
            "pde_solve": False,
        },
    }
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record_path


def test_d1_checker_passes_synthetic_mpi2_and_is_fail_closed(tmp_path: Path):
    record_path = _synthetic_record(tmp_path)
    passed = checker.check_record(record_path)
    assert passed["passed"] is True

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["artifacts"]["source"]["role"] = "full_fe_dual"
    wrong_role = tmp_path / "wrong-role.json"
    wrong_role.write_text(json.dumps(record), encoding="utf-8")
    assert checker.check_record(wrong_role)["passed"] is False

    record = json.loads(record_path.read_text(encoding="utf-8"))
    del record["artifacts"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(record), encoding="utf-8")
    failed = checker.check_record(broken)
    assert failed["passed"] is False
    assert failed["errors"]


def test_d1_checker_rejects_dirty_or_missing_required_identity(tmp_path: Path):
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["source"]["tracked_status_start"] = " M source.py"
    record["topology"].pop("canonical_sha256")
    broken = tmp_path / "dirty.json"
    broken.write_text(json.dumps(record), encoding="utf-8")
    result = checker.check_record(broken)
    assert result["passed"] is False
    assert any("source identity" in item or "canonical digest" in item for item in result["errors"])

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["model"]["wavelength_nm"] = 14.0
    model_broken = tmp_path / "model-broken.json"
    model_broken.write_text(json.dumps(record), encoding="utf-8")
    model_result = checker.check_record(model_broken)
    assert model_result["passed"] is False
    assert any("model identity" in item for item in model_result["errors"])

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["runtime"]["qualified_venv_bin_resolved"] = "relative/bin"
    runtime_broken = tmp_path / "runtime-broken.json"
    runtime_broken.write_text(json.dumps(record), encoding="utf-8")
    runtime_result = checker.check_record(runtime_broken)
    assert runtime_result["passed"] is False
    assert any("qualified venv bin" in item for item in runtime_result["errors"])


def test_d1_checker_malformed_serial_npz_fails_closed(tmp_path: Path):
    record_path = _synthetic_record(tmp_path, case="p2-mpi1")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    raw_dir = Path(record["raw_dir"])
    bad_npz = raw_dir / "malformed.npz"
    import numpy as np

    np.savez(bad_npz, B_slab0=np.zeros(3, dtype=np.complex128))
    record["serial_algebra"] = {
        "status": "measured",
        "relative_path": "malformed.npz",
        "bytes": bad_npz.stat().st_size,
        "sha256": hashlib.sha256(bad_npz.read_bytes()).hexdigest(),
    }
    broken = tmp_path / "malformed-serial.json"
    broken.write_text(json.dumps(record), encoding="utf-8")
    result = checker.check_record(broken)
    assert result["passed"] is False
    assert any("serial algebra" in item for item in result["errors"])


def test_d1_runner_parser_requires_stage_case_and_expected_identity():
    with pytest.raises(SystemExit):
        runner._parser().parse_args([])
    args = runner._parser().parse_args(
        [
            "--stage",
            "d1",
            "--case",
            "p2-mpi1",
            "--raw-dir",
            "/tmp/raw",
            "--record",
            "/tmp/record.json",
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "1",
        ]
    )
    assert args.stage == "d1"
    assert args.case == "p2-mpi1"


def test_d1_evidence_layer_has_no_numeric_allgather_or_solver_imports():
    root = Path(__file__).resolve().parents[2]
    runner_tree = ast.parse(
        (root / "benchmarks/run_task038_full3d_adaptive_coarse.py").read_text()
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "allgather"
        for node in ast.walk(runner_tree)
    )
    checker_tree = ast.parse(
        (root / "benchmarks/task038_full3d_adaptive_coarse_checker.py").read_text()
    )
    for node in ast.walk(checker_tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert all(
            not any(token in name.lower() for token in ("solver", "petsc", "mpi", "dolfinx"))
            for name in names
        )
