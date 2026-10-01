"""Pure standard-library gates: these tests launch no PDE or factor."""

from pathlib import Path
import copy
import json
import tempfile
import unittest

from benchmarks.run_real_p4_probe import projected_allocation_bytes, validate_source_receipt
from src.solvers.real_p4_probe import (
    G0_MODE_SHA256, G0_MODE_REFERENCE_SHA256, file_sha256,
    validate_named_input, validate_named_mode_inventory, write_json,
)


class ProbeContractTests(unittest.TestCase):
    def _mode_reference(self):
        path = Path(__file__).resolve().parents[2] / "benchmarks/cases/task40extra_dot_parallel_cloud/real_p4_mode_reference.json"
        self.assertEqual(file_sha256(path), G0_MODE_REFERENCE_SHA256)
        reference = json.loads(path.read_text())
        rows = []
        for index, row in enumerate(reference["rows"]):
            side, m, n, polarization = row["key"]
            rows.append({"side": side, "m": m, "n": n, "polarization": polarization, "mode_index": index,
                         "propagating": row["propagating"], "rayleigh_warning": row["rayleigh_warning"],
                         **{new: row[old] for old, new in (("alpha", "alpha"), ("gamma", "gamma"), ("beta", "beta"),
                             ("E", "e_vector"), ("H", "h_vector"), ("k", "k_vector"),
                             ("tangent_norm_sq", "electric_tangential_norm_sq"), ("power", "power_per_unit_amplitude"))}})
        return rows, reference

    def test_new_mode_identity_and_reference_gate_are_explicit(self):
        rows, reference = self._mode_reference()
        facts = validate_named_mode_inventory(rows, G0_MODE_SHA256, reference)
        self.assertFalse(facts["historical_hash_identity_claimed"])
        self.assertTrue(facts["exact_ordered_key_index_and_flags"])
        self.assertEqual(max(facts["max_absolute_deltas"].values()), 0)

    def test_mode_gate_rejects_old_hash_reorder_nonfinite_and_changed_values(self):
        rows, reference = self._mode_reference()
        with self.assertRaises(ValueError):
            validate_named_mode_inventory(rows, "c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a", reference)
        for field, value in (("m", 0), ("m", float(rows[0]["m"])), ("propagating", False),
                             ("power_per_unit_amplitude", float("nan")), ("power_per_unit_amplitude", 2.0)):
            mutated = copy.deepcopy(rows)
            mutated[0][field] = value
            with self.assertRaises(ValueError):
                validate_named_mode_inventory(mutated, G0_MODE_SHA256, reference)
        with self.assertRaises(ValueError):
            validate_named_mode_inventory(rows[::-1], G0_MODE_SHA256, reference)

    def test_repository_named_input_is_hash_bound(self):
        root = Path(__file__).resolve().parents[2]
        validate_named_input(root / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat")

    def test_unknown_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.dat"
            path.write_text("not a physical fixture")
            with self.assertRaises(ValueError):
                validate_named_input(path)

    def test_existing_allocation_boundaries_are_explicit(self):
        self.assertEqual(projected_allocation_bytes("condensed_matrix", {"matrix_payload_bytes": 10, "workspace_bytes": 2}), 12)
        self.assertEqual(projected_allocation_bytes("cell_tensor_working_set", {"retained_numeric_bytes_upper": 20, "workspace_bytes": 3}), 23)
        with self.assertRaises(ValueError):
            projected_allocation_bytes("unknown", {})

    def test_source_receipt_cannot_pass_wrong_head_or_missing_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            write_json(path, {"source_sha": "a" * 40, "all_required_checks_passed": True})
            digest = file_sha256(path)
            self.assertTrue(validate_source_receipt(path, digest, "a" * 40)["all_required_checks_passed"])
            with self.assertRaises(RuntimeError):
                validate_source_receipt(path, digest, "b" * 40)
            with self.assertRaises(RuntimeError):
                validate_source_receipt(path, "0" * 64, "a" * 40)
            write_json(path, {"source_sha": "a" * 40})
            with self.assertRaises(RuntimeError):
                validate_source_receipt(path, file_sha256(path), "a" * 40)


if __name__ == "__main__":
    unittest.main()
