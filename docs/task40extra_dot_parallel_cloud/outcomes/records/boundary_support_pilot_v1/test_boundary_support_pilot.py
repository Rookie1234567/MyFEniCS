"""Focused pure NumPy/public-Basix metadata tests; never FE/JIT/PDE."""
import ast
import hashlib
import inspect
import itertools
import unittest
from types import SimpleNamespace

import numpy as np

import target_boundary_support_pilot as subject
import target_boundary_support_reference as independent


class ArithmeticTests(unittest.TestCase):
    def test_pinned_helpers_and_unchanged_policy(self):
        native, reference, identities = subject.public_helpers()
        self.assertEqual(identities["native"]["sha256"], subject.PINNED_SOURCES["native"][1])
        self.assertEqual(identities["reference"]["sha256"], subject.PINNED_SOURCES["reference"][1])
        self.assertEqual(native.UNIT_MASS_ABSOLUTE_LIMIT, 1e-12)
        self.assertEqual(reference.OPERATION_RTOL, 1e-10)
        self.assertFalse(native.UNIT_MASS_POLICY["construction_error_theorem_claimed"])

    def test_weighted_absolute_uses_actual_nonunit_phase_and_does_not_zero_excluded(self):
        weights = np.array([.1, .2, .3], dtype=np.float64)
        phase = np.array([.6+.8j, .6+.800000000000001j, 1+.1j], dtype=np.complex128)
        values = np.array([[1., 1e-16, -2.], [2., -2e-16, 4.], [-3., 3e-16, 6.]])
        before = values.tobytes()
        measured, absolute, bound = subject.local_difference_bound(weights, phase, values, np.array([0, 2]))
        actual = np.einsum("q,qj->j", weights * phase, values, optimize=False)
        self.assertGreater(measured[1], 0)
        self.assertGreater(bound[1], abs(actual[1]))
        self.assertGreaterEqual(absolute[1], measured[1])
        self.assertLess(bound[0], absolute[0])
        self.assertEqual(values.tobytes(), before)

    def test_retained_two_kernel_bound_contains_layout_changes(self):
        rng = np.random.default_rng(1729)
        q, d = 32, 17
        weights = rng.random(q) + .1
        phase = np.exp(1j * rng.uniform(-1e4, 1e4, q))
        values = rng.normal(size=(q, d))
        closure = np.array([0, 2, 4, 7, 11, 16])
        anchor = np.einsum("q,qj->j", weights * phase, values, optimize=False)
        candidate = np.zeros(d, dtype=np.complex128)
        candidate[closure] = np.einsum("q,qj->j", weights * phase, np.ascontiguousarray(values[:, closure]), optimize=False)
        _, _, bound = subject.local_difference_bound(weights, phase, values, closure)
        self.assertTrue(np.all(np.abs(anchor - candidate) <= bound))

    def test_amplified_first_product_underflow_fails_closed(self):
        with self.assertRaises(FloatingPointError):
            subject.weighted_absolute_bounds(np.array([1e-300]), np.array([1e-300+0j]), np.array([[1e300]]))

    def test_distributed_tiny_real_l2_is_not_erased(self):
        error = np.full(4096, 1e-180)
        low, high = subject.stable_norm_bounds(error)
        expected = 64e-180
        self.assertLessEqual(low, expected)
        self.assertGreaterEqual(high, expected)
        self.assertGreater(low, 0)
        candidate = np.full(4096, 1e-170+0j)
        certificate, _ = subject.mask_margin_certificate(candidate, error)
        self.assertFalse(certificate["norms"]["l2"]["passed"])

    def test_distributed_subnormal_complex_norm_fails_closed(self):
        tiny = subject.TINY
        value = np.full(1000, complex(2 * tiny, 2 * tiny))
        with self.assertRaises(FloatingPointError):
            subject.stable_norm_bounds(value)
        certificate, _ = subject.mask_margin_certificate(value, np.zeros(1000))
        self.assertFalse(certificate["passed"])

    def test_masked_norm_must_pass_even_when_raw_norm_and_membership_pass(self):
        candidate = np.full(1000, .99e-30 + 0j)
        candidate[:2] = [2e-30, 1.1e-30]
        error = np.zeros(1000)
        error[:2] = 1.9e-41
        certificate, _ = subject.mask_margin_certificate(candidate, error)
        self.assertTrue(certificate["mask_membership_passed"])
        self.assertTrue(certificate["norms"]["l2"]["passed"])
        self.assertTrue(certificate["norms"]["linf"]["passed"])
        self.assertFalse(certificate["masked_norms"]["l2"]["passed"])
        self.assertFalse(certificate["passed"])

    def test_strict_cutoff_ambiguity_and_no_floor_in_relative_norm(self):
        candidate = np.array([1+0j, 1e-13+0j, 0j])
        certificate, ambiguous = subject.mask_margin_certificate(candidate, np.zeros(3))
        self.assertTrue(ambiguous[1])
        self.assertFalse(certificate["passed"])
        self.assertTrue(subject.mask_margin_certificate(np.array([1+0j, 0j]), np.array([1e-15, 1e-40]))[0]["passed"])

    def test_dual_bound_contains_complex_repeated_master_rounding(self):
        native, _, _ = subject.public_helpers()
        anchor = np.array([1+2j, 3-4j, -2+.5j, 5+1j])
        candidate = anchor + np.array([1e-13j, -2e-13, 3e-13j, 1e-13])
        error = subject.upper(np.abs(candidate-anchor), 8, 16)
        slaves = np.array([2, 3], dtype=np.int32)
        masters = np.array([0, 0, 1, 0], dtype=np.int32)
        coefficients = np.array([.2+.3j, -.4+.5j, .7-.2j, .1-.9j])
        offsets = np.array([0, 0, 0, 2, 4], dtype=np.int32)
        a = native.dual_project(anchor, slaves, masters, coefficients, offsets)
        c = native.dual_project(candidate, slaves, masters, coefficients, offsets)
        bound = subject.dual_error_bound(candidate, anchor, error, slaves, masters, coefficients, offsets)
        self.assertTrue(np.all(np.abs(a-c) <= bound))
        self.assertTrue(np.all(bound[slaves] == 0))
        np.testing.assert_array_equal(anchor, [1+2j, 3-4j, -2+.5j, 5+1j])

    def test_component_mask_then_combination_mask_and_single_conjugation(self):
        native, _, _ = subject.public_helpers()
        raw = np.array([[1+2j, 1e-15+1e-15j, 3-1j], [2-1j, 1e-15-1e-15j, -3+1j]])
        masked = np.zeros_like(raw)
        for j in range(2):
            rows, values, _ = native.unchanged_mask(raw[j])
            masked[j, rows] = values
        combined, final, _ = subject.combine_components(masked, (1, 1))
        self.assertEqual(combined[1], 0)
        self.assertEqual(final[2], 0)
        d = np.conjugate(final)
        self.assertEqual(d[0], 3-1j)

    def test_actual_modulus_checks_reject_nonunit_and_record_finite_exp(self):
        phase = np.exp(1j * np.array([0., 1., 1e4]))
        result = subject.phase_modulus_record(phase)
        self.assertFalse(result["ideal_unit_modulus_assumed"])
        self.assertEqual(result["computed_values"], 3)
        with self.assertRaises(FloatingPointError):
            subject.phase_modulus_record(np.array([2+0j]))


class PublicMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import basix
        cls.basix = basix
        cls.basis = basix.create_element(basix.ElementFamily.N1E, basix.CellType.hexahedron, 6,
                                         basix.LagrangeVariant.legendre)

    def test_exact_basis_identity(self):
        self.assertEqual(int(self.basis.hash()), subject.EXPECTED_BASIS_HASH)
        self.assertEqual(hashlib.sha256(self.basis.coefficient_matrix.tobytes()).hexdigest(), subject.EXPECTED_COEFFICIENT_SHA256)

    def test_all_six_public_closures_and_nontrivial_T_states(self):
        for face in range(6):
            for info in (0, (1 << 30)-1):
                closure, record = subject.validate_closure_and_T(self.basis, face, info)
                self.assertEqual(len(closure), 84)
                self.assertEqual(record["T_apply_input_directions_checked"], 882)
                self.assertTrue(record["literal_cross_block_zero"])
                self.assertFalse(record["tiny_entity_transform_values_thresholded"])

    def test_T_cross_block_leak_rejected(self):
        basis = self.basis
        closure = np.array(basis.entity_closure_dofs[2][0])
        outside = int(np.setdiff1d(np.arange(882), closure)[0])
        def leaking(data, block_size, info):
            basis.T_apply(data, block_size, info)
            data[outside] += data[closure[0]]
        fake = SimpleNamespace(dim=882, entity_dofs=basis.entity_dofs,
                               entity_closure_dofs=basis.entity_closure_dofs, T_apply=leaking)
        with self.assertRaises(ValueError):
            subject.validate_closure_and_T(fake, 0, 0)

    def test_exact_side_rectangle_signed_axis_permutations_independent_route(self):
        native, reference, _ = subject.public_helpers()
        for permutation in itertools.permutations(range(3)):
            J = np.zeros((3, 3))
            for column, row in enumerate(permutation):
                J[row, column] = [16.5, -12.5, 10.][row]
            xyz = np.array([0., 25., -10.]) + native._VERTICES @ J.T
            for side in ("top", "bottom"):
                plane = float(xyz[:, 2].max() if side == "top" else xyz[:, 2].min())
                face = xyz[xyz[:, 2] == plane]
                primary = subject.rectangle_from_geometry(1, 2, face, xyz, plane, side)
                ref = independent.reference_rectangle(1, 2, face, xyz, plane, side, reference)
                self.assertEqual(primary.area, ref.area)
                self.assertEqual(primary.zplane, ref.zplane)
                corrupt = xyz.copy()
                corrupt[7, 0] += 1e-12
                with self.assertRaises(ValueError):
                    subject.rectangle_from_geometry(1, 2, face, corrupt, plane, side)


