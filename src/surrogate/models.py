"""Independent-output Matérn-5/2 ARD GPs and small-sample baselines.

Optional scientific dependencies are imported only in numerical operations.
The saved model is JSON data, never pickle or executable deserialization.
"""
from __future__ import annotations

import warnings

from .design import OUTPUTS

DEFAULT_STRATEGY = {
    "name": "matern52-ard-independent-v1", "seed": 440701,
    "alpha_standardized": 1e-8, "constant_bounds": [1e-3, 1e3],
    "length_scale_initial": 0.5, "length_scale_bounds": [0.02, 20.0],
    "optimizer_restarts": 0, "linear_ridge": 1e-8,
    "input_normalization": "(thickness_nm-0.5)/0.5",
    "output_scaling": "training-only mean and population std; constant scale1",
    "uncertainty": "model posterior standard deviation; NOT a true-error bound",
}


def _arrays(x, y=None):
    import numpy as np
    a = np.asarray(x, dtype=float)
    if a.ndim != 2 or a.shape[1] != 6 or not np.isfinite(a).all():
        raise ValueError("finite six-dimensional X required")
    if np.any(a < 0.5) or np.any(a > 1):
        raise ValueError("outside frozen thickness range")
    if y is None:
        return (a - 0.5) / 0.5
    b = np.asarray(y, dtype=float)
    if b.shape != (len(a), 3) or not np.isfinite(b).all():
        raise ValueError("finite three-output Y required")
    return (a - 0.5) / 0.5, b


