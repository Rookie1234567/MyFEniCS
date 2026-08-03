"""Finite Task004 angle-model candidates and physical power reconstruction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.interpolate import RBFInterpolator

from ..models import ExactARDGP
from ..physics import analytic_power_mask, reconstruct_aggregates


def angle_features(angles: np.ndarray, candidate: str = "F1") -> np.ndarray:
    values = np.asarray(angles, dtype=np.float64)
    if values.ndim == 1:
        values = values[None, :]
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("angle inputs must have shape (n,2)")
    if np.any(values[:, 0] < 0.5) or np.any(values[:, 0] > 10.0) \
            or np.any(values[:, 1] < 0.0) or np.any(values[:, 1] > 90.0):
        raise ValueError("angle is outside the Task004 domain")
    grazing = np.deg2rad(values[:, 0]); azimuth = np.deg2rad(values[:, 1])
    f1 = np.column_stack((2.0 * (values[:, 0] - 5.25) / 9.5,
                          2.0 * values[:, 1] / 90.0 - 1.0))
    key = str(candidate).upper()
    if key == "F1":
        return f1
    kx = np.cos(grazing) * np.cos(azimuth)
    ky = np.cos(grazing) * np.sin(azimuth)
    if key == "F2":
        return np.column_stack((kx, ky))
    if key == "F3":
        margins = np.stack([1.0 - ((kx + m * 13.5 / 50.0) ** 2 + ky ** 2)
                            for m in range(-7, 4)], axis=1)
        # Keep signed distances, not only an absolute cutoff score, so the GP
        # can distinguish the two sides of a Rayleigh crossing.
        return np.column_stack((f1, margins))
    raise ValueError(f"unknown Task004 feature candidate: {candidate}")


def cutoff_distance(angles: np.ndarray) -> np.ndarray:
    values = np.asarray(angles, dtype=np.float64)
    return np.min(np.abs(angle_features(values, "F3")[:, 2:]), axis=1)


def cutoff_identity(angles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the nearest fixed-order cutoff index and its signed margin."""
    values = np.asarray(angles, dtype=np.float64)
    margins = angle_features(values, "F3")[:, 2:]
    nearest = np.argmin(np.abs(margins), axis=1)
    return nearest.astype(np.int64) - 7, margins[np.arange(len(values)), nearest]


def region_labels(angles: np.ndarray) -> list[str]:
    masks = region_masks(angles)
    labels = []
    for index in range(len(np.asarray(angles))):
        current = [name for name, mask in masks.items() if bool(mask[index])]
        labels.append("+".join(current))
    return labels


def region_masks(angles: np.ndarray) -> dict[str, np.ndarray]:
    """Return independent region masks; difficult regions are allowed to overlap."""

    values = np.asarray(angles, dtype=np.float64)
    if values.ndim == 1:
        values = values[None, :]
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("angle inputs must have shape (n,2)")
    low = values[:, 0] <= 2.0
    high = values[:, 1] >= 75.0
    cutoff = cutoff_distance(values) <= 0.02
    # ``ordinary_interior`` is intentionally an overlapping region.  It is a
    # broad interior band, not the complement of every difficult region;
    # cutoff points can therefore be reported in both windows.
    ordinary = (values[:, 0] > 2.0) & (values[:, 1] < 75.0)
    return {
        "low_grazing": low,
        "high_azimuth": high,
        "cutoff_near": cutoff,
        "ordinary_interior": ordinary,
    }


def analytic_power_carrying_mask(angles: np.ndarray) -> np.ndarray:
    """Evaluate the independent runtime propagation/Poynting mask authority."""

    values = np.asarray(angles, dtype=np.float64)
    if values.ndim == 1:
        values = values[None, :]
    points = np.column_stack((
        np.full(len(values), 120.0), np.full(len(values), 17.0), values,
    ))
    return np.asarray(analytic_power_mask(points), dtype=bool)


def _metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    error = np.asarray(prediction, dtype=np.float64) - np.asarray(truth, dtype=np.float64)
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


@dataclass
class LocalRBFModel:
    """Local RBF baseline without probabilistic claims."""

    smoothing: float = 1.0e-8
    neighbors: int = 32
    models: list[Any] | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LocalRBFModel":
        self.models = [RBFInterpolator(x, y[:, index], smoothing=self.smoothing,
                                        neighbors=min(self.neighbors, len(x)), kernel="thin_plate_spline")
                       for index in range(y.shape[1])]
        return self

    def predict(self, x: np.ndarray, *, return_std: bool = False):
        if self.models is None:
            raise RuntimeError("local RBF is not fitted")
        mean = np.column_stack([model(x) for model in self.models])
        if return_std:
            return mean, np.full_like(mean, np.nan)
        return mean

    def metadata(self) -> dict[str, Any]:
        return {"family": "local_rbf", "smoothing": self.smoothing,
                "neighbors": self.neighbors, "uncertainty": "not_available"}


