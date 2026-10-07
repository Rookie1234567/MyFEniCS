"""Meaningful opt-in global support, hard learning budget and scalar isolation."""

import json

import numpy as np
import pytest

from src.solvers.neural_wave_moments import Patch
from src.solvers.neural_wave_multiscale import (
    bounded_direction_optimize,
    MultiscaleSupportPolicy,
)
from src.solvers.neural_wave_multiscale_validation import continuation_gate
from src.io.neural_wave_campaign import load_wave, training_open_allowed, ROOT


def test_global_window_is_not_a_finite_bump():
    p = Patch((0, 0, 0), (1, 1, 1), kind="global")
    np.testing.assert_array_equal(p.window(np.array([[0, 0, 0], [100, 4, -8]])), [1, 1])
    assert Patch((0, 0, 0), (1, 1, 1)).window(np.array([[100, 4, -8]]))[0] == 0
    with pytest.raises(ValueError):
        Patch((0, 0, 0), (1, 1, 1), kind="coefficient_phase")
    from src.solvers.neural_wave_local_action import LocalWaveAction

    with pytest.raises(ValueError, match="GLOBAL_SUPPORT"):
        LocalWaveAction(None, [0], support_kind="global")


def test_hard_evaluation_guard_retains_evaluated_best_and_last_trial():
    evaluated = []
    q0 = np.array([[3.0, 2.0, 1.0]])

    def objective(q):
        evaluated.append(q.copy())
        # A high-accuracy quadratic needs more than a single call.
        return (-float(np.sum(q * q)), None, None, None, -2 * q)

    seed = objective(q0)
    q, value, record = bounded_direction_optimize(objective, q0, seed, 4, maxeval=1)
    assert record["function_calls"] == 1 and len(evaluated) == 2
    assert record["extra_result_evaluation_count"] == 0
    assert any(np.array_equal(q, e) for e in evaluated)
    assert value[0] == -np.sum(q * q)


class Moments:
    rows = np.arange(12).reshape(4, 3)

    def cells(self, p):
        return np.arange(4)


def test_all_scales_persist_and_rotation_is_independent_of_residual():
    policy = MultiscaleSupportPolicy(
        dict(bounds_nm=[[-1, 1], [-1, 1], [-1, 1]], cells=[2, 2, 2]), Moments()
    )
    seen = set()
    for i in range(400):
        p, rotation, _ = policy.preselect(np.zeros(12, dtype=complex), i)
        assert len(p) == 8 and {v.level for v in p} == {-1, 0, 1, 2}
        seen.add(rotation)
    assert len(seen) > 100


def test_nonhermitian_residual_location_can_miss_best_trial():
    A = np.array([[1, 4], [2, 0]], complex)
    r = np.array([1, 0], complex)
    score = [
        abs(np.vdot(A[:, j], r)) ** 2 / np.vdot(A[:, j], A[:, j]).real for j in range(2)
    ]
    np.testing.assert_allclose(score, [0.2, 1])
    assert abs(r[1]) == 0 and abs((A.conj().T @ r)[1]) > 0


def test_v32_schema_labels_and_legacy_states_are_rejected():
    spec = load_wave(
        ROOT / "input/task042extra_feinn_5nm/v32_fixed_multiscale_wave.dat"
    )
    assert spec["campaign_version"] == 32 and spec["max_seconds"] == 14400
    design = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v32.json").read_text()
    )
    active = ROOT / "benchmarks/artifacts/task42extra/v32/v32_fixed_multiscale_wave"
    design["active_training_artifact"] = str(active)
    assert training_open_allowed(active / "validation_scalars_1.json", design)
    assert training_open_allowed(active / "basis/block_00000_00003.npz", design)
    for name in [
        "index_e3_reference.json",
        "v31/v31_learned_block_wave/basis/state_03858.npz",
        "v32/v32_fixed_validate_1/scoring_record.json",
    ]:
        assert not training_open_allowed(
            ROOT / "benchmarks/artifacts/task42extra" / name, design
        )


def test_validation_threshold_requires_residual_and_both_field_failures(tmp_path):
    (tmp_path / "basis").mkdir()
    (tmp_path / "basis/committed.json").write_text("{}")
    assert (
        continuation_gate(tmp_path, 512, 0, {}) == "INDEPENDENT_VALIDATION_REQUESTED_1"
    )
    record = dict(
        schema="multiscale.validation.scalars.v1",
        node=1,
        boundary_sha256="hash",
        native_relative=0.3,
        augmented_relative=0.3,
        scattered_E_relative=0.9,
        scattered_curl_relative=0.9,
        source_sha="s",
        scoring_result_sha256="r",
        **{"continue": True},
    )
    (tmp_path / "validation_scalars_1.json").write_text(json.dumps(record))
    assert (
        continuation_gate(tmp_path, 1024, 0, {}) == "INDEPENDENT_VALIDATION_REQUESTED_2"
    )
    record.update(node=2, **{"continue": False})
    (tmp_path / "validation_scalars_2.json").write_text(json.dumps(record))
    assert continuation_gate(tmp_path, 1024, 0, {}) == "MULTISCALE_NO_USEFUL_PROGRESS"
    record.update(scattered_E_relative=0.4, **{"continue": True})
    (tmp_path / "validation_scalars_2.json").write_text(json.dumps(record))
    assert continuation_gate(tmp_path, 1024, 0, {}) is None
    record["reference_c"] = [1, 2, 3]
    (tmp_path / "validation_scalars_2.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="SCHEMA"):
        continuation_gate(tmp_path, 1024, 0, {})


def test_actual_optimizer_never_forces_a_change_at_stationary_seed():
    q = np.zeros((1, 3))

    def objective(q):
        return (-float(np.sum(q * q)), None, None, None, -2 * q)

    actual, _, r = bounded_direction_optimize(objective, q, objective(q), 4)
    np.testing.assert_array_equal(actual, q)
    assert r["function_calls"] == 1
