"""Small CPU-only problems exercise actual strong-Wolfe exceptions."""

import hashlib
import inspect
import json
import unittest
from copy import deepcopy
from pathlib import Path
from typing import ClassVar

import torch

from src.solvers.optimizer_step_transaction import OptimizerTransaction, parameter_hash


class BudgetStop(Exception):
    pass


def assert_state_equal(test, left, right):
    test.assertEqual(type(left), type(right))
    if isinstance(left, dict):
        test.assertEqual(left.keys(), right.keys())
        for key in left:
            assert_state_equal(test, left[key], right[key])
    elif isinstance(left, (tuple, list)):
        test.assertEqual(len(left), len(right))
        for a, b in zip(left, right, strict=True):
            assert_state_equal(test, a, b)
    elif isinstance(left, torch.Tensor):
        test.assertTrue(torch.equal(left, right))
    else:
        test.assertEqual(left, right)


def problem(stop_at=None, nonfinite=False):
    p = torch.nn.Parameter(torch.tensor([3.0, -1.0], dtype=torch.float64))
    A = torch.tensor(
        [[3 + 0.7j, 1 - 0.2j], [0.2 + 0.4j, 2 - 0.8j]], dtype=torch.complex128
    )
    b = torch.tensor([0.1 + 0.3j, -0.4 + 0.2j], dtype=torch.complex128)
    optimizer = torch.optim.LBFGS(
        [p],
        lr=10.0,
        line_search_fn="strong_wolfe",
        max_iter=3,
        max_eval=12,
        tolerance_grad=0.0,
        tolerance_change=0.0,
        history_size=20,
    )
    count = dict(closures=0, S=0, SH=0, optimizer_updates=0)
    evaluated = []

    def closure():
        count["closures"] += 1
        evaluated.append(parameter_hash([p]))
        if count["closures"] == stop_at and not nonfinite:
            raise BudgetStop
        optimizer.zero_grad()
        r = A @ p.to(torch.complex128) - b
        count["S"] += 1
        loss = (r.conj() * r).real.sum() / 2
        loss.backward()
        count["SH"] += 1
        if count["closures"] == stop_at and nonfinite:
            with torch.no_grad():
                p.fill_(float("nan"))
            raise FloatingPointError("synthetic nonfinite trial")
        return loss

    return p, optimizer, count, evaluated, closure


