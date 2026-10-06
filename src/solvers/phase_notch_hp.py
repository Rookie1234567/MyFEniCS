"""Thin finite hp queue over the qualified fixed-phase Maxwell kernels.

Only geometry/degree/inventory vary. Original uncondensed audits remain
independent of the finite-authority sparse matrix and exact direct factor.
"""
from dataclasses import replace
from pathlib import Path
import gc
import hashlib
import json
import numpy as np
from src.runners.task042_shared import write_json,_json_metadata
from .phase_notch_hp_scope import ROOT,ARTIFACT,window,plan_record,case_spec,stage,SOLVES
from .scattering_anchor import Journal,condense,audit_original,save_arrays,relative
from .scattering_anchor_checks import checked_arrays,native_recovery_action_split_check
from .phase_explicit_accuracy import make_setup,configuration as old_configuration,build_bundle,boundary_check,CoordinateFactor,equation_gate
from .phase_explicit_accuracy_fields import physical_output,PhaseEvaluator
from .phase_notch_hp_capacity import assembly_capacity
from .fixed_phase_fem import carrier


def configured_setup(spec,journal,*,scope=None):
    # Exact case spec is supplied by resolved input, including conditional
    # selections. Never infer a fine mesh from an old 80-cell active template.
    p=plan_record() if scope is None else scope.plan_record()
    label='v52' if scope is None else scope.NAMESPACE
    base=p['physical_descriptor']['geometry'];axes={}
    for key,factor in zip(('x','y','z'),spec['splits'],strict=True):
        old=base['axes_nm'][key]
        axes[key]=tuple(l+(r-l)*j/factor for l,r in zip(old[:-1],old[1:]) for j in range(factor))+(old[-1],)
    cfg=old_configuration('NOTCH',spec['degree'],'ORIGINAL')
    from .phase_notch_hp_modes import finite_mode_ranges
    m,n=finite_mode_ranges(spec['complete_modes'])
    cfg=replace(cfg,case_name='task042_'+label+'_notch_p'+str(spec['degree'])+'_'+''.join(map(str,spec['splits']))+'_m'+str(spec['complete_modes']),
        mesh_axis_x_values=axes['x'],mesh_axis_y_values=axes['y'],mesh_axis_z_values=axes['z'],
        mesh_axis_cell_counts=tuple(len(axes[a])-1 for a in ('x','y','z')),
        mesh_plan_id='task042.'+label+'.fixed',mesh_axis_z_profile='task042.'+label+'.fixed',
        diffraction_order_max_m=m,diffraction_order_max_n=n)
    geo={**base,'notch_expected_changed_cells':2*int(np.prod(spec['splits']))}
    cfg,setup,geometry=make_setup('NOTCH',spec['degree'],'SPEC',journal,configured=cfg,geometry_descriptor=geo,
        finite_authority_degree7=scope is not None and scope.NAMESPACE in ('v53','v54','v55') and spec['degree']==7)
    return cfg,setup,geometry


def parent(role):
    from .phase_explicit_accuracy_scope import stage as previous
    return previous('NOTCH_HPROBE' if role=='B0' else 'FLAT_P4')


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V52 scientific queue frozen')
    if not stage('SETUP')['pass_gate']:raise RuntimeError('V52 actual preflight not qualified')
    if role in ('HP','T','M'):
        pick=window.TMP/(role+'_admission.json')
        if not pick.exists():raise RuntimeError('conditional '+role+' not admitted')
        decision=json.loads(pick.read_text())
        if not decision['admitted'] or not decision.get('evidence'):raise RuntimeError('conditional '+role+' not bound')
        for item in decision['evidence']:
            path=Path(item['path']).resolve()
            if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('conditional evidence changed')
    completed=[s for s in SOLVES if (ARTIFACT/(s+'.json')).exists() and stage(s).get('returned_arrays')]
    if len(completed)>=5:raise RuntimeError('five complete solves already consumed')


