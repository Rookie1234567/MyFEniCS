import pathlib,json,hashlib,math,zipfile,ast,struct,time,shutil,subprocess
start=time.perf_counter();R=pathlib.Path.cwd();P=R/'benchmarks/artifacts/task43/v11_science/recovery_v15';r=P/'support/A1_saved_primary_postprocess_attempt1';run=r/'run'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p)}
x=read(P/'preparation/A1_saved_primary_postprocess_attempt1_root_terminal_observations.json');s=x['summary'];m=read(r/'snapshots/launch_manifest.json');t=read(run/'saved_primary_postprocess_terminal.json');q=read(run/'saved_primary_q_response.json');v=read(run/'saved_primary_volume_absorption.json');raw=read(run/'primary_raw_vector_audit.json')['audit']
assert s['classification']=='COMPLETED' and s['leader_exit_code']==0 and s['elapsed_seconds']<1800 and s['descendants_cleared'] and not s['remaining_child_pids']
assert x['launcher_exit']==x['watchdog_exit']=='0' and not x['setters'] and not x['signals'] and not x['trace_parse_anomalies'] and not x['resource_observations_requiring_classification']
assert all(z['current']==z['expected']==z['snapshot'] for z in x['source_checks']) and all(z['current']==z['expected'] for z in x['input_checks'])
assert not any(z['same_process_still_present'] for z in x['post_exit_host_proc_checks'])
assert all('[1]' in z['raw'] for z in x['all_syscall_records'])
assert t['status']=='POSTPROCESS_COMPLETE_DIAGNOSTIC_NOT_OFFICIAL' and t['source_input_snapshot_before']==t['source_input_snapshot_after'] and not t['PDE_solve_performed'] and not t['official_result']
for z in t['source_input_snapshot_after'].values():assert sha(pathlib.Path(z['path']))==z['sha256']
for k in ('primary_raw_vector_audit','volume_absorption','q_response'):assert sha(pathlib.Path(t[k]['path']))==t[k]['sha256']
e=read(run/'runtime_identity.json');assert e['mpi_size']==1 and e['rank_affinity']==[[1]] and 'complex128' in e['petsc_scalar_type'] and 'int64' in e['petsc_int_type'] and e['v11_mumps_available'] and set(e['v11_math_threads'].values())=={'1'}
i=e['v11_watchdog_worker_identity'];assert i['direct_watchdog_parent_verified'] and i['tracer_descends_from_watchdog'] and i['tracer_proc_status_verified']
checks=[]
def close(a,b,label):
 assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=2e-12,abs_tol=1e-28),(label,a,b)
 checks.append(label)
a=q['modal_comparison']['aggregate_power']
for k,g in a['gates'].items():
 d=abs(a['candidate'][k]-a['reference'][k]);close(d,g['absolute_difference'],k);assert d<=g['limit']
modal=q['modal_comparison'];rows=modal['per_channel_power_ratio']['all_rows'];expected={(side,m,n,p) for side in ('top','bottom') for m in range(-4,5) for n in range(-8,9) for p in ('s','p')}
assert len(rows)==612 and {tuple(z['key']) for z in rows}==expected
for z in rows:close(abs(z['candidate_power_ratio']-z['reference_power_ratio']),z['absolute_difference'],'channel '+str(z['key']))
maximum=max(z['absolute_difference'] for z in rows);assert maximum<=1e-7;close(maximum,modal['per_channel_power_ratio']['maximum_absolute_difference'],'channel maximum')
amps=modal['boundary_amplitude_all_rows'];assert len(amps)==612 and {tuple(z['key']) for z in amps}==expected
for z in amps:
 delta=complex(*z['candidate_boundary_amplitude'])-complex(*z['reference_boundary_amplitude']);close(abs(delta),z['absolute_difference'],'amplitude '+str(z['key']))
for group,g in modal['boundary_amplitude_groups'].items():
 side,pol=group.split('_');sub=[z for z in amps if z['key'][0]==side and z['key'][3]==pol];assert len(sub)==153
 d=math.sqrt(math.fsum(z['absolute_difference']**2 for z in sub));base=math.sqrt(math.fsum(abs(complex(*z['reference_boundary_amplitude']))**2 for z in sub));rel=d/max(1,base);close(rel,g['relative_with_unit_incident_modal_floor'],group);assert rel<=1e-5
