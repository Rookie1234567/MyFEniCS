"""Stdlib rejection tests only; no scientific payload, NumPy/SciPy or FE imports."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

from src.solvers import fresh_c1b_saved_authority as authority

class SourceRejections(unittest.TestCase):
    def setUp(self):
        self.source = {"head": authority.HEAD, "branch": authority.BRANCH, "dirty": "",
                       "files_sha256": {"src/frozen.py": "a" * 64}}
        self.env = {key: "fixed" for key in authority.ENV_FIELDS}
        self.env["qualification_manifest_sha256"] = authority.ABI_SHA

    def reject(self, source=None, env=None, **kwargs):
        with self.assertRaises(ValueError):
            authority.validate_source_environment(self.source, source or self.source,
                self.env, env or self.env, **kwargs)

    def test_existing_dependency_changed(self):
        changed = copy.deepcopy(self.source)
        changed["files_sha256"]["src/frozen.py"] = "b" * 64
        self.reject(changed)

    def test_existing_dependency_removed(self):
        changed = copy.deepcopy(self.source)
        changed["files_sha256"].clear()
        self.reject(changed)

    def test_unreviewed_added_dependency(self):
        changed = copy.deepcopy(self.source)
        changed["files_sha256"]["src/new.py"] = "b" * 64
        self.reject(changed)

    def test_existing_path_cannot_be_allowlisted(self):
        self.reject(allowed_added_paths=("src/frozen.py",))

    def test_traversal_cannot_be_allowlisted(self):
        self.reject(allowed_added_paths=("../outside.py",))

    def test_nonhash_added_dependency(self):
        changed = copy.deepcopy(self.source)
        changed["files_sha256"]["src/new.py"] = "invalid"
        self.reject(changed, allowed_added_paths=("src/new.py",))

    def test_dirty_source(self):
        changed = copy.deepcopy(self.source)
        changed["dirty"] = " M src/frozen.py"
        self.reject(changed)

    def test_other_branch(self):
        changed = copy.deepcopy(self.source)
        changed["branch"] = "other"
        self.reject(changed)

    def test_abi_changed(self):
        changed = copy.deepcopy(self.env)
        changed["petsc_int_type"] = "int64"
        self.reject(env=changed)

    def test_abi_missing(self):
        changed = copy.deepcopy(self.env)
        del changed["modules"]
        self.reject(env=changed)


class ReaderRejections(unittest.TestCase):
    def test_missing_current_gate(self):
        with self.assertRaises(ValueError):
            authority.FreshC1bSavedAuthority(".", new_source={}, new_environment={},
                allocation_gate=None, worker_library_receipt="none", checker_library_receipt="none")

    def test_q_outside_component(self):
        # Scope validation must happen before any reader state or payload access.
        for q in (1, 2, 3, -1, True, 0.0, "0"):
            with self.subTest(q=q), self.assertRaises(ValueError):
                authority.FreshC1bSavedAuthority.q_block(None, q)

    def test_wrong_q0_shape(self):
        with self.assertRaises(ValueError):
            authority.FreshC1bSavedAuthority.load_csr(None, "q_0_S", (1885, 1885))

    def test_unapproved_q_csr(self):
        with self.assertRaises(ValueError):
            authority.FreshC1bSavedAuthority.load_csr(None, "q_1_S", (1960, 1960))

    def test_path_escape(self):
        with tempfile.TemporaryDirectory() as root:
            for relative in ("../outside", "/tmp/outside", "missing"):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    authority.bound_path(root, relative)

    def test_metadata_hash_precedes_gate_and_parse(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "metadata.json"
            path.write_text("not JSON")
            with self.assertRaises(ValueError):
                authority._json(path, "0" * 64, lambda *_: self.fail("gate should not be called"))

    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError):
            authority._pairs([("same", 1), ("same", 2)])

    def test_metadata_cannot_inherit_unknown_pass(self):
        with self.assertRaises(ValueError):
            authority.validate_metadata({"status": "PASS"}, {"gate_pass": True}, {})

    def test_no_scientific_imports(self):
        import subprocess
        code = "import sys; before=set(sys.modules); from src.solvers import fresh_c1b_saved_authority; added=set(sys.modules)-before; assert not any(n.split('.')[0] in {'numpy','scipy','dolfinx','petsc4py','basix','ffcx','mpi4py'} for n in added)"
        completed=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)



if __name__ == "__main__":
    unittest.main()
