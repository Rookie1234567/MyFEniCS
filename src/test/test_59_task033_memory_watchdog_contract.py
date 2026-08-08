from __future__ import annotations

import json
import copy
import hashlib
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmarks.run_task033_memory_watchdog import (
    _case090_source_compatibility,
    _formal_shard_pass,
    _h5_stage_memory_summary,
    _parse_args,
    _task034_terminal_record_is_complete,
    _task034_terminal_worker_drain,
    _task037b_h5_numerical_pass,
    _task037b_v1_r1_numerical_pass,
    _task037b_v1_r2_numerical_pass,
    _task037b_v1_r3_numerical_pass,
    _task037b_v1_r4_numerical_pass,
    _task037b_v1_r5_numerical_pass,
    _task037b_v2_numerical_pass,
    _task037b_v2_resource_classification,
    _task037b_v3_numerical_pass,
    _task037b_v3_evaluate_record,
    _task037b_v3_resource_classification,
    _task037b_r5_resource_gate,
    _watchdog_source_after,
    _watchdog_source_before,
    _worker_command,
)
from benchmarks.watchdog_process_control import worker_process_group_popen_kwargs
from benchmarks.task033_watchdog_launch import (
    DEFAULT_RESOURCE_MATRIX,
    high_order_core_evidence_gate,
    hybrid_launch_gate,
)
from benchmarks.task033_case090_pde_core import attach_evidence_sha256
from benchmarks.task033_hybrid_funnel import build_hybrid_funnel


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "a" * 40


def _v1_raw_record() -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_negative_lowest_propagating_or_lossy",
    )
    probes = [
        {
            "name": name,
            "metadata": {"kind": "contract"},
            "source_digest": "a" * 64,
            "component_digest": "b" * 64,
            "action_relative_error": 1.0e-14,
            "component_repeat_relative_error": 1.0e-15,
            "finite": True,
            "pass": True,
        }
        for name in names
    ]
    side = {
        "h_condition_number": 2.0,
        "matrices": {},
        "operator_inventory": {},
        "probes": probes,
        "component_destroyed": True,
        "action_usable_after_component_destroy": True,
        "pass": True,
    }
    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r1-dtn-component-action.v1",
        "benchmark_id": "task037b_v1_dtn_component_action",
        "status": "task037b_v1_r1_pass_awaiting_r2",
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
        },
        "v1_telemetry": {
            "task037b_v1_gate": True,
            "formal_probe_count_per_side": 6,
            "sides": {"bottom": copy.deepcopy(side), "top": copy.deepcopy(side)},
        },
        "gates": {"r1_pass": True},
        "qualification": {
            "task037b_v1_gate": True,
            "r1_pass": True,
            "integration_pass": True,
        },
    }


def _v1_r2_raw_record() -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_positive_first_kind_evanescent",
        "modal_positive_highest_retained_index",
        "modal_negative_lowest_propagating_or_lossy",
        "modal_negative_first_kind_evanescent",
        "modal_negative_highest_retained_index",
    )

    def result() -> dict:
        return {
            "reason": 2,
            "iterations": 1,
            "reported_residual": 1.0e-12,
            "f_only_true_residual": 2.0e-12,
            "stationary_correction_residuals": {
                "1": 1.0e-1,
                "2": 1.0e-2,
                "4": 1.0e-3,
                "8": 1.0e-4,
            },
            "setup_seconds": 1.0,
            "solve_seconds": 2.0,
            "apply_seconds": 3.0,
            "operator_identity": "fine_action_F_only",
            "external_dtn_correction": "excluded",
            "explicit_true_residual_recomputed": True,
        }

    def side() -> dict:
        probes = []
        for name in names:
            probes.append(
                {
                    "name": name,
                    "first": result(),
                    "second": result(),
                    "repeat_reason_equal": True,
                    "repeat_iterations_equal": True,
                    "repeat_solution_relative_error": 1.0e-14,
                    "finite": True,
                    "pass": True,
                }
            )
        return {
            "operator_identity": "fine_action_F_only",
            "external_dtn_correction": "excluded",
            "probe_count": 11,
            "probes": probes,
            "pass": True,
        }

    def preconditioner_contract() -> dict:
        return {
            "configuration": {
                "coordinate_axis": 0,
                "num_slabs": 6,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "ilu_levels": 0,
                "factor_only": True,
                "one_apply_per_pc_apply": True,
                "two_step_action_operator": None,
                "outer_solver": "right_fgmres",
                "restart": 30,
                "max_it": 300,
                "rtol": 1.0e-10,
                "atol": 0.0,
                "true_residual_limit": 1.0e-8,
            },
            "smoother": {
                "subdomain_local_diagonal_shift": True,
                "factor_fingerprints": [
                    {"subdomain": index, "sha256": "a" * 64} for index in range(6)
                ],
            },
            "no_direct_fallback": True,
            "factor_count_before_destroy": 6,
            "factor_count_after_destroy": 0,
            "factors_released": True,
        }

    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r2-f-only-local-inverse.v1",
        "benchmark_id": "task037b_v1_r2_f_only_local_inverse",
        "status": "task037b_v1_r2_complete_awaiting_r3",
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "v1_r2_telemetry": {
            "task037b_v1_gate": True,
            "external_dtn_correction_excluded": True,
            "formal_probe_count_per_side": 11,
            "sides": {"bottom": side(), "top": side()},
            "preconditioner": {
                "bottom": preconditioner_contract(),
                "top": preconditioner_contract(),
            },
        },
        "gates": {
            "r2_record_complete": True,
            "r2_all_probe_records_complete": True,
            "r2_all_probes_finite": True,
            "r2_no_direct_fallback": True,
            "r2_factors_released": True,
            "r2_pass": True,
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r2_pass": True,
            "worker_numerical_pass": True,
            "integration_pass": True,
            "disposition": "pass_awaiting_r3",
        },
    }


def _v1_r3_raw_record(*, numerical_negative: bool = False) -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_positive_first_kind_evanescent",
        "modal_positive_highest_retained_index",
        "modal_negative_lowest_propagating_or_lossy",
        "modal_negative_first_kind_evanescent",
        "modal_negative_highest_retained_index",
    )
    residual = 2.0e-8 if numerical_negative else 1.0e-12

    def preconditioner(identity: str, correction: str) -> dict:
        return {
            "operator": {
                "matrix_type": "python",
                "identity": identity,
                "external_dtn_correction": correction,
            },
            "configuration": {
                "preconditioner_profile": "v1_whole_endcap_ilu0",
                "coordinate_axis": 0,
                "num_slabs": 1,
                "overlap_fraction": 0.0,
                "interpolation": "partition",
                "ilu_levels": 0,
                "factor_only": True,
                "one_apply_per_pc_apply": True,
                "two_step_action_operator": None,
                "outer_solver": "right_fgmres",
                "restart": 30,
                "max_it": 300,
                "rtol": 1.0e-10,
                "atol": 0.0,
                "true_residual_limit": 1.0e-8,
            },
            "rows": 8,
            "source_matrix_nnz": 16,
            "factor_nnz": 32,
            "factor_csr_payload_estimate_bytes": 128,
            "partition_audit": {"partition_weight_sum_error": 0.0},
            "owner_partition": {
                "owners": [0],
                "row_counts": [8],
                "intervals": [[0.0, 1.0]],
            },
            "shift": True,
            "factor_fingerprints": [{"subdomain": 0, "sha256": "b" * 64}],
            "no_direct_fallback": True,
            "borrowed_action_survives_after_release": True,
            "candidate_direct_factor_count": 0,
            "factor_count_before_destroy": 1,
            "factor_count_after_destroy": 0,
            "factors_released": True,
        }

    def probe(name: str) -> dict:
        return {
            "name": name,
            "reported_residual": residual,
            "true_relative_residual": residual,
            "setup_seconds": 1.0,
            "solve_seconds": 2.0,
            "apply_seconds": 3.0,
            "stationary_correction_residuals": {
                "1": 1.0e-1,
                "2": 1.0e-2,
                "4": 1.0e-3,
                "8": 1.0e-4,
            },
            "explicit_true_residual_recomputed": True,
            "finite": True,
            "pass": not numerical_negative,
            "reason": 2 if not numerical_negative else -3,
            "iterations": 1 if not numerical_negative else 300,
        }

    def case(identity: str, correction: str) -> dict:
        probes = [probe(name) for name in names]
        case_pass = not numerical_negative
        return {
            "operator_identity": identity,
            "external_dtn_correction": correction,
            "preconditioner": preconditioner(identity, correction),
            "probes": probes,
            "probe_count": 11,
            "max_true_relative_residual": residual,
            "all_probes_finite": True,
            "pass": case_pass,
        }

    sides = {
        "bottom": {
            "cases": {
                "R3-F": case("fine_action_F_only", "excluded"),
                "R3-A": case("complete_hybrid_action", "included"),
            },
            "pass": not numerical_negative,
        },
        "top": {
            "cases": {
                "R3-F": case("fine_action_F_only", "excluded"),
                "R3-A": case("complete_hybrid_action", "included"),
            },
            "pass": not numerical_negative,
        },
    }
    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r3-whole-endcap-ilu0.v1",
        "benchmark_id": "task037b_v1_r3_whole_endcap_ilu0",
        "status": "task037b_v1_r3_complete_awaiting_r4",
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "v1_r3_telemetry": {
            "task037b_v1_gate": True,
            "preconditioner_profile": "v1_whole_endcap_ilu0",
            "formal_probe_count_per_side": 11,
            "sides": sides,
            "r3_contract_pass": True,
            "r3_numerical_pass": not numerical_negative,
        },
        "gates": {
            "r3_record_complete": True,
            "r3_all_cases_complete": True,
            "r3_all_probes_finite": True,
            "r3_no_direct_fallback": True,
            "r3_factors_released": True,
            "r3_pass": not numerical_negative,
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r3_pass": not numerical_negative,
            "worker_numerical_pass": not numerical_negative,
            "integration_pass": True,
            "disposition": (
                "r3_numerical_pass_awaiting_r4"
                if not numerical_negative
                else "r3_numerical_negative_awaiting_r4"
            ),
        },
    }


