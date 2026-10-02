"""Stdlib AST-isolated descriptor tests; no numerical imports or saved arrays."""
from pathlib import Path
from types import SimpleNamespace
import ast
import copy
import hashlib
import json
import math
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT/"benchmarks/check_y_orbit_direct_probe.py"
REPO = ROOT.parents[1]/"repo" if ROOT.name == "y_orbit_direct_budget_staging" else ROOT


def extract():
    tree = ast.parse(CHECKER.read_text())
    names = {"require", "validate_descriptor_metadata", "validate_descriptor_payload"}
    nodes = [copy.deepcopy(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    saved = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SavedRun")
    method = next(node for node in saved.body if isinstance(node, ast.FunctionDef) and node.name == "descriptor")
    nodes.append(ast.ClassDef(name="DescriptorOnly", bases=[], keywords=[], body=[copy.deepcopy(method)], decorator_list=[]))
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    namespace = {"Path": Path, "hashlib": hashlib, "json": json, "math": math, "re": re}
    exec(compile(module, "<isolated readonly descriptor helpers>", "exec"), namespace)
    return namespace


class FakeDtype:
    def __init__(self, name="uint8", itemsize=1, hasobject=False):
        self.name, self.itemsize, self.hasobject = name, itemsize, hasobject

    def __str__(self): return self.name


class FakePanel:
    def __init__(self, payload, calls): self.payload, self.calls = payload, calls

    def tobytes(self, *, order):
        if order != "C": raise AssertionError("only the producer's C-order payload codec is admitted")
        self.calls.append((order, len(self.payload)))
        return self.payload


class FakeFlat:
    def __init__(self, value): self.value = value

    def __getitem__(self, key):
        if not isinstance(key, slice): raise AssertionError("bounded flat panels required")
        itemsize = self.value.dtype.itemsize
        return FakePanel(self.value.payload[key.start*itemsize:key.stop*itemsize], self.value.calls)


class FakeReadonlyArray:
    """Tiny bytes-backed stand-in; never creates a numerical ndarray or file."""
    def __init__(self, payload=b"tiny synthetic payload"):
        self.payload, self.calls = payload, []
        self.dtype, self.flags = FakeDtype(), SimpleNamespace(writeable=False)
        self.shape, self.size, self.nbytes = (len(payload),), len(payload), len(payload)
        self.flat = FakeFlat(self)

    def tobytes(self, **kwargs):
        raise AssertionError("a full-array copy must not replace bounded readonly panels")


def fixture(payload=b"tiny synthetic payload"):
    value = FakeReadonlyArray(payload)
    descriptor = {"path": "arrays/current.npy", "file_sha256": "f"*64, "shape": [len(payload)], "dtype": "uint8",
        "payload_bytes": len(payload), "finite_entries": len(payload), "nonfinite_entries": 0,
        "raw_failure_diagnostic_only": False}
    enriched = {**descriptor, "array_sha256": hashlib.sha256(payload).hexdigest()}
    return descriptor, enriched, value


class DirectDescriptorMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = extract()

    def validate(self, reference, manifest, value):
        return self.functions["validate_descriptor_payload"](reference, manifest, value)

    def test_honest_enrichment_and_plain_writer_descriptor(self):
        manifest, reference, value = fixture()
        self.assertTrue(self.validate(reference, manifest, value))
        self.assertEqual(value.calls, [("C", len(value.payload))])
        value.calls.clear()
        self.assertTrue(self.validate(manifest, manifest, value))
        self.assertEqual(value.calls, [])

    def test_empty_readonly_payload_hash_is_not_vacuous(self):
        manifest, reference, value = fixture(b"")
        self.assertTrue(self.validate(reference, manifest, value))
        reference["array_sha256"] = "0"*64
        with self.assertRaises(ValueError): self.validate(reference, manifest, value)

    def test_every_shared_field_is_required_in_both_records(self):
        manifest, reference, value = fixture()
        for key in manifest:
            missing = dict(reference); missing.pop(key)
            with self.subTest(record="reference", key=key), self.assertRaises(ValueError): self.validate(missing, manifest, value)
            missing = dict(manifest); missing.pop(key)
            with self.subTest(record="manifest", key=key), self.assertRaises(ValueError): self.validate(reference, missing, value)

    def test_different_shared_fields_are_never_normalized(self):
        manifest, reference, value = fixture()
        changes = {"path": "arrays/other.npy", "file_sha256": "a"*64, "shape": [len(value.payload)-1],
            "dtype": "float64", "payload_bytes": len(value.payload)+1, "finite_entries": len(value.payload)-1,
            "nonfinite_entries": 1, "raw_failure_diagnostic_only": True}
        for key, changed in changes.items():
            candidate = {**reference, key: changed}
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(candidate, manifest, value)

    def test_bad_payload_hash_or_hash_schema_is_rejected(self):
        manifest, reference, value = fixture()
        for digest in ("a"*64, "", "F"*64, "wrong", None, True):
            candidate = {**reference, "array_sha256": digest}
            with self.subTest(digest=digest), self.assertRaises(ValueError): self.validate(candidate, manifest, value)

    def test_only_known_enrichment_is_allowed(self):
        manifest, reference, value = fixture()
        for key in ("schema", "status", "array_hash", "array_sha256_2", "ignored_extra"):
            with self.subTest(record="reference", key=key), self.assertRaises(ValueError):
                self.validate({**reference, key: "unexpected"}, manifest, value)
            with self.subTest(record="manifest", key=key), self.assertRaises(ValueError):
                self.validate(reference, {**manifest, key: "unexpected"}, value)

    def test_nonfinite_and_raw_failure_evidence_is_rejected_even_if_shared(self):
        manifest, reference, value = fixture()
        for changes in ({"finite_entries": 0, "nonfinite_entries": value.size, "raw_failure_diagnostic_only": True},
            {"nonfinite_entries": 1}, {"raw_failure_diagnostic_only": True}, {"finite_entries": True},
            {"shape": [True]}, {"payload_bytes": float(value.nbytes)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.validate({**reference, **changes}, {**manifest, **changes}, value)

    def test_enrichment_requires_exact_readonly_typed_array(self):
        for mutation in ("writeable", "object", "shape", "dtype", "bytes", "size", "payload"):
            manifest, reference, value = fixture()
            if mutation == "writeable": value.flags.writeable = True
            elif mutation == "object": value.dtype.hasobject = True
            elif mutation == "shape": value.shape = (value.size+1,)
            elif mutation == "dtype": value.dtype.name = "int8"
            elif mutation == "bytes": value.nbytes += 1
            elif mutation == "size": value.size += 1
            else: value.payload = b"x"*len(value.payload)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.validate(reference, manifest, value)

    def test_saved_run_descriptor_uses_exact_manifest_and_independent_hash(self):
        manifest, reference, value = fixture()
        admissions, loads = [], []
        holder = SimpleNamespace(paths={manifest["path"]: "current"}, descriptors={"current": manifest},
            load=lambda name: (loads.append(name), value)[1], gate=lambda name, facts: admissions.append((name, facts)))
        method = self.functions["DescriptorOnly"].descriptor
        self.assertIs(method(holder, reference), value)
        self.assertEqual(loads, ["current"])
        self.assertEqual(admissions[0][1], {"matrix_payload_bytes": 0, "workspace_bytes": 2 << 20})
        candidate = {**reference, "finite_entries": 0}
        loads.clear()
        with self.assertRaises(ValueError): method(holder, candidate)
        self.assertEqual(loads, [])
        candidate = {**reference, "array_sha256": "a"*64}
        with self.assertRaises(ValueError): method(holder, candidate)

    def test_source_join_and_finite_loader_are_preserved(self):
        tree = ast.parse(CHECKER.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "check_direct")
        joins = [node for node in ast.walk(function) if isinstance(node, ast.For)
            and ast.unparse(node.iter) == "fresh['arrays'].items()"]
        self.assertEqual(len(joins), 1)
        self.assertIn("validate_descriptor_metadata(descriptor, manifest[name])", ast.unparse(joins[0]))
        self.assertIn("saved.descriptor(descriptor)", ast.unparse(joins[0]))
        staged = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SavedRun")
        canonical = next(node for node in ast.parse((REPO/"benchmarks/check_y_orbit_direct_probe.py").read_text()).body
                         if isinstance(node, ast.ClassDef) and node.name == "SavedRun")
        staged_load = next(node for node in staged.body if isinstance(node, ast.FunctionDef) and node.name == "load")
        canonical_load = next(node for node in canonical.body if isinstance(node, ast.FunctionDef) and node.name == "load")
        self.assertEqual(ast.dump(staged_load, include_attributes=False), ast.dump(canonical_load, include_attributes=False))
        for name in ("require", "validate_descriptor_metadata", "validate_descriptor_payload"):
            helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            self.assertFalse(any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(helper)))
        ast.parse(Path(__file__).read_text(), filename=str(Path(__file__)))
        for suffix in ("*.npy", "*.npz"):
            self.assertFalse(list((ROOT / "src").rglob(suffix)))
            self.assertFalse([path for path in (ROOT / "benchmarks").rglob(suffix)
                              if path.relative_to(ROOT / "benchmarks").parts[0] != "artifacts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
