"""One bounded V28 auxiliary invocation, reusing the established watchdog."""
import argparse,json,os,subprocess,sys,time
from datetime import datetime,timezone
from benchmarks.subreaper_watchdog import supervise
from src.runners.task042_shared import audit,SharedHealth,shared_envelope,write_json
from src.solvers import return_block_continuation_window as window


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args()
    clock=window.require_live(margin=900);used=window.auxiliary_wall()+window.ledger()['actor_wall_seconds']
    if used>=590:raise RuntimeError('V27+V28 bounded auxiliary cap/cleanup')
    folder=window.TMP/('aux_'+datetime.now(timezone.utc).strftime('%H%M%S%f'));folder.mkdir()
    baseline=audit(observed_activity=True,receipt_path=folder/'admission.json',input_path=' '.join(args.command))
    os.sched_setaffinity(0,{baseline['cpu']});os.nice(10)
    subprocess.run(['ionice','-c','3','-p',str(os.getpid())],check=True)
    write_json(folder/'baseline.json',baseline)
    result=supervise(args.command,folder/'supervision',wall_seconds=min(180,590-used,clock['heavy_remaining_seconds']),
        interval=.5,timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=16*2**30,
        rss_warning_bytes=12*2**30,memory_envelope_provider=shared_envelope,
        health_check=SharedHealth(folder,baseline['neighbor_processes']),include_pss=False,stop_on_global_swap=False)
    write_json(folder/'summary.json',result)
    print(json.dumps(dict(directory=str(folder),classification=result['classification'],elapsed_seconds=result['elapsed_seconds'],leader_exit_code=result['leader_exit_code'])))
    return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 1


if __name__=='__main__':sys.exit(main())
