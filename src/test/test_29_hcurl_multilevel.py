from __future__ import annotations

import hashlib
import json
from pathlib import Path
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
    _apply_solver_action,
    build_active_dof_map,
    build_condensed_galerkin_coarse,
    build_nonmatching_active_transfer,
    classify_screen_candidate,
    load_canonical_screen_baseline,
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
        raise AssertionError(args)

    def test_full_sha_attestation_marks_both_dirty_flags_false(self) -> None:
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
        self.assertFalse(metadata["git_dirty"])
        self.assertFalse(metadata["tracked_source_dirty"])
        self.assertEqual(
            metadata["tracked_source_verification"], "host_git_clean_attestation"
        )
        self.assertEqual(metadata["verified_clean_sha"], self.SHA)

    def test_sha_attestation_must_match_mounted_head(self) -> None:
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
            self.assertRaisesRegex(RuntimeError, "does not match mounted HEAD"),
        ):
            run_workstation_iterative._runtime_metadata("command")


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
        from petsc4py import PETSc

        if PETSc.Sys.getVersion() < (3, 24, 0):
            self.skipTest(
                "PETSc <3.24 cannot MatMatMult a virtual complex Hermitian transpose"
            )
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
