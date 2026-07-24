from __future__ import annotations

from typing import Any

import dolfinx_mpc
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from dolfinx.la.petsc import create_vector
import numpy as np
import ufl
from petsc4py import PETSc


class MpcFormActionContext:
    """Public-API MPC action for a bilinear form without a retained matrix."""

    def __init__(
        self,
        bilinear_form: Any,
        mpc: Any,
        reference: PETSc.Mat | None = None,
    ) -> None:
        self.mpc = mpc
        self.field = fem.Function(mpc.function_space)
        self.action_form = fem.form(ufl.action(bilinear_form, self.field))
        index_map = mpc.function_space.dofmap.index_map
        block_size = mpc.function_space.dofmap.index_map_bs
        self.input_vector = create_vector([(index_map, block_size)])
        self.action_vector = dolfinx_mpc.assemble_vector(self.action_form, mpc)
        if (
            reference is not None
            and reference.getSize()[0] != self.input_vector.getSize()
        ):
            raise ValueError(
                "MPC form-action vector size differs from assembled matrix"
            )
        owned_size = int(index_map.size_local * block_size)
        slaves = np.asarray(mpc.slaves, dtype=PETSc.IntType)
        self.owned_slaves = slaves[(slaves >= 0) & (slaves < owned_size)]
        self.apply_count = 0
        self.destroyed = False

    def mult(self, _mat: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("MPC form-action context has been destroyed")
        self.input_vector.getArray()[:] = x.getArray(readonly=True)
        self.input_vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        fem_petsc.assign(self.input_vector, self.field)
        self.mpc.homogenize(self.field)
        self.mpc.backsubstitution(self.field)
        dolfinx_mpc.assemble_vector(
            self.action_form, self.mpc, b=self.action_vector
        )
        self.action_vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self.action_vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        y.getArray()[:] = self.action_vector.getArray(readonly=True)
        y.getArray()[self.owned_slaves] = x.getArray(readonly=True)[self.owned_slaves]
        self.apply_count += 1

    def destroy(self, _mat: PETSc.Mat | None = None) -> None:
        if self.destroyed:
            return
        self.action_vector.destroy()
        self.input_vector.destroy()
        self.destroyed = True


def create_mpc_form_operator(
    bilinear_form: Any,
    mpc: Any,
    reference: PETSc.Mat,
) -> tuple[PETSc.Mat, MpcFormActionContext]:
    context = MpcFormActionContext(bilinear_form, mpc, reference)
    matrix = PETSc.Mat().createPython(
        reference.getSizes(), context=context, comm=reference.getComm()
    )
    matrix.setUp()
    return matrix, context