@dataclass
class ChebyshevTrend:
    degree: int
    ridge: float = 1.0e-10
    coefficients: np.ndarray | None = None
    powers: list[tuple[int, int]] | None = None

    def _basis(self, x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=np.float64)
        if self.powers is None:
            self.powers = [(i, j) for i in range(self.degree + 1)
                           for j in range(self.degree + 1) if i + j <= self.degree]
        columns = []
        for i, j in self.powers:
            ci = np.zeros(i + 1); ci[-1] = 1.0
            cj = np.zeros(j + 1); cj[-1] = 1.0
            columns.append(np.polynomial.chebyshev.chebval(values[:, 0], ci)
                           * np.polynomial.chebyshev.chebval(values[:, 1], cj))
        return np.column_stack(columns)

    def fit(self, x: np.ndarray, y: np.ndarray) -> "ChebyshevTrend":
        basis = self._basis(x)
        self.coefficients = np.linalg.solve(
            basis.T @ basis + self.ridge * np.eye(basis.shape[1]), basis.T @ y,
        )
        return self

    def predict(self, x: np.ndarray, *, return_std: bool = False):
        if self.coefficients is None:
            raise RuntimeError("Chebyshev trend is not fitted")
        mean = self._basis(x) @ self.coefficients
        if return_std:
            return mean, np.full_like(mean, np.nan)
        return mean

    def metadata(self) -> dict[str, Any]:
        return {"family": "tensor_total_degree_chebyshev", "degree": self.degree,
                "ridge": self.ridge, "term_count": len(self.powers or [])}


@dataclass
class AggregateModel:
    candidate: str
    jitter: float = 1.0e-10
    gp_starts: int = 8
    models: list[Any] | None = None

    def fit(self, angles: np.ndarray, aggregates: np.ndarray) -> "AggregateModel":
        x = angle_features(angles, self.candidate.split(":")[-1])
        latent = np.column_stack((np.log((aggregates[:, 0] + 1.0e-8) /
                                             (aggregates[:, 2] + 1.0e-8)),
                                  np.log((aggregates[:, 1] + 1.0e-8) /
                                             (aggregates[:, 2] + 1.0e-8))))
        if self.candidate.startswith("gp"):
            self.models = [ExactARDGP(jitter=self.jitter, optimizer_restarts=self.gp_starts,
                                      random_state=101 + index).fit(x, latent[:, index])
                           for index in range(2)]
        elif self.candidate.startswith("cheb"):
            degree = int(self.candidate[4:].split(":", 1)[0])
            self.models = [ChebyshevTrend(degree=degree).fit(x, latent[:, index])
                           for index in range(2)]
        elif self.candidate.startswith("rbf"):
            self.models = [LocalRBFModel().fit(x, latent[:, index:index + 1])
                           for index in range(2)]
        else:
            raise ValueError(f"unsupported aggregate candidate {self.candidate}")
        return self

    def predict(self, angles: np.ndarray, *, return_std: bool = False):
        if self.models is None:
            raise RuntimeError("aggregate model is not fitted")
        x = angle_features(angles, self.candidate.split(":")[-1])
        means = []; stds = []
        for model in self.models:
            mean, std = model.predict(x, return_std=True)
            means.append(np.asarray(mean).reshape(-1)); stds.append(np.asarray(std).reshape(-1))
        latent = np.column_stack(means)
        latent_std = np.column_stack(stds)
        # Task003 retains A_volume as a fourth diagnostic column.  Task004's
        # angle aggregate contract is the physical composition only: R, T,
        # and A_balance reconstructed from the same softmax weights.
        aggregate = reconstruct_aggregates(latent)[:, :3]
        # Delta-method uncertainty through softmax(zR,zT,0).
        if np.all(np.isfinite(latent_std)):
            p = aggregate
            jr = p * (np.eye(3)[0][None, :] - p[:, 0, None])
            jt = p * (np.eye(3)[1][None, :] - p[:, 1, None])
            std = np.sqrt((jr * latent_std[:, 0, None]) ** 2
                          + (jt * latent_std[:, 1, None]) ** 2)
        else:
            std = np.full_like(aggregate, np.nan)
        return (aggregate, std) if return_std else aggregate

    def metadata(self) -> dict[str, Any]:
        return {"candidate": self.candidate, "jitter": self.jitter,
                "gp_optimizer_initial_count": self.gp_starts,
                "models": [model.metadata() for model in (self.models or [])]}