def solve_case(role,folder,journal,*,scope=None):
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    from .scattering_accuracy import volume_form_identity
    live=window if scope is None else scope.window
    (require_stage if scope is None else scope.require_stage)(role)
    spec=case_spec(role) if scope is None else scope.case_spec(role)
    p=plan_record() if scope is None else scope.plan_record()
    mem=p.get('memory_budget',dict(planning_gib=16,sampled_stop_gib=24,extra_cache_workspace_gib=0))
    if not spec['splits']:raise RuntimeError('conditional geometry is not selected')
    resume=live.TMP/(role+'_post_resume.json')
    if resume.exists():return audit_saved_return(role,folder,journal,json.loads(resume.read_text()),scope=scope)
    cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    cap=assembly_capacity(setup,cfg,journal,spec,planning_limit_bytes=mem['planning_gib']*2**30,
        sampled_stop_bytes=mem['sampled_stop_gib']*2**30,extra_workspace_bytes=mem['extra_cache_workspace_gib']*2**30,
        row_cap=p.get('assembly_row_cap',80000))
    write_json(folder/'assembly_capacity.json',cap)
    if not cap['admitted']:return dict(status='CAPACITY_BLOCKED',role=role,case_spec=spec,capacity=cap)
    bundle=rhs=inverse=system=u=factor=None
    try:
        boundary=boundary_check(cfg,setup,folder,journal)
        if not boundary['pass_gate']:return dict(status='NUMERICAL_BOUNDARY_NOT_QUALIFIED',role=role,case_spec=spec,boundary=boundary,capacity=cap)
        bundle,rhs=build_bundle(cfg,setup,journal);write_json(folder/'actual_volume_form_identity.json',volume_form_identity(bundle))
        if len(bundle['modes'])!=spec['complete_modes']:raise ValueError('actual full mode count')
        checkpoint=None
        if scope is not None:
            from .phase_tensor_checkpoint import RawTensorCheckpoint
            reader=scope.raw_tensor_reader(role,bundle,journal) if hasattr(scope,'raw_tensor_reader') else None
            checkpoint=RawTensorCheckpoint(folder/'raw_tensor',bundle,journal,reader=reader)
        system,inverse=condense(bundle,journal,expected=(cap['native'],cap['trace'],cap['internal']),raw_tensor_provider=checkpoint)
        if checkpoint is not None:checkpoint.finish(setup,spec['degree'])
        write_json(folder/'build_audit.json',system.build_audit)
        if system.active_rows+len(bundle['modes'])!=spec['rows']:raise ValueError('condensed actual row identity')
        try:
            factor=CoordinateFactor(system.matrix,bundle,system.active_rows,journal,folder,symbolic_capacity=True,
                planning_limit_bytes=mem['planning_gib']*2**30)
        except MemoryError as error:
            path=folder/'h_symbolic_capacity.json'
            if not path.exists():raise
            symbolic=json.loads(path.read_text())
            if symbolic['plan']['admitted'] is not False:raise
            journal.event('bounded_numeric_not_admitted',reason=str(error),symbolic_plan=symbolic['plan'])
            return dict(status='CAPACITY_BLOCKED',role=role,case_spec=spec,capacity=cap,boundary=boundary,
                build_audit=_json_metadata(system.build_audit),symbolic_capacity=symbolic,
                global_factor_state='SYMBOLIC_ONLY_NO_NUMERIC',new_global_numeric_factor_count=0,
                new_complete_solves=0,reason=str(error))
        inverse.factor=factor
        with journal.measured('solve_and_affine_internal_recovery'):
            u=inverse.apply(rhs);port=inverse.last_port_solution.copy()
        early=save_arrays(folder/'returned_solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],
            slaves=np.asarray(setup['floquets'][spec['degree']].mpc.slaves),**geo)
        minimal=dict(status='AUDIT_PENDING',role=role,case='NOTCH',case_spec=spec,degree=spec['degree'],
            grid='x'.join(map(str,spec['splits'])),source=journal.source_state,arrays=early,returned_arrays=early,
            capacity=cap,boundary=boundary,build_audit=_json_metadata(system.build_audit),mode_sha256=bundle['mode_sha256'])
        write_json(folder/'minimal_scientific_state.json',minimal);journal.event('returned_complete_physical_state_saved',sha256=early['sha256'])
        norms,vectors=audit_original(bundle,rhs,u,port,journal);refinements=[]
        for _ in range(2):
            if max(norms[k] for k in ('true','augmented','port'))<=1e-10:break
            d=rhs.duplicate();d.array[:]=vectors['residual']
            with journal.measured('fixed_refinement'):
                delta=inverse.apply(d);u.axpy(1,delta);port+=inverse.last_port_solution
            delta.destroy();d.destroy();norms,vectors=audit_original(bundle,rhs,u,port,journal);refinements.append(norms)
        arrays=save_arrays(folder/'solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],
            slaves=np.asarray(setup['floquets'][spec['degree']].mpc.slaves),**geo,**vectors)
        minimal.update(arrays=arrays,original_audit=norms,fixed_refinements=refinements)
        write_json(folder/'minimal_scientific_state.json',minimal)
        inverse.factor=None;factor.destroy();factor=None;system.matrix.destroy();system.matrix=None;gc.collect()
        journal.event('factor_and_matrix_released_original_oracle_retained')
        result=postprocess_state(role,spec,cfg,setup,geo,bundle,rhs,u,port,arrays,early,folder,journal,
            cap,boundary,minimal['build_audit'],norms,vectors,scope=scope)
        if checkpoint is not None:result['raw_tensor_checkpoint']=checkpoint.record()
        result['fixed_refinements']=refinements;write_json(folder/'scientific_result.json',result)
        return result
    finally:
        if factor is not None:factor.destroy()
        if u is not None:u.destroy()
        if rhs is not None:rhs.destroy()
        if inverse is not None:inverse.destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)


