"""Zero is a caller proof, not a threshold; ordinary load paths unchanged."""

import sys
from types import SimpleNamespace
import numpy as np
from src.solvers import fixed_phase_audit as work


def test_explicit_zero_skips_only_volume_quadrature(monkeypatch):
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [1, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [0, 1, 1],
            [1, 1, 1],
        ],
        float,
    )
    calls = []

    def quadrature(cell, q):
        calls.append(cell)
        return (
            (np.array([[0.3, 0.4, 0.5]]), np.ones(1))
            if cell == "hex"
            else (np.array([[0.3, 0.4]]), np.ones(1))
        )

    fake = SimpleNamespace(
        CellType=SimpleNamespace(hexahedron="hex", quadrilateral="quad"),
        make_quadrature=quadrature,
        cell=SimpleNamespace(
            geometry=lambda _: vertices,
            topology=lambda _: {2: [[0, 1, 2, 3], [4, 5, 6, 7]]},
        ),
    )
    monkeypatch.setitem(sys.modules, "basix", fake)
    model = dict(
        cfg=SimpleNamespace(physical_z_max=1.0, physical_z_min=0.0),
        space=SimpleNamespace(
            mesh=SimpleNamespace(
                geometry=SimpleNamespace(x=vertices, dofmap=np.arange(8)[None, :])
            )
        ),
    )
    packet = SimpleNamespace(nc=1, dim=2, pullback=lambda x: x.ravel())

    def basis(model, cell, points):
        return np.ones((len(points), 2, 3), complex), None, points, 1.0, np.eye(3)

    monkeypatch.setattr(work, "affine_basis", basis)
    def traction(x, side):
        return np.ones_like(x, dtype=complex) * (2 + 3j)

    def zero(x):
        return np.zeros_like(x, dtype=complex)
    ordinary = work.integrate_load(model, packet, zero, traction, 47)
    assert calls == ["hex", "quad"]
    calls.clear()
    boundary = work.integrate_load(model, packet, None, traction, 47)
    assert calls == ["quad"]
    assert np.array_equal(ordinary, boundary)
    nonzero = work.integrate_load(
        model, packet, lambda x: np.ones_like(x), traction, 47
    )
    assert np.linalg.norm(nonzero - boundary) > 1
