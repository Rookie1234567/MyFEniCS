"""Independent campaign deadline/tree enforcement around the finite queue."""
import argparse
import json
import os
import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
from src.io.task042_profile import ROOT
from src.runners.task042_shared import HARD,WARNING,shared_envelope,write_json
from src.solvers.resumable_trace_window import snapshot,journal


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('solve','verify'));parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();directory=args.directory.resolve()
    if not directory.is_relative_to(ROOT/'tmp/task042/v17') or directory.exists():raise ValueError('fresh own queue supervision directory required')
    if os.environ.get('TASK042_ACTIVATION')!='1':raise ValueError('own qualified activation required')
    result=supervise([sys.executable,'scripts/task042_v17_campaign.py','--'+args.mode],directory,
         wall_seconds=snapshot()['heavy_remaining_seconds'],interval=.5,timebase_guard=True,
         source_state=dict(batch='V17',window=snapshot(),mode=args.mode,own_processes_only=True),
         hard_stop_immediate=True,rss_hard_limit_bytes=HARD,rss_warning_bytes=WARNING,
         memory_envelope_provider=shared_envelope,resource_stop_policy='legacy',stop_on_global_swap=False,
         include_pss=False)
    journal('queue_supervision_complete',mode=args.mode,classification=result['classification'],
             descendants_cleared=result['descendants_cleared'])
    print(json.dumps({k:result[k] for k in ('classification','leader_exit_code','descendants_cleared','elapsed_seconds','sampled_process_tree_rss_peak_bytes')}))
    return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 and result['descendants_cleared'] else 1


if __name__=='__main__':raise SystemExit(main())
