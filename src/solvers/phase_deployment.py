"""Deployment-local independent audit and paired physical carrier study.

No solver is reimplemented here: three explicit cases call the inherited
condensation/direct/recovery chain. All research comparisons run afterwards.
"""
import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from src.runners.task042_shared import write_json
from . import phase_deployment_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .phase_notch_hp import solve_case,restore_record
from .phase_saved_uncondensed import local_vectors,uncondensed_vectors,saved_audit
from .phase_boundary_checkpoint import packed_action


def gauge_identity(points,u,curl,k,G):
    """Independent product-rule control, not a finite-space equivalence claim."""
    phase=np.exp(-1j*(points@G))[:,None];up=phase*u
    cp=phase*(curl-1j*np.cross(G,u))
    E=np.exp(1j*(points@k))[:,None]*u
    Ep=np.exp(1j*(points@(k+G)))[:,None]*up
    C=np.exp(1j*(points@k))[:,None]*(curl+1j*np.cross(k,u))
    Cp=np.exp(1j*(points@(k+G)))[:,None]*(cp+1j*np.cross(k+G,up))
    return dict(E=relative(Ep-E,E),curl=relative(Cp-C,C),incident_envelope=up,
        continuous_gauge_only=True,finite_spaces_identical=False)


def quadrature_certificate(element,q):
    import basix
    d=int(element.embedded_superdegree);pts,w=basix.make_quadrature(basix.CellType.hexahedron,q)
    powers=[tuple(a if j==i else 0 for j in range(3)) for i in range(3) for a in range(2*d+1)]
    powers += [(2*d,2*d,2*d),(d,d+1,2*d)]
    errors=[abs(np.dot(w,np.prod(pts**np.asarray(a),axis=1))-np.prod([1/(v+1) for v in a])) for a in powers]
    return dict(embedded_superdegree=d,q=q,actual_points=len(w),polyset=str(element.polyset_type),
        tensor_product_degree_bound=[2*d]*3,monomial_absolute_max=max(errors),
        polynomial_moments=save_moments(pts,w,powers,errors),pass_gate=q>=2*d and max(errors)<=1e-12)


def save_moments(pts,w,powers,errors):
    # Small scalar-only descriptor; actual points and weights bound by digest.
    from .scattering_anchor import array_hash
    return dict(points_sha256=array_hash(pts),weights_sha256=array_hash(w),powers=powers,errors=errors)


def old_high_body(role):
    if role=='B6':return scope.parent(role)['independent']['arrays']
    from .phase_saved_closure_scope import stage
    return stage('S')['R7_original_regression']['arrays']


def body_qualification(role,folder,journal):
    r=scope.parent(role);restored=restore_record(r,journal,scope=scope);cfg,setup,geo,field=restored
    v=checked_arrays(r['arrays']);highrec=old_high_body(role);high=checked_arrays(highrec)
    if not np.array_equal(high['u_storage'],v['u_storage']):raise ValueError('q31 oracle belongs to different saved state')
    q=15 if r['degree']==6 else 17;cert=quadrature_certificate(field.function_space.element.basix_element,q)
    if not cert['pass_gate']:return dict(role=role,certificate=cert,pass_gate=False,fallback_q=31)
    low=uncondensed_vectors(field,cfg,v['kappa'],setup['floquets'][r['degree']].mpc,setup['mesh_data'],folder/'low_blocks',journal,q=q,
        identity=dict(parent_npz_sha256=r['arrays']['sha256'],qualification_only=True))
    names=('volume_action','volume_inside','volume_trace');rels=[relative(low['volume'][:,i]-high[k],high[k]) for i,k in enumerate(names)]
    cellrows=[];highroot=Path(highrec['path']).parent/'volume_blocks'
    if not highroot.is_dir():raise ValueError('saved full q31 cell curl/mass inventory absent')
    for c in range(r['case_spec']['cells']):
        a=json.loads((folder/'low_blocks'/f'cell_{c:06d}.json').read_text());b=json.loads((highroot/f'cell_{c:06d}.json').read_text())
        x=checked_arrays(a['arrays']);y=checked_arrays(b['arrays'])
        if not np.array_equal(x['rows'],y['rows']):raise ValueError('q31/low native row inventory')
        op=[float(np.linalg.norm(x['curl'][:,j]-y['curl'][:,j])+np.linalg.norm(x['mass'][:,j]-y['mass'][:,j]))/
            max(float(np.linalg.norm(y['curl'][:,j])+np.linalg.norm(y['mass'][:,j])),1e-30) for j in range(3)]
        cellrows.append(dict(cell=c,operation_scaled=op))
    actual=save_arrays(folder/'low_assembled_vectors.npz',curl=low['curl'],mass=low['mass'],volume=low['volume'])
    operation=max(max(x['operation_scaled']) for x in cellrows)
    out=dict(role=role,parent=r['arrays']['sha256'],q31_original=highrec,certificate=cert,vector_relative=rels,
        operation_scaled_max=operation,per_cell=cellrows,arrays=actual,
        pass_gate=max(rels)<=1e-10 and operation<=1e-12,qualification_scope='only polynomial body action; never RHS/Fourier/cross-gauge integrals')
    write_json(folder/'qualification.json',out)
    return out


