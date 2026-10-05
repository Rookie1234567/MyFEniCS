"""Fixed-phase complete Full3D finite authorities and physical accuracy.

Uses the existing condensation/direct/original uncondensed audit chain.
No learning, modal reduction, old numeric cache, or target-scale object.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import gc
import json
import numpy as np
from src.runners.task042_shared import write_json, _json_metadata
from .phase_explicit_accuracy_scope import plan_record,stage,window,SOLVES,ARTIFACT
from .scattering_anchor import Journal,condense,DirectFactor,audit_original,save_arrays,relative
from .scattering_anchor_checks import checked_arrays,native_recovery_action_split_check
from .fixed_phase_fem import carrier,envelope_configuration,port_coordinate_scales


def configuration(case,degree=4,grid='ORIGINAL'):
    from .scattering_accuracy import configuration as parent
    cfg=parent(case,min(degree,6),'ORIGINAL')
    axes={a:list(v) for a,v in plan_record()['physical_descriptor']['geometry']['axes_nm'].items()}
    if grid!='ORIGINAL':
        a=grid[0].lower();factor=int(grid[1:]);v=axes[a]
        axes[a]=[x for l,r in zip(v[:-1],v[1:]) for x in np.linspace(l,r,factor+1)[:-1]]+[v[-1]]
    cfg=replace(cfg,case_name=f'task042_v51_{case.lower()}_{grid.lower()}_p{degree}',nedelec_degree=degree,visualization_degree=degree,
        mesh_axis_x_values=tuple(axes['x']),mesh_axis_y_values=tuple(axes['y']),mesh_axis_z_values=tuple(axes['z']),
        mesh_axis_cell_counts=tuple(len(axes[a])-1 for a in ('x','y','z')),
        mesh_plan_id='task042.v51.fixed',mesh_axis_z_profile='task042.v51.fixed')
    cfg.stage4_dtn_quadrature_degree=47
    return cfg


def make_setup(case,degree,grid,journal,phase=True):
    from mpi4py import MPI
    from dolfinx import mesh as dxmesh,fem,default_real_type
    from basix.ufl import element
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh,_mark_boundary_facets,_mark_cells
    from src.constraints.floquet_3d import build_double_floquet_mpc
    cfg=configuration(case,degree,grid);k=carrier(cfg,phase)
    with journal.measured('mesh_materials_envelope_MPC'):
        mesh=_structured_hexa_mesh(MPI.COMM_SELF,cfg.mesh_axis_x_values,cfg.mesh_axis_y_values,cfg.mesh_axis_z_values,preserve_input_partition=cfg.stage4_preserve_structured_input_partition)
        facets,_=_mark_boundary_facets(mesh,cfg);tags=_mark_cells(mesh,cfg)
        centers=dxmesh.compute_midpoints(mesh,3,tags.indices);regular=tags.values.copy();values=regular.copy()
        if case=='FLAT':values[centers[:,2]>0]=cfg.tags.air
        else:
            box=np.asarray(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
            hit=np.all((centers>=box[:,0])&(centers<=box[:,1]),axis=1)&(regular==cfg.tags.grating)
            expected=2 if grid=='ORIGINAL' else 2*int(grid[1:])
            if int(hit.sum())!=expected:raise ValueError('genuine notch geometry/cell inventory')
            values[hit]=cfg.tags.air
        tags=dxmesh.meshtags(mesh,3,tags.indices,values)
        V=fem.functionspace(mesh,element('N1curl',mesh.basix_cell(),degree,dtype=default_real_type))
        data=SimpleNamespace(mesh=mesh,cell_tags=tags,facet_tags=facets)
        floquet=build_double_floquet_mpc(V,data,envelope_configuration(cfg,k))
    return cfg,dict(mesh=mesh,mesh_data=data,spaces={degree:V},floquets={degree:floquet}),dict(cell_centers=centers,cell_tags=values,regular_tags=regular,geometry_x=mesh.geometry.x.copy(),geometry_dofmap=mesh.geometry.dofmap.copy())


def build_bundle(cfg,setup,journal,q=47,phase=True):
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .scattering_accuracy_boundary import SurfaceComponents
    from petsc4py import PETSc
    k=carrier(cfg,phase);holder={}
    def surface(V,data,cfg,oldq,*,jit_options):
        src=SurfaceComponents(V,setup['floquets'][cfg.nedelec_degree].mpc,cfg,q,method='separable' if q==47 else 'basix2d',phase_carrier=k)
        holder['source']=src
        return src.assemblers()
    with journal.measured('JIT_full_Ckappa_and_complete532_carrier'):
        bundle=build_same_mesh_physical_action(setup,cfg,cfg.nedelec_degree,surface_assembler_factory=surface,retain_all_surface_entries=True,phase_carrier=k)
    bundle.update(kappa=k,dtn_quadrature_degree=q)
    with journal.measured('physical_incident_RHS'):
        base=PETSc.Vec().createSeq(setup['spaces'][cfg.nedelec_degree].dofmap.index_map.size_local,comm=PETSc.COMM_SELF);base.array[:]=holder['source'].incident_traction();rhs=base.duplicate()
        try:bundle['physical_action'].compose_physical_rhs(base,bundle['incident_projections'],rhs)
        finally:base.destroy()
    bundle['boundary_cost']=dict(seconds=holder['source'].seconds,q=q,method=holder['source'].method,unique_modes=holder['source'].calls)
    return bundle,rhs


def boundary_check(cfg,setup,folder,journal):
    from .scattering_accuracy_boundary import SurfaceComponents,carrier_pair,pack_carrier
    from .fullspace_dtn_action import build_dynamic_mode_inventory,build_fullspace_dtn_carrier_from_surface,FullspaceDtnAction
    from petsc4py import PETSc
    V=setup['spaces'][cfg.nedelec_degree];mpc=setup['floquets'][cfg.nedelec_degree].mpc;k=carrier(cfg)
    modes,ids,digest=build_dynamic_mode_inventory(cfg);objects=[];sources=[]
    for q,method in ((47,'separable'),(63,'basix2d')):
        with journal.measured(f'new_phase_all532_q{q}'):
            s=SurfaceComponents(V,mpc,cfg,q,method=method,phase_carrier=k)
            objects.append(build_fullspace_dtn_carrier_from_surface(modes,s.assemblers(),mpc,cfg,retain_all_nonzero=True));sources.append(s)
    pair=carrier_pair(*objects,ids);rng=np.random.default_rng(51047);x=PETSc.Vec().createSeq(V.dofmap.index_map.size_local,comm=PETSc.COMM_SELF)
    x.array[:]=rng.normal(size=x.getSize())+1j*rng.normal(size=x.getSize());x.array[mpc.slaves]=0
    values=[]
    for c in objects:
        action=FullspaceDtnAction(c,comm=V.mesh.comm);y=x.duplicate();action.apply(x,y);forward=y.array.copy();adj=np.zeros(x.getSize(),complex)
        for e in c.entries:np.add.at(adj,e.projection_rows,np.conj(e.projection_values)*np.vdot(e.coupling_values,x.array[e.coupling_rows])/np.conj(e.normalization_h))
        values.append((forward,adj));action.destroy();y.destroy()
    forward=relative(values[0][0]-values[1][0],values[1][0]);adjoint=relative(values[0][1]-values[1][1],values[1][1]);inc=[s.incident_traction() for s in sources]
    incident=relative(inc[0]-inc[1],inc[1]);witness=save_arrays(folder/'boundary_action_pair.npz',input=x.array.copy(),forward47=values[0][0],forward63=values[1][0],adjoint47=values[0][1],adjoint63=values[1][1],incident47=inc[0],incident63=inc[1]);x.destroy()
    receipts=[save_arrays(folder/f'phase_p{cfg.nedelec_degree}_q{q}_all532.npz',**pack_carrier(c)) for q,c in zip((47,63),objects)]
    r=dict(pair=pair,forward=forward,adjoint=adjoint,incident=incident,arrays=receipts,witness=witness,mode_sha256=digest,degree=cfg.nedelec_degree,
           costs=[s.seconds for s in sources],pass_gate=pair['pass'] and max(forward,adjoint)<=1e-10 and incident<=1e-11)
    write_json(folder/'boundary_check.json',r);journal.calls['A']+=2;journal.calls['AH']+=2
    return r


class CoordinateFactor:
    """Exact diagonal port change wrapped around the existing direct backend."""
    def __init__(self,matrix,bundle,nt,journal,folder):
        from .dtn_port_3d import _mode_boundary_phase
        self.left,self.right=port_coordinate_scales(nt,[e.normalization_h for e in bundle['dtn_action'].carrier.entries],[_mode_boundary_phase(m,bundle['cfg']) for m in bundle['modes']])
        self.mapping=save_arrays(folder/'port_coordinate_map.npz',left=self.left,right=self.right)
        scaled=matrix.copy();lv=matrix.createVecLeft();rv=matrix.createVecRight();lv.array[:]=self.left;rv.array[:]=self.right;scaled.diagonalScale(lv,rv)
        try:self.factor=DirectFactor(scaled,journal)
        finally:scaled.destroy();lv.destroy();rv.destroy()

    def solve_repeated(self,rhs,target):
        v=rhs.copy();v.array[:]*=self.left
        try:self.factor.solve_repeated(v,target);target.array[:]*=self.right
        finally:v.destroy()

    def destroy(self):self.factor.destroy()


def equation_gate(a,r):
    return all(a[k]<=1e-6 for k in ('true','native','augmented','port')) and a['identity']<=1e-10 and a['slave_zero'] and all(r[k]<=1e-10 for k in ('operation_scaled_interior','max_cell_operation_scaled','master_storage_max_abs','split_action_identity_operation_scale')) and r['slave_storage_zero']


def solve(role,folder,journal):
    from .scattering_accuracy import capacity,volume_form_identity
    from .phase_explicit_accuracy_fields import physical_output,flat_integrals,analytic_weak
    from .scattering_accuracy_analytic import flat_saved_physics
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V51 queue frozen')
    resume=window.TMP/(role+'_post_resume.json')
    if resume.exists():
        import hashlib
        identity=journal.source_state.get('postprocessing_resume')
        if identity is None or identity['sha256']!=hashlib.sha256(resume.read_bytes()).hexdigest():
            raise ValueError('postprocessing resume must be bound to resolved/live manifest')
        return resume_returned_state(role,folder,journal,json.loads(resume.read_text()))
    if role=='FLAT_P5' and stage('FLAT_P4').get('accuracy_pass'):return dict(status='NOT_RUN_F4_ACCURATE')
    if role.startswith('NOTCH') and not any((ARTIFACT/(x+'.json')).exists() and stage(x).get('accuracy_pass') for x in ('FLAT_P4','FLAT_P5')):
        return dict(status='NOT_RUN_FLAT_ACCURACY_GATE')
    case='NOTCH' if role.startswith('NOTCH') else 'FLAT';degree=5 if role in ('FLAT_P5','NOTCH_P5','NOTCH_HPROBE') else 4;grid='ORIGINAL'
    if role=='NOTCH_HPROBE':grid=json.loads((window.TMP/'h_selection.json').read_text())['grid']
    cfg,setup,geo=make_setup(case,degree,grid,journal);cap=capacity(setup,cfg,journal)
    if not cap['admitted']:return dict(status='NOT_RUN_CAPACITY_GATE',capacity=cap)
    bundle=rhs=inverse=system=u=factor=None
    try:
        boundary=stage('SETUP')['boundary'] if degree==4 and grid=='ORIGINAL' else boundary_check(cfg,setup,folder,journal)
        if not boundary['pass_gate']:return dict(status='NOT_RUN_NEW_BOUNDARY_GATE',boundary=boundary)
        bundle,rhs=build_bundle(cfg,setup,journal);write_json(folder/'actual_volume_form_identity.json',volume_form_identity(bundle))
        system,inverse=condense(bundle,journal)
        write_json(folder/'build_audit.json',system.build_audit)
        factor=CoordinateFactor(system.matrix,bundle,system.active_rows,journal,folder);inverse.factor=factor
        with journal.measured('solve_and_affine_internal_recovery'):
            u=inverse.apply(rhs);port=inverse.last_port_solution.copy()
        early=save_arrays(folder/'returned_solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],slaves=np.asarray(setup['floquets'][degree].mpc.slaves),**geo)
        write_json(folder/'minimal_scientific_state.json',dict(status='AUDIT_PENDING',role=role,case=case,degree=degree,grid=grid,source=journal.source_state,arrays=early,capacity=cap,mode_sha256=bundle['mode_sha256']))
        journal.event('returned_complete_envelope_saved',sha256=early['sha256'])
        norms,vectors=audit_original(bundle,rhs,u,port,journal);refinements=[]
        for _ in range(2):
            if max(norms[k] for k in ('true','augmented','port'))<=1e-10:break
            d=rhs.duplicate();d.array[:]=vectors['residual']
            with journal.measured('fixed_refinement'):
                delta=inverse.apply(d);u.axpy(1,delta);port+=inverse.last_port_solution
            delta.destroy();d.destroy();norms,vectors=audit_original(bundle,rhs,u,port,journal);refinements.append(norms)
        arrays=save_arrays(folder/'solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],slaves=np.asarray(setup['floquets'][degree].mpc.slaves),**geo,**vectors)
        inverse.factor=None;factor.destroy();factor=None;system.matrix.destroy();system.matrix=None;gc.collect();journal.event('factor_and_global_matrix_released_original_oracle_alive')
        _,recovery,rv=native_recovery_action_split_check(bundle,u,rhs,port,vectors,journal);rec=save_arrays(folder/'recovery.npz',**rv)
        output=physical_output(bundle,u,port,geo,folder,journal)
        accuracy=None;weak=None;pair=None;indicator=None
        if case=='FLAT':
            accuracy=flat_integrals(bundle,u,geo,folder,journal)
            full=flat_saved_physics(cfg,bundle['modes'],port,output,accuracy)
            fa={k:full.pop(k) for k in list(full) if isinstance(full[k],np.ndarray)};full['arrays']=save_arrays(folder/'analytic_modes.npz',**fa)
            accuracy['complete_physics']=full;accuracy['pass_gate']=accuracy['pass_gate'] and full['pass_gate']
            vv,cc,_=analytic_weak(bundle,journal)
            weak=dict(relative=relative(rhs.array-vv-cc,rhs.array),arrays=save_arrays(folder/'independent_analytic_weak.npz',volume=vv,coupling=cc,rhs=rhs.array.copy()))
            accuracy['pass_gate']=accuracy['pass_gate'] and weak['relative']<=1e-10
        if role=='NOTCH_P5':
            pair=compare_saved(stage('NOTCH_P4'),dict(case=case,degree=degree,grid=grid,arrays=arrays,output=output),folder,journal)
            from .phase_explicit_accuracy_fields import PhaseEvaluator
            from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
            env=restore_p0_full_field(setup['floquets'][degree],u);ev=PhaseEvaluator(env.function_space,15,bundle['kappa'])
            with journal.measured('pre_registered_direction_h_indicator'):
                per=np.asarray([ev.gradient_indicator(env,c,cfg.k0) for c in range(len(geo['cell_centers']))])
            total=per.sum(axis=0);axis=int(np.argmax(total));indicator=dict(totals=total,selected_axis=('x','y','z')[axis],grid=('X2','Y2','Z2')[axis],
                rule='sum h_K,d^2 integral(|partial_d u|^2+|partial_d Henv|^2), code units; first argmax gives x/y/z tie order',arrays=save_arrays(folder/'h_indicator.npz',per_cell=per,totals=total))
            if not pair['pass_gate'] and equation_gate(norms,recovery) and stage('NOTCH_P4')['equation_pass']:
                write_json(window.TMP/'h_selection.json',indicator|dict(parent_array_sha256=arrays['sha256']))
        eq=equation_gate(norms,recovery)
        result=dict(status='COMPLETED',role=role,case=case,degree=degree,grid=grid,representation='FIXED_PHASE_PERIODIC_NEDELEC_ENVELOPE',
            arrays=arrays,returned_arrays=early,original_audit=norms,recovery=recovery,recovery_arrays=rec,output=output,analytic=accuracy,analytic_weak=weak,
            accuracy_pass=eq and accuracy is not None and accuracy['pass_gate'],equation_pass=eq,direct_target_pass=max(norms[k] for k in ('true','augmented','port'))<=1e-10,
            p_pair=pair,h_indicator=indicator,
            capacity=cap,build_audit=_json_metadata(system.build_audit),port_coordinates=factor.mapping if factor is not None else str(folder/'port_coordinate_map.npz'),
            boundary=boundary,mode_sha256=bundle['mode_sha256'],fixed_refinements=refinements,timings=journal.timings,calls=journal.calls,NN_training=0)
        write_json(folder/'scientific_result.json',result)
        return result
    finally:
        if factor is not None:factor.destroy()
        if u is not None:u.destroy()
        if rhs is not None:rhs.destroy()
        if inverse is not None:inverse.destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)


def setup_stage(folder,journal):
    from .scattering_anchor import small_condensation_witness
    cfg,setup,geo=make_setup('FLAT',4,'ORIGINAL',journal)
    b=boundary_check(cfg,setup,folder,journal);k=carrier(cfg)
    physical=[cfg.floquet_phase_x,cfg.floquet_phase_y]
    reconstructed=[np.exp(1j*k[0]*(cfg.x_max-cfg.x_min)),np.exp(1j*k[1]*(cfg.y_max-cfg.y_min))]
    phase_error=max(abs(a-b) for a,b in zip(physical,reconstructed,strict=True))
    return dict(status='COMPLETED',boundary=b,kappa=k,phase_identity_error=phase_error,affine_nonzero_internal_port=small_condensation_witness(),
        geometry=save_arrays(folder/'geometry.npz',**geo),pass_gate=b['pass_gate'] and phase_error<=1e-10,timings=journal.timings,calls=journal.calls)


def execute(role,folder,state):
    journal=Journal(folder,window_scope=window,planning_limit_bytes=16*2**30);journal.source_state=state
    if role=='SETUP':return setup_stage(folder,journal)
    if role in SOLVES:
        if role=='ORDINARY_CONTROL':raise RuntimeError('ordinary fallback requires pre-registered representation/capacity selection')
        return solve(role,folder,journal)
    if role=='VERIFY_COST':return verify_cost(folder,journal)
    raise ValueError('V51 stage inventory')


def verify_cost(folder,journal):
    """One independent post-freeze action, no factor and no reference fitting."""
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    frozen=json.loads((window.TMP/'scientific_queue_frozen.json').read_text());rows=[]
    for role,item in frozen['completed_solves'].items():
        pointer=json.loads((ARTIFACT/(role+'.json')).read_text())
        if pointer!=item['pointer']:raise ValueError('frozen solve pointer changed')
        r=stage(role);v=checked_arrays(r['arrays']);cfg,setup,geo=make_setup(r['case'],r['degree'],r['grid'],journal)
        for key in ('cell_centers','cell_tags','geometry_x','geometry_dofmap'):
            if not np.array_equal(geo[key],v[key]):raise ValueError('frozen geometry identity '+key)
        bundle,rhs=build_bundle(cfg,setup,journal,q=63);u=rhs.duplicate();u.array[:]=v['u_storage']
        try:
            a,vec=audit_original(bundle,rhs,u,v['port'],journal);_,rec,rv=native_recovery_action_split_check(bundle,u,rhs,v['port'],vec,journal)
            receipt=save_arrays(folder/(role+'_independent_audit.npz'),**vec,**rv)
            rows.append(dict(role=role,parent=r['arrays']['sha256'],audit=a,recovery=rec,arrays=receipt,equation_pass=equation_gate(a,rec),analytic_pass=r['accuracy_pass'],power=r['output']['port_metrics'],volume=r['output']['volume_metrics']))
        finally:u.destroy();rhs.destroy();destroy_same_mesh_physical_action(bundle)
    pairs=[]
    if 'NOTCH_P4' in frozen['completed_solves'] and 'NOTCH_P5' in frozen['completed_solves']:
        sub=folder/'NOTCH_p_pair';sub.mkdir();pairs.append(dict(kind='p4_p5',comparison=compare_saved(stage('NOTCH_P4'),stage('NOTCH_P5'),sub,journal)))
    if 'NOTCH_HPROBE' in frozen['completed_solves']:
        sub=folder/'NOTCH_h_pair';sub.mkdir();pairs.append(dict(kind='p5_h',comparison=compare_saved(stage('NOTCH_P5'),stage('NOTCH_HPROBE'),sub,journal)))
    return dict(status='COMPLETED',rows=rows,pairs=pairs,NN_training=0,target_qualified=False,NN20=False,timings=journal.timings,calls=journal.calls)


def compare_saved(coarse,fine,folder,journal):
    from .phase_explicit_accuracy_fields import common_physical_difference
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from .scattering_anchor_checks import mode_comparison
    from petsc4py import PETSc
    functions=[]
    for r in (coarse,fine):
        cfg,setup,geo=make_setup(r['case'],r['degree'],r['grid'],journal);v=checked_arrays(r['arrays'])
        for key in ('geometry_x','geometry_dofmap','cell_tags','cell_centers'):
            if not np.array_equal(geo[key],v[key]):raise ValueError('physical comparison geometry '+key)
        vec=PETSc.Vec().createSeq(len(v['u_storage']),comm=PETSc.COMM_SELF);vec.array[:]=v['u_storage']
        try:functions.append(restore_p0_full_field(setup['floquets'][r['degree']],vec))
        finally:vec.destroy()
    low=common_physical_difference(*functions,cfg,journal,folder,q=23)
    result=common_physical_difference(*functions,cfg,journal,folder,q=31)
    # All integral differences are scaled by physical reference energy.
    # This retains nearly-zero differences without dividing by roundoff.
    qdef=max(abs(low['fields'][k][n]**2-result['fields'][k][n]**2)/max(result['fields'][k]['reference_L2']**2,1e-24) for k in result['fields'] for n in ('reference_L2','difference_L2'))
    result.update(quadrature_pair=[23,31],quadrature_operation_scaled=qdef,q23_arrays=low['arrays'])
    result['pass_gate']=result['pass_gate'] and qdef<=1e-10
    modes=mode_comparison(coarse,fine)
    power={k:abs(coarse['output']['port_metrics'][k]-fine['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(coarse['output']['volume_metrics']['A_volume_total']-fine['output']['volume_metrics']['A_volume_total'])
    energies=[abs(r['output']['volume_metrics']['energy_closure_error_port_volume']) for r in (coarse,fine)]
    result.update(modes=modes,power_differences=power,energies=energies)
    result['pass_gate']=result['pass_gate'] and all(modes[k]<=1e-4 for k in modes if k.endswith('_relative')) and modes['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energies)<=1e-5
    return result


def resume_returned_state(role,folder,journal,record):
    """Re-audit/recover an already returned physical vector; no new solve."""
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    from .phase_explicit_accuracy_fields import physical_output,PhaseEvaluator
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    import hashlib
    old=Path(record['old_artifact']).resolve()
    if not old.is_relative_to(ARTIFACT) or record['role']!=role:
        raise ValueError('postprocessing resume stage/path')
    for p,sha in record['saved_file_hashes'].items():
        if hashlib.sha256((old/p).read_bytes()).hexdigest()!=sha:raise ValueError('returned state altered '+p)
    v=checked_arrays(record['arrays']);cfg,setup,geo=make_setup(record['case'],record['degree'],record['grid'],journal)
    for key in geo:
        if not np.array_equal(geo[key],v[key]):raise ValueError('resume actual geometry/material '+key)
    if not np.array_equal(v['slaves'],setup['floquets'][record['degree']].mpc.slaves) or not np.array_equal(v['kappa'],carrier(cfg)):
        raise ValueError('resume canonical MPC/carrier')
    bundle,rhs=build_bundle(cfg,setup,journal);u=rhs.duplicate();u.array[:]=v['u_storage']
    try:
        if relative(rhs.array-v['rhs'],rhs.array)>1e-13:raise ValueError('resume physical RHS changed')
        norms,vectors=audit_original(bundle,rhs,u,v['port'],journal)
        _,rec,rv=native_recovery_action_split_check(bundle,u,rhs,v['port'],vectors,journal)
        output=physical_output(bundle,u,v['port'],geo,folder,journal)
        rec_arrays=save_arrays(folder/'recovery.npz',**rv)
        pair=compare_saved(stage('NOTCH_P4'),dict(case=record['case'],degree=record['degree'],grid=record['grid'],arrays=record['arrays'],output=output),folder,journal)
        env=restore_p0_full_field(setup['floquets'][record['degree']],u);ev=PhaseEvaluator(env.function_space,15,bundle['kappa'])
        with journal.measured('pre_registered_direction_h_indicator'):
            per=np.asarray([ev.gradient_indicator(env,c,cfg.k0) for c in range(len(geo['cell_centers']))])
        total=per.sum(axis=0);axis=int(np.argmax(total))
        indicator=dict(totals=total,selected_axis=('x','y','z')[axis],grid=('X2','Y2','Z2')[axis],
            rule='sum h_K,d^2 integral(|partial_d u|^2+|partial_d Henv|^2); code units; first argmax x/y/z',arrays=save_arrays(folder/'h_indicator.npz',per_cell=per,totals=total))
        eq=equation_gate(norms,rec)
        if eq and stage('NOTCH_P4')['equation_pass'] and not pair['pass_gate']:
            write_json(window.TMP/'h_selection.json',indicator|dict(parent_array_sha256=record['arrays']['sha256']))
        return dict(status='COMPLETED',role=role,case=record['case'],degree=record['degree'],grid=record['grid'],
            representation='FIXED_PHASE_PERIODIC_NEDELEC_ENVELOPE',arrays=record['arrays'],returned_arrays=record['returned_arrays'],
            solve_source_sha=record['solve_source_sha'],postprocessing_resume=record,original_audit=norms,recovery=rec,recovery_arrays=rec_arrays,
            output=output,analytic=None,accuracy_pass=False,analytic_weak=None,p_pair=pair,h_indicator=indicator,equation_pass=eq,
            direct_target_pass=max(norms[k] for k in ('true','augmented','port'))<=1e-10,capacity=record['capacity'],boundary=record['boundary'],
            build_audit=record['build_audit'],mode_sha256=bundle['mode_sha256'],fixed_refinements_count=record['fixed_refinements_count'],
            timings_parent_preserved=True,timings=journal.timings,calls=journal.calls,NN_training=0,new_complete_solves=0,new_factor_count=0)
    finally:u.destroy();rhs.destroy();destroy_same_mesh_physical_action(bundle)
