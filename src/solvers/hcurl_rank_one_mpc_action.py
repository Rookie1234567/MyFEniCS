"""Direct rank-one full-space action with a finalized H(curl) MPC.

The action assembles the ordinary rank-one residual into one ghosted local
buffer and applies the MPC restriction transpose with flat metadata.  It is
an explicitly opted-in H1R.2 component, not an ordinary solver path.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc
import ufl

__all__ = (
    "HcurlRankOneMpcAction",
    "build_task037_extra_h1r2_mpc_action",
)


class HcurlRankOneMpcAction:
    """Owned coefficient/output action with cached flat MPC metadata."""

    def __init__(self, bilinear_form: Any, mpc: Any) -> None:
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise TypeError("H1R.2 MPC action requires complex128 PETSc")
        if not hasattr(mpc, "function_space"):
            raise TypeError("H1R.2 MPC action requires finalized MPC metadata")
        function_space = mpc.function_space
        dofmap = function_space.dofmap
        if int(dofmap.index_map_bs) != 1:
            raise NotImplementedError("H1R.2 action requires scalar-blocked DoFs")

        self._mpc = mpc
        self._function_space = function_space
        self._coefficient = fem.Function(function_space)
        if np.dtype(self._coefficient.x.array.dtype) != np.dtype(np.complex128):
            raise TypeError("H1R.2 action requires complex128 coefficient storage")
        self._action_ufl = ufl.action(bilinear_form, self._coefficient)
        self._action_form = fem.form(self._action_ufl)
        self._assemble_vector = fem.assemble_vector
        self._pack_coefficients = fem.pack_coefficients
        self._constants = np.ascontiguousarray(
            np.asarray(fem.pack_constants(self._action_form))
        ).copy()

        index_map = dofmap.index_map
        self._owned_rows = int(index_map.size_local)
        self._ghost_rows = int(index_map.num_ghosts)
        self._global_rows = int(index_map.size_global)
        local_storage = self._owned_rows + self._ghost_rows
        if self._coefficient.x.array.size != local_storage:
            raise RuntimeError("MPC coefficient storage does not close")

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
        if offsets.size < local_storage + 1 or is_slave.size < local_storage:
            raise RuntimeError("MPC row metadata does not close local storage")

        flat_slaves: list[int] = []
        flat_masters: list[int] = []
        flat_conjugated_coefficients: list[complex] = []
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
            if np.any(is_slave[masters]):
                raise NotImplementedError("chained MPC rows are unsupported")
            flat_slaves.extend([row] * int(masters.size))
            flat_masters.extend(int(master) for master in masters)
            flat_conjugated_coefficients.extend(
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
            flat_conjugated_coefficients, dtype=np.complex128
        ).copy()
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
            [(index_map, dofmap.index_map_bs)]
        )
        self._destroyed = False
        self._audit: dict[str, Any] = {
            "backend": (
                "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
                " + vectorized MPC R^H"
            ),
            "mpc_enabled": True,
            "apply_count": 0,
            "local_owned_rows": self._owned_rows,
            "local_ghost_rows": self._ghost_rows,
            "local_storage_entries": local_storage,
            "global_rows": self._global_rows,
            "constraint_count": int(slaves.size),
            "owned_constraint_count": int(self._owned_slave_indices.size),
            "constraint_nnz": int(self._master_indices.size),
            "constraint_nnz_closes": bool(
                self._flat_slave_indices.size == self._master_indices.size
                and self._master_indices.size
                == self._conjugated_master_coefficients.size
                and self._master_indices.size == self._constraint_work.size
            ),
            "form_rank": int(len(self._action_ufl.arguments())),
            "coefficient_count": int(self._action_form.ufcx_form.num_coefficients),
            "retained_numeric_payload_components": {},
            "retained_numeric_payload_local_bytes": 0,
            "retained_numeric_payload_global_sum_bytes": 0,
            "retained_numeric_payload_global_max_bytes": 0,
            "last_packed_coefficient_shapes": [],
            "last_packed_coefficient_entry_count": 0,
            "last_packed_coefficient_bytes": 0,
            "per_apply_bounded_temporary_bytes": 0,
            "fresh_packed_arrays_released": True,
            "constraint_work_retained": True,
            "constraint_work_bytes": int(self._constraint_work.nbytes),
            "owned_slave_work_retained": True,
            "owned_slave_work_bytes": int(self._owned_slave_work.nbytes),
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "retained_dense_cell_tensor_count": 0,
            "dense_cell_tensor_materialized_per_apply": False,
            "cell_metadata_retained": False,
            "cell_schur_matrix_nnz": 0,
            "slab_matrix_nnz": 0,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
            "factor_count": 0,
            "ksp_created": False,
            "dtn_used": False,
            "ordinary_default_changed": False,
        }
        components = {
            "coefficient_function_local_array_bytes": int(
                self._coefficient.x.array.nbytes
            ),
            "output_vector_local_storage_bytes": int(
                local_storage * np.dtype(PETSc.ScalarType).itemsize
            ),
            "packed_constants_bytes": int(self._constants.nbytes),
            "slave_indices_bytes": int(self._slave_indices.nbytes),
            "owned_slave_indices_bytes": int(self._owned_slave_indices.nbytes),
            "flat_slave_indices_bytes": int(self._flat_slave_indices.nbytes),
            "master_indices_bytes": int(self._master_indices.nbytes),
            "conjugated_master_coefficients_bytes": int(
                self._conjugated_master_coefficients.nbytes
            ),
            "constraint_work_bytes": int(self._constraint_work.nbytes),
            "owned_slave_work_bytes": int(self._owned_slave_work.nbytes),
        }
        local_payload = int(sum(components.values()))
        comm = function_space.mesh.comm
        self._audit["retained_numeric_payload_components"] = MappingProxyType(
            components
        )
        self._audit["retained_numeric_payload_local_bytes"] = local_payload
        self._audit["retained_numeric_payload_global_sum_bytes"] = int(
            comm.allreduce(local_payload, op=MPI.SUM)
        )
        self._audit["retained_numeric_payload_global_max_bytes"] = int(
            comm.allreduce(local_payload, op=MPI.MAX)
        )

    @property
    def audit(self) -> MappingProxyType:
        return MappingProxyType(self._audit)

    @property
    def output_vector(self) -> PETSc.Vec:
        if self._destroyed:
            raise RuntimeError("H1R.2 MPC action has been destroyed")
        return self._output_vector

    def mult(self, source: PETSc.Vec) -> PETSc.Vec:
        """Apply the direct rank-one form and return the owned output Vec."""

        if self._destroyed:
            raise RuntimeError("H1R.2 MPC action has been destroyed")
        source_values = np.asarray(source.getArray(readonly=True))
        if source_values.size != self._owned_rows:
            raise RuntimeError("MPC action source has an incompatible owned layout")
        coefficient = self._coefficient
        coefficient.x.array[: self._owned_rows] = source_values
        coefficient.x.scatter_forward()
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
            np.take(
                raw,
                self._flat_slave_indices,
                out=self._constraint_work,
            )
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
        np.take(
            source_values,
            self._owned_slave_indices,
            out=self._owned_slave_work,
        )
        with self._output_vector.localForm() as output_local:
            output_local.array_w[self._owned_slave_indices] = self._owned_slave_work
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

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._output_vector.destroy()
        self._output_vector = None
        self._action_form = None
        self._action_ufl = None
        self._coefficient = None
        self._constants = None
        self._destroyed = True


def build_task037_extra_h1r2_mpc_action(
    bilinear_form: Any,
    mpc: Any,
    *,
    task037_extra_h1r2: bool = False,
) -> HcurlRankOneMpcAction:
    """Build the explicitly opted-in H1R.2 MPC rank-one action."""

    if not bool(task037_extra_h1r2):
        raise ValueError("H1R.2 MPC action requires explicit opt-in")
    return HcurlRankOneMpcAction(bilinear_form, mpc)
