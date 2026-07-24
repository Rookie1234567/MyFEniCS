"""Postprocess a future global-p6/h14 trace discriminator for Task035b.

The tool is deliberately diagnostic-only.  It consumes one completed MPI8
global-p5/p6 h14 watchdog plus frozen existing authorities, reads the raw p6
orders and field shards, and never launches a PDE solve.  Global p6/h14 has
92,850 Full3D-equivalent DoF, so even a 12/12 result can only support the
physics of a later selective-trace lane; it is never itself a <=90k candidate.
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

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.adaptivity.high_order_same_error import (
    compare_cross_mesh_fields,
    compare_observables,
    compare_significant_channels_to_reference_v1,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
RECORDS = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
DEFAULT_OUTPUT = RECORDS / "global_p6_h14_trace_discriminator.json"
REFERENCE_PATH = RECORDS / "significant_channel_reference_v1.json"
REFERENCE_SHA256 = (
    "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3"
)
FIXED_H14_PATH = (
    RECORDS / "fixed_p5trace_p6interior_h14_directional_z_mpi8.json"
)
FIXED_H14_SHA256 = (
    "e93f50155b3c8517292794cb9735730ebf738410aecafe00f43f7959c150a127"
)
H10_CONTROL_PATH = (
    RECORDS
    / "global_hexa_p5_p6_h10_assembly_time_condensed_independent_mpi8.json"
)
H10_CONTROL_SHA256 = (
    "9f7f44efb52b44c587ef59a57524849e08da81a6fcd5d90ec18e7b69e4f33ded"
)
SOURCE_FILES = (
    "benchmarks/task035b_global_p6_h14_trace_discriminator.py",
    "src/adaptivity/high_order_same_error.py",
)
EXPECTED_AXIS_CELLS = [6, 2, 11]
EXPECTED_GLOBAL_CELLS = 132
EXPECTED_GLOBAL_P5_DOFS = 54_595
EXPECTED_GLOBAL_P6_DOFS = 92_850
EXPECTED_GLOBAL_P5_ROWS = 18_500
EXPECTED_GLOBAL_P6_ROWS = 27_080
EXPECTED_FIXED_H14_DOFS = 82_315
FULL3D_EQUIVALENT_DOF_LIMIT = 90_000
EXPECTED_MPI_SIZE = 8
MAX_TRUE_RESIDUAL = 1.0e-9
EXPECTED_FIELD_SHARDS = 8
_FIXED_TARGET_IDENTITY = {
    "wavelength_nm": 13.5,
    "incidence_theta_deg": 80.0,
    "grazing_angle_deg": 10.0,
    "polarization": "S",
    "geometry": "Task034 fixed rectangular block grating",
    "mesh_backend": "boundary-fitted conforming hexahedron",
}


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


def _full_git_sha(value: Any) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 40 and all(
        character in "0123456789abcdef"
        for character in normalized
    )


def _full_sha256(value: Any) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef"
        for character in normalized
    )


def _resolve(repo_root: Path, path: Path | str) -> Path:
    result = Path(path)
    if not result.is_absolute():
        result = repo_root / result
    return result.resolve()


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


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
            "global-p6/h14 discriminator source gate failed: "
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


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": np.dtype(PETSc.ScalarType)
        == np.dtype(np.complex128),
        "int32_petsc": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "serial_postprocess_only": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "global-p6/h14 discriminator environment gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
    }


def _source_file_sha256(repo_root: Path) -> dict[str, str]:
    return {path: _sha256(repo_root / path) for path in SOURCE_FILES}


def _reverify_after_build(
    repo_root: Path,
    source_before: Mapping[str, Any],
    source_hashes_before: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    hashes_after = _source_file_sha256(repo_root)
    checks = {
        "head_stable_after_build": head == source_before.get("commit_sha"),
        "branch_stable_after_build": (
            branch == source_before.get("branch") == EXPECTED_BRANCH
        ),
        "tracked_and_untracked_worktree_clean_after_build": status == "",
        "source_file_hashes_stable_after_build": (
            hashes_after == dict(source_hashes_before)
        ),
    }
    if not all(checks.values()):
        raise SystemExit(
            "global-p6/h14 source changed during postprocessing: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return (
        {
            "head_after_sha": head,
            "branch_after": branch,
            "status_after_before_record_write": status,
            "stable_and_clean_after": True,
            "checks": checks,
        },
        hashes_after,
    )


def _qualified_output_source(source: Mapping[str, Any]) -> dict[str, Any]:
    checks = source.get("checks")
    if not (
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
    ):
        raise ValueError("output source identity is unqualified")
    return dict(source)


def _load_sha_bound_json(
    repo_root: Path,
    path: Path | str,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = str(expected_sha256).lower()
    if not _full_sha256(expected):
        raise ValueError(f"{label} expected SHA256 is invalid")
    resolved = _resolve(repo_root, path)
    if not resolved.is_file():
        raise ValueError(f"{label} is unreadable: {resolved}")
    actual = _sha256(resolved)
    if actual != expected:
        raise ValueError(
            f"{label} SHA256 mismatch: expected {expected}, got {actual}"
        )
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload, {
        "path": _display_path(repo_root, resolved),
        "sha256": actual,
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "source_commit_sha": (payload.get("source") or {}).get("commit_sha"),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _finite(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive(value: Any, *, label: str) -> float:
    result = _finite(value, label=label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _qualified_record_source(
    record: Mapping[str, Any],
    *,
    label: str,
) -> None:
    source = record.get("source")
    _require(isinstance(source, Mapping), f"{label} source is absent")
    commit = source.get("commit_sha")
    _require(_full_git_sha(commit), f"{label} source SHA is invalid")
    _require(
        commit == source.get("verified_clean_sha")
        and source.get("tracked_source_dirty") is False
        and source.get("head_after_sha") == commit
        and source.get("status_after_before_record_write") == ""
        and source.get("stable_and_clean_after") is True,
        f"{label} source was not clean and stable",
    )


def _qualification_pass(record: Mapping[str, Any], *, label: str) -> None:
    qualification = record.get("qualification")
    checks = (
        qualification.get("checks")
        if isinstance(qualification, Mapping)
        else None
    )
    _require(
        isinstance(qualification, Mapping)
        and qualification.get("pass") is True
        and qualification.get("failures") == []
        and isinstance(checks, Mapping)
        and bool(checks)
        and all(value is True for value in checks.values()),
        f"{label} qualification failed",
    )
    _require(
        record.get("terminated_for_memory") is False
        and record.get("terminated_for_timeout") is False,
        f"{label} terminated before completion",
    )
    _qualified_record_source(record, label=label)


def _true_residual(result: Mapping[str, Any], *, label: str) -> float:
    residual = (
        (result.get("cell_static_condensation") or {})
        .get("full_explicit_true_residual", {})
        .get("linear_system_relative_residual")
    )
    value = _finite(residual, label=f"{label}.true_residual")
    _require(
        0.0 <= value <= MAX_TRUE_RESIDUAL,
        f"{label} full explicit true residual exceeds 1e-9",
    )
    return value


def _mesh_identity_from_fixed(
    fixed_record: Mapping[str, Any],
) -> Mapping[str, Any]:
    return (
        ((fixed_record.get("candidate") or {}).get("high_order_resource_audit")
        or {}).get("mesh_identity")
        or {}
    )


def _validate_global_h14_record(
    record: Mapping[str, Any],
) -> Mapping[str, Any]:
    _require(
        record.get("schema_version")
        == "task035.actual-global-r5-watchdog.v1"
        and record.get("status") == "actual_global_r5_pass",
        "global-p6/h14 watchdog schema or status is invalid",
    )
    _qualification_pass(record, label="global_p6_h14")
    qualification_checks = record["qualification"]["checks"]
    required_requested_checks = {
        "requested_static_condensation_active",
        "requested_condensed_rows_physically_measured",
        "requested_full_residual_audit_present",
        "requested_floquet_slave_elimination_active",
        "requested_floquet_slave_rows_physically_removed",
        "requested_assembly_time_condensation_active",
        "requested_full_matrices_never_allocated",
        "requested_matrix_free_full_residual_present",
        "requested_global_pair_solve_artifacts_hash_bound",
    }
    _require(
        all(
            qualification_checks.get(name) is True
            for name in required_requested_checks
        ),
        "global-p6/h14 omitted a required condensation, Floquet, residual, "
        "or raw-artifact request",
    )
    _require(
        record.get("target_identity") == _FIXED_TARGET_IDENTITY,
        "global-p6/h14 target identity differs from Task034 fixed block",
    )
    mesh = record.get("common_mesh_identity")
    _require(isinstance(mesh, Mapping), "global-p6/h14 mesh identity is absent")
    _require(
        mesh.get("mesh_cell_type") == "hexahedron"
        and mesh.get("global_cell_count") == EXPECTED_GLOBAL_CELLS
        and mesh.get("mesh_cells_resolved") == EXPECTED_AXIS_CELLS
        and (mesh.get("material_plane_alignment") or {}).get("all_aligned")
        is True,
        "global-p6/h14 is not the exact (6,2,11), 132-cell mesh",
    )
    coarse = record.get("coarse")
    enriched = record.get("enriched")
    _require(
        isinstance(coarse, Mapping) and isinstance(enriched, Mapping),
        "global-p6/h14 p5/p6 summaries are absent",
    )
    for label, result, degree, dofs, rows in (
        (
            "global_h14_p5",
            coarse,
            5,
            EXPECTED_GLOBAL_P5_DOFS,
            EXPECTED_GLOBAL_P5_ROWS,
        ),
        (
            "global_h14_p6",
            enriched,
            6,
            EXPECTED_GLOBAL_P6_DOFS,
            EXPECTED_GLOBAL_P6_ROWS,
        ),
    ):
        cell_condensation = result.get("cell_static_condensation") or {}
        floquet = cell_condensation.get("floquet_slave_elimination") or {}
        matrix = result.get(
            "stage4_dtn_floquet_independent_matrix_stats"
        ) or {}
        _require(
            result.get("degree") == degree
            and _finite(result.get("h_nm"), label=f"{label}.h_nm") == 14.0
            and result.get("official_result") is True
            and result.get("mpi_size") == EXPECTED_MPI_SIZE
            and result.get("num_mesh_cells") == EXPECTED_GLOBAL_CELLS
            and result.get("num_nedelec_dofs") == dofs
            and result.get("mesh_cell_type_actual") == "hexahedron",
            f"{label} formal identity is invalid",
        )
        _require(
            result.get("stage4_cell_static_condensation") is True
            and result.get(
                "stage4_assembly_time_cell_static_condensation"
            )
            is True
            and result.get("stage4_floquet_slave_elimination") is True
            and cell_condensation.get("matrix_rows") == rows
            and matrix.get("matrix_rows") == rows
            and cell_condensation.get("full_global_matrix_allocated") is False
            and cell_condensation.get("full_trace_matrix_allocated") is False
            and cell_condensation.get(
                "embedded_mpc_slave_identity_rows_allocated"
            )
            is False
            and floquet.get("constraint_applied_before_global_matrix_insertion")
            is True
            and floquet.get("embedded_identity_slave_rows_allocated") is False,
            f"{label} is not the required physically reduced trace operator",
        )
        _true_residual(result, label=label)
    _require(
        record.get("same_mesh_hashes") is True
        and record.get("single_in_memory_mesh_instance") is True
        and record.get("reuse_single_mesh_requested") is True,
        "global p5/p6 h14 did not use one identical mesh",
    )
    return mesh


def _validate_fixed_h14_record(
    record: Mapping[str, Any],
) -> Mapping[str, Any]:
    _require(
        record.get("schema_version") == "task035b.fixed-trace-watchdog.v1"
        and record.get("status") == "actual_fixed_trace_controlled_negative",
        "fixed h14 authority schema or status is invalid",
    )
    _qualification_pass(record, label="fixed_h14")
    result = record.get("candidate")
    _require(isinstance(result, Mapping), "fixed h14 candidate is absent")
    _require(
        result.get("official_result") is True
        and result.get("mpi_size") == EXPECTED_MPI_SIZE
        and result.get("num_mesh_cells") == EXPECTED_GLOBAL_CELLS
        and result.get("num_nedelec_dofs") == EXPECTED_FIXED_H14_DOFS
        and result.get("nedelec_trace_degree_resolved") == 5
        and result.get("nedelec_interior_degree_resolved") == 6,
        "fixed h14 trace-p5/interior-p6 identity is invalid",
    )
    _true_residual(result, label="fixed_h14")
    mesh = _mesh_identity_from_fixed(record)
    _require(
        mesh.get("global_cell_count") == EXPECTED_GLOBAL_CELLS
        and mesh.get("mesh_cells_resolved") == EXPECTED_AXIS_CELLS
        and (mesh.get("material_plane_alignment") or {}).get("all_aligned")
        is True,
        "fixed h14 mesh identity is invalid",
    )
    comparison = record.get("diffraction_channel_comparison")
    field = record.get("selected_field_interface_error_gate")
    scalar = record.get("observable_comparison")
    _require(
        isinstance(comparison, Mapping)
        and comparison.get("frozen_significant_channel_count") == 12
        and comparison.get("analytic_channel_identity_pass") is True
        and comparison.get("thresholds_relaxed") is False,
        "fixed h14 frozen-channel comparison is invalid",
    )
    _require(
        isinstance(field, Mapping)
        and field.get("schema_version")
        == "task035b.cross-mesh-field-comparison.v1"
        and field.get("no_threshold_relaxation") is True,
        "fixed h14 selected-field comparison is invalid",
    )
    _require(
        isinstance(scalar, Mapping)
        and scalar.get("schema_version")
        == "task035b.cross-mesh-observable-comparison.v1",
        "fixed h14 scalar comparison is invalid",
    )
    return mesh


def _validate_h10_control(record: Mapping[str, Any]) -> None:
    _require(
        record.get("schema_version")
        == "task035.actual-global-r5-watchdog.v1"
        and record.get("status") == "actual_global_r5_pass",
        "h10 p5/p6 control schema or status is invalid",
    )
    _qualification_pass(record, label="h10_control")
    for label, degree in (("coarse", 5), ("enriched", 6)):
        result = record.get(label)
        _require(
            isinstance(result, Mapping)
            and result.get("degree") == degree
            and result.get("official_result") is True
            and result.get("mpi_size") == EXPECTED_MPI_SIZE,
            f"h10 control {label} identity is invalid",
        )
        _true_residual(result, label=f"h10_control.{label}")


def _raw_run_directory(
    repo_root: Path,
    record: Mapping[str, Any],
    *,
    label: str,
) -> tuple[Path, Mapping[str, Any]]:
    raw = record.get("raw_evidence")
    _require(isinstance(raw, Mapping), f"{label} raw evidence is absent")
    run_dir = _resolve(repo_root, raw.get("run_directory"))
    actual_path = _resolve(repo_root, raw.get("actual_r5_result"))
    expected = raw.get("actual_r5_result_sha256")
    _require(
        _full_sha256(expected)
        and actual_path.is_file()
        and _sha256(actual_path) == expected,
        f"{label} raw actual-R5 result is not SHA-bound",
    )
    actual = json.loads(actual_path.read_text(encoding="utf-8"))
    _require(
        actual.get("common_mesh_identity")
        == record.get("common_mesh_identity"),
        f"{label} raw result mesh differs from watchdog",
    )
    _require(run_dir.is_dir(), f"{label} run directory is absent")
    return run_dir, actual


def _validate_solve_artifact_manifest(
    repo_root: Path,
    record: Mapping[str, Any],
    run_dir: Path,
) -> Mapping[str, Any]:
    raw = record.get("raw_evidence") or {}
    manifest = raw.get("global_pair_solve_artifact_manifest")
    _require(
        isinstance(manifest, Mapping)
        and manifest.get("schema_version")
        == "task035b.global-pair-solve-artifact-manifest.v1"
        and manifest.get("requested") is True
        and manifest.get("pass") is True
        and all(
            value is True
            for value in (manifest.get("checks") or {}).values()
        ),
        "global-p6/h14 raw solve-artifact manifest is unqualified",
    )
    levels = manifest.get("levels")
    _require(
        isinstance(levels, Mapping)
        and set(levels) == {"coarse_p5", "enriched_p6"},
        "global-p6/h14 raw solve-artifact levels are incomplete",
    )
    all_files: list[dict[str, Any]] = []
    for level_name in ("coarse_p5", "enriched_p6"):
        level = levels[level_name]
        directory = (run_dir / level_name).resolve()
        _require(
            isinstance(level, Mapping)
            and level.get("pass") is True
            and all(
                value is True
                for value in (level.get("checks") or {}).values()
            )
            and _resolve(repo_root, level.get("directory")) == directory,
            f"{level_name} raw solve-artifact level is unqualified",
        )
        file_rows = [
            ("run_summary", level.get("run_summary")),
            ("dtn_port_orders", level.get("dtn_port_orders")),
        ]
        field_block = level.get("field_shards")
        _require(
            isinstance(field_block, Mapping)
            and field_block.get("shard_count") == EXPECTED_FIELD_SHARDS
            and isinstance(field_block.get("shards"), list)
            and len(field_block["shards"]) == EXPECTED_FIELD_SHARDS,
            f"{level_name} field-shard manifest is incomplete",
        )
        file_rows.extend(
            ("field_shard", row) for row in field_block["shards"]
        )
        expected_paths = {
            "run_summary": {directory / "run_summary.json"},
            "dtn_port_orders": {
                directory / "dtn_port_diffraction_orders_3d.json"
            },
            "field_shard": {
                directory
                / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
                for rank in range(EXPECTED_FIELD_SHARDS)
            },
        }
        observed_paths: dict[str, set[Path]] = {
            role: set() for role in expected_paths
        }
        verified_files: list[dict[str, Any]] = []
        for role, row in file_rows:
            _require(
                isinstance(row, Mapping)
                and _full_sha256(row.get("sha256")),
                f"{level_name} {role} is not SHA-bound",
            )
            path = _resolve(repo_root, row["path"])
            observed_paths[role].add(path)
            try:
                path.relative_to(directory)
            except ValueError as error:
                raise ValueError(
                    f"{level_name} {role} escaped its raw directory"
                ) from error
            _require(
                path.is_file()
                and path.stat().st_size == row.get("size_bytes")
                and _sha256(path) == row.get("sha256"),
                f"{level_name} {role} differs from the watchdog manifest",
            )
            verified_files.append(
                {
                    "role": role,
                    "path": row["path"],
                    "sha256": row["sha256"],
                    "size_bytes": row["size_bytes"],
                }
            )
        _require(
            observed_paths == expected_paths,
            f"{level_name} raw solve-artifact paths are noncanonical",
        )
        level_digest = hashlib.sha256(
            json.dumps(
                verified_files,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        _require(
            level_digest == level.get("files_manifest_sha256"),
            f"{level_name} file-manifest digest differs",
        )
        all_files.extend(
            {"level": level_name, **row} for row in verified_files
        )
    global_digest = hashlib.sha256(
        json.dumps(
            all_files,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _require(
        global_digest == manifest.get("files_manifest_sha256"),
        "global-p6/h14 solve-artifact manifest digest differs",
    )
    return manifest


def _artifact_identity(
    repo_root: Path,
    row: Mapping[str, Any],
    *,
    label: str,
) -> tuple[str, str, int]:
    """Normalize one postprocess/watchdog artifact identity."""

    _require(
        isinstance(row, Mapping)
        and isinstance(row.get("path"), (str, Path))
        and _full_sha256(row.get("sha256"))
        and isinstance(row.get("size_bytes"), int)
        and row["size_bytes"] >= 0,
        f"{label} artifact identity is incomplete",
    )
    return (
        str(_resolve(repo_root, row["path"])),
        str(row["sha256"]).lower(),
        int(row["size_bytes"]),
    )


def _validate_postprocess_authorities_against_manifest(
    repo_root: Path,
    manifest: Mapping[str, Any],
    raw_authorities: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind every enriched-p6 postprocess input to the watchdog manifest."""

    levels = manifest.get("levels")
    _require(
        isinstance(levels, Mapping)
        and isinstance(levels.get("enriched_p6"), Mapping),
        "watchdog manifest lacks the enriched-p6 level",
    )
    enriched = levels["enriched_p6"]
    field_block = enriched.get("field_shards")
    raw_fields = raw_authorities.get("enriched_p6_fields")
    _require(
        isinstance(field_block, Mapping)
        and isinstance(field_block.get("shards"), list)
        and isinstance(raw_fields, Mapping)
        and isinstance(raw_fields.get("shards"), list),
        "enriched-p6 field authorities are incomplete",
    )
    watchdog_fields = sorted(
        _artifact_identity(
            repo_root,
            row,
            label="watchdog enriched-p6 field",
        )
        for row in field_block["shards"]
    )
    postprocess_fields = sorted(
        _artifact_identity(
            repo_root,
            row,
            label="postprocess enriched-p6 field",
        )
        for row in raw_fields["shards"]
    )
    checks = {
        "summary_path_size_sha_match_watchdog_manifest": (
            _artifact_identity(
                repo_root,
                raw_authorities.get("enriched_p6_summary") or {},
                label="postprocess enriched-p6 summary",
            )
            == _artifact_identity(
                repo_root,
                enriched.get("run_summary") or {},
                label="watchdog enriched-p6 summary",
            )
        ),
        "orders_path_size_sha_match_watchdog_manifest": (
            _artifact_identity(
                repo_root,
                raw_authorities.get("enriched_p6_orders") or {},
                label="postprocess enriched-p6 orders",
            )
            == _artifact_identity(
                repo_root,
                enriched.get("dtn_port_orders") or {},
                label="watchdog enriched-p6 orders",
            )
        ),
        "eight_field_path_size_sha_rows_match_watchdog_manifest": (
            len(watchdog_fields) == EXPECTED_FIELD_SHARDS
            and postprocess_fields == watchdog_fields
        ),
    }
    _require(
        all(checks.values()),
        "postprocess authorities differ from the watchdog manifest",
    )
    return {
        "pass": True,
        "checks": checks,
        "watchdog_files_manifest_sha256": manifest.get(
            "files_manifest_sha256"
        ),
    }


