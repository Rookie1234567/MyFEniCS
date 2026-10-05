"""Fixed analytic controls and polynomial representation bounds, no solve.

Modal projection is checked by direct physical-face Gauss integration at the
boundary, avoiding evanescent exponential rescaling. Polynomial lower bounds
allow arbitrary coefficients on each cell, so also apply to the smaller
conforming/MPC space. They are not estimates from a PDE reference field.
"""
import numpy as np


def incident_projection_witness(cfg,modes,q):
    """All532, direct integration; return amplitudes at each reference face."""
    nodes,weights=np.polynomial.legendre.leggauss((q+2)//2)
    nodes=(nodes+1)/2;weights=weights/2
    ids=[i for i,m in enumerate(modes) if m.side=='top']
    e=np.asarray([modes[i].e_vector[:2] for i in ids])
    wave=np.asarray([[modes[i].alpha,modes[i].gamma] for i in ids])
    values=np.zeros(len(modes),np.complex128)
    s=complex(cfg.incident_amplitude)*np.asarray(cfg.polarization_vector[:2])
    overlap=np.conj(e)@s
    for xa,xb in zip(cfg.mesh_axis_x_values[:-1],cfg.mesh_axis_x_values[1:]):
        for ya,yb in zip(cfg.mesh_axis_y_values[:-1],cfg.mesh_axis_y_values[1:]):
            x=xa+(xb-xa)*nodes;y=ya+(yb-ya)*nodes
            px=np.exp(1j*(cfg.kx-wave[:,0,None])*x[None,:])@weights
            py=np.exp(1j*(cfg.ky-wave[:,1,None])*y[None,:])@weights
            values[ids]+=(xb-xa)*(yb-ya)*px*py*overlap
    area=(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)
    values[ids]*=np.exp(1j*cfg.kz*cfg.physical_z_max)/(area*np.sum(np.abs(e)**2,axis=1))
    return values


def flat_modal_reference(cfg,modes):
    """Analytic s-polarized flat interface, at original z=0 convention."""
    from src.common.analytic_fields_3d import fresnel_reference
    from .dtn_port_3d import _incident_projection_onto_top_mode,_mode_boundary_phase
    if cfg.polarization_kind.lower()!='s' or len(modes)!=532:
        raise ValueError('fixed analytic s/532 inventory')
    f=fresnel_reference(cfg);port=np.zeros(532,np.complex128)
    incident=np.asarray([_incident_projection_onto_top_mode(m,cfg) for m in modes])
    for i,m in enumerate(modes):
        if (m.m,m.n,m.polarization)==(0,0,'s'):
            port[i]=complex(cfg.incident_amplitude)*(f['r'] if m.side=='top' else f['t'])
    port+=incident
    phase=np.asarray([_mode_boundary_phase(m,cfg) for m in modes])
    outgoing=port-incident
    beta=next(m.beta for m in modes if (m.side,m.m,m.n,m.polarization)==('bottom',0,0,'s'))
    R=float(f['R']);T=float(f['T']*np.exp(2*beta.imag*cfg.physical_z_min))
    return dict(port=port,incident=incident,phase=phase,outgoing=outgoing,
                R=R,T=T,A_volume=1-R-T,Fresnel=f)


def flat_saved_physics(cfg,modes,port,output,analytic_result):
    """Check every saved complex field and mode, no adjustment or calibration."""
    from .scattering_anchor_checks import checked_arrays
    from .scattering_accuracy_fields import analytic
    from .scattering_anchor import relative
    from .dtn_port_3d import _mode_power_at_boundary
    from src.common.modes_3d import incident_power_3d
    f=checked_arrays(output['fields']);ref=flat_modal_reference(cfg,modes)
    points=f['selected_points'];known=analytic(cfg,points)
    fields={k:relative(f['selected_'+{'E':'E_total','H':'H_total','curl':'curl_total'}[k]]-known[k],known[k])
            for k in ('E','H','curl')}
    inc_boundary=ref['incident']*ref['phase']
    inc47=incident_projection_witness(cfg,modes,47);inc63=incident_projection_witness(cfg,modes,63)
    projection=dict(q47_q63_max_absolute=float(np.max(np.abs(inc47-inc63))),
        q47_analytic_max_absolute=float(np.max(np.abs(inc47-inc_boundary))),
        q63_analytic_max_absolute=float(np.max(np.abs(inc63-inc_boundary))),
        fixed_incident_amplitude_scale=abs(cfg.incident_amplitude))
    projection['pass_gate']=max(projection[k] for k in projection if k.endswith('absolute'))<=1e-11*abs(cfg.incident_amplitude)
    delta=(np.asarray(port)-ref['port'])*ref['phase']
    nonzero=np.asarray([(m.m,m.n,m.polarization)!=(0,0,'s') for m in modes])
    power=np.asarray([_mode_power_at_boundary(m,cfg,complex(a))/incident_power_3d(cfg)
        for m,a in zip(modes,np.asarray(port)-ref['incident'],strict=True)])
    ref_power=np.zeros(532)
    for i,m in enumerate(modes):
        if (m.m,m.n,m.polarization)==(0,0,'s'):ref_power[i]=ref['R'] if m.side=='top' else ref['T']
    pm=output['port_metrics'];vm=output['volume_metrics']
    av=float(vm['A_volume_total'])
    difference={k:abs(float(pm[k])-ref[r]) for k,r in (('R_total','R'),('T_total','T'),('A_balance','A_volume'))}
    difference['A_volume']=abs(av-ref['A_volume'])
    difference['maximum_single_mode_power']=float(np.max(np.abs(power-ref_power)))
    difference['energy']=abs(float(pm['R_total'])+float(pm['T_total'])+av-1)
    volume=(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*(cfg.physical_z_max-cfg.physical_z_min)
    zero_scattered={k:float(np.sqrt(analytic_result['fields'][k]['difference_squared'])/
        (abs(cfg.incident_amplitude)*np.sqrt(volume)*(cfg.k0 if k=='curl' else 1))) for k in ('E','H','curl')}
    passed=(projection['pass_gate'] and all(v<=1e-4 for v in fields.values()) and
        all(v<=1e-4 for v in zero_scattered.values()) and float(np.max(np.abs(delta[nonzero]),initial=0))<=1e-4 and
        all(difference[k]<=1e-5 for k in ('R_total','T_total','A_balance','A_volume','energy')) and
        difference['maximum_single_mode_power']<=1e-6)
    return dict(pass_gate=passed,selected_fields_relative=fields,
        all532_complex_boundary_error=delta,all532_reference_port=ref['port'],all532_reference_power=ref_power,
        all532_power=power,inc47=inc47,inc63=inc63,analytic_incident_boundary=inc_boundary,
        incident_projection=projection,expected={k:ref[k] for k in ('R','T','A_volume')},
        absolute_power_differences=difference,
        nonzero_orders_max_absolute_boundary_error=float(np.max(np.abs(delta[nonzero]),initial=0)),
        zero_scattered_L2_incident_scale=zero_scattered,
        fixed_zero_rule='amplitude1, Hcode1, scaledcurl1, physical domain volume, incident power; no near-zero denominator',
        source='analytic passive Fresnel solution at original finite reference planes; no fitted phase or normalization')


def polynomial_phase_lower_bounds(cfg):
    """One-dimensional exact Legendre projection lower bound for four spaces."""
    from scipy.special import spherical_jn
    from .scattering_accuracy_fields import analytic
    q,w=np.polynomial.legendre.leggauss(24);points=[];weights=[]
    for a,b in zip(cfg.mesh_axis_z_values[:-1],cfg.mesh_axis_z_values[1:]):
        points.extend(np.column_stack((np.zeros(len(q)),np.zeros(len(q)),a+(b-a)*(q+1)/2)))
        weights.extend(w*(b-a)/2)
    a=analytic(cfg,np.asarray(points));weights=np.asarray(weights)
    Hz_fraction=float(np.sum(weights*np.abs(a['H'][:,2])**2)/np.sum(weights[:,None]*np.abs(a['H'])**2))
    sx,sy=map(abs,cfg.s_polarization_vector[:2]);rows=[]
    for grid in ('ORIGINAL','X2'):
        widths=np.diff(cfg.mesh_axis_x_values)
        if grid=='X2':widths=np.repeat(widths/2,2)
        b=abs(cfg.kx)*widths/2
        for p in (5,6):
            # The first omitted non-negative squared Legendre coefficient alone
            # is a lower bound, rather than a subtractive 1-sum approximation.
            low_p=(2*p+3)*spherical_jn(p+1,b)**2
            low_pm1=(2*p+1)*spherical_jn(p,b)**2
            E2=float(np.dot(widths,sx*sx*low_pm1+sy*sy*low_p)/sum(widths))
            H2=float(Hz_fraction*np.dot(widths,low_pm1)/sum(widths))
            rows.append(dict(grid=grid,degree=p,E_relative_lower_bound=np.sqrt(E2)*(1-1e-10),
                H_curl_relative_lower_bound=np.sqrt(H2)*(1-1e-10),Hz_squared_fraction=Hz_fraction,
                minimum_assumptions='broken cell coefficients unrestricted; Ey x degree<=p, Ex/curlz x degree<=p-1; known real Bloch phase',
                gate=1e-4,not_a_PDE_result=True))
    return dict(rows=rows,formula='first omitted (2l+1)*spherical_jn(l,kx*h/2)^2; weighted by physical x lengths and known component norms',
        interpretation='cannot remove this error merely by better coefficients, more solver steps, or a same-space neural decoder',
        new_FE_objects=0,new_A_calls=0)


def analytic_weak_witness(bundle,journal,*,q=31):
    """Integrate the exact analytic field against all real native FE tests.

    This does not project the analytic field into the FE space first. It tests
    the weak volume sign, literal orientations/Floquet dual, and original DtN
    conventions independently of solving an interpolated analytic problem.
    No form is compiled at this new quadrature degree.
    """
    from .scattering_accuracy_fields import CellEvaluator,analytic
    from .target_boundary_witness import dual_maps
    cfg=bundle['cfg'];V=bundle['setup']['spaces'][bundle['degree']]
    mpc=bundle['setup']['floquets'][bundle['degree']].mpc
    ev=CellEvaluator(V,q);maps=dual_maps(V,mpc)
    result=np.zeros(V.dofmap.index_map.size_local,np.complex128)
    tags=bundle['setup']['mesh_data'].cell_tags
    eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
    with journal.measured('independent_analytic_full_volume_weak_integral'):
        for cell,tag in zip(tags.indices,tags.values,strict=True):
            J,origin,det=ev.geometry[cell]
            points=ev.points@J.T+origin;known=analytic(cfg,points)
            # Contract the analytic vector with each physical test basis before
            # allocating physical QxDOFx3 tables on every cell.
            local=(np.einsum('q,qc,qjc->j',ev.weights,known['curl']@J/cfg.mu_r,ev.curls)
                   -cfg.k0**2*eps[int(tag)]*det*np.einsum('q,qc,qjc->j',ev.weights,known['E']@np.linalg.inv(J).T,ev.values))
            local=np.ascontiguousarray(local,np.complex128)
            V.element.T_apply(local.view(np.float64),ev.permutations[cell:cell+1],2)
            for value,row in zip(local,V.dofmap.cell_dofs(cell),strict=True):
                masters,coef=maps[int(row)];np.add.at(result,masters,coef*value)
    ref=flat_modal_reference(cfg,bundle['modes']);coupling=np.zeros_like(result)
    for entry,a in zip(bundle['dtn_action'].carrier.entries,ref['port'],strict=True):
        np.add.at(coupling,entry.coupling_rows,entry.coupling_values*a)
    return result,coupling,ref


def flat_interface_witness(bundle,output):
    """Two-sided actual saved polynomial fields; analytic tangential signs."""
    from dolfinx import fem
    from basix.ufl import element
    from .scattering_anchor_checks import checked_arrays
    from src.common.analytic_fields_3d import _fresnel_components
    cfg=bundle['cfg'];mesh=bundle['setup']['mesh'];p=bundle['degree']
    data=checked_arrays(output['fields'])
    # The original output stores an exact DG-p polynomial representation of
    # total E/H/curl. This environment consumes that saved representation.
    V=fem.functionspace(mesh,element('DG',mesh.basix_cell(),p,shape=(3,)))
    centers=data['selected_points'];lower=np.flatnonzero(centers[:,2]<0)
    above=np.flatnonzero(centers[:,2]>0);upper=[];points=[]
    for c in lower:
        choices=[i for i in above if np.allclose(centers[i,:2],centers[c,:2],rtol=0,atol=1e-14)]
        if not choices:raise ValueError('FLAT interface face pairing')
        upper.append(min(choices,key=lambda i:centers[i,2]));points.append([*centers[c,:2],0.])
    points=np.asarray(points);upper=np.asarray(upper,np.int32);lower=lower.astype(np.int32)
    actual={}
    for k in ('E','H','curl'):
        f=fem.Function(V);f.x.array[:]=data[{'E':'E_total','H':'H_total','curl':'curl_total'}[k]]
        actual[k]=float(np.linalg.norm(f.eval(points,upper)[:,:2]-f.eval(points,lower)[:,:2])/
            (abs(cfg.incident_amplitude)*np.sqrt(len(points))*(cfg.k0 if k=='curl' else 1)))
    ki,kr,kt,ei,er,et=_fresnel_components(cfg)
    htop=(np.cross(ki,ei)+np.cross(kr,er))/(cfg.k0*cfg.mu_r)
    hbottom=np.cross(kt,et)/(cfg.k0*cfg.mu_r)
    analytic_defect=dict(E=float(np.linalg.norm((ei+er-et)[:2])/abs(cfg.incident_amplitude)),
        H=float(np.linalg.norm((htop-hbottom)[:2])/abs(cfg.incident_amplitude)),
        dispersion=max(float(abs(np.dot(k,k)-(cfg.k0*n)**2)/(cfg.k0**2*abs(n)**2))
            for k,n in ((ki,cfg.n_air),(kr,cfg.n_air),(kt,cfg.substrate_index))))
    return dict(actual_tangential_incident_scaled_jump=actual,analytic_defect=analytic_defect,
        analytic_conventions_pass=max(analytic_defect.values())<=1e-10,
        face_count=len(points),physical_z=0.,normal_component_excluded=True,
        actual_field_jump_role='diagnostic at fixed face centers; full analytic field error controls physical accuracy')
