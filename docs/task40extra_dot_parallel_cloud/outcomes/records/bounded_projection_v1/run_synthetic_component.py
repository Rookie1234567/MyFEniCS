"""Finite synthetic component probe; run from the authorized repository root."""
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy import sparse
import scipy

from src.solvers.bounded_compact_q_projection import BoundedCompactQAccumulator
from src.solvers.original_port_blocks import CachedPortCorrection

rng = np.random.default_rng(20261003)
def z(shape):
    return rng.normal(size=shape) + 1j*rng.normal(size=shape)

n, ni, lp, rq, width = 64, 9, 47, 53, 8
l, r = z((n, lp)), z((n, rq))
l[:, 1::6] = 0
r[:, 2::7] = 0
left, right = sparse.csr_matrix(l), sparse.csr_matrix(r)
di, xib = z((n, ni)), z((ni, n))
di.flags.writeable = xib.flags.writeable = False
ids = np.arange(n)
ids.flags.writeable = False
recipe = CachedPortCorrection(ids, di, xib)
events = []
def gate(name, **facts):
    events.append((name, facts))

acc = BoundedCompactQAccumulator((lp, rq), max_owned_bytes=160000, tile_width=width,
                                index_dtype=np.int32, gate=gate)
start = time.perf_counter()
acc.add(left, right, ids, ids, recipe, 'synthetic64')
actual = acc.finish()
tiled_seconds = time.perf_counter() - start
start = time.perf_counter()
reference = (l.conj().T @ di) @ (xib @ r)
dense_seconds = time.perf_counter() - start
error = float(np.linalg.norm(actual.toarray() - reference) / np.linalg.norm(reference))
sp, sq = np.unique(left.indices).size, np.unique(right.indices).size
paths = ('src/solvers/bounded_compact_q_projection.py',
         'src/solvers/y_orbit_two_cell_block_audit.py',
         'src/test/test_bounded_compact_q_projection.py')
record = {
    'schema': 'compact-q-bounded-projection.synthetic-component.v3',
    'status': 'synthetic_algebra_pass' if error < 1e-12 else 'fail',
    'seed': 20261003, 'geometry_or_FE_claim': False, 'raw_scientific_artifacts_read': False,
    'FE_JIT_factor_PDE_calls': 0,
    'source_base_HEAD': '7de238a4b6f74f2b90ec42156f64a71f54ce79e5', 'working_tree_candidate': True,
    'source_files_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'python': sys.executable, 'python_version': sys.version, 'numpy': np.__version__, 'scipy': scipy.__version__, 'thread_count': 1,
    'native_contribution_shape': [n, n], 'factor_inner_dimension': ni,
    'q_shape': [lp, rq], 'actual_support_shape': [int(sp), int(sq)], 'tile_width_upper': width,
    'named_array_budget_bytes': 160000,
    'observed_declared_peak_owned_upper_bytes': acc.peak_owned_upper_bytes,
    'final_CSR_arrays_bytes': sum(x.nbytes for x in (actual.data, actual.indices, actual.indptr)),
    'final_CSR_nnz': actual.nnz,
    'largest_projection_scratch_bound_bytes': max(f['payload'] for name, f in events if 'projection/' in name),
    'legacy_dense_projection_expression_bytes_upper': int(16*(2*n*sp+n*sq+sp*ni+ni*sq+sp*sq)),
    'largest_CSR_merge_declared_owned_upper_bytes': max(f['projection_owned_upper_bytes'] for name, f in events if 'CSR_merge/' in name),
    'max_relative_difference_to_dense_oracle': error,
    'tiled_component_seconds': tiled_seconds, 'dense_oracle_seconds': dense_seconds,
    'timing_comparability': 'Dense oracle does not build CSR or run per-allocation checks; timings are not a like-for-like speedup comparison.',
    'process_tree_RSS_peak_bytes': None, 'native_NumPy_SciPy_BLAS_packing_workspace_bound_bytes': None,
    'budget_scope': 'Owned explicit NumPy/CSR arrays, including old/new CSR and possible constructor copy; excludes q maps, contribution producers/recipes, Python objects and internal NumPy/SciPy/native packing/workspace. Fresh process-tree gate remains mandatory.',
    'data_kinds': {'timings_and_final_CSR_nbytes': 'measured', 'named_array_bounds': 'derived_from_allocations', 'process_tree_RSS_and_internal_workspace': 'not_run_or_unknown'},
    'qualification': 'Small synthetic exact-algebra/memory-accounting only; no speedup, FE, accuracy, production or 2TB/48h qualification',
}
output = Path(__file__).parent / 'synthetic_component_v3.json'
output.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
assert error < 1e-12
