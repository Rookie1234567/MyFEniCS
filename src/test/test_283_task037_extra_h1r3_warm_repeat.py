from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.run_task037_extra_candidate_h import (
    H1R3_CANDIDATE_APPLY_COUNT,
    H1R3_PEAK_LIMIT_BYTES,
    H1R3_RSS_SPAN_LIMIT_BYTES,
    H1R3_SOURCE_LABEL,
    H1R3_STEADY_MEDIAN_LIMIT_SECONDS,
    H1R3_TELEMETRY_FILE,
    H1R3_TIMEOUT_SECONDS,
    _h1r3_file_metadata,
    _h1r3_copy_first_output,
    _h1r3_scope,
    _evaluate_h1r3_warm_worker_qualification,
    _parser,
    _watchdog_command,
    run_h1r3_check,
)
from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
)
from src.solvers.hcurl_canonical_vector import canonical_key


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        wavevector=(1.0 + 0.1j, 0.5 - 0.2j, 0.25 + 0.0j),
        polarization_vector=(1.0 + 0.0j, 0.25 + 0.5j, -0.5 + 0.0j),
        incident_amplitude=1.0 + 0.25j,
    )


def _source_definition() -> dict:
    from benchmarks.run_task037_extra_candidate_h import _source_definition

    return _source_definition(H1R3_SOURCE_LABEL, _cfg())


def _scope() -> dict:
    scope = _h1r3_scope()
    scope.update({"global_rows": 4, "constraint_count": 1})
    return scope


def _candidate_audit() -> dict:
    return {
        "backend": (
            "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
            " + vectorized MPC R^H"
        ),
        "form_rank": 1,
        "coefficient_count": 1,
        "apply_count": H1R3_CANDIDATE_APPLY_COUNT,
        "local_owned_rows": 4,
        "local_ghost_rows": 0,
        "local_storage_entries": 4,
        "global_rows": 4,
        "constraint_count": 1,
        "constraint_nnz_closes": True,
        "constraint_nnz": 1,
        "retained_numeric_payload_components": {"bounded_buffers": 128},
        "retained_numeric_payload_local_bytes": 128,
        "retained_numeric_payload_global_sum_bytes": 128,
        "retained_numeric_payload_global_max_bytes": 128,
        "last_packed_coefficient_bytes": 32,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "retained_dense_cell_tensor_count": 0,
        "dense_cell_tensor_materialized_per_apply": False,
        "cell_metadata_retained": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "factor_count": 0,
        "ksp_created": False,
        "dtn_used": False,
        "ordinary_default_changed": False,
    }


def _telemetry() -> list[dict]:
    records = []
    for index in range(1, H1R3_CANDIDATE_APPLY_COUNT + 1):
        records.append(
            {
                "schema": "task037.candidate_h.h1r3.apply_telemetry.v1",
                "apply_index": index,
                "seconds": 1.0 if index >= 5 else 1.1,
                "process_tree_root_pid": 10,
                "process_tree_pids": [10, 11],
                "process_tree_worker_pid": 11,
                "worker_pid_in_process_tree": True,
                "process_tree_rss_bytes": 100,
                "process_tree_pss_bytes": 80,
                "process_tree_uss_bytes": 60,
                "process_tree_swap_bytes": 0,
                "process_tree_all_status_readable": True,
                "retained_numeric_payload_components": {"bounded_buffers": 128},
                "retained_numeric_payload_local_bytes": 128,
                "retained_numeric_payload_global_sum_bytes": 128,
                "retained_numeric_payload_global_max_bytes": 128,
                "packed_temporary_bytes": 32,
                "output_sha256": "a" * 64,
                "finite": True,
                "bitwise_equal_to_first": True,
                "reference_relative_error": (
                    1.0e-15 if index in (1, H1R3_CANDIDATE_APPLY_COUNT) else None
                ),
            }
        )
    return records


def _measurement() -> dict:
    source = _source_definition()
    return {
        "label": H1R3_SOURCE_LABEL,
        "kind": "physical_coordinate_analytic_primal",
        "iteration": None,
        "source_definition": source,
        "source_definition_sha256": source["definition_sha256"],
        "reference_apply_count": 1,
        "candidate_apply_count": H1R3_CANDIDATE_APPLY_COUNT,
        "reference_apply_seconds": 1.0,
        "candidate_apply_seconds": [
            item["seconds"] for item in _telemetry()
        ],
        "first_vs_reference_relative_error": 1.0e-15,
        "last_vs_reference_relative_error": 1.0e-15,
        "canonical_export": True,
        "canonical_export_count": 1,
        "candidate_manifest": {
            "path": "canonical/seed_17037/candidate_manifest.json",
            "sha256": "b" * 64,
            "packet_count": 3,
        },
    }


