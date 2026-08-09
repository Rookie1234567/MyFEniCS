"""Candidate-H full-space element-local H(curl) matrix-free action.

This deliberately narrow factory is an opt-in component probe for an
uncondensed complex p-order N1curl space on affine hexahedra.  It reuses the
qualified FFCx cell kernels and DOLFINx/Basix orientation convention from the
assembly-time path, but keeps only one temporary cell tensor while applying
the operator.  No global AIJ, cell matrix cache, smoother, or transfer is
constructed.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx.la.petsc import create_vector
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _orient_cell_tensor,
)

__all__ = (
    "FullSpaceMatrixFreeHcurlAction",
    "build_task037_extra_candidate_h_fullspace_action",
)


class FullSpaceMatrixFreeHcurlAction:
    """Owned MatPython action with borrowed mesh, space, and compiled form."""

    def __init__(
        self,
        compiled_form: Any,
        function_space: Any,
        cell_tags: Any,
        *,
        mpc: Any | None = None,
        geometry_tolerance: float,
    ) -> None:
        if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
            raise TypeError("Candidate H action requires complex128 FFCx form")
        mesh = function_space.mesh
        if "hexahedron" not in str(mesh.basix_cell()).lower():
            raise NotImplementedError("Candidate H action supports hexahedra only")
        if int(function_space.dofmap.index_map_bs) != 1:
            raise NotImplementedError(
                "Candidate H action requires scalar-blocked N1curl DoFs"
            )
        element = function_space.element
        family = str(
            getattr(element.basix_element.family, "name", element.basix_element.family)
        ).lower()
        if family not in {"n1curl", "n1e"}:
            raise NotImplementedError("Candidate H action requires N1curl")
        tolerance = float(geometry_tolerance)
        if not np.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("geometry_tolerance must be finite and positive")

        self._compiled_form = compiled_form
        self._function_space = function_space
        self._mpc = mpc
        self._element = element
        self._dofmap = function_space.dofmap
        self._kernels = _cell_integral_kernels(compiled_form)
        tdim = mesh.topology.dim
        owned_cells = int(mesh.topology.index_map(tdim).size_local)
        tags = _cell_tag_array(cell_tags, owned_cells)
        unknown_tags = (
            []
            if -1 in self._kernels
            else sorted(set(map(int, tags)) - set(self._kernels))
        )
        if unknown_tags:
            raise ValueError(
                f"compiled form has no cell integral for tags {unknown_tags}"
            )

        dimension = int(element.space_dimension)
        mesh.topology.create_entity_permutations()
        cell_infos = np.asarray(
            mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        if len(cell_infos) < owned_cells:
            raise RuntimeError("cell permutation info is shorter than owned cells")
        local_dofs = []
        coordinates = []
        info_arrays = []
        for cell in range(owned_cells):
            local_dofs.append(
                np.asarray(self._dofmap.cell_dofs(cell), dtype=np.int32)
            )
            canonical, _widths = _canonical_axis_aligned_coordinates(
                mesh,
                cell,
                tolerance=tolerance,
            )
            coordinate = np.ascontiguousarray(canonical, dtype=np.float64)
            coordinate.flags.writeable = False
            coordinates.append(coordinate)
            info = np.asarray([cell_infos[cell]], dtype=np.uint32)
            info.flags.writeable = False
            info_arrays.append(info)
        self._cell_local_dofs = tuple(local_dofs)
        self._cell_coordinates = tuple(coordinates)
        self._cell_infos = tuple(info_arrays)
        self._cell_tags = tuple(int(tag) for tag in tags)
        self._cell_tensor = np.empty((dimension, dimension), dtype=np.complex128)
        if mpc is None:
            vector_dofmap = self._dofmap
            self._mpc_owned_size = 0
            self._mpc_slave_indices = np.empty(0, dtype=np.int32)
            self._mpc_owned_slave_indices = np.empty(0, dtype=np.int32)
            self._mpc_slave_offsets = np.zeros(1, dtype=np.int32)
            self._mpc_slave_masters = np.empty(0, dtype=np.int32)
            self._mpc_slave_coefficients = np.empty(0, dtype=np.complex128)
            self._mpc_cell_slave_positions = tuple()
        else:
            vector_dofmap = mpc.function_space.dofmap
            if int(vector_dofmap.index_map_bs) != 1:
                raise NotImplementedError("MPC space must be scalar-blocked")
            original_index_map = self._dofmap.index_map
            extended_index_map = vector_dofmap.index_map
            if int(extended_index_map.size_local) != int(original_index_map.size_local):
                raise RuntimeError("MPC extended layout changed owned rows")
            if int(extended_index_map.size_global) != int(original_index_map.size_global):
                raise RuntimeError("MPC extended layout changed global rows")
            extended_local_size = int(extended_index_map.size_local + extended_index_map.num_ghosts)
            owned_size = int(extended_index_map.size_local)
            slaves = np.asarray(mpc.slaves, dtype=np.int32)
            if np.any(slaves < 0) or np.any(slaves >= extended_local_size):
                raise RuntimeError("MPC slave index is outside extended layout")
            coefficients, offsets = mpc.coefficients()
            coefficients = np.asarray(coefficients, dtype=np.complex128)
            offsets = np.asarray(offsets, dtype=np.int32)
            if offsets.size < extended_local_size + 1:
                raise RuntimeError("MPC coefficient offsets lack extended rows")
            is_slave = np.asarray(mpc.is_slave, dtype=bool)
            if is_slave.size < extended_local_size:
                raise RuntimeError("MPC slave mask lacks extended rows")
            row_data: dict[int, tuple[np.ndarray, np.ndarray]] = {}
            for slave in slaves:
                row = int(slave)
                start = int(offsets[row])
                stop = int(offsets[row + 1])
                masters = np.asarray(mpc.masters.links(row), dtype=np.int32)
                row_coefficients = np.ascontiguousarray(
                    coefficients[start:stop], dtype=np.complex128
                )
                if masters.size != row_coefficients.size:
                    raise RuntimeError("MPC master and coefficient counts differ")
                if np.any(masters < 0) or np.any(masters >= extended_local_size):
                    raise RuntimeError("MPC master index is outside extended layout")
                if np.any(is_slave[masters]):
                    raise RuntimeError("chained MPC slave master is unsupported")
                masters = np.ascontiguousarray(masters, dtype=np.int32)
                masters.flags.writeable = False
                row_coefficients.flags.writeable = False
                row_data[row] = (masters, row_coefficients)
            slave_offsets = np.zeros(extended_local_size + 1, dtype=np.int32)
            flat_masters: list[int] = []
            flat_coefficients: list[complex] = []
            for row in range(extended_local_size):
                data = row_data.get(row)
                if data is not None:
                    masters, row_coefficients = data
                    flat_masters.extend(int(value) for value in masters)
                    flat_coefficients.extend(complex(value) for value in row_coefficients)
                slave_offsets[row + 1] = len(flat_masters)
            slave_indices = np.ascontiguousarray(slaves, dtype=np.int32)
            owned_slave_indices = slave_indices[slave_indices < owned_size].copy()
            slave_masters = np.ascontiguousarray(flat_masters, dtype=np.int32)
            slave_coefficients = np.ascontiguousarray(
                flat_coefficients, dtype=np.complex128
            )
            for array in (
                slave_indices,
                owned_slave_indices,
                slave_offsets,
                slave_masters,
                slave_coefficients,
            ):
                array.flags.writeable = False
            cell_slave_positions = []
            cell_slave_position_sets = []
            cell_to_slaves = mpc.cell_to_slaves
            for cell, local_dofs in enumerate(self._cell_local_dofs):
                expected_slaves = {
                    int(dof)
                    for dof in local_dofs
                    if bool(is_slave[int(dof)])
                }
                listed_slaves = {
                    int(slave)
                    for slave in np.asarray(
                        cell_to_slaves.links(cell), dtype=np.int32
                    )
                }
                if listed_slaves != expected_slaves:
                    raise RuntimeError("cell slave metadata does not close")
                positions = []
                for slave in np.asarray(cell_to_slaves.links(cell), dtype=np.int32):
                    matches = np.flatnonzero(local_dofs == int(slave))
                    if matches.size != 1:
                        raise RuntimeError("cell slave metadata is missing or ambiguous")
                    positions.append((int(matches[0]), int(slave)))
                positions.sort()
                position_set = frozenset(position for position, _slave in positions)
                cell_slave_positions.append(tuple(positions))
                cell_slave_position_sets.append(position_set)
            self._mpc_owned_size = owned_size
            self._mpc_slave_indices = slave_indices
            self._mpc_owned_slave_indices = owned_slave_indices
            self._mpc_slave_offsets = slave_offsets
            self._mpc_slave_masters = slave_masters
            self._mpc_slave_coefficients = slave_coefficients
            self._mpc_cell_slave_positions = tuple(
                zip(cell_slave_positions, cell_slave_position_sets)
            )
        self._input_vector = create_vector(
            [(vector_dofmap.index_map, vector_dofmap.index_map_bs)]
        )
        self._output_vector = self._input_vector.duplicate()
        index_map = vector_dofmap.index_map
        local_rows = int(index_map.size_local)
        global_rows = int(index_map.size_global)
        self._matrix: PETSc.Mat | None = PETSc.Mat().createPython(
            ((local_rows, global_rows), (local_rows, global_rows)),
            context=self,
            comm=mesh.comm,
        )
        self._matrix.setUp()
        self._destroyed = False
        self.audit: Mapping[str, Any] = MappingProxyType(
            {
                "task037_extra_candidate_h": True,
                "operator": "fullspace_element_local_curl_plus_mass",
                "degree": int(element.basix_element.degree),
                "global_rows": global_rows,
                "local_owned_rows": local_rows,
                "local_cell_count": owned_cells,
                "cell_dof_count": dimension,
                "material_tags": tuple(sorted(set(self._cell_tags))),
                "kernel_ids": tuple(sorted(int(key) for key in self._kernels)),
                "orientation": "dolfinx_element_T_apply",
                "ghost_forward": True,
                "reverse_scatter": True,
                "global_matrix_materialized": False,
                "global_A_materialized": False,
                "retained_cell_dense_matrix_count": 0,
                "cell_tensor_scratch_count": 1,
                "cell_tensor_scratch_bytes": int(self._cell_tensor.nbytes),
                "cell_tensor_scratch_reused": True,
                "slab_matrix_nnz": 0,
                "slab_factor_count": 0,
                "factor_count": 0,
                "ordinary_default_changed": False,
                "mpc_enabled": mpc is not None,
                "mpc_local_slave_count": int(self._mpc_slave_indices.size),
                "mpc_owned_slave_count": int(self._mpc_owned_slave_indices.size),
                "mpc_constraint_nnz": int(self._mpc_slave_masters.size),
                "mpc_metadata_cached": mpc is not None,
                "mpc_per_apply_collective": False,
                "global_constraint_matrix_materialized": False,
            }
        )

    @property
    def matrix(self) -> PETSc.Mat:
        if self._matrix is None:
            raise RuntimeError("Candidate H action has been destroyed")
        return self._matrix

    def _tabulate_cell_tensor(self, cell: int) -> None:
        tensor = self._cell_tensor
        tensor.fill(0.0)
        ffi = self._compiled_form.module.ffi
        coordinates = self._cell_coordinates[cell]
        for kernel_id in (-1, self._cell_tags[cell]):
            kernel = self._kernels.get(kernel_id)
            if kernel is None:
                continue
            kernel(
                ffi.cast("double _Complex *", ffi.from_buffer(tensor)),
                ffi.NULL,
                ffi.NULL,
                ffi.cast("double *", ffi.from_buffer(coordinates)),
                ffi.NULL,
                ffi.NULL,
                ffi.NULL,
            )
        _orient_cell_tensor(self._element, tensor, self._cell_infos[cell])

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self._destroyed:
            raise RuntimeError("Candidate H action has been destroyed")
        if self._mpc is not None:
            self._mult_mpc(source, target)
            return
        self._input_vector.getArray()[:] = source.getArray(readonly=True)
        self._input_vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._output_vector.set(0.0)
        input_values = self._input_vector.getArray(readonly=True)
        output_values = self._output_vector.getArray()
        for cell, local_dofs in enumerate(self._cell_local_dofs):
            self._tabulate_cell_tensor(cell)
            local_input = input_values[local_dofs]
            output_values[local_dofs] += self._cell_tensor @ local_input
        self._output_vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self._output_vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        target.getArray()[:] = self._output_vector.getArray(readonly=True)

    def _mult_mpc(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        owned_size = self._mpc_owned_size
        source_values = np.asarray(source.getArray(readonly=True))
        if source_values.size != owned_size:
            raise RuntimeError("MPC action source has an incompatible owned layout")
        with self._input_vector.localForm() as input_local:
            input_local.set(0.0)
            input_local.array_w[:owned_size] = source_values
        self._input_vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        with self._input_vector.localForm() as input_local:
            input_values = input_local.array_w
            for slave in self._mpc_slave_indices:
                row = int(slave)
                start = int(self._mpc_slave_offsets[row])
                stop = int(self._mpc_slave_offsets[row + 1])
                masters = self._mpc_slave_masters[start:stop]
                coefficients = self._mpc_slave_coefficients[start:stop]
                input_values[row] = np.dot(coefficients, input_values[masters])
            with self._output_vector.localForm() as output_local:
                output_local.set(0.0)
                output_values = output_local.array_w
                for cell, local_dofs in enumerate(self._cell_local_dofs):
                    self._tabulate_cell_tensor(cell)
                    local_result = self._cell_tensor @ input_values[local_dofs]
                    slave_positions, slave_position_set = self._mpc_cell_slave_positions[cell]
                    for position, slave in slave_positions:
                        start = int(self._mpc_slave_offsets[slave])
                        stop = int(self._mpc_slave_offsets[slave + 1])
                        masters = self._mpc_slave_masters[start:stop]
                        coefficients = self._mpc_slave_coefficients[start:stop]
                        output_values[masters] += np.conjugate(coefficients) * local_result[position]
                    for position, dof in enumerate(local_dofs):
                        if position not in slave_position_set:
                            output_values[int(dof)] += local_result[position]
        self._output_vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        with self._output_vector.localForm() as output_local:
            output_values = output_local.array_w
            output_values[self._mpc_owned_slave_indices] = source_values[
                self._mpc_owned_slave_indices
            ]
            target.getArray()[:] = output_values[:owned_size]

    def _destroy_vectors(self) -> None:
        if self._output_vector is not None:
            self._output_vector.destroy()
            self._output_vector = None
        if self._input_vector is not None:
            self._input_vector.destroy()
            self._input_vector = None

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        matrix = self._matrix
        self._matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()
        self._destroy_vectors()


def build_task037_extra_candidate_h_fullspace_action(
    compiled_form: Any,
    function_space: Any,
    cell_tags: Any,
    *,
    mpc: Any | None = None,
    task037_extra_candidate_h: bool = False,
    geometry_tolerance: float = 1.0e-11,
) -> FullSpaceMatrixFreeHcurlAction:
    """Build the explicit Candidate-H H1.1 element-local action."""

    if not bool(task037_extra_candidate_h):
        raise ValueError(
            "full-space Candidate H action requires explicit opt-in"
        )
    return FullSpaceMatrixFreeHcurlAction(
        compiled_form,
        function_space,
        cell_tags,
        mpc=mpc,
        geometry_tolerance=geometry_tolerance,
    )
