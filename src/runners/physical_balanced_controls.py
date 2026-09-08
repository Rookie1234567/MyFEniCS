"""E1 finite common-input evaluation over the existing single diagnostic stack."""
import json
from pathlib import Path
import numpy as np
from .actual_error_diagnosis import checked_json
from .physical_diagnostic_completion import load_packet, independent_item


def load_balanced_inputs(inputs):
    center=json.loads(Path('docs/task039_extra_physical_multilevel/outcomes/records/actual_error_diagnosis_v5.json').read_text())
    binding=center['audits']['actual_errors_v1_formal_audit.json']
    audit=checked_json(binding['path'],binding['sha256'])
    hashes={v['path']:v['sha256'] for v in audit['artifact_hashes']}
    root=Path(center['reproducibility']['raw_root'])
    samples={}
    for label in ('A2R160','LIGHT448','JOINT448'):
        for suffix in ('actual_error','projection'):
            path=root/(label+'_'+suffix+'.json');checked_json(path,hashes[str(path)])
        error=load_packet(root/(label+'_actual_error.json'))
        projection=load_packet(root/(label+'_projection.json'))
        if not np.array_equal(error['e'],inputs['reference']['x']-inputs['packets'][label+'_identity']['x']):
            raise ValueError('balanced input is not the approved actual error')
        samples[label]=dict(e=error['e'],q=error['q'],projection=projection,
            evidence=dict(error=str(root/(label+'_actual_error.json')),error_sha256=hashes[str(root/(label+'_actual_error.json'))]))
    manifest=inputs['manifest']
    old=checked_json(manifest['completion_audit'],manifest['completion_audit_sha256'])
    old_hashes={v['path']:v['sha256'] for v in old['evidence']}
    path=Path(manifest['completion_root'])/'known_original.json';checked_json(path,old_hashes[str(path)])
    known=load_packet(path)
    samples['V4_KNOWN']=dict(e=known['e'],q=known['q'],evidence=dict(path=str(path),sha256=old_hashes[str(path)]))
    return samples


