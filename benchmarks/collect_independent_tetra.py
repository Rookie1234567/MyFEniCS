"""Frozen independent tetra array/action consumers and compact incremental costs."""
import gc
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import independent_tetra_scope as scope
from src.solvers.scattering_anchor import save_arrays,relative
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers import independent_tetra_reference as core


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restored(record,journal):
    s=core.make_setup(record['spec'],record['physical'],journal);v=checked_arrays(record['arrays'])
    for key in s['geometry']:
        if not np.array_equal(s['geometry'][key],v[key]):raise ValueError('saved tetra geometry '+key)
    if not np.array_equal(v['kappa'],s['kappa']) or not np.array_equal(v['masters'],s['masters']):raise ValueError('saved tetra carrier/MPC')
    if not np.array_equal(v['u_native'],s['P']@v['u_independent']) or not np.array_equal(v['port'],v['x'][s['P'].shape[1]:]):raise ValueError('complete full tetra recovered coefficients')
    return s,v,core.restore_field(s,v['u_independent'])


def saved_output_check(record):
    output=record['output'];f=checked_arrays(output['fields']);values=[]
    if f['selected_points'].shape!=(240,3) or not np.array_equal(f['kappa'],checked_arrays(record['arrays'])['kappa']):raise ValueError('tetra complete field/selected/carrier inventory')
    for k in ('E','H','curl'):
        for kind in ('total','scattered'):
            if f['selected_'+k+'_'+kind].shape!=(240,3) or not np.isfinite(f['selected_'+k+'_'+kind]).all():raise ValueError('tetra finite physical vector inventory')
    for item in output['integrals']:
        a=checked_arrays(item['arrays']);values.append(a['per_cell_volume_absorption'].sum(axis=0))
    from src.common.modes_3d import incident_power_3d
    cfg=core.configuration(record['spec'],record['physical']);av=float(values[-1][1]*cfg.k0/(2*incident_power_3d(cfg)))
    pm=output['port_metrics'];vm=output['volume_metrics'];energy=pm['R_total']+pm['T_total']+av-1
    op=max(abs(av-vm['A_volume_total']),abs(energy-vm['energy_closure_error']))
    qdef=float(abs(values[0][1]-values[-1][1])/max(abs(values[-1][1]),1e-30))
    return dict(A_volume=av,energy=energy,operation_difference=op,q23_q31_relative=qdef,pass_gate=op<=1e-10 and abs(energy)<=1e-5 and qdef<=1e-10)


