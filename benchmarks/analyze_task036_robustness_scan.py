"""Fail-closed Task036 Review V2 robustness-scan analyzer.

The analyzer consumes existing Full3D watchdog and Hybrid memory-watchdog
artifacts.  It never imports or calls a solver.  Numerical negatives are valid
map entries; malformed provenance, hashes, or physical identities are analysis
errors.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POINTS = ROOT / "benchmarks" / "task036_robustness_scan_points.csv"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HYBRID_DIR_RE = re.compile(r"^hybrid_m([1-9][0-9]*)$")

TRUE_RESIDUAL_MAX = 1.0e-9
INTERFACE_E_MAX = 1.0e-8
EXACT_TRACTION_MAX = 1.0e-8
BIORTHOGONALITY_ROW_MAX = 1.0e-6
DIRECT_PROJECTION_MAX = 1.0e-10
ENERGY_CLOSURE_MAX = 1.0e-5
TOTAL_DELTA_MAX = 1.0e-4
SIGNIFICANT_POWER_FLOOR = 1.0e-8
SIGNIFICANT_RELATIVE_MAX = 1.0e-3
WEAK_ABSOLUTE_MAX = 1.0e-8


class AnalysisError(ValueError):
    """Raised when an artifact cannot be used as authoritative evidence."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise AnalysisError(f"{label}: missing JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"{label}: unreadable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnalysisError(f"{label}: top-level JSON value must be an object")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _dig(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _finite(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise AnalysisError(f"{label}: finite number required")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisError(f"{label}: finite number required") from exc
    if not math.isfinite(number):
        raise AnalysisError(f"{label}: finite number required")
    return number


def _optional_finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise AnalysisError(f"{label}: positive integer required")
    return value


def _complex_pair(value: Any, label: str) -> complex:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise AnalysisError(f"{label}: [real, imag] pair required")
    return complex(
        _finite(value[0], f"{label}.real"),
        _finite(value[1], f"{label}.imag"),
    )


