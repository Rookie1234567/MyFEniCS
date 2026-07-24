"""Build the Task035b channel phase-dispersion diagnostic evidence.

This executable is a SHA-bound, exclusive-create pure postprocessor.  It reads
the frozen significant-channel reference and four completed MPI8 authorities;
it never imports a PDE runner, changes a Gate, or creates a formal candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping, Sequence

from src.adaptivity.channel_phase_dispersion import (
    build_phase_dispersion_analysis,
    channel_identity,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
RECORDS = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
    "channel_phase_dispersion_diagnostic_v1.json"
)
SOURCE_FILES = (
    "benchmarks/task035b_channel_phase_dispersion.py",
    "src/adaptivity/channel_phase_dispersion.py",
)
DEFAULT_AUTHORITIES = {
    "significant_reference_v1": {
        "path": RECORDS / "significant_channel_reference_v1.json",
        "sha256": (
            "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3"
        ),
    },
    "fixed_h15": {
        "path": (
            RECORDS
            / "fixed_p5trace_p6interior_h15_"
            "tensor_dedup_preallocation_mpi8.json"
        ),
        "sha256": (
            "1ffde81be08c24232e62c1d2dfbf1b7ad2dcb3623444ea40af68b5c6585758e3"
        ),
    },
    "fixed_h14": {
        "path": (
            RECORDS / "fixed_p5trace_p6interior_h14_directional_z_mpi8.json"
        ),
        "sha256": (
            "e93f50155b3c8517292794cb9735730ebf738410aecafe00f43f7959c150a127"
        ),
    },
    "fixed_h13": {
        "path": (
            RECORDS / "fixed_p5trace_p6interior_h13_directional_z_mpi8.json"
        ),
        "sha256": (
            "81ba43d91c4c9a35121676ae40368d56116f3a381e4559d630fb547a94dc4a5c"
        ),
    },
    "global_p6_h15": {
        "path": (
            RECORDS
            / "global_hexa_p5_p6_h15_"
            "assembly_time_condensed_independent_mpi8.json"
        ),
        "sha256": (
            "59859ef7b49ac6c40e2e3d803a366c71742a29411f7d9591384c62dc8fa923f9"
        ),
    },
}
CANDIDATE_ORDER = (
    "global_p6_h15_control",
    "fixed_p5trace_p6interior_h15",
    "fixed_p5trace_p6interior_h14",
    "fixed_p5trace_p6interior_h13",
)
PRIORITY_CANDIDATE = "fixed_p5trace_p6interior_h13"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _full_git_sha(value: Any) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 40 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _full_sha256(value: Any) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _resolve(repo_root: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = repo_root / resolved
    return resolved.resolve()


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _runtime_preflight(repo_root: Path) -> dict[str, Any]:
    virtual_environment = os.environ.get("VIRTUAL_ENV")
    expected_virtual_environment = str((repo_root / ".venv").resolve())
    temporary_directories = {
        name: os.environ.get(name)
        for name in ("TMPDIR", "TMP", "TEMP")
    }
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtual_environment": (
            virtual_environment is not None
            and str(Path(virtual_environment).resolve())
            == expected_virtual_environment
        ),
        "working_directory_is_repo_root": (
            Path.cwd().resolve() == repo_root.resolve()
        ),
        "linux_runtime": platform.system() == "Linux",
        "temporary_directories_not_on_windows_mount": all(
            value is not None and not str(value).startswith("/mnt/")
            for value in temporary_directories.values()
        ),
    }
    if not all(checks.values()):
        raise SystemExit(
            "channel phase-dispersion runtime gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "pass": True,
        "checks": checks,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "virtual_environment": virtual_environment,
        "temporary_directories": temporary_directories,
    }


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).strip().lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": _full_git_sha(verified),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "channel phase-dispersion source gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": status,
        "checks": checks,
    }


def _reverify_source_before_write(
    repo_root: Path,
    source_before: Mapping[str, Any],
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "head_stable_after_build": head == source_before.get("commit_sha"),
        "branch_stable_after_build": (
            branch == source_before.get("branch") == EXPECTED_BRANCH
        ),
        "tracked_and_untracked_worktree_clean_after_build": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "channel phase-dispersion source changed before evidence write: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "head_after_sha": head,
        "branch_after": branch,
        "status_after_before_record_write": status,
        "stable_and_clean_after": True,
        "checks": checks,
    }


def _validated_source(source: Mapping[str, Any]) -> dict[str, Any]:
    checks = source.get("checks")
    valid = bool(
        _full_git_sha(source.get("commit_sha"))
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and source.get("branch") == EXPECTED_BRANCH
        and source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_before") is True
        and source.get("head_after_sha") == source.get("commit_sha")
        and source.get("branch_after") == EXPECTED_BRANCH
        and source.get("status_after_before_record_write") == ""
        and source.get("stable_and_clean_after") is True
        and isinstance(checks, Mapping)
        and bool(checks)
        and all(value is True for value in checks.values())
    )
    if not valid:
        raise ValueError("channel phase-dispersion source is unqualified")
    return dict(source)


def _source_file_sha256(repo_root: Path) -> dict[str, str]:
    return {path: _sha256(repo_root / path) for path in SOURCE_FILES}


def _load_authorities(
    repo_root: Path,
    definitions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(definitions) != set(DEFAULT_AUTHORITIES):
        raise ValueError("channel phase-dispersion authority set is incomplete")
    records: dict[str, Any] = {}
    manifest: dict[str, Any] = {}
    for name in DEFAULT_AUTHORITIES:
        definition = definitions[name]
        expected = str(definition.get("sha256", "")).lower()
        if not _full_sha256(expected):
            raise ValueError(f"{name} expected SHA256 must be full 64-hex")
        path = _resolve(repo_root, definition["path"])
        if not path.is_file():
            raise ValueError(f"{name} authority is absent: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"{name} SHA256 mismatch: expected {expected}, got {actual}"
            )
        records[name] = json.loads(path.read_text(encoding="utf-8"))
        manifest[name] = {
            "path": str(path),
            "sha256": actual,
        }
    return records, manifest


def _clean_qualified_record(
    record: Mapping[str, Any],
    *,
    label: str,
) -> None:
    source = record.get("source")
    qualification = record.get("qualification")
    if not (
        isinstance(source, Mapping)
        and _full_git_sha(source.get("commit_sha"))
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and source.get("head_after_sha") == source.get("commit_sha")
        and source.get("tracked_source_dirty") is False
        and source.get("status_after_before_record_write") == ""
        and source.get("stable_and_clean_after") is True
        and isinstance(qualification, Mapping)
        and qualification.get("pass") is True
    ):
        raise ValueError(f"{label} is not a clean qualified authority")


def _authority_entry(
    reference: Mapping[str, Any],
    sample_id: str,
) -> Mapping[str, Any]:
    matches = [
        entry
        for entry in reference.get("authorities", [])
        if isinstance(entry, Mapping) and entry.get("sample_id") == sample_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"reference must contain exactly one {sample_id} authority"
        )
    return matches[0]


def _validate_reference(
    reference: Mapping[str, Any],
) -> None:
    channels = reference.get("channels")
    selection = reference.get("significant_channel_selection")
    if not (
        reference.get("schema_version")
        == "task035b.significant-channel-reference.v1"
        and reference.get("status")
        == "significant_channel_reference_v1_frozen"
        and reference.get("pass") is True
        and reference.get("mechanical_validation_pass") is True
        and reference.get("canonical") is False
        and reference.get("production_qualified") is False
        and reference.get("ordinary_default_changed") is False
        and reference.get("geometry")
        == "Task034 fixed rectangular block grating"
        and _full_sha256(reference.get("reference_payload_sha256"))
        and isinstance(selection, Mapping)
        and selection.get("channel_count") == 12
        and isinstance(channels, list)
        and len(channels) == 12
    ):
        raise ValueError("significant-channel reference v1 is unqualified")
    identities = []
    for entry in channels:
        if not isinstance(entry, Mapping):
            raise ValueError("reference channel entry must be an object")
        channel = entry.get("channel")
        analytic = entry.get("analytic_identity")
        if not isinstance(channel, Mapping) or not isinstance(analytic, Mapping):
            raise ValueError("reference channel identity is incomplete")
        identity = channel_identity(channel)
        if channel_identity(analytic) != identity:
            raise ValueError("reference analytic channel identity differs")
        gate = entry.get("unchanged_v0_acceptance_gate")
        if not (
            isinstance(gate, Mapping)
            and gate.get("uses_numerical_convergence_band") is False
            and gate.get("uses_h15_or_fixed_diagnostics") is False
            and gate.get("unchanged_v0_formula_verified") is True
        ):
            raise ValueError("reference unchanged-v0 Gate is unqualified")
        identities.append(identity)
    if len(identities) != len(set(identities)):
        raise ValueError("reference channel identities must be unique")


def _validate_fixed_record(
    record: Mapping[str, Any],
    *,
    h_nm: float,
    axis_cells: Sequence[int],
    reference_sha256: str,
    reference_payload_sha256: str,
    label: str,
) -> None:
    _clean_qualified_record(record, label=label)
    target = record.get("target_identity")
    candidate = record.get("candidate")
    qualification_checks = record.get("qualification", {}).get("checks", {})
    true_residual = (
        candidate.get("cell_static_condensation", {})
        .get("full_explicit_true_residual", {})
        .get("linear_system_relative_residual")
        if isinstance(candidate, Mapping)
        else None
    )
    if not (
        record.get("schema_version") == "task035b.fixed-trace-watchdog.v1"
        and record.get("status") == "actual_fixed_trace_controlled_negative"
        and isinstance(target, Mapping)
        and target.get("geometry") == "Task034 fixed rectangular block grating"
        and float(target.get("h_nm")) == h_nm
        and target.get("trace_degree") == 5
        and target.get("interior_degree") == 6
        and isinstance(candidate, Mapping)
        and qualification_checks.get("full_true_residual_le_1e-9") is True
        and isinstance(true_residual, (int, float))
        and 0.0 <= float(true_residual) <= 1.0e-9
    ):
        raise ValueError(f"{label} fixed-trace identity is unqualified")
    resolved = target.get("actual_mesh_cells_resolved")
    if resolved is None:
        resolved = (
            record.get("fixed_trace_resource_preflight", {})
            .get("axis_plan", {})
            .get("mesh_cells_resolved")
        )
    exact_axis_identity = (
        list(resolved) == list(axis_cells)
        if resolved is not None
        else (
            candidate.get("num_mesh_cells") == math.prod(axis_cells)
            and record.get("same_mesh_global_p6_baseline", {}).get("pass")
            is True
        )
    )
    if not exact_axis_identity:
        raise ValueError(f"{label} fixed-trace axis identity differs")
    comparison = record.get("diffraction_channel_comparison")
    if not isinstance(comparison, Mapping):
        raise ValueError(f"{label} channel comparison is absent")
    channels = comparison.get("channels")
    if not isinstance(channels, list) or len(channels) not in {12, 80}:
        raise ValueError(f"{label} channel comparison has invalid size")
    if h_nm in {13.0, 14.0}:
        authority = record.get("significant_channel_reference_authority")
        if not (
            isinstance(authority, Mapping)
            and authority.get("sha256") == reference_sha256
            and authority.get("reference_payload_sha256")
            == reference_payload_sha256
            and authority.get("frozen_channel_count") == 12
            and authority.get("unchanged_v0_gate") is True
            and authority.get("numerical_convergence_band_used_as_gate")
            is False
            and comparison.get("thresholds_relaxed") is False
            and comparison.get("numerical_convergence_band_used_as_gate")
            is False
        ):
            raise ValueError(f"{label} frozen reference binding differs")


def _validate_global_p6_h15(
    record: Mapping[str, Any],
    *,
    record_sha256: str,
    reference: Mapping[str, Any],
) -> None:
    _clean_qualified_record(record, label="global_p6_h15")
    target = record.get("target_identity")
    mesh = record.get("common_mesh_identity")
    enriched = record.get("enriched")
    qualification_checks = record.get("qualification", {}).get("checks", {})
    true_residual = (
        enriched.get("cell_static_condensation", {})
        .get("full_explicit_true_residual", {})
        .get("linear_system_relative_residual")
        if isinstance(enriched, Mapping)
        else None
    )
    if not (
        record.get("schema_version") == "task035.actual-global-r5-watchdog.v1"
        and record.get("status") == "actual_global_r5_pass"
        and isinstance(target, Mapping)
        and target.get("geometry") == "Task034 fixed rectangular block grating"
        and isinstance(mesh, Mapping)
        and mesh.get("mesh_cells_resolved") == [6, 2, 10]
        and isinstance(enriched, Mapping)
        and enriched.get("degree") == 6
        and float(enriched.get("h_nm")) == 15.0
        and enriched.get("mpi_size") == 8
        and enriched.get("official_result") is True
        and qualification_checks.get("both_true_residuals_le_1e-9") is True
        and isinstance(true_residual, (int, float))
        and 0.0 <= float(true_residual) <= 1.0e-9
    ):
        raise ValueError("global-p6/h15 authority is unqualified")
    entry = _authority_entry(reference, "p6_h15")
    bound_record = entry.get("record")
    if not (
        entry.get("role") == "underresolved_diagnostic"
        and isinstance(bound_record, Mapping)
        and bound_record.get("sha256") == record_sha256
        and entry.get("source_sha")
        == record.get("source", {}).get("commit_sha")
        and entry.get("qualification") == "validated_pass"
    ):
        raise ValueError("global-p6/h15 is not bound by reference v1")


def _reference_contract(
    reference: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for entry in reference["channels"]:
        identity = dict(entry["channel"])
        center = entry["reference_center"]
        analytic = entry["analytic_identity"]
        gate = entry["unchanged_v0_acceptance_gate"]
        rows.append(
            {
                **identity,
                "label": identity["label"],
                "kz": analytic["kz"],
                "reference_amplitude": center["complex_amplitude"],
                "reference_power": center["power"],
                "power_tolerance": gate["power_absolute_tolerance"],
                "amplitude_tolerance": (
                    gate["complex_amplitude_absolute_tolerance"]
                ),
            }
        )
    return rows


def _frozen_sample_channels(
    reference: Mapping[str, Any],
    sample_id: str,
) -> list[dict[str, Any]]:
    rows = []
    for entry in reference["channels"]:
        sample = entry.get("underresolved_diagnostics_not_in_bands", {}).get(
            sample_id
        )
        if not isinstance(sample, Mapping):
            raise ValueError(f"reference lacks frozen sample {sample_id}")
        rows.append(
            {
                **entry["channel"],
                "candidate_amplitude": sample["complex_amplitude"],
                "candidate_power": sample["power"],
            }
        )
    return rows


def _record_candidate_channels(
    record: Mapping[str, Any],
    *,
    reference_identities: set[tuple[str, int, int, str]],
    label: str,
) -> list[dict[str, Any]]:
    comparison = record["diffraction_channel_comparison"]
    rows = []
    for entry in comparison["channels"]:
        identity = channel_identity(entry)
        if identity not in reference_identities:
            continue
        rows.append(
            {
                "side": identity[0],
                "m": identity[1],
                "n": identity[2],
                "polarization": identity[3],
                "candidate_amplitude": (
                    entry["candidate_outgoing_amplitude_at_boundary"]
                ),
                "candidate_power": entry["candidate_power_ratio"],
                "authority_power_pass": entry.get("power_pass"),
                "authority_complex_amplitude_pass": entry.get(
                    "complex_amplitude_pass"
                ),
            }
        )
    if len(rows) != 12:
        raise ValueError(f"{label} does not contain all 12 frozen channels")
    if len({channel_identity(row) for row in rows}) != 12:
        raise ValueError(f"{label} frozen channel identities are duplicated")
    return rows


def _assert_fixed_h15_frozen_sample_identity(
    reference: Mapping[str, Any],
    fixed_h15_rows: Sequence[Mapping[str, Any]],
    *,
    fixed_h15_sha256: str,
) -> None:
    entry = _authority_entry(reference, "fixed_p5trace_p6interior_h15")
    bound_record = entry.get("record")
    if not (
        entry.get("role") == "underresolved_trace_diagnostic"
        and isinstance(bound_record, Mapping)
        and bound_record.get("sha256") == fixed_h15_sha256
        and entry.get("qualification") == "validated_pass"
    ):
        raise ValueError("fixed h15 is not bound by reference v1")
    frozen = {
        channel_identity(row): row
        for row in _frozen_sample_channels(
            reference,
            "fixed_p5trace_p6interior_h15",
        )
    }
    for row in fixed_h15_rows:
        expected = frozen[channel_identity(row)]
        if (
            row["candidate_amplitude"] != expected["candidate_amplitude"]
            or row["candidate_power"] != expected["candidate_power"]
        ):
            raise ValueError("fixed h15 values differ from frozen reference")


def _assert_authority_gate_identity(
    analysis: Mapping[str, Any],
    authority_rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> None:
    recorded = {
        channel_identity(row): row
        for row in authority_rows
    }
    for row in analysis["channels"]:
        authority = recorded[channel_identity(row)]
        for recorded_name, recomputed_name in (
            ("authority_power_pass", "power_pass"),
            (
                "authority_complex_amplitude_pass",
                "complex_amplitude_pass",
            ),
        ):
            recorded_value = authority.get(recorded_name)
            if (
                recorded_value is not None
                and recorded_value is not row[recomputed_name]
            ):
                raise ValueError(
                    f"{label} recomputed unchanged Gate differs from authority"
                )


def _validated_source_hashes(
    source_file_sha256: Mapping[str, str],
) -> dict[str, str]:
    hashes = dict(source_file_sha256)
    if not (
        set(hashes) == set(SOURCE_FILES)
        and all(_full_sha256(value) for value in hashes.values())
    ):
        raise ValueError("channel phase-dispersion source hashes are invalid")
    return hashes


def _phase_summary(analysis: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for candidate_id in CANDIDATE_ORDER:
        candidate = analysis["candidates"][candidate_id]
        result[candidate_id] = {
            "power_pass_count": candidate["power_pass_count_recomputed"],
            "complex_amplitude_pass_count": (
                candidate["complex_amplitude_pass_count_recomputed"]
            ),
            "bottom_reference_power_weighted_delta_z_eff_nm": (
                candidate["phase_fit_by_side"]["bottom"][
                    "reference_power_weighted"
                ]["delta_z_eff_nm"]
            ),
            "bottom_reference_power_weighted_residual_to_raw": (
                candidate["phase_fit_by_side"]["bottom"][
                    "reference_power_weighted"
                ]["weighted_residual_to_raw_phase_rms"]
            ),
            "top_reference_power_weighted_delta_z_eff_nm": (
                candidate["phase_fit_by_side"]["top"][
                    "reference_power_weighted"
                ]["delta_z_eff_nm"]
            ),
            "top_reference_power_weighted_residual_to_raw": (
                candidate["phase_fit_by_side"]["top"][
                    "reference_power_weighted"
                ]["weighted_residual_to_raw_phase_rms"]
            ),
        }
    return result


def build_channel_phase_dispersion_evidence(
    *,
    authorities: Mapping[str, Mapping[str, Any]],
    authority_manifest: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, Any],
    source_file_sha256: Mapping[str, str],
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the five authorities and build one diagnostic-only payload."""

    if set(authorities) != set(DEFAULT_AUTHORITIES):
        raise ValueError("channel phase-dispersion authorities are incomplete")
    if set(authority_manifest) != set(DEFAULT_AUTHORITIES):
        raise ValueError("channel phase-dispersion manifest is incomplete")
    qualified_source = _validated_source(source)
    hashes = _validated_source_hashes(source_file_sha256)
    reference = authorities["significant_reference_v1"]
    _validate_reference(reference)
    reference_sha = authority_manifest["significant_reference_v1"]["sha256"]
    payload_sha = reference["reference_payload_sha256"]

    fixed_specs = (
        ("fixed_h15", 15.0, (6, 2, 10)),
        ("fixed_h14", 14.0, (6, 2, 11)),
        ("fixed_h13", 13.0, (6, 2, 12)),
    )
    for name, h_nm, axes in fixed_specs:
        _validate_fixed_record(
            authorities[name],
            h_nm=h_nm,
            axis_cells=axes,
            reference_sha256=reference_sha,
            reference_payload_sha256=payload_sha,
            label=name,
        )
    _validate_global_p6_h15(
        authorities["global_p6_h15"],
        record_sha256=authority_manifest["global_p6_h15"]["sha256"],
        reference=reference,
    )

    reference_contract = _reference_contract(reference)
    reference_identities = {
        channel_identity(row) for row in reference_contract
    }
    fixed_h15 = _record_candidate_channels(
        authorities["fixed_h15"],
        reference_identities=reference_identities,
        label="fixed_h15",
    )
    _assert_fixed_h15_frozen_sample_identity(
        reference,
        fixed_h15,
        fixed_h15_sha256=authority_manifest["fixed_h15"]["sha256"],
    )
    fixed_h14 = _record_candidate_channels(
        authorities["fixed_h14"],
        reference_identities=reference_identities,
        label="fixed_h14",
    )
    fixed_h13 = _record_candidate_channels(
        authorities["fixed_h13"],
        reference_identities=reference_identities,
        label="fixed_h13",
    )
    candidates = {
        "global_p6_h15_control": _frozen_sample_channels(
            reference,
            "p6_h15",
        ),
        "fixed_p5trace_p6interior_h15": fixed_h15,
        "fixed_p5trace_p6interior_h14": fixed_h14,
        "fixed_p5trace_p6interior_h13": fixed_h13,
    }
    analysis = build_phase_dispersion_analysis(
        reference_channels=reference_contract,
        candidates=candidates,
        priority_candidate_id=PRIORITY_CANDIDATE,
    )
    _assert_authority_gate_identity(
        analysis["candidates"]["fixed_p5trace_p6interior_h14"],
        fixed_h14,
        label="fixed_h14",
    )
    _assert_authority_gate_identity(
        analysis["candidates"]["fixed_p5trace_p6interior_h13"],
        fixed_h13,
        label="fixed_h13",
    )
    evidence = {
        "schema_version": "task035b.channel-phase-dispersion-diagnostic.v1",
        "status": "diagnostic_only_phase_dispersion_complete",
        "pass": True,
        "classification": "diagnostic_only",
        "formal_record": False,
        "tracked_diagnostic_evidence": True,
        "canonical": False,
        "production_qualified": False,
        "formal_candidate_eligible": False,
        "ordinary_default_changed": False,
        "thresholds_relaxed": False,
        "purpose": (
            "separate phase-bearing diffraction error from magnitude error "
            "and prioritize the next physical trace-orbit diagnostic"
        ),
        "source": qualified_source,
        "source_file_sha256": hashes,
        "runtime": None if runtime is None else dict(runtime),
        "authorities": {
            name: dict(authority_manifest[name])
            for name in DEFAULT_AUTHORITIES
        },
        "authority_binding_checks": {
            "frozen_reference_v1_sha_bound": True,
            "fixed_h15_record_and_frozen_sample_sha_bound": True,
            "fixed_h14_and_h13_records_sha_bound": True,
            "global_p6_h15_record_bound_by_reference_manifest": True,
            "all_completed_records_clean_and_qualified": True,
            "all_12_channel_identities_exact": True,
            "h14_h13_recorded_gate_flags_match_recomputation": True,
        },
        "method": {
            "phase_model": (
                "arg(a_candidate/a_reference) ~= "
                "Re(kz_per_nm) * delta_z_eff_nm"
            ),
            "fit_intercept_radians": 0.0,
            "primary_weights": "frozen reference channel power",
            "secondary_weights": "uniform across each six-channel port side",
            "fit_sides": ["bottom", "top"],
            "complex_error_frame": (
                "(a_candidate-a_reference)*conj(a_reference)"
                "/abs(a_reference)"
            ),
            "phase_bearing_fraction_definition": (
                "abs(tangential_error)/abs(complex_error)"
            ),
            "phase_bearing_priority_threshold": 0.8,
            "delta_z_eff_semantics": (
                "effective numerical phase delay, not a geometry or "
                "reference-plane correction"
            ),
        },
        "analysis": analysis,
        "compact_phase_summary": _phase_summary(analysis),
        "gate_contract": {
            "reference": "significant channel reference v1",
            "channel_count": 12,
            "power_tolerances": "unchanged v0 per-channel values",
            "complex_amplitude_tolerances": (
                "unchanged v0 per-channel values"
            ),
            "power_and_amplitude_passes_recomputed_without_modification": True,
            "numerical_convergence_band_used_as_gate": False,
            "thresholds_relaxed": False,
            "diagnostic_does_not_change_candidate_status": True,
        },
        "research_decision": {
            **analysis["research_priority"],
            "interpretation": (
                "use the phase-bearing labels to prioritize physical "
                "periodic-orbit Riesz/DWR interrogation; do not select a "
                "trace subset from this algebraic fit alone"
            ),
        },
        "pde": {
            "status": "not_run",
            "mesh_built": False,
            "form_compiled": False,
            "matrix_assembled": False,
            "factorization_started": False,
            "solver_started": False,
        },
        "execution_contract": {
            "pure_postprocess": True,
            "pde_solve_count": 0,
            "mesh_build_count": 0,
            "matrix_assembly_count": 0,
            "factorization_count": 0,
            "mpi_launch_count": 0,
            "ordinary_default_changed": False,
            "thresholds_relaxed": False,
            "irregular_geometry_run": False,
            "formal_candidate_eligible": False,
            "formal_record_created": False,
        },
    }
    json.dumps(evidence, allow_nan=False)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    for name, definition in DEFAULT_AUTHORITIES.items():
        option = name.replace("_", "-")
        parser.add_argument(
            f"--{option}-record",
            type=Path,
            default=definition["path"],
        )
        parser.add_argument(
            f"--{option}-sha256",
            default=definition["sha256"],
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runtime = _runtime_preflight(ROOT)
    source_before = _verified_source_identity(
        ROOT,
        args.verified_clean_sha,
    )
    definitions = {
        name: {
            "path": getattr(args, f"{name}_record"),
            "sha256": getattr(args, f"{name}_sha256"),
        }
        for name in DEFAULT_AUTHORITIES
    }
    authorities, manifest = _load_authorities(ROOT, definitions)
    source_hashes = _source_file_sha256(ROOT)
    source_after = _reverify_source_before_write(ROOT, source_before)
    source = dict(source_before)
    source.update(source_after)
    combined_checks = dict(source_before["checks"])
    combined_checks.update(source_after["checks"])
    source["checks"] = combined_checks
    evidence = build_channel_phase_dispersion_evidence(
        authorities=authorities,
        authority_manifest=manifest,
        source=source,
        source_file_sha256=source_hashes,
        runtime=runtime,
    )
    source_final = _reverify_source_before_write(ROOT, source_before)
    final_source = dict(source_before)
    final_source.update(source_final)
    final_checks = dict(source_before["checks"])
    final_checks.update(source_final["checks"])
    final_source["checks"] = final_checks
    if _source_file_sha256(ROOT) != source_hashes:
        raise SystemExit(
            "channel phase-dispersion source files changed before write"
        )
    evidence["source"] = _validated_source(final_source)
    output = _resolve(ROOT, args.output)
    allowed_record_root = RECORDS.resolve()
    allowed_artifact_root = (ROOT / "benchmarks/artifacts").resolve()
    allowed_temporary_root = Path("/tmp").resolve()
    if not (
        output.is_relative_to(allowed_record_root)
        or output.is_relative_to(allowed_artifact_root)
        or output.is_relative_to(allowed_temporary_root)
    ):
        raise SystemExit(
            "diagnostic output must remain under Case095 records, "
            "benchmarks/artifacts, or /tmp"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            evidence,
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
