"""Focused new mathematics and actual five one-run schema wiring."""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.runners.task042_shared import write_json
from src.solvers.local_subcell_scope import ROOT,window,implementation_hashes


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    from petsc4py import PETSc
    import numpy as np
    if PETSc.ScalarType!=np.complex128 or os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1':raise RuntimeError('V60 qualified ABI')
    paths=['src/solvers/local_subcell_scope.py','src/solvers/local_trace_assembly.py','src/solvers/local_subcell_study.py',
        'src/solvers/subcell_macro_response.py','src/solvers/local_schur_bank.py','src/solvers/subcell_preparation_checkpoint.py','src/solvers/subcell_response_kernel.py','src/solvers/subcell_macro_deployment.py','src/test/test_subcell_response_workflow.py','benchmarks/collect_phase_explicit_accuracy.py','src/test/test_local_subcell.py','benchmarks/qualify_local_subcell.py','benchmarks/collect_local_subcell.py',
        'benchmarks/consume_saved_subcell.py','benchmarks/compact_local_subcell_raw.py','src/test/test_saved_subcell_consumer.py','src/test/test_local_subcell_archive.py',
        'src/solvers/trace_interior_restriction.py','src/solvers/trace_interior_study.py','src/solvers/phase_boundary_checkpoint.py',
        'src/solvers/scattering_accuracy_boundary.py','src/solvers/phase_notch_hp.py','src/runners/port_preparation.py','scripts/run_case.py']
    for p in paths:compile((ROOT/p).read_bytes(),p,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_local_subcell','src.test.test_subcell_response_workflow','src.test.test_local_subcell_archive','src.test.test_saved_subcell_consumer'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v60_*.dat'))]
    rows=[]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=cmd,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows));raise RuntimeError('targeted failure; repair only affected path')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=implementation_hashes()))
    print(json.dumps(dict(status='V60_TARGETED_PASSED',commands=len(rows))))


if __name__=='__main__':main()
