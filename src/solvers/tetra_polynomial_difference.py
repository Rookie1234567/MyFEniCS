"""Opt-in exact numerator for equal real carriers on contained affine tetra.

Physical denominators retain q23/q31. Saved blocks are actual restartable
arrays; progress alone is never a checkpoint.
"""
import hashlib
import json
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .independent_tetra_reference import CachedTetraEvaluator,TetraEvaluator
from .independent_tetra_fields import locate,evaluate_selected,selected_points
from .scattering_accuracy_fields import analytic

NAMES=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')


def require_identity(first,second):
    for key in ('materials','incidence'):
        if first['physical'][key]!=second['physical'][key]:raise ValueError('polynomial difference physical '+key)
    ka=checked_arrays(first['arrays'])['kappa'];kb=checked_arrays(second['arrays'])['kappa']
    if not np.array_equal(ka,kb) or np.any(np.asarray(ka).imag):raise ValueError('polynomial difference requires same real carrier')
    if first['spec'].get('case')!=second['spec'].get('case'):raise ValueError('different physical background/case')
    return ka.real


def parent_map(a,b):
    if len(a.geometry)==len(b.geometry) and np.array_equal(a.mesh.geometry.x,b.mesh.geometry.x) and np.array_equal(a.mesh.geometry.dofmap,b.mesh.geometry.dofmap):return np.arange(len(b.geometry),dtype=np.int32)
    mids=np.array([o+J@np.full(3,.25) for J,o,_ in b.geometry]);ids=locate(a,mids)
    for c,parent in enumerate(ids):
        J,o,_=a.geometry[int(parent)];JB,ob,_=b.geometry[c]
        vertices=np.vstack((ob,ob+JB.T));ref=(vertices-o)@np.linalg.inv(J).T
        if ref.min()<-1e-10 or ref.sum(axis=1).max()>1+1e-10:raise ValueError('common tetra not contained in actual parent')
    return ids


def norms(record,s,f,journal,folder):
    """Reuse old scattered norms; supplement missing total norms once."""
    rows=[]
    for item in record['output']['integrals']:
        q=item['q'];a=checked_arrays(item['arrays']);sc=a['per_cell_analytic_squared'].sum(axis=0)
        if 'per_cell_total_squared' in a:total_per=a['per_cell_total_squared'];total=total_per.sum(axis=0)
        else:
            path=folder/f'parent_total_norm_q{q}.json'
            if path.exists():
                r=json.loads(path.read_text())
                if r['parent']!=record['arrays']['sha256']:raise ValueError('parent norm identity')
                total_per=checked_arrays(r['arrays'])['per_cell_total_squared'];total=total_per.sum(axis=0)
            else:
                with journal.measured('supplement_old_total_norm_q'+str(q)):
                    ev=TetraEvaluator(s['V'],q,s['kappa']);per=[]
                    for c in range(len(ev.geometry)):
                        _,w,v=ev.cell(f,c,s['cfg'].k0);per.append([float(np.sum(w[:,None]*np.abs(v[k])**2)) for k in ('E','H','curl')])
                receipt=save_arrays(folder/f'parent_total_norm_q{q}.npz',per_cell_total_squared=np.asarray(per))
                total_per=np.asarray(per);total=total_per.sum(axis=0);write_json(path,dict(parent=record['arrays']['sha256'],total=total,arrays=receipt))
        rows.append(dict(q=q,reference=np.r_[total,sc[:,0]],incident=np.r_[sc[:,1],sc[:,1]],per_reference=np.c_[total_per,a['per_cell_analytic_squared'][:,:,0]],per_incident=np.c_[a['per_cell_analytic_squared'][:,:,1],a['per_cell_analytic_squared'][:,:,1]]))
    if [r['q'] for r in rows]!=[23,31]:raise ValueError('retained denominator q23/q31 inventory')
    return rows


