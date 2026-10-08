from __future__ import annotations

from math import pi
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.task40_p6_support_bounds import (
    assign_ordered_modes_to_q,
    derive_p6_q_csr_bounds,
    p6_periodic_topology_counts,
    support_bounds_from_native_calibration,
)


def _native_calibration(ny: int = 4) -> dict:
    return {
        "cell_permutation_codes": [0, 32769],
        "native_q_cell_support_scan": {
            "mesh_cell_axes": [8, ny, 7],
            "all_xz_representatives_covered": True,
            "every_y_layer_covered_for_each_xz_representative": True,
            "all_folded_cell_trace_supports_within_432_local_channels": True,
            "maximum_folded_cell_trace_support_size": 348,
            "periodic_x_boundary_support_rule": {
                "all_periodic_x_faces_verified_from_native_entity_slots": True,
                "observed_union_fits_conservative_formula_on_both_faces": True,
                "face_entity_dofs_per_face_for_reference": 60,
            },
        },
    }


def _side_counts(port_counts: list[int]) -> list[dict[str, int]]:
    return [{"top": count // 2, "bottom": count - count // 2} for count in port_counts]


def test_ny4_target_augmented_rows_use_condensed_trace_rows() -> None:
    topology = p6_periodic_topology_counts(272, 4, 14)
    assert topology["full_storage_rows"] == 10_228_620
    assert topology["periodic_independent_rows"] == 9_948_672
    assert topology["q_spatial_rows"] == 2_487_168
    assert topology["q_trace_rows"] == 773_568

    result = derive_p6_q_csr_bounds(
        topology,
        [
            {"top": 3966, "bottom": 3966},
            {"top": 4018, "bottom": 4018},
            {"top": 4028, "bottom": 4028},
            {"top": 4018, "bottom": 4018},
        ],
        folded_cell_trace_support_upper=348,
        boundary_trace_support_upper_per_face=272 * (348 - 60),
        evidence_classification="fixture",
    )
    assert [row["augmented_rows_columns"] for row in result["q_matrices"]] == [
        781_500,
        781_604,
        781_624,
        781_604,
    ]
    assert all(row["interior_rows_eliminated_per_q"] == 1_713_600 for row in result["q_matrices"])


def test_b0_ny8_zero_port_q_keeps_trace_rows_and_rejects_unknown_sides() -> None:
    topology = p6_periodic_topology_counts(4, 8, 5)
    assert topology["q_trace_rows"] == 4248
    assert topology["q_spatial_rows"] == 13_248
    result = derive_p6_q_csr_bounds(
        topology,
        _side_counts([76, 76, 76, 76, 0, 76, 76, 76]),
        folded_cell_trace_support_upper=432,
        boundary_trace_support_upper_per_face=4 * 432,
        evidence_classification="fixture",
    )
    assert [row["augmented_rows_columns"] for row in result["q_matrices"]] == [
        4324,
        4324,
        4324,
        4324,
        4248,
        4324,
        4324,
        4324,
    ]
    assert result["q_matrices"][4]["port_rows_columns"] == 0
    assert result["q_matrices"][4]["augmented_rows_columns"] == topology["q_trace_rows"]

    invalid = [{"top": 1, "bottom": 0, "unclassified": 2}] + [
        {"top": 0, "bottom": 0}
    ] * 7
    with pytest.raises(ValueError, match="only top and bottom"):
        derive_p6_q_csr_bounds(
            topology,
            invalid,
            folded_cell_trace_support_upper=432,
            boundary_trace_support_upper_per_face=4 * 432,
            evidence_classification="fixture",
        )


def test_ny8_does_not_inherit_ny4_measured_support() -> None:
    result = support_bounds_from_native_calibration(
        (272, 8, 14),
        (0, 32769),
        _native_calibration(ny=4),
    )
    assert result["folded_cell_trace_support_upper"] == 432
    assert result["boundary_trace_support_upper_per_face"] == 272 * 432
    assert result["same_Ny_calibration"] is False
    assert result["boundary_support_refined"] is False
    assert "calibration_Ny_does_not_match_target" in result["fallback_reasons"]
    assert "periodic_x_boundary_rule_not_transferable_to_target" in result["fallback_reasons"]


def test_matching_ny_and_map_coverage_can_use_calibration_bound() -> None:
    result = support_bounds_from_native_calibration(
        (272, 4, 14),
        (0, 32769),
        _native_calibration(ny=4),
    )
    assert result["folded_cell_trace_support_upper"] == 348
    assert result["boundary_trace_support_upper_per_face"] == 272 * 288
    assert result["boundary_support_refined"] is True
    assert result["fallback_reasons"] == []


def test_original_size_ny8_q_inventory_has_conservative_structural_bounds() -> None:
    topology = p6_periodic_topology_counts(272, 8, 14)
    assert topology["full_storage_rows"] == 20_181_348
    assert topology["periodic_independent_rows"] == 19_897_344
    assert topology["q_trace_rows"] == 773_568
    q_counts = [4076, 4052, 4028, 3984, 3856, 3984, 4028, 4052]
    result = derive_p6_q_csr_bounds(
        topology,
        _side_counts(q_counts),
        folded_cell_trace_support_upper=432,
        boundary_trace_support_upper_per_face=272 * 432,
        evidence_classification="derived_from_saved_manifest_and_conservative_full_trace_fallback",
    )
    assert [row["augmented_rows_columns"] for row in result["q_matrices"]] == [
        777_644,
        777_620,
        777_596,
        777_552,
        777_424,
        777_552,
        777_596,
        777_620,
    ]
    assert [
        row["structural_nnz_upper_bound"] for row in result["q_matrices"]
    ] == [
        1_685_170_576,
        1_679_335_312,
        1_673_501_200,
        1_662_808_320,
        1_631_723_776,
        1_662_808_320,
        1_673_501_200,
        1_679_335_312,
    ]
    assert result["q_count_distinct_payload_upper_bytes"] == 266_988_562_768
    assert result["all_q_structural_upper_bounds_fit_int32"] is True


def test_production_mapper_preserves_empty_q_and_rejects_missing_side() -> None:
    ny = 8
    period_y = 25.0
    dy = period_y / ny
    q_values = [0, 1, 2, 3, 5, 6, 7]
    modes = [
        SimpleNamespace(
            gamma=complex(2 * pi * q / (ny * dy)),
            mode_key=f"mode-{q}",
            side="top" if q % 2 == 0 else "bottom",
        )
        for q in q_values
    ]
    result = assign_ordered_modes_to_q(
        modes,
        SimpleNamespace(ky=0.0, period_y=period_y),
        {
            "x": (0.0, 50.0),
            "y": tuple(np.linspace(0.0, period_y, ny + 1)),
            "z": (-10.0, 130.0),
        },
    )
    assert result["q_counts"] == [1, 1, 1, 1, 0, 1, 1, 1]
    assert result["q_side_counts"][4] == {"top": 0, "bottom": 0}
    assert result["all_modes_assigned_once"] is True

    modes[0].side = "sideways"
    with pytest.raises(ValueError, match="unknown or missing side"):
        assign_ordered_modes_to_q(
            modes,
            SimpleNamespace(ky=0.0, period_y=period_y),
            {
                "x": (0.0, 50.0),
                "y": tuple(np.linspace(0.0, period_y, ny + 1)),
                "z": (-10.0, 130.0),
            },
        )



def test_int32_overflow_is_reported_without_truncation() -> None:
    topology = p6_periodic_topology_counts(107, 2, 108)
    result = derive_p6_q_csr_bounds(
        topology,
        [{"top": 0, "bottom": 0}, {"top": 0, "bottom": 0}],
        folded_cell_trace_support_upper=432,
        boundary_trace_support_upper_per_face=107 * 432,
        evidence_classification="overflow_fixture",
    )
    first = result["q_matrices"][0]
    assert first["structural_nnz_upper_bound"] > 2**31 - 1
    assert first["maximum_intermediate_csr_offset_upper"] == (
        first["structural_nnz_upper_bound"] - 1
    )
    assert first["int32_safe_for_shape_nnz_offsets_and_row_support"] is False
    assert result["all_q_structural_upper_bounds_fit_int32"] is False
