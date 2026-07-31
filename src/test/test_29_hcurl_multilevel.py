from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import numpy as np

from benchmarks import run_workstation_iterative
import src.solvers as ordinary_solvers
import src.solvers.hcurl_multilevel as hcurl_multilevel
from src.solvers.hcurl_multilevel import (
    CanonicalScreenBaseline,
    ModalWoodburyPc,
    NonmatchingTransfer,
    _apply_solver_action,
    build_active_dof_map,
    build_condensed_galerkin_coarse,
    build_nonmatching_active_transfer,
    classify_screen_candidate,
    load_canonical_screen_baseline,
    load_nonmatching_transfer_cache,
    save_nonmatching_transfer_cache,
    validate_transfer_action_against_interpolation,
)
from src.solvers.condensed_dtn import gather_small_petsc_matrix


class TestTask030ResearchApiBoundary(unittest.TestCase):
    def test_only_validated_infrastructure_is_public(self) -> None:
        self.assertEqual(
            tuple(hcurl_multilevel.__all__),
            hcurl_multilevel.VALIDATED_INFRASTRUCTURE_API,
        )
        for name in hcurl_multilevel.RESEARCH_ONLY_CANDIDATE_API:
            self.assertNotIn(name, hcurl_multilevel.__all__)

    def test_ordinary_solver_package_exports_no_failed_candidate(self) -> None:
        for name in hcurl_multilevel.RESEARCH_ONLY_CANDIDATE_API:
            self.assertFalse(hasattr(ordinary_solvers, name), name)