def postprocess_state(role,spec,cfg,setup,geo,bundle,rhs,u,port,arrays,early,folder,journal,cap,boundary,build_audit,norms,vectors,*,scope=None):
    _,recovery,rv=native_recovery_action_split_check(bundle,u,rhs,port,vectors,journal)
    rec=save_arrays(folder/'recovery.npz',**rv);output=physical_output(bundle,u,port,geo,folder,journal)
    projected=None
    if scope is not None and hasattr(scope,'project_mode_parent'):
        projected=scope.project_mode_parent(role,bundle,rhs,geo,folder,journal)
    if role=='M':
        from .phase_notch_hp_modes import project_saved_parent
        live=window if scope is None else scope.window
        selected=json.loads((live.TMP/'mode_selection.json').read_text())
        original=stage(selected['role']) if scope is None else scope.read(selected['role'])
        if original['arrays']['sha256']!=selected['parent_array_sha256']:raise ValueError('selected finite mode parent changed')
        projected=project_saved_parent(original,bundle,geo,folder,journal)
    indicator=None
    if role=='P':
        from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
        env=restore_p0_full_field(setup['floquets'][spec['degree']],u);ev=PhaseEvaluator(env.function_space,15,bundle['kappa'])
        with journal.measured('scattered_envelope_transverse_indicator'):
            per=np.asarray([ev.gradient_indicator(env,c,cfg.k0)[:2] for c in range(spec['cells'])])
        total=per.sum(axis=0);axis=int(np.argmax(total));splits=[1,1,2];splits[axis]=2
        indicator=dict(totals_xy=total,selected_axis=('x','y')[axis],splits=splits,
            rule='scattered envelope derivative; layered background transverse envelope derivatives exactly zero; x tie',
            arrays=save_arrays(folder/'transverse_indicator.npz',per_cell_xy=per,totals_xy=total))
        write_json(window.TMP/'transverse_selection.json',indicator|dict(parent_array_sha256=arrays['sha256']))
    return dict(status='COMPLETED',role=role,case='NOTCH',case_spec=spec,degree=spec['degree'],grid='x'.join(map(str,spec['splits'])),
        representation='FIXED_PHASE_PERIODIC_NEDELEC_ENVELOPE',arrays=arrays,returned_arrays=early,original_audit=norms,
        recovery=recovery,recovery_arrays=rec,output=output,equation_pass=equation_gate(norms,recovery),
        direct_target_pass=max(norms[k] for k in ('true','augmented','port'))<=1e-10,
        capacity=cap,build_audit=build_audit,boundary=boundary,mode_sha256=bundle['mode_sha256'],
        transverse_indicator=indicator,projected_parent828=projected,timings=journal.timings,calls=journal.calls,NN_training=0)


