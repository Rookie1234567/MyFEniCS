"""Independent NumPy checker for the V12 Route-A/R3 evidence records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np
from scipy.linalg import eigh


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_interlevel_spectral"
SCHEMA = "task038.full3d.interlevel-spectral.r1-record.v1"
ROUTE_B = "B"
ROUTE_B_SCHEMA = "task038.full3d.interlevel-spectral.r3-record.v1"
ROUTE_B_MARKER_SCHEMA = "task038.full3d.interlevel-spectral.r3-marker.v1"
ROUTE_B_CHECK_SCHEMA = "task038.full3d.interlevel-spectral.r3-check.v1"
ROUTE_B_PROBE_SCHEMA = "task038.route-b.global-probe.v1"
ROUTE_B_STAGE = "r3"
ROUTE_B_LEVELS = (6, 2, 1)
ROUTE_B_PAIRS = ((6, 2), (2, 1))
ROUTE_B_CANDIDATE = "lor_edge_geometric_mg_6_2_1_nested_v1"
MARKER_SCHEMA = "task038.full3d.interlevel-spectral.r1-marker.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
PROBE_NAMES = (
    "random", "gradient", "curl", "checkerboard",
    "physical_component_derived", "r3_long_tail_derived",
)
SOURCE_GENERATION = {
    "random": "native_l2_analytic_values:random",
    "gradient": "native_l2_analytic_values:gradient",
    "curl": "native_l2_analytic_values:curl",
    "checkerboard": "native_l2_analytic_values:checkerboard",
    "physical_component_derived": "s2_physical_rhs.compose_then_high_dual_restrict_then_p63_adjoint",
    "r3_long_tail_derived": "r3_canonical_full_fe_dual_packets_then_high_dual_restrict_then_p63_adjoint",
}
ROUTE_B_SOURCE_GENERATION = {
    **SOURCE_GENERATION,
    "physical_component_derived": "s2_physical_rhs.compose_then_high_dual_restrict_then_p62_adjoint",
    "r3_long_tail_derived": "r3_canonical_full_fe_dual_packets_then_high_dual_restrict_then_p62_adjoint",
}
MATERIAL_ROLE_TAGS = {"air": 1, "substrate": 2, "grating": 3}
R3_LONG_TAIL_MANIFEST_SHA256 = (
    "62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce"
)
R3_LONG_TAIL_SOURCE_SHA = "2c8fca90c7300b85b30021081868b699c0b306d2"
EXPECTED_INPUT_BYTES = 2119
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_BYTES = 4076
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
ALPHA = 0.37 + 0.19j
BETA = -0.23 + 0.41j
HERMITIAN_LIMIT = 1.0e-12
ENDPOINT_LIMIT = 1.0e-10
LAMBDA_MIN_LIMIT = 0.10
LAMBDA_MAX_LIMIT = 10.0
CONDITION_LIMIT = 100.0
PROBE_MIN = 0.10
PROBE_MAX = 10.0
ADJOINT_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
WATCHDOG_RSS_LIMIT = 2_000_000_000
PASS_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "level3_complete", "probes_complete", "release",
)
FAIL_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "local_gate_failed", "level3_not_run", "probes_not_run", "release",
)
ROUTE_B_PASS_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "level2_complete", "probes_complete", "release",
)
ROUTE_B_FAIL_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "local_gate_failed", "level2_not_run", "probes_not_run", "release",
)
A0_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-record.v1"
A0_CHECK_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-check.v1"
A0_MARKER_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-marker.v1"
A0_RAW_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-raw-manifest.v1"
A0_CASES = ("p6-h10-mpi1", "p6-h10-mpi2")
A0_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "level3_complete", "probes_complete", "release",
)
A0_PROBE_ROLES = (
    "source_before", "source_after", "source2", "projected",
    "projected_repeat", "projected2", "projected_combo", "fine_dual",
    "adjoint", "b3", "b6p",
    "fine_primal_local_ids", "fine_primal_local",
    "fine_dual_local_ids", "fine_dual_local",
    "coarse_source_local_ids", "coarse_source_local",
    "explicit_adjoint_local_ids", "explicit_adjoint_local",
    "implemented_adjoint_local_ids", "implemented_adjoint_local",
    "implemented_adjoint_owner_ids", "implemented_adjoint_owner",
)
A0_LIMITS = {
    "pairwise": 1.0e-13,
    "compensated": 1.0e-12,
    "vector": 1.0e-11,
    "ordinary_bound_factor": 4.0,
}
A0_LOCAL_PASS_CLASSIFICATION = "A0_STABLE_ADJOINT_PASS_MPI1_ONLY"
A0_PASS_CLASSIFICATION = "REOPENED_AFTER_STABLE_ADJOINT_CERTIFICATION"
A0_GATE_CLASSIFICATION = "CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE"


def _profile(record: dict[str, Any]) -> dict[str, Any] | None:
    route = record.get("route", "A")
    if route == "A":
        return {
            "route": "A", "schema": SCHEMA, "stage": "r1",
            "marker_schema": MARKER_SCHEMA, "check_schema": "task038.full3d.interlevel-spectral.r1-check.v1",
            "levels": (6, 3), "pair": (6, 3), "coarse_key": "b3",
            "rank": 144, "lambda_min": 0.10, "lambda_max": 10.0,
            "condition": 100.0, "energy": None, "adjoint": 1.0e-12,
            "q_mode": "interval", "q_limit": (0.10, 10.0),
            "source_generation": SOURCE_GENERATION,
            "pass_markers": PASS_MARKERS, "fail_markers": FAIL_MARKERS,
        }
    if route == ROUTE_B:
        return {
            "route": ROUTE_B, "schema": ROUTE_B_SCHEMA, "stage": ROUTE_B_STAGE,
            "candidate": ROUTE_B_CANDIDATE,
            "marker_schema": ROUTE_B_MARKER_SCHEMA, "check_schema": ROUTE_B_CHECK_SCHEMA,
            "levels": ROUTE_B_LEVELS, "pair": (6, 2), "coarse_key": "b2",
            "rank": 54, "lambda_min": 0.50, "lambda_max": 2.0,
            "condition": 4.0, "energy": 1.0e-9, "adjoint": 1.0e-11,
            "q_mode": "center", "q_limit": 1.0e-9,
            "source_generation": ROUTE_B_SOURCE_GENERATION,
            "pass_markers": ROUTE_B_PASS_MARKERS, "fail_markers": ROUTE_B_FAIL_MARKERS,
        }
    return None


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _semantic_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and bool(np.isfinite(float(value)))


def _close(actual: float, reported: Any) -> bool:
    return _finite(reported) and bool(np.isclose(actual, float(reported), rtol=1.0e-10, atol=1.0e-12))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array, dtype=np.complex128).view(np.uint8)).hexdigest()


def _compensated_vdot(left: np.ndarray, right: np.ndarray) -> complex:
    left_values = np.asarray(left, dtype=np.complex128).reshape(-1)
    right_values = np.asarray(right, dtype=np.complex128).reshape(-1)
    products = np.conjugate(left_values) * right_values
    return complex(
        math.fsum(float(value.real) for value in products),
        math.fsum(float(value.imag) for value in products),
    )


def _raw_digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()


def _complex_pair(value: Any) -> complex | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        result = complex(float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result.real) and np.isfinite(result.imag) else None


def _check_runtime_provenance(
    record: dict[str, Any], record_path: Path, expected_sha: str,
    errors: list[str], profile: dict[str, Any],
) -> bool:
    provenance_error = False
    if record.get("schema") != profile["schema"]:
        errors.append("record schema mismatch")
    if profile["route"] == ROUTE_B and record.get("candidate") != ROUTE_B_CANDIDATE:
        errors.append("Route-B candidate identity mismatch")
    if record.get("stage") != profile["stage"] or record.get("case") != "p6-h10-mpi1":
        errors.append("stage/case mismatch")
    if record.get("degree") != 6 or record.get("h_nm") != 10.0 or record.get("wavelength_nm") != 13.5 or record.get("mpi_size") != 1:
        errors.append("fixed p6/h10/MPI1 identity mismatch")
    if record.get("branch") != BRANCH:
        errors.append("branch mismatch")
        provenance_error = True
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source identity is missing")
        provenance_error = True
    else:
        for name in ("start", "end"):
            item = source.get(name)
            if not isinstance(item, dict) or item.get("commit_sha") != expected_sha or item.get("branch") != BRANCH or item.get("clean") is not True:
                errors.append(f"source {name} identity is not closed")
                provenance_error = True
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime identity is missing")
        provenance_error = True
    else:
        if runtime.get("qualified_activation") != "1":
            errors.append("qualified activation mismatch")
            provenance_error = True
        if runtime.get("mpi_size") != 1 or runtime.get("scalar_dtype") != "complex128" or runtime.get("int_dtype") != "int32":
            errors.append("runtime ABI mismatch")
            provenance_error = True
        threads = runtime.get("threads")
        if not isinstance(threads, dict) or any(threads.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            errors.append("thread identity mismatch")
            provenance_error = True
    command = record.get("command")
    raw_dir = record.get("raw_dir")
    record_string = record.get("record_path")
    expected_command_length = 21 if profile["route"] == ROUTE_B else 19
    if not isinstance(command, list) or len(command) != expected_command_length or not all(isinstance(value, str) for value in command) or not isinstance(raw_dir, str) or not isinstance(record_string, str):
        errors.append("worker command/raw path is missing")
        provenance_error = True
    else:
        runtime_executable = runtime.get("sys_executable") if isinstance(runtime, dict) else None
        expected_input = str((Path(__file__).resolve().parents[1] / "input/templates/full3d_iterative_example.dat").resolve())
        expected_command = [
            str(runtime_executable), "-m", MODULE,
            "--stage", profile["stage"], "--case", "p6-h10-mpi1",
            "--raw-dir", raw_dir, "--record", record_string,
            "--expected-source-sha", expected_sha,
            "--expected-mpi-size", "1", "--input", expected_input,
            "--r3-long-tail-manifest",
        ]
        manifest_path = None
        provenance = record.get("provenance")
        if isinstance(provenance, dict):
            manifest_path = provenance.get("r3_long_tail_manifest_path")
        expected_command.append(str(manifest_path))
        if profile["route"] == ROUTE_B:
            expected_command.extend(("--route", "b"))
        if not Path(command[0]).is_absolute() or command != expected_command:
            errors.append("worker command executable/module/stage/case mismatch")
            provenance_error = True
        if profile["route"] == ROUTE_B and record.get("route") != ROUTE_B:
            errors.append("Route-B route identity is missing")
            provenance_error = True
        manifest_index = 18 if profile["route"] == "A" else 18
        if not Path(command[manifest_index]).is_absolute() or record_string == raw_dir:
            errors.append("worker command R3 manifest binding is missing")
            provenance_error = True
    input_identity = record.get("input_identity")
    if not isinstance(input_identity, dict) or input_identity.get("path_relative") != "input/templates/full3d_iterative_example.dat" or input_identity.get("raw_bytes") != EXPECTED_INPUT_BYTES or input_identity.get("raw_sha256") != EXPECTED_INPUT_SHA256 or input_identity.get("resolved_bytes") != EXPECTED_RESOLVED_BYTES or input_identity.get("resolved_sha256") != EXPECTED_RESOLVED_SHA256 or input_identity.get("physical_model_sha256") != EXPECTED_PHYSICAL_MODEL_SHA256:
        errors.append("fixed input identity mismatch")
        provenance_error = True
    p = record.get("provenance")
    if not isinstance(p, dict) or p.get("r3_long_tail_expected_sha256") != R3_LONG_TAIL_MANIFEST_SHA256 or p.get("r3_long_tail_source_sha") != R3_LONG_TAIL_SOURCE_SHA:
        errors.append("R3 provenance identity mismatch")
        provenance_error = True
    else:
        r3_path = Path(str(p.get("r3_long_tail_manifest_path", "")))
        actual_manifest_sha = _sha256(r3_path) if r3_path.is_file() else None
        if (
            not r3_path.is_absolute()
            or not r3_path.is_file()
            or actual_manifest_sha != R3_LONG_TAIL_MANIFEST_SHA256
            or p.get("r3_long_tail_manifest_sha256") != actual_manifest_sha
            or not isinstance(command, list)
            or len(command) != (21 if profile["route"] == ROUTE_B else 19)
            or command[18] != str(r3_path.resolve())
        ):
            errors.append("R3 manifest is missing or SHA-bound identity failed")
            provenance_error = True
    if record.get("record_path") != str(record_path.resolve()) or not Path(str(raw_dir)).is_absolute() or Path(str(raw_dir)).resolve() == record_path.resolve():
        errors.append("record path identity mismatch")
        provenance_error = True
    return provenance_error


def _watchdog_command_validation(
    actual: Any, expected: Any, mpi_size: Any, *, a0: bool,
) -> tuple[bool, str]:
    if a0 and mpi_size == 2:
        if (
            isinstance(actual, list)
            and isinstance(expected, list)
            and len(actual) >= 4
            and isinstance(actual[0], str)
            and Path(actual[0]).is_absolute()
            and Path(actual[0]).name == "mpiexec"
            and actual[1:3] == ["-n", "2"]
            and actual[3:] == expected
        ):
            return True, "mpiexec_n2"
        return False, "invalid"
    if mpi_size == 1 and actual == expected:
        return True, "direct"
    if actual == expected:
        return True, "direct"
    return False, "invalid"


def _check_watchdog(compact_path: Path, record: dict[str, Any], record_path: Path,
                    expected_sha: str, errors: list[str], gates: list[str],
                    lifecycle_failures: list[str], *, mpi_size: Any = None,
                    allow_mpiexec_n2: bool = False) -> dict[str, Any]:
    try:
        compact = _read_json(compact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"watchdog compact unreadable: {exc}")
        return {}
    if compact.get("schema") != WATCHDOG_SCHEMA:
        errors.append("watchdog schema mismatch")
    if compact.get("source_sha") != expected_sha:
        errors.append("watchdog source SHA mismatch")
    command_valid, launcher_identity = _watchdog_command_validation(
        compact.get("worker_command"), record.get("command"),
        record.get("mpi_size") if mpi_size is None else mpi_size,
        a0=record.get("schema") == A0_SCHEMA or allow_mpiexec_n2,
    )
    if not command_valid:
        errors.append("watchdog worker command mismatch")
    if Path(str(compact.get("worker_record", ""))).resolve() != record_path.resolve():
        errors.append("watchdog worker record mismatch")
    if Path(str(compact.get("worker_raw_dir", ""))).resolve() != Path(str(record.get("raw_dir", ""))).resolve():
        errors.append("watchdog worker raw path mismatch")
    raw_path = Path(str(compact.get("watchdog_raw", "")))
    samples: list[dict[str, Any]] = []
    if not raw_path.is_absolute() or not raw_path.is_file():
        errors.append("watchdog raw ledger missing/relative")
    else:
        if _sha256(raw_path) != compact.get("raw_sha256"):
            errors.append("watchdog raw SHA mismatch")
        for number, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=_reject_constant)
            except (ValueError, json.JSONDecodeError) as exc:
                errors.append(f"watchdog raw line {number} invalid: {exc}")
                continue
            if isinstance(row, dict):
                samples.append(row)
            else:
                errors.append(f"watchdog raw line {number} is not an object")
    rss: list[int] = []
    swaps: list[int] = []
    readable: list[bool] = []
    for row in samples:
        tree = row.get("authority", {}).get("process_tree", {})
        if type(tree.get("rss_bytes")) is not int or tree["rss_bytes"] < 0:
            errors.append("watchdog RSS sample invalid")
        else:
            rss.append(int(tree["rss_bytes"]))
        if type(tree.get("swap_bytes")) is not int or tree["swap_bytes"] < 0:
            errors.append("watchdog swap sample invalid")
        else:
            swaps.append(int(tree["swap_bytes"]))
        readable.append(tree.get("all_status_readable") is True)
    peak = max(rss, default=-1)
    swap = max(swaps, default=-1)
    all_readable = bool(samples) and len(readable) == len(samples) and all(readable)
    if compact.get("sample_count") != len(samples) or compact.get("peak_process_tree_rss_bytes") != peak or compact.get("max_process_tree_swap_bytes") != swap or compact.get("all_status_readable") is not all_readable:
        errors.append("watchdog compact is not raw-derived")
    if compact.get("watchdog_poll_seconds") != 0.25 or compact.get("watchdog_rss_limit_bytes") != WATCHDOG_RSS_LIMIT:
        errors.append("watchdog frozen settings mismatch")
    if compact.get("returncode") != 0:
        lifecycle_failures.append("watchdog worker returncode is nonzero")
    if compact.get("natural_exit") is not True:
        lifecycle_failures.append("watchdog did not report natural_exit")
    if compact.get("no_orphan") is not True:
        lifecycle_failures.append("watchdog reported an orphan")
    if compact.get("stop_reason") != "natural_exit":
        lifecycle_failures.append("watchdog stop_reason is not natural_exit")
    if not all_readable or peak < 0 or peak >= WATCHDOG_RSS_LIMIT or swap != 0:
        gates.append("external watchdog resource Gate failed")
    return {
        "sample_count": len(samples),
        "peak_process_tree_rss_bytes": peak,
        "max_process_tree_swap_bytes": swap,
        "all_status_readable": all_readable,
        "natural_exit": compact.get("natural_exit"),
        "no_orphan": compact.get("no_orphan"),
        "stop_reason": compact.get("stop_reason"),
        "watchdog_compact": str(compact_path.resolve()),
        "watchdog_compact_sha256": _sha256(compact_path),
        "watchdog_raw": str(raw_path.resolve()),
        "watchdog_raw_sha256": _sha256(raw_path) if raw_path.is_file() else None,
        "worker_command_launcher": launcher_identity,
        "worker_command_valid": command_valid,
        "resource_gate_failed": bool(not all_readable or peak < 0 or peak >= WATCHDOG_RSS_LIMIT or swap != 0),
        "execution_lifecycle_failed": bool(lifecycle_failures),
    }


def _check_markers(
    record: dict[str, Any], raw_dir: Path, expected_sha: str,
    errors: list[str], profile: dict[str, Any],
) -> None:
    info = record.get("markers")
    expected = profile["pass_markers"] if record.get("local_gate_passed") is True else profile["fail_markers"] if record.get("local_gate_passed") is False else ()
    if not isinstance(info, dict) or tuple(info.get("names", ())) != expected:
        errors.append("marker list mismatch")
        return
    names = tuple(info["names"])
    wall_times = info.get("wall_time_ns")
    if not isinstance(wall_times, dict) or set(wall_times) != set(names):
        errors.append("record marker wall-time map is not exact")
    marker_dir = raw_dir / str(info.get("relative_dir", ""))
    times = []
    for name in names:
        path = marker_dir / f"{name}.json"
        if not _inside(path, raw_dir) or not path.is_file():
            errors.append(f"marker missing/escaped: {name}")
            continue
        try:
            row = _read_json(path)
            if row.get("schema") != profile["marker_schema"] or row.get("marker") != name or row.get("source_sha") != expected_sha:
                errors.append(f"marker identity mismatch: {name}")
            timestamp = row["wall_time_ns"]
            if type(timestamp) is not int or timestamp <= 0 or not isinstance(wall_times, dict) or wall_times.get(name) != timestamp:
                errors.append(f"marker wall-time mismatch: {name}")
            else:
                times.append(timestamp)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"marker unreadable: {name}: {exc}")
    closeout = marker_dir / "record_closeout.json"
    if not closeout.is_file():
        errors.append("record_closeout marker is missing")
    else:
        try:
            closeout_row = _read_json(closeout)
            closeout_facts = closeout_row.get("facts")
            closeout_time = closeout_row.get("wall_time_ns")
            release_time = wall_times.get("release") if isinstance(wall_times, dict) else None
            if closeout_row.get("schema") != profile["marker_schema"] or closeout_row.get("marker") != "record_closeout" or closeout_row.get("source_sha") != expected_sha or type(closeout_time) is not int or type(release_time) is not int or closeout_time <= release_time or not isinstance(closeout_facts, dict) or closeout_facts.get("record_path") != str(record.get("record_path")) or closeout_facts.get("record_sha256") != _sha256(Path(str(record.get("record_path")))):
                errors.append("record_closeout marker is not bound to the written record")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"record_closeout marker unreadable: {exc}")
    allowed_files = {f"{name}.json" for name in names} | {"record_closeout.json"}
    if marker_dir.is_dir() and {path.name for path in marker_dir.glob("*.json")} != allowed_files:
        errors.append("marker directory contains an unauthorized marker")
    if len(times) == len(names) and times != sorted(times):
        errors.append("marker sequence is not monotonic")


def _check_level_topology(
    architecture: Any, errors: list[str], level_names: tuple[int, ...] = (6, 3),
) -> None:
    """Close the compact parent/raw topology facts without loading topology arrays."""

    if not isinstance(architecture, dict) or not isinstance(architecture.get("levels"), dict):
        errors.append("level topology facts are missing")
        return
    required_text = {
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
    }
    for degree in level_names:
        level_name = f"level{degree}"
        level = architecture["levels"].get(level_name)
        if not isinstance(level, dict):
            errors.append(f"level facts missing: {level_name}")
            continue
        parent = level.get("parent_topology")
        raw = level.get("raw_topology")
        if not isinstance(parent, dict) or not isinstance(raw, dict):
            errors.append(f"parent/raw topology facts missing: {level_name}")
            continue
        for role, topology in (("parent", parent), ("raw", raw)):
            for name, expected in (
                ("owner_local_maps", True),
                ("numeric_allgather", False),
                ("global_transfer_matrix", False),
                ("slave_master_complete", True),
            ):
                if topology.get(name) is not expected:
                    errors.append(f"{level_name}.{role}.{name} is not closed")
            for name, expected in required_text.items():
                if topology.get(name) != expected:
                    errors.append(f"{level_name}.{role}.{name} identity mismatch")
            if type(topology.get("global_unique_edge_count")) is not int or topology["global_unique_edge_count"] <= 0:
                errors.append(f"{level_name}.{role}.global_unique_edge_count invalid")
            for name in ("local_unique_edge_count", "owned_unique_edge_count"):
                if type(topology.get(name)) is not int or topology[name] <= 0:
                    errors.append(f"{level_name}.{role}.{name} invalid")
        if isinstance(parent.get("global_unique_edge_count"), int) and isinstance(raw.get("global_unique_edge_count"), int):
            if parent["global_unique_edge_count"] != raw["global_unique_edge_count"]:
                errors.append(f"{level_name} parent/raw global topology inventory mismatch")
        for role, key in (("parent", "parent_global_unique_rows"), ("raw", "raw_global_unique_rows")):
            if level.get(key) != level[role + "_topology"].get("global_unique_edge_count"):
                errors.append(f"{level_name}.{key} is not bound to topology audit")


def _load_array(name: str, loaded: Any, descriptor: dict[str, Any], errors: list[str]) -> np.ndarray | None:
    if name not in loaded.files:
        errors.append(f"raw array missing: {name}")
        return None
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("dtype"), str) or not isinstance(descriptor.get("shape"), list) or not isinstance(descriptor.get("sha256"), str):
        errors.append(f"raw array descriptor malformed: {name}")
        return None
    value = np.asarray(loaded[name])
    try:
        expected_shape = tuple(int(item) for item in descriptor["shape"])
    except (TypeError, ValueError):
        errors.append(f"raw array shape descriptor malformed: {name}")
        return None
    if str(value.dtype) != descriptor.get("dtype") or value.shape != expected_shape or value.dtype.hasobject:
        errors.append(f"raw array descriptor mismatch: {name}")
        return None
    if _raw_digest(value) != descriptor.get("sha256") or not np.all(np.isfinite(value)):
        errors.append(f"raw array SHA/finite mismatch: {name}")
        return None
    return np.ascontiguousarray(value)


def _hermitian_defect(matrix: np.ndarray) -> float:
    return float(np.linalg.norm(matrix - matrix.conj().T) / max(np.linalg.norm(matrix), np.finfo(float).tiny))


def _endpoint_residual(g: np.ndarray, b: np.ndarray, value: float, vector: np.ndarray) -> float:
    residual = g @ vector - value * (b @ vector)
    denominator = max(np.linalg.norm(g @ vector), abs(value) * np.linalg.norm(b @ vector), np.finfo(float).tiny)
    return float(np.linalg.norm(residual) / denominator)


def _check_nested_class(
    item: dict[str, Any], arrays: dict[str, np.ndarray], errors: list[str],
    gates: list[str], profile: dict[str, Any],
) -> dict[str, Any]:
    identity = item.get("class_identity")
    digest = item.get("class_digest")
    if not isinstance(identity, dict) or not isinstance(digest, str) or _semantic_sha(identity) != digest:
        errors.append("nested material class identity/digest mismatch")
        return {}
    prefix = f"class_{digest}"
    p62 = arrays.get("p62")
    b2 = arrays.get(f"{prefix}__b2")
    b6p = arrays.get(f"{prefix}__b6p")
    eigenvector_min = arrays.get(f"{prefix}__eigenvector_min")
    eigenvector_max = arrays.get(f"{prefix}__eigenvector_max")
    required = (p62, b2, b6p, eigenvector_min, eigenvector_max)
    if any(value is None for value in required):
        errors.append(f"nested material class arrays missing: {digest}")
        return {}
    if any(value.dtype != np.dtype("complex128") for value in required):
        errors.append(f"nested material class dtype mismatch: {digest}")
        return {}
    if p62.shape != (882, 54) or b2.shape != (54, 54) or b6p.shape != (882, 54) or eigenvector_min.shape != (54,) or eigenvector_max.shape != (54,):
        errors.append(f"nested material class array shape mismatch: {digest}")
        return {}
    g62 = p62.conj().T @ b6p
    singular = np.linalg.svd(p62, compute_uv=False)
    threshold = max(p62.shape) * np.finfo(float).eps * float(singular[0])
    rank = int(np.count_nonzero(singular > threshold))
    b2_values = np.linalg.eigvalsh(b2)
    g_values = np.linalg.eigvalsh(g62)
    defect_b2, defect_g = _hermitian_defect(b2), _hermitian_defect(g62)
    minimum_b2, minimum_g = float(b2_values[0]), float(g_values[0])
    try:
        values, _vectors = eigh(g62, b2, driver="gvd", check_finite=True)
    except (np.linalg.LinAlgError, ValueError):
        gates.append(f"nested class {digest} generalized eigensolver failed")
        return {"class_digest": digest, "rank": rank, "finite": False, "gate_passed": False}
    lambda_min, lambda_max = float(values[0]), float(values[-1])
    condition = lambda_max / lambda_min if lambda_min > 0.0 else math.inf
    residual_min = _endpoint_residual(g62, b2, lambda_min, eigenvector_min)
    residual_max = _endpoint_residual(g62, b2, lambda_max, eigenvector_max)
    nested_energy = float(
        np.linalg.norm(g62 - b2) / max(np.linalg.norm(b2), np.finfo(float).tiny)
    )
    finite = bool(all(np.all(np.isfinite(value)) for value in (
        p62, b2, b6p, eigenvector_min, eigenvector_max, singular,
        b2_values, g_values, values,
    )))
    checks = (
        (rank == profile["rank"], "rank"),
        (defect_b2 <= HERMITIAN_LIMIT, "B2 Hermitian"),
        (defect_g <= HERMITIAN_LIMIT, "G62 Hermitian"),
        (minimum_b2 > 0.0, "B2 SPD"), (minimum_g > 0.0, "G62 SPD"),
        (lambda_min >= profile["lambda_min"], "lambda_min"),
        (lambda_max <= profile["lambda_max"], "lambda_max"),
        (condition <= profile["condition"], "condition"),
        (residual_min <= ENDPOINT_LIMIT, "smallest endpoint residual"),
        (residual_max <= ENDPOINT_LIMIT, "largest endpoint residual"),
        (nested_energy <= float(profile["energy"]), "nested energy"),
        (finite, "finite"),
    )
    for passed, label in checks:
        if not passed:
            gates.append(f"nested class {digest} {label} failed")
    actual = (
        (rank, "rank"), (float(singular[-1]), "sigma_min"),
        (float(singular[0]), "sigma_max"), (defect_b2, "hermitian_defect_b2"),
        (defect_g, "hermitian_defect_g62"), (minimum_b2, "minimum_eigenvalue_b2"),
        (minimum_g, "minimum_eigenvalue_g62"), (lambda_min, "lambda_min"),
        (lambda_max, "lambda_max"), (condition, "spectral_condition"),
        (residual_min, "endpoint_residual_min"),
        (residual_max, "endpoint_residual_max"),
        (nested_energy, "nested_energy_relative"),
    )
    for value, key in actual:
        if not _close(float(value), item.get(key)):
            errors.append(f"nested material class stored field mismatch: {key}")
    if (
        item.get("method") != "lor_edge_geometric_mg_6_2_1_nested_v1"
        or item.get("p62_shape") != [882, 54]
        or item.get("b2_shape") != [54, 54]
        or item.get("b6p_shape") != [882, 54]
        or item.get("nested_tiled_geometric") is not True
        or item.get("generic_high_polynomial_reconstruction") is not False
        or item.get("b6_dense_retained") is not False
        or item.get("g62_dense_retained") is not False
    ):
        errors.append(f"nested material class fixed architecture facts mismatch: {digest}")
    if item.get("strict_spd_b2") is not bool(minimum_b2 > 0.0) or item.get("strict_spd_g62") is not bool(minimum_g > 0.0):
        errors.append(f"nested material class SPD facts mismatch: {digest}")
    if item.get("finite") is not finite:
        errors.append(f"nested material class finite field mismatch: {digest}")
    gate_passed = bool(all(passed for passed, _label in checks))
    if item.get("gate_passed") is not gate_passed:
        errors.append(f"nested material class stored Gate mismatch: {digest}")
    return {
        "class_digest": digest, "rank": rank, "sigma_min": float(singular[-1]),
        "sigma_max": float(singular[0]), "lambda_min": lambda_min,
        "lambda_max": lambda_max, "spectral_condition": condition,
        "nested_energy_relative": nested_energy,
        "endpoint_residual_min": residual_min,
        "endpoint_residual_max": residual_max, "finite": finite,
        "gate_passed": gate_passed,
    }


def _check_class(
    item: dict[str, Any], arrays: dict[str, np.ndarray], errors: list[str],
    gates: list[str], profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile is not None and profile["route"] == ROUTE_B:
        return _check_nested_class(item, arrays, errors, gates, profile)
    identity = item.get("class_identity")
    digest = item.get("class_digest")
    if not isinstance(identity, dict) or not isinstance(digest, str) or _semantic_sha(identity) != digest:
        errors.append("material class identity/digest mismatch")
        return {}
    prefix = f"class_{digest}"
    p63 = arrays.get("p63")
    b3 = arrays.get(f"{prefix}__b3")
    b6p = arrays.get(f"{prefix}__b6p")
    eigenvector_min = arrays.get(f"{prefix}__eigenvector_min")
    eigenvector_max = arrays.get(f"{prefix}__eigenvector_max")
    if p63 is None:
        errors.append("P63 is unavailable for material class recomputation")
        return {}
    if b3 is None or b6p is None or eigenvector_min is None or eigenvector_max is None:
        errors.append(f"material class arrays missing: {digest}")
        return {}
    if b3.dtype != np.dtype("complex128") or b6p.dtype != np.dtype("complex128") or eigenvector_min.dtype != np.dtype("complex128") or eigenvector_max.dtype != np.dtype("complex128"):
        errors.append(f"material class dtype mismatch: {digest}")
        return {}
    if b3.shape != (144, 144) or b6p.shape != (882, 144) or eigenvector_min.shape != (144,) or eigenvector_max.shape != (144,):
        errors.append(f"material class array shape mismatch: {digest}")
        return {}
    g63 = p63.conj().T @ b6p
    singular = np.linalg.svd(p63, compute_uv=False)
    threshold = max(p63.shape) * np.finfo(float).eps * float(singular[0])
    rank = int(np.count_nonzero(singular > threshold))
    b3_values = np.linalg.eigvalsh(b3)
    g_values = np.linalg.eigvalsh(g63)
    defect_b3, defect_g = _hermitian_defect(b3), _hermitian_defect(g63)
    minimum_b3, minimum_g = float(b3_values[0]), float(g_values[0])
    try:
        values, vectors = eigh(g63, b3, driver="gvd", check_finite=True)
    except (np.linalg.LinAlgError, ValueError):
        gates.append(f"class {digest} generalized eigensolver failed")
        return {"class_digest": digest, "rank": rank, "finite": False, "gate_passed": False}
    lambda_min, lambda_max = float(values[0]), float(values[-1])
    residual_min = _endpoint_residual(g63, b3, lambda_min, eigenvector_min)
    residual_max = _endpoint_residual(g63, b3, lambda_max, eigenvector_max)
    condition = lambda_max / lambda_min if lambda_min > 0.0 else math.inf
    finite = bool(all(np.all(np.isfinite(value)) for value in (p63, b3, b6p, eigenvector_min, eigenvector_max, singular, b3_values, g_values, values, vectors)))
    reported = item
    checks = (
        (rank == 144, "rank"), (defect_b3 <= HERMITIAN_LIMIT, "B3 Hermitian"),
        (defect_g <= HERMITIAN_LIMIT, "G63 Hermitian"), (minimum_b3 > 0.0, "B3 SPD"),
        (minimum_g > 0.0, "G63 SPD"), (lambda_min >= LAMBDA_MIN_LIMIT, "lambda_min"),
        (lambda_max <= LAMBDA_MAX_LIMIT, "lambda_max"), (condition <= CONDITION_LIMIT, "condition"),
        (residual_min <= ENDPOINT_LIMIT, "smallest endpoint residual"),
        (residual_max <= ENDPOINT_LIMIT, "largest endpoint residual"), (finite, "finite"),
        (np.linalg.norm(eigenvector_min) > 0.0, "smallest endpoint eigenvector"),
        (np.linalg.norm(eigenvector_max) > 0.0, "largest endpoint eigenvector"),
    )
    for passed, label in checks:
        if not passed:
            gates.append(f"class {digest} {label} failed")
    for actual, key in ((rank, "rank"), (float(singular[-1]), "sigma_min"), (float(singular[0]), "sigma_max"), (defect_b3, "hermitian_defect_b3"), (defect_g, "hermitian_defect_g63"), (minimum_b3, "minimum_eigenvalue_b3"), (minimum_g, "minimum_eigenvalue_g63"), (lambda_min, "lambda_min"), (lambda_max, "lambda_max"), (condition, "spectral_condition"), (residual_min, "endpoint_residual_min"), (residual_max, "endpoint_residual_max")):
        if not _close(float(actual), reported.get(key)):
            errors.append(f"material class stored field mismatch: {key}")
    if reported.get("finite") is not finite:
        errors.append("material class finite field mismatch")
    gate_passed = bool(all(passed for passed, _label in checks))
    if reported.get("gate_passed") is not gate_passed:
        errors.append(f"material class stored Gate mismatch: {digest}")
    return {
        "class_digest": digest, "rank": rank, "sigma_min": float(singular[-1]),
        "sigma_max": float(singular[0]), "lambda_min": lambda_min,
        "lambda_max": lambda_max, "spectral_condition": condition,
        "endpoint_residual_min": residual_min, "endpoint_residual_max": residual_max,
        "finite": finite,
        "gate_passed": gate_passed,
    }


def _check_probe(
    item: dict[str, Any],
    arrays: dict[str, np.ndarray],
    descriptors: dict[str, Any],
    errors: list[str],
    gates: list[str],
    expected_coarse_rows: int,
    expected_fine_rows: int,
    *,
    coarse_action_key: str = "b3",
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = item.get("name")
    roles = item.get("raw_roles")
    if not isinstance(name, str) or not isinstance(roles, dict):
        errors.append("probe name/raw roles missing")
        return {}
    if profile is not None and profile["route"] == "B":
        if item.get("schema") != ROUTE_B_PROBE_SCHEMA:
            errors.append(f"Route-B probe schema mismatch: {name}")
        if item.get("coarse_action_role") != "B2":
            errors.append(f"Route-B probe coarse action role mismatch: {name}")
    required = tuple((key, roles.get(key)) for key in ("source_before", "source_after", "source2", "projected", "projected_repeat", "projected2", "projected_combo", "fine_dual", "adjoint", coarse_action_key, "b6p"))
    if any(not isinstance(key, str) or key not in arrays for _role, key in required):
        errors.append(f"probe raw roles missing: {name}")
        return {}
    x, xa, x2, p, pr, p2, pc, y, ph, coarse_action, b6p = (arrays[key] for _role, key in required)
    coarse = (x, xa, x2, ph, coarse_action)
    fine = (p, pr, p2, pc, y, b6p)
    if (
        any(value.dtype != np.dtype("complex128") or value.ndim != 1 or value.size == 0 for value in coarse + fine)
        or any(value.shape != (expected_coarse_rows,) for value in coarse)
        or any(value.shape != (expected_fine_rows,) for value in fine)
    ):
        errors.append(f"probe shape closure failed: {name}")
        return {}
    repeat = float(np.linalg.norm(pr - p) / max(np.linalg.norm(p), np.finfo(float).tiny))
    linearity = float(np.linalg.norm(pc - ALPHA * p - BETA * p2) / max(np.linalg.norm(pc), np.finfo(float).tiny))
    if profile is not None and profile["route"] == "B":
        lhs, rhs = _compensated_vdot(p, y), _compensated_vdot(x, ph)
    else:
        lhs, rhs = np.vdot(p, y), np.vdot(x, ph)
    lhs_abs = float(abs(lhs))
    rhs_abs = float(abs(rhs))
    absolute_defect = float(abs(lhs - rhs))
    adjoint = float(absolute_defect / max(lhs_abs, rhs_abs, np.finfo(float).tiny))
    ec, ef = np.vdot(x, coarse_action), np.vdot(p, b6p)
    if not (np.isfinite(ec.real) and np.isfinite(ec.imag) and abs(ec) > 0.0):
        gates.append(f"probe {name} coarse energy denominator invalid")
        ratio = complex(np.nan, np.nan)
    else:
        ratio = ef / ec
    finite = bool(all(np.all(np.isfinite(value)) for value in (x, xa, x2, p, pr, p2, pc, y, ph, coarse_action, b6p)))
    unchanged = _digest(x) == _digest(xa) == item.get("source_before_digest") == item.get("source_after_digest")
    source_norm = float(np.linalg.norm(x))
    source_finite = bool(np.all(np.isfinite(x)))
    source_nonzero = bool(source_norm > 0.0)
    if not finite:
        gates.append(f"probe {name} nonfinite")
    if not source_finite or not source_nonzero:
        gates.append(f"probe {name} source is zero")
    repeat_limit = REPEAT_LIMIT if profile is None else (1.0e-13)
    linearity_limit = LINEARITY_LIMIT if profile is None else (1.0e-12)
    adjoint_limit = ADJOINT_LIMIT if profile is None else float(profile["adjoint"])
    if repeat > repeat_limit:
        gates.append(f"probe {name} repeat failed")
    if linearity > linearity_limit:
        gates.append(f"probe {name} linearity failed")
    if adjoint > adjoint_limit:
        gates.append(f"probe {name} adjoint failed")
    if profile is not None and profile["q_mode"] == "center":
        q_failed = abs(ratio.real - 1.0) > float(profile["q_limit"])
    else:
        q_failed = not PROBE_MIN <= ratio.real <= PROBE_MAX
    if q_failed or abs(ratio.imag) > HERMITIAN_LIMIT:
        gates.append(f"probe {name} q outside frozen interval")
    if not unchanged or item.get("input_unchanged") is not True:
        gates.append(f"probe {name} input changed")
    if item.get("phase_once") is not True:
        gates.append(f"probe {name} phase contract failed")
    if item.get("finite") is not finite or item.get("source_finite") is not source_finite or item.get("source_nonzero") is not source_nonzero:
        errors.append(f"probe {name} stored finite/source fact mismatch")
    if not _close(source_norm, item.get("source_norm")):
        errors.append(f"probe {name} stored field mismatch: source_norm")
    expected_generation = (
        SOURCE_GENERATION if profile is None else profile["source_generation"]
    )
    if item.get("source_generation") != expected_generation.get(name):
        errors.append(f"probe {name} source-generation identity mismatch")
    for actual, key in ((float(ratio.real), "q"), (float(abs(ratio.imag)), "q_imag_defect"), (repeat, "repeat_relative"), (linearity, "linearity_relative"), (adjoint, "adjoint_work_relative")):
        if not _close(actual, item.get(key)):
            errors.append(f"probe {name} stored field mismatch: {key}")
    for actual, key in ((ec, "energy_coarse"), (ef, "energy_fine")):
        if _complex_pair(item.get(key)) is None or not np.isclose(actual, _complex_pair(item.get(key)), rtol=1.0e-10, atol=1.0e-12):
            errors.append(f"probe {name} stored energy mismatch: {key}")
    energy_imag = float(max(abs(ec.imag), abs(ef.imag)))
    if not _close(energy_imag, item.get("energy_imag_defect")):
        errors.append(f"probe {name} stored field mismatch: energy_imag_defect")
    return {
        "name": name,
        "q": float(ratio.real),
        "repeat_relative": repeat,
        "linearity_relative": linearity,
        "adjoint_work_relative": adjoint,
        "adjoint_lhs_abs": lhs_abs,
        "adjoint_rhs_abs": rhs_abs,
        "adjoint_absolute_defect": absolute_defect,
        "finite": finite,
        "input_unchanged": unchanged,
    }


def _check_local_transfer(
    name: str, matrix: np.ndarray | None, facts: Any, errors: list[str],
    gates: list[str], expected_shape: tuple[int, int], profile: dict[str, Any],
) -> dict[str, Any]:
    if matrix is None or not isinstance(facts, dict):
        errors.append(f"Route-B local transfer missing: {name}")
        return {}
    if matrix.dtype != np.dtype("complex128") or matrix.shape != expected_shape or not np.all(np.isfinite(matrix)):
        errors.append(f"Route-B local transfer raw shape/dtype/finite mismatch: {name}")
        return {}
    local_map = facts.get("local_map")
    if not isinstance(local_map, dict):
        errors.append(f"Route-B local transfer map audit missing: {name}")
        return {}
    expected_pair = [6, 2] if name == "6_2" else [2, 1]
    if facts.get("pair") != expected_pair:
        errors.append(f"Route-B local transfer pair mismatch: {name}")
    if facts.get("global_transfer_matrix") is not False:
        errors.append(f"Route-B local transfer reports global map: {name}")
    if facts.get("numeric_allgather") is not False:
        errors.append(f"Route-B local transfer reports numeric allgather: {name}")
    node_shape = (343, 27) if name == "6_2" else (27, 8)
    observed = {
        "edge_rows": int(matrix.shape[0]), "edge_cols": int(matrix.shape[1]),
        "edge_exact_nnz": int(np.count_nonzero(matrix)),
        "edge_numeric_bytes": int(matrix.nbytes),
        "node_rows": node_shape[0], "node_cols": node_shape[1],
    }
    audit = facts.get("local_transfer")
    if not isinstance(audit, dict):
        errors.append(f"Route-B local transfer local audit missing: {name}")
        return observed
    if (
        audit.get("schema") != "task038.local_interlevel_edge_transfer.v1"
        or audit.get("fine_degree") != expected_pair[0]
        or audit.get("coarse_degree") != expected_pair[1]
        or audit.get("edge_dtype") != "complex128"
        or audit.get("node_dtype") != "complex128"
    ):
        errors.append(f"Route-B local transfer fixed identity mismatch: {name}")
    for key, expected in (
        ("line_integral_histopolation", True),
        ("simple_injection", False),
        ("structural_projection", True),
        ("structural_forbidden_nnz_after", 0),
        ("oracle_workspace_retained", False),
    ):
        if audit.get(key) is not expected:
            errors.append(f"Route-B local transfer structural fact mismatch: {name}.{key}")
    observed.update({
        "node_exact_nnz": audit.get("node_nnz"),
        "node_numeric_bytes": audit.get("node_numeric_bytes"),
    })
    for key, value in observed.items():
        if local_map.get(key) != value:
            errors.append(f"Route-B local transfer stored field mismatch: {name}.{key}")
    if list(audit.get("edge_shape", ())) != list(expected_shape) or list(audit.get("node_shape", ())) != list(node_shape):
        errors.append(f"Route-B local transfer audit shape mismatch: {name}")
    for key, expected in (
        ("edge_nnz", observed["edge_exact_nnz"]),
        ("edge_numeric_bytes", observed["edge_numeric_bytes"]),
        ("node_nnz", observed["node_exact_nnz"]),
        ("node_numeric_bytes", observed["node_numeric_bytes"]),
    ):
        if audit.get(key) != expected:
            errors.append(f"Route-B local transfer audit field mismatch: {name}.{key}")
    limits = {
        "edge_line_integral_relative": 1.0e-11,
        "curl_flux_relative": 1.0e-11,
        "gradient_commuting_relative": 1.0e-11,
        "node_transfer_relative": 1.0e-11,
        "adjoint_work_relative": float(profile["adjoint"]),
        "linearity_relative": 1.0e-12,
        "repeat_relative": 1.0e-13,
    }
    for key, limit in limits.items():
        value = audit.get(key)
        if not _finite(value):
            errors.append(f"Route-B local transfer field is nonfinite: {name}.{key}")
        elif float(value) > limit:
            gates.append(f"Route-B local transfer {name}.{key} exceeds limit")
    if audit.get("input_unchanged") is not True or audit.get("finite") is not True:
        gates.append(f"Route-B local transfer {name} finite/input Gate failed")
    if audit.get("global_transfer_matrix") is not False:
        errors.append(f"Route-B local transfer {name} reports global transfer")
    if name == "6_2":
        if audit.get("gll_subset_exact") is not True:
            errors.append("Route-B P62 GLL subset identity is not exact")
        if audit.get("coarse_gll_subset_indices") != [0, 3, 6]:
            errors.append("Route-B P62 GLL subset indices mismatch")
        if (
            not isinstance(audit.get("coarse_gll_subset_coordinate_identity"), list)
            or audit.get("coarse_gll_subset_coordinate_identity")
            != audit.get("fine_gll_subset_coordinate_identity")
        ):
            errors.append("Route-B P62 GLL subset coordinates are not identical")
        if audit.get("nested_tiled_geometric") is not True or audit.get("generic_high_polynomial_reconstruction") is not False:
            errors.append("Route-B P62 geometric construction identity mismatch")
        if audit.get("shared_consistency") is not True:
            gates.append("Route-B P62 shared consistency failed")
        composition = audit.get("p62_p21_composition_relative")
        if not _finite(composition):
            errors.append("Route-B P62/P21 composition is missing/nonfinite")
        elif float(composition) > 1.0e-11:
            gates.append("Route-B P62/P21 composition failed")
    return {
        "name": name, "shape": [int(value) for value in matrix.shape],
        "nnz": int(np.count_nonzero(matrix)), "finite": bool(np.all(np.isfinite(matrix))),
    }


def _check_owner_probe(
    item: Any, arrays: dict[str, np.ndarray], errors: list[str], gates: list[str],
    expected_coarse_rows: int, expected_fine_rows: int,
) -> dict[str, Any]:
    if not isinstance(item, dict) or not isinstance(item.get("raw_roles"), dict):
        errors.append("Route-B owner probe facts/roles missing")
        return {}
    if item.get("schema") != ROUTE_B_PROBE_SCHEMA:
        errors.append("Route-B owner probe schema mismatch")
    if item.get("name") != "owner_packet_deterministic":
        errors.append("Route-B owner probe name mismatch")
    if item.get("pair") != [2, 1]:
        errors.append("Route-B owner probe pair mismatch")
    if item.get("source_generation") != "deterministic_owner_packet_p21":
        errors.append("Route-B owner probe source identity mismatch")
    roles = item["raw_roles"]
    required = tuple(
        (key, roles.get(key)) for key in (
            "source_before", "source_after", "source2", "projected",
            "projected_repeat", "projected2", "projected_combo", "fine_dual", "adjoint",
        )
    )
    if any(not isinstance(key, str) or key not in arrays for _name, key in required):
        errors.append("Route-B owner probe raw roles missing")
        return {}
    source, source_after, source2, projected, repeated, projected2, combo, fine_dual, adjoint = (
        arrays[key] for _name, key in required
    )
    coarse = (source, source_after, source2, adjoint)
    fine = (projected, repeated, projected2, combo, fine_dual)
    if any(value.dtype != np.dtype("complex128") or value.ndim != 1 or value.size == 0 for value in coarse + fine) or any(value.shape != (expected_coarse_rows,) for value in coarse) or any(value.shape != (expected_fine_rows,) for value in fine):
        errors.append("Route-B owner probe shape closure failed")
        return {}
    repeat = float(np.linalg.norm(repeated - projected) / max(np.linalg.norm(projected), np.finfo(float).tiny))
    linearity = float(np.linalg.norm(combo - ALPHA * projected - BETA * projected2) / max(np.linalg.norm(combo), np.finfo(float).tiny))
    lhs, rhs = _compensated_vdot(projected, fine_dual), _compensated_vdot(source, adjoint)
    adjoint_relative = float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny))
    finite = bool(all(np.all(np.isfinite(value)) for value in coarse + fine))
    unchanged = _digest(source) == _digest(source_after) == item.get("source_before_digest") == item.get("source_after_digest")
    source_norm = float(np.linalg.norm(source))
    source_finite = bool(np.all(np.isfinite(source)))
    source_nonzero = bool(source_norm > 0.0)
    for value, limit, label in ((repeat, 1.0e-13, "repeat"), (linearity, 1.0e-12, "linearity"), (adjoint_relative, 1.0e-11, "adjoint")):
        if not np.isfinite(value) or value > limit:
            gates.append(f"Route-B owner probe {label} failed")
    if not finite or not unchanged or item.get("finite") is not True or item.get("input_unchanged") is not True or item.get("phase_once") is not True:
        gates.append("Route-B owner probe finite/input/phase failed")
    if not source_finite or not source_nonzero:
        gates.append("Route-B owner probe source finite/nonzero Gate failed")
    for actual, key in ((repeat, "repeat_relative"), (linearity, "linearity_relative"), (adjoint_relative, "adjoint_work_relative")):
        if not _close(actual, item.get(key)):
            errors.append(f"Route-B owner probe stored field mismatch: {key}")
    if (
        item.get("source_finite") is not source_finite
        or item.get("source_nonzero") is not source_nonzero
        or not _close(source_norm, item.get("source_norm"))
    ):
        errors.append("Route-B owner probe stored source facts mismatch")
    return {
        "name": item.get("name"), "repeat_relative": repeat,
        "linearity_relative": linearity, "adjoint_work_relative": adjoint_relative,
        "finite": finite, "input_unchanged": unchanged,
    }


def _check_material_inventory(inventory: Any, classes: Any, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(inventory, dict) or inventory.get("schema") != "task038.full3d.route-a.material-inventory.v1":
        errors.append("material inventory schema mismatch")
        return []
    items = inventory.get("classes")
    if type(inventory.get("class_count")) is not int or not isinstance(items, list) or inventory["class_count"] != len(items):
        errors.append("material inventory class count is not closed")
        return []
    if inventory.get("exact_float64_identity") is not True or inventory.get("numeric_allgather") is not False:
        errors.append("material inventory exact/no-allgather facts are not closed")
    digests = [item.get("class_digest") if isinstance(item, dict) else None for item in items]
    if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in digests) or len(set(digests)) != len(digests) or digests != sorted(digests):
        errors.append("material inventory digest order/format is not closed")
    local_total = 0
    global_total = 0
    observed_roles: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("class_identity"), dict):
            errors.append("material inventory class identity is missing")
            continue
        identity = item["class_identity"]
        digest = item.get("class_digest")
        role = item.get("material_role")
        tag = item.get("tag")
        if role not in MATERIAL_ROLE_TAGS or type(tag) is not int:
            errors.append(f"material inventory role/tag is invalid: {digest}")
        else:
            observed_roles.add(role)
            if tag != MATERIAL_ROLE_TAGS[role]:
                errors.append(f"material inventory role/tag mapping mismatch: {digest}")
        if _semantic_sha(identity) != digest:
            errors.append(f"material inventory digest is not identity-bound: {digest}")
        material = identity.get("material_coefficient_identity", {})
        geometry = identity.get("geometry_jacobian_identity", {})
        if (
            material.get("material_role") != role
            or material.get("class_name") != f"{role}_tag_{tag}"
        ):
            errors.append(f"material inventory role/class identity mismatch: {digest}")
        try:
            curl_coefficient = float(material["curl_coefficient"])
            mass_coefficient = float(material["mass_coefficient"])
            coefficient_identity_ok = (
                math.isfinite(curl_coefficient) and curl_coefficient > 0.0
                and math.isfinite(mass_coefficient) and mass_coefficient > 0.0
                and material.get("curl_coefficient_float64_hex") == curl_coefficient.hex()
                and material.get("mass_coefficient_float64_hex") == mass_coefficient.hex()
            )
            widths = geometry["widths"]
            width_values = [float(value) for value in widths]
            geometry_identity_ok = (
                isinstance(widths, list) and len(width_values) == 3
                and all(math.isfinite(value) and value > 0.0 for value in width_values)
                and geometry.get("widths_float64_hex") == [value.hex() for value in width_values]
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            coefficient_identity_ok = False
            geometry_identity_ok = False
        if not coefficient_identity_ok:
            errors.append(f"material coefficient float64 identity mismatch: {digest}")
        if not geometry_identity_ok:
            errors.append(f"geometry float64 identity mismatch: {digest}")
        if type(item.get("cell_count_local")) is not int or item["cell_count_local"] <= 0 or type(item.get("cell_count_global")) is not int or item["cell_count_global"] <= 0:
            errors.append(f"material class cell count invalid: {digest}")
        else:
            local_total += item["cell_count_local"]
            global_total += item["cell_count_global"]
    if type(inventory.get("cell_count_local")) is not int or local_total != inventory.get("cell_count_local"):
        errors.append("material inventory local cell count is not closed")
    if type(inventory.get("cell_count_global")) is not int or global_total != inventory.get("cell_count_global"):
        errors.append("material inventory global cell count is not closed")
    if not {"air", "grating", "substrate"}.issubset(observed_roles):
        errors.append("material inventory does not cover air/grating/substrate roles")
    by_digest = {item.get("class_digest"): item for item in items if isinstance(item, dict)}
    if not isinstance(classes, list) or [item.get("class_digest") for item in classes if isinstance(item, dict)] != digests:
        errors.append("material audit class order/coverage is not exact")
    for item in classes if isinstance(classes, list) else ():
        if not isinstance(item, dict) or item.get("class_digest") not in by_digest:
            errors.append("material audit class is not in inventory")
            continue
        inventory_item = by_digest[item["class_digest"]]
        if (
            item.get("class_identity") != inventory_item.get("class_identity")
            or item.get("material_role") != inventory_item.get("material_role")
            or item.get("tag") != inventory_item.get("tag")
            or item.get("class_digest_matches_inventory") is not True
        ):
            errors.append(f"material audit identity mismatch: {item['class_digest']}")
    return items


def _a0_roles(name: str) -> dict[str, str]:
    if name not in PROBE_NAMES:
        raise ValueError(f"unknown A0 probe name: {name}")
    return {role: f"a0__{name}__{role}" for role in A0_PROBE_ROLES}


def _a0_pairwise_sum(values: np.ndarray) -> complex:
    current = np.asarray(values, dtype=np.complex128).reshape(-1).copy()
    while current.size > 1:
        pairs = current.size // 2
        next_values = current[: 2 * pairs : 2] + current[1 : 2 * pairs : 2]
        current = (
            next_values
            if current.size % 2 == 0
            else np.concatenate((next_values, current[-1:]))
        )
    return complex(current[0]) if current.size else 0.0 + 0.0j


def _a0_compensated_sum(values: np.ndarray) -> complex:
    values = np.asarray(values, dtype=np.complex128).reshape(-1)
    return complex(
        math.fsum(float(value.real) for value in values),
        math.fsum(float(value.imag) for value in values),
    )


def _a0_relative(left: complex, right: complex) -> float:
    return float(abs(left - right) / max(abs(left), abs(right), np.finfo(float).tiny))


def _a0_packet(
    ids: Any, values: Any, label: str, errors: list[str],
) -> tuple[np.ndarray, np.ndarray] | None:
    ids = np.asarray(ids)
    values = np.asarray(values)
    if ids.dtype != np.dtype("uint32") or values.dtype != np.dtype("complex128"):
        errors.append(f"A0 {label} packet dtype mismatch")
        return None
    if ids.ndim != 1 or values.ndim != 1 or ids.size == 0 or ids.shape != values.shape:
        errors.append(f"A0 {label} packet shape mismatch")
        return None
    if np.any(ids[1:] <= ids[:-1]):
        errors.append(f"A0 {label} packet keys are not strictly ascending")
        return None
    if not np.all(np.isfinite(values)):
        errors.append(f"A0 {label} packet is nonfinite")
        return None
    return ids.copy(), values.copy()


def _a0_merge_packets(
    packets: list[tuple[int, np.ndarray, np.ndarray]], label: str,
    errors: list[str], gates: list[str], *, mode: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
    entries = sorted(
        (int(key), int(rank), complex(value))
        for rank, ids, values in packets
        for key, value in zip(ids, values, strict=True)
    )
    if not entries:
        errors.append(f"A0 {label} packet set is empty")
        return None
    merged_ids: list[int] = []
    merged_values: list[complex] = []
    duplicate_count = 0
    max_abs_defect = 0.0
    max_relative_defect = 0.0
    index = 0
    while index < len(entries):
        key = entries[index][0]
        group: list[complex] = []
        while index < len(entries) and entries[index][0] == key:
            group.append(entries[index][2])
            index += 1
        merged_ids.append(key)
        if mode == "owner" and len(group) != 1:
            errors.append(f"A0 {label} owner key is duplicated: {key}")
        value = group[0]
        if len(group) > 1:
            duplicate_count += len(group) - 1
            for candidate in group[1:]:
                absolute = abs(candidate - value)
                relative = absolute / max(abs(candidate), abs(value), np.finfo(float).tiny)
                max_abs_defect = max(max_abs_defect, float(absolute))
                max_relative_defect = max(max_relative_defect, float(relative))
            if mode == "consistent" and max_relative_defect > 1.0e-11:
                gates.append(f"A0 {label} duplicate canonical values disagree")
            if mode == "sum":
                value = sum(group, 0.0 + 0.0j)
        merged_values.append(value)
    return (
        np.asarray(merged_ids, dtype=np.uint32),
        np.asarray(merged_values, dtype=np.complex128),
        {
            "unique_count": len(merged_ids),
            "duplicate_count": duplicate_count,
            "max_abs_defect": max_abs_defect,
            "max_relative_defect": max_relative_defect,
        },
    )


def _a0_global_norm2(values: list[np.ndarray]) -> float:
    return float(math.fsum(float(np.vdot(value, value).real) for value in values))


def _a0_check_markers(
    record: dict[str, Any], raw_dir: Path, record_path: Path,
    expected_sha: str, errors: list[str],
) -> None:
    info = record.get("markers")
    if not isinstance(info, dict) or tuple(info.get("names", ())) != A0_MARKERS:
        errors.append("A0 marker list mismatch")
        return
    wall_times = info.get("wall_time_ns")
    if not isinstance(wall_times, dict) or set(wall_times) != set(A0_MARKERS):
        errors.append("A0 marker wall-time map is not exact")
    marker_dir = raw_dir / str(info.get("relative_dir", ""))
    times: list[int] = []
    for name in A0_MARKERS:
        path = marker_dir / f"{name}.json"
        if not _inside(path, raw_dir) or not path.is_file():
            errors.append(f"A0 marker missing/escaped: {name}")
            continue
        try:
            item = _read_json(path)
            timestamp = item["wall_time_ns"]
            if (
                item.get("schema") != A0_MARKER_SCHEMA
                or item.get("marker") != name
                or item.get("source_sha") != expected_sha
                or type(timestamp) is not int
                or not isinstance(wall_times, dict)
                or wall_times.get(name) != timestamp
            ):
                errors.append(f"A0 marker identity mismatch: {name}")
            else:
                times.append(timestamp)
        except (OSError, ValueError, KeyError, TypeError):
            errors.append(f"A0 marker unreadable: {name}")
    closeout = marker_dir / "record_closeout.json"
    if not closeout.is_file():
        errors.append("A0 record_closeout marker is missing")
    else:
        try:
            item = _read_json(closeout)
            facts = item.get("facts")
            closeout_time = item.get("wall_time_ns")
            release_time = wall_times.get("release") if isinstance(wall_times, dict) else None
            if (
                item.get("schema") != A0_MARKER_SCHEMA
                or item.get("marker") != "record_closeout"
                or item.get("source_sha") != expected_sha
                or type(closeout_time) is not int
                or type(release_time) is not int
                or closeout_time <= release_time
                or not isinstance(facts, dict)
                or facts.get("record_path") != str(record_path.resolve())
                or facts.get("record_sha256") != _sha256(record_path)
            ):
                errors.append("A0 record_closeout is not bound to the written record")
        except (OSError, ValueError, KeyError, TypeError):
            errors.append("A0 record_closeout is unreadable")
    allowed = {f"{name}.json" for name in A0_MARKERS} | {"record_closeout.json"}
    if marker_dir.is_dir() and {path.name for path in marker_dir.iterdir()} != allowed:
        errors.append("A0 marker directory contains an unauthorized file")
    if len(times) == len(A0_MARKERS) and times != sorted(times):
        errors.append("A0 marker sequence is not monotonic")


def _a0_check_provenance(
    record: dict[str, Any], record_path: Path, expected_sha: str,
    errors: list[str], raw_dir: Path,
) -> bool:
    failed = False
    case = record.get("case")
    expected_mpi = int(case.rsplit("mpi", 1)[-1]) if case in A0_CASES else None
    if (
        record.get("schema") != A0_SCHEMA
        or record.get("stage") != "a0"
        or expected_mpi is None
        or record.get("mpi_size") != expected_mpi
        or record.get("degree") != 6
        or record.get("h_nm") != 10.0
        or record.get("wavelength_nm") != 13.5
        or record.get("branch") != BRANCH
    ):
        errors.append("A0 fixed stage/case identity mismatch")
        failed = True
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("A0 source identity is missing")
        failed = True
    else:
        for name in ("start", "end"):
            item = source.get(name)
            if (
                not isinstance(item, dict)
                or item.get("commit_sha") != expected_sha
                or item.get("branch") != BRANCH
                or item.get("clean") is not True
            ):
                errors.append(f"A0 source {name} identity is not closed")
                failed = True
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("A0 runtime identity is missing")
        failed = True
    else:
        if (
            runtime.get("qualified_activation") != "1"
            or runtime.get("mpi_size") != expected_mpi
            or runtime.get("scalar_dtype") != "complex128"
            or runtime.get("int_dtype") != "int32"
            or not Path(str(runtime.get("sys_executable", ""))).is_absolute()
        ):
            errors.append("A0 runtime ABI identity mismatch")
            failed = True
        threads = runtime.get("threads")
        if not isinstance(threads, dict) or any(
            threads.get(name) != "1"
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        ):
            errors.append("A0 thread identity mismatch")
            failed = True
    command = record.get("command")
    record_string = record.get("record_path")
    if (
        not isinstance(command, list)
        or len(command) != 19
        or not all(isinstance(value, str) for value in command)
        or not isinstance(record_string, str)
        or not isinstance(record.get("raw_dir"), str)
        or not Path(str(record.get("raw_dir"))).is_absolute()
        or record_string != str(record_path.resolve())
        or str(record.get("raw_dir")) == str(record_path.resolve())
        or not _inside(raw_dir, raw_dir.parent)
    ):
        errors.append("A0 command or artifact path identity is missing")
        failed = True
    else:
        expected_input = str((Path(__file__).resolve().parents[1] / "input/templates/full3d_iterative_example.dat").resolve())
        expected_command = [
            str(runtime.get("sys_executable")), "-m", MODULE,
            "--stage", "a0", "--case", case,
            "--raw-dir", str(raw_dir), "--record", str(record_path.resolve()),
            "--expected-source-sha", expected_sha,
            "--expected-mpi-size", str(expected_mpi), "--input", expected_input,
            "--r3-long-tail-manifest",
        ]
        provenance = record.get("provenance")
        manifest_path = provenance.get("r3_long_tail_manifest_path") if isinstance(provenance, dict) else None
        expected_command.append(str(manifest_path))
        if command != expected_command or not Path(command[0]).is_absolute() or command[18] != str(manifest_path):
            errors.append("A0 canonical worker command mismatch")
            failed = True
    input_identity = record.get("input_identity")
    if (
        not isinstance(input_identity, dict)
        or input_identity.get("path_relative") != "input/templates/full3d_iterative_example.dat"
        or input_identity.get("raw_bytes") != EXPECTED_INPUT_BYTES
        or input_identity.get("raw_sha256") != EXPECTED_INPUT_SHA256
        or input_identity.get("resolved_bytes") != EXPECTED_RESOLVED_BYTES
        or input_identity.get("resolved_sha256") != EXPECTED_RESOLVED_SHA256
        or input_identity.get("physical_model_sha256") != EXPECTED_PHYSICAL_MODEL_SHA256
    ):
        errors.append("A0 fixed input identity mismatch")
        failed = True
    provenance = record.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("r3_long_tail_expected_sha256") != R3_LONG_TAIL_MANIFEST_SHA256
        or provenance.get("r3_long_tail_source_sha") != R3_LONG_TAIL_SOURCE_SHA
        or provenance.get("p63_constructed_once") is not True
        or provenance.get("p63_construction_count") != 1
        or provenance.get("p63_construction_source") != "build_local_interlevel_edge_transfer(6,3)"
        or provenance.get("mpi_shard_count") != expected_mpi
    ):
        errors.append("A0 construction/provenance identity mismatch")
        failed = True
    else:
        manifest_path = Path(str(provenance["r3_long_tail_manifest_path"]))
        if (
            not manifest_path.is_absolute()
            or not manifest_path.is_file()
            or _sha256(manifest_path) != R3_LONG_TAIL_MANIFEST_SHA256
            or provenance.get("r3_long_tail_manifest_sha256") != R3_LONG_TAIL_MANIFEST_SHA256
            or not isinstance(command, list)
            or command[18] != str(manifest_path.resolve())
        ):
            errors.append("A0 R3 manifest identity is not hash-bound")
            failed = True
    settings = record.get("settings")
    expected_settings = {
        "probe_names": list(PROBE_NAMES),
        "levels": [6, 3], "transfer_pair": [6, 3],
        "canonical_key": "physical/canonical packed owner edge key",
        "canonical_order": "sort by canonical key after rank-shard merge",
        "canonical_packet_source": "topology canonical IDs; never PETSc row/local/rank order",
        "ordinary_terms": "conjugate(original raw left) * original raw right",
        "canonical_terms": "conjugate(key-aligned canonical values) * key-aligned canonical values",
        "forward_bound_scope": "ordinary raw terms only",
        "pairwise_limit": 1.0e-13, "compensated_limit": 1.0e-12,
        "vector_limit": 1.0e-11, "ordinary_bound_factor": 4.0,
        "phase_once": "once_in_canonical_owner_route", "mpi_sizes_supported": [1, 2],
    }
    if settings != expected_settings:
        errors.append("A0 settings/canonical authority mismatch")
    return failed


def _a0_check_architecture(
    record: dict[str, Any], errors: list[str],
) -> None:
    architecture = record.get("architecture")
    if not isinstance(architecture, dict):
        errors.append("A0 architecture is missing")
        return
    case_names = (
        "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
        "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
        "pcgamg_hierarchy_built", "physical_solve", "recovery",
    )
    extension_names = (
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_built", "p1_global_direct_factor", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    )
    derived_names = (
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_global_direct_factor", "p1_built", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    )
    expected_forbidden = {
        *(f"case.{name}" for name in case_names),
        *(f"extension.{name}" for name in extension_names),
        *derived_names,
    }
    forbidden = architecture.get("forbidden")
    if not isinstance(forbidden, dict) or set(forbidden) != expected_forbidden:
        errors.append("A0 forbidden architecture key set is not exact")
    elif any(value is not False for value in forbidden.values()):
        errors.append("A0 forbidden architecture fact is not false")
    for group, names in {
        "case": case_names, "extension": extension_names,
    }.items():
        nested = architecture.get(group)
        if not isinstance(nested, dict):
            errors.append(f"A0 nested architecture audit missing: {group}")
        else:
            for name in names:
                if nested.get(name) is not False:
                    errors.append(f"A0 nested forbidden fact is not false: {group}.{name}")
    _check_level_topology(architecture, errors, (6, 3))


def _a0_load_shards(
    record: dict[str, Any], raw_dir: Path, errors: list[str],
) -> tuple[list[tuple[int, dict[str, np.ndarray]]], dict[str, Any] | None]:
    descriptor = record.get("raw_arrays")
    if not isinstance(descriptor, dict) or descriptor.get("schema") != A0_RAW_SCHEMA:
        errors.append("A0 raw manifest descriptor is missing or has the wrong schema")
        return [], None
    relative = descriptor.get("relative_path")
    manifest_path = raw_dir / str(relative) if isinstance(relative, str) else raw_dir / "__missing__"
    if not isinstance(relative, str) or not _inside(manifest_path, raw_dir) or not manifest_path.is_file():
        errors.append("A0 raw manifest is missing or escaped")
        return [], None
    if _sha256(manifest_path) != descriptor.get("sha256"):
        errors.append("A0 raw manifest SHA mismatch")
        return [], None
    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"A0 raw manifest unreadable: {exc}")
        return [], None
    case_mpi = record.get("mpi_size")
    if type(case_mpi) is not int or case_mpi not in (1, 2):
        errors.append("A0 MPI shard size is missing/noncanonical")
        return [], None
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != A0_RAW_SCHEMA
        or manifest.get("mpi_size") != case_mpi
        or manifest.get("canonical_key_authority") != "physical/canonical packed edge key; no PETSc row, rank, or local order"
        or descriptor.get("mpi_size") != case_mpi
        or descriptor.get("shards") != manifest.get("shards")
    ):
        errors.append("A0 raw manifest authority mismatch")
        return [], None
    shard_list = manifest.get("shards")
    if not isinstance(shard_list, list) or [item.get("rank") for item in shard_list if isinstance(item, dict)] != list(range(int(case_mpi))):
        errors.append("A0 shard rank inventory is not exact")
        return [], None
    result: list[tuple[int, dict[str, np.ndarray]]] = []
    for shard in shard_list:
        if not isinstance(shard, dict) or type(shard.get("rank")) is not int:
            errors.append("A0 shard descriptor is malformed")
            continue
        rank = int(shard["rank"])
        relative_shard = shard.get("relative_path")
        path = raw_dir / str(relative_shard) if isinstance(relative_shard, str) else raw_dir / "__missing__"
        if not isinstance(relative_shard, str) or not _inside(path, raw_dir) or not path.is_file():
            errors.append(f"A0 shard path missing/escaped: rank {rank}")
            continue
        if _sha256(path) != shard.get("sha256"):
            errors.append(f"A0 shard SHA mismatch: rank {rank}")
            continue
        arrays_descriptor = shard.get("arrays")
        if not isinstance(arrays_descriptor, dict):
            errors.append(f"A0 shard array descriptor missing: rank {rank}")
            continue
        arrays: dict[str, np.ndarray] = {}
        try:
            with np.load(path, allow_pickle=False) as loaded:
                if set(loaded.files) != set(arrays_descriptor):
                    errors.append(f"A0 shard NPZ key set mismatch: rank {rank}")
                else:
                    for name, item in arrays_descriptor.items():
                        value = _load_array(name, loaded, item, errors)
                        if value is not None:
                            arrays[name] = value
        except (OSError, ValueError, EOFError, TypeError) as exc:
            errors.append(f"A0 shard NPZ unreadable: rank {rank}: {exc}")
        result.append((rank, arrays))
    return result, manifest


def _a0_expected_shard_keys(
    class_digests: list[str], probe_names: tuple[str, ...],
) -> set[str]:
    keys = {"p63"}
    for name in probe_names:
        keys.update(_a0_roles(name).values())
    for digest in class_digests:
        prefix = f"class_{digest}"
        keys.update(
            f"{prefix}__{role}"
            for role in ("b3", "b6p", "eigenvector_min", "eigenvector_max")
        )
    return keys


def _a0_check_inventory_shards(
    record: dict[str, Any], shards: list[tuple[int, dict[str, np.ndarray]]],
    errors: list[str],
) -> tuple[dict[str, np.ndarray], dict[str, list[tuple[int, dict[str, np.ndarray]]]]]:
    inventory = record.get("material_inventory")
    if not isinstance(inventory, dict) or not isinstance(inventory.get("classes"), list):
        errors.append("A0 material inventory is missing")
        return {}, {}
    digests = [item.get("class_digest") for item in inventory["classes"] if isinstance(item, dict)]
    by_rank = inventory.get("class_inventory_by_rank")
    def valid_rank_items(items: Any) -> bool:
        return (
            isinstance(items, list)
            and all(isinstance(item, str) for item in items)
            and items == sorted(items)
            and len(items) == len(set(items))
            and all(item in digests for item in items)
        )
    if (
        not isinstance(by_rank, list)
        or len(by_rank) != record.get("mpi_size")
        or not all(valid_rank_items(items) for items in by_rank)
        or sorted(set(value for items in by_rank for value in items)) != sorted(digests)
    ):
        errors.append("A0 per-rank material inventory coverage is not exact")
    merged: dict[str, np.ndarray] = {}
    by_probe: dict[str, list[tuple[int, dict[str, np.ndarray]]] ] = {
        name: [] for name in PROBE_NAMES
    }
    for rank, arrays in sorted(shards):
        local_classes = by_rank[rank] if isinstance(by_rank, list) and rank < len(by_rank) else []
        expected = _a0_expected_shard_keys(local_classes, PROBE_NAMES)
        if set(arrays) != expected:
            errors.append(f"A0 rank {rank} raw role set is not exact")
        for name in PROBE_NAMES:
            by_probe[name].append((rank, arrays))
        if "p63" in arrays:
            previous = merged.get("p63")
            if previous is None:
                merged["p63"] = arrays["p63"]
            elif previous.shape != arrays["p63"].shape or not np.array_equal(previous, arrays["p63"]):
                errors.append("A0 P63 differs between rank shards")
        for digest in local_classes:
            prefix = f"class_{digest}"
            for role in ("b3", "b6p", "eigenvector_min", "eigenvector_max"):
                key = f"{prefix}__{role}"
                if key not in arrays:
                    continue
                previous = merged.get(key)
                if previous is None:
                    merged[key] = arrays[key]
                elif previous.shape != arrays[key].shape or not np.array_equal(previous, arrays[key]):
                    errors.append(f"A0 class raw array differs between shards: {key}")
    return merged, by_probe


def _a0_check_probe(
    name: str, facts: Any, shard_arrays: list[tuple[int, dict[str, np.ndarray]]],
    errors: list[str], gates: list[str], mpi_size: int,
) -> dict[str, Any]:
    roles = _a0_roles(name)
    if not isinstance(facts, dict) or facts.get("name") != name or facts.get("raw_roles") != roles:
        errors.append(f"A0 probe identity/role map mismatch: {name}")
    expected_generation = SOURCE_GENERATION[name]
    if isinstance(facts, dict) and facts.get("source_generation") != expected_generation:
        errors.append(f"A0 source-generation identity mismatch: {name}")
    required = tuple(roles.values())
    local: list[tuple[int, dict[str, np.ndarray]]] = []
    for rank, arrays in shard_arrays:
        if any(key not in arrays for key in required):
            errors.append(f"A0 probe raw roles missing: {name}, rank {rank}")
            continue
        values = {role: arrays[key] for role, key in roles.items()}
        if any(
            value.dtype != np.dtype("complex128") or value.ndim != 1 or value.size == 0
            for role, value in values.items() if not role.endswith("_ids")
        ):
            errors.append(f"A0 probe raw vector dtype/shape mismatch: {name}, rank {rank}")
            continue
        local.append((rank, values))
        for id_role, value_role in (
            ("fine_primal_local_ids", "fine_primal_local"),
            ("fine_dual_local_ids", "fine_dual_local"),
            ("coarse_source_local_ids", "coarse_source_local"),
            ("explicit_adjoint_local_ids", "explicit_adjoint_local"),
            ("implemented_adjoint_local_ids", "implemented_adjoint_local"),
            ("implemented_adjoint_owner_ids", "implemented_adjoint_owner"),
        ):
            if _a0_packet(values[id_role], values[value_role], f"{name}.{id_role}", errors) is None:
                continue
        if not np.array_equal(values["source_before"], values["source_after"]):
            gates.append(f"A0 probe {name} input changed on rank {rank}")
    if not local or len(local) != len(shard_arrays):
        return {"name": name, "finite": False}

    def packets(id_role: str, value_role: str) -> list[tuple[int, np.ndarray, np.ndarray]]:
        result = []
        for rank, values in local:
            packet = _a0_packet(values[id_role], values[value_role], f"{name}.{value_role}", errors)
            if packet is not None:
                result.append((rank, packet[0], packet[1]))
        return result

    fine_primal = _a0_merge_packets(packets("fine_primal_local_ids", "fine_primal_local"), f"{name}.fine_primal", errors, gates, mode="consistent")
    fine_dual = _a0_merge_packets(packets("fine_dual_local_ids", "fine_dual_local"), f"{name}.fine_dual", errors, gates, mode="consistent")
    coarse_source = _a0_merge_packets(packets("coarse_source_local_ids", "coarse_source_local"), f"{name}.coarse_source", errors, gates, mode="consistent")
    explicit = _a0_merge_packets(packets("explicit_adjoint_local_ids", "explicit_adjoint_local"), f"{name}.explicit_adjoint", errors, gates, mode="sum")
    implemented = _a0_merge_packets(packets("implemented_adjoint_owner_ids", "implemented_adjoint_owner"), f"{name}.implemented_owner", errors, gates, mode="owner")
    if any(value is None for value in (fine_primal, fine_dual, coarse_source, explicit, implemented)):
        return {"name": name, "finite": False}
    fine_ids, fine_values, fine_merge = fine_primal
    dual_ids, dual_values, _dual_merge = fine_dual
    coarse_ids, coarse_values, _coarse_merge = coarse_source
    explicit_ids, explicit_values, explicit_merge = explicit
    implemented_ids, implemented_values, owner_merge = implemented
    if not (
        np.array_equal(fine_ids, dual_ids)
        and np.array_equal(coarse_ids, explicit_ids)
        and np.array_equal(coarse_ids, implemented_ids)
    ):
        errors.append(f"A0 {name} canonical key sets are not closed")
        return {"name": name, "finite": False}
    lhs_terms = np.conjugate(fine_values) * dual_values
    rhs_terms = np.conjugate(coarse_values) * implemented_values
    explicit_terms = np.conjugate(coarse_values) * explicit_values
    pairwise_lhs = _a0_pairwise_sum(lhs_terms)
    pairwise_rhs = _a0_pairwise_sum(rhs_terms)
    pairwise_explicit = _a0_pairwise_sum(explicit_terms)
    compensated_lhs = _a0_compensated_sum(lhs_terms)
    compensated_rhs = _a0_compensated_sum(rhs_terms)
    compensated_explicit = _a0_compensated_sum(explicit_terms)
    vector_difference = implemented_values - explicit_values
    vector_difference_sq = float(math.fsum(float(abs(value) ** 2) for value in vector_difference))
    vector_reference_sq = float(math.fsum(float(abs(value) ** 2) for value in explicit_values))
    vector_relative = math.sqrt(max(vector_difference_sq, 0.0)) / max(math.sqrt(max(vector_reference_sq, 0.0)), np.finfo(float).tiny)
    ordinary_lhs = sum(
        (complex(np.vdot(values["projected"], values["fine_dual"])) for _rank, values in local),
        0.0 + 0.0j,
    )
    ordinary_rhs = sum(
        (complex(np.vdot(values["source_before"], values["adjoint"])) for _rank, values in local),
        0.0 + 0.0j,
    )
    ordinary_lhs_terms = np.concatenate(
        [np.conjugate(values["projected"]) * values["fine_dual"] for _rank, values in local]
    )
    ordinary_rhs_terms = np.concatenate(
        [np.conjugate(values["source_before"]) * values["adjoint"] for _rank, values in local]
    )
    def bound(terms: np.ndarray) -> tuple[float, float, int]:
        count = int(terms.size)
        denominator = 1.0 - count * np.finfo(float).eps
        gamma = count * np.finfo(float).eps / denominator if denominator > 0.0 else math.inf
        return gamma * math.fsum(float(abs(value)) for value in terms), gamma, count
    lhs_bound, lhs_gamma, lhs_count = bound(ordinary_lhs_terms)
    rhs_bound, rhs_gamma, rhs_count = bound(ordinary_rhs_terms)
    ordinary_defect = abs(ordinary_lhs - ordinary_rhs)
    forward_bound = lhs_bound + rhs_bound
    pairwise_vs_compensated = max(
        _a0_relative(pairwise_lhs, compensated_lhs),
        _a0_relative(pairwise_rhs, compensated_rhs),
        _a0_relative(pairwise_explicit, compensated_explicit),
    )
    compensated_work = _a0_relative(compensated_lhs, compensated_rhs)
    checks = (
        (pairwise_vs_compensated <= A0_LIMITS["pairwise"], "pairwise_vs_compensated"),
        (compensated_work <= A0_LIMITS["compensated"], "compensated_work"),
        (vector_relative <= A0_LIMITS["vector"], "vector_adjoint"),
        (ordinary_defect <= A0_LIMITS["ordinary_bound_factor"] * forward_bound, "ordinary_forward_bound"),
    )
    for passed, label in checks:
        if not passed:
            gates.append(f"A0 probe {name} {label} failed")
    finite = bool(all(np.all(np.isfinite(value)) for _rank, values in local for value in values.values()))
    if not finite:
        gates.append(f"A0 probe {name} finite failed")
    stable = {
        "pairwise_vs_compensated_relative": float(pairwise_vs_compensated),
        "compensated_work_relative": float(compensated_work),
        "vector_adjoint_relative": float(vector_relative),
        "ordinary_abs_work_defect": float(ordinary_defect),
        "forward_error_bound_abs": float(forward_bound),
        "ordinary_lhs": [float(ordinary_lhs.real), float(ordinary_lhs.imag)],
        "ordinary_rhs": [float(ordinary_rhs.real), float(ordinary_rhs.imag)],
        "lhs_gamma_n": float(lhs_gamma), "rhs_gamma_n": float(rhs_gamma),
        "lhs_term_count": lhs_count, "rhs_term_count": rhs_count,
        "canonical_owner_count": int(coarse_ids.size),
        "canonical_duplicate_facts": {
            "fine_primal": fine_merge,
            "explicit_adjoint": explicit_merge,
            "implemented_owner": owner_merge,
        },
    }
    raw = {
        "q": None,
        "canonical_pairwise_lhs": [float(pairwise_lhs.real), float(pairwise_lhs.imag)],
        "canonical_pairwise_rhs": [float(pairwise_rhs.real), float(pairwise_rhs.imag)],
        "canonical_compensated_lhs": [float(compensated_lhs.real), float(compensated_lhs.imag)],
        "canonical_compensated_rhs": [float(compensated_rhs.real), float(compensated_rhs.imag)],
        "vector_adjoint_relative": float(vector_relative),
        "ordinary_abs_work_defect": float(ordinary_defect),
        "forward_error_bound_abs": float(forward_bound),
        "canonical_key_count": int(coarse_ids.size),
        "finite": finite,
    }
    for _rank, values in local:
        ec = np.vdot(values["source_before"], values["b3"])
        ef = np.vdot(values["projected"], values["b6p"])
        raw.setdefault("energy_coarse", 0.0 + 0.0j)
        raw.setdefault("energy_fine", 0.0 + 0.0j)
        raw["energy_coarse"] += complex(ec)
        raw["energy_fine"] += complex(ef)
    ec = raw["energy_coarse"]
    ef = raw["energy_fine"]
    if not np.isfinite(ec.real) or not np.isfinite(ec.imag) or abs(ec) <= 0.0:
        gates.append(f"A0 probe {name} coarse energy denominator invalid")
        q = complex(math.nan, math.nan)
    else:
        q = ef / ec
    raw["q"] = float(q.real)
    raw["q_imag_defect"] = float(abs(q.imag))
    raw["energy_imag_defect"] = float(max(abs(ec.imag), abs(ef.imag)))
    raw["energy_coarse"] = [float(ec.real), float(ec.imag)]
    raw["energy_fine"] = [float(ef.real), float(ef.imag)]
    raw["ordinary_adjoint_work_relative"] = float(_a0_relative(ordinary_lhs, ordinary_rhs))
    raw["repeat_relative"] = float(
        math.sqrt(_a0_global_norm2([values["projected_repeat"] - values["projected"] for _rank, values in local]))
        / max(math.sqrt(_a0_global_norm2([values["projected"] for _rank, values in local])), np.finfo(float).tiny)
    )
    raw["linearity_relative"] = float(
        math.sqrt(_a0_global_norm2([values["projected_combo"] - ALPHA * values["projected"] - BETA * values["projected2"] for _rank, values in local]))
        / max(math.sqrt(_a0_global_norm2([values["projected_combo"] for _rank, values in local])), np.finfo(float).tiny)
    )
    for value, limit, label in (
        (raw["repeat_relative"], REPEAT_LIMIT, "repeat"),
        (raw["linearity_relative"], LINEARITY_LIMIT, "linearity"),
        (raw["q_imag_defect"], HERMITIAN_LIMIT, "q_imag"),
        (raw["energy_imag_defect"], HERMITIAN_LIMIT, "energy_imag"),
    ):
        if not np.isfinite(value) or value > limit:
            gates.append(f"A0 probe {name} {label} failed")
    if not PROBE_MIN <= raw["q"] <= PROBE_MAX:
        gates.append(f"A0 probe {name} q interval failed")
    if mpi_size == 1 and isinstance(facts, dict):
        if (
            facts.get("source_before_digest") != _digest(local[0][1]["source_before"])
            or facts.get("source_after_digest") != _digest(local[0][1]["source_after"])
            or facts.get("source_finite") is not True
            or facts.get("source_nonzero") is not bool(
                np.linalg.norm(local[0][1]["source_before"]) > 0.0
            )
        ):
            errors.append(f"A0 source digest/fact mismatch: {name}")
        for actual, key in (
            (raw["q"], "q"),
            (raw["q_imag_defect"], "q_imag_defect"),
            (raw["energy_imag_defect"], "energy_imag_defect"),
            (raw["repeat_relative"], "repeat_relative"),
            (raw["linearity_relative"], "linearity_relative"),
            (raw["ordinary_adjoint_work_relative"], "adjoint_work_relative"),
        ):
            if not _close(actual, facts.get(key)):
                errors.append(f"A0 probe stored field mismatch: {name}.{key}")
        if facts.get("input_unchanged") is not True or not _close(
            float(np.linalg.norm(local[0][1]["source_before"])), facts.get("source_norm")
        ):
            errors.append(f"A0 probe input/source fact mismatch: {name}")
        stable_facts = facts.get("stable_adjoint")
        if not isinstance(stable_facts, dict) or stable_facts.get("schema") != "task038.full3d.interlevel-stable-adjoint.a0.v1":
            errors.append(f"A0 stable facts missing: {name}")
        else:
            for actual, key in (
                (pairwise_vs_compensated, "pairwise_vs_compensated_relative"),
                (compensated_work, "compensated_work_relative"),
                (vector_relative, "vector_adjoint_relative"),
                (ordinary_defect, "ordinary_abs_work_defect"),
                (forward_bound, "forward_error_bound_abs"),
            ):
                if not _close(actual, stable_facts.get(key)):
                    errors.append(f"A0 stable stored field mismatch: {name}.{key}")
    return {
        "name": name,
        **raw,
        **stable,
        "_canonical_ids": coarse_ids,
        "_implemented_values": implemented_values,
        "_explicit_values": explicit_values,
    }


def _a0_key_relative(
    left_ids: np.ndarray, left_values: np.ndarray,
    right_ids: np.ndarray, right_values: np.ndarray,
) -> float | None:
    if not all(
        isinstance(value, np.ndarray)
        for value in (left_ids, left_values, right_ids, right_values)
    ):
        return None
    if not np.array_equal(left_ids, right_ids):
        return None
    difference = left_values - right_values
    return float(
        math.sqrt(max(_a0_global_norm2([difference]), 0.0))
        / max(math.sqrt(max(_a0_global_norm2([right_values]), 0.0)), np.finfo(float).tiny)
    )


def _a0_check_mpi1_reference(
    record: dict[str, Any], current_metrics: list[dict[str, Any]],
    reference_path: Path | None, expected_sha: str,
    errors: list[str], gates: list[str],
) -> dict[str, Any]:
    mpi_size = record.get("mpi_size")
    if mpi_size == 1:
        if reference_path is not None:
            errors.append("A0 MPI1 checker must not claim a cross-MPI reference")
        return {"status": "mpi1_only_pending_mpi2"}
    if mpi_size != 2:
        return {"status": "not_available"}
    if reference_path is None:
        errors.append("A0 MPI2 checker requires --mpi1-reference")
        return {"status": "missing_mpi1_reference"}
    reference_path = reference_path.resolve()
    if not reference_path.is_file() or reference_path == Path(str(record.get("record_path"))).resolve():
        errors.append("A0 MPI1 reference record is missing or self-referential")
        return {"status": "invalid_mpi1_reference"}
    try:
        reference = _read_json(reference_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"A0 MPI1 reference record unreadable: {exc}")
        return {"status": "invalid_mpi1_reference"}
    reference_errors: list[str] = []
    reference_gates: list[str] = []
    reference_raw_dir = Path(str(reference.get("raw_dir", ""))).resolve()
    if isinstance(reference, dict):
        reference_source = reference.get("source")
    else:
        reference_source = None
    if (
        not isinstance(reference, dict)
        or reference.get("schema") != A0_SCHEMA
        or reference.get("case") != "p6-h10-mpi1"
        or reference.get("mpi_size") != 1
        or reference.get("branch") != BRANCH
        or not isinstance(reference_source, dict)
        or not isinstance(reference_source.get("start"), dict)
        or not isinstance(reference_source.get("end"), dict)
        or reference_source["start"].get("commit_sha") != expected_sha
        or reference_source["end"].get("commit_sha") != expected_sha
    ):
        reference_errors.append("MPI1 reference fixed identity mismatch")
    if isinstance(reference, dict):
        _a0_check_provenance(
            reference, reference_path, expected_sha, reference_errors, reference_raw_dir,
        )
    reference_shards, _manifest = _a0_load_shards(reference, reference_raw_dir, reference_errors) if isinstance(reference, dict) else ([], None)
    _merged, reference_probe_shards = _a0_check_inventory_shards(
        reference, reference_shards, reference_errors,
    ) if isinstance(reference, dict) else ({}, {})
    reference_probes = reference.get("probes") if isinstance(reference, dict) else None
    if not isinstance(reference_probes, list) or [item.get("name") for item in reference_probes if isinstance(item, dict)] != list(PROBE_NAMES):
        reference_errors.append("MPI1 reference probe order is not exact")
        reference_probes = []
    reference_metrics: list[dict[str, Any]] = []
    for name, item in zip(PROBE_NAMES, reference_probes, strict=True):
        reference_metrics.append(
            _a0_check_probe(
                name, item, reference_probe_shards.get(name, []),
                reference_errors, reference_gates, 1,
            )
        )
    if reference_errors:
        errors.extend(f"A0 MPI1 reference: {value}" for value in reference_errors)
    if reference_gates:
        gates.extend(f"A0 MPI1 reference: {value}" for value in reference_gates)
    if len(reference_metrics) != len(current_metrics) or reference_errors or reference_gates:
        return {
            "status": "invalid_mpi1_reference",
            "path": str(reference_path),
            "sha256": _sha256(reference_path),
        }
    relative_fields = (
        "q", "canonical_pairwise_lhs", "canonical_pairwise_rhs",
        "canonical_compensated_lhs", "canonical_compensated_rhs",
    )
    normalized_defect_fields = (
        "vector_adjoint_relative", "compensated_work_relative",
        "pairwise_vs_compensated_relative",
    )
    comparisons: list[dict[str, Any]] = []
    for current, prior in zip(current_metrics, reference_metrics, strict=True):
        name = current.get("name")
        key_relative_implemented = _a0_key_relative(
            current.get("_canonical_ids"), current.get("_implemented_values"),
            prior.get("_canonical_ids"), prior.get("_implemented_values"),
        )
        key_relative_explicit = _a0_key_relative(
            current.get("_canonical_ids"), current.get("_explicit_values"),
            prior.get("_canonical_ids"), prior.get("_explicit_values"),
        )
        if key_relative_implemented is None or key_relative_explicit is None:
            errors.append(f"A0 cross-MPI canonical key mismatch: {name}")
            continue
        if key_relative_implemented > 1.0e-11 or key_relative_explicit > 1.0e-11:
            gates.append(f"A0 cross-MPI canonical vector identity failed: {name}")
        relative_differences: dict[str, float] = {}
        for field in relative_fields:
            left = current.get(field)
            right = prior.get(field)
            if isinstance(left, list) and isinstance(right, list):
                left_complex = _complex_pair(left)
                right_complex = _complex_pair(right)
                difference = (
                    math.inf if left_complex is None or right_complex is None else
                    _a0_relative(left_complex, right_complex)
                )
            elif _finite(left) and _finite(right):
                difference = _a0_relative(float(left), float(right))
            else:
                difference = math.inf
            relative_differences[field] = difference
            if not np.isfinite(difference) or difference > 1.0e-11:
                gates.append(
                    f"A0 cross-MPI stable scalar relative identity failed: {name}.{field}"
                )
        normalized_defect_differences: dict[str, float] = {}
        for field in normalized_defect_fields:
            left = current.get(field)
            right = prior.get(field)
            difference = (
                float(abs(float(left) - float(right)))
                if _finite(left) and _finite(right) else math.inf
            )
            normalized_defect_differences[field] = difference
            if not np.isfinite(difference) or difference > 1.0e-11:
                gates.append(
                    f"A0 cross-MPI normalized defect absolute identity failed: {name}.{field}"
                )
        comparisons.append({
            "name": name,
            "implemented_vector_relative": float(key_relative_implemented),
            "explicit_vector_relative": float(key_relative_explicit),
            "stable_scalar_relative_differences": relative_differences,
            "normalized_defect_absolute_differences": normalized_defect_differences,
        })
    return {
        "status": "compared",
        "path": str(reference_path),
        "sha256": _sha256(reference_path),
        "probe_comparisons": comparisons,
        "relative_limit": 1.0e-11,
        "normalized_defect_absolute_limit": 1.0e-11,
    }


def _check_a0_record(
    record_path: Path, watchdog_compact: Path, expected_sha: str,
    record: dict[str, Any], mpi1_reference: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    lifecycle_failures: list[str] = []
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    if not raw_dir.is_absolute() or not raw_dir.is_dir():
        errors.append("A0 raw_dir is missing/invalid")
    provenance_error = _a0_check_provenance(
        record, record_path, expected_sha, errors, raw_dir,
    )
    _a0_check_markers(record, raw_dir, record_path, expected_sha, errors)
    resource = _check_watchdog(
        watchdog_compact, record, record_path, expected_sha,
        errors, gates, lifecycle_failures, mpi_size=record.get("mpi_size"),
    )
    watchdog_raw = resource.get("watchdog_raw")
    if watchdog_raw is not None and Path(str(watchdog_raw)).parent != raw_dir.parent:
        errors.append("A0 watchdog raw is not a sibling of worker raw_dir")
    _a0_check_architecture(record, errors)
    if record.get("record_authority") != "raw-shards-only; checker derives A0 classification":
        errors.append("A0 record authority is not raw-shards-only")

    shards, _manifest = _a0_load_shards(record, raw_dir, errors)
    merged_arrays, probe_shards = _a0_check_inventory_shards(
        record, shards, errors,
    )
    p63 = merged_arrays.get("p63")
    p63_audit = record.get("p63_audit")
    if (
        p63 is None
        or p63.dtype != np.dtype("complex128")
        or p63.shape != (882, 144)
        or not isinstance(p63_audit, dict)
    ):
        errors.append("A0 P63 raw/audit shape closure failed")
    else:
        singular = np.linalg.svd(p63, compute_uv=False)
        threshold = max(p63.shape) * np.finfo(float).eps * float(singular[0])
        observed = {
            "shape": [882, 144],
            "dtype": "complex128",
            "sigma_min": float(singular[-1]),
            "sigma_max": float(singular[0]),
            "rank_threshold": float(threshold),
            "rank": int(np.count_nonzero(singular > threshold)),
            "finite": bool(np.all(np.isfinite(p63))),
        }
        for key, value in observed.items():
            if p63_audit.get(key) != value:
                errors.append(f"A0 P63 stored field mismatch: {key}")
        if observed["rank"] != 144 or not observed["finite"]:
            gates.append("A0 P63 rank/finite Gate failed")

    inventory = record.get("material_inventory")
    classes = record.get("material_classes")
    class_metrics: list[dict[str, Any]] = []
    if (
        not isinstance(inventory, dict)
        or not isinstance(classes, list)
        or not isinstance(inventory.get("classes"), list)
        or len(classes) != len(inventory["classes"])
    ):
        errors.append("A0 material inventory/audits are not closed")
    else:
        _check_material_inventory(inventory, classes, errors)
        for item in classes:
            if isinstance(item, dict):
                class_metrics.append(_check_class(item, merged_arrays, errors, gates))

    probes = record.get("probes")
    if not isinstance(probes, list) or [item.get("name") for item in probes if isinstance(item, dict)] != list(PROBE_NAMES):
        errors.append("A0 probe identities/order are not frozen")
        probes = []
    probe_metrics: list[dict[str, Any]] = []
    mpi_size = record.get("mpi_size") if type(record.get("mpi_size")) is int else -1
    for name, item in zip(PROBE_NAMES, probes, strict=True):
        probe_metrics.append(
            _a0_check_probe(
                name, item, probe_shards.get(name, []), errors, gates,
                mpi_size,
            )
        )
    cross_mpi = _a0_check_mpi1_reference(
        record, probe_metrics, mpi1_reference, expected_sha, errors, gates,
    )
    if not shards:
        errors.append("A0 has no readable raw rank shards")
    elif len(shards) != record.get("mpi_size"):
        errors.append("A0 raw shard count does not match MPI size")

    classification: str
    if provenance_error:
        classification = "INPUT_PROVENANCE_INVALID"
    elif lifecycle_failures:
        classification = "EXECUTION_LIFECYCLE_FAILED"
    elif resource.get("resource_gate_failed") is True:
        classification = "RESOURCE_GATE_FAILED"
    elif errors:
        classification = "CONTRACT_INVALID"
    elif gates:
        classification = A0_GATE_CLASSIFICATION
    elif record.get("mpi_size") == 1:
        classification = A0_LOCAL_PASS_CLASSIFICATION
    else:
        classification = A0_PASS_CLASSIFICATION
    public_probe_metrics = [
        {key: value for key, value in item.items() if not key.startswith("_")}
        for item in probe_metrics
    ]
    return {
        "schema": A0_CHECK_SCHEMA,
        "passed": classification in {
            A0_LOCAL_PASS_CLASSIFICATION, A0_PASS_CLASSIFICATION,
        },
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "execution_lifecycle_failures": lifecycle_failures,
        "metrics": {
            "p63": {"shape": list(p63.shape)} if p63 is not None else {},
            "classes": class_metrics,
            "probes": public_probe_metrics,
            "resource": resource,
            "cross_mpi_identity": cross_mpi,
            "raw_shards": {
                "mpi_size": record.get("mpi_size"),
                "rank_count": len(shards),
                "canonical_merge": "physical key sort; consistent duplicates never averaged; explicit local contributions summed",
            },
        },
        "record": {"path": str(record_path.resolve()), "sha256": _sha256(record_path)},
        "expected_source_sha": expected_sha,
    }


def check_record(
    record_path: Path, watchdog_compact: Path, expected_sha: str,
    mpi1_reference: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    try:
        record = _read_json(record_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"passed": False, "classification": "CONTRACT_INVALID", "contract_errors": [str(exc)], "gate_failures": []}
    if not isinstance(record, dict):
        return {"passed": False, "classification": "CONTRACT_INVALID", "contract_errors": ["record is not an object"], "gate_failures": []}
    if record.get("schema") == A0_SCHEMA or record.get("stage") == "a0":
        for forbidden_record_field in ("status", "passed", "classification"):
            if forbidden_record_field in record:
                return {
                    "schema": A0_CHECK_SCHEMA,
                    "passed": False,
                    "classification": "CONTRACT_INVALID",
                    "contract_errors": [
                        f"worker record must not contain {forbidden_record_field}"
                    ],
                    "gate_failures": [],
                    "execution_lifecycle_failures": [],
                    "record": {"path": str(record_path.resolve()), "sha256": _sha256(record_path)},
                    "expected_source_sha": expected_sha,
                }
        return _check_a0_record(
            record_path, watchdog_compact, expected_sha, record, mpi1_reference,
        )
    for forbidden_record_field in ("status", "passed", "classification"):
        if forbidden_record_field in record:
            errors.append(f"worker record must not contain {forbidden_record_field}")
    profile = _profile(record)
    if profile is None:
        errors.append("unknown interlevel route profile")
        profile = _profile({})
    provenance_error = _check_runtime_provenance(record, record_path, expected_sha, errors, profile)
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    if not raw_dir.is_absolute() or not raw_dir.is_dir():
        errors.append("raw_dir missing/invalid")
    _check_markers(record, raw_dir, expected_sha, errors, profile)
    lifecycle_failures: list[str] = []
    resource = _check_watchdog(
        watchdog_compact, record, record_path, expected_sha, errors, gates, lifecycle_failures,
    )
    architecture = record.get("architecture")
    forbidden = architecture.get("forbidden") if isinstance(architecture, dict) else None
    required_forbidden = {
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_global_direct_factor", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    }
    if profile["route"] == "A":
        required_forbidden.add("p1_built")
    if not isinstance(forbidden, dict):
        errors.append("forbidden architecture facts are missing")
    else:
        for key in required_forbidden:
            if type(forbidden.get(key)) is not bool:
                errors.append(f"required forbidden fact is missing/nonboolean: {key}")
        for key, value in forbidden.items():
            if type(value) is not bool:
                errors.append(f"forbidden fact is not boolean: {key}")
            elif value:
                errors.append(f"forbidden object was reported built: {key}")
    if isinstance(architecture, dict):
        if record.get("local_gate_passed") is True:
            _check_level_topology(architecture, errors, profile["levels"])
        elif record.get("local_gate_passed") is False:
            levels = architecture.get("levels")
            expected_levels = {"level6": (True, False)}
            for degree in profile["levels"][1:]:
                expected_levels[f"level{degree}"] = (False, True)
            if not isinstance(levels, dict):
                errors.append("local Gate level facts are missing")
            else:
                for name, (foundation_built, not_run) in expected_levels.items():
                    facts = levels.get(name)
                    if (
                        not isinstance(facts, dict)
                        or facts.get("foundation_built") is not foundation_built
                        or facts.get("not_run_by_local_gate") is not not_run
                    ):
                        errors.append(f"local Gate level lifecycle mismatch: {name}")
        nested_names = {
            "case": (
                "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
                "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
                "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
                "pcgamg_hierarchy_built", "physical_solve", "recovery",
            ),
            "extension": (
                "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
                "p1_global_direct_factor", "smoother_built", "ksp_created",
                "physical_solve", "recovery",
            ),
        }
        if profile["route"] == "A":
            nested_names["extension"] = nested_names["extension"][:3] + ("p1_built",) + nested_names["extension"][3:]
        else:
            nested_names["extension"] = nested_names["extension"] + (
                "p6_exact_factor", "hx_hierarchy_built", "pcgamg_hierarchy_built",
                "retains_per_apply_history",
            )
        for group, names in nested_names.items():
            nested = architecture.get(group)
            if not isinstance(nested, dict):
                errors.append(f"nested architecture audit is missing: {group}")
            else:
                for name in names:
                    if type(nested.get(name)) is not bool:
                        errors.append(f"nested architecture fact is missing/nonboolean: {group}.{name}")
                    elif nested[name]:
                        errors.append(f"nested forbidden object was reported built: {group}.{name}")
        if profile["route"] == ROUTE_B:
            for name, expected in (
                ("level1_raw_matrix_built", record.get("local_gate_passed") is True),
                ("level1_global_direct_factor", False),
                ("p1_global_direct_factor", False),
            ):
                if architecture.get(name) is not expected:
                    errors.append(f"Route-B architecture fact mismatch: {name}")
    expected_not_run = (
        ["level2", "global_probes", "owner_probe"]
        if profile["route"] == ROUTE_B else ["level3", "global_probes"]
    )
    if record.get("local_gate_passed") is False and record.get("not_run_by_local_gate") != expected_not_run:
        errors.append("local Gate not-run ledger is not exact")
    settings = record.get("settings")
    frozen_settings = {
        "probe_names": list(PROBE_NAMES),
        "probe_alpha": [0.37, 0.19], "probe_beta": [-0.23, 0.41],
        "source_canonicalization": "owner_roundtrip_reduced_primal",
        "rank": profile["rank"], "levels": list(profile["levels"]),
        "transfer_pair": list(profile["pair"]),
        "lambda_min_limit": profile["lambda_min"],
        "lambda_max_limit": profile["lambda_max"],
        "condition_limit": profile["condition"],
        "hermitian_limit": 1.0e-12,
        "endpoint_residual_limit": ENDPOINT_LIMIT,
        "adjoint_limit": profile["adjoint"],
        "linearity_limit": 1.0e-12, "repeat_limit": 1.0e-13,
        "phase_once": "once_in_canonical_owner_route",
    }
    if profile["route"] == "A":
        frozen_settings["probe_q_interval"] = [0.10, 10.0]
    else:
        frozen_settings["nested_energy_limit"] = 1.0e-9
        frozen_settings["probe_q_center"] = 1.0
        frozen_settings["probe_q_abs_limit"] = 1.0e-9
    if not isinstance(settings, dict) or any(settings.get(key) != value for key, value in frozen_settings.items()):
        errors.append("Route-A settings/probe order mismatch")
    provenance_facts = record.get("provenance")
    if profile["route"] == ROUTE_B:
        if (
            not isinstance(provenance_facts, dict)
            or provenance_facts.get("p62_constructed_once") is not True
            or provenance_facts.get("p62_construction_count") != 1
            or provenance_facts.get("p62_construction_source") != "build_local_interlevel_edge_transfer(6,2)"
            or provenance_facts.get("p21_construction_count") != 1
            or provenance_facts.get("p21_construction_source") != "build_local_interlevel_edge_transfer(2,1)"
        ):
            errors.append("P62/P21 construction identity is not closed")
    elif not isinstance(provenance_facts, dict) or provenance_facts.get("p63_constructed_once") is not True or provenance_facts.get("p63_construction_count") != 1 or provenance_facts.get("p63_construction_source") != "build_local_interlevel_edge_transfer(6,3)":
        errors.append("P63 construction identity is not closed")
    raw_descriptor = record.get("raw_arrays")
    probes = record.get("probes")
    arrays: dict[str, np.ndarray] = {}
    if not isinstance(raw_descriptor, dict):
        errors.append("raw array descriptor missing")
    else:
        raw_path = raw_dir / str(raw_descriptor.get("relative_path", ""))
        if not _inside(raw_path, raw_dir) or not raw_path.is_file():
            errors.append("raw NPZ missing/escaped")
        elif _sha256(raw_path) != raw_descriptor.get("sha256"):
            errors.append("raw NPZ SHA mismatch")
        else:
            try:
                with np.load(raw_path, allow_pickle=False) as loaded:
                    descriptors = raw_descriptor.get("arrays")
                    if not isinstance(descriptors, dict):
                        errors.append("raw array descriptor map is missing/malformed")
                    elif set(loaded.files) != set(descriptors):
                        errors.append("NPZ keys and raw descriptor keys are not exact")
                    else:
                        for name, descriptor in descriptors.items():
                            value = _load_array(name, loaded, descriptor, errors)
                            if value is not None:
                                arrays[name] = value
            except (OSError, ValueError, EOFError) as exc:
                errors.append(f"raw NPZ unreadable: {exc}")
    if profile["route"] == ROUTE_B:
        p62 = arrays.get("p62")
        p21 = arrays.get("p21")
        for name, value, expected in (("p62", p62, (882, 54)), ("p21", p21, (54, 12))):
            audit = record.get(f"{name}_audit")
            if value is None or value.dtype != np.dtype("complex128") or value.ndim != 2 or value.shape != expected or not isinstance(audit, dict):
                errors.append(f"{name.upper()} raw array is missing or has wrong shape")
                continue
            singular = np.linalg.svd(value, compute_uv=False)
            threshold = max(value.shape) * np.finfo(float).eps * float(singular[0])
            facts = {
                "shape": [int(expected[0]), int(expected[1])], "dtype": "complex128",
                "sigma_min": float(singular[-1]), "sigma_max": float(singular[0]),
                "rank_threshold": float(threshold),
                "rank": int(np.count_nonzero(singular > threshold)),
                "finite": bool(np.all(np.isfinite(value))),
            }
            for key, actual in facts.items():
                if audit.get(key) != actual:
                    errors.append(f"{name.upper()} stored field mismatch: {key}")
            if not facts["finite"]:
                gates.append(f"{name.upper()} finite Gate failed")
        local_transfers = record.get("local_transfers")
        if not isinstance(local_transfers, dict):
            errors.append("Route-B local transfer audit is missing")
        else:
            _check_local_transfer("6_2", p62, local_transfers.get("6_2"), errors, gates, (882, 54), profile)
            _check_local_transfer("2_1", p21, local_transfers.get("2_1"), errors, gates, (54, 12), profile)
    else:
        p63 = arrays.get("p63")
        p63_audit = record.get("p63_audit")
        if p63 is None or p63.dtype != np.dtype("complex128") or p63.ndim != 2 or p63.shape != (882, 144) or not isinstance(p63_audit, dict):
            errors.append("P63 raw array is missing or has wrong shape")
        else:
            singular = np.linalg.svd(p63, compute_uv=False)
            threshold = max(p63.shape) * np.finfo(float).eps * float(singular[0])
            p63_values = {
                "shape": [882, 144], "dtype": "complex128", "sigma_min": float(singular[-1]),
                "sigma_max": float(singular[0]), "rank_threshold": float(threshold),
                "rank": int(np.count_nonzero(singular > threshold)),
                "finite": bool(np.all(np.isfinite(p63))),
            }
            for key, value in p63_values.items():
                if p63_audit.get(key) != value:
                    errors.append(f"P63 stored field mismatch: {key}")
            if p63_values["rank"] != 144:
                gates.append("P63 rank Gate failed")
    classes = record.get("material_classes")
    inventory = record.get("material_inventory")
    class_metrics: list[dict[str, Any]] = []
    if not isinstance(classes, list) or not isinstance(inventory, dict) or not isinstance(inventory.get("classes"), list) or len(classes) != len(inventory["classes"]):
        errors.append("material class inventory/records are not closed")
    else:
        _check_material_inventory(inventory, classes, errors)
        for item in classes:
            if isinstance(item, dict):
                class_metrics.append(_check_class(item, arrays, errors, gates, profile))
    local_gate_passed = record.get("local_gate_passed")
    if type(local_gate_passed) is not bool:
        errors.append("local_gate_passed is missing/nonboolean")
    else:
        computed_local_gate = bool(class_metrics) and all(
            metric.get("gate_passed") is True for metric in class_metrics
        )
        if local_gate_passed != computed_local_gate:
            errors.append("local_gate_passed disagrees with independent class metrics")
    if isinstance(raw_descriptor, dict) and isinstance(raw_descriptor.get("arrays"), dict):
        allowed = {"p62", "p21"} if profile["route"] == ROUTE_B else {"p63"}
        for item in classes if isinstance(classes, list) else ():
            if isinstance(item, dict) and isinstance(item.get("class_digest"), str):
                prefix = f"class_{item['class_digest']}"
                class_coarse_key = "b2" if profile["route"] == ROUTE_B else "b3"
                allowed.update({f"{prefix}__{class_coarse_key}", f"{prefix}__b6p", f"{prefix}__eigenvector_min", f"{prefix}__eigenvector_max"})
        for item in probes if isinstance(probes, list) else ():
            if isinstance(item, dict) and isinstance(item.get("raw_roles"), dict):
                allowed.update(value for value in item["raw_roles"].values() if isinstance(value, str))
        owner_probe = record.get("owner_probe")
        if isinstance(owner_probe, dict) and isinstance(owner_probe.get("raw_roles"), dict):
            allowed.update(value for value in owner_probe["raw_roles"].values() if isinstance(value, str))
        extra = set(raw_descriptor["arrays"]) - allowed
        if extra:
            errors.append(f"unknown raw array roles: {sorted(extra)}")
    probe_metrics: list[dict[str, Any]] = []
    owner_metrics: dict[str, Any] = {}
    descriptors = raw_descriptor.get("arrays", {}) if isinstance(raw_descriptor, dict) else {}
    if record.get("local_gate_passed") is True and (not isinstance(probes, list) or [item.get("name") for item in probes if isinstance(item, dict)] != list(PROBE_NAMES)):
        errors.append("probe identities/order are not frozen")
    elif record.get("local_gate_passed") is False and probes != []:
        errors.append("local Gate negative must not contain probe facts")
    else:
        expected_rows: dict[str, int] = {}
        levels = architecture.get("levels") if isinstance(architecture, dict) else None
        if record.get("local_gate_passed") is True:
            if not isinstance(levels, dict):
                errors.append("probe dimension authority is missing: architecture.levels")
            else:
                coarse_level_name = f"level{profile['pair'][1]}"
                fine_level_name = f"level{profile['pair'][0]}"
                for level_name, label in ((coarse_level_name, "coarse"), (fine_level_name, "fine")):
                    level = levels.get(level_name)
                    matrix = level.get("matrix") if isinstance(level, dict) else None
                    rows = matrix.get("rows") if isinstance(matrix, dict) else None
                    cols = matrix.get("cols") if isinstance(matrix, dict) else None
                    if type(rows) is not int or rows <= 0 or type(cols) is not int or cols <= 0 or rows != cols:
                        errors.append(f"probe dimension authority is not square/positive: {level_name}")
                    else:
                        expected_rows[label] = rows
        if record.get("local_gate_passed") is True and set(expected_rows) != {"coarse", "fine"}:
            errors.append("probe dimension authority is incomplete")
        elif record.get("local_gate_passed") is True:
            for item in probes:
                if isinstance(item, dict):
                    probe_metrics.append(
                        _check_probe(
                            item,
                            arrays,
                            descriptors,
                            errors,
                            gates,
                            expected_rows["coarse"],
                            expected_rows["fine"],
                            coarse_action_key=profile["coarse_key"],
                            profile=profile,
                        )
                    )
            if profile["route"] == ROUTE_B:
                level2 = levels.get("level2") if isinstance(levels, dict) else None
                level1 = levels.get("level1") if isinstance(levels, dict) else None
                matrix2 = level2.get("matrix") if isinstance(level2, dict) else None
                matrix1 = level1.get("matrix") if isinstance(level1, dict) else None
                rows2 = matrix2.get("rows") if isinstance(matrix2, dict) else None
                rows1 = matrix1.get("rows") if isinstance(matrix1, dict) else None
                owner_probe = record.get("owner_probe")
                if type(rows2) is not int or type(rows1) is not int or rows2 <= 0 or rows1 <= 0:
                    errors.append("Route-B owner probe dimension authority is missing")
                else:
                    owner_metrics = _check_owner_probe(
                        owner_probe, arrays, errors, gates, rows1, rows2,
                    )
                if owner_probe is None:
                    errors.append("Route-B owner probe is missing")
            else:
                owner_metrics = None
        else:
            owner_metrics = None
    if profile["route"] == ROUTE_B and record.get("local_gate_passed") is False and record.get("owner_probe") is not None:
        errors.append("Route-B local Gate negative must not contain owner probe facts")
    if provenance_error:
        classification = "INPUT_PROVENANCE_INVALID"
    elif lifecycle_failures:
        classification = "EXECUTION_LIFECYCLE_FAILED"
    elif resource.get("resource_gate_failed") is True:
        classification = "RESOURCE_GATE_FAILED"
    elif errors:
        classification = "CONTRACT_INVALID"
    elif gates:
        classification = "CLOSED_BY_INTERLEVEL_SPECTRAL_GATE"
    else:
        classification = "STRUCTURALLY_QUALIFIED"
    metrics = {"classes": class_metrics, "probes": probe_metrics, "resource": resource}
    if profile["route"] == ROUTE_B:
        metrics["owner_probe"] = owner_metrics
    return {
        "schema": profile["check_schema"],
        "passed": classification == "STRUCTURALLY_QUALIFIED",
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "execution_lifecycle_failures": lifecycle_failures,
        "metrics": metrics,
        "record": {"path": str(record_path.resolve()), "sha256": _sha256(record_path)},
        "expected_source_sha": expected_sha,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--mpi1-reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    result = check_record(
        args.record.resolve(), args.watchdog_compact.resolve(),
        args.expected_source_sha,
        args.mpi1_reference.resolve() if args.mpi1_reference is not None else None,
    )
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