sample_values={}
for order,f in q['field_comparisons'].items():
 assert f['same_points_and_weights'] and f['same_incident_background_arrays'] and f['sample_count']==(92160 if order=='q8' else 180000)
 for name,g in f['metrics'].items():
  val=g['difference_g_norm']/max(g['reference_g_norm'],g['incident_g_norm_floor']) if name=='G' else g['difference_l2']/max(g['reference_l2'],g['reference_norm_floor'])
  close(val,f['component_relative_values'][name],order+name);assert val<=1e-5
 sample=t['primary_samples'][order];npz=pathlib.Path(sample['npz_path']);assert sha(npz)==sample['npz_sha256'];arr={}
 with zipfile.ZipFile(npz) as z:
  for name,spec in sample['arrays'].items():
   data=z.read(name+'.npy');n=2 if data[6]==1 else 4;hlen=int.from_bytes(data[8:8+n],'little');head=ast.literal_eval(data[8+n:8+n+hlen].decode('latin1'));payload=data[8+n+hlen:]
   assert not head['fortran_order'] and list(head['shape'])==spec['shape'] and head['descr']==spec['dtype']
   assert hashlib.sha256(head['descr'].encode()+json.dumps(list(head['shape'])).encode()+payload).hexdigest()==spec['sha256']
   if name=='weights_nm3':arr[name]=[x[0] for x in struct.iter_unpack('<d',payload)]
   elif name in ('curl_E_total','H_total_A_per_m'):arr[name]=[complex(a,b) for a,b in struct.iter_unpack('<dd',payload)]
 assert all(w>0 for w in arr['weights_nm3']);volume=math.fsum(arr['weights_nm3']);assert math.isclose(volume,350000,rel_tol=1e-12)
 factor=0.002654418727984993/(1j*0.46542113386515455)
 error=max(abs(h-factor*c) for h,c in zip(arr['H_total_A_per_m'],arr['curl_E_total']));assert error<1e-14
 sample_values[order]={'points':f['sample_count'],'volume_nm3':volume,'H_curl_max_absolute_error':error,'component_relative_values':f['component_relative_values'],'npz':ref(npz)}
closure=v['R_total']+v['T_total']+v['A_volume_total']-1;close(closure,v['energy_closure_residual'],'closure');assert abs(closure)<=1e-5
assert v['material_absorption_form_rule']['quadrature_degree']==19 and v['material_absorption_form_rule']['observed_integral_count']==2
assert raw['independent_A6']['relative_residual']<=1e-8 and raw['full_active_transformed']['relative_residual']<=1e-8 and raw['returned_condensed']['relative_residual']<=1e-9
prior=read(P/'preparation/P3_raw_stdlib_recheck.json');assert prior['numerical_gates_pass']
g={'schema':'task43.v15.a1-saved-primary-joined-root-gate.v1','status':'A1_SAVED_PRIMARY_Q_GATES_PASSED_ROOT_VERIFIED','scope':'original failed A1 solve + saved-primary-only recovery; original failed terminal remains unchanged, no new formal solve','original_source_head':t['source_run_head'],'postprocess_head':m['head'],'original_failed_terminal':t['source_input_snapshot_before']['run/task43_v11_partial_terminal.json'],'postprocess_terminal':ref(run/'saved_primary_postprocess_terminal.json'),'postprocess_root_observations':ref(P/'preparation/A1_saved_primary_postprocess_attempt1_root_terminal_observations.json'),'raw_stdlib_recheck':ref(P/'preparation/P3_raw_stdlib_recheck.json'),'original_failure_closeout':ref(P/'preparation/P3_failed_root_closeout.json'),'raw_audit':raw,'aggregate_outputs':a,'maximum_channel_difference':maximum,'amplitude_groups':modal['boundary_amplitude_groups'],'field_values':sample_values,'closure_residual':closure,'Av_actual_form_metadata':v['actual_fem_form_integrals'],'root_json_arithmetic_checks':len(checks),'field_checks_scope':'sample NPZ hashes/shapes and positive weights volume/H-curl independently read; field difference norms recomputed from saved JSON scalars, not re-sampled or new independent A6','postprocess_summary':s,'trace_files':x['traces'],'trace_classification':'all final records/tails read; no setters/signals;19 gettersCPU1;5 new unique stack frames vs already read validation frames','cleanup':x['post_exit_host_proc_checks'],'source_count':len(x['source_checks']),'input_count':len(x['input_checks']),'P4_condition_met':True,'official_result':False,'production_qualified':False,'formal_dispatch_count':6,'formal_envelope':8,'sealed_slot_preserved':True,'static_read_seconds':time.perf_counter()-start}
gp=P/'preparation/A1_saved_primary_joined_root_gate.json';gp.write_text(json.dumps(g,indent=2)+'\n')
d=R/'docs/task43_hp_adaptivity/outcomes/records/v15_bugfix_sources/A1_saved_primary_recovered';d.mkdir()
for f in [gp,run/'saved_primary_postprocess_terminal.json',run/'primary_raw_vector_audit.json',run/'saved_primary_volume_absorption.json',run/'runtime_identity.json',r/'watchdog/summary.json',r/'snapshots/launch_manifest.json',r/'snapshots/launch.sh']:
 shutil.copyfile(f,d/f.name)
# full 612 row comparison is 0.6MB: retain a compact JSON encoding without dropping rows.
(d/'saved_primary_q_response.json').write_text(json.dumps(q,separators=(',',':'))+'\n')
(d/'trace_resource_excerpt.json').write_text(json.dumps({'events':x['all_syscall_records'],'resource_rows':x['resource_rows']},indent=2)+'\n')
shutil.copyfile(pathlib.Path(__file__),d/'root_close_saved_primary.py')
print(json.dumps({'joined_gate':ref(gp),'values':sample_values,'closure':closure,'max_channel':maximum,'elapsed':g['static_read_seconds']}))
