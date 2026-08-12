"""Thin opt-in M5 first-screen worker, watchdog, and checker.

The form, MPC action, M3Y store, resource sampler, and source helpers remain
owned by the existing H2B route.  This module only wires those authorities to
the fixed MPI1 right-FGMRES screen; it does not add a campaign framework.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import benchmarks.run_task037_extra_h2b as h2b


ROOT = Path(__file__).resolve().parents[1]
M5_SCHEMA = "task037.extra.h2b.m5.coercive"
M5_WORKER_SCHEMA = f"{M5_SCHEMA}.worker.v1"
M5_WATCHDOG_SCHEMA = f"{M5_SCHEMA}.watchdog.v1"
M5_CHECK_SCHEMA = f"{M5_SCHEMA}.check.v1"
M5_TIMEOUT_SECONDS = 3_600.0
M5_ONLINE_RSS_LIMIT_BYTES = 1_550_000_000
M5_SWAP_LIMIT_BYTES = 0
M5_CHECKPOINT_ITERATIONS = (20, 50, 100)
M5_GLOBAL_ROWS = 173_802
M5_LOCAL_NLOC = 882
M5_CELLS = 252
M5_CONSTRAINTS = 9_210
M5_RHS_SHA256 = "6f91c83e1722a07958e6d757f7aa13f88858c95ea9ff88fe9e8693629b6f2c6d"
M5_M4Y_COMPACT = (
    ROOT
    / "benchmarks/cases/101_task37_extra_development/records"
    / "m4y_full_packed_patch_pc.json"
)
M5_M4Y_COMPACT_SHA256 = (
    "7c227b67f288ca88990f1bc966f1266ff28eb280d0bc9623ab1354f527634812"
)
M5_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "cache_load_ready",
    "source_ready",
    "outer_ksp_ready",
    "summary_ready",
)


def _m5_scope() -> dict[str, Any]:
    return {
        "mode": "m5_b0_right_fgmres_first_screen",
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "global_cells": M5_CELLS,
        "local_cells": M5_CELLS,
        "local_nloc": M5_LOCAL_NLOC,
        "global_rows": M5_GLOBAL_ROWS,
        "constraint_count": M5_CONSTRAINTS,
        "operator": "Kcurl+k0^2*M_abs_epsilon",
        "rhs_label": "physical-RHS-like",
        "rhs_sha256": M5_RHS_SHA256,
        "fgmres_type": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": 20,
        "max_it": 100,
        "checkpoint_iterations": list(M5_CHECKPOINT_ITERATIONS),
        "online_timeout_seconds": M5_TIMEOUT_SECONDS,
        "online_rss_limit_bytes": M5_ONLINE_RSS_LIMIT_BYTES,
        "swap_limit_bytes": M5_SWAP_LIMIT_BYTES,
        "fine_space": "uncondensed_fullspace",
        "global_matrix_materialized": False,
        "static_condensation": False,
        "trace_slab": False,
        "dtn": False,
        "coarse_constructed": False,
        "pde": False,
        "ordinary_default_changed": False,
    }


def _m5_worker_command(executable: str, run_dir: Path) -> list[str]:
    return [
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_m5",
        "m5-worker",
        "--run-dir",
        str(Path(run_dir).resolve()),
    ]


def _m5_artifact(run_dir: Path, name: str) -> dict[str, Any]:
    return h2b._artifact(run_dir, name)


def _m5_artifacts(run_dir: Path) -> dict[str, Any]:
    names = [
        "stage_progress.jsonl",
        "stage_stdout.txt",
        "stage_summary.json",
        "stage_timeline.jsonl",
        "stage_root_pid.json",
        "m5_worker_summary.json",
        "m5_timeline.jsonl",
        "m5_progress.jsonl",
        "m5_stdout.txt",
        "m5_root_pid.json",
        "m5_iter20_solution.npy",
        "m5_iter20_b0_action.npy",
        "m5_iter20_residual.npy",
        "m5_iter20_rhs.npy",
        "m5_iter50_solution.npy",
        "m5_iter50_b0_action.npy",
        "m5_iter50_residual.npy",
        "m5_iter50_rhs.npy",
        "m5_iter100_solution.npy",
        "m5_iter100_b0_action.npy",
        "m5_iter100_residual.npy",
        "m5_iter100_rhs.npy",
    ]
    return {name: _m5_artifact(run_dir, name) for name in names}


def _m5_checkpoint_contract(
    run_dir: Path, item: Mapping[str, Any], *, tolerance: float = 1.0e-12
) -> tuple[bool, float | None, str | None]:
    if not isinstance(item, Mapping) or "iteration" not in item or "artifacts" not in item:
        return False, None, "checkpoint_shape"
    iteration = item["iteration"]
    artifacts = item["artifacts"]
    if iteration not in M5_CHECKPOINT_ITERATIONS or not isinstance(artifacts, Mapping):
        return False, None, "checkpoint_identity"
    required = {"solution", "b0_action", "residual", "rhs"}
    if set(artifacts) != required:
        return False, None, "checkpoint_artifacts"
    import numpy as np

    loaded: dict[str, Any] = {}
    try:
        for name in required:
            record = artifacts[name]
            if not isinstance(record, Mapping):
                return False, None, f"checkpoint_{name}_record"
            relative = record.get("path")
            expected_path = f"m5_iter{iteration}_{name}.npy"
            required_record = {"path", "bytes", "sha256", "array_sha256", "shape", "dtype"}
            if (
                set(record) != required_record
                or relative != expected_path
                or not isinstance(record.get("bytes"), int)
                or not isinstance(record.get("sha256"), str)
                or not isinstance(record.get("array_sha256"), str)
            ):
                return False, None, f"checkpoint_{name}_record"
            actual = _m5_artifact(run_dir, relative)
            if (
                actual.get("present") is not True
                or actual.get("path") != record["path"]
                or actual.get("bytes") != record["bytes"]
                or actual.get("sha256") != record["sha256"]
            ):
                return False, None, f"checkpoint_{name}_artifact"
            value = np.load(run_dir / relative, mmap_mode="r", allow_pickle=False)
            loaded[name] = value
            if (
                value.dtype != np.dtype(np.complex128)
                or value.ndim != 1
                or not np.all(np.isfinite(value))
                or list(value.shape) != record.get("shape")
                or record.get("dtype") != str(value.dtype)
            ):
                return False, None, f"checkpoint_{name}_array"
            if record.get("array_sha256") != hashlib.sha256(
                memoryview(np.ascontiguousarray(value)).cast("B")
            ).hexdigest():
                return False, None, f"checkpoint_{name}_array_sha"
            if name == "rhs" and record["array_sha256"] != M5_RHS_SHA256:
                return False, None, "checkpoint_rhs_binding"
        expected = np.asarray(loaded["rhs"]) - np.asarray(loaded["b0_action"])
        residual = np.asarray(loaded["residual"])
        denom = max(float(np.linalg.norm(loaded["rhs"])), np.finfo(float).tiny)
        closure = float(np.linalg.norm(expected - residual) / denom)
        relative = float(
            np.linalg.norm(residual)
            / max(float(np.linalg.norm(loaded["rhs"])), np.finfo(float).tiny)
        )
    finally:
        loaded.clear()
    recorded = item.get("true_relative_residual")
    if (
        not isinstance(recorded, (int, float))
        or isinstance(recorded, bool)
        or not np.isfinite(recorded)
        or abs(float(recorded) - relative) > tolerance * max(1.0, abs(relative))
        or closure > tolerance
    ):
        return False, relative, "checkpoint_recompute"
    return True, relative, None


def _m5_check_payload(
    worker: Mapping[str, Any], *, m4y_record: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Check worker-shaped scalar evidence without rebuilding FE objects."""

    import numpy as np

    checks = {
        "schema": False,
        "scope": False,
        "m4y_negative_binding": False,
        "p6_identity": False,
        "m3y_binding": False,
        "screen_config": False,
        "checkpoint_set": False,
        "rhs_binding": False,
        "architecture": False,
        "store_binding": False,
        "pc_audit": False,
        "form_cache": False,
        "action_architecture": False,
        "action_counts": False,
    }
    problems: list[str] = []
    if not isinstance(worker, Mapping):
        return {"checks": checks, "problems": ["worker_missing"], "pass": False}
    checks["schema"] = worker.get("schema") == M5_WORKER_SCHEMA
    checks["scope"] = worker.get("scope") == _m5_scope()
    record = m4y_record
    if record is None:
        try:
            record = h2b._read_json(M5_M4Y_COMPACT)
        except (OSError, ValueError, json.JSONDecodeError):
            record = None
    checks["m4y_negative_binding"] = bool(
        isinstance(record, Mapping)
        and M5_M4Y_COMPACT.is_file()
        and h2b._sha256_file(M5_M4Y_COMPACT) == M5_M4Y_COMPACT_SHA256
        and record.get("status") == "gate_failed"
        and record.get("pass") is False
    )
    measurement = worker.get("measurement")
    p6 = measurement.get("p6") if isinstance(measurement, Mapping) else None
    checks["p6_identity"] = p6 == {
        "global_cells": M5_CELLS,
        "local_cells": M5_CELLS,
        "local_nloc": M5_LOCAL_NLOC,
        "global_rows": M5_GLOBAL_ROWS,
        "constraint_count": M5_CONSTRAINTS,
    }
    binding = measurement.get("m3y_binding") if isinstance(measurement, Mapping) else None
    checks["m3y_binding"] = bool(
        isinstance(binding, Mapping)
        and binding.get("source_sha256") == h2b.H2B_M4Y_M3Y_SOURCE_SHA
        and binding.get("manifest_sha256") == h2b.H2B_M4Y_M3Y_MANIFEST_SHA
        and binding.get("evidence_sha256") == h2b.H2B_M4Y_M3Y_EVIDENCE_SHA
    )
    screen = measurement.get("screen") if isinstance(measurement, Mapping) else None
    checks["screen_config"] = bool(
        isinstance(screen, Mapping)
        and screen.get("ksp_type") == "fgmres"
        and screen.get("pc_side") == "right"
        and screen.get("norm_type") == "unpreconditioned"
        and screen.get("restart") == 20
        and screen.get("max_it") == 100
        and screen.get("fixed_screen") is True
        and screen.get("iterations") == 100
        and screen.get("final") is None
        and screen.get("sample_action_count") == 3
        and screen.get("rtol") == 0.0
        and screen.get("atol") == 0.0
        and screen.get("restart_set") == 20
        and screen.get("max_it_actual") == 100
    )
    samples = screen.get("samples") if isinstance(screen, Mapping) else None
    if isinstance(samples, Mapping) and set(samples) == {"20", "50", "100"}:
        checks["checkpoint_set"] = True
    rhs_binding = measurement.get("rhs_binding") if isinstance(measurement, Mapping) else None
    rhs_measurement = measurement.get("rhs") if isinstance(measurement, Mapping) else None
    checks["rhs_binding"] = bool(
        isinstance(rhs_binding, Mapping)
        and rhs_binding
        == {
            "label": "physical-RHS-like",
            "sha256": M5_RHS_SHA256,
            "definition": "physical-RHS-like primal, slave rows zero, exact B0 action",
        }
        and isinstance(rhs_measurement, Mapping)
        and rhs_measurement.get("sha256") == M5_RHS_SHA256
    )
    architecture = measurement.get("architecture") if isinstance(measurement, Mapping) else None
    checks["architecture"] = architecture == {
        "fine_space": "uncondensed_fullspace",
        "global_matrix_materialized": False,
        "static_condensation": False,
        "trace_slab": False,
        "dtn": False,
        "coarse_constructed": False,
        "pde": False,
        "ordinary_default_changed": False,
    }
    store = measurement.get("m3y_store_audit") if isinstance(measurement, Mapping) else None
    checks["store_binding"] = bool(
        isinstance(store, Mapping)
        and store.get("packed_factor_count") == 84
        and store.get("cell_count") == 252
        and type(store.get("retained_total_bytes")) is int
        and store["retained_total_bytes"] <= 560_000_000
        and store.get("retained_total_gate") is True
        and measurement.get("m3y_store_mmap_readonly") is True
    )
    pc_audit = measurement.get("pc_audit") if isinstance(measurement, Mapping) else None
    pc_materialization = (
        pc_audit.get("materialization_identity")
        if isinstance(pc_audit, Mapping)
        else None
    )
    checks["pc_audit"] = bool(
        isinstance(pc_audit, Mapping)
        and pc_audit.get("unique_factor_count") == 84
        and pc_audit.get("factor_reuse_count") == 168
        and pc_audit.get("factor_copy_count") == 0
        and pc_audit.get("per_cell_solution_retained") is False
        and type(pc_audit.get("m3y_retained_total_bytes")) is int
        and pc_audit["m3y_retained_total_bytes"] <= 560_000_000
        and isinstance(pc_audit.get("partition_of_unity_closure_error"), (int, float))
        and np.isfinite(float(pc_audit["partition_of_unity_closure_error"]))
        and float(pc_audit["partition_of_unity_closure_error"]) <= 1.0e-14
        and pc_audit.get("fine_space") == "uncondensed_fullspace"
        and pc_audit.get("ordinary_default_changed") is False
        and h2b._m4y_materialization_valid(pc_materialization)
    )
    form = measurement.get("form") if isinstance(measurement, Mapping) else None
    cache = measurement.get("cache") if isinstance(measurement, Mapping) else None
    checks["form_cache"] = bool(
        isinstance(form, Mapping)
        and form.get("role") == "b0"
        and form.get("code_state") == "hit_no_new_decl_impl"
        and isinstance(cache, Mapping)
        and cache.get("unchanged") is True
        and cache.get("before") == cache.get("after")
    )
    action_audit = measurement.get("action_audit") if isinstance(measurement, Mapping) else None
    checks["action_architecture"] = bool(
        h2b._m4y_action_audit_valid(action_audit)
    )
    operator_audit = measurement.get("operator_action_audit") if isinstance(measurement, Mapping) else None
    pc_action_audit = measurement.get("pc_action_audit") if isinstance(measurement, Mapping) else None
    checks["action_counts"] = bool(
        isinstance(screen, Mapping)
        and isinstance(operator_audit, Mapping)
        and isinstance(pc_action_audit, Mapping)
        and type(screen.get("operator_apply_count")) is int
        and screen["operator_apply_count"] > 0
        and type(screen.get("pc_apply_count")) is int
        and screen["pc_apply_count"] > 0
        and operator_audit.get("apply_count") == screen["operator_apply_count"]
        and pc_action_audit.get("apply_count") == screen["pc_apply_count"]
        and isinstance(action_audit, Mapping)
        and type(action_audit.get("apply_count")) is int
        and action_audit["apply_count"]
        == 1 + screen["operator_apply_count"] + screen["pc_apply_count"]
    )
    problems.extend(name for name, passed in checks.items() if not passed)
    return {"checks": checks, "problems": problems, "pass": not problems}