def _worker_qualification_record() -> tuple[dict, dict, list[dict]]:
    measurement = _measurement()
    audit = _candidate_audit()
    telemetry = _telemetry()
    return measurement, audit, telemetry


def test_h1r3_fixed_cli_and_scope_contract():
    parser = _parser()
    worker = parser.parse_args(["h1r3-warm-worker", "--run-dir", "relative"])
    assert worker.command == "h1r3-warm-worker"
    assert not any(
        hasattr(worker, name)
        for name in ("degree", "h_nm", "source", "repeat", "timeout", "memory")
    )
    watchdog = parser.parse_args(["h1r3-warm-watchdog", "--run-dir", "relative"])
    command = _watchdog_command(watchdog, mode="h1r3_warm")
    assert command[:3] == ["mpiexec", "-n", "1"]
    assert command[6:8] == ["h1r3-warm-worker", "--run-dir"]
    assert command[-1] == str(Path("relative").resolve())
    check = parser.parse_args(
        ["h1r3-warm-check", "--run-dir", "run", "--output", "compact.json"]
    )
    assert check.output.name == "compact.json"
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["h1r3-warm-worker", "--run-dir", "run", "--repeat", "12"]
        )


def test_h1r3_first_output_copy_copies_into_owned_first_vec():
    class FakeVec:
        def __init__(self, value):
            self.value = value

        def copy(self, *, result):
            result.value = list(self.value)

    output = FakeVec([1, 2, 3])
    first_output = FakeVec([0, 0, 0])
    _h1r3_copy_first_output(output, first_output)
    assert first_output.value == [1, 2, 3]
    assert output.value == [1, 2, 3]


def test_h1r3_worker_qualification_recomputes_twelve_apply_and_steady_gates():
    measurement, audit, telemetry = _worker_qualification_record()
    qualification = _evaluate_h1r3_warm_worker_qualification(
        measurement, audit, telemetry, scope=_scope()
    )
    assert qualification["pass"] is True
    assert qualification["problems"] == []
    assert len(telemetry) == 12
    assert qualification["steady_median_apply_seconds"] == 1.0
    assert qualification["steady_median_apply_seconds"] <= H1R3_STEADY_MEDIAN_LIMIT_SECONDS
    assert qualification["steady_rss_span_bytes"] == 0
    assert qualification["canonical_gate_pass"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "error",
        "hash_identity",
        "raw_binding",
        "payload",
        "payload_field_missing",
        "packed",
        "rss_span",
        "swap",
        "root_pid",
        "inventory_field_missing",
        "count",
    ),
)
def test_h1r3_worker_qualification_rejects_representative_mutations(mutation):
    measurement, audit, telemetry = _worker_qualification_record()
    if mutation == "missing":
        telemetry = telemetry[:-1]
    elif mutation == "error":
        measurement["last_vs_reference_relative_error"] = 1.0e-3
    elif mutation == "hash_identity":
        telemetry[5]["output_sha256"] = "b" * 64
        telemetry[5]["bitwise_equal_to_first"] = True
    elif mutation == "raw_binding":
        measurement["candidate_apply_seconds"][0] += 0.1
    elif mutation == "payload":
        telemetry[5]["retained_numeric_payload_components"]["bounded_buffers"] = 129
    elif mutation == "payload_field_missing":
        telemetry[5].pop("retained_numeric_payload_global_max_bytes")
    elif mutation == "packed":
        telemetry[5]["packed_temporary_bytes"] = 33
    elif mutation == "rss_span":
        telemetry[5]["process_tree_rss_bytes"] = H1R3_RSS_SPAN_LIMIT_BYTES + 101
    elif mutation == "swap":
        telemetry[5]["process_tree_swap_bytes"] = 1
    elif mutation == "root_pid":
        telemetry[5]["process_tree_root_pid"] = 12
    elif mutation == "inventory_field_missing":
        audit.pop("cell_schur_matrix_nnz")
    elif mutation == "count":
        measurement["candidate_apply_count"] = 11
    qualification = _evaluate_h1r3_warm_worker_qualification(
        measurement, audit, telemetry, scope=_scope()
    )
    assert qualification["pass"] is False
    assert qualification["problems"]


def test_h1r3_canonical_numeric_gate_is_separate_from_other_gates():
    measurement, audit, telemetry = _worker_qualification_record()
    telemetry[5]["process_tree_swap_bytes"] = 1
    measurement["reference_apply_seconds"] = 0.0
    qualification = _evaluate_h1r3_warm_worker_qualification(
        measurement, audit, telemetry, scope=_scope()
    )
    assert qualification["numerical_gate_pass"] is True
    assert qualification["canonical_gate_pass"] is True
    assert qualification["timing_gate_pass"] is False
    assert qualification["resource_gate_pass"] is False
    assert qualification["pass"] is False


