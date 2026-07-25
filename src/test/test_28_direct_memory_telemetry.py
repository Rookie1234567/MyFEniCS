from __future__ import annotations

import csv
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task035b_condensed_iterative import _iterative_config
from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _cpu_affinity_count,
    _directory_usage,
    _enrich_factor_inventory,
    _historical_peak_upper_bound,
    _latest_stage,
    _numeric_gate,
    _parse_args,
    _read_smaps_rollup,
    _read_thread_runtime,
    _sample,
    _source_provenance,
    _task29_direct_config,
    _two_point_power_law_prediction,
    _validate_h2_gate,
)
from src.solvers.common_3d_case_flow import (
    _linear_solve_failure_summary,
)
from src.solvers.common_3d_solve import (
    CondensedIterativeSolveFailure,
    DirectSolveFailure,
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)
from src.solvers.common_3d_utils import (
    _cgroup_memory_fields,
    _clear_official_field_outputs,
    _current_rss_mb,
)
from src.solvers.dtn_port_3d import (
    _iterative_official_output_eligible,
    _petsc_solve_failure_type,
    _solve_augmented_system,
)


class DirectMemoryTelemetryTests(unittest.TestCase):
    def test_historical_peak_upper_bound_uses_all_complete_checkpoints(self) -> None:
        events = [
            {"sum_rank_historical_peaks_mb_upper_bound": 10.0},
            {"sum_rank_historical_peaks_mb_upper_bound": 12.5},
        ]
        summary = {
            "sum_rank_historical_peaks_mb_upper_bound": 11.0,
            "total_peak_rss_mb": 9.0,
        }
        self.assertEqual(_historical_peak_upper_bound(events, summary), 12.5)

    def test_factor_inventory_records_only_algebraic_derived_ratios(self) -> None:
        inventory = {
            "matrix_stats": {
                "matrix_nnz_used": 60.0,
                "matrix_memory_estimate_mb": 24.0,
            }
        }
        augmented = {
            "matrix_nnz_used": 10.0,
            "matrix_memory_estimate_mb": 4.0,
        }
        enriched = _enrich_factor_inventory(inventory, augmented)
        self.assertIsNotNone(enriched)
        ratios = enriched["derived_ratios"]
        self.assertEqual(ratios["factor_to_augmented_nnz_ratio"], 6.0)
        self.assertEqual(ratios["factor_to_augmented_estimated_storage_ratio"], 6.0)
        self.assertIn("not inferred MUMPS", ratios["semantics"])

    def test_worker_forces_full_solve_not_assemble_only(self) -> None:
        args = _parse_args(["--h-nm", "5", "--profile", "default"])
        cfg = _task29_direct_config(args)
        self.assertFalse(cfg.matrix_diagnostics_assemble_only)
        self.assertEqual(cfg.stage_case, "stage4_block_grating")
        self.assertEqual(cfg.stage4_dtn_order_policy, "auto_propagating")

    def test_release_base_candidate_is_explicit_opt_in(self) -> None:
        ordinary = _task29_direct_config(_parse_args(["--h-nm", "5"]))
        candidate = _task29_direct_config(
            _parse_args(["--h-nm", "5", "--release-base-after-augmentation"])
        )
        self.assertFalse(ordinary.direct_release_base_after_augmentation)
        self.assertFalse(
            ordinary.stage4_assembly_time_cell_static_condensation
        )
        self.assertFalse(
            ordinary.direct_release_solver_before_postprocess
        )
        self.assertTrue(candidate.direct_release_base_after_augmentation)

    def test_ooc_scratch_usage_is_measured_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mumps_ooc_files"
            nested = root / "rank0"
            nested.mkdir(parents=True)
            (root / "a.bin").write_bytes(b"123")
            (nested / "b.bin").write_bytes(b"45678")
            self.assertEqual(_directory_usage(root), (2, 8))

    def test_direct_solve_failure_cleanup_is_idempotent(self) -> None:
        class FakePetscObject:
            def __init__(self) -> None:
                self.handle = 1
                self.destroy_count = 0

            def destroy(self) -> None:
                self.destroy_count += 1
                self.handle = 0

        objects = [FakePetscObject() for _ in range(4)]
        failure = DirectSolveFailure(
            "diagnostic",
            failure_stage="unit_test",
            petsc_error=RuntimeError("unit_test"),
            A=objects[0],
            b=objects[1],
            x=objects[2],
            ksp=objects[3],
        )
        failure.cleanup()
        failure.cleanup()
        self.assertEqual([obj.destroy_count for obj in objects], [1, 1, 1, 1])
        self.assertIsNone(failure.A)
        self.assertIsNone(failure.ksp)

    def test_condensed_iterative_failure_semantics_are_distinct(self) -> None:
        self.assertIs(
            _petsc_solve_failure_type(None),
            DirectSolveFailure,
        )
        self.assertIs(
            _petsc_solve_failure_type("gmres_jacobi"),
            CondensedIterativeSolveFailure,
        )
        failure = CondensedIterativeSolveFailure(
            "iterative diagnostic",
            failure_stage="stage4_dtn_augmented_solve",
            petsc_error=RuntimeError("unit_test"),
        )
        self.assertNotIsInstance(failure, DirectSolveFailure)

    def test_iterative_exception_summary_is_not_direct_lu(self) -> None:
        cfg = _iterative_config("gmres_jacobi", h_nm=15.0)
        mesh_data = SimpleNamespace(
            mesh_cell_type_resolved="hexahedron",
            mesh_cells_resolved=(6, 2, 10),
            mesh_spacing_mode_resolved="uniform",
            mesh_axis_cell_stats={},
            material_plane_alignment={},
        )
        failure = CondensedIterativeSolveFailure(
            "iterative setup failed",
            failure_stage="stage4_dtn_augmented_ksp_setup",
            petsc_error=RuntimeError("unit_test"),
            solver_backend="PETSc assembled condensed iterative",
        )
        log_lines: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            summary = _linear_solve_failure_summary(
                cfg=cfg,
                out_dir=Path(tmp),
                comm=MPI.COMM_SELF,
                timings={},
                started=time.perf_counter(),
                log=log_lines.append,
                log_lines=log_lines,
                petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
                selected_parallel_lu="mumps",
                dot_k_p=0.0j,
                failure=failure,
                num_cells=120,
                num_dofs=74890,
                floquet_data=None,
                mesh_data=mesh_data,
                domain_tag_volumes={},
                unconstrained_rhs_norm=None,
                unconstrained_matrix_stats=None,
                field_formulation="layered_scattered",
                solve_stage4_dtn_port=True,
                raw_boundary_dofs_global=0,
                boundary_dofs_global=0,
                ooc_info={},
            )
        self.assertEqual(
            summary["case_status"],
            "failed_condensed_iterative_exception",
        )
        self.assertEqual(
            summary["linear_solve_method"],
            "assembled_condensed_iterative",
        )
        self.assertIsNone(summary["petsc_direct_solver_profile"])
        self.assertEqual(summary["linear_solve_petsc_options"], {})
        self.assertTrue(summary["iterative_raw_petsc_options_ignored"])
        self.assertIsNone(summary["selected_parallel_lu_solver_type"])
        self.assertIn("condensed_iterative_solve_exception", summary)
        self.assertNotIn("direct_solve_exception", summary)

    def test_direct_exception_summary_remains_direct_lu(self) -> None:
        cfg = replace(
            _iterative_config("gmres_jacobi", h_nm=15.0),
            stage4_condensed_iterative_profile=None,
        )
        mesh_data = SimpleNamespace(
            mesh_cell_type_resolved="hexahedron",
            mesh_cells_resolved=(6, 2, 10),
            mesh_spacing_mode_resolved="uniform",
            mesh_axis_cell_stats={},
            material_plane_alignment={},
        )
        failure = DirectSolveFailure(
            "direct setup failed",
            failure_stage="stage4_dtn_augmented_ksp_setup",
            petsc_error=RuntimeError("unit_test"),
            solver_backend="PETSc direct LU",
        )
        log_lines: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            summary = _linear_solve_failure_summary(
                cfg=cfg,
                out_dir=Path(tmp),
                comm=MPI.COMM_SELF,
                timings={},
                started=time.perf_counter(),
                log=log_lines.append,
                log_lines=log_lines,
                petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
                selected_parallel_lu="mumps",
                dot_k_p=0.0j,
                failure=failure,
                num_cells=120,
                num_dofs=74890,
                floquet_data=None,
                mesh_data=mesh_data,
                domain_tag_volumes={},
                unconstrained_rhs_norm=None,
                unconstrained_matrix_stats=None,
                field_formulation="layered_scattered",
                solve_stage4_dtn_port=True,
                raw_boundary_dofs_global=0,
                boundary_dofs_global=0,
                ooc_info={},
            )
        self.assertEqual(summary["case_status"], "failed_direct_lu_exception")
        self.assertEqual(summary["linear_solve_method"], "direct_lu")
        self.assertEqual(
            summary["petsc_direct_solver_profile"],
            cfg.petsc_direct_solver_profile_requested,
        )
        self.assertEqual(
            summary["linear_solve_petsc_options"]["pc_type"],
            "lu",
        )
        self.assertEqual(
            summary["selected_parallel_lu_solver_type"],
            "mumps",
        )
        self.assertIn("direct_solve_exception", summary)
        self.assertNotIn("condensed_iterative_solve_exception", summary)

    def test_iterative_official_outputs_require_ksp_and_true_residual(
        self,
    ) -> None:
        self.assertTrue(
            _iterative_official_output_eligible(
                None,
                converged_reason=-3,
                full_relative_residual=None,
            )
        )
        self.assertFalse(
            _iterative_official_output_eligible(
                "gmres_jacobi",
                converged_reason=-3,
                full_relative_residual=1.0e-12,
            )
        )
        self.assertFalse(
            _iterative_official_output_eligible(
                "gmres_jacobi",
                converged_reason=2,
                full_relative_residual=2.0e-9,
            )
        )
        self.assertTrue(
            _iterative_official_output_eligible(
                "gmres_jacobi",
                converged_reason=2,
                full_relative_residual=1.0e-10,
            )
        )

    def test_failure_cleanup_removes_port_and_amplitude_outputs(self) -> None:
        official_names = (
            "port_power.json",
            "port_power.csv",
            "dtn_port_power_metrics_3d.json",
            "dtn_port_diffraction_orders_3d.json",
            "dtn_port_diffraction_orders_3d.csv",
            "dtn_auxiliary_amplitudes_3d.json",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in official_names:
                (root / name).write_text("diagnostic", encoding="utf-8")
            retained = root / "run_summary.json"
            retained.write_text("{}", encoding="utf-8")
            _clear_official_field_outputs(root, MPI.COMM_SELF)
            self.assertFalse(
                any((root / name).exists() for name in official_names)
            )
            self.assertTrue(retained.is_file())

    def test_memory_snapshot_schema(self) -> None:
        self.assertIsNotNone(_current_rss_mb())
        cgroup = _cgroup_memory_fields()
        self.assertIn("container_cgroup_current_mb", cgroup)
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "progress.jsonl"
            row = _sample(os.getpid(), progress, 0.0)
        self.assertEqual(set(TIMELINE_FIELDS), set(row))
        self.assertEqual(row["stage"], "process_start")
        self.assertGreaterEqual(float(row["container_process_rss_sum_mb"]), 0.0)
        self.assertIn("worker_rank_smaps_rollup_json", row)
        self.assertIn("worker_rank_uss_sum_mb", row)

    def test_linux_smaps_rollup_reports_pss_and_uss(self) -> None:
        rollup = _read_smaps_rollup(Path("/proc/self/smaps_rollup"))
        self.assertIsInstance(rollup, dict)
        assert rollup is not None
        self.assertGreater(rollup["rss_mb"], 0.0)
        self.assertGreater(rollup["pss_mb"], 0.0)
        self.assertGreaterEqual(rollup["uss_mb"], 0.0)

    def test_linux_thread_runtime_is_auditable(self) -> None:
        runtime = _read_thread_runtime(Path("/proc/self"))
        self.assertIsInstance(runtime, dict)
        assert runtime is not None
        self.assertGreaterEqual(runtime["thread_count_observed"], 1)
        self.assertTrue(runtime["thread_name_counts"])
        self.assertTrue(runtime["thread_wchan_counts"])
        self.assertIsInstance(
            runtime["loaded_parallel_runtime_libraries"],
            list,
        )

    def test_stage_marker_reads_last_complete_json_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.jsonl"
            path.write_text(
                '{"stage":"after_mesh","status":"end"}\n{"stage":"before_ksp_setup","status":"begin"}\n{partial',
                encoding="utf-8",
            )
            self.assertEqual(_latest_stage(path), ("before_ksp_setup", "begin"))

    def test_matrix_info_is_json_serializable(self) -> None:
        matrix = PETSc.Mat().createAIJ([3, 3], nnz=1, comm=PETSc.COMM_SELF)
        try:
            for index in range(3):
                matrix.setValue(index, index, 2.0)
            matrix.assemble()
            stats = _petsc_matrix_stats(matrix)
            json.dumps(stats)
            self.assertEqual(stats["matrix_rows"], 3)
            self.assertEqual(stats["matrix_cols"], 3)
            self.assertEqual(stats["matrix_row_ownership_range"], [0, 3])
            self.assertIn("matrix_nnz_unneeded", stats)
            self.assertIn("matrix_mallocs", stats)
            self.assertIn("matrix_petsc_info_global_sum", stats)
        finally:
            matrix.destroy()


    def test_factorization_only_stops_after_ksp_setup(self) -> None:
        matrix = PETSc.Mat().createAIJ([2, 2], nnz=1, comm=PETSc.COMM_SELF)
        diagonal = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
        rhs = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
        x = None
        ksp = None
        try:
            diagonal.set(2.0)
            rhs.set(1.0)
            matrix.setDiagonal(diagonal)
            matrix.assemble()
            with tempfile.TemporaryDirectory() as tmp:
                x, ksp, telemetry = _solve_augmented_system(
                    matrix,
                    rhs,
                    {"ksp_type": "preonly", "pc_type": "lu"},
                    "task034_factorization_gate_test_",
                    out_dir=Path(tmp),
                    comm=MPI.COMM_SELF,
                    dofs=2,
                    constraints=0,
                    factorization_only=True,
                )
                events = [
                    json.loads(line)
                    for line in (Path(tmp) / "progress_3d.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
            stages = {event["stage"] for event in events}
            self.assertTrue(telemetry["factorization_only"])
            self.assertIsInstance(telemetry["factor_inventory"], dict)
            self.assertEqual(x.norm(), 0.0)
            self.assertIn("after_ksp_setup_factorized", stages)
            self.assertFalse(
                stages
                & {
                    "stage4_dtn_augmented_solve",
                    "before_ksp_solve",
                    "during_ksp_solve_peak",
                    "after_ksp_solve",
                }
            )
        finally:
            if ksp is not None:
                ksp.destroy()
            if x is not None:
                x.destroy()
            rhs.destroy()
            diagonal.destroy()
            matrix.destroy()

    def test_condensed_iterative_profile_is_programmatic_and_factor_free(
        self,
    ) -> None:
        matrix = PETSc.Mat().createAIJ(
            [3, 3],
            nnz=1,
            comm=PETSc.COMM_SELF,
        )
        diagonal = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
        rhs = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
        x = None
        ksp = None
        try:
            diagonal.set(2.0)
            rhs.set(1.0)
            matrix.setDiagonal(diagonal)
            matrix.assemble()
            x, ksp, telemetry = _solve_augmented_system(
                matrix,
                rhs,
                {"ksp_type": "preonly", "pc_type": "lu"},
                "task035b_iterative_test_",
                comm=MPI.COMM_SELF,
                dofs=3,
                constraints=0,
                iterative_profile="gmres_jacobi",
            )
            audit = telemetry["condensed_iterative"]
            self.assertEqual(ksp.getType(), "gmres")
            self.assertEqual(ksp.getPC().getType(), "jacobi")
            self.assertTrue(audit["configured_programmatically"])
            self.assertFalse(
                audit["raw_petsc_options_used_for_iterative_configuration"]
            )
            self.assertEqual(audit["global_direct_factor_nnz"], 0)
            self.assertLess(
                audit["terminal_explicit_reduced_relative_residual"],
                1.0e-12,
            )
            self.assertFalse(
                telemetry["factor_inventory"]["available"]
            )
        finally:
            if ksp is not None:
                ksp.destroy()
            if x is not None:
                x.destroy()
            rhs.destroy()
            diagonal.destroy()
            matrix.destroy()

    def test_condensed_fgmres_asm_ilu_profile_is_programmatic(self) -> None:
        matrix = PETSc.Mat().createAIJ(
            [4, 4],
            nnz=3,
            comm=PETSc.COMM_SELF,
        )
        rhs = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
        x = None
        ksp = None
        try:
            for row in range(4):
                matrix.setValue(row, row, 4.0)
                if row:
                    matrix.setValue(row, row - 1, -1.0)
                if row + 1 < 4:
                    matrix.setValue(row, row + 1, -1.0)
            matrix.assemble()
            rhs.set(1.0)
            x, ksp, telemetry = _solve_augmented_system(
                matrix,
                rhs,
                {},
                "task035b_fgmres_asm_test_",
                comm=MPI.COMM_SELF,
                dofs=4,
                constraints=0,
                iterative_profile="fgmres_asm_ilu",
            )
            audit = telemetry["condensed_iterative"]
            self.assertEqual(ksp.getType(), "fgmres")
            self.assertEqual(ksp.getPC().getType(), "asm")
            self.assertTrue(audit["configured_programmatically"])
            self.assertEqual(audit["global_direct_factor_nnz"], 0)
            self.assertTrue(
                telemetry["factor_inventory"][
                    "local_subdomain_ilu_active"
                ]
            )
            self.assertLess(
                audit["terminal_explicit_reduced_relative_residual"],
                1.0e-12,
            )
        finally:
            if ksp is not None:
                ksp.destroy()
            if x is not None:
                x.destroy()
            rhs.destroy()
            matrix.destroy()

    def test_factor_inventory_does_not_reassemble_factored_matrix(self) -> None:
        matrix = PETSc.Mat().createAIJ([3, 3], nnz=1, comm=PETSc.COMM_SELF)
        diagonal = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
        ksp = PETSc.KSP().create(PETSc.COMM_SELF)
        try:
            diagonal.set(1.0)
            matrix.setDiagonal(diagonal)
            matrix.assemble()
            ksp.setType("preonly")
            ksp.getPC().setType("lu")
            ksp.setOperators(matrix)
            ksp.setUp()
            inventory = _petsc_factor_inventory(ksp)
            self.assertTrue(inventory["available"])
            self.assertEqual(inventory["matrix_stats"]["matrix_rows"], 3)
            self.assertEqual(
                inventory["matrix_stats"]["matrix_petsc_info"]["fill_ratio_needed"],
                1.0,
            )
            self.assertFalse(inventory["mumps_api_available"])
        finally:
            ksp.destroy()
            diagonal.destroy()
            matrix.destroy()

    def test_candidate_profile_parser(self) -> None:
        args = _parse_args(
            [
                "--h-nm",
                "5",
                "--profile",
                "mumps_ooc",
                "--mpi-size",
                "2",
                "--threads-per-rank",
                "2",
                "--cpu-affinity",
                "0-3",
            ]
        )
        self.assertEqual(args.h_nm, 5.0)
        self.assertEqual(args.profile, "mumps_ooc")
        self.assertEqual(args.mpi_size, 2)
        self.assertEqual(args.threads_per_rank, 2)
        self.assertEqual(args.cpu_affinity, "0-3")

    def test_cpu_core_equivalents_use_cumulative_proc_cpu_time(self) -> None:
        previous = {
            "elapsed_seconds": 1.0,
            "worker_rank_cpu_seconds": 2.0,
            "mpi_process_tree_cpu_seconds": 2.5,
        }
        current = {
            "elapsed_seconds": 1.5,
            "worker_rank_cpu_seconds": 3.5,
            "mpi_process_tree_cpu_seconds": 4.5,
            "worker_rank_cpu_core_equivalents": 0.0,
            "mpi_process_tree_cpu_core_equivalents": 0.0,
        }
        _add_cpu_core_equivalents(current, previous)
        self.assertAlmostEqual(current["worker_rank_cpu_core_equivalents"], 3.0)
        self.assertAlmostEqual(current["mpi_process_tree_cpu_core_equivalents"], 4.0)

    def test_cpu_affinity_count_understands_ranges_and_lists(self) -> None:
        self.assertEqual(_cpu_affinity_count("0-3"), 4)
        self.assertEqual(_cpu_affinity_count("0-1,4,6-7"), 5)
        self.assertIsNone(_cpu_affinity_count("3-1"))
        self.assertIsNone(_cpu_affinity_count("not-a-cpu-list"))

    def test_selected_candidate_record_contract(self) -> None:
        records = (
            "h5_mpi2_candidate.json",
            "h3_mpi2_candidate.json",
        )
        root = (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "cases"
            / "050_stage4_direct_memory_forensics"
            / "records"
        )
        required = {
            "benchmark_id",
            "status",
            "metadata",
            "physical_model",
            "resolved_config",
            "dimensions",
            "matrix_inventory",
            "factor_inventory",
            "memory_checkpoints",
            "memory",
            "timings_seconds",
            "qualification",
            "limitations",
        }
        for name in records:
            with self.subTest(record=name):
                record = json.loads((root / name).read_text(encoding="utf-8"))
                self.assertTrue(required.issubset(record))
                self.assertEqual(record["status"], "pass")
                self.assertFalse(record["metadata"]["tracked_source_dirty"])
                self.assertTrue(record["qualification"]["full_solve"])
                self.assertEqual(record["qualification"]["numeric_gate"], "pass")
        h5 = json.loads((root / records[0]).read_text(encoding="utf-8"))
        h3 = json.loads((root / records[1]).read_text(encoding="utf-8"))
        self.assertEqual(
            h5["qualification"]["memory_reduction_20pct_gate"], "pass"
        )
        self.assertEqual(
            h3["qualification"]["memory_reduction_20pct_gate"], "failed"
        )

    def test_task29_required_outcomes_contract(self) -> None:
        root = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "task029_stage4_direct_memory_forensics"
            / "outcomes"
        )
        required = (
            "README.md",
            "summary.md",
            "parameters.json",
            "environment.json",
            "changed_files.md",
            "run_log.txt",
            "test_summary.md",
            "gate_decision.csv",
            "merge_recommendation.md",
            "next_decision.md",
            "baseline_memory_timeline.csv",
            "baseline_matrix_inventory.csv",
            "baseline_factorization_summary.csv",
            "rank_scaling.csv",
            "optimization_hypotheses.csv",
            "optimization_manifest.csv",
            "candidate_comparison.csv",
            "object_lifecycle.md",
            "h2_memory_prediction.md",
            "h2_launch_decision.md",
            "comsol_reference_comparability.md",
        )
        for name in required:
            with self.subTest(outcome=name):
                self.assertTrue((root / name).is_file())
        for name in ("parameters.json", "environment.json"):
            json.loads((root / name).read_text(encoding="utf-8"))
        for name in (
            "gate_decision.csv",
            "optimization_hypotheses.csv",
            "optimization_manifest.csv",
            "candidate_comparison.csv",
        ):
            with (root / name).open(encoding="utf-8", newline="") as stream:
                self.assertGreater(len(list(csv.DictReader(stream))), 0)

    def test_numeric_gate_uses_task28_reference(self) -> None:
        reference = {
            "R_total": 0.1,
            "T_total": 0.4,
            "A_volume_total": 0.5,
        }
        summary = {
            **reference,
            "linear_system_relative_residual": 1.0e-12,
            "energy_closure_error_port_volume": 2.0e-12,
        }
        gate = _numeric_gate(summary, reference, 0)
        self.assertEqual(gate["status"], "pass")
        summary["T_total"] = 0.4001
        self.assertEqual(_numeric_gate(summary, reference, 0)["status"], "failed")

    def test_host_clean_sha_attestation_must_match_mounted_head(self) -> None:
        sha = "a" * 40
        args = _parse_args(["--h-nm", "5", "--verified-clean-sha", sha])
        with patch("benchmarks.run_direct_memory_forensics._git", return_value=sha):
            provenance = _source_provenance(args)
        self.assertFalse(provenance["tracked_source_dirty"])
        self.assertEqual(
            provenance["tracked_source_verification"],
            "host_git_clean_attestation",
        )

        args.verified_clean_sha = "b" * 40
        with patch("benchmarks.run_direct_memory_forensics._git", return_value=sha):
            with self.assertRaises(SystemExit):
                _source_provenance(args)

    def test_h2_is_blocked_without_passing_gate_record(self) -> None:
        args = _parse_args(["--h-nm", "2"])
        with self.assertRaises(SystemExit):
            _validate_h2_gate(args)

    def test_h2_gate_requires_every_safety_field(self) -> None:
        required = {
            "h5_numeric_pass": True,
            "h3_numeric_pass": True,
            "h5_memory_reduction_20pct": True,
            "h3_memory_reduction_20pct": True,
            "h3_no_swap": True,
            "prediction_upper_le_13p5_gb": True,
            "current_memory_margin_pass": True,
            "single_qualified_profile": True,
            "watchdog_enabled": True,
            "task28_h2_record_untouched": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.json"
            path.write_text(json.dumps(required), encoding="utf-8")
            args = _parse_args(["--h-nm", "2", "--h2-gate-json", str(path)])
            _validate_h2_gate(args)
            required["h3_no_swap"] = False
            path.write_text(json.dumps(required), encoding="utf-8")
            with self.assertRaises(SystemExit):
                _validate_h2_gate(args)

    def test_two_point_power_law_memory_prediction(self) -> None:
        result = _two_point_power_law_prediction(1.0, 10.0, 2.0, 20.0, 4.0)
        self.assertAlmostEqual(result["exponent"], 1.0)
        self.assertAlmostEqual(result["prediction"], 40.0)
        with self.assertRaises(ValueError):
            _two_point_power_law_prediction(1.0, 10.0, 1.0, 20.0, 4.0)


if __name__ == "__main__":
    unittest.main()
