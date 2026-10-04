from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest

from src.solvers.affine_field_output import two_sum, affine_state, total_field
from src.solvers.accurate_ports import recover_ports_components
from benchmarks.affine_output_checker import exact_sum_identity, check_state
from src.solvers.port_qualification_state import qualification_state


def fixture():
    a = dict(
        H=np.array([1.0]),
        gp=np.array([0j]),
        dp=np.array([0, 0]),
        dr=np.array([0, 1]),
        dv=np.array([1 + 0j, -1 + 0j]),
        background=np.array([1 + 1j, 1 + 1j]),
        masters=np.array([0, 1]),
    )
    c = np.array([2**-60 + 1j * 2**-61, 2**-62 + 1j * 2**-63])
    bg, _ = recover_ports_components(a, (a["background"],))
    a["background_alpha"] = bg
    alpha, _ = recover_ports_components(a, (c,))
    return a, affine_state(SimpleNamespace(a=a), c, alpha)


def test_exact_two_sum_and_every_component():
    a, s = fixture()
    v = total_field(s)
    assert exact_sum_identity(s["c_scattered"], s["background"], v.hi, v.lo)
    assert check_state(a, s, mode_hash="m", expected_mode_hash="m")["passed"]
    with pytest.raises(TypeError):
        np.asarray(v)
    assert v.lossy_projection()[1].startswith("LOSSY")
    applied = []

    def fun(c):
        applied.append(c)
        return c * 2

    mapped = v.map(fun)
    assert len(applied) == 2 and np.array_equal(mapped.lo, v.lo * 2)


@pytest.mark.parametrize("kind", ["low", "swap", "background", "master", "gp", "mode"])
def test_corrupt_exact_output_rejected(kind):
    a, s = fixture()
    a = deepcopy(a)
    s = deepcopy(s)
    mode = "m"
    if kind == "low":
        s["total_lo"][0] = 0
    if kind == "swap":
        s["total_hi"], s["total_lo"] = s["total_lo"], s["total_hi"]
    if kind == "background":
        s["background"][0] += 1
    if kind == "master":
        s["masters"] = s["masters"][::-1]
    if kind == "gp":
        a["gp"][0] = 1
    if kind == "mode":
        mode = "wrong"
    try:
        r = check_state(a, s, mode_hash=mode, expected_mode_hash="m")
    except ValueError:
        return
    assert not r["passed"]


@pytest.mark.parametrize(
    "shared,role,output,files,identity",
    [
        (False, True, True, True, True),
        (True, False, True, True, True),
        (True, True, False, True, True),
        (True, True, True, False, True),
        (True, True, True, True, False),
    ],
)
def test_incomplete_state_never_admits_solve(shared, role, output, files, identity):
    r = qualification_state(
        shared=shared,
        role=role,
        output=output,
        files_present=files,
        identity_matches=identity,
    )
    assert not r["solve_admitted"]
    assert r["negative_field_readable"] == (files and identity)


def test_gate_boolean_schema():
    with pytest.raises(ValueError):
        qualification_state(
            shared=1, role=True, output=True, files_present=True, identity_matches=True
        )


def test_random_exact_sums():
    rng = np.random.default_rng(422200)
    a = np.asarray(rng.normal(size=100) + 1j * rng.normal(size=100))
    b = np.asarray((rng.normal(size=100) + 1j * rng.normal(size=100)) * 1e-14)
    v = two_sum(a, b)
    assert exact_sum_identity(a, b, v.hi, v.lo)
