"""Narrow staged saved-checker contracts; NOT_RUN during source staging.

Tests use synthetic primitive arrays only. They do not import FE, generate the
same80 fixture, perform JIT, or claim physical p6 qualification.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


def checker_module():
    path = Path(__file__).resolve().parents[2] / "benchmarks/check_fresh_c1_p6_component.py"
    spec = importlib.util.spec_from_file_location("fresh_c1_p6_saved_checker_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MetricContracts(unittest.TestCase):
    def test_exact_zero_scale_never_accepts_small_nonzero_error(self):
        checker = checker_module()
        self.assertTrue(checker.metric_record(0., 0., 1.e-12)["passed"])
        for error in (1.e-300, 1.e-15, 1.):
            record = checker.metric_record(error, 0., 1.e-12)
            self.assertFalse(record["passed"])
            self.assertEqual(record["zero_scale_rule"], "error_must_be_exactly_zero")
            json.dumps(record, allow_nan=False)

    def test_positive_scale_uses_relative_bound(self):
        checker = checker_module()
        self.assertTrue(checker.metric_record(1.e-11, 10., 1.e-12)["passed"])
        self.assertFalse(checker.metric_record(1.1e-11, 10., 1.e-12)["passed"])

    def test_zero_scale_vector_gate_detects_norm_underflow(self):
        import numpy as np
        checker = checker_module()
        events = []
        measurements = checker._Measurements(lambda stage, facts: events.append((stage, facts)))
        with self.assertRaisesRegex(ValueError, "metric failed"):
            measurements.compare("tiny_nonzero_zero_scale", np.asarray([1.e-300]), np.zeros(1), scale=0.)
        record = measurements.records["tiny_nonzero_zero_scale"]
        self.assertFalse(record["passed"])
        self.assertTrue(record["nonzero_error_at_zero_scale"])
        json.dumps(events[-1][1], allow_nan=False)

    def test_nonfinite_diagnostics_are_json_safe_failures(self):
        checker = checker_module()
        for error, scale, limit in ((float("nan"), 1., 1.e-12),
                                    (float("inf"), 1., 1.e-12),
                                    (1., float("inf"), 1.e-12),
                                    (1., 1., float("inf"))):
            record = checker.metric_record(error, scale, limit)
            self.assertFalse(record["passed"])
            self.assertFalse(record["finite"])
            json.dumps(record, allow_nan=False)

    def test_wrong_component_inventory_checkpoints_failure(self):
        checker, events, loads = checker_module(), [], []
        report = {"schema": checker.WORKER_SCHEMA, "actual_inventory": {**checker.INVENTORY, "cell_count": 79}}
        with self.assertRaisesRegex(ValueError, "schema/inventory"):
            checker.check_component(report, lambda ref: loads.append(ref),
                allocation_gate=lambda stage, facts: None,
                checkpoint=lambda stage, facts: events.append((stage, facts)))
        self.assertEqual(loads, [])
        self.assertEqual(events[-1][0], "component_checker_failure")
        self.assertFalse(events[-1][1]["independent_component_pass"])
        json.dumps(events[-1][1], allow_nan=False)


class SavedPivotContracts(unittest.TestCase):
    @staticmethod
    def arrays(dimension=450):
        import numpy as np
        diagonal = np.linspace(1., 2., dimension).astype(np.complex128) + .1j
        lu = np.diag(diagonal)
        pivots = np.arange(dimension, dtype=np.int32)
        rhs = np.column_stack((np.cos(np.arange(dimension)) + .2j,
                               np.sin(np.arange(dimension)) - .3j)).astype(np.complex128)
        return lu, pivots, rhs, rhs / diagonal[:, None]

    def test_wrong_108_dimension_rejected_before_native_call(self):
        checker = checker_module()
        lu, pivots, rhs, _ = self.arrays(108)
        with mock.patch("scipy.linalg.lu_solve") as native:
            with self.assertRaisesRegex(ValueError, "450-row"):
                checker.solve_fresh_p6_saved_LU(lu, pivots, rhs,
                    allocation_gate=lambda stage, facts: None, label="wrong_dimension")
            native.assert_not_called()

    def test_wrong_pivot_dtype_never_narrows(self):
        checker = checker_module()
        lu, pivots, rhs, _ = self.arrays()
        with mock.patch("scipy.linalg.lu_solve") as native:
            with self.assertRaisesRegex(ValueError, "int32"):
                checker.solve_fresh_p6_saved_LU(lu, pivots.astype("int64"), rhs,
                    allocation_gate=lambda stage, facts: None, label="wrong_dtype")
            native.assert_not_called()

    def test_invalid_pivot_ranges_rejected_before_native_call(self):
        checker = checker_module()
        for position, invalid in ((0, -1), (100, 99), (0, 450)):
            lu, pivots, rhs, _ = self.arrays()
            pivots[position] = invalid
            with mock.patch("scipy.linalg.lu_solve") as native:
                with self.assertRaisesRegex(ValueError, "GETRF range"):
                    checker.solve_fresh_p6_saved_LU(lu, pivots, rhs,
                        allocation_gate=lambda stage, facts: None, label="invalid_range")
                native.assert_not_called()

    def test_allocation_denial_prevents_native_call(self):
        checker = checker_module()
        lu, pivots, rhs, _ = self.arrays()
        def deny_private(stage, facts):
            if "compact_private_pivots" in stage:
                raise MemoryError("private copy not admitted")
        with mock.patch("scipy.linalg.lu_solve") as native:
            with self.assertRaisesRegex(MemoryError, "not admitted"):
                checker.solve_fresh_p6_saved_LU(lu, pivots, rhs,
                    allocation_gate=deny_private, label="denied")
            native.assert_not_called()

    def test_readonly_mmaps_use_private_writable_pivots_and_preserve_bytes(self):
        import numpy as np
        from scipy.linalg import lu_solve as actual_native
        checker = checker_module()
        lu, pivots, rhs, expected = self.arrays()
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / (name + ".npy") for name in ("lu", "pivots", "rhs")]
            for path, array in zip(paths, (lu, pivots, rhs), strict=True):
                np.save(path, array, allow_pickle=False)
            archived = [np.load(path, mmap_mode="r", allow_pickle=False) for path in paths]
            before = [checker._sha(array, header=False) for array in archived]
            stages, calls = [], []
            def admitted(stage, facts):
                stages.append((stage, facts))
            def inspect_native(factor, values, *, overwrite_b):
                private = factor[1]
                self.assertTrue(private.flags.writeable)
                self.assertEqual(private.dtype, np.dtype("int32"))
                self.assertFalse(np.shares_memory(private, archived[1]))
                self.assertFalse(overwrite_b)
                self.assertTrue(any("compact_private_pivots" in stage for stage, _ in stages))
                calls.append(True)
                return actual_native(factor, values, overwrite_b=overwrite_b)
            with mock.patch("scipy.linalg.lu_solve", side_effect=inspect_native):
                result = checker.solve_fresh_p6_saved_LU(*archived,
                    allocation_gate=admitted, label="readonly_mmaps")
            self.assertEqual(len(calls), 1)
            np.testing.assert_allclose(result, expected, rtol=1.e-12, atol=0.)
            self.assertEqual(before, [checker._sha(array, header=False) for array in archived])
            self.assertTrue(all(not array.flags.writeable for array in archived))
            private_admission = next(facts for stage, facts in stages if "compact_private_pivots" in stage)
            self.assertEqual(private_admission["matrix_payload_bytes"], 450 * 4)
            self.assertTrue(private_admission["immutable_archived_pivots_preserved"])
            self.assertEqual(private_admission["possible_Fortran_LU_copy_bytes"], 450 * 450 * 16)
            self.assertGreaterEqual(private_admission["workspace_bytes"], archived[0].nbytes + archived[2].nbytes)

    def test_nonfinite_rhs_rejected_before_native_call(self):
        checker = checker_module()
        lu, pivots, rhs, _ = self.arrays()
        rhs[0, 0] = float("nan")
        with mock.patch("scipy.linalg.lu_solve") as native:
            with self.assertRaisesRegex(ValueError, "finite"):
                checker.solve_fresh_p6_saved_LU(lu, pivots, rhs,
                    allocation_gate=lambda stage, facts: None, label="nonfinite")
            native.assert_not_called()

    def test_archived_pivot_change_is_detected(self):
        checker = checker_module()
        lu, pivots, rhs, _ = self.arrays()
        def corrupt_archive(factor, values, *, overwrite_b):
            pivots[0] = 1
            return values.copy()
        with mock.patch("scipy.linalg.lu_solve", side_effect=corrupt_archive):
            with self.assertRaisesRegex(ValueError, "changed archived arrays"):
                checker.solve_fresh_p6_saved_LU(lu, pivots, rhs,
                    allocation_gate=lambda stage, facts: None, label="corrupted_archive")


class SavedMemberContracts(unittest.TestCase):
    @staticmethod
    def packet(checker, array):
        reference = {"name": "control", "shape": list(array.shape), "dtype": str(array.dtype),
                     "numeric_bytes": int(array.nbytes), "sha256": checker._sha(array)}
        upper = int(array.nbytes) + 4096
        return {"snapshot": {"members": [reference], "roles": {"control": reference},
                 "unique_member_count": 1, "numeric_bytes": int(array.nbytes),
                 "archive_members_bytes_upper": upper, "archive_payload_limit_bytes": upper}}, reference

    def test_hash_mismatch_and_mutable_archive_rejected(self):
        import numpy as np
        checker = checker_module()
        array = np.asarray([1.+2j], dtype=np.complex128)
        packet, reference = self.packet(checker, array)
        reader = checker._Reader(packet, lambda ref: array, lambda stage, facts: None)
        with self.assertRaisesRegex(ValueError, "immutable"):
            reader.ref(reference)
        array.flags.writeable = False
        corrupt = array.copy()
        corrupt[0] += 1.
        corrupt.flags.writeable = False
        reader = checker._Reader(packet, lambda ref: corrupt, lambda stage, facts: None)
        with self.assertRaisesRegex(ValueError, "hash differs"):
            reader.ref(reference)

    def test_missing_role_and_payload_budget_rejected(self):
        import numpy as np
        checker = checker_module()
        array = np.asarray([1.+2j], dtype=np.complex128)
        array.flags.writeable = False
        packet, _ = self.packet(checker, array)
        reader = checker._Reader(packet, lambda ref: array, lambda stage, facts: None)
        with self.assertRaisesRegex(ValueError, "missing required"):
            reader.role("missing")
        packet["snapshot"]["archive_payload_limit_bytes"] -= 1
        with self.assertRaisesRegex(ValueError, "payload budget"):
            checker._Reader(packet, lambda ref: array, lambda stage, facts: None)

    def test_wide_csr_pointer_ranges_fail_before_signed_conversion(self):
        import numpy as np
        checker = checker_module()
        wrapped = np.asarray([0, np.iinfo(np.int64).max, np.iinfo(np.int64).min, -1, 2], dtype=np.int64)
        unsigned = np.asarray([0, np.iinfo(np.uint64).max, 2], dtype=np.uint64)
        for pointers in (wrapped, unsigned):
            with self.assertRaisesRegex(ValueError, "range before narrowing"):
                checker._pointers(pointers, 2, name="malformed orientation pointers")
        for pointers in (np.asarray([0, -1, 2], dtype=np.int64),
                         np.asarray([0, 3, 2], dtype=np.int64)):
            with self.assertRaisesRegex(ValueError, "range before narrowing"):
                checker._pointers(pointers, 2, name="out-of-nnz orientation pointers")
        with self.assertRaisesRegex(ValueError, "monotonic"):
            checker._pointers(np.asarray([0, 2, 1, 3], dtype=np.int64), 3,
                              name="nonmonotone orientation pointers")
        valid = np.asarray([0, 1, 2], dtype=np.uint64)
        self.assertIs(checker._pointers(valid, 2, strictly_increasing=True), valid)


if __name__ == "__main__":
    unittest.main()
