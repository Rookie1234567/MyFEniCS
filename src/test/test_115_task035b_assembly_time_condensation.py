from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

import dolfinx_mpc
import numpy as np
import ufl
from basix.ufl import element, wrap_element
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
    recover_full_dual_from_active_trace,
    recover_owned_cell_interiors,
    register_appended_dual_interior_coupling,
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


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(
        values[start:end],
        dtype=PETSc.ScalarType,
    )
    vector.assemble()


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

    def test_p5_trace_p4_low_kernel_matches_direct_mixed_space(self) -> None:
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

        reduced = create_reduced_trace_hcurl_element(5, 6, 4)
        V_high = fem.functionspace(msh, wrap_element(reduced.element))
        V_low = fem.functionspace(msh, wrap_element(reduced.low_element))
        low_compiled = compiled_form(V_low)
        all_low = build_unconstrained_assembly_time_condensation(
            compiled_form(V_high),
            V_high,
            cell_tags,
            regionwise_element=reduced,
            regionwise_low_compiled_form=low_compiled,
            regionwise_high_canonical_cell_ids=(),
        )
        independent_low = build_unconstrained_assembly_time_condensation(
            low_compiled,
            V_low,
            cell_tags,
        )
        difference = all_low.matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            independent_low.matrix,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        self.assertLess(
            difference.norm()
            / max(independent_low.matrix.norm(), 1.0e-30),
            3.0e-11,
        )
        self.assertEqual(all_low.trace_rows, 540)
        self.assertEqual(all_low.active_interior_rows, 216)
        self.assertEqual(
            all_low.build_audit["active_full3d_equivalent_dofs"],
            756,
        )
        self.assertEqual(
            all_low.build_audit["regionwise_trace_degree"],
            5,
        )
        self.assertEqual(
            all_low.build_audit["regionwise_low_interior_degree"],
            4,
        )

        one_high = build_unconstrained_assembly_time_condensation(
            compiled_form(V_high),
            V_high,
            cell_tags,
            regionwise_element=reduced,
            regionwise_low_compiled_form=low_compiled,
            regionwise_high_canonical_cell_ids=(0,),
        )
        self.assertEqual(one_high.active_interior_rows, 558)
        self.assertEqual(
            one_high.build_audit["active_full3d_equivalent_dofs"],
            1098,
        )
        self.assertEqual(one_high.matrix.getSize(), (540, 540))
        self.assertFalse(
            one_high.build_audit["inactive_max_p_rows_retained_in_matrix"]
        )

        one_high.destroy()
        difference.destroy()
        independent_low.destroy()
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

    def test_complex_nonhermitian_dual_recovery_closes_schur_pairing(
        self,
    ) -> None:
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
        diagonal = full.createVecRight()
        full.getDiagonal(diagonal)
        self.assertGreater(
            np.linalg.norm(
                np.asarray(
                    diagonal.getArray(readonly=True),
                    dtype=np.complex128,
                ).imag
            ),
            1.0e-6,
        )
        diagonal.destroy()

        rng = np.random.default_rng(2026072402)
        active_primal = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        active_dual = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        full_primal_values = np.zeros(
            candidate.full_rows,
            dtype=np.complex128,
        )
        for original, (active_ids, coefficients) in (
            candidate.trace_constraints.expansion_by_original.items()
        ):
            full_primal_values[original] = np.dot(
                coefficients,
                active_primal[active_ids],
            )
        for rows, values in recover_owned_cell_interiors(
            candidate,
            active_primal,
        ):
            full_primal_values[rows] = values
        full_primal = full.createVecRight()
        _set_owned_values(full_primal, full_primal_values)
        full_dual = recover_full_dual_from_active_trace(
            candidate,
            active_dual,
        )

        full_action = full.createVecLeft()
        full.mult(full_primal, full_action)
        full_adjoint_action = full.createVecRight()
        full.multHermitian(full_dual, full_adjoint_action)
        interior_rows = np.concatenate(
            [
                cell.interior_original_dofs
                for cell in candidate.cell_recovery_maps
            ]
        )
        self.assertLess(
            np.linalg.norm(
                full_adjoint_action.getValues(
                    np.asarray(interior_rows, dtype=PETSc.IntType)
                )
            ),
            2.0e-10,
        )

        reduced_primal = candidate.matrix.createVecRight()
        reduced_dual = candidate.matrix.createVecLeft()
        _set_owned_values(reduced_primal, active_primal)
        _set_owned_values(reduced_dual, active_dual)
        reduced_action = candidate.matrix.createVecLeft()
        candidate.matrix.mult(reduced_primal, reduced_action)
        reduced_adjoint_action = candidate.matrix.createVecRight()
        candidate.matrix.multHermitian(
            reduced_dual,
            reduced_adjoint_action,
        )
        self.assertLess(
            abs(full_dual.dot(full_action) - reduced_dual.dot(reduced_action))
            / max(abs(reduced_dual.dot(reduced_action)), 1.0e-30),
            2.0e-12,
        )
        trace_rows = np.asarray(
            [
                original
                for original, _trace in sorted(
                    candidate.original_to_trace.items(),
                    key=lambda item: item[1],
                )
            ],
            dtype=PETSc.IntType,
        )
        np.testing.assert_allclose(
            full_adjoint_action.getValues(trace_rows),
            reduced_adjoint_action.getArray(readonly=True),
            rtol=3.0e-12,
            atol=3.0e-11,
        )

        reduced_adjoint_action.destroy()
        reduced_action.destroy()
        reduced_dual.destroy()
        reduced_primal.destroy()
        full_adjoint_action.destroy()
        full_action.destroy()
        full_dual.destroy()
        full_primal.destroy()
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
        self.assertEqual(audit["raw_tensor_class_count_global_unique"], 1)
        self.assertEqual(audit["raw_tensor_class_use_count_sum"], 1)
        self.assertFalse(audit["raw_tensor_cross_rank_dedup_active"])
        self.assertEqual(audit["cell_kernel_evaluation_fraction"], 0.5)
        matrix_info = candidate.matrix.getInfo(
            PETSc.Mat.InfoType.GLOBAL_SUM
        )
        self.assertEqual(matrix_info["mallocs"], 0.0)
        self.assertEqual(matrix_info["nz_unneeded"], 0.0)
        candidate.destroy()

    def test_exact_preallocation_covers_appended_support(self) -> None:
        _msh, cell_tags, V, compiled = _two_cell_problem(
            distinct_materials=False
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            appended_global_rows=2,
            appended_support_owned_cell_groups=(
                np.asarray([0], dtype=np.int32),
                np.asarray([1], dtype=np.int32),
            ),
            appended_support_group_by_row=(0, 1),
            defer_final_assembly=True,
        )
        audit = candidate.build_audit["trace_preallocation"]
        self.assertEqual(audit["appended_support_group_count"], 2)
        self.assertEqual(audit["appended_rows_per_support_group"], [1, 1])
        for appended_index, recovery in enumerate(
            candidate.cell_recovery_maps
        ):
            support = np.unique(
                np.concatenate(
                    [
                        candidate.trace_constraints.expansion_by_original[
                            int(original)
                        ][0]
                        for original in recovery.trace_original_dofs
                    ]
                )
            ).astype(PETSc.IntType)
            auxiliary = candidate.active_rows + appended_index
            candidate.matrix.setValues(
                support,
                np.asarray([auxiliary], dtype=PETSc.IntType),
                np.ones((len(support), 1), dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            candidate.matrix.setValues(
                np.asarray([auxiliary], dtype=PETSc.IntType),
                support,
                np.ones((1, len(support)), dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            candidate.matrix.setValue(
                auxiliary,
                auxiliary,
                PETSc.ScalarType(1.0),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        candidate.matrix.assemble()
        matrix_info = candidate.matrix.getInfo(
            PETSc.Mat.InfoType.GLOBAL_SUM
        )
        self.assertEqual(matrix_info["mallocs"], 0.0)
        self.assertEqual(matrix_info["nz_unneeded"], 0.0)
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

    def test_augmented_nonhermitian_dual_recovery_is_exact_and_fail_closed(
        self,
    ) -> None:
        _msh, cell_tags, V, compiled = _two_cell_problem(
            distinct_materials=True
        )
        auxiliary_count = 2
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            appended_global_rows=auxiliary_count,
            appended_support_owned_cell_groups=(
                np.arange(2, dtype=np.int32),
            ),
            appended_support_group_by_row=(0, 0),
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        all_rows = np.arange(candidate.full_rows, dtype=PETSc.IntType)
        full_dense = np.asarray(
            full.getValues(all_rows, all_rows),
            dtype=np.complex128,
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
        rng = np.random.default_rng(2026072404)
        left_values = (
            rng.standard_normal((auxiliary_count, candidate.full_rows))
            + 1j
            * rng.standard_normal(
                (auxiliary_count, candidate.full_rows)
            )
        )
        left_vectors: list[PETSc.Vec] = []
        row_scales = np.asarray(
            (0.7 - 0.2j, -0.4 + 0.5j),
            dtype=np.complex128,
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "appended interior coupling rows are incomplete",
        ):
            recover_full_dual_from_active_trace(
                candidate,
                np.zeros(
                    candidate.active_rows + auxiliary_count,
                    dtype=np.complex128,
                ),
            )
        for auxiliary in range(auxiliary_count):
            vector = full.createVecLeft()
            _set_owned_values(vector, left_values[auxiliary])
            left_vectors.append(vector)
            register_appended_dual_interior_coupling(
                candidate,
                auxiliary,
                (vector,),
                (1.0 + 0.0j,),
                row_scale=row_scales[auxiliary],
            )

        with self.assertRaisesRegex(
            ValueError,
            "active trace and every appended row",
        ):
            recover_full_dual_from_active_trace(
                candidate,
                np.zeros(candidate.active_rows, dtype=np.complex128),
            )
        right_coupling = (
            rng.standard_normal(
                (candidate.full_rows, auxiliary_count)
            )
            + 1j
            * rng.standard_normal(
                (candidate.full_rows, auxiliary_count)
            )
        )
        left_coupling = np.asarray(
            [
                row_scales[row] * np.conj(left_values[row])
                for row in range(auxiliary_count)
            ],
            dtype=np.complex128,
        )
        auxiliary_block = np.asarray(
            (
                (1.1 + 0.4j, -0.3 + 0.2j),
                (0.6 - 0.7j, 0.9 - 0.1j),
            ),
            dtype=np.complex128,
        )
        augmented = np.block(
            [
                [full_dense, right_coupling],
                [left_coupling, auxiliary_block],
            ]
        )
        kept = np.concatenate(
            (
                trace,
                candidate.full_rows
                + np.arange(auxiliary_count, dtype=np.int64),
            )
        )
        reduced = (
            augmented[np.ix_(kept, kept)]
            - augmented[np.ix_(kept, interior)]
            @ np.linalg.solve(
                augmented[np.ix_(interior, interior)],
                augmented[np.ix_(interior, kept)],
            )
        )
        reduced_dual = (
            rng.standard_normal(len(kept))
            + 1j * rng.standard_normal(len(kept))
        )
        recovered_fe = recover_full_dual_from_active_trace(
            candidate,
            reduced_dual,
        )
        full_dual = np.concatenate(
            (
                np.asarray(
                    recovered_fe.getArray(readonly=True),
                    dtype=np.complex128,
                ),
                reduced_dual[candidate.active_rows :],
            )
        )
        full_adjoint_action = augmented.conj().T @ full_dual
        self.assertLess(
            np.linalg.norm(full_adjoint_action[interior]),
            3.0e-10,
        )
        np.testing.assert_allclose(
            full_adjoint_action[kept],
            reduced.conj().T @ reduced_dual,
            rtol=4.0e-12,
            atol=4.0e-10,
        )

        reduced_primal = (
            rng.standard_normal(len(kept))
            + 1j * rng.standard_normal(len(kept))
        )
        full_primal = np.zeros(
            candidate.full_rows + auxiliary_count,
            dtype=np.complex128,
        )
        full_primal[kept] = reduced_primal
        full_primal[interior] = -np.linalg.solve(
            augmented[np.ix_(interior, interior)],
            augmented[np.ix_(interior, kept)] @ reduced_primal,
        )
        self.assertLess(
            abs(
                np.vdot(full_dual, augmented @ full_primal)
                - np.vdot(reduced_dual, reduced @ reduced_primal)
            )
            / max(
                abs(np.vdot(reduced_dual, reduced @ reduced_primal)),
                1.0e-30,
            ),
            5.0e-12,
        )
        context = assembly_time.assembly_time_dual_recovery_context(
            candidate
        )
        self.assertTrue(context["exact_augmented_interior_coupling"])
        self.assertEqual(
            context["appended_coupling_rows_registered"],
            auxiliary_count,
        )
        self.assertEqual(
            context["appended_nonzero_cell_blocks_global"],
            auxiliary_count * 2,
        )
        self.assertGreater(
            context["appended_recovery_storage_bytes_global"],
            0,
        )

        recovered_fe.destroy()
        for vector in left_vectors:
            vector.destroy()
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

        dual_active_values = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        dual_full = recover_full_dual_from_active_trace(
            candidate,
            dual_active_values,
        )
        full_action = unconstrained.createVecLeft()
        unconstrained.mult(x, full_action)
        full_adjoint_action = unconstrained.createVecRight()
        unconstrained.multHermitian(dual_full, full_adjoint_action)
        self.assertLess(
            float(
                np.linalg.norm(
                    full_adjoint_action.getValues(
                        np.asarray(
                            np.concatenate(interior_rows),
                            dtype=PETSc.IntType,
                        )
                    )
                )
            ),
            2.0e-10,
        )
        active_primal = candidate.matrix.createVecRight()
        active_dual = candidate.matrix.createVecLeft()
        _set_owned_values(active_primal, active_values)
        _set_owned_values(active_dual, dual_active_values)
        reduced_action = candidate.matrix.createVecLeft()
        candidate.matrix.mult(active_primal, reduced_action)
        self.assertLess(
            abs(dual_full.dot(full_action) - active_dual.dot(reduced_action))
            / max(abs(active_dual.dot(reduced_action)), 1.0e-30),
            3.0e-12,
        )
        slave_value = complex(
            dual_full.getValues(
                np.asarray([slave], dtype=PETSc.IntType)
            )[0]
        )
        master_active = (
            candidate.trace_constraints.original_to_active[master]
        )
        self.assertAlmostEqual(
            slave_value,
            coefficient * dual_active_values[master_active],
            places=12,
        )

        reduced_action.destroy()
        active_dual.destroy()
        active_primal.destroy()
        full_adjoint_action.destroy()
        full_action.destroy()
        dual_full.destroy()
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
        self.assertEqual(
            candidate.build_audit["raw_tensor_class_count_sum"],
            1,
        )
        self.assertEqual(
            candidate.build_audit["raw_tensor_class_count_global_unique"],
            1,
        )
        self.assertEqual(
            candidate.build_audit["raw_tensor_class_use_count_sum"],
            2,
        )
        self.assertTrue(
            candidate.build_audit["raw_tensor_cross_rank_dedup_active"]
        )
        self.assertTrue(
            candidate.build_audit[
                "raw_tensor_policy_signatures_identical"
            ]
        )
        matrix_info = candidate.matrix.getInfo(
            PETSc.Mat.InfoType.GLOBAL_SUM
        )
        self.assertEqual(matrix_info["mallocs"], 0.0)
        self.assertEqual(matrix_info["nz_unneeded"], 0.0)

        rng = np.random.default_rng(2026072403)
        active_primal_values = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        active_dual_values = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        full_primal_values = np.zeros(
            candidate.full_rows,
            dtype=np.complex128,
        )
        for original, (active_ids, coefficients) in (
            candidate.trace_constraints.expansion_by_original.items()
        ):
            full_primal_values[original] = np.dot(
                coefficients,
                active_primal_values[active_ids],
            )
        for rows, values in recover_owned_cell_interiors(
            candidate,
            active_primal_values,
        ):
            full_primal_values[rows] = values
        full_primal = full.createVecRight()
        _set_owned_values(full_primal, full_primal_values)
        full_dual = recover_full_dual_from_active_trace(
            candidate,
            active_dual_values,
        )
        full_action = full.createVecLeft()
        full.mult(full_primal, full_action)
        full_adjoint_action = full.createVecRight()
        full.multHermitian(full_dual, full_adjoint_action)
        local_interior = np.concatenate(
            [
                cell.interior_original_dofs
                for cell in candidate.cell_recovery_maps
            ]
        )
        local_dual_residual = float(
            np.linalg.norm(
                full_adjoint_action.getValues(
                    np.asarray(local_interior, dtype=PETSc.IntType)
                )
            )
        )
        self.assertLess(
            comm.allreduce(local_dual_residual, op=MPI.MAX),
            2.0e-10,
        )

        reduced_primal = candidate.matrix.createVecRight()
        reduced_dual = candidate.matrix.createVecLeft()
        _set_owned_values(reduced_primal, active_primal_values)
        _set_owned_values(reduced_dual, active_dual_values)
        reduced_action = candidate.matrix.createVecLeft()
        candidate.matrix.mult(reduced_primal, reduced_action)
        reduced_adjoint_action = candidate.matrix.createVecRight()
        candidate.matrix.multHermitian(
            reduced_dual,
            reduced_adjoint_action,
        )
        full_pairing = complex(full_dual.dot(full_action))
        reduced_pairing = complex(reduced_dual.dot(reduced_action))
        self.assertLess(
            abs(full_pairing - reduced_pairing)
            / max(abs(reduced_pairing), 1.0e-30),
            3.0e-12,
        )
        owned_active_original = (
            candidate.trace_constraints.owned_active_original_dofs
        )
        owned_active_ids = np.asarray(
            [
                candidate.trace_constraints.original_to_active[
                    int(original)
                ]
                for original in owned_active_original
            ],
            dtype=PETSc.IntType,
        )
        local_trace_error = float(
            np.max(
                np.abs(
                    full_adjoint_action.getValues(
                        owned_active_original
                    )
                    - reduced_adjoint_action.getValues(
                        owned_active_ids
                    )
                ),
                initial=0.0,
            )
        )
        self.assertLess(
            comm.allreduce(local_trace_error, op=MPI.MAX),
            3.0e-11,
        )

        reduced_adjoint_action.destroy()
        reduced_action.destroy()
        reduced_dual.destroy()
        reduced_primal.destroy()
        full_adjoint_action.destroy()
        full_action.destroy()
        full_dual.destroy()
        full_primal.destroy()
        difference.destroy()
        manual_difference.destroy()
        manual_full.destroy()
        reference.destroy()
        zero_rhs.destroy()
        full.destroy()
        candidate.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 augmented Hermitian dual recovery check",
    )
    def test_mpi2_augmented_dual_recovery_closes_full_schur_pairing(
        self,
    ) -> None:
        comm = MPI.COMM_WORLD
        msh = mesh.create_unit_cube(
            comm,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        tdim = msh.topology.dim
        owned_cells = int(msh.topology.index_map(tdim).size_local)
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
        compiled = fem.form(
            (
                ufl.inner(ufl.curl(u), ufl.curl(v))
                + PETSc.ScalarType(2.2 - 0.3j) * ufl.inner(u, v)
            )
            * ufl.dx
        )
        candidate = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            appended_global_rows=1,
            appended_support_owned_cell_groups=(
                np.arange(owned_cells, dtype=np.int32),
            ),
            appended_support_group_by_row=(0,),
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        rng = np.random.default_rng(2026072405)
        left_values = (
            rng.standard_normal(candidate.full_rows)
            + 1j * rng.standard_normal(candidate.full_rows)
        )
        right_values = (
            rng.standard_normal(candidate.full_rows)
            + 1j * rng.standard_normal(candidate.full_rows)
        )
        left = full.createVecLeft()
        right = full.createVecRight()
        _set_owned_values(left, left_values)
        _set_owned_values(right, right_values)
        row_scale = 0.6 - 0.35j
        auxiliary_diagonal = 1.2 + 0.45j
        register_appended_dual_interior_coupling(
            candidate,
            0,
            (left,),
            (1.0 + 0.0j,),
            row_scale=row_scale,
        )
        reduced_left = condense_unconstrained_vector_to_active_trace(
            candidate,
            left,
            side="left",
        )
        reduced_right = condense_unconstrained_vector_to_active_trace(
            candidate,
            right,
            side="right",
        )
        interior_bilinear = cell_interior_schur_bilinear(
            candidate,
            left,
            right,
        )
        auxiliary_schur = (
            auxiliary_diagonal - row_scale * interior_bilinear
        )

        reduced_dual_values = (
            rng.standard_normal(candidate.active_rows + 1)
            + 1j * rng.standard_normal(candidate.active_rows + 1)
        )
        z_aux = complex(reduced_dual_values[-1])
        recovered_dual = recover_full_dual_from_active_trace(
            candidate,
            reduced_dual_values,
        )
        full_adjoint_action = full.createVecRight()
        full.multHermitian(recovered_dual, full_adjoint_action)
        full_adjoint_action.axpy(
            PETSc.ScalarType(np.conj(row_scale) * z_aux),
            left,
        )
        local_interior = np.concatenate(
            [
                cell.interior_original_dofs
                for cell in candidate.cell_recovery_maps
            ]
        )
        local_interior_error = float(
            np.linalg.norm(
                full_adjoint_action.getValues(
                    np.asarray(local_interior, dtype=PETSc.IntType)
                )
            )
        )
        self.assertLess(
            comm.allreduce(local_interior_error, op=MPI.MAX),
            3.0e-10,
        )

        reduced_dual = candidate.matrix.createVecLeft()
        _set_owned_values(reduced_dual, reduced_dual_values)
        reduced_adjoint_action = candidate.matrix.createVecRight()
        candidate.matrix.multHermitian(
            reduced_dual,
            reduced_adjoint_action,
        )
        reduced_adjoint_action.axpy(
            PETSc.ScalarType(np.conj(row_scale) * z_aux),
            reduced_left,
        )
        owned_active_original = (
            candidate.trace_constraints.owned_active_original_dofs
        )
        owned_active_ids = np.asarray(
            [
                candidate.trace_constraints.original_to_active[
                    int(original)
                ]
                for original in owned_active_original
            ],
            dtype=PETSc.IntType,
        )
        local_trace_error = float(
            np.max(
                np.abs(
                    full_adjoint_action.getValues(
                        owned_active_original
                    )
                    - reduced_adjoint_action.getValues(
                        owned_active_ids
                    )
                ),
                initial=0.0,
            )
        )
        self.assertLess(
            comm.allreduce(local_trace_error, op=MPI.MAX),
            4.0e-10,
        )
        full_right_pairing = recovered_dual.dot(right)
        reduced_right_pairing = reduced_dual.dot(reduced_right)
        full_auxiliary_adjoint = (
            full_right_pairing
            + np.conj(auxiliary_diagonal) * z_aux
        )
        reduced_auxiliary_adjoint = (
            reduced_right_pairing
            + np.conj(auxiliary_schur) * z_aux
        )
        self.assertLess(
            abs(full_auxiliary_adjoint - reduced_auxiliary_adjoint),
            5.0e-10,
        )

        reduced_primal_values = (
            rng.standard_normal(candidate.active_rows + 1)
            + 1j * rng.standard_normal(candidate.active_rows + 1)
        )
        x_aux = complex(reduced_primal_values[-1])
        full_primal_values = np.zeros(
            candidate.full_rows,
            dtype=np.complex128,
        )
        for original, (active_ids, coefficients) in (
            candidate.trace_constraints.expansion_by_original.items()
        ):
            full_primal_values[original] = np.dot(
                coefficients,
                reduced_primal_values[active_ids],
            )
        interior_rhs = right.copy()
        interior_rhs.scale(PETSc.ScalarType(-x_aux))
        for rows, values in recover_owned_cell_interiors(
            candidate,
            reduced_primal_values[: candidate.active_rows],
            full_rhs=interior_rhs,
        ):
            full_primal_values[rows] = values
        full_primal = full.createVecRight()
        _set_owned_values(full_primal, full_primal_values)
        full_action = full.createVecLeft()
        full.mult(full_primal, full_action)
        full_action.axpy(PETSc.ScalarType(x_aux), right)
        full_auxiliary_action = (
            row_scale * full_primal.dot(left)
            + auxiliary_diagonal * x_aux
        )
        full_pairing = (
            full_action.dot(recovered_dual)
            + np.conj(z_aux) * full_auxiliary_action
        )

        reduced_primal = candidate.matrix.createVecRight()
        _set_owned_values(reduced_primal, reduced_primal_values)
        reduced_action = candidate.matrix.createVecLeft()
        candidate.matrix.mult(reduced_primal, reduced_action)
        reduced_action.axpy(PETSc.ScalarType(x_aux), reduced_right)
        reduced_auxiliary_action = (
            row_scale * reduced_primal.dot(reduced_left)
            + auxiliary_schur * x_aux
        )
        reduced_pairing = (
            reduced_action.dot(reduced_dual)
            + np.conj(z_aux) * reduced_auxiliary_action
        )
        self.assertLess(
            abs(full_pairing - reduced_pairing)
            / max(abs(reduced_pairing), 1.0e-30),
            6.0e-12,
        )
        context = assembly_time.assembly_time_dual_recovery_context(
            candidate
        )
        self.assertTrue(context["exact_augmented_interior_coupling"])
        self.assertEqual(
            context["appended_nonzero_cell_blocks_global"],
            2,
        )
        self.assertGreater(
            context["appended_recovery_storage_bytes_global"],
            0,
        )

        reduced_action.destroy()
        reduced_primal.destroy()
        full_action.destroy()
        full_primal.destroy()
        interior_rhs.destroy()
        reduced_adjoint_action.destroy()
        reduced_dual.destroy()
        full_adjoint_action.destroy()
        recovered_dual.destroy()
        reduced_right.destroy()
        reduced_left.destroy()
        right.destroy()
        left.destroy()
        full.destroy()
        candidate.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 collective raw-tensor owner failure check",
    )
    def test_mpi2_raw_tensor_owner_failure_is_collective(self) -> None:
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
        compiled = fem.form(ufl.inner(u, v) * dx(1))
        original = assembly_time._tabulate_raw_tensor_class

        def injected_failure(*args, **kwargs):
            raise RuntimeError("injected owner failure")

        replacement = injected_failure if comm.rank == 0 else original
        with mock.patch.object(
            assembly_time,
            "_tabulate_raw_tensor_class",
            replacement,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "rank 0: RuntimeError: injected owner failure",
            ):
                build_unconstrained_assembly_time_condensation(
                    compiled,
                    V,
                    cell_tags,
                )

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 collective trace-preallocation validation check",
    )
    def test_mpi2_preallocation_input_failure_is_collective(self) -> None:
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
        compiled = fem.form(ufl.inner(u, v) * dx(1))
        support_cell = owned_cells if comm.rank == 0 else 0
        with self.assertRaisesRegex(
            ValueError,
            (
                "rank 0: ValueError: appended support group contains "
                "a non-owned cell"
            ),
        ):
            build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                appended_global_rows=1,
                appended_support_owned_cell_groups=(
                    np.asarray([support_cell], dtype=np.int32),
                ),
                appended_support_group_by_row=(0,),
                defer_final_assembly=True,
            )

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
        self.assertEqual(
            summary["matrix_stats"]["matrix_mallocs"],
            0.0,
        )
        self.assertGreaterEqual(
            summary["matrix_stats"]["matrix_nnz_allocated"],
            summary["matrix_stats"]["matrix_nnz_used"],
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
        preallocation = audit["trace_preallocation"]
        self.assertTrue(
            preallocation["new_nonzero_allocation_error_enabled"]
        )
        self.assertEqual(
            preallocation["preallocated_structural_nnz"],
            summary["matrix_stats"]["matrix_nnz_allocated"],
        )

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

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 p5-trace/p4-low/p6-high end-to-end check",
    )
    def test_mpi2_end_to_end_mixed_trace_and_interior_orders(self) -> None:
        cfg = replace(
            target_stage4_config(degree=6, h_nm=100.0),
            case_name="task035b_p5trace_p4low_p6high_smoke_mpi2",
            nedelec_trace_degree=5,
            nedelec_interior_degree=6,
            stage4_regionwise_low_interior_degree=4,
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
            Path("/tmp/task035b_p5trace_p4low_p6high_smoke_mpi2"),
        )
        self.assertEqual(summary["case_status"], "completed")
        self.assertTrue(summary["official_result"])
        self.assertLessEqual(
            summary["linear_system_relative_residual"],
            1.0e-9,
        )
        audit = summary["cell_static_condensation"]
        self.assertEqual(audit["regionwise_trace_degree"], 5)
        self.assertEqual(audit["regionwise_low_interior_degree"], 4)
        self.assertEqual(audit["regionwise_high_interior_degree"], 6)
        self.assertEqual(audit["regionwise_high_cell_count"], 1)
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
        self.assertFalse(audit["full_trace_matrix_allocated"])
        for observable in ("R00_total", "R_total", "T_total"):
            self.assertTrue(np.isfinite(summary[observable]), observable)

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 fixed p5-trace/p6-interior end-to-end check",
    )
    def test_mpi2_end_to_end_fixed_p5_trace_p6_interior(self) -> None:
        cfg = replace(
            target_stage4_config(degree=6, h_nm=100.0),
            case_name="task035b_fixed_p5trace_p6interior_smoke_mpi2",
            nedelec_trace_degree=5,
            nedelec_interior_degree=6,
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
            Path("/tmp/task035b_fixed_p5trace_p6interior_smoke_mpi2"),
        )
        self.assertEqual(summary["case_status"], "completed")
        self.assertTrue(summary["official_result"])
        self.assertEqual(
            summary["config"]["nedelec_trace_degree_resolved"],
            5,
        )
        self.assertEqual(
            summary["config"]["nedelec_interior_degree_resolved"],
            6,
        )
        self.assertLessEqual(
            summary["linear_system_relative_residual"],
            1.0e-9,
        )
        audit = summary["cell_static_condensation"]
        self.assertFalse(audit["regionwise_interior_p_active"])
        self.assertEqual(audit["full_rows"], summary["num_nedelec_dofs"])
        self.assertEqual(
            summary["matrix_stats"]["matrix_rows"],
            audit["active_rows"] + audit["appended_rows"],
        )
        self.assertFalse(audit["full_global_matrix_allocated"])
        self.assertFalse(audit["full_trace_matrix_allocated"])
        self.assertIsInstance(
            audit["full_explicit_true_residual"][
                "eliminated_cell_interior_residual_norm"
            ],
            float,
        )
        for observable in ("R00_total", "R_total", "T_total"):
            self.assertTrue(np.isfinite(summary[observable]), observable)


if __name__ == "__main__":
    unittest.main()
