from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
from src.test.test_338_task037_m6b_w16_global_shifted_inner import (
    _synthetic_summary,
)
from src.solvers.persistent_residual_one_vector import repeat_rank_one_projection


EXPECTED_SHA = "a" * 40


def _source_identity() -> dict:
    return {
        "source_commit_full_sha": EXPECTED_SHA,
        "source_worktree_dirty": False,
        "tracked_source_dirty": False,
    }


def _descriptor(path: Path, array: np.ndarray, *, checkpoint: bool) -> dict:
    array = np.ascontiguousarray(array, dtype=np.complex128)
    return {
        "path": path.name if checkpoint else str(path.resolve()),
        "bytes": int(path.stat().st_size),
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(array),
        "shape": list(array.shape),
        "dtype": "complex128",
    }


def _write_array(
    path: Path, *, checkpoint: bool, values: np.ndarray | None = None
) -> dict:
    if values is None:
        values = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128)
    else:
        values = np.asarray(values, dtype=np.complex128)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, values, allow_pickle=False)
    return _descriptor(path, values, checkpoint=checkpoint)


@pytest.fixture
def formal_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 2)
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda value: True)
    monkeypatch.setattr(runner, "_m6b_w6a_runtime_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(runner, "_m6b_expected_p6", lambda value: True)

    import benchmarks.run_task037_extra_h2b as h2b

    source = _source_identity()
    monkeypatch.setattr(h2b, "_light_source", lambda: dict(source))
    cache = {"entries": [], "inventory_sha256": runner.M6B_W2_JIT_INVENTORY_SHA256}
    monkeypatch.setattr(runner, "_m6b_w2_cache_record", lambda _h2b, _path: deepcopy(cache))

    factor = {
        "path": str(tmp_path / "factor_store" / "manifest.json"),
        "present": True,
        "bytes": 12,
        "sha256": "b" * 64,
        "source_commit_full_sha": "d98254fecddc41940f50f72753ec9f0f80407793",
        "beta": 1.0,
        "audit": {
            "cell_count": 252,
            "factor_count": 84,
            "factor_order": 882,
            "retained_total_bytes": 1,
        },
        "builder_summary": {
            "path": "m6b_builder_summary.json",
            "present": True,
            "bytes": 12,
            "sha256": "c" * 64,
        },
        "builder_evidence_sha256": "e" * 64,
        "factor_compiler": {"version_line": "fixture", "probe_command": "fixture"},
    }
    monkeypatch.setattr(runner, "_m6b_w16a_factor_authority", lambda _path: deepcopy(factor))
    w7_residual = np.asarray(
        [1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128
    )
    w7 = {
        "compact": {
            "path": str(tmp_path / "w7.json"),
            "file_sha256": "f" * 64,
            "producer_source_sha": runner.M6B_W8A_W7_SOURCE_SHA,
        },
        "raw_dir": str(tmp_path / "w7_raw"),
        "residual_artifact": {
            "path": "m6b_iter400_residual.npy",
            "bytes": int(w7_residual.nbytes),
            "file_sha256": "1" * 64,
            "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(
                w7_residual
            ),
        },
    }
    monkeypatch.setattr(
        runner,
        "_m6b_w9a_load_w7",
        lambda *_paths: {
            **deepcopy(w7),
            "residual": np.array(w7_residual, copy=True),
        },
    )

    raw_dir = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw_dir.mkdir()
    watchdog_dir.mkdir()
    checkpoint_residual = 1.0e-3 * w7_residual
    checkpoint_outer_action = w7_residual - checkpoint_residual
    checkpoint_solution = np.asarray(
        [0.25 - 0.5j, -0.75 + 0.125j], dtype=np.complex128
    )
    physical_image = np.array(w7_residual, copy=True)
    summary = _synthetic_summary()
    summary["inner_audits"] = deepcopy(summary["inner_audits"])
    for index, audit in enumerate(summary["inner_audits"], start=1):
        v_path = raw_dir / "scratch" / f"run{index}" / "v_basis.bin"
        z_path = raw_dir / "scratch" / f"run{index}" / "z_basis.bin"
        v_path.parent.mkdir(parents=True, exist_ok=True)
        v_path.write_bytes(b"\0")
        with v_path.open("ab") as stream:
            stream.truncate(audit["v_basis"]["allocated_bytes"])
        z_path.write_bytes(b"\0")
        with z_path.open("ab") as stream:
            stream.truncate(audit["z_basis"]["allocated_bytes"])
        audit["scratch_paths"] = {
            "v_basis": str(v_path.resolve()),
            "z_basis": str(z_path.resolve()),
        }

    action = summary["action_audit"]
    action.update(
        {
            "retained_authority_vector_roles": ["w7_target_residual"],
            "lifecycle_events": [
                "auxiliary_constructed",
                "inner_apply_1",
                "inner_apply_2",
                "auxiliary_released",
                "physical_constructed",
                "physical_apply_1",
                "physical_apply_2",
                "physical_released",
            ],
            "auxiliary_construction": {
                "shifted_action": {"apply_count": 0},
                "local_pc": {"schema": "fixture"},
            },
            "auxiliary_final_counts": {
                "global_shifted_action_count": 42,
                "local_pc_apply_count": 40,
                "local_exact_shifted_volume_action_count": 40,
                "shifted_action_total_count": 82,
                "shifted_action_audit": {"apply_count": 82},
            },
            "physical_instances": [
                {
                    "physical": {
                        "apply_count": 2,
                        "global_matrix_materialized": False,
                        "global_constraint_matrix_materialized": False,
                        "global_condensed_schur_materialized": False,
                        "cell_schur_matrix_materialized": False,
                        "slab_matrix_materialized": False,
                        "retained_dense_cell_tensor_count": 0,
                        "dense_cell_tensor_materialized_per_apply": False,
                        "factor_count": 0,
                        "ksp_created": False,
                        "cell_schur_matrix_nnz": 0,
                        "slab_matrix_nnz": 0,
                        "explicit_C_materialized_count": 0,
                        "explicit_D_materialized_count": 0,
                        "ordinary_default_changed": False,
                    },
                    "outer": {
                        "apply_count": 2,
                        "matrix_type": "python_action_only",
                        "global_matrix": False,
                        "augmented_matrix": False,
                        "static_condensation": False,
                        "trace_slab": False,
                        "explicit_C_materialized_count": 0,
                        "explicit_D_materialized_count": 0,
                    },
                    "dtn": {
                        "apply_count": 2,
                        "mode_count": 80,
                        "fine_space": "uncondensed_fullspace",
                        "condensation": False,
                        "static_condensed_operator_used": False,
                        "trace_slab_pc_used": False,
                        "global_matrix_materialized": False,
                        "augmented_matrix_materialized": False,
                        "explicit_C_materialized_count": 0,
                        "explicit_D_materialized_count": 0,
                        "fe_sized_allgather": False,
                        "modal_allreduce_count_per_apply": 1,
                        "modal_allreduce_count_per_hermitian_apply": 1,
                    },
                    "bridge": {
                        "forward_apply_count": 2,
                        "fixed_work_vectors": 2,
                        "per_apply_vec_creation": 0,
                    },
                }
            ],
        }
    )
    core_artifacts = []
    checkpoint_values = {
        "solution": checkpoint_solution,
        "outer_action": checkpoint_outer_action,
        "residual": checkpoint_residual,
        "rhs": w7_residual,
    }
    for index in (1, 2):
        base = raw_dir / "inner_checkpoints" / f"run{index}"
        core_artifacts.append(
            {
                "run_index": index,
                "true_relative_residual": float(
                    np.linalg.norm(checkpoint_residual)
                    / np.linalg.norm(w7_residual)
                ),
                "artifacts": {
                    name: _write_array(
                        base / f"m6b_iter20_{name}.npy",
                        checkpoint=True,
                        values=checkpoint_values[name],
                    )
                    for name in ("solution", "outer_action", "residual", "rhs")
                },
            }
        )
    physical_artifacts = {
        name: _write_array(
            raw_dir / f"w16a_physical_{name}.npy",
            checkpoint=False,
            values=physical_image,
        )
        for name in ("p1", "p2")
    }
    summary["artifacts"] = {
        "inner_checkpoints": core_artifacts,
        "physical_action_outputs": physical_artifacts,
    }
    rhs_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(w7_residual)
    solution_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(
        checkpoint_solution
    )
    physical_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(physical_image)
    for record in summary["inner_records"]:
        record["rhs_sha256"] = rhs_sha
        record["solution_sha256"] = solution_sha
        record["true_residual"] = 1.0e-3
    summary["residual"] = {
        "role": "untouched_W7_cumulative400_full_explicit_residual",
        "authority": deepcopy(w7["compact"]),
        "artifact": deepcopy(w7["residual_artifact"]),
    }
    summary["z_identity"].update(
        {"first_sha256": solution_sha, "second_sha256": solution_sha}
    )
    summary["p_identity"].update(
        {"first_sha256": physical_sha, "second_sha256": physical_sha}
    )
    summary["measurements"] = [
        repeat_rank_one_projection(
            w7_residual,
            physical_image,
            block_size=runner.M6B_W11A_BLOCK_SIZE,
            schema=runner.M6B_W16A_SCHEMA,
        )
        for _ in (1, 2)
    ]
    summary["core"] = deepcopy(summary)
    summary["authority"] = {
        "w7": deepcopy(w7["compact"]),
        "w7_raw_dir": w7["raw_dir"],
        "w7_residual_artifact": deepcopy(w7["residual_artifact"]),
        "factor_manifest": deepcopy(factor),
    }
    summary.update(
        {
            "phase": runner.M6B_W16A_PHASE,
            "status": "action_gate_pass",
            "classification": "W16A_GLOBAL_SHIFTED_INNER_PASS",
            "w16a_pass": True,
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
            "w16b_locked": True,
            "w16b_action_candidate": True,
            "scope": runner._m6b_w16a_scope(),
            "runtime_identity": {"compiler": deepcopy(factor["factor_compiler"])},
            "p6": {},
            "predicted_live_set": runner._m6b_w16a_predicted_live_set(),
            "jit_cache": {
                "source": str((runner.ROOT / runner.M6B_W16A_JIT_RELATIVE_PATH).resolve()),
                "target": str((raw_dir / "jit_cache").resolve()),
                "source_before": deepcopy(cache),
                "source_final": deepcopy(cache),
                "target_before": deepcopy(cache),
                "target_final": deepcopy(cache),
                "source_unchanged": True,
                "target_unchanged": True,
                "target_matches_source": True,
                "warm_precompiled": True,
                "runtime_compile_allowed": False,
            },
            "source_at_start": source,
            "source_at_end": source,
            "checks": {},
            "problems": [],
            "error": None,
        }
    )
    progress = [
        {
            "schema": f"{runner.M6B_W16A_SCHEMA}.progress.v1",
            "phase": runner.M6B_W16A_PHASE,
            "event": event,
            "elapsed_wall_seconds": float(index),
        }
        for index, event in enumerate(runner.M6B_W16A_EVENTS)
    ]
    raw_progress = raw_dir / runner.M6B_W16A_PROGRESS_FILENAME
    raw_progress.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in progress),
        encoding="utf-8",
    )
    runner._write_json(raw_dir / runner.M6B_W16A_SUMMARY_FILENAME, runner._attach_evidence(summary))

    timeline_path = watchdog_dir / f"{runner.M6B_W16A_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W16A_PHASE,
                "rss_bytes": 100,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (watchdog_dir / f"{runner.M6B_W16A_PHASE}_stdout.txt").write_text("ok\n")
    (watchdog_dir / f"{runner.M6B_W16A_PHASE}_root_pid.json").write_text("{}\n")
    process = {
        "return_code": 0,
        "termination": None,
        "peak_rss_bytes": 100,
        "swap_bytes": 0,
    }
    timeline = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W16A_PHASE
    )
    watchdog = {
        "schema": runner.M6B_W16A_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W16A_PHASE,
        "status": "measurement_complete",
        "process": process,
        "drain": {"gone": True},
        "source_at_start": source,
        "source_at_end": source,
        "source_end_clean": True,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W16A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W16A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W16A_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(raw_dir.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "command": runner._m6b_w16a_worker_command(
            raw_dir,
            runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_W7_RAW_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_JIT_RELATIVE_PATH,
            EXPECTED_SHA,
        ),
        "artifact_inventory": {
            "raw": runner._m6b_w16a_raw_artifacts(raw_dir),
            "watchdog": runner._m6b_w16a_watchdog_artifacts(watchdog_dir),
        },
        "worker_summary": runner._artifact(
            raw_dir, runner.M6B_W16A_SUMMARY_FILENAME
        ),
        "timeline": timeline,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w16b_unlocked": False,
    }
    watchdog_path = watchdog_dir / runner.M6B_W16A_WATCHDOG_SUMMARY_FILENAME
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))
    return {
        "raw": raw_dir,
        "watchdog": watchdog_dir,
        "watchdog_summary": watchdog_path,
        "summary": summary,
    }


