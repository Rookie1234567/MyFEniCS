from __future__ import annotations

import gc
import time
from typing import Any

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .local_slab_solver import LocalCsrOperator


class SparseLuTeacherLocalSolver:
    """One-factor/many-RHS high-accuracy local sparse-LU teacher."""

    def __init__(
        self,
        operator: LocalCsrOperator,
        *,
        ordering: str = "COLAMD",
        diagonal_pivot_threshold: float = 1.0,
    ) -> None:
        self.operator_fingerprint = operator.fingerprint
        self.size = int(operator.shape[0])
        self.ordering = str(ordering)
        self.diagonal_pivot_threshold = float(diagonal_pivot_threshold)
        matrix = sp.csr_matrix(
            (operator.values, operator.indices, operator.indptr),
            shape=operator.shape,
            copy=True,
        ).tocsc()
        self.matrix_nnz = int(matrix.nnz)
        started = time.perf_counter()
        self._factor = spla.splu(
            matrix,
            permc_spec=self.ordering,
            diag_pivot_thresh=self.diagonal_pivot_threshold,
        )
        self.factorization_s = time.perf_counter() - started
        self.l_nnz = int(self._factor.L.nnz)
        self.u_nnz = int(self._factor.U.nnz)
        self.factor_nnz = self.l_nnz + self.u_nnz
        self.factor_storage_bytes = int(
            sum(
                array.nbytes
                for factor_matrix in (self._factor.L, self._factor.U)
                for array in (
                    factor_matrix.data,
                    factor_matrix.indices,
                    factor_matrix.indptr,
                )
            )
            + self._factor.perm_r.nbytes
            + self._factor.perm_c.nbytes
        )
        self.solve_count = 0
        self.solve_batch_count = 0
        self.solve_batch_size_max = 0
        self.solve_elapsed_s = 0.0
        self._solve_samples_s: list[float] = []
        self._destroyed = False

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("sparse-LU teacher has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self.size,) or out.shape != source.shape:
            raise ValueError("sparse-LU teacher rhs/output shape mismatch")
        started = time.perf_counter()
        values = np.asarray(self._factor.solve(source), dtype=np.complex128)
        elapsed = time.perf_counter() - started
        self.solve_elapsed_s += elapsed
        self._solve_samples_s.append(elapsed)
        if not np.all(np.isfinite(values)):
            raise RuntimeError("sparse-LU teacher returned NaN or Inf")
        out[:] = values
        self.solve_count += 1
        self.solve_batch_count += 1
        self.solve_batch_size_max = max(self.solve_batch_size_max, 1)

    def solve_many(
        self,
        rhs: np.ndarray,
        *,
        batch_size: int = 64,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self._destroyed:
            raise RuntimeError("sparse-LU teacher has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.ndim != 2 or source.shape[1] != self.size:
            raise ValueError("sparse-LU teacher batch shape mismatch")
        if batch_size < 1:
            raise ValueError("sparse-LU teacher batch size must be positive")
        output = np.empty_like(source)
        elapsed = np.empty(source.shape[0], dtype=np.float64)
        for first in range(0, source.shape[0], batch_size):
            stop = min(first + batch_size, source.shape[0])
            factor_rhs = np.asfortranarray(source[first:stop].T)
            started = time.perf_counter()
            solved = np.asarray(
                self._factor.solve(factor_rhs),
                dtype=np.complex128,
            ).T
            batch_elapsed = time.perf_counter() - started
            if not np.all(np.isfinite(solved)):
                raise RuntimeError("sparse-LU teacher returned NaN or Inf")
            output[first:stop] = solved
            count = stop - first
            per_rhs_elapsed = batch_elapsed / count
            elapsed[first:stop] = per_rhs_elapsed
            self.solve_elapsed_s += batch_elapsed
            self._solve_samples_s.extend([per_rhs_elapsed] * count)
            self.solve_count += count
            self.solve_batch_count += 1
            self.solve_batch_size_max = max(self.solve_batch_size_max, count)
        return output, elapsed

    @property
    def diagnostics(self) -> dict[str, Any]:
        samples = np.asarray(self._solve_samples_s, dtype=np.float64)
        return {
            "identity": "sparse_lu_teacher",
            "operator_fingerprint": self.operator_fingerprint,
            "size": self.size,
            "matrix_nnz": self.matrix_nnz,
            "ordering": self.ordering,
            "diagonal_pivot_threshold": self.diagonal_pivot_threshold,
            "factorization_s": self.factorization_s,
            "l_nnz": self.l_nnz,
            "u_nnz": self.u_nnz,
            "factor_nnz": self.factor_nnz,
            "fill_ratio": self.factor_nnz / max(self.matrix_nnz, 1),
            "factor_storage_bytes": self.factor_storage_bytes,
            "solve_count": self.solve_count,
            "solve_batch_count": self.solve_batch_count,
            "solve_batch_size_max": self.solve_batch_size_max,
            "solve_elapsed_s": self.solve_elapsed_s,
            "solve_mean_s": (
                float(np.mean(samples)) if samples.size else 0.0
            ),
            "solve_p95_s": (
                float(np.quantile(samples, 0.95)) if samples.size else 0.0
            ),
            "solve_max_s": (
                float(np.max(samples)) if samples.size else 0.0
            ),
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._factor = None  # type: ignore[assignment]
        self._solve_samples_s = []
        gc.collect()
        self._destroyed = True