def _load_summary(
    run_dir: Path,
    level: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = run_dir / level / "run_summary.json"
    if not path.is_file():
        raise ValueError(f"missing raw solver summary: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"raw solver summary is not an object: {path}")
    return payload, {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _validate_raw_candidate_summary(
    *,
    summary: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    fixed_mesh: Mapping[str, Any],
) -> None:
    enriched = watchdog["enriched"]
    _require(
        summary.get("nedelec_degree") == 6
        and summary.get("num_nedelec_dofs") == EXPECTED_GLOBAL_P6_DOFS
        and summary.get("num_mesh_cells") == EXPECTED_GLOBAL_CELLS,
        "raw enriched-p6 summary is not global p6/h14",
    )
    _require(
        summary.get("mesh_cells_resolved") == EXPECTED_AXIS_CELLS
        and summary.get("mesh_cell_type_actual") == "hexahedron"
        and (summary.get("mesh_material_plane_alignment") or {}).get(
            "all_aligned"
        )
        is True
        and fixed_mesh.get("global_cell_count") == EXPECTED_GLOBAL_CELLS,
        "raw enriched-p6 summary mesh identity is invalid",
    )
    for key in (
        "num_nedelec_dofs",
        "R00_total",
        "R_total",
        "T_total",
        "linear_system_relative_residual",
    ):
        left = _finite(summary.get(key), label=f"raw_p6.{key}")
        right = _finite(enriched.get(key), label=f"watchdog_p6.{key}")
        _require(
            math.isclose(left, right, rel_tol=0.0, abs_tol=1.0e-14),
            f"raw enriched-p6 summary differs from watchdog for {key}",
        )
    summary_matrix = summary.get(
        "stage4_dtn_floquet_independent_matrix_stats"
    ) or {}
    watchdog_matrix = enriched.get(
        "stage4_dtn_floquet_independent_matrix_stats"
    ) or {}
    summary_factor = (
        (summary.get("stage4_dtn_factor_inventory") or {}).get(
            "matrix_stats"
        )
        or {}
    )
    watchdog_factor = (
        (enriched.get("stage4_dtn_factor_inventory") or {}).get(
            "matrix_stats"
        )
        or {}
    )
    for key in ("matrix_rows", "matrix_nnz_used"):
        _require(
            _finite(summary_matrix.get(key), label=f"raw matrix {key}")
            == _finite(
                watchdog_matrix.get(key),
                label=f"watchdog matrix {key}",
            ),
            f"raw enriched-p6 matrix differs from watchdog for {key}",
        )
    _require(
        _finite(
            summary_factor.get("matrix_nnz_used"),
            label="raw factor nnz",
        )
        == _finite(
            watchdog_factor.get("matrix_nnz_used"),
            label="watchdog factor nnz",
        ),
        "raw enriched-p6 factor inventory differs from watchdog",
    )
    _true_residual(summary, label="raw_global_h14_p6")


def _field_manifest(directory: Path) -> dict[str, Any]:
    paths = sorted(directory.glob("fields_3d_for_paraview_rank*.vtu"))
    if len(paths) != EXPECTED_FIELD_SHARDS:
        raise ValueError(
            "global p6/h14 must have exactly eight enriched field shards"
        )
    rows = [
        {
            "path": str(path.resolve()),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in paths
    ]
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "shard_count": len(rows),
        "shards": rows,
        "manifest_sha256": digest,
    }


def _resource_metrics(
    record: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    stage: str,
) -> dict[str, Any]:
    matrix = result.get("stage4_dtn_floquet_independent_matrix_stats")
    factor = result.get("stage4_dtn_factor_inventory")
    factor_matrix = (
        factor.get("matrix_stats")
        if isinstance(factor, Mapping)
        else None
    )
    authority = record.get("resource_authority")
    _require(
        isinstance(matrix, Mapping)
        and isinstance(factor, Mapping)
        and factor.get("available") is True
        and isinstance(factor_matrix, Mapping)
        and isinstance(authority, Mapping),
        "matrix/factor/resource authority is incomplete",
    )
    stage_rows = [
        row
        for row in authority.get("stage_peaks") or []
        if row.get("stage") == stage
    ]
    _require(len(stage_rows) == 1, f"resource stage {stage!r} is not unique")
    matrix_nnz = _positive(
        matrix.get("matrix_nnz_used"),
        label="matrix_nnz",
    )
    factor_nnz = _positive(
        factor_matrix.get("matrix_nnz_used"),
        label="factor_nnz",
    )
    return {
        "full3d_equivalent_dofs": int(
            _positive(result.get("num_nedelec_dofs"), label="dofs")
        ),
        "active_rows": int(
            _positive(matrix.get("matrix_rows"), label="active_rows")
        ),
        "matrix_nnz": int(matrix_nnz),
        "matrix_average_row_width": matrix_nnz
        / _positive(matrix.get("matrix_rows"), label="active_rows"),
        "factor_nnz": int(factor_nnz),
        "factor_fill_ratio": factor_nnz / matrix_nnz,
        "overall_process_tree_peak_gib": _positive(
            authority.get("memory_authority_gib"),
            label="overall_peak_gib",
        ),
        "solve_stage_process_tree_peak_gib": _positive(
            stage_rows[0].get("max_mpi_process_tree_rss_mb"),
            label="stage_peak_mb",
        )
        / 1024.0,
    }


def _relative_delta(
    baseline: float,
    candidate: float,
) -> dict[str, float]:
    baseline_value = _positive(baseline, label="marginal baseline")
    candidate_value = _positive(candidate, label="marginal candidate")
    return {
        "fixed_h14": baseline_value,
        "global_p6_h14": candidate_value,
        "absolute_delta": candidate_value - baseline_value,
        "relative_delta": candidate_value / baseline_value - 1.0,
    }


def _error_delta(
    baseline: Any,
    candidate: Any,
    *,
    label: str,
) -> dict[str, float | None]:
    baseline_value = _finite(baseline, label=f"{label}.baseline")
    candidate_value = _finite(candidate, label=f"{label}.candidate")
    _require(
        baseline_value >= 0.0 and candidate_value >= 0.0,
        f"{label} errors must be nonnegative",
    )
    return {
        "fixed_h14": baseline_value,
        "global_p6_h14": candidate_value,
        "absolute_delta": candidate_value - baseline_value,
        "relative_delta": (
            candidate_value / baseline_value - 1.0
            if baseline_value > 0.0
            else None
        ),
    }


def _trace_resource_marginal(
    *,
    global_record: Mapping[str, Any],
    global_summary: Mapping[str, Any],
    fixed_record: Mapping[str, Any],
) -> dict[str, Any]:
    global_metrics = _resource_metrics(
        global_record,
        global_summary,
        stage="actual_r5_enriched_solve",
    )
    fixed_metrics = _resource_metrics(
        fixed_record,
        fixed_record["candidate"],
        stage="fixed_trace_candidate_solve",
    )
    fields = (
        "full3d_equivalent_dofs",
        "active_rows",
        "matrix_nnz",
        "factor_nnz",
        "overall_process_tree_peak_gib",
        "solve_stage_process_tree_peak_gib",
    )
    marginal = {
        field: _relative_delta(
            float(fixed_metrics[field]),
            float(global_metrics[field]),
        )
        for field in fields
    }
    return {
        "same_h14_mesh": True,
        "same_p6_cell_interior": True,
        "changed_trace_degree": {"fixed": 5, "global": 6},
        "fixed_h14": fixed_metrics,
        "global_p6_h14": global_metrics,
        "marginal": marginal,
        "full3d_equivalent_dof_limit": FULL3D_EQUIVALENT_DOF_LIMIT,
        "global_p6_h14_over_limit_by": (
            global_metrics["full3d_equivalent_dofs"]
            - FULL3D_EQUIVALENT_DOF_LIMIT
        ),
        "global_p6_h14_within_limit": (
            global_metrics["full3d_equivalent_dofs"]
            <= FULL3D_EQUIVALENT_DOF_LIMIT
        ),
        "peak_scope_note": (
            "overall global peak contains the p5/p6 pair; solve-stage peaks "
            "isolate enriched global-p6 versus fixed candidate solve"
        ),
    }


def _channel_trace_marginal(
    *,
    fixed_comparison: Mapping[str, Any],
    global_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    def key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
        return (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        )

    fixed_rows = {key(row): row for row in fixed_comparison["channels"]}
    global_rows = {key(row): row for row in global_comparison["channels"]}
    _require(
        len(fixed_rows) == len(global_rows) == 12
        and set(fixed_rows) == set(global_rows),
        "fixed/global h14 frozen channel identities differ",
    )
    rows: list[dict[str, Any]] = []
    for identity in sorted(fixed_rows):
        fixed = fixed_rows[identity]
        global_row = global_rows[identity]
        fixed_power = _finite(
            fixed["candidate_vs_reference_power_absolute_error"],
            label="fixed channel power error",
        ) / _positive(
            fixed["unchanged_v0_power_tolerance"],
            label="fixed power tolerance",
        )
        global_power = _finite(
            global_row["candidate_vs_reference_power_absolute_error"],
            label="global channel power error",
        ) / _positive(
            global_row["unchanged_v0_power_tolerance"],
            label="global power tolerance",
        )
        fixed_amplitude = _finite(
            fixed["candidate_vs_reference_amplitude_absolute_error"],
            label="fixed channel amplitude error",
        ) / _positive(
            fixed["unchanged_v0_complex_amplitude_tolerance"],
            label="fixed amplitude tolerance",
        )
        global_amplitude = _finite(
            global_row["candidate_vs_reference_amplitude_absolute_error"],
            label="global channel amplitude error",
        ) / _positive(
            global_row["unchanged_v0_complex_amplitude_tolerance"],
            label="global amplitude tolerance",
        )
        rows.append(
            {
                "side": identity[0],
                "m": identity[1],
                "n": identity[2],
                "polarization": identity[3],
                "fixed_power_error_normalized": fixed_power,
                "global_p6_power_error_normalized": global_power,
                "power_relative_reduction": (
                    1.0 - global_power / fixed_power
                    if fixed_power > 0.0
                    else None
                ),
                "fixed_amplitude_error_normalized": fixed_amplitude,
                "global_p6_amplitude_error_normalized": global_amplitude,
                "amplitude_relative_reduction": (
                    1.0 - global_amplitude / fixed_amplitude
                    if fixed_amplitude > 0.0
                    else None
                ),
                "fixed_power_pass": fixed.get("power_pass") is True,
                "global_p6_power_pass": global_row.get("power_pass") is True,
                "fixed_amplitude_pass": (
                    fixed.get("complex_amplitude_pass") is True
                ),
                "global_p6_amplitude_pass": (
                    global_row.get("complex_amplitude_pass") is True
                ),
            }
        )
    return {
        "fixed_power_pass_count": sum(
            row["fixed_power_pass"] for row in rows
        ),
        "global_p6_power_pass_count": sum(
            row["global_p6_power_pass"] for row in rows
        ),
        "fixed_complex_amplitude_pass_count": sum(
            row["fixed_amplitude_pass"] for row in rows
        ),
        "global_p6_complex_amplitude_pass_count": sum(
            row["global_p6_amplitude_pass"] for row in rows
        ),
        "channels": rows,
    }


def _scalar_trace_marginal(
    fixed: Mapping[str, Any],
    global_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    fixed_rows = fixed.get("observables")
    global_rows = global_comparison.get("observables")
    _require(
        isinstance(fixed_rows, Mapping)
        and isinstance(global_rows, Mapping)
        and set(fixed_rows) == set(global_rows),
        "fixed/global scalar observable identities differ",
    )
    rows: dict[str, Any] = {}
    for name in fixed_rows:
        fixed_error = _finite(
            fixed_rows[name]["normalized_error"],
            label=f"fixed scalar {name}",
        )
        global_error = _finite(
            global_rows[name]["normalized_error"],
            label=f"global scalar {name}",
        )
        rows[name] = {
            "fixed_normalized_error": fixed_error,
            "global_p6_normalized_error": global_error,
            "relative_reduction": (
                1.0 - global_error / fixed_error
                if fixed_error > 0.0
                else None
            ),
            "fixed_pass": fixed_rows[name].get("pass") is True,
            "global_p6_pass": global_rows[name].get("pass") is True,
        }
    return {
        "observables": rows,
        "fixed_R_T_Aclosure_l2": _finite(
            fixed.get("normalized_R_T_Aclosure_l2"),
            label="fixed RTA l2",
        ),
        "global_p6_R_T_Aclosure_l2": _finite(
            global_comparison.get("normalized_R_T_Aclosure_l2"),
            label="global RTA l2",
        ),
    }


def _field_trace_marginal(
    fixed: Mapping[str, Any],
    global_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    fixed_selections = fixed.get("selections")
    global_selections = global_comparison.get("selections")
    _require(
        isinstance(fixed_selections, Mapping)
        and isinstance(global_selections, Mapping)
        and set(fixed_selections) == set(global_selections),
        "fixed/global selected-field identities differ",
    )
    rows: dict[str, Any] = {}
    for name in fixed_selections:
        fixed_row = fixed_selections[name]
        global_row = global_selections[name]
        rows[name] = {
            "weighted_relative_l2": _error_delta(
                fixed_row["candidate_vs_p6_weighted_relative_l2"],
                global_row["candidate_vs_p6_weighted_relative_l2"],
                label=f"{name} weighted relative l2",
            ),
            "maximum_pointwise_absolute_error": _error_delta(
                fixed_row[
                    "candidate_vs_p6_max_pointwise_absolute_error"
                ],
                global_row[
                    "candidate_vs_p6_max_pointwise_absolute_error"
                ],
                label=f"{name} maximum pointwise error",
            ),
            "fixed_pass": fixed_row.get("pass") is True,
            "global_p6_pass": global_row.get("pass") is True,
        }
    return {"selections": rows}


def build_global_p6_h14_trace_discriminator(
    *,
    global_record: Mapping[str, Any],
    global_authority: Mapping[str, Any],
    reference_record: Mapping[str, Any],
    reference_authority: Mapping[str, Any],
    fixed_record: Mapping[str, Any],
    fixed_authority: Mapping[str, Any],
    control_record: Mapping[str, Any],
    control_authority: Mapping[str, Any],
    candidate_summary: Mapping[str, Any],
    raw_authorities: Mapping[str, Any],
    scalar_comparison: Mapping[str, Any],
    channel_comparison: Mapping[str, Any],
    field_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate formal authorities and classify the trace-only discriminator."""

    global_mesh = _validate_global_h14_record(global_record)
    fixed_mesh = _validate_fixed_h14_record(fixed_record)
    _validate_h10_control(control_record)
    _require(
        reference_record.get("schema_version")
        == "task035b.significant-channel-reference.v1"
        and reference_record.get("status")
        == "significant_channel_reference_v1_frozen"
        and reference_record.get("pass") is True
        and reference_record.get("mechanical_validation_pass") is True,
        "significant-channel reference v1 is invalid",
    )
    for key in (
        "partition_independent_mesh_sha256",
        "cell_tag_sha256",
        "facet_tag_sha256",
        "global_cell_count",
        "mesh_cells_resolved",
    ):
        _require(
            global_mesh.get(key) == fixed_mesh.get(key),
            f"global/fixed h14 mesh mismatch for {key}",
        )
    _validate_raw_candidate_summary(
        summary=candidate_summary,
        watchdog=global_record,
        fixed_mesh=fixed_mesh,
    )
    _require(
        scalar_comparison.get("schema_version")
        == "task035b.cross-mesh-observable-comparison.v1"
        and isinstance(scalar_comparison.get("pass"), bool),
        "global-p6/h14 scalar comparison is incomplete",
    )
    _require(
        channel_comparison.get("schema_version")
        == "task035b.significant-channel-reference-v1-comparison.v1"
        and channel_comparison.get("frozen_significant_channel_count") == 12
        and channel_comparison.get("analytic_channel_identity_pass") is True
        and channel_comparison.get("thresholds_relaxed") is False,
        "global-p6/h14 12-channel comparison is incomplete",
    )
    _require(
        field_comparison.get("schema_version")
        == "task035b.cross-mesh-field-comparison.v1"
        and field_comparison.get("no_threshold_relaxation") is True
        and isinstance(field_comparison.get("pass"), bool),
        "global-p6/h14 selected-field comparison is incomplete",
    )
    _require(
        isinstance(raw_authorities.get("enriched_p6_fields"), Mapping)
        and raw_authorities["enriched_p6_fields"].get("shard_count")
        == EXPECTED_FIELD_SHARDS
        and _full_sha256(
            raw_authorities["enriched_p6_fields"].get("manifest_sha256")
        )
        and _full_sha256(
            (raw_authorities.get("enriched_p6_orders") or {}).get("sha256")
        )
        and _full_sha256(
            (raw_authorities.get("enriched_p6_summary") or {}).get("sha256")
        ),
        "global-p6/h14 raw order/field/summary authorities are not hash-bound",
    )
    _require(
        (channel_comparison.get("candidate_authority") or {}).get("sha256")
        == raw_authorities["enriched_p6_orders"]["sha256"],
        "12-channel comparison does not bind enriched-p6 raw orders",
    )
    manifest_alignment = raw_authorities.get(
        "watchdog_manifest_alignment"
    )
    _require(
        isinstance(manifest_alignment, Mapping)
        and manifest_alignment.get("pass") is True
        and manifest_alignment.get(
            "reverified_after_all_postprocess_reads"
        )
        is True
        and isinstance(manifest_alignment.get("checks"), Mapping)
        and bool(manifest_alignment["checks"])
        and all(
            value is True
            for value in manifest_alignment["checks"].values()
        ),
        "postprocess inputs are not closed against the watchdog manifest",
    )

    all_12 = bool(
        channel_comparison.get("all_12_significant_powers_pass") is True
        and channel_comparison.get(
            "all_12_significant_complex_amplitudes_pass"
        )
        is True
        and channel_comparison.get("pass") is True
        and scalar_comparison.get("pass") is True
        and field_comparison.get("pass") is True
    )
    resource_marginal = _trace_resource_marginal(
        global_record=global_record,
        global_summary=candidate_summary,
        fixed_record=fixed_record,
    )
    _require(
        resource_marginal["global_p6_h14_over_limit_by"] == 2850
        and resource_marginal["global_p6_h14_within_limit"] is False,
        "global p6/h14 must remain an explicit 92850-DoF over-limit control",
    )
    evidence = {
        "schema_version": "task035b.global-p6-h14-trace-discriminator.v1",
        "status": (
            "positive_global_p6_h14_trace_physics_signal"
            if all_12
            else "controlled_negative_global_p6_h14_trace_discriminator"
        ),
        "pass": True,
        "diagnostic_only": True,
        "formal_candidate_eligible": False,
        "selective_trace_lane_physically_supported": all_12,
        "selection_rule": (
            "true only when global p6/h14 passes scalar and selected-field "
            "Gates plus all 12 frozen significant powers and all 12 frozen "
            "complex amplitudes"
        ),
        "authorities": {
            "global_p5_p6_h14_watchdog": dict(global_authority),
            "significant_channel_reference_v1": dict(reference_authority),
            "fixed_p5trace_p6interior_h14": dict(fixed_authority),
            "h10_p5_p6_control": dict(control_authority),
            "raw": dict(raw_authorities),
        },
        "global_p6_h14_gates": {
            "scalar": dict(scalar_comparison),
            "significant_12_power_and_complex_amplitude": dict(
                channel_comparison
            ),
            "selected_field_interface": dict(field_comparison),
        },
        "trace_only_marginal_on_identical_h14_mesh": {
            "resources": resource_marginal,
            "scalar": _scalar_trace_marginal(
                fixed_record["observable_comparison"],
                scalar_comparison,
            ),
            "significant_channels": _channel_trace_marginal(
                fixed_comparison=fixed_record[
                    "diffraction_channel_comparison"
                ],
                global_comparison=channel_comparison,
            ),
            "selected_fields": _field_trace_marginal(
                fixed_record["selected_field_interface_error_gate"],
                field_comparison,
            ),
        },
        "decision": {
            "global_p6_h14_full3d_equivalent_dofs": (
                EXPECTED_GLOBAL_P6_DOFS
            ),
            "full3d_equivalent_dof_limit": FULL3D_EQUIVALENT_DOF_LIMIT,
            "over_limit_by": 2850,
            "global_p6_h14_is_candidate": False,
            "only_possible_use": (
                "physics discriminator for a later physically reduced "
                "selective-p6-trace implementation"
            ),
            "ordinary_default_changed": False,
            "thresholds_relaxed": False,
        },
        "execution_contract": {
            "pure_postprocess": True,
            "pde_solve_count": 0,
            "mesh_build_count": 0,
            "matrix_assembly_count": 0,
            "factorization_count": 0,
            "mpi_launch_count": 0,
            "irregular_geometry_run": False,
        },
    }
    json.dumps(evidence, allow_nan=False)
    return evidence


def _formal_analysis(
    *,
    repo_root: Path,
    global_record_path: Path,
    global_record_sha256: str,
    reference_path: Path,
    reference_sha256: str,
    fixed_path: Path,
    fixed_sha256: str,
    control_path: Path,
    control_sha256: str,
) -> dict[str, Any]:
    global_record, global_authority = _load_sha_bound_json(
        repo_root,
        global_record_path,
        global_record_sha256,
        label="global p5/p6 h14 watchdog",
    )
    reference, reference_authority = _load_sha_bound_json(
        repo_root,
        reference_path,
        reference_sha256,
        label="significant-channel reference v1",
    )
    fixed, fixed_authority = _load_sha_bound_json(
        repo_root,
        fixed_path,
        fixed_sha256,
        label="fixed p5trace/p6interior h14",
    )
    control, control_authority = _load_sha_bound_json(
        repo_root,
        control_path,
        control_sha256,
        label="h10 p5/p6 control",
    )
    _validate_global_h14_record(global_record)
    fixed_mesh = _validate_fixed_h14_record(fixed)
    _validate_h10_control(control)

    global_dir, global_actual = _raw_run_directory(
        repo_root,
        global_record,
        label="global p5/p6 h14",
    )
    solve_artifact_manifest = _validate_solve_artifact_manifest(
        repo_root,
        global_record,
        global_dir,
    )
    control_dir, control_actual = _raw_run_directory(
        repo_root,
        control,
        label="h10 p5/p6 control",
    )
    control_p5, control_p5_authority = _load_summary(
        control_dir,
        "coarse_p5",
    )
    control_p6, control_p6_authority = _load_summary(
        control_dir,
        "enriched_p6",
    )
    candidate_p6, candidate_summary_authority = _load_summary(
        global_dir,
        "enriched_p6",
    )
    _require(
        control_p5 == ((control_actual.get("coarse") or {}).get("summary")),
        "h10 raw p5 summary differs from SHA-bound actual result",
    )
    _require(
        control_p6 == ((control_actual.get("enriched") or {}).get("summary")),
        "h10 raw p6 summary differs from SHA-bound actual result",
    )
    _require(
        candidate_p6
        == ((global_actual.get("enriched") or {}).get("summary")),
        "global h14 raw p6 summary differs from SHA-bound actual result",
    )
    _validate_raw_candidate_summary(
        summary=candidate_p6,
        watchdog=global_record,
        fixed_mesh=fixed_mesh,
    )
    orders = global_dir / "enriched_p6" / "dtn_port_diffraction_orders_3d.json"
    if not orders.is_file():
        raise ValueError("global p6/h14 enriched raw orders are absent")
    orders_authority = {
        "path": str(orders.resolve()),
        "sha256": _sha256(orders),
        "size_bytes": orders.stat().st_size,
    }
    fields_authority = _field_manifest(global_dir / "enriched_p6")

    scalar = compare_observables(candidate_p6, control_p5, control_p6)
    channels = compare_significant_channels_to_reference_v1(
        candidate_path=orders,
        reference_record_path=_resolve(repo_root, reference_path),
        reference_record_sha256=reference_sha256,
    )
    fields = compare_cross_mesh_fields(
        global_p5_dir=control_dir / "coarse_p5",
        global_p6_dir=control_dir / "enriched_p6",
        candidate_p6_dir=global_dir / "enriched_p6",
    )
    raw_authorities = {
        "h10_control_p5_summary": control_p5_authority,
        "h10_control_p6_summary": control_p6_authority,
        "enriched_p6_summary": candidate_summary_authority,
        "enriched_p6_orders": orders_authority,
        "enriched_p6_fields": fields_authority,
    }
    alignment = _validate_postprocess_authorities_against_manifest(
        repo_root,
        solve_artifact_manifest,
        raw_authorities,
    )
    manifest_after_postprocess = _validate_solve_artifact_manifest(
        repo_root,
        global_record,
        global_dir,
    )
    _require(
        manifest_after_postprocess.get("files_manifest_sha256")
        == solve_artifact_manifest.get("files_manifest_sha256"),
        "watchdog artifact manifest changed during postprocessing",
    )
    raw_authorities["watchdog_manifest_alignment"] = {
        **alignment,
        "reverified_after_all_postprocess_reads": True,
    }
    return build_global_p6_h14_trace_discriminator(
        global_record=global_record,
        global_authority=global_authority,
        reference_record=reference,
        reference_authority=reference_authority,
        fixed_record=fixed,
        fixed_authority=fixed_authority,
        control_record=control,
        control_authority=control_authority,
        candidate_summary=candidate_p6,
        raw_authorities=raw_authorities,
        scalar_comparison=scalar,
        channel_comparison=channels,
        field_comparison=fields,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--global-h14-record", type=Path, required=True)
    parser.add_argument("--global-h14-record-sha256", required=True)
    parser.add_argument(
        "--reference-record",
        type=Path,
        default=REFERENCE_PATH,
    )
    parser.add_argument(
        "--reference-record-sha256",
        default=REFERENCE_SHA256,
    )
    parser.add_argument(
        "--fixed-h14-record",
        type=Path,
        default=FIXED_H14_PATH,
    )
    parser.add_argument(
        "--fixed-h14-record-sha256",
        default=FIXED_H14_SHA256,
    )
    parser.add_argument(
        "--h10-control-record",
        type=Path,
        default=H10_CONTROL_PATH,
    )
    parser.add_argument(
        "--h10-control-record-sha256",
        default=H10_CONTROL_SHA256,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source_before = _verified_source_identity(
        ROOT,
        args.verified_clean_sha,
    )
    environment = _environment_identity(ROOT)
    hashes_before = _source_file_sha256(ROOT)
    evidence = _formal_analysis(
        repo_root=ROOT,
        global_record_path=args.global_h14_record,
        global_record_sha256=args.global_h14_record_sha256,
        reference_path=args.reference_record,
        reference_sha256=args.reference_record_sha256,
        fixed_path=args.fixed_h14_record,
        fixed_sha256=args.fixed_h14_record_sha256,
        control_path=args.h10_control_record,
        control_sha256=args.h10_control_record_sha256,
    )
    source_after, hashes_after = _reverify_after_build(
        ROOT,
        source_before,
        hashes_before,
    )
    source = dict(source_before)
    source.update(source_after)
    checks = dict(source_before["checks"])
    checks.update(source_after["checks"])
    source["checks"] = checks
    evidence["source"] = _qualified_output_source(source)
    evidence["environment"] = environment
    evidence["source_file_sha256"] = hashes_after
    json.dumps(evidence, allow_nan=False)

    output = _resolve(ROOT, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            evidence,
            stream,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
