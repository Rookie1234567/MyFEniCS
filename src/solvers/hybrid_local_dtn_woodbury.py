r"""Research-only exact DtN Woodbury action for one local Hybrid endcap.

The carrier applies the fixed identity

```math
A^{-1}r = z + W K^{-1} D z,
\qquad z = F^{-1}r,\quad W = F^{-1}C,\quad K = H-DW.
```

``F``, ``C``, ``D``, ``H`` and the base inverse are borrowed.  Only the
distributed owned rows of ``W`` and the replicated small ``K``/LU data are
owned here.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .condensed_dtn import gather_small_petsc_matrix


R4_MODAL_COUNT = 40

__all__ = (
    "R4_MODAL_COUNT",
    "HybridLocalDtnWoodburyOracle",
)


def _max_over_comm(comm: MPI.Comm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


def _gather_owned_small_vector(vector: PETSc.Vec) -> np.ndarray:
    """Replicate a small distributed vector without using matrix columns."""

    comm = vector.getComm().tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = np.asarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    packets = comm.allgather((first, last, local))
    values = np.empty(int(vector.getSize()), dtype=np.complex128)
    for packet_first, packet_last, packet_values in packets:
        values[packet_first:packet_last] = packet_values
    return values


class HybridLocalDtnWoodburyOracle:
    """Exact fixed 40-mode Woodbury action over borrowed local components."""

    def __init__(
        self,
        base_inverse: Any,
        components: Any,
        *,
        base_identity: str = "exact_F_direct",
    ) -> None:
        self.base_inverse = base_inverse
        self.components = components
        self.F = components.F
        self.C = components.C
        self.D = components.D
        self.H = components.H
        self.base_identity = str(base_identity)
        self.comm = self.F.getComm().tompi4py()
        self.n_aux = int(self.H.getSize()[0])
        if self.n_aux != R4_MODAL_COUNT or self.H.getSize() != (
            R4_MODAL_COUNT,
            R4_MODAL_COUNT,
        ):
            raise ValueError("R4 Woodbury oracle requires exactly 40 auxiliary modes")
        if self.C.getSize() != (self.F.getSize()[0], self.n_aux):
            raise ValueError("borrowed C has incompatible active/modal dimensions")
        if self.D.getSize() != (self.n_aux, self.F.getSize()[0]):
            raise ValueError("borrowed D has incompatible modal/active dimensions")
        if self.F.getSize()[0] != self.D.getSize()[1]:
            raise ValueError("borrowed F and D have incompatible active dimensions")
        if not hasattr(base_inverse, "solve"):
            raise TypeError("R4 base inverse must expose solve(source, target)")

        self._destroyed = False
        self._z = self.F.createVecLeft()
        self._d_work = self.D.createVecLeft()
        self._W_local: np.ndarray | None = None
        self._K: np.ndarray | None = None
        self._lu: np.ndarray | None = None
        self._piv: np.ndarray | None = None
        self._K_rank: int | None = None
        self._K_condition: float | None = None
        self._setup_seconds = 0.0
        self._apply_seconds = 0.0
        self.apply_count = 0
        self._build()

    def _build(self) -> None:
        started = perf_counter()
        H_dense = np.asarray(gather_small_petsc_matrix(self.H), dtype=np.complex128)
        local_rows = int(self.F.getLocalSize()[0])
        W_local = np.empty((local_rows, self.n_aux), dtype=np.complex128)
        D_times_W = np.empty((self.n_aux, self.n_aux), dtype=np.complex128)
        modal_basis = self.C.createVecRight()
        c_column = self.C.createVecLeft()
        w_column = self.F.createVecLeft()
        d_column = self.D.createVecLeft()
        try:
            first, last = (int(value) for value in modal_basis.getOwnershipRange())
            for column in range(self.n_aux):
                modal_basis.set(0.0)
                if first <= column < last:
                    modal_basis.getArray()[column - first] = PETSc.ScalarType(1.0)
                modal_basis.assemble()
                self.C.mult(modal_basis, c_column)
                self.base_inverse.solve(c_column, w_column)
                W_local[:, column] = np.asarray(
                    w_column.getArray(readonly=True),
                    dtype=np.complex128,
                )
                self.D.mult(w_column, d_column)
                D_times_W[:, column] = _gather_owned_small_vector(d_column)
        finally:
            d_column.destroy()
            w_column.destroy()
            c_column.destroy()
            modal_basis.destroy()

        K = H_dense - D_times_W
        singular_values = np.linalg.svd(K, compute_uv=False)
        if singular_values.size == 0 or not np.all(np.isfinite(singular_values)):
            raise RuntimeError("R4 Woodbury K SVD is not finite")
        scale = float(singular_values[0])
        rank_tolerance = np.finfo(np.float64).eps * max(K.shape) * scale
        rank = int(np.count_nonzero(singular_values > rank_tolerance))
        condition = (
            float(singular_values[0] / singular_values[-1])
            if singular_values[-1] > 0.0
            else float("inf")
        )
        lu, piv = lu_factor(K, check_finite=True)
        self._W_local = W_local
        self._K = K
        self._lu = np.asarray(lu, dtype=np.complex128)
        self._piv = np.asarray(piv, dtype=np.int32)
        self._K_rank = rank
        self._K_condition = condition
        self._setup_seconds = _max_over_comm(
            self.comm,
            perf_counter() - started,
        )

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the exact Woodbury inverse without touching borrowed objects."""

        if self._destroyed:
            raise RuntimeError("R4 Woodbury oracle has been destroyed")
        if (
            source.getSize() != self.F.getSize()[1]
            or target.getSize() != self.F.getSize()[0]
        ):
            raise ValueError("R4 Woodbury source/target size does not match F")
        started = perf_counter()
        self.base_inverse.solve(source, self._z)
        self.D.mult(self._z, self._d_work)
        d_values = _gather_owned_small_vector(self._d_work)
        q = lu_solve((self._lu, self._piv), d_values, check_finite=True)
        self._z.copy(target)
        target.getArray()[:] += self._W_local @ q
        self.apply_count += 1
        self._apply_seconds += _max_over_comm(
            self.comm,
            perf_counter() - started,
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        W_local = self._W_local
        K = self._K
        lu = self._lu
        piv = self._piv
        return {
            "base_identity": self.base_identity,
            "n_aux": self.n_aux,
            "normal_equations": False,
            "W_local_shape": None if W_local is None else list(W_local.shape),
            "W_local_nbytes": None if W_local is None else int(W_local.nbytes),
            "K_shape": None if K is None else list(K.shape),
            "K_dtype": None if K is None else str(K.dtype),
            "K_nbytes": None if K is None else int(K.nbytes),
            "K_rank": self._K_rank,
            "K_condition_number": self._K_condition,
            "LU_shape": None if lu is None else list(lu.shape),
            "LU_nbytes": (
                None if lu is None or piv is None else int(lu.nbytes + piv.nbytes)
            ),
            "setup_seconds": float(self._setup_seconds),
            "apply_count": int(self.apply_count),
            "apply_seconds": float(self._apply_seconds),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        """Release owned scratch and dense data; borrowed components survive."""

        if self._destroyed:
            return
        self._z.destroy()
        self._d_work.destroy()
        self._z = None
        self._d_work = None
        self._W_local = None
        self._K = None
        self._lu = None
        self._piv = None
        self._destroyed = True
