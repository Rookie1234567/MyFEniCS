"""Deterministic CPU exact-GP and PCE model primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures


@dataclass
class ExactARDGP:
    """Matérn-5/2 ARD exact GP with explicit diagonal jitter."""

    jitter: float = 1.0e-10
    optimizer_restarts: int = 0
    random_state: int = 0
    normalize_y: bool = True
    _model: GaussianProcessRegressor | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "ExactARDGP":
        kernel = ConstantKernel(
            1.0, constant_value_bounds=(1.0e-3, 1.0e3)
        ) * Matern(
            length_scale=np.ones(x.shape[1], dtype=np.float64),
            length_scale_bounds=(1.0e-2, 1.0e3), nu=2.5,
        )
        self._model = GaussianProcessRegressor(
            kernel=kernel,
            alpha=float(self.jitter),
            normalize_y=self.normalize_y,
            n_restarts_optimizer=int(self.optimizer_restarts),
            random_state=int(self.random_state),
        )
        self._model.fit(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
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

    def metadata(self) -> dict[str, Any]:
        return {
            "family": "exact_gp",
            "kernel": "Matern-5/2-ARD",
            "jitter": self.jitter,
            "optimizer_restarts": self.optimizer_restarts,
            "random_state": self.random_state,
            "normalize_y": self.normalize_y,
            "fitted_kernel": self.kernel_ if self._model is not None else None,
        }


@dataclass
class PolynomialPCE:
    """Deterministic degree-2/3 polynomial-chaos surrogate on CPU."""

    degree: int
    ridge_alpha: float = 1.0e-12
    _features: PolynomialFeatures | None = None
    _model: Ridge | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "PolynomialPCE":
        if self.degree not in (2, 3):
            raise ValueError("Task003 PCE degree must be 2 or 3")
        self._features = PolynomialFeatures(self.degree, include_bias=True)
        design = self._features.fit_transform(np.asarray(x, dtype=np.float64))
        self._model = Ridge(alpha=self.ridge_alpha, fit_intercept=False,
                            solver="svd")
        self._model.fit(design, np.asarray(y, dtype=np.float64))
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self._features is None or self._model is None:
            raise RuntimeError("PCE is not fitted")
        return self._model.predict(self._features.transform(np.asarray(x, dtype=np.float64)))

    def metadata(self) -> dict[str, Any]:
        return {
            "family": "pce",
            "degree": self.degree,
            "ridge_alpha": self.ridge_alpha,
            "term_count": int(self._features.n_output_features_)
            if self._features is not None else None,
        }

