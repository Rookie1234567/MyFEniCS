"""Complete saved-array axis/action/witness checks without production runner."""
import json, hashlib
from pathlib import Path
import numpy as np, basix, basix.ufl, mpmath as mp
from src.solvers.task40_w1_moment_reference import legendre_exponential_moments as moments
ROOT=Path.cwd(); ART=ROOT/'benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl'
RAW=ROOT/'benchmarks/artifacts/task40extra_0p7nm_engineering/local_w1_wsl/w1_probe_c354afa_retry1_20261004T1654Z/probe/w1_boundary_probe_arrays.npz'
MAN=ROOT/'benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json'
import runpy
base=runpy.run_path(str(ART/'analyze_saved_w1_moment_reference.py'))
with np.load(RAW,allow_pickle=False) as f: old={k:f[k] for k in f.files}
modes=json.loads(MAN.read_text())['modes']; x=old['surface_x_axis_nm']; y=old['surface_y_axis_nm']
nx,ny=len(x)-1,len(y)-1; i,j=map(int,old['representative_face_indices'][0])
x0,dx=float(x[i]),float(x[i+1]-x[i]); y0,dy=float(y[j]),float(y[j+1]-y[j])
el=basix.ufl.element('N1curl','hexahedron',6).basix_element; p=int(el.degree)
q,_=np.polynomial.legendre.leggauss(p+1); q=(q+1)/2; v=np.polynomial.legendre.legvander(2*q-1,p)
g0,g1=np.meshgrid(q,q,indexing='ij'); fc={}; maps={}
for side in ('bottom','top'):
 active,rows,weights=base['face_map'](el,side,i,j,nx,ny,old['floquet_phases'],len(old['trace']))
 zref=0. if side=='bottom' else 1.
 pts=np.column_stack((g0.ravel(),g1.ravel(),np.full(g0.size,zref)))
 tab=el.tabulate(0,pts)[0][:,:,:2].reshape(p+1,p+1,el.dim,2)
 a=np.linalg.solve(v,tab.reshape(p+1,-1)).reshape(tab.shape)
 coeff=np.linalg.solve(v,a.swapaxes(0,1).reshape(p+1,-1)).reshape(tab.shape).swapaxes(0,1)
 fc[side]=coeff[:,:,active,:]
 maps[side]=(rows,weights)
rule,w=basix.make_quadrature(basix.CellType.interval,60); rr=rule[:,0]
vv=np.polynomial.legendre.legvander(2*rr-1,p)
def oldmom(k,x0,L):
 return (w*np.exp(-1j*np.conj(k)*(x0+L*rr)))@vv
ex,ey,ox,oy={},{},{},{}
ref=np.empty((len(modes),2),complex); refx_oldy=ref.copy(); oldx_refy=ref.copy()
for idx,row in enumerate(modes):
 kv=tuple(base['z'](v) for v in row['k_vector'])
 if kv[0] not in ex:
  ex[kv[0]]=np.array([complex(v) for v in moments(-kv[0].conjugate(),x0,dx,p,dps=80)])
  ox[kv[0]]=oldmom(kv[0],x0,dx)
 if kv[1] not in ey:
  ey[kv[1]]=np.array([complex(v) for v in moments(-kv[1].conjugate(),y0,dy,p,dps=80)])
  oy[kv[1]]=oldmom(kv[1],y0,dy)
 side=row['side']; rows,wt=maps[side]; cell=np.einsum('abdc,d->abc',fc[side],old['trace'][rows]*wt,optimize=True)
 phase=np.exp(-1j*kv[2].conjugate()*(-10. if side=='bottom' else 130.))
 def proj(mx,my): return phase*np.einsum('a,b,abc->c',mx,my,cell,optimize=True)*np.array([dy,dx])
 ref[idx]=proj(ex[kv[0]],ey[kv[1]])
 refx_oldy[idx]=proj(ex[kv[0]],oy[kv[1]])
 oldx_refy[idx]=proj(ox[kv[0]],ey[kv[1]])
e=np.asarray([[base['z'](v) for v in r['e_vector'][:2]] for r in modes],complex)
t=np.asarray([[base['z'](v) for v in r['traction_vector'][:2]] for r in modes],complex)
h=np.asarray(old['denominators'],float)
rec=np.sum(e.conj()*ref,axis=1)/h
rhs=-t*rec[:,None]
apply=np.zeros_like(old['q60_apply'])
for idx,row in enumerate(modes):
 kv=tuple(base['z'](v) for v in row['k_vector']); side=row['side']
 rows,wt=maps[side]
 phase=np.exp(-1j*kv[2].conjugate()*(-10. if side=='bottom' else 130.))
 basis=np.einsum('a,b,abdc->dc',ex[kv[0]],ey[kv[1]],fc[side],optimize=True)
 basis*=phase*np.array([dy,dx])[None,:]
 local=np.sum(basis.conj()*rhs[idx][None,:],axis=1)*wt.conj()
 np.add.at(apply,rows,local)
apply_rel=np.linalg.norm(apply-old['q60_apply'])/max(np.linalg.norm(apply),np.finfo(float).tiny)
scale=np.maximum(np.linalg.norm(old['q60_components'],axis=1)/np.abs(h),np.finfo(float).tiny)
def recerr(comp):
 return np.abs(np.sum(e.conj()*comp,axis=1)/h-rec)/scale
