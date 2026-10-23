from __future__ import annotations

import unittest
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity import variable_p_transfer
from src.adaptivity.exact_sequence_variable_p import (
    build_variable_p_reference_space,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)
from src.adaptivity.variable_p_transfer import (
    build_variable_p_global_transfer,
    extract_active_full_from_p6_field,
    project_p6_dual_to_active_full,
    recover_active_full_to_p6_field,
)
from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _global_vec_values(vector: PETSc.Vec, comm) -> np.ndarray:
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    return np.concatenate(comm.allgather(local))


def _all_cell_projection_reference(
    transfer,
    p6_vector: PETSc.Vec,
) -> PETSc.Vec:
    """Original all-cell projection, kept only as a test oracle."""

    comm = transfer.entity_map.mesh.comm
    p6_vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    with p6_vector.localForm() as local_form:
        local_values = np.asarray(
            local_form.getArray(readonly=True), dtype=np.complex128
        ).copy()
    active = PETSc.Vec().createMPI(
        (
            transfer.active_counts[comm.rank],
            transfer.entity_map.active_rows,
        ),
        comm=comm,
    )
    active.set(PETSc.ScalarType(0.0))
    try:
        for cell_transfer in transfer.cells:
            local_p6 = np.zeros(882, dtype=np.complex128)
            selected = cell_transfer.designated_local_positions
            local_p6[selected] = local_values[
                cell_transfer.p6_local_dofs[selected]
            ]
            space = build_variable_p_reference_space(
                cell_transfer.cell.degree_map
            )
            local_active = space.project_p6_oriented_dual(
                local_p6,
                cell_info=cell_transfer.cell.cell_info,
            )
            active.setValues(
                np.asarray(
                    cell_transfer.cell.active_rows,
                    dtype=PETSc.IntType,
                ),
                np.asarray(local_active, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        active.assemble()
        return active
    except Exception:
        active.destroy()
        raise


def _expected_nonzero_cell_count(transfer, p6_vector: PETSc.Vec) -> int:
    p6_vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    with p6_vector.localForm() as local_form:
        local_values = np.asarray(
            local_form.getArray(readonly=True), dtype=np.complex128
        ).copy()
    count = 0
    for cell_transfer in transfer.cells:
        local_p6 = np.zeros(882, dtype=np.complex128)
        selected = cell_transfer.designated_local_positions
        local_p6[selected] = local_values[
            cell_transfer.p6_local_dofs[selected]
        ]
        count += int(bool(np.any(local_p6)))
    return count


def _surface_loads(msh, p6_space):
    """Build actual complex top/bottom port-component loads on one mesh."""

    fdim = msh.topology.dim - 1
    msh.topology.create_connectivity(fdim, msh.topology.dim)
    exterior = mesh.exterior_facet_indices(msh.topology)
    midpoints = mesh.compute_midpoints(msh, fdim, exterior)
    z = midpoints[:, 2]
    tags = np.zeros(len(exterior), dtype=np.int32)
    tags[np.isclose(z, 0.0)] = 11
    tags[np.isclose(z, 1.0)] = 12
    selected = tags != 0
    facet_tags = mesh.meshtags(
        msh,
        fdim,
        np.asarray(exterior[selected], dtype=np.int32),
        tags[selected],
    )
    mesh_data = SimpleNamespace(mesh=msh, facet_tags=facet_tags)
    mode = SimpleNamespace(
        alpha=0.37 + 0.11j,
        gamma=-0.23 + 0.07j,
        k_vector=np.asarray([0.2 + 0.1j, -0.3 + 0.05j, 0.41 + 0.08j]),
        boundary_amplitude_log_scale=0.0,
    )
    top = _ReusableSurfaceComponentAssembler(
        p6_space, mesh_data, 12, 0
    ).assemble_unconstrained_vector(mode)
    bottom = _ReusableSurfaceComponentAssembler(
        p6_space, mesh_data, 11, 0
    ).assemble_unconstrained_vector(mode)
    top_bottom = top.copy()
    top_bottom.axpy(PETSc.ScalarType(1.0), bottom)
    top_bottom.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return {"top": top, "bottom": bottom, "top_bottom": top_bottom}


def _compare_sparse_projection(transfer, p6_vector, *, time_paths=False):
    comm = transfer.entity_map.mesh.comm
    local_nonzero = _expected_nonzero_cell_count(transfer, p6_vector)
    if time_paths:
        warm_optimized = project_p6_dual_to_active_full(transfer, p6_vector)
        warm_reference = _all_cell_projection_reference(transfer, p6_vector)
        warm_optimized.destroy()
        warm_reference.destroy()

    calls = []
    original_builder = variable_p_transfer.build_variable_p_reference_space

    def track_builder(degree_map, *, calls=calls):
        calls.append(degree_map)
        return original_builder(degree_map)

    with patch.object(
        variable_p_transfer,
        "build_variable_p_reference_space",
        side_effect=track_builder,
    ):
        optimized_start = perf_counter()
        optimized = project_p6_dual_to_active_full(transfer, p6_vector)
        optimized_wall = perf_counter() - optimized_start
    try:
        reference_start = perf_counter()
        reference = _all_cell_projection_reference(transfer, p6_vector)
        reference_wall = perf_counter() - reference_start
    except Exception:
        optimized.destroy()
        raise

    optimized_values = _global_vec_values(optimized, comm)
    reference_values = _global_vec_values(reference, comm)
    difference = float(
        np.max(np.abs(optimized_values - reference_values), initial=0.0)
    )
    scale = max(
        float(np.max(np.abs(reference_values), initial=0.0)),
        1.0e-300,
    )
    audit = {
        "local_nonzero_cells": local_nonzero,
        "local_project_calls": len(calls),
        "global_nonzero_cells": int(comm.allreduce(local_nonzero, op=MPI.SUM)),
        "global_owned_cells": int(
            comm.allreduce(len(transfer.cells), op=MPI.SUM)
        ),
        "max_abs_difference": difference,
        "relative_difference": difference / scale,
        "optimized_wall_max_s": float(
            comm.allreduce(optimized_wall, op=MPI.MAX)
        ),
        "all_cell_reference_wall_max_s": float(
            comm.allreduce(reference_wall, op=MPI.MAX)
        ),
    }
    return optimized, reference, audit


class Task035dVariablePTransferTests(unittest.TestCase):
    def test_parent_p4_field_primal_transfers_to_candidate_p5_and_recovers(self) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("parent-to-candidate primal extraction is serial-only")
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        parent_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 4),
            face_degrees=_degree_array(msh, 2, 4),
            cell_degrees=_degree_array(msh, 3, 4),
        )
        candidate_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 5),
            face_degrees=_degree_array(msh, 2, 5),
            cell_degrees=_degree_array(msh, 3, 5),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        parent_transfer = build_variable_p_global_transfer(
            parent_map,
            p6_space,
        )
        candidate_transfer = build_variable_p_global_transfer(
            candidate_map,
            p6_space,
        )
        parent_rows = np.arange(parent_map.active_rows, dtype=np.float64)
        parent_active = np.sin(0.011 * parent_rows) + 1j * np.cos(
            0.017 * parent_rows
        )
        parent_field, _parent_recovery = recover_active_full_to_p6_field(
            parent_transfer,
            parent_active,
        )

        candidate_active, extraction = extract_active_full_from_p6_field(
            candidate_transfer,
            parent_field,
        )
        candidate_field, recovery = recover_active_full_to_p6_field(
            candidate_transfer,
            candidate_active,
        )
        self.assertTrue(extraction["pass"])
        self.assertEqual(extraction["unique_cell_degree_maps"], 1)
        self.assertLessEqual(
            extraction["maximum_shared_active_row_relative_error"],
            5.0e-10,
        )
        self.assertTrue(recovery["pass"])
        old_values = np.asarray(parent_field.x.array, dtype=np.complex128)
        new_values = np.asarray(candidate_field.x.array, dtype=np.complex128)
        relative_error = float(
            np.max(np.abs(old_values - new_values), initial=0.0)
            / max(1.0, float(np.max(np.abs(old_values), initial=0.0)))
        )
        self.assertLessEqual(relative_error, 5.0e-10)

    def test_matrix_free_transfer_is_conforming_and_adjoint(self) -> None:
        if MPI.COMM_WORLD.size not in {1, 2}:
            self.skipTest("Task035d A4 qualifies serial and MPI2")
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        entity_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 4),
            face_degrees=_degree_array(msh, 2, 5),
            cell_degrees=_degree_array(msh, 3, 6),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        transfer = build_variable_p_global_transfer(
            entity_map,
            p6_space,
        )
        self.assertTrue(transfer.audit["pass"])
        self.assertEqual(
            transfer.audit["p6_global_rows"],
            entity_map.uniform_p6_rows,
        )
        self.assertEqual(
            transfer.audit["active_global_rows"],
            entity_map.active_rows,
        )
        self.assertTrue(transfer.audit["designation_is_one_to_one"])
        self.assertTrue(
            transfer.audit[
                "entity_blocks_never_split_between_designating_cells"
            ]
        )
        self.assertFalse(
            transfer.audit["global_embedding_matrix_allocated"]
        )

        global_rows = np.arange(entity_map.active_rows, dtype=np.float64)
        active_values = (
            np.sin(0.013 * global_rows)
            + 1j * np.cos(0.017 * global_rows)
        )
        recovered, recovery_audit = recover_active_full_to_p6_field(
            transfer,
            active_values,
        )
        self.assertTrue(recovery_audit["pass"])
        self.assertLessEqual(
            recovery_audit["relative_shared_coefficient_error_max"],
            5.0e-10,
        )

        dual = fem.Function(p6_space)
        p6_index_map = p6_space.dofmap.index_map
        owned_p6 = int(p6_index_map.size_local)
        owned_global = np.asarray(
            p6_index_map.local_to_global(
                np.arange(owned_p6, dtype=np.int32)
            ),
            dtype=np.float64,
        )
        dual.x.array[:owned_p6] = (
            np.cos(0.019 * owned_global)
            + 1j * np.sin(0.023 * owned_global)
        )
        dual.x.scatter_forward()
        projected = project_p6_dual_to_active_full(
            transfer,
            dual.x.petsc_vec,
        )
        active_vector = PETSc.Vec().createMPI(
            (
                transfer.active_counts[MPI.COMM_WORLD.rank],
                entity_map.active_rows,
            ),
            comm=MPI.COMM_WORLD,
        )
        start, end = active_vector.getOwnershipRange()
        active_vector.getArray()[:] = active_values[start:end]
        active_vector.assemble()
        try:
            left = complex(
                dual.x.petsc_vec.dot(recovered.x.petsc_vec)
            )
            right = complex(projected.dot(active_vector))
            relative = abs(left - right) / max(abs(left), abs(right), 1.0)
            self.assertLessEqual(relative, 2.0e-11)
        finally:
            active_vector.destroy()
            projected.destroy()

    def test_sparse_surface_projection_skips_exact_zero_cells(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size not in {1, 2}:
            self.skipTest("sparse surface projection qualifies serial and MPI2")
        msh = mesh.create_unit_cube(
            comm,
            4,
            2,
            4,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        entity_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 4),
            face_degrees=_degree_array(msh, 2, 5),
            cell_degrees=_degree_array(msh, 3, 6),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        transfer = build_variable_p_global_transfer(entity_map, p6_space)
        loads = _surface_loads(msh, p6_space)
        global_cells = int(
            comm.allreduce(len(transfer.cells), op=MPI.SUM)
        )
        active_primal = (
            np.sin(0.013 * np.arange(entity_map.active_rows, dtype=np.float64))
            + 1j
            * np.cos(0.017 * np.arange(entity_map.active_rows, dtype=np.float64))
        )

        zero_function = fem.Function(p6_space)
        zero_function.x.array[:] = PETSc.ScalarType(0.0)
        zero_function.x.scatter_forward()
        try:
            zero_calls = []
            original_builder = variable_p_transfer.build_variable_p_reference_space

            def track_zero_builder(degree_map, *, zero_calls=zero_calls):
                zero_calls.append(degree_map)
                return original_builder(degree_map)

            with patch.object(
                variable_p_transfer,
                "build_variable_p_reference_space",
                side_effect=track_zero_builder,
            ):
                projected_zero = project_p6_dual_to_active_full(
                    transfer, zero_function.x.petsc_vec
                )
            try:
                self.assertEqual(zero_calls, [])
                self.assertEqual(projected_zero.norm(), 0.0)
            finally:
                projected_zero.destroy()
        finally:
            del zero_function

        load_names = ("top", "bottom") if comm.size == 1 else ("top_bottom",)
        try:
            for index, load_name in enumerate(load_names):
                with self.subTest(load=load_name, mpi_size=comm.size):
                    p6_load = loads[load_name]
                    self.assertGreater(p6_load.norm(), 0.0)
                    projected, reference, audit = _compare_sparse_projection(
                        transfer,
                        p6_load,
                        time_paths=(index == 0),
                    )
                    try:
                        self.assertEqual(
                            audit["local_project_calls"],
                            audit["local_nonzero_cells"],
                        )
                        self.assertLess(
                            audit["global_nonzero_cells"],
                            global_cells,
                        )
                        if comm.size == 2:
                            per_rank = comm.allgather(
                                audit["local_nonzero_cells"]
                            )
                            self.assertTrue(
                                all(value > 0 for value in per_rank),
                                f"surface load did not span ranks: {per_rank}",
                            )
                        self.assertLessEqual(audit["relative_difference"], 2.0e-12)
                        self.assertGreater(
                            audit["global_owned_cells"]
                            - audit["global_nonzero_cells"],
                            0,
                        )
                        if comm.rank == 0:
                            print(
                                "SPARSE_P6_PROJECTION_AUDIT "
                                f"mpi_size={comm.size} side={load_name} "
                                f"projected={audit['global_nonzero_cells']}/"
                                f"{audit['global_owned_cells']} "
                                f"skipped={audit['global_owned_cells'] - audit['global_nonzero_cells']} "
                                f"max_abs_diff={audit['max_abs_difference']:.9g} "
                                f"relative_diff={audit['relative_difference']:.9g} "
                                f"optimized_warm_wall_max_s={audit['optimized_wall_max_s']:.9g} "
                                f"all_cell_warm_wall_max_s={audit['all_cell_reference_wall_max_s']:.9g}",
                                flush=True,
                            )

                        if index == 0:
                            primal_vec = PETSc.Vec().createMPI(
                                (
                                    transfer.active_counts[comm.rank],
                                    entity_map.active_rows,
                                ),
                                comm=comm,
                            )
                            start, end = primal_vec.getOwnershipRange()
                            primal_vec.getArray()[:] = active_primal[start:end]
                            primal_vec.assemble()
                            recovered, recovery_audit = (
                                recover_active_full_to_p6_field(
                                    transfer, active_primal
                                )
                            )
                            try:
                                self.assertTrue(recovery_audit["pass"])
                                left = complex(
                                    p6_load.dot(recovered.x.petsc_vec)
                                )
                                right = complex(projected.dot(primal_vec))
                                relative_adjoint_error = abs(left - right) / max(
                                    abs(left), abs(right), 1.0e-300
                                )
                                self.assertLessEqual(
                                    relative_adjoint_error, 2.0e-11
                                )
                            finally:
                                del recovered
                                primal_vec.destroy()

                            tiny_load = p6_load.copy()
                            tiny_load.scale(PETSc.ScalarType(1.0e-100))
                            try:
                                self.assertGreater(tiny_load.norm(), 0.0)
                                tiny_projected, tiny_reference, tiny_audit = (
                                    _compare_sparse_projection(
                                        transfer, tiny_load
                                    )
                                )
                                try:
                                    self.assertEqual(
                                        tiny_audit["local_project_calls"],
                                        tiny_audit["local_nonzero_cells"],
                                    )
                                    self.assertEqual(
                                        tiny_audit["local_nonzero_cells"],
                                        audit["local_nonzero_cells"],
                                    )
                                    self.assertLessEqual(
                                        tiny_audit["relative_difference"],
                                        2.0e-12,
                                    )
                                    if comm.rank == 0:
                                        print(
                                            "SPARSE_P6_TINY_AUDIT "
                                            f"scale=1e-100 "
                                            f"projected={tiny_audit['global_nonzero_cells']}/"
                                            f"{tiny_audit['global_owned_cells']} "
                                            f"max_abs_diff={tiny_audit['max_abs_difference']:.9g} "
                                            f"relative_diff={tiny_audit['relative_difference']:.9g}",
                                            flush=True,
                                        )
                                finally:
                                    tiny_reference.destroy()
                                    tiny_projected.destroy()
                            finally:
                                tiny_load.destroy()
                    finally:
                        reference.destroy()
                        projected.destroy()
        finally:
            for vector in loads.values():
                vector.destroy()


if __name__ == "__main__":
    unittest.main()