def continuous_gauge_flat(cfg,modes,k,kp,folder,journal):
    """Four continuous lifts, full physical ports/load, no FE interpolation.

    The test envelope is changed together with the analytic field envelope.
    Body uses q31, Fourier boundary q63; the polynomial body shortcut is not
    applied to exponential functions. All 828 keys remain in the saved port
    inventory, even though the exact flat solution has zero diffracted modes.
    """
    import basix
    from src.common.analytic_fields_3d import fresnel_reference
    from .scattering_accuracy_fields import analytic
    from .common_continuous_weak import volume_parts
    from .dtn_port_3d import _traction_vector,_mode_boundary_phase,_incident_projection_onto_top_mode
    ref=fresnel_reference(cfg);port=np.zeros(len(modes),complex)
    inc=np.asarray([_incident_projection_onto_top_mode(m,cfg) for m in modes])
    for i,m in enumerate(modes):
        if (m.m,m.n,m.polarization)==(0,0,'s'):
            port[i]=cfg.incident_amplitude*(ref['r'] if m.side=='top' else ref['t'])
    port+=inc
    if np.linalg.norm(port)==0 or np.linalg.norm(inc)==0:raise ValueError('nonzero physical flat port/load control')
    lo=np.array([cfg.x_min,cfg.y_min,cfg.z_min]);hi=np.array([cfg.x_max,cfg.y_max,cfg.z_max]);G=kp-k
    definitions=[(side,a) for side in ('top','bottom') for a in (0,1)]
    def lifts(points):
        zz=(points[:,2]-lo[2])/(hi[2]-lo[2]);v=[];cv=[]
        for side,a in definitions:
            unit=np.eye(3)[a];sign=1 if side=='top' else -1
            phi=zz if sign==1 else 1-zz
            v.append(phi[:,None]*unit);cv.append(np.broadcast_to(np.cross([0.,0.,sign/(hi[2]-lo[2])],unit),(len(points),3)))
        return np.asarray(v),np.asarray(cv)
    terms=[];ops=[];bounds=[lo[2],0.,hi[2]]
    points,w=basix.make_quadrature(basix.CellType.hexahedron,31)
    with journal.measured('continuous_flat_paired_gauge_body_and_q63_ports'):
        for carrier in (k,kp):
            body=np.zeros((5,4),complex);operation=np.zeros(4)
            for z0,z1 in zip(bounds[:-1],bounds[1:]):
                box0=lo.copy();box0[2]=z0;box1=hi.copy();box1[2]=z1
                xyz=box0+points*(box1-box0);ww=w*np.prod(box1-box0);v,cv=lifts(xyz)
                if np.array_equal(carrier,kp):
                    ph=np.exp(-1j*(xyz@G))[None,:,None]
                    cv=ph*(cv-1j*np.cross(G,v));v=ph*v
                epsilon=cfg.eps_substrate if z1<=0 else cfg.eps_air
                a,b=volume_parts(analytic(cfg,xyz),xyz,ww,v,cv,kappa=carrier,k0=cfg.k0,
                    epsilon=epsilon,mu=cfg.mu_r,return_operation=True)
                body+=a;operation+=b
            # Literal physical boundary integration includes the test phase,
            # modal reference phase, independent C/D sign and incident load.
            qp,qw=basix.make_quadrature(basix.CellType.quadrilateral,63)
            dt=np.zeros(4,complex);load=dt.copy();bm=np.zeros((len(modes),4),complex)
            for side,z in (('top',hi[2]),('bottom',lo[2])):
                xyz=np.column_stack((lo[:2]+qp*(hi-lo)[:2],np.full(len(qp),z)))
                v,_=lifts(xyz)
                if np.array_equal(carrier,kp):v=v*np.exp(-1j*(xyz@G))[None,:,None]
                physical_test=np.exp(1j*(xyz@carrier))[None,:,None]*v
                ww=qw*np.prod((hi-lo)[:2])
                for i,m in enumerate(modes):
                    if m.side!=side or (port[i]==0 and inc[i]==0):continue
                    tr=np.exp(1j*(xyz[:,:2]@np.array([m.alpha,m.gamma])))[:,None]*(_traction_vector(m,cfg)*_mode_boundary_phase(m,cfg))
                    overlap=np.einsum('q,qc,jqc->j',ww,tr,np.conj(physical_test))
                    bm[i]=-port[i]*overlap;dt+=bm[i];load-=inc[i]*overlap
                if side=='top':
                    ei=cfg.incident_amplitude*np.asarray(cfg.polarization_vector)
                    tr=np.exp(1j*(xyz@cfg.wavevector))[:,None]*np.cross(1j*np.cross(cfg.wavevector,ei),[0.,0.,1.])
                    load+=np.einsum('q,qc,jqc->j',ww,tr,np.conj(physical_test))
            terms.append(np.vstack((body,dt,load)));ops.append(operation+np.abs(bm).sum(axis=0)+np.abs(load))
    a=np.asarray(terms);op=np.asarray(ops);res=a[:,6]-a[:,:6].sum(axis=1)
    rel=float(np.max(np.abs(res)/np.maximum(op,1e-30)))
    # Only the combined full curl term is gauge invariant; individual cross
    # components change with the carrier and are retained separately.
    combined=np.concatenate((a[:,:4].sum(axis=1)[:,None,:],a[:,4:]),axis=1)
    diff=float(np.max(np.abs(combined[0]-combined[1])/np.maximum(op.sum(axis=0),1e-30)))
    arrays=save_arrays(folder/'continuous_flat_gauge_balance.npz',terms=a,operation_scales=op,residuals=res,
        physical_port=port,incident_projection=inc,kappa=k,kappa_prime=kp)
    return dict(arrays=arrays,physical_modes=len(modes),tests=4,body_q=31,boundary_q=63,
        maximum_operation_scaled_balance=rel,combined_gauge_operation_difference=diff,
        nonzero_port_rhs=True,no_FE_interpolation=True,no_PDE=True,pass_gate=max(rel,diff)<=1e-10)


