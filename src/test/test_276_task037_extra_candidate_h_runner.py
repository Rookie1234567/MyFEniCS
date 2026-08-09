from __future__ import annotations

from copy import deepcopy
import json
import sys

import numpy as np
import pytest

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.run_task037_extra_candidate_h import (
    DUAL_RELATIVE_TOLERANCE,
    SOURCE_DEFINITIONS,
    _evaluate_worker_qualification,
    _parser,
    _source_values,
    _source_definition,
    _watchdog_command,
    compare_run_directories,
)
from src.common.config_3d import target_stage4_config
from src.solvers.hcurl_canonical_vector import canonical_key


def test_candidate_h_sources_and_subcommands_are_fixed():
    cfg = target_stage4_config(degree=2, h_nm=1000.0)
    assert tuple(SOURCE_DEFINITIONS) == (
        "seed_17037",
        "seed_27037",
        "seed_37037",
        "physical_rhs_like_primal",
    )
    definitions = tuple(_source_definition(label, cfg) for label in SOURCE_DEFINITIONS)
    assert [item["seed"] for item in definitions[:3]] == [17037, 27037, 37037]
    assert [item["frequency"] for item in definitions[:3]] == [
        (1, 1, 0),
        (2, 1, 1),
        (4, 3, 2),
    ]
    assert definitions[3]["seed"] is None
    assert all(len(item["definition_sha256"]) == 64 for item in definitions)
    parser = _parser()
    assert parser.parse_args(["worker", "--run-dir", "/tmp/h1-worker"]).command == "worker"
    watchdog_args = parser.parse_args(
        ["watchdog", "--run-dir", "/tmp/h1-watchdog", "--mpi-size", "2"]
    )
    watchdog_command = _watchdog_command(watchdog_args)
    assert watchdog_command[:3] == ["mpiexec", "-n", "2"]
    assert watchdog_command[3] == sys.executable
    assert "--degree" not in watchdog_command
    assert "--h-nm" not in watchdog_command
    with pytest.raises(SystemExit):
        parser.parse_args(["worker", "--run-dir", "/tmp/h1", "--degree", "2"])
    with pytest.raises(SystemExit):
        parser.parse_args(["watchdog", "--run-dir", "/tmp/h1", "--mpi-size", "4"])
    compare_args = parser.parse_args(
        ["compare", "--mpi1-run-dir", "mpi1", "--mpi2-run-dir", "mpi2"]
    )
    assert compare_args.mpi1_run_dir.name == "mpi1"
    assert compare_args.mpi2_run_dir.name == "mpi2"
    assert not hasattr(compare_args, "relative_tolerance")

    coordinates = np.asarray(
        [[0.2, 0.7], [0.3, 0.4], [0.1, 0.8]], dtype=np.float64
    )
    for label in SOURCE_DEFINITIONS:
        definition = _source_definition(label, cfg)
        if label == "physical_rhs_like_primal":
            assert "not assembled traction RHS" in definition["primal_semantics"]
            continue
        source = SOURCE_DEFINITIONS[label]
        scale = np.asarray(
            (
                cfg.x_max - cfg.x_min,
                cfg.y_max - cfg.y_min,
                cfg.domain_z_max - cfg.domain_z_min,
            ),
            dtype=np.float64,
        )
        normalized = np.vstack(
            (
                (coordinates[0] - cfg.x_min) / scale[0],
                (coordinates[1] - cfg.y_min) / scale[1],
                (coordinates[2] - cfg.domain_z_min) / scale[2],
            )
        )
        coefficients = source["envelope_coefficients"]
        envelope = sum(
            complex(*coefficients[name]) * values
            for name, values in (
                ("constant", 1.0),
                ("xi", normalized[0]),
                ("eta", normalized[1]),
                ("zeta", normalized[2]),
            )
        )
        frequency = source["frequency"]
        phase = np.exp(2j * np.pi * np.sum(
            np.asarray(frequency, dtype=np.float64)[:, None] * normalized,
            axis=0,
        ))
        expected = np.asarray(cfg.polarization_vector, dtype=np.complex128)[:, None]
        expected = expected * envelope[None, :] * phase[None, :]
        np.testing.assert_array_equal(_source_values(label, cfg, coordinates), expected)
        assert definition["frequency"] == source["frequency"]
        assert definition["envelope_coefficients"] == source["envelope_coefficients"]


