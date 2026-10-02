"""Stdlib-only direct-X observer admission and protected-default AST tests.

Numerical modules are never imported. Only isolated guard/helper definitions
are evaluated with synthetic metadata and explicit dependency stubs.
"""
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Mapping
import ast
import copy
import hashlib
import json
import subprocess
import sys
import unittest

BASE = "23fc05cd1bbf2e2b053fab6955eeccedfced6805"
ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]/"repo" if ROOT.name == "y_orbit_direct_raw_observer_fix" else ROOT
SOLVERS = ROOT/"src/solvers"
MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"


def baseline(name):
    return subprocess.run(["git", "-C", str(REPO), "show", BASE+":src/solvers/"+name],
        check=True, capture_output=True, text=True).stdout


def definition(source, name):
    return next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)


def dump(node):
    return ast.dump(node, include_attributes=False)


def old_guard(function):
    return next(node for node in ast.walk(function) if isinstance(node, ast.If)
        and "raw_mode_observer" in ast.unparse(node.test)
        and "80-cell p4 authority" in ast.unparse(node))


class StripDirectExtension(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if "raw_observer_profile" in [arg.arg for arg in node.args.kwonlyargs]:
            pairs = [(arg, default) for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
                     if arg.arg != "raw_observer_profile"]
            node.args.kwonlyargs, node.args.kw_defaults = [item[0] for item in pairs], [item[1] for item in pairs]
        return self.generic_visit(node)

    def visit_Call(self, node):
        node.keywords = [keyword for keyword in node.keywords if keyword.arg != "raw_observer_profile"]
        return self.generic_visit(node)

    def visit_If(self, node):
        names = {member.id for member in ast.walk(node.test) if isinstance(member, ast.Name)}
        if "raw_observer_profile" in names and "raw_mode_observer" in names:
            return None
        if ast.unparse(node.test) == "quotient_context.direct_profile_name is not None":
            return None
        if (names == {"raw_observer_profile"} and isinstance(node.test, ast.Compare)
                and isinstance(node.test.ops[0], ast.Is) and isinstance(node.test.comparators[0], ast.Constant)
                and node.test.comparators[0].value is None):
            return [self.visit(member) for member in node.body]
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if any(isinstance(target, ast.Name) and target.id == "expected_local_cells" for target in node.targets):
            return None
        return self.generic_visit(node)

    def visit_Name(self, node):
        if node.id == "expected_local_cells" and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Constant(value=40), node)
        return node


class RemoveLocalImports(ast.NodeTransformer):
    def visit_Import(self, node):
        return None

    def visit_ImportFrom(self, node):
        return None


def execute_statements(statements, namespace):
    module = ast.Module(body=copy.deepcopy(statements), type_ignores=[])
    module = ast.fix_missing_locations(RemoveLocalImports().visit(module))
    exec(compile(module, "<isolated stdlib metadata guard>", "exec"), namespace)


def guard_namespace(cells, mode_count, twist=None):
    mesh = SimpleNamespace(comm=SimpleNamespace(size=1),
        topology=SimpleNamespace(index_map=lambda dimension: SimpleNamespace(size_local=cells)))
    space = SimpleNamespace(mesh=mesh, element=SimpleNamespace(basix_element=SimpleNamespace(degree=4)))
    return {"raw_mode_observer": lambda packet: None, "raw_observer_profile": None,
        "mpc": SimpleNamespace(function_space=space), "comm": mesh.comm, "modes": [None]*mode_count,
        "quotient_context": None if twist is None else SimpleNamespace(twist_index=twist),
        "_manifest_sha": MANIFEST, "PHYSICAL_GENERATOR_SHA256": MANIFEST,
        "assembly_context": {"gauss": {"degree": 23}}}


class ProtectedObserverSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = {
            "fullspace_dtn_action.py": "build_fullspace_dtn_carrier_from_surface",
            "fullspace_same_mesh_hcurl_pmg_physical.py": "build_same_mesh_physical_action",
            "y_orbit_direct_carrier_qualification.py": "build_fresh_direct_carriers",
            "dtn_boundary_phase_gauge.py": "build_gauge_assembly_context"}
        cls.old = {name: definition(baseline(name), function) for name, function in cls.functions.items()}
        cls.new = {name: definition((SOLVERS/name).read_text(), function) for name, function in cls.functions.items()}

    def test_protected_function_default_ASTs_exact(self):
        for name, old in self.old.items():
            new = StripDirectExtension().visit(copy.deepcopy(self.new[name]))
            if name == "y_orbit_direct_carrier_qualification.py":
                # The separately reviewed budget change touches receipt text
                # only. Restore exactly its known import/value, then retain
                # this whole-function comparison for every numerical node.
                marker = ast.parse("from os import environ").body[0]
                removed = 0
                for parent in ast.walk(new):
                    for _field, values in ast.iter_fields(parent):
                        if isinstance(values, list):
                            for index in range(len(values)-1, -1, -1):
                                if isinstance(values[index], ast.ImportFrom) and dump(values[index]) == dump(marker):
                                    del values[index]; removed += 1
                self.assertEqual(removed, 1)
                old_value = next(value for node in ast.walk(old) if isinstance(node, ast.Dict)
                                 for key, value in zip(node.keys, node.values)
                                 if isinstance(key, ast.Constant) and key.value == "resource_authority")
                restored = 0
                for node in ast.walk(new):
                    if isinstance(node, ast.Dict):
                        for index, key in enumerate(node.keys):
                            if isinstance(key, ast.Constant) and key.value == "resource_authority":
                                self.assertEqual(dump(node.values[index]), dump(ast.parse("_resource_authority(environ)", mode="eval").body))
                                node.values[index] = copy.deepcopy(old_value); restored += 1
                self.assertEqual(restored, 1)
            self.assertEqual(dump(new), dump(old), name)

    def test_legacy_raw_guard_body_is_verbatim_None_branch(self):
        old = old_guard(self.old["fullspace_dtn_action.py"])
        new = old_guard(self.new["fullspace_dtn_action.py"])
        wrapper = next(node for node in new.body if isinstance(node, ast.If)
            and ast.unparse(node.test) == "raw_observer_profile is None")
        self.assertEqual([dump(node) for node in wrapper.body], [dump(node) for node in old.body])
        calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "validate_direct_raw_observer_profile"]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual([ast.unparse(node) for node in call.args], ["raw_observer_profile"])
        self.assertEqual({keyword.arg for keyword in call.keywords}, {"modes", "mpc", "cfg", "assembly_context",
            "physical_cfg", "quotient_context", "physical_manifest_sha", "surface_assemblers"})

    def test_default_80_40_guard_accepts_and_rejects_exact_old_cases(self):
        old = old_guard(self.old["fullspace_dtn_action.py"])
        new = old_guard(self.new["fullspace_dtn_action.py"])
        for cells, count, twist, passed in ((80, 532, None, True), (40, 228, 0, True), (40, 304, 1, True),
            (120, 532, None, False), (60, 228, 0, False), (60, 304, 1, False), (80, 80, None, False)):
            outcomes = []
            for node in (old, new):
                namespace = guard_namespace(cells, count, twist)
                try:
                    execute_statements(node.body, namespace)
                    outcomes.append(True)
                except ValueError:
                    outcomes.append(False)
            self.assertEqual(outcomes, [passed, passed])

    def test_profile_without_observer_rejected_before_assembly(self):
        for name in ("fullspace_dtn_action.py", "fullspace_same_mesh_hcurl_pmg_physical.py"):
            function = self.new[name]
            keyword_names = [arg.arg for arg in function.args.kwonlyargs]
            self.assertIn("raw_observer_profile", keyword_names)
            default = function.args.kw_defaults[keyword_names.index("raw_observer_profile")]
            self.assertIsInstance(default, ast.Constant)
            self.assertIsNone(default.value)
            rejection = next(node for node in function.body if isinstance(node, ast.If)
                and "raw_observer_profile" in ast.unparse(node.test) and "raw_mode_observer" in ast.unparse(node.test))
            prefix = function.body[:function.body.index(rejection)+1]
            self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in {"_surface_assemblers", "components_for", "_build_split_volume_action"}
                for statement in prefix for node in ast.walk(statement)))
            for value in ("X", "XZ", "Y", True, "", 1):
                namespace = {"raw_observer_profile": value, "raw_mode_observer": None, "mpc": object(),
                    "validate_phase_gauge": lambda value: None, "phase_gauge": "boundary_plane", "dtn_phase_gauge": "boundary_plane",
                    "BOUNDARY_PLANE": "boundary_plane"}
                with self.assertRaises(ValueError): execute_statements(prefix, namespace)

    def test_global_and_local_forwarding_is_explicit(self):
        physical = self.new["fullspace_same_mesh_hcurl_pmg_physical.py"]
        calls = [node for node in ast.walk(physical) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "build_fullspace_dtn_carrier_from_surface"]
        self.assertEqual(len(calls), 3)
        observer_calls = [node for node in calls if any(keyword.arg == "raw_mode_observer" for keyword in node.keywords)]
        self.assertEqual(len(observer_calls), 2)
        for call in observer_calls:
            value = next(keyword.value for keyword in call.keywords if keyword.arg == "raw_observer_profile")
            self.assertEqual(ast.unparse(value), "raw_observer_profile")
        direct = self.new["y_orbit_direct_carrier_qualification.py"]
        calls = [node for node in ast.walk(direct) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "build_same_mesh_physical_action"]
        self.assertEqual(len(calls), 2)
        for call in calls:
            value = next(keyword.value for keyword in call.keywords if keyword.arg == "raw_observer_profile")
            self.assertEqual(ast.literal_eval(value), "X")

    def test_context_local40_default_and_X_local60_seam(self):
        function = self.new["dtn_boundary_phase_gauge.py"]
        assigns = [node for node in ast.walk(function) if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "expected_local_cells" for target in node.targets)]
        self.assertEqual(len(assigns), 2)
        self.assertEqual(ast.literal_eval(assigns[0].value), 40)
        self.assertEqual(ast.unparse(assigns[1].value), "direct_raw_observer_expected_local_cells(quotient_context, cfg)")
        wrapper = next(node for node in ast.walk(function) if isinstance(node, ast.If)
            and ast.unparse(node.test) == "quotient_context.direct_profile_name is not None")
        self.assertTrue(any(isinstance(node, ast.Assign) and node in assigns for node in wrapper.body))
        comparisons = [node for node in ast.walk(function) if isinstance(node, ast.Compare)
            and ast.unparse(node.left) == "cell_count" and any(isinstance(part, ast.Name) and part.id == "expected_local_cells"
                for part in node.comparators)]
        self.assertEqual(len(comparisons), 1)


