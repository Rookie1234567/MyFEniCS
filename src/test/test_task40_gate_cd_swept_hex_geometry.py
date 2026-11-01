from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from src.geometry.swept_hex_mesh import (
    _remap_input_cell_tags,
    build_swept_hex_mesh,
)
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_swept_hex_coordinates,
    _trilinear_hex_jacobian_determinants,
    build_unconstrained_assembly_time_condensation,
)


def _cell_map(coords: np.ndarray):
    return SimpleNamespace(
        geometry=SimpleNamespace(
            dofmap=np.asarray([np.arange(8, dtype=np.int32)]),
            x=np.asarray(coords, dtype=np.float64),
            cmap=SimpleNamespace(degree=1),
        )
    )


def _swept_cell(*, x_slope: float = 0.0, y_slope: float = 0.0, shift=0.0):
    x0 = np.asarray((0.0, 1.0)) + shift
    y0 = np.asarray((0.0, 1.0)) + shift
    x1 = np.asarray((0.0, 1.0 + x_slope)) + shift
    y1 = np.asarray((0.0, 1.0 + y_slope)) + shift
    z0, z1 = 0.0 + shift, 1.0 + shift
    return np.asarray(
        [
            (x0[0], y0[0], z0),
            (x0[1], y0[0], z0),
            (x0[0], y0[1], z0),
            (x0[1], y0[1], z0),
            (x1[0], y1[0], z1),
            (x1[1], y1[0], z1),
            (x1[0], y1[1], z1),
            (x1[1], y1[1], z1),
        ],
        dtype=np.float64,
    )


def _real_swept_mesh():
    z = np.asarray((0.0, 1.0, 2.0))
    x = np.asarray(((0.0, 1.0, 2.0), (0.0, 0.9, 2.0), (0.0, 0.8, 2.0)))
    y = np.asarray(((0.0, 1.0, 2.0), (0.0, 1.1, 2.0), (0.0, 1.2, 2.0)))
    return build_swept_hex_mesh(
        MPI.COMM_SELF,
        z,
        x,
        y,
        cell_tags=np.ones(8, dtype=np.int32),
        require_periodic_xy=True,
    )


def test_explicit_swept_builder_uses_reference_vertex_order_and_jacobian():
    msh, tags = _real_swept_mesh()
    assert tags is not None
    assert tags.values.tolist() == [1] * 8
    assert int(msh.topology.index_map(3).size_local) == 8
    coordinates = msh.geometry.x[msh.geometry.dofmap[0]]
    canonical, identity, facts = _canonical_swept_hex_coordinates(
        msh,
        0,
        tolerance=1.0e-12,
        translation_invariant_form=False,
    )
    np.testing.assert_array_equal(canonical.reshape(8, 3), coordinates)
    assert len(identity) == 24
    assert facts["min_detJ_analytic"] > 0.0
    assert facts["min_detJ_sampled"] == pytest.approx(
        facts["min_detJ_analytic"], rel=5.0e-13
    )


