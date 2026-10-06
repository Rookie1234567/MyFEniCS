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
            new_r=rhs.array-out.array;old_r=old['residual'];load_delta=rhs.array-old['rhs']
            old_boundary=old['coupling_action'];boundary_delta=dtn.array-old_boundary
            volume_delta=volume-old['volume_action']
            action_delta=volume_delta+boundary_delta
            defect=(new_r-old_r)-(load_delta-action_delta)
            scale=max(np.linalg.norm(new_r)+np.linalg.norm(old_r)+np.linalg.norm(load_delta)+np.linalg.norm(action_delta),1e-30)
            operation=float(np.linalg.norm(defect)/scale)
            volume_operation=relative(volume_delta,old['volume_action'])
            witness=save_arrays(folder/'old_field_changed_inventory_residual.npz',
                new_residual=new_r,old_residual=old_r,load_delta=load_delta,boundary_delta=boundary_delta,
                volume_delta=volume_delta,action_delta=action_delta,identity_defect=defect,
                rhs_new=rhs.array.copy(),rhs_old=old['rhs'],u_unchanged=src.array.copy())
        if operation>1e-10 or volume_operation>1e-10:raise ValueError('mode-only original volume/residual identity')
        projected['finite_mode_projection']['residual_identity']=dict(operation=operation,numerator=float(np.linalg.norm(defect)),
            denominator=float(scale),volume_operation=volume_operation,arrays=witness,
            new_rho=float(np.linalg.norm(new_r)/max(np.linalg.norm(rhs.array),1e-30)),
            load_delta_norm=float(np.linalg.norm(load_delta)),boundary_delta_norm=float(np.linalg.norm(boundary_delta)),
            complex_cross_load_action=[float(np.vdot(load_delta,action_delta).real),float(np.vdot(load_delta,action_delta).imag)],
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
        from .phase_p_order_consistency import diagnose
        return diagnose(folder,journal,scope)
    if role in scope.SOLVES:
        result=solve_case(role,folder,journal,scope=scope)
        write_json(folder/'completed_before_comparison.json',result)
        if result.get('equation_pass'):result['comparisons']=finish_comparisons(role,result,journal)
        result.update(timings=journal.timings,calls=journal.calls)
        return result
    if role=='VERIFY_COST':return verify_cost(folder,journal,scope=scope)
    raise ValueError('V54 explicit stage inventory')
