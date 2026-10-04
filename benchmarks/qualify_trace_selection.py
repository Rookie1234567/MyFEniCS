"""Final-byte focused V47 qualification, charged inside the tree supervisor."""

import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.port_component_study import environment
from src.solvers.trace_selection_scope import ROOT, implementation_hashes, window


def main():
    window.guard_worker_parent()
    folder = Path(os.environ["TASK042_V36_AUX_DIRECTORY"])
    hashes = implementation_hashes()
    for name in hashes:
        if name.endswith(".py"):
            compile((ROOT/name).read_bytes(),name,"exec")
    commands = [[sys.executable,"-m","unittest","-q","src.test.test_trace_selection"],
                ["/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff","check","--select","E9,F63,F7,F82",
                 *[name for name in hashes if name.endswith(".py")]],
                *[[sys.executable,"scripts/run_case.py",f"input/task042_neural_coarse_inverse/v47_{name}.dat","--validate-only"]
                  for name in ("data","oracle","check","analysis")]]
    rows = []
    for i,command in enumerate(commands):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
        (folder/f"command{i}.stdout").write_text(result.stdout)
        (folder/f"command{i}.stderr").write_text(result.stderr)
        rows.append({"command":command,"returncode":result.returncode})
        if result.returncode:
            write_json(folder/"tests.json",{"status":"FAILED","commands":rows,"implementation_hashes":hashes})
            raise RuntimeError("focused test failed; repair only the actual cause")
    # A separate short supervisor exercise covers deadline and descendant cleanup.
    from benchmarks.subreaper_watchdog import supervise
    smoke=supervise([sys.executable,"-c","import subprocess,time; subprocess.Popen(['sleep','20']); time.sleep(20)"],
                    folder/"watchdog_test",wall_seconds=1,interval=.1,timebase_guard=True,
                    hard_stop_immediate=True,rss_hard_limit_bytes=128*2**20,include_pss=False)
    if not smoke["descendants_cleared"] or smoke["classification"] == "COMPLETED":
        raise RuntimeError("deadline/own tree cleanup test failed")
    write_json(folder/"tests.json",{"status":"PASSED","commands":rows,"implementation_hashes":hashes,
                                   "environment":environment(),"watchdog_test":smoke,"numeric_actions":0})
    print(json.dumps({"status":"V47_FOCUSED_QUALIFICATION_PASSED","tests":len(rows)}))


if __name__ == "__main__":
    main()
