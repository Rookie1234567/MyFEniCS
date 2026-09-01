from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import task038_full3d_floquet_wave_checkpoint_diagnostic_checker as checker
from benchmarks import run_task038_full3d_jit_staged_parent as parent
from src.solvers.fullspace_physical_wave_diagnostic import two_pass_mgs, two_pass_mgs_append


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/templates/full3d_iterative_example.dat"
PYTHON = ROOT / ".venv/bin/python"
SOURCE = "a" * 40


def _write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _facts(values: object) -> dict[str, object]:
    array = np.asarray(values, dtype=np.complex128)
    return {
        "array_sha256": checker._array_sha(array),
        "finite": bool(np.all(np.isfinite(array))),
        "norm": float(np.linalg.norm(array)),
        "owned_slave_max": 0.0,
    }


def _runtime() -> dict[str, object]:
    return {
        "source_sha": SOURCE,
        "branch": checker.BRANCH,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(PYTHON),
        "python_prefix": str(ROOT / ".venv"),
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        "abi_modules": {
            "mpi4py": "/tmp/mpi4py.py",
            "petsc4py": "/tmp/petsc4py.py",
            "dolfinx": "/tmp/dolfinx.py",
            "basix": "/tmp/basix.py",
        },
    }


def _member(pid: int, ppid: int, stage: str, stamp: int, rss: int) -> dict[str, object]:
    return {
        "pid": pid,
        "ppid": ppid,
        "comm": "python",
        "state": "S",
        "cmdline": "python synthetic",
        "stage": stage,
        "rss_bytes": rss,
        "pss_bytes": rss,
        "swap_bytes": 0,
        "timestamp_ns": stamp + 1,
        "exit_code": None,
    }


def _monitor(pid: int, stage: dict[str, object]) -> dict[str, object]:
    descendants = list(stage["observed_descendant_pids"])
    return {
        "pid": pid,
        "process_group_id": pid,
        "warning_limit_bytes": checker.RSS_WARNING,
        "stop_limit_bytes": checker.RSS_WATCHDOG,
        "resource_warning": stage["peak_rss_bytes"] >= checker.RSS_WARNING,
        "warning_crossed": stage["warning_crossed"],
        "warning_sample_index": stage["warning_sample_index"],
        "warning_timestamp_ns": stage["warning_timestamp_ns"],
        "started_ns": stage["first_timestamp_ns"],
        "ended_ns": stage["last_timestamp_ns"],
        "returncode": 0,
        "natural_exit": True,
        "stop_reason": "natural_exit",
        "sample_count": stage["sample_count"],
        "peak_rss_bytes": stage["peak_rss_bytes"],
        "max_swap_bytes": stage["max_swap_bytes"],
        "all_status_readable": True,
        "compiler_descendant_peak": 0,
        "observed_descendant_pids": descendants,
        "last_sample": stage["last_sample"],
        "signals": [],
        "required_sigkill": False,
        "process_group_gone": True,
        "descendants_gone": True,
    }


