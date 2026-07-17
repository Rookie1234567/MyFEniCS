from __future__ import annotations

import copy
import cmath
import json
import unittest
from pathlib import Path

from benchmarks.run_task033_memory_watchdog import (
    _environment_preflight,
    _formal_shard_pass,
    _hybrid_measurements,
)
from benchmarks.run_task033_qep_matrix import (
    _matrix_relative_difference,
    _resource_environment_snapshot,
    _stage_memory,
)
from benchmarks.task033_case090_pde_core import attach_evidence_sha256
from benchmarks.task033_qep_qualification import (
    TREND_DEGREES,
    TREND_H_NM,
    aggregate_qep_shards,
    qep_full_aggregate_gate,
    qep_p3_only_partial_aggregate_gate,
    qep_shard_gate,
    recompute_cross_h_tracking,
    resource_authority_gate,
    source_identity_gate,
)
from benchmarks.task033_watchdog_launch import hybrid_launch_gate


ROOT = Path(__file__).resolve().parents[2]


def _source() -> dict:
    sha = "a" * 40
    return {
        "commit_sha": sha,
        "head_before_sha": sha,
        "head_after_sha": sha,
        "verified_clean_sha": sha,
        "tracked_status_before": "",
        "tracked_status_after": "",
        "source_stable_during_run": True,
        "source_clean_verified": True,
    }


def _resource() -> dict:
    return {
        "simultaneous_live_worker_rss_sum_bytes": 2 * 1024**3,
        "container_cgroup_current_bytes": 3 * 1024**3,
        "memory_authority_bytes": 3 * 1024**3,
        "container_memory_limit_bytes": 14 * 1024**3,
        "host_available_memory_bytes": 20 * 1024**3,
        "container_swap_current_bytes": 0,
        "pswpin_delta_pages": 0,
        "pswpout_delta_pages": 0,
    }