def test_exact_geometry_key_distinguishes_same_bbox_different_slope():
    first_geometry = np.asarray(
        [
            (0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
            (0.1, 0.1, 1), (0.9, 0.1, 1), (0.1, 0.9, 1), (0.9, 0.9, 1),
        ], dtype=np.float64
    )
    second_geometry = np.asarray(
        [
            (0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
            (0.2, 0.2, 1), (0.8, 0.2, 1), (0.2, 0.8, 1), (0.8, 0.8, 1),
        ], dtype=np.float64
    )
    first = _cell_map(first_geometry)
    second = _cell_map(second_geometry)
    first_key = _canonical_swept_hex_coordinates(
        first, 0, tolerance=1.0e-12, translation_invariant_form=False
    )[1]
    second_key = _canonical_swept_hex_coordinates(
        second, 0, tolerance=1.0e-12, translation_invariant_form=False
    )[1]
    assert first_key != second_key
    # Both boxes have the same bounding box.  The slope is still retained.
    np.testing.assert_array_equal(
        np.ptp(first_geometry, axis=0),
        np.ptp(second_geometry, axis=0),
    )


def test_translation_is_removed_only_after_explicit_invariance_assertion():
    # Binary-exact increments make this an exact translation test, not an
    # accidental probe of floating-point subtraction after decimal addition.
    first = _cell_map(_swept_cell(x_slope=0.125, y_slope=0.25))
    translated = _cell_map(
        _swept_cell(x_slope=0.125, y_slope=0.25, shift=8.0)
    )
    first_exact = _canonical_swept_hex_coordinates(
        first, 0, tolerance=1.0e-12, translation_invariant_form=False
    )[1]
    translated_exact = _canonical_swept_hex_coordinates(
        translated, 0, tolerance=1.0e-12, translation_invariant_form=False
    )[1]
    first_invariant = _canonical_swept_hex_coordinates(
        first, 0, tolerance=1.0e-12, translation_invariant_form=True
    )[1]
    translated_invariant = _canonical_swept_hex_coordinates(
        translated, 0, tolerance=1.0e-12, translation_invariant_form=True
    )[1]
    assert first_exact != translated_exact
    assert first_invariant == translated_invariant


@pytest.mark.parametrize(
    "coordinates",
    [
        # Folded z endpoint ordering.
        np.asarray(
            [
                (0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1),
            ], dtype=np.float64
        )[[0, 1, 2, 3, 7, 6, 5, 4]],
        # Same bounding box but a non-separable cross-section.
        np.asarray(
            [
                (0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                (0, 0, 1), (1, 0, 1), (0, 1, 1), (1.1, 1, 1),
            ], dtype=np.float64
        ),
        # Degenerate x width.
        np.asarray(
            [
                (0, 0, 0), (0, 0, 0), (0, 1, 0), (0, 1, 0),
                (0, 0, 1), (0, 0, 1), (0, 1, 1), (0, 1, 1),
            ], dtype=np.float64
        ),
    ],
)
def test_non_swept_or_degenerate_geometry_is_rejected(coordinates):
    with pytest.raises(ValueError):
        _canonical_swept_hex_coordinates(
            _cell_map(coordinates),
            0,
            tolerance=1.0e-12,
            translation_invariant_form=False,
        )


def test_translation_periodic_boundary_must_stay_fixed():
    with pytest.raises(ValueError, match="periodic x-min"):
        build_swept_hex_mesh(
            MPI.COMM_SELF,
            (0.0, 1.0),
            ((0.0, 1.0, 2.0), (0.1, 1.0, 2.1)),
            ((0.0, 1.0), (0.0, 1.0)),
            require_periodic_xy=True,
        )


def test_input_cell_tags_follow_exact_geometry_if_mesh_order_changes():
    points = np.asarray(
        [
            (x, y, z)
            for z in (0.0, 1.0)
            for y in (0.0, 1.0)
            for x in (0.0, 1.0, 2.0)
        ],
        dtype=np.float64,
    )

    def node(i, j, k):
        return k * 2 * 3 + j * 3 + i

    cells = np.asarray(
        [
            [node(0, 0, 0), node(1, 0, 0), node(0, 1, 0), node(1, 1, 0),
             node(0, 0, 1), node(1, 0, 1), node(0, 1, 1), node(1, 1, 1)],
            [node(1, 0, 0), node(2, 0, 0), node(1, 1, 0), node(2, 1, 0),
             node(1, 0, 1), node(2, 0, 1), node(1, 1, 1), node(2, 1, 1)],
        ],
        dtype=np.int64,
    )
    remapped = _remap_input_cell_tags(
        cells,
        points,
        np.asarray((7, 9), dtype=np.int32),
        (points[cells[1]], points[cells[0]]),
    )
    np.testing.assert_array_equal(remapped, (9, 7))


def test_jacobian_sample_helper_rejects_nonfinite_coordinates():
    coords = _swept_cell()
    coords[4, 0] = np.nan
    with pytest.raises(FloatingPointError):
        _trilinear_hex_jacobian_determinants(coords)


def test_translation_invariance_optin_cannot_leak_to_legacy_geometry_policies():
    with pytest.raises(ValueError, match="only valid with mapped_exact"):
        build_unconstrained_assembly_time_condensation(
            SimpleNamespace(dtype=np.dtype(np.complex128)),
            SimpleNamespace(),
            None,
            geometry_identity_policy="raw_unrounded",
            mapped_geometry_translation_invariant=True,
        )
