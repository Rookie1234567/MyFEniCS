"""Physical gVh evaluation and independent integrals, without DG projection."""
import numpy as np
from .scattering_accuracy_fields import CellEvaluator, analytic
from .scattering_anchor import relative, save_arrays


class PhaseEvaluator(CellEvaluator):
    def __init__(self, space, q, kappa):
        super().__init__(space,q)
        self.kappa=np.asarray(kappa,float)

    def physical(self, points, envelope, curl, k0, mu=1):
        g=np.exp(1j*(points@self.kappa))[:,None]
        ck=curl+1j*np.cross(self.kappa,envelope)
        return {'E':g*envelope,'curl':g*ck,'H':g*ck/(1j*k0*mu)}

    def cell(self,function,c,k0):
        points,w,v=super().cell(function,c,k0)
        return points,w,self.physical(points,v['E'],v['curl'],k0)

    def at(self,function,c,points,k0):
        J,o,det=self.geometry[c]
        ref=(points-o)@np.linalg.inv(J).T
        tab=self.space.element.basix_element.tabulate(1,ref)
        curls=np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)
        info=int(self.permutations[c]);dim=self.space.element.space_dimension
        if info not in self.transforms:
            T=np.eye(dim);self.space.element.T_apply(T.ravel(),self.permutations[c:c+1],dim);self.transforms[info]=T
        coef=self.transforms[info].T@function.x.array[self.space.dofmap.cell_dofs(c)]
        e=np.einsum('qjc,j->qc',tab[0],coef)@np.linalg.inv(J)
        curl=np.einsum('qjc,j->qc',curls,coef)@J.T/det
        return self.physical(points,e,curl,k0)

    def gradient_indicator(self,function,c,k0):
        """Within-cell derivatives of u and Ckappa(u)/(i*k0); no JIT."""
        import basix
        J,o,det=self.geometry[c];inv=np.linalg.inv(J)
        if not hasattr(self,'second_tabulation'):
            self.second_tabulation=self.space.element.basix_element.tabulate(2,self.points)
        tab=self.second_tabulation
        info=int(self.permutations[c]);dim=self.space.element.space_dimension
        if info not in self.transforms:
            T=np.eye(dim);self.space.element.T_apply(T.ravel(),self.permutations[c:c+1],dim);self.transforms[info]=T
        coef=self.transforms[info].T@function.x.array[self.space.dofmap.cell_dofs(c)]
        first=np.asarray([np.einsum('qjc,j->qc',tab[basix.index(*(int(i==a) for i in range(3)))],coef)@inv for a in range(3)])
        grad=np.einsum('aqc,ad->dqc',first,inv)
        second=np.empty((3,3,len(self.points),3),complex)
        for a in range(3):
            for b in range(3):
                index=basix.index(*(int(i==a)+int(i==b) for i in range(3)))
                second[a,b]=np.einsum('qjc,j->qc',tab[index],coef)@inv
        hess=np.einsum('abqc,ad,be->deqc',second,inv,inv)
        dcurl=np.stack((hess[:,1,:,2]-hess[:,2,:,1],hess[:,2,:,0]-hess[:,0,:,2],hess[:,0,:,1]-hess[:,1,:,0]),axis=-1)
        dh=(dcurl+1j*np.cross(self.kappa,grad))/(1j*k0)
        widths=np.sum(np.abs(J),axis=1)
        return widths**2*det*np.asarray([np.sum(self.weights[:,None]*(np.abs(grad[d])**2+np.abs(dh[d])**2)) for d in range(3)])


