"""Action-only assembled-block oracle for the Task037b Hybrid system.

The terminal FEM blocks remain assembled, while the global Hybrid operator is
represented only by a PETSc MatPython action.  The monolithic AIJ reference is
owned by the focused test, never by this production context.
"""

from __future__ import annotations

import numpy as np
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from .hybrid_local_dtn import HybridLocalDtnSystem

__all__ = ("HybridBlockOperator", "create_hybrid_assembled_block_action")


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


def _gather_owned_small(vector: PETSc.Vec, expected_size: int) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    values = None
    if comm.rank == comm.size - 1:
        values = np.asarray(
            vector.getValues(np.arange(expected_size, dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(values, root=comm.size - 1), dtype=np.complex128)


class HybridBlockOperator:
    """MatPython context for exact assembled-block Hybrid multiplication.

    ``bottom_system.A`` and ``top_system.A`` are borrowed assembled blocks.
    Coupling matrices are also borrowed and applied as actions.  Only scratch
    vectors are owned here; no global monolithic matrix is formed or retained.
    """

    def __init__(
        self,
        bottom_system: HybridLocalDtnSystem,
        top_system: HybridLocalDtnSystem,
        coupling: HybridInternalModeCoupling,
    ) -> None:
        self.bottom_system = bottom_system
        self.top_system = top_system
        self.coupling = coupling
        self.layout = HybridAugmentedLayout.build(
            bottom_system,
            top_system,
            coupling.internal_unknown_count,
        )
        self.mode_count = int(coupling.mode_count_per_direction)
        self._forward_factors = np.asarray(
            coupling.propagation.forward.factors, dtype=np.complex128
        )
        self._backward_factors = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
        self.modal_constraint = internal_modal_constraint_matrix(coupling)
        self._bottom_source = bottom_system.A.createVecRight()
        self._top_source = top_system.A.createVecRight()
        self._bottom_target = bottom_system.A.createVecLeft()
        self._top_target = top_system.A.createVecLeft()
        self._bottom_positive_source = (
            coupling.bottom.positive_traction.createVecRight()
        )
        self._bottom_negative_source = (
            coupling.bottom.negative_traction.createVecRight()
        )
        self._top_positive_source = coupling.top.positive_traction.createVecRight()
        self._top_negative_source = coupling.top.negative_traction.createVecRight()
        self._bottom_positive_target = coupling.bottom.positive_traction.createVecLeft()
        self._bottom_negative_target = coupling.bottom.negative_traction.createVecLeft()
        self._top_positive_target = coupling.top.positive_traction.createVecLeft()
        self._top_negative_target = coupling.top.negative_traction.createVecLeft()
        self._bottom_projection_target = coupling.bottom.projection.createVecLeft()
        self._top_projection_target = coupling.top.projection.createVecLeft()
        self._destroyed = False
        self.inventory = {
            "matrix_type": "python",
            "matrix_free": True,
            "global_A_materialized": False,
            "bottom_A_assembled": True,
            "top_A_assembled": True,
            "global_size": self.layout.global_size,
            "local_size": self.layout.local_size,
            "modal_count": self.layout.modal_count,
        }
        self._check_layouts()

    def _check_layouts(self) -> None:
        checks = (
            (
                self._bottom_source,
                self.layout.bottom_local_sizes[self.layout.comm.rank],
            ),
            (self._top_source, self.layout.top_local_sizes[self.layout.comm.rank]),
            (
                self._bottom_target,
                self.layout.bottom_local_sizes[self.layout.comm.rank],
            ),
            (self._top_target, self.layout.top_local_sizes[self.layout.comm.rank]),
        )
        for vector, expected in checks:
            if vector.getLocalSize() != expected:
                raise ValueError("Hybrid block ownership does not match layout.")
        if self._bottom_positive_source.getSize() != self.mode_count:
            raise ValueError("Bottom positive traction modal size is incorrect.")
        if self._bottom_negative_source.getSize() != self.mode_count:
            raise ValueError("Bottom negative traction modal size is incorrect.")
        if self._top_positive_source.getSize() != self.mode_count:
            raise ValueError("Top positive traction modal size is incorrect.")
        if self._top_negative_source.getSize() != self.mode_count:
            raise ValueError("Top negative traction modal size is incorrect.")

    def _modal_values(self, source: PETSc.Vec) -> np.ndarray:
        rank = self.layout.comm.rank
        local = (
            np.asarray(
                source.getArray(readonly=True)[self.layout.local_modal_slice]
            ).copy()
            if rank == self.layout.modal_owner
            else None
        )
        return np.asarray(
            self.layout.comm.bcast(local, root=self.layout.modal_owner),
            dtype=np.complex128,
        )

    def _modal_source(self, vector: PETSc.Vec, values: np.ndarray) -> None:
        _set_owned_values(vector, np.asarray(values, dtype=np.complex128))

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        source_values = np.asarray(source.getArray(readonly=True))
        bottom_local = source_values[self.layout.local_bottom_slice]
        top_local = source_values[self.layout.local_top_slice]
        self._bottom_source.getArray()[:] = bottom_local
        self._top_source.getArray()[:] = top_local
        modal = self._modal_values(source)
        mode_count = self.mode_count
        self._modal_source(self._bottom_positive_source, modal[:mode_count])
        self._modal_source(
            self._bottom_negative_source,
            self._backward_factors * modal[mode_count:],
        )
        self._modal_source(
            self._top_positive_source,
            self._forward_factors * modal[:mode_count],
        )
        self._modal_source(self._top_negative_source, modal[mode_count:])
        self.bottom_system.A.mult(self._bottom_source, self._bottom_target)
        self.top_system.A.mult(self._top_source, self._top_target)
        self.coupling.bottom.positive_traction.mult(
            self._bottom_positive_source, self._bottom_positive_target
        )
        self.coupling.bottom.negative_traction.mult(
            self._bottom_negative_source, self._bottom_negative_target
        )
        self.coupling.top.positive_traction.mult(
            self._top_positive_source, self._top_positive_target
        )
        self.coupling.top.negative_traction.mult(
            self._top_negative_source, self._top_negative_target
        )
        self._bottom_target.axpy(1.0, self._bottom_positive_target)
        self._bottom_target.axpy(1.0, self._bottom_negative_target)
        self._top_target.axpy(1.0, self._top_positive_target)
        self._top_target.axpy(1.0, self._top_negative_target)
        self.coupling.bottom.projection.mult(
            self._bottom_source, self._bottom_projection_target
        )
        self.coupling.top.projection.mult(self._top_source, self._top_projection_target)
        modal_result = self.modal_constraint @ modal
        modal_result[:mode_count] += _gather_owned_small(
            self._bottom_projection_target, mode_count
        )
        modal_result[mode_count:] += _gather_owned_small(
            self._top_projection_target, mode_count
        )
        target_local = target.getArray()
        target_local[self.layout.local_bottom_slice] = self._bottom_target.getArray(
            readonly=True
        )
        target_local[self.layout.local_top_slice] = self._top_target.getArray(
            readonly=True
        )
        if self.layout.comm.rank == self.layout.modal_owner:
            target_local[self.layout.local_modal_slice] = modal_result

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        for vector in (
            self._top_projection_target,
            self._bottom_projection_target,
            self._top_negative_target,
            self._top_positive_target,
            self._bottom_negative_target,
            self._bottom_positive_target,
            self._top_negative_source,
            self._top_positive_source,
            self._bottom_negative_source,
            self._bottom_positive_source,
            self._top_target,
            self._bottom_target,
            self._top_source,
            self._bottom_source,
        ):
            vector.destroy()
        self._destroyed = True


def create_hybrid_assembled_block_action(
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
) -> tuple[PETSc.Mat, HybridBlockOperator]:
    """Create the action-only H2a Hybrid operator and its owned context."""

    context = HybridBlockOperator(bottom_system, top_system, coupling)
    matrix = PETSc.Mat().createPython(
        ((context.layout.local_size, context.layout.global_size),) * 2,
        context=context,
        comm=context.layout.comm,
    )
    matrix.setUp()
    return matrix, context
