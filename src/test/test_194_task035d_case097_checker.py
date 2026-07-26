from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from benchmarks.run_direct_memory_forensics import TIMELINE_FIELDS
from benchmarks.task035d_case097_checker import (
    MANDATORY_PEAK_GIB,
    STATIC_P6_FACTOR_NNZ,
    STATIC_P6_MATRIX_NNZ,
    Task035dEvidenceError,
    _candidate_launch_contract,
    _control_field_directories,
    _energy_comparison,
    _load_frozen_authorities,
    _resource_comparison,
    _timeline_resource_metrics,
    evaluate_task035d_case097_candidate,
    main,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_LOCAL_H_ACTIVE_FE_DOFS,
    TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256,
    TASK035D_LOCAL_H_AUTHORITY_PATH,
    TASK035D_LOCAL_H_PLAN_FILE_SHA256,
    TASK035D_LOCAL_H_PLAN_NAME,
    TASK035D_LOCAL_H_PLAN_PATH,
    TASK035D_LOCAL_H_SOLVE_ROWS,
    TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS,
    TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256,
    TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH,
    TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256,
    TASK035D_SIDEWALL_GUARD_PLAN_PATH,
    TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
    TASK035D_T30_ACTIVE_FE_DOFS,
    TASK035D_T30_AUTHORITY_FILE_SHA256,
    TASK035D_T30_AUTHORITY_PATH,
    TASK035D_T30_PLAN_FILE_SHA256,
    TASK035D_T30_PLAN_PATH,
    TASK035D_T30_SOLVE_ROWS,
    task035d_case097_local_h_plan_authority_gate,
    task035d_case097_sidewall_guard_plan_authority_gate,
)
from src.adaptivity.high_order_same_error import (
    _sample_lagrange_hex_position_fallback,
)


ROOT = Path(__file__).resolve().parents[2]
T30_CONTROLLED_NEGATIVE = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
    / "records"
    / "t30_h10_mpi8_controlled_negative_v1.json"
)
T30_CONTROLLED_NEGATIVE_SHA256 = (
    "ac0266578fe38dd9934cfcfb840d817f8c4fbc617694a068462f7d505392acc1"
)


def _timeline_row(*, process_rss_mb: float = 512.0) -> dict[str, object]:
    smaps = [
        {
            "rank": rank,
            "pid": 1000 + rank,
            "rss_mb": 40.0 + rank,
            "pss_mb": 35.0 + rank,
            "uss_mb": 30.0 + rank,
            "shared_mb": 10.0,
            "anonymous_mb": 25.0 + rank,
            "swap_mb": 0.0,
            "swap_pss_mb": 0.0,
        }
        for rank in range(8)
    ]
    workers = [
        {
            "rank": item["rank"],
            "pid": item["pid"],
            "rss_mb": item["rss_mb"],
        }
        for item in smaps
    ]
    return {
        "timestamp_utc": "2026-07-26T00:00:00+00:00",
        "elapsed_seconds": 1.0,
        "stage": "during_ksp_setup_peak",
        "stage_status": "running",
        "worker_rank_rss_sum_mb": sum(item["rss_mb"] for item in smaps),
        "worker_rank_pss_sum_mb": sum(item["pss_mb"] for item in smaps),
        "worker_rank_uss_sum_mb": sum(item["uss_mb"] for item in smaps),
        "worker_rank_shared_sum_mb": sum(
            item["shared_mb"] for item in smaps
        ),
        "worker_rank_smaps_swap_sum_mb": 0.0,
        "mpi_process_tree_rss_mb": process_rss_mb,
        "mpi_process_tree_swap_mb": 0.0,
        "container_process_rss_sum_mb": process_rss_mb,
        "worker_rank_rss_mb_json": json.dumps(workers),
        "worker_rank_smaps_rollup_json": json.dumps(smaps),
        "worker_rank_smaps_readable_count": 8,
        "worker_rank_cpu_affinity_json": "[]",
        "worker_rank_thread_count_sum": 8,
        "worker_rank_thread_runtime_json": "[]",
        "mpi_process_tree_thread_count": 9,
        "worker_rank_cpu_seconds": 8.0,
        "mpi_process_tree_cpu_seconds": 8.0,
        "worker_rank_cpu_core_equivalents": 8.0,
        "mpi_process_tree_cpu_core_equivalents": 8.0,
        "container_cgroup_current_mb": 1024.0,
        "container_cgroup_peak_mb": 2048.0,
        "container_swap_current_mb": 0.0,
        "job_cgroup_path": "/init.scope",
        "job_cgroup_dedicated": False,
        "wsl_pswpin_pages": 0,
        "wsl_pswpout_pages": 0,
        "ooc_scratch_file_count": 0,
        "ooc_scratch_bytes": 0,
        "mpi_process_tree_read_bytes": 0,
        "mpi_process_tree_write_bytes": 0,
        "mpi_process_tree_blkio_delay_seconds": 0.0,
    }


