"""Saved-launch guards only: no FE/JIT, numerical replay or file mutation."""
import ast
import inspect
import unittest
from types import SimpleNamespace

import launch_saved_boundary_support_checker as subject


class SavedLauncherTests(unittest.TestCase):
    def test_worker_ancestor_same_and_descendant_rejected_before_preflight(self):
        base = subject.worker.inherited()
        for path in (subject.WORKER, subject.WORKER/"child", subject.WORKER.parent):
            with self.assertRaisesRegex(ValueError, "disjoint"):
                subject.preflight(base, SimpleNamespace(run_directory=path))

    def test_import_hash_precedes_module_execution(self):
        text = inspect.getsource(subject)
        self.assertLess(text.index('hashlib.sha256(_WORKER_PATH.read_bytes())'), text.index('_SPEC.loader.exec_module(worker)'))
        self.assertEqual(subject.WORKER_EXPECTED if hasattr(subject, "WORKER_EXPECTED") else subject._WORKER_EXPECTED,
                         subject.WORKER_LAUNCHER_SHA)

    def test_saved_dispatch_does_not_call_live_runner(self):
        tree = ast.parse(inspect.getsource(subject.child))
        attributes = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(attributes & {"run_pilot", "assemble_boundary_support_pilot", "run_reference", "create_mesh", "form", "factorize"})
        self.assertIn("check_saved", attributes)

    def test_manifest_admission_precedes_parse_and_retention_is_explicit(self):
        text = inspect.getsource(subject.child)
        self.assertLess(text.index('gate("sealed_original_manifest_parse_before_load"'), text.index('manifest = base.read_json'))
        self.assertIn('32060*12288', text)
        self.assertIn('retained_selected_metadata = 4 << 20', text)
        self.assertIn('additional = base.allocation_bytes(facts)+retained_selected_metadata', text)

    def test_supervision_and_complete_identity_gates_preserved(self):
        text = inspect.getsource(subject.main)
        for item in ('hard_stop_immediate=True', 'timebase_guard=True', 'stop_on_global_swap=True',
                     'base.require_summary', 'report.get("checker_inputs")==admitted["checker_inputs"]'):
            self.assertIn(item, text)
        self.assertEqual(subject.WALL, 600)
        self.assertEqual(subject.CHECKER_SHA, "9cdf0722301a196c79a04d4bdad69ecd3998d042196e6069ce41f6fb9ddcef5c")


if __name__ == "__main__": unittest.main(verbosity=2)
