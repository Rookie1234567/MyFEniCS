"""Deterministic CPU exact-GP and orthogonal polynomial model primitives."""

from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern
from sklearn.exceptions import ConvergenceWarning


def deterministic_optimization_initials(dimension: int, count: int = 8,
                                         seed: int = 0) -> list[np.ndarray]:
    """Return a fixed set of 8--16 ARD length-scale starts.

    The values are deliberately explicit rather than generated from an
    optimizer's hidden RNG.  ``seed`` only selects a deterministic rotation of
    the list, so repeated CV runs have byte-identical starts.
    """

    if count < 8 or count > 16:
        raise ValueError("Task003 requires 8--16 deterministic GP starts")
    def pad(values: list[float]) -> np.ndarray:
        return np.asarray((values + [values[-1]] * dimension)[:dimension], dtype=np.float64)

    def repeat(values: list[float]) -> np.ndarray:
        """Repeat a declared pattern to the requested ARD dimension."""
        return np.resize(np.asarray(values, dtype=np.float64), dimension)

    patterns = [
        np.full(dimension, 0.10), np.full(dimension, 0.25),
        np.full(dimension, 0.50), np.full(dimension, 1.00),
        np.full(dimension, 2.00),
        pad([0.25, 0.25, 0.50]),
        pad([2.00, 2.00, 0.50]),
        repeat([0.50, 2.00, 0.25, 2.00, 0.50]),
        repeat([2.00, 0.50, 2.00, 0.25, 0.50]),
        repeat([0.05, 0.50, 1.50, 3.00, 0.15]),
        repeat([3.00, 1.50, 0.50, 0.05, 2.00]),
        repeat([0.15, 3.00, 0.05, 1.50, 0.50]),
        repeat([1.50, 0.05, 3.00, 0.15, 0.50]),
        repeat([0.75, 0.75, 0.15, 3.00, 0.15]),
        repeat([3.00, 0.15, 0.75, 0.75, 0.15]),
        repeat([0.15, 0.75, 3.00, 0.15, 0.75]),
    ]
    rotation = int(seed) % len(patterns)
    ordered = patterns[rotation:] + patterns[:rotation]
    return [np.asarray(value, dtype=np.float64) for value in ordered[:count]]


def _boundary_collisions(model: GaussianProcessRegressor, *, tolerance: float = 1.0e-6
                         ) -> list[str]:
    theta = np.asarray(model.kernel_.theta, dtype=np.float64)
    bounds = np.asarray(model.kernel_.bounds, dtype=np.float64)
    names = ["constant"] + [f"length_scale_{i}" for i in range(len(theta) - 1)]
    collisions: list[str] = []
    for name, value, bound in zip(names, theta, bounds):
        if abs(value - bound[0]) <= tolerance:
            collisions.append(f"{name}:lower")
        if abs(value - bound[1]) <= tolerance:
            collisions.append(f"{name}:upper")
    return collisions


@dataclass
class ExactARDGP:
    """Matérn-5/2 ARD exact GP with auditable deterministic multi-start fits."""

    jitter: float = 1.0e-10
    optimizer_restarts: int = 8
    random_state: int = 0
    normalize_y: bool = True
    _model: GaussianProcessRegressor | None = None
    optimization_runs: list[dict[str, Any]] = field(default_factory=list)
    selected_start: int | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "ExactARDGP":
        values = np.asarray(x, dtype=np.float64)
        target = np.asarray(y, dtype=np.float64)
        initials = deterministic_optimization_initials(
            values.shape[1], count=int(self.optimizer_restarts), seed=self.random_state,
        )
        best: GaussianProcessRegressor | None = None
        best_lml = -np.inf
        self.optimization_runs = []
        for start_index, length_scale in enumerate(initials):
            kernel = ConstantKernel(
                1.0, constant_value_bounds=(1.0e-3, 1.0e3)
            ) * Matern(
                length_scale=length_scale,
                length_scale_bounds=(1.0e-2, 1.0e3), nu=2.5,
            )
            captured: list[warnings.WarningMessage] = []
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model = GaussianProcessRegressor(
                    kernel=kernel, alpha=float(self.jitter),
                    normalize_y=self.normalize_y, n_restarts_optimizer=0,
                    random_state=int(self.random_state),
                )
                model.fit(values, target)
                captured.extend(caught)
            warning_rows = [
                {"category": item.category.__name__, "message": str(item.message)}
                for item in captured
            ]
            # Do not silently discard optimizer warnings.  Persist them and
            # re-emit each warning so a caller sees the same diagnostic.
            for item in captured:
                warnings.warn(item.message, item.category, stacklevel=2)
            lml = float(model.log_marginal_likelihood_value_)
            collisions = _boundary_collisions(model)
            status = "warning" if warning_rows else "converged"
            self.optimization_runs.append({
                "start_index": start_index,
                "initial_length_scale": length_scale.tolist(),
                "fitted_kernel": str(model.kernel_),
                "log_marginal_likelihood": lml,
                "boundary_collisions": collisions,
                "warning_count": len(warning_rows),
                "warnings": warning_rows,
                "optimizer_status": status,
            })
            if best is None or lml > best_lml:
                best, best_lml = model, lml
                self.selected_start = start_index
        self._model = best
        return self

    def predict(self, x: np.ndarray, *, return_std: bool = False) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("exact GP is not fitted")
        return self._model.predict(np.asarray(x, dtype=np.float64), return_std=return_std)

    @property
    def kernel_(self) -> str:
        if self._model is None:
            raise RuntimeError("exact GP is not fitted")
        return str(self._model.kernel_)

    @property
    def log_marginal_likelihood_(self) -> float:
        if self._model is None:
            raise RuntimeError("exact GP is not fitted")
        return float(self._model.log_marginal_likelihood_value_)

    def metadata(self) -> dict[str, Any]:
        return {
            "family": "exact_gp",
            "kernel": "Matern-5/2-ARD",
            "jitter": self.jitter,
            "optimizer_initial_count": self.optimizer_restarts,
            "random_state": self.random_state,
            "normalize_y": self.normalize_y,
            "selected_start": self.selected_start,
            "fitted_kernel": self.kernel_ if self._model is not None else None,
            "log_marginal_likelihood": self.log_marginal_likelihood_
            if self._model is not None else None,
            "optimization_runs": self.optimization_runs,
        }


