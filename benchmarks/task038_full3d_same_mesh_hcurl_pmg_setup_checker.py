"""Independent checker for the setup-only p6/p3/p1 same-mesh candidate.

Only JSON, NPZ, and the external watchdog stream are inputs.  The checker does
not import the worker, a solver, PETSc, MPI, or a numerical setup helper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_setup"
STAGE = "c1-p6-setup"
CASE = "p6-h10-mpi1"
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.setup-record.v2"
MARKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.setup-marker.v2"
CHECKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.setup-check.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
PROBE_SOURCE_SCHEMA = "task038.v13.c0.physical-canonical-source.v1"
PROBE_SOURCE_GENERATION = "physical_canonical_key_sha256_v1"
PROBE_SOURCE_ROLE = "full_fe_dual"
PROBE_SEEDS = [
    "task038.v13.c1.p6-setup-probe-x-v1",
    "task038.v13.c1.p6-setup-probe-y-v1",
]
EXPECTED_LEVELS = [6, 3, 1]
EXPECTED_PAIRS = [[6, 3], [3, 1]]
EXPECTED_MARKERS = [
    "paths_ready",
    "bundle_built",
    "audit_ready",
    "reserve_built",
    "pc_applies_complete",
    "retained_ready",
    "reserve_destroyed",
    "bundle_destroyed",
    "record_written",
]
EXPECTED_APPLY_LABELS = [
    "x",
    "y",
    "x_repeat",
    "combo",
    "alpha_x",
    "beta_y",
    "x_repeat_2",
    "y_repeat",
    "combo_repeat",
    "y_repeat_2",
]
EXPECTED_INPUT_INDICES = [0, 1, 0, 2, 3, 4, 0, 1, 2, 1]
ALPHA = 0.37 - 0.19j
BETA = -0.23 + 0.41j
COLD_RSS_LIMIT = 2_000_000_000
RETAINED_RSS_LIMIT = 1_800_000_000
REPEAT_LIMIT = 1e-13
LINEARITY_LIMIT = 1e-12
P1_LIMIT = 1e-11


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError, OverflowError):
        return False


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(right)), np.finfo(float).tiny)
    return float(np.linalg.norm(left - right) / denominator)


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _gate(gates: list[str], message: str) -> None:
    gates.append(message)


def _load_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"{label} is not strict JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        _error(errors, f"{label} must be a JSON object")
        return {}
    return value


def _mapping(value: Any, errors: list[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error(errors, f"{label} must be an object")
        return {}
    return value


def _require(mapping: dict[str, Any], key: str, errors: list[str], label: str) -> Any:
    if key not in mapping:
        _error(errors, f"missing {label}.{key}")
        return None
    return mapping[key]


def _exact(mapping: dict[str, Any], key: str, expected: Any, errors: list[str], label: str) -> Any:
    value = _require(mapping, key, errors, label)
    if value != expected:
        _error(errors, f"{label}.{key}={value!r}, expected {expected!r}")
    return value


def _check_provenance(
    record: dict[str, Any],
    record_path: Path,
    expected_source_sha: str,
    errors: list[str],
) -> tuple[Path | None, dict[str, Any]]:
    _exact(record, "schema", RECORD_SCHEMA, errors, "record")
    _exact(record, "stage", STAGE, errors, "record")
    _exact(record, "case", CASE, errors, "record")
    for forbidden in ("status", "classification", "passed"):
        if forbidden in record:
            _error(errors, f"worker record must not contain decision field {forbidden}")
    raw_value = _require(record, "raw_dir", errors, "record")
    stored_record = _require(record, "record_path", errors, "record")
    _exact(record, "isolated_jit_cache", True, errors, "record")
    jit_value = _require(record, "jit_cache_dir", errors, "record")
    raw_dir: Path | None = None
    jit_cache_dir: Path | None = None
    if isinstance(raw_value, str) and Path(raw_value).is_absolute():
        raw_dir = Path(raw_value).resolve()
    else:
        _error(errors, "record.raw_dir must be absolute")
    if isinstance(jit_value, str) and Path(jit_value).is_absolute():
        jit_cache_dir = Path(jit_value).resolve()
    else:
        _error(errors, "record.jit_cache_dir must be absolute")
    if not isinstance(stored_record, str) or not Path(stored_record).is_absolute():
        _error(errors, "record.record_path must be absolute")
    elif Path(stored_record).resolve() != record_path.resolve():
        _error(errors, "record.record_path differs from checker input")
    if raw_dir is not None:
        if raw_dir == record_path.resolve():
            _error(errors, "worker record path must differ from raw_dir")
        if not raw_dir.is_dir():
            _error(errors, "record.raw_dir does not exist")
    if raw_dir is not None and jit_cache_dir is not None:
        expected_jit_cache = (raw_dir.parent / "jit_cache").resolve()
        if jit_cache_dir != expected_jit_cache:
            _error(errors, "record.jit_cache_dir is not raw_dir.parent/jit_cache")
        if not jit_cache_dir.is_dir():
            _error(errors, "record.jit_cache_dir does not exist")
    provenance = _mapping(
        _require(record, "provenance", errors, "record"), errors, "record.provenance"
    )
    for key in (
        "source_sha",
        "branch",
        "clean_source_tree",
        "qualified_activation",
        "python_executable",
        "mpi_size",
        "petsc_scalar_type",
        "petsc_int_type",
        "threads",
        "abi_modules",
        "input_path",
        "input_sha256",
        "jit_cache_dir",
        "isolated_jit_cache",
        "command",
    ):
        _require(provenance, key, errors, "record.provenance")
    _exact(provenance, "source_sha", expected_source_sha, errors, "provenance")
    _exact(provenance, "branch", BRANCH, errors, "provenance")
    _exact(provenance, "clean_source_tree", True, errors, "provenance")
    _exact(provenance, "qualified_activation", "1", errors, "provenance")
    _exact(provenance, "mpi_size", 1, errors, "provenance")
    _exact(provenance, "petsc_scalar_type", "complex128", errors, "provenance")
    _exact(provenance, "petsc_int_type", "int32", errors, "provenance")
    _exact(provenance, "isolated_jit_cache", True, errors, "provenance")
    if jit_cache_dir is not None:
        _exact(provenance, "jit_cache_dir", str(jit_cache_dir), errors, "provenance")
    threads = _mapping(provenance.get("threads"), errors, "provenance.threads")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        _exact(threads, name, "1", errors, "provenance.threads")
    executable = provenance.get("python_executable")
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        _error(errors, "provenance.python_executable must be absolute")
    input_path_value = provenance.get("input_path")
    input_path = Path(input_path_value) if isinstance(input_path_value, str) else None
    if input_path is None or not input_path.is_absolute() or not input_path.is_file():
        _error(errors, "provenance.input_path must be an existing absolute file")
    else:
        if _sha256_file(input_path) != provenance.get("input_sha256"):
            _error(errors, "provenance input SHA256 mismatch")
    command = record.get("command")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        _error(errors, "record.command must be a string list")
        command = []
    if provenance.get("command") != command:
        _error(errors, "provenance.command differs from record.command")
    if command and (command[0] != executable or command[1:3] != ["-m", MODULE]):
        _error(errors, "worker command does not identify the setup worker")
    if raw_dir is not None and command:
        expected_tail = [
            "--stage", STAGE, "--case", CASE,
            "--raw-dir", str(raw_dir),
            "--jit-cache-dir", str(jit_cache_dir) if jit_cache_dir is not None else "",
            "--record", str(record_path.resolve()),
            "--expected-source-sha", expected_source_sha,
            "--expected-mpi-size", "1",
            "--input", str(input_path.resolve()) if input_path is not None else "",
        ]
        if command[3:] != expected_tail:
            _error(errors, "record.command is not the fixed setup command")
    return raw_dir, provenance


def _check_markers(
    record: dict[str, Any],
    raw_dir: Path | None,
    expected_source_sha: str,
    errors: list[str],
) -> dict[str, int]:
    lifecycle = _mapping(record.get("lifecycle"), errors, "record.lifecycle")
    _exact(lifecycle, "marker_relative_dir", "markers", errors, "lifecycle")
    names = _exact(lifecycle, "marker_names", EXPECTED_MARKERS, errors, "lifecycle")
    _exact(lifecycle, "destroy_order", ["reserve", "bundle"], errors, "lifecycle")
    _exact(lifecycle, "record_written_after_destroy", True, errors, "lifecycle")
    if raw_dir is None:
        return {}
    marker_dir = raw_dir / "markers"
    if not marker_dir.is_dir():
        _error(errors, "marker directory is missing")
        return {}
    if not isinstance(names, list):
        return {}
    times: dict[str, int] = {}
    for name in EXPECTED_MARKERS:
        marker = _load_json(marker_dir / f"{name}.json", errors, f"marker {name}")
        _exact(marker, "schema", MARKER_SCHEMA, errors, f"marker {name}")
        _exact(marker, "marker", name, errors, f"marker {name}")
        _exact(marker, "source_sha", expected_source_sha, errors, f"marker {name}")
        wall = _require(marker, "wall_time_ns", errors, f"marker {name}")
        if type(wall) is not int or wall < 0:
            _error(errors, f"marker {name}.wall_time_ns is invalid")
        else:
            times[name] = wall
        _mapping(marker.get("facts"), errors, f"marker {name}.facts")
    if list(times) == EXPECTED_MARKERS and any(times[a] >= times[b] for a, b in zip(EXPECTED_MARKERS, EXPECTED_MARKERS[1:])):
        _error(errors, "marker wall times are not strictly ordered")
    return times


def _check_watchdog(
    compact: dict[str, Any],
    record: dict[str, Any],
    expected_source_sha: str,
    raw_dir: Path | None,
    marker_times: dict[str, int],
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    _exact(compact, "schema", WATCHDOG_SCHEMA, errors, "watchdog")
    _exact(compact, "source_sha", expected_source_sha, errors, "watchdog")
    _exact(compact, "worker_command", record.get("command"), errors, "watchdog")
    _exact(compact, "watchdog_poll_seconds", 0.25, errors, "watchdog")
    _exact(compact, "watchdog_rss_limit_bytes", COLD_RSS_LIMIT, errors, "watchdog")
    _exact(compact, "returncode", 0, errors, "watchdog")
    _exact(compact, "natural_exit", True, errors, "watchdog")
    _exact(compact, "no_orphan", True, errors, "watchdog")
    _exact(compact, "all_status_readable", True, errors, "watchdog")
    if raw_dir is not None:
        _exact(compact, "worker_raw_dir", str(raw_dir), errors, "watchdog")
        record_value = record.get("record_path")
        expected_record = (
            str(Path(record_value).resolve())
            if isinstance(record_value, str) and Path(record_value).is_absolute()
            else None
        )
        _exact(compact, "worker_record", expected_record, errors, "watchdog")
    raw_value = compact.get("watchdog_raw")
    raw_path = Path(raw_value) if isinstance(raw_value, str) else None
    if raw_path is None or not raw_path.is_absolute() or not raw_path.is_file():
        _error(errors, "watchdog.watchdog_raw must be an existing absolute JSONL file")
        return {}
    raw_sha = compact.get("raw_sha256")
    if not isinstance(raw_sha, str) or _sha256_file(raw_path) != raw_sha:
        _error(errors, "watchdog raw SHA256 mismatch")
    samples: list[dict[str, Any]] = []
    try:
        lines = raw_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _error(errors, f"cannot read watchdog raw stream: {exc}")
        return {}
    for line_no, line in enumerate(lines, 1):
        try:
            sample = json.loads(line, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
        except (ValueError, TypeError) as exc:
            _error(errors, f"watchdog sample {line_no} is invalid JSON: {exc}")
            continue
        authority = sample.get("authority") if isinstance(sample, dict) else None
        process = authority.get("process_tree") if isinstance(authority, dict) else None
        if not isinstance(sample, dict) or not isinstance(process, dict):
            _error(errors, f"watchdog sample {line_no} lacks process-tree authority")
            continue
        wall = sample.get("wall_time_ns")
        rss = process.get("rss_bytes")
        swap = process.get("swap_bytes")
        readable = process.get("all_status_readable")
        if type(wall) is not int or type(rss) is not int or type(swap) is not int or type(readable) is not bool:
            _error(errors, f"watchdog sample {line_no} has malformed resource facts")
            continue
        if wall < 0 or rss < 0 or swap < 0:
            _error(errors, f"watchdog sample {line_no} has negative resource facts")
            continue
        if not readable:
            _error(errors, f"watchdog sample {line_no} is not readable")
        samples.append({"wall_time_ns": wall, "rss_bytes": rss, "swap_bytes": swap})
    if not samples:
        _error(errors, "watchdog has no readable resource samples")
        return {}
    if any(
        first["wall_time_ns"] >= second["wall_time_ns"]
        for first, second in zip(samples, samples[1:])
    ):
        _error(errors, "watchdog sample wall times are not strictly increasing")
    cold_peak = max(item["rss_bytes"] for item in samples)
    cold_swap = max(item["swap_bytes"] for item in samples)
    if cold_peak >= COLD_RSS_LIMIT:
        _gate(gates, f"cold process-tree peak {cold_peak} >= {COLD_RSS_LIMIT}")
    if cold_swap != 0:
        _gate(gates, f"cold process-tree swap is {cold_swap}")
    ready = marker_times.get("retained_ready")
    stop = marker_times.get("reserve_destroyed")
    retained = (
        [item for item in samples if ready is not None and stop is not None and ready <= item["wall_time_ns"] <= stop]
        if ready is not None and stop is not None else []
    )
    if not retained:
        _gate(gates, "retained window has no watchdog samples")
    retained_peak = max((item["rss_bytes"] for item in retained), default=-1)
    retained_swap = max((item["swap_bytes"] for item in retained), default=-1)
    if retained_peak >= RETAINED_RSS_LIMIT:
        _gate(gates, f"retained process-tree peak {retained_peak} >= {RETAINED_RSS_LIMIT}")
    if retained_swap != 0:
        _gate(gates, f"retained process-tree swap is {retained_swap}")
    for key, expected in (
        ("sample_count", len(samples)),
        ("peak_process_tree_rss_bytes", cold_peak),
        ("max_process_tree_swap_bytes", cold_swap),
    ):
        if compact.get(key) != expected:
            _error(errors, f"watchdog.{key} does not match raw samples")
    return {
        "cold_peak_process_tree_rss_bytes": cold_peak,
        "cold_max_process_tree_swap_bytes": cold_swap,
        "sample_count": len(samples),
        "retained_sample_count": len(retained),
        "retained_peak_process_tree_rss_bytes": retained_peak,
        "retained_max_process_tree_swap_bytes": retained_swap,
        "all_status_readable": True,
    }


def _positive(value: Any, errors: list[str], label: str) -> bool:
    if type(value) not in (int, float) or not _finite(value) or value <= 0:
        _error(errors, f"{label} must be finite and positive")
        return False
    return True


def _check_architecture(
    audit: dict[str, Any], errors: list[str]
) -> tuple[int | None, dict[str, Any]]:
    _exact(audit, "schema", "task038.same_mesh_hcurl_pmg.setup.v1", errors, "setup_audit")
    profile = _mapping(audit.get("profile"), errors, "setup_audit.profile")
    _exact(profile, "wavelength_nm", 13.5, errors, "profile")
    _exact(profile, "mesh_target_size_nm", 10.0, errors, "profile")
    _exact(profile, "levels", EXPECTED_LEVELS, errors, "profile")
    _exact(profile, "pairs", EXPECTED_PAIRS, errors, "profile")
    _exact(profile, "same_physical_mesh", True, errors, "profile")
    _exact(profile, "finalized_double_floquet_mpc_count", 3, errors, "profile")
    architecture = _mapping(audit.get("architecture"), errors, "setup_audit.architecture")
    required_false = (
        "p6_global_aij", "global_dense_transfer", "global_transfer_matrix",
        "numeric_allgather", "p6_factor", "outer_ksp_created", "restart_reserve",
        "physical_solve", "dtn", "recovery", "high_order_global_aij",
    )
    for key in required_false:
        _exact(architecture, key, False, errors, "architecture")
    _exact(architecture, "p6_matrix_free", True, errors, "architecture")
    _exact(architecture, "p3_sparse_allowed", True, errors, "architecture")
    _exact(architecture, "p1_sparse_allowed", True, errors, "architecture")
    layouts = _mapping(audit.get("layouts"), errors, "setup_audit.layouts")
    local_rows: int | None = None
    facts = _mapping(layouts.get("6"), errors, "layout 6")
    local_value = _require(facts, "local_owned_rows", errors, "layout 6")
    if type(local_value) is int and local_value > 0:
        local_rows = local_value
    else:
        _error(errors, "layout 6.local_owned_rows must be a positive integer")
    factor = _mapping(audit.get("p1_factor"), errors, "setup_audit.p1_factor")
    for key in ("factor_matrix_rows", "factor_matrix_nnz", "setup_count", "solve_count"):
        _positive(factor.get(key), errors, f"p1_factor.{key}")
    _exact(factor, "setup_count", 1, errors, "p1_factor")
    _exact(factor, "solve_count", 10, errors, "p1_factor")
    ledger = _mapping(audit.get("retained_ledger"), errors, "setup_audit.retained_ledger")
    components = _mapping(ledger.get("components_local_bytes"), errors, "ledger.components")
    if "restart_reserve_local_bytes" in components or "p6_exact_diagonal_global_numeric_bytes" in components:
        _error(errors, "setup ledger contains a non-component byte field")
    known = 0
    for name, value in components.items():
        if value is None:
            continue
        if type(value) is not int or value < 0:
            _error(errors, f"ledger component {name} must be a non-negative integer or null")
        else:
            known += value
    if ledger.get("known_component_local_bytes") != known:
        _error(errors, "setup ledger known component sum is not closed")
    global_facts = _mapping(ledger.get("global_facts"), errors, "ledger.global_facts")
    _positive(global_facts.get("p6_exact_diagonal_global_numeric_bytes"), errors, "ledger diagonal global bytes")
    _exact(ledger, "not_included", ["restart20_reserve", "outer_ksp", "source"], errors, "ledger")
    return local_rows, {"architecture": architecture, "factor": factor, "ledger": ledger}


def _check_reserve(
    reserve: dict[str, Any], local_rows: int | None, errors: list[str]
) -> dict[str, Any]:
    for key in ("basis_count", "auxiliary_vector_count", "vector_count", "local_entries_per_vector", "local_numeric_bytes"):
        _require(reserve, key, errors, "reserve")
    _exact(reserve, "basis_count", 21, errors, "reserve")
    _exact(reserve, "auxiliary_vector_count", 4, errors, "reserve")
    _exact(reserve, "vector_count", 25, errors, "reserve")
    _exact(reserve, "touched", True, errors, "reserve")
    if local_rows is not None:
        _exact(reserve, "local_entries_per_vector", local_rows, errors, "reserve")
        expected = 25 * local_rows * 16
        _exact(reserve, "local_numeric_bytes", expected, errors, "reserve")
    return reserve


def _check_probes(
    record: dict[str, Any], raw_dir: Path | None, errors: list[str], gates: list[str]
) -> dict[str, Any]:
    probes = _mapping(record.get("probes"), errors, "record.probes")
    _exact(probes, "probe_kind", "canonical_diagnostic_dual", errors, "probes")
    _exact(probes, "no_pde_rhs", True, errors, "probes")
    _exact(probes, "no_physical_solve", True, errors, "probes")
    _exact(probes, "no_outer_ksp", True, errors, "probes")
    _exact(probes, "apply_count", 10, errors, "probes")
    _exact(probes, "input_labels", ["x", "y", "combo", "alpha_x", "beta_y"], errors, "probes")
    _exact(probes, "apply_labels", EXPECTED_APPLY_LABELS, errors, "probes")
    _exact(probes, "apply_input_indices", EXPECTED_INPUT_INDICES, errors, "probes")
    source_facts = probes.get("source_facts")
    if not isinstance(source_facts, list) or len(source_facts) != len(PROBE_SEEDS):
        _error(errors, "probes.source_facts must contain the two fixed source facts")
    else:
        for index, (facts_value, seed) in enumerate(zip(source_facts, PROBE_SEEDS, strict=True)):
            facts = _mapping(facts_value, errors, f"probe source {index}")
            for key, expected in (
                ("schema", PROBE_SOURCE_SCHEMA),
                ("source_generation", PROBE_SOURCE_GENERATION),
                ("role", PROBE_SOURCE_ROLE),
                ("fixed_seed", seed),
                ("source_finite", True),
                ("source_nonzero", True),
                ("dependent_value_authority", "slave_zero_dual_storage"),
                ("phase_application", "dual_source_slave_zero_no_phase_reapplication"),
            ):
                _exact(facts, key, expected, errors, f"probe source {index}")
    if raw_dir is None:
        return probes
    npz_facts = _mapping(probes.get("npz"), errors, "probes.npz")
    relative = npz_facts.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute() or Path(relative).name != relative:
        _error(errors, "probe NPZ path must be a raw-dir-relative filename")
        return probes
    npz_path = raw_dir / relative
    if not npz_path.is_file():
        _error(errors, "probe NPZ is missing")
        return probes
    if npz_facts.get("bytes") != npz_path.stat().st_size or npz_facts.get("sha256") != _sha256_file(npz_path):
        _error(errors, "probe NPZ descriptor does not match the file")
    _exact(npz_facts, "roles", ["input_before", "input_after", "outputs"], errors, "probes.npz")
    try:
        with np.load(npz_path, allow_pickle=False) as data:
            if set(data.files) != {"input_before", "input_after", "outputs"}:
                _error(errors, "probe NPZ role set is not exact")
                return probes
            before = np.asarray(data["input_before"])
            after = np.asarray(data["input_after"])
            outputs = np.asarray(data["outputs"])
    except (OSError, ValueError) as exc:
        _error(errors, f"probe NPZ cannot be read: {exc}")
        return probes
    if before.ndim != 2 or before.shape[0] != 5 or after.shape != before.shape or outputs.ndim != 2 or outputs.shape[0] != 10 or outputs.shape[1] != before.shape[1]:
        _error(errors, "probe NPZ shapes are not the fixed setup shapes")
        return probes
    if before.dtype != np.dtype(np.complex128) or after.dtype != np.dtype(np.complex128) or outputs.dtype != np.dtype(np.complex128):
        _error(errors, "probe NPZ arrays must be complex128")
        return probes
    if not np.all(np.isfinite(before)) or not np.all(np.isfinite(after)) or not np.all(np.isfinite(outputs)):
        _gate(gates, "probe arrays are non-finite")
    input_unchanged = bool(np.array_equal(before, after))
    if not input_unchanged:
        _gate(gates, "probe inputs changed during the ten applies")
    alpha_facts = _mapping(probes.get("alpha"), errors, "probes.alpha")
    beta_facts = _mapping(probes.get("beta"), errors, "probes.beta")
    try:
        alpha = complex(float(alpha_facts["real"]), float(alpha_facts["imag"]))
        beta = complex(float(beta_facts["real"]), float(beta_facts["imag"]))
    except (KeyError, TypeError, ValueError):
        _error(errors, "probe alpha/beta facts are incomplete")
        return probes
    if alpha != ALPHA or beta != BETA:
        _error(errors, "probe coefficients differ from the fixed qualification values")
    expected_combo = alpha * before[0] + beta * before[1]
    expected_alpha = alpha * before[0]
    expected_beta = beta * before[1]
    for actual, expected, label in ((before[2], expected_combo, "combo"), (before[3], expected_alpha, "alpha_x"), (before[4], expected_beta, "beta_y")):
        if _relative(actual, expected) > 1e-13:
            _gate(gates, f"probe {label} construction is not closed")
    repeats = max(
        _relative(outputs[0], outputs[2]),
        _relative(outputs[0], outputs[6]),
        _relative(outputs[1], outputs[7]),
        _relative(outputs[1], outputs[9]),
        _relative(outputs[3], outputs[8]),
    )
    linearity = _relative(outputs[3], outputs[4] + outputs[5])
    independent = float(np.linalg.norm(before[1] - (np.vdot(before[0], before[1]) / max(float(np.real(np.vdot(before[0], before[0]))), np.finfo(float).tiny)) * before[0]) / max(float(np.linalg.norm(before[1])), np.finfo(float).tiny))
    finite = bool(
        np.all(np.isfinite(before))
        and np.all(np.isfinite(after))
        and np.all(np.isfinite(outputs))
    )
    if repeats > REPEAT_LIMIT:
        _gate(gates, f"probe repeat relative {repeats} > {REPEAT_LIMIT}")
    if linearity > LINEARITY_LIMIT:
        _gate(gates, f"probe linearity relative {linearity} > {LINEARITY_LIMIT}")
    if independent <= 1e-8:
        _gate(gates, "probe pair is numerically collinear")
    rows = probes.get("rows")
    input_labels = probes.get("input_labels")
    if not isinstance(rows, list) or len(rows) != 10:
        _error(errors, "probe rows must contain exactly ten entries")
    elif not isinstance(input_labels, list) or len(input_labels) != 5:
        _error(errors, "probe input labels are incomplete")
    else:
        for index, row_value in enumerate(rows):
            row = _mapping(row_value, errors, f"probe row {index}")
            _exact(row, "label", EXPECTED_APPLY_LABELS[index], errors, f"probe row {index}")
            _exact(row, "input_label", input_labels[EXPECTED_INPUT_INDICES[index]], errors, f"probe row {index}")
            for key, expected in (("p6_smoother_apply_count", 2), ("p63_adjoint_count", 1), ("p63_primal_count", 1), ("lower_cycle_count", 1), ("p1_solve_count", 1)):
                _exact(row, key, expected, errors, f"probe row {index}")
            residual = row.get("p1_relative_residual")
            if not _finite(residual) or float(residual) > P1_LIMIT:
                _gate(gates, f"probe row {index} p1 residual exceeds {P1_LIMIT}")
    slave_values = probes.get("owned_slave_indices")
    owned_slave_max = 0.0
    if not isinstance(slave_values, list) or not all(type(value) is int for value in slave_values):
        _error(errors, "probe owned_slave_indices must be an integer list")
    elif any(value < 0 or value >= outputs.shape[1] for value in slave_values):
        _error(errors, "probe owned_slave_indices exceed NPZ storage")
    elif slave_values:
        slave_arrays = (before[:, slave_values], after[:, slave_values], outputs[:, slave_values])
        owned_slave_max = float(max(np.max(np.abs(array)) for array in slave_arrays))
        if owned_slave_max != 0.0:
            _gate(gates, "probe owned slave input or output is not zero")
    p1_residual_max = max(
        (float(row.get("p1_relative_residual")) for row in rows if isinstance(row, dict) and _finite(row.get("p1_relative_residual"))),
        default=float("nan"),
    )
    if not _finite(p1_residual_max) or p1_residual_max > P1_LIMIT:
        _gate(gates, "maximum p1 residual exceeds the setup limit")
    def row_total(key: str) -> int:
        total = 0
        for index, row_value in enumerate(rows if isinstance(rows, list) else ()):
            row = _mapping(row_value, errors, f"probe row {index}")
            value = row.get(key)
            if type(value) is not int:
                _error(errors, f"probe row {index}.{key} must be int")
            else:
                total += value
        return total

    row_totals = {
        "smoother_apply_total": row_total("p6_smoother_apply_count"),
        "p63_adjoint_total": row_total("p63_adjoint_count"),
        "p63_primal_total": row_total("p63_primal_count"),
        "lower_cycle_total": row_total("lower_cycle_count"),
        "p1_solve_total": row_total("p1_solve_count"),
    }
    for key, expected in row_totals.items():
        if expected != 10 * (2 if key == "smoother_apply_total" else 1):
            _error(errors, f"probes.{key} does not have the fixed ten-apply total")
    return {
        "apply_count": 10,
        "finite": finite,
        "input_unchanged": input_unchanged,
        "repeat_relative": repeats,
        "linearity_relative": linearity,
        "independent_probe_relative": independent,
        "owned_slave_max": owned_slave_max,
        "p1_relative_residual_max": p1_residual_max,
        **row_totals,
        "local_entries": int(before.shape[1]),
    }


def check_record(
    record_path: Path,
    watchdog_path: Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record = _load_json(record_path, errors, "record")
    raw_dir, _ = _check_provenance(record, record_path, expected_source_sha, errors)
    marker_times = _check_markers(record, raw_dir, expected_source_sha, errors)
    audit = _mapping(record.get("setup_audit"), errors, "record.setup_audit")
    local_rows, audit_facts = _check_architecture(audit, errors)
    reserve = _check_reserve(_mapping(record.get("reserve"), errors, "record.reserve"), local_rows, errors)
    probes = _check_probes(record, raw_dir, errors, gates)
    factor = audit_facts.get("factor", {})
    if factor.get("solve_count") != probes.get("p1_solve_total"):
        _error(errors, "p1 factor solve_count does not match the ten row counts")
    watchdog = _load_json(watchdog_path, errors, "watchdog")
    resource = _check_watchdog(
        watchdog,
        record,
        expected_source_sha,
        raw_dir,
        marker_times,
        errors,
        gates,
    )
    if errors:
        classification = "CONTRACT_INVALID"
        status = "FAIL"
    elif gates:
        classification = "C1_P6_SETUP_GATE_FAIL"
        status = "FAIL"
    else:
        classification = "C1_P6_SETUP_PASS"
        status = "PASS"
    return {
        "schema": CHECKER_SCHEMA,
        "status": status,
        "classification": classification,
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "metrics": {
            "local_rows": local_rows,
            "reserve_local_numeric_bytes": reserve.get("local_numeric_bytes"),
            "probe": probes,
            "p1_factor": audit_facts.get("factor", {}),
            "setup_ledger": audit_facts.get("ledger", {}),
        },
        "resource": resource,
        "lifecycle": {
            "destroy_order": ["reserve", "bundle"],
        },
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
    result = check_record(args.record.resolve(), args.watchdog_compact.resolve(), args.expected_source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    with args.output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({key: result[key] for key in ("status", "classification", "passed", "contract_errors", "gate_failures")}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ("CHECKER_SCHEMA", "check_record", "main")
