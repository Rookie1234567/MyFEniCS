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
               residual_candidate_unlabeled=subset == "PDE8",
               oracle_data_role="REFERENCE_EXPOSED_LOCAL_ORACLE")
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


def saved_campaign(tmp_path, monkeypatch):
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
    np.savez(path, **{state + "_" + k: v for state in ("fixed", "second") for k, v in raw.items()})
    directions = [dict(column=j, kind="PDE" if j < 8 else "reference_G", group=str(j % 8)) for j in range(16)]
    state = dict(parameter_norm=float(np.linalg.norm(theta)), parameter_sha256=runner.array_sha(theta),
                 complete_c_sha256=runner.array_sha(c), directions=directions)
    reference = dict(packet="fixture_identity")
    def write(name, value):
        p = tmp_path / name
        p.write_text(json.dumps(value))
        return dict(path=str(p), sha256=runner.sha(p))
    states = dict(fixed=state, second=copy.deepcopy(state))
    result_entry = write("old.json", dict(reference=reference, states=states))
    vectors_entry = dict(path=str(path), sha256=runner.sha(path))
    index_entry = write("index.json", dict(source_sha="old_source", files=dict(vectors=vectors_entry, result=result_entry)))
    geometry_entry = write("geometry.json", dict(reference=reference, rows={s: dict(native_denominator=2) for s in states}))
    geometry_index = write("geometry_index.json", dict(files=dict(result=geometry_entry)))
    design = dict(states=states, inputs=dict(index=index_entry, result=result_entry, vectors=vectors_entry,
                  field_geometry=geometry_entry, field_geometry_index=geometry_index), original_C1_source="old_source",
                  packet_identity=reference, rconds=[1e-10, 1e-12], native_denominator=2, parameter_count=22, FE_count=20, review_sha="fixture_review")
    dpath = tmp_path / "design.json"
    dpath.write_text(json.dumps(design))
    output = tmp_path / "run"
    old_extract = runner.extract
    def observe(npz, state, keys, design, columns=None):
        if "e" in keys:
            ledger = json.loads((output / "candidate_freeze.json").read_text())
            assert len(ledger["candidates"]) == 4
            for item in ledger["candidates"].values():
                assert runner.sha(item["path"]) == item["sha256"]
        return old_extract(npz, state, keys, design, columns)
    monkeypatch.setattr(runner, "extract", observe)
    runner.run(dpath, output)
    # The fsync observer qualifies producer ordering only. It must not inspect
    # subsequently damaged files on behalf of the independent checker.
    monkeypatch.setattr(runner, "extract", old_extract)
    result = json.loads((output / "result.json").read_text())
    assert len(result["configurations"]) == 8 and not result["unknown"]
    runner.check(output / "result.json", tmp_path / "checker.json")
    assert json.loads((tmp_path / "checker.json").read_text())["optimize_calls"] == 0
    return runner, output, result, design


def test_complete_saved_array_pipeline_freezes_candidates_first(tmp_path, monkeypatch):
    runner, output, result, _ = saved_campaign(tmp_path, monkeypatch)
    checked = json.loads((tmp_path / "checker.json").read_text())
    assert checked["status"] == "COMPLETE_RECORDS_VERIFIED"
    assert checked["configuration_and_comparison_coverage"]["verified_comparison_points"] == 32
    assert checked["frozen_evidence"]["qualified"]
    assert checked["original_numerical_source"] == result["source_sha"]
    assert runner.sha(output / "result.json") == checked["result_sha256"]


