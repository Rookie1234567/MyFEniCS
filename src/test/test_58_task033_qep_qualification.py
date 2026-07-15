from __future__ import annotations

import copy
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
    qep_shard_gate,
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
            "is_physical_qualification_record": False,
            "physical_qualified": False,
        },
        "candidate": {
            "material_kind": material,
            "degree": degree,
            "h_nm": h_nm,
            "mpi_size": 1,
        },
        "memory_prediction": {},
        "runtime_preflight": {},
        "provenance": _source(),
        "numerical_results": {
            "analytic_beta_relative_error": analytic_error,
            "left_right_classification": {
                "right_polynomial_relative_residual_max": 1.0e-12,
                "left_polynomial_relative_residual_max": 1.0e-10,
                "biorthogonality_identity_error": 1.0e-8,
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
        "gates": {"all_required_numerical_gates_pass": True},
    }


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
        validator.validate(aggregate_qep_shards(qep_records))
        forged = copy.deepcopy(_hybrid_shard(160, 0.0))
        forged["physical_qualified"] = True
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(forged)


if __name__ == "__main__":
    unittest.main()
