from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import src.studies.task44_surrogate as surrogate_module
from src.studies.task44_surrogate import (
    Matern52ARDRegressor,
    MultiOutputMatern52ARDGP,
    OutputStandardization,
    baseline_predictions,
    denormalize_thicknesses,
    geometry_key,
    initial_geometry_partitions,
    latin_hypercube,
    normalize_thicknesses,
    regression_metrics,
    validate_disjoint_geometry_groups,
)


def _synthetic_outputs(thicknesses_nm: np.ndarray) -> np.ndarray:
    x = normalize_thicknesses(thicknesses_nm)
    return np.column_stack(
        (
            0.1 + 0.02 * np.sin(2.0 * np.pi * x[:, 0]) + 0.01 * x[:, 1],
            0.8 + 0.04 * x[:, 2] * x[:, 3],
            0.09 + 0.015 * np.exp(-np.sum((x - 0.5) ** 2, axis=1)),
        )
    )


def _reference_matern52_covariance(
    left: np.ndarray,
    right: np.ndarray,
    length_scales: np.ndarray,
    signal_scale: float,
) -> np.ndarray:
    """Small loop-based reference independent of the production vectorization."""
    covariance = np.empty((left.shape[0], right.shape[0]), dtype=np.float64)
    for i, left_row in enumerate(left):
        for j, right_row in enumerate(right):
            scaled_radius = np.sqrt(5.0) * np.linalg.norm(
                (left_row - right_row) / length_scales
            )
            covariance[i, j] = signal_scale**2 * (
                1.0 + scaled_radius + scaled_radius**2 / 3.0
            ) * np.exp(-scaled_radius)
    return covariance


def test_latin_hypercube_is_reproducible_stratified_and_in_bounds():
    first = latin_hypercube(12, seed=440732)
    second = latin_hypercube(12, seed=440732)

    np.testing.assert_array_equal(first, second)
    normalized = normalize_thicknesses(first)
    for column in range(6):
        np.testing.assert_array_equal(
            np.sort(np.floor(normalized[:, column] * 12).astype(int)),
            np.arange(12),
        )


def test_initial_train_development_and_blind_geometry_groups_are_disjoint():
    first = initial_geometry_partitions(seed=440731)
    second = initial_geometry_partitions(seed=440731)

    assert {name: values.shape for name, values in first.items()} == {
        "training": (20, 6),
        "development": (10, 6),
        "blind_test": (10, 6),
    }
    for name in first:
        np.testing.assert_array_equal(first[name], second[name])
    validate_disjoint_geometry_groups(first)
    expected_anchors = {
        geometry_key([0.5] * 6),
        geometry_key([0.75] * 6),
        geometry_key([1.0] * 6),
        geometry_key([0.5, 1.0, 0.5, 1.0, 0.5, 1.0]),
    }
    assert expected_anchors.issubset(
        {geometry_key(row) for row in first["training"]}
    )


def test_duplicate_geometry_is_rejected_within_or_across_groups():
    point = [[0.5] * 6]
    with pytest.raises(ValueError, match="duplicate geometry"):
        validate_disjoint_geometry_groups({"training": point, "blind_test": point})
    with pytest.raises(ValueError, match="duplicate geometry"):
        validate_disjoint_geometry_groups({"training": point + point})


def test_input_and_training_only_output_normalization_round_trip():
    inputs = np.array([[0.5] * 6, [0.75] * 6, [1.0] * 6])
    np.testing.assert_allclose(
        denormalize_thicknesses(normalize_thicknesses(inputs)), inputs, atol=0.0
    )
    training_outputs = np.array(
        [[0.1, 0.8, 0.09], [0.2, 0.7, 0.11], [0.3, 0.6, 0.13]]
    )
    withheld_outputs = np.array([[50.0, 60.0, 70.0]])
    scaler = OutputStandardization.fit(training_outputs)
    np.testing.assert_allclose(scaler.mean, training_outputs.mean(axis=0))
    assert not np.any(np.isclose(scaler.mean, withheld_outputs.mean(axis=0)))
    np.testing.assert_allclose(
        scaler.inverse_transform(scaler.transform(training_outputs)),
        training_outputs,
    )


def test_metrics_are_computed_in_original_output_units():
    actual = np.array([[0.10, 0.80, 0.09], [0.20, 0.70, 0.11]])
    predicted = np.array([[0.11, 0.78, 0.095], [0.18, 0.73, 0.10]])
    metrics = regression_metrics(actual, predicted)

    assert metrics["R_total"] == {
        "mae": pytest.approx(0.015),
        "max_abs": pytest.approx(0.02),
        "actual_range": pytest.approx(0.1),
    }
    assert metrics["T_total"]["mae"] == pytest.approx(0.025)
    assert metrics["R00_total"]["max_abs"] == pytest.approx(0.01)


