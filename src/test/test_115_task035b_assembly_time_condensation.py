from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

import dolfinx_mpc
import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc

from src.adaptivity.hcurl_regionwise_p import (
    create_reduced_trace_hcurl_element,
    reduced_trace_hcurl_ufl_element,
)
from src.common.config_3d import target_stage4_config
from src.solvers import hcurl_assembly_time_condensation as assembly_time
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
    project_mpc_vector_to_active_trace,
    recover_owned_cell_interiors,
)
from src.solvers.hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    owned_hcurl_cell_interior_dofs,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


def _two_cell_problem(*, distinct_materials: bool):
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = msh.topology.dim
    values = (
        np.asarray([1, 2], dtype=np.int32)
        if distinct_materials
        else np.asarray([1, 1], dtype=np.int32)
    )
    cell_tags = mesh.meshtags(
        msh,
        tdim,
        np.asarray([0, 1], dtype=np.int32),
        values,
    )
    V = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    a = (
        ufl.inner(ufl.curl(u), ufl.curl(v))
        + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
    ) * dx(1)
    if distinct_materials:
        a += (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(1.7 + 0.1j) * ufl.inner(u, v)
        ) * dx(2)
    return msh, cell_tags, V, fem.form(a)


class TestTask035bAssemblyTimeCondensation(unittest.TestCase):
    def test_regionwise_all_low_equals_standard_p4_and_mixed_counts(
        self,
    ) -> None:
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        cell_tags = mesh.meshtags(
            msh,
            msh.topology.dim,
            np.asarray([0, 1], dtype=np.int32),
            np.asarray([1, 1], dtype=np.int32),
        )

        def compiled_form(V):
            u = ufl.TrialFunction(V)
            v = ufl.TestFunction(V)
            dx = ufl.Measure(
                "dx",
                domain=msh,
                subdomain_data=cell_tags,
            )
            return fem.form(
                (
                    ufl.inner(ufl.curl(u), ufl.curl(v))
                    + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
                )
                * dx(1)
            )

        reduced = create_reduced_trace_hcurl_element(4, 6)
        V_reduced = fem.functionspace(
            msh,
            reduced_trace_hcurl_ufl_element(4, 6),
        )
        V_p4 = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                4,
                dtype=default_real_type,
            ),
        )
        low_compiled = compiled_form(V_p4)
        all_low = build_unconstrained_assembly_time_condensation(
            compiled_form(V_reduced),
            V_reduced,
            cell_tags,
            regionwise_element=reduced,
            regionwise_low_compiled_form=low_compiled,
            regionwise_high_canonical_cell_ids=(),
        )
        p4 = build_unconstrained_assembly_time_condensation(
            low_compiled,
            V_p4,
            cell_tags,
        )
        difference = all_low.matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            p4.matrix,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        self.assertLess(
            difference.norm() / max(p4.matrix.norm(), 1.0e-30),
            2.0e-11,
        )
        self.assertEqual(all_low.trace_rows, 344)
        self.assertEqual(all_low.active_interior_rows, 216)
        self.assertEqual(
            all_low.build_audit["active_full3d_equivalent_dofs"],
            560,
        )

        mixed = build_unconstrained_assembly_time_condensation(
            compiled_form(V_reduced),
            V_reduced,
            cell_tags,
            regionwise_element=reduced,
            regionwise_low_compiled_form=low_compiled,
            regionwise_high_canonical_cell_ids=(0,),
        )
        self.assertEqual(
            mixed.build_audit["regionwise_high_cell_count"],
            1,
        )
        self.assertEqual(
            mixed.build_audit["regionwise_low_cell_count"],
            1,
        )
        self.assertEqual(mixed.active_interior_rows, 558)
        self.assertEqual(
            mixed.build_audit["active_full3d_equivalent_dofs"],
            902,
        )
        self.assertEqual(mixed.matrix.getSize(), (344, 344))
        self.assertFalse(
            mixed.build_audit["inactive_max_p_rows_retained_in_matrix"]
        )

        mixed.destroy()
        difference.destroy()
        p4.destroy()
        all_low.destroy()

    def test_reduced_p4_trace_p6_interior_kernel_condenses_exactly(
        self,
    ) -> None:
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        cell_tags = mesh.meshtags(
            msh,
            msh.topology.dim,
            np.asarray([0], dtype=np.int32),
            np.asarray([1], dtype=np.int32),
        )
        V = fem.functionspace(
            msh,
            reduced_trace_hcurl_ufl_element(4, 6),
        )
        u = ufl.TrialFunction(V)
        v = ufl.TestFunction(V)
        dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
        compiled = fem.form(
            (
                ufl.inner(ufl.curl(u), ufl.curl(v))
                + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
            )
            * dx(1)
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        zero_rhs = full.createVecRight()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        reference = build_explicit_cell_static_condensation(
            full,
            zero_rhs,
            owned_hcurl_cell_interior_dofs(V),
        )
        difference = candidate.matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            reference.matrix,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        self.assertLess(
            difference.norm() / max(reference.matrix.norm(), 1.0e-30),
            1.0e-12,
        )
        self.assertEqual(candidate.full_rows, 642)
        self.assertEqual(candidate.trace_rows, 192)
        self.assertEqual(candidate.interior_rows, 450)
        self.assertEqual(
            candidate.build_audit["local_tensor_dimension"],
            642,
        )
        self.assertFalse(
            candidate.build_audit["full_global_matrix_allocated"]
        )

        difference.destroy()
        reference.destroy()
        zero_rhs.destroy()
        full.destroy()
        candidate.destroy()

    def test_matches_post_assembly_reference_and_recovers_interiors(self) -> None:
        _msh, cell_tags, V, compiled = _two_cell_problem(
            distinct_materials=True
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        zero_rhs = full.createVecRight()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        reference = build_explicit_cell_static_condensation(
            full,
            zero_rhs,
            owned_hcurl_cell_interior_dofs(V),
        )
        candidate_dense = (
            candidate.matrix.convert("dense").getDenseArray().copy()
        )
        reference_dense = (
            reference.matrix.convert("dense").getDenseArray().copy()
        )
        relative = np.linalg.norm(candidate_dense - reference_dense) / np.linalg.norm(
            reference_dense
        )
        self.assertLess(relative, 1.0e-13)
        self.assertLess(
            float(np.max(np.abs(candidate_dense - reference_dense))),
            1.0e-11,
        )
        self.assertFalse(
            candidate.build_audit["full_global_matrix_allocated"]
        )
        self.assertTrue(candidate.build_audit["assembly_cost_avoided"])

        rng = np.random.default_rng(20260724)
        trace_values = (
            rng.standard_normal(candidate.trace_rows)
            + 1j * rng.standard_normal(candidate.trace_rows)
        )
        full_values = np.zeros(candidate.full_rows, dtype=np.complex128)
        for original, trace in candidate.original_to_trace.items():
            full_values[original] = trace_values[trace]
        recovered = recover_owned_cell_interiors(candidate, trace_values)
        interior_rows: list[np.ndarray] = []
        for dofs, values in recovered:
            full_values[dofs] = values
            interior_rows.append(dofs)
        x = full.createVecRight()
        x.getArray()[:] = np.asarray(full_values, dtype=PETSc.ScalarType)
        x.assemble()
        residual = full.createVecLeft()
        full.mult(x, residual)
        all_interiors = np.concatenate(interior_rows)
        self.assertLess(
            float(
                np.linalg.norm(
                    np.asarray(
                        residual.getValues(all_interiors),
                        dtype=np.complex128,
                    )
                )
            ),
            1.0e-10,
        )

        residual.destroy()
        x.destroy()
        reference.destroy()
        zero_rhs.destroy()
        full.destroy()
        candidate.destroy()

    def test_reuses_raw_tensor_for_equal_material_and_width(self) -> None:
        _msh, cell_tags, V, compiled = _two_cell_problem(
            distinct_materials=False
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
        )
        audit = candidate.build_audit
        self.assertEqual(audit["owned_cell_count_global"], 2)
        self.assertEqual(audit["raw_tensor_class_count_sum"], 1)
        self.assertEqual(audit["cell_kernel_evaluation_fraction"], 0.5)
        candidate.destroy()

    def test_nonzero_interior_rhs_and_auxiliary_schur_terms(self) -> None:
        _msh, cell_tags, V, compiled = _two_cell_problem(
            distinct_materials=True
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        full_dense = full.convert("dense").getDenseArray().copy()
        rng = np.random.default_rng(2026072401)
        right_values = (
            rng.standard_normal(candidate.full_rows)
            + 1j * rng.standard_normal(candidate.full_rows)
        )
        left_values = (
            rng.standard_normal(candidate.full_rows)
            + 1j * rng.standard_normal(candidate.full_rows)
        )
        right = full.createVecRight()
        right.getArray()[:] = np.asarray(
            right_values,
            dtype=PETSc.ScalarType,
        )
        right.assemble()
        left = full.createVecLeft()
        left.getArray()[:] = np.asarray(
            left_values,
            dtype=PETSc.ScalarType,
        )
        left.assemble()

        reduced_right = condense_unconstrained_vector_to_active_trace(
            candidate,
            right,
            side="right",
        )
        reduced_left = condense_unconstrained_vector_to_active_trace(
            candidate,
            left,
            side="left",
        )
        trace = np.asarray(
            [
                original
                for original, _trace in sorted(
                    candidate.original_to_trace.items(),
                    key=lambda item: item[1],
                )
            ],
            dtype=np.int64,
        )
        interior = np.asarray(
            sorted(set(range(candidate.full_rows)) - set(trace)),
            dtype=np.int64,
        )
        A_ii = full_dense[np.ix_(interior, interior)]
        A_it = full_dense[np.ix_(interior, trace)]
        A_ti = full_dense[np.ix_(trace, interior)]
        expected_right = (
            right_values[trace]
            - A_ti @ np.linalg.solve(A_ii, right_values[interior])
        )
        expected_left = (
            left_values[trace]
            - A_it.conj().T
            @ np.linalg.solve(
                A_ii.conj().T,
                left_values[interior],
            )
        )
        np.testing.assert_allclose(
            reduced_right.getArray(readonly=True),
            expected_right,
            rtol=2.0e-13,
            atol=2.0e-12,
        )
        np.testing.assert_allclose(
            reduced_left.getArray(readonly=True),
            expected_left,
            rtol=2.0e-13,
            atol=2.0e-12,
        )
        expected_bilinear = np.vdot(
            left_values[interior],
            np.linalg.solve(A_ii, right_values[interior]),
        )
        self.assertAlmostEqual(
            cell_interior_schur_bilinear(
                candidate,
                left,
                right,
            ),
            expected_bilinear,
            places=11,
        )

        trace_solution = np.linalg.solve(
            candidate.matrix.convert("dense").getDenseArray(),
            expected_right,
        )
        recovered_values = np.zeros(
            candidate.full_rows,
            dtype=np.complex128,
        )
        recovered_values[trace] = trace_solution
        for rows, values in recover_owned_cell_interiors(
            candidate,
            trace_solution,
            full_rhs=right,
        ):
            recovered_values[rows] = values
        np.testing.assert_allclose(
            recovered_values,
            np.linalg.solve(full_dense, right_values),
            rtol=3.0e-12,
            atol=3.0e-11,
        )

        reduced_left.destroy()
        reduced_right.destroy()
        left.destroy()
        right.destroy()
        full.destroy()
        candidate.destroy()

    def test_rejects_non_axis_aligned_geometry(self) -> None:
        msh, cell_tags, V, compiled = _two_cell_problem(
            distinct_materials=True
        )
        msh.geometry.x[0, 1] += 0.03125
        with self.assertRaisesRegex(
            ValueError,
            "axis-aligned affine hexahedra",
        ):
            build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
            )

    def test_complex_mpc_is_applied_before_global_insertion(self) -> None:
        msh, cell_tags, V, _compiled = _two_cell_problem(
            distinct_materials=False
        )
        u = ufl.TrialFunction(V)
        v = ufl.TestFunction(V)
        dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
        compiled = fem.form(
            PETSc.ScalarType(0.0) * ufl.inner(u, v) * dx
            + (
                ufl.inner(ufl.curl(u), ufl.curl(v))
                + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
            )
            * dx(1)
        )
        cell_interiors = owned_hcurl_cell_interior_dofs(V)
        interior_set = {
            int(value)
            for interior in cell_interiors
            for value in interior
        }
        trace_original = [
            value
            for value in range(V.dofmap.index_map.size_global)
            if value not in interior_set
        ]
        master = int(trace_original[0])
        slave = int(trace_original[-1])
        coefficient = PETSc.ScalarType(0.5 + 0.25j)
        mpc = dolfinx_mpc.MultiPointConstraint(V)
        mpc.add_constraint(
            V,
            np.asarray([slave], dtype=np.int32),
            np.asarray([master], dtype=np.int64),
            np.asarray([coefficient], dtype=PETSc.ScalarType),
            np.asarray([0], dtype=np.int32),
            np.asarray([0, 1], dtype=np.int32),
        )
        mpc.finalize()

        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            mpc=mpc,
        )
        embedded = dolfinx_mpc.assemble_matrix(
            compiled,
            mpc,
            bcs=[],
        )
        embedded.assemble()
        zero_rhs = embedded.createVecRight()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        post = build_explicit_cell_static_condensation(
            embedded,
            zero_rhs,
            cell_interiors,
        )
        reference = build_floquet_independent_trace_system(
            post.matrix,
            post.rhs,
            owned_slave_original_dofs=np.asarray(
                [slave],
                dtype=PETSc.IntType,
            ),
            original_to_trace=post.original_to_trace,
        )
        difference = candidate.matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            reference.matrix,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        self.assertLess(
            difference.norm() / max(reference.matrix.norm(), 1.0e-30),
            1.0e-13,
        )
        self.assertEqual(candidate.trace_rows, 84)
        self.assertEqual(candidate.active_rows, 83)
        self.assertFalse(
            candidate.build_audit["full_trace_matrix_allocated"]
        )
        self.assertFalse(
            candidate.build_audit[
                "embedded_mpc_slave_identity_rows_allocated"
            ]
        )
        projected_rhs = project_mpc_vector_to_active_trace(
            candidate,
            zero_rhs,
        )
        self.assertEqual(projected_rhs.getSize(), candidate.active_rows)
        self.assertEqual(projected_rhs.norm(), 0.0)

        unconstrained = fem_petsc.assemble_matrix(compiled, bcs=[])
        unconstrained.assemble()
        rng = np.random.default_rng(20260724)
        active_values = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        full_values = np.zeros(candidate.full_rows, dtype=np.complex128)
        for original, (active_ids, coefficients) in (
            candidate.trace_constraints.expansion_by_original.items()
        ):
            full_values[original] = np.dot(
                coefficients,
                active_values[active_ids],
            )
        recovered = recover_owned_cell_interiors(
            candidate,
            active_values,
        )
        interior_rows: list[np.ndarray] = []
        for rows, values in recovered:
            full_values[rows] = values
            interior_rows.append(rows)
        x = unconstrained.createVecRight()
        x.getArray()[:] = np.asarray(
            full_values,
            dtype=PETSc.ScalarType,
        )
        x.assemble()
        residual = unconstrained.createVecLeft()
        unconstrained.mult(x, residual)
        self.assertLess(
            float(
                np.linalg.norm(
                    residual.getValues(np.concatenate(interior_rows))
                )
            ),
            1.0e-10,
        )

        residual.destroy()
        x.destroy()
        unconstrained.destroy()
        projected_rhs.destroy()
        difference.destroy()
        reference.destroy()
        post.destroy()
        zero_rhs.destroy()
        embedded.destroy()
        candidate.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 distributed condensation check",
    )
    def test_mpi2_matches_post_assembly_reference(self) -> None:
        comm = MPI.COMM_WORLD
        msh = mesh.create_unit_cube(
            comm,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        tdim = msh.topology.dim
        owned_cells = msh.topology.index_map(tdim).size_local
        cell_tags = mesh.meshtags(
            msh,
            tdim,
            np.arange(owned_cells, dtype=np.int32),
            np.ones(owned_cells, dtype=np.int32),
        )
        V = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                2,
                dtype=default_real_type,
            ),
        )
        u = ufl.TrialFunction(V)
        v = ufl.TestFunction(V)
        dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
        compiled = fem.form(
            (
                ufl.inner(ufl.curl(u), ufl.curl(v))
                + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
            )
            * dx(1)
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        manual_full = PETSc.Mat().createAIJ(
            size=(
                (
                    V.dofmap.index_map.size_local,
                    V.dofmap.index_map.size_global,
                ),
                (
                    V.dofmap.index_map.size_local,
                    V.dofmap.index_map.size_global,
                ),
            ),
            nnz=2 * V.element.space_dimension,
            comm=comm,
        )
        manual_full.setOption(
            PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,
            False,
        )
        kernels = assembly_time._cell_integral_kernels(compiled)
        msh.topology.create_entity_permutations()
        permutations = msh.topology.get_cell_permutation_info()
        for cell in range(owned_cells):
            coordinates, _widths = (
                assembly_time._canonical_axis_aligned_coordinates(
                    msh,
                    cell,
                    tolerance=1.0e-11,
                )
            )
            tensor = assembly_time._tabulate_cell_tensor(
                compiled,
                kernels[1],
                coordinates,
                V.element.space_dimension,
            )
            assembly_time._orient_cell_tensor(
                V.element,
                tensor,
                permutations[cell : cell + 1],
            )
            local_dofs = np.asarray(
                V.dofmap.cell_dofs(cell),
                dtype=np.int32,
            )
            global_dofs = np.asarray(
                V.dofmap.index_map.local_to_global(local_dofs),
                dtype=PETSc.IntType,
            )
            manual_full.setValues(
                global_dofs,
                global_dofs,
                tensor,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        manual_full.assemble()
        manual_difference = manual_full.copy()
        manual_difference.axpy(
            PETSc.ScalarType(-1.0),
            full,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        manual_relative = manual_difference.norm() / max(
            full.norm(),
            1.0e-30,
        )
        self.assertLess(manual_relative, 1.0e-13)
        zero_rhs = full.createVecRight()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        reference = build_explicit_cell_static_condensation(
            full,
            zero_rhs,
            owned_hcurl_cell_interior_dofs(V),
        )
        difference = candidate.matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            reference.matrix,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        relative = difference.norm() / max(reference.matrix.norm(), 1.0e-30)
        self.assertLess(relative, 1.0e-13)
        self.assertEqual(candidate.trace_rows, reference.trace_rows)
        self.assertEqual(
            candidate.build_audit["owned_cell_count_global"],
            2,
        )

        difference.destroy()
        manual_difference.destroy()
        manual_full.destroy()
        reference.destroy()
        zero_rhs.destroy()
        full.destroy()
        candidate.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size in {2, 8},
        "MPI2/MPI8 end-to-end assembly-time condensation check",
    )
    def test_mpi_end_to_end_fixed_rectangular_dtn(self) -> None:
        comm = MPI.COMM_WORLD
        cfg = replace(
            target_stage4_config(degree=2, h_nm=100.0),
            case_name=(
                f"task035b_assembly_time_smoke_mpi{comm.size}"
            ),
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            stage4_cell_static_condensation=True,
            stage4_assembly_time_cell_static_condensation=True,
            stage4_floquet_slave_elimination=True,
            direct_release_base_after_augmentation=True,
            direct_release_solver_before_postprocess=True,
            unique_output=False,
        )
        summary = run_stage4b_block_grating_3d_case(
            cfg,
            Path(
                f"/tmp/task035b_assembly_time_smoke_mpi{comm.size}"
            ),
        )
        self.assertEqual(summary["case_status"], "completed")
        self.assertTrue(
            summary["stage4_assembly_time_cell_static_condensation"]
        )
        self.assertTrue(
            summary["solver_objects_released_before_postprocess"]
        )
        release_audit = summary["solver_release_audit"]
        self.assertTrue(release_audit["petsc_garbage_cleanup_called"])
        heap_trim = release_audit["process_heap_trim"]
        self.assertEqual(heap_trim["implementation"], "glibc_malloc_trim")
        self.assertTrue(heap_trim["supported_on_all_ranks"])
        self.assertTrue(heap_trim["succeeded_on_all_ranks"])
        self.assertEqual(len(heap_trim["return_codes_by_rank"]), comm.size)
        self.assertTrue(all(heap_trim["return_codes_by_rank"]))
        self.assertGreaterEqual(heap_trim["sum_rss_before_mb"], 0.0)
        self.assertGreaterEqual(heap_trim["sum_rss_after_mb"], 0.0)
        self.assertGreaterEqual(heap_trim["sum_rss_released_mb"], 0.0)
        self.assertFalse(heap_trim["ordinary_default_changed"])
        self.assertEqual(summary["num_nedelec_dofs"], 802)
        self.assertEqual(summary["matrix_stats"]["matrix_rows"], 560)
        self.assertEqual(
            summary["matrix_stats"]["matrix_nnz_used"],
            {2: 48412.0, 8: 48716.0}[comm.size],
        )
        self.assertLess(
            summary["linear_system_relative_residual"],
            1.0e-10,
        )
        self.assertAlmostEqual(
            summary["R_total"],
            0.9997827084780738,
            places=11,
        )
        self.assertAlmostEqual(
            summary["T_total"],
            0.00010870177442776466,
            places=13,
        )
        audit = summary["cell_static_condensation"]
        self.assertFalse(audit["full_global_matrix_allocated"])
        self.assertFalse(audit["full_trace_matrix_allocated"])
        self.assertFalse(
            audit["embedded_mpc_slave_identity_rows_allocated"]
        )
        self.assertEqual(audit["full_rows"], 802)
        self.assertEqual(audit["trace_rows"], 658)
        self.assertEqual(audit["active_rows"], 480)
        self.assertEqual(audit["appended_rows"], 80)

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 reduced-trace regionwise-p end-to-end check",
    )
    def test_mpi2_end_to_end_reduced_trace_regionwise_p(self) -> None:
        cfg = replace(
            target_stage4_config(degree=6, h_nm=100.0),
            case_name="task035b_regionwise_p_smoke_mpi2",
            nedelec_trace_degree=4,
            nedelec_interior_degree=6,
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            stage4_cell_static_condensation=True,
            stage4_assembly_time_cell_static_condensation=True,
            stage4_floquet_slave_elimination=True,
            stage4_regionwise_interior_p=True,
            stage4_regionwise_high_canonical_cell_ids=(0,),
            direct_release_base_after_augmentation=True,
            direct_release_solver_before_postprocess=True,
            unique_output=False,
        )
        summary = run_stage4b_block_grating_3d_case(
            cfg,
            Path("/tmp/task035b_regionwise_p_smoke_mpi2"),
        )
        self.assertEqual(summary["case_status"], "completed")
        self.assertTrue(summary["official_result"])
        self.assertLessEqual(
            summary["linear_system_relative_residual"],
            1.0e-9,
        )
        audit = summary["cell_static_condensation"]
        self.assertTrue(audit["regionwise_interior_p_active"])
        self.assertEqual(audit["regionwise_high_cell_count"], 1)
        self.assertEqual(
            audit["regionwise_low_cell_count"],
            audit["owned_cell_count_global"] - 1,
        )
        expected_active_modes = (
            audit["trace_rows"]
            + 450
            + 108 * audit["regionwise_low_cell_count"]
        )
        self.assertEqual(
            audit["active_full3d_equivalent_dofs"],
            expected_active_modes,
        )
        self.assertEqual(
            summary["matrix_stats"]["matrix_rows"],
            audit["active_rows"] + audit["appended_rows"],
        )
        self.assertFalse(
            audit["inactive_max_p_rows_retained_in_matrix"]
        )
        self.assertFalse(audit["full_global_matrix_allocated"])
        for observable in ("R00_total", "R_total", "T_total"):
            self.assertTrue(np.isfinite(summary[observable]), observable)


if __name__ == "__main__":
    unittest.main()