@dataclass
class FractionPowerModel:
    """Side-total plus masked fraction model; side ledgers close exactly."""

    training_angles: np.ndarray
    training_powers: np.ndarray
    training_mask: np.ndarray

    def predict(self, angles: np.ndarray, aggregates: np.ndarray,
                mask: np.ndarray, *, aggregate_std: np.ndarray | None = None
                ) -> tuple[np.ndarray, np.ndarray]:
        del aggregate_std
        values = np.asarray(angles, dtype=np.float64)
        distances = np.linalg.norm(
            (values[:, None, :] - self.training_angles[None, :, :]) /
            np.asarray([9.5, 90.0]), axis=2,
        )
        nearest = np.argmin(distances, axis=1)
        output = np.full((len(values), 22, 2), np.nan, dtype=np.float64)
        for row, source in enumerate(nearest):
            source_power = np.where(self.training_mask[source], self.training_powers[source], 0.0)
            for side, sl, total_index in ((0, slice(0, 11), 0), (1, slice(11, 22), 1)):
                active = np.asarray(mask[row, sl, :], dtype=bool)
                fractions = np.where(self.training_mask[source, sl, :], source_power[sl, :], 0.0)
                denom = float(np.sum(fractions))
                if denom > 0.0:
                    fractions /= denom
                fractions *= max(float(aggregates[row, total_index]), 0.0)
                output[row, sl, :][active] = fractions[active]
                # A final sidewise normalization removes floating-point drift.
                current = np.nansum(output[row, sl, :])
                if current > 0.0:
                    output[row, sl, :][active] *= float(aggregates[row, total_index]) / current
        # This nearest-neighbour object is retained only as a diagnostic
        # baseline.  It has no calibrated uncertainty, so zero is forbidden.
        return output, np.full_like(output, np.nan)


@dataclass
class _LatentFractionRegressor:
    """Small deterministic local-RBF regressor with a constant fallback."""

    model: Any | None = None
    constant: float = 0.0
    residual_scale: float = 1.0
    prediction_fallbacks: int = 0

    def fit(self, x: np.ndarray, y: np.ndarray) -> "_LatentFractionRegressor":
        values = np.asarray(y, dtype=np.float64).reshape(-1)
        self.constant = float(np.mean(values)) if values.size else 0.0
        self.residual_scale = float(np.std(values - self.constant)) if values.size else 1.0
        self.residual_scale = max(self.residual_scale, 1.0e-6)
        if len(values) >= 3:
            try:
                self.model = RBFInterpolator(
                    np.asarray(x, dtype=np.float64), values,
                    smoothing=1.0e-8, neighbors=min(32, len(values)),
                    kernel="thin_plate_spline",
                )
            except (ValueError, np.linalg.LinAlgError):
                self.model = None
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values = np.full(len(np.asarray(x)), self.constant, dtype=np.float64)
        if self.model is not None:
            try:
                values = np.asarray(self.model(x), dtype=np.float64).reshape(-1)
            except (ValueError, np.linalg.LinAlgError):
                # Collinear local support can make SciPy's thin-plate
                # polynomial system singular at a query.  The deterministic
                # constant fit is a declared fallback, not a nearest-point
                # substitution; retain the event in model provenance.
                self.prediction_fallbacks += 1
        return values, np.full_like(values, self.residual_scale)


