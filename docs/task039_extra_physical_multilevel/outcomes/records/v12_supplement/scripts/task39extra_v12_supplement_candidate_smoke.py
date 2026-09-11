"""Exercise the actual O2 orchestration on a tiny matrix, with no PDE stack."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from petsc4py import PETSc

assert os.environ['_MYFENICS_WSL_QUALIFIED_ACTIVATION'] == '1'
assert os.path.samefile(sys.executable, '.venv/bin/python')
assert PETSc.ScalarType is np.complex128
sys.path.insert(0, str(Path.cwd()))

from src.runners import physical_macro_v12 as runner

size = 96
matrix = np.diag(np.geomspace(1e-4, 20, size).astype(complex))
matrix += np.diag(np.full(size - 1, .007 + .003j), 1)
rhs = PETSc.Vec().createSeq(size)
rhs.array[:] = np.linspace(1, 2, size) + .1j
node32 = {}


class Action:
    def apply(self, source, target):
        target.array[:] = matrix @ source.array
        return target


class TinyPC:
    def __init__(self):
        self.apply_count = 0
        self.total_counts = {'tiny_identity': 0}
        self.total_operation_seconds = {'tiny_identity': 0.0}

    def apply(self, source):
        self.apply_count += 1
        self.total_counts['tiny_identity'] += 1
        return source.copy()


def make_pc(stack, **kwargs):
    pc = TinyPC()
    stack['I4'] = pc
    return pc


def costs(stack, i4):
    return {'synthetic_PC_count': i4.apply_count}


def metric(stack, solution, reference):
    time.sleep(.002)
    return {'status': 'SYNTHETIC_MEASUREMENT_ONLY', 'max_relative': 1.0}


try:
    for restart in (32, 64):
        stack = {'a6': Action()}
        directory = Path(tempfile.mkdtemp(prefix='task39extra-v12-tiny-o2-'))
        with patch('src.solvers.physical_macro_dd4.make_macro_pc', make_pc), \
             patch('src.runners.physical_macro_controls._stack_cost_snapshot', costs), \
             patch.object(runner, '_field_compare', metric):
            result = runner._run_outer_candidate(
                stack, rhs, framework='BAL_H', restart=restart, max_it=64,
                sample=lambda: {}, marker=lambda *args: None,
                checkpoint_root=directory, input_sha256='a' * 64,
                operator_sha256='b' * 64, physical_sha256='c' * 64,
                source_sha='d' * 40, stage=f'O2_RESTART_PROBE_{restart}',
                output_name=f'tiny_{restart}', reference_x_ref=np.zeros(size),
            )
        try:
            nodes = result['node_records']
            assert result['iterations'] == 64
            assert len({row['iteration'] for row in nodes}) == len(nodes)
            for row in nodes:
                assert row['elapsed_seconds_conservative'] >= row['elapsed_seconds_monotonic'] - 1e-8
                if 'reference_field' in row:
                    # Diagnostic cost must be in both node clocks.
                    assert row['reference_field_elapsed_seconds'] >= .001
                    assert abs(row['elapsed_seconds'] - row['elapsed_seconds_monotonic']) < .001
            assert result['cost_delta']['synthetic_PC_count'] == 64
            assert result['outer_pc_calls'] == 64
            at32 = next(row for row in nodes if row['iteration'] == 32)
            node32[restart] = (at32['solution_sha256'], at32['true_residual'])
            exact = np.linalg.norm(rhs.array - matrix @ result['final_solution'].array) / rhs.norm()
            assert abs(exact - result['final_true_residual']) < 1e-12
            print(json.dumps({'restart': restart, 'status': 'PASS', 'iterations': 64,
                              'nodes': [row['iteration'] for row in nodes],
                              'final_rho': exact, 'directory': str(directory),
                              'new_PDE_runs': 0}))
        finally:
            result['final_solution'].destroy()
    assert node32[32] == node32[64], node32
    print(json.dumps({'prefix32': 'IDENTICAL', 'new_PDE_runs': 0}))
finally:
    rhs.destroy()
