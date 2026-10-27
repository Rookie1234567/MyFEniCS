"""Offline extraction of completed P2R evidence; no project/native imports."""
import csv, datetime, hashlib, json, shutil, time
from pathlib import Path
started=time.perf_counter()
R=Path('/home/fenics/Projects/NN-Lab-V2'); base=R/'benchmarks/artifacts/task43/v11_science/recovery_v12'; run=base/'support/space_and_saved_primary_attempt2'
out=R/'docs/task43_hp_adaptivity/outcomes/records/v14_p2r_sources'; out.mkdir(exist_ok=False)
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
index=[]
def copy(p,relative):
 d=out/relative;d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d);index.append(dict(original=str(p.relative_to(R)),copy=str(d.relative_to(R)),sha256=sha(p),bytes=p.stat().st_size))
for name in ['launch_context.txt','launch_command.txt','launcher_started_utc.txt','launcher_finished_utc.txt','launcher_exit_code.txt','watchdog_exit_code.txt','source_head.txt','source_status.txt','source_diff.patch','watchdog/summary.json','watchdog/worker.log','watchdog/workflow_phase.json','snapshots/launch_manifest.json','snapshots/launch.sh','plan_output/actual_authority_before_fe_gate.json','plan_output/A2_saved_primary_q_response.json','plan_output/space_authority_observation_complete.json','plan_output/plans/v11_r9_h8.json']:
 copy(run/name,name)
