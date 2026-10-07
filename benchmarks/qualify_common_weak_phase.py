"""Final-source targeted checks under the existing independent supervisor."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.common_weak_phase_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);hashes=implementation_hashes()
    from petsc4py import PETSc
    import numpy as np
    import dolfinx,basix,mpi4py,petsc4py,slepc4py
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V57 native complex ABI')
    abi=dict(python=sys.executable,scalar=str(PETSc.ScalarType),integer=str(PETSc.IntType),paths={m.__name__:m.__file__ for m in (dolfinx,basix,mpi4py,petsc4py,slepc4py)})
    paths=['src/solvers/common_weak_phase.py','src/solvers/common_weak_phase_scope.py','src/solvers/common_continuous_weak.py',
        'src/solvers/hcurl_affine_phase_tensor.py','src/solvers/phase_reference_provider.py','src/runners/port_preparation.py',
        'scripts/run_case.py','src/solvers/phase_notch_hp.py','src/solvers/phase_explicit_accuracy.py',
        'src/test/test_common_weak_phase.py','benchmarks/qualify_common_weak_phase.py','benchmarks/collect_common_weak_phase.py',
        'benchmarks/collect_phase_explicit_accuracy.py']
    for name in paths:compile((ROOT/name).read_bytes(),name,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_common_weak_phase'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v57_*.dat'))]
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows,abi=abi,implementation_hashes=hashes))
            raise RuntimeError('V57 targeted failure; repair affected check only')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,abi=abi,implementation_hashes=hashes,new_solve_count=0))
    print(json.dumps(dict(status='V57_QUALIFICATION_PASSED',commands=len(rows))))


if __name__=='__main__':main()