def _v1_r4_raw_record() -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_positive_first_kind_evanescent",
        "modal_positive_highest_retained_index",
        "modal_negative_lowest_propagating_or_lossy",
        "modal_negative_first_kind_evanescent",
        "modal_negative_highest_retained_index",
    )

    def row(name: str, zero_physical_rhs: bool) -> dict:
        return {
            "name": name,
            "direct_true_residual": 1.0e-12,
            "woodbury_true_residual": 2.0e-12,
            "solution_relative_error": 3.0e-12,
            "repeat_error": 4.0e-13,
            "zero_physical_rhs": zero_physical_rhs,
            "zero_equation_pass": zero_physical_rhs,
            "capacity_pass": not zero_physical_rhs,
            "finite": True,
            "pass": True,
        }

    def side(side_name: str) -> dict:
        rows = [
            row(name, side_name == "bottom" and name == "physical") for name in names
        ]
        expected_capacity = 10 if side_name == "bottom" else 11
        components = {
            "F": {"type": "python", "shape": [8424, 8424]},
            "C": {"type": "python", "shape": [8424, 40]},
            "D": {"type": "python", "shape": [40, 8424]},
            "H": {"type": "python", "shape": [40, 40]},
        }
        return {
            "probe_count": 11,
            "rows": rows,
            "operator": {
                "identity": "borrowed_F_plus_Dtn_Woodbury",
                "base_identity": "exact_F_direct_test_only",
                "external_dtn_correction": "included",
                "n_aux": 40,
                "normal_equations": False,
                "components": components,
            },
            "woodbury": {
                "base_identity": "exact_F_direct_test_only",
                "n_aux": 40,
                "K_rank": 40,
                "K_shape": [40, 40],
                "K_dtype": "complex128",
                "K_condition_number": 2.0,
                "normal_equations": False,
                "W_local_nbytes_by_rank": [8424 * 40 * 16],
                "K_replicated_per_rank_nbytes": 40 * 40 * 16,
                "LU_replicated_per_rank_nbytes": 40 * 40 * 16,
            },
            "factor_release": {
                "a_factor": {
                    "factor_count_before": 1,
                    "factor_count_after": 0,
                    "released": True,
                },
                "f_factor": {
                    "factor_count_before": 1,
                    "factor_count_after": 0,
                    "released": True,
                },
                "never_simultaneous": True,
                "max_active_factor_count": 1,
                "final_active_factor_count": 0,
                "a_released_before_f_created": True,
                "explicit_reference_C_D_H_released_before_f_factor": True,
            },
            "action_survives_after_release": True,
            "all_probes_finite": True,
            "contract_pass": True,
            "nonzero_capacity_count": expected_capacity,
            "capacity_pass_count": expected_capacity,
            "capacity_expected_count": expected_capacity,
            "zero_physical_count": 1 if side_name == "bottom" else 0,
            "zero_equation_pass": True,
            "pass": True,
        }

    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r4-dtn-woodbury.v1",
        "benchmark_id": "task037b_v1_r4_dtn_woodbury_oracle",
        "status": "task037b_v1_r4_complete_awaiting_r5",
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
            "external_auxiliary_rows_in_krylov": 0,
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
            "external_diffraction_orders": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "v1_r4_telemetry": {
            "task037b_v1_gate": True,
            "n_aux": 40,
            "normal_equations": False,
            "formal_probe_count_per_side": 11,
            "r4_contract_pass": True,
            "r4_numerical_pass": True,
            "ordinary_default_changed": False,
            "sides": {"bottom": side("bottom"), "top": side("top")},
        },
        "gates": {
            "r4_record_complete": True,
            "r4_all_probe_records_complete": True,
            "r4_all_probes_finite": True,
            "r4_factor_noncoexistence": True,
            "r4_factors_released": True,
            "r4_no_direct_fallback": True,
            "r4_pass": True,
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r4_pass": True,
            "worker_numerical_pass": True,
            "integration_pass": True,
            "disposition": "r4_pass_awaiting_r5",
        },
    }


def _v1_r5_raw_record(
    *, numerical_negative: bool = False, negative_side: str = "both"
) -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_positive_first_kind_evanescent",
        "modal_positive_highest_retained_index",
        "modal_negative_lowest_propagating_or_lossy",
        "modal_negative_first_kind_evanescent",
        "modal_negative_highest_retained_index",
    )

    def metadata(name: str) -> dict:
        if name == "physical":
            return {"kind": "physical_action_rhs"}
        if name.startswith("random_seed_"):
            return {
                "kind": "partition_independent_complex_random",
                "seed": int(name.rsplit("_", 1)[1]),
            }
        direction = "positive" if "positive" in name else "negative"
        if "lowest" in name:
            criterion = "lowest_propagating_or_lossy"
            local_mode_index = 0
        elif "first_kind" in name:
            criterion = "first_kind_evanescent"
            local_mode_index = 1
        else:
            criterion = "highest_retained_index"
            local_mode_index = 119
        return {
            "kind": "frozen_modal_traction",
            "mode_identity": {
                "direction": direction,
                "criterion": criterion,
                "local_mode_index": local_mode_index,
            },
        }

    def row(name: str, side_name: str) -> dict:
        zero = side_name == "bottom" and name == "physical"
        side_negative = numerical_negative and negative_side in {"both", side_name}
        residual = 2.0e-7 if side_negative and name == "random_seed_3701" else 2.0e-12
        numeric = not side_negative or name != "random_seed_3701"
        first = {
            "reason": 2,
            "iterations": 1,
            "reported_residual": 1.0e-12,
            "complete_A_true_residual": residual,
            "setup_seconds": 1.0,
            "solve_seconds": 2.0,
            "apply_seconds": 3.0,
        }
        second = dict(first)
        return {
            "name": name,
            "metadata": metadata(name),
            "first": first,
            "second": second,
            "repeat_reason_equal": True,
            "repeat_iterations_equal": True,
            "repeat_solution_relative_error": 1.0e-13,
            "zero_physical_rhs": zero,
            "zero_equation_pass": numeric if zero else False,
            "capacity_pass": numeric if not zero else False,
            "finite": True,
            "pass": numeric,
        }

    def side(side_name: str) -> dict:
        rows = [row(name, side_name) for name in names]
        expected_capacity = 10 if side_name == "bottom" else 11
        capacity_pass_count = sum(
            row_item["capacity_pass"]
            for row_item in rows
            if not row_item["zero_physical_rhs"]
        )
        components = {
            "F": {"type": "python", "shape": [8424, 8424]},
            "C": {"type": "python", "shape": [8424, 40]},
            "D": {"type": "python", "shape": [40, 8424]},
            "H": {"type": "python", "shape": [40, 40]},
        }
        return {
            "probe_count": 11,
            "rows": rows,
            "operator": {
                "identity": "complete_hybrid_action_with_whole_endcap_dtn_woodbury",
                "base_identity": "whole_endcap_ilu0_smoother",
                "external_dtn_correction": "included",
                "matrix_type": "python",
                "matrix_free": True,
                "global_A_materialized": False,
                "direct_factor_count": 0,
                "components": components,
            },
            "configuration": {
                "preconditioner_profile": "v1_whole_endcap_ilu0",
                "num_subdomains": 1,
                "overlap_fraction": 0.0,
                "coordinate_axis": 0,
                "interpolation": "partition",
                "ilu_levels": 0,
                "factor_only": True,
                "one_apply_per_pc_apply": True,
                "two_step_action_operator": None,
                "outer_solver": "right_fgmres",
                "restart": 30,
                "max_it": 300,
                "rtol": 1.0e-10,
                "atol": 0.0,
                "true_residual_limit": 1.0e-8,
            },
            "base": {
                "identity": "whole_endcap_ilu0_smoother",
                "source_matrix_nnz": 1000,
                "factor_nnz": 2000,
                "factor_csr_payload_estimate_bytes": 32000,
            },
            "woodbury": {
                "base_identity": "whole_endcap_ilu0_smoother",
                "n_aux": 40,
                "K_rank": 40,
                "K_shape": [40, 40],
                "K_dtype": "complex128",
                "K_condition_number": 2.0,
                "normal_equations": False,
                "arrays_finite": True,
                "W_local_nbytes_by_rank": [8424 * 40 * 16],
                "K_replicated_per_rank_nbytes": 40 * 40 * 16,
                "LU_replicated_per_rank_nbytes": 40 * 40 * 16,
            },
            "pc_audit": {
                "linearity_error": 1.0e-13,
                "determinism_error": 1.0e-14,
                "finite": True,
            },
            "factor_release": {
                "factor_count_before": 1,
                "factor_count_after": 0,
                "factors_released": True,
                "woodbury_destroyed": True,
                "max_active_factor_count": 1,
                "never_simultaneous": True,
            },
            "action_survives_after_release": True,
            "no_direct_fallback": True,
            "all_probes_finite": True,
            "contract_pass": True,
            "algebra_legality_pass": True,
            "nonzero_capacity_count": expected_capacity,
            "capacity_expected_count": expected_capacity,
            "capacity_pass_count": capacity_pass_count,
            "zero_physical_count": 1 if side_name == "bottom" else 0,
            "zero_equation_pass": True,
            "pass": not (numerical_negative and negative_side in {"both", side_name}),
        }

    status = (
        "DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE"
        if numerical_negative
        else "task037b_v1_r5_complete_awaiting_h6"
    )
    numeric_pass = not numerical_negative
    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r5-dtn-woodbury-local-inverse.v1",
        "benchmark_id": "task037b_v1_r5_dtn_woodbury_local_inverse",
        "timestamp_utc": "2026-08-08T00:00:00+00:00",
        "status": status,
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
            "external_auxiliary_rows_in_krylov": 0,
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
            "external_diffraction_orders": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "v1_r5_telemetry": {
            "task037b_v1_gate": True,
            "ordinary_default_changed": False,
            "formal_probe_count_per_side": 11,
            "r5_contract_pass": True,
            "r5_algebra_legality_pass": True,
            "r5_numerical_pass": numeric_pass,
            "r5_borderline": numerical_negative,
            "severe_negative": False,
            "sides": {"bottom": side("bottom"), "top": side("top")},
        },
        "gates": {
            "r5_record_complete": True,
            "r5_all_probe_records_complete": True,
            "r5_all_probes_finite": True,
            "r5_pc_linearity": True,
            "r5_pc_determinism": True,
            "r5_factors_released": True,
            "r5_no_direct_fallback": True,
            "r5_factor_noncoexistence": True,
            "r5_algebra_legality_pass": True,
            "r5_pass": numeric_pass,
            "r5_factor_lifecycle": {
                "bottom_released_before_top_setup": True,
                "global_max_active_factor_count": 1,
                "global_final_active_factor_count": 0,
            },
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r5_pass": numeric_pass,
            "worker_numerical_pass": numeric_pass,
            "integration_pass": True,
            "disposition": (
                "r5_pass_awaiting_h6"
                if numeric_pass
                else "DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE"
            ),
        },
    }


def _funnel_shard(mode_count: int, delta: float) -> dict:
    return {
        "schema_version": 2,
        "benchmark_id": "task033_external_memory_watchdog",
        "status": "measured_shard_pass",
        "target": "hybrid",
        "return_code": 0,
        "command": ["mpiexec", "-n", "4", "python", "hybrid"],
        "requested_modes": mode_count,
        "candidate_modes": 2 * mode_count,
        "formal_pass": True,
        "numeric_pass": True,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "memory_authority_pass": True,
        "resource_authority": {"gate": {"pass": True}},
        "source_gate": {"pass": True},
        "launch_gate": {"pass": True},
        "source": {
            "commit_sha": SOURCE_SHA,
            "verified_clean_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "source_clean_verified": True,
        },
        "measurements": {
            "case": {
                "degree": 1,
                "h_nm": 5.0,
                "wavelength_nm": 13.5,
                "incident_grazing_deg": 10.0,
                "polarization_kind": "s",
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "graded_reference_h_nm": None,
                "graded_plan_hash": None,
                "requested_modes_per_direction": mode_count,
            },
            "hybrid_system": {"primary_solver_path": "modal-schur-memory-minimal"},
            "solve": {"true_relative_residual": 1.0e-12},
            "port_power": {
                "R_total": 0.1 + delta,
                "T_total": 0.7 - delta,
                "A_balance": 0.2,
            },
            "external_diffraction_orders": [
                {
                    "side": "top",
                    "m": 0,
                    "n": 0,
                    "polarization": "s",
                    "propagating": True,
                    "outgoing_amplitude_at_boundary": [
                        0.4 + delta,
                        -0.2,
                    ],
                    "power_ratio": 0.2 + delta,
                }
            ],
            "gates": {
                "monolithic_true_relative_residual_le_1e-9": True,
                "sampled_interface_e_t_relative_l2_le_5e-3": True,
                "sampled_interface_h_t_relative_l2_le_1e-2": True,
            },
            "qualification": {
                "integration_pass": True,
                "algebraic_chain_pass": True,
                "physical_field_gates_pass": True,
                "task033_physical_truncation_allowed": True,
            },
        },
    }


