"""Focused pure contracts for the W16B fixed outer-2 screen."""

from __future__ import annotations

from copy import deepcopy
import json
import inspect
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w16_global_shifted_inner_pc as core

EXPECTED_SHA = "a" * 40


def _diagonal_problem(size: int = 64) -> tuple[callable, callable, np.ndarray]:
    diagonal = 1.0 + 0.03125 * np.arange(size) + 0.02j * np.arange(size)
    matrix = np.diag(diagonal)
    matrix += np.diag(np.full(size - 1, 0.11 + 0.03j), 1)
    matrix += np.diag(np.full(size - 1, -0.07 + 0.02j), -1)
    matrix[0, -1] = 0.17 - 0.04j
    matrix[-1, 0] = -0.13 + 0.05j
    rhs = np.linspace(1.0, 2.0, size).astype(np.complex128)
    rhs += 0.03j * np.arange(size)

    def action(values: np.ndarray) -> np.ndarray:
        return matrix @ np.asarray(values, dtype=np.complex128)

    def identity_pc(values: np.ndarray) -> np.ndarray:
        return np.array(values, dtype=np.complex128, copy=True)

    return action, identity_pc, rhs


def _basis(capacity: int) -> dict[str, object]:
    return {
        "capacity": capacity,
        "written_count": capacity,
        "write_count": capacity,
        "allocated_bytes": capacity * core.W16A_VECTOR_BYTES,
        "mmap": False,
    }


def _inner_audit(initial: bool, suffix: str) -> dict[str, object]:
    return {
        "algorithm": "right_flexible_gmres",
        "rows": core.W16A_VECTOR_BYTES // 16,
        "dtype": "complex128",
        "max_steps": 20,
        "iterations": 20,
        "checkpoint_iterations": [20],
        "checkpoint_count": 1,
        "observer_count": 1,
        "action_count": 22 if initial else 21,
        "pc_count": 20,
        "initial_action_count": 1 if initial else 0,
        "orthogonalization_passes": 2,
        "mmap": False,
        "basis_in_memory": False,
        "scratch_bytes": core.W16A_SCRATCH_PER_RUN_BYTES,
        "scratch_mmap": False,
        "scratch_basis_in_memory": False,
        "checkpoint_set_complete": True,
        "bounded_full_vector_gate": True,
        "scratch_paths": {
            "v_basis": f"/w16b/{suffix}/v_basis.bin",
            "z_basis": f"/w16b/{suffix}/z_basis.bin",
        },
        "v_basis": _basis(21),
        "z_basis": _basis(20),
        "initial_solution_provided": initial,
    }


def _fixed40_record(apply_index: int, screen: int) -> dict[str, object]:
    prefix = f"screen{screen}/apply{apply_index}"
    z_hash = f"{apply_index:02d}".zfill(64)
    return {
        "apply_index": apply_index,
        "schema": core.W16B_INNER_SCHEMA,
        "algorithm": "fgmres_right_shifted_beta1_composed_fixed20_plus20",
        "initial_solution_provided": False,
        "initial_action_count": 0,
        "cycle20": _inner_audit(False, f"{prefix}/cycle20"),
        "cycle40": _inner_audit(True, f"{prefix}/cycle40"),
        "global_action_count": core.W16B_FIXED40_GLOBAL_ACTION_COUNT,
        "pc_apply_count": core.W16B_FIXED40_PC_COUNT,
        "shifted_action_count": core.W16B_FIXED40_SHIFTED_ACTION_COUNT,
        "solution_sha256": z_hash,
        "solution_artifact": {
            "path": f"/w16b/{prefix}/solution.npy",
            "array_sha256": z_hash,
            "file_sha256": "a" * 64,
        },
        "finite": True,
        "cycle20_relative_residual": 0.02,
        "cycle40_relative_residual": 0.008,
        "final_relative_residual": 0.008,
        "scratch_paths": {
            "cycle20": _inner_audit(False, f"{prefix}/cycle20")["scratch_paths"],
            "cycle40": _inner_audit(True, f"{prefix}/cycle40")["scratch_paths"],
        },
    }


