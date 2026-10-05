"""Post-freeze physical verification on the complete native FE problem.

Rebuilds no inverse: an independent original uncondensed form action plus all
DtN functionals audits the frozen coefficients. L2 differences are actual FE
volume integrals, with full vector cross terms, not coefficient norm proxies.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from .scattering_anchor_scope import stage


def checked_arrays(record):
    from .scattering_anchor import array_hash
    p=Path(record['path'])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('frozen NPZ whole-file identity')
    with np.load(p,allow_pickle=False) as saved:
        if set(saved.files)!=set(record['members']):raise ValueError('frozen NPZ exact member inventory')
        values={}
        for name,meta in record['members'].items():
            a=saved[name]
            if list(a.shape)!=meta['shape'] or str(a.dtype)!=meta['dtype'] or array_hash(a)!=meta['sha256']:raise ValueError('frozen scientific member identity '+name)
            values[name]=a
    return values


def complete_finite_gate(row):
    """Recompute the frozen finite criteria; recorded status is not evidence."""
    field_names={'E_total','E_scattered','H_total','H_scattered','scaled_curl_total','scaled_curl_scattered'}
    selected_names={'selected_E_total','selected_E_scattered','selected_H_total','selected_H_scattered','selected_curl_total','selected_curl_scattered'}
    mode_names={'auxiliary_amplitude_total_projection_relative','outgoing_amplitude_relative','outgoing_amplitude_at_boundary_relative'}
    if set(row['fields'])!=field_names or set(row['selected'])!=selected_names:
        raise ValueError('complete E/H/curl observable inventory')
    if row['all_modes']['mode_count']!=532 or not mode_names.issubset(row['all_modes']):
        raise ValueError('complete532 complex mode inventory')
    if set(row['power_differences'])!={'R_total','T_total','A_balance','A_volume'}:
        raise ValueError('complete power inventory')
    def audit(a,threshold):
        return all(np.isfinite(a[k]) and 0<=a[k]<=threshold for k in ('true','native','augmented','port')) and np.isfinite(a['identity']) and 0<=a['identity']<=1e-10 and a['slave_zero'] is True
    def recovery(r):
        return all(np.isfinite(r[k]) and 0<=r[k]<=1e-10 for k in ('operation_scaled_interior','max_cell_operation_scaled','master_storage_max_abs')) and r['slave_storage_zero'] is True
    field_values=[v['mixed_relative'] for v in row['fields'].values()]+list(row['selected'].values())+[row['all_modes'][k] for k in mode_names]
    fields=all(np.isfinite(v) and 0<=v<=1e-4 for v in field_values)
    power=all(np.isfinite(v) and 0<=v<=1e-5 for v in row['power_differences'].values())
    modes=np.isfinite(row['all_modes']['mode_power_max_absolute']) and 0<=row['all_modes']['mode_power_max_absolute']<=1e-6
    energies=all(np.isfinite(row[k]) and 0<=row[k]<=1e-5 for k in ('reference_energy_absolute','candidate_energy_absolute'))
    ref=audit(row['reference_audit'],1e-10) and recovery(row['reference_recovery'])
    equation=audit(row['candidate_audit'],1e-6);recovered=recovery(row['candidate_recovery'])
    return {'reference_direct_and_recovery_pass':bool(ref),'candidate_equation_pass':bool(equation),
            'candidate_recovery_pass':bool(recovered),'field_and_full_complex_vector_pass':bool(fields),
            'power_mode_energy_pass':bool(power and modes and energies),
            'FINITE_OBSERVABLE_PASS':bool(ref and equation and recovered and fields and power and modes and energies),
            'comparison':'original frozen relative complete observable-vector norms, floor1e-12, no phase/normalization adjustment'}


def integrated_difference(mesh,reference,candidate,k0):
    from dolfinx import fem
    import ufl
    dx=ufl.Measure('dx',domain=mesh,metadata={'quadrature_degree':12})
    # For the same p4, degree12 integrates the complete polynomial products.
    # The one p5 comparison uses the same fixed degree12, not a q scan.
    result={}
    for name,r,c in [('E_total',reference,candidate),('scaled_curl_total',ufl.curl(reference)/k0,ufl.curl(candidate)/k0),
                     ('H_total',ufl.curl(reference)/(1j*k0),ufl.curl(candidate)/(1j*k0))]:
        den=max(float(np.real(fem.assemble_scalar(fem.form(ufl.inner(r,r)*dx)))),0)
        num=max(float(np.real(fem.assemble_scalar(fem.form(ufl.inner(c-r,c-r)*dx)))),0)
        result[name]={'reference_L2':den**.5,'difference_L2':num**.5,'mixed_relative':num**.5/max(den**.5,1e-12)}
    return result


def native_recovery_check(bundle,u,rhs,port,vectors):
    """Independent cell equations with operation scale, no extra factor solve."""
    from dolfinx import fem
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from .hcurl_assembly_time_condensation import _cell_integral_kernels,_tabulate_raw_tensor_class,_orient_cell_tensor
    V=bundle['setup']['spaces'][bundle['degree']];mesh=V.mesh
    E=restore_p0_full_field(bundle['setup']['floquets'][bundle['degree']],u)
    slaves=np.asarray(bundle['setup']['floquets'][bundle['degree']].mpc.slaves)
    independent=np.setdiff1d(np.arange(len(u.array)),slaves)
    master_defect=float(np.max(np.abs(E.x.array[independent]-u.array[independent]),initial=0))
    compiled=fem.form(bundle['volume_action'].bilinear_form)
    kernels=_cell_integral_kernels(compiled,sum_duplicate_cell_integrals=True)
    mesh.topology.create_entity_permutations();infos=mesh.topology.get_cell_permutation_info()
    ip=np.asarray(V.element.basix_element.entity_dofs[3][0]);tp=np.setdiff1d(np.arange(V.element.space_dimension),ip)
    tags=dict(zip(bundle['setup']['mesh_data'].cell_tags.indices,bundle['setup']['mesh_data'].cell_tags.values))
    rows=[]
    for cell in range(mesh.topology.index_map(3).size_local):
        dofs=V.dofmap.cell_dofs(cell);coords=np.ascontiguousarray(mesh.geometry.x[mesh.geometry.dofmap[cell]])
        tensor=_tabulate_raw_tensor_class(compiled,kernels,coords,tag=int(tags[cell]),dimension=V.element.space_dimension)
        _orient_cell_tensor(V.element,tensor,infos[cell:cell+1])
        vi=tensor[np.ix_(ip,ip)]@E.x.array[dofs[ip]];vt=tensor[np.ix_(ip,tp)]@E.x.array[dofs[tp]]
        f=rhs.array[dofs[ip]];ba=vectors['coupling_action'][dofs[ip]]
        residual=f-vi-vt-ba;scale=sum(np.linalg.norm(x) for x in (f,vi,vt,ba))
        rows.append((float(np.linalg.norm(residual)),float(scale)))
    res=np.array(rows)
    defect=float(np.linalg.norm(res[:,0])/max(np.linalg.norm(res[:,1]),1e-30))
    maximum=float(np.max(res[:,0]/np.maximum(res[:,1],1e-30)))
    return E,{'operation_scaled_interior':defect,'max_cell_operation_scaled':maximum,
              'master_storage_max_abs':master_defect,'slave_storage_zero':bool(np.all(u.array[slaves]==0)),
              'basis':'original uncondensed oriented native cell tensor; no inverse/condensed residual reused'}


def mode_comparison(reference,candidate):
    from .scattering_anchor import relative
    rr=json.loads(Path(reference['output']['fields']['path']).with_name('port_power.json').read_text())
    cc=json.loads(Path(candidate['output']['fields']['path']).with_name('port_power.json').read_text())
    a,b=rr['orders'],cc['orders']
    if len(a)!=532 or len(b)!=532:raise ValueError('complete532 mode power inventory')
    keys=lambda x:(x['auxiliary_index'],x['side'],x['m'],x['n'],x['polarization'])
    if [keys(x) for x in a]!=[keys(x) for x in b]:raise ValueError('original mode key/order/polarization mismatch')
    if rr['reference_planes']!=cc['reference_planes']:raise ValueError('original reference planes differ')
    arrays={}
    for name in ('auxiliary_amplitude_total_projection','outgoing_amplitude','outgoing_amplitude_at_boundary'):
        ar=np.array([complex(*x[name]) for x in a]);ac=np.array([complex(*x[name]) for x in b])
        arrays[name+'_relative']=relative(ac-ar,ar)
        arrays[name+'_max_absolute']=float(np.max(np.abs(ac-ar)))
    arrays['mode_power_max_absolute']=float(np.max(np.abs(np.array([x['power_ratio'] for x in b])-np.array([x['power_ratio'] for x in a]))))
    arrays['mode_count']=532
    return arrays


def native_recovery_action_split_check(bundle,u,rhs,port,vectors,journal):
    """Independent original volume action on private interior/trace parts.

    Interior DOFs belong to one cell. The two original form actions provide
    the same Vii*ui and Vit*ut without constructing a dense tensor merely to
    multiply it by one vector. The earlier tensor oracle remains unchanged.
    """
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    V=bundle['setup']['spaces'][bundle['degree']];mesh=V.mesh
    ip=np.asarray(V.element.basix_element.entity_dofs[3][0])
    bycell=[V.dofmap.cell_dofs(c)[ip] for c in range(mesh.topology.index_map(3).size_local)]
    interior=np.concatenate(bycell)
    if len(np.unique(interior))!=len(interior):raise ValueError('interior rows are not one-cell-owned')
    ui=u.duplicate();ut=u.copy()
    try:
        ui.set(0);ui.array[interior]=u.array[interior];ut.array[interior]=0
        vi=bundle['volume_action'].apply(ui).array.copy()
        vt=bundle['volume_action'].apply(ut).array.copy()
        journal.calls['volume_only']=journal.calls.get('volume_only',0)+2
    finally:ui.destroy();ut.destroy()
    ba=vectors['coupling_action'];residual=rhs.array-vi-vt-ba
    rows=np.array([(np.linalg.norm(residual[d]),sum(np.linalg.norm(v[d]) for v in (rhs.array,vi,vt,ba))) for d in bycell])
    identity=np.linalg.norm(vi+vt-vectors['volume_action'])/max(np.linalg.norm(vi)+np.linalg.norm(vt),1e-30)
    E=restore_p0_full_field(bundle['setup']['floquets'][bundle['degree']],u)
    slaves=np.asarray(bundle['setup']['floquets'][bundle['degree']].mpc.slaves)
    independent=np.setdiff1d(np.arange(len(u.array)),slaves)
    facts={'operation_scaled_interior':float(np.linalg.norm(rows[:,0])/max(np.linalg.norm(rows[:,1]),1e-30)),
           'max_cell_operation_scaled':float(np.max(rows[:,0]/np.maximum(rows[:,1],1e-30))),
           'master_storage_max_abs':float(np.max(np.abs(E.x.array[independent]-u.array[independent]),initial=0)),
           'slave_storage_zero':bool(np.all(u.array[slaves]==0)),
           'split_action_identity_operation_scale':float(identity),
           'internal_rhs_norm':float(np.linalg.norm(rhs.array[interior])),
           'basis':'independent original uncondensed UFL volume action, private interior/trace split; no factor or condensed action'}
    if identity>1e-10 or not all(np.isfinite(v) for v in facts.values() if isinstance(v,(float,int))):
        raise ValueError('original split volume identity is not trusted')
    return E,facts,{'interior_only_volume_action':vi,'trace_only_volume_action':vt,'interior_rows':interior}


def verify(folder,journal):
    from petsc4py import PETSc
    from dolfinx import fem
    from .scattering_anchor import (make_setup,build_bundle,audit_original,save_arrays,relative)
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    from .common_3d_fields import stage4_layered_background_field
    rows=[]
    for case in ('REGULAR','NOTCH'):
        ref=stage('REFERENCE_'+case)
        try:candidate=stage('ENGINE_'+case)
        except FileNotFoundError:candidate=None
        cfg,setup,geometry=make_setup(case,4,journal);bundle,rhs,_=build_bundle(cfg,setup,journal)
        states={};functions={};audits={};recoveries={}
        try:
            for label,record in [('REFERENCE',ref),('CANDIDATE',candidate)]:
                if record is None:continue
                values=checked_arrays(record['arrays'])
                for key in ('geometry_x','geometry_dofmap','cell_centers','cell_tags'):
                    if not np.array_equal(values[key],geometry[key]):raise ValueError('live geometry/material/ordering identity '+key)
                if relative(values['rhs']-rhs.array,rhs.array)>1e-13:raise ValueError('same physical background/RHS changed')
                u=PETSc.Vec().createSeq(len(values['u_storage']),comm=PETSc.COMM_SELF);u.array[:]=values['u_storage']
                try:
                    norms,vec=audit_original(bundle,rhs,u,values['port'],journal)
                    E,recovery=native_recovery_check(bundle,u,rhs,values['port'],vec)
                finally:u.destroy()
                functions[label]=E;states[label]=values;audits[label]=norms;recoveries[label]=recovery
                save_arrays(folder/f'{case}_{label}_independent_audit.npz',**vec)
            baseline=ref['output'];energy=baseline['volume_metrics']['energy_closure_error_port_volume']
            row={'case':case,'reference_audit':audits['REFERENCE'],'reference_recovery':recoveries['REFERENCE'],
                 'reference_energy_absolute':abs(energy),'reference_energy_pass':abs(energy)<=1e-5,
                 'reference_equation_pass':max(audits['REFERENCE'][k] for k in ('true','native','augmented','port'))<=1e-6,
                 'reference_direct_internal_target_pass':max(audits['REFERENCE'][k] for k in ('true','augmented','port'))<=1e-10}
            if candidate is not None:
                with journal.measured(case+'_same_discrete_physical_integrals'):
                    fields=integrated_difference(setup['mesh'],functions['REFERENCE'],functions['CANDIDATE'],cfg.k0)
                    bg=stage4_layered_background_field(functions['REFERENCE'].function_space,cfg)
                    esr=fem.Function(bg.function_space);esc=fem.Function(bg.function_space)
                    esr.x.array[:]=functions['REFERENCE'].x.array-bg.x.array;esc.x.array[:]=functions['CANDIDATE'].x.array-bg.x.array
                    fields.update({k.replace('total','scattered'):v for k,v in integrated_difference(setup['mesh'],esr,esc,cfg.k0).items()})
                rf=checked_arrays(ref['output']['fields']);cf=checked_arrays(candidate['output']['fields'])
                if not np.array_equal(rf['selected_points'],cf['selected_points']):raise ValueError('fixed selected physical points')
                selected={k:float(np.linalg.norm(cf[k]-rf[k])/max(np.linalg.norm(rf[k]),1e-12)) for k in rf if k.startswith('selected_') and k!='selected_points'}
                modes=mode_comparison(ref,candidate)
                power={k:abs(candidate['output']['port_metrics'][k]-baseline['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
                power['A_volume']=abs(candidate['output']['volume_metrics']['A_volume_total']-baseline['volume_metrics']['A_volume_total'])
                energy_c=abs(candidate['output']['volume_metrics']['energy_closure_error_port_volume'])
                equation=max(audits['CANDIDATE'][k] for k in ('true','native','augmented','port'))<=1e-6
                recovery=max(recoveries['CANDIDATE'][k] for k in ('operation_scaled_interior','max_cell_operation_scaled','master_storage_max_abs'))<=1e-10 and recoveries['CANDIDATE']['slave_storage_zero'] and audits['CANDIDATE']['identity']<=1e-10
                field_pass=max([v['mixed_relative'] for v in fields.values()]+list(selected.values())+[modes[k] for k in modes if k.endswith('_relative')])<=1e-4
                physics=equation and recovery and field_pass and max(power.values())<=1e-5 and modes['mode_power_max_absolute']<=1e-6 and energy_c<=1e-5
                row.update(candidate_audit=audits['CANDIDATE'],candidate_recovery=recoveries['CANDIDATE'],
                           fields=fields,selected=selected,all_modes=modes,power_differences=power,candidate_energy_absolute=energy_c,
                           equation_pass=equation,recovery_pass=recovery,same_discrete_field_pass=field_pass,FINITE_OBSERVABLE_PASS=physics)
            else:row.update(candidate_status='ADAPTER_BLOCKED_OR_NOT_RUN',FINITE_OBSERVABLE_PASS=False)
            rows.append(row)
            journal.event('independent_case_verified',case=case,observable=row['FINITE_OBSERVABLE_PASS'])
        finally:rhs.destroy();destroy_same_mesh_physical_action(bundle)
    return {'status':'COMPLETED','pairs':rows,'reference_read_after_candidates_frozen':True,
            'physical_integral_q':12,'comparison_floor':1e-12,'no_phase_or_conservation_adjustment':True,
            'TARGET_NOT_QUALIFIED':True,'NN_NOT_TRAINED_THIS_BATCH':True,'timings':journal.timings,'calls':journal.calls}
