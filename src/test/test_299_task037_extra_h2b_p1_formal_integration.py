from __future__ import annotations

import gc
import json
from pathlib import Path
import weakref

import numpy as np
import pytest

import benchmarks.run_task037_extra_h2b as runner
from src.solvers.hcurl_h2b_block_smoother import factorize_h2b_p0_patch
from src.solvers.hcurl_h2b_p1_factor_store import (
    H2B_P1_FACTOR_STORE_SCHEMA,
    H2BP1FactorLimitExceeded,
    H2BP1FactorStore,
    build_h2b_p1_factor_store,
    h2b_p1_live_set_audit,
    load_h2b_p1_factor_store,
    write_h2b_p1_factor_store,
)


def _factor() -> object:
    matrix = np.asarray(
        ((0.2 + 0.1j, 1.0 - 0.2j), (2.0 + 0.3j, 0.4 + 0.2j)),
        dtype=np.complex128,
        order="C",
    )
    return factorize_h2b_p0_patch(matrix, task037_extra_h2b=True)


def _neighborhoods() -> list[dict[str, object]]:
    return [
        {
            "neighborhood_id": 0,
            "key_sha256": "a" * 64,
            "representative_cell": 0,
            "cell_ordinals": [0, 1],
            "multiplicity": 2,
            "central_class_id": 0,
            "touching_cell_ordinals": [0],
            "touching_class_ids": [0],
            "touching_count": 1,
            "touching_class_count": 1,
            "numeric_accumulation_order": [0],
            "numeric_accumulation_order_sha256": runner.hashlib.sha256(
                b"[0]"
            ).hexdigest(),
            "factor_id": 0,
        }
    ]


def _store(tmp_path: Path) -> tuple[H2BP1FactorStore, object]:
    factor = _factor()
    neighborhoods = _neighborhoods()
    # The canonical JSON helper encodes [0] without spaces; use the production
    # SHA rather than duplicating its serialization in the fixture.
    neighborhoods[0]["numeric_accumulation_order_sha256"] = runner.hashlib.sha256(
        b"[0]"
    ).hexdigest()
    store = build_h2b_p1_factor_store(
        (factor,),
        neighborhoods,
        np.asarray([0, 0], dtype=np.int32),
        np.asarray([0, 2, 4], dtype=np.int64),
        np.asarray([10, 20, 30, 40], dtype=np.int64),
        identity={"source": "a" * 40, "scope": "synthetic"},
        task037_extra_h2b=True,
    )
    manifest = write_h2b_p1_factor_store(
        store, tmp_path / "factor_store", task037_extra_h2b=True
    )
    return load_h2b_p1_factor_store(manifest, task037_extra_h2b=True), factor


def _write_three_factor_store(tmp_path: Path) -> Path:
    factors = tuple(
        factorize_h2b_p0_patch(
            np.asarray([[2.0 + index + 0.1j]], dtype=np.complex128, order="C"),
            task037_extra_h2b=True,
        )
        for index in range(3)
    )
    neighborhoods = [
        {
            "neighborhood_id": index,
            "key_sha256": f"{index + 1:064x}",
            "representative_cell": index,
            "cell_ordinals": [index],
            "multiplicity": 1,
            "central_class_id": 0,
            "touching_cell_ordinals": [index],
            "touching_class_ids": [index],
            "touching_count": 1,
            "touching_class_count": 1,
            "numeric_accumulation_order": [index],
            "numeric_accumulation_order_sha256": runner.hashlib.sha256(
                f"[{index}]".encode()
            ).hexdigest(),
            "factor_id": index,
        }
        for index in range(3)
    ]
    store = build_h2b_p1_factor_store(
        factors,
        neighborhoods,
        np.asarray([0, 1, 2], dtype=np.int32),
        np.asarray([0, 2, 4, 6], dtype=np.int64),
        np.asarray([10, 20, 30, 40, 50, 60], dtype=np.int64),
        identity={"source": "a" * 40},
        task037_extra_h2b=True,
    )
    return write_h2b_p1_factor_store(
        store, tmp_path / "factor_store", task037_extra_h2b=True
    )


