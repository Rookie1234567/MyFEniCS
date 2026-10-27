"""Root: stdlib-only arithmetic on saved P5 evidence, no native/project import."""
from pathlib import Path
import json, hashlib, math, zipfile, ast, array, time
start=time.perf_counter();R=Path('/home/fenics/Projects/NN-Lab-V2');B=R/'benchmarks/artifacts/task43/v11_science';P=B/'recovery_v15';r=B/'support/union_comparison_attempt1';out=r/'comparison'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
def ref(p):return {'path':str(p),'sha256':sha(p)}
x=read(out/'v11_r9_h8_union_comparison.json');checks=[]
def close(a,b,label):
 assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=5e-11,abs_tol=1e-24),(label,a,b)
 checks.append(label)
def npy(data):
 n=2 if data[6]==1 else 4;hlen=int.from_bytes(data[8:8+n],'little');h=ast.literal_eval(data[8+n:8+n+hlen].decode('latin1'))
 assert not h['fortran_order'];return h,data[8+n+hlen:]
def load_array(z,name,meta):
 h,p=npy(z.read(name+'.npy'));s=meta['arrays'][name]
 assert h['descr']==s['dtype'] and list(h['shape'])==s['shape']
 assert hashlib.sha256(h['descr'].encode()+json.dumps(list(h['shape'])).encode()+p).hexdigest()==s['sha256'],name
 a=array.array({'<f8':'d','<c16':'d','<i8':'q','<i4':'i'}[h['descr']]);a.frombytes(p);return a
