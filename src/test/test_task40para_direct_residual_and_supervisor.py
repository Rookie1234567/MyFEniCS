import numpy as np

from src.runners.p6_condensed_direct import (
    _bounded_same_factor_condensed_refinement,
    _release_task40_direct_algebra,
)


class _Vec:
    def __init__(self, values):
        self.array = np.asarray(values, dtype=np.complex128).copy()

    def duplicate(self):
        return _Vec(np.zeros_like(self.array))

    def set(self, value):
        self.array.fill(value)

    def norm(self):
        return float(np.linalg.norm(self.array))

    def copy(self, other):
        other.array[:] = self.array

    def axpy(self, alpha, other):
        self.array[:] += alpha * other.array

    def destroy(self):
        pass


class _Matrix:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128)

    def mult(self, vector, output):
        output.array[:] = self.values @ vector.array


class _Factor:
    def __init__(self, matrix, correction_scale=1.0):
        self.matrix = matrix
        self.correction_scale = correction_scale
        self.symbolic_calls = 1
        self.numeric_calls = 1
        self.solve_calls = 1

    def solve_repeated(self, rhs, solution):
        solution.array[:] = self.correction_scale * np.linalg.solve(
            self.matrix.values, rhs.array
        )
        self.solve_calls += 1


def _run_refinement(correction_scale):
    matrix = _Matrix([[2.0, 1.0j], [-1.0j, 3.0]])
    exact = np.asarray([1.0 + 2.0j, -0.5 + 0.25j])
    rhs = _Vec(matrix.values @ exact)
    solution = _Vec(exact + np.asarray([2.0e-5 - 1.0e-5j, -1.0e-5j]))
    action, residual = rhs.duplicate(), rhs.duplicate()
    matrix.mult(solution, action)
    rhs.copy(residual)
    residual.axpy(-1.0, action)
    initial = residual.norm() / rhs.norm()
    factor = _Factor(matrix, correction_scale=correction_scale)
    markers = []
    relative, count, history = _bounded_same_factor_condensed_refinement(
        factor, matrix, rhs, solution, action, residual,
        initial_relative=initial,
        relative_gate=1.0e-9,
        max_corrections=2,
        marker=lambda name, facts: markers.append((name, facts)),
    )
    return matrix, factor, relative, count, history, markers


def test_condensed_residual_uses_one_same_factor_correction_and_passes_gate():
    matrix, factor, relative, count, history, markers = _run_refinement(1.0)
    assert count == 1
    assert factor.solve_calls == 2
    assert relative <= 1.0e-9
    assert len(history) == 2
    assert len(markers) == 1
    assert markers[0][1]['same_matrix_object_id'] == id(matrix)


def test_condensed_residual_refinement_is_bounded_to_two_corrections():
    _, factor, relative, count, history, markers = _run_refinement(0.5)
    assert count == 2
    assert factor.solve_calls == 3
    assert relative > 1.0e-9
    assert len(history) == 3
    assert len(markers) == 2


