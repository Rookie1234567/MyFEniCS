"""Focused X/XZ metadata and startup guards; no numerical modules imported.

Only stdlib AST extraction and explicit synthetic descriptor fixtures run.
These tests prove admission behavior, never FE or numerical qualification.
"""
from pathlib import Path
from types import ModuleType, SimpleNamespace
from collections.abc import Mapping
import ast
import copy
import hashlib
import json
import subprocess
import sys
import unittest


BASE = "2a07d23d17b527675e6ae0b904c56121e258b4fc"
ROOT = Path(__file__).resolve().parents[2]
SOLVERS = ROOT / "src/solvers"
CANONICAL = ROOT if (ROOT / ".git").exists() else ROOT.parents[2] / "repo"
MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"


class RemoveImports(ast.NodeTransformer):
    def visit_Import(self, node):
        return None

    def visit_ImportFrom(self, node):
        return None


def definition(name, function):
    return next(node for node in ast.parse((SOLVERS / name).read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == function)


def isolated(nodes, namespace):
    tree = ast.Module(body=copy.deepcopy(nodes), type_ignores=[])
    tree = ast.fix_missing_locations(RemoveImports().visit(tree))
    exec(compile(tree, "<stdlib-only XZ admission contract>", "exec"), namespace)
    return namespace


def metadata_module():
    module = ModuleType("_xz_profile_contract_metadata")
    sys.modules[module.__name__] = module
    path = SOLVERS / "y_orbit_direct_profile.py"
    exec(compile(ast.parse(path.read_text()), str(path), "exec"), module.__dict__)
    return module


def fixture_support(profile, twist):
    """Reuse existing synthetic descriptors with the actual profile metadata."""
    source = ROOT / "src/test/test_y_orbit_direct_raw_observer_metadata.py"
    names = {"FakeArray", "FakeGeometry", "FakeConfig", "canonical", "signature",
             "fake_file_sha", "synthetic_fixture"}
    nodes = [copy.deepcopy(node) for node in ast.parse(source.read_text()).body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]

    class ProfileFixture(ast.NodeTransformer):
        def visit_Assign(self, node):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names == {"axes"}:
                node.value = ast.parse("metadata_source.global_axes", mode="eval").body
            elif names == {"metadata"}:
                node.value = ast.Name(id="metadata_source", ctx=ast.Load())
            elif any(isinstance(target, ast.Tuple) and
                     all(isinstance(part, ast.Name) for part in target.elts) and
                     [part.id for part in target.elts] == ["cells", "rows", "independent"]
                     for target in node.targets):
                node.value = ast.parse(
                    "(metadata.cell_count, metadata.storage_rows, metadata.independent_rows) if twist is None "
                    "else (metadata.local_cell_count, metadata.local_storage_rows, metadata.local_independent_rows)",
                    mode="eval").body
            return self.generic_visit(node)

        def visit_Constant(self, node):
            if node.value == "X":
                return ast.copy_location(ast.Name(id="profile_name", ctx=ast.Load()), node)
            return node

    namespace = {"SimpleNamespace": SimpleNamespace, "Path": Path, "hashlib": hashlib,
                 "json": json, "sys": sys, "copy": copy, "MANIFEST": MANIFEST,
                 "metadata_source": profile, "profile_name": profile.name}
    isolated([ProfileFixture().visit(node) for node in nodes], namespace)
    metadata, values = namespace["synthetic_fixture"](twist)
    physical = values["cfg"] if twist is None else values["physical_cfg"]
    scale = 7.0 / 135.0
    for name, value in {
        "mesh_cell_type": "hexahedron", "geometry_kind": "rectangular_block_grating",
        "cell_notch": None, "air_void_box_nm": None, "lambda0": .7,
        "incident_phi_deg": 5.0, "stage4_dtn_order_policy": "manual",
        "diffraction_zero_order_only": False, "diffraction_order_max_m": 9,
        "diffraction_order_max_n": 3, "period_x": 50 * scale, "period_y": 25 * scale,
        "grating_width_x": 17 * scale, "grating_width_y": 25 * scale,
        "grating_height": 120 * scale, "z_min": -10 * scale, "z_max": 130 * scale,
    }.items():
        setattr(physical, name, value)
    return metadata, values, namespace


def admission_namespace(profile_module, fixture_namespace):
    helper = SOLVERS / "y_orbit_raw_observer_admission.py"
    names = {"validate_direct_raw_observer_profile", "direct_raw_observer_expected_local_cells"}
    nodes = [node for node in ast.parse(helper.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    fake_array = fixture_namespace["FakeArray"]

    def values(value):
        return value.values if isinstance(value, fake_array) else value

    namespace = {
        "Mapping": Mapping, "Path": Path, "hashlib": hashlib, "sys": sys,
        "__file__": str(helper), "SCHEMA": "task40extra.direct-X-raw-observer-admission.v1",
        "_file_sha256": fixture_namespace["fake_file_sha"],
        "_array_signature": fixture_namespace["signature"],
        "_canonical_json_bytes": fixture_namespace["canonical"],
        "DirectTwoCellProfile": profile_module.DirectTwoCellProfile,
        "direct_profile_metadata": profile_module.direct_profile_metadata,
        "validate_direct_physical_config": profile_module.validate_direct_physical_config,
        "PHYSICAL_GENERATOR_SHA256": MANIFEST,
        "package_version": lambda name: "fixture " + name,
        "np": SimpleNamespace(__version__="fixture numpy", asarray=lambda value: value,
            unique=lambda value: sorted(set(values(value))),
            array_equal=lambda left, right: list(values(left)) == list(values(right)),
            dtype=lambda value: value),
        "basix": SimpleNamespace(__version__="fixture basix"),
        "dolfinx": SimpleNamespace(__version__="fixture dolfinx"),
        "ffcx": SimpleNamespace(__version__="fixture ffcx"),
        "PETSc": SimpleNamespace(ScalarType="complex128", IntType="int32",
            Sys=SimpleNamespace(getVersion=lambda: (3, 23, 4))),
    }
    return isolated(nodes, namespace)


class XZProfileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile_module = metadata_module()

    def fixture(self, profile="XZ", twist=None):
        metadata = self.profile_module.direct_profile_metadata(profile)
        metadata, values, support = fixture_support(metadata, twist)
        return metadata, values, support, admission_namespace(self.profile_module, support)

    def test_exact_XZ_complete_metadata_and_unchanged_factor_policy(self):
        profile = self.profile_module.direct_profile_metadata("XZ")
        self.assertEqual(profile.dimensions, (6, 4, 7))
        self.assertEqual((profile.cell_count, profile.storage_rows, profile.independent_rows,
                          profile.interior_rows, profile.trace_rows), (168, 35332, 33024, 18144, 14880))
        self.assertEqual((profile.local_cell_count, profile.local_storage_rows,
                          profile.local_independent_rows, profile.local_interior_rows,
                          profile.local_trace_rows), (84, 18364, 16512, 9072, 7440))
        self.assertEqual((profile.rows_per_q, profile.trace_rows_per_q), (8256, 3720))
        self.assertEqual(profile.augmented_rows_per_q, (3796, 3872, 3872, 3872))
        self.assertEqual(profile.q_port_counts, (76, 152, 152, 152))
        self.assertEqual(profile.sector_port_counts, (228, 304))
        self.assertEqual(profile.factor_allowance_aggregate_bytes, 512 * 1024**2)
        self.assertEqual(profile.factor_allowance_per_q_bytes, 128 * 1024**2)
        self.assertEqual(profile.evidence_reserve_bytes, 128 * 1024**2)
        self.assertEqual(profile.global_axes[2], tuple(value * (7 / 135)
                         for value in (-10, 0, 20, 40, 80, 100, 120, 130)))
        self.assertEqual(profile.identity()["qualification"], "derived_metadata_NOT_RUN")

    def test_X_and_XZ_global_and_both_local_actual_inventory_guards(self):
        for name in ("X", "XZ"):
            for twist in (None, 0, 1):
                with self.subTest(profile=name, twist=twist):
                    metadata, values, _, namespace = self.fixture(name, twist)
                    receipt = namespace["validate_direct_raw_observer_profile"](name, **values)
                    self.assertEqual(receipt["profile"], name)
                    self.assertEqual(receipt["actual_cells"],
                                     metadata.cell_count if twist is None else metadata.local_cell_count)
                    self.assertEqual(receipt["actual_storage_rows"],
                                     metadata.storage_rows if twist is None else metadata.local_storage_rows)
                    self.assertFalse(receipt["numerical_qualification_performed"])
                    self.assertFalse(receipt["assembly_or_cutoff_changed"])
                    if twist is not None:
                        self.assertEqual(namespace["direct_raw_observer_expected_local_cells"](
                            values["quotient_context"], values["cfg"]), metadata.local_cell_count)

    def test_Y_unknown_nonliteral_and_cross_profile_raw_admission_rejected(self):
        _, values, _, namespace = self.fixture()
        helper = namespace["validate_direct_raw_observer_profile"]
        for name in ("Y", "x", "xz", "", None, True, 1, self.profile_module.DirectTwoCellProfile.XZ):
            with self.subTest(profile=name), self.assertRaises(ValueError):
                helper(name, **values)
        with self.assertRaises(ValueError):
            helper("X", **values)

    def test_XZ_wrong_global_and_local_actual_cfg_or_mesh_rejected(self):
        for twist in (None, 0, 1):
            for mutation in ("cells", "rows", "global_rows", "range", "mpi", "basis", "degree",
                             "axes", "cfg_counts", "mode_policy", "physical_geometry", "slaves"):
                metadata, values, support, namespace = self.fixture(twist=twist)
                space = values["mpc"].function_space
                physical = values["cfg"] if twist is None else values["physical_cfg"]
                if mutation == "cells":
                    space.mesh.topology.index_map = lambda dimension: SimpleNamespace(size_local=120)
                elif mutation == "rows": space.dofmap.index_map.size_local -= 1
                elif mutation == "global_rows": space.dofmap.index_map.size_global -= 1
                elif mutation == "range": space.dofmap.index_map.local_range = (0, metadata.storage_rows - 1)
                elif mutation == "mpi": space.mesh.comm.size = 2
                elif mutation == "basis": space.element.space_dimension = 299
                elif mutation == "degree": space.element.basix_element.degree = 2
                elif mutation == "axes": space.mesh.geometry.x.axes = ((0.,),) + space.mesh.geometry.x.axes[1:]
                elif mutation == "cfg_counts": values["cfg"].mesh_axis_cell_counts = (6, 2 if twist is not None else 4, 5)
                elif mutation == "mode_policy": physical.diffraction_order_max_n = 2
                elif mutation == "physical_geometry": physical.grating_height = 120
                else: values["mpc"].slaves = support["FakeArray"]([], "missing slaves")
                with self.subTest(twist=twist, mutation=mutation), self.assertRaises(ValueError):
                    namespace["validate_direct_raw_observer_profile"]("XZ", **values)

    def test_XZ_context_hash_Gauss_source_ABI_and_alias_mutations_rejected(self):
        for mutation in ("basis_hash", "MPC_hash", "cfg_hash", "geometry_hash", "orientation_hash",
                         "dofmap_hash", "source_hash", "ABI", "Gauss", "Gauss_nodes", "kernel",
                         "manifest", "aliases", "local_profile", "twist", "local_receipt"):
            _, values, _, namespace = self.fixture(twist=0)
            context = values["assembly_context"]
            if mutation == "basis_hash": context["basix_coefficients"]["sha256"] = "wrong"
            elif mutation == "MPC_hash": context["MPC"]["coefficients"]["sha256"] = "wrong"
            elif mutation == "cfg_hash": context["config_sha256"] = "wrong"
            elif mutation == "geometry_hash": context["mesh"]["geometry_x"]["sha256"] = "wrong"
            elif mutation == "orientation_hash": context["orientation"]["sha256"] = "wrong"
            elif mutation == "dofmap_hash": context["cell_dofmap_sha256"] = "wrong"
            elif mutation == "source_hash": context["source_sha256"]["modes_3d.py"] = "wrong"
            elif mutation == "ABI": context["ABI"]["scalar"] = "float64"
            elif mutation == "Gauss": context["gauss"]["degree"] = 19
            elif mutation == "Gauss_nodes": values["surface_assemblers"][("top", 0)].compiled_gauss_identity["rules"][0]["points"]["shape"] = [143, 2]
            elif mutation == "kernel": values["surface_assemblers"][("top", 0)].compiled_gauss_identity["loaded_kernel"]["binary_sha256"] = "wrong"
            elif mutation == "manifest": values["physical_manifest_sha"] = "wrong"
            elif mutation == "aliases": values["modes"][-1] = values["modes"][0]
            elif mutation == "local_profile": values["quotient_context"].direct_profile_name = "X"
            elif mutation == "twist": values["quotient_context"].twist_index = True
            else: context["y_orbit_quotient"]["actual_local_cells"] = 60
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                namespace["validate_direct_raw_observer_profile"]("XZ", **values)

    def test_exact_enum_operator_inventory_and_negative_Y_unknown(self):
        def require(condition, message):
            if not condition: raise ValueError(message)
        namespace = isolated([definition("y_orbit_direct_operator_qualification.py", "_metadata")], {
            "_require": require, "direct_profile_metadata": self.profile_module.direct_profile_metadata,
            "DirectTwoCellProfile": self.profile_module.DirectTwoCellProfile})
        for name in ("X", "XZ", "Y"):
            self.assertEqual(namespace["_metadata"](name), self.profile_module.direct_profile_metadata(name))
        for name in ("other", "xz", "", None, True):
            with self.assertRaises(ValueError): namespace["_metadata"](name)
        changed = copy.copy(self.profile_module.direct_profile_metadata("XZ"))
        object.__setattr__(changed, "dimensions", (6, 4, 5))
        namespace["direct_profile_metadata"] = lambda profile: changed
        with self.assertRaises(ValueError): namespace["_metadata"]("XZ")

    def test_carrier_budget_receipts_exact_X_and_XZ_and_fail_closed(self):
        helper = isolated([definition("y_orbit_direct_carrier_qualification.py", "_resource_authority")],
                          {"json": json})["_resource_authority"]
        self.assertEqual(helper({}), "external min(fresh dynamic cap,1.5GiB)/600s/zeroSwap/MPI1/thread1 supervision")
        self.assertEqual(helper({"QUOTIENT_RESEARCH_WALL_SECONDS": "1800", "QUOTIENT_PHASE_WALL_SECONDS": "1700"}),
                         "external min(fresh dynamic cap,1.5GiB)/1800s/zeroSwap/MPI1/thread1 supervision")
        for name, memory, wall in (("X", 2, 1800), ("XZ", 3, 4500)):
            cap = memory * 1024**3
            receipt = {"requested_memory_gib": memory, "requested_tree_cap_bytes": cap,
                       "required_cap_plus_evidence_reserve_bytes": cap + 128 * 1024**2,
                       "launch_admission_passed": True}
            environment = {"QUOTIENT_RESEARCH_MEMORY_GIB": str(memory), "QUOTIENT_RESEARCH_MEMORY_PROFILE": name,
                "QUOTIENT_RESEARCH_MEMORY_STAGE": "solve", "QUOTIENT_RESEARCH_WALL_SECONDS": str(wall),
                "QUOTIENT_RESEARCH_TREE_CAP_BYTES": str(cap), "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES": str(cap),
                "QUOTIENT_PHASE_WALL_SECONDS": str(wall - 1),
                "QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION": json.dumps(receipt)}
            self.assertEqual(helper(environment), f"external min(fresh dynamic cap,{memory}GiB)/{wall}s/zeroSwap/MPI1/thread1 supervision")
            for key, bad in (("QUOTIENT_RESEARCH_MEMORY_PROFILE", "other"), ("QUOTIENT_RESEARCH_MEMORY_GIB", "4"),
                             ("QUOTIENT_RESEARCH_MEMORY_STAGE", "prefactor"), ("QUOTIENT_RESEARCH_WALL_SECONDS", "600"),
                             ("QUOTIENT_PHASE_WALL_SECONDS", "nan"), ("QUOTIENT_PHASE_WALL_SECONDS", str(wall + 1)),
                             ("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "1"),
                             ("QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION", "null")):
                with self.subTest(profile=name, field=key), self.assertRaises(ValueError):
                    helper({**environment, key: bad})
            for key in receipt:
                broken = {**receipt, key: False if key == "launch_admission_passed" else 1}
                with self.subTest(profile=name, receipt=key), self.assertRaises(ValueError):
                    helper({**environment, "QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION": json.dumps(broken)})

    def test_none_default_guards_and_numerical_kernels_remain_exact_BASE(self):
        for name in ("fullspace_dtn_action.py", "dtn_boundary_phase_gauge.py",
                     "fullspace_same_mesh_hcurl_pmg_physical.py",
                     "y_orbit_two_cell_transport.py", "y_orbit_quotient_condensed.py"):
            old = subprocess.run(["git", "-C", str(CANONICAL), "show", BASE + ":src/solvers/" + name],
                                 check=True, capture_output=True, text=True).stdout
            current=(SOLVERS / name).read_text()
            if name=='fullspace_dtn_action.py':
                self.assertEqual(current.count('denominator*quotient_context.replication_count'),1)
                self.assertEqual(current.count('"local_H_scale_from_global_plane_H": 1/quotient_context.replication_count,'),1)
                current=current.replace('denominator*quotient_context.replication_count','denominator*2').replace('"local_H_scale_from_global_plane_H": 1/quotient_context.replication_count,','"local_H_scale_from_global_plane_H": 0.5,')
            elif name=='dtn_boundary_phase_gauge.py':
                self.assertEqual(current.count('(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*quotient_context.replication_count'),1)
                current=current.replace('(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*quotient_context.replication_count','(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*2')
            self.assertEqual(current, old, name)
        profile_tree = ast.parse((SOLVERS / "y_orbit_direct_profile.py").read_text())
        old_profile = ast.parse(subprocess.run(["git", "-C", str(CANONICAL), "show", BASE + ":src/solvers/y_orbit_direct_profile.py"], check=True, capture_output=True, text=True).stdout)
        helper = next(n for n in profile_tree.body if isinstance(n, ast.FunctionDef) and n.name == "direct_notch_box_and_count")
        profile_tree.body.remove(helper)
        owner = next(n for n in profile_tree.body if isinstance(n, ast.ClassDef) and n.name == "DirectTwoCellProfileMetadata")
        identity = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == "identity")
        return_node = next(n for n in identity.body if isinstance(n, ast.Return))
        policy_index = next(i for i,key in enumerate(return_node.value.keys) if isinstance(key, ast.Constant) and key.value == "factor_policy")
        policy = return_node.value.values[policy_index]
        self.assertIsInstance(policy, ast.IfExp)
        self.assertEqual(ast.unparse(policy.test), "self.name == 'Y'")
        self.assertEqual(policy.orelse.value, "unchanged_128MiB_per_q; Y_768MiB_aggregate_requires_review_before_numeric")
        return_node.value.values[policy_index] = policy.orelse
        self.assertEqual(ast.dump(profile_tree), ast.dump(old_profile))
        function = definition("fullspace_dtn_action.py", "build_fullspace_dtn_carrier_from_surface")
        wrapper = next(node for node in ast.walk(function) if isinstance(node, ast.If)
                       and ast.unparse(node.test) == "raw_observer_profile is None")
        for cells, modes, twist, passed in ((80, 532, None, True), (40, 228, 0, True), (40, 304, 1, True),
                                           (120, 532, None, False), (60, 228, 0, False),
                                           (168, 532, None, False), (84, 228, 0, False)):
            mesh = SimpleNamespace(topology=SimpleNamespace(index_map=lambda dimension: SimpleNamespace(size_local=cells)))
            namespace = {"mpc": SimpleNamespace(function_space=SimpleNamespace(mesh=mesh,
                element=SimpleNamespace(basix_element=SimpleNamespace(degree=4)))), "comm": SimpleNamespace(size=1),
                "modes": [None] * modes, "quotient_context": None if twist is None else SimpleNamespace(twist_index=twist),
                "_manifest_sha": MANIFEST, "PHYSICAL_GENERATOR_SHA256": MANIFEST,
                "assembly_context": {"gauss": {"degree": 23}}}
            try:
                isolated(wrapper.body, namespace)
                admitted = True
            except ValueError:
                admitted = False
            self.assertEqual(admitted, passed, (cells, modes, twist))

    def test_unknown_factor_profile_is_rejected_before_any_matrix_factor_access(self):
        tree = ast.parse((SOLVERS / "y_orbit_two_cell_inverse.py").read_text())
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FourBranchFactors")
        init = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        first = init.body[0]
        namespace = {"self": SimpleNamespace(), "direct_profile": "other",
                     "direct_profile_metadata": self.profile_module.direct_profile_metadata}
        with self.assertRaises(ValueError): isolated([first], namespace)
        for name in (None, "X", "XZ"):
            namespace.update(self=SimpleNamespace(), direct_profile=name)
            isolated([first], namespace)
            self.assertEqual(namespace["self"].nq, 4)
            self.assertEqual(namespace["self"].per_q_allowance, 128 * 1024**2)
        calls = {ast.unparse(node.func) for node in ast.walk(first) if isinstance(node, ast.Call)}
        self.assertFalse(calls.intersection({"splu", "spsolve", "csr_audit"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
