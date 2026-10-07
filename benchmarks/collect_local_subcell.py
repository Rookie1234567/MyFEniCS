"""Saved V60 physical/mixed consumers; no assembly, factor or PDE solve."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json
from src.solvers import local_subcell_scope as scope
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.scattering_anchor import relative


def macro_saved_check(r):
    a=checked_arrays(r['arrays']);v=checked_arrays(r['independent']['ambient_original']['arrays']);m=checked_arrays(r['trace_mapping']);saved=checked_arrays(r['independent']['arrays'])
    J=sparse.csr_matrix((m['J_data'],m['J_indices'],m['J_indptr']),shape=tuple(m['J_shape']));ih=m['internal_rows'];sl=m['slaves'];nt=r.get('mapping_check',{}).get('trace',32832);ni=696960
    if J.shape!=(len(a['u_storage']),ni+nt) or len(ih)!=ni or len(np.unique(ih))!=ni or len(np.setdiff1d(np.arange(J.shape[0]),sl))!=834048:raise ValueError('macro complete native/mixed inventory')
    x=np.r_[a['u_storage'][ih],a['low_trace']];mapped=J@x;op=relative(mapped-a['u_storage'],a['u_storage'])
    den=max(np.linalg.norm(J.conj().T@v['rhs']),1e-30)
    res=J.conj().T@v['residual'];aug=J.conj().T@v['augmented_top'];pr=v['port_residual']
    fields=dict(true=float(np.linalg.norm(res)/den),native=float(np.linalg.norm(res)/den),augmented=float(np.linalg.norm(aug)/den),port=relative(pr,v['projected']))
    stored=relative(res-saved['mixed_residual'],J.conj().T@v['rhs'])
    rh=relative(v['rhs']-a['rhs'],a['rhs']);volume=relative(v['volume_action']-a['volume_action'],a['volume_action'])
    recs=[]
    for rows in ih.reshape(160,4356):recs.append(float(np.linalg.norm(v['residual'][rows])/max(np.linalg.norm(v['volume_curl'][rows])+np.linalg.norm(v['volume_mass'][rows]),1e-30)))
    rec=max(recs)
    if not np.array_equal(v['u_storage'],a['u_storage']) or not np.array_equal(v['port'],a['port']):raise ValueError('independent H2 candidate identity')
    if len(a['port'])!=828 or len(a['low_trace'])!=nt or len(np.unique(sl))!=len(sl):raise ValueError('complete H2 port/trace/slave inventory')
    if not np.array_equal(np.sort(np.r_[ih,m['high_native_rows'],sl]),np.arange(len(a['u_storage']))):raise ValueError('H2 complete disjoint native partition')
    scale=np.abs(v['rhs'])+np.abs(v['volume_action'])+np.abs(v['native_boundary_action'])+np.abs(v['coupling_action'])
    identities=dict(native=relative(v['residual']-(v['rhs']-v['volume_action']-v['native_boundary_action']),scale),
        augmented=relative(v['augmented_top']-(v['rhs']-v['volume_action']-v['coupling_action']),scale),
        native_augmented=relative(v['residual']-(v['augmented_top']-v['native_boundary_action']+v['coupling_action']),scale),
        port=relative(v['port_residual']-(v['projected']-v['H']*v['port']),np.abs(v['projected'])+np.abs(v['H']*v['port'])),
        volume_parts=relative(v['volume_action']-v['volume_curl']-v['volume_mass'],np.abs(v['volume_curl'])+np.abs(v['volume_mass'])),
        action_split=relative(v['volume_action']-v['volume_inside']-v['volume_trace'],np.abs(v['volume_inside'])+np.abs(v['volume_trace'])))
    if not all(np.all(np.isfinite(value)) for value in v.values()):raise ValueError('nonfinite independent H2 inventory')
    allfinite=all(np.isfinite(x) for x in [*fields.values(),*identities.values(),op,stored,rh,volume,rec]);slave=bool(np.all(a['u_storage'][sl]==0))
    return dict(mixed=fields,ambient_relative=relative(v['residual'],v['rhs']),mapping_operation=op,saved_pullback_difference=stored,
        RHS_pair_relative=rh,production_independent_volume_relative=volume,macro_internal_recovery_operation=rec,macro_internal_operation_by_cell=recs,
        mixed_internal_rows=ni,mixed_trace_rows=nt,ambient_independent_rows=834048,port_rows=828,slave_zero=slave,
        operation_identities=identities,
        pass_gate=allfinite and max(fields.values())<=1e-6 and max(op,stored,rh,volume,rec,*identities.values())<=1e-10 and slave,
        direct_target_pass=allfinite and max(fields.values())<=1e-10,NOT_A_FULL_AMBIENT_SOLUTION=True)


def comparison(a,b,folder,journal,*,reproduction=False,live_scope=None):
    from src.solvers.phase_notch_hp import restore_record
    from src.solvers.phase_notch_hp_fields import common_difference
    from src.solvers.phase_notch_hp_modes import mode_comparison
    from src.solvers.phase_saved_closure import selected_points
    from src.solvers.phase_evaluation_cache import cached_evaluator_factory
    actual_scope=scope if live_scope is None else live_scope
    first=restore_record(a,journal,scope=actual_scope);second=restore_record(b,journal,scope=actual_scope);carriers=[checked_arrays(r['arrays'])['kappa'] for r in (a,b)]
    if not np.array_equal(*carriers):raise ValueError('original same kappa physical comparison')
    folder.mkdir(parents=True,exist_ok=True);identity=dict(parent_array_sha256=[a['arrays']['sha256'],b['arrays']['sha256']],consumer_module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    factory=cached_evaluator_factory(limit_bytes=256*2**20,quadrature_tables=False);rows=[]
    for q in (23,31):
        r=common_difference(first[3],second[3],second[0],journal,folder,q=q,selected_points=selected_points(),evaluator_factory=factory,progress_identity=identity,carrier_pair=carriers)
        rows.append(r);write_json(folder/f'common_q{q}.json',r)
    lo,r=rows;qdef=max(abs(lo['fields'][k][n]**2-r['fields'][k][n]**2)/max(r['fields'][k]['reference_L2']**2,1e-24) for k in r['fields'] for n in ('reference_L2','difference_L2'))
    if qdef>1e-10:
        previous=r;r=common_difference(first[3],second[3],second[0],journal,folder,q=39,selected_points=selected_points(),evaluator_factory=factory,progress_identity=identity,carrier_pair=carriers)
        qdef=max(abs(previous['fields'][k][n]**2-r['fields'][k][n]**2)/max(r['fields'][k]['reference_L2']**2,1e-24) for k in r['fields'] for n in ('reference_L2','difference_L2'));rows.append(r)
    modes=mode_comparison(a,b,folder);power={k:abs(a['output']['port_metrics'][k]-b['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(a['output']['volume_metrics']['A_volume_total']-b['output']['volume_metrics']['A_volume_total']);energy=[abs(s['output']['volume_metrics']['energy_closure_error_port_volume']) for s in (a,b)]
    fgate,pgate,mgate=(1e-6,1e-8,1e-9) if reproduction else (1e-4,1e-5,1e-6)
    maximum=max([x['relative'] for x in r['fields'].values()]+list(r['selected'].values()))
    r.update(quadrature_pair=[x['q'] for x in rows],quadrature_operation_scaled=qdef,q23_arrays=rows[0]['arrays'],modes=modes,power_differences=power,energies=energy,**identity,
        fields_threshold=fgate,power_threshold=pgate,single_mode_power_threshold=mgate,strict_same_space_reproduction=reproduction)
    r['pass_gate']=maximum<=fgate and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=fgate and modes['mode_power_max_absolute']<=mgate and max(power.values())<=pgate and max(energy)<=1e-5
    r['classification']='SAME_SPACE_REPRODUCTION_PASS' if reproduction and r['pass_gate'] else 'STRUCTURAL_MAP_SENSITIVITY' if reproduction else 'SPACE_INCREMENT_PASS' if r['pass_gate'] else 'SPACE_INCREMENT_FAIL'
    write_json(folder/'comparison.json',r);return r


def verify(folder,journal):
    from benchmarks.collect_trace_interior import mixed_vector_check
    from benchmarks.collect_common_weak_phase import output_check
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    frozen_path=scope.window.TMP/'scientific_queue_frozen.json';frozen=json.loads(frozen_path.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=hashlib.sha256(frozen_path.read_bytes()).hexdigest():raise ValueError('V60 frozen consumer actual identity')
    states={};checks={}
    for role,item in frozen['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=item['array_sha256']:raise ValueError('V60 saved state changed after queue freeze')
        checks[role]=dict(mixed_original=mixed_vector_check(r) if role=='C67' else macro_saved_check(r),physical_outputs=output_check(r));states[role]=r
        if role=='H2' and 'local_schur_bank' in r:
            from src.solvers.local_schur_bank import SavedLocalSchurAction
            bank=r['local_schur_bank'];receiver=SavedLocalSchurAction(bank['path'],source_sha=r.get('solve_source_sha',r['source_sha']),manifest_sha256=bank['sha256'],trace_rows=32832,cell_count=160)
            witnesses=[]
            with journal.measured('independent_saved_local_bank_consumer'):
                for row in r['local_body_action_pairs']:
                    a=checked_arrays(row['arrays']);y=receiver.apply(a['input']);witnesses.append(relative(y-a['assembled'],a['assembled']))
            checks[role]['saved_local_action_bank']=dict(relative=witnesses,pass_gate=max(witnesses)<=1e-10,owner_payload_bytes=receiver.owner_payload_bytes,no_factor_reload=True,no_global_matrix=True)
            del receiver
        write_json(folder/(role+'_saved_check.json'),checks[role])
    shim=SimpleNamespace(NAMESPACE='v60',window=scope.window,plan_record=scope.plan_record,stage=lambda role:states[role])
    modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder)
    pairs={}
    if 'C67' in states:pairs['C67_M67']=comparison(states['C67'],scope.parent('M67'),folder/'C67_M67',journal,reproduction=True)
    if 'H2' in states:
        pairs['R6_H2']=comparison(scope.parent('R6'),states['H2'],folder/'R6_H2',journal)
        pairs['M68_H2']=comparison(scope.parent('M68'),states['H2'],folder/'M68_H2',journal)
    from benchmarks.collect_phase_notch_hp import saved_checks
    allstates=dict(states,**{name:scope.parent(name) for name in ('M67','R6','M68')})
    _,regions,pair_gates=saved_checks(allstates,pairs,scope=scope)
    for name,p in pairs.items():
        gate=pair_gates[name];fg,pg,mg=(p['fields_threshold'],p['power_threshold'],p['single_mode_power_threshold'])
        strict=gate['field_max']<=fg and gate['selected_max']<=fg and gate['modal']['outgoing_amplitude_at_boundary_relative']<=fg and gate['modal']['mode_power_max_absolute']<=mg and max(gate['power'].values())<=pg and max(gate['energies'])<=1e-5 and gate['quadrature_operation']<=1e-10
        gate.update(field_mode_power_pass=bool(strict),field_threshold=fg,power_threshold=pg,single_mode_power_threshold=mg)
        if bool(strict)!=bool(p['pass_gate']):raise ValueError('strict V60 pair gate from actual saved integrals differs')
    r=dict(status='COMPLETED',role='VERIFY_COST',checks=checks,regions=regions,saved_pair_gates=pair_gates,pairs=pairs,modal=modal,new_factor_count=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings)
    write_json(folder/'verification_scientific_result.json',r);return r



def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def deployment_receipt(role):
    p=scope.window.TMP/(role+'_one_run/receipt.json')
    if not p.exists():return dict(status='unknown',reason='no measured external process/cleanup receipt')
    a=json.loads(p.read_text());r=scope.stage(role);ok=a['exit_code']==0 and r.get('deployment_complete',False)
    if r.get('consumer_only'):
        from datetime import datetime
        paths=sorted(scope.window.TMP.glob(role+'_one_run*/receipt.json'))
        parts=[dict(path=str(p),sha256=digest(p),**json.loads(p.read_text())) for p in paths]
        start=min(datetime.fromisoformat(v['start_utc']) for v in parts);end=max(datetime.fromisoformat(v['end_utc']) for v in parts)
        return dict(status='measured_complete_restart_chain' if ok else 'partial_restart_chain',
            T_N1_observed_restart_chain_seconds=(end-start).total_seconds(),necessary_process_segments_seconds=sum(v['elapsed_seconds'] for v in parts),
            fresh_numerical_cold_T_N1_seconds='unknown; preparation was stopped and reused, not independently rebuilt',
            receipts=parts,original_stop=r['original_stop'],postprocessing_source_sha=r['source_sha'],solve_source_sha=r['solve_source_sha'],
            boundaries='first H2 preparation process through saved-only consumer cleanup; repair, archival and intervening waits included in observed chain',
            cold_policy='177 child/110 macro class checkpoints reused; remaining exact classes constructed; all historical failures charged',
            time_gain_not_granted_without_matched_control=True,history_comparisons_included=False,optional_local_research_included=False)
    return dict(status='measured_complete' if ok else 'partial',T_N1_seconds=a['elapsed_seconds'],receipt=a,receipt_sha256=digest(p),
        boundaries='before run_case process through complete required outputs, independent original audit, IO and process cleanup',
        cold_policy='fresh per-case numerical preparation; shared OS/JIT cache retained and recorded',
        history_comparisons_included=False,optional_local_research_included=False,matched_old_cold_control=False,
        time_gain_not_granted_without_matched_control=True)


def compact_candidate(r,pointer):
    names=('status','case','degree','case_spec','grid','representation','source_sha','source','solve_source_sha','arrays','returned_arrays',
        'trace_mapping','mapping_check','original_audit','ambient_audit','recovery','recovery_arrays','capacity','graph','fixed_refinements',
        'local_global_factors','local_action_pairs','build_audit','local_response_classes','child_local_classes','preparation_resume','cache_payload_bytes','local_schur_bank','local_body_action_pairs',
        'equation_pass','direct_target_pass','deployment_complete','boundary','boundary_provider','tangential_check',
        'consumer_only','original_stop','producer_manifest','original_solve_source')
    result={k:r[k] for k in names if k in r};result['result']=pointer
    i=r.get('independent',{});result['independent']={k:i[k] for k in ('original_audit','arrays','equation_pass','recovery_pass','direct_internal_target_pass','audit_path','macro_internal_operation_scaled') if k in i}
    result['independent']['ambient_original_arrays']=i.get('ambient_original',{}).get('arrays')
    o=r.get('output',{});result['output']={k:o[k] for k in ('fields','fixed_240','port_metrics','volume_metrics') if k in o}
    result['ambient_not_formal_pass_prerequisite']=True;return result


def collect():
    import os
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir(exist_ok=True)
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}
    parents={r:dict(source_sha=scope.parent(r)['source_sha'],arrays_sha256=scope.parent(r)['arrays']['sha256'],
        u_member_sha256=scope.parent(r)['arrays']['members']['u_storage']['sha256'],kappa_member_sha256=scope.parent(r)['arrays']['members']['kappa']['sha256']) for r in ('M67','M68','R6','R7','C6')}
    repairs=[json.loads(x) for x in (scope.window.TMP/'repair_journal.jsonl').read_text().splitlines()]
    numeric_attempts=scope.numeric_factor_attempts();numeric_completed=sum(c['actual_global_numeric_factors'] for c in costs)
    data=dict(run_index_v60=dict(runs=runs,pointers=pointers,parents=parents,all_parent_science_read_only=True),
        scientific_checks_v60=dict(candidates={r:compact_candidate(stages[r],pointers[r]) for r in scope.SOLVES if r in stages},
            preflight=stages.get('PREFLIGHT'),local_response=stages.get('LOCAL_RESPONSE'),verification=stages.get('VERIFY_COST'),
            NN_training=0,NN20=False,target_qualified=False,continuum_accuracy=False,complete_ambient_solution_not_claimed=True),
        resource_costs_v60=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),
            charged_known_lower_seconds=scope.window.charged_wall(),historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],
            historical_unknown='preserved; no invented exact old bill',deployments={r:deployment_receipt(r) for r in scope.SOLVES if r in stages},
            global_numeric_attempts_including_failure=numeric_attempts,global_numeric_completed=numeric_completed,
            inclusive_N1_not_added_to_nested_timers=True,nominal_sampling_seconds=.5,sampled_peak_not_continuous_hard_peak=True),
        physical_identity_bindings_v60=dict(physical=scope.plan_record()['physical_descriptor'],runs=bindings,cases=scope.plan_record()['cases'],
            carrier=[8.94046081729244,.7821889682108057,0.],G6_G7_not_used=True,all_modes=828,primal_dual='Hermitian',
            local_inside_affine_particular_retained=True,high_global_schur_not_formed=True),
        target_gap_v60=dict(parent=dict(path='docs/task042_neural_coarse_inverse/outcomes/records/target_gap_v59.json',sha256=digest(scope.ROOT/'docs/task042_neural_coarse_inverse/outcomes/records/target_gap_v59.json')),
            local_formation='sum E_e^H S_e E_e, no global high Schur/projection',fixed_trace_port_rows=33660,
            one_complex128_trace_port_vector_bytes=33660*16,FGMRES_restart32_V33_Z32_payload_bytes=65*33660*16,
            actual_FGMRES_allocation=False,complete_FE_vectors_excluded_from_interface_Krylov=True,
            graph_bound_derived=34360848,C67_actual_graph=stages.get('C67',{}).get('build_audit'),H2_actual_graph=stages.get('H2',{}).get('graph'),
            H2_mixed=729792,H2_ambient=834048,local_cache_cap_bytes=8*2**30,local_r4_cap_bytes=16*2**30,
            local_objects='exact geometry/material/direction classes shared readonly; full field block recovery, no cellwise duplicate response library',
            target_fill='unknown',target_iterations='unknown',target_simultaneous_RSS='unknown',target_complete_N1='unknown',
            global_direct_factor_present=True,NN_training=0,NN20=False,qualified_2TB_48h=False),
        repair_journal_v60=dict(entries=repairs,all_failures_and_costs_retained=True))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V60_COMPACT_EVIDENCE_COLLECTED',records=str(out),increment_only=True)))


def main():
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v58.md',response_name='response_v60.md',outcome_name='local_assembly_subcell_response_v60.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V60 explicit collector arguments')


if __name__=='__main__':main()
