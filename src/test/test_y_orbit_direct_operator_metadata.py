"""Standard-library-only source/negative metadata tests; never import FE.

The scalar admission function is extracted with AST.  Neither the numerical
module nor NumPy/SciPy/project packages are imported or executed by this file.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
import re
import copy
import math


SOURCE = Path(__file__).parents[1] / "solvers" / "y_orbit_direct_operator_qualification.py"


def scalar_admission():
    tree = ast.parse(SOURCE.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "checked_integer_metadata")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["checked_integer_metadata"]


def scalar_name_codec():
    tree = ast.parse(SOURCE.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "safe_witness_name")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["safe_witness_name"]


def provider_norm_gate():
    tree = ast.parse(SOURCE.read_text())
    names = {"_require", "_check_provider_block_norms"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    limit = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "LIMIT" for target in node.targets))
    namespace = {"LIMIT": limit}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_check_provider_block_norms"]


def matrix_block_record(p, q, reference, independent):
    """Exact small block injections test the gate, not a Maxwell substitute."""
    left = [complex(value) for row in reference for value in row]
    right = [complex(value) for row in independent for value in row]
    differences = [a-b for a, b in zip(right, left, strict=True)]
    return {"p": p, "q": q, "reference_norm": math.hypot(*(abs(value) for value in left)),
        "norm": math.hypot(*(abs(value) for value in right)),
        "difference_norm": math.hypot(*(abs(value) for value in differences)),
        "absolute_max_reference": max(map(abs, left)), "absolute_max_independent": max(map(abs, right)),
        "absolute_max_difference": max(map(abs, differences))}


def block_inventory():
    zero = [[0, 0], [0, 0]]
    return [matrix_block_record(p, q, [[scale, 0], [0, scale]], [[scale, 0], [0, scale]])
            if p == q else matrix_block_record(p, q, zero, zero)
            for p in (0, 1) for q in (0, 1)
            for scale in [10 if p == 0 else 1]]


class DirectOperatorMetadataTests(unittest.TestCase):
    def test_complete_public_source_is_syntactic_and_FE_imports_are_lazy(self):
        source = SOURCE.read_text()
        tree = ast.parse(source)
        compile(source, str(SOURCE), "exec")
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue({"audit_direct_original_cell_contributions", "check_direct_original_cell_contributions",
                         "export_direct_volume_source", "saved_direct_volume_action"}.issubset(functions))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module, {"dolfinx", "petsc4py", "mpi4py", "basix", "ufl"})
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)}
        self.assertFalse(calls.intersection({"splu", "spsolve", "lu_factor", "lu_solve"}))

    def test_admits_only_bounded_actual_integers(self):
        self.assertTrue(scalar_admission()([0, 8], 9))

    def test_rejects_scalar_type_and_range_before_conversion(self):
        admission = scalar_admission()
        for values, upper, expected in (([1.5], 9, TypeError), ([True], 9, TypeError),
                                        ([-1], 9, ValueError), ([9], 9, ValueError),
                                        ([2**64 - 1], 9, ValueError)):
            with self.subTest(values=values, upper=upper):
                with self.assertRaises(expected):
                    admission(values, upper)

    def test_rejects_capacity_overflow_even_with_empty_actual_inventory(self):
        with self.assertRaises(OverflowError):
            scalar_admission()([], 2**31 + 1)

    def test_rejects_malformed_target_capacity(self):
        admission = scalar_admission()
        for upper, maximum in ((0, 9), (1.0, 9), (1, -1), (1, True)):
            with self.subTest(upper=upper, maximum=maximum):
                with self.assertRaises(ValueError):
                    admission([0], upper, maximum=maximum)

    def test_runner_name_codec_is_safe_and_does_not_collide(self):
        codec = scalar_name_codec()
        names = ["role/native/rows", "role_native_rows", "role_x2f_native", "role/α", "role/x3b1_", "a/b", "a_x2f_b"]
        encoded = [codec(name) for name in names]
        self.assertEqual(len(set(encoded)), len(names))
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_]+", name) for name in encoded))


class ProviderZeroOffbranchGateTests(unittest.TestCase):
    def test_complete_identical_operator_passes_and_preserves_norms(self):
        records = block_inventory()
        output = provider_norm_gate()(records)
        self.assertIs(output, records)
        self.assertTrue(all(item["whole_2x2_frobenius_relative_difference"] == 0 for item in output))
        for item in output:
            if item["p"] != item["q"]:
                self.assertEqual([row["diagonal_branch"] for row in item["both_diagonal_operation_scales"]],
                                 [item["p"], item["q"]])

    def test_cancellation_residue_keeps_failed_self_relative_as_diagnostic(self):
        records = block_inventory()
        records[1] = matrix_block_record(0, 1, [[1e-15, 0], [0, 0]], [[2e-15, 0], [0, 0]])
        output = provider_norm_gate()(records)
        self.assertEqual(output[1]["full_column_difference"], 1)
        self.assertGreater(output[1]["operation_scaled_difference"], 0)
        self.assertLess(output[1]["operation_scaled_difference"], 1e-11)

    def test_injected_equal_wrong_offbranch_coupling_cannot_hide_in_zero_difference(self):
        records = block_inventory()
        coupling = [[2e-11, 0], [0, 0]]
        records[1] = matrix_block_record(0, 1, coupling, coupling)
        with self.assertRaisesRegex(ValueError, "offbranch difference or leakage"):
            provider_norm_gate()(records)

    def test_one_sided_wrong_coupling_rejected_in_either_reconstruction(self):
        zero, coupling = [[0, 0], [0, 0]], [[2e-11, 0], [0, 0]]
        for reference, independent in ((zero, coupling), (coupling, zero)):
            with self.subTest(reference=reference):
                records = block_inventory()
                records[2] = matrix_block_record(1, 0, reference, independent)
                with self.assertRaisesRegex(ValueError, "offbranch difference or leakage"):
                    provider_norm_gate()(records)

    def test_larger_other_diagonal_cannot_mask_weak_diagonal(self):
        records = block_inventory()
        records[0] = matrix_block_record(0, 0, [[1e8, 0], [0, 1e8]], [[1e8, 0], [0, 1e8]])
        records[1] = matrix_block_record(0, 1, [[2e-11, 0], [0, 0]], [[2e-11, 0], [0, 0]])
        with self.assertRaisesRegex(ValueError, "offbranch difference or leakage"):
            provider_norm_gate()(records)

    def test_diagonal_self_relative_gate_remains(self):
        records = block_inventory()
        records[3] = matrix_block_record(1, 1, [[1, 0], [0, 1]], [[1+1e-9, 0], [0, 1]])
        with self.assertRaisesRegex(ValueError, "diagonal contribution sum"):
            provider_norm_gate()(records)

    def test_per_block_bounds_do_not_replace_complete_operator_bound(self):
        reference, independent = [[1, 0], [0, 1]], [[1+1.2e-11, 0], [0, 1]]
        coupling, zero = [[1.2e-11, 0], [0, 0]], [[0, 0], [0, 0]]
        records = [matrix_block_record(p, q, reference, independent) if p == q
                   else matrix_block_record(p, q, coupling, zero)
                   for p in (0, 1) for q in (0, 1)]
        with self.assertRaisesRegex(ValueError, "original2x2 Frobenius"):
            provider_norm_gate()(records)

    def test_zero_diagonal_rejected_without_floor(self):
        for name in ("reference_norm", "norm"):
            records = block_inventory()
            records[0][name] = 0
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "zero diagonal"):
                provider_norm_gate()(records)

    def test_nonfinite_negative_norms_rejected_in_every_diagnostic(self):
        for name in ("norm", "reference_norm", "difference_norm", "absolute_max_difference",
                     "absolute_max_reference", "absolute_max_independent"):
            for value in (math.nan, math.inf, -1):
                records = block_inventory()
                records[1][name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    provider_norm_gate()(records)

    def test_missing_duplicate_and_extra_pairs_rejected(self):
        records = block_inventory()
        malformed = [records[:-1], records+[copy.deepcopy(records[0])],
                     [records[0], records[1], records[1], records[3]]]
        for entries in malformed:
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, "every2x2 block"):
                provider_norm_gate()(entries)

    def test_aggregate_overflow_cannot_turn_excessive_difference_into_zero(self):
        records = block_inventory()
        for item in records:
            if item["p"] == item["q"]:
                item["reference_norm"] = item["norm"] = 1.7e308
        with self.assertRaisesRegex(ValueError, "aggregate norms must be finite"):
            provider_norm_gate()(records)


if __name__ == "__main__":
    unittest.main()
