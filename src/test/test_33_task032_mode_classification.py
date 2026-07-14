from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    build_biorthogonal_mode_basis,
    classify_mode_branch,
    pair_reciprocal_mode_bases,
    track_mode_bases,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.modes.stable_propagation import (
    build_two_sided_propagation,
    diagnose_reciprocity_and_passivity,
)


class Task032ModeClassificationTests(unittest.TestCase):
    @staticmethod
    def _build_air_basis(*, theta_deg: float, requested_modes: int):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cfg.incident_theta_deg = float(theta_deg)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        right_modes, _ = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=requested_modes,
        )
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=requested_modes,
        )
        return cfg, cross_section, spaces, operators, target, basis

    def test_branch_rules_cover_flux_evanescent_and_cutoff(self):
        self.assertEqual(
            classify_mode_branch(1.0 + 0.01j, 2.0, 1.0e-8, 1.0e-10),
            ("lossy_propagating", "forward", "poynting_flux", True),
        )
        self.assertEqual(
            classify_mode_branch(-1.0 - 0.01j, -2.0, 1.0e-8, 1.0e-10),
            ("lossy_propagating", "backward", "poynting_flux", True),
        )
        self.assertEqual(
            classify_mode_branch(0.0 + 0.4j, 0.0, 1.0e-8, 1.0e-10),
            ("evanescent", "forward", "positive_imag_beta_decay", True),
        )
        self.assertEqual(
            classify_mode_branch(0.0 - 0.4j, 0.0, 1.0e-8, 1.0e-10),
            ("evanescent", "backward", "negative_imag_beta_decay", True),
        )
        self.assertEqual(
            classify_mode_branch(0.0 + 0.0j, 0.0, 1.0e-8, 1.0e-10),
            (
                "cutoff_or_near_zero_flux",
                "ambiguous",
                "near_zero_flux_and_beta_imag",
                False,
            ),
        )

    def test_air_modes_use_poynting_and_adjoint_qep_biorthogonality(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        positive_right, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        negative_right = None
        if MPI.COMM_WORLD.size == 1:
            negative_right, _ = solve_quadratic_beta_modes(
                operators, target=-target, requested_modes=2
            )
        positive = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
        )
        negative = None
        if negative_right is not None:
            negative = build_biorthogonal_mode_basis(
                cfg,
                cross_section,
                spaces,
                operators,
                negative_right,
                adjoint_target=-np.conj(target),
                requested_left_modes=2,
            )
        try:
            self.assertEqual(len(positive.modes), 2)
            self.assertFalse(positive.full_vector_gathered)
            self.assertLess(positive.max_identity_error, 1.0e-8)
            self.assertTrue(any(len(group.indices) == 2 for group in positive.groups))
            for mode in positive.modes:
                self.assertEqual(mode.direction, "forward")
                self.assertEqual(mode.classification_basis, "poynting_flux")
                self.assertTrue(mode.passive_branch_valid)
                self.assertAlmostEqual(
                    mode.poynting_z_after_normalization, 1.0, places=9
                )
                self.assertLess(mode.left_polynomial_relative_residual, 1.0e-8)
                self.assertLess(abs(mode.qprime_overlap_after - 1.0), 1.0e-8)
                self.assertFalse(mode.left_ownership.gathered_to_root)
                self.assertEqual(
                    MPI.COMM_WORLD.allreduce(
                        mode.left_ownership.reduced_local_size, op=MPI.SUM
                    ),
                    operators.reduced_shape[0],
                )
                self.assertEqual(
                    MPI.COMM_WORLD.allreduce(
                        mode.left_ownership.full_local_size, op=MPI.SUM
                    ),
                    operators.full_shape[0],
                )
            if negative is not None:
                self.assertEqual(len(negative.modes), 2)
                self.assertLess(negative.max_identity_error, 1.0e-8)
                for mode in negative.modes:
                    self.assertEqual(mode.direction, "backward")
                    self.assertTrue(mode.passive_branch_valid)
                    self.assertAlmostEqual(
                        mode.poynting_z_after_normalization, -1.0, places=9
                    )
                    self.assertLess(mode.left_polynomial_relative_residual, 1.0e-8)

                pairs = pair_reciprocal_mode_bases(operators, positive, negative)
                self.assertEqual(len(pairs), 2)
                for pair in pairs:
                    self.assertLess(pair.relative_beta_error, 1.0e-8)
                    self.assertGreater(pair.electric_mass_overlap, 0.5)
                    self.assertTrue(pair.opposite_direction)
                    self.assertTrue(pair.passive_branches_valid)

                propagation = build_two_sided_propagation(
                    [*positive.modes, *negative.modes], 100.0
                )
                propagation_report = diagnose_reciprocity_and_passivity(propagation)
                self.assertTrue(propagation.passivity_valid)
                self.assertTrue(propagation_report.reciprocity_valid)
                self.assertLessEqual(propagation.max_factor_magnitude, 1.0)
                self.assertEqual(propagation.stored_complex_scalars, 4)
        finally:
            positive.destroy()
            if negative is not None:
                negative.destroy()
            operators.destroy()

    @unittest.skipIf(
        MPI.COMM_WORLD.size > 1,
        "lossy branch is covered by the formal MPI benchmark",
    )
    def test_lossy_modes_use_complex_adjoint_branch(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cfg, "lossy_homogeneous")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_grating)
        right_modes, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
        )
        try:
            self.assertLess(basis.max_identity_error, 1.0e-7)
            for mode in basis.modes:
                self.assertGreater(mode.beta.imag, 0.0)
                self.assertEqual(mode.kind, "lossy_propagating")
                self.assertEqual(mode.direction, "forward")
                self.assertTrue(mode.passive_branch_valid)
                self.assertAlmostEqual(
                    mode.poynting_z_after_normalization, 1.0, places=8
                )
                self.assertLess(mode.left_polynomial_relative_residual, 1.0e-8)
        finally:
            basis.destroy()
            operators.destroy()

    @unittest.skipIf(
        MPI.COMM_WORLD.size > 1,
        "adjacent-parameter tracking is a serial small-dense contract",
    )
    def test_overlap_tracking_handles_angle_change_and_mode_count_change(self):
        _, _, _, operators_previous, _, previous = self._build_air_basis(
            theta_deg=80.0, requested_modes=2
        )
        _, _, _, operators_current, _, current = self._build_air_basis(
            theta_deg=79.8, requested_modes=3
        )
        try:
            report = track_mode_bases(operators_current, previous, current)
            self.assertEqual(len(report.matches), 2)
            self.assertEqual(report.unmatched_previous, ())
            self.assertGreaterEqual(len(report.unmatched_current), 1)
            self.assertTrue(all(match.overlap > 0.5 for match in report.matches))
            self.assertTrue(report.subspaces)
            self.assertLess(report.subspaces[0].max_principal_angle_rad, 0.2)
        finally:
            previous.destroy()
            current.destroy()
            operators_previous.destroy()
            operators_current.destroy()


if __name__ == "__main__":
    unittest.main()
