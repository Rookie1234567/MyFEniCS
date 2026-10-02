"""Focused AST-extracted production metadata guards; no FE/JIT/factor/PDE.

Synthetic scalar controls test admission and exhaustive loop inventories only.
No numerical qualification is claimed. This test file is staged, not run.
"""
from __future__ import annotations

import ast
import cmath
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

ROOT = Path(__file__).parents[2]
SOLVERS = ROOT / "src/solvers"
CANONICAL = ROOT if (ROOT / ".git").exists() else ROOT.parents[2] / "repo"
MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"


class StripImports(ast.NodeTransformer):
    def visit_Import(self, node): return None
    def visit_ImportFrom(self, node): return None


def tree(name):
    return ast.parse((SOLVERS / name).read_text())


def function(name, symbol, owner=None):
    nodes = tree(name).body
    if owner is not None:
        nodes = next(node for node in nodes if isinstance(node, ast.ClassDef) and node.name == owner).body
    return next(copy.deepcopy(node) for node in nodes if isinstance(node, ast.FunctionDef) and node.name == symbol)


def isolated(nodes, namespace):
    module = StripImports().visit(ast.Module(body=copy.deepcopy(nodes), type_ignores=[]))
    ast.fix_missing_locations(module)
    exec(compile(module, "<isolated production AST>", "exec"), namespace)
    return namespace


def metadata_module():
    path = SOLVERS / "y_orbit_direct_profile.py"
    if not path.exists(): path = CANONICAL / "src/solvers/y_orbit_direct_profile.py"
    module = ModuleType("isolated_y_profile_for_guard_tests")
    sys.modules[module.__name__] = module
    exec(compile(ast.parse(path.read_text()), str(path), "exec"), module.__dict__)
    return module


def require(condition, message):
    if not condition: raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class Vector(list):
    def __sub__(self, other): return Vector(a - b for a, b in zip(self, other, strict=True))
    def __truediv__(self, other): return Vector(a / b for a, b in zip(self, other, strict=True))


class ScalarBlock:
    def __init__(self, value): self.value = complex(value)
    def __sub__(self, other): return ScalarBlock(self.value - other.value)


NP = SimpleNamespace(pi=math.pi, exp=cmath.exp, isfinite=cmath.isfinite,
    asarray=lambda values: Vector(values), abs=lambda values: Vector(abs(value) for value in values), max=max,
    finfo=lambda dtype: SimpleNamespace(tiny=sys.float_info.min),
    linalg=SimpleNamespace(norm=lambda value: abs(value.value)))


def grid_source(metadata, local):
    ny = metadata.local_y_cells if local else metadata.ny
    axes = metadata.local_axes if local else metadata.global_axes
    cells = []
    for ix in range(metadata.nx):
        for iy in range(ny):
            for iz in range(metadata.nz):
                cells.append({"cell_index": len(cells), "grid": [ix, iy, iz], "tag": 1,
                    "widths": [axis[index + 1] - axis[index] for axis, index in zip(axes, (ix, iy, iz), strict=True)]})
    return {"profile": metadata.identity(), "local_two_cell": local, "cells": cells, "axes": axes,
        "cell_count": len(cells), "native": {"full_rows": metadata.local_storage_rows if local else metadata.storage_rows},
        "entities": {"ny": ny}}


def orbit_receipt(metadata):
    phase = cmath.exp(.37j)
    etas = [cmath.exp(1j * (.37 + 2 * math.pi * q) / metadata.ny) for q in range(metadata.ny)]
    return {"global_source": grid_source(metadata, False),
        "local_sources": [grid_source(metadata, True) for _ in range(metadata.replication_count)],
        "global_eta": [[eta.real, eta.imag] for eta in etas], "global_phase_y": [phase.real, phase.imag]}


def orbit_function():
    def pair_sums(source, cells, etas, **kwargs):
        return [0], {(p, q): ScalarBlock(1 if p == q else 0)
                     for p in range(len(etas)) for q in range(len(etas))}
    namespace = {"np": NP, "_require": require, "LIMIT": 1e-11, "_orbit_pair_sums": pair_sums}
    return isolated([function("y_orbit_direct_operator_qualification.py", symbol)
                     for symbol in ("_uncomplex", "_relative", "_check_orbits")], namespace)


class YProofMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.profile_module = metadata_module()

    def profile(self, name="Y"): return self.profile_module.direct_profile_metadata(name)

    def operator_metadata(self):
        return isolated([function("y_orbit_direct_operator_qualification.py", "_metadata")], {
            "_require": require, "DirectTwoCellProfile": self.profile_module.DirectTwoCellProfile,
            "direct_profile_metadata": self.profile_module.direct_profile_metadata})

    def test_exact_production_inventory_and_old_X_XZ(self):
        namespace = self.operator_metadata()
        for name in ("X", "XZ", "Y"):
            self.assertEqual(namespace["_metadata"](name), self.profile(name))
        metadata = namespace["_metadata"]("Y")
        self.assertEqual(metadata.dimensions, (4, 6, 5))
        self.assertEqual((metadata.cell_count, metadata.storage_rows, metadata.independent_rows,
            metadata.interior_rows, metadata.trace_rows), (120, 25468, 23808, 12960, 10848))
        self.assertEqual((metadata.local_cell_count, metadata.local_storage_rows, metadata.local_independent_rows,
            metadata.local_interior_rows, metadata.local_trace_rows), (40, 8940, 7936, 4320, 3616))
        self.assertEqual(metadata.q_port_counts, (76, 76, 76, 152, 76, 76))
        self.assertEqual(metadata.sector_port_counts, (228, 152, 152))

    def test_unknown_and_mutated_Ny_q_alias_inventory_fail_closed(self):
        namespace = self.operator_metadata()
        for name in (None, True, "y", "YZ", ""):
            with self.subTest(profile=name), self.assertRaises(ValueError): namespace["_metadata"](name)
        for field, bad in (("dimensions", (4, 4, 5)),
                           ("q_port_counts", (76, 76, 76, 152, 76)),
                           ("q_port_counts", (76, 152, 152, 152, 152, 152))):
            changed = copy.copy(self.profile())
            object.__setattr__(changed, field, bad)
            namespace["direct_profile_metadata"] = lambda profile: changed
            with self.subTest(field=field), self.assertRaises(ValueError): namespace["_metadata"]("Y")

    def test_production_Y_sector_and_branch_example_preserves_both_n3_aliases(self):
        path = CANONICAL / "src/solvers/y_orbit_quotient_context.py"
        production = next(node for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name == "build_two_cell_quotient_context")
        selection = next(node for node in production.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "indices" for target in node.targets))
        result = next(node.value for node in production.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "result" for target in node.targets))
        branches = ast.Expression(body=copy.deepcopy(result.args[-2]))
        ast.fix_missing_locations(branches)
        modes = tuple(SimpleNamespace(n=n, gamma=.1+n) for n in range(-3, 4))
        metadata = self.profile()
        for b, expected in ((0, (-3, 0, 3)), (1, (-2, 1)), (2, (-1, 2))):
            namespace = {"modes": modes, "b": b, "replication_count": metadata.replication_count,
                "profile_name": "Y", "LOCAL_Y_CELLS": 2, "REPLICATION_COUNT": 2}
            isolated([selection], namespace)
            selected_n = tuple(modes[index].n for index in namespace["indices"])
            self.assertEqual(selected_n, expected)
            actual_branches = eval(compile(branches, str(path), "eval"), namespace)
            self.assertEqual(actual_branches, tuple(((n-b)//3)%2 for n in expected))
            if b == 0:
                self.assertEqual((selected_n[0]%6, selected_n[-1]%6), (3, 3))
                self.assertEqual((actual_branches[0], actual_branches[-1]), (1, 1))
                self.assertNotEqual(modes[0].gamma, modes[-1].gamma)
        self.assertNotEqual(1%6, (-3)%6)
        self.assertEqual(metadata.q_port_counts[3], 152)
        block_path = CANONICAL / "src/solvers/y_orbit_two_cell_block_audit.py"
        block_tree = ast.parse(block_path.read_text())
        owner = next(node for node in block_tree.body if isinstance(node, ast.ClassDef)
                     and node.name == "TwoCellBranchCoordinates")
        init = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        physical_eta = next(node.value for node in init.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "eta" for target in node.targets))
        self.assertIn("complex(m.gamma)", ast.unparse(physical_eta))

    def test_all20_orbits_all36_global_and12_local_and24_cross_twist_pairs(self):
        metadata = self.profile()
        namespace = orbit_function()
        result = namespace["_check_orbits"](orbit_receipt(metadata), load=None, gate=None, metadata=metadata)
        self.assertEqual(len(result), 20)
        for orbit in result:
            self.assertEqual(len(orbit["global_cell_ids"]), 6)
            self.assertEqual({(row["p"], row["q"]) for row in orbit["all_global_q_pairs"]},
                             {(p, q) for p in range(6) for q in range(6)})
            self.assertEqual(sum(row["cross_twist"] for row in orbit["all_global_q_pairs"]), 24)
            self.assertEqual([row["b"] for row in orbit["local_twists"]], [0, 1, 2])
            self.assertEqual(sum(len(row["all2x2_pairs"]) for row in orbit["local_twists"]), 12)
            for sector in orbit["local_twists"]:
                self.assertEqual({(pair["global_p"], pair["global_q"]) for pair in sector["all2x2_pairs"]},
                    {(sector["b"] + 3*p, sector["b"] + 3*q) for p in (0, 1) for q in (0, 1)})
        for name, groups in (("X", 30), ("XZ", 42)):
            old = self.profile(name)
            result = namespace["_check_orbits"](orbit_receipt(old), load=None, gate=None, metadata=old)
            self.assertEqual(len(result), groups)
            self.assertTrue(all(len(orbit["all_global_q_pairs"]) == 16 for orbit in result))
            self.assertTrue(all(len(orbit["local_twists"]) == 2 for orbit in result))

    def test_missing_q_sector_or_cell_and_wrong_phase_are_rejected(self):
        metadata = self.profile()
        namespace = orbit_function()
        for mutation in ("q", "sector", "cell", "phase"):
            receipt = orbit_receipt(metadata)
            if mutation == "q": receipt["global_eta"].pop()
            elif mutation == "sector": receipt["local_sources"].pop()
            elif mutation == "cell": receipt["global_source"]["cells"].pop()
            else: receipt["global_eta"][-1] = receipt["global_eta"][0]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                namespace["_check_orbits"](receipt, load=None, gate=None, metadata=metadata)

    def test_production_cell_source_and_complete_interior_inventory_predicates(self):
        production = function("y_orbit_direct_operator_qualification.py", "_check_source")
        prefix = []
        for node in production.body:
            if isinstance(node, ast.ImportFrom): break
            prefix.append(node)
        coverage = next(node for node in production.body if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call) and any(isinstance(arg, ast.Constant)
            and arg.value == "complete actual cell/grid/interior coverage is not exhaustive" for arg in node.value.args))
        metadata = self.profile()
        for local, count in ((False, 12960), (True, 4320)):
            source = grid_source(metadata, local)
            namespace = {"source": source, "metadata": metadata, "_require": require,
                         "_token": lambda value: canonical(value).decode()}
            isolated(prefix, namespace)
            namespace.update(seen_cells={cell["cell_index"] for cell in source["cells"]},
                seen_grid={tuple(cell["grid"]) for cell in source["cells"]},
                seen_interiors=set(range(count)), INTERIOR_DIMENSION=108)
            isolated([coverage], namespace)
            namespace["seen_interiors"].remove(count - 1)
            with self.assertRaises(ValueError): isolated([coverage], namespace)
            source["entities"]["ny"] = 4 if not local else 3
            with self.assertRaises(ValueError): isolated(prefix, namespace)

    def test_Y_all_actual12960_interior_guard_and_old_degree_profiles(self):
        production = function("y_orbit_centered_evidence.py", "fixture_interior_positions")
        direct_gate = next(node for node in production.body if isinstance(node, ast.If)
            and ast.unparse(node.test) == "direct_profile is not None")
        complete_gate = next(node for node in production.body if isinstance(node, ast.If)
            and ast.unparse(node.test).startswith("expected is None"))
        for name in ("X", "XZ", "Y"):
            metadata = self.profile(name)
            namespace = {"direct_profile": name, "direct_profile_metadata": self.profile_module.direct_profile_metadata,
                "degree": 4, "layout": SimpleNamespace(full_rows=metadata.storage_rows),
                "positions": range(metadata.interior_rows), "rows": range(metadata.interior_rows)}
            isolated([direct_gate, complete_gate], namespace)
            self.assertEqual(namespace["expected"], metadata.interior_rows)
            namespace["positions"] = range(metadata.interior_rows - 1)
            with self.assertRaises(ValueError): isolated([direct_gate, complete_gate], namespace)
        for degree, count in ((2, 480), (4, 8640)):
            namespace = {"direct_profile": None, "degree": degree, "expected": count,
                "positions": range(count), "rows": range(count)}
            isolated([direct_gate, complete_gate], namespace)

    def test_production_alias_counts_include76_for_nonzero_q(self):
        production = function("y_orbit_direct_operator_qualification.py", "_check_condensation")
        alias_gate = next(node for node in ast.walk(production) if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call) and any(isinstance(arg, ast.Constant)
            and arg.value == "complete physical aliases differ" for arg in node.value.args))
        metadata = self.profile()
        for q, count in enumerate(metadata.q_port_counts):
            namespace = {"metadata": metadata, "qglobal": q, "aliases": range(count), "_require": require}
            isolated([alias_gate], namespace)
            namespace["aliases"] = range(152 if count == 76 else 76)
            with self.assertRaises(ValueError): isolated([alias_gate], namespace)


class YAdmissionAndFactorMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.profile_module = metadata_module()

    def local_fixture(self, b):
        metadata = self.profile_module.direct_profile_metadata("Y")
        cfg = SimpleNamespace(mesh_axis_cell_counts=(4, 2, 5), nedelec_degree=4,
            nedelec_trace_degree=None, nedelec_interior_degree=None,
            mesh_axis_x_values=metadata.local_axes[0], mesh_axis_y_values=metadata.local_axes[1],
            mesh_axis_z_values=metadata.local_axes[2], as_jsonable=lambda: {"fixture": "actual admitted local axes"})
        first = metadata.q_port_counts[b]
        count = metadata.sector_port_counts[b]
        context = SimpleNamespace(direct_profile_name="Y", global_axes=metadata.global_axes,
            local_axes=metadata.local_axes, global_y_cells=6, local_y_cells=2, replication_count=3,
            twist_index=b, global_q_indices=(b, b+3), physical_generator_manifest_sha256=MANIFEST,
            original_mode_indices=tuple(range(count)), original_mode_keys=tuple(range(count)),
            local_branch_indices=(0,)*first + (1,)*(count-first),
            assembly_config_sha256=hashlib.sha256(canonical(cfg.as_jsonable())).hexdigest())
        return metadata, cfg, context

    def local_guard(self):
        return isolated([function("y_orbit_raw_observer_admission.py", "direct_raw_observer_expected_local_cells")], {
            "DirectTwoCellProfile": self.profile_module.DirectTwoCellProfile,
            "direct_profile_metadata": self.profile_module.direct_profile_metadata,
            "PHYSICAL_GENERATOR_SHA256": MANIFEST, "hashlib": hashlib,
            "_canonical_json_bytes": canonical})["direct_raw_observer_expected_local_cells"]

    def test_all_three_Y_local_admissions_keep_actual40_cells(self):
        guard = self.local_guard()
        for b in range(3):
            metadata, cfg, context = self.local_fixture(b)
            self.assertEqual(guard(context, cfg), metadata.local_cell_count)

    def test_local_Ny_missing_q_sector_or_alias_rejected(self):
        guard = self.local_guard()
        for field, bad in (("direct_profile_name", "unknown"), ("global_y_cells", 4),
            ("replication_count", 2), ("twist_index", 3), ("twist_index", True),
            ("global_q_indices", (0, 2)), ("original_mode_indices", ()),
            ("original_mode_keys", ()), ("local_branch_indices", (0,)*228)):
            _, cfg, context = self.local_fixture(0)
            setattr(context, field, bad)
            with self.subTest(field=field), self.assertRaises(ValueError): guard(context, cfg)

    def factor_prefix(self):
        production = function("y_orbit_two_cell_inverse.py", "__init__", "FourBranchFactors")
        prefix = []
        for node in production.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Tuple) for target in node.targets): break
            prefix.append(node)
        return prefix

    def test_six_factor_admission_shapes_and_missing_q_fail_before_factor(self):
        prefix = self.factor_prefix()
        for name in (None, "X", "XZ", "Y"):
            profile = self.profile_module.direct_profile_metadata(name) if name else None
            counts = profile.augmented_rows_per_q if profile else (1884, 1960, 1960, 1960)
            matrices = {q: SimpleNamespace(shape=(count, count), indices=SimpleNamespace(dtype="int32"))
                        for q, count in enumerate(counts)}
            namespace = {"self": SimpleNamespace(), "direct_profile": name, "matrices": matrices,
                "direct_profile_metadata": self.profile_module.direct_profile_metadata,
                "csr_audit": lambda *args, **kwargs: None}
            isolated(prefix, namespace)
            self.assertEqual(namespace["self"].nq, len(counts))
            self.assertEqual(namespace["self"].per_q_allowance, 128*1024**2)
            if name == "Y":
                self.assertEqual(namespace["self"].nq*namespace["self"].per_q_allowance, 768*1024**2)
                matrices.pop(5)
                with self.assertRaises(ValueError): isolated(prefix, namespace)
        namespace["direct_profile"] = "unknown"
        with self.assertRaises(ValueError): isolated(prefix, namespace)
        profile = self.profile_module.direct_profile_metadata("Y")
        matrices = {q: SimpleNamespace(shape=(count, count), indices=SimpleNamespace(dtype="int32"))
                    for q, count in enumerate(profile.augmented_rows_per_q)}
        namespace.update(direct_profile="Y", matrices=matrices)
        matrices[2].shape = (1960, 1960)
        with self.assertRaises(ValueError): isolated(prefix, namespace)

    def test_factor_Y_and_old_profile_receipt_fields(self):
        production = function("y_orbit_two_cell_inverse.py", "__init__", "FourBranchFactors")
        receipt_gate = next(node for node in ast.walk(production) if isinstance(node, ast.If)
            and ast.unparse(node.test) == "direct_profile is not None"
            and any(isinstance(child, ast.Constant) and child.value == "all_six_retained_simultaneously"
                    for child in ast.walk(node)))
        for name in ("X", "XZ", "Y"):
            profile = self.profile_module.direct_profile_metadata(name)
            owner = SimpleNamespace(audit={"all_four_retained_simultaneously": True}, nq=profile.ny,
                per_q_allowance=128*1024**2, direct_profile_name=name)
            isolated([receipt_gate], {"self": owner, "direct_profile": name, "profile": profile})
            self.assertTrue(owner.audit["all_actual_q_retained_simultaneously"])
            self.assertEqual(owner.audit["all_four_retained_simultaneously"], name != "Y")
            self.assertEqual(owner.audit["factor_allowance_aggregate_bytes"], profile.factor_allowance_aggregate_bytes)
            if name == "Y": self.assertTrue(owner.audit["all_six_retained_simultaneously"])
            else: self.assertNotIn("all_six_retained_simultaneously", owner.audit)

    def test_shared_evidence_requires_every_Y_role_and_preserves_old_roles(self):
        init = function("y_orbit_shared_transform_evidence.py", "__init__", "SharedTransformEvidence")
        result = function("y_orbit_shared_transform_evidence.py", "result", "SharedTransformEvidence")
        namespace = isolated([init, result], {"ROLES": ("full", "twist_0", "twist_1"),
            "SCHEMA": "fixture schema", "direct_profile_metadata": self.profile_module.direct_profile_metadata})
        bank = SimpleNamespace(receipt=lambda **kwargs: {"sealed": True})
        for name, expected in ((None, ("full", "twist_0", "twist_1")),
            ("X", ("full", "twist_0", "twist_1")), ("XZ", ("full", "twist_0", "twist_1")),
            ("Y", ("full", "twist_0", "twist_1", "twist_2"))):
            owner = SimpleNamespace()
            namespace["__init__"](owner, bank, save_array=None, event=None, allocation_gate=None,
                mapping_limit=1e-11, direct_profile=name)
            self.assertEqual(owner.expected_roles, expected)
            owner.roles = [{"role": role} for role in expected]
            self.assertTrue(namespace["result"](owner)["complete_before_any_factor"])
            owner.roles.pop()
            with self.assertRaises(ValueError): namespace["result"](owner)

    def test_Y_budget_requires_exact_bound_launch_packet_and_preserves_old(self):
        guard = isolated([function("y_orbit_direct_carrier_qualification.py", "_resource_authority")],
                         {"json": json})["_resource_authority"]
        self.assertIn("1.5GiB)/600s", guard({}))
        for name, memory, wall in (("X", 2, 1800), ("XZ", 3, 4500), ("Y", 3, 4500)):
            cap = memory*1024**3
            admission = {"requested_memory_gib": memory, "requested_tree_cap_bytes": cap,
                "required_cap_plus_evidence_reserve_bytes": cap+128*1024**2, "launch_admission_passed": True}
            environment = {"QUOTIENT_RESEARCH_MEMORY_GIB": str(memory), "QUOTIENT_RESEARCH_MEMORY_PROFILE": name,
                "QUOTIENT_RESEARCH_MEMORY_STAGE": "solve", "QUOTIENT_RESEARCH_WALL_SECONDS": str(wall),
                "QUOTIENT_RESEARCH_TREE_CAP_BYTES": str(cap), "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES": str(cap),
                "QUOTIENT_PHASE_WALL_SECONDS": str(wall),
                "QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION": json.dumps(admission)}
            self.assertIn(f"{memory}GiB)/{wall}s", guard(environment))
            for field, bad in (("QUOTIENT_RESEARCH_MEMORY_PROFILE", "unknown"),
                ("QUOTIENT_RESEARCH_WALL_SECONDS", "600"), ("QUOTIENT_RESEARCH_MEMORY_GIB", "4"),
                ("QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION", "null")):
                with self.subTest(profile=name, field=field), self.assertRaises(ValueError):
                    guard({**environment, field: bad})


if __name__ == "__main__": unittest.main()
