import numpy as np
from types import SimpleNamespace
from benchmarks.reliable_port_checker import raw_equations
from src.solvers.affine_field_output import affine_state
from src.solvers.accurate_ports import recover_ports_components


def test_independent_full_equation_and_damage():
    c = np.array([0.2 + 0.1j, -0.4 + 0.7j])
    bg = np.array([1.0 + 0.2j, 1.0 - 0.3j])
    a = dict(
        F=np.array([[[3.0, 1.0], [1.0, 2.0]]], complex),
        classes=np.array([0]),
        cell_dofs=np.array([[0, 1]]),
        erows=np.array([0, 1]),
        eids=np.array([0, 1]),
        evals=np.ones(2, complex),
        masters=np.array([0, 1]),
        br=np.array([0, 1]),
        bp=np.array([0, 0]),
        bv=np.array([1.0, -1.0], complex),
        dp=np.array([0, 0]),
        dr=np.array([0, 1]),
        dv=np.array([1.0, -1.0], complex),
        H=np.array([1.0]),
        gp=np.array([0j]),
        background=bg,
    )
    alpha, _ = recover_ports_components(a, (c,))
    ba, _ = recover_ports_components(a, (bg,))
    a["background_alpha"] = ba
    a["g"] = a["F"][0] @ c + a["bv"] * alpha[0]
    a["total_g"] = a["g"] + a["F"][0] @ bg + a["bv"] * ba[0]
    state = affine_state(SimpleNamespace(a=a), c, alpha)
    assert max(raw_equations(a, state).values()) < 1e-14
    a["g"] = a["g"].copy()
    a["g"][0] += 0.1
    assert raw_equations(a, state)["native_relative"] > 1e-3
