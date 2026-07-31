from __future__ import annotations

import unittest

import numpy as np

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _local_two_way_multiplane_diagnostic,
)
from src.solvers.one_cell_discrete_bloch import (
    ProjectedTwoPortSchur,
    bloch_residual_metrics,
    scalar_cg_sign_fixture,
)


class Task036OneCellDiscreteBlochAlgebraTests(unittest.TestCase):
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