@pytest.mark.parametrize("damage", ["empty", "duplicates", "missing", "extra", "unknown_state", "unknown_overlap", "unknown_unsourced", "four_points", "nonzero_zero", "endpoint_binding", "point_layout", "point_role", "global_pass", "top_pde", "top_production", "row_pde", "row_production", "row_official", "row_NN", "oracle_label"])
def test_batch_and_usage_corruption_rejected(tmp_path, monkeypatch, damage):
    runner, output, result, _ = saved_campaign(tmp_path, monkeypatch)
    rows = result["configurations"]
    if damage == "empty":
        result["configurations"] = []
    elif damage == "duplicates":
        result["configurations"] = [rows[0]] * len(rows)
    elif damage == "missing":
        rows.pop()
    elif damage == "extra":
        rows.append(copy.deepcopy(rows[0]))
        rows[-1]["rcond"] = 1e-8
    elif damage.startswith("unknown_"):
        result["unknown"] = [dict(state="fixed", status="UNKNOWN", phase="fixture", reason="retained_failure")]
        if damage == "unknown_state":
            result["unknown"][0]["state"] = "unexpected"
        if damage == "unknown_unsourced":
            result["unknown"][0]["source_sha"] = "another_source"
    elif damage == "four_points":
        rows[0]["points"] = dict(common=rows[0]["points"]["common"])
    elif damage == "nonzero_zero":
        rows[0]["points"]["zero"]["u"][0] = 1e-12
    elif damage == "endpoint_binding":
        rows[0]["common"]["u_F"][0] += .01
    elif damage == "point_layout":
        rows[0]["points"]["field"]["alpha"] = []
    elif damage == "point_role":
        rows[0]["points"]["common"]["data_role"] = "UNLABELED_PDE8_RESIDUAL_CANDIDATE"
    elif damage == "global_pass":
        result["status"] = "OFFICIAL_SOLVER_PASS"
    elif damage.startswith("top_"):
        result["pde_only_solve" if damage == "top_pde" else "production_initialization_allowed"] = True
    elif damage.startswith("row_"):
        rows[0][dict(row_pde="pde_only_solve", row_production="production_initialization_allowed", row_official="official_candidate_results", row_NN="true_NN_increment")[damage]] = True
    else:
        rows[0]["oracle_data_role"] = "UNLABELED"
    path = output / "damaged.json"
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError):
        runner.check(path, tmp_path / "negative.json")


@pytest.mark.parametrize("damage", ["missing_ledger", "wrong_ledger_hash", "no_freeze_events", "duplicate_freeze", "missing_reference", "duplicate_reference", "time_nan", "time_negative", "time_reverse", "missing_candidate", "candidate_hash", "candidate_source", "candidate_array", "candidate_state", "candidate_rcond", "candidate_allowlist", "candidate_label"])
def test_freeze_corruption_retains_numerics_but_never_qualifies(tmp_path, monkeypatch, damage):
    runner, output, result, _ = saved_campaign(tmp_path, monkeypatch)
    events = result["events"]
    if damage == "missing_ledger":
        (output / "candidate_freeze.json").unlink()  # Own tiny fixture only.
    elif damage == "wrong_ledger_hash":
        events[-1]["preceding_candidate_ledger_sha256"] = "0" * 64
    elif damage == "no_freeze_events":
        result["events"] = events[-1:]
    elif damage == "duplicate_freeze":
        events.insert(0, copy.deepcopy(events[0]))
    elif damage == "missing_reference":
        events.pop()
    elif damage == "duplicate_reference":
        events.append(copy.deepcopy(events[-1]))
    elif damage.startswith("time_"):
        events[0]["monotonic_since_start"] = dict(time_nan=float("nan"), time_negative=-1, time_reverse=events[-1]["monotonic_since_start"] + 1)[damage]
    else:
        key = next(iter(result["candidates"]))
        entry = result["candidates"][key]
        path = output / (key + "_candidate.json")
        if damage == "missing_candidate":
            path.unlink()
        elif damage == "candidate_hash":
            entry["sha256"] = "0" * 64
        else:
            candidate = json.loads(path.read_text())
            if damage == "candidate_source":
                candidate["source_sha"] = "wrong"
            elif damage == "candidate_array":
                candidate["array_sha256"] = "0" * 64
            elif damage == "candidate_state":
                candidate["state"] = "unexpected"
            elif damage == "candidate_rcond":
                candidate["basis"]["rcond"] = 1e-8
            elif damage == "candidate_allowlist":
                candidate["construction_array_members"].append("fixed_e")
            else:
                candidate["reference_used_for_construction"] = True
            path.write_text(json.dumps(candidate))
            entry["sha256"] = runner.sha(path)
    damaged = output / "damaged.json"
    damaged.write_text(json.dumps(result))
    checked = runner.check(damaged, tmp_path / "negative.json", native_attribution=True)
    assert checked["status"] == "PARTIAL"
    assert checked["raw_vector_and_certificate_validity"]["status"] == "PASS"
    assert checked["frozen_evidence"]["status"] == "UNKNOWN"
    assert not checked["candidate_freeze_order_verified"]
    assert not checked["unlabeled_two_state_admission"]["admitted"]
    assert not checked["native_direction_attribution"]
    assert not checked["unlabeled_two_state_admission"]["admitted"]


