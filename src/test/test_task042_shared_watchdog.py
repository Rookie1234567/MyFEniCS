"""Exercise tree enforcement with an orphan in its own session; no FE work."""

import json
import subprocess
import sys


def test_opt_in_tree_limit_clears_orphan_without_signalling_sibling(tmp_path):
    root = tmp_path / "tree"
    script = tmp_path / "supervisor.py"
    script.write_text("""import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
from src.runners.task042_shared import shared_envelope
command=[sys.executable,'-c',"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import os,time;os.setsid();x=bytearray(180*1024**2);time.sleep(30)']);time.sleep(30)"]
summary=supervise(command,Path(sys.argv[1]),wall_seconds=20,interval=.1,hard_stop_immediate=True,rss_hard_limit_bytes=128*1024**2,rss_warning_bytes=96*1024**2,memory_envelope_provider=shared_envelope,include_pss=False)
assert summary['classification']=='RESOURCE_CONTROLLED_STOP'
assert summary['descendants_cleared'] and not summary['remaining_child_pids']
assert summary['sampled_process_tree_rss_peak_bytes']>=128*1024**2
assert summary['sampled_process_tree_swap_peak_bytes']==0
""")
    sibling = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    try:
        result = subprocess.run(
            [sys.executable, str(script), str(root)],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert sibling.poll() is None
        summary = json.loads((root / "summary.json").read_text())
        assert len(summary["observed_child_pids"]) >= 2
    finally:
        sibling.terminate()
        sibling.wait(timeout=5)
