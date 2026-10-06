"""Final-source focused V56 wiring; no old campaign or PDE replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.phase_saved_closure_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);hashes=implementation_hashes()
    from petsc4py import PETSc
    import numpy as np
    import dolfinx,basix,mpi4py,petsc4py,slepc4py
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V56 native ABI')
    abi=dict(python=sys.executable,scalar=str(PETSc.ScalarType),integer=str(PETSc.IntType),paths={m.__name__:m.__file__ for m in (dolfinx,basix,mpi4py,petsc4py,slepc4py)})
    paths=['src/postprocessing/phase_volume_quadrature.py','src/solvers/phase_saved_closure.py','src/solvers/phase_saved_closure_scope.py',
        'src/solvers/phase_saved_uncondensed.py','src/solvers/phase_target_bridge.py','src/solvers/phase_evaluation_cache.py',
        'src/solvers/phase_notch_hp_fields.py','src/solvers/phase_notch_hp.py','src/solvers/scattering_accuracy_fields.py',
        'src/solvers/phase_explicit_accuracy_fields.py','src/runners/port_preparation.py','scripts/run_case.py',
        'src/test/test_phase_saved_closure.py','benchmarks/qualify_phase_saved_closure.py','benchmarks/collect_phase_saved_closure.py',
        'benchmarks/collect_phase_explicit_accuracy.py']
    for name in paths:compile((ROOT/name).read_bytes(),name,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_phase_saved_closure'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v56_*.dat'))]
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows,abi=abi,implementation_hashes=hashes))
            raise RuntimeError('V56 focused test failed; preserve and minimally repair')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,abi=abi,implementation_hashes=hashes,new_solve_count=0,new_factor_count=0))
    print(json.dumps(dict(status='V56_QUALIFICATION_PASSED',commands=len(rows))))


if __name__=='__main__':main()
