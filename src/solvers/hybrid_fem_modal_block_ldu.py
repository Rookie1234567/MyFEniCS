"""Exact block-LDU oracle for the Task037b Hybrid action operator.

The global operator remains the H2b MatPython action.  This module temporarily
uses explicit-condensed bottom/top matrices and their MUMPS factors only to
verify the exact right block-LDU algebra on a small oracle problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import HybridAugmentedLayout
from .hybrid_fem_modal_schur_direct import (
    HybridModalSchurDirectSystem,
    build_hybrid_modal_schur_direct_system,
)

__all__ = (
    "HybridBlockLduPreconditioner",
    "HybridBlockLduSolveResult",
    "create_exact_block_ldu_preconditioner",
    "solve_exact_block_ldu",
)

_TINY = np.finfo(float).tiny


def _replicated_modal_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    owner = comm.size - 1
    local = None
    if comm.rank == owner:
        local = np.asarray(
            vector.getValues(np.arange(vector.getSize(), dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


@dataclass
class HybridBlockLduPreconditioner:
    """Reusable exact right block-LDU application context.

    ``bottom_system`` and ``top_system`` are explicit-condensed oracle views;
    the operator being preconditioned can still be the H2b action-only matrix.
    The two direct factors and the dense modal Schur are owned here.
    """

    layout: HybridAugmentedLayout
    coupling: HybridInternalModeCoupling
    bottom_system: object
    top_system: object
    modal_schur_system: HybridModalSchurDirectSystem
    _destroyed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        bottom_factor = self.modal_schur_system.bottom_factor
        top_factor = self.modal_schur_system.top_factor
        if bottom_factor is None or top_factor is None:
            raise RuntimeError("H3 exact block-LDU requires both direct factors.")
        self.bottom_factor = bottom_factor
        self.top_factor = top_factor
        self.modal_schur = np.asarray(
            self.modal_schur_system.modal_schur, dtype=np.complex128
        )
        self.mode_count = int(self.coupling.mode_count_per_direction)
        self._forward_factors = np.asarray(
            self.coupling.propagation.forward.factors, dtype=np.complex128
        )
        self._backward_factors = np.asarray(
            self.coupling.propagation.backward.factors, dtype=np.complex128
        )
        self._bottom_rhs = self.bottom_system.A.createVecRight()
        self._top_rhs = self.top_system.A.createVecRight()
        self._bottom_first = self.bottom_system.A.createVecLeft()
        self._top_first = self.top_system.A.createVecLeft()
        self._bottom_delta = self.bottom_system.A.createVecLeft()
        self._top_delta = self.top_system.A.createVecLeft()
        self._bottom_coupling = self.bottom_system.A.createVecLeft()
        self._top_coupling = self.top_system.A.createVecLeft()
        self._bottom_projection = self.coupling.bottom.projection.createVecLeft()
        self._top_projection = self.coupling.top.projection.createVecLeft()
        self._bottom_positive_source = (
            self.coupling.bottom.positive_traction.createVecRight()
        )
        self._bottom_negative_source = (
            self.coupling.bottom.negative_traction.createVecRight()
        )
        self._top_positive_source = self.coupling.top.positive_traction.createVecRight()
        self._top_negative_source = self.coupling.top.negative_traction.createVecRight()
        self._bottom_positive_target = (
            self.coupling.bottom.positive_traction.createVecLeft()
        )
        self._bottom_negative_target = (
            self.coupling.bottom.negative_traction.createVecLeft()
        )
        self._top_positive_target = self.coupling.top.positive_traction.createVecLeft()
        self._top_negative_target = self.coupling.top.negative_traction.createVecLeft()
        self._modal_rhs = np.empty(2 * self.mode_count, dtype=np.complex128)
        self._modal_solution = np.empty_like(self._modal_rhs)
        self._check_layouts()

    @property
    def direct_factor_count(self) -> int:
        return 2

    @property
    def factors_released(self) -> bool:
        return self._destroyed

    @property
    def inventory(self) -> dict[str, object]:
        return {
            "global_A_materialized": False,
            "oracle_local_direct_factor_count": self.direct_factor_count
            if not self._destroyed
            else 0,
            "bottom_factor_released": self._destroyed,
            "top_factor_released": self._destroyed,
            "modal_schur_condition": float(
                self.modal_schur_system.modal_schur_condition
            ),
        }

    def _check_layouts(self) -> None:
        expected_bottom = sum(self.layout.bottom_local_sizes)
        if self.bottom_system.A.getSize() != (expected_bottom, expected_bottom):
            raise ValueError("H3 bottom oracle matrix does not match layout.")
        expected_top = sum(self.layout.top_local_sizes)
        if self.top_system.A.getSize() != (expected_top, expected_top):
            raise ValueError("H3 top oracle matrix does not match layout.")
        if self.modal_schur.shape != (self.layout.modal_count, self.layout.modal_count):
            raise ValueError("H3 modal Schur does not match the Hybrid layout.")

    def _source_parts(self, source: PETSc.Vec) -> np.ndarray:
        local = np.asarray(source.getArray(readonly=True))
        self._bottom_rhs.getArray()[:] = local[self.layout.local_bottom_slice]
        self._top_rhs.getArray()[:] = local[self.layout.local_top_slice]
        if self.layout.comm.rank == self.layout.modal_owner:
            modal_local = np.asarray(
                local[self.layout.local_modal_slice], dtype=np.complex128
            ).copy()
        else:
            modal_local = None
        return np.asarray(
            self.layout.comm.bcast(modal_local, root=self.layout.modal_owner),
            dtype=np.complex128,
        )

    def _apply_modal_tractions(self, modal: np.ndarray) -> None:
        count = self.mode_count
        _set_owned_values(self._bottom_positive_source, modal[:count])
        _set_owned_values(
            self._bottom_negative_source,
            self._backward_factors * modal[count:],
        )
        _set_owned_values(
            self._top_positive_source,
            self._forward_factors * modal[:count],
        )
        _set_owned_values(self._top_negative_source, modal[count:])
        self.coupling.bottom.positive_traction.mult(
            self._bottom_positive_source, self._bottom_positive_target
        )
        self.coupling.bottom.negative_traction.mult(
            self._bottom_negative_source, self._bottom_negative_target
        )
        self._bottom_coupling.getArray()[:] = self._bottom_positive_target.getArray(
            readonly=True
        ) + self._bottom_negative_target.getArray(readonly=True)
        self.coupling.top.positive_traction.mult(
            self._top_positive_source, self._top_positive_target
        )
        self.coupling.top.negative_traction.mult(
            self._top_negative_source, self._top_negative_target
        )
        self._top_coupling.getArray()[:] = self._top_positive_target.getArray(
            readonly=True
        ) + self._top_negative_target.getArray(readonly=True)

    def apply(self, _pc: PETSc.PC | None, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("H3 block-LDU preconditioner has been destroyed")
        modal = self._source_parts(source)
        self.bottom_factor.solve(self._bottom_rhs, self._bottom_first)
        self.top_factor.solve(self._top_rhs, self._top_first)
        self.coupling.bottom.projection.mult(
            self._bottom_first, self._bottom_projection
        )
        self.coupling.top.projection.mult(self._top_first, self._top_projection)
        self._modal_rhs[:] = modal
        count = self.mode_count
        self._modal_rhs[:count] -= _replicated_modal_values(self._bottom_projection)
        self._modal_rhs[count:] -= _replicated_modal_values(self._top_projection)
        self._modal_solution[:] = np.linalg.solve(self.modal_schur, self._modal_rhs)
        self._apply_modal_tractions(self._modal_solution)
        self.bottom_factor.solve(self._bottom_coupling, self._bottom_delta)
        self.top_factor.solve(self._top_coupling, self._top_delta)
        self._bottom_first.axpy(PETSc.ScalarType(-1.0), self._bottom_delta)
        self._top_first.axpy(PETSc.ScalarType(-1.0), self._top_delta)
        target_local = target.getArray()
        target_local[self.layout.local_bottom_slice] = self._bottom_first.getArray(
            readonly=True
        )
        target_local[self.layout.local_top_slice] = self._top_first.getArray(
            readonly=True
        )
        if self.layout.comm.rank == self.layout.modal_owner:
            target_local[self.layout.local_modal_slice] = self._modal_solution

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        for vector in (
            self._top_negative_target,
            self._top_positive_target,
            self._bottom_negative_target,
            self._bottom_positive_target,
            self._top_negative_source,
            self._top_positive_source,
            self._bottom_negative_source,
            self._bottom_positive_source,
            self._top_projection,
            self._bottom_projection,
            self._top_coupling,
            self._bottom_coupling,
            self._top_delta,
            self._bottom_delta,
            self._top_first,
            self._bottom_first,
            self._top_rhs,
            self._bottom_rhs,
        ):
            vector.destroy()
        self.modal_schur_system.destroy()
        self._destroyed = True


@dataclass
class HybridBlockLduSolveResult:
    solution: PETSc.Vec
    iterations: int
    converged_reason: int
    reported_relative_residual: float
    true_relative_residual: float
    block_relative_residuals: dict[str, float]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if not self._destroyed:
            self.solution.destroy()
            self._destroyed = True


def create_exact_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: object,
    top_system: object,
    coupling: HybridInternalModeCoupling,
) -> HybridBlockLduPreconditioner:
    """Create the H3 exact right block-LDU oracle and retain two local factors."""

    modal_schur = build_hybrid_modal_schur_direct_system(
        bottom_system,
        top_system,
        coupling,
    )
    return HybridBlockLduPreconditioner(
        layout=layout,
        coupling=coupling,
        bottom_system=bottom_system,
        top_system=top_system,
        modal_schur_system=modal_schur,
    )


def _residual_metrics(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
) -> tuple[float, dict[str, float]]:
    residual = rhs.duplicate()
    operator.mult(solution, residual)
    residual.scale(PETSc.ScalarType(-1.0))
    residual.axpy(PETSc.ScalarType(1.0), rhs)
    rhs_bottom, rhs_top, rhs_modal = context.layout.split(
        rhs,
        context.bottom_system.b,
        context.top_system.b,
    )
    residual_bottom, residual_top, residual_modal = context.layout.split(
        residual,
        context.bottom_system.b,
        context.top_system.b,
    )
    solution_bottom, solution_top, solution_modal = context.layout.split(
        solution,
        context.bottom_system.b,
        context.top_system.b,
    )
    bottom_action = context.bottom_system.A.createVecLeft()
    top_action = context.top_system.A.createVecLeft()
    try:
        context.bottom_system.A.mult(solution_bottom, bottom_action)
        context.top_system.A.mult(solution_top, top_action)
        context._apply_modal_tractions(solution_modal)
        context.coupling.bottom.projection.mult(
            solution_bottom, context._bottom_projection
        )
        context.coupling.top.projection.mult(solution_top, context._top_projection)
        bottom_scale = max(
            float(rhs_bottom.norm()),
            float(bottom_action.norm()),
            float(context._bottom_coupling.norm()),
            1.0e-30,
        )
        top_scale = max(
            float(rhs_top.norm()),
            float(top_action.norm()),
            float(context._top_coupling.norm()),
            1.0e-30,
        )
        modal_scale = max(
            float(np.linalg.norm(rhs_modal)),
            float(np.linalg.norm(_replicated_modal_values(context._bottom_projection))),
            float(np.linalg.norm(_replicated_modal_values(context._top_projection))),
            float(
                np.linalg.norm(
                    context.modal_schur_system.modal_constraint @ solution_modal
                )
            ),
            1.0e-30,
        )
        block = {
            "bottom": float(residual_bottom.norm() / bottom_scale),
            "top": float(residual_top.norm() / top_scale),
            "modal": float(np.linalg.norm(residual_modal) / modal_scale),
        }
        global_relative = float(residual.norm() / max(float(rhs.norm()), _TINY))
    finally:
        top_action.destroy()
        bottom_action.destroy()
        solution_top.destroy()
        solution_bottom.destroy()
        residual_top.destroy()
        residual_bottom.destroy()
        rhs_top.destroy()
        rhs_bottom.destroy()
        residual.destroy()
    return global_relative, block


def solve_exact_block_ldu(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
) -> HybridBlockLduSolveResult:
    """Solve one RHS with fixed right FGMRES and the exact block-LDU PC."""

    ksp = PETSc.KSP().create(operator.getComm())
    ksp.setOperators(operator)
    ksp.setType(PETSc.KSP.Type.FGMRES)
    ksp.setGMRESRestart(90)
    ksp.setPCSide(PETSc.PC.Side.RIGHT)
    ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
    ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=3)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.PYTHON)
    pc.setPythonContext(context)
    ksp.setUp()
    solution = rhs.duplicate()
    solution.set(0.0)
    try:
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        reported = float(ksp.getResidualNorm()) / max(float(rhs.norm()), _TINY)
        true_residual, block_residuals = _residual_metrics(
            operator, rhs, solution, context
        )
    except Exception:
        solution.destroy()
        raise
    finally:
        ksp.destroy()
        context.destroy()
    return HybridBlockLduSolveResult(
        solution=solution,
        iterations=iterations,
        converged_reason=reason,
        reported_relative_residual=reported,
        true_relative_residual=true_residual,
        block_relative_residuals=block_residuals,
    )
