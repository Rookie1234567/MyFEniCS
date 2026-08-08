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
    _formal_shard_pass,
    _h5_stage_memory_summary,
    _parse_args,
    _task034_terminal_worker_drain,
    _task037b_h5_numerical_pass,
    _task037b_v1_r1_numerical_pass,
    _task037b_v1_r2_numerical_pass,
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


def _v1_raw_record() -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_negative_lowest_propagating_or_lossy",
    )
    probes = [
        {
            "name": name,
            "metadata": {"kind": "contract"},
            "source_digest": "a" * 64,
            "component_digest": "b" * 64,
            "action_relative_error": 1.0e-14,
            "component_repeat_relative_error": 1.0e-15,
            "finite": True,
            "pass": True,
        }
        for name in names
    ]
    side = {
        "h_condition_number": 2.0,
        "matrices": {},
        "operator_inventory": {},
        "probes": probes,
        "component_destroyed": True,
        "action_usable_after_component_destroy": True,
        "pass": True,
    }
    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r1-dtn-component-action.v1",
        "benchmark_id": "task037b_v1_dtn_component_action",
        "status": "task037b_v1_r1_pass_awaiting_r2",
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
        },
        "v1_telemetry": {
            "task037b_v1_gate": True,
            "formal_probe_count_per_side": 6,
            "sides": {"bottom": copy.deepcopy(side), "top": copy.deepcopy(side)},
        },
        "gates": {"r1_pass": True},
        "qualification": {
            "task037b_v1_gate": True,
            "r1_pass": True,
            "integration_pass": True,
        },
    }


