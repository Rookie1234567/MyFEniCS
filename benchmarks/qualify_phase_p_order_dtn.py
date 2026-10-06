"""Focused V54 reader/embedding/schema and final-source ABI qualification."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.phase_p_order_dtn_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);hashes=implementation_hashes()
    from petsc4py import PETSc
    import numpy as np
    import dolfinx,basix,mpi4py,petsc4py,slepc4py
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V54 ABI preflight')
    abi=dict(python=sys.executable,scalar=str(PETSc.ScalarType),integer=str(PETSc.IntType),
        paths={m.__name__:m.__file__ for m in (dolfinx,basix,mpi4py,petsc4py,slepc4py)})
    for name in hashes:
        if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
    paths=['src/solvers/phase_p_order_dtn_scope.py','src/solvers/phase_p_order_dtn.py',
        'src/solvers/phase_p_order_consistency.py','src/solvers/phase_raw_tensor_reader.py',
        'src/solvers/phase_notch_hp.py','src/solvers/phase_notch_hp_modes.py','src/solvers/phase_tensor_checkpoint.py',
        'src/io/phase_notch_hp.py','src/runners/port_preparation.py','scripts/run_case.py',
        'src/test/test_phase_p_order_dtn.py','benchmarks/collect_phase_p_order_dtn.py','benchmarks/check_phase_p_order_dtn.py',
        'src/solvers/scattering_accuracy_boundary.py','src/solvers/phase_explicit_accuracy.py']
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_phase_p_order_dtn'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v54_*.dat'))]
    rows=[]
    for i,command in enumerate(commands):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(result.stdout);(folder/f'command{i}.stderr').write_text(result.stderr)
        rows.append(dict(command=command,returncode=result.returncode))
        if result.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows,implementation_hashes=hashes,abi=abi))
            raise RuntimeError('V54 focused qualification failed; preserve and minimally repair')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=hashes,abi=abi,
        watchdog='unchanged subreaper/deadline core; inherited V53 timeout cleanup witness; V54 resolved memory verified',scientific_actions=0))
    print(json.dumps(dict(status='V54_QUALIFICATION_PASSED',commands=len(rows))))


if __name__=='__main__':main()