def fit_model(x, y, strategy=None):
    import numpy as np
    import scipy
    import sklearn
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern

    strategy = dict(DEFAULT_STRATEGY if strategy is None else strategy)
    if set(strategy) != set(DEFAULT_STRATEGY) or strategy["name"] != DEFAULT_STRATEGY["name"]:
        raise ValueError("unknown or incomplete model strategy")
    for key in ("alpha_standardized", "linear_ridge"):
        if not np.isfinite(strategy[key]) or strategy[key] <= 0:
            raise ValueError("positive numerical regularization required")
    if not 0 <= strategy["optimizer_restarts"] <= 2:
        raise ValueError("bounded declared optimizer work required")
    xn, yn = _arrays(x, y)
    if len(xn) < 3:
        raise ValueError("too few samples even for diagnostic fitting")
    mean, std = yn.mean(axis=0), yn.std(axis=0)
    constant = std <= 1e-12
    scale = np.where(constant, 1.0, std)
    scaled = (yn - mean) / scale
    parameters, captured = [], []
    for j in range(3):
        kernel = ConstantKernel(1.0, tuple(strategy["constant_bounds"])) * Matern(
            length_scale=np.full(6, strategy["length_scale_initial"]),
            length_scale_bounds=tuple(strategy["length_scale_bounds"]), nu=2.5)
        gp = GaussianProcessRegressor(kernel=kernel, alpha=strategy["alpha_standardized"],
                                      normalize_y=False, random_state=strategy["seed"] + j,
                                      n_restarts_optimizer=strategy["optimizer_restarts"])
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            gp.fit(xn, scaled[:, j])
        captured.extend(f"{OUTPUTS[j]}: {w.message}" for w in seen)
        parameters.append({"constant": float(gp.kernel_.k1.constant_value),
                           "length_scale": gp.kernel_.k2.length_scale.tolist(),
                           "log_marginal_likelihood": float(gp.log_marginal_likelihood_value_)})
    # Ridge only on six slopes; intercept is not penalized. Safe even in small CV folds.
    augmented = np.column_stack([np.ones(len(xn)), xn])
    penalty = np.diag([0.0] + [strategy["linear_ridge"]] * 6)
    linear = np.linalg.solve(augmented.T @ augmented + penalty, augmented.T @ yn)
    return {"schema": "sixlayer-gp-model-v1", "strategy": strategy,
            "packages": {"numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__},
            "x_train_nm": np.asarray(x).tolist(), "y_train_raw": yn.tolist(),
            "scaler": {"mean": mean.tolist(), "scale": scale.tolist(), "constant_output": constant.tolist()},
            "gp_parameters": parameters, "linear_coefficients": linear.tolist(),
            "linear_rank": int(np.linalg.matrix_rank(augmented)),
            "linear_condition": float(np.linalg.cond(augmented)), "warnings": captured}


def predict_model(model, x):
    import numpy as np
    import scipy
    import sklearn
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern

    actual_packages = {"numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__}
    if model["packages"] != actual_packages:
        raise ValueError("statistical runtime packages changed; qualify/refit explicitly before prediction")
    xn = _arrays(x)
    train, y = _arrays(model["x_train_nm"], model["y_train_raw"])
    mean = np.asarray(model["scaler"]["mean"])
    scale = np.asarray(model["scaler"]["scale"])
    predicted, uncertainty = [], []
    for j, params in enumerate(model["gp_parameters"]):
        kernel = ConstantKernel(params["constant"], "fixed") * Matern(
            length_scale=params["length_scale"], length_scale_bounds="fixed", nu=2.5)
        gp = GaussianProcessRegressor(kernel=kernel, optimizer=None, normalize_y=False,
                                      alpha=model["strategy"]["alpha_standardized"])
        gp.fit(train, (y[:, j] - mean[j]) / scale[j])
        prediction, sigma = gp.predict(xn, return_std=True)
        predicted.append(prediction * scale[j] + mean[j])
        uncertainty.append(sigma * scale[j])
    result = {"gp": np.column_stack(predicted), "gp_std": np.column_stack(uncertainty),
              "mean": np.tile(mean, (len(xn), 1)),
              "linear": np.column_stack([np.ones(len(xn)), xn]) @ np.asarray(model["linear_coefficients"])}
    if not all(np.isfinite(a).all() for a in result.values()):
        raise ValueError("nonfinite prediction")
    # Deliberately do not clip powers: clipping would hide model error.
    return {name: value.tolist() for name, value in result.items()}


def errors(y, prediction):
    import numpy as np
    truth, pred = np.asarray(y), np.asarray(prediction)
    if truth.shape != pred.shape or truth.ndim != 2 or truth.shape[1] != 3:
        raise ValueError("prediction shape mismatch")
    error = np.abs(truth - pred)
    if not np.isfinite(error).all():
        raise ValueError("nonfinite errors")
    return {name: {"mae": float(error[:, j].mean()), "max_absolute_error": float(error[:, j].max()),
                   "worst_index": int(error[:, j].argmax())} for j, name in enumerate(OUTPUTS)}


def cross_validate(x, y, strategy=None):
    """LOOCV <=12, otherwise deterministic five-fold. Refit EVERY fold scaler/GP."""
    import numpy as np
    x, y = np.asarray(x), np.asarray(y)
    count = len(x)
    if count < 4:
        raise ValueError("CV needs at least four data points")
    folds = [list(range(i, count, min(count, 5))) for i in range(min(count, 5))]
    if count <= 12:
        folds = [[i] for i in range(count)]
    predictions = {name: np.empty_like(y, dtype=float) for name in ("gp", "mean", "linear")}
    receipts = []
    for held in folds:
        train = [i for i in range(count) if i not in held]
        model = fit_model(x[train], y[train], strategy)
        current = predict_model(model, x[held])
        for name in predictions:
            predictions[name][held] = current[name]
        receipts.append({"train_indices": train, "held_indices": held, "scaler": model["scaler"],
                         "linear_rank": model["linear_rank"], "warnings": model["warnings"]})
    return {"kind": "leave-one-out" if count <= 12 else "deterministic-five-fold",
            "metrics": {name: errors(y, value) for name, value in predictions.items()},
            "folds": receipts, "hyperparameter_selection": "train-fold likelihood only; no held labels in fit"}


def evaluation_report(model, records, y, predictions, qualification):
    import numpy as np
    metrics = {name: errors(y, predictions[name]) for name in ("gp", "mean", "linear")}
    output = {}
    train = np.asarray(model["y_train_raw"])
    truth = np.asarray(y)
    for j, name in enumerate(OUTPUTS):
        m = metrics["gp"][name]
        index = m["worst_index"]
        variation = float(np.ptp(train[:, j]))
        observed = qualification["checked_point_refinement_difference"][name]
        repeat = qualification["repeat_noise_indicator"]
        repeat_difference = None if repeat is None else repeat["max_absolute_difference"][name]
        near_repeat = False if repeat_difference is None else variation <= 2 * repeat_difference
        baseline_meets = metrics["mean"][name]["max_absolute_error"] <= 1e-3
        output[name] = {
            "train_min": float(train[:, j].min()), "train_max": float(train[:, j].max()),
            "train_range": variation, "evaluation_range": float(np.ptp(truth[:, j])),
            "metrics": {key: metrics[key][name] for key in metrics},
            "baseline_improvement": {key: {
                measure: (None if metrics[key][name][measure] == 0 else
                          1 - metrics["gp"][name][measure] / metrics[key][name][measure])
                for measure in ("mae", "max_absolute_error")} for key in ("mean", "linear")},
            "mae_target_met": m["mae"] <= 1e-3,
            "max_error_target_met": m["max_absolute_error"] <= 1e-3,
            "checked_point_refinement_difference": observed,
            "repeat_noise_indicator": repeat,
            "repeat_noise_status": "NOT_MEASURED" if repeat is None else "MEASURED_AT_REPEATED_POINTS_ONLY",
            "repeat_max_absolute_difference": repeat_difference,
            "response_near_measured_repeat_difference": near_repeat,
            "response_near_checked_refinement_difference": variation <= 2 * observed,
            "mean_baseline_already_meets_target": baseline_meets,
            "generalization_evidence_insufficient": (baseline_meets or variation <= 2 * observed
                                                       or near_repeat or model["linear_rank"] < 7),
            "worst_point": {"sample_id": records[index]["sample_id"],
                            "thickness_nm": records[index]["thickness_nm"],
                            "absolute_error": m["max_absolute_error"],
                            "gp_std_not_error_bound": predictions["gp_std"][index][j],
                            "cause": "not established by surrogate errors alone"},
        }
    return {"outputs": output, "units": "raw dimensionless power ratios",
            "affine_geometry_rank": model["linear_rank"], "affine_geometry_condition": model["linear_condition"],
            "scope": "evaluated points only, not a continuous-domain or standard-size guarantee",
            "uncertainty": DEFAULT_STRATEGY["uncertainty"],
            "all_max_error_targets_met": all(row["max_error_target_met"] for row in output.values())}
