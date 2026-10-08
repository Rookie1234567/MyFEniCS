"""Bounded final-source targeted qualification and actual V62 dat schemas."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.independent_tetra_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    from petsc4py import PETSc
    import numpy as np
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('qualified V62 native ABI')
    paths=['src/solvers/independent_tetra_reference.py','src/solvers/independent_tetra_fields.py','src/solvers/independent_tetra_study.py',
        'src/solvers/independent_tetra_scope.py','src/io/independent_tetra_reference.py','src/runners/port_preparation.py',
        'src/test/test_independent_tetra_reference.py','src/test/test_independent_tetra_saved_checks.py','benchmarks/check_independent_tetra.py',
        'benchmarks/qualify_independent_tetra.py','benchmarks/collect_independent_tetra.py','scripts/run_case.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_independent_tetra_reference','src.test.test_independent_tetra_saved_checks'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v62_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True);(folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V62 targeted path failed: repair affected part')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V62_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
