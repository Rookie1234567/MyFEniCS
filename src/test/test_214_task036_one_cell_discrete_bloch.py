from __future__ import annotations

import unittest

import numpy as np

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _local_two_way_multiplane_diagnostic,
)
from benchmarks.run_task036_exact_cauchy_port_audit import (
    _modal_port_matrix,
    _stable_unit_and_log10_norm,
    _stable_vdot,
)
from src.solvers.one_cell_discrete_bloch import (
    ProjectedTwoPortSchur,
    bloch_residual_metrics,
    compose_projected_two_port_schur,
    scalar_cg_sign_fixture,
)


class Task036OneCellDiscreteBlochAlgebraTests(unittest.TestCase):
    def test_cauchy_audit_scaled_norm_and_pairing_avoid_overflow(self) -> None:
        values = np.asarray((1.0e200 + 2.0e200j, -3.0e200j))
        unit, log10_norm = _stable_unit_and_log10_norm(values)
        self.assertAlmostEqual(np.linalg.norm(unit), 1.0)
        self.assertIsNotNone(log10_norm)
        self.assertTrue(np.isfinite(log10_norm))
        paired = _stable_vdot(
            values,
            np.asarray((2.0e-200 - 1.0e-200j, 4.0e-200j)),
        )
        expected = np.vdot(
            values / 1.0e200,
            np.asarray((2.0 - 1.0j, 4.0j)),
        )
        self.assertAlmostEqual(paired.real, expected.real)
        self.assertAlmostEqual(paired.imag, expected.imag)
        zero_unit, zero_log = _stable_unit_and_log10_norm(
            np.zeros(4, dtype=np.complex128)
        )
        self.assertFalse(np.any(zero_unit))
        self.assertIsNone(zero_log)

    def test_one_cell_modal_port_reconstructs_same_projected_schur(self) -> None:
        count = 3
        diagonal = np.diag(
            np.asarray((2.0 + 0.1j, 2.5 - 0.2j, 3.0 + 0.3j))
        )
        coupling = np.diag(
            np.asarray((-0.4 + 0.05j, -0.3j, -0.2 - 0.1j))
        )
        port = ProjectedTwoPortSchur(
            S_LL=diagonal,
            S_LR=coupling,
            S_RL=coupling,
            S_RR=diagonal,
            port_rows=2 * count,
            interior_rows=0,
            interior_matrix_nnz=0,
        )
        forward = np.asarray((0.8 + 0.1j, 0.7 - 0.2j, 0.6 + 0.05j))
        backward = np.asarray((0.75 - 0.1j, 0.65 + 0.2j, 0.55 - 0.05j))
        negative = np.asarray(
            [
                [1.0, 0.1j, 0.0],
                [0.0, 1.0, -0.05j],
                [0.02, 0.0, 1.0],
            ],
            dtype=np.complex128,
        )
        actual, audit = _modal_port_matrix(
            port,
            negative,
            forward,
            backward,
            1,
        )
        expected = np.block(
            [[port.S_LL, port.S_LR], [port.S_RL, port.S_RR]]
        )
        self.assertLess(
            np.linalg.norm(actual - expected, ord="fro")
            / np.linalg.norm(expected, ord="fro"),
            1.0e-13,
        )
        self.assertLess(audit["boundary_resolver_relative_residual"], 1.0e-13)

    def test_projected_port_star_product_matches_explicit_schur(self) -> None:
        rng = np.random.default_rng(3604)
        count = 4

        def block() -> np.ndarray:
            return (
                rng.standard_normal((count, count))
                + 1j * rng.standard_normal((count, count))
            ) / 20.0

        left = ProjectedTwoPortSchur(
            S_LL=2.0 * np.eye(count) + block(),
            S_LR=block(),
            S_RL=block(),
            S_RR=2.5 * np.eye(count) + block(),
            port_rows=2 * count,
            interior_rows=3,
            interior_matrix_nnz=10,
        )
        right = ProjectedTwoPortSchur(
            S_LL=3.0 * np.eye(count) + block(),
            S_LR=block(),
            S_RL=block(),
            S_RR=3.5 * np.eye(count) + block(),
            port_rows=2 * count,
            interior_rows=5,
            interior_matrix_nnz=12,
        )
        combined, audit = compose_projected_two_port_schur(left, right)

        full = np.block(
            [
                [left.S_LL, left.S_LR, np.zeros((count, count))],
                [left.S_RL, left.S_RR + right.S_LL, right.S_LR],
                [np.zeros((count, count)), right.S_RL, right.S_RR],
            ]
        )
        endpoint = np.r_[np.arange(count), np.arange(2 * count, 3 * count)]
        interior = np.arange(count, 2 * count)
        expected = full[np.ix_(endpoint, endpoint)] - full[
            np.ix_(endpoint, interior)
        ] @ np.linalg.solve(
            full[np.ix_(interior, interior)],
            full[np.ix_(interior, endpoint)],
        )
        actual = np.block(
            [
                [combined.S_LL, combined.S_LR],
                [combined.S_RL, combined.S_RR],
            ]
        )
        self.assertLess(
            np.linalg.norm(actual - expected, ord="fro")
            / np.linalg.norm(expected, ord="fro"),
            1.0e-13,
        )
        self.assertLess(audit["pivot_solve_relative_residual"], 1.0e-13)

    def test_outward_flux_sign_fixture_rejects_wrong_sign(self) -> None:
        audit = scalar_cg_sign_fixture(0.8 + 0.02j)
        self.assertLess(audit["polynomial_relative_residual"], 1.0e-13)
        self.assertLess(
            audit["outward_flux_balance_relative_residual"],
            1.0e-13,
        )
        self.assertGreater(
            audit["wrong_sign_negative_control_relative_residual"],
            1.0e-3,
        )

    def test_projected_polynomial_detects_cross_mode_mixing(self) -> None:
        multipliers = np.asarray(
            [0.81 + 0.04j, 0.72 - 0.03j],
            dtype=np.complex128,
        )
        S_lr = np.asarray(
            [[-1.2 + 0.1j, 0.0], [0.0, -0.9 - 0.06j]],
            dtype=np.complex128,
        )
        S_rl = S_lr.copy()
        S_sum = np.diag(
            [
                -(S_rl[index, index] + multipliers[index] ** 2 * S_lr[index, index])
                / multipliers[index]
                for index in range(2)
            ]
        )
        schur = ProjectedTwoPortSchur(
            S_LL=0.5 * S_sum,
            S_LR=S_lr,
            S_RL=S_rl,
            S_RR=0.5 * S_sum,
            port_rows=4,
            interior_rows=2,
            interior_matrix_nnz=4,
        )
        clean = bloch_residual_metrics(schur, multipliers)
        self.assertLess(clean["forward"]["max_rho"], 1.0e-13)
        self.assertLess(
            clean["forward"]["projected_offdiagonal_ratio"],
            1.0e-13,
        )

        mixed = ProjectedTwoPortSchur(
            S_LL=schur.S_LL.copy(),
            S_LR=schur.S_LR.copy(),
            S_RL=schur.S_RL.copy(),
            S_RR=schur.S_RR.copy(),
            port_rows=4,
            interior_rows=2,
            interior_matrix_nnz=4,
        )
        mixed.S_RL[0, 1] = 2.0e-3 - 1.0e-3j
        failed = bloch_residual_metrics(mixed, multipliers)
        self.assertGreater(
            failed["forward"]["projected_offdiagonal_ratio"],
            1.0e-5,
        )

    def test_multiplane_resolver_handles_nonidentity_negative_trace_map(
        self,
    ) -> None:
        lam = np.asarray([0.83 + 0.11j, 0.76 - 0.08j])
        mu = np.asarray([0.79 - 0.06j, 0.71 + 0.04j])
        coordinates = np.asarray(
            [[1.0 + 0.0j, 0.07 - 0.02j], [-0.03j, 0.94 + 0.01j]]
        )
        a0 = np.asarray([0.4 + 0.1j, -0.2 + 0.05j])
        b_top = np.asarray([-0.1 + 0.2j, 0.15 - 0.08j])
        cells = 4
        planes = np.stack(
            [
                lam**plane * a0
                + coordinates @ (mu ** (cells - plane) * b_top)
                for plane in range(cells + 1)
            ]
        )
        report = _local_two_way_multiplane_diagnostic(
            planes,
            lam,
            mu,
            coordinates,
            groups=[(0, 1)],
            positive_trace_metric=np.eye(2),
        )
        self.assertLess(
            report["forward_cross_cell_trace_metric_relative_l2"],
            1.0e-13,
        )
        self.assertLess(
            report["backward_cross_cell_trace_metric_relative_l2"],
            1.0e-13,
        )
        self.assertLess(report["pair_reconstruction_relative_l2"], 1.0e-13)

        perturbed = planes.copy()
        perturbed[2, 0] += 2.0e-3 - 1.0e-3j
        failed = _local_two_way_multiplane_diagnostic(
            perturbed,
            lam,
            mu,
            coordinates,
            groups=[(0, 1)],
            positive_trace_metric=np.eye(2),
        )
        self.assertGreater(
            failed["forward_cross_cell_trace_metric_relative_l2"],
            1.0e-4,
        )


if __name__ == "__main__":
    unittest.main()
