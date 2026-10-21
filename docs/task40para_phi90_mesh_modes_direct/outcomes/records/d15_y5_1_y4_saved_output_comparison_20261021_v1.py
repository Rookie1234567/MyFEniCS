"""Offline saved-output comparison of D15 Y5-1 against Y4-1 and Y4-3; no FE/factor/VTU/resources."""
import hashlib, itertools, json
from pathlib import Path
import numpy as np
W=Path('/home/fenics/Projects/Maxwell3D-Phi90')
ROOT=W/'results/si_block_phi90_50x50_17x20_h120'
MODE_SHA='1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e'
P_GLOBAL=1e-5; P_MODE=1e-6; P_FIELD=1e-4
runs={
 'Y4-1':ROOT/'task40_phi90_13p5_D15_Y3_3_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T095046.847009Z',
 'Y4-1':ROOT/'task40_phi90_13p5_D15_Y3_3_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T095046.847009Z',
 'Y4-3':ROOT/'task40_phi90_13p5_D15_Y4_4_4_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T110215.702256Z',
 'Y5-1':ROOT/'task40_phi90_13p5_D15_Y5_1_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T115035.556208Z',
}
def readj(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cval(x): return complex(float(x[0]),float(x[1]))
def load(label,run):
 m=readj(run/'run_manifest.json'); s=readj(run/'run_summary.json'); phase=readj(run/'workflow_phase.json')
 pwr=readj(run/'numerical_output/dtn_port_power_metrics_3d.json'); vol=readj(run/'numerical_output/volume_absorption.json')
 orders=readj(run/'numerical_output/dtn_port_diffraction_orders_3d.json')['orders']
 evi=readj(run/'numerical_output/task40_direct_factor_evidence/evidence.json')
 assert s['status']=='finished' and s['exit_status']==0 and s['resource_authority']['descendants_cleared'] is True
 assert phase['phase']=='complete' and phase['facts']['passed'] is True
 assert pwr['active_mode_count']==612 and pwr['active_mode_sha256']==MODE_SHA
 assert pwr['dtn_sparse_cutoff_policy']=='scale_homogeneous_relative_only_v1'
 assert len(orders)==612
 keyed={(str(o['side']),int(o['m']),int(o['n']),str(o['polarization'])):o for o in orders}
 assert len(keyed)==612
 assert evi['operator_identity']['active_mode_sha256']==MODE_SHA
 assert evi['operator_identity']['dtn_sparse_cutoff_policy']=='scale_homogeneous_relative_only_v1'
 assert evi['operator_identity']['parent_quadrature_degree']==28
 vr=evi['operator_identity']['volume_quadrature_records']
 assert vr and all(x['quadrature_degree']==15 and x['quadrature_rule']=='default' for x in vr)
 with np.load(run/'numerical_output/full3d_reference_samples.npz',allow_pickle=False) as z: samples={k:z[k].copy() for k in z.files}
 sm=readj(run/'numerical_output/full3d_reference_samples.json')
 resolved=readj(run/'resolved_config.json')
 phys={k:resolved[k] for k in ('geometry','materials','incidence','boundary')}
 return {'label':label,'run':run,'manifest':m,'summary':s,'phase':phase,'power':pwr,'volume':vol,'keyed':keyed,'samples':samples,'sample_meta':sm,'physical':phys,'evidence':evi,'identity':{'run_id':m['run_id'],'source_sha':m['source_sha'],'input_sha256':m['input_sha256'],'physical_model_sha256':m['physical_model_sha256'],'resolved_config_sha256':m['resolved_config_sha256'],'run_manifest_sha256':sha(run/'run_manifest.json'),'run_summary_sha256':sha(run/'run_summary.json'),'phase_sha256':sha(run/'workflow_phase.json'),'factor_evidence_sha256':sha(run/'numerical_output/task40_direct_factor_evidence/evidence.json'),'sample_archive_sha256':sha(run/'numerical_output/full3d_reference_samples.npz'),'sample_archive_internal_sha256':sm['archive_sha256'],'mode_count':612,'mode_sha256':MODE_SHA,'surface_q':28,'volume_q':15,'volume_rule':'default','cutoff_policy':pwr['dtn_sparse_cutoff_policy'],'operator_scope':evi['operator_identity']['operator_scope'],'axis_cell_counts':resolved['discretization']['mesh_axis_cell_counts'],'y_values_nm':resolved['discretization']['mesh_axis_y_values'],'single_run_status':phase['facts']['status'],'full_dtn_status':pwr['full_dtn_status']}}
def argmax_signed(d,keys,component):
 if not len(d): return {'max_abs_delta':0.0,'delta':0.0,'key':None,'reference':None,'candidate':None}
 i=int(np.argmax(np.abs(d))); return {'max_abs_delta':float(abs(d[i])),'delta':float(d[i]),'key':list(keys[i]),'reference':float(refvals[i]),'candidate':float(candvals[i])}
def norm(a,b):
 a=np.asarray(a);b=np.asarray(b)
 if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all(): raise ValueError(f'invalid arrays {a.shape} {b.shape}')
 na=float(np.linalg.norm(a.ravel()));nd=float(np.linalg.norm((b-a).ravel()))
 return {'reference_l2':na,'difference_l2':nd,'relative_l2_no_phase_fit':nd/na if na else None,'max_abs_delta':float(np.max(np.abs(b-a))),'max_abs_index':[int(i) for i in np.unravel_index(np.argmax(np.abs(b-a)),a.shape)]}
def compare(ref,cand):
 if ref['physical']!=cand['physical']: raise ValueError('geometry/material/incidence/boundary mismatch')
 if set(ref['keyed'])!=set(cand['keyed']): raise ValueError('modal key mismatch')
 keys=sorted(ref['keyed']); A=ref['keyed'];B=cand['keyed']
 for k in keys:
  for flag in ('propagating','power_carrying','rayleigh_warning'):
   if bool(A[k].get(flag))!=bool(B[k].get(flag)): raise ValueError(f'class mismatch {k} {flag}')
 groups={'all_612':keys,'power_carrying':[k for k in keys if A[k]['power_carrying']],'propagating':[k for k in keys if A[k]['propagating']]}
 per={}
 for g,ks in groups.items():
  per[g]={}
  for comp in ('R','T'):
   vals=np.array([float(B[k][comp])-float(A[k][comp]) for k in ks],dtype=float)
   i=int(np.argmax(np.abs(vals))) if len(vals) else 0
   per[g][comp]={'count':len(ks),'max_abs_delta':float(abs(vals[i])) if len(vals) else 0.0,'signed_delta':float(vals[i]) if len(vals) else 0.0,'key':list(ks[i]) if len(vals) else None,'reference':float(A[ks[i]][comp]) if len(vals) else None,'candidate':float(B[ks[i]][comp]) if len(vals) else None,'l2_delta':float(np.linalg.norm(vals)),'over_limit_count':int(np.count_nonzero(np.abs(vals)>P_MODE)),'limit':P_MODE,'pass':bool(not np.any(np.abs(vals)>P_MODE))}
 glob={}
 for name,ra,rb,lim in [('R_total',ref['power']['R_total'],cand['power']['R_total'],P_GLOBAL),('T_total',ref['power']['T_total'],cand['power']['T_total'],P_GLOBAL),('A_balance',ref['power']['A_balance'],cand['power']['A_balance'],P_GLOBAL),('A_volume',ref['volume']['A_volume_total'],cand['volume']['A_volume_total'],P_GLOBAL),('R00_s',ref['power']['R00_s'],cand['power']['R00_s'],P_MODE),('R00_total',ref['power']['R00_total'],cand['power']['R00_total'],P_MODE)]:
  delta=float(rb)-float(ra);glob[name]={'reference':float(ra),'candidate':float(rb),'signed_delta':delta,'abs_delta':abs(delta),'limit':lim,'pass':abs(delta)<=lim}
 # Boundary-plane complex outgoing amplitudes, all exact common keys, no phase fit.
 ba=np.array([cval(A[k]['outgoing_amplitude_at_boundary']) for k in keys]);bb=np.array([cval(B[k]['outgoing_amplitude_at_boundary']) for k in keys]);bn=norm(ba,bb);bi=int(np.argmax(np.abs(bb-ba)))
 boundary={'count':len(keys),**bn,'max_delta_key':list(keys[bi]),'limit':P_FIELD,'pass':bn['relative_l2_no_phase_fit'] is not None and bn['relative_l2_no_phase_fit']<=P_FIELD}
 # Exact coordinate and complex arrays; no interpolation or phase alignment.
 a=ref['samples'];b=cand['samples'];coord={}
 for key in ('x_nm','y_nm','z_nm','interface_z_nm'):
  coord[key]=bool(np.array_equal(a[key],b[key]))
 if not all(coord.values()): raise ValueError(f'sample coordinates differ: {coord}')
 field={}
 for name in ('E_V_per_m','H_A_per_m'):
  field[name]=norm(a[name],b[name]);field[name]['limit']=P_FIELD;field[name]['pass']=field[name]['relative_l2_no_phase_fit'] is not None and field[name]['relative_l2_no_phase_fit']<=P_FIELD
 horiz={}
 for name in ('E_t_interface_V_per_m','H_t_interface_A_per_m'):
  horiz[name]=norm(a[name],b[name]);horiz[name]['scope']='horizontal interface z planes only; not canonical pillar sidewalls'
 global_pass=all(glob[k]['pass'] for k in ('R_total','T_total','A_balance','A_volume'))
 modes_pass=all(per['all_612'][k]['pass'] and per['power_carrying'][k]['pass'] for k in ('R','T')) and glob['R00_s']['pass'] and glob['R00_total']['pass']
 boundary_field_pass=boundary['pass'] and field['E_V_per_m']['pass'] and field['H_A_per_m']['pass']
 return {'reference':ref['label'],'candidate':cand['label'],'global_observables':glob,'per_mode_R_T':per,'boundary_complex_amplitude':boundary,'same_coordinate_fields':{'coordinates_exact_equal':coord,'E_H':field,'horizontal_Et_Ht_diagnostics_only':horiz,'comparison':'saved complex arrays on exact common coordinates; no interpolation; no phase fitting','canonical_sidewall':'NOT_MEASURED'},'gate_groups':{'global_R_T_A_balance_A_volume':global_pass,'all_common_mode_R_T_including_power_carrying_and_R00_s':modes_pass,'boundary_and_same_coordinate_E_H':boundary_field_pass},'all_three_gate_groups_pass':bool(global_pass and modes_pass and boundary_field_pass)}
loaded={name:load(name,path) for name,path in runs.items()}
for name in list(loaded)[1:]:
 if loaded[name]['physical']!=loaded['Y4-1']['physical']: raise ValueError(f'physical identity differs {name}')
pairs=[]
for refname,candname in [('Y4-1','Y5-1'),('Y4-3','Y5-1')]:pairs.append(compare(loaded[refname],loaded[candname]))
payload={'schema':'task40.d15.y5_1_y4_saved_output_comparison.v1','created_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),'scope':'offline saved-output comparisons only; no FE, factor, VTU or resource-stream reads','aliases':{'Y4-1':'internal D15_Y3_3 3/6/3','Y4-3':'internal D15_Y4_4_4 4/4/4','Y5-1':'internal D15_Y5_1 4/6/4'},'identities':{k:v['identity'] for k,v in loaded.items()},'thresholds':{'global_R_T_A_balance_A_volume_abs':P_GLOBAL,'each_channel_R_T_abs_all_612_and_power_carrying':P_MODE,'R00_s_R00_total_abs':P_MODE,'boundary_complex_amplitude_relative_l2_no_phase_fit':P_FIELD,'same_coordinate_complex_E_H_relative_l2_no_phase_fit':P_FIELD},'method':'mode-key joins by side,m,n,polarization; all 612 plus power-carrying and propagating groups reported. Boundary uses saved outgoing amplitude at boundary plane. E/H samples compared as exact common complex arrays; no interpolation/phase fitting.','grid_scope':{'Y4-1_to_Y5-1':'y segment counts 3/6/3 -> 4/6/4; x,z unchanged.','Y4-3_to_Y5-1':'y segment counts 4/4/4 -> 4/6/4; x,z unchanged.'},'source_identity_note':'Y4-1 and Y4-3 use source ee5793a9b6a62de52730f1b78de334ac01a53ced; Y5-1 uses source 55c58972d230f53103f8ef6cb950ebb9417711cb. The source diff is limited to the new Y5-1 axis plan, dat/profile dispatch and its focused tests; no operator, quadrature, cutoff, assembly or solve arithmetic changed.','limitations':['FULL_DTN_NOT_VERIFIED','canonical_sidewall_NOT_MEASURED; horizontal Et/Ht are diagnostics only'],'comparisons':pairs}
out=Path(__file__).with_suffix('.json');out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'output':str(out),'sha256':sha(out),'comparisons':[{'reference':x['reference'],'candidate':x['candidate'],'global':x['gate_groups']['global_R_T_A_balance_A_volume'],'modes':x['gate_groups']['all_common_mode_R_T_including_power_carrying_and_R00_s'],'field':x['gate_groups']['boundary_and_same_coordinate_E_H'],'all':x['all_three_gate_groups_pass'],'global_deltas':{k:v['abs_delta'] for k,v in x['global_observables'].items()},'max_R_all':x['per_mode_R_T']['all_612']['R'],'max_T_all':x['per_mode_R_T']['all_612']['T'],'max_R_pc':x['per_mode_R_T']['power_carrying']['R'],'max_T_pc':x['per_mode_R_T']['power_carrying']['T'],'boundary_rel':x['boundary_complex_amplitude']['relative_l2_no_phase_fit'],'E_rel':x['same_coordinate_fields']['E_H']['E_V_per_m']['relative_l2_no_phase_fit'],'H_rel':x['same_coordinate_fields']['E_H']['H_A_per_m']['relative_l2_no_phase_fit']} for x in pairs]},sort_keys=True,indent=2))