def comparison(first,second,folder,journal,*,old_hex=False,old_scope=None):
    from src.solvers.independent_tetra_fields import common_tetra_difference,common_hex_tetra_difference,selected_points
    from src.solvers.phase_notch_hp_modes import mode_comparison
    b,v,g=restored(second,journal)
    if old_hex:
        from src.solvers.phase_notch_hp import restore_record
        a=restore_record(first,journal,scope=old_scope);f=a[3]
        ka=checked_arrays(first['arrays'])['kappa']
        if not np.array_equal(ka,v['kappa']):raise ValueError('same physical carrier for old cross-check')
    else:a,va,f=restored(first,journal)
    folder.mkdir(parents=True,exist_ok=True);rows=[];pp=selected_points(second['physical'])
    for q in (23,31,39):
        if q==39 and quadrature_defect(rows[-2],rows[-1])<=1e-10:break
        r=common_hex_tetra_difference(f,g,b['cfg'],v['kappa'],journal,folder,q,pp) if old_hex else common_tetra_difference(f,g,b['cfg'],journal,folder,q,pp)
        rows.append(r);write_json(folder/f'common_q{q}.json',r)
    r=rows[-1];qdef=quadrature_defect(rows[-2],r);modes=mode_comparison(first,second,folder)
    pm={k:abs(first['output']['port_metrics'][k]-second['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    pm['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
    energies=[abs(s['output']['volume_metrics'].get('energy_closure_error',s['output']['volume_metrics'].get('energy_closure_error_port_volume'))) for s in (first,second)]
    maximum=max([x['relative'] for x in r['fields'].values()]+list(r['selected'].values()))
    r.update(quadrature_pair=[x['q'] for x in rows],quadrature_operation_scaled=qdef,q23_arrays=rows[0]['arrays'],modes=modes,power_differences=pm,energies=energies,
        parent_array_sha256=[first['arrays']['sha256'],second['arrays']['sha256']],physical_truth_not_assumed=True)
    r['pass_gate']=maximum<=1e-4 and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(pm.values())<=1e-5 and max(energies)<=1e-5
    r['classification']='SPACE_INCREMENT_PASS' if r['pass_gate'] else 'SPACE_INCREMENT_FAIL'
    write_json(folder/'comparison.json',r);del f,g,a,b;gc.collect();return r


def quadrature_defect(lo,hi):
    return max(abs(lo['fields'][k][n]-hi['fields'][k][n])/max(hi['fields'][k]['reference_squared'],1e-24) for k in hi['fields'] for n in ('difference_squared','reference_squared'))


def verify(folder,journal):
    from src.solvers.independent_tetra_fields import tangential_check
    p=scope.window.TMP/'scientific_queue_frozen.json';frozen=json.loads(p.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(p):raise ValueError('V62 live frozen consumer identity')
    checks={};states={}
    for role,item in frozen['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=item['array_sha256']:raise ValueError('frozen tetra field changed')
        states[role]=r;sub=folder/role;sub.mkdir(parents=True,exist_ok=True)
        with journal.measured('independent_saved_original_consumer_'+role):
            s,v,field=restored(r,journal);b=__import__('src.solvers.independent_tetra_study',fromlist=['load_boundary']).load_boundary(s,r['boundary_arrays'],r['mode_sha256'],q='q63')
            audit,res,rhs=core.audit(s,b,v['x'],v['rhs'],journal)
            arrays=save_arrays(sub/'independent_original.npz',residual=res,rhs=rhs,action=rhs-res,x=v['x'])
            saved=checked_arrays(r['audit']['arrays']);reproduction=relative(res-saved['residual'],rhs)
            tangent=tangential_check(s,field,sub);output=saved_output_check(r)
        checks[role]=dict(original=audit,arrays=arrays,producer_consumer_operation=reproduction,tangential=tangent,output=output,
            pass_gate=audit['pass_gate'] and reproduction<=1e-10 and tangent['pass_gate'] and output['pass_gate'])
        write_json(sub/'checker.json',checks[role]);write_json(folder/'state_inventory.json',checks)
        del s,v,field,b;gc.collect()
    # Use the qualified pure saved-mode checker with an explicit 828 inventory,
    # without importing any old FE field or old factor into the new solves.
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    shim=SimpleNamespace(NAMESPACE='v61',window=scope.window,plan_record=scope.plan_record,
        stage=lambda role:dict(states[role],case_spec={'complete_modes':828}))
    try:modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder)
    except ValueError as error:
        modal=dict(status='FAIL',reason=str(error));write_json(folder/'modal_checker_failure.json',modal)
    pairs={}
    for first,second in [('T4','T5'),('T5','TH3')]:
        if first in states and second in states:
            pairs[first+'_'+second]=comparison(states[first],states[second],folder/(first+'_'+second),journal)
            write_json(folder/'comparison_progress.json',pairs)
    # These old coefficients are first opened after the entire new solve queue
    # is frozen. They cannot initialize, choose or stop a new candidate.
    if 'T5' in states:
        from src.solvers import face_trace_scope as old
        for role in ('FXY','R7'):
            prior=old.stage(role) if role=='FXY' else old.parent(role)
            key=role+'_T5';pairs[key]=comparison(prior,states['T5'],folder/key,journal,old_hex=True,old_scope=old)
            write_json(folder/'comparison_progress.json',pairs)
    agreement=bool('T5_TH3' in pairs and pairs['T5_TH3']['pass_gate'])
    result=dict(status='COMPLETED',checks=checks,comparisons=pairs,modal=modal,
        classification='BOUNDED_INDEPENDENT_REFERENCE_AGREEMENT' if agreement else 'NO_CROSS_REFERENCE_AGREEMENT',
        new_numeric_factors=0,new_complete_solves=0,NN_training=0,NN20=False,target_qualified=False,source=journal.source_state)
    write_json(folder/'verification_scientific_result.json',result);return result


def deployment(role):
    receipts=sorted(scope.window.TMP.glob(role+'_one_run*/receipt.json'))
    if not receipts:return dict(status='unknown',reason='missing outer process timing')
    r=scope.stage(role);parts=[dict(path=str(p),sha256=digest(p),**json.loads(p.read_text())) for p in receipts]
    seconds=sum(x['elapsed_seconds'] for x in parts)
    return dict(status='measured_complete' if r.get('deployment_complete') else 'partial',T_N1_process_chain_seconds=seconds,receipts=parts,
        numerical_objects_fresh_per_case=True,OS_JIT_caches_not_cleared=True,full_N1_includes_independent_audit_outputs_IO_cleanup=True,
        recovery_no_condensation='all native FE reconstructed with actual periodic P',research_comparisons_not_included=True,
        speed_ratio_same_accuracy='not_granted_without_complete_matched_accuracy_control')


def collect():
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir(exist_ok=True)
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()};ptr={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}
    repairs=scope.window.TMP/'repair_journal.jsonl'
    data=dict(run_index_v62=dict(runs=runs,pointers=ptr,old_windows_closed=True),
        scientific_checks_v62=dict(stages=stages,NN_training=0,NN20=False,continuum_accuracy=False,target_qualified=False),
        resource_costs_v62=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),charged_known_lower_seconds=scope.window.charged_wall(),
            historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],historical_unknown='preserved',deployments={r:deployment(r) for r in scope.SOLVES if r in stages},
            nominal_sampling_seconds=.5,sampled_peak_not_continuous_hard_peak=True,inclusive_N1_not_added_to_nested_timers=True),
        repair_journal_v62=dict(entries=[json.loads(x) for x in repairs.read_text().splitlines()] if repairs.exists() else [],failures_preserved=True),
        target_gap_v62=dict(new_representation='FULL_UNCONDENSED_TETRA_N1CURL_PHASE_UFL',global_finite_factor_present=True,
            target_accuracy_mesh='unknown',target_modes='unknown',target_PC_factor_fill='unknown',target_iterations='unknown',target_N1='unknown',target_simultaneous_RSS='unknown',
            target_2TB48h_qualified=False,NN20=False,next_pilot_basis='actual independent field agreement, not fewer DOFs alone'))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V62_COMPACT_COSTS',runs=len(runs),records=len(data))))


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v60.md',response_name='response_v62.md',outcome_name='independent_tetra_reference_v62.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V62 collector arguments')