def _outer_audit(screen: int) -> dict[str, object]:
    return {
        "algorithm": "right_flexible_gmres",
        "rows": core.W16A_VECTOR_BYTES // 16,
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
        "bounded_full_vector_gate": True,
        "checkpoint_set_complete": True,
        "scratch_bytes": core.W16B_OUTER_SCRATCH_PER_SCREEN_BYTES,
        "scratch_mmap": False,
        "scratch_basis_in_memory": False,
        "bounded_full_vector_buffer_count": 12,
        "bounded_full_vector_bytes": core.W16B_OUTER_BOUNDED_VECTOR_BYTES,
        "v_basis": _basis(3),
        "z_basis": _basis(2),
        "scratch_paths": {
            "v_basis": f"/w16b/outer/screen{screen}/v_basis.bin",
            "z_basis": f"/w16b/outer/screen{screen}/z_basis.bin",
        },
    }


def _checkpoint(screen: int, iteration: int, rho: float) -> dict[str, object]:
    prefix = f"/w16b/outer_checkpoints/screen{screen}/m6b_iter{iteration}"
    return {
        "iteration": iteration,
        "true_relative_residual": rho,
        "residual_closure": 0.0,
        "artifacts": {
            name: {
                "path": f"{prefix}_{name}.npy",
                "array_sha256": f"{iteration}{name}".encode().hex().ljust(64, "0")[:64],
                "file_sha256": "b" * 64,
                "dtype": "complex128",
                "shape": [core.W16A_VECTOR_BYTES // 16],
                "bytes": core.W16A_VECTOR_BYTES + 128,
            }
            for name in ("solution", "outer_action", "residual", "rhs")
        },
    }


def _w16b_action_audit() -> dict[str, object]:
    physical = {
        "apply_count": 8,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "factor_count": 0,
        "ksp_created": False,
    }
    outer = {
        "apply_count": 8,
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab": False,
    }
    dtn = {
        "apply_count": 8,
        "mode_count": 80,
        "fine_space": "uncondensed_fullspace",
        "global_matrix_materialized": False,
        "augmented_matrix_materialized": False,
        "condensation": False,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
    }
    bridge = {"forward_apply_count": 8, "fixed_work_vectors": 2, "per_apply_vec_creation": 0}
    return {
        "retained_authority_vector_roles": ["w7_target_residual"],
        "lifecycle_events": [
            "auxiliary_constructed",
            "physical_constructed",
            "screen_run_1",
            "screen_run_2",
            "physical_released",
            "auxiliary_released",
        ],
        "global_shifted_action_count": 172,
        "local_pc_apply_count": 160,
        "local_exact_shifted_volume_action_count": 160,
        "shifted_action_total_count": 332,
        "physical_action_count": 8,
        "physical_dtn_action_count": 8,
        "outer_pc_apply_count": 4,
        "auxiliary_construction": {"shifted_action": {"apply_count": 0}},
        "physical_construction": {
            "physical": {"apply_count": 0},
            "outer": {"apply_count": 0},
            "dtn": {"apply_count": 0},
            "bridge": {"forward_apply_count": 0},
        },
        "auxiliary_final_counts": {
            "global_shifted_action_count": 172,
            "local_pc_apply_count": 160,
            "local_exact_shifted_volume_action_count": 160,
            "shifted_action_total_count": 332,
            "shifted_action_audit": {"apply_count": 332},
        },
        "physical_instances": [
            {"physical": physical, "outer": outer, "dtn": dtn, "bridge": bridge}
        ],
    }


def _synthetic_summary() -> dict[str, object]:
    rho1 = core.W16B_RHO1_ANCHOR
    rho2 = core.W16B_RHO2_LIMIT
    runs = []
    for screen in (1, 2):
        runs.append(
            {
                "run_index": screen,
                "outer_audit": _outer_audit(screen),
                "inner_records": [_fixed40_record(1, screen), _fixed40_record(2, screen)],
                "checkpoints": [_checkpoint(screen, 1, rho1), _checkpoint(screen, 2, rho2)],
                "rho1": rho1,
                "rho2": rho2,
                "finite": True,
            }
        )
    return {
        "schema": core.W16B_SCHEMA,
        "fixed_identity": {
            "operator": "shifted_volume_only",
            "beta": 1.0,
            "right_pc": "direct_beta1_shifted_row_complete_local_patch",
            "auxiliary_dtn_used": False,
            "projected_range_used": False,
            "b0_used": False,
            "m3y_used": False,
            "range_store_used": False,
        },
        "screen_runs": runs,
        "inner_identity": [
            {
                "first_sha256": runs[0]["inner_records"][index]["solution_sha256"],
                "second_sha256": runs[1]["inner_records"][index]["solution_sha256"],
                "sha256_equal": True,
                "relative_difference": 0.0,
            }
            for index in (0, 1)
        ],
        "action_audit": _w16b_action_audit(),
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "physical_operator": "beta0_volume_plus_matrix_free_dtn80",
            "auxiliary_operator": "shifted_volume_only",
            "auxiliary_dtn_used": False,
            "global_matrix_materialized": False,
            "augmented_matrix_materialized": False,
            "condensation": False,
            "static_condensation": False,
            "trace_slab": False,
            "slab_factors": 0,
            "physical_ksp_used": False,
            "pde_used": False,
            "official_rta": False,
        },
        "lifecycle": {
            "auxiliary_physical_overlap": True,
            "release_between_screen_runs": False,
            "heavy_objects_reused_between_screens": True,
            "events": [
                "auxiliary_constructed",
                "physical_constructed",
                "screen_run_1",
                "screen_run_2",
                "physical_released",
                "auxiliary_released",
            ],
        },
        "prediction": runner._m6b_w16b_predicted_live_set(),
        "w16r_authority": {
            "compact_file_sha256": core.W16B_W16R_COMPACT_FILE_SHA256,
            "compact_evidence_sha256": core.W16B_W16R_COMPACT_EVIDENCE_SHA256,
            "measured_peak_rss_bytes": core.W16B_W16R_MEASURED_PEAK_BYTES,
            "measured_swap_bytes": 0,
        },
        "memory_audit": {
            "physical_retained_numeric_payload_bytes": core.W16B_PHYSICAL_RETAINED_PAYLOAD_BYTES,
            "physical_per_apply_temporary_bytes": core.W16B_PHYSICAL_PER_APPLY_TEMP_BYTES,
            "dtn_retained_and_work_bytes": core.W16B_DTN_RETAINED_WORK_BYTES,
            "outer_bridge_fixed_vectors": 2,
            "outer_petsc_template_vector_bytes": core.W16A_VECTOR_BYTES,
            "outer_solver_bounded_vector_bytes": core.W16B_OUTER_BOUNDED_VECTOR_BYTES,
        },
    }


