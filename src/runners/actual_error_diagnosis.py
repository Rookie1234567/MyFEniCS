"""Thin matched-error sequence over the existing diagnostic builder/actions."""
import hashlib
import json
from pathlib import Path
import numpy as np

from .physical_diagnostic_completion import load_packet,independent_item

LABELS=('A2R160','LIGHT448','JOINT448')


def checked_json(path,digest):
    path=Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('evidence hash mismatch: '+str(path))
    return json.loads(path.read_text())


def load_actual_evidence(manifest_path,inventory_path,reused):
    from .fine_reference_preflight import input_identity
    manifest=json.loads(Path(manifest_path).read_text())
    inventory=checked_json(inventory_path,manifest['inventory_sha256'])
    if manifest['samples']!=list(LABELS):raise ValueError('actual-error sample order differs')
    packets,evidence=reused
    audit=checked_json(manifest['reference_audit'],manifest['reference_audit_sha256'])
    hashes={e['path']:e['sha256'] for e in audit['artifact_hashes']}
    root=Path(manifest['reference_root']);references={}
    for name in ('reference_full_residual','reference_native_map','reference_candidate_initial'):
        path=root/(name+'.json');checked_json(path,hashes[str(path)])
        references[name]=load_packet(path)
    payload_path=root/'input_resolved.json';payload=checked_json(payload_path,hashes[str(payload_path)])
    bridge=input_identity(payload)
    reference=references['reference_full_residual'];mapping=references['reference_native_map'];indices=mapping['independent_indices']
    identity=reference['identity']
    if (identity['source_sha']!=manifest['reference_source_sha'] or
        any(identity[k]!=v for k,v in bridge.items()) or
        bridge['original_physical_sha256']!=inventory['samples'][0]['physical_sha256'] or
        identity['mode_sha256']!=packets['rhs']['facts']['mode_manifest_sha256']):
        raise ValueError('reference source/physical backend bridge/mode mismatch')
    for key,value in packets['native_constraint_map_p6'].items():
        if isinstance(value,np.ndarray) and not np.array_equal(value,mapping[key]):raise ValueError('reference native map mismatch: '+key)
    for name in ('x_ref','b','ax','r'):
        value=reference[name]
        if value.shape!=(173802,) or not np.isfinite(value).all() or np.any(value[mapping['slaves']]!=0):
            raise ValueError('illegal reference vector: '+name)
    relative=np.linalg.norm(reference['b']-reference['ax'])/np.linalg.norm(reference['b'])
    if relative>1e-10 or not np.array_equal(reference['b']-reference['ax'],reference['r']):
        raise ValueError('reference native residual no longer qualifies')
    if not np.array_equal(reference['b'][indices],packets['rhs']['b']):raise ValueError('reference RHS differs from old snapshots')
    for label in LABELS:
        source=next(s for s in inventory['samples'] if s['label']==label)
        path=Path(source['path']);original=checked_json(path/'manifest.json',source['manifest_sha256'])
        raw_path=path/'solution_rank0.npy'
        if hashlib.sha256(raw_path.read_bytes()).hexdigest()!=source['solution_sha256']:raise ValueError('snapshot solution hash mismatch')
        raw=np.load(raw_path,allow_pickle=False)
        operator=hashlib.sha256(json.dumps(dict(source_sha=original['source_sha'],physical=original['physical_model_sha256'],
            modes=identity['mode_sha256'],quadrature=reference['quadrature']),sort_keys=True).encode()).hexdigest()
        if (raw.shape!=(173802,) or np.any(raw[mapping['slaves']]!=0) or not np.isfinite(raw).all() or
            not np.array_equal(raw[indices],packets[label+'_identity']['x']) or
            original['physical_model_sha256']!=bridge['original_physical_sha256'] or operator!=original['operator_identity_sha256']):
            raise ValueError('snapshot coordinate/operator chain mismatch: '+label)
    completed=checked_json(manifest['completion_audit'],manifest['completion_audit_sha256'])
    completed_hashes={e['path']:e['sha256'] for e in completed['evidence']}
    for name in ('JOINT448_LIGHT','JOINT448_JOINT'):
        path=Path(manifest['completion_root'])/(name+'.json');checked_json(path,completed_hashes[str(path)])
        packet=load_packet(path)
        if packet['status']!='completed':raise ValueError('old completed PC packet is not complete')
        packets[name]=packet['result']
    initial=references['reference_candidate_initial']['x_ref']
    if initial.shape!=(173802,) or not np.isfinite(initial).all() or np.any(initial[mapping['slaves']]!=0):raise ValueError('invalid initial reference candidate')
    ref=dict(x=reference['x_ref'][indices],b=reference['b'][indices],ax=reference['ax'][indices],
        r=reference['r'][indices],delta=(reference['x_ref']-initial)[indices],identity=identity,
        quadrature=reference['quadrature'],map=mapping,relative_residual=float(relative))
    return dict(reference=ref,packets=packets,manifest=manifest,old_evidence=evidence)


