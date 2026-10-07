"""One frozen new-space verification and compact incremental V61 costs."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from src.runners.task042_shared import write_json
from src.solvers import face_trace_scope as scope


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(folder,journal):
    from benchmarks.collect_local_subcell import macro_saved_check,comparison
    from benchmarks.collect_common_weak_phase import output_check
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    from benchmarks.collect_phase_notch_hp import saved_checks
    p=scope.window.TMP/'scientific_queue_frozen.json';f=json.loads(p.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(p):raise ValueError('V61 actual frozen consumer identity')
    states={'H2':scope.parent('H2')};checks={}
    for role,row in f['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=row['array_sha256']:raise ValueError('frozen face coefficients changed')
        checks[role]=dict(mixed_original=macro_saved_check(r),physical_outputs=output_check(r));states[role]=r
        write_json(folder/(role+'_saved_checks.json'),checks[role])
    shim=SimpleNamespace(NAMESPACE='v61',window=scope.window,plan_record=scope.plan_record,stage=lambda role:states[role])
    modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder)
    pairs={}
    for key,a,b in [('H2_FX','H2','FX'),('FX_FXY','FX','FXY'),('H2_FXY','H2','FXY')]:
        if a in states and b in states:
            pairs[key]=comparison(states[a],states[b],folder/key,journal,live_scope=scope)
            write_json(folder/'incremental_pair_index.json',pairs)
    _,regions,gates=saved_checks(states,pairs,scope=scope)
    for name,pair in pairs.items():
        gate=gates[name];passed=gate['field_max']<=1e-4 and gate['selected_max']<=1e-4 and gate['modal']['outgoing_amplitude_at_boundary_relative']<=1e-4 and gate['modal']['mode_power_max_absolute']<=1e-6 and max(gate['power'].values())<=1e-5 and max(gate['energies'])<=1e-5 and gate['quadrature_operation']<=1e-10
        if bool(passed)!=bool(pair['pass_gate']):raise ValueError('V61 independent saved comparison gate mismatch')
    r=dict(status='COMPLETED',role='VERIFY_COST',checks=checks,pairs=pairs,regions=regions,saved_pair_gates=gates,modal=modal,
        new_factor_count=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings)
    write_json(folder/'verification_scientific_result.json',r);return r


def deployment_receipt(role):
    p=scope.window.TMP/(role+'_one_run/receipt.json')
    if not p.exists():return dict(status='unknown',reason='no outer process receipt')
    r=json.loads(p.read_text());s=scope.stage(role)
    return dict(status='measured_complete_prepared_start' if r['exit_code']==0 and s.get('deployment_complete') else 'partial',
        T_N1_prepared_start_process_seconds=r['elapsed_seconds'],receipt=dict(path=str(p),sha256=digest(p)),
        fresh_numerical_cold_N1='unknown; parent H2 factors and boundary packets reused',
        first_preparation_lineage=dict(parent_H2=scope.parent('H2')['arrays']['sha256'],old_failures_charged=True),
        timing_boundary='before run_case through complete required field, independent audit, IO and descendant cleanup',
        reference_comparisons_not_in_this_deployment=True)


def collect():
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    from benchmarks.collect_local_subcell import compact_candidate
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir(exist_ok=True)
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()};ptr={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}
    candidates={}
    for role in scope.SOLVES:
        if role not in stages:continue
        r=stages[role];c=compact_candidate(r,ptr[role]);c.update({k:r[k] for k in ('face_inventory','face_physical_witness','internal_service_consumption','local_public_witness','prepared_start','fresh_cold_N1') if k in r});candidates[role]=c
    repairs=[json.loads(x) for x in (scope.window.TMP/'repair_journal.jsonl').read_text().splitlines()]
    data=dict(run_index_v61=dict(runs=runs,pointers=ptr,parent_H2=dict(arrays=scope.parent('H2')['arrays'],bank=scope.parent('H2')['local_schur_bank']),old_window_closed=True),
        scientific_checks_v61=dict(candidates=candidates,preflight=stages.get('PREFLIGHT'),verification=stages.get('VERIFY_COST'),NN_training=0,NN20=False,continuum_accuracy=False,target_qualified=False),
        resource_costs_v61=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),charged_known_lower_seconds=scope.window.charged_wall(),
            historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],historical_unknown='preserved',
            deployments={r:deployment_receipt(r) for r in scope.SOLVES if r in stages},global_numeric_attempts=scope.numeric_factor_attempts(),
            nominal_sampling_seconds=.5,sampled_peak_not_continuous_hard_peak=True,inclusive_N1_not_added_to_nested_timers=True),
        target_gap_v61=dict(interface_payload_bytes={r:65*scope.case_spec(r)['rows']*16 for r in scope.SOLVES},
            V33_Z32_65_vectors_derived_not_RSS=True,internal_rows_not_in_interface_Krylov=696960,local_cache_bytes=16*2**30,
            scenario=dict(Nx=80,Ny=80,Nz=400,modes=268156,accuracy_unqualified=True),H2_interface_TB=.528,FX_interface_TB=1.071,FXY_interface_TB=1.614,
            all_micro_FE_65_vectors_TB=12.125,per_cell_dense_Schur_copy_TB=7.644,
            missing=['original action/PC','x/b/r/workspace','recovery and MPI copies','system reserve','target fill/iterations/time/RSS'],
            target_N1='unknown',qualified_2TB48h=False,NN_training=0,NN20=False),repair_journal_v61=dict(entries=repairs,failures_preserved=True))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V61_COMPACT_COSTS',runs=len(runs),records=len(data))))


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v59.md',response_name='response_v61.md',outcome_name='face_trace_enrichment_v61.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V61 collector arguments')