class TestTask030CleanSourceMetadata(unittest.TestCase):
    SHA = "a" * 40

    @classmethod
    def _git_output(cls, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return cls.SHA
        if args == ("branch", "--show-current"):
            return "codex/task030"
        if args in (
            ("status", "--short"),
            ("status", "--short", "--untracked-files=all"),
        ):
            return ""
        raise AssertionError(args)

    def test_start_capture_uses_complete_git_status_without_exclusions(self) -> None:
        calls: list[tuple[str, ...]] = []

        def git_output(*args: str) -> str:
            calls.append(args)
            return self._git_output(*args)

        with mock.patch.object(
            run_workstation_iterative,
            "_git_output",
            side_effect=git_output,
        ):
            metadata = run_workstation_iterative._runtime_metadata_rank0("command")
        self.assertTrue(metadata["source_capture_ok"])
        self.assertEqual(metadata["git_status_scope"], "full_repository")
        self.assertEqual(metadata["git_status_excluded_runner_owned_paths"], [])
        self.assertTrue(metadata["runner_owned_path_capture_ok"])
        self.assertEqual(
            metadata["tracked_source_verification"],
            "local_git_status",
        )
        self.assertIn(("status", "--short"), calls)
        self.assertIn(
            ("status", "--short", "--untracked-files=all"),
            calls,
        )
        self.assertFalse(
            any(
                argument.startswith(":(top,literal,exclude)")
                for call in calls
                for argument in call
            )
        )

    def test_end_capture_excludes_only_exact_runner_owned_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args: str) -> None:
                subprocess.run(
                    ["git", *args],
                    cwd=root,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.name", "Task036 Test")
            git("config", "user.email", "task036@example.invalid")
            records = root / "benchmarks" / "records"
            records.mkdir(parents=True)
            (root / "src").mkdir()
            record = records / "run [owned] #1.json"
            parameters = records / "run [owned] #1_parameters?.json"
            progress = records / "run [owned] #1_progress*.json"
            memory_stage = records / "run [owned] #1_memory stages!.jsonl"
            record.write_text("baseline record\n", encoding="utf-8")
            parameters.write_text("baseline parameters\n", encoding="utf-8")
            git("add", "--", ".")
            git("commit", "-q", "-m", "baseline")
            owned_paths = (record, parameters, progress, memory_stage)

            with (
                mock.patch.object(
                    run_workstation_iterative,
                    "REPOSITORY_ROOT",
                    root,
                ),
                mock.patch.dict(os.environ, {}, clear=False),
            ):
                for name in (
                    "BENCHMARK_GIT_DIRTY",
                    "BENCHMARK_COMMIT_SHA",
                    "BENCHMARK_VERIFIED_CLEAN_SHA",
                ):
                    os.environ.pop(name, None)
                start = run_workstation_iterative._runtime_metadata_rank0(
                    "command"
                )
                self.assertFalse(start["git_dirty"])
                self.assertFalse(start["tracked_source_dirty"])

                record.write_text("runner record\n", encoding="utf-8")
                parameters.write_text("runner parameters\n", encoding="utf-8")
                progress.write_text("runner progress\n", encoding="utf-8")
                memory_stage.write_text("runner stage\n", encoding="utf-8")

                dirty_start = run_workstation_iterative._runtime_metadata_rank0(
                    "command"
                )
                self.assertTrue(dirty_start["git_dirty"])
                self.assertTrue(dirty_start["tracked_source_dirty"])

                owned_only_end = (
                    run_workstation_iterative._runtime_metadata_rank0(
                        "command",
                        runner_owned_paths=owned_paths,
                    )
                )
                self.assertFalse(owned_only_end["git_dirty"])
                self.assertFalse(owned_only_end["tracked_source_dirty"])
                self.assertEqual(
                    owned_only_end["git_status_scope"],
                    "repository_except_exact_runner_outputs",
                )
                self.assertEqual(
                    owned_only_end["git_status_excluded_runner_owned_paths"],
                    [
                        path.relative_to(root).as_posix()
                        for path in owned_paths
                    ],
                )
                self.assertTrue(
                    run_workstation_iterative._source_identity_stable(
                        start,
                        owned_only_end,
                    )
                )
                self.assertFalse(
                    run_workstation_iterative._source_identity_stable(
                        dirty_start,
                        owned_only_end,
                    )
                )

                (root / "src" / "other.py").write_text(
                    "unrelated = True\n",
                    encoding="utf-8",
                )
                unrelated_end = (
                    run_workstation_iterative._runtime_metadata_rank0(
                        "command",
                        runner_owned_paths=owned_paths,
                    )
                )
                self.assertTrue(unrelated_end["git_dirty"])
                self.assertTrue(unrelated_end["tracked_source_dirty"])
                self.assertFalse(
                    run_workstation_iterative._source_identity_stable(
                        start,
                        unrelated_end,
                    )
                )

    def test_owned_path_resolution_failure_is_recorded_fail_closed(self) -> None:
        with (
            mock.patch.object(
                run_workstation_iterative,
                "_git_output",
                side_effect=self._git_output,
            ),
            mock.patch.object(
                Path,
                "resolve",
                side_effect=OSError("owned path unavailable"),
            ),
        ):
            metadata = run_workstation_iterative._runtime_metadata_rank0(
                "command",
                runner_owned_paths=(Path("owned output.json"),),
            )
        self.assertFalse(metadata["source_capture_ok"])
        self.assertFalse(metadata["runner_owned_path_capture_ok"])
        self.assertEqual(metadata["git_status_scope"], "full_repository")
        self.assertEqual(metadata["git_status_excluded_runner_owned_paths"], [])
        self.assertEqual(
            metadata["provenance"],
            "runtime_git_capture_unqualified",
        )

    def test_full_sha_attestation_records_measured_clean_source(self) -> None:
        with (
            mock.patch.dict(
                run_workstation_iterative.os.environ,
                {"BENCHMARK_VERIFIED_CLEAN_SHA": self.SHA},
                clear=True,
            ),
            mock.patch.object(
                run_workstation_iterative,
                "_git_output",
                side_effect=self._git_output,
            ),
        ):
            metadata = run_workstation_iterative._runtime_metadata("command")
        self.assertTrue(metadata["source_capture_ok"])
        self.assertFalse(metadata["git_dirty"])
        self.assertFalse(metadata["tracked_source_dirty"])
        self.assertEqual(
            metadata["tracked_source_verification"],
            "host_git_clean_attestation",
        )
        self.assertEqual(metadata["verified_clean_sha"], self.SHA)
        self.assertTrue(metadata["verified_clean_sha_match"])
        self.assertEqual(metadata["provenance"], "clean_rerun")
        self.assertEqual(metadata["environment_identity"]["petsc_scalar_type"], "complex128")
        self.assertEqual(
            metadata["container_image"],
            metadata["environment_identity"]["container_image"],
        )

    def test_sha_attestation_mismatch_is_recorded_without_losing_evidence(self) -> None:
        with (
            mock.patch.dict(
                run_workstation_iterative.os.environ,
                {"BENCHMARK_VERIFIED_CLEAN_SHA": "b" * 40},
                clear=True,
            ),
            mock.patch.object(
                run_workstation_iterative,
                "_git_output",
                side_effect=self._git_output,
            ),
        ):
            metadata = run_workstation_iterative._runtime_metadata("command")
        self.assertFalse(metadata["verified_clean_sha_match"])
        self.assertEqual(metadata["provenance"], "runtime_git_capture_unqualified")
        self.assertFalse(
            run_workstation_iterative._source_identity_stable(
                metadata, metadata
            )
        )

    def test_dirty_source_and_head_drift_fail_stability(self) -> None:
        start = {
            "commit_sha": self.SHA,
            "source_capture_ok": True,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "claimed_commit_match": True,
            "verified_clean_sha_match": True,
            "environment_identity": {"environment": "A"},
        }
        self.assertTrue(
            run_workstation_iterative._source_identity_stable(start, dict(start))
        )
        self.assertFalse(
            run_workstation_iterative._source_identity_stable(
                start, {**start, "commit_sha": "b" * 40}
            )
        )
        self.assertFalse(
            run_workstation_iterative._source_identity_stable(
                start, {**start, "tracked_source_dirty": True}
            )
        )
        self.assertFalse(
            run_workstation_iterative._source_identity_stable(
                start,
                {**start, "environment_identity": {"environment": "B"}},
            )
        )

    def test_input_hash_is_canonical_and_sensitive(self) -> None:
        first = run_workstation_iterative._input_config_sha256({"b": 2, "a": 1})
        second = run_workstation_iterative._input_config_sha256({"a": 1, "b": 2})
        changed = run_workstation_iterative._input_config_sha256({"a": 1, "b": 3})
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_end_state_rewrites_provenance_and_binds_input(self) -> None:
        start = {
            "commit_sha": self.SHA,
            "source_capture_ok": True,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "claimed_commit_match": True,
            "verified_clean_sha_match": True,
            "environment_identity": {"environment": "A"},
        }
        clean = run_workstation_iterative._final_runtime_identity_metadata(
            source_at_start=start,
            source_at_end=dict(start),
            input_config_sha256_at_start="input-a",
            input_config_sha256_at_end="input-a",
        )
        self.assertEqual(clean["provenance"], "clean_rerun")
        self.assertTrue(clean["source_qualified_for_formal"])

        dirty_end = run_workstation_iterative._final_runtime_identity_metadata(
            source_at_start=start,
            source_at_end={**start, "tracked_source_dirty": True},
            input_config_sha256_at_start="input-a",
            input_config_sha256_at_end="input-a",
        )
        self.assertEqual(
            dirty_end["provenance"], "runtime_git_capture_unqualified"
        )
        self.assertFalse(dirty_end["source_qualified_for_formal"])

        input_drift = run_workstation_iterative._final_runtime_identity_metadata(
            source_at_start=start,
            source_at_end=dict(start),
            input_config_sha256_at_start="input-a",
            input_config_sha256_at_end="input-b",
        )
        self.assertTrue(input_drift["source_identity_stable"])
        self.assertFalse(input_drift["input_config_stable"])
        self.assertFalse(input_drift["source_qualified_for_formal"])

    def test_start_attestation_mismatch_stops_before_assembly(self) -> None:
        from argparse import Namespace

        mismatch = {
            "source_capture_ok": True,
            "verified_clean_sha_valid": True,
            "verified_clean_sha_match": False,
            "claimed_commit_match": True,
            "tracked_source_dirty": False,
        }
        with (
            mock.patch.object(
                run_workstation_iterative,
                "_runtime_metadata",
                return_value=mismatch,
            ),
            mock.patch.object(
                run_workstation_iterative,
                "assemble_target_stage4_system",
            ) as assemble,
            self.assertRaisesRegex(RuntimeError, "does not match mounted HEAD"),
        ):
            run_workstation_iterative.run(Namespace(exact_command="worker"))
        assemble.assert_not_called()

        dirty = {
            **mismatch,
            "verified_clean_sha_match": True,
            "tracked_source_dirty": True,
        }
        run_workstation_iterative._workstation_source_preflight(dirty)

    def test_nonroot_receives_source_snapshot_without_git_capture(self) -> None:
        expected = {"commit_sha": self.SHA, "tracked_source_dirty": False}

        class NonRootComm:
            rank = 1

            @staticmethod
            def bcast(payload, root=0):
                assert root == 0
                assert payload is None
                return expected

        with mock.patch.object(
            run_workstation_iterative,
            "_runtime_metadata_rank0",
            side_effect=AssertionError("non-root must not query Git"),
        ):
            received = run_workstation_iterative._runtime_metadata(
                "command", comm=NonRootComm()
            )
        self.assertEqual(received, expected)


class TestWorkstationMemoryStageClaim(unittest.TestCase):
    def test_claim_is_exclusive_and_preserves_existing(self) -> None:
        from mpi4py import MPI

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "records"
            owner = output_dir / "record.json"
            stage = output_dir / "record_memory_stages.jsonl"
            run_workstation_iterative._claim_memory_stage_file(
                MPI.COMM_SELF,
                stage,
                owner_path=owner,
            )
            self.assertEqual(stage.read_bytes(), b"")

            sentinel = b'{"stage":"preserved"}\n'
            with stage.open("ab") as stream:
                stream.write(sentinel)
            with self.assertRaisesRegex(RuntimeError, "FileExistsError"):
                run_workstation_iterative._claim_memory_stage_file(
                    MPI.COMM_SELF,
                    stage,
                    owner_path=owner,
                )
            self.assertEqual(stage.read_bytes(), sentinel)

            with self.assertRaisesRegex(RuntimeError, "must differ"):
                run_workstation_iterative._claim_memory_stage_file(
                    MPI.COMM_SELF,
                    owner,
                    owner_path=owner,
                )
            external_stage = root / "other" / "memory_stages.jsonl"
            run_workstation_iterative._claim_memory_stage_file(
                MPI.COMM_SELF,
                external_stage,
                owner_path=owner,
            )
            self.assertEqual(external_stage.read_bytes(), b"")
            run_workstation_iterative._claim_memory_stage_file(
                MPI.COMM_SELF,
                None,
                owner_path=owner,
            )


class TestTask030WorkstationFormalQualification(unittest.TestCase):
    GOOD_RTA = {
        "R_total": 0.1,
        "T_total": 0.6,
        "A_volume_total": 0.3,
        "energy_closure_error": 0.0,
    }

    def _qualify(self, **changes):
        inputs = {
            "qualified_profile": True,
            "ksp_reason": 2,
            "condensed_true_residual": 1.0e-8,
            "full_augmented_true_residual": 1.0e-8,
            "rta_candidate": self.GOOD_RTA,
            "source_clean": True,
        }
        inputs.update(changes)
        return run_workstation_iterative._workstation_formal_qualification(**inputs)

    def test_each_solver_and_rta_gate_fails_closed(self) -> None:
        failures = {
            "ksp_reason": {"ksp_reason": -3},
            "condensed_residual": {"condensed_true_residual": 1.05e-6},
            "full_residual": {"full_augmented_true_residual": 1.05e-6},
            "rta_missing": {"rta_candidate": None},
            "energy_closure": {
                "rta_candidate": {
                    **self.GOOD_RTA,
                    "energy_closure_error": 1.05e-6,
                }
            },
        }
        for name, changes in failures.items():
            with self.subTest(name=name):
                result = self._qualify(**changes)
                self.assertFalse(result["formal_pass"])
                self.assertEqual(
                    run_workstation_iterative._workstation_exit_code(result), 2
                )

    def test_positive_case_is_formal_and_uses_frozen_energy_limit(self) -> None:
        result = self._qualify()
        self.assertEqual(result["status"], "formal_pass")
        self.assertTrue(result["formal_pass"])
        self.assertEqual(run_workstation_iterative._workstation_exit_code(result), 0)
        self.assertEqual(
            run_workstation_iterative.FORMAL_ENERGY_CLOSURE_LIMIT,
            1.0e-6,
        )
        self.assertEqual(
            run_workstation_iterative.FORMAL_TRUE_RESIDUAL_LIMIT,
            1.0e-6,
        )

    def test_source_failure_preserves_numeric_and_physics_results(self) -> None:
        result = self._qualify(source_clean=False)
        self.assertEqual(result["status"], "controlled_negative_source_identity")
        self.assertTrue(result["numeric_solver_pass"])
        self.assertTrue(result["physics_pass"])
        self.assertFalse(result["formal_pass"])


class _FakeComm:
    rank = 0

    @staticmethod
    def allgather(value):
        return [value]


class _FakeIndexMap:
    size_local = 5
    size_global = 5
    local_range = (0, 5)


class _FakeDofMap:
    index_map = _FakeIndexMap()
    index_map_bs = 1


class _FakeMesh:
    comm = _FakeComm()


class _FakeSpace:
    dofmap = _FakeDofMap()
    mesh = _FakeMesh()


class TestTask030SolverActionAdapter(unittest.TestCase):
    def test_accepts_solve_and_python_pc_contexts(self):
        calls = []

        class SolveStyle:
            def solve(self, source, target):
                calls.append(("solve", source, target))

        class ApplyStyle:
            def apply(self, pc, source, target):
                calls.append(("apply", pc, source, target))

        _apply_solver_action(SolveStyle(), "s1", "t1")
        _apply_solver_action(ApplyStyle(), "s2", "t2")
        self.assertEqual(calls[0], ("solve", "s1", "t1"))
        self.assertEqual(calls[1], ("apply", None, "s2", "t2"))


class TestTask030Baseline(unittest.TestCase):
    def test_pinned_record_and_iteration_are_read_from_canonical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = root / "record.json"
            record = {
                "history": [{"iteration": 100, "true_relative_residual": 0.25}],
                "final_peak_total_gb": 2.0,
                "full_augmented_true_residual": 1.0e-7,
                "iterations": 321,
            }
            record_path.write_text(json.dumps(record), encoding="utf-8")
            digest = hashlib.sha256(record_path.read_bytes()).hexdigest()
            reference = root / "reference.json"
            reference.write_text(
                json.dumps({"canonical_record": "record.json", "sha256": digest}),
                encoding="utf-8",
            )
            result = load_canonical_screen_baseline(reference, repository_root=root)
            self.assertEqual(result.iteration, 100)
            self.assertEqual(result.true_relative_residual, 0.25)
            self.assertEqual(result.total_iterations, 321)

    def test_hash_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "record.json").write_text("{}", encoding="utf-8")
            reference = root / "reference.json"
            reference.write_text(
                json.dumps({"canonical_record": "record.json", "sha256": "0" * 64}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                load_canonical_screen_baseline(reference, repository_root=root)

    def test_screen_classification_uses_ratios(self):
        baseline = CanonicalScreenBaseline(
            reference_path=Path("reference"),
            canonical_path=Path("record"),
            sha256="0" * 64,
            iteration=100,
            true_relative_residual=1.0,
            peak_rss_gb=2.0,
            full_true_relative_residual=1.0e-6,
            total_iterations=1000,
        )
        strong = classify_screen_candidate(
            true_residual=0.49, peak_rss_gb=2.1, baseline=baseline
        )
        memory = classify_screen_candidate(
            true_residual=1.05, peak_rss_gb=1.3, baseline=baseline
        )
        negative = classify_screen_candidate(
            true_residual=1.3, peak_rss_gb=2.0, baseline=baseline
        )
        self.assertEqual(strong["classification"], "strong_positive")
        self.assertEqual(memory["classification"], "memory_positive")
        self.assertEqual(negative["classification"], "negative")


class TestTask030ActiveDofs(unittest.TestCase):
    def test_owned_slaves_are_removed_and_ghost_slave_is_ignored(self):
        mapping = build_active_dof_map(
            _FakeSpace(), np.asarray([1, 4, 7], dtype=np.int32)
        )
        np.testing.assert_array_equal(mapping.local_full_dofs, [0, 2, 3])
        np.testing.assert_array_equal(mapping.local_active_ids, [0, 1, 2])
        np.testing.assert_array_equal(mapping.active_to_full_global, [0, 2, 3])
        self.assertEqual(mapping.global_active_size, 3)


class TestTask030NonmatchingTransfer(unittest.TestCase):
    def test_hexa_n1curl_action_and_adjoint(self):
        from basix.ufl import element
        from dolfinx import fem, mesh
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        fine_mesh = mesh.create_box(
            comm,
            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
            [2, 2, 2],
            cell_type=mesh.CellType.hexahedron,
        )
        coarse_mesh = mesh.create_box(
            comm,
            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
            [1, 1, max(2, comm.size)],
            cell_type=mesh.CellType.hexahedron,
        )
        fine_space = fem.functionspace(fine_mesh, element("N1curl", "hexahedron", 2))
        coarse_space = fem.functionspace(
            coarse_mesh, element("N1curl", "hexahedron", 1)
        )
        no_slaves = np.empty(0, dtype=np.int32)
        transfer = build_nonmatching_active_transfer(
            fine_space=fine_space,
            coarse_space=coarse_space,
            fine_local_slave_dofs=no_slaves,
            coarse_local_slave_dofs=no_slaves,
        )
        action_error = validate_transfer_action_against_interpolation(
            transfer,
            fine_space=fine_space,
            coarse_space=coarse_space,
            fine_local_slave_dofs=no_slaves,
        )
        self.assertLessEqual(
            transfer.validation["adjoint_identity_relative_error"], 1.0e-12
        )
        self.assertLessEqual(action_error, 1.0e-12)
        self.assertGreater(transfer.validation["matrix_nnz"], 0)
        transfer.destroy()

    def test_cached_rows_redistribute_to_current_fine_ownership(self):
        import shutil

        from basix.ufl import element
        from dolfinx import fem, mesh
        from mpi4py import MPI
        from petsc4py import PETSc

        comm = MPI.COMM_WORLD
        coarse_mesh = mesh.create_box(
            comm,
            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
            [1, 1, max(1, comm.size)],
            cell_type=mesh.CellType.hexahedron,
        )
        coarse_space = fem.functionspace(
            coarse_mesh, element("N1curl", "hexahedron", 1)
        )
        no_slaves = np.empty(0, dtype=np.int32)
        active = build_active_dof_map(coarse_space, no_slaves)
        saved_counts = tuple(rank + 1 for rank in range(comm.size))
        target_counts = tuple(reversed(saved_counts))
        global_rows = sum(saved_counts)
        saved_local_rows = saved_counts[comm.rank]
        matrix = PETSc.Mat().createAIJ(
            size=(
                (saved_local_rows, global_rows),
                (active.local_active_size, active.global_active_size),
            ),
            nnz=1,
            comm=comm,
        )
        row_start = sum(saved_counts[: comm.rank])
        for local_row in range(saved_local_rows):
            row = row_start + local_row
            matrix.setValue(
                row,
                row % active.global_active_size,
                PETSc.ScalarType(row + 1),
            )
        matrix.assemble()
        expected = gather_small_petsc_matrix(matrix)
        transfer = NonmatchingTransfer(
            matrix=matrix,
            active_map=active,
            validation={"status": "passed"},
            owners=(),
        )
        directory = comm.bcast(
            tempfile.mkdtemp(prefix="task030_transfer_cache_")
            if comm.rank == 0
            else None,
            root=0,
        )
        try:
            save_nonmatching_transfer_cache(transfer, Path(directory))
            loaded = load_nonmatching_transfer_cache(
                Path(directory),
                coarse_space=coarse_space,
                coarse_local_slave_dofs=no_slaves,
                expected_fine_global_dofs=global_rows,
                expected_fine_local_dofs=target_counts[comm.rank],
            )
            self.assertEqual(loaded.matrix.getLocalSize()[0], target_counts[comm.rank])
            self.assertEqual(
                loaded.validation["cache_row_redistributed"], comm.size > 1
            )
            np.testing.assert_allclose(
                gather_small_petsc_matrix(loaded.matrix), expected,
                rtol=0.0, atol=0.0,
            )
            loaded.destroy()
        finally:
            transfer.destroy()
            comm.barrier()
            if comm.rank == 0:
                shutil.rmtree(directory)
            comm.barrier()


class TestTask030CondensedGalerkin(unittest.TestCase):
    @staticmethod
    def _distributed_matrix(values):
        from mpi4py import MPI
        from petsc4py import PETSc

        array = np.asarray(values, dtype=PETSc.ScalarType)
        matrix = PETSc.Mat().createAIJ(size=array.shape, comm=MPI.COMM_WORLD)
        matrix.setUp()
        start, end = matrix.getOwnershipRange()
        if end > start:
            rows = np.arange(start, end, dtype=PETSc.IntType)
            cols = np.arange(array.shape[1], dtype=PETSc.IntType)
            matrix.setValues(rows, cols, array[start:end, :])
        matrix.assemble()
        return matrix

    def test_complex_hermitian_condensed_action(self):
        F_values = np.asarray(
            [
                [4 + 1j, 1, 0, 0],
                [0.5j, 3 - 0.2j, 1, 0],
                [0, -1j, 2 + 0.5j, 0.25],
                [0.1, 0, 0.4j, 3],
            ],
            dtype=np.complex128,
        )
        C_values = np.asarray([[1], [0.5j], [0.2], [-0.1j]])
        D_values = np.asarray([[0.25j, 0.5, -0.2j, 0.1]])
        P_values = np.asarray(
            [[1, 0.2j], [0.5, 0], [0.1j, 1], [0, -0.25]],
            dtype=np.complex128,
        )
        F = self._distributed_matrix(F_values)
        C = self._distributed_matrix(C_values)
        D = self._distributed_matrix(D_values)
        H = self._distributed_matrix([[1]])
        P = self._distributed_matrix(P_values)
        coarse = build_condensed_galerkin_coarse(F=F, C=C, D=D, H=H, transfer=P)
        expected = P_values.conjugate().T @ (F_values - C_values @ D_values) @ P_values
        actual = gather_small_petsc_matrix(coarse.matrix)
        np.testing.assert_allclose(actual, expected, rtol=1.0e-13, atol=1.0e-13)
        self.assertTrue(coarse.diagnostics["uses_hermitian_restriction"])
        coarse.destroy()
        for matrix in (P, H, D, C, F):
            matrix.destroy()

    def test_all_mode_woodbury_matches_dense_inverse_and_destroy_is_idempotent(self):
        diagonal = np.asarray([4 + 0.2j, 3 - 0.1j, 2.5 + 0.3j, 5 - 0.4j])
        C_values = np.asarray([[0.4], [0.1j], [-0.2], [0.05j]])
        D_values = np.asarray([[0.3j, -0.2, 0.1j, 0.25]])
        H_values = np.asarray([[1.0]])
        C = self._distributed_matrix(C_values)
        D = self._distributed_matrix(D_values)
        H = self._distributed_matrix(H_values)

        class DiagonalInverse:
            def solve(self, source, target):
                start, end = source.getOwnershipRange()
                target.getArray()[:] = (
                    source.getArray(readonly=True) / diagonal[start:end]
                )

        woodbury = ModalWoodburyPc(base_solver=DiagonalInverse(), C=C, D=D, H=H)
        source = C.createVecLeft()
        start, end = source.getOwnershipRange()
        source_values = np.asarray([1 + 0.1j, -0.3j, 0.4, -0.2 + 0.5j])
        source.getArray()[:] = source_values[start:end]
        target = C.createVecLeft()
        woodbury.solve(source, target)
        expected = np.linalg.solve(
            np.diag(diagonal) - C_values @ D_values, source_values
        )
        np.testing.assert_allclose(
            target.getArray(readonly=True),
            expected[start:end],
            rtol=2e-13,
            atol=2e-13,
        )
        self.assertEqual(woodbury.diagnostics["n_aux"], 1)
        self.assertEqual(woodbury.diagnostics["apply_count"], 1)
        target.destroy()
        source.destroy()
        woodbury.destroy()
        woodbury.destroy()
        for matrix in (H, D, C):
            matrix.destroy()


if __name__ == "__main__":
    unittest.main()
