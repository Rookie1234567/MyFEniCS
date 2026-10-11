"""Final clean-source targeted V72 consumption/continuation qualification."""
import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.reused_trace_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':
        raise RuntimeError('V72 qualified native complex ABI')
    paths=['src/solvers/reused_trace_scope.py','src/solvers/reused_trace_admission.py','src/solvers/bounded_trace_study.py',
           'src/solvers/physical_retained_fgmres.py','src/runners/port_preparation.py','scripts/run_case.py',
           'benchmarks/collect_bounded_trace.py','benchmarks/qualify_reused_trace.py','src/test/test_reused_trace.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_reused_trace'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v72_*.dat')))
    rows=[]
    for j,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{j}.stdout').write_text(r.stdout);(folder/f'command{j}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V72 minimal targeted repair required')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V72_TARGETED_PASSED',tests=6,commands=len(rows))))


if __name__=='__main__':main()