assert x['status']=='COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE' and not x['official_result'] and not x['passed'] and not x['selection_transition_written']
assert x['source_identity_start']==x['source_identity_end'] and x['input_identity_start']==x['input_identity_end'] and x['v12_p2_p4_input_identity_start']==x['v12_p2_p4_input_identity_end']
assert x['candidate_terminal_status']=='FAILED' and x['candidate_endpoint_sha256'] is None
assert x['actual_FE']=={'R9':110472,'R9_H8':116740,'Delta_FE':6268}
expected={(s,m,n,p) for s in ('top','bottom') for m in range(-4,5) for n in range(-8,9) for p in ('s','p')}
assert x['same_physics']['shared_identity']['numeric']['mu_r']==[1.0,0.0]
k0=x['same_physics']['shared_identity']['numeric']['k0_per_nm'][0];hs=x['same_physics']['shared_identity']['numeric']['magnetic_field_scale_a_per_m'][0]
samples={};values={}
for order in ('q8','q10'):
 entry=x['saved_union_samples'][order];path=Path(entry['path']);assert sha(path)==entry['sha256']
 with zipfile.ZipFile(path) as z:
  _,payload=npy(z.read('__task43_record_json__.npy'));meta=json.loads(payload);assert meta['identity']['sample_count']==entry['sample_count'] and meta['identity']['p4_original_terminal_status']=='FAILED'
  assert meta['identity']['quadrature_order']==int(order[1:]) and meta['identity']['rule_sha256']==entry['rule_sha256']
  assert meta['identity']['sample_count']==meta['identity']['partition_box_count']*int(order[1:])**3
  assert meta['arrays']['points_nm']['sha256']==entry['point_hash'] and meta['arrays']['weights_nm3']['sha256']==entry['weight_hash']
  assert not meta['official_result'] and not meta['passed'] and meta['continuation_all_false']
  a={name:load_array(z,name,meta) for name in meta['arrays']}
 weights=a['weights_nm3'];N=len(weights);assert N==entry['sample_count'] and all(w>0 and math.isfinite(w) for w in weights);volume=math.fsum(weights);close(volume,350000,order+' volume')
 points=a['points_nm'];assert len(points)==3*N and all(math.isfinite(v) for v in points)
 axes=meta['identity']['axis_breakpoints_nm']
 for axis,required in zip(axes,((0,16.5,33.5,50),(0,15,35,50),(-10,0,120,130))):assert all(any(abs(v-e)<1e-12 for v in axis) for e in required)
 assert all(all(lo<=points[3*i+j]<=hi for j,(lo,hi) in enumerate(((0,50),(0,50),(-10,130)))) for i in range(N))
 for label in ('R9','R9_H8','Y6_1'):
  ids=a[label+'_cell_global_ids'];slots=a[label+'_point_cell_local_slots'];pointids=a[label+'_point_cell_global_ids'];assert len(slots)==len(pointids)==N
  assert all(0<=slot<len(ids) and ids[slot]==gid for slot,gid in zip(slots,pointids))
  assert len(a[label+'_E'])==len(a[label+'_curl_E'])==6*N and all(math.isfinite(v) for v in a[label+'_E']) and all(math.isfinite(v) for v in a[label+'_curl_E'])
 samples[order]={'npz':ref(path),'points':N,'volume_nm3':volume,'arrays_verified':len(meta['arrays']),'partition_boxes':meta['identity']['partition_box_count'],'axes_nm':axes,'original_P4_status':'FAILED'}
 values[order]={}
 for label in ('R9','R9_H8'):
  result=x['results'][order][label];f=result['field_metrics'];m=result['modal_metrics'];signed=result['signed_observables'];scaled={}
  power=signed['aggregate_signed_candidate_minus_reference']
  for k,d in power.items():
   close(abs(d),m['power_absolute_differences'][k],order+label+k);scaled['power.'+k]=abs(d)/(1e-6 if k in ('R00_s','R00_p') else 1e-5)
  rows=signed['signed_individual_channel_power_ratio_differences'];amps=signed['complex_boundary_amplitude_differences']
  assert len(rows)==len(amps)==612 and {tuple(v['mode_key']) for v in rows}==expected and {tuple(v['mode_key']) for v in amps}==expected
  assert [v['mode_key'] for v in rows]==[v['mode_key'] for v in amps]
  diffs=[abs(v['candidate_minus_reference']) for v in rows]
  for i,(d,other) in enumerate(zip(diffs,m['individual_channel_power_ratio_absolute_differences'],strict=True)):close(d,other,order+label+' channel '+str(i))
  close(max(diffs),m['maximum_individual_channel_power_ratio_absolute_difference'],'max power');scaled['power.max_individual_channel']=max(diffs)/1e-6
  close(math.sqrt(math.fsum(d*d for d in diffs)),m['individual_channel_power_ratio_absolute_difference_l2'],'power norm')
  for group,g in m['boundary_amplitude_groups'].items():
   side,pol=group.split('_');sub=[complex(*v['candidate_minus_reference']) for v in amps if v['mode_key'][0]==side and v['mode_key'][3]==pol];assert len(sub)==153
   norm=math.sqrt(math.fsum(abs(v)**2 for v in sub));close(norm,g['difference_boundary_amplitude_l2'],group)
   rel=norm/max(1,g['reference_boundary_amplitude_l2']);close(rel,g['relative_with_unit_incident_modal_floor'],group+' rel');scaled['amplitude.'+group]=rel/1e-4
  for name,g in f.items():
   if name=='G':rel=g['difference_g_norm']/max(g['reference_g_norm'],g['incident_g_norm_floor']);close(rel,g['relative_with_incident_floor'],'G ratio')
   else:rel=g['difference_l2']/max(g['reference_l2'],g['reference_norm_floor']);close(rel,g['relative_to_reference_or_floor'],name+' ratio')
   if name!='curl_E_over_k0_code':scaled['field.'+name]=rel/1e-4
  # Actual saved E/curl arrays, independently weighted; H follows fixed constitutive scale.
  E=a[label+'_E'];C=a[label+'_curl_E'];ER=a['Y6_1_E'];CR=a['Y6_1_curl_E']
  def integral(u,v=None):
   if v is None:return math.fsum(w*math.fsum(u[6*i+j]**2 for j in range(6)) for i,w in enumerate(weights))
   return math.fsum(w*math.fsum((u[6*i+j]-v[6*i+j])**2 for j in range(6)) for i,w in enumerate(weights))
  e2=integral(E,ER);c2=integral(C,CR);er2=integral(ER);cr2=integral(CR);ec2=integral(E);cc2=integral(C)
  for key,val in [('reference_g_norm',math.sqrt(er2+cr2/k0**2)),('candidate_g_norm',math.sqrt(ec2+cc2/k0**2)),('difference_g_norm',math.sqrt(e2+c2/k0**2))]:close(val,f['G'][key],order+label+key)
  close(math.sqrt(e2),f['E_total_code']['difference_l2'],'E raw difference');close(math.sqrt(c2)*hs/k0,f['H_total_A_per_m']['difference_l2'],'H raw difference')
  close(math.sqrt(er2),f['E_total_code']['reference_l2'],'E raw reference');close(math.sqrt(cr2)*hs/k0,f['H_total_A_per_m']['reference_l2'],'H raw reference')
  close(f['E_total_code']['difference_l2'],f['E_scattered_code']['difference_l2'],'common E background cancels');close(f['H_total_A_per_m']['difference_l2'],f['H_scattered_A_per_m']['difference_l2'],'common H background cancels')
  for name,val in scaled.items():close(val,result['J_infinity']['components'][name],name+' J component')
  J=max(scaled.values());eta=math.sqrt(e2+c2/k0**2)/max(math.sqrt(er2+cr2/k0**2),math.sqrt(700000));close(J,result['J_infinity']['value'],'J max');close(eta,result['eta'],'eta')
  values[order][label]={'J':J,'witness':result['J_infinity']['witness'],'eta':eta,'absolute_power_differences':m['power_absolute_differences'],'maximum_channel_power_difference':max(diffs),'signed_outputs':power,'field_metrics':f,'amplitude_groups':m['boundary_amplitude_groups']}
 del a
 r9=values[order]['R9'];h=values[order]['R9_H8'];dj=r9['J']-h['J'];dg=r9['eta']-h['eta'];ej=x['fixed_thresholds']['epsilon_J'];eg=x['fixed_thresholds']['epsilon_G'];assert ej==0.12716416232413652 and eg==9.088158796603444e-6
 cls='POSITIVE_FIXED_REFERENCE_OUTPUT_RESPONSE' if dj>ej and h['eta']<=r9['eta']+eg else 'NEGATIVE_OR_TRADEOFF_RESPONSE' if h['J']>r9['J']+ej or h['eta']>r9['eta']+eg else 'NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE'
 official=x['q8_robustness_classification' if order=='q8' else 'q10_primary_classification'];assert cls==official['classification']
 for key,val in [('Delta_J',dj),('Delta_G',dg),('Delta_J_per_added_FE_dof',dj/6268),('Delta_G_per_added_FE_dof',dg/6268)]:close(val,official[key],key)
 values[order]['classification']=official
record={'schema':'task43.v15.root-p5-data-recheck.v1','comparison':ref(out/'v11_r9_h8_union_comparison.json'),'checks':len(checks),'samples':samples,'values':values,'actual_FE':x['actual_FE'],'thresholds':x['fixed_thresholds'],'scope':'stdlib reading original NPZ/JSON only; all sample arrays hash verified; owner-map slot/global-id internal consistency verified (not a fresh geometric owner search); E/curl/H/G norms and J/deltas independently recalculated; scattered-reference norms and modal reference norms use saved scalar evidence, no independent background sampler or mode physics rerun','source':ref(Path(__file__)),'elapsed_static_seconds':time.perf_counter()-start,'no_native_import':True,'no_PDE_or_resampling':True}
p=P/'preparation/P5_data_stdlib_recheck.json'
with p.open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps({'record':ref(p),'elapsed':record['elapsed_static_seconds'],'checks':len(checks),'values':{q:{k:v for k,v in vv.items() if k=='classification'} for q,vv in values.items()}},indent=2))
