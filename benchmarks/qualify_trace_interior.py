"""Only new restricted-space tests, lint, compile and four actual dat inputs."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.trace_interior_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    from petsc4py import PETSc
    import numpy as np
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V59 qualified ABI')
    paths=['src/solvers/trace_interior_scope.py','src/solvers/trace_interior_restriction.py','src/solvers/trace_interior_study.py',
        'src/test/test_trace_interior.py','benchmarks/qualify_trace_interior.py','benchmarks/collect_trace_interior.py','benchmarks/collect_phase_deployment.py','benchmarks/collect_common_weak_phase.py',
        'src/constraints/floquet_3d.py','src/constraints/high_order_floquet_trace.py','src/solvers/phase_explicit_accuracy.py',
        'src/solvers/phase_notch_hp.py','src/runners/port_preparation.py','src/io/phase_notch_hp.py','scripts/run_case.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_trace_interior'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v59_*.dat'))]
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('targeted failure; fix only affected path')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V59_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
