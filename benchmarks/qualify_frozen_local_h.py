"""V66 final-source focused qualification, no mesh/PDE/factor replay."""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.frozen_local_h_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V66 qualified ABI')
    paths=['src/solvers/frozen_local_h_scope.py','src/solvers/frozen_local_h_study.py','src/solvers/p6_completion_study.py',
        'src/solvers/tetra_body_checkpoint.py','src/postprocessing/paired_field_norms.py','src/runners/port_preparation.py',
        'scripts/run_case.py','src/test/test_frozen_local_h.py','benchmarks/collect_frozen_local_h.py','benchmarks/qualify_frozen_local_h.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_frozen_local_h',
        'src.test.test_tetra_coefficient_action.CoefficientTests','src.test.test_p6_completion.CompletionTests.test_prepared_body_owner_references_are_released_before_output'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v66_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V66 targeted qualification requires diagnosed repair')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V66_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
