"""Fixed residual-error subspace correction for the Task39 side capacity probe."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import solve_triangular

__all__ = (
    "FixedSideErrorSubspaceCorrectionAction",
    "build_fixed_side_error_subspace_correction_action",
)


class FixedSideErrorSubspaceCorrectionAction:
    """Apply a frozen block-Arnoldi correction to a borrowed fixed side action.

    The action owns only its Arnoldi/QR vectors, dense triangular ``R`` and
    scratch vectors.  The matrix-free side operator and the one-pass
    ILU(0)+dynamic-DtN action are borrowed and remain usable after ``destroy``.
    """

    seed_count = 8
    arnoldi_depth = 16
    rank_cap = 128
    dependence_relative_tolerance = 1.0e-12
    operator_identity = "fixed_side_error_subspace_correction"

    def __init__(
        self,
        operator: PETSc.Mat,
        base_action: Any,
        seeds: Sequence[PETSc.Vec],
    ) -> None:
        if str(operator.getType()).lower() != "python":
            raise TypeError("Fixed side correction requires a matrix-free MatPython")
        if not hasattr(base_action, "apply"):
            raise TypeError(
                "Fixed side correction base action needs apply(source, target)"
            )
        if len(seeds) != self.seed_count:
            raise ValueError("Fixed side correction requires exactly eight seeds")
        if operator.getSize()[0] != operator.getSize()[1]:
            raise ValueError("Fixed side correction requires a square operator")
        base_diagnostics = base_action.diagnostics
        self._base_ilu_factor_count = int(base_diagnostics["base_factor_count"])
        self._base_nested_ksp_created = bool(base_diagnostics["nested_ksp_created"])
        self.operator: PETSc.Mat | None = operator
        self.base_action: Any | None = base_action
        self._comm = operator.getComm().tompi4py()
        self._u: list[PETSc.Vec] = []
        self._q: list[PETSc.Vec] = []
        self._r: np.ndarray | None = None
        self._base_solution: PETSc.Vec | None = operator.createVecLeft()
        self._operator_image: PETSc.Vec | None = operator.createVecLeft()
        self._residual: PETSc.Vec | None = operator.createVecLeft()
        self._destroyed = False
        self._apply_count = 0
        self._operator_apply_count = 0
        self._base_apply_count = 0
        self._setup_operator_apply_count = 0
        self._setup_base_apply_count = 0
        self._layers_completed = 0
        self._seed_rank = 0
        self._dependent_directions = 0
        self._dependent_v_directions = 0
        self._qr_reconstruction_error = 0.0
        self._q_orthogonality_error = 0.0
        self._r_condition_number = float("nan")
        self._setup_seconds = 0.0

        try:
            self._build(seeds)
        except Exception:
            self.destroy()
            raise

    def _orthonormalize(
        self,
        candidate: PETSc.Vec,
        basis: Sequence[PETSc.Vec],
    ) -> PETSc.Vec | None:
        work = candidate.duplicate()
        candidate.copy(work)
        candidate_norm = float(candidate.norm())
        if not np.isfinite(candidate_norm):
            work.destroy()
            raise ValueError("Fixed side Arnoldi candidate norm is non-finite")
        for _ in range(2):
            for vector in basis:
                coefficient = np.conjugate(vector.dot(work))
                work.axpy(-coefficient, vector)
        residual_norm = float(work.norm())
        if not np.isfinite(residual_norm):
            work.destroy()
            raise ValueError("Fixed side Arnoldi residual norm is non-finite")
        if residual_norm <= self.dependence_relative_tolerance * max(
            candidate_norm, 1.0e-30
        ):
            work.destroy()
            return None
        work.scale(PETSc.ScalarType(1.0 / residual_norm))
        return work

    def _apply_error(self, vector: PETSc.Vec) -> PETSc.Vec:
        candidate = vector.duplicate()
        vector.copy(candidate)
        self.base_action.apply(vector, self._base_solution)
        self._base_apply_count += 1
        self.operator.mult(self._base_solution, self._operator_image)
        self._operator_apply_count += 1
        candidate.axpy(PETSc.ScalarType(-1.0), self._operator_image)
        return candidate

    def _build(self, seeds: Sequence[PETSc.Vec]) -> None:
        started = perf_counter()
        current: list[PETSc.Vec] = []
        for seed in seeds:
            if seed.getSize() != self.operator.getSize()[1]:
                raise ValueError("Fixed side seed has the wrong global size")
            candidate = self.operator.createVecRight()
            seed.copy(candidate)
            accepted = self._orthonormalize(candidate, self._u)
            candidate.destroy()
            if accepted is None:
                self._dependent_directions += 1
                continue
            self._u.append(accepted)
            current.append(accepted)
        self._seed_rank = len(current)

        self._layers_completed = 1 if current else 0
        for layer in range(1, self.arnoldi_depth):
            if not current or len(self._u) >= self.rank_cap:
                break
            next_current: list[PETSc.Vec] = []
            for vector in current:
                candidate = self._apply_error(vector)
                accepted = self._orthonormalize(candidate, self._u)
                candidate.destroy()
                if accepted is None:
                    self._dependent_directions += 1
                    continue
                self._u.append(accepted)
                next_current.append(accepted)
                if len(self._u) >= self.rank_cap:
                    break
            self._layers_completed = layer + 1
            current = next_current

        self._setup_operator_apply_count = self._operator_apply_count
        self._setup_base_apply_count = self._base_apply_count
        if not self._u:
            raise ValueError("Fixed side Arnoldi produced no independent direction")

        retained_u: list[PETSc.Vec] = []
        q_vectors: list[PETSc.Vec] = []
        columns: list[list[complex]] = []
        for vector in self._u:
            value = self.operator.createVecLeft()
            self.operator.mult(vector, value)
            self._operator_apply_count += 1
            value_norm = float(value.norm())
            if not np.isfinite(value_norm):
                value.destroy()
                raise ValueError("Fixed side QR vector norm is non-finite")
            work = value.duplicate()
            value.copy(work)
            coefficients = np.zeros(len(q_vectors), dtype=np.complex128)
            for _ in range(2):
                for index, q_vector in enumerate(q_vectors):
                    coefficient = np.conjugate(q_vector.dot(work))
                    coefficients[index] += complex(coefficient)
                    work.axpy(-coefficient, q_vector)
            diagonal = float(work.norm())
            if not np.isfinite(diagonal):
                value.destroy()
                work.destroy()
                raise ValueError("Fixed side QR residual norm is non-finite")
            if diagonal <= self.dependence_relative_tolerance * max(
                value_norm, 1.0e-30
            ):
                value.destroy()
                work.destroy()
                vector.destroy()
                self._dependent_v_directions += 1
                continue

            work.scale(PETSc.ScalarType(1.0 / diagonal))
            column = coefficients.tolist() + [complex(diagonal)]
            reconstruction = value.duplicate()
            reconstruction.set(0.0)
            for coefficient, q_vector in zip(column, (*q_vectors, work)):
                reconstruction.axpy(coefficient, q_vector)
            difference = value.duplicate()
            value.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), reconstruction)
            reconstruction_error = float(difference.norm()) / max(value_norm, 1.0e-30)
            self._qr_reconstruction_error = max(
                self._qr_reconstruction_error, reconstruction_error
            )
            difference.destroy()
            reconstruction.destroy()
            value.destroy()
            retained_u.append(vector)
            q_vectors.append(work)
            columns.append(column)

        self._u = retained_u
        self._q = q_vectors
        rank = len(self._q)
        if rank == 0:
            raise ValueError("Fixed side QR produced no independent image direction")
        self._r = np.zeros((rank, rank), dtype=np.complex128)
        for column_index, column in enumerate(columns):
            self._r[: len(column), column_index] = column
        if not np.all(np.isfinite(self._r)):
            raise ValueError("Fixed side QR R is non-finite")
        r_inverse = solve_triangular(
            self._r,
            np.eye(rank, dtype=np.complex128),
            lower=False,
            check_finite=True,
        )
        self._r_condition_number = float(
            np.linalg.norm(self._r, ord=np.inf) * np.linalg.norm(r_inverse, ord=np.inf)
        )
        if not np.isfinite(self._r_condition_number):
            raise ValueError("Fixed side QR R condition is non-finite")
        for row, left in enumerate(self._q):
            for column, right in enumerate(self._q):
                expected = 1.0 if row == column else 0.0
                self._q_orthogonality_error = max(
                    self._q_orthogonality_error,
                    abs(complex(np.conjugate(left.dot(right))) - expected),
                )
        self._setup_seconds = float(
            self._comm.allreduce(perf_counter() - started, op=MPI.MAX)
        )

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Fixed side correction has been destroyed")
        if source.getSize() != self.operator.getSize()[1]:
            raise ValueError("Fixed side correction source has the wrong size")
        if target.getSize() != self.operator.getSize()[0]:
            raise ValueError("Fixed side correction target has the wrong size")
        self.base_action.apply(source, self._base_solution)
        self._base_apply_count += 1
        self.operator.mult(self._base_solution, self._operator_image)
        self._operator_apply_count += 1
        source.copy(self._residual)
        self._residual.axpy(PETSc.ScalarType(-1.0), self._operator_image)
        coefficients = np.asarray(
            [np.conjugate(q_vector.dot(self._residual)) for q_vector in self._q],
            dtype=np.complex128,
        )
        correction_coefficients = solve_triangular(
            self._r,
            coefficients,
            lower=False,
            check_finite=True,
        )
        self._base_solution.copy(target)
        for coefficient, u_vector in zip(correction_coefficients, self._u):
            target.axpy(PETSc.ScalarType(coefficient), u_vector)
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "research_only": True,
            "operator_identity": self.operator_identity,
            "seed_count": self.seed_count,
            "seed_rank": self._seed_rank,
            "arnoldi_depth": self.arnoldi_depth,
            "seed_block_is_layer_one": True,
            "layers_completed": self._layers_completed,
            "rank_cap": self.rank_cap,
            "rank": len(self._q),
            "dependent_directions": self._dependent_directions,
            "dependent_v_directions": self._dependent_v_directions,
            "dependence_relative_tolerance": self.dependence_relative_tolerance,
            "qr_reconstruction_relative_error": self._qr_reconstruction_error,
            "q_orthogonality_error": self._q_orthogonality_error,
            "R_shape": None if self._r is None else list(self._r.shape),
            "R_condition_number": self._r_condition_number,
            "normal_equations": False,
            "svd": False,
            "direct_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
            "base_ilu_factor_count": self._base_ilu_factor_count,
            "base_nested_ksp_created": self._base_nested_ksp_created,
            "operator_borrowed": True,
            "base_action_borrowed": True,
            "setup_operator_apply_count": self._setup_operator_apply_count,
            "setup_base_apply_count": self._setup_base_apply_count,
            "operator_apply_count": self._operator_apply_count,
            "base_apply_count": self._base_apply_count,
            "apply_count": self._apply_count,
            "setup_seconds": self._setup_seconds,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        for vector in self._u:
            vector.destroy()
        for vector in self._q:
            vector.destroy()
        self._u = []
        self._q = []
        if self._base_solution is not None:
            self._base_solution.destroy()
            self._base_solution = None
        if self._operator_image is not None:
            self._operator_image.destroy()
            self._operator_image = None
        if self._residual is not None:
            self._residual.destroy()
            self._residual = None
        self._r = None
        self.operator = None
        self.base_action = None
        self._destroyed = True


def build_fixed_side_error_subspace_correction_action(
    operator: PETSc.Mat,
    base_action: Any,
    seeds: Sequence[PETSc.Vec],
) -> FixedSideErrorSubspaceCorrectionAction:
    """Explicitly opt in to the fixed Task39 side-capacity correction."""

    return FixedSideErrorSubspaceCorrectionAction(operator, base_action, seeds)