class FakeArray:
    """Synthetic descriptor values, not a numerical ndarray or FE object."""
    def __init__(self, values, token, kind="i", shape=None):
        self.values, self.token = list(values), token
        self.ndim, self.dtype = 1, SimpleNamespace(kind=kind)
        self.shape = tuple(shape) if shape is not None else (len(self.values),)
        self.size = len(self.values)

    def __len__(self): return len(self.values)
    def min(self): return min(self.values)
    def max(self): return max(self.values)


class FakeGeometry(FakeArray):
    def __init__(self, axes):
        super().__init__([], "actual geometry descriptor", "f", (1, 3))
        self.axes = axes

    def __getitem__(self, key):
        return FakeArray(self.axes[key[1]], "axis metadata "+str(key[1]), "f")


class FakeConfig:
    def __init__(self, axes, local=False):
        self.axes, self.local = axes, local
        self.mesh_axis_cell_counts = tuple(len(axis)-1 for axis in axes)
        for name, axis in zip(("x", "y", "z"), axes, strict=True): setattr(self, "mesh_axis_"+name+"_values", axis)
        self.nedelec_degree = 4
        self.nedelec_trace_degree = self.nedelec_interior_degree = None

    def as_jsonable(self):
        return {"axes": self.axes, "local": self.local, "degree": self.nedelec_degree}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def signature(value):
    return {"shape": list(value.shape), "token": value.token,
        "sha256": hashlib.sha256(canonical(value.values)).hexdigest()}


