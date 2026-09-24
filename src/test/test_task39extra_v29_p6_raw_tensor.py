from __future__ import annotations

from types import SimpleNamespace

import basix
import numpy as np
import ufl
from basix.ufl import element

from src.solvers.task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate


def test_p6_blocked_gram_uses_full_form_analysis_and_is_complex_finite() -> None:
    space_element = element("N1curl", "hexahedron", 6)
    coordinate_element = element("P", "hexahedron", 1, shape=(3,))
    domain = ufl.Mesh(coordinate_element)
    space = ufl.FunctionSpace(domain, space_element)
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    mass = 2.5 - 0.2j
    full_form = (
        ufl.inner(ufl.curl(trial), ufl.curl(test))
        + mass * ufl.inner(trial, test)
    ) * ufl.dx(domain=domain) + (
        np.complex128(0.0)
        * ufl.inner(ufl.curl(trial), ufl.curl(test))
        * ufl.dx(domain=domain)
    )
    cfg = SimpleNamespace(
        use_pml=False,
        divergence_penalty=0.0,
        mu_r=1.0,
        k0=1.0,
        eps_r=-mass,
        substrate_index=1.0,
        grating_index=1.0,
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
    )
    builder = Task39ExtraP6RawTensorCandidate(
        space_element.basix_element,
        cfg,
        full_form,
        tag_aliases={"otherwise": 1},
        require_all_material_tags=False,
    )
    audit = builder.audit()
    rule = audit["integral_rule_records"][0]
    assert rule["components"] == ["curl", "mass"]
    assert rule["degree"] == 15
    assert rule["point_count"] == 512
    assert audit["literal_zero_default_integral_count"] == 1

    coordinates = basix.geometry(basix.CellType.hexahedron).ravel()
    matrix = builder.build(coordinates, tag=1, dimension=882)
    assert matrix.shape == (882, 882)
    assert np.isfinite(matrix).all()
    scale = max(float(np.linalg.norm(matrix)), np.finfo(float).tiny)
    assert float(np.linalg.norm(matrix - matrix.conjugate().T) / scale) > 1.0e-5