def _qep_shard(material: str, degree: int, h_nm: float) -> dict:
    analytic_error = (
        None
        if material == "stage4_xy"
        else 1.0e-3 * (h_nm / 5.0) ** 2 / degree**2
    )
    tracking = None
    right_requested_modes = 8
    left_candidate_requested_modes = 16
    left_pair_relative_errors = [1.0e-10] * right_requested_modes
    if material == "stage4_xy":
        # Compact common-probe moments are the measured shard input.  The
        # aggregate must recompute the assignment; no claimed overlap/pass is
        # trusted from this fixture (or from a real worker).
        permutation = (1, 0) if h_nm == 3.0 else (0, 1)
        basis = (
            ([1.0, 0.0], [0.0, 0.0], [0.0, 0.0]),
            ([0.0, 0.0], [1.0, 0.0], [0.0, 0.0]),
        )
        modes = []
        for mode_index, physical_index in enumerate(permutation):
            fingerprint = basis[physical_index]
            modes.append(
                {
                    "mode_index": mode_index,
                    "beta_per_nm": [
                        1.0 + 0.1 * physical_index + 1.0e-3 * h_nm,
                        0.0,
                    ],
                    "direction": "forward",
                    "kind": "propagating",
                    "passive_branch_valid": True,
                    "right_fourier_fingerprint": fingerprint,
                    "left_fourier_fingerprint": fingerprint,
                    "right_moment_norm_before_normalization": 1.0,
                    "left_moment_norm_before_normalization": 1.0,
                    "qprime_left_right_overlap_after": [1.0, 0.0],
                }
            )
        tracking = {
            "evidence_kind": "measured_per_shard_input_for_cross_h_tracking",
            "status": "compact_input_ready_for_aggregate",
            "aggregate_recomputation_required": True,
            "compact_evidence": {
                "schema_version": 1,
                "evidence_kind": (
                    "measured_common_fourier_left_right_mode_fingerprints"
                ),
                "status": "compact_input_ready_for_cross_h_aggregate",
                "assignment_performed_in_shard": False,
                "cross_h_vector_dot_performed": False,
                "probe_orders": [[0, 0]],
                "components_per_order": ["Et_x", "Et_y", "Ez"],
                "fingerprint_length": 3,
                "quadrature_degree": 8,
                "mode_count": 2,
                "modes": modes,
                "full_eigenvector_gathered": False,
            },
            "failure": None,
        }
    return {
        "schema_version": "task033.case091.qep-measurement.v2",
        "record_type": "task033_qep_measurement_shard",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "measured_shard_pass",
        "identity": {
            "is_pde_run": True,
            "is_solver_pass": True,
            "is_memory_measurement": True,
            "result_identity": "measured_shard",
            "is_physical_qualification_record": False,
            "physical_qualified": False,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "candidate": {
            "material_kind": material,
            "degree": degree,
            "h_nm": h_nm,
            "mpi_size": 1,
        },
        "memory_prediction": {},
        "runtime_preflight": {
            "runtime_contract_verified": True,
            "launch_eligible": True,
            "failures": [],
        },
        "provenance": _source(),
        "numerical_results": {
            "converged_eigenpairs": right_requested_modes,
            "analytic_beta_relative_error": analytic_error,
            "left_right_classification": {
                "right_polynomial_relative_residual_max": 1.0e-12,
                "left_polynomial_relative_residual_max": 1.0e-10,
                "biorthogonality_identity_error": 1.0e-8,
                "biorthogonality_infinity_norm_error": 8.0e-8,
                "left_candidate_pool_policy": (
                    "max_requested_plus_8_or_2x"
                ),
                "right_requested_modes": right_requested_modes,
                "left_candidate_requested_modes": (
                    left_candidate_requested_modes
                ),
                "left_candidate_converged_modes": (
                    left_candidate_requested_modes
                ),
                "left_pair_relative_errors": left_pair_relative_errors,
                "left_pair_relative_error_max": max(
                    left_pair_relative_errors
                ),
                "near_degenerate_groups": [
                    {
                        "indices": [index],
                        "beta_center_per_nm": [1.0, 0.0],
                        "max_relative_beta_spread": 0.0,
                        "overlap_condition": 1.0,
                        "normalization_method": "diagonal_qprime",
                        "post_normalization_identity_error": 1.0e-12,
                    }
                    for index in range(right_requested_modes)
                ],
            },
            "quadrature": {
                "raised_comparison": {
                    "max_matrix_relative_difference": 1.0e-13,
                    "pass": True,
                }
            },
            "cross_h_tracking": tracking,
        },
        "resource_measurements": {
            "formal_resource_authority": _resource(),
        },
        "gates": {
            "converged_eigenpair": True,
            "polynomial_relative_residual_le_1e-10": True,
            "left_polynomial_relative_residual_le_1e-8": True,
            "biorthogonality_identity_error_le_1e-6": True,
            "all_required_numerical_gates_pass": True,
            "left_right_beta_pair_relative_error_le_1e-7": True,
            "analytic_beta_error_finite": (
                "not_applicable_patterned_cross_section"
                if material == "stage4_xy"
                else True
            ),
            "no_swap": True,
            "below_controlled_termination": True,
            "formal_resource_authority_pass": True,
            "raised_quadrature_pass": True,
            "patterned_tracking_compact_ready": True,
            "single_shard_only_not_physical_qualification": True,
            "source_identity_stable_clean_pass": True,
        },
    }


def _controlled_p4_negative(shard: dict) -> dict:
    record = copy.deepcopy(shard)
    record["status"] = "measured_shard_failed"
    record["identity"]["is_solver_pass"] = False
    record["gates"]["all_required_numerical_gates_pass"] = False
    record["gates"]["biorthogonality_identity_error_le_1e-6"] = False
    record["numerical_results"]["left_right_classification"][
        "biorthogonality_identity_error"
    ] = 2.0e-6
    record["numerical_results"]["left_right_classification"][
        "biorthogonality_infinity_norm_error"
    ] = 3.0e-6
    return record


def _rotated_near_degenerate_tracking_record(*, beta_scale: float) -> dict:
    mode_count = 5
    modes = []
    for mode_index in range(mode_count):
        fingerprint = [
            [
                float((cmath.exp(2j * cmath.pi * mode_index * axis / mode_count)).real),
                float((cmath.exp(2j * cmath.pi * mode_index * axis / mode_count)).imag),
            ]
            for axis in range(mode_count)
        ]
        modes.append(
            {
                "mode_index": mode_index,
                "beta_per_nm": [beta_scale * (1.0 + 1.0e-8 * mode_index), 0.0],
                "direction": "forward",
                "kind": "propagating",
                "right_fourier_fingerprint": fingerprint,
                "left_fourier_fingerprint": fingerprint,
            }
        )
    return {
        "numerical_results": {
            "left_right_classification": {
                "near_degenerate_groups": [
                    {
                        "indices": list(range(mode_count)),
                        "beta_center_per_nm": [beta_scale, 0.0],
                        "max_relative_beta_spread": 4.0e-8,
                        "overlap_condition": 1.0,
                        "normalization_method": "near_degenerate_block_inverse",
                        "post_normalization_identity_error": 1.0e-12,
                    }
                ]
            },
            "cross_h_tracking": {
                "evidence_kind": "measured_per_shard_input_for_cross_h_tracking",
                "status": "compact_input_ready_for_aggregate",
                "aggregate_recomputation_required": True,
                "compact_evidence": {
                    "schema_version": 1,
                    "evidence_kind": (
                        "measured_common_fourier_left_right_mode_fingerprints"
                    ),
                    "status": "compact_input_ready_for_cross_h_aggregate",
                    "assignment_performed_in_shard": False,
                    "cross_h_vector_dot_performed": False,
                    "probe_orders": [[axis, 0] for axis in range(mode_count)],
                    "components_per_order": ["Et_x"],
                    "fingerprint_length": mode_count,
                    "mode_count": mode_count,
                    "modes": modes,
                    "full_eigenvector_gathered": False,
                },
            },
        }
    }


def _canonical_near_degenerate_tracking_record(*, beta_scale: float) -> dict:
    record = _rotated_near_degenerate_tracking_record(beta_scale=beta_scale)
    modes = record["numerical_results"]["cross_h_tracking"][
        "compact_evidence"
    ]["modes"]
    for mode_index, mode in enumerate(modes):
        fingerprint = [
            [1.0 if axis == mode_index else 0.0, 0.0]
            for axis in range(len(modes))
        ]
        mode["right_fourier_fingerprint"] = fingerprint
        mode["left_fourier_fingerprint"] = fingerprint
    return record


def _hybrid_shard(mode: int, offset: float) -> dict:
    order = {
        "side": "top",
        "m": 0,
        "n": 0,
        "polarization": "s",
        "power_ratio": 0.5 + offset,
        "outgoing_amplitude_at_boundary": [1.0 + offset, 0.2],
    }
    return {
        "schema_version": "task033.memory-watchdog.v2",
        "benchmark_id": "task033_external_memory_watchdog",
        "status": "measured_shard_pass",
        "formal_pass": True,
        "physical_qualified": False,
        "requested_modes": mode,
        "source": _source(),
        "resource_authority": _resource(),
        "measurements": {
            "validation": {
                "port_power": {
                    "R_total": 0.1 + offset,
                    "T_total": 0.5 - offset,
                    "A_balance": 0.4,
                },
                "external_diffraction_orders": [order],
            }
        },
    }


def _core_evidence(source_sha: str = "a" * 40) -> dict:
    return attach_evidence_sha256(
        {
            "schema_version": 1,
            "record_type": "high_order_floquet_core_gate_result",
            "case_id": "090_high_order_3d_floquet_hcurl",
            "identity": {
                "is_pde_run": True,
                "is_solver_pass": True,
                "tracked_source_dirty": False,
                "source_commit_full_sha": source_sha,
            },
            "all_core_gates_passed": True,
            "coverage": [
                {"degree": degree, "mpi_size": mpi_size}
                for degree in (1, 2, 3, 4)
                for mpi_size in (1, 2, 4)
            ],
            "failures": [],
        }
    )
class Task033QepQualificationTests(unittest.TestCase):
    @staticmethod
    def _hybrid_launch(
        degree: int,
        h_nm: float,
        *,
        solver_path: str = "modal-schur-memory-minimal",
        graded_reference_h: float | None = None,
        core_evidence: dict | None = None,
    ) -> dict:
        matrix = json.loads(
            (
                ROOT
                / "benchmarks"
                / "cases"
                / "091_hybrid_hp_adaptivity_feasibility"
                / "records"
                / "resource_matrix.json"
            ).read_text(encoding="utf-8")
        )
        return hybrid_launch_gate(
            matrix,
            degree=degree,
            h_nm=h_nm,
            requested_modes=80,
            candidate_modes=160,
            solver_path=solver_path,
            compare_modal_schur=False,
            bottom_interface_nm=10.0,
            top_interface_nm=110.0,
            graded_reference_h=graded_reference_h,
            container_limit_bytes=14 * 1024**3,
            host_available_memory_bytes=20 * 1024**3,
            warning_gib=11.0,
            terminate_gib=12.5,
            core_evidence=core_evidence,
            expected_core_sha256=(
                None
                if core_evidence is None
                else core_evidence["evidence_sha256"]
            ),
            current_source_sha="a" * 40,
        )

    def test_docker_petsc_matrix_delta_and_live_authority_contract(self) -> None:
        try:
            from mpi4py import MPI
            from petsc4py import PETSc
        except ImportError:  # pragma: no cover - Windows host has no PETSc
            self.skipTest("PETSc/MPI runtime is not installed")
        first = PETSc.Mat().createAIJ([2, 2], comm=MPI.COMM_SELF)
        first.setValue(0, 0, 2.0)
        first.setValue(1, 1, 3.0)
        first.assemble()
        second = first.copy()
        try:
            self.assertLess(_matrix_relative_difference(first, second), 1.0e-15)
            second.setValue(0, 0, 2.1)
            second.assemble()
            self.assertGreater(_matrix_relative_difference(first, second), 0.0)
            stage = _stage_memory(MPI.COMM_SELF, "test58")
            self.assertEqual(
                stage["memory_authority_bytes"],
                max(
                    stage["simultaneous_live_worker_rss_sum_bytes"],
                    stage["container_cgroup_current_bytes"],
                ),
            )
            self.assertGreater(stage["host_available_memory_bytes"], 0)
            if stage["container_memory_limit_bytes"] is None:
                preflight = _environment_preflight(
                    _resource_environment_snapshot()
                )
                self.assertFalse(preflight["pass"])
                self.assertIn(
                    "container_limit_readable", preflight["failures"]
                )
            else:
                self.assertGreater(stage["container_memory_limit_bytes"], 0)
        finally:
            second.destroy()
            first.destroy()

    def test_source_identity_requires_clean_full_sha_before_and_after(self) -> None:
        self.assertTrue(source_identity_gate(_source())["pass"])
        unstable = _source()
        unstable["head_after_sha"] = "b" * 40
        self.assertFalse(source_identity_gate(unstable)["pass"])
        dirty = _source()
        dirty["tracked_status_after"] = " M src/example.py"
        self.assertFalse(source_identity_gate(dirty)["pass"])

    def test_resource_authority_is_exact_max_and_all_swap_evidence_is_zero(self) -> None:
        self.assertTrue(resource_authority_gate(_resource())["pass"])
        wrong = _resource()
        wrong["memory_authority_bytes"] = wrong[
            "simultaneous_live_worker_rss_sum_bytes"
        ]
        self.assertFalse(resource_authority_gate(wrong)["pass"])
        unreadable = _resource()
        unreadable["host_available_memory_bytes"] = None
        self.assertFalse(resource_authority_gate(unreadable)["pass"])
        swapped = _resource()
        swapped["container_swap_current_bytes"] = 4096
        self.assertFalse(resource_authority_gate(swapped)["pass"])

    def test_hybrid_launch_reads_case091_and_recomputes_live_scaled_gates(self) -> None:
        self.assertTrue(self._hybrid_launch(1, 5.0)["pass"])
        memory_veto = self._hybrid_launch(4, 5.0, core_evidence=_core_evidence())
        self.assertFalse(memory_veto["pass"])
        self.assertFalse(
            memory_veto["checks"]["stored_prediction_gate_pass"]
        )

    def test_high_order_launch_requires_real_same_source_core_evidence(self) -> None:
        missing = self._hybrid_launch(3, 5.0)
        self.assertFalse(missing["pass"])
        self.assertFalse(missing["checks"]["high_order_core_evidence"])
        passed = self._hybrid_launch(3, 5.0, core_evidence=_core_evidence())
        self.assertTrue(passed["pass"])
        stale = self._hybrid_launch(
            3, 5.0, core_evidence=_core_evidence("b" * 40)
        )
        self.assertFalse(stale["pass"])

    def test_augmented_anchor_and_graded_variant_need_independent_prediction(self) -> None:
        reused_uniform = self._hybrid_launch(2, 3.0)
        self.assertFalse(reused_uniform["pass"])
        augmented = self._hybrid_launch(2, 3.0, solver_path="augmented")
        self.assertTrue(augmented["pass"])
        self.assertTrue(augmented["independent_prediction"]["required"])
        self.assertEqual(
            augmented["independent_prediction"]["prediction_identity"],
            "task032_augmented_anchor_independent_two_center",
        )
        graded = self._hybrid_launch(2, 5.0, graded_reference_h=5.0)
        self.assertTrue(graded["pass"])
        self.assertEqual(
            graded["independent_prediction"][
                "uncalibrated_geometry_contingency"
            ],
            1.25,
        )

    def test_qep_mpi_timeout_and_unreadable_authority_fail_closed(self) -> None:
        common = {
            "return_code": 0,
            "numerical_pass": True,
            "resource_gate_pass": True,
            "source_gate_pass": True,
            "launch_gate_pass": True,
            "terminated_for_memory": False,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
        }
        self.assertTrue(_formal_shard_pass(**common))
        timed_out = {**common, "terminated_for_timeout": True}
        self.assertFalse(_formal_shard_pass(**timed_out))
        unreadable = {
            **common,
            "terminated_for_authority_unreadable": True,
        }
        self.assertFalse(_formal_shard_pass(**unreadable))

    def test_single_qep_shard_requires_raised_quadrature_but_is_not_physical(self) -> None:
        shard = _qep_shard("air", 3, 3.0)
        self.assertTrue(qep_shard_gate(shard)["pass"])
        self.assertFalse(shard["identity"]["is_physical_qualification_record"])
        failed = copy.deepcopy(shard)
        failed["numerical_results"]["quadrature"]["raised_comparison"][
            "pass"
        ] = False
        self.assertFalse(qep_shard_gate(failed)["pass"])

    def test_qep_shard_rejects_false_identity_zero_convergence_and_failure_payload(self) -> None:
        shard = _qep_shard("air", 3, 3.0)
        mutations = {
            "identity_false": lambda row: row["identity"].__setitem__(
                "is_pde_run", False
            ),
            "zero_converged_eigenpairs": lambda row: row[
                "numerical_results"
            ].__setitem__("converged_eigenpairs", 0),
            "insufficient_converged_eigenpairs": lambda row: row[
                "numerical_results"
            ].__setitem__("converged_eigenpairs", 1),
            "exception_failure_payload": lambda row: row.__setitem__(
                "failure", {"type": "RuntimeError", "message": "pairing failed"}
            ),
        }
        expected_check = {
            "identity_false": "measurement_identity",
            "zero_converged_eigenpairs": "converged_eigenpairs",
            "insufficient_converged_eigenpairs": "converged_eigenpairs",
            "exception_failure_payload": "no_exception_failure_payload",
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                forged = copy.deepcopy(shard)
                mutate(forged)
                gate = qep_shard_gate(forged)
                self.assertFalse(gate["pass"])
                self.assertFalse(gate["checks"][expected_check[name]])

        for field, value in (
            ("schema_version", "evil.v9"),
            ("record_type", "other"),
            ("case_id", "000"),
        ):
            with self.subTest(identity_field=field):
                forged = copy.deepcopy(shard)
                forged[field] = value
                gate = qep_shard_gate(forged)
                self.assertFalse(gate["pass"])
                self.assertFalse(gate["checks"]["record_identity"])

        for field, value in (
            ("is_memory_measurement", False),
            ("result_identity", "forged"),
            ("ordinary_default_changed", True),
            ("proves_0p7nm_feasible", True),
        ):
            with self.subTest(identity_field=field):
                forged = copy.deepcopy(shard)
                forged["identity"][field] = value
                gate = qep_shard_gate(forged)
                self.assertFalse(gate["pass"])
                self.assertFalse(gate["checks"]["measurement_identity"])

    def test_qep_pairing_pool_and_raw_beta_pair_gate_are_recomputed(self) -> None:
        shard = _qep_shard("air", 3, 3.0)
        result = qep_shard_gate(shard)
        self.assertTrue(result["pass"])
        self.assertTrue(
            result["checks"][
                "left_right_beta_pair_relative_error_le_1e-7"
            ]
        )

        undersampled = copy.deepcopy(shard)
        classification = undersampled["numerical_results"][
            "left_right_classification"
        ]
        classification["left_candidate_requested_modes"] = 15
        self.assertFalse(qep_shard_gate(undersampled)["pass"])

        incomplete = copy.deepcopy(shard)
        classification = incomplete["numerical_results"][
            "left_right_classification"
        ]
        classification["left_candidate_converged_modes"] = 7
        self.assertFalse(qep_shard_gate(incomplete)["pass"])

        invalid_infinity_diagnostic = copy.deepcopy(shard)
        classification = invalid_infinity_diagnostic["numerical_results"][
            "left_right_classification"
        ]
        classification["biorthogonality_infinity_norm_error"] = 5.0e-9
        self.assertFalse(qep_shard_gate(invalid_infinity_diagnostic)["pass"])

        inconsistent = copy.deepcopy(shard)
        classification = inconsistent["numerical_results"][
            "left_right_classification"
        ]
        classification["left_pair_relative_error_max"] = 9.0e-8
        self.assertFalse(qep_shard_gate(inconsistent)["pass"])

        above_gate = copy.deepcopy(shard)
        classification = above_gate["numerical_results"][
            "left_right_classification"
        ]
        classification["left_pair_relative_errors"][-1] = 2.0e-7
        classification["left_pair_relative_error_max"] = 2.0e-7
        # A forged stored True cannot override the recomputed raw-list Gate.
        self.assertTrue(
            above_gate["gates"][
                "left_right_beta_pair_relative_error_le_1e-7"
            ]
        )
        failed = qep_shard_gate(above_gate)
        self.assertFalse(failed["pass"])
        self.assertFalse(
            failed["checks"][
                "left_right_beta_pair_relative_error_le_1e-7"
            ]
        )

    def test_qep_shard_rejects_negative_metrics_and_coerced_axes(self) -> None:
        metric_mutations = {
            "analytic": (
                lambda row: row["numerical_results"].__setitem__(
                    "analytic_beta_relative_error", -1.0
                ),
                "analytic_beta_identity",
            ),
            "right_residual": (
                lambda row: row["numerical_results"][
                    "left_right_classification"
                ].__setitem__("right_polynomial_relative_residual_max", -1.0),
                "right_residual",
            ),
            "left_residual": (
                lambda row: row["numerical_results"][
                    "left_right_classification"
                ].__setitem__("left_polynomial_relative_residual_max", -1.0),
                "left_residual",
            ),
            "biorthogonality": (
                lambda row: row["numerical_results"][
                    "left_right_classification"
                ].__setitem__("biorthogonality_identity_error", -1.0),
                "biorthogonality",
            ),
            "infinity_diagnostic": (
                lambda row: row["numerical_results"][
                    "left_right_classification"
                ].__setitem__("biorthogonality_infinity_norm_error", -1.0),
                "biorthogonality_infinity_norm_diagnostic",
            ),
            "oversized_infinity_diagnostic": (
                lambda row: row["numerical_results"][
                    "left_right_classification"
                ].__setitem__("biorthogonality_infinity_norm_error", 1.0),
                "biorthogonality_infinity_norm_diagnostic",
            ),
            "quadrature_delta": (
                lambda row: row["numerical_results"]["quadrature"][
                    "raised_comparison"
                ].__setitem__("max_matrix_relative_difference", -1.0),
                "raised_quadrature",
            ),
        }
        for name, (mutate, expected_check) in metric_mutations.items():
            with self.subTest(metric=name):
                forged = _qep_shard("air", 3, 3.0)
                mutate(forged)
                gate = qep_shard_gate(forged)
                self.assertFalse(gate["pass"])
                self.assertFalse(gate["checks"][expected_check])

        for name, field, value in (
            ("degree_string", "degree", "3"),
            ("h_string", "h_nm", "3.0"),
            ("mpi_bool", "mpi_size", True),
        ):
            with self.subTest(axis=name):
                forged = _qep_shard("air", 3, 3.0)
                forged["candidate"][field] = value
                gate = qep_shard_gate(forged)
                self.assertFalse(gate["pass"])
                self.assertFalse(gate["checks"]["candidate_axes"])

        invalid_groups = _qep_shard("air", 3, 3.0)
        groups = invalid_groups["numerical_results"][
            "left_right_classification"
        ]["near_degenerate_groups"]
        groups[0]["indices"] = [0, 1]
        groups.pop(1)
        self.assertFalse(qep_shard_gate(invalid_groups)["pass"])
        self.assertFalse(
            qep_shard_gate(invalid_groups)["checks"][
                "near_degenerate_group_contract"
            ]
        )

    def test_qep_aggregate_requires_air_lossy_trends_p2_comparison_and_tracking(self) -> None:
        records = [
            _qep_shard(material, degree, h_nm)
            for material in ("air", "lossy_homogeneous", "stage4_xy")
            for degree in TREND_DEGREES
            for h_nm in TREND_H_NM
        ]
        aggregate = aggregate_qep_shards(records)
        self.assertEqual(
            aggregate["status"], "qep_component_aggregate_qualified"
        )
        self.assertTrue(aggregate["identity"]["is_qep_component_qualified"])
        self.assertTrue(qep_full_aggregate_gate(aggregate)["pass"])
        self.assertFalse(aggregate["identity"]["is_physical_qualification_record"])
        first_tracking = aggregate["patterned_cross_h_tracking"]["p1"][0]
        self.assertEqual(
            first_tracking["evidence_kind"],
            "aggregate_recomputed_cross_h_mode_tracking",
        )
        self.assertEqual(
            {
                (row["previous_mode_index"], row["current_mode_index"])
                for row in first_tracking["matches"]
            },
            {(0, 1), (1, 0)},
        )

        missing_tracking = copy.deepcopy(records)
        missing_tracking[-1]["numerical_results"]["cross_h_tracking"] = None
        blocked = aggregate_qep_shards(missing_tracking)
        self.assertEqual(
            blocked["status"], "qep_component_aggregate_not_qualified"
        )

        forged_overlap = copy.deepcopy(records)
        forged = forged_overlap[-1]["numerical_results"]["cross_h_tracking"]
        forged["minimum_overlap"] = 1.0
        forged["pass"] = True
        forged["compact_evidence"] = None
        blocked_forgery = aggregate_qep_shards(forged_overlap)
        self.assertEqual(
            blocked_forgery["status"],
            "qep_component_aggregate_not_qualified",
        )

        forged_counts = copy.deepcopy(aggregate)
        forged_counts["received_unique_shard_count"] = 0
        forged_counts["p1_p2_p3_passed_shard_count"] = 0
        forged_counts["p4_completed_shard_count"] = 0
        self.assertFalse(qep_full_aggregate_gate(forged_counts)["pass"])

        truncated_shard_gate = copy.deepcopy(aggregate)
        first_shard_gate = next(
            iter(truncated_shard_gate["shard_gates"].values())
        )
        first_shard_gate["positive_gate"]["checks"] = {
            "source_identity": True
        }
        self.assertFalse(
            qep_full_aggregate_gate(truncated_shard_gate)["pass"]
        )

        coerced_axis_records = copy.deepcopy(records)
        coerced_axis_records[0]["candidate"]["degree"] = "1"
        coerced_axis_aggregate = aggregate_qep_shards(coerced_axis_records)
        self.assertEqual(
            coerced_axis_aggregate["qualification_classification"],
            "not_qualified",
        )
        self.assertFalse(qep_full_aggregate_gate(coerced_axis_aggregate)["pass"])

    def test_near_degenerate_block_tracking_resolves_basis_rotation_only(self) -> None:
        previous = _canonical_near_degenerate_tracking_record(beta_scale=1.0)
        rotated = _rotated_near_degenerate_tracking_record(beta_scale=1.001)
        resolved = recompute_cross_h_tracking(
            previous,
            rotated,
            previous_h_nm=5.0,
            current_h_nm=3.0,
        )
        self.assertLess(resolved["minimum_overlap"], 0.5)
        self.assertTrue(resolved["near_degenerate_basis_rotation_resolved"])
        self.assertEqual(
            resolved["tracking_basis_resolution"],
            "near_degenerate_block_subspace",
        )
        self.assertTrue(resolved["block_subspace_tracking"]["pass"])
        self.assertTrue(resolved["pass"])

        drifted = _rotated_near_degenerate_tracking_record(beta_scale=1.4)
        rejected = recompute_cross_h_tracking(
            previous,
            drifted,
            previous_h_nm=5.0,
            current_h_nm=3.0,
        )
        self.assertFalse(rejected["near_degenerate_basis_rotation_resolved"])
        self.assertFalse(rejected["block_subspace_tracking"]["pass"])
        self.assertIn(
            "maximum_relative_beta_drift_above_gate", rejected["failures"]
        )
        self.assertFalse(rejected["pass"])

    def test_qep_aggregate_accepts_only_complete_controlled_p4_partial(self) -> None:
        records = [
            _qep_shard(material, degree, h_nm)
            for material in ("air", "lossy_homogeneous", "stage4_xy")
            for degree in TREND_DEGREES
            for h_nm in TREND_H_NM
        ]
        p4_index = next(
            index
            for index, record in enumerate(records)
            if record["candidate"] == {
                "material_kind": "lossy_homogeneous",
                "degree": 4,
                "h_nm": 3.0,
                "mpi_size": 1,
            }
        )
        records[p4_index] = _controlled_p4_negative(records[p4_index])
        partial = aggregate_qep_shards(
            records, allow_p4_controlled_negative=True
        )
        self.assertEqual(
            partial["status"], "qep_component_aggregate_not_qualified"
        )
        self.assertEqual(
            partial["qualification_classification"], "partial_p3_only"
        )
        self.assertFalse(partial["identity"]["is_qep_component_qualified"])
        self.assertTrue(partial["identity"]["is_qep_p3_only_partial"])
        self.assertEqual(partial["p1_p2_p3_passed_shard_count"], 27)
        self.assertEqual(partial["p4_completed_shard_count"], 9)
        self.assertEqual(partial["negative_observation_count"], 1)
        self.assertTrue(qep_p3_only_partial_aggregate_gate(partial)["pass"])

        missing_core = copy.deepcopy(partial)
        for name in (
            "analytic_beta_trends",
            "relative_to_p2",
            "patterned_cross_h_tracking",
        ):
            del missing_core[name]
        self.assertFalse(
            qep_p3_only_partial_aggregate_gate(missing_core)["pass"]
        )

        forged = copy.deepcopy(partial)
        lower = next(
            row
            for key, row in forged["shard_gates"].items()
            if "|1|" in key
        )
        lower["positive_gate"]["failures"] = ["forged"]
        self.assertFalse(qep_p3_only_partial_aggregate_gate(forged)["pass"])

        truncated_controlled_gate = copy.deepcopy(partial)
        controlled = next(
            row
            for row in truncated_controlled_gate["shard_gates"].values()
            if row["disposition"] == "controlled_numeric_negative"
        )
        del controlled["controlled_negative_gate"]["checks"][
            "source_identity_stable_clean_pass"
        ]
        self.assertFalse(
            qep_p3_only_partial_aggregate_gate(truncated_controlled_gate)[
                "pass"
            ]
        )

        lower_negative = copy.deepcopy(records)
        p3_index = next(
            index
            for index, record in enumerate(lower_negative)
            if record["candidate"]["degree"] == 3
        )
        lower_negative[p3_index] = _controlled_p4_negative(
            lower_negative[p3_index]
        )
        blocked_lower = aggregate_qep_shards(
            lower_negative, allow_p4_controlled_negative=True
        )
        self.assertEqual(
            blocked_lower["qualification_classification"], "not_qualified"
        )

        infrastructure = copy.deepcopy(records)
        infrastructure[p4_index]["gates"]["no_swap"] = False
        blocked_infrastructure = aggregate_qep_shards(
            infrastructure, allow_p4_controlled_negative=True
        )
        self.assertEqual(
            blocked_infrastructure["qualification_classification"],
            "not_qualified",
        )

        unexpected = [*records, _qep_shard("air", 4, 5.0)]
        unexpected[-1]["candidate"]["degree"] = 5
        blocked_unexpected = aggregate_qep_shards(
            unexpected, allow_p4_controlled_negative=True
        )
        self.assertEqual(blocked_unexpected["unexpected_record_count"], 1)
        self.assertEqual(
            blocked_unexpected["qualification_classification"],
            "not_qualified",
        )

    def test_watchdog_promotes_lightweight_orders_and_field_summaries(self) -> None:
        record = {
            "hybrid_system": {
                "bottom_matrix_stats": {"matrix_rows": 100, "matrix_nnz_used": 500},
                "top_matrix_stats": {"matrix_rows": 120, "matrix_nnz_used": 600},
                "bottom_local_fe_dofs": 90,
                "top_local_fe_dofs": 110,
                "bottom_global_size": 100,
                "top_global_size": 120,
                "internal_unknown_count": 320,
            },
            "validation": {
                "port_power": {"R_total": 0.1},
                "external_diffraction_orders": [{"m": 0, "n": 0}],
            },
            "physical_field_reconstruction": {
                "interface_continuity": {"electric_relative_error": 1.0e-5},
                "volume_absorption": {"A_volume": 0.4},
                "selected_plane_full3d_comparison": {"max_E_error": 1.0e-4},
                "sample_payload_bytes": 4096,
                "sample_grid_shape_z_y_x_component": [3, 4, 5, 3],
                "full_middle_volume_reconstructed": False,
                "heavy_field_vector": [1, 2, 3],
            },
            "object_payload_ledger": {
                "projection_matrix": {
                    "bottom": {"matrix_rows": 80, "matrix_nnz_used": 400}
                },
                "heavy_projection_vector": [1, 2, 3],
            },
            "timing_seconds_max_rank": {"total": 2.5},
        }
        promoted = _hybrid_measurements(record)
        self.assertEqual(
            promoted["validation"]["external_diffraction_orders"],
            [{"m": 0, "n": 0}],
        )
        physical = promoted["physical_field_reconstruction"]
        self.assertIn("selected_plane_full3d_comparison", physical)
        self.assertIn("volume_absorption", physical)
        self.assertNotIn("heavy_field_vector", physical)
        hybrid = promoted["hybrid_system"]
        self.assertEqual(hybrid["bottom_matrix_stats"]["matrix_rows"], 100)
        self.assertEqual(hybrid["top_local_fe_dofs"], 110)
        ledger = promoted["object_payload_ledger"]
        self.assertIn("projection_matrix", ledger)
        self.assertNotIn("heavy_projection_vector", ledger)
        self.assertEqual(promoted["timing_seconds_max_rank"]["total"], 2.5)

    def test_new_schema_accepts_qep_aggregate_and_rejects_single_m_promotion(self) -> None:
        try:
            import jsonschema
        except ImportError:  # pragma: no cover
            self.skipTest("jsonschema is not installed")
        schema = json.loads(
            (ROOT / "benchmarks" / "task033_qep_qualification_schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = jsonschema.Draft202012Validator(schema)
        qep_records = [
            _qep_shard(material, degree, h_nm)
            for material in ("air", "lossy_homogeneous", "stage4_xy")
            for degree in TREND_DEGREES
            for h_nm in TREND_H_NM
        ]
        live_shard = _qep_shard("air", 3, 3.0)
        validator.validate(live_shard)
        qualified_aggregate = aggregate_qep_shards(qep_records)
        validator.validate(qualified_aggregate)

        contradictory_aggregate = copy.deepcopy(qualified_aggregate)
        contradictory_aggregate["qualification_classification"] = (
            "not_qualified"
        )
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(contradictory_aggregate)

        partial_records = copy.deepcopy(qep_records)
        p4_index = next(
            index
            for index, record in enumerate(partial_records)
            if record["candidate"]["degree"] == 4
        )
        partial_records[p4_index] = _controlled_p4_negative(
            partial_records[p4_index]
        )
        validator.validate(
            aggregate_qep_shards(
                partial_records, allow_p4_controlled_negative=True
            )
        )

        missing_pairing_policy = copy.deepcopy(live_shard)
        del missing_pairing_policy["numerical_results"][
            "left_right_classification"
        ]["left_candidate_pool_policy"]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(missing_pairing_policy)

        forged_pair_pass = copy.deepcopy(live_shard)
        classification = forged_pair_pass["numerical_results"][
            "left_right_classification"
        ]
        classification["left_pair_relative_errors"][-1] = 2.0e-7
        classification["left_pair_relative_error_max"] = 2.0e-7
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(forged_pair_pass)

        forged = copy.deepcopy(_hybrid_shard(160, 0.0))
        forged["physical_qualified"] = True
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(forged)


if __name__ == "__main__":
    unittest.main()
