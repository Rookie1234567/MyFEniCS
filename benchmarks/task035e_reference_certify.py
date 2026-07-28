#!/usr/bin/env python3
"""Adapt hash-bound Task035e watchdog evidence into a sealed reference campaign.

This is an evaluator-side adapter.  It deliberately reads raw Full3D evidence
and therefore must never be imported by, or write into, ``blind_controller``.
The only persistent output is the existing certifier's mode-0600 sealed
package; stdout contains status and content hashes, never physical values.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np

from src.adaptivity.reference_certifier import (
    ComplexObservation,
    ComplexValue,
    DiffractionOrderObservation,
    PhysicalRunIdentity,
    ReferenceCampaign,
    REFERENCE_CERTIFICATION_INCOMPLETE,
    ReferenceCertifier,
    ReferenceRunResult,
    RunGateEvidence,
    ScalarObservation,
)


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_SCHEMA = "task033.full3d-watchdog.v1"
WATCHDOG_BENCHMARK_ID = "task033_target_full3d_watchdog"
TASK035E_RESOURCE_SCHEMA = "task035e.reference-resource-authority.v1"
TASK035E_CONFIG_SCHEMA = "task035e.reference-config-authority.v1"
TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA = (
    "task035e.h5-factorization-launch-authority.v1"
)
STATIC_BACKEND = "assembly_time_static_condensed"
FIXED_PORTS = ("top", "bottom")
FIXED_M = (0, -1, -2, -3, -4, -5, -6, -7)
FIXED_N = 0
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_NORMALIZATION_CONTRACT = {
    "schema_version": "task035e.fixed-order-normalization.v1",
    "amplitude_plane": "physical_boundary",
    "co_polarization_for_incident_S": "s",
    "cross_polarization_for_incident_S": "p",
    "total_power": "s_plus_p_power_ratio",
    "admittance": "s_beta_over_k0_mu_r",
    "far_field_power_applicability": "positive_outward_real_poynting",
}
NORMALIZATION_IDENTITY = (
    "sha256:"
    + hashlib.sha256(
        json.dumps(
            _NORMALIZATION_CONTRACT,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()
)

_GEOMETRY_CONFIG_KEYS = (
    "geometry_kind",
    "stage_case",
    "period_x",
    "period_y",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    "physical_z_min",
    "physical_z_max",
    "air_height",
    "substrate_thickness",
    "grating_height",
    "grating_width_x",
    "grating_width_y",
    "grating_bounds",
    "interface_z",
    "use_pml",
    "pml_top_thickness",
    "pml_bottom_thickness",
)
_MATERIAL_CONFIG_KEYS = (
    "lambda0",
    "n_air",
    "n_grating",
    "n_substrate",
    "eps_air",
    "eps_grating",
    "eps_substrate",
    "mu_r",
    "grating_material_label",
    "substrate_material_label",
)
_INCIDENT_CONFIG_KEYS = (
    "lambda0",
    "incident_theta_deg",
    "incident_phi_deg",
    "polarization_kind",
    "incident_amplitude",
    "incident_e0_v_per_m",
    "propagation_direction",
    "wavevector",
    "scattering_background",
)
_DTN_CONFIG_KEYS = (
    "stage4_boundary_model",
    "stage4_dtn_order_policy",
    "stage4_dtn_assembly",
    "stage4_pml_outer_bc",
    "use_floquet_xy",
    "period_x",
    "period_y",
    "floquet_phase_x",
    "floquet_phase_y",
    "physical_z_min",
    "physical_z_max",
    "n_air",
    "n_substrate",
    "diffraction_zero_order_only",
    "diffraction_order_max_m",
    "diffraction_order_max_n",
    "diffraction_rayleigh_tol",
)
_POSTPROCESS_CONFIG_KEYS = (
    "full3d_reference_export",
    "full3d_reference_plane_z",
    "full3d_reference_sample_count_x",
    "full3d_reference_sample_count_y",
    "diffraction_sample_count_x",
    "diffraction_sample_count_y",
    "diffraction_probe_fraction",
    "electric_field_unit",
    "magnetic_field_unit",
)


class ReferenceArtifactError(ValueError):
    """Raised when a watchdog record or one of its artifacts is not authoritative."""


@dataclass(frozen=True, slots=True)
class WatchdogRecordInput:
    """One record path plus an independently frozen byte hash."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if _SHA256_RE.fullmatch(self.sha256) is None:
            raise ReferenceArtifactError(
                "watchdog record SHA-256 must be 64 lowercase hexadecimal characters"
            )