for p in sorted((run/'plan_output/A2_saved_primary_q_response_substages').glob('*.json')): copy(p,p.relative_to(run))
obs_path=base/'preparation/space_and_saved_primary_attempt2_root_terminal_observations.json'; obs=read(obs_path)
compact={k:v for k,v in obs.items() if k not in ['resource_rows','identities']}
compact['observation_original']={'path':str(obs_path.relative_to(R)),'sha256':sha(obs_path)}
compact['identities']=[dict(pid=x['pid'],start_ticks=x['start_ticks'],first=x['observations'][0],last=x['observations'][-1],all_live_affinity_cpu1=all(m['affinity']==[1] for m in x['observations'] if m['state'] not in ['Z','X'])) for x in obs['identities']]
write(out/'root_terminal_readback.json',compact)
rows=[json.loads(x) for x in (run/'watchdog/resources.jsonl').read_text().splitlines()]
with (out/'resource_rows_compact.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['row','elapsed_seconds','rss_bytes','swap_bytes','cap','available','reserve','pids','live_affinity','exit'])
 for n,x in enumerate(rows,1): w.writerow([n,x['elapsed_seconds'],x['rss_bytes'],x['swap_bytes'],x['launch_cap_bytes'],x['memory_envelope']['effective_available_bytes'],x['memory_envelope']['reserve_bytes'],';'.join(str(m['pid']) for m in x['members']),';'.join(str(m['affinity']) for m in x['members'] if m['state'] not in ['Z','X']),x.get('exit_code')])
write(out/'resource_raw_selected.json',{'first':rows[0],'peak':max(rows,key=lambda x:x['rss_bytes']),'last':rows[-1], 'sample_interval_min':min(b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(rows,rows[1:])), 'sample_interval_max':max(b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(rows,rows[1:]))})
trace_lines=[]
for p in sorted((run/'strace').glob('sched.*')):
 for n,line in enumerate(p.read_text().splitlines(),1):
  if not line.startswith(' > '): trace_lines.append(f'{p.name}:{n}: {line}')
(out/'trace_all_call_and_exit_lines.txt').write_text('\n'.join(trace_lines)+'\n')
events=[json.loads(x) for x in (run/'plan_output/authority_observations.jsonl').read_text().splitlines()];begins={};pairs=[]
for e in events:
 key=(e.get('stage'),e.get('call_id'))
 if e.get('event')=='BEGIN' and 'call_id' in e: begins[key]=e
 elif e.get('event')=='END' and key in begins:
  b=begins[key];pairs.append({'stage':e['stage'],'function':e['function'],'call_id':e['call_id'],'wall_seconds':e['wall_seconds'],'worker_cpu_delta_seconds':e['worker_cpu_seconds']-b['worker_cpu_seconds'],'cache_before':b.get('cache_before'),'cache_after':e.get('cache_after'),'completed_work':e.get('completed_work'), 'arguments':b.get('arguments')})
cold=[x for x in pairs if x['stage']=='space_authority' and x['function'].endswith('.build_variable_p_reference_space') and x['cache_before'] and x['cache_after']['misses']>x['cache_before']['misses']]
selected=[x for x in pairs if x['function'] in ['space_authority'] or x['function'].endswith(('.build_broken_hexa_cell_trace_constraint_map','.build_stage4_local_h_reduction_authority'))]
write(out/'authority_profile_extract.json',{'scope':'read-only existing events; nested times do not sum to whole','event_count':len(events),'space_cold_reference_calls':cold,'major_completed_calls':selected,'tail':events[-3:]})
a=read(run/'plan_output/actual_authority_before_fe_gate.json');s=a['space_authority_detail'];seed=s['seed_forest_root_index'];box=[16.5,5.,-10.,33.5,10.,0.]
checks={
 'one_requested_seed':len(s['requested_root_ids'])==1,'requested_matches_seed_root':s['requested_root_ids']==[seed],
 'requested_box':s['requested_root_boxes']=={str(seed):box},'seed_box':s['seed_root_box_nm']==box,
 'global_seed8':s['seed_mesh_global_cell_id']==8,'requested_global_ids8':s['requested_root_mesh_global_cell_ids']==[8],
 'namespace':s['root_id_namespace']=='forest_root_index; not the parent mesh global-cell ID',
 'requested_forced_disjoint':not(set(s['requested_root_ids'])&set(s['forced_closure_root_ids'])),
 'actual_roots_union':set(s['actual_refined_root_ids'])==set(s['requested_root_ids'])|set(s['forced_closure_root_ids']),
 'all_leaf_inheritance':s['all_actual_leaves_inherit_parent_degree'],'seed_p5':s['seed_parent_degree']==5,
 'seed_children_p5':s['seed_child_degrees']==[5],'seed_inheritance':s['seed_child_degree_inheritance_pass'],
 'returned_trace_plus612':s['predicted_returned_trace_dtn_rows']==a['dofs']['independent_trace_rows']+612,
 'no_slave_global_numbering_as_recorded':not s['hanging_or_floquet_slave_rows_globally_numbered']}
assert [k for k,v in checks.items() if not v]==['no_slave_global_numbering_as_recorded']
write(out/'root_space_diagnosis.json',{'scope':'offline review of saved values and frozen code; not project gate execution, not a successful P2 bundle', 'observed_gate_predicates':checks,'dofs':a['dofs'],'forest':a['forest'],'strict_FE_interval_numeric_only':110472<a['dofs']['independent_active_fe_dofs']<237600,'raw_minus_slaves':{'raw':124012,'hanging':s['hanging_slave_rows'],'periodic':s['floquet_periodic_relations']['periodic_slave_rows'],'independent':116740},'recorded_bad_flag':s['hanging_or_floquet_slave_rows_globally_numbered'],'consumer_wrong_key':'hanging_or_periodic_slave_rows_globally_numbered','producer_key':'hanging_or_floquet_slave_rows_globally_numbered','producer_false_evidence':'frozen source src/adaptivity/hcurl_broken_cell_trace.py:2310; raw producer audit map was not separately persisted','qualification':'FAILED; no corrected historical audit, successful bundle or continuation created'})
stages=[json.loads(x) for x in (run/'plan_output/stages.jsonl').read_text().splitlines()]
write(out/'worker_identity_and_stages.json',{'stages':[dict(stage=x['stage'],phase=x['phase'],monotonic=x['updated_monotonic']) for x in stages], 'preflight_facts':next(x['facts'] for x in stages if x['stage']=='task43_v11_p2_worker_identity_bound')})
for p in [base/'preparation/v14/monitor_static_failure.json',base/'preparation/v14/subagent_cache_statement_correction.json',base/'preparation/v14/rejected_downstream_drafts/rejected_downstream_draft_note.json',base/'preparation/v14/root_dispatch_and_budget_note.json']:
 if p.exists():copy(p,'preparation/'+p.name)
raw_index=[]
for p in sorted(run.rglob('*')):
 if p.is_file():raw_index.append(dict(path=str(p.relative_to(R)),sha256=sha(p),bytes=p.stat().st_size))
write(out/'raw_index.json',raw_index)
write(out/'copies_index.json',index)
whole=obs['summary']['elapsed_seconds'];start=datetime.datetime.fromisoformat((run/'launcher_started_utc.txt').read_text().strip());end=datetime.datetime.fromisoformat((run/'launcher_finished_utc.txt').read_text().strip())
write(out/'root_closeout.json',dict(status='FAILED_RESEARCH_AUDIT_KEY_MISMATCH',source_head=obs['source_head'],source_checks=51,input_checks=38,source_and_input_unchanged_before_static_fix=all(x['expected']==x['current']==x['snapshot'] for x in obs['source_checks']) and all(x['expected']==x['current'] for x in obs['input_checks']),worker_exit=1,watchdog_exit=2,launcher_exit=2,whole_watchdog_seconds=whole,launcher_timestamp_interval_seconds=(end-start).total_seconds(),resource_samples=len(rows),rss_sampled_peak_bytes=max(x['rss_bytes'] for x in rows),swap_sampled_peak_bytes=max(x['swap_bytes'] for x in rows),trace_files=len(obs['traces']),trace_lines=sum(x['lines'] for x in obs['traces']),setters=obs['setters'],signals=obs['signals'],resource_issues=obs['resource_observations_requiring_classification'],cleanup_host_pid_ticks=obs['post_exit_host_proc_checks'],formal_new_dispatches=0,P3_P4_P5='NOT_RUN',P2_continuation=False,P2R_used=1,P2R_limit=1,recovery_support_used=5,recovery_support_limit=5,recovery_whole_seconds=618.6039171176963+whole,caveats=obs['caveats']))
shutil.copyfile(__file__,out/'archive_existing_evidence.py')
write(out/'archive_action.json',dict(measured_seconds=time.perf_counter()-started,command='python3 /tmp/task43_v14_archive.py',exit_code=0,classification='offline stdlib extraction; no project/native execution'))
print(json.dumps({'out':str(out),'cold_count':len(cold),'whole':whole,'launcher_interval':(end-start).total_seconds(),'checks':checks,'archive_seconds':read(out/'archive_action.json')['measured_seconds']},indent=2))