def actual_gauge_controls(folder,journal):
    from .phase_explicit_accuracy import configuration
    from .phase_notch_hp import configured_setup
    from .fixed_phase_fem import carrier,envelope_configuration
    from .fullspace_dtn_action import build_dynamic_mode_inventory
    from .scattering_accuracy_fields import CellEvaluator,analytic
    cfg,setup,geo=configured_setup(scope.case_spec('G6'),journal,scope=scope)
    k=carrier(cfg);kp=setup['numerical_carrier'];G=kp-k
    rng=np.random.default_rng(5806);points=rng.random((12,3))*np.array([cfg.x_max-cfg.x_min,cfg.y_max-cfg.y_min,cfg.z_max-cfg.z_min])
    u=rng.normal(size=(12,3))+1j*rng.normal(size=(12,3));curl=rng.normal(size=(12,3))+1j*rng.normal(size=(12,3))
    result=gauge_identity(points,u,curl,k,G);result.pop('incident_envelope')
    env=envelope_configuration(cfg,kp);periodic=max(abs(env.floquet_phase_x-1),abs(env.floquet_phase_y-1))
    modes,ids,sha=build_dynamic_mode_inventory(cfg);original=configuration('NOTCH',6,'ORIGINAL')
    modes0,ids0,sha0=build_dynamic_mode_inventory(original)
    # ORIGINAL has a legacy 532 cutoff; compare the live physical incidence,
    # and construct the identical cutoff without changing numerical carrier.
    import dataclasses
    original=dataclasses.replace(original,diffraction_order_max_m=11,diffraction_order_max_n=4)
    modes0,ids0,sha0=build_dynamic_mode_inventory(original)
    if sha!=sha0 or len(modes)!=828:raise ValueError('gauge changed physical mode keys or waves')
    arrays=save_arrays(folder/'phase_product_rule.npz',points=points,u=u,curl=curl,kappa=k,kappa_prime=kp,G=G)
    # Continuous analytic FLAT field, transform envelope and its curl exactly.
    bg=analytic(cfg,points);up=np.exp(-1j*(points@k))[:,None]*bg['E']
    cp=np.exp(-1j*(points@k))[:,None]*bg['curl']-1j*np.cross(k,up)
    flat=gauge_identity(points,up,cp,k,G);flat.pop('incident_envelope')
    continuous=continuous_gauge_flat(cfg,modes,k,kp,folder,journal)
    cellchecks=[]
    for degree,q in ((6,15),(7,17)):
        spec=scope.case_spec('G6' if degree==6 else 'G7');c,s,_=configured_setup(spec,journal,scope=scope)
        V=s['spaces'][degree];evlow=CellEvaluator(V,q);evhigh=CellEvaluator(V,31)
        aspects=[max(np.linalg.norm(J,axis=0))/min(np.linalg.norm(J,axis=0)) for J,_,_ in evlow.geometry]
        cells=sorted(set([int(np.argmin(aspects)),int(np.argmax(aspects))]))
        coeff=rng.normal(size=(V.element.space_dimension,2))+1j*rng.normal(size=(V.element.space_dimension,2))
        for cell in cells:
            J,_,_=evlow.geometry[cell];pair=[]
            for ev in (evlow,evhigh):
                a=np.zeros_like(coeff);b=a.copy()
                for start in range(0,len(ev.points),256):
                    sl=slice(start,start+256);aa,bb=local_vectors(ev.values[sl],ev.curls[sl],coeff,J,ev.weights[sl],kp,c.k0,c.eps_grating,c.mu_r);a+=aa;b+=bb
                pair.append((a,b))
            op=float(np.linalg.norm(pair[0][0]-pair[1][0])+np.linalg.norm(pair[0][1]-pair[1][1]))/max(sum(np.linalg.norm(v) for v in pair[1]),1e-30)
            rel=relative(sum(pair[0])-sum(pair[1]),sum(pair[1]));rec=save_arrays(folder/f'gauge_p{degree}_cell{cell}.npz',coefficients=coeff,J=J,kappa_prime=kp,
                low_curl=pair[0][0],low_mass=pair[0][1],high_curl=pair[1][0],high_mass=pair[1][1])
            cellchecks.append(dict(degree=degree,cell=cell,q=q,operation_scaled=op,relative=rel,arrays=rec,pass_gate=op<=1e-12 and rel<=1e-10))
        del evlow,evhigh,s;gc.collect()
    result.update(kappa=k,kappa_prime=kp,G=G,product_rule_arrays=arrays,periodic_phase_defect=periodic,
        physical_inventory_sha=sha,mode_count=len(modes),n_env_rule='n_physical - 1; physical key unchanged',
        analytic_flat_continuous=flat,analytic_flat_balance=continuous,new_carrier_body_cells=cellchecks,
        pass_gate=max(result['E'],result['curl'],periodic,flat['E'],flat['curl'])<=1e-12 and continuous['pass_gate'] and all(x['pass_gate'] for x in cellchecks))
    write_json(folder/'gauge_controls.json',result);return result


