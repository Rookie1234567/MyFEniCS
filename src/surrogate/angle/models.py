"""Finite Task004 angle-model candidates and physical power reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.interpolate import RBFInterpolator

from ..models import ExactARDGP
from ..physics import reconstruct_aggregates


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


def region_labels(angles: np.ndarray) -> list[str]:
    values = np.asarray(angles, dtype=np.float64)
    distance = cutoff_distance(values)
    labels = []
    for row, cut in zip(values, distance):
        if row[0] <= 2.0:
            labels.append("low_grazing")
        elif row[1] >= 75.0:
            labels.append("high_azimuth")
        elif cut <= 0.02:
            labels.append("cutoff_near")
        else:
            labels.append("ordinary_interior")
    return labels


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
        aggregate = reconstruct_aggregates(latent)
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
                mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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
        return output, np.zeros_like(output)
