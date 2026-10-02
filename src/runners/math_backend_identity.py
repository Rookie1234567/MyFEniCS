"""One boundary read of loaded math libraries; never used for RSS supervision."""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path


def component_factory_identity(root):
    """Bind configured implementations; runtime audits establish actual use."""
    factories = {
        'src/solvers/fullspace_metric_positive_diagonal.py': 'build_reference_metric_positive_diagonal',
        'src/solvers/fullspace_fused_split_volume.py': 'FullspaceFusedSplitVolumeAction',
        'src/solvers/fullspace_n1e_sum_factor.py': 'N1ESumFactorizedAction',
        'src/solvers/physical_equivalent_fast.py': 'build_packed_physical_action',
        'src/solvers/physical_light_setup.py': 'build_light_h6_setup',
        'src/solvers/hcurl_blocked_gram_tensor.py': 'HcurlBlockedGramTensor',
        'src/solvers/p4_cell_condensed_inverse.py': 'P4CellCondensedInverse / P4RefinementLedger',
        'src/runners/physical_retained_condensed_v20.py': 'RetainedCondensedRuntime / run_retained_condensed_workflow',
    }
    rows = []
    for path, factory in factories.items():
        raw = (Path(root)/path).read_bytes()
        rows.append({'path': path, 'factory': factory,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
    return {'scope': 'configured factories; H6-only does not construct A4/A6/p4 factor',
            'files': rows}


def math_backend_identity():
    """Query already-loaded OpenBLAS runtimes without changing their controls."""
    paths = set()
    try:
        for line in Path('/proc/self/maps').read_text().splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) == 6 and fields[5].startswith('/'):
                path = fields[5]
                name = Path(path).name.lower()
                if any(word in name for word in ('blas', 'mumps', 'petsc', 'gomp', 'iomp')):
                    paths.add(path)
    except OSError:
        pass
    libraries = []
    for path in sorted(paths):
        row = {'path': path}
        if 'openblas' in Path(path).name.lower():
            library = ctypes.CDLL(path)
            for key, stem, result_type in (
                ('configured_threads', 'get_num_threads', ctypes.c_int),
                ('parallel_runtime', 'get_parallel', ctypes.c_int),
                ('build_config', 'get_config', ctypes.c_char_p),
            ):
                value = None
                for prefix in ('openblas_', 'scipy_openblas_'):
                    for suffix in ('', '64_'):
                        query = getattr(library, prefix+stem+suffix, None)
                        if query is not None:
                            query.argtypes = []
                            query.restype = result_type
                            value = query()
                            if isinstance(value, bytes):
                                value = value.decode(errors='replace')
                            break
                    if value is not None:
                        break
                row[key] = value
        libraries.append(row)
    threads = []
    for entry in sorted(Path('/proc/self/task').glob('[0-9]*')):
        try:
            status = dict(line.split(':', 1) for line in (entry/'status').read_text().splitlines())
            threads.append({'tid': int(entry.name), 'state': status['State'].strip(),
                            'cpus_allowed_list': status['Cpus_allowed_list'].strip()})
        except OSError:
            continue
    return {'scope': 'single process boundary; loaded library queries, not a speedup claim',
            'libraries': libraries, 'process_threads': threads,
            'process_affinity': sorted(os.sched_getaffinity(0)),
            'environment_threads': {name: os.environ.get(name) for name in
                ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')},
            'controls_modified': False, 'pss_or_smaps_read': False,
            'mumps_shared_memory_capability': 'unknown; no inference from environment alone'}
