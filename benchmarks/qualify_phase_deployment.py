"""Targeted final-source tests in the existing supervised V58 auxiliary."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.phase_deployment_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    from petsc4py import PETSc
    import numpy as np
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V58 native complex ABI')
    paths=['src/solvers/phase_deployment.py','src/solvers/phase_deployment_scope.py','src/solvers/phase_boundary_checkpoint.py',
        'src/solvers/phase_deployment_defect.py','src/solvers/phase_notch_hp.py','src/solvers/phase_notch_hp_fields.py',
        'src/solvers/phase_explicit_accuracy.py','src/runners/port_preparation.py','scripts/run_case.py','src/io/phase_notch_hp.py',
        'src/test/test_phase_deployment.py','benchmarks/qualify_phase_deployment.py','benchmarks/collect_phase_deployment.py',
        'benchmarks/collect_common_weak_phase.py','benchmarks/collect_phase_explicit_accuracy.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    cmds=[[sys.executable,'-m','unittest','-q','src.test.test_phase_deployment'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    cmds += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v58_*.dat'))]
    rows=[]
    for i,cmd in enumerate(cmds):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True);(folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('targeted qualification failure; repair affected check only')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V58_QUALIFICATION_PASSED',commands=len(rows))))


if __name__=='__main__':main()
