from __future__ import annotations

import inspect
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np

from dolfinx import default_real_type, fem, mesh
from basix.ufl import element

from src.adaptivity.task035e_goal_gradients import (
    _assemble_volume_p6_gradient,
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


def test_volume_gradient_uses_field_scaled_quadratic_difference() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_unit_cube(
        comm,
        2,
        2,
        max(2, 2 * comm.size),
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    field = fem.Function(space)
    start = int(space.dofmap.index_map.local_range[0])
    rows = start + np.arange(len(field.x.array), dtype=float)
    field.x.array[:] = (
        0.7 * np.cos(0.031 * (rows + 1.0))
        + 0.4j * np.sin(0.047 * (rows + 1.0))
    )
    field.x.scatter_forward()
    cell_map = domain.topology.index_map(domain.topology.dim)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    cell_tags = mesh.meshtags(
        domain,
        domain.topology.dim,
        owned_cells,
        np.ones(len(owned_cells), dtype=np.int32),
    )
    view = SimpleNamespace(
        field=field,
        mesh_data=SimpleNamespace(
            mesh=domain,
            cell_tags=cell_tags,
        ),
        config=SimpleNamespace(
            k0=0.35,
            eps_grating=2.1 + 0.7j,
            eps_substrate=1.4 + 0.0j,
            tags=SimpleNamespace(grating=1, substrate=2),
        ),
        port_metrics={"incident_power_code_units": 1.3},
    )
    gradient, audit = _assemble_volume_p6_gradient(view)
    try:
        assert audit["finite_difference_relative_step"] == 1.0e-5
        assert audit["finite_difference_absolute_step"] > 1.0e-7
        assert audit["finite_difference_relative_error"] <= 2.0e-7
        assert audit["field_l2_norm"] > 0.0
        assert audit["direction_l2_norm"] > 0.0
    finally:
        gradient.destroy()


def test_formal_builder_has_no_reference_or_endpoint_input() -> None:
    from src.adaptivity.task035e_goal_gradients import (
        build_task035e_formal_goal_gradients,
    )

    parameters = inspect.signature(
        build_task035e_formal_goal_gradients
    ).parameters
    assert tuple(parameters) == ("view",)
