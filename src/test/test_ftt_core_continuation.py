"""Small fixtures for exact R4 imports, unchanged defaults and finite policies."""

from copy import deepcopy
import json
from pathlib import Path
from time import monotonic
import numpy as np
import pytest
import torch

from src.solvers.ftt_core_continuation import (
    policy_for,
    identity,
    axis_order,
    new_counts,
    charged_iterations,
    trend_decision,
    scalar_pending,
    validate_parent,
)
from src.solvers.ftt_bloch_field import BlochFTTField, scalar_continuation
from src.solvers.ftt_core_training import CoreBoundary, run_core_training
from src.solvers.ftt_conditional_core import hidden_parameters
from src.solvers.ftt_factored_moments import FactoredMomentMap
from src.solvers.optimization_checkpoint import (
    capture,
    restore,
    atomic_write,
    digest,
    load_checkpoint,
)
from src.test.test_ftt_bloch import phase
from src.test.test_ftt_structure import BOX, fixture
from src.test.test_ftt_conditional_core import TinyAction


def scalar(R, E, H=None):
    H = E if H is None else H
    return dict(
        native_relative=R,
        augmented_relative=R,
        scattered_E_relative=E,
        scattered_H_relative=H,
        scattered_curl_relative=H,
    )


def parent_fixture(tmp_path):
    model = BlochFTTField(BOX, "fttnn", phase())
    model.nonzero_qualification_state()
    position = dict(
        round=4,
        complete_rounds=4,
        axis_index=0,
        phase="core",
        slow_streak=1,
        round_start_native=0.44455,
    )
    counts = dict(
        core_visits=12,
        LSMR_iterations=3358,
        LSMR_unretained_iterations_upper_bound=0,
        accepted_core_updates=12,
        effective_core_updates=12,
        accepted_hidden_updates=4,
        effective_hidden_updates=4,
        hidden_actual_calls=53,
        K=3394,
        KH=3394,
        B=3382,
        BH=3394,
        round_audits=4,
        uncommitted_K=0,
        uncommitted_KH=0,
    )
    costs = dict(
        core_solve_and_check=2.0,
        real_acceptance=1.0,
        hidden=0.3,
        persistence=0.2,
        audit=0.1,
    )
    binding = dict(
        source_sha="a" * 40,
        input_sha256="b" * 64,
        design_sha256="c" * 64,
        native_sha256="d" * 64,
        moments_sha256="e" * 64,
        phase_sha256="f" * 64,
        model_kind="fttnn",
        metric_kind="native_euc",
        route="BLOCH_FTTNN_CORE_LEARNED",
        phase_definition=phase(),
        reference_used_for_training=False,
        reference_sha256=None,
        features_reference_exposed=False,
        pde_only_solve=True,
        production_initialization_allowed=False,
        official_candidate_results=False,
        pde_only_solver_qualified=False,
        route_origin_monotonic=monotonic(),
    )
    mapping = FactoredMomentMap(fixture())
    action = TinyAction(np.eye(6, dtype=np.complex128))
    action.audit = lambda c: dict(
        native_relative=float(
            np.linalg.norm(action.apply(c) - action.f) / action.bnorm
        ),
        augmented_relative=float(
            np.linalg.norm(action.apply(c) - action.f) / action.bnorm
        ),
    )
    action.counts = {}
    action.costs = {}
    c = mapping.forward(model)
    state = capture(
        model,
        CoreBoundary(position),
        dict(
            binding,
            position=position,
            counts=counts,
            costs=costs,
            rounds=[
                dict(
                    round=i,
                    native=0.7,
                    isolated_validation_scalars=scalar(0.7, 0.4),
                    predeclared_continuation_allowed=False,
                )
                for i in range(4)
            ],
        ),
    )
    state.update(
        c=c,
        r=action.apply(c) - action.f,
        last_completed_hidden_optimizer={"old": "evidence_only"},
    )
    path = tmp_path / "parent.pt"
    atomic_write(path, lambda stream: torch.save(state, stream))
    parent = dict(
        path=str(path),
        sha256=digest(path),
        bytes=path.stat().st_size,
        binding={k: binding[k] for k in ("source_sha", "route", "phase_sha256")},
        inherited_counts=counts,
    )
    return model, action, state, parent, binding


