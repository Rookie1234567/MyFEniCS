"""Thin V54 physical queue, fixed p and finite DtN increments."""
import hashlib
import json
import numpy as np
from src.runners.task042_shared import write_json
from . import phase_p_order_dtn_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .phase_notch_hp import solve_case,compare_saved,verify_cost
from .phase_evaluation_cache import cached_evaluator_factory


def residual_inventory_identity(old_rhs,new_rhs,old_r,new_r,old_volume,new_volume,old_boundary,new_boundary):
    """Use assembled original terms, not the small difference as a scale."""
    load_delta=new_rhs-old_rhs;volume_delta=new_volume-old_volume;boundary_delta=new_boundary-old_boundary
    action_delta=volume_delta+boundary_delta;defect=(new_r-old_r)-(load_delta-action_delta)
    denominator=sum(np.linalg.norm(v) for v in (old_rhs,new_rhs,old_volume,new_volume,old_boundary,new_boundary))
    result_denominator=sum(np.linalg.norm(v) for v in (old_r,new_r,load_delta,action_delta))
    return dict(load_delta=load_delta,volume_delta=volume_delta,boundary_delta=boundary_delta,
        action_delta=action_delta,identity_defect=defect),dict(operation=float(np.linalg.norm(defect)/max(denominator,1e-30)),
        numerator=float(np.linalg.norm(defect)),denominator=float(denominator),
        result_scale_diagnostic=float(np.linalg.norm(defect)/max(result_denominator,1e-30)),result_denominator=float(result_denominator))


def project_with_residual_identity(parent,bundle,rhs,geometry,folder,journal):
    from .phase_notch_hp_modes import project_saved_parent
    from petsc4py import PETSc
    projected=project_saved_parent(parent,bundle,geometry,folder,journal)
    old=checked_arrays(parent['arrays']);src=PETSc.Vec().createSeq(len(old['u_storage']),comm=PETSc.COMM_SELF)
    src.array[:]=old['u_storage'];out=src.duplicate();dtn=src.duplicate()
    try:
        with journal.measured('unchanged_parent_new_closed_original_residual'):
            bundle['physical_action'].apply(src,out);journal.calls['A']+=1
            volume=bundle['volume_action'].apply(src).array.copy()
            bundle['dtn_action'].apply(src,dtn)
            # Old native residual closes the port exactly. Its saved explicit
            # auxiliary coefficients have a small, separately audited defect.
            # Reconstruct the same CLOSED old boundary, pairing physical keys.
            payload=json.loads(__import__('pathlib').Path(parent['output']['fields']['path']).with_name('port_power.json').read_text())
            keys=lambda r:(r['side'],r['m'],r['n'],r['polarization'])
            entries={keys(e.mode_identity):e for e in bundle['dtn_action'].carrier.entries}
            old_boundary=np.zeros_like(volume)
            for i,row in enumerate(payload['orders']):
                e=entries[keys(row)];np.add.at(old_boundary,e.coupling_rows,e.coupling_values*old['projected'][i]/old['H'][i])
            new_r=rhs.array-out.array;old_r=old['residual']
            terms,metrics=residual_inventory_identity(old['rhs'],rhs.array,old_r,new_r,old['volume_action'],volume,old_boundary,dtn.array)
            volume_operation=relative(terms['volume_delta'],old['volume_action'])
            witness=save_arrays(folder/'old_field_changed_inventory_residual.npz',
                new_residual=new_r,old_residual=old_r,**terms,old_closed_boundary=old_boundary,new_closed_boundary=dtn.array.copy(),
                old_explicit_auxiliary_boundary=old['coupling_action'],old_volume=old['volume_action'],new_volume=volume,
                rhs_new=rhs.array.copy(),rhs_old=old['rhs'],u_unchanged=src.array.copy())
        if metrics['operation']>1e-10 or volume_operation>1e-10:raise ValueError('mode-only original volume/residual identity')
        projected['finite_mode_projection']['residual_identity']=dict(**metrics,volume_operation=volume_operation,arrays=witness,
            new_rho=float(np.linalg.norm(new_r)/max(np.linalg.norm(rhs.array),1e-30)),
            load_delta_norm=float(np.linalg.norm(terms['load_delta'])),boundary_delta_norm=float(np.linalg.norm(terms['boundary_delta'])),
            old_closed_auxiliary_defect_norm=float(np.linalg.norm(old_boundary-old['coupling_action'])),
            complex_cross_load_action=[float(np.vdot(terms['load_delta'],terms['action_delta']).real),float(np.vdot(terms['load_delta'],terms['action_delta']).imag)],
            qualification='OFFLINE_UNCHANGED_FIELD_NEW_BOUNDARY_DIAGNOSTIC; not a new solve')
        return projected
    finally:src.destroy();out.destroy();dtn.destroy()


def finish_comparisons(role,result,journal):
    cache=scope.ARTIFACT/'comparisons';cache.mkdir(exist_ok=True);rows=[]
    for left in scope.plan_record()['comparison_partners'][role]:
        previous=result['projected_parent828'] if (left,role) in (('B','R7'),('P','R6'),('R7','C')) else scope.read(left)
        if not previous.get('equation_pass'):continue
        name=left+'_'+role;path=cache/(name+'.json')
        if path.exists():
            r=json.loads(path.read_text())
            if r['parent_array_sha256']!=[previous['arrays']['sha256'],result['arrays']['sha256']]:raise ValueError('V54 pair cache identity')
        else:
            sub=cache/(name+'_'+journal.folder.name);sub.mkdir(exist_ok=False)
            r=compare_saved(previous,result,sub,journal,scope=scope,evaluator_factory=cached_evaluator_factory())
            write_json(path,r)
        rows.append(dict(pair=[left,role],comparison_path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pass_gate=r['pass_gate']))
    return rows


def execute(role,folder,state):
    p=scope.plan_record();journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=p['memory_budget']['planning_gib']*2**30)
    journal.source_state=state
    if state.get('memory_budget')!=p['memory_budget']:raise ValueError('V54 live numerical memory contract')
    if role=='D':
        from .phase_p_order_consistency import diagnose,recheck_saved_operation_scale
        if state.get('postprocessing_resume'):return recheck_saved_operation_scale(folder,journal,scope,state)
        return diagnose(folder,journal,scope)
    if role in scope.SOLVES:
        result=solve_case(role,folder,journal,scope=scope)
        write_json(folder/'completed_before_comparison.json',result)
        if result.get('equation_pass'):result['comparisons']=finish_comparisons(role,result,journal)
        result.update(timings=journal.timings,calls=journal.calls)
        return result
    if role=='VERIFY_COST':return verify_cost(folder,journal,scope=scope)
    raise ValueError('V54 explicit stage inventory')
