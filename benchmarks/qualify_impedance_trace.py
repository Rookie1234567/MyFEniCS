"""Final clean-source narrow qualification, no physical PDE or numeric."""
import json
import os
import subprocess
import sys
from pathlib import Path

from src.solvers import impedance_trace_scope as scope
from src.runners.task042_shared import write_json


def main():
    import numpy as np
    from petsc4py import PETSc
    scope.window.guard_worker_parent()
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':
        raise RuntimeError('V77 native ABI')
    folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    paths=['src/solvers/impedance_trace_scope.py','src/solvers/impedance_trace_study.py',
        'src/solvers/physical_impedance_patch.py','src/solvers/controlled_trace_study.py',
        'src/solvers/physical_retained_fgmres.py','src/runners/port_preparation.py','scripts/run_case.py',
        'benchmarks/collect_controlled_trace.py','benchmarks/check_impedance_patch.py','benchmarks/qualify_impedance_trace.py',
        'src/test/test_physical_impedance_patch.py']
    for p in paths:compile((scope.ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_physical_impedance_patch'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v77_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=scope.ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        write_json(folder/'tests.json',dict(status='RUNNING' if not r.returncode else 'FAILED',commands=rows))
        if r.returncode:raise RuntimeError('V77 narrow failure: fix affected path and continue')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=scope.implementation_hashes()))
    print(json.dumps(dict(status='V77_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