def _refresh_summary_and_watchdog(fixture, summary):
    raw_dir = fixture["raw"]
    watchdog_path = fixture["watchdog_summary"]
    runner._write_json(
        raw_dir / runner.M6B_W16A_SUMMARY_FILENAME,
        runner._attach_evidence(summary),
    )
    watchdog = runner._read_json(watchdog_path)
    watchdog["worker_summary"] = runner._artifact(
        raw_dir, runner.M6B_W16A_SUMMARY_FILENAME
    )
    watchdog["artifact_inventory"]["raw"][0] = watchdog["worker_summary"]
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))


def test_w16a_formal_gate_passes_and_compact_is_scalar_only(formal_fixture):
    report = runner._m6b_w16a_formal_gate(
        formal_fixture["raw"], formal_fixture["watchdog_summary"], EXPECTED_SHA
    )
    assert report["pass"] is True
    assert report["classification"] == "W16A_FORMAL_ACTION_GATE_PASS"
    assert all(report["checks"].values())
    assert "records" not in report["timeline"]
    measured = report["measured"]
    assert measured["global_shifted_action_count"] == 42
    assert measured["local_exact_shifted_volume_action_count"] == 40
    assert measured["physical_action_count"] == 2
    output = formal_fixture["raw"].parent / "closeout.json"
    assert (
        runner._run_m6b_w16a_check(
            formal_fixture["raw"],
            formal_fixture["watchdog_summary"],
            output,
            EXPECTED_SHA,
        )
        == 0
    )
    compact = runner._read_json(output)
    assert compact["classification"] == "W16A_FORMAL_ACTION_GATE_PASS"
    assert "records" not in compact["timeline"]
    assert compact["w16b_unlocked"] is True


