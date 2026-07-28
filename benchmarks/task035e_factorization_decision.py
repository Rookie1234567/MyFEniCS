#!/usr/bin/env python3
"""Build the fail-closed Task035e p6/h5 factorization launch authority.

The authority grants no numerical or PDE credit.  It only decides whether the
already assembled p6/h5 matrix may safely enter MUMPS factorization.  The
decision is calibrated by completed p6/h10 and p6/h7.5 full solves and by the
p6/h5 assembly-only record, all bound by independently supplied file hashes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any, Mapping, Sequence


AUTHORITY_SCHEMA = "task035e.h5-factorization-launch-authority.v1"
WATCHDOG_SCHEMA = "task033.full3d-watchdog.v1"
WATCHDOG_BENCHMARK = "task033_target_full3d_watchdog"
RESOURCE_SCHEMA = "task035e.reference-resource-authority.v1"
CONFIG_SCHEMA = "task035e.reference-config-authority.v1"
LIFECYCLE_SCHEMA = "task035e.reference-lifecycle-authority.v1"
STATIC_BACKEND = "assembly_time_static_condensed"
MINIMUM_HEADROOM_FRACTION = 0.20
TOTAL_MEMORY_CAP_FRACTION = 0.80
AUTHORITY_VALIDITY_SECONDS = 15 * 60
MIB = 1024**2

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_MESH_ONLY_CONFIG_KEYS = frozenset(
    {
        "case_name",
        "h_nm",
        "mesh_axis_cell_counts",
        "mesh_cells",
        "mesh_refined_size_resolved",
        "mesh_refinement_radius_resolved",
        "mesh_target_size",
    }
)
_ASSEMBLY_STAGES = frozenset({"stage4_full3d_assembly_backend"})
_SOLVER_STAGES = frozenset(
    {
        "during_ksp_setup_peak",
        "during_ksp_solve_peak",
        "stage4_dtn_port_assembly_and_solve",
    }
)


class FactorizationDecisionError(ValueError):
    """Raised when an authority cannot be persisted safely."""


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise FactorizationDecisionError("non-finite values are not canonical JSON")
    return value


def _json_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FactorizationDecisionError(f"{label} must be a JSON object")
    return value


def _positive_number(value: Any, *, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise FactorizationDecisionError(f"{label} must be finite and positive")
    return float(value)


def _positive_integer_measure(value: Any, *, label: str) -> int:
    number = _positive_number(value, label=label)
    rounded = round(number)
    if not math.isclose(number, rounded, rel_tol=0.0, abs_tol=1.0e-6):
        raise FactorizationDecisionError(f"{label} must be integer-valued")
    return int(rounded)


def _load_bound_record(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[Mapping[str, Any], str]:
    if _SHA256_RE.fullmatch(expected_sha256) is None:
        raise FactorizationDecisionError(
            f"{label} expected SHA-256 must be 64 lowercase hexadecimal characters"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FactorizationDecisionError(
            f"{label} record is not readable"
        ) from exc
    observed = hashlib.sha256(raw).hexdigest()
    if observed != expected_sha256:
        raise FactorizationDecisionError(
            f"{label} record hash mismatch: expected {expected_sha256}, "
            f"observed {observed}"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactorizationDecisionError(
            f"{label} record is not readable JSON"
        ) from exc
    return _mapping(payload, label=f"{label} record"), observed


def _validate_source(record: Mapping[str, Any], *, label: str) -> str:
    source = _mapping(record.get("source"), label=f"{label}.source")
    commit = source.get("commit_sha")
    if _SOURCE_SHA_RE.fullmatch(str(commit)) is None:
        raise FactorizationDecisionError(f"{label}.source.commit_sha is invalid")
    checks = {
        "head_after_matches": source.get("head_after_sha") == commit,
        "tracked_source_clean": source.get("tracked_source_dirty") is False,
        "stable_and_clean_after": source.get("stable_and_clean_after") is True,
        "empty_status_after": source.get("status_after") == "",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise FactorizationDecisionError(
            f"{label} clean-source identity failed: {', '.join(failures)}"
        )
    return str(commit)


def _validate_config(
    task035e: Mapping[str, Any],
    *,
    label: str,
) -> tuple[str, str]:
    authority = _mapping(
        task035e.get("config_authority"),
        label=f"{label}.task035e.config_authority",
    )
    payload = _mapping(
        authority.get("payload"),
        label=f"{label}.task035e.config_authority.payload",
    )
    if (
        authority.get("schema_version") != CONFIG_SCHEMA
        or payload.get("schema_version") != CONFIG_SCHEMA
        or payload.get("mpi_size") != 8
    ):
        raise FactorizationDecisionError(
            f"{label} reference config authority identity drifted"
        )
    observed_sha = _json_sha256(payload)
    if authority.get("sha256") != observed_sha:
        raise FactorizationDecisionError(
            f"{label} reference config authority hash is invalid"
        )
    config = _mapping(payload.get("config"), label=f"{label}.config")
    physical_config = {
        str(key): value
        for key, value in config.items()
        if str(key) not in _MESH_ONLY_CONFIG_KEYS
    }
    if not physical_config:
        raise FactorizationDecisionError(f"{label} physical config is empty")
    return observed_sha, _json_sha256(physical_config)


def _validate_live_resource(
    record: Mapping[str, Any],
    task035e: Mapping[str, Any],
    *,
    label: str,
) -> Mapping[str, Any]:
    live = _mapping(
        task035e.get("live_resource_gate"),
        label=f"{label}.task035e.live_resource_gate",
    )
    policy = _mapping(
        live.get("policy"), label=f"{label}.task035e.live_resource_gate.policy"
    )
    total = policy.get("mem_total_bytes")
    available = policy.get("mem_available_start_bytes")
    policy_readable = bool(
        isinstance(total, int)
        and not isinstance(total, bool)
        and total > 0
        and isinstance(available, int)
        and not isinstance(available, bool)
        and 0 <= available <= total
    )
    expected_headroom = (
        int(MINIMUM_HEADROOM_FRACTION * total) if policy_readable else None
    )
    expected_cap = (
        min(
            int(TOTAL_MEMORY_CAP_FRACTION * total),
            available - expected_headroom,
        )
        if policy_readable and expected_headroom is not None
        else None
    )
    checks = {
        "top_level_zero_swap": record.get("no_swap") is True,
        "live_gate_pass": live.get("pass") is True,
        "not_controlled_stop": live.get("controlled_resource_stop") is False,
        "no_stop_reason": live.get("stop_reason") is None,
        "zero_swap_every_sample": live.get("zero_swap_every_sample") is True,
        "zero_swap_bytes": live.get("maximum_swap_authority_bytes") == 0,
        "headroom_preserved": (
            live.get("minimum_headroom_20_percent_preserved") is True
        ),
        "cap_respected": live.get("effective_job_cap_respected") is True,
        "policy_identity": (
            policy.get("schema_version")
            == "task035e.reference-resource-policy.v1"
            and policy.get("pass") is True
            and policy.get("minimum_headroom_fraction")
            == MINIMUM_HEADROOM_FRACTION
            and policy.get("total_memory_cap_fraction")
            == TOTAL_MEMORY_CAP_FRACTION
            and policy.get("formula")
            == "min(0.8*MemTotal, MemAvailable_start-0.2*MemTotal)"
        ),
        "policy_exact_cap": (
            policy_readable
            and policy.get("headroom_floor_bytes") == expected_headroom
            and policy.get("effective_job_cap_bytes") == expected_cap
        ),
        "live_values_below_policy_cap": (
            isinstance(live.get("maximum_job_memory_authority_bytes"), int)
            and not isinstance(live.get("maximum_job_memory_authority_bytes"), bool)
            and live["maximum_job_memory_authority_bytes"] > 0
            and isinstance(expected_cap, int)
            and live["maximum_job_memory_authority_bytes"] < expected_cap
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise FactorizationDecisionError(
            f"{label} live resource identity failed: {', '.join(failures)}"
        )
    return live


def _validate_lifecycle(
    task035e: Mapping[str, Any],
    *,
    label: str,
) -> None:
    lifecycle = _mapping(
        task035e.get("lifecycle_authority"),
        label=f"{label}.task035e.lifecycle_authority",
    )
    checks = _mapping(
        lifecycle.get("checks"),
        label=f"{label}.task035e.lifecycle_authority.checks",
    )
    required = {
        "schema": lifecycle.get("schema_version") == LIFECYCLE_SCHEMA,
        "self_hash": lifecycle.get("sha256")
        == _json_sha256(
            {
                key: value
                for key, value in lifecycle.items()
                if key not in {"sha256", "checks", "pass"}
            }
        ),
        "pass": lifecycle.get("pass") is True,
        "all_checks": bool(checks) and all(value is True for value in checks.values()),
        "static": lifecycle.get("assembly_backend") == STATIC_BACKEND,
        "default": lifecycle.get("petsc_direct_solver_profile") == "default",
        "mumps": lifecycle.get("selected_parallel_lu_solver_type") == "mumps",
        "no_extra_options": lifecycle.get("petsc_extra_options") == {},
        "no_mumps_override": lifecycle.get("mumps_icntl_overrides") == {},
    }
    failures = [name for name, passed in required.items() if not passed]
    if failures:
        raise FactorizationDecisionError(
            f"{label} MUMPS lifecycle identity failed: {', '.join(failures)}"
        )


def _validate_common_identity(
    record: Mapping[str, Any],
    *,
    label: str,
    expected_h_nm: float,
    expected_run_kind: str,
) -> dict[str, Any]:
    expected_status = (
        "task035e_reference_full_solve_pass"
        if expected_run_kind == "full-solve"
        else "task035e_reference_assembly_resource_pass"
    )
    task035e = _mapping(
        record.get("task035e_reference_certifier"),
        label=f"{label}.task035e_reference_certifier",
    )
    qualification = _mapping(
        record.get("qualification"), label=f"{label}.qualification"
    )
    calibration = _mapping(
        record.get("calibration"), label=f"{label}.calibration"
    )
    checks = {
        "schema": record.get("schema_version") == WATCHDOG_SCHEMA,
        "benchmark": record.get("benchmark_id") == WATCHDOG_BENCHMARK,
        "status": record.get("status") == expected_status,
        "run_kind": record.get("run_kind") == expected_run_kind,
        "p6": record.get("degree") == 6,
        "h": isinstance(record.get("h_nm"), (int, float))
        and not isinstance(record.get("h_nm"), bool)
        and math.isclose(
            float(record["h_nm"]), expected_h_nm, rel_tol=0.0, abs_tol=1.0e-12
        ),
        "s_polarization": record.get("polarization_kind") == "s",
        "mpi8": record.get("mpi_size") == 8,
        "default_profile": record.get("profile") == "default",
        "static_requested": (
            record.get("stage4_full3d_assembly_backend_requested") == STATIC_BACKEND
        ),
        "static_actual": (
            record.get("stage4_full3d_assembly_backend_actual") == STATIC_BACKEND
        ),
        "task035e_schema": task035e.get("schema_version") == RESOURCE_SCHEMA,
        "task035e_selected": task035e.get("selected") is True,
        "task035e_credit": task035e.get("credit")
        == (
            "reference_physics_pending_hidden_certifier"
            if expected_run_kind == "full-solve"
            else "resource_only_not_physics"
        ),
        "qualification_pass": qualification.get("pass") is True,
        "qualification_empty_failures": qualification.get("failures") == [],
        "factor_stage_semantics": (
            calibration.get("factorization_or_solve_stage_seen")
            is (expected_run_kind == "full-solve")
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise FactorizationDecisionError(
            f"{label} watchdog identity failed: {', '.join(failures)}"
        )
    source_sha = _validate_source(record, label=label)
    config_sha, physical_config_sha = _validate_config(task035e, label=label)
    _validate_lifecycle(task035e, label=label)
    live = _validate_live_resource(record, task035e, label=label)
    rows = _positive_integer_measure(
        calibration.get("exact_rows"), label=f"{label}.calibration.exact_rows"
    )
    assembled_nnz = _positive_integer_measure(
        calibration.get("exact_assembled_nnz"),
        label=f"{label}.calibration.exact_assembled_nnz",
    )
    return {
        "source_sha": source_sha,
        "config_authority_sha256": config_sha,
        "physical_config_sha256": physical_config_sha,
        "rows": rows,
        "assembled_nnz": assembled_nnz,
        "live_resource_gate": live,
    }


def _stage_peak_mb(
    resource: Mapping[str, Any],
    stages: frozenset[str],
    *,
    label: str,
) -> float:
    rows = resource.get("stage_peaks")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise FactorizationDecisionError(f"{label}.stage_peaks must be an array")
    dedicated = resource.get("dedicated_job_cgroup_observed") is True
    values: list[float] = []
    for row_raw in rows:
        row = _mapping(row_raw, label=f"{label}.stage_peaks[]")
        if row.get("stage") not in stages:
            continue
        process_mb = _positive_number(
            row.get("max_mpi_process_tree_rss_mb"),
            label=f"{label}.{row.get('stage')}.process_tree_mb",
        )
        authority_mb = process_mb
        if dedicated:
            cgroup = _positive_number(
                row.get("max_container_cgroup_current_mb"),
                label=f"{label}.{row.get('stage')}.cgroup_mb",
            )
            authority_mb = max(authority_mb, cgroup)
        values.append(authority_mb)
    if not values:
        raise FactorizationDecisionError(
            f"{label} lacks required stage peak evidence"
        )
    return max(values)


def _completed_full_metrics(
    record: Mapping[str, Any],
    common: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    solver = _mapping(record.get("solver_summary"), label=f"{label}.solver_summary")
    petsc_options = _mapping(
        solver.get("linear_solve_petsc_options"),
        label=f"{label}.solver_summary.linear_solve_petsc_options",
    )
    solver_identity = {
        "default_profile": solver.get("petsc_direct_solver_profile") == "default",
        "mumps_selected": (
            solver.get("selected_parallel_lu_solver_type") == "mumps"
            and solver.get("actual_pc_factor_solver_type") == "mumps"
        ),
        "preonly_lu": (
            petsc_options.get("ksp_type") == "preonly"
            and petsc_options.get("pc_type") == "lu"
            and petsc_options.get("pc_factor_mat_solver_type") == "mumps"
        ),
        "no_raw_mumps_override": not any(
            str(key).startswith("mat_mumps_icntl_") for key in petsc_options
        ),
    }
    solver_identity_failures = [
        name for name, passed in solver_identity.items() if not passed
    ]
    if solver_identity_failures:
        raise FactorizationDecisionError(
            f"{label} solver MUMPS identity failed: "
            f"{', '.join(solver_identity_failures)}"
        )
    inventory = _mapping(
        solver.get("stage4_dtn_factor_inventory"),
        label=f"{label}.solver_summary.stage4_dtn_factor_inventory",
    )
    factor_matrix = _mapping(
        inventory.get("matrix_stats"), label=f"{label}.factor.matrix_stats"
    )
    resource = _mapping(
        record.get("resource_authority"), label=f"{label}.resource_authority"
    )
    if (
        inventory.get("available") is not True
        or inventory.get("factor_solver_type") != "mumps"
    ):
        raise FactorizationDecisionError(
            f"{label} lacks a completed MUMPS factor inventory"
        )
    factor_rows = _positive_integer_measure(
        factor_matrix.get("matrix_rows"), label=f"{label}.factor.matrix_rows"
    )
    factor_nnz = _positive_integer_measure(
        factor_matrix.get("matrix_nnz_used"),
        label=f"{label}.factor.matrix_nnz_used",
    )
    if factor_rows != common["rows"]:
        raise FactorizationDecisionError(
            f"{label} factor rows do not match assembled rows"
        )
    assembly_peak_mb = _stage_peak_mb(
        resource, _ASSEMBLY_STAGES, label=f"{label}.resource_authority"
    )
    solver_peak_mb = _stage_peak_mb(
        resource, _SOLVER_STAGES, label=f"{label}.resource_authority"
    )
    if solver_peak_mb <= assembly_peak_mb:
        raise FactorizationDecisionError(
            f"{label} solver peak must exceed its assembly-stage peak"
        )
    return {
        **common,
        "factor_nnz": factor_nnz,
        "assembly_peak_bytes": math.ceil(assembly_peak_mb * MIB),
        "solver_peak_bytes": math.ceil(solver_peak_mb * MIB),
        "incremental_factor_bytes": math.ceil(
            (solver_peak_mb - assembly_peak_mb) * MIB
        ),
    }


def _assembly_only_metrics(
    record: Mapping[str, Any],
    common: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    resource = _mapping(
        record.get("resource_authority"), label=f"{label}.resource_authority"
    )
    peak_mb = _positive_number(
        resource.get("memory_authority_mb"),
        label=f"{label}.resource_authority.memory_authority_mb",
    )
    return {
        **common,
        "assembly_peak_bytes": math.ceil(peak_mb * MIB),
    }


def _power_law_extrapolate(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    target_x: float,
    *,
    label: str,
) -> tuple[float, float]:
    if not (0.0 < x1 < x2 < target_x and 0.0 < y1 < y2):
        raise FactorizationDecisionError(
            f"{label} requires increasing positive two-point evidence and target"
        )
    exponent = math.log(y2 / y1) / math.log(x2 / x1)
    if not math.isfinite(exponent) or exponent <= 0.0:
        raise FactorizationDecisionError(f"{label} power-law exponent is invalid")
    return y2 * (target_x / x2) ** exponent, exponent


def _build_prediction(
    h10: Mapping[str, Any],
    h7p5: Mapping[str, Any],
    h5: Mapping[str, Any],
) -> dict[str, Any]:
    if not (
        h10["rows"] < h7p5["rows"] < h5["rows"]
        and h10["assembled_nnz"] < h7p5["assembled_nnz"] < h5["assembled_nnz"]
    ):
        raise FactorizationDecisionError(
            "rows and assembled NNZ must increase from h10 to h7.5 to h5"
        )
    fill10 = h10["factor_nnz"] / h10["assembled_nnz"]
    fill7p5 = h7p5["factor_nnz"] / h7p5["assembled_nnz"]
    factor_power, factor_exponent = _power_law_extrapolate(
        h10["assembled_nnz"],
        h10["factor_nnz"],
        h7p5["assembled_nnz"],
        h7p5["factor_nnz"],
        h5["assembled_nnz"],
        label="factor-NNZ extrapolation",
    )
    factor_lower = math.floor(h5["assembled_nnz"] * min(fill10, fill7p5))
    factor_central = math.ceil(h5["assembled_nnz"] * max(fill10, fill7p5))
    factor_upper = math.ceil(
        max(
            1.25 * h5["assembled_nnz"] * max(fill10, fill7p5),
            1.15 * factor_power,
        )
    )

    rates = [
        h10["incremental_factor_bytes"] / h10["factor_nnz"],
        h7p5["incremental_factor_bytes"] / h7p5["factor_nnz"],
    ]
    direct_peak_power, peak_exponent = _power_law_extrapolate(
        h10["factor_nnz"],
        h10["solver_peak_bytes"],
        h7p5["factor_nnz"],
        h7p5["solver_peak_bytes"],
        factor_upper,
        label="solver-peak extrapolation",
    )
    peak_lower = math.ceil(
        h5["assembly_peak_bytes"] + factor_lower * min(rates)
    )
    peak_central = math.ceil(
        h5["assembly_peak_bytes"] + factor_central * max(rates)
    )
    peak_upper = math.ceil(
        max(
            h5["assembly_peak_bytes"] + 1.25 * factor_upper * max(rates),
            1.15 * direct_peak_power,
            peak_central,
        )
    )
    return {
        "schema_version": "task035e.h5-factorization-conservative-prediction.v1",
        "method": {
            "factor_nnz": (
                "max(1.25*largest_observed_fill*h5_assembled_nnz, "
                "1.15*two_point_power_law)"
            ),
            "solver_peak": (
                "max(h5_measured_assembly_peak + "
                "1.25*factor_nnz_upper*largest_incremental_bytes_per_factor_nnz, "
                "1.15*two_point_direct_peak_power_law)"
            ),
            "calibration_points": ["p6/h10_full", "p6/h7.5_full"],
            "target_baseline": "p6/h5_assembly_only_measured_peak",
            "assumptions": [
                "same clean source, physical config, MPI8, static backend, "
                "default MUMPS lifecycle, and zero-swap telemetry",
                "rows, assembled NNZ, factor NNZ, and solver peak grow "
                "monotonically under h refinement",
                "25 percent envelope protects observed fill and incremental "
                "factor-memory rates",
                "15 percent envelope protects two-point power-law extrapolation",
                "prediction is a launch resource bound, not PDE or accuracy credit",
            ],
        },
        "calibration": {
            "h10": {
                "rows": h10["rows"],
                "assembled_nnz": h10["assembled_nnz"],
                "factor_nnz": h10["factor_nnz"],
                "fill_ratio": fill10,
                "assembly_peak_bytes": h10["assembly_peak_bytes"],
                "solver_peak_bytes": h10["solver_peak_bytes"],
                "incremental_bytes_per_factor_nnz": rates[0],
            },
            "h7p5": {
                "rows": h7p5["rows"],
                "assembled_nnz": h7p5["assembled_nnz"],
                "factor_nnz": h7p5["factor_nnz"],
                "fill_ratio": fill7p5,
                "assembly_peak_bytes": h7p5["assembly_peak_bytes"],
                "solver_peak_bytes": h7p5["solver_peak_bytes"],
                "incremental_bytes_per_factor_nnz": rates[1],
            },
            "h5_assembly": {
                "rows": h5["rows"],
                "assembled_nnz": h5["assembled_nnz"],
                "assembly_peak_bytes": h5["assembly_peak_bytes"],
            },
        },
        "fit_diagnostics": {
            "factor_nnz_power_exponent": factor_exponent,
            "solver_peak_power_exponent": peak_exponent,
        },
        "factor_nnz_interval": {
            "lower": factor_lower,
            "central": factor_central,
            "upper": factor_upper,
        },
        "solver_peak_bytes_interval": {
            "lower": peak_lower,
            "central": peak_central,
            "upper": peak_upper,
        },
    }


def read_live_memory_snapshot(path: Path = Path("/proc/meminfo")) -> dict[str, Any]:
    """Read the launch-time Linux memory and current swap-use authority."""

    values: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise FactorizationDecisionError("live /proc/meminfo is unreadable") from exc
    for line in lines:
        name, separator, remainder = line.partition(":")
        if not separator:
            continue
        fields = remainder.strip().split()
        if len(fields) != 2 or fields[1] != "kB":
            continue
        try:
            values[name] = int(fields[0]) * 1024
        except ValueError:
            continue
    required = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
    missing = [name for name in required if name not in values]
    if missing:
        raise FactorizationDecisionError(
            f"live /proc/meminfo lacks: {', '.join(missing)}"
        )
    total = values["MemTotal"]
    available = values["MemAvailable"]
    swap_used = values["SwapTotal"] - values["SwapFree"]
    if total <= 0 or available < 0 or swap_used < 0:
        raise FactorizationDecisionError("live memory values are invalid")
    # Match the watchdog's byte-level policy exactly: ``int`` truncates the
    # positive product toward zero.
    headroom = int(MINIMUM_HEADROOM_FRACTION * total)
    cap = min(
        math.floor(TOTAL_MEMORY_CAP_FRACTION * total),
        available - headroom,
    )
    return {
        "schema_version": "task035e.h5-factorization-live-memory.v1",
        "captured_from": "/proc/meminfo",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "mem_total_bytes": total,
        "mem_available_bytes": available,
        "swap_total_bytes": values["SwapTotal"],
        "swap_free_bytes": values["SwapFree"],
        "swap_used_bytes": swap_used,
        "minimum_headroom_fraction": MINIMUM_HEADROOM_FRACTION,
        "headroom_floor_bytes": headroom,
        "total_memory_cap_fraction": TOTAL_MEMORY_CAP_FRACTION,
        "effective_job_cap_bytes": cap,
        "formula": "min(0.8*MemTotal, MemAvailable-0.2*MemTotal)",
    }


def build_factorization_decision(
    *,
    h10_record: Path,
    h10_sha256: str,
    h7p5_record: Path,
    h7p5_sha256: str,
    h5_assembly_record: Path,
    h5_assembly_sha256: str,
    live_memory: Mapping[str, Any] | None = None,
    decision_time: datetime | None = None,
) -> dict[str, Any]:
    """Return a closed, self-hashed allow/deny authority."""

    issued_at = decision_time or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise FactorizationDecisionError("decision_time must be timezone-aware")
    issued_at = issued_at.astimezone(timezone.utc)
    expires_at = issued_at + timedelta(seconds=AUTHORITY_VALIDITY_SECONDS)
    specifications = (
        ("h10_full", h10_record, h10_sha256, 10.0, "full-solve"),
        ("h7p5_full", h7p5_record, h7p5_sha256, 7.5, "full-solve"),
        ("h5_assembly", h5_assembly_record, h5_assembly_sha256, 5.0, "assembly-only"),
    )
    metrics: dict[str, dict[str, Any]] = {}
    input_rows: dict[str, Any] = {}
    failures: list[str] = []
    for label, path, expected_sha, h_nm, run_kind in specifications:
        input_rows[label] = {
            "path": str(Path(path).resolve()),
            "expected_sha256": expected_sha,
            "observed_sha256": None,
        }
        try:
            record, observed = _load_bound_record(path, expected_sha, label=label)
            input_rows[label]["observed_sha256"] = observed
            common = _validate_common_identity(
                record,
                label=label,
                expected_h_nm=h_nm,
                expected_run_kind=run_kind,
            )
            metrics[label] = (
                _completed_full_metrics(record, common, label=label)
                if run_kind == "full-solve"
                else _assembly_only_metrics(record, common, label=label)
            )
        except (OSError, FactorizationDecisionError) as exc:
            failures.append(f"{label}: {exc}")

    same_identity: dict[str, bool | None] = {
        "same_clean_source": None,
        "same_physical_config_except_mesh_h": None,
    }
    prediction: dict[str, Any] | None = None
    campaign_identity: dict[str, Any] | None = None
    if len(metrics) == 3:
        source_shas = {row["source_sha"] for row in metrics.values()}
        config_shas = {row["physical_config_sha256"] for row in metrics.values()}
        same_identity = {
            "same_clean_source": len(source_shas) == 1,
            "same_physical_config_except_mesh_h": len(config_shas) == 1,
        }
        if len(source_shas) == 1 and len(config_shas) == 1:
            campaign_identity = {
                "source_sha": next(iter(source_shas)),
                "physical_config_sha256": next(iter(config_shas)),
                "h5_config_authority_sha256": metrics["h5_assembly"][
                    "config_authority_sha256"
                ],
            }
        failures.extend(
            name for name, passed in same_identity.items() if passed is not True
        )
        if not failures:
            try:
                prediction = _build_prediction(
                    metrics["h10_full"],
                    metrics["h7p5_full"],
                    metrics["h5_assembly"],
                )
            except FactorizationDecisionError as exc:
                failures.append(f"prediction: {exc}")

    try:
        memory = (
            dict(live_memory)
            if live_memory is not None
            else read_live_memory_snapshot()
        )
        total = _positive_integer_measure(
            memory.get("mem_total_bytes"), label="live_memory.mem_total_bytes"
        )
        available = _positive_integer_measure(
            memory.get("mem_available_bytes"),
            label="live_memory.mem_available_bytes",
        )
        swap_used = memory.get("swap_used_bytes")
        swap_total = memory.get("swap_total_bytes")
        swap_free = memory.get("swap_free_bytes")
        cap = memory.get("effective_job_cap_bytes")
        headroom = memory.get("headroom_floor_bytes")
        captured_at = memory.get("captured_at_utc")
        try:
            captured_time = datetime.fromisoformat(str(captured_at))
        except ValueError as exc:
            raise FactorizationDecisionError(
                "live memory capture timestamp is invalid"
            ) from exc
        if (
            memory.get("schema_version")
            != "task035e.h5-factorization-live-memory.v1"
            or memory.get("captured_from") != "/proc/meminfo"
            or captured_time.tzinfo is None
            or memory.get("formula")
            != "min(0.8*MemTotal, MemAvailable-0.2*MemTotal)"
            or available > total
            or isinstance(swap_used, bool)
            or not isinstance(swap_used, int)
            or swap_used < 0
            or isinstance(swap_total, bool)
            or not isinstance(swap_total, int)
            or swap_total < 0
            or isinstance(swap_free, bool)
            or not isinstance(swap_free, int)
            or swap_free < 0
            or swap_free > swap_total
            or swap_used != swap_total - swap_free
            or isinstance(cap, bool)
            or not isinstance(cap, int)
            or isinstance(headroom, bool)
            or not isinstance(headroom, int)
        ):
            raise FactorizationDecisionError(
                "live memory swap/cap/headroom fields are invalid"
            )
        expected_headroom = int(MINIMUM_HEADROOM_FRACTION * total)
        expected_cap = min(
            math.floor(TOTAL_MEMORY_CAP_FRACTION * total),
            available - expected_headroom,
        )
        if (
            memory.get("minimum_headroom_fraction")
            != MINIMUM_HEADROOM_FRACTION
            or memory.get("total_memory_cap_fraction")
            != TOTAL_MEMORY_CAP_FRACTION
            or headroom != expected_headroom
            or cap != expected_cap
        ):
            raise FactorizationDecisionError(
                "live memory policy fields do not match the Task035e formula"
            )
        if swap_used != 0:
            failures.append("live_memory: nonzero_swap")
        if available < headroom or cap <= 0:
            failures.append("live_memory: less_than_20_percent_headroom")
    except FactorizationDecisionError as exc:
        memory = dict(live_memory or {})
        failures.append(f"live_memory: {exc}")
        cap = None

    predicted_upper = (
        prediction["solver_peak_bytes_interval"]["upper"]
        if prediction is not None
        else None
    )
    below_cap = bool(
        isinstance(predicted_upper, int)
        and isinstance(cap, int)
        and predicted_upper < cap
    )
    if prediction is not None and not below_cap:
        failures.append("predicted_solver_peak_upper_not_below_dynamic_cap")
    failures = list(dict.fromkeys(failures))
    launch_allowed = not failures and below_cap
    payload = {
        "schema_version": AUTHORITY_SCHEMA,
        "authority_role": "resource_launch_decision_only",
        "credit": "no_pde_no_accuracy_no_reference_qualification_credit",
        "issued_at_utc": issued_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "validity_seconds": AUTHORITY_VALIDITY_SECONDS,
        "campaign_identity": campaign_identity,
        "target": {
            "degree": 6,
            "h_nm": 5.0,
            "run_kind_to_authorize": "full-solve",
            "factor_solver": "mumps",
            "mpi_size": 8,
            "assembly_backend": STATIC_BACKEND,
            "profile": "default",
        },
        "input_records": input_rows,
        "identity_checks": same_identity,
        "prediction": prediction,
        "live_memory": memory,
        "gate": {
            "launch_allowed": launch_allowed,
            "predicted_upper_below_dynamic_cap": below_cap,
            "zero_swap_at_decision": memory.get("swap_used_bytes") == 0,
            "minimum_20_percent_headroom_available": bool(
                isinstance(memory.get("mem_available_bytes"), int)
                and isinstance(memory.get("headroom_floor_bytes"), int)
                and memory["mem_available_bytes"] >= memory["headroom_floor_bytes"]
            ),
            "failures": failures,
            "deny_is_controlled_resource_stop": not launch_allowed,
            "launch_semantics": (
                "single immediate h5 full-solve launch only; the watchdog "
                "continuous live resource gate remains mandatory"
            ),
        },
    }
    return {
        "schema_version": AUTHORITY_SCHEMA,
        "sha256": _json_sha256(payload),
        "payload": payload,
    }


def write_authority_exclusive(path: Path, authority: Mapping[str, Any]) -> None:
    """Atomically publish a mode-0600 authority without replacing a file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FactorizationDecisionError(f"refusing to overwrite authority: {path}")
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    data = (
        json.dumps(
            _canonical(authority),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise FactorizationDecisionError(
                f"refusing to overwrite authority: {path}"
            ) from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h10-record", type=Path, required=True)
    parser.add_argument("--h10-sha256", required=True)
    parser.add_argument("--h7p5-record", type=Path, required=True)
    parser.add_argument("--h7p5-sha256", required=True)
    parser.add_argument("--h5-assembly-record", type=Path, required=True)
    parser.add_argument("--h5-assembly-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        authority = build_factorization_decision(
            h10_record=args.h10_record,
            h10_sha256=args.h10_sha256,
            h7p5_record=args.h7p5_record,
            h7p5_sha256=args.h7p5_sha256,
            h5_assembly_record=args.h5_assembly_record,
            h5_assembly_sha256=args.h5_assembly_sha256,
        )
        write_authority_exclusive(args.output, authority)
    except (OSError, FactorizationDecisionError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    launch_allowed = authority["payload"]["gate"]["launch_allowed"] is True
    print(
        json.dumps(
            {
                "schema_version": AUTHORITY_SCHEMA,
                "launch_allowed": launch_allowed,
                "authority_sha256": authority["sha256"],
                "output": str(args.output),
                "credit": "no_pde_no_accuracy_no_reference_qualification_credit",
            },
            sort_keys=True,
        )
    )
    return 0 if launch_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
