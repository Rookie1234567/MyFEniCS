from __future__ import annotations

import inspect

from mpi4py import MPI
import numpy as np

from dolfinx import default_real_type, fem, mesh
from basix.ufl import element

from src.adaptivity.task035e_goal_gradients import (
    _oriented_physical_basis,
    _point_owners,
)


def _space(domain: mesh.Mesh):
    return fem.functionspace(
        domain,
        element(
            "N1curl",
            domain.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )


def test_oriented_point_basis_matches_complex_function_eval() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [2, 1, max(1, comm.size)],
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    field = fem.Function(space)
    start = int(space.dofmap.index_map.local_range[0])
    rows = start + np.arange(len(field.x.array), dtype=float)
    field.x.array[:] = (
        np.cos(0.13 * (rows + 1.0))
        + 1j * np.sin(0.17 * (rows + 1.0))
    )
    field.x.scatter_forward()
    cell_count = domain.topology.index_map(domain.topology.dim).size_local
    assert cell_count > 0
    domain.topology.create_connectivity(domain.topology.dim, 0)
    cell = 0
    coordinates = domain.geometry.x[domain.geometry.dofmap[cell]]
    points = np.asarray(
        [
            0.25 * coordinates.min(axis=0)
            + 0.75 * coordinates.max(axis=0),
            0.65 * coordinates.min(axis=0)
            + 0.35 * coordinates.max(axis=0),
        ]
    )
    basis = _oriented_physical_basis(
        space,
        cell=cell,
        points=points,
    )
    coefficients = field.x.array[space.dofmap.cell_dofs(cell)]
    predicted = np.einsum("i,pic->pc", coefficients, basis)
    observed = np.asarray(
        field.eval(
            points,
            np.full(len(points), cell, dtype=np.int32),
        )
    ).reshape((-1, 3))
    np.testing.assert_allclose(predicted, observed, rtol=1e-13, atol=1e-13)


def test_point_owner_catalog_closes_in_mpi() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_unit_cube(
        comm,
        2,
        2,
        max(2, 2 * comm.size),
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    points = np.asarray(
        [
            [0.25, 0.25, 0.0],
            [0.75, 0.75, 0.5],
            [0.25, 0.75, 1.0],
        ],
        dtype=np.float64,
    )
    owners, cells, audit = _point_owners(
        space,
        points,
        np.asarray([1, 1, -1], dtype=np.int8),
    )
    assert owners.shape == (3,)
    assert cells.shape == (3,)
    assert np.all(owners >= 0)
    assert np.all(owners < comm.size)
    assert np.all(cells >= 0)
    assert audit["full_vector_python_allgather_used"] is False


def test_formal_builder_has_no_reference_or_endpoint_input() -> None:
    from src.adaptivity.task035e_goal_gradients import (
        build_task035e_formal_goal_gradients,
    )

    parameters = inspect.signature(
        build_task035e_formal_goal_gradients
    ).parameters
    assert tuple(parameters) == ("view",)
