"""Direct rank-one UFL action for a local H(curl) diagnostic.

This wrapper owns one coefficient Function and one NumPy output buffer.  Each
action repacks the current coefficient and calls the direct DOLFINx ndarray
linear-form assembly overload; it never creates a matrix or a dense cell
tensor.  The implementation is intentionally a single-cell H1R diagnostic,
not an MPI/MPC production operator.
"""

from __future__ import annotations

from types import MappingProxyType
import time
from typing import Any

import numpy as np

__all__ = ("HcurlRankOneFormAction",)


class HcurlRankOneFormAction:
    """Owned rank-one form action with bounded local numeric storage."""

    def __init__(self, bilinear_form: Any, function_space: Any) -> None:
        from dolfinx import fem
        import ufl

        started = time.perf_counter()
        self._function_space = function_space
        self._coefficient = fem.Function(function_space)
        if np.dtype(self._coefficient.x.array.dtype) != np.dtype(np.complex128):
            raise TypeError("rank-one action requires complex128 coefficients")
        self._action_ufl = ufl.action(bilinear_form, self._coefficient)
        self._action_form = fem.form(self._action_ufl)
        self._assemble_vector = fem.assemble_vector
        self._pack_coefficients = fem.pack_coefficients
        self._constants = np.asarray(fem.pack_constants(self._action_form))
        self._output = np.zeros_like(
            self._coefficient.x.array,
            dtype=np.complex128,
        )
        self._destroyed = False

        index_map = function_space.dofmap.index_map
        block_size = int(function_space.dofmap.index_map_bs)
        form_rank = int(len(self._action_ufl.arguments()))
        coefficient_count = int(self._action_form.ufcx_form.num_coefficients)
        local_owned_rows = int(index_map.size_local * block_size)
        local_ghost_rows = int(index_map.num_ghosts * block_size)
        local_storage_entries = int(self._output.size)
        if local_storage_entries != local_owned_rows + local_ghost_rows:
            raise RuntimeError("rank-one local storage does not close")
        global_rows = int(index_map.size_global * block_size)
        components = {
            "coefficient_function_local_array_bytes": int(
                self._coefficient.x.array.nbytes
            ),
            "output_buffer_bytes": int(self._output.nbytes),
            "packed_constants_bytes": int(self._constants.nbytes),
        }
        total_bytes = int(sum(components.values()))
        self._audit: dict[str, Any] = {
            "backend": "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)",
            "form_rank": form_rank,
            "coefficient_count": coefficient_count,
            "kernel_output_local_rows": local_storage_entries,
            "kernel_output_local_rows_semantics": "local_storage_entries",
            "kernel_output_shape": [local_storage_entries],
            "local_owned_rows": local_owned_rows,
            "local_ghost_rows": local_ghost_rows,
            "local_storage_entries": local_storage_entries,
            "global_rows": global_rows,
            "global_matrix_materialized": False,
            "dense_cell_tensor_materialized_per_apply": False,
            "retained_dense_cell_tensor_count": 0,
            "cell_tensor_scratch_count": 0,
            "apply_count": 0,
            "retained_numeric_payload_components": components,
            "retained_numeric_payload_total_bytes": total_bytes,
            "retained_payload_per_exact_class_bytes": total_bytes,
            "last_packed_coefficient_shapes": [],
            "last_packed_coefficient_entry_count": 0,
            "last_packed_coefficient_bytes": 0,
            "per_apply_packed_coefficient_temporary": True,
            "per_apply_bounded_temporary": (
                "packed coefficient arrays are rebuilt per apply and released "
                "after direct ndarray assembly"
            ),
            "python_object_headers_excluded": True,
            "borrowed_mesh_form_excluded": True,
            "ordinary_default_changed": False,
            "setup_seconds": float(time.perf_counter() - started),
        }

    @property
    def audit(self) -> MappingProxyType:
        return MappingProxyType(self._audit)

    @property
    def output(self) -> np.ndarray:
        if self._destroyed or self._output is None:
            raise RuntimeError("rank-one action has been destroyed")
        return self._output

    def apply(self, values: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("rank-one action has been destroyed")
        values = np.asarray(values)
        if values.shape != self._coefficient.x.array.shape:
            raise ValueError("rank-one action input has incompatible local shape")
        if values.dtype != np.dtype(np.complex128):
            raise TypeError("rank-one action input requires complex128 values")
        self._coefficient.x.array[...] = values
        self._coefficient.x.scatter_forward()
        self._output.fill(0.0)
        packed_coefficients = self._pack_coefficients(self._action_form)
        packed_arrays = [
            np.asarray(array) for array in packed_coefficients.values()
        ]
        packed_shapes = [list(array.shape) for array in packed_arrays]
        packed_entry_count = int(sum(array.size for array in packed_arrays))
        packed_bytes = int(
            sum(array.nbytes for array in packed_arrays)
        )
        self._assemble_vector(
            self._output,
            self._action_form,
            self._constants,
            packed_coefficients,
        )
        self._audit["apply_count"] = int(self._audit["apply_count"]) + 1
        self._audit["last_packed_coefficient_shapes"] = packed_shapes
        self._audit["last_packed_coefficient_entry_count"] = (
            packed_entry_count
        )
        self._audit["last_packed_coefficient_bytes"] = packed_bytes
        self._audit["per_apply_bounded_temporary_bytes"] = packed_bytes
        del packed_coefficients
        return self._output

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._action_form = None
        self._action_ufl = None
        self._coefficient = None
        self._constants = None
        self._output = None
        self._destroyed = True
