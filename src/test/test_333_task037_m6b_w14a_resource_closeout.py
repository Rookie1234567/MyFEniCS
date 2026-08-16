from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_m6b_w14_global_b0_inner_pc import W14A_ACTION_SCHEMA


def _watchdog_args() -> list[str]:
    return [
        "m6b-w14a-watchdog",
        "--run-dir",
        "run",
        "--watchdog-dir",
        "watchdog",
        "--w5-compact",
        "w5.json",
        "--w5-raw-dir",
        "w5",
        "--w7-compact",
        "w7.json",
        "--w7-raw-dir",
        "w7",
        "--m3y-manifest",
        "m3y.json",
        "--jit-cache-source",
        "physical-jit",
        "--b0-jit-cache-source",
        "b0-jit",
        "--expected-source-sha",
        "a" * 40,
    ]


def test_w14a_marker_contract_and_fixed_worker_command():
    assert runner.M6B_W14A_EVENTS == (
        "authority_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "b0_ready",
        "inner_pc_ready",
        "physical_action_ready",
        "coexistence_ready",
        "inner_apply_1_ready",
        "inner_apply_2_ready",
        "physical_apply_1_ready",
        "physical_apply_2_ready",
        "measurement_ready",
        "summary_ready",
    )
    command = runner._m6b_w14a_worker_command(
        Path("run"),
        Path("w5.json"),
        Path("w5"),
        Path("w7.json"),
        Path("w7"),
        Path("m3y.json"),
        Path("physical-jit"),
        Path("b0-jit"),
        "a" * 40,
    )
    assert command[0] == sys.executable
    assert command[1:4] == [
        "-m",
        "benchmarks.run_task037_extra_m6b",
        "m6b-w14a-action-diagnostic",
    ]
    assert command[-2:] == ["--expected-source-sha", "a" * 40]


def test_w14a_watchdog_parser_exposes_all_fixed_authorities():
    args = runner._parser().parse_args(_watchdog_args())
    assert args.command == "m6b-w14a-watchdog"
    assert args.run_dir == "run"
    assert args.watchdog_dir == "watchdog"
    assert args.w5_compact == "w5.json"
    assert args.w7_compact == "w7.json"
    assert args.b0_jit_cache_source == "b0-jit"


def test_w14a_watchdog_main_dispatch_is_thin(monkeypatch):
    observed = {}

    def fake_watchdog(*args):
        observed["args"] = args
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w14a_watchdog", fake_watchdog)
    assert runner.main(_watchdog_args()) == 17
    assert observed["args"][-1] == "a" * 40
    assert observed["args"][0] == Path("run").resolve()
    assert observed["args"][1] == Path("watchdog").resolve()


