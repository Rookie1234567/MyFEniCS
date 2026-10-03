import numpy as np
import pytest

from src.solvers.feinn_native_network_witness import two_forwards, WitnessBoundaryWriter


@pytest.mark.parametrize("failure", [None, "original", "trial"])
def test_two_forward_transaction_restores_after_failure(failure):
    theta = np.array([1.0, 2.0])
    step = np.array([0.01, -0.02])
    current = theta.copy()
    buffers = {"fixed": np.array([0.5])}
    original = buffers["fixed"].copy()
    count = 0

    def assign(value):
        nonlocal current
        current = value.copy()

    def forward():
        nonlocal count
        count += 1
        buffers["fixed"] += 1
        if failure == ("original" if count == 1 else "trial"):
            raise RuntimeError("explicit forward fixture failure")
        return current.astype(np.complex128)

    def snapshot():
        return {key: value.copy() for key, value in buffers.items()}

    def restore(values):
        buffers.update(values)

    if failure:
        with pytest.raises(RuntimeError, match="fixture failure"):
            two_forwards(
                theta,
                step,
                assign,
                forward,
                lambda: current,
                snapshot,
                restore,
                theta.astype(complex),
            )
    else:
        c0, c1, proof = two_forwards(
            theta,
            step,
            assign,
            forward,
            lambda: current,
            snapshot,
            restore,
            theta.astype(complex),
        )
        assert (
            np.array_equal(c0, theta)
            and np.array_equal(c1, theta + step)
            and proof["theta_restored"]
        )
    assert count == (1 if failure == "original" else 2)
    assert np.array_equal(current, theta) and np.array_equal(buffers["fixed"], original)


def test_bad_original_identity_stops_before_trial_and_restores():
    theta = np.ones(2)
    calls = []

    def forward():
        calls.append(1)
        return np.ones(2, dtype=complex) * 2

    with pytest.raises(ValueError, match="ORIGINAL_COMPLETE_C"):
        two_forwards(
            theta,
            np.zeros(2),
            lambda _: None,
            forward,
            lambda: theta,
            lambda: {},
            lambda _: None,
            theta.astype(complex),
        )
    assert len(calls) == 1


def test_FE_import_of_witness_stays_Torch_free():
    import subprocess
    import sys

    assert (
        subprocess.run(
            [
                sys.executable,
                "-c",
                'import sys; import src.solvers.feinn_native_network_witness; assert "torch" not in sys.modules',
            ],
            check=False,
        ).returncode
        == 0
    )


def test_independent_witness_classification_and_count_contract():
    from benchmarks.check_feinn_native_witness import evaluate
    from src.solvers.neural_fe_action_packet import array_hash
    from src.solvers.feinn_saved_attribution import DiagnosticActions
    from types import SimpleNamespace

    theta = np.array([1.0, 2.0])
    c0 = theta.astype(np.complex128)
    delta = -0.02 * theta
    cl = c0 + delta
    ca = cl + 0.001 * delta
    arrays = {
        "M_theta_zero": theta,
        "M_theta_trial": theta + delta,
        "M_theta_restored": theta.copy(),
        "M_delta_theta": delta,
    }
    for kind, c in (("zero", c0), ("linear", cl), ("actual", ca)):
        for prefix in ("c", "r", "qr", "e", "Ge"):
            arrays["M_" + prefix + "_" + kind] = c.copy()
    proof = dict(
        theta_restored=True,
        buffers_restored=True,
        theta_zero_sha256=array_hash(theta),
        theta_trial_sha256=array_hash(theta + delta),
        c_zero_sha256=array_hash(c0),
        c_actual_sha256=array_hash(ca),
        original_c_identity_relative=0.0,
        operator_pairings={"native": 0.0},
    )
    meta = dict(native_denominator=1.0, d_G=1.0, rows={"M": proof})
    predicted = {
        "raw_points": {"native_constrained": dict(N=0.98**2, R=0.98**2, F=0.98**2)}
    }
    row = evaluate(arrays, "M", predicted, meta)
    assert row["local_pre_FE_support"] and row["nonlinear_defect"] == pytest.approx(
        0.001
    )
    arrays["M_qr_actual"] *= 1.2
    row = evaluate(arrays, "M", predicted, meta)
    assert row["failure_quantities"] == ["dual_nonincrease"]
    arrays["M_theta_restored"][0] += 1
    with pytest.raises(ValueError, match="RESTORED_PARAMETERS"):
        evaluate(arrays, "M", predicted, meta)
    packet = SimpleNamespace(counts=dict(A=0, AH=0))
    factor = SimpleNamespace(solves=0)
    manifest = dict(
        supervision_budget_origin_monotonic=__import__("time").perf_counter(),
        supervised_limit_seconds=600,
    )
    ops = DiagnosticActions(
        packet, np.eye(2), factor, dict(A=6, AH=0, Gsolve=4, G_matvec=8), manifest
    )
    for _ in range(4):
        ops.gm(np.ones(2))
        factor.solves += 1
    assert ops.record()["G_matvec"] == 8
    with pytest.raises(RuntimeError, match="CAP_G_matvec"):
        ops.gm(np.ones(2))


