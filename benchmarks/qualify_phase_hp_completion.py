"""Focused V53 final-source wiring, ABI and independent deadline cleanup."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.phase_hp_completion_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);hashes=implementation_hashes()
    from petsc4py import PETSc
    import numpy as np
    import dolfinx,basix,mpi4py,petsc4py,slepc4py
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V53 ABI preflight')
    abi=dict(python=sys.executable,scalar=str(PETSc.ScalarType),integer=str(PETSc.IntType),
        paths={m.__name__:m.__file__ for m in (dolfinx,basix,mpi4py,petsc4py,slepc4py)})
    for n in hashes:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec')
    paths=[n for n in hashes if ('phase' in n and n.endswith('.py'))]
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_phase_hp_completion'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',
         *paths,'src/runners/port_preparation.py','scripts/run_case.py']]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v53_*.dat'))]
    rows=[]
    for i,c in enumerate(commands):
        r=subprocess.run(c,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=c,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows,implementation_hashes=hashes,abi=abi))
            raise RuntimeError('focused qualification failed; preserve and minimally repair')
    from benchmarks.subreaper_watchdog import supervise
    result=supervise([sys.executable,'-c','import subprocess,time;subprocess.Popen(["sleep","20"]);time.sleep(20)'],folder/'watchdog_test',wall_seconds=1,interval=.1,timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=128*2**20,include_pss=False)
    if not result['descendants_cleared'] or result['classification']=='COMPLETED':raise RuntimeError('deadline cleanup failed')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=hashes,watchdog_test=result,abi=abi,scientific_actions=0))
    print(json.dumps(dict(status='V53_QUALIFICATION_PASSED',commands=len(rows))))


if __name__=='__main__':main()
