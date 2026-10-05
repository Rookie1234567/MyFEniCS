"""Paid final-source focused checks, real dat validation and tree cleanup."""
import json
import os
import subprocess
import sys
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.scattering_accuracy_scope import ROOT,implementation_hashes,window


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);hashes=implementation_hashes()
    for name in hashes:
        if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
    paths=[n for n in hashes if 'scattering_accuracy' in n]+['src/solvers/hcurl_assembly_time_condensation.py','src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py','src/runners/port_preparation.py','scripts/run_case.py']
    paths=[n for n in paths if n.endswith('.py')]
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_scattering_accuracy'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*paths]]
    commands += [[sys.executable,'scripts/run_case.py',str(p),'--validate-only'] for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v50_*.dat'))]
    rows=[]
    for i,c in enumerate(commands):
        r=subprocess.run(c,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=c,returncode=r.returncode))
        if r.returncode:
            write_json(folder/'tests.json',dict(status='FAILED',commands=rows,implementation_hashes=hashes))
            raise RuntimeError('targeted qualifier failure; preserve logs, fix localized cause')
    from benchmarks.subreaper_watchdog import supervise
    result=supervise([sys.executable,'-c','import subprocess,time;subprocess.Popen(["sleep","20"]);time.sleep(20)'],
        folder/'watchdog_test',wall_seconds=1,interval=.1,timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=128*2**20,include_pss=False)
    if not result['descendants_cleared'] or result['classification']=='COMPLETED':raise RuntimeError('deadline/own descendants cleanup')
    write_json(folder/'tests.json',dict(status='PASSED',commands=rows,implementation_hashes=hashes,watchdog_test=result,science_actions=0))
    print(json.dumps(dict(status='V50_QUALIFICATION_PASSED',commands=len(rows))))


if __name__=='__main__':main()