def test_multiple_partial_and_final_boundaries_are_matched_and_immutable(tmp_path):
    import json
    from src.runners.feinn_common_descent_arrays import sha

    writer = WitnessBoundaryWriter(tmp_path)
    first, first_path = writer.save({"M_c": np.array([1j])}, {"status": "PARTIAL"})
    original_bytes = first_path.read_bytes()
    writer.save({"M_c": np.array([2j]), "F_c": np.array([3j])}, {"status": "PARTIAL"})
    final, path = writer.save(
        {"M_c": np.array([2j]), "F_c": np.array([3j])}, {"status": "FROZEN"}
    )
    assert final["boundary_sequence"] == 3 and first_path.read_bytes() == original_bytes
    for number in (1, 2, 3):
        boundary = json.loads(
            (tmp_path / f"witness_boundary_{number:04d}.json").read_text()
        )
        assert boundary["vectors"]["sha256"] == sha(boundary["vectors"]["path"])
    with np.load(path) as data:
        assert np.array_equal(data["M_c"], np.array([2j]))
    assert first["boundary_sequence"] == 1
    with pytest.raises(ValueError, match="IMMUTABLE_BOUNDARY"):
        WitnessBoundaryWriter(tmp_path).save({"M_c": np.ones(1)}, {"status": "PARTIAL"})


def test_exception_boundary_keeps_successful_previous_snapshot(tmp_path):
    import json

    writer = WitnessBoundaryWriter(tmp_path)
    try:
        writer.save({"M_c": np.ones(2)}, {"status": "PARTIAL"})
        raise RuntimeError("retained original worker error")
    except RuntimeError:
        writer.save({"M_c": np.ones(2)}, {"status": "PARTIAL_ERROR"})
    assert (
        json.loads((tmp_path / "witness_boundary_0001.json").read_text())["status"]
        == "PARTIAL"
    )
    assert (
        json.loads((tmp_path / "witness_boundary_0002.json").read_text())["status"]
        == "PARTIAL_ERROR"
    )


def test_failed_attempt_counts_cannot_disappear_from_replay_caps():
    from benchmarks.check_feinn_native_witness import replay_operation_account

    actions = dict(A=8, AH=0, Gsolve=4, G_matvec=12)
    result = dict(
        complete_network_forwards=4,
        Gram_factor_lifecycles=1,
        JVP=0,
        VJP=0,
        prior_failed_attempt=dict(
            operation_upper_bound=dict(
                A=6,
                AH=0,
                Gsolve=4,
                G_matvec=8,
                network_forward=4,
                Gram_factor=1,
                JVP=0,
                VJP=0,
            )
        ),
    )
    combined = replay_operation_account(actions, result)
    assert combined == dict(
        A=14,
        AH=0,
        Gsolve=8,
        G_matvec=20,
        network_forward=8,
        Gram_factor=2,
        JVP=0,
        VJP=0,
    )
    actions["A"] = 11
    with pytest.raises(ValueError, match="INCLUDING_FAILED"):
        replay_operation_account(actions, result)