def common_physical_difference(coarse,fine,cfg,journal,folder,*,q=23):
    """Integrate on the finer geometry, evaluating both physical gVh fields."""
    from .fixed_phase_fem import carrier
    fc,ff=coarse,fine;ec=PhaseEvaluator(fc.function_space,q,carrier(cfg));ef=PhaseEvaluator(ff.function_space,q,ec.kappa)
    # Affine boxes: a point's parent is found from actual stored vertices,
    # never from a guessed native numbering or interpolated field.
    bounds=np.asarray([[fc.function_space.mesh.geometry.x[fc.function_space.mesh.geometry.dofmap[c]].min(axis=0),fc.function_space.mesh.geometry.x[fc.function_space.mesh.geometry.dofmap[c]].max(axis=0)] for c in range(len(ec.geometry))])
    sums={k:np.zeros(3) for k in ('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')};per=[];components=[];selected={k:[] for k in sums};selected_ref={k:[] for k in sums}
    with journal.measured('common_physical_p_h_integrals'):
        for c in range(len(ef.geometry)):
            points,w,vf=ef.cell(ff,c,cfg.k0);mid=points.mean(axis=0)
            parents=np.flatnonzero(np.all((mid>=bounds[:,0]-1e-12)&(mid<=bounds[:,1]+1e-12),axis=1))
            if len(parents)!=1:raise ValueError('common physical cell-parent ambiguity')
            p=int(parents[0]);vc=ec.at(fc,p,points,cfg.k0);bg=analytic(cfg,points);cell=[];parts=[]
            for name in sums:
                k=name.split('_')[0];a=vc[k];b=vf[k]
                if name.endswith('scattered'):a=a-bg[k];b=b-bg[k]
                triple=np.asarray([np.sum(w[:,None]*np.abs(b-a)**2),np.sum(w[:,None]*np.abs(b)**2),np.sum(w[:,None]*np.abs(bg[k])**2)])
                sums[name]+=triple;cell.append(triple);parts.append(np.sum(w[:,None]*np.abs(b-a)**2,axis=0))
            per.append(cell)
            components.append(parts)
            cv=ec.at(fc,p,mid[None,:],cfg.k0);fv=ef.at(ff,c,mid[None,:],cfg.k0);bv=analytic(cfg,mid[None,:])
            for name in sums:
                k=name.split('_')[0];b=bv[k][0] if name.endswith('scattered') else 0
                selected[name].append(cv[k][0]-b);selected_ref[name].append(fv[k][0]-b)
    rows={k:dict(difference_L2=float(np.sqrt(v[0])),reference_L2=float(np.sqrt(v[1])),relative=float(np.sqrt(v[0])/max(np.sqrt(v[1]),1e-12)),incident_scaled=float(np.sqrt(v[0])/max(np.sqrt(v[2]),1e-12))) for k,v in sums.items()}
    select={k:relative(np.asarray(selected[k])-selected_ref[k],selected_ref[k]) for k in sums}
    witness={}
    for k in sums:
        witness['selected_'+k+'_coarse']=np.asarray(selected[k]);witness['selected_'+k+'_fine']=np.asarray(selected_ref[k])
    arrays=save_arrays(folder/f'common_physical_difference_q{q}.npz',per_cell_integrals=np.asarray(per),per_cell_component_error_squared=np.asarray(components),**witness)
    return dict(fields=rows,selected=select,arrays=arrays,q=q,full_cross_terms=True,pass_gate=max([r['relative'] for r in rows.values()]+list(select.values()))<=1e-4)


def physical_output(bundle,u,port,geometry,folder,journal):
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from .dtn_port_3d import _port_power_metrics,_write_port_outputs
    from src.common.modes_3d import incident_power_3d
    from src.postprocessing.rta_3d import compute_volume_absorption_3d
    cfg=bundle['cfg'];env=restore_p0_full_field(bundle['setup']['floquets'][bundle['degree']],u)
    ev=PhaseEvaluator(env.function_space,23,bundle['kappa'])
    with journal.measured('physical_E_H_curl_evaluation'):
        selected={k:[] for k in ('E','H','curl')}
        for c,point in enumerate(geometry['cell_centers']):
            v=ev.at(env,c,point[None,:],cfg.k0)
            for k in selected:selected[k].append(v[k][0])
        points=geometry['cell_centers'];bg=analytic(cfg,points)
        vals={'envelope_native_full':env.x.array.copy(),'kappa':bundle['kappa'],'selected_points':points}
        for k in selected:
            vals['selected_'+k+'_total']=np.asarray(selected[k])
            vals['selected_'+k+'_scattered']=np.asarray(selected[k])-bg[k]
        fields=save_arrays(folder/'fields.npz',**vals)
    with journal.measured('all532_power_and_volume_absorption'):
        pm=_port_power_metrics(cfg,list(bundle['modes']),port,list(bundle['incident_projections']))
        _write_port_outputs(folder,cfg,list(bundle['modes']),port,list(bundle['incident_projections']),pm,bundle['setup']['mesh'].comm)
        # |g|=1: this is exactly |physical E|^2, no polynomial projection.
        vm=compute_volume_absorption_3d(bundle['setup']['mesh_data'],cfg,env,folder,incident_power=incident_power_3d(cfg),port_metrics=pm)
    return dict(fields=fields,port_metrics=pm,volume_metrics=vm,mode_manifest_sha256=bundle['mode_sha256'],
        full_field_representation='authoritative full native envelope + original geometry/space/MPC + kappa; E=g*u and curl=g*(curlu+i*kappa cross u)',
        sampled_fields_are_not_authority=True,background='same analytic layered physical background',
        H_units='curl(E)/(i*k0*mu) code; physical H=Hcode/eta0',surface_quadrature_degree=bundle['dtn_quadrature_degree'])