def _write_timeline(path: Path, row: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerow(row)


def _solver_summary() -> dict:
    return {
        "num_actual_conforming_active_fe_dofs": (
            TASK035D_T30_ACTIVE_FE_DOFS
        ),
        "matrix_stats": {
            "matrix_rows": TASK035D_T30_SOLVE_ROWS,
            "matrix_nnz_used": STATIC_P6_MATRIX_NNZ - 1,
        },
        "stage4_dtn_factor_inventory": {
            "matrix_stats": {
                "matrix_nnz_used": STATIC_P6_FACTOR_NNZ - 1,
            }
        },
    }


def _pass_payload() -> dict:
    return {"pass": True}


class Task035dCase097CheckerTests(unittest.TestCase):
    def test_lagrange_hex_locator_fallback_is_exact_and_unique(self) -> None:
        import numpy as np
        import pyvista as pv
        from vtkmodules.vtkCommonDataModel import vtkLagrangeHexahedron

        order = (2, 2, 2)
        points = np.zeros((27, 3), dtype=np.float64)
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    index = vtkLagrangeHexahedron.PointIndexFromIJK(
                        i,
                        j,
                        k,
                        order,
                    )
                    points[index] = (0.5 * i, 0.5 * j, 0.5 * k)
        cells = np.concatenate(
            ([len(points)], np.arange(len(points), dtype=np.int64))
        )
        grid = pv.UnstructuredGrid(
            cells,
            np.asarray(
                [pv.CellType.LAGRANGE_HEXAHEDRON],
                dtype=np.uint8,
            ),
            points,
        )
        real = np.column_stack(
            (
                points[:, 0] + 2.0 * points[:, 1],
                points[:, 1] - points[:, 2],
                points[:, 2] + 3.0 * points[:, 0],
            )
        )
        imaginary = -0.5 * real
        query = np.asarray([[0.2, 0.3, 0.4]], dtype=np.float64)
        fallback = _sample_lagrange_hex_position_fallback(
            grid,
            query,
            np.asarray([True]),
            real,
            imaginary,
        )
        expected_real = np.asarray([0.8, -0.1, 1.0])
        self.assertEqual(fallback["valid"].tolist(), [True])
        self.assertEqual(fallback["ambiguous"], [])
        np.testing.assert_allclose(
            fallback["values"][0],
            expected_real - 0.5j * expected_real,
            rtol=0.0,
            atol=2.0e-15,
        )

    def test_t30_controlled_negative_record_is_hash_bound(self) -> None:
        self.assertEqual(
            hashlib.sha256(T30_CONTROLLED_NEGATIVE.read_bytes()).hexdigest(),
            T30_CONTROLLED_NEGATIVE_SHA256,
        )
        record = json.loads(
            T30_CONTROLLED_NEGATIVE.read_text(encoding="utf-8")
        )
        self.assertEqual(
            record["status"],
            "task035d_t30_p_only_controlled_negative",
        )
        self.assertFalse(record["pass"])
        self.assertEqual(
            record["channel_comparison"][
                "significant_power_pass_count"
            ],
            0,
        )
        self.assertEqual(
            record["channel_comparison"][
                "significant_complex_amplitude_pass_count"
            ],
            0,
        )
        self.assertTrue(record["resource_comparison"]["pass"])
        self.assertEqual(
            record["source_sha"],
            "c3768cf4723c2ae949c82d1ce8b18a56f5ab0f7b",
        )
        self.assertEqual(
            record["checker_source"]["commit_sha"],
            "5f960f912809b162e363259b0896af25ef3b0018",
        )

    def test_candidate_launch_contract_is_bound_to_actual_command(
        self,
    ) -> None:
        source_sha = "a" * 40
        command = [
            "mpiexec",
            "-n",
            "8",
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "benchmarks.run_task033_full3d_watchdog",
            "--worker",
            "--degree",
            "6",
            "--h-nm",
            "10.0",
            "--polarization-kind",
            "s",
            "--run-kind",
            "full-solve",
            "--mpi-size",
            "8",
            "--profile",
            "default",
            "--stage4-full3d-assembly-backend",
            TASK035D_CASE097_BACKEND,
            "--stage4-variable-p-cell-degree-plan",
            str(ROOT / TASK035D_T30_PLAN_PATH),
            "--stage4-variable-p-cell-degree-plan-sha256",
            TASK035D_T30_PLAN_FILE_SHA256,
            "--task035d-case097-gate",
            "--task035d-plan-authority",
            str(ROOT / TASK035D_T30_AUTHORITY_PATH),
            "--task035d-plan-authority-sha256",
            TASK035D_T30_AUTHORITY_FILE_SHA256,
            "--verified-clean-sha",
            source_sha,
        ]
        record = {
            "command": command,
            "task035d_case097_launch_gate": {
                "schema_version": "task035d.case097-t30-launch-gate.v1",
                "status": "task035d_t30_launch_authority_pass",
                "pass": True,
                "checks": {"frozen": True},
                "failures": [],
                "accuracy_credit": (
                    "none_until_fresh_12_channel_checker_passes"
                ),
                "plan_identity": {
                    "path": TASK035D_T30_PLAN_PATH,
                    "file_sha256": TASK035D_T30_PLAN_FILE_SHA256,
                    "actual_conforming_active_fe_dofs": (
                        TASK035D_T30_ACTIVE_FE_DOFS
                    ),
                    "predicted_direct_solve_rows": TASK035D_T30_SOLVE_ROWS,
                },
            },
            "resource_policy": {"swap_allowed": False},
            "no_swap": True,
            "task035d_accuracy_credit": (
                "pending_independent_12_channel_and_field_checker"
            ),
        }
        contract = _candidate_launch_contract(
            record,
            source_sha=source_sha,
        )
        self.assertTrue(contract["pass"])

        drifted = json.loads(json.dumps(record))
        drifted["command"][
            drifted["command"].index(
                "--stage4-variable-p-cell-degree-plan-sha256"
            )
            + 1
        ] = "0" * 64
        with self.assertRaises(Task035dEvidenceError):
            _candidate_launch_contract(drifted, source_sha=source_sha)

    def test_sidewall_guard_launch_contract_requires_candidate_identity(
        self,
    ) -> None:
        source_sha = "b" * 40
        plan_path = ROOT / TASK035D_SIDEWALL_GUARD_PLAN_PATH
        authority_path = ROOT / TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        authority = json.loads(
            authority_path.read_text(encoding="utf-8")
        )
        embedded = (
            task035d_case097_sidewall_guard_plan_authority_gate(
                plan,
                authority,
                expected_plan_file_sha256=(
                    TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256
                ),
                observed_plan_file_sha256=(
                    TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256
                ),
                expected_authority_sha256=(
                    TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256
                ),
                observed_authority_sha256=(
                    TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256
                ),
                plan_is_tracked=True,
                authority_is_tracked=True,
                plan_path_from_root=(
                    TASK035D_SIDEWALL_GUARD_PLAN_PATH
                ),
                authority_path_from_root=(
                    TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH
                ),
            )
        )
        self.assertTrue(embedded["pass"], embedded["failures"])
        command = [
            "mpiexec",
            "-n",
            "8",
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "benchmarks.run_task033_full3d_watchdog",
            "--worker",
            "--degree",
            "6",
            "--h-nm",
            "10.0",
            "--polarization-kind",
            "s",
            "--run-kind",
            "full-solve",
            "--mpi-size",
            "8",
            "--profile",
            "default",
            "--stage4-full3d-assembly-backend",
            TASK035D_CASE097_BACKEND,
            "--task035d-case097-gate",
            "--task035d-candidate-id",
            "sidewall_z0_guard_v1",
            "--stage4-variable-p-cell-degree-plan",
            str(plan_path),
            "--stage4-variable-p-cell-degree-plan-sha256",
            TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256,
            "--task035d-plan-authority",
            str(authority_path),
            "--task035d-plan-authority-sha256",
            TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256,
            "--verified-clean-sha",
            source_sha,
        ]
        record = {
            "command": command,
            "task035d_candidate_id": "sidewall_z0_guard_v1",
            "task035d_case097_launch_gate": embedded,
            "resource_policy": {"swap_allowed": False},
            "no_swap": True,
            "task035d_accuracy_credit": (
                "pending_independent_12_channel_and_field_checker"
            ),
        }
        contract = _candidate_launch_contract(
            record,
            source_sha=source_sha,
            candidate_id="sidewall_z0_guard_v1",
        )
        self.assertTrue(contract["pass"])
        self.assertEqual(
            embedded["plan_identity"][
                "actual_conforming_active_fe_dofs"
            ],
            TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS,
        )
        self.assertEqual(
            embedded["plan_identity"]["predicted_direct_solve_rows"],
            TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
        )

        drifted = json.loads(json.dumps(record))
        drifted["task035d_candidate_id"] = "t30"
        with self.assertRaises(Task035dEvidenceError):
            _candidate_launch_contract(
                drifted,
                source_sha=source_sha,
                candidate_id="sidewall_z0_guard_v1",
            )

    def test_h15_local_h_launch_contract_uses_only_local_h_plan(self) -> None:
        source_sha = "c" * 40
        plan_path = ROOT / TASK035D_LOCAL_H_PLAN_PATH
        authority_path = ROOT / TASK035D_LOCAL_H_AUTHORITY_PATH
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        authority = json.loads(
            authority_path.read_text(encoding="utf-8")
        )
        embedded = task035d_case097_local_h_plan_authority_gate(
            plan,
            authority,
            expected_plan_file_sha256=TASK035D_LOCAL_H_PLAN_FILE_SHA256,
            observed_plan_file_sha256=TASK035D_LOCAL_H_PLAN_FILE_SHA256,
            expected_authority_sha256=(
                TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256
            ),
            observed_authority_sha256=(
                TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256
            ),
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=TASK035D_LOCAL_H_PLAN_PATH,
            authority_path_from_root=TASK035D_LOCAL_H_AUTHORITY_PATH,
        )
        self.assertTrue(embedded["pass"], embedded["failures"])
        command = [
            "mpiexec",
            "-n",
            "8",
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "benchmarks.run_task033_full3d_watchdog",
            "--worker",
            "--degree",
            "6",
            "--h-nm",
            "15.0",
            "--polarization-kind",
            "s",
            "--run-kind",
            "full-solve",
            "--mpi-size",
            "8",
            "--profile",
            "default",
            "--stage4-full3d-assembly-backend",
            TASK035D_CASE097_BACKEND,
            "--stage4-local-h-refinement-plan",
            str(plan_path),
            "--stage4-local-h-refinement-plan-sha256",
            TASK035D_LOCAL_H_PLAN_FILE_SHA256,
            "--task035d-case097-gate",
            "--task035d-candidate-id",
            TASK035D_LOCAL_H_PLAN_NAME,
            "--task035d-plan-authority",
            str(authority_path),
            "--task035d-plan-authority-sha256",
            TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256,
            "--verified-clean-sha",
            source_sha,
        ]
        record = {
            "command": command,
            "task035d_candidate_id": TASK035D_LOCAL_H_PLAN_NAME,
            "task035d_case097_launch_gate": embedded,
            "resource_policy": {"swap_allowed": False},
            "no_swap": True,
            "task035d_accuracy_credit": (
                "pending_independent_12_channel_and_field_checker"
            ),
        }
        contract = _candidate_launch_contract(
            record,
            source_sha=source_sha,
            candidate_id=TASK035D_LOCAL_H_PLAN_NAME,
        )
        self.assertTrue(contract["pass"])
        self.assertEqual(
            embedded["plan_identity"][
                "actual_conforming_active_fe_dofs"
            ],
            TASK035D_LOCAL_H_ACTIVE_FE_DOFS,
        )
        self.assertEqual(
            embedded["plan_identity"]["predicted_direct_solve_rows"],
            TASK035D_LOCAL_H_SOLVE_ROWS,
        )

        mixed = json.loads(json.dumps(record))
        mixed["command"].extend(
            (
                "--stage4-variable-p-cell-degree-plan",
                str(ROOT / TASK035D_T30_PLAN_PATH),
            )
        )
        with self.assertRaises(Task035dEvidenceError):
            _candidate_launch_contract(
                mixed,
                source_sha=source_sha,
                candidate_id=TASK035D_LOCAL_H_PLAN_NAME,
            )

    def test_frozen_control_field_shards_remain_hash_bound(self) -> None:
        authorities = _load_frozen_authorities()
        p5_dir, p6_dir, observed = _control_field_directories(authorities)
        self.assertTrue(p5_dir.is_dir())
        self.assertTrue(p6_dir.is_dir())
        self.assertEqual(len(observed["global_p5_control"]), 8)
        self.assertEqual(len(observed["global_p6_reference"]), 8)

    def test_timeline_recomputes_mpi8_pss_uss_and_cgroup_diagnostic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timeline.csv"
            row = _timeline_row()
            row["worker_rank_rss_sum_mb"] = (
                float(row["worker_rank_rss_sum_mb"]) - 0.25
            )
            _write_timeline(path, row)
            metrics = _timeline_resource_metrics(path)
            self.assertEqual(metrics["max_observed_worker_rank_count"], 8)
            self.assertEqual(
                metrics["fully_readable_mpi8_smaps_sample_count"],
                1,
            )
            self.assertEqual(
                metrics["max_container_cgroup_current_observed_mb"],
                1024.0,
            )
            self.assertFalse(metrics["dedicated_job_cgroup_observed"])
            self.assertEqual(metrics["memory_authority_gib"], 0.5)
            self.assertTrue(metrics["zero_swap"])
            self.assertEqual(
                metrics["per_rank_smaps_rollup_peak_mb"]["7"]["uss_mb"],
                37.0,
            )

            tampered = dict(row)
            tampered["worker_rank_pss_sum_mb"] = 1.0
            _write_timeline(path, tampered)
            with self.assertRaises(Task035dEvidenceError):
                _timeline_resource_metrics(path)

    def test_energy_and_resource_gates_are_independently_recomputed(
        self,
    ) -> None:
        candidate = {
            "R00_s": 0.01,
            "R00_p": 0.0,
            "R00_total": 0.01,
            "R_total": 0.1,
            "T_total": 0.6,
            "A_volume_total": 0.3,
            "energy_closure_error_port_volume": 0.0,
        }
        coarse = {"A_volume_total": 0.29}
        enriched = {"A_volume_total": 0.3}
        energy = _energy_comparison(candidate, coarse, enriched)
        self.assertTrue(energy["pass"], energy["checks"])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timeline.csv"
            _write_timeline(path, _timeline_row())
            timeline = _timeline_resource_metrics(path)
        watchdog_resource = {
            key: value
            for key, value in timeline.items()
            if key
            in {
                "sample_count",
                "fully_readable_mpi8_smaps_sample_count",
                "max_observed_worker_rank_count",
                "max_simultaneous_worker_rss_mb",
                "max_simultaneous_worker_pss_mb",
                "max_simultaneous_worker_uss_mb",
                "max_simultaneous_worker_smaps_swap_mb",
                "max_process_tree_rss_mb",
                "max_process_tree_swap_mb",
                "max_container_cgroup_current_observed_mb",
                "max_container_cgroup_peak_mb",
                "memory_authority_mb",
                "memory_authority_gib",
                "per_rank_smaps_rollup_peak_mb",
            }
        }
        resource = _resource_comparison(
            solver_summary=_solver_summary(),
            watchdog_resource=watchdog_resource,
            timeline=timeline,
        )
        self.assertTrue(resource["pass"], resource["checks"])
        self.assertLess(
            resource["candidate"]["peak_memory_gib"],
            MANDATORY_PEAK_GIB,
        )

        failed_timeline = dict(timeline)
        failed_timeline["memory_authority_gib"] = MANDATORY_PEAK_GIB + 0.1
        failed_timeline["memory_authority_mb"] = (
            failed_timeline["memory_authority_gib"] * 1024.0
        )
        failed_resource = _resource_comparison(
            solver_summary=_solver_summary(),
            watchdog_resource={
                **watchdog_resource,
                "memory_authority_gib": failed_timeline[
                    "memory_authority_gib"
                ],
                "memory_authority_mb": failed_timeline[
                    "memory_authority_mb"
                ],
            },
            timeline=failed_timeline,
        )
        self.assertFalse(failed_resource["pass"])
        self.assertFalse(
            failed_resource["checks"][
                "mandatory_peak_reduction_ge_20_percent"
            ]
        )

    def test_final_evaluator_requires_all_12_channels(self) -> None:
        watchdog = {
            "return_code": 0,
            "terminated_for_memory": False,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
            "qualification": {"pass": True},
        }
        solver_gate = {
            "pass": True,
            "checks": {"ordinary_default_unchanged": True},
        }
        channels = {
            "pass": True,
            "significant_power_pass_count": 12,
            "significant_complex_amplitude_pass_count": 12,
        }
        result = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=_pass_payload(),
            solver_gate=solver_gate,
            channel_comparison=channels,
            observable_comparison=_pass_payload(),
            energy_comparison=_pass_payload(),
            field_comparison=_pass_payload(),
            resource_comparison=_pass_payload(),
        )
        self.assertTrue(result["pass"])

        rejected = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=_pass_payload(),
            solver_gate=solver_gate,
            channel_comparison={
                **channels,
                "pass": False,
                "significant_power_pass_count": 11,
            },
            observable_comparison=_pass_payload(),
            energy_comparison=_pass_payload(),
            field_comparison=_pass_payload(),
            resource_comparison=_pass_payload(),
        )
        self.assertFalse(rejected["pass"])
        self.assertIn(
            "significant_12_power_and_12_amplitude",
            rejected["failures"],
        )

    def test_cli_persists_fail_closed_checker_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed.json"
            with mock.patch(
                "benchmarks.task035d_case097_checker."
                "build_task035d_case097_candidate_check",
                side_effect=Task035dEvidenceError("tampered authority"),
            ):
                return_code = main(
                    [
                        "--watchdog",
                        str(Path(directory) / "missing-watchdog.json"),
                        "--watchdog-sha256",
                        "0" * 64,
                        "--output",
                        str(output),
                    ]
                )
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(return_code, 2)
            self.assertFalse(result["pass"])
            self.assertEqual(
                result["classification"],
                "fail_closed_evidence_error",
            )
            self.assertEqual(result["failures"], ["evidence_integrity"])


if __name__ == "__main__":
    unittest.main()
