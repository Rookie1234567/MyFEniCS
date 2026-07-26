from __future__ import annotations

from dataclasses import dataclass
import unittest

import numpy as np

from src.modes.stable_propagation import (
    _scalar_cg_reference_matrices,
    build_two_sided_propagation,
    diagnose_reciprocity_and_passivity,
    full3d_uniform_cg_discrete_beta,
    scalar_cg_discrete_traction_beta,
)


@dataclass(frozen=True)
class _SyntheticMode:
    beta: complex
    direction: str
    passive_branch_valid: bool = True


def _reciprocal_modes(*forward_beta: complex) -> list[_SyntheticMode]:
    return [
        *(_SyntheticMode(beta, "forward") for beta in forward_beta),
        *(_SyntheticMode(-beta, "backward") for beta in forward_beta),
    ]


class Task032StablePropagationTests(unittest.TestCase):
    def test_full3d_uniform_cg2_matches_axial_dispersion_reference(self):
        expected_phase_corrections = {
            0.0557: -2.317531607315404e-05,
            0.324456: -0.13485247283944735,
            0.416629: -0.42455442084429196,
            0.463140: -0.6744734820144815,
        }
        for beta, expected in expected_phase_corrections.items():
            effective = full3d_uniform_cg_discrete_beta(
                beta, degree=2, h_nm=5.0
            )
            self.assertAlmostEqual(
                (effective.real - beta) * 100.0, expected, places=12
            )
            self.assertAlmostEqual(effective.imag, 0.0, places=14)

    def test_full3d_uniform_cg_converges_to_continuous_small_q(self):
        beta = 0.02 + 0.001j
        errors = []
        for h_nm in (4.0, 2.0, 1.0):
            effective = full3d_uniform_cg_discrete_beta(
                beta, degree=2, h_nm=h_nm
            )
            errors.append(abs(effective - beta))
        self.assertLess(errors[1], errors[0] / 8.0)
        self.assertLess(errors[2], errors[1] / 8.0)

    def test_full3d_uniform_cg6_small_q_is_machine_close(self):
        beta = 0.02 + 0.001j
        for h_nm in (8.0, 4.0, 2.0, 1.0):
            effective = full3d_uniform_cg_discrete_beta(
                beta, degree=6, h_nm=h_nm
            )
            self.assertLess(abs(effective - beta), 1.0e-12)

    def test_full3d_uniform_cg_pole_and_stop_band_select_passive_root(self):
        pole = full3d_uniform_cg_discrete_beta(
            np.sqrt(10.0), degree=2, h_nm=1.0
        )
        self.assertAlmostEqual(pole.real, np.pi, places=14)
        self.assertAlmostEqual(pole.imag, 0.0, places=14)
        forward = full3d_uniform_cg_discrete_beta(
            3.25, degree=2, h_nm=1.0, direction="forward"
        )
        backward = full3d_uniform_cg_discrete_beta(
            -3.25, degree=2, h_nm=1.0, direction="backward"
        )
        self.assertAlmostEqual(forward.real, np.pi, places=14)
        self.assertGreater(forward.imag, 0.1)
        self.assertAlmostEqual(backward.real, -forward.real, places=14)
        self.assertAlmostEqual(backward.imag, -forward.imag, places=14)

    def test_scalar_cg_traction_symbol_is_reciprocal_and_convergent(self):
        beta = 0.324456 + 0.002j
        errors = []
        for h_nm in (5.0, 2.5, 1.25):
            forward = scalar_cg_discrete_traction_beta(
                beta,
                degree=2,
                h_nm=h_nm,
                direction="forward",
            )
            backward = scalar_cg_discrete_traction_beta(
                -beta,
                degree=2,
                h_nm=h_nm,
                direction="backward",
            )
            np.testing.assert_allclose(backward, -forward, rtol=1.0e-12)
            errors.append(abs(forward - beta))
        self.assertLess(errors[1], errors[0] / 8.0)
        self.assertLess(errors[2], errors[1] / 8.0)

    def test_scalar_cg_traction_matches_schur_away_from_resonance(self):
        for degree, beta in (
            (2, 0.324456 + 0.002j),
            (6, 0.416629 + 0.0003j),
        ):
            h_nm = 1.25
            mass, stiffness = _scalar_cg_reference_matrices(degree)
            q = beta * h_nm
            dynamic = stiffness.astype(np.complex128) - q * q * mass
            endpoints = np.asarray((0, degree), dtype=np.int64)
            interior = np.arange(1, degree, dtype=np.int64)
            schur = dynamic[np.ix_(endpoints, endpoints)].copy()
            if interior.size:
                schur -= dynamic[np.ix_(endpoints, interior)] @ np.linalg.solve(
                    dynamic[np.ix_(interior, interior)],
                    dynamic[np.ix_(interior, endpoints)],
                )
            effective = full3d_uniform_cg_discrete_beta(
                beta,
                degree=degree,
                h_nm=h_nm,
                direction="forward",
            )
            multiplier = np.exp(1j * effective * h_nm)
            expected = (
                1j * (schur[0, 0] + schur[0, 1] * multiplier) / h_nm
            )
            actual = scalar_cg_discrete_traction_beta(
                beta,
                degree=degree,
                h_nm=h_nm,
                direction="forward",
            )
            np.testing.assert_allclose(actual, expected, rtol=1.0e-10, atol=1.0e-12)

    def test_scalar_cg_traction_survives_near_p6_dirichlet_resonance(self):
        degree = 6
        mass, stiffness = _scalar_cg_reference_matrices(degree)
        interior = np.arange(1, degree, dtype=np.int64)
        interior_mass = mass[np.ix_(interior, interior)]
        interior_stiffness = stiffness[np.ix_(interior, interior)]
        eigenvalues = np.linalg.eigvals(
            np.linalg.solve(interior_mass, interior_stiffness)
        )
        first_pole = float(np.sqrt(np.min(eigenvalues.real)))
        beta = first_pole + 1.0e-12j
        dynamic_interior = (
            interior_stiffness.astype(np.complex128)
            - beta * beta * interior_mass
        )
        self.assertGreater(np.linalg.cond(dynamic_interior), 1.0e14)

        forward = scalar_cg_discrete_traction_beta(
            beta,
            degree=degree,
            h_nm=1.0,
            direction="forward",
        )
        backward = scalar_cg_discrete_traction_beta(
            -beta,
            degree=degree,
            h_nm=1.0,
            direction="backward",
        )
        self.assertTrue(np.isfinite(forward.real))
        self.assertTrue(np.isfinite(forward.imag))
        np.testing.assert_allclose(backward, -forward, rtol=1.0e-10)

    def test_scalar_cg_traction_validates_inputs_before_assembly(self):
        kwargs = {"degree": 2, "h_nm": 1.0, "direction": "forward"}
        for beta in (np.nan, np.inf, 1.0 + np.inf * 1j):
            with self.subTest(beta=beta):
                with self.assertRaisesRegex(ValueError, "beta must be finite"):
                    scalar_cg_discrete_traction_beta(beta, **kwargs)
        for h_nm in (0.0, -1.0, np.nan, np.inf):
            with self.subTest(h_nm=h_nm):
                with self.assertRaisesRegex(
                    ValueError, "h_nm must be finite and positive"
                ):
                    scalar_cg_discrete_traction_beta(
                        0.2,
                        degree=2,
                        h_nm=h_nm,
                        direction="forward",
                    )
        for degree in (0, 7):
            with self.subTest(degree=degree):
                with self.assertRaisesRegex(ValueError, r"degree must lie in \[1, 6\]"):
                    scalar_cg_discrete_traction_beta(
                        0.2,
                        degree=degree,
                        h_nm=1.0,
                        direction="forward",
                    )
        with self.assertRaisesRegex(ValueError, "degree must be an integer"):
            scalar_cg_discrete_traction_beta(
                0.2,
                degree=2.5,
                h_nm=1.0,
                direction="forward",
            )
        with self.assertRaisesRegex(ValueError, "Unsupported.*direction"):
            scalar_cg_discrete_traction_beta(
                0.2,
                degree=2,
                h_nm=1.0,
                direction="sideways",
            )
        with self.assertRaisesRegex(ValueError, "not passive"):
            scalar_cg_discrete_traction_beta(
                0.2 - 0.01j,
                degree=2,
                h_nm=1.0,
                direction="forward",
            )

    def test_full3d_uniform_cg_is_opt_in_reciprocal_and_passive(self):
        modes = _reciprocal_modes(0.08 + 0.01j, 0.0 + 10.0j)
        ordinary = build_two_sided_propagation(modes, 100.0)
        corrected = build_two_sided_propagation(
            modes,
            100.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=2,
            axial_h_nm=5.0,
        )

        self.assertEqual(ordinary.propagation_model, "continuous_beta")
        np.testing.assert_allclose(
            ordinary.forward.effective_beta_per_nm,
            ordinary.forward.beta_per_nm,
        )
        self.assertEqual(corrected.propagation_model, "full3d_uniform_cg")
        self.assertTrue(corrected.passivity_valid)
        self.assertTrue(
            diagnose_reciprocity_and_passivity(corrected).reciprocity_valid
        )
        self.assertLessEqual(corrected.max_factor_magnitude, 1.0)
        self.assertNotEqual(
            corrected.forward.effective_beta_per_nm[0],
            corrected.forward.beta_per_nm[0],
        )

    def test_full3d_uniform_cg_requires_explicit_degree_and_h(self):
        modes = _reciprocal_modes(0.08 + 0.0j)
        with self.assertRaisesRegex(ValueError, "axial_fem_degree"):
            build_two_sided_propagation(
                modes,
                100.0,
                propagation_model="full3d_uniform_cg",
                axial_h_nm=5.0,
            )
        with self.assertRaisesRegex(ValueError, "axial_h_nm"):
            build_two_sided_propagation(
                modes,
                100.0,
                propagation_model="full3d_uniform_cg",
                axial_fem_degree=2,
            )
        with self.assertRaisesRegex(ValueError, "integer number"):
            build_two_sided_propagation(
                modes,
                102.0,
                propagation_model="full3d_uniform_cg",
                axial_fem_degree=2,
                axial_h_nm=5.0,
            )

    def test_single_lossless_mode_is_reflection_free_in_both_directions(self):
        propagation = build_two_sided_propagation(_reciprocal_modes(0.08 + 0.0j), 100.0)
        from_bottom = propagation.apply([2.0 - 0.5j], [0.0j])
        from_top = propagation.apply([0.0j], [-0.25 + 1.0j])

        expected = np.exp(1j * 0.08 * 100.0)
        np.testing.assert_allclose(
            from_bottom.top_forward, expected * np.asarray([2.0 - 0.5j])
        )
        np.testing.assert_array_equal(from_bottom.bottom_backward, [0.0j])
        np.testing.assert_allclose(
            from_top.bottom_backward, expected * np.asarray([-0.25 + 1.0j])
        )
        np.testing.assert_array_equal(from_top.top_forward, [0.0j])
        self.assertFalse(propagation.local_reflection_terms_present)
        self.assertFalse(propagation.growing_inverse_factors_present)
        self.assertTrue(propagation.passivity_valid)

    def test_lossy_and_strong_evanescent_modes_decay_without_overflow(self):
        propagation = build_two_sided_propagation(
            _reciprocal_modes(0.08 + 0.01j, 0.0 + 10.0j), 100.0
        )
        outgoing = propagation.apply(np.ones(2), np.ones(2))

        self.assertLessEqual(propagation.max_factor_magnitude, 1.0)
        self.assertAlmostEqual(abs(propagation.forward.factors[0]), np.exp(-1.0))
        self.assertAlmostEqual(abs(propagation.backward.factors[0]), np.exp(-1.0))
        self.assertEqual(propagation.forward.factors[1], 0.0j)
        self.assertEqual(propagation.backward.factors[1], 0.0j)
        self.assertTrue(np.all(np.isfinite(outgoing.top_forward)))
        self.assertTrue(np.all(np.isfinite(outgoing.bottom_backward)))
        self.assertEqual(propagation.stored_complex_scalars, 4)

    def test_growing_or_ambiguous_branches_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "grows"):
            build_two_sided_propagation(
                [
                    _SyntheticMode(0.08 - 0.01j, "forward"),
                    _SyntheticMode(-0.08 - 0.01j, "backward"),
                ],
                100.0,
            )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            build_two_sided_propagation(
                [
                    _SyntheticMode(0.0j, "ambiguous", False),
                    _SyntheticMode(-0.08, "backward"),
                ],
                100.0,
            )
        with self.assertRaisesRegex(ValueError, "not certified"):
            build_two_sided_propagation(
                [
                    _SyntheticMode(0.08, "forward", False),
                    _SyntheticMode(-0.08, "backward"),
                ],
                100.0,
            )

    def test_composition_matches_one_segment_for_phase_and_attenuation(self):
        modes = _reciprocal_modes(0.08 + 0.003j, 0.03 + 0.25j)
        first = build_two_sided_propagation(modes, 37.0)
        second = build_two_sided_propagation(modes, 63.0)
        combined = first.compose(second)
        direct = build_two_sided_propagation(modes, 100.0)

        np.testing.assert_allclose(
            combined.forward.factors, direct.forward.factors, rtol=2.0e-14
        )
        np.testing.assert_allclose(
            combined.backward.factors, direct.backward.factors, rtol=2.0e-14
        )
        incoming_forward = np.asarray([1.0 + 2.0j, -0.5j])
        incoming_backward = np.asarray([0.25 - 0.75j, 2.0 + 0.0j])
        one = direct.apply(incoming_forward, incoming_backward)
        two = combined.apply(incoming_forward, incoming_backward)
        np.testing.assert_allclose(two.top_forward, one.top_forward)
        np.testing.assert_allclose(two.bottom_backward, one.bottom_backward)

    def test_reciprocity_and_passivity_diagnostic_has_negative_control(self):
        reciprocal = build_two_sided_propagation(
            _reciprocal_modes(0.08 + 0.003j, 0.03 + 0.1j), 100.0
        )
        report = diagnose_reciprocity_and_passivity(reciprocal)
        self.assertTrue(report.reciprocity_valid)
        self.assertTrue(report.passivity_valid)
        self.assertLess(report.max_relative_beta_error, 1.0e-14)
        self.assertLess(report.max_relative_factor_error, 1.0e-14)

        nonreciprocal = build_two_sided_propagation(
            [
                _SyntheticMode(0.08 + 0.003j, "forward"),
                _SyntheticMode(-0.07 - 0.003j, "backward"),
            ],
            100.0,
        )
        negative = diagnose_reciprocity_and_passivity(nonreciprocal)
        self.assertFalse(negative.reciprocity_valid)
        self.assertTrue(negative.passivity_valid)
        self.assertGreater(negative.max_relative_beta_error, 1.0e-2)

    def test_shape_length_and_mode_identity_mismatches_are_rejected(self):
        modes = _reciprocal_modes(0.08 + 0.003j)
        propagation = build_two_sided_propagation(modes, 100.0)
        with self.assertRaisesRegex(ValueError, "shape"):
            propagation.apply([1.0, 2.0], [1.0])
        with self.assertRaisesRegex(ValueError, "non-negative"):
            build_two_sided_propagation(modes, -1.0)
        incompatible = build_two_sided_propagation(
            _reciprocal_modes(0.081 + 0.003j), 20.0
        )
        with self.assertRaisesRegex(ValueError, "different beta"):
            propagation.compose(incompatible)


if __name__ == "__main__":
    unittest.main()