def _make_process(root: Path) -> tuple[Path, dict[str, object], dict[str, dict[str, object]], dict[str, int]]:
    root_pid = 100000
    samples: list[dict[str, object]] = []
    stage_stats: dict[str, dict[str, object]] = {}
    stage_pids: dict[str, int] = {}
    stamp = 1000
    for index, stage in enumerate(checker.PROCESS_STAGES):
        pid = 200000 + index
        stage_pids[stage] = pid
        members = [_member(root_pid, 1, stage, stamp, 100)]
        if stage != "precompile:parent-only":
            members.append(_member(pid, root_pid, stage, stamp, 10))
        sample = {
            "schema": checker.SAMPLE_SCHEMA,
            "root_pid": root_pid,
            "stage": stage,
            "timestamp_ns": stamp,
            "exit_code": None,
            "members": members,
            "unreadable_pids": [],
            "vanished_pids": [],
            "all_status_readable": True,
            "compiler_descendant_count": 0,
            "rss_bytes": 110 if len(members) == 2 else 100,
            "swap_bytes": 0,
            "pss_all_readable": True,
            "pss_bytes": 110 if len(members) == 2 else 100,
        }
        samples.append(sample)
        stage_stats[stage] = {
            "sample_count": 1,
            "first_timestamp_ns": stamp,
            "last_timestamp_ns": stamp,
            "peak_rss_bytes": sample["rss_bytes"],
            "max_swap_bytes": 0,
            "all_status_readable": True,
            "compiler_descendant_peak": 0,
            "observed_descendant_pids": [] if stage == "precompile:parent-only" else [pid],
            "last_sample": sample,
            "warning_crossed": False,
            "warning_sample_index": None,
            "warning_timestamp_ns": None,
        }
        stamp += 1000
    process_path = root / "parent_process.jsonl"
    with process_path.open("x", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n")
    observed = sorted(pid for stage, pid in stage_pids.items() if stage != "precompile:parent-only")
    process = {
        "sample_path": str(process_path),
        "sample_sha256": _sha(process_path),
        "sample_count": len(samples),
        "parent_pid": root_pid,
        "first_timestamp_ns": samples[0]["timestamp_ns"],
        "last_timestamp_ns": samples[-1]["timestamp_ns"],
        "all_status_readable": True,
        "peak_rss_bytes": 110,
        "max_swap_bytes": 0,
        "compiler_descendant_peak": 0,
        "warning_limit_bytes": checker.RSS_WARNING,
        "stop_limit_bytes": checker.RSS_WATCHDOG,
        "resource_warning": False,
        "warning_crossed": False,
        "warning_sample_index": None,
        "warning_timestamp_ns": None,
        "observed_descendant_pids": observed,
        "last_sample": samples[-1],
        "stage_summaries": stage_stats,
    }
    return process_path, process, stage_stats, stage_pids


def _make_cache(root: Path, children_dir: Path, manifests_dir: Path) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    cache_dir = root / "jit_cache"
    cache_dir.mkdir()
    initial_body = {"cache_dir": str(cache_dir), "artifacts": [], "artifact_count": 0}
    initial_path = manifests_dir / "initial.json"
    _write_json(initial_path, initial_body)
    initial = {"path": str(initial_path), "sha256": _sha(initial_path), "artifact_count": 0, "manifest": initial_body}
    group_entries: list[dict[str, object]] = []
    children: list[dict[str, object]] = []
    all_modules: list[str] = []
    previous: list[dict[str, object]] = []
    for index, group in enumerate(checker.GROUPS):
        count, roles = checker.GROUP_ROLES[group]
        added: list[dict[str, object]] = []
        for component in range(count):
            name = f"module_{index:02d}_{component}.so"
            target = cache_dir / name
            target.write_bytes(f"module-{group}-{component}".encode())
            item = {"relative_path": name, "bytes": target.stat().st_size, "sha256": _sha(target)}
            added.append(item)
            all_modules.append(name)
        current = previous + added
        current.sort(key=lambda item: item["relative_path"])
        body = {"cache_dir": str(cache_dir), "artifacts": current, "artifact_count": len(current)}
        manifest_path = manifests_dir / f"{index:02d}-{group.replace('-', '_')}.json"
        _write_json(manifest_path, body)
        group_entries.append({"group": group, "path": str(manifest_path), "sha256": _sha(manifest_path), "artifact_count": len(current), "new_module_basenames": sorted(Path(item["relative_path"]).name for item in added)})
        output_dir = children_dir
        record_path = output_dir / f"{index:02d}.json"
        stdout = output_dir / f"{index:02d}.stdout"
        stderr = output_dir / f"{index:02d}.stderr"
        stdout.write_bytes(b"")
        stderr.write_bytes(b"")
        command = [str(PYTHON), "-m", "benchmarks.run_task038_full3d_jit_precompile", "--group", group, "--cache-dir", str(cache_dir), "--record", str(record_path), "--expected-source-sha", SOURCE, "--input", str(INPUT)]
        child_payload = {
            "schema": "task038.full3d.jit-split.child-record.v1",
            "stage": "j3-split-precompile-child",
            "group": group,
            "source_sha": SOURCE,
            "branch": checker.BRANCH,
            "command": command,
            "input": {"path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": checker.PROFILE},
            "cache": {"cache_dir": str(cache_dir), "jit_options": {}},
            "facts": {"mode_count": 80, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "group_facts": {"compiled_form_count": count, "form_roles": list(roles)}},
            "architecture": {"matrix": False, "factor": False, "pc": False, "rhs_vector": False, "surface_carrier": False, "dtn_carrier": False, "solve": False, "recovery": False, "compile": True, "mesh": True, "jit": True, "pde": False, "compiler_descendant_authority": "parent_watchdog"},
            "runtime": _runtime(),
            "raw_facts_only": True,
        }
        _write_json(record_path, child_payload)
        children.append({
            "group": group,
            "pid": 200000 + index,
            "returncode": 0,
            "natural_exit": True,
            "stop_reason": "natural_exit",
            "descendants_gone": True,
            "record_path": str(record_path),
            "record_sha256": _sha(record_path),
            "stdout_path": str(stdout),
            "stdout_sha256": _sha(stdout),
            "stderr_path": str(stderr),
            "stderr_sha256": _sha(stderr),
            "process": None,
            "added_artifacts": added,
            "new_module_basenames": sorted(Path(item["relative_path"]).name for item in added),
            "cache_manifest_path": str(manifest_path),
            "cache_manifest_sha256": _sha(manifest_path),
            "cache_artifact_count": len(current),
        })
        previous = current
    before_path = manifests_dir / "before_solver.json"
    after_path = manifests_dir / "after_diagnostic.json"
    _write_json(before_path, {"cache_dir": str(cache_dir), "artifacts": previous, "artifact_count": len(previous)})
    _write_json(after_path, {"cache_dir": str(cache_dir), "artifacts": previous, "artifact_count": len(previous)})
    before_body = {"cache_dir": str(cache_dir), "artifacts": previous, "artifact_count": len(previous)}
    cache = {
        "initial_empty": True,
        "initial_manifest": initial,
        "group_manifests": group_entries,
        "before_solver": {"path": str(before_path), "sha256": _sha(before_path), "artifact_count": len(previous), "manifest": before_body},
        "after_diagnostic": {"path": str(after_path), "sha256": _sha(after_path), "artifact_count": len(previous), "manifest": before_body},
        "precompiled_module_basenames": sorted(all_modules),
        "deferred_incident_module_basenames": [],
        "solver_unchanged": True,
    }
    return cache, children, sorted(all_modules)


def _write_checkpoint_authority(checkpoint_dir: Path) -> tuple[str, str]:
    values = np.zeros(checker.CHECKPOINT_VECTOR_SHAPE, dtype=np.complex128)
    shard_path = checkpoint_dir / "solution_rank0.npy"
    np.save(shard_path, values, allow_pickle=False)
    descriptor = {
        "relative_path": shard_path.name,
        "bytes": shard_path.stat().st_size,
        "sha256": _sha(shard_path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }
    manifest = {
        "schema": checker.CHECKPOINT_SCHEMA,
        "iteration": checker.CHECKPOINT["iteration"],
        "explicit_true_residual": checker.CHECKPOINT["stored_explicit_true_residual"],
        "input_identity_sha256": checker.CHECKPOINT["input_identity_sha256"],
        "operator_identity_sha256": checker.CHECKPOINT["operator_identity_sha256"],
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        "source_sha": checker.CHECKPOINT["source_sha"],
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
        "ranks": [
            {
                "rank": 0,
                "ownership": {
                    "rank": 0,
                    "ownership_range": [0, checker.CHECKPOINT_GLOBAL_SIZE],
                    "local_size": checker.CHECKPOINT_LOCAL_SIZE,
                    "global_size": checker.CHECKPOINT_GLOBAL_SIZE,
                },
                "solution": descriptor,
            }
        ],
    }
    manifest_path = checkpoint_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return _sha(manifest_path), descriptor["sha256"]


def _synthetic_checkpoint_authority(tmp_path: Path) -> dict[str, object]:
    probe_dir = tmp_path / "checkpoint-authority-probe"
    probe_dir.mkdir()
    manifest_sha, shard_sha = _write_checkpoint_authority(probe_dir)
    return {
        **checker.CHECKPOINT,
        "manifest_sha256": manifest_sha,
        "shard_sha256": shard_sha,
    }


def _make_fixture(
    tmp_path: Path,
    *,
    f2_negative: bool = False,
    span_negative: bool = False,
    identity_negative: bool = False,
    checkpoint_failure: bool = False,
) -> tuple[Path, Path, list[str]]:
    root = tmp_path / "f2-root"
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    marker_dir = root / "markers"
    children_dir = root / "children"
    solver_dir = root / "solver"
    manifests_dir = root / "cache_manifests"
    raw_dir = root / "diagnostic_raw"
    checkpoint_dir = tmp_path / "frozen-checkpoint"
    for directory in (marker_dir, children_dir, solver_dir, manifests_dir, raw_dir, checkpoint_dir):
        directory.mkdir()
    manifest_sha, shard_sha = _write_checkpoint_authority(checkpoint_dir)
    assert manifest_sha == checker.CHECKPOINT["manifest_sha256"]
    assert shard_sha == checker.CHECKPOINT["shard_sha256"]
    process_path, process, stage_stats, stage_pids = _make_process(root)
    cache, children, modules = _make_cache(root, children_dir, manifests_dir)
    for child, stage in zip(children, (f"precompile:{group}" for group in checker.GROUPS)):
        child["process"] = _monitor(stage_pids[stage], stage_stats[stage])
    diagnostic_stdout = solver_dir / "diagnostic.stdout"
    diagnostic_stderr = solver_dir / "diagnostic.stderr"
    diagnostic_stdout.write_bytes(b"")
    diagnostic_stderr.write_bytes(b"")
    q = np.eye(32, dtype=np.complex128)
    residual = np.zeros(32, dtype=np.complex128)
    residual[0] = checker.CHECKPOINT["stored_explicit_true_residual"]
    r_factor = np.eye(32, dtype=np.complex128)
    coefficients = q.conj().T @ residual
    projected = q @ coefficients
    perpendicular = residual - projected
    vector_path = raw_dir / "diagnostic_vectors.npz"
    np.savez(vector_path, q=q, r_factor=r_factor, residual=residual, coefficients=coefficients, projected=projected, perpendicular=perpendicular)
    vector_facts = {"path": str(vector_path), "sha256": _sha(vector_path), "bytes": vector_path.stat().st_size, "roles": ["q", "r_factor", "residual", "coefficients", "projected", "perpendicular"]}
    scalar_one = _facts(np.array([1.0 + 0.0j]))
    scalar_zero = _facts(np.array([0.0 + 0.0j]))
    worker_f2 = {
        "status": "observed",
        "identity_gate_passed": True,
        "identity_failures": [],
        "checkpoint": {
            "manifest_sha256": checker.CHECKPOINT["manifest_sha256"],
            "iteration": checker.CHECKPOINT["iteration"],
            "explicit_true_residual": checker.CHECKPOINT["stored_explicit_true_residual"],
            "rank": 0,
            "restored_shard_sha256": checker.CHECKPOINT["shard_sha256"],
        },
        "stored_true_residual": checker.CHECKPOINT["stored_explicit_true_residual"],
        "recomputed_true_residual": checker.CHECKPOINT["stored_explicit_true_residual"],
        "relative_difference": 0.0,
        "finite": True,
        "rhs_input_unchanged": True,
        "solution_input_unchanged": True,
        "solution_finite": True,
        "residual_action_finite": True,
        "owned_slave_max": 0.0,
        "residual_action_count": 1,
        "checkpoint_solution_before": scalar_zero,
        "checkpoint_solution_after": scalar_zero,
        "rhs_before": scalar_one,
        "rhs_after": scalar_one,
        "exact_action_output": scalar_zero,
        "residual": _facts(residual),
    }
    column_facts = [{"mode_index": mode, "modal_rhs_norm": 1.0, "modal_rhs": scalar_one, "pc_output": scalar_one, "action_output": scalar_one, "modal_input_unchanged": True, "pc_input_unchanged": True, "action_input_unchanged": True, "r_diagonal_abs": 1.0, "qr_reconstruction_numerator": 0.0, "qr_reconstruction_denominator": 1.0, "qr_reconstruction_relative": 0.0} for mode in checker.SELECTED_MODE_INDICES]
    worker_f3 = {"status": "observed", "selector": {"schema": checker.SELECTOR_SCHEMA, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "selected_mode_indices": list(checker.SELECTED_MODE_INDICES), "selected_rank": 32, "selector_payload_sha256": checker.SELECTOR_SHA256}, "rank": 32, "condition_ratio": 1.0, "condition_finite": True, "orthogonality": 0.0, "qr_reconstruction_relative": 0.0, "projection_repeat_relative": 0.0, "captured_energy": 1.0, "rho": 0.0, "ideal_projected_true_residual_relative": 0.0, "pc_apply_count": 32, "exact_action_count": 32, "modal_rhs_apply_count": 32, "column_facts": column_facts, "vectors": vector_facts}
    worker_architecture = dict(checker.EXPECTED_ARCHITECTURE)
    lifecycle_names = list(checker.F2_MARKER_ORDER[20:32])
    marker_names = list(checker.F2_MARKER_ORDER)
    source_payload = {"before": scalar_one, "after": scalar_one, "input_unchanged": True}
    if checkpoint_failure:
        vector_path.unlink()
        vector_facts = None
        worker_f2 = {
            "status": "checkpoint_restore_failed",
            "identity_gate_passed": True,
            "identity_failures": [],
            "checkpoint_solution_before": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "checkpoint_solution_after": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "rhs_before": scalar_one,
            "rhs_after": scalar_one,
            "exact_action_output": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "residual": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "stored_true_residual": checker.CHECKPOINT["stored_explicit_true_residual"],
            "recomputed_true_residual": None,
            "relative_difference": None,
            "finite": None,
            "rhs_input_unchanged": True,
            "solution_input_unchanged": None,
            "solution_finite": None,
            "residual_action_finite": None,
            "owned_slave_max": scalar_one["owned_slave_max"],
            "residual_action_count": 0,
        }
        worker_f3 = {"status": "not_run_by_f2_checkpoint_gate"}
        worker_architecture.update({"checkpoint_read": False, "basis_pc_count": 0, "basis_action_count": 0, "retains_q": False, "retains_r": False, "residual_action_count": 0})
        lifecycle_names = ["bundle_built", "source_built", "checkpoint_restore_started", "release_started", "release_complete"]
        marker_names = list(checker.F2_MARKER_ORDER[:23]) + list(checker.F2_MARKER_ORDER[30:33])
        source_payload = {"before": scalar_one}
    elif identity_negative:
        vector_path.unlink()
        vector_facts = None
        worker_f2 = {
            "status": "identity_gate_failed",
            "identity_gate_passed": False,
            "identity_failures": ["operator_identity_sha256 does not match checkpoint authority"],
            "checkpoint_solution_before": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "checkpoint_solution_after": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "rhs_before": scalar_one,
            "rhs_after": scalar_one,
            "exact_action_output": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "residual": {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None},
            "stored_true_residual": checker.CHECKPOINT["stored_explicit_true_residual"],
            "recomputed_true_residual": None,
            "relative_difference": None,
            "finite": None,
            "rhs_input_unchanged": None,
            "solution_input_unchanged": None,
            "solution_finite": None,
            "residual_action_finite": None,
            "owned_slave_max": None,
            "residual_action_count": 0,
        }
        worker_f3 = {"status": "not_run_by_f2_identity_gate"}
        worker_architecture.update({"checkpoint_read": False, "basis_pc_count": 0, "basis_action_count": 0, "retains_q": False, "retains_r": False})
        worker_architecture["residual_action_count"] = 0
        lifecycle_names = ["bundle_built", "source_built", "release_started", "release_complete"]
        marker_names = list(checker.F2_MARKER_ORDER[:22]) + list(checker.F2_MARKER_ORDER[30:33])
    elif f2_negative:
        vector_path.unlink()
        np.savez(vector_path, residual=residual)
        vector_facts = {"path": str(vector_path), "sha256": _sha(vector_path), "bytes": vector_path.stat().st_size, "roles": ["residual"]}
        worker_f2["relative_difference"] = 0.25
        worker_f2["solution_input_unchanged"] = False
        worker_f3 = {"status": "not_run_by_f2_residual_gate"}
        worker_architecture.update({"basis_pc_count": 0, "basis_action_count": 0, "retains_q": False, "retains_r": False})
        lifecycle_names = list(checker.F2_MARKER_ORDER[20:26]) + list(checker.F2_MARKER_ORDER[30:32])
        marker_names = list(checker.F2_MARKER_ORDER[:26]) + list(checker.F2_MARKER_ORDER[30:33])
    elif span_negative:
        vector_path.unlink()
        np.savez(vector_path, q=q[:, :1], r_factor=r_factor[:1, :1], residual=residual)
        vector_facts = {"path": str(vector_path), "sha256": _sha(vector_path), "bytes": vector_path.stat().st_size, "roles": ["q", "r_factor", "residual"]}
        worker_f3 = {
            "status": "span_gate_failed",
            "selector": {"schema": checker.SELECTOR_SCHEMA, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "selected_mode_indices": list(checker.SELECTED_MODE_INDICES), "selected_rank": 32, "selector_payload_sha256": checker.SELECTOR_SHA256},
            "rank": 1,
            "accepted_rank": 1,
            "condition_ratio": None,
            "condition_finite": None,
            "orthogonality": None,
            "qr_reconstruction_relative": 0.0,
            "projection_repeat_relative": None,
            "captured_energy": None,
            "rho": None,
            "ideal_projected_true_residual_relative": None,
            "pc_apply_count": 2,
            "exact_action_count": 2,
            "modal_rhs_apply_count": 2,
            "column_facts": column_facts[:1],
            "failed_column": {"column_index": 1, "mode_index": checker.SELECTED_MODE_INDICES[1], "reason": "dependent MGS column", "pc_apply_count": 2, "exact_action_count": 2, "modal_rhs_apply_count": 2},
            "vectors": vector_facts,
        }
        worker_architecture.update({"basis_pc_count": 2, "basis_action_count": 2, "retains_q": True, "retains_r": True})
        lifecycle_names = list(checker.F2_MARKER_ORDER[20:26]) + ["basis_started", "basis_complete"] + list(checker.F2_MARKER_ORDER[30:32])
        marker_names = list(checker.F2_MARKER_ORDER[:28]) + list(checker.F2_MARKER_ORDER[30:33])
    worker_path = solver_dir / "diagnostic_record.json"
    worker_command = [str(PYTHON), "-m", checker.WORKER_MODULE, "--artifact-root", str(root), "--cache-dir", str(root / "jit_cache"), "--marker-dir", str(marker_dir), "--checkpoint-dir", str(checkpoint_dir), "--record", str(worker_path), "--expected-source-sha", SOURCE, "--expected-mpi-size", "1", "--input", str(INPUT)]
    worker_identity = {
        "input_file_sha256": checker.INPUT_SHA256,
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        "profile": checker.WORKER_PROFILE,
        "input_identity_sha256": checker.CHECKPOINT["input_identity_sha256"],
        "operator_identity_sha256": checker.CHECKPOINT["operator_identity_sha256"],
        "checkpoint_input_identity_sha256": checker.CHECKPOINT["input_identity_sha256"],
        "checkpoint_operator_identity_sha256": checker.CHECKPOINT["operator_identity_sha256"],
    }
    if identity_negative:
        worker_identity["operator_identity_sha256"] = "c" * 64
    worker_architecture["residual_action_count"] = worker_f2["residual_action_count"]
    worker = {
        "schema": checker.WORKER_SCHEMA, "stage": "f2-f3-floquet-wave-diagnostic", "workflow": "f2-f3-floquet-wave", "source_sha": SOURCE, "branch": checker.BRANCH, "command": worker_command, "provenance": _runtime(),
        "identity": worker_identity,
        "checkpoint": {**checker.CHECKPOINT, "solution_only": True},
        "paths": {"artifact_root": str(root), "cache_dir": str(root / "jit_cache"), "marker_dir": str(marker_dir), "raw_dir": str(raw_dir), "record": str(worker_path), "vectors": vector_facts, "checkpoint_dir": str(checkpoint_dir)},
        "mode": {"count": 80, "manifest_sha256": checker.MODE_MANIFEST_SHA256, "selector_schema": checker.SELECTOR_SCHEMA, "selector_payload_sha256": checker.SELECTOR_SHA256, "selected_mode_indices": list(checker.SELECTED_MODE_INDICES)},
        "ffcx_calls": [{"index": index, "module_name": f"module_{index}", "module_file": str(root / "jit_cache" / modules[index]), "code": [None, None], "cache_hit": True} for index in range(11)], "expected_ffcx_call_count": 11,
        "source": source_payload,
        "f2": worker_f2,
        "f3": worker_f3,
        "architecture": worker_architecture, "lifecycle": {"marker_schema": checker.MARKER_SCHEMA, "marker_names": lifecycle_names}, "raw_facts_only": True,
    }
    _write_json(worker_path, worker)
    diagnostic_monitor = _monitor(stage_pids["diagnostic"], stage_stats["diagnostic"])
    diagnostic = {"command": worker_command, "process": diagnostic_monitor, "record_path": str(worker_path), "record_sha256": _sha(worker_path), "stdout_path": str(diagnostic_stdout), "stdout_sha256": _sha(diagnostic_stdout), "stderr_path": str(diagnostic_stderr), "stderr_sha256": _sha(diagnostic_stderr), "cache_unchanged": True}
    marker_entries = []
    marker_time = 1
    for index, name in enumerate(checker.F2_MARKER_ORDER):
        if name not in marker_names:
            continue
        stage = "f2-f3-floquet-wave-parent" if index < 20 or name == "parent_complete" else "f2-f3-floquet-wave-diagnostic"
        facts = {"stage": stage, "artifact_root": str(root), "cache_dir": str(root / "jit_cache"), "source_sha": SOURCE, "watchdog_stop_bytes": checker.RSS_WATCHDOG}
        if stage.endswith("diagnostic"):
            facts["mpi_size"] = 1
        if name == "parent_complete":
            facts["compiler_descendant_count"] = 0
        marker_path = marker_dir / f"{index:03d}_{name}.json"
        _write_json(marker_path, {"schema": checker.MARKER_SCHEMA, "name": name, "marker_index": index, "timestamp_ns": marker_time, "facts": facts})
        marker_entries.append({"name": name, "path": str(marker_path), "sha256": _sha(marker_path)})
        marker_time += 1
    marker_manifest_path = root / "marker_manifest.json"
    _write_json(marker_manifest_path, marker_entries)
    parent_record_path = root / "parent_record.json"
    parent_command = [str(PYTHON), "-m", checker.PARENT_MODULE, "--workflow", "f2-f3-floquet-wave", "--artifact-root", str(root), "--record", str(parent_record_path), "--source-sha", SOURCE, "--input", str(INPUT), "--expected-mpi-size", "1", "--checkpoint-dir", str(checkpoint_dir)]
    parent_record = {
        "schema": checker.PARENT_SCHEMA, "stage": "f2-f3-floquet-wave-parent", "workflow": "f2-f3-floquet-wave", "source_sha": SOURCE, "branch": checker.BRANCH, "command": parent_command, "identity": {"input_path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": checker.PROFILE, "runtime": {"source_sha": SOURCE, "branch": checker.BRANCH, "clean_source_tree": True, "qualified_activation": "1", "python_executable": str(PYTHON), "python_prefix": str(ROOT / ".venv")}},
        "paths": {"artifact_root": str(root), "cache_dir": str(root / "jit_cache"), "marker_dir": str(marker_dir), "record": str(parent_record_path), "process_samples": str(process_path), "marker_manifest": str(marker_manifest_path), "children_dir": str(children_dir), "solver_dir": str(solver_dir), "cache_manifests_dir": str(manifests_dir), "diagnostic_record": str(worker_path), "diagnostic_raw_dir": str(raw_dir), "checkpoint_dir": str(checkpoint_dir)}, "marker_schema": checker.MARKER_SCHEMA, "sample_schema": checker.SAMPLE_SCHEMA, "markers": {"names": marker_names, "manifest_path": str(marker_manifest_path), "manifest_sha256": _sha(marker_manifest_path)}, "process": process, "children": children, "diagnostic": diagnostic, "cache": cache, "architecture": {**checker.EXPECTED_PARENT_ARCHITECTURE, "checkpoint_read": worker_architecture["checkpoint_read"], "residual_action_count": worker_architecture["residual_action_count"], "f3_status": worker_f3["status"], "basis_pc_count": worker_architecture["basis_pc_count"], "basis_action_count": worker_architecture["basis_action_count"], "retains_q": worker_architecture["retains_q"], "retains_r": worker_architecture["retains_r"]}, "raw_facts_only": True,
    }
    _write_json(parent_record_path, parent_record)
    return root, parent_record_path, modules


def _refresh_worker_hashes(record_path: Path) -> None:
    parent = json.loads(record_path.read_text(encoding="utf-8"))
    worker_path = Path(parent["diagnostic"]["record_path"])
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    vector = Path(worker["paths"]["vectors"]["path"])
    descriptor = {
        "path": str(vector),
        "sha256": _sha(vector),
        "bytes": vector.stat().st_size,
        "roles": worker["paths"]["vectors"]["roles"],
    }
    worker["paths"]["vectors"] = descriptor
    if worker["f3"].get("status") == "observed":
        worker["f3"]["vectors"] = descriptor
    worker_path.write_text(
        json.dumps(worker, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    parent["diagnostic"]["record_sha256"] = _sha(worker_path)
    record_path.write_text(
        json.dumps(parent, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_f2_f3_parser_and_streaming_mgs_contract() -> None:
    args = parent.build_parser().parse_args(["--workflow", parent.WORKFLOW_F2_F3, "--artifact-root", "/tmp/root", "--record", "/tmp/root/parent_record.json", "--source-sha", SOURCE, "--input", str(INPUT), "--checkpoint-dir", "/tmp/checkpoint"])
    assert args.workflow == parent.WORKFLOW_F2_F3
    assert parent._diagnostic_command(Path("/tmp/root"), Path("/tmp/root/jit_cache"), Path("/tmp/root/markers"), Path("/tmp/checkpoint"), INPUT, Path("/tmp/root/solver/diagnostic_record.json"), SOURCE)[2] == checker.WORKER_MODULE
    columns = [np.array([1.0, 0.0, 0.0], dtype=np.complex128), np.array([0.0, 1.0, 0.0], dtype=np.complex128)]
    q, r = two_pass_mgs(columns)
    appended, coefficients, norm = two_pass_mgs_append(q[:, :1], columns[1])
    assert np.linalg.norm(q @ r - np.column_stack(columns)) <= 1e-12
    assert np.linalg.norm(appended - q[:, 1]) <= 1e-12
    assert np.linalg.norm(coefficients) <= 1e-12
    assert abs(norm - 1.0) <= 1e-12
    helper_source = inspect.getsource(two_pass_mgs_append)
    assert "np.ascontiguousarray" not in helper_source
    backing = np.zeros((4, 4), dtype=np.complex128)
    backing[:, :2] = np.eye(4, 2, dtype=np.complex128)
    backing_before = backing.copy()
    q_view = backing[:, :2]
    assert q_view.flags.c_contiguous is False
    normalized, _, _ = two_pass_mgs_append(q_view, np.array([0.0, 0.0, 1.0, 0.0]))
    assert np.array_equal(backing, backing_before)
    assert np.linalg.norm(normalized - np.array([0.0, 0.0, 1.0, 0.0])) <= 1e-12
    assert "q.conj().T @ q" not in (ROOT / "benchmarks/run_task038_full3d_floquet_wave_checkpoint_diagnostic.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "benchmarks/run_task038_full3d_floquet_wave_checkpoint_diagnostic.py").read_text(encoding="utf-8")
    assert worker_source.index("z = upper_cycle.apply(modal_rhs)") < worker_source.index("f_after_sha = _array_sha")
    assert worker_source.index("f_after_sha = _array_sha") < worker_source.index("modal_rhs.destroy()") < worker_source.index('bundle["physical_action"].apply(z, y)')
    mgs_call = worker_source.index("q_column, mgs_coefficients, norm = two_pass_mgs_append")
    assert worker_source.index('bundle["physical_action"].apply(z, y)') < worker_source.index("z.destroy()") < worker_source.index("y_values = _vector_view(y)") < mgs_call
    assert mgs_call < worker_source.index("y.destroy()")
    assert inspect.signature(parent._monitor_child).parameters["stop_limit_bytes"].default == parent.RSS_HARD_LIMIT
    assert inspect.signature(parent._run_child).parameters["stop_limit_bytes"].default == parent.RSS_HARD_LIMIT
    assert parent.F2_RSS_WATCHDOG == 1_950_000_000


def test_synthetic_f2_f3_checker_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "CHECKPOINT", _synthetic_checkpoint_authority(tmp_path))
    _root, record_path, _modules = _make_fixture(tmp_path)
    result = checker.check_record(record_path, SOURCE)
    assert result["passed"] is True
    assert result["classification"] == "F2_F3_COLD_STAGED_PASS"
    assert result["metrics"]["precompiled_module_count"] == 11
    assert result["metrics"]["rank"] == 32


def test_f2_f3_checker_mutations_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "CHECKPOINT", _synthetic_checkpoint_authority(tmp_path))
    root, record_path, modules = _make_fixture(tmp_path / "cache")
    (root / "jit_cache" / modules[0]).write_bytes(b"mutation")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE)
    root, record_path, _modules = _make_fixture(tmp_path / "checkpoint-authority")
    manifest_path = tmp_path / "checkpoint-authority/frozen-checkpoint/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["iteration"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = checker.check_record(record_path, SOURCE)
    assert result["classification"] == "F2_IDENTITY_OR_ALGEBRA_GATE_FAIL"
    root, record_path, _modules = _make_fixture(tmp_path / "marker")
    marker = root / "markers/020_bundle_built.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["marker_index"] = 19
    marker.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE)
    root, record_path, _modules = _make_fixture(tmp_path / "vector")
    vector = root / "diagnostic_raw/diagnostic_vectors.npz"
    with np.load(vector, allow_pickle=False) as arrays:
        values = {name: np.asarray(arrays[name]) for name in arrays.files}
    values["q"][0, 0] = 2.0
    np.savez(vector, **values)
    _refresh_worker_hashes(record_path)
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE)
    root, record_path, _modules = _make_fixture(tmp_path / "qr", f2_negative=False)
    worker_path = root / "solver/diagnostic_record.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    worker["f3"]["column_facts"][0]["qr_reconstruction_numerator"] = 1.0
    worker["f3"]["column_facts"][0]["qr_reconstruction_relative"] = 1.0
    worker_path.write_text(json.dumps(worker), encoding="utf-8")
    _refresh_worker_hashes(record_path)
    with pytest.raises(checker.CheckError) as error:
        checker.check_record(record_path, SOURCE)
    assert error.value.kind == "span"
    root, record_path, _modules = _make_fixture(tmp_path / "span-negative", span_negative=True)
    result = checker.check_record(record_path, SOURCE)
    assert result["passed"] is False
    assert result["classification"] == "FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE"
    assert result["metrics"]["rank"] == 1
    assert result["metrics"]["pc_apply_count"] == 2
    assert result["metrics"]["failed_column"]["column_index"] == 1
    root, record_path, _modules = _make_fixture(tmp_path / "f2-negative", f2_negative=True)
    result = checker.check_record(record_path, SOURCE)
    assert result["passed"] is False
    assert result["classification"] == "F2_IDENTITY_OR_ALGEBRA_GATE_FAIL"
    assert any("relative residual difference" in item for item in result["gate_failures"])
    root, record_path, _modules = _make_fixture(tmp_path / "residual-hash", f2_negative=True)
    vector = root / "diagnostic_raw/diagnostic_vectors.npz"
    with np.load(vector, allow_pickle=False) as arrays:
        values = {name: np.asarray(arrays[name]) for name in arrays.files}
    values["residual"][0] *= 2.0
    np.savez(vector, **values)
    _refresh_worker_hashes(record_path)
    result = checker.check_record(record_path, SOURCE)
    assert any("residual hash" in item for item in result["gate_failures"])
    root, record_path, _modules = _make_fixture(tmp_path / "checkpoint-reader", checkpoint_failure=True)
    with pytest.raises(checker.CheckError) as error:
        checker.check_record(record_path, SOURCE)
    assert error.value.kind == "contract"
    assert "checkpoint reader failed" in str(error.value)
    root, record_path, _modules = _make_fixture(tmp_path / "nonfinite-f2", f2_negative=True)
    worker_path = root / "solver/diagnostic_record.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    nonfinite = dict(worker["f2"]["exact_action_output"])
    nonfinite.update({"finite": False, "norm": None, "owned_slave_max": None})
    worker["f2"]["exact_action_output"] = nonfinite
    worker["f2"]["residual_action_finite"] = False
    nonfinite_solution = dict(worker["f2"]["checkpoint_solution_after"])
    nonfinite_solution.update({"finite": False, "norm": None, "owned_slave_max": None})
    worker["f2"]["checkpoint_solution_after"] = nonfinite_solution
    worker["f2"]["solution_finite"] = False
    worker_path.write_text(json.dumps(worker), encoding="utf-8")
    _refresh_worker_hashes(record_path)
    result = checker.check_record(record_path, SOURCE)
    assert result["classification"] == "F2_IDENTITY_OR_ALGEBRA_GATE_FAIL"
    assert any("non-finite" in item for item in result["gate_failures"])
    root, record_path, _modules = _make_fixture(tmp_path / "identity-negative", identity_negative=True)
    result = checker.check_record(record_path, SOURCE)
    assert result["passed"] is False
    assert result["classification"] == "F2_IDENTITY_OR_ALGEBRA_GATE_FAIL"
    assert "operator_identity_sha256" in result["gate_failures"][0]


def test_f2_f3_lazy_import_boundary_and_independent_checker() -> None:
    worker_path = ROOT / "benchmarks/run_task038_full3d_floquet_wave_checkpoint_diagnostic.py"
    worker_source = worker_path.read_text(encoding="utf-8")
    assert "np.column_stack" not in worker_source
    assert "np.savez_compressed" not in worker_source
    assert "PETSc.KSP" not in worker_source
    assert "createKSP" not in worker_source
    assert "Z/AZ" not in worker_source
    for path in (worker_path, Path(__file__).resolve().parents[2] / "benchmarks/task038_full3d_floquet_wave_checkpoint_diagnostic_checker.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Import):
                assert all(alias.name not in {"mpi4py", "petsc4py", "dolfinx"} for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {"mpi4py", "petsc4py", "dolfinx", "src", "benchmarks.run_task038_full3d_jit_staged_parent"}
