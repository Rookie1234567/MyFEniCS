"""Read-only qualification checker for the frozen Task037b M10 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    MANIFEST_SCHEMA,
    read_canonical_manifest,
    read_canonical_packet_shard,
)
from benchmarks.task035c_channel_resource_checker import (
    _compare_full_hybrid,
    _compare_to_significant_reference,
    _load_significant_reference,
    _order_key,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKER_SCHEMA = "task037b.m10-offline-check.v1"
WATCHDOG_SCHEMA = "task037b.m10-frozen-watchdog.v1"
RECORD_SCHEMA = "task037b.v6-traction-aligned-full-block-pc.v1"
QUALIFICATION_SCHEMA = "task037b.m10-frozen-positive-qualification.v1"
RSS_LIMIT_MIB = 6144.0
Q_TOLERANCE = 1.0e-5
FIELD_TOLERANCE = 5.0e-3
CANONICAL_TOLERANCE = 1.0e-5
OBSERVABLE_TOLERANCE = 1.0e-5
RESIDUAL_TOLERANCE = 5.0e-9
TRACTION_TOLERANCE = 1.0e-8
LIFECYCLE = (
    "setup",
    "solve",
    "retained_solution_postsolve",
    "bottom_recovery",
    "inter_side_cleanup",
    "top_recovery",
    "recovery_cleanup",
    "own_physics_grid",
    "precanonical_cleanup",
    "bottom_active_full_stream_cleanup",
    "top_active_full_stream_cleanup",
    "record",
)
FINAL_RELEASE_ORDER = (
    "recovery",
    "coupling",
    "bottom",
    "top",
    "positive",
    "negative",
)
FINAL_RELEASE_CHECKS = (
    "recovery_destroyed",
    "coupling_destroy_call_completed",
    "bottom_destroyed",
    "top_destroyed",
    "positive_destroy_call_completed",
    "negative_destroy_call_completed",
    "cleanup_collective_call_completed",
)
ARRAY_SPEC = {
    "x_nm": ((40,), "float64"),
    "y_nm": ((20,), "float64"),
    "z_nm": ((5,), "float64"),
    "E_V_per_m": ((5, 20, 40, 3), "complex128"),
    "H_A_per_m": ((5, 20, 40, 3), "complex128"),
    "modal_amplitudes": ((240,), "complex128"),
    "bottom_q": ((40,), "complex128"),
    "top_q": ((40,), "complex128"),
}
PROFILE = {
    "target": "hybrid",
    "degree": 6,
    "h_nm": 10.0,
    "modal_degree": 6,
    "modal_h_nm": 10.0,
    "wavelength_nm": 13.5,
    "polarization_kind": "s",
    "incident_grazing_deg": 10.0,
    "bottom_interface_nm": 10.0,
    "top_interface_nm": 110.0,
    "requested_modes": 120,
    "candidate_modes": 240,
    "dtN_modes_per_endcap": 40,
    "internal_propagation_model": "full3d_uniform_cg",
    "internal_traction_model": "scalar_cg_discrete_derivative",
    "operator_identity": "exact_monolithic_hybrid_operator",
    "solver_path": "block-ldu-action-full-solve",
    "preconditioner_identity": "fixed_whole_endcap_ilu0_plus_40_mode_dtn_woodbury",
    "subdomain_count": 1,
    "overlap": 0.0,
    "ilu_level": 0,
    "shift": 0.1,
    "near_degenerate_tolerance": 1.0e-6,
    "block_rotation_tolerance": 1.0e-6,
    "restart": 90,
    "max_it": 1000,
    "rtol": 5.0e-9,
    "initial_guess": "zero",
    "mpi_size": 8,
    "assembly_backend": "assembly_time_static_condensed",
}
RESIDUAL_FIELDS = (
    "reported_relative_residual",
    "global_true_relative_residual",
    "bottom_true_relative_residual",
    "top_true_relative_residual",
    "modal_true_relative_residual",
)


class EvidenceError(ValueError):
    """A required evidence contract is absent or inconsistent."""


class OutputExistsError(EvidenceError):
    """The immutable checker output already exists."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _finite(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise EvidenceError(f"{context} is not numeric") from error
    if not math.isfinite(result):
        raise EvidenceError(f"{context} is not finite")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{context} is not a mapping")
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EvidenceError(f"{context} is not a sequence")
    return value


def _path_candidates(value: str | Path, anchors: Sequence[Path]) -> tuple[Path, ...]:
    candidate = Path(value)
    if candidate.is_absolute():
        return (candidate,)
    paths: list[Path] = []
    for anchor in anchors:
        parent = anchor.resolve()
        while True:
            paths.append(parent / candidate)
            if parent == parent.parent:
                break
            parent = parent.parent
    paths.append(ROOT / candidate)
    return tuple(dict.fromkeys(path.resolve() for path in paths))


def _resolve_path(value: Any, anchors: Sequence[Path], context: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise EvidenceError(f"{context} path is not a string")
    candidates = _path_candidates(value, anchors)
    for path in candidates:
        if path.exists():
            return path
    raise EvidenceError(f"{context} path does not exist: {value}")


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _bind_file(
    value: Any,
    expected_sha256: Any,
    anchors: Sequence[Path],
    context: str,
) -> tuple[Path, dict[str, Any]]:
    path = _resolve_path(value, anchors, f"{context}.path")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(
            character not in "0123456789abcdefABCDEF" for character in expected_sha256
        )
    ):
        raise EvidenceError(f"{context}.sha256 is invalid")
    observed_sha = _sha256(path)
    _require(observed_sha == expected_sha256, f"{context} SHA mismatch")
    descriptor = {
        "path": _display_path(path),
        "resolved_path": str(path.resolve()),
        "sha256": observed_sha,
        "bytes": path.stat().st_size,
        "pass": True,
    }
    return path, descriptor


def _load_json_binding(
    path_value: str | Path,
    expected_sha256: str,
    context: str,
    anchors: Sequence[Path] = (ROOT,),
) -> tuple[Path, Mapping[str, Any], dict[str, Any]]:
    path, binding = _bind_file(path_value, expected_sha256, anchors, context)
    try:
        with path.open(encoding="utf-8") as stream:
            record = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"{context} JSON is invalid") from error
    return path, _mapping(record, context), binding


