"""Standard-library metadata/source tests; no project package or FE import."""
from pathlib import Path
import ast
import copy
import json
import sys
import types
import unittest

TEST_ROOT = Path(__file__).resolve().parents[2]
if TEST_ROOT.name == "pipeline":
    STAGING = TEST_ROOT.parent
    REPO = STAGING.parents[1]/"repo"
    PIPELINE = TEST_ROOT/"src"/"solvers"
    CORE = STAGING/"core"/"src"/"solvers"
else:
    REPO = TEST_ROOT
    STAGING = TEST_ROOT
    PIPELINE = CORE = TEST_ROOT/"src"/"solvers"


def extract(path, names, namespace=None):
    tree = ast.parse(path.read_text(), filename=str(path))
    class RemoveLocalImports(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None
    nodes = [copy.deepcopy(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    tree = ast.fix_missing_locations(RemoveLocalImports().visit(ast.Module(body=nodes, type_ignores=[])))
    result = {} if namespace is None else dict(namespace)
    exec(compile(tree, str(path), "exec"), result)
    return result


def metadata_functions():
    # The profile module is explicitly pure standard library at import time.
    # Evaluate its definitions in an isolated named module to support dataclass
    # identity, rather than importing any src package or FE dependency.
    name = "_direct_carrier_metadata_contract_profile"
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(ast.parse((CORE/"y_orbit_direct_profile.py").read_text()), str(CORE/"y_orbit_direct_profile.py"), "exec"), module.__dict__)
    return module.direct_profile_metadata


class DirectCarrierMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = staticmethod(metadata_functions())
        source = ast.parse((REPO/"src"/"solvers"/"y_orbit_raw_packet_spool.py").read_text())
        constants = {}
        for node in source.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in
                   ("METADATA_FIELDS", "OBSERVER_SCHEMA", "MODE_COUNTS") for target in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "<constants>", "exec"), constants)
        cls.old = staticmethod(extract(REPO/"src"/"solvers"/"y_orbit_raw_packet_spool.py", {"_profile_errors"}, constants)["_profile_errors"])
        constants["direct_profile_metadata"] = cls.profile
        cls.new = staticmethod(extract(PIPELINE/"y_orbit_raw_packet_spool.py", {"_profile_errors"}, constants)["_profile_errors"])
        cls.fields = constants["METADATA_FIELDS"]

    def packet(self, twist=None, n=17204, original_n=0):
        packet = {field: None for field in self.fields}
        packet.update(schema="task40extra.dtn-raw-mode-observer.research.v1", local_mode_index=0,
                      original_mode_index=0, quotient_twist_index=twist,
                      original_mode_key=("top", 0, original_n, "s"),
                      local_branch_index=None if twist is None else 0,
                      quotient_contract_sha256=None if twist is None else "bounded-context",
                      ownership_range=(0, n), single_D_conjugation=True,
                      raw_vectors_destroyed_before_callback=True)
        return packet

    def test_default_profile_exact_old_behavior(self):
        samples = [self.packet(), self.packet(0, 8940), self.packet(1, 8940, 1)]
        for field, value in (("ownership_range", (0, 25468)), ("quotient_twist_index", 2),
                             ("local_branch_index", 1), ("original_mode_index", 532),
                             ("raw_vectors_destroyed_before_callback", False), ("local_mode_index", True)):
            item = self.packet()
            item[field] = value
            samples.append(item)
        # Exact legacy classifications frozen from canonical HEAD3570347;
        # remain meaningful after these tests migrate beside guarded sources.
        expected = [[], [], [], ["bounded MPI1 p4 owned storage is required"],
                    ["only global or two quotient twists are supported", "local branch must be explicit 0 or 1",
                     "quotient contract hash is required", "bounded MPI1 p4 owned storage is required"],
                    ["global observer mapping must retain the original contiguous index"],
                    ["original index is missing, duplicated, or out of range",
                     "global observer mapping must retain the original contiguous index"],
                    ["existing observer conjugation/lifecycle proof is required"],
                    ["local indices must be unique contiguous integers",
                     "global observer mapping must retain the original contiguous index"]]
        for packet, errors in zip(samples, expected):
            self.assertEqual(self.old(packet, next_index=0, original_indices=set()), errors)
            self.assertEqual(self.new(packet, next_index=0, original_indices=set()), errors)

    def test_X_exact_storage_and_branches(self):
        metadata = self.profile("X")
        self.assertEqual((metadata.cell_count, metadata.storage_rows, metadata.independent_rows, metadata.interior_rows),
                         (120, 25468, 23808, 12960))
        self.assertEqual((metadata.local_cell_count, metadata.local_storage_rows, metadata.local_independent_rows,
                          metadata.local_interior_rows), (60, 13236, 11904, 6480))
        self.assertEqual(metadata.sector_port_counts, (228, 304))
        for twist, n, original_n in ((None, metadata.storage_rows, 0), (0, metadata.local_storage_rows, 0),
                                    (1, metadata.local_storage_rows, 1)):
            packet = self.packet(twist, n, original_n)
            self.assertEqual(self.new(packet, next_index=0, original_indices=set(), direct_profile="X"), [])
            self.assertTrue(self.new(packet, next_index=0, original_indices=set()))
            packet["ownership_range"] = (0, n-1)
            self.assertTrue(self.new(packet, next_index=0, original_indices=set(), direct_profile="X"))

    def test_XZ_Y_metadata_only_no_numeric_admission(self):
        self.assertEqual(self.profile("XZ").dimensions, (6, 4, 7))
        metadata = self.profile("Y")
        self.assertEqual(metadata.dimensions, (4, 6, 5))
        self.assertEqual(metadata.replication_count, 3)
        self.assertEqual(self.new(self.packet(2, metadata.local_storage_rows, 2), next_index=0,
                                  original_indices=set(), direct_profile="Y"), [])
        packet = self.packet(2, metadata.local_storage_rows, 2)
        packet["local_branch_index"] = 1
        self.assertTrue(self.new(packet, next_index=0, original_indices=set(), direct_profile="Y"))
        for name in ("", "x", "same80", None):
            with self.assertRaises(ValueError):
                self.profile(name)

    def test_entry_signatures_and_import_only_standard_library(self):
        expected = {"dtn_boundary_plane_qualification.py": "qualify_boundary_plane_bundle",
                    "y_orbit_quotient_raw_qualification.py": "qualify_quotient_raw_bundle"}
        for file, function in expected.items():
            tree = ast.parse((PIPELINE/file).read_text())
            node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == function)
            keyword_names = [arg.arg for arg in node.args.kwonlyargs]
            self.assertIn("direct_profile", keyword_names)
            self.assertIsNone(node.args.kw_defaults[keyword_names.index("direct_profile")].value)
            self.assertIn("literal_mode_observer", keyword_names)
            self.assertIsNone(node.args.kw_defaults[keyword_names.index("literal_mode_observer")].value)
        tree = ast.parse((PIPELINE/"y_orbit_direct_carrier_qualification.py").read_text())
        allowed = {"__future__", "dataclasses", "pathlib", "typing", "hashlib", "json"}
        for node in tree.body:
            if isinstance(node, ast.Import):
                self.assertTrue({alias.name for alias in node.names} <= allowed)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
        function = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "build_fresh_direct_carriers")
        names = [arg.arg for arg in function.args.kwonlyargs]
        self.assertIn("shared_template_bank", names)
        self.assertIsNone(function.args.kw_defaults[names.index("shared_template_bank")])
        owner = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "DirectCarrierQualification")
        self.assertTrue(any(isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
                            and item.target.id == "global_mode_inventory" for item in owner.body))
        assignment = [item for item in ast.walk(function) if isinstance(item, ast.Assign)
                      and any(isinstance(target, ast.Attribute) and target.attr == "global_mode_inventory"
                              for target in item.targets)]
        self.assertEqual(len(assignment), 1)
        self.assertIsInstance(assignment[0].value, ast.Name)
        self.assertEqual(assignment[0].value.id, "inventory")
        destructor = next(item for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == "destroy")
        self.assertTrue(any(isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant)
                            and item.value.value is None
                            and any(isinstance(target, ast.Attribute) and target.attr == "global_mode_inventory"
                                    for target in item.targets) for item in ast.walk(destructor)))
        text = (PIPELINE/"y_orbit_direct_carrier_qualification.py").read_text()
        self.assertIn('is not DirectTwoCellProfile.X', text)
        self.assertNotIn('authority.restore_bundle', text)
        self.assertNotIn('splu(', text)
        self.assertNotIn('np.save(', text)

    def test_literal_control_metadata_has_no_numeric_execution(self):
        tree = ast.parse((PIPELINE/"y_orbit_direct_carrier_qualification.py").read_text())
        collector = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "DirectLiteralModeSpool")
        text = ast.unparse(collector)
        self.assertIn("task40extra.direct-literal-current-mode-spool.v1", text)
        self.assertIn("every exact nonzero; no magnitude cutoff", text)
        self.assertIn("literal_binding_sha256", text)
        self.assertIn("literal_payload", text)
        self.assertIn("frozen_literal_binding", text)
        self.assertIn("literal_controls_qualified", text)
        self.assertNotIn("_mask(", text)
        self.assertNotIn("_assemble", text)
        self.assertIn('vector != 0', text)
        function = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "build_fresh_direct_carriers")
        names = [arg.arg for arg in function.args.kwonlyargs]
        self.assertIn("entity_callback", names)
        self.assertIn("layout_callback", names)
        literal_calls = [call for call in ast.walk(function) if isinstance(call, ast.Call) and any(
            keyword.arg == "literal_mode_observer" for keyword in call.keywords)]
        self.assertEqual(len(literal_calls), 2)

    def test_syntax_and_no_baked_arrays(self):
        for path in PIPELINE.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
        self.assertFalse(list((STAGING/"pipeline").rglob("*.npy")))
        self.assertFalse(list((STAGING/"pipeline").rglob("*.npz")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