def audit_saved_return(role,folder,journal,record,*,scope=None):
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    live=window if scope is None else scope.window
    resume=live.TMP/(role+'_post_resume.json')
    if journal.source_state.get('postprocessing_resume',{}).get('sha256')!=hashlib.sha256(resume.read_bytes()).hexdigest():
        raise ValueError('live resolved returned-state binding')
    spec=record['case_spec'];v=checked_arrays(record['arrays']);cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    for k in geo:
        if not np.array_equal(geo[k],v[k]):raise ValueError('returned geometry changed '+k)
    if not np.array_equal(v['kappa'],carrier(cfg)) or not np.array_equal(v['slaves'],setup['floquets'][spec['degree']].mpc.slaves):
        raise ValueError('returned carrier/MPC changed')
    bundle,rhs=build_bundle(cfg,setup,journal);u=rhs.duplicate();u.array[:]=v['u_storage']
    try:
        if relative(rhs.array-v['rhs'],rhs.array)>1e-13:raise ValueError('returned physical RHS changed')
        norms,vectors=audit_original(bundle,rhs,u,v['port'],journal)
        r=postprocess_state(role,spec,cfg,setup,geo,bundle,rhs,u,v['port'],record['arrays'],record['returned_arrays'],
            folder,journal,record['capacity'],record['boundary'],record['build_audit'],norms,vectors,scope=scope)
        r.update(postprocessing_resume=True,solve_source_sha=record['source']['source_sha'],new_complete_solves=0,new_factor_count=0)
        return r
    finally:u.destroy();rhs.destroy();destroy_same_mesh_physical_action(bundle)


def preflight(folder,journal):
    parents={}
    for role in ('FLAT','B0'):
        r=parent(role);v=checked_arrays(r['arrays'])
        if r['role']!=('FLAT_P4' if role=='FLAT' else 'NOTCH_HPROBE') or not r['equation_pass'] or (role=='FLAT' and not r['accuracy_pass']):
            raise ValueError('frozen V51 parent qualification')
        parents[role]=dict(array_sha256=r['arrays']['sha256'],source_sha=r['source_sha'],mode_sha256=r['mode_sha256'],
            saved_field_members=list(v),equation_pass=True,analytic_pass=r.get('accuracy_pass',False))
    cfg,setup,geo=configured_setup(case_spec('P'),journal);capacity=assembly_capacity(setup,cfg,journal,case_spec('P'))
    return dict(status='COMPLETED',role='SETUP',parents=parents,geometry=save_arrays(folder/'geometry.npz',**geo),
        capacity=capacity,pass_gate=True,capacity_P=capacity['admitted'],new_solve_count=0,new_factor_count=0,
        FLAT_analytic_reused=True,timings=journal.timings,calls=journal.calls)


def restore_record(r,journal,*,scope=None):
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    if 'case_spec' in r:cfg,setup,geo=configured_setup(r['case_spec'],journal,scope=scope)
    else:cfg,setup,geo=make_setup(r['case'],r['degree'],r['grid'],journal)
    v=checked_arrays(r['arrays'])
    for key in geo:
        if not np.array_equal(geo[key],v[key]):raise ValueError('saved comparison geometry '+key)
    vec=PETSc.Vec().createSeq(len(v['u_storage']),comm=PETSc.COMM_SELF);vec.array[:]=v['u_storage']
    try:field=restore_p0_full_field(setup['floquets'][r['degree']],vec)
    finally:vec.destroy()
    return cfg,setup,geo,field


