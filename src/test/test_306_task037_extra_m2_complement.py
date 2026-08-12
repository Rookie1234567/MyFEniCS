from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import benchmarks.run_task037_extra_h2b as h2b_runner
import benchmarks.run_task037_extra_m as m2_runner

from src.solvers.hcurl_h2b_m2_complement import (
    M2_HIGH_DIMENSION,
    M2_LOW_DIMENSION,
    M2_PATCH_DIMENSION,
    build_h2b_m2_cell_injection,
    build_h2b_m2_complement,
    measure_h2b_m2_source,
)
from src.solvers.hcurl_h2b_block_smoother import _p0_numeric_sha


def test_m2_runner_helper_ownership_and_cli(monkeypatch) -> None:
    """Exercise the M2-to-H2B helper bindings without entering a worker."""

    assert m2_runner.M2_TIMEOUT_SECONDS == 3_600.0
    assert m2_runner._lazy_h2a is h2b_runner._lazy_h2a
    assert m2_runner._h2b_build_b0_form is h2b_runner._build_b0_form
    assert m2_runner._h2b_expected_jit_options is h2b_runner._expected_jit_options
    assert m2_runner._h2b_p1_authority is h2b_runner._p1_authority
    assert m2_runner.H2B_R2_MANIFEST is h2b_runner.H2B_R2_MANIFEST
    assert m2_runner._p0_numeric_sha is _p0_numeric_sha
    assert callable(m2_runner._h2b_source_arrays)
    assert callable(m2_runner._h2b_residual_source_arrays)

    sentinel = object()
    monkeypatch.setattr(m2_runner, "_lazy_h2a", lambda: sentinel)
    assert m2_runner._lazy_h2a() is sentinel

    for argv in (
        ("m2-worker", "--run-dir", "/tmp/m2"),
        ("m2-watchdog", "--run-dir", "/tmp/m2"),
        ("m2-check", "--run-dir", "/tmp/m2", "--output", "/tmp/m2.json"),
    ):
        assert m2_runner._parser().parse_args(argv).command == argv[0]
    assert "m2_patch_rows.npy" in m2_runner._m2_recorded_artifacts(Path("/tmp/m2"))
    assert "stage_summary.json" in m2_runner._m2_recorded_artifacts(Path("/tmp/m2"))


def test_m2_watchdog_stage_gate_locks_or_allows_online(monkeypatch, tmp_path) -> None:
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    calls: list[str] = []

    online_compiler_pids: list[int] = []

    with monkeypatch.context() as strict:
        strict.setattr(m2_runner, "_m2_stage_summary_valid", lambda *_args: True)
        strict.setattr(m2_runner, "_m2_timeline_resource_valid", lambda *_args, **_kwargs: True)
        stage_process = {
            "return_code": 0,
            "termination": None,
            "processes_gone": True,
            "peak_rss_bytes": m2_runner.M2_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
        }
        assert not m2_runner._m2_stage_gate_valid(stage_process, {}, tmp_path, True)
        stage_process["peak_rss_bytes"] -= 1
        assert m2_runner._m2_stage_gate_valid(stage_process, {}, tmp_path, True)

    def monitor(_run_dir, phase, _command, _timeout, _limit):
        calls.append(phase)
        timeline = {
            "schema": h2b_runner.H2B_PROGRESS_SCHEMA,
            "phase": phase,
            "sample_kind": "worker",
            "elapsed_wall_seconds": 0.1,
            "root_pid": 1,
            "pids": [1],
            "process_count": 1,
            "rss_bytes": 100,
            "swap_bytes": 0,
            "all_status_readable": True,
            "compiler_descendant_pids": list(online_compiler_pids if phase == "m2" else []),
        }
        (_run_dir / f"{phase}_timeline.jsonl").write_text(
            json.dumps(timeline) + "\n",
            encoding="utf-8",
        )
        return {
            "phase": phase,
            "return_code": 0 if phase == "stage" else 0,
            "termination": None,
            "peak_rss_bytes": 100,
            "swap_bytes": 0,
            "observed_process_tree_pids": [],
        }

    monkeypatch.setattr(m2_runner, "_h2b_monitor_phase", monitor)
    monkeypatch.setattr(m2_runner, "_h2b_bounded_process_drain", lambda _value: {"gone": True})
    monkeypatch.setattr(m2_runner, "_process_gone", lambda _value: True)
    monkeypatch.setattr(m2_runner, "_clean_source", lambda: source)
    monkeypatch.setattr(m2_runner, "_read_json", lambda _path: {})
    monkeypatch.setattr(m2_runner, "_write_json", lambda *_args: None)
    monkeypatch.setattr(
        m2_runner,
        "_artifact",
        lambda _run_dir, name: {"path": name, "present": name == "m2_worker_summary.json"},
    )
    monkeypatch.setattr(m2_runner, "_m2_stage_gate_valid", lambda *_args: False)
    assert m2_runner._run_m2_watchdog(tmp_path / "stage-stop") == 1
    assert calls == ["stage"]

    calls.clear()
    monkeypatch.setattr(m2_runner, "_m2_stage_gate_valid", lambda *_args: True)
    assert m2_runner._run_m2_watchdog(tmp_path / "stage-pass") == 0
    assert calls == ["stage", "m2"]

    calls.clear()
    online_compiler_pids[:] = [1234]
    assert m2_runner._run_m2_watchdog(tmp_path / "online-compiler-stop") == 1
    assert calls == ["stage", "m2"]