def test_w16a_numeric_fail_is_not_worker_execution_fail(formal_fixture):
    summary = deepcopy(formal_fixture["summary"])
    residual = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128)
    failing_direction = np.asarray(
        [-np.conjugate(residual[1]), np.conjugate(residual[0])],
        dtype=np.complex128,
    )
    physical = summary["core"]["artifacts"]["physical_action_outputs"]
    for name in ("p1", "p2"):
        path = Path(physical[name]["path"])
        np.save(path, failing_direction, allow_pickle=False)
        physical[name] = _descriptor(path, failing_direction, checkpoint=False)
    failing_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(failing_direction)
    summary["core"]["p_identity"].update(
        {"first_sha256": failing_sha, "second_sha256": failing_sha}
    )
    summary["core"]["measurements"] = [
        repeat_rank_one_projection(
            residual,
            failing_direction,
            block_size=runner.M6B_W11A_BLOCK_SIZE,
            schema=runner.M6B_W16A_SCHEMA,
        )
        for _ in (1, 2)
    ]
    summary["status"] = "gate_failed"
    summary["classification"] = "W16A_GLOBAL_SHIFTED_INNER_NUMERIC_FAIL"
    summary["w16a_pass"] = False
    summary["w16b_action_candidate"] = False
    _refresh_summary_and_watchdog(formal_fixture, summary)
    watchdog = runner._read_json(formal_fixture["watchdog_summary"])
    watchdog["process"]["return_code"] = 1
    runner._write_json(
        formal_fixture["watchdog_summary"], runner._attach_evidence(watchdog)
    )
    report = runner._m6b_w16a_formal_gate(
        formal_fixture["raw"], formal_fixture["watchdog_summary"], EXPECTED_SHA
    )
    assert report["pass"] is False
    assert report["classification"] == "W16A_GLOBAL_SHIFTED_INNER_NUMERIC_FAIL"
    assert report["checks"]["worker_action_gate"] is False
    assert all(report["checks"][name] for name in report["checks"] if name != "worker_action_gate")


