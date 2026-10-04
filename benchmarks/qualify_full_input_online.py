"""Paid, supervised final-source targeted qualification; no real LU/PDE reads."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers import full_input_online_window as window
from src.solvers.neural_fe_action_packet import file_hash


def main():
    from src.runners.actual_loss_block_descent import _pure_blas_threads
    folder=Path(os.environ['TASK042_V35_AUX_DIRECTORY'])
    window.guard_worker_parent()
    began=time.monotonic();hashes=window.implementation_hashes()
    if os.environ.get('TASK042_ENV_MODE')!='pure' or Path(sys.executable).parent!=ROOT/'.venv/bin':
        raise RuntimeError('V35 qualification activation/interpreter')
    # Compile real final files, not merely import a fixture that may skip them.
    for filename in hashes:
        if filename.endswith('.py'):compile((ROOT/filename).read_bytes(),filename,'exec')
    command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--basetemp='+str(folder/'fixtures'),
        'src/test/test_task042_v35_online.py',
        'src/test/test_neural_fe_action_packet.py',
        'src/test/test_task042_v21_recycling.py::test_class_batch_exact_complex_interleaved_singletons_tail_and_readonly',
        'src/test/test_task042_v18_completion.py::test_return_survives_close_audit_writer_failures_no_arnoldi_replay',
        'src/test/test_task042_v18_completion.py::test_atomic_writer_failure_and_nonfinite_hash_rollback',
        '--junitxml='+str(folder/'pytest.xml')]
    with (folder/'pytest.stdout').open('w') as out,(folder/'pytest.stderr').open('w') as err:
        completed=subprocess.run(command,stdout=out,stderr=err)
    receipt=dict(status='PASSED' if completed.returncode==0 else 'FAILED',
        command=command,returncode=completed.returncode,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        implementation_hashes=hashes,threads=_pure_blas_threads(),
        environment_mode=os.environ['TASK042_ENV_MODE'],interpreter=sys.executable,
        affinity=sorted(os.sched_getaffinity(0)),compiled_files=list(hashes),
        ruff_availability='AVAILABLE' if importlib.util.find_spec('ruff') else 'NOT_INSTALLED_NO_UPGRADE',
        output_hashes={p.name:file_hash(p) for p in folder.glob('pytest.*')},
        helper_wall_seconds=time.monotonic()-began,real_factor_reads=0,new_real_actions=0)
    write_json(folder/'qualification.json',receipt)
    if completed.returncode==0:
        write_json(window.TMP/'pre_qualification.json',dict(status='PASSED',implementation_hashes=hashes,
            test_receipt=dict(path=str(folder/'qualification.json'),sha256=file_hash(folder/'qualification.json'))))
    print(json.dumps(dict(status=receipt['status'],receipt=str(folder/'qualification.json'))),flush=True)
    return completed.returncode


if __name__=='__main__':
    sys.exit(main())