def test_m2_online_cache_and_compiler_contract(monkeypatch, tmp_path) -> None:
    snapshot = [{"path": "module.so", "bytes": 3, "mtime_ns": 7, "sha256": "a" * 64}]
    monkeypatch.setattr(m2_runner, "_h2b_cache_snapshot", lambda _path: snapshot)
    monkeypatch.setattr(m2_runner, "_sha256_file", lambda _path: "b" * 64)
    monkeypatch.setattr(m2_runner, "_h2b_forms_match", lambda *_args: True)
    cache = {
        "before": snapshot,
        "after": snapshot,
        "unchanged": True,
        "form_jit_cache_hit": True,
        "c_source_regeneration": False,
        "compiler_descendant_pids": [],
    }
    measurement = {"cache": cache, "stage_manifest_sha256": "b" * 64}
    assert m2_runner._m2_online_cache_valid(measurement, {}, {}, tmp_path) is True
    assert m2_runner._m2_online_cache_valid(
        {"cache": dict(cache, compiler_descendant_pids=[1234]), "stage_manifest_sha256": "b" * 64},
        {},
        {},
        tmp_path,
    ) is False
    assert m2_runner._m2_online_cache_valid(
        {"cache": dict(cache, after=[]), "stage_manifest_sha256": "b" * 64},
        {},
        {},
        tmp_path,
    ) is False


