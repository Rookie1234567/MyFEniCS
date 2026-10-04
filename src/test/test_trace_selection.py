"""Focused actual workflow and negative evidence tests; no old campaign replay."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix

from benchmarks.check_trace_selection import inventory
from src.solvers.bound_array_identity import consume_identity, file_hash, read_arrays, source_identity
from src.solvers.port_component_study import array_file
from src.solvers.trace_subspace_selection import SingleCSR, mask_from_scores, masked_coefficients, witness_metrics


class IdentityTests(unittest.TestCase):
    def test_p4_declared_p6_never_reaches_consumer(self):
        actual = source_identity(b"cfg=replace(cfg,nedelec_degree=4)\nr={'degree':4}\n", {"source_head":"a"*40}, blob="b"*40)
        called = []
        result = consume_identity({"degree": 6}, actual, lambda _: called.append(True))
        self.assertFalse(result["accepted"])
        self.assertFalse(called)
        self.assertEqual(actual["scale"], "unknown")

    def test_conflicting_source_and_unknown_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            source_identity(b"cfg=replace(cfg,nedelec_degree=4)\nr={'degree':6}\n", {}, blob="b")
        self.assertFalse(consume_identity({"degree": 6}, {}, lambda _: True)["accepted"])

    def test_streaming_actual_reader_not_read_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            p = Path(name)/"x.npz"
            receipt = array_file(p, compressed=True, value=np.arange(32, dtype=np.complex128))
            with patch.object(Path, "read_bytes", side_effect=AssertionError("large bytes copy")):
                self.assertEqual(file_hash(p), receipt["sha256"])
                self.assertEqual(len(read_arrays(receipt, name)["value"]), 32)
            bad = copy.deepcopy(receipt)
            bad["members"]["value"]["sha256"] = "0"*64
            with self.assertRaisesRegex(ValueError, "member"):
                read_arrays(bad, name)

    def test_wrong_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            receipt = array_file(Path(name)/"x.npz", value=np.zeros(2))
            receipt["members"]["missing"] = receipt["members"]["value"]
            with self.assertRaisesRegex(ValueError, "inventory"):
                read_arrays(receipt, name)


class NumericalTests(unittest.TestCase):
    def test_complex_nonhermitian_adjoint_without_conjugate_copy(self):
        m = csr_matrix(np.array([[2+3j, 4j], [7-1j, -2+2j]]))
        op = SingleCSR({"data":m.data,"indices":m.indices,"indptr":m.indptr,"shape":np.array(m.shape)})
        self.assertTrue(np.shares_memory(op.matrix.data, op.transpose.data))
        x = np.array([1+2j, -3+4j])
        np.testing.assert_allclose(op.apply(x, adjoint=True), m.toarray().conj().T@x, atol=1e-14)

    def test_top_coordinate_optimum_complex_and_internal_retention(self):
        c = np.array([3+4j, 5j, 2-1j, 1+1j, 100j])
        mask = mask_from_scores(abs(c[:4]), 4, 0.5)
        np.testing.assert_array_equal(mask, [True, True, False, False])
        selected = masked_coefficients(c, mask)
        self.assertEqual(selected[-1], c[-1])
        from itertools import combinations
        error = np.linalg.norm(c-selected)
        for ids in combinations(range(4), 2):
            other = np.zeros(4, bool);other[list(ids)] = True
            self.assertLessEqual(error, np.linalg.norm(c-masked_coefficients(c, other))+1e-14)

    def test_zero_and_exact_full_keep(self):
        c = np.zeros(5, complex)
        metric = witness_metrics(c,c,np.zeros(7,complex),np.zeros(7,complex),3)
        self.assertTrue(metric["passed"])
        np.testing.assert_array_equal(mask_from_scores(np.zeros(4),4,.5),[True,True,False,False])

    def test_small_coefficient_error_can_have_large_native_residual(self):
        c = np.array([1,1e-6,2], complex)
        selected = masked_coefficients(c, np.array([True,False]))
        a = np.diag([1,1e7,1])
        result = witness_metrics(c,selected,a@c,a@(selected-c),2)
        self.assertLess(result["eta"],1e-4)
        self.assertGreater(result["rho"],1e-6)
        self.assertFalse(result["passed"])

    def test_finite_floor_and_invalid_scores(self):
        self.assertEqual(mask_from_scores(np.arange(7),7,.8).sum(),5)
        with self.assertRaisesRegex(ValueError,"finite"):
            mask_from_scores(np.array([0,np.nan]),2,.5)

    def test_checker_inventory_is_exact_not_status(self):
        plan={"split":{s:{"seeds":[1],"families":["x"]} for s in ("train","validation")}}
        rows=[dict(split=s,sample=0,fraction=f,seed=1,family="x") for s in plan["split"] for f in (.5,.8)]
        inventory(plan,rows)
        with self.assertRaisesRegex(ValueError,"inventory"):
            inventory(plan,rows[:-1])
        with self.assertRaisesRegex(ValueError,"inventory"):
            inventory(plan,rows+rows[:1])

    def test_real_dat_schema_and_live_limits(self):
        from src.io.port_preparation import load_preparation
        from src.runners.port_preparation import storage_limits
        from src.solvers.trace_selection_scope import ROOT
        for label in ("data","oracle","check","analysis"):
            spec=load_preparation(ROOT/f"input/task042_neural_coarse_inverse/v47_{label}.dat")
            self.assertEqual(spec.derived["preparation_scope"],"v47")
            self.assertEqual(dict(spec.derived["storage_limits"]),storage_limits("v47"))
            self.assertEqual(spec.execution["terminate_memory_gib"],2)


if __name__ == "__main__":
    unittest.main()