def _m5_runtime_measurement(
    run_dir: Path, worker: Mapping[str, Any], online: Mapping[str, Any]
) -> dict[str, Any]:
    measurement = worker.get("measurement")
    if not isinstance(measurement, Mapping):
        raise ValueError("M5 measurement is missing")
    screen = measurement.get("screen")
    if not isinstance(screen, Mapping):
        raise ValueError("M5 screen measurement is missing")
    recomputed: dict[str, float] = {}
    checkpoint_problems: list[str] = []
    for key in ("20", "50", "100"):
        item = screen.get("samples", {}).get(key) if isinstance(screen.get("samples"), Mapping) else None
        ok, relative, problem = _m5_checkpoint_contract(run_dir, item)
        if not ok or relative is None:
            checkpoint_problems.append(problem or f"checkpoint_{key}")
        else:
            recomputed[key] = relative
    if not isinstance(online, Mapping):
        return {
            "pass": False,
            "problems": ["online_missing"],
            "recomputed_true_residuals": {},
            "checkpoint_artifacts": _m5_artifacts(run_dir),
        }
    online_gone = bool(online.get("processes_gone_after_m5"))
    from src.solvers.hcurl_h2b_m5_coercive import evaluate_m5_screen_gate

    gate = evaluate_m5_screen_gate(
        {key: {"true_relative_residual": value} for key, value in recomputed.items()},
        online_peak_rss_bytes=online.get("peak_rss_bytes"),
        online_swap_bytes=online.get("swap_bytes"),
        processes_gone=online_gone,
    )
    if checkpoint_problems:
        gate["pass"] = False
        gate["problems"] = checkpoint_problems + list(gate["problems"])
    result = dict(gate)
    result["recomputed_true_residuals"] = recomputed
    result["online_peak_rss_bytes"] = online.get("peak_rss_bytes")
    result["online_swap_bytes"] = online.get("swap_bytes")
    result["checkpoint_artifacts"] = _m5_artifacts(run_dir)
    if not isinstance(online.get("peak_rss_bytes"), int):
        result["pass"] = False
        result["problems"].append("online_peak_missing")
    return result