def _check_watchdog(
    path: Path,
    summary: Mapping[str, Any],
    expected_source_sha: str,
    anchors: Sequence[Path],
) -> tuple[bool, dict[str, Any], list[str], Path | None, Mapping[str, Any] | None]:
    failures: list[str] = []
    gate: dict[str, Any] = {}
    try:
        _require(summary.get("schema") == WATCHDOG_SCHEMA, "watchdog schema mismatch")
        _require(summary.get("frozen") is True, "watchdog frozen flag is false")
        _require(
            summary.get("explicit_opt_in") is True, "watchdog opt-in flag is false"
        )
        _require(
            summary.get("ordinary_default_changed") is False, "ordinary default changed"
        )
        source = _mapping(summary.get("source_preflight"), "watchdog source")
        gate["source"] = bool(
            source.get("head") == expected_source_sha
            and source.get("verified_clean_sha") == expected_source_sha
            and source.get("clean") is True
            and source.get("match") is True
            and source.get("dirty") == ""
        )
        worker = _mapping(summary.get("worker"), "watchdog worker")
        termination = _mapping(summary.get("termination"), "watchdog termination")
        control = _mapping(
            termination.get("process_control"), "watchdog process control"
        )
        gate["worker"] = worker.get("return_code") == 0
        gate["termination"] = bool(
            termination.get("classification") == "natural_exit"
            and termination.get("termination_calls") == 1
            and control.get("worker_exited") is True
            and control.get("process_group_exited") is True
        )
        resource_data = _mapping(summary.get("resource"), "watchdog resource")
        sample_count = int(resource_data.get("sample_count"))
        peak_rss = _finite(
            resource_data.get("process_tree_peak_rss_mib"),
            "watchdog resource peak RSS",
        )
        swap = _finite(
            resource_data.get("process_tree_peak_swap_mib"),
            "watchdog resource peak swap",
        )
        gate["resource"] = bool(
            sample_count > 0
            and peak_rss <= RSS_LIMIT_MIB
            and swap == 0.0
            and resource_data.get("rss_pass") is True
            and resource_data.get("swap_pass") is True
            and resource_data.get("pass") is True
            and resource_data.get("timeline_authority")
            == "simultaneous mpi_process_tree_rss_mb"
        )
        artifact_rows = _sequence(summary.get("artifacts"), "watchdog artifacts")
        artifact_map = {
            str(_mapping(item, "watchdog artifact").get("path")): _mapping(
                item, "watchdog artifact"
            )
            for item in artifact_rows
        }
        online_meta = _mapping(summary.get("online_record"), "watchdog online record")
        online_path, online_binding = _bind_file(
            online_meta.get("path"),
            online_meta.get("sha256"),
            anchors,
            "watchdog online record",
        )
        online_state = _load_json_binding(
            online_path,
            online_binding["sha256"],
            "watchdog online record",
            (online_path.parent, *anchors),
        )
        online_record = online_state[1]
        online_matches = []
        for item in artifact_rows:
            item_path = _resolve_path(
                _mapping(item, "watchdog artifact").get("path"),
                anchors,
                "watchdog online artifact.path",
            )
            if item_path == online_path:
                online_matches.append(_mapping(item, "watchdog online artifact"))
        _require(len(online_matches) == 1, "watchdog online artifact is not unique")
        online_descriptor = online_matches[0]
        _require(
            online_descriptor.get("sha256") == online_binding["sha256"]
            and online_descriptor.get("bytes") == online_binding["bytes"],
            "watchdog online artifact binding mismatch",
        )
        gate["online_artifact"] = bool(
            online_meta.get("json_valid") is True
            and online_meta.get("online_pass") is True
            and online_record.get("online_pass") is True
        )
        qualification = _mapping(summary.get("qualification"), "watchdog qualification")
        qualification_checks = _mapping(
            qualification.get("checks"), "watchdog qualification.checks"
        )
        expected_checks = {
            "worker_exit0": gate["worker"],
            "online_pass": gate["online_artifact"],
            "resource_pass": gate["resource"],
            "swap_zero": swap == 0.0,
            "no_timeout": termination.get("classification") != "wall_timeout",
            "process_group_clean": bool(
                control.get("worker_exited") is True
                and control.get("process_group_exited") is True
            ),
        }
        qualification_pass = bool(all(expected_checks.values()))
        gate["qualification"] = bool(
            qualification_pass and qualification.get("pass") is True
        )
        gate["qualification_consistency"] = bool(
            set(qualification_checks) == set(expected_checks)
            and all(
                qualification_checks.get(name) is value
                for name, value in expected_checks.items()
            )
            and qualification.get("status")
            == (
                "watchdog_pass_awaiting_offline_checker"
                if qualification_pass
                else "failed"
            )
        )
        expected_status = (
            "watchdog_pass_awaiting_offline_checker" if qualification_pass else "failed"
        )
        gate["summary_status"] = summary.get("status") == expected_status
        gate["summary_failures"] = bool(
            qualification_pass and summary.get("failures") == []
        )
        for suffix in (
            "memory_stages.jsonl",
            "memory_timeline.csv",
            "worker_stdout.txt",
        ):
            matches = [
                item for name, item in artifact_map.items() if name.endswith(suffix)
            ]
            _require(len(matches) == 1, f"watchdog artifact {suffix} is not unique")
            item = matches[0]
            artifact_path, descriptor = _bind_file(
                item.get("path"),
                item.get("sha256"),
                anchors,
                f"watchdog artifact {suffix}",
            )
            _require(
                item.get("bytes") == descriptor["bytes"],
                f"watchdog artifact {suffix} bytes mismatch",
            )
            _require(artifact_path.is_file(), f"watchdog artifact {suffix} missing")
        gate["artifacts"] = True
        failures.extend(
            f"watchdog.{name}" for name, passed in gate.items() if not passed
        )
    except (EvidenceError, TypeError, ValueError, OSError) as error:
        failures.append(f"watchdog:{error}")
    passed = bool(gate and all(gate.values()) and not failures)
    online_path = locals().get("online_path")
    online_record = locals().get("online_record")
    return passed, gate, failures, online_path, online_record


