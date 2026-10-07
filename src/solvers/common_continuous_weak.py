"""Continuous, non-FE-interpolated Maxwell test functions and weak balances.

The same analytic functions and fixed background scale are used for every
saved field. Boundary lifts have exact Fourier integrals over the full period.
"""
import itertools
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays

PARTS=('curl','phase_trial','phase_test','phase_square','mass','DtN','load')


def design(geometry,kappa):
    ax=geometry['axes_nm']; x,y,z=[ax[a] for a in ('x','y','z')]
    # All support ends are existing physical boundaries, before any field read.
    boxes=[[[x[1],x[3]],[y[1],y[3]],[z[1],z[4]]],
        [[x[1],x[3]],[y[1],y[3]],[z[2],z[3]]],
        [[x[1],x[3]],[y[1],y[3]],[z[0],z[2]]]]
    funcs=[]
    for j,box in enumerate(boxes):
        for a in range(4):funcs.append(dict(kind='window',window=j,box=box,component=a,
            frequency=[2*np.pi/(x[-1]-x[0]),0.,0.],gradient=a==3))
    for m,n in ((0,0),(1,0),(0,1)):
        for a in (0,1):
            for side in ('top','bottom'):funcs.append(dict(kind='lift',mode=[m,n],component=a,side=side))
    return dict(functions=funcs,kappa=list(kappa),geometry=geometry,
        scale='k0^2*(1+max(abs(epsilon))+abs(1/mu))*background positive scaled Hcurl norm * test positive scaled Hcurl norm',
        no_saved_field_in_design=True,no_FE_interpolation=True,q_degrees=[23,31],maximum_recheck_q=39,
        analytic_perturbation={'function_index':0,'amplitude':0.001,'zero_boundary_trace':True})


def tests(points,definition):
    p=np.asarray(points);k=np.asarray(definition['kappa']);geo=definition['geometry']; ax=geo['axes_nm']
    vs=[];cs=[]
    for f in definition['functions']:
        if f['kind']=='window':
            box=np.asarray(f['box']);h=box[:,1]-box[:,0];t=(p-box[:,0])/h
            b=t*t*(1-t)**2;db=2*t*(1-t)*(1-2*t)/h
            inside=np.all((t>0)&(t<1),axis=1);b[~inside]=0;db[~inside]=0
            phi=np.prod(b,axis=1).astype(complex);grad=np.column_stack([db[:,a]*np.prod(b[:,[j for j in range(3) if j!=a]],axis=1) for a in range(3)]).astype(complex)
            freq=np.asarray(f['frequency']);phase=np.exp(1j*(p@freq));grad=phase[:,None]*(grad+1j*phi[:,None]*freq);phi*=phase
            if f['gradient']:
                v=grad+1j*phi[:,None]*k;cv=-1j*np.cross(k,v) # Ckappa v=0 analytically
            else:
                unit=np.eye(3)[f['component']];v=phi[:,None]*unit;cv=np.cross(grad,unit)
        else:
            m,n=f['mode'];freq=np.array([2*np.pi*m/(ax['x'][-1]-ax['x'][0]),2*np.pi*n/(ax['y'][-1]-ax['y'][0]),0.])
            dz=ax['z'][-1]-ax['z'][0];lift=(p[:,2]-ax['z'][0])/dz
            sign=1 if f['side']=='top' else -1
            if sign<0:lift=1-lift
            phase=np.exp(1j*(p@freq));phi=lift*phase
            grad=1j*phi[:,None]*freq;grad[:,2]=sign*phase/dz
            unit=np.eye(3)[f['component']];v=phi[:,None]*unit;cv=np.cross(grad,unit)
        vs.append(v);cs.append(cv)
    return np.asarray(vs),np.asarray(cs)


def volume_parts(physical,points,weights,v,cv,*,kappa,k0,epsilon,mu,return_operation=False):
    g=np.exp(1j*(points@kappa))[:,None];u=physical['E']/g
    cu=physical['curl']/g-1j*np.cross(kappa,u);pu=1j*np.cross(kappa,u);pv=1j*np.cross(kappa,v)
    def pair(a,b):return np.einsum('q,qc,jqc->j',weights,a,np.conj(b),optimize=True)
    terms=np.asarray([pair(cu,cv)/mu,pair(pu,cv)/mu,pair(cu,pv)/mu,
        pair(pu,pv)/mu,-k0*k0*epsilon*pair(u,v)])
    if not return_operation:return terms
    def bound(a,b):return np.einsum('q,qc,jqc->j',weights,np.abs(a),np.abs(b),optimize=True)
    operation=(bound(cu,cv)+bound(pu,cv)+bound(cu,pv)+bound(pu,pv))/abs(mu)+k0*k0*abs(epsilon)*bound(u,v)
    return terms,operation