@dataclass(frozen=True, slots=True)
class H5FactorizationDecisionInput:
    """One prelaunch DENY authority used as an incomplete h5 endpoint."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if _SHA256_RE.fullmatch(self.sha256) is None:
            raise ReferenceArtifactError(
                "h5 factorization decision SHA-256 must be 64 lowercase "
                "hexadecimal characters"
            )


@dataclass(frozen=True, slots=True)
class AdaptedReferenceRun:
    """Typed run plus adapter-only cross-point identities."""

    result: ReferenceRunResult
    normalized_config_sha256: str
    sample_grid_sha256: str | None
    artifact_sha256: Mapping[str, str]


def _canonical(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, np.generic):
        return _canonical(value.item())
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReferenceArtifactError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ReferenceArtifactError(f"{label} must be a JSON array")
    return value


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReferenceArtifactError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ReferenceArtifactError(f"{label} must be finite")
    return result


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReferenceArtifactError(f"{label} must be an integer")
    return int(value)


def _complex(value: Any, *, label: str) -> complex:
    row = _sequence(value, label=label)
    if len(row) != 2:
        raise ReferenceArtifactError(f"{label} must contain [real, imag]")
    return complex(
        _finite(row[0], label=f"{label}[0]"),
        _finite(row[1], label=f"{label}[1]"),
    )


def _load_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceArtifactError(f"cannot read {label}: {path}") from exc
    return _mapping(value, label=label)


def _resolve_repo_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReferenceArtifactError(f"{label} must be a nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def _run_child(run_dir: Path, name: Any, *, label: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ReferenceArtifactError(f"{label} must be one plain file name")
    path = (run_dir / name).resolve()
    if path.parent != run_dir:
        raise ReferenceArtifactError(f"{label} escapes the hash-bound run directory")
    return path


def _require_hash(path: Path, expected: Any, *, label: str) -> str:
    if not path.is_file():
        raise ReferenceArtifactError(f"{label} is missing: {path}")
    if not isinstance(expected, str) or _SHA256_RE.fullmatch(expected) is None:
        raise ReferenceArtifactError(f"{label} lacks a valid expected SHA-256")
    observed = _file_sha256(path)
    if observed != expected:
        raise ReferenceArtifactError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {observed}"
        )
    return observed


def _selected_config(
    config: Mapping[str, Any],
    keys: Sequence[str],
    *,
    label: str,
) -> dict[str, Any]:
    missing = [key for key in keys if key not in config]
    if missing:
        raise ReferenceArtifactError(f"{label} config is missing keys: {missing}")
    return {key: _canonical(config[key]) for key in keys}


def _physical_identity(
    config: Mapping[str, Any],
    source_sha: str,
) -> PhysicalRunIdentity:
    return PhysicalRunIdentity(
        geometry_sha256=_json_sha256(
            {
                "schema_version": "task035e.geometry-identity.v1",
                "config": _selected_config(
                    config,
                    _GEOMETRY_CONFIG_KEYS,
                    label="geometry",
                ),
            }
        ),
        material_sha256=_json_sha256(
            {
                "schema_version": "task035e.material-identity.v1",
                "config": _selected_config(
                    config,
                    _MATERIAL_CONFIG_KEYS,
                    label="material",
                ),
            }
        ),
        incident_sha256=_json_sha256(
            {
                "schema_version": "task035e.incident-identity.v1",
                "config": _selected_config(
                    config,
                    _INCIDENT_CONFIG_KEYS,
                    label="incident",
                ),
            }
        ),
        dtn_definition_sha256=_json_sha256(
            {
                "schema_version": "task035e.dtn-identity.v1",
                "config": _selected_config(
                    config,
                    _DTN_CONFIG_KEYS,
                    label="DtN",
                ),
                "normalization": _NORMALIZATION_CONTRACT,
            }
        ),
        postprocessing_sha256=_json_sha256(
            {
                "schema_version": "task035e.postprocessing-identity.v1",
                "config": _selected_config(
                    config,
                    _POSTPROCESS_CONFIG_KEYS,
                    label="postprocess",
                ),
                "field_observations": {
                    "interface": ["E_t_interface_V_per_m", "H_t_interface_A_per_m"],
                    "volume": ["E_V_per_m", "H_A_per_m"],
                    "volume_plane_selection": "middle_plane_indices",
                    "storage": "pointwise_complex_observations",
                },
            }
        ),
        source_sha=source_sha,
    )


def _normalized_config_sha(config: Mapping[str, Any]) -> str:
    # These are the only legal h-sequence differences.  All physical,
    # discretization-family, solver, lifecycle and postprocess options remain.
    normalized = {
        key: _canonical(value)
        for key, value in config.items()
        if key != "case_name" and not key.startswith("mesh_")
    }
    return _json_sha256(
        {
            "schema_version": "task035e.reference-normalized-config.v1",
            "config": normalized,
        }
    )


def _record_context(
    record_input: WatchdogRecordInput,
    *,
    expected_h_nm: float,
) -> tuple[
    Mapping[str, Any],
    Path,
    Mapping[str, Any],
    Mapping[str, Any],
    str,
    dict[str, str],
]:
    record_path = Path(record_input.path).resolve()
    record_sha = _require_hash(
        record_path,
        record_input.sha256,
        label="watchdog record",
    )
    record = _load_json(record_path, label="watchdog record")
    if (
        record.get("schema_version") != WATCHDOG_SCHEMA
        or record.get("benchmark_id") != WATCHDOG_BENCHMARK_ID
    ):
        raise ReferenceArtifactError("watchdog record identity is not Task033 Full3D")
    if _finite(record.get("h_nm"), label="record.h_nm") != expected_h_nm:
        raise ReferenceArtifactError("watchdog record h point differs from CLI slot")
    if (
        record.get("degree") != 6
        or record.get("polarization_kind") != "s"
        or record.get("mpi_size") != 8
        or record.get("profile") != "default"
        or record.get("stage4_full3d_assembly_backend_requested")
        != STATIC_BACKEND
    ):
        raise ReferenceArtifactError(
            "reference record must be p6/static/default/direct-campaign MPI8 S"
        )

    source = _mapping(record.get("source"), label="record.source")
    source_sha = source.get("commit_sha")
    if not isinstance(source_sha, str) or _SOURCE_SHA_RE.fullmatch(source_sha) is None:
        raise ReferenceArtifactError("record source commit must be a full Git SHA")
    if not all(
        (
            source.get("head_after_sha") == source_sha,
            source.get("tracked_source_dirty") is False,
            source.get("stable_and_clean_after") is True,
            source.get("status_after") == "",
        )
    ):
        raise ReferenceArtifactError("record source was not stable and clean")

    task035e = _mapping(
        record.get("task035e_reference_certifier"),
        label="record.task035e_reference_certifier",
    )
    if (
        task035e.get("schema_version") != TASK035E_RESOURCE_SCHEMA
        or task035e.get("selected") is not True
    ):
        raise ReferenceArtifactError("Task035e reference gate was not selected")
    config_authority = _mapping(
        task035e.get("config_authority"),
        label="Task035e config authority",
    )
    payload = _mapping(
        config_authority.get("payload"),
        label="Task035e config authority payload",
    )
    if (
        payload.get("schema_version") != TASK035E_CONFIG_SCHEMA
        or payload.get("mpi_size") != 8
    ):
        raise ReferenceArtifactError("Task035e config authority identity is invalid")
    config_sha = config_authority.get("sha256")
    if (
        not isinstance(config_sha, str)
        or _SHA256_RE.fullmatch(config_sha) is None
        or _json_sha256(payload) != config_sha
    ):
        raise ReferenceArtifactError("Task035e config authority SHA-256 mismatch")
    config = _mapping(payload.get("config"), label="Task035e config")
    if (
        _finite(config.get("mesh_target_size"), label="config.mesh_target_size")
        != expected_h_nm
    ):
        raise ReferenceArtifactError("config mesh target differs from h point")
    run_dir = _resolve_repo_path(
        _mapping(record.get("raw_evidence"), label="record.raw_evidence").get(
            "run_directory"
        ),
        label="record.raw_evidence.run_directory",
    )
    if not run_dir.is_dir():
        raise ReferenceArtifactError(f"hash-bound run directory is missing: {run_dir}")
    return (
        record,
        run_dir,
        task035e,
        config,
        source_sha,
        {
            "record": record_sha,
            "config_authority": config_sha,
        },
    )


def _validate_completed_solver(
    record: Mapping[str, Any],
    run_dir: Path,
    task035e: Mapping[str, Any],
    config: Mapping[str, Any],
    hashes: dict[str, str],
) -> Mapping[str, Any]:
    if (
        record.get("run_kind") != "full-solve"
        or record.get("status") != "task035e_reference_full_solve_pass"
        or record.get("controlled_resource_stop") is not False
    ):
        raise ReferenceArtifactError("completed reference needs a passed full-solve record")
    qualification = _mapping(
        record.get("qualification"),
        label="record.qualification",
    )
    if qualification.get("pass") is not True or qualification.get("failures") != []:
        raise ReferenceArtifactError("watchdog qualification did not pass")
    lifecycle = _mapping(
        task035e.get("lifecycle_authority"),
        label="Task035e lifecycle authority",
    )
    lifecycle_checks = _mapping(
        lifecycle.get("checks"),
        label="Task035e lifecycle checks",
    )
    if lifecycle.get("pass") is not True or not lifecycle_checks or not all(
        value is True for value in lifecycle_checks.values()
    ):
        raise ReferenceArtifactError("Task035e lifecycle authority did not pass")

    raw = _mapping(record.get("raw_evidence"), label="record.raw_evidence")
    summary_path = _run_child(run_dir, "run_summary.json", label="run summary")
    if _resolve_repo_path(raw.get("solver_summary"), label="raw solver summary") != summary_path:
        raise ReferenceArtifactError("record solver-summary path escaped its run directory")
    hashes["run_summary"] = _require_hash(
        summary_path,
        record.get("solver_summary_sha256"),
        label="run summary",
    )
    summary = _load_json(summary_path, label="run summary")
    if _canonical(record.get("solver_summary")) != _canonical(summary):
        raise ReferenceArtifactError("embedded and on-disk run summaries differ")
    if _canonical(summary.get("config")) != _canonical(config):
        raise ReferenceArtifactError("run summary and config authority differ")

    petsc = _mapping(
        summary.get("linear_solve_petsc_options"),
        label="run summary PETSc options",
    )
    backend_qualification = _mapping(
        summary.get("stage4_full3d_assembly_backend_qualification"),
        label="static backend qualification",
    )
    condensation = _mapping(
        summary.get("cell_static_condensation"),
        label="static condensation audit",
    )
    required = (
        summary.get("case_status") == "completed",
        summary.get("official_result") is True,
        summary.get("diagnostic_only") is False,
        summary.get("postprocess_skipped") is False,
        summary.get("nedelec_degree") == 6,
        summary.get("polarization_kind") == "s",
        summary.get("mpi_size") == 8,
        summary.get("stage4_full3d_assembly_backend_actual") == STATIC_BACKEND,
        summary.get("stage4_assembly_time_cell_static_condensation") is True,
        backend_qualification.get("status") == "qualified",
        condensation.get("full_global_matrix_allocated") is False,
        summary.get("linear_solve_method") == "direct_lu",
        summary.get("selected_parallel_lu_solver_type") == "mumps",
        summary.get("actual_ksp_type") == "preonly",
        summary.get("actual_pc_type") == "lu",
        summary.get("actual_pc_factor_solver_type") == "mumps",
        petsc.get("ksp_type") == "preonly",
        petsc.get("pc_type") == "lu",
        petsc.get("pc_factor_mat_solver_type") == "mumps",
        summary.get("ksp_converged") is True,
        summary.get("full3d_reference_exported") is True,
    )
    if not all(required):
        raise ReferenceArtifactError(
            "run summary is not the required p6 static direct-MUMPS MPI8 S solve"
        )
    return summary


def _validate_resource_gate(
    record: Mapping[str, Any],
    task035e: Mapping[str, Any],
    *,
    completed: bool,
) -> tuple[int, float | None, str | None]:
    live = _mapping(
        task035e.get("live_resource_gate"),
        label="Task035e live resource gate",
    )
    policy = _mapping(live.get("policy"), label="Task035e resource policy")
    total = _integer(policy.get("mem_total_bytes"), label="resource MemTotal")
    minimum_available_value = live.get("minimum_mem_available_bytes")
    minimum_available = (
        None
        if minimum_available_value is None
        else _integer(minimum_available_value, label="minimum MemAvailable")
    )
    maximum_swap_value = live.get("maximum_swap_authority_bytes")
    maximum_swap = (
        0
        if maximum_swap_value is None and not completed
        else _integer(maximum_swap_value, label="maximum swap")
    )
    headroom = (
        None
        if minimum_available is None
        else float(minimum_available / total)
    )
    if completed:
        if not all(
            (
                record.get("no_swap") is True,
                live.get("pass") is True,
                live.get("controlled_resource_stop") is False,
                live.get("stop_reason") is None,
                live.get("zero_swap_every_sample") is True,
                live.get("minimum_headroom_20_percent_preserved") is True,
                maximum_swap == 0,
                headroom is not None and headroom >= 0.20,
            )
        ):
            raise ReferenceArtifactError(
                "completed reference violated zero-swap or 20% headroom"
            )
        return maximum_swap, headroom, None
    reason = live.get("stop_reason")
    if (
        record.get("status") != "controlled_resource_stop"
        or record.get("controlled_resource_stop") is not True
        or live.get("controlled_resource_stop") is not True
        or not isinstance(reason, str)
        or not reason
    ):
        raise ReferenceArtifactError("incomplete h5 is not a controlled resource stop")
    return maximum_swap, headroom, reason


def _order_observations(
    summary: Mapping[str, Any],
    dtn: Mapping[str, Any],
) -> tuple[DiffractionOrderObservation, ...]:
    metrics = _mapping(dtn.get("metrics"), label="DtN metrics")
    if (
        metrics.get("power_source") != "dtn_port_modal_amplitudes"
        or metrics.get("diffraction_total_power_source")
        != "dtn_port_modal_amplitudes"
        or metrics.get("stage4_dtn_assembly") != "auxiliary"
        or not isinstance(metrics.get("dtn_port_modal_amplitude_convention"), str)
    ):
        raise ReferenceArtifactError("DtN artifact uses a different power convention")
    for name in ("R00_s", "R00_p", "R00_total", "R_total", "T_total"):
        if not math.isclose(
            _finite(metrics.get(name), label=f"DtN metrics.{name}"),
            _finite(summary.get(name), label=f"run summary.{name}"),
            rel_tol=0.0,
            abs_tol=1.0e-15,
        ):
            raise ReferenceArtifactError(f"DtN metrics and run summary differ for {name}")

    indexed: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for raw in _sequence(dtn.get("orders"), label="DtN orders"):
        row = _mapping(raw, label="DtN order")
        key = (
            str(row.get("side")),
            _integer(row.get("m"), label="DtN order m"),
            _integer(row.get("n"), label="DtN order n"),
            str(row.get("polarization")),
        )
        if key in indexed:
            raise ReferenceArtifactError(f"duplicate DtN order/polarization: {key}")
        indexed[key] = row

    k0 = _finite(summary.get("config", {}).get("k0"), label="config.k0")
    mu_r = _complex(summary.get("config", {}).get("mu_r"), label="config.mu_r")
    physical_ids = {
        (port, m, n)
        for port, m, n, polarization in indexed
        if polarization in {"s", "p"}
    }
    if any(
        port not in FIXED_PORTS or polarization not in {"s", "p"}
        for port, _m, _n, polarization in indexed
    ):
        raise ReferenceArtifactError(
            "DtN order inventory contains an unsupported port/polarization"
        )
    fixed_ids = {
        (port, m, FIXED_N)
        for port in FIXED_PORTS
        for m in FIXED_M
    }
    missing_fixed = sorted(fixed_ids - physical_ids)
    if missing_fixed:
        raise ReferenceArtifactError(
            f"missing fixed DtN physical orders: {missing_fixed[:2]}"
        )

    port_index = {port: index for index, port in enumerate(FIXED_PORTS)}
    observations = []
    for port, m, n in sorted(
        physical_ids,
        key=lambda row: (port_index[row[0]], row[1], row[2]),
    ):
        rows = {}
        for polarization in ("s", "p"):
            key = (port, m, n, polarization)
            if key not in indexed:
                fixed_label = (
                    "fixed " if (port, m, n) in fixed_ids else ""
                )
                raise ReferenceArtifactError(
                    f"missing {fixed_label}DtN order/polarization: {key}"
                )
            rows[polarization] = indexed[key]
        co = rows["s"]
        cross = rows["p"]
        for field in ("propagating", "power_carrying"):
            if co.get(field) is not cross.get(field):
                raise ReferenceArtifactError(
                    f"S/P {field} metadata differs for {(port, m, n)}"
                )
        if _complex(co.get("kz"), label="S kz") != _complex(
            cross.get("kz"),
            label="P kz",
        ):
            raise ReferenceArtifactError("S/P kz metadata differs")
        propagating = co.get("propagating")
        power_carrying = co.get("power_carrying")
        if not isinstance(propagating, bool) or not isinstance(
            power_carrying,
            bool,
        ):
            raise ReferenceArtifactError(
                "propagating/power_carrying must be boolean"
            )
        if propagating is not power_carrying:
            raise ReferenceArtifactError(
                "reference order propagation and power-carrying flags differ"
            )
        raw_co_power = co.get("power_ratio")
        raw_cross_power = cross.get("power_ratio")
        if power_carrying:
            co_power = _finite(raw_co_power, label="S power ratio")
            cross_power = _finite(
                raw_cross_power,
                label="P power ratio",
            )
            if co_power < 0.0 or cross_power < 0.0:
                raise ReferenceArtifactError(
                    "order power ratios must be nonnegative"
                )
        else:
            co_power = (
                0.0
                if raw_co_power is None
                else _finite(raw_co_power, label="S evanescent power")
            )
            cross_power = (
                0.0
                if raw_cross_power is None
                else _finite(
                    raw_cross_power,
                    label="P evanescent power",
                )
            )
            if co_power != 0.0 or cross_power != 0.0:
                raise ReferenceArtifactError(
                    "evanescent order carries nonzero power"
                )
        beta = _complex(co.get("beta"), label="S beta")
        admittance = beta / (k0 * mu_r)
        observations.append(
            DiffractionOrderObservation(
                port=port,
                m=m,
                n=n,
                propagating=power_carrying,
                kz=ComplexValue.from_complex(
                    _complex(co.get("kz"), label="S kz")
                ),
                admittance=ComplexValue.from_complex(admittance),
                normalization_identity=NORMALIZATION_IDENTITY,
                total_power=(
                    co_power + cross_power if power_carrying else None
                ),
                co_polarized_amplitude=ComplexValue.from_complex(
                    _complex(
                        co.get("outgoing_amplitude_at_boundary"),
                        label="S boundary amplitude",
                    )
                ),
                cross_polarized_power=(
                    cross_power if power_carrying else None
                ),
                cross_polarized_amplitude=ComplexValue.from_complex(
                    _complex(
                        cross.get("outgoing_amplitude_at_boundary"),
                        label="P boundary amplitude",
                    )
                ),
            )
        )
    return tuple(observations)


def _field_observations(
    run_dir: Path,
    summary: Mapping[str, Any],
    hashes: dict[str, str],
    *,
    expected_metadata_sha256: Any,
) -> tuple[tuple[ComplexObservation, ...], str]:
    metadata_path = _run_child(
        run_dir,
        "full3d_reference_samples.json",
        label="reference metadata",
    )
    hashes["reference_json"] = _require_hash(
        metadata_path,
        expected_metadata_sha256,
        label="reference metadata",
    )
    metadata = _load_json(metadata_path, label="reference metadata")
    archive_path = _run_child(
        run_dir,
        metadata.get("archive"),
        label="reference archive",
    )
    archive_expected_sha = metadata.get("archive_sha256")
    hashes["reference_npz"] = _require_hash(
        archive_path,
        archive_expected_sha,
        label="reference NPZ",
    )
    if (
        _resolve_repo_path(
            summary.get("full3d_reference_archive"),
            label="run summary reference archive",
        )
        != archive_path
        or summary.get("full3d_reference_archive_sha256") != hashes["reference_npz"]
        or _integer(metadata.get("archive_bytes"), label="reference archive bytes")
        != archive_path.stat().st_size
        or _integer(
            summary.get("full3d_reference_archive_bytes"),
            label="run summary archive bytes",
        )
        != archive_path.stat().st_size
    ):
        raise ReferenceArtifactError("reference JSON/NPZ/run-summary binding differs")

    try:
        archive = np.load(archive_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ReferenceArtifactError("cannot load reference NPZ safely") from exc
    with archive:
        required = {
            "x_nm",
            "y_nm",
            "z_nm",
            "E_V_per_m",
            "H_A_per_m",
            "interface_z_nm",
            "E_t_interface_V_per_m",
            "H_t_interface_A_per_m",
        }
        if set(archive.files) != required:
            raise ReferenceArtifactError(
                f"reference NPZ inventory differs: {sorted(set(archive.files) ^ required)}"
            )
        arrays = {name: np.asarray(archive[name]) for name in required}

    x = arrays["x_nm"]
    y = arrays["y_nm"]
    z = arrays["z_nm"]
    interface_z = arrays["interface_z_nm"]
    e = arrays["E_V_per_m"]
    h = arrays["H_A_per_m"]
    e_interface = arrays["E_t_interface_V_per_m"]
    h_interface = arrays["H_t_interface_A_per_m"]
    for name, array in arrays.items():
        if not np.all(np.isfinite(array)):
            raise ReferenceArtifactError(f"reference array {name} is not finite")
    if (
        x.ndim != 1
        or y.ndim != 1
        or z.ndim != 1
        or interface_z.ndim != 1
        or e.shape != (z.size, y.size, x.size, 3)
        or h.shape != e.shape
        or e_interface.shape != (interface_z.size, y.size, x.size, 2)
        or h_interface.shape != e_interface.shape
        or e.dtype.kind != "c"
        or h.dtype.kind != "c"
        or e_interface.dtype.kind != "c"
        or h_interface.dtype.kind != "c"
    ):
        raise ReferenceArtifactError("reference NPZ shapes or dtypes differ")
    expected_shape = list(e.shape)
    if (
        list(metadata.get("array_shape_z_y_x_component", ())) != expected_shape
        or _integer(metadata.get("point_count"), label="reference point count")
        != z.size * y.size * x.size
        or list(metadata.get("components", ())) != ["x", "y", "z"]
        or list(metadata.get("tangential_components", ())) != ["x", "y"]
    ):
        raise ReferenceArtifactError("reference metadata does not describe the NPZ")
    config = _mapping(summary.get("config"), label="run summary config")
    expected_x = (
        _finite(config.get("x_min"), label="config.x_min")
        + (np.arange(x.size) + 0.5)
        * (
            _finite(config.get("x_max"), label="config.x_max")
            - _finite(config.get("x_min"), label="config.x_min")
        )
        / x.size
    )
    expected_y = (
        _finite(config.get("y_min"), label="config.y_min")
        + (np.arange(y.size) + 0.5)
        * (
            _finite(config.get("y_max"), label="config.y_max")
            - _finite(config.get("y_min"), label="config.y_min")
        )
        / y.size
    )
    expected_z = np.asarray(config.get("full3d_reference_plane_z"), dtype=float)
    interface_indices = np.asarray(
        metadata.get("interface_plane_indices"),
        dtype=np.int64,
    )
    middle_indices = np.asarray(
        metadata.get("middle_plane_indices"),
        dtype=np.int64,
    )
    if (
        not np.array_equal(x, expected_x)
        or not np.array_equal(y, expected_y)
        or not np.array_equal(z, expected_z)
        or interface_indices.shape != (2,)
        or np.any(interface_indices < 0)
        or np.any(interface_indices >= z.size)
        or middle_indices.ndim != 1
        or middle_indices.size == 0
        or np.any(middle_indices < 0)
        or np.any(middle_indices >= z.size)
        or not np.array_equal(interface_z, z[interface_indices])
        or not np.array_equal(e_interface, e[interface_indices, :, :, :2])
        or not np.array_equal(h_interface, h[interface_indices, :, :, :2])
    ):
        raise ReferenceArtifactError("reference sample grid or interface slices differ")

    grid_payload = {
        "schema_version": "task035e.reference-sample-grid.v1",
        "x_nm": x.tolist(),
        "y_nm": y.tolist(),
        "z_nm": z.tolist(),
        "interface_z_nm": interface_z.tolist(),
        "interface_plane_indices": interface_indices.tolist(),
        "middle_plane_indices": middle_indices.tolist(),
        "components": list(metadata["components"]),
        "tangential_components": list(metadata["tangential_components"]),
        "electric_field_unit": metadata.get("electric_field_unit"),
        "magnetic_field_unit": metadata.get("magnetic_field_unit"),
        "grid_convention": metadata.get("grid_convention"),
    }
    grid_sha = _json_sha256(grid_payload)
    observations: list[ComplexObservation] = []

    def append_array(
        name: str,
        array: np.ndarray,
        *,
        category: str,
    ) -> None:
        for index in np.ndindex(array.shape):
            suffix = "/".join(f"i{axis}={value}" for axis, value in enumerate(index))
            observations.append(
                ComplexObservation(
                    name=f"{name}/{suffix}",
                    value=ComplexValue.from_complex(complex(array[index])),
                    category=category,
                )
            )

    append_array("interface/E_t", e_interface, category="interface_field")
    append_array("interface/H_t", h_interface, category="interface_field")
    append_array("volume/E", e[middle_indices], category="volume_field")
    append_array("volume/H", h[middle_indices], category="volume_field")
    return tuple(observations), grid_sha


def _completed_run(
    record_input: WatchdogRecordInput,
    *,
    expected_h_nm: float,
) -> AdaptedReferenceRun:
    (
        record,
        run_dir,
        task035e,
        config,
        source_sha,
        hashes,
    ) = _record_context(record_input, expected_h_nm=expected_h_nm)
    summary = _validate_completed_solver(record, run_dir, task035e, config, hashes)
    swap_bytes, headroom, _ = _validate_resource_gate(
        record,
        task035e,
        completed=True,
    )

    raw = _mapping(record.get("raw_evidence"), label="record.raw_evidence")
    dtn_path = _run_child(
        run_dir,
        summary.get("dtn_port_orders_json"),
        label="DtN orders",
    )
    if _resolve_repo_path(raw.get("dtn_orders"), label="raw DtN orders") != dtn_path:
        raise ReferenceArtifactError("record DtN path escaped its run directory")
    hashes["dtn_orders"] = _require_hash(
        dtn_path,
        record.get("dtn_orders_sha256"),
        label="DtN orders",
    )
    dtn = _load_json(dtn_path, label="DtN orders")
    orders = _order_observations(summary, dtn)

    volume_path = _run_child(
        run_dir,
        summary.get("volume_absorption_file"),
        label="volume absorption",
    )
    if (
        _resolve_repo_path(
            raw.get("volume_absorption"),
            label="raw volume absorption",
        )
        != volume_path
    ):
        raise ReferenceArtifactError(
            "record volume-absorption path escaped its run directory"
        )
    hashes["volume_absorption"] = _require_hash(
        volume_path,
        record.get("volume_absorption_sha256"),
        label="volume absorption",
    )
    volume = _load_json(volume_path, label="volume absorption")
    if (
        volume.get("method") != "volume_absorption"
        or volume.get("status") != "ok"
        or volume.get("power_source") != "volume_integral_Im_epsilon_E2"
    ):
        raise ReferenceArtifactError("volume absorption is not official")
    a_volume = _finite(
        volume.get("A_volume_total"),
        label="volume A_volume_total",
    )
    if not math.isclose(
        a_volume,
        _finite(summary.get("A_volume_total"), label="summary A_volume_total"),
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise ReferenceArtifactError("volume artifact and run summary differ")

    reference_metadata_path = _run_child(
        run_dir,
        "full3d_reference_samples.json",
        label="reference metadata",
    )
    if (
        _resolve_repo_path(
            raw.get("reference_metadata"),
            label="raw reference metadata",
        )
        != reference_metadata_path
    ):
        raise ReferenceArtifactError(
            "record reference-metadata path escaped its run directory"
        )
    complex_fields, grid_sha = _field_observations(
        run_dir,
        summary,
        hashes,
        expected_metadata_sha256=record.get("reference_metadata_sha256"),
    )
    r_total = _finite(summary.get("R_total"), label="R_total")
    t_total = _finite(summary.get("T_total"), label="T_total")
    a_closure = _finite(summary.get("A_balance"), label="A_balance")
    energy_total = r_total + t_total + a_volume
    energy_error = abs(energy_total - 1.0)
    closure_error = abs(a_closure - a_volume)
    recorded_energy = _finite(
        volume.get("energy_closure_error_port_volume"),
        label="volume energy closure",
    )
    if not math.isclose(
        recorded_energy,
        energy_error,
        rel_tol=0.0,
        abs_tol=5.0e-15,
    ):
        raise ReferenceArtifactError("recorded and recomputed energy errors differ")
    residual = _finite(
        summary.get("linear_system_relative_residual"),
        label="full explicit true residual",
    )
    if residual > 1.0e-9 or energy_error > 1.0e-9 or closure_error > 1.0e-9:
        raise ReferenceArtifactError("passed watchdog record violates residual/energy gates")

    totals = {
        "R00_s": _finite(summary.get("R00_s"), label="R00_s"),
        "R00_p": _finite(summary.get("R00_p"), label="R00_p"),
        "R00_total": _finite(summary.get("R00_total"), label="R00_total"),
        "R_total": r_total,
        "T_total": t_total,
        "A_closure": a_closure,
        "A_volume": a_volume,
        "energy_closure": energy_total,
    }
    scalars = tuple(
        ScalarObservation(name=name, value=value, category="total")
        for name, value in totals.items()
    ) + (
        ScalarObservation(
            name="A_volume_grating",
            value=_finite(
                volume.get("A_volume_grating"),
                label="A_volume_grating",
            ),
            category="diagnostic",
        ),
        ScalarObservation(
            name="A_volume_substrate",
            value=_finite(
                volume.get("A_volume_substrate"),
                label="A_volume_substrate",
            ),
            category="diagnostic",
        ),
    )
    evidence_sha = _json_sha256(
        {
            "schema_version": "task035e.reference-artifact-binding.v1",
            "artifacts": hashes,
        }
    )
    result = ReferenceRunResult(
        h_nm=expected_h_nm,
        identity=_physical_identity(config, source_sha),
        gate=RunGateEvidence(
            completed=True,
            full_explicit_true_residual=residual,
            energy_balance_error=energy_error,
            closure_volume_error=closure_error,
            official_postprocessing_passed=True,
            swap_peak_bytes=swap_bytes,
            minimum_memory_headroom_fraction=headroom,
        ),
        evidence_sha256=evidence_sha,
        scalar_observations=scalars,
        complex_observations=complex_fields,
        diffraction_orders=orders,
    )
    return AdaptedReferenceRun(
        result=result,
        normalized_config_sha256=_normalized_config_sha(config),
        sample_grid_sha256=grid_sha,
        artifact_sha256=dict(hashes),
    )


def _factorization_deny_run(
    decision_input: H5FactorizationDecisionInput,
    *,
    h10_input: WatchdogRecordInput,
    h7p5_input: WatchdogRecordInput,
) -> AdaptedReferenceRun:
    """Adapt only a resource DENY with otherwise valid h5 campaign identity."""

    decision_path = Path(decision_input.path).resolve()
    decision_file_sha = _require_hash(
        decision_path,
        decision_input.sha256,
        label="h5 factorization decision",
    )
    outer = _load_json(
        decision_path,
        label="h5 factorization decision",
    )
    if (
        set(outer) != {"schema_version", "sha256", "payload"}
        or outer.get("schema_version")
        != TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA
    ):
        raise ReferenceArtifactError(
            "h5 factorization decision outer schema differs"
        )
    payload = _mapping(
        outer.get("payload"),
        label="h5 factorization decision payload",
    )
    if (
        payload.get("schema_version")
        != TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA
        or outer.get("sha256") != _json_sha256(payload)
        or payload.get("authority_role")
        != "resource_launch_decision_only"
        or payload.get("credit")
        != "no_pde_no_accuracy_no_reference_qualification_credit"
    ):
        raise ReferenceArtifactError(
            "h5 factorization decision identity or self-hash differs"
        )
    target = _mapping(payload.get("target"), label="h5 decision target")
    if target != {
        "degree": 6,
        "h_nm": 5.0,
        "run_kind_to_authorize": "full-solve",
        "factor_solver": "mumps",
        "mpi_size": 8,
        "assembly_backend": STATIC_BACKEND,
        "profile": "default",
    }:
        raise ReferenceArtifactError("h5 factorization decision target differs")
    try:
        issued_at = datetime.fromisoformat(str(payload.get("issued_at_utc")))
        expires_at = datetime.fromisoformat(str(payload.get("expires_at_utc")))
    except ValueError as exc:
        raise ReferenceArtifactError(
            "h5 factorization decision validity timestamps are invalid"
        ) from exc
    if (
        issued_at.tzinfo is None
        or expires_at.tzinfo is None
        or payload.get("validity_seconds") != 15 * 60
        or (expires_at - issued_at).total_seconds() != 15 * 60
    ):
        raise ReferenceArtifactError(
            "h5 factorization decision validity window differs"
        )
    input_records = _mapping(
        payload.get("input_records"),
        label="h5 factorization decision inputs",
    )
    if set(input_records) != {"h10_full", "h7p5_full", "h5_assembly"}:
        raise ReferenceArtifactError(
            "h5 factorization decision input inventory differs"
        )
    for name, raw in input_records.items():
        row = _mapping(raw, label=f"h5 factorization input {name}")
        expected = row.get("expected_sha256")
        if (
            not isinstance(expected, str)
            or _SHA256_RE.fullmatch(expected) is None
            or row.get("observed_sha256") != expected
        ):
            raise ReferenceArtifactError(
                f"h5 factorization input {name} is not hash-bound"
            )
    for name, provided in (
        ("h10_full", h10_input),
        ("h7p5_full", h7p5_input),
    ):
        row = _mapping(
            input_records[name],
            label=f"h5 factorization input {name}",
        )
        recorded_path = _resolve_repo_path(
            row.get("path"),
            label=f"h5 factorization input {name} path",
        )
        if (
            row.get("expected_sha256") != provided.sha256
            or recorded_path != Path(provided.path).resolve()
        ):
            raise ReferenceArtifactError(
                f"h5 factorization decision does not bind supplied {name}"
            )
    h5_input = _mapping(
        input_records["h5_assembly"],
        label="h5 assembly input",
    )
    assembly_path = _resolve_repo_path(
        h5_input.get("path"),
        label="h5 assembly input path",
    )
    assembly_sha = str(h5_input["expected_sha256"])
    (
        assembly_record,
        _run_dir,
        task035e,
        config,
        source_sha,
        hashes,
    ) = _record_context(
        WatchdogRecordInput(assembly_path, assembly_sha),
        expected_h_nm=5.0,
    )
    qualification = _mapping(
        assembly_record.get("qualification"),
        label="h5 assembly qualification",
    )
    if not all(
        (
            assembly_record.get("run_kind") == "assembly-only",
            assembly_record.get("status")
            == "task035e_reference_assembly_resource_pass",
            assembly_record.get("controlled_resource_stop") is not True,
            assembly_record.get("no_swap") is True,
            qualification.get("pass") is True,
            qualification.get("failures") == [],
            task035e.get("credit") == "resource_only_not_physics",
        )
    ):
        raise ReferenceArtifactError(
            "h5 factorization decision does not bind a passed assembly preflight"
        )
    campaign = _mapping(
        payload.get("campaign_identity"),
        label="h5 decision campaign identity",
    )
    config_authority = _mapping(
        task035e.get("config_authority"),
        label="h5 assembly config authority",
    )
    if not all(
        (
            campaign.get("source_sha") == source_sha,
            campaign.get("h5_config_authority_sha256")
            == config_authority.get("sha256"),
            isinstance(campaign.get("physical_config_sha256"), str),
            _SHA256_RE.fullmatch(
                str(campaign.get("physical_config_sha256"))
            )
            is not None,
            _mapping(
                payload.get("identity_checks"),
                label="h5 decision identity checks",
            )
            == {
                "same_clean_source": True,
                "same_physical_config_except_mesh_h": True,
            },
        )
    ):
        raise ReferenceArtifactError(
            "h5 factorization decision campaign identity differs"
        )
    gate = _mapping(payload.get("gate"), label="h5 decision gate")
    failures = gate.get("failures")
    if (
        gate.get("launch_allowed") is not False
        or gate.get("deny_is_controlled_resource_stop") is not True
        or not isinstance(failures, list)
        or not failures
        or any(not isinstance(value, str) for value in failures)
        or any(
            not (
                value == "predicted_solver_peak_upper_not_below_dynamic_cap"
                or value.startswith("live_memory:")
            )
            for value in failures
        )
    ):
        raise ReferenceArtifactError(
            "h5 decision is not a resource-only controlled DENY"
        )
    memory = _mapping(payload.get("live_memory"), label="h5 decision memory")
    total = _integer(memory.get("mem_total_bytes"), label="decision MemTotal")
    available = _integer(
        memory.get("mem_available_bytes"),
        label="decision MemAvailable",
    )
    swap_used = _integer(
        memory.get("swap_used_bytes"),
        label="decision swap used",
    )
    if total <= 0 or available < 0 or swap_used < 0:
        raise ReferenceArtifactError("h5 decision resource snapshot is invalid")
    hashes.update(
        {
            "h5_factorization_decision": decision_file_sha,
            "h5_factorization_payload": str(outer["sha256"]),
        }
    )
    reason = "h5_factorization_prelaunch_denied:" + "|".join(failures)
    result = ReferenceRunResult(
        h_nm=5.0,
        identity=_physical_identity(config, source_sha),
        gate=RunGateEvidence(
            completed=False,
            full_explicit_true_residual=None,
            energy_balance_error=None,
            closure_volume_error=None,
            official_postprocessing_passed=False,
            swap_peak_bytes=swap_used,
            minimum_memory_headroom_fraction=available / total,
            controlled_resource_stop=True,
            failure_reason=reason,
        ),
        evidence_sha256=_json_sha256(
            {
                "schema_version": "task035e.reference-artifact-binding.v1",
                "artifacts": hashes,
                "controlled_resource_stop": reason,
            }
        ),
    )
    return AdaptedReferenceRun(
        result=result,
        normalized_config_sha256=_normalized_config_sha(config),
        sample_grid_sha256=None,
        artifact_sha256=dict(hashes),
    )


def _controlled_stop_run(
    record_input: WatchdogRecordInput,
    *,
    expected_h_nm: float,
) -> AdaptedReferenceRun:
    (
        record,
        _run_dir,
        task035e,
        config,
        source_sha,
        hashes,
    ) = _record_context(record_input, expected_h_nm=expected_h_nm)
    if expected_h_nm != 5.0:
        raise ReferenceArtifactError("only the formal h5 point may be incomplete")
    swap_bytes, headroom, reason = _validate_resource_gate(
        record,
        task035e,
        completed=False,
    )
    assert reason is not None
    result = ReferenceRunResult(
        h_nm=expected_h_nm,
        identity=_physical_identity(config, source_sha),
        gate=RunGateEvidence(
            completed=False,
            full_explicit_true_residual=None,
            energy_balance_error=None,
            closure_volume_error=None,
            official_postprocessing_passed=False,
            swap_peak_bytes=swap_bytes,
            minimum_memory_headroom_fraction=headroom,
            controlled_resource_stop=True,
            failure_reason=reason,
        ),
        evidence_sha256=_json_sha256(
            {
                "schema_version": "task035e.reference-artifact-binding.v1",
                "artifacts": hashes,
                "controlled_resource_stop": reason,
            }
        ),
    )
    return AdaptedReferenceRun(
        result=result,
        normalized_config_sha256=_normalized_config_sha(config),
        sample_grid_sha256=None,
        artifact_sha256=dict(hashes),
    )


def adapt_watchdog_reference(
    record_input: WatchdogRecordInput,
    *,
    expected_h_nm: float,
) -> AdaptedReferenceRun:
    """Load one full reference result, or the formal h5 controlled stop."""

    record_path = Path(record_input.path).resolve()
    record = _load_json(record_path, label="watchdog record")
    if record.get("status") == "controlled_resource_stop":
        return _controlled_stop_run(
            record_input,
            expected_h_nm=expected_h_nm,
        )
    return _completed_run(record_input, expected_h_nm=expected_h_nm)


def build_reference_campaign_from_watchdogs(
    *,
    h10: WatchdogRecordInput,
    h7p5: WatchdogRecordInput,
    h5: WatchdogRecordInput | H5FactorizationDecisionInput,
) -> ReferenceCampaign:
    """Build the typed campaign after exact cross-point identity checks."""

    adapted = (
        adapt_watchdog_reference(h10, expected_h_nm=10.0),
        adapt_watchdog_reference(h7p5, expected_h_nm=7.5),
        (
            _factorization_deny_run(
                h5,
                h10_input=h10,
                h7p5_input=h7p5,
            )
            if isinstance(h5, H5FactorizationDecisionInput)
            else adapt_watchdog_reference(h5, expected_h_nm=5.0)
        ),
    )
    if len({row.normalized_config_sha256 for row in adapted}) != 1:
        raise ReferenceArtifactError(
            "h10/h7.5/h5 configs differ beyond case name and actual mesh"
        )
    identities = {row.result.identity for row in adapted}
    if len(identities) != 1:
        raise ReferenceArtifactError(
            "source/geometry/material/incident/DtN/postprocess identity differs"
        )
    completed_grids = {
        row.sample_grid_sha256
        for row in adapted
        if row.result.gate.completed
    }
    if len(completed_grids) != 1:
        raise ReferenceArtifactError(
            "completed reference points do not share the exact sample grid"
        )
    return ReferenceCampaign(
        h10=adapted[0].result,
        h7p5=adapted[1].result,
        h5=adapted[2].result,
    )


def _safe_summary(certification: Any, receipt: Any | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": "task035e.reference-certify-cli-result.v1",
        "status": certification.status,
        "qualified": certification.qualified,
        "reasons": list(certification.reasons),
        "gates": {
            name: bool(getattr(certification.gates, name))
            for name in certification.gates.__dataclass_fields__
        },
        "observable_count": len(certification.convergence),
        "run_evidence_sha256": [
            run.evidence_sha256 for run in certification.campaign.runs
        ],
        "physical_values_emitted": False,
    }
    if receipt is not None:
        summary["sealed_package"] = {
            "path": str(receipt.path),
            "file_sha256": _file_sha256(Path(receipt.path)),
            "sealed_payload_sha256": receipt.sealed_payload_sha256,
            "campaign_binding_sha256": receipt.campaign_binding_sha256,
            "byte_count": receipt.byte_count,
            "qualified": receipt.qualified,
        }
    return summary


def _assert_hidden_destination(path: Path) -> None:
    resolved = path.resolve()
    forbidden = (ROOT / "src" / "adaptivity" / "blind_controller").resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        raise ReferenceArtifactError(
            "sealed reference output cannot be written into blind_controller"
        )
    if any(part.lower() == "blind_controller" for part in resolved.parts):
        raise ReferenceArtifactError(
            "sealed reference output path contains blind_controller"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("h10", "h7p5"):
        parser.add_argument(f"--{label}-record", type=Path, required=True)
        parser.add_argument(f"--{label}-record-sha256", required=True)
    h5_source = parser.add_mutually_exclusive_group(required=True)
    h5_source.add_argument("--h5-record", type=Path)
    h5_source.add_argument("--h5-factorization-decision", type=Path)
    parser.add_argument("--h5-record-sha256")
    parser.add_argument("--h5-factorization-decision-sha256")
    parser.add_argument("--sealed-package", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and certify in memory without writing a package",
    )
    parser.add_argument(
        "--seal-incomplete-evidence",
        action="store_true",
        help=(
            "explicitly preserve an incomplete controlled-resource campaign; "
            "the command still exits nonzero"
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    h5_watchdog_selected = args.h5_record is not None
    if h5_watchdog_selected != bool(args.h5_record_sha256):
        raise SystemExit(
            "--h5-record and --h5-record-sha256 must be provided together"
        )
    h5_decision_selected = args.h5_factorization_decision is not None
    if h5_decision_selected != bool(
        args.h5_factorization_decision_sha256
    ):
        raise SystemExit(
            "--h5-factorization-decision and its SHA-256 must be provided "
            "together"
        )
    if h5_watchdog_selected and args.h5_factorization_decision_sha256:
        raise SystemExit(
            "h5 watchdog and factorization-decision inputs are mutually exclusive"
        )
    if h5_decision_selected and args.h5_record_sha256:
        raise SystemExit(
            "h5 watchdog and factorization-decision inputs are mutually exclusive"
        )
    if args.check and args.seal_incomplete_evidence:
        raise SystemExit(
            "--seal-incomplete-evidence cannot be combined with --check"
        )
    if not args.check and args.sealed_package is None:
        raise SystemExit("--sealed-package is required unless --check is used")
    campaign = build_reference_campaign_from_watchdogs(
        h10=WatchdogRecordInput(args.h10_record, args.h10_record_sha256),
        h7p5=WatchdogRecordInput(args.h7p5_record, args.h7p5_record_sha256),
        h5=(
            WatchdogRecordInput(args.h5_record, args.h5_record_sha256)
            if h5_watchdog_selected
            else H5FactorizationDecisionInput(
                args.h5_factorization_decision,
                args.h5_factorization_decision_sha256,
            )
        ),
    )
    certifier = ReferenceCertifier()
    certification = certifier.certify(campaign)
    receipt = None
    if args.check:
        pass
    elif certification.qualified:
        destination = Path(args.sealed_package)
        _assert_hidden_destination(destination)
        result = certifier.certify_and_seal(
            campaign,
            destination,
            seal_incomplete_evidence=False,
            overwrite=args.overwrite,
        )
        certification = result.certification
        receipt = result.receipt
    elif (
        certification.status == REFERENCE_CERTIFICATION_INCOMPLETE
        and args.seal_incomplete_evidence
    ):
        destination = Path(args.sealed_package)
        _assert_hidden_destination(destination)
        result = certifier.certify_and_seal(
            campaign,
            destination,
            seal_incomplete_evidence=True,
            overwrite=args.overwrite,
        )
        certification = result.certification
        receipt = result.receipt
    elif args.seal_incomplete_evidence:
        raise SystemExit(
            "--seal-incomplete-evidence applies only to an incomplete "
            "controlled-resource campaign"
        )
    else:
        receipt = None
    print(
        json.dumps(
            _safe_summary(certification, receipt),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    if certification.qualified:
        return 0
    if certification.status == REFERENCE_CERTIFICATION_INCOMPLETE:
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AdaptedReferenceRun",
    "H5FactorizationDecisionInput",
    "NORMALIZATION_IDENTITY",
    "ReferenceArtifactError",
    "WatchdogRecordInput",
    "adapt_watchdog_reference",
    "build_reference_campaign_from_watchdogs",
]