def test_old_policy_stays_false_new_trend_is_eligible():
    assert not scalar_continuation(
        4, 0.444550296117, 0.132626683892, 0.132884263175, 0.741414507640
    )
    result = trend_decision(
        8,
        scalar(0.444550296117, 0.132626683892, 0.132884263175),
        scalar(0.741414507640, 0.471857766118, 0.472274564567),
        policy_for(True),
        learned=True,
    )
    assert result["allowed"] and result["ordinary"]


@pytest.mark.parametrize(
    "values",
    [scalar(0.7, 0.5), scalar(0.4, 0.8), scalar(float("nan"), 0.1), scalar(-1, 0.1)],
)
def test_loss_only_field_only_nonfinite_negative_are_not_trend_pass(values):
    assert not trend_decision(
        8, values, scalar(0.7, 0.4), policy_for(True), learned=True
    )["allowed"]


def test_diagnostic_and_absolute_round_cap_and_refinement():
    p = policy_for(True)
    assert trend_decision(6, scalar(0.9, 0.8), None, p, learned=True)["allowed"]
    assert not trend_decision(
        8, scalar(0.1, 0.1), scalar(0.2, 0.2), policy_for(False), learned=False
    )["allowed"]
    assert not trend_decision(12, scalar(0.1, 0.1), scalar(0.2, 0.2), p, learned=True)[
        "allowed"
    ]
    assert trend_decision(
        10, scalar(9.8e-6, 9.9e-4), scalar(1e-5, 1e-3), p, learned=True
    )["refinement"]
    z = trend_decision(8, scalar(0, 0), scalar(0, 0), p, learned=True)
    assert z["zero_metric_requires_joint_verification"] and "ratios_R_E_H" not in z


def test_axes_pending_and_inherited_budgets():
    assert axis_order(4) == [2, 0, 1] and axis_order(5) == [1, 0, 2]
    assert axis_order(6) == [2, 0, 1]
    assert not scalar_pending({"complete_rounds": 4}, [{"round": 3}], policy_for(True))
    assert scalar_pending({"complete_rounds": 6}, [{"round": 5}], policy_for(True))
    assert not scalar_pending(
        {"complete_rounds": 6},
        [{"round": 5, "isolated_validation_scalars": {}}],
        policy_for(True),
    )
    work = new_counts(
        {
            "core_visits": 36,
            "LSMR_iterations": 10558,
            "LSMR_unretained_iterations_upper_bound": 0,
        },
        {
            "core_visits": 12,
            "LSMR_iterations": 3358,
            "LSMR_unretained_iterations_upper_bound": 0,
        },
    )
    assert work["core_visits"] == 24 and charged_iterations(work) == 7200
    with pytest.raises(ValueError):
        new_counts({"x": 1}, {"x": 2})
    assert identity(policy_for(True)) != identity(policy_for(False))


@pytest.mark.parametrize(
    "bad", ["hash", "phase", "label", "counter", "partial", "buffer"]
)
def test_parent_rejects_wrong_or_incomplete_state(tmp_path, bad):
    m, _, state, parent, binding = parent_fixture(tmp_path)
    if bad == "hash":
        with pytest.raises(ValueError):
            load_checkpoint(parent["path"], "0" * 64)
        return
    state = deepcopy(state)
    if bad == "phase":
        state["metadata"]["phase_sha256"] = "0" * 64
    if bad == "label":
        state["metadata"]["reference_used_for_training"] = True
    if bad == "counter":
        state["metadata"]["counts"]["core_visits"] = 0
    if bad == "partial":
        state["optimizer"]["axis_index"] = 1
    if bad == "buffer":
        state["model"]["phase_wavevector"][0] += 1
    with pytest.raises(ValueError):
        validate_parent(state, parent, binding, m)


