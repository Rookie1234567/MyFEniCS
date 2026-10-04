"""Paid final static/related regression; no real operator or factor loads."""
import json
import os
from pathlib import Path
import subprocess
import sys

from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers import full_input_online_window as window
from src.solvers.neural_fe_action_packet import file_hash


def main():
    from src.runners.actual_loss_block_descent import _pure_blas_threads
    folder = Path(os.environ['TASK042_V35_AUX_DIRECTORY'])
    window.guard_worker_parent()
    paths = {p for p in window.implementation_hashes() if p.endswith('.py')}
    paths.update(('src/runners/orthonormal_trace_reprofile.py',
                  'benchmarks/verify_full_input_online.py',
                  'benchmarks/finalize_full_input_online.py',
                  'benchmarks/package_full_input_online.py',
                  'src/test/test_task042_v35_cache.py'))
    for name in sorted(paths):
        compile((ROOT / name).read_bytes(), name, 'exec')
    ruff = Path('/home/fenics/Projects/Metrology/.venv/bin/ruff')
    # Compile dependencies, but lint the new V35 modules rather than cleaning
    # unrelated historical imports in the shared cycle/old V14 runner.
    ruff_paths = [p for p in sorted(paths)
                  if 'full_input_online' in p or 'test_task042_v35_' in p]
    targets = ['src/test/test_task042_v35_online.py', 'src/test/test_task042_v35_cache.py',
               'src/test/test_26_documentation_contract.py']
    if '--export-repair' in sys.argv:
        targets = [
            'src/test/test_task042_v35_online.py::test_actual_dat_kernel_runner_return_checkpoint_independent_checker',
            'src/test/test_task042_v35_online.py::test_independent_checker_rejects_hash_inventory_and_fakepass',
        ]
    commands = [
        [str(ruff), 'check', '--select', 'E9,F', *ruff_paths],
        [sys.executable, '-m', 'benchmarks.package_full_input_online'],
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
         '--basetemp=' + str(folder / 'fixtures'),
         *targets,
         '--junitxml=' + str(folder / 'pytest.xml')],
    ]
    results = []
    for number, command in enumerate(commands):
        with (folder / f'check{number}.stdout').open('w') as out, \
                (folder / f'check{number}.stderr').open('w') as err:
            result = subprocess.run(command, stdout=out, stderr=err)
        results.append(dict(command=command, returncode=result.returncode))
        if result.returncode:
            break
    record = dict(status='PASSED' if all(x['returncode'] == 0 for x in results) else 'FAILED',
                  source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  compiled_files=sorted(paths), results=results, threads=_pure_blas_threads(),
                  affinity=sorted(os.sched_getaffinity(0)), interpreter=sys.executable,
                  ruff_binary_sha256=file_hash(ruff), ruff_read_only_reuse=True,
                  targeted_export_repair='--export-repair' in sys.argv,
                  new_real_actions=0, new_factor_reads=0, no_reference_read=True)
    write_json(folder / 'final_static_tests.json', record)
    print(json.dumps(dict(status=record['status'], path=str(folder / 'final_static_tests.json'))))
    return 0 if record['status'] == 'PASSED' else 1


if __name__ == '__main__':
    sys.exit(main())
