"""Final-source targeted compile/algebra/schema; no real PDE inside tests."""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.assembly_tetra_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V70 qualified complex ABI')
    paths=['src/solvers/tetra_cell_kernel.py','src/solvers/tetra_assembly_packet.py','src/solvers/assembly_tetra_scope.py',
        'src/solvers/assembly_tetra_study.py','src/solvers/independent_tetra_reference.py','src/solvers/independent_tetra_study.py',
        'src/runners/port_preparation.py','scripts/run_case.py','benchmarks/qualify_assembly_tetra.py',
        'benchmarks/collect_assembly_tetra.py','src/test/test_tetra_assembly_packet.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_tetra_assembly_packet'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v70_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V70 targeted failure: locate minimally and continue')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V70_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