@pytest.fixture
def w16b_formal_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 2)
    monkeypatch.setattr(core, "W16A_VECTOR_BYTES", 16)
    monkeypatch.setattr(core, "W16A_SCRATCH_PER_RUN_BYTES", 16)

    source = {
        "source_commit_full_sha": "a" * 40,
        "source_worktree_dirty": False,
        "tracked_source_dirty": False,
    }
    factor = {
        "path": str(tmp_path / "factor" / "manifest.json"),
        "present": True,
        "bytes": 1,
        "sha256": "b" * 64,
        "source_commit_full_sha": "d98254fecddc41940f50f72753ec9f0f80407793",
        "factor_compiler": {"version_line": "fixture", "probe_command": ["fixture"]},
    }
    w16r_authority = {
        "compact_path": str(tmp_path / "w16r.json"),
        "compact_file_sha256": core.W16B_W16R_COMPACT_FILE_SHA256,
        "compact_evidence_sha256": core.W16B_W16R_COMPACT_EVIDENCE_SHA256,
        "producer_source_sha": "d0d9724c0ba3b91bffe407a2e6fd39943aefd992",
        "measured_peak_rss_bytes": core.W16B_W16R_MEASURED_PEAK_BYTES,
        "measured_swap_bytes": 0,
        "classification": "W16R_FORMAL_ACTION_GATE_PASS",
        "w16b_unlocked": True,
    }
    rhs = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128)
    rhs_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(rhs)
    w7 = {
        "compact": {
            "path": str(tmp_path / "w7.json"),
            "file_sha256": "c" * 64,
            "producer_source_sha": runner.M6B_W8A_W7_SOURCE_SHA,
        },
        "raw_dir": str(tmp_path / "w7_raw"),
        "residual_artifact": {
            "path": "m6b_iter400_residual.npy",
            "bytes": int(rhs.nbytes),
            "file_sha256": "d" * 64,
            "array_sha256": rhs_sha,
        },
    }

    import benchmarks.run_task037_extra_h2b as h2b

    monkeypatch.setattr(runner, "_m6b_w16b_w16r_authority", lambda _path: deepcopy(w16r_authority))
    monkeypatch.setattr(runner, "_m6b_w9a_load_w7", lambda *_paths: deepcopy(w7))
    monkeypatch.setattr(runner, "_m6b_w16a_factor_authority", lambda _path: deepcopy(factor))
    monkeypatch.setattr(runner, "_m6b_w16a_jit_valid", lambda *_args: True)
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda _value: True)
    monkeypatch.setattr(runner, "_m6b_w6a_runtime_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_m6b_expected_p6", lambda _value: True)
    monkeypatch.setattr(h2b, "_light_source", lambda: deepcopy(source))

    raw_dir = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw_dir.mkdir()
    watchdog_dir.mkdir()
    core_summary = _synthetic_summary()
    core_summary["w16r_authority"] = deepcopy(w16r_authority)
    core_summary["residual"] = {
        "role": "untouched_W7_cumulative400_full_explicit_residual",
        "authority": deepcopy(w7["compact"]),
        "artifact": deepcopy(w7["residual_artifact"]),
    }

    def write_array(path: Path, values: np.ndarray, *, checkpoint: bool) -> dict[str, object]:
        values = np.ascontiguousarray(values, dtype=np.complex128)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, values, allow_pickle=False)
        return {
            "path": path.name if checkpoint else str(path.resolve()),
            "bytes": int(path.stat().st_size),
            "sha256": runner._sha256_file(path),
            "file_sha256": runner._sha256_file(path),
            "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(values),
            "shape": list(values.shape),
            "dtype": "complex128",
        }

    for screen_index, screen in enumerate(core_summary["screen_runs"], start=1):
        outer_root = raw_dir / "outer_scratch" / f"screen{screen_index}"
        outer_paths = {
            "v_basis": outer_root / "v_basis.bin",
            "z_basis": outer_root / "z_basis.bin",
        }
        screen["outer_audit"]["scratch_paths"] = {
            key: str(path.resolve()) for key, path in outer_paths.items()
        }
        for role, path in outer_paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as stream:
                stream.truncate(screen["outer_audit"][role]["allocated_bytes"])
        for apply_index, record in enumerate(screen["inner_records"], start=1):
            apply_root = outer_root / "inner" / f"apply_{apply_index:02d}"
            z_values = np.asarray(
                [0.25 * apply_index + 0.1j, 0.5 * apply_index - 0.2j],
                dtype=np.complex128,
            )
            record["solution_artifact"] = write_array(
                apply_root / "solution.npy", z_values, checkpoint=False
            )
            record["solution_sha256"] = record["solution_artifact"]["array_sha256"]
            record["rhs_sha256"] = rhs_sha
            record["scratch_paths"] = {}
            for cycle_name in ("cycle20", "cycle40"):
                cycle_root = apply_root / cycle_name
                cycle_paths = {
                    "v_basis": cycle_root / "v_basis.bin",
                    "z_basis": cycle_root / "z_basis.bin",
                }
                record[cycle_name]["scratch_paths"] = {
                    key: str(path.resolve()) for key, path in cycle_paths.items()
                }
                record["scratch_paths"][cycle_name] = record[cycle_name]["scratch_paths"]
                for role, path in cycle_paths.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("wb") as stream:
                        stream.truncate(record[cycle_name][role]["allocated_bytes"])
        for checkpoint_index, checkpoint in enumerate(screen["checkpoints"], start=1):
            rho = core.W16B_RHO1_ANCHOR if checkpoint_index == 1 else core.W16B_RHO2_LIMIT
            residual = rho * rhs
            action = rhs - residual
            solution = np.asarray(
                [0.05 * checkpoint_index + 0.01j, 0.08 * checkpoint_index - 0.02j],
                dtype=np.complex128,
            )
            base = raw_dir / "outer_checkpoints" / f"screen{screen_index}"
            checkpoint["true_relative_residual"] = rho
            checkpoint["residual_closure"] = 0.0
            checkpoint["artifacts"] = {
                name: write_array(
                    base / f"m6b_iter{checkpoint_index}_{name}.npy",
                    values,
                    checkpoint=True,
                )
                for name, values in (
                    ("solution", solution),
                    ("outer_action", action),
                    ("residual", residual),
                    ("rhs", rhs),
                )
            }

    for index in (0, 1):
        first = core_summary["screen_runs"][0]["inner_records"][index]
        second = core_summary["screen_runs"][1]["inner_records"][index]
        core_summary["inner_identity"][index].update(
            {
                "first_sha256": first["solution_sha256"],
                "second_sha256": second["solution_sha256"],
                "sha256_equal": True,
                "relative_difference": 0.0,
            }
        )

    summary = {
        "schema": runner.M6B_W16B_SCHEMA,
        "phase": runner.M6B_W16B_PHASE,
        "status": "action_gate_pass",
        "classification": "W16B_OUTER2_ACTION_GATE_PASS",
        "w16b_pass": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w16c_locked": True,
        "w16c_unlocked": False,
        "authority": {
            "w7": deepcopy(w7["compact"]),
            "w7_raw_dir": w7["raw_dir"],
            "w7_residual_artifact": deepcopy(w7["residual_artifact"]),
            "factor_manifest": deepcopy(factor),
            "w16r_authority": deepcopy(w16r_authority),
        },
        "scope": runner._m6b_w16b_scope(),
        "runtime_identity": {"compiler": deepcopy(factor["factor_compiler"])},
        "p6": {},
        "prediction": runner._m6b_w16b_predicted_live_set(),
        "predicted_live_set": runner._m6b_w16b_predicted_live_set(),
        "jit_cache": {},
        "source_at_start": deepcopy(source),
        "source_at_end": deepcopy(source),
        "action_audit": deepcopy(core_summary["action_audit"]),
        "core": core_summary,
    }
    progress = []
    for event in runner.M6B_W16B_EVENTS:
        record = {
            "schema": f"{runner.M6B_W16B_SCHEMA}.progress.v1",
            "phase": runner.M6B_W16B_PHASE,
            "event": event,
            "elapsed_wall_seconds": 1.0,
        }
        if event in {"authority_validated", "summary_ready"}:
            record["w16r_authority"] = deepcopy(w16r_authority)
        progress.append(record)
    progress_path = raw_dir / runner.M6B_W16B_PROGRESS_FILENAME
    progress_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in progress),
        encoding="utf-8",
    )
    summary_path = raw_dir / runner.M6B_W16B_SUMMARY_FILENAME
    runner._write_json(summary_path, runner._attach_evidence(summary))

    timeline_path = watchdog_dir / f"{runner.M6B_W16B_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W16B_PHASE,
                "rss_bytes": 100,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (watchdog_dir / f"{runner.M6B_W16B_PHASE}_stdout.txt").write_text("ok\n")
    (watchdog_dir / f"{runner.M6B_W16B_PHASE}_root_pid.json").write_text("{}\n")
    timeline = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W16B_PHASE
    )
    expected_raw = runner._m6b_w16a_raw_artifacts(raw_dir, mode="w16b")
    expected_watchdog = runner._m6b_w16a_watchdog_artifacts(watchdog_dir, mode="w16b")
    watchdog = {
        "schema": runner.M6B_W16B_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W16B_PHASE,
        "status": "measurement_complete",
        "process": {
            "return_code": 0,
            "termination": None,
            "peak_rss_bytes": 100,
            "swap_bytes": 0,
        },
        "drain": {"gone": True},
        "source_at_start": deepcopy(source),
        "source_at_end": deepcopy(source),
        "source_end_clean": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W16B_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W16B_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W16B_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(raw_dir.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "w16r_authority": deepcopy(w16r_authority),
        "w16c_unlocked": False,
        "w16c_locked": True,
        "command": runner._m6b_w16b_worker_command(
            raw_dir,
            runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_W7_RAW_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_JIT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16B_W16R_COMPACT_RELATIVE_PATH,
            EXPECTED_SHA,
        ),
        "artifact_inventory": {"raw": expected_raw, "watchdog": expected_watchdog},
        "worker_summary": expected_raw[0],
        "timeline": timeline,
    }
    watchdog_path = watchdog_dir / runner.M6B_W16B_WATCHDOG_SUMMARY_FILENAME
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))
    return {
        "raw": raw_dir,
        "watchdog": watchdog_dir,
        "watchdog_summary": watchdog_path,
        "summary": summary,
    }


