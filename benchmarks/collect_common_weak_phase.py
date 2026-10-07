"""V57 independent saved-array verdicts and compact incremental accounting."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import common_weak_phase_scope as scope
from src.solvers.scattering_anchor import relative
from src.solvers.scattering_anchor_checks import checked_arrays


def reproduction_check(pair):
    thresholds=dict(fields=1e-6,selected=1e-6,channels=1e-6,power=1e-8,mode_power=1e-9,q=1e-10)
    measures=dict(fields=max(x['relative'] for x in pair['fields'].values()),
        selected=max(pair['selected'].values()),channels=pair['modes']['outgoing_amplitude_at_boundary_relative'],
        power=max(pair['power_differences'].values()),mode_power=pair['modes']['mode_power_max_absolute'],
        q=pair['quadrature_operation_scaled'])
    return dict(measured=measures,limits=thresholds,pass_gate=all(np.isfinite(v) and v<=thresholds[k] for k,v in measures.items()))


def weak_check(r,*,frozen_scales=None):
    out=[]
    for row in r['rows']:
        v=checked_arrays(row['arrays']);terms=v['terms'];res=terms[6]-terms[:6].sum(axis=0)
        if terms.shape!=(7,24) or v['permode_DtN'].shape!=(828,24):raise ValueError('continuous full test/mode inventory')
        if relative(res-v['residual'],np.maximum(np.abs(terms).sum(axis=0),1e-300))>1e-12:raise ValueError('continuous complex residual sum')
        if relative(v['region_terms'].sum(axis=0)-terms[:5],terms[:5])>1e-12:raise ValueError('continuous material contribution sum')
        if relative(v['permode_DtN'].sum(axis=0)-terms[5],terms[5])>1e-12:raise ValueError('continuous 828 boundary sum')
        if not np.allclose(v['fixed_scaled'],np.abs(res)/v['fixed_scale'],rtol=1e-13,atol=1e-300):raise ValueError('common fixed scale')
        if not np.all(np.isfinite(v['fixed_scale'])) or np.any(v['fixed_scale']<=0):raise ValueError('nonpositive continuous scale')
        if frozen_scales is not None and row['q'] in frozen_scales and not np.allclose(v['fixed_scale'],frozen_scales[row['q']],rtol=1e-13,atol=0):raise ValueError('four candidates must share the frozen background scale')
        out.append(dict(q=row['q'],maximum_fixed_scaled=float(np.max(np.abs(res)/v['fixed_scale'])),
            maximum_absolute=float(np.max(np.abs(res))),arrays_sha256=row['arrays']['sha256']))
    return out


def diagnostic_check(r):
    if r.get('status')!='COMPLETED' or set(r['states'])!={'R6','T6','R7','H7'} or len(r['design']['functions'])!=24:raise ValueError('complete frozen continuous study inventory')
    control=r['analytic_control'];scales={};control_rows=weak_check(control)
    for row in control['rows']:
        v=checked_arrays(row['arrays']);scales[row['q']]=v['fixed_scale']
        perturb=v['residual']-v['perturbation_terms'].sum(axis=0)
        if not np.allclose(perturb,v['perturbation_residual'],rtol=1e-13,atol=1e-25):raise ValueError('analytic nonzero perturbation balance')
        if np.max(np.abs(v['residual'])/v['fixed_scale'])>1e-10:raise ValueError('analytic FLAT formula control')
        if np.max(np.abs(v['perturbation_terms'].sum(axis=0)))<=1e-10*np.max(v['fixed_scale']):raise ValueError('zero-return diagnostic not detected')
    return dict(control=control_rows,states={key:weak_check(v,frozen_scales=scales) for key,v in r['states'].items()},
        full_field_accuracy_certificate=False)


def tensor_check(k):
    out={}
    for degree in k['degrees']:
        if degree['status']!='COMPLETED':out[str(degree['degree'])]=dict(status=degree['status']);continue
        rows=[]
        for row in degree['rows']:
            new=checked_arrays(row['arrays']);old=checked_arrays(row['raw_parent'])['tensor'];delta=new['new_tensor']-old
            values=dict(relative=relative(delta,old),operation=float(np.linalg.norm(delta)/float(new['operation_scale'])),
                old_action=relative(old@new['directions']-new['old_action'],new['old_action']),
                new_action=relative(new['new_tensor']@new['directions']-new['new_action'],new['new_action']))
            values['pass_gate']=values['relative']<=1e-10 and values['operation']<=1e-12 and max(values['old_action'],values['new_action'])<=1e-12
            rows.append(values)
        recoveries=[]
        for rec in degree['recoveries']:
            v=checked_arrays(rec['arrays']);matrix=checked_arrays(rec['combined_tensor'])['new_tensor'];i=v['internal_rows'];t=v['trace_rows'];co=v['actual_coefficients']
            residual=matrix[np.ix_(i,i)]@v['recovered_internal']+matrix[np.ix_(i,t)]@co[t]-v['internal_rhs']
            defect=relative(v['recovered_internal']-co[i],co[i]);operation=relative(residual,v['internal_rhs'])
            recoveries.append(dict(relative=defect,residual=operation,pass_gate=defect<=1e-10 and operation<=1e-10))
        out[str(degree['degree'])]=dict(rows=rows,recoveries=recoveries,pass_gate=all(x['pass_gate'] for x in rows+recoveries))
    if sum(len(v.get('recoveries',[])) for v in out.values())>2:raise ValueError('two actual recovery witness limit')
    return out


def verify(folder,journal):
    from benchmarks.collect_phase_saved_closure import vector_check
    from benchmarks.collect_phase_notch_hp import saved_checks
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    freeze=scope.window.TMP/'scientific_queue_frozen.json';f=json.loads(freeze.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=hashlib.sha256(freeze.read_bytes()).hexdigest():raise ValueError('frozen V57 inventory identity')
    out={}
    for role,item in f['completed_solves'].items():
        r=scope.stage(role)
        if item['array_sha256']!=r['arrays']['sha256']:raise ValueError('actual frozen solve changed')
        sub=Path(folder)/role;sub.mkdir(exist_ok=True)
        with journal.measured(role+'_independent_saved_checker'):
            vectors=vector_check(r['independent']['arrays'])
            states={role:r};states.update({x:scope.parent(x) for x in scope.plan_record()['comparison_partners'][role]})
            _,regions,gates=saved_checks(states,r['comparisons'],scope=scope)
            shim=SimpleNamespace(NAMESPACE='v57',window=scope.window,plan_record=scope.plan_record,stage=lambda _:r)
            modes=modal_recalculation(scope=shim,role_names=(role,),output_folder=sub)
            row=dict(original=vectors,regions=regions,gates=gates,modes=modes)
            if role=='B6':row['backend_reproduction']=reproduction_check(r['comparisons']['R6_B6'])
            if r.get('weak_balance'):row['weak_balance']=weak_check(r['weak_balance'])
            out[role]=row;write_json(sub/'independent_checker.json',row)
    for role,fn in (('D',diagnostic_check),('K',tensor_check)):
        if (scope.ARTIFACT/(role+'.json')).exists():out[role]=fn(scope.stage(role))
    return dict(status='COMPLETED',role='VERIFY_COST',checks=out,new_FE_calls=0,new_factor_count=0,new_complete_solves=0)


def collect():
    from benchmarks.collect_phase_notch_hp import measured_timeline,sampling_receipt
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    costs=[];sources={};bindings=[]
    for r in scope.window.ledger()['runs']:
        d=Path(r['folder']);manifest=json.loads((d/'run_manifest.json').read_text());sources[r['source_sha']]=manifest['implementation_hashes']
        summary=d/('run_summary.json' if (d/'run_summary.json').exists() else 'summary.json')
        if not summary.exists():summary=d/'launcher_failure.json'
        s=json.loads(summary.read_text())
        worker=scope.ARTIFACT/d.name
        costs.append(dict(role=r['role'],folder=str(d),source_sha=r['source_sha'],classification=r['classification'],
            supervised_seconds=r['elapsed_seconds'],launch_seconds=s['launch_wall_seconds'],peak_bytes=r['peak_bytes'],swap_bytes=r['swap_bytes'],
            sampling=sampling_receipt(d/'supervision/resources.jsonl') if (d/'supervision/resources.jsonl').exists() else dict(status='NOT_MEASURED_NO_WORKER_STARTED'),
            disjoint_timing=measured_timeline(worker/'events.jsonl') if (worker/'events.jsonl').exists() else {},
            before_supervisor_resource_status=r.get('resource_measurement_status','measured sampled tree')))
        if (d/'resolved_config.json').exists():bindings.append(dict(role=r['role'],source_sha=r['source_sha'],input_sha256=manifest['input_sha256'],
            physical_sha256=manifest['physical_sha256'],resolved_sha256=hashlib.sha256((d/'resolved_config.json').read_bytes()).hexdigest(),memory=manifest['memory_budget']))
    pointers={role:json.loads((scope.ARTIFACT/(role+'.json')).read_text()) for role in scope.STAGES if (scope.ARTIFACT/(role+'.json')).exists()}
    for name,value in [('run_index_v57',dict(runs=scope.window.ledger()['runs'],pointers=pointers)),
        ('resource_costs_v57',dict(runs=costs,charged_lower_seconds=scope.window.charged_wall(),historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],
            historical_unknown='preserved; no manufactured exact old bill',source_hashes=sources,bindings=bindings,clock=scope.window.snapshot())),
        ('stage_verdicts_v57',{role:dict(status=scope.stage(role)['status'],source_sha=scope.stage(role).get('source_sha'),
            result=pointers[role]) for role in pointers})]:write_json(out/(name+'.json'),value)
    print(json.dumps(dict(status='V57_COMPACT_EVIDENCE_COLLECTED',records=str(out))))


if __name__=='__main__':collect()
