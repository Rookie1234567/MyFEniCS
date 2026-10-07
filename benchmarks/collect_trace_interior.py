"""Frozen mixed-space checker and physical comparisons; no solve or factor."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json
from src.solvers import trace_interior_scope as scope
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.scattering_anchor import relative


def restricted_array_check(v,m,a,saved,spec):
    """Consume every included weak row; omitted ambient tests are diagnostic."""
    R=sparse.csr_matrix((m['R_data'],m['R_indices'],m['R_indptr']),shape=tuple(m['R_shape']))
    nt,nh,ni,np_=spec['mixed_trace'],spec['trace'],spec['internal'],spec['complete_modes']
    N=len(a['u_storage']);internal=np.asarray(m['internal_rows']);trace=np.asarray(m['high_native_rows']);slaves=np.asarray(a['slaves'])
    if R.shape!=(nh,nt) or ni+nh!=spec['independent'] or N!=ni+nh+len(slaves):raise ValueError('complete mixed native dimensions')
    if any(len(rows)!=len(np.unique(rows)) for rows in (internal,trace,slaves)) or len(internal)!=ni or len(trace)!=nh:raise ValueError('complete mixed row inventory')
    if not np.array_equal(np.sort(np.r_[internal,trace,slaves]),np.arange(N)):raise ValueError('complete mixed disjoint native partition')
    if len(m['low_native_rows'])!=nt or len(np.unique(m['low_native_rows']))!=nt or len(m['owner'])!=nh:raise ValueError('canonical trace owner inventory')
    if not np.array_equal(internal,v['internal_rows']):raise ValueError('independent internal row order')
    if len(a['low_trace'])!=nt or len(a['port'])!=np_:raise ValueError('complete mixed port/trace inventory')
    for name in ('rhs','residual','augmented_top','volume_action','volume_inside','volume_trace','volume_curl','volume_mass','coupling_action','native_boundary_action','u_storage'):
        if v[name].shape!=(N,) or not np.all(np.isfinite(v[name])):raise ValueError('complete finite native vector '+name)
    for name in ('projected','port_residual','H','port'):
        if v[name].shape!=(np_,) or not np.all(np.isfinite(v[name])):raise ValueError('complete finite port vector '+name)
    if not np.array_equal(v['u_storage'],a['u_storage']) or not np.array_equal(v['port'],a['port']) or not np.array_equal(v['slaves'],slaves):raise ValueError('independent candidate identity')
    if v['internal_residual'].shape!=(ni,) or len(v['internal_numerators'])!=spec['cells'] or len(v['internal_operation_scale'])!=spec['cells']:raise ValueError('internal recovery cell inventory')
    def pull(x):return np.r_[x[internal],R.conj().T@x[trace]]
    rhs=pull(v['rhs']);den=max(np.linalg.norm(rhs),1e-30)
    residual=pull(v['residual']);top=pull(v['augmented_top'])
    fields={'true':float(np.linalg.norm(residual)/den),'native':float(np.linalg.norm(residual)/den),
        'augmented':float(np.linalg.norm(top)/den),'port':relative(v['port_residual'],v['projected'])}
    for name,value in [('mixed_residual',residual),('mixed_augmented_top',top),('mixed_rhs',rhs),('ambient_residual',v['residual']),('port_residual',v['port_residual']),('projected',v['projected'])]:
        if not np.array_equal(value,saved[name]):raise ValueError('independent pullback member differs '+name)
    rec=float(np.max(v['internal_numerators']/np.maximum(v['internal_operation_scale'],1e-30)))
    op_scale=np.abs(v['rhs'])+np.abs(v['volume_action'])+np.abs(v['native_boundary_action'])+np.abs(v['coupling_action'])
    ops=dict(split=relative(v['volume_action']-v['volume_inside']-v['volume_trace'],np.maximum(np.abs(v['volume_inside']),np.abs(v['volume_trace']))),
        volume_parts=relative(v['volume_action']-v['volume_curl']-v['volume_mass'],np.abs(v['volume_curl'])+np.abs(v['volume_mass'])),
        native=relative(v['residual']-(v['rhs']-v['volume_action']-v['native_boundary_action']),op_scale),
        augmented=relative(v['augmented_top']-(v['rhs']-v['volume_action']-v['coupling_action']),op_scale),
        port=relative(v['port_residual']-(v['projected']-v['H']*v['port']),np.abs(v['projected'])+np.abs(v['H']*v['port'])),
        native_augmented_identity=relative(v['residual']-(v['augmented_top']-v['native_boundary_action']+v['coupling_action']),op_scale),
        saved_rhs=relative(v['rhs']-a['rhs'],a['rhs']),
        mapping=relative(R@a['low_trace']-a['u_storage'][trace],a['u_storage'][trace]))
    expected_internal=(v['rhs']-v['volume_inside']-v['volume_trace']-v['coupling_action'])[internal]
    ops['internal_residual']=relative(v['internal_residual']-expected_internal,op_scale[internal])
    nums=np.linalg.norm(expected_internal.reshape(spec['cells'],-1),axis=1)
    ops['internal_numerators']=relative(nums-v['internal_numerators'],v['internal_operation_scale'])
    slave=bool(np.all(a['u_storage'][slaves]==0))
    finite=all(np.isfinite(x) for x in [*fields.values(),*ops.values(),rec])
    return dict(mixed=fields,mixed_rhs_norm=float(den),ambient_relative=relative(v['residual'],v['rhs']),
        ambient_internal_norm=float(np.linalg.norm(v['residual'][internal])),ambient_trace_norm=float(np.linalg.norm(v['residual'][trace])),
        mapping_lift_operation=ops['mapping'],recovery_operation_max=rec,split_identity_operation=ops['split'],operation_identities=ops,slave_zero=slave,
        included_internal_rows=ni,included_trace_rows=nt,included_port_rows=np_,native_storage_rows=N,
        pass_gate=finite and max(fields.values())<=1e-6 and max(rec,*ops.values())<=1e-10 and slave,
        direct_target_pass=finite and max(fields.values())<=1e-10,ambient_not_a_pass_prerequisite=True,NOT_A_FULL_AMBIENT_SOLUTION=True)


def mixed_vector_check(r):
    v=checked_arrays(r['independent']['ambient_original']['arrays']);m=checked_arrays(r['trace_mapping']);a=checked_arrays(r['arrays'])
    saved=checked_arrays(r['independent']['arrays'])
    return restricted_array_check(v,m,a,saved,r['case_spec'])


def comparison(a,b,folder,journal):
    from src.solvers.phase_notch_hp import restore_record
    from src.solvers.phase_notch_hp_fields import common_difference
    from src.solvers.phase_notch_hp_modes import mode_comparison
    from src.solvers.phase_saved_closure import selected_points
    from src.solvers.phase_evaluation_cache import cached_evaluator_factory
    first=restore_record(a,journal,scope=scope);second=restore_record(b,journal,scope=scope)
    carriers=[checked_arrays(r['arrays'])['kappa'] for r in (a,b)]
    if not np.array_equal(*carriers):raise ValueError('only original same carrier comparison')
    folder.mkdir(parents=True,exist_ok=True);identity=dict(parent_array_sha256=[a['arrays']['sha256'],b['arrays']['sha256']],
        consumer_module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    factory=cached_evaluator_factory(limit_bytes=256*2**20,quadrature_tables=False);rows=[]
    for q in (23,31):
        r=common_difference(first[3],second[3],second[0],journal,folder,q=q,selected_points=selected_points(),
            evaluator_factory=factory,progress_identity=identity,carrier_pair=carriers)
        rows.append(r);write_json(folder/f'common_q{q}.json',r)
    lo,r=rows
    qdef=max(abs(lo['fields'][k][n]**2-r['fields'][k][n]**2)/max(r['fields'][k]['reference_L2']**2,1e-24)
        for k in r['fields'] for n in ('reference_L2','difference_L2'))
    if qdef>1e-10:
        previous=r;r=common_difference(first[3],second[3],second[0],journal,folder,q=39,selected_points=selected_points(),
            evaluator_factory=factory,progress_identity=identity,carrier_pair=carriers)
        qdef=max(abs(previous['fields'][k][n]**2-r['fields'][k][n]**2)/max(r['fields'][k]['reference_L2']**2,1e-24)
            for k in r['fields'] for n in ('reference_L2','difference_L2'));rows.append(r)
    modes=mode_comparison(a,b,folder)
    power={k:abs(a['output']['port_metrics'][k]-b['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    power['A_volume']=abs(a['output']['volume_metrics']['A_volume_total']-b['output']['volume_metrics']['A_volume_total'])
    energy=[abs(s['output']['volume_metrics']['energy_closure_error_port_volume']) for s in (a,b)]
    r.update(quadrature_pair=[x['q'] for x in rows],quadrature_operation_scaled=qdef,q23_arrays=rows[0]['arrays'],modes=modes,
        power_differences=power,energies=energy,**identity)
    r['pass_gate']=r['pass_gate'] and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energy)<=1e-5
    write_json(folder/'comparison.json',r);return r


def verify(folder,journal):
    from benchmarks.collect_common_weak_phase import output_check
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    f=scope.window.TMP/'scientific_queue_frozen.json';frozen=json.loads(f.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=hashlib.sha256(f.read_bytes()).hexdigest():raise ValueError('frozen actual consumer inventory')
    states={};checks={}
    for role,item in frozen['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=item['array_sha256']:raise ValueError('frozen mixed candidate changed')
        states[role]=r
        with journal.measured('independent_saved_mixed_and_complete_output_'+role):
            original=mixed_vector_check(r);out=output_check(r)
        checks[role]=dict(original=original,output=out,pass_gate=original['pass_gate'] and out['energy_pass'])
        write_json(folder/'completed_checker_states.json',checks)
    shim=SimpleNamespace(NAMESPACE='v59',window=scope.window,plan_record=scope.plan_record,stage=lambda x:states[x])
    modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder);pairs={}
    for x,y in (('R6','M67'),('R7','M67'),('M67','M68')):
        if y not in states or (x in scope.SOLVES and x not in states):continue
        a=states[x] if x in states else scope.parent(x)
        pairs[x+'_'+y]=comparison(a,states[y],folder/(x+'_'+y),journal)
        write_json(folder/'comparison_progress.json',dict(completed=list(pairs),pairs=pairs))
    return dict(status='COMPLETED',role='VERIFY_COST',states=checks,comparisons=pairs,modal=modal,
        independent_saved_checker=True,new_complete_solves=0,new_global_factors=0)


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def compact_candidate(r,pointer):
    output=r['output'];vm=output['volume_metrics'];pm=output['port_metrics'];ind=r['independent']
    return dict(status=r['status'],source_sha=r['source_sha'],result=pointer,case_spec=r['case_spec'],
        representation=r['representation'],trace_degree=6,interior_degree=r['interior_degree'],ambient_degree=r['ambient_degree'],
        arrays=r['arrays'],returned_arrays=r['returned_arrays'],trace_mapping=r['trace_mapping'],mapping_check=r['mapping_check'],
        mixed_original=r['original_audit'],independent_mixed={k:ind[k] for k in ('original_audit','arrays','equation_pass','recovery_pass','direct_internal_target_pass','audit_path')},
        ambient_audit_pointer=dict(path=str(Path(r['arrays']['path']).parent/'independent_original/independent_original_audit.json'),
            sha256=digest(Path(r['arrays']['path']).parent/'independent_original/independent_original_audit.json')),
        ambient_not_a_formal_pass_prerequisite=True,NOT_A_FULL_AMBIENT_SOLUTION=True,
        recovery=r['recovery'],recovery_arrays=r['recovery_arrays'],capacity=r['capacity'],fixed_refinements=r['fixed_refinements'],
        local_global_factors=r['local_global_factors'],
        output=dict(fields=output['fields'],fixed_240=output['fixed_240'],
            power={k:pm[k] for k in ('R_total','T_total','A_balance')},A_volume=vm['A_volume_total'],energy=vm['energy_closure_error_port_volume'],
            volume_quadrature=vm['q_pair'],volume_arrays=vm['all_rule_arrays'],full_mode_file=str(Path(output['fields']['path']).with_name('port_power.json'))),
        equation_pass=r['equation_pass'],deployment_complete=r['deployment_complete'],boundary_provider=r['boundary_provider'])


def deployment_receipt(role):
    p=scope.window.TMP/(role+'_one_run/receipt.json')
    if not p.exists():return dict(status='unknown',reason='missing measured external start-to-cleanup receipt')
    a=json.loads(p.read_text());passed=a['exit_code']==0 and scope.stage(role).get('deployment_complete',False)
    return dict(status='measured_complete' if passed else 'partial',T_N1_seconds=a['elapsed_seconds'],receipt=a,receipt_sha256=digest(p),
        boundaries='before one independent run_case process through full required physics/provenance/IO and descendant cleanup',
        cold_policy='fresh own case numerical caches; OS/JIT state retained and bound, not cleared',
        history_comparisons_included=False,optional_local_research_included=False,
        matched_old_complete_cold_control=False,end_to_end_speed_ratio=None)


def target_contract(costs):
    p=scope.ROOT/'docs/task042_neural_coarse_inverse/outcomes/records/target_gap_v58.json'
    prior=json.loads(p.read_text());bydegree=prior['FGMRES_restart32']
    return dict(parent=dict(path=str(p.relative_to(scope.ROOT)),sha256=digest(p)),
        existing_scenario=prior['parent_scope'],prior_FGMRES_V_Z_libraries=bydegree,
        new_mixed_control=dict(trace_degree=6,interior_degrees=[7,8],fixed_trace_port_rows=33660,
            one_complex128_trace_port_vector_bytes=33660*16,principal_V_Z_vectors_bytes=65*33660*16,
            actual_Krylov_allocation=False,topological_row_reduction_vs_uniform7=1-33660/46076,
            topological_row_reduction_vs_uniform8=1-33660/60476),
        interpretation='conditional global-interface/library reduction; not an RSS or runtime reduction by the same fraction',
        high_global_matrix_prototype=True,target_should_use='cellwise restricted Schur action R_e^H S_e R_e, not a target high global matrix',
        target_local_LU_recovery_bytes='unknown',target_iterations='unknown',target_factor_fill='unknown',
        target_complete_N1_seconds='unknown',target_simultaneous_RSS='unknown',
        target_2TB_48h_qualified=False,continuum_accuracy=False,NN_training=0,NN20=False,
        new_mesh_target_allocation=0,measured_increment={r['role']:dict(wall_seconds=r['launch_seconds'],sampled_peak_bytes=r['peak_bytes'])
            for r in costs if r['role'] in scope.SOLVES},
        next_decision='use actual paired fields and ambient diagnostics, not internal coefficient share, to select one next pilot')


def collect():
    import os
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}
    parents={r:dict(npz_sha256=scope.parent(r)['arrays']['sha256'],source_sha=scope.parent(r)['source_sha'],
        u_member_sha256=scope.parent(r)['arrays']['members']['u_storage']['sha256'],kappa_sha256=scope.parent(r)['arrays']['members']['kappa']['sha256']) for r in ('R6','R7')}
    pre=stages.get('PREFLIGHT',{});qualification={}
    for q,r in pre.get('degrees',{}).items():
        qualification[q]=dict(pass_gate=r['pass_gate'],actual_basis_dimension=r['actual_basis_dimension'],actual_local_interior=r['actual_local_interior'],
            trace_mapping=r['trace_mapping'],mapping_check=r['mapping_check'],body_q=r['body_certificate']['q'],body_certified=r['body_certificate']['pass_gate'],
            two_independent_raw_witnesses=[dict(cell=x['cell'],tag=x['tag'],q31_vector=x['q31_vector'],operation_scaled=x['operation_scaled'],arrays=x['arrays']) for x in r['raw_classes']],
            real_cell_schur_pair=r['one_real_cell_schur_pair'])
    data=dict(run_index_v59=dict(runs=runs,pointers=pointers,parents=parents),
        scientific_checks_v59=dict(candidates={r:compact_candidate(stages[r],pointers[r]) for r in scope.SOLVES if r in stages},
            qualification=qualification,small_block=pre.get('small'),verification=stages.get('VERIFY_COST'),
            optional_local_response=dict(status='not_run',reason='prioritize two complete physical solves and independent outputs; no additional diagnostic interface or factor'),
            NN_training=0,NN20=False,target_qualified=False,complete_ambient_high_space_pass=False,continuum_accuracy=False),
        resource_costs_v59=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),
            charged_known_lower_seconds=scope.window.charged_wall(),historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],
            historical_unknown='preserved; no invented old bill',deployments={r:deployment_receipt(r) for r in scope.SOLVES if r in stages},
            nonoverlap_policy='outer complete N1 inclusive; exclusive timings decompose it and are never added twice',
            nominal_sampling_seconds=.5,sampled_peak_is_not_continuous_hard_peak=True),
        physical_identity_bindings_v59=dict(physical=scope.plan_record()['physical_descriptor'],runs=bindings,numerical_cases=scope.plan_record()['cases'],
            physical_carrier=[8.94046081729244,.7821889682108057,0],G6_G7_not_used=True,
            mixed_J='identity on all ambient interiors, R_tau on trace and identity on all 828 port rows',conjugate_dual=True),
        target_gap_v59=target_contract(costs),
        repair_journal_v59=json.loads((scope.window.TMP/'repair_notes.json').read_text()))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V59_COMPACT_EVIDENCE_COLLECTED',records=str(out),increment_only=True)))


def main():
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v57.md',response_name='response_v59.md',outcome_name='trace_fixed_interior_enrichment_v59.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V59 explicit collector arguments')


if __name__=='__main__':main()
