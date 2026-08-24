"""Independent JSON/raw checker for the V11 S2 memory-first foundation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.full3d.lor-memory-first.s2-foundation.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_lor_s2_memory_first"
CASE = "p6-h10-mpi1"
APPLY_NAMES = (
    "high_positive",
    "physical_volume_dtn",
    "restrict_high_to_lor",
    "lor_edge_matvec",
    "lift_lor_to_high",
)
REPEAT_COUNT = 10
RESERVE_COUNT = 25
COLD_LIMIT = 1_800_000_000
RETAINED_LIMIT = 1_550_000_000
GROWTH_LIMIT = 32_000_000
TRANSFER_SCRATCH = 1_053_696
RETAINED_DWELL_SECONDS = 2.0
REPEAT_NORM_TOL = 1.0e-13
TEMPLATE_RELATIVE_PATH = "input/templates/full3d_iterative_example.dat"
EXPECTED_INPUT_BYTES = 2119
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_BYTES = 4076
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
SETUP_RESOURCE_STAGES = (
    "start",
    "high_mesh_space_mpc",
    "high_actions",
    "low_mesh_space_mpc",
    "low_matrix_transfer_topology_work",
)
FORBIDDEN_ARCHITECTURE = (
    "scalar_node_matrix_built",
    "hx_hierarchy_built",
    "pcgamg_hierarchy_built",
    "p6_exact_edge_factor_built",
    "global_direct_coarse_built",
    "recovery_field_arrays_built",
    "global_high_order_aij",
    "global_dense_transfer",
    "global_numeric_allgather",
    "numeric_allgather",
    "hx_or_node_action_built",
    "production_local_spectral_built",
)
REQUIRED_NESTED_FIELDS = {
    "high_positive_action": {
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "dense_cell_tensor_materialized_per_apply": False,
        "retained_dense_cell_tensor_count": 0,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "factor_count": 0,
        "ksp_created": False,
        "numeric_allgather": False,
    },
    "physical_action": {
        "global_aij_materialized": False,
        "global_schur_materialized": False,
        "ksp_created": False,
        "numeric_allgather": False,
    },
    "physical_action.volume_action": {
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "dense_cell_tensor_materialized_per_apply": False,
        "retained_dense_cell_tensor_count": 0,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "factor_count": 0,
        "ksp_created": False,
        "numeric_allgather": False,
    },
    "physical_action.dtn_action": {
        "global_aij_materialized": False,
        "global_schur_materialized": False,
        "trace_matrix_materialized": False,
        "ksp_created": False,
        "numeric_allgather": False,
        "explicit_c_matrix_count": 0,
        "explicit_d_matrix_count": 0,
    },
}
MARKERS = (
    "paths_ready",
    "source_runtime_closed",
    "fixture_built",
    "reserve_built",
    "apply_ledger_written",
    "retained_ready",
    "record_written",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _loads_strict(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_json_constant)


def _read(path: Path) -> Any:
    return _loads_strict(path.read_text(encoding="utf-8"))


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


def _finite_number(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _check_nested_forbidden(
    errors: list[str], label: str, facts: Any, required: dict[str, Any]
) -> None:
    if not isinstance(facts, dict):
        errors.append(f"{label} audit is missing")
        return
    for key, expected in required.items():
        _error(errors, key not in facts, f"{label}.{key} is missing")
        if key in facts:
            _error(errors, facts[key] != expected, f"{label}.{key} is not frozen")


def _check_setup_resources(errors: list[str], architecture: dict[str, Any]) -> None:
    rows = architecture.get("setup_resources")
    _error(errors, not isinstance(rows, list), "setup resource snapshots are missing")
    if not isinstance(rows, list):
        return
    _error(
        errors,
        [row.get("stage") for row in rows] != list(SETUP_RESOURCE_STAGES),
        "setup resource stage sequence is not frozen",
    )
    previous = None
    for index, row in enumerate(rows):
        tree = row.get("process_tree", {}) if isinstance(row, dict) else {}
        rss = tree.get("rss_bytes")
        swap = tree.get("swap_bytes")
        _error(errors, not isinstance(rss, int) or rss < 0, f"setup resource RSS missing at stage {index}")
        _error(errors, not isinstance(swap, int) or swap < 0, f"setup resource swap missing at stage {index}")
        _error(errors, tree.get("all_status_readable") is not True, f"setup resource status unreadable at stage {index}")
        if index and "rss_delta_bytes" not in row:
            errors.append(f"setup resource RSS delta missing at stage {index}")
        if previous is not None and isinstance(rss, int):
            _error(
                errors,
                int(row.get("rss_delta_bytes", rss - previous)) != rss - previous,
                f"setup resource RSS delta mismatch at stage {index}",
            )
        if isinstance(rss, int):
            previous = rss


def _check_watchdog(
    compact_path: Path,
    record: dict[str, Any],
    expected_sha: str,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    compact = _read(compact_path)
    _error(errors, compact.get("schema") != WATCHDOG_SCHEMA, "watchdog schema mismatch")
    _error(errors, compact.get("source_sha") != expected_sha, "watchdog source SHA mismatch")
    command = record.get("command")
    _error(errors, compact.get("worker_command") != command, "watchdog and record command differ")
    _error(errors, Path(compact.get("worker_raw_dir", "")).resolve() != Path(record.get("raw_dir", "")).resolve(), "watchdog raw_dir differs")
    _error(errors, Path(compact.get("worker_record", "")).resolve() != Path(record.get("record_path", "")).resolve(), "watchdog record path differs")
    raw_path = Path(compact.get("watchdog_raw", ""))
    _error(errors, not raw_path.is_absolute(), "watchdog raw path is not absolute")
    _error(errors, not raw_path.is_file(), "watchdog raw ledger is missing")
    raw_digest = _sha256(raw_path) if raw_path.is_file() else ""
    _error(errors, raw_digest != compact.get("raw_sha256"), "watchdog raw SHA mismatch")
    samples: list[dict[str, Any]] = []
    if raw_path.is_file():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                samples.append(_loads_strict(line))
    _error(errors, len(samples) != int(compact.get("sample_count", -1)), "watchdog sample_count does not match raw")
    _error(errors, int(compact.get("returncode", -1)) != 0, "watchdog returncode is not zero")
    _error(errors, compact.get("natural_exit") is not True, "watchdog natural_exit is not true")
    _error(errors, compact.get("no_orphan") is not True, "watchdog no_orphan is not true")
    _error(errors, compact.get("all_status_readable") is not True, "watchdog status readability is false")
    _error(errors, compact.get("stop_reason") != "natural_exit", "watchdog stop reason is not natural_exit")
    rss = [
        int(row["authority"]["process_tree"]["rss_bytes"])
        for row in samples
        if "authority" in row and "process_tree" in row["authority"]
    ]
    swaps = [
        int(row["authority"]["process_tree"]["swap_bytes"])
        for row in samples
        if "authority" in row and "process_tree" in row["authority"]
    ]
    derived_readable = bool(samples) and all(
        bool(row.get("authority", {}).get("process_tree", {}).get("all_status_readable", False))
        for row in samples
    )
    _error(
        errors,
        compact.get("all_status_readable") is not derived_readable,
        "watchdog status readability is not raw-derived",
    )
    derived_peak = max(rss, default=-1)
    derived_swap = max(swaps, default=-1)
    _error(errors, int(compact.get("peak_process_tree_rss_bytes", -1)) != derived_peak, "watchdog peak RSS is not raw-derived")
    _error(errors, int(compact.get("max_process_tree_swap_bytes", -1)) != derived_swap, "watchdog swap is not raw-derived")
    _error(errors, int(compact.get("watchdog_rss_limit_bytes", -1)) != COLD_LIMIT, "watchdog RSS limit is not 1.8GB")
    _gate(gates, derived_peak < 0 or derived_peak >= COLD_LIMIT, "cold process-tree RSS Gate failed")
    _gate(gates, derived_swap != 0, "cold process-tree swap Gate failed")
    retained_ready_ns = int(record.get("retained_ready_wall_time_ns", -1))
    retained_samples = [
        row
        for row in samples
        if int(row.get("wall_time_ns", -1)) >= retained_ready_ns
    ]
    _error(
        errors,
        retained_ready_ns < 0,
        "retained_ready_wall_time_ns is missing",
    )
    _error(
        errors,
        not retained_samples,
        "watchdog has no retained-window samples after retained_ready",
    )
    retained_rss = [
        int(row["authority"]["process_tree"]["rss_bytes"])
        for row in retained_samples
        if "authority" in row and "process_tree" in row["authority"]
    ]
    retained_swaps = [
        int(row["authority"]["process_tree"]["swap_bytes"])
        for row in retained_samples
        if "authority" in row and "process_tree" in row["authority"]
    ]
    retained_peak = max(retained_rss, default=-1)
    retained_swap = max(retained_swaps, default=-1)
    _gate(
        gates,
        retained_peak < 0 or retained_peak > RETAINED_LIMIT,
        "external retained process-tree RSS Gate failed",
    )
    _gate(
        gates,
        retained_swap != 0,
        "external retained process-tree swap Gate failed",
    )
    return {
        "source_sha": expected_sha,
        "sample_count": len(samples),
        "peak_process_tree_rss_bytes": derived_peak,
        "max_process_tree_swap_bytes": derived_swap,
        "retained_sample_count": len(retained_samples),
        "retained_peak_process_tree_rss_bytes": retained_peak,
        "retained_peak_process_tree_swap_bytes": retained_swap,
        "natural_exit": compact.get("natural_exit"),
        "no_orphan": compact.get("no_orphan"),
        "all_status_readable": compact.get("all_status_readable"),
        "stop_reason": compact.get("stop_reason"),
        "watchdog_rss_limit_bytes": compact.get("watchdog_rss_limit_bytes"),
        "watchdog_compact": str(compact_path.resolve()),
        "watchdog_compact_sha256": _sha256(compact_path),
        "watchdog_raw": str(raw_path.resolve()),
        "watchdog_raw_sha256": raw_digest,
        "worker_command": command,
    }


def check_record(record_path: Path, watchdog_path: Path, expected_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record = _read(record_path)
    raw_dir = Path(record.get("raw_dir", ""))
    _error(errors, record.get("schema") != SCHEMA, "record schema mismatch")
    _error(errors, record.get("stage") != "s2", "stage mismatch")
    _error(errors, record.get("case") != CASE, "case mismatch")
    _error(errors, int(record.get("degree", -1)) != 6, "degree mismatch")
    _error(errors, float(record.get("h_nm", -1.0)) != 10.0, "mesh h mismatch")
    _error(errors, float(record.get("wavelength_nm", -1.0)) != 13.5, "wavelength mismatch")
    _error(errors, int(record.get("mpi_size", -1)) != 1, "MPI size mismatch")
    _error(errors, not raw_dir.is_absolute() or not raw_dir.is_dir(), "raw_dir is missing or not absolute")
    _error(errors, Path(record.get("record_path", "")).resolve() != record_path.resolve(), "record path is not self-bound")
    command = record.get("command")
    _error(errors, not isinstance(command, list) or len(command) < 3, "worker command is missing")
    if isinstance(command, list) and command:
        _error(errors, not Path(str(command[0])).is_absolute(), "worker executable is not absolute")
        expected_tail = [
            "-m",
            MODULE,
            "--stage",
            "s2",
            "--case",
            CASE,
            "--raw-dir",
            str(raw_dir.resolve()),
            "--record",
            str(record_path.resolve()),
            "--expected-source-sha",
            expected_sha,
            "--expected-mpi-size",
            "1",
            "--input",
            str((Path(__file__).resolve().parents[1] / TEMPLATE_RELATIVE_PATH).resolve()),
        ]
        _error(errors, command[1:] != expected_tail, "worker command argv is not exact")
    input_identity = record.get("input_identity", {})
    repo_root = Path(__file__).resolve().parents[1]
    expected_input_path = (repo_root / TEMPLATE_RELATIVE_PATH).resolve()
    _error(errors, input_identity.get("path_absolute") != str(expected_input_path), "input absolute path mismatch")
    _error(errors, input_identity.get("path_relative") != TEMPLATE_RELATIVE_PATH, "input relative path mismatch")
    _error(errors, input_identity.get("raw_bytes") != EXPECTED_INPUT_BYTES, "input byte count mismatch")
    _error(errors, input_identity.get("raw_sha256") != EXPECTED_INPUT_SHA256, "input SHA mismatch")
    _error(errors, input_identity.get("physical_model_sha256") != EXPECTED_PHYSICAL_MODEL_SHA256, "physical model SHA mismatch")
    _error(errors, input_identity.get("resolved_bytes") != EXPECTED_RESOLVED_BYTES, "resolved input byte count mismatch")
    _error(errors, input_identity.get("resolved_sha256") != EXPECTED_RESOLVED_SHA256, "resolved input SHA mismatch")
    source = record.get("source", {})
    for side in ("start", "end"):
        facts = source.get(side, {})
        _error(errors, facts.get("expected_sha") != expected_sha, f"source {side} SHA mismatch")
        _error(errors, facts.get("commit_sha") != expected_sha, f"source {side} commit mismatch")
        _error(errors, facts.get("branch") != BRANCH, f"source {side} branch mismatch")
        _error(errors, facts.get("clean") is not True, f"source {side} not clean")
    runtime = record.get("runtime", {})
    _error(errors, runtime.get("qualified_activation") != "1", "qualification marker missing")
    _error(errors, runtime.get("mpi_size") != 1, "runtime MPI mismatch")
    _error(errors, runtime.get("petsc_scalar_type") != "<class 'numpy.complex128'>", "complex128 ABI mismatch")
    _error(errors, runtime.get("petsc_int_type") != "<class 'numpy.int32'>", "int32 ABI mismatch")
    if isinstance(command, list) and command:
        _error(errors, runtime.get("sys_executable") != command[0], "runtime executable does not match worker command")

    settings = record.get("settings", {})
    _error(errors, settings.get("apply_names") != list(APPLY_NAMES), "apply order mismatch")
    _error(errors, settings.get("repeat_count") != REPEAT_COUNT, "repeat count mismatch")
    _error(errors, settings.get("reserve_vector_count") != RESERVE_COUNT, "restart reserve count mismatch")
    _error(errors, settings.get("restart_basis_count") != 21, "basis reserve count mismatch")
    _error(errors, settings.get("auxiliary_vector_count") != 4, "auxiliary reserve count mismatch")
    _error(errors, settings.get("retained_rss_limit_bytes") != RETAINED_LIMIT, "retained RSS limit is not 1.55GB")
    _error(errors, settings.get("cold_rss_limit_bytes") != COLD_LIMIT, "cold RSS limit is not 1.8GB")
    _error(errors, settings.get("repeat_growth_limit_bytes") != GROWTH_LIMIT, "repeat growth limit is not 32MB")
    _error(errors, "iteration history" not in str(settings.get("restart_semantics", "")), "restart reserve semantics missing")
    _error(errors, any(key in record for key in ("basis_history", "vector_history", "checkpoint_vectors")), "large vector history is present")

    reserve = record.get("reserve")
    _error(errors, not isinstance(reserve, dict), "restart reserve facts are missing")
    if isinstance(reserve, dict):
        _error(errors, reserve.get("basis_count") != 21, "reserve basis count is not 21")
        _error(errors, reserve.get("auxiliary_vector_count") != 4, "reserve auxiliary count is not 4")
        _error(errors, reserve.get("vector_count") != RESERVE_COUNT, "reserve vector count is not 25")
        _error(errors, reserve.get("touched") is not True, "reserve vectors were not touched")
        local_entries = reserve.get("local_entries_per_vector")
        local_bytes = reserve.get("local_numeric_bytes")
        _error(errors, not isinstance(local_entries, int) or local_entries <= 0, "reserve local vector size is missing")
        _error(errors, not isinstance(local_bytes, int) or local_bytes < 0, "reserve numeric bytes are missing")
        if isinstance(local_entries, int) and isinstance(local_bytes, int):
            _error(errors, local_bytes != RESERVE_COUNT * local_entries * 16, "reserve numeric bytes do not close")

    architecture = record.get("architecture", {})
    for key in FORBIDDEN_ARCHITECTURE:
        _error(errors, architecture.get(key) is not False, f"{key} is not false")
    high_space = architecture.get("high_space")
    low_space = architecture.get("low_space")
    for label, space in (("high_space", high_space), ("low_space", low_space)):
        _error(errors, not isinstance(space, dict), f"{label} facts are missing")
        if isinstance(space, dict):
            for key in ("global_rows", "local_storage_entries"):
                _error(
                    errors,
                    not _positive_int(space.get(key)),
                    f"{label}.{key} is not a positive integer",
                )
    high_rows = high_space.get("global_rows") if isinstance(high_space, dict) else None
    _error(
        errors,
        not isinstance(architecture.get("high_positive_action"), dict)
        or not _positive_int(architecture.get("high_positive_action", {}).get("global_rows")),
        "high_positive_action.global_rows is not a positive integer",
    )
    _error(
        errors,
        not isinstance(architecture.get("physical_action"), dict)
        or not isinstance(architecture.get("physical_action", {}).get("volume_action"), dict)
        or not _positive_int(
            architecture.get("physical_action", {})
            .get("volume_action", {})
            .get("global_rows")
        ),
        "physical_action.volume_action.global_rows is not a positive integer",
    )
    if _positive_int(high_rows):
        _error(
            errors,
            architecture.get("high_positive_action", {}).get("global_rows") != high_rows,
            "high_positive_action.global_rows does not match high_space",
        )
        _error(
            errors,
            architecture.get("physical_action", {})
            .get("volume_action", {})
            .get("global_rows")
            != high_rows,
            "physical_action.volume_action.global_rows does not match high_space",
        )
    _check_nested_forbidden(
        errors,
        "high_positive_action",
        architecture.get("high_positive_action"),
        REQUIRED_NESTED_FIELDS["high_positive_action"],
    )
    physical_action = architecture.get("physical_action")
    _check_nested_forbidden(
        errors,
        "physical_action",
        physical_action,
        REQUIRED_NESTED_FIELDS["physical_action"],
    )
    if isinstance(physical_action, dict):
        _check_nested_forbidden(
            errors,
            "physical_action.volume_action",
            physical_action.get("volume_action"),
            REQUIRED_NESTED_FIELDS["physical_action.volume_action"],
        )
        _check_nested_forbidden(
            errors,
            "physical_action.dtn_action",
            physical_action.get("dtn_action"),
            REQUIRED_NESTED_FIELDS["physical_action.dtn_action"],
        )
    _check_setup_resources(errors, architecture)
    transfer = architecture.get("transfer", {})
    _error(errors, transfer.get("global_transfer_matrix") is not False, "transfer matrix flag is not false")
    _error(errors, int(transfer.get("batch_scratch_bytes", -1)) != TRANSFER_SCRATCH, "transfer scratch fact mismatch")
    low_raw_map = architecture.get("low_raw_map", {})
    _error(
        errors,
        not isinstance(low_raw_map, dict)
        or not _positive_int(low_raw_map.get("owned_raw_rows")),
        "low raw-map owned rows are missing",
    )
    for key in ("active_raw_rows", "phase_rows"):
        _error(
            errors,
            not isinstance(low_raw_map, dict)
            or type(low_raw_map.get(key)) is not int
            or low_raw_map[key] < 0,
            f"low raw-map {key} is missing",
        )
    if (
        isinstance(low_raw_map, dict)
        and type(low_raw_map.get("owned_raw_rows")) is int
        and type(low_raw_map.get("active_raw_rows")) is int
        and type(low_raw_map.get("phase_rows")) is int
    ):
        _error(
            errors,
            low_raw_map["active_raw_rows"] + low_raw_map["phase_rows"]
            != low_raw_map["owned_raw_rows"],
            "low raw-map active/phase rows do not close",
        )
    low_matrix = architecture.get("low_matrix", {})
    _error(errors, not isinstance(low_matrix, dict), "low matrix facts are missing")
    if isinstance(low_matrix, dict):
        for key in ("rows", "cols", "nnz", "index_bytes", "numeric_bytes"):
            _error(
                errors,
                not _positive_int(low_matrix.get(key)),
                f"low matrix {key} is not a positive integer",
            )
        _error(
            errors,
            type(low_matrix.get("petsc_reported_memory_bytes")) is not int
            or low_matrix["petsc_reported_memory_bytes"] < 0,
            "low matrix PETSc reported memory is invalid",
        )
        if _positive_int(low_matrix.get("rows")) and _positive_int(low_matrix.get("cols")):
            _error(errors, low_matrix["rows"] != low_matrix["cols"], "low matrix is not square")
        if _positive_int(low_matrix.get("rows")) and _positive_int(low_space.get("global_rows") if isinstance(low_space, dict) else None):
            _error(
                errors,
                low_matrix["rows"] != low_space["global_rows"],
                "low matrix rows do not match low_space",
            )
    for key in ("retained_numeric_bytes", "reference_factor_index_metadata_bytes", "reference_factor_approx_retained_bytes"):
        _error(
            errors,
            not isinstance(transfer, dict) or not _positive_int(transfer.get(key)),
            f"transfer {key} is not positive",
        )
    _error(
        errors,
        int(transfer.get("reference_factor_approx_retained_bytes", -1))
        != int(transfer.get("retained_numeric_bytes", -2))
        + int(transfer.get("reference_factor_index_metadata_bytes", -2)),
        "transfer retained-byte decomposition is inconsistent",
    )

    marker_dir = raw_dir / "markers"
    marker_rows = []
    marker_contract = record.get("markers", {})
    _error(errors, marker_contract.get("relative_dir") != "markers", "marker directory binding is missing")
    _error(errors, marker_contract.get("names") != list(MARKERS), "marker sequence contract is missing")
    for marker in MARKERS:
        marker_path = marker_dir / f"{marker}.json"
        _error(errors, not _inside(marker_path, raw_dir) or not marker_path.is_file(), f"marker missing: {marker}")
        if marker_path.is_file():
            marker_row = _read(marker_path)
            _error(errors, marker_row.get("marker") != marker, f"marker identity mismatch: {marker}")
            _error(errors, marker_row.get("source_sha") != expected_sha, f"marker source mismatch: {marker}")
            marker_rows.append(marker_row)
    marker_times = [int(row.get("wall_time_ns", -1)) for row in marker_rows]
    _error(errors, any(value < 0 for value in marker_times), "marker timestamp missing")
    _error(errors, marker_times != sorted(marker_times), "marker order is not monotonic")
    retained_marker_times = {
        row.get("marker"): int(row.get("wall_time_ns", -1)) for row in marker_rows
    }
    _error(
        errors,
        record.get("retained_ready_wall_time_ns")
        != retained_marker_times.get("retained_ready", -1),
        "retained_ready timestamp is not marker-bound",
    )
    _error(
        errors,
        float(record.get("retained_dwell_seconds", -1.0)) != RETAINED_DWELL_SECONDS,
        "retained dwell is not the fixed 2-second observation",
    )

    ledger_info = record.get("apply_ledger", {})
    ledger_path = raw_dir / str(ledger_info.get("relative_path", ""))
    _error(errors, not _inside(ledger_path, raw_dir), "apply ledger escapes raw_dir")
    _error(errors, not ledger_path.is_file(), "apply ledger is missing")
    if ledger_path.is_file():
        _error(errors, _sha256(ledger_path) != ledger_info.get("sha256"), "apply ledger SHA mismatch")
        ledger = _read(ledger_path)
    else:
        ledger = {}
    rows = ledger.get("rows", [])
    _error(errors, ledger.get("operation_names") != list(APPLY_NAMES), "raw apply order mismatch")
    _error(errors, ledger.get("repeat_count") != REPEAT_COUNT or len(rows) != REPEAT_COUNT, "raw apply repeat rows incomplete")
    repeat_identity: dict[str, Any] = {}
    repeat_indices = [row.get("repeat") for row in rows if isinstance(row, dict)]
    _error(errors, repeat_indices != list(range(REPEAT_COUNT)), "repeat indices are not exactly 0..9")
    for row in rows:
        for name in APPLY_NAMES:
            fact = row.get(name, {})
            _gate(
                gates,
                fact.get("finite") is not True or not _finite_number(fact.get("norm")),
                f"nonfinite {name} apply",
            )
            _error(
                errors,
                not isinstance(fact.get("digest"), str)
                or len(fact["digest"]) != 64,
                f"{name} digest missing",
            )
        resource = row.get("resource", {})
        process_tree = resource.get("process_tree", {})
        _gate(gates, process_tree.get("all_status_readable") is not True, "cycle resource unreadable")
        _gate(gates, int(process_tree.get("swap_bytes", -1)) != 0, "cycle resource swap nonzero")
    for name in APPLY_NAMES:
        facts = [row.get(name, {}) for row in rows if isinstance(row, dict)]
        digests = [fact.get("digest") for fact in facts]
        norms = [fact.get("norm") for fact in facts]
        digest_identical = len(digests) == REPEAT_COUNT and len(set(digests)) == 1
        norm_identical = (
            len(norms) == REPEAT_COUNT
            and all(_finite_number(value) for value in norms)
            and bool(
                all(
                    np.isclose(
                        float(value),
                        float(norms[0]),
                        rtol=REPEAT_NORM_TOL,
                        atol=1.0e-15,
                    )
                    for value in norms[1:]
                )
            )
        )
        _error(errors, not digest_identical, f"{name} repeat digest identity failed")
        _error(errors, not norm_identical, f"{name} repeat norm identity failed")
        repeat_identity[name] = {
            "repeat_indices": list(repeat_indices),
            "digest": digests[0] if digests else None,
            "digests_identical": digest_identical,
            "norms": norms,
            "norms_identical": norm_identical,
        }

    input_facts = record.get("input_facts", {})
    _error(
        errors,
        set(input_facts) != {"high_primal", "high_dual", "low_primal"},
        "role-separated input facts are incomplete",
    )
    for role in ("high_primal", "high_dual", "low_primal"):
        facts = input_facts.get(role, {})
        _gate(
            gates,
            facts.get("unchanged") is not True
            or facts.get("before_digest") != facts.get("after_digest"),
            f"{role} input changed",
        )
    retained = record.get("retained", {})
    retained_resource = retained.get("resource", {})
    retained_tree = retained_resource.get("process_tree", {})
    retained_rss = int(retained.get("measured_process_tree_rss_bytes", -1))
    retained_swap = int(retained_tree.get("swap_bytes", -1))
    _error(
        errors,
        retained_rss != int(retained_tree.get("rss_bytes", -2)),
        "retained RSS does not match its resource sample",
    )
    _error(errors, retained_tree.get("all_status_readable") is not True, "worker retained sample unreadable")
    _gate(gates, retained_swap != 0, "worker retained swap nonzero")
    rss_rows = [
        int(row.get("resource", {}).get("process_tree", {}).get("rss_bytes", -1))
        for row in rows
    ]
    _error(errors, len(rss_rows) != REPEAT_COUNT or any(value < 0 for value in rss_rows), "repeat RSS rows are incomplete")
    repeat_growth = None
    if len(rss_rows) == REPEAT_COUNT and all(value >= 0 for value in rss_rows):
        repeat_growth = max(0, max(rss_rows[1:]) - rss_rows[0])
        _gate(gates, repeat_growth > GROWTH_LIMIT, "repeat retained RSS growth exceeds 32MB")
    watchdog_metrics = _check_watchdog(watchdog_path, record, expected_sha, errors, gates)
    retained_known = retained.get("known_total_bytes")
    unattributed = retained.get("unattributed_remainder_bytes")
    _error(errors, not isinstance(retained_known, int) or retained_known < 0, "retained known-byte total is invalid")
    _error(errors, not isinstance(unattributed, int) or unattributed < 0, "unattributed retained bytes are negative/invalid")
    vector_facts = retained.get("vector_facts", {})
    known_bytes = retained.get("known_bytes")
    _error(errors, not isinstance(known_bytes, dict), "retained known-byte ledger is missing")
    known_sum = None
    if isinstance(known_bytes, dict):
        _error(errors, "mesh_space_mpc_known_array_bytes" not in known_bytes, "mesh/space/MPC null ledger entry is missing")
        numeric_values = []
        for key, value in known_bytes.items():
            if key == "mesh_space_mpc_known_array_bytes":
                _error(errors, value is not None, "mesh/space/MPC known_array_bytes must be null")
            else:
                _error(errors, type(value) is not int or value < 0, f"known retained bytes invalid: {key}")
                if type(value) is int and value >= 0:
                    numeric_values.append(value)
        for key in (
            "high_topology_retained_array_bytes",
            "low_topology_retained_array_bytes",
            "lor_matrix_index_bytes",
            "lor_matrix_numeric_bytes",
            "transfer_reference_factor_approx_retained_bytes",
        ):
            _error(
                errors,
                not _positive_int(known_bytes.get(key)),
                f"known retained {key} is not positive",
            )
        known_sum = int(sum(numeric_values))
        _error(errors, known_sum != retained_known, "known retained bytes do not sum to known_total_bytes")
        if all(
            type(vector_facts.get(key)) is int
            for key in ("high_vector_count", "high_bytes_per_vector", "low_vector_count", "low_bytes_per_vector")
        ):
            _error(
                errors,
                known_bytes.get("foundation_high_work_vectors_bytes")
                != vector_facts["high_vector_count"] * vector_facts["high_bytes_per_vector"],
                "high work-vector bytes do not close",
            )
            _error(
                errors,
                known_bytes.get("foundation_low_work_vectors_bytes")
                != vector_facts["low_vector_count"] * vector_facts["low_bytes_per_vector"],
                "low work-vector bytes do not close",
            )
    _error(
        errors,
        isinstance(unattributed, int)
        and isinstance(retained_known, int)
        and unattributed != retained_rss - retained_known,
        "unattributed retained bytes do not equal measured minus known",
    )
    mesh_semantics = retained.get("mesh_space_mpc", {})
    _error(errors, mesh_semantics.get("known_array_bytes") is not None, "mesh/space/MPC known_array_bytes must be null")
    _error(errors, mesh_semantics.get("measured_separately") is not False, "mesh/space/MPC measurement semantics changed")
    _error(errors, mesh_semantics.get("included_in_unattributed") is not True, "mesh/space/MPC remainder semantics missing")
    for key in ("high_bytes_per_vector", "low_bytes_per_vector"):
        _error(errors, type(vector_facts.get(key)) is not int or vector_facts[key] <= 0, f"retained vector fact missing: {key}")
    _error(errors, vector_facts.get("high_vector_count") != 3, "high vector count is not 3")
    _error(errors, vector_facts.get("low_vector_count") != 3, "low vector count is not 3")
    if isinstance(reserve, dict):
        local_entries = reserve.get("local_entries_per_vector")
        local_bytes = reserve.get("local_numeric_bytes")
        if type(local_entries) is int and type(vector_facts.get("high_bytes_per_vector")) is int:
            _error(errors, vector_facts["high_bytes_per_vector"] != local_entries * 16, "reserve/high vector bytes do not close")
        if isinstance(known_bytes, dict) and type(local_bytes) is int:
            _error(errors, known_bytes.get("restart_reserve_numeric_bytes") != local_bytes, "reserve numeric bytes do not close")
    bounded = retained.get("bounded_temporary_bytes", {})
    _error(errors, bounded.get("included_in_known_total") is not False, "bounded temporary bytes are included in known total")
    _error(errors, ledger.get("retains_vectors") is not False, "raw apply ledger retains vectors")
    external_retained_rss = int(
        watchdog_metrics.get("retained_peak_process_tree_rss_bytes", -1)
    )
    if errors:
        classification = "CONTRACT_INVALID"
    elif external_retained_rss > RETAINED_LIMIT and external_retained_rss < COLD_LIMIT:
        classification = "BASE_FITS_BUT_NO_PRODUCTION_HEADROOM"
    elif external_retained_rss >= 0 and not gates:
        classification = "RETAINED_MEMORY_GATE_PASS"
    else:
        classification = "MEMORY_GATE_FAILED"
    return {
        "schema": "task038.full3d.lor-memory-first.s2-check.v1",
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "classification": classification,
        "metrics": {
            "repeat_count": len(rows),
            "repeat_identity": repeat_identity,
            "repeat_rss_rows": rss_rows,
            "repeat_rss_growth_bytes": repeat_growth,
            "retained_rss_bytes": retained_rss,
            "retained_swap_bytes": retained_swap,
            "external_retained_rss_bytes": external_retained_rss,
            "known_retained_bytes": retained.get("known_total_bytes"),
            "unattributed_remainder_bytes": retained.get("unattributed_remainder_bytes"),
            "transfer_batch_scratch_bytes": transfer.get("batch_scratch_bytes"),
        },
        "resource": watchdog_metrics,
    }


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
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