mix_xy=recerr(refx_oldy); mix_yx=recerr(oldx_refy)
round_rel=np.zeros(len(modes)); eps=np.finfo(float).eps; gamma=256*eps/(1-256*eps)
for idx,row in enumerate(modes):
 kv=tuple(base['z'](v) for v in row['k_vector']); side=row['side']
 rows,wt=maps[side]; cell=np.einsum('abdc,d->abc',fc[side],old['trace'][rows]*wt,optimize=True)
 ax,ay=ex[kv[0]],ey[kv[1]]
 sums=np.asarray([np.sum(np.abs(ax[:,None]*ay[None,:]*cell[:,:,c])) for c in (0,1)])
 bound=gamma*sums*np.asarray([dy,dx])
 round_rel[idx]=(abs(e[idx,0])*bound[0]+abs(e[idx,1])*bound[1])/abs(h[idx])/scale[idx]
rep_error={}
for side in ('bottom','top'):
 active=base['active_dofs'](el,side); rows,wt=maps[side]
 local=old['trace'][rows]*wt; zref=0. if side=='bottom' else 1.
 test=np.array([[.137,.731],[.913,.287]])
 pts=np.column_stack((test,np.full(2,zref)))
 direct=np.einsum("qdc,d->qc",el.tabulate(0,pts)[0][:,active,:2],local) # @ local
 cell=np.einsum('abdc,d->abc',fc[side],local,optimize=True)
 vx=np.polynomial.legendre.legvander(2*test[:,0]-1,p)
 vy=np.polynomial.legendre.legvander(2*test[:,1]-1,p)
 approx=np.einsum('qa,qb,abc->qc',vx,vy,cell,optimize=True)
 rep_error[side]=float(np.max(np.abs(direct-approx)))
def direct_mom(k,x0,L,dps=100):
 ctx=mp.mp.clone(); ctx.dps=dps
 kw=-ctx.conj(ctx.mpc(float(k.real),float(k.imag)))
 x0p,Lp=ctx.mpf(x0),ctx.mpf(L); out=[]
 for ell in range(p+1):
  out.append(ctx.quad(lambda r:ctx.legendre(ell,2*r-1)*ctx.exp(ctx.j*kw*(x0p+Lp*r)),[0,.2,.4,.6,.8,1]))
 return tuple(out)
witness_ids=[8576,6018,6158]; witness_values=[]; witness_errors=[]; witness_keys=[]
for idx in witness_ids:
 row=modes[idx]; kv=tuple(base['z'](v) for v in row['k_vector']); side=row['side']
 mx=direct_mom(kv[0],x0,dx); my=direct_mom(kv[1],y0,dy)
 rows,wt=maps[side]; cell=np.einsum('abdc,d->abc',fc[side],old['trace'][rows]*wt,optimize=True)
 ctx=mp.mp.clone(); ctx.dps=110
 phase=ctx.exp(-ctx.j*ctx.conj(ctx.mpc(kv[2].real,kv[2].imag))*ctx.mpf(-10. if side=='bottom' else 130.))
 vals=[]
 for c,sc in enumerate((dy,dx)):
  total=ctx.mpc(0)
  for a in range(p+1):
   for b in range(p+1):
    qv=cell[a,b,c]; co=ctx.mpc(float(qv.real),float(qv.imag))
    total += ctx.mpc(mx[a])*ctx.mpc(my[b])*co
  vals.append(phase*total*ctx.mpf(sc))
 d=np.asarray([complex(v) for v in vals]); witness_values.append(d)
 witness_errors.append(float(np.linalg.norm(d-ref[idx])/max(np.linalg.norm(d),np.finfo(float).tiny)))
 witness_keys.append([row['side'],row['m'],row['n'],row['polarization']])
refrel=np.abs(np.sum(e.conj()*old['q60_components'],axis=1)/h-rec)/scale
mixmax={'reference_x_q60_y':float(mix_xy.max()),'q60_x_reference_y':float(mix_yx.max())}
actcheck={'relative_to_reference':float(apply_rel),
 'relative_q60_to_q30':float(np.linalg.norm(old['q60_apply']-old['q30_apply'])/max(np.linalg.norm(old['q60_apply']),np.finfo(float).tiny))}
roundoff={'max_recovered_relative_bound':float(round_rel.max()),
 'pass_below_1e-12':bool(round_rel.max()<1e-12)}
npzout=ART/'w1_reference_completion_raw_v2.npz'
np.savez_compressed(npzout,reference_components_80=ref,
 reference_x_q60_y=refx_oldy,q60_x_reference_y=oldx_refy,
 reference_action_80=apply,q60_components_saved=old['q60_components'],
 q60_apply_saved=old['q60_apply'],witness_mode_index=np.asarray(witness_ids,np.int32),
 witness_keys=np.asarray(witness_keys,dtype='U16'),
 witness_direct_100=np.asarray(witness_values),witness_reference_80=ref[witness_ids])
rawhash=hashlib.sha256(npzout.read_bytes()).hexdigest()
report={
 'schema':'task40extra.w1_reference_completion.v2',
 'scope':'offline saved-array reference diagnostics; no PDE, no production runner',
 'mode_count':len(modes),'mpmath_dps':80,'q60_scalar_reference_max':float(refrel.max()),
 'q60_scalar_reference_pass':bool(refrel.max()<=1e-10),
 'mixed_axis_max_recovered_relative':mixmax,'full_action':actcheck,
 'representation_offgrid_max_abs':rep_error,'roundoff_bound':roundoff,
 'three_actual_key_witnesses':[{'mode_index':k,'key':witness_keys[n],
  'direct100_vs_ref80_relative':witness_errors[n]} for n,k in enumerate(witness_ids)],
 'new_raw_npz':npzout.name,'new_raw_npz_sha256':rawhash,
 'gate_complete':bool(refrel.max()<=1e-10 and apply_rel<=1e-10 and
  max(mixmax.values())<=1e-10 and max(rep_error.values())<1e-12 and
  round_rel.max()<1e-12 and max(witness_errors)<1e-12),
 'p6_started':False}
out=ART/'w1_reference_completion_v2.json'
out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(report,indent=2,sort_keys=True))