def test_synthetic_three_output_gp_and_baselines_are_finite():
    training_x = latin_hypercube(10, seed=440734)
    evaluation_x = latin_hypercube(3, seed=440735)
    training_y = _synthetic_outputs(training_x)

    model = MultiOutputMatern52ARDGP(max_iterations=30).fit(training_x, training_y)
    predicted, predicted_std = model.predict(evaluation_x, return_std=True)
    baselines = baseline_predictions(training_x, training_y, evaluation_x)

    assert predicted.shape == (3, 3)
    assert predicted_std.shape == (3, 3)
    assert np.all(np.isfinite(predicted))
    assert np.all(np.isfinite(predicted_std))
    assert np.all(predicted_std >= 0.0)
    assert set(baselines) == {"mean", "linear"}
    assert all(np.all(np.isfinite(value)) for value in baselines.values())
    assert set(regression_metrics(_synthetic_outputs(evaluation_x), predicted)) == {
        "R_total",
        "T_total",
        "R00_total",
    }


def test_fixed_matern52_posterior_matches_independent_closed_form(monkeypatch):
    training_x = np.array(
        [
            [0.05, 0.15, 0.25, 0.35, 0.45, 0.55],
            [0.25, 0.45, 0.65, 0.15, 0.75, 0.35],
            [0.85, 0.75, 0.55, 0.45, 0.25, 0.95],
        ]
    )
    training_y = np.array([0.2, -0.1, 0.7])
    evaluation_x = np.array(
        [[0.35, 0.25, 0.55, 0.65, 0.15, 0.45], [0.7, 0.6, 0.2, 0.8, 0.4, 0.3]]
    )
    length_scales = np.array([0.35, 0.5, 0.65, 0.4, 0.75, 0.55])
    signal_scale = 1.4
    alpha = 0.025

    def fixed_minimize(_objective, _initial, **_kwargs):
        return SimpleNamespace(
            x=np.log(np.r_[length_scales, signal_scale]),
            success=True,
            message="fixed test hyperparameters",
        )

    monkeypatch.setattr(surrogate_module, "minimize", fixed_minimize)
    model = Matern52ARDRegressor(alpha=alpha).fit(training_x, training_y)
    actual_mean, actual_std = model.predict(evaluation_x, return_std=True)

    training_covariance = _reference_matern52_covariance(
        training_x, training_x, length_scales, signal_scale
    ) + alpha * np.eye(training_x.shape[0])
    cross_covariance = _reference_matern52_covariance(
        evaluation_x, training_x, length_scales, signal_scale
    )
    dual = np.linalg.solve(training_covariance, training_y)
    expected_mean = cross_covariance @ dual
    solved_cross = np.linalg.solve(training_covariance, cross_covariance.T).T
    expected_variance = signal_scale**2 - np.sum(
        cross_covariance * solved_cross, axis=1
    )
    expected_std = np.sqrt(np.maximum(expected_variance, 0.0))

    np.testing.assert_allclose(actual_mean, expected_mean, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(actual_std, expected_std, rtol=1e-12, atol=1e-12)


def test_learning_curve_rejects_duplicate_development_geometry():
    partitions = initial_geometry_partitions(seed=440731)
    development = partitions["development"].copy()
    development[1] = development[0]

    with pytest.raises(ValueError, match="duplicate geometry"):
        surrogate_module.evaluate_learning_curve(
            partitions["training"],
            _synthetic_outputs(partitions["training"]),
            development,
            _synthetic_outputs(development),
            [4],
        )


def test_learning_curve_exposes_nonconverged_optimizer_receipt(monkeypatch):
    partitions = initial_geometry_partitions(seed=440731)
    training = partitions["training"]
    development = partitions["development"]

    def failed_minimize(_objective, initial, **_kwargs):
        return SimpleNamespace(
            x=np.asarray(initial),
            success=False,
            message="injected test non-convergence",
        )

    monkeypatch.setattr(surrogate_module, "minimize", failed_minimize)
    result = surrogate_module.evaluate_learning_curve(
        training,
        _synthetic_outputs(training),
        development,
        _synthetic_outputs(development),
        [4],
    )

    record = result[4]
    assert record["evaluation_partition"] == "development"
    receipt = record["fit_receipt"]
    assert receipt["all_outputs_converged"] is False
    assert receipt["posterior_finite"] is True
    assert receipt["fit_status"] == "diagnostic_only_optimizer_not_converged"
    assert set(receipt["outputs"]) == {"R_total", "T_total", "R00_total"}
    for output_receipt in receipt["outputs"].values():
        assert output_receipt["optimizer_success"] is False
        assert output_receipt["optimizer_message"] == "injected test non-convergence"
        assert len(output_receipt["length_scales"]) == 6
        assert output_receipt["signal_scale"] > 0.0
        assert output_receipt["alpha_nugget"] > 0.0
        assert output_receipt["posterior_finite"] is True