def _m2_form_reuse_source() -> dict[str, object]:
    return {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _m2_form_reuse_form(code_state: str = "hit_no_new_decl_impl") -> dict[str, object]:
    return {
        "role": "b0",
        "ufl_signature": "ufl",
        "ufcx_signature": "ufcx",
        "module_name": "libffcx_forms_demo",
        "ffcx_signature_stem": "demo",
        "code_state": code_state,
        "jit_options": {"cache_dir": "/tmp/jit_cache", "cffi_extra_compile_args": []},
        "form_compiler_options": {"scalar_type": "complex128"},
        "proxy_identity": {"operator": "B0"},
        "element_signature": ["N1E", 6],
        "cache_files": [{"path": "module.so", "bytes": 3, "mtime_ns": 7, "sha256": "a" * 64}],
    }


def _m2_form_reuse_fixture(tmp_path):
    source = _m2_form_reuse_source()
    stage_form = _m2_form_reuse_form("cold_decl_impl_generated")
    online_form = _m2_form_reuse_form()
    cache = [{"path": "module.so", "bytes": 3, "mtime_ns": 7, "sha256": "a" * 64}]
    (tmp_path / "stage_summary.json").write_text("{}\n", encoding="utf-8")
    return source, stage_form, online_form, cache


def test_m2_form_reuse_sidecar_records_each_gate(monkeypatch, tmp_path) -> None:
    source, stage_form, online_form, cache = _m2_form_reuse_fixture(tmp_path)
    monkeypatch.setattr(m2_runner, "_h2b_forms_match", lambda *_args: True)

    sidecar = m2_runner._m2_write_form_reuse(
        tmp_path,
        source,
        {"form": stage_form},
        online_form,
        cache,
        cache,
    )
    assert sidecar["checks"] == {
        "code_state_hit": True,
        "cache_unchanged": True,
        "forms_match": True,
    }
    assert sidecar["all_pass"] is True
    assert m2_runner._evidence_valid(sidecar)
    assert json.loads((tmp_path / m2_runner.M2_FORM_REUSE_ARTIFACT).read_text())["all_pass"] is True

    for failure, key, form, after in (
        ("code", "code_state_hit", _m2_form_reuse_form("cold_decl_impl_generated"), cache),
        ("cache", "cache_unchanged", online_form, []),
        ("forms", "forms_match", online_form, cache),
    ):
        monkeypatch.setattr(m2_runner, "_h2b_forms_match", lambda *_args, ok=failure != "forms": ok)
        failed = m2_runner._m2_write_form_reuse(
            tmp_path,
            source,
            {"form": stage_form},
            form,
            cache,
            after,
        )
        assert failed["checks"][key] is False
        assert failed["all_pass"] is False


def test_m2_form_reuse_normalizes_fresh_nested_tuples(monkeypatch, tmp_path) -> None:
    source, stage_form, online_form, cache = _m2_form_reuse_fixture(tmp_path)
    stage_form["element_signature"] = ["N1E", 6, [["edge", [1, 2]]]]
    online_form["element_signature"] = ("N1E", 6, (("edge", (1, 2)),))
    seen: dict[str, object] = {}

    def match(stage, online, _run_dir):
        seen["stage"] = stage
        seen["online"] = online
        return stage["element_signature"] == online["element_signature"]

    monkeypatch.setattr(m2_runner, "_h2b_forms_match", match)
    sidecar = m2_runner._m2_write_form_reuse(
        tmp_path,
        source,
        {"form": stage_form},
        online_form,
        cache,
        cache,
    )
    assert seen["online"]["element_signature"] == stage_form["element_signature"]
    assert isinstance(seen["online"]["element_signature"][2], list)
    assert sidecar["online_form"]["element_signature"] == stage_form["element_signature"]
    assert sidecar["online_form"]["code_state"] != stage_form["code_state"]
    assert sidecar["checks"]["forms_match"] is True


def test_m2_checker_contract_rejects_tampered_sidecar(monkeypatch, tmp_path) -> None:
    source, stage_form, online_form, cache = _m2_form_reuse_fixture(tmp_path)
    monkeypatch.setattr(m2_runner, "_h2b_forms_match", lambda *_args: True)
    sidecar = m2_runner._m2_write_form_reuse(
        tmp_path,
        source,
        {"form": stage_form},
        online_form,
        cache,
        cache,
    )
    artifact = {"present": True, "sha256": "c" * 64}
    measurement = {
        "cache": {"before": cache, "after": cache},
        "stage_manifest_sha256": sidecar["stage_manifest_sha256"],
        "form_reuse": {
            "artifact_sha256": artifact["sha256"],
            "checks": sidecar["checks"],
            "all_pass": True,
        },
    }
    stage = {"form": stage_form}
    worker = {
        "source_at_start": source,
        "source_at_end": source,
        "form": online_form,
        "measurement": measurement,
    }
    watchdog = {
        "raw_artifacts": {m2_runner.M2_FORM_REUSE_ARTIFACT: artifact},
    }
    documents = {
        "m2_form_reuse.json": sidecar,
        "stage_summary.json": stage,
        "m2_worker_summary.json": worker,
        "m2_watchdog_summary.json": watchdog,
    }
    monkeypatch.setattr(m2_runner, "_read_json", lambda path: documents[path.name])
    monkeypatch.setattr(m2_runner, "_artifact", lambda _run_dir, name: artifact)
    monkeypatch.setattr(m2_runner, "_m2_recorded_artifacts", lambda _run_dir: watchdog["raw_artifacts"])
    monkeypatch.setattr(m2_runner, "_evidence_valid", lambda _value: True)
    monkeypatch.setattr(m2_runner, "_m2_stage_gate_valid", lambda *_args: True)
    monkeypatch.setattr(m2_runner, "_m2_stage_summary_valid", lambda *_args: True)
    monkeypatch.setattr(m2_runner, "_m2_online_cache_valid", lambda *_args: True)
    monkeypatch.setattr(m2_runner, "_h2b_p1_authority", lambda: {"p0": {}})
    accepted = m2_runner._m2_check_raw(tmp_path, source)
    assert accepted["checks"]["form_reuse"] is True

    tampered = dict(sidecar, checks=dict(sidecar["checks"], forms_match=False), all_pass=True)
    documents["m2_form_reuse.json"] = tampered
    rejected = m2_runner._m2_check_raw(tmp_path, source)
    assert rejected["checks"]["form_reuse"] is False


def test_m2_checker_source_scope_is_fail_closed() -> None:
    source = {
        "finite": True,
        "rho_scope": "complete_882_patch_rows",
        "global_rho_scope": "full_global_rows_diagnostic_only",
        "projected_high_closure_relative": 1.0e-14,
        "action_closure_relative": 2.0e-14,
        "full_space_rho_star": 0.2,
        "full_space_rho_unit": 0.3,
    }
    assert m2_runner._m2_source_gate_valid(source, 0.7)
    wrong_scope = dict(source, rho_scope="full_global_rows")
    assert not m2_runner._m2_source_gate_valid(wrong_scope, 0.7)
    nonfinite_projected = dict(source, projected_high_closure_relative=float("inf"))
    assert not m2_runner._m2_source_gate_valid(nonfinite_projected, 0.7)


class _Solve:
    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        return np.linalg.solve(self.matrix, rhs)


def test_m2_fixed_dimensions_and_deterministic_qr_carrier() -> None:
    assert (M2_PATCH_DIMENSION, M2_LOW_DIMENSION, M2_HIGH_DIMENSION) == (
        882,
        300,
        582,
    )
    injection = np.asarray(
        (
            (1.0 + 0.0j, 0.2 - 0.1j),
            (0.1 + 0.2j, 1.1 + 0.0j),
            (0.3 + 0.0j, -0.4 + 0.1j),
            (0.2 - 0.2j, 0.5 + 0.3j),
            (-0.1 + 0.4j, 0.7 - 0.2j),
            (0.9 + 0.1j, -0.2 + 0.5j),
        ),
        dtype=np.complex128,
        order="C",
    )
    first = build_h2b_m2_complement(
        injection,
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    second = build_h2b_m2_complement(
        injection.copy(),
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    assert first.audit["rank"] == 2
    assert first.audit["q_high_dimension"] == 4
    assert first.audit["rank_threshold"] == (
        first.audit["rank_threshold_factor"] * first.audit["injection_2_norm"]
    )
    assert first.audit["q_orthogonality_error"] <= 1.0e-12
    assert first.audit["split_reconstruction_error"] <= 1.0e-11
    assert np.array_equal(first.q_low, second.q_low)
    assert np.array_equal(first.q_high, second.q_high)
    assert first.q_low.flags.writeable is False
    assert first.q_high.flags.writeable is False
    assert first.retained_transform_bytes == first.q_low.nbytes + first.q_high.nbytes
    assert first.audit["retained_transform_bytes"] == first.retained_transform_bytes
    assert first.audit["dense_qh_retained"] is True
    assert first.audit["dense_qh_count"] == 1


def test_m2_constrained_cell_injection_uses_orientation_and_mpc_once() -> None:
    calls: list[tuple[int, int]] = []

    def local_apply(values: np.ndarray, cell_info: int) -> np.ndarray:
        calls.append((cell_info, values.size))
        return np.asarray(
            (values[0], values[1], values[0] - values[1], 2.0 * values[1]),
            dtype=np.complex128,
        )

    def p4_lift(values: np.ndarray) -> None:
        values[1] = (0.37 + 0.11j) * values[0]

    def p6_lift(values: np.ndarray) -> None:
        values[3] = (-0.2 + 0.4j) * values[0]

    injection = build_h2b_m2_cell_injection(
        patch_rows=np.asarray((20, 21, 22, 23), dtype=np.int64),
        p4_global_rows=np.asarray((10, 11), dtype=np.int64),
        p4_cell_dofs=np.asarray((0, 1), dtype=np.int32),
        p6_global_rows=np.asarray((20, 21, 22, 23), dtype=np.int64),
        p6_cell_dofs=np.asarray((0, 1, 2, 3), dtype=np.int32),
        p4_local_rows=2,
        p6_local_rows=4,
        cell_info=7,
        local_apply=local_apply,
        p4_lift=p4_lift,
        p6_lift=p6_lift,
    )
    assert injection.shape == (4, 2)
    assert np.all(np.isfinite(injection))
    assert calls == [(7, 2), (7, 2)]
    assert np.array_equal(
        injection[:, 0],
        np.asarray((1.0, 0.37 + 0.11j, 1.0 - (0.37 + 0.11j), (-0.2 + 0.4j)), dtype=np.complex128),
    )


def test_m2_full_space_source_oracle_binds_projected_patch_action() -> None:
    injection = np.asarray(
        (
            (1.0 + 0.0j, 0.0 + 0.0j),
            (0.0 + 0.0j, 1.0 + 0.0j),
            (1.0 + 0.0j, 1.0 + 0.0j),
            (0.2 + 0.1j, -0.3 + 0.2j),
            (0.5 - 0.2j, 0.7 + 0.1j),
            (-0.4 + 0.3j, 0.2 - 0.6j),
        ),
        dtype=np.complex128,
        order="C",
    )
    carrier = build_h2b_m2_complement(
        injection,
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    operator = np.asarray(
        (
            (3.0, 0.2, 0.0, 0.1, 0.0, 0.0),
            (0.2, 2.7, 0.1, 0.0, 0.0, 0.0),
            (0.0, 0.1, 2.5, 0.0, 0.2, 0.0),
            (0.1, 0.0, 0.0, 2.2, 0.0, 0.3),
            (0.0, 0.0, 0.2, 0.0, 2.9, 0.1),
            (0.0, 0.0, 0.0, 0.3, 0.1, 2.4),
        ),
        dtype=np.complex128,
        order="C",
    )
    high_matrix = np.ascontiguousarray(carrier.q_high.conj().T @ operator @ carrier.q_high)
    factor = _Solve(high_matrix)
    rhs = np.asarray((1.0 + 0.3j, -0.4 + 0.2j, 0.7 - 0.1j, 0.1 + 0.6j, -0.3j, 0.9 + 0.2j), dtype=np.complex128)
    first = measure_h2b_m2_source(
        rhs,
        np.arange(6, dtype=np.int64),
        carrier,
        factor,
        lambda values: operator @ values,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    second = measure_h2b_m2_source(
        rhs,
        np.arange(6, dtype=np.int64),
        carrier,
        factor,
        lambda values: operator @ values,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    assert first["action_closure_relative"] <= 1.0e-11
    assert first["projected_high_closure_relative"] <= 1.0e-11
    assert first["rho_scope"] == "complete_6_patch_rows"
    assert first["global_rho_scope"] == "full_global_rows_diagnostic_only"
    assert np.isfinite(first["full_space_rho_star"])
    assert first["correction_sha256"] == second["correction_sha256"]
    assert first["action_sha256"] == second["action_sha256"]
    assert abs(
        first["p4_low_energy_fraction"]
        + first["high_complement_energy_fraction"]
        - 1.0
    ) <= 1.0e-14
    assert np.array_equal(first["correction"], second["correction"])

    bad_action = lambda values: operator @ values + carrier.q_low @ np.asarray(
        (0.25 + 0.0j, -0.17 + 0.0j), dtype=np.complex128
    )
    bad = measure_h2b_m2_source(
        rhs,
        np.arange(6, dtype=np.int64),
        carrier,
        factor,
        bad_action,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    assert bad["projected_high_closure_relative"] <= 1.0e-11
    assert bad["action_closure_relative"] > 1.0e-6


def test_m2_rho_gate_uses_patch_rows_not_off_patch_spill() -> None:
    injection = np.asarray(
        (
            (1.0 + 0.0j, 0.0 + 0.0j),
            (0.0 + 0.0j, 1.0 + 0.0j),
            (1.0 + 0.0j, 1.0 + 0.0j),
            (0.2 + 0.1j, -0.3 + 0.2j),
            (0.5 - 0.2j, 0.7 + 0.1j),
            (-0.4 + 0.3j, 0.2 - 0.6j),
        ),
        dtype=np.complex128,
        order="C",
    )
    carrier = build_h2b_m2_complement(
        injection,
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    operator = np.diag(
        np.asarray((2.0, 2.2, 2.4, 2.6, 2.8, 3.0), dtype=np.complex128)
    )
    high_matrix = np.ascontiguousarray(
        carrier.q_high.conj().T @ operator @ carrier.q_high
    )
    factor = _Solve(high_matrix)
    rows = np.arange(1, 7, dtype=np.int64)
    rhs = np.zeros(8, dtype=np.complex128)
    rhs[rows] = np.asarray(
        (1.0 + 0.3j, -0.4 + 0.2j, 0.7 - 0.1j, 0.1 + 0.6j, -0.3j, 0.9 + 0.2j),
        dtype=np.complex128,
    )
    rhs[0] = 1.7 - 0.2j
    rhs[-1] = -0.8 + 0.4j

    def action_without_spill(values: np.ndarray) -> np.ndarray:
        result = np.zeros_like(values)
        result[rows] = operator @ values[rows]
        return result

    def action_with_spill(values: np.ndarray) -> np.ndarray:
        result = action_without_spill(values)
        result[0] = 4.0 + 0.5j
        result[-1] = -3.0 + 0.25j
        return result

    base = measure_h2b_m2_source(
        rhs,
        rows,
        carrier,
        factor,
        action_without_spill,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    spill = measure_h2b_m2_source(
        rhs,
        rows,
        carrier,
        factor,
        action_with_spill,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    assert np.isclose(base["full_space_rho_star"], spill["full_space_rho_star"])
    assert np.isclose(base["full_space_rho_unit"], spill["full_space_rho_unit"])
    assert base["global_action_norm"] != spill["global_action_norm"]
    assert base["global_rho_star"] != spill["global_rho_star"]
