from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task037_extra_h2b as runner


def _runtime() -> dict[str, object]:
    return {
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


def _source(label: str) -> dict[str, object]:
    return {
        "label": label,
        "definition": runner.H2B_SOURCE_DEFINITIONS[label],
        "definition_sha256": runner._source_definition_sha(label),
        "vector_sha256": "a" * 64,
        "full_space_norm": 1.0,
        "slave_semantics": "slave identity rows are explicitly zero in B0 source; smoother copies rhs identity correction",
        "rho_norm_scope": "all_fullspace_rows",
        "external_slave_mask": False,
        "correction_sha256": "b" * 64,
        "repeat_correction_sha256": "b" * 64,
        "residual_sha256": "c" * 64,
        "repeat_residual_sha256": "c" * 64,
        "finite": True,
        "independent_residual_numerator": 0.2,
        "independent_residual_denominator": 1.0,
        "rho": 0.2,
        "independent_action_relative_error": 0.0,
        "apply_seconds": [2.0, 2.0],
    }


def _core_identity() -> dict[str, object]:
    return {
        "fine_space": "uncondensed_fullspace",
        "condensation": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "B2_B4_local_krylov_used": False,
        "fullspace_patch_pc_used": True,
        "interior_recovery_required": False,
        "ordinary_default_changed": False,
    }


def _producer_authority() -> dict[str, object]:
    return {
        "r0_source": "b7eef17f10655be99f5bba072f9a547ae05f17ac",
        "r1_source": "107a3ac1ea01ab0cfdd450a268789890ef76e030",
        "r2_producer_source_full_sha": "da8ddbb257b0d9d510e9d711d23144f50dabd0e4",
        "r2_record_sha256": runner.H2B_R2_RECORD_SHA256,
        "r2_record_evidence_sha256": runner.H2B_R2_RECORD_EVIDENCE_SHA256,
        "r2_factor_manifest_sha256": runner.H2B_R2_MANIFEST_SHA256,
    }


def _marker(path: Path, phase: str, event: str) -> str:
    return json.dumps(
        {
            "schema": runner.H2B_PROGRESS_SCHEMA,
            "phase": phase,
            "event": event,
            "elapsed_wall_seconds": 0.1,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _timeline(path: Path, phase: str, rss: int, swap: int, compiler: list[int]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": runner.H2B_PROGRESS_SCHEMA,
                "phase": phase,
                "sample_kind": "worker",
                "elapsed_wall_seconds": 0.1,
                "root_pid": 100 if phase == "stage" else 200,
                "pids": [100 if phase == "stage" else 200],
                "process_count": 1,
                "rss_bytes": rss,
                "swap_bytes": swap,
                "all_status_readable": True,
                "compiler_descendant_pids": compiler,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(runner._attach_evidence(payload), sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _raw_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        runner,
        "_authority",
        lambda: {
            "producer_authority": _producer_authority(),
            "factor_manifest_sha256": runner.H2B_R2_MANIFEST_SHA256,
        },
    )
    raw = tmp_path / "h2b-raw"
    raw.mkdir()
    source = {
        "source_commit_full_sha": "d" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "cleanliness_semantics": "all tracked changes plus every nonignored untracked path",
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    runtime = _runtime()
    identity = runner._fixed_identity()
    scope = runner._fixed_scope()
    cache_dir = raw / "jit_cache"
    cache_dir.mkdir()
    cache_files = []
    for suffix in (".c", ".o", ".so", ".c.cached"):
        path = cache_dir / f"libffcx_forms_synthetic{suffix}"
        path.write_bytes(("artifact" + suffix).encode("ascii"))
        cache_files.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "sha256": runner._sha256_file(path),
            }
        )
    form_common = {
        "role": "b0",
        "ufl_signature": "ufl-synthetic",
        "ufcx_signature": "ufcx-synthetic",
        "module_name": "libffcx_forms_synthetic",
        "ffcx_signature_stem": "synthetic",
        "jit_options": runner._expected_jit_options(cache_dir),
        "form_compiler_options": {"scalar_type": "complex128"},
        "proxy_identity": {"operator": "B0"},
        "element_signature": ["N1curl", 882],
        "cache_files": cache_files,
    }
    stage_form = {**form_common, "code_state": "cold_decl_impl_generated"}
    online_form = {**form_common, "code_state": "hit_no_new_decl_impl"}
    stage = {
        "schema": runner.H2B_WORKER_SCHEMA,
        "phase": "stage",
        "status": "measurement_complete",
        "scope": scope,
        "identity": identity,
        "phase_identity": runner._phase_identity(jit_api=True, compile_called=True, compiler_probe=True),
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": runtime,
        "measurement": {"global_cells": 252, "local_cells": 252, "local_nloc": 882, "global_rows": 173802},
        "form": stage_form,
        "error": None,
    }
    sources = [_source(label) for label in runner.H2B_SOURCE_LABELS]
    factor = {
        "unique_factor_count": 16,
        "class_count": 24,
        "cell_count": 252,
        "finite": True,
        "deterministic": True,
        "factor_plus_metadata_bytes": 201_933_812,
        "factorization_residual_max": 1.0e-15,
        "solve_residual_max": 1.0e-11,
    }
    smoother = {
        "factor_plus_work_bytes": 300_000_000,
        "factor_payload_bytes": 201_933_812,
        "global_row_count": 173802,
        "apply_count": 10,
        "identity": _core_identity(),
        "materialization_identity": {
            key: False
            for key in (
                "global_matrix_materialized",
                "global_constraint_matrix_materialized",
                "cell_schur_matrix_materialized",
                "slab_matrix_materialized",
                "schur_materialized",
                "per_cell_factor",
                "per_cell_dense_c",
                "ksp_created",
                "dtn_used",
                "pde_solve_called",
            )
        },
    }
    timing = {
        "warm_action_seconds": 1.0,
        "volume_action_seconds": [1.0] * 5,
        "action_median_seconds": 1.0,
        "smoother_apply_seconds": [2.0] * 10,
        "smoother_median_seconds": 2.0,
        "smoother_action_ratio": 2.0,
    }
    online = {
        "schema": runner.H2B_WORKER_SCHEMA,
        "phase": "online",
        "status": "measurement_complete",
        "scope": scope,
        "identity": identity,
        "phase_identity": runner._phase_identity(jit_api=True, compile_called=False, compiler_probe=False),
        "source_at_start": source,
        "source_at_end": source,
        "current_online_source": source,
        "runtime_identity": runtime,
        "producer_authority": _producer_authority(),
        "factor_manifest_sha256": runner.H2B_R2_MANIFEST_SHA256,
        "factor_manifest": str(runner.H2B_R2_MANIFEST),
        "measurement": {
            "p6": {"global_cells": 252, "local_cells": 252, "local_nloc": 882, "global_rows": 173802, "constraint_count": 9210},
            "cache": {"unchanged": True, "form_jit_cache_hit": True, "c_source_regeneration": False, "compiler_descendant_pids": []},
            "timing": timing,
        },
        "form": online_form,
        "factor_audit": factor,
        "smoother_audit": {
            **smoother,
            "action_count": 2,
            "expected_action_count": 2,
            "total_action_count": 20,
        },
        "sources": sources,
        "error": None,
    }
    watchdog = {
        "schema": runner.H2B_WATCHDOG_SCHEMA,
        "status": "pass",
        "run_dir": str(raw),
        "scope": scope,
        "identity": identity,
        "command_identity": {
            "python": runtime["sys_executable"],
            "launch_mode": "direct_singleton",
            "stage_command": runner._worker_command(runtime["sys_executable"], "jit-worker", raw),
            "online_command": runner._worker_command(runtime["sys_executable"], "online-worker", raw),
        },
        "source_at_start": source,
        "source_at_end": source,
        "stage": {"return_code": 0, "termination": None, "processes_gone_before_online": True},
        "online": {"return_code": 0, "termination": None},
        "error": None,
    }
    _write_payload(raw / "stage_summary.json", stage)
    online["measurement"]["stage_manifest_sha256"] = runner._sha256_file(
        raw / "stage_summary.json"
    )
    online["measurement"]["r2_manifest_sha256"] = runner.H2B_R2_MANIFEST_SHA256
    _write_payload(raw / "online_summary.json", online)
    _write_payload(raw / "h2b_watchdog_summary.json", watchdog)
    (raw / "stage_progress.jsonl").write_text(
        "\n".join(_marker(raw / "stage_progress.jsonl", "stage", event) for event in runner.H2B_STAGE_EVENTS) + "\n",
        encoding="utf-8",
    )
    (raw / "online_progress.jsonl").write_text(
        "\n".join(_marker(raw / "online_progress.jsonl", "online", event) for event in runner.H2B_ONLINE_EVENTS) + "\n",
        encoding="utf-8",
    )
    _timeline(raw / "stage_timeline.jsonl", "stage", 1_000_000, 0, [301])
    _timeline(raw / "online_timeline.jsonl", "online", 1_000_000, 0, [])
    for name in ("stage_stdout.txt", "online_stdout.txt", "stage_root_pid.json", "online_root_pid.json"):
        (raw / name).write_text(name, encoding="utf-8")
    watchdog = runner._read_json(raw / "h2b_watchdog_summary.json")
    watchdog["raw_artifacts"] = {
        name: runner._artifact(raw, name)
        for name in (
            "stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json", "stage_timeline.jsonl",
            "online_progress.jsonl", "online_stdout.txt", "online_summary.json", "online_timeline.jsonl",
            "stage_root_pid.json", "online_root_pid.json",
        )
    }
    _write_payload(raw / "h2b_watchdog_summary.json", watchdog)
    return raw


def _read_result(raw: Path) -> dict[str, object]:
    return runner._check_raw(raw)


def test_h2b_fixed_cli_scope_and_singleton_commands(tmp_path: Path):
    parser = runner._parser()
    args = parser.parse_args(["watchdog", "--run-dir", str(tmp_path)])
    assert args.command == "watchdog"
    command = runner._worker_command("/repo/.venv/bin/python", "jit-worker", tmp_path)
    assert command == ["/repo/.venv/bin/python", "-m", "benchmarks.run_task037_extra_h2b", "jit-worker", "--run-dir", str(tmp_path.resolve())]
    with pytest.raises(SystemExit):
        parser.parse_args(["watchdog", "--run-dir", str(tmp_path), "--timeout", "1"])
    assert runner._fixed_scope()["stage_rss_limit_bytes"] == 1_800_000_000
    assert runner._fixed_scope()["online_rss_limit_bytes"] == 1_450_000_000
    assert runner._fixed_scope()["swap_limit_bytes"] == 0


def test_h2b_worker_executable_preserves_venv_symlink(monkeypatch, tmp_path: Path):
    target = tmp_path / "usr" / "bin" / "python3.12"
    target.parent.mkdir(parents=True)
    target.write_text("python", encoding="utf-8")
    link = tmp_path / ".venv" / "bin" / "python"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    monkeypatch.setattr(runner.sys, "executable", str(link))
    executable = runner._worker_executable()
    command = runner._worker_command(executable, "jit-worker", tmp_path)
    assert executable == str(link)
    assert command[0] == str(link)
    assert command[0] != str(target)


def test_h2b_sources_are_action_mapped_and_mixed_uses_residuals():
    size = 8
    slave_rows = np.array([1, 6], dtype=np.int64)
    primal = {
        label: np.ascontiguousarray(
            np.arange(size, dtype=np.float64) + (index + 1) * 1j
        )
        for index, label in enumerate(runner.H2B_SOURCE_LABELS)
    }
    calls: list[str] = []

    def action(source: np.ndarray, target: np.ndarray) -> None:
        calls.append("mapped")
        target[:] = 2.0 * source + source[::-1]
        target[slave_rows] = 0.0

    residuals = runner._residual_source_arrays(primal, action, slave_rows)
    assert len(calls) == 3
    for label in (
        "gradient-dominated",
        "curl-dominated",
        "physical-RHS-like",
    ):
        source = primal[label].copy()
        source[slave_rows] = 0.0
        expected = 2.0 * source + source[::-1]
        expected[slave_rows] = 0.0
        np.testing.assert_array_equal(residuals[label], expected)
    gradient = residuals["gradient-dominated"]
    curl = residuals["curl-dominated"]
    expected_mixed = gradient / np.linalg.norm(gradient)
    expected_mixed += (0.37 + 0.11j) * curl / np.linalg.norm(curl)
    expected_mixed /= np.linalg.norm(expected_mixed)
    np.testing.assert_allclose(residuals["mixed"], expected_mixed)
    assert np.all(residuals["checkerboard/high-frequency"][slave_rows] == 0.0)


def test_h2b_watchdog_module_has_no_top_level_heavy_imports():
    tree = ast.parse(
        Path(runner.__file__).read_text(encoding="utf-8"),
        filename=str(runner.__file__),
    )
    imported = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(
        name == "dolfinx"
        or name.startswith("dolfinx.")
        or name == "petsc4py"
        or name == "mpi4py"
        or name == "benchmarks.run_task037_extra_h2"
        for name in imported
    )


def test_h2b_good_raw_recomputes_sources_timing_and_authority(tmp_path, monkeypatch):
    raw = _raw_fixture(tmp_path, monkeypatch)
    result = _read_result(raw)
    assert result["pass"] is True
    assert result["problems"] == []
    assert result["authority"]["factor_manifest_sha256"] == runner.H2B_R2_MANIFEST_SHA256
    assert result["measurements"]["p6"]["constraint_count"] == 9210
    assert result["measurements"]["timing"]["smoother_action_ratio"] == 2.0
    online = runner._read_json(raw / "online_summary.json")
    compact_sources = result["measurements"]["sources"]
    assert compact_sources == online["sources"]
    assert [item["label"] for item in compact_sources] == list(runner.H2B_SOURCE_LABELS)
    sources_by_label = {item["label"]: item for item in compact_sources}
    assert "rho" in sources_by_label["mixed"]
    assert "rho" in sources_by_label["checkerboard/high-frequency"]


def test_h2b_light_source_matches_source_identity_shape(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "HEAD":
            return SimpleNamespace(stdout="a" * 40 + "\n")
        return SimpleNamespace(stdout=" M tracked.py\n?? ignored-artifact/raw.json\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    identity = runner._light_source()
    assert identity == {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": True,
        "source_worktree_dirty": True,
        "cleanliness_semantics": "all tracked changes plus every nonignored untracked path",
        "nonignored_untracked_paths": ["ignored-artifact/raw.json"],
        "worktree_status_porcelain": [" M tracked.py", "?? ignored-artifact/raw.json"],
        "git_error": None,
    }
    assert calls[1][0][-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("stage_peak", "stage_resource"),
        ("online_peak", "online_resource"),
        ("online_swap", "online_resource"),
        ("cache", "cache_hit"),
        ("rho", "sources"),
        ("missing_timing", "timing"),
        ("factor_work", "factor_work"),
        ("identity", "identity"),
        ("authority", "authority"),
        ("runtime", "runtime"),
        ("form", "forms"),
        ("p6_measurement", "p6_measurement"),
        ("source_hash", "sources"),
        ("timing_ratio", "timing"),
    ),
)
def test_h2b_checker_fails_closed_for_gate_mutations(tmp_path, monkeypatch, mutation, expected):
    raw = _raw_fixture(tmp_path, monkeypatch)
    if mutation == "stage_peak":
        _timeline(raw / "stage_timeline.jsonl", "stage", runner.H2B_STAGE_RSS_LIMIT_BYTES, 0, [301])
    elif mutation == "online_peak":
        _timeline(raw / "online_timeline.jsonl", "online", runner.H2B_ONLINE_RSS_LIMIT_BYTES, 0, [])
    elif mutation == "online_swap":
        _timeline(raw / "online_timeline.jsonl", "online", 1_000_000, 1, [])
    elif mutation == "cache":
        value = runner._read_json(raw / "online_summary.json")
        value["measurement"]["cache"]["unchanged"] = False
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "rho":
        value = runner._read_json(raw / "online_summary.json")
        value["sources"][0]["rho"] = 0.9
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "missing_timing":
        value = runner._read_json(raw / "online_summary.json")
        del value["measurement"]["timing"]
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "factor_work":
        value = runner._read_json(raw / "online_summary.json")
        value["smoother_audit"]["factor_plus_work_bytes"] = runner.H2B_FACTOR_WORK_LIMIT_BYTES + 1
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "identity":
        value = runner._read_json(raw / "online_summary.json")
        value["identity"]["condensation"] = True
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "authority":
        value = runner._read_json(raw / "online_summary.json")
        value["producer_authority"]["r0_source"] = "e" * 40
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "runtime":
        value = runner._read_json(raw / "online_summary.json")
        value["runtime_identity"]["threads"]["OMP_NUM_THREADS"] = "2"
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "form":
        value = runner._read_json(raw / "online_summary.json")
        value["form"]["module_name"] = "libffcx_forms_other"
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "p6_measurement":
        value = runner._read_json(raw / "online_summary.json")
        value["measurement"]["p6"]["global_rows"] = 173801
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "source_hash":
        value = runner._read_json(raw / "online_summary.json")
        value["sources"][0]["correction_sha256"] = None
        value["sources"][0]["repeat_correction_sha256"] = None
        _write_payload(raw / "online_summary.json", value)
    elif mutation == "timing_ratio":
        value = runner._read_json(raw / "online_summary.json")
        value["measurement"]["timing"]["smoother_action_ratio"] = 2.5
        _write_payload(raw / "online_summary.json", value)
    result = _read_result(raw)
    assert result["pass"] is False
    assert expected in result["problems"]


def test_h2b_stage_failure_locks_online():
    stage = {"return_code": 1, "termination": None}
    summary = runner._attach_evidence({"status": "gate_failed"})
    assert runner._stage_gate_allows_online(stage, summary, True) is False
    assert runner._stage_gate_allows_online(
        {"return_code": 0, "termination": None},
        runner._attach_evidence({"status": "measurement_complete"}),
        False,
    ) is False


def test_h2b_stage_failure_preserves_controlled_negative(tmp_path, monkeypatch):
    raw = _raw_fixture(tmp_path, monkeypatch)
    stage = runner._read_json(raw / "stage_summary.json")
    stage["status"] = "gate_failed"
    stage["error"] = "process_tree_rss_at_or_over_limit"
    _write_payload(raw / "stage_summary.json", stage)
    watchdog = runner._read_json(raw / "h2b_watchdog_summary.json")
    watchdog["status"] = "gate_failed"
    watchdog["error"] = "stage_gate_failed_before_online"
    watchdog["stage"]["return_code"] = 1
    watchdog["online"] = None
    for path in raw.glob("online_*"):
        path.unlink()
    watchdog["raw_artifacts"] = {
        name: runner._artifact(raw, name)
        for name in (
            "stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json", "stage_timeline.jsonl",
            "online_progress.jsonl", "online_stdout.txt", "online_summary.json", "online_timeline.jsonl",
            "stage_root_pid.json", "online_root_pid.json",
        )
    }
    _write_payload(raw / "h2b_watchdog_summary.json", watchdog)
    output = tmp_path / "controlled.json"
    assert runner._run_check(raw, output) == 1
    result = runner._read_json(output)
    assert result["pass"] is False
    assert result["measurements"] is None
    assert result["failure_measurements"]["online_not_run"] is True
    assert result["failure_measurements"]["stage"]["process_tree_peak_rss_bytes"] == 1_000_000
    assert "online_not_run" in result["problems"]


def test_h2b_raw_missing_key_is_controlled_failure(tmp_path, monkeypatch):
    raw = _raw_fixture(tmp_path, monkeypatch)
    value = runner._read_json(raw / "online_summary.json")
    del value["factor_audit"]["solve_residual_max"]
    _write_payload(raw / "online_summary.json", value)
    result = _read_result(raw)
    assert result["pass"] is False
    assert "factor_work" in result["problems"]


def test_h2b_checker_does_not_create_future_record(tmp_path, monkeypatch):
    raw = _raw_fixture(tmp_path, monkeypatch)
    assert _read_result(raw)["pass"] is True
    assert not (tmp_path / "h2b_block_smoother.json").exists()