def same_native_difference(f,g):
    """Subtract coefficients only after exact native basis/geometry checks."""
    from dolfinx import fem
    a,b=f.function_space,g.function_space
    ea,eb=a.element.basix_element,b.element.basix_element
    identities=((a.mesh.geometry.x,b.mesh.geometry.x),
                (a.mesh.geometry.dofmap,b.mesh.geometry.dofmap),
                (getattr(a.dofmap.list,'array',a.dofmap.list),
                 getattr(b.dofmap.list,'array',b.dofmap.list)),
                (ea.coefficient_matrix,eb.coefficient_matrix))
    if ea.cell_type!=eb.cell_type or ea.map_type!=eb.map_type or ea.degree!=eb.degree or any(
            not np.array_equal(x,y) for x,y in identities) or f.x.array.shape!=g.x.array.shape:
        raise ValueError('coefficient difference requires identical native basis, geometry and numbering')
    delta=fem.Function(b);delta.x.array[:]=g.x.array-f.x.array;delta.x.scatter_forward()
    return delta


def numerator(f,g,cfg,kappa,journal,folder,q,*,parent_hashes,spot=False,coefficient_first=False):
    folder.mkdir(parents=True,exist_ok=True)
    a=CachedTetraEvaluator(f.function_space,q,kappa);b=CachedTetraEvaluator(g.function_space,q,kappa)
    delta=same_native_difference(f,g) if coefficient_first else None
    parents=parent_map(a,b);identity=dict(parents=parent_hashes,q=q,carrier=list(kappa),cells=len(b.geometry),
        strategy='SAME_NATIVE_BASIS_COEFFICIENT_FIRST' if coefficient_first else 'SEPARATE_FIELDS')
    ix=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest();chunks=[]
    with journal.measured('same_real_carrier_polynomial_numerator_q'+str(q)):
        for begin in range(0,len(b.geometry),128):
            end=min(begin+128,len(b.geometry));path=folder/f'block_{begin:05d}.json'
            if path.exists():
                r=json.loads(path.read_text())
                if r['identity']!=ix or r['begin']!=begin or r['end']!=end:raise ValueError('common numerator block identity')
                chunks.append(checked_arrays(r['arrays'])['per_cell_difference']);continue
            per=[]
            for c in range(begin,end):
                J,o,det=b.geometry[c];points=b.points@J.T+o;w=abs(det)*b.weights
                if delta is not None:
                    difference=b.at(delta,c,points,cfg.k0)
                else:
                    va=a.at(f,int(parents[c]),points,cfg.k0);vb=b.at(g,c,points,cfg.k0)
                    difference={k:vb[k]-va[k] for k in ('E','H','curl')}
                per.append([float(np.sum(w[:,None]*np.abs(difference[k])**2)) for k in ('E','H','curl')])
            array=np.asarray(per);receipt=save_arrays(folder/f'block_{begin:05d}.npz',per_cell_difference=array)
            write_json(path,dict(identity=ix,begin=begin,end=end,arrays=receipt));chunks.append(array)
            journal.event('polynomial_numerator_block_committed',q=q,begin=begin,end=end,sha256=receipt['sha256'])
    per=np.concatenate(chunks);spot_rows=[]
    if spot:
        # Independent tabulate/field path, actual high q on fixed subcells.
        direct=TetraEvaluator(g.function_space,31,kappa);left=TetraEvaluator(f.function_space,31,kappa,quadrature_tables=False)
        with journal.measured('new_pair_independent_q31_fixed_subcell_check'):
            for c in np.unique(np.linspace(0,len(b.geometry)-1,8,dtype=int)):
                p,w,vg=direct.cell(g,int(c),cfg.k0);vf=left.at(f,int(parents[c]),p,cfg.k0)
                legacy=np.array([np.sum(w[:,None]*np.abs(vg[k]-vf[k])**2) for k in ('E','H','curl')])
                if delta is not None:
                    _,_,difference=direct.cell(delta,int(c),cfg.k0)
                    actual=np.array([np.sum(w[:,None]*np.abs(difference[k])**2) for k in ('E','H','curl')])
                else:actual=legacy
                op=float(np.max(np.abs(actual-per[c])/np.maximum(actual,1e-24)))
                spot_rows.append(dict(cell=int(c),polynomial=per[c],q31=actual,relative_squared=op,
                    original_separate_field_subtraction_q31=legacy,
                    separate_subtraction_relative=float(np.max(np.abs(legacy-actual)/np.maximum(actual,1e-24)))))
        write_json(folder/'independent_q31_spots.json',dict(identity=identity,rows=spot_rows))
        if max(r['relative_squared'] for r in spot_rows)>2e-6:raise ValueError('independent q31 numerator mismatch; use original comparison')
    return per,parents,spot_rows


