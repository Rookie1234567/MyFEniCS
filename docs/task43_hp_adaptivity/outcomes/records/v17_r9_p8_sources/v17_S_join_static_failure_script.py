from pathlib import Path
import json,hashlib,collections,re,datetime
R=Path('/home/fenics/Projects/NN-Lab-V2');B=R/'benchmarks/artifacts/task43/v16_p8';r=B/'support/space_attempt1'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for s in iter(lambda:f.read(8388608),b''):h.update(s)
 return h.hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p)}
def write(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n')
obs_path=B/'preparation/space_attempt1_root_terminal_observations.json';obs=read(obs_path);summary=obs['summary'];m=read(r/'snapshots/launch_manifest.json');planpath=r/'plan_output/plans/v16_r9_p8.json';auditpath=r/'plan_output/plans/v16_r9_p8.audit.json';bundlepath=r/'plan_output/plan_audit.json';plan=read(planpath);audit=read(auditpath);bundle=read(bundlepath);saved=read(r/'plan_output/saved_p5_input_gate.json')['gate'];stages=[json.loads(l) for l in (r/'stages.jsonl').read_text().splitlines()];start=next(s['facts'] for s in stages if s['stage']=='task43_v16_p8_space_worker_bound');end=next(s['facts'] for s in stages if s['stage']=='task43_v16_p8_space_complete')
assert start['source_sha256']==end['source_sha256_end']
assert start['input_sha256']==end['input_sha256_end']
assert all(x['expected']==x['current']==x['snapshot'] for x in obs['source_checks'])
assert all(x['expected']==x['current'] for x in obs['input_checks'])
assert all(not x['same_process_still_present'] for x in obs['post_exit_host_proc_checks'])
assert not obs['resource_observations_requiring_classification'] and not obs['setters'] and not obs['signals'] and not obs['trace_parse_anomalies']
assert obs['launcher_exit']==obs['watchdog_exit']=='0' and summary['leader_exit_code']==0
assert summary['classification']=='COMPLETED' and summary['descendants_cleared'] and summary['remaining_child_pids']==[]
assert summary['elapsed_seconds']<1800 and summary['sampled_process_tree_rss_peak_bytes']<8589934592 and summary['sampled_process_tree_swap_peak_bytes']==0
assert all('[1]) = 8' in x['raw'] for x in obs['all_syscall_records'])
runtime=start['runtime_environment'];worker=start['worker_identity'];assert runtime['mpi_size']==1 and runtime['v11_mumps_available'] and runtime['rank_affinity']==[[1]]
assert 'complex128' in runtime['petsc_scalar_type'] and 'int64' in runtime['petsc_int_type'];assert set(runtime['v11_math_threads'].values())=={'1'}
assert worker['worker_parent_pid']==worker['watchdog_pid']==worker['tracer_parent_pid']
parent=read(R/'benchmarks/artifacts/task43/round9_p_only_authority_attempt1/plan_output/plans/round9_p_up.json')
def degrees(p):return {tuple(x['lower']+x['upper']):x['degree'] for x in p['cell_interior_degrees']}
pd,nd=degrees(parent),degrees(plan);assert pd.keys()==nd.keys() and len(nd)==180
changes=[{'box_nm':list(k),'parent':pd[k],'new':nd[k]} for k in nd if pd[k]!=nd[k]]
assert changes==[{'box_nm':[16.5,5.0,-10.0,33.5,10.0,0.0],'parent':5,'new':6}]
assert not plan['marked_root_boxes'] and plan['maximum_level']==0
assert collections.Counter(nd.values())=={5:27,6:153}
d=audit['dofs'];detail=audit['space_authority_detail'];assert d['independent_active_fe_dofs']==d['independent_trace_rows']+d['active_cell_interior_rows']==110722
assert 110472<d['independent_active_fe_dofs']<237600
assert d['added_independent_fe_dofs']==250 and d['raw_broken_active_fe_dofs_before_hanging_floquet_constraints']-detail['floquet_periodic_relations']['periodic_slave_rows']==110722
assert detail['predicted_returned_trace_dtn_rows']==d['independent_trace_rows']+612==36004
assert audit['forest']['actual_leaf_cell_count']==180 and audit['forest']['actual_one_level_root_splits']==0
assert all(audit['actual_space_gate']['checks'].values())
assert bundle['plan_sha256']==sha(planpath) and bundle['audit_sha256']==sha(auditpath)
assert all(bundle[k] is False for k in ['pde_matrix_constructed','factorization_performed','solve_performed'])
for q,n in [('q8',565248),('q10',1104000)]:
 v=saved[q];assert v['sample_count']==n and v['partition_box_count']==1104 and abs(v['integrated_domain_volume_nm3']-350000)<1e-8 and set(v['owner_box_checks'].values())=={n}
assert saved['shared_physics_identity'] and saved['saved_modal_orders']['pass'] and saved['pass']
assert all(c['mode_count']==612 and c['aggregate_power_matches_p5'] and c['power_ratios_match_p5_full_612'] and c['ordered_keys_match_p5'] for c in saved['saved_modal_orders']['cases'].values())
rows=[json.loads(l) for l in (r/'watchdog/resources.jsonl').read_text().splitlines()];assert len(rows)==559
identity_summary={}
for row in rows:
 for mem in row['members']:
  k=(mem['pid'],mem['start_ticks']);item=identity_summary.setdefault(k,{'pid':k[0],'start_ticks':k[1],'ppids':set(),'states':set(),'affinities':set(),'observations':0});item['ppids'].add(mem['ppid']);item['states'].add(mem['state']);item['affinities'].add(tuple(mem['affinity']));item['observations']+=1
for x in identity_summary.values():
 for key in ['ppids','states','affinities']:x[key]=sorted(x[key])
compact_resources=[{k:row.get(k) for k in ['elapsed_seconds','rss_bytes','swap_bytes','exit_code','live_or_unreaped_children']} for row in rows]
observation={'schema':'task43.v17.S-root-observation.v1','reviewer':'/root','read_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_head':m['head'],'raw_terminal_observation':ref(obs_path),'source_checks':obs['source_checks'],'input_checks':obs['input_checks'],'worker_source_before_after_equal':True,'worker_input_before_after_equal':True,'runtime':runtime,'worker':worker,'resource_summary':summary,'resource_rows':compact_resources,'process_identities':list(identity_summary.values()),'trace_files':obs['traces'],'trace_affinity_events':obs['all_syscall_records'],'trace_setters':[],'trace_signals':[],'trace_review':'All final raw lines read, including exit tails; repeated identical stack-frame text deduplicated only for display. Zero setters, all getters [1].','post_exit_host_proc_checks':obs['post_exit_host_proc_checks'],'plan_degree_changes_independently_recomputed':changes,'dofs':d,'space_authority':{k:v for k,v in detail.items() if k!='leaf_inheritance_by_root'},'forest':audit['forest'],'actual_geometry':audit['actual_geometry'],'saved_p5_gate':saved,'source_before':start['source_sha256'],'source_after':end['source_sha256_end'],'input_before':start['input_sha256'],'input_after':end['input_sha256_end'],'products':{'plan':ref(planpath),'audit':ref(auditpath),'bundle':ref(bundlepath)},'raw_files':[ref(r/p) for p in ['stages.jsonl','watchdog/resources.jsonl','watchdog/summary.json','snapshots/launch_manifest.json','launcher_exit_code.txt','watchdog_exit_code.txt','source_head.txt']],'limits':['S is actual space only; returned matrix rows are predicted, NNZ not measured','Shared JIT/global cache not audited; per-authority cache counters are distinct','No scientific accuracy or merge qualification']}
opath=r/'v17_root_space_observation.json';write(opath,observation)
authorization=read(B/'preparation/T_root_qualification.json')['authorization_review']
joined={'schema':'task43.v16.p8-space-root-joined-terminal.v1','space_source_id':'S_MAIN','status':'S_COMPLETE_ROOT_VERIFIED','contract_sha256':m['contract_sha256'],'review_commit':'f72e1c8d031de7acc374f0806ddac06099c461c4','authorization_review':authorization,'source_head':m['head'],'launcher_exit_code':0,'watchdog_exit_code':0,'worker_exit_code':0,'descendants_cleared':True,'remaining_child_pids':[],'root_observation_record':ref(opath),'products':observation['products'],'gates':{name:{'pass':True,'evidence':ref(opath)} for name in ['source','input','resource','trace','space','old_samples']}}
jpath=r/'v16_p8_space_joined_terminal.json';write(jpath,joined);print(json.dumps({'joined':ref(jpath),'actual_FE':110722,'delta_FE':250,'trace_rows':35392,'interior_rows':75330,'predicted_returned_rows':36004,'whole_seconds':summary['elapsed_seconds']},indent=2))
