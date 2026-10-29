import json,pathlib,hashlib,subprocess,time
repo=pathlib.Path('/home/fenics/Projects/NN-Lab-V2');p=repo/'benchmarks/artifacts/task43/v21_r10_h67';s=p/'support/space_attempt1'
def rd(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
a=rd(s/'plan_output/plans/v21_r10_h67.audit.json');b=rd(s/'plan_output/plan_audit.json');t=rd(s/'stage_terminal.json');life=rd(s/'root_lifecycle_readback.json');plan=rd(s/'plan_output/plans/v21_r10_h67.json');rest=rd(s/'plan_output/frozen_parent_restore_identities.json')
assert not life['issues'] and not life['vanished_samples_for_manual_classification'] and life['worker_exit_code']==0
assert t['status']=='COMPLETE' and a['dofs']['independent_active_fe_dofs']==139554
n=a['dofs'];f=a['forest'];d=a['space_authority_detail'];assert n['independent_trace_rows']+n['active_cell_interior_rows']==n['independent_active_fe_dofs']
assert n['active_cell_interior_rows']==81000+3150*f['actual_one_level_root_splits'] and f['actual_leaf_cell_count']==180+7*f['actual_one_level_root_splits']
assert 118800<n['independent_active_fe_dofs']<237600 and d['requested_root_ids']==[127]
assert f['closure_split_counts']=={'balance':0,'material':4,'periodic':0,'user':1}
assert d['actual_refined_root_ids']==[127,129,130,131,160]
assert set(d['leaf_inheritance_by_root'])==set(map(str,range(180)))
for k,v in d['leaf_inheritance_by_root'].items():
 leaves=8 if int(k) in d['actual_refined_root_ids'] else 1
 assert v=={'degree_counts':{'p6':leaves},'leaf_count':leaves}
assert d['predicted_returned_trace_dtn_rows']==n['independent_trace_rows']+612
assert a['degrees']['entity_constraints_pass'] and a['degrees']['degree_plan_pass']
for value in rest['shared_modal_physics']['maximum_absolute_complex_differences'].values():assert all(x==0 for x in value.values())
for value in rest['shared_physics']['maximum_absolute_differences_by_case'].values():assert all(x==0 for x in value.values())
assert rest['new_pde_solve'] is False and rest['new_quadrature_sampling'] is False
old=[('R9','round9_p_up_attempt1',110472,35964),('R10','round10_p_up_attempt1',118800,38412),('H8','v11_science/formal/R9_H8_attempt1',116740,37402),('P8','v16_p8/formal/v18_R9_P8_attempt1',110722,36004)]
basis=[];newrows=d['predicted_returned_trace_dtn_rows'];newfe=n['independent_active_fe_dofs']
for label,path,fe,rows in old:
 r=repo/'benchmarks/artifacts/task43'/path;w=rd(r/'watchdog/summary.json');sm=r/'run/solve/run_summary.json';wall=w['elapsed_seconds'];solv=rd(sm)['elapsed_seconds'] if sm.exists() else wall
 # Cubic row scaling conservatively applied to the entire old numerical solver interval;
 # non-overlapping remaining workflow scales with FE; avoid adding nested timers.
 rr=max(1,newrows/rows);fr=max(1,newfe/fe)
 estimate=1.15*(solv*max(rr**3,fr)+(wall-solv)*fr)
 memory=2*w['sampled_process_tree_rss_peak_bytes']*max(rr**2,fr)
 basis.append({'model':label,'actual_FE':fe,'actual_returned_rows':rows,'watchdog_whole_seconds':wall,'solver_interval_seconds':solv,'remaining_disjoint_workflow_seconds':wall-solv,'tree_RSS_peak_bytes':w['sampled_process_tree_rss_peak_bytes'],'status':w['classification'],'watchdog_source':{'path':str(r/'watchdog/summary.json'),'sha256':sha(r/'watchdog/summary.json')},'solver_source':{'path':str(sm),'sha256':sha(sm)} if sm.exists() else None,'row_ratio':rr,'FE_ratio':fr,'predicted_work_seconds':estimate,'predicted_peak_bytes':memory,'scope':'H8 prior output failed; resource calibration only' if label=='H8' else 'historical measured resource calibration, not H67 measurements'})
upper=max(v['predicted_work_seconds'] for v in basis);memory=max(v['predicted_peak_bytes'] for v in basis)
admission={'pass':upper<6900 and memory<32*2**30,'predicted_peak_bytes_upper':memory,'predicted_work_seconds_upper':upper,'work_limit_seconds':6900,'rss_limit_bytes':32*2**30,'basis':basis,'model':'max across four prior runs: 1.15*(old solver elapsed*max(row_ratio^3,FE_ratio) + disjoint remaining whole*FE_ratio); memory=2*old sampled tree peak*max(row_ratio^2,FE_ratio)','uncertainty':'Engineering planning envelope, not a certified upper bound. Same q/R/p6 direct backend; local hanging constraints can change fill and timing. Entire solver is scaled cubically in returned rows and includes linear assembly/A6 costs; 15% additional time and 2x RSS reserve. Watchdog work/whole limits remain fixed; no OOM or extension authorized.'}
assert admission['pass'],admission
out={'status':'QUALIFIED_FOR_F1','checks':dict.fromkeys(['source','input','trace','resource','cleanup'],True),'formal_admission':admission,'actual_FE':newfe,'independent_trace_rows':n['independent_trace_rows'],'active_interior_rows':n['active_cell_interior_rows'],'new_FE':newfe-118800,'actual_leaves':215,'actual_splits':5,'closure_roots':d['forced_closure_root_ids'],'closure_reason':'All four forced splits are material closure: actual aggregate material=4 and balance=periodic=0; no per-event causal trace beyond the existing forest audit','carrier':d['p6_carrier'],'hanging_slave_rows':d['hanging_slave_rows'],'periodic':d['floquet_periodic_relations'],'predicted_returned_rows':newrows,'lifecycle_sha256':sha(s/'root_lifecycle_readback.json'),'restoration_sha256':sha(s/'plan_output/frozen_parent_restore_identities.json'),'audit_sha256':sha(s/'plan_output/plans/v21_r10_h67.audit.json'),'root_review':'root checked full source/input snapshots, all resource/trace lines via stdlib parser and non-stack event lines directly, all 180 inheritance records with independent scalar assertions; old field arrays restored/checked by S, not independently FE-restored again by root','recorded_unix':time.time()}
with (s/'root_independent_audit.json').open('x') as stream:json.dump(out,stream,indent=2);stream.write('\n')
cp=repo/'docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_contract.json';c=rd(cp);root=p/c['slots']['F1']['root'];assert not root.exists();assert not subprocess.check_output(['git','status','--porcelain']).strip()
paths={'space_plan':'plan_output/plans/v21_r10_h67.json','space_audit':'plan_output/plans/v21_r10_h67.audit.json','space_bundle':'plan_output/plan_audit.json','space_terminal':'stage_terminal.json','space_watchdog':'watchdog/summary.json','space_launcher':'launcher_terminal.json','space_root_audit':'root_independent_audit.json'}
release={'decision':'ALLOW_ONE_FIXED_SLOT','stage':'F1','actual_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'contract_sha256':sha(cp),'authorization_review':c['authorization_review'],'root':str(root),'products':{k:{'path':str(s/v),'sha256':sha(s/v)} for k,v in paths.items()},'recorded_unix':time.time()}
with (p/'preparation/F1_root_release.json').open('x') as stream:json.dump(release,stream,indent=2);stream.write('\n')
print(json.dumps({'FE':newfe,'rows':newrows,'predicted_work_upper_seconds':upper,'predicted_peak_GiB':memory/2**30,'admission_pass':admission['pass'],'F1_root':str(root)},indent=2))
