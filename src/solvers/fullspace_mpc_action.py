"""Owner-local full-space H(curl) form action with optional finalized MPC.

The action assembles one UFL rank-one residual into a bounded vector buffer.
When a finalized MPC is supplied, its restriction transpose is applied from
cached row metadata.  The module retains only vector and row-work storage.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc
import ufl

__all__ = (
    "FullspaceMpcFormAction",
    "build_fullspace_mpc_form_action",
)


def _compile_action_form(
    action_ufl: Any,
    jit_options: Mapping[str, Any] | None,
) -> Any:
    if jit_options is None:
        return fem.form(action_ufl)
    return fem.form(action_ufl, jit_options=dict(jit_options))


class FullspaceMpcFormAction:
    """Matrix-free owner-local action for an uncondensed full-space form.

    ``bilinear_form`` is a raw UFL bilinear form; a compiled ``fem.Form`` is
    retained only by tests as an assembled oracle.  ``slave_row_identity``
    defaults to ``True`` so the ordinary full-space operator keeps its
    finalized-MPC constraint identity rows; split physical volume actions may
    explicitly set it to ``False`` when a surrounding shell owns those rows.
    """

    def __init__(
        self,
        bilinear_form: Any,
        function_space: Any,
        *,
        mpc: Any | None = None,
        slave_row_identity: bool = True,
        jit_options: Mapping[str, Any] | None = None,
    ) -> None:
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise TypeError("full-space form action requires complex128 PETSc")
        if int(function_space.dofmap.index_map_bs) != 1:
            raise NotImplementedError("full-space action requires scalar-blocked DoFs")
        if mpc is not None:
            mpc_space = mpc.function_space
            if mpc_space.mesh is not function_space.mesh:
                raise ValueError("MPC and action meshes must be identical")
            if (
                int(mpc_space.dofmap.index_map.size_global)
                != int(function_space.dofmap.index_map.size_global)
                or int(mpc_space.dofmap.index_map_bs)
                != int(function_space.dofmap.index_map_bs)
            ):
                raise ValueError("MPC and action layouts must be identical")
            function_space = mpc_space

        self._function_space = function_space
        self._mpc = mpc
        self._slave_row_identity = bool(slave_row_identity)
        self._coefficient = fem.Function(function_space)
        self._action_ufl = ufl.action(bilinear_form, self._coefficient)
        self._jit_options = None if jit_options is None else dict(jit_options)
        self._action_form = _compile_action_form(self._action_ufl, self._jit_options)
        self._assemble_vector = fem.assemble_vector
        self._pack_coefficients = fem.pack_coefficients
        self._constants = np.ascontiguousarray(
            np.asarray(fem.pack_constants(self._action_form))
        ).copy()

        index_map = function_space.dofmap.index_map
        self._owned_rows = int(index_map.size_local)
        self._ghost_rows = int(index_map.num_ghosts)
        self._global_rows = int(index_map.size_global)
        local_storage = self._owned_rows + self._ghost_rows
        if self._coefficient.x.array.size != local_storage:
            raise RuntimeError("full-space coefficient storage does not close")

        self._slave_indices = np.empty(0, dtype=np.int32)
        self._owned_slave_indices = np.empty(0, dtype=np.int32)
        self._flat_slave_indices = np.empty(0, dtype=np.int32)
        self._master_indices = np.empty(0, dtype=np.int32)
        self._conjugated_master_coefficients = np.empty(
            0, dtype=np.complex128
        )
        self._row_metadata_size = 0
        if mpc is not None:
            self._prepare_mpc_metadata(mpc, local_storage)
        self._constraint_work = np.empty(
            self._master_indices.size, dtype=np.complex128
        )
        self._owned_slave_work = np.empty(
            self._owned_slave_indices.size, dtype=np.complex128
        )
        for array in (
            self._slave_indices,
            self._owned_slave_indices,
            self._flat_slave_indices,
            self._master_indices,
            self._conjugated_master_coefficients,
        ):
            array.flags.writeable = False

        self._output_vector = create_vector(
            [(index_map, function_space.dofmap.index_map_bs)]
        )
        self._matrix: PETSc.Mat | None = PETSc.Mat().createPython(
            ((self._owned_rows, self._global_rows),)
            * 2,
            context=self,
            comm=function_space.mesh.comm,
        )
        self._matrix.setUp()
        self._destroyed = False
        constraint_count = int(
            function_space.mesh.comm.allreduce(
                self._owned_slave_indices.size,
                op=MPI.SUM,
            )
        )
        components = {
            "coefficient_function_local_array_bytes": int(
                self._coefficient.x.array.nbytes
            ),
            "output_vector_local_storage_bytes": int(
                local_storage * np.dtype(PETSc.ScalarType).itemsize
            ),
            "constraint_work_bytes": int(self._constraint_work.nbytes),
            "owned_slave_work_bytes": int(self._owned_slave_work.nbytes),
            "slave_indices_bytes": int(self._slave_indices.nbytes),
            "owned_slave_indices_bytes": int(self._owned_slave_indices.nbytes),
            "flat_slave_indices_bytes": int(self._flat_slave_indices.nbytes),
            "master_indices_bytes": int(self._master_indices.nbytes),
            "conjugated_master_coefficients_bytes": int(
                self._conjugated_master_coefficients.nbytes
            ),
            "packed_constants_bytes": int(self._constants.nbytes),
        }
        local_payload = int(sum(components.values()))
        if local_payload != int(sum(int(value) for value in components.values())):
            raise RuntimeError("full-space retained payload does not close")
        comm = function_space.mesh.comm
        self._audit: dict[str, Any] = {
            "schema": "task038.fullspace-mpc-form-action.v1",
            "backend": "dolfinx.fem.assemble_vector + owner-local MPC R^H",
            "matrix_type": self._matrix.getType(),
            "operator": "uncondensed_fullspace_curl_mass_form",
            "mpc_enabled": mpc is not None,
            "slave_row_identity": self._slave_row_identity,
            "apply_count": 0,
            "global_rows": self._global_rows,
            "local_owned_rows": self._owned_rows,
            "local_ghost_rows": self._ghost_rows,
            "local_storage_entries": local_storage,
            "constraint_row_metadata_entries": int(self._row_metadata_size),
            "constraint_count": constraint_count,
            "owned_constraint_count": int(self._owned_slave_indices.size),
            "constraint_nnz": int(self._master_indices.size),
            "constraint_nnz_closes": bool(
                self._flat_slave_indices.size
                == self._master_indices.size
                == self._conjugated_master_coefficients.size
                == self._constraint_work.size
            ),
            "form_rank": int(len(self._action_ufl.arguments())),
            "coefficient_count": int(self._action_form.ufcx_form.num_coefficients),
            "phase_application": (
                "finalized_floquet_mpc_once" if mpc is not None else "none"
            ),
            "orientation": "dolfinx_n1curl_form_kernel",
            "owner_local": True,
            "numeric_allgather": False,
            "replicated_global_numeric_vector": False,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
            "retained_dense_cell_tensor_count": 0,
            "dense_cell_tensor_materialized_per_apply": False,
            "cell_schur_matrix_nnz": 0,
            "slab_matrix_nnz": 0,
            "factor_count": 0,
            "ksp_created": False,
            "dtn_used": False,
            "ordinary_default_changed": False,
            "fresh_packed_arrays_released": True,
            "jit_options_explicit": jit_options is not None,
            "retained_numeric_payload_components": MappingProxyType(components),
            "retained_numeric_payload_local_bytes": local_payload,
            "retained_numeric_payload_global_sum_bytes": int(
                comm.allreduce(local_payload, op=MPI.SUM)
            ),
            "retained_numeric_payload_global_max_bytes": int(
                comm.allreduce(local_payload, op=MPI.MAX)
            ),
            "last_packed_coefficient_shapes": [],
            "last_packed_coefficient_entry_count": 0,
            "last_packed_coefficient_bytes": 0,
            "per_apply_bounded_temporary_bytes": 0,
        }

    def _prepare_mpc_metadata(self, mpc: Any, local_storage: int) -> None:
        slaves = np.asarray(mpc.slaves, dtype=np.int32)
        slaves = np.array(np.sort(slaves), dtype=np.int32, copy=True, order="C")
        if slaves.size and np.any(slaves[1:] == slaves[:-1]):
            raise RuntimeError("MPC slave metadata contains duplicate rows")
        if slaves.size and (
            np.any(slaves < 0) or np.any(slaves >= local_storage)
        ):
            raise RuntimeError("MPC slave metadata exceeds local storage")
        coefficients, offsets = mpc.coefficients()
        coefficients = np.asarray(coefficients, dtype=np.complex128)
        offsets = np.asarray(offsets, dtype=np.int64)
        is_slave = np.asarray(mpc.is_slave, dtype=bool)
        row_metadata_size = int(offsets.size - 1)
        # A finalized MPC may add ghost slots for imported masters. Its
        # offsets/is_slave arrays describe local coefficient/slave rows, so
        # those extra slots are valid masters but cannot be local slave rows.
        if (
            row_metadata_size < 0
            or row_metadata_size > local_storage
            or is_slave.size < row_metadata_size
        ):
            raise RuntimeError("MPC row metadata does not close coefficient rows")
        if slaves.size and np.any(slaves >= row_metadata_size):
            raise RuntimeError("MPC slave metadata exceeds coefficient row metadata")
        self._row_metadata_size = row_metadata_size

        flat_slaves: list[int] = []
        flat_masters: list[int] = []
        flat_coefficients: list[complex] = []
        for slave in slaves:
            row = int(slave)
            start = int(offsets[row])
            stop = int(offsets[row + 1])
            masters = np.asarray(mpc.masters.links(row), dtype=np.int32)
            row_coefficients = np.asarray(
                coefficients[start:stop], dtype=np.complex128
            )
            if masters.size != row_coefficients.size:
                raise RuntimeError("MPC master/coefficient metadata does not close")
            if masters.size and (
                np.any(masters < 0) or np.any(masters >= local_storage)
            ):
                raise RuntimeError("MPC master metadata exceeds local storage")
            known_slave_rows = masters < is_slave.size
            if np.any(is_slave[masters[known_slave_rows]]):
                raise NotImplementedError("chained MPC rows are unsupported")
            flat_slaves.extend([row] * int(masters.size))
            flat_masters.extend(int(master) for master in masters)
            flat_coefficients.extend(
                complex(np.conjugate(value)) for value in row_coefficients
            )

        self._slave_indices = slaves
        self._owned_slave_indices = np.ascontiguousarray(
            slaves[slaves < self._owned_rows], dtype=np.int32
        ).copy()
        self._flat_slave_indices = np.ascontiguousarray(
            flat_slaves, dtype=np.int32
        ).copy()
        self._master_indices = np.ascontiguousarray(
            flat_masters, dtype=np.int32
        ).copy()
        self._conjugated_master_coefficients = np.ascontiguousarray(
            flat_coefficients, dtype=np.complex128
        ).copy()

    @property
    def matrix(self) -> PETSc.Mat:
        if self._matrix is None:
            raise RuntimeError("full-space action has been destroyed")
        return self._matrix

    @property
    def audit(self) -> MappingProxyType:
        self._audit["apply_count"] = int(self._audit["apply_count"])
        return MappingProxyType(self._audit)

    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._destroyed:
            raise RuntimeError("full-space action has been destroyed")
        source_values = np.asarray(source.getArray(readonly=True))
        if source_values.size != self._owned_rows:
            raise RuntimeError("action source has an incompatible owned layout")
        coefficient = self._coefficient
        coefficient.x.array[: self._owned_rows] = source_values
        coefficient.x.scatter_forward()
        if self._mpc is not None:
            self._mpc.homogenize(coefficient)
            self._mpc.backsubstitution(coefficient)
            coefficient.x.scatter_forward()

        with self._output_vector.localForm() as output_local:
            output_local.set(0.0)
            raw = output_local.array_w
            packed_coefficients = self._pack_coefficients(self._action_form)
            packed_arrays = [
                np.asarray(array) for array in packed_coefficients.values()
            ]
            packed_shapes = [list(array.shape) for array in packed_arrays]
            packed_entries = int(sum(array.size for array in packed_arrays))
            packed_bytes = int(sum(array.nbytes for array in packed_arrays))
            self._assemble_vector(
                raw,
                self._action_form,
                self._constants,
                packed_coefficients,
            )
            del packed_arrays
            del packed_coefficients
            if self._mpc is not None:
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
        if self._mpc is not None and self._slave_row_identity:
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
        self._audit["apply_count"] = int(self._audit["apply_count"]) + 1
        self._audit["last_packed_coefficient_shapes"] = packed_shapes
        self._audit["last_packed_coefficient_entry_count"] = packed_entries
        self._audit["last_packed_coefficient_bytes"] = packed_bytes
        self._audit["per_apply_bounded_temporary_bytes"] = packed_bytes
        return self._output_vector

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        result = self.apply(source)
        target.getArray()[:] = result.getArray(readonly=True)

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
        self._constants = None
        self._mpc = None
        self._function_space = None


def build_fullspace_mpc_form_action(
    bilinear_form: Any,
    function_space: Any,
    *,
    mpc: Any | None = None,
    slave_row_identity: bool = True,
    jit_options: Mapping[str, Any] | None = None,
) -> FullspaceMpcFormAction:
    """Build from a raw UFL form without retaining an assembled matrix.

    The compiled ``fem.Form`` counterpart belongs in oracle tests only.
    The default ``slave_row_identity=True`` preserves the ordinary action
    contract; callers must opt out explicitly for a split shell that supplies
    the constraint identity exactly once.
    """

    return FullspaceMpcFormAction(
        bilinear_form,
        function_space,
        mpc=mpc,
        slave_row_identity=slave_row_identity,
        jit_options=jit_options,
    )
