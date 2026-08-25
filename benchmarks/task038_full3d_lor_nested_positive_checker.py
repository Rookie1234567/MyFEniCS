"""Independent checker for the R4.1 Route-B setup/positive evidence.

Only the standard library and NumPy are used.  The worker writes raw facts;
this module recomputes scalar identities, raw array identities, resource
windows, checkpoint inventory, and lifecycle before assigning a classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.full3d.lor-nested-positive.r4.v1"
CHECKER_SCHEMA = "task038.full3d.lor-nested-positive.checker.v1"
MARKER_SCHEMA = "task038.full3d.lor-nested-positive.marker.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
CHECKPOINT_SCHEMA = "fixed-memory-krylov.solution-checkpoint.v1"
MODULE = "benchmarks.run_task038_full3d_lor_nested_positive"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
CASE = "p6-h10-mpi1"
LEVELS = (6, 2, 1)
PAIRS = ((6, 2), (2, 1))
TRANSFER_COUNT_KEYS = tuple(
    f"transfer_{fine}_{coarse}_{kind}_total"
    for fine, coarse in PAIRS
    for kind in ("primal", "adjoint")
)
SOURCES = ("random", "gradient", "curl", "checkerboard")
MPI_SIZE = 1
DEGREE = 6
H_NM = 10.0
WAVELENGTH_NM = 13.5
CHEBYSHEV_DEGREE = 3
POWER_STEPS = 10
RESTART = 20
MAX_IT = 10000
RESIDUAL_LIMIT = 1.0e-8
CHECKPOINT_INTERVAL = 500
COLD_LIMIT = 2_000_000_000
RETAINED_LIMIT = 1_800_000_000
GROWTH_LIMIT = 32_000_000
MILESTONE_KEYS = (20, 100, 200, 500, 1000, 2000, 5000, 10000)
IMMUTABLE_OPERATOR_ACTION_KEYS = (
    "schema", "backend", "matrix_type", "operator", "mpc_enabled",
    "slave_row_identity", "global_rows", "local_owned_rows",
    "local_ghost_rows", "local_storage_entries",
    "constraint_row_metadata_entries", "constraint_count",
    "owned_constraint_count", "constraint_nnz", "constraint_nnz_closes",
    "form_rank", "coefficient_count", "phase_application", "orientation",
    "owner_local", "numeric_allgather", "replicated_global_numeric_vector",
    "global_matrix_materialized", "global_constraint_matrix_materialized",
    "global_condensed_schur_materialized", "cell_schur_matrix_materialized",
    "slab_matrix_materialized", "cell_schur_matrix_nnz", "slab_matrix_nnz",
    "factor_count", "ksp_created", "dtn_used", "ordinary_default_changed",
    "fresh_packed_arrays_released", "jit_options_explicit",
    "retained_numeric_payload_components",
    "retained_numeric_payload_local_bytes",
    "retained_numeric_payload_global_sum_bytes",
    "retained_numeric_payload_global_max_bytes",
    "retained_dense_cell_tensor_count",
    "dense_cell_tensor_materialized_per_apply",
)
SETUP_LABELS = (
    "x", "y", "x_repeat", "combo", "ax", "by",
    "x_repeat_2", "x_repeat_3", "x_repeat_4", "x_repeat_5",
)
POSITIVE_RAW_ROLES = (
    "source_before", "source_after", "rhs", "rhs_repeat",
    "final_solution", "final_action", "final_true_residual",
)
FORBIDDEN_FIELDS = (
    "global_high_order_aij", "global_transfer_matrix", "global_dense_transfer",
    "numeric_allgather", "global_numeric_allgather", "p6_exact_factor",
    "p6_exact_edge_factor_built", "level2_exact_factor", "global_direct_coarse",
    "hx_hierarchy_built", "pcgamg_hierarchy_built", "scalar_node_matrix_built",
    "recovery_field_arrays_built", "hx_or_node_action_built",
    "production_local_spectral_built", "physical_solve", "recovery",
    "retains_per_apply_history",
)
MARKERS = {
    "setup": (
        "paths_ready", "source_runtime_closed", "foundation_built",
        "extension_built", "vcycle_built", "reserve_built",
        "pc_applies_complete", "retained_ready", "vcycle_destroyed",
        "reserve_destroyed", "foundation_destroyed", "record_written",
    ),
    "positive": (
        "paths_ready", "source_runtime_closed", "foundation_built",
        "extension_built", "vcycle_built", "positive_started",
        "checkpoints_complete", "retained_ready", "vcycle_destroyed",
        "foundation_destroyed", "record_written",
    ),
}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, parse_constant=_reject_constant)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_sha(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _immutable_operator_action_audit(audit: Any) -> dict[str, Any] | None:
    if not isinstance(audit, dict) or any(key not in audit for key in IMMUTABLE_OPERATOR_ACTION_KEYS):
        return None
    return {key: audit[key] for key in IMMUTABLE_OPERATOR_ACTION_KEYS}


def _array_sha(values: np.ndarray) -> str:
    values = np.ascontiguousarray(values)
    return hashlib.sha256(values.view(np.uint8)).hexdigest()


def _finite(value: Any) -> bool:
    try:
        return bool(np.all(np.isfinite(np.asarray(value))))
    except (TypeError, ValueError):
        return False


def _hex64(value: Any) -> bool:
    value = str(value)
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _close(left: Any, right: Any, tolerance: float = 1.0e-12) -> bool:
    return _finite(left) and _finite(right) and abs(float(left) - float(right)) <= tolerance


def _transfer_counts_closed(value: Any, expected: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(expected, int)
        and not isinstance(expected, bool)
        and set(value) == set(TRANSFER_COUNT_KEYS)
        and all(
            isinstance(value[key], int)
            and not isinstance(value[key], bool)
            and value[key] == expected
            for key in TRANSFER_COUNT_KEYS
        )
    )


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _expected_command(record: dict[str, Any]) -> list[str]:
    command = record["command"]
    if not isinstance(command, list) or not command or not Path(str(command[0])).is_absolute():
        raise ValueError("command must start with an absolute Python executable")
    stage = str(record["stage"])
    expected = [
        str(command[0]), "-m", MODULE, "--stage", stage, "--case", CASE,
        "--raw-dir", str(Path(record["raw_dir"]).resolve()),
        "--record", str(Path(record["record_path"]).resolve()),
        "--expected-source-sha", str(record["source"]["start"]["expected_sha"]),
        "--expected-mpi-size", str(MPI_SIZE),
        "--input", str(Path(record["input_identity"]["path_absolute"]).resolve()),
    ]
    if stage == "positive":
        expected.extend(("--source", str(record["stage_facts"]["source"]["name"])))
    return expected


def _check_watchdog(
    record: dict[str, Any], compact_path: Path, errors: list[str], gates: list[str]
) -> dict[str, Any]:
    try:
        compact = _read_json(compact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"watchdog compact unreadable: {exc}")
        return {"compact": {}}
    if compact.get("schema") != WATCHDOG_SCHEMA:
        errors.append("watchdog schema mismatch")
    if compact.get("source_sha") != record.get("source", {}).get("start", {}).get("expected_sha"):
        errors.append("watchdog source SHA mismatch")
    if compact.get("worker_command") != record.get("command"):
        errors.append("watchdog worker command mismatch")
    if compact.get("worker_raw_dir") != record.get("raw_dir") or compact.get("worker_record") != record.get("record_path"):
        errors.append("watchdog worker path binding mismatch")
    if compact.get("watchdog_poll_seconds") != 0.25 or compact.get("watchdog_rss_limit_bytes") != COLD_LIMIT:
        errors.append("watchdog fixed polling/resource contract mismatch")
    raw_path = Path(str(compact.get("watchdog_raw", "")))
    if not raw_path.is_file() or not _path_inside(raw_path, compact_path.parent):
        errors.append("watchdog raw path is missing or escapes artifact root")
        return {"compact": compact}
    if compact.get("raw_sha256") != _sha256(raw_path):
        errors.append("watchdog raw SHA mismatch")
    rows: list[dict[str, Any]] = []
    try:
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line, parse_constant=_reject_constant)
                if not isinstance(row, dict):
                    raise ValueError("watchdog row is not an object")
                rows.append(row)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"watchdog raw invalid: {exc}")
        return {"compact": compact}
    rss: list[int] = []
    swap: list[int] = []
    readable: list[bool] = []
    for row in rows:
        try:
            tree = row["authority"]["process_tree"]
            rss_value = int(tree["rss_bytes"])
            swap_value = int(tree["swap_bytes"])
            if rss_value < 0 or swap_value < 0:
                raise ValueError("negative resource sample")
            rss.append(rss_value)
            swap.append(swap_value)
            readable.append(tree["all_status_readable"] is True)
        except (KeyError, TypeError, ValueError):
            errors.append("watchdog sample schema invalid")
    if not rows or not rss:
        errors.append("watchdog has no readable samples")
    if compact.get("sample_count") != len(rows):
        errors.append("watchdog sample count mismatch")
    if compact.get("all_status_readable") is not all(readable):
        errors.append("watchdog compact readability mismatch")
    if rss and compact.get("peak_process_tree_rss_bytes") != max(rss):
        errors.append("watchdog peak mismatch")
    if swap and compact.get("max_process_tree_swap_bytes") != max(swap):
        errors.append("watchdog swap mismatch")
    if compact.get("natural_exit") is not True or compact.get("no_orphan") is not True or compact.get("returncode") != 0:
        errors.append("watchdog lifecycle is not natural/no-orphan/rc0")
    if rss and max(rss) >= COLD_LIMIT:
        gates.append("resource: cold process-tree RSS reached 2GB")
    if swap and max(swap) != 0:
        gates.append("resource: process-tree swap is nonzero")
    ready = int(record.get("retained_ready_wall_time_ns", -1))
    observed = int(record.get("retained_observed_wall_time_ns", -1))
    if record.get("retained_dwell_seconds") != 2.0 or observed - ready < 2_000_000_000:
        errors.append("retained dwell is shorter than the fixed two seconds")
    record_resource = record.get("resource", {})
    for name in ("retained_ready", "retained_observed"):
        sample = record_resource.get(name) if isinstance(record_resource, dict) else None
        if (
            not isinstance(sample, dict)
            or sample.get("all_status_readable") is not True
            or sample.get("swap_bytes") != 0
            or not isinstance(sample.get("rss_bytes"), int)
            or sample["rss_bytes"] < 0
        ):
            errors.append(f"record retained {name} resource fact is incomplete")
    retained = [
        value for row, value in zip(rows, rss, strict=False)
        if ready <= int(row.get("wall_time_ns", -1)) <= observed
    ]
    if not retained:
        errors.append("watchdog has no retained-window sample")
    elif max(retained) >= RETAINED_LIMIT:
        gates.append("resource: retained-window RSS reached 1.8GB")
    return {
        "compact": compact,
        "raw_rss": rss,
        "raw_swap": swap,
        "sample_count": len(rows),
        "peak_process_tree_rss_bytes": max(rss) if rss else None,
        "max_process_tree_swap_bytes": max(swap) if swap else None,
    }


def _check_markers(record: dict[str, Any], raw_dir: Path, errors: list[str]) -> None:
    stage = str(record.get("stage"))
    expected = MARKERS.get(stage)
    if expected is None or tuple(record.get("markers", {}).get("names", ())) != expected:
        errors.append("marker sequence mismatch")
        return
    marker_dir = raw_dir / str(record.get("markers", {}).get("relative_dir", "markers"))
    if not marker_dir.is_dir():
        errors.append("marker directory missing")
        return
    files = sorted(path.name for path in marker_dir.glob("*.json"))
    if files != sorted(f"{name}.json" for name in expected):
        errors.append("marker inventory contains missing or extra files")
        return
    times: dict[str, int] = {}
    record_sha = _sha256(Path(record["record_path"]))
    for name in expected:
        try:
            item = _read_json(marker_dir / f"{name}.json")
            if item.get("schema") != MARKER_SCHEMA or item.get("marker") != name:
                errors.append(f"marker schema mismatch: {name}")
            if item.get("source_sha") != record["source"]["start"]["expected_sha"]:
                errors.append(f"marker source mismatch: {name}")
            times[name] = int(item["wall_time_ns"])
            if name == "record_written" and (
                item.get("facts", {}).get("record_path") != record["record_path"]
                or item.get("facts", {}).get("record_sha256") != record_sha
            ):
                errors.append("record_written marker does not close the record")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"marker invalid {name}: {exc}")
    values = list(times.values())
    if values != sorted(values) or len(set(values)) != len(values):
        errors.append("marker times are not strictly increasing")
    stored = record.get("markers", {}).get("wall_time_ns", {})
    if set(stored) != set(expected[:-1]):
        errors.append("record marker time map has missing or extra entries")
    for name in expected[:-1]:
        if stored.get(name) != times.get(name):
            errors.append(f"record marker time mismatch: {name}")
    lifecycle = record.get("lifecycle", {})
    required_order = ["vcycle", "reserve", "foundation"] if stage == "setup" else ["vcycle", "foundation"]
    if lifecycle.get("normal_closeout") is not True or lifecycle.get("destroy_order") != required_order:
        errors.append("lifecycle closeout is not the fixed destroy order")
    if times.get("retained_ready", -1) >= times.get("vcycle_destroyed", -1):
        errors.append("vcycle was destroyed before retained observation")


def _check_common(record: dict[str, Any], expected_sha: str, errors: list[str]) -> None:
    if set(record) & {"passed", "status", "classification", "gates"}:
        errors.append("worker record contains checker-owned decision fields")
    if record.get("schema") != SCHEMA or record.get("case") != CASE:
        errors.append("record schema/case mismatch")
    if record.get("degree") != DEGREE or record.get("h_nm") != H_NM or record.get("wavelength_nm") != WAVELENGTH_NM or record.get("mpi_size") != MPI_SIZE:
        errors.append("fixed p6/h10/13.5/MPI1 identity mismatch")
    source = record.get("source", {})
    if source.get("start", {}).get("expected_sha") != expected_sha or source.get("end", {}).get("expected_sha") != expected_sha:
        errors.append("source SHA binding mismatch")
    for side in ("start", "end"):
        item = source.get(side, {})
        if item.get("commit_sha") != expected_sha or item.get("branch") != BRANCH or item.get("clean") is not True:
            errors.append(f"source {side} identity is not closed")
    runtime = record.get("runtime", {})
    command = record.get("command", [])
    if runtime.get("qualified_activation") != "1" or runtime.get("mpi_size") != MPI_SIZE or runtime.get("sys_executable") != (command[0] if command else None):
        errors.append("runtime identity mismatch")
    threads = runtime.get("threads")
    if not isinstance(threads, dict) or set(threads) != {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"} or any(value not in (None, "1") for value in threads.values()):
        errors.append("runtime thread facts are not fixed to one")
    if runtime.get("petsc_scalar_type") != "<class 'numpy.complex128'>" or runtime.get("petsc_int_type") != "<class 'numpy.int32'>":
        errors.append("complex128/int32 ABI identity mismatch")
    provenance = record.get("provenance", {})
    if provenance.get("source_sha") != expected_sha or provenance.get("branch") != BRANCH:
        errors.append("provenance source/branch mismatch")
    identity = record.get("input_identity", {})
    input_path = Path(str(identity.get("path_absolute", ""))).resolve()
    if not input_path.is_file() or not str(input_path).endswith("input/templates/full3d_iterative_example.dat"):
        errors.append("input path is not the frozen template")
    for key in ("raw_sha256", "resolved_sha256", "physical_model_sha256"):
        if not _hex64(identity.get(key)):
            errors.append(f"input identity {key} is not a SHA256")
    if input_path.is_file() and _sha256(input_path) != identity.get("raw_sha256"):
        errors.append("frozen input raw SHA does not match the file")
    try:
        if record.get("command") != _expected_command(record):
            errors.append("worker command is not the fixed canonical argv")
    except (KeyError, TypeError, ValueError):
        errors.append("worker command cannot be reconstructed")
    settings = record.get("settings", {})
    fixed = {
        "levels": [6, 2, 1], "pairs": [[6, 2], [2, 1]], "chebyshev_degree": 3,
        "power_steps": 10, "pre_sweeps": 1, "post_sweeps": 1, "vcycle_count": 1,
        "restart": 20, "max_it": 10000, "residual_replacement": True,
        "checkpoint_interval": 500, "cold_rss_limit_bytes": COLD_LIMIT,
        "retained_rss_limit_bytes": RETAINED_LIMIT, "setup_growth_limit_bytes": GROWTH_LIMIT,
    }
    for key, value in fixed.items():
        if settings.get(key) != value:
            errors.append(f"fixed setting mismatch: {key}")
    stage = record.get("stage_facts", {})
    for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
        if not _hex64(stage.get(key)) or provenance.get(key) != stage.get(key):
            errors.append(f"provenance/stage identity mismatch: {key}")
    authority = stage.get("identity_authority", {})
    if authority.get("resolved_config_sha256") != identity.get("resolved_sha256") or authority.get("physical_model_sha256") != identity.get("physical_model_sha256"):
        errors.append("resolved/physical identity authority mismatch")
    resolved_sha = identity.get("resolved_sha256")
    raw_sha = identity.get("raw_sha256")
    physical_sha = identity.get("physical_model_sha256")
    if isinstance(resolved_sha, str) and isinstance(raw_sha, str) and isinstance(physical_sha, str):
        input_authority = stage.get("input_identity_authority")
        if not isinstance(input_authority, dict) or stage.get("input_identity_sha256") != _stable_sha(input_authority):
            errors.append("input identity authority is missing or hash-inconsistent")
        if record.get("stage") == "setup":
            expected_input_authority = {
                "stage": "setup", "resolved_config_sha256": resolved_sha,
                "input_raw_sha256": raw_sha, "physical_model_sha256": physical_sha,
            }
            if input_authority != expected_input_authority:
                errors.append("setup input identity authority is not fixed to config/input/physical facts")
        elif not isinstance(input_authority, dict) or set(input_authority) != {
            "source_generation", "source_before", "resolved_config_sha256",
            "input_raw_sha256", "physical_model_sha256",
        }:
            errors.append("positive input identity authority shape is incomplete")
        architecture = record.get("architecture", {})
        case_audit = architecture.get("case_audit") if isinstance(architecture, dict) else None
        action_snapshot = _immutable_operator_action_audit(
            case_audit.get("high_positive_action") if isinstance(case_audit, dict) else None
        )
        high_coeff = architecture.get("high_coefficient_audit") if isinstance(architecture, dict) else None
        if action_snapshot is None or high_coeff is None:
            errors.append("immutable high positive operator authority inputs are missing")
        else:
            expected_operator_authority = {
                "resolved_config_sha256": resolved_sha,
                "input_raw_sha256": raw_sha,
                "physical_model_sha256": physical_sha,
                "high_coefficient_audit": high_coeff,
                "high_positive_action_audit": action_snapshot,
                "matrix_free_action_identity": "S2FoundationCase.high_positive.apply",
            }
            if stage.get("operator_identity_authority") != expected_operator_authority or stage.get("operator_identity_sha256") != _stable_sha(expected_operator_authority):
                errors.append("operator identity authority is missing or not independently bound")


def _check_architecture(record: dict[str, Any], errors: list[str]) -> None:
    architecture = record.get("architecture", {})
    forbidden = architecture.get("forbidden")
    if not isinstance(forbidden, dict) or set(forbidden) != set(FORBIDDEN_FIELDS) or any(value is not False for value in forbidden.values()):
        errors.append("forbidden architecture facts are not explicit false values")
    if architecture.get("current_anchor_p1_exact_oracle") is not True:
        errors.append("current p1 exact oracle anchor is missing")
    source_bindings = {
        "global_high_order_aij": ("vcycle_audit", "global_high_order_aij"),
        "global_transfer_matrix": ("extension_audit", "global_transfer_matrix"),
        "global_dense_transfer": ("case_audit", "global_dense_transfer"),
        "numeric_allgather": ("extension_audit", "numeric_allgather"),
        "global_numeric_allgather": ("case_audit", "global_numeric_allgather"),
        "p6_exact_factor": ("extension_audit", "p6_exact_factor"),
        "p6_exact_edge_factor_built": ("case_audit", "p6_exact_edge_factor_built"),
        "level2_exact_factor": ("vcycle_audit", "level2_exact_factor"),
        "global_direct_coarse": ("vcycle_audit", "global_direct_coarse"),
        "hx_hierarchy_built": ("extension_audit", "hx_hierarchy_built"),
        "pcgamg_hierarchy_built": ("extension_audit", "pcgamg_hierarchy_built"),
        "scalar_node_matrix_built": ("case_audit", "scalar_node_matrix_built"),
        "recovery_field_arrays_built": ("case_audit", "recovery_field_arrays_built"),
        "hx_or_node_action_built": ("case_audit", "hx_or_node_action_built"),
        "production_local_spectral_built": ("case_audit", "production_local_spectral_built"),
        "physical_solve": ("extension_audit", "physical_solve"),
        "recovery": ("extension_audit", "recovery"),
        "retains_per_apply_history": ("vcycle_audit", "retains_per_apply_history"),
    }
    for name, (source_name, key) in source_bindings.items():
        source = architecture.get(source_name)
        if not isinstance(source, dict) or key not in source or not isinstance(source[key], bool):
            errors.append(f"missing architecture audit {source_name}.{key}")
        elif source[key] is not forbidden.get(name):
            errors.append(f"forbidden architecture binding mismatch: {name}")
    vcycle = architecture.get("vcycle_audit", {})
    if vcycle.get("p1_exact_factor") is not True or vcycle.get("p1_factor_ksp_created") is not True or vcycle.get("p6_exact_factor") is not False or vcycle.get("level2_exact_factor") is not False:
        errors.append("V-cycle factor audit is not closed")
    factor = architecture.get("level1_factor", {})
    positive_ints = ("matrix_rows", "matrix_cols", "matrix_nnz", "factor_matrix_nnz", "setup_count")
    if factor.get("backend") != "petsc-preonly-lu-mumps" or factor.get("factor_solver_type") != "mumps" or any(not isinstance(factor.get(key), int) or factor[key] <= 0 for key in positive_ints):
        errors.append("p1 factor matrix/setup facts are incomplete")
    available = factor.get("petsc_reported_factor_memory_available")
    local = factor.get("petsc_reported_factor_memory_local_bytes")
    global_value = factor.get("petsc_reported_factor_memory_global_bytes")
    summary = factor.get("petsc_reported_factor_memory_bytes")
    ledger = record.get("retained_ledger", {})
    route = ledger.get("route_b", {}) if isinstance(ledger, dict) else {}
    route_known = route.get("known_bytes") if isinstance(route, dict) else None
    known = ledger.get("known_bytes") if isinstance(ledger, dict) else None
    memory_values = (local, global_value, summary)
    if not isinstance(available, bool):
        errors.append("p1 factor memory availability flag is missing or not boolean")
    elif available:
        if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in memory_values) or global_value != local or summary != local:
            errors.append("available p1 factor memory facts are not positive and closed")
        if (
            not isinstance(route_known, dict)
            or not isinstance(known, dict)
            or route.get("p1_factor_memory_bytes") != local
            or route_known.get("p1_factor_memory_bytes") != local
            or known.get("p1_factor_memory_bytes") != local
        ):
            errors.append("available p1 factor memory is missing from the Route-B ledger")
    else:
        if any(not isinstance(value, int) or isinstance(value, bool) or value != 0 for value in memory_values):
            errors.append("unavailable p1 factor memory facts must be explicit zero")
        if (
            not isinstance(route_known, dict)
            or not isinstance(known, dict)
            or route.get("p1_factor_memory_bytes") != 0
            or "p1_factor_memory_bytes" in route_known
            or "p1_factor_memory_bytes" in known
        ):
            errors.append("unavailable p1 factor memory must remain in the unattributed remainder")
    stage = record.get("stage_facts", {})
    if factor.get("solve_count") != stage.get("p1_solve_count"):
        errors.append("p1 factor solve count does not close the stage count")


def _check_ledger(record: dict[str, Any], errors: list[str]) -> None:
    ledger = record.get("retained_ledger", {})
    if not isinstance(ledger, dict) or ledger.get("estimates_included") is not False:
        errors.append("retained ledger is missing measured-only semantics")
        return
    foundation = ledger.get("foundation", {})
    route = ledger.get("route_b", {})
    known = ledger.get("known_bytes")
    if not isinstance(known, dict) or not isinstance(route, dict) or not isinstance(foundation, dict):
        errors.append("retained component ledger is incomplete")
        return
    if any(not isinstance(value, int) or value < 0 for value in known.values()):
        errors.append("retained known bytes contain an invalid component")
    if ledger.get("known_total_bytes") != sum(known.values()):
        errors.append("retained known total is not closed")
    foundation_known = foundation.get("known_bytes", {})
    route_known = route.get("known_bytes", {})
    if not isinstance(foundation_known, dict) or not isinstance(route_known, dict):
        errors.append("foundation/Route-B known byte maps are missing")
    else:
        if foundation.get("known_total_bytes") != sum(value for value in foundation_known.values() if isinstance(value, int)):
            errors.append("foundation ledger total is not closed")
        if sum(value for value in route_known.values() if isinstance(value, int)) != sum(value for key, value in known.items() if key in route_known):
            errors.append("Route-B ledger component total is not closed")
    smoother_detail = route.get("smoother_work_vectors", {})
    for degree in (6, 2):
        item = smoother_detail.get(f"level{degree}", {}) if isinstance(smoother_detail, dict) else {}
        entries = item.get("local_entries", [])
        if item.get("vector_count") != 8 or not isinstance(entries, list) or len(entries) != 8 or item.get("complex128_bytes") != sum(int(value) * 16 for value in entries):
            errors.append(f"level{degree} smoother retained vectors are not closed")
    work = route.get("vcycle_work_vectors", {})
    if not isinstance(work, dict) or work.get("complex128_bytes") != sum(int(value) * 16 for value in work.get("local_entries", [])):
        errors.append("V-cycle work-vector ledger is not closed")
    factor = record.get("architecture", {}).get("level1_factor", {})
    if route.get("p1_factor_memory_bytes") != factor.get("petsc_reported_factor_memory_local_bytes"):
        errors.append("retained ledger does not bind p1 factor memory")
    reserve = record.get("reserve")
    expected_reserve = int(reserve.get("local_numeric_bytes", -1)) if isinstance(reserve, dict) else 0
    if route.get("restart_reserve_numeric_bytes") != expected_reserve:
        errors.append("retained ledger does not bind restart reserve")
    retained = record.get("resource", {}).get("retained_observed", {})
    measured = ledger.get("measured_process_tree_rss_bytes")
    if not isinstance(retained, dict) or not isinstance(retained.get("rss_bytes"), int):
        errors.append("retained observed resource fact is missing")
    elif measured != retained["rss_bytes"]:
        errors.append("retained ledger RSS does not bind retained observed RSS")
    remainder = ledger.get("unattributed_remainder_bytes")
    if not isinstance(measured, int) or not isinstance(remainder, int) or remainder != measured - ledger.get("known_total_bytes", -1):
        errors.append("retained unattributed remainder does not close")
    elif remainder < 0:
        errors.append("retained known bytes exceed measured RSS")


def _check_setup(record: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    stage = record.get("stage_facts", {})
    reserve = record.get("reserve")
    if not isinstance(reserve, dict) or reserve.get("basis_count") != 21 or reserve.get("auxiliary_vector_count") != 4 or reserve.get("vector_count") != 25 or reserve.get("touched") is not True or not isinstance(reserve.get("local_numeric_bytes"), int) or reserve["local_numeric_bytes"] <= 0:
        errors.append("restart reserve contract is incomplete")
    applies = stage.get("apply_facts")
    if stage.get("apply_count") != 10 or tuple(item.get("label") for item in applies or ()) != SETUP_LABELS or stage.get("vcycle_apply_count") != 10:
        errors.append("setup does not contain the fixed ten apply labels/count")
    if stage.get("p1_solve_count") != 10:
        errors.append("setup p1 solve count is not exactly ten")
    transfer_counts = stage.get("transfer_counts")
    if not _transfer_counts_closed(transfer_counts, 10):
        errors.append("setup transfer aggregate counts are not exactly ten")
    if stage.get("outer_ksp_create_count") != 0 or stage.get("outer_ksp_destroy_count") != 0:
        errors.append("setup unexpectedly created an outer KSP")
    for index, item in enumerate(applies if isinstance(applies, list) else (), 1):
        resource = item.get("resource", {})
        if item.get("output_finite") is not True or item.get("input_unchanged") is not True or item.get("p1_solve_count") != index or not _finite(item.get("p1_relative_residual")) or float(item["p1_relative_residual"]) > 1.0e-11:
            gates.append(f"numerical: setup p1 apply fact failed: {item.get('label')}")
        if resource.get("all_status_readable") is not True or not isinstance(resource.get("rss_bytes"), int) or resource["rss_bytes"] < 0:
            errors.append(f"setup resource row invalid: {item.get('label')}")
        if resource.get("swap_bytes") != 0:
            gates.append("resource: setup apply swap is nonzero")
        if not _finite(item.get("primal_constraint_relative")) or float(item["primal_constraint_relative"]) > 1.0e-12:
            gates.append(f"numerical: setup legal primal failed: {item.get('label')}")
    if stage.get("finite") is not True or stage.get("input_unchanged") is not True or stage.get("legal_high_primal") is not True:
        gates.append("numerical: setup finite/input/legal-primal fact failed")
    if not _finite(stage.get("independent_input_relative")) or float(stage["independent_input_relative"]) <= 1.0e-6:
        errors.append("setup x/y inputs are not independently non-collinear")
    if not _finite(stage.get("linearity_relative")) or float(stage["linearity_relative"]) > 1.0e-12:
        gates.append("numerical: setup linearity failed")
    if not _finite(stage.get("repeat_relative")) or float(stage["repeat_relative"]) > 1.0e-13:
        gates.append("numerical: setup repeat failed")
    rss = [item.get("resource", {}).get("rss_bytes") for item in applies or ()]
    swaps = [item.get("resource", {}).get("swap_bytes") for item in applies or ()]
    if len(rss) != 10 or any(not isinstance(value, int) or value < 0 for value in rss):
        errors.append("setup resource rows are incomplete")
    else:
        recomputed = max(0, max(rss[1:]) - rss[0])
        if stage.get("rss_span_bytes") != recomputed:
            errors.append("setup RSS span does not close from the ten raw rows")
        if recomputed > GROWTH_LIMIT:
            gates.append("resource: setup ten-apply RSS growth exceeded 32MB")
    if any(value != 0 for value in swaps):
        gates.append("resource: setup max swap is nonzero")
    if not swaps or stage.get("max_swap_bytes") != max(swaps):
        errors.append("setup maximum swap does not close from the ten raw rows")
    if not _finite(stage.get("max_p1_relative_residual")) or float(stage["max_p1_relative_residual"]) > 1.0e-11:
        gates.append("numerical: setup maximum p1 residual exceeded 1e-11")
    return {"apply_count": stage.get("apply_count"), "rss_span_bytes": stage.get("rss_span_bytes"), "linearity_relative": stage.get("linearity_relative"), "repeat_relative": stage.get("repeat_relative")}


def _check_checkpoint(
    fact: dict[str, Any], raw_dir: Path, stage: dict[str, Any], expected_sha: str,
    errors: list[str],
) -> None:
    path = Path(str(fact.get("manifest_path", "")))
    if not path.is_file() or not _path_inside(path, raw_dir):
        errors.append("checkpoint manifest missing or escapes raw directory")
        return
    if fact.get("rank") != 0 or fact.get("mpi_size") != 1:
        errors.append("checkpoint fact rank/MPI identity mismatch")
    if fact.get("manifest_sha256") != _sha256(path):
        errors.append("checkpoint manifest SHA mismatch")
    try:
        manifest = _read_json(path)
        if (
            manifest.get("schema") != CHECKPOINT_SCHEMA
            or manifest.get("solution_only") is not True
            or manifest.get("numeric_allgather") is not False
            or manifest.get("vector_roles") != ["solution"]
            or manifest.get("forbidden_vector_roles") != ["action", "residual", "krylov_basis"]
        ):
            errors.append("checkpoint is not solution-only")
        for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
            if manifest.get(key) != stage.get(key):
                errors.append(f"checkpoint {key} mismatch")
        if manifest.get("source_sha") != expected_sha or manifest.get("mpi_size") != MPI_SIZE or manifest.get("iteration") != fact.get("iteration"):
            errors.append("checkpoint source/iteration/MPI mismatch")
        if not _finite(manifest.get("explicit_true_residual")) or manifest.get("explicit_true_residual") != fact.get("explicit_true_residual"):
            errors.append("checkpoint explicit residual mismatch")
        ranks = manifest.get("ranks")
        if not isinstance(ranks, list) or [item.get("rank") for item in ranks] != [0]:
            errors.append("checkpoint rank inventory mismatch")
        for rank_fact in ranks or ():
            ownership = rank_fact.get("ownership", {})
            descriptor = rank_fact["solution"]
            shard = path.parent / descriptor["relative_path"]
            ownership_range = ownership.get("ownership_range")
            local_size = ownership.get("local_size")
            global_size = ownership.get("global_size")
            if (
                ownership.get("rank") != rank_fact.get("rank")
                or ownership_range != [0, global_size]
                or local_size != global_size
                or not isinstance(local_size, int)
                or local_size <= 0
                or not shard.is_file()
            ):
                errors.append("checkpoint ownership/shard missing")
                continue
            values = np.load(shard, allow_pickle=False)
            if values.dtype != np.dtype(np.complex128) or values.ndim != 1 or values.shape != (local_size,) or not np.all(np.isfinite(values)):
                errors.append("checkpoint solution shard dtype/finite mismatch")
            if descriptor.get("bytes") != shard.stat().st_size or descriptor.get("sha256") != _sha256(shard) or descriptor.get("shape") != list(values.shape) or descriptor.get("dtype") != str(values.dtype):
                errors.append("checkpoint solution descriptor mismatch")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"checkpoint invalid: {exc}")


def _check_positive(record: dict[str, Any], raw_dir: Path, errors: list[str], gates: list[str]) -> dict[str, Any]:
    stage = record.get("stage_facts", {})
    if record.get("reserve") is not None or record.get("retained_ledger", {}).get("route_b", {}).get("restart_reserve_numeric_bytes") != 0:
        errors.append("positive stage retains a forbidden restart reserve")
    if stage.get("source_finite") is not True or stage.get("source_nonzero") is not True or stage.get("source_before_finite") is not True or stage.get("source_before_nonzero") is not True:
        gates.append("numerical: positive source is zero or non-finite")
    if stage.get("source_unchanged") is not True or not _finite(stage.get("rhs_repeat_relative")) or float(stage["rhs_repeat_relative"]) > 1.0e-13:
        gates.append("numerical: positive source/RHS repeat identity failed")
    settings = stage.get("settings", {})
    if (
        settings.get("ksp_type") != "gmres"
        or settings.get("pc_side") != "right"
        or settings.get("norm_type") != "unpreconditioned"
        or settings.get("restart") != RESTART
        or settings.get("cycle_max_it") != RESTART
        or settings.get("max_it") != MAX_IT
        or settings.get("start_iteration") != 0
        or settings.get("initial_guess_nonzero") is not False
        or settings.get("residual_limit") != RESIDUAL_LIMIT
        or settings.get("residual_replacement") is not True
        or settings.get("first_checkpoint_iteration") is not None
        or settings.get("checkpoint_interval") != CHECKPOINT_INTERVAL
    ):
        errors.append("positive KSP/restart/checkpoint settings mismatch")
    cycles = stage.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        errors.append("positive cycle ledger is empty")
        cycles = []
    initial = stage.get("initial_true_residual")
    if not _finite(initial) or abs(float(initial) - 1.0) > 1.0e-13:
        errors.append("positive zero-initial true residual is not one")
    total = 0
    for index, cycle in enumerate(cycles):
        start = int(cycle.get("start_iteration", -1))
        end = int(cycle.get("end_iteration", -1))
        iterations = int(cycle.get("iterations", -1))
        if cycle.get("cycle_index") != index or start != total or end - start != iterations or iterations <= 0 or iterations > RESTART or cycle.get("ksp_destroyed") is not True:
            errors.append("positive cycle ledger is not continuous restart-20 data")
        if cycle.get("initial_guess_nonzero") is not (index > 0):
            errors.append("positive cycle initial-guess ownership does not close")
        if index < len(cycles) - 1 and iterations != RESTART:
            errors.append("non-final positive cycle is shorter than restart=20")
        if not _finite(cycle.get("explicit_true_residual")) or not _finite(cycle.get("reported_final_residual")):
            errors.append("positive cycle residual is non-finite")
        if cycle.get("resource", {}).get("swap_bytes") != 0:
            gates.append("resource: positive cycle swap is nonzero")
        total = end
    if cycles:
        last_cycle = cycles[-1]
        if stage.get("reason") != last_cycle.get("reason"):
            errors.append("positive stage reason does not close the final cycle")
        if not _close(stage.get("final_true_residual"), last_cycle.get("explicit_true_residual"), 1.0e-15):
            errors.append("positive final residual does not close the final cycle")
    if stage.get("iterations") != total or total <= 0 or total > MAX_IT:
        errors.append("positive iteration total mismatch")
    cycle_count = len(cycles)
    for key in ("ksp_create_count", "ksp_destroy_count", "outer_ksp_create_count", "outer_ksp_destroy_count"):
        if stage.get(key) != cycle_count:
            errors.append(f"positive {key} does not close over cycle count")
    if stage.get("matvec_count") != sum(int(cycle.get("matvec_count", -1)) for cycle in cycles) or stage.get("pc_apply_count") != sum(int(cycle.get("pc_apply_count", -1)) for cycle in cycles):
        errors.append("positive matvec/PC counts do not close over cycles")
    if stage.get("vcycle_apply_count") != stage.get("pc_apply_count") or stage.get("p1_solve_count") != stage.get("pc_apply_count"):
        errors.append("positive V-cycle/p1 counts do not close over PC applications")
    if stage.get("explicit_action_count") != stage.get("ksp_create_count", -1) + 4 or stage.get("rhs_action_count") != 1 or stage.get("final_action_recheck_count") != 1 or stage.get("rhs_repeat_action_count") != 1:
        errors.append("positive explicit action count does not close initial/repeat/cycle/final actions")
    transfer_counts = stage.get("transfer_counts")
    if not _transfer_counts_closed(transfer_counts, stage.get("pc_apply_count")):
        errors.append("positive cumulative transfer counts do not close")
    if not _finite(stage.get("max_p1_relative_residual")) or float(stage["max_p1_relative_residual"]) > 1.0e-11:
        gates.append("numerical: positive maximum p1 residual exceeded 1e-11")
    final = stage.get("final_true_residual")
    if not _finite(final) or float(final) > RESIDUAL_LIMIT:
        gates.append("numerical: positive final explicit true residual exceeded 1e-8")
    milestones = stage.get("milestones")
    expected_milestones = {str(value): ("measured" if total >= value else "not_reached") for value in MILESTONE_KEYS}
    if milestones != expected_milestones:
        errors.append("positive milestone status is not independently derivable")
    raw = stage.get("raw", {})
    raw_path = raw_dir / str(raw.get("relative_path", ""))
    if not raw_path.is_file() or raw.get("sha256") != _sha256(raw_path):
        errors.append("positive owned raw array artifact missing or SHA mismatch")
        return {"iterations": total, "final_true_residual": final}
    try:
        with np.load(raw_path, allow_pickle=False) as bundle:
            if set(bundle.files) != set(POSITIVE_RAW_ROLES):
                errors.append("positive raw role inventory mismatch")
            arrays = {name: np.asarray(bundle[name]) for name in bundle.files}
        if any(values.dtype != np.dtype(np.complex128) or values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)) for values in arrays.values()):
            errors.append("positive raw arrays shape/dtype/finite mismatch")
        shapes = {tuple(values.shape) for values in arrays.values()}
        if len(shapes) != 1 or shapes == {()}:
            errors.append("positive raw arrays do not share one non-empty layout")
        if set(raw.get("arrays", {})) != set(POSITIVE_RAW_ROLES):
            errors.append("positive raw descriptor role set mismatch")
        for name in POSITIVE_RAW_ROLES:
            descriptor = raw.get("arrays", {}).get(name, {})
            values = arrays.get(name)
            if values is None or descriptor.get("dtype") != str(values.dtype) or descriptor.get("shape") != list(values.shape) or descriptor.get("bytes") != int(values.nbytes) or descriptor.get("sha256") != _array_sha(values) or descriptor.get("relative_path") != raw_path.name:
                errors.append(f"positive raw descriptor mismatch: {name}")
        if all(name in arrays for name in ("source_before", "source_after", "rhs", "rhs_repeat", "final_action", "final_true_residual")):
            source_unchanged = np.array_equal(arrays["source_before"], arrays["source_after"])
            source_finite = bool(np.all(np.isfinite(arrays["source_before"])))
            source_nonzero = bool(np.linalg.norm(arrays["source_before"]) > 0.0)
            rhs_repeat = float(np.linalg.norm(arrays["rhs_repeat"] - arrays["rhs"]) / max(np.linalg.norm(arrays["rhs"]), np.finfo(float).tiny))
            calculated = float(np.linalg.norm(arrays["rhs"] - arrays["final_action"]) / max(np.linalg.norm(arrays["rhs"]), np.finfo(float).tiny))
            stored = float(np.linalg.norm(arrays["final_true_residual"]) / max(np.linalg.norm(arrays["rhs"]), np.finfo(float).tiny))
            source_authority = stage.get("input_identity_authority")
            raw_facts = stage.get("raw", {})
            expected_source_authority = {
                "source_generation": stage.get("source"),
                "source_before": {
                    "sha256": _array_sha(arrays["source_before"]),
                    "dtype": str(arrays["source_before"].dtype),
                    "shape": list(arrays["source_before"].shape),
                    "ownership_range": raw_facts.get("ownership_range"),
                    "local_size": raw_facts.get("local_size"),
                    "global_size": raw_facts.get("global_size"),
                    "finite": source_finite,
                    "nonzero": source_nonzero,
                },
                "resolved_config_sha256": stage.get("identity_authority", {}).get("resolved_config_sha256"),
                "input_raw_sha256": record.get("input_identity", {}).get("raw_sha256"),
                "physical_model_sha256": stage.get("physical_model_sha256"),
            }
            if source_authority != expected_source_authority or stage.get("input_identity_sha256") != _stable_sha(expected_source_authority):
                errors.append("positive input identity authority does not close from source raw facts")
            if source_finite is not (stage.get("source_finite") is True) or source_finite is not (stage.get("source_before_finite") is True):
                errors.append("positive source finite fact does not bind raw arrays")
            if source_nonzero is not (stage.get("source_nonzero") is True) or source_nonzero is not (stage.get("source_before_nonzero") is True):
                errors.append("positive source nonzero fact does not bind raw arrays")
            if source_unchanged is not (stage.get("source_unchanged") is True):
                errors.append("positive source unchanged fact does not bind raw arrays")
            if not _close(rhs_repeat, stage.get("rhs_repeat_relative"), 1.0e-13):
                errors.append("positive RHS repeat fact does not bind raw arrays")
            if not _close(calculated, stored, 1.0e-13) or not _close(calculated, final, 1.0e-10):
                errors.append("positive final residual raw recomputation mismatch")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"positive raw NPZ invalid: {exc}")
    checkpoints = stage.get("checkpoint_facts")
    expected_checkpoints = list(range(CHECKPOINT_INTERVAL, total + 1, CHECKPOINT_INTERVAL))
    if not isinstance(checkpoints, list) or [item.get("iteration") for item in checkpoints] != expected_checkpoints:
        errors.append("positive checkpoint inventory is not the exact 500-step set")
    for item in checkpoints if isinstance(checkpoints, list) else ():
        _check_checkpoint(item, raw_dir, stage, record["source"]["start"]["expected_sha"], errors)
    return {"iterations": total, "final_true_residual": final, "checkpoint_count": len(checkpoints) if isinstance(checkpoints, list) else 0}


def check_record(record_path: Path, watchdog_path: Path, expected_source_sha: str) -> dict[str, Any]:
    """Return an independent checker result; malformed input is contract-invalid."""

    errors: list[str] = []
    gates: list[str] = []
    try:
        record = _read_json(Path(record_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": CHECKER_SCHEMA, "passed": False, "classification": "CONTRACT_INVALID", "contract_errors": [f"record unreadable: {exc}"], "gate_failures": []}
    if not isinstance(record, dict):
        return {"schema": CHECKER_SCHEMA, "passed": False, "classification": "CONTRACT_INVALID", "contract_errors": ["record is not an object"], "gate_failures": []}
    raw_dir = Path(str(record.get("raw_dir", "")))
    if not raw_dir.is_dir() or Path(str(record.get("record_path", ""))).resolve() != Path(record_path).resolve():
        errors.append("record/raw path identity mismatch")
    try:
        _check_common(record, expected_source_sha, errors)
        _check_architecture(record, errors)
        _check_ledger(record, errors)
        if raw_dir.is_dir():
            _check_markers(record, raw_dir, errors)
        watchdog = _check_watchdog(record, Path(watchdog_path), errors, gates)
        if record.get("stage") == "setup":
            metrics = _check_setup(record, errors, gates)
        elif record.get("stage") == "positive":
            metrics = _check_positive(record, raw_dir, errors, gates)
        else:
            errors.append("unknown R4.1 stage")
            metrics = {}
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        errors.append(f"contract evaluation failed closed: {exc}")
        metrics = {}
        watchdog = {}
    if errors:
        classification = "CONTRACT_INVALID"
    elif gates:
        classification = "RESOURCE_GATE_FAILED" if any(item.startswith("resource:") for item in gates) else "NUMERICAL_GATE_FAILED"
    else:
        classification = "SETUP_EVIDENCE_PASS" if record.get("stage") == "setup" else "POSITIVE_EVIDENCE_PASS"
    return {
        "schema": CHECKER_SCHEMA, "record": str(Path(record_path).resolve()),
        "watchdog": str(Path(watchdog_path).resolve()), "passed": not errors and not gates,
        "classification": classification, "contract_errors": errors,
        "gate_failures": gates, "metrics": metrics,
        "resource": watchdog.get("compact", {}) if isinstance(watchdog, dict) else {},
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
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
