import json, hashlib, re, time, datetime
from pathlib import Path
start=time.monotonic()
base=Path('/home/fenics/Projects/NN-Lab-V2')
p=base/'benchmarks/artifacts/task43/v9_resume_preparation'
r=base/'benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1'
def sha(x): return hashlib.sha256(x.read_bytes()).hexdigest()
def read(x): return json.loads(x.read_text())
issues=[]
def check(ok,msg):
 if not ok: issues.append(msg)
snapshot=read(p/'prelaunch_snapshot.json')
check(sha(p/'prelaunch_snapshot.json')=='ef12d0f5aed0d1925b274b1996d4c06743a84eada56ffa3a52044b4f0f883919','prelaunch snapshot changed')
sources=[]
for x in snapshot['source_manifest']:
 paths=[base/x['path'],base/x['snapshot'],r/'source_snapshot'/x['path']]
 hashes=[sha(f) for f in paths]
 check(all(h==x['sha256'] for h in hashes),x['path'])
 sources.append(dict(path=x['path'],sha256=x['sha256'],current_prelaunch_run_hashes=hashes))
for name,h in snapshot['predecessor_hashes'].items(): check(sha(p/name)==h,'predecessor '+name)
drivers=[]
for name,h in [('run_d3.sh','e84d2eb0bfcd257549fcd85b336d5ce9ea5f8faa72eef5261e7ca936d076127a'),('probe_import_affinity.py','fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4')]:
 paths=[Path('/tmp/task43_v7_d3_proposal')/name,r/'driver_snapshot'/name]
 hashes=[sha(f) for f in paths];check(hashes==[h,h],name)
 drivers.append(dict(path=name,sha256=h,actual_hashes=hashes))
traces=[];setter_records=[];getter_records=[];signal_records=[]
for f in sorted((r/'strace').glob('sched.*')):
 lines=f.read_text().splitlines()
 for n,l in enumerate(lines,1):
  record=dict(file=f.name,line=n,raw=l)
  if 'sched_setaffinity' in l: setter_records.append(record)
  if re.search(r'\bsched_getaffinity\(',l):
   getter_records.append(record);check(bool(re.search(r', \[1\]\)\s+=\s+8$',l)),'getter '+str(record))
  if '--- SIG' in l or 'killed by' in l: signal_records.append(record)
 check(lines[-1].endswith('+++ exited with 0 +++'),'trace tail '+f.name)
 traces.append(dict(file=f.name,sha256=sha(f),bytes=f.stat().st_size,lines=len(lines),tail=lines[-1]))
check(len(traces)==6,'trace count');check(not setter_records,'setter requires classification');check(not signal_records,'signal requires classification')
rows=[json.loads(l) for l in (r/'watchdog/resources.jsonl').read_text().splitlines()]
summary=read(r/'watchdog/summary.json');stage=[json.loads(l) for l in (r/'probe_stages.jsonl').read_text().splitlines()]
identities={};row_review=[]
for n,row in enumerate(rows,1):
 check(row['all_status_readable'] and not row['unreadable_pids'] and not row['vanished_pids'],'readability '+str(n))
 check(sum(m['rss_bytes'] for m in row['members'])==row['rss_bytes'],'rss sum '+str(n))
 check(row['swap_bytes']==sum(m['swap_bytes'] for m in row['members'])==0,'swap '+str(n))
 check(row['rss_bytes']<row['launch_cap_bytes']<=8589934592,'cap '+str(n))
 env=row['memory_envelope'];check(env['effective_available_bytes']>env['reserve_bytes'],'reserve '+str(n))
 check(not row['warning'] and row['compiler_descendant_count']==0,'warning/compiler '+str(n))
 for m in row['members']:
  check(m['affinity']==[1] and bool(m['cmdline']),'affinity/cmdline '+str(m['pid']))
  ident={k:m[k] for k in ('pid','ppid','start_ticks','comm','cmdline')}
  check(m['pid'] not in identities or identities[m['pid']]==ident,'identity changed')
  identities[m['pid']]=ident
 row_review.append({k:row[k] for k in ('timestamp_ns','elapsed_seconds','rss_bytes','swap_bytes','launch_cap_bytes','live_or_unreaped_children','exit_code')})
 for k in ('effective_available_bytes','reserve_bytes'): row_review[-1][k]=env[k]
 row_review[-1]['members']=[{k:m[k] for k in ('pid','ppid','start_ticks','affinity','rss_bytes','swap_bytes','state')} for m in row['members']]