def boundary_parts(cfg,modes,port,definition):
    from .dtn_port_3d import _traction_vector,_incident_projection_onto_top_mode,_mode_boundary_phase
    area=(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)
    by_mode=np.zeros((len(modes),len(definition['functions'])),complex);load=np.zeros(by_mode.shape[1],complex)
    inc_e=cfg.incident_amplitude*np.asarray(cfg.polarization_vector)
    traction=np.cross(1j*np.cross(cfg.wavevector,inc_e),[0.,0.,1.])
    for j,f in enumerate(definition['functions']):
        if f['kind']=='lift' and f['side']=='top' and f['mode']==[0,0]:
            load[j]+=area*traction[f['component']]*np.exp(1j*cfg.kz*cfg.physical_z_max)
    for i,(m,alpha) in enumerate(zip(modes,port,strict=True)):
        tr=_traction_vector(m,cfg)*_mode_boundary_phase(m,cfg)
        inc=_incident_projection_onto_top_mode(m,cfg)
        for j,f in enumerate(definition['functions']):
            if f['kind']=='lift' and f['side']==m.side and f['mode']==[m.m,m.n]:
                term=area*tr[f['component']];by_mode[i,j]=-term*alpha;load[j]-=term*inc
    return by_mode.sum(axis=0),load,by_mode


def common_layout(space,definition):
    from .phase_notch_hp_fields import mesh_bounds,parents_at
    p=definition['geometry']['axes_nm'];ordered={};bounds=mesh_bounds(space)
    for a,f in zip(('x','y','z'),(2,1,4),strict=True):
        # Include actual cell cuts: the Y6 witness may not cross its new faces.
        # The functions and their frozen physical support remain unchanged.
        i=('x','y','z').index(a)
        ordered[a]=sorted(set(p[a])|{l+(r-l)*j/f for l,r in zip(p[a][:-1],p[a][1:]) for j in range(f)}|set(bounds[:,:,i].ravel()))
    intervals=[list(zip(ordered[a][:-1],ordered[a][1:])) for a in ('x','y','z')]
    boxes=np.asarray([np.asarray(t).T for t in itertools.product(*intervals)])
    return boxes,parents_at(bounds,boxes.mean(axis=1))


