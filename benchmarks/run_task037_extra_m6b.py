"""Thin M6B shifted-screen stage, builder, online, and checker entry point.

The controller remains standard-library only; DOLFINx/PETSc are imported only
inside the three workers.  Numeric patch/action logic lives in ``src`` and the
checker reads raw evidence rather than rebuilding a finite-element operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
M6B_SCHEMA = "task037.extra.h2b.m6b.v1"
M6B_STAGE_SCHEMA = f"{M6B_SCHEMA}.stage"
M6B_BUILDER_SCHEMA = f"{M6B_SCHEMA}.builder"
M6B_WORKER_SCHEMA = f"{M6B_SCHEMA}.worker"
M6B_WATCHDOG_SCHEMA = f"{M6B_SCHEMA}.watchdog"
M6B_CHECK_SCHEMA = f"{M6B_SCHEMA}.check"
M6B_DEGREE = 6
M6B_H_NM = 10.0
M6B_GLOBAL_CELLS = 252
M6B_LOCAL_NLOC = 882
M6B_GLOBAL_ROWS = 173_802
M6B_CONSTRAINTS = 9_210
M6B_BETA = 0.5
M6B_SHARED_VOLUME_OPERATOR = (
    "C-k0^2*M_epsilon+i*beta*k0^2*M_abs_epsilon"
)
M6B_SHIFTED_OPERATOR = (
    "B_beta=Kcurl-k0^2*M_epsilon+i*beta*k0^2*M_abs_epsilon"
)
M6B_SHARED_VOLUME_REPRESENTATION = "exact_DG0_single_integral"
M6B_SHARED_VOLUME_SCHEMA = "task037.extra.h2b.m6b.shared-volume.v1"
M6B_FACTOR_COUNT = 84
M6B_FACTOR_REUSE = 168
M6B_RETAINED_TOTAL_LIMIT_BYTES = 1_100_000_000
M6B_WATCHDOG_RSS_LIMIT_BYTES = 1_950_000_000
M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES = 1_900_000_000
M6B_STAGE_TIMEOUT_SECONDS = 3_600.0
M6B_BUILDER_TIMEOUT_SECONDS = 10_800.0
M6B_ONLINE_TIMEOUT_SECONDS = 10_800.0
M6B_SWAP_LIMIT_BYTES = 0
M6B_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_FACTOR_PAYLOAD_BYTES = 84 * (882 * 882 * 16 + 882 * 4)
M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES = 8_000_000
M6B_M5_PEAK_MINUS_M3Y_BYTES = 978_083_840 - 525_196_562
M6B_M6A_RETAINED_WORK_BYTES = 16_673_350
M6B_ONE_TRANSIENT_FACTOR_BYTES = 882 * 882 * 16 + 882 * 4
M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES = 64_000_000
M6B_FIXED_RUNTIME_RESERVE_BYTES = 64_000_000
M6B_PREDICTED_LIVE_SET_BYTES = sum(
    (
        M6B_M5_PEAK_MINUS_M3Y_BYTES,
        M6B_FACTOR_PAYLOAD_BYTES,
        M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES,
        M6B_M6A_RETAINED_WORK_BYTES,
        M6B_ONE_TRANSIENT_FACTOR_BYTES,
        M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES,
        M6B_FIXED_RUNTIME_RESERVE_BYTES,
    )
)
M6B_W1_SCHEMA = "task037.extra.m6b.sparse-range-builder.v2"
M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES = 1_657_665_813
M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W1_BUILDER_RSS_LIMIT_BYTES = 1_500_000_000
M6B_STAGE_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "proxy_forms_ready",
    "outer_form_ready",
    "shifted_form_ready",
    "surface_forms_ready",
    "summary_ready",
)
M6B_BUILDER_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "class_expansion_ready",
    "class_blocks_ready",
    "neighborhood_ready",
    "patch_stream_ready",
    "factor_store_ready",
    "summary_ready",
)
M6B_ONLINE_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "cache_ready",
    "store_ready",
    "outer_action_ready",
    "rhs_ready",
    "screen_ready",
    "summary_ready",
)
M6B_SCREEN_ITERATIONS = (20, 100, 150, 200)
M6B_SCREEN_RHO_LIMITS = {
    "20": 0.60,
    "100": 0.20,
    "200": 0.08,
}
M6B_IMPROVEMENT_LIMIT = 0.15


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _attach_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("evidence_sha256", None)
    result["evidence_sha256"] = hashlib.sha256(_canonical_json(result)).hexdigest()
    return result


def _evidence_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    observed = value.get("evidence_sha256")
    return (
        isinstance(observed, str)
        and len(observed) == 64
        and observed == _attach_evidence(value).get("evidence_sha256")
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {"path": relative, "present": False}
    return {
        "path": relative,
        "present": True,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _m6b_scope(*, phase: str | None = None) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "beta": M6B_BETA,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "shifted_operator": M6B_SHIFTED_OPERATOR,
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "ordinary_default": False,
        "watchdog_rss_limit_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "online_completion_rss_limit_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "stage_timeout_seconds": M6B_STAGE_TIMEOUT_SECONDS,
        "builder_timeout_seconds": M6B_BUILDER_TIMEOUT_SECONDS,
        "online_timeout_seconds": M6B_ONLINE_TIMEOUT_SECONDS,
        "timeout_basis": (
            "M5 100-step measured wall plus shifted-LU one-PC timing; "
            "online budget is fixed at 10800 seconds"
        ),
        "swap_limit_bytes": M6B_SWAP_LIMIT_BYTES,
        "predicted_live_set_bytes": M6B_PREDICTED_LIVE_SET_BYTES,
        "predicted_live_set_limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "predicted_live_set_is_measurement": False,
        "predicted_live_set_basis": {
            "m5_online_peak_minus_m3y_retained_bytes": M6B_M5_PEAK_MINUS_M3Y_BYTES,
            "shifted_factor_payload_bytes": M6B_FACTOR_PAYLOAD_BYTES,
            "shifted_store_metadata_reserve_bytes": M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES,
            "m6a_retained_plus_work_bytes": M6B_M6A_RETAINED_WORK_BYTES,
            "one_transient_factor_bytes": M6B_ONE_TRANSIENT_FACTOR_BYTES,
            "second_volume_action_reserve_bytes": M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES,
            "fixed_runtime_reserve_bytes": M6B_FIXED_RUNTIME_RESERVE_BYTES,
        },
        "screen_iterations": list(M6B_SCREEN_ITERATIONS),
        "screen_rho_limits": dict(M6B_SCREEN_RHO_LIMITS),
        "screen_improvement_limit": M6B_IMPROVEMENT_LIMIT,
        "retained_total_limit_bytes": M6B_RETAINED_TOTAL_LIMIT_BYTES,
        "physical_rhs_definition": (
            "fresh M6A incident top traction plus fixed modal projections"
        ),
    }
    if phase is not None:
        scope["phase"] = str(phase)
    return scope


def _predicted_live_set() -> dict[str, Any]:
    components = {
        "m5_online_peak_minus_m3y_retained_bytes": M6B_M5_PEAK_MINUS_M3Y_BYTES,
        "shifted_lu_factor_payload_bytes": M6B_FACTOR_PAYLOAD_BYTES,
        "shifted_store_metadata_reserve_bytes": M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES,
        "m6a_retained_plus_work_bytes": M6B_M6A_RETAINED_WORK_BYTES,
        "one_transient_factor_bytes": M6B_ONE_TRANSIENT_FACTOR_BYTES,
        "second_volume_action_reserve_bytes": M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES,
        "fixed_runtime_reserve_bytes": M6B_FIXED_RUNTIME_RESERVE_BYTES,
    }
    total = int(sum(components.values()))
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "is_measurement": False,
    }


def _dynamic_predicted_live_set(retained_total_bytes: int) -> dict[str, Any]:
    if type(retained_total_bytes) is not int or retained_total_bytes < 0:
        raise ValueError("M6B retained store total is invalid")
    components = dict(_predicted_live_set()["components"])
    del components["shifted_lu_factor_payload_bytes"]
    del components["shifted_store_metadata_reserve_bytes"]
    components["shifted_store_retained_total_bytes"] = retained_total_bytes
    total = int(sum(components.values()))
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "is_measurement": False,
        "basis": "builder factor_audit.retained_total_bytes",
    }


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _m6b_factor_audit_valid(value: Any, *, loaded: bool) -> bool:
    required = (
        "schema",
        "beta",
        "factor_order",
        "factor_count",
        "cell_count",
        "factor_payload_bytes",
        "retained_total_bytes",
        "retained_total_gate",
        "factor_reuse_count",
        "factor_copy_count",
        "full_dense_patch_matrix_retained",
        "pivots_retained",
        "mmap_readonly",
        "mmap_loaded",
        "max_live_patch_matrix_count",
        "max_live_lu_factor_count",
        "materialization_identity",
    )
    if not isinstance(value, Mapping) or any(key not in value for key in required):
        return False
    materialization = value["materialization_identity"]
    materialization_keys = {
        "global_matrix",
        "global_constraint_matrix",
        "patch_matrices",
        "per_cell_factor",
        "static_condensation",
        "trace_slab",
        "schur",
        "slab_factor",
    }
    return bool(
        value["schema"] == "task037.extra.h2b.m6b.shifted-lu-store.v1"
        and value["beta"] == M6B_BETA
        and value["factor_order"] == M6B_LOCAL_NLOC
        and value["factor_count"] == M6B_FACTOR_COUNT
        and value["cell_count"] == M6B_GLOBAL_CELLS
        and value["factor_payload_bytes"] == M6B_FACTOR_PAYLOAD_BYTES
        and type(value["retained_total_bytes"]) is int
        and value["retained_total_bytes"] >= M6B_FACTOR_PAYLOAD_BYTES
        and value["retained_total_bytes"] <= M6B_RETAINED_TOTAL_LIMIT_BYTES
        and value["retained_total_gate"] is True
        and value["factor_reuse_count"] == M6B_FACTOR_REUSE
        and value["factor_copy_count"] == 0
        and value["full_dense_patch_matrix_retained"] is False
        and value["pivots_retained"] is True
        and value["mmap_readonly"] is loaded
        and value["mmap_loaded"] is loaded
        and value["max_live_patch_matrix_count"] == 1
        and value["max_live_lu_factor_count"] == 1
        and isinstance(materialization, Mapping)
        and set(materialization) == materialization_keys
        and all(materialization[key] is False for key in materialization_keys)
    )


def _m6b_builder_factor_audit_valid(value: Any) -> bool:
    return _m6b_factor_audit_valid(value, loaded=False)


def _m6b_loaded_factor_audit_valid(value: Any) -> bool:
    return _m6b_factor_audit_valid(value, loaded=True)


def _m6b_lifecycle_valid(
    value: Any,
    *,
    online: bool,
    require_compiler_empty: bool | None = None,
) -> bool:
    required = (
        "return_code",
        "termination",
        "processes_gone",
        "peak_rss_bytes",
        "swap_bytes",
        "watchdog_rss_limit_bytes",
        "completion_rss_limit_bytes",
        "timeout_seconds",
    )
    if not isinstance(value, Mapping) or any(key not in value for key in required):
        return False
    if require_compiler_empty is None:
        require_compiler_empty = online
    compiler_ok = not require_compiler_empty or value.get("compiler_descendant_pids") == []
    limit = (
        M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
        if online
        else M6B_WATCHDOG_RSS_LIMIT_BYTES
    )
    return bool(
        value["return_code"] == 0
        and value["termination"] is None
        and value["processes_gone"] is True
        and type(value["peak_rss_bytes"]) is int
        and value["peak_rss_bytes"] < limit
        and value["swap_bytes"] == 0
        and value["watchdog_rss_limit_bytes"] == M6B_WATCHDOG_RSS_LIMIT_BYTES
        and value["completion_rss_limit_bytes"]
        == M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
        and _finite_number(value["timeout_seconds"])
        and float(value["timeout_seconds"]) > 0.0
        and compiler_ok
    )


def _m6b_screen_structure_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        str(item) for item in M6B_SCREEN_ITERATIONS
    }:
        return False
    return all(
        isinstance(value[key], Mapping)
        and _finite_number(value[key].get("true_relative_residual"))
        and float(value[key]["true_relative_residual"]) >= 0.0
        for key in value
    )


def _m6b_screen_valid(value: Any) -> bool:
    if not _m6b_screen_structure_valid(value):
        return False
    residuals = {
        key: float(value[key]["true_relative_residual"])
        for key in value
    }
    return bool(
        residuals["20"] <= M6B_SCREEN_RHO_LIMITS["20"]
        and residuals["100"] <= M6B_SCREEN_RHO_LIMITS["100"]
        and residuals["200"] <= M6B_SCREEN_RHO_LIMITS["200"]
        and residuals["150"] > 0.0
        and 1.0 - residuals["200"] / residuals["150"] >= M6B_IMPROVEMENT_LIMIT
    )


def _m6b_screen_metadata_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    samples = value.get("samples")
    return bool(
        value.get("schema") == "task037.extra.h2b.m6b.screen.v1"
        and value.get("rows") == M6B_GLOBAL_ROWS
        and value.get("ksp_type") == "fgmres"
        and value.get("pc_side") == "right"
        and value.get("norm_type") == "unpreconditioned"
        and value.get("restart_set") == 20
        and value.get("max_it") == 200
        and value.get("max_it_actual") == 200
        and value.get("iterations") == 200
        and value.get("rtol") == 0.0
        and value.get("atol") == 0.0
        and value.get("fixed_screen") is True
        and type(value.get("converged_reason")) is int
        and type(value.get("operator_apply_count")) is int
        and value.get("operator_apply_count") > 0
        and type(value.get("pc_apply_count")) is int
        and value.get("pc_apply_count") > 0
        and value.get("sample_action_count") == len(M6B_SCREEN_ITERATIONS)
        and isinstance(samples, Mapping)
        and _m6b_screen_structure_valid(samples)
    )


def _m6b_builder_summary_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    sample = value.get("sample_patch_action_closure")
    class_audit = value.get("class_block_audit")
    cache = value.get("cache")
    form = value.get("form")
    shared_kernel = value.get("shared_volume_kernel")
    return bool(
        isinstance(sample, Mapping)
        and set(sample) == {"0", "42", "83"}
        and all(
            _finite_number(sample[key])
            and 0.0 <= float(sample[key]) <= 1.0e-11
            for key in sample
        )
        and isinstance(class_audit, Mapping)
        and class_audit.get("class_count") == 24
        and class_audit.get("factor_count") == 24
        and class_audit.get("reconstruction_count") == 24
        and class_audit.get("fresh_B_beta_class_count") == 24
        and class_audit.get("fresh_B_beta_matrix_count") == 24
        and class_audit.get("operator_identity") == M6B_SHIFTED_OPERATOR
        and class_audit.get("numeric_matrix_source")
        == "fresh_transformed_B_beta_class_block"
        and class_audit.get("r2_numeric_store_used_for_blocks") is False
        and class_audit.get("global_matrix_materialized") is False
        and isinstance(cache, Mapping)
        and all(key in cache for key in ("stage", "before", "after", "unchanged"))
        and cache["stage"] == cache["before"] == cache["after"]
        and cache["unchanged"] is True
        and _m6b_shared_kernel_valid(shared_kernel, phase="builder")
        and _m6b_form_record_bound(
            form,
            shared_kernel,
            role="shifted_volume",
            beta=M6B_BETA,
            code_state="hit_no_new_decl_impl",
            shared_phase="stage",
        )
        and _m6b_material_tag_coverage_valid(
            value.get("material_tag_coverage"), owned_cells=M6B_GLOBAL_CELLS
        )
    )


def _m6b_pc_audit_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    materialization = value.get("materialization_identity")
    required_materialization = {
        "global_matrix",
        "global_constraint_matrix",
        "patch_matrices",
        "per_cell_factor",
        "static_condensation",
        "trace_slab",
        "schur",
        "slab_factor",
    }
    closure = value.get("partition_of_unity_closure_error")
    return bool(
        value.get("beta") == M6B_BETA
        and value.get("unique_factor_count") == M6B_FACTOR_COUNT
        and value.get("solve_count_per_apply") == M6B_FACTOR_COUNT
        and value.get("factor_reuse_count") == M6B_FACTOR_REUSE
        and value.get("factor_reuse_exercised") == M6B_FACTOR_REUSE
        and value.get("rhs_count") == M6B_GLOBAL_CELLS
        and value.get("factor_copy_count") == 0
        and value.get("per_cell_solution_retained") is False
        and value.get("fine_space") == "uncondensed_fullspace"
        and _finite_number(closure)
        and 0.0 <= float(closure) <= 1.0e-14
        and isinstance(materialization, Mapping)
        and set(materialization) == required_materialization
        and all(materialization[key] is False for key in required_materialization)
    )


def _m6b_phase_source_identity(
    summaries: Mapping[str, Any],
) -> dict[str, Any]:
    expected = ("stage", "builder", "online", "watchdog")
    if set(summaries) != set(expected):
        return {
            "pass": False,
            "source_commit_full_sha": None,
            "phase_names": list(expected),
            "all_tracked_source_clean": False,
        }
    commits: set[str] = set()
    clean = True
    for name in expected:
        summary = summaries[name]
        if not isinstance(summary, Mapping):
            clean = False
            continue
        start = summary.get("source_at_start")
        end = summary.get("source_at_end")
        if not isinstance(start, Mapping) or not isinstance(end, Mapping):
            clean = False
            continue
        if start.get("source_commit_full_sha") != end.get("source_commit_full_sha"):
            clean = False
        if start.get("tracked_source_dirty") is not False or end.get(
            "tracked_source_dirty"
        ) is not False:
            clean = False
        commit = start.get("source_commit_full_sha")
        if isinstance(commit, str):
            commits.add(commit)
        else:
            clean = False
    same = len(commits) == 1
    commit = next(iter(commits)) if same else None
    return {
        "pass": bool(same and clean),
        "source_commit_full_sha": commit,
        "phase_names": list(expected),
        "all_tracked_source_clean": bool(clean),
    }


def _m6b_check_payload(value: Any) -> dict[str, Any]:
    """Check a worker-shaped compact mapping without defaulting missing keys."""

    checks = {
        "schema": False,
        "scope": False,
        "p6_identity": False,
        "factor_audit": False,
        "builder_factor_audit": False,
        "screen": False,
        "stage_lifecycle": False,
        "online_lifecycle": False,
        "architecture": False,
        "source_pair": False,
        "runtime_identity": False,
        "cache_identity": False,
        "pc_repeat": False,
        "phase_source_identity": False,
        "pc_audit": False,
        "shared_volume_kernel": False,
        "material_tag_coverage": False,
    }
    problems: list[str] = []
    if not isinstance(value, Mapping):
        return {"pass": False, "checks": checks, "problems": ["raw_mapping"]}
    checks["schema"] = value.get("schema") == M6B_WORKER_SCHEMA
    checks["scope"] = value.get("scope") == _m6b_scope(phase="mpi1")
    checks["p6_identity"] = value.get("p6") == {
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
    }
    factor = value.get("factor_store")
    checks["factor_audit"] = _m6b_loaded_factor_audit_valid(factor)
    checks["builder_factor_audit"] = _m6b_builder_factor_audit_valid(
        value.get("builder_factor_audit")
    )
    screen = value.get("screen")
    screen_metadata = value.get("screen_metadata")
    checks["screen"] = bool(
        _m6b_screen_valid(screen)
        and _m6b_screen_metadata_valid(screen_metadata)
        and screen_metadata.get("samples") == screen
    ) if isinstance(screen_metadata, Mapping) else False
    stage_lifecycle = value.get("stage")
    online_lifecycle = value.get("online")
    checks["stage_lifecycle"] = bool(
        _m6b_lifecycle_valid(stage_lifecycle, online=False)
        and stage_lifecycle["timeout_seconds"] == M6B_STAGE_TIMEOUT_SECONDS
    ) if isinstance(stage_lifecycle, Mapping) else False
    checks["online_lifecycle"] = bool(
        _m6b_lifecycle_valid(online_lifecycle, online=True)
        and online_lifecycle["timeout_seconds"] == M6B_ONLINE_TIMEOUT_SECONDS
    ) if isinstance(online_lifecycle, Mapping) else False
    architecture = value.get("architecture")
    required_architecture = (
        "fine_space",
        "global_matrix",
        "augmented_matrix",
        "static_condensation",
        "trace_slab_pc",
        "explicit_C_materialized_count",
        "explicit_D_materialized_count",
        "dtn",
        "pde",
    )
    checks["architecture"] = bool(
        isinstance(architecture, Mapping)
        and set(architecture) == set(required_architecture)
        and all(key in architecture for key in required_architecture)
        and architecture["fine_space"] == "uncondensed_fullspace"
        and all(
            architecture[key] is False
            for key in (
                "global_matrix",
                "augmented_matrix",
                "static_condensation",
                "trace_slab_pc",
                "pde",
            )
        )
        and architecture["dtn"] is True
        and architecture["explicit_C_materialized_count"] == 0
        and architecture["explicit_D_materialized_count"] == 0
    )
    start = value.get("source_at_start")
    end = value.get("source_at_end")
    checks["source_pair"] = bool(
        isinstance(start, Mapping)
        and isinstance(end, Mapping)
        and start.get("source_commit_full_sha")
        and start.get("source_commit_full_sha") == end.get("source_commit_full_sha")
        and start.get("tracked_source_dirty") is False
        and end.get("tracked_source_dirty") is False
    )
    phase_identity = value.get("phase_source_identity")
    checks["phase_source_identity"] = bool(
        isinstance(phase_identity, Mapping)
        and phase_identity.get("pass") is True
        and phase_identity.get("phase_names")
        == ["stage", "builder", "online", "watchdog"]
        and phase_identity.get("all_tracked_source_clean") is True
        and isinstance(phase_identity.get("source_commit_full_sha"), str)
        and isinstance(start, Mapping)
        and isinstance(end, Mapping)
        and phase_identity.get("source_commit_full_sha") == start.get(
            "source_commit_full_sha"
        )
        and phase_identity.get("source_commit_full_sha") == end.get(
            "source_commit_full_sha"
        )
    )
    try:
        import benchmarks.run_task037_extra_h2b as h2b

        runtime = value["runtime_identity"]
        checks["runtime_identity"] = bool(
            h2b._runtime_valid(runtime)
            and isinstance(runtime.get("compiler"), Mapping)
            and runtime.get("mpi_size") == 1
        )
    except (ImportError, KeyError, TypeError, AttributeError):
        checks["runtime_identity"] = False
    cache = value.get("cache")
    checks["cache_identity"] = bool(
        isinstance(cache, Mapping)
        and all(
            key in cache for key in ("stage", "before", "after", "final", "unchanged")
        )
        and cache["stage"] == cache["before"] == cache["after"] == cache["final"]
        and cache["unchanged"] is True
    )
    repeat = value.get("pc_repeat")
    required_probe_hashes = {
        "rhs_sha256",
        "correction0_sha256",
        "action_sha256",
        "correction_sha256",
        "residual_sha256",
    }
    checks["pc_repeat"] = bool(
        isinstance(repeat, Mapping)
        and repeat.get("identical") is True
        and isinstance(repeat.get("first"), Mapping)
        and isinstance(repeat.get("second"), Mapping)
        and repeat["first"].get("hashes") == repeat["second"].get("hashes")
        and set(repeat["first"].get("hashes", {})) == required_probe_hashes
        and all(
            _finite_number(repeat[side].get("wall_seconds"))
            and repeat[side].get("finite") is True
            and repeat[side].get("exact_shifted_action_count") == 1
            and _finite_number(repeat[side].get("partition_of_unity_closure_error"))
            and float(repeat[side]["partition_of_unity_closure_error"]) >= 0.0
            and float(repeat[side]["partition_of_unity_closure_error"]) <= 1.0e-14
            for side in ("first", "second")
        )
    )
    online_measurement = value.get("online_measurement")
    shared_kernel = (
        online_measurement.get("shared_volume_kernel")
        if isinstance(online_measurement, Mapping)
        else None
    )
    online_form = (
        online_measurement.get("form")
        if isinstance(online_measurement, Mapping)
        else None
    )
    checks["shared_volume_kernel"] = bool(
        _m6b_shared_kernel_valid(shared_kernel, phase="mpi1")
        and isinstance(online_form, Mapping)
        and _m6b_form_records_bound(
            online_form.get("outer_volume"),
            online_form.get("shifted_volume"),
            shared_kernel,
            phase="mpi1",
        )
    )
    checks["material_tag_coverage"] = _m6b_material_tag_coverage_valid(
        online_measurement.get("material_tag_coverage")
        if isinstance(online_measurement, Mapping)
        else None,
        owned_cells=M6B_GLOBAL_CELLS,
    )
    checks["pc_audit"] = bool(
        isinstance(online_measurement, Mapping)
        and _m6b_pc_audit_valid(online_measurement.get("pc_audit"))
    )
    problems.extend(name for name, passed in checks.items() if not passed)
    return {
        "pass": not problems,
        "checks": checks,
        "problems": problems,
        "scope": _m6b_scope(phase="mpi1"),
        "predicted_live_set": _predicted_live_set(),
    }


def _m6b_emit(stream: Any, phase: str, event: str, started: float, **extra: Any) -> None:
    expected = {
        "stage": M6B_STAGE_EVENTS,
        "builder": M6B_BUILDER_EVENTS,
        "mpi1": M6B_ONLINE_EVENTS,
    }[phase]
    if event not in expected:
        raise ValueError(f"M6B unknown progress event: {event}")
    payload = {
        "schema": f"{M6B_SCHEMA}.progress.v1",
        "phase": phase,
        "event": event,
        "elapsed_wall_seconds": float(__import__("time").perf_counter() - started),
        **extra,
    }
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()
    print(json.dumps(payload, sort_keys=True), flush=True)


def _m6b_w1_cache_deltas(
    target_before: Mapping[str, Any],
    target_after_forward: Mapping[str, Any],
    target_after_adjoint: Mapping[str, Any],
    target_after_surface: Mapping[str, Any],
    target_final: Mapping[str, Any],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Classify W1 target-cache content changes between fixed lifecycle points."""

    def delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
        before_by_path = {
            item["path"]: {
                "path": item["path"],
                "bytes": int(item["bytes"]),
                "sha256": item["sha256"],
            }
            for item in before["entries"]
        }
        after_by_path = {
            item["path"]: {
                "path": item["path"],
                "bytes": int(item["bytes"]),
                "sha256": item["sha256"],
            }
            for item in after["entries"]
        }
        added = [after_by_path[path] for path in sorted(after_by_path.keys() - before_by_path.keys())]
        removed = [before_by_path[path] for path in sorted(before_by_path.keys() - after_by_path.keys())]
        changed = [
            {
                "path": path,
                "before": before_by_path[path],
                "after": after_by_path[path],
            }
            for path in sorted(before_by_path.keys() & after_by_path.keys())
            if before_by_path[path] != after_by_path[path]
        ]
        return {"added": added, "removed": removed, "changed": changed}

    return {
        "forward_delta": delta(target_before, target_after_forward),
        "adjoint_staging_delta": delta(
            target_after_forward, target_after_adjoint
        ),
        "surface_delta": delta(target_after_adjoint, target_after_surface),
        "final_delta": delta(target_after_surface, target_final),
    }


