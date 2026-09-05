"""Independent compact checker for the Review V19 R0 prototype.

The checker reads only the parent record, the compact raw record, the input,
and marker files.  It never imports the runner or any finite-element/MPI
module and therefore cannot reproduce the numerical implementation by
accident.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


PROFILE = "fullspace_pml_double_sweep_v19"
SCHEMA = "task038.v19.r0.record.v1"
MARKER_SCHEMA = "task038.v19.r0.marker.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SWEEP_ORDER = (0, 1, 2, 3, 3, 2, 1, 0)
P2_IDENTITY_LIMIT = 1.0e-10
POU_LIMIT = 1.0e-12
PML_LAYER_COUNT = 2
P6_SYMBOLIC_PARENT_SCHEMA = "task038.v19.r0.p6-slab1-mumps-symbolic.parent.v1"
P6_SYMBOLIC_PREFLIGHT_SCHEMA = "task038.v19.r0.p6-slab1-mumps-symbolic.preflight.v1"
P6_SYMBOLIC_PARENT_MARKER_SCHEMA = "task038.v19.r0.p6-slab1-mumps-symbolic.parent-marker.v1"
P6_SYMBOLIC_WORKER_MARKER_SCHEMA = "task038.v19.r0.p6-slab1-mumps-symbolic.marker.v1"
P6_SYMBOLIC_PHASE = "r0-p6-symbolic"
P6_SYMBOLIC_HARD_LIMIT = 12_000_000_000
P6_SYMBOLIC_WARNING = 10_000_000_000
P6_SYMBOLIC_REFERENCE_INPUT_SHA256 = (
    "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
)
P6_SYMBOLIC_RESOURCE_STOPS = {
    "process_tree_rss_watchdog",
    "process_tree_swap",
}


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_pairs,
        parse_constant=_reject_constant,
    )


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _cache_manifest(cache_dir: Path) -> dict[str, Any]:
    cache_dir = cache_dir.absolute()
    artifacts: list[dict[str, Any]] = []
    for path in cache_dir.rglob("*"):
        if path.suffix not in {".c", ".o", ".so"} or not path.is_file():
            continue
        artifacts.append(
            {
                "relative_path": path.relative_to(cache_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    artifacts.sort(key=lambda item: item["relative_path"])
    return {
        "cache_dir": str(cache_dir),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }


def _cache_manifest_sha(manifest: dict[str, Any]) -> str:
    return sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _read_process_timeline(path: Path) -> dict[str, Any]:
    rss_values: list[int] = []
    swap_values: list[int] = []
    readable = True
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise ValueError(f"blank process timeline line {line_number}")
            sample = json.loads(
                line,
                object_pairs_hook=_strict_pairs,
                parse_constant=_reject_constant,
            )
            if not isinstance(sample, dict):
                raise ValueError(f"process timeline line {line_number} is not an object")
            authority = sample.get("authority")
            process_tree = authority.get("process_tree") if isinstance(authority, dict) else None
            if not isinstance(process_tree, dict):
                raise ValueError(f"process timeline line {line_number} has no process tree")
            rss = process_tree.get("rss_bytes")
            swap = process_tree.get("swap_bytes")
            status = process_tree.get("all_status_readable")
            if type(rss) is not int or rss < 0:
                raise ValueError(f"process timeline line {line_number} has invalid RSS")
            if type(swap) is not int or swap < 0:
                raise ValueError(f"process timeline line {line_number} has invalid swap")
            if type(status) is not bool:
                raise ValueError(f"process timeline line {line_number} has invalid readability")
            rss_values.append(rss)
            swap_values.append(swap)
            readable = readable and status
    if not rss_values:
        raise ValueError("process timeline is empty")
    return {
        "sample_count": len(rss_values),
        "peak_rss_bytes": max(rss_values),
        "max_swap_bytes": max(swap_values),
        "all_status_readable": readable,
    }


def _recompute_p6_launch_cap(preflight: Any) -> int:
    if not isinstance(preflight, dict):
        raise ValueError("p6 symbolic preflight is not an object")
    mem_total = preflight.get("mem_total_bytes")
    mem_available = preflight.get("mem_available_bytes")
    if type(mem_total) is not int or type(mem_available) is not int:
        raise ValueError("p6 symbolic memory facts are invalid")
    reserve = max(4 * 1024**3, int(0.1 * mem_total))
    if preflight.get("reserve_bytes") != reserve:
        raise ValueError("p6 symbolic reserve does not match MemTotal")
    cap = min(P6_SYMBOLIC_HARD_LIMIT, mem_available - reserve)
    if cap <= 0:
        raise ValueError("p6 symbolic recomputed cap is non-positive")
    if preflight.get("launch_cap_bytes") != cap:
        raise ValueError("p6 symbolic launch cap does not match memory facts")
    if preflight.get("formula") != "min(12000000000, MemAvailable - max(4GiB, 0.1*MemTotal))":
        raise ValueError("p6 symbolic launch-cap formula mismatch")
    return cap


def _check_p6_resource_observation(
    timeline: Any,
    process: Any,
    worker: Any,
    preflight: Any,
    budget: Any,
    errors: list[str],
    gate_failures: list[str],
) -> int | None:
    if not isinstance(timeline, dict):
        _error(errors, "p6 symbolic process timeline facts are missing")
        return None
    try:
        launch_cap = _recompute_p6_launch_cap(preflight)
    except ValueError as exc:
        _error(errors, str(exc))
        return None
    if not isinstance(process, dict):
        _error(errors, "p6 symbolic parent process facts are missing")
    else:
        for key in ("sample_count", "peak_rss_bytes", "max_swap_bytes", "all_status_readable"):
            if process.get(key) != timeline[key]:
                _error(errors, f"p6 symbolic parent process {key} is not timeline-derived")
    if not isinstance(worker, dict):
        _error(errors, "p6 symbolic worker resource facts are missing")
        return launch_cap
    for key in ("peak_rss_bytes", "max_swap_bytes", "all_status_readable"):
        if worker.get(key) != timeline[key]:
            _error(errors, f"p6 symbolic worker {key} is not timeline-derived")
    if (
        type(worker.get("sample_count")) is not int
        or worker["sample_count"] <= 0
        or worker["sample_count"] > timeline["sample_count"]
    ):
        _error(errors, "p6 symbolic worker sample count is not bounded by timeline")
    if not isinstance(budget, dict) or budget.get("launch_cap_bytes") != launch_cap:
        _error(errors, "p6 symbolic budget launch cap is not independently closed")
    if worker.get("rss_watchdog_bytes") != launch_cap:
        _error(errors, "p6 symbolic worker watchdog is not the measured launch cap")
    stop_reason = worker.get("stop_reason")
    if stop_reason == "process_tree_rss_watchdog":
        if timeline["peak_rss_bytes"] < launch_cap:
            _error(errors, "p6 symbolic RSS stop is not supported by timeline peak")
        if timeline["max_swap_bytes"] != 0:
            _error(errors, "p6 symbolic RSS stop has nonzero swap")
    elif stop_reason == "process_tree_swap":
        if timeline["max_swap_bytes"] <= 0:
            _error(errors, "p6 symbolic swap stop is not supported by timeline")
    else:
        _error(errors, "p6 symbolic worker is not a recognized resource stop")
    if timeline["peak_rss_bytes"] >= P6_SYMBOLIC_HARD_LIMIT:
        _error(errors, "p6 symbolic timeline reached the hard limit")
    if stop_reason in P6_SYMBOLIC_RESOURCE_STOPS:
        gate_failures.append(stop_reason)
    return launch_cap


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _error(errors: list[str], text: str) -> None:
    errors.append(text)


def _relative_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("missing relative path")
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def _check_markers(root: Path, errors: list[str]) -> list[str]:
    marker_dir = root / "markers"
    if not marker_dir.is_dir():
        _error(errors, "markers directory is missing")
        return []
    paths = sorted(marker_dir.glob("*.json"))
    names: list[str] = []
    for path in paths:
        try:
            marker = _load_json(path)
        except (OSError, TypeError, ValueError) as exc:
            _error(errors, f"marker unreadable: {path.name}: {exc}")
            continue
        if not isinstance(marker, dict) or marker.get("schema") != MARKER_SCHEMA:
            _error(errors, f"marker schema mismatch: {path.name}")
        name = marker.get("name") if isinstance(marker, dict) else None
        if not isinstance(name, str):
            _error(errors, f"marker name missing: {path.name}")
        else:
            names.append(name)
    expected = [
        "paths_ready",
        "abi_ready",
        "p2_fixture_complete",
        "p6_inventory_complete",
        "record_written",
        "release_complete",
    ]
    if names != expected:
        _error(errors, f"marker order mismatch: {names!r}")
    return names


def _check_map_audit(facts: Any, errors: list[str]) -> None:
    if not isinstance(facts, dict):
        _error(errors, "p2 map audit is missing")
        return
    for key in ("global_row_count", "local_size", "local_position_count"):
        if type(facts.get(key)) is not int or facts[key] <= 0:
            _error(errors, f"p2 map {key} is invalid")
    if facts.get("numeric_allgather") is not False:
        _error(errors, "p2 map permits numeric allgather")
    if facts.get("primal_map") != "global[row] += phase * local":
        _error(errors, "p2 primal map semantics mismatch")
    if facts.get("dual_map") != "local = conjugate(phase) * global[row]":
        _error(errors, "p2 dual map semantics mismatch")


def _check_p2(p2: Any, errors: list[str], gate_failures: list[str]) -> None:
    if not isinstance(p2, dict):
        _error(errors, "p2 fixture facts are missing")
        return
    if p2.get("degree") != 2:
        _error(errors, "p2 fixture degree mismatch")
    if p2.get("pml_rows_materialized") is not True:
        _error(errors, "p2 local PML mesh was not materialized")
    if p2.get("input_unchanged") is not True:
        _error(errors, "p2 source input changed")
    if p2.get("finite") is not True or p2.get("source_finite") is not True or p2.get("output_finite") is not True:
        _error(errors, "p2 action facts are non-finite")
    if p2.get("owned_slave_max") != 0.0:
        _error(errors, "p2 action source is not slave-zero")
    if type(p2.get("owned_slave_count")) is not int or p2["owned_slave_count"] < 0:
        _error(errors, "p2 slave count is invalid")
    for key in (
        "local_action_relative",
        "local_action_repeat_relative",
        "stretch_one_local_maxwell_relative",
        "map_dual_primal_relative",
        "pou_max_error",
    ):
        if not _finite_number(p2.get(key)):
            _error(errors, f"p2 {key} is not finite")
    for key in (
        "local_action_relative",
        "local_action_repeat_relative",
        "stretch_one_local_maxwell_relative",
        "map_dual_primal_relative",
    ):
        if _finite_number(p2.get(key)) and p2[key] > P2_IDENTITY_LIMIT:
            gate_failures.append(f"p2_{key}")
    if _finite_number(p2.get("pou_max_error")) and p2["pou_max_error"] > POU_LIMIT:
        gate_failures.append("p2_pou")
    if p2.get("map_input_unchanged") is not True:
        _error(errors, "p2 map input was changed")
    outgoing = p2.get("pml_outgoing_profile")
    if not isinstance(outgoing, dict):
        _error(errors, "p2 outgoing PML profile facts are missing")
    else:
        for side, profile in outgoing.items():
            if not isinstance(profile, dict) or not _finite_number(
                profile.get("outgoing_amplitude_at_thickness")
            ):
                _error(errors, f"p2 outgoing profile is invalid for {side}")
            elif profile["outgoing_amplitude_at_thickness"] > 0.01 + 1.0e-12:
                gate_failures.append(f"p2_outgoing_decay_{side}")
    _check_map_audit(p2.get("map_audit"), errors)
    form = p2.get("form_facts")
    if not isinstance(form, dict):
        _error(errors, "p2 physical/PML form facts are missing")
    else:
        if form.get("physical_operator") != "curl-curl-k0^2 epsilon":
            _error(errors, "p2 physical operator identity mismatch")
        if form.get("pml_operator") != "same material with Maxwell coordinate pullback":
            _error(errors, "p2 PML operator identity mismatch")
        if form.get("artificial_outer_boundary") != "zero_tangential":
            _error(errors, "p2 outer boundary identity mismatch")
    mumps = p2.get("mumps")
    if not isinstance(mumps, dict):
        _error(errors, "p2 MUMPS facts are missing")
    else:
        analysis = mumps.get("analysis")
        solve = mumps.get("solve")
        preflight = mumps.get("resource_preflight")
        if not isinstance(analysis, dict) or not isinstance(solve, dict):
            _error(errors, "p2 MUMPS analysis/solve facts are incomplete")
        else:
            if (
                analysis.get("analysis_only") is not True
                or analysis.get("symbolic_calls") != 1
                or analysis.get("numeric_calls") != 0
                or analysis.get("solve_calls") != 0
            ):
                _error(errors, "p2 MUMPS analysis lifecycle is not symbolic-only")
            if (
                solve.get("resource_preflight") != "passed"
                or solve.get("analysis_only") is not False
                or solve.get("numeric_factor_called") is not True
                or solve.get("solve_called") is not True
                or solve.get("symbolic_calls") != 1
                or solve.get("numeric_calls") != 1
                or solve.get("solve_calls") != 1
            ):
                _error(errors, "p2 MUMPS same-factor solve lifecycle is not closed")
            raw_info = analysis.get("raw_info")
            infog = raw_info.get("infog") if isinstance(raw_info, dict) else None
            if not isinstance(infog, dict) or type(infog.get("16")) is not int:
                _error(errors, "p2 MUMPS INFOG(16) is missing")
        if not isinstance(preflight, dict):
            _error(errors, "p2 MUMPS resource preflight is missing")
        else:
            predicted = preflight.get("predicted_peak_bytes")
            live_rss = preflight.get("post_analysis_process_tree_rss_bytes")
            infog16 = preflight.get("infog16")
            hard_limit = preflight.get("hard_limit_bytes")
            if (
                type(predicted) is not int
                or type(live_rss) is not int
                or type(infog16) is not int
                or type(hard_limit) is not int
                or predicted != live_rss + max(infog16, 0) * 1_000_000
                or predicted >= hard_limit
                or preflight.get("formula")
                != "post_analysis_process_tree_rss_bytes + max(INFOG(16), 0) * 1000000"
                or preflight.get("safe_cap") != "R0 p2 local diagnostic hard cap"
            ):
                _error(errors, "p2 MUMPS resource prediction is not measured/closed")
        residual = mumps.get("explicit_residual_relative")
        if not _finite_number(residual):
            _error(errors, "p2 MUMPS explicit residual is not finite")
        elif residual > P2_IDENTITY_LIMIT:
            gate_failures.append("p2_mumps_explicit_residual")
        if mumps.get("finite") is not True:
            _error(errors, "p2 MUMPS finite fact is false")
        release = mumps.get("release")
        if not isinstance(release, dict) or release.get("factor_destroyed") is not True:
            _error(errors, "p2 MUMPS factor release is not recorded")
    local_mesh = p2.get("pml_local_mesh_facts")
    if not isinstance(local_mesh, list) or len(local_mesh) != 4:
        _error(errors, "p2 four-slab local mesh facts are missing")
        return
    for index, item in enumerate(local_mesh):
        if not isinstance(item, dict) or item.get("subdomain_id") != index:
            _error(errors, f"p2 subdomain {index} fact mismatch")
            continue
        if item.get("pml_cell_count", 0) <= 0 or item.get("pml_only_local_row_count", 0) <= 0:
            _error(errors, f"p2 subdomain {index} has no actual PML cells/rows")
        if item.get("outer_boundary") != "zero_tangential":
            _error(errors, f"p2 subdomain {index} outer boundary mismatch")
        thickness = item.get("pml_thicknesses_nm")
        if not isinstance(thickness, dict):
            _error(errors, f"p2 subdomain {index} thickness facts missing")
        elif any(
            not _finite_number(thickness.get(side)) or float(thickness.get(side)) < 0.0
            for side in ("left", "right")
        ):
            _error(errors, f"p2 subdomain {index} thickness facts invalid")


def _check_p6(p6: Any, errors: list[str]) -> None:
    if not isinstance(p6, dict):
        _error(errors, "p6 inventory facts are missing")
        return
    if p6.get("degree") != 6:
        _error(errors, "p6 inventory degree mismatch")
    if p6.get("numeric_allgather") is not False or p6.get("matrix_assembled") is not False:
        _error(errors, "p6 inventory violates R0 structure-only contract")
    audit = p6.get("pml_audit")
    if not isinstance(audit, dict) or audit.get("pml_rows_materialized") is not True:
        _error(errors, "p6 actual PML mesh inventory is missing")
        return
    if audit.get("pml_mesh_materials_copied") is not True:
        _error(errors, "p6 PML material continuation is missing")
    if audit.get("pml_layers_are_new_coordinates") is not True:
        _error(errors, "p6 PML coordinates are not marked as new")
    local_facts = audit.get("pml_local_mesh_facts")
    if not isinstance(local_facts, list) or len(local_facts) != 4:
        _error(errors, "p6 four local PML inventories are missing")
    else:
        for index, item in enumerate(local_facts):
            if not isinstance(item, dict) or item.get("subdomain_id") != index:
                _error(errors, f"p6 local subdomain {index} mismatch")
                continue
            if item.get("pml_cell_count", 0) <= 0:
                _error(errors, f"p6 local subdomain {index} has no PML cells")
            if len(item.get("z_values_nm", [])) < 3:
                _error(errors, f"p6 local subdomain {index} z extension is missing")
    if audit.get("global_aij_nnz") is not None or audit.get("global_aij_nnz_status") != "not_assembled_R0_structure_only":
        _error(errors, "p6 global matrix was materialized")


def _check_p6_symbolic(
    parent_path: Path,
    parent: dict[str, Any],
    expected_source_sha: str,
) -> dict[str, Any]:
    """Check the stopped p6 symbolic preflight without importing heavy code."""

    errors: list[str] = []
    gate_failures: list[str] = []
    root = parent_path.parent

    if parent.get("source", {}).get("source_sha") != expected_source_sha:
        _error(errors, "p6 symbolic source SHA mismatch")
    if parent.get("phase") != P6_SYMBOLIC_PHASE:
        _error(errors, "p6 symbolic phase mismatch")
    if parent.get("classification") != "R0_P6_SYMBOLIC_RESOURCE_CONTROLLED_STOP":
        _error(errors, "p6 symbolic stop classification mismatch")
    if parent.get("numeric_factor_and_solve") is not False:
        _error(errors, "p6 symbolic record permits numeric factor or solve")

    paths = parent.get("paths")
    required_paths = {
        "jit_cache": "jit_cache",
        "preflight": "raw/p6_symbolic_preflight.json",
        "worker_record": "raw/worker_record.json",
        "worker_markers": "raw/worker_markers",
        "process_samples": "parent_process.jsonl",
    }
    if not isinstance(paths, dict):
        _error(errors, "p6 symbolic paths are missing")
        paths = {}
    for key, expected in required_paths.items():
        if paths.get(key) != expected:
            _error(errors, f"p6 symbolic path mismatch: {key}")

    try:
        preflight_path = _relative_path(root, paths.get("preflight"))
        process_path = _relative_path(root, paths.get("process_samples"))
        worker_markers = _relative_path(root, paths.get("worker_markers"))
        worker_record_path = _relative_path(root, paths.get("worker_record"))
    except (TypeError, ValueError) as exc:
        _error(errors, f"p6 symbolic path invalid: {exc}")
        preflight_path = process_path = worker_markers = worker_record_path = None

    preflight: Any = None
    if preflight_path is None or not preflight_path.is_file():
        _error(errors, "p6 symbolic preflight is missing")
    else:
        try:
            preflight = _load_json(preflight_path)
        except (OSError, TypeError, ValueError) as exc:
            _error(errors, f"p6 symbolic preflight unreadable: {exc}")
        if isinstance(preflight, dict):
            if preflight.get("schema") != P6_SYMBOLIC_PREFLIGHT_SCHEMA:
                _error(errors, "p6 symbolic preflight schema mismatch")
            if preflight.get("source_sha") != expected_source_sha:
                _error(errors, "p6 symbolic preflight source mismatch")
            if preflight.get("input_sha256") != P6_SYMBOLIC_REFERENCE_INPUT_SHA256:
                _error(errors, "p6 symbolic input SHA mismatch")
            if preflight.get("hard_limit_bytes") != P6_SYMBOLIC_HARD_LIMIT:
                _error(errors, "p6 symbolic hard limit mismatch")
            if preflight.get("warning_bytes") != P6_SYMBOLIC_WARNING:
                _error(errors, "p6 symbolic warning limit mismatch")
            if preflight.get("numeric_and_solve_forbidden") is not True:
                _error(errors, "p6 symbolic numeric/solve prohibition missing")
            if preflight.get("swap_required") != 0:
                _error(errors, "p6 symbolic swap contract mismatch")
            known = preflight.get("known_slab1_preassembly_estimate")
            if (
                not isinstance(known, dict)
                or known.get("structural_entries") != 136_361_232
                or known.get("simultaneous_known_bytes") != 5_999_894_208
                or known.get("sufficiency_claim") is not False
            ):
                _error(errors, "p6 symbolic structural estimate mismatch")

    worker = parent.get("worker")
    resource_stop = isinstance(worker, dict) and worker.get("stop_reason") in P6_SYMBOLIC_RESOURCE_STOPS
    if not resource_stop:
        _error(errors, "p6 symbolic worker is not a recognized resource stop")
    else:
        if worker.get("process_group_gone") is not True:
            _error(errors, "p6 symbolic worker process group remains")
        if worker.get("lifecycle_failure") is not False:
            _error(errors, "p6 symbolic worker lifecycle failed")
        if worker.get("record_present") is not False or worker.get("record_sha256") is not None:
            _error(errors, "p6 symbolic stopped worker record is inconsistent")
        if worker.get("max_swap_bytes") != 0:
            _error(errors, "p6 symbolic worker swap is nonzero")
    process = parent.get("process")
    if (
        not isinstance(process, dict)
        or process.get("all_status_readable") is not True
        or process.get("max_swap_bytes") != 0
        or type(process.get("peak_rss_bytes")) is not int
        or process.get("sample_count", 0) <= 0
    ):
        _error(errors, "p6 symbolic parent process facts are incomplete")

    budget = parent.get("budget")
    if (
        not isinstance(budget, dict)
        or budget.get("hard_limit_bytes") != P6_SYMBOLIC_HARD_LIMIT
        or budget.get("warning_bytes") != P6_SYMBOLIC_WARNING
        or type(budget.get("launch_cap_bytes")) is not int
        or budget.get("launch_cap_bytes") <= 0
        or budget.get("numeric_and_solve_forbidden") is not True
    ):
        _error(errors, "p6 symbolic budget facts are incomplete")

    cache_observation: dict[str, Any] | None = None
    cache = parent.get("cache")
    if not isinstance(cache, dict):
        _error(errors, "p6 symbolic cache boundary is missing")
    else:
        initial_cache = cache.get("initial")
        after_cache = cache.get("after_worker")
        cache_path = None
        try:
            cache_path = _relative_path(root, paths.get("jit_cache"))
        except (TypeError, ValueError) as exc:
            _error(errors, f"p6 symbolic cache path invalid: {exc}")
        if not isinstance(initial_cache, dict) or not isinstance(after_cache, dict):
            _error(errors, "p6 symbolic cache snapshots are incomplete")
        elif cache_path is None or not cache_path.is_dir():
            _error(errors, "p6 symbolic cache directory is missing")
        else:
            actual_cache = _cache_manifest(cache_path)
            empty_cache = {
                "cache_dir": actual_cache["cache_dir"],
                "artifacts": [],
                "artifact_count": 0,
            }
            if (
                type(initial_cache.get("artifact_count")) is not int
                or initial_cache["artifact_count"] != 0
                or initial_cache.get("manifest_sha256") != _cache_manifest_sha(empty_cache)
            ):
                _error(errors, "p6 symbolic initial cache snapshot is not empty/closed")
            recorded_count = after_cache.get("artifact_count")
            recorded_sha = after_cache.get("manifest_sha256")
            if (
                type(recorded_count) is not int
                or recorded_count < 0
                or not isinstance(recorded_sha, str)
                or len(recorded_sha) != 64
                or actual_cache["artifact_count"] < recorded_count
            ):
                _error(errors, "p6 symbolic after-cache snapshot is invalid")
            else:
                if _cache_manifest_sha(actual_cache) != recorded_sha:
                    _error(
                        errors,
                        "p6 symbolic after-cache snapshot differs from current files; "
                        "post-exit cache tail and complete process peak are unknown",
                    )
            cache_observation = {
                "recorded_initial": initial_cache,
                "recorded_after_worker": after_cache,
                "current": {
                    "artifact_count": actual_cache["artifact_count"],
                    "manifest_sha256": _cache_manifest_sha(actual_cache),
                },
                "matches_recorded_after": _cache_manifest_sha(actual_cache) == recorded_sha,
            }
    if process_path is None or not process_path.is_file():
        _error(errors, "p6 symbolic process timeline is missing")
        timeline_facts = None
    else:
        try:
            timeline_facts = _read_process_timeline(process_path)
        except (OSError, TypeError, ValueError) as exc:
            _error(errors, f"p6 symbolic process timeline is invalid: {exc}")
            timeline_facts = None
    if worker_record_path is not None and worker_record_path.exists():
        _error(errors, "p6 symbolic worker record exists after controlled stop")

    launch_cap = _check_p6_resource_observation(
        timeline_facts,
        process,
        worker,
        preflight,
        budget,
        errors,
        gate_failures,
    )

    parent_marker_dir = root / "markers"
    expected_parent_markers = [
        "paths_ready",
        "abi_ready",
        "worker_complete",
        "record_written",
        "release_complete",
    ]
    parent_names: list[str] = []
    for path in sorted(parent_marker_dir.glob("*.json")):
        try:
            marker = _load_json(path)
        except (OSError, TypeError, ValueError) as exc:
            _error(errors, f"p6 symbolic parent marker unreadable: {path.name}: {exc}")
            continue
        if not isinstance(marker, dict) or marker.get("schema") != P6_SYMBOLIC_PARENT_MARKER_SCHEMA:
            _error(errors, f"p6 symbolic parent marker schema mismatch: {path.name}")
        if isinstance(marker, dict) and isinstance(marker.get("name"), str):
            parent_names.append(marker["name"])
    if parent_names != expected_parent_markers:
        _error(errors, f"p6 symbolic parent marker order mismatch: {parent_names!r}")

    worker_names: list[str] = []
    if worker_markers is None or not worker_markers.is_dir():
        _error(errors, "p6 symbolic worker markers are missing")
    else:
        for path in sorted(worker_markers.glob("*.json")):
            try:
                marker = _load_json(path)
            except (OSError, TypeError, ValueError) as exc:
                _error(errors, f"p6 symbolic worker marker unreadable: {path.name}: {exc}")
                continue
            if not isinstance(marker, dict) or marker.get("schema") != P6_SYMBOLIC_WORKER_MARKER_SCHEMA:
                _error(errors, f"p6 symbolic worker marker schema mismatch: {path.name}")
            if isinstance(marker, dict) and isinstance(marker.get("name"), str):
                worker_names.append(marker["name"])
    if worker_names != [
        "paths_ready",
        "abi_ready",
        "p6_levels_built",
        "p6_plan_built",
        "slab1_local_mesh_built",
    ]:
        _error(errors, f"p6 symbolic worker marker order mismatch: {worker_names!r}")

    evidence_valid = not errors
    cache_matches = bool(
        isinstance(cache_observation, dict)
        and cache_observation.get("matches_recorded_after") is True
    )
    return {
        "schema": "task038.v19.r0.p6-slab1-mumps-symbolic.checker.v1",
        "status": "PASS" if evidence_valid else "FAIL",
        "evidence_valid": evidence_valid,
        "classification": (
            "R0_P6_SYMBOLIC_RESOURCE_CONTROLLED_STOP"
            if evidence_valid
            else "R0_P6_SYMBOLIC_EVIDENCE_FAIL"
        ),
        "errors": errors,
        "gate_failures": gate_failures,
        "source_sha": expected_source_sha,
        "parent_record": str(parent_path),
        "resource_stop": resource_stop,
        "resource_gate_failed": resource_stop,
        "launch_cap_bytes": launch_cap,
        "process_timeline": timeline_facts,
        "cache_observation": cache_observation,
        "resource_peak_scope": (
            "complete_timeline"
            if cache_matches
            else "sampled_lower_bound_cache_tail_unobserved"
        ),
        "complete_lifecycle": cache_matches and evidence_valid,
        "worker_marker_order": worker_names,
        "parent_marker_order": parent_names,
    }


def check_record(parent_path: Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gate_failures: list[str] = []
    root = parent_path.parent
    try:
        parent = _load_json(parent_path)
    except (OSError, TypeError, ValueError) as exc:
        return {
            "schema": "task038.v19.r0.checker.v1",
            "status": "FAIL",
            "evidence_valid": False,
            "errors": [f"parent unreadable: {exc}"],
            "gate_failures": [],
        }
    if isinstance(parent, dict) and parent.get("schema") == P6_SYMBOLIC_PARENT_SCHEMA:
        return _check_p6_symbolic(parent_path, parent, expected_source_sha)
    if not isinstance(parent, dict) or parent.get("schema") != SCHEMA:
        _error(errors, "parent schema mismatch")
        return {
            "schema": "task038.v19.r0.checker.v1",
            "status": "FAIL",
            "evidence_valid": False,
            "errors": errors,
            "gate_failures": gate_failures,
        }
    if parent.get("source_sha") != expected_source_sha:
        _error(errors, "source SHA mismatch")
    if parent.get("profile") != PROFILE or parent.get("phase") != "r0":
        _error(errors, "profile/phase mismatch")
    raw_relative = parent.get("raw_record")
    try:
        raw_path = _relative_path(root, raw_relative)
    except (TypeError, ValueError) as exc:
        _error(errors, f"raw record path invalid: {exc}")
        raw_path = None
    if raw_path is None or not raw_path.is_file():
        _error(errors, "raw record missing")
        raw = None
    else:
        if parent.get("raw_record_sha256") != _sha256(raw_path):
            _error(errors, "raw record SHA mismatch")
        try:
            raw = _load_json(raw_path)
        except (OSError, TypeError, ValueError) as exc:
            _error(errors, f"raw record unreadable: {exc}")
            raw = None
    if isinstance(raw, dict):
        if raw.get("schema") != SCHEMA or raw.get("source_sha") != expected_source_sha:
            _error(errors, "raw identity mismatch")
        if raw.get("profile") != PROFILE or raw.get("outer_solve") != "not_run_R0":
            _error(errors, "raw R0 scope mismatch")
        abi = raw.get("abi")
        if not isinstance(abi, dict):
            _error(errors, "R0 ABI facts are missing")
        else:
            if (
                abi.get("qualified_activation") != "1"
                or abi.get("petsc_scalar_type") != "complex128"
                or abi.get("petsc_int_type") != "int32"
                or abi.get("mpi_size") != 1
                or not isinstance(abi.get("python"), str)
                or not isinstance(abi.get("python_prefix"), str)
            ):
                _error(errors, "R0 ABI facts are not qualified complex MPI1")
            library_paths = abi.get("library_paths")
            if not isinstance(library_paths, dict) or any(
                not isinstance(library_paths.get(name), str) or not library_paths[name]
                for name in ("PETSC_DIR", "SLEPC_DIR", "LD_LIBRARY_PATH")
            ):
                _error(errors, "R0 ABI library paths are missing")
        input_facts = raw.get("input")
        if not isinstance(input_facts, dict):
            _error(errors, "input facts missing")
        else:
            try:
                input_path = _relative_path(root, input_facts["relative_path"])
            except (TypeError, ValueError) as exc:
                _error(errors, f"input path invalid: {exc}")
            else:
                if not input_path.is_file() or _sha256(input_path) != input_facts.get("sha256"):
                    _error(errors, "input SHA does not bind the file")
        architecture = raw.get("architecture")
        if not isinstance(architecture, dict):
            _error(errors, "architecture facts missing")
        else:
            if tuple(architecture.get("sweep_order", ())) != SWEEP_ORDER:
                _error(errors, "sweep order mismatch")
            if architecture.get("core_count") != 4 or architecture.get("overlap_layers") != 1:
                _error(errors, "core/overlap contract mismatch")
            if architecture.get("pml_layers") != PML_LAYER_COUNT:
                _error(errors, "PML layer count mismatch")
            if architecture.get("global_matrix_materialized") is not False or architecture.get("numeric_allgather") is not False:
                _error(errors, "architecture materializes forbidden global data")
        _check_p2(raw.get("p2_fixture"), errors, gate_failures)
        _check_p6(raw.get("p6_inventory"), errors)
    marker_names = _check_markers(root, errors)
    evidence_valid = not errors
    classification = (
        "R0_PML_DOUBLE_SWEEP_READY"
        if evidence_valid and not gate_failures
        else "R0_PML_DOUBLE_SWEEP_IDENTITY_FAIL"
        if evidence_valid
        else "R0_PML_DOUBLE_SWEEP_EVIDENCE_FAIL"
    )
    return {
        "schema": "task038.v19.r0.checker.v1",
        "status": "PASS" if evidence_valid else "FAIL",
        "evidence_valid": evidence_valid,
        "classification": classification,
        "errors": errors,
        "gate_failures": gate_failures,
        "marker_order": marker_names,
        "source_sha": expected_source_sha,
        "profile": PROFILE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_record(args.record.absolute(), args.expected_source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