class SourceBoundaryTests(unittest.TestCase):
    def test_only_caller_supplied_FE_objects_and_public_eval_reference(self):
        for module in (subject, independent):
            tree = ast.parse(inspect.getsource(module))
            calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)}
            self.assertFalse(calls & {"create_mesh", "functionspace", "form", "assemble_matrix", "factorize", "solve"})
        source = inspect.getsource(independent.run_reference)
        self.assertIn("field.eval(", source)
        self.assertNotIn(".tabulate(", source)
        self.assertNotIn("closure", source)
        self.assertIn("for increment in (8, 16)", source)

    def test_exact_inventory_and_default_chunk32(self):
        modes = tuple(SimpleNamespace(side=s, m=m, n=n, polarization=p, alpha=float(m), gamma=float(n),
                                      k_vector=np.array([m, n, 1j]), e_vector=np.array([1+0j, 1j, 0j]))
                      for s in ("top", "bottom") for m, n in subject.PHASE_ORDERS for p in ("s", "p"))
        groups = subject.validate_mode_inventory(modes, tuple(range(12)))
        self.assertEqual(len(groups), 6)
        self.assertEqual(inspect.signature(subject.assemble_boundary_support_pilot).parameters["chunk_size"].default, 32)
        with self.assertRaises(ValueError):
            subject.validate_mode_inventory(modes[:-1], tuple(range(11)))
        with self.assertRaises(ValueError):
            subject.validate_mode_inventory(modes, (0,) * 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