def test_candidate_h_compare_artifact_contract(tmp_path):
    keys = (
        canonical_key(
            role="full_fe_dual",
            entity_dimension=3,
            physical_entity=((0, 0, 0), (1, 0, 0)),
            entity_local_basis_index=0,
            orientation_state=("canonical_cell", "Tt_apply"),
        ),
        canonical_key(
            role="full_fe_dual",
            entity_dimension=3,
            physical_entity=((0, 0, 0), (0, 1, 0)),
            entity_local_basis_index=1,
            orientation_state=("canonical_cell", "Tt_apply"),
        ),
    )
    manifest_records = {"mpi1": {}, "mpi2": {}}
    for run_name, mpi_size in (("mpi1", 1), ("mpi2", 2)):
        for label in SOURCE_DEFINITIONS:
            source_dir = tmp_path / run_name / "canonical" / label
            source_dir.mkdir(parents=True)
            shard_metadata = []
            for rank, shard_keys in enumerate(
                (keys,) if mpi_size == 1 else ((keys[0],), (keys[1],))
            ):
                shard = source_dir / f"candidate_rank{rank}.jsonl"
                shard_metadata.append(
                    write_canonical_packet_shard(
                        shard,
                        tuple((key, 1.0 + 2.0j) for key in shard_keys),
                    )
                )
            manifest = canonical_shard_manifest(
                role="full_fe_dual",
                mpi_size=mpi_size,
                shard_metadata=tuple(shard_metadata),
                extractor_audit={"source": label, "method": "Candidate-H"},
            )
            manifest_path = source_dir / "candidate_manifest.json"
            manifest_sha = write_canonical_manifest(manifest_path, manifest)
            manifest_records[run_name][label] = {
                "path": f"canonical/{label}/candidate_manifest.json",
                "sha256": manifest_sha,
            }
    source_sha = "a" * 40
    for run_name, mpi_size in (("mpi1", 1), ("mpi2", 2)):
        run_dir = tmp_path / run_name
        measurements = [
            {
                "label": label,
                "candidate_manifest": manifest_records[run_name][label],
            }
            for label in SOURCE_DEFINITIONS
        ]
        run_summary = {
            "status": "pass",
            "scope": {
                "mpi_size": mpi_size,
                "global_rows": 10,
                "constraint_count": 8,
            },
            "measurements": measurements,
            "qualification": {"pass": True},
        }
        (run_dir / "run_summary.json").write_text(
            json.dumps(run_summary), encoding="utf-8"
        )
        source_identity = {
            "source_commit_full_sha": source_sha,
            "tracked_source_dirty": False,
        }
        watchdog_summary = {
            "status": "pass",
            "mpi_size": mpi_size,
            "worker_qualification_pass": True,
            "source_stable_clean": True,
            "source_at_start": source_identity,
            "source_at_end": source_identity,
        }
        (run_dir / "watchdog_summary.json").write_text(
            json.dumps(watchdog_summary), encoding="utf-8"
        )
    assert json.loads((tmp_path / "mpi1" / "run_summary.json").read_text())[
        "scope"
    ]["constraint_count"] == 8
    comparison = compare_run_directories(tmp_path / "mpi1", tmp_path / "mpi2")
    assert comparison["pass"] is True
    assert comparison["run_identity_checks"]["pass"] is True
    assert comparison["run_identity_checks"]["common_source_sha"] == source_sha
    assert comparison["source_order"] == list(SOURCE_DEFINITIONS)
    assert comparison["relative_tolerance"] == DUAL_RELATIVE_TOLERANCE
    assert comparison["duplicate_left_count"] == 0
    assert comparison["duplicate_right_count"] == 0
    assert comparison["missing_key_count"] == 0
    assert comparison["extra_key_count"] == 0

    mpi2_watchdog_path = tmp_path / "mpi2" / "watchdog_summary.json"
    bad_watchdog = json.loads(mpi2_watchdog_path.read_text(encoding="utf-8"))
    bad_watchdog["mpi_size"] = 1
    mpi2_watchdog_path.write_text(json.dumps(bad_watchdog), encoding="utf-8")
    bad_comparison = compare_run_directories(tmp_path / "mpi1", tmp_path / "mpi2")
    assert bad_comparison["run_identity_checks"]["pass"] is False
    assert bad_comparison["pass"] is False


def _qualification_audit():
    return {
        "cell_dof_count": 882,
        "global_matrix_materialized": False,
        "global_A_materialized": False,
        "global_condensed_schur_materialized": False,
        "retained_cell_dense_882x882_count": 0,
        "cell_tensor_scratch_count": 1,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "slab_factor_count": 0,
        "dtn_probe": False,
        "explicit_C_nnz": 0,
        "explicit_D_nnz": 0,
        "ksp_create_count": 0,
        "ksp_solve_count": 0,
        "official_field": False,
        "official_RTA": False,
        "ordinary_default_changed": False,
        "candidate_owned_numeric_payload_global_sum_bytes": 1024,
        "candidate_owned_numeric_payload_global_max_bytes": 1024,
    }


def _qualification_measurements(packet_count=4):
    return [
        {
            "label": label,
            "reference_vs_candidate_relative_error": 0.0,
            "finite": True,
            "deterministic": True,
            "candidate_canonical_packet_count": packet_count,
        }
        for label in SOURCE_DEFINITIONS
    ]


def test_candidate_h_worker_qualification_fixed_sources_payload_and_inventory():
    good = _evaluate_worker_qualification(
        _qualification_measurements(),
        _qualification_audit(),
        global_rows=10,
        constraint_count=6,
    )
    assert good["pass"] is True

    bad_measurement = _qualification_measurements()
    bad_measurement[0]["reference_vs_candidate_relative_error"] = 2.0e-11
    assert _evaluate_worker_qualification(
        bad_measurement,
        _qualification_audit(),
        global_rows=10,
        constraint_count=6,
    )["pass"] is False

    bad_payload = _qualification_audit()
    bad_payload["candidate_owned_numeric_payload_global_sum_bytes"] = int(0.50 * 1024**3) + 1
    assert _evaluate_worker_qualification(
        _qualification_measurements(),
        bad_payload,
        global_rows=10,
        constraint_count=6,
    )["pass"] is False

    bad_inventory = deepcopy(_qualification_audit())
    bad_inventory["dtn_probe"] = True
    assert _evaluate_worker_qualification(
        _qualification_measurements(),
        bad_inventory,
        global_rows=10,
        constraint_count=6,
    )["pass"] is False
