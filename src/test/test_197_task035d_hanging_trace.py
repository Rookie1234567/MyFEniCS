from __future__ import annotations

import numpy as np
import pytest

from src.adaptivity.hcurl_hanging_trace import (
    build_hanging_face_reference_pair,
    build_hexa_face_trace_pair,
    build_oriented_hanging_face_reference_catalog,
    build_oriented_quad_child_trace_restriction,
    build_quad_child_trace_restriction,
    build_quad_d4_trace_transform_pair,
    random_hanging_static_condensation_audit,
)
from src.constraints.high_order_floquet_trace import (
    quadrilateral_d4_vertex_permutations,
)


def test_p4_unique_hanging_face_restriction_matches_frozen_authority() -> None:
    pair = build_hanging_face_reference_pair(4)
    assert pair.audit["pass"] is True
    assert pair.hcurl_unique_fine_from_coarse.shape == (144, 40)
    assert pair.h1_unique_fine_from_coarse.shape == (81, 25)
    assert pair.audit["hcurl_restriction_rank"] == 40
    assert pair.audit["hcurl_restriction_condition_number"] == pytest.approx(
        38.92351207014342,
        rel=1.0e-12,
    )
    assert pair.audit["shared_child_hcurl_row_mismatch"] == 0.0
    assert pair.audit["maximum_child_commuting_error"] <= 5.0e-11
    assert pair.audit["unique_commuting_error"] <= 5.0e-11
    assert pair.audit["fine_discrete_gradient_rank"] == 80
    assert pair.audit["curl_grad_maximum_error"] <= 2.0e-10
    assert pair.audit["hcurl_restriction_sha256"] == (
        "7c1a37b9f99da5ba01015257afa712d427457eaee1dabb6ff36e6ac62ac14e2b"
    )


@pytest.mark.parametrize(
    ("degree", "hcurl_shape", "h1_shape", "expected_condition"),
    (
        (5, (220, 60), (121, 36), 78.09837549420138),
        (6, (312, 84), (169, 49), 76.34554119256732),
    ),
)
def test_p5_p6_reference_maps_remain_full_rank_and_commuting(
    degree: int,
    hcurl_shape: tuple[int, int],
    h1_shape: tuple[int, int],
    expected_condition: float,
) -> None:
    pair = build_hanging_face_reference_pair(degree)
    assert pair.audit["pass"] is True
    assert pair.hcurl_unique_fine_from_coarse.shape == hcurl_shape
    assert pair.h1_unique_fine_from_coarse.shape == h1_shape
    assert pair.audit["hcurl_restriction_rank"] == hcurl_shape[1]
    assert pair.audit["hcurl_restriction_condition_number"] == pytest.approx(
        expected_condition,
        rel=1.0e-12,
    )
    assert pair.audit["unique_commuting_error"] <= 5.0e-11


def test_covariant_piola_factor_is_required_for_commuting() -> None:
    pair = build_hanging_face_reference_pair(4)
    child = build_quad_child_trace_restriction(4, (1, 1))
    missing_j_transpose = 2.0 * child.hcurl_from_parent
    error = np.max(
        np.abs(
            missing_j_transpose @ pair.coarse_discrete_gradient
            - pair.coarse_discrete_gradient @ child.h1_from_parent
        )
    )
    assert error > 1.0e-2


def test_random_static_condensation_commutes_with_hanging_elimination() -> None:
    audit = random_hanging_static_condensation_audit(
        build_hanging_face_reference_pair(4),
        seed=350197,
    )
    assert audit["pass"] is True
    assert audit["unique_fine_patch_trace_rows"] == 144
    assert audit["independent_coarse_trace_rows"] == 40
    assert audit["hanging_constraint_slave_rows"] == 144
    assert audit["fine_patch_coordinate_excess_over_coarse"] == 104
    assert audit["relative_schur_error"] <= 2.0e-12
    assert audit["hermitian_error"] <= 2.0e-12
    assert audit["stationarity_residual"] <= 2.0e-12


def test_hanging_reference_input_fails_closed() -> None:
    with pytest.raises(ValueError, match="p4/p5/p6"):
        build_hanging_face_reference_pair(3)
    with pytest.raises(ValueError, match="quadrant"):
        build_quad_child_trace_restriction(4, (2, 0))


@pytest.mark.parametrize("degree", (4, 5, 6))
def test_all_hexa_face_trace_charts_are_isomorphisms_and_commute(
    degree: int,
) -> None:
    expected = (
        (2, 0, (0, 1)),
        (1, 0, (0, 2)),
        (0, 0, (1, 2)),
        (0, 1, (1, 2)),
        (1, 1, (0, 2)),
        (2, 1, (0, 1)),
    )
    rows = tuple(
        build_hexa_face_trace_pair(degree, local_face)
        for local_face in range(6)
    )
    assert tuple(
        (row.normal_axis, row.side, row.tangential_axes)
        for row in rows
    ) == expected
    assert all(row.audit["pass"] is True for row in rows)
    assert all(
        row.audit["gradient_commuting_error"] <= 5.0e-11
        for row in rows
    )


@pytest.mark.parametrize("degree", (4, 5, 6))
def test_complete_quad_d4_transforms_match_task033_and_commute(
    degree: int,
) -> None:
    permutations = tuple(
        sorted(quadrilateral_d4_vertex_permutations())
    )
    rows = tuple(
        build_quad_d4_trace_transform_pair(degree, permutation)
        for permutation in permutations
    )
    assert len(rows) == 8
    assert len({row.audit["hcurl_sha256"] for row in rows}) == 8
    assert all(row.audit["pass"] is True for row in rows)
    assert max(
        row.audit["task033_block_mismatch"] for row in rows
    ) <= 5.0e-12
    assert max(
        row.audit["gradient_commuting_error"] for row in rows
    ) <= 5.0e-11


@pytest.mark.parametrize("degree", (4, 5, 6))
def test_all_oriented_child_combinations_pass_catalog(
    degree: int,
) -> None:
    audit = build_oriented_hanging_face_reference_catalog(degree)
    assert audit["pass"] is True
    assert audit["hexa_face_count"] == 6
    assert audit["d4_permutation_count"] == 8
    assert audit["oriented_child_combination_count"] == 256
    assert audit["maximum_oriented_child_commuting_error"] <= 5.0e-11
    assert audit["maximum_d4_condition_relative_drift"] <= 1.0e-7


def test_oriented_child_and_non_d4_inputs_fail_closed() -> None:
    permutations = tuple(
        sorted(quadrilateral_d4_vertex_permutations())
    )
    row = build_oriented_quad_child_trace_restriction(
        4,
        (1, 0),
        permutations[3],
        permutations[6],
    )
    assert row.audit["pass"] is True
    assert row.audit["commuting_error"] <= 5.0e-11
    with pytest.raises(ValueError, match="D4"):
        build_quad_d4_trace_transform_pair(4, (0, 1, 3, 2))
    with pytest.raises(ValueError, match="local face"):
        build_hexa_face_trace_pair(4, 6)