def _run_m5_worker(run_dir: Path) -> int:
    """Build the fixed B0/M4Y screen and save only three checkpoint vectors."""

    import gc
    import numpy as np
    from petsc4py import PETSc

    from src.solvers.hcurl_h2b_m4y_packed_patch_pc import (
        build_h2b_m4y_packed_patch_pc,
    )
    from src.solvers.hcurl_h2b_packed_patch_store import (
        load_h2b_m3y_packed_patch_store,
    )
    from src.solvers.hcurl_h2b_m5_coercive import (
        M5M4YPCContext,
        build_m5_b0_mat,
        run_m5_right_fgmres_screen,
    )
    from src.solvers.hcurl_rank_one_mpc_action import (
        build_task037_extra_h1r2_mpc_action,
    )

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    progress_path = run_dir / "m5_progress.jsonl"
    summary_path = run_dir / "m5_worker_summary.json"
    started = time.perf_counter()
    h2a = h2b._lazy_h2a()
    source_start = h2b._source_pair(h2a)
    source_end: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    form_record: dict[str, Any] | None = None
    measurement: dict[str, Any] | None = None
    error: str | None = None
    action = None
    source_vec = None
    rhs_vec = None
    matrix = None
    store = None
    with progress_path.open("w", encoding="utf-8") as markers:
        try:
            stage = h2b._read_json(run_dir / "stage_summary.json")
            stage_scope = stage.get("scope")
            stage_form = stage.get("form")
            if (
                stage.get("status") != "measurement_complete"
                or not h2b._evidence_valid(stage)
                or not isinstance(stage_scope, Mapping)
                or stage_scope.get("global_rows") != M5_GLOBAL_ROWS
                or not isinstance(stage_form, Mapping)
                or stage_form.get("role") != "b0"
            ):
                raise ValueError("M5 stage authority is not valid")
            h2b._emit_marker(markers, event="authority_validated", phase="m5", started=started)
            from src.common.config_3d import target_stage4_config
            from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
            from src.solvers.common_3d_solve import _create_nedelec_space

            cfg = target_stage4_config(degree=6, h_nm=10.0)
            mesh_data = build_airbox_mesh_3d(cfg, run_dir / "m5_mesh")
            h2b._emit_marker(markers, event="mesh_ready", phase="m5", started=started)
            function_space = _create_nedelec_space(mesh_data.mesh, cfg)
            h2b._emit_marker(markers, event="space_ready", phase="m5", started=started)
            floquet = h2a.build_double_floquet_mpc(function_space, mesh_data, cfg)
            h2b._emit_marker(markers, event="floquet_mpc_ready", phase="m5", started=started)
            manifest_path = h2b.H2B_M4Y_M3Y_MANIFEST
            manifest = h2b._read_json(manifest_path)
            if (
                h2b._sha256_file(manifest_path) != h2b.H2B_M4Y_M3Y_MANIFEST_SHA
                or manifest.get("evidence_sha256") != h2b.H2B_M4Y_M3Y_EVIDENCE_SHA
                or manifest.get("metadata", {})
                .get("identity", {})
                .get("source_identity", {})
                .get("source_commit_full_sha")
                != h2b.H2B_M4Y_M3Y_SOURCE_SHA
            ):
                raise ValueError("M5 M3Y manifest authority mismatch")
            store = load_h2b_m3y_packed_patch_store(
                manifest_path, task037_extra_h2b=True
            )
            h2b._emit_marker(markers, event="cache_load_ready", phase="m5", started=started)
            index_map = function_space.dofmap.index_map
            p6 = {
                "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
                "local_cells": int(mesh_data.mesh.topology.index_map(3).size_local),
                "local_nloc": int(function_space.element.space_dimension),
                "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
                "constraint_count": int(floquet.num_constraints),
            }
            expected_p6 = {
                "global_cells": M5_CELLS,
                "local_cells": M5_CELLS,
                "local_nloc": M5_LOCAL_NLOC,
                "global_rows": M5_GLOBAL_ROWS,
                "constraint_count": M5_CONSTRAINTS,
            }
            if p6 != expected_p6:
                raise ValueError(f"M5 p6 identity mismatch: {p6}")
            cache_dir = run_dir / "jit_cache"
            cache_before = h2b._cache_snapshot(cache_dir)
            b0, _epsilon = h2b._build_b0_form(function_space, mesh_data, cfg)
            runtime = h2b._runtime_identity(
                h2a,
                compiler_probe=False,
                compiler=stage["runtime_identity"]["compiler"],
            )
            action = build_task037_extra_h1r2_mpc_action(
                b0,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=h2b._expected_jit_options(cache_dir),
            )
            form_record = h2b._form_record(
                action._action_form,
                action._action_ufl,
                cache_dir,
                cfg,
                function_space,
                "b0",
            )
            cache_after = h2b._cache_snapshot(cache_dir)
            if (
                form_record.get("code_state") != "hit_no_new_decl_impl"
                or cache_before != cache_after
            ):
                raise ValueError("M5 B0 form did not reuse staged cache")
            owned = int(index_map.size_local)
            source_vec = action.output_vector.duplicate()
            slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)

            def exact_action(source: np.ndarray, target: np.ndarray) -> None:
                with source_vec.localForm() as local:
                    local.set(0.0)
                    local.array_w[: source.size] = source
                source_vec.ghostUpdate(
                    addv=PETSc.InsertMode.INSERT_VALUES,
                    mode=PETSc.ScatterMode.FORWARD,
                )
                result = action.mult(source_vec)
                target[:] = np.asarray(
                    result.getArray(readonly=True), dtype=np.complex128
                )

            primal_arrays = h2b._source_arrays(function_space, cfg, slaves, floquet.mpc)
            primal = np.array(
                primal_arrays["physical-RHS-like"], dtype=np.complex128, copy=True
            )
            del primal_arrays
            primal[slaves] = 0.0
            rhs = np.empty(owned, dtype=np.complex128)
            exact_action(primal, rhs)
            rhs[slaves] = 0.0
            rhs_sha = h2b._array_sha256(rhs)
            if rhs_sha != M5_RHS_SHA256:
                raise ValueError(f"M5 fresh RHS SHA mismatch: {rhs_sha}")
            h2b._emit_marker(markers, event="source_ready", phase="m5", started=started)
            with source_vec.localForm() as local:
                local.set(0.0)
                local.array_w[:owned] = rhs
            source_vec.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            rhs_vec = source_vec.duplicate()
            with rhs_vec.localForm() as local:
                local.set(0.0)
                local.array_w[:owned] = rhs
            rhs_vec.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            pc = build_h2b_m4y_packed_patch_pc(
                store,
                global_row_count=M5_GLOBAL_ROWS,
                exact_action=exact_action,
                slave_identity_rows=slaves,
                task037_extra_h2b=True,
            )
            matrix, matrix_context = build_m5_b0_mat(
                action,
                owned_rows=owned,
                global_rows=M5_GLOBAL_ROWS,
                comm=mesh_data.mesh.comm,
            )
            pc_context = M5M4YPCContext(pc, global_rows=M5_GLOBAL_ROWS)
            h2b._emit_marker(markers, event="outer_ksp_ready", phase="m5", started=started)
            screen = run_m5_right_fgmres_screen(
                matrix,
                rhs_vec,
                pc_context=pc_context,
                operator_context=matrix_context,
                checkpoint_dir=run_dir,
            )
            measurement = {
                "p6": p6,
                "rhs": {
                    "label": "physical-RHS-like",
                    "sha256": rhs_sha,
                    "definition": "physical-RHS-like primal, slave rows zero, exact B0 action",
                },
                "rhs_binding": {
                    "label": "physical-RHS-like",
                    "sha256": M5_RHS_SHA256,
                    "definition": "physical-RHS-like primal, slave rows zero, exact B0 action",
                },
                "screen": screen,
                "operator_action_audit": matrix_context.audit,
                "pc_action_audit": pc_context.audit,
                "action_audit": h2a._jsonable(action.audit),
                "pc_audit": pc.audit,
                "m3y_store_audit": store.audit_jsonable(),
                "m3y_binding": {
                    "source_sha256": h2b.H2B_M4Y_M3Y_SOURCE_SHA,
                    "manifest_sha256": h2b.H2B_M4Y_M3Y_MANIFEST_SHA,
                    "evidence_sha256": h2b.H2B_M4Y_M3Y_EVIDENCE_SHA,
                },
                "m3y_store_mmap_readonly": bool(
                    len(store.factors) == h2b.H2B_M3Y_NEIGHBORHOOD_COUNT
                    and all(
                        isinstance(factor.packed_values.base, np.memmap)
                        and factor.packed_values.flags.writeable is False
                        for factor in store.factors
                    )
                ),
                "form": form_record,
                "cache": {
                    "before": cache_before,
                    "after": cache_after,
                    "unchanged": cache_before == cache_after,
                },
                "architecture": {
                    key: _m5_scope()[key]
                    for key in (
                        "fine_space",
                        "global_matrix_materialized",
                        "static_condensation",
                        "trace_slab",
                        "dtn",
                        "coarse_constructed",
                        "pde",
                        "ordinary_default_changed",
                    )
                },
            }
            h2b._emit_marker(markers, event="summary_ready", phase="m5", started=started)
        except h2b._worker_error_types() as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            if matrix is not None:
                matrix.destroy()
            if rhs_vec is not None:
                rhs_vec.destroy()
            if source_vec is not None:
                source_vec.destroy()
            if action is not None:
                action.destroy()
            if store is not None:
                del store
            h2a.clear_floquet_topology_cache()
            gc.collect()
    source_end = h2b._source_pair(h2a)
    status = "measurement_complete" if error is None and measurement is not None else "gate_failed"
    payload = h2b._attach_evidence(
        {
            "schema": M5_WORKER_SCHEMA,
            "phase": "m5",
            "status": status,
            "route": "M5",
            "scope": _m5_scope(),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "runtime_identity": runtime,
            "form": form_record,
            "measurement": measurement,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    h2b._write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _run_m5_watchdog(run_dir: Path) -> int:
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        raise FileExistsError(f"M5 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    started = time.perf_counter()
    executable = h2b._worker_executable()
    source_start = h2b._light_source()
    stage = h2b._monitor_phase(
        run_dir,
        "stage",
        h2b._worker_command(executable, "jit-worker", run_dir),
        h2b.H2B_STAGE_TIMEOUT_SECONDS,
        h2b.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES,
    )
    stage_drain = h2b._bounded_process_drain(stage)
    stage["processes_gone_before_m5"] = bool(stage_drain["gone"])
    stage_ok = bool(
        (run_dir / "stage_summary.json").is_file()
        and h2b._stage_gate_allows_online(
            stage,
            h2b._read_json(run_dir / "stage_summary.json"),
            bool(stage_drain["gone"]),
            run_dir,
        )
        and stage.get("peak_rss_bytes") < h2b.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES
        and stage.get("swap_bytes") == M5_SWAP_LIMIT_BYTES
    )
    online = None
    error = None
    if stage_ok:
        online = h2b._monitor_phase(
            run_dir,
            "m5",
            _m5_worker_command(executable, run_dir),
            M5_TIMEOUT_SECONDS,
            M5_ONLINE_RSS_LIMIT_BYTES,
        )
        online_drain = h2b._bounded_process_drain(online)
        online["processes_gone_after_m5"] = bool(online_drain["gone"])
        try:
            online_metrics = h2b._timeline_metrics(
                run_dir / "m5_timeline.jsonl", "m5"
            )
            online["compiler_descendant_pids"] = online_metrics[
                "compiler_descendant_pids"
            ]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            online["compiler_descendant_pids"] = None
        if not (
            online.get("return_code") == 0
            and online.get("termination") is None
            and online.get("processes_gone_after_m5") is True
            and online.get("peak_rss_bytes") < M5_ONLINE_RSS_LIMIT_BYTES
            and online.get("swap_bytes") == M5_SWAP_LIMIT_BYTES
            and online.get("compiler_descendant_pids") == []
        ):
            error = "m5_online_resource_or_execution_gate_failed"
    else:
        error = "stage_gate_failed_before_m5"
    source_end = h2b._light_source()
    passed = bool(
        error is None
        and online is not None
        and online.get("return_code") == 0
        and online.get("termination") is None
        and online.get("processes_gone_after_m5") is True
        and online.get("peak_rss_bytes") < M5_ONLINE_RSS_LIMIT_BYTES
        and online.get("swap_bytes") == M5_SWAP_LIMIT_BYTES
        and online.get("compiler_descendant_pids") == []
    )
    payload = h2b._attach_evidence(
        {
            "schema": M5_WATCHDOG_SCHEMA,
            "status": "pass" if passed else "gate_failed",
            "pass": passed,
            "route": "M5",
            "run_dir": str(run_dir),
            "scope": _m5_scope(),
            "command_identity": {
                "python": executable,
                "stage_command": stage.get("command"),
                "m5_command": None if online is None else online.get("command"),
            },
            "source_at_start": source_start,
            "source_at_end": source_end,
            "stage": stage,
            "online": online,
            "raw_artifacts": _m5_artifacts(run_dir),
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    h2b._write_json(run_dir / "m5_watchdog_summary.json", payload)
    return 0 if passed else 1


def _m5_check_raw(run_dir: Path, checker_source: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    watchdog = h2b._read_json(run_dir / "m5_watchdog_summary.json")
    worker = h2b._read_json(run_dir / "m5_worker_summary.json")
    worker_start = worker.get("source_at_start")
    watchdog_start = watchdog.get("source_at_start")
    checks = {
        "watchdog_evidence": watchdog.get("schema") == M5_WATCHDOG_SCHEMA and h2b._evidence_valid(watchdog),
        "worker_evidence": worker.get("schema") == M5_WORKER_SCHEMA and h2b._evidence_valid(worker),
        "source": h2b._source_pair_valid(worker_start, worker.get("source_at_end"))
        and h2b._source_pair_valid(watchdog.get("source_at_start"), watchdog.get("source_at_end"))
        and worker_start == watchdog_start
        and h2b._checker_source_valid(checker_source)
        and isinstance(worker_start, Mapping)
        and checker_source.get("source_commit_full_sha")
        == worker_start.get("source_commit_full_sha")
        and checker_source.get("source_commit_full_sha")
        == watchdog_start.get("source_commit_full_sha")
        if isinstance(watchdog_start, Mapping)
        else False,
        "scope": worker.get("scope") == _m5_scope() and watchdog.get("scope") == _m5_scope(),
        "command_identity": False,
        "worker_status": worker.get("status") == "measurement_complete" and worker.get("error") is None,
        "progress": False,
        "lifecycle_resource": False,
        "runtime_form_cache": False,
        "m3y_manifest_store": False,
        "raw_artifacts": False,
    }
    command_identity = watchdog.get("command_identity")
    if isinstance(command_identity, Mapping) and isinstance(command_identity.get("python"), str):
        executable = command_identity["python"]
        checks["command_identity"] = bool(
            command_identity.get("stage_command")
            == h2b._worker_command(executable, "jit-worker", run_dir)
            and command_identity.get("m5_command")
            == _m5_worker_command(executable, run_dir)
        )
    try:
        checks["progress"] = (
            h2b._progress_events(run_dir / "m5_progress.jsonl", "m5")
            == list(M5_EVENTS)
        )
        stage_metrics = h2b._timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")
        online_metrics = h2b._timeline_metrics(run_dir / "m5_timeline.jsonl", "m5")
        stage_process = watchdog.get("stage")
        online_process = watchdog.get("online")
        stage_summary = h2b._read_json(run_dir / "stage_summary.json")
        checks["lifecycle_resource"] = bool(
            isinstance(stage_process, Mapping)
            and isinstance(online_process, Mapping)
            and stage_process.get("return_code") == 0
            and stage_process.get("termination") is None
            and stage_process.get("processes_gone_before_m5") is True
            and online_process.get("return_code") == 0
            and online_process.get("termination") is None
            and online_process.get("processes_gone_after_m5") is True
            and stage_metrics.get("peak_rss_bytes") == stage_process.get("peak_rss_bytes")
            and stage_metrics.get("swap_bytes") == stage_process.get("swap_bytes")
            and online_metrics.get("peak_rss_bytes") == online_process.get("peak_rss_bytes")
            and online_metrics.get("swap_bytes") == online_process.get("swap_bytes")
            and online_metrics.get("compiler_descendant_pids") == []
            and stage_metrics.get("peak_rss_bytes") < h2b.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES
            and stage_metrics.get("swap_bytes") == 0
            and online_metrics.get("peak_rss_bytes") < M5_ONLINE_RSS_LIMIT_BYTES
            and online_metrics.get("swap_bytes") == 0
            and h2b._stage_gate_allows_online(
                stage_process,
                stage_summary,
                stage_process.get("processes_gone_before_m5") is True,
                run_dir,
            )
            and watchdog.get("status") == "pass"
        )
        worker_measurement = worker.get("measurement")
        stage_form = stage_summary.get("form")
        worker_form = worker.get("form")
        worker_cache = (
            worker_measurement.get("cache")
            if isinstance(worker_measurement, Mapping)
            else None
        )
        checks["runtime_form_cache"] = bool(
            h2b._runtime_valid(stage_summary.get("runtime_identity"))
            and h2b._runtime_valid(worker.get("runtime_identity"))
            and stage_summary["runtime_identity"].get("sys_executable")
            == worker["runtime_identity"].get("sys_executable")
            and h2b._forms_match(stage_form, worker_form, run_dir)
            and isinstance(worker_cache, Mapping)
            and worker_cache.get("before") == worker_cache.get("after")
            and stage_summary.get("cache_inventory") == worker_cache.get("after")
            and worker_cache.get("after") == h2b._cache_snapshot(run_dir / "jit_cache")
        )
        binding = (
            worker_measurement.get("m3y_binding")
            if isinstance(worker_measurement, Mapping)
            else None
        )
        manifest = h2b._read_json(h2b.H2B_M4Y_M3Y_MANIFEST)
        from src.solvers.hcurl_h2b_packed_patch_store import (
            load_h2b_m3y_packed_patch_store,
        )

        loaded_store = load_h2b_m3y_packed_patch_store(
            h2b.H2B_M4Y_M3Y_MANIFEST, task037_extra_h2b=True
        )
        loaded_audit = loaded_store.audit_jsonable()
        loaded_mmap = bool(
            len(loaded_store.factors) == h2b.H2B_M3Y_NEIGHBORHOOD_COUNT
            and all(
                isinstance(factor.packed_values.base, np.memmap)
                and factor.packed_values.flags.writeable is False
                for factor in loaded_store.factors
            )
        )
        checks["m3y_manifest_store"] = bool(
            isinstance(worker_measurement, Mapping)
            and isinstance(binding, Mapping)
            and binding.get("source_sha256") == h2b.H2B_M4Y_M3Y_SOURCE_SHA
            and binding.get("manifest_sha256") == h2b.H2B_M4Y_M3Y_MANIFEST_SHA
            and binding.get("evidence_sha256") == h2b.H2B_M4Y_M3Y_EVIDENCE_SHA
            and h2b._sha256_file(h2b.H2B_M4Y_M3Y_MANIFEST)
            == h2b.H2B_M4Y_M3Y_MANIFEST_SHA
            and manifest.get("evidence_sha256") == h2b.H2B_M4Y_M3Y_EVIDENCE_SHA
            and manifest.get("metadata", {})
            .get("identity", {})
            .get("source_identity", {})
            .get("source_commit_full_sha")
            == h2b.H2B_M4Y_M3Y_SOURCE_SHA
            and h2b._m4y_m3y_audit_valid(loaded_audit)
            and loaded_mmap
            and loaded_audit == worker_measurement.get("m3y_store_audit")
        )
        del loaded_store
        checks["raw_artifacts"] = watchdog.get("raw_artifacts") == _m5_artifacts(run_dir)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        checks["progress"] = False
        checks["lifecycle_resource"] = False
        checks["runtime_form_cache"] = False
        checks["m3y_manifest_store"] = False
        checks["raw_artifacts"] = False
    payload = _m5_check_payload(worker)
    checks.update({f"worker_{key}": value for key, value in payload["checks"].items()})
    online = watchdog.get("online")
    try:
        recomputed = _m5_runtime_measurement(run_dir, worker, online)
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        recomputed = {"pass": False, "problems": [f"recompute:{type(exc).__name__}"]}
    checks["independent_checkpoint_recompute"] = recomputed.get("pass") is True
    passed = bool(all(checks.values()) and recomputed.get("pass") is True)
    problems = [name for name, value in checks.items() if value is not True]
    problems.extend(recomputed.get("problems", []))
    return {
        "schema": M5_CHECK_SCHEMA,
        "status": "pass" if passed else "gate_failed",
        "pass": passed,
        "route": "M5-FIRST-SCREEN-PASS" if passed else "M5-review-only",
        "checks": checks,
        "problems": sorted(set(problems)),
        "measurements": {
            "worker": worker.get("measurement"),
            "checker_recomputed": recomputed,
        },
        "checker_source": checker_source,
        "raw_artifacts": watchdog.get("raw_artifacts"),
    }


def _run_m5_check(run_dir: Path, output: Path) -> int:
    try:
        checker_source = h2b._light_source()
        result = _m5_check_raw(Path(run_dir).resolve(), checker_source)
    except h2b._worker_error_types() as exc:
        result = {
            "schema": M5_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "route": "M5-review-only",
            "checks": {},
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
        }
    h2b._write_json(Path(output).resolve(), h2b._attach_evidence(result))
    print(f"M5 check status={result['status']} output={Path(output).resolve()}", flush=True)
    return 0 if result["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    worker = sub.add_parser("m5-worker")
    worker.add_argument("--run-dir", required=True)
    worker.set_defaults(handler=lambda args: _run_m5_worker(Path(args.run_dir)))
    watchdog = sub.add_parser("m5-watchdog")
    watchdog.add_argument("--run-dir", required=True)
    watchdog.set_defaults(handler=lambda args: _run_m5_watchdog(Path(args.run_dir)))
    checker = sub.add_parser("m5-check")
    checker.add_argument("--run-dir", required=True)
    checker.add_argument("--output", required=True)
    checker.set_defaults(
        handler=lambda args: _run_m5_check(Path(args.run_dir), Path(args.output))
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
