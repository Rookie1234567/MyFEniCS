from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
)
from benchmarks.run_task037_extra_candidate_h import (
    H1R31_CANONICAL_TOLERANCE,
    H1R31_CONSTRAINT_COUNT,
    H1R31_CANDIDATE_SECOND_LIMIT_SECONDS,
    H1R31_GLOBAL_ROWS,
    H1R31_PACKET_COUNT,
    H1R31_PAYLOAD_BYTES_PER_ROW_LIMIT,
    H1R31_PEAK_LIMIT_BYTES,
    H1R31_SOURCE_LABEL,
    H1R31_TIMEOUT_SECONDS,
    _evaluate_h1r31_worker_qualification,
    _h1r3_path_metadata,
    _h1r31_file_metadata,
    _h1r31_scope,
    _parser,
    _watchdog_command,
    run_h1r31_check,
)
from src.test.test_281_task037_extra_h1r2_runner_contract import (
    _candidate_audit,
    _measurement,
)
from src.solvers.hcurl_canonical_vector import canonical_key


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_identity(sha: str) -> dict:
    return {
        "source_commit_full_sha": sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _runtime_identity() -> dict[str, str]:
    import sys

    return {
        "_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1",
        "sys.executable": sys.executable,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }


def _write_manifest(
    run_dir: Path, *, mpi_size: int, method: str, packet_count: int = 3
) -> tuple[str, dict]:
    source_dir = run_dir / "canonical" / H1R31_SOURCE_LABEL
    source_dir.mkdir(parents=True, exist_ok=True)
    packets = tuple(
        (
            canonical_key(
                role="full_fe_dual",
                entity_dimension=1,
                physical_entity=((index, 0, 0), (index + 1, 0, 0)),
                entity_local_basis_index=0,
                orientation_state=0,
            ),
            complex(index + 1.0, -0.25 * index),
        )
        for index in range(packet_count)
    )
    shard_path = source_dir / "candidate_rank0.jsonl"
    shard_metadata = write_canonical_packet_shard(shard_path, packets)
    manifest = canonical_shard_manifest(
        role="full_fe_dual",
        mpi_size=mpi_size,
        shard_metadata=(shard_metadata,),
        extractor_audit={
            "source": H1R31_SOURCE_LABEL,
            "method": method,
        },
    )
    manifest_path = source_dir / "candidate_manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    return manifest_sha, manifest


def _make_authority(tmp_path: Path, monkeypatch, source_definition: dict) -> Path:
    raw_dir = tmp_path / "historical_mpi1"
    raw_dir.mkdir()
    record_path = tmp_path / "historical_record.json"
    old_sha = "a" * 40
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_HISTORICAL_RAW_DIR",
        raw_dir,
    )
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_HISTORICAL_RECORD",
        record_path,
    )
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_HISTORICAL_SOURCE_SHA",
        old_sha,
    )
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_PACKET_COUNT", 3
    )
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_GLOBAL_ROWS", 100
    )
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_CONSTRAINT_COUNT", 97
    )
    manifest_sha, _manifest = _write_manifest(
        raw_dir, mpi_size=1, method="H1R2-direct-rank-one-MPC"
    )
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_HISTORICAL_MANIFEST_SHA256",
        manifest_sha,
    )
    source = _source_identity(old_sha)
    historical_worker = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r2.worker.v1",
            "status": "pass",
            "qualification": {"status": "pass", "pass": True},
            "source_at_start": source,
            "source_at_end": source,
            "measurements": [{"source_definition": source_definition}],
        }
    )
    _write_json(raw_dir / "run_summary.json", historical_worker)
    historical_watchdog = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r2.watchdog.v1",
            "status": "pass",
            "return_code": 0,
            "source_at_start": source,
            "source_at_end": source,
        }
    )
    _write_json(raw_dir / "watchdog_summary.json", historical_watchdog)
    historical_artifacts = {
        "run_summary.json": _h1r3_path_metadata(
            raw_dir / "run_summary.json", "run_summary.json"
        ),
        "watchdog_summary.json": _h1r3_path_metadata(
            raw_dir / "watchdog_summary.json", "watchdog_summary.json"
        ),
        "canonical/seed_17037/candidate_manifest.json": _h1r3_path_metadata(
            raw_dir / "canonical/seed_17037/candidate_manifest.json",
            "canonical/seed_17037/candidate_manifest.json",
        ),
    }
    compact = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r2.compact_check.v1",
            "status": "pass",
            "pass": True,
            "raw_run_directory": str(raw_dir),
            "source_identity": {
                "source_commit_full_sha": old_sha,
                "start": source,
                "end": source,
            },
            "raw_artifacts": historical_artifacts,
            "measurement": {"canonical_packet_count": 3},
        }
    )
    _write_json(record_path, compact)
    return raw_dir


