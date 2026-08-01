from __future__ import annotations

import unittest

import numpy as np

from benchmarks.task036_transfer_capacity import (
    bilateral_whiten,
    core_complement_action,
    core_projector_action,
    decoder,
    singular_tail_summary,
    transfer_action,
    transfer_weighted_adjoint_action,
)


def _hpd(seed: np.ndarray, shift: float = 1.0) -> np.ndarray:
    return seed.conj().T @ seed + shift * np.eye(seed.shape[1])


class Task036TransferCapacityAlgebraTests(unittest.TestCase):
    def test_full_hermitian_weighted_adjoint_includes_direct_term(self) -> None:
        system = np.asarray(
            [
                [3.2 + 0.4j, -0.7 + 0.9j, 0.2j, 0.0],
                [0.1 - 0.3j, 2.8 - 0.2j, 0.6 + 0.1j, -0.2j],
                [0.4, -0.1 + 0.2j, 3.5 + 0.6j, 0.8 - 0.4j],
                [-0.3j, 0.5, 0.1 + 0.7j, 2.9 - 0.5j],
            ],
            dtype=np.complex128,
        )
        source = np.asarray(
            [
                [1.0 + 0.2j, -0.3j, 0.4],
                [0.2 - 0.1j, 0.7, -0.5j],
                [-0.4, 0.3 + 0.2j, 0.6 - 0.1j],
                [0.1j, -0.2 + 0.4j, 0.9],
            ],
            dtype=np.complex128,
        )
        output = np.asarray(
            [
                [0.5, -0.2j, 0.7 + 0.1j, -0.1],
                [0.3j, 0.8, -0.4 + 0.2j, 0.6],
                [-0.2 + 0.1j, 0.1, 0.5j, 0.9 - 0.3j],
            ],
            dtype=np.complex128,
        )
        direct = np.asarray(
            [
                [0.12 + 0.08j, -0.05j, 0.03],
                [-0.07, 0.09 - 0.02j, 0.04j],
                [0.02 - 0.06j, 0.05, -0.11 + 0.03j],
            ],
            dtype=np.complex128,
        )
        source_metric = _hpd(
            np.asarray([[1.0, 0.2j, -0.1], [0.3, 0.8, 0.1j], [-0.2j, 0.1, 1.1]])
        )
        output_metric = _hpd(
            np.asarray([[0.9, -0.1j, 0.2], [0.1, 1.2, 0.3j], [-0.2j, 0.2, 0.7]])
        )
        x = np.asarray([0.7 - 0.2j, -0.4 + 0.5j, 0.3 + 0.1j])
        y = np.asarray([-0.2 + 0.6j, 0.8 - 0.1j, 0.4 + 0.3j])

        applied = transfer_action(system, source, output, direct, x)
        adjoint_applied = transfer_weighted_adjoint_action(
            system,
            source,
            output,
            direct,
            source_metric,
            output_metric,
            y,
        )
        dense_transfer = output @ np.linalg.solve(system, source) + direct
        np.testing.assert_allclose(
            applied,
            dense_transfer @ x,
            rtol=0.0,
            atol=1.0e-13,
        )
        np.testing.assert_allclose(
            adjoint_applied,
            np.linalg.solve(
                source_metric,
                dense_transfer.conj().T @ output_metric @ y,
            ),
            rtol=0.0,
            atol=1.0e-13,
        )
        lhs = np.vdot(applied, output_metric @ y)
        rhs = np.vdot(x, source_metric @ adjoint_applied)
        self.assertLess(abs(lhs - rhs), 1.0e-12)

        weighted_y = output_metric @ y
        wrong_state = np.linalg.solve(system.T, output.T @ weighted_y)
        wrong_adjoint = np.linalg.solve(
            source_metric,
            source.T @ wrong_state + direct.T @ weighted_y,
        )
        wrong_rhs = np.vdot(x, source_metric @ wrong_adjoint)
        self.assertGreater(abs(lhs - wrong_rhs), 1.0e-3)

        missing_direct_state = np.linalg.solve(
            system.conj().T,
            output.conj().T @ weighted_y,
        )
        missing_direct_adjoint = np.linalg.solve(
            source_metric,
            source.conj().T @ missing_direct_state,
        )
        missing_direct_rhs = np.vdot(
            x,
            source_metric @ missing_direct_adjoint,
        )
        self.assertGreater(abs(lhs - missing_direct_rhs), 1.0e-3)

    def test_bilateral_whitening_and_decoder_close_the_pair(self) -> None:
        rng = np.random.default_rng(36051)
        metric_seed = rng.standard_normal((6, 6)) + 1j * rng.standard_normal((6, 6))
        metric = _hpd(metric_seed, shift=2.0)
        right = rng.standard_normal((6, 3)) + 1j * rng.standard_normal((6, 3))
        left = rng.standard_normal((6, 3)) + 1j * rng.standard_normal((6, 3))

        whitened_right, whitened_left = bilateral_whiten(right, left, metric)
        pairing = whitened_left.conj().T @ metric @ whitened_right
        np.testing.assert_allclose(
            pairing,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-12,
        )
        raw_decoder = decoder(right, left, metric)
        np.testing.assert_allclose(
            raw_decoder @ right,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-12,
        )
        whitened_pair_decoder = decoder(
            whitened_right,
            whitened_left,
            metric,
        )
        np.testing.assert_allclose(
            whitened_pair_decoder @ whitened_right,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-12,
        )

    def test_near_rank_deficient_pair_and_core_fail_at_frozen_cutoff(self) -> None:
        metric = np.eye(3, dtype=np.complex128)
        right = np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]],
            dtype=np.complex128,
        )
        near_rank_left = np.asarray(
            [[1.0, 0.0], [0.0, 1.0e-11], [0.0, 0.0]],
            dtype=np.complex128,
        )
        with self.assertRaises(np.linalg.LinAlgError):
            bilateral_whiten(right, near_rank_left, metric)
        with self.assertRaises(np.linalg.LinAlgError):
            decoder(right, near_rank_left, metric)

        qualified_core = np.asarray(
            [[1.0, 0.0], [0.0, 1.0e-6], [0.0, 0.0]],
            dtype=np.complex128,
        )
        np.testing.assert_allclose(
            core_projector_action(qualified_core, metric, right),
            right,
            rtol=0.0,
            atol=1.0e-14,
        )
        near_rank_core = np.asarray(
            [[1.0, 0.0], [0.0, 1.0e-11], [0.0, 0.0]],
            dtype=np.complex128,
        )
        with self.assertRaises(np.linalg.LinAlgError):
            core_projector_action(near_rank_core, metric, right)

    def test_metric_core_projector_and_complement_contracts(self) -> None:
        rng = np.random.default_rng(36052)
        metric_seed = rng.standard_normal((7, 7)) + 1j * rng.standard_normal((7, 7))
        metric = _hpd(metric_seed, shift=1.5)
        core = rng.standard_normal((7, 3)) + 1j * rng.standard_normal((7, 3))
        probes = rng.standard_normal((7, 4)) + 1j * rng.standard_normal((7, 4))

        projected = core_projector_action(core, metric, probes)
        np.testing.assert_allclose(
            core_projector_action(core, metric, projected),
            projected,
            rtol=0.0,
            atol=2.0e-13,
        )
        other_probes = rng.standard_normal((7, 4)) + 1j * rng.standard_normal((7, 4))
        other_projected = core_projector_action(core, metric, other_probes)
        np.testing.assert_allclose(
            projected.conj().T @ metric @ other_probes,
            probes.conj().T @ metric @ other_projected,
            rtol=0.0,
            atol=2.0e-12,
        )
        np.testing.assert_allclose(
            core_complement_action(core, metric, core),
            np.zeros_like(core),
            rtol=0.0,
            atol=2.0e-13,
        )
        complement = core_complement_action(core, metric, probes)
        np.testing.assert_allclose(
            core.conj().T @ metric @ complement,
            np.zeros((core.shape[1], probes.shape[1])),
            rtol=0.0,
            atol=2.0e-12,
        )

    def test_singular_tail_and_captured_energy_are_distinct_metrics(self) -> None:
        singular_values = np.asarray([10.0, 5.0e-6, 5.0e-8, 5.0e-10, 5.0e-12])
        summary = singular_tail_summary(singular_values)
        np.testing.assert_allclose(
            summary["absolute_worst_case_tail_by_rank"],
            np.asarray([10.0, 5.0e-6, 5.0e-8, 5.0e-10, 5.0e-12, 0.0]),
            rtol=0.0,
            atol=0.0,
        )
        np.testing.assert_allclose(
            summary["relative_worst_case_tail_by_rank"],
            np.asarray([1.0, 5.0e-7, 5.0e-9, 5.0e-11, 5.0e-13, 0.0]),
            rtol=1.0e-15,
            atol=0.0,
        )
        self.assertEqual(
            summary["minimum_rank_by_absolute_tail"],
            {1.0e-6: 2, 1.0e-8: 3, 1.0e-10: 4},
        )
        self.assertEqual(
            summary["minimum_rank_by_relative_tail"],
            {1.0e-6: 1, 1.0e-8: 2, 1.0e-10: 3},
        )
        captured = summary["captured_energy_by_rank"]
        expected = np.concatenate(
            (
                np.zeros(1),
                np.cumsum(singular_values**2) / np.sum(singular_values**2),
            )
        )
        np.testing.assert_allclose(captured, expected, rtol=0.0, atol=0.0)
        self.assertGreater(captured[1], 0.99999)
        self.assertGreater(
            summary["absolute_worst_case_tail_by_rank"][1],
            1.0e-6,
        )
        self.assertLess(
            summary["relative_worst_case_tail_by_rank"][1],
            1.0e-6,
        )


if __name__ == "__main__":
    unittest.main()