@dataclass
class MaskedFractionPowerModel:
    """Physics-constrained side-total plus active-channel composition model.

    Each observed mask topology is a separate simplex.  Active-channel
    fractions are represented by additive log-ratios to the last active
    channel and reconstructed by a softmax, so side ledgers close exactly.
    """

    feature: str = "F1"
    floor: float = 1.0e-12
    training_angles: np.ndarray | None = None
    training_powers: np.ndarray | None = None
    training_mask: np.ndarray | None = None
    groups: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = field(default_factory=dict)
    unsupported_topologies: list[dict[str, Any]] = field(default_factory=list)

    def fit(self, angles: np.ndarray, powers: np.ndarray, mask: np.ndarray) -> "MaskedFractionPowerModel":
        values = np.asarray(angles, dtype=np.float64)
        powers = np.asarray(powers, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        if powers.shape != mask.shape or powers.ndim != 3 or powers.shape[1:] != (22, 2):
            raise ValueError("Task004 power/mask arrays must have shape (n,22,2)")
        self.training_angles = values.copy()
        self.training_powers = powers.copy()
        self.training_mask = mask.copy()
        self.unsupported_topologies = []
        features = angle_features(values, self.feature)
        self.groups = {}
        for side, sl in ((0, slice(0, 11)), (1, slice(11, 22))):
            side_mask = mask[:, sl, :].reshape(len(values), -1)
            for signature in sorted({tuple(np.flatnonzero(row)) for row in side_mask}):
                rows = np.asarray([tuple(np.flatnonzero(row)) == signature for row in side_mask])
                active = np.asarray(signature, dtype=int)
                if not len(active) or not np.any(rows):
                    continue
                reference = int(active[-1])
                regressors: dict[int, _LatentFractionRegressor] = {}
                for channel in active[:-1]:
                    numerator = np.maximum(powers[rows, sl, :].reshape(np.sum(rows), -1)[:, channel], self.floor)
                    denominator = np.maximum(powers[rows, sl, :].reshape(np.sum(rows), -1)[:, reference], self.floor)
                    regressors[int(channel)] = _LatentFractionRegressor().fit(
                        features[rows], np.log(numerator / denominator),
                    )
                self.groups[(side, signature)] = {
                    "rows": rows, "active": active.tolist(),
                    "reference": reference, "regressors": regressors,
                    "fallback_fractions": self._mean_fractions(
                        powers[rows, sl, :].reshape(np.sum(rows), -1), active,
                    ),
                }
        return self

    @staticmethod
    def _mean_fractions(values: np.ndarray, active: np.ndarray) -> np.ndarray:
        if len(active) == 0:
            return np.asarray([], dtype=np.float64)
        mean = np.nanmean(values[:, active], axis=0)
        mean = np.where(np.isfinite(mean), np.maximum(mean, 0.0), 0.0)
        total = float(np.sum(mean))
        return mean / total if total > 0.0 else np.full(len(active), 1.0 / len(active))

    def predict(
        self, angles: np.ndarray, aggregates: np.ndarray, mask: np.ndarray,
        *, aggregate_std: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.training_angles is None or self.training_powers is None or self.training_mask is None:
            raise RuntimeError("masked fraction model is not fitted")
        values = np.asarray(angles, dtype=np.float64)
        aggregates = np.asarray(aggregates, dtype=np.float64)
        query_mask = np.asarray(mask, dtype=bool)
        output = np.full((len(values), 22, 2), np.nan, dtype=np.float64)
        uncertainty = np.full_like(output, np.nan)
        self.unsupported_topologies = []
        features = angle_features(values, self.feature)
        for row in range(len(values)):
            for side, sl in ((0, slice(0, 11)), (1, slice(11, 22))):
                active = np.flatnonzero(query_mask[row, sl, :].reshape(-1))
                signature = tuple(int(value) for value in active)
                group = self.groups.get((side, signature))
                if group is None:
                    # A topology unseen during training is not qualified.  Do
                    # not silently borrow a nearest-neighbour fraction: the
                    # caller must surface this as unsupported_mask_topology.
                    self.unsupported_topologies.append({
                        "row": int(row), "side": int(side),
                        "signature": [int(value) for value in active],
                    })
                    continue
                else:
                    latent = np.zeros(max(len(active) - 1, 0), dtype=np.float64)
                    latent_std = np.zeros(max(len(active) - 1, 0), dtype=np.float64)
                    for index, channel in enumerate(active[:-1]):
                        latent[index], latent_std[index] = group["regressors"][int(channel)].predict(
                            features[row:row + 1]
                        )
                    logits = np.concatenate((latent, np.asarray([0.0])))
                    logits -= np.max(logits)
                    weights = np.exp(logits)
                    fractions = weights / np.sum(weights)
                    latent_scale = float(np.max(latent_std)) if latent_std.size else 0.0
                    fraction_std = np.maximum(np.abs(fractions) * latent_scale, 1.0e-8)
                total = max(float(aggregates[row, side]), 0.0)
                total_std = 0.0
                if aggregate_std is not None and np.asarray(aggregate_std).ndim == 2:
                    candidate_std = float(aggregate_std[row, side])
                    total_std = candidate_std if np.isfinite(candidate_std) else 0.0
                flat_output = output[row, sl, :].reshape(-1)
                flat_uncertainty = uncertainty[row, sl, :].reshape(-1)
                flat_output[active] = total * fractions
                flat_uncertainty[active] = np.maximum(
                    np.sqrt((total * fraction_std) ** 2 + (total_std * fractions) ** 2),
                    1.0e-12,
                )
                output[row, sl, :] = flat_output.reshape(11, 2)
                uncertainty[row, sl, :] = flat_uncertainty.reshape(11, 2)
        return output, uncertainty

    def metadata(self) -> dict[str, Any]:
        return {
            "family": "masked_active_fraction_local_rbf",
            "feature": self.feature, "floor": self.floor,
            "topology_group_count": len(self.groups),
            "uncertainty": "heuristic_training_residual_scale",
            "uncertainty_calibration": "not_calibrated_physical_uncertainty",
            "unsupported_topology_policy": "fail_closed",
            "prediction_fallback_policy": "constant_on_collinear_support",
            "prediction_fallback_count": int(sum(
                reg.prediction_fallbacks for group in self.groups.values()
                for reg in group["regressors"].values()
            )),
        }
