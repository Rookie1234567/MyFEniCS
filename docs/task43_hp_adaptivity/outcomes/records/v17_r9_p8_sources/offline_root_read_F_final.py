"""One-off stdlib archival reading of existing F evidence; never runs project code."""
import pathlib,json,hashlib,re,datetime,time
start=time.monotonic()
repo=pathlib.Path('/home/fenics/Projects/NN-Lab-V2'); r=repo/'benchmarks/artifacts/task43/v16_p8/formal/R9_P8_attempt1'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size}
def read(p):return json.loads(p.read_text())
manifest=read(r/'snapshots/launch_manifest.json'); sources=[];inputs=[]
for x in manifest['source']:
 sources.append({**x,'current_sha256':sha(repo/x['path']),'snapshot_sha256':sha(pathlib.Path(x['snapshot']))})
for x in manifest['inputs']:inputs.append({**x,'current_sha256':sha(pathlib.Path(x['path']))})
rows=[json.loads(l) for l in (r/'watchdog/resources.jsonl').read_text().splitlines()]; traces=[];events=[];setters=[];signals=[];unknown=[];stacks=set()
for p in sorted((r/'strace').glob('sched.*')):
 lines=p.read_text().splitlines();traces.append({**ref(p),'lines':len(lines),'tail':lines[-1]})
 for n,l in enumerate(lines,1):
  e={'file':p.name,'line':n,'raw':l}
  if l.startswith(' > '):stacks.add(l);continue
  events.append(e)
  if 'sched_setaffinity(' in l:
   m=re.fullmatch(r'\d+\.\d+ sched_setaffinity\((\d+), (\d+), \[1\]\) = 0',l)
   setters.append({**e,'classification':'SUCCESS_CPU1' if m else 'UNKNOWN','stack':lines[n:next((i for i in range(n,len(lines)) if not lines[i].startswith(' > ')),len(lines))]})
  elif 'sched_getaffinity(' in l:
   if not re.fullmatch(r'\d+\.\d+ sched_getaffinity\(\d+, \d+, \[1\]\) = 8',l):unknown.append(e)
  elif '--- SIG' in l:signals.append({**e,'classification':'NORMAL_CHILD_EXIT' if 'si_code=CLD_EXITED' in l and 'si_status=0' in l else 'UNEXPLAINED'})
  elif not re.fullmatch(r'\d+\.\d+ \+\+\+ exited with [01] \+\+\+',l):unknown.append(e)
terminal=read(r/'run/task43_v16_p8_partial_terminal.json');stages=[json.loads(l) for l in (r/'run/stages.jsonl').read_text().splitlines()]
progress=[json.loads(l) for l in (r/'run/solve/progress_3d.jsonl').read_text().splitlines()]
compactrows=[{k:x.get(k) for k in ['timestamp_ns','elapsed_seconds','rss_bytes','swap_bytes','exit_code','warning','all_status_readable','live_or_unreaped_children']}|{'members':[{k:m.get(k) for k in ['pid','ppid','start_ticks','state','cpu_seconds','affinity','rss_bytes','swap_bytes']} for m in x['members']]} for x in rows]
resource={'row_count':len(rows),'last_elapsed_seconds':rows[-1]['elapsed_seconds'],'sampled_tree_peak_rss_bytes':max(x['rss_bytes'] for x in rows),'sampled_task_swap_peak_bytes':max(x['swap_bytes'] for x in rows),'all_sampled_affinity_CPU1':all(m.get('affinity')==[1] for x in rows for m in x['members']),'all_status_readable':all(x['all_status_readable'] for x in rows),'any_warning':any(x['warning'] for x in rows),'max_sample_gap_seconds':max(b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(rows,rows[1:])),'first_memory_envelope':rows[0]['memory_envelope'],'last_member_cpu_seconds':{str(m['pid']):m['cpu_seconds'] for m in rows[-1]['members']},'coverage':'Incomplete: samples end before worker exit; no whole/resource/cleanup PASS'}
started=(r/'launcher_started_utc.txt').read_text().strip();finished=(r/'launcher_finished_utc.txt').read_text().strip()
# Decimal nanosecond duration, not replacement for missing watchdog whole.
from decimal import Decimal
def timestamp(s):
 a,b=s[:-1].split('.');return Decimal(int(datetime.datetime.fromisoformat(a).replace(tzinfo=datetime.timezone.utc).timestamp()))+Decimal('0.'+b)