def test_p1_store_roundtrip_cell_mapping_and_solve(tmp_path):
    store, factor = _store(tmp_path)
    assert store.audit["schema"] == H2B_P1_FACTOR_STORE_SCHEMA
    assert store.audit["factor_plus_metadata_bytes"] == sum(
        store.audit["retained_payload_components"].values()
    )
    assert store.audit["materialization_identity"]["patch_matrices"] is False
    assert store.manifest is None
    assert store.audit["materialization_identity"]["per_cell_factor"] is False
    assert not store.cell_neighborhood_ids.flags.writeable
    assert not store.cell_independent_global_rows.flags.writeable
    assert np.array_equal(store.cell_rows(1), np.asarray([30, 40]))
    full = np.arange(50, dtype=np.float64).astype(np.complex128)
    assert np.array_equal(store.gather_cell(full, 1), full[[30, 40]])
    rhs = np.asarray([1.0 + 0.2j, 2.0 - 0.1j], dtype=np.complex128)
    assert np.allclose(store.solve_cell(1, rhs), factor.solve(rhs))
    with pytest.raises(ValueError):
        store.cell_neighborhood_ids[0] = 1
    with pytest.raises(ValueError):
        store.solve_cell(0, rhs.astype(np.complex64))


def test_p1_audit_jsonable_can_be_attached_and_roundtripped(tmp_path):
    store, _factor_value = _store(tmp_path)
    payload = runner._attach_evidence({"factor_store": store.audit_jsonable()})
    encoded = json.dumps(payload, allow_nan=False)
    assert json.loads(encoded) == payload
    assert json.loads(json.dumps(store.audit_jsonable(), allow_nan=False)) == (
        store.audit_jsonable()
    )


