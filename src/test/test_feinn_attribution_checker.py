import copy
import numpy as np
import pytest

from benchmarks.check_task42extra_v12 import (
    same,
    verify_B,
    verify_C,
    auxiliary_state_mapping,
)


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


def local_fixture():
    """Independent real least squares after explicit small whitening."""
    rng = np.random.default_rng(42213)
    A = rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4))
    G = np.diag([1.0, 2.0, 3.0, 4.0])
    f = rng.normal(size=4) + 1j * rng.normal(size=4)
    cref = np.linalg.solve(A, f)
    e = rng.normal(size=4) + 1j * rng.normal(size=4)
    r = A @ e
    X = rng.normal(size=(4, 2)) + 1j * rng.normal(size=(4, 2))
    Y = A @ X
    P = rng.normal(size=(5, 2))
    raw = {
        "fixed_" + k: v
        for k, v in dict(
            c=cref + e,
            e=e,
            Ge=G @ e,
            r=r,
            qr=np.linalg.solve(G, r),
            X=X,
            GX=G @ X,
            Y=Y,
            WY=np.linalg.solve(G, Y),
            P=P,
        ).items()
    }
    dref = float(np.vdot(cref, G @ cref).real)
    dG = float(np.vdot(f, np.linalg.solve(G, f)).real)
    projections = {}
    for kind, cols, target, whiten in [
        ("field", X, e, np.sqrt(G)),
        ("residual", Y, r, np.sqrt(np.linalg.inv(G))),
    ]:
        Z, t = whiten @ cols, whiten @ target
        alpha = np.linalg.lstsq(
            np.vstack([Z.real, Z.imag]), -np.concatenate([t.real, t.imag]), rcond=None
        )[0]
        raw["fixed_" + kind + "_alpha"] = alpha
        raw["fixed_" + kind + "_step"] = P @ alpha
        changes = {}
        for label, old, delta, W in [
            ("field", e, X @ alpha, G),
            ("residual", r, Y @ alpha, np.linalg.inv(G)),
        ]:
            before = float(np.vdot(old, W @ old).real)
            after = float(np.vdot(old + delta, W @ (old + delta)).real)
            cross = float(2 * np.vdot(old, W @ delta).real)
            update = float(np.vdot(delta, W @ delta).real)
            scale = max(before, after, abs(cross) + update)
            changes[label] = dict(
                before=before,
                after=after,
                cross=cross,
                update_energy=update,
                change=after - before,
                reconstructed_change=cross + update,
                operation_scale=scale,
                defect=abs(after - before - cross - update) / scale,
            )
        obj = changes[kind]
        projections[kind] = dict(
            before_energy=obj["before"],
            after_energy=obj["after"],
            removed_energy_fraction=1 - obj["after"] / obj["before"],
            field_cross_effect=changes["field"],
            residual_cross_effect=changes["residual"],
            E_G_after_linear=np.sqrt(changes["field"]["after"] / dref),
            dual_loss_after_linear=changes["residual"]["after"] / (2 * dG),
            rank=2,
            real_coefficients=True,
        )
    record = dict(
        d_ref=dref,
        d_G=dG,
        states=dict(
            fixed=dict(
                projections=projections,
                witnesses=[],
                parameter_buffers_unchanged=True,
                parameter_norm=1.0,
            )
        ),
        counts=dict(JVP=2, VJP=0, forward_witnesses=0),
        actions=dict(A=2, AH=0, Gsolve=0, G_matvec=0),
    )
    return record, raw


def test_C1_complex_nonhermitian_real_parameters_recompute_classification():
    record, raw = local_fixture()
    result = verify_C(record, raw)["fixed"]
    assert result["field_energy_removed"] == pytest.approx(
        record["states"]["fixed"]["projections"]["field"]["removed_energy_fraction"]
    )
    assert not result["raw_projections"]["field"]["field"]["near_zero_before"]


@pytest.mark.parametrize("kind", ["field", "residual"])
@pytest.mark.parametrize(
    "key", ["removed_energy_fraction", "before_energy", "after_energy"]
)
def test_C1_rejects_corrupted_projection_fraction_and_energies(kind, key):
    record, raw = local_fixture()
    record["states"]["fixed"]["projections"][kind][key] += 1.0
    with pytest.raises(ValueError, match="MISMATCH"):
        verify_C(record, raw)


@pytest.mark.parametrize("kind", ["field", "residual"])
@pytest.mark.parametrize("effect", ["field_cross_effect", "residual_cross_effect"])
@pytest.mark.parametrize(
    "key",
    [
        "before",
        "after",
        "cross",
        "update_energy",
        "change",
        "reconstructed_change",
        "operation_scale",
        "defect",
    ],
)
def test_C1_rejects_each_corrupted_cross_effect(kind, effect, key):
    record, raw = local_fixture()
    record["states"]["fixed"]["projections"][kind][effect][key] += 1.0
    with pytest.raises(ValueError, match="MISMATCH"):
        verify_C(record, raw)


@pytest.mark.parametrize("key", ["e", "Ge", "r", "qr", "X", "GX", "Y", "WY"])
def test_C1_rejects_nonfinite_raw_vectors(key):
    record, raw = local_fixture()
    raw["fixed_" + key].flat[0] = np.nan
    with pytest.raises(ValueError, match="NONFINITE"):
        verify_C(record, raw)


def test_auxiliary_cost_mapping_distinguishes_performed_gate_from_unrun_D1():
    cost = dict(
        baseline_complete_seconds=100.0,
        time_gain_threshold_seconds=80.0,
        nn_prefix_lower_bound_seconds=1000.0,
        baseline_peak_tree_RSS_bytes=100,
        memory_lower_bound_from_historical_NN_workflow_bytes=200,
        D1_status="NOT_RUN_COST_VETO",
    )
    assert auxiliary_state_mapping(cost) == dict(
        D0="COST_VETO_CONFIRMED", D1="NOT_RUN_COST_VETO"
    )
    cost["nn_prefix_lower_bound_seconds"] = 10.0
    with pytest.raises(ValueError, match="D0_COST"):
        auxiliary_state_mapping(cost)