def qualification(folder,journal):
    rows={}
    for role in ('B6','R7'):
        d=folder/role;d.mkdir();rows[role]=body_qualification(role,d,journal)
        write_json(folder/'body_progress.json',rows)
    b=scope.parent('B6')['boundary'];old=checked_arrays(b['arrays'][1]);w=checked_arrays(b['witness'])
    rec=save_arrays(folder/'old_B6_q63_reloaded.npz',**old);new=checked_arrays(rec)
    bitwise=all(np.array_equal(v,new[k]) for k,v in old.items())
    forward=packed_action(new,w['input']);adj=packed_action(new,w['input'],adjoint=True)
    fr=relative(forward-w['forward63'],w['forward63']);ar=relative(adj-w['adjoint63'],w['adjoint63'])
    scale=max(np.linalg.norm(w['forward63']),np.linalg.norm(w['adjoint63']),1e-30)
    operation=(np.linalg.norm(forward-w['forward63'])+np.linalg.norm(adj-w['adjoint63']))/scale
    reload=dict(old=b['arrays'][1],new=rec,bitwise=bitwise,forward=fr,adjoint=ar,operation_scaled=float(operation),
        pass_gate=bitwise and max(fr,ar)<=1e-10 and operation<=1e-12,no_old_boundary_reintegration=True)
    g=actual_gauge_controls(folder,journal)
    return dict(status='COMPLETED',role='P',body=rows,boundary_reader=reload,gauge=g,gauge_control_pass=g['pass_gate'],
        body_low_q_pass={str(scope.parent(k)['degree']):x['pass_gate'] for k,x in rows.items()},
        pass_gate=reload['pass_gate'] and g['pass_gate'] and all(x['pass_gate'] for x in rows.values()),new_complete_solves=0,new_factor_count=0)


