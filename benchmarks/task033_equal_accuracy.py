"""Fail-closed global equal-accuracy efficiency comparison for Task033.

The inputs are *qualified* Case091 Hybrid mode funnels.  A funnel is only an
index: the selected-M external-watchdog record is reopened and its SHA256,
source identity, physical evidence, and measured resource values are checked
again here.  Projected resource-matrix values are never accepted as measured
costs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = ROOT / "benchmarks" / "cases" / "091_hybrid_hp_adaptivity_feasibility"
FUNNEL_SCHEMA_PATH = CASE_ROOT / "hybrid_funnel_schema.json"
WATCHDOG_SCHEMA_PATH = ROOT / "benchmarks" / "task033_qep_qualification_schema.json"
OUTPUT_SCHEMA_PATH = CASE_ROOT / "equal_accuracy_schema.json"

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RTA_ABSOLUTE_MAX = 1.0e-5
SIGNIFICANT_ORDER_POWER = 1.0e-8
ORDER_COMPLEX_AMPLITUDE_RELATIVE_MAX = 1.0e-3
INTERFACE_E_RELATIVE_MAX = 5.0e-3
INTERFACE_H_RELATIVE_MAX = 1.0e-2
SELECTED_PLANE_FIELD_RELATIVE_MAX = 5.0e-3
QEP_BETA_RELATIVE_MAX = 1.0e-3
TRUE_RESIDUAL_MAX = 1.0e-9


class EqualAccuracyError(ValueError):
    """Raised when evidence cannot support a fail-closed comparison."""


@dataclass(frozen=True)
class _JsonFile:
    path: Path
    payload: dict[str, Any]
    sha256: str


@dataclass(frozen=True)
class _Evidence:
    funnel: _JsonFile
    watchdog: _JsonFile
    funnel_descriptor_path: str
    watchdog_descriptor_path: str
    source_sha: str
    selected_m: int
    case: Mapping[str, Any]
    measurements: Mapping[str, Any]
    costs: dict[str, int | float]

    def input_descriptor(self) -> dict[str, Any]:
        return {
            "funnel_path": self.funnel_descriptor_path,
            "funnel_sha256": self.funnel.sha256,
            "selected_mode_count_per_direction": self.selected_m,
            "selected_watchdog_path": self.watchdog_descriptor_path,
            "selected_watchdog_sha256": self.watchdog.sha256,
            "source_commit_full_sha": self.source_sha,
        }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(path: Path | str, *, root: Path) -> tuple[Path, str]:
    requested = Path(path)
    resolved_root = root.resolve()
    resolved = (
        requested.resolve()
        if requested.is_absolute()
        else (resolved_root / requested).resolve()
    )
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise EqualAccuracyError(
            f"equal-accuracy evidence path escapes repository root: {path}"
        ) from exc
    return resolved, relative.as_posix()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("payload_sha256", None)
    rendered = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _read_json(path: Path | str) -> _JsonFile:
    resolved = Path(path).resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EqualAccuracyError(f"cannot read JSON evidence {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EqualAccuracyError(f"JSON evidence {resolved} must contain an object")
    return _JsonFile(resolved, payload, _file_sha256(resolved))


def _schema(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EqualAccuracyError(f"cannot read schema {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise EqualAccuracyError(f"schema {path} is not a JSON object")
    return payload


def _validate_schema(payload: Mapping[str, Any], path: Path, *, label: str) -> None:
    errors = sorted(
        Draft202012Validator(_schema(path)).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        pointer = "/" + "/".join(map(str, first.absolute_path))
        raise EqualAccuracyError(f"{label} failed schema at {pointer}: {first.message}")


def _finite(value: object, *, label: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EqualAccuracyError(f"{label} must be a finite measured number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise EqualAccuracyError(f"{label} must be finite{' and positive' if positive else ''}")
    return result


def _positive_int(value: object, *, label: str) -> int:
    number = _finite(value, label=label, positive=True)
    rounded = round(number)
    if not math.isclose(number, rounded, rel_tol=0.0, abs_tol=1.0e-9):
        raise EqualAccuracyError(f"{label} must be an integer count")
    return int(rounded)


def _complex_value(value: object, *, label: str) -> complex:
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 2
    ):
        return complex(
            _finite(value[0], label=f"{label}.real"),
            _finite(value[1], label=f"{label}.imag"),
        )
    raise EqualAccuracyError(f"{label} must be a [real, imaginary] pair")


def classify_compression(ratio: float) -> str:
    """Classify same-accuracy local-DoF compression at exact Task033 bounds."""

    value = _finite(ratio, label="compression ratio", positive=True)
    if value < 1.3:
        return "weak"
    if value < 2.0:
        return "positive"
    if value < 3.0:
        return "clear"
    if value < 5.0:
        return "engineering"
    return "strong"


def _resolve_source_path(raw: object, *, funnel_path: Path) -> Path:
    if not isinstance(raw, str) or not raw:
        raise EqualAccuracyError(f"funnel {funnel_path} has an invalid source-record path")
    requested = Path(raw)
    candidates: list[Path] = []
    if requested.is_absolute():
        candidates.append(requested)
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/work/"):
        candidates.append(ROOT / normalized.removeprefix("/work/"))
    if not requested.is_absolute():
        candidates.extend((funnel_path.parent / requested, ROOT / requested))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise EqualAccuracyError(
        f"funnel {funnel_path} selected watchdog source cannot be read: {raw!r}"
    )


def _clean_source_sha(payload: Mapping[str, Any], *, label: str) -> str:
    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise EqualAccuracyError(f"{label} lacks source evidence")
    sha_values = {
        key: source.get(key)
        for key in (
            "commit_sha",
            "head_before_sha",
            "head_after_sha",
            "verified_clean_sha",
        )
    }
    if not all(
        isinstance(value, str) and FULL_SHA_RE.fullmatch(value.lower())
        for value in sha_values.values()
    ):
        raise EqualAccuracyError(f"{label} lacks complete full-SHA source evidence")
    normalized = {str(value).lower() for value in sha_values.values()}
    if len(normalized) != 1:
        raise EqualAccuracyError(f"{label} source SHA changed or differs from attestation")
    empty_status_keys = (
        "tracked_status_before",
        "tracked_status_after",
        "worktree_status_before",
        "worktree_status_after",
    )
    if any(source.get(key) != "" for key in empty_status_keys):
        raise EqualAccuracyError(
            f"{label} source is dirty (tracked or nonignored untracked worktree state)"
        )
    for key in ("nonignored_untracked_before", "nonignored_untracked_after"):
        if source.get(key) != []:
            raise EqualAccuracyError(f"{label} has nonignored untracked source files")
    if (
        source.get("source_stable_during_run") is not True
        or source.get("source_clean_verified") is not True
    ):
        raise EqualAccuracyError(f"{label} lacks stable complete-clean source attestation")
    semantics = source.get("cleanliness_semantics")
    if not isinstance(semantics, str) or "nonignored" not in semantics:
        raise EqualAccuracyError(f"{label} does not attest nonignored-untracked semantics")
    return normalized.pop()


def _selected_watchdog(funnel: _JsonFile) -> tuple[_JsonFile, int]:
    payload = funnel.payload
    qualification = payload.get("qualification")
    if not isinstance(qualification, Mapping):
        raise EqualAccuracyError(f"funnel {funnel.path} lacks qualification")
    selected_m = qualification.get("selected_mode_count_per_direction")
    if type(selected_m) is not int or selected_m <= 0:
        raise EqualAccuracyError(f"funnel {funnel.path} lacks a selected M")
    descriptors = payload.get("source_records")
    if not isinstance(descriptors, list):
        raise EqualAccuracyError(f"funnel {funnel.path} lacks source_records")
    selected = [
        row
        for row in descriptors
        if isinstance(row, Mapping) and row.get("mode_count_per_direction") == selected_m
    ]
    if len(selected) != 1:
        raise EqualAccuracyError(
            f"funnel {funnel.path} must bind selected M={selected_m} to one watchdog"
        )
    descriptor = selected[0]
    watchdog = _read_json(
        _resolve_source_path(descriptor.get("path"), funnel_path=funnel.path)
    )
    expected_hash = descriptor.get("sha256")
    if (
        not isinstance(expected_hash, str)
        or SHA256_RE.fullmatch(expected_hash.lower()) is None
        or expected_hash.lower() != watchdog.sha256
    ):
        raise EqualAccuracyError(f"selected watchdog SHA256 mismatch for {funnel.path}")
    return watchdog, selected_m


def _watchdog_measurements(
    watchdog: _JsonFile, *, funnel_sha: str
) -> tuple[Mapping[str, Any], str]:
    payload = watchdog.payload
    _validate_schema(
        payload, WATCHDOG_SCHEMA_PATH, label=f"watchdog {watchdog.path}"
    )
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    launch_gate = payload.get("launch_gate")
    launch_gate = launch_gate if isinstance(launch_gate, Mapping) else {}
    checks = {
        "schema_version": payload.get("schema_version") == "task033.memory-watchdog.v2",
        "benchmark_id": payload.get("benchmark_id") == "task033_external_memory_watchdog",
        "hybrid_target": payload.get("target") == "hybrid",
        "measured_status": payload.get("status") == "measured_shard_pass",
        "formal_pass": payload.get("formal_pass") is True,
        "memory_authority_pass": payload.get("memory_authority_pass") is True,
        "return_code_zero": payload.get("return_code") == 0,
        "no_swap": payload.get("no_swap") is True,
        "not_memory_terminated": payload.get("terminated_for_memory") is False,
        "not_timeout_terminated": payload.get("terminated_for_timeout") is False,
        "not_authority_terminated": (
            payload.get("terminated_for_authority_unreadable", False) is False
        ),
        "resource_authority_gate": resource_gate.get("pass") is True,
        "external_launch_gate": launch_gate.get("pass") is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise EqualAccuracyError(
            f"watchdog {watchdog.path} failed external-watchdog gates: {failed}"
        )
    source_sha = _clean_source_sha(payload, label=f"watchdog {watchdog.path}")
    if source_sha != funnel_sha:
        raise EqualAccuracyError(
            f"watchdog {watchdog.path} source SHA differs from its funnel"
        )
    measurements = payload.get("measurements")
    if not isinstance(measurements, Mapping):
        raise EqualAccuracyError(f"watchdog {watchdog.path} lacks measurements")
    qualification = measurements.get("qualification")
    gates = measurements.get("gates")
    solve = measurements.get("solve")
    if not isinstance(qualification, Mapping) or not all(
        qualification.get(key) is True
        for key in (
            "integration_pass",
            "algebraic_chain_pass",
            "physical_field_gates_pass",
            "task033_physical_truncation_allowed",
        )
    ):
        raise EqualAccuracyError(f"watchdog {watchdog.path} failed physical qualification")
    if (
        not isinstance(gates, Mapping)
        or not gates
        or any(type(value) is not bool or not value for value in gates.values())
    ):
        raise EqualAccuracyError(f"watchdog {watchdog.path} has failed/incomplete gates")
    if not isinstance(solve, Mapping) or _finite(
        solve.get("true_relative_residual"), label="true relative residual"
    ) > TRUE_RESIDUAL_MAX:
        raise EqualAccuracyError(f"watchdog {watchdog.path} failed true-residual gate")
    return measurements, source_sha


def _costs(payload: Mapping[str, Any], measurements: Mapping[str, Any]) -> dict[str, int | float]:
    hybrid = measurements.get("hybrid_system")
    timing = measurements.get("timing_seconds_max_rank")
    resource = payload.get("resource_authority")
    if not isinstance(hybrid, Mapping) or not isinstance(timing, Mapping) or not isinstance(
        resource, Mapping
    ):
        raise EqualAccuracyError("selected watchdog lacks measured hybrid/timing/resource costs")
    local_dofs = _positive_int(
        hybrid.get("bottom_local_fe_dofs"), label="bottom_local_fe_dofs"
    ) + _positive_int(hybrid.get("top_local_fe_dofs"), label="top_local_fe_dofs")
    explicit_rows = hybrid.get("total_rows")
    if explicit_rows is not None:
        total_rows = _positive_int(explicit_rows, label="total_rows")
    elif all(
        hybrid.get(key) is not None
        for key in ("bottom_global_size", "top_global_size", "internal_unknown_count")
    ):
        total_rows = sum(
            _positive_int(hybrid.get(key), label=key)
            for key in ("bottom_global_size", "top_global_size", "internal_unknown_count")
        )
    else:
        matrix_stats = hybrid.get("matrix_stats")
        if not isinstance(matrix_stats, Mapping):
            raise EqualAccuracyError("selected watchdog lacks measured total rows")
        total_rows = _positive_int(matrix_stats.get("matrix_rows"), label="matrix_rows")
    assembled_value = hybrid.get("assembled_nnz")
    if assembled_value is None:
        matrix_stats = hybrid.get("matrix_stats")
        if isinstance(matrix_stats, Mapping):
            assembled_value = matrix_stats.get("matrix_nnz_used")
    if assembled_value is None:
        parts = [hybrid.get("bottom_matrix_stats"), hybrid.get("top_matrix_stats")]
        if all(isinstance(part, Mapping) for part in parts):
            assembled_value = sum(
                _positive_int(part.get("matrix_nnz_used"), label="local matrix NNZ")
                for part in parts
                if isinstance(part, Mapping)
            )
    assembled_nnz = _positive_int(assembled_value, label="assembled_nnz")
    rss_bytes = _positive_int(
        resource.get("memory_authority_bytes"), label="memory_authority_bytes"
    )
    total_seconds = _finite(
        timing.get("total"), label="timing_seconds_max_rank.total", positive=True
    )
    return {
        "local_dofs": local_dofs,
        "total_rows": total_rows,
        "assembled_nnz": assembled_nnz,
        "authoritative_rss_bytes": rss_bytes,
        "authoritative_rss_gib": rss_bytes / float(1024**3),
        "total_time_seconds": total_seconds,
    }


def _load_evidence(path: Path | str, *, repo_root: Path) -> _Evidence:
    funnel_path, funnel_descriptor = _repo_path(path, root=repo_root)
    funnel = _read_json(funnel_path)
    _validate_schema(funnel.payload, FUNNEL_SCHEMA_PATH, label=f"funnel {funnel.path}")
    payload = funnel.payload
    identity = payload.get("identity")
    qualification = payload.get("qualification")
    case = payload.get("case")
    if (
        payload.get("status") != "qualified"
        or not isinstance(identity, Mapping)
        or identity.get("tracked_source_clean") is not True
        or not isinstance(qualification, Mapping)
        or qualification.get("mode_count_converged") is not True
        or qualification.get("all_sources_same_clean_sha") is not True
        or qualification.get("all_external_watchdogs_pass") is not True
        or not isinstance(case, Mapping)
    ):
        raise EqualAccuracyError(f"funnel {funnel.path} is not canonical qualified evidence")
    funnel_sha = identity.get("source_commit_full_sha")
    if not isinstance(funnel_sha, str) or FULL_SHA_RE.fullmatch(funnel_sha.lower()) is None:
        raise EqualAccuracyError(f"funnel {funnel.path} lacks a full clean source SHA")
    funnel_sha = funnel_sha.lower()
    watchdog, selected_m = _selected_watchdog(funnel)
    _, watchdog_descriptor = _repo_path(watchdog.path, root=repo_root)
    measurements, watchdog_sha = _watchdog_measurements(
        watchdog, funnel_sha=funnel_sha
    )
    measured_case = measurements.get("case")
    if not isinstance(measured_case, Mapping):
        raise EqualAccuracyError(f"watchdog {watchdog.path} lacks case identity")
    case_keys = (
        "degree",
        "h_nm",
        "wavelength_nm",
        "incident_grazing_deg",
        "polarization_kind",
        "bottom_interface_nm",
        "top_interface_nm",
        "graded_reference_h_nm",
        "graded_plan_hash",
    )
    mismatched = [key for key in case_keys if measured_case.get(key) != case.get(key)]
    if measured_case.get("requested_modes_per_direction") != selected_m:
        mismatched.append("requested_modes_per_direction")
    if mismatched:
        raise EqualAccuracyError(
            f"selected watchdog {watchdog.path} differs from funnel case: {mismatched}"
        )
    return _Evidence(
        funnel=funnel,
        watchdog=watchdog,
        funnel_descriptor_path=funnel_descriptor,
        watchdog_descriptor_path=watchdog_descriptor,
        source_sha=watchdog_sha,
        selected_m=selected_m,
        case=case,
        measurements=measurements,
        costs=_costs(watchdog.payload, measurements),
    )


def _port_power(measurements: Mapping[str, Any]) -> dict[str, float]:
    power = measurements.get("port_power")
    validation = measurements.get("validation")
    if not isinstance(power, Mapping) and isinstance(validation, Mapping):
        power = validation.get("port_power")
    if not isinstance(power, Mapping):
        raise EqualAccuracyError("missing R/T/A evidence")
    absorption = power.get("A_balance", power.get("A_total"))
    return {
        "R_total": _finite(power.get("R_total"), label="R_total"),
        "T_total": _finite(power.get("T_total"), label="T_total"),
        "A_balance": _finite(absorption, label="A_balance"),
    }


def _diffraction_orders(
    measurements: Mapping[str, Any],
) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    rows = measurements.get("external_diffraction_orders")
    validation = measurements.get("validation")
    if not isinstance(rows, list) and isinstance(validation, Mapping):
        rows = validation.get("external_diffraction_orders")
    if not isinstance(rows, list) or not rows:
        raise EqualAccuracyError("missing diffraction-order evidence")
    result: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EqualAccuracyError(f"diffraction order {index} is not an object")
        try:
            key = (
                str(row["side"]),
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EqualAccuracyError(f"diffraction order {index} has invalid identity") from exc
        if key in result:
            raise EqualAccuracyError(f"duplicate diffraction order {key}")
        result[key] = {
            "propagating": row.get("propagating") is True,
            "power_ratio": _finite(row.get("power_ratio"), label=f"order {key} power"),
            "amplitude": _complex_value(
                row.get("outgoing_amplitude_at_boundary"),
                label=f"order {key} amplitude",
            ),
        }
    return result


def _field_evidence(measurements: Mapping[str, Any]) -> dict[str, Any]:
    physical = measurements.get("physical_field_reconstruction")
    if not isinstance(physical, Mapping):
        raise EqualAccuracyError("missing physical field reconstruction")
    continuity = physical.get("interface_continuity")
    if not isinstance(continuity, Mapping):
        raise EqualAccuracyError("missing interface E/H evidence")
    interface_rows: dict[str, dict[str, float]] = {}
    for side in ("bottom", "top"):
        row = continuity.get(side)
        if not isinstance(row, Mapping):
            raise EqualAccuracyError(f"missing {side} interface E/H evidence")
        electric = row.get("electric_tangential")
        magnetic = row.get("magnetic_tangential")
        if not isinstance(electric, Mapping) or not isinstance(magnetic, Mapping):
            raise EqualAccuracyError(f"incomplete {side} interface E/H evidence")
        interface_rows[side] = {
            "electric_relative_l2": _finite(
                electric.get("relative_l2"), label=f"{side} interface E"
            ),
            "magnetic_relative_l2": _finite(
                magnetic.get("relative_l2"), label=f"{side} interface H"
            ),
        }
    selected = physical.get("selected_plane_full3d_comparison")
    if not isinstance(selected, Mapping):
        raise EqualAccuracyError("missing selected-plane field evidence")
    planes = selected.get("planes")
    if not isinstance(planes, list) or not planes:
        raise EqualAccuracyError("missing selected-plane field rows")
    plane_rows: dict[float, dict[str, float]] = {}
    for index, row in enumerate(planes):
        if not isinstance(row, Mapping):
            raise EqualAccuracyError(f"selected plane {index} is not an object")
        z_nm = _finite(row.get("z_nm"), label=f"selected plane {index} z")
        if z_nm in plane_rows:
            raise EqualAccuracyError(f"duplicate selected plane z={z_nm}")
        electric = row.get("electric")
        magnetic = row.get("magnetic")
        if not isinstance(electric, Mapping) or not isinstance(magnetic, Mapping):
            raise EqualAccuracyError(f"selected plane z={z_nm} lacks E/H fields")
        plane_rows[z_nm] = {
            "electric_relative_l2": _finite(
                electric.get("relative_l2"), label=f"selected plane {z_nm} E"
            ),
            "magnetic_relative_l2": _finite(
                magnetic.get("relative_l2"), label=f"selected plane {z_nm} H"
            ),
        }
    return {
        "interfaces": interface_rows,
        "planes": plane_rows,
        "reference_npz": selected.get("reference_npz"),
        "sample_shape": selected.get("sample_shape_z_y_x_component"),
    }


def _ignored_beta_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in ("target", "error", "tolerance", "residual", "drift", "gate")
    )


def _flatten_beta(value: object, path: str) -> dict[str, complex]:
    if isinstance(value, bool):
        return {}
    if isinstance(value, (int, float)):
        number = _finite(value, label=path)
        return {path: complex(number, 0.0)}
    if isinstance(value, Mapping):
        result: dict[str, complex] = {}
        for key, child in value.items():
            result.update(_flatten_beta(child, f"{path}/{key}"))
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) == 2 and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        ):
            return {path: _complex_value(value, label=path)}
        result = {}
        for index, child in enumerate(value):
            result.update(_flatten_beta(child, f"{path}/{index}"))
        return result
    return {}


def _beta_evidence(measurements: Mapping[str, Any]) -> dict[str, complex]:
    qep = measurements.get("qep")
    if not isinstance(qep, Mapping):
        return {}
    result: dict[str, complex] = {}
    for key, value in qep.items():
        name = str(key)
        if "beta" in name.lower() and not _ignored_beta_key(name):
            result.update(_flatten_beta(value, f"qep/{name}"))
    return result


def _physical_identity(reference: _Evidence, candidate: _Evidence) -> list[str]:
    failures: list[str] = []
    for key in ("wavelength_nm", "incident_grazing_deg", "polarization_kind"):
        if reference.case.get(key) != candidate.case.get(key):
            failures.append(f"physical_case_mismatch:{key}")
    optional = ("period_x_nm", "period_y_nm", "geometry_kind", "material_kind")
    for key in optional:
        if key in reference.case or key in candidate.case:
            if reference.case.get(key) != candidate.case.get(key):
                failures.append(f"physical_case_mismatch:{key}")
    return failures


def _comparison(reference: _Evidence, candidate: _Evidence) -> dict[str, Any]:
    failures = _physical_identity(reference, candidate)
    if reference.source_sha != candidate.source_sha:
        failures.append("source_sha_mismatch")

    ref_rta = _port_power(reference.measurements)
    cand_rta = _port_power(candidate.measurements)
    rta_rows = {
        key: {
            "reference": ref_rta[key],
            "candidate": cand_rta[key],
            "absolute_delta": abs(cand_rta[key] - ref_rta[key]),
        }
        for key in ref_rta
    }
    rta_pass = max(row["absolute_delta"] for row in rta_rows.values()) <= RTA_ABSOLUTE_MAX
    if not rta_pass:
        failures.append("rta_absolute_delta_above_gate")

    ref_orders = _diffraction_orders(reference.measurements)
    cand_orders = _diffraction_orders(candidate.measurements)
    ref_propagating = {key for key, row in ref_orders.items() if row["propagating"]}
    cand_propagating = {key for key, row in cand_orders.items() if row["propagating"]}
    coverage_equal = ref_propagating == cand_propagating and bool(ref_propagating)
    order_rows: list[dict[str, Any]] = []
    for key in sorted(ref_propagating & cand_propagating):
        ref = ref_orders[key]
        cand = cand_orders[key]
        significant = max(abs(ref["power_ratio"]), abs(cand["power_ratio"])) >= SIGNIFICANT_ORDER_POWER
        delta = abs(cand["amplitude"] - ref["amplitude"])
        relative = delta / max(abs(ref["amplitude"]), abs(cand["amplitude"]), 1.0e-30)
        order_rows.append(
            {
                "key": list(key),
                "significant": significant,
                "reference_amplitude": [ref["amplitude"].real, ref["amplitude"].imag],
                "candidate_amplitude": [cand["amplitude"].real, cand["amplitude"].imag],
                "complex_amplitude_relative_delta": relative,
                "pass": (not significant) or relative <= ORDER_COMPLEX_AMPLITUDE_RELATIVE_MAX,
            }
        )
    significant_rows = [row for row in order_rows if row["significant"]]
    orders_pass = bool(significant_rows) and coverage_equal and all(
        row["pass"] for row in significant_rows
    )
    if not orders_pass:
        failures.append("significant_diffraction_complex_amplitude_gate_failed")

    ref_fields = _field_evidence(reference.measurements)
    cand_fields = _field_evidence(candidate.measurements)
    interface_rows = []
    for side in ("bottom", "top"):
        ref = ref_fields["interfaces"][side]
        cand = cand_fields["interfaces"][side]
        interface_rows.append(
            {
                "side": side,
                "reference": ref,
                "candidate": cand,
                "electric_metric_absolute_delta": abs(
                    cand["electric_relative_l2"] - ref["electric_relative_l2"]
                ),
                "magnetic_metric_absolute_delta": abs(
                    cand["magnetic_relative_l2"] - ref["magnetic_relative_l2"]
                ),
            }
        )
    interface_pass = all(
        max(row[which]["electric_relative_l2"] for which in ("reference", "candidate"))
        <= INTERFACE_E_RELATIVE_MAX
        and max(row[which]["magnetic_relative_l2"] for which in ("reference", "candidate"))
        <= INTERFACE_H_RELATIVE_MAX
        for row in interface_rows
    )
    if not interface_pass:
        failures.append("interface_e_h_gate_failed")

    ref_planes = ref_fields["planes"]
    cand_planes = cand_fields["planes"]
    plane_coverage_equal = set(ref_planes) == set(cand_planes) and bool(ref_planes)
    reference_binding_equal = True
    for key in ("reference_npz", "sample_shape"):
        if ref_fields[key] is not None or cand_fields[key] is not None:
            reference_binding_equal = reference_binding_equal and ref_fields[key] == cand_fields[key]
    plane_rows = []
    for z_nm in sorted(set(ref_planes) & set(cand_planes)):
        ref = ref_planes[z_nm]
        cand = cand_planes[z_nm]
        plane_rows.append(
            {
                "z_nm": z_nm,
                "reference": ref,
                "candidate": cand,
                "electric_metric_absolute_delta": abs(
                    cand["electric_relative_l2"] - ref["electric_relative_l2"]
                ),
                "magnetic_metric_absolute_delta": abs(
                    cand["magnetic_relative_l2"] - ref["magnetic_relative_l2"]
                ),
            }
        )
    planes_pass = bool(plane_rows) and plane_coverage_equal and reference_binding_equal and all(
        max(
            row[which][field]
            for which in ("reference", "candidate")
            for field in ("electric_relative_l2", "magnetic_relative_l2")
        )
        <= SELECTED_PLANE_FIELD_RELATIVE_MAX
        for row in plane_rows
    )
    if not planes_pass:
        failures.append("selected_plane_field_gate_failed")

    ref_beta = _beta_evidence(reference.measurements)
    cand_beta = _beta_evidence(candidate.measurements)
    common_beta = sorted(set(ref_beta) & set(cand_beta))
    if not common_beta:
        beta = {
            "status": "not_available",
            "required_for_equal_accuracy_gate": False,
            "pass": True,
            "reason": "no common measured QEP beta evidence in selected watchdog records",
            "rows": [],
        }
    else:
        beta_rows = []
        for key in common_beta:
            ref = ref_beta[key]
            cand = cand_beta[key]
            relative = abs(cand - ref) / max(abs(ref), abs(cand), 1.0e-30)
            beta_rows.append(
                {
                    "evidence_path": key,
                    "reference_beta": [ref.real, ref.imag],
                    "candidate_beta": [cand.real, cand.imag],
                    "relative_delta": relative,
                    "pass": relative <= QEP_BETA_RELATIVE_MAX,
                }
            )
        beta_pass = set(ref_beta) == set(cand_beta) and all(row["pass"] for row in beta_rows)
        beta = {
            "status": "available",
            "required_for_equal_accuracy_gate": True,
            "coverage_equal": set(ref_beta) == set(cand_beta),
            "pass": beta_pass,
            "rows": beta_rows,
        }
        if not beta_pass:
            failures.append("qep_beta_gate_failed")

    gates = {
        "same_clean_source_sha": reference.source_sha == candidate.source_sha,
        "same_physical_case": not any(
            failure.startswith("physical_case_mismatch") for failure in failures
        ),
        "rta_absolute_delta": rta_pass,
        "significant_diffraction_complex_amplitude": orders_pass,
        "interface_e_h": interface_pass,
        "selected_plane_fields": planes_pass,
        "qep_beta_when_available": beta["pass"],
    }
    qualified = not failures and all(gates.values())
    return {
        "status": "equal_accuracy_qualified" if qualified else "not_qualified",
        "gates": gates,
        "failures": list(dict.fromkeys(failures)),
        "comparisons": {
            "rta": {"pass": rta_pass, "rows": rta_rows},
            "diffraction_orders": {
                "pass": orders_pass,
                "coverage_equal": coverage_equal,
                "significant_order_count": len(significant_rows),
                "rows": order_rows,
            },
            "interface_e_h": {"pass": interface_pass, "rows": interface_rows},
            "selected_plane_fields": {
                "pass": planes_pass,
                "coverage_equal": plane_coverage_equal,
                "reference_binding_equal": reference_binding_equal,
                "rows": plane_rows,
            },
            "qep_beta": beta,
        },
    }


def _compression(reference: Mapping[str, int | float], candidate: Mapping[str, int | float]) -> dict[str, float]:
    keys = (
        "local_dofs",
        "total_rows",
        "assembled_nnz",
        "authoritative_rss_bytes",
        "total_time_seconds",
    )
    return {key: float(reference[key]) / float(candidate[key]) for key in keys}


def _pareto_frontier(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    keys = ("local_dofs", "total_rows", "assembled_nnz", "authoritative_rss_bytes", "total_time_seconds")
    frontier: list[str] = []
    for row in rows:
        costs = row["costs"]
        dominated = any(
            other is not row
            and all(other["costs"][key] <= costs[key] for key in keys)
            and any(other["costs"][key] < costs[key] for key in keys)
            for other in rows
        )
        if not dominated:
            frontier.append(str(row["candidate_id"]))
    return frontier


def build_equal_accuracy(
    reference: Path | str,
    candidates: Sequence[Path | str],
    *,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Compare arbitrary qualified Hybrid p/h candidates against one reference."""

    if not candidates:
        raise EqualAccuracyError("at least one --candidate funnel is required")
    root = Path(repo_root).resolve()
    reference_evidence = _load_evidence(reference, repo_root=root)
    # A reference that lacks complete observable evidence cannot define equal accuracy.
    _port_power(reference_evidence.measurements)
    _diffraction_orders(reference_evidence.measurements)
    reference_fields = _field_evidence(reference_evidence.measurements)
    if any(
        row["electric_relative_l2"] > INTERFACE_E_RELATIVE_MAX
        or row["magnetic_relative_l2"] > INTERFACE_H_RELATIVE_MAX
        for row in reference_fields["interfaces"].values()
    ) or any(
        max(row.values()) > SELECTED_PLANE_FIELD_RELATIVE_MAX
        for row in reference_fields["planes"].values()
    ):
        raise EqualAccuracyError("reference fails interface or selected-plane field gates")

    candidate_rows: list[dict[str, Any]] = []
    input_rows: list[dict[str, Any]] = []
    for index, requested in enumerate(candidates, start=1):
        candidate_id = f"candidate_{index}"
        path, candidate_descriptor = _repo_path(requested, root=root)
        try:
            evidence = _load_evidence(path, repo_root=root)
            comparison = _comparison(reference_evidence, evidence)
            compression = _compression(reference_evidence.costs, evidence.costs)
            row = {
                "candidate_id": candidate_id,
                "label": evidence.funnel.path.stem,
                "status": comparison["status"],
                "case": dict(evidence.case),
                "selected_mode_count_per_direction": evidence.selected_m,
                "source_commit_full_sha": evidence.source_sha,
                "input": evidence.input_descriptor(),
                "costs": evidence.costs,
                "compression_ratios": compression,
                "local_dof_compression_classification": classify_compression(
                    compression["local_dofs"]
                ),
                "gates": comparison["gates"],
                "comparisons": comparison["comparisons"],
                "failures": comparison["failures"],
            }
            input_rows.append({"candidate_id": candidate_id, **evidence.input_descriptor()})
        except EqualAccuracyError as exc:
            funnel_hash = _file_sha256(path) if path.is_file() else None
            row = {
                "candidate_id": candidate_id,
                "label": path.stem,
                "status": "not_qualified",
                "case": None,
                "selected_mode_count_per_direction": None,
                "source_commit_full_sha": None,
                "input": {
                    "funnel_path": candidate_descriptor,
                    "funnel_sha256": funnel_hash,
                    "selected_watchdog_path": None,
                    "selected_watchdog_sha256": None,
                },
                "costs": None,
                "compression_ratios": None,
                "local_dof_compression_classification": None,
                "gates": {},
                "comparisons": {},
                "failures": [f"candidate_evidence_invalid: {exc}"],
            }
            input_rows.append({"candidate_id": candidate_id, **row["input"]})
        candidate_rows.append(row)

    qualified = [row for row in candidate_rows if row["status"] == "equal_accuracy_qualified"]
    frontier = _pareto_frontier(qualified)
    keys = ("local_dofs", "total_rows", "assembled_nnz", "authoritative_rss_bytes", "total_time_seconds")
    best = min(
        qualified,
        key=lambda row: tuple(row["costs"][key] for key in keys) + (row["candidate_id"],),
        default=None,
    )
    record: dict[str, Any] = {
        "schema_version": "task033.case091.equal-accuracy.v1",
        "record_type": "task033_global_equal_accuracy_efficiency",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "qualified" if best is not None else "not_qualified",
        "identity": {
            "is_pde_run": False,
            "consumes_measured_pde_records": True,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
            "source_commit_full_sha": reference_evidence.source_sha,
            "all_qualified_inputs_same_clean_sha": all(
                row.get("source_commit_full_sha") == reference_evidence.source_sha
                for row in qualified
            ),
        },
        "tolerances": {
            "rta_absolute_max": RTA_ABSOLUTE_MAX,
            "significant_order_power": SIGNIFICANT_ORDER_POWER,
            "significant_order_complex_amplitude_relative_max": ORDER_COMPLEX_AMPLITUDE_RELATIVE_MAX,
            "interface_e_relative_max": INTERFACE_E_RELATIVE_MAX,
            "interface_h_relative_max": INTERFACE_H_RELATIVE_MAX,
            "selected_plane_field_relative_max": SELECTED_PLANE_FIELD_RELATIVE_MAX,
            "qep_beta_relative_max_when_available": QEP_BETA_RELATIVE_MAX,
            "true_residual_max": TRUE_RESIDUAL_MAX,
        },
        "inputs": {
            "reference": reference_evidence.input_descriptor(),
            "candidates": input_rows,
        },
        "reference": {
            "label": reference_evidence.funnel.path.stem,
            "case": dict(reference_evidence.case),
            "selected_mode_count_per_direction": reference_evidence.selected_m,
            "source_commit_full_sha": reference_evidence.source_sha,
            "costs": reference_evidence.costs,
        },
        "candidates": candidate_rows,
        "selection": {
            "qualified_candidate_count": len(qualified),
            "pareto_frontier_candidate_ids": frontier,
            "best_candidate_id": None if best is None else best["candidate_id"],
            "best_candidate_label": None if best is None else best["label"],
            "criterion": (
                "lexicographic minimum measured local DoF, total rows, assembled NNZ, "
                "authoritative RSS, then total time among equal-accuracy-qualified candidates"
            ),
        },
        "classification_boundaries": {
            "weak": "<1.3",
            "positive": ">=1.3 and <2",
            "clear": ">=2 and <3",
            "engineering": ">=3 and <5",
            "strong": ">=5",
        },
    }
    record["payload_sha256"] = _payload_sha256(record)
    _validate_schema(record, OUTPUT_SCHEMA_PATH, label="equal-accuracy output")
    return record


def build_equal_accuracy_from_paths(
    reference: Path | str,
    candidates: Sequence[Path | str],
    *,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """CLI-friendly alias for :func:`build_equal_accuracy`."""

    return build_equal_accuracy(reference, candidates, repo_root=repo_root)


build_equal_accuracy_comparison = build_equal_accuracy


__all__ = [
    "EqualAccuracyError",
    "build_equal_accuracy",
    "build_equal_accuracy_comparison",
    "build_equal_accuracy_from_paths",
    "classify_compression",
]
