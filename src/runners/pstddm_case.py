"""Thin opt-in orchestration for one explicitly frozen PSTDDM pilot case."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def plain(value):
    import numpy as np
    from collections.abc import Mapping
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items() if k != 'z'}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, complex):
        return [value.real, value.imag]
    return value


def run_pstddm(input_path, *, dry_run=False):
    if not __debug__ or os.environ.get('PYTHONOPTIMIZE'):
        raise RuntimeError('Optimization mode is forbidden')
    from src.io.input_loader import load_dat_input
    loaded = load_dat_input(input_path)
    doc = dict(loaded.document)
    fixed = {'model': 'pstddm_partition_pilot', 'degree': 2,
             'workflow': 'source_transfer_initial_then_fgmres', 'restart': 30,
             'max_iterations': 100, 'true_residual_tolerance': 1e-8,
             'reference_tolerance': 1e-10, 'field_E_tolerance': 1e-4, 'field_H_tolerance': 1e-3,
             'pml_thickness_nm': 10., 'pml_cells_per_side': 2, 'pml_grading_ratio': 1.25,
             'pml_nominal_amplitude': .01, 'factor_strategy': 'cache_all_local_plus_global_mass'}
    if any(doc.get(key) != value for key, value in fixed.items()):
        raise ValueError('Input changed the frozen pilot configuration')
    if doc['mode'] not in ('correctness', 'direct', 'candidate') or doc['partitions'] not in (2, 4):
        raise ValueError('Unsupported pilot mode/partition')
    if set(doc) != set(fixed)|{'case_id', 'mode', 'partitions', 'reference_case'}:
        raise ValueError('Unexpected pilot input keys')
    if dry_run:
        return {'status': 'VALID_CONFIGURATION_NOT_RUN', 'config': doc}
    if os.environ.get('PSTDDM_SUPERVISOR_PID') != str(os.getppid()):
        raise RuntimeError('Formal cases require the bounded PSTDDM supervisor')
    out = Path(os.environ['PSTDDM_OUTPUT']).resolve()
    root = Path(__file__).resolve().parents[2]
    assert out.parent == root/'benchmarks/artifacts/pstddm_partition_pilot'
    import numpy as np
    from scipy import sparse
    from src.solvers.pstddm_native import global_system, build_partition
    from src.solvers.pstddm_comparison import direct_reference, candidate
    events = []

    def gate(stage, future=0):
        status = dict(x.split(':', 1) for x in Path('/proc/self/status').read_text().splitlines() if ':' in x)
        rss = int(status['VmRSS'].split()[0])*1024
        mem = {k: int(v.split()[0])*1024 for k, v in (x.split(':', 1) for x in Path('/proc/meminfo').read_text().splitlines())}
        event = {'stage': stage, 'elapsed': time.monotonic()-start, 'rss_bytes': rss,
                 'planned_extra_bytes': int(future), 'reserve_bytes': 512 << 20,
                 'available_bytes': mem['MemAvailable']}
        events.append(event)
        (out/'phase_gates.json').write_text(json.dumps(events, indent=2))
        print(json.dumps(event), flush=True)
        assert rss+int(future)+(512 << 20) < 2 << 30, '2GiB phase cap including reserve'
        assert mem['MemAvailable'] > int(future)+(1 << 30)+(512 << 20), 'system phase available reserve'
        assert mem['MemAvailable'] > (2 << 30)+(512 << 20), 'original 2.5GiB available floor'
        assert mem['MemTotal']-mem['MemAvailable']+int(future)+(512 << 20) < 6 << 30, '6GiB system stage cap'
        assert int(status.get('VmSwap', '0 kB').split()[0]) == 0, 'task swap forbidden'

    start = time.monotonic()
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    tracked = subprocess.check_output(['git','ls-files','src','scripts'],cwd=root,text=True).splitlines()
    source_hashes = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in tracked}
    (out/'source_hashes.json').write_text(json.dumps(source_hashes,indent=2))
    (out/'input_original.dat').write_bytes(loaded.raw_input_bytes)
    system = global_system(out, doc['degree'], gate)
    import sys
    import dolfinx
    import basix
    from petsc4py import PETSc
    from mpi4py import MPI
    (out/'environment.json').write_text(json.dumps({'python':sys.executable,'python_version':sys.version,
        'dolfinx':dolfinx.__version__,'basix':basix.__version__,'numpy':np.__version__,
        'PETSc':PETSc.Sys.getVersion(),'PETSc_ScalarType':str(np.dtype(PETSc.ScalarType)),
        'PETSc_IntType':str(np.dtype(PETSc.IntType)),'MPI_library':MPI.Get_library_version(),
        'threads':{key:os.environ[key] for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']}},indent=2))
    physical = plain(system.p.cfg.as_jsonable())
    physical_bytes = json.dumps(physical, sort_keys=True, separators=(',', ':')).encode()
    physical_sha = hashlib.sha256(physical_bytes).hexdigest()
    (out/'resolved_config.json').write_text(json.dumps({'pilot': doc, 'global': physical,
       'global_pml_disabled': True, 'unused_global_pml_alpha': system.p.cfg.pml_alpha}, indent=2))
    manifest = {'base_sha': '2c7aa97f4746c5de0545cf511908321b356a74df', 'source_sha': source_sha,
                'input_sha256': loaded.input_sha256, 'physical_sha256': physical_sha,
                'mode': doc['mode'], 'case_id': doc['case_id'], 'global_FE_independent': system.A.shape[0],
                'global_FE_raw': system.T.shape[0], 'auxiliary': system.C.shape[1], 'matrix_rows': system.full.shape[0],
                'mpi': 1, 'threads': 1, 'scope': 'coarse p2 same-discrete algorithm pilot; not physical convergence'}
    (out/'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    for name, matrix in [('A', system.A), ('C', system.C), ('D', system.D), ('mass', system.M),
                         ('curl_gram', system.K), ('T', system.T), ('full', system.full),
                         ('raw_A',system.raw_A),('raw_C',system.dtn.C),('raw_D',system.dtn.D)]:
        sparse.save_npz(out/(name+'.npz'), matrix)
    np.save(out/'rhs.npy', system.rhs)
    np.save(out/'physical_rhs.npy',system.rhs)
    np.save(out/'raw_f.npy',system.raw_f)
    np.save(out/'physical_raw_f.npy',system.raw_f)
    np.save(out/'raw_aux_rhs.npy',system.rhs[system.A.shape[0]:])
    mpc=system.p.floquet.mpc
    coefficients,offsets=mpc.coefficients()
    np.savez(out/'raw_mpc.npz',slaves=mpc.slaves[:mpc.num_local_slaves],
             masters=mpc.masters.array,master_offsets=mpc.masters.offsets,
             coefficients=coefficients,coefficient_offsets=offsets)
    (out/'mode_manifest.json').write_text(json.dumps(plain({'metadata': system.dtn.metadata,
        'modes': [vars(m) for m in system.dtn.modes]}), indent=2))
    if doc['mode'] == 'direct':
        result = direct_reference(system, gate, out)
    else:
        if doc['mode'] == 'correctness':
            # Nonzero all-layer FE and auxiliary manufactured algebraic forcing.
            expected = np.sin(np.arange(system.full.shape[0])*.13)+1j*np.cos(np.arange(system.full.shape[0])*.17)
            system.rhs = system.full@expected
            np.save(out/'rhs.npy', system.rhs)
            np.save(out/'raw_f.npy',system.raw_A@(system.T@expected[:system.A.shape[0]])+system.dtn.C@expected[system.A.shape[0]:])
            np.save(out/'raw_aux_rhs.npy',system.rhs[system.A.shape[0]:])
            np.save(out/'manufactured_expected.npy', expected)
            reference = direct_reference(system, gate, out)
            manufactured_reference_error=float(np.linalg.norm(reference['z']-expected)/np.linalg.norm(expected))
            if manufactured_reference_error>1e-9:
                raise RuntimeError(f'Manufactured direct field mismatch {manufactured_reference_error}')
        else:
            ref = out.parent/doc['reference_case']
            identity = json.loads((ref/'run_manifest.json').read_text())
            if identity['physical_sha256'] != physical_sha:
                raise ValueError('Reference physical identity differs')
            # Exact system and input arrays, rather than just matching R/T.
            for name, matrix in [('A',system.A), ('C',system.C), ('D',system.D), ('T',system.T),
                                 ('mass',system.M),('curl_gram',system.K)]:
                previous = sparse.load_npz(ref/(name+'.npz'))
                delta = previous-matrix
                if delta.nnz and np.max(abs(delta.data)) != 0:
                    raise ValueError(f'Reference {name} is not array-identical')
            if not np.array_equal(np.load(ref/'rhs.npy'),system.rhs):
                raise ValueError('Reference RHS differs')
            summary = json.loads((ref/'run_summary.json').read_text())
            reference = {'z': np.load(ref/'reference_solution.npz')['z'],
                         'true_residual': summary['result']['true_residual'],
                         'diagnostics': json.loads((ref/'reference_diagnostics.json').read_text())}
            manifest['reference_identity'] = identity
            (out/'run_manifest.json').write_text(json.dumps(manifest, indent=2))
        core, pairs, partition = build_partition(system, doc['partitions'], gate)
        (out/'partition_audit.json').write_text(json.dumps(plain(partition), indent=2))
        for i,pair in enumerate(pairs):
            for name,matrix in [('map',pair.S),('commutator_plus',pair.plus),('commutator_minus',pair.minus),('L',pair.L)]:
                sparse.save_npz(out/f'pair{i}_{name}.npz',matrix)
        gate('candidate_recovery_reserve',256 << 20)
        result = candidate(system, core, reference, out)
        if doc['mode']=='correctness':
            result['manufactured_direct_coefficient_relative']=manufactured_reference_error
            result['manufactured_candidate_coefficient_relative']=float(np.linalg.norm(result['z']-expected)/np.linalg.norm(expected))
        partition['actual_solve_counts'] = [x.solve_count for x in pairs]
        partition['actual_solve_seconds'] = [x.solve_seconds for x in pairs]
        (out/'partition_audit.json').write_text(json.dumps(plain(partition), indent=2))
    summary = {'result': plain(result), 'global_setup_seconds':system.setup_seconds,
               'numerical_wall_seconds': time.monotonic()-start, 'physical_sha256': physical_sha,
               'source_sha': source_sha, 'status':'COMPLETED_NUMERICAL_REVIEW_PENDING'}
    (out/'run_summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    hashes = {}
    for file in out.iterdir():
        if file.is_file() and file.name not in ('artifact_hashes.json', 'stdout.log', 'stderr.log'):
            hashes[file.name] = {'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'bytes':file.stat().st_size}
    (out/'artifact_hashes.json').write_text(json.dumps(hashes, indent=2))
    return summary