def flat_integrals(bundle,u,geometry,folder,journal):
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    cfg=bundle['cfg'];env=restore_p0_full_field(bundle['setup']['floquets'][bundle['degree']],u)
    results=[]
    for q in (23,31):
        ev=PhaseEvaluator(env.function_space,q,bundle['kappa']);sums=np.zeros((3,2));per=[]
        with journal.measured(f'analytic_physical_integrals_q{q}'):
            for c in range(len(geometry['cell_centers'])):
                points,w,v=ev.cell(env,c,cfg.k0);known=analytic(cfg,points)
                pair=np.asarray([[np.sum(w[:,None]*np.abs(v[k]-known[k])**2),np.sum(w[:,None]*np.abs(known[k])**2)] for k in ('E','H','curl')],float)
                sums+=pair;per.append(pair)
        results.append(sums)
    fields={k:dict(difference_squared=float(v[0]),reference_squared=float(v[1]),relative=float(np.sqrt(v[0]/v[1]))) for k,v in zip(('E','H','curl'),results[-1],strict=True)}
    # Near-zero differences use total-field operation scale; not subtractive relative noise.
    qdef=float(np.max(np.abs(results[0]-results[1])/np.maximum(results[1][:,1,None],1e-30)))
    arrays=save_arrays(folder/'analytic_integrals.npz',per_cell_squared=np.asarray(per),q23=results[0],q31=results[1])
    return dict(fields=fields,arrays=arrays,q_pair=[23,31],quadrature_operation_scaled=qdef,
                pass_gate=all(v['relative']<=1e-4 for v in fields.values()) and qdef<=1e-10)


def analytic_weak(bundle,journal,q=31):
    """Independent analytic E tested against g*phi, both curls transformed."""
    from .target_boundary_witness import dual_maps
    from .scattering_accuracy_analytic import flat_modal_reference
    cfg=bundle['cfg'];V=bundle['setup']['spaces'][bundle['degree']];mpc=bundle['setup']['floquets'][bundle['degree']].mpc
    ev=CellEvaluator(V,q);maps=dual_maps(V,mpc);kappa=bundle['kappa']
    result=np.zeros(V.dofmap.index_map.size_local,complex)
    eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
    with journal.measured(f'independent_analytic_gVh_weak_q{q}'):
        for c,tag in zip(bundle['setup']['mesh_data'].cell_tags.indices,bundle['setup']['mesh_data'].cell_tags.values,strict=True):
            J,o,det=ev.geometry[c];points=ev.points@J.T+o;known=analytic(cfg,points)
            phase=np.exp(-1j*(points@kappa))[:,None]
            E=known['E']*phase;curl=known['curl']*phase
            basis=ev.values@np.linalg.inv(J)
            ck=ev.curls@J.T/det+1j*np.cross(kappa,basis)
            local=det*np.einsum('q,qc,qjc->j',ev.weights,curl/cfg.mu_r,np.conj(ck))-det*cfg.k0**2*eps[int(tag)]*np.einsum('q,qc,qjc->j',ev.weights,E,basis)
            local=np.ascontiguousarray(local,complex);V.element.T_apply(local.view(float),ev.permutations[c:c+1],2)
            for value,row in zip(local,V.dofmap.cell_dofs(c),strict=True):
                masters,coeff=maps[int(row)];np.add.at(result,masters,coeff*value)
    ref=flat_modal_reference(cfg,bundle['modes']);coupling=np.zeros_like(result)
    for e,a in zip(bundle['dtn_action'].carrier.entries,ref['port'],strict=True):np.add.at(coupling,e.coupling_rows,e.coupling_values*a)
    return result,coupling,ref
