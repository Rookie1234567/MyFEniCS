"""Frozen V63 saved-field audits, bounded comparisons and incremental costs."""
import gc
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from src.runners.task042_shared import write_json
from src.solvers import fine_tetra_scope as scope
from src.solvers.scattering_anchor import save_arrays,relative
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers import independent_tetra_reference as core
from benchmarks.collect_independent_tetra import restored,saved_output_check,digest,deployment_from_parts,comparison as original_comparison


def pair(first,second,folder,journal):
    if first['spec']['complete_modes']!=second['spec']['complete_modes']:
        first=project_parent(first,second,folder,journal)
    qualified=scope.stage('PREFLIGHT').get('polynomial_pass',False)
    if qualified:
        from src.solvers.tetra_polynomial_difference import comparison
        try:return comparison(first,second,folder,journal)
        except ValueError as exc:
            write_json(folder/'fast_path_rejected.json',dict(error=str(exc),source=journal.source_state))
    return original_comparison(first,second,folder/'original_fallback',journal)


def project_parent(first,second,folder,journal):
    """Actual unchanged A field onto all M modes, including added 360."""
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.phase_notch_hp_modes import keyed_modes
    from src.solvers.dtn_port_3d import _port_power_metrics,_write_port_outputs
    import numpy as np
    import copy
    if (first['spec']['complete_modes'],second['spec']['complete_modes'])!=(828,1188):raise ValueError('unregistered tetra mode pair')
    folder.mkdir(parents=True,exist_ok=True);sub=folder/'parent_projected1188';sub.mkdir(exist_ok=True)
    s,v,_=restored(second,journal);parent=checked_arrays(first['arrays'])
    for key in ('geometry_x','geometry_dofmap','cell_tags','masters','kappa'):
        if not np.array_equal(parent[key],v[key]):raise ValueError('mode projection same original physical field geometry '+key)
    boundary=load_boundary(s,second['boundary_arrays'],second['mode_sha256']);_,D,H=core.boundary_matrices(s,boundary)
    with journal.measured('unchanged_A_actual_new360_mode_projection'):
        port=(D@parent['u_independent'])/H
        pm=_port_power_metrics(s['cfg'],boundary['modes'],port,boundary['projections'])
        _write_port_outputs(sub,s['cfg'],boundary['modes'],port,boundary['projections'],pm,s['mesh'].comm)
    old=json.loads(Path(first['output']['fields']['path']).with_name('port_power.json').read_text())
    fresh=json.loads((sub/'port_power.json').read_text());a=keyed_modes(old,828);b=keyed_modes(fresh,1188)
    x=np.array([complex(*a[k]['outgoing_amplitude_at_boundary']) for k in sorted(a)])
    y=np.array([complex(*b[k]['outgoing_amplitude_at_boundary']) for k in sorted(a)])
    defect=relative(y-x,x)
    if defect>1e-10:raise ValueError('unchanged A common828 mode projection')
    arrays=save_arrays(sub/'actual_all1188_projection.npz',port=port)
    result=copy.deepcopy(first);result['mode_power_path']=str(sub/'port_power.json')
    result['output']['port_metrics']=pm;result['spec']['complete_modes']=1188
    result['mode_projection']=dict(arrays=arrays,common828_relative=defect,added360_not_zeroed=True,original_array_sha256=first['arrays']['sha256'])
    write_json(folder/'projected_parent.json',result);del s,v,D,H,boundary;gc.collect();return result


def compare_gate():
    """Paid saved consumer before conditional M; no queue freeze/solve."""
    from src.solvers.scattering_anchor import Journal
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30)
    journal.source_state=json.loads((folder/'run_manifest.json').read_text())
    result=pair(scope.stage('A'),scope.stage('B'),folder/'A_B',journal)
    result['equation_parents_pass']=all(scope.stage(r)['equation_pass'] for r in ('A','B'))
    result['pass_gate']=result['pass_gate'] and result['equation_parents_pass']
    write_json(scope.ARTIFACT/'A_B_gate.json',result)
    print(json.dumps(dict(status='A_B_GATE_SAVED',pass_gate=result['pass_gate'])))


