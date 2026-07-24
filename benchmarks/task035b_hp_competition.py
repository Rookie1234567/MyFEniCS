"""Build the Task035b measured sequential h-versus-p competition audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


_OBSERVABLES = ("R_total", "T_total", "A_volume_total")
_MESH_IDENTITY_KEYS = (
    "global_cell_count",
    "partition_independent_mesh_sha256",
    "cell_tag_sha256",
    "facet_tag_sha256",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_source(payload: dict[str, Any], label: str) -> str:
    source = payload.get("source") or {}
    commit = source.get("commit_sha")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or source.get("verified_clean_sha") != commit
        or source.get("head_after_sha") != commit
        or source.get("tracked_source_dirty") is not False
        or source.get("stable_and_clean_after") is not True
        or source.get("status_after_before_record_write") != ""
    ):
        raise ValueError(f"{label} lacks a stable clean-source attestation")
    return commit


def _matrix_resource(endpoint: dict[str, Any]) -> dict[str, Any]:
    matrix = endpoint.get("matrix_stats") or {}
    required = (
        "matrix_rows",
        "matrix_nnz_used",
        "matrix_average_nnz_per_row",
    )
    if any(key not in matrix for key in required):
        raise ValueError("competition endpoint lacks measured matrix resources")
    return {
        "dofs": int(endpoint["num_nedelec_dofs"]),
        "active_rows": int(matrix["matrix_rows"]),
        "matrix_nnz": int(matrix["matrix_nnz_used"]),
        "matrix_average_row_width": float(
            matrix["matrix_average_nnz_per_row"]
        ),
        "solve_elapsed_seconds": float(endpoint["elapsed_seconds"]),
        "factor_nnz": None,
        "peak_memory_gib": None,
    }


def _observable_error(
    endpoint: dict[str, Any],
    reference: dict[str, Any],
) -> tuple[float, float]:
    vector_error = math.sqrt(
        sum(
            (
                float(endpoint[name])
                - float(reference["observables"][name])
            )
            ** 2
            for name in _OBSERVABLES
        )
    )
    strict_r_error = abs(
        float(endpoint["R_total"])
        - float(reference["observables"]["R_total"])
    )
    return vector_error, strict_r_error


def _endpoint(
    name: str,
    endpoint: dict[str, Any],
    reference: dict[str, Any],
    control: dict[str, Any],
) -> dict[str, Any]:
    if (
        endpoint.get("official_result") is not True
        or endpoint.get("case_status") != "completed"
        or int(endpoint.get("mpi_size", -1)) != 8
        or endpoint.get("mesh_cell_type_actual") != "tetrahedron"
        or float(endpoint.get("linear_system_relative_residual", math.inf))
        > 1.0e-9
    ):
        raise ValueError(f"{name} endpoint fails the formal-solve gate")
    vector_error, strict_r_error = _observable_error(endpoint, reference)
    return {
        "name": name,
        "degree": int(endpoint["degree"]),
        "mesh_cells": int(endpoint["num_mesh_cells"]),
        "observables": {
            observable: float(endpoint[observable])
            for observable in _OBSERVABLES
        },
        "true_relative_residual": float(
            endpoint["linear_system_relative_residual"]
        ),
        "reference_errors": {
            "R_T_A_volume_l2": vector_error,
            "strict_R_total_absolute": strict_r_error,
        },
        "accuracy_control_ratios": {
            "R_T_A_volume_l2": vector_error
            / float(control["reference_observable_error_l2"]),
            "strict_R_total_absolute": strict_r_error
            / float(control["reference_r_total_absolute_error"]),
        },
        "resource": _matrix_resource(endpoint),
    }


def _action(
    name: str,
    origin: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    added = {
        "dofs": (
            result["resource"]["dofs"] - origin["resource"]["dofs"]
        ),
        "active_rows": (
            result["resource"]["active_rows"]
            - origin["resource"]["active_rows"]
        ),
        "matrix_nnz": (
            result["resource"]["matrix_nnz"]
            - origin["resource"]["matrix_nnz"]
        ),
    }
    if any(value <= 0 for value in added.values()):
        raise ValueError(f"{name} action does not add positive resources")

    benefits: dict[str, dict[str, float]] = {}
    for metric in ("R_T_A_volume_l2", "strict_R_total_absolute"):
        before = float(origin["reference_errors"][metric])
        after = float(result["reference_errors"][metric])
        if not 0.0 < after < before:
            raise ValueError(f"{name} action does not reduce {metric}")
        log10_gain = math.log10(before / after)
        benefits[metric] = {
            "absolute_error_reduction": before - after,
            "relative_error_reduction": 1.0 - after / before,
            "log10_error_gain": log10_gain,
            "log10_gain_per_1k_added_dofs": (
                log10_gain / (added["dofs"] / 1.0e3)
            ),
            "log10_gain_per_1k_added_rows": (
                log10_gain / (added["active_rows"] / 1.0e3)
            ),
            "log10_gain_per_1m_added_matrix_nnz": (
                log10_gain / (added["matrix_nnz"] / 1.0e6)
            ),
        }
    return {
        "name": name,
        "origin": origin["name"],
        "result": result["name"],
        "added_resource": added,
        "benefits": benefits,
        "action_peak_memory": {
            "status": "not_available_nonisolated",
            "value_gib": None,
        },
        "action_wall_time": {
            "status": "not_available_nonisolated",
            "value_seconds": None,
        },
        "factor_nnz": {
            "status": "not_available_in_source_records",
            "value": None,
        },
    }


def build_actual_hp_competition_record(
    dwr_payload: dict[str, Any],
    p_up_payload: dict[str, Any],
    *,
    dwr_source: dict[str, str] | None = None,
    p_up_source: dict[str, str] | None = None,
    generator_source_commit: str | None = None,
) -> dict[str, Any]:
    """Compare one actual local-h action and the following fixed-mesh p-up."""

    if dwr_payload.get("status") != "actual_dwr_adaptive_cycles_pass":
        raise ValueError("DWR local-h authority is not a passing record")
    if p_up_payload.get("status") != "actual_common_mesh_angle_sweep_pass":
        raise ValueError("fixed-mesh p-up authority is not a passing record")
    if (dwr_payload.get("qualification") or {}).get("pass") is not True:
        raise ValueError("DWR local-h qualification failed")
    if (p_up_payload.get("qualification") or {}).get("pass") is not True:
        raise ValueError("fixed-mesh p-up qualification failed")
    dwr_commit = _clean_source(dwr_payload, "DWR local-h authority")
    p_up_commit = _clean_source(p_up_payload, "fixed-mesh p-up authority")
    if (
        float(
            (dwr_payload.get("resource_authority") or {}).get(
                "max_process_tree_swap_mb",
                math.inf,
            )
        )
        != 0.0
        or float(
            (p_up_payload.get("resource_authority") or {}).get(
                "max_process_tree_swap_mb",
                math.inf,
            )
        )
        != 0.0
    ):
        raise ValueError("competition authorities must have zero swap")

    target_dwr = dwr_payload.get("target_identity") or {}
    target_p = p_up_payload.get("target_identity") or {}
    for key in ("wavelength_nm", "polarization", "geometry"):
        if target_dwr.get(key) != target_p.get(key):
            raise ValueError(f"competition target mismatch: {key}")
    if (
        float(target_dwr.get("grazing_angle_deg", math.nan)) != 10.0
        or list(target_p.get("grazing_angles_deg") or []) != [10.0]
    ):
        raise ValueError("competition records do not bind the 10 degree case")

    cycles = dwr_payload.get("cycles") or []
    refinements = dwr_payload.get("refinements") or []
    angles = p_up_payload.get("angle_results") or []
    if len(cycles) != 2 or len(refinements) != 1:
        raise ValueError("competition requires exactly one local-h refinement")
    if len(angles) != 1:
        raise ValueError("competition requires exactly one fixed-mesh p-up case")
    if (
        int(cycles[0].get("cycle_index", -1)) != 0
        or int(cycles[1].get("cycle_index", -1)) != 1
    ):
        raise ValueError("DWR cycle identity is not consecutive")

    refined_mesh = cycles[1].get("mesh_audit") or {}
    replay_mesh = p_up_payload.get("common_mesh_identity") or {}
    for key in _MESH_IDENTITY_KEYS:
        if refined_mesh.get(key) != replay_mesh.get(key):
            raise ValueError(f"refined/p-up mesh identity mismatch: {key}")
    if refinements[0].get("pass") is not True:
        raise ValueError("the single local-h refinement audit failed")

    base_raw = cycles[0].get("enriched") or {}
    h_raw = cycles[1].get("enriched") or {}
    p_origin_raw = angles[0].get("coarse") or {}
    p_raw = angles[0].get("enriched") or {}
    if (
        int(base_raw.get("degree", -1)) != 5
        or int(h_raw.get("degree", -1)) != 5
        or int(p_origin_raw.get("degree", -1)) != 5
        or int(p_raw.get("degree", -1)) != 6
    ):
        raise ValueError("competition endpoints must be p5, p5, p5, p6")

    p5_resource_keys = (
        ("num_nedelec_dofs", None),
        ("matrix_rows", "matrix_stats"),
        ("matrix_nnz_used", "matrix_stats"),
    )
    for key, parent in p5_resource_keys:
        left = h_raw[key] if parent is None else h_raw[parent][key]
        right = (
            p_origin_raw[key]
            if parent is None
            else p_origin_raw[parent][key]
        )
        if left != right:
            raise ValueError(f"fixed-mesh p5 origin mismatch: {key}")
    p5_observable_deltas = {
        name: abs(float(h_raw[name]) - float(p_origin_raw[name]))
        for name in _OBSERVABLES
    }
    if max(p5_observable_deltas.values()) > 1.0e-12:
        raise ValueError("fixed-mesh p5 observables do not reproduce local-h")

    reference = dwr_payload.get("fixed_observable_reference") or {}
    evaluation = p_up_payload.get("hp_budget_evaluation") or {}
    p_reference = evaluation.get("fixed_reference") or {}
    control = evaluation.get("accuracy_control") or {}
    if (
        reference.get("record_sha256") != p_reference.get("record_sha256")
        or reference.get("key") != p_reference.get("key")
        or control.get("record_sha256") != reference.get("record_sha256")
    ):
        raise ValueError("competition reference/control identity mismatch")
    if evaluation.get("thresholds_relaxed") is not False:
        raise ValueError("competition accuracy thresholds were relaxed")

    endpoints = {
        "B_base_p5": _endpoint(
            "B_base_p5",
            base_raw,
            reference,
            control,
        ),
        "H_one_local_h_p5": _endpoint(
            "H_one_local_h_p5",
            h_raw,
            reference,
            control,
        ),
        "P_fixed_mesh_p6": _endpoint(
            "P_fixed_mesh_p6",
            p_raw,
            reference,
            control,
        ),
    }
    expected_errors = (
        float(cycles[0]["enriched_fixed_reference_error_l2"]),
        float(cycles[1]["enriched_fixed_reference_error_l2"]),
        float(evaluation["candidate"]["reference_observable_error_l2"]),
    )
    actual_errors = tuple(
        endpoints[name]["reference_errors"]["R_T_A_volume_l2"]
        for name in endpoints
    )
    if any(
        abs(actual - expected) > 1.0e-12
        for actual, expected in zip(actual_errors, expected_errors, strict=True)
    ):
        raise ValueError("recomputed observable-vector errors do not close")

    h_action = _action(
        "one_local_h_at_p5",
        endpoints["B_base_p5"],
        endpoints["H_one_local_h_p5"],
    )
    p_action = _action(
        "fixed_mesh_global_p5_to_p6",
        endpoints["H_one_local_h_p5"],
        endpoints["P_fixed_mesh_p6"],
    )
    h_vector_efficiency = h_action["benefits"]["R_T_A_volume_l2"][
        "log10_gain_per_1k_added_dofs"
    ]
    p_vector_efficiency = p_action["benefits"]["R_T_A_volume_l2"][
        "log10_gain_per_1k_added_dofs"
    ]
    h_r_efficiency = h_action["benefits"]["strict_R_total_absolute"][
        "log10_gain_per_1k_added_dofs"
    ]
    p_r_efficiency = p_action["benefits"]["strict_R_total_absolute"][
        "log10_gain_per_1k_added_dofs"
    ]
    minimum_target = 90_000
    final = endpoints["P_fixed_mesh_p6"]
    return {
        "schema_version": "task035b.actual-h-vs-p-competition.v1",
        "status": "actual_sequential_h_vs_p_proxy_pass",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "scope": "comparable_sequential_global_marginal_proxy",
        "head_to_head_same_origin": False,
        "same_patch": False,
        "cell_decision_authority": False,
        "geometry": "Task034 fixed rectangular block grating",
        "target": {
            "wavelength_nm": 13.5,
            "grazing_angle_deg": 10.0,
            "polarization": "S",
            "mesh_backend": "audited periodic tetrahedron",
        },
        "source_records": {
            "one_local_h": dwr_source,
            "fixed_mesh_p_up": p_up_source,
        },
        "source_commits": {
            "one_local_h": dwr_commit,
            "fixed_mesh_p_up": p_up_commit,
            "generator": generator_source_commit,
        },
        "common_refined_mesh_identity": {
            key: refined_mesh[key] for key in _MESH_IDENTITY_KEYS
        },
        "fixed_reference": reference,
        "accuracy_control": control,
        "p5_replay_closure": {
            "pass": True,
            "resource_identity_exact": True,
            "observable_absolute_deltas": p5_observable_deltas,
            "observable_tolerance": 1.0e-12,
        },
        "endpoints": endpoints,
        "actions": {
            "one_local_h_at_p5": h_action,
            "fixed_mesh_global_p5_to_p6": p_action,
        },
        "cost_normalized_conclusion": {
            "single_winner": False,
            "R_T_A_volume_l2_dof_efficiency_preference": (
                "one_local_h_at_p5"
                if h_vector_efficiency > p_vector_efficiency
                else "fixed_mesh_global_p5_to_p6"
            ),
            "strict_R_total_dof_efficiency_preference": (
                "one_local_h_at_p5"
                if h_r_efficiency > p_r_efficiency
                else "fixed_mesh_global_p5_to_p6"
            ),
            "reason": (
                "the observable-vector and strict-R objectives prefer "
                "different sequential actions"
            ),
        },
        "engineering_gate": {
            "minimum_equivalent_dof_target": minimum_target,
            "final_dofs": final["resource"]["dofs"],
            "final_dof_target_pass": (
                final["resource"]["dofs"] <= minimum_target
            ),
            "final_vector_control_pass": (
                final["accuracy_control_ratios"]["R_T_A_volume_l2"] <= 1.0
            ),
            "final_strict_R_control_pass": (
                final["accuracy_control_ratios"][
                    "strict_R_total_absolute"
                ]
                <= 1.0
            ),
            "status": "controlled_negative",
        },
        "workflow_resource_context": {
            "one_local_h_record": {
                "wall_seconds": float(dwr_payload["elapsed_seconds"]),
                "peak_memory_gib": float(
                    dwr_payload["resource_authority"][
                        "memory_authority_gib"
                    ]
                ),
            },
            "fixed_mesh_p_up_record": {
                "wall_seconds": float(p_up_payload["elapsed_seconds"]),
                "peak_memory_gib": float(
                    p_up_payload["resource_authority"][
                        "memory_authority_gib"
                    ]
                ),
            },
            "semantics": (
                "whole-record workflow context only; not isolated action "
                "costs and therefore excluded from normalized scores"
            ),
        },
        "unavailable_accuracy_fields": [
            "R00",
            "A_closure",
            "significant_diffraction_orders",
            "complex_amplitudes",
            "selected_field_and_interface_errors",
        ],
        "limitations": [
            "the h and p actions are sequential, not head-to-head from one origin",
            "the evidence is global tetra routing, not a same-hexa-cell patch test",
            "time and memory cannot be isolated per action from the source records",
            "the record informs route selection but cannot authorize cellwise hp",
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dwr-record", type=Path, required=True)
    parser.add_argument("--p-up-record", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if (
        len(args.verified_clean_sha) != 40
        or any(
            character not in "0123456789abcdef"
            for character in args.verified_clean_sha.lower()
        )
    ):
        raise ValueError("--verified-clean-sha must be a full 40-hex commit")
    dwr_path = args.dwr_record.resolve()
    p_up_path = args.p_up_record.resolve()
    record = build_actual_hp_competition_record(
        json.loads(dwr_path.read_text(encoding="utf-8")),
        json.loads(p_up_path.read_text(encoding="utf-8")),
        dwr_source={"path": str(dwr_path), "sha256": _sha256(dwr_path)},
        p_up_source={"path": str(p_up_path), "sha256": _sha256(p_up_path)},
        generator_source_commit=args.verified_clean_sha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
