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
from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
)
from benchmarks.run_task037_extra_candidate_h import (
    H1R2_SOURCE_LABEL,
    H1R2_TIMEOUT_SECONDS,
    H1_RSS_LIMIT_BYTES,
    _h1r2_file_metadata,
    _h1r2_scope_boundary,
    _h1r2_memory_authority,
    _parser,
    _watchdog_command,
    run_h1r2_check,
)
from src.solvers.hcurl_canonical_vector import canonical_key
from src.test.test_281_task037_extra_h1r2_runner_contract import (
    _candidate_audit,
    _measurement,
    _scope,
)


def _source_identity(sha: str = "a" * 40) -> dict:
    return {
        "source_commit_full_sha": sha,
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


def _make_run(tmp_path: Path) -> Path:
    from benchmarks.run_task037_extra_candidate_h import (
        _evaluate_h1r2_worker_qualification,
    )

    run_dir = tmp_path / "h1r2"
    run_dir.mkdir()
    scope = _scope()
    audit = _candidate_audit()
    measurement = _measurement()
    runtime_identity = {
        "_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1",
        "sys.executable": sys.executable,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    source_dir = run_dir / "canonical" / H1R2_SOURCE_LABEL
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
            complex(index + 1.0, -0.25 * index),
        )
        for index in range(3)
    )
    shard_path = source_dir / "candidate_rank0.jsonl"
    shard_metadata = write_canonical_packet_shard(shard_path, packets)
    manifest = canonical_shard_manifest(
        role="full_fe_dual",
        mpi_size=1,
        shard_metadata=(shard_metadata,),
        extractor_audit={
            "source": H1R2_SOURCE_LABEL,
            "method": "H1R2-direct-rank-one-MPC",
        },
    )
    manifest_path = source_dir / "candidate_manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    measurement["candidate_manifest"] = {
        "path": "canonical/seed_17037/candidate_manifest.json",
        "sha256": manifest_sha,
        "packet_count": 3,
    }
    qualification = _evaluate_h1r2_worker_qualification(
        [measurement], audit, scope=scope
    )
    worker = {
        "schema": "task037.candidate_h.h1r2.worker.v1",
        "runtime_identity": runtime_identity,
        "status": "pass",
        "mpi_size": 1,
        "global_rows": 4,
        "constraint_count": 1,
        "scope": scope,
        "source_definitions": {
            H1R2_SOURCE_LABEL: measurement["source_definition"]
        },
        "measurements": [measurement],
        "candidate_action_audit": audit,
        "reference_action": {
            "type": "MpcFormActionContext",
            "same_worker": True,
            "apply_count": 1,
            "global_matrix_materialized": False,
        },
        "retained_numeric_payload_components": audit[
            "retained_numeric_payload_components"
        ],
        "qualification": qualification,
    }
    worker = attach_evidence_sha256(worker)
    _write_json(run_dir / "run_summary.json", worker)
    (run_dir / "worker_stdout.txt").write_bytes(b"synthetic worker\n")
    live_sample = {
        "worker_alive": True,
        "worker_tree_rss_sum_bytes": 100,
        "process_tree_swap_bytes": 0,
        "process_tree_all_status_readable": True,
    }
    final_sample = {
        "worker_alive": False,
        "worker_tree_rss_sum_bytes": 0,
        "process_tree_swap_bytes": 0,
        "process_tree_all_status_readable": True,
    }
    (run_dir / "watchdog_timeline.jsonl").write_text(
        json.dumps(live_sample, sort_keys=True)
        + "\n"
        + json.dumps(final_sample, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(run_dir=run_dir)
    watchdog = {
        "schema": "task037.candidate_h.h1r2.watchdog.v1",
        "command": _watchdog_command(args, mode="h1r2"),
        "mpi_size": 1,
        "return_code": 0,
        "status": "pass",
        "controlled_stop": None,
        "timeout_seconds": H1R2_TIMEOUT_SECONDS,
        "poll_interval_seconds": 0.25,
        "rss_limit_bytes": H1_RSS_LIMIT_BYTES,
        "termination": {"requested": False, "method": None},
        "wall_seconds": 0.5,
        "completion_elapsed_seconds": 0.5,
        "peak_process_tree_rss_bytes": 100,
        "peak_includes_only_worker_alive_samples": True,
        "worker_live_sample_count": 1,
        "worker_process_tree_swap_bytes": 0,
        "worker_swap_zero": True,
        "resource_authority_readable": True,
        "final_sample": final_sample,
        "worker_summary_present": True,
        "worker_summary_status": "pass",
        "worker_summary_evidence_sha256_valid": True,
        "worker_qualification_recomputed": qualification,
        "worker_qualification_pass": True,
        "watchdog_runtime_identity": runtime_identity,
        "worker_runtime_identity_match": True,
        "source_at_start": _source_identity(),
        "source_at_end": _source_identity(),
        "source_stable_clean": True,
        "reference_and_candidate_same_worker": True,
        "raw_artifacts": _h1r2_file_metadata(run_dir),
    }
    _write_json(run_dir / "watchdog_summary.json", attach_evidence_sha256(watchdog))
    return run_dir


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite_watchdog(run_dir: Path, mutate) -> None:
    path = run_dir / "watchdog_summary.json"
    watchdog = _load(path)
    mutate(watchdog)
    _write_json(path, attach_evidence_sha256(watchdog))


def test_h1r2_fixed_parser_and_command_contract():
    parser = _parser()
    watchdog_args = parser.parse_args(["h1r2-watchdog", "--run-dir", "run"])
    assert watchdog_args.command == "h1r2-watchdog"
    assert not hasattr(watchdog_args, "mpi_size")
    command = _watchdog_command(watchdog_args, mode="h1r2")
    assert command[:3] == ["mpiexec", "-n", "1"]
    assert command[6:8] == ["h1r2-worker", "--run-dir"]
    assert command[-1] == str(Path("run").resolve())
    check_args = parser.parse_args(
        ["h1r2-check", "--run-dir", "run", "--output", "compact.json"]
    )
    assert check_args.output.name == "compact.json"
    with pytest.raises(SystemExit):
        parser.parse_args(["h1r2-watchdog", "--run-dir", "run", "--timeout", "1"])


def test_h1r2_checker_recomputes_good_raw_and_binds_compact_evidence(tmp_path):
    run_dir = _make_run(tmp_path)
    output = tmp_path / "compact.json"
    assert run_h1r2_check(run_dir, output) == 0
    compact = _load(output)
    assert compact["pass"] is True
    assert compact["status"] == "pass"
    assert evidence_sha256_is_valid(compact)
    assert compact["memory_authority"] == _h1r2_memory_authority(100)
    assert compact["scope_boundary"] == _h1r2_scope_boundary()
    assert compact["memory_authority"]["review_v4_peak_gate_pass"] is True
    assert compact["memory_authority"]["user_lt_2GB_target_evaluated"] is True
    assert compact["memory_authority"]["user_lt_2GB_target_pass"] is True
    runtime = compact["runtime_identity"]
    assert runtime["match"] is True
    for identity in (runtime["watchdog"], runtime["worker"]):
        assert identity["_MYFENICS_WSL_QUALIFIED_ACTIVATION"] == "1"
        assert identity["sys.executable"] == _load(
            run_dir / "watchdog_summary.json"
        )["command"][3]
        assert identity["OMP_NUM_THREADS"] == "1"
        assert identity["OPENBLAS_NUM_THREADS"] == "1"
        assert identity["MKL_NUM_THREADS"] == "1"
        assert identity["NUMEXPR_NUM_THREADS"] == "1"
    assert compact["source_identity"]["source_commit_full_sha"] == "a" * 40
    for relative_path in (
        "worker_stdout.txt",
        "watchdog_timeline.jsonl",
        "run_summary.json",
        "watchdog_summary.json",
        "canonical/seed_17037/candidate_manifest.json",
    ):
        actual_sha = hashlib.sha256(
            (run_dir / relative_path).read_bytes()
        ).hexdigest()
        assert compact["raw_artifacts"][relative_path]["sha256"] == actual_sha
    assert compact["raw_evidence_sha256"]["worker_summary_bytes"] == hashlib.sha256(
        (run_dir / "run_summary.json").read_bytes()
    ).hexdigest()
    assert compact["raw_evidence_sha256"]["watchdog_summary_bytes"] == hashlib.sha256(
        (run_dir / "watchdog_summary.json").read_bytes()
    ).hexdigest()
    assert compact["raw_evidence_sha256"]["canonical_manifest_bytes"] == hashlib.sha256(
        (run_dir / "canonical/seed_17037/candidate_manifest.json").read_bytes()
    ).hexdigest()
    assert compact["embedded_evidence_sha256"]["worker_summary"] == _load(
        run_dir / "run_summary.json"
    )["evidence_sha256"]
    assert compact["embedded_evidence_sha256"]["watchdog_summary"] == _load(
        run_dir / "watchdog_summary.json"
    )["evidence_sha256"]
    assert compact["measurement"]["global_rows"] == 4
    assert compact["measurement"]["constraint_count"] == 1
    assert compact["measurement"]["canonical_packet_count"] == 3
    assert compact["raw_artifacts"]["run_summary.json"]["present"] is True


def test_h1r2_wall_is_diagnostic_when_completion_is_within_gate(tmp_path):
    run_dir = _make_run(tmp_path)
    _rewrite_watchdog(
        run_dir,
        lambda raw: raw.update(
            {"wall_seconds": 601.0, "completion_elapsed_seconds": 0.5}
        ),
    )
    output = tmp_path / "compact.json"
    assert run_h1r2_check(run_dir, output) == 0
    compact = _load(output)
    assert compact["watchdog_checks"]["wall_seconds"] is True
    assert compact["watchdog_checks"]["completion_elapsed_seconds"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "wall",
        "peak",
        "swap",
        "source",
        "worker_evidence",
        "runtime",
        "timeline_hash",
        "embedded_pass",
        "status_closure",
    ),
)
def test_h1r2_checker_rejects_representative_raw_mutations(tmp_path, mutation):
    run_dir = _make_run(tmp_path)
    if mutation == "wall":
        _rewrite_watchdog(
            run_dir,
            lambda raw: raw.update(
                {"wall_seconds": 601.0, "completion_elapsed_seconds": 601.0}
            ),
        )
    elif mutation == "peak":
        timeline_path = run_dir / "watchdog_timeline.jsonl"
        rows = [json.loads(line) for line in timeline_path.read_text().splitlines()]
        rows[0]["worker_tree_rss_sum_bytes"] = H1_RSS_LIMIT_BYTES + 1
        timeline_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        _rewrite_watchdog(
            run_dir,
            lambda raw: raw.update(
                {
                    "peak_process_tree_rss_bytes": H1_RSS_LIMIT_BYTES + 1,
                    "raw_artifacts": _h1r2_file_metadata(run_dir),
                }
            ),
        )
    elif mutation == "swap":
        timeline_path = run_dir / "watchdog_timeline.jsonl"
        rows = [json.loads(line) for line in timeline_path.read_text().splitlines()]
        rows[0]["process_tree_swap_bytes"] = 1
        timeline_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        _rewrite_watchdog(
            run_dir,
            lambda raw: raw.update({"raw_artifacts": _h1r2_file_metadata(run_dir)}),
        )
    elif mutation == "source":
        _rewrite_watchdog(
            run_dir,
            lambda raw: raw["source_at_end"].update(
                {"source_commit_full_sha": "b" * 40}
            ),
        )
    elif mutation == "worker_evidence":
        worker_path = run_dir / "run_summary.json"
        worker = _load(worker_path)
        worker["evidence_sha256"] = "0" * 64
        _write_json(worker_path, worker)
    elif mutation == "runtime":
        worker_path = run_dir / "run_summary.json"
        worker = _load(worker_path)
        worker["runtime_identity"]["OMP_NUM_THREADS"] = "2"
        worker = attach_evidence_sha256(worker)
        _write_json(worker_path, worker)
        _rewrite_watchdog(
            run_dir,
            lambda raw: raw.update(
                {"raw_artifacts": _h1r2_file_metadata(run_dir)}
            ),
        )
    elif mutation == "timeline_hash":
        timeline_path = run_dir / "watchdog_timeline.jsonl"
        with timeline_path.open("a", encoding="utf-8") as stream:
            stream.write("{}\n")
        _rewrite_watchdog(run_dir, lambda raw: raw.update({"status": "pass"}))
    else:
        if mutation == "status_closure":
            worker_path = run_dir / "run_summary.json"
            worker = _load(worker_path)
            worker["status"] = "gate_failed"
            worker = attach_evidence_sha256(worker)
            _write_json(worker_path, worker)
            _rewrite_watchdog(
                run_dir,
                lambda raw: raw.update(
                    {
                        "worker_summary_status": "gate_failed",
                        "worker_qualification_pass": False,
                        "raw_artifacts": _h1r2_file_metadata(run_dir),
                    }
                ),
            )
        else:
            worker_path = run_dir / "run_summary.json"
            worker = _load(worker_path)
            worker["status"] = "pass"
            worker["qualification"]["pass"] = True
            worker["measurements"][0]["reference_vs_candidate_relative_error"] = 1.0e-3
            worker = attach_evidence_sha256(worker)
            _write_json(worker_path, worker)
            _rewrite_watchdog(
                run_dir,
                lambda raw: raw.update(
                    {
                        "raw_artifacts": _h1r2_file_metadata(run_dir),
                        "worker_summary_evidence_sha256_valid": True,
                    }
                ),
            )
    output = tmp_path / "compact.json"
    assert run_h1r2_check(run_dir, output) == 1
    compact = _load(output)
    assert compact["pass"] is False
    assert evidence_sha256_is_valid(compact)
