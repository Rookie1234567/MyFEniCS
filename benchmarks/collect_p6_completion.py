"""Frozen saved P6 coefficients and complete field/cost evidence, no factor."""
import gc
import json
import os
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers import p6_completion_scope as scope
from src.solvers.scattering_anchor import save_arrays,relative
from src.solvers.scattering_anchor_checks import checked_arrays
from benchmarks.collect_independent_tetra import restored,saved_output_check,digest


def verify(folder,journal):
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.independent_tetra_fields import tangential_check
    from src.solvers.tetra_coefficient_action import CoefficientFullAction
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers import fine_tetra_scope as parent
    path=scope.window.TMP/'scientific_queue_frozen.json';frozen=json.loads(path.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(path):raise ValueError('V65 frozen live inventory')
    if not frozen['states']:
        return dict(status='NO_RETURNED_FIELD',new_numeric_factors=0,new_complete_solves=0,field_accuracy='NOT_RUN',target_qualified=False)
    r=scope.stage('SOLVE_COMPLETE')
    if r['arrays']['sha256']!=frozen['states']['P6']['array_sha256']:raise ValueError('V65 frozen field changed')
    s,v,field=restored(r,journal);b=load_boundary(s,r['boundary_arrays'],r['mode_sha256'],'q63')
    action=CoefficientFullAction(s,b,17)
    audit,res,rhs=action.audit(v['x'],v['rhs'],journal)
    arrays=save_arrays(folder/'independent_original.npz',residual=res,rhs=rhs,action=rhs-res,x=v['x'])
    old=checked_arrays(r['audit']['arrays']);op=relative(res-old['residual'],rhs)
    tangent=tangential_check(s,field,folder);output=saved_output_check(r)
    check=dict(original=audit,arrays=arrays,producer_consumer_operation=op,tangential=tangent,output=output,
        pass_gate=audit['pass_gate'] and op<=1e-10 and tangent['pass_gate'] and output['pass_gate'])
    write_json(folder/'P6_saved_checker.json',check)
    del s,v,field,b,action;gc.collect()
    # Frozen coefficients precede reference scoring; only this single pair.
    B=parent.stage('B');pair=comparison(B,r,folder/'B_P6',journal)
    from benchmarks.check_independent_tetra import saved_pair
    from src.solvers.independent_tetra_fields import selected_points
    independently=saved_pair(pair,B,r,expected_points=selected_points(r['physical']))
    if not independently['published_gate_matches_recalculation']:raise ValueError('B/P6 saved-array checker verdict')
    result=dict(status='COMPLETED',checks={'P6':check},comparisons={'B_P6':pair},independent_pair=independently,
        new_numeric_factors=0,new_complete_solves=0,full_field_qualification=check['pass_gate'],
        finite_p5_p6_increment_pass=pair['pass_gate'],continuum_accuracy=False,target_qualified=False,NN20=False,
        source=journal.source_state,timings=journal.timings)
    write_json(folder/'verification_scientific_result.json',result);return result


def collect():
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir(exist_ok=True)
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    data=dict(run_index_v65=dict(runs=runs,pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}),
        scientific_checks_v65=dict(stages=stages,continuum_accuracy=False,target_qualified=False,NN20=False),
        resource_costs_v65=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),
            charged_known_lower_seconds=scope.window.charged_wall(),cumulative_P6_case_seconds=scope.window.case_used(),
            historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],historical_unknown='preserved',
            nominal_sampling_seconds=.5,sampled_peak_not_continuous_hard_peak=True),
        repair_journal_v65=dict(entries=[json.loads(line) for line in (scope.window.TMP/'repair_journal.jsonl').read_text().splitlines()],failures_preserved=True))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V65_COMPACT_COSTS',runs=len(runs),records=len(data))))


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v63.md',response_name='response_v65.md',outcome_name='coefficient_first_p6_completion_v65.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V65 collector arguments')
