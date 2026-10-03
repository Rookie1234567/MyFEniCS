import copy
import json
import multiprocessing
from pathlib import Path
from time import monotonic

import numpy as np
import pytest
from scipy.optimize import minimize

from src.solvers.feinn_common_descent import objective, residual_candidate
from src.solvers.feinn_native_constraint import constrained_minimum, native_candidate
from benchmarks.check_feinn_native_constraint import direct_points, verify


@pytest.mark.parametrize(
    "kind", ["R_inactive", "R_active", "ball_active", "opposing", "zero_gradient"]
)
def test_constraint_against_independent_small_solver(kind):
    HN, HR = np.eye(2), np.eye(2) / 2
    aN, aR = np.array([-0.3, -0.2]), np.array([-0.1, -0.1])
    if kind == "R_active":
        aR = np.array([0.25, -0.25])
    elif kind == "ball_active":
        aN, aR = np.array([-2.0, -0.2]), np.array([-1.0, -1.0])
    elif kind == "opposing":
        aN, aR = np.array([-1.0, 0.0]), np.array([1.0, 0.0])
    elif kind == "zero_gradient":
        aN = aR = np.zeros(2)
    row = constrained_minimum(HN, aN, HR, aR)
    u = np.asarray(row["u"])
    independent = minimize(
        lambda x: objective(HN, aN, x),
        np.zeros(2),
        jac=lambda x: 2 * (HN @ x + aN),
        method="SLSQP",
        constraints=[
            dict(type="ineq", fun=lambda x: 1 - x @ x),
            dict(type="ineq", fun=lambda x: 1 - objective(HR, aR, x)),
        ],
        options=dict(ftol=1e-13, maxiter=150),
    )
    assert objective(HR, aR, u) <= 1 + 1e-10 and np.linalg.norm(u) <= 1 + 1e-10
    assert row["U"] == pytest.approx(independent.fun, abs=1e-8)
    assert (
        row["certificate"]["lower"] - row["certificate"]["numerical_margin"]
        <= independent.fun + 1e-10
    )
    assert row["multiplier_evaluations"] <= 96 and row["ball_root_iteration_max"] <= 80


def complex_fixture():
    rng = np.random.default_rng(4211801)
    A = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
    G = np.diag(np.arange(1.0, 8.0))
    X = rng.normal(size=(7, 4)) + 1j * rng.normal(size=(7, 4))
    e = rng.normal(size=7) + 1j * rng.normal(size=7)
    Y, r = A @ X, A @ e
    raw = dict(
        P=rng.normal(size=(11, 4)),
        X=X,
        GX=G @ X,
        Y=Y,
        WY=np.linalg.solve(G, Y),
        e=e,
        Ge=G @ e,
        r=r,
        qr=np.linalg.solve(G, r),
    )
    pde = {k: raw[k] for k in ("P", "Y", "WY", "r", "qr")}
    pde["theta_norm"] = 3.0
    candidate = native_candidate(pde, 1e-10)
    old = residual_candidate(pde, 1e-10)
    points = {
        name: direct_points(raw, a, 0.29104200262261154)
        for name, a in (
            ("zero", np.zeros(4)),
            ("original_R_minimum", np.asarray(old["alpha"])),
            ("native_constrained", np.asarray(candidate["alpha"])),
        )
    }
    return raw, pde, candidate, old, points


def test_complex_chain_and_independent_whitening():
    raw, _, candidate, old, points = complex_fixture()
    row = verify(candidate, raw, points, np.asarray(old["alpha"]), 0.29104200262261154)
    assert row["producer_or_optimizer_calls"] == 0
    T = np.asarray(candidate["T"])
    Z = 0.003 * raw["Y"] @ T
    denom = np.linalg.norm(raw["r"]) ** 2
    assert np.asarray(candidate["quadratic_N"]["H"]) == pytest.approx(
        (Z.real.T @ Z.real + Z.imag.T @ Z.imag) / denom, abs=1e-12
    )


@pytest.mark.parametrize(
    "damage", ["bound", "mu", "lambda", "u", "F", "policy", "PSD", "nonfinite"]
)
def test_independent_checker_rejects_corruption(damage):
    raw, _, candidate, old, points = complex_fixture()
    if damage == "bound":
        candidate["solution"]["certificate"]["lower"] += 0.1
    elif damage in ("mu", "lambda"):
        candidate["solution"]["certificate"]["mu" if damage == "mu" else "lambda_"] = -1
    elif damage == "u":
        candidate["solution"]["u"][0] += 0.1
    elif damage == "F":
        points["native_constrained"]["F"] += 0.1
    elif damage == "policy":
        candidate["official_candidate_results"] = True
    elif damage == "PSD":
        candidate["quadratic_N"]["H"][0][0] = -10.0
    else:
        raw["qr"][0] = np.nan
    with pytest.raises(ValueError):
        verify(candidate, raw, points, np.asarray(old["alpha"]), 0.29104200262261154)


@pytest.mark.parametrize("damage", ["denominator", "PSD", "rank", "label", "nan"])
def test_constructor_invalid_input_never_regularized(damage):
    _, packet, _, _, _ = complex_fixture()
    packet = copy.deepcopy(packet)
    if damage == "denominator":
        packet["r"] *= 0
    elif damage == "PSD":
        packet["WY"] *= -1
    elif damage == "rank":
        packet["P"] *= 0
    elif damage == "label":
        packet["e"] = np.ones(7)
    else:
        packet["r"][0] = np.nan
    with pytest.raises(ValueError):
        native_candidate(packet, 1e-10)


