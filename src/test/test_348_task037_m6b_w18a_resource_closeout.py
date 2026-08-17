"""Focused pure contracts for the W18A watchdog wrapper."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w18_nested_auxiliary_pc as w18
from src.solvers.hcurl_h2b_m5_coercive import _array_sha256
from src.solvers.persistent_residual_one_vector import (
    repeat_rank_one_projection,
)
from src.test.test_345_task037_m6b_w17a_resource_closeout import (
    _action_audit,
    _dtn,
    _materialization,
    _outer,
    _physical,
    _shifted,
    _source,
    _timeline,
    _write_array,
    _write_sparse,
)


EXPECTED_SOURCE_SHA = "a" * 40
CHECKER_SOURCE_SHA = "e" * 40


def test_w18a_watchdog_constants_command_and_inventory() -> None:
    prediction = runner._m6b_w18a_predicted_live_set()
    command = runner._m6b_w18a_worker_command(
        Path("run"),
        Path("w7.json"),
        Path("w7_raw"),
        Path("factor.json"),
        Path("jit"),
        EXPECTED_SOURCE_SHA,
    )
    raw = runner._m6b_w16a_raw_artifacts(Path("raw"), mode="w18a")
    watchdog = runner._m6b_w16a_watchdog_artifacts(
        Path("watchdog"), mode="w18a"
    )

    assert runner.M6B_W18A_WATCHDOG_SCHEMA.endswith("w18a.watchdog.v1")
    assert runner.M6B_W18A_WATCHDOG_SUMMARY_FILENAME == "w18a_watchdog_summary.json"
    assert runner.M6B_W18A_TIMEOUT_SECONDS == 3600.0
    assert runner.M6B_W18A_WATCHDOG_RSS_LIMIT_BYTES == 1_950_000_000
    assert runner.M6B_W18A_FORMAL_RSS_LIMIT_BYTES == 1_950_000_000
    assert prediction["bytes"] == 1_734_993_014
    assert prediction["gate"] is True
    assert command[3] == "m6b-w18a-nested-auxiliary-diagnostic"
    assert len(raw) == 46
    assert len(watchdog) == 3
    assert watchdog[0]["path"] == "w18a_nested_auxiliary_timeline.jsonl"


def test_w18a_watchdog_wrapper_forces_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_shared(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w16a_watchdog", fake_shared)
    result = runner._run_m6b_w18a_watchdog(
        Path("run"),
        Path("watchdog"),
        Path("w7.json"),
        Path("w7_raw"),
        Path("factor.json"),
        Path("jit"),
        EXPECTED_SOURCE_SHA,
    )

    assert result == 17
    assert observed["kwargs"] == {"mode": "w18a"}


@pytest.mark.parametrize("worker_return_code", [0, 1])
def test_w18a_worker_completion_keeps_physical_screen_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_return_code: int,
) -> None:
    import benchmarks.run_task037_extra_h2b as h2b

    w7_compact = tmp_path / "w7.json"
    w7_compact.write_text("{}", encoding="utf-8")
    w7_raw_dir = tmp_path / "w7_raw"
    w7_raw_dir.mkdir()
    factor_manifest = tmp_path / "factor" / "manifest.json"
    factor_manifest.parent.mkdir()
    factor_manifest.write_text("{}", encoding="utf-8")
    jit_cache = tmp_path / "jit"
    jit_cache.mkdir()
    run_dir = tmp_path / "run"
    watchdog_dir = tmp_path / "watchdog"
    captured: dict[str, object] = {}

    source = {
        "source_commit_full_sha": EXPECTED_SOURCE_SHA,
        "tracked_source_dirty": False,
    }
    monkeypatch.setattr(runner, "_m6b_w16a_factor_authority", lambda *_: {})
    monkeypatch.setattr(runner, "_m6b_w9a_load_w7", lambda *_: {})
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda *_: True)
    monkeypatch.setattr(h2b, "_light_source", lambda: dict(source))
    monkeypatch.setattr(
        h2b,
        "_monitor_phase",
        lambda *_args: {
            "return_code": worker_return_code,
            "termination": None,
        },
    )
    monkeypatch.setattr(h2b, "_bounded_process_drain", lambda *_: {"gone": True})
    monkeypatch.setattr(
        runner,
        "_m6b_w8a_timeline_valid",
        lambda *_args, **_kwargs: {"pass": True},
    )
    monkeypatch.setattr(runner, "_write_json", lambda _path, value: captured.update(value))

    result = runner._run_m6b_w18a_watchdog(
        run_dir,
        watchdog_dir,
        w7_compact,
        w7_raw_dir,
        factor_manifest,
        jit_cache,
        EXPECTED_SOURCE_SHA,
    )

    assert result == 0
    assert captured["status"] == (
        "measurement_complete" if worker_return_code == 0 else "gate_failed"
    )
    assert captured["process"]["return_code"] == worker_return_code
    assert captured["process"]["termination"] is None
    assert captured["drain"]["gone"] is True
    assert captured["formal_pass"] is False
    assert captured["pde_pass"] is False
    assert captured["official_rta"] is False
    assert captured["physical_screen_unlocked"] is False
    assert captured["physical_screen_locked"] is True
    assert captured["resource_limits"] == {
        "timeout_seconds": 3600.0,
        "watchdog_rss_bytes": 1_950_000_000,
        "completion_peak_rss_bytes": 1_950_000_000,
        "swap_bytes": 0,
    }


def test_w18a_watchdog_parser_and_main_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_watchdog(*args):
        observed["args"] = args
        return 23

    monkeypatch.setattr(runner, "_run_m6b_w18a_watchdog", fake_watchdog)
    result = runner.main(
        [
            "m6b-w18a-watchdog",
            "--run-dir",
            "run",
            "--watchdog-dir",
            "watchdog",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7_raw",
            "--shifted-factor-manifest",
            "factor.json",
            "--jit-cache-source",
            "jit",
            "--expected-source-sha",
            EXPECTED_SOURCE_SHA,
        ]
    )

    assert result == 23
    assert [Path(value).name for value in observed["args"][:-1]] == [
        "run",
        "watchdog",
        "w7.json",
        "w7_raw",
        "factor.json",
        "jit",
    ]
    assert observed["args"][-1] == EXPECTED_SOURCE_SHA


def _w18a_outer_audit(raw_dir: Path, repeat_index: int) -> dict[str, object]:
    root = raw_dir / "outer_scratch" / f"repeat{repeat_index}"
    rows = runner.M6B_GLOBAL_ROWS
    vector_bytes = rows * 16
    v_audit = {
        "path": str((root / "v_basis.bin").resolve()),
        "rows": rows,
        "dtype": "complex128",
        "capacity": 3,
        "written_count": 3,
        "read_count": 6,
        "write_count": 3,
        "allocated_bytes": 3 * vector_bytes,
        "bytes_read": 6 * vector_bytes,
        "bytes_written": 3 * vector_bytes,
        "mmap": False,
    }
    z_audit = {
        "path": str((root / "z_basis.bin").resolve()),
        "rows": rows,
        "dtype": "complex128",
        "capacity": 2,
        "written_count": 2,
        "read_count": 3,
        "write_count": 2,
        "allocated_bytes": 2 * vector_bytes,
        "bytes_read": 3 * vector_bytes,
        "bytes_written": 2 * vector_bytes,
        "mmap": False,
    }
    audit = {
        "algorithm": "right_flexible_gmres",
        "rows": rows,
        "dtype": "complex128",
        "max_steps": 2,
        "iterations": 2,
        "checkpoint_iterations": [1, 2],
        "checkpoint_count": 2,
        "observer_count": 2,
        "action_count": 4,
        "pc_count": 2,
        "initial_action_count": 0,
        "orthogonalization_passes": 2,
        "mmap": False,
        "basis_in_memory": False,
        "scratch_mmap": False,
        "scratch_basis_in_memory": False,
        "bounded_full_vector_gate": True,
        "retained_full_vector_count": 1,
        "retained_full_vector_bytes": vector_bytes,
        "bounded_full_vector_bytes": 12 * vector_bytes,
        "bounded_full_vector_buffer_count": 12,
        "checkpoint_set_complete": True,
        "scratch_bytes": 5 * vector_bytes,
        "v_basis": v_audit,
        "z_basis": z_audit,
        "scratch_paths": {
            "v_basis": v_audit["path"],
            "z_basis": z_audit["path"],
        },
    }
    _write_sparse(root / "v_basis.bin", v_audit["allocated_bytes"])
    _write_sparse(root / "z_basis.bin", z_audit["allocated_bytes"])
    return audit


def _w18a_inner_record(
    raw_dir: Path, repeat_index: int, apply_index: int
) -> dict[str, object]:
    root = (
        raw_dir
        / "outer_scratch"
        / f"repeat{repeat_index}"
        / "inner"
        / f"apply_{apply_index:02d}"
    )
    solution = _write_array(
        root / "solution.npy",
        np.asarray([apply_index, repeat_index, 0, 0], dtype=np.complex128),
    )
    cycles: dict[str, object] = {}
    scratch_paths: dict[str, object] = {}
    for cycle in (20, 40):
        cycle_root = root / f"cycle{cycle}"
        cycle_paths = {
            role: str((cycle_root / f"{role}.bin").resolve())
            for role in ("v_basis", "z_basis")
        }
        for path in cycle_paths.values():
            _write_sparse(Path(path), 16)
        cycle_audit = {
            "v_basis": {"allocated_bytes": 16},
            "z_basis": {"allocated_bytes": 16},
            "scratch_paths": cycle_paths,
        }
        cycles[f"cycle{cycle}"] = cycle_audit
        scratch_paths[f"cycle{cycle}"] = cycle_paths
    return {
        "schema": w18.W18A_INNER_SCHEMA,
        "algorithm": "fgmres_right_shifted_beta1_composed_fixed20_plus20",
        "apply_index": apply_index,
        "initial_solution_provided": False,
        "initial_action_count": 0,
        "cycle20_relative_residual": 0.009,
        "cycle40_relative_residual": 0.008,
        "final_relative_residual": 0.008,
        "finite": True,
        "global_action_count": 43,
        "pc_apply_count": 40,
        "shifted_action_count": 83,
        "solution_sha256": solution["array_sha256"],
        "solution_artifact": solution,
        "scratch_paths": scratch_paths,
        **cycles,
    }


def _w18a_action_audit(
    factor_audit: dict[str, int], repeats: list[dict[str, object]]
) -> dict[str, object]:
    audit = deepcopy(_action_audit(factor_audit))
    audit["retained_authority_vector_roles"] = ["w7_target_residual"]
    audit["lifecycle_events"] = [
        "dtn_constructed",
        "auxiliary_constructed",
        "auxiliary_repeat_1",
        "auxiliary_repeat_2",
        "auxiliary_released",
        "physical_constructed",
        "physical_apply_1",
        "physical_apply_2",
        "physical_apply_3",
        "physical_apply_4",
        "physical_released",
        "dtn_released",
    ]
    audit.update(
        {
            "outer_auxiliary_action_count": 8,
            "outer_pc_apply_count": 4,
            "inner_global_shifted_action_count": 172,
            "global_auxiliary_action_count": 172,
            "global_shifted_action_count": 172,
            "local_pc_apply_count": 160,
            "local_exact_shifted_action_count": 160,
            "local_exact_shifted_volume_action_count": 160,
            "shifted_action_total_count": 340,
            "shifted_action_count": 340,
            "auxiliary_dtn_action_count": 8,
            "physical_volume_action_count": 4,
            "physical_dtn_action_count": 4,
            "total_dtn_action_count": 12,
            "physical_action_count": 4,
        }
    )
    construction_shifted = _shifted(0)
    construction_shifted.pop("materialization_identity")
    audit["auxiliary_construction"]["shifted_action"] = construction_shifted
    audit["auxiliary_construction"]["shifted_action"].update(
        {
            "last_packed_coefficient_bytes": 0,
            "last_packed_coefficient_entry_count": 0,
            "last_packed_coefficient_shapes": [],
            "per_apply_bounded_temporary_bytes": 0,
        }
    )
    shifted_final = _shifted(340)
    shifted_final.pop("materialization_identity")
    shifted_final.update(
        {
            "last_packed_coefficient_bytes": 3_564_288,
            "last_packed_coefficient_entry_count": 222_768,
            "last_packed_coefficient_shapes": [[252, 884]],
            "per_apply_bounded_temporary_bytes": 3_564_288,
        }
    )
    audit["auxiliary_final_counts"] = {
        "outer": [deepcopy(run["outer_audit"]) for run in repeats],
        "dtn": _dtn(8),
        "shifted_action": shifted_final,
    }
    physical = _physical()
    physical.pop("materialization_identity")
    audit["physical_instances"] = [
        {
            "physical": physical | {"apply_count": 4},
            "outer": _outer(4),
            "dtn": _dtn(12),
            "bridge": {"forward_apply_count": 4, "fixed_work_vectors": 2,
                       "per_apply_vec_creation": 0},
        }
    ]
    return audit


def _w18a_formal_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    import benchmarks.run_task037_extra_h2b as h2b

    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 4)
    raw_dir = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw_dir.mkdir()
    watchdog_dir.mkdir()
    factor_path = tmp_path / "factor" / "manifest.json"
    factor_audit = {
        "beta": 1.0,
        "cell_count": 252,
        "factor_count": 84,
        "factor_order": 882,
        "factor_payload_bytes": 123,
        "finite": True,
        "retained_total_bytes": 456,
        "retained_total_gate": True,
        "full_dense_patch_matrix_retained": False,
        "ordinary_default_changed": False,
        "materialization_identity": _materialization(),
    }
    factor_path.parent.mkdir()
    factor_path.write_text(json.dumps({"audit": factor_audit}), encoding="utf-8")
    factor = {
        "path": str(factor_path.resolve()),
        "present": True,
        "bytes": factor_path.stat().st_size,
        "sha256": "b" * 64,
        "source_commit_full_sha": "d" * 40,
        "beta": 1.0,
        "audit": deepcopy(factor_audit),
        "factor_compiler": {"version_line": "fixture"},
    }
    residual = np.asarray([1, 0, 0, 0], dtype=np.complex128)
    w7 = {
        "compact": {"path": "w7.json", "file_sha256": "c" * 64},
        "raw_dir": "w7_raw",
        "residual": residual.copy(),
        "residual_artifact": {
            "path": "m6b_iter400_residual.npy",
            "bytes": residual.nbytes,
            "file_sha256": "d" * 64,
            "array_sha256": _array_sha256(residual),
        },
    }
    source = _source()
    monkeypatch.setattr(runner, "_m6b_w9a_load_w7", lambda *_: deepcopy(w7))
    monkeypatch.setattr(
        runner, "_m6b_w16a_factor_authority", lambda *_: deepcopy(factor)
    )
    monkeypatch.setattr(runner, "_m6b_w16a_jit_valid", lambda *_: True)
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda *_: True)
    monkeypatch.setattr(runner, "_m6b_w6a_runtime_valid", lambda *_args, **_kw: True)
    monkeypatch.setattr(runner, "_m6b_expected_p6", lambda *_: True)
    monkeypatch.setattr(h2b, "_light_source", lambda: deepcopy(source))

    repeats: list[dict[str, object]] = []
    checkpoint_artifacts: list[dict[str, object]] = []
    physical_outputs: dict[str, object] = {}
    rho1_t = w18.W18A_RHO1_ANCHOR / np.sqrt(1 - w18.W18A_RHO1_ANCHOR**2)
    p_values = {
        1: np.asarray([1, rho1_t, 0, 0], dtype=np.complex128),
        2: np.asarray([1, 4 / 3, 0, 0], dtype=np.complex128),
    }
    for repeat_index in (1, 2):
        repeat_checkpoints: dict[str, object] = {}
        inner_records = [
            _w18a_inner_record(raw_dir, repeat_index, apply_index)
            for apply_index in (1, 2)
        ]
        outer_audit = _w18a_outer_audit(raw_dir, repeat_index)
        for iteration in (1, 2):
            base = raw_dir / "outer_checkpoints" / f"repeat{repeat_index}"
            solution = np.asarray([iteration, 0, 0, 0], dtype=np.complex128)
            outer_action = 0.992 * residual
            residual_value = 0.008 * residual
            descriptors = {
                "solution": _write_array(
                    base / f"m6b_iter{iteration}_solution.npy", solution
                ),
                "outer_action": _write_array(
                    base / f"m6b_iter{iteration}_outer_action.npy", outer_action
                ),
                "residual": _write_array(
                    base / f"m6b_iter{iteration}_residual.npy", residual_value
                ),
                "rhs": _write_array(
                    base / f"m6b_iter{iteration}_rhs.npy", residual
                ),
            }
            for descriptor in descriptors.values():
                descriptor["sha256"] = descriptor.pop("file_sha256")
            checkpoint = {
                "iteration": iteration,
                "finite": True,
                "true_relative_residual": 0.008,
                "solution_sha256": descriptors["solution"]["array_sha256"],
                "action_sha256": descriptors["outer_action"]["array_sha256"],
                "solution_relative_difference": 0.0,
                "action_relative_difference": 0.0,
                "residual_closure": 0.0,
                "artifacts": descriptors,
            }
            repeat_checkpoints[str(iteration)] = checkpoint
            checkpoint_artifacts.append(
                {
                    "repeat_index": repeat_index,
                    "checkpoints": {
                        str(iteration): {"artifacts": descriptors}
                    },
                }
            )
            p_name = f"w18a_p_repeat{repeat_index}_checkpoint{iteration}.npy"
            p_descriptor = _write_array(raw_dir / p_name, p_values[iteration])
            physical_outputs[f"repeat{repeat_index}_checkpoint{iteration}"] = p_descriptor
        measurements = {
            str(iteration): {
                **repeat_rank_one_projection(
                    residual,
                    p_values[iteration],
                    block_size=runner.M6B_W11A_BLOCK_SIZE,
                    schema=runner.M6B_W18A_SCHEMA,
                ),
                "checkpoint": iteration,
            }
            for iteration in (1, 2)
        }
        repeats.append(
            {
                "repeat_index": repeat_index,
                "outer_audit": outer_audit,
                "inner_records": inner_records,
                "checkpoints": repeat_checkpoints,
                "measurements": measurements,
            }
        )
    checkpoint_artifacts = [
        {
            "repeat_index": repeat_index,
            "checkpoints": repeats[repeat_index - 1]["checkpoints"],
        }
        for repeat_index in (1, 2)
    ]
    action_audit = _w18a_action_audit(factor_audit, repeats)
    core_summary = {
        "schema": runner.M6B_W18A_SCHEMA,
        "fixed_identity": deepcopy(w18.W18A_FIXED_IDENTITY),
        "repeats": repeats,
        "action_counts": deepcopy(w18.W18A_ACTION_COUNTS),
        "architecture": deepcopy(w18.W18A_ARCHITECTURE),
        "lifecycle": {
            **deepcopy(w18.W18A_LIFECYCLE),
            "events": action_audit["lifecycle_events"],
            "auxiliary_physical_context_overlap": False,
            "release_between_repeats": False,
        },
        "prediction": runner._m6b_w18a_predicted_live_set(),
        "physical_identity": {
            str(iteration): {
                "first_sha256": physical_outputs[
                    f"repeat1_checkpoint{iteration}"
                ]["array_sha256"],
                "second_sha256": physical_outputs[
                    f"repeat2_checkpoint{iteration}"
                ]["array_sha256"],
                "sha256_equal": True,
                "relative_difference": 0.0,
            }
            for iteration in (1, 2)
        },
        "artifacts": {
            "outer_checkpoints": checkpoint_artifacts,
            "physical_outputs": physical_outputs,
        },
        "action_audit": action_audit,
        "checks": {},
        "problems": [],
    }
    assert set(core_summary) == {
        "schema",
        "fixed_identity",
        "repeats",
        "action_counts",
        "architecture",
        "lifecycle",
        "prediction",
        "physical_identity",
        "artifacts",
        "action_audit",
        "checks",
        "problems",
    }
    assert set(action_audit["auxiliary_final_counts"]) == {
        "outer",
        "dtn",
        "shifted_action",
    }
    assert "bridge" not in action_audit["auxiliary_final_counts"]
    report = w18.evaluate_w18a_action_gate(core_summary)
    assert report["pass"] is True, report
    core_summary["checks"] = {
        **report["checks"],
        "source": True,
        "cache": True,
        "execution": True,
    }
    summary = {
        "schema": runner.M6B_W18A_SCHEMA,
        "phase": runner.M6B_W18A_PHASE,
        "status": "action_gate_pass",
        "classification": "W18A_NESTED_AUXILIARY_PASS",
        "w18a_pass": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w18a_formal_candidate": True,
        "physical_screen_locked": True,
        "physical_screen_candidate": False,
        "scope": runner._m6b_w18a_scope(),
        "authority": {
            "w7": deepcopy(w7["compact"]),
            "w7_raw_dir": w7["raw_dir"],
            "w7_residual_artifact": deepcopy(w7["residual_artifact"]),
            "factor_manifest": deepcopy(factor),
        },
        "runtime_identity": {"compiler": deepcopy(factor["factor_compiler"])},
        "p6": {"fixture": True},
        "jit_cache": {"fixture": True},
        "predicted_live_set": runner._m6b_w18a_predicted_live_set(),
        "architecture": deepcopy(core_summary["architecture"]),
        "action_audit": action_audit,
        "core": core_summary,
        "checks": {**core_summary["checks"], "source": True, "cache": True, "execution": True},
        "error": None,
        "source_at_start": deepcopy(source),
        "source_at_end": deepcopy(source),
    }
    progress_path = raw_dir / runner.M6B_W18A_PROGRESS_FILENAME
    progress_path.write_text(
        "".join(
            json.dumps(
                {
                    "schema": f"{runner.M6B_W18A_SCHEMA}.progress.v1",
                    "phase": runner.M6B_W18A_PHASE,
                    "event": event,
                }
            )
            + "\n"
            for event in runner.M6B_W18A_EVENTS
        ),
        encoding="utf-8",
    )
    summary_path = raw_dir / runner.M6B_W18A_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    timeline_path = watchdog_dir / f"{runner.M6B_W18A_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W18A_PHASE,
                "rss_bytes": 1000,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    timeline = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W18A_PHASE
    )
    (watchdog_dir / f"{runner.M6B_W18A_PHASE}_stdout.txt").write_text(
        "fixture\n", encoding="utf-8"
    )
    (watchdog_dir / f"{runner.M6B_W18A_PHASE}_root_pid.json").write_text(
        '{"pid":1}\n', encoding="utf-8"
    )
    watchdog = {
        "schema": runner.M6B_W18A_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W18A_PHASE,
        "status": "measurement_complete",
        "process": {
            "return_code": 0,
            "termination": None,
            "peak_rss_bytes": 1000,
            "swap_bytes": 0,
        },
        "drain": {"gone": True},
        "source_at_start": deepcopy(source),
        "source_at_end": deepcopy(source),
        "source_end_clean": True,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W18A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W18A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W18A_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(raw_dir.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "command": runner._m6b_w18a_worker_command(
            raw_dir,
            runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_W7_RAW_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_JIT_RELATIVE_PATH,
            EXPECTED_SOURCE_SHA,
        ),
        "timeline": timeline,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "physical_screen_unlocked": False,
        "physical_screen_locked": True,
    }
    watchdog["artifact_inventory"] = {
        "raw": runner._m6b_w16a_raw_artifacts(raw_dir, mode="w18a"),
        "watchdog": runner._m6b_w16a_watchdog_artifacts(
            watchdog_dir, mode="w18a"
        ),
    }
    watchdog["worker_summary"] = watchdog["artifact_inventory"]["raw"][0]
    watchdog_path = watchdog_dir / runner.M6B_W18A_WATCHDOG_SUMMARY_FILENAME
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    return {
        "raw": raw_dir,
        "watchdog": watchdog_dir,
        "summary_path": summary_path,
        "watchdog_summary": watchdog_path,
        "timeline_path": timeline_path,
    }


def _refresh_w18a_fixture(fixture: dict[str, object]) -> None:
    raw_dir = fixture["raw"]
    watchdog_dir = fixture["watchdog"]
    summary_path = fixture["summary_path"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    watchdog_path = fixture["watchdog_summary"]
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    timeline = runner._m6b_w8a_timeline_valid(
        fixture["timeline_path"], phase=runner.M6B_W18A_PHASE
    )
    watchdog["timeline"] = timeline
    watchdog["artifact_inventory"] = {
        "raw": runner._m6b_w16a_raw_artifacts(raw_dir, mode="w18a"),
        "watchdog": runner._m6b_w16a_watchdog_artifacts(
            watchdog_dir, mode="w18a"
        ),
    }
    watchdog["worker_summary"] = watchdog["artifact_inventory"]["raw"][0]
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )


def test_w18a_formal_gate_passes_and_checker_unlocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _w18a_formal_fixture(tmp_path, monkeypatch)
    gate = runner._m6b_w18a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["pass"] is True, gate["checks"]
    summary = json.loads(fixture["summary_path"].read_text(encoding="utf-8"))
    action_audit = summary["action_audit"]
    shifted_construction = action_audit["auxiliary_construction"]["shifted_action"]
    shifted_final = action_audit["auxiliary_final_counts"]["shifted_action"]
    assert shifted_construction["last_packed_coefficient_bytes"] == 0
    assert shifted_construction["last_packed_coefficient_entry_count"] == 0
    assert shifted_construction["last_packed_coefficient_shapes"] == []
    assert shifted_final["last_packed_coefficient_bytes"] == 3_564_288
    assert shifted_final["last_packed_coefficient_entry_count"] == 222_768
    assert shifted_final["last_packed_coefficient_shapes"] == [[252, 884]]
    output = tmp_path / "closeout.json"
    assert (
        runner._run_m6b_w18a_check(
            fixture["raw"], fixture["watchdog_summary"], output, EXPECTED_SOURCE_SHA
        )
        == 0
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["classification"] == "W18A_FORMAL_ACTION_GATE_PASS"
    assert record["physical_screen_unlocked"] is True
    assert "records" not in record["watchdog"]
    with pytest.raises(FileExistsError):
        runner._run_m6b_w18a_check(
            fixture["raw"], fixture["watchdog_summary"], output, EXPECTED_SOURCE_SHA
        )


def test_w18a_checker_source_sha_is_separate_from_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benchmarks.run_task037_extra_h2b as h2b

    fixture = _w18a_formal_fixture(tmp_path, monkeypatch)
    checker_source = {
        "source_commit_full_sha": CHECKER_SOURCE_SHA,
        "tracked_source_dirty": False,
    }
    monkeypatch.setattr(h2b, "_light_source", lambda: deepcopy(checker_source))
    gate = runner._m6b_w18a_formal_gate(
        fixture["raw"],
        fixture["watchdog_summary"],
        EXPECTED_SOURCE_SHA,
        CHECKER_SOURCE_SHA,
    )
    assert gate["checks"]["source"] is True
    assert gate["checks"]["checker_source"] is True
    assert gate["checker_source_sha"] == CHECKER_SOURCE_SHA
    output = tmp_path / "source-bound-closeout.json"
    assert (
        runner._run_m6b_w18a_check(
            fixture["raw"],
            fixture["watchdog_summary"],
            output,
            EXPECTED_SOURCE_SHA,
            CHECKER_SOURCE_SHA,
        )
        == 0
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["producer_source_sha"] == EXPECTED_SOURCE_SHA
    assert record["checker_source_sha"] == CHECKER_SOURCE_SHA
    assert (
        record["checker_source"]["source_commit_full_sha"]
        == CHECKER_SOURCE_SHA
    )
    default_gate = runner._m6b_w18a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert default_gate["checks"]["checker_source"] is False


@pytest.mark.parametrize("resource_tamper", ["peak", "swap", "termination"])
def test_w18a_numeric_only_and_resource_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resource_tamper: str,
) -> None:
    fixture = _w18a_formal_fixture(tmp_path, monkeypatch)
    summary = json.loads(fixture["summary_path"].read_text(encoding="utf-8"))
    for repeat in summary["core"]["repeats"]:
        for record in repeat["inner_records"]:
            record["final_relative_residual"] = 0.010001
    report = w18.evaluate_w18a_action_gate(summary["core"])
    checks = dict(report["checks"])
    checks.update(source=True, cache=True, execution=True)
    summary["core"]["checks"] = checks
    summary["checks"] = deepcopy(checks)
    summary.update(
        status="gate_failed",
        classification="W18A_NESTED_AUXILIARY_NUMERIC_FAIL",
        w18a_pass=False,
        w18a_formal_candidate=False,
    )
    fixture["summary_path"].write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    watchdog = json.loads(fixture["watchdog_summary"].read_text(encoding="utf-8"))
    watchdog["status"] = "gate_failed"
    watchdog["process"]["return_code"] = 1
    fixture["watchdog_summary"].write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    _refresh_w18a_fixture(fixture)
    gate = runner._m6b_w18a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["classification"] == "W18A_NESTED_AUXILIARY_NUMERIC_FAIL"
    assert gate["checks"]["worker_action_gate"] is False
    watchdog = json.loads(fixture["watchdog_summary"].read_text(encoding="utf-8"))
    timeline_peak = 1000
    timeline_swap = 0
    if resource_tamper == "peak":
        watchdog["process"]["peak_rss_bytes"] = (
            runner.M6B_W18A_FORMAL_RSS_LIMIT_BYTES
        )
        timeline_peak = runner.M6B_W18A_FORMAL_RSS_LIMIT_BYTES
    elif resource_tamper == "swap":
        watchdog["process"]["swap_bytes"] = 1
        timeline_swap = 1
    else:
        watchdog["process"]["termination"] = "rss_limit"
    fixture["watchdog_summary"].write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    timeline_path = fixture["timeline_path"]
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W18A_PHASE,
                "rss_bytes": timeline_peak,
                "swap_bytes": timeline_swap,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _refresh_w18a_fixture(fixture)
    gate = runner._m6b_w18a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["classification"] == "W18A_RESOURCE_FAIL"


@pytest.mark.parametrize(
    "tamper,expected_check",
    [
        ("solution_hash", "vector_evidence"),
        ("measurement", "vector_evidence"),
        ("closure", "vector_evidence"),
        ("dtn", "action_audit"),
        ("materialization", "action_audit"),
        ("shifted_materialization", "action_audit"),
        ("outer_buffer", "action_audit"),
        ("factor_payload", "action_audit"),
        ("inner_action", "action_audit"),
        ("scratch", "scratch"),
        ("progress", "progress"),
        ("watchdog", "watchdog_evidence"),
        ("incomplete", "worker_evidence"),
    ],
)
def test_w18a_formal_gate_high_value_tamper_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    expected_check: str,
) -> None:
    fixture = _w18a_formal_fixture(tmp_path, monkeypatch)
    summary = json.loads(fixture["summary_path"].read_text(encoding="utf-8"))
    watchdog = json.loads(fixture["watchdog_summary"].read_text(encoding="utf-8"))
    if tamper == "solution_hash":
        summary["core"]["repeats"][0]["inner_records"][0]["solution_sha256"] = "f" * 64
    elif tamper == "measurement":
        summary["core"]["repeats"][0]["measurements"]["1"]["rho"] += 0.001
    elif tamper == "closure":
        summary["core"]["repeats"][0]["checkpoints"]["1"]["residual_closure"] = 0.1
    elif tamper == "dtn":
        summary["action_audit"]["physical_instances"][0]["dtn"]["apply_count"] = 11
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "materialization":
        summary["action_audit"]["auxiliary_construction"]["local_pc"][
            "materialization_identity"
        ] = {}
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "shifted_materialization":
        summary["action_audit"]["auxiliary_final_counts"]["shifted_action"][
            "global_matrix_materialized"
        ] = True
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "outer_buffer":
        summary["action_audit"]["auxiliary_final_counts"]["outer"][0][
            "bounded_full_vector_buffer_count"
        ] = 11
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "factor_payload":
        factor_manifest_path = Path(summary["authority"]["factor_manifest"]["path"])
        factor_manifest = json.loads(
            factor_manifest_path.read_text(encoding="utf-8")
        )
        del factor_manifest["audit"]["factor_payload_bytes"]
        factor_manifest_path.write_text(
            json.dumps(factor_manifest), encoding="utf-8"
        )
    elif tamper == "inner_action":
        summary["core"]["repeats"][0]["inner_records"][0][
            "global_action_count"
        ] = 42
    elif tamper == "scratch":
        summary["core"]["repeats"][0]["inner_records"][0]["cycle20"][
            "scratch_paths"
        ]["v_basis"] = "/outside/v_basis.bin"
    elif tamper == "progress":
        path = fixture["raw"] / runner.M6B_W18A_PROGRESS_FILENAME
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace("authority_validated", "wrong")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper == "watchdog":
        watchdog["evidence_sha256"] = "0" * 64
    else:
        summary["core"] = []
    fixture["summary_path"].write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    fixture["watchdog_summary"].write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    _refresh_w18a_fixture(fixture)
    if tamper == "watchdog":
        broken = json.loads(fixture["watchdog_summary"].read_text(encoding="utf-8"))
        broken["evidence_sha256"] = "0" * 64
        fixture["watchdog_summary"].write_text(
            json.dumps(broken, sort_keys=True), encoding="utf-8"
        )
    gate = runner._m6b_w18a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["pass"] is False
    assert gate["checks"][expected_check] is False
    if tamper == "watchdog":
        assert gate["classification"] == "W18A_EXECUTION_OR_EVIDENCE_FAIL"


def test_w18a_malformed_summary_and_parser_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _w18a_formal_fixture(tmp_path, monkeypatch)
    fixture["summary_path"].write_text("{malformed", encoding="utf-8")
    gate = runner._m6b_w18a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["classification"] == "W18A_EXECUTION_OR_EVIDENCE_FAIL"
    observed: list[object] = []
    monkeypatch.setattr(
        runner,
        "_run_m6b_w18a_check",
        lambda *args: observed.append(args) or 19,
    )
    output = tmp_path / "out.json"
    assert (
        runner.main(
            [
                "m6b-w18a-check",
                "--raw-dir",
                str(fixture["raw"]),
                "--watchdog-summary",
                str(fixture["watchdog_summary"]),
                "--output",
                str(output),
                "--expected-source-sha",
                EXPECTED_SOURCE_SHA,
                "--expected-checker-source-sha",
                CHECKER_SOURCE_SHA,
            ]
        )
        == 19
    )
    assert observed
    assert len(observed[0]) == 5
    assert observed[0][-1] == CHECKER_SOURCE_SHA
