from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.solvers.local_slab_solver import (
    CallableLocalSlabSolver,
    LocalCsrOperator,
    relative_local_residual,
)
from src.solvers.neural_local_pc import (
    CHECKPOINT_SCHEMA,
    FrozenNumpyMlp,
    IluNeuralCorrectionSlabSolver,
    NeuralLocalSlabSolver,
    pack_complex,
    sha256_file,
    unpack_complex,
)


def _diagonal_operator(diagonal: np.ndarray) -> LocalCsrOperator:
    diagonal = np.asarray(diagonal, dtype=np.complex128)
    return LocalCsrOperator(
        shape=(diagonal.size, diagonal.size),
        indptr=np.arange(diagonal.size + 1, dtype=np.int64),
        indices=np.arange(diagonal.size, dtype=np.int64),
        values=diagonal,
        metadata={"slab_id": 0},
    )


class _FakeModel:
    def __init__(self, operator: LocalCsrOperator, action):
        self.operator_fingerprint = operator.fingerprint
        self.packed_size = 2 * operator.shape[1]
        self.storage_bytes = 0
        self.checkpoint_sha256 = "fixture"
        self._action = action

    def predict(self, rhs: np.ndarray) -> np.ndarray:
        return np.asarray(self._action(rhs), dtype=np.complex128)


class NeuralLocalPcTests(unittest.TestCase):
    def test_complex_pack_round_trip(self) -> None:
        values = np.asarray([1.0 + 2.0j, -3.0 + 0.25j, 0.0 - 4.0j])
        np.testing.assert_array_equal(unpack_complex(pack_complex(values)), values)

    def test_complex_sparse_action_and_residual(self) -> None:
        operator = _diagonal_operator(np.asarray([2.0 + 0.1j, 3.0 - 0.2j]))
        correction = np.asarray([1.0 - 0.5j, -0.2 + 0.7j])
        rhs = np.asarray([2.0 + 0.1j, 3.0 - 0.2j]) * correction
        np.testing.assert_allclose(operator.action(correction), rhs)
        self.assertLess(relative_local_residual(operator, rhs, correction), 1.0e-14)

    def test_deterministic_inference_and_fail_closed_without_fallback(self) -> None:
        operator = _diagonal_operator(np.asarray([2.0 + 0.1j, 3.0 - 0.2j]))
        exact = _FakeModel(operator, lambda rhs: rhs / operator.values)
        solver = NeuralLocalSlabSolver(operator, exact, residual_ratio_limit=1.0e-12)
        rhs = np.asarray([1.0 + 0.5j, -0.25 + 0.1j])
        first = np.empty_like(rhs)
        repeated = np.empty_like(rhs)
        solver.solve(rhs, first)
        solver.solve(rhs, repeated)
        np.testing.assert_array_equal(first, repeated)
        self.assertEqual(solver.diagnostics["fallback_count"], 0)
        solver.destroy()

        invalid = _FakeModel(operator, lambda rhs: np.full_like(rhs, np.nan))
        fail_closed = NeuralLocalSlabSolver(operator, invalid)
        with self.assertRaisesRegex(RuntimeError, "no fallback"):
            fail_closed.solve(rhs, np.empty_like(rhs))

    def test_bad_local_residual_uses_explicit_fallback(self) -> None:
        operator = _diagonal_operator(np.asarray([2.0 + 0.1j, 3.0 - 0.2j]))
        bad = _FakeModel(operator, lambda rhs: np.zeros_like(rhs))
        fallback = CallableLocalSlabSolver(
            2, lambda rhs: rhs / operator.values, identity="fixture_ilu"
        )
        solver = NeuralLocalSlabSolver(
            operator, bad, fallback=fallback, residual_ratio_limit=0.95
        )
        rhs = np.asarray([1.0 + 0.5j, -0.25 + 0.1j])
        out = np.empty_like(rhs)
        solver.solve(rhs, out)
        np.testing.assert_allclose(out, rhs / operator.values)
        self.assertEqual(solver.diagnostics["fallback_count"], 1)

    def test_ilu_neural_correction_never_degrades_controlled_fixture(self) -> None:
        operator = _diagonal_operator(np.asarray([2.0 + 0.1j, 3.0 - 0.2j]))
        rhs = np.asarray([1.0 + 0.5j, -0.25 + 0.1j])
        ilu = CallableLocalSlabSolver(2, lambda value: 0.4 * value / operator.values, identity="ilu")
        exact_residual_correction = _FakeModel(
            operator, lambda residual: residual / operator.values
        )
        solver = IluNeuralCorrectionSlabSolver(
            operator, exact_residual_correction, ilu, residual_ratio_limit=1.0e-12
        )
        out = np.empty_like(rhs)
        solver.solve(rhs, out)
        self.assertLess(relative_local_residual(operator, rhs, out), 1.0e-13)
        self.assertEqual(solver.diagnostics["fallback_count"], 0)

        degraded_ilu = CallableLocalSlabSolver(
            2, lambda value: 0.4 * value / operator.values, identity="ilu"
        )
        bad = _FakeModel(operator, lambda residual: -residual / operator.values)
        protected = IluNeuralCorrectionSlabSolver(operator, bad, degraded_ilu)
        protected_out = np.empty_like(rhs)
        protected.solve(rhs, protected_out)
        baseline = 0.4 * rhs / operator.values
        np.testing.assert_allclose(protected_out, baseline)
        self.assertEqual(protected.diagnostics["fallback_count"], 1)

    def test_checkpoint_missing_corrupt_and_checksum_mismatch_fail_closed(self) -> None:
        operator = _diagonal_operator(np.asarray([2.0 + 0.1j, 3.0 - 0.2j]))
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            with self.assertRaises(FileNotFoundError):
                FrozenNumpyMlp.load(directory)
            arrays = {
                "input_basis": np.eye(4),
                "output_basis": np.eye(4),
                "weight_1": np.eye(4),
                "bias_1": np.zeros(4),
                "weight_2": np.eye(4),
                "bias_2": np.zeros(4),
            }
            np.savez_compressed(directory / "weights.npz", **arrays)
            manifest = {
                "schema": CHECKPOINT_SCHEMA,
                "operator_fingerprint": operator.fingerprint,
                "weights_sha256": "wrong",
            }
            (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                FrozenNumpyMlp.load(directory)
            manifest["weights_sha256"] = sha256_file(directory / "weights.npz")
            (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            loaded = FrozenNumpyMlp.load(
                directory, expected_operator_fingerprint=operator.fingerprint
            )
            self.assertEqual(loaded.operator_fingerprint, operator.fingerprint)
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                FrozenNumpyMlp.load(directory, expected_operator_fingerprint="bad")


if __name__ == "__main__":
    unittest.main()
