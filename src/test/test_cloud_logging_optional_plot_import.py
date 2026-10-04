"""Import-only regression; no FE objects, assembly, JIT, factors or PDE."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _run_import_only(code):
    environment = os.environ.copy()
    environment.update(UCX_TLS="self", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       NUMEXPR_NUM_THREADS="1")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            env=environment, capture_output=True, text=True,
                            timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_c1_import_chain_does_not_require_optional_plotting():
    _run_import_only("""
import builtins, importlib, json
from pathlib import Path
import numpy as np
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == 'pyvista' or name.startswith('vtk') or name.endswith('postprocessing.postprocess'):
        raise AssertionError('unexpected plotting import: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from dolfinx import fem
def forbidden(*args, **kwargs):
    raise AssertionError('import-only regression must not construct FE/JIT objects')
fem.form = forbidden
fem.functionspace = forbidden
for name in (
    'src.solvers.common_3d_utils', 'src.solvers.dtn_port_3d',
    'src.solvers.fullspace_same_mesh_hcurl_pmg_physical',
    'src.solvers.fullspace_dtn_action', 'src.solvers.y_orbit_condensed_adapter',
    'src.solvers.p6_cell_condensed_action',
    'src.solvers.dtn_boundary_plane_qualification',
    'src.solvers.original_port_blocks', 'src.solvers.fresh_c1_p6_component',
    'src.solvers.y_orbit_sparse_probe', 'src.solvers.y_orbit_centered_evidence'):
    importlib.import_module(name)
from src.solvers.solve_vector_maxwell import _json_default
assert json.loads(json.dumps([1+2j, np.int32(3), np.float64(4), Path('a')], default=_json_default)) == [[1,2],3,4,'a']
try:
    _json_default(object())
except TypeError:
    pass
else:
    raise AssertionError('unsupported JSON type unexpectedly accepted')
""")


def test_actual_plotting_case_still_requires_original_plot_import_first():
    _run_import_only("""
import builtins
from src.solvers.solve_vector_maxwell import run_case
class ExpectedPlotImport(ImportError):
    pass
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.endswith('postprocessing.postprocess'):
        raise ExpectedPlotImport('original plotting dependency requested')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
try:
    run_case(None, None)
except ExpectedPlotImport:
    pass
else:
    raise AssertionError('plotting dependency was skipped or numerical case ran')
""")