@dataclass
class TrendResidualGP:
    """Finite G2 candidate: degree-2 orthogonal trend plus exact-GP residual."""

    jitter: float = 1.0e-10
    optimizer_restarts: int = 8
    random_state: int = 0
    trend_kind: str = "legendre"
    trend_degree: int = 2
    _trend: OrthogonalPCE | None = None
    _residual: ExactARDGP | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TrendResidualGP":
        self._trend = OrthogonalPCE(degree=self.trend_degree,
                                    kind=self.trend_kind).fit(x, y)
        residual = np.asarray(y, dtype=np.float64) - self._trend.predict(x)
        self._residual = ExactARDGP(
            jitter=self.jitter, optimizer_restarts=self.optimizer_restarts,
            random_state=self.random_state,
        ).fit(x, residual)
        return self

    def predict(self, x: np.ndarray, *, return_std: bool = False) -> np.ndarray:
        if self._trend is None or self._residual is None:
            raise RuntimeError("trend-residual GP is not fitted")
        trend = self._trend.predict(x)
        if return_std:
            residual, std = self._residual.predict(x, return_std=True)
            return trend + residual, std
        return trend + self._residual.predict(x)

    def metadata(self) -> dict[str, Any]:
        if self._trend is None or self._residual is None:
            raise RuntimeError("trend-residual GP is not fitted")
        return {
            "family": "degree2_orthogonal_trend_plus_exact_gp_residual",
            "trend": self._trend.metadata(),
            "residual_gp": self._residual.metadata(),
            "jitter": self.jitter,
        }


def _multi_indices(dimension: int, degree: int) -> list[tuple[int, ...]]:
    return [powers for powers in itertools.product(range(degree + 1), repeat=dimension)
            if sum(powers) <= degree]


@dataclass
class OrthogonalPCE:
    """Total-degree Legendre/Chebyshev orthogonal polynomial basis."""

    degree: int
    kind: str = "legendre"
    ridge_alpha: float = 1.0e-12
    _indices: list[tuple[int, ...]] | None = None
    _coefficients: np.ndarray | None = None

    def _basis(self, x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=np.float64)
        if np.any(values < -1.000001) or np.any(values > 1.000001):
            raise ValueError("orthogonal PCE inputs must be scaled to [-1,1]")
        if self._indices is None:
            self._indices = _multi_indices(values.shape[1], self.degree)
        columns: list[np.ndarray] = []
        for powers in self._indices:
            term = np.ones(len(values), dtype=np.float64)
            for axis, order in enumerate(powers):
                if self.kind == "legendre":
                    coeff = np.zeros(order + 1); coeff[-1] = 1.0
                    term *= np.polynomial.legendre.legval(values[:, axis], coeff)
                elif self.kind == "chebyshev":
                    coeff = np.zeros(order + 1); coeff[-1] = 1.0
                    term *= np.polynomial.chebyshev.chebval(values[:, axis], coeff)
                else:
                    raise ValueError("orthogonal PCE kind must be legendre or chebyshev")
            columns.append(term)
        return np.column_stack(columns)

    def fit(self, x: np.ndarray, y: np.ndarray) -> "OrthogonalPCE":
        if self.degree not in (2, 3):
            raise ValueError("Task003 PCE degree must be 2 or 3")
        design = self._basis(x)
        lhs = design.T @ design + self.ridge_alpha * np.eye(design.shape[1])
        rhs = design.T @ np.asarray(y, dtype=np.float64)
        self._coefficients = np.linalg.solve(lhs, rhs)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self._coefficients is None:
            raise RuntimeError("orthogonal PCE is not fitted")
        return self._basis(x) @ self._coefficients

    def metadata(self) -> dict[str, Any]:
        return {"family": "orthogonal_pce", "degree": self.degree,
                "basis": self.kind, "ridge_alpha": self.ridge_alpha,
                "term_count": len(self._indices) if self._indices is not None else None}


# Backward-compatible import name; implementation is no longer monomial.
PolynomialPCE = OrthogonalPCE