def _v1_r2_raw_record() -> dict:
    names = (
        "physical",
        "random_seed_3701",
        "random_seed_3702",
        "random_seed_3703",
        "random_seed_3704",
        "modal_positive_lowest_propagating_or_lossy",
        "modal_positive_first_kind_evanescent",
        "modal_positive_highest_retained_index",
        "modal_negative_lowest_propagating_or_lossy",
        "modal_negative_first_kind_evanescent",
        "modal_negative_highest_retained_index",
    )

    def result() -> dict:
        return {
            "reason": 2,
            "iterations": 1,
            "reported_residual": 1.0e-12,
            "f_only_true_residual": 2.0e-12,
            "stationary_correction_residuals": {
                "1": 1.0e-1,
                "2": 1.0e-2,
                "4": 1.0e-3,
                "8": 1.0e-4,
            },
            "setup_seconds": 1.0,
            "solve_seconds": 2.0,
            "apply_seconds": 3.0,
            "operator_identity": "fine_action_F_only",
            "external_dtn_correction": "excluded",
            "explicit_true_residual_recomputed": True,
        }

    def side() -> dict:
        probes = []
        for name in names:
            probes.append(
                {
                    "name": name,
                    "first": result(),
                    "second": result(),
                    "repeat_reason_equal": True,
                    "repeat_iterations_equal": True,
                    "repeat_solution_relative_error": 1.0e-14,
                    "finite": True,
                    "pass": True,
                }
            )
        return {
            "operator_identity": "fine_action_F_only",
            "external_dtn_correction": "excluded",
            "probe_count": 11,
            "probes": probes,
            "pass": True,
        }

    def preconditioner_contract() -> dict:
        return {
            "configuration": {
                "coordinate_axis": 0,
                "num_slabs": 6,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "ilu_levels": 0,
                "factor_only": True,
                "one_apply_per_pc_apply": True,
                "two_step_action_operator": None,
                "outer_solver": "right_fgmres",
                "restart": 30,
                "max_it": 300,
                "rtol": 1.0e-10,
                "atol": 0.0,
                "true_residual_limit": 1.0e-8,
            },
            "smoother": {
                "subdomain_local_diagonal_shift": True,
                "factor_fingerprints": [
                    {"subdomain": index, "sha256": "a" * 64} for index in range(6)
                ],
            },
            "no_direct_fallback": True,
            "factor_count_before_destroy": 6,
            "factor_count_after_destroy": 0,
            "factors_released": True,
        }

    return {
        "schema_version": 1,
        "record_schema": "task037b.v1-r2-f-only-local-inverse.v1",
        "benchmark_id": "task037b_v1_r2_f_only_local_inverse",
        "status": "task037b_v1_r2_complete_awaiting_r3",
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "v1_r2_telemetry": {
            "task037b_v1_gate": True,
            "external_dtn_correction_excluded": True,
            "formal_probe_count_per_side": 11,
            "sides": {"bottom": side(), "top": side()},
            "preconditioner": {
                "bottom": preconditioner_contract(),
                "top": preconditioner_contract(),
            },
        },
        "gates": {
            "r2_record_complete": True,
            "r2_all_probe_records_complete": True,
            "r2_all_probes_finite": True,
            "r2_no_direct_fallback": True,
            "r2_factors_released": True,
            "r2_pass": True,
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r2_pass": True,
            "worker_numerical_pass": True,
            "integration_pass": True,
            "disposition": "pass_awaiting_r3",
        },
    }


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
            "hybrid_system": {"primary_solver_path": "modal-schur-memory-minimal"},
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

    def test_high_order_core_accepts_only_audited_non_numerical_descendant(
        self,
    ) -> None:
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
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
                "records/p4_h5_e0_prediction.json\n"
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
                "expected.json\n"
                "benchmarks/run_task034_wsl_qualification.py\n"
                "benchmarks/task034_p3_h3_reranking.py\n"
                "src/coupling/modal_trace_projection.py\n"
                "src/modes/mode_classification.py\n"
                "benchmarks/task034_numerical_blob_checker.py\n"
                "benchmarks/task034_mpi_identity.py\n"
                "src/common/distributed_matrix_diagnostics.py\n"
                "src/solvers/hybrid_fem_modal_schur_direct.py\n"
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
            [
                "src/coupling/modal_trace_projection.py",
                "src/modes/mode_classification.py",
                "benchmarks/task034_mpi_identity.py",
                "src/common/distributed_matrix_diagnostics.py",
                "src/solvers/hybrid_fem_modal_schur_direct.py",
            ],
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

    def test_source_preflight_rejects_nonignored_untracked_before_and_after(
        self,
    ) -> None:
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
        self.assertEqual(after["nonignored_untracked_after"], ["uncommitted_solver.py"])

    def test_task032_anchor_default_reuse_and_explicit_same_sha_requalification(
        self,
    ) -> None:
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
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        rendered = " ".join(command)
        self.assertIn("benchmarks.run_task033_qep_matrix", rendered)
        self.assertIn("--no-swap-verified", command)
        self.assertIn("--watchdog-enabled-verified", command)
        self.assertIn("--one-large-case-verified", command)
        self.assertIn("--left-candidate-modes", command)
        self.assertEqual(command[command.index("--left-candidate-modes") + 1], "16")
        self.assertIn("b" * 64, command)
        self.assertIn("--container-limit-gib", command)
        self.assertIn("9.25", command)

    def test_hybrid_command_propagates_explicit_axial_model_only(self) -> None:
        base = [
            "--target",
            "hybrid",
            "--case-label",
            "task035c_p2_h5",
            "--degree",
            "2",
            "--h-nm",
            "5",
            "--mpi-size",
            "1",
            "--requested-modes",
            "160",
            "--candidate-modes",
            "320",
            "--verified-clean-sha",
            "a" * 40,
        ]
        ordinary = _parse_args(base)
        corrected = _parse_args(
            [
                *base,
                "--internal-propagation-model",
                "full3d_uniform_cg",
                "--internal-traction-model",
                "scalar_cg_discrete_derivative",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ordinary_command = _worker_command(
                ordinary, root / "ordinary.json", root / "ordinary.jsonl"
            )
            corrected_command = _worker_command(
                corrected, root / "corrected.json", root / "corrected.jsonl"
            )
        self.assertNotIn("--internal-propagation-model", ordinary_command)
        self.assertEqual(
            corrected_command[
                corrected_command.index("--internal-propagation-model") + 1
            ],
            "full3d_uniform_cg",
        )
        self.assertEqual(
            corrected_command[corrected_command.index("--internal-traction-model") + 1],
            "scalar_cg_discrete_derivative",
        )

    def test_h4_gate_forwards_only_bounded_modal_diagnostic(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "task037b_h4",
                "--degree",
                "6",
                "--h-nm",
                "10",
                "--modal-degree",
                "6",
                "--modal-h-nm",
                "10",
                "--mpi-size",
                "8",
                "--requested-modes",
                "120",
                "--candidate-modes",
                "240",
                "--solver-path",
                "block-ldu-exact",
                "--stage4-full3d-assembly-backend",
                "assembly_time_static_condensed",
                "--bottom-interface-nm",
                "10",
                "--top-interface-nm",
                "110",
                "--incident-grazing-deg",
                "10",
                "--polarization-kind",
                "s",
                "--internal-propagation-model",
                "full3d_uniform_cg",
                "--internal-traction-model",
                "scalar_cg_discrete_derivative",
                "--full3d-reference",
                "reference.json",
                "--full3d-reference-sha256",
                "b" * 64,
                "--task037b-h4-gate",
                "--task035c-p6-preflight-authority",
                "authority.json",
                "--task035c-p6-preflight-sha256",
                "a" * 64,
                "--verified-clean-sha",
                SOURCE_SHA,
                "--host-environment-id",
                "WSL2-Ubuntu-24.04",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        self.assertIn("--task037b-h4-gate", command)
        self.assertNotIn("--task037b-h3-gate", command)
        self.assertNotIn("--task037b-h1-gate", command)

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
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
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

    def test_hybrid_command_can_refine_only_the_modal_cross_section(self) -> None:
        args = _parse_args(
            [
                "--target",
                "hybrid",
                "--case-label",
                "task035c_p2_h5_modal_h3",
                "--degree",
                "2",
                "--h-nm",
                "5",
                "--modal-degree",
                "2",
                "--modal-h-nm",
                "3",
                "--mpi-size",
                "1",
                "--requested-modes",
                "120",
                "--candidate-modes",
                "240",
                "--full3d-reference",
                "records/p2_h5_reference.json",
                "--verified-clean-sha",
                "d" * 40,
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
        rendered = " ".join(command)
        self.assertIn("--degree 2", rendered)
        self.assertIn("--h-nm 5.0", rendered)
        self.assertIn("--modal-degree 2", rendered)
        self.assertIn("--modal-h-nm 3.0", rendered)

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

    def test_hybrid_nondefault_physics_and_minimal_comparison_are_forwarded(
        self,
    ) -> None:
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
            command = _worker_command(args, root / "record.json", root / "stages.jsonl")
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
        fast = hybrid_launch_gate(matrix, comparison_solver_path="fast", **common)
        self.assertFalse(fast["pass"])
        self.assertIn(
            "task033_augmented_comparison_uses_memory_minimal",
            fast["failures"],
        )
        minimal = hybrid_launch_gate(matrix, comparison_solver_path="minimal", **common)
        self.assertTrue(minimal["pass"], minimal["failures"])
        self.assertEqual(minimal["physical_case"]["comparison_solver_path"], "minimal")
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
        passed = hybrid_launch_gate(matrix, m160_funnel_evidence=evidence, **common)
        self.assertTrue(passed["pass"], passed["failures"])
        self.assertTrue(passed["conditional_m240_evidence"]["pass"])
        self.assertEqual(
            passed["independent_prediction"]["conditional_mode_workspace_contingency"],
            2.25,
        )

        missing = hybrid_launch_gate(matrix, m160_funnel_evidence=None, **common)
        self.assertFalse(missing["pass"])
        stale_case = copy.deepcopy(evidence)
        stale_case["case"]["h_nm"] = 3.0
        stale = hybrid_launch_gate(matrix, m160_funnel_evidence=stale_case, **common)
        self.assertFalse(stale["pass"])
        wrong_digest = hybrid_launch_gate(
            matrix,
            m160_funnel_evidence=evidence,
            **{**common, "observed_m160_funnel_sha256": "e" * 64},
        )
        self.assertFalse(wrong_digest["pass"])

    def test_task32_comparison_contract_records_selected_builder(self) -> None:
        source = (ROOT / "benchmarks" / "run_task032_phase6_augmented.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--comparison-solver-path"', source)
        self.assertIn('choices=("fast", "minimal")', source)
        self.assertIn('"comparison_solver_path": comparison_solver_path', source)
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

    def test_static_hybrid_cli_requires_hash_bound_fresh_reference(self) -> None:
        base = [
            "--target",
            "hybrid",
            "--case-label",
            "static_h1a",
            "--degree",
            "2",
            "--h-nm",
            "5",
            "--mpi-size",
            "1",
            "--requested-modes",
            "120",
            "--candidate-modes",
            "240",
            "--full3d-reference",
            "fresh_static.json",
            "--stage4-full3d-assembly-backend",
            "assembly_time_static_condensed",
            "--verified-clean-sha",
            "f" * 40,
        ]
        args = _parse_args([*base, "--full3d-reference-sha256", "a" * 64])
        self.assertEqual(
            args.stage4_full3d_assembly_backend,
            "assembly_time_static_condensed",
        )
        self.assertEqual(args.full3d_reference_sha256, "a" * 64)
        with self.assertRaises(SystemExit):
            _parse_args(base)
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "standard",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "120",
                    "--candidate-modes",
                    "240",
                    "--full3d-reference",
                    "standard.json",
                    "--full3d-reference-sha256",
                    "a" * 64,
                    "--verified-clean-sha",
                    "f" * 40,
                ]
            )

    def test_h5_numerical_pass_does_not_require_physical_truncation(self) -> None:
        record = {
            "qualification": {
                "task037b_h5_gate": True,
                "worker_numerical_pass": True,
                "integration_pass": True,
                "task033_physical_truncation_allowed": False,
            }
        }
        self.assertTrue(_task037b_h5_numerical_pass(record))
        record["qualification"]["integration_pass"] = False
        self.assertFalse(_task037b_h5_numerical_pass(record))
        self.assertFalse(
            _task037b_h5_numerical_pass(
                {
                    "qualification": {
                        "worker_numerical_pass": True,
                        "integration_pass": True,
                    }
                }
            )
        )

    def test_v1_numerical_pass_recomputes_raw_component_contract(self) -> None:
        self.assertTrue(_task037b_v1_r1_numerical_pass(_v1_raw_record()))

        error_record = _v1_raw_record()
        error_record["v1_telemetry"]["sides"]["bottom"]["probes"][0][
            "action_relative_error"
        ] = 2.0e-11
        self.assertFalse(_task037b_v1_r1_numerical_pass(error_record))

        missing_side = _v1_raw_record()
        del missing_side["v1_telemetry"]["sides"]["top"]
        self.assertFalse(_task037b_v1_r1_numerical_pass(missing_side))

        qualification_only = {
            "qualification": {
                "task037b_v1_gate": True,
                "r1_pass": True,
                "integration_pass": True,
            }
        }
        self.assertFalse(_task037b_v1_r1_numerical_pass(qualification_only))

    def test_v1_r2_numerical_pass_recomputes_f_only_contract(self) -> None:
        self.assertTrue(_task037b_v1_r2_numerical_pass(_v1_r2_raw_record()))

        error_record = _v1_r2_raw_record()
        error_record["v1_r2_telemetry"]["sides"]["bottom"]["probes"][0]["first"][
            "f_only_true_residual"
        ] = 2.0e-8
        error_record["v1_r2_telemetry"]["sides"]["bottom"]["probes"][0]["pass"] = False
        error_record["v1_r2_telemetry"]["sides"]["bottom"]["pass"] = False
        error_record["gates"]["r2_pass"] = False
        error_record["qualification"]["r2_pass"] = False
        error_record["qualification"]["worker_numerical_pass"] = False
        error_record["qualification"]["disposition"] = (
            "F_ONLY_LOCAL_INVERSE_FAMILY_DIAGNOSTIC_NEGATIVE"
        )
        self.assertTrue(
            _task037b_v1_r2_numerical_pass(error_record, require_numerical_pass=False)
        )
        self.assertFalse(_task037b_v1_r2_numerical_pass(error_record))

        missing_side = _v1_r2_raw_record()
        del missing_side["v1_r2_telemetry"]["sides"]["top"]
        self.assertFalse(_task037b_v1_r2_numerical_pass(missing_side))

        malformed_name = _v1_r2_raw_record()
        malformed_name["v1_r2_telemetry"]["sides"]["bottom"]["probes"][0]["name"] = None
        self.assertFalse(_task037b_v1_r2_numerical_pass(malformed_name))

        wrong_configuration = _v1_r2_raw_record()
        wrong_configuration["v1_r2_telemetry"]["preconditioner"]["bottom"][
            "configuration"
        ]["overlap_fraction"] = 0.25
        self.assertFalse(_task037b_v1_r2_numerical_pass(wrong_configuration))

        qualification_only = {
            "qualification": {
                "task037b_v1_gate": True,
                "r2_pass": True,
                "integration_pass": True,
            }
        }
        self.assertFalse(_task037b_v1_r2_numerical_pass(qualification_only))

    def test_h5_external_no_swap_is_a_formal_requirement(self) -> None:
        kwargs = {
            "return_code": 0,
            "numerical_pass": True,
            "resource_gate_pass": True,
            "source_gate_pass": True,
            "launch_gate_pass": True,
            "terminated_for_memory": False,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
        }
        self.assertTrue(_formal_shard_pass(**kwargs, no_swap_pass=True))
        self.assertFalse(_formal_shard_pass(**kwargs, no_swap_pass=False))

    def test_h5_terminal_stage_requires_complete_record_and_no_workers(self) -> None:
        kwargs = {
            "task034_workstation_gate": True,
            "process_running": True,
            "authority_readable": False,
            "stage": "h5b_release_record",
            "terminal_record_complete": True,
            "live_worker_count": 0,
            "terminal_stage": "h5b_release_record",
        }
        self.assertTrue(_task034_terminal_worker_drain(**kwargs))
        self.assertFalse(
            _task034_terminal_worker_drain(**{**kwargs, "stage": "record_and_release"})
        )
        self.assertFalse(
            _task034_terminal_worker_drain(
                **{**kwargs, "terminal_record_complete": False}
            )
        )
        self.assertFalse(
            _task034_terminal_worker_drain(**{**kwargs, "live_worker_count": 1})
        )

    def test_h5_stage_memory_summary_keeps_peaks_separate(self) -> None:
        rows = [
            {
                "stage": "h5_action_coupling_build",
                "worker_rank_rss_sum_mb": 10.0,
                "worker_rank_pss_sum_mb": 4.0,
                "worker_rank_uss_sum_mb": 3.0,
                "mpi_process_tree_rss_mb": 20.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5a_bottom_factor",
                "worker_rank_rss_sum_mb": 12.0,
                "worker_rank_pss_sum_mb": 5.0,
                "worker_rank_uss_sum_mb": 4.0,
                "mpi_process_tree_rss_mb": 24.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5a_top_solve",
                "worker_rank_rss_sum_mb": 15.0,
                "worker_rank_pss_sum_mb": 6.0,
                "worker_rank_uss_sum_mb": 5.0,
                "mpi_process_tree_rss_mb": 30.0,
                "worker_rank_smaps_readable_count": 1,
            },
            {
                "stage": "h5_post_direct_heap_trim",
                "worker_rank_rss_sum_mb": 8.0,
                "worker_rank_pss_sum_mb": 3.0,
                "worker_rank_uss_sum_mb": 2.0,
                "mpi_process_tree_rss_mb": 16.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5b_bottom_solves",
                "worker_rank_rss_sum_mb": 25.0,
                "worker_rank_pss_sum_mb": 9.0,
                "worker_rank_uss_sum_mb": 7.0,
                "mpi_process_tree_rss_mb": 40.0,
                "worker_rank_smaps_readable_count": 2,
            },
            {
                "stage": "h5b_top_solves",
                "worker_rank_rss_sum_mb": 30.0,
                "worker_rank_pss_sum_mb": 10.0,
                "worker_rank_uss_sum_mb": 8.0,
                "mpi_process_tree_rss_mb": 50.0,
                "worker_rank_smaps_readable_count": 2,
            },
        ]
        summary = _h5_stage_memory_summary(rows, expected_mpi_size=2)
        common = summary["common_action_coupling"]
        h5a = summary["h5a_direct_reference"]
        trim = summary["h5_post_direct_trim"]
        h5b = summary["h5b_candidate"]
        self.assertEqual(common["peak_worker_rank_rss_sum_mb"], 10.0)
        self.assertEqual(common["peak_mpi_process_tree_rss_mb"], 20.0)
        self.assertEqual(h5a["peak_worker_rank_rss_sum_mb"], 15.0)
        self.assertEqual(h5a["peak_mpi_process_tree_rss_mb"], 30.0)
        self.assertEqual(h5a["peak_worker_rank_pss_sum_mb"], 5.0)
        self.assertEqual(h5a["peak_worker_rank_uss_sum_mb"], 4.0)
        self.assertEqual(h5a["complete_smaps_sample_count"], 1)
        self.assertEqual(trim["peak_worker_rank_rss_sum_mb"], 8.0)
        self.assertEqual(h5b["peak_worker_rank_rss_sum_mb"], 30.0)
        self.assertEqual(h5b["peak_mpi_process_tree_rss_mb"], 50.0)
        self.assertEqual(h5b["peak_worker_rank_pss_sum_mb"], 10.0)
        self.assertEqual(h5b["peak_worker_rank_uss_sum_mb"], 8.0)
        incomplete = _h5_stage_memory_summary(
            [
                {
                    "stage": "h5_post_direct_heap_trim",
                    "worker_rank_rss_sum_mb": 18.0,
                    "worker_rank_pss_sum_mb": 11.0,
                    "worker_rank_uss_sum_mb": 9.0,
                    "mpi_process_tree_rss_mb": 27.0,
                    "worker_rank_smaps_readable_count": 1,
                }
            ],
            expected_mpi_size=2,
        )["h5_post_direct_trim"]
        self.assertEqual(incomplete["complete_smaps_sample_count"], 0)
        self.assertIsNone(incomplete["peak_worker_rank_pss_sum_mb"])
        self.assertIsNone(incomplete["peak_worker_rank_uss_sum_mb"])
        self.assertEqual(incomplete["peak_worker_rank_rss_sum_mb"], 18.0)
        self.assertEqual(incomplete["peak_mpi_process_tree_rss_mb"], 27.0)


if __name__ == "__main__":
    unittest.main()
