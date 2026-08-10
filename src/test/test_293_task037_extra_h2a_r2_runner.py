"""Focused synthetic contracts for the H2A-R2 B2 runner/checker."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task037_extra_h2 as runner
from src.solvers.hcurl_r2_constrained_local_block import (
    build_h2a_r2_cell_expansion,
)
from src.solvers.hcurl_r2_factor_store import (
    H2AR2CellReference,
    H2AR2ClassInput,
    build_h2a_r2_factor_store,
    load_h2a_r2_factor_store,
    write_h2a_r2_factor_store,
)


def _clean_source() -> dict[str, object]:
    return {
        "source_commit_full_sha": "c" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _fake_authorities(monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    runtime = {
        "qualified_activation": "1",
        "sys_executable": str(runner.ROOT / ".venv/bin/python"),
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
    }
    forms = [{"role": "curl"}, {"role": "mass"}]
    cache_inventory = [{"path": "synthetic.cache", "bytes": 1, "sha256": "a" * 64}]
    monkeypatch.setattr(runner, "R2_FIXED_NLOC", 2)
    inventory = []
    for class_id in range(24):
        inventory.append(
            {
                "class_id": class_id,
                "class_key_sha256": f"{class_id + 1:064x}",
                "constraint_pattern_sha256": f"{class_id + 101:064x}",
                "cell_count": 11 if class_id < 12 else 10,
                "local_nloc": 2,
                "constrained_unique_reduced_row_count": 2,
                "constraint_pattern_kinds": (
                    ["edge:corner"]
                    if class_id == 0
                    else ["edge:x"]
                    if class_id == 1
                    else []
                ),
            }
        )
    r0 = {
        "record_sha256": runner.R1_R0_RECORD_SHA256,
        "evidence_sha256": "d" * 64,
        "source_commit_full_sha": runner.R1_R0_SOURCE_SHA,
        "inventory_digest": runner._r0_digest(tuple(inventory)),
        "class_inventory": inventory,
        "identity": runner._r0_identity(),
        "global_cells": runner.R2_FIXED_CELL_COUNT,
        "local_nloc": 2,
        "global_rows": runner.R2_FIXED_GLOBAL_ROWS,
        "constraint_count": runner.R2_FIXED_CONSTRAINT_COUNT,
    }
    r1 = {
        "record_sha256": runner.R2_R1_RECORD_SHA256,
        "evidence_sha256": runner.R2_R1_EVIDENCE_SHA256,
        "source_commit_full_sha": runner.R2_R1_SOURCE_SHA,
        "raw_dir": str(runner.R2_R1_RAW_DIR),
        "runtime_identity": runtime,
        "stage_forms": forms,
        "hit_forms": forms,
        "cache_inventory": cache_inventory,
        "raw_artifacts": {},
        "watchdog_evidence_sha256": "w" * 64,
    }
    monkeypatch.setattr(runner, "_r2_read_r0_authority", lambda: r0)
    monkeypatch.setattr(runner, "_r2_read_r1_authority", lambda: r1)
    return r0, r1


def _write_synthetic_r1_canonical(path: Path, authority: dict) -> dict:
    record = runner.attach_evidence_sha256(
        {
            "schema": runner.R1_CHECK_SCHEMA,
            "status": "pass",
            "pass": True,
            "problems": [],
            "measurements": {
                "source_commit_full_sha": authority["source_commit_full_sha"],
                "runtime_identity": authority["runtime_identity"],
                "stage": {
                    "forms": authority["stage_forms"],
                    "cache_inventory": authority["cache_inventory"],
                },
                "hit": {"forms": authority["hit_forms"]},
            },
            "raw_artifacts": authority["raw_artifacts"],
        }
    )
    runner._write_json(path, record)
    return record


def _synthetic_r1_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict:
    source = "s" * 40
    runtime = {"synthetic": True}
    forms = [{"role": "curl"}, {"role": "mass"}]
    cache_inventory = [{"path": "synthetic.cache", "bytes": 1, "sha256": "a" * 64}]
    path = tmp_path / "r1" / "h2a_staged_factor_cache.json"
    record = runner.attach_evidence_sha256(
        {
            "schema": runner.R1_CHECK_SCHEMA,
            "status": "pass",
            "pass": True,
            "problems": [],
            "measurements": {
                "source_commit_full_sha": source,
                "runtime_identity": runtime,
                "stage": {"forms": forms, "cache_inventory": cache_inventory},
                "hit": {"forms": forms},
            },
            "raw_artifacts": {},
        }
    )
    runner._write_json(path, record)
    monkeypatch.setattr(runner, "R2_R1_RECORD_PATH", path)
    monkeypatch.setattr(runner, "R2_R1_RECORD_SHA256", runner._sha256_file(path))
    monkeypatch.setattr(runner, "R2_R1_EVIDENCE_SHA256", record["evidence_sha256"])
    monkeypatch.setattr(runner, "R2_R1_SOURCE_SHA", source)
    monkeypatch.setattr(runner, "R2_R1_RAW_DIR", tmp_path / "r1-raw")
    monkeypatch.setattr(runner, "R2_R1_JIT_CACHE_DIR", tmp_path / "r1-cache")
    monkeypatch.setattr(
        runner, "_r2_validate_r1_authority", lambda authority: dict(authority)
    )
    return record


def _synthetic_r2_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict:
    _synthetic_r1_setup(tmp_path, monkeypatch)
    authority = runner._r2_read_r1_authority()
    snapshot = runner._r2_make_r1_authority_snapshot(authority)
    record = runner.attach_evidence_sha256(
        {
            "schema": runner.R2_CHECK_SCHEMA,
            "status": "pass",
            "pass": True,
            "problems": [],
            "r1_authority_snapshot": snapshot,
        }
    )
    path = tmp_path / "r2" / "h2a_staged_factor_cache.json"
    runner._write_json(path, record)
    monkeypatch.setattr(runner, "R2_R1_RECORD_PATH", path)
    return record


def _write_progress(path: Path) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for event in runner.R2_PROGRESS_PREFIX:
            runner._r2_emit_marker(stream, event=event, started=0.0)
        for class_id in range(24):
            runner._r2_emit_marker(
                stream, event="factor_started", started=0.0, class_id=class_id
            )
            runner._r2_emit_marker(
                stream, event="factor_ready", started=0.0, class_id=class_id
            )
        for event in runner.R2_PROGRESS_SUFFIX:
            runner._r2_emit_marker(stream, event=event, started=0.0)


def _build_raw_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authorities: tuple[dict, dict] | None = None,
) -> Path:
    if authorities is None:
        r0, r1 = _fake_authorities(monkeypatch)
    else:
        r0, r1 = authorities
    run_dir = tmp_path / "r2"
    run_dir.mkdir()
    class_map = r0["class_inventory"]
    class_local = np.asarray([0, 1], dtype=np.int64)

    class IndexMap:
        def local_to_global(self, rows):
            return np.asarray(rows, dtype=np.int64) + 1000

    expansion = build_h2a_r2_cell_expansion(
        (),
        class_local,
        IndexMap(),
        index_map_bs=1,
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    source = _clean_source()
    runtime = r1["runtime_identity"]
    forms = r1["hit_forms"]
    cell_refs = tuple(
        H2AR2CellReference(
            index % 24,
            np.asarray([1000 + 2 * index, 1001 + 2 * index], dtype=np.int64),
        )
        for index in range(252)
    )

    def inputs():
        for item in class_map:
            yield H2AR2ClassInput(
                class_id=item["class_id"],
                class_key_sha256=item["class_key_sha256"],
                constraint_pattern_sha256=item["constraint_pattern_sha256"],
                expansion_pattern_sha256=expansion.pattern_sha256,
                expansion=expansion,
                transformed_matrix=np.asarray(
                    [[3.0 + 0.0j, 1.0j], [0.5 + 0.0j, 2.5 + 0.0j]],
                    dtype=np.complex128,
                ),
            )

    store = build_h2a_r2_factor_store(
        inputs(),
        cell_refs,
        identity={
            "source_identity": source,
            "config_identity": {"degree": 6, "h_nm": 10.0, "mpi_size": 1},
            "form_identity": forms,
            "cache_identity": {
                "cache_dir": str(runner.R2_R1_JIT_CACHE_DIR.resolve()),
                "inventory": r1["cache_inventory"],
            },
        },
        task037_extra_h2a_r2=True,
    )
    manifest = write_h2a_r2_factor_store(
        store, run_dir / "factor_store", task037_extra_h2a_r2=True
    )
    loaded_audit = dict(
        load_h2a_r2_factor_store(manifest, task037_extra_h2a_r2=True).audit
    )
    _write_progress(run_dir / "r2_progress.jsonl")
    (run_dir / "r2_worker_stdout.txt").write_text("", encoding="utf-8")
    timeline = {
        "schema": runner.R2_PROGRESS_SCHEMA,
        "sample_kind": "worker",
        "elapsed_wall_seconds": 0.25,
        "root_pid": 31415,
        "pids": [31415],
        "process_count": 1,
        "rss_bytes": 1024,
        "swap_bytes": 0,
        "all_status_readable": True,
        "progress_event": "worker_summary_started",
        "compiler_descendant_pids": [],
    }
    (run_dir / "r2_watchdog_timeline.jsonl").write_text(
        json.dumps(timeline, sort_keys=True) + "\n"
        + json.dumps(
            {"schema": runner.R2_PROGRESS_SCHEMA, "sample_kind": "final", "return_code": 0},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    runner._write_json(
        run_dir / "r2_root_pid.json",
        {"schema": f"{runner.R2_SCHEMA}.root.v1", "root_pid": 31415},
    )
    inventory = copy.deepcopy(class_map)
    expansion_inventory = [
        {
            "class_id": item["class_id"],
            "expansion_pattern_sha256": expansion.pattern_sha256,
            "independent_count": 2,
            "nloc": 2,
            "cell_count": item["cell_count"],
        }
        for item in inventory
    ]
    worker = runner.attach_evidence_sha256(
        {
            "schema": runner.R2_WORKER_SCHEMA,
            "status": "measurement_complete",
            "scope": runner._r2_scope(),
            "identity": runner._r2_identity(),
            "phase_identity": {
                "form_jit_called": True,
                "tensor_tabulation_called": True,
                "factorization_called": True,
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
            },
            "source_at_start": source,
            "source_at_end": source,
            "runtime_identity": runtime,
            "measurement": {
                "global_cells": 252,
                "local_cells": 252,
                "local_nloc": 2,
                "global_rows": runner.R2_FIXED_GLOBAL_ROWS,
                "constraint_count": runner.R2_FIXED_CONSTRAINT_COUNT,
            },
            "forms": forms,
            "cache_before": r1["cache_inventory"],
            "cache_after": r1["cache_inventory"],
            "cache_unchanged": True,
            "compiler_descendant_pids": [],
            "class_inventory": inventory,
            "expansion_inventory": expansion_inventory,
            "cell_reference_count": 252,
            "representative_class_ids": {"interior": 2, "periodic": 1, "corner": 0},
            "action_relative_error_max": 0.0,
            "action_relative_errors": [0.0] * 24,
            "factor_manifest": "factor_store/manifest.json",
            "factor_manifest_sha256": runner._sha256_file(manifest),
            "factor_audit": dict(store.audit),
            "loaded_factor_audit": loaded_audit,
            "loaded_solve_deterministic": True,
            "error": None,
        }
    )
    runner._write_json(run_dir / "run_summary.json", worker)
    raw_names = (
        "r2_worker_stdout.txt",
        "r2_progress.jsonl",
        "r2_watchdog_timeline.jsonl",
        "r2_root_pid.json",
        "run_summary.json",
        "factor_store/manifest.json",
    )
    watchdog = runner.attach_evidence_sha256(
        {
            "schema": runner.R2_WATCHDOG_SCHEMA,
            "status": "pass",
            "run_dir": str(run_dir.resolve()),
            "command": runner._r2_worker_command(run_dir, runtime["sys_executable"]),
            "scope": runner._r2_scope(),
            "runtime_identity": runtime,
            "source_at_start": source,
            "source_at_end": source,
            "source_clean_and_stable": True,
            "return_code": 0,
            "termination": None,
            "completion_elapsed_seconds": 0.25,
            "live_sample_count": 1,
            "process_tree_peak_rss_bytes": 1024,
            "process_tree_swap_bytes": 0,
            "compiler_descendant_pids": [],
            "worker_summary_present": True,
            "worker_evidence_valid": True,
            "worker_runtime_identity_match": True,
            "raw_artifacts": {name: runner._r2_artifact(run_dir, name) for name in raw_names},
        }
    )
    runner._write_json(run_dir / "r2_watchdog_summary.json", watchdog)
    return run_dir


def _resign_worker(run_dir: Path, mutate) -> None:
    worker_path = run_dir / "run_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    mutate(worker)
    runner._write_json(worker_path, runner.attach_evidence_sha256(worker))
    watchdog_path = run_dir / "r2_watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    watchdog["raw_artifacts"]["run_summary.json"] = runner._r2_artifact(
        run_dir, "run_summary.json"
    )
    runner._write_json(watchdog_path, runner.attach_evidence_sha256(watchdog))


def test_r2_fixed_scope_and_parser() -> None:
    assert runner._r2_scope()["timeout_seconds"] == 7200.0
    assert runner._r2_scope()["rss_limit_bytes"] == 1_750_000_000
    assert runner._r2_scope()["identity"]["condensation"] is False
    args = runner._parser().parse_args(["r2-watchdog", "--run-dir", "run"])
    assert args.command == "r2-watchdog"
    assert runner._r2_worker_command(Path("run"), "/qualified/python")[3] == "r2-worker"
    with pytest.raises(SystemExit):
        runner._parser().parse_args(["r2-watchdog", "--run-dir", "run", "--timeout", "1"])


def test_r2_authority_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _synthetic_r1_setup(tmp_path, monkeypatch)
    initial = runner._r2_read_r1_authority()
    assert initial["record_sha256"] == runner.R2_R1_RECORD_SHA256
    assert initial["evidence_sha256"] == runner.R2_R1_EVIDENCE_SHA256
    snapshot = runner._r2_make_r1_authority_snapshot(initial)
    record = runner.attach_evidence_sha256(
        {
            "schema": runner.R2_CHECK_SCHEMA,
            "status": "pass",
            "pass": True,
            "problems": [],
            "r1_authority_snapshot": snapshot,
        }
    )
    path = tmp_path / "r2-state.json"
    runner._write_json(path, record)
    monkeypatch.setattr(runner, "R2_R1_RECORD_PATH", path)
    promoted = runner._r2_read_r1_authority()
    assert promoted["record_sha256"] == runner.R2_R1_RECORD_SHA256
    assert promoted["evidence_sha256"] == runner.R2_R1_EVIDENCE_SHA256


def test_r2_real_authorities_are_read_only() -> None:
    r0 = runner._r2_read_r0_authority()
    r1 = runner._r2_read_r1_authority()
    assert len(r0["class_inventory"]) == 24
    assert r0["global_rows"] == 173802
    assert r0["constraint_count"] == 9210
    assert r1["record_sha256"] == runner.R2_R1_RECORD_SHA256
    assert r1["evidence_sha256"] == runner.R2_R1_EVIDENCE_SHA256
    assert r1["source_commit_full_sha"] == runner.R2_R1_SOURCE_SHA
    assert set(r1["raw_artifacts"]) == {
        "stage_progress.jsonl",
        "stage_stdout.txt",
        "stage_summary.json",
        "stage_timeline.jsonl",
        "hit_progress.jsonl",
        "hit_stdout.txt",
        "hit_summary.json",
        "hit_timeline.jsonl",
        "r1_watchdog_summary.json",
    }
    assert r1["cache_inventory"]


def test_r2_snapshot_is_required_and_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _synthetic_r2_record(tmp_path, monkeypatch)
    cases = []
    missing = copy.deepcopy(original)
    missing.pop("r1_authority_snapshot")
    cases.append(missing)
    tampered = copy.deepcopy(original)
    snapshot = tampered["r1_authority_snapshot"]
    snapshot["r1_source_commit_full_sha"] = "f" * 40
    tampered["r1_authority_snapshot"] = runner.attach_evidence_sha256(snapshot)
    cases.append(tampered)
    for index, record in enumerate(cases):
        path = tmp_path / f"r2-{index}.json"
        runner._write_json(path, runner.attach_evidence_sha256(record))
        monkeypatch.setattr(runner, "R2_R1_RECORD_PATH", path)
        with pytest.raises(ValueError):
            runner._r2_read_r1_authority()


def test_r2_checker_synthetic_pass_and_gate_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _build_raw_fixture(tmp_path, monkeypatch)
    good = runner._r2_check_raw(run_dir)
    assert good["pass"] is True, good["problems"]
    assert good["measurements"]["factor"]["unique_factor_count"] == 1

    mutations = {
        "dedup": lambda worker: worker["factor_audit"].update(
            {"unique_factor_count": 0}
        ),
        "residual": lambda worker: worker["factor_audit"].update(
            {"factorization_residual_max": 1.0}
        ),
        "cache": lambda worker: worker.update({"cache_unchanged": False}),
        "identity": lambda worker: worker["identity"].update({"condensation": True}),
    }
    for name, mutate in mutations.items():
        case_dir = tmp_path / name
        case_dir.mkdir()
        for source in run_dir.rglob("*"):
            if source.is_file():
                target = case_dir / source.relative_to(run_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        _resign_worker(case_dir, mutate)
        result = runner._r2_check_raw(case_dir)
        assert result["pass"] is False, (name, result)

    worker = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    loaded = load_h2a_r2_factor_store(
        run_dir / "factor_store/manifest.json", task037_extra_h2a_r2=True
    )
    r0, r1 = _fake_authorities(monkeypatch)
    overloaded_audit = dict(loaded.audit)
    overloaded_audit["factor_plus_metadata_bytes"] = (
        runner.R2_FACTOR_PAYLOAD_LIMIT_BYTES + 1
    )
    overloaded = SimpleNamespace(
        audit=overloaded_audit,
        classes=loaded.classes,
        solve=loaded.solve,
    )
    qualification = runner._r2_worker_qualification(
        worker, r0, r1, overloaded
    )
    assert qualification["pass"] is False
    assert "factor_payload" in qualification["problems"]

    manifest_path = run_dir / "factor_store/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metadata"]["source_identity"]["source_commit_full_sha"] = "e" * 40
    runner._write_json(manifest_path, manifest)
    result = runner._r2_check_raw(run_dir)
    assert result["pass"] is False
    assert result["watchdog_checks"]["manifest_identity"] is False

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metadata"]["classes"][0]["class_key_sha256"] = "e" * 64
    runner._write_json(manifest_path, manifest)
    mutated_store = load_h2a_r2_factor_store(
        manifest_path, task037_extra_h2a_r2=True
    )
    qualification = runner._r2_worker_qualification(
        worker, r0, r1, mutated_store
    )
    assert qualification["checks"]["factor_class_authority"] is False


def test_r2_checker_is_idempotent_for_one_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    production_reader = runner._r2_read_r1_authority
    r0, r1 = _fake_authorities(monkeypatch)
    output = tmp_path / "canonical" / "h2a_staged_factor_cache.json"
    r1_record = _write_synthetic_r1_canonical(output, r1)
    monkeypatch.setattr(runner, "R2_R1_RECORD_PATH", output)
    monkeypatch.setattr(
        runner, "R2_R1_RECORD_SHA256", runner._sha256_file(output)
    )
    monkeypatch.setattr(
        runner, "R2_R1_EVIDENCE_SHA256", r1_record["evidence_sha256"]
    )
    monkeypatch.setattr(
        runner,
        "_r2_validate_r1_authority",
        lambda authority: dict(authority),
    )
    run_dir = _build_raw_fixture(tmp_path, monkeypatch, (r0, r1))
    monkeypatch.setattr(runner, "_r2_read_r1_authority", production_reader)
    snapshot_calls = []
    production_snapshot_reader = runner._r2_r1_authority_from_snapshot

    def snapshot_reader(snapshot):
        snapshot_calls.append(snapshot)
        return production_snapshot_reader(snapshot)

    monkeypatch.setattr(runner, "_r2_r1_authority_from_snapshot", snapshot_reader)
    args = SimpleNamespace(run_dir=str(run_dir), output=str(output))
    r1_sha = runner._sha256_file(output)
    assert runner._r2_run_check(args) == 0
    first = output.read_bytes()
    assert runner._sha256_file(output) != r1_sha
    assert snapshot_calls == []
    assert runner._r2_run_check(args) == 0
    assert output.read_bytes() == first
    assert len(snapshot_calls) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["r1_authority_snapshot"]["schema"] == runner.R2_R1_SNAPSHOT_SCHEMA


def test_r2_checker_rejects_missing_marker_and_peak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _build_raw_fixture(tmp_path, monkeypatch)
    progress = run_dir / "r2_progress.jsonl"
    lines = progress.read_text(encoding="utf-8").splitlines()
    progress.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    result = runner._r2_check_raw(run_dir)
    assert result["pass"] is False

    peak_dir = tmp_path / "peak"
    peak_dir.mkdir()
    for source in run_dir.rglob("*"):
        if source.is_file():
            target = peak_dir / source.relative_to(run_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    timeline_path = peak_dir / "r2_watchdog_timeline.jsonl"
    timeline = [json.loads(line) for line in timeline_path.read_text().splitlines()]
    timeline[0]["rss_bytes"] = runner.R2_RSS_LIMIT_BYTES
    timeline_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in timeline) + "\n",
        encoding="utf-8",
    )
    result = runner._r2_check_raw(peak_dir)
    assert result["pass"] is False
