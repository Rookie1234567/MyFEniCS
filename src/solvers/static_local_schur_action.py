"""Owner-computes PETSc action for retained cell-local trace Schur blocks."""

import numpy as np
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
)

__all__ = ("create_static_local_schur_action",)


class _LocalSchurActionContext:
    def __init__(
        self,
        condensed: AssemblyTimeCondensedSystem,
        fine_reference: PETSc.Mat,
    ) -> None:
        schurs = condensed.retained_local_schur_by_class
        if schurs is None:
            raise ValueError("local Schur retention is required for this action")
        if tuple(map(int, fine_reference.getSize())) != (
            condensed.active_rows,
            condensed.active_rows,
        ):
            raise ValueError("fine reference must have active-trace size")
        self._schurs = schurs
        raw_cells = []
        union: set[int] = set()
        constraints = condensed.trace_constraints
        for cell in condensed.cell_recovery_maps:
            active_ids, expansion, _ = _cell_trace_expansion(
                cell.trace_original_dofs,
                constraints,
            )
            raw_cells.append((cell.class_key, expansion, active_ids))
            union.update(map(int, active_ids))
        self._union_indices = np.asarray(sorted(union), dtype=PETSc.IntType)
        self._cells = tuple(
            (
                class_key,
                expansion,
                np.asarray(
                    np.searchsorted(self._union_indices, active_ids),
                    dtype=PETSc.IntType,
                ),
            )
            for class_key, expansion, active_ids in raw_cells
        )
        template = fine_reference.createVecRight()
        self._source = PETSc.Vec().createSeq(
            len(self._union_indices), comm=PETSc.COMM_SELF
        )
        self._target = self._source.duplicate()
        global_is = PETSc.IS().createGeneral(self._union_indices, comm=PETSc.COMM_SELF)
        local_is = PETSc.IS().createStride(
            len(self._union_indices), first=0, step=1, comm=PETSc.COMM_SELF
        )
        self._scatter = PETSc.Scatter().create(
            template, global_is, self._source, local_is
        )
        local_is.destroy()
        global_is.destroy()
        template.destroy()
        self._destroyed = False

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        target.set(0.0)
        self._source.set(0.0)
        self._scatter.scatter(
            source,
            self._source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        source_values = self._source.getArray(readonly=True)
        self._target.set(0.0)
        target_values = self._target.getArray()
        for class_key, expansion, positions in self._cells:
            local_trace = expansion.dot(source_values[positions])
            local_action = self._schurs[class_key] @ local_trace
            target_values[positions] += np.asarray(
                expansion.conjugate().transpose().dot(local_action),
                dtype=PETSc.ScalarType,
            )
        self._scatter.scatter(
            self._target,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if not self._destroyed:
            self._scatter.destroy()
            self._target.destroy()
            self._source.destroy()
            self._destroyed = True


def create_static_local_schur_action(
    condensed: AssemblyTimeCondensedSystem,
    fine_reference: PETSc.Mat,
) -> tuple[PETSc.Mat, _LocalSchurActionContext]:
    """Create an active-trace MatPython action from retained local Schur data."""

    context = _LocalSchurActionContext(condensed, fine_reference)
    action = PETSc.Mat().createPython(
        fine_reference.getSizes(),
        context=context,
        comm=fine_reference.getComm(),
    )
    action.setUp()
    return action, context
