import copy
import json

import numpy as np
import pytest

from src.solvers.feinn_common_descent import (
    analyze_configuration, atomic_json, common_minimum, parameter_basis,
    provenance_columns, quadratic, residual_candidate, trust_ball,
)
from benchmarks.check_feinn_common_descent import verify_configuration


def test_opposing_extremes_can_have_common_improvement():
    # Independent known witness (1/2,1/2) gives F=R=1/2.
    row = common_minimum(np.eye(2), np.array([-1., 0.]), np.eye(2), np.array([0., -1.]))
    assert row["U"] == pytest.approx(.5, abs=1e-10)
    assert row["certificate"]["lower"] == pytest.approx(.5, abs=1e-10)
    assert np.linalg.norm(row["u"]) <= 1
    assert row["u_R"] == pytest.approx([0, 1])
    assert row["u_F"] == pytest.approx([1, 0])


def test_true_conflict_has_closed_numerical_bounds():
    row = common_minimum(np.ones((1, 1)), np.array([-1.]), np.ones((1, 1)), np.array([1.]))
    assert row["U"] == pytest.approx(1)
    assert row["certificate"]["lower"] - row["certificate"]["numerical_margin"] > .999
    assert row["gap"] < 1e-10


def fixture():
    rng = np.random.default_rng(4211501)
    A = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
    L = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
    G = L.conj().T @ L + np.eye(7)
    X = rng.normal(size=(7, 4)) + 1j * rng.normal(size=(7, 4))
    e = rng.normal(size=7) + 1j * rng.normal(size=7)
    Y, r = A @ X, A @ e
    raw = dict(P=rng.normal(size=(11, 4)), X=X, GX=G @ X, Y=Y,
               WY=np.linalg.solve(G, Y), e=e, Ge=G @ e, r=r, qr=np.linalg.solve(G, r))
    metadata = dict(name="fixed", identity=dict(parameter="hash_theta", c="hash_c"),
                    directions=[dict(column=j, kind="PDE" if j < 2 else "reference_G", group=str(j % 2)) for j in range(4)])
    return raw, metadata, G


def record_fixture(subset="ALL16"):
    raw, meta, G = fixture()
    columns = provenance_columns(meta["directions"], 4, subset)
    selected = {k: v[:, columns] if v.ndim == 2 else v for k, v in raw.items()}
    row = analyze_configuration(selected, 3, 1e-10, 2)
    row.update(state="fixed", subset=subset, columns=columns, state_identity=meta["identity"],
               residual_candidate_unlabeled=subset == "PDE8")
    return row, raw, meta, G


def test_complex_nonhermitian_chain_and_explicit_whitening():
    row, raw, meta, G = record_fixture()
    checked = verify_configuration(row, raw, meta, 3, 2)
    assert checked["raw_cross_defect"] < 1e-12
    # Independent whitening computes real least-square coefficients and energy.
    T = np.asarray(row["T"])
    B = .003 * raw["X"] @ T
    W = np.linalg.cholesky(G).conj().T
    Z, t = W @ B, W @ raw["e"]
    denom = np.linalg.norm(t) ** 2
    H = (Z.real.T @ Z.real + Z.imag.T @ Z.imag) / denom
    a = (Z.real.T @ t.real + Z.imag.T @ t.imag) / denom
    assert np.asarray(row["quadratic_F"]["H"]) == pytest.approx(H, abs=1e-12)
    assert np.asarray(row["quadratic_F"]["a"]) == pytest.approx(a, abs=1e-12)


