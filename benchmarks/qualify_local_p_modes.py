"""Final-source V67 targeted tests and all five real dat validations."""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.local_p_mode_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    import numpy as np
    from petsc4py import PETSc
    if PETSc.ScalarType!=np.complex128 or PETSc.IntType!=np.int64 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V67 qualified ABI')
    paths=['src/solvers/local_p_mode_scope.py','src/solvers/local_p_mode_study.py','benchmarks/collect_local_p_modes.py',
        'benchmarks/collect_frozen_local_h.py','src/runners/port_preparation.py','src/runners/preparation_interruption.py','scripts/run_case.py','src/test/test_local_p_modes.py','benchmarks/qualify_local_p_modes.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_local_p_modes',
        'src.test.test_frozen_local_h.FrozenLocalTests.test_dual_denominators_keep_one_numerator_and_all_complex_components',
        'src.test.test_p6_completion.CompletionTests.test_prepared_body_owner_references_are_released_before_output'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands.extend([sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v67_*.dat')))
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('V67 targeted failure: diagnose before continuation')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V67_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
