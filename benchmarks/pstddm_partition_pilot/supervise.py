"""Single-process-group, cumulative-budget supervisor for the opt-in pilot."""
from __future__ import annotations
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASE = ROOT/'benchmarks/artifacts/pstddm_partition_pilot'
G = 1 << 30
THREADS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')


def main():
    if not __debug__ or sys.flags.optimize or os.environ.get('PYTHONOPTIMIZE'):
        raise RuntimeError('Optimization mode is forbidden for assertion-based admission')
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path)
    parser.add_argument('--python',type=Path,required=True)
    args=parser.parse_args()
    BASE.mkdir(parents=True,exist_ok=True)
    lock=(BASE/'run.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    spec=tomllib.loads(args.input.read_text())
    assert spec['model']=='pstddm_partition_pilot'
    out=BASE/spec['case_id']
    assert out.parent==BASE and not out.exists(),'Unique case id; never overwrite evidence'
    subprocess.run(['git','diff','--exit-code'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['git','diff','--cached','--exit-code'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    assert not subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).strip(),'Untracked source/evidence must be committed before formal run'
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='task40extra_dot_parallel_cloud'
    ledger_path=BASE/'budget_ledger.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    for entry in ledger:
        if entry.get('status')=='running':
            raise RuntimeError('Unfinished ledger reservation: inspect its outcome before continuing')
    assert len(ledger)<10 and sum(r['wall_seconds'] for r in ledger)<21600
    source_names=subprocess.check_output(['git','ls-files','src','scripts','benchmarks/pstddm_partition_pilot',
        'input/pstddm_partition_pilot'],cwd=ROOT,text=True).splitlines()
    source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names}
    input_hash=hashlib.sha256(args.input.read_bytes()).hexdigest()
    def facts():
        m={k:int(v.split()[0])*1024 for k,v in (x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())}
        v={k:int(x) for k,x in (r.split() for r in Path('/proc/vmstat').read_text().splitlines())}
        return {'available':m['MemAvailable'],'system_used':m['MemTotal']-m['MemAvailable'],
                'swap_used':m['SwapTotal']-m['SwapFree'],'pswpin':v['pswpin'],'pswpout':v['pswpout'],
                'disk_free':shutil.disk_usage(BASE).free}
    initial=facts()
    def output_bytes():
        total=0
        for path in out.rglob('*'):
            try:
                if path.is_file():
                    total+=path.stat().st_size
            except FileNotFoundError:
                pass  # A JIT temporary was atomically renamed between samples.
        return total
    def gate(f):
        assert f['available']>2*G+(512<<20),'2.5GiB original available floor'
        assert f['system_used']+(512<<20)<6*G,'6GiB system usage including stage reserve'
        assert f['swap_used']==0 and (f['pswpin'],f['pswpout'])==(initial['pswpin'],initial['pswpout']),'zero swap'
        assert f['disk_free']>12*G+(256<<20),'12GiB disk floor plus output reserve'
    gate(initial)
    out.mkdir()
    previous=sum(x['wall_seconds'] for x in ledger)
    assert previous+1800<=21600,'full next-case time reserve'
    reservation={'case':spec['case_id'],'status':'running','wall_seconds':1800,
                 'budget_reserved_seconds':1800,'source_sha':sha,
                 'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'supervisor_pid':os.getpid(),'input_sha256':input_hash}
    ledger.append(reservation)
    ledger_path.write_text(json.dumps(ledger,indent=2))
    (out/'supervisor_identity.json').write_text(json.dumps({'source_sha':sha,'source_hashes':source_hashes,
        'input_sha256':input_hash,'started_utc':reservation['started_utc']},indent=2))
    env=os.environ.copy()
    for name in ['LD_PRELOAD','LD_LIBRARY_PATH','LD_AUDIT','PYTHONPATH','PYTHONHOME','PETSC_OPTIONS','PETSC_DIR','PETSC_ARCH']:
        assert not env.get(name),'unexpected runtime injection '+name
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        env[name]='1'
    env['CC']=str(args.python.resolve().parent/'gcc')
    env['PSTDDM_SUPERVISOR_PID']=str(os.getpid())
    env['PSTDDM_OUTPUT']=str(out)
    env['XDG_CACHE_HOME']=str(out/'cache')
    cmd=[str(args.python.resolve()),'-I','-B',str(ROOT/'scripts/run_case.py'),str(args.input.resolve())]
    start=time.monotonic()
    samples=[]
    reason=None
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        reservation['child_pgid']=process.pid
        ledger_path.write_text(json.dumps(ledger,indent=2))
        def owned():
            rows=[]
            for path in Path('/proc').glob('[0-9]*/stat'):
                try:
                    s=path.read_text();rest=s[s.rfind(')')+2:].split();pid=int(path.parent.name)
                    if int(rest[2])==process.pid or pid==os.getpid():
                        status=dict(x.split(':',1) for x in (path.parent/'status').read_text().splitlines() if ':' in x)
                        rows.append({'pid':pid,'rss':int(status.get('VmRSS','0 kB').split()[0])*1024,
                                     'swap':int(status.get('VmSwap','0 kB').split()[0])*1024})
                except (FileNotFoundError,ProcessLookupError):
                    pass
            return rows
        try:
            while True:
                f=facts();rows=owned();elapsed=time.monotonic()-start
                rss=sum(r['rss'] for r in rows)
                samples.append({'elapsed':elapsed,'rss':rss,'processes':rows,**f})
                gate(f)
                assert rss+(512<<20)<2*G,'2GiB task tree budget including reserve'
                assert all(r['swap']==0 for r in rows)
                assert elapsed<1800 and elapsed+previous<21600,'case/cumulative time budget'
                assert output_bytes()<(240<<20),'256MiB output cap with 16MiB supervisor reserve'
                if process.poll() is not None:
                    break
                time.sleep(.1)
        except BaseException as exc:
            reason=repr(exc)
        finally:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
            deadline=time.monotonic()+5
            remaining=[r for r in owned() if r['pid']!=os.getpid()]
            while remaining and time.monotonic()<deadline:
                time.sleep(.1);remaining=[r for r in owned() if r['pid']!=os.getpid()]
            if remaining:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                time.sleep(.2)
                remaining=[r for r in owned() if r['pid']!=os.getpid()]
    elapsed=time.monotonic()-start
    final=facts()
    try:gate(final)
    except BaseException as exc:reason=(reason or '')+' FINAL '+repr(exc)
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=sha:
        reason=(reason or '')+' SOURCE_SHA_CHANGED'
    if subprocess.call(['git','diff','--quiet'],cwd=ROOT):
        reason=(reason or '')+' TRACKED_SOURCE_CHANGED'
    if subprocess.call(['git','diff','--cached','--quiet'],cwd=ROOT):
        reason=(reason or '')+' STAGED_SOURCE_CHANGED'
    if subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).strip():
        reason=(reason or '')+' UNTRACKED_SOURCE_CHANGED'
    current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names}
    if current!=source_hashes or hashlib.sha256(args.input.read_bytes()).hexdigest()!=input_hash:
        reason=(reason or '')+' SOURCE_OR_INPUT_BYTES_CHANGED'
    record={'case':spec['case_id'],'status':'finished','started_utc':reservation['started_utc'],
            'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_sha':sha,'wall_seconds':elapsed,'returncode':process.returncode,
            'stop_reason':reason,'remaining':remaining,'peak_sampled_tree_rss':max(s['rss'] for s in samples),
            'initial':initial,'final':final,'command':cmd,'sampling_seconds':.1,
            'rss_limit_including_512MiB':2*G,'system_used_limit':6*G,'disk_floor':12*G}
    (out/'resource_samples.json').write_text(json.dumps(samples))
    record['output_bytes']=0
    # Fixed-point byte count includes this metadata itself and all raw samples.
    for _ in range(4):
        (out/'supervision.json').write_text(json.dumps(record,indent=2))
        measured=output_bytes()
        if measured==record['output_bytes']:
            break
        record['output_bytes']=measured
    if measured>=(256<<20):
        reason=(reason or '')+' FINAL_OUTPUT_CAP_CONTROLLED_STOP'
        record['stop_reason']=reason
    record['wall_seconds']=time.monotonic()-start
    record['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    for _ in range(4):
        (out/'supervision.json').write_text(json.dumps(record,indent=2))
        measured=output_bytes()
        if measured==record['output_bytes']:
            break
        record['output_bytes']=measured
    ledger[-1]=record;ledger_path.write_text(json.dumps(ledger,indent=2))
    print(json.dumps(record,indent=2),flush=True)
    assert reason is None and process.returncode==0 and not remaining


def _workstation_meminfo():
    result={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name,value=line.split(':',1);fields=value.split()
        result[name]=int(fields[0])*(1024 if len(fields)>1 and fields[1]=='kB' else 1)
    return result


def _workstation_cgroup():
    root=Path('/sys/fs/cgroup').resolve(strict=True)
    relative=next((line.split(':',2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
                  if line.startswith('0::')),None)
    if relative is None:raise RuntimeError('unified cgroup v2 membership is required')
    path=(root/relative.lstrip('/')).resolve(strict=True)
    if not path.is_relative_to(root):raise RuntimeError('cgroup path escapes /sys/fs/cgroup')
    facts={name:int((path/file).read_text().strip()) for name,file in (
        ('memory_current_bytes','memory.current'),('memory_max_bytes','memory.max'),
        ('swap_current_bytes','memory.swap.current'),('swap_max_bytes','memory.swap.max'))}
    ancestors=[]
    parent=path.parent
    while parent!=root:
        if not parent.is_relative_to(root):raise RuntimeError('invalid cgroup ancestor')
        if (parent/'memory.max').is_file():
            limit=(parent/'memory.max').read_text().strip()
            ancestors.append({'path':str(parent),
                              'memory_max_bytes':None if limit=='max' else int(limit),
                              'memory_current_bytes':int((parent/'memory.current').read_text().strip())})
        parent=parent.parent
    facts['ancestors']=ancestors
    return path,facts


def _workstation_group(pgid):
    rows=[]
    for stat_path in Path('/proc').glob('[0-9]*/stat'):
        try:
            stat=stat_path.read_text();rest=stat[stat.rfind(')')+2:].split()
            pid,ppid,group=int(stat_path.parent.name),int(rest[1]),int(rest[2])
            if group!=pgid:continue
            status=dict(line.split(':',1) for line in (stat_path.parent/'status').read_text().splitlines() if ':' in line)
            rows.append({'pid':pid,'ppid':ppid,
                         'start_ticks':int(rest[19]),
                         'rss_bytes':int(status.get('VmRSS','0 kB').split()[0])*1024,
                         'swap_bytes':int(status.get('VmSwap','0 kB').split()[0])*1024})
        except (FileNotFoundError,ProcessLookupError,PermissionError,ValueError,IndexError):
            continue
    return rows


def _workstation_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def _workstation_prepare_case_output(output,runtime,identity):
    output.mkdir();(output/'tmp').mkdir();(output/'cache').mkdir()
    _workstation_json(output/'runtime_receipt.json',runtime)
    identity=dict(identity)
    identity['runtime_receipt_sha256']=hashlib.sha256((output/'runtime_receipt.json').read_bytes()).hexdigest()
    _workstation_json(output/'supervisor_identity.json',identity)
    return identity


def _workstation_limits(profile, model):
    """Explicit opt-in budgets; the historical p2 contract is unchanged."""
    profiles = {
        'workstation': ('pstddm_stationary_workstation_pilot', 8_000_000_000, 1800,
                        'budget_ledger.json'),
        'workstation-p6': ('pstddm_p6_convergence_workstation', 64*G, 7200,
                           'budget_ledger_p6.json'),
    }
    if profile not in profiles or model != profiles[profile][0]:
        raise ValueError('workstation profile/model mismatch')
    _, cap, case_seconds, ledger_name = profiles[profile]
    return cap, case_seconds, ledger_name


def _workstation_file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _workstation_disk_floor(profile):
    return 380_000_000_000 if profile == 'workstation-p6' else 400_000_000_000


def _seed_p6_retry_jit_cache(output, document, runtime, source_hashes, disk_floor):
    """Copy only hash-bound same-input JIT products; never mutate old evidence."""
    match = re.fullmatch(r'(.+)_retry[1-9][0-9]*', document['case_id'])
    if match is None:
        return None
    donor = output.parent / match.group(1)
    identity = json.loads((donor/'supervisor_identity.json').read_text())
    prior_input = Path(identity['input_path'])
    if _workstation_file_hash(prior_input) != identity['input_sha256']:
        raise RuntimeError('JIT donor input hash changed')
    old_document = tomllib.loads(prior_input.read_text())
    if ({k:v for k,v in old_document.items() if k != 'case_id'} !=
            {k:v for k,v in document.items() if k != 'case_id'}):
        raise RuntimeError('JIT donor mathematical input differs')
    if _workstation_file_hash(donor/'runtime_receipt.json') != identity['runtime_receipt_sha256']:
        raise RuntimeError('JIT donor ABI receipt hash changed')
    prior_runtime = json.loads((donor/'runtime_receipt.json').read_text())
    for key in ('activation_and_abi_dependencies','PETSc_scalar_type','PETSc_integer_type',
                'PETSc_version','MPI_library','modules','python_executable'):
        if prior_runtime[key] != runtime[key]:
            raise RuntimeError('JIT donor runtime differs: '+key)
    allowed_nonform_changes = {
        'src/common/runtime_resource_policy.py', 'src/solvers/bounded_mumps.py',
        'src/runners/pstddm_p6_convergence.py',
    }
    for path, digest in identity['source_hashes'].items():
        if (path.startswith('src/') and not path.startswith('src/test/')
                and path not in allowed_nonform_changes and source_hashes.get(path) != digest):
            raise RuntimeError('JIT donor form dependency changed: '+path)
    inventory = json.loads((donor/'artifact_hashes.json').read_text())
    products = {p:r for p,r in inventory.items() if p.startswith('cache/fenics/')}
    total = sum(row['bytes'] for row in products.values())
    if shutil.disk_usage(output).free < disk_floor + total:
        raise RuntimeError('JIT cache copy exceeds disk admission')
    started = time.monotonic()
    for relative, row in products.items():
        original = donor / relative
        target = output / relative
        if (original.is_symlink() or not original.resolve().is_relative_to(donor.resolve())
                or original.stat().st_size != row['bytes']
                or _workstation_file_hash(original) != row['sha256']):
            raise RuntimeError('JIT donor product identity failed: '+relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if _workstation_file_hash(target) != row['sha256']:
            raise RuntimeError('JIT product copy hash failed: '+relative)
    return {'donor':str(donor), 'donor_source_sha':identity['source_sha'],
            'files':len(products), 'copied_bytes':total,
            'elapsed_seconds':time.monotonic()-started,
            'artifact_inventory_sha256':_workstation_file_hash(donor/'artifact_hashes.json'),
            'old_files_changed':False, 'FEM_or_factor_reuse_claimed':False}


def _workstation_profile_main(argv=None):
    case_started=time.monotonic()
    parser=argparse.ArgumentParser(description='Native-Linux workstation PSTDDM resource profile.')
    parser.add_argument('--profile',choices=('workstation','workstation-p6'),required=True)
    parser.add_argument('input',type=Path)
    parser.add_argument('--scope-root',type=Path,required=True)
    parser.add_argument('--runs-root',type=Path,required=True)
    args=parser.parse_args(argv)
    scope=args.scope_root.resolve(strict=True);runs=args.runs_root.resolve(strict=True)
    input_path=args.input.resolve(strict=True)
    if not runs.is_relative_to(scope) or runs.name!='runs' or not input_path.is_relative_to(scope):
        raise ValueError('workstation inputs and outputs must stay below the assigned task root')
    if _git_branch()!='task40extra_dot_parallel_cloud':
        raise RuntimeError('workstation case requires the exact task execution branch')
    subprocess.run(['git','diff','--exit-code'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['git','diff','--cached','--exit-code'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    if subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).strip():
        raise RuntimeError('workstation run requires frozen tracked source and inputs')
    with input_path.open('rb') as stream:document=tomllib.load(stream)
    tree_limit,case_seconds,ledger_name=_workstation_limits(args.profile,document.get('model'))
    disk_floor=_workstation_disk_floor(args.profile)
    case_id=str(document.get('case_id',''))
    if not case_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in case_id):
        raise ValueError('unsafe or missing case_id')
    output=runs/case_id
    if output.exists():raise FileExistsError(f'refusing to overwrite evidence: {output}')
    for name in THREADS:os.environ[name]='1'
    lock_path=scope/'run.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger_path=scope/ledger_name
        for other_name in ('budget_ledger.json','budget_ledger_p6.json'):
            other_path=scope/other_name
            if other_path.exists() and any(row.get('status')=='running'
                                          for row in json.loads(other_path.read_text())):
                raise RuntimeError('an unfinished workstation attempt is already reserved')
        ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        if any(row.get('status')=='running' for row in ledger):
            raise RuntimeError('an unfinished attempt is already reserved')
        if len(ledger)>=10:raise RuntimeError('shared ten-attempt budget is exhausted')
        previous=sum(float(row.get('wall_seconds',0.)) for row in ledger)
        if previous+case_seconds>21600:raise RuntimeError('not enough cumulative time remains for a full case reserve')
        from src.runners.pstddm_workstation_case import (
            qualified_native_runtime_receipt, validate_workstation_cgroup,
        )
        runtime=qualified_native_runtime_receipt(scope)
        cgroup_path,cg=_workstation_cgroup()
        validate_workstation_cgroup(str(cgroup_path),cg,str(runtime['preparation_cgroup']['path']),
                                    tree_limit_bytes=tree_limit)
        memory=_workstation_meminfo();disk=shutil.disk_usage(scope).free
        if memory['MemAvailable']<400*G or disk<disk_floor:
            raise RuntimeError('initial host reserve or profile disk floor failed')
        if any(os.environ.get(name)!='1' for name in THREADS):raise RuntimeError('thread contract failed')
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        tracked=subprocess.check_output(['git','ls-files','src','scripts','benchmarks/pstddm_partition_pilot',
                                        'input/pstddm_workstation_pilot',
                                        'input/pstddm_p6_convergence_workstation'],cwd=ROOT,text=True).splitlines()
        hashes={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in tracked}
        input_sha=hashlib.sha256(input_path.read_bytes()).hexdigest()
        reservation={'case_id':case_id,'status':'running','reserved_seconds':case_seconds,'wall_seconds':0.,
                     'profile':args.profile,'ledger_path':str(ledger_path),
                     'source_sha':sha,'input_sha256':input_sha,
                     'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     'supervisor_pid':os.getpid(),'branch':'task40extra_dot_parallel_cloud'}
        ledger.append(reservation);_workstation_json(ledger_path,ledger)
        _workstation_prepare_case_output(output,runtime,{
            'case_id':case_id,'supervisor_pid':os.getpid(),
            'source_sha':sha,'source_hashes':hashes,'input_path':str(input_path),'input_sha256':input_sha,
            'scope_root':str(scope),'runs_root':str(runs),'cgroup_path':str(cgroup_path),
            'initial_cgroup':cg,'initial_MemAvailable_bytes':memory['MemAvailable'],
            'initial_disk_free_bytes':disk,'host_reserve_bytes':400*G,
            'tree_limit_bytes':tree_limit,'case_seconds':case_seconds,'profile':args.profile,
            'ledger_path':str(ledger_path),'staging_reserve_bytes':512<<20})
        env=os.environ.copy();env.update({
            'PSTDDM_WORKSTATION_SUPERVISOR_PID':str(os.getpid()),
            'PSTDDM_WORKSTATION_SCOPE_ROOT':str(scope),'PSTDDM_WORKSTATION_OUTPUT':str(output),
            'TMPDIR':str(output/'tmp'),'TMP':str(output/'tmp'),'TEMP':str(output/'tmp'),
            'XDG_CACHE_HOME':str(output/'cache')})
        command=[str(Path(sys.executable).absolute()),'-I','-B',str(ROOT/'scripts/run_case.py'),str(input_path)]
        start=case_started;samples=[];reason=None;process=None
        with (output/'stdout.log').open('wb') as stdout,(output/'stderr.log').open('wb') as stderr:
            try:
                if args.profile == 'workstation-p6':
                    cache_record = _seed_p6_retry_jit_cache(output,document,runtime,hashes,disk_floor)
                    if cache_record is not None:
                        identity_path=output/'supervisor_identity.json'
                        identity=json.loads(identity_path.read_text())
                        identity['jit_cache_adoption']=cache_record
                        _workstation_json(identity_path,identity)
                process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
                pgid=process.pid;reservation['child_pgid']=pgid;_workstation_json(ledger_path,ledger)
                while process.poll() is None:
                    elapsed=time.monotonic()-start;mem=_workstation_meminfo();_,facts=_workstation_cgroup()
                    procs=_workstation_group(pgid);rss=sum(row['rss_bytes'] for row in procs)
                    swap=sum(row['swap_bytes'] for row in procs);free=shutil.disk_usage(scope).free
                    sample={'elapsed_seconds':elapsed,'process_group_id':pgid,'process_tree_rss_bytes':rss,
                            'process_tree_swap_bytes':swap,'processes':procs,'MemAvailable_bytes':mem['MemAvailable'],
                            'host_total_bytes':mem['MemTotal'],'disk_free_bytes':free,'cgroup':facts}
                    samples.append(sample)
                    if rss+(512<<20)>tree_limit:raise RuntimeError('process tree exceeded profile cap with staging reserve')
                    if swap or facts['swap_current_bytes']:raise RuntimeError('task process group/cgroup used swap')
                    validate_workstation_cgroup(str(cgroup_path),facts,
                                                str(runtime['preparation_cgroup']['path']),
                                                tree_limit_bytes=tree_limit)
                    if mem['MemAvailable']<400*G:raise RuntimeError('host MemAvailable crossed 400 GiB reserve')
                    if free<disk_floor:raise RuntimeError('task disk free space crossed profile floor')
                    if elapsed>=case_seconds or previous+elapsed>=21600:raise RuntimeError('case/shared wall budget reached')
                    if int(elapsed)%15==0 and (len(samples)==1 or int(samples[-2]['elapsed_seconds'])!=int(elapsed)):
                        print(json.dumps({'heartbeat_seconds':round(elapsed,1),'rss_bytes':rss,
                                          'available_bytes':mem['MemAvailable'],'disk_free_bytes':free}),flush=True)
                    time.sleep(1.)
                if process.returncode!=0:reason=f'child_returncode_{process.returncode}'
            except BaseException as exc:
                reason=f'controlled_stop:{type(exc).__name__}:{exc}'
            finally:
                if process is not None:
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        process.wait()
                    deadline=time.monotonic()+10
                    while _workstation_group(process.pid) and time.monotonic()<deadline:time.sleep(.2)
                    remaining=_workstation_group(process.pid)
                    if remaining:
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        deadline=time.monotonic()+5
                        while _workstation_group(process.pid) and time.monotonic()<deadline:time.sleep(.2)
                        remaining=_workstation_group(process.pid)
                else:
                    remaining=[]
        elapsed=time.monotonic()-start;memory=_workstation_meminfo();_,final_cg=_workstation_cgroup()
        free=shutil.disk_usage(scope).free;head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT,text=True).strip())
        now_hashes={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in tracked}
        if head!=sha or dirty or now_hashes!=hashes or hashlib.sha256(input_path.read_bytes()).hexdigest()!=input_sha:
            reason=(reason or '')+' source_or_input_changed_during_run'
        if remaining:
            reason=(reason or '')+' remaining_process_group_members_after_SIGKILL'
        status=('COMPLETED_PROCESS_REVIEW_PENDING' if reason is None and process is not None and process.returncode==0
                else 'CONTROLLED_STOP' if reason and reason.startswith('controlled_stop:') else 'FAILED')
        record={**reservation,'status':status,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'wall_seconds':elapsed,'returncode':None if process is None else process.returncode,
                'stop_reason':reason,'peak_sampled_process_tree_rss_bytes':max(
                    (int(sample['process_tree_rss_bytes']) for sample in samples),default=0),
                'resource_sample_count':len(samples),'final_MemAvailable_bytes':memory['MemAvailable'],
                'final_disk_free_bytes':free,'final_cgroup':final_cg,
                'remaining_descendants':remaining,
                'final_cgroup_swap_current_bytes':final_cg['swap_current_bytes'],
                'budget_limits':{'attempt_count':10,'cumulative_seconds':21600,'case_seconds':case_seconds,
                    'tree_bytes':tree_limit,'staging_reserve_bytes':512<<20,
                    'host_reserve_bytes':400*G,'disk_floor_bytes':disk_floor},'command':command}
        _workstation_json(output/'resource_samples.json',samples)
        _workstation_json(output/'supervision.json',record)
        artifacts={}
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.name not in ('artifact_hashes.json','stdout.log','stderr.log'):
                artifacts[str(path.relative_to(output))]={'sha256':_workstation_file_hash(path),
                                                            'bytes':path.stat().st_size}
        _workstation_json(output/'artifact_hashes.json',artifacts)
        record['wall_seconds']=time.monotonic()-case_started
        record['wall_scope']='supervisor entry through cleanup and required artifact hashing'
        if record['wall_seconds']>=case_seconds or previous+record['wall_seconds']>=21600:
            record['status']='CONTROLLED_STOP'
            record['stop_reason']=(record['stop_reason'] or '')+' closeout_exceeded_case_or_shared_budget'
        _workstation_json(output/'supervision.json',record)
        artifacts['supervision.json']={'sha256':_workstation_file_hash(output/'supervision.json'),
                                      'bytes':(output/'supervision.json').stat().st_size}
        _workstation_json(output/'artifact_hashes.json',artifacts)
        ledger[-1]=record;_workstation_json(ledger_path,ledger)
        print(json.dumps(record,indent=2),flush=True)
        return 0 if record['status']=='COMPLETED_PROCESS_REVIEW_PENDING' else 2


def _git_branch():
    return subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()


if __name__=='__main__':
    if sys.argv[1:2]==['--profile'] and len(sys.argv)>2 and sys.argv[2] in ('workstation','workstation-p6'):
        raise SystemExit(_workstation_profile_main(sys.argv[1:]))
    if sys.argv[1:2]==['--profile'] and len(sys.argv)>2 and sys.argv[2]=='cloud':
        sys.argv=sys.argv[:1]+sys.argv[3:]
    main()
