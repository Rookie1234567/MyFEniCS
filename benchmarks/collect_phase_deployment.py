"""V58 frozen consumers, independent saved-array checks and narrow cost index."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import phase_deployment_scope as scope
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.phase_notch_hp import restore_record
from src.solvers.phase_saved_closure import selected_points


def comparison(first,second,folder,journal):
    from src.solvers.phase_notch_hp_fields import common_difference
    from src.solvers.phase_notch_hp_modes import mode_comparison
    from src.solvers.phase_evaluation_cache import cached_evaluator_factory
    a=restore_record(first,journal,scope=scope);b=restore_record(second,journal,scope=scope)
    carriers=[checked_arrays(r['arrays'])['kappa'] for r in (first,second)]
    identity=dict(parent_array_sha256=[first['arrays']['sha256'],second['arrays']['sha256']],carrier_hashes=[r['arrays']['members']['kappa']['sha256'] for r in (first,second)],
        consumer_module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    factory=cached_evaluator_factory(limit_bytes=256*2**20,quadrature_tables=False);rows=[]
    folder.mkdir(parents=True,exist_ok=True)
    for q in (23,31):
        r=common_difference(a[3],b[3],b[0],journal,folder,q=q,selected_points=selected_points(),
            evaluator_factory=factory,progress_identity=identity,carrier_pair=carriers)
        rows.append(r);write_json(folder/f'common_q{q}.json',r)
    lo,r=rows
    qdef=max(abs(lo['fields'][k][n]**2-r['fields'][k][n]**2)/max(r['fields'][k]['reference_L2']**2,1e-24)
        for k in r['fields'] for n in ('reference_L2','difference_L2'))
    if qdef>1e-10:
        q=39;r=common_difference(a[3],b[3],b[0],journal,folder,q=q,selected_points=selected_points(),
            evaluator_factory=factory,progress_identity=identity,carrier_pair=carriers)
        prev=rows[-1];qdef=max(abs(prev['fields'][k][n]**2-r['fields'][k][n]**2)/max(r['fields'][k]['reference_L2']**2,1e-24)
            for k in r['fields'] for n in ('reference_L2','difference_L2'));rows.append(r)
    modes=mode_comparison(first,second,folder)
    power={k:abs(first['output']['port_metrics'][k]-second['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
    energy=[abs(v['output']['volume_metrics']['energy_closure_error_port_volume']) for v in (first,second)]
    r.update(quadrature_pair=[x['q'] for x in rows],quadrature_operation_scaled=qdef,q23_arrays=rows[0]['arrays'],
        modes=modes,power_differences=power,energies=energy,**identity)
    r['pass_gate']=r['pass_gate'] and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energy)<=1e-5
    r['quadrature_classification']='STABLE' if qdef<=1e-10 else 'INCONCLUSIVE'
    write_json(folder/'comparison.json',r);return r


def verify(folder,journal):
    from benchmarks.collect_phase_saved_closure import vector_check
    from benchmarks.collect_common_weak_phase import output_check,reproduction_check
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    frozen=json.loads((scope.window.TMP/'scientific_queue_frozen.json').read_text())
    bound=journal.source_state.get('verification_inventory',{})
    if bound.get('sha256')!=hashlib.sha256((scope.window.TMP/'scientific_queue_frozen.json').read_bytes()).hexdigest():raise ValueError('live frozen verification inventory')
    checks={};states={}
    for role,item in frozen['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=item['array_sha256']:raise ValueError('frozen candidate changed')
        states[role]=r
        with journal.measured('saved_independent_original_and_output_'+role):
            original=vector_check(r['independent']['arrays']);output=output_check(r)
        checks[role]=checked_state(original,output)
        write_json(folder/'completed_checker_states.json',checks)
    shim=SimpleNamespace(NAMESPACE='v58',window=scope.window,plan_record=scope.plan_record,stage=lambda role:states[role])
    modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder)
    pairs={}
    for x,y in (('B6','C6'),('G6','G7'),('R6','G6'),('R7','G7')):
        if y not in states or (x in scope.SOLVES and x not in states):continue
        first=states[x] if x in states else scope.parent(x)
        pairs[x+'_'+y]=comparison(first,states[y],folder/(x+'_'+y),journal)
        if y=='C6':pairs[x+'_'+y]['strict_reproduction']=reproduction_check(pairs[x+'_'+y])
        write_json(folder/'comparison_progress.json',dict(completed=list(pairs),pairs=pairs))
    # This checker reuses established saved integrals/regions but never a PDE.
    from benchmarks.collect_phase_notch_hp import saved_checks
    allstates=dict(states,**{x:scope.parent(x) for x in ('B6','R6','R7')})
    _,regions,gates=saved_checks(allstates,pairs,scope=scope)
    return dict(status='COMPLETED',role='VERIFY_COST',states=checks,comparisons=pairs,regions=regions,
        saved_pair_gates=gates,modal=modal,independent_consumer=True,new_complete_solves=0,new_factor_count=0)


def checked_state(original,output):
    # output_check independently recomputes volume/energy and validates the
    # full field inventory; its public verdict is energy_pass, not pass_gate.
    return dict(original=original,output=output,
        pass_gate=bool(original['pass_gate'] and output['energy_pass']))




def cost_binding(run,manifest,directory,*,active_scope=scope):
    scope=active_scope
    directory=Path(directory)
    if manifest['source_sha']!=run['source_sha']:raise ValueError('cost source identity')
    formal=run['role'] in scope.STAGES
    return dict(role=run['role'],source_sha=run['source_sha'],
        binding_scope='formal_one_run' if formal else 'auxiliary_command',
        input_sha256=manifest['input_sha256'] if formal else None,
        physical_sha256=manifest['physical_sha256'] if formal else None,
        auxiliary_has_no_PDE_input=not formal,
        resolved_sha256=digest(directory/'resolved_config.json') if (directory/'resolved_config.json').exists() else None,
        memory=manifest.get('memory_budget'),manifest_sha256=digest(directory/'run_manifest.json'))


def cost_rows(runs,*,active_scope=scope):
    scope=active_scope
    from benchmarks.collect_phase_notch_hp import measured_timeline,sampling_receipt
    rows=[];sources={};bindings=[]
    for run in runs:
        d=Path(run['folder']);m=json.loads((d/'run_manifest.json').read_text())
        sources[run['source_sha']]=m['implementation_hashes']
        sp=d/('run_summary.json' if (d/'run_summary.json').exists() else 'summary.json')
        if not sp.exists():sp=d/'launcher_failure.json'
        summary=json.loads(sp.read_text());worker=scope.ARTIFACT/d.name
        ep=worker/'events.jsonl';events=[json.loads(s) for s in ep.read_text().splitlines()] if ep.exists() else []
        rows.append(dict(role=run['role'],folder=str(d.relative_to(scope.ROOT)),source_sha=run['source_sha'],
            classification=run['classification'],supervised_seconds=run['elapsed_seconds'],
            launch_seconds=summary.get('launch_wall_seconds',run['elapsed_seconds']),
            peak_bytes=run['peak_bytes'],swap_bytes=run['swap_bytes'],shared_workstation=True,
            sampling=sampling_receipt(d/'supervision/resources.jsonl') if (d/'supervision/resources.jsonl').exists() else None,
            disjoint_timing=measured_timeline(ep) if ep.exists() else {},
            actual_global_numeric_factors=sum(e['event']=='h_bounded_numeric_factor_end' for e in events),
            lifecycle=[{k:v for k,v in e.items() if k!='clock'} for e in events if 'released' in e['event'] or
                e['event'] in ('object_owner_snapshot','factor_present','h_numeric_capacity','finite_factor_numeric_admission')],
            symbolic_numeric_capacity=json.loads((worker/'h_symbolic_capacity.json').read_text())['plan']
                if (worker/'h_symbolic_capacity.json').exists() else None))
        bindings.append(cost_binding(run,m,d,active_scope=scope))
    return rows,sources,bindings


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact_candidates(stages,pointers):
    out={}
    for role in scope.SOLVES:
        if role not in stages:continue
        r=stages[role]
        out[role]={k:r[k] for k in ('status','degree','case_spec','source_sha','solve_source_sha','arrays',
            'returned_arrays','original_audit','equation_pass','direct_target_pass','recovery','capacity',
            'fixed_refinements','deployment_complete','numerical_carrier','physical_carrier','boundary_provider') if k in r}
        out[role]['result']=pointers[role]
        out[role]['independent']={k:r['independent'][k] for k in ('arrays','original_audit','equation_pass','recovery_pass','recovery','direct_internal_target_pass','audit_path','volume_q','surface_q') if k in r['independent']}
        output=r['output'];vm=output['volume_metrics'];pm=output['port_metrics']
        out[role]['output']=dict(fields=output['fields'],fixed_240=output['fixed_240'],
            power={k:pm[k] for k in ('R_total','T_total','A_balance')},
            A_volume=vm['A_volume_total'],energy=vm['energy_closure_error_port_volume'],volume_quadrature=vm['q_pair'],
            volume_arrays=vm['all_rule_arrays'],full_mode_file=str(Path(output['fields']['path']).with_name('port_power.json')))
        raw=Path(r['arrays']['path']).parent/'raw_tensor/manifest.json'
        if raw.exists():out[role]['raw_preparation']=dict(path=str(raw.relative_to(scope.ROOT)),sha256=digest(raw))
    return out


def deployment_cost_receipt(role):
    p=scope.window.TMP/(role+'_one_run')/'receipt.json'
    if not p.exists():return dict(status='unknown',reason='missing outer process clock',role=role)
    r=json.loads(p.read_text())
    if r['returncode']!=0:return dict(status='partial',outer_receipt=r,role=role)
    return dict(status='measured',T_N1_seconds=r['elapsed_seconds'],outer_receipt=r,receipt_sha256=digest(p),
        start_boundary='before independent run_case process launch',
        end_boundary='after original audit, all field/mode/power/volume/provenance/IO and descendant cleanup',
        numerical_preparation_cold=True,OS_JIT_system_cache_not_cleared=True,
        research_comparisons_included=False,matched_old_complete_cold_control=False,end_to_end_speed_ratio=None)


def target_scope(costs):
    p=scope.ROOT/'docs/task042_neural_coarse_inverse/outcomes/records/target_gap_v57.json'
    old=json.loads(p.read_text());q=scope.ROOT/old['parent']['path']
    if digest(q)!=old['parent']['sha256']:raise ValueError('frozen target layout parent changed')
    previous=json.loads(q.read_text());base=previous['bridge_scenarios'][-1]
    libraries={}
    for degree in (6,7):
        layout=base['layouts'][str(degree)];trace=layout['condensed_rows'];full=layout['independent_FE']
        libraries[str(degree)]=dict(trace_plus_port_rows=trace,full_FE_rows=full,
            complex128_bytes_per_value=16,trace_plus_port_one_vector_bytes=16*trace,
            V_vectors=33,Z_vectors=32,principal_vectors=65,
            trace_plus_port_V_and_Z_bytes=65*16*trace,full_FE_V_and_Z_bytes=65*16*full,
            full_FE_library_excludes_port_rows=True,
            extra_solution_rhs_residual_workspace_not_included=True,
            classification='derived scenario, not measured RSS or target allocation')
    return dict(parent=dict(path=str(p.relative_to(scope.ROOT)),sha256=digest(p)),
        layout_parent=dict(path=str(q.relative_to(scope.ROOT)),sha256=digest(q)),
        parent_scope=dict(scale_fraction=base['scale_fraction'],modes=base['modes'],
            Nx=base['Nx'],Ny=base['Ny'],Nz=base['Nz'],not_accuracy_lower_bound=True),FGMRES_restart32=libraries,
        implementation_scope='standard FGMRES with both V_(m+1) and preconditioned Z_m resident; other solver implementations require own accounting',
        measured_increment={r['role']:dict(launch_seconds=r['launch_seconds'],sampled_peak_bytes=r['peak_bytes'])
            for r in costs if r['role'] in scope.SOLVES},
        target_local_Schur_and_PC_bytes='unknown',target_factor_fill='unknown',target_iteration_count='unknown',
        target_operator_PC_orthogonalization_communication_seconds='unknown',
        target_simultaneous_RSS='unknown',target_complete_N1_seconds='unknown',
        continuum_accuracy=False,target_2TB_48h_qualified=False,target_allocations=0,NN_training=0,NN20=False,
        learning_object_selected=None,NN20_necessary_condition='f*V-H >= 0.2*T_best_non_neural at same complete correctness, other resource compliant')


def saved_defect_check(record):
    if not record:return dict(status='not_run',reason='no bounded S result')
    v=checked_arrays(record['arrays'])
    names=('u7','Pu6','delta','A7Pu6','A7delta','A7u7','b7','defect','r7','identity')
    size=v['u7'].size
    if any(v[n].shape!=(size,) or not np.isfinite(v[n]).all() for n in names):
        raise ValueError('complete finite S full-body inventory')
    den=max(sum(np.linalg.norm(v[n]) for n in ('b7','A7Pu6','A7u7','A7delta')),1e-30)
    eq=v['defect']-v['r7']-v['A7delta']
    op=float(np.linalg.norm(eq)/den)
    if not np.array_equal(v['delta'],v['u7']-v['Pu6']) or not np.array_equal(v['defect'],v['b7']-v['A7Pu6']) or not np.array_equal(v['r7'],v['b7']-v['A7u7']):
        raise ValueError('saved S actual vector identity')
    if not np.allclose(eq,v['identity'],rtol=0,atol=1e-30) or not np.isclose(op,record['identity_operation_scaled'],rtol=1e-12):
        raise ValueError('saved S reported operation scale')
    norms={n:float(np.linalg.norm(v[n])) for n in ('defect','r7','P_H_defect','physical_port_residual')}
    body={n:float(np.linalg.norm(v['defect'][v[n+'_rows']])) for n in ('internal','trace')}
    if np.intersect1d(v['internal_rows'],v['trace_rows']).size:raise ValueError('disjoint S row partitions')
    return dict(status='measured_saved_array_check',pass_gate=op<=1e-10,identity_operation_scaled=op,
        vector_norms=norms,row_norms=body,rhs_relative=norms['defect']/max(np.linalg.norm(v['b7']),1e-30),
        pulled_defect_rhs_relative=norms['P_H_defect']/max(np.linalg.norm(v['b7']),1e-30),
        source_array_sha256=record['arrays']['sha256'],coefficient_norm_is_not_field_norm=True,
        no_condition_number_no_error_bound=True,new_A_AH=0,new_complete_solves=0)


def collect():
    import os
    from benchmarks.collect_common_weak_phase import archive_increment
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}
    P=stages.get('P',{});verify_state=stages.get('VERIFY_COST',{})
    science=dict(candidates=compact_candidates(stages,pointers),
        qualification=P,saved_defect=stages.get('S'),saved_defect_independent=saved_defect_check(stages.get('S')),verification=verify_state,
        strict_reproduction=verify_state.get('comparisons',{}).get('B6_C6',{}).get('strict_reproduction'),
        complete_continuum_accuracy=False,NN_training=0,NN20=False,target_qualified=False)
    values=dict(run_index_v58=dict(runs=runs,pointers=pointers),scientific_checks_v58=science,
        resource_costs_v58=dict(runs=costs,source_hashes=sources,bindings=bindings,
            charged_lower_seconds=scope.window.charged_wall(),historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],
            historical_unknown='preserved; no invented old cost',clock=scope.window.snapshot(),
            C6_deployment=deployment_cost_receipt('C6'),other_cases={r:deployment_cost_receipt(r) for r in ('G6','G7')},
            nonoverlap_policy='outer complete deployment is inclusive; exclusive event timeline is a decomposition, never added to it',
            nominal_sampling_seconds=.5,sampled_peak_is_not_continuous_hard_peak=True,
            final_auxiliary_tail='included by later settlement receipt; this record is a frozen snapshot'),
        physical_identity_bindings_v58=dict(physical=scope.plan_record()['physical_descriptor'],runs=bindings,
            physical_incidence_unchanged=True,numerical_carrier_shift=[0,1],
            legacy_physical_hash_includes_discretization_and_numerical_carrier=True,
            common_physical_inventory_descriptor_sha256=digest_bytes(scope.plan_record()['physical_descriptor']),
            physical_only_sha256=digest_bytes({k:scope.plan_record()['physical_descriptor'][k] for k in ('geometry','materials','incidence')}),
            numerical_cases=scope.plan_record()['cases']),
        target_gap_v58=target_scope(costs),stage_verdicts_v58={r:dict(status=v['status'],source_sha=v.get('source_sha'),result=pointers[r]) for r,v in stages.items()},
        repair_journal_v58=json.loads((scope.window.TMP/'repair_notes.json').read_text()))
    for name,value in values.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V58_COMPACT_EVIDENCE_COLLECTED',records=str(out),increment_only=True)))


def digest_bytes(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v56.md',response_name='response_v58.md',outcome_name='deployment_cost_paired_gauge_v58.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V58 explicit collector arguments')


if __name__=='__main__':main()