def fake_file_sha(path):
    return hashlib.sha256(Path(path).name.encode()).hexdigest()


def synthetic_fixture(twist=None):
    scale = 7/135
    axes = tuple(tuple(value*scale for value in axis) for axis in
        ((0, 8.25, 16.5, 25, 33.5, 41.75, 50), (0, 6.25, 12.5, 18.75, 25), (-10, 0, 40, 80, 120, 130)))
    local_axes = (axes[0], axes[1][:3], axes[2])
    metadata = SimpleNamespace(cell_count=120, storage_rows=25468, independent_rows=23808,
        local_cell_count=60, local_storage_rows=13236, local_independent_rows=11904,
        global_axes=axes, local_axes=local_axes, sector_port_counts=(228, 304), q_port_counts=(76, 152, 152, 152))
    physical_cfg = FakeConfig(axes)
    cfg = physical_cfg if twist is None else FakeConfig(local_axes, local=True)
    cells, rows, independent = (120, 25468, 23808) if twist is None else (60, 13236, 11904)
    selected_axes = axes if twist is None else local_axes
    modes = [SimpleNamespace(side=side, m=m, n=n, polarization=polarization) for side in ("top", "bottom")
        for m in range(-9, 10) for n in range(-3, 4) for polarization in ("s", "p")
        if twist is None or (n-twist)%2 == 0]
    quotient = None
    if twist is not None:
        quotient = SimpleNamespace(direct_profile_name="X", twist_index=twist, global_y_cells=4,
            replication_count=2, local_y_cells=2, global_axes=axes, local_axes=local_axes,
            physical_generator_manifest_sha256=MANIFEST,
            assembly_config_sha256=hashlib.sha256(canonical(cfg.as_jsonable())).hexdigest(),
            sha256="fixture quotient sha "+str(twist), original_mode_keys=tuple((mode.side, mode.m, mode.n, mode.polarization) for mode in modes))
        quotient.identity = lambda: {"profile": "X", "twist": quotient.twist_index, "axes": quotient.local_axes}
    geometry = FakeGeometry(selected_axes)
    geometry_dofmap = FakeArray([], "complete geometry dofmap", shape=(cells, 8))
    orientation = FakeArray([], "complete actual cell orientation", shape=(cells,))
    mesh = SimpleNamespace(comm=SimpleNamespace(size=1),
        topology=SimpleNamespace(dim=3, index_map=lambda dimension: SimpleNamespace(size_local=cells),
            get_cell_permutation_info=lambda: orientation),
        geometry=SimpleNamespace(x=geometry, dofmap=geometry_dofmap))
    index_map = SimpleNamespace(size_local=rows, size_global=rows, local_range=(0, rows))
    element = SimpleNamespace(degree=4, map_type=SimpleNamespace(name="covariantPiola"),
        coefficient_matrix=FakeArray([], "complete p4 basis descriptor", "f", (300, 300)))
    space = SimpleNamespace(mesh=mesh, element=SimpleNamespace(basix_element=element, space_dimension=300),
        dofmap=SimpleNamespace(index_map=index_map,
            cell_dofs=lambda cell: FakeArray([], "complete300 cell row metadata "+str(cell), shape=(300,))))
    coeff, offsets = FakeArray([], "finalized coefficient descriptor", "f"), FakeArray([], "finalized offsets descriptor")
    mpc = SimpleNamespace(function_space=space,
        slaves=FakeArray(range(rows-independent), "actual finalized slaves"),
        masters=SimpleNamespace(array=FakeArray([], "actual finalized masters")), coefficients=lambda: (coeff, offsets))
    rule = {"degree": 23, "facet_cell": "quadrilateral", "integral_type": "exterior_facet",
        "points": {"shape": [144, 2], "dtype": "float64"}, "weights": {"shape": [144], "dtype": "float64"},
        "compiled_weight_tables_verified": 1}
    surface = {}
    for side in ("top", "bottom"):
        for component in (0, 1):
            path = f"/synthetic_metadata/{side}_{component}.so"
            generated = f"/synthetic_metadata/{side}_{component}.c"
            identity = {"rules": [copy.deepcopy(rule)], "loaded_kernel": {"module_path": path,
                "binary_sha256": fake_file_sha(path), "module_bound_C_path": generated, "module_bound_C_sha256": fake_file_sha(generated)}}
            surface[(side, component)] = SimpleNamespace(compiled_gauss_identity=identity)
    names = ["dtn_boundary_phase_gauge.py", "dtn_port_3d.py", "fullspace_dtn_action.py",
        "fullspace_same_mesh_hcurl_pmg_physical.py", "dtn_boundary_plane_qualification.py", "modes_3d.py", "config_3d.py"]
    if twist is not None:
        names += ["y_orbit_quotient_context.py", "fullspace_same_mesh_hcurl_pmg_global.py", "y_orbit_condensed_adapter.py",
            "floquet_3d.py", "floquet_3d_high_order.py", "high_order_floquet_trace.py"]
    context = {"schema": "task40extra.dtn-plane-discrete-context.v1", "element_degree": 4,
        "element_map_type": "covariantPiola", "basix_coefficients": signature(element.coefficient_matrix),
        "MPC": {name: signature(value) for name, value in (("slaves", mpc.slaves), ("masters", mpc.masters.array),
            ("coefficients", coeff), ("offsets", offsets))},
        "config_sha256": hashlib.sha256(canonical(cfg.as_jsonable())).hexdigest(),
        "mesh": {"geometry_x": signature(geometry), "geometry_dofmap": signature(geometry_dofmap)},
        "orientation": signature(orientation),
        "cell_dofmap_sha256": hashlib.sha256(b"".join(canonical(signature(space.dofmap.cell_dofs(cell))) for cell in range(cells))).hexdigest(),
        "source_sha256": {name: fake_file_sha(name) for name in names},
        "ABI": {"python": sys.version, "numpy": "fixture numpy", "basix": "fixture basix", "dolfinx": "fixture dolfinx",
            "dolfinx_mpc": "fixture dolfinx_mpc", "ffcx": "fixture ffcx", "PETSc": (3, 23, 4), "scalar": "complex128", "integer": "int32"},
        "gauss": {"degree": 23, "compiled_forms_verified": {f"{side}/{component}": assembler.compiled_gauss_identity
            for (side, component), assembler in surface.items()}}}
    if twist is not None:
        context["y_orbit_quotient"] = {"contract_sha256": quotient.sha256, "contract": quotient.identity(),
            "actual_local_cells": cells, "actual_local_storage_rows": rows, "actual_finalized_mpc_slave_rows": rows-independent}
    values = {"modes": modes, "mpc": mpc, "cfg": cfg, "assembly_context": context,
        "physical_cfg": None if twist is None else physical_cfg, "quotient_context": quotient,
        "physical_manifest_sha": MANIFEST, "surface_assemblers": surface}
    return metadata, values


