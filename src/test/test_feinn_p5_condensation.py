"""Independent non-Hermitian complex cell elimination, MPC and port witness."""

from pathlib import Path
import numpy as np
import pytest

from src.io.feinn_pilot import load_pilot
from src.solvers.feinn_native import FullNativePacket
from src.solvers.feinn_exact_condensation import ExactInteriorCondensation, capacity
from src.runners.feinn_gn_campaign import (
    STAGES,
    AUTHORITY,
    SUPERVISED,
    DEPENDENCIES,
    campaign_budget,
)


def synthetic():
    rng = np.random.default_rng(421905)
    F = rng.normal(size=(2, 3, 3)) + 1j * rng.normal(size=(2, 3, 3))
    F += 5 * np.eye(3)[None]
    return FullNativePacket(
        dict(
            F=F,
            classes=np.arange(2),
            cell_dofs=np.array([[0, 1, 3], [1, 2, 4]]),
            masters=np.arange(5),
            slaves=np.array([], int),
            full_rows=np.asarray(5),
            erows=np.arange(6),
            eids=np.array([0, 1, 3, 1, 2, 4]),
            evals=np.array([1, np.exp(0.4j), 1, 1, 1, 1]),
            idofs=np.array([[3], [4]]),
            br=np.array([0, 2]),
            bp=np.array([0, 0]),
            bv=np.array([0.4 + 0.2j, 0.3 - 0.1j]),
            dr=np.array([0, 2]),
            dp=np.array([0, 0]),
            dv=np.array([-0.1 + 0.3j, 0.2 + 0.1j]),
            H=np.array([2.0]),
            g=rng.normal(size=5) + 1j * rng.normal(size=5),
            gp=np.array([0.1 + 0.3j]),
            background=np.zeros(5, complex),
            background_alpha=np.zeros(1, complex),
            total_g=np.ones(5, complex),
        )
    )


def test_exact_nonzero_internal_load_and_complex_MPC_recover_full_equation(tmp_path):
    p = synthetic()
    reduced = ExactInteriorCondensation(p, [2])
    M, pair = reduced.assemble(save=tmp_path / "packet.npz")
    z = np.linalg.solve(M.toarray(), reduced.rhs)
    c, alpha = reduced.recover(z)
    V = np.column_stack(
        [p.volume(np.eye(p.size, dtype=complex)[:, j]) for j in range(p.size)]
    )
    B = np.column_stack([p.B(np.eye(p.np, dtype=complex)[:, j]) for j in range(p.np)])
    D = np.column_stack(
        [p.D(np.eye(p.size, dtype=complex)[:, j]) for j in range(p.size)]
    )
    full = np.block([[V, B], [-D, np.diag(p.a["H"])]])
    original = np.linalg.solve(full, np.r_[p.a["g"], p.a["gp"]])
    np.testing.assert_allclose(np.r_[c, alpha], original, rtol=1e-12, atol=1e-12)
    assert pair < 1e-12 and np.linalg.norm(c[[3, 4]]) > 0
    assert np.linalg.norm(full - full.conj().T) > 0.1


def test_reject_port_interior_and_shared_internal_unknown():
    p = synthetic()
    with pytest.raises(ValueError, match="PORT_HAS_INTERIOR"):
        ExactInteriorCondensation(FullNativePacket(dict(p.a, br=np.array([0, 3]))), [2])
    with pytest.raises(ValueError, match="NOT_CELL_LOCAL"):
        ExactInteriorCondensation(
            FullNativePacket(dict(p.a, eids=np.array([0, 1, 3, 1, 2, 3]))), [2]
        )


def test_inventory_capacity_and_label_boundary():
    plan = capacity(384, 5)
    assert plan["local_dimension"] == 540 and plan["local_interior"] == 240
    assert plan["raw_all_cell_tensor_bytes"] == 1791590400
    assert plan["allocation_upper_bytes"] < 12 * 2**30
    root = Path(__file__).resolve().parents[2]
    for name in STAGES:
        spec = load_pilot(root / "input/task042extra_feinn_5nm" / f"{name}.dat")
        assert spec.discretization["degree"] == (5 if name in AUTHORITY else 3)
        if name not in AUTHORITY:
            assert spec.derived["reference_used_for_training"] == (name in SUPERVISED)
    for name in ("v9_plain_gn", "v9_phase_gn"):
        assert "e3_reference" not in DEPENDENCIES[name]
    result = campaign_budget(
        [
            dict(path="/tmp/checks/v9_a_test_123/summary.json", seconds=2),
            dict(
                path="/old/task42extra_v8_plain_dual_123/run_summary.json", seconds=100
            ),
        ]
    )
    assert result["new_used_seconds"] == 2 and result["groups_used_seconds"]["A"] == 2
