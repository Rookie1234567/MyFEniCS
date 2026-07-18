from __future__ import annotations

import json
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmarks.run_task033_memory_watchdog import (
    _case090_source_compatibility,
    _parse_args,
    _watchdog_source_after,
    _watchdog_source_before,
    _worker_command,
)
from benchmarks.task033_watchdog_launch import (
    DEFAULT_RESOURCE_MATRIX,
    high_order_core_evidence_gate,
    hybrid_launch_gate,
)
from benchmarks.task033_case090_pde_core import attach_evidence_sha256
from benchmarks.task033_hybrid_funnel import build_hybrid_funnel


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "a" * 40


def _funnel_shard(mode_count: int, delta: float) -> dict:
    return {
        "schema_version": 2,
        "benchmark_id": "task033_external_memory_watchdog",
        "status": "measured_shard_pass",
        "target": "hybrid",
        "return_code": 0,
        "command": ["mpiexec", "-n", "4", "python", "hybrid"],
        "requested_modes": mode_count,
        "candidate_modes": 2 * mode_count,
        "formal_pass": True,
        "numeric_pass": True,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "memory_authority_pass": True,
        "resource_authority": {"gate": {"pass": True}},
        "source_gate": {"pass": True},
        "launch_gate": {"pass": True},
        "source": {
            "commit_sha": SOURCE_SHA,
            "verified_clean_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "source_clean_verified": True,
        },
        "measurements": {
            "case": {
                "degree": 1,
                "h_nm": 5.0,
                "wavelength_nm": 13.5,
                "incident_grazing_deg": 10.0,
                "polarization_kind": "s",
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "graded_reference_h_nm": None,
                "graded_plan_hash": None,
                "requested_modes_per_direction": mode_count,
            },
            "hybrid_system": {
                "primary_solver_path": "modal-schur-memory-minimal"
            },
            "solve": {"true_relative_residual": 1.0e-12},
            "port_power": {
                "R_total": 0.1 + delta,
                "T_total": 0.7 - delta,
                "A_balance": 0.2,
            },
            "external_diffraction_orders": [
                {
                    "side": "top",
                    "m": 0,
                    "n": 0,
                    "polarization": "s",
                    "propagating": True,
                    "outgoing_amplitude_at_boundary": [
                        0.4 + delta,
                        -0.2,
                    ],
                    "power_ratio": 0.2 + delta,
                }
            ],
            "gates": {
                "monolithic_true_relative_residual_le_1e-9": True,
                "sampled_interface_e_t_relative_l2_le_5e-3": True,
                "sampled_interface_h_t_relative_l2_le_1e-2": True,
            },
            "qualification": {
                "integration_pass": True,
                "algebraic_chain_pass": True,
                "physical_field_gates_pass": True,
                "task033_physical_truncation_allowed": True,
            },
        },
    }


