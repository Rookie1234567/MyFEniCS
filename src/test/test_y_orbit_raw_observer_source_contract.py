"""Exact source-diff exception tests; no FE, numeric arrays or kernel imports."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
BRIDGE=ROOT/'benchmarks/y_orbit_direct_source_contract.py'

def load(path):
    spec=importlib.util.spec_from_file_location('_raw_observer_source_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class RawObserverSourceContractTests(unittest.TestCase):
    def fixture(self,mutation=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);(root/'benchmarks').mkdir()
        (root/'benchmarks/y_orbit_direct_source_contract.py').write_bytes(BRIDGE.read_bytes())
        bridge=load(root/'benchmarks/y_orbit_direct_source_contract.py');files={}
        for relative in bridge.RAW_OBSERVER_BASELINE_AST:
            text=(ROOT/relative).read_text()
            if mutation is not None:text=mutation(relative,text)
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
            files[relative]=hashlib.sha256(target.read_bytes()).hexdigest()
        return bridge,files

    def test_exact_three_module_default_and_numerical_AST(self):
        bridge,files=self.fixture();proof=bridge.validate_raw_observer_ast_seams(files)
        self.assertEqual(len(proof),3)
        self.assertTrue(all(p['numerical_and_None_default_AST_unchanged'] for p in proof))
        self.assertTrue(all(not p['whole_file_byte_equality_claimed'] for p in proof))

    def test_updated_file_hash_cannot_hide_changed_normalization_math(self):
        def mutation(path,text):
            if path.endswith('fullspace_dtn_action.py'):
                tree=ast.parse(text)
                node=next(n for n in ast.walk(tree) if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Div)
                          and isinstance(n.right,ast.Attribute) and n.right.attr=='normalization_h')
                node.op=ast.Mult();return ast.unparse(tree)
            return text
        bridge,files=self.fixture(mutation)
        with self.assertRaises(ValueError):bridge.validate_raw_observer_ast_seams(files)

    def test_early_callback_rejection_cannot_move_after_numeric_work(self):
        def mutation(path,text):
            if path.endswith('fullspace_dtn_action.py'):
                tree=ast.parse(text);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_fullspace_dtn_carrier_from_surface')
                fn.body.append(fn.body.pop(1));return ast.unparse(tree)
            return text
        bridge,files=self.fixture(mutation)
        with self.assertRaises(ValueError):bridge.validate_raw_observer_ast_seams(files)

    def test_local_cell_prelude_cannot_move_after_mesh_gate(self):
        def mutation(path,text):
            if path.endswith('dtn_boundary_phase_gauge.py'):
                tree=ast.parse(text);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_gauge_assembly_context')
                local=next(n for n in fn.body if isinstance(n,ast.If) and ast.unparse(n.test)=='quotient_context is not None')
                prelude=local.body[3:5];del local.body[3:5];local.body.extend(prelude);return ast.unparse(tree)
            return text
        bridge,files=self.fixture(mutation)
        with self.assertRaises(ValueError):bridge.validate_raw_observer_ast_seams(files)

    def test_stale_source_byte_receipt_rejected_before_normalization(self):
        bridge,files=self.fixture();files[next(iter(files))]='0'*64
        with self.assertRaises(ValueError):bridge.validate_raw_observer_ast_seams(files)

    def test_arbitrary_extra_code_is_never_removed_as_metadata(self):
        def mutation(path,text):
            if path.endswith('fullspace_dtn_action.py'):
                tree=ast.parse(text);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_fullspace_dtn_carrier_from_surface')
                fn.body[1].body.append(ast.parse('print("unapproved")').body[0]);return ast.unparse(tree)
            return text
        bridge,files=self.fixture(mutation)
        with self.assertRaises(ValueError):bridge.validate_raw_observer_ast_seams(files)

if __name__=='__main__':unittest.main()