def extracted_helper(metadata):
    helper = SOLVERS/"y_orbit_raw_observer_admission.py"
    tree = ast.parse(helper.read_text())
    nodes = [copy.deepcopy(node) for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {"validate_direct_raw_observer_profile", "direct_raw_observer_expected_local_cells"}]
    module = ast.fix_missing_locations(RemoveLocalImports().visit(ast.Module(body=nodes, type_ignores=[])))
    def array_equal(left, right):
        return list(left.values if isinstance(left, FakeArray) else left) == list(right.values if isinstance(right, FakeArray) else right)
    def unique(value): return sorted(set(value.values if isinstance(value, FakeArray) else value))
    def validate_physical(cfg, profile):
        if profile != "X" or cfg is None or cfg.local or cfg.axes != metadata.global_axes or cfg.nedelec_degree != 4:
            raise ValueError("synthetic original physical configuration rejected")
        return metadata
    namespace = {"Mapping": Mapping, "Path": Path, "hashlib": hashlib, "sys": sys,
        "__file__": str(helper), "SCHEMA": "task40extra.direct-X-raw-observer-admission.v1",
        "_file_sha256": fake_file_sha, "_array_signature": signature, "_canonical_json_bytes": canonical,
        "validate_direct_physical_config": validate_physical, "direct_profile_metadata": lambda profile: metadata,
        "PHYSICAL_GENERATOR_SHA256": MANIFEST, "package_version": lambda name: "fixture "+name,
        "np": SimpleNamespace(__version__="fixture numpy", asarray=lambda value: value, unique=unique,
            array_equal=array_equal, dtype=lambda value: value),
        "basix": SimpleNamespace(__version__="fixture basix"), "dolfinx": SimpleNamespace(__version__="fixture dolfinx"),
        "ffcx": SimpleNamespace(__version__="fixture ffcx"),
        "PETSc": SimpleNamespace(ScalarType="complex128", IntType="int32", Sys=SimpleNamespace(getVersion=lambda: (3, 23, 4)))}
    exec(compile(module, str(helper), "exec"), namespace)
    return namespace


