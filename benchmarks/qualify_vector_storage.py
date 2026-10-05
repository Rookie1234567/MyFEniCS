"""Focused final-source codec qualification under the existing supervisor."""
import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.port_component_study import environment
from src.solvers.vector_storage_scope import ROOT, guard_source, implementation_hashes, window


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    source=guard_source(folder);hashes=implementation_hashes()
    for name in hashes:
        if name.endswith('.py'):
            compile((ROOT/name).read_bytes(),name,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_lossless_vector_bank'],
              ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*[n for n in hashes if n.endswith('.py')]]]
    rows=[]
    for i,command in enumerate(commands):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
        (folder/f'command{i}.stdout').write_text(result.stdout);(folder/f'command{i}.stderr').write_text(result.stderr)
        rows.append({'command':command,'returncode':result.returncode})
        if result.returncode:
            write_json(folder/'tests.json',{'status':'FAILED','commands':rows,'source':source})
            raise RuntimeError('focused qualification failed; retain and repair diagnosed cause')
    from benchmarks.subreaper_watchdog import supervise
    smoke=supervise([sys.executable,'-c',"import subprocess,time; subprocess.Popen(['sleep','20']); time.sleep(20)"],
        folder/'watchdog_test',wall_seconds=1,interval=.1,timebase_guard=True,hard_stop_immediate=True,
        rss_hard_limit_bytes=128*2**20,include_pss=False)
    if not smoke['descendants_cleared'] or smoke['classification']=='COMPLETED':
        raise RuntimeError('deadline/own descendants regression')
    write_json(folder/'tests.json',{'status':'PASSED','commands':rows,'source':source,'environment':environment(),'watchdog_test':smoke,'A_AH_B':0})
    print(json.dumps({'status':'V48_FOCUSED_QUALIFICATION_PASSED','test_commands':len(commands)}),flush=True)


if __name__=='__main__':
    main()
