"""Isolated tiny storage contracts; never import a project FE module.

These definitions may run under stdlib unittest once bounded helper execution
is authorized. They use only two-channel invented helper data, not PDE arrays
or saved numerical evidence; they confer no same80 numerical qualification.
"""

import gc
import ast
from dataclasses import dataclass, field
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import patch
import weakref

import numpy as np


_PATH = Path(__file__).resolve().parents[1] / "solvers" / "y_orbit_transform_bank.py"
_SPEC = importlib.util.spec_from_file_location("isolated_y_orbit_transform_bank", _PATH)
bank_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bank_module
_SPEC.loader.exec_module(bank_module)


class TransformBankContracts(unittest.TestCase):
    def setUp(self):
        self.bank = bank_module.RunLocalTransformBank()
        self.basis = self.bank.bind_basis({"actual_test_basis": "two_channels", "degree": 4})
        self.key = bank_module.TransformKey(self.basis, 3, (2, 2), (4, 7),
                                            ("cell_info", 0), ("test_Tt_apply_semantics",))
        self.matrix = np.array([[2, 1j], [0, 3]], dtype=np.complex128)

    def test_each_actual_state_builder_runs_once(self):
        calls = []

        def build():
            calls.append(True)
            return self.matrix

        first = self.bank.matrix(self.key, build)
        second = self.bank.matrix(self.key, build)
        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)
        with patch.object(bank_module, "_digest", wraps=bank_module._digest) as digest:
            for _ in range(10):
                self.bank.validate_borrow(self.key, first)
                self.bank.key_for(first)
                self.bank.matrix(self.key, build)
            self.assertEqual(digest.call_count, 0)

    def test_identical_contents_intern_across_actual_cell_states(self):
        first = self.bank.matrix(self.key, lambda: self.matrix)
        other = bank_module.TransformKey(self.basis, 3, (2, 2), (4, 7),
                                         ("cell_info", 17), ("test_Tt_apply_semantics",))
        second = self.bank.matrix(other, lambda: self.matrix.copy())
        self.assertIs(first, second)
        receipt = self.bank.receipt(stage="two_states")
        self.assertEqual(receipt["actual_state_count"], 2)
        self.assertEqual(receipt["matrix_template_count"], 1)
        self.assertEqual(receipt["lazy_inverse_count"], 0)

    def test_lazy_inverse_is_shared_and_uses_actual_inverse(self):
        first = self.bank.matrix(self.key, lambda: self.matrix)
        self.assertEqual(self.bank.receipt(stage="before_inverse")["lazy_inverse_count"], 0)
        inverse = self.bank.inverse(first)
        self.assertIs(self.bank.inverse(first), inverse)
        np.testing.assert_array_equal(inverse, np.linalg.inv(self.matrix))
        self.assertFalse(np.array_equal(inverse, first.conj().T))
        self.assertEqual(self.bank.receipt(stage="after_inverse")["lazy_inverse_count"], 1)

    def test_array_data_and_write_flag_cannot_mutate(self):
        first = self.bank.matrix(self.key, lambda: self.matrix)
        inverse = self.bank.inverse(first)
        for array in (first, inverse):
            with self.assertRaises(ValueError):
                array[0, 0] = 0
            with self.assertRaises(ValueError):
                array.setflags(write=True)
            with self.assertRaises(ValueError):
                array.base.setflags(write=True)

    def test_metadata_mutation_and_unbanked_borrower_fail(self):
        first = self.bank.matrix(self.key, lambda: self.matrix)
        with self.assertRaises(ValueError):
            self.bank.inverse(first.copy())
        first.shape = (4,)
        with self.assertRaises(ValueError):
            self.bank.key_for(first)

    def test_basis_channel_order_and_semantics_are_not_cross_interned(self):
        first = self.bank.matrix(self.key, lambda: self.matrix)
        other_basis = self.bank.bind_basis({"actual_test_basis": "different_coefficients", "degree": 4})
        keys = [bank_module.TransformKey(other_basis, 3, (2, 2), (4, 7), self.key.state, self.key.semantics),
                bank_module.TransformKey(self.basis, 3, (2, 2), (7, 4), self.key.state, self.key.semantics),
                bank_module.TransformKey(self.basis, 3, (2, 2), (4, 7), self.key.state, ("different_semantics",))]
        for key in keys:
            self.assertIsNot(first, self.bank.matrix(key, lambda: self.matrix))

    def test_complete_content_collision_fails(self):
        with patch.object(bank_module, "_digest", return_value="collision"):
            self.bank.matrix(self.key, lambda: self.matrix)
            other = bank_module.TransformKey(self.basis, 3, (2, 2), (4, 7),
                                             ("cell_info", 1), self.key.semantics)
            with self.assertRaises(ValueError):
                self.bank.matrix(other, lambda: self.matrix + 1)

    def test_unknown_state_basis_shape_and_unseen_sealed_key_fail(self):
        keys = [bank_module.TransformKey("unknown", 3, (2, 2), (4, 7), self.key.state, self.key.semantics),
                bank_module.TransformKey(self.basis, 1, (2, 2), (0, 1), ("edge_reversal", 8), self.key.semantics),
                bank_module.TransformKey(self.basis, 2, (2, 2), (0, 1), ("face_D4", (0, 1, 2, 3), 8), self.key.semantics),
                bank_module.TransformKey(self.basis, 3, (2, 2), (4, 7), ("cell_info", 2**30), self.key.semantics),
                bank_module.TransformKey(self.basis, 3, (2, 2), (4,), self.key.state, self.key.semantics)]
        for key in keys:
            with self.assertRaises(ValueError):
                self.bank.matrix(key, lambda: self.matrix)
        first = self.bank.matrix(self.key, lambda: self.matrix)
        self.bank.seal()
        self.assertIs(first, self.bank.matrix(self.key, lambda: self.matrix))
        with self.assertRaises(ValueError):
            self.bank.bind_basis({"new_basis": True})
        other = bank_module.TransformKey(self.basis, 3, (2, 2), (4, 7), ("cell_info", 1), self.key.semantics)
        with self.assertRaises(ValueError):
            self.bank.matrix(other, lambda: self.matrix)

    def test_owner_receipt_counts_aliases_once_and_ids_stay_stable(self):
        first = self.bank.matrix(self.key, lambda: self.matrix)
        receipt = self.bank.receipt({"full.matrix": first, "local.matrix": first,
                                     "local.transpose": first.T}, stage="matrix_only")
        self.assertEqual(receipt["owner_count"], 1)
        self.assertEqual(receipt["unique_backing_owner_nbytes"], first.nbytes)
        self.assertEqual(receipt["sum_view_nbytes_with_aliases"], 4 * first.nbytes)
        token = receipt["owners"][0]["owner_id"]
        next_receipt = self.bank.receipt({"full.matrix": first}, stage="later")
        self.assertEqual(next_receipt["owners"][0]["owner_id"], token)
        self.assertNotIn("pointer", str(receipt))

    def test_inventory_handles_byte_buffer_subview_and_negative_strides(self):
        inventory = bank_module.BackingOwnerInventory()
        buffer = bytes(range(32))
        array = np.frombuffer(buffer, dtype=np.uint8)[4:12]
        receipt = inventory.receipt({"forward": array, "reverse": array[::-1]}, stage="byte_views")
        self.assertEqual(receipt["owner_count"], 1)
        self.assertEqual(receipt["unique_backing_owner_nbytes"], len(buffer))
        self.assertEqual(receipt["sum_view_nbytes_with_aliases"], 16)
        self.assertTrue(all(view["backing_span"] == [4, 12] for view in receipt["views"]))
        fortran = np.asfortranarray(np.array([[1, 2], [3, 4]], dtype=np.int16))
        receipt = inventory.receipt({"old_fortran": fortran}, stage="fortran_owner")
        self.assertEqual(receipt["owners"][0]["sha256"], sha256(fortran.tobytes(order="A")).hexdigest())
        self.assertEqual(receipt["views"][0]["sha256"], sha256(fortran.tobytes(order="C")).hexdigest())
        self.assertEqual(receipt["owners"][0]["strides"], list(fortran.strides))

    def test_receipt_registry_does_not_retain_discarded_arrays(self):
        inventory = bank_module.BackingOwnerInventory()
        array = np.arange(6)
        reference = weakref.ref(array)
        inventory.receipt({"temporary": array}, stage="temporary")
        del array
        gc.collect()
        self.assertIsNone(reference())
        self.assertEqual(inventory.receipt({}, stage="cleanup")["unique_backing_owner_nbytes"], 0)

    def test_destroying_one_borrower_keeps_other_borrower_valid(self):
        full = {"matrix": self.bank.matrix(self.key, lambda: self.matrix)}
        local = {"matrix": full["matrix"]}
        inverse = self.bank.inverse(local["matrix"])
        del local
        gc.collect()
        self.assertIs(self.bank.inverse(full["matrix"]), inverse)
        matrix_ref, inverse_ref = weakref.ref(full["matrix"]), weakref.ref(inverse)
        del full, inverse
        self.bank.close()
        gc.collect()
        self.assertIsNone(matrix_ref())
        self.assertIsNone(inverse_ref())
        receipt = self.bank.receipt(stage="whole_run_cleanup")
        self.assertTrue(receipt["closed"])
        self.assertEqual(receipt["unique_backing_owner_nbytes"], 0)
        for operation in (lambda: self.bank.bind_basis({"new": True}),
                          lambda: self.bank.matrix(self.key, lambda: self.matrix),
                          lambda: self.bank.inverse(self.matrix), lambda: self.bank.seal()):
            with self.assertRaises(ValueError):
                operation()

    def test_actual_state_witness_returns_independent_fresh_metadata(self):
        # Extract just the dataclass from owned source, without importing its
        # module, scipy, or any project FE module. No FE/numerical arrays run.
        source = _PATH.with_name("task40extra_y_orbit_reference.py")
        tree = ast.parse(source.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "YOrbitEntities")
        namespace = {"__name__": _SPEC.name, "np": np, "dataclass": dataclass,
                     "field": field, "Any": Any}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
        entities = object.__new__(namespace["YOrbitEntities"])
        record = (0, (2, "example"))
        entities._transform_bank = object()
        entities._actual_state_witnesses = {
            record: (2, ((0.0, 1.0, 2.0), (3.0, 4.0, 5.0)), 7, 1, (8, 6), 19)}
        witness = entities.actual_state_witness(record)
        self.assertEqual(witness, {"dimension": 2, "native_coordinates": [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
                                   "cell": 7, "local_entity": 1, "positions": [8, 6], "cell_info": 19})
        witness["native_coordinates"][0][0] = 99.0
        witness["positions"].reverse()
        fresh = entities.actual_state_witness(record)
        self.assertEqual(fresh["native_coordinates"][0][0], 0.0)
        self.assertEqual(fresh["positions"], [8, 6])
        entities._transform_bank = None
        with self.assertRaises(ValueError):
            entities.actual_state_witness(record)


if __name__ == "__main__":
    unittest.main()
