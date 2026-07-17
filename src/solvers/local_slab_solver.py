from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np
import scipy.sparse as sp


TINY = np.finfo(float).tiny


@dataclass(frozen=True)
class LocalCsrOperator:
    """Portable complex CSR representation of one owner-computes slab."""

    shape: tuple[int, int]
    indptr: np.ndarray
    indices: np.ndarray
    values: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rows, columns = (int(self.shape[0]), int(self.shape[1]))
        indptr = np.asarray(self.indptr, dtype=np.int64)
        indices = np.asarray(self.indices, dtype=np.int64)
        values = np.asarray(self.values, dtype=np.complex128)
        if rows <= 0 or columns <= 0:
            raise ValueError("local CSR operator shape must be positive")
        if indptr.shape != (rows + 1,) or indptr[0] != 0:
            raise ValueError("local CSR indptr has an invalid shape or origin")
        if np.any(indptr[1:] < indptr[:-1]) or int(indptr[-1]) != indices.size:
            raise ValueError("local CSR indptr is not monotone or has a wrong endpoint")
        if indices.shape != values.shape:
            raise ValueError("local CSR indices and values must have matching shapes")
        if indices.size and (indices.min() < 0 or indices.max() >= columns):
            raise ValueError("local CSR column index is out of bounds")
        if not np.all(np.isfinite(values)):
            raise ValueError("local CSR values must be finite")
        object.__setattr__(self, "shape", (rows, columns))
        object.__setattr__(self, "indptr", indptr)
        object.__setattr__(self, "indices", indices)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(np.asarray(self.shape, dtype=np.int64).tobytes())
        digest.update(self.indptr.tobytes())
        digest.update(self.indices.tobytes())
        digest.update(self.values.tobytes())
        return digest.hexdigest()

    @property
    def storage_bytes(self) -> int:
        return int(self.indptr.nbytes + self.indices.nbytes + self.values.nbytes)

    def action(self, vector: np.ndarray) -> np.ndarray:
        source = np.asarray(vector, dtype=np.complex128)
        if source.shape != (self.shape[1],):
            raise ValueError("local CSR input has the wrong shape")
        target = np.zeros(self.shape[0], dtype=np.complex128)
        for row in range(self.shape[0]):
            first, last = int(self.indptr[row]), int(self.indptr[row + 1])
            target[row] = np.dot(
                self.values[first:last], source[self.indices[first:last]]
            )
        return target

    def dense(self, *, maximum_entries: int = 4_000_000) -> np.ndarray:
        if self.shape[0] * self.shape[1] > maximum_entries:
            raise MemoryError("refusing to densify a production-sized slab operator")
        matrix = np.zeros(self.shape, dtype=np.complex128)
        for row in range(self.shape[0]):
            first, last = int(self.indptr[row]), int(self.indptr[row + 1])
            matrix[row, self.indices[first:last]] = self.values[first:last]
        return matrix


class ScipyCsrAction:
    """Persistent compiled CSR matvec for production-sized local actions."""

    def __init__(self, operator: LocalCsrOperator) -> None:
        self.operator_fingerprint = operator.fingerprint
        self.shape = operator.shape
        self._matrix = sp.csr_matrix(
            (operator.values, operator.indices, operator.indptr),
            shape=operator.shape,
            copy=True,
        )
        self._matrix.sum_duplicates()
        self._matrix.sort_indices()
        self.apply_count = 0

    @property
    def storage_bytes(self) -> int:
        return int(
            self._matrix.data.nbytes
            + self._matrix.indices.nbytes
            + self._matrix.indptr.nbytes
        )

    def action(self, vector: np.ndarray) -> np.ndarray:
        source = np.asarray(vector, dtype=np.complex128)
        if source.shape != (self.shape[1],):
            raise ValueError("compiled CSR input has the wrong shape")
        self.apply_count += 1
        return np.asarray(self._matrix @ source, dtype=np.complex128)

    def action_many(self, vectors: np.ndarray) -> np.ndarray:
        source = np.asarray(vectors, dtype=np.complex128)
        if source.ndim != 2 or source.shape[1] != self.shape[1]:
            raise ValueError("compiled CSR batch has the wrong shape")
        self.apply_count += int(source.shape[0])
        return np.asarray((self._matrix @ source.T).T, dtype=np.complex128)


@runtime_checkable
class LocalSlabSolver(Protocol):
    """Stable local backend contract used by Schwarz owner ranks."""

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None: ...

    @property
    def diagnostics(self) -> dict[str, Any]: ...

    def destroy(self) -> None: ...


class CallableLocalSlabSolver:
    """Adapter for an existing PETSc factor or another in-place local solve."""

    def __init__(
        self,
        size: int,
        action: Callable[[np.ndarray], np.ndarray],
        *,
        identity: str,
    ) -> None:
        self.size = int(size)
        self._action = action
        self.identity = str(identity)
        self.apply_count = 0
        self._destroyed = False

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("local slab solver has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self.size,) or out.shape != (self.size,):
            raise ValueError("local slab rhs/output shape mismatch")
        values = np.asarray(self._action(source), dtype=np.complex128)
        if values.shape != source.shape or not np.all(np.isfinite(values)):
            raise RuntimeError("local slab backend returned an invalid correction")
        out[:] = values
        self.apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {"identity": self.identity, "apply_count": self.apply_count}

    def destroy(self) -> None:
        self._action = None  # type: ignore[assignment]
        self._destroyed = True


class IluLocalSlabSolver(CallableLocalSlabSolver):
    """Named adapter for the existing factor-only shifted-F ILU action."""

    def __init__(self, size: int, action: Callable[[np.ndarray], np.ndarray]) -> None:
        super().__init__(size, action, identity="ilu")


class JacobiLocalSlabSolver:
    def __init__(self, diagonal: np.ndarray) -> None:
        values = np.asarray(diagonal, dtype=np.complex128)
        scale = float(np.max(np.abs(values), initial=0.0))
        if values.ndim != 1 or np.any(np.abs(values) <= max(scale, TINY) * 1.0e-14):
            raise ValueError("Jacobi local solver requires a finite nonzero diagonal")
        self._inverse = 1.0 / values
        self.apply_count = 0
        self._destroyed = False

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("Jacobi local solver has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != self._inverse.shape or out.shape != source.shape:
            raise ValueError("Jacobi local rhs/output shape mismatch")
        out[:] = self._inverse * source
        self.apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {"identity": "jacobi", "apply_count": self.apply_count}

    def destroy(self) -> None:
        self._inverse = np.empty(0, dtype=np.complex128)
        self._destroyed = True


class DenseTeacherLocalSlabSolver:
    """Small-fixture/high-accuracy teacher; never densifies production slabs."""

    def __init__(self, operator: LocalCsrOperator, *, maximum_entries: int = 4_000_000):
        self._matrix = operator.dense(maximum_entries=maximum_entries)
        self.apply_count = 0

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self._matrix.shape[0],) or out.shape != source.shape:
            raise ValueError("teacher local rhs/output shape mismatch")
        out[:] = np.linalg.solve(self._matrix, source)
        self.apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {"identity": "dense_teacher", "apply_count": self.apply_count}

    def destroy(self) -> None:
        self._matrix = np.empty((0, 0), dtype=np.complex128)


def relative_local_residual(
    operator: LocalCsrOperator, rhs: np.ndarray, correction: np.ndarray
) -> float:
    source = np.asarray(rhs, dtype=np.complex128)
    residual = source - operator.action(correction)
    return float(np.linalg.norm(residual) / max(float(np.linalg.norm(source)), TINY))
