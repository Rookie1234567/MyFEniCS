from __future__ import annotations

import numpy as np
import pytest

from src.postprocessing.task40_saved_field_h_comparison import (
    direct_curl_dg,
    _partition_mesh_exterior_surfaces,
    structured_cell_grid,
    union_axis_points,
    weighted_vector_squared_norm,
)


def test_common_axis_union_preserves_distinct_nearby_coordinates():
    union, facts = union_axis_points(
        np.asarray([0.0, 1.0, 2.0]),
        np.asarray([0.0, 1.0 + 5.0e-13, 1.5, 2.0]),
    )

    assert np.array_equal(union, [0.0, 1.0, 1.0 + 5.0e-13, 1.5, 2.0])
    assert facts["exact_duplicate_count"] == 2
    assert facts["near_distinct_gap_count_below_diagnostic_tolerance"] == 1


def test_common_axis_union_preserves_a_real_tiny_source_cell():
    union, _ = union_axis_points(
        np.asarray([0.0, 5.0e-13, 1.0]),
        np.asarray([0.0, 1.0]),
    )
    assert np.array_equal(union, [0.0, 5.0e-13, 1.0])


def test_weighted_vector_norm_uses_one_weight_per_vector_sample():
    values = np.asarray([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]])
    weights = np.asarray([2.0, 3.0])

    assert weighted_vector_squared_norm(values, weights) == pytest.approx(14.0)
    assert weighted_vector_squared_norm(values[1:] - values[:1], weights[1:]) == pytest.approx(15.0)


def test_structured_cell_grid_maps_midpoints_without_geometry_collision_tolerance():
    axes = (
        np.asarray([0.0, 1.0, 2.0]),
        np.asarray([0.0, 1.0]),
        np.asarray([0.0, 1.0, 2.0, 3.0]),
    )
    keys = [(1, 0, 2), (0, 0, 1), (1, 0, 0), (0, 0, 2), (1, 0, 1), (0, 0, 0)]
    midpoints = np.asarray(
        [
            [
                0.5 * (axes[0][i] + axes[0][i + 1]),
                0.5,
                0.5 * (axes[2][k] + axes[2][k + 1]),
            ]
            for i, _j, k in keys
        ]
    )

    grid = structured_cell_grid(axes, midpoints)

    for cell, (i, j, k) in enumerate(keys):
        assert grid[i, j, k] == cell


def test_material_trace_partition_skips_only_exact_shared_domain_exteriors():
    axes0 = (
        np.asarray([0.0, 0.5, 1.0]),
        np.asarray([0.0, 0.5, 1.0]),
        np.asarray([-1.0, 0.0, 1.0]),
    )
    axes1 = tuple(axis.copy() for axis in axes0)
    surfaces = [
        {"axis_index": 1, "coordinate_nm": 0.0, "names": ["grating_y_min"]},
        {"axis_index": 2, "coordinate_nm": 0.0, "names": ["interior_z_face"]},
    ]

    interior, exterior = _partition_mesh_exterior_surfaces(surfaces, axes0, axes1)

    assert [item["names"] for item in interior] == [["interior_z_face"]]
    assert len(exterior) == 1
    assert exterior[0]["plane_names"] == ["grating_y_min"]
    assert exterior[0]["reason"].startswith("mesh exterior")


def test_direct_ufl_curl_fixture_covers_complex_p6_hexa_polynomial():
    from dolfinx import fem, mesh
    from mpi4py import MPI
    import ufl

    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(domain, ("N1curl", 6))
    electric = fem.Function(space, name="known_E")
    x = ufl.SpatialCoordinate(domain)
    coefficient = 1.0 + 0.3j
    expression = ufl.as_vector((0.0 * x[0], 0.0 * x[0], coefficient * x[0] ** 6 * x[1]))
    points = space.element.interpolation_points
    if callable(points):
        points = points()
    electric.interpolate(fem.Expression(expression, points))
    electric.x.scatter_forward()

    curl = direct_curl_dg(electric, degree=6)
    locations = np.asarray(
        [[0.37, 0.41, 0.59], [0.71, 0.29, 0.13]], dtype=np.float64
    )
    values = np.asarray(curl.eval(locations, np.asarray([0, 0], dtype=np.int32))).reshape((-1, 3))
    expected = np.column_stack(
        (
            coefficient * locations[:, 0] ** 6,
            -6.0 * coefficient * locations[:, 0] ** 5 * locations[:, 1],
            np.zeros(len(locations), dtype=np.complex128),
        )
    )

    np.testing.assert_allclose(values, expected, rtol=0.0, atol=2.0e-11)
