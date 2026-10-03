import copy
import numpy as np
import pytest

from benchmarks.check_task42extra_v12 import same, verify_B


def fixture():
    rng = np.random.default_rng(23)
    A = rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4))
    G = np.diag([1.0, 2.0, 3.0, 4.0])
    f = np.arange(4, dtype=float).astype(complex) + 1j
    cref = np.linalg.solve(A, f)
    c = cref + rng.normal(size=4)
    e = c - cref
    r = A @ c - f
    raw = dict(
        c_ref=cref,
        Gref=G @ cref,
        f=f,
        qf=np.linalg.solve(G, f),
        r_ref=A @ cref - f,
        fixed_e=e,
        fixed_Ge=G @ e,
        fixed_r=r,
        fixed_qr=np.linalg.solve(G, r),
        fixed_Ae=A @ e,
        direction_AX=np.ones((4, 1), complex),
        direction_qAX=np.linalg.solve(G, np.ones((4, 1), complex)),
        small_T=np.ones((1, 1)),
    )
    H = raw["direction_AX"].conj().T @ raw["direction_qAX"]
    raw["small_image_H"] = H
    record = dict(
        d_ref=np.vdot(cref, G @ cref).real,
        d_G=np.vdot(f, raw["qf"]).real,
        rows=dict(
            fixed=dict(
                E_G=np.sqrt(np.vdot(e, G @ e).real / np.vdot(cref, G @ cref).real),
                dual_loss=np.vdot(r, raw["fixed_qr"]).real
                / (2 * np.vdot(f, raw["qf"]).real),
                native_relative=np.linalg.norm(r) / np.linalg.norm(f),
            )
        ),
        steps=[],
        finite_field_subspace=dict(
            image_energy_eigenvalues=np.linalg.eigvalsh(H).tolist()
        ),
        actions=dict(A=4, AH=0, Gsolve=2, G_matvec=4),
    )
    return record, raw


def test_independent_checker_recomputes_nonhermitian_error_identity():
    r, raw = fixture()
    assert verify_B(r, raw)["identity_worst"] < 1e-10


@pytest.mark.parametrize("corruption", ["loss", "identity", "cap", "spectrum"])
def test_independent_checker_rejects_corrupt_numeric_records(corruption):
    r, raw = fixture()
    r = copy.deepcopy(r)
    if corruption == "loss":
        r["rows"]["fixed"]["dual_loss"] *= 2
    elif corruption == "identity":
        raw["fixed_Ae"][0] += 1
    elif corruption == "cap":
        r["actions"]["A"] = 65
    else:
        r["finite_field_subspace"]["image_energy_eigenvalues"][0] *= 2
    with pytest.raises(ValueError):
        verify_B(r, raw)


def test_near_zero_comparison_uses_given_operation_scale():
    same(1e-25, 0.0, scale=1.0)
    with pytest.raises(ValueError):
        same(1e-2, 0.0, scale=1.0)
