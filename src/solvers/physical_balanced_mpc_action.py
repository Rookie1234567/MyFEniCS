"""Small owner-local full-space MPC action used by the BAL_H smoother."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import numpy as np
import ufl
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from petsc4py import PETSc


class FullspaceMpcFormAction:
    """Apply one uncondensed form and then the finalized MPC restriction."""

    def __init__(
        self,
        bilinear_form: Any,
        function_space: Any,
        *,
        mpc: Any,
        local_kernel: Any | None = None,
    ) -> None:
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise TypeError("BAL_H requires complex128 PETSc")
        if int(function_space.dofmap.index_map_bs) != 1:
            raise NotImplementedError("BAL_H requires scalar-blocked H(curl) DoFs")
        if mpc.function_space.mesh is not function_space.mesh:
            raise ValueError("MPC and BAL_H action meshes must match")
        if int(mpc.function_space.dofmap.index_map.size_global) != int(
            function_space.dofmap.index_map.size_global
        ):
            raise ValueError("MPC and BAL_H action layouts must match")
        if local_kernel is not None and local_kernel.space is not mpc.function_space:
            raise ValueError("BAL_H local kernel must use the finalized MPC space")

        self._space = mpc.function_space
        self._mpc = mpc
        self._coefficient = fem.Function(self._space)
        self._action_ufl = ufl.action(bilinear_form, self._coefficient)
        self._local_kernel = local_kernel
        self._action_form = None if local_kernel is not None else fem.form(self._action_ufl)
        self._constants = (
            np.ascontiguousarray(
                np.asarray(fem.pack_constants(self._action_form))
            )
            if self._action_form is not None
            else np.empty(0, dtype=np.complex128)
        )

        index_map = self._space.dofmap.index_map
        self._owned_rows = int(index_map.size_local)
        self._global_rows = int(index_map.size_global)
        local_storage = self._owned_rows + int(index_map.num_ghosts)
        if self._coefficient.x.array.size != local_storage:
            raise RuntimeError("BAL_H coefficient storage does not close")
        self._prepare_mpc_metadata(local_storage)
        self._constraint_work = np.empty(
            self._master_indices.size, dtype=np.complex128
        )
        self._owned_slave_work = np.empty(
            self._owned_slave_indices.size, dtype=np.complex128
        )
        self._output_vector = create_vector(
            [(index_map, int(self._space.dofmap.index_map_bs))]
        )
        self._matrix: PETSc.Mat | None = PETSc.Mat().createPython(
            ((self._owned_rows, self._global_rows),) * 2,
            context=self,
            comm=self._space.mesh.comm,
        )
        self._matrix.setUp()
        self._destroyed = False
        self._apply_count = 0
        self._audit = {
            "backend": (
                "FFCx assemble_vector + owner-local C^H"
                if local_kernel is None
                else "IsotropicPartialAssembly positive_sum + owner-local C^H"
            ),
            "local_kernel": None if local_kernel is None else dict(local_kernel.audit),
            "global_matrix_materialized": False,
            "numeric_allgather": False,
            "slave_row_identity": True,
            "factor_count": 0,
            "apply_count": 0,
            "owned_rows": self._owned_rows,
            "global_rows": self._global_rows,
            "local_storage_entries": local_storage,
            "constraint_nnz": int(self._master_indices.size),
        }

    def _prepare_mpc_metadata(self, local_storage: int) -> None:
        slaves = np.asarray(self._mpc.slaves, dtype=np.int32)
        slaves = np.array(np.sort(slaves), dtype=np.int32, copy=True)
        if slaves.size and np.any(slaves < 0) or slaves.size and np.any(
            slaves >= local_storage
        ):
            raise RuntimeError("MPC slave rows exceed local BAL_H storage")
        coefficients, offsets = self._mpc.coefficients()
        coefficients = np.asarray(coefficients, dtype=np.complex128)
        offsets = np.asarray(offsets, dtype=np.int64)
        is_slave = np.asarray(self._mpc.is_slave, dtype=bool)
        row_count = int(offsets.size - 1)
        if row_count < 0 or row_count > local_storage or is_slave.size < row_count:
            raise RuntimeError("MPC row metadata does not close BAL_H storage")
        if slaves.size and np.any(slaves >= row_count):
            raise RuntimeError("MPC slave rows exceed BAL_H coefficient metadata")

        flat_slaves: list[int] = []
        flat_masters: list[int] = []
        flat_coefficients: list[complex] = []
        for slave in slaves.tolist():
            start = int(offsets[slave])
            stop = int(offsets[slave + 1])
            masters = np.asarray(self._mpc.masters.links(slave), dtype=np.int32)
            row_coefficients = coefficients[start:stop]
            if masters.size != row_coefficients.size:
                raise RuntimeError("MPC master/coefficient metadata do not close")
            if masters.size and (
                np.any(masters < 0) or np.any(masters >= local_storage)
            ):
                raise RuntimeError("MPC masters exceed local BAL_H storage")
            known = masters < is_slave.size
            if np.any(is_slave[masters[known]]):
                raise NotImplementedError("chained MPC rows are outside BAL_H")
            flat_slaves.extend([int(slave)] * int(masters.size))
            flat_masters.extend(int(master) for master in masters.tolist())
            flat_coefficients.extend(
                complex(np.conjugate(value)) for value in row_coefficients.tolist()
            )
        self._slave_indices = np.ascontiguousarray(slaves, dtype=np.int32)
        self._owned_slave_indices = np.ascontiguousarray(
            slaves[slaves < self._owned_rows], dtype=np.int32
        )
        self._flat_slave_indices = np.ascontiguousarray(flat_slaves, dtype=np.int32)
        self._master_indices = np.ascontiguousarray(flat_masters, dtype=np.int32)
        self._conjugated_master_coefficients = np.ascontiguousarray(
            flat_coefficients, dtype=np.complex128
        )

    @property
    def matrix(self) -> PETSc.Mat:
        if self._matrix is None:
            raise RuntimeError("BAL_H action has been destroyed")
        return self._matrix

    @property
    def audit(self) -> MappingProxyType:
        self._audit["apply_count"] = int(self._apply_count)
        return MappingProxyType(self._audit)

    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._destroyed:
            raise RuntimeError("BAL_H action has been destroyed")
        source_values = np.asarray(source.getArray(readonly=True))
        if source_values.size != self._owned_rows:
            raise ValueError("BAL_H source has an incompatible owned layout")
        self._coefficient.x.array[: self._owned_rows] = source_values
        self._coefficient.x.scatter_forward()
        self._mpc.homogenize(self._coefficient)
        self._mpc.backsubstitution(self._coefficient)
        self._coefficient.x.scatter_forward()

        with self._output_vector.localForm() as output_local:
            output_local.set(0.0)
            raw = output_local.array_w
            if self._local_kernel is None:
                packed = fem.pack_coefficients(self._action_form)
                fem.assemble_vector(raw, self._action_form, self._constants, packed)
            else:
                self._local_kernel.apply(self._coefficient.x.array, raw)
            np.take(raw, self._flat_slave_indices, out=self._constraint_work)
            np.multiply(
                self._constraint_work,
                self._conjugated_master_coefficients,
                out=self._constraint_work,
            )
            np.add.at(raw, self._master_indices, self._constraint_work)
            raw[self._slave_indices] = 0.0

        self._output_vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        if self._owned_slave_indices.size:
            np.take(
                source_values,
                self._owned_slave_indices,
                out=self._owned_slave_work,
            )
            with self._output_vector.localForm() as output_local:
                output_local.array_w[self._owned_slave_indices] = (
                    self._owned_slave_work
                )
        self._output_vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._apply_count += 1
        return self._output_vector

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self.apply(source).copy(target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        matrix = self._matrix
        self._matrix = None
        self._destroyed = True
        if matrix is not None and _matrix is None:
            matrix.destroy()
        self._output_vector.destroy()
        self._output_vector = None
        self._action_form = None
        self._action_ufl = None
        self._coefficient = None
        self._mpc = None
        self._local_kernel = None
        self._space = None