def _m160_nonconvergence_evidence() -> dict:
    descriptors = [
        {
            "path": f"m{mode}.json",
            "sha256": str(mode // 40) * 64,
            "mode_count_per_direction": mode,
            "source_commit_full_sha": SOURCE_SHA,
            "data_identity": "measured_external_watchdog_summary",
        }
        for mode in (80, 120, 160)
    ]
    return build_hybrid_funnel(
        [
            _funnel_shard(80, 3.0e-3),
            _funnel_shard(120, 2.0e-3),
            _funnel_shard(160, 1.0e-3),
        ],
        source_descriptors=descriptors,
    )


def _v2_raw_record(
    *, profile: str = "bottom-approx", negative: bool = False, max_it: int = 20
) -> dict:
    expected = {
        "bottom-approx": {"bottom": (0, 1), "top": (1, 0)},
        "top-approx": {"bottom": (1, 0), "top": (0, 1)},
        "double": {"bottom": (0, 1), "top": (0, 1)},
    }[profile]
    if max_it == 20:
        iterations = [0, 5, 10, 15, 20]
        residuals = [0.8, 0.6, 0.45, 0.3, 0.2 if not negative else 0.4]
    elif max_it == 100:
        iterations = [0, 25, 50, 75, 100]
        residuals = [0.8, 0.5, 0.3, 0.16, 0.1]
    else:
        iterations = [0, 50, 100, 150, 200]
        residuals = [0.8, 0.2, 0.05, 0.01, 0.001]
    approximate = (
        {"bottom"}
        if profile == "bottom-approx"
        else {"top"}
        if profile == "top-approx"
        else {"bottom", "top"}
    )
    one_apply_diagnostic_sides = (
        {"bottom"}
        if profile == "bottom-approx"
        else {"top"}
        if profile == "top-approx"
        else set()
    )

    def certificate() -> dict:
        return {
            "pass": True,
            "wrapper_vs_internal_woodbury_error": 1.0e-14,
            "linearity_error": 1.0e-13,
            "determinism_error": 1.0e-15,
            "repeat_hash_equal": True,
            "apply_count_before": 0,
            "apply_count_after": 7,
            "apply_count_increment": 7,
            "base_factor_count": 1,
            "local_direct_factor_count": 0,
            "nested_ksp_created": False,
            "woodbury": {
                "K_rank": 40,
                "K_condition_number": 2.0,
                "arrays_finite": True,
            },
        }

    def release_record(name: str) -> dict:
        if name in approximate:
            return {
                "woodbury": {
                    "before": {"destroyed": False},
                    "after": {"destroyed": True},
                },
                "fixed_base": {
                    "before": {"destroyed": False},
                    "after": {"destroyed": True},
                },
                "components": {"destroyed": True},
                "release_pass": True,
            }
        return {
            "direct_action": {
                "before": {"destroyed": False},
                "after": {"destroyed": True},
            },
            "oracle": {"destroyed": True},
            "release_pass": True,
        }

    def side(name: str) -> dict:
        direct, ilu = expected[name]
        row_list = []
        side_release = release_record(name)
        side_record = {
            "factor_identity": {
                "direct_factor_count": direct,
                "ilu_factor_count": ilu,
                "borrowed_local_factor_count": direct + ilu,
                "expected_direct_factor_count": direct,
                "expected_ilu_factor_count": ilu,
                "pass": True,
            },
            "online_apply": {
                "before": 0,
                "after": 2,
                "increment": 2,
                "expected_increment": 2,
                "pass": True,
            },
            "release_records": side_release,
            "release_pass": True,
            "borrowed_action_survives_after_screen": True,
        }
        if name in one_apply_diagnostic_sides:
            count = 10 if name == "bottom" else 11
            side_record["one_apply_diagnostic"] = {
                "status": "pass",
                "expected_nonzero_rhs_count": count,
            }
            row_list = [
                {
                    "apply_count_before": index,
                    "apply_count_after": index + 1,
                    "apply_count_increment": 1,
                    "finite": True,
                    "rho": 0.1,
                }
                for index in range(count)
            ]
        elif profile == "double":
            side_record["one_apply_diagnostic"] = {
                "status": "not_run_here",
                "authority": "one-sided B/T required",
            }
        if name in one_apply_diagnostic_sides:
            side_record["rho_records"] = row_list
        return side_record

    sides = {"bottom": side("bottom"), "top": side("top")}
    factor_identity = {
        name: sides[name]["factor_identity"] for name in ("bottom", "top")
    }
    release_records = {
        "bottom": sides["bottom"]["release_records"],
        "top": sides["top"]["release_records"],
        "outer": {
            "outer_rhs_destroy_call_completed": True,
            "action_matrix_destroy_call_completed": True,
            "action_context_destroyed": True,
            "destroy_calls_complete": True,
        },
    }
    history = []
    for position, (index, value) in enumerate(zip(iterations, residuals)):
        is_final = position == len(iterations) - 1
        history.append(
            {
                "iteration": index,
                "elapsed_seconds": float(index + 1),
                "reported_relative_residual": value,
                "global_true_relative_residual": value,
                "bottom_true_relative_residual": value,
                "top_true_relative_residual": value,
                "modal_true_relative_residual": value,
                "pc_apply_count": 1 if is_final else 0,
                "bottom_action_apply_count": 2 if is_final else 0,
                "top_action_apply_count": 2 if is_final else 0,
            }
        )
    contract = True
    numeric = not negative
    telemetry = {
        "task037b_v2_gate": True,
        "profile": profile,
        "max_it": max_it,
        "ordinary_default_changed": False,
        "sides": sides,
        "fixed_callback_certificates": {
            "bottom": certificate() if "bottom" in approximate else None,
            "top": certificate() if "top" in approximate else None,
        },
        "modal_schur": {
            "shape": [240, 240],
            "rank": 240,
            "finite": True,
            "condition": 2.0,
            "matrix_repeat_error": 1.0e-14,
            "lu_repeat_solve_error": 1.0e-14,
            "build_apply_count": {"bottom": 480, "top": 480},
        },
        "modal_schur_contract_pass": True,
        "factor_identity": factor_identity,
        "factor_identity_pass": True,
        "global_operator_inventory": {
            "global_A_materialized": False,
            "matrix_free": True,
            "p6_direct_factor_count": 0,
        },
        "global_operator_contract": True,
        "pc_setup_inventory": {
            "global_A_materialized": False,
            "borrowed_local_factor_count": 2,
            "pc_owned_local_factor_count": 0,
            "bottom_direct_factor_count": expected["bottom"][0],
            "bottom_ilu_factor_count": expected["bottom"][1],
            "top_direct_factor_count": expected["top"][0],
            "top_ilu_factor_count": expected["top"][1],
        },
        "pc_inventory_pass": True,
        "online_apply_counts": {
            "bottom": sides["bottom"]["online_apply"],
            "top": sides["top"]["online_apply"],
        },
        "release_records": release_records,
        "release_pass": True,
    }
    validation = {
        "official_record": False,
        "R": "not_run",
        "T": "not_run",
        "A": "not_run",
        "A_volume": "not_run",
        "orders": "not_run",
        "external_diffraction_orders": "not_run",
        "field": "not_run",
        "12_plus_12": "not_run",
        "Full3D": "not_run",
        "full3d_comparison": "not_run",
    }
    return {
        "schema_version": 1,
        "record_schema": "task037b.v2-block-pc-screen.v1",
        "timestamp_utc": "2026-08-08T00:00:00+00:00",
        "benchmark_id": "task037b_v2_bounded_block_pc_screen",
        "official_record": False,
        "case": {
            "degree": 6,
            "h_nm": 10.0,
            "modal_degree": 6,
            "modal_h_nm": 10.0,
            "requested_modes": 120,
            "candidate_modes": 240,
            "mpi_size": 8,
            "solver_path": "block-ldu-action-screen",
            "polarization_kind": "s",
            "incident_grazing_deg": 10.0,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "v2_profile": profile,
            "v2_max_it": max_it,
        },
        "hybrid_system": {
            "global_A_materialized": False,
            "global_direct_factor_count": 0,
        },
        "screen": {
            "profile": profile,
            "max_it": max_it,
            "restart": 90,
            "rtol": 1.0e-6,
            "atol": 0.0,
            "zero_initial": True,
            "converged_reason": 2 if not negative else -3,
            "iterations": max_it,
            "history": history,
            "inventory_before_release": {
                "pc_apply_count": 1,
                "bottom_action_apply_count": 2,
                "top_action_apply_count": 2,
            },
        },
        "v2_telemetry": telemetry,
        "validation": validation,
        "physical_field_reconstruction": {"status": "not_run"},
        "gates": {
            "v2_fixed_callback_certificate": True,
            "v2_modal_schur": True,
            "v2_online_apply_counts": True,
            "v2_factor_identity": True,
            "v2_global_operator": True,
            "v2_pc_inventory": True,
            "v2_release": True,
            "v2_screen": numeric,
            "v2_integration_pass": contract,
            "v2_worker_numerical_pass": numeric,
        },
        "qualification": {
            "task037b_v2_gate": True,
            "profile": profile,
            "max_it": max_it,
            "official_record": False,
            "integration_pass": contract,
            "worker_numerical_pass": numeric,
            "disposition": "screen_pass" if numeric else "screen_numerical_negative",
        },
        "status": (
            "task037b_v2_screen_pass"
            if numeric
            else "task037b_v2_screen_numerical_negative"
        ),
    }


def _v3_raw_record(kind: str = "pass") -> dict:
    record = _v2_raw_record(profile="double", max_it=200)
    record["record_schema"] = "task037b.v3-progressive-block-pc-screen.v1"
    record["benchmark_id"] = "task037b_v3_progressive_block_pc_screen"
    record["status"] = "task037b_v3_pass"
    record["case"].pop("v2_profile", None)
    record["case"].pop("v2_max_it", None)
    record["case"]["v3_gate"] = True
    record["case"].update(
        {
            "wavelength_nm": 13.5,
            "internal_propagation_model": "full3d_uniform_cg",
            "internal_traction_model": "scalar_cg_discrete_derivative",
            "stage4_full3d_assembly_backend": "assembly_time_static_condensed",
        }
    )
    record["hybrid_system"]["operator_inventory"] = {
        "global_A_materialized": False,
        "matrix_free": True,
        "p6_direct_factor_count": 0,
    }
    record["screen"]["profile"] = "double"
    record["screen"]["max_it"] = 200
    record["screen"]["converged_reason"] = -3
    telemetry = record.pop("v2_telemetry")
    telemetry["task037b_v2_gate"] = False
    telemetry["task037b_v3_gate"] = True
    telemetry["profile"] = "double"
    telemetry["max_it"] = 200
    telemetry["v3_release"] = True
    telemetry["stage_markers"] = [
        "action_coupling_build_started",
        "action_coupling_build_ready",
        "bottom_approx_setup_started",
        "bottom_approx_setup_ready",
        "top_approx_setup_started",
        "top_approx_setup_ready",
        "modal_schur_build_started",
        "modal_schur_build_ready",
        "release_started",
        "release_finished",
    ]
    telemetry["modal_schur"].update({"dtype": "complex128", "normal_equations": False})
    telemetry["prediction"] = {
        "interval": [120, 200],
        "sample_count": 81,
    }
    telemetry["official_outputs"] = {
        key: "not_run"
        for key in (
            "R",
            "T",
            "A",
            "A_volume",
            "orders",
            "field",
            "12_plus_12",
            "Full3D",
        )
    }
    for side in ("bottom", "top"):
        telemetry["sides"][side]["object_ledger"] = {
            "inventory": {
                "fine_global_A_materialized": False,
                "explicit_external_c_matrix_count": 0,
                "explicit_external_d_matrix_count": 0,
            }
        }
    record["validation"]["official_outputs"] = dict(telemetry["official_outputs"])
    record["screen"]["outer_solver"] = "fgmres"
    record["screen"]["pc_side"] = "right"
    for certificate in telemetry["fixed_callback_certificates"].values():
        if certificate is not None:
            certificate["pass"] = True
    history = []
    if kind == "early":
        iterations = list(range(11))
    elif kind == "negative":
        iterations = list(range(21))
    else:
        iterations = list(range(201))
    for iteration in iterations:
        if kind == "slow":
            if iteration <= 100:
                value = 0.8 * math.exp(-0.021 * iteration)
            elif iteration <= 160:
                value = (
                    0.8 * math.exp(-0.021 * 100) * math.exp(-0.001 * (iteration - 100))
                )
            else:
                value = 0.09 * math.exp(-0.0052 * (iteration - 160))
        elif kind == "negative":
            value = 0.8 * math.exp(-0.021 * iteration)
            if iteration >= 20:
                value = 0.7
        else:
            value = 0.8 * math.exp(-0.021 * iteration)
        if kind == "early" and iteration == 10:
            value = 1.0e-7
        history.append(
            {
                "iteration": iteration,
                "elapsed_seconds": float(iteration + 1),
                "reported_relative_residual": value,
                "global_true_relative_residual": value,
                "bottom_true_relative_residual": value,
                "top_true_relative_residual": value,
                "modal_true_relative_residual": value,
                "pc_apply_count": 1 if iteration == iterations[-1] else 0,
                "bottom_action_apply_count": 2 if iteration == iterations[-1] else 0,
                "top_action_apply_count": 2 if iteration == iterations[-1] else 0,
            }
        )
    record["screen"]["history"] = history
    telemetry["stage_markers"] = [
        *telemetry["stage_markers"][:8],
        *[
            f"outer_iter_{checkpoint}"
            for checkpoint in (20, 60, 100, 200)
            if iterations[-1] >= checkpoint
        ],
        "release_started",
        "release_finished",
    ]
    record["screen"]["iterations"] = iterations[-1]
    record["screen"]["converged_reason"] = (
        2 if kind == "early" else (-4 if kind == "negative" else -3)
    )
    record["screen"]["gate"] = {
        "stage": iterations[-1] if iterations[-1] in {20, 60, 100, 200} else None,
        "not_reached_due_to_convergence": (
            [20, 30, 40, 60, 80, 90, 100, 120, 150, 160, 180, 200]
            if kind == "early"
            else []
        ),
        "pass": kind == "pass",
    }
    if iterations[-1] == 200:
        xs = list(range(120, 201))
        ys = [
            math.log(max(row["global_true_relative_residual"], 1.0e-300))
            for row in history
            if 120 <= row["iteration"] <= 200
        ]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
        intercept = y_mean - slope * x_mean
        predicted = max(
            200,
            math.ceil((math.log(1.0e-6) - intercept) / slope),
        )
        record["screen"]["gate"].update(
            {
                "prediction_interval": [120, 200],
                "prediction_sample_count": 81,
                "prediction_slope": slope,
                "prediction_intercept": intercept,
                "prediction_q_fit": math.exp(slope),
                "predicted_iterations": predicted,
            }
        )
    if kind == "early":
        record["screen"]["progressive_stop_cause"] = None
    elif kind == "negative":
        record["screen"]["progressive_stop_cause"] = "v3_20_admission_failed"
    else:
        record["screen"]["progressive_stop_cause"] = None
    telemetry["sides"]["bottom"]["release_records"] = telemetry["release_records"][
        "bottom"
    ]
    telemetry["sides"]["top"]["release_records"] = telemetry["release_records"]["top"]
    telemetry["factor_identity_pass"] = True
    telemetry["modal_schur_contract_pass"] = True
    telemetry["pc_inventory_pass"] = True
    telemetry["global_operator_contract"] = True
    telemetry["release_pass"] = True
    record["v3_telemetry"] = telemetry
    record["gates"] = {
        "v3_fixed_callback_certificate": True,
        "v3_modal_schur": True,
        "v3_online_apply_counts": True,
        "v3_factor_identity": True,
        "v3_global_operator": True,
        "v3_pc_inventory": True,
        "v3_release": True,
        "v3_integration_pass": True,
        "v3_worker_numerical_pass": kind in {"pass", "early"},
        "v3_screen": kind in {"pass", "early"},
    }
    qualification = record["qualification"]
    qualification.pop("task037b_v2_gate", None)
    qualification["task037b_v3_gate"] = True
    qualification["profile"] = "double"
    qualification["max_it"] = 200
    qualification["integration_pass"] = True
    qualification["worker_numerical_pass"] = kind in {"pass", "early"}
    numeric = kind in {"pass", "early"}
    qualification["disposition"] = (
        "DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW"
        if numeric
        else "DOUBLE_APPROXIMATE_SLOW_CONTRACTION_AWAITING_REVIEW"
        if kind == "slow"
        else "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE"
    )
    record["status"] = (
        "task037b_v3_pass"
        if numeric
        else "task037b_v3_slow"
        if kind == "slow"
        else "task037b_v3_family_negative"
    )
    if kind == "implementation":
        telemetry["modal_schur"]["condition"] = 1.0e7
        qualification["integration_pass"] = False
        qualification["worker_numerical_pass"] = False
        qualification["disposition"] = "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
        record["status"] = "task037b_v3_implementation_gate_failed"
    return record


class Task033MemoryWatchdogContractTests(unittest.TestCase):
    def test_high_order_core_uses_canonical_evidence_not_file_sha(self) -> None:
        evidence = attach_evidence_sha256(
            {
                "record_type": "high_order_floquet_core_gate_result",
                "all_core_gates_passed": True,
                "identity": {
                    "is_pde_run": True,
                    "is_solver_pass": True,
                    "tracked_source_dirty": False,
                    "source_commit_full_sha": SOURCE_SHA,
                },
                "coverage": [
                    {"degree": degree, "mpi_size": mpi_size}
                    for degree in (3, 4)
                    for mpi_size in (1, 2, 4)
                ],
            }
        )
        canonical_sha = evidence["evidence_sha256"]
        accepted = high_order_core_evidence_gate(
            3,
            evidence,
            expected_sha256=canonical_sha,
            current_source_sha=SOURCE_SHA,
        )
        self.assertTrue(accepted["pass"], accepted["failures"])

        rendered_file_sha = hashlib.sha256(
            (json.dumps(evidence, indent=2) + "\n").encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(rendered_file_sha, canonical_sha)
        rejected = high_order_core_evidence_gate(
            3,
            evidence,
            expected_sha256=rendered_file_sha,
            current_source_sha=SOURCE_SHA,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn("expected_sha256_matches", rejected["failures"])

    def test_high_order_core_accepts_only_audited_non_numerical_descendant(
        self,
    ) -> None:
        current_sha = "b" * 40
        evidence = attach_evidence_sha256(
            {
                "record_type": "high_order_floquet_core_gate_result",
                "all_core_gates_passed": True,
                "identity": {
                    "is_pde_run": True,
                    "is_solver_pass": True,
                    "tracked_source_dirty": False,
                    "source_commit_full_sha": SOURCE_SHA,
                },
                "coverage": [
                    {"degree": degree, "mpi_size": mpi_size}
                    for degree in (3, 4)
                    for mpi_size in (1, 2, 4)
                ],
            }
        )
        compatibility = {
            "pass": True,
            "evidence_source_sha": SOURCE_SHA,
            "current_source_sha": current_sha,
            "numerical_source_unchanged": True,
            "changed_paths": ["benchmarks/task033_qep_qualification.py"],
            "disallowed_changed_paths": [],
            "failures": [],
        }
        accepted = high_order_core_evidence_gate(
            4,
            evidence,
            expected_sha256=evidence["evidence_sha256"],
            current_source_sha=current_sha,
            source_compatibility=compatibility,
        )
        self.assertTrue(accepted["pass"], accepted["failures"])
        self.assertEqual(
            accepted["source_reuse_kind"],
            "audited_non_numerical_descendant",
        )

        forged = {**compatibility, "current_source_sha": "c" * 40}
        rejected = high_order_core_evidence_gate(
            4,
            evidence,
            expected_sha256=evidence["evidence_sha256"],
            current_source_sha=current_sha,
            source_compatibility=forged,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "same_full_source_sha_or_audited_non_numerical_descendant",
            rejected["failures"],
        )

    def test_case090_source_compatibility_is_component_scoped(self) -> None:
        evidence = {"identity": {"source_commit_full_sha": SOURCE_SHA}}
        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=(
                SOURCE_SHA,
                "docs/README.md\n"
                "src/test/test_x.py\n"
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
                "records/p4_h5_e0_prediction.json\n"
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
                "expected.json\n"
                "benchmarks/run_task034_wsl_qualification.py\n"
                "benchmarks/task034_p3_h3_reranking.py\n"
                "src/coupling/modal_trace_projection.py\n"
                "src/modes/mode_classification.py\n"
                "benchmarks/task034_numerical_blob_checker.py\n"
                "benchmarks/task034_mpi_identity.py\n"
                "src/common/distributed_matrix_diagnostics.py\n"
                "src/solvers/hybrid_fem_modal_schur_direct.py\n"
                "benchmarks/task033_phaseC.py",
            ),
        ):
            accepted = _case090_source_compatibility(
                evidence, current_source_sha="b" * 40
            )
        self.assertTrue(accepted["pass"], accepted["failures"])
        self.assertTrue(accepted["case090_core_source_unchanged"])
        self.assertEqual(
            accepted["component_disjoint_numerical_changed_paths"],
            [
                "src/coupling/modal_trace_projection.py",
                "src/modes/mode_classification.py",
                "benchmarks/task034_mpi_identity.py",
                "src/common/distributed_matrix_diagnostics.py",
                "src/solvers/hybrid_fem_modal_schur_direct.py",
            ],
        )
        self.assertEqual(
            accepted["compatibility_scope"],
            "case090_pure3d_floquet_core",
        )

        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=(SOURCE_SHA, "benchmarks/run_task033_qep_matrix.py"),
        ):
            rejected = _case090_source_compatibility(
                evidence, current_source_sha="b" * 40
            )
        self.assertFalse(rejected["pass"])
        self.assertEqual(
            rejected["disallowed_changed_paths"],
            ["benchmarks/run_task033_qep_matrix.py"],
        )

    def test_source_preflight_rejects_nonignored_untracked_before_and_after(
        self,
    ) -> None:
        sha = "a" * 40

        def dirty_git(*args: str) -> str:
            if args[:2] == ("rev-parse", "HEAD"):
                return sha
            self.assertEqual(
                args,
                ("status", "--short", "--untracked-files=all"),
            )
            return "?? uncommitted_solver.py"

        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=dirty_git,
        ):
            source = _watchdog_source_before(sha)
        self.assertFalse(source["source_clean_verified"])
        self.assertEqual(
            source["nonignored_untracked_before"], ["uncommitted_solver.py"]
        )

        clean_source = {
            **source,
            "tracked_status_before": "",
            "worktree_status_before": "",
            "nonignored_untracked_before": [],
            "source_clean_verified": True,
        }
        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=dirty_git,
        ):
            after = _watchdog_source_after(clean_source)
        self.assertFalse(after["source_stable_during_run"])
        self.assertFalse(after["source_clean_verified"])
        self.assertEqual(after["nonignored_untracked_after"], ["uncommitted_solver.py"])

    def test_task032_anchor_default_reuse_and_explicit_same_sha_requalification(
        self,
    ) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        common = {
            "degree": 2,
            "h_nm": 3.0,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 16 * 1024**3,
            "warning_gib": 11.5,
            "terminate_gib": 13.0,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": "b" * 40,
        }
        default = hybrid_launch_gate(
            matrix, requested_modes=80, candidate_modes=160, **common
        )
        self.assertFalse(default["pass"])
        self.assertIn(
            "existing_uniform_anchor_not_relaunched_without_variant",
            default["failures"],
        )
        for requested_modes in (80, 120, 160):
            with self.subTest(requested_modes=requested_modes):
                gate = hybrid_launch_gate(
                    matrix,
                    requested_modes=requested_modes,
                    candidate_modes=2 * requested_modes,
                    task033_same_sha_anchor_requalification=True,
                    source_clean_verified=True,
                    resource_matrix_is_canonical=True,
                    resource_matrix_is_tracked=True,
                    external_watchdog_active=True,
                    **common,
                )
                self.assertTrue(gate["pass"], gate["failures"])
                requalification = gate["task033_anchor_requalification"]
                self.assertTrue(requalification["allowed"])
                self.assertEqual(
                    requalification["reason"],
                    "Task033 same-SHA formal requalification",
                )
                self.assertEqual(
                    requalification["required_complete_mode_funnel"],
                    [80, 120, 160],
                )
                self.assertTrue(requalification["does_not_replace_task032_anchor"])

        denied = hybrid_launch_gate(
            matrix,
            requested_modes=80,
            candidate_modes=160,
            task033_same_sha_anchor_requalification=True,
            source_clean_verified=False,
            resource_matrix_is_canonical=True,
            resource_matrix_is_tracked=True,
            external_watchdog_active=True,
            **common,
        )
        self.assertFalse(denied["pass"])
        self.assertIn(
            "task033_anchor_requalification_request_is_scoped", denied["failures"]
        )

    def test_qep_command_carries_every_formal_runtime_attestation(self) -> None:
        args = _parse_args(
            [
                "--target",
                "qep",
                "--case-label",
                "qep_air_p3_h5",
                "--degree",
                "3",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--material-kind",
                "air",
                "--verified-clean-sha",
                "a" * 40,
                "--high-order-core-evidence-sha256",
                "b" * 64,
            ]
        )
        args._qep_effective_limit_gib = 9.25
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        rendered = " ".join(command)
        self.assertIn("benchmarks.run_task033_qep_matrix", rendered)
        self.assertIn("--no-swap-verified", command)
        self.assertIn("--watchdog-enabled-verified", command)
        self.assertIn("--one-large-case-verified", command)
        self.assertIn("--left-candidate-modes", command)
        self.assertEqual(command[command.index("--left-candidate-modes") + 1], "16")
        self.assertIn("b" * 64, command)
        self.assertIn("--container-limit-gib", command)
        self.assertIn("9.25", command)

    def test_hybrid_command_propagates_explicit_axial_model_only(self) -> None:
        base = [
            "--target",
            "hybrid",
            "--case-label",
            "task035c_p2_h5",
            "--degree",
            "2",
            "--h-nm",
            "5",
            "--mpi-size",
            "1",
            "--requested-modes",
            "160",
            "--candidate-modes",
            "320",
            "--verified-clean-sha",
            "a" * 40,
        ]
        ordinary = _parse_args(base)
        corrected = _parse_args(
            [
                *base,
                "--internal-propagation-model",
                "full3d_uniform_cg",
                "--internal-traction-model",
                "scalar_cg_discrete_derivative",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ordinary_command = _worker_command(
                ordinary, root / "ordinary.json", root / "ordinary.jsonl"
            )
            corrected_command = _worker_command(
                corrected, root / "corrected.json", root / "corrected.jsonl"
            )
        self.assertNotIn("--internal-propagation-model", ordinary_command)
        self.assertEqual(
            corrected_command[
                corrected_command.index("--internal-propagation-model") + 1
            ],
            "full3d_uniform_cg",
        )
        self.assertEqual(
            corrected_command[corrected_command.index("--internal-traction-model") + 1],
            "scalar_cg_discrete_derivative",
        )

    def test_h4_gate_forwards_only_bounded_modal_diagnostic(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "task037b_h4",
                "--degree",
                "6",
                "--h-nm",
                "10",
                "--modal-degree",
                "6",
                "--modal-h-nm",
                "10",
                "--mpi-size",
                "8",
                "--requested-modes",
                "120",
                "--candidate-modes",
                "240",
                "--solver-path",
                "block-ldu-exact",
                "--stage4-full3d-assembly-backend",
                "assembly_time_static_condensed",
                "--bottom-interface-nm",
                "10",
                "--top-interface-nm",
                "110",
                "--incident-grazing-deg",
                "10",
                "--polarization-kind",
                "s",
                "--internal-propagation-model",
                "full3d_uniform_cg",
                "--internal-traction-model",
                "scalar_cg_discrete_derivative",
                "--full3d-reference",
                "reference.json",
                "--full3d-reference-sha256",
                "b" * 64,
                "--task037b-h4-gate",
                "--task035c-p6-preflight-authority",
                "authority.json",
                "--task035c-p6-preflight-sha256",
                "a" * 64,
                "--verified-clean-sha",
                SOURCE_SHA,
                "--host-environment-id",
                "WSL2-Ubuntu-24.04",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        self.assertIn("--task037b-h4-gate", command)
        self.assertNotIn("--task037b-h3-gate", command)
        self.assertNotIn("--task037b-h1-gate", command)

    def test_twelve_gib_runtime_guard_fits_smaller_live_host_ceiling(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "requested_modes": 80,
            "candidate_modes": 160,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "container_limit_bytes": 13 * 1024**3,
            "host_available_memory_bytes": int(12.75 * 1024**3),
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
        }
        wider = hybrid_launch_gate(
            matrix,
            warning_gib=10.678571428571429,
            terminate_gib=12.071428571428571,
            **common,
        )
        self.assertFalse(wider["pass"])
        self.assertIn(
            "warning_threshold_not_wider_than_scaled_gate",
            wider["failures"],
        )
        self.assertIn(
            "termination_threshold_not_wider_than_scaled_gate",
            wider["failures"],
        )

        guarded = hybrid_launch_gate(
            matrix,
            warning_gib=9.857142857142856,
            terminate_gib=11.142857142857142,
            **common,
        )
        self.assertTrue(guarded["pass"], guarded["failures"])
        self.assertEqual(
            guarded["live_scaled_limits"]["effective_hard_budget_gib"],
            12.75,
        )
        undersized = hybrid_launch_gate(
            matrix,
            warning_gib=9.857142857142856,
            terminate_gib=11.142857142857142,
            **{
                **common,
                "host_available_memory_bytes": 12 * 1024**3 - 1,
            },
        )
        self.assertFalse(undersized["pass"])
        self.assertIn(
            "warning_threshold_not_wider_than_scaled_gate",
            undersized["failures"],
        )
        self.assertIn(
            "termination_threshold_not_wider_than_scaled_gate",
            undersized["failures"],
        )

    def test_hybrid_command_preserves_degree_buffer_and_graded_policy(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "graded_h5_m80",
                "--degree",
                "2",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--requested-modes",
                "80",
                "--candidate-modes",
                "160",
                "--graded-reference-h",
                "5",
                "--full3d-reference",
                "records/p2_h5_reference.json",
                "--verified-clean-sha",
                "c" * 40,
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        rendered = " ".join(command)
        self.assertIn("benchmarks.run_task032_phase6_augmented", rendered)
        self.assertIn("--degree 2", rendered)
        self.assertIn("--requested-modes 80", rendered)
        self.assertIn("--candidate-modes 160", rendered)
        self.assertIn("--graded-reference-h 5.0", rendered)
        self.assertIn("--incident-grazing-deg 10.0", rendered)
        self.assertIn("--polarization-kind s", rendered)
        self.assertIn("--comparison-solver-path fast", rendered)
        self.assertEqual(
            Path(command[command.index("--full3d-reference") + 1]),
            Path("records/p2_h5_reference.json"),
        )
        self.assertIn("--memory-stages", command)

    def test_hybrid_command_can_refine_only_the_modal_cross_section(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "task035c_p2_h5_modal_h3",
                "--degree",
                "2",
                "--h-nm",
                "5",
                "--modal-degree",
                "2",
                "--modal-h-nm",
                "3",
                "--mpi-size",
                "1",
                "--requested-modes",
                "120",
                "--candidate-modes",
                "240",
                "--full3d-reference",
                "records/p2_h5_reference.json",
                "--verified-clean-sha",
                "d" * 40,
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        rendered = " ".join(command)
        self.assertIn("--degree 2", rendered)
        self.assertIn("--h-nm 5.0", rendered)
        self.assertIn("--modal-degree 2", rendered)
        self.assertIn("--modal-h-nm 3.0", rendered)

    def test_hybrid_candidate_pool_is_exactly_twice_requested_modes(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        evidence = _m160_nonconvergence_evidence()
        digest = "f" * 64
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 20 * 1024**3,
            "warning_gib": 11.0,
            "terminate_gib": 12.5,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
        }
        for requested_modes in (80, 120, 160, 240):
            conditional = (
                {
                    "m160_funnel_evidence": evidence,
                    "expected_m160_funnel_sha256": digest,
                    "observed_m160_funnel_sha256": digest,
                }
                if requested_modes == 240
                else {}
            )
            with self.subTest(requested_modes=requested_modes, relation="exact"):
                gate = hybrid_launch_gate(
                    matrix,
                    requested_modes=requested_modes,
                    candidate_modes=2 * requested_modes,
                    **conditional,
                    **common,
                )
                self.assertTrue(gate["pass"], gate["failures"])
                self.assertTrue(
                    gate["checks"]["candidate_pool_is_twice_requested_modes"]
                )
            for candidate_modes in (
                2 * requested_modes - 1,
                2 * requested_modes + 1,
            ):
                with self.subTest(
                    requested_modes=requested_modes,
                    candidate_modes=candidate_modes,
                ):
                    gate = hybrid_launch_gate(
                        matrix,
                        requested_modes=requested_modes,
                        candidate_modes=candidate_modes,
                        **conditional,
                        **common,
                    )
                    self.assertFalse(gate["pass"])
                    self.assertIn(
                        "candidate_pool_is_twice_requested_modes",
                        gate["failures"],
                    )

    def test_hybrid_nondefault_physics_and_minimal_comparison_are_forwarded(
        self,
    ) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "p1_h5_augmented_vs_minimal_p",
                "--degree",
                "1",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--requested-modes",
                "80",
                "--candidate-modes",
                "160",
                "--solver-path",
                "augmented",
                "--compare-modal-schur",
                "--comparison-solver-path",
                "minimal",
                "--incident-grazing-deg",
                "5",
                "--polarization-kind",
                "p",
                "--verified-clean-sha",
                SOURCE_SHA,
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        rendered = " ".join(command)
        self.assertIn("--incident-grazing-deg 5.0", rendered)
        self.assertIn("--polarization-kind p", rendered)
        self.assertIn("--comparison-solver-path minimal", rendered)

        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "requested_modes": 80,
            "candidate_modes": 160,
            "solver_path": "augmented",
            "compare_modal_schur": True,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 5.0,
            "polarization_kind": "p",
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 20 * 1024**3,
            "warning_gib": 11.0,
            "terminate_gib": 12.5,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
        }
        fast = hybrid_launch_gate(matrix, comparison_solver_path="fast", **common)
        self.assertFalse(fast["pass"])
        self.assertIn(
            "task033_augmented_comparison_uses_memory_minimal",
            fast["failures"],
        )
        minimal = hybrid_launch_gate(matrix, comparison_solver_path="minimal", **common)
        self.assertTrue(minimal["pass"], minimal["failures"])
        self.assertEqual(minimal["physical_case"]["comparison_solver_path"], "minimal")
        self.assertEqual(
            minimal["independent_prediction"][
                "uncalibrated_incidence_polarization_contingency"
            ],
            1.25,
        )

    def test_m240_requires_bound_same_case_measured_m160_nonconvergence(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        evidence = _m160_nonconvergence_evidence()
        self.assertEqual(evidence["status"], "not_qualified")
        digest = "f" * 64
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "requested_modes": 240,
            "candidate_modes": 480,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 20 * 1024**3,
            "warning_gib": 11.0,
            "terminate_gib": 12.5,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
            "expected_m160_funnel_sha256": digest,
            "observed_m160_funnel_sha256": digest,
        }
        passed = hybrid_launch_gate(matrix, m160_funnel_evidence=evidence, **common)
        self.assertTrue(passed["pass"], passed["failures"])
        self.assertTrue(passed["conditional_m240_evidence"]["pass"])
        self.assertEqual(
            passed["independent_prediction"]["conditional_mode_workspace_contingency"],
            2.25,
        )

        missing = hybrid_launch_gate(matrix, m160_funnel_evidence=None, **common)
        self.assertFalse(missing["pass"])
        stale_case = copy.deepcopy(evidence)
        stale_case["case"]["h_nm"] = 3.0
        stale = hybrid_launch_gate(matrix, m160_funnel_evidence=stale_case, **common)
        self.assertFalse(stale["pass"])
        wrong_digest = hybrid_launch_gate(
            matrix,
            m160_funnel_evidence=evidence,
            **{**common, "observed_m160_funnel_sha256": "e" * 64},
        )
        self.assertFalse(wrong_digest["pass"])

    def test_task32_comparison_contract_records_selected_builder(self) -> None:
        source = (ROOT / "benchmarks" / "run_task032_phase6_augmented.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--comparison-solver-path"', source)
        self.assertIn('choices=("fast", "minimal")', source)
        self.assertIn('"comparison_solver_path": comparison_solver_path', source)
        self.assertIn("build_hybrid_modal_schur_memory_minimal_system", source)

    def test_contract_rejects_missing_qep_material_and_bad_thresholds(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "qep",
                    "--case-label",
                    "missing_material",
                    "--degree",
                    "1",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--verified-clean-sha",
                    "d" * 40,
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "qep",
                    "--case-label",
                    "undersampled_left_pool",
                    "--degree",
                    "1",
                    "--h-nm",
                    "3",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "8",
                    "--candidate-modes",
                    "8",
                    "--material-kind",
                    "air",
                    "--verified-clean-sha",
                    "d" * 40,
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "bad_threshold",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--verified-clean-sha",
                    "e" * 40,
                    "--warning-gib",
                    "13",
                    "--terminate-gib",
                    "12",
                ]
            )

    def test_anchor_requalification_cli_is_explicit_and_narrow(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "same_case_m80",
                "--degree",
                "2",
                "--h-nm",
                "3",
                "--mpi-size",
                "1",
                "--requested-modes",
                "80",
                "--candidate-modes",
                "160",
                "--verified-clean-sha",
                "f" * 40,
                "--task033-same-sha-anchor-requalification",
            ]
        )
        self.assertTrue(args.task033_same_sha_anchor_requalification)

        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "wrong_anchor",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "80",
                    "--candidate-modes",
                    "160",
                    "--verified-clean-sha",
                    "f" * 40,
                    "--task033-same-sha-anchor-requalification",
                ]
            )

    def test_hybrid_cli_accepts_only_exact_two_m_candidate_pools(self) -> None:
        for requested_modes in (80, 120, 160, 240):
            base = [
                "--target",
                "hybrid",
                "--case-label",
                f"m{requested_modes}",
                "--degree",
                "1",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--requested-modes",
                str(requested_modes),
                "--verified-clean-sha",
                "f" * 40,
            ]
            if requested_modes == 240:
                base.extend(
                    [
                        "--m160-funnel-evidence-file",
                        "m160_funnel.json",
                        "--m160-funnel-evidence-sha256",
                        "a" * 64,
                    ]
                )
            with self.subTest(requested_modes=requested_modes, relation="exact"):
                args = _parse_args(
                    [
                        *base,
                        "--candidate-modes",
                        str(2 * requested_modes),
                    ]
                )
                self.assertEqual(args.candidate_modes, 2 * requested_modes)
            for candidate_modes in (
                2 * requested_modes - 1,
                2 * requested_modes + 1,
            ):
                with self.subTest(
                    requested_modes=requested_modes,
                    candidate_modes=candidate_modes,
                ):
                    with self.assertRaises(SystemExit):
                        _parse_args(
                            [
                                *base,
                                "--candidate-modes",
                                str(candidate_modes),
                            ]
                        )

    def test_static_hybrid_cli_requires_hash_bound_fresh_reference(self) -> None:
        base = [
            "--target",
            "hybrid",
            "--case-label",
            "static_h1a",
            "--degree",
            "2",
            "--h-nm",
            "5",
            "--mpi-size",
            "1",
            "--requested-modes",
            "120",
            "--candidate-modes",
            "240",
            "--full3d-reference",
            "fresh_static.json",
            "--stage4-full3d-assembly-backend",
            "assembly_time_static_condensed",
            "--verified-clean-sha",
            "f" * 40,
        ]
        args = _parse_args([*base, "--full3d-reference-sha256", "a" * 64])
        self.assertEqual(
            args.stage4_full3d_assembly_backend,
            "assembly_time_static_condensed",
        )
        self.assertEqual(args.full3d_reference_sha256, "a" * 64)
        with self.assertRaises(SystemExit):
            _parse_args(base)
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "standard",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "120",
                    "--candidate-modes",
                    "240",
                    "--full3d-reference",
                    "standard.json",
                    "--full3d-reference-sha256",
                    "a" * 64,
                    "--verified-clean-sha",
                    "f" * 40,
                ]
            )

    def test_h5_numerical_pass_does_not_require_physical_truncation(self) -> None:
        record = {
            "qualification": {
                "task037b_h5_gate": True,
                "worker_numerical_pass": True,
                "integration_pass": True,
                "task033_physical_truncation_allowed": False,
            }
        }
        self.assertTrue(_task037b_h5_numerical_pass(record))
        record["qualification"]["integration_pass"] = False
        self.assertFalse(_task037b_h5_numerical_pass(record))
        self.assertFalse(
            _task037b_h5_numerical_pass(
                {
                    "qualification": {
                        "worker_numerical_pass": True,
                        "integration_pass": True,
                    }
                }
            )
        )

    def test_v1_numerical_pass_recomputes_raw_component_contract(self) -> None:
        self.assertTrue(_task037b_v1_r1_numerical_pass(_v1_raw_record()))

        error_record = _v1_raw_record()
        error_record["v1_telemetry"]["sides"]["bottom"]["probes"][0][
            "action_relative_error"
        ] = 2.0e-11
        self.assertFalse(_task037b_v1_r1_numerical_pass(error_record))

        missing_side = _v1_raw_record()
        del missing_side["v1_telemetry"]["sides"]["top"]
        self.assertFalse(_task037b_v1_r1_numerical_pass(missing_side))

        qualification_only = {
            "qualification": {
                "task037b_v1_gate": True,
                "r1_pass": True,
                "integration_pass": True,
            }
        }
        self.assertFalse(_task037b_v1_r1_numerical_pass(qualification_only))

    def test_v1_r2_numerical_pass_recomputes_f_only_contract(self) -> None:
        self.assertTrue(_task037b_v1_r2_numerical_pass(_v1_r2_raw_record()))

        error_record = _v1_r2_raw_record()
        error_record["v1_r2_telemetry"]["sides"]["bottom"]["probes"][0]["first"][
            "f_only_true_residual"
        ] = 2.0e-8
        error_record["v1_r2_telemetry"]["sides"]["bottom"]["probes"][0]["pass"] = False
        error_record["v1_r2_telemetry"]["sides"]["bottom"]["pass"] = False
        error_record["gates"]["r2_pass"] = False
        error_record["qualification"]["r2_pass"] = False
        error_record["qualification"]["worker_numerical_pass"] = False
        error_record["qualification"]["disposition"] = (
            "F_ONLY_LOCAL_INVERSE_FAMILY_DIAGNOSTIC_NEGATIVE"
        )
        self.assertTrue(
            _task037b_v1_r2_numerical_pass(error_record, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v1_r2_numerical_pass(error_record))

        missing_side = _v1_r2_raw_record()
        del missing_side["v1_r2_telemetry"]["sides"]["top"]
        self.assertFalse(_task037b_v1_r2_numerical_pass(missing_side))

        malformed_name = _v1_r2_raw_record()
        malformed_name["v1_r2_telemetry"]["sides"]["bottom"]["probes"][0]["name"] = None
        self.assertFalse(_task037b_v1_r2_numerical_pass(malformed_name))

        wrong_configuration = _v1_r2_raw_record()
        wrong_configuration["v1_r2_telemetry"]["preconditioner"]["bottom"][
            "configuration"
        ]["overlap_fraction"] = 0.25
        self.assertFalse(_task037b_v1_r2_numerical_pass(wrong_configuration))

        qualification_only = {
            "qualification": {
                "task037b_v1_gate": True,
                "r2_pass": True,
                "integration_pass": True,
            }
        }
        self.assertFalse(_task037b_v1_r2_numerical_pass(qualification_only))

    def test_v1_r3_checker_contract_and_legal_negative(self) -> None:
        self.assertTrue(_task037b_v1_r3_numerical_pass(_v1_r3_raw_record()))

        negative = _v1_r3_raw_record(numerical_negative=True)
        self.assertTrue(
            _task037b_v1_r3_numerical_pass(negative, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v1_r3_numerical_pass(negative))

        wrong_profile = _v1_r3_raw_record()
        wrong_profile["v1_r3_telemetry"]["sides"]["bottom"]["cases"]["R3-F"][
            "preconditioner"
        ]["configuration"]["preconditioner_profile"] = "h5_six_slab_ilu0"
        self.assertFalse(_task037b_v1_r3_numerical_pass(wrong_profile))

        unreleased = _v1_r3_raw_record()
        unreleased["v1_r3_telemetry"]["sides"]["top"]["cases"]["R3-A"][
            "preconditioner"
        ]["factors_released"] = False
        self.assertFalse(_task037b_v1_r3_numerical_pass(unreleased))

    def test_v1_r4_checker_contract_threshold_lifecycle_and_terminal(self) -> None:
        self.assertTrue(_task037b_v1_r4_numerical_pass(_v1_r4_raw_record()))

        threshold = _v1_r4_raw_record()
        threshold["v1_r4_telemetry"]["sides"]["bottom"]["rows"][1][
            "woodbury_true_residual"
        ] = 1.0e-9
        self.assertFalse(_task037b_v1_r4_numerical_pass(threshold))

        unreleased = _v1_r4_raw_record()
        unreleased["v1_r4_telemetry"]["sides"]["top"]["factor_release"]["f_factor"][
            "factor_count_after"
        ] = 1
        self.assertFalse(_task037b_v1_r4_numerical_pass(unreleased))

        terminal = _v1_r4_raw_record()
        terminal["timestamp_utc"] = "2026-08-08T00:00:00+00:00"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "solver_record.json"
            path.write_text(json.dumps(terminal), encoding="utf-8")
            self.assertTrue(_task034_terminal_record_is_complete(path))

    def test_v1_r5_checker_mapping_lifecycle_and_resource_gate(self) -> None:
        record = _v1_r5_raw_record()
        self.assertTrue(_task037b_v1_r5_numerical_pass(record))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "solver_record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertTrue(_task034_terminal_record_is_complete(path))

        borderline = _v1_r5_raw_record(numerical_negative=True, negative_side="bottom")
        self.assertTrue(
            _task037b_v1_r5_numerical_pass(borderline, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v1_r5_numerical_pass(borderline))

        negative = copy.deepcopy(borderline)
        for side_name, side in negative["v1_r5_telemetry"]["sides"].items():
            for row in side["rows"]:
                if (row["metadata"] or {}).get("kind") == (
                    "partition_independent_complex_random"
                ):
                    row["first"]["complete_A_true_residual"] = 2.0e-2
                    row["second"]["complete_A_true_residual"] = 2.0e-2
                    row["pass"] = False
                    row["capacity_pass"] = False
            side["capacity_pass_count"] = 6 if side_name == "bottom" else 7
            side["pass"] = False
        negative["v1_r5_telemetry"]["r5_borderline"] = False
        negative["v1_r5_telemetry"]["severe_negative"] = True
        negative["status"] = "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE"
        negative["qualification"]["disposition"] = (
            "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE"
        )
        self.assertTrue(
            _task037b_v1_r5_numerical_pass(negative, require_numerical_pass=False)
        )

        lifecycle = _v1_r5_raw_record()
        lifecycle["gates"]["r5_factor_lifecycle"][
            "global_final_active_factor_count"
        ] = 1
        self.assertFalse(
            _task037b_v1_r5_numerical_pass(lifecycle, require_numerical_pass=False)
        )

        common = {
            "formal_pass": True,
            "record_complete": True,
            "numerical_pass": True,
        }
        below = _task037b_r5_resource_gate(
            **common, process_tree_peak_mb=7.0 * 1024.0 - 1.0
        )
        exact = _task037b_r5_resource_gate(**common, process_tree_peak_mb=7.0 * 1024.0)
        above = _task037b_r5_resource_gate(
            **common, process_tree_peak_mb=7.0 * 1024.0 + 1.0
        )
        missing = _task037b_r5_resource_gate(**common, process_tree_peak_mb=None)
        self.assertTrue(below["h6_eligible"])
        self.assertTrue(exact["h6_eligible"])
        self.assertTrue(above["resource_review"])
        self.assertFalse(above["h6_eligible"])
        self.assertTrue(missing["measurement_failure"])
        self.assertFalse(missing["h6_eligible"])

    def test_h5_external_no_swap_is_a_formal_requirement(self) -> None:
        kwargs = {
            "return_code": 0,
            "numerical_pass": True,
            "resource_gate_pass": True,
            "source_gate_pass": True,
            "launch_gate_pass": True,
            "terminated_for_memory": False,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
        }
        self.assertTrue(_formal_shard_pass(**kwargs, no_swap_pass=True))
        self.assertFalse(_formal_shard_pass(**kwargs, no_swap_pass=False))

    def test_h5_terminal_stage_requires_complete_record_and_no_workers(self) -> None:
        kwargs = {
            "task034_workstation_gate": True,
            "process_running": True,
            "authority_readable": False,
            "stage": "h5b_release_record",
            "terminal_record_complete": True,
            "live_worker_count": 0,
            "terminal_stage": "h5b_release_record",
        }
        self.assertTrue(_task034_terminal_worker_drain(**kwargs))
        self.assertFalse(
            _task034_terminal_worker_drain(**{**kwargs, "stage": "record_and_release"})
        )
        self.assertFalse(
            _task034_terminal_worker_drain(
                **{**kwargs, "terminal_record_complete": False}
            )
        )
        self.assertFalse(
            _task034_terminal_worker_drain(**{**kwargs, "live_worker_count": 1})
        )

    def test_v1_r3_terminal_record_is_complete(self) -> None:
        record = _v1_r3_raw_record()
        record["timestamp_utc"] = "2026-08-08T00:00:00+00:00"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "solver_record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertTrue(_task034_terminal_record_is_complete(path))

    def test_h5_stage_memory_summary_keeps_peaks_separate(self) -> None:
        rows = [
            {
                "stage": "h5_action_coupling_build",
                "worker_rank_rss_sum_mb": 10.0,
                "worker_rank_pss_sum_mb": 4.0,
                "worker_rank_uss_sum_mb": 3.0,
                "mpi_process_tree_rss_mb": 20.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5a_bottom_factor",
                "worker_rank_rss_sum_mb": 12.0,
                "worker_rank_pss_sum_mb": 5.0,
                "worker_rank_uss_sum_mb": 4.0,
                "mpi_process_tree_rss_mb": 24.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5a_top_solve",
                "worker_rank_rss_sum_mb": 15.0,
                "worker_rank_pss_sum_mb": 6.0,
                "worker_rank_uss_sum_mb": 5.0,
                "mpi_process_tree_rss_mb": 30.0,
                "worker_rank_smaps_readable_count": 1,
            },
            {
                "stage": "h5_post_direct_heap_trim",
                "worker_rank_rss_sum_mb": 8.0,
                "worker_rank_pss_sum_mb": 3.0,
                "worker_rank_uss_sum_mb": 2.0,
                "mpi_process_tree_rss_mb": 16.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5b_bottom_solves",
                "worker_rank_rss_sum_mb": 25.0,
                "worker_rank_pss_sum_mb": 9.0,
                "worker_rank_uss_sum_mb": 7.0,
                "mpi_process_tree_rss_mb": 40.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5b_top_solves",
                "worker_rank_rss_sum_mb": 30.0,
                "worker_rank_pss_sum_mb": 10.0,
                "worker_rank_uss_sum_mb": 8.0,
                "mpi_process_tree_rss_mb": 50.0,
                "worker_rank_smaps_readable_count": 2,
            },
        ]
        summary = _h5_stage_memory_summary(rows, expected_mpi_size=2)
        common = summary["common_action_coupling"]
        h5a = summary["h5a_direct_reference"]
        trim = summary["h5_post_direct_trim"]
        h5b = summary["h5b_candidate"]
        self.assertEqual(common["peak_worker_rank_rss_sum_mb"], 10.0)
        self.assertEqual(common["peak_mpi_process_tree_rss_mb"], 20.0)
        self.assertEqual(h5a["peak_worker_rank_rss_sum_mb"], 15.0)
        self.assertEqual(h5a["peak_mpi_process_tree_rss_mb"], 30.0)
        self.assertEqual(h5a["peak_worker_rank_pss_sum_mb"], 5.0)
        self.assertEqual(h5a["peak_worker_rank_uss_sum_mb"], 4.0)
        self.assertEqual(h5a["complete_smaps_sample_count"], 1)
        self.assertEqual(trim["peak_worker_rank_rss_sum_mb"], 8.0)
        self.assertEqual(h5b["peak_worker_rank_rss_sum_mb"], 30.0)
        self.assertEqual(h5b["peak_mpi_process_tree_rss_mb"], 50.0)
        self.assertEqual(h5b["peak_worker_rank_pss_sum_mb"], 10.0)
        self.assertEqual(h5b["peak_worker_rank_uss_sum_mb"], 8.0)
        incomplete = _h5_stage_memory_summary(
            [
                {
                    "stage": "h5_post_direct_heap_trim",
                    "worker_rank_rss_sum_mb": 18.0,
                    "worker_rank_pss_sum_mb": 11.0,
                    "worker_rank_uss_sum_mb": 9.0,
                    "mpi_process_tree_rss_mb": 27.0,
                    "worker_rank_smaps_readable_count": 1,
                }
            ],
            expected_mpi_size=2,
        )["h5_post_direct_trim"]
        self.assertEqual(incomplete["complete_smaps_sample_count"], 0)
        self.assertIsNone(incomplete["peak_worker_rank_pss_sum_mb"])
        self.assertIsNone(incomplete["peak_worker_rank_uss_sum_mb"])
        self.assertEqual(incomplete["peak_worker_rank_rss_sum_mb"], 18.0)
        self.assertEqual(incomplete["peak_mpi_process_tree_rss_mb"], 27.0)

    def test_v2_parser_scope_forwarding_and_fixed_watchdog_limits(self) -> None:
        base = [
            "--target",
            "hybrid",
            "--case-label",
            "task037b_v2",
            "--degree",
            "6",
            "--h-nm",
            "10",
            "--modal-degree",
            "6",
            "--modal-h-nm",
            "10",
            "--mpi-size",
            "8",
            "--requested-modes",
            "120",
            "--candidate-modes",
            "240",
            "--solver-path",
            "block-ldu-action-screen",
            "--stage4-full3d-assembly-backend",
            "assembly_time_static_condensed",
            "--bottom-interface-nm",
            "10",
            "--top-interface-nm",
            "110",
            "--incident-grazing-deg",
            "10",
            "--polarization-kind",
            "s",
            "--internal-propagation-model",
            "full3d_uniform_cg",
            "--internal-traction-model",
            "scalar_cg_discrete_derivative",
            "--full3d-reference",
            "full3d.json",
            "--full3d-reference-sha256",
            "b" * 64,
            "--task035c-p6-preflight-authority",
            "preflight.json",
            "--task035c-p6-preflight-sha256",
            "a" * 64,
            "--verified-clean-sha",
            SOURCE_SHA,
            "--host-environment-id",
            "WSL2-Ubuntu-24.04",
            "--task037b-v2-gate",
            "--task037b-v2-profile",
            "bottom-approx",
            "--task037b-v2-max-it",
            "20",
            "--warning-gib",
            "10",
            "--terminate-gib",
            "14",
            "--timeout-seconds",
            "3600",
        ]
        args = _parse_args(base)
        self.assertEqual(args.task037b_v2_profile, "bottom-approx")
        self.assertEqual(args.task037b_v2_max_it, 20)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        self.assertEqual(command.count("--task037b-v2-gate"), 1)
        self.assertEqual(command.count("--task037b-v2-profile"), 1)
        self.assertIn("bottom-approx", command)
        self.assertEqual(command.count("--task037b-v2-max-it"), 1)
        for flag in (
            "--task035c-p6-h10-gate",
            "--task037b-h1-gate",
            "--task037b-h3-gate",
            "--task037b-h4-gate",
            "--task037b-h5-gate",
            "--task037b-v1-gate",
        ):
            self.assertNotIn(flag, command)
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    item
                    for item in base
                    if item not in {"--task037b-v2-profile", "bottom-approx"}
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    *base[:-6],
                    "--warning-gib",
                    "11",
                    "--terminate-gib",
                    "14",
                    "--timeout-seconds",
                    "3600",
                ]
            )
        double = _parse_args(
            [
                *base,
                "--task037b-v2-profile",
                "double",
                "--task037b-v2-max-it",
                "100",
                "--timeout-seconds",
                "7200",
            ]
        )
        self.assertEqual(
            (double.task037b_v2_profile, double.task037b_v2_max_it), ("double", 100)
        )
        self.assertEqual(
            worker_process_group_popen_kwargs().get("start_new_session"), True
        )
        v3_base = [
            item
            for item in base
            if item
            not in {
                "--task037b-v2-gate",
                "--task037b-v2-profile",
                "bottom-approx",
                "--task037b-v2-max-it",
                "20",
                "--timeout-seconds",
                "3600",
            }
        ]
        v3_base.extend(("--task037b-v3-gate", "--timeout-seconds", "7200"))
        v3_args = _parse_args(v3_base)
        self.assertTrue(v3_args.task037b_v3_gate)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            v3_command = _worker_command(
                v3_args, root / "record.json", root / "stages.jsonl"
            )
        self.assertEqual(v3_command.count("--task037b-v3-gate"), 1)
        for forbidden in (
            "--task037b-v2-gate",
            "--task037b-v2-profile",
            "--task037b-v2-max-it",
            "--task037b-h1-gate",
            "--task037b-h3-gate",
            "--task037b-h4-gate",
            "--task037b-h5-gate",
            "--task037b-v1-gate",
        ):
            self.assertNotIn(forbidden, v3_command)

    def test_v2_raw_checker_recomputes_pass_negative_lifecycle_and_terminal(
        self,
    ) -> None:
        for profile in ("bottom-approx", "top-approx", "double"):
            record = _v2_raw_record(profile=profile)
            self.assertTrue(_task037b_v2_numerical_pass(record))
            record["status"] = "forged_status"
            self.assertFalse(
                _task037b_v2_numerical_pass(record, require_numerical_pass=False)
            )
        self.assertTrue(
            _task037b_v2_numerical_pass(_v2_raw_record(profile="double", max_it=100))
        )
        self.assertTrue(
            _task037b_v2_numerical_pass(_v2_raw_record(profile="double", max_it=200))
        )
        negative = _v2_raw_record(profile="bottom-approx", negative=True)
        self.assertFalse(_task037b_v2_numerical_pass(negative))
        self.assertTrue(
            _task037b_v2_numerical_pass(negative, require_numerical_pass=False)
        )
        frozen_screen = _v2_raw_record(profile="double")
        frozen_screen["screen"]["restart"] = 89
        self.assertFalse(
            _task037b_v2_numerical_pass(frozen_screen, require_numerical_pass=False)
        )
        lifecycle = _v2_raw_record(profile="double")
        lifecycle["v2_telemetry"]["release_pass"] = False
        self.assertFalse(
            _task037b_v2_numerical_pass(lifecycle, require_numerical_pass=False)
        )
        destroyed = _v2_raw_record(profile="double")
        destroyed["v2_telemetry"]["release_records"]["bottom"]["woodbury"]["after"][
            "destroyed"
        ] = False
        self.assertFalse(
            _task037b_v2_numerical_pass(destroyed, require_numerical_pass=False)
        )
        terminal = _v2_raw_record(profile="double")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "solver_record.json"
            path.write_text(json.dumps(terminal), encoding="utf-8")
            self.assertTrue(_task034_terminal_record_is_complete(path))

    def test_v2_resource_classification_keeps_numeric_result_separate(self) -> None:
        below = _task037b_v2_resource_classification(5.0 * 1024.0)
        exact = _task037b_v2_resource_classification(6.0 * 1024.0)
        above = _task037b_v2_resource_classification(6.0 * 1024.0 + 1.0)
        missing = _task037b_v2_resource_classification(None)
        negative = _task037b_v2_resource_classification(-1.0)
        self.assertTrue(below["engineering_positive"])
        self.assertTrue(below["resource_positive"])
        self.assertTrue(exact["resource_positive"])
        self.assertFalse(exact["resource_review"])
        self.assertTrue(above["resource_review"])
        self.assertFalse(above["resource_positive"])
        self.assertTrue(missing["measurement_failure"])
        self.assertTrue(negative["measurement_failure"])
        self.assertFalse(negative["measurement_present"])

    def test_v3_raw_checker_recomputes_classification_and_resource_separation(
        self,
    ) -> None:
        passed = _v3_raw_record("pass")
        self.assertTrue(_task037b_v3_numerical_pass(passed))
        self.assertEqual(
            _task037b_v3_evaluate_record(passed)["disposition"],
            "DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW",
        )

        slow = _v3_raw_record("slow")
        self.assertTrue(_task037b_v3_numerical_pass(slow, require_numerical_pass=False))
        self.assertFalse(_task037b_v3_numerical_pass(slow))
        self.assertEqual(
            _task037b_v3_evaluate_record(slow)["disposition"],
            "DOUBLE_APPROXIMATE_SLOW_CONTRACTION_AWAITING_REVIEW",
        )

        negative = _v3_raw_record("negative")
        self.assertTrue(
            _task037b_v3_numerical_pass(negative, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v3_numerical_pass(negative))
        self.assertEqual(
            _task037b_v3_evaluate_record(negative)["disposition"],
            "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE",
        )

        early = _v3_raw_record("early")
        self.assertTrue(_task037b_v3_numerical_pass(early))
        self.assertEqual(
            early["screen"]["gate"]["not_reached_due_to_convergence"],
            [20, 30, 40, 60, 80, 90, 100, 120, 150, 160, 180, 200],
        )
        bounded_checkpoint = _v3_raw_record("early")
        last_row = bounded_checkpoint["screen"]["history"][-1]
        for iteration in range(11, 21):
            row = copy.deepcopy(last_row)
            row["iteration"] = iteration
            row["elapsed_seconds"] = float(iteration + 1)
            bounded_checkpoint["screen"]["history"].append(row)
        bounded_checkpoint["screen"]["iterations"] = 20
        bounded_checkpoint["screen"]["converged_reason"] = 2
        bounded_checkpoint["screen"]["gate"]["stage"] = 20
        bounded_checkpoint["screen"]["gate"]["not_reached_due_to_convergence"] = [
            30,
            40,
            60,
            80,
            90,
            100,
            120,
            150,
            160,
            180,
            200,
        ]
        bounded_checkpoint["v3_telemetry"]["stage_markers"].insert(8, "outer_iter_20")
        self.assertTrue(_task037b_v3_numerical_pass(bounded_checkpoint))

        implementation = _v3_raw_record("implementation")
        self.assertFalse(
            _task037b_v3_numerical_pass(implementation, require_numerical_pass=False)
        )
        hard_stop = _v3_raw_record("negative")
        for row in hard_stop["screen"]["history"][-5:]:
            for key in (
                "reported_relative_residual",
                "global_true_relative_residual",
                "bottom_true_relative_residual",
                "top_true_relative_residual",
                "modal_true_relative_residual",
            ):
                row[key] = 2.0
        hard_stop["screen"]["progressive_stop_cause"] = "v3_hard_stop"
        self.assertTrue(
            _task037b_v3_numerical_pass(hard_stop, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v3_numerical_pass(hard_stop))
        self.assertEqual(
            _task037b_v3_evaluate_record(hard_stop)["disposition"],
            "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE",
        )
        breakdown = _v3_raw_record("negative")
        breakdown["screen"]["converged_reason"] = -5
        breakdown["screen"]["progressive_stop_cause"] = None
        self.assertTrue(
            _task037b_v3_numerical_pass(breakdown, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v3_numerical_pass(breakdown))

        nonnegative_slope = _v3_raw_record("pass")
        for row in nonnegative_slope["screen"]["history"]:
            if 120 <= row["iteration"] <= 200:
                for key in (
                    "reported_relative_residual",
                    "global_true_relative_residual",
                    "bottom_true_relative_residual",
                    "top_true_relative_residual",
                    "modal_true_relative_residual",
                ):
                    row[key] = 0.01
        nonnegative_slope["screen"]["gate"].update(
            {
                "prediction_slope": 0.0,
                "prediction_intercept": math.log(0.01),
                "prediction_q_fit": 1.0,
                "predicted_iterations": None,
                "pass": False,
            }
        )
        nonnegative_slope["status"] = "task037b_v3_family_negative"
        nonnegative_slope["qualification"].update(
            {
                "disposition": "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE",
                "worker_numerical_pass": False,
            }
        )
        nonnegative_evaluation = _task037b_v3_evaluate_record(nonnegative_slope)
        self.assertTrue(
            _task037b_v3_numerical_pass(nonnegative_slope, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v3_numerical_pass(nonnegative_slope))
        self.assertTrue(nonnegative_evaluation["prediction_infinite"])
        self.assertEqual(
            nonnegative_evaluation["disposition"],
            "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE",
        )

        tamper_cases = (
            (
                "reason_cause",
                "negative",
                lambda candidate: candidate["screen"].update({"converged_reason": -3}),
                "reason_cause",
            ),
            (
                "not_reached",
                "negative",
                lambda candidate: candidate["screen"]["gate"].update(
                    {"not_reached_due_to_convergence": [20]}
                ),
                "not_reached",
            ),
            (
                "duplicate_history",
                "negative",
                lambda candidate: candidate["screen"]["history"].append(
                    copy.deepcopy(candidate["screen"]["history"][-1])
                ),
                "history",
            ),
            (
                "missing_history",
                "negative",
                lambda candidate: candidate["screen"]["history"].pop(3),
                "history",
            ),
            (
                "reported_true_audit",
                "negative",
                lambda candidate: candidate["screen"]["history"][1].update(
                    {"reported_relative_residual": 1.0}
                ),
                "reported_true_agree",
            ),
            (
                "prediction_samples",
                "pass",
                lambda candidate: candidate["screen"]["gate"].update(
                    {"prediction_sample_count": 80}
                ),
                "prediction",
            ),
            (
                "callback_rank",
                "negative",
                lambda candidate: candidate["v3_telemetry"][
                    "fixed_callback_certificates"
                ]["bottom"]["woodbury"].update({"K_rank": 39}),
                "callback",
            ),
            (
                "callback_condition",
                "negative",
                lambda candidate: candidate["v3_telemetry"][
                    "fixed_callback_certificates"
                ]["top"]["woodbury"].update({"K_condition_number": 1.0e7}),
                "callback",
            ),
            (
                "modal_condition",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["modal_schur"].update(
                    {"condition": 1.0e7}
                ),
                "modal",
            ),
            (
                "modal_rank",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["modal_schur"].update(
                    {"rank": 239}
                ),
                "modal",
            ),
            (
                "direct_inventory",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["factor_identity"][
                    "bottom"
                ].update({"direct_factor_count": 1}),
                "factor_identity",
            ),
            (
                "nested_ksp",
                "negative",
                lambda candidate: candidate["v3_telemetry"][
                    "fixed_callback_certificates"
                ]["top"].update({"nested_ksp_created": True}),
                "callback",
            ),
            (
                "apply_count",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["sides"]["top"][
                    "online_apply"
                ].update({"increment": 1}),
                "online_counts",
            ),
            (
                "outer_release",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["release_records"][
                    "outer"
                ].update({"destroy_calls_complete": False}),
                "outer_release",
            ),
            (
                "side_release",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["release_records"][
                    "bottom"
                ]["woodbury"]["after"].update({"destroyed": False}),
                "release",
            ),
            (
                "stage_order",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["stage_markers"].append(
                    "outer_iter_200"
                ),
                "stages",
            ),
            (
                "official_output",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["official_outputs"].update(
                    {"R": "run"}
                ),
                "official_boundary",
            ),
            (
                "object_inventory",
                "negative",
                lambda candidate: candidate["v3_telemetry"]["sides"]["bottom"][
                    "object_ledger"
                ]["inventory"].update({"fine_global_A_materialized": True}),
                "object_inventory",
            ),
            (
                "record_status",
                "negative",
                lambda candidate: candidate.update({"status": "task037b_v3_pass"}),
                "record_status_mismatch",
            ),
        )
        for label, kind, mutate, failure in tamper_cases:
            with self.subTest(tamper=label):
                candidate = _v3_raw_record(kind)
                mutate(candidate)
                evaluation = _task037b_v3_evaluate_record(candidate)
                self.assertFalse(
                    _task037b_v3_numerical_pass(candidate, require_numerical_pass=False)
                )
                self.assertIn(failure, evaluation["failures"])
        for peak, resource_positive, engineering_positive, stretch_positive in (
            (6.0 * 1024.0, True, False, False),
            (5.0 * 1024.0, True, True, False),
            (3.77 * 1024.0, True, True, True),
        ):
            classified = _task037b_v3_resource_classification(peak)
            self.assertEqual(classified["resource_positive"], resource_positive)
            self.assertEqual(classified["engineering_positive"], engineering_positive)
            self.assertEqual(classified["stretch_positive"], stretch_positive)
        self.assertTrue(
            _task037b_v3_resource_classification(None)["measurement_failure"]
        )
        self.assertTrue(
            _task037b_v3_resource_classification(-1.0)["measurement_failure"]
        )
        pass_disposition = _task037b_v3_evaluate_record(passed)["disposition"]
        resource_negative = _task037b_v3_resource_classification(6.5 * 1024.0)
        self.assertTrue(resource_negative["resource_review"])
        self.assertEqual(
            _task037b_v3_evaluate_record(passed)["disposition"],
            pass_disposition,
        )
        terminal = _v3_raw_record("negative")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "solver_record.json"
            path.write_text(json.dumps(terminal), encoding="utf-8")
            self.assertTrue(_task034_terminal_record_is_complete(path))


if __name__ == "__main__":
    unittest.main()
