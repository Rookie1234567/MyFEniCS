"""Read existing V11 terminal evidence; never import native code or launch work."""
import datetime, hashlib, json, re, sys
from pathlib import Path
R = Path('/home/fenics/Projects/NN-Lab-V2')
P = R / 'benchmarks/artifacts/task43/v11_science'
r = Path(sys.argv[1]).resolve()
if r.parent not in {P/'support', P/'formal', P/'recovery_v12/support'}:
    raise ValueError('only an existing V11 attempt can be read')
def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()
def read(p): return json.loads(p.read_text())
summary = read(r/'watchdog/summary.json')
rows = [json.loads(x) for x in (r/'watchdog/resources.jsonl').read_text().splitlines()]
manifest = read(r/'snapshots/launch_manifest.json')
source_checks = []
for x in manifest['source']:
    source_checks.append(dict(path=x['path'], expected=x['sha256'],
        current=sha(R/x['path']), snapshot=sha(Path(x['snapshot']))))
input_checks = [dict(path=x['path'], expected=x['sha256'], current=sha(Path(x['path'])))
                for x in manifest['inputs']]
traces = []; events = []; setters = []; signals = []; anomalies = []
for p in sorted((r/'strace').glob('sched.*')):
    lines = p.read_text().splitlines(); pending = None
    for n, line in enumerate(lines, 1):
        # Stack frames may contain syscall names; they are not syscall events.
        if not re.match(r'^\d+\.\d+ ', line): continue
        if 'sched_setaffinity(' in line or '<... sched_setaffinity resumed>' in line:
            if '<unfinished ...>' in line:
                if pending: anomalies.append(dict(file=p.name,line=n,reason='second unfinished setter'))
                pending = (n, line); continue
            completed = line; original = [dict(line=n,raw=line)]
            if '<... sched_setaffinity resumed>' in line:
                if pending is None:
                    anomalies.append(dict(file=p.name,line=n,reason='setter resumed without entry')); continue
                original.insert(0,dict(line=pending[0],raw=pending[1]))
                completed = pending[1].split('<unfinished ...>')[0] + line.split('<... sched_setaffinity resumed>',1)[1]
                pending = None
            match = re.search(r'sched_setaffinity\((\d+),\s*(\d+),\s*(.*?)\)\s*=\s*(-?\d+)(.*)$',completed)
            event = dict(file=p.name, tid=int(p.name.rsplit('.',1)[1]), raw_records=original,
                         joined=completed, stack=[])
            for following in lines[n:]:
                if re.match(r'^\d+\.\d+ ',following): break
                event['stack'].append(following)
            if match:
                pid, size, mask, ret, tail = match.groups()
                event.update(target_pid=int(pid),size=int(size),mask=mask,result=int(ret),result_tail=tail)
                event['classification'] = ('FAILED_CALL_NO_SUCCESSFUL_REBIND' if int(ret)<0 else
                    'SUCCESS_CPU1' if int(ret)==0 and mask.strip()=='[1]' else
                    'SUCCESS_NON_CPU1_OR_UNEXPLAINED')
            else: event['classification']='UNPARSED_SETTER'
            setters.append(event)
        if 'sched_' in line: events.append(dict(file=p.name,line=n,raw=line))
        if '--- SIG' in line or 'killed by' in line:
            signals.append(dict(file=p.name,line=n,raw=line))
    if pending: anomalies.append(dict(file=p.name,line=pending[0],reason='unclosed unfinished setter',raw=pending[1]))
    traces.append(dict(file=p.name,sha256=sha(p),bytes=p.stat().st_size,lines=len(lines),tail=lines[-1] if lines else None))
identities = {}; issues = []; resource_rows = []
for n, row in enumerate(rows,1):
    members = row.get('members',[])
    if sum(m['rss_bytes'] for m in members)!=row['rss_bytes']: issues.append([n,'RSS sum mismatch'])
    if sum(m['swap_bytes'] for m in members)!=row['swap_bytes']: issues.append([n,'swap sum mismatch'])
    if row['swap_bytes']!=0: issues.append([n,'task swap nonzero'])
    if row['rss_bytes']>=row['launch_cap_bytes']: issues.append([n,'RSS cap reached'])
    env=row['memory_envelope']
    if env['effective_available_bytes']<env['reserve_bytes']: issues.append([n,'reserve violated'])
    if not row['all_status_readable']: issues.append([n,'status unreadable',row.get('unreadable_pids'),row.get('vanished_pids')])
    for m in members:
        key=(m['pid'],m['start_ticks'])
        identities.setdefault(key,[]).append({k:m.get(k) for k in ('ppid','state','comm','cmdline','affinity')})
        if m.get('state') not in {'Z','X'} and m.get('affinity')!=[1]: issues.append([n,'live affinity',m])
        if not m.get('cmdline'): issues.append([n,'empty cmdline; classify by state/identity',m])
    resource_rows.append({k:row.get(k) for k in ('timestamp_ns','elapsed_seconds','rss_bytes','swap_bytes','launch_cap_bytes','live_or_unreaped_children','exit_code','worker_phase')})
postproc=[]
for pid,start in sorted(identities):
    p=Path('/proc')/str(pid)/'stat'
    raw=p.read_text() if p.exists() else None
    same=raw is not None and int(raw.rsplit(')',1)[1].split()[19])==start
    postproc.append(dict(pid=pid,start_ticks=start,same_process_still_present=same,proc_stat=raw))
record=dict(schema='task43.v12.root-terminal-observations.v1',read_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    run_root=str(r),source_head=manifest['head'],launcher_exit=(r/'launcher_exit_code.txt').read_text().strip(),
    watchdog_exit=(r/'watchdog_exit_code.txt').read_text().strip(),summary=summary,
    source_checks=source_checks,input_checks=input_checks,traces=traces,all_syscall_records=events,
    setters=setters,signals=signals,trace_parse_anomalies=anomalies,
    resource_rows=resource_rows,resource_observations_requiring_classification=issues,
    identities=[dict(pid=k[0],start_ticks=k[1],observations=v) for k,v in identities.items()],
    post_exit_host_proc_checks=postproc,
    caveats=['No auto-qualification: root must classify signals, failed calls, transient observations and phase/test/numerical results.',
        'No --cache-path: cache_metadata_stable does not audit shared JIT/global caches.',
        'Read from real host /proc; sampled RSS/swap, not continuous high-water marks.'])
out=P/'recovery_v12/preparation'/(r.name+'_root_terminal_observations.json')
with out.open('x') as f: json.dump(record,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(dict(path=str(out),sha256=sha(out),summary=summary,traces=traces,setters=setters,signals=signals,
    anomalies=anomalies,resource_observations=issues,postproc=postproc),ensure_ascii=False,indent=2))
