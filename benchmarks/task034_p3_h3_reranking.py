"""Task034 Phase D4 reranking against the p3/h3 finer discrete reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping

from benchmarks.task033_reduced_equal_accuracy import (
    ROOT,
    TRUE_RESIDUAL_MAX,
    ReducedEqualAccuracyError,
    _finite,
    _load_full3d,
    _order_error,
    _order_map,
    _physical_no_worse,
    _repo_path,
    _sha256,
    compare_full3d_to_reference,
)


class Task034RerankingError(ValueError):
    """Raised when Phase D4 evidence is incomplete or incompatible."""


_METRIC_PATHS = {
    "R_total_absolute_error": ("scalar_observables", "R_total", "absolute_error"),
    "T_total_absolute_error": ("scalar_observables", "T_total", "absolute_error"),
    "A_balance_absolute_error": (
        "scalar_observables",
        "A_balance",
        "absolute_error",
    ),
    "A_volume_total_absolute_error": (
        "scalar_observables",
        "A_volume_total",
        "absolute_error",
    ),
    "max_selected_plane_electric_relative_l2": (
        "selected_planes",
        "max_electric_relative_l2",
    ),
    "max_selected_plane_magnetic_relative_l2": (
        "selected_planes",
        "max_magnetic_relative_l2",
    ),
    "max_interface_electric_tangential_relative_l2": (
        "interfaces",
        "max_electric_tangential_relative_l2",
    ),
    "max_interface_magnetic_tangential_relative_l2": (
        "interfaces",
        "max_magnetic_tangential_relative_l2",
    ),
    "diffraction_power_relative_error_max": (
        "diffraction_orders",
        "power_relative_error_max",
    ),
    "diffraction_power_relative_error_rms": (
        "diffraction_orders",
        "power_relative_error_rms",
    ),
    "diffraction_complex_amplitude_relative_error_max": (
        "diffraction_orders",
        "complex_amplitude_relative_error_max",
    ),
    "diffraction_complex_amplitude_relative_error_rms": (
        "diffraction_orders",
        "complex_amplitude_relative_error_rms",
    ),
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task034RerankingError(
            f"cannot read JSON evidence {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise Task034RerankingError(f"JSON evidence must be an object: {path}")
    return value


def _nested(record: Mapping[str, Any], path: tuple[str, ...], *, label: str) -> float:
    value: Any = record
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            raise Task034RerankingError(f"missing {label}: {'.'.join(path)}")
        value = value[key]
    try:
        return _finite(value, label=label)
    except ReducedEqualAccuracyError as exc:
        raise Task034RerankingError(str(exc)) from exc


def comparison_metric_vector(comparison: Mapping[str, Any]) -> dict[str, float]:
    """Return the exact twelve-observable Task033 D1 error vector."""

    return {
        name: _nested(comparison, path, label=name)
        for name, path in _METRIC_PATHS.items()
    }


def rerank_against_p2_threshold(
    comparisons: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rank by the worst component ratio to the p2/h3 D1 threshold vector."""

    if "p2_h3" not in comparisons:
        raise Task034RerankingError("p2_h3 threshold comparison is required")
    vectors = {
        name: comparison_metric_vector(comparison)
        for name, comparison in comparisons.items()
    }
    baseline = vectors["p2_h3"]
    if any(value <= 0.0 for value in baseline.values()):
        raise Task034RerankingError("p2/h3 threshold vector must be strictly positive")
    rows = []
    for name, vector in vectors.items():
        ratios = {key: vector[key] / baseline[key] for key in baseline}
        residual = _nested(
            comparisons[name],
            ("full_true_relative_residual",),
            label=f"{name}.full_true_relative_residual",
        )
        rows.append(
            {
                "candidate": name,
                "metric_vector": vector,
                "ratio_to_p2_h3_threshold": ratios,
                "max_ratio_to_p2_h3_threshold": max(ratios.values()),
                "componentwise_no_worse_than_p2_h3": all(
                    ratio <= 1.0 for ratio in ratios.values()
                ),
                "full_true_residual": residual,
                "full_true_residual_le_1e-9": residual <= TRUE_RESIDUAL_MAX,
            }
        )
    rows.sort(
        key=lambda row: (row["max_ratio_to_p2_h3_threshold"], row["candidate"])
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _hybrid_comparison(
    *,
    reference: Mapping[str, Any],
    watchdog_path: Path,
    funnel_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    watchdog = _read_json(watchdog_path)
    funnel = _read_json(funnel_path)
    checks = {
        "watchdog_schema": (
            watchdog.get("schema_version") == "task033.memory-watchdog.v2"
        ),
        "watchdog_formal_pass": watchdog.get("formal_pass") is True,
        "watchdog_numeric_pass": watchdog.get("numeric_pass") is True,
        "watchdog_zero_swap": watchdog.get("no_swap") is True,
        "watchdog_m160": watchdog.get("requested_modes") == 160,
        "funnel_qualified": funnel.get("status") == "qualified",
        "funnel_degree_p3": funnel.get("case", {}).get("degree") == 3,
        "funnel_h3": math.isclose(
            float(funnel.get("case", {}).get("h_nm", math.nan)),
            3.0,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "funnel_includes_m160": (
            160 in funnel.get("case", {}).get("mode_counts", [])
        ),
        "funnel_m160_all_gates": (
            funnel.get("individual_gates", {})
            .get("160", {})
            .get("all_reported_gates_pass")
            is True
        ),
    }
    source_rows = funnel.get("source_records")
    if not isinstance(source_rows, list):
        raise Task034RerankingError("funnel source_records are missing")
    selected = [
        row
        for row in source_rows
        if isinstance(row, Mapping) and row.get("mode_count_per_direction") == 160
    ]
    checks["single_funnel_m160_record"] = len(selected) == 1
    if len(selected) == 1:
        checks["funnel_m160_path_matches"] = (
            Path(str(selected[0].get("path"))).resolve() == watchdog_path.resolve()
        )
        checks["funnel_m160_sha_matches"] = (
            selected[0].get("sha256") == _sha256(watchdog_path)
        )
    measurements = watchdog.get("measurements")
    if not isinstance(measurements, Mapping):
        raise Task034RerankingError("Hybrid watchdog measurements are missing")
    gates = measurements.get("gates")
    checks["all_hybrid_measurement_gates"] = (
        isinstance(gates, Mapping)
        and bool(gates)
        and all(value is True for value in gates.values())
    )
    source = watchdog.get("source")
    checks["hybrid_source_clean_and_stable"] = (
        isinstance(source, Mapping)
        and source.get("source_clean_verified") is True
        and source.get("source_stable_during_run") is True
    )
    reconstruction = measurements.get("physical_field_reconstruction")
    validation = measurements.get("validation")
    solve = measurements.get("solve")
    if not all(
        isinstance(value, Mapping) for value in (reconstruction, validation, solve)
    ):
        raise Task034RerankingError("Hybrid physical evidence is incomplete")
    selected_planes = reconstruction.get("selected_plane_full3d_comparison")
    volume = reconstruction.get("volume_absorption")
    port = validation.get("port_power")
    if not all(
        isinstance(value, Mapping) for value in (selected_planes, volume, port)
    ):
        raise Task034RerankingError("Hybrid comparison fields are incomplete")
    binding = reference["descriptor"].get("derived_descriptor")
    checks["reference_descriptor_derivative_bound"] = isinstance(binding, Mapping)
    if isinstance(binding, Mapping):
        checks["hybrid_original_reference_sha_matches"] = (
            selected_planes.get("reference_record_sha256")
            == binding.get("source_descriptor_sha256")
        )
    ref_npz = reference["descriptor"]["artifacts"]["reference_npz_sha256"]
    checks["hybrid_reference_npz_matches"] = (
        selected_planes.get("reference_npz_sha256_expected") == ref_npz
        and selected_planes.get("reference_npz_sha256_observed") == ref_npz
        and selected_planes.get("reference_binding_verified") is True
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise Task034RerankingError(
            "Hybrid selected-M evidence failed: " + ", ".join(failures)
        )
    ref_results = reference["descriptor"]["results"]
    scalar_values = {
        "R_total": port.get("R_total"),
        "T_total": port.get("T_total"),
        "A_balance": port.get("A_balance"),
        "A_volume_total": volume.get("A_volume_total"),
    }
    scalars = {}
    for name, value in scalar_values.items():
        reference_value = _finite(ref_results.get(name), label=f"reference.{name}")
        candidate_value = _finite(value, label=f"Hybrid.{name}")
        scalars[name] = {
            "reference": reference_value,
            "candidate": candidate_value,
            "absolute_error": abs(candidate_value - reference_value),
        }
    planes = selected_planes.get("planes")
    if not isinstance(planes, list) or len(planes) != 5:
        raise Task034RerankingError("Hybrid comparison must contain five planes")
    reference_z = [float(value) for value in reference["arrays"]["z_nm"]]
    if [float(row.get("z_nm")) for row in planes] != reference_z:
        raise Task034RerankingError("Hybrid selected-plane coordinates differ")
    plane_rows = [
        {
            "z_nm": float(row["z_nm"]),
            "electric_relative_l2": _finite(
                row.get("electric", {}).get("relative_l2"),
                label="Hybrid plane E",
            ),
            "magnetic_relative_l2": _finite(
                row.get("magnetic", {}).get("relative_l2"),
                label="Hybrid plane H",
            ),
        }
        for row in planes
    ]
    interface_rows = [
        {
            "z_nm": float(row["z_nm"]),
            "electric_tangential_relative_l2": _finite(
                row.get("electric_tangential", {}).get("relative_l2"),
                label="Hybrid interface E",
            ),
            "magnetic_tangential_relative_l2": _finite(
                row.get("magnetic_tangential", {}).get("relative_l2"),
                label="Hybrid interface H",
            ),
        }
        for row in (planes[0], planes[-1])
    ]
    orders = validation.get("external_diffraction_orders")
    if not isinstance(orders, list):
        raise Task034RerankingError("Hybrid diffraction orders are missing")
    comparison = {
        "scalar_observables": scalars,
        "selected_planes": {
            "rows": plane_rows,
            "max_electric_relative_l2": max(
                row["electric_relative_l2"] for row in plane_rows
            ),
            "max_magnetic_relative_l2": max(
                row["magnetic_relative_l2"] for row in plane_rows
            ),
        },
        "interfaces": {
            "rows": interface_rows,
            "max_electric_tangential_relative_l2": max(
                row["electric_tangential_relative_l2"] for row in interface_rows
            ),
            "max_magnetic_tangential_relative_l2": max(
                row["magnetic_tangential_relative_l2"] for row in interface_rows
            ),
        },
        "diffraction_orders": _order_error(
            reference["orders"], _order_map({"orders": orders})
        ),
        "full_true_relative_residual": _finite(
            solve.get("true_relative_residual"), label="Hybrid true residual"
        ),
    }
    provenance = {
        "watchdog_path": watchdog_path.relative_to(ROOT).as_posix(),
        "watchdog_sha256": _sha256(watchdog_path),
        "funnel_path": funnel_path.relative_to(ROOT).as_posix(),
        "funnel_sha256": _sha256(funnel_path),
        "source_commit_sha": source.get("commit_sha"),
        "requested_modes": 160,
        "checks": checks,
        "failures": failures,
    }
    return comparison, provenance


def _numerical_audit(path: Path) -> dict[str, Any]:
    audit = _read_json(path)
    rows = audit.get("rows")
    if (
        audit.get("status") != "numerical_blob_compatibility_pass"
        or audit.get("formal_pass") is not True
        or audit.get("failures") != []
        or not isinstance(rows, list)
        or not rows
        or not all(row.get("pass") is True for row in rows)
    ):
        raise Task034RerankingError(
            "numerical-blob audit is not a clean formal pass"
        )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
        "status": audit["status"],
        "formal_pass": True,
        "corresponding_pde_rerun_required_paths": audit.get(
            "corresponding_pde_rerun_required_paths", []
        ),
    }


def _input_descriptor(record: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "descriptor_path",
        "descriptor_sha256",
        "run_root",
        "run_summary_path",
        "run_summary_sha256",
        "orders_sha256",
    )
    return {key: record[key] for key in keys}


def build_p3_h3_reranking(
    *,
    p3_h3_reference: Path | str,
    p2_h3_reference: Path | str,
    p3_h7p5_reference: Path | str,
    p3_h5_reference: Path | str,
    hybrid_m160_watchdog: Path | str,
    hybrid_funnel: Path | str,
    numerical_blob_audit: Path | str,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Build the complete Task034 Phase D4 measured reranking record."""

    root = Path(repo_root).resolve()
    if root != ROOT.resolve():
        raise Task034RerankingError(
            "Task034 reranking must run from this repository"
        )
    try:
        reference = _load_full3d(p3_h3_reference, root=root)
        candidates = {
            "p2_h3": _load_full3d(p2_h3_reference, root=root),
            "p3_h7p5": _load_full3d(p3_h7p5_reference, root=root),
            "p3_h5": _load_full3d(p3_h5_reference, root=root),
        }
    except ReducedEqualAccuracyError as exc:
        raise Task034RerankingError(str(exc)) from exc
    expected = {
        "p3_h3": (3, 3.0),
        "p2_h3": (2, 3.0),
        "p3_h7p5": (3, 7.5),
        "p3_h5": (3, 5.0),
    }
    for name, item in {"p3_h3": reference, **candidates}.items():
        degree, h_nm = expected[name]
        if (
            item["degree"] != degree
            or not math.isclose(
                item["h_nm"], h_nm, rel_tol=0.0, abs_tol=1.0e-12
            )
            or item["execution"]["no_swap"] is not True
        ):
            raise Task034RerankingError(
                f"unexpected or unqualified input {name}"
            )
    comparisons = {
        name: compare_full3d_to_reference(reference, candidate)
        for name, candidate in candidates.items()
    }
    watchdog_path, _ = _repo_path(hybrid_m160_watchdog, root=root)
    funnel_path, _ = _repo_path(hybrid_funnel, root=root)
    hybrid_comparison, hybrid_provenance = _hybrid_comparison(
        reference=reference,
        watchdog_path=watchdog_path,
        funnel_path=funnel_path,
    )
    comparisons["p3_h3_hybrid_m160"] = hybrid_comparison
    decisions = {
        name: _physical_no_worse(comparisons["p2_h3"], comparisons[name])
        for name in ("p3_h7p5", "p3_h5", "p3_h3_hybrid_m160")
    }
    p2_checks = {
        "defines_task033_d1_threshold_vector": True,
        "all_twelve_threshold_components_finite": (
            len(comparison_metric_vector(comparisons["p2_h3"])) == 12
        ),
        "full_true_residual_le_1e-9": (
            comparisons["p2_h3"]["full_true_relative_residual"]
            <= TRUE_RESIDUAL_MAX
        ),
    }
    p2_pass = all(p2_checks.values())
    audit_path, _ = _repo_path(numerical_blob_audit, root=root)
    source_audit = _numerical_audit(audit_path)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=root,
        text=True,
    ).strip()
    record: dict[str, Any] = {
        "schema_version": "task034.case092.p3-h3-reranking.v1",
        "record_type": "task034_p3_h3_reference_and_reranking",
        "case_id": "092_workstation_wsl_adaptive_scalability",
        "status": (
            "p3_h3_reference_and_reranking_pass"
            if p2_pass and decisions["p3_h7p5"]["pass"]
            else "p3_h3_reference_and_reranking_negative"
        ),
        "aggregation_source": {
            "commit_sha": head,
            "worktree_clean_including_nonignored_untracked": not status,
            "status_short": status,
        },
        "identity": {
            "is_pde_run": False,
            "consumes_measured_pde_records": True,
            "reference_identity": "p3_h3_finer_discrete_reference",
            "continuum_reference": False,
            "grid_convergence_proven": False,
            "threshold_rule": (
                "Task033 D1 componentwise no-worse: p2/h3 errors against "
                "p3/h3 define the twelve-component threshold vector; "
                "true residual <= 1e-9"
            ),
            "thresholds_relaxed": False,
        },
        "source_compatibility": source_audit,
        "inputs": {
            "p3_h3_reference": _input_descriptor(reference),
            "candidates": {
                name: _input_descriptor(item)
                for name, item in candidates.items()
            },
            "p3_h3_hybrid_m160": hybrid_provenance,
        },
        "comparison_to_p3_h3_finer_discrete_reference": comparisons,
        "task033_d1_componentwise_decisions": {
            "p2_h3": {
                "pass": p2_pass,
                "checks": p2_checks,
                "failures": [
                    name for name, passed in p2_checks.items() if not passed
                ],
                "semantics": (
                    "baseline threshold vector, not a zero-error self-comparison"
                ),
            },
            **decisions,
        },
        "reranking": {
            "method": (
                "ascending worst component ratio to the p2/h3 Task033 D1 "
                "threshold vector"
            ),
            "uses_full_true_residual_as_gate_not_ranking_score": True,
            "rows": rerank_against_p2_threshold(comparisons),
        },
        "classification": {
            "p3_h3_reference_available": True,
            "p3_h5_to_h3_grid_change": "measured",
            "p3_h7p5_equal_accuracy_under_new_reference": (
                "pass" if decisions["p3_h7p5"]["pass"] else "fail"
            ),
            "p2_h3_equal_accuracy_under_new_reference": (
                "pass" if p2_pass else "fail"
            ),
            "grid_convergence_proven": False,
            "continuum_reference": False,
        },
        "limitations": [
            "p3/h3 is a finer discrete reference, not a continuum reference.",
            (
                "The p2/h3 vector defines the Task033 D1 threshold; its pass "
                "is a baseline qualification, not zero discretization error."
            ),
            (
                "The scalar reranking score does not replace the twelve "
                "componentwise checks."
            ),
            (
                "Wall-time and memory provenance are not mixed into the "
                "physical-error ranking."
            ),
        ],
    }
    canonical = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    record["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p3-h3-reference", required=True)
    parser.add_argument("--p2-h3-reference", required=True)
    parser.add_argument("--p3-h7p5-reference", required=True)
    parser.add_argument("--p3-h5-reference", required=True)
    parser.add_argument("--hybrid-m160-watchdog", required=True)
    parser.add_argument("--hybrid-funnel", required=True)
    parser.add_argument("--numerical-blob-audit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    record = build_p3_h3_reranking(
        p3_h3_reference=args.p3_h3_reference,
        p2_h3_reference=args.p2_h3_reference,
        p3_h7p5_reference=args.p3_h7p5_reference,
        p3_h5_reference=args.p3_h5_reference,
        hybrid_m160_watchdog=args.hybrid_m160_watchdog,
        hybrid_funnel=args.hybrid_funnel,
        numerical_blob_audit=args.numerical_blob_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": record["status"],
                "classification": record["classification"],
                "payload_sha256": record["payload_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return (
        0
        if record["status"] == "p3_h3_reference_and_reranking_pass"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Task034RerankingError",
    "build_p3_h3_reranking",
    "comparison_metric_vector",
    "rerank_against_p2_threshold",
]
