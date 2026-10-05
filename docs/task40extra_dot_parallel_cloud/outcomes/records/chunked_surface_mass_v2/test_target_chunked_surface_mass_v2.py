"""Pure guard tests on literal synthetic weights; no runtime rule construction."""
import ast
import inspect
import unittest

import numpy as np

import target_chunked_surface_vector_mass_v2 as helper
import target_higher_quadrature_reference_mass_v2 as reference
import test_target_chunked_surface_vector as prior

prior.subject = helper


class PriorNativeTests(prior.ChunkedPureTests):
    """Run every prior pure/adversarial helper test against the active variant."""


class UnitMassGuardTests(unittest.TestCase):
    def both(self, weights):
        first = helper.unit_mass_metric(weights)
        second = reference.unit_mass_metric(weights)
        self.assertEqual(first, second)
        return first

    def test_representative_2p67e_minus13_error_accepted_without_mutation(self):
        weights = np.full(4, .25 * .9999999999997333, dtype=np.float64)
        before = weights.tobytes()
        metric = self.both(weights)
        self.assertTrue(metric["passed"])
        self.assertGreater(metric["absolute_error"], 2.6e-13)
        self.assertLess(metric["absolute_error"], 2.8e-13)
        self.assertEqual(metric["absolute_limit"], 1e-12)
        self.assertEqual(weights.tobytes(), before)
        self.assertFalse(metric["weights_normalized"])
        self.assertFalse(metric["construction_error_theorem_claimed"])

    def test_uniform_1e_minus11_mass_perturbation_rejected_both_signs(self):
        for shift in (-1e-11, 1e-11):
            weights = np.full(4, .25 * (1 + shift), dtype=np.float64)
            before = weights.tobytes()
            metric = self.both(weights)
            self.assertFalse(metric["passed"])
            self.assertGreater(metric["absolute_error"], 9e-12)
            self.assertEqual(weights.tobytes(), before)

    def test_exact_constant_and_zero_mass(self):
        self.assertTrue(self.both(np.array([.25, .75]))["passed"])
        self.assertEqual(self.both(np.array([.25, .75]))["absolute_error"], 0)
        metric = self.both(np.zeros(4))
        self.assertFalse(metric["passed"])
        self.assertEqual(metric["measured_mass"], 0)
        self.assertEqual(metric["absolute_error"], 1)
        self.assertFalse(self.both(np.empty(0))["passed"])

    def test_nonfinite_negative_zero_and_wrong_dtype_weights_rejected(self):
        for weights in (np.array([np.nan]), np.array([np.inf]), np.array([-np.inf]),
                        np.array([-.2, 1.2]), np.array([0., 1.]),
                        np.array([1.], dtype=np.float32), np.array([[1.]]),
                        np.array([1 + 0j])):
            with self.subTest(weights=repr(weights)):
                self.assertFalse(self.both(weights)["passed"])
        self.assertIsNone(self.both(np.array([np.nan]))["measured_mass"])
        self.assertIsNone(self.both(np.array([1e308, 1e308]))["measured_mass"])

    def test_unchanged_zero_scale_and_operation_limit(self):
        self.assertEqual(reference.OPERATION_RTOL, 1e-10)
        self.assertTrue(reference.operation_scaled_difference(0j, 0j, 0)["passed"])
        self.assertFalse(reference.operation_scaled_difference(1e-300j, 0j, 0)["passed"])
        self.assertEqual(helper.UNIT_MASS_ABSOLUTE_LIMIT, reference.UNIT_MASS_ABSOLUTE_LIMIT)
        self.assertEqual(helper.UNIT_MASS_POLICY["fraction_of_unchanged_1e_minus10_action_budget"], .01)

    def test_metric_event_precedes_guard_and_rule_bytes_stay_unmodified(self):
        for module, function, event_kind in ((helper, helper.assemble_chunked_top_x, "native_unit_mass_metric_before_gate"),
                                             (reference, reference.run_reference, "reference_unit_mass_metric_before_gate")):
            source = inspect.getsource(function)
            self.assertLess(source.index(event_kind), source.index('not unit_mass["passed"]'))
            tree = ast.parse(inspect.getsource(module.unit_mass_metric))
            mutations = [node for node in ast.walk(tree) if isinstance(node, ast.AugAssign)]
            self.assertEqual(mutations, [])
            calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
            self.assertIn("fsum", calls)
            for name in ("make_quadrature", "roots_legendre", "create_mesh", "form", "eval"):
                self.assertNotIn(name, calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
