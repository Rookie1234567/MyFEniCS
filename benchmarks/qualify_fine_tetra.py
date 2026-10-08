"""Minimal final-source regression/schema qualification, under shared supervisor."""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.fine_tetra_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V63 qualified complex/int64 ABI')
    hashes=implementation_hashes()
    paths=[p for p in hashes if p.endswith('.py') and ('tetra' in p or p in ('scripts/run_case.py','src/runners/port_preparation.py'))]
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_fine_tetra','src.test.test_independent_tetra_reference'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v63_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(result.stdout);(folder/f'command{i}.stderr').write_text(result.stderr)
        rows.append(dict(command=cmd,returncode=result.returncode))
        if result.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V63 affected test/entry requires repair')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=hashes))
    print(json.dumps(dict(status='V63_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
