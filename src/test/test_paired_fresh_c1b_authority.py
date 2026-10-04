"""Metadata-only admission/rejection tests; no NumPy, SciPy, FE or array files."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "solvers" / "paired_fresh_c1b_authority.py"
spec = importlib.util.spec_from_file_location("paired_fresh_c1b_candidate", MODULE_PATH)
authority = importlib.util.module_from_spec(spec)
spec.loader.exec_module(authority)


class SourceEnvironmentAdmission(unittest.TestCase):
    def setUp(self):
        self.before = {"head": authority.HEAD, "branch": authority.BRANCH, "dirty": "",
            "files_sha256": {"src/frozen.py": "a" * 64,
                             authority.PROVIDER_PATH: authority.PROVIDER_OLD_SHA}}
        self.after = copy.deepcopy(self.before)
        self.after["head"] = "1" * 40
        self.after["files_sha256"][authority.PROVIDER_PATH] = authority.PROVIDER_NEW_SHA
        self.env = {key: "fixed" for key in authority.ENV_FIELDS}
        self.env["qualification_manifest_sha256"] = authority.ABI_SHA
        self.env["qualification_manifest"] = "exact/manifest.json"

    def validate(self, before=None, after=None, env=None, **kwargs):
        return authority.validate_source_environment(
            self.before if before is None else before,
            self.after if after is None else after, self.env,
            self.env if env is None else env, **kwargs)

    def reject(self, **kwargs):
        with self.assertRaises(ValueError):
            self.validate(**kwargs)

    def test_exact_pair_accepted_without_mutating_sources(self):
        before, after = copy.deepcopy(self.before), copy.deepcopy(self.after)
        self.assertEqual(self.validate(), [])
        self.assertEqual(self.before, before)
        self.assertEqual(self.after, after)

    def test_explicit_new_path_accepted(self):
        self.after["files_sha256"]["src/new.py"] = "b" * 64
        self.assertEqual(self.validate(allowed_added_paths=("src/new.py",)), ["src/new.py"])

    def test_old_provider_hash_must_be_exact(self):
        self.before["files_sha256"][authority.PROVIDER_PATH] = "0" * 64
        self.reject()

    def test_new_provider_hash_must_be_exact(self):
        self.after["files_sha256"][authority.PROVIDER_PATH] = "0" * 64
        self.reject()

    def test_unmodified_provider_is_not_the_reviewed_candidate(self):
        self.after["files_sha256"][authority.PROVIDER_PATH] = authority.PROVIDER_OLD_SHA
        self.reject()

    def test_provider_cannot_disappear(self):
        del self.after["files_sha256"][authority.PROVIDER_PATH]
        self.reject()

    def test_provider_must_have_been_in_saved_source(self):
        del self.before["files_sha256"][authority.PROVIDER_PATH]
        self.reject()

    def test_other_dependency_cannot_change(self):
        self.after["files_sha256"]["src/frozen.py"] = "b" * 64
        self.reject()

    def test_other_dependency_cannot_disappear(self):
        del self.after["files_sha256"]["src/frozen.py"]
        self.reject()

    def test_added_dependency_requires_declaration(self):
        self.after["files_sha256"]["src/new.py"] = "b" * 64
        self.reject()

    def test_existing_dependency_cannot_be_allowlisted(self):
        for name in ("src/frozen.py", authority.PROVIDER_PATH):
            with self.subTest(name=name):
                self.reject(allowed_added_paths=(name,))

    def test_bad_added_paths_rejected(self):
        for name in ("../outside", "/tmp/outside", "src/../new.py", "src//new.py",
                     "src/./new.py", "src\\new.py", ".", "", 5):
            with self.subTest(name=name):
                self.reject(allowed_added_paths=(name,))

    def test_dependency_map_hashes_must_be_valid(self):
        for sha in ("invalid", "A" * 64, None, 64):
            with self.subTest(sha=sha):
                changed = copy.deepcopy(self.after)
                changed["files_sha256"]["src/new.py"] = sha
                self.reject(after=changed, allowed_added_paths=("src/new.py",))

    def test_saved_hashes_must_be_valid(self):
        self.before["files_sha256"]["src/frozen.py"] = "invalid"
        self.reject()

    def test_source_paths_cannot_be_noncanonical(self):
        self.after["files_sha256"]["src/./new.py"] = "b" * 64
        self.reject(allowed_added_paths=("src/new.py",))

    def test_new_head_must_be_valid(self):
        for head in ("short", "A" * 40, None):
            with self.subTest(head=head):
                changed = copy.deepcopy(self.after)
                changed["head"] = head
                self.reject(after=changed)

    def test_saved_head_must_be_pinned(self):
        self.before["head"] = "2" * 40
        self.reject()

    def test_branch_must_be_pinned(self):
        for which in (self.before, self.after):
            original = which["branch"]
            which["branch"] = "other"
            self.reject()
            which["branch"] = original

    def test_dirty_source_rejected(self):
        for which in (self.before, self.after):
            which["dirty"] = " M src/frozen.py"
            self.reject()
            which["dirty"] = ""

    def test_missing_clean_source_declaration_rejected(self):
        del self.after["dirty"]
        self.reject()

    def test_required_abi_change_rejected(self):
        changed = copy.deepcopy(self.env)
        changed["petsc_int_type"] = "int64"
        self.reject(env=changed)

    def test_required_abi_field_missing_rejected(self):
        changed = copy.deepcopy(self.env)
        del changed["modules"]
        self.reject(env=changed)

    def test_complete_environment_extra_field_difference_rejected(self):
        changed = copy.deepcopy(self.env)
        changed["unexpected"] = "new"
        self.reject(env=changed)

    def test_complete_environment_unlisted_field_difference_rejected(self):
        changed = copy.deepcopy(self.env)
        changed["qualification_manifest"] = "another/manifest.json"
        self.reject(env=changed)

    def test_complete_environment_unlisted_field_missing_rejected(self):
        changed = copy.deepcopy(self.env)
        del changed["qualification_manifest"]
        self.reject(env=changed)

    def test_complete_environment_nested_difference_rejected(self):
        self.env["modules"] = {"nested": {"version": "one"}}
        changed = copy.deepcopy(self.env)
        changed["modules"]["nested"]["version"] = "two"
        self.reject(env=changed)

    def test_complete_environment_type_difference_rejected(self):
        self.env["additional"] = 1
        changed = copy.deepcopy(self.env)
        changed["additional"] = True
        self.reject(env=changed)


class ReaderMetadataRejections(unittest.TestCase):
    def test_missing_allocation_gate_rejected_before_metadata(self):
        with self.assertRaises(ValueError):
            authority.PairedFreshC1bAuthority(".", new_source={}, new_environment={},
                allocation_gate=None, worker_library_receipt="missing", checker_library_receipt="missing")

    def test_q_outside_explicit_four_integers_rejected_before_reader_state(self):
        for q in (-1, 4, True, False, 0.0, "0", None):
            with self.subTest(q=q), self.assertRaises(ValueError):
                authority.PairedFreshC1bAuthority.q_block(None, q)

    def test_q_dispatch_uses_complete_fixed_shape(self):
        class Dispatch:
            def load_csr(self, *args):
                return args
        for q, shape in enumerate(authority.Q_SHAPES):
            self.assertEqual(authority.PairedFreshC1bAuthority.q_block(Dispatch(), q),
                             (f"q_{q}_S", shape))

    def test_wrong_q_width_rejected_before_payload_access(self):
        for q, shape in enumerate(authority.Q_SHAPES):
            with self.subTest(q=q), self.assertRaises(ValueError):
                authority.PairedFreshC1bAuthority.load_csr(None, f"q_{q}_S", (shape[0], shape[1]-1))

    def test_unapproved_csr_rejected_before_payload_access(self):
        for prefix in ("q_4_S", "other", "q_0", "q_00_S"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                authority.PairedFreshC1bAuthority.load_csr(None, prefix)

    def test_q_csr_cannot_be_reinterpreted_as_csc(self):
        for q in range(4):
            with self.subTest(q=q), self.assertRaises(ValueError):
                authority.PairedFreshC1bAuthority.load_csr(None, f"q_{q}_S", csc=True)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            for relative in ("../outside", "/tmp/outside", "missing"):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    authority.bound_path(root, relative)

    def test_metadata_hash_checked_before_gate_and_parse(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "metadata.json"
            path.write_text("not JSON")
            with self.assertRaises(ValueError):
                authority._json(path, "0" * 64, lambda *_: self.fail("gate called before hash"))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):
            authority._pairs([("same", 1), ("same", 2)])

    def test_unknown_metadata_pass_rejected(self):
        with self.assertRaises(ValueError):
            authority.validate_metadata({"status": "PASS"}, {"gate_pass": True}, {})

    def test_no_scientific_imports_or_activation_on_module_import(self):
        code = ("import importlib.util,sys; before=set(sys.modules); "
                "spec=importlib.util.spec_from_file_location('paired_candidate',sys.argv[1]); "
                "mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
                "added=set(sys.modules)-before; "
                "assert not any(n.split('.')[0] in {'numpy','scipy','dolfinx','petsc4py',"
                "'slepc4py','basix','ffcx','mpi4py'} for n in added)")
        result = subprocess.run([sys.executable, "-c", code, str(MODULE_PATH)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class SparseAdmissionRejections(unittest.TestCase):
    """Structural array stand-ins prove rejection precedes SciPy and allocation."""
    class Array:
        def __init__(self, length, dtype, samples):
            self.length, self.dtype, self.samples = length, dtype, samples
            self.ndim = 1

        def __len__(self):
            return self.length

        def __iter__(self):
            return iter(self.samples)

        def __getitem__(self, key):
            if isinstance(key, slice):
                return self.samples[key]
            return self.samples[key]

    def setUp(self):
        q, self.shape = 2, authority.Q_SHAPES[2]
        self.prefix, self.nnz = f"q_{q}_S", authority.Q_NNZ[q]
        self.arrays = {"data": self.Array(self.nnz, "complex128", [0j]),
                       "indices": self.Array(self.nnz, "int32", [0]),
                       "indptr": self.Array(self.shape[0]+1, "int32", [0, self.nnz])}

    def reject(self):
        test = self
        class Reader:
            def load(self, name):
                return test.arrays[name.rsplit("_", 1)[-1]]

            def allocation_gate(self, *_):
                test.fail("malformed sparse metadata reached constructor allocation")
        with self.assertRaises(ValueError):
            authority.PairedFreshC1bAuthority.load_csr(Reader(), self.prefix)

    def test_wrong_q_nnz_rejected(self):
        self.arrays["data"].length -= 1
        self.arrays["indices"].length -= 1
        self.arrays["indptr"].samples[-1] -= 1
        self.reject()

    def test_index_at_full_width_rejected(self):
        self.arrays["indices"].samples = [self.shape[1]]
        self.reject()

    def test_negative_index_rejected(self):
        self.arrays["indices"].samples = [-1]
        self.reject()

    def test_nonmonotone_offsets_rejected(self):
        self.arrays["indptr"].samples = [0, self.nnz, self.nnz-1, self.nnz]
        self.reject()

    def test_wrong_offsets_length_rejected(self):
        self.arrays["indptr"].length -= 1
        self.reject()

    def test_wrong_data_dtype_rejected(self):
        self.arrays["data"].dtype = "float64"
        self.reject()

    def test_wrong_index_dtype_rejected(self):
        self.arrays["indices"].dtype = "int64"
        self.reject()

    def test_multidimensional_array_rejected(self):
        self.arrays["data"].ndim = 2
        self.reject()


if __name__ == "__main__":
    unittest.main()
