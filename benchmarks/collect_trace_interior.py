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


def mixed_vector_check(r):
    v=checked_arrays(r['independent']['ambient_original']['arrays']);m=checked_arrays(r['trace_mapping']);a=checked_arrays(r['arrays'])
    R=sparse.csr_matrix((m['R_data'],m['R_indices'],m['R_indptr']),shape=tuple(m['R_shape']))
    if R.shape!=(r['case_spec']['trace'],32832) or len(a['port'])!=828 or len(a['low_trace'])!=32832:raise ValueError('complete mixed/canonical inventory')
    def pull(x):return np.r_[x[m['internal_rows']],R.conj().T@x[m['high_native_rows']]]
    rhs=pull(v['rhs']);den=max(np.linalg.norm(rhs),1e-30)
    residual=pull(v['residual']);top=pull(v['augmented_top'])
    fields={'true':float(np.linalg.norm(residual)/den),'native':float(np.linalg.norm(residual)/den),
        'augmented':float(np.linalg.norm(top)/den),'port':relative(v['port_residual'],v['projected'])}
    lift=relative(R@a['low_trace']-a['u_storage'][m['high_native_rows']],a['u_storage'][m['high_native_rows']])
    saved=checked_arrays(r['independent']['arrays'])
    for name,value in [('mixed_residual',residual),('mixed_augmented_top',top),('mixed_rhs',rhs),('ambient_residual',v['residual'])]:
        if not np.array_equal(value,saved[name]):raise ValueError('independent pullback member differs '+name)
    ids=v['internal_rows'];rec=float(np.max(v['internal_numerators']/np.maximum(v['internal_operation_scale'],1e-30)))
    identity=relative(v['volume_action']-v['volume_inside']-v['volume_trace'],np.maximum(np.abs(v['volume_inside']),np.abs(v['volume_trace'])))
    slave=bool(np.all(a['u_storage'][a['slaves']]==0))
    return dict(mixed=fields,mixed_rhs_norm=float(den),ambient_relative=relative(v['residual'],v['rhs']),
        ambient_internal_norm=float(np.linalg.norm(v['residual'][ids])),ambient_trace_norm=float(np.linalg.norm(v['residual'][m['high_native_rows']])),
        mapping_lift_operation=lift,recovery_operation_max=rec,split_identity_operation=identity,slave_zero=slave,
        pass_gate=max(fields.values())<=1e-6 and max(lift,rec,identity)<=1e-10 and slave,
        direct_target_pass=max(fields.values())<=1e-10,ambient_not_a_pass_prerequisite=True,NOT_A_FULL_AMBIENT_SOLUTION=True)


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


def main():
    import os
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    # The metadata settlement is completed after frozen VERIFY, never another
    # numerical solve hidden behind an auxiliary consumer.
    write_json(folder/'scope_clock.json',scope.window.snapshot())
    print(json.dumps(dict(status='V59_METADATA_CLOCK',clock=scope.window.snapshot())))


if __name__=='__main__':main()
