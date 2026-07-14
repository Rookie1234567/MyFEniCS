from __future__ import annotations

from dataclasses import dataclass
import unittest

import numpy as np

from src.modes.stable_propagation import (
    build_two_sided_propagation,
    diagnose_reciprocity_and_passivity,
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
