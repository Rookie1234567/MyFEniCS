"""Postprocess the Task035b y-only global-p5 directional control.

This tool is deliberately independent of the PDE runner.  It consumes a
completed SHA-bound watchdog record, the frozen significant-channel reference
v1, and the accepted h15 global-p5 baseline.  It never runs a solve and its
output is always diagnostic-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Sequence

from src.adaptivity.high_order_same_error import (
    compare_significant_channels_to_reference_v1,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
SOURCE_FILES = (
    "benchmarks/task035b_y_directional_control.py",
    "src/adaptivity/high_order_same_error.py",
)
_EXPECTED_Y_MESH_IDENTITY = {
    "mesh_cell_type": "hexahedron",
    "global_cell_count": 180,
    "mesh_cells_resolved": [6, 3, 10],
    "partition_independent_mesh_sha256": (
        "59d053ac70baaa80c6de82fcd2388d0076291f033cf074197c218055756eec8f"
    ),
    "cell_tag_sha256": (
        "60209a26ca68027775dc54783cc44a67314804ced204928025d35607c4d999e0"
    ),
    "facet_tag_sha256": (
        "270b60e1c061cd539e64219e349e29abe0deb6e414c35c979abb25e2660b9c75"
    ),
}
_H15_AXIS_SHA256 = {
    "x": "86dc23ef348c79d9ed51d79c199cbaddf95416e04c51e5569c666234c6613cc3",
    "y": "d3aac691ebe8875dc45e5817b42b4f33c45277f999f2d010fd29fecd7ec1401f",
    "z": "f5aef6ea431298d9ebb46c16f2b674faf765046d3705d8b32dda6a2244bd6464",
}
_Y_AXIS_SHA256 = {
    "x": _H15_AXIS_SHA256["x"],
    "y": "d7841480e80baeda07536ebc44681af4488f7d61a2eaa7de4d33cdacb9fa19fb",
    "z": _H15_AXIS_SHA256["z"],
}
_EXPECTED_Y_RESOURCES = {
    "coarse_p4_dofs": 38092,
    "enriched_p5_dofs": 72995,
}
_FIXED_TARGET_IDENTITY = {
    "wavelength_nm": 13.5,
    "incidence_theta_deg": 80.0,
    "grazing_angle_deg": 10.0,
    "polarization": "S",
    "geometry": "Task034 fixed rectangular block grating",
    "mesh_backend": "boundary-fitted conforming hexahedron",
}
_MAX_TRUE_RESIDUAL = 1.0e-9
_MATERIAL_REDUCTION = 5.0e-2
_MAX_L2_REGRESSION = 1.0e-2


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _full_git_sha(value: str) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 40 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    """Require the reviewed branch and a completely clean full-SHA source."""

    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": _full_git_sha(verified_clean_sha),
        "head_matches_verified_sha": head == verified_clean_sha,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "y-only comparator source gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified_clean_sha,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": status,
        "checks": checks,
    }


def _source_file_sha256() -> dict[str, str]:
    return {
        path: _sha256(ROOT / path)
        for path in SOURCE_FILES
    }


def _reverify_source_before_write(
    repo_root: Path,
    source_before: dict[str, Any],
) -> dict[str, Any]:
    """Recheck HEAD, branch, and the worktree after all classification work."""

    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "head_stable_after_build": (
            head == source_before.get("commit_sha")
        ),
        "branch_stable_after_build": (
            branch == source_before.get("branch") == EXPECTED_BRANCH
        ),
        "tracked_and_untracked_worktree_clean_after_build": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "y-only comparator source changed before record write: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "head_after_sha": head,
        "branch_after": branch,
        "status_after_before_record_write": status,
        "stable_and_clean_after": True,
        "checks": checks,
    }


def _validated_comparator_source(
    source: dict[str, Any],
) -> dict[str, Any]:
    checks = source.get("checks") or {}
    valid = bool(
        _full_git_sha(source.get("commit_sha", ""))
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and source.get("branch") == EXPECTED_BRANCH
        and source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_before") is True
        and source.get("head_after_sha") == source.get("commit_sha")
        and source.get("branch_after") == EXPECTED_BRANCH
        and source.get("status_after_before_record_write") == ""
        and source.get("stable_and_clean_after") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )
    if not valid:
        raise ValueError(
            "y-only comparator source identity is missing or unqualified"
        )
    return dict(source)


def _validate_sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a lowercase-compatible SHA256")
    return normalized


def _resolve(repo_root: Path, path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _load_sha_bound_json(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[dict[str, Any], str]:
    expected = _validate_sha256(expected_sha256, label=label)
    if not path.is_file():
        raise ValueError(f"{label} is not a readable file: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(
            f"{label} SHA256 mismatch: expected {expected}, got {actual}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload, actual


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _qualified_watchdog(record: dict[str, Any], *, label: str) -> None:
    qualification = record.get("qualification") or {}
    checks = qualification.get("checks") or {}
    _require(
        qualification.get("pass") is True
        and qualification.get("failures") == []
        and bool(checks)
        and all(value is True for value in checks.values()),
        f"{label} qualification is not a complete pass",
    )
    source = record.get("source") or {}
    _require(
        source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_after") is True
        and source.get("commit_sha") == source.get("verified_clean_sha"),
        f"{label} source is not SHA-stable and clean",
    )
    _require(
        record.get("terminated_for_memory") is False
        and record.get("terminated_for_timeout") is False,
        f"{label} was resource-terminated",
    )


def _full_true_residual(summary: dict[str, Any]) -> float:
    audit = summary.get("cell_static_condensation") or {}
    full = audit.get("full_explicit_true_residual") or {}
    value = full.get("linear_system_relative_residual")
    if not isinstance(value, (int, float)):
        raise ValueError("full explicit true residual is missing")
    return float(value)


def _validate_solve(
    summary: dict[str, Any],
    *,
    degree: int,
    dofs: int,
    axis_cells: list[int],
    require_axis_request: bool,
) -> None:
    _require(
        summary.get("degree") == degree
        and float(summary.get("h_nm", math.nan)) == 15.0
        and summary.get("case_status") == "completed"
        and summary.get("official_result") is True
        and summary.get("mpi_size") == 8
        and summary.get("mesh_cell_type_actual") == "hexahedron"
        and summary.get("num_mesh_cells") == math.prod(axis_cells)
        and summary.get("num_nedelec_dofs") == dofs,
        f"p{degree} compact solve identity is not qualified",
    )
    if require_axis_request:
        _require(
            summary.get("mesh_cells_resolved") == axis_cells
            and summary.get("mesh_axis_cell_counts_requested") == axis_cells,
            f"p{degree} compact solve does not preserve exact axis identity",
        )
    residual = summary.get("linear_system_relative_residual")
    _require(
        isinstance(residual, (int, float))
        and float(residual) <= _MAX_TRUE_RESIDUAL
        and _full_true_residual(summary) <= _MAX_TRUE_RESIDUAL,
        f"p{degree} true residual exceeds {_MAX_TRUE_RESIDUAL}",
    )


def _validate_mesh_identity(
    identity: dict[str, Any],
    expected: dict[str, Any],
    *,
    label: str,
) -> None:
    _require(
        all(identity.get(key) == value for key, value in expected.items()),
        f"{label} mesh/tag identity mismatch",
    )
    alignment = identity.get("material_plane_alignment") or {}
    _require(
        alignment.get("all_aligned") is True,
        f"{label} material planes are not aligned",
    )


def _find_reference_authority(
    reference: dict[str, Any],
    sample_id: str,
) -> dict[str, Any]:
    matches = [
        row
        for row in reference.get("authorities") or []
        if row.get("sample_id") == sample_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"reference v1 must contain exactly one {sample_id} authority"
        )
    return matches[0]


def _validate_h15_baseline(
    *,
    repo_root: Path,
    record_path: Path,
    record: dict[str, Any],
    record_sha256: str,
    reference: dict[str, Any],
) -> Path:
    authority = _find_reference_authority(reference, "p5_h15")
    recorded = authority.get("record") or {}
    raw_orders = authority.get("raw_dtn_port_orders") or {}
    _require(
        authority.get("role") == "underresolved_diagnostic"
        and authority.get("degree") == 5
        and float(authority.get("h_nm", math.nan)) == 15.0
        and authority.get("qualification") == "validated_pass"
        and recorded.get("sha256") == record_sha256
        and _resolve(repo_root, recorded.get("path", ""))
        == record_path.resolve(),
        "reference v1 does not bind the supplied h15 global-p5 record",
    )
    _require(
        record.get("schema_version")
        == "task035.actual-global-r5-watchdog.v1"
        and record.get("status") == "actual_global_r5_pass",
        "h15 global-p5 baseline is not an accepted watchdog pass",
    )
    _qualified_watchdog(record, label="h15 global-p5 baseline")
    _require(
        record.get("target_identity") == _FIXED_TARGET_IDENTITY,
        "h15 global-p5 target identity mismatch",
    )
    expected_identity = {
        key: value
        for key, value in (
            authority.get("record_expectations") or {}
        ).items()
        if key.startswith("common_mesh_identity.")
    }
    common = record.get("common_mesh_identity") or {}
    for dotted, expected in expected_identity.items():
        key = dotted.split(".", 1)[1]
        _require(
            common.get(key) == expected,
            f"h15 global-p5 {dotted} mismatch",
        )
    _require(
        record.get("same_mesh_hashes") is True,
        "h15 global-p5 record is not a same-mesh p5/p6 pair",
    )
    _validate_solve(
        record.get("coarse") or {},
        degree=5,
        dofs=49690,
        axis_cells=[6, 2, 10],
        require_axis_request=False,
    )
    _validate_solve(
        record.get("enriched") or {},
        degree=6,
        dofs=84492,
        axis_cells=[6, 2, 10],
        require_axis_request=False,
    )
    path = _resolve(repo_root, raw_orders.get("path", ""))
    expected_raw_sha = _validate_sha256(
        raw_orders.get("sha256", ""),
        label="h15 global-p5 raw DtN orders",
    )
    _require(
        path.is_file()
        and _sha256(path) == expected_raw_sha
        and raw_orders.get("order_count") == 80,
        "h15 global-p5 raw DtN authority is missing or hash-invalid",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(
        isinstance(payload.get("orders"), list)
        and len(payload["orders"]) == 80,
        "h15 global-p5 raw DtN authority must contain 80 orders",
    )
    return path


def _validate_y_control(
    *,
    repo_root: Path,
    record: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    _require(
        record.get("schema_version")
        == "task035.actual-global-r5-watchdog.v1"
        and record.get("status") == "actual_global_r5_pass",
        "y-only control is not a completed global R5 watchdog pass",
    )
    _qualified_watchdog(record, label="y-only global-p5 control")
    _require(
        record.get("target_identity") == _FIXED_TARGET_IDENTITY,
        "y-only control target identity mismatch",
    )
    classification = (
        record.get("structured_axis_control_classification") or {}
    )
    _require(
        classification
        == {
            "role": "y_only_global_p5_directional_control",
            "diagnostic_only": True,
            "formal_candidate_eligible": False,
            "reference_v1_gate_evaluated_in_this_record": False,
            "required_followup": (
                "SHA-bound frozen-reference-v1 channel comparator"
            ),
            "thresholds_relaxed": False,
        },
        "y-only watchdog does not preserve the diagnostic-only contract",
    )
    _require(
        record.get("same_mesh_hashes") is True
        and record.get("reuse_single_mesh_requested") is True
        and record.get("single_in_memory_mesh_instance") is True,
        "y-only control is not an exact single-mesh p4/p5 pair",
    )
    common = record.get("common_mesh_identity") or {}
    _validate_mesh_identity(
        common,
        _EXPECTED_Y_MESH_IDENTITY,
        label="y-only control",
    )
    _validate_solve(
        record.get("coarse") or {},
        degree=4,
        dofs=_EXPECTED_Y_RESOURCES["coarse_p4_dofs"],
        axis_cells=[6, 3, 10],
        require_axis_request=True,
    )
    _validate_solve(
        record.get("enriched") or {},
        degree=5,
        dofs=_EXPECTED_Y_RESOURCES["enriched_p5_dofs"],
        axis_cells=[6, 3, 10],
        require_axis_request=True,
    )

    preflight = record.get("structured_axis_resource_preflight") or {}
    axis_plan = preflight.get("axis_plan") or {}
    expected_identity = axis_plan.get("expected_mesh_identity") or {}
    _require(
        preflight.get("schema_version")
        == "task035b.structured-axis-global-control-preflight.v1"
        and preflight.get("status") == "pass"
        and preflight.get("pass") is True
        and preflight.get("control_role")
        == "y_only_global_p5_directional_control"
        and preflight.get("ordinary_default_changed") is False
        and axis_plan.get("mesh_cells_resolved") == [6, 3, 10]
        and axis_plan.get("axis_sha256") == _Y_AXIS_SHA256
        and all(
            expected_identity.get(key) == value
            for key, value in _EXPECTED_Y_MESH_IDENTITY.items()
            if key.endswith("sha256")
        ),
        "y-only structured-axis preflight identity mismatch",
    )
    changed_axes = [
        axis
        for axis in ("x", "y", "z")
        if _Y_AXIS_SHA256[axis] != _H15_AXIS_SHA256[axis]
    ]
    _require(
        changed_axes == ["y"],
        "y-only control contract changes more than the y axis",
    )

    raw_evidence = record.get("raw_evidence") or {}
    run_dir = _resolve(repo_root, raw_evidence.get("run_directory", ""))
    actual_result_path = _resolve(
        repo_root,
        raw_evidence.get("actual_r5_result", ""),
    )
    preflight_path = _resolve(
        repo_root,
        raw_evidence.get("structured_axis_resource_preflight", ""),
    )
    _require(
        actual_result_path == (run_dir / "actual_r5_result.json").resolve(),
        "y-only raw result path is not inside its watchdog run directory",
    )
    raw_result, _ = _load_sha_bound_json(
        actual_result_path,
        raw_evidence.get("actual_r5_result_sha256", ""),
        label="y-only raw actual R5 result",
    )
    raw_preflight, _ = _load_sha_bound_json(
        preflight_path,
        raw_evidence.get("structured_axis_resource_preflight_sha256", ""),
        label="y-only structured-axis preflight artifact",
    )
    _require(
        raw_preflight == preflight,
        "embedded and raw y-only structured-axis preflights differ",
    )
    qualification_checks = (
        (record.get("qualification") or {}).get("checks") or {}
    )
    _require(
        record.get("ordinary_default_changed") is False
        and qualification_checks.get("ordinary_default_unchanged")
        is True
        and raw_result.get("ordinary_default_changed") is False,
        "y-only ordinary-default identity does not close across watchdog, "
        "qualification, and raw result",
    )
    _require(
        raw_result.get("schema_version")
        == "task035.target-actual-global-r5.v1"
        and raw_result.get("status") == "actual_global_r5_pass"
        and raw_result.get("same_mesh_hashes") is True
        and raw_result.get("reuse_single_mesh_requested") is True
        and raw_result.get("single_in_memory_mesh_instance") is True,
        "y-only raw actual R5 result identity mismatch",
    )
    _validate_mesh_identity(
        raw_result.get("common_mesh_identity") or {},
        _EXPECTED_Y_MESH_IDENTITY,
        label="y-only raw result",
    )
    for label, degree, dofs in (
        ("coarse", 4, _EXPECTED_Y_RESOURCES["coarse_p4_dofs"]),
        ("enriched", 5, _EXPECTED_Y_RESOURCES["enriched_p5_dofs"]),
    ):
        entry = raw_result.get(label) or {}
        summary = entry.get("summary") or {}
        _require(
            entry.get("degree") == degree
            and float(entry.get("h_nm", math.nan)) == 15.0,
            f"y-only raw {label} degree/h identity mismatch",
        )
        compact = record.get(label) or {}
        _require(
            summary.get("case_status") == "completed"
            and summary.get("official_result") is True
            and summary.get("mpi_size") == 8
            and summary.get("mesh_cells_resolved") == [6, 3, 10]
            and summary.get("num_mesh_cells") == 180
            and summary.get("num_nedelec_dofs") == dofs
            and (summary.get("config") or {}).get(
                "mesh_axis_cell_counts_requested"
            )
            == [6, 3, 10]
            and _full_true_residual(summary) <= _MAX_TRUE_RESIDUAL
            and summary.get("linear_system_relative_residual")
            == compact.get("linear_system_relative_residual"),
            f"y-only raw {label} solve does not match compact watchdog data",
        )

    enriched_summary = (
        (raw_result.get("enriched") or {}).get("summary") or {}
    )
    orders_filename = enriched_summary.get("dtn_port_orders_json")
    _require(
        orders_filename == "dtn_port_diffraction_orders_3d.json",
        "y-only raw enriched-p5 DtN order filename is not canonical",
    )
    orders_path = (
        run_dir / "enriched_p5" / str(orders_filename)
    ).resolve()
    recorded_orders_path = _resolve(
        repo_root,
        raw_evidence.get("structured_axis_enriched_orders", ""),
    )
    recorded_orders_sha = _validate_sha256(
        raw_evidence.get(
            "structured_axis_enriched_orders_sha256",
            "",
        ),
        label="y-only enriched-p5 DtN orders",
    )
    _require(
        orders_path == recorded_orders_path
        and orders_path.is_file()
        and _sha256(orders_path) == recorded_orders_sha
        and raw_evidence.get(
            "structured_axis_enriched_orders_count"
        )
        == 80
        and raw_evidence.get(
            "structured_axis_enriched_orders_qualified"
        )
        is True,
        "y-only raw enriched-p5 DtN orders are not SHA-bound",
    )
    orders = json.loads(orders_path.read_text(encoding="utf-8"))
    _require(
        isinstance(orders.get("orders"), list)
        and len(orders["orders"]) == 80,
        "y-only raw enriched-p5 authority must contain 80 orders",
    )
    return orders_path, raw_result


def _channel_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(row["side"]),
        int(row["m"]),
        int(row["n"]),
        str(row["polarization"]),
    )


def _normalized_l2(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows]
    _require(
        all(math.isfinite(value) and value >= 0.0 for value in values),
        f"directional normalized error {key} is non-finite or negative",
    )
    result = math.hypot(*values)
    _require(
        math.isfinite(result),
        f"directional normalized L2 {key} is non-finite",
    )
    return result


def _directional_signal(
    seed: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    seed_by_key = {
        _channel_key(row): row for row in seed.get("channels") or []
    }
    candidate_by_key = {
        _channel_key(row): row
        for row in candidate.get("channels") or []
    }
    _require(
        len(seed_by_key) == 12
        and set(seed_by_key) == set(candidate_by_key),
        "seed and y-only comparisons do not share the frozen 12 channels",
    )
    for label, comparison in (
        ("seed", seed),
        ("candidate", candidate),
    ):
        _require(
            comparison.get("schema_version")
            == (
                "task035b.significant-channel-reference-v1-"
                "comparison.v1"
            )
            and comparison.get("frozen_significant_channel_count")
            == 12
            and comparison.get("analytic_channel_identity_pass") is True
            and comparison.get(
                "numerical_convergence_band_used_as_gate"
            )
            is False
            and comparison.get("thresholds_relaxed") is False,
            f"{label} significant-channel comparison identity failed",
        )
    rows: list[dict[str, Any]] = []
    for key in sorted(seed_by_key):
        seed_row = seed_by_key[key]
        candidate_row = candidate_by_key[key]
        power_tolerance = float(
            seed_row["unchanged_v0_power_tolerance"]
        )
        amplitude_tolerance = float(
            seed_row["unchanged_v0_complex_amplitude_tolerance"]
        )
        candidate_power_tolerance = float(
            candidate_row["unchanged_v0_power_tolerance"]
        )
        candidate_amplitude_tolerance = float(
            candidate_row[
                "unchanged_v0_complex_amplitude_tolerance"
            ]
        )
        _require(
            math.isfinite(power_tolerance)
            and power_tolerance > 0.0
            and math.isfinite(amplitude_tolerance)
            and amplitude_tolerance > 0.0
            and math.isfinite(candidate_power_tolerance)
            and candidate_power_tolerance > 0.0
            and math.isfinite(candidate_amplitude_tolerance)
            and candidate_amplitude_tolerance > 0.0
            and power_tolerance == candidate_power_tolerance
            and amplitude_tolerance == candidate_amplitude_tolerance,
            f"frozen tolerances differ for channel {key}",
        )
        seed_power_error = float(
            seed_row["candidate_vs_reference_power_absolute_error"]
        )
        candidate_power_error = float(
            candidate_row[
                "candidate_vs_reference_power_absolute_error"
            ]
        )
        seed_amplitude_error = float(
            seed_row[
                "candidate_vs_reference_amplitude_absolute_error"
            ]
        )
        candidate_amplitude_error = float(
            candidate_row[
                "candidate_vs_reference_amplitude_absolute_error"
            ]
        )
        _require(
            all(
                math.isfinite(value) and value >= 0.0
                for value in (
                    seed_power_error,
                    candidate_power_error,
                    seed_amplitude_error,
                    candidate_amplitude_error,
                )
            ),
            f"directional channel errors are non-finite or negative for {key}",
        )
        pass_flags = (
            seed_row.get("power_pass"),
            candidate_row.get("power_pass"),
            seed_row.get("complex_amplitude_pass"),
            candidate_row.get("complex_amplitude_pass"),
        )
        _require(
            all(isinstance(value, bool) for value in pass_flags),
            f"directional channel pass flags are not boolean for {key}",
        )
        rows.append(
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "seed_power_error_normalized": (
                    seed_power_error / power_tolerance
                ),
                "candidate_power_error_normalized": (
                    candidate_power_error / power_tolerance
                ),
                "seed_amplitude_error_normalized": (
                    seed_amplitude_error / amplitude_tolerance
                ),
                "candidate_amplitude_error_normalized": (
                    candidate_amplitude_error / amplitude_tolerance
                ),
                "seed_power_pass": seed_row["power_pass"],
                "candidate_power_pass": candidate_row["power_pass"],
                "seed_complex_amplitude_pass": seed_row[
                    "complex_amplitude_pass"
                ],
                "candidate_complex_amplitude_pass": candidate_row[
                    "complex_amplitude_pass"
                ],
            }
        )

    seed_power_l2 = _normalized_l2(
        rows,
        "seed_power_error_normalized",
    )
    candidate_power_l2 = _normalized_l2(
        rows,
        "candidate_power_error_normalized",
    )
    seed_amplitude_l2 = _normalized_l2(
        rows,
        "seed_amplitude_error_normalized",
    )
    candidate_amplitude_l2 = _normalized_l2(
        rows,
        "candidate_amplitude_error_normalized",
    )
    seed_power_count = sum(row["seed_power_pass"] for row in rows)
    candidate_power_count = sum(
        row["candidate_power_pass"] for row in rows
    )
    seed_amplitude_count = sum(
        row["seed_complex_amplitude_pass"] for row in rows
    )
    candidate_amplitude_count = sum(
        row["candidate_complex_amplitude_pass"] for row in rows
    )
    power_reduction = (
        (seed_power_l2 - candidate_power_l2)
        / max(seed_power_l2, 1.0e-30)
    )
    amplitude_reduction = (
        (seed_amplitude_l2 - candidate_amplitude_l2)
        / max(seed_amplitude_l2, 1.0e-30)
    )
    _require(
        all(
            math.isfinite(value)
            for value in (
                seed_power_l2,
                candidate_power_l2,
                seed_amplitude_l2,
                candidate_amplitude_l2,
                power_reduction,
                amplitude_reduction,
            )
        ),
        "directional L2 or relative-reduction metric is non-finite",
    )
    failed_power = [
        row for row in rows if not row["seed_power_pass"]
    ]
    failed_amplitude = [
        row
        for row in rows
        if not row["seed_complex_amplitude_pass"]
    ]
    power_improved = sum(
        row["candidate_power_error_normalized"]
        < row["seed_power_error_normalized"]
        for row in failed_power
    )
    amplitude_improved = sum(
        row["candidate_amplitude_error_normalized"]
        < row["seed_amplitude_error_normalized"]
        for row in failed_amplitude
    )
    no_count_regression = bool(
        candidate_power_count >= seed_power_count
        and candidate_amplitude_count >= seed_amplitude_count
    )
    no_material_l2_regression = bool(
        power_reduction >= -_MAX_L2_REGRESSION
        and amplitude_reduction >= -_MAX_L2_REGRESSION
    )
    count_improved = bool(
        candidate_power_count > seed_power_count
        or candidate_amplitude_count > seed_amplitude_count
    )
    material_majority_improvement = bool(
        (
            power_reduction >= _MATERIAL_REDUCTION
            and power_improved > len(failed_power) / 2.0
        )
        or (
            amplitude_reduction >= _MATERIAL_REDUCTION
            and amplitude_improved > len(failed_amplitude) / 2.0
        )
    )
    positive = bool(
        no_count_regression
        and no_material_l2_regression
        and (count_improved or material_majority_improvement)
    )
    return {
        "schema_version": (
            "task035b.y-only-global-p5-directional-signal.v1"
        ),
        "status": (
            "positive_y_directional_control_signal"
            if positive
            else "controlled_negative_y_directional_control_signal"
        ),
        "classification": (
            "positive" if positive else "controlled_negative"
        ),
        "positive_signal": positive,
        "diagnostic_only": True,
        "formal_candidate_eligible": False,
        "seed": "global p5 h15 on exact axis plan (6,2,10)",
        "candidate": "global p5 h15 y-only axis plan (6,3,10)",
        "seed_power_pass_count": seed_power_count,
        "candidate_power_pass_count": candidate_power_count,
        "seed_complex_amplitude_pass_count": seed_amplitude_count,
        "candidate_complex_amplitude_pass_count": (
            candidate_amplitude_count
        ),
        "all_12_normalized_power_l2": {
            "seed": seed_power_l2,
            "candidate": candidate_power_l2,
            "relative_reduction": power_reduction,
        },
        "all_12_normalized_complex_amplitude_l2": {
            "seed": seed_amplitude_l2,
            "candidate": candidate_amplitude_l2,
            "relative_reduction": amplitude_reduction,
        },
        "seed_failed_power_channel_count": len(failed_power),
        "seed_failed_complex_amplitude_channel_count": len(
            failed_amplitude
        ),
        "seed_failed_power_normalized_l2": _normalized_l2(
            failed_power,
            "seed_power_error_normalized",
        ),
        "candidate_on_seed_failed_power_normalized_l2": (
            _normalized_l2(
                failed_power,
                "candidate_power_error_normalized",
            )
        ),
        "seed_failed_amplitude_normalized_l2": _normalized_l2(
            failed_amplitude,
            "seed_amplitude_error_normalized",
        ),
        "candidate_on_seed_failed_amplitude_normalized_l2": (
            _normalized_l2(
                failed_amplitude,
                "candidate_amplitude_error_normalized",
            )
        ),
        "power_improved_seed_failed_channel_count": power_improved,
        "amplitude_improved_seed_failed_channel_count": (
            amplitude_improved
        ),
        "no_count_regression": no_count_regression,
        "no_material_l2_regression": no_material_l2_regression,
        "count_improved": count_improved,
        "material_majority_improvement": (
            material_majority_improvement
        ),
        "classification_thresholds": {
            "minimum_material_relative_reduction": (
                _MATERIAL_REDUCTION
            ),
            "maximum_allowed_l2_regression": _MAX_L2_REGRESSION,
            "acceptance_gate_unchanged": True,
            "thresholds_relaxed": False,
        },
        "normalization": (
            "unchanged v0 per-channel h10 p5-to-p6 Gate tolerance"
        ),
        "channels": rows,
    }


def _build_y_directional_control_payload(
    *,
    repo_root: Path,
    y_control_record_path: Path,
    y_control_record_sha256: str,
    reference_record_path: Path,
    reference_record_sha256: str,
    h15_p5_baseline_record_path: Path,
    h15_p5_baseline_record_sha256: str,
) -> dict[str, Any]:
    """Validate all authorities and classify the y-only p5 control."""

    root = Path(repo_root).resolve()
    y_path = _resolve(root, y_control_record_path)
    reference_path = _resolve(root, reference_record_path)
    baseline_path = _resolve(root, h15_p5_baseline_record_path)
    y_record, y_sha = _load_sha_bound_json(
        y_path,
        y_control_record_sha256,
        label="y-only watchdog record",
    )
    reference, reference_sha = _load_sha_bound_json(
        reference_path,
        reference_record_sha256,
        label="significant-channel reference v1",
    )
    baseline, baseline_sha = _load_sha_bound_json(
        baseline_path,
        h15_p5_baseline_record_sha256,
        label="h15 global-p5 baseline record",
    )
    baseline_orders = _validate_h15_baseline(
        repo_root=root,
        record_path=baseline_path,
        record=baseline,
        record_sha256=baseline_sha,
        reference=reference,
    )
    y_orders, raw_y_result = _validate_y_control(
        repo_root=root,
        record=y_record,
    )
    seed_comparison = compare_significant_channels_to_reference_v1(
        candidate_path=baseline_orders,
        reference_record_path=reference_path,
        reference_record_sha256=reference_sha,
    )
    candidate_comparison = (
        compare_significant_channels_to_reference_v1(
            candidate_path=y_orders,
            reference_record_path=reference_path,
            reference_record_sha256=reference_sha,
        )
    )
    signal = _directional_signal(
        seed_comparison,
        candidate_comparison,
    )
    qualification_checks = {
        "y_watchdog_record_sha_bound": _sha256(y_path) == y_sha,
        "reference_v1_record_sha_bound": (
            _sha256(reference_path) == reference_sha
        ),
        "h15_p5_baseline_record_sha_bound": (
            _sha256(baseline_path) == baseline_sha
        ),
        "reference_binds_baseline_and_raw_orders": (
            seed_comparison.get("candidate_authority", {}).get(
                "sha256"
            )
            == _sha256(baseline_orders)
        ),
        "fixed_rectangular_target_identity": (
            y_record.get("target_identity") == _FIXED_TARGET_IDENTITY
        ),
        "only_y_axis_changed": (
            signal.get("candidate")
            == "global p5 h15 y-only axis plan (6,3,10)"
        ),
        "exact_axis_plan_6_3_10": (
            (
                y_record.get("common_mesh_identity") or {}
            ).get("mesh_cells_resolved")
            == [6, 3, 10]
        ),
        "mesh_and_tag_hashes_frozen": all(
            (
                y_record.get("common_mesh_identity") or {}
            ).get(key)
            == value
            for key, value in _EXPECTED_Y_MESH_IDENTITY.items()
        ),
        "global_p4_p5_pair": (
            (y_record.get("coarse") or {}).get("degree") == 4
            and (y_record.get("enriched") or {}).get("degree") == 5
        ),
        "mpi8": all(
            (y_record.get(label) or {}).get("mpi_size") == 8
            for label in ("coarse", "enriched")
        ),
        "full_explicit_true_residuals_le_1e_9": all(
            _full_true_residual(y_record.get(label) or {})
            <= _MAX_TRUE_RESIDUAL
            for label in ("coarse", "enriched")
        ),
        "watchdog_and_raw_result_consistent": (
            raw_y_result.get("common_mesh_identity")
            == y_record.get("common_mesh_identity")
        ),
        "raw_enriched_p5_orders_read": (
            candidate_comparison.get("candidate_authority", {}).get(
                "sha256"
            )
            == _sha256(y_orders)
        ),
        "frozen_12_channel_gate_unmodified": all(
            comparison.get("frozen_significant_channel_count") == 12
            and comparison.get("analytic_channel_identity_pass") is True
            and comparison.get("thresholds_relaxed") is False
            and comparison.get(
                "numerical_convergence_band_used_as_gate"
            )
            is False
            for comparison in (
                seed_comparison,
                candidate_comparison,
            )
        ),
        "diagnostic_only": (
            (
                y_record.get(
                    "structured_axis_control_classification"
                )
                or {}
            ).get("diagnostic_only")
            is True
        ),
        "formal_candidate_eligible_false": (
            (
                y_record.get(
                    "structured_axis_control_classification"
                )
                or {}
            ).get("formal_candidate_eligible")
            is False
        ),
    }
    failures = [
        name
        for name, passed in qualification_checks.items()
        if not passed
    ]
    if failures:
        raise ValueError(
            "y-only comparison qualification failed: "
            + ", ".join(failures)
        )
    return {
        "schema_version": (
            "task035b.y-only-global-p5-directional-control-comparison.v1"
        ),
        "status": signal["status"],
        "classification": signal["classification"],
        "diagnostic_only": True,
        "formal_candidate_eligible": False,
        "ordinary_default_changed": False,
        "thresholds_relaxed": False,
        "geometry_scope": "Task034 fixed rectangular block grating",
        "purpose": (
            "measure whether y-only structured-h changes the frozen "
            "significant-channel errors; never qualifies a final candidate"
        ),
        "qualification": {
            "pass": not failures,
            "checks": qualification_checks,
            "failures": failures,
        },
        "authorities": {
            "y_control_watchdog": {
                "path": _display_path(root, y_path),
                "sha256": y_sha,
                "source_commit_sha": (
                    (y_record.get("source") or {}).get("commit_sha")
                ),
            },
            "y_control_raw_result": {
                "path": _display_path(
                    root,
                    _resolve(
                        root,
                        (y_record.get("raw_evidence") or {}).get(
                            "actual_r5_result",
                            "",
                        ),
                    ),
                ),
                "sha256": (
                    (y_record.get("raw_evidence") or {}).get(
                        "actual_r5_result_sha256"
                    )
                ),
                "schema_version": raw_y_result.get("schema_version"),
            },
            "y_control_raw_enriched_p5_orders": {
                "path": _display_path(root, y_orders),
                "sha256": _sha256(y_orders),
                "order_count": 80,
            },
            "significant_channel_reference_v1": {
                "path": _display_path(root, reference_path),
                "sha256": reference_sha,
                "reference_payload_sha256": reference.get(
                    "reference_payload_sha256"
                ),
            },
            "h15_global_p5_baseline": {
                "path": _display_path(root, baseline_path),
                "sha256": baseline_sha,
                "source_commit_sha": (
                    (baseline.get("source") or {}).get("commit_sha")
                ),
            },
            "h15_global_p5_raw_orders": {
                "path": _display_path(root, baseline_orders),
                "sha256": _sha256(baseline_orders),
                "order_count": 80,
            },
        },
        "mesh_directional_identity": {
            "seed_axis_cells": [6, 2, 10],
            "candidate_axis_cells": [6, 3, 10],
            "seed_axis_sha256": _H15_AXIS_SHA256,
            "candidate_axis_sha256": _Y_AXIS_SHA256,
            "changed_axes": ["y"],
            "candidate_mesh_identity": _EXPECTED_Y_MESH_IDENTITY,
        },
        "seed_significant_channel_comparison": seed_comparison,
        "candidate_significant_channel_comparison": (
            candidate_comparison
        ),
        "directional_signal": signal,
    }


def _bind_comparator_source(
    record: dict[str, Any],
    *,
    source: dict[str, Any],
    source_file_sha256: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Bind a completed read-only comparison to its own source authority."""

    qualified_source = _validated_comparator_source(source)
    hashes = (
        _source_file_sha256()
        if source_file_sha256 is None
        else dict(source_file_sha256)
    )
    if set(hashes) != set(SOURCE_FILES) or any(
        len(str(value)) != 64
        or any(
            character not in "0123456789abcdef"
            for character in str(value).lower()
        )
        for value in hashes.values()
    ):
        raise ValueError(
            "y-only comparator source-file hashes are incomplete or invalid"
        )
    result = dict(record)
    qualification = dict(result.get("qualification") or {})
    checks = dict(qualification.get("checks") or {})
    checks.update(
        {
            "comparator_source_identity_hash_bound": True,
            "comparator_source_files_hash_bound": True,
            "comparator_source_stable_and_clean_after": True,
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    qualification.update(
        {
            "pass": not failures,
            "checks": checks,
            "failures": failures,
        }
    )
    result.update(
        {
            "source": qualified_source,
            "source_file_sha256": hashes,
            "qualification": qualification,
        }
    )
    return result


def build_y_directional_control_comparison(
    *,
    repo_root: Path,
    y_control_record_path: Path,
    y_control_record_sha256: str,
    reference_record_path: Path,
    reference_record_sha256: str,
    h15_p5_baseline_record_path: Path,
    h15_p5_baseline_record_sha256: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Validate authorities, classify the y lane, and bind clean source."""

    record = _build_y_directional_control_payload(
        repo_root=repo_root,
        y_control_record_path=y_control_record_path,
        y_control_record_sha256=y_control_record_sha256,
        reference_record_path=reference_record_path,
        reference_record_sha256=reference_record_sha256,
        h15_p5_baseline_record_path=h15_p5_baseline_record_path,
        h15_p5_baseline_record_sha256=(
            h15_p5_baseline_record_sha256
        ),
    )
    return _bind_comparator_source(record, source=source)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Strictly postprocess the Task035b y-only global-p5 "
            "directional control; no PDE is run."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
    )
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--y-control-record", type=Path, required=True)
    parser.add_argument(
        "--y-control-record-sha256",
        required=True,
    )
    parser.add_argument(
        "--reference-record",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--reference-record-sha256",
        required=True,
    )
    parser.add_argument(
        "--h15-p5-baseline-record",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--h15-p5-baseline-record-sha256",
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.repo_root.resolve()
    output = _resolve(root, args.output)
    if output in {
        _resolve(root, args.y_control_record),
        _resolve(root, args.reference_record),
        _resolve(root, args.h15_p5_baseline_record),
    }:
        raise ValueError("output must not overwrite an input authority")
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing evidence: {output}"
        )

    source_before = _verified_source_identity(
        root,
        args.verified_clean_sha,
    )
    record = _build_y_directional_control_payload(
        repo_root=root,
        y_control_record_path=args.y_control_record,
        y_control_record_sha256=args.y_control_record_sha256,
        reference_record_path=args.reference_record,
        reference_record_sha256=args.reference_record_sha256,
        h15_p5_baseline_record_path=args.h15_p5_baseline_record,
        h15_p5_baseline_record_sha256=(
            args.h15_p5_baseline_record_sha256
        ),
    )
    source_hashes = _source_file_sha256()
    source_after = _reverify_source_before_write(root, source_before)
    source = {
        **source_before,
        **{
            key: value
            for key, value in source_after.items()
            if key != "checks"
        },
        "checks": {
            **(source_before.get("checks") or {}),
            **(source_after.get("checks") or {}),
        },
    }
    record = _bind_comparator_source(
        record,
        source=source,
        source_file_sha256=source_hashes,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