def _run_m6b_w1_builder(run_dir: Path, jit_cache_source: Path) -> int:
    """Build the W1 sparse ``Z``/``A Z`` carrier without running a screen."""

    import gc
    import shutil
    import time
    from types import SimpleNamespace

    import numpy as np
    from mpi4py import MPI
    import ufl

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from benchmarks.run_workstation_iterative import _fixed_floquet_hat_basis
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        build_m6b_outer_mat,
        build_m6b_volume_form,
    )
    from src.solvers.hcurl_m6b_sparse_range import (
        M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
        M6B_W1_W0_BASIS_MANIFEST_SHA256,
        M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA,
        M6B_W1_W0_ORACLE_OUTPUT_SHA256,
        M6B_W1_W0_RESIDUAL_SOURCE_SHA,
        SparseM6BRangeCarrier,
        basis_manifest_from_vectors,
        load_sparse_m6b_range_carrier,
        validate_w0_authority,
    )
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    run_dir = Path(run_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists():
        raise FileExistsError(f"W1 builder refuses existing directory: {run_dir}")
    if not jit_cache_source.is_dir():
        raise FileNotFoundError(f"W1 JIT cache source is missing: {jit_cache_source}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("W1 sparse range builder is fixed to MPI1")
    run_dir.mkdir(parents=True)
    cache_dir = run_dir / "jit_cache"
    shutil.copytree(jit_cache_source, cache_dir)
    started = time.perf_counter()
    progress_path = run_dir / "w1_builder_progress.jsonl"

    def emit(event: str, **extra: Any) -> None:
        payload = {
            "schema": f"{M6B_W1_SCHEMA}.progress.v1",
            "phase": "w1_builder",
            "event": event,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
            **extra,
        }
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
        print(json.dumps(payload, sort_keys=True), flush=True)

    def cache_record(path: Path) -> dict[str, Any]:
        entries = h2b._cache_snapshot(path)
        content_entries = [
            {
                "path": item["path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in entries
        ]
        inventory_sha = hashlib.sha256(
            h2b._canonical_json({"entries": content_entries})
        ).hexdigest()
        return {"entries": content_entries, "inventory_sha256": inventory_sha}

    emit("cache_ready", source=str(jit_cache_source))
    source_cache_before = cache_record(jit_cache_source)
    target_cache_before = cache_record(cache_dir)
    if target_cache_before["inventory_sha256"] != source_cache_before["inventory_sha256"]:
        raise ValueError("W1 copied JIT cache differs from source")
    cfg = mesh_data = function_space = floquet = None
    physical_action = adjoint_physical_action = dtn_action = outer_mat = outer_context = None
    surface_assemblers = None
    volume_ufl = adjoint_ufl = epsilon = abs_epsilon = beta = None
    template = None
    try:
        cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
            run_dir, mesh_name="m6b_w1_mesh"
        )
        physical_ufl, epsilon, abs_epsilon, beta, tag_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=0.0
        )
        volume_ufl = physical_ufl
        physical_action = build_task037_extra_h1r2_mpc_action(
            physical_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        target_cache_after_forward = cache_record(cache_dir)
        source_cache_after_forward = cache_record(jit_cache_source)
        if (
            target_cache_after_forward["inventory_sha256"]
            != target_cache_before["inventory_sha256"]
            or source_cache_after_forward["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("W1 physical forward action changed the JIT cache")
        adjoint_ufl = ufl.adjoint(physical_ufl)
        adjoint_physical_action = build_task037_extra_h1r2_mpc_action(
            adjoint_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        target_cache_after_adjoint = cache_record(cache_dir)
        source_cache_after_adjoint = cache_record(jit_cache_source)
        if source_cache_after_adjoint["inventory_sha256"] != source_cache_before[
            "inventory_sha256"
        ]:
            raise ValueError("W1 adjoint action changed the source JIT cache")
        surface_assemblers = m6a._surface_assemblers(
            function_space, mesh_data, cfg, modes, cache_dir
        )
        target_cache_after_surface = cache_record(cache_dir)
        source_cache_after_surface = cache_record(jit_cache_source)
        if (
            target_cache_after_surface["inventory_sha256"]
            != target_cache_after_adjoint["inventory_sha256"]
            or source_cache_after_surface["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("W1 surface forms changed the frozen JIT cache")
        emit(
            "forms_ready",
            cache_inventory_sha256=target_cache_after_surface["inventory_sha256"],
            adjoint_form_staged=True,
        )
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes,
            surface_assemblers,
            floquet.mpc,
            cfg,
            expected_mode_count=80,
        )
        dtn_action = build_fullspace_dtn_action(carrier, comm=MPI.COMM_WORLD)
        outer_mat, outer_context = build_m6b_outer_mat(
            physical_action,
            dtn_action,
            owned_rows=M6B_GLOBAL_ROWS,
            global_rows=M6B_GLOBAL_ROWS,
            comm=MPI.COMM_WORLD,
            volume_hermitian_action=adjoint_physical_action,
        )
        template = outer_mat.createVecRight()
        ownership = tuple(int(value) for value in template.getOwnershipRange())
        local_rows = ownership[1] - ownership[0]

        def apply_local(values: np.ndarray, *, hermitian: bool = False) -> np.ndarray:
            values = np.asarray(values, dtype=np.complex128)
            if (
                values.ndim != 1
                or values.size != local_rows
                or not np.all(np.isfinite(values))
            ):
                raise ValueError("W1 outer probe has an invalid owned layout")
            source = template.duplicate()
            result = template.duplicate()
            try:
                np.copyto(source.getArray(), values)
                if hermitian:
                    outer_context.apply_hermitian(source, result)
                else:
                    outer_mat.mult(source, result)
                return np.array(
                    result.getArray(readonly=True),
                    dtype=np.complex128,
                    copy=True,
                )
            finally:
                result.destroy()
                source.destroy()

        probe_index = np.arange(local_rows, dtype=np.float64)
        x_values = 0.125 + 1.0e-6 * probe_index + 1j * (
            0.25 - 2.0e-6 * probe_index
        )
        y_values = -0.375 + 1.5e-6 * probe_index + 1j * (
            0.5 - 1.0e-6 * probe_index
        )
        x_before = x_values.copy()
        y_before = y_values.copy()
        forward_values = apply_local(x_values)
        adjoint_values = apply_local(y_values, hermitian=True)
        adjoint_repeat = apply_local(y_values, hermitian=True)
        lhs = np.vdot(forward_values, y_values)
        rhs = np.vdot(x_values, adjoint_values)
        inner_product_defect = float(
            abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny)
        )
        adjoint_finite = bool(
            np.all(np.isfinite(forward_values))
            and np.all(np.isfinite(adjoint_values))
            and np.all(np.isfinite(adjoint_repeat))
        )
        adjoint_repeat_equal = bool(np.array_equal(adjoint_values, adjoint_repeat))
        probe_sources_unchanged = bool(
            np.array_equal(x_values, x_before)
            and np.array_equal(y_values, y_before)
        )
        adjoint_identity = {
            "schema": "task037.extra.m6b.w1.adjoint-identity.v1",
            "relative_inner_product_defect": inner_product_defect,
            "limit": 1.0e-11,
            "finite": adjoint_finite,
            "repeat_equal": adjoint_repeat_equal,
            "source_unchanged": probe_sources_unchanged,
            "forward_action_count": 1,
            "adjoint_action_count": 1,
            "adjoint_repeat_action_count": 1,
            "adjoint_total_action_count": 2,
            "outer_forward_apply_count": int(outer_context.apply_count),
            "outer_adjoint_apply_count": int(
                outer_context.audit["hermitian_apply_count"]
            ),
            "volume_forward_action_count": int(physical_action.audit["apply_count"]),
            "volume_adjoint_action_count": int(
                adjoint_physical_action.audit["apply_count"]
            ),
            "lhs_abs": float(abs(lhs)),
            "rhs_abs": float(abs(rhs)),
            "lhs_real": float(lhs.real),
            "lhs_imag": float(lhs.imag),
            "rhs_real": float(rhs.real),
            "rhs_imag": float(rhs.imag),
            "repeat_max_abs_diff": float(
                np.max(np.abs(adjoint_values - adjoint_repeat))
            ),
        }
        if not (
            adjoint_finite
            and adjoint_repeat_equal
            and probe_sources_unchanged
            and inner_product_defect <= adjoint_identity["limit"]
        ):
            raise ValueError("W1 full-space adjoint identity Gate failed")
        emit(
            "adjoint_identity_ready",
            relative_inner_product_defect=inner_product_defect,
            forward_action_count=1,
            adjoint_action_count=1,
            repeat_action_count=1,
        )
        del (
            probe_index,
            x_values,
            y_values,
            x_before,
            y_before,
            forward_values,
            adjoint_values,
            adjoint_repeat,
        )

        def basis_progress(completed: int, total: int) -> None:
            if completed % 5 == 0 or completed == total:
                emit("basis_progress", completed=completed, total=total)

        basis = tuple(
            _fixed_floquet_hat_basis(
                SimpleNamespace(cfg=cfg, V=function_space, floquet_data=floquet),
                outer_mat,
                coarse_slabs=24,
                progress=basis_progress,
            )
        )
        if len(basis) != 75:
            raise ValueError("W1 fixed basis rank is not 75")
        basis_manifest = basis_manifest_from_vectors(basis)
        basis_manifest_sha256 = hashlib.sha256(
            json.dumps(
                basis_manifest,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if basis_manifest_sha256 != M6B_W1_W0_BASIS_MANIFEST_SHA256:
            raise ValueError("W1 basis manifest differs from frozen W0 authority")
        emit("basis_ready", completed=75, total=75, basis_manifest_sha256=basis_manifest_sha256)

        action_count = [0]

        def apply_column(vector: Any) -> np.ndarray:
            local = np.zeros(local_rows, dtype=np.complex128)
            rows = np.asarray(vector.indices, dtype=np.int64)
            start, end = ownership
            if rows.size and (rows.min() < start or rows.max() >= end):
                raise ValueError("W1 fixed basis row is outside ownership")
            local[rows - start] = np.asarray(vector.values, dtype=np.complex128)
            represented = apply_local(local)
            action_count[0] += 1
            if action_count[0] % 5 == 0 or action_count[0] == 75:
                emit("az_progress", completed=action_count[0], total=75)
            return represented

        def apply_hermitian_column(values: np.ndarray) -> np.ndarray:
            return apply_local(values, hermitian=True)

        identity = {
            "source_sha": h2b._light_source()["source_commit_full_sha"],
            "operator_identity": "A=Kcurl-k0^2*M_epsilon+A_DtN",
            "basis_manifest_sha256": basis_manifest_sha256,
            "basis_manifest": basis_manifest,
            "basis_helper": "benchmarks.run_workstation_iterative._fixed_floquet_hat_basis",
            "coarse_slabs": 24,
            "w0_az_column_sha256_aggregate": M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
            "w0_oracle_output_sha256": M6B_W1_W0_ORACLE_OUTPUT_SHA256,
            "w0_residual_source_sha": M6B_W1_W0_RESIDUAL_SOURCE_SHA,
            "w0_oracle_execution_source_sha": M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA,
            "fine_space": "uncondensed_fullspace",
            "global_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
        }
        carrier = SparseM6BRangeCarrier.from_action(
            basis,
            apply_column,
            hermitian_action=apply_hermitian_column,
            global_rows=M6B_GLOBAL_ROWS,
            ownership_range=ownership,
            comm=MPI.COMM_WORLD,
            identity=identity,
        )
        validate_w0_authority(identity, carrier.audit["az_column_sha256_aggregate"])
        emit(
            "az_ready",
            completed=75,
            total=75,
            az_column_sha256_aggregate=carrier.audit["az_column_sha256_aggregate"],
        )
        manifest_path = carrier.save(run_dir / "sparse_range_store")
        del carrier
        gc.collect()
        loaded = load_sparse_m6b_range_carrier(
            manifest_path,
            hermitian_action=apply_hermitian_column,
        )
        audit = loaded.audit
        final_cache = cache_record(cache_dir)
        source_cache_after = cache_record(jit_cache_source)
        if (
            final_cache["inventory_sha256"]
            != target_cache_after_surface["inventory_sha256"]
            or source_cache_after["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("W1 JIT cache changed after form construction")
        cache_deltas = _m6b_w1_cache_deltas(
            target_cache_before,
            target_cache_after_forward,
            target_cache_after_adjoint,
            target_cache_after_surface,
            final_cache,
        )
        emit("store_ready", manifest=str(manifest_path))
        predicted = int(
            M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES
            + audit["retained_total_bytes"]
            + audit["bounded_work_bytes"]
            + int(adjoint_physical_action.audit["retained_numeric_payload_global_max_bytes"])
            + int(adjoint_physical_action.audit["per_apply_bounded_temporary_bytes"])
        )
        if predicted > M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES:
            raise ValueError("W1 derived live-set prediction exceeds fixed limit")
        full_vector_bytes = int(local_rows * np.dtype(np.complex128).itemsize)
        dtn_work_bytes = full_vector_bytes
        carrier_bounded_work_bytes = int(audit["bounded_work_bytes"])
        adjoint_packed_work_bytes = int(
            adjoint_physical_action.audit["per_apply_bounded_temporary_bytes"]
        )
        phase_pack_incremental = int(
            2 * full_vector_bytes + adjoint_packed_work_bytes
        )
        phase_copy_incremental = int(3 * full_vector_bytes)
        phase_post_incremental = carrier_bounded_work_bytes
        worst_phase_incremental = max(
            phase_pack_incremental,
            phase_copy_incremental,
            phase_post_incremental,
        )
        predicted_incremental_work_bytes = int(
            carrier_bounded_work_bytes + adjoint_packed_work_bytes
        )
        incremental_work_excess_over_worst_phase_bytes = int(
            predicted_incremental_work_bytes - worst_phase_incremental
        )
        reserve_remaining_after_dtn_bytes = int(
            M6B_FIXED_RUNTIME_RESERVE_BYTES - dtn_work_bytes
        )
        lifecycle_basis = {
            "basis": "derived_not_measured",
            "full_owned_vector_bytes": full_vector_bytes,
            "callback_petsc_source_target_bytes": int(2 * full_vector_bytes),
            "callback_return_ndarray_copy_bytes": full_vector_bytes,
            "callback_peak_transient_bytes": int(3 * full_vector_bytes),
            "post_callback_adjoint_ndarray_and_correction_bytes": int(
                2 * full_vector_bytes
            ),
            "dtn_fe_target_work_bytes": dtn_work_bytes,
            "dtn_fe_target_work_coverage": "fixed_runtime_reserve_bytes",
            "dtn_fe_target_work_covered": (
                dtn_work_bytes <= M6B_FIXED_RUNTIME_RESERVE_BYTES
            ),
            "reserve_remaining_after_dtn_bytes": reserve_remaining_after_dtn_bytes,
            "carrier_bounded_work_bytes": carrier_bounded_work_bytes,
            "adjoint_packed_work_bytes": adjoint_packed_work_bytes,
            "phase_pack_incremental": phase_pack_incremental,
            "phase_copy_incremental": phase_copy_incremental,
            "phase_post_incremental": phase_post_incremental,
            "worst_phase_incremental": worst_phase_incremental,
            "predicted_incremental_work_bytes": predicted_incremental_work_bytes,
            "incremental_work_excess_over_worst_phase_bytes": (
                incremental_work_excess_over_worst_phase_bytes
            ),
            "incremental_formula_is_conservative": True,
            "dtn_not_in_incremental_formula": True,
            "worst_overlap_formula": (
                "worst_phase_incremental=max(phase_pack_incremental,"
                "phase_copy_incremental,phase_post_incremental); "
                "predicted_incremental_work_bytes=phase_post_incremental+"
                "adjoint_packed_work_bytes; dtn_fe_target_work_bytes is "
                "covered by base fixed_runtime_reserve_bytes and is not added "
                "to the incremental formula"
            ),
            "post_callback_vectors_not_simultaneous_with_callback_vectors": True,
        }
        summary = {
            "schema": M6B_W1_SCHEMA,
            "status": "measurement_complete",
            "formal_pass": False,
            "pde_pass": False,
            "qualification": "not_run",
            "source": h2b._light_source(),
            "scope": {
                "global_rows": M6B_GLOBAL_ROWS,
                "columns": 75,
                "operator_identity": identity["operator_identity"],
                "fine_space": identity["fine_space"],
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "ordinary_default": False,
            },
            "basis_manifest_sha256": basis_manifest_sha256,
            "store_manifest": str(manifest_path),
            "carrier_audit": audit,
            "jit_cache": {
                "source": str(jit_cache_source),
                "target": str(cache_dir),
                "source_before": source_cache_before,
                "target_before": target_cache_before,
                "target_after_forward": target_cache_after_forward,
                "target_after_adjoint": target_cache_after_adjoint,
                "target_after_surface": target_cache_after_surface,
                "target_final": final_cache,
                "source_after_forward": source_cache_after_forward,
                "source_after_adjoint": source_cache_after_adjoint,
                "source_after_surface": source_cache_after_surface,
                "source_final": source_cache_after,
                "forward_cache_reused": (
                    target_cache_after_forward == target_cache_before
                ),
                "adjoint_staging_changed_cache": (
                    target_cache_after_adjoint != target_cache_after_forward
                ),
                "surface_cache_reused_after_adjoint": (
                    target_cache_after_surface == target_cache_after_adjoint
                ),
                "target_frozen_unchanged": (
                    final_cache == target_cache_after_surface
                ),
                "source_unchanged": all(
                    record == source_cache_before
                    for record in (
                        source_cache_after_forward,
                        source_cache_after_adjoint,
                        source_cache_after_surface,
                        source_cache_after,
                    )
                ),
                "forward_delta": cache_deltas["forward_delta"],
                "adjoint_staging_delta": cache_deltas["adjoint_staging_delta"],
                "surface_delta": cache_deltas["surface_delta"],
                "final_delta": cache_deltas["final_delta"],
                "inventory_sha256": final_cache["inventory_sha256"],
            },
            "adjoint_identity": adjoint_identity,
            "memory_lifecycle": lifecycle_basis,
            "predicted_live_set": {
                "base_bytes": M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES,
                "coarse_retained_bytes": audit["retained_total_bytes"],
                "coarse_bounded_work_bytes": audit["bounded_work_bytes"],
                "adjoint_volume_action_payload_bytes": int(
                    adjoint_physical_action.audit["retained_numeric_payload_global_max_bytes"]
                ),
                "adjoint_volume_action_work_bytes": int(
                    adjoint_physical_action.audit["per_apply_bounded_temporary_bytes"]
                ),
                "adjoint_identity_forward_count": 1,
                "adjoint_identity_adjoint_count": 2,
                "predicted_bytes": predicted,
                "limit_bytes": M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES,
                "gate": True,
                "is_measurement": False,
            },
            "builder_peak_limit_bytes": M6B_W1_BUILDER_RSS_LIMIT_BYTES,
            "swap_limit_bytes": 0,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
        emit("summary_ready", qualification="not_run")
        _write_json(run_dir / "w1_builder_summary.json", _attach_evidence(summary))
        return 0
    finally:
        if template is not None:
            template.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if dtn_action is not None:
            dtn_action.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if adjoint_physical_action is not None:
            adjoint_physical_action.destroy()
        if surface_assemblers is not None:
            for assembler in surface_assemblers.values():
                destroy = getattr(assembler, "destroy", None)
                if destroy is not None:
                    destroy()
        del volume_ufl, adjoint_ufl, epsilon, abs_epsilon, beta
        gc.collect()


def _m6b_form_record(
    h2b: Any,
    action: Any,
    cache_dir: Path,
    cfg: Any,
    function_space: Any,
    role: str,
    beta: float,
) -> dict[str, Any]:
    record = h2b._form_record(
        action._action_form,
        action._action_ufl,
        cache_dir,
        cfg,
        function_space,
        role,
    )
    record.pop("proxy_identity", None)
    record["role"] = role
    record["beta"] = float(beta)
    record["beta_runtime_parameter"] = "fem.Constant"
    record["operator_identity"] = M6B_SHARED_VOLUME_OPERATOR
    record["representation"] = M6B_SHARED_VOLUME_REPRESENTATION
    return record


def _m6b_fixed_physics_identity(cfg: Any) -> dict[str, Any]:
    identity = {
        "use_pml": bool(cfg.use_pml),
        "pml_top_thickness": float(cfg.pml_top_thickness),
        "pml_bottom_thickness": float(cfg.pml_bottom_thickness),
        "divergence_penalty": float(cfg.divergence_penalty),
        "material_representation": "DG0_epsilon_and_abs_epsilon",
    }
    if (
        identity["use_pml"]
        or identity["pml_top_thickness"] != 0.0
        or identity["pml_bottom_thickness"] != 0.0
        or identity["divergence_penalty"] != 0.0
    ):
        raise ValueError("M6B shared volume physics is not the fixed no-PML contract")
    return identity


def _m6b_shared_kernel_identity(
    outer: Mapping[str, Any],
    shifted: Mapping[str, Any],
    cfg: Any,
    *,
    phase: str,
) -> dict[str, Any]:
    fixed_physics = _m6b_fixed_physics_identity(cfg)
    required = (
        "beta",
        "beta_runtime_parameter",
        "operator_identity",
        "representation",
        "module_name",
        "ufl_signature",
        "ufcx_signature",
        "code_state",
    )
    if not isinstance(outer, Mapping) or not isinstance(shifted, Mapping):
        raise ValueError("M6B shared volume form records are incomplete")
    if any(key not in outer or key not in shifted for key in required):
        raise ValueError("M6B shared volume form identity is incomplete")
    if (
        outer["beta"] != 0.0
        or shifted["beta"] != M6B_BETA
        or outer["beta_runtime_parameter"] != "fem.Constant"
        or shifted["beta_runtime_parameter"] != "fem.Constant"
        or outer["operator_identity"] != M6B_SHARED_VOLUME_OPERATOR
        or shifted["operator_identity"] != M6B_SHARED_VOLUME_OPERATOR
        or outer["representation"] != M6B_SHARED_VOLUME_REPRESENTATION
        or shifted["representation"] != M6B_SHARED_VOLUME_REPRESENTATION
        or outer["module_name"] != shifted["module_name"]
        or outer["ufl_signature"] != shifted["ufl_signature"]
        or outer["ufcx_signature"] != shifted["ufcx_signature"]
    ):
        raise ValueError("M6B physical/shifted shared kernel identity changed")
    return {
        "schema": M6B_SHARED_VOLUME_SCHEMA,
        "phase": str(phase),
        "operator_identity": M6B_SHARED_VOLUME_OPERATOR,
        "representation": M6B_SHARED_VOLUME_REPRESENTATION,
        "fixed_physics": fixed_physics,
        "beta_runtime_parameter": "fem.Constant",
        "outer_beta": 0.0,
        "shifted_beta": M6B_BETA,
        "module_name": outer["module_name"],
        "ufl_signature": outer["ufl_signature"],
        "ufcx_signature": outer["ufcx_signature"],
        "outer_code_state": outer["code_state"],
        "shifted_code_state": shifted["code_state"],
        "same_module": True,
        "same_ufl_signature": True,
        "same_ufcx_signature": True,
    }


def _m6b_shared_kernel_valid(value: Any, *, phase: str) -> bool:
    required = {
        "schema",
        "phase",
        "operator_identity",
        "representation",
        "fixed_physics",
        "beta_runtime_parameter",
        "outer_beta",
        "shifted_beta",
        "module_name",
        "ufl_signature",
        "ufcx_signature",
        "outer_code_state",
        "shifted_code_state",
        "same_module",
        "same_ufl_signature",
        "same_ufcx_signature",
    }
    if phase not in {"stage", "builder", "mpi1"}:
        return False
    if not isinstance(value, Mapping) or set(value) != required:
        return False
    physics = value["fixed_physics"]
    expected_outer_state = "cold_decl_impl_generated"
    expected_shifted_state = "hit_no_new_decl_impl"
    if phase == "mpi1":
        expected_outer_state = expected_shifted_state
    return bool(
        value["schema"] == M6B_SHARED_VOLUME_SCHEMA
        and value["phase"] == ("stage" if phase == "builder" else phase)
        and value["operator_identity"] == M6B_SHARED_VOLUME_OPERATOR
        and value["representation"] == M6B_SHARED_VOLUME_REPRESENTATION
        and isinstance(physics, Mapping)
        and set(physics)
        == {
            "use_pml",
            "pml_top_thickness",
            "pml_bottom_thickness",
            "divergence_penalty",
            "material_representation",
        }
        and physics["use_pml"] is False
        and physics["pml_top_thickness"] == 0.0
        and physics["pml_bottom_thickness"] == 0.0
        and physics["divergence_penalty"] == 0.0
        and physics["material_representation"] == "DG0_epsilon_and_abs_epsilon"
        and value["beta_runtime_parameter"] == "fem.Constant"
        and value["outer_beta"] == 0.0
        and value["shifted_beta"] == M6B_BETA
        and isinstance(value["module_name"], str)
        and value["module_name"].startswith("libffcx_forms_")
        and isinstance(value["ufl_signature"], str)
        and bool(value["ufl_signature"])
        and isinstance(value["ufcx_signature"], str)
        and bool(value["ufcx_signature"])
        and value["outer_code_state"] == expected_outer_state
        and value["shifted_code_state"] == expected_shifted_state
        and value["same_module"] is True
        and value["same_ufl_signature"] is True
        and value["same_ufcx_signature"] is True
    )


def _m6b_form_record_bound(
    record: Any,
    shared: Any,
    *,
    role: str,
    beta: float,
    code_state: str,
    shared_phase: str = "stage",
) -> bool:
    if not _m6b_shared_kernel_valid(shared, phase=shared_phase):
        return False
    if not isinstance(record, Mapping):
        return False
    required = {
        "role",
        "beta",
        "beta_runtime_parameter",
        "operator_identity",
        "representation",
        "module_name",
        "ufl_signature",
        "ufcx_signature",
        "code_state",
    }
    if not required.issubset(record):
        return False
    return bool(
        record["role"] == role
        and record["beta"] == beta
        and record["beta_runtime_parameter"] == "fem.Constant"
        and record["operator_identity"] == shared["operator_identity"]
        and record["representation"] == shared["representation"]
        and record["module_name"] == shared["module_name"]
        and record["ufl_signature"] == shared["ufl_signature"]
        and record["ufcx_signature"] == shared["ufcx_signature"]
        and record["code_state"] == code_state
    )


def _m6b_form_records_bound(
    outer: Any,
    shifted: Any,
    shared: Any,
    *,
    phase: str,
) -> bool:
    if phase not in {"stage", "mpi1"}:
        return False
    outer_state = "cold_decl_impl_generated" if phase == "stage" else "hit_no_new_decl_impl"
    return bool(
        _m6b_form_record_bound(
            outer,
            shared,
            role="outer_volume",
            beta=0.0,
            code_state=outer_state,
            shared_phase=phase,
        )
        and _m6b_form_record_bound(
            shifted,
            shared,
            role="shifted_volume",
            beta=M6B_BETA,
            code_state="hit_no_new_decl_impl",
            shared_phase=phase,
        )
    )


def _m6b_material_tag_coverage_valid(value: Any, *, owned_cells: int) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value) == {
            "owned_cell_count",
            "allowed_tag_values",
            "tag_counts",
            "complete",
        }
        and value["owned_cell_count"] == owned_cells
        and value["allowed_tag_values"] == {"air": 1, "substrate": 2, "grating": 3}
        and isinstance(value["tag_counts"], Mapping)
        and set(value["tag_counts"]) == {"air", "substrate", "grating"}
        and all(
            type(value["tag_counts"][key]) is int
            and value["tag_counts"][key] >= 0
            for key in value["tag_counts"]
        )
        and sum(value["tag_counts"].values()) == owned_cells
        and value["complete"] is True
    )


def _m6b_runtime_identity(
    h2b: Any, h2a: Any, comm: Any, *, compiler_probe: bool, compiler: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    import dolfinx
    import mpi4py
    import petsc4py
    import slepc4py

    identity = dict(
        h2b._runtime_identity(
            h2a,
            compiler_probe=compiler_probe,
            compiler=compiler,
        )
    )
    identity.update(
        {
            "mpi_size": int(comm.size),
            "linux_abi": os.name == "posix",
            "package_paths": {
                "petsc4py": str(petsc4py.__file__),
                "slepc4py": str(slepc4py.__file__),
                "dolfinx": str(dolfinx.__file__),
                "mpi4py": str(mpi4py.__file__),
            },
        }
    )
    return identity


def _m6b_p6_identity(mesh_data: Any, function_space: Any, floquet: Any) -> dict[str, int]:
    index_map = function_space.dofmap.index_map
    return {
        "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
        "local_cells": int(mesh_data.mesh.topology.index_map(3).size_local),
        "local_nloc": int(function_space.element.space_dimension),
        "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
        "constraint_count": int(floquet.num_constraints),
    }


def _m6b_progress_valid(path: Path, phase: str, expected: Sequence[str]) -> bool:
    observed: list[str] = []
    elapsed = 0.0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            value = item.get("elapsed_wall_seconds") if isinstance(item, Mapping) else None
            if (
                not isinstance(item, Mapping)
                or item.get("schema") != f"{M6B_SCHEMA}.progress.v1"
                or item.get("phase") != phase
                or item.get("event") not in expected
                or item["event"] in observed
                or type(value) not in (int, float)
                or not math.isfinite(float(value))
                or float(value) < elapsed
            ):
                return False
            observed.append(str(item["event"]))
            elapsed = float(value)
        return tuple(observed) == tuple(expected)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _m6b_expected_p6(identity: Mapping[str, Any]) -> bool:
    return dict(identity) == {
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
    }


def _run_m6b_stage_worker(run_dir: Path) -> int:
    """Compile the exact online forms into one isolated cache and exit."""

    import gc
    import time

    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from dolfinx import fem
    from src.solvers.dtn_port_3d import _incident_top_traction_form
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import build_m6b_volume_form

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6B stage is fixed to MPI1")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    progress_path = run_dir / "m6b_stage_progress.jsonl"
    summary_path = run_dir / "m6b_stage_summary.json"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    forms: dict[str, Any] | None = None
    cache_inventory: list[dict[str, Any]] | None = None
    try:
        with progress_path.open("w", encoding="utf-8") as markers:
            _m6b_emit(markers, "stage", "authority_validated", started)
            cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
                run_dir, mesh_name="m6b_stage_mesh"
            )
            _m6b_emit(markers, "stage", "mesh_ready", started)
            _m6b_emit(markers, "stage", "space_ready", started)
            _m6b_emit(markers, "stage", "floquet_mpc_ready", started)
            if len(modes) != 80:
                raise ValueError("M6B mode authority is not 80 modes")
            cache_dir = run_dir / "jit_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            proxy_forms = h2a._proxy_forms(
                function_space, mesh_data, cfg, cache_dir=cache_dir
            )
            _m6b_emit(markers, "stage", "proxy_forms_ready", started)
            del proxy_forms
            gc.collect()
            physical_ufl, epsilon0, abs_epsilon0, beta0, tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=0.0
            )
            jit_options = h2b._expected_jit_options(cache_dir)
            physical_action = build_task037_extra_h1r2_mpc_action(
                physical_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            physical_record = _m6b_form_record(
                h2b,
                physical_action,
                cache_dir,
                cfg,
                function_space,
                "outer_volume",
                0.0,
            )
            physical_action.destroy()
            del physical_action, physical_ufl, epsilon0, abs_epsilon0, beta0
            gc.collect()
            _m6b_emit(markers, "stage", "outer_form_ready", started)
            shifted_ufl, epsilon1, abs_epsilon1, beta1, shifted_tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=M6B_BETA
            )
            if shifted_tag_coverage != tag_coverage:
                raise ValueError("M6B shared volume material tag coverage changed")
            shifted_action = build_task037_extra_h1r2_mpc_action(
                shifted_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            shifted_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                M6B_BETA,
            )
            shifted_action.destroy()
            del shifted_action, shifted_ufl, epsilon1, abs_epsilon1, beta1
            gc.collect()
            _m6b_emit(markers, "stage", "shifted_form_ready", started)
            shared_volume_kernel = _m6b_shared_kernel_identity(
                physical_record,
                shifted_record,
                cfg,
                phase="stage",
            )
            assemblers = m6a._surface_assemblers(
                function_space, mesh_data, cfg, modes, cache_dir
            )
            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=jit_options,
            )
            surface_identity = m6a._surface_identity(cache_dir, modes)
            cache_inventory = h2b._cache_snapshot(cache_dir)
            forms = {
                "outer_volume": physical_record,
                "shifted_volume": shifted_record,
                "shared_volume_kernel": shared_volume_kernel,
                "material_tag_coverage": tag_coverage,
                "surface": surface_identity,
                "incident_form_count": 1,
                "cache_inventory": cache_inventory,
            }
            p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
            if not _m6b_expected_p6(p6):
                raise ValueError(f"M6B p6 identity mismatch: {p6}")
            runtime = _m6b_runtime_identity(h2b, h2a, comm, compiler_probe=True)
            _m6b_emit(markers, "stage", "surface_forms_ready", started)
            _m6b_emit(markers, "stage", "summary_ready", started)
            del assemblers, incident_form
            del mesh_data, function_space, floquet, modes, cfg
            gc.collect()
            status = "measurement_complete"
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_end = h2b._light_source()
    payload = _attach_evidence(
        {
            "schema": M6B_STAGE_SCHEMA,
            "status": status,
            "scope": _m6b_scope(phase="stage"),
            "events": list(M6B_STAGE_EVENTS),
            "p6": p6,
            "forms": forms,
            "cache_inventory": cache_inventory,
            "runtime_identity": runtime,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _m6b_patch_closure(
    matrix: Any,
    patch_rows: Any,
    action: Any,
    source: Any,
) -> float:
    import numpy as np
    from petsc4py import PETSc

    rows = np.asarray(patch_rows, dtype=np.int64)
    owned_start, owned_end = map(int, source.getOwnershipRange())
    local_rows = rows - owned_start
    if np.any(local_rows < 0) or np.any(rows >= owned_end):
        raise ValueError("M6B patch closure rows are not owned by the builder")
    with source.localForm() as local_source:
        local_source.array_w[:] = 0.0
        local_source.array_w[local_rows] = np.asarray(
            [
                np.sin(0.0021 * row) + 1j * np.cos(0.0011 * row)
                for row in rows.tolist()
            ],
            dtype=np.complex128,
        )
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    result = action.mult(source)
    observed = np.array(
        result.getArray(readonly=True), dtype=np.complex128, copy=True
    )
    expected = np.asarray(matrix, dtype=np.complex128) @ values[local_rows]
    actual = observed[local_rows]
    del result
    return float(
        np.linalg.norm(actual - expected)
        / max(float(np.linalg.norm(expected)), 1.0e-300)
    )


def _run_m6b_builder(run_dir: Path) -> int:
    """Build fresh shifted class blocks and stream 84 row-complete LU factors."""

    import gc
    import time
    from types import SimpleNamespace

    import numpy as np
    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from petsc4py import PETSc
    from src.common.config_3d import target_stage4_config
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
        build_h2b_m6b_shifted_lu_factor,
        stream_write_h2b_m6b_shifted_lu_patch_store,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        build_m6b_volume_form,
        m6b_shifted_local_matrix,
    )
    from src.solvers.hcurl_h2b_p1_factor_store import (
        H2BP1ClassBlockAuthority,
        discover_h2b_p1_neighborhoods,
        stream_h2b_p1_neighborhood,
    )
    from src.solvers.hcurl_r2_constrained_local_block import (
        build_h2a_r2_cell_expansion,
        build_h2a_r2_transformed_block,
    )
    from src.solvers.hcurl_r2_factor_store import (
        H2AR2CellReference,
        load_h2a_r2_factor_store,
    )

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6B builder is fixed to MPI1")
    run_dir = run_dir.resolve()
    started = time.perf_counter()
    progress_path = run_dir / "m6b_builder_progress.jsonl"
    summary_path = run_dir / "m6b_builder_summary.json"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    form_record: dict[str, Any] | None = None
    store_manifest: Path | None = None
    store_audit: dict[str, Any] | None = None
    sample_closure: dict[str, float] = {}
    class_block_audit: dict[str, Any] | None = None
    shared_volume_kernel: dict[str, Any] | None = None
    tag_coverage: dict[str, Any] | None = None
    cache_before: Any = None
    cache_after: Any = None
    shifted_action = None
    shifted_ufl = None
    epsilon = None
    abs_epsilon = None
    beta_constant = None
    source_vec = None
    try:
        with progress_path.open("w", encoding="utf-8") as markers:
            stage = h2b._read_json(run_dir / "m6b_stage_summary.json")
            if (
                stage.get("status") != "measurement_complete"
                or not h2b._evidence_valid(stage)
                or stage.get("forms", {}).get("cache_inventory") is None
            ):
                raise ValueError("M6B stage authority is incomplete")
            _m6b_emit(markers, "builder", "authority_validated", started)
            cfg = target_stage4_config(degree=6, h_nm=10.0)
            mesh_data = build_airbox_mesh_3d(cfg, run_dir / "m6b_builder_mesh")
            _m6b_emit(markers, "builder", "mesh_ready", started)
            function_space = _create_nedelec_space(mesh_data.mesh, cfg)
            _m6b_emit(markers, "builder", "space_ready", started)
            floquet = h2a.build_double_floquet_mpc(function_space, mesh_data, cfg)
            p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
            if not _m6b_expected_p6(p6):
                raise ValueError(f"M6B builder p6 identity mismatch: {p6}")
            _m6b_emit(markers, "builder", "floquet_mpc_ready", started)
            cache_dir = run_dir / "jit_cache"
            cache_before = h2b._cache_snapshot(cache_dir)
            shifted_ufl, epsilon, abs_epsilon, beta_constant, tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=M6B_BETA
            )
            shifted_action = __import__(
                "src.solvers.hcurl_rank_one_mpc_action",
                fromlist=["build_task037_extra_h1r2_mpc_action"],
            ).build_task037_extra_h1r2_mpc_action(
                shifted_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=h2b._expected_jit_options(cache_dir),
            )
            form_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                M6B_BETA,
            )
            shared_volume_kernel = _m6b_shared_kernel_identity(
                stage["forms"]["outer_volume"],
                form_record,
                cfg,
                phase="stage",
            )
            if shared_volume_kernel != stage["forms"].get("shared_volume_kernel"):
                raise ValueError("M6B builder shared volume identity differs from stage")
            authority = h2b._authority()
            r2_store = load_h2a_r2_factor_store(
                h2b.H2B_R2_MANIFEST, task037_extra_h2a_r2=True
            )
            discovery = h2a._discover_cell_references(
                function_space,
                mesh_data,
                cfg,
                floquet,
                geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
            )
            class_inventory = authority["r0"]["class_inventory"]
            key_to_id = {
                str(item["class_key_sha256"]): int(item["class_id"])
                for item in class_inventory
            }
            blocks = tuple(floquet.phase_independent_topology.blocks)
            cell_refs: list[H2AR2CellReference] = []
            expansions: dict[int, Any] = {}
            for reference in discovery["references"]:
                cell_dofs = np.asarray(reference.local_dofs, dtype=np.int64)
                class_id = key_to_id.get(h2a._r0_digest(reference.class_key))
                if class_id is None:
                    raise ValueError("M6B discovery class is not in R0 authority")
                expansion = build_h2a_r2_cell_expansion(
                    h2a._blocks_for_cell(blocks, cell_dofs),
                    cell_dofs,
                    function_space.dofmap.index_map,
                    index_map_bs=int(function_space.dofmap.index_map_bs),
                    phase_x=floquet.phase_x,
                    phase_y=floquet.phase_y,
                    phase_corner=floquet.phase_corner,
                )
                old = expansions.get(class_id)
                if old is not None and old.pattern_sha256 != expansion.pattern_sha256:
                    raise ValueError("M6B expansion pattern differs within class")
                expansions.setdefault(class_id, expansion)
                cell_refs.append(H2AR2CellReference(class_id, expansion.independent_global_rows))
            if len(cell_refs) != M6B_GLOBAL_CELLS or len(r2_store.cells) != len(cell_refs):
                raise ValueError("M6B cell reference count mismatch")
            if any(
                len(cell.independent_global_rows) != M6B_LOCAL_NLOC
                for cell in cell_refs
            ):
                raise ValueError("M6B cell row-complete references are not 882")
            if any(
                a.class_id != b.class_id
                or not np.array_equal(a.independent_global_rows, b.independent_global_rows)
                for a, b in zip(r2_store.cells, cell_refs, strict=True)
            ):
                raise ValueError("M6B fresh cell rows differ from frozen topology")
            del r2_store
            gc.collect()
            proxy_forms = h2a._proxy_forms(function_space, mesh_data, cfg, cache_dir=cache_dir)
            cache_after = h2b._cache_snapshot(cache_dir)
            if (
                cache_before != stage["forms"]["cache_inventory"]
                or cache_before != cache_after
                or form_record.get("code_state") != "hit_no_new_decl_impl"
            ):
                raise ValueError("M6B builder form/cache identity changed after proxy construction")
            _m6b_emit(markers, "builder", "class_expansion_ready", started)
            representative_by_class = {
                int(key_to_id[h2a._r0_digest(key)]): item
                for key, item in discovery["representatives"].items()
            }
            if len(class_inventory) != 24:
                raise ValueError("M6B class inventory is not the fixed 24-class authority")
            class_matrices: list[np.ndarray] = []
            class_shas: list[str] = []
            for class_id in range(len(class_inventory)):
                representative = representative_by_class[class_id]
                cell = int(representative["cell"])
                tag = int(representative["tag"])
                curl, widths, cell_info = h2a.tabulate_task037_extra_h2a_cell_tensor(
                    proxy_forms[0], function_space, mesh_data.cell_tags, cell,
                    geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
                )
                mass, mass_widths, mass_info = h2a.tabulate_task037_extra_h2a_cell_tensor(
                    proxy_forms[1], function_space, mesh_data.cell_tags, cell,
                    geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
                )
                if widths != mass_widths or cell_info != mass_info:
                    raise ValueError("M6B curl/mass tensor identity mismatch")
                epsilon_value = h2a._material_epsilon(cfg, tag)
                local = m6b_shifted_local_matrix(
                    curl,
                    mass,
                    epsilon_value,
                    cfg.k0,
                    M6B_BETA,
                )
                transformed = build_h2a_r2_transformed_block(
                    local, expansions[class_id]
                )
                class_matrices.append(transformed)
                class_shas.append(
                    hashlib.sha256(
                        memoryview(np.ascontiguousarray(transformed)).cast("B")
                    ).hexdigest()
                )
                del curl, mass, local, transformed
            class_authority = H2BP1ClassBlockAuthority(
                np.arange(len(class_matrices), dtype=np.int32),
                tuple(class_shas),
                tuple(class_matrices),
            )
            class_block_audit = {
                key: value
                for key, value in class_authority.audit.items()
                if key != "retained_payload_components"
            }
            class_block_audit["retained_payload_components"] = dict(
                class_authority.audit["retained_payload_components"]
            )
            class_block_audit.update(
                {
                    "operator_identity": M6B_SHIFTED_OPERATOR,
                    "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
                    "retained_class_block_bytes": int(
                        class_authority.audit["retained_payload_bytes"]
                    ),
                    "fresh_B_beta_class_count": len(class_inventory),
                    "fresh_B_beta_matrix_count": len(class_shas),
                    "r2_numeric_store_used_for_blocks": False,
                }
            )
            class_count = len(class_matrices)
            del class_matrices
            gc.collect()
            _m6b_emit(
                markers,
                "builder",
                "class_blocks_ready",
                started,
                class_count=class_count,
            )
            inventory_by_id = {
                int(item["class_id"]): item for item in class_inventory
            }
            fresh_class_records = tuple(
                SimpleNamespace(
                    class_id=class_id,
                    class_key_sha256=inventory_by_id[class_id]["class_key_sha256"],
                    constraint_pattern_sha256=inventory_by_id[class_id][
                        "constraint_pattern_sha256"
                    ],
                    expansion_pattern_sha256=expansions[class_id].pattern_sha256,
                    numeric_matrix_sha256=class_shas[class_id],
                    numeric_matrix_shape=tuple(
                        int(value) for value in class_authority.matrix_for_factor(class_id).shape
                    ),
                    numeric_matrix_dtype=str(
                        class_authority.matrix_for_factor(class_id).dtype
                    ),
                    expansion=expansions[class_id],
                )
                for class_id in range(len(class_inventory))
            )
            p1_discovery = discover_h2b_p1_neighborhoods(
                cell_refs,
                fresh_class_records,
                class_inventory,
                {
                    "operator": M6B_SHIFTED_OPERATOR,
                    "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
                },
                task037_extra_h2b=True,
            )
            if p1_discovery["unique_neighborhood_count"] != M6B_FACTOR_COUNT:
                raise ValueError("M6B neighborhood count mismatch")
            neighborhoods = p1_discovery["neighborhoods"]
            _m6b_emit(
                markers,
                "builder",
                "neighborhood_ready",
                started,
                neighborhood_count=len(neighborhoods),
            )
            source_vec = shifted_action.output_vector.duplicate()
            # The generator keeps only the matrix currently handed to the
            # streaming writer; sampled repeats replace the first matrix.
            def matrix_records():
                for neighborhood in neighborhoods:
                    first = stream_h2b_p1_neighborhood(
                        neighborhood, cell_refs, class_authority, task037_extra_h2b=True
                    )
                    first_matrix = first.pop("matrix")
                    matrix_sha = first["matrix_sha256"]
                    record = {
                        "neighborhood_id": int(neighborhood.neighborhood_id),
                        "key_sha256": neighborhood.key_sha256,
                        "cell_ordinals": list(neighborhood.cell_ordinals),
                        "multiplicity": len(neighborhood.cell_ordinals),
                        "central_class_id": int(neighborhood.central_class_id),
                        "touching_cell_ordinals": list(neighborhood.touching_cell_ordinals),
                        "touching_class_ids": list(neighborhood.touching_class_ids),
                        "touching_count": int(neighborhood.touching_cell_count),
                        "repeat_performed": neighborhood.neighborhood_id in {0, 42, 83},
                    }
                    matrix_to_write = first_matrix
                    if neighborhood.neighborhood_id in {0, 42, 83}:
                        first_factor = build_h2b_m6b_shifted_lu_factor(
                            first_matrix,
                            beta=M6B_BETA,
                            matrix_sha256=matrix_sha,
                            task037_extra_m6b=True,
                        )
                        first_factor_sha = first_factor.factor_sha256
                        del first_factor, first_matrix
                        first_matrix = None
                        repeat = stream_h2b_p1_neighborhood(
                            neighborhood, cell_refs, class_authority, task037_extra_h2b=True
                        )
                        repeat_matrix = repeat.pop("matrix")
                        repeat_matrix_sha = repeat["matrix_sha256"]
                        repeat_factor = build_h2b_m6b_shifted_lu_factor(
                            repeat_matrix,
                            beta=M6B_BETA,
                            matrix_sha256=repeat_matrix_sha,
                            task037_extra_m6b=True,
                        )
                        repeat_factor_sha = repeat_factor.factor_sha256
                        if repeat_matrix_sha != matrix_sha:
                            raise ValueError("M6B sampled shifted patch is nondeterministic")
                        if repeat_factor_sha != first_factor_sha:
                            raise ValueError("M6B sampled shifted factor is nondeterministic")
                        sample_closure[str(neighborhood.neighborhood_id)] = _m6b_patch_closure(
                            repeat_matrix,
                            neighborhood.patch_rows,
                            shifted_action,
                            source_vec,
                        )
                        if sample_closure[str(neighborhood.neighborhood_id)] > 1.0e-11:
                            raise ValueError("M6B shifted patch action closure failed")
                        sample_matrix_sha = repeat_matrix_sha
                        sample_factor_sha = repeat_factor_sha
                        matrix_to_write = repeat_matrix
                        del repeat_factor, repeat_matrix, repeat
                        record.update(
                            {
                                "first_matrix_sha256": matrix_sha,
                                "repeat_matrix_sha256": sample_matrix_sha,
                                "expected_matrix_sha256": sample_matrix_sha,
                                "repeat_factor_sha256": sample_factor_sha,
                                "expected_factor_sha256": sample_factor_sha,
                            }
                        )
                    else:
                        del first
                    yield record, matrix_to_write
                    del matrix_to_write, first_matrix
            cell_counts = np.asarray(
                [len(cell.independent_global_rows) for cell in cell_refs],
                dtype=np.int64,
            )
            row_offsets = np.empty(cell_counts.size + 1, dtype=np.int64)
            row_offsets[0] = 0
            row_offsets[1:] = np.cumsum(cell_counts, dtype=np.int64)
            cell_rows = np.concatenate(
                [cell.independent_global_rows for cell in cell_refs]
            ).astype(np.int64, copy=False)
            if row_offsets[-1] != cell_rows.size or cell_rows.size != M6B_GLOBAL_CELLS * M6B_LOCAL_NLOC:
                raise ValueError("M6B cell row offsets do not close at 252*882")
            store_manifest = stream_write_h2b_m6b_shifted_lu_patch_store(
                matrix_records(),
                run_dir / "shifted_lu_store",
                p1_discovery["cell_neighborhood_ids"],
                row_offsets,
                cell_rows,
                neighborhoods=[
                    {
                        "neighborhood_id": int(item.neighborhood_id),
                        "key_sha256": item.key_sha256,
                        "cell_ordinals": list(item.cell_ordinals),
                        "multiplicity": len(item.cell_ordinals),
                        "factor_id": 0,
                    }
                    for item in neighborhoods
                ],
                identity={
                    "source_identity": source_start,
                    "stage_manifest_sha256": h2b._sha256_file(run_dir / "m6b_stage_summary.json"),
                    "r2_metadata_manifest_sha256": h2b.H2B_R2_MANIFEST_SHA256,
                    "r2_role": "topology_and_class_identity_only",
                    "r2_numeric_store_used_for_blocks": False,
                    "beta": M6B_BETA,
                    "operator": M6B_SHIFTED_OPERATOR,
                },
                beta=M6B_BETA,
                expected_factor_count=M6B_FACTOR_COUNT,
                expected_neighborhood_count=M6B_FACTOR_COUNT,
                task037_extra_m6b=True,
            )
            manifest = h2b._read_json(store_manifest)
            store_audit = dict(manifest["audit"])
            if store_audit["factor_count"] != M6B_FACTOR_COUNT:
                raise ValueError("M6B shifted store factor count mismatch")
            _m6b_emit(markers, "builder", "patch_stream_ready", started)
            _m6b_emit(markers, "builder", "factor_store_ready", started)
            _m6b_emit(markers, "builder", "summary_ready", started)
            del class_authority, fresh_class_records, proxy_forms
            runtime = _m6b_runtime_identity(h2b, h2a, comm, compiler_probe=False, compiler=stage["runtime_identity"]["compiler"])
            status = "measurement_complete"
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for item in (source_vec,):
            if item is not None:
                item.destroy()
        if shifted_action is not None:
            shifted_action.destroy()
        del shifted_ufl, epsilon, abs_epsilon, beta_constant
        gc.collect()
    source_end = h2b._light_source()
    payload = _attach_evidence(
        {
            "schema": M6B_BUILDER_SCHEMA,
            "status": status,
            "scope": _m6b_scope(phase="builder"),
            "events": list(M6B_BUILDER_EVENTS),
            "p6": p6,
            "form": form_record,
            "shared_volume_kernel": shared_volume_kernel if form_record else None,
            "material_tag_coverage": tag_coverage,
            "cache": {
                "stage": stage["forms"]["cache_inventory"],
                "before": cache_before,
                "after": cache_after,
                "unchanged": cache_before == cache_after,
            },
            "factor_store": _artifact(run_dir, "shifted_lu_store/manifest.json") if store_manifest else None,
            "factor_audit": store_audit,
            "class_block_audit": class_block_audit,
            "sample_patch_action_closure": sample_closure,
            "runtime_identity": runtime,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _run_m6b_online_worker(run_dir: Path) -> int:
    """Load the shifted store and run the fixed right-FGMRES screen."""

    import gc
    import time

    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from dolfinx import fem
    from src.solvers.dtn_port_3d import _assemble_mpc_form_vector, _incident_top_traction_form
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
        load_h2b_m6b_shifted_lu_patch_store,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        H2BM6BShiftedPatchPC,
        M6BShiftedPCContext,
        build_m6b_outer_mat,
        build_m6b_volume_form,
        compose_m6b_physical_rhs,
        run_m6b_right_fgmres_screen,
    )
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6B online screen is fixed to MPI1")
    run_dir = run_dir.resolve()
    started = time.perf_counter()
    progress_path = run_dir / "m6b_mpi1_progress.jsonl"
    summary_path = run_dir / "m6b_mpi1_worker_summary.json"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    measurement: dict[str, Any] | None = None
    cache_before: Any = None
    cache_after: Any = None
    cache_final: Any = None
    store = None
    physical_action = None
    shifted_action = None
    dtn_action = None
    outer_mat = None
    outer_context = None
    shifted_vec = None
    rhs_vec = None
    base_vec = None
    physical_ufl = None
    shifted_ufl = None
    epsilon0 = None
    abs_epsilon0 = None
    beta0 = None
    epsilon1 = None
    abs_epsilon1 = None
    beta1 = None
    try:
        with progress_path.open("w", encoding="utf-8") as markers:
            stage = h2b._read_json(run_dir / "m6b_stage_summary.json")
            builder = h2b._read_json(run_dir / "m6b_builder_summary.json")
            if (
                stage.get("status") != "measurement_complete"
                or builder.get("status") != "measurement_complete"
                or not h2b._evidence_valid(stage)
                or not h2b._evidence_valid(builder)
                or builder.get("factor_store") is None
            ):
                raise ValueError("M6B online stage/builder authority is incomplete")
            _m6b_emit(markers, "mpi1", "authority_validated", started)
            cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
                run_dir, mesh_name="m6b_mpi1_mesh"
            )
            p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
            if not _m6b_expected_p6(p6):
                raise ValueError(f"M6B online p6 identity mismatch: {p6}")
            _m6b_emit(markers, "mpi1", "mesh_ready", started)
            _m6b_emit(markers, "mpi1", "space_ready", started)
            _m6b_emit(markers, "mpi1", "floquet_mpc_ready", started)
            cache_dir = run_dir / "jit_cache"
            cache_before = h2b._cache_snapshot(cache_dir)
            physical_ufl, epsilon0, abs_epsilon0, beta0, tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=0.0
            )
            shifted_ufl, epsilon1, abs_epsilon1, beta1, shifted_tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=M6B_BETA
            )
            if shifted_tag_coverage != tag_coverage:
                raise ValueError("M6B shared volume material tag coverage changed")
            jit_options = h2b._expected_jit_options(cache_dir)
            physical_action = build_task037_extra_h1r2_mpc_action(
                physical_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            shifted_action = build_task037_extra_h1r2_mpc_action(
                shifted_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            surface_assemblers = m6a._surface_assemblers(
                function_space, mesh_data, cfg, modes, cache_dir
            )
            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=jit_options,
            )
            cache_after = h2b._cache_snapshot(cache_dir)
            if cache_after != stage.get("forms", {}).get("cache_inventory"):
                raise ValueError("M6B online form/cache identity changed")
            outer_record = _m6b_form_record(
                h2b,
                physical_action,
                cache_dir,
                cfg,
                function_space,
                "outer_volume",
                0.0,
            )
            shifted_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                M6B_BETA,
            )
            shared_volume_kernel = _m6b_shared_kernel_identity(
                outer_record,
                shifted_record,
                cfg,
                phase="mpi1",
            )
            stage_kernel = stage.get("forms", {}).get("shared_volume_kernel")
            if not _m6b_shared_kernel_valid(stage_kernel, phase="stage"):
                raise ValueError("M6B stage shared volume identity is invalid")
            if any(
                shared_volume_kernel[key] != stage_kernel[key]
                for key in (
                    "operator_identity",
                    "representation",
                    "fixed_physics",
                    "module_name",
                    "ufl_signature",
                    "ufcx_signature",
                )
            ):
                raise ValueError("M6B online shared volume identity differs from stage")
            runtime = _m6b_runtime_identity(
                h2b,
                h2a,
                comm,
                compiler_probe=False,
                compiler=stage["runtime_identity"]["compiler"],
            )
            _m6b_emit(markers, "mpi1", "cache_ready", started)
            store = load_h2b_m6b_shifted_lu_patch_store(
                run_dir / "shifted_lu_store" / "manifest.json",
                task037_extra_m6b=True,
            )
            _m6b_emit(markers, "mpi1", "store_ready", started)
            carrier = build_fullspace_dtn_carrier_from_surface(
                modes,
                surface_assemblers,
                floquet.mpc,
                cfg,
                expected_mode_count=80,
            )
            dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
            outer_mat, outer_context = build_m6b_outer_mat(
                physical_action,
                dtn_action,
                owned_rows=M6B_GLOBAL_ROWS,
                global_rows=M6B_GLOBAL_ROWS,
                comm=comm,
            )
            _m6b_emit(markers, "mpi1", "outer_action_ready", started)
            ownership = tuple(int(value) for value in function_space.dofmap.index_map.local_range)
            projections = tuple(
                __import__(
                    "src.solvers.dtn_port_3d",
                    fromlist=["_incident_projection_onto_top_mode"],
                )._incident_projection_onto_top_mode(mode, cfg)
                for mode in modes
            )
            base_vec = _assemble_mpc_form_vector(incident_form, floquet.mpc)
            rhs_vec = base_vec.duplicate()
            compose_m6b_physical_rhs(dtn_action, base_vec, projections, rhs_vec)
            dual_iterator = __import__(
                "src.solvers.hcurl_canonical_vector_dolfinx",
                fromlist=["iter_canonical_full_fe_dual_packets"],
            ).iter_canonical_full_fe_dual_packets
            rhs_manifest = m6a._write_canonical_role(
                run_dir,
                "mpi1",
                "candidate_physical_rhs_dual",
                dual_iterator(function_space, floquet.mpc, rhs_vec),
                rank=comm.rank,
                mpi_size=comm.size,
                ownership_range=ownership,
                comm=comm,
            )
            _m6b_emit(markers, "mpi1", "rhs_ready", started)
            shifted_vec = shifted_action.output_vector.duplicate()

            def shifted_np(values: np.ndarray) -> np.ndarray:
                with shifted_vec.localForm() as local:
                    local.set(0.0)
                    local.array_w[: values.size] = values
                shifted_vec.ghostUpdate(
                    addv=PETSc.InsertMode.INSERT_VALUES,
                    mode=PETSc.ScatterMode.FORWARD,
                )
                result = shifted_action.mult(shifted_vec)
                values = np.array(
                    result.getArray(readonly=True),
                    dtype=np.complex128,
                    copy=True,
                )
                del result
                return values

            slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
            pc_core = H2BM6BShiftedPatchPC(
                store,
                global_row_count=M6B_GLOBAL_ROWS,
                shifted_action=shifted_np,
                slave_identity_rows=slaves,
                task037_extra_m6b=True,
            )
            probe = np.asarray(
                [np.sin(0.0021 * index) + 1j * np.cos(0.0011 * index) for index in range(M6B_GLOBAL_ROWS)],
                dtype=np.complex128,
            )
            first_started = time.perf_counter()
            first_probe, first_probe_measurement = pc_core.apply_with_measurement(probe)
            first_wall_seconds = float(time.perf_counter() - first_started)
            second_started = time.perf_counter()
            second_probe, second_probe_measurement = pc_core.apply_with_measurement(probe)
            second_wall_seconds = float(time.perf_counter() - second_started)

            def probe_record(values: np.ndarray, measurement: Mapping[str, Any], wall: float) -> dict[str, Any]:
                return {
                    "wall_seconds": wall,
                    "hashes": {
                        key: measurement[key]
                        for key in (
                            "rhs_sha256",
                            "correction0_sha256",
                            "action_sha256",
                            "correction_sha256",
                            "residual_sha256",
                        )
                    },
                    "omega": measurement["omega"],
                    "rho_unit": measurement["rho_unit"],
                    "rho_star": measurement["rho_star"],
                    "finite": measurement["finite"],
                    "exact_shifted_action_count": measurement[
                        "exact_shifted_action_count"
                    ],
                    "partition_of_unity_closure_error": measurement[
                        "partition_of_unity_closure_error"
                    ],
                    "correction_bytes": int(np.asarray(values).nbytes),
                }

            first_probe_record = probe_record(
                first_probe, first_probe_measurement, first_wall_seconds
            )
            second_probe_record = probe_record(
                second_probe, second_probe_measurement, second_wall_seconds
            )
            repeat_probe = {
                "first": first_probe_record,
                "second": second_probe_record,
                "identical": bool(
                    first_probe_record["hashes"] == second_probe_record["hashes"]
                    and first_probe_record["omega"] == second_probe_record["omega"]
                    and first_probe_record["rho_unit"] == second_probe_record["rho_unit"]
                    and first_probe_record["rho_star"] == second_probe_record["rho_star"]
                    and first_probe_record["exact_shifted_action_count"]
                    == second_probe_record["exact_shifted_action_count"]
                    and first_probe_record["partition_of_unity_closure_error"]
                    == second_probe_record["partition_of_unity_closure_error"]
                    and first_probe_record["finite"] is True
                    and second_probe_record["finite"] is True
                ),
            }
            del first_probe, second_probe, probe
            pc_context = M6BShiftedPCContext(pc_core)
            screen = run_m6b_right_fgmres_screen(
                outer_mat,
                rhs_vec,
                pc_context=pc_context,
                checkpoint_dir=run_dir,
                operator_context=outer_context,
            )
            _m6b_emit(markers, "mpi1", "screen_ready", started)
            cache_final = h2b._cache_snapshot(cache_dir)
            if cache_before != cache_after or cache_after != cache_final:
                raise ValueError("M6B online cache changed after form construction")
            samples = screen.get("samples")
            if not _m6b_screen_metadata_valid(screen):
                raise ValueError("M6B screen samples are incomplete or nonfinite")
            measurement = {
                "p6": p6,
                "rhs_binding": {
                    "definition": "fresh M6A incident top traction plus fixed outgoing-mode projections",
                    "mode_count": 80,
                    "canonical": rhs_manifest,
                },
                "screen": screen,
                "outer_action_audit": outer_context.audit,
                "volume_action_audit": dict(physical_action.audit),
                "shifted_action_audit": dict(shifted_action.audit),
                "dtn_action_audit": dict(dtn_action.audit),
                "pc_audit": pc_core.audit,
                "material_tag_coverage": tag_coverage,
                "pc_repeat": repeat_probe,
                "m6b_store_audit": store.audit_jsonable(),
                "shared_volume_kernel": shared_volume_kernel,
                "form": {
                    "outer_volume": outer_record,
                    "shifted_volume": shifted_record,
                    "shared_volume_kernel": shared_volume_kernel,
                    "surface": m6a._surface_identity(cache_dir, modes),
                },
                "cache": {
                    "stage": stage.get("forms", {}).get("cache_inventory"),
                    "before": cache_before,
                    "after": cache_after,
                    "final": cache_final,
                    "unchanged": cache_before == cache_after == cache_final,
                },
                "architecture": {
                    "fine_space": "uncondensed_fullspace",
                    "global_matrix": False,
                    "augmented_matrix": False,
                    "static_condensation": False,
                    "trace_slab_pc": False,
                    "explicit_C_materialized_count": 0,
                    "explicit_D_materialized_count": 0,
                    "dtn": True,
                    "pde": False,
                },
                "finite": bool(
                    all(
                        np.isfinite(item["true_relative_residual"])
                        for item in samples.values()
                    )
                ),
            }
            _m6b_emit(markers, "mpi1", "summary_ready", started)
            status = "measurement_complete"
            del surface_assemblers, incident_form, carrier
            gc.collect()
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for item in (rhs_vec, base_vec, shifted_vec):
            if item is not None:
                item.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if shifted_action is not None:
            shifted_action.destroy()
        del physical_ufl, shifted_ufl, epsilon0, abs_epsilon0, beta0
        del epsilon1, abs_epsilon1, beta1
        gc.collect()
        if dtn_action is not None:
            dtn_action.destroy()
    source_end = h2b._light_source()
    payload = _attach_evidence(
        {
            "schema": M6B_WORKER_SCHEMA,
            "status": status,
            "scope": _m6b_scope(phase="mpi1"),
            "events": list(M6B_ONLINE_EVENTS),
            "p6": p6,
            "measurement": measurement,
            "runtime_identity": runtime,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _m6b_command(command: str, run_dir: Path) -> list[str]:
    if command not in {"m6b-stage-worker", "m6b-builder", "m6b-worker"}:
        raise ValueError("M6B command identity is invalid")
    return [
        os.path.abspath(sys.executable),
        "-m",
        "benchmarks.run_task037_extra_m6b",
        command,
        "--run-dir",
        str(run_dir.resolve()),
    ]


def _m6b_phase_record(
    h2b: Any,
    run_dir: Path,
    monitor_phase: str,
    process_info: Mapping[str, Any],
    *,
    compiler_must_be_empty: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    drain = h2b._bounded_process_drain(process_info)
    record = dict(process_info)
    record["timeout_seconds"] = float(timeout_seconds)
    record["watchdog_rss_limit_bytes"] = M6B_WATCHDOG_RSS_LIMIT_BYTES
    record["completion_rss_limit_bytes"] = M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
    record["processes_gone"] = bool(drain["gone"])
    record["drain"] = drain
    try:
        metrics = h2b._timeline_metrics(
            run_dir / f"{monitor_phase}_timeline.jsonl", monitor_phase
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        metrics = None
        record["timeline_error"] = f"{type(exc).__name__}: {exc}"
    record["timeline_metrics"] = metrics
    if isinstance(metrics, Mapping):
        record["peak_rss_bytes"] = int(metrics["peak_rss_bytes"])
        record["swap_bytes"] = int(metrics["swap_bytes"])
        record["compiler_descendant_pids"] = list(
            metrics["compiler_descendant_pids"]
        )
    elif compiler_must_be_empty:
        record["compiler_descendant_pids"] = None
    return record


def _m6b_phase_gate(
    h2b: Any,
    run_dir: Path,
    summary: Mapping[str, Any],
    process_record: Mapping[str, Any],
    *,
    monitor_phase: str,
    progress_phase: str,
    expected_events: Sequence[str],
    compiler_must_be_empty: bool,
    timeout_seconds: float,
    stage_cache: Any = None,
    stage_kernel: Any = None,
) -> bool:
    if monitor_phase not in {"stage", "builder", "online"}:
        return False
    if not isinstance(summary, Mapping) or not _evidence_valid(summary):
        return False
    expected_schema = {
        "stage": M6B_STAGE_SCHEMA,
        "builder": M6B_BUILDER_SCHEMA,
        "online": M6B_WORKER_SCHEMA,
    }[monitor_phase]
    expected_scope = {
        "stage": _m6b_scope(phase="stage"),
        "builder": _m6b_scope(phase="builder"),
        "online": _m6b_scope(phase="mpi1"),
    }[monitor_phase]
    if summary.get("schema") != expected_schema or summary.get("scope") != expected_scope:
        return False
    if not _m6b_lifecycle_valid(
        process_record,
        online=monitor_phase == "online",
        require_compiler_empty=compiler_must_be_empty,
    ):
        return False
    metrics = process_record.get("timeline_metrics")
    if not isinstance(metrics, Mapping):
        return False
    if (
        metrics.get("peak_rss_bytes") != process_record.get("peak_rss_bytes")
        or metrics.get("swap_bytes") != process_record.get("swap_bytes")
        or process_record.get("processes_gone") is not True
        or process_record.get("timeout_seconds") != timeout_seconds
    ):
        return False
    progress_path = {
        "stage": "m6b_stage_progress.jsonl",
        "builder": "m6b_builder_progress.jsonl",
        "online": "m6b_mpi1_progress.jsonl",
    }[monitor_phase]
    progress_phase_value = "mpi1" if monitor_phase == "online" else progress_phase
    if not _m6b_progress_valid(
        run_dir / progress_path, progress_phase_value, expected_events
    ):
        return False
    if summary.get("status") != "measurement_complete":
        return False
    runtime = summary.get("runtime_identity")
    if not h2b._runtime_valid(runtime) or not isinstance(runtime, Mapping):
        return False
    if not isinstance(runtime.get("compiler"), Mapping):
        return False
    if not h2b._source_pair_valid(
        summary.get("source_at_start"), summary.get("source_at_end")
    ):
        return False
    if not _m6b_expected_p6(summary.get("p6", {})):
        return False
    if monitor_phase == "stage":
        forms = summary.get("forms")
        return bool(
            isinstance(forms, Mapping)
            and isinstance(forms.get("cache_inventory"), list)
            and forms["cache_inventory"]
            == h2b._cache_snapshot(run_dir / "jit_cache")
            and _m6b_form_records_bound(
                forms.get("outer_volume"),
                forms.get("shifted_volume"),
                forms.get("shared_volume_kernel"),
                phase="stage",
            )
            and _m6b_material_tag_coverage_valid(
                forms.get("material_tag_coverage"), owned_cells=M6B_GLOBAL_CELLS
            )
        )
    if monitor_phase == "builder":
        cache = summary.get("cache")
        return bool(
            isinstance(cache, Mapping)
            and isinstance(stage_cache, list)
            and isinstance(stage_kernel, Mapping)
            and cache.get("before") == stage_cache == cache.get("after")
            and cache.get("unchanged") is True
            and _m6b_builder_factor_audit_valid(summary.get("factor_audit"))
            and _m6b_builder_summary_valid(summary)
            and summary.get("shared_volume_kernel") == stage_kernel
            and summary.get("factor_store") is not None
        )
    measurement = summary.get("measurement")
    if not isinstance(measurement, Mapping):
        return False
    cache = measurement.get("cache")
    return bool(
        isinstance(cache, Mapping)
        and isinstance(stage_cache, list)
        and isinstance(stage_kernel, Mapping)
        and cache.get("stage") == stage_cache
        and cache.get("before") == stage_cache
        and cache.get("after") == stage_cache
        and cache.get("final") == stage_cache
        and cache.get("unchanged") is True
        and isinstance(measurement.get("screen"), Mapping)
        and _m6b_screen_metadata_valid(measurement["screen"])
        and measurement.get("finite") is True
        and _m6b_loaded_factor_audit_valid(measurement.get("m6b_store_audit"))
        and _m6b_form_records_bound(
            measurement.get("form", {}).get("outer_volume")
            if isinstance(measurement.get("form"), Mapping)
            else None,
            measurement.get("form", {}).get("shifted_volume")
            if isinstance(measurement.get("form"), Mapping)
            else None,
            measurement.get("shared_volume_kernel"),
            phase="mpi1",
        )
        and _m6b_material_tag_coverage_valid(
            measurement.get("material_tag_coverage"), owned_cells=M6B_GLOBAL_CELLS
        )
        and all(
            measurement["shared_volume_kernel"][key] == stage_kernel[key]
            for key in (
                "operator_identity",
                "representation",
                "fixed_physics",
                "module_name",
                "ufl_signature",
                "ufcx_signature",
            )
        )
        and isinstance(measurement.get("rhs_binding"), Mapping)
        and isinstance(measurement["rhs_binding"].get("canonical"), Mapping)
    )


def _m6b_raw_artifacts(
    run_dir: Path, worker: Mapping[str, Any] | None
) -> dict[str, Any]:
    paths = {
        "m6b_stage_summary.json",
        "m6b_stage_progress.jsonl",
        "m6b_builder_summary.json",
        "m6b_builder_progress.jsonl",
        "m6b_mpi1_worker_summary.json",
        "m6b_mpi1_progress.jsonl",
        "stage_timeline.jsonl",
        "stage_stdout.txt",
        "stage_root_pid.json",
        "builder_timeline.jsonl",
        "builder_stdout.txt",
        "builder_root_pid.json",
        "online_timeline.jsonl",
        "online_stdout.txt",
        "online_root_pid.json",
        "shifted_lu_store/manifest.json",
    }
    store_manifest = run_dir / "shifted_lu_store" / "manifest.json"
    if store_manifest.is_file():
        try:
            manifest = _read_json(store_manifest)
            for relative in manifest.get("files", {}):
                paths.add(f"shifted_lu_store/{relative}")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    if isinstance(worker, Mapping):
        measurement = worker.get("online_measurement")
        if isinstance(measurement, Mapping):
            rhs_binding = measurement.get("rhs_binding")
            rhs = (
                rhs_binding.get("canonical")
                if isinstance(rhs_binding, Mapping)
                else None
            )
            if isinstance(rhs, Mapping) and isinstance(rhs.get("path"), str):
                paths.add(rhs["path"])
                manifest_path = run_dir / rhs["path"]
                if manifest_path.is_file():
                    try:
                        manifest = _read_json(manifest_path)
                        for shard in manifest.get("per_rank_shards", []):
                            if isinstance(shard, Mapping) and isinstance(shard.get("filename"), str):
                                paths.add(shard["filename"])
                    except (OSError, TypeError, ValueError, json.JSONDecodeError):
                        pass
            screen = measurement.get("screen")
            if isinstance(screen, Mapping):
                samples = screen.get("samples")
                if isinstance(samples, Mapping):
                    for item in samples.values():
                        if isinstance(item, Mapping):
                            for artifact in item.get("artifacts", {}).values():
                                if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str):
                                    paths.add(artifact["path"])
    return {relative: _artifact(run_dir, relative) for relative in sorted(paths)}


def _run_m6b_watchdog(run_dir: Path) -> int:
    import time

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_start = h2b._light_source()
    source_end = source_start
    predicted = _predicted_live_set()
    dynamic_predicted: dict[str, Any] | None = None
    commands = {
        "stage": _m6b_command("m6b-stage-worker", run_dir),
        "builder": _m6b_command("m6b-builder", run_dir),
        "online": _m6b_command("m6b-worker", run_dir),
    }
    phases: dict[str, Any] = {}
    phase_gates: dict[str, bool] = {}
    stage_summary: dict[str, Any] = {}
    builder_summary: dict[str, Any] = {}
    online_summary: dict[str, Any] = {}
    worker: dict[str, Any] | None = None
    phase_source_identity: dict[str, Any] = {
        "pass": False,
        "source_commit_full_sha": None,
        "phase_names": ["stage", "builder", "online", "watchdog"],
        "all_tracked_source_clean": False,
    }
    status = "controlled_stop"
    error: str | None = None
    try:
        if predicted["gate"] is not True:
            raise ValueError("M6B initial predicted live-set Gate failed")
        stage_process = h2b._monitor_phase(
            run_dir,
            "stage",
            commands["stage"],
            M6B_STAGE_TIMEOUT_SECONDS,
            M6B_WATCHDOG_RSS_LIMIT_BYTES,
        )
        phases["stage"] = _m6b_phase_record(
            h2b,
            run_dir,
            "stage",
            stage_process,
            compiler_must_be_empty=False,
            timeout_seconds=M6B_STAGE_TIMEOUT_SECONDS,
        )
        stage_path = run_dir / "m6b_stage_summary.json"
        if stage_path.is_file():
            stage_summary = _read_json(stage_path)
        phase_gates["stage"] = _m6b_phase_gate(
            h2b,
            run_dir,
            stage_summary,
            phases["stage"],
            monitor_phase="stage",
            progress_phase="stage",
            expected_events=M6B_STAGE_EVENTS,
            compiler_must_be_empty=False,
            timeout_seconds=M6B_STAGE_TIMEOUT_SECONDS,
        )
        if phase_gates["stage"]:
            builder_process = h2b._monitor_phase(
                run_dir,
                "builder",
                commands["builder"],
                M6B_BUILDER_TIMEOUT_SECONDS,
                M6B_WATCHDOG_RSS_LIMIT_BYTES,
            )
            phases["builder"] = _m6b_phase_record(
                h2b,
                run_dir,
                "builder",
                builder_process,
                compiler_must_be_empty=True,
                timeout_seconds=M6B_BUILDER_TIMEOUT_SECONDS,
            )
            builder_path = run_dir / "m6b_builder_summary.json"
            if builder_path.is_file():
                builder_summary = _read_json(builder_path)
            stage_cache = stage_summary.get("forms", {}).get("cache_inventory")
            phase_gates["builder"] = _m6b_phase_gate(
                h2b,
                run_dir,
                builder_summary,
                phases["builder"],
                monitor_phase="builder",
                progress_phase="builder",
                expected_events=M6B_BUILDER_EVENTS,
                compiler_must_be_empty=True,
                timeout_seconds=M6B_BUILDER_TIMEOUT_SECONDS,
                stage_cache=stage_cache,
                stage_kernel=stage_summary.get("forms", {}).get(
                    "shared_volume_kernel"
                ),
            )
        else:
            phase_gates["builder"] = False
            phases["builder"] = {"not_run_by_gate": True}
        if phase_gates["stage"] and phase_gates["builder"]:
            builder_factor_audit = builder_summary.get("factor_audit")
            if not isinstance(builder_factor_audit, Mapping):
                raise ValueError("M6B builder factor audit is missing")
            dynamic_predicted = _dynamic_predicted_live_set(
                builder_factor_audit["retained_total_bytes"]
            )
            if dynamic_predicted["gate"] is True:
                online_process = h2b._monitor_phase(
                    run_dir,
                    "online",
                    commands["online"],
                    M6B_ONLINE_TIMEOUT_SECONDS,
                    M6B_WATCHDOG_RSS_LIMIT_BYTES,
                )
                phases["online"] = _m6b_phase_record(
                    h2b,
                    run_dir,
                    "online",
                    online_process,
                    compiler_must_be_empty=True,
                    timeout_seconds=M6B_ONLINE_TIMEOUT_SECONDS,
                )
                online_path = run_dir / "m6b_mpi1_worker_summary.json"
                if online_path.is_file():
                    online_summary = _read_json(online_path)
                stage_cache = stage_summary.get("forms", {}).get("cache_inventory")
                phase_gates["online"] = _m6b_phase_gate(
                    h2b,
                    run_dir,
                    online_summary,
                    phases["online"],
                    monitor_phase="online",
                    progress_phase="mpi1",
                    expected_events=M6B_ONLINE_EVENTS,
                    compiler_must_be_empty=True,
                    timeout_seconds=M6B_ONLINE_TIMEOUT_SECONDS,
                    stage_cache=stage_cache,
                    stage_kernel=stage_summary.get("forms", {}).get(
                        "shared_volume_kernel"
                    ),
                )
            else:
                phase_gates["online"] = False
                phases["online"] = {
                    "not_run_by_gate": True,
                    "predicted_live_set": dynamic_predicted,
                }
        else:
            phase_gates["online"] = False
            phases["online"] = {"not_run_by_gate": True}
        source_end = h2b._light_source()
        phase_source_identity = _m6b_phase_source_identity(
            {
                "stage": stage_summary,
                "builder": builder_summary,
                "online": online_summary,
                "watchdog": {
                    "source_at_start": source_start,
                    "source_at_end": source_end,
                },
            }
        )
        if all(phase_gates.get(name) is True for name in ("stage", "builder", "online")) and phase_source_identity["pass"] is True:
            measurement = online_summary["measurement"]
            worker = _attach_evidence(
                {
                    "schema": M6B_WORKER_SCHEMA,
                    "status": "measurement_complete",
                    "scope": _m6b_scope(phase="mpi1"),
                    "p6": measurement["p6"],
                    "stage": phases["stage"],
                    "online": phases["online"],
                    "factor_store": measurement["m6b_store_audit"],
                    "builder_factor_audit": builder_summary["factor_audit"],
                    "screen": measurement["screen"]["samples"],
                    "screen_metadata": measurement["screen"],
                    "architecture": measurement["architecture"],
                    "runtime_identity": online_summary["runtime_identity"],
                    "source_at_start": online_summary["source_at_start"],
                    "source_at_end": online_summary["source_at_end"],
                    "phase_source_identity": phase_source_identity,
                    "cache": measurement["cache"],
                    "pc_repeat": measurement["pc_repeat"],
                    "rhs_binding": measurement["rhs_binding"],
                    "online_measurement": measurement,
                    "builder_summary": _artifact(run_dir, "m6b_builder_summary.json"),
                    "stage_summary": _artifact(run_dir, "m6b_stage_summary.json"),
                }
            )
            _write_json(run_dir / "m6b_worker_summary.json", worker)
            status = "measurement_complete"
        else:
            error = (
                "M6B phase/source Gate stopped before complete online measurement"
            )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    final_source_end = h2b._light_source()
    final_phase_source_identity = _m6b_phase_source_identity(
        {
            "stage": stage_summary,
            "builder": builder_summary,
            "online": online_summary,
            "watchdog": {
                "source_at_start": source_start,
                "source_at_end": final_source_end,
            },
        }
    )
    if final_phase_source_identity != phase_source_identity:
        if status == "measurement_complete":
            status = "controlled_stop"
            error = "M6B source identity changed before watchdog finalization"
        phase_source_identity = final_phase_source_identity
    source_end = final_source_end
    payload = _attach_evidence(
        {
            "schema": M6B_WATCHDOG_SCHEMA,
            "status": status,
            "pass": status == "measurement_complete",
            "scope": _m6b_scope(),
            "predicted_live_set": predicted,
            "dynamic_predicted_live_set": dynamic_predicted,
            "command_identity": commands,
            "phase_gates": phase_gates,
            "phase_source_identity": phase_source_identity,
            "phases": phases,
            "worker_summary": _artifact(run_dir, "m6b_worker_summary.json"),
            "raw_artifacts": _m6b_raw_artifacts(run_dir, worker),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(run_dir / "m6b_watchdog_summary.json", payload)
    return 0 if status == "measurement_complete" else 1


def _m6b_checkpoint_recompute(run_dir: Path, screen: Any) -> dict[str, Any]:
    import numpy as np

    required_iterations = {str(value) for value in M6B_SCREEN_ITERATIONS}
    problems: list[str] = []
    residuals: dict[str, float] = {}
    if not isinstance(screen, Mapping) or set(screen) != required_iterations:
        return {"pass": False, "problems": ["checkpoint_set"], "residuals": residuals}
    required_arrays = {"solution", "outer_action", "residual", "rhs"}
    for key in sorted(required_iterations, key=int):
        item = screen[key]
        if not isinstance(item, Mapping) or set(item.get("artifacts", {})) != required_arrays:
            problems.append(f"checkpoint_{key}_artifacts")
            continue
        arrays: dict[str, Any] = {}
        for name in sorted(required_arrays):
            record = item["artifacts"][name]
            expected_path = f"m6b_iter{int(key)}_{name}.npy"
            if (
                not isinstance(record, Mapping)
                or set(record) != {"path", "bytes", "sha256", "array_sha256", "shape", "dtype"}
                or record.get("path") != expected_path
            ):
                problems.append(f"checkpoint_{key}_{name}_identity")
                continue
            path = run_dir / expected_path
            actual = _artifact(run_dir, expected_path)
            if (
                actual.get("present") is not True
                or actual.get("bytes") != record.get("bytes")
                or actual.get("sha256") != record.get("sha256")
            ):
                problems.append(f"checkpoint_{key}_{name}_file")
                continue
            try:
                array = np.load(path, allow_pickle=False, mmap_mode="r")
                observed_array_sha = hashlib.sha256(
                    memoryview(np.ascontiguousarray(array)).cast("B")
                ).hexdigest()
                if (
                    array.dtype != np.dtype(np.complex128)
                    or list(array.shape) != [M6B_GLOBAL_ROWS]
                    or record.get("shape") != [M6B_GLOBAL_ROWS]
                    or record.get("dtype") != "complex128"
                    or observed_array_sha != record.get("array_sha256")
                    or not np.all(np.isfinite(array))
                ):
                    problems.append(f"checkpoint_{key}_{name}_array")
                arrays[name] = array
            except (OSError, TypeError, ValueError):
                problems.append(f"checkpoint_{key}_{name}_load")
        if set(arrays) != required_arrays:
            continue
        expected_residual = np.asarray(arrays["rhs"]) - np.asarray(arrays["outer_action"])
        closure = float(
            np.linalg.norm(expected_residual - np.asarray(arrays["residual"]))
            / max(float(np.linalg.norm(arrays["rhs"])), np.finfo(float).tiny)
        )
        relative = float(
            np.linalg.norm(expected_residual)
            / max(float(np.linalg.norm(arrays["rhs"])), np.finfo(float).tiny)
        )
        recorded = item.get("true_relative_residual")
        if (
            not _finite_number(recorded)
            or closure > 1.0e-12
            or abs(relative - float(recorded)) > 1.0e-12 * max(1.0, abs(relative))
        ):
            problems.append(f"checkpoint_{key}_residual")
        else:
            residuals[key] = relative
        del arrays, expected_residual
    return {"pass": not problems, "problems": problems, "residuals": residuals}


def _check_command(run_dir: Path, output: Path) -> int:
    checks: dict[str, bool] = {
        "watchdog": False,
        "worker_summary": False,
        "worker_payload": False,
        "checkpoint_arrays": False,
        "raw_inventory": False,
        "command_identity": False,
        "initial_prediction": False,
        "dynamic_prediction": False,
        "phase_lifecycle": False,
        "builder_summary": False,
        "watchdog_phase_source_identity": False,
        "worker_phase_source_identity": False,
        "checker_source_identity": False,
        "shared_volume_kernel": False,
        "material_tag_coverage": False,
    }
    problems: list[str] = []
    watchdog_path = run_dir / "m6b_watchdog_summary.json"
    worker_path = run_dir / "m6b_worker_summary.json"
    watchdog: dict[str, Any] | None = None
    worker: dict[str, Any] | None = None
    checker_h2b: Any | None = None
    checker_source_start: Mapping[str, Any] | None = None
    checker_source_end: Mapping[str, Any] | None = None
    phase_source_identity_for_check: Mapping[str, Any] | None = None
    try:
        checker_h2b = __import__(
            "benchmarks.run_task037_extra_h2b", fromlist=["_light_source"]
        )
        checker_source_start = checker_h2b._light_source()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        problems.append(f"checker_source_start:{type(exc).__name__}")
    try:
        watchdog = _read_json(watchdog_path)
        watchdog_start = watchdog.get("source_at_start")
        watchdog_end = watchdog.get("source_at_end")
        watchdog_source_pair = bool(
            isinstance(watchdog_start, Mapping)
            and isinstance(watchdog_end, Mapping)
            and watchdog_start.get("source_commit_full_sha")
            == watchdog_end.get("source_commit_full_sha")
            and watchdog_start.get("tracked_source_dirty") is False
            and watchdog_end.get("tracked_source_dirty") is False
        )
        stage_summary_for_check = _read_json(run_dir / "m6b_stage_summary.json")
        builder_summary_for_check = _read_json(
            run_dir / "m6b_builder_summary.json"
        )
        online_summary_for_check = _read_json(
            run_dir / "m6b_mpi1_worker_summary.json"
        )
        phase_source_identity_for_check = _m6b_phase_source_identity(
            {
                "stage": stage_summary_for_check,
                "builder": builder_summary_for_check,
                "online": online_summary_for_check,
                "watchdog": {
                    "source_at_start": watchdog_start,
                    "source_at_end": watchdog_end,
                },
            }
        )
        checks["watchdog"] = bool(
            watchdog.get("schema") == M6B_WATCHDOG_SCHEMA
            and _evidence_valid(watchdog)
            and watchdog.get("status") == "measurement_complete"
            and watchdog.get("pass") is True
            and watchdog.get("scope") == _m6b_scope()
            and watchdog.get("predicted_live_set") == _predicted_live_set()
            and isinstance(watchdog.get("predicted_live_set"), Mapping)
            and watchdog["predicted_live_set"].get("gate") is True
            and watchdog.get("phase_gates") == {
                "stage": True,
                "builder": True,
                "online": True,
            }
            and watchdog_source_pair
            and watchdog.get("phase_source_identity") == phase_source_identity_for_check
            and phase_source_identity_for_check["pass"] is True
            and watchdog_start.get("source_commit_full_sha")
            == phase_source_identity_for_check["source_commit_full_sha"]
        )
        builder_factor_audit_for_check = builder_summary_for_check["factor_audit"]
        expected_dynamic_prediction = _dynamic_predicted_live_set(
            builder_factor_audit_for_check["retained_total_bytes"]
        )
        checks["initial_prediction"] = bool(
            watchdog.get("predicted_live_set") == _predicted_live_set()
            and isinstance(watchdog.get("predicted_live_set"), Mapping)
            and watchdog["predicted_live_set"].get("gate") is True
        )
        checks["dynamic_prediction"] = bool(
            watchdog.get("dynamic_predicted_live_set") == expected_dynamic_prediction
            and isinstance(watchdog.get("dynamic_predicted_live_set"), Mapping)
            and watchdog["dynamic_predicted_live_set"].get("gate") is True
        )
        checks["builder_summary"] = _m6b_builder_summary_valid(
            builder_summary_for_check
        )
        stage_kernel_for_check = (
            stage_summary_for_check.get("forms", {}).get("shared_volume_kernel")
            if isinstance(stage_summary_for_check.get("forms"), Mapping)
            else None
        )
        builder_kernel_for_check = builder_summary_for_check.get(
            "shared_volume_kernel"
        )
        online_measurement_for_check = online_summary_for_check.get("measurement")
        online_kernel_for_check = (
            online_measurement_for_check.get("shared_volume_kernel")
            if isinstance(online_measurement_for_check, Mapping)
            else None
        )
        stage_forms_for_check = stage_summary_for_check.get("forms")
        online_forms_for_check = (
            online_measurement_for_check.get("form")
            if isinstance(online_measurement_for_check, Mapping)
            else None
        )
        identity_keys = (
            "operator_identity",
            "representation",
            "fixed_physics",
            "module_name",
            "ufl_signature",
            "ufcx_signature",
        )
        checks["shared_volume_kernel"] = bool(
            _m6b_shared_kernel_valid(stage_kernel_for_check, phase="stage")
            and _m6b_shared_kernel_valid(builder_kernel_for_check, phase="builder")
            and _m6b_shared_kernel_valid(online_kernel_for_check, phase="mpi1")
            and isinstance(stage_forms_for_check, Mapping)
            and _m6b_form_records_bound(
                stage_forms_for_check.get("outer_volume"),
                stage_forms_for_check.get("shifted_volume"),
                stage_kernel_for_check,
                phase="stage",
            )
            and _m6b_form_record_bound(
                builder_summary_for_check.get("form"),
                builder_kernel_for_check,
                role="shifted_volume",
                beta=M6B_BETA,
                code_state="hit_no_new_decl_impl",
                shared_phase="stage",
            )
            and isinstance(online_forms_for_check, Mapping)
            and _m6b_form_records_bound(
                online_forms_for_check.get("outer_volume"),
                online_forms_for_check.get("shifted_volume"),
                online_kernel_for_check,
                phase="mpi1",
            )
            and builder_kernel_for_check == stage_kernel_for_check
            and all(
                online_kernel_for_check[key] == stage_kernel_for_check[key]
                for key in identity_keys
            )
        )
        checks["material_tag_coverage"] = bool(
            isinstance(stage_forms_for_check, Mapping)
            and _m6b_material_tag_coverage_valid(
                stage_forms_for_check.get("material_tag_coverage"),
                owned_cells=M6B_GLOBAL_CELLS,
            )
            and _m6b_material_tag_coverage_valid(
                builder_summary_for_check.get("material_tag_coverage"),
                owned_cells=M6B_GLOBAL_CELLS,
            )
            and isinstance(online_measurement_for_check, Mapping)
            and _m6b_material_tag_coverage_valid(
                online_measurement_for_check.get("material_tag_coverage"),
                owned_cells=M6B_GLOBAL_CELLS,
            )
        )
        phase_records = watchdog["phases"]
        phase_specs = (
            ("stage", False, False, M6B_STAGE_TIMEOUT_SECONDS),
            ("builder", False, True, M6B_BUILDER_TIMEOUT_SECONDS),
            ("online", True, True, M6B_ONLINE_TIMEOUT_SECONDS),
        )
        checks["phase_lifecycle"] = bool(
            isinstance(phase_records, Mapping)
            and all(
                isinstance(phase_records[name], Mapping)
                and _m6b_lifecycle_valid(
                    phase_records[name],
                    online=online,
                    require_compiler_empty=require_compiler_empty,
                )
                and phase_records[name]["timeout_seconds"] == timeout_seconds
                for name, online, require_compiler_empty, timeout_seconds in phase_specs
            )
        )
        checks["watchdog_phase_source_identity"] = bool(
            watchdog.get("phase_source_identity") == phase_source_identity_for_check
        )
        expected_commands = {
            name: _m6b_command(command, run_dir)
            for name, command in (
                ("stage", "m6b-stage-worker"),
                ("builder", "m6b-builder"),
                ("online", "m6b-worker"),
            )
        }
        checks["command_identity"] = watchdog.get("command_identity") == expected_commands
        checks["raw_inventory"] = watchdog.get("raw_artifacts") == _m6b_raw_artifacts(
            run_dir, _read_json(worker_path) if worker_path.is_file() else None
        )
        worker = _read_json(worker_path)
        checks["worker_summary"] = bool(
            worker.get("schema") == M6B_WORKER_SCHEMA
            and _evidence_valid(worker)
            and watchdog.get("worker_summary") == _artifact(run_dir, worker_path.name)
        )
        checks["worker_phase_source_identity"] = bool(
            checks["worker_summary"]
            and worker.get("phase_source_identity")
            == watchdog.get("phase_source_identity")
        )
        if checks["worker_summary"]:
            worker_checks = _m6b_check_payload(worker)
            checks["worker_payload"] = worker_checks["pass"] is True
            checkpoint = _m6b_checkpoint_recompute(
                run_dir, worker.get("screen")
            )
            checks["checkpoint_arrays"] = checkpoint["pass"] is True
            problems.extend(worker_checks["problems"])
            problems.extend(checkpoint["problems"])
        else:
            worker_checks = {"checks": {}, "problems": ["worker_summary_invalid"]}
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        worker_checks = {"checks": {}, "problems": [f"raw_unreadable:{type(exc).__name__}"]}
        problems.append(f"raw_unreadable:{type(exc).__name__}")
    if checker_h2b is not None and checker_source_start is not None:
        checker_source_end = checker_h2b._light_source()
        checks["checker_source_identity"] = bool(
            checker_h2b._source_pair_valid(checker_source_start, checker_source_end)
            and isinstance(phase_source_identity_for_check, Mapping)
            and phase_source_identity_for_check.get("pass") is True
            and checker_source_start.get("source_commit_full_sha")
            == phase_source_identity_for_check.get("source_commit_full_sha")
            and checker_source_end.get("source_commit_full_sha")
            == phase_source_identity_for_check.get("source_commit_full_sha")
        )
    for name, passed in checks.items():
        if not passed:
            problems.append(name)
    result = {
        "schema": M6B_CHECK_SCHEMA,
        "status": "pass" if all(checks.values()) else "gate_failed",
        "pass": all(checks.values()),
        "checks": {**checks, **worker_checks.get("checks", {})},
        "problems": sorted(set(problems)),
        "predicted_live_set": _predicted_live_set(),
        "watchdog": _artifact(run_dir, watchdog_path.name),
        "worker_summary": _artifact(run_dir, worker_path.name),
        "dynamic_predicted_live_set": watchdog.get("dynamic_predicted_live_set")
        if isinstance(watchdog, Mapping)
        else None,
        "checker_source": {
            "start": checker_source_start,
            "end": checker_source_end,
        },
        "worker_source": None if worker is None else {
            "start": worker.get("source_at_start"),
            "end": worker.get("source_at_end"),
        },
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (
        "m6b-stage-worker",
        "m6b-builder",
        "m6b-worker",
        "m6b-watchdog",
        "m6b-w1-builder",
    ):
        item = sub.add_parser(command)
        item.add_argument("--run-dir", required=True)
        if command == "m6b-w1-builder":
            item.add_argument("--jit-cache-source", required=True)
    check = sub.add_parser("m6b-check")
    check.add_argument("--run-dir", required=True)
    check.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    if args.command == "m6b-check":
        return _check_command(run_dir, Path(args.output).resolve())
    if args.command == "m6b-stage-worker":
        return _run_m6b_stage_worker(run_dir)
    if args.command == "m6b-builder":
        return _run_m6b_builder(run_dir)
    if args.command == "m6b-worker":
        return _run_m6b_online_worker(run_dir)
    if args.command == "m6b-watchdog":
        return _run_m6b_watchdog(run_dir)
    if args.command == "m6b-w1-builder":
        return _run_m6b_w1_builder(run_dir, Path(args.jit_cache_source).resolve())
    raise ValueError(f"unknown M6B command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
