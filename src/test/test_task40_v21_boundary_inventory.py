from __future__ import annotations

import numpy as np
import pytest

from src.geometry.task40_v21_boundary_inventory import map_boundary_facet_rows


def _vertices(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> np.ndarray:
    return np.asarray(
        [
            [x0, y0, z0],
            [x1, y0, z0],
            [x0, y1, z0],
            [x1, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x0, y1, z1],
            [x1, y1, z1],
        ],
        dtype=np.float64,
    )


def _class(class_id: str, tag: int, widths: tuple[float, float, float], permutation: int) -> dict:
    return {
        "class_id": class_id,
        "material_tag": tag,
        "cell_widths_nm": list(widths),
        "cell_permutation": permutation,
        "metric_identity": {
            "cell_widths_float_hex": [float(value).hex() for value in widths],
            "cell_permutation": permutation,
        },
    }


def _facet(side: str, facet_id: int, cell_id: int, center: list[float]) -> dict:
    z = -2.0 if side == "bottom" else 6.0
    return {
        "side": side,
        "facet_id": facet_id,
        "adjacent_cell_ids": [cell_id],
        "projected_center_nm": center,
        "actual_center_nm": [center[0], center[1], z],
    }


def _map(facets: list[dict], *, material_tags: dict[int, int] | None = None) -> dict:
    return map_boundary_facet_rows(
        facets,
        cell_vertices={
            20: _vertices(0.0, 0.5, 0.0, 1.0, -2.0, 0.0),
            31: _vertices(1.0, 1.5, 2.0, 3.0, 4.0, 6.0),
        },
        cell_permutations={20: 7, 31: 11},
        cell_material_tags=material_tags or {20: 2, 31: 1},
        side_boundary_z_nm={"bottom": -2.0, "top": 6.0},
        saved_classes=[
            _class("c00", 2, (0.5, 1.0, 2.0), 7),
            _class("c01", 1, (0.5, 1.0, 2.0), 11),
        ],
    )


def test_maps_facets_to_exact_classes_and_counts_after_center_check() -> None:
    result = _map(
        [
            _facet("bottom", 4, 20, [0.25, 0.5]),
            _facet("top", 9, 31, [1.25, 2.5]),
        ]
    )
    mapped = result["facet_mappings"]
    assert [(row["side"], row["facet_id"], row["cell_id"], row["class_id"]) for row in mapped] == [
        ("bottom", 4, 20, "c00"),
        ("top", 9, 31, "c01"),
    ]
    assert result["facet_count_by_side"] == {"bottom": 1, "top": 1}
    assert result["unique_cell_count_by_side"] == {"bottom": 1, "top": 1}
    assert result["class_facet_count_by_side"] == {
        "bottom": {"c00": 1},
        "top": {"c01": 1},
    }


def test_rejects_facet_when_saved_and_readback_centers_differ() -> None:
    facet = _facet("bottom", 4, 20, [0.25, 0.5])
    facet["actual_center_nm"] = [0.25, 0.5000001, -2.0]
    with pytest.raises(ValueError, match="center differs"):
        _map([facet])


def test_rejects_facet_when_reconstructed_material_tag_is_wrong() -> None:
    with pytest.raises(ValueError, match="no saved class"):
        _map([_facet("bottom", 4, 20, [0.25, 0.5])], material_tags={20: 1, 31: 1})


@pytest.mark.parametrize("adjacent", [[], [20, 21]])
def test_rejects_facet_without_one_real_adjacent_cell(adjacent: list[int]) -> None:
    facet = _facet("bottom", 4, 20, [0.25, 0.5])
    facet["adjacent_cell_ids"] = adjacent
    with pytest.raises(ValueError, match="exactly one adjacent cell"):
        _map([facet])