def evaluate(record,restored,definition,folder,journal,*,scope,qs=(23,31),analytic_control=False,frozen_scales=None):
    import basix
    from .phase_evaluation_cache import cached_evaluator_factory
    from .phase_explicit_accuracy_fields import analytic
    from .fixed_phase_fem import carrier
    from .fullspace_dtn_action import build_dynamic_mode_inventory
    from src.common.analytic_fields_3d import fresnel_reference
    cfg,setup,geo,field=restored;degree=record['degree'];kappa=carrier(cfg)
    modes,_,mode_sha=build_dynamic_mode_inventory(cfg)
    if len(modes)!=828 or mode_sha!=record['mode_sha256']:raise ValueError('continuous witness full mode identity')
    boxes,parents=common_layout(field.function_space,definition);tags=setup['mesh_data'].cell_tags.values
    nf=len(definition['functions']);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    evfactory=cached_evaluator_factory(limit_bytes=256*2**20,quadrature_tables=False)
    ev=evfactory(field.function_space,15,kappa)
    port=np.asarray(__import__('src.solvers.scattering_anchor_checks',fromlist=['checked_arrays']).checked_arrays(record['arrays'])['port'])
    if analytic_control:
        f=fresnel_reference(cfg);port=np.zeros(828,complex)
        from .dtn_port_3d import _incident_projection_onto_top_mode
        for i,m in enumerate(modes):
            if (m.m,m.n,m.polarization)==(0,0,'s'):port[i]=cfg.incident_amplitude*(f['r'] if m.side=='top' else f['t'])
            port[i]+=_incident_projection_onto_top_mode(m,cfg)
    dt,load,permode=boundary_parts(cfg,modes,port,definition);rows=[];qs=list(qs)
    for q in qs:
        points,w=basix.make_quadrature(basix.CellType.hexahedron,q);sums=np.zeros((5,nf),complex);regions={};bg2=0.;v2=np.zeros(nf)
        operation_volume=np.zeros(nf);perturbation=np.zeros_like(sums)
        with journal.measured(('analytic_flat_control' if analytic_control else record['role'])+'_common_continuous_q'+str(q)):
            for bi,(box,c) in enumerate(zip(boxes,parents,strict=True)):
                xyz=box[0]+points*(box[1]-box[0]);weights=w*np.prod(box[1]-box[0]);v,cv=tests(xyz,definition)
                known=analytic(cfg,xyz);value=known if analytic_control else ev.at(field,int(c),xyz,cfg.k0)
                tag=int(tags[c]);eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}[tag]
                if analytic_control:eps=cfg.eps_substrate if box.mean(axis=0)[2]<0 else cfg.eps_air
                chunk,op=volume_parts(value,xyz,weights,v,cv,kappa=kappa,k0=cfg.k0,epsilon=eps,mu=cfg.mu_r,return_operation=True)
                operation_volume+=op
                if analytic_control:
                    pd=definition['analytic_perturbation'];j=pd['function_index'];amp=pd['amplitude'];g=np.exp(1j*(xyz@kappa))[:,None]
                    delta={'E':amp*g*v[j],'curl':amp*g*(cv[j]+1j*np.cross(kappa,v[j]))}
                    perturbation+=volume_parts(delta,xyz,weights,v,cv,kappa=kappa,k0=cfg.k0,epsilon=eps,mu=cfg.mu_r)
                sums+=chunk;regions.setdefault(str(tag),np.zeros_like(sums));regions[str(tag)]+=chunk
                bg2+=float(np.sum(weights[:,None]*(np.abs(known['E'])**2+np.abs(known['curl']/cfg.k0)**2)))
                v2+=np.einsum('q,jqc->j',weights,np.abs(v)**2+np.abs((cv+1j*np.cross(kappa,v))/cfg.k0)**2)
                if bi%64==0:journal.event('continuous_weak_box',state=record['role'],q=q,box=bi,boxes=len(boxes))
        scale=cfg.k0**2*(1+max(abs(cfg.eps_air),abs(cfg.eps_grating),abs(cfg.eps_substrate))+abs(1/cfg.mu_r))*np.sqrt(bg2*v2)
        scale_match=None
        if frozen_scales is not None and q in frozen_scales:
            frozen=np.asarray(frozen_scales[q]);scale_match=float(np.linalg.norm(scale-frozen)/np.linalg.norm(frozen))
            if frozen.shape!=(nf,) or scale_match>1e-10:raise ValueError('frozen background scale / geometry integration mismatch')
            scale=frozen
        terms=np.vstack((sums,dt,load));res=load-dt-sums.sum(axis=0)
        operation=operation_volume+np.abs(permode).sum(axis=0)+np.abs(load)
        arrays=save_arrays(folder/f'q{q}.npz',terms=terms,residual=res,absolute=np.abs(res),fixed_scale=scale,
            fixed_scaled=np.abs(res)/scale,operation_scale=operation,permode_DtN=permode,
            region_tag=np.asarray(list(regions),dtype='S16'),region_terms=np.asarray(list(regions.values())),boxes=boxes,
            perturbation_terms=perturbation,perturbation_residual=res-perturbation.sum(axis=0))
        row=dict(q=q,arrays=arrays,maximum_fixed_scaled=float(np.max(np.abs(res)/scale)),
            maximum_operation_scaled=float(np.max(np.abs(res)/np.maximum(operation,1e-300))),
            no_FE_interpolation=True,complex_parts=list(PARTS),regions='actual material tags; flat control uses layered epsilon',
            operation_scale='absolute component products integrated before assembly/cancellation + absolute mode and load contributions',
            frozen_background_scale_relative=scale_match)
        if analytic_control:
            row['analytic_control_pass']=bool(np.max(np.abs(res)/scale)<=1e-10)
            row['nonzero_perturbation_defect']=float(np.max(np.abs(perturbation.sum(axis=0))))
            row['nonzero_perturbation_detected']=bool(row['nonzero_perturbation_defect']>1e-10*np.max(scale))
        rows.append(row);write_json(folder/'progress.json',dict(rows=rows,definition=definition,parent=record['arrays']['sha256']))
        if len(rows)>=2:
            from .scattering_anchor_checks import checked_arrays
            prev=checked_arrays(rows[-2]['arrays']);delta=np.abs(terms-prev['terms']).sum(axis=0)/np.maximum(operation+prev['operation_scale'],1e-300)
            row['quadrature_max_operation_difference']=float(delta.max());row['quadrature_pass']=bool(delta.max()<=1e-10)
            if not row['quadrature_pass'] and q==31:qs.append(39)
        write_json(folder/'progress.json',dict(rows=rows,definition=definition,parent=record['arrays']['sha256']))
    return dict(status='COMPLETED',rows=rows,mode_sha256=mode_sha,field_parent=record['arrays']['sha256'],
        quadrature_pass=rows[-1].get('quadrature_pass',len(rows)==1),analytic_control=analytic_control,
        analytic_control_pass=rows[-1].get('analytic_control_pass'),nonzero_perturbation_detected=rows[-1].get('nonzero_perturbation_detected'),
        no_matrix_factor_solve=True,cache=evfactory.cache.record(),eval_checks=ev.eval_checks)
