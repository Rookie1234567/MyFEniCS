"""Independent NumPy checker for the S5 hierarchy-capacity worker."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.full3d.lor-hierarchy-capacity.s5.v1"
CHECK_SCHEMA = "task038.full3d.lor-hierarchy-capacity.s5-check.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_lor_hierarchy_capacity"
CASE = "p6-h10-mpi1"
TEMPLATE_RELATIVE_PATH = "input/templates/full3d_iterative_example.dat"
EXPECTED_INPUT_BYTES = 2119
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_BYTES = 4076
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
LEVELS = (6, 3, 1)
PAIRS = ((6, 3), (3, 1))
MARKERS = (
    "paths_ready", "source_runtime_closed", "foundation_built", "reserve_built",
    "hierarchy_built_first", "probes_complete", "hierarchy_destroyed",
    "hierarchy_rebuilt", "retained_ready", "record_written",
)
ALPHA = 0.37 + 0.19j
BETA = -0.23 + 0.41j
COLD_LIMIT = 2_000_000_000
RETAINED_LIMIT = 1_800_000_000
REPEAT_LIMIT = 1.0e-13
LINEARITY_LIMIT = 1.0e-12
ADJOINT_LIMIT = 1.0e-12
ENERGY_LIMIT = 1.0e-9
LOCAL_LIMIT = 1.0e-11
FINGERPRINT_BANNED_KEYS = frozenset({
    "petsc_reported_memory_bytes", "petsc_overhead_bytes", "rss_bytes",
    "wall_time_ns", "elapsed_seconds", "object_id", "allocator",
    "matrix_mult_count", "power_matrix_mult_count", "apply_count", "cumulative_apply_count",
    "timestamp", "time_ns",
})
TOPOLOGY_FACTS = (
    "owner_local_maps", "numeric_allgather", "global_transfer_matrix",
    "phase_application", "edge_orientation", "cell_permutation",
    "floquet_phase", "slave_master_complete", "global_unique_edge_count",
    "owned_unique_edge_count", "local_unique_edge_count",
)
FORBIDDEN_FACTS = (
    "global_high_order_aij", "global_transfer_matrix", "global_dense_transfer",
    "numeric_allgather", "global_numeric_allgather", "p1_global_direct_factor",
    "p6_exact_factor", "p6_exact_edge_factor_built", "hx_hierarchy_built",
    "pcgamg_hierarchy_built", "scalar_node_matrix_built", "global_direct_coarse_built",
    "recovery_field_arrays_built", "hx_or_node_action_built",
    "production_local_spectral_built", "physical_solve", "recovery",
)
MATRIX_FACTS = ("rows", "cols", "nnz", "index_bytes", "numeric_bytes", "type")
PARENT_INVENTORY = (
    "parent_local_owned_rows", "parent_local_unique_rows", "parent_global_unique_rows",
    "parent_cell_count_local", "owner_route", "parent_matrix_built",
)
RAW_INVENTORY = ("raw_local_owned_rows", "raw_local_unique_rows", "raw_global_unique_rows")
LOCAL_MAP_FACTS = (
    "edge_rows", "edge_cols", "edge_exact_nnz", "edge_numeric_bytes",
    "node_rows", "node_cols", "node_exact_nnz", "node_numeric_bytes",
)
LOCAL_LEGALITY_FACTS = (
    "edge_line_integral_relative", "curl_flux_relative", "gradient_commuting_relative",
    "node_transfer_relative", "adjoint_work_relative", "linearity_relative",
    "repeat_relative", "line_integral_histopolation", "simple_injection",
    "structural_projection", "structural_forbidden_entry_count",
    "structural_forbidden_nnz_after", "structural_removed_nonzero_count",
    "structural_removed_max_abs",
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _semantic_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _error(errors: list[str], condition: bool, message: str) -> None:
    if condition:
        errors.append(message)


def _gate(gates: list[str], condition: bool, message: str) -> None:
    if condition:
        gates.append(message)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _finite_number(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _check_structural_local_legality(
    value: Any, label: str, errors: list[str]
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} structural audit is missing")
        return
    _error(errors, value.get("structural_projection") is not True,
           f"{label} structural projection is not enabled")
    forbidden_count = value.get("structural_forbidden_entry_count")
    _error(errors, type(forbidden_count) is not int or forbidden_count <= 0,
           f"{label} structural forbidden entry count is invalid")
    _error(errors, value.get("structural_forbidden_nnz_after") != 0,
           f"{label} structural forbidden entries are not exact zero")
    removed_count = value.get("structural_removed_nonzero_count")
    _error(errors, type(removed_count) is not int or removed_count < 0 or (
        type(forbidden_count) is int
        and (removed_count > forbidden_count)
    ), f"{label} structural removed count is invalid")
    removed_max_abs = value.get("structural_removed_max_abs")
    removed_max_finite = _finite_number(removed_max_abs)
    _error(errors, not removed_max_finite or float(removed_max_abs) < 0.0,
           f"{label} structural removed maximum is invalid")
    if (
        type(removed_count) is int
        and removed_max_finite
        and float(removed_max_abs) >= 0.0
    ):
        _error(errors, (removed_count == 0) != (float(removed_max_abs) == 0.0),
               f"{label} structural removal facts are not closed")


def _array(data: dict[str, np.ndarray], key: str, errors: list[str]) -> np.ndarray | None:
    if key not in data:
        errors.append(f"raw probe array is missing: {key}")
        return None
    value = np.asarray(data[key])
    if value.ndim != 1 or not np.issubdtype(value.dtype, np.number) or value.size == 0:
        errors.append(f"raw probe array has invalid shape/type: {key}")
        return None
    return np.asarray(value, dtype=np.complex128)


def _same_shape(values: dict[str, np.ndarray | None], errors: list[str], label: str) -> bool:
    arrays = [value for value in values.values() if value is not None]
    if len(arrays) != len(values):
        return False
    if len({array.shape for array in arrays}) != 1:
        errors.append(f"raw probe shape mismatch: {label}")
        return False
    return True


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value, dtype=np.complex128).view(np.uint8)).hexdigest()


def _close(errors: list[str], actual: float, expected: Any, name: str) -> None:
    if not _finite_number(expected) or not np.isclose(actual, float(expected), rtol=1.0e-12, atol=1.0e-15):
        errors.append(f"stored {name} does not match raw recomputation")


def _close_complex(errors: list[str], actual: complex, expected: Any, name: str) -> None:
    if not isinstance(expected, list) or len(expected) != 2:
        errors.append(f"stored {name} complex pair is missing/invalid")
        return
    try:
        expected_value = complex(float(expected[0]), float(expected[1]))
    except (TypeError, ValueError):
        errors.append(f"stored {name} complex pair is invalid")
        return
    if not np.isfinite(expected_value.real) or not np.isfinite(expected_value.imag):
        errors.append(f"stored {name} complex pair is nonfinite")
    elif not np.isclose(actual.real, expected_value.real, rtol=1.0e-12, atol=1.0e-15) or not np.isclose(actual.imag, expected_value.imag, rtol=1.0e-12, atol=1.0e-15):
        errors.append(f"stored {name} does not match raw recomputation")


def _stored_bool(errors: list[str], facts: dict[str, Any], key: str, actual: bool, label: str) -> None:
    _error(errors, facts.get(key) is not actual, f"stored {label} does not match raw recomputation")


def _check_watchdog(compact_path: Path, record: dict[str, Any], record_path: Path,
                    expected_sha: str, errors: list[str], gates: list[str]) -> dict[str, Any]:
    compact = _read(compact_path)
    _error(errors, compact.get("schema") != WATCHDOG_SCHEMA, "watchdog schema mismatch")
    _error(errors, compact.get("source_sha") != expected_sha, "watchdog source SHA mismatch")
    _error(errors, compact.get("worker_command") != record.get("command"), "watchdog command is not record.command")
    _error(errors, Path(compact.get("worker_raw_dir", "")).resolve() != Path(record.get("raw_dir", "")).resolve(), "watchdog worker raw path mismatch")
    _error(errors, Path(compact.get("worker_record", "")).resolve() != record_path.resolve(), "watchdog worker record path mismatch")
    raw_path = Path(compact.get("watchdog_raw", ""))
    _error(errors, not raw_path.is_absolute() or not raw_path.is_file(), "watchdog raw ledger is missing/relative")
    raw_sha = _sha256(raw_path) if raw_path.is_file() else ""
    _error(errors, raw_sha != compact.get("raw_sha256"), "watchdog raw SHA mismatch")
    samples: list[dict[str, Any]] = []
    if raw_path.is_file():
        for number, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=_reject_constant)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"watchdog raw line {number} is invalid: {exc}")
                continue
            if not isinstance(row, dict):
                errors.append(f"watchdog raw line {number} is not an object")
                continue
            samples.append(row)
    _error(errors, compact.get("sample_count") != len(samples), "watchdog sample_count is not raw-derived")
    _error(errors, compact.get("watchdog_poll_seconds") != 0.25, "watchdog poll is not frozen")
    _error(errors, compact.get("watchdog_rss_limit_bytes") != COLD_LIMIT, "watchdog limit is not 2GB")
    _error(errors, compact.get("returncode") != 0, "watchdog worker returncode is not zero")
    _error(errors, compact.get("natural_exit") is not True, "watchdog natural_exit is not true")
    _error(errors, compact.get("no_orphan") is not True, "watchdog no_orphan is not true")
    _error(errors, compact.get("stop_reason") != "natural_exit", "watchdog stop reason is not natural_exit")
    rss: list[int] = []
    swaps: list[int] = []
    readable: list[bool] = []
    for row in samples:
        tree = row.get("authority", {}).get("process_tree", {})
        valid_rss = type(tree.get("rss_bytes")) is int and tree.get("rss_bytes", -1) >= 0
        valid_swap = type(tree.get("swap_bytes")) is int and tree.get("swap_bytes", -1) >= 0
        _error(errors, not valid_rss, "watchdog RSS sample invalid")
        _error(errors, not valid_swap, "watchdog swap sample invalid")
        if valid_rss:
            rss.append(int(tree["rss_bytes"]))
        if valid_swap:
            swaps.append(int(tree["swap_bytes"]))
        readable.append(tree.get("all_status_readable") is True)
    derived_peak, derived_swap = max(rss, default=-1), max(swaps, default=-1)
    derived_readable = bool(samples) and len(readable) == len(samples) and all(readable)
    _error(errors, compact.get("all_status_readable") != derived_readable, "watchdog readability is not raw-derived")
    _error(errors, compact.get("peak_process_tree_rss_bytes") != derived_peak, "watchdog peak RSS is not raw-derived")
    _error(errors, compact.get("max_process_tree_swap_bytes") != derived_swap, "watchdog swap is not raw-derived")
    _gate(gates, not derived_readable, "watchdog process-tree status unreadable")
    _gate(gates, derived_peak < 0 or derived_peak >= COLD_LIMIT, "cold process-tree RSS Gate failed")
    _gate(gates, derived_swap != 0, "cold process-tree swap Gate failed")
    retained_ns = record.get("retained_ready_wall_time_ns", -1)
    retained = [row for row in samples if isinstance(retained_ns, int) and int(row.get("wall_time_ns", -1)) >= retained_ns]
    _error(errors, not retained, "watchdog has no retained-window sample")
    retained_rss = [int(row.get("authority", {}).get("process_tree", {}).get("rss_bytes", -1)) for row in retained]
    retained_swap = [int(row.get("authority", {}).get("process_tree", {}).get("swap_bytes", -1)) for row in retained]
    retained_peak = max(retained_rss, default=-1)
    retained_max_swap = max(retained_swap, default=-1)
    _gate(gates, retained_peak < 0 or retained_peak >= RETAINED_LIMIT, "retained process-tree RSS Gate failed")
    _gate(gates, retained_max_swap != 0, "retained process-tree swap Gate failed")
    return {
        "source_sha": expected_sha, "sample_count": len(samples),
        "peak_process_tree_rss_bytes": derived_peak, "max_process_tree_swap_bytes": derived_swap,
        "retained_sample_count": len(retained), "retained_peak_process_tree_rss_bytes": retained_peak,
        "retained_peak_process_tree_swap_bytes": retained_max_swap,
        "natural_exit": compact.get("natural_exit"), "no_orphan": compact.get("no_orphan"),
        "all_status_readable": derived_readable, "stop_reason": compact.get("stop_reason"),
        "watchdog_poll_seconds": compact.get("watchdog_poll_seconds"),
        "watchdog_rss_limit_bytes": compact.get("watchdog_rss_limit_bytes"),
        "watchdog_compact": str(compact_path.resolve()), "watchdog_compact_sha256": _sha256(compact_path),
        "watchdog_raw": str(raw_path.resolve()), "watchdog_raw_sha256": raw_sha,
        "worker_command": record.get("command"),
    }


def _check_markers(raw_dir: Path, record: dict[str, Any], expected_sha: str, errors: list[str]) -> dict[str, int]:
    marker_info = record.get("markers", {})
    _error(errors, marker_info.get("names") != list(MARKERS), "marker list is not frozen")
    marker_dir = raw_dir / str(marker_info.get("relative_dir", ""))
    times: dict[str, int] = {}
    for name in MARKERS:
        path = marker_dir / f"{name}.json"
        _error(errors, not _inside(path, raw_dir), f"marker escapes raw_dir: {name}")
        _error(errors, not path.is_file(), f"marker missing: {name}")
        if not path.is_file():
            continue
        row = _read(path)
        _error(errors, row.get("marker") != name, f"marker name mismatch: {name}")
        _error(errors, row.get("source_sha") != expected_sha, f"marker source mismatch: {name}")
        times[name] = int(row.get("wall_time_ns", -1))
    values = [times.get(name, -1) for name in MARKERS]
    _error(errors, any(value < 0 for value in values) or values != sorted(values), "marker sequence is not monotonic")
    _error(errors, record.get("retained_ready_wall_time_ns") != times.get("retained_ready", -1), "retained_ready is not marker-bound")
    _error(errors, record.get("settings", {}).get("retained_dwell_seconds") != 2.0, "retained dwell is not 2 seconds")
    return times


def _check_action(label: str, data: dict[str, np.ndarray], facts: dict[str, Any], prefix: str,
                  degree: int, errors: list[str], gates: list[str]) -> dict[str, Any]:
    group = {name: _array(data, f"{prefix}{degree}_{name}", errors) for name in ("input", "out1", "out2")}
    if not _same_shape(group, errors, label):
        return {}
    x, y1, y2 = group["input"], group["out1"], group["out2"]
    assert x is not None and y1 is not None and y2 is not None
    diff, ref = float(np.linalg.norm(y2 - y1)), float(np.linalg.norm(y1))
    finite = bool(all(np.all(np.isfinite(value)) for value in group.values()))
    repeat = diff / max(ref, 1.0e-300)
    unchanged = _digest(x) == facts.get("input_before_digest") == facts.get("input_after_digest")
    _close(errors, diff, facts.get("diff_norm"), f"{label} diff_norm")
    _close(errors, ref, facts.get("ref_norm"), f"{label} ref_norm")
    _stored_bool(errors, facts, "finite", finite, f"{label} finite")
    _stored_bool(errors, facts, "input_unchanged", unchanged, f"{label} input_unchanged")
    _error(errors, facts.get("input_before_digest") != _digest(x) or facts.get("input_after_digest") != _digest(x), f"{label} input digest is not raw-bound")
    _gate(gates, not finite, f"{label} nonfinite")
    _gate(gates, repeat > REPEAT_LIMIT, f"{label} repeat failed")
    _gate(gates, not unchanged, f"{label} input changed")
    return {"repeat_relative": repeat, "finite": finite, "input_unchanged": unchanged}


def _check_probes(record: dict[str, Any], raw_dir: Path, errors: list[str], gates: list[str]) -> dict[str, Any]:
    descriptor = record.get("raw_artifacts", {}).get("probe_npz", {})
    path = raw_dir / str(descriptor.get("relative_path", ""))
    _error(errors, not _inside(path, raw_dir) or not path.is_file(), "probe artifact is missing/escaped")
    _error(errors, path.is_file() and _sha256(path) != descriptor.get("sha256"), "probe artifact SHA mismatch")
    if not path.is_file():
        return {}
    try:
        with np.load(path, allow_pickle=False) as loaded:
            data = {key: np.asarray(loaded[key]).copy() for key in loaded.files}
    except (OSError, ValueError, EOFError, KeyError) as exc:
        errors.append(f"probe artifact cannot be read: {exc}")
        return {}
    first = record.get("probes", {}).get("first", {})
    rebuild = record.get("probes", {}).get("rebuild", {})
    metrics: dict[str, Any] = {"actions": {}, "rebuild_actions": {}, "transfers": {}, "smoothers": {}}
    for degree in LEVELS:
        metrics["actions"][str(degree)] = _check_action(f"action {degree}", data, first.get("actions", {}).get(str(degree), {}), "a", degree, errors, gates)
    metrics["rebuild_actions"]["6"] = _check_action("rebuild action 6", data, rebuild.get("actions", {}).get("6", {}), "rebuild_a", 6, errors, gates)
    for pair in PAIRS:
        tag, pair_name = f"{pair[0]}{pair[1]}", f"{pair[0]}-{pair[1]}"
        names = ("x", "x2", "y", "px1", "px_repeat", "px2", "pcombo", "phy", "coarse_action", "fine_action")
        values = {name: _array(data, f"t{tag}_{name}", errors) for name in names}
        if any(value is None for value in values.values()):
            continue
        x, x2, y = values["x"], values["x2"], values["y"]
        px1, px_repeat, px2, pcombo = values["px1"], values["px_repeat"], values["px2"], values["pcombo"]
        phy, coarse_action, fine_action = values["phy"], values["coarse_action"], values["fine_action"]
        assert all(value is not None for value in values.values())
        if not _same_shape({"x": x, "x2": x2, "phy": phy, "coarse_action": coarse_action}, errors, f"transfer {pair_name} coarse"):
            continue
        if not _same_shape({"y": y, "px1": px1, "px_repeat": px_repeat, "px2": px2, "pcombo": pcombo, "fine_action": fine_action}, errors, f"transfer {pair_name} fine"):
            continue
        stored = first.get("transfers", {}).get(pair_name, {})
        repeat = float(np.linalg.norm(px_repeat - px1) / max(float(np.linalg.norm(px1)), 1.0e-300))
        linearity = float(np.linalg.norm(pcombo - ALPHA * px1 - BETA * px2) / max(float(np.linalg.norm(pcombo)), 1.0e-300))
        lhs, rhs = np.vdot(px1, y), np.vdot(x, phy)
        adjoint = float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1.0e-300))
        ec, ef = np.vdot(x, coarse_action), np.vdot(px1, fine_action)
        energy = float(abs(ef - ec) / max(abs(ec), 1.0e-300))
        finite = bool(all(np.all(np.isfinite(value)) for value in values.values()))
        unchanged = (_digest(x) == stored.get("x_before_digest") == stored.get("x_after_digest") and _digest(y) == stored.get("y_before_digest") == stored.get("y_after_digest"))
        for actual, key in ((repeat, "repeat_relative"), (linearity, "linearity_relative"), (adjoint, "adjoint_relative"), (energy, "energy_relative")):
            _close(errors, actual, stored.get(key), f"transfer {pair_name} {key}")
        _close_complex(errors, ec, stored.get("energy_coarse"), f"transfer {pair_name} energy_coarse")
        _close_complex(errors, ef, stored.get("energy_fine"), f"transfer {pair_name} energy_fine")
        _close(errors, max(abs(ec.imag), abs(ef.imag)), stored.get("energy_imag_defect"), f"transfer {pair_name} energy_imag_defect")
        _stored_bool(errors, stored, "finite", finite, f"transfer {pair_name} finite")
        _stored_bool(errors, stored, "input_unchanged", unchanged, f"transfer {pair_name} input_unchanged")
        _error(errors, stored.get("x_before_digest") != _digest(x) or stored.get("x_after_digest") != _digest(x) or stored.get("y_before_digest") != _digest(y) or stored.get("y_after_digest") != _digest(y), f"transfer {pair_name} input digest is not raw-bound")
        _gate(gates, not finite, f"transfer {pair_name} nonfinite")
        _gate(gates, repeat > REPEAT_LIMIT, f"transfer {pair_name} repeat failed")
        _gate(gates, linearity > LINEARITY_LIMIT, f"transfer {pair_name} linearity failed")
        _gate(gates, adjoint > ADJOINT_LIMIT, f"transfer {pair_name} adjoint failed")
        _gate(gates, energy > ENERGY_LIMIT, f"transfer {pair_name} energy failed")
        _gate(gates, not unchanged, f"transfer {pair_name} input changed")
        local = record.get("architecture", {}).get("transfers", {}).get(pair_name, {}).get("local_transfer", {})
        for key, limit in (("edge_line_integral_relative", LOCAL_LIMIT), ("curl_flux_relative", LOCAL_LIMIT), ("gradient_commuting_relative", LOCAL_LIMIT), ("adjoint_work_relative", ADJOINT_LIMIT), ("linearity_relative", LINEARITY_LIMIT), ("repeat_relative", REPEAT_LIMIT)):
            _gate(gates, not _finite_number(local.get(key)) or float(local.get(key)) > limit, f"local transfer {pair_name} {key} failed")
        _error(errors, local.get("finite") is not True or local.get("input_unchanged") is not True, f"local transfer {pair_name} finite/input facts missing")
        _error(errors, local.get("line_integral_histopolation") is not True or local.get("simple_injection") is not False, f"local transfer {pair_name} interpolation identity mismatch")
        metrics["transfers"][pair_name] = {"repeat_relative": repeat, "linearity_relative": linearity, "adjoint_relative": adjoint, "energy_relative": energy, "finite": finite}
    for degree in (6, 3):
        values = {name: _array(data, f"s{degree}_{name}", errors) for name in ("rhs", "out1", "out2")}
        if not _same_shape(values, errors, f"smoother {degree}"):
            continue
        rhs, out1, out2 = values["rhs"], values["out1"], values["out2"]
        assert rhs is not None and out1 is not None and out2 is not None
        stored = first.get("smoothers", {}).get(str(degree), {})
        repeat = float(np.linalg.norm(out2 - out1) / max(float(np.linalg.norm(out1)), 1.0e-300))
        finite = bool(np.all(np.isfinite(out1)) and np.all(np.isfinite(out2)))
        unchanged = _digest(rhs) == stored.get("input_before_digest") == stored.get("input_after_digest")
        _close(errors, repeat, stored.get("repeat_relative"), f"smoother {degree} repeat")
        _stored_bool(errors, stored, "finite", finite, f"smoother {degree} finite")
        _stored_bool(errors, stored, "input_unchanged", unchanged, f"smoother {degree} input_unchanged")
        _error(errors, stored.get("input_before_digest") != _digest(rhs) or stored.get("input_after_digest") != _digest(rhs), f"smoother {degree} input digest is not raw-bound")
        _gate(gates, repeat > REPEAT_LIMIT, f"smoother {degree} repeat failed")
        _gate(gates, not finite, f"smoother {degree} nonfinite")
        _gate(gates, not unchanged, f"smoother {degree} input changed")
        metrics["smoothers"][str(degree)] = {"repeat_relative": repeat, "finite": finite}
    return metrics


def _scan_fingerprint(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text in FINGERPRINT_BANNED_KEYS:
                errors.append(f"fingerprint contains non-semantic field: {path}.{key_text}")
            _scan_fingerprint(child, f"{path}.{key_text}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_fingerprint(child, f"{path}[{index}]", errors)


def _check_semantic_tree(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, dict) or not _hex(value.get("sha256"), 64):
        errors.append(f"fingerprint semantic tree is missing/invalid: {path}")
        return False
    kind = value.get("kind")
    valid = True
    if kind == "mapping":
        valid = set(value) == {"kind", "entries", "sha256"} and isinstance(value.get("entries"), list)
        entries = value.get("entries", [])
        keys = [entry.get("key") for entry in entries if isinstance(entry, dict)]
        valid = valid and len(keys) == len(entries) and all(isinstance(key, str) for key in keys)
        valid = valid and keys == sorted(keys) and len(set(keys)) == len(keys)
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != {"key", "child"}:
                errors.append(f"fingerprint mapping entry is invalid: {path}[{index}]")
                valid = False
                continue
            valid = _check_semantic_tree(entry["child"], f"{path}.entries[{index}].child", errors) and valid
    elif kind == "sequence":
        children = value.get("children")
        valid = set(value) == {"kind", "children", "sha256"} and isinstance(children, list)
        if isinstance(children, list):
            for index, child in enumerate(children):
                valid = _check_semantic_tree(child, f"{path}.children[{index}]", errors) and valid
    elif kind == "ndarray":
        shape = value.get("shape")
        valid = set(value) == {"kind", "dtype", "shape", "data_sha256", "sha256"}
        valid = valid and isinstance(value.get("dtype"), str) and "object" not in value["dtype"]
        valid = valid and isinstance(shape, list) and all(type(item) is int and item >= 0 for item in shape)
        valid = valid and _hex(value.get("data_sha256"), 64)
    elif kind == "scalar":
        scalar = value.get("value")
        valid = set(value) == {"kind", "type", "value", "sha256"}
        valid = valid and isinstance(value.get("type"), str)
        valid = valid and (scalar is None or isinstance(scalar, (str, bool, int, float)))
    else:
        errors.append(f"fingerprint semantic tree kind is invalid: {path}")
        valid = False
    if valid:
        body = {key: child for key, child in value.items() if key != "sha256"}
        if value["sha256"] != _semantic_sha256(body):
            errors.append(f"fingerprint semantic tree sha is not child-bound: {path}")
            valid = False
    return valid


def _check_fingerprint_shape(payload: dict[str, Any], label: str, errors: list[str]) -> None:
    levels = payload.get("levels")
    _error(errors, not isinstance(levels, dict) or set(levels) != {str(d) for d in LEVELS}, f"fingerprint {label} levels are incomplete")
    if isinstance(levels, dict):
        for degree in LEVELS:
            level = levels.get(str(degree), {})
            _error(errors, not isinstance(level, dict), f"fingerprint {label} level {degree} is invalid")
            if not isinstance(level, dict):
                continue
            _error(errors, level.get("degree") != degree, f"fingerprint {label} level {degree} degree is invalid")
            matrix = level.get("matrix", {})
            _error(errors, not isinstance(matrix, dict) or any(key not in matrix for key in MATRIX_FACTS), f"fingerprint {label} level {degree} matrix is incomplete")
            for key in ("parent_inventory", "raw_inventory"):
                required = PARENT_INVENTORY if key == "parent_inventory" else RAW_INVENTORY
                value = level.get(key)
                _error(errors, not isinstance(value, dict) or any(item not in value for item in required), f"fingerprint {label} level {degree} {key} is incomplete")
            for key in ("parent_topology", "raw_topology"):
                value = level.get(key)
                _error(errors, not isinstance(value, dict) or any(item not in value for item in TOPOLOGY_FACTS), f"fingerprint {label} level {degree} {key} is incomplete")
            for key in ("parent_topology_arrays", "raw_topology_arrays", "raw_map_arrays", "raw_permutations", "incidence_unique"):
                _check_semantic_tree(level.get(key), f"fingerprint.{label}.levels.{degree}.{key}", errors)
    transfers = payload.get("transfers")
    _error(errors, not isinstance(transfers, dict) or set(transfers) != {"6-3", "3-1"}, f"fingerprint {label} transfers are incomplete")
    if isinstance(transfers, dict):
        for name in ("6-3", "3-1"):
            transfer = transfers.get(name, {})
            _error(errors, not isinstance(transfer, dict), f"fingerprint {label} transfer {name} is invalid")
            if not isinstance(transfer, dict):
                continue
            local = transfer.get("local_map")
            _error(errors, not isinstance(local, dict) or any(key not in local for key in LOCAL_MAP_FACTS), f"fingerprint {label} transfer {name} map is incomplete")
            legality = transfer.get("local_legality")
            _error(errors, not isinstance(legality, dict) or any(key not in legality for key in LOCAL_LEGALITY_FACTS), f"fingerprint {label} transfer {name} legality is incomplete")
            _error(errors, transfer.get("pair") != list(PAIRS[0] if name == "6-3" else PAIRS[1]), f"fingerprint {label} transfer {name} pair is invalid")
            for key in ("edge_transfer", "node_transfer"):
                _check_semantic_tree(transfer.get(key), f"fingerprint.{label}.transfers.{name}.{key}", errors)
    smoothers = payload.get("smoothers")
    _error(errors, not isinstance(smoothers, dict) or set(smoothers) != {"6", "3"}, f"fingerprint {label} smoothers are incomplete")
    if isinstance(smoothers, dict):
        for degree in (6, 3):
            facts = smoothers.get(str(degree), {})
            _error(errors, not isinstance(facts, dict) or any(key not in facts for key in ("degree", "fixed_degree", "power_steps", "pre_sweeps", "post_sweeps", "lambda_power10", "lambda_hi", "lambda_lo")), f"fingerprint {label} smoother {degree} is incomplete")


def _compare_fields(errors: list[str], actual: Any, expected: Any, fields: tuple[str, ...], label: str) -> None:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        errors.append(f"fingerprint {label} architecture binding is missing")
        return
    for field in fields:
        if field not in actual or field not in expected or actual[field] != expected[field]:
            errors.append(f"fingerprint {label} does not match architecture: {field}")


def _check_fingerprint_architecture(payload: dict[str, Any], architecture: dict[str, Any], label: str, errors: list[str]) -> None:
    levels = payload.get("levels", {})
    architecture_levels = architecture.get("levels", {})
    for degree in LEVELS:
        actual = levels.get(str(degree), {})
        expected = architecture_levels.get(str(degree), {})
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            errors.append(f"fingerprint {label} level {degree} architecture binding is missing")
            continue
        _compare_fields(errors, actual, expected, ("degree",), f"{label} level {degree}")
        _compare_fields(errors, actual.get("matrix"), expected.get("matrix"), MATRIX_FACTS, f"{label} level {degree} matrix")
        _compare_fields(errors, actual.get("parent_inventory"), expected, PARENT_INVENTORY, f"{label} level {degree} parent inventory")
        _compare_fields(errors, actual.get("raw_inventory"), expected, RAW_INVENTORY, f"{label} level {degree} raw inventory")
        for topology_name in ("parent_topology", "raw_topology"):
            _compare_fields(errors, actual.get(topology_name), expected.get(topology_name), TOPOLOGY_FACTS, f"{label} level {degree} {topology_name}")
    transfers = payload.get("transfers", {})
    architecture_transfers = architecture.get("transfers", {})
    for name in ("6-3", "3-1"):
        actual = transfers.get(name, {})
        expected = architecture_transfers.get(name, {})
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            errors.append(f"fingerprint {label} transfer {name} architecture binding is missing")
            continue
        _compare_fields(errors, actual, expected, ("pair",), f"{label} transfer {name}")
        _compare_fields(errors, actual.get("local_map"), expected.get("local_map"), LOCAL_MAP_FACTS, f"{label} transfer {name} local map")
        _compare_fields(errors, actual.get("local_legality"), expected.get("local_transfer"), LOCAL_LEGALITY_FACTS, f"{label} transfer {name} local legality")
        arrays = expected.get("local_transfer_arrays", {})
        _compare_fields(errors, actual, arrays, ("edge_transfer", "node_transfer"), f"{label} transfer {name} array descriptors")
    smoothers = payload.get("smoothers", {})
    architecture_smoothers = architecture.get("smoothers", {})
    for degree in (6, 3):
        actual = smoothers.get(str(degree), {})
        expected = architecture_smoothers.get(str(degree), {})
        _compare_fields(errors, actual, expected, ("degree", "fixed_degree", "power_steps", "pre_sweeps", "post_sweeps", "lambda_power10", "lambda_hi", "lambda_lo"), f"{label} smoother {degree}")


def _check_fingerprint(record: dict[str, Any], architecture: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    fingerprint = record.get("fingerprint", {})
    first, rebuild = fingerprint.get("first"), fingerprint.get("rebuild")
    valid = isinstance(first, dict) and isinstance(rebuild, dict)
    _error(errors, not valid, "fingerprint first/rebuild payloads are missing")
    if not valid:
        return {}
    payloads: dict[str, dict[str, Any]] = {}
    for name, facts in (("first", first), ("rebuild", rebuild)):
        payload, sha = facts.get("payload"), facts.get("sha256")
        _error(errors, not isinstance(payload, dict) or not _hex(sha, 64), f"fingerprint {name} format is invalid")
        if isinstance(payload, dict) and _hex(sha, 64):
            _check_fingerprint_shape(payload, name, errors)
            _scan_fingerprint(payload, f"fingerprint.{name}", errors)
            _error(errors, sha != _semantic_sha256(payload), f"fingerprint {name} is not payload-bound")
            _check_fingerprint_architecture(payload, architecture, name, errors)
            payloads[name] = payload
    if set(payloads) == {"first", "rebuild"}:
        same = payloads["first"] == payloads["rebuild"]
        _gate(gates, not same, "first/rebuild semantic fingerprint differs")
        _error(errors, fingerprint.get("exact_identity") is not same, "fingerprint exact_identity is not derived")
    return {"first_sha256": first.get("sha256"), "rebuild_sha256": rebuild.get("sha256"), "exact_identity": fingerprint.get("exact_identity")}


def _check_record(record_path: Path, watchdog_path: Path, expected_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record = _read(record_path)
    raw_dir = Path(record.get("raw_dir", ""))
    _error(errors, not _hex(expected_sha, 40), "expected source SHA format invalid")
    _error(errors, record.get("schema") != SCHEMA, "record schema mismatch")
    _error(errors, record.get("stage") != "s5" or record.get("case") != CASE, "stage/case mismatch")
    _error(errors, record.get("degree") != 6 or record.get("h_nm") != 10.0 or record.get("wavelength_nm") != 13.5, "fixed p6/h10 identity mismatch")
    _error(errors, record.get("mpi_size") != 1, "S5 requires MPI1")
    _error(errors, not raw_dir.is_absolute() or not raw_dir.is_dir(), "raw_dir is missing/relative")
    _error(errors, Path(record.get("record_path", "")).resolve() != record_path.resolve(), "record path is not self-bound")
    _error(errors, any(key in record for key in ("passed", "gates", "classification")), "worker record contains checker status")
    command = record.get("command")
    expected_input = (Path(__file__).resolve().parents[1] / TEMPLATE_RELATIVE_PATH).resolve()
    expected_tail = ["-m", MODULE, "--stage", "s5", "--case", CASE, "--raw-dir", str(raw_dir.resolve()), "--record", str(record_path.resolve()), "--expected-source-sha", expected_sha, "--expected-mpi-size", "1", "--input", str(expected_input)]
    _error(errors, not isinstance(command, list) or not command or not Path(str(command[0])).is_absolute(), "worker command is not absolute")
    if isinstance(command, list) and command:
        _error(errors, command[1:] != expected_tail, "worker command argv is not exact")
    source = record.get("source", {})
    for side in ("start", "end"):
        facts = source.get(side, {})
        _error(errors, facts.get("expected_sha") != expected_sha or facts.get("commit_sha") != expected_sha, f"source {side} SHA mismatch")
        _error(errors, not _hex(facts.get("commit_sha"), 40), f"source {side} SHA format invalid")
        _error(errors, facts.get("branch") != BRANCH or facts.get("clean") is not True, f"source {side} is not closed")
    runtime = record.get("runtime", {})
    _error(errors, runtime.get("qualified_activation") != "1" or runtime.get("mpi_size") != 1, "runtime qualification mismatch")
    _error(errors, runtime.get("petsc_scalar_type") != "<class 'numpy.complex128'>" or runtime.get("petsc_int_type") != "<class 'numpy.int32'>", "runtime ABI mismatch")
    if isinstance(command, list) and command:
        _error(errors, runtime.get("sys_executable") != command[0], "runtime executable mismatch")
    identity = record.get("input_identity", {})
    _error(errors, identity.get("path_absolute") != str(expected_input), "input absolute path mismatch")
    _error(errors, identity.get("path_relative") != TEMPLATE_RELATIVE_PATH or identity.get("raw_bytes") != EXPECTED_INPUT_BYTES or identity.get("raw_sha256") != EXPECTED_INPUT_SHA256 or identity.get("resolved_bytes") != EXPECTED_RESOLVED_BYTES or identity.get("resolved_sha256") != EXPECTED_RESOLVED_SHA256 or identity.get("physical_model_sha256") != EXPECTED_PHYSICAL_MODEL_SHA256, "frozen input identity mismatch")
    for key in ("raw_sha256", "resolved_sha256", "physical_model_sha256"):
        _error(errors, not _hex(identity.get(key), 64), f"input identity hash is invalid: {key}")
    provenance = record.get("provenance", {})
    _error(errors, provenance.get("source_sha") != expected_sha or provenance.get("branch") != BRANCH, "provenance source is not closed")
    for key in ("input_sha256", "resolved_sha256", "physical_model_sha256"):
        expected = identity.get("raw_sha256" if key == "input_sha256" else key)
        _error(errors, provenance.get(key) != expected or not _hex(provenance.get(key), 64), f"provenance hash is invalid: {key}")
    settings = record.get("settings", {})
    _error(errors, settings.get("levels") != list(LEVELS) or settings.get("pairs") != [list(p) for p in PAIRS], "level/pair settings mismatch")
    _error(errors, settings.get("chebyshev_degree") != 3 or settings.get("power_steps") != 10 or settings.get("pre_sweeps") != 1 or settings.get("post_sweeps") != 1 or settings.get("retained_dwell_seconds") != 2.0, "fixed settings mismatch")
    reserve = record.get("reserve", {})
    _error(errors, reserve.get("basis_count") != 21 or reserve.get("auxiliary_vector_count") != 4 or reserve.get("vector_count") != 25 or reserve.get("touched") is not True, "restart reserve facts missing")
    _error(errors, not _positive_int(reserve.get("local_entries_per_vector")) or reserve.get("local_numeric_bytes") != reserve.get("vector_count", 0) * reserve.get("local_entries_per_vector", 0) * 16, "restart reserve byte facts do not close")
    architecture = record.get("architecture", {})
    forbidden = architecture.get("forbidden", {})
    forbidden_sources = architecture.get("forbidden_sources", {})
    for key in FORBIDDEN_FACTS:
        _error(errors, key not in forbidden or forbidden[key] is not False, f"forbidden architecture fact is not false: {key}")
        _error(errors, not isinstance(forbidden_sources, dict) or not isinstance(forbidden_sources.get(key), str), f"forbidden architecture source is missing: {key}")
    level_facts = architecture.get("levels", {})
    _error(errors, set(level_facts) != {str(d) for d in LEVELS}, "level architecture inventory is incomplete")
    for degree in LEVELS:
        level = level_facts.get(str(degree), {})
        for key in ("parent_local_owned_rows", "parent_local_unique_rows", "parent_global_unique_rows", "raw_local_owned_rows", "raw_local_unique_rows", "raw_global_unique_rows", "parent_cell_count_local"):
            _error(errors, not _positive_int(level.get(key)), f"level {degree} owner/topology fact missing: {key}")
        _error(errors, level.get("owner_route") != "typed_complex128_alltoallv", f"level {degree} owner route mismatch")
        matrix = level.get("matrix", {})
        for key in ("rows", "cols", "nnz", "index_bytes", "numeric_bytes"):
            _error(errors, not _positive_int(matrix.get(key)), f"level {degree} matrix fact missing: {key}")
        _error(errors, not isinstance(matrix.get("type"), str) or not matrix.get("type"), f"level {degree} matrix fact missing: type")
        _error(errors, matrix.get("rows") != matrix.get("cols"), f"level {degree} matrix is not square")
        _error(errors, level.get("topology_inventory_closed") is not True, f"level {degree} topology inventory not closed")
        topology_values: dict[str, dict[str, Any]] = {}
        for topo_name in ("parent_topology", "raw_topology"):
            topo = level.get(topo_name, {})
            _error(errors, not isinstance(topo, dict), f"level {degree} {topo_name} facts missing")
            for key in TOPOLOGY_FACTS:
                _error(errors, key not in topo, f"level {degree} {topo_name} missing: {key}")
            if isinstance(topo, dict):
                topology_values[topo_name] = topo
                _error(errors, topo.get("owner_local_maps") is not True or topo.get("numeric_allgather") is not False or topo.get("global_transfer_matrix") is not False, f"level {degree} {topo_name} route facts invalid")
                _error(errors, topo.get("phase_application") != "once_in_canonical_owner_route", f"level {degree} {topo_name} phase application invalid")
                _error(errors, topo.get("edge_orientation") != "dolfinx_cell_permutation_Tt_then_T" or topo.get("cell_permutation") != "Tt_before_high_to_lor_and_T_after_lor_to_high" or topo.get("floquet_phase") != "complete_slave_edge_mapped_to_master_once", f"level {degree} {topo_name} orientation/phase facts invalid")
                _error(errors, topo.get("slave_master_complete") is not True, f"level {degree} {topo_name} slave closure invalid")
                _error(errors, topo.get("global_unique_edge_count") != level.get("parent_global_unique_rows" if topo_name == "parent_topology" else "raw_global_unique_rows"), f"level {degree} {topo_name} global inventory mismatch")
                prefix = "parent" if topo_name == "parent_topology" else "raw"
                _error(errors, topo.get("owned_unique_edge_count") != level.get(f"{prefix}_local_owned_rows") or topo.get("local_unique_edge_count") != level.get(f"{prefix}_local_unique_rows"), f"level {degree} {topo_name} local inventory mismatch")
        if len(topology_values) == 2:
            _error(errors, topology_values["parent_topology"]["global_unique_edge_count"] != topology_values["raw_topology"]["global_unique_edge_count"], f"level {degree} parent/raw global inventory differs")
    transfer_facts = architecture.get("transfers", {})
    _error(errors, set(transfer_facts) != {"6-3", "3-1"}, "transfer inventory is incomplete")
    for name in ("6-3", "3-1"):
        transfer = transfer_facts.get(name, {})
        local = transfer.get("local_map", {})
        for key in LOCAL_MAP_FACTS:
            _error(errors, not _positive_int(local.get(key)), f"transfer {name} local map missing: {key}")
        _error(errors, transfer.get("global_transfer_matrix") is not False or transfer.get("numeric_allgather") is not False, f"transfer {name} is not implicit")
        _check_structural_local_legality(
            transfer.get("local_transfer"),
            f"transfer {name}",
            errors,
        )
        arrays = transfer.get("local_transfer_arrays", {})
        _error(errors, not isinstance(arrays, dict), f"transfer {name} local array descriptors are missing")
        if isinstance(arrays, dict):
            for array_name in ("edge_transfer", "node_transfer"):
                _error(errors, not isinstance(arrays.get(array_name), dict), f"transfer {name} local array descriptor is missing: {array_name}")
    smoothers = architecture.get("smoothers", {})
    for degree in (6, 3):
        facts = smoothers.get(str(degree), {})
        _error(errors, facts.get("fixed_degree") != 3 or facts.get("power_steps") != 10 or facts.get("pre_sweeps") != 1 or facts.get("post_sweeps") != 1, f"smoother {degree} settings mismatch")
        _error(errors, not all(_finite_number(facts.get(key)) and float(facts.get(key)) > 0.0 for key in ("lambda_power10", "lambda_hi", "lambda_lo")), f"smoother {degree} spectral facts invalid")
        _error(errors, facts.get("power_matrix_mult_count") != 20 or not _positive_int(facts.get("matrix_mult_count")), f"smoother {degree} action counts are not measured")
    budget = architecture.get("p1_coarse_budget", {})
    _error(errors, budget.get("status") != "derived_estimate_only" or budget.get("solver_selected") is not False or budget.get("direct_factor_built") is not False, "p1 coarse budget selected a solver/factor")
    for key in ("matrix_payload_bytes", "fixed_work_vector_count", "fixed_work_vector_bytes", "petsc_overhead_bytes", "estimated_total_bytes"):
        _error(errors, type(budget.get(key)) is not int or budget.get(key) < 0, f"p1 budget field invalid: {key}")
    if all(type(budget.get(key)) is int and budget.get(key) >= 0 for key in ("matrix_payload_bytes", "fixed_work_vector_bytes", "petsc_overhead_bytes", "estimated_total_bytes")):
        _error(errors, budget.get("fixed_work_vector_count") != 8, "p1 budget work-vector count is not 8")
        _error(errors, budget["estimated_total_bytes"] != budget["matrix_payload_bytes"] + budget["fixed_work_vector_bytes"] + budget["petsc_overhead_bytes"], "p1 budget arithmetic is not closed")
    _check_markers(raw_dir, record, expected_sha, errors)
    probes = _check_probes(record, raw_dir, errors, gates)
    fingerprint = _check_fingerprint(record, architecture, errors, gates)
    retained = record.get("retained", {})
    known = retained.get("known_bytes", {})
    _error(errors, not isinstance(known, dict), "combined retained ledger is missing")
    if isinstance(known, dict):
        values = []
        for key, value in known.items():
            if key == "mesh_space_mpc_known_array_bytes":
                _error(errors, value is not None, "mesh/space/MPC known array bytes must be null")
            else:
                _error(errors, type(value) is not int or value < 0, f"retained ledger value is invalid: {key}")
                if type(value) is int and value >= 0:
                    values.append(value)
        _error(errors, sum(values) != retained.get("known_total_bytes"), "retained ledger sum mismatch")
    measured = retained.get("measured_process_tree_rss_bytes", -1)
    resource_rss = retained.get("resource", {}).get("process_tree", {}).get("rss_bytes", -2)
    _error(errors, not isinstance(measured, int) or measured < 0 or measured != resource_rss, "retained RSS is not resource-bound")
    _error(errors, retained.get("unattributed_remainder_bytes") != measured - retained.get("known_total_bytes", 0), "retained unattributed remainder mismatch")
    _error(errors, retained.get("unattributed_remainder_bytes", -1) < 0, "retained ledger exceeds measured RSS")
    _error(errors, retained.get("level6_foundation_ledger_included_once") is not True, "level6 foundation ownership is not explicit")
    _error(errors, retained.get("bounded_temporary_bytes", {}).get("included_in_known_total") is not False, "temporary workspace is counted as retained")
    watchdog = _check_watchdog(watchdog_path, record, record_path, expected_sha, errors, gates)
    classification = "CONTRACT_INVALID" if errors else "RESOURCE_OR_ALGEBRA_GATE_FAILED" if gates else "P6_LOR_EDGE_HIERARCHY_RESOURCE_PASS_WITH_COARSE_SOLVER_OPEN"
    return {
        "schema": CHECK_SCHEMA, "passed": not errors and not gates,
        "contract_errors": errors, "gate_failures": gates, "classification": classification,
        "metrics": {"probe_metrics": probes, "fingerprint": fingerprint, "retained_known_bytes": retained.get("known_total_bytes"), "retained_unattributed_bytes": retained.get("unattributed_remainder_bytes")},
        "resource": watchdog,
    }


def check_record(record_path: Path, watchdog_path: Path, expected_sha: str) -> dict[str, Any]:
    try:
        return _check_record(record_path.resolve(), watchdog_path.resolve(), expected_sha)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {"schema": CHECK_SCHEMA, "passed": False, "contract_errors": [f"CONTRACT_INVALID: {exc}"], "gate_failures": [], "classification": "CONTRACT_INVALID", "metrics": {}, "resource": {}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    result = check_record(args.record, args.watchdog_compact, args.expected_source_sha)
    _write(args.output, result)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