def _m160_nonconvergence_evidence() -> dict:
    descriptors = [
        {
            "path": f"m{mode}.json",
            "sha256": str(mode // 40) * 64,
            "mode_count_per_direction": mode,
            "source_commit_full_sha": SOURCE_SHA,
            "data_identity": "measured_external_watchdog_summary",
        }
        for mode in (80, 120, 160)
    ]
    return build_hybrid_funnel(
        [
            _funnel_shard(80, 3.0e-3),
            _funnel_shard(120, 2.0e-3),
            _funnel_shard(160, 1.0e-3),
        ],
        source_descriptors=descriptors,
    )


class Task033MemoryWatchdogContractTests(unittest.TestCase):
    def test_high_order_core_uses_canonical_evidence_not_file_sha(self) -> None:
        evidence = attach_evidence_sha256(
            {
                "record_type": "high_order_floquet_core_gate_result",
                "all_core_gates_passed": True,
                "identity": {
                    "is_pde_run": True,
                    "is_solver_pass": True,
                    "tracked_source_dirty": False,
                    "source_commit_full_sha": SOURCE_SHA,
                },
                "coverage": [
                    {"degree": degree, "mpi_size": mpi_size}
                    for degree in (3, 4)
                    for mpi_size in (1, 2, 4)
                ],
            }
        )
        canonical_sha = evidence["evidence_sha256"]
        accepted = high_order_core_evidence_gate(
            3,
            evidence,
            expected_sha256=canonical_sha,
            current_source_sha=SOURCE_SHA,
        )
        self.assertTrue(accepted["pass"], accepted["failures"])

        rendered_file_sha = hashlib.sha256(
            (json.dumps(evidence, indent=2) + "\n").encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(rendered_file_sha, canonical_sha)
        rejected = high_order_core_evidence_gate(
            3,
            evidence,
            expected_sha256=rendered_file_sha,
            current_source_sha=SOURCE_SHA,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn("expected_sha256_matches", rejected["failures"])

    def test_high_order_core_accepts_only_audited_non_numerical_descendant(self) -> None:
        current_sha = "b" * 40
        evidence = attach_evidence_sha256(
            {
                "record_type": "high_order_floquet_core_gate_result",
                "all_core_gates_passed": True,
                "identity": {
                    "is_pde_run": True,
                    "is_solver_pass": True,
                    "tracked_source_dirty": False,
                    "source_commit_full_sha": SOURCE_SHA,
                },
                "coverage": [
                    {"degree": degree, "mpi_size": mpi_size}
                    for degree in (3, 4)
                    for mpi_size in (1, 2, 4)
                ],
            }
        )
        compatibility = {
            "pass": True,
            "evidence_source_sha": SOURCE_SHA,
            "current_source_sha": current_sha,
            "numerical_source_unchanged": True,
            "changed_paths": ["benchmarks/task033_qep_qualification.py"],
            "disallowed_changed_paths": [],
            "failures": [],
        }
        accepted = high_order_core_evidence_gate(
            4,
            evidence,
            expected_sha256=evidence["evidence_sha256"],
            current_source_sha=current_sha,
            source_compatibility=compatibility,
        )
        self.assertTrue(accepted["pass"], accepted["failures"])
        self.assertEqual(
            accepted["source_reuse_kind"],
            "audited_non_numerical_descendant",
        )

        forged = {**compatibility, "current_source_sha": "c" * 40}
        rejected = high_order_core_evidence_gate(
            4,
            evidence,
            expected_sha256=evidence["evidence_sha256"],
            current_source_sha=current_sha,
            source_compatibility=forged,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "same_full_source_sha_or_audited_non_numerical_descendant",
            rejected["failures"],
        )

    def test_case090_source_compatibility_is_component_scoped(self) -> None:
        evidence = {"identity": {"source_commit_full_sha": SOURCE_SHA}}
        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=(
                SOURCE_SHA,
                "docs/README.md\n"
                "src/test/test_x.py\n"
                "src/coupling/modal_trace_projection.py\n"
                "benchmarks/task033_phaseC.py",
            ),
        ):
            accepted = _case090_source_compatibility(
                evidence, current_source_sha="b" * 40
            )
        self.assertTrue(accepted["pass"], accepted["failures"])
        self.assertTrue(accepted["case090_core_source_unchanged"])
        self.assertEqual(
            accepted["component_disjoint_numerical_changed_paths"],
            ["src/coupling/modal_trace_projection.py"],
        )
        self.assertEqual(
            accepted["compatibility_scope"],
            "case090_pure3d_floquet_core",
        )

        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=(SOURCE_SHA, "benchmarks/run_task033_qep_matrix.py"),
        ):
            rejected = _case090_source_compatibility(
                evidence, current_source_sha="b" * 40
            )
        self.assertFalse(rejected["pass"])
        self.assertEqual(
            rejected["disallowed_changed_paths"],
            ["benchmarks/run_task033_qep_matrix.py"],
        )

    def test_source_preflight_rejects_nonignored_untracked_before_and_after(self) -> None:
        sha = "a" * 40

        def dirty_git(*args: str) -> str:
            if args[:2] == ("rev-parse", "HEAD"):
                return sha
            self.assertEqual(
                args,
                ("status", "--short", "--untracked-files=all"),
            )
            return "?? uncommitted_solver.py"

        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=dirty_git,
        ):
            source = _watchdog_source_before(sha)
        self.assertFalse(source["source_clean_verified"])
        self.assertEqual(
            source["nonignored_untracked_before"], ["uncommitted_solver.py"]
        )

        clean_source = {
            **source,
            "tracked_status_before": "",
            "worktree_status_before": "",
            "nonignored_untracked_before": [],
            "source_clean_verified": True,
        }
        with mock.patch(
            "benchmarks.run_task033_memory_watchdog._git",
            side_effect=dirty_git,
        ):
            after = _watchdog_source_after(clean_source)
        self.assertFalse(after["source_stable_during_run"])
        self.assertFalse(after["source_clean_verified"])
        self.assertEqual(
            after["nonignored_untracked_after"], ["uncommitted_solver.py"]
        )

    def test_task032_anchor_default_reuse_and_explicit_same_sha_requalification(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        common = {
            "degree": 2,
            "h_nm": 3.0,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 16 * 1024**3,
            "warning_gib": 11.5,
            "terminate_gib": 13.0,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": "b" * 40,
        }
        default = hybrid_launch_gate(
            matrix, requested_modes=80, candidate_modes=160, **common
        )
        self.assertFalse(default["pass"])
        self.assertIn(
            "existing_uniform_anchor_not_relaunched_without_variant",
            default["failures"],
        )
        for requested_modes in (80, 120, 160):
            with self.subTest(requested_modes=requested_modes):
                gate = hybrid_launch_gate(
                    matrix,
                    requested_modes=requested_modes,
                    candidate_modes=2 * requested_modes,
                    task033_same_sha_anchor_requalification=True,
                    source_clean_verified=True,
                    resource_matrix_is_canonical=True,
                    resource_matrix_is_tracked=True,
                    external_watchdog_active=True,
                    **common,
                )
                self.assertTrue(gate["pass"], gate["failures"])
                requalification = gate["task033_anchor_requalification"]
                self.assertTrue(requalification["allowed"])
                self.assertEqual(
                    requalification["reason"],
                    "Task033 same-SHA formal requalification",
                )
                self.assertEqual(
                    requalification["required_complete_mode_funnel"],
                    [80, 120, 160],
                )
                self.assertTrue(requalification["does_not_replace_task032_anchor"])

        denied = hybrid_launch_gate(
            matrix,
            requested_modes=80,
            candidate_modes=160,
            task033_same_sha_anchor_requalification=True,
            source_clean_verified=False,
            resource_matrix_is_canonical=True,
            resource_matrix_is_tracked=True,
            external_watchdog_active=True,
            **common,
        )
        self.assertFalse(denied["pass"])
        self.assertIn(
            "task033_anchor_requalification_request_is_scoped", denied["failures"]
        )

    def test_qep_command_carries_every_formal_runtime_attestation(self) -> None:
        args = _parse_args(
            [
                "--target",
                "qep",
                "--case-label",
                "qep_air_p3_h5",
                "--degree",
                "3",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--material-kind",
                "air",
                "--verified-clean-sha",
                "a" * 40,
                "--high-order-core-evidence-sha256",
                "b" * 64,
            ]
        )
        args._qep_effective_limit_gib = 9.25
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(
                args, root / "record.json", root / "stages.jsonl"
            )
        rendered = " ".join(command)
        self.assertIn("benchmarks.run_task033_qep_matrix", rendered)
        self.assertIn("--no-swap-verified", command)
        self.assertIn("--watchdog-enabled-verified", command)
        self.assertIn("--one-large-case-verified", command)
        self.assertIn("--left-candidate-modes", command)
        self.assertEqual(
            command[command.index("--left-candidate-modes") + 1], "16"
        )
        self.assertIn("b" * 64, command)
        self.assertIn("--container-limit-gib", command)
        self.assertIn("9.25", command)

    def test_twelve_gib_runtime_guard_fits_smaller_live_host_ceiling(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "requested_modes": 80,
            "candidate_modes": 160,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "container_limit_bytes": 13 * 1024**3,
            "host_available_memory_bytes": int(12.75 * 1024**3),
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
        }
        wider = hybrid_launch_gate(
            matrix,
            warning_gib=10.678571428571429,
            terminate_gib=12.071428571428571,
            **common,
        )
        self.assertFalse(wider["pass"])
        self.assertIn(
            "warning_threshold_not_wider_than_scaled_gate",
            wider["failures"],
        )
        self.assertIn(
            "termination_threshold_not_wider_than_scaled_gate",
            wider["failures"],
        )

        guarded = hybrid_launch_gate(
            matrix,
            warning_gib=9.857142857142856,
            terminate_gib=11.142857142857142,
            **common,
        )
        self.assertTrue(guarded["pass"], guarded["failures"])
        self.assertEqual(
            guarded["live_scaled_limits"]["effective_hard_budget_gib"],
            12.75,
        )
        undersized = hybrid_launch_gate(
            matrix,
            warning_gib=9.857142857142856,
            terminate_gib=11.142857142857142,
            **{
                **common,
                "host_available_memory_bytes": 12 * 1024**3 - 1,
            },
        )
        self.assertFalse(undersized["pass"])
        self.assertIn(
            "warning_threshold_not_wider_than_scaled_gate",
            undersized["failures"],
        )
        self.assertIn(
            "termination_threshold_not_wider_than_scaled_gate",
            undersized["failures"],
        )

    def test_hybrid_command_preserves_degree_buffer_and_graded_policy(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "graded_h5_m80",
                "--degree",
                "2",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--requested-modes",
                "80",
                "--candidate-modes",
                "160",
                "--graded-reference-h",
                "5",
                "--full3d-reference",
                "records/p2_h5_reference.json",
                "--verified-clean-sha",
                "c" * 40,
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(
                args, root / "record.json", root / "stages.jsonl"
            )
        rendered = " ".join(command)
        self.assertIn("benchmarks.run_task032_phase6_augmented", rendered)
        self.assertIn("--degree 2", rendered)
        self.assertIn("--requested-modes 80", rendered)
        self.assertIn("--candidate-modes 160", rendered)
        self.assertIn("--graded-reference-h 5.0", rendered)
        self.assertIn("--incident-grazing-deg 10.0", rendered)
        self.assertIn("--polarization-kind s", rendered)
        self.assertIn("--comparison-solver-path fast", rendered)
        self.assertEqual(
            Path(command[command.index("--full3d-reference") + 1]),
            Path("records/p2_h5_reference.json"),
        )
        self.assertIn("--memory-stages", command)

    def test_hybrid_candidate_pool_is_exactly_twice_requested_modes(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        evidence = _m160_nonconvergence_evidence()
        digest = "f" * 64
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 20 * 1024**3,
            "warning_gib": 11.0,
            "terminate_gib": 12.5,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
        }
        for requested_modes in (80, 120, 160, 240):
            conditional = (
                {
                    "m160_funnel_evidence": evidence,
                    "expected_m160_funnel_sha256": digest,
                    "observed_m160_funnel_sha256": digest,
                }
                if requested_modes == 240
                else {}
            )
            with self.subTest(requested_modes=requested_modes, relation="exact"):
                gate = hybrid_launch_gate(
                    matrix,
                    requested_modes=requested_modes,
                    candidate_modes=2 * requested_modes,
                    **conditional,
                    **common,
                )
                self.assertTrue(gate["pass"], gate["failures"])
                self.assertTrue(
                    gate["checks"]["candidate_pool_is_twice_requested_modes"]
                )
            for candidate_modes in (
                2 * requested_modes - 1,
                2 * requested_modes + 1,
            ):
                with self.subTest(
                    requested_modes=requested_modes,
                    candidate_modes=candidate_modes,
                ):
                    gate = hybrid_launch_gate(
                        matrix,
                        requested_modes=requested_modes,
                        candidate_modes=candidate_modes,
                        **conditional,
                        **common,
                    )
                    self.assertFalse(gate["pass"])
                    self.assertIn(
                        "candidate_pool_is_twice_requested_modes",
                        gate["failures"],
                    )

    def test_hybrid_nondefault_physics_and_minimal_comparison_are_forwarded(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "p1_h5_augmented_vs_minimal_p",
                "--degree",
                "1",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--requested-modes",
                "80",
                "--candidate-modes",
                "160",
                "--solver-path",
                "augmented",
                "--compare-modal-schur",
                "--comparison-solver-path",
                "minimal",
                "--incident-grazing-deg",
                "5",
                "--polarization-kind",
                "p",
                "--verified-clean-sha",
                SOURCE_SHA,
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(
                args, root / "record.json", root / "stages.jsonl"
            )
        rendered = " ".join(command)
        self.assertIn("--incident-grazing-deg 5.0", rendered)
        self.assertIn("--polarization-kind p", rendered)
        self.assertIn("--comparison-solver-path minimal", rendered)

        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "requested_modes": 80,
            "candidate_modes": 160,
            "solver_path": "augmented",
            "compare_modal_schur": True,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 5.0,
            "polarization_kind": "p",
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 20 * 1024**3,
            "warning_gib": 11.0,
            "terminate_gib": 12.5,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
        }
        fast = hybrid_launch_gate(
            matrix, comparison_solver_path="fast", **common
        )
        self.assertFalse(fast["pass"])
        self.assertIn(
            "task033_augmented_comparison_uses_memory_minimal",
            fast["failures"],
        )
        minimal = hybrid_launch_gate(
            matrix, comparison_solver_path="minimal", **common
        )
        self.assertTrue(minimal["pass"], minimal["failures"])
        self.assertEqual(
            minimal["physical_case"]["comparison_solver_path"], "minimal"
        )
        self.assertEqual(
            minimal["independent_prediction"][
                "uncalibrated_incidence_polarization_contingency"
            ],
            1.25,
        )

    def test_m240_requires_bound_same_case_measured_m160_nonconvergence(self) -> None:
        matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
        evidence = _m160_nonconvergence_evidence()
        self.assertEqual(evidence["status"], "not_qualified")
        digest = "f" * 64
        common = {
            "degree": 1,
            "h_nm": 5.0,
            "requested_modes": 240,
            "candidate_modes": 480,
            "solver_path": "modal-schur-memory-minimal",
            "compare_modal_schur": False,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "graded_reference_h": None,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "container_limit_bytes": 14 * 1024**3,
            "host_available_memory_bytes": 20 * 1024**3,
            "warning_gib": 11.0,
            "terminate_gib": 12.5,
            "core_evidence": None,
            "expected_core_sha256": None,
            "current_source_sha": SOURCE_SHA,
            "expected_m160_funnel_sha256": digest,
            "observed_m160_funnel_sha256": digest,
        }
        passed = hybrid_launch_gate(
            matrix, m160_funnel_evidence=evidence, **common
        )
        self.assertTrue(passed["pass"], passed["failures"])
        self.assertTrue(passed["conditional_m240_evidence"]["pass"])
        self.assertEqual(
            passed["independent_prediction"][
                "conditional_mode_workspace_contingency"
            ],
            2.25,
        )

        missing = hybrid_launch_gate(
            matrix, m160_funnel_evidence=None, **common
        )
        self.assertFalse(missing["pass"])
        stale_case = copy.deepcopy(evidence)
        stale_case["case"]["h_nm"] = 3.0
        stale = hybrid_launch_gate(
            matrix, m160_funnel_evidence=stale_case, **common
        )
        self.assertFalse(stale["pass"])
        wrong_digest = hybrid_launch_gate(
            matrix,
            m160_funnel_evidence=evidence,
            **{**common, "observed_m160_funnel_sha256": "e" * 64},
        )
        self.assertFalse(wrong_digest["pass"])

    def test_task32_comparison_contract_records_selected_builder(self) -> None:
        source = (
            ROOT / "benchmarks" / "run_task032_phase6_augmented.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"--comparison-solver-path"', source)
        self.assertIn('choices=("fast", "minimal")', source)
        self.assertIn(
            '"comparison_solver_path": comparison_solver_path', source
        )
        self.assertIn("build_hybrid_modal_schur_memory_minimal_system", source)

    def test_contract_rejects_missing_qep_material_and_bad_thresholds(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "qep",
                    "--case-label",
                    "missing_material",
                    "--degree",
                    "1",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--verified-clean-sha",
                    "d" * 40,
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "qep",
                    "--case-label",
                    "undersampled_left_pool",
                    "--degree",
                    "1",
                    "--h-nm",
                    "3",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "8",
                    "--candidate-modes",
                    "8",
                    "--material-kind",
                    "air",
                    "--verified-clean-sha",
                    "d" * 40,
                ]
            )
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "bad_threshold",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--verified-clean-sha",
                    "e" * 40,
                    "--warning-gib",
                    "13",
                    "--terminate-gib",
                    "12",
                ]
            )

    def test_anchor_requalification_cli_is_explicit_and_narrow(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "same_case_m80",
                "--degree",
                "2",
                "--h-nm",
                "3",
                "--mpi-size",
                "1",
                "--requested-modes",
                "80",
                "--candidate-modes",
                "160",
                "--verified-clean-sha",
                "f" * 40,
                "--task033-same-sha-anchor-requalification",
            ]
        )
        self.assertTrue(args.task033_same_sha_anchor_requalification)

        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "wrong_anchor",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "80",
                    "--candidate-modes",
                    "160",
                    "--verified-clean-sha",
                    "f" * 40,
                    "--task033-same-sha-anchor-requalification",
                ]
            )

    def test_hybrid_cli_accepts_only_exact_two_m_candidate_pools(self) -> None:
        for requested_modes in (80, 120, 160, 240):
            base = [
                "--target",
                "hybrid",
                "--case-label",
                f"m{requested_modes}",
                "--degree",
                "1",
                "--h-nm",
                "5",
                "--mpi-size",
                "1",
                "--requested-modes",
                str(requested_modes),
                "--verified-clean-sha",
                "f" * 40,
            ]
            if requested_modes == 240:
                base.extend(
                    [
                        "--m160-funnel-evidence-file",
                        "m160_funnel.json",
                        "--m160-funnel-evidence-sha256",
                        "a" * 64,
                    ]
                )
            with self.subTest(requested_modes=requested_modes, relation="exact"):
                args = _parse_args(
                    [
                        *base,
                        "--candidate-modes",
                        str(2 * requested_modes),
                    ]
                )
                self.assertEqual(args.candidate_modes, 2 * requested_modes)
            for candidate_modes in (
                2 * requested_modes - 1,
                2 * requested_modes + 1,
            ):
                with self.subTest(
                    requested_modes=requested_modes,
                    candidate_modes=candidate_modes,
                ):
                    with self.assertRaises(SystemExit):
                        _parse_args(
                            [
                                *base,
                                "--candidate-modes",
                                str(candidate_modes),
                            ]
                        )


if __name__ == "__main__":
    unittest.main()
