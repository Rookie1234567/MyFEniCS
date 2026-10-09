"""Final-source targeted qualification, no PDE or closed-window consumption."""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.p6_completion_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V65 qualified ABI')
    paths=['src/solvers/tetra_coefficient_action.py','src/solvers/tetra_body_checkpoint.py','src/solvers/p6_completion_scope.py',
        'src/solvers/p6_completion_study.py','src/solvers/independent_tetra_reference.py','src/solvers/independent_tetra_study.py',
        'src/solvers/phase_explicit_accuracy_capacity.py',
        'src/solvers/local_h_pilot_scope.py','src/runners/port_preparation.py','scripts/run_case.py',
        'src/test/test_tetra_coefficient_action.py','src/test/test_p6_completion.py','benchmarks/collect_p6_completion.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_tetra_coefficient_action','src.test.test_p6_completion',
        'src.test.test_local_h_pilot.LocalHPilotTests.test_rejected_entry_and_same_source_retry_costs_are_paid_once'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v65_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V65 targeted qualification requires diagnosed repair')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V65_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