def _refresh_w16b_formal_summary(fixture, summary):
    runner._write_json(
        fixture["raw"] / runner.M6B_W16B_SUMMARY_FILENAME,
        runner._attach_evidence(summary),
    )
    watchdog = runner._read_json(fixture["watchdog_summary"])
    watchdog["worker_summary"] = runner._artifact(
        fixture["raw"], runner.M6B_W16B_SUMMARY_FILENAME
    )
    watchdog["artifact_inventory"]["raw"] = runner._m6b_w16a_raw_artifacts(
        fixture["raw"], mode="w16b"
    )
    runner._write_json(
        fixture["watchdog_summary"], runner._attach_evidence(watchdog)
    )


def test_fixed40_uses_zero_start_then_restart_and_fixed_counts(tmp_path: Path) -> None:
    action, pc, rhs = _diagonal_problem()
    root = tmp_path / "inner" / "apply_01"
    root.mkdir(parents=True)
    result = core.run_w16b_fixed40(action, pc, rhs, root)

    assert result.cycle20_audit["initial_solution_provided"] is False
    assert result.cycle20_audit["action_count"] == 21
    assert result.cycle20_audit["pc_count"] == 20
    assert result.cycle40_audit["initial_solution_provided"] is True
    assert result.cycle40_audit["initial_action_count"] == 1
    assert result.cycle40_audit["action_count"] == 22
    assert result.cycle40_audit["pc_count"] == 20
    assert result.audit["global_action_count"] == 43
    assert result.audit["pc_apply_count"] == 40
    assert result.audit["shifted_action_count"] == 83
    expected = np.linalg.norm(rhs - action(result.solution)) / np.linalg.norm(rhs)
    assert result.final_relative_residual == pytest.approx(expected)
    assert (root / "cycle20" / "v_basis.bin").is_file()
    assert (root / "cycle40" / "z_basis.bin").is_file()