class TransactionTests(unittest.TestCase):
    observations: ClassVar[list] = []

    def check_interruption(self, stop_at, nonfinite=False):
        p, opt, count, evaluated, closure = problem(stop_at, nonfinite)
        before = p.detach().clone()
        before_hash = parameter_hash([p])
        old_state = deepcopy(opt.state_dict())
        adapter = OptimizerTransaction([p])
        error = FloatingPointError if nonfinite else BudgetStop
        with self.assertRaises(error):
            adapter.step(
                opt, lambda: opt.step(closure), phase="LBFGS", counts=lambda: count
            )
        self.assertTrue(torch.equal(before, p))
        assert_state_equal(self, old_state, opt.state_dict())
        self.assertEqual(count["closures"], stop_at)
        self.assertEqual(adapter.committed["parameter_sha256"], before_hash)
        self.assertEqual(adapter.completed, 0)
        if stop_at > 1:
            self.assertNotEqual(evaluated[-1], before_hash)
            self.assertNotEqual(adapter.last_trial["parameter_sha256"], before_hash)
        self.observations.append(
            dict(
                stop_at=stop_at,
                nonfinite=nonfinite,
                counts=dict(count),
                distinct_real_line_search_trial=stop_at > 1,
                parameters_restored=True,
                optimizer_restored=True,
            )
        )

    def test_initial_closure_exception(self):
        self.check_interruption(1)

    def test_first_line_search_trial_exception(self):
        self.check_interruption(2)

    def test_later_line_search_trial_exception(self):
        self.check_interruption(3)

    def test_nonfinite_trial(self):
        self.check_interruption(2, True)

    def test_old_semantics_leave_trial_live(self):
        p, opt, count, evaluated, closure = problem(2)
        original = parameter_hash([p])
        with self.assertRaises(BudgetStop):
            opt.step(closure)
        self.assertNotEqual(original, parameter_hash([p]))
        self.assertEqual(count["closures"], 2)
        self.assertNotEqual(evaluated[-1], evaluated[0])

    def test_completed_boundary_and_consistent_reload(self):
        p, opt, count, _, closure = problem()
        adapter = OptimizerTransaction([p])
        adapter.step(
            opt, lambda: opt.step(closure), phase="LBFGS", counts=lambda: count
        )
        accepted = p.detach().clone()
        saved = deepcopy(opt.state_dict())
        completed_hash = parameter_hash([p])
        consumed = dict(count)
        self.assertEqual(adapter.committed["state_kind"], "LAST_COMPLETED_OUTER_STEP")
        self.assertEqual(
            adapter.committed["internal_wolfe_acceptance"], "UNKNOWN_NOT_OBSERVED"
        )

        def fail():
            count["closures"] += 1
            with torch.no_grad():
                p.add_(100)
            raise BudgetStop

        with self.assertRaises(BudgetStop):
            adapter.step(opt, fail, phase="LBFGS", counts=lambda: count)
        self.assertTrue(torch.equal(p, accepted))
        assert_state_equal(self, saved, opt.state_dict())
        self.assertEqual(parameter_hash([p]), completed_hash)
        self.assertEqual(count["closures"], consumed["closures"] + 1)
        # A clone loads parameters and optimizer from the same boundary.
        clone = torch.nn.Parameter(accepted.clone())
        new_optimizer = torch.optim.LBFGS(
            [clone], lr=10.0, line_search_fn="strong_wolfe"
        )
        new_optimizer.load_state_dict(deepcopy(adapter.committed["optimizer"]))
        assert_state_equal(self, opt.state_dict(), new_optimizer.state_dict())
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            records = adapter.save(directory)
            disk = torch.load(records["committed"]["path"], weights_only=True)
            trial = torch.load(records["last_trial"]["path"], weights_only=True)
            self.assertTrue(torch.equal(disk["parameters"][0], accepted))
            assert_state_equal(self, saved, disk["optimizer"])
            self.assertNotIn("optimizer", trial)
            self.assertEqual(
                trial["checkpoint_qualification"],
                "PARAMETER_ONLY_CHECKPOINT_NOT_RESUMABLE",
            )

    def test_adam_closure_and_update_transaction(self):
        p = torch.nn.Parameter(torch.tensor([1.0, 2.0], dtype=torch.float64))
        opt = torch.optim.Adam([p], lr=0.001)
        adapter = OptimizerTransaction([p])
        counts = dict(closures=0)

        def normal():
            counts["closures"] += 1
            p.grad = torch.ones_like(p)
            opt.step()

        adapter.step(opt, normal, phase="ADAM", counts=lambda: counts)
        committed = parameter_hash([p])
        before_state = deepcopy(opt.state_dict())

        def fail():
            counts["closures"] += 1
            opt.step()
            raise BudgetStop

        with self.assertRaises(BudgetStop):
            adapter.step(opt, fail, phase="ADAM", counts=lambda: counts)
        self.assertEqual(parameter_hash([p]), committed)
        assert_state_equal(self, opt.state_dict(), before_state)
        self.assertEqual(counts["closures"], 2)


if __name__ == "__main__":
    import sys

    from src.solvers.neural_trace_torch import qualify_threads

    threads = qualify_threads()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransactionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    path = Path(inspect.getsourcefile(torch.optim.LBFGS))
    report = dict(
        status="PASS" if result.wasSuccessful() else "FAIL",
        tests=result.testsRun,
        observations=TransactionTests.observations,
        torch_version=torch.__version__,
        torch_lbfgs_path=str(path),
        torch_lbfgs_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        threads=threads,
        actual_strong_wolfe_exercised=True,
        V7_acceptance_state="V7_ACCEPTANCE_STATE_UNKNOWN",
        long_physical_training_replayed=False,
    )
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
