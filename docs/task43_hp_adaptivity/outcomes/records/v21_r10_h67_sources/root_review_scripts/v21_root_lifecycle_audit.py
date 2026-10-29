"""Read only completed V21 artifacts; stdlib, no imports of project or native libraries."""
import pathlib,json,sys,hashlib,re,subprocess,time
repo=pathlib.Path('/home/fenics/Projects/NN-Lab-V2');root=pathlib.Path(sys.argv[1]);start=time.monotonic()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text())
w=read(root/'watchdog/summary.json');l=read(root/'launcher_terminal.json');m=read(root/'run_manifest.json');issues=[];observed={};vanished=[];rss=swap=0;rows=[]
for number,line in enumerate((root/'watchdog/resources.jsonl').read_text().splitlines(),1):
 s=json.loads(line);members=s['members'];rss=max(rss,s['rss_bytes']);swap=max(swap,s['swap_bytes']);rows.append(s)
 if s['rss_bytes']!=sum(x['rss_bytes'] for x in members):issues.append(['rss_sum',number])
 if s['swap_bytes']!=sum(x['swap_bytes'] for x in members):issues.append(['swap_sum',number])
 if s.get('unreadable_pids') or not s['all_status_readable']:issues.append(['unreadable',number])
 if s.get('vanished_pids'):vanished.append([number,s['vanished_pids']])
 if s['rss_bytes']>s['launch_cap_bytes'] or s['swap_bytes']:issues.append(['resource_limit',number])
 e=s['memory_envelope']
 if e['effective_available_bytes']<e['reserve_bytes']:issues.append(['reserve',number])
 for x in members:
  if x['affinity']!=[1]:issues.append(['affinity',number,x['pid'],x['affinity'],x['state']])
  key=f"{x['pid']}:{x['start_ticks']}"
  observed.setdefault(key,{'pid':x['pid'],'start_ticks':x['start_ticks'],'ppids':[],'comm':x['comm'],'max_cpu_seconds':0})
  v=observed[key];v['max_cpu_seconds']=max(v['max_cpu_seconds'],x['cpu_seconds'])
  if x['ppid'] not in v['ppids']:v['ppids'].append(x['ppid'])
trace=[];trace_index=[];exits={};total=stack=0
for p in sorted((root/'strace').glob('sched.*')):
 lines=p.read_text().splitlines();pid=int(p.name.split('.')[-1]);trace_index.append({'path':str(p),'sha256':sha(p),'lines':len(lines)});total+=len(lines)
 for num,line in enumerate(lines,1):
  if line.startswith(' > '):stack+=1;continue
  item={'pid_or_tid':pid,'line_number':num,'raw':line};trace.append(item)
  if re.fullmatch(r'\d+\.\d+ sched_getaffinity\(\d+, \d+, \[1\]\) = \d+',line):item['classification']='CPU1_GETTER'
  elif re.fullmatch(r'\d+\.\d+ sched_setaffinity\(\d+, \d+, \[1\]\) = 0',line):item['classification']='CPU1_SETTER_SUCCESS'
  elif re.fullmatch(r'\d+\.\d+ \+\+\+ exited with \d+ \+\+\+',line):
   item['classification']='EXIT';exits[pid]=int(re.search(r'exited with (\d+)',line)[1])
  elif '--- SIGCHLD ' in line and 'si_code=CLD_EXITED' in line:
   item['classification']='SIGCHLD_TO_CHECK';item['child']=int(re.search(r'si_pid=(\d+)',line)[1]);item['status']=int(re.search(r'si_status=(\d+)',line)[1])
  else:item['classification']='UNCLASSIFIED';issues.append(['unclassified_trace',str(p),num,line])
for item in trace:
 if item['classification']=='SIGCHLD_TO_CHECK':
  if exits.get(item['child'])==item['status']:item['classification']='SIGCHLD_MATCHED_TRACED_EXIT'
  else:issues.append(['unmatched_SIGCHLD',item])
for key,v in observed.items():
 p=pathlib.Path(f"/proc/{v['pid']}/stat")
 if p.exists():
  try:
   f=p.read_text().rsplit(')',1)[1].split()
   if int(f[19])==v['start_ticks'] and f[0]!='Z':issues.append(['still_live',key])
  except FileNotFoundError:pass
source_mismatches=[]
for rel,b in m['sources'].items():
 p=root/'snapshots'/rel
 if sha(p)!=b['sha256'] or p.read_bytes()!=subprocess.check_output(['git','show',m['actual_head']+':'+rel]):source_mismatches.append(rel)
input_mismatches=[k for k,b in m['inputs'].items() if sha(pathlib.Path(b['path']))!=b['sha256']]
if source_mismatches or input_mismatches:issues.append(['identity',source_mismatches,input_mismatches])
if not w['descendants_cleared'] or w['remaining_child_pids']:issues.append(['cleanup_summary'])
if not w['cache_metadata_stable']:issues.append(['cache_change'])
if l['received_signal'] or not l['whole_limit_pass']:issues.append(['launcher_signal_or_time'])
if rss!=w['sampled_process_tree_rss_peak_bytes'] or swap!=w['sampled_process_tree_swap_peak_bytes']:issues.append(['summary_peak_disagreement'])
r={'schema':'task43.v21.root_lifecycle_readback.v1','actual_head':m['actual_head'],'stage':l['stage'],'root':str(root),'method':'root-authored stdlib parse of every resource row and every raw trace line incl stack frames and exit tail; no old auditor or native execution','issues':issues,'vanished_samples_for_manual_classification':vanished,'source_mismatches':source_mismatches,'input_mismatches':input_mismatches,'resource_samples':len(rows),'resource_first':rows[0],'resource_last':rows[-1],'observed_processes':list(observed.values()),'trace_line_count':total,'stack_frame_lines':stack,'trace_events':trace,'trace_files':trace_index,'rss_peak_bytes':rss,'task_swap_peak_bytes':swap,'global_swap':w['global_swap_activity'],'watchdog_classification':w['classification'],'worker_exit_code':w['leader_exit_code'],'outer':l,'readback_seconds':time.monotonic()-start}
(root/'root_lifecycle_readback.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:r[k] for k in ('stage','issues','vanished_samples_for_manual_classification','resource_samples','trace_line_count','rss_peak_bytes','task_swap_peak_bytes','watchdog_classification','worker_exit_code','outer','readback_seconds')},indent=2))
