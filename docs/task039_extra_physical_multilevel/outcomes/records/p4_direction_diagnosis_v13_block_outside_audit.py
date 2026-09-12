import hashlib,json,time,sys
from pathlib import Path
import numpy as np
start=time.perf_counter()
r=Path(sys.argv[1]); out=[]
for stem in ['A2R160_BAL_H_p4_01','A2R160_BAL_H_p4_02','LIGHT448_BAL_H_p4_09']:
 p=r/'records'/f'{stem}_p2_observation.json'; j=json.loads(p.read_text()); ap=Path(j['arrays']['path'])
 h=hashlib.sha256()
 with ap.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 assert h.hexdigest()==j['arrays']['sha256']
 with np.load(ap,allow_pickle=False) as z:
  a=lambda v:z[v['array_key']]
  hvals=a(j['h_values']); rr=a(j['r_ref_values']); vals=[]
  for b in j['local_blocks']:
   ix=a(b['indices']); chi=a(b['chi']); ell=a(b['ell']); dra=a(b['D_i_R_i_e_h'])
   scale=np.linalg.norm((hvals-rr)[ix])+np.linalg.norm(dra)
   vals.append({'block_index':b['block_index'],'chi_norm':float(np.linalg.norm(chi)), 'ell_norm':float(np.linalg.norm(ell)), 'reference_residual_norm':float(np.linalg.norm(rr[ix])), 'chi_over_Aeh_plus_DReh':float(np.linalg.norm(chi)/max(scale,np.finfo(float).tiny))})
 out.append({'stem':stem,'p2_npz_sha256':h.hexdigest(),'blocks':vals,'ranges':{k:{'min':min(v[k] for v in vals),'median':float(np.median([v[k] for v in vals])),'max':max(v[k] for v in vals)} for k in ['chi_norm','ell_norm','reference_residual_norm','chi_over_Aeh_plus_DReh']}})
d={'status':'COMPLETED','classification':'derived_from_saved_measured_vectors','source_sha':'3457b5e2f54dec690fcb70deb1f387fe7f6d57cd','inputs':out,'core_seconds':time.perf_counter()-start,'new_PC':0,'new_A4':0,'new_M0':0,'new_curl':0,'meaning':'Block coefficient norms compare operation terms only; overlaps prevent summing them as global field energy or cause percentages.'}
Path(sys.argv[2]).write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({**{k:v for k,v in d.items() if k!='inputs'},'input_ranges':[{'stem':v['stem'],'ranges':v['ranges']} for v in out]},indent=2))
