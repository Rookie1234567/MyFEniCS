from __future__ import annotations

import numpy as np
import pytest
from dolfinx import fem, mesh
from mpi4py import MPI

from src.postprocessing.physical_field_comparison import build_common_volume_quadrature
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)


def test_affine_hex_n1e_p6_electric_and_curl_are_preserved_in_dgq6() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [comm.size, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    space = fem.functionspace(domain, ("N1curl", 6))
    electric = fem.Function(space, name="source_electric_code")

    def polynomial_electric(coordinates: np.ndarray) -> np.ndarray:
        x, y, z = coordinates
        return np.asarray((x * y**6, y * z**6, z * x**6), dtype=np.complex128)

    electric.interpolate(polynomial_electric)
    electric.x.scatter_forward()
    exported = prepare_cell_local_vector_field_export(electric)
    x_breakpoints = np.linspace(0.0, 1.0, comm.size + 1)
    rule = build_common_volume_quadrature(
        [(x_breakpoints, [0.0, 1.0], [0.0, 1.0])], gauss_order=8
    )
    samples = sample_cell_local_vector_fields(
        {
            "source_electric": electric,
            "exported_electric": exported.electric_dgq6,
            "exported_curl": exported.curl_electric_dgq6,
        },
        rule.points_nm,
        batch_size=73,
    )
    if comm.rank != 0:
        assert samples is None
        return
    assert samples is not None

    x, y, z = rule.points_nm.T
    expected_electric = np.column_stack((x * y**6, y * z**6, z * x**6))
    expected_curl = np.column_stack((-6 * y * z**5, -6 * z * x**5, -6 * x * y**5))
    np.testing.assert_allclose(samples["source_electric"], expected_electric, rtol=2e-11, atol=2e-12)
    np.testing.assert_allclose(samples["exported_electric"], expected_electric, rtol=2e-11, atol=2e-12)
    np.testing.assert_allclose(samples["exported_curl"], expected_curl, rtol=2e-11, atol=2e-12)
    assert exported.source_electric is electric
    assert exported.source_degree == exported.target_degree == 6


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="collective geometry rejection fixture must run with exactly two ranks",
)
def test_mpi2_non_affine_hex_rejection_is_collective() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [4, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    local_cell_count = int(domain.topology.index_map(3).size_local)
    if comm.rank == 1:
        assert local_cell_count > 0
        geometry_dofs = np.asarray(domain.geometry.dofmap[0], dtype=np.int64)
        domain.geometry.x[int(geometry_dofs[0]), 0] += 0.03125
        domain.geometry.x[int(geometry_dofs[0]), 1] += 0.03125

    space = fem.functionspace(domain, ("N1curl", 1))
    electric = fem.Function(space)
    with pytest.raises(ValueError, match="axis-aligned affine hexahedra"):
        prepare_cell_local_vector_field_export(electric)
