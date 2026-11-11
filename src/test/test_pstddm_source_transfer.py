"""Small algebraic oracles; no native FE, local PML, or physics qualification."""
import unittest

import numpy as np

from src.solvers.pstddm_source_transfer import PureSourceTransfer, curl_product, smooth_cutoff
from src.solvers.pstddm_comparison import flexible_gmres


def oracle(layers):
    """Tridiagonal wave-like operator with exact transparent local inverses.

    Full inverses are used ONLY in this tiny algebraic oracle. Restricting
    their fields to a pair is equivalent to exact exterior elimination; it
    is not the proposed PML implementation or a measured local-memory saving.
    """
    width = 4
    size = layers * width
    diagonal = 1.7 + 0.11j + 0.03 * np.arange(size)
    a = np.diag(diagonal) + np.diag(np.full(size - 1, -1.0), 1)
    a += np.diag(np.full(size - 1, -1.0), -1)
    inverse = np.linalg.inv(a)
    parts = []
    betas = []
    for layer in range(layers):
        mask = np.zeros(size)
        mask[width * layer:width * (layer + 1)] = 1.0
        parts.append(np.diag(mask))
        beta = smooth_cutoff(np.arange(size), width * layer, width * (layer + 1) - 1)
        betas.append(np.diag(beta))
    calls = []

    def solve(pair, rhs):
        calls.append((pair, rhs.copy()))
        return inverse @ rhs

    def comm(pair, field, reverse=False):
        layer = pair if reverse else pair + 1
        beta = np.eye(size) - betas[layer] if reverse else betas[layer]
        return parts[layer] @ (a @ (beta @ field) - beta @ (a @ field))

    def reconstruct(layer, up, down):
        return parts[layer] @ ((np.zeros(size) if up is None else up)
                               + (np.zeros(size) if down is None else down))

    pc = PureSourceTransfer(partition_mass=parts,
                            forward_beta_mass=[p @ b for p, b in zip(parts, betas)],
                            mass_solve=lambda x: x.copy(), solve_pair=solve,
                            forward_commutator=lambda i, u: comm(i, u),
                            reverse_commutator=lambda i, u: comm(i, u, True),
                            reconstruct_load=reconstruct)
    return pc, a, calls


class PureSourceTransferTests(unittest.TestCase):
    def test_flexible_gmres_restart_nonzero_initial_and_variable_pc(self):
        rng = np.random.default_rng(911)
        a = np.diag(np.linspace(2, 4, 12)+.3j)+.07*(rng.normal(size=(12,12))+1j*rng.normal(size=(12,12)))
        b = rng.normal(size=12)+1j*rng.normal(size=12)
        x0 = np.full(12, .3+.1j)
        count = [0]
        def pc(v):
            count[0] += 1
            return v/(np.diag(a)*(1+.02*np.sin(count[0]+np.arange(12))))
        x, result = flexible_gmres(a,b,pc,x0,restart=3,max_iterations=100,tolerance=1e-10)
        self.assertTrue(result['passed'])
        self.assertGreater(result['iterations'],3)
        np.testing.assert_allclose(x,np.linalg.solve(a,b),rtol=2e-9,atol=2e-9)
        for record in result['history']:
            self.assertTrue(np.isfinite(record['true_residual']))
        _, limited = flexible_gmres(a,b,lambda v:v,x0,restart=1,max_iterations=1,tolerance=1e-12)
        self.assertFalse(limited['passed'])
        self.assertEqual(limited['iterations'],1)
        self.assertEqual(limited['reason'],'maximum_iterations')

    def test_complex_exact_source_transfer_oracle(self):
        for layers in (2, 3, 4, 8):
            with self.subTest(layers=layers):
                pc, a, calls = oracle(layers)
                rng = np.random.default_rng(900 + layers)
                rhs = rng.normal(size=a.shape[0]) + 1j * rng.normal(size=a.shape[0])
                result = pc.apply(rhs)
                np.testing.assert_allclose(a @ result.field, rhs, rtol=2e-12, atol=2e-12)
                self.assertEqual(len(calls), 2 * (layers - 1))
                self.assertEqual(result.statistics['mass_solve_count'], 2)

    def test_two_layer_endpoint_sources_not_doubled(self):
        pc, a, calls = oracle(2)
        rhs = np.arange(a.shape[0]) + 1j
        field = pc(rhs)
        self.assertEqual([i for i, _ in calls], [0, 0])
        np.testing.assert_array_equal(calls[0][1], rhs)
        np.testing.assert_array_equal(calls[1][1], rhs)
        np.testing.assert_allclose(field, np.linalg.solve(a, rhs), rtol=1e-12, atol=1e-12)

    def test_each_application_uses_fresh_residual(self):
        pc, a, _ = oracle(4)
        r = np.arange(a.shape[0]) + 1j
        s = np.cos(np.arange(a.shape[0])) + 0.2j
        np.testing.assert_allclose(pc(2 * r - 3j * s), 2 * pc(r) - 3j * pc(s),
                                   rtol=1e-12, atol=1e-12)
        np.testing.assert_array_equal(pc(np.zeros_like(r)), np.zeros_like(r))

    def test_inconsistent_lifting_rejected(self):
        pc, a, _ = oracle(2)
        pc.mass_solve = lambda x: 2 * x
        with self.assertRaisesRegex(ValueError, 'lifting residual'):
            pc(np.ones(a.shape[0]))

    def test_cutoff_bounds_and_end_derivatives(self):
        x = np.array([-1., 0., 0.25, 0.5, 0.75, 1., 2.])
        b = smooth_cutoff(x, 0., 1.)
        np.testing.assert_allclose(b, [1., 1., .84375, .5, .15625, 0., 0.])
        np.testing.assert_allclose(b + smooth_cutoff(x, 0., 1., increasing=True), 1.)
        h = 1e-6
        self.assertLess(abs((smooth_cutoff(h, 0., 1.) - 1.) / h), 4e-6)
        self.assertLess(abs(smooth_cutoff(1.-h, 0., 1.) / h), 4e-6)

    def test_curl_product_against_analytic_polynomial(self):
        # E=(xy,yz,zx), beta=x^2+yz. Direct derivatives of beta*E
        # independently give the following curl components.
        x, y, z = .23, -.51, .79
        e = np.array([x*y, y*z, z*x], dtype=complex) * (1 + .3j)
        beta = x*x + y*z
        gradient = np.array([2*x, z, y])
        curl_e = np.array([-y, -z, -x], dtype=complex) * (1 + .3j)
        expected = np.array([z*z*x - y*y*z - beta*y,
                             x*y*y - 2*z*x*x - beta*z,
                             2*x*y*z - z*x*y - beta*x]) * (1 + .3j)
        np.testing.assert_allclose(curl_product(beta, curl_e, gradient, e), expected,
                                   rtol=1e-14, atol=1e-14)


if __name__ == '__main__':
    unittest.main()
