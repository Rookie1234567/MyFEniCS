"""Tiny stdlib-only storage/source contracts; never opens numerical arrays."""
import ast
import argparse
from copy import deepcopy
import hashlib
import json
from numbers import Integral
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

CHECKER = Path(__file__).resolve().parents[2] / "benchmarks/check_y_orbit_quotient_probe.py"


class SortFixContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(CHECKER.read_text())
        keep = {"digest_json", "bind_checker_source", "admit_checker_output", "csr_row_sort_permutation", "validate_pinned_full_q_asset"}
        body = [node for node in tree.body if isinstance(node, ast.Assign)
                or isinstance(node, ast.FunctionDef) and node.name in keep]
        cls.scope = {"__file__": str(CHECKER), "Path": Path, "Integral": Integral,
                     "re": re, "json": json, "hashlib": hashlib}
        exec(compile(ast.Module(body=body, type_ignores=[]), str(CHECKER), "exec"), cls.scope)

    def source_fixture(self):
        old = {"head": self.scope["SOLVE_WORKER_HEAD"], "branch": "task40extra_dot_parallel_cloud", "dirty": "",
               "files_sha256": {"benchmarks/check_y_orbit_quotient_probe.py": "a" * 64,
                    "src/solvers/unchanged.py": "b" * 64, "input/frozen.dat": "c" * 64}}
        new = deepcopy(old); new["head"] = "d" * 40
        new["files_sha256"]["benchmarks/check_y_orbit_quotient_probe.py"] = "e" * 64
        new["files_sha256"]["src/test/test_y_orbit_quotient_checker_sort_metadata.py"] = "f" * 64
        return old, new

    def asset_fixture(self):
        descriptors = {part: {"file_sha256": digest, "shape": [15873] if part == "indptr" else [107840],
            "dtype": "complex128" if part == "data" else "int32",
            "payload_bytes": {"data": 1725440, "indices": 431360, "indptr": 63492}[part]}
            for part, digest in self.scope["HISTORICAL_FULL_Q_FILES"].items()}
        return {"prefix": "full_Q", "old": True, "csc": False, "head": self.scope["HISTORICAL_FULL_Q_HEAD"],
                "shape": (15872, 15872), "descriptors": descriptors}

    def test_exact_copy_permutation_preserves_raw_columns_values_and_pointers(self):
        columns, pointers, values = [2, 0, 1, 2, 0], [0, 3, 5], [3+4j, 1-2j, 7j, -2+1j, 8-9j]
        before = deepcopy((columns, pointers, values))
        permutation, facts = self.scope["csr_row_sort_permutation"](columns, pointers, (2, 3), historical_only=True)
        self.assertEqual(permutation, [1, 2, 0, 4, 3])
        self.assertEqual(facts["unsorted_rows"], 2)
        sorted_columns, sorted_values = [columns[i] for i in permutation], [values[i] for i in permutation]
        self.assertEqual(sorted_columns, [0, 1, 2, 0, 2])
        self.assertEqual(sorted_values, [1-2j, 7j, 3+4j, 8-9j, -2+1j])
        self.assertEqual((columns, pointers, values), before)
        for row in range(2):
            start, stop = pointers[row:row+2]
            self.assertEqual(set(permutation[start:stop]), set(range(start, stop)))
        for vector in ([1+2j, 3-1j, -4j], [0j, 1j, 2j]):
            original = [sum(values[i]*vector[columns[i]] for i in range(pointers[r], pointers[r+1])) for r in range(2)]
            normalized = [sum(sorted_values[i]*vector[sorted_columns[i]] for i in range(pointers[r], pointers[r+1])) for r in range(2)]
            self.assertEqual(original, normalized)

    def test_unsorted_candidate_is_rejected(self):
        with self.assertRaises(ValueError):
            self.scope["csr_row_sort_permutation"]([1, 0], [0, 2], (1, 2), historical_only=False)

    def test_sorted_candidate_keeps_exact_identity_permutation(self):
        permutation, facts = self.scope["csr_row_sort_permutation"]([0, 1], [0, 2], (1, 2), historical_only=False)
        self.assertEqual(permutation, [0, 1]); self.assertEqual(facts["unsorted_rows"], 0)

    def test_duplicate_columns_rejected_in_both_scopes(self):
        for historical in (False, True):
            for columns in ([0, 0], [1, 0, 1]):
                with self.subTest(historical=historical, columns=columns), self.assertRaises(ValueError):
                    self.scope["csr_row_sort_permutation"](columns, [0, len(columns)], (1, 2), historical_only=historical)

    def test_malformed_integer_pointers_and_columns_fail(self):
        fixtures = [([0], [1, 1], (1, 1)), ([0], [0, 0], (1, 1)), ([0], [0, 2], (1, 1)),
                    ([0, 1], [0, 2, 1], (2, 2)), ([2], [0, 1], (1, 2)), ([-1], [0, 1], (1, 2)),
                    ([0.0], [0, 1], (1, 2)), ([True], [0, 1], (1, 2)), ([0], [0., 1], (1, 2)),
                    ([0], [0, 1], (1.0, 2)), ([0], [0, 1], (True, 2))]
        for columns, pointers, shape in fixtures:
            with self.subTest(columns=columns, pointers=pointers, shape=shape), self.assertRaises(ValueError):
                self.scope["csr_row_sort_permutation"](columns, pointers, shape, historical_only=True)

    def test_no_implicit_truthy_historical_permission(self):
        for value in (1, "true", None):
            with self.assertRaises(ValueError):
                self.scope["csr_row_sort_permutation"]([1, 0], [0, 2], (1, 2), historical_only=value)

    def test_only_exact_pinned_historical_asset_allowed(self):
        self.assertTrue(self.scope["validate_pinned_full_q_asset"](**self.asset_fixture()))
        for key, value in (("prefix", "candidate_Q"), ("old", False), ("csc", True), ("head", "0" * 40), ("shape", (3, 3))):
            fixture = self.asset_fixture(); fixture[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.scope["validate_pinned_full_q_asset"](**fixture)

    def test_swapped_raw_hash_dtype_payload_or_missing_part_fails(self):
        for field in ("file_sha256", "dtype", "shape", "payload_bytes", "missing"):
            fixture = self.asset_fixture()
            if field == "missing": fixture["descriptors"].pop("indices")
            else: fixture["descriptors"]["indices"][field] = {"file_sha256": "0" * 64, "dtype": "int64", "shape": [1], "payload_bytes": 1}[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.scope["validate_pinned_full_q_asset"](**fixture)

    def test_checker_only_source_bridge_has_exact_non_numeric_changes(self):
        old, new = self.source_fixture()
        receipt = self.scope["bind_checker_source"](old, new)
        self.assertEqual(set(receipt["changed_paths"]), self.scope["CHECKER_SORT_ALLOWED_PATHS"])
        self.assertTrue(receipt["all_other_numerical_config_input_dependencies_equal"])
        self.assertFalse(receipt["same_head_exact_source_identity"])

    def test_wrong_worker_head_dirty_branch_and_unrecognized_path_fail(self):
        for field in ("head", "dirty", "branch", "numerical", "input", "deleted", "added"):
            old, new = self.source_fixture()
            if field == "head": old["head"] = "1" * 40
            elif field == "dirty": new["dirty"] = " M tracked"
            elif field == "branch": new["branch"] = "master"
            elif field == "numerical": new["files_sha256"]["src/solvers/unchanged.py"] = "1" * 64
            elif field == "input": new["files_sha256"]["input/frozen.dat"] = "1" * 64
            elif field == "deleted": new["files_sha256"].pop("src/solvers/unchanged.py")
            else: new["files_sha256"]["src/solvers/extra.py"] = "1" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.scope["bind_checker_source"](old, new)

    def test_same_head_source_equality_stays_exact(self):
        old, _ = self.source_fixture()
        self.assertTrue(self.scope["bind_checker_source"](old, deepcopy(old))["same_head_exact_source_identity"])
        new = deepcopy(old); new["files_sha256"]["benchmarks/check_y_orbit_quotient_probe.py"] = "e" * 64
        with self.assertRaises(ValueError): self.scope["bind_checker_source"](old, new)

    def test_normalization_does_not_call_duplicate_summing_or_mutating_sort(self):
        tree = ast.parse(CHECKER.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "sort_pinned_historical_full_q")
        calls = {node.func.attr for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & {"sum_duplicates", "sort_indices", "solve", "splu"})
        code = ast.get_source_segment(CHECKER.read_text(), function)
        self.assertLess(code.index('allocation_gate("checker_historical_full_Q_private_copy_sort"'), code.index('positions, facts ='))
        self.assertIn('raw_after != raw_before', code)
        self.assertIn('exact_coefficient_byte_permutation', code)

    def test_worker_sources_route_all_authority_and_restoration_seams(self):
        source = CHECKER.read_text()
        self.assertIn('validate_supervision(json.loads(summary_path.read_text()), worker_source)', source)
        self.assertEqual(source.count('new_source=worker_source,'), 2)
        self.assertIn('authority_receipt=authority_receipt, source=worker_source,', source)
        self.assertIn('"source": worker_source, "checker_source": checker_source', source)
        self.assertNotIn('new_source=checker_source,', source)

    def isolated_main(self, source_reader, fake_file):
        tree = ast.parse(CHECKER.read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        # Supply stdlib/stubs directly. No project module is imported in this
        # rejection-path regression, and no checker numeric call can occur.
        main.body = [node for node in main.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        scope = dict(self.scope, __file__=str(fake_file), argparse=argparse, os=os, sys=sys,
                     source_facts=source_reader, environment_facts=lambda: self.fail("ABI import must not be reached"),
                     write_json=lambda *args: self.fail("rejected output path must not write evidence"))
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(CHECKER), "exec"), scope)
        return scope["main"]

    def test_missing_cross_head_output_and_stale_expected_head_do_not_overwrite(self):
        old, new = self.source_fixture()
        for failure in ("missing_fresh_output", "stale_expected_head"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                worker = root / "benchmarks/artifacts/task40extra_dot_parallel_cloud/worker"
                worker.mkdir(parents=True)
                (worker / "probe_report.json").write_text(json.dumps({"source": old}))
                for name in ("independent_checker.json", "checker_traceback.txt", "checker_events.jsonl", "checker_phase.json"):
                    (worker / name).write_text("immutable old evidence")
                before = {path.name: path.read_bytes() for path in worker.iterdir()}
                def read_source(expected):
                    if failure == "stale_expected_head":
                        raise RuntimeError("actual clean HEAD differs from stale expected HEAD")
                    return new
                main = self.isolated_main(read_source, root / "benchmarks/check_y_orbit_quotient_probe.py")
                with patch.dict(os.environ, {"PHYSICAL_WATCHDOG_PARENT_PID": str(os.getppid()),
                        "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES": str(self.scope["TREE_CAP_BYTES"]),
                        "PHYSICAL_TIMEBASE_GUARD": "1"}), self.assertRaises((RuntimeError, ValueError)):
                    main(["--worker", "--expected-head", new["head"], "--stage", "solve", "--run-directory", str(worker)])
                self.assertEqual(before, {path.name: path.read_bytes() for path in worker.iterdir()})

    def test_output_admission_uses_actual_source_and_preserves_same_head_prior_attempt(self):
        old, new = self.source_fixture()
        for checker, explicit, prior, output in ((new, False, False, "/tmp/worker"),
                (new, True, False, "/tmp/worker"), (old, False, True, "/tmp/worker")):
            with self.assertRaises(ValueError):
                self.scope["admit_checker_output"](old, checker, worker_directory="/tmp/worker",
                    output_directory=output, explicit_checker_directory=explicit, prior_checker_output=prior)
        receipt = self.scope["admit_checker_output"](old, new, worker_directory="/tmp/worker",
            output_directory="/tmp/checker_attempt2", explicit_checker_directory=True, prior_checker_output=False)
        self.assertEqual(receipt["worker_head"], old["head"])

    def test_no_numerical_import_at_top_level(self):
        tree = ast.parse(CHECKER.read_text())
        for node in tree.body:
            if isinstance(node, ast.ImportFrom): self.assertFalse((node.module or "").startswith(("src", "benchmarks", "numpy", "scipy")))
            if isinstance(node, ast.Import): self.assertFalse(any(value.name.startswith(("numpy", "scipy", "src", "benchmarks")) for value in node.names))


if __name__ == "__main__":
    unittest.main()