def test_nonzero_same_parent_two_forks_and_no_round4_rerun(tmp_path):
    m, action, state, parent, binding = parent_fixture(tmp_path)
    h0 = [p.detach().clone() for p in hidden_parameters(m)]
    outputs = []
    for learned in (True, False):
        restore(m, CoreBoundary({}), state)
        result = run_core_training(
            action,
            fixture(),
            m,
            tmp_path / str(learned),
            binding,
            monotonic() - 1,
            lambda *_: None,
            learned=learned,
            validation_callback=lambda *_: pytest.fail(
                "old R4 must not be scored again"
            ),
            parent_checkpoint=parent,
            execution_policy=policy_for(learned),
        )
        assert result["position"]["round"] == 4 and result["new_complete_rounds"] == 0
        assert (
            result["new_counts"]["hidden_actual_calls"] == 0
            and result["new_counts"]["core_visits"] == 0
        )
        assert result["counts"]["LSMR_iterations"] == 3358
        assert result["rounds"][-1]["predeclared_continuation_allowed"] is False
        assert (
            result["checkpoint"]["metadata"]["production_initialization_allowed"]
            is False
        )
        saved = load_checkpoint(
            tmp_path / str(learned) / "checkpoints" / result["checkpoint"]["name"],
            result["checkpoint"]["sha256"],
        )
        assert all(
            p.detach().equal(q) for p, q in zip(hidden_parameters(m), h0, strict=True)
        )
        outputs.append(saved)
    assert all(outputs[0]["model"][k].equal(v) for k, v in outputs[1]["model"].items())
    assert np.array_equal(outputs[0]["c"], outputs[1]["c"]) and np.array_equal(
        outputs[0]["r"], outputs[1]["r"]
    )


def test_atomic_interruption_preserves_complete_state(tmp_path):
    _, _, state, parent, _ = parent_fixture(tmp_path)
    old = Path(parent["path"]).read_bytes()

    def fail(_):
        raise RuntimeError("half write")

    with pytest.raises(RuntimeError):
        atomic_write(parent["path"], fail)
    assert Path(parent["path"]).read_bytes() == old
    assert (
        load_checkpoint(parent["path"], parent["sha256"])["optimizer"]
        == state["optimizer"]
    )


def test_four_new_rounds_ignore_old_stagnation_and_preserve_frozen_hidden(
    tmp_path, monkeypatch
):
    m, action, state, parent, binding = parent_fixture(tmp_path)
    axes = []

    def solve(op, b, maxiter):
        axes.append(op.axis)
        return np.zeros(op.size, dtype=np.complex128), dict(iterations=1)

    monkeypatch.setattr("src.solvers.ftt_core_training.solve_core", solve)
    calls = []

    def validation(number, *_):
        calls.append(number)
        return scalar(0.8, 0.6)

    result = run_core_training(
        action,
        fixture(),
        m,
        tmp_path / "freeze",
        binding,
        monotonic() + 300,
        lambda *_: None,
        learned=False,
        validation_callback=validation,
        parent_checkpoint=parent,
        execution_policy=policy_for(False),
    )
    assert axes == [2, 0, 1, 1, 0, 2, 2, 0, 1, 1, 0, 2]
    assert calls == [6, 8] and result["new_complete_rounds"] == 4
    assert (
        result["new_counts"]["core_visits"] == 12
        and result["counts"]["core_visits"] == 24
    )
    assert result["new_counts"]["hidden_actual_calls"] == 0
    assert result["freeze_hidden_bitwise_unchanged"]
    assert result["stop_reason"] == "AUTHORIZED_TOTAL_ROUND_LIMIT"