@pytest.mark.parametrize(
    "tamper",
    ["rhs_authority", "solution_z", "p_identity", "inner_residual", "measurement"],
)
def test_w16a_vector_evidence_tamper_fails_closed(formal_fixture, tamper):
    summary = deepcopy(formal_fixture["summary"])
    core = summary["core"]
    if tamper == "rhs_authority":
        core["residual"]["artifact"]["array_sha256"] = "0" * 64
    elif tamper == "solution_z":
        core["z_identity"]["first_sha256"] = "0" * 64
    elif tamper == "p_identity":
        core["p_identity"]["first_sha256"] = "0" * 64
    elif tamper == "inner_residual":
        core["inner_records"][0]["true_residual"] = 0.2
    else:
        core["measurements"][0]["rho"] = 0.123
    _refresh_summary_and_watchdog(formal_fixture, summary)
    report = runner._m6b_w16a_formal_gate(
        formal_fixture["raw"], formal_fixture["watchdog_summary"], EXPECTED_SHA
    )
    assert report["pass"] is False
    assert report["checks"]["vector_evidence"] is False
    assert report["classification"] == "W16A_EXECUTION_OR_EVIDENCE_FAIL"


def test_w16a_resource_failure_is_distinct(formal_fixture):
    watchdog_path = formal_fixture["watchdog_summary"]
    watchdog = runner._read_json(watchdog_path)
    watchdog["process"]["peak_rss_bytes"] = runner.M6B_W16A_FORMAL_RSS_LIMIT_BYTES
    timeline_path = formal_fixture["watchdog"] / f"{runner.M6B_W16A_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W16A_PHASE,
                "rss_bytes": runner.M6B_W16A_FORMAL_RSS_LIMIT_BYTES,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    watchdog["timeline"] = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W16A_PHASE
    )
    watchdog["artifact_inventory"]["watchdog"][0] = runner._artifact(
        formal_fixture["watchdog"], f"{runner.M6B_W16A_PHASE}_timeline.jsonl"
    )
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))
    report = runner._m6b_w16a_formal_gate(
        formal_fixture["raw"], watchdog_path, EXPECTED_SHA
    )
    assert report["classification"] == "W16A_RESOURCE_FAIL"
    assert report["checks"]["resource"] is False