def comparison(first,second,folder,journal,*,spot=True,coefficient_first=False):
    from benchmarks.collect_independent_tetra import restored
    from .phase_notch_hp_modes import mode_comparison
    folder.mkdir(parents=True,exist_ok=True);kappa=require_identity(first,second)
    a,_,f=restored(first,journal);b,_,g=restored(second,journal)
    for s in (a,b):
        if s['V'].mesh.basix_cell().name!='tetrahedron' or s['cfg'].mu_r!=1:raise ValueError('affine tetra/piecewise constant mu certificate')
    q=2*max(a['V'].element.basix_element.embedded_superdegree,b['V'].element.basix_element.embedded_superdegree)+3
    per,parents,spot_rows=numerator(f,g,b['cfg'],kappa,journal,folder/'numerator',q,parent_hashes=[first['arrays']['sha256'],second['arrays']['sha256']],spot=spot,coefficient_first=coefficient_first)
    denominator=norms(second,b,g,journal,folder);hi=denominator[-1];lo=denominator[0]
    sums=per.sum(axis=0);sums=np.r_[sums,sums]
    fields={k:dict(difference_squared=float(sums[j]),reference_squared=float(hi['reference'][j]),incident_squared=float(hi['incident'][j]),
        relative=float(np.sqrt(sums[j])/max(np.sqrt(hi['reference'][j]),1e-12))) for j,k in enumerate(NAMES)}
    qdef=float(np.max(np.abs(lo['reference']-hi['reference'])/np.maximum(hi['reference'],1e-24)))
    pp=selected_points(second['physical']);av,ia,_=evaluate_selected(f,b['cfg'],kappa,pp);bv,ib,_=evaluate_selected(g,b['cfg'],kappa,pp);bg=analytic(b['cfg'],pp)
    selected={};arr={}
    for name in NAMES:
        key=name.split('_')[0];x=av[key];y=bv[key]
        if name.endswith('scattered'):x=x-bg[key];y=y-bg[key]
        selected[name]=relative(x-y,y);arr['selected_'+name+'_first']=x;arr['selected_'+name+'_second']=y
    data=np.zeros((len(per),6,3));data[:,:,0]=np.c_[per,per]
    data[:,:,1]=hi['per_reference'];data[:,:,2]=hi['per_incident']
    lower=data.copy();lower[:,:,1]=lo['per_reference'];lower[:,:,2]=lo['per_incident']
    q23_receipt=save_arrays(folder/'common_denominator_q23.npz',per_cell_integrals=lower)
    receipt=save_arrays(folder/'common_polynomial.npz',per_cell_integrals=data,per_cell_difference=per,common_parent_first=parents,
        selected_points=pp,selected_parent_first=ia,selected_parent_second=ib,**arr)
    modes=mode_comparison(first,second,folder)
    power={k:abs(first['output']['port_metrics'][k]-second['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
    energies=[abs(r['output']['volume_metrics']['energy_closure_error']) for r in (first,second)]
    gate=max([v['relative'] for v in fields.values()]+list(selected.values()))<=1e-4 and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energies)<=1e-5
    result=dict(backend='SAME_REAL_CARRIER_POLYNOMIAL_DIFFERENCE',fields=fields,selected=selected,arrays=receipt,q=q,
        quadrature_pair=[23,31],quadrature_operation_scaled=qdef,q23_arrays=q23_receipt,modes=modes,power_differences=power,energies=energies,
        parent_array_sha256=[first['arrays']['sha256'],second['arrays']['sha256']],physical_truth_not_assumed=True,
        numerator_certificate=dict(q=q,actual_superdegrees=[a['V'].element.basix_element.embedded_superdegree,b['V'].element.basix_element.embedded_superdegree],spot_q31=spot_rows,
            coefficient_first_same_native_basis=coefficient_first),
        per_cell_denominator_location='actual original or once-supplemented second-field integral packet',
        pass_gate=gate,classification='SPACE_INCREMENT_PASS' if gate else 'SPACE_INCREMENT_FAIL')
    write_json(folder/'comparison.json',result);return result