def _source(sha: str) -> dict[str, object]:
    return {
        "source_commit_full_sha": sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _jit_fixture(tmp_path: Path) -> dict[str, object]:
    physical = {"entries": [], "inventory_sha256": "physical"}
    b0 = {"entries": [], "inventory_sha256": "b0"}
    union = {"entries": [], "inventory_sha256": "union"}
    stages = []
    for stage in (
        "after_stage",
        "after_b0_ready",
        "after_physical_action_ready",
        "after_measurement",
        "final",
    ):
        stages.append(
            {
                "stage": stage,
                "physical_source_inventory_sha256": "physical",
                "b0_source_inventory_sha256": "b0",
                "union_target_inventory_sha256": "union",
                "physical_file_count": runner.M6B_W11A_PHYSICAL_JIT_FILE_COUNT,
                "b0_file_count": runner.M6B_W11A_B0_JIT_FILE_COUNT,
                "union_file_count": runner.M6B_W11A_UNION_JIT_FILE_COUNT,
                "target_matches_union": True,
            }
        )
    physical_path = str((tmp_path / "physical-jit").resolve())
    b0_path = str((tmp_path / "b0-jit").resolve())
    target_path = str((tmp_path / "union-jit").resolve())
    return {
        "physical_source": physical_path,
        "b0_source": b0_path,
        "union_target": target_path,
        "physical_source_before": physical,
        "b0_source_before": b0,
        "physical_source_final": physical,
        "b0_source_final": b0,
        "union_target_final": union,
        "physical_file_count": runner.M6B_W11A_PHYSICAL_JIT_FILE_COUNT,
        "b0_file_count": runner.M6B_W11A_B0_JIT_FILE_COUNT,
        "union_file_count": runner.M6B_W11A_UNION_JIT_FILE_COUNT,
        "warm_precompiled": True,
        "runtime_compile_allowed": False,
        "source_unchanged": True,
        "target_frozen_unchanged": True,
        "verification_error": None,
        "verification_stages": stages,
    }


def _core_fixture() -> dict[str, object]:
    record = {
        "algorithm": "fgmres_right_b0_fixed20",
        "iterations": 20,
        "converged_reason": -3,
        "pc_apply_count_delta": 20,
        "operator_apply_count_delta": 20,
        "finite": True,
        "gate_pass": True,
        "true_residual": 1.0e-3,
        "rhs_sha256": "rhs",
    }
    return {
        "inner_audit": {
            "algorithm": {
                "solver": "fgmres",
                "restart": 20,
                "max_it": 20,
                "zero_start": True,
                "rtol": 0.0,
                "atol": 0.0,
                "pc_side": "right",
                "mpi_size": 1,
            },
            "rows": 2,
            "underlying_pc": {"apply_count": 40},
            "applications": [dict(record), dict(record)],
            "rhs_vec_owned": True,
            "rhs_vec_destroyed": False,
            "wrapper_owned_full_vector_count": 1,
            "wrapper_owned_full_vector_bytes": 32,
            "retained_full_vector_count": 1,
            "retained_full_vector_bytes": 32,
            "application_records_full_vector_count": 0,
            "application_records_full_vector_bytes": 0,
        },
        "z_identity": {
            "finite": True,
            "dtype": "complex128",
            "shape_equal": True,
            "sha256_equal": True,
            "relative_difference": 0.0,
        },
        "p_identity": {
            "finite": True,
            "dtype": "complex128",
            "shape_equal": True,
            "sha256_equal": True,
            "relative_difference": 0.0,
        },
        "measurement": {
            "schema": W14A_ACTION_SCHEMA,
            "finite": True,
            "rho": 0.8,
            "normal_closure": 1.0e-12,
            "projection_orthogonality": 1.0e-12,
            "repeat_exact": True,
            "repeat": {"repeat_exact": True, "passes": 2},
        },
        "p2_measurement": {
            "schema": W14A_ACTION_SCHEMA,
            "finite": True,
            "rho": 0.8,
            "normal_closure": 1.0e-12,
            "projection_orthogonality": 1.0e-12,
        },
        "physical_action_count": 2,
    }


def _action_audit_fixture(inner_audit: dict[str, object]) -> dict[str, object]:
    outer = {
        "apply_count": 2,
        "matrix_type": "python_action_only",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
    }
    physical = {
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
    }
    dtn = {
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
    }
    bridge = {
        "vector_create_count": 2,
        "fixed_work_vectors": 2,
        "per_apply_vec_creation": 0,
        "forward_apply_count": 2,
    }
    construction_outer = copy.deepcopy(outer)
    construction_outer["apply_count"] = 0
    construction_physical = copy.deepcopy(physical)
    construction_physical["apply_count"] = 0
    construction_dtn = copy.deepcopy(dtn)
    construction_dtn["apply_count"] = 0
    construction_bridge = copy.deepcopy(bridge)
    construction_bridge["forward_apply_count"] = 0
    lifecycle = [
        "b0_constructed",
        "physical_constructed",
        "coexistence_ready",
        "physical_released",
        "b0_released",
    ]
    return {
        "authority_vector_retention": {
            "q_vector_retained": False,
            "retained_authority_vector_roles": ["target"],
        },
        "lifecycle_events": lifecycle,
        "coexistence": {
            "b0_live": True,
            "physical_live": True,
            "release_between_operations": False,
        },
        "b0_instances": [
            {"total_pc_apply_count": 40, "inner_pc": inner_audit}
        ],
        "physical_instances": [
            {
                "physical": physical,
                "outer": outer,
                "dtn": dtn,
                "bridge": bridge,
                "total_physical_action_count": 2,
            }
        ],
        "physical": construction_physical,
        "outer": construction_outer,
        "dtn": construction_dtn,
        "bridge": construction_bridge,
    }


def _write_w14a_fixture(tmp_path: Path, monkeypatch) -> tuple[Path, Path, str]:
    sha = "a" * 40
    raw_dir = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw_dir.mkdir(parents=True)
    watchdog_dir.mkdir(parents=True)
    source = _source(sha)
    monkeypatch.setattr(
        __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"]),
        "_light_source",
        lambda: copy.deepcopy(source),
    )
    core = _core_fixture()
    authority = {
        "q": {"raw_path": str((tmp_path / "w5" / "q.npy").resolve())},
        "target": {"raw_path": str((tmp_path / "w7" / "target.npy").resolve())},
        "w5_compact": {"path": str((tmp_path / "w5.json").resolve())},
        "w7_compact": {"path": str((tmp_path / "w7.json").resolve())},
    }
    jit = _jit_fixture(tmp_path)
    summary = {
        "schema": runner.M6B_W14A_SCHEMA,
        "phase": runner.M6B_W14A_PHASE,
        "status": "action_gate_pass",
        "classification": "W14A_ACTION_GATE_PASS",
        "w14a_pass": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w14_2_locked": True,
        "scope": runner._m6b_w14a_scope(),
        "p6": {
            "global_cells": runner.M6B_GLOBAL_CELLS,
            "local_cells": runner.M6B_GLOBAL_CELLS,
            "local_nloc": runner.M6B_LOCAL_NLOC,
            "global_rows": runner.M6B_GLOBAL_ROWS,
            "constraint_count": runner.M6B_CONSTRAINTS,
        },
        "authority": authority,
        "jit_cache": jit,
        "predicted_live_set": runner._m6b_w14a_predicted_live_set(),
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "global_matrix_materialized": False,
            "augmented_matrix_materialized": False,
            "condensation": False,
            "static_condensed_operator_used": False,
            "trace_slab_pc_used": False,
            "slab_factors": 0,
            "shifted_pc_used": False,
            "physical_ksp_used": False,
            "pde_used": False,
            "official_rta": False,
        },
        "action_audit": _action_audit_fixture(core["inner_audit"]),
        "core": core,
        "source_at_start": source,
        "source_at_end": source,
    }
    runner._write_json(raw_dir / runner.M6B_W14A_SUMMARY_FILENAME, runner._attach_evidence(summary))
    progress = [
        {
            "schema": f"{runner.M6B_W14A_SCHEMA}.progress.v1",
            "phase": runner.M6B_W14A_PHASE,
            "event": event,
            "elapsed_wall_seconds": float(index),
        }
        for index, event in enumerate(runner.M6B_W14A_EVENTS)
    ]
    (raw_dir / runner.M6B_W14A_PROGRESS_FILENAME).write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in progress),
        encoding="utf-8",
    )
    timeline_name = f"{runner.M6B_W14A_PHASE}_timeline.jsonl"
    (watchdog_dir / timeline_name).write_text(
        json.dumps(
            {
                "phase": runner.M6B_W14A_PHASE,
                "rss_bytes": 100,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (watchdog_dir / f"{runner.M6B_W14A_PHASE}_stdout.txt").write_text("ok", encoding="utf-8")
    (watchdog_dir / f"{runner.M6B_W14A_PHASE}_root_pid.json").write_text("{}", encoding="utf-8")
    watchdog = {
        "schema": runner.M6B_W14A_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W14A_PHASE,
        "status": "measurement_complete",
        "process": {
            "return_code": 0,
            "termination": None,
            "peak_rss_bytes": 100,
            "swap_bytes": 0,
        },
        "drain": {"gone": True},
        "source_at_start": source,
        "source_at_end": source,
        "source_end_clean": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W14A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W14A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W14A_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(raw_dir.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "command": runner._m6b_w14a_worker_command(
            raw_dir,
            Path(authority["w5_compact"]["path"]),
            Path(authority["q"]["raw_path"]).parent,
            Path(authority["w7_compact"]["path"]),
            Path(authority["target"]["raw_path"]).parent,
            runner.ROOT / runner.M6B_W11A_M3Y_MANIFEST_RELATIVE_PATH,
            Path(jit["physical_source"]),
            Path(jit["b0_source"]),
            sha,
        ),
        "artifact_inventory": {
            "raw": [
                runner._artifact(raw_dir, runner.M6B_W14A_SUMMARY_FILENAME),
                runner._artifact(raw_dir, runner.M6B_W14A_PROGRESS_FILENAME),
            ],
            "watchdog": [
                runner._artifact(watchdog_dir, timeline_name),
                runner._artifact(watchdog_dir, f"{runner.M6B_W14A_PHASE}_stdout.txt"),
                runner._artifact(watchdog_dir, f"{runner.M6B_W14A_PHASE}_root_pid.json"),
            ],
        },
        "worker_summary": runner._artifact(raw_dir, runner.M6B_W14A_SUMMARY_FILENAME),
        "timeline": runner._m6b_w8a_timeline_valid(
            watchdog_dir / timeline_name, phase=runner.M6B_W14A_PHASE
        ),
    }
    runner._write_json(
        watchdog_dir / runner.M6B_W14A_WATCHDOG_SUMMARY_FILENAME,
        runner._attach_evidence(watchdog),
    )
    monkeypatch.setattr(
        runner,
        "_m6b_w11a_dual_jit_snapshot",
        lambda *_args, **_kwargs: {
            "physical": {"entries": [], "inventory_sha256": "physical"},
            "b0": {"entries": [], "inventory_sha256": "b0"},
            "union": {"entries": [], "inventory_sha256": "union"},
            "target": {"entries": [], "inventory_sha256": "union"},
        },
    )
    return raw_dir, watchdog_dir / runner.M6B_W14A_WATCHDOG_SUMMARY_FILENAME, sha


def _refresh_w14a_watchdog_fixture(
    raw_dir: Path, watchdog_summary: Path, *, refresh_timeline: bool = False
) -> None:
    watchdog = json.loads(watchdog_summary.read_text(encoding="utf-8"))
    inventory = watchdog["artifact_inventory"]
    inventory["raw"][0] = runner._artifact(
        raw_dir, runner.M6B_W14A_SUMMARY_FILENAME
    )
    watchdog["worker_summary"] = inventory["raw"][0]
    if refresh_timeline:
        timeline_name = f"{runner.M6B_W14A_PHASE}_timeline.jsonl"
        watchdog["timeline"] = runner._m6b_w8a_timeline_valid(
            watchdog_summary.parent / timeline_name, phase=runner.M6B_W14A_PHASE
        )
        inventory["watchdog"][0] = runner._artifact(
            watchdog_summary.parent, timeline_name
        )
    runner._write_json(watchdog_summary, runner._attach_evidence(watchdog))


def test_w14a_formal_checker_accepts_complete_synthetic_fixture(tmp_path, monkeypatch):
    raw_dir, watchdog_summary, sha = _write_w14a_fixture(tmp_path, monkeypatch)
    output = tmp_path / "formal.json"
    assert runner._run_m6b_w14a_check(raw_dir, watchdog_summary, output, sha) == 0
    worker = json.loads(
        (raw_dir / runner.M6B_W14A_SUMMARY_FILENAME).read_text(encoding="utf-8")
    )
    audit = worker["action_audit"]
    assert audit["outer"]["apply_count"] == 0
    assert audit["physical"]["apply_count"] == 0
    assert audit["dtn"]["apply_count"] == 0
    assert audit["bridge"]["forward_apply_count"] == 0
    assert audit["physical_instances"][0]["outer"]["apply_count"] == 2
    assert audit["physical_instances"][0]["physical"]["apply_count"] == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["classification"] == "W14A_FORMAL_RESOURCE_CLOSEOUT_PASS"
    assert result["formal_pass"] is True
    assert result["pde_pass"] is False
    assert result["official_rta"] is False
    assert result["w14_2_unlocked"] is True
    assert result["w14_2_locked"] is False
    assert all(result["checks"].values())
    assert "records" not in result["timeline"]
    assert result["measured"]["physical_action_count"] == 2


@pytest.mark.parametrize("failure", ("peak", "swap", "compiler"))
def test_w14a_formal_checker_resource_fail_closed(tmp_path, monkeypatch, failure):
    raw_dir, watchdog_summary, sha = _write_w14a_fixture(tmp_path, monkeypatch)
    watchdog = json.loads(watchdog_summary.read_text(encoding="utf-8"))
    if failure == "peak":
        watchdog["process"]["peak_rss_bytes"] = runner.M6B_W14A_FORMAL_RSS_LIMIT_BYTES
    elif failure == "swap":
        watchdog["process"]["swap_bytes"] = 1
    else:
        timeline = watchdog_summary.parent / f"{runner.M6B_W14A_PHASE}_timeline.jsonl"
        timeline.write_text(
            json.dumps(
                {
                    "phase": runner.M6B_W14A_PHASE,
                    "rss_bytes": 100,
                    "swap_bytes": 0,
                    "compiler_descendant_pids": [7],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        _refresh_w14a_watchdog_fixture(
            raw_dir, watchdog_summary, refresh_timeline=True
        )
    if failure != "compiler":
        runner._write_json(watchdog_summary, runner._attach_evidence(watchdog))
    output = tmp_path / "formal.json"
    assert runner._run_m6b_w14a_check(raw_dir, watchdog_summary, output, sha) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["classification"] == "W14A_RESOURCE_FAIL"
    assert result["formal_pass"] is False
    assert result["w14_2_locked"] is True
    if failure == "compiler":
        assert result["checks"]["artifacts"] is True
        assert result["checks"]["watchdog_evidence"] is True
        assert result["checks"]["resource"] is False


def test_w14a_formal_checker_rejects_marker_and_recomputed_numeric_tamper(tmp_path, monkeypatch):
    raw_dir, watchdog_summary, sha = _write_w14a_fixture(tmp_path, monkeypatch)
    progress = raw_dir / runner.M6B_W14A_PROGRESS_FILENAME
    lines = progress.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    progress.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = tmp_path / "marker.json"
    assert runner._run_m6b_w14a_check(raw_dir, watchdog_summary, output, sha) == 1
    marker_result = json.loads(output.read_text(encoding="utf-8"))
    assert marker_result["checks"]["progress"] is False

    raw_dir, watchdog_summary, sha = _write_w14a_fixture(tmp_path / "numeric", monkeypatch)
    summary_path = raw_dir / runner.M6B_W14A_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["w14a_pass"] = True
    summary["core"]["measurement"]["rho"] = 0.99
    runner._write_json(summary_path, runner._attach_evidence(summary))
    _refresh_w14a_watchdog_fixture(raw_dir, watchdog_summary)
    output = raw_dir.parent / "numeric.json"
    assert runner._run_m6b_w14a_check(raw_dir, watchdog_summary, output, sha) == 1
    numeric_result = json.loads(output.read_text(encoding="utf-8"))
    assert numeric_result["classification"] == "W14A_ACTION_NUMERIC_FAIL"
    assert numeric_result["checks"]["worker_action_gate"] is False
    assert numeric_result["checks"]["artifacts"] is True
    assert numeric_result["checks"]["watchdog_evidence"] is True


def test_w14a_formal_checker_missing_core_key_fails_closed(tmp_path, monkeypatch):
    raw_dir, watchdog_summary, sha = _write_w14a_fixture(tmp_path, monkeypatch)
    summary_path = raw_dir / runner.M6B_W14A_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del summary["core"]["p2_measurement"]
    runner._write_json(summary_path, runner._attach_evidence(summary))
    output = tmp_path / "missing.json"
    assert runner._run_m6b_w14a_check(raw_dir, watchdog_summary, output, sha) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["formal_pass"] is False
    assert result["classification"] == "W14A_EXECUTION_OR_EVIDENCE_FAIL"


def test_w14a_progress_rejects_json_scalar_record(tmp_path):
    progress = tmp_path / runner.M6B_W14A_PROGRESS_FILENAME
    progress.write_text("1\n", encoding="utf-8")
    result = runner._m6b_w14a_progress_valid(progress)
    assert result["pass"] is False


def test_w14a_check_parser_has_fixed_contract():
    args = runner._parser().parse_args(
        [
            "m6b-w14a-check",
            "--raw-dir",
            "raw",
            "--watchdog-summary",
            "watchdog.json",
            "--output",
            "out.json",
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.command == "m6b-w14a-check"
    assert args.expected_source_sha == "a" * 40
