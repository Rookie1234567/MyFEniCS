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
    parser.add_argument('--batch',choices=('v17','v18','v19','v20','v21','v22','v23','v24'),default='v17')
    args=parser.parse_args();directory=args.directory.resolve()
    if args.batch=='v24':
        from src.solvers.local_block_window import snapshot as selected_snapshot,journal as selected_journal
    elif args.batch=='v23':
        from src.solvers.p1_image_window import snapshot as selected_snapshot,journal as selected_journal
    elif args.batch=='v22':
        from src.solvers.p1_trace_window import snapshot as selected_snapshot,journal as selected_journal
    elif args.batch=='v21':
        from src.solvers.exact_recycle_window import snapshot as selected_snapshot,journal as selected_journal
    elif args.batch=='v20':
        from src.solvers.fixed_p3_ilu0_window import snapshot as selected_snapshot,journal as selected_journal
    elif args.batch=='v19':
        from src.solvers.post_lsqr_window import snapshot as selected_snapshot,journal as selected_journal
    elif args.batch=='v18':
        from src.solvers.residual_completion_window import snapshot as selected_snapshot,journal as selected_journal
    else:selected_snapshot,selected_journal=snapshot,journal
    if not directory.is_relative_to(ROOT/'tmp/task042'/args.batch) or directory.exists():raise ValueError('fresh own queue supervision directory required')
    if os.environ.get('TASK042_ACTIVATION')!='1':raise ValueError('own qualified activation required')
    result=supervise([sys.executable,'scripts/task042_v17_campaign.py','--batch',args.batch,'--'+args.mode],directory,
         wall_seconds=selected_snapshot()['heavy_remaining_seconds'],interval=.5,timebase_guard=True,
         source_state=dict(batch=args.batch.upper(),window=selected_snapshot(),mode=args.mode,own_processes_only=True),
         hard_stop_immediate=True,rss_hard_limit_bytes=HARD,rss_warning_bytes=WARNING,
         memory_envelope_provider=shared_envelope,resource_stop_policy='legacy',stop_on_global_swap=False,
         include_pss=False)
    selected_journal('queue_supervision_complete',mode=args.mode,classification=result['classification'],
             descendants_cleared=result['descendants_cleared'])
    print(json.dumps({k:result[k] for k in ('classification','leader_exit_code','descendants_cleared','elapsed_seconds','sampled_process_tree_rss_peak_bytes')}))
    return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 and result['descendants_cleared'] else 1


if __name__=='__main__':raise SystemExit(main())
