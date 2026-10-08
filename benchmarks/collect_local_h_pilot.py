"""V64 frozen saved-field consumers and compact cost records; no factor."""
import gc
import json
import os
from pathlib import Path
from types import SimpleNamespace
from src.runners.task042_shared import write_json
from src.solvers import local_h_pilot_scope as scope
from src.solvers.scattering_anchor import save_arrays,relative
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers import independent_tetra_reference as core
from benchmarks.collect_independent_tetra import restored,saved_output_check,digest


def verify(folder,journal):
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.independent_tetra_fields import tangential_check
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers import fine_tetra_scope as prior
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    path=scope.window.TMP/'scientific_queue_frozen.json';frozen=json.loads(path.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(path):raise ValueError('V64 frozen live inventory')
    states={};checks={};pairs={}
    for role,item in frozen['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=item['array_sha256']:raise ValueError('V64 frozen field changed')
        states[role]=r;sub=folder/role;sub.mkdir(exist_ok=True)
        s,v,field=restored(r,journal);b=load_boundary(s,r['boundary_arrays'],r['mode_sha256'],q='q63')
        audit,res,rhs=core.audit(s,b,v['x'],v['rhs'],journal)
        arrays=save_arrays(sub/'independent_original.npz',residual=res,rhs=rhs,action=rhs-res,x=v['x'])
        previous=checked_arrays(r['audit']['arrays']);op=relative(res-previous['residual'],rhs)
        tangent=tangential_check(s,field,sub);output=saved_output_check(r)
        checks[role]=dict(original=audit,arrays=arrays,producer_consumer_operation=op,tangential=tangent,output=output,
            pass_gate=audit['pass_gate'] and op<=1e-10 and tangent['pass_gate'] and output['pass_gate'])
        write_json(sub/'checker.json',checks[role]);write_json(folder/'state_inventory.json',checks)
        del s,v,field,b;gc.collect()
    shim=SimpleNamespace(NAMESPACE='v61',window=scope.window,plan_record=scope.plan_record,stage=lambda r:dict(states[r],case_spec=states[r]['spec']))
    modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder)
    endpoints={r:prior.stage(r) for r in ('A','B')};endpoints.update(states)
    for a,b in [('B','P6'),('A','L4'),('B','L4'),('P6','L4')]:
        if b not in states or a not in endpoints:continue
        p=comparison(endpoints[a],states[b],folder/(a+'_'+b),journal)
        pairs[a+'_'+b]=p;write_json(folder/'comparison_progress.json',pairs)
    efficiency={}
    if 'P6' in states:
        a_p=comparison(endpoints['A'],states['P6'],folder/'efficiency_A_P6',journal)
        ref=checked_arrays(states['P6']['output']['integrals'][-1]['arrays'])['per_cell_analytic_squared'].sum(axis=0)[:2,0]
        for name,p in [('A',a_p),('B',pairs.get('B_P6')),('L4',pairs.get('P6_L4'))]:
            if p is not None:
                efficiency[name]={key:(p['fields'][key]['difference_squared']/max(float(ref[i]),1e-24))**.5 for i,key in enumerate(('E_scattered','H_scattered'))}
        efficiency['P6_reference_squared']=ref;efficiency['A_P6_arrays']=a_p['arrays']
    partial=None
    if not states and (scope.window.TMP/'P6_case_reserve_stop.json').exists():
        from benchmarks.check_tetra_preparation import partial_saved_check
        partial=partial_saved_check(scope,folder,journal)
    result=dict(status='COMPLETED' if states else 'NO_NEW_RETURNED_FIELDS',checks=checks,comparisons=pairs,efficiency_fixed_P6=efficiency,modal=modal,
        partial_preparation=partial,full_field_qualification=bool(states) and all(c['pass_gate'] for c in checks.values()),
        new_numeric_factors=0,new_complete_solves=0,NN_training=0,NN20=False,target_qualified=False,source=journal.source_state)
    write_json(folder/'verification_scientific_result.json',result);return result


def collect():
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    from benchmarks.collect_fine_tetra import deployment_accounting
    from benchmarks.check_independent_tetra import saved_pair
    from src.solvers.independent_tetra_fields import selected_points
    from src.solvers import fine_tetra_scope as prior
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir(exist_ok=True)
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()};lifecycle={}
    for role in scope.SOLVES:
        r=stages.get(role,{})
        if not r.get('arrays'):continue
        path=Path(r['arrays']['path']).parent
        events=[json.loads(line) for line in (path/'events.jsonl').read_text().splitlines()]
        receipts=[dict(path=str(p),sha256=digest(p),**json.loads(p.read_text())) for p in scope.window.TMP.glob(role+'_one_run*/receipt.json')]
        lifecycle[role]=dict(nnz=r['nnz'],actual_FE=r['spec']['independent'],actual_rows=r['spec']['rows'],actual_native=r['arrays']['members']['u_native']['shape'][0],
            capacity=r['capacity'],symbolic=json.loads((path/'h_symbolic_capacity.json').read_text()),numeric=json.loads((path/'h_numeric_factor_info.json').read_text()),
            deployment=deployment_accounting(receipts,r),global_finite_LU_present=True,static_condensation=False,
            solution_bytes=Path(r['arrays']['path']).stat().st_size,
            ownership_and_release=[e for e in events if e['event'] in ('object_owner_snapshot','global_finite_factor_released','global_body_augmented_and_factor_released')],
            boundary_bytes={q:Path(a['path']).stat().st_size for q,a in r['boundary_arrays'].items()})
    checks={}
    if 'VERIFY_COST' in stages:
        parents={**{r:prior.stage(r) for r in ('A','B')},**stages}
        for name,p in stages['VERIFY_COST']['comparisons'].items():
            a,b=name.split('_');checks[name]=saved_pair(p,parents[a],parents[b],expected_points=selected_points(parents[b]['physical']))
            if not checks[name]['published_gate_matches_recalculation']:raise ValueError('V64 independent saved verdict mismatch')
    data=dict(run_index_v64=dict(runs=runs,pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}),
        scientific_checks_v64=dict(stages=stages,NN20=False,continuum_accuracy=False,target_qualified=False),
        resource_costs_v64=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),charged_known_lower_seconds=scope.window.charged_wall(),historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],historical_unknown='preserved',nominal_sampling_seconds=.5,sampled_peak_not_continuous_hard_peak=True),
        storage_lifecycle_deployment_v64=dict(cases=lifecycle,L4_prerequisite_A_B_costs='V63 deployment receipts; not free'),
        independent_saved_pair_checks_v64=dict(pairs=checks,new_numeric=0,new_solve=0,
            field_checks_run=bool(checks),partial_preparation=stages.get('VERIFY_COST',{}).get('partial_preparation')),
        repair_journal_v64=dict(entries=[json.loads(line) for line in (scope.window.TMP/'repair_journal.jsonl').read_text().splitlines()],failures_preserved=True))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V64_COMPACT_COSTS',runs=len(runs),records=len(data))))


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v62.md',response_name='response_v64.md',outcome_name='p6_reference_local_h_v64.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V64 collector arguments')
