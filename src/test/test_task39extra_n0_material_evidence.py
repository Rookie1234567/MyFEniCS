"""Pure metadata fixtures, without constructing any FE mesh or operator."""

from itertools import pairwise

import numpy as np
import pytest

from src.runners.n0_port_material_evidence import _y_column_evidence


def _metadata():
    y = [-2.0, -0.5, 0.75, 1.5]
    bounds, tags = [], []
    for x in (0.0, 2.0):
        for z in (0.0, 3.0):
            for low, high in pairwise(y):
                bounds.append([x, x + 1, low, high, z, z + 2])
                tags.append(1 if x == 0 else 2)
    return np.asarray(bounds), np.asarray(tags, dtype=np.int32)


def _check(bounds, tags):
    return _y_column_evidence(bounds, tags, y_min=-2.0, y_max=1.5, y_slabs=3)


def test_actual_y_columns_work_with_nonuniform_slabs_and_permuted_cell_order():
    bounds, tags = _metadata()
    permutation = [10, 2, 4, 9, 1, 3, 8, 7, 0, 6, 11, 5]
    facts = _check(bounds[permutation], tags[permutation])
    assert facts["actual_cell_count"] == 12
    assert facts["actual_xz_column_count"] == 4
    assert facts["actual_y_slabs_per_column"] == 3
    assert facts["actual_cell_tag_counts"] == {"1": 6, "2": 6}
    assert facts["actual_tags_constant_along_y"]
    assert facts["raw_xz_column_y_coverage_exact"]
    assert not facts["geometry_rounding_applied"]


def test_material_change_in_one_actual_y_cell_is_rejected():
    bounds, tags = _metadata()
    tags[1] = 2
    with pytest.raises(ValueError, match="vary along a y column"):
        _check(bounds, tags)


@pytest.mark.parametrize("fault", ["gap", "overlap", "column_coverage", "missing_cell"])
def test_actual_y_coverage_faults_are_rejected(fault):
    bounds, tags = _metadata()
    if fault == "gap":
        bounds[1::3, 2] += 0.01
    elif fault == "overlap":
        bounds[1::3, 2] -= 0.01
    elif fault == "column_coverage":
        bounds[0, 2] += 0.01
    else:
        bounds, tags = bounds[:-1], tags[:-1]
    with pytest.raises(ValueError, match="y slabs"):
        _check(bounds, tags)


def test_raw_geometry_is_not_rounded_to_make_columns_match():
    bounds, tags = _metadata()
    bounds[0, 0] = np.nextafter(bounds[0, 0], 1.0)
    with pytest.raises(ValueError, match="required y slabs"):
        _check(bounds, tags)
