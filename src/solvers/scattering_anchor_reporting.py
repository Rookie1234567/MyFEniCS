"""Complete finite anchor cost and one fixed p-increment consumer.

No solver is implemented here. Saved parents are checked, original FE fields
are integrated once, and nested stage timings are converted to disjoint costs.
"""
import json
from pathlib import Path
import numpy as np

from .scattering_anchor_scope import ROOT,stage,window


def disjoint_timings(events):
    stack=[];exclusive={};inclusive={};roots=0.
    for e in events:
        name=e['event'];now=float(e['elapsed_s'])
        if name.endswith('_begin'):
            stack.append([name[:-6],now,0.])
        elif name.endswith('_end'):
            role=name[:-4]
            if not stack or stack[-1][0]!=role:raise ValueError('non-paired timing event '+role)
            _,began,children=stack.pop();duration=now-began
            if duration<children-1e-7:raise ValueError('nested timing exceeds parent')
            inclusive[role]=inclusive.get(role,0.)+duration
            exclusive[role]=exclusive.get(role,0.)+max(0.,duration-children)
            if stack:stack[-1][2]+=duration
            else:roots+=duration
    if stack:raise ValueError('incomplete measured timeline')
    return {'exclusive_seconds':exclusive,'inclusive_seconds_do_not_sum':inclusive,'root_measured_seconds':roots}


def p5_capacity():
    # Dense LU and one equally sized factor workspace envelope, sparse assembly
    # copies, bounded cell recovery caches and compiler/runtime coexistence.
    rows=12132;dense=rows**2*16
    contributors={'finite_dense_factor_payload_bound':dense,'factor_workspace_reserve_prediction':dense,
                  'assembly_sparse_copies_reserve':2**30,'cell_recovery_cache_reserve':2**29,
                  'native_JIT_compiler_runtime_reserve':2**30}
    total=sum(contributors.values())
    if total>8*2**30:raise MemoryError('P5_CAPACITY_BLOCKED planned coexistence')
    return {'classification':'predicted_not_measured','native_rows':32865,'independent_FE':30800,
            'trace':11600,'interior':19200,'ports':532,'condensed_rows':rows,
            'contributors_bytes':contributors,'planned_peak_bytes':total,
            'planning_limit_bytes':8*2**30,'uncertainty':'opaque MUMPS/JIT actual workspace remains independently sampled; prediction is not an RSS guarantee'}


