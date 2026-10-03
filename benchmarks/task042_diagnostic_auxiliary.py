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
    group.add_argument('--v34-phase',choices=('pre','check'))
    group.add_argument('--v33-phase',choices=('pre','check'))
    group.add_argument('--v32-phase',choices=('pre','check'))
    parser.add_argument('--attempt')
    parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args()
    if args.command and args.command[0]=='--':args.command=args.command[1:]
    if args.v29:return v29(args.command)
    if args.v30:return v29(args.command,batch='v30')
    if args.v31_phase:return v31(args.command,phase=args.v31_phase)
    if args.v34_phase:return v32(args.command,phase=args.v34_phase,attempt=args.attempt,batch=34)
    if args.v33_phase:return v32(args.command,phase=args.v33_phase,attempt=args.attempt,batch=33)
    if args.v32_phase:return v32(args.command,phase=args.v32_phase,attempt=args.attempt)
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


def v32(command,*,phase,attempt,batch=32):
    """Bounded, uniquely named repair attempts; a resource rejection stops retries."""
    import re
    from src.io.task042_profile import ROOT
    if batch==34:
        from src.solvers import full_input_block_v34_window as w
    elif batch==33:
        from src.solvers import full_input_block_v33_window as w
    elif batch==32:
        from src.solvers import return_block_v32_window as w
    else:raise ValueError("unapproved auxiliary batch")
    from src.runners.diagnostic_storage import enforce
    if phase not in ('pre','check') or not attempt or not re.fullmatch('[0-9]{3}',attempt):
        raise ValueError('V32 phase and immutable three-digit attempt ID required')
    clock=w.require_live(margin=30);book=w.ledger()
    if book['closed'] or book['active'] is not None:raise RuntimeError('V32 closed/active auxiliary boundary')
    if batch!=34 and (w.TMP/'auxiliary_resource_rejection.json').exists():raise RuntimeError('V32 resource rejection; no retry')
    complete=sum(run['classification']=='COMPLETED' and run['exact_counts'] for run in book['runs'])
    if phase=='check' and (complete!=1 if batch==34 else sum(any(run['counts'].values()) for run in book['runs'])!=1):raise RuntimeError('checker requires one settled complete actor')
    if phase=='pre' and book['runs'] and not (batch in (33,34) and w.allow_entry_repair()):raise RuntimeError('pre-test after consuming actor forbidden')
    used_phase=sum(json.loads(p.read_text())['elapsed_seconds'] for p in w.TMP.glob('aux_'+phase+'_*/summary.json'))
    used=w.auxiliary_wall()-w.CARRIED_SECONDS-(w.probe_wall() if batch==34 else 0.)
    limit=70 if phase=='pre' else 20
    seconds=min(limit-used_phase,90-used,600-w.auxiliary_wall()-book['actor_wall_seconds'],
                clock['heavy_remaining_seconds'])-2
    if seconds<=0:raise RuntimeError('V32 auxiliary / cumulative / deadline exhausted')
    enforce(ROOT,batch=batch,reserve_bytes=2*2**20)
    if batch==34:w.require_retry_ready()
    folder=w.TMP/('aux_'+phase+'_'+attempt);folder.mkdir(parents=True,exist_ok=False)
    with (ROOT/'tmp/task042/task042_shared.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with (folder/'admission_attempt.json').open('x') as stream:
            json.dump(dict(command=command,phase=phase,attempt=attempt,clock=clock),stream)
            stream.flush();os.fsync(stream.fileno())
        try:
            if batch==34:
                baseline=w.admission(audit,observed_activity=True,receipt_path=folder/'admission.json',input_path=' '.join(command),
                    source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
            else:baseline=audit(observed_activity=True,receipt_path=folder/'admission.json',input_path=' '.join(command))
        except Exception as error:
            if batch!=34:write_json(w.TMP/'auxiliary_resource_rejection.json',dict(phase=phase,attempt=attempt,error=repr(error),directory=str(folder)))
            w.journal('auxiliary_admission_rejected',phase=phase,attempt=attempt,error=repr(error))
            raise
        os.sched_setaffinity(0,{baseline['cpu']});os.nice(10)
        subprocess.run(['ionice','-c','3','-p',str(os.getpid())],check=True)
        write_json(folder/'baseline.json',baseline)
        source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        os.environ['TASK042_V'+str(batch)+'_AUX_DIRECTORY']=str(folder)
        result=supervise(command,folder/'supervision',wall_seconds=min(seconds,600-w.auxiliary_wall()-book['actor_wall_seconds']-2),
            interval=.5,timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=2*2**30,
            rss_warning_bytes=2**30,memory_envelope_provider=shared_envelope,
            source_state=dict(source_sha=source,role='V'+str(batch)+' '+phase+' auxiliary',attempt=attempt),
            health_check=SharedHealth(folder,baseline['neighbor_processes']),include_pss=False,stop_on_global_swap=False)
        write_json(folder/'summary.json',result)
        w.journal('auxiliary_settled',phase=phase,attempt=attempt,seconds=result['elapsed_seconds'],
                  cumulative=w.auxiliary_wall()+book['actor_wall_seconds'])
        clean=result['classification']=='COMPLETED' and result['leader_exit_code']==0
        if batch==34 and result['classification']=='RESOURCE_CONTROLLED_STOP' and result['descendants_cleared']:
            w.wait_after_stop('RESOURCE_CONTROLLED_STOP',folder/'summary.json')
        proof=folder/'tests/qualification.json'
        if phase=='pre' and clean and (batch!=34 or proof.exists()):
            from src.solvers.neural_fe_action_packet import file_hash
            write_json(w.TMP/'pre_qualification.json',dict(path=str(proof),sha256=file_hash(proof)))
            w.require_qualification()
        elif batch!=34 and result['classification']!='WORKER_FAILED' and not clean:
            write_json(w.TMP/'auxiliary_resource_rejection.json',dict(phase=phase,attempt=attempt,
                classification=result['classification'],directory=str(folder)))
        if used_phase+result['elapsed_seconds']>limit or w.auxiliary_wall()-w.CARRIED_SECONDS-(w.probe_wall() if batch==34 else 0.)>90:
            raise RuntimeError('V32 auxiliary allocation exceeded')
        print(json.dumps(dict(directory=str(folder),classification=result['classification'],
                              seconds=result['elapsed_seconds'],source_sha=source)))
        return 0 if clean else 1

if __name__=='__main__':sys.exit(main())