def test_fixed40_repeat_is_exact_with_distinct_scratch(tmp_path: Path) -> None:
    action, pc, rhs = _diagonal_problem()
    first_root = tmp_path / "apply_01"
    second_root = tmp_path / "apply_02"
    first_root.mkdir()
    second_root.mkdir()
    first = core.run_w16b_fixed40(action, pc, rhs, first_root)
    second = core.run_w16b_fixed40(action, pc, rhs, second_root)

    assert np.array_equal(first.solution, second.solution)
    assert first.audit["scratch_paths"] != second.audit["scratch_paths"]


def test_outer2_creates_nested_scratch_once_and_fixed_counts(tmp_path: Path) -> None:
    action, pc, rhs = _diagonal_problem()
    physical = lambda values: action(values) + 0.2 * np.asarray(values)
    events: list[dict[str, np.ndarray]] = []
    outer_root = tmp_path / "outer" / "screen1"
    result, composed = core.run_w16b_outer2(
        physical,
        action,
        pc,
        rhs,
        outer_root,
        observer=lambda event: events.append(
            {key: np.array(event[key], copy=True) for key in ("solution", "action", "residual", "rhs")}
        ),
    )

    assert result.audit["action_count"] == 4
    assert result.audit["pc_count"] == 2
    assert composed.apply_count == 2
    assert result.audit["scratch_bytes"] == 5 * rhs.size * 16
    assert len(events) == 2
    assert (outer_root / "v_basis.bin").is_file()
    assert (outer_root / "inner" / "apply_01" / "cycle20" / "v_basis.bin").is_file()
    assert (outer_root / "inner" / "apply_02" / "cycle40" / "z_basis.bin").is_file()
    with pytest.raises(FileExistsError):
        core.run_w16b_outer2(action, action, pc, rhs, outer_root)


