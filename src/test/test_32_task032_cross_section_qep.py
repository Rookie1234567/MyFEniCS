from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.constraints.cross_section_floquet import (
    build_cross_section_floquet_constraints,
    build_distributed_constraint_transform,
)
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)


class Task032CrossSectionSpaceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = target_stage4_config(degree=2, h_nm=5.0)

    def test_matching_mesh_and_material_contract(self):
        plan = stage4_axis_plan(self.cfg, MPI.COMM_WORLD.size)
        air = build_matching_cross_section(self.cfg, "air")
        lossy = build_matching_cross_section(self.cfg, "lossy_homogeneous")
        patterned = build_matching_cross_section(self.cfg, "stage4_xy")

        np.testing.assert_allclose(air.x_values, plan.x_values, atol=0.0, rtol=0.0)
        np.testing.assert_allclose(air.y_values, plan.y_values, atol=0.0, rtol=0.0)
        self.assertEqual(air.mesh_cells, plan.mesh_cells_resolved[:2])
        self.assertTrue(np.allclose(air.epsilon_r.x.array, self.cfg.n_air**2))
        self.assertTrue(np.allclose(lossy.epsilon_r.x.array, self.cfg.n_grating**2))

        local_values = np.asarray(patterned.epsilon_r.x.array)
        local_grating = int(np.count_nonzero(np.isclose(local_values, self.cfg.n_grating**2)))
        local_air = int(np.count_nonzero(np.isclose(local_values, self.cfg.n_air**2)))
        global_grating = MPI.COMM_WORLD.allreduce(local_grating, op=MPI.SUM)
        global_air = MPI.COMM_WORLD.allreduce(local_air, op=MPI.SUM)
        self.assertGreater(global_grating, 0)
        self.assertGreater(global_air, 0)

    def test_double_floquet_constraint_transform_is_distributed_and_chain_free(self):
        cross_section = build_matching_cross_section(self.cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        constraints = build_cross_section_floquet_constraints(
            cross_section,
            spaces,
            kx=self.cfg.kx,
            ky=self.cfg.ky,
        )
        transform = build_distributed_constraint_transform(spaces, constraints)

        expected_phase_x = np.exp(1j * self.cfg.kx * self.cfg.period_x)
        expected_phase_y = np.exp(1j * self.cfg.ky * self.cfg.period_y)
        self.assertAlmostEqual(abs(constraints.phase_x - expected_phase_x), 0.0, places=12)
        self.assertAlmostEqual(abs(constraints.phase_y - expected_phase_y), 0.0, places=12)
        self.assertLess(constraints.max_pair_coordinate_error, 1.0e-12)
        self.assertLess(constraints.max_probe_residual, 1.0e-10)
        self.assertGreater(constraints.transverse_constraint_count, 0)
        self.assertGreater(constraints.longitudinal_constraint_count, 0)

        global_slaves = np.asarray(
            sorted(
                value
                for values in MPI.COMM_WORLD.allgather(constraints.slave_global.tolist())
                for value in values
            ),
            dtype=np.int64,
        )
        self.assertEqual(transform.global_slave_count, len(global_slaves))
        self.assertEqual(
            transform.reduced_global_size,
            transform.full_global_size - transform.global_slave_count,
        )

        def reduced_index(global_dof: int) -> int:
            return int(global_dof - np.searchsorted(global_slaves, global_dof, side="left"))

        for row, slave in enumerate(constraints.slave_global):
            columns, values = transform.matrix.getRow(int(slave))
            start = int(constraints.offsets[row])
            stop = int(constraints.offsets[row + 1])
            expected_columns = np.asarray(
                [reduced_index(int(master)) for master in constraints.master_global[start:stop]],
                dtype=np.int32,
            )
            order = np.argsort(columns)
            expected_order = np.argsort(expected_columns)
            np.testing.assert_array_equal(columns[order], expected_columns[expected_order])
            np.testing.assert_allclose(
                values[order],
                constraints.coefficients[start:stop][expected_order],
                atol=1.0e-12,
                rtol=1.0e-12,
            )
        transform.matrix.destroy()


class Task032QuadraticBetaEigenproblemTests(unittest.TestCase):
    @staticmethod
    def _destroy_modes(modes):
        for mode in modes:
            mode.destroy()

    def _build_operators(self, material_kind: str, h_nm: float):
        cfg = target_stage4_config(degree=2, h_nm=h_nm)
        cross_section = build_matching_cross_section(cfg, material_kind)
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        return cfg, operators

    def test_air_qep_matches_analytic_beta_pairs_and_normalizes(self):
        cfg, operators = self._build_operators("air", h_nm=2.0)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        positive, positive_report = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        negative, negative_report = solve_quadratic_beta_modes(
            operators, target=-target, requested_modes=2
        )
        try:
            self.assertEqual(operators.scalar_dtype, "complex128")
            self.assertEqual(operators.K0.getSize(), operators.K1.getSize())
            self.assertEqual(operators.K0.getSize(), operators.K2.getSize())
            self.assertEqual(operators.K0.getSize(), operators.electric_mass.getSize())
            self.assertEqual(operators.reduced_shape[0], operators.reduced_shape[1])
            self.assertLess(operators.reduced_shape[0], operators.full_shape[0])
            self.assertTrue(operators.leading_coefficient_singular_by_design)
            self.assertGreater(positive_report.converged_modes, 0)
            self.assertGreater(negative_report.converged_modes, 0)
            self.assertLessEqual(
                len(positive), positive_report.requested_modes
            )
            self.assertLessEqual(
                len(negative), negative_report.requested_modes
            )

            plus = min(positive, key=lambda mode: abs(mode.beta - target))
            minus = min(negative, key=lambda mode: abs(mode.beta + target))
            self.assertLess(abs(plus.beta - target) / abs(target), 1.5e-2)
            self.assertLess(abs(plus.beta + minus.beta) / abs(target), 1.0e-9)
            for mode in (plus, minus):
                self.assertLess(mode.polynomial_relative_residual, 1.0e-10)
                self.assertLess(mode.slepc_relative_error, 1.0e-8)
                self.assertAlmostEqual(mode.electric_l2_norm_after, 1.0, places=11)
                self.assertEqual(mode.normalization_kind, "cross_section_electric_L2")
                self.assertFalse(mode.ownership.gathered_to_root)
                self.assertEqual(mode.ownership.comm_size, MPI.COMM_WORLD.size)
                global_reduced = MPI.COMM_WORLD.allreduce(
                    mode.ownership.reduced_local_size, op=MPI.SUM
                )
                global_full = MPI.COMM_WORLD.allreduce(
                    mode.ownership.full_local_size, op=MPI.SUM
                )
                self.assertEqual(global_reduced, operators.reduced_shape[0])
                self.assertEqual(global_full, operators.full_shape[0])
        finally:
            self._destroy_modes(positive)
            self._destroy_modes(negative)
            operators.destroy()

    def test_lossy_homogeneous_qep_matches_complex_branch(self):
        cfg, operators = self._build_operators("lossy_homogeneous", h_nm=2.0)
        target = analytic_homogeneous_beta(cfg, cfg.n_grating)
        modes, report = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        try:
            self.assertGreater(report.converged_modes, 0)
            mode = min(modes, key=lambda candidate: abs(candidate.beta - target))
            self.assertGreater(mode.beta.real, 0.0)
            self.assertGreater(mode.beta.imag, 0.0)
            self.assertLess(abs(mode.beta - target) / abs(target), 2.0e-2)
            self.assertLess(mode.polynomial_relative_residual, 1.0e-10)
            self.assertAlmostEqual(mode.electric_l2_norm_after, 1.0, places=11)
        finally:
            self._destroy_modes(modes)
            operators.destroy()

    def test_patterned_cross_section_has_resolved_reciprocal_pair(self):
        cfg, operators = self._build_operators("stage4_xy", h_nm=3.0)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        positive, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        negative, _ = solve_quadratic_beta_modes(
            operators, target=-target, requested_modes=2
        )
        try:
            plus = min(positive, key=lambda mode: abs(mode.beta - target))
            minus = min(negative, key=lambda mode: abs(mode.beta + target))
            self.assertGreater(plus.beta.real, 0.0)
            self.assertGreater(plus.beta.imag, 0.0)
            self.assertLess(abs(plus.beta + minus.beta), 1.0e-10)
            self.assertLess(plus.polynomial_relative_residual, 1.0e-10)
            self.assertLess(minus.polynomial_relative_residual, 1.0e-10)
        finally:
            self._destroy_modes(positive)
            self._destroy_modes(negative)
            operators.destroy()


if __name__ == "__main__":
    unittest.main()