def test_checker_has_no_optimizer_or_producer_dependency():
    text = Path("benchmarks/check_feinn_native_constraint.py").read_text()
    assert "scipy" not in text and "src.solvers" not in text


def test_actual_separate_freeze_score_check_pipeline(tmp_path, monkeypatch):
    from src.runners import feinn_common_descent_arrays as common
    from src.runners import feinn_native_constraint_arrays as runner

    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "source", lambda: "fixture_source")
    monkeypatch.setenv("TASK42EXTRA_ENV_MODE", "pure")
    rng = np.random.default_rng(4211802)
    P = rng.normal(size=(22, 16))
    X = rng.normal(size=(20, 16)) + 1j * rng.normal(size=(20, 16))
    A = rng.normal(size=(20, 20)) + 1j * rng.normal(size=(20, 20))
    G = np.diag(np.arange(1.0, 21.0))
    e = rng.normal(size=20) + 1j
    theta = rng.normal(size=22)
    Y, r = A @ X, A @ e
    raw = dict(
        P=P,
        X=X,
        GX=G @ X,
        Y=Y,
        WY=np.linalg.solve(G, Y),
        e=e,
        Ge=G @ e,
        r=r,
        qr=np.linalg.solve(G, r),
        theta=theta,
    )

    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return dict(path=str(path), sha256=common.sha(path))

    vectors = tmp_path / "vectors.npz"
    np.savez(
        vectors, **{s + "_" + k: v for s in ("M3600", "Mfinal") for k, v in raw.items()}
    )
    state = dict(
        parameter_norm=float(np.linalg.norm(theta)),
        parameter_sha256=common.array_sha(theta),
        complete_c_sha256="immutable_c",
        directions=[
            dict(column=j, kind="PDE" if j < 8 else "reference_G", group=str(j % 8))
            for j in range(16)
        ],
    )
    states = dict(M3600=state, Mfinal=copy.deepcopy(state))
    reference = dict(packet="fixed")
    result = write("old.json", dict(reference=reference, states=states))
    vector_entry = dict(path=str(vectors), sha256=common.sha(vectors))
    index = write(
        "old_index.json",
        dict(source_sha="old", files=dict(vectors=vector_entry, result=result)),
    )
    geometry = write(
        "geometry.json",
        dict(
            reference=reference,
            rows={s: dict(native_denominator=0.29104200262261154) for s in states},
        ),
    )
    geometry_index = write("geometry_index.json", dict(files=dict(result=geometry)))
    originals = {}
    packet = {
        k: (raw[k][:, :8] if k in ("P", "Y", "WY") else raw[k])
        for k in ("P", "Y", "WY", "r", "qr")
    }
    packet["theta_norm"] = state["parameter_norm"]
    for s in states:
        for rc in (1e-10, 1e-12):
            old = residual_candidate(packet, rc)
            old.update(state=s, columns=list(range(8)))
            originals[f"{s}_{rc:g}"] = write(f"{s}_{rc}_old.json", old)
    design = dict(
        states=states,
        rconds=[1e-10, 1e-12],
        parameter_count=22,
        FE_count=20,
        packet_identity=reference,
        original_C1_source="old",
        native_denominator=0.29104200262261154,
        original_R_candidates=originals,
        inputs=dict(
            index=index,
            result=result,
            vectors=vector_entry,
            field_geometry=geometry,
            field_geometry_index=geometry_index,
        ),
    )
    write("clock.json", dict(hard_deadline_monotonic=monotonic() + 2000))
    campaign = write(
        "campaign.json",
        dict(A=design, batch_clock="clock.json", review_publication="fixture"),
    )
    directory = tmp_path / "run"
    original_extract = runner.extract

    def guarded(saved, state, keys, design, columns=None):
        assert not any(k in keys for k in ("X", "GX", "e", "Ge"))
        return original_extract(saved, state, keys, design, columns)

    monkeypatch.setattr(runner, "extract", guarded)
    runner.build(campaign["path"], directory)
    monkeypatch.setattr(runner, "extract", original_extract)
    # Real forked scoring process sees the fully fsynced ledger; no fake PID.
    child = multiprocessing.get_context("fork").Process(
        target=runner.score, args=(directory,)
    )
    child.start()
    child.join(20)
    assert child.exitcode == 0
    monkeypatch.setattr(
        "src.solvers.feinn_native_constraint.constrained_minimum",
        lambda *a: (_ for _ in ()).throw(AssertionError("checker invoked optimizer")),
    )
    runner.check(directory, tmp_path / "check.json")
    checked = json.loads((tmp_path / "check.json").read_text())
    assert checked["status"] == "COMPLETE" and len(checked["configurations"]) == 4
    candidate = next(
        iter(
            json.loads((directory / "candidate_freeze.json").read_text())[
                "candidates"
            ].values()
        )
    )
    Path(candidate["path"]).write_text("{}")
    with pytest.raises(ValueError, match="FROZEN_INPUT_HASH"):
        runner.check(directory, tmp_path / "corrupt.json")