def fixed_output(r,field,cfg,kappa,folder,journal):
    from .phase_saved_closure import selected_points
    from .phase_notch_hp_fields import mesh_bounds,parents_at
    from .phase_evaluation_cache import cached_evaluator_factory
    from .scattering_accuracy_fields import analytic
    pp=selected_points();ids=parents_at(mesh_bounds(field.function_space),pp,interior=False)
    ev=cached_evaluator_factory(limit_bytes=64*2**20,quadrature_tables=False)(field.function_space,23,kappa)
    values={n:np.empty((len(pp),3),complex) for n in ('E','H','curl')}
    with journal.measured('deployment_fixed_240_full_physical_fields'):
        for c in np.unique(ids):
            mask=ids==c;vv=ev.at(field,int(c),pp[mask],cfg.k0)
            for n in values:values[n][mask]=vv[n]
    bg=analytic(cfg,pp);v=dict(points=pp,parent_cells=ids,kappa=kappa)
    for n,x in values.items():v[n+'_total']=x;v[n+'_scattered']=x-bg[n]
    r['output']['fixed_240']=save_arrays(folder/'fixed_240_physical_fields.npz',**v)


def complete_deployment(r,restored,bundle,rhs,u,port,folder,journal):
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    cfg,setup,geo=restored;field=restore_p0_full_field(setup['floquets'][r['degree']],u)
    fixed_output(r,field,cfg,bundle['kappa'],folder,journal)
    qualified=scope.stage('P')['body_low_q_pass'].get(str(r['degree']),False)
    q=(15 if r['degree']==6 else 17) if qualified else 31
    values=uncondensed_vectors(field,cfg,bundle['kappa'],setup['floquets'][r['degree']].mpc,setup['mesh_data'],folder/'independent_volume',journal,q=q,
        identity=dict(parent_npz_sha256=r['arrays']['sha256'],study_local_body_qualification=qualified))
    v=checked_arrays(r['arrays']);ind=setup['boundary_provider'].bundle(63)
    (folder/'independent_original').mkdir(exist_ok=True)
    r['independent']=saved_audit(v,setup,cfg,field,values,ind,folder/'independent_original',journal)
    r['boundary_provider']=dict(folder=str(setup['boundary_provider'].folder),generated=dict(setup['boundary_provider'].generated),loads=dict(setup['boundary_provider'].loads),
        q47_production_q63_independent=True)
    r.update(numerical_carrier=bundle['kappa'],physical_carrier=__import__('src.solvers.fixed_phase_fem',fromlist=['carrier']).carrier(cfg),
        deployment_complete=r['independent']['equation_pass'] and r['independent']['recovery_pass'],
        numeric_cache='empty case-local numerical preparation, OS/JIT cache state recorded, not system-cold',
        deployment_includes=['mesh/MPC','JIT','both quadratures','reference/raw/condensation','factor/solve/refine','full recovery','E/H/curl/240','all modes/power','volume','independent original audit','provenance/required IO'],
        research_comparisons_in_this_process=False)
    write_json(folder/'completed_deployment_state.json',r);journal.event('necessary_single_deployment_outputs_completed',role=r['role'])
    return r


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V58 live memory binding')
    if role=='P':r=qualification(folder,journal)
    elif role in scope.SOLVES:r=solve_case(role,folder,journal,scope=scope)
    elif role=='S':r=saved_defect(folder,journal)
    elif role=='VERIFY_COST':
        from benchmarks.collect_phase_deployment import verify
        r=verify(folder,journal)
    else:raise ValueError('V58 explicit role')
    r.update(timings=journal.timings,calls=journal.calls,NN_training=0,target_qualified=False)
    write_json(folder/'minimum_scientific_results.json',r);return r


def saved_defect(folder,journal):
    # An explicit finite diagnostic is appended before this stage is admitted.
    from .phase_deployment_defect import consume_defect
    return consume_defect(folder,journal,scope)
