"""Focused final-source qualification, without a scientific solve."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.harmonic_trace_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V74 qualified native ABI')
    paths=['src/solvers/harmonic_trace_scope.py','src/solvers/harmonic_trace_coarse.py','src/solvers/harmonic_trace_study.py',
        'src/solvers/bounded_trace_pc.py','src/solvers/bounded_trace_study.py','src/runners/port_preparation.py','scripts/run_case.py',
        'benchmarks/qualify_harmonic_trace.py','benchmarks/collect_harmonic_trace.py','benchmarks/collect_restart_feedback.py','src/test/test_harmonic_trace.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_harmonic_trace'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v74_*.dat')))
    rows=[]
    for j,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{j}.stdout').write_text(r.stdout);(folder/f'command{j}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V74 targeted failure: minimal repair')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    match=re.search(r'Ran (\d+) tests?',(folder/'command0.stderr').read_text())
    if match is None:raise RuntimeError('unittest count is not available from actual run')
    print(json.dumps(dict(status='V74_TARGETED_PASSED',tests=int(match.group(1)),commands=len(rows))))


if __name__=='__main__':main()