def _make_current_run(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    run_dir = tmp_path / "current_mpi2"
    run_dir.mkdir()
    monkeypatch.setattr(
        "benchmarks.run_task037_extra_candidate_h.H1R31_PACKET_COUNT", 3
    )
    measurement = _measurement()
    source_definition = measurement["source_definition"]
    historical_dir = _make_authority(
        tmp_path, monkeypatch, source_definition
    )
    audit = _candidate_audit()
    audit.update(
        {
            "global_rows": 100,
            "constraint_count": 97,
            "retained_numeric_payload_global_sum_bytes": 2048,
            "retained_numeric_payload_global_max_bytes": 1024,
            "cell_schur_matrix_nnz": 0,
            "slab_matrix_nnz": 0,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
        }
    )
    current_sha = "b" * 40
    source = _source_identity(current_sha)
    scope = _h1r31_scope(global_rows=100, constraint_count=97)
    manifest_sha, _manifest = _write_manifest(
        run_dir, mpi_size=2, method="H1R3.1-direct-rank-one-MPC"
    )
    measurement.update(
        {
            "candidate_manifest": {
                "path": "canonical/seed_17037/candidate_manifest.json",
                "sha256": manifest_sha,
                "packet_count": 3,
            },
            "candidate_canonical_packet_count": 3,
            "canonical_export": True,
            "timing_reduction": "mpi_max",
        }
    )
    qualification = _evaluate_h1r31_worker_qualification(
        measurement, audit, scope=scope
    )
    assert qualification["pass"] is True
    worker = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.mpi2.worker.v1",
            "runtime_identity": _runtime_identity(),
            "status": "pass",
            "mpi_size": 2,
            "global_rows": 100,
            "constraint_count": 97,
            "scope": scope,
            "source_definitions": {H1R31_SOURCE_LABEL: source_definition},
            "measurements": [measurement],
            "candidate_action_audit": audit,
            "reference_action": {
                "type": "MpcFormActionContext",
                "same_worker": True,
                "apply_count": 1,
                "global_matrix_materialized": False,
            },
            "source_at_start": source,
            "source_at_end": source,
            "qualification": qualification,
        }
    )
    _write_json(run_dir / "run_summary.json", worker)
    (run_dir / "worker_stdout.txt").write_bytes(b"synthetic mpi2 worker\n")
    startup = {
        "worker_alive": True,
        "live_worker_process_count": 1,
        "worker_tree_rss_sum_bytes": 10,
        "process_tree_swap_bytes": 0,
        "process_tree_all_status_readable": True,
    }
    live = {
        "worker_alive": True,
        "live_worker_process_count": 3,
        "worker_tree_rss_sum_bytes": 100,
        "process_tree_swap_bytes": 0,
        "process_tree_all_status_readable": True,
    }
    final = {
        "worker_alive": False,
        "live_worker_process_count": 0,
        "worker_tree_rss_sum_bytes": 0,
        "process_tree_swap_bytes": 0,
        "process_tree_all_status_readable": True,
    }
    (run_dir / "watchdog_timeline.jsonl").write_text(
        json.dumps(startup, sort_keys=True)
        + "\n"
        + json.dumps(live, sort_keys=True)
        + "\n"
        + json.dumps(final, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(run_dir=run_dir)
    watchdog = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.mpi2.watchdog.v1",
            "command": _watchdog_command(args, mode="h1r3_mpi2"),
            "mpi_size": 2,
            "return_code": 0,
            "status": "pass",
            "controlled_stop": None,
            "timeout_seconds": H1R31_TIMEOUT_SECONDS,
            "poll_interval_seconds": 0.25,
            "rss_limit_bytes": H1R31_PEAK_LIMIT_BYTES,
            "termination": {"requested": False, "method": None},
            "wall_seconds": 1.0,
            "completion_elapsed_seconds": 1.0,
            "peak_process_tree_rss_bytes": 100,
            "peak_includes_only_worker_alive_samples": True,
            "worker_live_sample_count": 2,
            "worker_process_tree_swap_bytes": 0,
            "worker_swap_zero": True,
            "resource_authority_readable": True,
            "worker_process_tree_all_ranks": True,
            "final_sample": final,
            "worker_summary_present": True,
            "worker_summary_status": "pass",
            "worker_summary_evidence_sha256_valid": True,
            "worker_qualification_recomputed": qualification,
            "worker_qualification_pass": True,
            "watchdog_runtime_identity": _runtime_identity(),
            "worker_runtime_identity_match": True,
            "source_at_start": source,
            "source_at_end": source,
            "source_stable_clean": True,
            "reference_and_candidate_same_worker": True,
            "global_rows": 100,
            "constraint_count": 97,
            "raw_artifacts": _h1r31_file_metadata(
                run_dir, "canonical/seed_17037/candidate_manifest.json"
            ),
        }
    )
    _write_json(run_dir / "watchdog_summary.json", watchdog)
    return run_dir, historical_dir


