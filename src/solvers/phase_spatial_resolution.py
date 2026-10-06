"""Thin V55 queue: prior audit, two finite spatial probes, incremental audit."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from . import phase_spatial_resolution_scope as scope
from .scattering_anchor import Journal,save_arrays
from .phase_notch_hp import configured_setup,solve_case,compare_saved,verify_cost
from .phase_notch_hp_capacity import assembly_capacity
from .phase_evaluation_cache import cached_evaluator_factory


def prior_extra(role,r,setup,bundle,field,folder,journal):
    from .phase_tangential_audit import audit_tangential
    from .phase_explicit_accuracy_fields import PhaseEvaluator
    extra={}
    if role in ('R6','R7'):
        extra['tangential']=audit_tangential(field,bundle,folder,role,journal)
        write_json(folder/(role+'_tangential_record.json'),extra['tangential'])
    if role=='R6':
        ev=PhaseEvaluator(field.function_space,15,bundle['kappa'])
        with journal.measured('R6_scattered_envelope_transverse_indicator_once_q15'):
            per=np.asarray([ev.gradient_indicator(field,c,bundle['cfg'].k0)[:2] for c in range(r['case_spec']['cells'])])
        total=per.sum(axis=0);axis=int(np.argmax(total));splits=[1,1,2];splits[axis]=2
        if not np.isfinite(total).all() or np.any(total<0):raise ValueError('finite transverse indicator')
        extra['transverse_indicator']=dict(totals_xy=total,selected_axis=('x','y')[axis],splits=splits,
            parent_array_sha256=r['arrays']['sha256'],q=15,
            rule='sum h_d^2 integral(|d_d u_s|^2+|d_d Henv_s|^2); layered background transverse derivatives zero; exact tie x',
            arrays=save_arrays(folder/'R6_transverse_indicator.npz',per_cell_xy=per,totals_xy=total))
        write_json(scope.window.TMP/'transverse_selection.json',extra['transverse_indicator'])
    return extra


def saved_checker(rows,folder,journal,*,prior=False):
    from benchmarks.collect_phase_notch_hp import saved_checks
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    reader=scope.parent if prior else scope.stage
    states={r['role']:reader(r['role']) for r in rows};states['VERIFY_COST']=dict(rows=rows)
    comparisons={}
    check_scope=scope
    if prior:
        from . import phase_p_order_dtn_scope as previous
        states.update({k:previous.parent(k) for k in ('P','B')})
        comparisons={p.stem:json.loads(p.read_text()) for p in (previous.ARTIFACT/'comparisons').glob('*.json')}
        check_scope=previous  # Only the immutable saved comparison semantics; no old window operation.
    else:
        states.update({k:scope.parent(k) for k in ('R6','R7')})
        comparisons={p.stem:json.loads(p.read_text()) for p in (scope.ARTIFACT/'comparisons').glob('*.json') if p.stem.split('_')[-1] in {r['role'] for r in rows}}
    with journal.measured('independent_saved_array_checker_no_FE_calls'):
        independent,regions,pairs=saved_checks(states,comparisons,scope=check_scope)
    for row in independent:
        if not row['recalculated']['pass_gate'] or not row['direct_internal_target_pass']:raise ValueError('independent saved original equation gate')
    shim=SimpleNamespace(NAMESPACE='v55',window=scope.window,plan_record=scope.plan_record,stage=reader)
    with journal.measured('independent_all_mode_power_recalculation_no_FE_calls'):
        modal=modal_recalculation(scope=shim,role_names=tuple(r['role'] for r in rows),output_folder=folder)
    result=dict(independent_audits=independent,regions=regions,pair_gates=pairs,modal=modal,new_factor_count=0,new_complete_solves=0)
    write_json(folder/'saved_checker.json',result)
    return result


def preflight(folder,journal):
    if not scope.stage('Q0')['pass_gate']:raise RuntimeError('prior audit not qualified')
    p=scope.plan_record();mem=p['memory_budget'];capacities={};forecasts={}
    from .hcurl_assembly_time_condensation import _canonical_axis_aligned_coordinates
    from .phase_tensor_checkpoint import RawTensorCheckpoint
    for role in scope.SOLVES:
        spec=scope.case_spec(role);cfg,setup,geo=configured_setup(spec,journal,scope=scope)
        cap=assembly_capacity(setup,cfg,journal,spec,planning_limit_bytes=64*2**30,sampled_stop_bytes=96*2**30,
            extra_workspace_bytes=mem['extra_cache_workspace_gib']*2**30,row_cap=p['assembly_row_cap'])
        capacities[role]=cap
        keys=set()
        for c,tag in enumerate(setup['mesh_data'].cell_tags.values):
            coords,_=_canonical_axis_aligned_coordinates(setup['mesh'],c,tolerance=1e-11,geometry_identity_policy='raw_unrounded')
            keys.add(RawTensorCheckpoint.key(coords,tag))
        parent_names=('p7',) if role=='H7' else ('p6_Z2','p6_Z4');known=set();timing_samples=[]
        for name in parent_names:
            contract=p['raw_tensor_parents'][name];path=scope.ROOT/contract['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=contract['sha256']:raise ValueError('raw forecast manifest identity')
            known.update(row['key'] for row in json.loads(path.read_text())['classes'] if row['degree']==spec['degree'])
            historical=json.loads(path.with_name('manifest.json').parent.parent.joinpath('result.json').read_text())
            timing_samples.extend(v for k,v in historical.get('timings',{}).items() if k.startswith('raw_exact_tensor_class_'))
        forecasts[role]=dict(actual_unique_classes=len(keys),geometry_tag_key_hits=len(keys&known),geometry_tag_key_misses=len(keys-known),
            qualification='geometry/tag preliminary only; live full form/Basix/kappa gate remains mandatory',
            keys_sha256=hashlib.sha256(repr(sorted(keys)).encode()).hexdigest(),parent_contracts=[p['raw_tensor_parents'][n] for n in parent_names],
            historical_class_seconds=timing_samples,
            predicted_missing_raw_seconds=(len(keys-known)*float(np.median(timing_samples))) if timing_samples else 'unknown',
            predicted_missing_raw_conservative_seconds=(len(keys-known)*max(timing_samples)) if timing_samples else 'unknown',
            estimate_not_numeric_admission=True)
        write_json(folder/(role+'_preflight.json'),dict(capacity=cap,raw_forecast=forecasts[role],case_spec=spec))
        del setup,cfg,geo
    return dict(status='COMPLETED',role='SETUP',pass_gate=True,capacities=capacities,raw_forecasts=forecasts,
        planning_GiB=64,warning_GiB=80,sampled_stop_GiB=96,assembly_row_cap=100000,new_factor_count=0,new_complete_solves=0,timings=journal.timings,calls=journal.calls)


def finish_comparisons(role,r,journal):
    cache=scope.ARTIFACT/'comparisons';cache.mkdir(exist_ok=True);items=[]
    for left in scope.plan_record()['comparison_partners'][role]:
        old=scope.parent(left);path=cache/(left+'_'+role+'.json')
        if path.exists():
            pair=json.loads(path.read_text())
            if pair['parent_array_sha256']!=[old['arrays']['sha256'],r['arrays']['sha256']]:raise ValueError('V55 saved pair changed')
        else:
            folder=cache/(left+'_'+role+'_'+journal.folder.name);folder.mkdir()
            pair=compare_saved(old,r,folder,journal,scope=scope,evaluator_factory=cached_evaluator_factory())
            write_json(path,pair)
        items.append(dict(pair=[left,role],comparison_path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pass_gate=pair['pass_gate'],
            purpose='same-p h qualification' if (left,role) in (('R7','H7'),('R6','T6')) else 'cross-p disagreement diagnostic'))
    return items


def execute(role,folder,state):
    p=scope.plan_record();journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=p['memory_budget']:raise ValueError('V55 actual resource binding')
    if role=='Q0':
        freeze=p['prior_queue_freeze'];path=scope.ROOT/freeze['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=freeze['sha256']:raise ValueError('V54 closed queue identity')
        r=verify_cost(folder,journal,scope=scope,inventory_path=scope.verification_inventory_for(role),read_state=scope.parent,after_state=prior_extra,output_role=role)
        write_json(folder/'prior_FE_audit_completed.json',r)
        r['saved_checker']=saved_checker(r['rows'],folder,journal,prior=True);r['saved_checker_pass']=True
        r['pass_gate']=all(x['equation_pass'] and x.get('additional_checks',{}).get('tangential',{'pass_gate':True})['pass_gate'] for x in r['rows'])
        r.update(timings=journal.timings,calls=journal.calls)
        return r
    if role=='SETUP':return preflight(folder,journal)
    if role in scope.SOLVES:
        r=solve_case(role,folder,journal,scope=scope);write_json(folder/'completed_before_comparison.json',r)
        if r.get('equation_pass'):r['comparisons']=finish_comparisons(role,r,journal)
        r.update(timings=journal.timings,calls=journal.calls);return r
    if role.startswith('AUDIT_') or role=='VERIFY_COST':
        r=verify_cost(folder,journal,scope=scope,inventory_path=scope.verification_inventory_for(role),output_role=role)
        write_json(folder/'independent_FE_audit_completed.json',r)
        r['saved_checker']=saved_checker(r['rows'],folder,journal) if r['rows'] else dict(independent_audits=[],all_prior_new_states_already_audited=True)
        r['saved_checker_pass']=True;r['pass_gate']=all(x['equation_pass'] for x in r['rows'])
        r.update(timings=journal.timings,calls=journal.calls);return r
    raise ValueError('V55 stage inventory')
