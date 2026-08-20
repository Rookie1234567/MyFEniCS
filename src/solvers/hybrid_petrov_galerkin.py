"""Fixed linear owner-row Petrov--Galerkin side correction."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve


PETROV_COARSE_RANK_LIMIT = 512
PETROV_CONDITION_LIMIT = 1.0e12

__all__ = (
    "PETROV_COARSE_RANK_LIMIT",
    "PETROV_CONDITION_LIMIT",
    "FixedLinearOwnerRowPetrovCorrectionAction",
)


def _action_diagnostics(action: Any) -> Mapping[str, Any]:
    diagnostics = getattr(action, "diagnostics", {})
    if callable(diagnostics):
        diagnostics = diagnostics()
    if not isinstance(diagnostics, Mapping):
        raise TypeError("Base action diagnostics must be a mapping.")
    return diagnostics


def _adjoint_matvec_without_matrix_copy(
    matrix: np.ndarray, vector: np.ndarray
) -> np.ndarray:
    """Compute ``matrix^H @ vector`` without conjugating the full matrix."""

    return np.conjugate(matrix.T @ np.conjugate(vector))


class FixedLinearOwnerRowPetrovCorrectionAction:
    """Apply a fixed owner-row Petrov correction around a borrowed base action.

    The only persistent large objects are the local rows of ``Z`` and ``Y``.
    The coarse matrix and its LU factors are replicated because their rank is
    explicitly capped at 512.  ``base_action`` and ``f_operator`` are borrowed
    and are never destroyed by this action.
    """

    operator_identity = "fixed_linear_owner_row_petrov_correction"

    def __init__(
        self,
        base_action: Any,
        f_operator: PETSc.Mat,
        z_local: np.ndarray,
        y_local: np.ndarray,
        *,
        factor_inventory: Mapping[str, Any] | None = None,
        condition_limit: float = PETROV_CONDITION_LIMIT,
        basis_ownership: str = "copy",
    ) -> None:
        if not hasattr(base_action, "apply"):
            raise TypeError("Base action must expose apply(source, target).")
        if not hasattr(f_operator, "mult"):
            raise TypeError("F operator must expose mult(source, target).")
        if not np.isfinite(float(condition_limit)) or float(condition_limit) <= 1.0:
            raise ValueError(
                "Petrov condition limit must be finite and greater than one."
            )
        if basis_ownership not in {"copy", "borrowed_readonly"}:
            raise ValueError("Petrov basis ownership must be copy or borrowed_readonly")

        self.base_action = base_action
        self.operator = f_operator
        self._comm = f_operator.getComm().tompi4py()
        self._destroyed = False
        self._apply_count = 0
        self._base_action_count = 0
        self._f_action_count = 0
        self._setup_f_action_count = 0
        self._condition_limit = float(condition_limit)
        self._base_work: PETSc.Vec | None = None
        self._f_work: PETSc.Vec | None = None
        self._residual_work: PETSc.Vec | None = None
        self._z_local: np.ndarray | None = None
        self._y_local: np.ndarray | None = None
        self._e: np.ndarray | None = None
        self._lu: np.ndarray | None = None
        self._pivots: np.ndarray | None = None

        rows, columns = (int(value) for value in f_operator.getSize())
        if rows != columns:
            raise ValueError("Petrov side correction requires a square F operator.")
        local_rows, local_columns = (int(value) for value in f_operator.getLocalSize())
        if local_rows != local_columns:
            raise ValueError(
                "Petrov side correction requires matching local ownership."
            )
        if basis_ownership == "borrowed_readonly":
            z_array = np.asarray(z_local, dtype=np.complex128, order="K")
            y_array = np.asarray(y_local, dtype=np.complex128, order="K")
            if z_array.flags.writeable or y_array.flags.writeable:
                raise ValueError("Borrowed Petrov bases must be read-only")
        else:
            z_array = np.array(z_local, dtype=np.complex128, copy=True, order="C")
            y_array = np.array(y_local, dtype=np.complex128, copy=True, order="C")
        if z_array.ndim != 2 or y_array.ndim != 2:
            raise ValueError("Owner-row Petrov bases must be two-dimensional arrays.")
        if z_array.shape != y_array.shape:
            raise ValueError("Owner-row right and left bases must have the same shape.")
        if z_array.shape[0] != local_rows:
            raise ValueError("Owner-row bases must match the local F row ownership.")
        coarse_rank = int(z_array.shape[1])
        if coarse_rank <= 0 or coarse_rank > PETROV_COARSE_RANK_LIMIT:
            raise ValueError("Petrov coarse rank must be in [1, 512].")
        right_template = f_operator.createVecRight()
        try:
            row_first, row_last = (
                int(value) for value in f_operator.getOwnershipRange()
            )
            right_first, right_last = (
                int(value) for value in right_template.getOwnershipRange()
            )
            if (row_first, row_last) != (right_first, right_last):
                raise ValueError(
                    "Owner-row basis requires matching F row and right-vector ownership."
                )
            if int(right_template.getSize()) != rows:
                raise ValueError("F right-vector global size does not match F rows.")
        finally:
            right_template.destroy()

        base_inventory = dict(_action_diagnostics(base_action))
        explicit_inventory = {} if factor_inventory is None else dict(factor_inventory)
        for key in ("exact_factor_count", "global_direct_factor_count"):
            if key in base_inventory and key in explicit_inventory:
                if int(base_inventory[key]) != int(explicit_inventory[key]):
                    raise ValueError(f"Conflicting factor inventory key: {key}")
        inventory = {**base_inventory, **explicit_inventory}
        missing = [
            key
            for key in ("exact_factor_count", "global_direct_factor_count")
            if key not in inventory
        ]
        if missing:
            raise ValueError(
                "Petrov factor inventory must prove zero exact/global factors: "
                + ", ".join(missing)
            )
        if int(inventory["exact_factor_count"]) != 0:
            raise ValueError("Petrov correction cannot retain an exact side factor.")
        if int(inventory["global_direct_factor_count"]) != 0:
            raise ValueError("Petrov correction cannot retain a global direct factor.")
        self._factor_inventory = inventory
        self._global_rows = rows
        self._local_rows = local_rows
        self._coarse_rank = coarse_rank
        self._z_local_nbytes = int(z_array.nbytes)
        self._y_local_nbytes = int(y_array.nbytes)
        self._basis_ownership = str(basis_ownership)
        self._e_nbytes = int(
            coarse_rank * coarse_rank * np.dtype(np.complex128).itemsize
        )
        self._z_local = z_array
        self._y_local = y_array

        try:
            self._base_work = f_operator.createVecLeft()
            self._f_work = f_operator.createVecLeft()
            self._residual_work = f_operator.createVecLeft()
            self._build_coarse_operator()
        except Exception:
            self.destroy()
            raise

    def _apply_f(
        self, source: PETSc.Vec, target: PETSc.Vec, *, setup: bool = False
    ) -> None:
        self.operator.mult(source, target)
        self._f_action_count += 1
        if setup:
            self._setup_f_action_count += 1

    def _build_coarse_operator(self) -> None:
        assert self._z_local is not None
        assert self._y_local is not None
        z_vector = self.operator.createVecRight()
        fz_vector = self.operator.createVecLeft()
        local_e = np.zeros((self._coarse_rank, self._coarse_rank), dtype=np.complex128)
        try:
            for column in range(self._coarse_rank):
                z_vector.getArray()[:] = self._z_local[:, column]
                self._apply_f(z_vector, fz_vector, setup=True)
                fz_local = np.asarray(
                    fz_vector.getArray(readonly=True), dtype=np.complex128
                )
                local_e[:, column] = _adjoint_matvec_without_matrix_copy(
                    self._y_local, fz_local
                )
            coarse_e = np.empty_like(local_e)
            self._comm.Allreduce(local_e, coarse_e, op=MPI.SUM)
        finally:
            fz_vector.destroy()
            z_vector.destroy()

        singular_value = np.linalg.svd(coarse_e, compute_uv=False)
        scale = float(singular_value[0]) if singular_value.size else 0.0
        rank_tolerance = np.finfo(float).eps * max(self._coarse_rank, 1) * scale
        svd_rank = int(np.count_nonzero(singular_value > rank_tolerance))
        condition = float(
            np.inf if singular_value[-1] == 0.0 else scale / singular_value[-1]
        )
        if svd_rank != self._coarse_rank:
            raise ValueError(
                f"Petrov coarse E is rank deficient: {svd_rank}/{self._coarse_rank}"
            )
        if not np.isfinite(condition) or condition > self._condition_limit:
            raise ValueError(
                "Petrov coarse E condition exceeds the fixed limit: "
                f"{condition:.6e} > {self._condition_limit:.6e}"
            )
        self._e = coarse_e
        self._lu, self._pivots = lu_factor(coarse_e, check_finite=True)
        self._svd_rank = svd_rank
        self._condition = condition

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Petrov correction action has been destroyed.")
        if (
            source.getSize() != self._global_rows
            or target.getSize() != self._global_rows
        ):
            raise ValueError("Petrov source/target global size does not match F.")
        assert self._base_work is not None
        assert self._f_work is not None
        assert self._residual_work is not None
        assert self._z_local is not None
        assert self._y_local is not None
        assert self._lu is not None and self._pivots is not None
        self.base_action.apply(source, self._base_work)
        self._base_action_count += 1
        self._apply_f(self._base_work, self._f_work)
        self._residual_work.getArray()[:] = source.getArray(readonly=True)
        self._residual_work.axpy(
            PETSc.ScalarType(-1.0),
            self._f_work,
        )
        residual_local = np.asarray(
            self._residual_work.getArray(readonly=True), dtype=np.complex128
        )
        local_rhs = _adjoint_matvec_without_matrix_copy(self._y_local, residual_local)
        rhs = np.empty_like(local_rhs)
        self._comm.Allreduce(local_rhs, rhs, op=MPI.SUM)
        coefficients = lu_solve((self._lu, self._pivots), rhs, check_finite=True)
        target.getArray()[:] = (
            np.asarray(self._base_work.getArray(readonly=True), dtype=np.complex128)
            + self._z_local @ coefficients
        )
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "operator_identity": self.operator_identity,
            "fixed_linear": True,
            "basis_storage": "owner_row_local",
            "basis_ownership": self._basis_ownership,
            "basis_copied": self._basis_ownership == "copy",
            "borrowed_basis_readonly": self._basis_ownership == "borrowed_readonly",
            "global_basis_materialized": False,
            "global_rows": int(self._global_rows),
            "local_rows": int(self._local_rows),
            "coarse_rank": int(self._coarse_rank),
            "z_local_bytes": int(self._z_local_nbytes),
            "y_local_bytes": int(self._y_local_nbytes),
            "coarse_e_bytes_per_rank": int(self._e_nbytes),
            "coarse_e_shape": [int(self._coarse_rank), int(self._coarse_rank)],
            "coarse_e_svd_rank": int(getattr(self, "_svd_rank", 0)),
            "coarse_e_condition": float(getattr(self, "_condition", np.nan)),
            "condition_limit": float(self._condition_limit),
            "apply_count": int(self._apply_count),
            "base_action_count": int(self._base_action_count),
            "f_action_count": int(self._f_action_count),
            "setup_f_action_count": int(self._setup_f_action_count),
            "exact_factor_count": int(self._factor_inventory["exact_factor_count"]),
            "global_direct_factor_count": int(
                self._factor_inventory["global_direct_factor_count"]
            ),
            "base_factor_count": self._factor_inventory.get("base_factor_count"),
            "destroyed": bool(self._destroyed),
            "lifecycle": {
                "borrowed_base_action": True,
                "borrowed_f_operator": True,
                "coarse_factor_released": self._e is None and self._lu is None,
                "owned_vectors_released": self._base_work is None,
                "basis_reference_released": self._z_local is None
                and self._y_local is None,
            },
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        for name in ("_base_work", "_f_work", "_residual_work"):
            vector = getattr(self, name)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        self._z_local = None
        self._y_local = None
        self._e = None
        self._lu = None
        self._pivots = None
        self._destroyed = True
