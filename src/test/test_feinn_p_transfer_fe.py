"""Nonzero complex p3->p4, orientation, curl and Floquet on eight hexes."""

import json
from copy import deepcopy
from dataclasses import replace
import basix.ufl
from dolfinx import fem

from src.io.feinn_pilot import DESIGN
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.feinn_interpolation import full_space
from src.solvers.feinn_discretization_audit import embedding_check


def test_complete_nonzero_complex_p_embedding_with_MPC():
    design = deepcopy(json.loads(DESIGN.read_text()))
    design["geometry"]["cells"] = [2, 2, 2]
    cfg, data, s3, *_ = full_space(design, 3)
    s4 = fem.functionspace(data.mesh, basix.ufl.element("N1curl", "hexahedron", 4))
    f3 = build_double_floquet_mpc(s3, data, cfg)
    f4 = build_double_floquet_mpc(s4, data, replace(cfg, nedelec_degree=4))
    record = embedding_check(data, s3, f3, s4, f4)
    assert record["passed"]
    assert record["p4_internal_nonzero_norm"] > 0
    assert record["orientation_classes"] > 1
    assert abs(record["phase_x"][1]) > 1e-5


def test_authority_surface_rule_is_frozen_while_ordinary_rule_stays_automatic():
    from src.solvers.feinn_fem import physical_config
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from types import SimpleNamespace
    design = json.loads(DESIGN.read_text())
    cfg, _ = physical_config(design, 4)
    modes = [SimpleNamespace(m=3, n=1)]
    assert _dtn_surface_quadrature_degree(cfg, modes) == 17
    cfg.stage4_dtn_quadrature_degree = 15
    assert _dtn_surface_quadrature_degree(cfg, modes) == 15