def test_h1r31_parser_and_fixed_mpi2_command():
    parser = _parser()
    args = parser.parse_args(
        [
            "h1r3-mpi2-watchdog",
            "--run-dir",
            "relative/run",
        ]
    )
    command = _watchdog_command(args, mode="h1r3_mpi2")
    assert command[:3] == ["mpiexec", "-n", "2"]
    assert command[6:8] == ["h1r3-mpi2-worker", "--run-dir"]
    assert command[-1] == str(Path("relative/run").resolve())
    assert H1R31_TIMEOUT_SECONDS == 600.0
    assert H1R31_PEAK_LIMIT_BYTES == 805306368
    assert H1R31_CANDIDATE_SECOND_LIMIT_SECONDS == 2.390866201836616
    assert H1R31_PAYLOAD_BYTES_PER_ROW_LIMIT == 45
    assert H1R31_GLOBAL_ROWS == 173802
    assert H1R31_CONSTRAINT_COUNT == 9210
    assert H1R31_PACKET_COUNT == 164592
    for name in ("degree", "h_nm", "source", "repeat", "limit", "mpi_size"):
        assert not hasattr(args, name)
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["h1r3-mpi2-watchdog", "--run-dir", "run", "--mpi-size", "2"]
        )


def test_h1r31_checker_passes_with_distinct_historical_source_and_preserves_raw(
    tmp_path, monkeypatch
):
    run_dir, historical = _make_current_run(tmp_path, monkeypatch)
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    output = tmp_path / "compact.json"
    assert run_h1r31_check(run_dir, historical, output) == 0
    compact = json.loads(output.read_text(encoding="utf-8"))
    assert compact["pass"] is True
    assert compact["status"] == "pass"
    assert compact["source_identity"]["source_commit_full_sha"] == "b" * 40
    assert compact["historical_authority"]["source_commit_full_sha"] == "a" * 40
    assert compact["measurement"]["canonical_comparison"][
        "relative_coefficient_l2"
    ] <= H1R31_CANONICAL_TOLERANCE
    assert evidence_sha256_is_valid(compact)
    assert compact["checks"]["historical_path_argument"] is True
    assert compact["worker_qualification_recomputed"]["timing_checks"][
        "timing_reduction"
    ] is True
    assert all(
        compact["historical_authority"]["raw_artifact_checks"].values()
    )
    assert compact["historical_authority"][
        "embedded_evidence_sha256_valid"
    ] == {"worker_summary": True, "watchdog_summary": True}
    assert compact["measurement"]["retained_payload_global_sum_bytes"] == 2048
    assert compact["measurement"]["retained_payload_global_max_bytes"] == 1024
    assert compact["scope_boundary"]["H1R3.2"] == "eligible_by_review_v6"
    for path in run_dir.rglob("*"):
        if path.is_file():
            assert before[path.relative_to(run_dir)] == path.read_bytes()