@pytest.mark.parametrize("kind", ["permute", "scales", "duplicate", "near"])
def test_parameter_basis_physical_step_invariance_and_rank(kind):
    raw, _, _ = fixture()
    P, Y, WY, r, qr = [raw[k] for k in ("P", "Y", "WY", "r", "qr")]
    baseline = residual_candidate(dict(P=P, Y=Y, WY=WY, r=r, qr=qr, theta_norm=3), 1e-10)
    if kind in ("duplicate", "near"):
        P = np.column_stack([P, P[:, 0] + (1e-13 * P[:, 1] if kind == "near" else 0)])
        Y = np.column_stack([Y, Y[:, 0] + (1e-13 * Y[:, 1] if kind == "near" else 0)])
        WY = np.column_stack([WY, WY[:, 0] + (1e-13 * WY[:, 1] if kind == "near" else 0)])
    else:
        order = [2, 0, 3, 1]
        scale = np.array([1e-4, 1e4, 3, .2]) if kind == "scales" else np.ones(4)
        P, Y, WY = [v[:, order] * scale for v in (P, Y, WY)]
    new = residual_candidate(dict(P=P, Y=Y, WY=WY, r=r, qr=qr, theta_norm=3), 1e-10)
    assert new["basis"]["rank"] == 4
    assert P @ new["alpha"] == pytest.approx(raw["P"] @ baseline["alpha"], abs=1e-10)
    assert Y @ new["alpha"] == pytest.approx(raw["Y"] @ baseline["alpha"], abs=1e-10)


def test_rank_sensitivity_is_retained_not_selected():
    P = np.array([[1., 1.], [0., 2e-11], [0., 0.]])
    _, main = parameter_basis(P, 1e-10)
    _, sensitivity = parameter_basis(P, 1e-12)
    assert main["rank"] == 1 and sensitivity["rank"] == 2


def test_zero_gradient_and_minimum_norm():
    u, _ = trust_ball(np.diag([0., 1.]), np.zeros(2))
    assert np.array_equal(u, np.zeros(2))
    row = common_minimum(np.zeros((2, 2)), np.zeros(2), np.zeros((2, 2)), np.zeros(2))
    assert row["U"] == 1 and row["certificate"]["lower"] == 1


@pytest.mark.parametrize("kind", ["zero_denom", "near_denom", "negative", "NaN"])
def test_invalid_data_not_regularized(kind):
    X = np.eye(2, dtype=complex)
    WX, x, wx = X.copy(), np.ones(2, complex), np.ones(2, complex)
    if kind == "zero_denom":
        wx[:] = 0
    elif kind == "near_denom":
        wx = np.array([1., -1. + 1e-16], complex)
    elif kind == "negative":
        WX *= -1
    else:
        WX[0, 0] = np.nan
    with pytest.raises(ValueError):
        quadratic(X, WX, x, wx)


def test_label_isolation_and_save_before_reference_evaluation(tmp_path):
    raw, meta, _ = fixture()
    columns = provenance_columns(meta["directions"], 4, "PDE8")
    def construct(data):
        packet = {k: data[k][:, columns].copy() if k in ("P", "Y", "WY") else data[k].copy() for k in ("P", "Y", "WY", "r", "qr")}
        return residual_candidate(dict(**packet, theta_norm=3), 1e-10)
    before = construct(raw)
    digest = atomic_json(tmp_path / "candidate.json", before)
    altered = {k: v.copy() for k, v in raw.items()}
    for k in ("P", "Y", "WY"):
        altered[k][:, 2:] = np.nan
    altered.pop("e")
    altered.pop("Ge")
    altered.pop("X")
    altered.pop("GX")
    assert construct(altered) == before
    assert len(digest) == 64 and json.loads((tmp_path / "candidate.json").read_text()) == before
    with pytest.raises(ValueError, match="ALLOWLIST"):
        residual_candidate(dict(P=raw["P"], Y=raw["Y"], WY=raw["WY"], r=raw["r"], qr=raw["qr"], theta_norm=3, e=raw["e"]), 1e-10)
    with pytest.raises(ValueError, match="IMMUTABLE"):
        atomic_json(tmp_path / "candidate.json", before)


@pytest.mark.parametrize("damage", ["u", "lambda", "mu", "bound", "denominator", "columns", "state", "identity", "NaN", "Inf", "classification", "labels"])
def test_corrupted_records_rejected(damage):
    row, raw, meta, _ = record_fixture()
    row = copy.deepcopy(row)
    if damage == "u":
        row["points"]["common"]["u"][0] += 2
    elif damage in ("lambda", "mu"):
        row["common"]["certificate"]["lambda_" if damage == "lambda" else "mu"] = -1
    elif damage == "bound":
        row["common"]["certificate"]["lower"] += .02
    elif damage == "denominator":
        row["quadratic_R"]["denominator"] *= 2
    elif damage == "columns":
        row["columns"] = list(reversed(row["columns"]))
    elif damage == "state":
        row["state"] = "other"
    elif damage == "identity":
        row["state_identity"]["c"] = "corrupt"
    elif damage in ("NaN", "Inf"):
        row["points"]["common"]["F"] = np.nan if damage == "NaN" else np.inf
    elif damage == "classification":
        row["classification"] = "PRODUCER_FAKE_PASS"
    else:
        row["residual_candidate_unlabeled"] = True
    with pytest.raises(ValueError):
        verify_configuration(row, raw, meta, 3, 2)


