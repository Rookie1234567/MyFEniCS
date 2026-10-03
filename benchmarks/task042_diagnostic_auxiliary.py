"""One bounded V28 auxiliary invocation, reusing the established watchdog."""
import argparse,json,os,subprocess,sys,time,fcntl
from datetime import datetime,timezone
from benchmarks.subreaper_watchdog import supervise
from src.runners.task042_shared import audit,SharedHealth,shared_envelope,write_json
from src.solvers import return_block_continuation_window as window


def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group()
    group.add_argument('--v29',action='store_true');group.add_argument('--v30',action='store_true')
    group.add_argument('--v31-phase',choices=('pre','check'))
    parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args()
    if args.command and args.command[0]=='--':args.command=args.command[1:]
    if args.v29:return v29(args.command)
    if args.v30:return v29(args.command,batch='v30')
    if args.v31_phase:return v31(args.command,phase=args.v31_phase)
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


def v29(command,*,batch='v29'):
    """One new light admission, using the same deadline and tree supervisor.

    This is an auxiliary profile only; no new official numerical runner/dat.
    """
    from src.io.task042_profile import ROOT
    from src.solvers.bounded_diagnostic_window import DiagnosticWindow
    if batch not in ('v29','v30'):raise ValueError('unapproved auxiliary namespace')
    carried=21.163846769952215;folder=ROOT/'tmp/task042'/batch
    w=DiagnosticWindow(folder,{},batch.upper(),carried_auxiliary_seconds=carried)
    clock=w.require_live(margin=30)
    if w.ledger()['closed']:raise RuntimeError(batch.upper()+' window already closed')
    lock_path=ROOT/'tmp/task042/task042_shared.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        marker=folder/'auxiliary_admission_attempt.json'
        # Exclusive creation consumes the single attempt even on early failure.
        with marker.open('x') as stream:json.dump(dict(command=command,clock=clock),stream)
        baseline=audit(observed_activity=True,receipt_path=folder/'admission.json',input_path=' '.join(command))
        os.sched_setaffinity(0,{baseline['cpu']});os.nice(10)
        subprocess.run(['ionice','-c','3','-p',str(os.getpid())],check=True)
        write_json(folder/'baseline.json',baseline)
        source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        result=supervise(command,folder/'supervision',wall_seconds=min(115,clock['heavy_remaining_seconds']-10),
            interval=.5,timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=2*2**30,
            rss_warning_bytes=2**30,memory_envelope_provider=shared_envelope,
            source_state=dict(source_sha=source,role=batch.upper()+' auxiliary; no real actor'),
            health_check=SharedHealth(folder,baseline['neighbor_processes']),include_pss=False,stop_on_global_swap=False)
        write_json(folder/'auxiliary_summary.json',result)
        w.journal('single_auxiliary_finished',classification=result['classification'],seconds=result['elapsed_seconds'])
        if result['elapsed_seconds']>120 or carried+result['elapsed_seconds']>600:
            raise RuntimeError(batch.upper()+' auxiliary cumulative cap exceeded')
        return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 1


def v31(command,*,phase):
    """One pre-test and one post-settlement checker admission, separately charged."""
    from src.io.task042_profile import ROOT
    from src.solvers import return_block_v31_window as w
    clock=w.require_live(margin=30);book=w.ledger()
    if book['closed'] or book['active'] is not None:raise RuntimeError('V31 closed/active auxiliary boundary')
    if phase=='check' and len(book['runs'])!=1:raise RuntimeError('V31 checker requires settled actor')
    if phase=='pre' and book['runs']:raise RuntimeError('V31 pre-test after actor forbidden')
    quota=40 if phase=='pre' else 20
    used=w.auxiliary_wall()-w.CARRIED_SECONDS
    if used>=60:raise RuntimeError('V31 auxiliary allocation exhausted')
    folder=w.TMP/('aux_'+phase);folder.mkdir(parents=True,exist_ok=True)
    with (ROOT/'tmp/task042/task042_shared.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with (folder/'admission_attempt.json').open('x') as stream:
            json.dump(dict(command=command,phase=phase,clock=clock),stream)
            stream.flush();os.fsync(stream.fileno())
        baseline=audit(observed_activity=True,receipt_path=folder/'admission.json',input_path=' '.join(command))
        os.sched_setaffinity(0,{baseline['cpu']});os.nice(10)
        subprocess.run(['ionice','-c','3','-p',str(os.getpid())],check=True)
        write_json(folder/'baseline.json',baseline)
        source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        result=supervise(command,folder/'supervision',wall_seconds=min(quota,60-used,
            600-w.auxiliary_wall()-book['actor_wall_seconds'],clock['heavy_remaining_seconds']),
            interval=.5,timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=2*2**30,
            rss_warning_bytes=2**30,memory_envelope_provider=shared_envelope,
            source_state=dict(source_sha=source,role='V31 '+phase+' auxiliary'),
            health_check=SharedHealth(folder,baseline['neighbor_processes']),include_pss=False,stop_on_global_swap=False)
        write_json(folder/'auxiliary_summary.json',result)
        w.journal('auxiliary_settled',phase=phase,seconds=result['elapsed_seconds'],cumulative=w.auxiliary_wall()+book['actor_wall_seconds'])
        if result['elapsed_seconds']>quota or w.auxiliary_wall()-w.CARRIED_SECONDS>60:
            raise RuntimeError('V31 auxiliary cumulative allocation exceeded')
        return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 1

if __name__=='__main__':sys.exit(main())