def _complex_json(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _same_float(actual: Any, expected: float, label: str) -> None:
    number = _finite(actual, label)
    tolerance = max(1.0e-12, 1.0e-11 * max(1.0, abs(expected)))
    if abs(number - expected) > tolerance:
        raise AnalysisError(f"{label}: expected {expected}, observed {number}")


def _require_sha(value: Any, expected: str, label: str) -> None:
    if not isinstance(value, str) or value.lower() != expected:
        raise AnalysisError(f"{label}: expected source SHA {expected}, observed {value!r}")


def _require_hash(value: Any, expected: str, label: str) -> None:
    if not isinstance(value, str) or value.lower() != expected:
        raise AnalysisError(f"{label}: expected SHA-256 {expected}, observed {value!r}")


def _resolve_evidence_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AnalysisError(f"{label}: evidence path is missing")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _normalize_point(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        axis_counts_value = row.get("axis_counts")
        if axis_counts_value is None:
            axis_counts_value = (row["nx"], row["ny"], row["nz"])
        if (
            not isinstance(axis_counts_value, Sequence)
            or isinstance(axis_counts_value, (str, bytes))
            or len(axis_counts_value) != 3
        ):
            raise ValueError("axis counts")
        return {
            "point_id": str(row["point_id"]),
            "round": str(row.get("round", "")),
            "degree": int(row.get("degree", row.get("nedelec_degree"))),
            "h_nm": float(row["h_nm"]),
            "height_nm": float(row["height_nm"]),
            "width_x_nm": float(row["width_x_nm"]),
            "grazing_deg": float(row["grazing_deg"]),
            "azimuth_deg": float(row["azimuth_deg"]),
            "polarization": str(
                row.get("polarization", row.get("incident_polarization"))
            ).lower(),
            "axis_counts": [int(value) for value in axis_counts_value],
            "initial_m": int(
                row.get("initial_m", row.get("initial_m_per_direction", 120))
            ),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisError(f"invalid frozen point row: {row!r}") from exc


def _validate_point(point: Mapping[str, Any]) -> None:
    if not point["point_id"]:
        raise AnalysisError("point_id must be nonempty")
    if point["polarization"] not in {"s", "p"}:
        raise AnalysisError(f"{point['point_id']}: polarization must be S or P")
    if point["degree"] <= 0 or point["h_nm"] <= 0.0:
        raise AnalysisError(f"{point['point_id']}: degree and h must be positive")
    if len(point["axis_counts"]) != 3 or any(
        value <= 0 for value in point["axis_counts"]
    ):
        raise AnalysisError(f"{point['point_id']}: invalid axis counts")


def _order_key(
    row: Mapping[str, Any],
    label: str,
) -> tuple[str, int, int, str]:
    side = row.get("side")
    polarization = row.get("polarization")
    if side not in {"top", "bottom"}:
        raise AnalysisError(f"{label}: order side must be top or bottom")
    if polarization not in {"s", "p"}:
        raise AnalysisError(f"{label}: order polarization must be s or p")
    m_value = row.get("order_m", row.get("m"))
    n_value = row.get("order_n", row.get("n"))
    if type(m_value) is not int or type(n_value) is not int:
        raise AnalysisError(f"{label}: integer order identity is required")
    return side, m_value, n_value, polarization


def _order_map(
    rows: Any,
    label: str,
) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise AnalysisError(f"{label}: nonempty diffraction-order list required")
    result: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            raise AnalysisError(f"{label}[{index}]: order row must be an object")
        key = _order_key(item, f"{label}[{index}]")
        if key in result:
            raise AnalysisError(f"{label}: duplicate fixed order identity {key}")
        amplitude = _complex_pair(
            item.get("outgoing_amplitude_at_boundary"),
            f"{label}[{index}].outgoing_amplitude_at_boundary",
        )
        power = _finite(item.get("power_ratio"), f"{label}[{index}].power_ratio")
        result[key] = {
            "amplitude": amplitude,
            "power": power,
            "propagating": item.get("propagating"),
            "power_carrying": item.get("power_carrying"),
        }
    return result


def _factor_nnz(inventory: Any, label: str) -> float | None:
    value = _mapping(inventory)
    corrected = _optional_finite(value.get("factor_nnz_corrected"))
    if corrected is not None:
        return corrected
    raw = _optional_finite(_dig(value, "matrix_stats", "matrix_nnz_used"))
    if raw is not None:
        return raw
    if value.get("available") is True:
        raise AnalysisError(f"{label}: available factor inventory lacks finite NNZ")
    return None


def _verify_full3d(
    point: Mapping[str, Any],
    point_dir: Path,
    expected_sha: str,
) -> tuple[dict[str, Any], dict[tuple[str, int, int, str], dict[str, Any]]]:
    watchdog_path = point_dir / "full3d" / "watchdog_summary.json"
    watchdog = _load_json_object(watchdog_path, f"{point['point_id']}.full3d")
    source = _mapping(watchdog.get("source"))
    for key in ("commit_sha", "verified_clean_sha", "head_after_sha"):
        _require_sha(source.get(key), expected_sha, f"full3d.source.{key}")
    if (
        source.get("stable_and_clean_after") is not True
        or source.get("tracked_source_dirty") is not False
        or source.get("status_after") != ""
    ):
        raise AnalysisError(f"{point['point_id']}: Full3D source is not clean and stable")

    watchdog_sha = _sha256(watchdog_path)
    process_complete = watchdog.get("return_code") == 0
    if not process_complete:
        return (
            {
                "status": "failed",
                "watchdog_path": str(watchdog_path),
                "watchdog_sha256": watchdog_sha,
                "return_code": watchdog.get("return_code"),
                "gates": {"process_completed": False, "pass": False},
            },
            {},
        )

    raw_evidence = _mapping(watchdog.get("raw_evidence"))
    summary_path = _resolve_evidence_path(
        raw_evidence.get("solver_summary"),
        f"{point['point_id']}.full3d.raw_evidence.solver_summary",
    )
    orders_path = _resolve_evidence_path(
        raw_evidence.get("dtn_orders"),
        f"{point['point_id']}.full3d.raw_evidence.dtn_orders",
    )
    summary_sha = _sha256(summary_path)
    orders_sha = _sha256(orders_path)
    _require_hash(
        watchdog.get("solver_summary_sha256"),
        summary_sha,
        "full3d.solver_summary_sha256",
    )
    _require_hash(
        watchdog.get("dtn_orders_sha256"),
        orders_sha,
        "full3d.dtn_orders_sha256",
    )
    summary = _load_json_object(summary_path, f"{point['point_id']}.full3d.summary")
    orders = _load_json_object(orders_path, f"{point['point_id']}.full3d.orders")
    config = _mapping(summary.get("config"))

    if watchdog.get("degree") != point["degree"]:
        raise AnalysisError(f"{point['point_id']}: Full3D degree identity mismatch")
    _same_float(watchdog.get("h_nm"), point["h_nm"], "full3d.h_nm")
    if watchdog.get("mpi_size") != 8 or summary.get("mpi_size") != 8:
        raise AnalysisError(f"{point['point_id']}: Full3D must be MPI8")
    if summary.get("polarization_kind") != point["polarization"]:
        raise AnalysisError(f"{point['point_id']}: Full3D polarization mismatch")
    if summary.get("nedelec_degree") != point["degree"]:
        raise AnalysisError(f"{point['point_id']}: Full3D summary degree mismatch")
    if summary.get("mesh_cells_resolved") != point["axis_counts"]:
        raise AnalysisError(f"{point['point_id']}: Full3D mesh identity mismatch")
    if config.get("mesh_axis_cell_counts") != point["axis_counts"]:
        raise AnalysisError(f"{point['point_id']}: Full3D requested mesh mismatch")
    _same_float(
        config.get("grating_height"),
        point["height_nm"],
        "full3d.grating_height",
    )
    _same_float(
        config.get("grating_width_x"),
        point["width_x_nm"],
        "full3d.grating_width_x",
    )
    _same_float(
        summary.get("incident_theta_deg"),
        90.0 - point["grazing_deg"],
        "full3d.incident_theta_deg",
    )
    _same_float(
        summary.get("incident_phi_deg"),
        point["azimuth_deg"],
        "full3d.incident_phi_deg",
    )
    if summary.get("geometry_kind") != "rectangular_block_grating":
        raise AnalysisError(f"{point['point_id']}: Full3D geometry mismatch")
    if (
        summary.get("stage4_full3d_assembly_backend_actual")
        != "assembly_time_static_condensed"
    ):
        raise AnalysisError(f"{point['point_id']}: Full3D backend mismatch")

    order_rows = orders.get("orders")
    order_values = _order_map(order_rows, f"{point['point_id']}.full3d.orders")
    residual = _finite(
        summary.get("linear_system_relative_residual"),
        "full3d.linear_system_relative_residual",
    )
    r_total = _finite(summary.get("R_total"), "full3d.R_total")
    t_total = _finite(summary.get("T_total"), "full3d.T_total")
    a_volume = _finite(summary.get("A_volume_total"), "full3d.A_volume_total")
    energy_closure = abs(r_total + t_total + a_volume - 1.0)
    projection = _mapping(summary.get("auxiliary_direct_tangential_projection_audit"))
    projection_difference = _optional_finite(
        projection.get("max_absolute_outgoing_projection_difference")
    )
    projection_pass = bool(
        projection.get("requested") is True
        and projection.get("pass") is True
        and projection_difference is not None
        and projection_difference <= DIRECT_PROJECTION_MAX
    )
    factor_nnz = _factor_nnz(
        summary.get("stage4_dtn_factor_inventory"),
        "full3d.stage4_dtn_factor_inventory",
    )
    peak_gib = _finite(
        _dig(watchdog, "resource_authority", "memory_authority_gib"),
        "full3d.resource_authority.memory_authority_gib",
    )
    wall_seconds = _finite(summary.get("elapsed_seconds"), "full3d.elapsed_seconds")
    gates = {
        "process_completed": True,
        "qualification_pass": _dig(watchdog, "qualification", "pass") is True,
        "true_residual_le_1e-9": residual <= TRUE_RESIDUAL_MAX,
        "direct_projection_le_1e-10": projection_pass,
        "energy_closure_le_1e-5": energy_closure <= ENERGY_CLOSURE_MAX,
        "zero_swap": watchdog.get("no_swap") is True,
    }
    gates["pass"] = all(gates.values())
    return (
        {
            "status": "pass" if gates["pass"] else "failed",
            "watchdog_path": str(watchdog_path),
            "watchdog_sha256": watchdog_sha,
            "solver_summary_path": str(summary_path),
            "solver_summary_sha256": summary_sha,
            "dtn_orders_path": str(orders_path),
            "dtn_orders_sha256": orders_sha,
            "source_sha": expected_sha,
            "command": watchdog.get("command"),
            "metrics": {
                "true_relative_residual": residual,
                "direct_projection_difference": projection_difference,
                "R_total": r_total,
                "T_total": t_total,
                "A_volume_total": a_volume,
                "energy_closure_error": energy_closure,
                "condensed_rows": summary.get("num_active_condensed_dofs"),
                "independent_trace_rows": summary.get("num_independent_trace_rows"),
                "matrix_nnz": _optional_finite(
                    _dig(summary, "matrix_stats", "matrix_nnz_used")
                ),
                "factor_nnz": factor_nnz,
                "peak_memory_gib": peak_gib,
                "wall_seconds": wall_seconds,
            },
            "gates": gates,
        },
        order_values,
    )


def _hybrid_direct_projection(
    solver: Mapping[str, Any],
) -> dict[str, Any]:
    audit = _dig(
        solver,
        "validation",
        "auxiliary_direct_tangential_projection_audit",
    )
    if not isinstance(audit, Mapping):
        return {
            "present": False,
            "available": False,
            "difference": None,
            "pass": False,
            "reason": "hybrid_candidate_direct_projection_missing",
        }
    reported_difference = _optional_finite(
        audit.get("max_absolute_outgoing_projection_difference")
    )
    tolerance = _optional_finite(audit.get("tolerance"))
    orders = audit.get("orders")
    rows = orders if isinstance(orders, list) else []
    identities: list[tuple[str, int, int, str]] = []
    row_differences: list[float] = []
    rows_valid = bool(rows)
    for row in rows:
        if not isinstance(row, Mapping):
            rows_valid = False
            continue
        try:
            identities.append(
                _order_key(
                    row,
                    "hybrid_candidate_direct_projection.orders",
                )
            )
            row_differences.append(
                _finite(
                    row.get("absolute_outgoing_projection_difference"),
                    (
                        "hybrid_candidate_direct_projection.orders."
                        "absolute_outgoing_projection_difference"
                    ),
                )
            )
            _finite(
                row.get("absolute_total_projection_difference"),
                (
                    "hybrid_candidate_direct_projection.orders."
                    "absolute_total_projection_difference"
                ),
            )
        except AnalysisError:
            rows_valid = False
    expected = audit.get("expected_mode_count")
    audited = audit.get("audited_mode_count")
    counts_valid = bool(
        type(expected) is int
        and expected > 0
        and type(audited) is int
        and audited == expected
        and len(rows) == expected
    )
    identities_valid = bool(
        rows_valid
        and len(identities) == len(rows)
        and len(set(identities)) == len(identities)
        and {key[0] for key in identities} == {"bottom", "top"}
        and {key[3] for key in identities} == {"s", "p"}
    )
    recomputed_difference = max(row_differences, default=None)
    difference_matches = bool(
        reported_difference is not None
        and recomputed_difference is not None
        and math.isclose(
            reported_difference,
            recomputed_difference,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
    )
    evidence_complete = bool(
        audit.get("requested") is True
        and audit.get("scope") == "hybrid_candidate"
        and tolerance == DIRECT_PROJECTION_MAX
        and counts_valid
        and identities_valid
        and difference_matches
    )
    passed = bool(
        evidence_complete
        and audit.get("pass") is True
        and recomputed_difference is not None
        and recomputed_difference <= DIRECT_PROJECTION_MAX
    )
    return {
        "present": True,
        "available": evidence_complete,
        "difference": recomputed_difference,
        "reported_difference": reported_difference,
        "expected_mode_count": expected,
        "audited_mode_count": audited,
        "unique_top_bottom_s_p_coverage": identities_valid,
        "pass": passed,
        "reason": (
            None
            if passed
            else (
                "hybrid_candidate_direct_projection_failed"
                if evidence_complete
                else "hybrid_candidate_direct_projection_incomplete"
            )
        ),
    }


def _biorthogonality_row_norm(solver: Mapping[str, Any]) -> float | None:
    values = [
        _optional_finite(_dig(solver, "qep", "positive", "max_biorthogonality_identity_error")),
        _optional_finite(_dig(solver, "qep", "negative", "max_biorthogonality_identity_error")),
        _optional_finite(
            _dig(
                solver,
                "qep",
                "task036_scalar_stage4_reciprocal_basis",
                "independent_negative",
                "max_biorthogonality_identity_error",
            )
        ),
    ]
    finite_values = [value for value in values if value is not None]
    return max(finite_values) if finite_values else None


def _capacity_evidence(
    solver: Mapping[str, Any],
    mode_count: int,
) -> dict[str, Any]:
    value = solver.get("modal_basis_capacity")
    if not isinstance(value, Mapping):
        value = _dig(solver, "qualification", "modal_basis_capacity")
    capacity = _mapping(value)
    available = capacity.get("available_finite_trace_rank")
    reached = bool(
        capacity.get("maximum_finite_full_trace_rank_reached") is True
        or capacity.get("full_trace_rank_reached") is True
    )
    valid = bool(type(available) is int and available == mode_count and reached)
    return {
        "available_finite_trace_rank": available if type(available) is int else None,
        "maximum_finite_full_trace_rank_reached": reached,
        "explicit_last_m_capacity_pass": valid,
        "finite_candidate_count_not_used_as_capacity": True,
    }


def _verify_hybrid(
    point: Mapping[str, Any],
    run_dir: Path,
    mode_count: int,
    expected_sha: str,
    full3d_sha: str,
) -> tuple[dict[str, Any], dict[tuple[str, int, int, str], dict[str, Any]]]:
    solver_path = run_dir / "solver_record.json"
    memory_path = run_dir / "memory_sampler_summary.json"
    if not solver_path.is_file() or not memory_path.is_file():
        return (
            {
                "status": "evidence_incomplete",
                "solver_record_present": solver_path.is_file(),
                "memory_sampler_present": memory_path.is_file(),
                "formal_evidence_complete": False,
            },
            {},
        )
    solver = _load_json_object(solver_path, f"{point['point_id']}.hybrid_m{mode_count}")
    memory = _load_json_object(
        memory_path,
        f"{point['point_id']}.hybrid_m{mode_count}.memory",
    )
    solver_sha = _sha256(solver_path)
    _require_hash(
        memory.get("solver_record_sha256"),
        solver_sha,
        f"{point['point_id']}.hybrid_m{mode_count}.solver_record_sha256",
    )

    memory_source = _mapping(memory.get("source"))
    for key in (
        "commit_sha",
        "verified_clean_sha",
        "head_before_sha",
        "head_after_sha",
    ):
        _require_sha(
            memory_source.get(key),
            expected_sha,
            f"hybrid_m{mode_count}.source.{key}",
        )
    if (
        memory_source.get("source_clean_verified") is not True
        or memory_source.get("source_stable_during_run") is not True
        or memory_source.get("tracked_status_before") != ""
        or memory_source.get("tracked_status_after") != ""
        or memory_source.get("worktree_status_before") != ""
        or memory_source.get("worktree_status_after") != ""
        or memory_source.get("nonignored_untracked_before") != []
        or memory_source.get("nonignored_untracked_after") != []
    ):
        raise AnalysisError(f"{point['point_id']}: Hybrid source is not clean and stable")
    metadata = _mapping(solver.get("metadata"))
    for key in ("commit_sha", "verified_clean_sha", "source_commit_at_end_full_sha"):
        _require_sha(
            metadata.get(key),
            expected_sha,
            f"hybrid_m{mode_count}.metadata.{key}",
        )
    if (
        metadata.get("source_clean_and_stable") is not True
        or metadata.get("git_dirty") is not False
        or metadata.get("tracked_source_dirty") is not False
    ):
        raise AnalysisError(f"{point['point_id']}: Hybrid solver source is not clean")
    if _dig(memory, "source_gate", "pass") is not True:
        raise AnalysisError(f"{point['point_id']}: Hybrid source gate failed")
    if _dig(memory, "launch_gate", "pass") is not True:
        raise AnalysisError(f"{point['point_id']}: Hybrid launch gate failed")

    bindings = [
        _dig(memory, "launch_gate", "matching_full3d_reference"),
        _dig(metadata, "task036_domain_robustness_authority_gate"),
    ]
    for index, binding_value in enumerate(bindings):
        binding = _mapping(binding_value)
        if binding.get("pass") is not True:
            raise AnalysisError(
                f"{point['point_id']}: Full3D binding {index} is not a pass"
            )
        _require_hash(
            binding.get("expected_sha256"),
            full3d_sha,
            f"hybrid_m{mode_count}.binding[{index}].expected_sha256",
        )
        _require_hash(
            binding.get("observed_sha256"),
            full3d_sha,
            f"hybrid_m{mode_count}.binding[{index}].observed_sha256",
        )
        for key in ("reference_source_sha", "current_source_sha"):
            _require_sha(
                binding.get(key),
                expected_sha,
                f"hybrid_m{mode_count}.binding[{index}].{key}",
            )

    case = _mapping(solver.get("case"))
    if metadata.get("mpi_size") != 8:
        raise AnalysisError(f"{point['point_id']}: Hybrid must be MPI8")
    if case.get("degree") != point["degree"] or case.get("modal_degree") != point["degree"]:
        raise AnalysisError(f"{point['point_id']}: Hybrid degree identity mismatch")
    _same_float(case.get("h_nm"), point["h_nm"], "hybrid.h_nm")
    _same_float(case.get("modal_h_nm"), point["h_nm"], "hybrid.modal_h_nm")
    _same_float(
        case.get("grating_height_nm"),
        point["height_nm"],
        "hybrid.grating_height_nm",
    )
    _same_float(
        case.get("grating_width_x_nm"),
        point["width_x_nm"],
        "hybrid.grating_width_x_nm",
    )
    _same_float(
        case.get("incident_grazing_deg"),
        point["grazing_deg"],
        "hybrid.incident_grazing_deg",
    )
    _same_float(
        case.get("incident_phi_deg"),
        point["azimuth_deg"],
        "hybrid.incident_phi_deg",
    )
    if case.get("polarization_kind") != point["polarization"]:
        raise AnalysisError(f"{point['point_id']}: Hybrid polarization mismatch")
    if case.get("mesh_axis_cell_counts_actual_full_plan") != point["axis_counts"]:
        raise AnalysisError(f"{point['point_id']}: Hybrid mesh identity mismatch")
    if case.get("requested_modes_per_direction") != mode_count:
        raise AnalysisError(f"{point['point_id']}: Hybrid mode-count mismatch")
    if memory.get("requested_modes") != mode_count:
        raise AnalysisError(f"{point['point_id']}: watchdog mode-count mismatch")
    if memory.get("candidate_modes") != 2 * mode_count:
        raise AnalysisError(f"{point['point_id']}: Hybrid candidate window mismatch")
    hybrid_system = _mapping(solver.get("hybrid_system"))
    if (
        hybrid_system.get("bottom_assembly_backend_actual")
        != "assembly_time_static_condensed"
        or hybrid_system.get("top_assembly_backend_actual")
        != "assembly_time_static_condensed"
    ):
        raise AnalysisError(f"{point['point_id']}: Hybrid backend mismatch")

    order_values = _order_map(
        _dig(solver, "validation", "external_diffraction_orders"),
        f"{point['point_id']}.hybrid_m{mode_count}.orders",
    )
    residual = _optional_finite(_dig(solver, "solve", "true_relative_residual"))
    interface = _optional_finite(
        _dig(solver, "validation", "interface_e_projection", "combined_relative_residual")
    )
    traction_values = [
        _optional_finite(
            _dig(
                solver,
                "validation",
                "fe_modal_traction_equilibrium",
                side,
                "relative_dual",
            )
        )
        for side in ("bottom_dual", "top_dual")
    ]
    traction = (
        max(value for value in traction_values if value is not None)
        if any(value is not None for value in traction_values)
        else None
    )
    biorthogonality = _biorthogonality_row_norm(solver)
    port_power = _mapping(_dig(solver, "validation", "port_power"))
    r_total = _optional_finite(port_power.get("R_total"))
    t_total = _optional_finite(port_power.get("T_total"))
    a_volume = _optional_finite(
        _dig(
            solver,
            "physical_field_reconstruction",
            "volume_absorption",
            "A_volume_total",
        )
    )
    energy_closure = (
        abs(r_total + t_total + a_volume - 1.0)
        if r_total is not None and t_total is not None and a_volume is not None
        else None
    )
    direct_projection = _hybrid_direct_projection(solver)
    resource_gate = bool(
        memory.get("memory_authority_pass") is True
        and _dig(memory, "resource_authority", "gate", "pass") is True
    )
    peak_gib = _optional_finite(
        _dig(memory, "resource_authority", "memory_authority_gib")
    )
    wall_seconds = _optional_finite(_dig(solver, "timing_seconds_max_rank", "total"))
    external_pass = bool(
        memory.get("return_code") == 0
        and memory.get("no_swap") is True
        and memory.get("terminated_for_memory") is False
        and memory.get("terminated_for_timeout") is False
        and memory.get("terminated_for_authority_unreadable") is False
        and resource_gate
        and peak_gib is not None
        and peak_gib > 0.0
    )
    numerical_gates = {
        "external_watchdog_pass": external_pass,
        "true_residual_le_1e-9": residual is not None
        and residual <= TRUE_RESIDUAL_MAX,
        "interface_e_le_1e-8": interface is not None
        and interface <= INTERFACE_E_MAX,
        "exact_traction_le_1e-8": traction is not None
        and traction <= EXACT_TRACTION_MAX,
        "biorthogonality_row_le_1e-6": biorthogonality is not None
        and biorthogonality <= BIORTHOGONALITY_ROW_MAX,
        "energy_closure_le_1e-5": energy_closure is not None
        and energy_closure <= ENERGY_CLOSURE_MAX,
        "zero_swap": memory.get("no_swap") is True,
    }
    numerical_gates["pass"] = all(numerical_gates.values())
    formal_gates = {
        **numerical_gates,
        "candidate_direct_projection_le_1e-10": direct_projection["pass"],
    }
    formal_gates["pass"] = bool(
        numerical_gates["pass"] and direct_projection["pass"]
    )

    factor_inventory = _mapping(
        _dig(solver, "object_payload_ledger", "local_or_augmented_factor_inventory")
    )
    matrix_nnz_by_side = {
        side: _optional_finite(
            _dig(solver, "hybrid_system", f"{side}_matrix_stats", "matrix_nnz_used")
        )
        for side in ("bottom", "top")
    }
    factor_nnz_by_side = {
        side: _factor_nnz(
            factor_inventory.get(side),
            f"hybrid_m{mode_count}.factor_inventory.{side}",
        )
        for side in ("bottom", "top")
    }
    capacity = _capacity_evidence(solver, mode_count)
    return (
        {
            "status": "complete",
            "solver_record_path": str(solver_path),
            "solver_record_sha256": solver_sha,
            "memory_sampler_path": str(memory_path),
            "memory_sampler_sha256": _sha256(memory_path),
            "source_sha": expected_sha,
            "mode_count_per_direction": mode_count,
            "finite_candidate_count": {
                "positive": _dig(
                    solver,
                    "qep",
                    "positive_directional_selection",
                    "finite_candidate_count",
                ),
                "negative": _dig(
                    solver,
                    "qep",
                    "negative_directional_selection",
                    "finite_candidate_count",
                ),
            },
            "capacity": capacity,
            "metrics": {
                "true_relative_residual": residual,
                "interface_e_relative_residual": interface,
                "exact_traction_relative_dual": traction,
                "biorthogonality_row_norm": biorthogonality,
                "direct_projection_difference": direct_projection["difference"],
                "R_total": r_total,
                "T_total": t_total,
                "A_volume_total": a_volume,
                "energy_closure_error": energy_closure,
                "local_rows_by_side": {
                    side: _dig(
                        solver,
                        "hybrid_system",
                        f"{side}_static_condensation",
                        "local_algebra_rows",
                    )
                    for side in ("bottom", "top")
                },
                "internal_modal_rows": hybrid_system.get("internal_unknown_count"),
                "matrix_nnz_by_side": matrix_nnz_by_side,
                "matrix_nnz_inventory_sum_not_simultaneous_peak": (
                    sum(value for value in matrix_nnz_by_side.values() if value is not None)
                    if all(value is not None for value in matrix_nnz_by_side.values())
                    else None
                ),
                "factor_nnz_by_side": factor_nnz_by_side,
                "factor_nnz_inventory_sum_not_simultaneous_peak": (
                    sum(value for value in factor_nnz_by_side.values() if value is not None)
                    if all(value is not None for value in factor_nnz_by_side.values())
                    else None
                ),
                "modal_schur_shape": _dig(
                    solver, "hybrid_system", "modal_schur", "shape"
                ),
                "peak_memory_gib": peak_gib,
                "wall_seconds": wall_seconds,
            },
            "candidate_direct_projection": direct_projection,
            "numerical_individual_gates": numerical_gates,
            "formal_individual_gates": formal_gates,
            "formal_evidence_complete": direct_projection["available"],
        },
        order_values,
    )


def _significance_inventory(
    order_maps: Sequence[Mapping[tuple[str, int, int, str], Mapping[str, Any]]],
) -> dict[tuple[str, int, int, str], bool]:
    keys: set[tuple[str, int, int, str]] = set()
    for values in order_maps:
        keys.update(values)
    return {
        key: max(
            abs(float(values[key]["power"]))
            for values in order_maps
            if key in values
        )
        >= SIGNIFICANT_POWER_FLOOR
        for key in sorted(keys)
    }


def _compare_channels(
    left: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    right: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    significance: Mapping[tuple[str, int, int, str], bool],
    incident_polarization: str,
) -> dict[str, Any]:
    if not left or set(left) != set(right):
        raise AnalysisError("fixed diffraction-order coverage is missing or unequal")
    rows: list[dict[str, Any]] = []
    for key in sorted(left):
        left_row = left[key]
        right_row = right[key]
        left_amplitude = left_row["amplitude"]
        right_amplitude = right_row["amplitude"]
        left_power = float(left_row["power"])
        right_power = float(right_row["power"])
        amplitude_absolute = abs(right_amplitude - left_amplitude)
        amplitude_relative = amplitude_absolute / max(
            abs(left_amplitude),
            abs(right_amplitude),
            1.0e-30,
        )
        power_absolute = abs(right_power - left_power)
        power_relative = power_absolute / max(
            abs(left_power),
            abs(right_power),
            1.0e-30,
        )
        significant = bool(significance.get(key, False))
        amplitude_pass = (
            amplitude_relative <= SIGNIFICANT_RELATIVE_MAX
            if significant
            else amplitude_absolute <= WEAK_ABSOLUTE_MAX
        )
        power_pass = (
            power_relative <= SIGNIFICANT_RELATIVE_MAX
            if significant
            else power_absolute <= WEAK_ABSOLUTE_MAX
        )
        rows.append(
            {
                "key": list(key),
                "significant": significant,
                "cross_polarization": key[3] != incident_polarization,
                "left_propagating": left_row.get("propagating"),
                "right_propagating": right_row.get("propagating"),
                "left_power_carrying": left_row.get("power_carrying"),
                "right_power_carrying": right_row.get("power_carrying"),
                "left_power": left_power,
                "right_power": right_power,
                "power_absolute_error": power_absolute,
                "power_relative_error": power_relative,
                "left_amplitude": _complex_json(left_amplitude),
                "right_amplitude": _complex_json(right_amplitude),
                "complex_amplitude_absolute_error": amplitude_absolute,
                "complex_amplitude_relative_error": amplitude_relative,
                "power_pass": power_pass,
                "complex_amplitude_pass": amplitude_pass,
                "pass": power_pass and amplitude_pass,
            }
        )
    return {
        "coverage_equal": True,
        "fixed_channel_count": len(rows),
        "significant_channel_count": sum(row["significant"] for row in rows),
        "pass_count": sum(row["pass"] for row in rows),
        "pass": all(row["pass"] for row in rows),
        "failures": [row for row in rows if not row["pass"]],
        "rows": rows,
    }


def _compare_totals(
    left_metrics: Mapping[str, Any],
    right_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    deltas = {
        key: abs(
            _finite(left_metrics.get(key), f"left.{key}")
            - _finite(right_metrics.get(key), f"right.{key}")
        )
        for key in ("R_total", "T_total", "A_volume_total")
    }
    maximum = max(deltas.values())
    return {
        "absolute_deltas": deltas,
        "max_absolute_delta": maximum,
        "pass": maximum <= TOTAL_DELTA_MAX,
    }


def _resource_ratio(
    full3d: Mapping[str, Any],
    hybrid: Mapping[str, Any],
) -> dict[str, Any]:
    full_metrics = _mapping(full3d.get("metrics"))
    hybrid_metrics = _mapping(hybrid.get("metrics"))
    full_peak = _optional_finite(full_metrics.get("peak_memory_gib"))
    hybrid_peak = _optional_finite(hybrid_metrics.get("peak_memory_gib"))
    full_wall = _optional_finite(full_metrics.get("wall_seconds"))
    hybrid_wall = _optional_finite(hybrid_metrics.get("wall_seconds"))
    peak_ratio = (
        hybrid_peak / full_peak
        if hybrid_peak is not None and full_peak is not None and full_peak > 0.0
        else None
    )
    wall_ratio = (
        hybrid_wall / full_wall
        if hybrid_wall is not None and full_wall is not None and full_wall > 0.0
        else None
    )
    return {
        "hybrid_over_full3d_peak_memory": peak_ratio,
        "hybrid_over_full3d_wall": wall_ratio,
        "peak_memory_reduction_fraction": (
            None if peak_ratio is None else 1.0 - peak_ratio
        ),
        "wall_reduction_fraction": None if wall_ratio is None else 1.0 - wall_ratio,
        "authority": "simultaneous_process_tree_live_memory_and_solver_wall",
    }


def _comparison_to_full3d(
    full3d: Mapping[str, Any],
    full_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    hybrid: Mapping[str, Any],
    hybrid_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    significance: Mapping[tuple[str, int, int, str], bool],
    incident_polarization: str,
) -> dict[str, Any]:
    totals = _compare_totals(
        _mapping(full3d.get("metrics")),
        _mapping(hybrid.get("metrics")),
    )
    channels = _compare_channels(
        full_orders,
        hybrid_orders,
        significance,
        incident_polarization,
    )
    numerical = bool(
        _dig(full3d, "gates", "pass") is True
        and _dig(hybrid, "numerical_individual_gates", "pass") is True
        and totals["pass"]
        and channels["pass"]
    )
    formal = bool(
        numerical
        and _dig(hybrid, "formal_individual_gates", "pass") is True
    )
    return {
        "totals": totals,
        "fixed_channels": channels,
        "numerical_pass": numerical,
        "formal_pass": formal,
    }


def _adjacent_pair(
    previous_m: int,
    previous: Mapping[str, Any],
    previous_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    current_m: int,
    current: Mapping[str, Any],
    current_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    significance: Mapping[tuple[str, int, int, str], bool],
    incident_polarization: str,
) -> dict[str, Any]:
    totals = _compare_totals(
        _mapping(previous.get("metrics")),
        _mapping(current.get("metrics")),
    )
    channels = _compare_channels(
        previous_orders,
        current_orders,
        significance,
        incident_polarization,
    )
    adjacent_numerical = bool(
        _dig(previous, "numerical_individual_gates", "pass") is True
        and _dig(current, "numerical_individual_gates", "pass") is True
        and totals["pass"]
        and channels["pass"]
    )
    numerical_qualification = bool(
        adjacent_numerical
        and _dig(previous, "full3d_comparison", "numerical_pass") is True
        and _dig(current, "full3d_comparison", "numerical_pass") is True
    )
    formal_qualification = bool(
        numerical_qualification
        and _dig(previous, "formal_individual_gates", "pass") is True
        and _dig(current, "formal_individual_gates", "pass") is True
        and _dig(previous, "full3d_comparison", "formal_pass") is True
        and _dig(current, "full3d_comparison", "formal_pass") is True
    )
    return {
        "previous_m": previous_m,
        "current_m": current_m,
        "totals": totals,
        "fixed_channels": channels,
        "adjacent_numerical_pass": adjacent_numerical,
        "numerical_qualification_pass": numerical_qualification,
        "formal_qualification_pass": formal_qualification,
    }


def _point_failure_buckets(
    hybrids: Mapping[int, Mapping[str, Any]],
) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for mode_count in sorted(hybrids):
        hybrid = hybrids[mode_count]
        comparison = _mapping(hybrid.get("full3d_comparison"))
        channels = _mapping(comparison.get("fixed_channels"))
        for row in channels.get("failures", []):
            prefix = "significant" if row["significant"] else "weak"
            suffix = "cross_polarization" if row["cross_polarization"] else "co_polarization"
            result[f"{prefix}_{suffix}"].append(
                {"mode_count": mode_count, "key": row["key"]}
            )
        if _dig(comparison, "totals", "pass") is False:
            result["totals"].append(mode_count)
        gates = _mapping(hybrid.get("numerical_individual_gates"))
        for name, passed in gates.items():
            if name != "pass" and passed is False:
                result[name].append(mode_count)
        if hybrid.get("formal_evidence_complete") is False:
            result["candidate_direct_projection_evidence_missing"].append(mode_count)
    return {key: result[key] for key in sorted(result)}


def _classify_point(
    full3d: Mapping[str, Any],
    hybrids: Mapping[int, Mapping[str, Any]],
    adjacent_pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    complete_modes = [
        mode for mode, value in sorted(hybrids.items()) if value.get("status") == "complete"
    ]
    numerical_minimum: int | None = None
    formal_minimum: int | None = None
    for pair in adjacent_pairs:
        if numerical_minimum is None and pair["numerical_qualification_pass"]:
            numerical_minimum = int(pair["previous_m"])
        if formal_minimum is None and pair["formal_qualification_pass"]:
            formal_minimum = int(pair["previous_m"])

    if complete_modes:
        last_m = complete_modes[-1]
        last = hybrids[last_m]
        capacity_pass = _dig(last, "capacity", "explicit_last_m_capacity_pass") is True
        if (
            numerical_minimum is None
            and capacity_pass
            and _dig(last, "full3d_comparison", "numerical_pass") is True
        ):
            numerical_minimum = last_m
        if (
            formal_minimum is None
            and capacity_pass
            and _dig(last, "full3d_comparison", "formal_pass") is True
        ):
            formal_minimum = last_m

    evidence_complete = bool(
        complete_modes
        and all(hybrids[mode]["formal_evidence_complete"] for mode in complete_modes)
    )
    adjacent_converged = any(
        pair["adjacent_numerical_pass"] for pair in adjacent_pairs
    )
    full3d_pass = _dig(full3d, "gates", "pass") is True
    same_p_full3d_pass = {
        str(mode): bool(_dig(hybrids[mode], "full3d_comparison", "numerical_pass"))
        for mode in complete_modes
    }
    individual_numerical_pass = all(
        _dig(hybrids[mode], "numerical_individual_gates", "pass") is True
        for mode in complete_modes
    )
    plateau = any(
        pair["adjacent_numerical_pass"]
        and not pair["numerical_qualification_pass"]
        for pair in adjacent_pairs
    )
    if not full3d_pass:
        status = "full3d_failed"
    elif not complete_modes:
        status = "hybrid_not_run"
    elif not individual_numerical_pass:
        status = "basis_or_physical_gate_failed"
    elif plateau:
        status = "rank_plateau_not_sufficient"
    elif numerical_minimum is not None and formal_minimum is None:
        status = "formal_evidence_incomplete"
    elif formal_minimum is not None:
        status = "qualified"
    elif len(complete_modes) == 1 and not _dig(
        hybrids[complete_modes[0]],
        "capacity",
        "explicit_last_m_capacity_pass",
    ):
        status = "rank_pending_next_m"
    else:
        status = "rank_not_converged"
    return {
        "status": status,
        "adjacent_m_converged": adjacent_converged,
        "same_p_full3d_pass_by_m": same_p_full3d_pass,
        "numerical_minimum_passing_M": numerical_minimum,
        "formal_evidence_complete": evidence_complete,
        "formal_minimum_passing_M": formal_minimum,
        "finite_candidate_count_used_as_capacity": False,
    }


def analyze_point(
    point_row: Mapping[str, Any],
    point_dir: Path,
    expected_sha: str,
) -> dict[str, Any]:
    """Analyze one frozen Task036 point without executing a PDE."""

    if FULL_SHA_RE.fullmatch(expected_sha) is None:
        raise AnalysisError("expected source SHA must be 40 lowercase hex characters")
    point = _normalize_point(point_row)
    _validate_point(point)
    watchdog_path = point_dir / "full3d" / "watchdog_summary.json"
    if not watchdog_path.is_file():
        return {
            "point_id": point["point_id"],
            "input": point,
            "status": "not_run",
            "full3d": {"status": "not_run"},
            "hybrid_by_m": {},
            "adjacent_pairs": [],
            "classification": {
                "status": "not_run",
                "numerical_minimum_passing_M": None,
                "formal_minimum_passing_M": None,
            },
            "failure_buckets": {},
        }

    full3d, full_orders = _verify_full3d(point, point_dir, expected_sha)
    hybrid_dirs: list[tuple[int, Path]] = []
    if point_dir.is_dir():
        for path in point_dir.iterdir():
            match = HYBRID_DIR_RE.fullmatch(path.name)
            if path.is_dir() and match is not None:
                hybrid_dirs.append((int(match.group(1)), path))
    hybrids: dict[int, dict[str, Any]] = {}
    hybrid_orders: dict[int, dict[tuple[str, int, int, str], dict[str, Any]]] = {}
    for mode_count, run_dir in sorted(hybrid_dirs):
        if mode_count in hybrids:
            raise AnalysisError(f"{point['point_id']}: duplicate Hybrid M{mode_count}")
        value, orders = _verify_hybrid(
            point,
            run_dir,
            mode_count,
            expected_sha,
            str(full3d["watchdog_sha256"]),
        )
        hybrids[mode_count] = value
        if value.get("status") == "complete":
            hybrid_orders[mode_count] = orders

    complete_modes = sorted(hybrid_orders)
    all_order_maps = [full_orders, *(hybrid_orders[mode] for mode in complete_modes)]
    significance = _significance_inventory(all_order_maps) if full_orders else {}
    for mode_count in complete_modes:
        hybrid = hybrids[mode_count]
        hybrid["full3d_comparison"] = _comparison_to_full3d(
            full3d,
            full_orders,
            hybrid,
            hybrid_orders[mode_count],
            significance,
            point["polarization"],
        )
        hybrid["resource_ratio"] = _resource_ratio(full3d, hybrid)

    adjacent_pairs = [
        _adjacent_pair(
            first,
            hybrids[first],
            hybrid_orders[first],
            second,
            hybrids[second],
            hybrid_orders[second],
            significance,
            point["polarization"],
        )
        for first, second in zip(complete_modes[:-1], complete_modes[1:], strict=True)
    ]
    classification = _classify_point(full3d, hybrids, adjacent_pairs)
    failure_buckets = _point_failure_buckets(hybrids)
    return {
        "point_id": point["point_id"],
        "input": point,
        "status": classification["status"],
        "full3d": full3d,
        "hybrid_by_m": {
            str(mode): hybrids[mode] for mode in sorted(hybrids)
        },
        "significance_inventory": {
            "definition": "max_abs_power_across_full3d_and_all_complete_hybrid_M",
            "power_floor": SIGNIFICANT_POWER_FLOOR,
            "significant_keys": [
                list(key) for key, significant_value in significance.items() if significant_value
            ],
        },
        "adjacent_pairs": adjacent_pairs,
        "classification": classification,
        "failure_buckets": failure_buckets,
    }


def build_failure_clusters(
    points: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Group points sharing one exact fixed-channel failure signature."""

    grouped: dict[tuple[tuple[Any, ...], ...], list[str]] = defaultdict(list)
    mechanisms: dict[tuple[tuple[Any, ...], ...], set[str]] = defaultdict(set)
    for point in points:
        signatures: set[tuple[Any, ...]] = set()
        point_mechanisms: set[str] = set()
        for mode_text, hybrid_value in _mapping(point.get("hybrid_by_m")).items():
            comparison = _mapping(_mapping(hybrid_value).get("full3d_comparison"))
            channels = _mapping(comparison.get("fixed_channels"))
            for row in channels.get("failures", []):
                signature = (
                    "significant" if row["significant"] else "weak",
                    "cross" if row["cross_polarization"] else "co",
                    *row["key"],
                )
                signatures.add(signature)
                point_mechanisms.add(f"{signature[0]}_{signature[1]}")
            if _dig(comparison, "totals", "pass") is False:
                signatures.add(("totals", str(mode_text)))
                point_mechanisms.add("totals")
        if signatures:
            key = tuple(sorted(signatures))
            grouped[key].append(str(point.get("point_id")))
            mechanisms[key].update(point_mechanisms)
    return [
        {
            "signature": [list(item) for item in signature],
            "mechanisms": sorted(mechanisms[signature]),
            "point_ids": sorted(grouped[signature]),
        }
        for signature in sorted(grouped)
    ]


def analyze_scan(
    point_rows: Sequence[Mapping[str, Any]],
    artifact_root: Path,
    expected_sha: str,
    *,
    points_sha256: str | None = None,
) -> dict[str, Any]:
    points = [
        analyze_point(row, artifact_root / str(row["point_id"]), expected_sha)
        for row in sorted(point_rows, key=lambda value: str(value["point_id"]))
    ]
    statuses: dict[str, int] = defaultdict(int)
    for point in points:
        statuses[str(point["status"])] += 1
    return {
        "analysis_contract": "task036_review_v2",
        "expected_source_sha": expected_sha,
        "points_sha256": points_sha256,
        "thresholds": {
            "true_residual": TRUE_RESIDUAL_MAX,
            "interface_e": INTERFACE_E_MAX,
            "exact_traction": EXACT_TRACTION_MAX,
            "biorthogonality_row": BIORTHOGONALITY_ROW_MAX,
            "candidate_direct_projection": DIRECT_PROJECTION_MAX,
            "energy_closure": ENERGY_CLOSURE_MAX,
            "same_p_and_adjacent_total_absolute": TOTAL_DELTA_MAX,
            "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
            "significant_channel_relative": SIGNIFICANT_RELATIVE_MAX,
            "weak_channel_absolute": WEAK_ABSOLUTE_MAX,
            "channel_tolerance_source": "existing_task033_funnel_contract",
        },
        "points": points,
        "summary": {
            "selected_point_count": len(points),
            "status_counts": {key: statuses[key] for key in sorted(statuses)},
            "failure_clusters": build_failure_clusters(points),
        },
    }


def _load_points(
    path: Path,
    rounds: set[str],
    point_ids: set[str],
) -> list[dict[str, str]]:
    if not path.is_file():
        raise AnalysisError(f"missing frozen point table: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    selected = [
        row
        for row in rows
        if (not rounds or row.get("round") in rounds)
        and (not point_ids or row.get("point_id") in point_ids)
    ]
    if not selected:
        raise AnalysisError("no frozen Task036 points matched the selection")
    return selected


def _csv_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in analysis["points"]:
        hybrids = _mapping(point.get("hybrid_by_m"))
        if not hybrids:
            rows.append(
                {
                    "point_id": point["point_id"],
                    "point_status": point["status"],
                    "mode_count": "",
                }
            )
            continue
        for mode_text, hybrid_value in sorted(
            hybrids.items(), key=lambda item: int(item[0])
        ):
            hybrid = _mapping(hybrid_value)
            comparison = _mapping(hybrid.get("full3d_comparison"))
            rows.append(
                {
                    "point_id": point["point_id"],
                    "point_status": point["status"],
                    "mode_count": mode_text,
                    "hybrid_status": hybrid.get("status"),
                    "numerical_individual_pass": _dig(
                        hybrid, "numerical_individual_gates", "pass"
                    ),
                    "formal_individual_pass": _dig(
                        hybrid, "formal_individual_gates", "pass"
                    ),
                    "same_p_full3d_numerical_pass": comparison.get("numerical_pass"),
                    "same_p_full3d_formal_pass": comparison.get("formal_pass"),
                    "fixed_channel_pass_count": _dig(
                        comparison, "fixed_channels", "pass_count"
                    ),
                    "fixed_channel_count": _dig(
                        comparison, "fixed_channels", "fixed_channel_count"
                    ),
                    "peak_memory_gib": _dig(
                        hybrid, "metrics", "peak_memory_gib"
                    ),
                    "wall_seconds": _dig(hybrid, "metrics", "wall_seconds"),
                    "hybrid_over_full3d_peak_memory": _dig(
                        hybrid,
                        "resource_ratio",
                        "hybrid_over_full3d_peak_memory",
                    ),
                    "hybrid_over_full3d_wall": _dig(
                        hybrid, "resource_ratio", "hybrid_over_full3d_wall"
                    ),
                }
            )
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze existing Task036 V2 Full3D/Hybrid artifacts."
    )
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--points", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--round", action="append", default=[])
    parser.add_argument("--point-id", action="append", default=[])
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        expected_sha = str(args.expected_source_sha).lower()
        if FULL_SHA_RE.fullmatch(expected_sha) is None:
            raise AnalysisError(
                "--expected-source-sha must be 40 lowercase hex characters"
            )
        points_path = args.points if args.points.is_absolute() else ROOT / args.points
        points = _load_points(
            points_path.resolve(),
            set(args.round),
            set(args.point_id),
        )
        analysis = analyze_scan(
            points,
            args.artifact_root.resolve(),
            expected_sha,
            points_sha256=_sha256(points_path),
        )
        rendered = json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        if args.output_csv is not None:
            _write_csv(args.output_csv, _csv_rows(analysis))
        return 0
    except AnalysisError as exc:
        print(f"Task036 analysis error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