def test_complete_saved_array_pipeline_freezes_candidates_first(tmp_path, monkeypatch):
    """Tiny independent nonHermitian fixture exercises IO/staging, no FE services."""
    from src.runners import feinn_common_descent_arrays as runner
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("TASK42EXTRA_ENV_MODE", "pure")
    monkeypatch.setattr(runner.subprocess, "check_output", lambda args, **kwargs: "fixture_source\n" if args[1] == "rev-parse" else "task42extra_feinn_5nm\n" if args[1] == "branch" else "")
    rng = np.random.default_rng(4211502)
    P = rng.normal(size=(22, 16))
    X = (rng.normal(size=(20, 16)) + 1j * rng.normal(size=(20, 16))).astype(complex)
    A = rng.normal(size=(20, 20)) + 1j * rng.normal(size=(20, 20))
    G = np.diag(np.arange(1, 21))
    e = rng.normal(size=20).astype(complex) + 1j
    theta, c = rng.normal(size=22), e + 2j
    Y, r = A @ X, A @ e
    raw = dict(P=P, X=X, GX=G @ X, Y=Y, WY=np.linalg.solve(G, Y), e=e, Ge=G @ e,
               r=r, qr=np.linalg.solve(G, r), theta=theta, c=c)
    path = tmp_path / "raw.npz"
    np.savez(path, **{"fixed_" + k: v for k, v in raw.items()})
    directions = [dict(column=j, kind="PDE" if j < 8 else "reference_G", group=str(j % 8)) for j in range(16)]
    state = dict(parameter_norm=float(np.linalg.norm(theta)), parameter_sha256=runner.array_sha(theta),
                 complete_c_sha256=runner.array_sha(c), directions=directions)
    reference = dict(packet="fixture_identity")
    def write(name, value):
        p = tmp_path / name
        p.write_text(json.dumps(value))
        return dict(path=str(p), sha256=runner.sha(p))
    result_entry = write("old.json", dict(reference=reference, states=dict(fixed=state)))
    vectors_entry = dict(path=str(path), sha256=runner.sha(path))
    index_entry = write("index.json", dict(source_sha="old_source", files=dict(vectors=vectors_entry, result=result_entry)))
    geometry_entry = write("geometry.json", dict(reference=reference, rows=dict(fixed=dict(native_denominator=2))))
    geometry_index = write("geometry_index.json", dict(files=dict(result=geometry_entry)))
    design = dict(states=dict(fixed=state), inputs=dict(index=index_entry, result=result_entry, vectors=vectors_entry,
                  field_geometry=geometry_entry, field_geometry_index=geometry_index), original_C1_source="old_source",
                  packet_identity=reference, rconds=[1e-10, 1e-12], native_denominator=2, parameter_count=22, FE_count=20, review_sha="fixture_review")
    dpath = tmp_path / "design.json"
    dpath.write_text(json.dumps(design))
    output = tmp_path / "run"
    old_extract = runner.extract
    def observe(npz, state, keys, design, columns=None):
        if "e" in keys:
            ledger = json.loads((output / "candidate_freeze.json").read_text())
            assert len(ledger["candidates"]) == 2
            for item in ledger["candidates"].values():
                assert runner.sha(item["path"]) == item["sha256"]
        return old_extract(npz, state, keys, design, columns)
    monkeypatch.setattr(runner, "extract", observe)
    runner.run(dpath, output)
    result = json.loads((output / "result.json").read_text())
    assert len(result["configurations"]) == 4 and not result["unknown"]
    runner.check(output / "result.json", tmp_path / "checker.json")
    assert json.loads((tmp_path / "checker.json").read_text())["optimize_calls"] == 0
