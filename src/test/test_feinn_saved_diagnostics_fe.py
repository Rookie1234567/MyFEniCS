"""One minimal FE fixture for the newly connected masks/order/integral path."""

from types import SimpleNamespace

import numpy as np
import pytest


def test_saved_field_order_and_fixed_masks_and_bounded_integrals():
    from dolfinx import fem, mesh
    from mpi4py import MPI
    import basix.ufl
    from src.solvers.feinn_saved_field_diagnostics import assert_order, fixed_regions
    from src.solvers.feinn_bounded_field_integrals import BoundedFieldIntegrals

    msh = mesh.create_box(
        MPI.COMM_WORLD,
        [np.zeros(3), np.ones(3)],
        [2, 2, 2],
        cell_type=mesh.CellType.hexahedron,
    )
    V = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 3))
    f = SimpleNamespace(mpc=SimpleNamespace(slaves=np.array([], np.int32)))
    p = SimpleNamespace(
        a=dict(
            cell_dofs=np.asarray(V.dofmap.list, np.int64), slaves=np.array([], np.int64)
        )
    )
    assert_order(V, f, p)
    with pytest.raises(ValueError, match="NUMBERING_CHANGED"):
        assert_order(
            V,
            f,
            SimpleNamespace(
                a=dict(cell_dofs=p.a["cell_dofs"][::-1], slaves=p.a["slaves"])
            ),
        )
    cells = np.arange(8, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, 3, cells)
    tags = np.where(centers[:, 0] < 0.5, 1, 3)
    notch = centers[:, 2] > 0.5
    regions = fixed_regions(
        msh, centers, tags, notch, np.array([[0.0, 1.0]] * 3), h=0.5
    )
    assert len(regions["air_notch"]) == 2 and len(regions["air_other"]) == 2
    assert len(regions["periodic_boundary_neighbor"]) == 8
    assert len(regions["material_interface_neighbor"]) == 8
    E = fem.Function(V)
    E.interpolate(
        lambda x: np.vstack(
            (
                (1 + 2j) * np.ones(x.shape[1]),
                (2 - 1j) * np.ones(x.shape[1]),
                1j * np.ones(x.shape[1]),
            )
        )
    )
    integrator = BoundedFieldIntegrals(msh, 1.0)
    en = integrator.energies(E, q=5)
    assert en[0] == pytest.approx(11.0, rel=1e-10)
    assert en[1] < 1e-20
    assert np.linalg.norm(integrator.energies((E, E), q=5)) < 1e-25