def _source_identity() -> dict:
    return {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _make_raw_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "h1r3"
    run_dir.mkdir()
    (run_dir / "h1r3_root_pid.json").write_text(
        '{"root_pid": 10, "schema": "task037.candidate_h.h1r3.root_pid.v1"}\n',
        encoding="utf-8",
    )
    telemetry = _telemetry()
    (run_dir / H1R3_TELEMETRY_FILE).write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in telemetry),
        encoding="utf-8",
    )
    timeline = [
        {
            "worker_alive": True,
            "worker_tree_rss_sum_bytes": 100,
            "process_tree_swap_bytes": 0,
            "process_tree_all_status_readable": True,
        },
        {
            "worker_alive": True,
            "worker_tree_rss_sum_bytes": 100,
            "process_tree_swap_bytes": 0,
            "process_tree_all_status_readable": True,
        },
        {
            "worker_alive": False,
            "worker_tree_rss_sum_bytes": 0,
            "process_tree_swap_bytes": 0,
            "process_tree_all_status_readable": True,
        },
    ]
    (run_dir / "watchdog_timeline.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in timeline),
        encoding="utf-8",
    )
    (run_dir / "worker_stdout.txt").write_bytes(b"synthetic h1r3\n")
    source_dir = run_dir / "canonical" / H1R3_SOURCE_LABEL
    source_dir.mkdir(parents=True)
    packets = tuple(
        (
            canonical_key(
                role="full_fe_dual",
                entity_dimension=1,
                physical_entity=((index, 0, 0), (index + 1, 0, 0)),
                entity_local_basis_index=0,
                orientation_state=0,
            ),
            complex(index + 1.0, 0.5),
        )
        for index in range(3)
    )
    shard_metadata = write_canonical_packet_shard(
        source_dir / "candidate_rank0.jsonl", packets
    )
    manifest = canonical_shard_manifest(
        role="full_fe_dual",
        mpi_size=1,
        shard_metadata=(shard_metadata,),
        extractor_audit={
            "source": H1R3_SOURCE_LABEL,
            "method": "H1R3-direct-rank-one-MPC",
        },
    )
    manifest_path = source_dir / "candidate_manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    measurement, audit, _ = _worker_qualification_record()
    measurement["candidate_manifest"] = {
        "path": "canonical/seed_17037/candidate_manifest.json",
        "sha256": manifest_sha,
        "packet_count": 3,
    }
    scope = _scope()
    qualification = _evaluate_h1r3_warm_worker_qualification(
        measurement, audit, telemetry, scope=scope
    )
    runtime = {
        "_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1",
        "sys.executable": sys.executable,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    telemetry_metadata = _h1r3_file_metadata(run_dir)[H1R3_TELEMETRY_FILE]
    worker = {
        "schema": "task037.candidate_h.h1r3.warm.worker.v1",
        "runtime_identity": runtime,
        "status": "pass",
        "mpi_size": 1,
        "global_rows": 4,
        "constraint_count": 1,
        "scope": scope,
        "source_definitions": {H1R3_SOURCE_LABEL: measurement["source_definition"]},
        "measurements": [measurement],
        "apply_telemetry": {"path": H1R3_TELEMETRY_FILE, **telemetry_metadata},
        "candidate_action_audit": audit,
        "reference_action": {
            "type": "MpcFormActionContext",
            "same_worker": True,
            "apply_count": 1,
            "global_matrix_materialized": False,
        },
        "source_at_start": _source_identity(),
        "source_at_end": _source_identity(),
        "qualification": qualification,
    }
    _write_json(run_dir / "run_summary.json", attach_evidence_sha256(worker))
    artifacts = _h1r3_file_metadata(run_dir)
    manifest_relative_path = "canonical/seed_17037/candidate_manifest.json"
    artifacts[manifest_relative_path] = {
        "path": manifest_relative_path,
        "present": True,
        "bytes": (run_dir / manifest_relative_path).stat().st_size,
        "sha256": hashlib.sha256(
            (run_dir / manifest_relative_path).read_bytes()
        ).hexdigest(),
    }
    args = SimpleNamespace(run_dir=run_dir)
    watchdog = {
        "schema": "task037.candidate_h.h1r3.warm.watchdog.v1",
        "command": _watchdog_command(args, mode="h1r3_warm"),
        "mpi_size": 1,
        "return_code": 0,
        "status": "pass",
        "controlled_stop": None,
        "timeout_seconds": H1R3_TIMEOUT_SECONDS,
        "poll_interval_seconds": 0.25,
        "rss_limit_bytes": H1R3_PEAK_LIMIT_BYTES,
        "termination": {"requested": False, "method": None},
        "wall_seconds": 1.0,
        "completion_elapsed_seconds": 1.0,
        "peak_process_tree_rss_bytes": 100,
        "peak_includes_only_worker_alive_samples": True,
        "worker_live_sample_count": 2,
        "worker_process_tree_swap_bytes": 0,
        "worker_swap_zero": True,
        "resource_authority_readable": True,
        "final_sample": timeline[-1],
        "worker_summary_present": True,
        "worker_summary_status": "pass",
        "worker_summary_evidence_sha256_valid": True,
        "worker_qualification_recomputed": qualification,
        "worker_qualification_pass": True,
        "watchdog_runtime_identity": runtime,
        "worker_runtime_identity_match": True,
        "source_at_start": _source_identity(),
        "source_at_end": _source_identity(),
        "source_stable_clean": True,
        "reference_and_candidate_same_worker": True,
        "raw_artifacts": artifacts,
    }
    _write_json(run_dir / "watchdog_summary.json", attach_evidence_sha256(watchdog))
    return run_dir


def test_h1r3_checker_recomputes_good_raw_and_binds_hashes(tmp_path):
    run_dir = _make_raw_run(tmp_path)
    output = tmp_path / "compact.json"
    assert run_h1r3_check(run_dir, output) == 0
    compact = json.loads(output.read_text(encoding="utf-8"))
    assert compact["pass"] is True
    assert compact["status"] == "pass"
    assert compact["problems"] == []
    assert evidence_sha256_is_valid(compact)
    assert compact["measurement"]["global_rows"] == 4
    assert compact["measurement"]["constraint_count"] == 1
    assert compact["measurement"]["canonical_export"] is True
    assert compact["measurement"]["canonical_packet_count"] == 3
    per_apply = compact["measurement"]["per_apply_telemetry"]
    assert len(per_apply) == H1R3_CANDIDATE_APPLY_COUNT
    assert per_apply[0]["apply_index"] == 1
    assert per_apply[0]["retained_numeric_payload_global_sum_bytes"] == 128
    assert per_apply[0]["retained_numeric_payload_global_max_bytes"] == 128
    assert compact["measurement"]["steady_median_apply_seconds"] == 1.0
    assert compact["measurement"]["steady_rss_span_bytes"] == 0
    assert compact["scope_boundary"] == {
        "H1R3.1": "eligible_by_review_v5_if_H1R3.0_pass",
        "H1R3.2": "locked_pending_H1R3.1_pass",
        "H2": "locked",
    }
    assert compact["memory_authority"]["review_v5_peak_gate_pass"] is True
    assert compact["memory_authority"]["user_lt_2GB_target_evaluated"] is True
    assert compact["memory_authority"]["user_lt_2GB_target_pass"] is True
    assert compact["runtime_identity"]["match"] is True
    assert compact["runtime_identity"]["watchdog"]["_MYFENICS_WSL_QUALIFIED_ACTIVATION"] == "1"
    assert compact["runtime_identity"]["watchdog"]["sys.executable"] == sys.executable
    for relative_path, metadata in compact["raw_artifacts"].items():
        if metadata["present"]:
            assert metadata["sha256"] == hashlib.sha256(
                (run_dir / relative_path).read_bytes()
            ).hexdigest()


def test_h1r3_checker_missing_raw_fails_closed(tmp_path):
    output = tmp_path / "compact.json"
    assert run_h1r3_check(tmp_path / "missing", output) == 1
    compact = json.loads(output.read_text(encoding="utf-8"))
    assert compact["pass"] is False
    assert compact["status"] == "gate_failed"


def test_h1r3_checker_peak_mutation_fails_from_recomputed_timeline(tmp_path):
    run_dir = _make_raw_run(tmp_path)
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    rows = [json.loads(line) for line in timeline_path.read_text().splitlines()]
    rows[0]["worker_tree_rss_sum_bytes"] = H1R3_PEAK_LIMIT_BYTES + 1
    timeline_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    watchdog_path = run_dir / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    watchdog["peak_process_tree_rss_bytes"] = H1R3_PEAK_LIMIT_BYTES + 1
    watchdog["raw_artifacts"]["watchdog_timeline.jsonl"] = {
        "path": "watchdog_timeline.jsonl",
        "present": True,
        "bytes": timeline_path.stat().st_size,
        "sha256": hashlib.sha256(timeline_path.read_bytes()).hexdigest(),
    }
    _write_json(watchdog_path, attach_evidence_sha256(watchdog))
    output = tmp_path / "compact.json"
    assert run_h1r3_check(run_dir, output) == 1
    compact = json.loads(output.read_text(encoding="utf-8"))
    assert compact["pass"] is False
    assert any("timeline.peak_limit" in problem for problem in compact["problems"])
