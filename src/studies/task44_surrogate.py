"""Small, auditable sampling and Gaussian-process helpers for Task44."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

PARAMETER_COUNT = 6
OUTPUT_NAMES = ("R_total", "T_total", "R00_total")
THICKNESS_LOWER_NM = 0.5
THICKNESS_UPPER_NM = 1.0
_SQRT5 = np.sqrt(5.0)


def _as_matrix(values: Sequence[Sequence[float]], columns: int, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != columns:
        raise ValueError(f"{name} must have shape (n, {columns})")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} must contain only finite values")
    return matrix


def normalize_thicknesses(thicknesses_nm: Sequence[Sequence[float]]) -> np.ndarray:
    """Map the frozen six thickness ranges [0.5, 1.0] nm to [0, 1]."""
    values = _as_matrix(thicknesses_nm, PARAMETER_COUNT, "thicknesses_nm")
    if np.any(values < THICKNESS_LOWER_NM) or np.any(values > THICKNESS_UPPER_NM):
        raise ValueError("thicknesses fall outside the frozen [0.5, 1.0] nm range")
    return (values - THICKNESS_LOWER_NM) / (
        THICKNESS_UPPER_NM - THICKNESS_LOWER_NM
    )


def denormalize_thicknesses(normalized: Sequence[Sequence[float]]) -> np.ndarray:
    """Map normalized six-parameter rows back to thicknesses in nm."""
    values = _as_matrix(normalized, PARAMETER_COUNT, "normalized")
    if np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("normalized thicknesses must be in [0, 1]")
    return THICKNESS_LOWER_NM + values * (
        THICKNESS_UPPER_NM - THICKNESS_LOWER_NM
    )


def geometry_key(thicknesses_nm: Sequence[float]) -> tuple[str, ...]:
    """Return an exact, stable key for a six-thickness geometry."""
    row = np.asarray(thicknesses_nm, dtype=np.float64)
    if row.shape != (PARAMETER_COUNT,) or not np.all(np.isfinite(row)):
        raise ValueError("a geometry must contain six finite thicknesses")
    if np.any(row < THICKNESS_LOWER_NM) or np.any(row > THICKNESS_UPPER_NM):
        raise ValueError("geometry falls outside the frozen thickness range")
    return tuple(float(value).hex() for value in row)


def validate_disjoint_geometry_groups(
    groups: Mapping[str, Sequence[Sequence[float]]],
) -> None:
    """Reject duplicate geometries within or across data partitions."""
    seen: dict[tuple[str, ...], str] = {}
    for group_name, geometries in groups.items():
        for row in geometries:
            key = geometry_key(row)
            previous = seen.get(key)
            if previous is not None:
                raise ValueError(
                    f"duplicate geometry appears in {previous!r} and {group_name!r}"
                )
            seen[key] = group_name


def latin_hypercube(samples: int, *, seed: int) -> np.ndarray:
    """Generate a deterministic, independently stratified six-dimensional design."""
    if samples < 1:
        raise ValueError("samples must be positive")
    rng = np.random.Generator(np.random.PCG64(seed))
    unit = np.empty((samples, PARAMETER_COUNT), dtype=np.float64)
    for column in range(PARAMETER_COUNT):
        unit[:, column] = (
            rng.permutation(samples) + rng.random(samples)
        ) / samples
    return denormalize_thicknesses(unit)


def initial_geometry_partitions(*, seed: int) -> dict[str, np.ndarray]:
    """Freeze 20 train candidates plus disjoint 10-point development/blind sets."""
    anchors = np.array(
        [
            [0.5] * PARAMETER_COUNT,
            [0.75] * PARAMETER_COUNT,
            [1.0] * PARAMETER_COUNT,
            [0.5, 1.0, 0.5, 1.0, 0.5, 1.0],
        ],
        dtype=np.float64,
    )
    groups = {
        "training": np.vstack((anchors, latin_hypercube(16, seed=seed + 1))),
        "development": latin_hypercube(10, seed=seed + 2),
        "blind_test": latin_hypercube(10, seed=seed + 3),
    }
    validate_disjoint_geometry_groups(groups)
    return groups


@dataclass(frozen=True)
class OutputStandardization:
    mean: np.ndarray
    scale: np.ndarray

    @classmethod
    def fit(cls, training_outputs: Sequence[Sequence[float]]) -> OutputStandardization:
        values = _as_matrix(training_outputs, len(OUTPUT_NAMES), "training_outputs")
        mean = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale == 0.0] = 1.0
        return cls(mean=mean, scale=scale)

    def transform(self, outputs: Sequence[Sequence[float]]) -> np.ndarray:
        values = _as_matrix(outputs, len(OUTPUT_NAMES), "outputs")
        return (values - self.mean) / self.scale

    def inverse_transform(self, outputs: Sequence[Sequence[float]]) -> np.ndarray:
        values = _as_matrix(outputs, len(OUTPUT_NAMES), "standardized outputs")
        return values * self.scale + self.mean


class Matern52ARDRegressor:
    """One-output GP with a Matérn-5/2 kernel and one length per input axis."""

    def __init__(self, *, alpha: float = 1e-8, max_iterations: int = 250) -> None:
        if alpha <= 0.0:
            raise ValueError("alpha must be positive")
        self.alpha = float(alpha)
        self.max_iterations = int(max_iterations)
        self.length_scales_: np.ndarray | None = None
        self.signal_scale_: float | None = None
        self.x_train_: np.ndarray | None = None
        self.y_train_: np.ndarray | None = None
        self.cholesky_: np.ndarray | None = None
        self.alpha_solution_: np.ndarray | None = None
        self.optimizer_success_: bool | None = None
        self.optimizer_message_: str | None = None

    @staticmethod
    def _kernel(
        left: np.ndarray,
        right: np.ndarray,
        length_scales: np.ndarray,
        signal_scale: float,
    ) -> np.ndarray:
        delta = (left[:, None, :] - right[None, :, :]) / length_scales
        radius = np.sqrt(np.sum(delta * delta, axis=2))
        scaled = _SQRT5 * radius
        return signal_scale**2 * (1.0 + scaled + scaled**2 / 3.0) * np.exp(
            -scaled
        )

    def fit(
        self, normalized_inputs: Sequence[Sequence[float]], outputs: Sequence[float]
    ) -> Matern52ARDRegressor:
        x = _as_matrix(normalized_inputs, PARAMETER_COUNT, "normalized_inputs")
        y = np.asarray(outputs, dtype=np.float64)
        if y.shape != (x.shape[0],) or not np.all(np.isfinite(y)):
            raise ValueError("outputs must be a finite vector matching the input rows")
        if x.shape[0] < 2:
            raise ValueError("at least two training rows are required")
        if np.any(x < 0.0) or np.any(x > 1.0):
            raise ValueError("normalized inputs must be in [0, 1]")

        identity = np.eye(x.shape[0], dtype=np.float64)

        def objective(parameters: np.ndarray) -> float:
            lengths = np.exp(parameters[:PARAMETER_COUNT])
            signal = float(np.exp(parameters[PARAMETER_COUNT]))
            covariance = self._kernel(x, x, lengths, signal)
            covariance.flat[:: x.shape[0] + 1] += self.alpha
            try:
                factor = np.linalg.cholesky(covariance)
            except np.linalg.LinAlgError:
                return 1e100
            solved = np.linalg.solve(factor.T, np.linalg.solve(factor, y))
            return float(
                0.5 * y @ solved
                + np.log(np.diag(factor)).sum()
                + 0.5 * y.size * np.log(2.0 * np.pi)
            )

        initial = np.r_[np.full(PARAMETER_COUNT, np.log(0.25)), 0.0]
        bounds = [
            (np.log(1e-3), np.log(10.0))
        ] * PARAMETER_COUNT + [(np.log(1e-3), np.log(100.0))]
        optimized = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": self.max_iterations, "ftol": 1e-10},
        )
        parameters = optimized.x if np.all(np.isfinite(optimized.x)) else initial
        self.length_scales_ = np.exp(parameters[:PARAMETER_COUNT])
        self.signal_scale_ = float(np.exp(parameters[PARAMETER_COUNT]))
        covariance = self._kernel(
            x, x, self.length_scales_, self.signal_scale_
        ) + self.alpha * identity
        self.cholesky_ = np.linalg.cholesky(covariance)
        self.alpha_solution_ = np.linalg.solve(
            self.cholesky_.T, np.linalg.solve(self.cholesky_, y)
        )
        self.x_train_ = x.copy()
        self.y_train_ = y.copy()
        self.optimizer_success_ = bool(optimized.success)
        self.optimizer_message_ = str(optimized.message)
        return self

    def predict(
        self, normalized_inputs: Sequence[Sequence[float]], *, return_std: bool = False
    ) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
        if (
            self.x_train_ is None
            or self.cholesky_ is None
            or self.alpha_solution_ is None
            or self.length_scales_ is None
            or self.signal_scale_ is None
        ):
            raise RuntimeError("fit must be called before predict")
        x = _as_matrix(normalized_inputs, PARAMETER_COUNT, "normalized_inputs")
        if np.any(x < 0.0) or np.any(x > 1.0):
            raise ValueError("normalized inputs must be in [0, 1]")
        cross = self._kernel(x, self.x_train_, self.length_scales_, self.signal_scale_)
        mean = cross @ self.alpha_solution_
        if not return_std:
            return mean
        projected = np.linalg.solve(self.cholesky_, cross.T)
        variance = self.signal_scale_**2 - np.sum(projected * projected, axis=0)
        return mean, np.sqrt(np.maximum(variance, 0.0))


class MultiOutputMatern52ARDGP:
    """Three independent ARD GPs with output scaling fitted on training rows only."""

    def __init__(self, *, alpha: float = 1e-8, max_iterations: int = 250) -> None:
        self.alpha = alpha
        self.max_iterations = max_iterations
        self.output_scaler_: OutputStandardization | None = None
        self.models_: list[Matern52ARDRegressor] = []

    def fit(
        self,
        thicknesses_nm: Sequence[Sequence[float]],
        outputs: Sequence[Sequence[float]],
    ) -> MultiOutputMatern52ARDGP:
        x = normalize_thicknesses(thicknesses_nm)
        y = _as_matrix(outputs, len(OUTPUT_NAMES), "outputs")
        if x.shape[0] != y.shape[0] or x.shape[0] < 2:
            raise ValueError("training inputs and outputs must have matching rows >= 2")
        self.output_scaler_ = OutputStandardization.fit(y)
        scaled = self.output_scaler_.transform(y)
        self.models_ = []
        for column in range(len(OUTPUT_NAMES)):
            model = Matern52ARDRegressor(
                alpha=self.alpha, max_iterations=self.max_iterations
            )
            model.fit(x, scaled[:, column])
            self.models_.append(model)
        return self

    def predict(
        self, thicknesses_nm: Sequence[Sequence[float]], *, return_std: bool = False
    ) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
        if self.output_scaler_ is None or len(self.models_) != len(OUTPUT_NAMES):
            raise RuntimeError("fit must be called before predict")
        x = normalize_thicknesses(thicknesses_nm)
        if return_std:
            predictions, deviations = zip(
                *(model.predict(x, return_std=True) for model in self.models_)
            )
            scaled_mean = np.column_stack(predictions)
            scaled_std = np.column_stack(deviations)
            mean = self.output_scaler_.inverse_transform(scaled_mean)
            return mean, scaled_std * self.output_scaler_.scale
        predictions = np.column_stack([model.predict(x) for model in self.models_])
        return self.output_scaler_.inverse_transform(predictions)

    def fit_receipt(self) -> dict[str, object]:
        """Expose per-output optimizer state and the parameters actually used."""
        if len(self.models_) != len(OUTPUT_NAMES):
            raise RuntimeError("fit must be called before fit_receipt")
        outputs: dict[str, dict[str, object]] = {}
        posterior_finite = True
        for name, model in zip(OUTPUT_NAMES, self.models_, strict=True):
            if (
                model.optimizer_success_ is None
                or model.optimizer_message_ is None
                or model.length_scales_ is None
                or model.signal_scale_ is None
                or model.cholesky_ is None
                or model.alpha_solution_ is None
            ):
                raise RuntimeError("fit did not produce a complete per-output receipt")
            finite = bool(
                np.all(np.isfinite(model.length_scales_))
                and np.isfinite(model.signal_scale_)
                and np.all(np.isfinite(model.cholesky_))
                and np.all(np.isfinite(model.alpha_solution_))
            )
            posterior_finite = posterior_finite and finite
            outputs[name] = {
                "optimizer_success": model.optimizer_success_,
                "optimizer_message": model.optimizer_message_,
                "length_scales": model.length_scales_.tolist(),
                "signal_scale": model.signal_scale_,
                "alpha_nugget": model.alpha,
                "posterior_finite": finite,
            }
        all_converged = all(
            model.optimizer_success_ is True for model in self.models_
        )
        if not posterior_finite:
            fit_status = "failed_nonfinite_posterior"
        elif all_converged:
            fit_status = "optimizer_converged"
        else:
            fit_status = "diagnostic_only_optimizer_not_converged"
        return {
            "all_outputs_converged": all_converged,
            "posterior_finite": posterior_finite,
            "fit_status": fit_status,
            "outputs": outputs,
        }


def baseline_predictions(
    training_inputs_nm: Sequence[Sequence[float]],
    training_outputs: Sequence[Sequence[float]],
    evaluation_inputs_nm: Sequence[Sequence[float]],
) -> dict[str, np.ndarray]:
    """Return training-mean and ordinary linear least-squares predictions."""
    x_train = normalize_thicknesses(training_inputs_nm)
    x_eval = normalize_thicknesses(evaluation_inputs_nm)
    y_train = _as_matrix(training_outputs, len(OUTPUT_NAMES), "training_outputs")
    if x_train.shape[0] != y_train.shape[0] or x_train.shape[0] < 2:
        raise ValueError("training inputs and outputs must have matching rows >= 2")
    mean = np.broadcast_to(y_train.mean(axis=0), (x_eval.shape[0], len(OUTPUT_NAMES)))
    design = np.column_stack((np.ones(x_train.shape[0]), x_train))
    evaluation = np.column_stack((np.ones(x_eval.shape[0]), x_eval))
    coefficients, *_ = np.linalg.lstsq(design, y_train, rcond=None)
    return {"mean": mean.copy(), "linear": evaluation @ coefficients}


def regression_metrics(
    actual: Sequence[Sequence[float]],
    predicted: Sequence[Sequence[float]],
) -> dict[str, dict[str, float]]:
    """Compute MAE, maximum absolute error, and observed range in output units."""
    truth = _as_matrix(actual, len(OUTPUT_NAMES), "actual")
    estimate = _as_matrix(predicted, len(OUTPUT_NAMES), "predicted")
    if truth.shape != estimate.shape or truth.shape[0] == 0:
        raise ValueError("actual and predicted must have identical nonempty shapes")
    error = np.abs(estimate - truth)
    return {
        name: {
            "mae": float(error[:, column].mean()),
            "max_abs": float(error[:, column].max()),
            "actual_range": float(np.ptp(truth[:, column])),
        }
        for column, name in enumerate(OUTPUT_NAMES)
    }


def evaluate_learning_curve(
    training_inputs_nm: Sequence[Sequence[float]],
    training_outputs: Sequence[Sequence[float]],
    development_inputs_nm: Sequence[Sequence[float]],
    development_outputs: Sequence[Sequence[float]],
    training_sizes: Sequence[int],
) -> dict[int, dict[str, object]]:
    """Evaluate nested training prefixes on the disjoint development set only.

    Blind-test evaluation is intentionally not part of this repeated learning-curve
    helper. A frozen model needs a separate, single blind evaluation.
    """
    x_train = _as_matrix(training_inputs_nm, PARAMETER_COUNT, "training_inputs_nm")
    y_train = _as_matrix(training_outputs, len(OUTPUT_NAMES), "training_outputs")
    x_development = _as_matrix(
        development_inputs_nm, PARAMETER_COUNT, "development_inputs_nm"
    )
    y_development = _as_matrix(
        development_outputs, len(OUTPUT_NAMES), "development_outputs"
    )
    if (
        x_train.shape[0] != y_train.shape[0]
        or x_development.shape[0] != y_development.shape[0]
    ):
        raise ValueError("input and output row counts must match")
    if x_development.shape[0] == 0:
        raise ValueError("development set must contain at least one row")
    validate_disjoint_geometry_groups(
        {"training": x_train, "development": x_development}
    )
    result: dict[int, dict[str, object]] = {}
    for size in training_sizes:
        if size < 2 or size > x_train.shape[0]:
            raise ValueError(f"invalid learning-curve training size: {size}")
        selected_x = x_train[:size]
        selected_y = y_train[:size]
        gp = MultiOutputMatern52ARDGP().fit(selected_x, selected_y)
        predictions = {"gp": gp.predict(x_development)}
        predictions.update(
            baseline_predictions(selected_x, selected_y, x_development)
        )
        result[int(size)] = {
            "evaluation_partition": "development",
            "metrics": {
                model_name: regression_metrics(y_development, prediction)
                for model_name, prediction in predictions.items()
            },
            "fit_receipt": gp.fit_receipt(),
        }
    return result
