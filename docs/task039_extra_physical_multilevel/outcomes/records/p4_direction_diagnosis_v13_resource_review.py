import hashlib,json,sys,time
from pathlib import Path
start=time.perf_counter();root=Path(sys.argv[1]);p=root/'watchdog/resources.jsonl'
term=json.loads((root/'terminal.json').read_text()); n=0; bad=[]; peak=0; peakpss=0; maxswap=0; minavailable=None; h=hashlib.sha256()
with p.open('rb') as f:
 for line in f:
  h.update(line);d=json.loads(line);n+=1
  peak=max(peak,d['rss_bytes']);peakpss=max(peakpss,d.get('pss_bytes') or 0);maxswap=max(maxswap,d['swap_bytes'])
  e=d['memory_envelope'];available=e['effective_available_bytes'];minavailable=available if minavailable is None else min(available,minavailable)
  checks=[d['rss_bytes']==sum(x['rss_bytes'] for x in d['members']),d['swap_bytes']==sum(x['swap_bytes'] for x in d['members']),d['rss_bytes']<=d['launch_cap_bytes'],d['swap_bytes']==0,available>=e['reserve_bytes'],d['global_swap_stop_reason'] is None,d['all_status_readable'],not d['warning']]
  if not all(checks):bad.append({'sample':n,'checks':checks})
assert n==term['samples'] and peak==term['sampled_process_tree_rss_peak_bytes'] and maxswap==term['sampled_process_tree_swap_peak_bytes']
assert not any(term['global_swap_activity']['delta'].values())
out={'status':'PASS' if not bad else 'FAILED','source_sha':term['source_state']['head'],'source_resources_sha256':h.hexdigest(),'samples':n,'sample_checks':n*8,'failures':bad,'simultaneous_tree_rss_peak_bytes':peak,'simultaneous_tree_pss_peak_bytes':peakpss,'tree_swap_peak_bytes':maxswap,'effective_available_min_bytes':minavailable,'global_swap_delta':term['global_swap_activity']['delta'],'max_parent_budget_seconds':term['workflow_clock_interval']['budget_seconds'],'no_new_FE_PC_actions':True,'core_seconds':time.perf_counter()-start,'limitations':'Sampled simultaneous RSS/PSS, not an unsampled continuous or cgroup peak.'}
Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
assert not bad