def _profile_gate(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    profile = record.get("profile")
    if not isinstance(profile, Mapping):
        return False, ["profile_missing"]
    for name, expected in PROFILE.items():
        if profile.get(name) != expected:
            failures.append(f"profile.{name}")
    return not failures, failures


def _bool_fields_gate(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if record.get("record_schema") != RECORD_SCHEMA:
        failures.append("record_schema")
    if record.get("qualification_schema") != QUALIFICATION_SCHEMA:
        failures.append("qualification_schema")
    if record.get("ordinary_default_changed") is not False:
        failures.append("ordinary_default_changed")
    if record.get("explicit_opt_in") is not True:
        failures.append("explicit_opt_in")
    qualification = record.get("qualification")
    if not isinstance(qualification, Mapping):
        failures.append("qualification_missing")
    else:
        for name in (
            "numerical_pass",
            "release_pass",
            "recovery_pass",
            "physics_pass",
            "lifecycle_pass",
            "source_after_pass",
            "final_release_pass",
            "integration_performance_pass",
            "error_free",
        ):
            if qualification.get(name) is not True:
                failures.append(f"qualification.{name}")
    if record.get("online_pass") is not True:
        failures.append("online_pass")
    if record.get("status") != "online_candidate_pass_awaiting_offline_checker":
        failures.append("status")
    return not failures, failures


def _linear_gate(record: Mapping[str, Any]) -> tuple[bool, dict[str, Any], list[str]]:
    failures: list[str] = []
    linear = _mapping(record.get("linear"), "linear")
    result: dict[str, Any] = {}
    result["reason"] = linear.get("reason")
    result["iterations"] = linear.get("iterations")
    try:
        reason = int(linear.get("reason"))
        iterations = int(linear.get("iterations"))
        if reason <= 0:
            failures.append("linear.reason")
        if not 0 < iterations <= 900:
            failures.append("linear.iterations")
    except (TypeError, ValueError):
        failures.append("linear.iterations_or_reason")
    if linear.get("linear_pass") is not True:
        failures.append("linear.linear_pass")
    postsolve = _mapping(linear.get("postsolve_audit"), "linear.postsolve_audit")
    if postsolve.get("pass") is not True:
        failures.append("linear.postsolve_pass")
    residuals = _mapping(
        linear.get("postsolve_residuals"), "linear.postsolve_residuals"
    )
    for field in RESIDUAL_FIELDS:
        try:
            value = _finite(residuals.get(field), field)
            if not 0.0 <= value <= RESIDUAL_TOLERANCE:
                failures.append(f"residual.{field}")
        except EvidenceError:
            failures.append(f"residual.{field}")
    result["residuals"] = dict(residuals)
    result["pass"] = not failures
    return not failures, result, failures


def _complex_pair(value: Any, context: str) -> complex:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EvidenceError(f"{context} is not a complex pair")
    _require(len(value) == 2, f"{context} complex pair length")
    result = complex(
        _finite(value[0], f"{context}.real"),
        _finite(value[1], f"{context}.imag"),
    )
    _require(
        math.isfinite(result.real) and math.isfinite(result.imag),
        f"{context} is not finite",
    )
    return result


def _traction_gate(
    physics: Mapping[str, Any],
) -> tuple[bool, dict[str, Any], list[str]]:
    failures: list[str] = []
    traction = _mapping(physics.get("traction"), "physics.traction")
    reports: dict[str, Any] = {}
    for side in ("bottom", "top"):
        report = _mapping(traction.get(side), f"physics.traction.{side}")
        try:
            relative = abs(
                _finite(report["relative_dual"], f"traction.{side}.relative_dual")
            )
            if relative > TRACTION_TOLERANCE:
                failures.append(f"traction.{side}.threshold")
            reports[side] = {"relative_dual": relative}
        except (EvidenceError, KeyError):
            failures.append(f"traction.{side}.finite")
    return not failures, reports, failures


def _orders_map(
    rows_value: Any, context: str
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    rows = _sequence(rows_value, context)
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for index, value in enumerate(rows):
        row = _mapping(value, f"{context}[{index}]")
        side = row.get("side")
        m = row.get("m")
        n = row.get("n")
        polarization = row.get("polarization")
        _require(side in {"bottom", "top"}, f"{context}[{index}].side")
        _require(
            isinstance(m, int) and not isinstance(m, bool), f"{context}[{index}].m"
        )
        _require(
            isinstance(n, int) and not isinstance(n, bool), f"{context}[{index}].n"
        )
        _require(polarization in {"s", "p"}, f"{context}[{index}].polarization")
        _order_key(row, f"{context}[{index}]")
        key = (str(side), int(m), int(n), str(polarization))
        _require(key not in result, f"{context} duplicate key {key}")
        for name in (
            "beta_per_nm",
            "total_projection",
            "incident_projection",
            "outgoing_amplitude",
            "outgoing_amplitude_at_boundary",
        ):
            value_complex = _complex_pair(row.get(name), f"{context}[{index}].{name}")
            _require(
                math.isfinite(value_complex.real) and math.isfinite(value_complex.imag),
                f"{context}[{index}].{name}",
            )
        for name in ("power_ratio", "R", "T"):
            _finite(row.get(name), f"{context}[{index}].{name}")
        result[key] = row
    _require(len(result) == 80, f"{context} does not contain 80 unique orders")
    return result


def _energy_gate(
    physics: Mapping[str, Any],
) -> tuple[bool, dict[str, float], list[str]]:
    failures: list[str] = []
    values: dict[str, float] = {}
    energy = _mapping(physics.get("energy"), "physics.energy")
    for name in ("R", "T", "A", "A_volume", "closure"):
        try:
            values[name] = _finite(energy[name], f"energy.{name}")
        except (EvidenceError, KeyError):
            failures.append(f"energy.{name}")
    if not failures and abs(values["closure"]) > 1.0e-5:
        failures.append("energy.closure")
    return not failures, values, failures


def _lifecycle_gate(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    lifecycle = _mapping(record.get("lifecycle"), "lifecycle")
    failures: list[str] = []
    if lifecycle.get("schema_version") != "task037b.m10-lifecycle.v1":
        failures.append("lifecycle.schema_version")
    if lifecycle.get("order") != list(LIFECYCLE):
        failures.append("lifecycle.order")
    observed = lifecycle.get("observed")
    if observed != list(LIFECYCLE):
        failures.append("lifecycle.observed")
    timestamps = lifecycle.get("timestamps")
    if not isinstance(timestamps, Sequence) or isinstance(timestamps, (str, bytes)):
        failures.append("lifecycle.timestamps")
    else:
        if len(timestamps) != len(LIFECYCLE):
            failures.append("lifecycle.timestamps.length")
        else:
            for index, timestamp in enumerate(timestamps):
                if (
                    not isinstance(timestamp, Mapping)
                    or timestamp.get("stage") != LIFECYCLE[index]
                ):
                    failures.append(f"lifecycle.timestamps.{index}")
    if lifecycle.get("pass") is not True:
        failures.append("lifecycle.pass")
    return not failures, failures


def _final_release_gate(
    record: Mapping[str, Any],
) -> tuple[bool, dict[str, Any], list[str]]:
    release = _mapping(record.get("final_release"), "final_release")
    checks = _mapping(release.get("checks"), "final_release.checks")
    failures: list[str] = []
    if set(checks) != set(FINAL_RELEASE_CHECKS):
        failures.append("final_release.checks.keys")
    failures.extend(
        f"final_release.checks.{name}"
        for name in FINAL_RELEASE_CHECKS
        if checks.get(name) is not True
    )
    order = release.get("order")
    if order != list(FINAL_RELEASE_ORDER):
        failures.append("final_release.order")
    if release.get("pass") is not True:
        failures.append("final_release.pass")
    return (
        not failures,
        {"checks": dict(checks), "order": order, "pass": not failures},
        failures,
    )


def _candidate_grid_metadata(record: Mapping[str, Any]) -> Mapping[str, Any]:
    physics = _mapping(record.get("physics"), "physics")
    return _mapping(physics.get("own_grid"), "physics.own_grid")


def _array_digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes(order="C")).hexdigest()


def _load_npz_payload(
    metadata: Mapping[str, Any],
    anchors: Sequence[Path],
    context: str,
    *,
    descriptor_names: Sequence[str],
    metadata_schema_key: str,
    expected_metadata_schema: str,
    require_rank0_only: bool = False,
) -> tuple[bool, dict[str, Any], list[str], dict[str, np.ndarray]]:
    failures: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    report: dict[str, Any] = {}
    try:
        _require(
            metadata.get(metadata_schema_key) == expected_metadata_schema,
            f"{context} schema",
        )
        if require_rank0_only:
            _require(metadata.get("rank0_only") is True, f"{context} rank0_only")
        path, binding = _bind_file(
            metadata.get("path"),
            metadata.get("sha256"),
            anchors,
            context,
        )
        _require(
            metadata.get("bytes") == binding["bytes"],
            f"{context} metadata bytes mismatch",
        )
        with np.load(path, allow_pickle=False) as payload:
            _require(set(payload.files) == set(ARRAY_SPEC), f"{context} keys mismatch")
            descriptors = _mapping(metadata.get("arrays"), f"{context}.arrays")
            if expected_metadata_schema == "task037b.m10-own-grid-EH-modal-q.v1":
                _require(
                    metadata.get("keys") == list(ARRAY_SPEC),
                    f"{context}.keys mismatch",
                )
                _require(
                    set(descriptors) == set(ARRAY_SPEC),
                    f"{context}.arrays keys mismatch",
                )
            else:
                _require(
                    set(descriptors) == set(descriptor_names),
                    f"{context}.arrays keys mismatch",
                )
            for name, (shape, dtype_name) in ARRAY_SPEC.items():
                array = np.asarray(payload[name])
                expected_dtype = np.dtype(dtype_name)
                _require(array.shape == shape, f"{context}.{name} shape")
                _require(array.dtype == expected_dtype, f"{context}.{name} dtype")
                _require(bool(np.all(np.isfinite(array))), f"{context}.{name} finite")
                digest = _array_digest(array)
                if name in descriptor_names:
                    descriptor = _mapping(
                        descriptors.get(name), f"{context}.{name}.descriptor"
                    )
                    _require(
                        descriptor.get("shape") == list(shape),
                        f"{context}.{name} descriptor shape",
                    )
                    _require(
                        descriptor.get("dtype") == dtype_name,
                        f"{context}.{name} descriptor dtype",
                    )
                    _require(
                        descriptor.get("sha256") == digest,
                        f"{context}.{name} descriptor hash",
                    )
                    _require(
                        descriptor.get("bytes") == int(array.nbytes),
                        f"{context}.{name} descriptor bytes",
                    )
                arrays[name] = array.copy()
                report[name] = {
                    "shape": list(array.shape),
                    "dtype": str(array.dtype),
                    "sha256": digest,
                    "finite": True,
                }
        report["file"] = binding
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as error:
        failures.append(f"{context}:{error}")
    return not failures, report, failures, arrays


def _load_candidate_grid(
    metadata: Mapping[str, Any], anchors: Sequence[Path]
) -> tuple[bool, dict[str, Any], list[str], dict[str, np.ndarray]]:
    return _load_npz_payload(
        metadata,
        anchors,
        "candidate.own_grid",
        descriptor_names=tuple(ARRAY_SPEC),
        metadata_schema_key="schema_version",
        expected_metadata_schema="task037b.m10-own-grid-EH-modal-q.v1",
    )


def _load_h1_grid(
    metadata: Mapping[str, Any], anchors: Sequence[Path]
) -> tuple[bool, dict[str, Any], list[str], dict[str, np.ndarray]]:
    return _load_npz_payload(
        metadata,
        anchors,
        "h1_solver.h1_telemetry.own_grid",
        descriptor_names=(
            "E_V_per_m",
            "H_A_per_m",
            "modal_amplitudes",
            "bottom_q",
            "top_q",
        ),
        metadata_schema_key="schema",
        expected_metadata_schema="task037b.h1-authority-grid-EH-modal-q.v1",
        require_rank0_only=True,
    )


def _canonical_metadata(record: Mapping[str, Any]) -> Mapping[str, Any]:
    physics = _mapping(record.get("physics"), "physics")
    return _mapping(physics.get("canonical"), "physics.canonical")


def _canonical_role(
    item: Mapping[str, Any],
    side: str,
    role: str,
    anchors: Sequence[Path],
) -> tuple[bool, dict[str, Any], list[str], dict[tuple[Any, ...], complex]]:
    failures: list[str] = []
    values: dict[tuple[Any, ...], complex] = {}
    report: dict[str, Any] = {}
    try:
        manifest_path, manifest_binding = _bind_file(
            item.get("manifest"),
            item.get("manifest_sha256"),
            anchors,
            f"canonical.{side}.{role}.manifest",
        )
        manifest = read_canonical_manifest(manifest_path, manifest_binding["sha256"])
        _require(manifest.get("schema_version") == MANIFEST_SCHEMA, "canonical schema")
        _require(manifest.get("role") == f"{side}_{role}", "canonical role")
        _require(manifest.get("dtype") == "complex128", "canonical dtype")
        all_keys: list[tuple[Any, ...]] = []
        packet_count = 0
        shards = _sequence(manifest.get("per_rank_shards"), "canonical shards")
        shard_reports: list[dict[str, Any]] = []
        for index, shard in enumerate(shards):
            shard_map = _mapping(shard, f"canonical shard {index}")
            shard_path = manifest_path.parent / str(shard_map.get("filename"))
            packets = read_canonical_packet_shard(
                shard_path, shard_map.get("file_sha256")
            )
            keys = [key for key, _value in packets]
            values_finite = all(
                math.isfinite(complex(value).real)
                and math.isfinite(complex(value).imag)
                for _key, value in packets
            )
            _require(values_finite, f"canonical shard {index} nonfinite")
            _require(len(keys) == len(set(keys)), f"canonical shard {index} duplicate")
            _require(
                int(shard_map.get("packet_count")) == len(packets),
                f"canonical shard {index} count",
            )
            _require(
                int(shard_map.get("local_duplicate_count", 0)) == 0,
                f"canonical shard {index} local duplicate",
            )
            all_keys.extend(keys)
            packet_count += len(packets)
            for key, value in packets:
                _require(key not in values, f"canonical global duplicate {key}")
                values[key] = complex(value)
            shard_reports.append(
                {
                    "rank": shard_map.get("rank"),
                    "packet_count": len(packets),
                    "pass": True,
                }
            )
        _require(len(all_keys) == len(set(all_keys)), "canonical global key duplicate")
        _require(
            int(manifest.get("global_summed_packet_count")) == packet_count,
            "canonical global count",
        )
        _require(
            int(manifest.get("summed_local_duplicate_count", 0)) == 0,
            "canonical summed duplicate",
        )
        _require(item.get("pass") is True, "canonical role pass flag")
        report = {
            "manifest": manifest_binding,
            "packet_count": packet_count,
            "shards": shard_reports,
            "pass": True,
        }
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as error:
        failures.append(f"canonical.{side}.{role}:{error}")
    return not failures, report, failures, values


def _canonical_payload(
    record: Mapping[str, Any],
    anchors: Sequence[Path],
) -> tuple[bool, dict[str, Any], list[str], dict[str, dict[tuple[Any, ...], complex]]]:
    metadata = _canonical_metadata(record)
    reports: dict[str, Any] = {}
    failures: list[str] = []
    values: dict[str, dict[tuple[Any, ...], complex]] = {}
    for side in ("bottom", "top"):
        side_data = _mapping(metadata.get(side), f"canonical.{side}")
        roles = _mapping(side_data.get("roles"), f"canonical.{side}.roles")
        for role in ("active_trace", "full_fe"):
            role_pass, report, role_failures, role_values = _canonical_role(
                _mapping(roles.get(role), f"canonical.{side}.{role}"),
                side,
                role,
                anchors,
            )
            reports[f"{side}_{role}"] = report
            failures.extend(role_failures)
            values[f"{side}_{role}"] = role_values
            if not role_pass:
                failures.append(f"canonical.{side}.{role}.pass")
    return not failures, reports, failures, values


def _relative_l2(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.shape != right.shape:
        return None
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        return None
    return float(
        np.linalg.norm(
            np.asarray(left, dtype=np.complex128)
            - np.asarray(right, dtype=np.complex128)
        )
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-30)
    )


def _magnitude_l2(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.shape != right.shape:
        return None
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        return None
    return float(
        np.linalg.norm(np.abs(left) - np.abs(right))
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-30)
    )


def _payload_comparison(
    candidate_arrays: Mapping[str, np.ndarray],
    authority_arrays: Mapping[str, np.ndarray],
) -> tuple[bool, dict[str, Any], list[str]]:
    failures: list[str] = []
    report: dict[str, Any] = {}
    for name in ("x_nm", "y_nm", "z_nm"):
        if name not in authority_arrays or not np.array_equal(
            candidate_arrays.get(name), authority_arrays[name]
        ):
            failures.append(f"coordinates.{name}")
            report[name] = {"pass": False}
        else:
            report[name] = {"pass": True}
    for name in ("bottom_q", "top_q"):
        if name not in authority_arrays:
            failures.append(f"q.{name}.missing")
            report[name] = {"pass": False}
            continue
        error = _relative_l2(candidate_arrays[name], authority_arrays[name])
        report[name] = {
            "relative_l2": error,
            "pass": error is not None and error <= Q_TOLERANCE,
        }
        if not report[name]["pass"]:
            failures.append(f"q.{name}")
    for name in ("E_V_per_m", "H_A_per_m"):
        if name not in authority_arrays:
            report[name] = {"pass": False}
            failures.append(f"field.{name}.missing")
            continue
        if name == "E_V_per_m":
            selected_candidate = np.concatenate(
                (
                    candidate_arrays[name][0, :, :, :2].ravel(),
                    candidate_arrays[name][1:4].ravel(),
                    candidate_arrays[name][4, :, :, :2].ravel(),
                )
            )
            selected_authority = np.concatenate(
                (
                    authority_arrays[name][0, :, :, :2].ravel(),
                    authority_arrays[name][1:4].ravel(),
                    authority_arrays[name][4, :, :, :2].ravel(),
                )
            )
        else:
            selected_candidate = np.concatenate(
                (
                    candidate_arrays[name][0, :, :, :2].ravel(),
                    candidate_arrays[name][1:4].ravel(),
                    candidate_arrays[name][4, :, :, :2].ravel(),
                )
            )
            selected_authority = np.concatenate(
                (
                    authority_arrays[name][0, :, :, :2].ravel(),
                    authority_arrays[name][1:4].ravel(),
                    authority_arrays[name][4, :, :, :2].ravel(),
                )
            )
        error = _relative_l2(selected_candidate, selected_authority)
        magnitude = _magnitude_l2(selected_candidate, selected_authority)
        report[name] = {
            "relative_l2": error,
            "magnitude_relative_l2": magnitude,
            "pass": error is not None and error <= FIELD_TOLERANCE,
        }
        if not report[name]["pass"]:
            failures.append(f"field.{name}")
    if "modal_amplitudes" not in authority_arrays:
        failures.append("modal_amplitudes.missing")
    else:
        raw = _relative_l2(
            candidate_arrays["modal_amplitudes"], authority_arrays["modal_amplitudes"]
        )
        magnitude = _magnitude_l2(
            candidate_arrays["modal_amplitudes"], authority_arrays["modal_amplitudes"]
        )
        report["modal_amplitudes"] = {
            "raw_relative_l2": raw,
            "magnitude_relative_l2": magnitude,
            "raw_status": "diagnostic_not_comparable_independent_qep_gauge",
            "pass": magnitude is not None and magnitude <= Q_TOLERANCE,
        }
        if not report["modal_amplitudes"]["pass"]:
            failures.append("modal_amplitudes.magnitude")
    return not failures, report, failures


def _canonical_comparison(
    candidate: Mapping[str, Mapping[tuple[Any, ...], complex]],
    authority: Mapping[str, Mapping[tuple[Any, ...], complex]],
) -> tuple[bool, dict[str, Any], list[str]]:
    failures: list[str] = []
    report: dict[str, Any] = {}
    for role in (
        "bottom_active_trace",
        "bottom_full_fe",
        "top_active_trace",
        "top_full_fe",
    ):
        left = candidate.get(role, {})
        right = authority.get(role)
        if right is None:
            report[role] = {"pass": False, "status": "missing"}
            failures.append(f"canonical_compare.{role}.missing")
            continue
        if set(left) != set(right):
            report[role] = {"pass": False, "key_set_equal": False}
            failures.append(f"canonical_compare.{role}.keys")
            continue
        left_values = np.asarray(
            [left[key] for key in sorted(left)], dtype=np.complex128
        )
        right_values = np.asarray(
            [right[key] for key in sorted(right)], dtype=np.complex128
        )
        relative_l2 = float(
            np.linalg.norm(left_values - right_values)
            / max(np.linalg.norm(left_values), np.linalg.norm(right_values), 1.0e-30)
        )
        relative_errors = [
            abs(left[key] - right[key]) / max(abs(left[key]), abs(right[key]), 1.0e-30)
            for key in left
        ]
        maximum = max(relative_errors, default=0.0)
        passed = relative_l2 <= CANONICAL_TOLERANCE
        report[role] = {
            "key_set_equal": True,
            "relative_l2": relative_l2,
            "max_relative_error": maximum,
            "pass": passed,
        }
        if not passed:
            failures.append(f"canonical_compare.{role}.values")
    return not failures, report, failures


def _candidate_orders(
    record: Mapping[str, Any],
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    physics = _mapping(record.get("physics"), "candidate.physics")
    return _orders_map(
        physics.get("external_orders"), "candidate.physics.external_orders"
    )


def _h1_solver_payload(solver: Mapping[str, Any]) -> Mapping[str, Any]:
    telemetry = _mapping(solver.get("h1_telemetry"), "h1_solver.h1_telemetry")
    return telemetry


def _h1_grid_metadata(solver: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(
        _h1_solver_payload(solver).get("own_grid"),
        "h1_solver.h1_telemetry.own_grid",
    )


def _h1_canonical_metadata(solver: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(
        _h1_solver_payload(solver).get("canonical_export"),
        "h1_solver.h1_telemetry.canonical_export",
    )


def _h1_validation(solver: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(solver.get("validation"), "h1_solver.validation")


def _h1_volume_absorption(solver: Mapping[str, Any]) -> Mapping[str, Any]:
    reconstruction = _mapping(
        solver.get("physical_field_reconstruction"),
        "h1_solver.physical_field_reconstruction",
    )
    return _mapping(
        reconstruction.get("volume_absorption"),
        "h1_solver.physical_field_reconstruction.volume_absorption",
    )


def _significant_reference_order_map(
    reference: Mapping[str, Any],
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    channels = reference.get("channels")
    if not isinstance(channels, Mapping) or len(channels) != 12:
        raise EvidenceError("significant reference must contain 12 channels")
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for key, item in channels.items():
        channel = _mapping(item, "significant reference channel")
        identity = _mapping(
            channel.get("analytic_identity"),
            "significant reference analytic identity",
        )
        center = _mapping(
            channel.get("reference_center"),
            "significant reference reference center",
        )
        order_key = _order_key(identity, "significant reference analytic identity")
        _require(
            order_key == key and order_key not in result,
            "significant reference channel identity is duplicated",
        )
        amplitude = center.get("complex_amplitude")
        _complex_pair(amplitude, f"significant reference {order_key} amplitude")
        power = _finite(center.get("power"), f"significant reference {order_key} power")
        mapped = dict(identity)
        mapped["outgoing_amplitude_at_boundary"] = amplitude
        mapped["power_ratio"] = power
        result[order_key] = mapped
    _require(
        len(result) == 12,
        "significant reference channel identity is incomplete",
    )
    return result


def _h1_orders(
    solver: Mapping[str, Any],
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    return _orders_map(
        _h1_validation(solver).get("external_diffraction_orders"),
        "h1_solver.validation.external_diffraction_orders",
    )


def _h1_observables(solver: Mapping[str, Any]) -> dict[str, float]:
    validation = _h1_validation(solver)
    port_power = _mapping(
        validation.get("port_power"), "h1_solver.validation.port_power"
    )
    volume = _h1_volume_absorption(solver)
    values = {
        "R": _finite(port_power.get("R_total"), "h1 R_total"),
        "T": _finite(port_power.get("T_total"), "h1 T_total"),
        "A": _finite(port_power.get("A_balance"), "h1 A_balance"),
        "A_volume": _finite(volume.get("A_volume_total"), "h1 A_volume_total"),
        "closure": _finite(
            volume.get("energy_closure_error"),
            "h1 energy_closure_error",
        ),
    }
    return values


def _candidate_observables(record: Mapping[str, Any]) -> dict[str, float]:
    physics = _mapping(record.get("physics"), "candidate.physics")
    energy = _mapping(physics.get("energy"), "candidate.physics.energy")
    return {
        name: _finite(energy.get(name), f"candidate.physics.energy.{name}")
        for name in ("R", "T", "A", "A_volume", "closure")
    }


def _absorption_observables(
    source: Mapping[str, Any], context: str
) -> dict[str, float]:
    volume = _mapping(source, context)
    local_regions = volume.get("local_regions")
    middle = volume.get("middle_modal_region")
    result: dict[str, float] = {}
    if local_regions is not None:
        local = _mapping(local_regions, f"{context}.local_regions")
        bottom = _mapping(local.get("bottom"), f"{context}.local_regions.bottom")
        top = _mapping(local.get("top"), f"{context}.local_regions.top")
        result["local_bottom"] = _finite(
            bottom.get("total_absorbed_power_code_units"),
            f"{context}.local_regions.bottom.total_absorbed_power_code_units",
        )
        result["local_top"] = _finite(
            top.get("total_absorbed_power_code_units"),
            f"{context}.local_regions.top.total_absorbed_power_code_units",
        )
    if middle is not None:
        middle_map = _mapping(middle, f"{context}.middle_modal_region")
        result["middle"] = _finite(
            middle_map.get("absorbed_power_code_units"),
            f"{context}.middle_modal_region.absorbed_power_code_units",
        )
    return result


def _observable_delta(left: float, right: float) -> dict[str, Any]:
    absolute = abs(left - right)
    relative = absolute / max(abs(left), abs(right), 1.0e-30)
    return {
        "absolute_delta": absolute,
        "relative_delta": relative,
        "pass": absolute <= OBSERVABLE_TOLERANCE or relative <= OBSERVABLE_TOLERANCE,
    }


def _authority_bindings_gate(
    candidate: Mapping[str, Any],
    h1_summary: Mapping[str, Any],
    h1_solver: Mapping[str, Any],
    h1_summary_binding: Mapping[str, Any],
    full3d_binding: Mapping[str, Any],
    h1_solver_binding: Mapping[str, Any],
    expected_source_sha: str,
    online_anchors: Sequence[Path],
) -> tuple[bool, dict[str, Any], list[str]]:
    failures: list[str] = []
    result: dict[str, Any] = {
        "candidate_full3d_reference": False,
        "candidate_pinned_full3d_gate": False,
        "candidate_h1_reference": False,
        "h1_summary_solver_binding": False,
        "source": False,
    }
    candidate_bindings = _mapping(
        candidate.get("authority_bindings"), "candidate.authority_bindings"
    )
    candidate_h1 = _mapping(
        candidate_bindings.get("h1_direct_hybrid"), "candidate.h1_direct_hybrid"
    )
    candidate_full3d = _mapping(candidate_bindings.get("full3d"), "candidate.full3d")
    pinned_full3d = _mapping(
        candidate_bindings.get("pinned_full3d"),
        "candidate.authority_bindings.pinned_full3d",
    )
    if candidate_h1.get("sha256") != h1_summary_binding["sha256"]:
        failures.append("candidate.h1_direct_hybrid.sha256")
    elif _resolve_path(
        candidate_h1.get("path"), online_anchors, "candidate.h1_direct_hybrid.path"
    ) != Path(h1_summary_binding["resolved_path"]):
        failures.append("candidate.h1_direct_hybrid.path")
    else:
        result["candidate_h1_reference"] = True
    if candidate_full3d.get("sha256") != full3d_binding["sha256"]:
        failures.append("candidate.full3d_authority_sha")
    elif _resolve_path(
        candidate_full3d.get("path"), online_anchors, "candidate.full3d.path"
    ) != Path(full3d_binding["resolved_path"]):
        failures.append("candidate.full3d.path")
    else:
        result["candidate_full3d_reference"] = True
    pinned_checks = _mapping(
        pinned_full3d.get("checks"), "candidate.pinned_full3d.checks"
    )
    pinned_pass = bool(
        pinned_full3d.get("schema_version")
        == "task037b.h1-pinned-full3d-reference-gate.v1"
        and pinned_full3d.get("pass") is True
        and pinned_full3d.get("expected_sha256") == full3d_binding["sha256"]
        and pinned_full3d.get("observed_sha256") == full3d_binding["sha256"]
        and pinned_full3d.get("current_hybrid_source_sha") == expected_source_sha
        and pinned_full3d.get("failures") == []
        and pinned_checks
        and all(value is True for value in pinned_checks.values())
    )
    if not pinned_pass:
        failures.append("candidate.pinned_full3d")
    else:
        result["candidate_pinned_full3d_gate"] = True
    if h1_summary.get("solver_record_sha256") != h1_solver_binding["sha256"]:
        failures.append("h1.summary.solver_sha")
    ignored = h1_summary.get("solver_record_ignored_path")
    expected_solver_path = _resolve_path(
        ignored,
        (Path(h1_summary_binding["resolved_path"]).parent, ROOT),
        "h1 summary solver_record_ignored_path",
    )
    if expected_solver_path != Path(h1_solver_binding["resolved_path"]):
        failures.append("h1.summary.solver_path")
    else:
        result["h1_summary_solver_binding"] = True
    source = _mapping(candidate.get("source"), "candidate.source")
    before = _mapping(source.get("before"), "candidate.source.before")
    after = _mapping(source.get("after"), "candidate.source.after")
    source_pass = bool(
        before.get("commit_sha") == expected_source_sha
        and before.get("verified_clean_sha") == expected_source_sha
        and before.get("tracked_source_dirty") is False
        and before.get("stable_and_clean_before") is True
        and after.get("head") == expected_source_sha
        and after.get("verified_clean_sha") == expected_source_sha
        and after.get("matches_verified_clean_sha") is True
        and after.get("clean") is True
    )
    result["source"] = source_pass
    if not source_pass:
        failures.append("candidate.source")
    return not failures, result, failures


def _compare_significant(
    h1_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    candidate_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    significant: Mapping[str, Any],
    context: str,
) -> tuple[dict[str, Any], list[str]]:
    report: dict[str, Any] = {
        "pinned_full3d_payload": "hash_bound_significant_reference"
    }
    failures: list[str] = []
    hybrid = _compare_full_hybrid(h1_orders, candidate_orders)
    report["h1_vs_candidate"] = hybrid
    if hybrid.get("pass") is not True:
        failures.append(f"{context}.h1_vs_candidate")
    reference = _load_significant_reference(significant["path"], significant["sha256"])
    frozen_orders = _significant_reference_order_map(reference)
    direct = _compare_to_significant_reference(frozen_orders, h1_orders, reference)
    iterative = _compare_to_significant_reference(
        frozen_orders, candidate_orders, reference
    )
    report["direct_vs_significant_reference"] = direct
    report["iterative_vs_significant_reference"] = iterative
    if direct.get("pass") is not True:
        failures.append(f"{context}.direct_significant")
    if iterative.get("pass") is not True:
        failures.append(f"{context}.iterative_significant")
    return report, failures


def _candidate_gate(
    record: Mapping[str, Any],
    anchors: Sequence[Path],
) -> tuple[
    bool,
    dict[str, Any],
    list[str],
    dict[str, np.ndarray],
    dict[str, dict[tuple[Any, ...], complex]],
    dict[tuple[str, int, int, str], Mapping[str, Any]],
]:
    failures: list[str] = []
    gate: dict[str, Any] = {}
    profile_pass, profile_failures = _profile_gate(record)
    gate["profile"] = profile_pass
    failures.extend(profile_failures)
    bool_pass, bool_failures = _bool_fields_gate(record)
    gate["online_schema_and_qualification"] = bool_pass
    failures.extend(bool_failures)
    linear_pass, linear_report, linear_failures = _linear_gate(record)
    gate["linear"] = linear_pass
    failures.extend(linear_failures)
    physics = _mapping(record.get("physics"), "physics")
    traction_pass, traction_report, traction_failures = _traction_gate(physics)
    gate["traction"] = traction_pass
    failures.extend(traction_failures)
    try:
        orders = _candidate_orders(record)
        gate["orders"] = True
    except EvidenceError as error:
        orders = {}
        gate["orders"] = False
        failures.append(f"orders:{error}")
    try:
        energy_pass, energy_report, energy_failures = _energy_gate(physics)
    except EvidenceError as error:
        energy_pass, energy_report, energy_failures = False, {}, [str(error)]
    gate["energy"] = energy_pass
    failures.extend(energy_failures)
    lifecycle_pass, lifecycle_failures = _lifecycle_gate(record)
    gate["lifecycle"] = lifecycle_pass
    failures.extend(lifecycle_failures)
    recovery = _mapping(record.get("recovery"), "recovery")
    gate["recovery"] = recovery.get("recovery_pass") is True
    if not gate["recovery"]:
        failures.append("recovery.recovery_pass")
    final_release_pass, final_release_report, final_release_failures = (
        _final_release_gate(record)
    )
    gate["final_release"] = final_release_pass
    failures.extend(final_release_failures)
    try:
        grid_pass, grid_report, grid_failures, arrays = _load_candidate_grid(
            _candidate_grid_metadata(record), anchors
        )
    except (EvidenceError, TypeError) as error:
        grid_pass, grid_report, grid_failures, arrays = False, {}, [str(error)], {}
    gate["own_grid"] = grid_pass
    failures.extend(grid_failures)
    try:
        canonical_pass, canonical_report, canonical_failures, canonical_values = (
            _canonical_payload(record, anchors)
        )
    except (EvidenceError, TypeError) as error:
        canonical_pass, canonical_report, canonical_failures, canonical_values = (
            False,
            {},
            [str(error)],
            {},
        )
    gate["canonical"] = canonical_pass
    failures.extend(canonical_failures)
    order_audit = _mapping(physics.get("order_audit"), "physics.order_audit")
    gate["order_audit"] = bool(
        len(orders) == 80
        and order_audit.get("count") == 80
        and order_audit.get("unique_key_count") == 80
        and order_audit.get("keys_unique") is True
        and order_audit.get("identity_valid") is True
        and order_audit.get("all_finite") is True
        and order_audit.get("pass") is True
    )
    if not gate["order_audit"]:
        failures.append("physics.order_audit")
    gate["canonical_pass"] = physics.get("canonical_pass") is True
    if not gate["canonical_pass"]:
        failures.append("physics.canonical_pass")
    gate["own_physics_pass"] = physics.get("own_physics_pass") is True
    if not gate["own_physics_pass"]:
        failures.append("physics.own_physics_pass")
    gate["physics_pass"] = physics.get("physics_pass") is True
    if not gate["physics_pass"]:
        failures.append("physics.physics_pass")
    report = {
        "profile": record.get("profile"),
        "linear": linear_report,
        "traction": traction_report,
        "energy": energy_report,
        "own_grid": grid_report,
        "canonical": canonical_report,
        "final_release": final_release_report,
        "gate": gate,
    }
    return not failures, report, failures, arrays, canonical_values, orders


def check_evidence(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output).resolve()
    if output.exists():
        raise OutputExistsError(f"checker output already exists: {output}")
    if (
        not isinstance(args.expected_source_sha, str)
        or len(args.expected_source_sha) != 40
        or any(
            character not in "0123456789abcdef"
            for character in args.expected_source_sha
        )
    ):
        raise EvidenceError("expected source SHA is not a 40-character hex digest")
    started = time.perf_counter()
    watchdog_path, watchdog_summary, watchdog_binding = _load_json_binding(
        args.watchdog_summary,
        args.watchdog_summary_sha256,
        "watchdog_summary",
        (Path(args.watchdog_summary).resolve().parent, ROOT),
    )
    watchdog_pass, watchdog_gate, watchdog_failures, online_path, online_record = (
        _check_watchdog(
            watchdog_path,
            watchdog_summary,
            args.expected_source_sha,
            (watchdog_path.parent, ROOT),
        )
    )
    if online_path is None or online_record is None:
        raise EvidenceError("watchdog did not bind a valid online record")
    h1_summary_path, h1_summary, h1_summary_binding = _load_json_binding(
        args.h1_summary,
        args.h1_summary_sha256,
        "h1_summary",
        (Path(args.h1_summary).resolve().parent, ROOT),
    )
    h1_solver_path, h1_solver, h1_solver_binding = _load_json_binding(
        args.h1_solver_record,
        args.h1_solver_record_sha256,
        "h1_solver_record",
        (Path(args.h1_solver_record).resolve().parent, ROOT),
    )
    _full3d_path, _full3d, full3d_binding = _load_json_binding(
        args.full3d_reference,
        args.full3d_reference_sha256,
        "full3d_reference",
        (Path(args.full3d_reference).resolve().parent, ROOT),
    )
    significant_path, _significant, significant_binding = _load_json_binding(
        args.significant_reference,
        args.significant_reference_sha256,
        "significant_reference",
        (Path(args.significant_reference).resolve().parent, ROOT),
    )
    authority_pass, authority_report, authority_failures = _authority_bindings_gate(
        online_record,
        h1_summary,
        h1_solver,
        h1_summary_binding,
        full3d_binding,
        h1_solver_binding,
        args.expected_source_sha,
        (online_path.parent, watchdog_path.parent, ROOT),
    )
    (
        candidate_pass,
        candidate_report,
        candidate_failures,
        candidate_arrays,
        candidate_canonical,
        candidate_orders,
    ) = _candidate_gate(
        online_record,
        (online_path.parent, watchdog_path.parent, ROOT),
    )
    payload_report: dict[str, Any] = {"candidate": candidate_report}
    comparison_failures: list[str] = []
    h1_grid_anchors = (
        Path(h1_solver_binding["resolved_path"]).parent,
        h1_solver_path.parent,
        h1_summary_path.parent,
        ROOT,
    )
    h1_grid_pass, h1_grid_report, h1_grid_failures, h1_arrays = _load_h1_grid(
        _h1_grid_metadata(h1_solver),
        h1_grid_anchors,
    )
    payload_report["h1"] = h1_grid_report
    comparison_failures.extend(h1_grid_failures)
    payload_comparison_pass, payload_comparison, payload_failures = _payload_comparison(
        candidate_arrays,
        h1_arrays,
    )
    comparison_failures.extend(payload_failures)
    payload_report["candidate_vs_h1"] = payload_comparison
    h1_canonical_values: dict[str, dict[tuple[Any, ...], complex]] = {}
    h1_can_pass, h1_can_report, h1_can_failures, h1_canonical_values = (
        _canonical_payload(
            {"physics": {"canonical": _h1_canonical_metadata(h1_solver)}},
            h1_grid_anchors,
        )
    )
    payload_report["h1_canonical"] = h1_can_report
    comparison_failures.extend(h1_can_failures)
    canonical_pass, canonical_report, canonical_failures = _canonical_comparison(
        candidate_canonical,
        h1_canonical_values,
    )
    comparison_failures.extend(canonical_failures)
    comparisons: dict[str, Any] = {
        "candidate_vs_h1_payload": payload_comparison,
        "candidate_vs_h1_canonical": canonical_report,
    }
    candidate_observables = _candidate_observables(online_record)
    h1_observables = _h1_observables(h1_solver)
    observable_report: dict[str, Any] = {}
    observable_failures: list[str] = []
    for name in ("R", "T", "A", "A_volume", "closure"):
        delta = _observable_delta(candidate_observables[name], h1_observables[name])
        observable_report[name] = delta
        if not delta["pass"]:
            observable_failures.append(f"observables.{name}")
    candidate_absorption = _absorption_observables(
        _mapping(
            _mapping(online_record.get("physics"), "candidate.physics").get(
                "absorption"
            ),
            "candidate.physics.absorption",
        ),
        "candidate.physics.absorption",
    )
    h1_absorption = _absorption_observables(
        _h1_volume_absorption(h1_solver),
        "h1_solver.physical_field_reconstruction.volume_absorption",
    )
    if bool(candidate_absorption) != bool(h1_absorption) or set(
        candidate_absorption
    ) != set(h1_absorption):
        observable_failures.append("observables.optional_absorption_presence")
    else:
        for name in candidate_absorption:
            delta = _observable_delta(candidate_absorption[name], h1_absorption[name])
            observable_report[name] = delta
            if not delta["pass"]:
                observable_failures.append(f"observables.{name}")
    comparisons["observables"] = observable_report
    comparison_failures.extend(observable_failures)
    h1_orders = _h1_orders(h1_solver)
    significant_meta = {
        "path": significant_path,
        "sha256": significant_binding["sha256"],
    }
    significant_report, significant_failures = _compare_significant(
        h1_orders,
        candidate_orders,
        significant_meta,
        "candidate",
    )
    comparisons["significant_full3d"] = significant_report
    comparison_failures.extend(significant_failures)
    comparisons["modal_raw_gauge"] = {
        "status": "diagnostic_not_comparable_independent_qep_gauge",
        "magnitude_qualification": "checked through own-grid payload comparison",
    }
    payload_comparison_pass = bool(payload_comparison_pass and h1_grid_pass)
    canonical_comparison_pass = bool(canonical_pass and h1_can_pass)
    observables_pass = not observable_failures
    integrity_pass = bool(
        watchdog_pass
        and candidate_pass
        and payload_comparison_pass
        and canonical_comparison_pass
        and observables_pass
        and not candidate_failures
    )
    authority_bindings_pass = bool(authority_pass and not authority_failures)
    all_failures = list(watchdog_failures)
    all_failures.extend(candidate_failures)
    all_failures.extend(authority_failures)
    all_failures.extend(comparison_failures)
    passed = bool(integrity_pass and authority_bindings_pass and not all_failures)
    elapsed = time.perf_counter() - started
    offline_resource = {
        "wall_seconds": elapsed,
        "ru_maxrss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        "online_rss_included": False,
        "authority": "checker_process_only",
    }
    return {
        "schema": CHECKER_SCHEMA,
        "bindings": {
            "watchdog_summary": watchdog_binding,
            "h1_summary": h1_summary_binding,
            "h1_solver_record": h1_solver_binding,
            "full3d_reference": full3d_binding,
            "significant_reference": significant_binding,
            "expected_source_sha": args.expected_source_sha,
        },
        "candidate_gate": candidate_report,
        "payload": payload_report,
        "comparisons": comparisons,
        "candidate_vs_h1_payload_pass": payload_comparison_pass,
        "candidate_vs_h1_canonical_pass": canonical_comparison_pass,
        "h1_grid_pass": h1_grid_pass,
        "h1_canonical_pass": h1_can_pass,
        "payload_comparison_pass": payload_comparison_pass,
        "canonical_comparison_pass": canonical_comparison_pass,
        "observables_pass": observables_pass,
        "offline_resource": offline_resource,
        "candidate_evidence_pass": integrity_pass,
        "evidence_integrity_pass": integrity_pass,
        "authority_bindings_pass": authority_bindings_pass,
        "pass": passed,
        "failures": sorted(set(all_failures)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchdog-summary", required=True, type=Path)
    parser.add_argument("--watchdog-summary-sha256", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--h1-summary", required=True, type=Path)
    parser.add_argument("--h1-summary-sha256", required=True)
    parser.add_argument("--h1-solver-record", required=True, type=Path)
    parser.add_argument("--h1-solver-record-sha256", required=True)
    parser.add_argument("--full3d-reference", required=True, type=Path)
    parser.add_argument("--full3d-reference-sha256", required=True)
    parser.add_argument("--significant-reference", required=True, type=Path)
    parser.add_argument("--significant-reference-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        print(f"checker output already exists: {output}", file=sys.stderr)
        return 2
    try:
        result = check_evidence(args)
    except OutputExistsError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (EvidenceError, OSError, ValueError, TypeError, KeyError) as error:
        result = {
            "schema": CHECKER_SCHEMA,
            "candidate_evidence_pass": False,
            "evidence_integrity_pass": False,
            "authority_bindings_pass": False,
            "pass": False,
            "failures": [f"checker:{error}"],
            "offline_resource": {
                "online_rss_included": False,
                "authority": "checker_process_only",
            },
        }
    _write_json(output, result)
    return 0 if result.get("pass") is True and result.get("failures") == [] else 1


if __name__ == "__main__":
    raise SystemExit(main())