def compare_saved(first,second,folder,journal,*,scope=None,evaluator_factory=None):
    from .phase_notch_hp_fields import common_difference
    from .phase_notch_hp_modes import mode_comparison
    a=restore_record(first,journal,scope=scope);b=restore_record(second,journal,scope=scope)
    # These are the actual published V51 physical sampling points, never a
    # replacement set chosen to improve the comparison.
    points=[]
    for name in ('NOTCH_P5','NOTCH_HPROBE'):
        from .phase_explicit_accuracy_scope import stage as previous
        r=previous(name);f=checked_arrays(r['output']['fields']);points.append(f['selected_points'])
    pp=np.unique(np.concatenate(points),axis=0)
    low=common_difference(a[3],b[3],b[0],journal,folder,q=23,selected_points=pp,evaluator_factory=evaluator_factory)
    r=common_difference(a[3],b[3],b[0],journal,folder,q=31,selected_points=pp,evaluator_factory=evaluator_factory)
    qdef=max(abs(low['fields'][key][n]**2-r['fields'][key][n]**2)/max(r['fields'][key]['reference_L2']**2,1e-24)
        for key in r['fields'] for n in ('reference_L2','difference_L2'))
    r.update(quadrature_pair=[23,31],quadrature_operation_scaled=qdef,q23_arrays=low['arrays'])
    modes=mode_comparison(first,second,folder)
    power={key:abs(first['output']['port_metrics'][key]-second['output']['port_metrics'][key]) for key in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
    energies=[abs(x['output']['volume_metrics']['energy_closure_error_port_volume']) for x in (first,second)]
    r.update(modes=modes,power_differences=power,energies=energies,parent_array_sha256=[first['arrays']['sha256'],second['arrays']['sha256']],
        mode_qualification_quantity='physical outgoing amplitude at original boundary reference planes; raw diagnostic separately retained')
    r['pass_gate']=r['pass_gate'] and first['equation_pass'] and second['equation_pass'] and first.get('direct_target_pass',max(first['original_audit'][k] for k in ('true','augmented','port'))<=1e-10) and second.get('direct_target_pass',False) and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energies)<=1e-5
    return r