@pytest.mark.parametrize("kind", ["one", "legacy_state"])
def test_legal_partial_records_are_explicitly_partial_or_unknown(tmp_path, monkeypatch, kind):
    runner, output, result, _ = saved_campaign(tmp_path, monkeypatch)
    removed = result["configurations"].pop()
    row = dict(state=removed["state"], status="UNKNOWN", phase="retained_evaluation", reason="fixture_not_retained", source_sha=result["source_sha"])
    if kind == "one":
        row.update(subset=removed["subset"], rcond=removed["rcond"])
    else:
        result["configurations"] = []
    result["unknown"] = [row] if kind == "one" else [dict(row, state=s) for s in ("fixed", "second")]
    partial = output / "partial.json"
    partial.write_text(json.dumps(result))
    checked = runner.check(partial, tmp_path / "partial_check.json", native_attribution=True)
    assert checked["status"] == ("PARTIAL" if kind == "one" else "UNKNOWN")
    assert checked["configuration_and_comparison_coverage"]["unknown_configurations"] == (1 if kind == "one" else 8)
    assert not checked["native_direction_attribution"]
    assert not checked["unlabeled_two_state_admission"]["admitted"]


def test_checker_never_calls_optimizer_and_binds_frozen_input(tmp_path, monkeypatch):
    runner, output, result, _ = saved_campaign(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("checker invoked producer/optimization")
    from src.solvers import feinn_common_descent as core
    for name in ("common_minimum", "trust_ball", "residual_candidate"):
        monkeypatch.setattr(core, name, forbidden)
    monkeypatch.setattr(runner, "run", forbidden)
    for name in ("analyze_configuration", "residual_candidate"):
        monkeypatch.setattr(runner, name, forbidden)
    checked = runner.check(output / "result.json", tmp_path / "checked_no_optimizer.json", native_attribution=True)
    assert checked["status"] == "COMPLETE_RECORDS_VERIFIED"
    assert len(checked["native_direction_attribution"]) == 2
    with pytest.raises(ValueError, match="AUTHORIZED_RESULT_HASH"):
        runner.check(output / "result.json", tmp_path / "wrong_hash.json", expected_result_sha256="0" * 64)


@pytest.mark.parametrize("F,R,L,margin,expected", [(.998, .998, .998, 1e-12, "COMMON_DESCENT_AT_LEAST_0P1_PERCENT"), (1., 1., 1., 1e-12, "NO_0P1_PERCENT_COMMON_DESCENT_IN_RETAINED_BALL"), (.999, .999, .999, 1e-8, "UNKNOWN_THRESHOLD_BRACKET"), (.9992, .9992, .9991, .0002, "UNKNOWN_THRESHOLD_BRACKET")])
def test_threshold_roundoff_brackets_preserve_unknown(F, R, L, margin, expected):
    from benchmarks.check_feinn_common_descent import classify
    assert classify(F, R, L, margin, True) == expected


def test_unlabeled_admission_never_uses_oracle_common_point():
    from benchmarks.check_feinn_common_descent import admission
    rows = [dict(state=s, subset="PDE8", rcond=rc, recomputed_points=dict(
        zero=dict(native_linear=1.), residual=dict(F=.998, R=.998, native_linear=.9), common=dict(F=.5, R=.5)))
        for s in ("a", "b") for rc in (1e-10, 1e-12)]
    assert admission(rows, ["a", "b"], [1e-10, 1e-12], True)["admitted"]
    rows[0]["recomputed_points"]["residual"]["R"] = .999
    assert admission(rows, ["a", "b"], [1e-10, 1e-12], True)["status"] == "UNKNOWN"
    rows[0]["recomputed_points"]["residual"]["R"] = 1.1
    assert admission(rows, ["a", "b"], [1e-10, 1e-12], True)["status"] == "NOT_ADMITTED"
    assert not admission(rows, ["a", "b"], [1e-10, 1e-12], False)["admitted"]


@pytest.mark.parametrize("delta,expected", [(1., "DIRECTION_NATIVE_CONFLICT"), (-3., "LINEAR_STEP_OVERSHOOT"), (0., "UNKNOWN")])
def test_frozen_native_attribution_separates_conflict_and_overshoot(delta, expected):
    from src.solvers.feinn_diagnostic_algebra import frozen_direction_attribution
    old = np.array([1. + 1j])
    columns = np.array([[delta * (1. + 1j)]])
    raw = dict(e=old, Ge=old, r=old, qr=old, X=columns, GX=columns, Y=columns, WY=columns)
    checked = frozen_direction_attribution(raw, [1.], 2)
    assert checked["classification"] == expected
    assert checked["evaluated_s"] == [0, 1] and not checked["new_candidate_generated"]
    assert checked["norms"]["N"]["b"] == pytest.approx(2 * delta)
    assert checked["norms"]["N"]["c"] == pytest.approx(delta * delta)
    if expected == "LINEAR_STEP_OVERSHOOT":
        assert checked["analytic_nonzero_intersection_diagnostic_only"] == pytest.approx(2 / 3)