def test_host_floor_supervise_runs_short_child_without_legacy_cap(tmp_path):
    import json
    import subprocess
    import sys

    script = r'''
import json
import sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
watchdog.memory_envelope = lambda: {
    "mem_total_bytes": 2000,
    "mem_available_bytes": 1500,
    "effective_total_bytes": 2000,
    "effective_available_bytes": 1500,
    "reserve_bytes": None,
    "launch_cap_bytes": None,
    "planning_cap_bytes": None,
    "minimum_available_bytes": 100,
    "resource_stop_policy": "host_available_floor_v1",
    "cgroup_limits": [],
}
watchdog.vmstat_swap_pages = lambda: {"pswpin_pages": 0, "pswpout_pages": 0}
result = watchdog.supervise(
    ["/usr/bin/true"], Path(sys.argv[1]), wall_seconds=None,
    solve_seconds=None, interval=0.05, grace_seconds=0.2,
    resource_stop_policy="host_available_floor_v1",
    minimum_available_bytes=100, stop_on_global_swap=False,
    pss_sampling_policy="disabled_by_profile",
)
print(json.dumps(result, sort_keys=True))
'''
    completed = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path/'run')],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(completed.stdout.strip().splitlines()[-1])

    assert summary['classification'] == 'COMPLETED'
    assert summary['descendants_cleared'] is True
    assert summary['resource_stop_policy'] == 'host_available_floor_v1'
    assert summary['rss_hard_limit_bytes'] is None
    assert summary['minimum_available_bytes'] == 100
    assert summary['launch_envelope']['launch_cap_bytes'] is None
    assert summary['samples'] >= 1
    assert summary['swap_policy'] == 'observe_only'
    assert summary['job_swap_activity'].startswith('HOST_FLOOR_OBSERVE_ONLY_')
    assert 'zero_supported' not in summary['job_swap_activity']


def test_task40_early_release_destroys_factor_then_borrow_then_single_matrix_owner():
    events = []

    class Matrix:
        destroyed = False

        def destroy(self):
            assert not self.destroyed
            self.destroyed = True
            events.append('matrix')

    class Condensed:
        def __init__(self, matrix):
            self.matrix = matrix
            self._destroyed = False

        def destroy(self):
            assert not self._destroyed
            self.matrix.destroy()
            self._destroyed = True
            events.append('condensed')

    class Factor:
        destroyed = False

        def destroy(self):
            assert not self.destroyed
            self.destroyed = True
            events.append('factor')

    class BorrowedAction:
        owns_condensed = False
        _destroyed = False

        def __init__(self, view):
            self.condensed = view

        def destroy(self):
            assert not self._destroyed
            self._destroyed = True
            events.append('action')

    matrix = Matrix()
    condensed = Condensed(matrix)
    class View:
        matrix = None

    view = View()
    factor = Factor()
    action = BorrowedAction(view)

    facts = _release_task40_direct_algebra(
        factor, action, view, condensed, matrix
    )

    assert events == ['factor', 'action', 'matrix', 'condensed']
    assert matrix.destroyed and factor.destroyed and action._destroyed
    assert condensed._destroyed and condensed.matrix is None
    assert facts['materialized_matrix_destroyed_by'] == 'condensed.destroy'


def test_task40_release_rejects_an_action_that_claims_matrix_ownership():
    events = []

    class Resource:
        def destroy(self):
            events.append('destroy')

    class Condensed:
        matrix = Resource()
        _destroyed = False

    class View:
        matrix = None

    class Action:
        owns_condensed = True
        condensed = View()

    with np.testing.assert_raises(RuntimeError):
        _release_task40_direct_algebra(
            Resource(), Action(), Action.condensed, Condensed(), Condensed.matrix
        )
    assert events == []


def test_task40_release_is_wired_before_field_and_absorption_postprocessing():
    import ast
    import inspect

    from src.runners.p6_condensed_direct import run_p6_condensed_direct

    tree = ast.parse(inspect.getsource(run_p6_condensed_direct))
    release_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == '_release_task40_direct_algebra'
    ]
    output_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'recover_p0_outputs'
    ]
    assert len(release_calls) == len(output_calls) == 1
    assert release_calls[0].lineno < output_calls[0].lineno

    def is_task40_family_guard(node):
        if not isinstance(node, ast.If):
            return False
        test = node.test
        return (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Subscript)
            and isinstance(test.left.value, ast.Name)
            and test.left.value.id == 'route'
            and isinstance(test.left.slice, ast.Constant)
            and test.left.slice.value == 'family'
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == 'task40_phi90'
        )

    task40_guards = [node for node in ast.walk(tree) if is_task40_family_guard(node)]
    assert any(
        any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == '_release_task40_direct_algebra'
            for child in ast.walk(guard)
        )
        for guard in task40_guards
    )