class DirectObserverAdmissionTests(unittest.TestCase):
    def run_helper(self, values, metadata):
        return extracted_helper(metadata)["validate_direct_raw_observer_profile"]("X", **values)

    def test_valid_global_and_both_actual_twists(self):
        for twist in (None, 0, 1):
            metadata, values = synthetic_fixture(twist)
            receipt = self.run_helper(values, metadata)
            self.assertEqual(receipt["actual_cells"], 120 if twist is None else 60)
            self.assertEqual(receipt["actual_storage_rows"], 25468 if twist is None else 13236)
            self.assertEqual(receipt["actual_independent_rows"], 23808 if twist is None else 11904)
            self.assertEqual(receipt["actual_mode_count"], 532 if twist is None else (228, 304)[twist])
            self.assertEqual(receipt["twist_index"], twist)
            self.assertIs(receipt["numerical_qualification_performed"], False)
            self.assertIs(receipt["assembly_or_cutoff_changed"], False)

    def test_only_literal_X_permission_is_accepted_before_local_imports(self):
        metadata, values = synthetic_fixture()
        helper = extracted_helper(metadata)["validate_direct_raw_observer_profile"]
        for profile in (None, "XZ", "Y", "x", "", True, False, 1, {"profile": "X"}):
            with self.assertRaises(ValueError): helper(profile, **values)

    def test_wrong_actual_cells_storage_basis_geometry_or_MPC_rejected(self):
        for twist in (None, 0, 1):
            for mutation in ("cells", "storage", "global_rows", "ownership", "mpi", "degree", "basis_dimension",
                "axes", "slave_count", "duplicate_slaves", "slave_range", "slave_dtype", "config"):
                metadata, values = synthetic_fixture(twist)
                space = values["mpc"].function_space
                if mutation == "cells": space.mesh.topology.index_map = lambda dimension: SimpleNamespace(size_local=80)
                elif mutation == "storage": space.dofmap.index_map.size_local -= 1
                elif mutation == "global_rows": space.dofmap.index_map.size_global += 1
                elif mutation == "ownership": space.dofmap.index_map.local_range = (1, space.dofmap.index_map.size_local+1)
                elif mutation == "mpi": space.mesh.comm.size = 2
                elif mutation == "degree": space.element.basix_element.degree = 2
                elif mutation == "basis_dimension": space.element.space_dimension = 299
                elif mutation == "axes": space.mesh.geometry.x.axes = ((0.,),)+space.mesh.geometry.x.axes[1:]
                elif mutation == "slave_count": values["mpc"].slaves = FakeArray([], "missing actual slaves")
                elif mutation == "duplicate_slaves": values["mpc"].slaves.values[-1] = values["mpc"].slaves.values[0]
                elif mutation == "slave_range": values["mpc"].slaves.values[-1] = space.dofmap.index_map.size_local
                elif mutation == "slave_dtype": values["mpc"].slaves.dtype.kind = "f"
                else: values["cfg"].mesh_axis_cell_counts = (6, 3, 5)
                with self.subTest(twist=twist, mutation=mutation), self.assertRaises(ValueError): self.run_helper(values, metadata)

    def test_actual_context_source_ABI_MPC_and_Gauss_bindings(self):
        for mutation in ("schema", "degree", "map", "basis", "MPC", "config", "geometry", "orientation", "dofs", "source",
            "ABI", "Gauss_degree", "Gauss_forms", "Gauss_nodes", "Gauss_weights", "Gauss_verification", "kernel_binary", "kernel_C"):
            metadata, values = synthetic_fixture(0)
            context, assembler = values["assembly_context"], values["surface_assemblers"][("top", 0)]
            if mutation == "schema": context["schema"] = "historical_wrong"
            elif mutation == "degree": context["element_degree"] = 2
            elif mutation == "map": context["element_map_type"] = "identity"
            elif mutation == "basis": context["basix_coefficients"]["sha256"] = "wrong"
            elif mutation == "MPC": context["MPC"]["coefficients"]["sha256"] = "wrong"
            elif mutation == "config": context["config_sha256"] = "wrong"
            elif mutation == "geometry": context["mesh"]["geometry_x"]["sha256"] = "wrong"
            elif mutation == "orientation": context["orientation"]["sha256"] = "wrong"
            elif mutation == "dofs": context["cell_dofmap_sha256"] = "wrong"
            elif mutation == "source": context["source_sha256"]["dtn_port_3d.py"] = "wrong"
            elif mutation == "ABI": context["ABI"]["scalar"] = "float64"
            elif mutation == "Gauss_degree": context["gauss"]["degree"] = 22
            elif mutation == "Gauss_forms": context["gauss"]["compiled_forms_verified"] = {}
            elif mutation == "Gauss_nodes": assembler.compiled_gauss_identity["rules"][0]["points"]["shape"] = [143, 2]
            elif mutation == "Gauss_weights": assembler.compiled_gauss_identity["rules"][0]["weights"]["dtype"] = "float32"
            elif mutation == "Gauss_verification": assembler.compiled_gauss_identity["rules"][0]["compiled_weight_tables_verified"] = 0
            elif mutation == "kernel_binary": assembler.compiled_gauss_identity["loaded_kernel"]["binary_sha256"] = "wrong"
            else: assembler.compiled_gauss_identity["loaded_kernel"]["module_bound_C_sha256"] = "wrong"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.run_helper(values, metadata)

    def test_physical_mode_hash_count_alias_order_and_context(self):
        for twist in (None, 0, 1):
            for mutation in ("mode_count", "duplicate", "manifest", "physical_cfg", "alias"):
                metadata, values = synthetic_fixture(twist)
                if mutation == "mode_count": values["modes"].pop()
                elif mutation == "duplicate": values["modes"][-1] = values["modes"][0]
                elif mutation == "manifest": values["physical_manifest_sha"] = "wrong"
                elif mutation == "physical_cfg":
                    physical = values["cfg"] if twist is None else values["physical_cfg"]
                    physical.nedelec_degree = 2
                else: values["modes"][0].n += 1
                with self.subTest(twist=twist, mutation=mutation), self.assertRaises(ValueError): self.run_helper(values, metadata)
        for mutation in ("profile", "twist", "axes", "count", "contract", "actual_local_cells", "actual_storage", "actual_slaves"):
            metadata, values = synthetic_fixture(0); quotient = values["quotient_context"]
            if mutation == "profile": quotient.direct_profile_name = "Y"
            elif mutation == "twist": quotient.twist_index = True
            elif mutation == "axes": quotient.global_axes = ()
            elif mutation == "count": quotient.replication_count = 3
            elif mutation == "contract": values["assembly_context"]["y_orbit_quotient"]["contract_sha256"] = "wrong"
            elif mutation == "actual_local_cells": values["assembly_context"]["y_orbit_quotient"]["actual_local_cells"] = 40
            elif mutation == "actual_storage": values["assembly_context"]["y_orbit_quotient"]["actual_local_storage_rows"] = 8940
            else: values["assembly_context"]["y_orbit_quotient"]["actual_finalized_mpc_slave_rows"] = 1004
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.run_helper(values, metadata)

    def test_expected_local_cells_only_explicit_X_contract(self):
        for twist in (0, 1):
            metadata, values = synthetic_fixture(twist)
            helper = extracted_helper(metadata)["direct_raw_observer_expected_local_cells"]
            self.assertEqual(helper(values["quotient_context"], values["cfg"]), 60)
        for mutation in ("profile", "twist", "local_y", "manifest", "cfg_degree", "cfg_counts", "cfg_axes", "cfg_hash"):
            metadata, values = synthetic_fixture(0)
            quotient, cfg = values["quotient_context"], values["cfg"]
            if mutation == "profile": quotient.direct_profile_name = "XZ"
            elif mutation == "twist": quotient.twist_index = 2
            elif mutation == "local_y": quotient.local_y_cells = 1
            elif mutation == "manifest": quotient.physical_generator_manifest_sha256 = "wrong"
            elif mutation == "cfg_degree": cfg.nedelec_degree = 2
            elif mutation == "cfg_counts": cfg.mesh_axis_cell_counts = (4, 2, 5)
            elif mutation == "cfg_axes": cfg.mesh_axis_x_values = (0.,)
            else: quotient.assembly_config_sha256 = "wrong"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                extracted_helper(metadata)["direct_raw_observer_expected_local_cells"](quotient, cfg)

    def test_helper_syntax_stdlib_module_imports_and_no_numerical_calls(self):
        path = SOLVERS/"y_orbit_raw_observer_admission.py"; tree = ast.parse(path.read_text())
        allowed = {"collections.abc", "importlib.metadata", "pathlib", "hashlib", "sys"}
        for node in tree.body:
            if isinstance(node, ast.Import): self.assertTrue({alias.name for alias in node.names} <= allowed)
            elif isinstance(node, ast.ImportFrom): self.assertIn(node.module, allowed)
        forbidden = {"assemble", "assemble_vector", "assemble_matrix", "splu", "spsolve", "solve", "_observe_raw_mode"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                self.assertNotIn(name, forbidden)
        for name in ("fullspace_dtn_action.py", "fullspace_same_mesh_hcurl_pmg_physical.py",
                     "y_orbit_direct_carrier_qualification.py", "dtn_boundary_phase_gauge.py"):
            ast.parse((SOLVERS/name).read_text(), filename=str(SOLVERS/name))
        for suffix in ("*.npy", "*.npz"):
            self.assertFalse(list((ROOT / "src").rglob(suffix)))
            self.assertFalse([path for path in (ROOT / "benchmarks").rglob(suffix)
                              if path.relative_to(ROOT / "benchmarks").parts[0] != "artifacts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