def run_actual_errors(bundle,cfg,actions,b,directory,source_sha,ledger,sample,summary,inputs):
    from .physical_diagnosis_worker import save_packet
    from src.solvers.physical_error_diagnostics import (metric_square,copied_apply,evaluate_profiles,
        coarse_diagnostics,coarse_identity_diagnostics)
    from src.solvers.actual_error_diagnostics import (error_identity,saved_pc_error,cell_energy_summary,coarse_gap_closure)
    from src.solvers.fullspace_physical_intermediate_runtime import attach_physical_reference
    from src.solvers.physical_reference_diagnostics import DiagnosticRefinementV4
    from src.solvers.fullspace_p4_reference import ReferenceResourceBlocked
    from src.solvers.physical_error_metric import SerialAction
    def save(name,facts):save_packet(directory,name,facts)
    ref=inputs['reference'];packets=inputs['packets']
    summary.update(reference='MATCHED_DISCRETE_REFERENCE_PASS',complete_pc_calls=0,independent_smoother_calls=0,
                   independent_smoother_attempted=0,logical_p4_rhs=0,external_MatSolve_calls=0,closure_checks={})
    save('actual_input_identity',dict(manifest=inputs['manifest'],reference_identity=ref['identity'],
        reference_relative_residual=ref['relative_residual'],old_evidence=inputs['old_evidence']))
    for degree in (6,4):
        current=load_packet(directory/f'native_constraint_map_p{degree}.json')
        for key,value in packets[f'native_constraint_map_p{degree}'].items():
            if isinstance(value,np.ndarray) and not np.array_equal(value,current[key]):raise ValueError('rebuilt actual-error map mismatch')
    if not np.array_equal(b,ref['b']):raise ValueError('rebuilt actual-error RHS differs')
    if tuple(bundle['actions']['volume_quadrature_metadata'])!=tuple(ref['quadrature']):raise ValueError('actual-error quadrature differs')
    M=actions.M0;curl=actions.metrics[6].curl
    ref_metrics=dict(L2_squared=metric_square(M,ref['x']),scaled_curl_squared=metric_square(curl,ref['x']))
    delta_metrics=dict(L2_squared=metric_square(M,ref['delta']),scaled_curl_squared=metric_square(curl,ref['delta']))
    save('reference_primal_sensitivity',dict(reference=ref_metrics,initial_to_corrected=delta_metrics,
        interpretation='one augmented correction sensitivity; no strict forward/continuum bound'))
    errors={};projections={};mass_errors=[]
    for label in LABELS:
        ledger.marker(label+'_actual_error_started',{});sample()
        old=packets[label+'_identity']
        facts=error_identity(actions.A,ref['x'],old['x'],old['r'],ref['r'],ref['ax'],old['ax'])
        save(label+'_actual_error',facts)
        if facts['closure_relative_to_operations']>1e-10:raise ValueError('actual error A6/residual bridge failed: '+label)
        errors[label]=facts;e=facts['e']
        me=copied_apply(M,e);mass_errors.append(me)
        energies=dict(L2_squared=metric_square(M,e),scaled_curl_squared=metric_square(curl,e))
        save(label+'_primal_metrics',dict(energies=energies,
            relative_to_reference={k:float(np.sqrt(v/max(ref_metrics[k],np.finfo(float).tiny))) for k,v in energies.items()},
            reference_correction_over_error={k:float(np.sqrt(delta_metrics[k]/max(v,np.finfo(float).tiny))) for k,v in energies.items()}))
        cells=actions.metrics[6].cell_energies(e,checkpoint=sample)
        groups=cell_energy_summary(cells,energies['L2_squared'],energies['scaled_curl_squared'])
        save(label+'_cell_energies',dict(**cells,summary=groups))
        if max(groups['global_relative_defects'].values())>1e-9:raise ValueError('cell integrals do not match global metric')
        ledger.marker(label+'_projection_started',{})
        projection=actions.project(e,checkpoint=sample,retain_approximation=True);projections[label]=projection
        save(label+'_projection',dict(**projection,cumulative_projection_seconds=actions.projection_seconds))
        ledger.marker(label+'_projection_completed',dict(status=projection['status'],cumulative_seconds=actions.projection_seconds))
    gram=np.array([[np.vdot(errors[left]['e'],me) for me in mass_errors] for left in LABELS])
    save('actual_error_M0_gram',dict(labels=LABELS,gram=gram,roles='primal errors; unweighted L2 Gram'))
    for label in LABELS:
        projection=projections[label]
        if projection['status']=='PROJECTION_CLOSED' and np.linalg.norm(projection['perpendicular'])>0:
            for name,smoother in actions.smoothers.items():
                summary['independent_smoother_attempted']+=1
                if summary['independent_smoother_attempted']>6:raise RuntimeError('smoother budget exceeded')
                result=evaluate_profiles(actions.A,M,projection['perpendicular'],{name:smoother},checkpoint=sample)
                save(label+'_complement_'+name,dict(**result,cost=actions.timings[-1]))
                summary['independent_smoother_calls']+=1
        else:save(label+'_complement_skipped',dict(status='skipped',projection=projection['status']))
        for name in ('S6','LIGHT','JOINT'):
            result=saved_pc_error(M,errors[label]['e'],packets[label+'_identity']['r'],ref['r'],packets[label+'_'+name])
            save(label+'_saved_'+name,dict(**result,source_strategy='V4 refined diagnostic' if label=='JOINT448' and name!='S6' else 'V3 original once-backsolve',
                saved_PC_packet=label+'_'+name))
    # All no-LU-dependent evidence is now durable. One p4 factor follows.
    control=np.zeros(actions.P.source.getLocalSize(),dtype=np.complex128)
    control[actions.P.indices]=projections[LABELS[0]]['coarse']
    identity=dict(source_sha=source_sha,physical_sha256=ref['identity']['original_physical_sha256'],
        mode_sha256=ref['identity']['mode_sha256'],quadrature=ref['quadrature'],
        constraints=load_packet(directory/'native_constraint_map_p4.json')['arrays'],purpose='matched actual errors')
    policy=DiagnosticRefinementV4(save,bundle['actions']['physical'][4]['dtn_action'],control,identity)
    ledger.marker('actual_p4_reference_started',{})
    try:attach_physical_reference(bundle,cfg,resource_sample=sample,marker=ledger.marker,diagnostic_refinement_v4=policy)
    except ReferenceResourceBlocked as exc:
        save('actual_p4_skipped',dict(status='CAPACITY_NOT_ADMITTED',reason=str(exc)))
        summary.update(projection_seconds=actions.projection_seconds,timings=actions.timings)
        summary['status']='ACTUAL_ERRORS_COMPLETED_WITH_LIMITATIONS';return
    identity['matrix']=bundle['reference_matrix_facts']
    digest=hashlib.sha256()
    for row in range(bundle['reference_matrix'].getSize()[0]):
        columns,values=bundle['reference_matrix'].getRow(row)
        digest.update(np.asarray([row,len(columns)],dtype=np.int64).tobytes())
        digest.update(columns.tobytes());digest.update(values.tobytes())
    identity['matrix_sha256']=digest.hexdigest()
    digest=hashlib.sha256()
    for entry in policy.carrier_action.carrier.entries:
        for value in (entry.coupling_rows,entry.coupling_values,entry.projection_rows,
                      entry.projection_values,np.asarray([entry.normalization_h])):
            digest.update(np.asarray(value).tobytes())
    identity['carrier']=dict(port_count=len(policy.carrier_action.carrier.entries),
        representation='existing sparse carrier',sha256=digest.hexdigest())
    actions.attach_reference(bundle)
    A4=SerialAction(bundle['levels']['spaces'][4],bundle['levels']['floquets'][4],bundle['actions']['physical'][4]['physical_action'].apply)
    def solve(g):
        if policy.logical_rhs>=4:raise RuntimeError('actual-error p4 RHS budget exceeded')
        save(policy.label+'_coarse_rhs',dict(g=g,role='dual PH A6 e'))
        result=actions.solve(g)
        if policy.external_solves>12:raise RuntimeError('actual-error MatSolve budget exceeded')
        return result
    try:
        for label in LABELS:
            policy.label=label+'_coarse'
            result=independent_item(label+'_coarse',lambda label=label:coarse_diagnostics(actions.A,M,actions.P,actions.PH,
                solve,errors[label]['e'],projections[label],identity_check=False,saved_q=errors[label]['q']),save,summary,ledger.marker)
            if result is not None:
                gap=coarse_gap_closure(A4,actions.PH,actions.A,projections[label],result,M)
                checks=dict(decomposition=dict(value=result['decomposition_relative_defect'],limit=1e-9,
                    qualified=result['decomposition_qualified'] and result['decomposition_relative_defect']<=1e-9),
                    coarse_gap=dict(value=gap['closure_relative_to_operations'],limit=1e-10,
                    qualified=gap['projection_qualified'] and gap['closure_relative_to_operations']<=1e-10))
                summary['closure_checks'][label]=checks
                save(label+'_coarse_gap',dict(**gap,closure_checks=checks))
        eligible=next((label for label in LABELS if projections[label]['status']=='PROJECTION_CLOSED' and
                       np.linalg.norm(projections[label]['parallel'])>0),None)
        if eligible:
            policy.label='actual_range_identity'
            result=independent_item('actual_range_identity',lambda:coarse_identity_diagnostics(actions.A,M,actions.P,
                actions.PH,solve,projections[eligible]['parallel']),save,summary,ledger.marker)
            if result is not None:
                value=result['coarse_identity_relative_field_error']
                check=dict(value=value,limit=1e-8,qualified=value<=1e-8)
                summary['closure_checks']['range_identity']={'field':check}
                save('actual_range_identity_qualification',check)
        else:
            save('actual_range_identity',dict(status='skipped',dependency='no qualified nonzero projection'))
            summary.setdefault('items',{})['actual_range_identity']='skipped'
    finally:
        A4.destroy()
        summary.update(logical_p4_rhs=policy.logical_rhs,external_MatSolve_calls=policy.external_solves,
                       reference_records=policy.records,timings=actions.timings,projection_seconds=actions.projection_seconds)
    summary['status']='ACTUAL_ERRORS_COMPLETED_WITH_LIMITATIONS' if (
        any(p['status']!='PROJECTION_CLOSED' for p in projections.values()) or
        any(not check['qualified'] for group in summary['closure_checks'].values() for check in group.values()) or
        any(v in ('rejected','skipped') for v in summary.get('items',{}).values())) else 'ACTUAL_ERRORS_COMPLETED'