def test_two_outer_screens_have_exact_checkpoint_identity(tmp_path: Path) -> None:
    action, pc, rhs = _diagonal_problem()
    physical = lambda values: action(values) + 0.2 * np.asarray(values)
    screens: list[list[np.ndarray]] = []
    for index in (1, 2):
        events: list[np.ndarray] = []
        core.run_w16b_outer2(
            physical,
            action,
            pc,
            rhs,
            tmp_path / f"screen{index}",
            observer=lambda event: events.append(np.array(event["solution"], copy=True)),
        )
        screens.append(events)
    assert all(np.array_equal(screens[0][i], screens[1][i]) for i in (0, 1))


@pytest.mark.parametrize(
    "tamper",
    [
        lambda value: value["screen_runs"][0].update({"rho2": 0.9}),
        lambda value: value["screen_runs"][0]["outer_audit"].update({"scratch_bytes": 1}),
        lambda value: value["action_audit"].update({"physical_action_count": 7}),
        lambda value: value["prediction"]["components"].update(
            {"physical_per_apply_temporary_bytes": 1}
        ),
        lambda value: value["screen_runs"][1]["inner_records"][1].update(
            {"solution_sha256": "bad"}
        ),
        lambda value: value["inner_identity"][0].update(
            {"second_sha256": "b" * 64, "sha256_equal": True}
        ),
    ],
    ids=("rho", "scratch", "counts", "prediction", "record_identity", "inner_identity"),
)
def test_outer2_evaluator_fails_closed_on_tamper(tamper) -> None:
    summary = _synthetic_summary()
    tamper(summary)
    report = core.evaluate_w16b_outer2_gate(summary)
    assert report["pass"] is False
    assert report["problems"]


