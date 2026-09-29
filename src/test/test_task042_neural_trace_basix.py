"""Basix-only moment qualification; no mesh, physical operator or FE solve."""

import basix
import numpy as np
import pytest

from src.solvers.neural_trace_dolfinx import extended_moment_element


@pytest.mark.parametrize("quadrature", [15, 30])
def test_full_p3_moments_keep_the_original_space_and_all_higher_dofs(quadrature):
    original = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        3,
        basix.LagrangeVariant.legendre,
    )
    extended = extended_moment_element(original, quadrature)
    assert original.dim == extended.dim == 144
    assert original.entity_dofs == extended.entity_dofs
    assert sum(len(dofs) for dofs in extended.entity_dofs[1]) == 36
    assert sum(len(dofs) for dofs in extended.entity_dofs[2]) == 72
    points = np.random.default_rng(420906).random((23, 3))
    assert (
        np.linalg.norm(original.tabulate(0, points) - extended.tabulate(0, points))
        / np.linalg.norm(original.tabulate(0, points))
        <= 1e-10
    )
    # Independent basis values -> upgraded full moments reproduce ALL 144 DOFs.
    values = original.tabulate(0, extended.points)[0]
    interpolation = extended.interpolation_matrix @ values.transpose(2, 0, 1).reshape(
        -1, 144
    )
    assert np.linalg.norm(interpolation - np.eye(144)) <= 1e-10
