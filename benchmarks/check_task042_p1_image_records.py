"""Independent raw-field decision reconstruction; no FE/solver execution."""
import csv,json,math,sys
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def bounded(values,tolerance):return all(math.isfinite(float(v)) and float(v)<=tolerance for v in values)
def check(root):
 s=read(root/'setup_QR_v23.json');d=read(root/'small_overlap_Gate_v23.json');c=read(root/'coarse_compare_v23.json')
 q=s['decomposition'];qr=bounded((q['QR_reconstruction_relative'],q['U_orthogonality_normalized_Frobenius'],q['TH_W_Ac']['operation_relative']),1e-10)
 rank=q['R_safety']['ratio']>=1e-12 and math.isfinite(q['R_safety']['ratio'])
 pairs=bounded((row[k]['operation_relative'] for row in s['witnesses'] for k in ('W_original','UR_original','JAT')),1e-10)
 pairs=pairs and bounded((row['operation_relative'] for row in s['old_class_action_pairs']),1e-10)
 image=qr and rank and pairs and s['zero_exact'] and s['MR_stationarity_operation_relative']<=1e-8
 pc=image and d['D_safety']['ratio']>=1e-12 and d['DH_R_Ac']['operation_relative']<=1e-10
 if pc:
  actual=d['right_PC'];pc=bounded((actual['repeat']['operation_relative'],actual['complex_linearity']['operation_relative'],*(r['operation_relative'] for r in actual['UH_A_B_balance'])),1e-10)
 assert image==s['image_qualified'] and pc==d['PC_qualified']
 assert s['reading_permission']==dict(warm_NPZ_decoded=False,reference_arrays_read=False)
 for r in c['comparison'].values():
  assert r['MR_residual_norm']<=min(r['G_residual_norm'],r['original_residual_norm'])+r['inequality_fixed_margin']
 for r in c['warm_corrections'].values():assert r['actual_thin_residual_difference_full_b']<=1e-11
 candidates=list(csv.DictReader((root/'candidate_comparison_v23.csv').open()));count=0
 fields=read(root/'field_checks_v23.json')
 for r in candidates:
  original=fields['rows'][r['state']]['audit']
  eq=all(math.isfinite(float(r[k])) and float(r[k])<=1e-6 for k in ('Schur','native','augmented','port_full','port_operation'))
  eq=eq and bounded((original['original_total_augmented_relative'],),1e-6)
  eq=eq and max(float(r['recovery']),float(r['identity']))<=1e-10 and float(r['slave'])==0
  field=all(math.isfinite(float(r[k])) and float(r[k])<=1e-4 for k in ('total_E','total_curl','scattered_E','scattered_curl','selected_E','selected_H','complex_ports'))
  passed=eq and fields['reference_native_pass'] and field and float(r['independent_total_native'])<=1e-6 and float(r['max_RTA_Avolume_difference'])<=1e-5 and float(r['max_channel_power_difference'])<=1e-6 and float(r['energy_closure'])<=1e-5
  assert passed==(r['strict_qualified']=='True');count+=passed
 channels=list(csv.DictReader((root/'field_channels_v23.csv').open()))
 for r in candidates:
  rows=[x for x in channels if x['state']==r['state']]
  assert len(rows)==40 and len({int(x['index']) for x in rows})==40
  for x in rows:
   assert abs((float(x['total_real'])-float(x['reference_total_real']))-float(x['error_real']))<=1e-14
   assert abs((float(x['total_imag'])-float(x['reference_total_imag']))-float(x['error_imag']))<=1e-14
 assert count==read(root/'qualification_and_dispatch_v23.json')['passed']
 cost=read(root/'resource_costs_v23.json');assert cost['own_swap_peak_bytes']==0 and cost['simultaneous_sampled_tree_peak_bytes']<16*2**30
 caps=dict(actions=32000,B_M=15000,R_triangular=16000,audits=120,field_states=10,image_builds=1,image_columns=1248,image_QR=1,R_SVD=1,D_SVD=1,factor_setups=1,G_triangular=64)
 assert all(cost['charged'][k]<=v for k,v in caps.items())
 assert cost['storage']['artifacts']['logical_bytes']<=2*2**30
 return dict(image_qualified=image,PC_qualified=pc,states=len(candidates),passed=count,all_limits_pass=True,raw_fields_recomputed=True)
if __name__=='__main__':print(json.dumps(check(Path(sys.argv[1]))))
