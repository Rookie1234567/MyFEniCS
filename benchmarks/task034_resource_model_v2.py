"""Component-separated Task034 resource model; never authorizes a PDE run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


GIB = 1024**3
REFERENCE_WAVELENGTH_NM = 13.5
WAVELENGTHS_NM = (13.5, 5.0, 2.0, 1.0, 0.7)
BUDGETS_GIB = (256.0, 1024.0, 2048.0)
MPI_SIZE = 48
COMPLEX_BYTES = 16
SPARSE_ENTRY_BYTES = 24
REPLICATED_MODAL_OBJECT_COUNT = 6
SCENARIO_METADATA = {
    "p2_h3_current_layout_stress_test": {
        "degree": 2,
        "h_nm": 3.0,
        "accuracy_role": "Task033 equal-accuracy threshold baseline",
    },
    "p3_h3_finer_discrete_stress_test": {
        "degree": 3,
        "h_nm": 3.0,
        "accuracy_role": "Task034 p3 finer discrete reference",
    },
    "p4_h5_best_available_stress_test": {
        "degree": 4,
        "h_nm": 5.0,
        "accuracy_role": "Case093 best available discrete reference",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _require(value: Any, name: str) -> float:
    number = _finite(value)
    if number is None or number <= 0.0:
        raise ValueError(f"missing positive {name}")
    return number


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _factor_nnz(ledger: Mapping[str, Any], side: str) -> float:
    inventory = _mapping(ledger.get("local_or_augmented_factor_inventory"))
    matrix = _mapping(_mapping(inventory.get(side)).get("matrix_stats"))
    return _require(matrix.get("matrix_nnz_used"), f"{side} factor nnz")


def _base_components(payload: Mapping[str, Any]) -> dict[str, float]:
    measurements = _mapping(payload.get("measurements"))
    system = _mapping(measurements.get("hybrid_system"))
    qep = _mapping(measurements.get("qep"))
    ledger = _mapping(measurements.get("object_payload_ledger"))
    fields = _mapping(measurements.get("physical_field_reconstruction"))
    memory = _mapping(payload.get("memory"))
    bottom = _mapping(system.get("bottom_matrix_stats"))
    top = _mapping(system.get("top_matrix_stats"))
    projection = _mapping(ledger.get("projection_matrix"))
    modal_schur = _mapping(system.get("modal_schur"))
    shape = qep.get("full_shape")
    if not isinstance(shape, list) or not shape:
        raise ValueError("missing QEP shape")
    qep_dofs = _require(shape[0], "QEP DoF")
    local_dofs = _require(
        system.get("bottom_local_fe_dofs"), "bottom FE DoF"
    ) + _require(system.get("top_local_fe_dofs"), "top FE DoF")
    assembly_nnz = _require(
        bottom.get("matrix_nnz_used"), "bottom assembly nnz"
    ) + _require(top.get("matrix_nnz_used"), "top assembly nnz")
    factor_nnz = _factor_nnz(ledger, "bottom") + _factor_nnz(ledger, "top")
    projection_bytes = sum(
        _require(
            _mapping(projection.get(side)).get("matrix_memory_estimate_bytes"),
            f"{side} projection bytes",
        )
        for side in ("bottom", "top")
    )
    transient = _mapping(modal_schur.get("transient_dense_rhs_solution_bytes"))
    multi_rhs_bytes = _require(
        transient.get("bottom"), "bottom multi-RHS bytes"
    ) + _require(transient.get("top"), "top multi-RHS bytes")
    modes = _require(payload.get("requested_modes"), "retained modes")
    one_m_square = (2.0 * modes) ** 2 * COMPLEX_BYTES
    components = {
        "local_3d_fe_assembly": assembly_nnz * SPARSE_ENTRY_BYTES,
        "local_3d_factorization": factor_nnz * SPARSE_ENTRY_BYTES,
        "qep_coefficient_matrices": 3.0 * qep_dofs * 80.0 * SPARSE_ENTRY_BYTES,
        "qep_shift_invert_factorization": 48.0 * qep_dofs**1.5,
        "right_left_mode_vectors": _require(
            ledger.get("retained_right_left_eigenvector_bytes"), "mode vector bytes"
        ),
        "interface_projection_n_times_m": projection_bytes,
        "replicated_dense_modal_arrays": (
            one_m_square * REPLICATED_MODAL_OBJECT_COUNT * MPI_SIZE
        ),
        "hybrid_schur_dense_multi_rhs": multi_rhs_bytes,
        "field_reconstruction": (
            _require(fields.get("sample_payload_bytes"), "sample payload bytes")
            + 2.0 * local_dofs * COMPLEX_BYTES
        ),
    }
    measured_peak = (
        _require(memory.get("max_simultaneous_worker_rss_gib"), "peak memory") * GIB
    )
    accounted = sum(components.values())
    components["mpi_process_runtime_overhead"] = max(
        measured_peak - accounted, 0.25 * GIB
    )
    return {
        **components,
        "reference_peak_bytes": measured_peak,
        "reference_local_fe_dofs_sum": local_dofs,
        "reference_qep_dofs": qep_dofs,
        "reference_modes_per_direction": modes,
        "reference_one_complex_2m_square_bytes": one_m_square,
    }


def _classification(envelope_gib: float, largest_gib: float, budget_gib: float) -> str:
    if largest_gib >= budget_gib:
        return "infeasible_current_layout_by_single_component"
    if envelope_gib > budget_gib:
        return "cumulative_envelope_exceeds_budget_peak_unknown"
    if envelope_gib > 0.7 * budget_gib:
        return "cumulative_envelope_high_risk_peak_unknown"
    return "cumulative_envelope_within_guardband_peak_unknown"


def _prediction(
    base: Mapping[str, float], wavelength_nm: float, *, scenario_key: str = "test"
) -> dict[str, Any]:
    scale = REFERENCE_WAVELENGTH_NM / wavelength_nm
    exponents = {
        "local_3d_fe_assembly": 3.0,
        "local_3d_factorization": 4.0,
        "qep_coefficient_matrices": 2.0,
        "qep_shift_invert_factorization": 3.0,
        "right_left_mode_vectors": 4.0,
        "interface_projection_n_times_m": 4.0,
        "replicated_dense_modal_arrays": 4.0,
        "hybrid_schur_dense_multi_rhs": 5.0,
        "field_reconstruction": 3.0,
        "mpi_process_runtime_overhead": 0.0,
    }
    components = {
        name: {
            "bytes": float(base[name] * scale**exponent),
            "gib": float(base[name] * scale**exponent / GIB),
            "scaling_exponent_in_13p5_over_lambda": exponent,
            "data_identity": "measured_calibrated" if scale == 1.0 else "predicted",
        }
        for name, exponent in exponents.items()
    }
    envelope_gib = sum(row["gib"] for row in components.values())
    largest_name, largest = max(components.items(), key=lambda item: item[1]["gib"])
    local_names = {
        "local_3d_fe_assembly",
        "local_3d_factorization",
        "field_reconstruction",
    }
    local_gib = sum(components[name]["gib"] for name in local_names)
    modal_gib = envelope_gib - local_gib
    measured_peak_gib = base["reference_peak_bytes"] / GIB if scale == 1.0 else None
    budgets = {}
    for budget in BUDGETS_GIB:
        available_for_local = budget - modal_gib
        available_for_modal = budget - local_gib
        budgets[str(int(budget))] = {
            "budget_gib": budget,
            "classification": _classification(envelope_gib, largest["gib"], budget),
            "largest_component_lower_bound_ratio": largest["gib"] / budget,
            "cumulative_component_envelope_ratio": envelope_gib / budget,
            "simultaneous_peak_ratio": (
                measured_peak_gib / budget if measured_peak_gib is not None else None
            ),
            "required_local_compression_if_modal_unchanged": (
                None
                if available_for_local <= 0.0
                else max(1.0, local_gib / available_for_local)
            ),
            "required_modal_compression_if_local_unchanged": (
                None
                if available_for_modal <= 0.0
                else max(1.0, modal_gib / available_for_modal)
            ),
            "current_modal_layout_alone_exceeds_budget": modal_gib > budget,
            "cumulative_envelope_compression_ratio": max(1.0, envelope_gib / budget),
            "local_subtotal_to_half_budget_ratio": max(
                1.0, 2.0 * local_gib / budget
            ),
            "modal_subtotal_to_half_budget_ratio": max(
                1.0, 2.0 * modal_gib / budget
            ),
        }
    predicted_modes = int(math.ceil(base["reference_modes_per_direction"] * scale**2))
    one_square_gib = (2 * predicted_modes) ** 2 * COMPLEX_BYTES / GIB
    return {
        "scenario_key": scenario_key,
        "scenario": SCENARIO_METADATA.get(scenario_key, {}),
        "wavelength_nm": wavelength_nm,
        "scale_13p5_over_lambda": scale,
        "predicted_local_fe_dofs_sum_uniform": int(
            math.ceil(base["reference_local_fe_dofs_sum"] * scale**3)
        ),
        "predicted_cross_section_qep_dofs": int(
            math.ceil(base["reference_qep_dofs"] * scale**2)
        ),
        "predicted_modes_per_direction": predicted_modes,
        "one_complex_2m_square_gib": one_square_gib,
        "one_complex_2m_square_near_or_over_256gib": one_square_gib >= 0.7 * 256.0,
        "components": components,
        "local_component_subtotal_gib": local_gib,
        "modal_and_runtime_component_subtotal_gib": modal_gib,
        "cumulative_component_envelope_gib": envelope_gib,
        "measured_simultaneous_peak_gib": measured_peak_gib,
        "predicted_simultaneous_peak_gib": None,
        "simultaneous_peak_model_status": (
            "measured_at_reference" if scale == 1.0 else "unknown_no_lifecycle_overlap_model"
        ),
        "largest_component": largest_name,
        "largest_component_gib": largest["gib"],
        "budgets": budgets,
    }


def build_resource_model(
    *,
    fixed_geometry_csv: Path,
    adaptive_json: Path,
    baseline_hybrid_json: Path | None = None,
    baseline_hybrid_jsons: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    with fixed_geometry_csv.open(encoding="utf-8", newline="") as stream:
        fixed_rows = list(csv.DictReader(stream))
    adaptive = _load_json(adaptive_json)
    if baseline_hybrid_jsons is None:
        if baseline_hybrid_json is None:
            raise ValueError("at least one baseline Hybrid JSON is required")
        baseline_hybrid_jsons = {
            "p2_h3_current_layout_stress_test": baseline_hybrid_json
        }
    baseline_paths = dict(baseline_hybrid_jsons)
    baselines = {key: _load_json(path) for key, path in baseline_paths.items()}
    if len(fixed_rows) < 10:
        raise ValueError("Task034 resource model requires at least ten fixed p/h rows")
    decision = _mapping(adaptive.get("decision"))
    if decision.get("same_error_compression_demonstrated") is not False:
        raise ValueError("adaptive compression identity must be explicit")
    base_components = {key: _base_components(value) for key, value in baselines.items()}
    predictions = [
        _prediction(base, wavelength, scenario_key=key)
        for key, base in base_components.items()
        for wavelength in WAVELENGTHS_NM
    ]
    adaptive_profiles = _mapping(adaptive.get("profiles"))
    adaptive_calibration = []
    for name, record in adaptive_profiles.items():
        shards = record.get("shards") if isinstance(record, Mapping) else None
        if not isinstance(shards, list) or not shards:
            continue
        m160 = next(row for row in shards if row.get("mode_count") == 160)
        adaptive_calibration.append(
            {
                "profile": name,
                "same_error_qualified": record.get("status") == "same_error_qualified",
                "local_fe_dofs_sum": m160.get("local_fe_dofs_sum"),
                "factor_nnz_sum": m160.get("factor_nnz_sum"),
                "peak_memory_gib": m160.get("peak_memory_gib"),
                "wall_time_seconds": m160.get("wall_time_seconds"),
                "raw_dof_ratio_vs_uniform": record.get(
                    "raw_local_fe_dof_ratio_vs_uniform"
                ),
            }
        )
    return {
        "schema_version": "task034.resource-model.v2.1",
        "record_type": "component_separated_resource_prediction",
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "authorizes_heavy_launch": False,
            "proves_0p7nm_feasible": False,
            "ordinary_default_changed": False,
        },
        "inputs": {
            "fixed_geometry_csv": str(fixed_geometry_csv),
            "fixed_geometry_csv_sha256": _sha256(fixed_geometry_csv),
            "adaptive_json": str(adaptive_json),
            "adaptive_json_sha256": _sha256(adaptive_json),
            "baseline_hybrid_jsons": {
                key: {
                    "path": str(path),
                    "sha256": _sha256(path),
                    "scenario": SCENARIO_METADATA.get(key, {}),
                }
                for key, path in baseline_paths.items()
            },
            "mpi_size_for_replicated_layout": MPI_SIZE,
        },
        "calibration": {
            "fixed_geometry_rows": fixed_rows,
            "adaptive_m160_rows": adaptive_calibration,
            "reference_components_bytes_by_scenario": base_components,
            "measured_same_error_adaptive_compression_available": False,
            "allowed_adaptive_compression_factor_in_predictions": 1.0,
        },
        "scaling_model": {
            "spatial_policy": "mechanical fixed-layout scaling from p2/h3, p3/h3 and p4/h5 M160 stress-test scenarios; no common target-accuracy claim",
            "mode_policy": "M scales with transverse reciprocal-order area, s^2",
            "3d_direct_factor_policy": "nested-dissection engineering proxy, s^4",
            "replicated_layout_policy": f"{REPLICATED_MODAL_OBJECT_COUNT} complex (2M)^2 arrays on {MPI_SIZE} ranks",
            "dense_multi_rhs_policy": "local FE rows times modal RHS, s^5",
            "uncertainty": "engineering component envelope; lifecycle overlap, simultaneous extrapolated peak, material dispersion, target-accuracy DoF, cutoff changes and future solver redesign are unknown",
        },
        "predictions": predictions,
        "decision": {
            "current_layout_0p7nm": "single-component bottlenecks or cumulative-envelope budget crossings occur in the stress-test scenarios",
            "production_target_accuracy_0p7nm": "unknown",
            "predicted_simultaneous_peak_0p7nm": None,
            "cumulative_envelope_is_not_peak": True,
            "measured_adaptive_path_enters_budget": False,
            "required_redesign": [
                "qualified field-driven h-adaptivity",
                "matrix-free or low-storage iterative local solver",
                "distributed/streamed mode vectors",
                "remove replicated dense M^2 arrays",
                "blocked/streamed multi-RHS recovery",
            ],
        },
        "limitations": [
            "Predictions are not PDE runs and do not authorize a launch.",
            "No failed adaptive raw DoF ratio is credited as accuracy-preserving compression.",
            "Sparse factor and QEP fill exponents are engineering proxies, not exact asymptotics.",
            "Predicted mode counts require future physical convergence validation.",
            "The p2/p3/p4 scenarios are current-layout mechanical stress tests, not an equal-accuracy p-refinement comparison.",
            "Extrapolated simultaneous peak is unknown because component lifecycle overlap was not modelled.",
        ],
    }


def write_csv(model: Mapping[str, Any], path: Path) -> None:
    fields = [
        "scenario_key",
        "degree",
        "h_nm",
        "wavelength_nm",
        "budget_gib",
        "classification",
        "largest_component",
        "largest_component_gib",
        "largest_component_lower_bound_ratio",
        "cumulative_component_envelope_gib",
        "cumulative_component_envelope_ratio",
        "measured_simultaneous_peak_gib",
        "predicted_simultaneous_peak_gib",
        "simultaneous_peak_ratio",
        "simultaneous_peak_model_status",
        "predicted_local_fe_dofs_sum_uniform",
        "predicted_cross_section_qep_dofs",
        "predicted_modes_per_direction",
        "one_complex_2m_square_gib",
        "local_component_subtotal_gib",
        "modal_and_runtime_component_subtotal_gib",
        "cumulative_envelope_compression_ratio",
        "local_subtotal_to_half_budget_ratio",
        "modal_subtotal_to_half_budget_ratio",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for prediction in model["predictions"]:
            for budget in prediction["budgets"].values():
                writer.writerow(
                    {
                        **{name: prediction.get(name) for name in fields},
                        "budget_gib": budget["budget_gib"],
                        "classification": budget["classification"],
                        "degree": prediction["scenario"].get("degree"),
                        "h_nm": prediction["scenario"].get("h_nm"),
                        "largest_component_lower_bound_ratio": budget[
                            "largest_component_lower_bound_ratio"
                        ],
                        "cumulative_component_envelope_ratio": budget[
                            "cumulative_component_envelope_ratio"
                        ],
                        "simultaneous_peak_ratio": budget["simultaneous_peak_ratio"],
                        "cumulative_envelope_compression_ratio": budget[
                            "cumulative_envelope_compression_ratio"
                        ],
                        "local_subtotal_to_half_budget_ratio": budget[
                            "local_subtotal_to_half_budget_ratio"
                        ],
                        "modal_subtotal_to_half_budget_ratio": budget[
                            "modal_subtotal_to_half_budget_ratio"
                        ],
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixed-geometry-csv", type=Path, required=True)
    parser.add_argument("--adaptive-json", type=Path, required=True)
    parser.add_argument("--baseline-hybrid-json", type=Path)
    parser.add_argument("--p2-baseline-hybrid-json", type=Path)
    parser.add_argument("--p3-baseline-hybrid-json", type=Path)
    parser.add_argument("--p4-baseline-hybrid-json", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    scenario_paths = {
        key: path
        for key, path in {
            "p2_h3_current_layout_stress_test": args.p2_baseline_hybrid_json,
            "p3_h3_finer_discrete_stress_test": args.p3_baseline_hybrid_json,
            "p4_h5_best_available_stress_test": args.p4_baseline_hybrid_json,
        }.items()
        if path is not None
    }
    if not scenario_paths and args.baseline_hybrid_json is None:
        parser.error("provide --baseline-hybrid-json or one or more p2/p3/p4 baselines")
    model = build_resource_model(
        fixed_geometry_csv=args.fixed_geometry_csv,
        adaptive_json=args.adaptive_json,
        baseline_hybrid_json=args.baseline_hybrid_json,
        baseline_hybrid_jsons=scenario_paths or None,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_csv(model, args.csv_output)
    print(json.dumps(model["decision"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