def test_p1_store_loader_rejects_hash_and_missing_field(tmp_path):
    store, _factor_value = _store(tmp_path)
    manifest_path = tmp_path / "factor_store" / "manifest.json"
    values_path = tmp_path / "factor_store" / "factor_0_values.npy"
    original_bytes = values_path.read_bytes()
    values_path.write_bytes(bytes([original_bytes[0] ^ 1]) + original_bytes[1:])
    with pytest.raises(ValueError):
        load_h2b_p1_factor_store(manifest_path, task037_extra_h2b=True)
    values_path.write_bytes(original_bytes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metadata"].pop("factors")
    manifest["evidence_sha256"] = runner.hashlib.sha256(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "evidence_sha256"},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        load_h2b_p1_factor_store(manifest_path, task037_extra_h2b=True)


def test_p1_live_set_has_separate_reconstruction_and_factor_stages():
    dense = 882 * 882 * 16
    live = h2b_p1_live_set_audit(
        reconstruction_stage={
            "mesh_action_runtime_bytes": 1,
            "r2_lu_bytes": 2,
            "reconstructed_cache_bytes": 3,
            "reconstruction_lower_workspace_bytes": dense,
            "reconstruction_upper_workspace_bytes": dense,
            "reconstruction_permuted_workspace_bytes": dense,
            "reconstruction_output_workspace_bytes": dense,
            "reconstruction_pivots_bytes": 4,
            "authority_copy_source_bytes": dense,
            "authority_copy_destination_bytes": dense,
            "metadata_work_bytes": 5,
            "runtime_reserve_bytes": 6,
        },
        factor_stage={
            "mesh_action_runtime_bytes": 7,
            "reconstructed_cache_bytes": 8,
            "accepted_factor_bytes": 9,
            "current_patch_matrix_bytes": dense,
            "current_lu_workspace_bytes": dense,
            "factorization_original_copy_bytes": dense,
            "factorization_first_lu_bytes": dense,
            "factorization_repeated_lu_bytes": dense,
            "factorization_lower_workspace_bytes": dense,
            "factorization_upper_workspace_bytes": dense,
            "factorization_reconstructed_workspace_bytes": dense,
            "factorization_pivots_workspace_bytes": 10,
            "factorization_condition_workspace_bytes": dense,
            "metadata_work_bytes": 11,
            "runtime_reserve_bytes": 12,
        },
        task037_extra_h2b=True,
    )
    assert set(live["stages"]) == {"reconstruction", "factor"}
    assert live["workspace_accounting"]["reconstruction_internal_dense_matrices"] == 4
    assert live["workspace_accounting"]["factor_reconstruction_internal_dense_matrices"] == 3
    assert live["r2_store_released_before_factor_stage"] is True


def _source(value: str) -> dict[str, object]:
    return {
        "source_commit_full_sha": value,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "cleanliness_semantics": "all tracked changes plus every nonignored untracked path",
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _write_progress(path: Path, phase: str, events: list[str], schema: str):
    neighborhood_id = 0
    rows = []
    for event in events:
        item = {"schema": schema, "phase": phase, "event": event}
        if phase == "p1" and event in {"neighborhood_started", "patch_ready", "factor_ready", "factor_dedup"}:
            item["neighborhood_id"] = neighborhood_id
            if event in {"factor_ready", "factor_dedup"}:
                neighborhood_id += 1
        if phase == "p1" and event == "factor_limit_controlled_stop":
            item.update(
                {
                    "reason": "unique_numeric_factor_limit",
                    "offending_neighborhood_id": 32,
                    "offending_key_sha256": "a" * 64,
                    "offending_matrix_sha256": "b" * 64,
                    "unique_factor_limit": 32,
                    "lower_bound_unique_factor_count": 33,
                }
            )
        rows.append(json.dumps(item) + "\n")
    path.write_text(
        "".join(rows),
        encoding="utf-8",
    )


def _p1_success_events() -> list[str]:
    prefix = list(runner.H2B_P1_EVENTS[: runner.H2B_P1_EVENTS.index("neighborhood_started")])
    suffix = ["store_write_ready", "builder_release", "loader_ready", "summary_ready"]
    return prefix + sum(
        [["neighborhood_started", "patch_ready", "factor_ready"] for _ in range(84)], []
    ) + suffix


def _p1_controlled_events() -> list[str]:
    prefix = list(runner.H2B_P1_EVENTS[: runner.H2B_P1_EVENTS.index("neighborhood_started")])
    return prefix + sum(
        [["neighborhood_started", "patch_ready", "factor_ready"] for _ in range(32)], []
    ) + ["factor_limit_controlled_stop", "summary_ready"]


def _write_timeline(path: Path, phase: str, root_pid: int):
    path.write_text(
        json.dumps(
            {
                "schema": runner.H2B_PROGRESS_SCHEMA,
                "phase": phase,
                "sample_kind": "worker",
                "elapsed_wall_seconds": 1.0,
                "root_pid": root_pid,
                "pids": [root_pid],
                "process_count": 1,
                "rss_bytes": 1,
                "swap_bytes": 0,
                "all_status_readable": True,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _good_raw(tmp_path: Path, monkeypatch):
    source = _source("a" * 40)
    form = {"code_state": "hit_no_new_decl_impl"}
    stage_form = {"code_state": "cold_decl_impl_generated"}
    producer = {
        "r0_source": "b" * 40,
        "r1_source": "c" * 40,
        "r2_producer_source_full_sha": "d" * 40,
        "r2_record_sha256": "e" * 64,
        "r2_record_evidence_sha256": "f" * 64,
        "r2_factor_manifest_sha256": "1" * 64,
    }
    authority = {
        "r0": {"class_inventory": [{} for _ in range(24)]},
        "r1": {},
        "r2_record_sha256": "e" * 64,
        "r2_evidence_sha256": "f" * 64,
        "factor_manifest_sha256": "1" * 64,
        "producer_authority": producer,
        "p0": {
            "record_sha256": runner.H2B_P1_PREFLIGHT_P0_RECORD_SHA256,
            "evidence_sha256": runner.H2B_P1_PREFLIGHT_P0_EVIDENCE_SHA256,
        },
    }
    store_identity = {
        "source_identity": source,
        "form_identity": form,
        "config_identity": {"degree": 6, "h_nm": 10.0, "mpi_size": 1},
        "cache_identity": {
            "cache_dir": str((tmp_path / "jit_cache").resolve()),
            "inventory": [],
        },
        "r0_authority": authority["r0"],
        "r1_authority": authority["r1"],
        "r2_authority": producer,
        "p0_authority": authority["p0"],
    }
    fake_store = type(
        "FakeStore",
        (),
        {
            "factors": tuple(
                type(
                    "FakeFactor",
                    (),
                    {
                        "matrix_sha256": f"{index + 1:064x}",
                        "factor_values_sha256": f"{index + 17:064x}",
                        "pivot_sha256": f"{index + 33:064x}",
                        "finite": True,
                        "deterministic": True,
                        "factorization_residual": 0.0,
                        "solve_residual": 0.0,
                    },
                )()
                for index in range(16)
            ),
            "neighborhoods": tuple(
                {
                    "key_sha256": f"{index + 1:064x}",
                    "central_class_id": index % 24,
                    "cell_ordinals": list(range(index * 3, index * 3 + 3)),
                }
                for index in range(84)
            ),
            "cell_neighborhood_ids": np.repeat(
                np.arange(84, dtype=np.int32), 3
            ),
            "identity": store_identity,
            "audit": {
                "neighborhood_count": 84,
                "cell_count": 252,
                "unique_factor_count": 16,
                "factor_plus_metadata_bytes": 201_933_812,
                "factor_plus_metadata_gate": True,
                "finite": True,
                "deterministic": True,
                "materialization_identity": {
                    "patch_matrices": False,
                    "per_cell_factor": False,
                    "class_expansion": False,
                    "global_matrix": False,
                    "global_constraint_matrix": False,
                    "slab_factor": False,
                    "schur": False,
                },
            },
            "audit_jsonable": lambda self: json.loads(json.dumps(self.audit)),
        },
    )()
    monkeypatch.setattr(runner, "_p1_authority", lambda: authority)
    monkeypatch.setattr(runner, "_source_pair_valid", lambda *_args: True)
    monkeypatch.setattr(runner, "_runtime_valid", lambda *_args: True)
    monkeypatch.setattr(runner, "_forms_match", lambda *_args: True)
    import src.solvers.hcurl_h2b_p1_factor_store as p1_module

    monkeypatch.setattr(p1_module, "load_h2b_p1_factor_store", lambda *_args, **_kwargs: fake_store)
    cache_dir = tmp_path / "jit_cache"
    cache_dir.mkdir()
    for name in runner.H2B_P1_ARTIFACT_NAMES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "factor_store" / "manifest.json"
    manifest.write_text(
        json.dumps({"evidence_sha256": "9" * 64}) + "\n", encoding="utf-8"
    )
    manifest_sha = runner._sha256_file(manifest)
    manifest_evidence = "9" * 64
    p6 = {
        "global_cells": 252,
        "local_cells": 252,
        "local_nloc": 882,
        "global_rows": 173802,
        "constraint_count": 9210,
    }
    sources = {
        label: {"finite": True, "exact_action_relative_error": 0.0}
        for label in runner.H2B_SOURCE_LABELS
    }
    measurement = {
        "p6": p6,
        "authority": authority,
        "cache": {
            "dir": str(cache_dir.resolve()),
            "before": [],
            "after": [],
            "unchanged": True,
        },
        "p0_anchor": {
            "schema": "task037.extra.h2b.p1.anchor.v1",
            "source_order": list(runner.H2B_SOURCE_LABELS),
            "sources": sources,
            "finite": True,
        },
        "neighborhood_digest": runner.hashlib.sha256(
            memoryview(
                np.ascontiguousarray(np.repeat(np.arange(84, dtype=np.int32), 3))
            ).cast("B")
        ).hexdigest(),
        "factor_store": fake_store.audit,
        "materialization_identity": fake_store.audit["materialization_identity"],
        "neighborhood_count": 84,
        "cell_count": 252,
        "unique_factor_count": 16,
        "retained_unique_factor_count": 16,
        "factor_store_manifest": {
            "sha256": manifest_sha,
            "evidence_sha256": manifest_evidence,
        },
        "preflight_live_set": runner._p1_preflight_live_set(),
        "preflight_basis": runner._p1_preflight_basis(),
    }
    stage = {
        "schema": runner.H2B_WORKER_SCHEMA,
        "phase": "stage",
        "status": "measurement_complete",
        "error": None,
        "scope": runner._fixed_scope(),
        "identity": runner._fixed_identity(),
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": {"sys_executable": "/tmp/.venv/bin/python"},
        "form": stage_form,
        "phase_identity": runner._phase_identity(
            jit_api=True, compile_called=True, compiler_probe=True
        ),
    }
    worker = {
        "schema": runner.H2B_P1_WORKER_SCHEMA,
        "phase": "p1",
        "status": "measurement_complete",
        "error": None,
        "scope": runner._p1_scope(),
        "identity": runner._fixed_identity(),
        "phase_identity": {
            **runner._phase_identity(
                jit_api=True, compile_called=False, compiler_probe=False
            ),
            "factorization_called": True,
        },
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": {"sys_executable": "/tmp/.venv/bin/python"},
        "form": form,
        "measurement": measurement,
        "preflight_live_set": runner._p1_preflight_live_set(),
        "preflight_basis": runner._p1_preflight_basis(),
    }
    runner._write_json(tmp_path / "stage_summary.json", runner._attach_evidence(stage))
    runner._write_json(tmp_path / "p1_summary.json", runner._attach_evidence(worker))
    _write_progress(tmp_path / "stage_progress.jsonl", "stage", runner.H2B_STAGE_EVENTS, runner.H2B_PROGRESS_SCHEMA)
    _write_progress(tmp_path / "p1_progress.jsonl", "p1", _p1_success_events(), runner.H2B_PROGRESS_SCHEMA)
    _write_timeline(tmp_path / "stage_timeline.jsonl", "stage", 1001)
    _write_timeline(tmp_path / "p1_timeline.jsonl", "p1", 1002)
    process = {"return_code": 0, "termination": None, "peak_rss_bytes": 1, "swap_bytes": 0}
    watchdog = {
        "schema": runner.H2B_P1_WATCHDOG_SCHEMA,
        "status": "pass",
        "scope": runner._p1_scope(),
        "identity": runner._fixed_identity(),
        "run_dir": str(tmp_path.resolve()),
        "command_identity": {
            "python": "/tmp/.venv/bin/python",
            "launch_mode": "direct_singleton",
            "stage_command": runner._worker_command(
                "/tmp/.venv/bin/python", "jit-worker", tmp_path
            ),
            "p1_command": runner._worker_command(
                "/tmp/.venv/bin/python", "p1-worker", tmp_path
            ),
        },
        "source_at_start": source,
        "source_at_end": source,
        "stage": {**process, "processes_gone_before_p1": True},
        "p1": {**process, "processes_gone_after_p1": True},
        "raw_artifacts": {name: runner._artifact(tmp_path, name) for name in runner.H2B_P1_ARTIFACT_NAMES},
    }
    runner._write_json(tmp_path / "p1_watchdog_summary.json", runner._attach_evidence(watchdog))
    return authority, worker


def _prepare_controlled_raw(tmp_path: Path, monkeypatch):
    _good_raw(tmp_path, monkeypatch)
    (tmp_path / "factor_store" / "manifest.json").unlink()
    _write_progress(
        tmp_path / "p1_progress.jsonl",
        "p1",
        _p1_controlled_events(),
        runner.H2B_PROGRESS_SCHEMA,
    )
    worker = json.loads((tmp_path / "p1_summary.json").read_text(encoding="utf-8"))
    worker["status"] = "gate_failed"
    worker["controlled_stop"] = {
        "reason": "unique_numeric_factor_limit",
        "offending_neighborhood_id": 32,
        "offending_key_sha256": "a" * 64,
        "offending_matrix_sha256": "b" * 64,
        "unique_factor_limit": 32,
        "lower_bound_unique_factor_count": 33,
    }
    worker["measurement"].update(
        {
            "processed_neighborhood_count": 32,
            "retained_unique_factor_count": 32,
            "controlled_stop": worker["controlled_stop"],
        }
    )
    runner._write_json(tmp_path / "p1_summary.json", runner._attach_evidence(worker))
    watchdog = json.loads(
        (tmp_path / "p1_watchdog_summary.json").read_text(encoding="utf-8")
    )
    watchdog["status"] = "gate_failed"
    watchdog["p1"]["return_code"] = 1
    watchdog["raw_artifacts"] = {
        name: runner._artifact(tmp_path, name) for name in runner.H2B_P1_ARTIFACT_NAMES
    }
    runner._write_json(
        tmp_path / "p1_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    return worker, watchdog


def test_p1_checker_recomputes_good_result_and_rejects_status_tamper(tmp_path, monkeypatch):
    _good_raw(tmp_path, monkeypatch)
    result = runner._p1_check_raw(tmp_path)
    assert result["pass"] is True
    assert all(result["checks"].values())
    worker = json.loads((tmp_path / "p1_summary.json").read_text(encoding="utf-8"))
    worker["measurement"]["p0_anchor"]["sources"]["mixed"][
        "exact_action_relative_error"
    ] = 2.0e-11
    runner._write_json(tmp_path / "p1_summary.json", runner._attach_evidence(worker))
    failed_anchor = runner._p1_check_raw(tmp_path)
    assert failed_anchor["pass"] is False
    assert "anchor" in failed_anchor["problems"]
    worker = json.loads((tmp_path / "p1_summary.json").read_text(encoding="utf-8"))
    worker["status"] = "gate_failed"
    runner._write_json(tmp_path / "p1_summary.json", runner._attach_evidence(worker))
    failed = runner._p1_check_raw(tmp_path)
    assert failed["pass"] is False
    assert "p1_worker" in failed["problems"]


def _anchor_gate_fixture():
    return {
        "schema": "task037.extra.h2b.p1.anchor.v1",
        "source_order": list(runner.H2B_SOURCE_LABELS),
        "finite": True,
        "sources": {
            label: {"finite": True, "exact_action_relative_error": 0.0}
            for label in runner.H2B_SOURCE_LABELS
        },
    }


@pytest.mark.parametrize("mutation", ["missing", "nan", "closure", "finite"])
def test_p1_anchor_gate_is_explicit_and_fail_closed(mutation):
    anchor = _anchor_gate_fixture()
    if mutation == "missing":
        del anchor["sources"]["mixed"]["exact_action_relative_error"]
    elif mutation == "nan":
        anchor["sources"]["mixed"]["exact_action_relative_error"] = float("nan")
    elif mutation == "closure":
        anchor["sources"]["mixed"]["exact_action_relative_error"] = 2.0e-11
    else:
        anchor["sources"]["mixed"]["finite"] = False
    assert runner._p1_anchor_gate_valid(anchor) is False


def test_p1_anchor_failure_measurements_keep_json_safe_metrics():
    anchor = _anchor_gate_fixture()
    anchor["sources"]["mixed"]["finite"] = False
    failure = runner._p1_anchor_failure_measurements(
        anchor,
        {"global_cells": 252, "global_rows": 173802},
        {"matrix_sha256": "a" * 64, "matrix": np.zeros((1, 1))},
        {"matrix_sha256": "b" * 64, "solve_residual": 0.0},
        {"source": "c" * 40},
        None,
        None,
    )
    encoded = json.dumps(failure, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["p6"]["global_cells"] == 252
    assert "mixed" in decoded["p0_anchor"]["sources"]
    assert "matrix" not in decoded["patch"]


@pytest.mark.parametrize("mutation", ["factor_store", "neighborhood_digest"])
def test_p1_checker_binds_measurement_to_fresh_store(
    tmp_path, monkeypatch, mutation
):
    _good_raw(tmp_path, monkeypatch)
    worker = json.loads((tmp_path / "p1_summary.json").read_text(encoding="utf-8"))
    if mutation == "factor_store":
        worker["measurement"]["factor_store"]["neighborhood_count"] = 83
    else:
        worker["measurement"]["neighborhood_digest"] = "0" * 64
    runner._write_json(tmp_path / "p1_summary.json", runner._attach_evidence(worker))
    watchdog = json.loads(
        (tmp_path / "p1_watchdog_summary.json").read_text(encoding="utf-8")
    )
    watchdog["raw_artifacts"] = {
        name: runner._artifact(tmp_path, name)
        for name in runner.H2B_P1_ARTIFACT_NAMES
    }
    runner._write_json(
        tmp_path / "p1_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    result = runner._p1_check_raw(tmp_path)
    assert result["pass"] is False
    assert result["checks"]["measurement_store_binding"] is False


@pytest.mark.parametrize(
    "controlled,missing",
    [(False, "stage_stdout.txt"), (True, "p1_stdout.txt")],
)
def test_p1_checker_requires_declared_artifacts(
    tmp_path, monkeypatch, controlled, missing
):
    if controlled:
        _prepare_controlled_raw(tmp_path, monkeypatch)
    else:
        _good_raw(tmp_path, monkeypatch)
    (tmp_path / missing).unlink()
    result = runner._p1_check_raw(tmp_path)
    assert result["pass"] is False
    assert result["checks"]["watchdog_evidence"] is False


def test_p1_checker_keeps_structured_33rd_factor_stop(tmp_path, monkeypatch):
    _prepare_controlled_raw(tmp_path, monkeypatch)
    result = runner._p1_check_raw(tmp_path)
    assert result["status"] == "gate_failed"
    assert result["problems"] == ["unique_numeric_factor_limit"]
    assert result["controlled_stop"]["lower_bound_unique_factor_count"] == 33


def test_p1_loader_streams_factor_pairs_without_double_payload(tmp_path, monkeypatch):
    _write_three_factor_store(tmp_path)
    import src.solvers.hcurl_h2b_p1_factor_store as p1_module

    original = p1_module._p1_load_array
    state = {"active": 0, "peak": 0}

    def tracked(root, files, relative):
        values = original(root, files, relative)
        if str(relative).startswith("factor_"):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            def release():
                state["active"] -= 1

            weakref.finalize(values, release)
        return values

    monkeypatch.setattr(p1_module, "_p1_load_array", tracked)
    load_h2b_p1_factor_store(
        tmp_path / "factor_store" / "manifest.json", task037_extra_h2b=True
    )
    gc.collect()
    assert state["peak"] == 2
    assert state["active"] == 0


def test_p1_store_json_owned_parts_are_immutable_after_build(tmp_path):
    factor = _factor()
    records = _neighborhoods()
    identity = {"nested": {"flag": True}, "source": "a" * 40}
    cell_ids = np.asarray([0, 0], dtype=np.int32)
    offsets = np.asarray([0, 2, 4], dtype=np.int64)
    rows = np.asarray([10, 20, 30, 40], dtype=np.int64)
    store = build_h2b_p1_factor_store(
        (factor,),
        records,
        cell_ids,
        offsets,
        rows,
        identity=identity,
        task037_extra_h2b=True,
    )
    records[0]["factor_id"] = 7
    identity["nested"]["flag"] = False
    cell_ids.setflags(write=True)
    offsets.setflags(write=True)
    rows.setflags(write=True)
    cell_ids[0] = 1
    offsets[1] = 1
    rows[0] = 999
    assert store.factor_id_for_cell(0) == 0
    assert store.identity["nested"]["flag"] is True
    assert np.array_equal(store.cell_neighborhood_ids, np.asarray([0, 0]))
    assert np.array_equal(store.cell_row_offsets, np.asarray([0, 2, 4]))
    assert np.array_equal(store.cell_independent_global_rows, np.asarray([10, 20, 30, 40]))
    with pytest.raises(TypeError):
        store.neighborhoods[0]["factor_id"] = 7
    with pytest.raises(TypeError):
        store.identity["nested"]["flag"] = False
    with pytest.raises(TypeError):
        store.audit["retained_payload_components"]["factor_values_bytes"] = 0


def test_p1_factor_limit_is_typed_and_plain_value_error_is_not_wrapped():
    from src.solvers.hcurl_h2b_p1_factor_store import H2BP1FactorLedger

    ledger = H2BP1FactorLedger(task037_extra_h2b=True)
    for index in range(32):
        ledger.accept(
            np.asarray([[2.0 + index]], dtype=np.complex128, order="C"),
            task037_extra_h2b=True,
        )
    with pytest.raises(H2BP1FactorLimitExceeded) as limit:
        ledger.accept(np.asarray([[99.0 + 0.0j]], dtype=np.complex128), task037_extra_h2b=True)
    assert limit.value.lower_bound == 33
    with pytest.raises(ValueError) as invalid:
        ledger.accept(np.asarray([[np.nan + 0.0j]], dtype=np.complex128), task037_extra_h2b=True)
    assert not isinstance(invalid.value, H2BP1FactorLimitExceeded)


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "stage",
        "swap",
        "offending_id",
        "offending_key",
        "preflight",
        "measurement",
    ],
)
def test_p1_controlled_stop_checker_rejects_tampered_gate(tmp_path, monkeypatch, mutation):
    worker, watchdog = _prepare_controlled_raw(tmp_path, monkeypatch)
    if mutation == "source":
        watchdog["source_at_start"] = _source("c" * 40)
    elif mutation == "stage":
        watchdog["stage"]["return_code"] = 1
    elif mutation == "swap":
        watchdog["p1"]["swap_bytes"] = 1
    elif mutation == "offending_id":
        worker["controlled_stop"]["offending_neighborhood_id"] = 84
    elif mutation == "offending_key":
        worker["controlled_stop"]["offending_key_sha256"] = "not-a-sha"
    elif mutation == "measurement":
        worker["measurement"]["authority"] = {}
    else:
        worker["preflight_basis"]["runtime_reserve_bytes"] = 1
    runner._write_json(tmp_path / "p1_summary.json", runner._attach_evidence(worker))
    watchdog["raw_artifacts"] = {
        name: runner._artifact(tmp_path, name) for name in runner.H2B_P1_ARTIFACT_NAMES
    }
    runner._write_json(
        tmp_path / "p1_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    result = runner._p1_check_raw(tmp_path)
    assert result["pass"] is False
    assert result["measurements"] is None
    assert "unique_numeric_factor_limit" in result["problems"]


def test_p1_parser_exposes_only_the_opt_in_commands():
    args = runner._parser().parse_args(["p1-check", "--run-dir", "raw", "--output", "out.json"])
    assert args.command == "p1-check"
    assert runner._worker_command("/tmp/.venv/bin/python", "p1-worker", Path("raw"))[3] == "p1-worker"
