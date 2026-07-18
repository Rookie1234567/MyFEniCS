from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

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
            "current_source_sha": "a" * 40,
            "source_compatibility": {"pass": True},
            "source_clean_verified": True,
            "authority_is_canonical": True,
            "authority_is_tracked": True,
            "external_watchdog_active": True,
            "full3d_reference_sha256": self.reference_sha,
        }

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

    def test_reference_source_compatibility_audit_is_fail_closed(self) -> None:
        exact = _task034_authority_source_compatibility(
            self.authority,
            degree=3,
            h_nm=3.0,
            current_source_sha="685c9a7e8cd9499070e5d1abb11957f6014444e7",
        )
        self.assertTrue(exact["pass"], exact["failures"])
        missing = _task034_authority_source_compatibility(
            {}, degree=3, h_nm=3.0, current_source_sha="a" * 40
        )
        self.assertFalse(missing["pass"])


if __name__ == "__main__":
    unittest.main()