def test_w16a_evidence_tamper_fails_closed(formal_fixture):
    summary = deepcopy(formal_fixture["summary"])
    summary["w16b_locked"] = False
    _refresh_summary_and_watchdog(formal_fixture, summary)
    report = runner._m6b_w16a_formal_gate(
        formal_fixture["raw"], formal_fixture["watchdog_summary"], EXPECTED_SHA
    )
    assert report["pass"] is False
    assert report["classification"] == "W16A_EXECUTION_OR_EVIDENCE_FAIL"
    assert report["checks"]["worker_evidence"] is False


def test_w16a_parser_and_command_dispatch(monkeypatch):
    assert runner.M6B_W16A_EVENTS == (
        "authority_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "auxiliary_constructed",
        "inner_checkpoint_1_ready",
        "inner_checkpoint_2_ready",
        "auxiliary_released",
        "physical_constructed",
        "physical_apply_1_ready",
        "physical_apply_2_ready",
        "physical_released",
        "measurement_ready",
        "summary_ready",
    )
    parser = runner._parser()
    args = parser.parse_args(
        [
            "m6b-w16a-watchdog",
            "--run-dir",
            "raw",
            "--watchdog-dir",
            "watch",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7raw",
            "--shifted-factor-manifest",
            "factor.json",
            "--jit-cache-source",
            "jit",
            "--expected-source-sha",
            EXPECTED_SHA,
        ]
    )
    assert args.command == "m6b-w16a-watchdog"
    check_args = parser.parse_args(
        [
            "m6b-w16a-check",
            "--raw-dir",
            "raw",
            "--watchdog-summary",
            "watch/w16a_watchdog_summary.json",
            "--output",
            "out.json",
            "--expected-source-sha",
            EXPECTED_SHA,
        ]
    )
    assert check_args.command == "m6b-w16a-check"
    observed = []
    monkeypatch.setattr(
        runner,
        "_run_m6b_w16a_watchdog",
        lambda *values: observed.append(values) or 17,
    )
    assert (
        runner.main(
            [
                "m6b-w16a-watchdog",
                "--run-dir",
                "raw",
                "--watchdog-dir",
                "watch",
                "--w7-compact",
                "w7.json",
                "--w7-raw-dir",
                "w7raw",
                "--shifted-factor-manifest",
                "factor.json",
                "--jit-cache-source",
                "jit",
                "--expected-source-sha",
                EXPECTED_SHA,
            ]
        )
        == 17
    )
    assert len(observed) == 1
    check_observed = []
    monkeypatch.setattr(
        runner,
        "_run_m6b_w16a_check",
        lambda *values: check_observed.append(values) or 19,
    )
    assert (
        runner.main(
            [
                "m6b-w16a-check",
                "--raw-dir",
                "raw",
                "--watchdog-summary",
                "watch/w16a_watchdog_summary.json",
                "--output",
                "out.json",
                "--expected-source-sha",
                EXPECTED_SHA,
            ]
        )
        == 19
    )
    assert len(check_observed) == 1
    command = runner._m6b_w16a_worker_command(
        Path("raw"), Path("w7"), Path("w7raw"), Path("factor"), Path("jit"), EXPECTED_SHA
    )
    assert command[3] == "m6b-w16a-global-shifted-inner-diagnostic"
    assert "--shifted-factor-manifest" in command


def test_w16a_worker_never_unlocks_w16b_early():
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert '"w16b_locked": True' in source
    assert '"w16b_action_candidate": bool(diagnostic_pass)' in source
