from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import benchmarks.run_task036_transfer_optimal_port_capacity as d2_runner

from benchmarks.task036_transfer_capacity import (
    bilateral_whiten,
    complex_gaussian_holdout_multiplier,
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
    def test_d2_current_identity_and_observable_contract(self) -> None:
        cfg = SimpleNamespace(
            nedelec_degree=5,
            mesh_target_size=10.0,
            polarization_kind="p",
            incident_theta_deg=89.5,
            incident_phi_deg=90.0,
            grating_height=120.0,
            grating_width_x=17.0,
            mesh_axis_cell_counts=(6, 4, 14),
        )
        with tempfile.TemporaryDirectory(prefix="task036-authority-") as temp_dir:
            root = Path(temp_dir)
            record_path = root / "full3d_record.json"
            reference_root = root / "reference"
            reference_root.mkdir()
            orders = reference_root / "dtn_port_diffraction_orders_3d.json"
            orders.write_bytes(b"minimal orders")
            values = {
                "R_total": 0.6,
                "T_total": 0.1,
                "R00_total": 0.6,
                "R_plus_T_plus_A_volume": 1.0,
                "A_volume_total": 0.3,
                "energy_closure_error_port_volume": 0.0,
                "incident_power_code_units": 2.0,
            }
            (reference_root / "dtn_port_power_metrics_3d.json").write_text(
                json.dumps(values)
            )
            (reference_root / "volume_absorption.json").write_text(
                json.dumps(
                    {
                        key: values[key]
                        for key in (
                            "A_volume_total",
                            "energy_closure_error_port_volume",
                            "incident_power_code_units",
                        )
                    }
                )
            )
            sha = "3" * 40
            record = {
                "status": "full3d_reference_pass",
                "qualification": {"pass": True, "failures": []},
                "source": {
                    "commit_sha": sha,
                    "head_after_sha": sha,
                    "verified_clean_sha": sha,
                },
                "degree": 5,
                "h_nm": 10.0,
                "mpi_size": 8,
                "polarization_kind": "p",
                "dtn_orders_sha256": hashlib.sha256(orders.read_bytes()).hexdigest(),
                "solver_summary": {
                    "incident_theta_deg": 89.5,
                    "incident_phi_deg": 90.0,
                    "elapsed_seconds": 12.5,
                    "config": {
                        "grating_height": 120.0,
                        "grating_width_x": 17.0,
                        "mesh_axis_cell_counts": [6, 4, 14],
                    },
                    **values,
                },
                "resource_authority": {
                    "max_process_tree_rss_mb": 1024.0,
                    "max_process_tree_swap_mb": 0.0,
                },
            }
            record_path.write_text(json.dumps(record))

            def clean_git(command: list[str], text: bool = True) -> str:
                return sha if command[1] == "rev-parse" else ""

            with patch.object(
                d2_runner.subprocess, "check_output", side_effect=clean_git
            ):
                identity = d2_runner._validate_current_full3d_reference(
                    record_path, reference_root, cfg
                )
            self.assertEqual(identity["source_sha"], sha)
            self.assertEqual(identity["resource_reference"]["swap"], 0.0)
            self.assertEqual(len(identity["artifact_hashes"]), 3)

            power_path = reference_root / "dtn_port_power_metrics_3d.json"
            power = json.loads(power_path.read_text())
            power["R_total"] = float(power["R_total"]) + 1.0e-3
            power_path.write_text(json.dumps(power))
            with patch.object(
                d2_runner.subprocess, "check_output", side_effect=clean_git
            ):
                with self.assertRaisesRegex(AssertionError, "observable mismatch"):
                    d2_runner._validate_current_full3d_reference(
                        record_path, reference_root, cfg
                    )

    def test_d2_argument_and_output_root_contract(self) -> None:
        record_path = Path("current_full3d_record.json")
        fake_mpi = SimpleNamespace(COMM_WORLD=SimpleNamespace(size=8, rank=0))
        sentinel = RuntimeError("heavy body reached")
        seen_cases: list[dict[str, object]] = []

        def descriptor(_case_id: str) -> dict[str, object]:
            case = {
                "case_id": "A007-P",
                "cfg": SimpleNamespace(),
                "reference_root": Path("legacy-reference"),
                "reference_hashes": {},
                "source_equivalence": "legacy",
                "source_equivalence_boundary": {},
                "resource_reference": {"legacy": True},
                "output_root": Path("legacy-output"),
            }
            seen_cases.append(case)
            return case

        identity = {
            "record_sha256": "record",
            "source_sha": "source",
            "artifact_hashes": {},
            "physical_config": {},
            "resource_reference": {},
        }
        with tempfile.TemporaryDirectory(prefix="task036-args-") as temp_dir:
            temp_root = Path(temp_dir)
            existing_root = temp_root / "existing"
            existing_root.mkdir()
            new_root = temp_root / "new"
            with (
                patch.object(d2_runner, "MPI", fake_mpi),
                patch.object(d2_runner, "_d2_case_descriptor", side_effect=descriptor),
                patch.object(
                    d2_runner, "_build_d1_local_factor_setup", side_effect=sentinel
                ),
            ):
                with self.assertRaises(ValueError):
                    d2_runner.run_live_d2_block_direct_solve(
                        "A007-P", current_full3d_record=record_path
                    )
                with patch.object(
                    d2_runner,
                    "_validate_current_full3d_reference",
                    return_value=identity,
                ):
                    with self.assertRaises(FileExistsError):
                        d2_runner.run_live_d2_block_direct_solve(
                            "A007-P",
                            current_full3d_record=record_path,
                            current_full3d_reference_root=temp_root / "reference",
                            d2_output_root=existing_root,
                        )
                    with self.assertRaisesRegex(RuntimeError, "heavy body reached"):
                        d2_runner.run_live_d2_block_direct_solve(
                            "A007-P",
                            current_full3d_record=record_path,
                            current_full3d_reference_root=temp_root / "reference",
                            d2_output_root=new_root,
                        )
                with self.assertRaisesRegex(RuntimeError, "heavy body reached"):
                    d2_runner.run_live_d2_block_direct_solve("A007-P")
        self.assertEqual(seen_cases[-1]["reference_root"], Path("legacy-reference"))
        self.assertEqual(seen_cases[-1]["output_root"], Path("legacy-output"))

    def test_frozen_complex_gaussian_holdout_multiplier(self) -> None:
        observed = complex_gaussian_holdout_multiplier(1.0e-12 / 482.0, 20)
        self.assertAlmostEqual(observed, 2.2147082545082073, places=15)
        for delta, count in ((0.0, 20), (1.0, 20), (0.5, 0)):
            with self.assertRaises(ValueError):
                complex_gaussian_holdout_multiplier(delta, count)

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
