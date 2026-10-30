"""Small exact-tensor cache tests; no FE, MPI, global matrix or solve."""
from __future__ import annotations

import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from src.common.exact_tensor_checkpoint import ExactTensorCheckpoint, canonical_identity


class TestExactTensorCheckpoint(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ExactTensorCheckpoint(self.root / "cache", max_tensor_bytes=4096, disk_reserve_bytes=0)
        self.identity = {"schema": "synthetic-kernel.v1", "tag": 21,
                         "exact_widths_hex": [float(.85).hex(), float(.5).hex(), float(.5).hex()],
                         "form_sha256": "a" * 64, "runtime_sha256": "b" * 64,
                         "quadrature": 15, "translation_invariant": True}
        self.original = np.array([[1+2j, 3-4j], [-5+6j, 7+8j]], dtype="<c16")
        self.calls = 0

    def compute(self):
        self.calls += 1
        return self.original.copy()

    def cold(self):
        return self.store.get_or_compute(self.identity, (2, 2), self.compute)

    def entry(self):
        return self.store.directory / sha256(canonical_identity(self.identity)).hexdigest()

    def test_exact_cold_warm_and_no_second_callback(self):
        cold, receipt = self.cold()
        self.assertFalse(receipt["cache_hit"])
        self.assertEqual(self.calls, 1)
        np.testing.assert_array_equal(cold, self.original)
        before = {p.name: p.read_bytes() for p in self.entry().iterdir()}
        warm, second = self.cold()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(self.calls, 1)
        self.assertEqual(second["compute_seconds"], 0.0)
        np.testing.assert_array_equal(warm, cold)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.entry().iterdir()})
        self.assertEqual(second["tensor"]["payload_sha256"], sha256(memoryview(cold).cast("B")).hexdigest())
        self.assertEqual(set(before), {"manifest.json", "tensor.npy"})
        self.assertTrue(second["independent_original_residual_still_required"])

    def test_scientific_identity_change_is_a_distinct_cold_entry(self):
        self.cold()
        changed = copy.deepcopy(self.identity)
        changed["exact_widths_hex"][0] = float(.85000000000001).hex()
        _array, receipt = self.store.get_or_compute(changed, (2, 2), self.compute)
        self.assertFalse(receipt["cache_hit"])
        self.assertEqual(self.calls, 2)
        self.assertEqual(len(list(self.store.directory.iterdir())), 2)

    def test_manifest_identity_change_rejected_without_recompute(self):
        self.cold()
        p = self.entry() / "manifest.json"
        m = json.loads(p.read_text())
        m["identity"]["quadrature"] = 17
        p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "scientific identity"):
            self.cold()
        self.assertEqual(self.calls, 1)

    def test_payload_corruption_rejected(self):
        self.cold()
        p = self.entry() / "tensor.npy"
        with p.open("r+b") as f:
            f.seek(-1, 2)
            old = f.read(1)
            f.seek(-1, 2)
            f.write(bytes([old[0] ^ 1]))
        with self.assertRaises(ValueError):
            self.cold()
        self.assertEqual(self.calls, 1)

    def test_header_shape_rejected_before_load_allocation(self):
        self.cold()
        with (self.entry() / "tensor.npy").open("wb") as f:
            np.lib.format.write_array(f, np.zeros((1, 4), dtype="<c16"), allow_pickle=False)
        with self.assertRaisesRegex(ValueError, "header/length"):
            self.cold()
        self.assertEqual(self.calls, 1)

    def test_header_dtype_rejected(self):
        self.cold()
        with (self.entry() / "tensor.npy").open("wb") as f:
            np.lib.format.write_array(f, np.zeros((2, 2), dtype=np.float64), allow_pickle=False)
        with self.assertRaisesRegex(ValueError, "header/length"):
            self.cold()

    def test_trailing_payload_rejected(self):
        self.cold()
        with (self.entry() / "tensor.npy").open("ab") as f:
            f.write(b"extra")
        with self.assertRaisesRegex(ValueError, "header/length"):
            self.cold()

    def test_partial_entry_is_not_overwritten(self):
        self.entry().mkdir()
        p = self.entry() / "tensor.npy.building"
        p.write_bytes(b"interrupted")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.cold()
        self.assertEqual(self.calls, 0)
        self.assertEqual(p.read_bytes(), b"interrupted")

    def test_unknown_entry_member_rejected(self):
        self.cold()
        (self.entry() / "unregistered").write_bytes(b"unknown")
        with self.assertRaisesRegex(ValueError, "unknown members"):
            self.cold()

    def test_root_and_entry_symlink_rejected(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "linked"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            ExactTensorCheckpoint(link)
        self.entry().symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.cold()
        self.assertEqual(self.calls, 0)

    def test_tensor_symlink_rejected(self):
        self.cold()
        p = self.entry() / "tensor.npy"
        target = self.root / "tensor_copy.npy"
        target.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(target)
        with self.assertRaises(OSError):
            self.cold()
        self.assertEqual(self.calls, 1)

    def test_fifo_rejected_without_blocking_or_kernel(self):
        self.cold()
        p = self.entry() / "tensor.npy"
        p.unlink()
        os.mkfifo(p)
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.cold()
        self.assertEqual(self.calls, 1)

    def test_bad_producer_arrays_reject_without_entry(self):
        bad_arrays = [np.ones((2, 2), dtype=np.float64), np.ones((2, 3), dtype="<c16"),
                      np.ones((2, 2), dtype="<c16").T,
                      np.array([[np.nan, 1], [2, 3]], dtype="<c16"),
                      np.array([[np.inf, 1], [2, 3]], dtype="<c16")]
        for array in bad_arrays:
            with self.subTest(dtype=array.dtype, shape=array.shape):
                with self.assertRaises((TypeError, ValueError)):
                    self.store.get_or_compute(self.identity, (2, 2), lambda: array)
                self.assertFalse(self.entry().exists())

    def test_shape_budget_before_compute(self):
        for shape in [(True, 2), (0, 2), (1000000, 1000000), (2,), (2.0, 2)]:
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                self.store.get_or_compute(self.identity, shape, self.compute)
        self.assertEqual(self.calls, 0)

    def test_identity_exact_types_and_rejected_unknowns(self):
        self.assertNotEqual(canonical_identity({"x": 1}), canonical_identity({"x": 1.0}))
        self.assertNotEqual(canonical_identity({"x": 1}), canonical_identity({"x": True}))
        self.assertNotEqual(canonical_identity({"x": 0.0}), canonical_identity({"x": -0.0}))
        for bad in [{}, {"x": np.int64(1)}, {"x": float("nan")}, {"x": (1, 2)}, {"x": 1j}]:
            with self.subTest(bad=repr(bad)), self.assertRaises((ValueError, TypeError)):
                self.store.get_or_compute(bad, (2, 2), self.compute)
        self.assertEqual(self.calls, 0)

    def test_callback_identity_mutation_rejected(self):
        def mutate():
            self.identity["tag"] = 22
            return self.original.copy()
        with self.assertRaisesRegex(ValueError, "mutated"):
            self.store.get_or_compute(self.identity, (2, 2), mutate)
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_callback_exception_preserved(self):
        def fail():
            raise ArithmeticError("original compute failure")
        with self.assertRaisesRegex(ArithmeticError, "original compute failure"):
            self.store.get_or_compute(self.identity, (2, 2), fail)
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_disk_admission_before_compute(self):
        class Empty:
            f_bavail = 0
            f_frsize = 4096
        with patch("src.common.exact_tensor_checkpoint.os.statvfs", return_value=Empty()):
            with self.assertRaisesRegex(RuntimeError, "disk reserve admission"):
                self.cold()
        self.assertEqual(self.calls, 0)

    def test_cold_manifest_commit_failure_keeps_partial_not_false_hit(self):
        from src.common import exact_tensor_checkpoint as module
        original = module._publish_no_replace
        def fail_manifest(temporary, final):
            if final.name == "manifest.json":
                raise OSError("controlled manifest commit failure")
            return original(temporary, final)
        with patch.object(module, "_publish_no_replace", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "controlled manifest"):
                self.cold()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.cold()
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
