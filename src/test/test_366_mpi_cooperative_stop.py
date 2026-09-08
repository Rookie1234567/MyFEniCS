"""Real MPI1 process lifecycle, without PETSc, FE objects or a PDE solve."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def run_mpi_stop_fixture(tmp_path, mode, *, cooperative):
    worker = tmp_path/'worker.py'
    worker.write_text('''
import json,os,signal,time
from pathlib import Path
from mpi4py import MPI
root=Path(__file__).parent
requested=[]
def stop(signum,frame):
    requested.append(signum)
    (root/'requests.json').write_text(json.dumps(requested))
signal.signal(signal.SIGTERM,stop)
pid=os.getpid()
ticks=int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
if os.environ['STOP_FIXTURE_MODE']=='stale_identity': ticks+=1
phase=dict(phase='solve',stage='inside_PC',phase_started_monotonic=time.monotonic(),
           application_worker=dict(pid=pid,start_ticks=ticks))
(root/'phase.json').write_text(json.dumps(phase))
(root/'ready.json').write_text(json.dumps(dict(pid=pid,rank=MPI.COMM_WORLD.rank)))
deadline=time.monotonic()+2.1
while time.monotonic()<deadline:
    time.sleep(.02)
if os.environ['STOP_FIXTURE_MODE']=='noncooperative':
    while True: time.sleep(.02)
if requested:
    (root/'safe_marker').write_text('current PC completed')
    (root/'checkpoint.json').write_text(json.dumps(dict(solution_only=True,iteration=1)))
    (root/'minimum_summary.json').write_text(json.dumps(dict(status='CONTROLLED_STOP',last_safe_iteration=1)))
else:
    raise RuntimeError('fixture expected performance-stop request')
MPI.COMM_WORLD.Barrier()
''')
    monitor = '''
import json,os,sys
from pathlib import Path
import benchmarks.subreaper_watchdog as watchdog
root=Path(sys.argv[1]);mode=sys.argv[2];cooperative=sys.argv[3]=='True'
original=watchdog.process_tree_snapshot
def sample(*args):
    result=original(*args)
    if mode=='resource' and (root/'ready.json').exists(): result['rss_bytes']=10**15
    return result
watchdog.process_tree_snapshot=sample
kwargs=dict(cooperative_performance_stop=True) if cooperative else {}
result=watchdog.supervise(['/usr/bin/mpiexec','-n','1',sys.executable,str(root/'worker.py')],
    root/'watchdog',wall_seconds=20,solve_seconds=.2,phase_path=root/'phase.json',interval=.05,
    grace_seconds=3,hard_stop_immediate=True,worker_environment={'STOP_FIXTURE_MODE':mode},**kwargs)
print(json.dumps(result))
'''
    process = subprocess.run([sys.executable, '-c', monitor, str(tmp_path), mode, str(cooperative)],
                             text=True, capture_output=True, env=os.environ.copy())
    assert process.returncode == 0, process.stdout+process.stderr
    summary = json.loads((tmp_path/'watchdog/summary.json').read_text())
    assert summary['descendants_cleared'] and not summary['remaining_child_pids']
    assert all(not Path(f'/proc/{pid}').exists() for pid in summary['observed_child_pids'])
    print('MPI fixture',mode,'cooperative',cooperative,'summary',json.dumps(summary),flush=True)
    return summary


def test_legacy_mpi_tree_sigterm_preempts_safe_worker(tmp_path):
    summary=run_mpi_stop_fixture(tmp_path,'cooperative',cooperative=False)
    assert summary['classification']=='PERFORMANCE_CONTROLLED_STOP'
    assert summary['leader_exit_code'] != 0
    assert not (tmp_path/'minimum_summary.json').exists()
    assert not (tmp_path/'safe_marker').exists()


@pytest.mark.parametrize('mode', ['cooperative','noncooperative','resource','stale_identity'])
def test_opt_in_mpi_application_soft_stop_and_hard_gates(tmp_path,mode):
    summary=run_mpi_stop_fixture(tmp_path,mode,cooperative=True)
    if mode=='cooperative':
        assert summary['classification']=='PERFORMANCE_CONTROLLED_STOP'
        assert summary['leader_exit_code']==0
        assert json.loads((tmp_path/'requests.json').read_text()) == [15]
        assert (tmp_path/'safe_marker').read_text()=='current PC completed'
        assert json.loads((tmp_path/'checkpoint.json').read_text())['solution_only']
        assert json.loads((tmp_path/'minimum_summary.json').read_text())['status']=='CONTROLLED_STOP'
        assert summary['cooperative_stop_request']['worker_pid']==json.loads((tmp_path/'ready.json').read_text())['pid']
        assert 'first_SIGKILL' not in summary
    elif mode=='noncooperative':
        assert summary['classification']=='PERFORMANCE_CONTROLLED_STOP'
        assert json.loads((tmp_path/'requests.json').read_text())==[15]
        assert summary['first_SIGKILL']['monotonic']-summary['stop_event']['monotonic']>=3
        assert not (tmp_path/'minimum_summary.json').exists()
    elif mode=='resource':
        assert summary['classification']=='RESOURCE_CONTROLLED_STOP'
        assert 'first_SIGKILL' in summary and 'cooperative_stop_request' not in summary
        assert 'first_SIGTERM' not in summary and not (tmp_path/'safe_marker').exists()
    else:
        assert summary['classification']=='MONITORING_FAILED'
        assert 'identity' in summary['exception_message']
        assert 'cooperative_stop_request' not in summary and not (tmp_path/'requests.json').exists()