def run_balanced_controls(bundle,cfg,actions,b,directory,source_sha,ledger,sample,summary,inputs):
    from .physical_diagnosis_worker import save_packet
    from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling, ROUTES, BalancedNumericalRejected
    from src.solvers.fullspace_physical_intermediate_runtime import attach_physical_reference
    from src.solvers.physical_reference_diagnostics import DiagnosticRefinementV4
    from src.solvers.physical_error_diagnostics import metric_square
    from .workflow_timebase import clock_sample, checked_interval
    save=lambda name,facts:save_packet(directory,name,facts)
    if not np.array_equal(b,inputs['reference']['b']):raise ValueError('E1 native RHS mismatch')
    for degree in (6,4):
        current=load_packet(directory/f'native_constraint_map_p{degree}.json')
        for key,value in inputs['packets'][f'native_constraint_map_p{degree}'].items():
            if isinstance(value,np.ndarray) and not np.array_equal(value,current[key]):raise ValueError('E1 native mapping mismatch')
    samples=inputs['balanced_samples']
    control=np.zeros(actions.P.source.getLocalSize(),complex)
    control[actions.P.indices]=samples['A2R160']['projection']['coarse']
    policy=DiagnosticRefinementV4(save,bundle['actions']['physical'][4]['dtn_action'],control,
        dict(source_sha=source_sha,physical=inputs['reference']['identity'],purpose='E1 new balanced inputs, no old rejection replay'),
        logical_limit=55,solve_limit=165,replay_first_failure=False,verify_first_actions=False)
    ledger.marker('balanced_reference_started',{})
    attach_physical_reference(bundle,cfg,resource_sample=sample,marker=ledger.marker,diagnostic_refinement_v4=policy)
    actions.attach_reference(bundle)
    policy.identity.update(matrix=bundle['reference_matrix_facts'],
        constraints=load_packet(directory/'native_constraint_map_p4.json')['arrays'],
        mode_sha256=bundle['fine']['mode_sha256'],quadrature=bundle['actions']['volume_quadrature_metadata'])
    def coarse(q):return actions.P(actions.solve(actions.PH(q)))
    pcs={route:PhysicalBalancedCoupling(actions.A,coarse,
        actions.smoothers['S6_complement' if route=='BAL_S' else 'H6'],actions.PH,
        route=route,checkpoint=sample) for route in ROUTES}
    summary.update(complete_pc_attempted=0,complete_pc_calls=0,reference='MATCHED_REFERENCE_EVALUATION_ONLY',
        projection_calls=0,routes={},items={})
    from src.io.physical_balanced_profile import BALANCED_PROFILES, balanced_profile_facts
    save('balanced_profiles', {name:balanced_profile_facts(name) for name in BALANCED_PROFILES})
    range_e=samples['A2R160']['projection']['parallel']
    sequence=[(name,v['e'],v['q']) for name,v in samples.items()]+[('RANGE',range_e,None)]
    blocked_routes=set()
    try:
        for label,e,saved_q in sequence:
            q=actions.A(e)
            if saved_q is not None:
                difference=float(np.linalg.norm(q-saved_q)/max(np.linalg.norm(q),np.finfo(float).tiny))
                if difference>1e-10:raise ValueError('E1 saved A6 action mismatch')
            scale=float(np.linalg.norm(q))
            if not np.isfinite(scale) or scale==0:raise ValueError('E1 nonzero control required')
            en,qn=e/scale,q/scale
            save(label+'_balanced_input',dict(e=en,q=qn,normalization_scale=scale,
                role='primal/dual scaled together; actual q=Ae, not old r',reference_only_in_evaluator=True))
            for route,pc in pcs.items():
                name=label+'_'+route;policy.label=name
                if route in blocked_routes:
                    save(name,dict(status='not_run_route_rejected',route=route))
                    summary['items'][name]='skipped'
                    continue
                summary['complete_pc_attempted']+=1
                if summary['complete_pc_attempted']>15:raise RuntimeError('E1 15 PC cap')
                def evaluate():
                    before=dict(policy.action_counts,MatSolve=policy.external_solves)
                    started=clock_sample();z=pc.apply(qn);az=actions.A(z)
                    remaining=en-z;dual=qn-az
                    phq=actions.PH(qn);phaz=actions.PH(az)
                    defect=float(np.linalg.norm(phq-phaz)/max(np.linalg.norm(phq)+np.linalg.norm(phaz),np.finfo(float).tiny))
                    remaining_mass=metric_square(actions.M0,remaining)
                    input_mass=metric_square(actions.M0,en)
                    range_relative=float(np.sqrt(remaining_mass/max(input_mass,np.finfo(float).tiny))) if label=='RANGE' else None
                    range_scaled=(float(np.sqrt(remaining_mass)/max(np.sqrt(input_mass)+
                        np.sqrt(metric_square(actions.M0,z)),np.finfo(float).tiny)) if label=='RANGE' else None)
                    return dict(z=z,Az=az,remaining_L2_squared=remaining_mass,
                        remaining_scaled_curl_squared=metric_square(actions.metrics[6].curl,remaining),
                        input_L2_squared=input_mass,input_scaled_curl_squared=metric_square(actions.metrics[6].curl,en),
                        true_residual_ratio=float(np.linalg.norm(dual)/np.linalg.norm(qn)),
                        coarse_balance_relative=defect,coarse_balance_limit=1e-8,
                        finite_eligible=bool(defect<=1e-8 and (range_scaled is None or range_scaled<=1e-8)),
                        range_identity_relative=range_relative,range_identity_operation_scaled=range_scaled,
                        range_identity_limit=1e-8,single_rho_below_one_required=False,
                        p4_action_counts={key:value-before[key] for key,value in
                            dict(policy.action_counts,MatSolve=policy.external_solves).items()},
                        stages=pc.last_apply_facts,cost=checked_interval(started,clock_sample(),policy=ledger.timebase_policy))
                try:
                    result=independent_item(name,evaluate,save,summary,ledger.marker)
                except BalancedNumericalRejected as exc:
                    save(name,dict(status='combination_numerical_rejected',exception_type=type(exc).__name__,
                        rejection=exc.facts,stages=pc.last_apply_facts,input_packet=label+'_balanced_input.json',
                        completed_output_available=False))
                    summary['items'][name]='rejected'
                    blocked_routes.add(route)
                    result=None
                if result is not None:
                    summary['complete_pc_calls']+=1
                    summary['routes'].setdefault(route,[]).append(dict(input=label,eligible=result['finite_eligible'],
                        true_residual_ratio=result['true_residual_ratio']))
    finally:
        summary.update(logical_p4_rhs=policy.logical_rhs,external_MatSolve_calls=policy.external_solves,
            reference_records=policy.records,p4_action_counts=policy.action_counts,timings=actions.timings)
    summary['candidate_eligibility']={route:len(summary['routes'].get(route,[]))==5 and
        all(v['eligible'] for v in summary['routes'].get(route,[])) for route in ROUTES}
    summary['status']='BALANCED_E1_COMPLETED' if all(summary['candidate_eligibility'].values()) else 'BALANCED_E1_COMPLETED_WITH_LIMITATIONS'