def test_outer2_evaluator_accepts_fixed_p6_contract_fixture() -> None:
    report = core.evaluate_w16b_outer2_gate(_synthetic_summary())
    assert report["pass"] is True
    assert all(type(value) is bool and value for value in report["checks"].values())


def test_prediction_ledger_and_disk_scratch_semantics() -> None:
    prediction = runner._m6b_w16b_predicted_live_set()
    assert prediction["bytes"] == 1_734_993_014
    assert prediction["derived_not_measured"] is True
    assert prediction["scratch_is_disk_not_rss"] is True
    assert prediction["scratch_components"] == {
        "inner_per_apply_bytes": 228_028_224,
        "inner_per_screen_bytes": 456_056_448,
        "outer_scratch_per_screen_bytes": 13_904_160,
        "total_scratch_per_screen_bytes": 469_960_608,
        "two_screen_total_scratch_bytes": 939_921_216,
    }
    assert sum(prediction["components"].values()) == prediction["bytes"]


def test_w16b_command_parser_and_old_w16_commands() -> None:
    source = "a" * 40
    common = [
        "--run-dir", "run", "--w7-compact", "w7", "--w7-raw-dir", "raw",
        "--shifted-factor-manifest", "factor", "--jit-cache-source", "jit",
        "--w16r-compact", "w16r", "--expected-source-sha", source,
    ]
    args = runner._parser().parse_args(["m6b-w16b-watch-screen", *common])
    assert args.command == "m6b-w16b-watch-screen"
    assert args.w16r_compact == "w16r"
    for command in ("m6b-w16a-global-shifted-inner-diagnostic", "m6b-w16r-restart20-diagnostic"):
        assert runner._parser().parse_args(
            [command, "--run-dir", "run", "--w7-compact", "w7", "--w7-raw-dir", "raw",
             "--shifted-factor-manifest", "factor", "--jit-cache-source", "jit",
             *(["--w16a-compact", "a", "--w16a-raw-dir", "ar"] if command.endswith("diagnostic") and "w16r" in command else []),
             "--expected-source-sha", source]
        ).command == command


def test_w16b_raw_inventory_is_complete_without_reading_artifacts(tmp_path: Path) -> None:
    inventory = runner._m6b_w16a_raw_artifacts(tmp_path, mode="w16b")
    assert len(inventory) == 42
    assert not any(item["present"] for item in inventory)


def test_w16b_formal_gate_reads_raw_vectors_and_checker_unlocks(
    w16b_formal_fixture,
):
    report = runner._m6b_w16b_formal_gate(
        w16b_formal_fixture["raw"],
        w16b_formal_fixture["watchdog_summary"],
        EXPECTED_SHA,
    )
    assert report["pass"] is True
    assert report["checks"]["checkpoint_artifacts"] is True
    assert report["checks"]["scratch"] is True
    assert report["checks"]["action_audit"] is True
    assert report["checks"]["watchdog_evidence"] is True
    assert len(report["vector_evidence"]["artifact_hashes"]) == 20

    output = w16b_formal_fixture["raw"].parent / "w16b_closeout.json"
    assert (
        runner._run_m6b_w16b_check(
            w16b_formal_fixture["raw"],
            w16b_formal_fixture["watchdog_summary"],
            output,
            EXPECTED_SHA,
        )
        == 0
    )
    compact = runner._read_json(output)
    assert compact["w16c_unlocked"] is True
    assert compact["w16c_locked"] is False
    assert compact["formal_pass"] is True


