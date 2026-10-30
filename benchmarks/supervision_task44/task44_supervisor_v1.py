"""Task44 application watchdog, not an OS-enforced memory quota."""
from pathlib import Path
import argparse, datetime, fcntl, hashlib, json, os, signal, subprocess, sys, time
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D))
from process_observation_v1 import proc_facts, group_facts, cleanup_child, system_facts, atomic_json
from stop_request_channel_v1 import RequestChannel, FAILED_CLOSES

def _run(owned):
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--launch',type=Path,required=True)
    p.add_argument('--pins-sha256',required=True)
    p.add_argument('--case',required=True)
    p.add_argument('--lock',type=Path,required=True)
    p.add_argument('--seconds',type=float,required=True)
    p.add_argument('--rss-bytes',type=int,default=8000000000)
    p.add_argument('--disk-reserve-bytes',type=int,default=2147483648)
    p.add_argument('--pending-disk-bytes',type=int,default=0)
    p.add_argument('--deadline-utc',default='2026-11-01T11:29:46+00:00')
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args();cmd=a.command[1:] if a.command[:1]==['--'] else a.command
    if not cmd or not 0<a.seconds<=172800 or not 0<a.rss_bytes<=10000000000 or a.pending_disk_bytes<0 or a.disk_reserve_bytes<1073741824:
        p.error('invalid bounded command/resources')
    deadline=datetime.datetime.fromisoformat(a.deadline_utc)
    if deadline.tzinfo is None:p.error('timezone-aware deadline required')
    if deadline.timestamp()>1793532586:p.error('deadline exceeds authorized November 1 11:29:46 UTC')
    if not a.output.is_absolute() or a.output.name!=a.case or not a.case.startswith('task44_') or a.output.exists():p.error('fresh absolute case output required')
    a.lock.parent.mkdir(parents=True,exist_ok=True)
    lock=os.open(a.lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    owned['lock']=lock
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    a.output.mkdir(parents=True,exist_ok=False)
    owned['output']=a.output
    baseline=system_facts(a.output);start=time.monotonic();start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
    available_floor=1073741824
    effective=min(a.rss_bytes,baseline['available']-available_floor)
    summary={'schema':'task44-supervision.v1','case':a.case,'command':cmd,'baseline':baseline,'started_utc':start_utc,'started_monotonic':start,'deadline_utc':a.deadline_utc,'requested_rss_cap':a.rss_bytes,'effective_launch_rss_cap':effective,'target_rss_bytes':8000000000,'hard_rss_bytes':10000000000,'application_sampling_not_cgroup_quota':True,'sampling_seconds':0.25,'status':'ADMISSION_FAILED','cleanup_verified':False}
    proc=None;channel=None;tracked={};reason=None;errors=[];remaining=[];code=None;peak=0;samples=0;requests=[]
    for sig in (signal.SIGINT,signal.SIGTERM):
        owned['handlers'][sig]=signal.signal(sig,lambda signum,frame:requests.append(signum))
    try:
        if effective<=0 or baseline['swap_used'] or baseline['disk_free']<a.disk_reserve_bytes+a.pending_disk_bytes or time.time()>=deadline.timestamp():
            summary['admission_reason']='memory/swap/disk/deadline';return 3
        actual=Path('/proc/self/cmdline').read_bytes().decode().split('\0')[:-1]
        channel=RequestChannel(a.output,a.case,a.pins_sha256,a.launch,actual,cmd)
        env=dict(os.environ)
        for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS']:env[name]='1'
        env.update(TASK44_SUPERVISOR_PID=str(os.getpid()),TASK44_SUPERVISOR_START_TICKS=str(proc_facts(os.getpid())['start_ticks']),TASK44_TREE_CAP_BYTES=str(effective),TASK44_AVAILABLE_FLOOR_BYTES=str(available_floor),TASK44_STAGE_LOG=str(a.output/'stage_admission.jsonl'))
        with (a.output/'stdout.log').open('xb') as out,(a.output/'stderr.log').open('xb') as err,(a.output/'resources.jsonl').open('x') as log:
            proc=subprocess.Popen(cmd,stdout=out,stderr=err,env=env,start_new_session=True)
            tracked[proc.pid]=proc_facts(proc.pid)['start_ticks']
            while True:
                accepted=channel.poll()
                if accepted is not None:requests.append(signal.SIGTERM)
                elapsed=time.monotonic()-start;members,read_errors=group_facts(proc.pid,tracked);system=system_facts(a.output);sup=proc_facts(os.getpid())
                rss=sum(x['rss'] for x in members)+sup['rss'];peak=max(peak,rss);samples+=1
                sample={'elapsed':elapsed,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'process_tree':members,'supervisor':sup,'rss':rss,'target_exceeded':rss>8000000000,'unreadable':read_errors,'system':system}
                log.write(json.dumps(sample,sort_keys=True)+'\n');log.flush()
                if requests:reason='REQUESTED_STOP'
                elif elapsed>=a.seconds:reason='RECOVERABLE_CASE_WATCHDOG'
                elif time.time()>=deadline.timestamp():reason='AUTHORIZED_DEADLINE'
                elif read_errors:reason='OBSERVATION_FAILED'
                elif rss>effective or rss>10000000000:reason='TREE_RSS_LIMIT'
                elif system['available']<available_floor:reason='AVAILABLE_HEADROOM_LIMIT'
                elif system['disk_free']<a.disk_reserve_bytes:reason='DISK_RESERVE_LIMIT'
                elif any(x['swap'] for x in members) or sup['swap'] or system['swap_used'] or any(system[k]!=baseline[k] for k in ['pswpin','pswpout']):reason='SWAP_OBSERVED'
                if reason or proc.poll() is not None:break
                time.sleep(.25)
    except BaseException as exc:
        reason='SUPERVISOR_OR_CONTROL_ERROR';summary['error']=repr(exc)
    finally:
        if proc is not None:
            try:code,remaining,cleanup_errors=cleanup_child(proc,tracked);errors.extend(cleanup_errors)
            except BaseException as exc:errors.append('cleanup_child:'+repr(exc));remaining=[{'unknown':True}]
        if channel is not None:
            try:channel.close()
            except BaseException as exc:errors.append(repr(exc))
            try:summary['request_channel']=channel.facts()
            except BaseException as exc:errors.append('channel_facts:'+repr(exc))
        if proc is not None:summary['status']='CONTROLLED_STOP' if reason else 'CHILD_EXIT_ZERO' if code==0 else 'CHILD_FAILED'
        summary.update(child_exit_code=code,stop_reason=reason,elapsed_seconds=time.monotonic()-start,process_tree_peak_rss_bytes=peak,resource_sample_count=samples,remaining=remaining,cleanup_errors=errors,cleanup_verified=not remaining and not errors and not FAILED_CLOSES)
        owned['summary']=summary
        try:atomic_json(a.output/'summary.json',summary)
        except BaseException as exc:
            errors.append('summary_publication:'+repr(exc));summary['cleanup_verified']=False
            print(json.dumps({'summary_publication_failed':repr(exc),'summary':summary}),file=sys.stderr)
    return 0 if proc is not None and code==0 and reason is None and summary['cleanup_verified'] else 4

def main():
    owned={'lock':None,'handlers':{},'output':None,'summary':None};code=4;primary=None;tail_errors=[]
    try:code=_run(owned)
    except BaseException as exc:
        primary=repr(exc)
        print(json.dumps({'primary_failure':primary}),file=sys.stderr)
        if isinstance(exc,SystemExit) and type(exc.code) is int:code=exc.code
    finally:
        # A close failure is never retried: fd identity might already be reused.
        fd=owned['lock'];owned['lock']=None
        if fd is not None:
            try:os.close(fd)
            except BaseException as exc:tail_errors.append('lock_close:'+repr(exc))
        if owned['output'] is not None and (primary is not None or tail_errors):
            summary=owned['summary'] or {'schema':'task44-supervision.v1','status':'OWNER_PREFLIGHT_FAILURE','cleanup_verified':False}
            summary.update(primary_failure=primary,finalization_errors=tail_errors,cleanup_verified=False)
            try:atomic_json(owned['output']/'summary.json',summary)
            except BaseException as exc:tail_errors.append('failure_summary:'+repr(exc))
        for sig,handler in owned['handlers'].items():
            try:signal.signal(sig,handler)
            except BaseException as exc:tail_errors.append('handler_restore:'+repr(exc))
        if tail_errors:print(json.dumps({'finalization_errors':tail_errors,'primary_failure':primary}),file=sys.stderr)
    return 4 if primary is not None or tail_errors else code

if __name__=='__main__':raise SystemExit(main())
