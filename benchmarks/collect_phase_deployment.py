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


if __name__=='__main__':
    raise SystemExit('Use the one-run VERIFY_COST or explicit final metadata collector; no implicit PDE')