@pytest.mark.parametrize(
    "tamper,expected_check",
    [
        ("inner_hash", "worker_action_gate"),
        ("raw_closure", "checkpoint_artifacts"),
        ("memory_audit", "worker_action_gate"),
        ("w16r_authority", "w16r_authority"),
        ("watchdog_artifact", "watchdog_evidence"),
        ("resource_limits", "watchdog_evidence"),
    ],
)
def test_w16b_formal_gate_fails_closed_on_high_value_tamper(
    w16b_formal_fixture, tamper, expected_check
):
    summary = deepcopy(w16b_formal_fixture["summary"])
    if tamper == "inner_hash":
        summary["core"]["inner_identity"][0]["second_sha256"] = "e" * 64
        summary["core"]["inner_identity"][0]["sha256_equal"] = True
        _refresh_w16b_formal_summary(w16b_formal_fixture, summary)
    elif tamper == "raw_closure":
        descriptor = summary["core"]["screen_runs"][0]["checkpoints"][0][
            "artifacts"
        ]["residual"]
        path = w16b_formal_fixture["raw"] / "outer_checkpoints" / "screen1" / descriptor[
            "path"
        ]
        values = np.load(path, allow_pickle=False) + (0.1 + 0.0j)
        np.save(path, values, allow_pickle=False)
        descriptor["sha256"] = runner._sha256_file(path)
        descriptor["file_sha256"] = descriptor["sha256"]
        descriptor["array_sha256"] = runner._m6b_w6a_w5_legacy_raw_array_sha256(values)
        _refresh_w16b_formal_summary(w16b_formal_fixture, summary)
    elif tamper == "memory_audit":
        summary["core"]["memory_audit"]["physical_per_apply_temporary_bytes"] = 1
        _refresh_w16b_formal_summary(w16b_formal_fixture, summary)
    elif tamper == "w16r_authority":
        summary["authority"]["w16r_authority"]["compact_file_sha256"] = "0" * 64
        _refresh_w16b_formal_summary(w16b_formal_fixture, summary)
    elif tamper == "watchdog_artifact":
        (
            w16b_formal_fixture["watchdog"]
            / f"{runner.M6B_W16B_PHASE}_stdout.txt"
        ).unlink()
    else:
        watchdog = runner._read_json(w16b_formal_fixture["watchdog_summary"])
        watchdog["resource_limits"]["swap_bytes"] = 1
        runner._write_json(
            w16b_formal_fixture["watchdog_summary"],
            runner._attach_evidence(watchdog),
        )

    report = runner._m6b_w16b_formal_gate(
        w16b_formal_fixture["raw"],
        w16b_formal_fixture["watchdog_summary"],
        EXPECTED_SHA,
    )
    assert report["pass"] is False
    assert report["checks"][expected_check] is False


def test_w16b_check_writes_closeout_for_malformed_summary(w16b_formal_fixture):
    raw_summary = w16b_formal_fixture["raw"] / runner.M6B_W16B_SUMMARY_FILENAME
    runner._write_json(raw_summary, runner._attach_evidence({}))
    watchdog = runner._read_json(w16b_formal_fixture["watchdog_summary"])
    watchdog["worker_summary"] = runner._artifact(
        w16b_formal_fixture["raw"], runner.M6B_W16B_SUMMARY_FILENAME
    )
    watchdog["artifact_inventory"]["raw"] = runner._m6b_w16a_raw_artifacts(
        w16b_formal_fixture["raw"], mode="w16b"
    )
    runner._write_json(
        w16b_formal_fixture["watchdog_summary"], runner._attach_evidence(watchdog)
    )
    output = w16b_formal_fixture["raw"].parent / "malformed_closeout.json"
    assert (
        runner._run_m6b_w16b_check(
            w16b_formal_fixture["raw"],
            w16b_formal_fixture["watchdog_summary"],
            output,
            EXPECTED_SHA,
        )
        == 1
    )
    result = runner._read_json(output)
    assert result["status"] == "gate_failed"
    assert result["w16c_locked"] is True


def test_worker_stays_locked_and_checker_only_unlocks(tmp_path: Path, monkeypatch) -> None:
    summary = _synthetic_summary()
    gate = {
        "pass": True,
        "classification": "W16B_FORMAL_ACTION_GATE_PASS",
        "summary": {"core": summary},
        "checks": {"worker_action_gate": True},
        "problems": [],
        "worker_checks": {},
        "vector_evidence": {},
        "timeline": {},
        "checker_source": {},
    }
    monkeypatch.setattr(runner, "_m6b_w16b_formal_gate", lambda *args: gate)
    output = tmp_path / "closeout.json"
    assert runner._run_m6b_w16b_check(tmp_path / "raw", tmp_path / "watchdog.json", output, "a" * 40) == 0
    result = runner._read_json(output)
    assert result["w16c_unlocked"] is True
    assert result["w16c_locked"] is False


def test_core_ready_escape_is_after_core_and_real_errors_are_not_sentinel() -> None:
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    raise_index = source.index("raise _W16BCoreReady()")
    assert source.rfind('core_result = {', 0, raise_index) < raise_index
    assert "except _W16BCoreReady:" in source
    assert "except (OSError, RuntimeError, ValueError, TypeError, KeyError, FloatingPointError)" in source