def compare_queue(folder,journal):
    pairs=[('B0','H'),('B0','P'),('H','P'),('H','HP'),('P','HP'),('P','T')];rows=[]
    if (ARTIFACT/'M.json').exists() and stage('M').get('equation_pass'):
        pairs.append((json.loads((window.TMP/'mode_selection.json').read_text())['role'],'M'))
    cache=ARTIFACT/'comparisons';cache.mkdir(exist_ok=True)
    for left,right in pairs:
        if any(x!='B0' and (not (ARTIFACT/(x+'.json')).exists() or not stage(x).get('equation_pass')) for x in (left,right)):continue
        records=[stage('M')['projected_parent828'] if right=='M' and x==left else parent(x) if x=='B0' else stage(x) for x in (left,right)];name=left+'_'+right
        dest=cache/(name+'.json')
        if dest.exists():
            r=json.loads(dest.read_text())
            if r['parent_array_sha256']!=[x['arrays']['sha256'] for x in records]:raise ValueError('cached comparison identity')
        else:
            sub=cache/name;sub.mkdir(exist_ok=False);r=compare_saved(*records,sub,journal);write_json(dest,r)
        rows.append(dict(pair=[left,right],comparison=r,comparison_path=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    return rows


def verify_cost(folder,journal,*,scope=None,inventory_path=None,read_state=None,after_state=None,output_role='VERIFY_COST'):
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    live=window if scope is None else scope.window
    read_stage=read_state or (stage if scope is None else scope.stage)
    path=Path(inventory_path) if inventory_path is not None else live.TMP/'scientific_queue_frozen.json'
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('actual frozen queue binding')
    frozen=json.loads(path.read_text());rows=[]
    for role,item in frozen['completed_solves'].items():
        r=read_stage(role)
        if item['array_sha256']!=r['arrays']['sha256']:raise ValueError('frozen actual state changed')
        v=checked_arrays(r['arrays']);cfg,setup,geo=configured_setup(r['case_spec'],journal,scope=scope)
        basis=scope.verification_basis_identity(setup,r) if scope is not None and hasattr(scope,'verification_basis_identity') else None
        for key in geo:
            if not np.array_equal(geo[key],v[key]):raise ValueError('independent final geometry '+key)
        bundle,rhs=build_bundle(cfg,setup,journal,q=63);u=rhs.duplicate();u.array[:]=v['u_storage']
        try:
            norms,vectors=audit_original(bundle,rhs,u,v['port'],journal)
            field,rec,rv=native_recovery_action_split_check(bundle,u,rhs,v['port'],vectors,journal)
            receipt=save_arrays(folder/(role+'_independent_audit.npz'),u_storage=u.array.copy(),rhs=rhs.array.copy(),port=v['port'],recovered_native_full=field.x.array.copy(),**vectors,**rv)
            rows.append(dict(role=role,parent=r['arrays']['sha256'],audit=norms,recovery=rec,arrays=receipt,equation_pass=equation_gate(norms,rec)))
            if basis is not None:rows[-1]['actual_basis_identity']=basis
            write_json(folder/(role+'_audit_record.json'),rows[-1])
            write_json(folder/'verification_progress.json',dict(status='AUDIT_PENDING',rows=rows,
                frozen_queue_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source=journal.source_state))
            if after_state is not None:
                rows[-1]['additional_checks']=after_state(role,r,setup,bundle,field,folder,journal)
                write_json(folder/(role+'_audit_record.json'),rows[-1])
                write_json(folder/'verification_progress.json',dict(status='AUDIT_PENDING',rows=rows,
                    frozen_queue_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source=journal.source_state))
        finally:u.destroy();rhs.destroy();destroy_same_mesh_physical_action(bundle)
    return dict(status='COMPLETED',role=output_role,rows=rows,cached_comparisons=compare_queue(folder,journal) if scope is None else scope.cached_comparisons(),
        new_factor_count=0,new_complete_solves=0,NN_training=0,target_qualified=False,timings=journal.timings,calls=journal.calls)


def execute(role,folder,state):
    journal=Journal(folder,window_scope=window,planning_limit_bytes=16*2**30);journal.source_state=state
    if role=='SETUP':return preflight(folder,journal)
    if role in SOLVES:
        result=solve_case(role,folder,journal)
        # All direct/original objects have left solve_case before these
        # pairwise integrations. Persisted returned coefficients survive any
        # later presentation/comparison exception without another solve.
        if result.get('equation_pass'):
            result['comparisons']=finish_comparisons(role,result,journal)
        return result
    if role=='VERIFY_COST':return verify_cost(folder,journal)
    raise ValueError('V52 stage inventory')


def finish_comparisons(role,result,journal):
    partners={'H':['B0'],'P':['B0','H'],'HP':['H','P'],'T':['P'],'M':[]}[role]
    cache=ARTIFACT/'comparisons';cache.mkdir(exist_ok=True);rows=[]
    if role=='M':partners=[json.loads((window.TMP/'mode_selection.json').read_text())['role']]
    for left in partners:
        if left!='B0' and (not (ARTIFACT/(left+'.json')).exists() or not stage(left).get('equation_pass')):continue
        previous=result['projected_parent828'] if role=='M' else parent(left) if left=='B0' else stage(left);name=left+'_'+role;dest=cache/(name+'.json')
        if dest.exists():
            r=json.loads(dest.read_text())
            if r['parent_array_sha256']!=[previous['arrays']['sha256'],result['arrays']['sha256']]:raise ValueError('cached comparison changed')
        else:
            sub=cache/(name+'_'+journal.folder.name);sub.mkdir(exist_ok=False)
            r=compare_saved(previous,result,sub,journal);write_json(dest,r)
        rows.append(dict(pair=[left,role],comparison_path=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),pass_gate=r['pass_gate']))
    return rows