def test_pending_scalar_recovery_and_source_guard(tmp_path, monkeypatch):
    m, action, state, parent, binding = parent_fixture(tmp_path)
    visits = []

    def solve(op, b, maxiter):
        visits.append(op.axis)
        return np.zeros(op.size, dtype=np.complex128), dict(iterations=1)

    monkeypatch.setattr("src.solvers.ftt_core_training.solve_core", solve)
    artifact = tmp_path / "recover"

    def failed(number, *_):
        assert number == 6
        raise RuntimeError("scalar writer failed after committed round")

    kwargs = dict(
        learned=False, parent_checkpoint=parent, execution_policy=policy_for(False)
    )
    with pytest.raises(RuntimeError, match="scalar writer failed"):
        run_core_training(
            action,
            fixture(),
            m,
            artifact,
            binding,
            monotonic() + 300,
            lambda *_: None,
            validation_callback=failed,
            **kwargs,
        )
    assert len(visits) == 6
    bad = dict(binding, source_sha="0" * 40)
    with pytest.raises(ValueError, match="CONTINUATION_RESUME_IDENTITY"):
        run_core_training(
            action,
            fixture(),
            m,
            artifact,
            bad,
            monotonic() + 300,
            lambda *_: None,
            **kwargs,
        )
    # Simulate loss of the final companion-index write, keeping the valid pointer.
    ip = artifact / "checkpoint_index.json"
    index = json.loads(ip.read_text())
    ip.write_text(json.dumps(index[:-1]))
    recovered = []
    result = run_core_training(
        action,
        fixture(),
        m,
        artifact,
        binding,
        monotonic() + 300,
        lambda *_: None,
        validation_callback=lambda n, *_: recovered.append(n) or scalar(0.8, 0.6),
        **kwargs,
    )
    assert recovered == [6, 8] and len(visits) == 12
    assert result["new_counts"]["core_visits"] == 12


def test_explicit_v43_inputs_resources_and_label_firewall():
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths
    from src.io.ftt_continuation_campaign import STAGES, DESIGN, validate_design
    from src.runners.ftt_worker import training_allowed
    from src.runners.neural_wave_campaign import window
    from src.runners.block_wave_admission import pool, wait_limit

    d = json.loads(DESIGN.read_text())
    for stage in STAGES:
        s = load_wave(ROOT / "input/task042extra_feinn_5nm" / (stage + ".dat"))
        assert s["campaign_version"] == 43 and profile_paths(s)["root"].name == "v43"
        assert window(s)["budget_s"] == 28800
    active = ROOT / "benchmarks/artifacts/task42extra/v43/test"
    assert training_allowed(ROOT / d["parent_checkpoint"]["path"], d, active, False)
    for key in ("reference", "gram"):
        assert not training_allowed(ROOT / d[key]["path"], d, active, False)
    assert not training_allowed(
        ROOT / "benchmarks/artifacts/task42extra/v39/fit/checkpoints/a.pt",
        d,
        active,
        False,
    )
    assert pool(ROOT / "tmp/task42extra/v43/durable").parent.name == "v43"
    assert wait_limit(ROOT / "tmp/task42extra/v43/durable") == 900
    bad = deepcopy(d)
    bad["execution_policies"]["learned"]["ordinary_ratio"] = 0.95
    with pytest.raises(ValueError):
        validate_design(bad)


def test_joint_feedback_strict_bool_identity_and_no_vector(tmp_path):
    from src.runners.ftt_continuation_feedback import read_verdict

    request = dict(
        source_sha="a", input_sha256="b", design_sha256="c", boundary_sha256="d"
    )
    good = dict(
        request,
        schema="ftt.joint-boundary.scalar-verdict.v1",
        joint_pass=False,
        mapping_and_quadrature_pass=True,
        reference_feedback="booleans_and_identity_only",
        production_initialization_allowed=False,
    )
    p = tmp_path / "verdict.json"
    p.write_text(json.dumps(good))
    assert read_verdict(p, request) == good
    for wrong in (
        {"reference_vector": [1, 2]},
        {"joint_pass": 1},
        {"boundary_sha256": "wrong"},
        {"production_initialization_allowed": True},
    ):
        p.write_text(json.dumps(dict(good, **wrong)))
        with pytest.raises(ValueError):
            read_verdict(p, request)