def finite_power_comparison(reference,candidate):
    from .scattering_anchor_checks import mode_comparison
    r,c=reference['output'],candidate['output']
    power={k:abs(c['port_metrics'][k]-r['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(c['volume_metrics']['A_volume_total']-r['volume_metrics']['A_volume_total'])
    return {'power_absolute_differences':power,'all_modes':mode_comparison(reference,candidate),
            'reference_energy_absolute':abs(r['volume_metrics']['energy_closure_error_port_volume']),
            'candidate_energy_absolute':abs(c['volume_metrics']['energy_closure_error_port_volume'])}


def p4_companion_mpc(space,mesh_data,cfg):
    # MPC validates the actual edge/face degree. The physical mesh/material/
    # wavevector are unchanged, but a p4 space must never receive a p5 layout.
    from dataclasses import replace
    from src.constraints.floquet_3d import build_double_floquet_mpc
    companion=replace(cfg,nedelec_degree=4,visualization_degree=4)
    return build_double_floquet_mpc(space,mesh_data,companion)


def p_increment(folder,journal):
    from dolfinx import fem
    from basix.ufl import element
    from .scattering_anchor import make_setup,build_bundle,audit_original,save_arrays,relative
    from .scattering_anchor_checks import checked_arrays,native_recovery_action_split_check,integrated_difference
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action,restore_p0_full_field
    from .common_3d_fields import stage4_layered_background_field
    ref=stage('REFERENCE_NOTCH')
    try:p5=stage('REFERENCE_NOTCH_P5')
    except FileNotFoundError:return {'status':'not_run','reason':'no qualified saved p5 parent'}
    values4=checked_arrays(ref['arrays']);values5=checked_arrays(p5['arrays'])
    cfg,setup,geometry=make_setup('NOTCH',5,journal);bundle,rhs,_=build_bundle(cfg,setup,journal)
    try:
        from src.io.scattering_anchor import load_scattering_anchor
        p5_spec=load_scattering_anchor(ROOT/'input/task042_neural_coarse_inverse/v49_reference_notch_p5.dat')
        if p5_spec.physical_model_sha256!=p5['physical_contract_sha256']:raise ValueError('p5 live/frozen physical descriptor')
        if bundle['mode_sha256']!=p5['output']['mode_manifest_sha256']:raise ValueError('p5 live complete mode identity')
        if relative(values5['rhs']-rhs.array,rhs.array)>1e-13:raise ValueError('p5 live/frozen physical RHS')
        for values in (values4,values5):
            for key in ('geometry_x','geometry_dofmap','cell_centers','cell_tags'):
                if not np.array_equal(values[key],geometry[key]):raise ValueError('same physical mesh p-increment '+key)
        from petsc4py import PETSc
        u=PETSc.Vec().createSeq(len(values5['u_storage']),comm=PETSc.COMM_SELF);u.array[:]=values5['u_storage']
        try:
            norms,vectors=audit_original(bundle,rhs,u,values5['port'],journal)
            E5,recovery,split=native_recovery_action_split_check(bundle,u,rhs,values5['port'],vectors,journal)
        finally:u.destroy()
        independent_arrays=save_arrays(Path(folder)/'P5_original_independent_audit.npz',**vectors,**split)
        V4=fem.functionspace(setup['mesh'],element('N1curl',setup['mesh'].basix_cell(),4))
        mpc4=p4_companion_mpc(V4,setup['mesh_data'],cfg)
        if not np.array_equal(mpc4.mpc.slaves,values4['slaves']):raise ValueError('p4 reconstruction canonical slave order')
        v4=PETSc.Vec().createSeq(len(values4['u_storage']),comm=PETSc.COMM_SELF);v4.array[:]=values4['u_storage']
        try:E4=restore_p0_full_field(mpc4,v4)
        finally:v4.destroy()
        with journal.measured('p4_p5_common_physical_integrals'):
            fields=integrated_difference(setup['mesh'],E4,E5,cfg.k0)
            bg4=stage4_layered_background_field(V4,cfg);bg5=stage4_layered_background_field(E5.function_space,cfg)
            es4=fem.Function(V4);es5=fem.Function(E5.function_space)
            es4.x.array[:]=E4.x.array-bg4.x.array;es5.x.array[:]=E5.x.array-bg5.x.array
            fields.update({k.replace('total','scattered'):v for k,v in integrated_difference(setup['mesh'],es4,es5,cfg.k0).items()})
        rf=checked_arrays(ref['output']['fields']);cf=checked_arrays(p5['output']['fields'])
        if not np.array_equal(rf['selected_points'],cf['selected_points']):raise ValueError('fixed p4/p5 selected physical points')
        selected={k:float(np.linalg.norm(cf[k]-rf[k])/max(np.linalg.norm(rf[k]),1e-12))
                  for k in rf if k.startswith('selected_') and k!='selected_points'}
        equation=max(norms[k] for k in ('true','native','augmented','port'))<=1e-6 and norms['identity']<=1e-10 and norms['slave_zero']
        recovering=max(recovery[k] for k in ('operation_scaled_interior','max_cell_operation_scaled','master_storage_max_abs','split_action_identity_operation_scale'))<=1e-10 and recovery['slave_storage_zero']
        return {'status':'measured','degree_pair':[4,5],'same_geometry_same_80mesh':True,
                'actual_operator_identity':{'degree':5,'physical_contract_sha256':p5_spec.physical_model_sha256,
                    'source_sha':p5['source_sha'],'mode_sha256':bundle['mode_sha256'],'parent_state_sha256':p5['arrays']['sha256']},
                'p5_original_audit':norms,'p5_recovery':recovery,'independent_arrays':independent_arrays,
                'p5_equation_pass':equation,'p5_direct_internal_target_pass':max(norms[k] for k in ('true','augmented','port'))<=1e-10,
                'p5_recovery_pass':recovering,'p5_energy_pass':abs(p5['output']['volume_metrics']['energy_closure_error_port_volume'])<=1e-5,
                'fields':fields,'selected':selected,
                **finite_power_comparison(ref,p5),'no_continuum_convergence_claim':True}
    finally:rhs.destroy();destroy_same_mesh_physical_action(bundle)


def route_cost(name):
    record=stage(name);artifact=Path(record['arrays']['path']).parent
    result_dir=ROOT/'results/task042'/artifact.name
    summary=json.loads((result_dir/'run_summary.json').read_text())
    manifest=json.loads((result_dir/'run_manifest.json').read_text())
    events=[json.loads(x) for x in (artifact/'events.jsonl').read_text().splitlines()]
    time=disjoint_timings(events)
    samples=[json.loads(x) for x in (result_dir/'supervision/resources.jsonl').read_text().splitlines()]
    sample_t=np.array([x['elapsed_seconds'] for x in samples])
    peak_sample=max(samples,key=lambda x:x['rss_bytes'])
    peak_monotonic=peak_sample['parent_clock']['monotonic']
    phases=[x for x in events if x['clock']['observed_monotonic']<=peak_monotonic]
    source_time={k:float(record.get(k,0.)) for k in ('elapsed_worker_seconds',)}
    return {'stage':name,'source_sha':record['source_sha'],'parent_result_path':str(artifact/'result.json'),
            'physical_contract_sha256':record['physical_contract_sha256'],'array_sha256':record['arrays']['sha256'],
            'cold_N1_measured_dat_launch_lower_bound_seconds':summary['launch_wall_seconds'],
            'startup_before_launcher_seconds':'unknown; no claim of an exact shell-to-end timer',
            'worker_seconds':source_time['elapsed_worker_seconds'],'supervised_seconds':summary['elapsed_seconds'],
            **time,'worker_unclassified_IO_cleanup_and_uninstrumented_seconds':max(0.,source_time['elapsed_worker_seconds']-time['root_measured_seconds']),
            'process_tree_sampled_peak_bytes':summary['sampled_process_tree_rss_peak_bytes'],
            'own_swap_peak_bytes':summary['sampled_process_tree_swap_peak_bytes'],
            'actual_sample_max_interval_seconds':float(np.max(np.diff(sample_t),initial=0)),
            'peak_nearest_preceding_event':phases[-1]['event'] if phases else 'launcher/pre-worker',
            'peak_phase_clock_basis':'same CLOCK_MONOTONIC; worker and supervisor elapsed origins are not assumed equal',
            'MPI':manifest['MPI_size'],'cpu':manifest['cpu'],'math_threads':1,'GPU':0,
            'compile_cache_policy':'Task042/v49 isolated cache; retained OS/JIT hits, no factor reuse from another case',
            'cache_first_use_record':'REFERENCE_REGULAR source e184; first JIT cost retained in research and its cold record',
            'timing_classification':'shared-workstation; no contention-free speedup claim',
            'nested_timing_policy':'only exclusive_seconds sum; inclusive costs are alternatives',
            'actual_factor_inventory':{'global_finite_authority':1 if name.startswith('REFERENCE') else 0,
                'bounded_four_q_factors':4 if name.startswith('ENGINE') else 0,
                'local_class_LU_counts':[e['cell_classes'] for e in events if e['event']=='condensed_objects_ready']},
            'original_action_calls':record['calls'],'equation_pass':record['equation_pass'],
            'saved_before_audit':True,'factor_free':False,
            'lifecycle_events':[{k:v for k,v in e.items() if k!='clock'} for e in events if e['event'] in
                ('object_owner_snapshot','factor_present','global_finite_factor_released','condensed_matrix_released','two_cell_matrix_released','all4q_local_factors_released','condensed_objects_ready')]}


def cost_report(folder,journal):
    rows=[];missing=[]
    for name in ('REFERENCE_REGULAR','REFERENCE_NOTCH','ENGINE_REGULAR','ENGINE_NOTCH','REFERENCE_NOTCH_P5'):
        try:rows.append(route_cost(name))
        except FileNotFoundError:missing.append({'stage':name,'status':'not_run'})
    pcheck=p_increment(folder,journal)
    # These are distinct scientific objects: only full solve/factor removal is
    # not already excluded by the optimistic time bound; no training is run.
    opportunity=[]
    for case in ('REGULAR','NOTCH'):
        eligible=[r for r in rows if r['stage'] in ('REFERENCE_'+case,'ENGINE_'+case) and r['equation_pass']]
        if not eligible:continue
        r=min(eligible,key=lambda v:v['cold_N1_measured_dat_launch_lower_bound_seconds'])
        t=r['cold_N1_measured_dat_launch_lower_bound_seconds'];e=r['exclusive_seconds']
        tail=e.get('solve_and_minimal_internal_recovery',0.)+e.get('global_finite_factor_setup',0.)
        allsolve=tail+e.get('condensation_local_factors',0.)+e.get('two_cell_all4q_reference_inverse',0.)+e.get('outer_original_FGMRES32',0.)
        opportunity.append({'case':case,'selected_non_neural_baseline':r['stage'],'baseline_seconds_lower_bound':t,
             'factor_and_tail_complete_removal_optimistic_fraction':tail/t,
             'tail_or_initialization_only_20percent_impossible_even_H0':tail<.2*t,
             'one_possible_learning_object':'complete physical FE+DtN coefficient prediction that avoids condensation/factors, followed by original independent audit; distinct from closed fixed-A correction',
             'replaceable_condensation_factor_solve_seconds_optimistic':allsolve,
             'maximum_cold_data_teacher_training_inference_extra_check_seconds_optimistic':allsolve-.2*t,
             'same_case_full_teacher_alone_exceeds_allowance':t>allsolve-.2*t,
             'strongest_traditional_control':'qualified exact Full3D with exact geometry/tensor/cache sharing and full costs; sharing improvement unmeasured here',
             'necessary_peak_condition':'saved simultaneous bytes minus model/workspace >=0.2 measured full peak; opaque factor overlap and future model/teacher peaks unknown',
             'NN20':'NOT_DEMONSTRATED','decision':'no automatic training; necessary time space only, not an evidence-qualified learning proposal'})
    return {'status':'COMPLETED','routes':rows,'not_run':missing,'p_increment':pcheck,
            'research_ledger_snapshot':window.ledger(),'charged_loaded_seconds_before_this_stage':window.charged_wall(),
            'historical_known_lower_bound_seconds':88875.68891642192,'historical_unknowns_retained':True,
            'deployment_and_external_reference_verification_separate':True,'opportunity':opportunity,
            'NN_NOT_TRAINED_THIS_BATCH':True,'TARGET_NOT_QUALIFIED':True,'timings':journal.timings,'calls':journal.calls}