def verify(folder,journal):
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.independent_tetra_fields import tangential_check
    frozen_path=scope.window.TMP/'scientific_queue_frozen.json';frozen=json.loads(frozen_path.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(frozen_path):raise ValueError('V63 frozen live identity')
    states={};checks={};pairs={}
    for role,item in frozen['states'].items():
        r=scope.stage(role)
        if r['arrays']['sha256']!=item['array_sha256']:raise ValueError('V63 frozen field changed')
        states[role]=r;sub=folder/role;sub.mkdir(exist_ok=True)
        s,v,field=restored(r,journal);oracle=load_boundary(s,r['boundary_arrays'],r['mode_sha256'],q='q63')
        audit,res,rhs=core.audit(s,oracle,v['x'],v['rhs'],journal)
        receipt=save_arrays(sub/'independent_original.npz',residual=res,rhs=rhs,action=rhs-res,x=v['x'])
        previous=checked_arrays(r['audit']['arrays']);reproduction=relative(res-previous['residual'],rhs)
        tangent=tangential_check(s,field,sub);output=saved_output_check(r)
        checks[role]=dict(original=audit,arrays=receipt,producer_consumer_operation=reproduction,tangential=tangent,output=output,
            pass_gate=audit['pass_gate'] and reproduction<=1e-10 and tangent['pass_gate'] and output['pass_gate'])
        write_json(sub/'checker.json',checks[role]);write_json(folder/'state_inventory.json',checks)
        del s,v,field,oracle;gc.collect()
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    shim=SimpleNamespace(NAMESPACE='v61',window=scope.window,plan_record=scope.plan_record,
        stage=lambda role:dict(states[role],case_spec=states[role]['spec']))
    modal=modal_recalculation(scope=shim,role_names=tuple(states),output_folder=folder)
    from src.solvers import independent_tetra_scope as prior
    endpoints={r:prior.stage(r) for r in ('TH3','T5')}
    for a,b in (('TH3','A'),('T5','A'),('A','B'),('T5','B'),('A','M')):
        if b not in states or a not in states and a not in endpoints:continue
        if a=='A' and b=='B' and (scope.ARTIFACT/'A_B_gate.json').exists():result=json.loads((scope.ARTIFACT/'A_B_gate.json').read_text())
        else:result=pair(states.get(a,endpoints.get(a)),states[b],folder/(a+'_'+b),journal)
        pairs[a+'_'+b]=result;write_json(folder/'comparison_progress.json',pairs)
    # Historical hex comparison is optional after all selection/solver freeze.
    result=dict(status='COMPLETED',checks=checks,comparisons=pairs,modal=modal,
        fine_p_increment_pass=bool('A_B' in pairs and pairs['A_B']['pass_gate'] and all(checks[r]['pass_gate'] for r in ('A','B'))),
        new_numeric_factors=0,new_complete_solves=0,NN_training=0,NN20=False,target_qualified=False,source=journal.source_state)
    write_json(folder/'verification_scientific_result.json',result);return result


def collect():
    from benchmarks.collect_phase_deployment import cost_rows
    from benchmarks.collect_common_weak_phase import archive_increment
    from benchmarks.check_independent_tetra import saved_pair
    from src.solvers.independent_tetra_fields import selected_points
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir(exist_ok=True)
    runs=scope.window.ledger()['runs'];costs,sources,bindings=cost_rows(runs,active_scope=scope)
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    lifecycle={}
    for role in scope.SOLVES:
        if role not in stages:continue
        r=stages[role]
        if not r.get('arrays'):continue
        path=Path(r['arrays']['path']).parent
        symbolic=path/'h_symbolic_capacity.json';numeric=path/'h_numeric_factor_info.json'
        receipts=[dict(path=str(p),sha256=digest(p),**json.loads(p.read_text())) for p in scope.window.TMP.glob(role+'_one_run*/receipt.json')]
        lifecycle[role]=dict(nnz=r['nnz'],actual_FE=r['spec']['independent'],actual_rows=r['spec']['rows'],actual_native=r['arrays']['members']['u_native']['shape'][0],
            capacity=r['capacity'],symbolic=json.loads(symbolic.read_text()) if symbolic.exists() else None,
            numeric=json.loads(numeric.read_text()) if numeric.exists() else None,deployment=deployment_from_parts(receipts,r) if receipts else {'status':'unknown'},
            global_finite_LU_present=True,static_condensation=False,solution_bytes=Path(r['arrays']['path']).stat().st_size,
            boundary_bytes={q:Path(a['path']).stat().st_size for q,a in r['boundary_arrays'].items()})
    checks={}
    if 'VERIFY_COST' in stages:
        from src.solvers import independent_tetra_scope as prior
        parents={**stages,**{r:prior.stage(r) for r in ('TH3','T5')}}
        for name,p in stages['VERIFY_COST']['comparisons'].items():
            a,b=name.split('_');checks[name]=saved_pair(p,parents[a],parents[b],expected_points=selected_points(parents[b]['physical']))
            if not checks[name]['published_gate_matches_recalculation']:raise ValueError('V63 saved consumer verdict mismatch')
    data=dict(run_index_v63=dict(runs=runs,pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}),
        scientific_checks_v63=dict(stages=stages,NN20=False,continuum_accuracy=False,target_qualified=False),
        resource_costs_v63=dict(runs=costs,source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),charged_known_lower_seconds=scope.window.charged_wall(),historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],historical_unknown='preserved',nominal_sampling_seconds=.5,sampled_peak_not_continuous_hard_peak=True),
        storage_lifecycle_deployment_v63=dict(cases=lifecycle,complete_cold_cost_and_research_separate=True),
        independent_saved_pair_checks_v63=dict(pairs=checks,new_FE=0,new_numeric=0,new_solve=0),
        report_version_ruling_v63=json.loads((scope.window.TMP/'report_version_ruling.json').read_text()))
    for name,value in data.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources,active_scope=scope)
    print(json.dumps(dict(status='V63_COMPACT_COSTS',runs=len(runs),records=len(data))))


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--gate']:compare_gate()
    elif sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v61.md',response_name='response_v63.md',outcome_name='fine_tetra_accuracy_bounded_cost_v63.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V63 collector arguments')
