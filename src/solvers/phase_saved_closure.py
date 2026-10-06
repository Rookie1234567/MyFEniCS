"""Saved H7 physical consumption, bounded transverse case, independent audit.

This queue calls existing field, mode and direct-solver kernels. The saved
stage deliberately has no path to tensor generation, condensation or solve.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from . import phase_saved_closure_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .phase_notch_hp import restore_record,solve_case
from .phase_notch_hp_fields import common_difference,parents_at,mesh_bounds
from .phase_evaluation_cache import cached_evaluator_factory
from .phase_saved_uncondensed import uncondensed_vectors,saved_audit


def selected_points():
    from .phase_explicit_accuracy_scope import stage
    pp=[]
    for name in ('NOTCH_P5','NOTCH_HPROBE'):
        r=stage(name);pp.append(checked_arrays(r['output']['fields'])['selected_points'])
    result=np.unique(np.concatenate(pp),axis=0)
    if result.shape!=(240,3):raise ValueError('original fixed 240 physical points')
    return result


def boundary_bundle(cfg,setup,q,journal):
    from .scattering_accuracy_boundary import SurfaceComponents
    from .fullspace_dtn_action import build_dynamic_mode_inventory,build_fullspace_dtn_carrier_from_surface
    from .dtn_port_3d import _incident_projection_onto_top_mode
    from .fixed_phase_fem import carrier
    degree=cfg.nedelec_degree;V=setup['spaces'][degree];mpc=setup['floquets'][degree].mpc;k=carrier(cfg)
    with journal.measured(f'saved_full828_boundary_q{q}_p{degree}'):
        modes,rows,sha=build_dynamic_mode_inventory(cfg)
        if len(modes)!=828:raise ValueError('saved full 828 inventory')
        src=SurfaceComponents(V,mpc,cfg,q,method='separable' if q==47 else 'basix2d',phase_carrier=k)
        c=build_fullspace_dtn_carrier_from_surface(modes,src.assemblers(),mpc,cfg,retain_all_nonzero=True)
        incident=tuple(_incident_projection_onto_top_mode(mode,cfg) for mode in modes)
    return dict(cfg=cfg,setup=setup,degree=degree,kappa=k,modes=modes,mode_rows=rows,mode_sha256=sha,
        incident_projections=incident,dtn_action=SimpleNamespace(carrier=c),dtn_quadrature_degree=q,surface=src)


def few_point_check(field,cfg,kappa,folder,journal):
    from .phase_explicit_accuracy_fields import PhaseEvaluator
    from .phase_evaluation_cache import CachedPhaseEvaluator,ExactTabulations
    V=field.function_space;old=PhaseEvaluator(V,23,kappa,quadrature_tables=False)
    new=CachedPhaseEvaluator(V,23,kappa,cache=ExactTabulations(4*2**20),quadrature_tables=False)
    rows=[];witness={}
    with journal.measured('actual_H7_few_point_native_full_Ckappa_check'):
        for c in (0,len(old.geometry)//2,len(old.geometry)-1):
            J,o,_=old.geometry[c];pts=np.array([[.21,.37,.43],[.67,.59,.73],[.5,.5,.5]])@J.T+o
            a=old.at(field,c,pts,cfg.k0);b=new.at(field,c,pts,cfg.k0)
            for name in ('E','H','curl'):
                rows.append(dict(cell=c,name=name,relative=relative(a[name]-b[name],a[name])))
                witness[f'{c}_{name}_old']=a[name];witness[f'{c}_{name}_new']=b[name]
    r=dict(rows=rows,pass_gate=all(x['relative']<=1e-11 for x in rows),limit=1e-11,
        arrays=save_arrays(folder/'actual_H7_few_point_witness.npz',**witness))
    write_json(folder/'actual_H7_few_point_check.json',r);return r


def complete_output(r,restored,folder,journal):
    from petsc4py import PETSc
    from .phase_explicit_accuracy_fields import physical_output,analytic
    cfg,setup,geo,field=restored;folder.mkdir(parents=True,exist_ok=True)
    bundle=boundary_bundle(cfg,setup,47,journal)
    if bundle['mode_sha256']!=r['mode_sha256']:raise ValueError('H7 physical mode identity')
    vals=checked_arrays(r['arrays']);v=PETSc.Vec().createSeq(len(vals['u_storage']),comm=PETSc.COMM_SELF);v.array[:]=vals['u_storage']
    try:output=physical_output(bundle,v,vals['port'],geo,folder,journal,volume_backend='direct_phase_quadrature')
    finally:v.destroy()
    pp=selected_points();ids=parents_at(mesh_bounds(field.function_space),pp,interior=False)
    factory=cached_evaluator_factory(limit_bytes=64*2**20,quadrature_tables=False);ev=factory(field.function_space,23,bundle['kappa'])
    selected={n:np.empty((len(pp),3),complex) for n in ('E','H','curl')}
    with journal.measured('fixed_original_240_full_physical_points'):
        for c in np.unique(ids):
            mask=ids==c;values=ev.at(field,int(c),pp[mask],cfg.k0)
            for n in selected:selected[n][mask]=values[n]
    bg=analytic(cfg,pp);witness=dict(points=pp,parent_cells=ids,kappa=bundle['kappa'])
    for n,v in selected.items():witness[n+'_total']=v;witness[n+'_scattered']=v-bg[n]
    output['fixed_240']=save_arrays(folder/'fixed_240_physical_fields.npz',**witness)
    rr=dict(r,output=output,direct_target_pass=max(r['original_audit'][k] for k in ('true','native','augmented','port'))<=1e-10,
        consumer_source=journal.source_state)
    write_json(folder/'completed_saved_physical_state.json',rr)
    return rr


def compare_pair(first,second,a,b,folder,journal):
    from .phase_notch_hp_modes import mode_comparison
    folder.mkdir(parents=True,exist_ok=True);pp=selected_points()
    identity=dict(parent_array_sha256=[first['arrays']['sha256'],second['arrays']['sha256']],
        consumer_field_module_sha256=hashlib.sha256(Path(__file__).with_name('phase_notch_hp_fields.py').read_bytes()).hexdigest())
    factory=cached_evaluator_factory(limit_bytes=256*2**20,quadrature_tables=False)
    results=[]
    for q in (23,31):
        results.append(common_difference(a[3],b[3],b[0],journal,folder,q=q,selected_points=pp,
            evaluator_factory=factory,progress_identity=identity))
        write_json(folder/f'completed_common_q{q}.json',results[-1])
    low,r=results
    qdef=max(abs(low['fields'][key][n]**2-r['fields'][key][n]**2)/max(r['fields'][key]['reference_L2']**2,1e-24)
        for key in r['fields'] for n in ('reference_L2','difference_L2'))
    modes=mode_comparison(first,second,folder)
    power={key:abs(first['output']['port_metrics'][key]-second['output']['port_metrics'][key]) for key in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
    energies=[abs(x['output']['volume_metrics']['energy_closure_error_port_volume']) for x in (first,second)]
    r.update(quadrature_pair=[23,31],quadrature_operation_scaled=qdef,q23_arrays=low['arrays'],modes=modes,
        power_differences=power,energies=energies,**identity)
    r['pass_gate']=r['pass_gate'] and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energies)<=1e-5
    write_json(folder/'comparison.json',r);return r


def independent_state(r,restored,folder,journal,*,regress=False):
    cfg,setup,_,field=restored;v=checked_arrays(r['arrays']);folder.mkdir(parents=True,exist_ok=True)
    mpc=setup['floquets'][r['degree']].mpc
    volume=uncondensed_vectors(field,cfg,v['kappa'],mpc,setup['mesh_data'],folder/'volume_blocks',journal,
        identity=dict(parent_npz_sha256=r['arrays']['sha256']))
    bundle=boundary_bundle(cfg,setup,63,journal)
    out=saved_audit(v,setup,cfg,field,volume,bundle,folder,journal,regression=v if regress else None)
    out.update(parent_array_sha256=r['arrays']['sha256'],consumer_source_sha=journal.source_state['source_sha'])
    write_json(folder/'independent_original_audit.json',out);return out


def saved_closure(folder,journal):
    from src.postprocessing.phase_volume_quadrature import phase_volume_absorption
    from src.common.modes_3d import incident_power_3d
    p=scope.plan_record();records={k:scope.parent(k) for k in ('R7','H7','R6')};restored={}
    for k in ('R7','H7','R6'):
        restored[k]=restore_record(records[k],journal,scope=scope)
        packet=checked_arrays(records[k]['arrays']);cfg,setup,_,field=restored[k]
        from .fixed_phase_fem import carrier
        actual_slaves=np.asarray(setup['floquets'][records[k]['degree']].mpc.slaves)
        masters=np.setdiff1d(np.arange(len(packet['u_storage'])),actual_slaves)
        if not np.array_equal(packet['kappa'],carrier(cfg)) or not np.array_equal(packet['slaves'],actual_slaves):raise ValueError('live saved kappa/MPC identity')
        if not np.array_equal(packet['u_storage'][masters],field.x.array[masters]) or np.any(packet['u_storage'][actual_slaves]!=0):raise ValueError('saved master/slave storage identity')
        journal.event('saved_state_restored_no_factor',role=k,parent=records[k]['arrays']['sha256'])
    c,s,_,f=restored['R7'];sub=folder/'R7_absorption_regression';sub.mkdir(exist_ok=True)
    vm=phase_volume_absorption(s['mesh_data'],c,f,checked_arrays(records['R7']['arrays'])['kappa'],sub,
        incident_power=incident_power_3d(c),port_metrics=records['R7']['output']['port_metrics'],journal=journal)
    reference=records['R7']['output']['volume_metrics']['A_volume_total'];defect=abs(vm['A_volume_total']-reference)/max(abs(reference),1e-30)
    absreg=dict(operation_scaled=defect,absolute_difference=abs(vm['A_volume_total']-reference),denominator=abs(reference),reference=reference,
        measured=vm['A_volume_total'],pass_gate=defect<=1e-10 and vm['quadrature_pass'],volume_result=vm)
    write_json(folder/'R7_absorption_regression.json',absreg)
    h7check=few_point_check(restored['H7'][3],restored['H7'][0],checked_arrays(records['H7']['arrays'])['kappa'],folder,journal)
    if not absreg['pass_gate'] or not h7check['pass_gate']:raise ValueError('no-JIT absorption/native field gate failed; saved scientific records retained')
    h7=complete_output(records['H7'],restored['H7'],folder/'H7_output',journal);records['H7']=h7
    comparisons={}
    for k in ('R7','R6'):
        comparisons[k+'_H7']=compare_pair(records[k],h7,restored[k],restored['H7'],folder/(k+'_H7'),journal)
        write_json(folder/'comparison_progress.json',dict(completed=list(comparisons),pairs={name:row['pass_gate'] for name,row in comparisons.items()}))
    # The independent original-form consumer is separate from the output chain.
    reg=independent_state(records['R7'],restored['R7'],folder/'R7_original_regression',journal,regress=True)
    independent=independent_state(h7,restored['H7'],folder/'H7_original',journal)
    complete=reg['regression']['pass_gate'] and independent['equation_pass'] and independent['recovery_pass']
    r=dict(status='COMPLETED',role='S',H7=h7,R7_absorption=absreg,H7_few_point=h7check,
        comparisons=comparisons,R7_original_regression=reg,H7_independent=independent,complete_saved_closure=complete,
        field_accuracy_pass=comparisons['R7_H7']['pass_gate'],cross_p_diagnostic_pass=comparisons['R6_H7']['pass_gate'],
        new_factor_count=0,new_complete_solves=0,new_raw_tensor_classes=0,timings=journal.timings,calls=journal.calls,
        old_H7_failed_stage_preserved=True,NN_training=0)
    write_json(folder/'minimum_scientific_results.json',r)
    from .phase_target_bridge import target_bridge
    r['target_bridge']=target_bridge(r,folder,journal)
    return r


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V56 live resolved memory binding')
    if role=='S':
        checkpoint=scope.ARTIFACT/'saved_science';checkpoint.mkdir(parents=True,exist_ok=True)
        result=saved_closure(checkpoint,journal);result['science_checkpoint_root']=str(checkpoint)
        return result
    if role=='T6':
        r=solve_case(role,folder,journal,scope=scope);write_json(folder/'completed_before_comparison.json',r)
        if r.get('equation_pass'):
            b=restore_record(r,journal,scope=scope);pairs={}
            for k in ('R6','R7'):
                old=scope.parent(k);a=restore_record(old,journal,scope=scope)
                pairs[k+'_T6']=compare_pair(old,r,a,b,folder/(k+'_T6'),journal)
            r['comparisons']=pairs
            r['independent']=independent_state(r,b,folder/'T6_original',journal)
        r.update(timings=journal.timings,calls=journal.calls);return r
    if role=='VERIFY_COST':
        from benchmarks.collect_phase_saved_closure import check_saved_stage
        s=scope.stage('S');checked=check_saved_stage(s,folder,journal)
        return dict(status='COMPLETED',role=role,checks=checked,all_scientific_vectors_already_independently_consumed=True,
            new_factor_count=0,new_complete_solves=0,timings=journal.timings,calls=journal.calls)
    raise ValueError('V56 explicit stage inventory')