record={'schema':'task43.v17.root-F-incomplete-observation.v1','reviewer':'/root','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_head':(r/'source_head.txt').read_text().strip(),'status':'FAILED_MONITOR_PARENT_CHAIN_INCOMPLETE','authorization_review':'ddbe92264d17f1111dcb551431b3b96d26b0d167','source_checks':sources,'input_checks':inputs,'source_all_match':all(x['sha256']==x['current_sha256']==x['snapshot_sha256'] for x in sources),'inputs_all_match':all(x['sha256']==x['current_sha256'] for x in inputs),'resource':resource,'resource_rows':compactrows,'trace_files':traces,'trace_events':events,'setters':setters,'signals':signals,'unclassified_trace_lines':unknown,'unique_stack_lines':sorted(stacks),'trace_scope':'All saved raw lines read after worker exit; watchdog and launcher themselves were not traced; TID start_ticks not independently captured; trace starts after taskset','terminal_fields':{k:v for k,v in terminal.items() if k not in ['candidate_identity','contract_binding','source_identity']},'stages':stages,'solver_progress_compact':[{k:x.get(k) for k in ['time_wall','stage','status','elapsed_seconds','dofs','floquet_constraints','rank_peak_rss_mb','swap_used_mb']} for x in progress],'exit':{'outer_exec_session':5630,'outer_exec_code':143,'outer_code_source':'tool result from original launch session; not a newly executed command','launcher_file_code':int((r/'launcher_exit_code.txt').read_text()),'watchdog_code':None,'worker_trace_code':1,'watchdog_summary_present':(r/'watchdog/summary.json').exists(),'watchdog_exit_file_present':(r/'watchdog_exit_code.txt').exists(),'cause_of_watchdog_loss':'UNKNOWN','signal_sender':'UNKNOWN'},'time':{'launcher_started_utc_raw':started,'launcher_finished_utc_raw':finished,'derived_launcher_timestamp_seconds':str(timestamp(finished)-timestamp(started)),'whole_watchdog_seconds':None,'whole_status':'not_measured','last_resource_lower_bound_seconds':rows[-1]['elapsed_seconds'],'last_trace_epoch':max(Decimal(e['raw'].split()[0]) for e in events).__str__(),'warning':'launcher ended before worker trace; derived launcher duration is not workflow whole and does not establish cleanup compliance'},'cleanup_observation':ref(r/'v17_monitor_loss_cleanup.json'),'root_live_orphan_observation':{'source':'earlier root tool output, not a contemporaneously saved file','timestamp':'UNKNOWN','watchdog_absent':True,'worker_pid':3522929,'worker_start_ticks':309271633,'worker_ppid':1,'tracer_pid':3522940,'tracer_start_ticks':309271644,'tracer_ppid':1,'orted_pid':3522941,'orted_start_ticks':309271753,'orted_ppid':3522929,'subsequent_record_all_absent':True,'root_sent_signals':[],'interpretation':'Later absence does not restore watchdog cleanup qualification'},'missing':['watchdog/summary.json','watchdog_exit_code.txt','qualified primary','full-active/condensed/A6 residuals','normal-correction evidence','612/R/T/Av','P8 q8/q10 samples','F joined PASS','C results'],'continuation_allowed':False,'raw_index':[ref(p) for p in sorted(r.rglob('*')) if p.is_file() and 'snapshots/source' not in str(p)],'static_cost_seconds':time.monotonic()-start}
out=r/'v17_root_F_incomplete_observation.json'
with out.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print(json.dumps({'output':ref(out),'source_count':len(sources),'input_count':len(inputs),'source_match':record['source_all_match'],'input_match':record['inputs_all_match'],'resource':resource,'traces':len(traces),'lines':sum(x['lines'] for x in traces),'getters':sum('sched_getaffinity(' in x['raw'] for x in events),'setters':len(setters),'signals':signals,'unclassified':unknown,'time':record['time'],'static_cost':record['static_cost_seconds']},indent=2))
