from __future__ import annotations

import itertools

import pytest

from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)


def _tensor_boxes(
    nx: int,
    ny: int,
    nz: int,
) -> list[tuple[float, float, float, float, float, float]]:
    return [
        (
            float(i),
            float(j),
            float(k),
            float(i + 1),
            float(j + 1),
            float(k + 1),
        )
        for k in range(nz)
        for j in range(ny)
        for i in range(nx)
    ]


def _root(nx: int, i: int, j: int, k: int = 0) -> int:
    return k * nx * nx + j * nx + i


def _touches(
    left: tuple[float, ...],
    right: tuple[float, ...],
    tolerance: float = 1.0e-12,
) -> bool:
    separated = any(
        left[axis + 3] < right[axis] - tolerance
        or right[axis + 3] < left[axis] - tolerance
        for axis in range(3)
    )
    if separated:
        return False
    positive = sum(
        min(left[axis + 3], right[axis + 3])
        - max(left[axis], right[axis])
        > tolerance
        for axis in range(3)
    )
    return positive < 3


def test_single_split_is_true_local_and_catalogs_one_hanging_face() -> None:
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [1, 1],
        periodic_axes=(),
    )
    refined = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    assert refined.audit["pass"] is True
    assert len(refined.leaves) == 9
    assert refined.audit["leaf_level_counts"] == {"0": 1, "1": 8}
    assert refined.audit["hanging_face_count"] == 1
    assert refined.audit["hanging_fine_face_count"] == 4
    patch = refined.hanging_faces[0]
    assert patch.coarse.root == 1
    assert patch.axis == 0
    assert patch.side == 0
    assert patch.child_offsets == ((0, 0), (0, 1), (1, 0), (1, 1))

    unique = [
        sorted({cell.box[axis] for cell in refined.leaves}
               | {cell.box[axis + 3] for cell in refined.leaves})
        for axis in range(3)
    ]
    global_plane_cell_count = (
        (len(unique[0]) - 1)
        * (len(unique[1]) - 1)
        * (len(unique[2]) - 1)
    )
    assert global_plane_cell_count == 12
    assert len(refined.leaves) < global_plane_cell_count
    assert sum(
        (cell.box[3] - cell.box[0])
        * (cell.box[4] - cell.box[1])
        * (cell.box[5] - cell.box[2])
        for cell in refined.leaves
    ) == pytest.approx(2.0)


def test_level_two_mark_reaches_all_touch_strong_two_to_one_fixed_point() -> None:
    boxes = _tensor_boxes(3, 3, 3)
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=(),
    )
    center = 1 * 9 + 1 * 3 + 1
    level_one = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(center, 0, 0, 0, 0)],
        maximum_level=2,
    )
    level_two = refine_balanced_dyadic_hexa_forest(
        level_one,
        [DyadicHexKey(center, 1, 0, 0, 0)],
        maximum_level=2,
    )
    assert level_two.audit["pass"] is True
    assert level_two.audit["balance_touch_class"] == "face_edge_vertex"
    assert level_two.audit["maximum_adjacent_level_jump"] <= 1
    assert level_two.audit["closure_split_counts"]["balance"] > 0
    for left, right in itertools.combinations(level_two.leaves, 2):
        if _touches(left.box, right.box):
            assert abs(left.key.level - right.key.level) <= 1

    with pytest.raises(ValueError, match="maximum level"):
        refine_balanced_dyadic_hexa_forest(
            level_one,
            [DyadicHexKey(center, 1, 0, 0, 0)],
            maximum_level=1,
        )


def test_xy_corner_periodic_mark_closes_four_root_orbit() -> None:
    boxes = _tensor_boxes(3, 3, 1)
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=("x", "y"),
    )
    refined = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    assert len(refined.leaves) == 37
    refined_roots = {
        cell.key.root for cell in refined.leaves if cell.key.level == 1
    }
    assert refined_roots == {0, 2, 6, 8}
    assert refined.audit["closure_split_counts"]["periodic"] == 3
    for axis in ("x", "y"):
        row = refined.audit["periodic_boundary_audit"][axis]
        assert row["matching"] is True
        assert row["lower_patch_count"] == row["upper_patch_count"]
        assert row["lower_sha256"] == row["upper_sha256"]


def test_material_interface_refinement_is_conforming_and_tags_are_inherited() -> None:
    forest = build_root_dyadic_hexa_forest(
        _tensor_boxes(2, 1, 1),
        [11, 22],
        periodic_axes=(),
        protect_material_interfaces=True,
    )
    refined = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    assert len(refined.leaves) == 16
    assert refined.audit["closure_split_counts"]["material"] == 1
    assert refined.audit["material_interface_hanging_face_count"] == 0
    assert {
        cell.material_tag
        for cell in refined.leaves
        if cell.key.root == 0
    } == {11}
    assert {
        cell.material_tag
        for cell in refined.leaves
        if cell.key.root == 1
    } == {22}


def test_invalid_mark_and_duplicate_root_geometry_fail_closed() -> None:
    boxes = _tensor_boxes(2, 1, 1)
    with pytest.raises(ValueError, match="unique"):
        build_root_dyadic_hexa_forest(
            [boxes[0], boxes[0]],
            [1, 1],
            periodic_axes=(),
        )
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1, 1],
        periodic_axes=(),
    )
    with pytest.raises(ValueError, match="not current leaves"):
        refine_balanced_dyadic_hexa_forest(
            forest,
            [DyadicHexKey(0, 1, 0, 0, 0)],
        )
