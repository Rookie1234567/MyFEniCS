from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from benchmarks.run_task033_memory_watchdog import (
    _authority_unreadable_requires_termination,
    _parse_args,
    _resource_readability_sample_is_formal,
    _task034_terminal_record_is_complete,
    _task034_terminal_worker_drain,
    _task034_authority_source_compatibility,
)
from benchmarks.task033_resource_gates import scaled_gate_limits
from benchmarks.task034_workstation_resource_gates import (
    GIB,
    task034_workstation_hybrid_launch_gate,
)

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = (
    ROOT
    / "benchmarks"
    / "cases"
    / "092_workstation_wsl_adaptive_scalability"
    / "records"
    / "workstation_hybrid_launch_authority.json"
)


class Task034WorkstationResourceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = json.loads(AUTHORITY.read_text())
        self.authority_sha = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
        self.reference_sha = self.authority["entries"][0]["full3d_reference"][
            "descriptor_sha256"
        ]
        self.p4_h5_entry = next(
            entry
            for entry in self.authority["entries"]
            if entry["matrix_key"] == "phase_f_p4_h5_s"
        )
        self.p4_anchor_sha = self.p4_h5_entry["assembly_resource_anchor"][
            "watchdog_record_sha256"
        ]
        self.p4_reference_sha = self.p4_h5_entry["full3d_reference"][
            "descriptor_sha256"
        ]
        self.p2_h5_entry = next(
            entry
            for entry in self.authority["entries"]
            if entry["matrix_key"] == "phase_f_p2_h5_s"
        )
        self.p2_h5_reference_sha = self.p2_h5_entry["full3d_reference"][
            "descriptor_sha256"
        ]
        self.p2_h5_p_entry = next(
            entry
            for entry in self.authority["entries"]
            if entry["matrix_key"] == "phase_f_p2_h5_p"
        )
        self.p2_h5_p_reference_sha = self.p2_h5_p_entry["full3d_reference"][
            "descriptor_sha256"
        ]
        self.p2_h3_entry = next(
            entry
            for entry in self.authority["entries"]
            if entry["matrix_key"] == "phase_f_p2_h3_s"
        )
        self.p2_h3_reference_sha = self.p2_h3_entry["full3d_reference"][
            "descriptor_sha256"
        ]
        self.p2_h2_entry = next(
            entry
            for entry in self.authority["entries"]
            if entry["matrix_key"] == "phase_f_p2_h2_s"
        )
        self.p2_h2_reference_sha = self.p2_h2_entry["full3d_reference"][
            "descriptor_sha256"
        ]

    def _gate(self, **overrides):
        kwargs = {
            "authority_expected_sha256": self.authority_sha,
            "authority_observed_sha256": self.authority_sha,
            "degree": 3,
            "h_nm": 3.0,
            "requested_modes": 160,
            "candidate_modes": 320,
            "solver_path": "modal-schur-memory-minimal",
            "comparison_solver_path": "fast",
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "effective_limit": {
                "effective_limit_bytes": 200 * GIB,
                "warning_bytes": 160 * GIB,
                "termination_bytes": 190 * GIB,
                "formula": "test fixture",
            },
            "warning_gib": 160.0,
            "terminate_gib": 190.0,
            "core_gate": {"pass": True},
            "mpi_size": 8,
            "available_physical_core_count": 48,
            "current_source_sha": "a" * 40,
            "source_compatibility": {"pass": True},
            "source_clean_verified": True,
            "authority_is_canonical": True,
            "authority_is_tracked": True,
            "external_watchdog_active": True,
            "full3d_reference_sha256": self.reference_sha,
        }
        kwargs.update(overrides)
        return task034_workstation_hybrid_launch_gate(
            self.authority, **kwargs
        )

    def test_explicit_workstation_gate_passes_complete_p3_h3_evidence(self) -> None:
        gate = self._gate()
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertFalse(
            gate["prediction"][
                "historical_task033_model_is_standalone_authority"
            ]
        )

    def test_explicit_workstation_gate_narrowly_authorizes_p2_h5_p(self) -> None:
        gate = self._gate(
            degree=2,
            h_nm=5.0,
            mpi_size=8,
            requested_modes=160,
            candidate_modes=320,
            polarization_kind="p",
            full3d_reference_sha256=self.p2_h5_p_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["matrix_key"], "phase_f_p2_h5_p")
        m80 = self._gate(
            degree=2,
            h_nm=5.0,
            mpi_size=8,
            requested_modes=80,
            candidate_modes=160,
            polarization_kind="p",
            full3d_reference_sha256=self.p2_h5_p_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertFalse(m80["pass"])
        self.assertIn("user_approved_p_polarization_scope", m80["failures"])
        mpi16 = self._gate(
            degree=2,
            h_nm=5.0,
            mpi_size=16,
            requested_modes=160,
            candidate_modes=320,
            polarization_kind="p",
            full3d_reference_sha256=self.p2_h5_p_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertFalse(mpi16["pass"])
        self.assertIn(
            "user_approved_p_polarization_scope", mpi16["failures"]
        )
        p3 = self._gate(
            degree=3,
            h_nm=5.0,
            mpi_size=8,
            requested_modes=160,
            candidate_modes=320,
            polarization_kind="p",
            full3d_reference_sha256=self.p2_h5_p_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertFalse(p3["pass"])
        self.assertIn("exactly_one_matching_p_h_entry", p3["failures"])

    def test_explicit_workstation_gate_passes_p4_e0_resource_anchor(self) -> None:
        gate = self._gate(
            degree=4,
            h_nm=5.0,
            full3d_reference_sha256=None,
            resource_anchor_sha256=self.p4_anchor_sha,
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["resource_anchor_kind"], "assembly_calibration")
        wrong_hash = self._gate(
            degree=4,
            h_nm=5.0,
            full3d_reference_sha256=None,
            resource_anchor_sha256="b" * 64,
        )
        self.assertFalse(wrong_hash["pass"])
        self.assertIn(
            "measured_resource_anchor_sha256_matches",
            wrong_hash["failures"],
        )

    def test_explicit_workstation_gate_passes_p4_post_e3_reference(self) -> None:
        gate = self._gate(
            degree=4,
            h_nm=5.0,
            full3d_reference_sha256=self.p4_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["resource_anchor_kind"], "full3d_reference")
        both = self._gate(
            degree=4,
            h_nm=5.0,
            full3d_reference_sha256=self.p4_reference_sha,
            resource_anchor_sha256=self.p4_anchor_sha,
        )
        self.assertFalse(both["pass"])
        self.assertIn(
            "measured_resource_anchor_kind_supported", both["failures"]
        )

    def test_explicit_workstation_gate_passes_phase_f_p2_h5_mpi8(self) -> None:
        gate = self._gate(
            degree=2,
            h_nm=5.0,
            mpi_size=8,
            full3d_reference_sha256=self.p2_h5_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["matrix_key"], "phase_f_p2_h5_s")
        self.assertEqual(gate["resource_anchor_kind"], "full3d_reference")
        self.assertFalse(
            self.p2_h5_entry["full3d_reference"][
                "derived_descriptor_written"
            ]
        )

    def test_explicit_workstation_gate_passes_phase_f_p2_h3_mpi8(self) -> None:
        gate = self._gate(
            degree=2,
            h_nm=3.0,
            mpi_size=8,
            full3d_reference_sha256=self.p2_h3_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["matrix_key"], "phase_f_p2_h3_s")
        self.assertEqual(gate["resource_anchor_kind"], "full3d_reference")
        self.assertFalse(
            self.p2_h3_entry["full3d_reference"][
                "derived_descriptor_written"
            ]
        )
        self.assertEqual(
            self.p2_h3_entry["staged_resource_evidence"][
                "factorization_peak_memory_gib"
            ],
            9.12186050415039,
        )

    def test_explicit_workstation_gate_passes_phase_f_p2_h2_mpi8(self) -> None:
        gate = self._gate(
            degree=2,
            h_nm=2.0,
            mpi_size=8,
            full3d_reference_sha256=self.p2_h2_reference_sha,
            resource_anchor_sha256=None,
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["matrix_key"], "phase_f_p2_h2_s")
        self.assertEqual(gate["resource_anchor_kind"], "full3d_reference")
        self.assertFalse(
            self.p2_h2_entry["full3d_reference"][
                "derived_descriptor_written"
            ]
        )
        self.assertEqual(
            self.p2_h2_entry["staged_resource_evidence"][
                "factorization_peak_memory_gib"
            ],
            32.245399475097656,
        )

    def test_gate_fails_closed_on_hash_threshold_and_old_model_override(self) -> None:
        wrong_hash = self._gate(authority_observed_sha256="b" * 64)
        self.assertFalse(wrong_hash["pass"])
        self.assertIn("authority_raw_sha256_matches", wrong_hash["failures"])
        wrong_threshold = self._gate(warning_gib=161.0)
        self.assertFalse(wrong_threshold["pass"])
        self.assertIn(
            "warning_threshold_matches_live_task034_gate",
            wrong_threshold["failures"],
        )
        mutated = copy.deepcopy(self.authority)
        mutated["entries"][0]["workstation_prediction"][
            "task033_old_model_is_launch_authority"
        ] = True
        gate = task034_workstation_hybrid_launch_gate(
            mutated,
            **{
                key: value
                for key, value in self._gate_arguments().items()
            },
        )
        self.assertFalse(gate["pass"])
        self.assertIn(
            "task033_old_model_not_standalone_authority", gate["failures"]
        )

    def _gate_arguments(self):
        return {
            "authority_expected_sha256": self.authority_sha,
            "authority_observed_sha256": self.authority_sha,
            "degree": 3,
            "h_nm": 3.0,
            "requested_modes": 160,
            "candidate_modes": 320,
            "solver_path": "modal-schur-memory-minimal",
            "comparison_solver_path": "fast",
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "effective_limit": {
                "effective_limit_bytes": 200 * GIB,
                "warning_bytes": 160 * GIB,
                "termination_bytes": 190 * GIB,
                "formula": "test fixture",
            },
            "warning_gib": 160.0,
            "terminate_gib": 190.0,
            "core_gate": {"pass": True},
            "mpi_size": 8,
            "available_physical_core_count": 48,
            "current_source_sha": "a" * 40,
            "source_compatibility": {"pass": True},
            "source_clean_verified": True,
            "authority_is_canonical": True,
            "authority_is_tracked": True,
            "external_watchdog_active": True,
            "full3d_reference_sha256": self.reference_sha,
        }

    def test_workstation_gate_rejects_oversubscribed_mpi(self) -> None:
        gate = self._gate(
            mpi_size=32,
            available_physical_core_count=16,
        )
        self.assertFalse(gate["pass"])
        self.assertIn(
            "requested_mpi_size_does_not_oversubscribe",
            gate["failures"],
        )
        qualified = self._gate(
            mpi_size=32,
            available_physical_core_count=48,
        )
        self.assertTrue(qualified["pass"], qualified["failures"])

    def test_task034_ignores_only_post_exit_readability_race(self) -> None:
        self.assertFalse(
            _resource_readability_sample_is_formal(
                task034_workstation_gate=True, process_running=False
            )
        )
        self.assertTrue(
            _resource_readability_sample_is_formal(
                task034_workstation_gate=True, process_running=True
            )
        )
        self.assertTrue(
            _resource_readability_sample_is_formal(
                task034_workstation_gate=False, process_running=False
            )
        )

    def test_task034_ignores_only_complete_terminal_worker_drain(self) -> None:
        complete_drain = {
            "task034_workstation_gate": True,
            "process_running": True,
            "authority_readable": False,
            "stage": "record_and_release",
            "terminal_record_complete": True,
            "live_worker_count": 0,
        }
        self.assertTrue(_task034_terminal_worker_drain(**complete_drain))
        self.assertFalse(
            _resource_readability_sample_is_formal(
                task034_workstation_gate=True,
                process_running=True,
                terminal_worker_drain=True,
            )
        )
        for key, value in (
            ("task034_workstation_gate", False),
            ("authority_readable", True),
            ("stage", "middle_plane_reconstruction"),
            ("terminal_record_complete", False),
            ("live_worker_count", 1),
            ("live_worker_count", None),
        ):
            incomplete = complete_drain | {key: value}
            self.assertFalse(_task034_terminal_worker_drain(**incomplete))
        self.assertTrue(
            _resource_readability_sample_is_formal(
                task034_workstation_gate=False,
                process_running=True,
                terminal_worker_drain=True,
            )
        )

    def test_task034_terminal_record_requires_complete_schema_v1(self) -> None:
        complete = {
            "schema_version": 1,
            "benchmark_id": "task033_high_order_or_buffer_hybrid_direct",
            "timestamp_utc": "2026-07-18T17:31:57+00:00",
            "status": "physical_integration_pass_mode_convergence_pending",
            "qualification": {},
            "solve": {},
            "gates": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solver_record.json"
            path.write_text(json.dumps(complete))
            self.assertTrue(_task034_terminal_record_is_complete(path))
            for key in complete:
                incomplete = complete.copy()
                incomplete.pop(key)
                path.write_text(json.dumps(incomplete))
                self.assertFalse(_task034_terminal_record_is_complete(path))
            wrong_schema = complete | {"schema_version": "1"}
            path.write_text(json.dumps(wrong_schema))
            self.assertFalse(_task034_terminal_record_is_complete(path))

    def test_only_formal_live_unreadable_authority_terminates(self) -> None:
        required = {
            "process_running": True,
            "readability_sample_is_formal": True,
            "authority_readable": False,
        }
        self.assertTrue(_authority_unreadable_requires_termination(**required))
        for key, value in (
            ("process_running", False),
            ("readability_sample_is_formal", False),
            ("authority_readable", True),
        ):
            self.assertFalse(
                _authority_unreadable_requires_termination(
                    **(required | {key: value})
                )
            )

    def test_task033_gate_still_caps_larger_hosts_at_14_gib(self) -> None:
        limits = scaled_gate_limits(200.0)
        self.assertEqual(limits["effective_hard_budget_gib"], 14.0)
        self.assertEqual(limits["host_hard_budget_gib"], 14.0)

    def test_cli_opt_in_is_narrowly_scoped(self) -> None:
        args = _parse_args(
            [
                "--target", "hybrid",
                "--case-label", "task034_p3_h3_m160",
                "--degree", "3",
                "--h-nm", "3",
                "--mpi-size", "4",
                "--requested-modes", "160",
                "--candidate-modes", "320",
                "--full3d-reference", "reference.json",
                "--high-order-core-evidence-file", "core.json",
                "--high-order-core-evidence-sha256", "c" * 64,
                "--verified-clean-sha", "d" * 40,
                "--host-environment-id", "WSL2-Ubuntu-24.04",
                "--task034-workstation-gate",
                "--task034-workstation-resource-authority-sha256",
                self.authority_sha,
            ]
        )
        self.assertTrue(args.task034_workstation_gate)
        self.assertEqual(args.requested_modes, 160)
        p4_args = _parse_args(
            [
                "--target", "hybrid",
                "--case-label", "task034_p4_h5_m80",
                "--degree", "4",
                "--h-nm", "5",
                "--mpi-size", "4",
                "--requested-modes", "80",
                "--candidate-modes", "160",
                "--task034-workstation-resource-anchor", "assembly.json",
                "--high-order-core-evidence-file", "core.json",
                "--high-order-core-evidence-sha256", "c" * 64,
                "--verified-clean-sha", "d" * 40,
                "--host-environment-id", "WSL2-Ubuntu-24.04",
                "--task034-workstation-gate",
                "--task034-workstation-resource-authority-sha256",
                self.authority_sha,
            ]
        )
        self.assertIsNone(p4_args.full3d_reference)
        self.assertEqual(
            p4_args.task034_workstation_resource_anchor,
            Path("assembly.json"),
        )
        p4_closure_args = _parse_args(
            [
                "--target", "hybrid",
                "--case-label", "task034_p4_h5_m160_closure",
                "--degree", "4",
                "--h-nm", "5",
                "--mpi-size", "4",
                "--requested-modes", "160",
                "--candidate-modes", "320",
                "--full3d-reference", "p4_reference.json",
                "--high-order-core-evidence-file", "core.json",
                "--high-order-core-evidence-sha256", "c" * 64,
                "--verified-clean-sha", "d" * 40,
                "--host-environment-id", "WSL2-Ubuntu-24.04",
                "--task034-workstation-gate",
                "--task034-workstation-resource-authority-sha256",
                self.authority_sha,
            ]
        )
        self.assertEqual(
            p4_closure_args.full3d_reference, Path("p4_reference.json")
        )
        self.assertIsNone(
            p4_closure_args.task034_workstation_resource_anchor
        )
        phase_f_args = _parse_args(
            [
                "--target", "hybrid",
                "--case-label", "task034_phase_f_p2_h5_m80_mpi8",
                "--degree", "2",
                "--h-nm", "5",
                "--mpi-size", "8",
                "--requested-modes", "80",
                "--candidate-modes", "160",
                "--full3d-reference", "p2_h5_watchdog.json",
                "--verified-clean-sha", "d" * 40,
                "--host-environment-id", "WSL2-Ubuntu-24.04",
                "--task034-workstation-gate",
                "--task034-workstation-resource-authority-sha256",
                self.authority_sha,
            ]
        )
        self.assertEqual(phase_f_args.mpi_size, 8)
        self.assertEqual(
            phase_f_args.full3d_reference,
            Path("p2_h5_watchdog.json"),
        )
        p_args = _parse_args(
            [
                "--target", "hybrid",
                "--case-label", "task034_p2_h5_p_m160_mpi8",
                "--degree", "2",
                "--h-nm", "5",
                "--mpi-size", "8",
                "--requested-modes", "160",
                "--candidate-modes", "320",
                "--polarization-kind", "p",
                "--full3d-reference", "p2_h5_p_watchdog.json",
                "--verified-clean-sha", "d" * 40,
                "--host-environment-id", "WSL2-Ubuntu-24.04",
                "--task034-workstation-gate",
                "--task034-workstation-resource-authority-sha256",
                self.authority_sha,
            ]
        )
        self.assertEqual(p_args.polarization_kind, "p")
        self.assertEqual(p_args.requested_modes, 160)
        self.assertEqual(
            p_args.full3d_reference,
            Path("p2_h5_p_watchdog.json"),
        )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target", "hybrid",
                    "--case-label", "task033_mpi8_must_not_expand",
                    "--degree", "2",
                    "--h-nm", "5",
                    "--mpi-size", "8",
                    "--requested-modes", "80",
                    "--candidate-modes", "160",
                    "--full3d-reference", "p2_h5_watchdog.json",
                    "--verified-clean-sha", "d" * 40,
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target", "hybrid",
                    "--case-label", "task034_p4_h5_bad_two_anchors",
                    "--degree", "4",
                    "--h-nm", "5",
                    "--mpi-size", "4",
                    "--requested-modes", "160",
                    "--candidate-modes", "320",
                    "--full3d-reference", "p4_reference.json",
                    "--task034-workstation-resource-anchor", "assembly.json",
                    "--high-order-core-evidence-file", "core.json",
                    "--high-order-core-evidence-sha256", "c" * 64,
                    "--verified-clean-sha", "d" * 40,
                    "--host-environment-id", "WSL2-Ubuntu-24.04",
                    "--task034-workstation-gate",
                    "--task034-workstation-resource-authority-sha256",
                    self.authority_sha,
                ]
            )

    def test_reference_source_compatibility_audit_is_fail_closed(self) -> None:
        p3_reference_sha = next(
            entry["full3d_reference"]["source_sha"]
            for entry in self.authority["entries"]
            if entry["degree"] == 3 and entry["h_nm"] == 3.0
        )
        exact = _task034_authority_source_compatibility(
            self.authority,
            degree=3,
            h_nm=3.0,
            current_source_sha=p3_reference_sha,
        )
        self.assertTrue(exact["pass"], exact["failures"])
        p4_exact = _task034_authority_source_compatibility(
            self.authority,
            degree=4,
            h_nm=5.0,
            current_source_sha="e0917859aa53cd6cff6bc3bc411b29255aeac9e2",
        )
        self.assertTrue(p4_exact["pass"], p4_exact["failures"])
        p2_exact = _task034_authority_source_compatibility(
            self.authority,
            degree=2,
            h_nm=5.0,
            current_source_sha=(
                "6b30df2d445db42823139f57dd3960ec2aa7a116"
            ),
        )
        self.assertTrue(p2_exact["pass"], p2_exact["failures"])

        p2_p_reference_sha = self.p2_h5_p_entry["full3d_reference"][
            "source_sha"
        ]
        p2_p_exact = _task034_authority_source_compatibility(
            self.authority,
            degree=2,
            h_nm=5.0,
            polarization_kind="p",
            current_source_sha=p2_p_reference_sha,
        )
        self.assertTrue(p2_p_exact["pass"], p2_p_exact["failures"])

        p2_reference_sha = next(
            entry["full3d_reference"]["source_sha"]
            for entry in self.authority["entries"]
            if entry["degree"] == 2
            and entry["h_nm"] == 5.0
        )
        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=(
                p2_reference_sha,
                "src/modes/mode_classification.py\n"
                "benchmarks/run_task032_phase6_augmented.py\n"
                "benchmarks/task034_mpi_identity.py\n"
                "src/common/distributed_matrix_diagnostics.py\n"
                "benchmarks/task034_numerical_blob_checker.py\n"
                "src/solvers/hybrid_fem_modal_schur_direct.py\n"
                "src/test/test_mode_overlap.py",
            ),
        ):
            hybrid_only = _task034_authority_source_compatibility(
                self.authority,
                degree=2,
                h_nm=5.0,
                current_source_sha="b" * 40,
            )
        self.assertTrue(hybrid_only["pass"], hybrid_only["failures"])
        self.assertEqual(
            hybrid_only["component_disjoint_numerical_changed_paths"],
            [
                "src/modes/mode_classification.py",
                "benchmarks/run_task032_phase6_augmented.py",
                "benchmarks/task034_mpi_identity.py",
                "src/common/distributed_matrix_diagnostics.py",
                "src/solvers/hybrid_fem_modal_schur_direct.py",
            ],
        )
        self.assertEqual(hybrid_only["disallowed_changed_paths"], [])

        missing = _task034_authority_source_compatibility(
            {}, degree=3, h_nm=3.0, current_source_sha="a" * 40
        )
        self.assertFalse(missing["pass"])


if __name__ == "__main__":
    unittest.main()