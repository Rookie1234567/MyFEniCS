"""Pure contract tests for the J3 split cold-staged parent and checker."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task038_full3d_jit_solver_bundle as solver
from benchmarks import run_task038_full3d_jit_staged_parent as parent
from benchmarks import task038_full3d_jit_staging as staging
from benchmarks import task038_full3d_jit_staged_checker as checker
from benchmarks import task038_full3d_same_mesh_hcurl_pmg_p0_physical_checker as p0_checker


ROOT = Path(__file__).resolve().parents[2]
INPUT = (ROOT / "input/templates/full3d_iterative_example.dat").resolve()
SOURCE_SHA = "a" * 40
PYTHON = ROOT / ".venv" / "bin" / "python"
GROUP_COUNTS = {group: value[0] for group, value in checker.EXPECTED_GROUP_ROLES.items()}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile() -> dict[str, object]:
    return dict(checker.EXPECTED_PROFILE)


def _runtime() -> dict[str, object]:
    return {
        "source_sha": SOURCE_SHA,
        "branch": checker.BRANCH,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(PYTHON),
        "python_prefix": str(ROOT / ".venv"),
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        "abi_modules": {name: str(ROOT / ".venv" / "lib" / f"{name}.so") for name in ("mpi4py", "petsc4py", "dolfinx", "basix")},
    }


def _physical_audit() -> dict[str, object]:
    components = {
        name: {
            "schema": "task038.fullspace-mpc-form-action.v1",
            "operator": "uncondensed_fullspace_curl_mass_form",
            "slave_row_identity": slave_identity,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
        }
        for name, slave_identity in (
            ("curl_curl", True),
            ("complex_material_mass", False),
        )
    }
    return {
        "schema": "task038.fullspace-physical-action.v1",
        "operator": "A_volume_plus_dynamic_DtN",
        "physical_form": "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn",
        "volume_component_count": 2,
        "volume_components": ["curl_curl", "complex_material_mass"],
        "volume_action": {
            "schema": "task038.fullspace-split-volume-action.v1",
            "operator": "A_curl_curl_plus_A_complex_material_mass",
            "component_count": 2,
            "components": components,
            "constraint_identity_rows_exactly_once": True,
            "third_persistent_sum_vector": False,
        },
    }


def _member(pid: int, ppid: int, stage: str, rss: int, pss: int) -> dict[str, object]:
    return {"pid": pid, "ppid": ppid, "comm": "worker" if pid != 4242 else "python", "state": "S", "cmdline": "python -m worker", "stage": stage, "rss_bytes": rss, "pss_bytes": pss, "swap_bytes": 0, "timestamp_ns": 10, "exit_code": None}


def _sample(stage: str, timestamp: int, descendant: int | None) -> dict[str, object]:
    members = [_member(4242, 1, stage, 100, 50)]
    if descendant is not None:
        members.append(_member(descendant, 4242, stage, 50, 25))
    return {"schema": checker.SAMPLE_SCHEMA, "root_pid": 4242, "stage": stage, "timestamp_ns": timestamp, "exit_code": None, "members": members, "unreadable_pids": [], "vanished_pids": [], "all_status_readable": True, "readability_retry_count": 0, "compiler_descendant_count": 0, "rss_bytes": sum(item["rss_bytes"] for item in members), "swap_bytes": 0, "pss_all_readable": True, "pss_bytes": sum(item["pss_bytes"] for item in members)}


def _monitor(pid: int, started: int, ended: int, sample_count: int = 3) -> dict[str, object]:
    return {"pid": pid, "process_group_id": pid, "started_ns": started, "ended_ns": ended, "returncode": 0, "natural_exit": True, "stop_reason": "natural_exit", "sample_count": sample_count, "peak_rss_bytes": 150, "max_swap_bytes": 0, "all_status_readable": True, "compiler_descendant_peak": 0, "observed_descendant_pids": [pid], "last_sample": None, "signals": [], "required_sigkill": False, "process_group_gone": True, "descendants_gone": True}


def _valid_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / "j3-root"
    cache = root / "jit_cache"
    marker_dir = root / "markers"
    children_dir = root / "children"
    solver_dir = root / "solver"
    manifests_dir = root / "cache_manifests"
    for path in (root, cache, marker_dir, children_dir, solver_dir, manifests_dir):
        path.mkdir()
    record_path = root / "parent_record.json"
    sample_path = root / "parent_process.jsonl"
    marker_manifest_path = root / "marker_manifest.json"

    marker_entries = []
    for marker_name in checker.EXPECTED_MARKERS:
        index = checker.MARKER_ORDER.index(marker_name)
        solver_start = checker.EXPECTED_MARKERS.index("positive_setup_started")
        solver_end = checker.EXPECTED_MARKERS.index("bundle_built")
        marker_stage = "j3-split-cold-staged-solver" if solver_start <= index <= solver_end else "j3-split-cold-staged-parent"
        facts: dict[str, object] = {"stage": marker_stage, "artifact_root": str(root), "cache_dir": str(cache), "source_sha": SOURCE_SHA}
        if marker_name.startswith("precompile_") and marker_name.endswith("_started"):
            facts["command"] = [str(PYTHON), "-m", checker.CHILD_MODULE]
        if marker_name == "solver_child_started":
            facts["command"] = [str(PYTHON), "-m", checker.SOLVER_MODULE]
        if marker_name == "parent_complete":
            facts["compiler_descendant_count"] = 0
        path = marker_dir / f"{index:03d}_{marker_name}.json"
        _write(path, {"schema": checker.MARKER_SCHEMA, "name": marker_name, "marker_index": index, "timestamp_ns": index + 1, "facts": facts})
        marker_entries.append({"name": marker_name, "path": str(path), "sha256": _sha(path)})
    _write(marker_manifest_path, marker_entries)

    stages = [*(f"precompile:{group}" for group in checker.GROUPS), "precompile:parent-only", "solver"]
    sample_values = []
    for index, stage in enumerate(stages):
        descendant = 5000 + index if stage != "precompile:parent-only" else None
        if stage == "solver":
            descendant = 6000
        sample_values.extend((_sample(stage, 100 + index * 10, descendant), _sample(stage, 101 + index * 10, descendant), _sample(stage, 102 + index * 10, None)))
    sample_path.write_text("".join(json.dumps(value, separators=(",", ":")) + "\n" for value in sample_values), encoding="utf-8")

    initial_manifest_path = manifests_dir / "initial.json"
    initial_manifest = {"cache_dir": str(cache), "artifacts": [], "artifact_count": 0}
    _write(initial_manifest_path, initial_manifest)
    child_entries = []
    artifacts: list[dict[str, object]] = []
    module_index = 0
    for group_index, group in enumerate(checker.GROUPS):
        count, roles = checker.EXPECTED_GROUP_ROLES[group]
        added = []
        for _ in range(count):
            relative = f"module_{module_index}.so"
            target = cache / relative
            target.write_bytes(f"module-{module_index}".encode())
            item = {"relative_path": relative, "bytes": target.stat().st_size, "sha256": _sha(target)}
            artifacts.append(item)
            added.append(item)
            module_index += 1
        manifest = {"cache_dir": str(cache), "artifacts": list(artifacts), "artifact_count": len(artifacts)}
        manifest_path = manifests_dir / f"{group_index:02d}-{group.replace('-', '_')}.json"
        _write(manifest_path, manifest)
        child_record = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.json"
        child_command = [str(PYTHON), "-m", checker.CHILD_MODULE, "--group", group, "--cache-dir", str(cache), "--record", str(child_record), "--expected-source-sha", SOURCE_SHA, "--input", str(INPUT)]
        group_facts = {"compiled_form_count": count, "form_roles": list(roles)}
        if group in {"physical-volume-curl", "physical-volume-mass"}:
            group_facts.update({"component": "curl" if group.endswith("curl") else "mass", "component_count": 1})
        _write(child_record, {"schema": checker.CHILD_RECORD_SCHEMA, "stage": "j3-split-precompile-child", "group": group, "source_sha": SOURCE_SHA, "branch": checker.BRANCH, "command": child_command, "input": {"path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": _profile()}, "cache": {"cache_dir": str(cache), "jit_options": {}}, "facts": {"group_facts": group_facts}, "architecture": {"matrix": False, "factor": False, "pc": False, "rhs_vector": False, "surface_carrier": False, "dtn_carrier": False, "solve": False, "recovery": False, "compile": True, "mesh": True, "jit": True, "pde": False}, "runtime": _runtime(), "raw_facts_only": True})
        stdout = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.stdout"
        stderr = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.stderr"
        stdout.write_bytes(b"")
        stderr.write_bytes(b"")
        pid = 5000 + group_index
        child_entries.append({"group": group, "command": child_command, "pid": pid, "returncode": 0, "natural_exit": True, "stop_reason": "natural_exit", "descendants_gone": True, "record_path": str(child_record), "record_sha256": _sha(child_record), "stdout_path": str(stdout), "stdout_sha256": _sha(stdout), "stderr_path": str(stderr), "stderr_sha256": _sha(stderr), "cache_manifest_path": str(manifest_path), "cache_manifest_sha256": _sha(manifest_path), "cache_artifact_count": len(artifacts), "added_artifacts": added, "new_module_basenames": [item["relative_path"] for item in added], "process": _monitor(pid, 100 + group_index * 10, 102 + group_index * 10)})

    before_path = manifests_dir / "before_solver.json"
    after_path = manifests_dir / "after_solver.json"
    final_manifest = {"cache_dir": str(cache), "artifacts": list(artifacts), "artifact_count": len(artifacts)}
    _write(before_path, final_manifest)
    _write(after_path, final_manifest)
    solver_record = solver_dir / "solver_record.json"
    module_names = sorted(f"module_{index}.so" for index in range(11))
    solver_module_indices = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10)
    calls = [{"index": index, "module_name": f"module_{module_index}", "module_file": str(cache / f"module_{module_index}.so"), "code": [None, None], "cache_hit": True} for index, module_index in enumerate(solver_module_indices)]
    solver_command = [str(PYTHON), "-m", checker.SOLVER_MODULE, "--cache-dir", str(cache), "--record", str(solver_record), "--marker-dir", str(marker_dir), "--expected-source-sha", SOURCE_SHA, "--expected-mpi-size", "1", "--input", str(INPUT)]
    solver_architecture = {"p6_matrix_free": True, "p6_global_aij": False, "high_order_global_aij": False, "global_dense_transfer": False, "numeric_allgather": False, "p3_sparse_matrix_built": True, "p1_sparse_matrix_built": True, "p1_direct_factor_built": True, "same_mesh_pmg_built": True, "streaming_dtn_action_built": True, "dtn_carrier_built": True, "dtn_carrier_lifetime": "transient_released", "physical_volume_action_built": True, "volume_component_count": 2, "volume_components": ["curl_curl", "complex_material_mass"], "monolithic_physical_volume": False, "rhs_built": False, "outer_ksp_built": False, "solve_run": False, "recovery_run": False, "bundle_destroyed_before_record": True}
    _write(solver_record, {"schema": checker.SOLVER_RECORD_SCHEMA, "stage": "j3-split-cold-staged-solver", "source_sha": SOURCE_SHA, "branch": checker.BRANCH, "command": solver_command, "identity": {"input_path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": _profile()}, "paths": {"artifact_root": str(root), "cache_dir": str(cache), "marker_dir": str(marker_dir), "record": str(solver_record)}, "runtime": _runtime(), "mode": {"count": 1, "manifest_sha256": checker.MODE_MANIFEST_SHA256, "dtn_quadrature_degree": 1}, "ffcx_calls": calls, "expected_ffcx_call_count": 10, "setup_audit": {}, "physical_audit": _physical_audit(), "architecture": solver_architecture, "marker_names": list(checker.EXPECTED_MARKERS[:-1]), "raw_facts_only": True})
    solver_stdout = solver_dir / "solver.stdout"
    solver_stderr = solver_dir / "solver.stderr"
    solver_stdout.write_bytes(b"")
    solver_stderr.write_bytes(b"")
    solver_process = _monitor(6000, 180, 182)
    solver_process["last_sample"] = None
    solver_info = {"command": solver_command, "process": solver_process, "record_path": str(solver_record), "record_sha256": _sha(solver_record), "stdout_path": str(solver_stdout), "stdout_sha256": _sha(solver_stdout), "stderr_path": str(solver_stderr), "stderr_sha256": _sha(solver_stderr), "before_solver_manifest_sha256": _sha(before_path), "after_solver_manifest_sha256": _sha(after_path), "cache_unchanged": True}

    process_summary = parent._process_summary(sample_path)
    record = {"schema": checker.RECORD_SCHEMA, "stage": "j3-split-cold-staged-parent", "source_sha": SOURCE_SHA, "branch": checker.BRANCH, "command": [str(PYTHON), "-m", checker.PARENT_MODULE, "--artifact-root", str(root), "--record", str(record_path), "--source-sha", SOURCE_SHA, "--input", str(INPUT)], "identity": {"input_path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": _profile(), "runtime": _runtime()}, "paths": {"artifact_root": str(root), "cache_dir": str(cache), "marker_dir": str(marker_dir), "record": str(record_path), "process_samples": str(sample_path), "marker_manifest": str(marker_manifest_path), "children_dir": str(children_dir), "solver_dir": str(solver_dir), "cache_manifests_dir": str(manifests_dir)}, "marker_schema": checker.MARKER_SCHEMA, "sample_schema": checker.SAMPLE_SCHEMA, "markers": {"names": list(checker.EXPECTED_MARKERS), "manifest_path": str(marker_manifest_path), "manifest_sha256": _sha(marker_manifest_path)}, "process": process_summary, "children": child_entries, "solver": solver_info, "cache": {"initial_empty": True, "initial_manifest": {"path": str(initial_manifest_path), "sha256": _sha(initial_manifest_path), "artifact_count": 0, "manifest": initial_manifest}, "group_manifests": [{"group": group, "path": child["cache_manifest_path"], "sha256": child["cache_manifest_sha256"], "artifact_count": child["cache_artifact_count"], "new_module_basenames": child["new_module_basenames"]} for group, child in zip(checker.GROUPS, child_entries)], "before_solver": {"path": str(before_path), "sha256": _sha(before_path), "artifact_count": 11, "manifest": final_manifest}, "after_solver": {"path": str(after_path), "sha256": _sha(after_path), "artifact_count": 11, "manifest": final_manifest}, "precompiled_module_basenames": module_names, "deferred_incident_module_basenames": ["module_8.so"], "solver_unchanged": True}, "architecture": solver_architecture, "raw_facts_only": True}
    _write(record_path, record)
    return record_path, root, record


def _j4_member(
    pid: int,
    ppid: int,
    stage: str,
    rss: int = 100,
    pss: int = 50,
    *,
    swap: int = 0,
    comm: str = "worker",
    cmdline: str = "python -m worker",
) -> dict[str, object]:
    return {
        "pid": pid,
        "ppid": ppid,
        "comm": comm,
        "state": "S",
        "cmdline": cmdline,
        "stage": stage,
        "rss_bytes": rss,
        "pss_bytes": pss,
        "swap_bytes": swap,
        "timestamp_ns": 1,
        "exit_code": None,
    }


def _j4_sample(
    stage: str,
    timestamp: int,
    descendant: int | None,
    *,
    root_rss: int = 100,
    child_rss: int = 50,
    swap: int = 0,
    compiler: bool = False,
) -> dict[str, object]:
    members = [_j4_member(4242, 1, stage, root_rss, 50, swap=swap, comm="python", cmdline="python -m parent")]
    if descendant is not None:
        members.append(
            _j4_member(
                descendant,
                4242,
                stage,
                child_rss,
                25,
                comm="gcc" if compiler else "worker",
                cmdline="gcc -c form.c" if compiler else "python -m child",
            )
        )
    return {
        "schema": p0_checker.SAMPLE_SCHEMA,
        "root_pid": 4242,
        "stage": stage,
        "timestamp_ns": timestamp,
        "exit_code": None,
        "members": members,
        "unreadable_pids": [],
        "vanished_pids": [],
        "all_status_readable": True,
        "readability_retry_count": 0,
        "compiler_descendant_count": int(compiler),
        "rss_bytes": sum(int(item["rss_bytes"]) for item in members),
        "swap_bytes": swap,
        "pss_all_readable": True,
        "pss_bytes": sum(int(item["pss_bytes"]) for item in members),
    }


def _j4_monitor(
    pid: int,
    started: int,
    ended: int,
    sample_count: int,
    *,
    peak: int = 150,
    swap: int = 0,
    compiler_peak: int = 0,
) -> dict[str, object]:
    return {
        "pid": pid,
        "process_group_id": pid,
        "started_ns": started,
        "ended_ns": ended,
        "returncode": 0,
        "natural_exit": True,
        "stop_reason": "natural_exit",
        "sample_count": sample_count,
        "peak_rss_bytes": peak,
        "max_swap_bytes": swap,
        "all_status_readable": True,
        "compiler_descendant_peak": compiler_peak,
        "observed_descendant_pids": [pid],
        "last_sample": None,
        "signals": [],
        "required_sigkill": False,
        "process_group_gone": True,
        "descendants_gone": True,
    }


def _j4_architecture() -> dict[str, object]:
    return {
        "p6_matrix_free": True,
        "p6_global_aij": False,
        "high_order_global_aij": False,
        "global_dense_transfer": False,
        "numeric_allgather": False,
        "p3_sparse_matrix_built": True,
        "p1_sparse_matrix_built": True,
        "p1_direct_factor_built": True,
        "same_mesh_pmg_built": True,
        "streaming_dtn_action_built": True,
        "dtn_carrier_built": True,
        "dtn_carrier_lifetime": "transient_released",
        "physical_volume_action_built": True,
        "volume_component_count": 2,
        "volume_components": ["curl_curl", "complex_material_mass"],
        "monolithic_physical_volume": False,
        "rhs_built": True,
        "outer_ksp_built": True,
        "solve_run": True,
        "recovery_run": False,
        "bundle_destroyed_before_record": True,
    }


def _j4_runtime() -> dict[str, object]:
    return {
        "source_sha": SOURCE_SHA,
        "branch": p0_checker.BRANCH,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(PYTHON),
        "python_prefix": str(ROOT / ".venv"),
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        "abi_modules": {name: str(ROOT / ".venv" / "lib" / f"{name}.so") for name in ("mpi4py", "petsc4py", "dolfinx", "basix")},
    }


def _j4_worker_command(root: Path, cache: Path, marker_dir: Path, worker_path: Path) -> list[str]:
    return [
        str(PYTHON),
        "-m",
        p0_checker.MODULE,
        "--workflow",
        p0_checker.J4_WORKFLOW,
        "--stage",
        "p0-physical",
        "--case",
        "p6-h10-mpi1",
        "--source",
        "physical_rhs",
        "--raw-dir",
        str(root / "worker_raw"),
        "--jit-cache-dir",
        str(cache),
        "--checkpoint-root",
        str(root / "checkpoints"),
        "--record",
        str(worker_path),
        "--expected-source-sha",
        SOURCE_SHA,
        "--expected-mpi-size",
        "1",
        "--input",
        str(INPUT),
        "--v14-marker-dir",
        str(marker_dir),
    ]


def _j4_write_worker_markers(raw_dir: Path) -> dict[str, int]:
    marker_dir = raw_dir / "markers"
    marker_dir.mkdir(parents=True)
    times = {
        name: timestamp
        for name, timestamp in zip(
            p0_checker.J4_WORKER_MARKERS,
            (
                28_000_000_000,
                29_000_000_000,
                30_000_000_000,
                31_000_000_000,
                32_000_000_000,
                33_000_000_000,
                38_000_000_000,
                39_000_000_000,
                41_000_000_000,
                42_000_000_000,
                43_000_000_000,
                44_000_000_000,
                45_000_000_000,
                46_000_000_000,
                47_000_000_000,
            ),
        )
    }
    for name, timestamp in times.items():
        facts: dict[str, object] = {}
        if name == "solve_started":
            facts["max_it"] = 20
        _write(marker_dir / f"{name}.json", {"schema": p0_checker.J4_WORKER_MARKER_SCHEMA, "marker": name, "source_sha": SOURCE_SHA, "wall_time_ns": timestamp, "facts": facts})
    return times


def _valid_j4_fixture(tmp_path: Path, *, root_name: str = "j4-root") -> tuple[Path, Path]:
    root = tmp_path / root_name
    cache = root / "jit_cache"
    marker_dir = root / "markers"
    children_dir = root / "children"
    solver_dir = root / "solver"
    manifests_dir = root / "cache_manifests"
    worker_raw = root / "worker_raw"
    checkpoints = root / "checkpoints"
    for path in (root, cache, marker_dir, children_dir, solver_dir, manifests_dir, worker_raw, checkpoints):
        path.mkdir()
    record_path = root / "parent_record.json"
    sample_path = root / "parent_process.jsonl"
    marker_manifest_path = root / "marker_manifest.json"

    marker_entries = []
    for name in p0_checker.J4_MARKER_ORDER:
        index = p0_checker.J4_PARENT_MARKER_INDEX[name]
        timestamp = (index + 1) * 1_000_000_000
        facts: dict[str, object] = {
            "stage": "j4-p0r-solver" if 20 <= index <= 38 else "j4-p0r-parent",
            "artifact_root": str(root),
            "cache_dir": str(cache),
            "source_sha": SOURCE_SHA,
        }
        if name.startswith("precompile_") and name.endswith("_started"):
            facts["command"] = [str(PYTHON), "-m", parent.CHILD_MODULE]
        if name == "solver_child_started":
            facts["command"] = [str(PYTHON), "-m", parent.P0_MODULE, "--workflow", parent.WORKFLOW_J4]
        if name == "parent_complete":
            facts["compiler_descendant_count"] = 0
        path = marker_dir / f"{index:03d}_{name}.json"
        _write(path, {"schema": p0_checker.V14_MARKER_SCHEMA, "name": name, "marker_index": index, "timestamp_ns": timestamp, "facts": facts})
        marker_entries.append({"name": name, "path": str(path), "sha256": _sha(path)})
    _write(marker_manifest_path, marker_entries)

    stages = [*(f"precompile:{group}" for group in p0_checker.J4_GROUP_COUNTS), "precompile:parent-only", "solver"]
    samples: list[dict[str, object]] = []
    for index, stage in enumerate(stages[:-2]):
        base = 2_000_000_000 + index * 2_000_000_000
        pid = 5000 + index
        samples.extend((_j4_sample(stage, base + 100_000_000, pid), _j4_sample(stage, base + 200_000_000, pid), _j4_sample(stage, base + 300_000_000, pid)))
    parent_only = stages[-2]
    samples.extend((_j4_sample(parent_only, 16_100_000_000, None), _j4_sample(parent_only, 16_200_000_000, None), _j4_sample(parent_only, 16_300_000_000, None)))
    solver_stage = stages[-1]
    samples.extend((_j4_sample(solver_stage, 36_500_000_000, 6000), _j4_sample(solver_stage, 39_500_000_000, 6000), _j4_sample(solver_stage, 40_500_000_000, 6000), _j4_sample(solver_stage, 44_500_000_000, 6000), _j4_sample(solver_stage, 46_500_000_000, 6000)))
    sample_path.write_text("".join(json.dumps(value, separators=(",", ":")) + "\n" for value in samples), encoding="utf-8")

    initial_manifest_path = manifests_dir / "initial.json"
    initial_manifest = {"cache_dir": str(cache), "artifacts": [], "artifact_count": 0}
    _write(initial_manifest_path, initial_manifest)
    initial_ref = {"path": str(initial_manifest_path), "sha256": _sha(initial_manifest_path), "artifact_count": 0, "manifest": initial_manifest}

    children = []
    artifacts: list[dict[str, object]] = []
    module_index = 0
    for group_index, group in enumerate(p0_checker.J4_GROUP_COUNTS):
        roles = list(p0_checker.J4_GROUP_ROLES[group])
        added: list[dict[str, object]] = []
        for _ in roles:
            for suffix in ("c", "o", "so"):
                relative = f"module_{module_index}.{suffix}"
                target = cache / relative
                target.write_bytes(f"module-{module_index}-{suffix}".encode())
                item = {"relative_path": relative, "bytes": target.stat().st_size, "sha256": _sha(target)}
                artifacts.append(item)
                added.append(item)
            module_index += 1
        manifest = {"cache_dir": str(cache), "artifacts": list(artifacts), "artifact_count": len(artifacts)}
        manifest_path = manifests_dir / f"{group_index:02d}-{group.replace('-', '_')}.json"
        _write(manifest_path, manifest)
        child_record = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.json"
        child_command = [str(PYTHON), "-m", parent.CHILD_MODULE, "--group", group, "--cache-dir", str(cache), "--record", str(child_record), "--expected-source-sha", SOURCE_SHA, "--input", str(INPUT)]
        child_facts = {"compiled_form_count": len(roles), "form_roles": roles}
        if group.startswith("physical-volume-"):
            child_facts.update({"component": "curl" if group.endswith("curl") else "mass", "component_count": 1})
        _write(child_record, {"schema": parent.CHILD_RECORD_SCHEMA, "stage": "j3-split-precompile-child", "group": group, "source_sha": SOURCE_SHA, "branch": p0_checker.BRANCH, "command": child_command, "input": {"path": str(INPUT), "input_sha256": p0_checker.INPUT_SHA256, "physical_model_sha256": p0_checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": p0_checker.MODE_MANIFEST_SHA256, "profile": _profile()}, "cache": {"cache_dir": str(cache), "jit_options": {}}, "facts": {"group_facts": child_facts}, "architecture": {"matrix": False, "factor": False, "pc": False, "rhs_vector": False, "surface_carrier": False, "dtn_carrier": False, "solve": False, "recovery": False, "compile": True, "mesh": True, "jit": True, "pde": False}, "runtime": _runtime(), "raw_facts_only": True})
        stdout = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.stdout"
        stderr = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.stderr"
        stdout.write_bytes(b"")
        stderr.write_bytes(b"")
        pid = 5000 + group_index
        child_entries = {"group": group, "command": child_command, "pid": pid, "returncode": 0, "natural_exit": True, "stop_reason": "natural_exit", "descendants_gone": True, "record_path": str(child_record), "record_sha256": _sha(child_record), "stdout_path": str(stdout), "stdout_sha256": _sha(stdout), "stderr_path": str(stderr), "stderr_sha256": _sha(stderr), "cache_manifest_path": str(manifest_path), "cache_manifest_sha256": _sha(manifest_path), "cache_artifact_count": len(artifacts), "added_artifacts": added, "new_module_basenames": sorted(item["relative_path"] for item in added if str(item["relative_path"]).endswith(".so")), "process": _j4_monitor(pid, 2_000_000_000 + group_index * 2_000_000_000, 2_400_000_000 + group_index * 2_000_000_000, 3)}
        children.append(child_entries)

    before_path = manifests_dir / "before_solver.json"
    after_path = manifests_dir / "after_solver.json"
    final_manifest = {"cache_dir": str(cache), "artifacts": list(artifacts), "artifact_count": len(artifacts)}
    _write(before_path, final_manifest)
    _write(after_path, final_manifest)

    worker_path = root / "worker_record.json"
    raw_dir = worker_raw
    worker_command = _j4_worker_command(root, cache, marker_dir, worker_path)
    _j4_write_worker_markers(raw_dir)
    arrays = {
        "rhs_before": np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
        "rhs_after": np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
        "final_solution": np.asarray([0.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
        "final_action": np.asarray([0.5 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
        "final_residual": np.asarray([0.5 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
        "one_action_output": np.asarray([0.5 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
        "one_pc_output": np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128),
    }
    npz_path = raw_dir / "physical_probe.npz"
    np.savez_compressed(npz_path, **arrays)
    npz = {"relative_path": "physical_probe.npz", "bytes": npz_path.stat().st_size, "sha256": _sha(npz_path), "roles": list(arrays), "solution_only": False}
    audit = _physical_audit()
    krylov = {"cycles": [{"start_iteration": 0, "end_iteration": 20, "iterations": 20, "ksp_destroyed": True, "matvec_count": 3, "pc_apply_count": 2}], "iterations": 20, "ksp_destroy_count": 1, "checkpoint_facts": [], "matvec_count": 3, "pc_apply_count": 2, "pc_apply_facts": [{"apply_index": 0}, {"apply_index": 1}], "explicit_action_count": 2, "driver_explicit_action_count": 2, "rhs_action_count": 0, "final_action_recheck_count": 1, "extra_action_count": 1, "explicit_action_count_total": 3, "action_calls_total": 6, "initial_true_residual": 1.0, "final_true_residual": 0.5}
    worker = {"schema": p0_checker.J4_WORKER_SCHEMA, "workflow": p0_checker.J4_WORKFLOW, "stage": "j4-p0r-solver", "source_sha": SOURCE_SHA, "branch": p0_checker.BRANCH, "command": worker_command, "record_path": str(worker_path), "raw_dir": str(raw_dir), "checkpoint_root": str(checkpoints), "provenance": {**_j4_runtime(), "jit_cache_dir": str(cache), "parent_owned_cache": True, "command": worker_command}, "ffcx_calls": [{"index": index, "module_name": f"module_{index}", "module_file": str(cache / f"module_{index}.so"), "code": [None, None], "cache_hit": True} for index in range(11)], "settings": {"max_it": 20, "restart": 20, "cycle_max_it": 20, "residual_replacement": True, "zero_initial_guess": True, "checkpoint_writer": False, "checkpoint_interval": None, "first_checkpoint_iteration": None, "stop_on_true_residual": False, "official_recovery": False}, "krylov": krylov, "npz": npz, "source": {"facts": {"source_sha": SOURCE_SHA}, "generation": "dtn_port_modal_physical_rhs", "role": "physical_maxwell_rhs", "phase_application": "finalized_floquet_mpc_once", "owned_slave_indices": []}, "j4": {"one_action_probe_count": 1, "one_pc_probe_count": 1, "one_action_output": {"array_sha256": p0_checker._array_sha(arrays["one_action_output"]), "finite": True, "owned_slave_max": 0.0}, "one_pc_output": {"array_sha256": p0_checker._array_sha(arrays["one_pc_output"]), "finite": True, "owned_slave_max": 0.0}, "final_explicit_true_residual": 0.5, "rho20": 0.5, "actual_iterations": 20, "cycle_count": 1}, "physical": {"audit": audit, "recovery": {"status": "not_run", "official_outputs_written": False}}, "architecture": _j4_architecture(), "lifecycle": {"marker_relative_dir": "markers", "marker_schema": p0_checker.J4_WORKER_MARKER_SCHEMA, "marker_names": list(p0_checker.J4_WORKER_MARKERS), "retained_dwell_seconds": 2.0, "release_observation_seconds": 1.0, "release_order": ["source_rhs", "retained_window", "krylov_result", "solver_stack", "bundle"]}, "raw_facts_only": True}
    _write(worker_path, worker)
    for name in p0_checker.J4_WORKER_MARKERS:
        if name == "record_written":
            marker = json.loads((raw_dir / "markers" / f"{name}.json").read_text(encoding="utf-8"))
            marker["facts"] = {"record_path": str(worker_path), "record_sha256": _sha(worker_path)}
            _write(raw_dir / "markers" / f"{name}.json", marker)

    solver_stdout = solver_dir / "worker.stdout"
    solver_stderr = solver_dir / "worker.stderr"
    solver_stdout.write_bytes(b"")
    solver_stderr.write_bytes(b"")
    solver_process = _j4_monitor(6000, 36_000_000_000, 47_000_000_000, 5)
    solver_info = {"workflow": p0_checker.J4_WORKFLOW, "command": worker_command, "process": solver_process, "record_path": str(worker_path), "record_sha256": _sha(worker_path), "stdout_path": str(solver_stdout), "stdout_sha256": _sha(solver_stdout), "stderr_path": str(solver_stderr), "stderr_sha256": _sha(solver_stderr), "before_solver_manifest_sha256": _sha(before_path), "after_solver_manifest_sha256": _sha(after_path), "cache_unchanged": True}

    process = parent._process_summary(sample_path)
    parent_command = [str(PYTHON), "-m", parent.MODULE, "--workflow", parent.WORKFLOW_J4, "--artifact-root", str(root), "--record", str(record_path), "--source-sha", SOURCE_SHA, "--input", str(INPUT), "--expected-mpi-size", "1"]
    record = {"schema": p0_checker.J4_PARENT_SCHEMA, "stage": "j4-p0r-parent", "workflow": p0_checker.J4_WORKFLOW, "source_sha": SOURCE_SHA, "branch": p0_checker.BRANCH, "command": parent_command, "identity": {"input_path": str(INPUT), "input_sha256": p0_checker.INPUT_SHA256, "physical_model_sha256": p0_checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": p0_checker.MODE_MANIFEST_SHA256, "profile": dict(p0_checker.J4_EXPECTED_PROFILE), "runtime": _j4_runtime()}, "paths": {"artifact_root": str(root), "cache_dir": str(cache), "marker_dir": str(marker_dir), "record": str(record_path), "process_samples": str(sample_path), "marker_manifest": str(marker_manifest_path), "children_dir": str(children_dir), "solver_dir": str(solver_dir), "worker_record": str(worker_path), "cache_manifests_dir": str(manifests_dir)}, "marker_schema": p0_checker.V14_MARKER_SCHEMA, "sample_schema": p0_checker.SAMPLE_SCHEMA, "markers": {"names": list(p0_checker.J4_MARKER_ORDER), "manifest_path": str(marker_manifest_path), "manifest_sha256": _sha(marker_manifest_path)}, "process": process, "children": children, "solver": solver_info, "cache": {"initial_empty": True, "initial_manifest": initial_ref, "group_manifests": [{"group": child["group"], "path": child["cache_manifest_path"], "sha256": child["cache_manifest_sha256"], "artifact_count": child["cache_artifact_count"], "new_module_basenames": child["new_module_basenames"]} for child in children], "before_solver": {"path": str(before_path), "sha256": _sha(before_path), "artifact_count": len(artifacts), "manifest": final_manifest}, "after_solver": {"path": str(after_path), "sha256": _sha(after_path), "artifact_count": len(artifacts), "manifest": final_manifest}, "precompiled_module_basenames": sorted(f"module_{index}.so" for index in range(11)), "deferred_incident_module_basenames": [], "solver_unchanged": True}, "architecture": {"workflow": p0_checker.J4_WORKFLOW, "precompile_group_count": 7, "solver_worker": p0_checker.MODULE, "physical_workflow": True, "physical_volume_action_built": True, "volume_component_count": 2, "volume_components": ["curl_curl", "complex_material_mass"], "monolithic_physical_volume": False, "official_recovery": False}, "raw_facts_only": True}
    _write(record_path, record)
    return record_path, root


def _j5_worker_command(root: Path, cache: Path, marker_dir: Path, worker_path: Path) -> list[str]:
    return [
        str(PYTHON), "-m", p0_checker.MODULE,
        "--workflow", p0_checker.J5_WORKFLOW,
        "--stage", "p0-physical", "--case", "p6-h10-mpi1", "--source", "physical_rhs",
        "--raw-dir", str(root / "worker_raw"),
        "--jit-cache-dir", str(cache),
        "--checkpoint-root", str(root / "checkpoints"),
        "--record", str(worker_path),
        "--expected-source-sha", SOURCE_SHA, "--expected-mpi-size", "1",
        "--input", str(INPUT), "--v14-marker-dir", str(marker_dir),
    ]


def _j5_write_authority(path: Path) -> None:
    values = {
        "R": 0.3656257891787136,
        "T": 0.01299063241062439,
        "A": 0.621383578410662,
        "A_volume": 0.6213835795387049,
    }
    profile = {
        "degree": 6, "h_nm": 10.0, "wavelength_nm": 13.5,
        "polarization": "s", "grazing_deg": 1.0,
        "requested_modes": 120, "mpi_size": 8,
    }
    case = {
        "phi_deg": 0.0,
        **{
            name: {
                "gate": {"status": "task037c_direct_robustness_pass", "return_code": 0, "pass": True},
                "rta": dict(values),
            }
            for name in ("direct_M120", "direct_M160")
        },
    }
    _write(path, {"profile": profile, "raw_evidence": {"arrays_included": False}, "cases": [case]})


def _j5_write_checkpoints(checkpoint_root: Path, iterations: int, identities: dict[str, str]) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for iteration in range(500, iterations + 1, 500):
        directory = checkpoint_root / f"checkpoint-{iteration:05d}"
        directory.mkdir()
        solution = directory / "solution.npy"
        np.save(solution, np.zeros(2, dtype=np.complex128))
        manifest = {
            "schema": "fixed-memory-krylov.solution-checkpoint.v1",
            "iteration": iteration,
            "source_sha": SOURCE_SHA,
            "mpi_size": 1,
            "solution_only": True,
            "numeric_allgather": False,
            "vector_roles": ["solution"],
            **identities,
            "ranks": [{"rank": 0, "solution": {"relative_path": solution.name, "bytes": solution.stat().st_size, "sha256": _sha(solution), "dtype": "complex128", "shape": [2]}}],
        }
        manifest_path = directory / "manifest.json"
        _write(manifest_path, manifest)
        facts.append({"iteration": iteration, "manifest_path": str(manifest_path), "manifest_sha256": _sha(manifest_path)})
    return facts


def _valid_j5_fixture(
    tmp_path: Path,
    authority_path: Path,
    *,
    iteration_count: int = 40,
    final_residual: float = 1.0e-7,
    memory_values: list[int] | None = None,
) -> tuple[Path, Path]:
    if iteration_count <= 0 or iteration_count % 20:
        raise ValueError("synthetic J5 iterations must be a positive multiple of 20")
    record_path, root = _valid_j4_fixture(tmp_path, root_name="j5-root")
    cache = root / "jit_cache"
    marker_dir = root / "markers"
    marker_manifest_path = root / "marker_manifest.json"
    worker_path = root / "worker_record.json"
    worker_raw = root / "worker_raw"
    checkpoints = root / "checkpoints"
    solver_dir = root / "solver"
    worker_command = _j5_worker_command(root, cache, marker_dir, worker_path)

    parent_times = {name: (index + 1) * 1_000_000_000 for name, index in p0_checker.J4_PARENT_MARKER_INDEX.items()}
    parent_times.update({"solve_started": 36_000_000_000, "solve_complete": 37_000_000_000, "solver_stack_release_started": 43_000_000_000, "solver_stack_release_complete": 44_000_000_000, "recovery_started": 46_000_000_000, "recovery_complete": 49_000_000_000, "parent_complete": 52_000_000_000})
    solver_start = p0_checker.J4_PARENT_MARKER_INDEX["positive_setup_started"]
    solver_end = p0_checker.J4_PARENT_MARKER_INDEX["solver_stack_release_complete"]
    for name in p0_checker.J4_MARKER_ORDER:
        index = p0_checker.J4_PARENT_MARKER_INDEX[name]
        marker_path = marker_dir / f"{index:03d}_{name}.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        facts = dict(marker.get("facts", {}))
        facts.update({"stage": p0_checker.J5_SOLVER_STAGE if solver_start <= index <= solver_end else p0_checker.J5_PARENT_STAGE, "artifact_root": str(root), "cache_dir": str(cache), "source_sha": SOURCE_SHA})
        if name == "solver_child_started":
            facts["command"] = worker_command
        if name == "parent_complete":
            facts["compiler_descendant_count"] = 0
        marker.update({"schema": p0_checker.V14_MARKER_SCHEMA, "name": name, "marker_index": index, "timestamp_ns": parent_times[name], "facts": facts})
        _write(marker_path, marker)
    _write(marker_manifest_path, [{"name": name, "path": str(marker_dir / f"{p0_checker.J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json"), "sha256": _sha(marker_dir / f"{p0_checker.J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json")} for name in p0_checker.J4_MARKER_ORDER])

    worker_marker_times = dict(zip(p0_checker.J5_WORKER_MARKERS, (28_000_000_000, 29_000_000_000, 30_000_000_000, 31_000_000_000, 32_000_000_000, 36_000_000_000, 37_000_000_000, 39_000_000_000, 41_000_000_000, 42_000_000_000, 43_000_000_000, 44_000_000_000, 45_000_000_000, 46_000_000_000, 47_000_000_000, 48_000_000_000, 49_000_000_000, 50_000_000_000, 51_000_000_000)))
    worker_marker_dir = worker_raw / "markers"
    for path in worker_marker_dir.glob("*.json"):
        path.unlink()
    recovery_complete = final_residual <= p0_checker.RESIDUAL_LIMIT
    for name, timestamp in worker_marker_times.items():
        facts: dict[str, object] = {}
        if name == "solve_started":
            facts["max_it"] = p0_checker.MAX_IT
        elif name == "solve_complete":
            facts["final_explicit_recheck"] = True
        elif name == "retained_ready":
            facts["retained_dwell_seconds"] = 2.0
        elif name == "release_observation":
            facts["release_observation_seconds"] = 1.0
        elif name == "recovery_built":
            facts.update({"status": "complete" if recovery_complete else "not_run", "reason": "" if recovery_complete else "fixed-cap residual did not meet the recovery threshold"})
        elif name in {"official_outputs_written", "recovery_complete"}:
            facts.update({"status": "complete" if recovery_complete else "not_run", "artifact_count": 1 if recovery_complete else 0})
        _write(worker_marker_dir / f"{name}.json", {"schema": p0_checker.J5_WORKER_MARKER_SCHEMA, "marker": name, "source_sha": SOURCE_SHA, "wall_time_ns": timestamp, "facts": facts})

    arrays = {"rhs_before": np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128), "rhs_after": np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128), "final_solution": np.asarray([0.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128), "final_action": np.asarray([1.0 - final_residual + 0.0j, 0.0 + 0.0j], dtype=np.complex128), "final_residual": np.asarray([final_residual + 0.0j, 0.0 + 0.0j], dtype=np.complex128), "one_action_output": np.asarray([1.0 - final_residual + 0.0j, 0.0 + 0.0j], dtype=np.complex128), "one_pc_output": np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128)}
    npz_path = worker_raw / "physical_probe.npz"
    np.savez_compressed(npz_path, **arrays)
    npz = {"relative_path": "physical_probe.npz", "bytes": npz_path.stat().st_size, "sha256": _sha(npz_path), "roles": list(arrays), "solution_only": False}

    cycle_count = iteration_count // 20
    if memory_values is None:
        memory_values = [150, 140] + [140] * max(cycle_count - 2, 0)
    if len(memory_values) != cycle_count:
        raise ValueError("synthetic J5 memory sequence must match cycle count")
    cycles = []
    pc_facts = []
    for index in range(cycle_count):
        end = (index + 1) * 20
        cycles.append({"cycle_index": index, "start_iteration": index * 20, "end_iteration": end, "iterations": 20, "ksp_destroyed": True, "initial_guess_nonzero": index > 0, "explicit_true_residual": final_residual if index == cycle_count - 1 else 0.5, "matvec_count": 3, "pc_apply_count": 2, "wall_seconds": 0.1 + index * 0.001, "resource": {"process_tree": {"root_pid": 4242, "rss_bytes": memory_values[index], "swap_bytes": 0, "all_status_readable": True}, "memory_authority_bytes": memory_values[index], "job_no_swap": True}})
        pc_facts.extend({"apply_index": index * 2 + offset, "output_finite": True, "owned_slave_max": 0.0} for offset in range(2))
    identities = {"input_identity_sha256": p0_checker.INPUT_SHA256, "operator_identity_sha256": "1" * 64, "physical_model_sha256": p0_checker.PHYSICAL_MODEL_SHA256}
    checkpoint_facts = _j5_write_checkpoints(checkpoints, iteration_count, identities)
    krylov = {"cycles": cycles, "iterations": iteration_count, "ksp_destroy_count": cycle_count, "checkpoint_facts": checkpoint_facts, "matvec_count": 3 * cycle_count, "pc_apply_count": 2 * cycle_count, "pc_apply_facts": pc_facts, "explicit_action_count": cycle_count, "driver_explicit_action_count": cycle_count, "rhs_action_count": 0, "final_action_recheck_count": 1, "extra_action_count": 1, "explicit_action_count_total": cycle_count + 1, "action_calls_total": 4 * cycle_count + 1, "initial_true_residual": 1.0, "final_true_residual": final_residual, "final_output": {"array_sha256": p0_checker._array_sha(arrays["final_solution"])}}
    values = {"R_total": 0.3656257891787136, "T_total": 0.01299063241062439, "R_plus_T": 0.37861642158933797, "A_balance": 0.621383578410662, "R00_s": 0.1, "R00_p": 0.1, "dtn_port_top_mode_count": 12, "dtn_port_bottom_mode_count": 12}
    recovery = {"status": "complete", "field_model": "total_field", "electric_finite": True, "auxiliary_finite": True, "auxiliary_facts": {"shape": [2], "dtype": "complex128", "finite": True, "owned_slave_max": 0.0}, "port_metrics": values, "volume_metrics": {"A_volume_total": 0.6213835795387049, "energy_closure_error_port_volume": 1.1280429e-9}, "diffraction_metrics": {"diffraction_channel_count": 1}, "diffraction_channel_count": 1, "field_export": {"full3d_reference_exported": False}, "direct_authority": {"status": "scalar_only", "record_path": str(authority_path), "record_sha256": _sha(authority_path), "arrays_included": False}, "significant_gate_semantics": {"identity_set_count": 12, "power_gate_count": 12, "complex_boundary_amplitude_gate_count": 12, "same_identity_set": True, "definition": p0_checker.SIGNIFICANT_GATE_DEFINITION, "authority": "benchmarks/task035d_case097_checker.py::significant_12_power_and_12_amplitude"}, "artifacts": []}
    if not recovery_complete:
        recovery = {"status": "not_run", "reason": "fixed-cap residual did not meet the recovery threshold", "official_outputs_written": False}
    else:
        official_dir = worker_raw / "official"
        official_dir.mkdir()
        official_path = official_dir / "dtn_port_power_metrics_3d.json"
        _write(official_path, values)
        reference_archive = official_dir / "full3d_reference_samples.npz"
        reference_metadata = official_dir / "full3d_reference_samples.json"
        x_nm = (np.arange(40, dtype=np.float64) + 0.5) * 50.0 / 40.0
        y_nm = (np.arange(20, dtype=np.float64) + 0.5) * 25.0 / 20.0
        z_nm = np.asarray([10.0, 30.0, 60.0, 90.0, 110.0], dtype=np.float64)
        field_shape = (5, 20, 40, 3)
        np.savez_compressed(
            reference_archive,
            x_nm=x_nm,
            y_nm=y_nm,
            z_nm=z_nm,
            E_V_per_m=np.zeros(field_shape, dtype=np.complex128),
            H_A_per_m=np.zeros(field_shape, dtype=np.complex128),
        )
        _write(
            reference_metadata,
            {
                "schema_version": 1,
                "archive": reference_archive.name,
                "archive_sha256": _sha(reference_archive),
                "archive_bytes": reference_archive.stat().st_size,
                "array_shape_z_y_x_component": list(field_shape),
                "point_count": 4000,
            },
        )
        diffraction_path = official_dir / "diffraction_orders_3d.json"
        _write(
            diffraction_path,
            {
                "orders": [
                    {
                        "m": 0,
                        "n": 0,
                        "polarization": "s",
                        "alpha": 0.0,
                        "gamma": 0.0,
                        "beta_top": {"real": 0.0, "imag": 0.0},
                        "beta_bottom": {"real": 0.0, "imag": 0.0},
                        "reflected_amplitude": {"real": 0.0, "imag": 0.0},
                        "transmitted_amplitude": {"real": 0.0, "imag": 0.0},
                        "R": 0.0,
                        "T": 0.0,
                    }
                ],
                "metrics": {"diffraction_channel_count": 1},
            },
        )
        recovery["field_export"] = {
            "full3d_reference_exported": True,
            "full3d_reference_archive": str(reference_archive),
            "full3d_reference_metadata": str(reference_metadata),
            "full3d_reference_archive_sha256": _sha(reference_archive),
            "full3d_reference_archive_bytes": reference_archive.stat().st_size,
            "full3d_reference_array_shape": list(field_shape),
            "full3d_reference_point_count": 4000,
            "full3d_reference_plane_z_nm": z_nm.tolist(),
        }
        recovery["artifacts"] = [
            {"relative_path": path.name, "bytes": path.stat().st_size, "sha256": _sha(path)}
            for path in (official_path, reference_archive, reference_metadata, diffraction_path)
        ]
    architecture = _j4_architecture()
    architecture.update({"workflow": p0_checker.J5_WORKFLOW, "official_recovery": True, "qualification_only": False, "recovery_run": recovery_complete})
    worker = {"schema": p0_checker.J5_WORKER_SCHEMA, "workflow": p0_checker.J5_WORKFLOW, "stage": p0_checker.J5_SOLVER_STAGE, "source_sha": SOURCE_SHA, "branch": p0_checker.BRANCH, "command": worker_command, "record_path": str(worker_path), "raw_dir": str(worker_raw), "checkpoint_root": str(checkpoints), "provenance": {**_j4_runtime(), "stage": p0_checker.J5_SOLVER_STAGE, "jit_cache_dir": str(cache), "parent_owned_cache": True, "command": worker_command}, "ffcx_calls": [{"index": index, "module_name": f"module_{index}", "module_file": str(cache / f"module_{index}.so"), "code": [None, None], "cache_hit": True} for index in range(11)], "settings": {"max_it": p0_checker.MAX_IT, "restart": 20, "cycle_max_it": 20, "residual_replacement": True, "zero_initial_guess": True, "checkpoint_writer": True, "checkpoint_interval": 500, "first_checkpoint_iteration": None, "stop_on_true_residual": True, "qualification_only": False, "official_recovery": True}, "krylov": krylov, "npz": npz, "identities": identities, "source": {"facts": {"source_sha": SOURCE_SHA}, "generation": "dtn_port_modal_physical_rhs", "role": "physical_maxwell_rhs", "phase_application": "finalized_floquet_mpc_once", "owned_slave_indices": [], "before": {"array_sha256": p0_checker._array_sha(arrays["rhs_before"])}, "after": {"array_sha256": p0_checker._array_sha(arrays["rhs_after"])}}, "j5": {"one_action_probe_count": 1, "one_pc_probe_count": 1, "one_action_output": {"array_sha256": p0_checker._array_sha(arrays["one_action_output"]), "finite": True, "owned_slave_max": 0.0}, "one_pc_output": {"array_sha256": p0_checker._array_sha(arrays["one_pc_output"]), "finite": True, "owned_slave_max": 0.0}}, "physical": {"audit": _physical_audit(), "recovery": recovery}, "architecture": architecture, "lifecycle": {"marker_relative_dir": "markers", "marker_schema": p0_checker.J5_WORKER_MARKER_SCHEMA, "marker_names": list(p0_checker.J5_WORKER_MARKERS), "retained_dwell_seconds": 2.0, "release_observation_seconds": 1.0, "release_order": ["source_rhs", "retained_window", "krylov_result", "solver_stack", "recovery", "bundle"]}, "raw_facts_only": True}
    _write(worker_path, worker)
    record_written = worker_marker_dir / "record_written.json"
    marker = json.loads(record_written.read_text(encoding="utf-8"))
    marker["facts"] = {"record_path": str(worker_path), "record_sha256": _sha(worker_path)}
    _write(record_written, marker)

    base = json.loads(record_path.read_text(encoding="utf-8"))
    base["paths"]["worker_record"] = str(worker_path)
    base["identity"].update({"input_identity_sha256": p0_checker.INPUT_SHA256, "operator_identity_sha256": "1" * 64, "physical_model_identity_sha256": p0_checker.PHYSICAL_MODEL_SHA256})
    solver_process = _j4_monitor(6000, 36_000_000_000, 52_000_000_000, 5)
    solver_info = {"workflow": p0_checker.J5_WORKFLOW, "command": worker_command, "process": solver_process, "record_path": str(worker_path), "record_sha256": _sha(worker_path), "stdout_path": str(solver_dir / "worker.stdout"), "stdout_sha256": _sha(solver_dir / "worker.stdout"), "stderr_path": str(solver_dir / "worker.stderr"), "stderr_sha256": _sha(solver_dir / "worker.stderr"), "before_solver_manifest_sha256": base["solver"]["before_solver_manifest_sha256"], "after_solver_manifest_sha256": base["solver"]["after_solver_manifest_sha256"], "cache_unchanged": True}
    base.update({"schema": p0_checker.J5_PARENT_SCHEMA, "stage": p0_checker.J5_PARENT_STAGE, "workflow": p0_checker.J5_WORKFLOW, "source_sha": SOURCE_SHA, "command": [str(PYTHON), "-m", parent.MODULE, "--workflow", p0_checker.J5_WORKFLOW, "--artifact-root", str(root), "--record", str(record_path), "--source-sha", SOURCE_SHA, "--input", str(INPUT), "--expected-mpi-size", "1"], "identity": {"input_path": str(INPUT), "input_sha256": p0_checker.INPUT_SHA256, "physical_model_sha256": p0_checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": p0_checker.MODE_MANIFEST_SHA256, "profile": dict(p0_checker.J4_EXPECTED_PROFILE), "runtime": _j4_runtime()}, "markers": {"names": list(p0_checker.J4_MARKER_ORDER), "manifest_path": str(marker_manifest_path), "manifest_sha256": _sha(marker_manifest_path)}, "process": parent._process_summary(root / "parent_process.jsonl"), "solver": solver_info, "architecture": {"workflow": p0_checker.J5_WORKFLOW, "precompile_group_count": 7, "solver_worker": p0_checker.MODULE, "physical_workflow": True, "physical_volume_action_built": True, "volume_component_count": 2, "volume_components": ["curl_curl", "complex_material_mass"], "monolithic_physical_volume": False, "official_recovery": True, "qualification_only": False, "max_it": p0_checker.MAX_IT, "checkpoint_interval": 500}, "raw_facts_only": True})
    base["cache"]["deferred_incident_module_basenames"] = []
    base["cache"]["solver_unchanged"] = True
    _write(record_path, base)
    return record_path, root


def _refresh_j4_process(record_path: Path, sample_path: Path) -> dict[str, object]:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["process"] = parent._process_summary(sample_path)
    stage = record["process"]["stage_summaries"]["solver"]
    monitor = record["solver"]["process"]
    monitor.update({"peak_rss_bytes": stage["peak_rss_bytes"], "max_swap_bytes": stage["max_swap_bytes"], "compiler_descendant_peak": stage["compiler_descendant_peak"], "observed_descendant_pids": stage["observed_descendant_pids"], "sample_count": stage["sample_count"]})
    _write(record_path, record)
    return record


def test_fresh_root_and_marker_subsequence_are_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    cache = root / "jit_cache"
    paths = staging.prepare_fresh_root(root, cache)
    staging.write_marker(paths["marker_dir"], "parent_started", {})
    staging.create_fresh_cache(cache)
    staging.write_marker(paths["marker_dir"], "fresh_cache_created", {})
    with pytest.raises(ValueError):
        staging.write_marker(paths["marker_dir"], "parent_started", {})
    with pytest.raises(FileExistsError):
        staging.prepare_fresh_root(root, cache)


def test_process_jsonl_and_manifest_delta_are_flushable(tmp_path: Path) -> None:
    sample_path = tmp_path / "samples.jsonl"
    code = (
        "import json,subprocess,sys;"
        "from pathlib import Path;"
        "from benchmarks import run_task038_full3d_jit_staged_parent as parent;"
        "sample_path=Path(sys.argv[1]);"
        "child_code=\"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.25)']); time.sleep(0.35)\";"
        "process=subprocess.Popen([sys.executable,'-c',child_code],start_new_session=True);"
        "print(json.dumps(parent._monitor_child(process,sample_path,'test')))"
    )
    probe = subprocess.run(
        [sys.executable, "-c", code, str(sample_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    monitor = json.loads(probe.stdout)
    assert len(monitor["observed_descendant_pids"]) >= 2
    assert monitor["pid"] in monitor["observed_descendant_pids"]
    assert monitor["process_group_gone"] is True
    assert monitor["required_sigkill"] is False
    assert json.loads(sample_path.read_text(encoding="utf-8").splitlines()[0])["schema"] == staging.SAMPLE_SCHEMA
    previous = {"manifest": {"artifacts": [], "artifact_count": 0}}
    current = {"manifest": {"artifacts": [{"relative_path": "a.so", "sha256": "x"}], "artifact_count": 1}}
    assert parent._manifest_delta(previous, current) == current["manifest"]["artifacts"]


@pytest.mark.parametrize(
    ("vanished_results", "expected_vanished", "expected_unreadable"),
    [((False, True), [200], []), ((False, False), [], [200])],
)
def test_snapshot_has_bounded_terminal_retry(
    monkeypatch: pytest.MonkeyPatch,
    vanished_results: tuple[bool, bool],
    expected_vanished: list[int],
    expected_unreadable: list[int],
) -> None:
    calls: dict[int, int] = {}
    sleeps: list[float] = []
    vanished_calls = iter(vanished_results)

    def fake_process_fact(pid: int, stage: str) -> dict[str, object] | None:
        calls[pid] = calls.get(pid, 0) + 1
        if pid == 100:
            return {
                "pid": 100,
                "ppid": 1,
                "comm": "python",
                "state": "S",
                "cmdline": "python -m parent",
                "stage": stage,
                "rss_bytes": 100,
                "pss_bytes": 50,
                "swap_bytes": 0,
                "timestamp_ns": 1,
                "exit_code": None,
            }
        return None

    monkeypatch.setattr(staging, "_live_parent_map", lambda: {100: [200]})
    monkeypatch.setattr(staging, "_process_fact", fake_process_fact)
    monkeypatch.setattr(staging, "_pid_vanished", lambda pid: next(vanished_calls))
    monkeypatch.setattr(staging.time, "sleep", sleeps.append)

    result = staging.process_tree_snapshot(100, "test")

    assert calls == {100: 1, 200: 3}
    assert sleeps == [0.01, 0.01]
    assert result["vanished_pids"] == expected_vanished
    assert result["unreadable_pids"] == expected_unreadable
    assert result["all_status_readable"] is (not expected_unreadable)
    assert result["readability_retry_count"] == 1


def test_checker_accepts_fake_unchanged_solver_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record_path, _root, record = _valid_fixture(tmp_path)
    result = checker.check_record(record_path, SOURCE_SHA)
    assert result["passed"] is True
    assert result["classification"] == "J3_SPLIT_COLD_STAGED_PASS"
    assert result["identity"]["source_sha"] == SOURCE_SHA
    assert result["metrics"]["solver_ffcx_call_count"] == 10
    assert result["metrics"]["precompiled_module_count"] == 11

    j4_pass_root = tmp_path / "j4-pass"
    j4_pass_root.mkdir()
    j4_record_path, _j4_root = _valid_j4_fixture(j4_pass_root)
    j4_result = p0_checker.check_j4_record(j4_record_path, SOURCE_SHA)
    assert j4_result["passed"] is True
    assert j4_result["classification"] == "J4_P0R_PASS"
    assert j4_result["metrics"]["precompiled_module_count"] == 11
    assert j4_result["metrics"]["ffcx_call_count"] == 11
    with pytest.raises(checker.CheckError):
        checker.check_record(j4_record_path, SOURCE_SHA)

    authority_path = tmp_path / "j5-authority.json"
    _j5_write_authority(authority_path)
    monkeypatch.setattr(p0_checker, "DIRECT_AUTHORITY_PATH", authority_path)
    monkeypatch.setattr(p0_checker, "DIRECT_AUTHORITY_SHA256", _sha(authority_path))
    j5_record_path, _j5_root = _valid_j5_fixture(tmp_path, authority_path)
    j5_result = p0_checker.check_j5_record(j5_record_path, SOURCE_SHA)
    assert j5_result["passed"] is False, j5_result
    assert j5_result["classification"] == p0_checker.J5_AUTHORITY_ARRAYS_MISSING
    assert not j5_result["contract_errors"]
    assert j5_result["metrics"]["iterations"] == 40
    assert j5_result["metrics"]["cycle_boundaries"][-1]["iteration"] == 40
    assert j5_result["metrics"]["milestone_residuals"] == {"20": 0.5}
    assert j5_result["metrics"]["memory_accumulation"] is False
    assert j5_result["metrics"]["ffcx_call_count"] == 11
    assert j5_result["resource"]["solve_window_peak_rss_bytes"] == 150

    from benchmarks import run_task038_full3d_same_mesh_hcurl_pmg_p0_physical as p0_worker

    direct_record = p0_worker._record(
        raw_dir=tmp_path / "direct-raw",
        checkpoint_root=tmp_path / "direct-checkpoints",
        record_path=tmp_path / "direct-record.json",
        command=[],
        source={"source_sha": SOURCE_SHA},
        rhs_facts={},
        rhs_after_facts={},
        owned_slave_indices=np.asarray([], dtype=np.int32),
        setup_audit={},
        physical_audit={},
        architecture={},
        rhs_generation={"generation": "g", "role": "r", "phase_application": "p"},
        provenance={"source_sha": SOURCE_SHA},
        identities={},
        result={"explicit_action_count": 0},
        pc_apply_facts=[],
        npz_facts={},
        recovery={},
        action_calls=0,
        workflow=p0_worker.WORKFLOW_J4,
    )
    assert direct_record["stage"] == "j4-p0r-solver"
    assert direct_record["source_sha"] == SOURCE_SHA
    assert direct_record["lifecycle"]["marker_schema"] == p0_worker.J4_MARKER_SCHEMA
    assert direct_record["settings"]["max_it"] == 20
    assert direct_record["settings"]["qualification_only"] is True

    j5_probe = {
        "one_action_probe_count": 1,
        "one_pc_probe_count": 1,
        "one_action_output": {"array_sha256": "a" * 64, "finite": True, "owned_slave_max": 0.0},
        "one_pc_output": {"array_sha256": "b" * 64, "finite": True, "owned_slave_max": 0.0},
    }
    j5_record = p0_worker._record(
        raw_dir=tmp_path / "direct-j5-raw",
        checkpoint_root=tmp_path / "direct-j5-checkpoints",
        record_path=tmp_path / "direct-j5-record.json",
        command=[],
        source={"source_sha": SOURCE_SHA},
        rhs_facts={},
        rhs_after_facts={},
        owned_slave_indices=np.asarray([], dtype=np.int32),
        setup_audit={},
        physical_audit={},
        architecture={},
        rhs_generation={"generation": "g", "role": "r", "phase_application": "p"},
        provenance={"source_sha": SOURCE_SHA},
        identities={},
        result={"explicit_action_count": 0},
        pc_apply_facts=[],
        npz_facts={},
        recovery={},
        action_calls=0,
        workflow=p0_worker.WORKFLOW_J5,
        ffcx_calls=[],
        j4_probe_facts=j5_probe,
    )
    assert set(j5_record["j5"]) == set(j5_probe)
    assert not set(j5_record["j5"]).intersection({"rho20", "final_explicit_true_residual", "actual_iterations", "cycle_count", "checkpoint_count", "milestone_iterations"})
    assert j5_record["settings"]["max_it"] == p0_worker.MAX_IT
    assert j5_record["settings"]["checkpoint_interval"] == 500

    worker_tree = ast.parse(
        (ROOT / "benchmarks/run_task038_full3d_same_mesh_hcurl_pmg_p0_physical.py").read_text(encoding="utf-8")
    )
    run_worker = next(node for node in worker_tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_worker")
    j4_early_return = next(
        node
        for node in ast.walk(run_worker)
        if isinstance(node, ast.If)
        and any(isinstance(child, ast.Return) for child in ast.walk(node))
        and any(
            isinstance(child, ast.Call)
            and any(
                keyword.arg == "workflow"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "WORKFLOW_J4"
                for keyword in child.keywords
            )
            for child in ast.walk(node)
        )
    )
    assert isinstance(j4_early_return.test, ast.Name)
    assert j4_early_return.test.id == "qualification_only"


def test_checker_rejects_cache_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record_path, _root, record = _valid_fixture(tmp_path)
    after_path = Path(record["cache"]["after_solver"]["path"])
    changed = json.loads(after_path.read_text(encoding="utf-8"))
    changed["artifact_count"] = 99
    after_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE_SHA)

    def j4_case(name: str) -> tuple[Path, Path]:
        case_root = tmp_path / name
        case_root.mkdir()
        return _valid_j4_fixture(case_root)

    marker_record, marker_root = j4_case("j4-marker-mutation")
    marker_path = marker_root / "markers" / "000_parent_started.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["name"] = "parent_complete"
    _write(marker_path, marker)
    marker_result = p0_checker.check_j4_record(marker_record, SOURCE_SHA)
    assert marker_result["passed"] is False
    assert marker_result["classification"] == "J4_CONTRACT_INVALID"

    delta_record, delta_root = j4_case("j4-delta-mutation")
    delta_payload = json.loads(delta_record.read_text(encoding="utf-8"))
    delta_payload["children"][0]["added_artifacts"][0]["sha256"] = "0" * 64
    _write(delta_record, delta_payload)
    delta_result = p0_checker.check_j4_record(delta_record, SOURCE_SHA)
    assert delta_result["passed"] is False
    assert delta_result["classification"] == "J4_CONTRACT_INVALID"

    solver_cache_record, solver_cache_root = j4_case("j4-solver-cache-mutation")
    solver_cache_payload = json.loads((solver_cache_root / "worker_record.json").read_text(encoding="utf-8"))
    solver_cache_payload["ffcx_calls"][0]["module_file"] = str(solver_cache_root / "jit_cache/module_1.so")
    worker_record_path = solver_cache_root / "worker_record.json"
    _write(worker_record_path, solver_cache_payload)
    solver_cache_parent = json.loads(solver_cache_record.read_text(encoding="utf-8"))
    solver_cache_parent["solver"]["record_sha256"] = _sha(worker_record_path)
    _write(solver_cache_record, solver_cache_parent)
    solver_cache_result = p0_checker.check_j4_record(solver_cache_record, SOURCE_SHA)
    assert solver_cache_result["passed"] is False
    assert solver_cache_result["classification"] == "J4_CONTRACT_INVALID"

    warning_record, warning_root = j4_case("j4-retained-warning")
    warning_sample_path = warning_root / "parent_process.jsonl"
    warning_rows = [json.loads(line) for line in warning_sample_path.read_text(encoding="utf-8").splitlines()]
    warning_solver_row = next(row for row in warning_rows if row["stage"] == "solver")
    warning_solver_row["members"][0]["rss_bytes"] = 1_650_000_000 - warning_solver_row["members"][1]["rss_bytes"]
    warning_solver_row["rss_bytes"] = sum(int(item["rss_bytes"]) for item in warning_solver_row["members"])
    warning_sample_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in warning_rows), encoding="utf-8")
    _refresh_j4_process(warning_record, warning_sample_path)
    warning_result = p0_checker.check_j4_record(warning_record, SOURCE_SHA)
    assert warning_result["passed"] is True
    assert any("1.6-1.7GB warning interval" in item for item in warning_result["warnings"])

    for name, mutate in (
        (
            "j4-rss-gate",
            lambda row: row["members"][0].update({"rss_bytes": p0_checker.COLD_RSS_LIMIT - 50}),
        ),
        ("j4-compiler-gate", lambda row: row["members"][1].update({"comm": "gcc", "cmdline": "gcc -c form.c"})),
    ):
        resource_record, resource_root = j4_case(name)
        sample_path = resource_root / "parent_process.jsonl"
        rows = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines()]
        solver_row = next(row for row in rows if row["stage"] == "solver")
        mutate(solver_row)
        solver_row["rss_bytes"] = sum(int(item["rss_bytes"]) for item in solver_row["members"])
        solver_row["swap_bytes"] = sum(int(item["swap_bytes"]) for item in solver_row["members"])
        if name == "j4-compiler-gate":
            solver_row["compiler_descendant_count"] = 1
        sample_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
        _refresh_j4_process(resource_record, sample_path)
        resource_result = p0_checker.check_j4_record(resource_record, SOURCE_SHA)
        assert resource_result["passed"] is False
        assert resource_result["classification"] == "J4_RESOURCE_GATE_FAIL"

    numerical_record, numerical_root = j4_case("j4-numerical-gate")
    numerical_worker_path = numerical_root / "worker_record.json"
    numerical_worker = json.loads(numerical_worker_path.read_text(encoding="utf-8"))
    numerical_npz = numerical_root / "worker_raw/physical_probe.npz"
    with np.load(numerical_npz, allow_pickle=False) as archive:
        numerical_arrays = {name: np.asarray(archive[name]) for name in archive.files}
    numerical_arrays["final_residual"] = np.asarray([2.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128)
    numerical_arrays["final_action"] = numerical_arrays["rhs_before"] - numerical_arrays["final_residual"]
    np.savez_compressed(numerical_npz, **numerical_arrays)
    numerical_worker["npz"]["bytes"] = numerical_npz.stat().st_size
    numerical_worker["npz"]["sha256"] = _sha(numerical_npz)
    numerical_worker["j4"]["final_explicit_true_residual"] = 2.0
    numerical_worker["j4"]["rho20"] = 2.0
    numerical_worker["krylov"]["final_true_residual"] = 2.0
    _write(numerical_worker_path, numerical_worker)
    numerical_parent = json.loads(numerical_record.read_text(encoding="utf-8"))
    numerical_parent["solver"]["record_sha256"] = _sha(numerical_worker_path)
    _write(numerical_record, numerical_parent)
    numerical_result = p0_checker.check_j4_record(numerical_record, SOURCE_SHA)
    assert numerical_result["passed"] is False
    assert numerical_result["classification"] == "J4_NUMERICAL_GATE_FAIL"

    j5_authority = tmp_path / "j5-mutation-authority.json"
    _j5_write_authority(j5_authority)
    monkeypatch.setattr(p0_checker, "DIRECT_AUTHORITY_PATH", j5_authority)
    monkeypatch.setattr(p0_checker, "DIRECT_AUTHORITY_SHA256", _sha(j5_authority))

    def j5_case(name: str, **kwargs: object) -> tuple[Path, Path]:
        case_root = tmp_path / name
        case_root.mkdir()
        return _valid_j5_fixture(case_root, j5_authority, **kwargs)

    j5_marker_record, j5_marker_root = j5_case("j5-marker-mutation")
    j5_marker_path = j5_marker_root / "worker_raw/markers/solve_started.json"
    j5_marker = json.loads(j5_marker_path.read_text(encoding="utf-8"))
    j5_marker["facts"]["max_it"] = 19
    _write(j5_marker_path, j5_marker)
    j5_marker_result = p0_checker.check_j5_record(j5_marker_record, SOURCE_SHA)
    assert j5_marker_result["passed"] is False
    assert j5_marker_result["classification"] == "J5_CONTRACT_INVALID"

    j5_delta_record, j5_delta_root = j5_case("j5-delta-mutation")
    j5_delta_payload = json.loads(j5_delta_record.read_text(encoding="utf-8"))
    j5_delta_payload["children"][0]["added_artifacts"][0]["sha256"] = "0" * 64
    _write(j5_delta_record, j5_delta_payload)
    j5_delta_result = p0_checker.check_j5_record(j5_delta_record, SOURCE_SHA)
    assert j5_delta_result["passed"] is False
    assert j5_delta_result["classification"] == "J5_CONTRACT_INVALID"

    j5_solver_cache_record, j5_solver_cache_root = j5_case("j5-solver-cache-mutation")
    j5_solver_payload = json.loads((j5_solver_cache_root / "worker_record.json").read_text(encoding="utf-8"))
    j5_solver_payload["ffcx_calls"][0]["module_file"] = str(j5_solver_cache_root / "jit_cache/module_1.so")
    j5_solver_path = j5_solver_cache_root / "worker_record.json"
    _write(j5_solver_path, j5_solver_payload)
    j5_solver_parent = json.loads(j5_solver_cache_record.read_text(encoding="utf-8"))
    j5_solver_parent["solver"]["record_sha256"] = _sha(j5_solver_path)
    _write(j5_solver_cache_record, j5_solver_parent)
    j5_solver_result = p0_checker.check_j5_record(j5_solver_cache_record, SOURCE_SHA)
    assert j5_solver_result["passed"] is False
    assert j5_solver_result["classification"] == "J5_CONTRACT_INVALID"

    for name, mutate in (
        ("j5-rss-gate", lambda row: row["members"][0].update({"rss_bytes": p0_checker.COLD_RSS_LIMIT - row["members"][1]["rss_bytes"]})),
        ("j5-compiler-gate", lambda row: row["members"][1].update({"comm": "gcc", "cmdline": "gcc -c form.c"})),
    ):
        j5_resource_record, j5_resource_root = j5_case(name)
        j5_sample_path = j5_resource_root / "parent_process.jsonl"
        j5_rows = [json.loads(line) for line in j5_sample_path.read_text(encoding="utf-8").splitlines()]
        j5_solver_row = next(row for row in j5_rows if row["stage"] == "solver")
        mutate(j5_solver_row)
        j5_solver_row["rss_bytes"] = sum(int(item["rss_bytes"]) for item in j5_solver_row["members"])
        j5_solver_row["swap_bytes"] = sum(int(item["swap_bytes"]) for item in j5_solver_row["members"])
        if name == "j5-compiler-gate":
            j5_solver_row["compiler_descendant_count"] = 1
        j5_sample_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in j5_rows), encoding="utf-8")
        _refresh_j4_process(j5_resource_record, j5_sample_path)
        j5_resource_result = p0_checker.check_j5_record(j5_resource_record, SOURCE_SHA)
        assert j5_resource_result["passed"] is False
        assert j5_resource_result["classification"] == "J5_RESOURCE_GATE_FAIL"

    j5_numeric_record, j5_numeric_root = j5_case("j5-numerical-gate")
    j5_numeric_path = j5_numeric_root / "worker_record.json"
    j5_numeric_worker = json.loads(j5_numeric_path.read_text(encoding="utf-8"))
    j5_numeric_npz = j5_numeric_root / "worker_raw/physical_probe.npz"
    with np.load(j5_numeric_npz, allow_pickle=False) as archive:
        j5_arrays = {name: np.asarray(archive[name]) for name in archive.files}
    j5_arrays["final_residual"] = np.asarray([2.0e-6 + 0.0j, 0.0 + 0.0j], dtype=np.complex128)
    j5_arrays["final_action"] = j5_arrays["rhs_before"] - j5_arrays["final_residual"]
    np.savez_compressed(j5_numeric_npz, **j5_arrays)
    j5_numeric_worker["npz"].update({"bytes": j5_numeric_npz.stat().st_size, "sha256": _sha(j5_numeric_npz)})
    j5_numeric_worker["krylov"]["cycles"][1]["explicit_true_residual"] = 2.0e-6
    j5_numeric_worker["krylov"]["final_true_residual"] = 2.0e-6
    j5_numeric_worker["physical"]["recovery"] = {"status": "not_run", "official_outputs_written": False}
    _write(j5_numeric_path, j5_numeric_worker)
    j5_numeric_marker = j5_numeric_root / "worker_raw/markers/record_written.json"
    j5_numeric_marker_payload = json.loads(j5_numeric_marker.read_text(encoding="utf-8"))
    j5_numeric_marker_payload["facts"]["record_sha256"] = _sha(j5_numeric_path)
    _write(j5_numeric_marker, j5_numeric_marker_payload)
    for marker_name, facts in (("recovery_built", {"status": "not_run"}), ("official_outputs_written", {"status": "not_run", "artifact_count": 0})):
        marker_path = j5_numeric_root / f"worker_raw/markers/{marker_name}.json"
        marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
        marker_payload["facts"] = facts
        _write(marker_path, marker_payload)
    j5_numeric_parent = json.loads(j5_numeric_record.read_text(encoding="utf-8"))
    j5_numeric_parent["solver"]["record_sha256"] = _sha(j5_numeric_path)
    _write(j5_numeric_record, j5_numeric_parent)
    j5_numeric_result = p0_checker.check_j5_record(j5_numeric_record, SOURCE_SHA)
    assert j5_numeric_result["passed"] is False
    assert j5_numeric_result["classification"] == p0_checker.J5_NUMERICAL_BEFORE_CAP

    fixed_record, fixed_root = j5_case("j5-fixed-cap", iteration_count=p0_checker.MAX_IT, final_residual=2.0e-6)
    fixed_result = p0_checker.check_j5_record(fixed_record, SOURCE_SHA)
    assert fixed_result["passed"] is False
    assert fixed_result["classification"] == p0_checker.J5_NUMERICAL_FIXED_CAP
    assert fixed_result["metrics"]["iterations"] == p0_checker.MAX_IT
    assert fixed_result["metrics"]["checkpoint_iterations"] == list(range(500, p0_checker.MAX_IT + 1, 500))

    j5_checkpoint_record, j5_checkpoint_root = j5_case("j5-checkpoint-mutation")
    j5_checkpoint_path = j5_checkpoint_root / "worker_record.json"
    j5_checkpoint_worker = json.loads(j5_checkpoint_path.read_text(encoding="utf-8"))
    j5_checkpoint_worker["krylov"]["checkpoint_facts"] = [{"iteration": 500}]
    _write(j5_checkpoint_path, j5_checkpoint_worker)
    j5_checkpoint_marker = j5_checkpoint_root / "worker_raw/markers/record_written.json"
    j5_checkpoint_marker_payload = json.loads(j5_checkpoint_marker.read_text(encoding="utf-8"))
    j5_checkpoint_marker_payload["facts"]["record_sha256"] = _sha(j5_checkpoint_path)
    _write(j5_checkpoint_marker, j5_checkpoint_marker_payload)
    j5_checkpoint_parent = json.loads(j5_checkpoint_record.read_text(encoding="utf-8"))
    j5_checkpoint_parent["solver"]["record_sha256"] = _sha(j5_checkpoint_path)
    _write(j5_checkpoint_record, j5_checkpoint_parent)
    j5_checkpoint_result = p0_checker.check_j5_record(j5_checkpoint_record, SOURCE_SHA)
    assert j5_checkpoint_result["passed"] is False
    assert j5_checkpoint_result["classification"] == p0_checker.J5_CHECKPOINT_GATE_FAIL

    j5_memory_record, _j5_memory_root = j5_case("j5-memory-accumulation", memory_values=[100, 200])
    j5_memory_result = p0_checker.check_j5_record(j5_memory_record, SOURCE_SHA)
    assert j5_memory_result["passed"] is False
    assert j5_memory_result["classification"] == "J5_RESOURCE_GATE_FAIL"
    assert j5_memory_result["metrics"]["memory_accumulation"] is True

    j5_partial_record, j5_partial_root = j5_case("j5-partial-resource")
    j5_sample_path = j5_partial_root / "parent_process.jsonl"
    j5_rows = [json.loads(line) for line in j5_sample_path.read_text(encoding="utf-8").splitlines()]
    j5_solver_row = next(row for row in j5_rows if row["stage"] == "solver")
    j5_solver_row["members"][0]["rss_bytes"] = p0_checker.COLD_RSS_LIMIT - j5_solver_row["members"][1]["rss_bytes"]
    j5_solver_row["rss_bytes"] = sum(int(item["rss_bytes"]) for item in j5_solver_row["members"])
    j5_sample_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in j5_rows), encoding="utf-8")
    _refresh_j4_process(j5_partial_record, j5_sample_path)
    j5_partial_payload = json.loads(j5_partial_record.read_text(encoding="utf-8"))
    j5_partial_payload.update({"partial": True, "error": "process_tree_rss_limit"})
    _write(j5_partial_record, j5_partial_payload)
    j5_partial_result = p0_checker.check_j5_record(j5_partial_record, SOURCE_SHA)
    assert j5_partial_result["passed"] is False
    assert j5_partial_result["classification"] == "J5_RESOURCE_GATE_FAIL"

    j5_partial_summary_record, _j5_partial_summary_root = j5_case("j5-partial-summary-only")
    j5_partial_summary_payload = json.loads(j5_partial_summary_record.read_text(encoding="utf-8"))
    j5_partial_summary_payload.update({"partial": True, "error": "process_tree_rss_limit"})
    j5_partial_summary_payload["process"]["peak_rss_bytes"] = p0_checker.COLD_RSS_LIMIT
    _write(j5_partial_summary_record, j5_partial_summary_payload)
    j5_partial_summary_invalid = p0_checker.check_j5_record(j5_partial_summary_record, SOURCE_SHA)
    assert j5_partial_summary_invalid["passed"] is False
    assert j5_partial_summary_invalid["classification"] == "J5_CONTRACT_INVALID"

    j5_recovery_record, j5_recovery_root = j5_case("j5-recovery-mutation")
    j5_recovery_path = j5_recovery_root / "worker_record.json"
    j5_recovery_worker = json.loads(j5_recovery_path.read_text(encoding="utf-8"))
    j5_recovery_worker["physical"]["recovery"]["field_export"]["full3d_reference_exported"] = False
    _write(j5_recovery_path, j5_recovery_worker)
    j5_recovery_marker = j5_recovery_root / "worker_raw/markers/record_written.json"
    j5_recovery_marker_payload = json.loads(j5_recovery_marker.read_text(encoding="utf-8"))
    j5_recovery_marker_payload["facts"]["record_sha256"] = _sha(j5_recovery_path)
    _write(j5_recovery_marker, j5_recovery_marker_payload)
    j5_recovery_parent = json.loads(j5_recovery_record.read_text(encoding="utf-8"))
    j5_recovery_parent["solver"]["record_sha256"] = _sha(j5_recovery_path)
    _write(j5_recovery_record, j5_recovery_parent)
    j5_recovery_result = p0_checker.check_j5_record(j5_recovery_record, SOURCE_SHA)
    assert j5_recovery_result["passed"] is False
    assert j5_recovery_result["classification"] == "J5_RECOVERY_PHYSICS_FAIL"

    child_root = tmp_path / "child-mutation"
    child_root.mkdir()
    record_path, _root, record = _valid_fixture(child_root)
    mutated = json.loads(record_path.read_text(encoding="utf-8"))
    mutated["children"][0]["process"]["pid"] += 1
    record_path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE_SHA)

    audit_root = tmp_path / "audit-mutation"
    audit_root.mkdir()
    record_path, _root, record = _valid_fixture(audit_root)
    solver_path = Path(record["solver"]["record_path"])
    solver_payload = json.loads(solver_path.read_text())
    solver_payload["physical_audit"]["volume_action"]["components"]["curl_curl"]["slave_row_identity"] = False
    solver_path.write_text(json.dumps(solver_payload), encoding="utf-8")
    mutated = json.loads(record_path.read_text())
    mutated["solver"]["record_sha256"] = _sha(solver_path)
    record_path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE_SHA)


def test_parent_and_solver_keep_heavy_imports_lazy(tmp_path: Path) -> None:
    for path in (ROOT / "benchmarks/run_task038_full3d_jit_staged_parent.py", ROOT / "benchmarks/run_task038_full3d_jit_solver_bundle.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".", 1)[0])
        assert not names.intersection({"dolfinx", "mpi4py", "petsc4py", "ufl", "src"})
    assert parent.JIT_GROUPS == checker.GROUPS
    assert parent._child_command("positive-p6", Path("/x/cache"), Path("/x/r"), INPUT, SOURCE_SHA)[2] == checker.CHILD_MODULE
    j4_command = parent._p0_command(
        tmp_path / "root",
        tmp_path / "root/jit_cache",
        tmp_path / "root/markers",
        INPUT,
        tmp_path / "root/parent_record.json",
        SOURCE_SHA,
    )
    assert j4_command[:3] == [str(PYTHON), "-m", parent.P0_MODULE]
    assert parent._solver_command(tmp_path / "root/jit_cache", tmp_path / "root/solver.json", tmp_path / "root/markers", INPUT, SOURCE_SHA)[2] != j4_command[2]
    assert parent.WORKFLOW_J4 in j4_command
    j5_command = parent._p0_command(
        tmp_path / "j5-root",
        tmp_path / "j5-root/jit_cache",
        tmp_path / "j5-root/markers",
        INPUT,
        tmp_path / "j5-root/worker_record.json",
        SOURCE_SHA,
        workflow=parent.WORKFLOW_J5,
    )
    assert j5_command[:3] == [str(PYTHON), "-m", parent.P0_MODULE]
    assert parent.WORKFLOW_J5 in j5_command
    module = SimpleNamespace(__name__="fake", __file__=str(ROOT / "fake.so"))
    results = [("compiled", module, (None, None)), ("compiled", module, ("header", "implementation"))]

    def original(*_args: object, **_kwargs: object) -> object:
        return results.pop(0)

    module.ffcx_jit = original
    calls, saved = solver._install_ffcx_observer(module)
    assert module.ffcx_jit()[2] == (None, None)
    assert module.ffcx_jit()[2] == ("header", "implementation")
    solver._restore_ffcx_observer(module, saved)
    assert calls[0]["code"] == [None, None] and calls[0]["cache_hit"] is True
    assert calls[1]["code"] == ["<non_none>", "<non_none>"] and calls[1]["cache_hit"] is False
