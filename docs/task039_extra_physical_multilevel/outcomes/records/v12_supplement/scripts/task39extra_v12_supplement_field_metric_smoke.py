"""Reproduce pre-recovery quadrature wiring and check independent field norms."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path.cwd()))
assert os.environ['_MYFENICS_WSL_QUALIFIED_ACTIVATION'] == '1'
assert os.path.samefile(sys.executable, '.venv/bin/python')
from src.runners.physical_macro_v12 import _field_compare

quadrature = ({'quadrature_degree': 14}, {'quadrature_degree': 16})
levels = {'spaces': {6: object()}, 'floquets': {6: object()}}
destroyed = []


class Metric:
    def __init__(self, actual_levels, degree, k0, metadata):
        assert actual_levels is levels and degree == 6 and k0 == 2.0
        assert metadata is quadrature
        self.mass = lambda x: np.array([2.0, 5.0]) * x
        self.curl = lambda x: np.array([3.0, 7.0]) * x

    def destroy(self):
        destroyed.append(True)


solution = SimpleNamespace(array=np.array([2.0 + 1j, 999.0, 4.0 - 2j]))
reference = np.array([1.0 + 2j, -888.0, 3.0 + 1j])
before, before_ref = solution.array.copy(), reference.copy()
for mode in ('live_actions', 'after_auxiliary_release'):
    stack = {'levels': levels, 'fine': {'setup': levels, 'cfg': SimpleNamespace(k0=2.0)}}
    if mode == 'live_actions':
        stack['actions'] = {'volume_quadrature_metadata': quadrature}
    else:
        stack['recovery_quadrature_metadata'] = quadrature
    with patch('src.solvers.physical_error_metric.LosslessFEMetric', Metric), \
         patch('src.solvers.condensed_fine_reference.native_map_arrays',
               lambda *args: {'independent_indices': [0, 2]}):
        result = _field_compare(stack, solution, reference)
    error = solution.array[[0, 2]] - reference[[0, 2]]
    ref = reference[[0, 2]]
    for key, weights in [('L2', np.array([2., 5.])), ('scaled_curl', np.array([3., 7.]))]:
        expected = np.sqrt(np.sum(weights * abs(error)**2) / np.sum(weights * abs(ref)**2))
        assert np.isclose(result[key]['relative'], expected, rtol=1e-14)
    assert result['status'] == 'REFERENCE_FIELD_AVAILABLE'
    assert np.array_equal(solution.array, before) and np.array_equal(reference, before_ref)
    print(json.dumps({'mode': mode, 'status': 'PASS', 'field': result,
                      'scope': 'quadrature plumbing and independent norm arithmetic; no PDE or FE quadrature'}))
assert len(destroyed) == 2