check(len(rows)==summary['samples']==13,'sample count')
check(max(x['rss_bytes'] for x in rows)==summary['sampled_process_tree_rss_peak_bytes'],'peak')
check(summary['elapsed_seconds']<120 and rows[-1]['elapsed_seconds']<summary['elapsed_seconds'],'whole time')
check(not rows[-1]['live_or_unreaped_children'] and rows[-1]['exit_code']==0,'final resource row')
check(summary['descendants_cleared'] and not summary['remaining_child_pids'] and summary['leader_exit_code']==0,'cleanup summary')
check(summary['cache_metadata_stable'],'cache')
for s in stage:
 check((s['pid'],s['ppid'],s['start_ticks'])==(257450,257437,286512204),'stage identity')
 if 'affinity_by_tid' in s:
  check(all(v==[1] for v in s['affinity_by_tid'].values()),'stage affinity')
  check(s['trace_sync'] and not s['trace_errors'] and not s['unreadable_tids'] and not s['unclassified_setter_records'],'stage trace')
  check(s['hwloc_components']=='-x86' and s['ompi_mca_pml']=='ob1','worker env')
abi=next(s for s in stage if s['stage']=='abi_preflight');f=abi['facts']
check(not abi['failures'] and f['mpi_size']==1 and f['petsc_scalar']=='complex128' and f['petsc_integer']=='int64','ABI')
check(len(f['thread_environment'])==6 and set(f['thread_environment'].values())=={'1'},'threads')
check((r/'source_head.txt').read_text().strip()==snapshot['git']['head'].strip(),'run head')
check(not (r/'source_status.txt').read_text(),'run dirty')
check((r/'launcher_exit_code.txt').read_text().strip()=='0','launcher exit')
check('20 passed in 0.91s' in (r/'watchdog/worker.log').read_text(),'pytest result')
postproc=[]
for pid in sorted(set(identities)|{257452,257453,257454,257455}):
 proc=Path('/proc')/str(pid)/'stat'
 raw=proc.read_text() if proc.exists() else None
 postproc.append(dict(pid=pid,proc_stat=raw,status='ABSENT' if raw is None else 'PRESENT_REQUIRES_REVIEW'))
 check(raw is None,'post-exit pid present '+str(pid))
index=[]
for f in sorted(r.rglob('*')):
 if f.is_file(): index.append(dict(path=str(f.relative_to(base)),bytes=f.stat().st_size,sha256=sha(f)))
result=dict(schema='task43.v9.root-terminal-audit.v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),review_sha=snapshot['review_sha'],fixed_code_sha=snapshot['fixed_code_commit'],prelaunch_snapshot_sha256=sha(p/'prelaunch_snapshot.json'),issues=issues,scope='LIMITED_FIXED_CHAIN_AND_20_TEST_BYTES_ONLY',status='PASS_LIMITED_ENGINEERING' if not issues else 'INCOMPLETE_NOT_QUALIFIED',sources=sources,drivers=drivers,traces=traces,trace_total_lines=sum(t['lines'] for t in traces),setter_records=setter_records,setter_classification='NO_SETTER_RECORDS_OF_ANY_KIND_IN_ALL_FINAL_RAW_FILES',getter_records=getter_records,signal_records=signal_records,resource_rows=row_review,process_identities=list(identities.values()),post_exit_host_proc_check=postproc,abi=abi,stages=stage,watchdog_summary=summary,probe_terminal=read(r/'probe_terminal.json'),outer_exec=dict(session_id=73877,exit_code=0,evidence='root tool write_stdin completion chunk 1d94a5; shell launcher_exit_code.txt independently 0'),raw_file_index=index,limitations=['sampled RSS/VmSwap, not continuous maxima','no production ABI/full CI/scientific endpoint/merge qualification','trace begins after taskset; launcher binding supported by frozen shell and sampled identities','no loader closure claim from sched-only trace','thread start_ticks not separately recorded by frozen probe; TIDs bound by stage task enumeration and final trace files'],processing_seconds=time.monotonic()-start)
with (p/'root_terminal_audit.json').open('x') as out: json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
print(json.dumps(dict(status=result['status'],issues=issues,traces=traces,getters=len(getter_records),setter_count=len(setter_records),resources=row_review,host_processes=postproc,processing_seconds=result['processing_seconds'],audit_sha256=sha(p/'root_terminal_audit.json')),ensure_ascii=False))
