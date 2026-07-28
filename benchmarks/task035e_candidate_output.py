#!/usr/bin/env python3
"""Build one hash-bound Task035e current or shadow output payload.

The adapter consumes only one qualified blind solve's watchdog record and raw
artifacts.  It has no evaluator-side imports and never opens a sealed package.
The requested current/p-shadow/h-shadow role must match the watchdog authority.
Physical values are written only to the requested mode-0600 output; stdout
contains provenance hashes and status.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_SCHEMA = "task033.full3d-watchdog.v1"
WATCHDOG_BENCHMARK_ID = "task033_target_full3d_watchdog"
CANDIDATE_AUTHORITY_SCHEMA = "task035e.blind-current-solve-authority.v1"
CANDIDATE_OUTPUT_SCHEMA = "task035e.frozen-candidate-outputs.v1"
CANDIDATE_OUTPUT_STATUS = "task035e_blind_candidate_full_solve_pass"
CANDIDATE_BACKEND = "assembly_time_variable_p_condensed"
CANDIDATE_OUTPUT_ROLES = {
    "current": "blind_current_solve",
    "p-shadow": "blind_p_shadow_solve",
    "h-shadow": "blind_h_shadow_solve",
}
FIXED_PORTS = ("top", "bottom")
FIXED_M = (0, -1, -2, -3, -4, -5, -6, -7)
FIXED_N = 0
FIXED_ORDER_KEYS = tuple(
    (port, m, FIXED_N) for port in FIXED_PORTS for m in FIXED_M
)
FORMAL_FIELD_SCALAR_NAMES = (
    "interface_probe_l2",
    "volume_probe_l2",
)
FORMAL_FIELD_COMPLEX_NAMES = (
    "interface_probe_complex",
    "volume_probe_complex",
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_EVALUATOR_CONSUMED_KEY = "hidden_" + "reference_consumed"
_EVALUATOR_CAMPAIGN_KEY = "task035e_ref" + "erence_certifier"
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
_CANDIDATE_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "selected",
        "output_role",
        "trial_id",
        "cycle_index",
        "source_sha",
        "config_sha256",
    }
)
_OUTPUT_KEYS = frozenset(
    {
        "schema_version",
        "orders",
        "scalar_observations",
        "complex_observations",
        "full_explicit_true_residual",
    }
)


class CandidateOutputError(ValueError):
    """Raised when blind-solve evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class CandidateWatchdogInput:
    """One watchdog record plus an independently supplied byte hash."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise CandidateOutputError("watchdog path must use pathlib.Path")
        if not isinstance(self.sha256, str) or _SHA256_RE.fullmatch(
            self.sha256
        ) is None:
            raise CandidateOutputError(
                "watchdog SHA-256 must be 64 lowercase hexadecimal characters"
            )


@dataclass(frozen=True, slots=True)
class AdaptedCandidateOutput:
    """Candidate payload plus the provenance needed by the later freeze step."""

    payload: Mapping[str, Any]
    output_sha256: str
    record_sha256: str
    source_sha: str
    config_sha256: str
    trial_id: str
    cycle_index: int
    output_role: str
    plan_path: Path
    plan_file_sha256: str
    forest_leaf_catalog_sha256: str
    carrier_connectivity_sha256: str
    mesh_cell_box_catalog_sha256: str
    cell_degree_plan_sha256: str
    geometry_canonical_entity_degree_sha256: str
    structural_inventory: Mapping[str, int]
    artifact_sha256: Mapping[str, str]
    live_role_evidence: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class CandidateOutputWriteReceipt:
    """Non-physical receipt for one atomically written candidate output."""

    path: Path
    output_sha256: str
    byte_count: int
    source_sha: str
    config_sha256: str
    trial_id: str
    cycle_index: int
    output_role: str


@dataclass(frozen=True, slots=True)
class _CandidateProvenance:
    plan_path: Path
    plan_file_sha256: str
    forest_leaf_catalog_sha256: str
    carrier_connectivity_sha256: str
    mesh_cell_box_catalog_sha256: str
    cell_degree_plan_sha256: str
    geometry_canonical_entity_degree_sha256: str
    structural_inventory: Mapping[str, int]
    live_role_evidence: Mapping[str, Any] | None


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


def _namespaced_json_sha256(value: Mapping[str, Any], *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def candidate_config_sha256(config: Mapping[str, Any]) -> str:
    """Return the config identity written into the blind-run authority."""

    return _json_sha256(
        {
            "schema_version": "task035e.blind-current-config.v1",
            "config": _canonical(config),
        }
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateOutputError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CandidateOutputError(f"{label} must be a JSON array")
    return value


def _exact_keys(
    value: Any,
    expected: frozenset[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    row = _mapping(value, label=label)
    observed = set(row)
    if observed != expected:
        raise CandidateOutputError(
            f"{label} keys differ; "
            f"missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )
    return row


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateOutputError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise CandidateOutputError(f"{label} must be finite")
    return result


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CandidateOutputError(f"{label} must be an integer")
    return int(value)


def _positive_integral_number(value: Any, *, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        or not float(value).is_integer()
    ):
        raise CandidateOutputError(f"{label} must be a positive exact integer")
    return int(value)


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CandidateOutputError(
            f"{label} must be 64 lowercase hexadecimal characters"
        )
    return value


def _complex(value: Any, *, label: str) -> complex:
    row = _sequence(value, label=label)
    if len(row) != 2:
        raise CandidateOutputError(f"{label} must contain [real, imag]")
    return complex(
        _finite(row[0], label=f"{label}[0]"),
        _finite(row[1], label=f"{label}[1]"),
    )


def _complex_payload(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _load_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateOutputError(f"cannot read {label}: {path}") from error
    return _mapping(value, label=label)


def _resolve_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CandidateOutputError(f"{label} must be a nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def _run_child(run_dir: Path, name: Any, *, label: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise CandidateOutputError(f"{label} must be one plain file name")
    path = (run_dir / name).resolve()
    if path.parent != run_dir:
        raise CandidateOutputError(f"{label} escapes the run directory")
    return path


def _require_hash(path: Path, expected: Any, *, label: str) -> str:
    if not path.is_file():
        raise CandidateOutputError(f"{label} is missing: {path}")
    if not isinstance(expected, str) or _SHA256_RE.fullmatch(expected) is None:
        raise CandidateOutputError(f"{label} lacks a valid expected SHA-256")
    observed = _file_sha256(path)
    if observed != expected:
        raise CandidateOutputError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {observed}"
        )
    return observed


def _same(left: Any, right: Any) -> bool:
    return _canonical(left) == _canonical(right)


def _record_context(
    record_input: CandidateWatchdogInput,
    *,
    output_role: str,
) -> tuple[
    Mapping[str, Any],
    Path,
    Mapping[str, Any],
    Mapping[str, Any],
    str,
    str,
    dict[str, str],
]:
    expected_authority_role = CANDIDATE_OUTPUT_ROLES.get(output_role)
    if expected_authority_role is None:
        raise CandidateOutputError(
            "output role must be current, p-shadow, or h-shadow"
        )
    record_path = record_input.path.resolve()
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
        raise CandidateOutputError("watchdog record is not the Full3D authority")
    if (
        record.get("status") != CANDIDATE_OUTPUT_STATUS
        or record.get("degree") != 6
        or record.get("h_nm") not in {20.0, 15.0}
        or record.get("run_kind") != "full-solve"
        or record.get("polarization_kind") != "s"
        or record.get("mpi_size") != 8
        or record.get("profile") != "default"
        or record.get("stage4_full3d_assembly_backend_requested")
        != CANDIDATE_BACKEND
        or record.get("stage4_full3d_assembly_backend_actual")
        != CANDIDATE_BACKEND
        or record.get("controlled_resource_stop") is not False
        or record.get("return_code") != 0
        or record.get("terminated_for_memory") is not False
        or record.get("terminated_for_timeout") is not False
    ):
        raise CandidateOutputError(
            "candidate needs a completed MPI8 variable-p Full3D blind solve"
        )
    if record.get(_EVALUATOR_CAMPAIGN_KEY) is not None:
        raise CandidateOutputError(
            "evaluator campaign records cannot become blind candidate outputs"
        )
    qualification = _mapping(
        record.get("qualification"),
        label="record.qualification",
    )
    if (
        qualification.get("pass") is not True
        or qualification.get("failures") != []
    ):
        raise CandidateOutputError("watchdog qualification did not pass")

    source = _mapping(record.get("source"), label="record.source")
    source_sha = source.get("commit_sha")
    if not isinstance(source_sha, str) or _SOURCE_SHA_RE.fullmatch(
        source_sha
    ) is None:
        raise CandidateOutputError("candidate source commit is not a full SHA")
    if not all(
        (
            source.get("head_after_sha") == source_sha,
            source.get("tracked_source_dirty") is False,
            source.get("stable_and_clean_after") is True,
            source.get("status_after") == "",
        )
    ):
        raise CandidateOutputError("candidate source was not stable and clean")

    authority = _exact_keys(
        record.get("task035e_blind_candidate"),
        _CANDIDATE_AUTHORITY_KEYS,
        label="record.task035e_blind_candidate",
    )
    if (
        authority["schema_version"] != CANDIDATE_AUTHORITY_SCHEMA
        or authority["selected"] is not True
        or authority["output_role"] != expected_authority_role
        or authority["source_sha"] != source_sha
        or not isinstance(authority["trial_id"], str)
        or not authority["trial_id"]
        or isinstance(authority["cycle_index"], bool)
        or not isinstance(authority["cycle_index"], int)
        or not 0 <= int(authority["cycle_index"]) <= 5
    ):
        raise CandidateOutputError("blind candidate authority is invalid")

    raw = _mapping(record.get("raw_evidence"), label="record.raw_evidence")
    run_dir = _resolve_path(
        raw.get("run_directory"),
        label="record.raw_evidence.run_directory",
    )
    if not run_dir.is_dir():
        raise CandidateOutputError(f"run directory is missing: {run_dir}")
    summary_path = _run_child(run_dir, "run_summary.json", label="run summary")
    if (
        _resolve_path(raw.get("solver_summary"), label="raw solver summary")
        != summary_path
    ):
        raise CandidateOutputError("solver-summary path escaped the run directory")
    summary_sha = _require_hash(
        summary_path,
        record.get("solver_summary_sha256"),
        label="run summary",
    )
    summary = _load_json(summary_path, label="run summary")
    if not _same(record.get("solver_summary"), summary):
        raise CandidateOutputError("embedded and on-disk summaries differ")
    config = _mapping(summary.get("config"), label="run summary config")
    config_sha = candidate_config_sha256(config)
    if authority["config_sha256"] != config_sha:
        raise CandidateOutputError("blind candidate config SHA-256 mismatch")
    return (
        record,
        run_dir,
        summary,
        config,
        source_sha,
        config_sha,
        {
            "watchdog_record": record_sha,
            "run_summary": summary_sha,
        },
    )


def _validate_solver_summary(
    record: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    petsc = _mapping(
        summary.get("linear_solve_petsc_options"),
        label="run summary PETSc options",
    )
    backend = _mapping(
        summary.get("stage4_full3d_assembly_backend_qualification"),
        label="static backend qualification",
    )
    condensation = _mapping(
        summary.get("cell_static_condensation"),
        label="static condensation audit",
    )
    if not all(
        (
            summary.get("case_status") == "completed",
            summary.get("official_result") is True,
            summary.get("diagnostic_only") is False,
            summary.get("postprocess_skipped") is False,
            summary.get("polarization_kind") == "s",
            summary.get("mpi_size") == 8,
            summary.get("stage4_full3d_assembly_backend_actual")
            == CANDIDATE_BACKEND,
            summary.get("stage4_assembly_time_cell_static_condensation")
            is True,
            backend.get("status") == "qualified",
            condensation.get("full_p6_global_matrix_allocated") is False,
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
            record.get("no_swap") is True,
        )
    ):
        raise CandidateOutputError(
            "run summary is not an official variable-p direct-MUMPS MPI8 solve"
        )


def _passed_gate(
    value: Any,
    *,
    label: str,
    schema_version: str,
) -> Mapping[str, Any]:
    gate = _mapping(value, label=label)
    checks = _mapping(gate.get("checks"), label=f"{label}.checks")
    if (
        gate.get("schema_version") != schema_version
        or gate.get("pass") is not True
        or gate.get("failures") != []
        or not checks
        or any(passed is not True for passed in checks.values())
    ):
        raise CandidateOutputError(f"{label} did not pass exactly")
    return gate


def _candidate_provenance(
    record: Mapping[str, Any],
    run_dir: Path,
    summary: Mapping[str, Any],
    hashes: dict[str, str],
) -> _CandidateProvenance:
    """Extract identities and measurements only from qualified run evidence."""

    launch = _mapping(
        record.get("task035e_blind_candidate_launch_gate"),
        label="record.task035e_blind_candidate_launch_gate",
    )
    if (
        launch.get("schema_version")
        != "task035e.blind-candidate-launch-gate.v1"
        or launch.get("selected") is not True
    ):
        raise CandidateOutputError(
            "blind candidate launch authority is missing or invalid"
        )
    plan_gate = _passed_gate(
        launch.get("plan"),
        label="blind candidate plan gate",
        schema_version=(
            "task035e.blind-multilevel-plan-authority-gate.v1"
        ),
    )
    _passed_gate(
        launch.get("solver"),
        label="blind candidate solver gate",
        schema_version="task035e.blind-candidate-solver-gate.v1",
    )
    artifact_gate = _passed_gate(
        launch.get("artifacts"),
        label="blind candidate artifact gate",
        schema_version="task035e.blind-candidate-artifact-gate.v1",
    )
    resource_policy = _mapping(
        launch.get("resource_policy"),
        label="blind candidate resource policy",
    )
    live_resource = _mapping(
        launch.get("live_resource_gate"),
        label="blind candidate live resource gate",
    )
    if (
        resource_policy.get("schema_version")
        != "task035e.blind-candidate-resource-policy.v1"
        or resource_policy.get("pass") is not True
        or live_resource.get("schema_version")
        != "task035e.blind-candidate-live-resource-gate.v1"
        or live_resource.get("pass") is not True
        or live_resource.get("controlled_resource_stop") is not False
        or live_resource.get("stop_reason") is not None
        or live_resource.get("zero_swap_every_sample") is not True
        or live_resource.get("maximum_swap_authority_bytes") != 0
        or live_resource.get("memory_cap_at_most_11_gib") is not True
        or live_resource.get("policy") != resource_policy
    ):
        raise CandidateOutputError(
            "blind candidate live resource authority is invalid"
        )

    expected_plan_sha = _sha256(
        plan_gate.get("expected_file_sha256"),
        label="plan gate expected file SHA-256",
    )
    if (
        _sha256(
            plan_gate.get("observed_file_sha256"),
            label="plan gate observed file SHA-256",
        )
        != expected_plan_sha
    ):
        raise CandidateOutputError("blind plan expected and observed hashes differ")
    plan_path = _resolve_path(
        plan_gate.get("path"),
        label="blind candidate plan path",
    )
    hashes["blind_plan"] = _require_hash(
        plan_path,
        expected_plan_sha,
        label="blind candidate plan",
    )
    plan = _load_json(plan_path, label="blind candidate plan")
    authority = _mapping(
        record.get("task035e_blind_candidate"),
        label="record.task035e_blind_candidate",
    )
    live_reference_raw = artifact_gate.get("blind_live_role_evidence")
    live_reference: dict[str, str] | None = None
    artifact_checks = _mapping(
        artifact_gate.get("checks"),
        label="blind candidate artifact checks",
    )
    if live_reference_raw is None and artifact_checks != {
        "fixture_authority": True
    }:
        raise CandidateOutputError(
            "formal blind candidate artifact gate lacks live-role evidence"
        )
    if live_reference_raw is not None:
        live_reference_row = _exact_keys(
            live_reference_raw,
            frozenset(
                {
                    "role",
                    "path",
                    "sha256",
                    "schema_version",
                    "status",
                    "independent_gate",
                }
            ),
            label="blind live-role evidence reference",
        )
        role_by_authority = {
            "blind_current_solve": "current",
            "blind_p_shadow_solve": "p-shadow",
            "blind_h_shadow_solve": "h-shadow",
        }
        live_role = role_by_authority.get(authority.get("output_role"))
        if live_role is None or live_reference_row["role"] != live_role:
            raise CandidateOutputError(
                "blind live-role evidence role differs from solve authority"
            )
        independent_gate = _mapping(
            live_reference_row["independent_gate"],
            label="blind live-role independent replay gate",
        )
        independent_checks = _mapping(
            independent_gate.get("checks"),
            label="blind live-role independent replay checks",
        )
        independent_details = _mapping(
            independent_gate.get("details"),
            label="blind live-role independent replay details",
        )
        if (
            independent_gate.get("schema_version")
            != "task035e.blind-live-role-evidence-gate.v1"
            or independent_gate.get("pass") is not True
            or independent_gate.get("failures") != []
            or not independent_checks
            or not all(value is True for value in independent_checks.values())
            or independent_details.get("role") != live_role
        ):
            raise CandidateOutputError(
                "blind live-role evidence did not pass independent replay"
            )
        expected_live_path = (
            run_dir / "task035e_current_snapshot" / "manifest.json"
            if live_role == "current"
            else run_dir
            / f"task035e_{live_role.replace('-', '_')}_evaluation.json"
        ).resolve()
        live_path = _resolve_path(
            live_reference_row["path"],
            label="blind live-role evidence path",
        )
        if live_path != expected_live_path:
            raise CandidateOutputError(
                "blind live-role evidence escaped its qualified run directory"
            )
        live_sha = _require_hash(
            live_path,
            live_reference_row["sha256"],
            label="blind live-role evidence",
        )
        if (live_path.stat().st_mode & 0o777) != 0o600:
            raise CandidateOutputError(
                "blind live-role evidence must be immutable mode 0600"
            )
        live_payload = _load_json(
            live_path,
            label="blind live-role evidence",
        )
        expected_schema = (
            "task035e.multigoal-current-live-snapshot.v1"
            if live_role == "current"
            else "task035e.live-shadow-evaluation.v1"
        )
        expected_status = (
            "multigoal_current_live_snapshot_pass"
            if live_role == "current"
            else "live_shadow_59_goal_actual_dwr_pass"
        )
        if (
            live_reference_row["schema_version"] != expected_schema
            or live_reference_row["status"] != expected_status
            or live_payload.get("schema_version") != expected_schema
            or live_payload.get("status") != expected_status
            or live_payload.get("pass") is not True
            or live_payload.get("source_sha") != authority.get("source_sha")
            or live_payload.get("trial_id") != authority.get("trial_id")
            or live_payload.get("cycle_index") != authority.get("cycle_index")
            or live_payload.get("mpi_size") != 8
            or live_payload.get("formal_mpi8_qualified") is not True
            or live_payload.get("ordinary_default_changed") is not False
        ):
            raise CandidateOutputError(
                "blind live-role evidence identity or qualification differs"
            )
        if live_role == "current":
            stored_payload_sha = _sha256(
                live_payload.get("manifest_payload_sha256"),
                label="current live snapshot payload SHA-256",
            )
            unsigned_live = dict(live_payload)
            unsigned_live.pop("manifest_payload_sha256")
            observed_payload_sha = _namespaced_json_sha256(
                unsigned_live,
                namespace="task035e.multigoal-current-manifest.v1",
            )
            plan_identity = _mapping(
                live_payload.get("plan_identity"),
                label="current live snapshot plan identity",
            )
            role_specific_identity = (
                live_payload.get("role") == "current_blind_state"
                and plan_identity.get("file_sha256") == expected_plan_sha
            )
        else:
            stored_payload_sha = _sha256(
                live_payload.get("payload_sha256"),
                label="shadow live evaluation payload SHA-256",
            )
            unsigned_live = dict(live_payload)
            unsigned_live.pop("payload_sha256")
            observed_payload_sha = _namespaced_json_sha256(
                unsigned_live,
                namespace="task035e.live-shadow-evaluation-payload.v1",
            )
            role_specific_identity = (
                live_payload.get("shadow_kind") == live_role
                and live_payload.get("shadow_plan_file_sha256")
                == expected_plan_sha
                and live_payload.get(_EVALUATOR_CONSUMED_KEY) is False
                and live_payload.get("endpoint_delta_used_as_dwr") is False
            )
        if (
            stored_payload_sha != observed_payload_sha
            or not role_specific_identity
        ):
            raise CandidateOutputError(
                "blind live-role evidence self-hash or plan identity differs"
            )
        hashes["blind_live_role_evidence"] = live_sha
        live_reference = {
            "role": str(live_role),
            "path": str(live_path),
            "sha256": live_sha,
            "schema_version": str(expected_schema),
            "status": str(expected_status),
            "payload_sha256": stored_payload_sha,
            "independent_gate_sha256": _json_sha256(independent_gate),
        }

    local_h = _mapping(
        summary.get("stage4_local_h_constraint_audit"),
        label="run summary local-h authority",
    )
    mesh = _mapping(local_h.get("mesh"), label="local-h mesh authority")
    forest = _mapping(mesh.get("forest"), label="local-h forest authority")
    carrier = _mapping(mesh.get("carrier"), label="local-h carrier authority")
    degree = _mapping(
        local_h.get("degree_plan"),
        label="local-h degree-plan authority",
    )
    if (
        local_h.get("schema_version")
        != "task035e.stage4-multilevel-local-hp-reduction-authority.v1"
        or local_h.get("status")
        != "stage4_local_h_reduction_authority_pass"
        or local_h.get("pass") is not True
        or mesh.get("schema_version")
        != "task035e.stage4-multilevel-local-h-mesh.v1"
        or mesh.get("status")
        != "stage4_balanced_multilevel_local_h_mesh_pass"
        or mesh.get("pass") is not True
        or forest.get("schema_version")
        != "task035d.dyadic-hexa-forest.v1"
        or forest.get("pass") is not True
        or carrier.get("schema_version")
        != "task035d.broken-dyadic-hexa-carrier.v1"
        or carrier.get("pass") is not True
        or degree.get("schema_version")
        != "task035e.local-h-variable-exact-sequence-plan.v1"
        or degree.get("status")
        != "local_h_variable_exact_sequence_plan_closed"
        or degree.get("pass") is not True
    ):
        raise CandidateOutputError(
            "executed local-h/p identities are not qualified"
        )
    if (
        _resolve_path(mesh.get("plan_path"), label="executed plan path")
        != plan_path
        or _sha256(
            mesh.get("plan_file_sha256"),
            label="executed plan SHA-256",
        )
        != expected_plan_sha
    ):
        raise CandidateOutputError(
            "executed plan path or SHA-256 differs from launch authority"
        )

    forest_sha = _sha256(
        forest.get("leaf_catalog_sha256"),
        label="forest leaf-catalog SHA-256",
    )
    carrier_leaf_sha = _sha256(
        carrier.get("leaf_catalog_sha256"),
        label="carrier leaf-catalog SHA-256",
    )
    carrier_connectivity_sha = _sha256(
        carrier.get("canonical_connectivity_sha256"),
        label="carrier connectivity SHA-256",
    )
    mesh_box_sha = _sha256(
        degree.get("mesh_cell_box_catalog_sha256"),
        label="mesh cell-box catalog SHA-256",
    )
    cell_degree_sha = _sha256(
        degree.get("cell_degree_plan_sha256"),
        label="cell-degree plan SHA-256",
    )
    entity_degree_sha = _sha256(
        degree.get("geometry_canonical_entity_degree_sha256"),
        label="geometry entity-degree SHA-256",
    )
    expected_forest = _mapping(
        plan.get("expected_forest"),
        label="blind plan expected forest",
    )
    if (
        carrier_leaf_sha != forest_sha
        or _sha256(
            expected_forest.get("leaf_catalog_sha256"),
            label="plan leaf-catalog SHA-256",
        )
        != forest_sha
        or _sha256(
            plan.get("cell_interior_degree_plan_sha256"),
            label="plan cell-degree SHA-256",
        )
        != cell_degree_sha
        or _sha256(
            mesh.get("cell_interior_degree_plan_sha256"),
            label="mesh cell-degree SHA-256",
        )
        != cell_degree_sha
        or plan_gate.get("base_config_identity_sha256")
        != mesh.get("base_config_identity_sha256")
    ):
        raise CandidateOutputError(
            "plan, forest, carrier, and degree-map identities differ"
        )

    raw_active_dofs = _positive_integral_number(
        summary.get("num_raw_broken_active_fe_dofs"),
        label="run summary raw active FE DoFs",
    )
    active_dofs = _positive_integral_number(
        summary.get("num_actual_conforming_active_fe_dofs"),
        label="run summary conforming active FE DoFs",
    )
    if (
        _positive_integral_number(
            degree.get("active_rows"),
            label="degree-plan active rows",
        )
        != raw_active_dofs
        or active_dofs > raw_active_dofs
    ):
        raise CandidateOutputError("active FE DoF inventories differ")

    matrix = _mapping(summary.get("matrix_stats"), label="matrix stats")
    matrix_rows = _positive_integral_number(
        matrix.get("matrix_rows"),
        label="matrix rows",
    )
    if (
        _positive_integral_number(
            matrix.get("matrix_cols"),
            label="matrix columns",
        )
        != matrix_rows
    ):
        raise CandidateOutputError("candidate matrix is not square")
    matrix_nnz = _positive_integral_number(
        matrix.get("matrix_nnz_used"),
        label="matrix NNZ",
    )
    factor = _mapping(
        summary.get("stage4_dtn_factor_inventory"),
        label="MUMPS factor inventory",
    )
    factor_matrix = _mapping(
        factor.get("matrix_stats"),
        label="MUMPS factor matrix stats",
    )
    factor_nnz = _positive_integral_number(
        factor_matrix.get("matrix_nnz_used"),
        label="factor NNZ",
    )
    if (
        factor.get("available") is not True
        or factor.get("factor_solver_type") != "mumps"
        or _positive_integral_number(
            factor_matrix.get("matrix_rows"),
            label="factor rows",
        )
        != matrix_rows
    ):
        raise CandidateOutputError("MUMPS factor inventory is invalid")

    calibration = _mapping(
        record.get("calibration"),
        label="watchdog calibration",
    )
    matrix_inventory = _mapping(
        record.get("matrix_inventory"),
        label="watchdog matrix inventory",
    )
    if (
        _positive_integral_number(
            calibration.get("exact_rows"),
            label="watchdog exact rows",
        )
        != matrix_rows
        or _positive_integral_number(
            calibration.get("exact_assembled_nnz"),
            label="watchdog exact assembled NNZ",
        )
        != matrix_nnz
        or calibration.get("factorization_or_solve_stage_seen") is not True
        or not _same(matrix_inventory.get("final"), matrix)
    ):
        raise CandidateOutputError(
            "watchdog and embedded structural inventories differ"
        )
    solver_peak_bytes = _positive_integral_number(
        live_resource.get("maximum_job_memory_authority_bytes"),
        label="solver lifecycle peak bytes",
    )
    effective_cap = _positive_integral_number(
        resource_policy.get("effective_job_cap_bytes"),
        label="blind resource cap bytes",
    )
    if (
        solver_peak_bytes >= effective_cap
        or effective_cap > 11 * 1024**3
        or live_resource.get("effective_job_cap_respected") is not True
        or live_resource.get("minimum_headroom_20_percent_preserved")
        is not True
    ):
        raise CandidateOutputError(
            "solver lifecycle peak violates the qualified resource envelope"
        )

    return _CandidateProvenance(
        plan_path=plan_path,
        plan_file_sha256=expected_plan_sha,
        forest_leaf_catalog_sha256=forest_sha,
        carrier_connectivity_sha256=carrier_connectivity_sha,
        mesh_cell_box_catalog_sha256=mesh_box_sha,
        cell_degree_plan_sha256=cell_degree_sha,
        geometry_canonical_entity_degree_sha256=entity_degree_sha,
        structural_inventory={
            "raw_active_fe_dofs": raw_active_dofs,
            "active_fe_dofs": active_dofs,
            "matrix_rows": matrix_rows,
            "matrix_nnz": matrix_nnz,
            "factor_nnz": factor_nnz,
            "solver_peak_bytes": solver_peak_bytes,
        },
        live_role_evidence=live_reference,
    )


def _order_payload(
    summary: Mapping[str, Any],
    config: Mapping[str, Any],
    dtn: Mapping[str, Any],
) -> list[dict[str, Any]]:
    metrics = _mapping(dtn.get("metrics"), label="DtN metrics")
    if (
        metrics.get("power_source") != "dtn_port_modal_amplitudes"
        or metrics.get("diffraction_total_power_source")
        != "dtn_port_modal_amplitudes"
        or metrics.get("stage4_dtn_assembly") != "auxiliary"
        or not isinstance(
            metrics.get("dtn_port_modal_amplitude_convention"),
            str,
        )
    ):
        raise CandidateOutputError("DtN artifact uses a different convention")
    for name in ("R00_s", "R00_p", "R00_total", "R_total", "T_total"):
        if not math.isclose(
            _finite(metrics.get(name), label=f"DtN metrics.{name}"),
            _finite(summary.get(name), label=f"run summary.{name}"),
            rel_tol=0.0,
            abs_tol=1.0e-15,
        ):
            raise CandidateOutputError(
                f"DtN metrics and run summary differ for {name}"
            )

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
            raise CandidateOutputError(f"duplicate DtN order/polarization: {key}")
        indexed[key] = row
    if any(
        port not in FIXED_PORTS or polarization not in {"s", "p"}
        for port, _m, _n, polarization in indexed
    ):
        raise CandidateOutputError("DtN inventory has an unsupported mode")
    physical_ids = {
        (port, m, n)
        for port, m, n, polarization in indexed
        if polarization in {"s", "p"}
    }
    missing_fixed = tuple(
        identity for identity in FIXED_ORDER_KEYS if identity not in physical_ids
    )
    if missing_fixed:
        raise CandidateOutputError(
            f"DtN inventory misses fixed physical orders: {missing_fixed[:2]}"
        )

    k0 = _finite(config.get("k0"), label="config.k0")
    mu_r = _complex(config.get("mu_r"), label="config.mu_r")
    if k0 <= 0.0 or abs(mu_r) <= 0.0:
        raise CandidateOutputError("k0 and mu_r must be nonzero")
    port_index = {port: index for index, port in enumerate(FIXED_PORTS)}
    result = []
    for port, m, n in sorted(
        physical_ids,
        key=lambda identity: (
            port_index[identity[0]],
            -identity[1],
            identity[2],
        ),
    ):
        rows = {}
        for polarization in ("s", "p"):
            key = (port, m, n, polarization)
            if key not in indexed:
                raise CandidateOutputError(
                    f"DtN physical order lacks {polarization}: {(port, m, n)}"
                )
            rows[polarization] = indexed[key]
        co = rows["s"]
        cross = rows["p"]
        for field in ("propagating", "power_carrying"):
            if co.get(field) is not cross.get(field):
                raise CandidateOutputError(
                    f"S/P {field} differs for {(port, m, n)}"
                )
        if _complex(co.get("kz"), label="S kz") != _complex(
            cross.get("kz"),
            label="P kz",
        ):
            raise CandidateOutputError(f"S/P kz differs for {(port, m, n)}")
        propagating = co.get("propagating")
        power_carrying = co.get("power_carrying")
        if (
            not isinstance(propagating, bool)
            or not isinstance(power_carrying, bool)
            or propagating is not power_carrying
        ):
            raise CandidateOutputError(
                f"propagation/power identity differs for {(port, m, n)}"
            )
        co_power_raw = co.get("power_ratio")
        cross_power_raw = cross.get("power_ratio")
        if power_carrying:
            co_power = _finite(co_power_raw, label="S power ratio")
            cross_power = _finite(
                cross_power_raw,
                label="P power ratio",
            )
            if co_power < 0.0 or cross_power < 0.0:
                raise CandidateOutputError("far-field power must be nonnegative")
            total_power: float | None = co_power + cross_power
            cross_power_payload: float | None = cross_power
        else:
            for label, value in (
                ("S evanescent power", co_power_raw),
                ("P evanescent power", cross_power_raw),
            ):
                if value is not None and _finite(value, label=label) != 0.0:
                    raise CandidateOutputError(
                        "evanescent order carries nonzero far-field power"
                    )
            total_power = None
            cross_power_payload = None
        admittance = _complex(co.get("beta"), label="S beta") / (k0 * mu_r)
        result.append(
            {
                "port": port,
                "m": m,
                "n": n,
                "propagating": power_carrying,
                "total_power": total_power,
                "co_polarized_amplitude": _complex_payload(
                    _complex(
                        co.get("outgoing_amplitude_at_boundary"),
                        label="S boundary amplitude",
                    )
                ),
                "cross_polarized_power": cross_power_payload,
                "cross_polarized_amplitude": _complex_payload(
                    _complex(
                        cross.get("outgoing_amplitude_at_boundary"),
                        label="P boundary amplitude",
                    )
                ),
                "kz": _complex_payload(
                    _complex(co.get("kz"), label="S kz")
                ),
                "admittance": _complex_payload(admittance),
                "normalization_identity": NORMALIZATION_IDENTITY,
            }
        )
    return result


def _field_payload(
    run_dir: Path,
    summary: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    metadata_sha256: str,
    hashes: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if metadata.get("schema_version") != 1:
        raise CandidateOutputError("field metadata schema is unsupported")
    archive_path = _run_child(
        run_dir,
        metadata.get("archive"),
        label="field archive",
    )
    archive_sha = _require_hash(
        archive_path,
        metadata.get("archive_sha256"),
        label="field archive",
    )
    hashes["field_metadata"] = metadata_sha256
    hashes["field_archive"] = archive_sha
    if (
        metadata.get("archive_bytes") != archive_path.stat().st_size
        or summary.get("full3d_reference_archive_sha256") != archive_sha
        or summary.get("full3d_reference_archive_bytes")
        != archive_path.stat().st_size
        or Path(str(summary.get("full3d_reference_archive"))).name
        != archive_path.name
    ):
        raise CandidateOutputError("field archive metadata differs from summary")
    try:
        with np.load(archive_path, allow_pickle=False) as archive:
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
                raise CandidateOutputError(
                    "field archive array inventory is incomplete"
                )
            x = np.asarray(archive["x_nm"], dtype=float)
            y = np.asarray(archive["y_nm"], dtype=float)
            z = np.asarray(archive["z_nm"], dtype=float)
            e = np.asarray(archive["E_V_per_m"], dtype=complex)
            h = np.asarray(archive["H_A_per_m"], dtype=complex)
            interface_z = np.asarray(archive["interface_z_nm"], dtype=float)
            e_interface = np.asarray(
                archive["E_t_interface_V_per_m"],
                dtype=complex,
            )
            h_interface = np.asarray(
                archive["H_t_interface_A_per_m"],
                dtype=complex,
            )
    except (OSError, ValueError) as error:
        if isinstance(error, CandidateOutputError):
            raise
        raise CandidateOutputError("cannot read field archive") from error
    arrays = (x, y, z, e, h, interface_z, e_interface, h_interface)
    if any(not np.all(np.isfinite(array)) for array in arrays):
        raise CandidateOutputError("field archive contains non-finite values")
    expected_shape = (len(z), len(y), len(x), 3)
    interface_indices = np.asarray(
        metadata.get("interface_plane_indices"),
        dtype=int,
    )
    middle_indices = np.asarray(
        metadata.get("middle_plane_indices"),
        dtype=int,
    )
    if (
        e.shape != expected_shape
        or h.shape != expected_shape
        or list(expected_shape)
        != metadata.get("array_shape_z_y_x_component")
        or interface_indices.ndim != 1
        or middle_indices.ndim != 1
        or interface_indices.size == 0
        or middle_indices.size == 0
        or np.any(interface_indices < 0)
        or np.any(interface_indices >= len(z))
        or np.any(middle_indices < 0)
        or np.any(middle_indices >= len(z))
        or not np.array_equal(interface_z, z[interface_indices])
        or not np.array_equal(e_interface, e[interface_indices, :, :, :2])
        or not np.array_equal(h_interface, h[interface_indices, :, :, :2])
    ):
        raise CandidateOutputError("field grid, shapes, or slices differ")

    scalar_observations = [
        {
            "name": FORMAL_FIELD_SCALAR_NAMES[0],
            "value": float(np.linalg.norm(e_interface.ravel())),
        },
        {
            "name": FORMAL_FIELD_SCALAR_NAMES[1],
            "value": float(np.linalg.norm(e[middle_indices].ravel())),
        },
    ]
    complex_observations = [
        {
            "name": FORMAL_FIELD_COMPLEX_NAMES[0],
            "value": _complex_payload(complex(np.mean(e_interface))),
        },
        {
            "name": FORMAL_FIELD_COMPLEX_NAMES[1],
            "value": _complex_payload(complex(np.mean(e[middle_indices]))),
        },
    ]

    def append_array(name: str, array: np.ndarray) -> None:
        for index in np.ndindex(array.shape):
            suffix = "/".join(
                f"i{axis}={value}" for axis, value in enumerate(index)
            )
            complex_observations.append(
                {
                    "name": f"{name}/{suffix}",
                    "value": _complex_payload(complex(array[index])),
                }
            )

    append_array("interface/E_t", e_interface)
    append_array("interface/H_t", h_interface)
    append_array("volume/E", e[middle_indices])
    append_array("volume/H", h[middle_indices])
    return scalar_observations, complex_observations


def adapt_candidate_output(
    record_input: CandidateWatchdogInput,
    *,
    output_role: str = "current",
) -> AdaptedCandidateOutput:
    """Rebuild one qualified current or shadow output from hashed files.

    The default remains the blind current solve.  Shadow outputs must be
    requested explicitly and must carry the matching qualified watchdog role;
    a caller cannot relabel one solved endpoint after the fact.
    """

    (
        record,
        run_dir,
        summary,
        config,
        source_sha,
        config_sha,
        hashes,
    ) = _record_context(record_input, output_role=output_role)
    _validate_solver_summary(record, summary)
    provenance = _candidate_provenance(record, run_dir, summary, hashes)
    raw = _mapping(record.get("raw_evidence"), label="record.raw_evidence")

    dtn_path = _run_child(
        run_dir,
        summary.get("dtn_port_orders_json"),
        label="DtN orders",
    )
    if _resolve_path(raw.get("dtn_orders"), label="raw DtN orders") != dtn_path:
        raise CandidateOutputError("DtN path escaped the run directory")
    hashes["dtn_orders"] = _require_hash(
        dtn_path,
        record.get("dtn_orders_sha256"),
        label="DtN orders",
    )
    orders = _order_payload(
        summary,
        config,
        _load_json(dtn_path, label="DtN orders"),
    )

    volume_path = _run_child(
        run_dir,
        summary.get("volume_absorption_file"),
        label="volume absorption",
    )
    if (
        _resolve_path(
            raw.get("volume_absorption"),
            label="raw volume absorption",
        )
        != volume_path
    ):
        raise CandidateOutputError(
            "volume-absorption path escaped the run directory"
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
        or volume.get("power_source")
        != "volume_integral_Im_epsilon_E2"
    ):
        raise CandidateOutputError("volume absorption is not official")
    a_volume = _finite(
        volume.get("A_volume_total"),
        label="volume A_volume_total",
    )
    if not math.isclose(
        a_volume,
        _finite(summary.get("A_volume_total"), label="summary A_volume"),
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise CandidateOutputError("volume artifact and summary differ")

    metadata_path = _run_child(
        run_dir,
        "full3d_reference_samples.json",
        label="field metadata",
    )
    if (
        _resolve_path(
            raw.get("reference_metadata"),
            label="raw field metadata",
        )
        != metadata_path
    ):
        raise CandidateOutputError("field metadata path escaped the run directory")
    metadata_sha = _require_hash(
        metadata_path,
        record.get("reference_metadata_sha256"),
        label="field metadata",
    )
    field_scalars, field_complex = _field_payload(
        run_dir,
        summary,
        _load_json(metadata_path, label="field metadata"),
        metadata_sha256=metadata_sha,
        hashes=hashes,
    )

    r00_s = _finite(summary.get("R00_s"), label="R00_s")
    r00_p = _finite(summary.get("R00_p"), label="R00_p")
    r00_total = _finite(summary.get("R00_total"), label="R00_total")
    r_total = _finite(summary.get("R_total"), label="R_total")
    t_total = _finite(summary.get("T_total"), label="T_total")
    a_closure = _finite(summary.get("A_balance"), label="A_closure")
    residual = _finite(
        summary.get("linear_system_relative_residual"),
        label="full explicit true residual",
    )
    if not math.isclose(
        r00_total,
        r00_s + r00_p,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise CandidateOutputError("R00 total is not the S/P sum")
    energy_total = r_total + t_total + a_volume
    if (
        residual > 1.0e-9
        or abs(energy_total - 1.0) > 1.0e-9
        or abs(a_closure - a_volume) > 1.0e-9
        or a_volume < 0.0
    ):
        raise CandidateOutputError(
            "candidate residual, energy, or absorption gate failed"
        )
    totals = {
        "R00_s": r00_s,
        "R00_p": r00_p,
        "R00_total": r00_total,
        "R_total": r_total,
        "T_total": t_total,
        "A_closure": a_closure,
        "A_volume": a_volume,
        "energy_closure": energy_total,
    }
    scalar_observations = [
        {"name": name, "value": value}
        for name, value in totals.items()
    ]
    scalar_observations.extend(field_scalars)
    for name in ("A_volume_grating", "A_volume_substrate"):
        if name in volume:
            scalar_observations.append(
                {
                    "name": name,
                    "value": _finite(volume[name], label=name),
                }
            )
    payload: dict[str, Any] = {
        "schema_version": CANDIDATE_OUTPUT_SCHEMA,
        "orders": orders,
        "scalar_observations": scalar_observations,
        "complex_observations": field_complex,
        "full_explicit_true_residual": residual,
    }
    if set(payload) != _OUTPUT_KEYS:
        raise AssertionError("candidate output construction used an open schema")
    authority = _mapping(
        record["task035e_blind_candidate"],
        label="record.task035e_blind_candidate",
    )
    return AdaptedCandidateOutput(
        payload=payload,
        output_sha256=_json_sha256(payload),
        record_sha256=hashes["watchdog_record"],
        source_sha=source_sha,
        config_sha256=config_sha,
        trial_id=str(authority["trial_id"]),
        cycle_index=int(authority["cycle_index"]),
        output_role=str(authority["output_role"]),
        plan_path=provenance.plan_path,
        plan_file_sha256=provenance.plan_file_sha256,
        forest_leaf_catalog_sha256=(
            provenance.forest_leaf_catalog_sha256
        ),
        carrier_connectivity_sha256=(
            provenance.carrier_connectivity_sha256
        ),
        mesh_cell_box_catalog_sha256=(
            provenance.mesh_cell_box_catalog_sha256
        ),
        cell_degree_plan_sha256=provenance.cell_degree_plan_sha256,
        geometry_canonical_entity_degree_sha256=(
            provenance.geometry_canonical_entity_degree_sha256
        ),
        structural_inventory=dict(provenance.structural_inventory),
        artifact_sha256=dict(hashes),
        live_role_evidence=(
            None
            if provenance.live_role_evidence is None
            else dict(provenance.live_role_evidence)
        ),
    )


def write_candidate_output(
    path: Path | str,
    adapted: AdaptedCandidateOutput,
    *,
    overwrite: bool = False,
) -> CandidateOutputWriteReceipt:
    """Atomically write one immutable mode-0600 candidate output."""

    if overwrite:
        raise CandidateOutputError("formal candidate outputs are immutable")
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite candidate output: {destination}"
        )
    forbidden = {"reference_certifier", "hidden_auditor", "sealed_reference"}
    if any(part.lower() in forbidden for part in destination.parts):
        raise CandidateOutputError(
            "candidate output destination crosses a layer boundary"
        )
    if _json_sha256(adapted.payload) != adapted.output_sha256:
        raise CandidateOutputError("candidate output changed after adaptation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            adapted.payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, destination)
        temporary_path.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return CandidateOutputWriteReceipt(
        path=destination,
        output_sha256=adapted.output_sha256,
        byte_count=len(encoded),
        source_sha=adapted.source_sha,
        config_sha256=adapted.config_sha256,
        trial_id=adapted.trial_id,
        cycle_index=adapted.cycle_index,
        output_role=adapted.output_role,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--record-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--output-role",
        choices=tuple(CANDIDATE_OUTPUT_ROLES),
        default="current",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        adapted = adapt_candidate_output(
            CandidateWatchdogInput(
                path=args.record,
                sha256=args.record_sha256,
            ),
            output_role=args.output_role,
        )
        receipt = write_candidate_output(args.output, adapted)
    except (CandidateOutputError, FileExistsError) as error:
        print(
            json.dumps(
                {
                    "schema_version": "task035e.candidate-output-adapter-receipt.v1",
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": "task035e.candidate-output-adapter-receipt.v1",
                "status": "completed",
                "output_sha256": receipt.output_sha256,
                "source_sha": receipt.source_sha,
                "config_sha256": receipt.config_sha256,
                "trial_id": receipt.trial_id,
                "cycle_index": receipt.cycle_index,
                "output_role": receipt.output_role,
                "byte_count": receipt.byte_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANDIDATE_AUTHORITY_SCHEMA",
    "CANDIDATE_OUTPUT_SCHEMA",
    "CANDIDATE_OUTPUT_ROLES",
    "CANDIDATE_OUTPUT_STATUS",
    "AdaptedCandidateOutput",
    "CandidateOutputError",
    "CandidateOutputWriteReceipt",
    "CandidateWatchdogInput",
    "adapt_candidate_output",
    "candidate_config_sha256",
    "main",
    "write_candidate_output",
]