@pytest.mark.parametrize(
    "mutation",
    (
        "numerical",
        "timing",
        "payload",
        "peak",
        "swap",
        "historical_raw_tamper",
        "canonical_missing",
        "canonical_relative",
        "canonical_duplicate",
        "audit_missing",
        "process_tree_count",
        "source_dirty",
    ),
)
def test_h1r31_checker_rejects_representative_raw_mutations(
    tmp_path, monkeypatch, mutation
):
    run_dir, historical = _make_current_run(tmp_path, monkeypatch)
    worker_path = run_dir / "run_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    watchdog_path = run_dir / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    if mutation == "numerical":
        worker["measurements"][0]["reference_vs_candidate_relative_error"] = 1.0e-3
    elif mutation == "timing":
        worker["measurements"][0]["candidate_repeat_apply_seconds"] = (
            H1R31_CANDIDATE_SECOND_LIMIT_SECONDS + 1.0
        )
    elif mutation == "payload":
        worker["candidate_action_audit"][
            "retained_numeric_payload_global_sum_bytes"
        ] = 45 * worker["global_rows"] + 1
    elif mutation == "audit_missing":
        del worker["candidate_action_audit"]["cell_schur_matrix_nnz"]
    elif mutation == "source_dirty":
        worker["source_at_end"]["source_worktree_dirty"] = True
    elif mutation == "peak":
        timeline_path = run_dir / "watchdog_timeline.jsonl"
        rows = [json.loads(line) for line in timeline_path.read_text().splitlines()]
        rows[0]["worker_tree_rss_sum_bytes"] = H1R31_PEAK_LIMIT_BYTES + 1
        timeline_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        watchdog["peak_process_tree_rss_bytes"] = H1R31_PEAK_LIMIT_BYTES + 1
    elif mutation == "swap":
        timeline_path = run_dir / "watchdog_timeline.jsonl"
        rows = [json.loads(line) for line in timeline_path.read_text().splitlines()]
        rows[0]["process_tree_swap_bytes"] = 1
        timeline_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    elif mutation == "process_tree_count":
        timeline_path = run_dir / "watchdog_timeline.jsonl"
        rows = [json.loads(line) for line in timeline_path.read_text().splitlines()]
        rows[1]["live_worker_process_count"] = 2
        timeline_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    elif mutation == "historical_raw_tamper":
        historical_worker_path = historical / "run_summary.json"
        historical_worker_path.write_bytes(
            historical_worker_path.read_bytes() + b"\n"
        )
    elif mutation == "canonical_missing":
        worker["measurements"][0]["candidate_manifest"]["path"] = (
            "canonical/seed_17037/missing.json"
        )
    elif mutation == "canonical_relative":
        shard_path = run_dir / "canonical/seed_17037/candidate_rank0.jsonl"
        rows = [json.loads(line) for line in shard_path.read_text().splitlines()]
        rows[0]["value"][0] += 1.0
        shard_path.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        shard_sha = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        manifest_path = run_dir / "canonical/seed_17037/candidate_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["per_rank_shards"][0]["file_sha256"] = shard_sha
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        worker["measurements"][0]["candidate_manifest"]["sha256"] = manifest_sha
    elif mutation == "canonical_duplicate":
        manifest_path = run_dir / "canonical/seed_17037/candidate_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["summed_local_duplicate_count"] = 1
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        worker["measurements"][0]["candidate_manifest"]["sha256"] = manifest_sha
    worker = attach_evidence_sha256(worker)
    _write_json(worker_path, worker)
    watchdog["raw_artifacts"] = _h1r31_file_metadata(
        run_dir, "canonical/seed_17037/candidate_manifest.json"
    )
    watchdog = attach_evidence_sha256(watchdog)
    _write_json(watchdog_path, watchdog)
    output = tmp_path / "compact.json"
    assert run_h1r31_check(run_dir, historical, output) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["pass"] is False
    assert result["problems"]
