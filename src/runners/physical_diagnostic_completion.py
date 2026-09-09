"""Review V4 dependency order, using existing numerical diagnostic functions."""
import hashlib
import json
from pathlib import Path

import numpy as np

from src.solvers.physical_reference_diagnostics import ReferenceAccuracyRejected, ReferenceDependencySkipped, EvidenceBlocked


def finalize_diagnostics(summary, finalizers, write, primary=None):
    """Attempt all cleanup and atomically write the summary even after a destructor fails."""
    errors=[]
    for finalizer in finalizers:
        try:
            finalizer()
        except BaseException as exc:
            errors.append(dict(type=type(exc).__name__,message=str(exc)))
    summary['cleanup_errors']=errors
    if errors and primary is None:
        summary['status']='CLEANUP_FAILED'
    write()
    if errors and primary is None:
        raise RuntimeError('diagnostic cleanup failed; summary retained')


def independent_item(name, operation, save, summary, marker):
    """Only reference accuracy is a local refusal; all other errors propagate."""
    summary.setdefault('items',{})[name]='started'
    marker(name+'_started',{})
    try:
        result=operation()
    except ReferenceDependencySkipped as exc:
        save(name,dict(status='skipped',reference=exc.facts))
        summary['items'][name]='skipped'
        marker(name+'_skipped',exc.facts)
        return None
    except ReferenceAccuracyRejected as exc:
        save(name,dict(status='rejected',reference=exc.facts))
        summary['items'][name]='rejected'
        marker(name+'_rejected',exc.facts)
        return None
    save(name,dict(status='completed',result=result))
    summary['items'][name]='completed'
    marker(name+'_completed',{})
    return result


def load_packet(path):
    record=json.loads(path.read_text())
    arrays={}
    if 'arrays' in record:
        target=Path(record['arrays']['path'])
        if hashlib.sha256(target.read_bytes()).hexdigest()!=record['arrays']['sha256']:
            raise ValueError('packet array hash mismatch: '+str(path))
        with np.load(target,allow_pickle=False) as archive:
            arrays={k:archive[k].copy() for k in archive.files}
    def expand(value):
        if isinstance(value,dict):
            if 'array_key' in value:return arrays[value['array_key']]
            return {k:expand(v) for k,v in value.items()}
        if isinstance(value,list):return [expand(v) for v in value]
        return value
    try:
        return expand(record)
    finally:
        # Returned arrays have their own owners; the recursive closure must not retain extras.
        arrays.clear()


def reuse_v3(inventory):
    """Verify immutable old packets and recompute their scalar claims without PC calls."""
    root=Path(inventory['latest_formal_attempt']['root'])
    entry=next(e for e in inventory['latest_evidence'] if e['path'].endswith('/diagnostic_audit.json'))
    audit_path=Path(entry['path'])
    if hashlib.sha256(audit_path.read_bytes()).hexdigest()!=entry['sha256']:
        raise ValueError('old diagnostic audit hash mismatch')
    hashes={e['path']:e['sha256'] for e in json.loads(audit_path.read_text())['evidence']}
    names=[label+'_'+pc for label,pcs in [('A2R160',('S6','LIGHT','JOINT')),
             ('LIGHT448',('S6','LIGHT','JOINT')),('JOINT448',('S6',))] for pc in pcs]
    names += [label+'_identity' for label in ('A2R160','LIGHT448','JOINT448')]
    names += ['rhs','native_constraint_map_p6','native_constraint_map_p4']
    packets={}; evidence=[]
    for name in names:
        path=root/(name+'.json')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=hashes[str(path)]:raise ValueError('old packet hash mismatch: '+name)
        packets[name]=load_packet(path)
        evidence.append(dict(path=str(path),sha256=digest))
    for name in names[:7]:
        packet=packets[name]
        item=next(iter(packet['profiles'].values()))
        measured=np.linalg.norm(packet['normalized_q']-item['applied_direction'])/np.linalg.norm(packet['normalized_q'])
        if not np.isclose(measured,item['true_residual_ratio'],rtol=1e-13,atol=0):
            raise ValueError('old PC residual does not recompute: '+name)
    b=packets['rhs']['b']
    for label in ('A2R160','LIGHT448','JOINT448'):
        p=packets[label+'_identity']
        if not np.array_equal(b-p['ax'],p['r']):raise ValueError('old identity residual differs')
        if not np.isclose(np.linalg.norm(p['r'])/np.linalg.norm(b),p['recomputed_true_residual'],rtol=1e-13):
            raise ValueError('old identity scalar differs')
    return packets,evidence


def run_completion_controls(bundle,cfg,actions,b,inventory,directory,source_sha,ledger,sample,summary,reused):
    from .physical_diagnosis_worker import save_packet
    from src.solvers.fullspace_physical_intermediate_runtime import attach_physical_reference
    from src.solvers.fullspace_p4_reference import ReferenceResourceBlocked
    from src.solvers.physical_reference_diagnostics import DiagnosticRefinementV4
    from src.solvers.physical_error_metric import interpolate_known_error
    from src.solvers.physical_error_diagnostics import (metric_square, correction_diagnostics,
        coarse_diagnostics, coarse_identity_diagnostics, evaluate_profiles,
        evaluate_residual_profiles, homogeneity_check)
    def save(name,facts):
        try:
            save_packet(directory,name,facts)
        except Exception as exc:
            raise EvidenceBlocked('required diagnostic packet: '+name) from exc
    packets,evidence=reused
    save('reused_v3',dict(evidence=evidence,completed_PC=7,identities=3,recomputed_without_PC=True))
    for degree in (6,4):
        name='native_constraint_map_p'+str(degree)
        current=load_packet(directory/(name+'.json'))
        for key,value in packets[name].items():
            if isinstance(value,np.ndarray) and not np.array_equal(value,current[key]):
                raise ValueError('native constraint map mismatch: '+name+'/'+key)
    old=packets['JOINT448_identity']
    ax=actions.A(old['x'])
    relative=float(np.linalg.norm(ax-old['ax'])/max(np.linalg.norm(old['ax']),np.finfo(float).tiny))
    save('C1_connection',dict(x=old['x'],ax=ax,relative=relative,limit=1e-10,
        b_matches_old=bool(np.array_equal(b,packets['rhs']['b'])),old_evidence=evidence))
    if relative>1e-10 or not np.array_equal(b,packets['rhs']['b']):
        raise ValueError('fine operator/RHS connection failed')
    levels=bundle['levels']
    e_raw=interpolate_known_error(levels['spaces'][6],levels['floquets'][6],cfg,actions.A.indices)
    q_raw=actions.A(e_raw)
    save('known_original',dict(e=e_raw,q=q_raw,recipe=inventory['known_error'],roles=dict(e='primal known error',q='dual A6e')))
    scale=float(np.linalg.norm(q_raw))
    if not np.isfinite(scale) or scale==0:raise ValueError('known error normalization invalid')
    e,q=e_raw/scale,q_raw/scale
    save('known_normalized',dict(e=e,q=q,scale=scale,roles=dict(e='primal',q='dual')))
    c=actions.PH(e); pc=actions.P(c)
    left=actions.PH(actions.M0(pc)); right=actions.metrics[4].mass(c)
    mass_error=float(np.linalg.norm(left-right)/max(np.linalg.norm(right),np.finfo(float).tiny))
    save('mass_galerkin',dict(c=c,left=left,right=right,relative=mass_error,limit=1e-10))
    if mass_error>1e-10:raise ValueError('native mass differs from PH M0 P')
    sample()
    ledger.marker('C2_projection_started',{})
    projection=actions.project(e,checkpoint=sample,retain_approximation=True)
    save('known_projection',dict(**projection,projection_seconds=actions.projection_seconds))
    energies={}
    for name,value in [('e',e),('parallel',projection['parallel']),('perpendicular',projection['perpendicular'])]:
        if value is not None:
            energies[name]=dict(L2_squared=metric_square(actions.M0,value),
                scaled_curl_squared=metric_square(actions.metrics[6].curl,value))
    save('known_primal_metrics',dict(energies=energies,k0=cfg.k0))
    summary['projection']=projection['status']
    summary['projection_seconds']=actions.projection_seconds
    if projection['status']=='PROJECTION_CLOSED' and np.linalg.norm(projection['perpendicular'])>0:
        for name,smoother in actions.smoothers.items():
            sample()
            result=evaluate_profiles(actions.A,actions.M0,projection['perpendicular'],{name:smoother},checkpoint=sample)
            summary['independent_smoother_calls']+=1
            save('complement_'+name,result)
            repeated=homogeneity_check(result['normalized_q'],{name:result['profiles'][name]['correction']},
                {name:smoother},scale=1+1j,checkpoint=sample)
            summary['independent_smoother_calls']+=1
            save('complement_homogeneity_'+name,repeated)
    else:
        save('complement_skipped',dict(status='skipped',dependency=projection['status']))
    ledger.marker('C2_completed',dict(projection=projection['status']))
    sample()
    control=np.zeros(actions.P.source.getLocalSize(),dtype=np.complex128)
    control[actions.P.indices]=c
    identity=dict(source_sha=source_sha,physical_sha256=inventory['samples'][0]['physical_sha256'],
        mode_sha256=bundle['fine']['mode_sha256'],quadrature=bundle['actions']['volume_quadrature_metadata'],
        constraints=load_packet(directory/'native_constraint_map_p4.json')['arrays'],
        reconstruction='RECONSTRUCTED_FAILURE_CASE; old g was not saved')
    policy=DiagnosticRefinementV4(save,bundle['actions']['physical'][4]['dtn_action'],control,identity)
    ledger.marker('C3_reference_started',{})
    try:
        attach_physical_reference(bundle,cfg,resource_sample=sample,marker=ledger.marker,
                                  diagnostic_refinement_v4=policy)
    except ReferenceResourceBlocked as exc:
        summary.update(status='DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS',C3='RESOURCE_PREFLIGHT_UNQUALIFIED')
        save('C3_skipped',dict(reason=str(exc),status=summary['C3']))
        return
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
    summary['attempted_pc_calls']=0
    def item(name,operation,*,pc=False):
        policy.label=name
        if pc:
            summary['attempted_pc_calls']+=1
            if summary['attempted_pc_calls']>8:raise RuntimeError('PC attempt budget exceeded')
        result=independent_item(name,operation,save,summary,ledger.marker)
        if pc and result is not None:summary['complete_pc_calls']+=1
        return result
    try:
        for name in ('LIGHT','JOINT'):
            item('JOINT448_'+name,lambda name=name:evaluate_residual_profiles(
                actions.A,actions.M0,old['r'],{name:actions.profiles[name]},checkpoint=sample),pc=True)
        corrections={}
        for name,profile in actions.profiles.items():
            def known(profile=profile):
                sample()
                z=profile(q)
                return dict(correction=z,**correction_diagnostics(actions.A,actions.M0,e,q,z))
            result=item('known_'+name,known,pc=True)
            if result is not None:corrections[name]=result['correction']
        for name,profile in actions.profiles.items():
            if name in corrections:
                item('known_homogeneity_'+name,lambda name=name,profile=profile:homogeneity_check(
                    q,{name:corrections[name]},{name:profile},scale=1+1j,checkpoint=sample),pc=True)
            else:
                summary['items']['known_homogeneity_'+name]='skipped'
                save('known_homogeneity_'+name,dict(status='skipped',dependency='known_'+name))
        direct=item('known_coarse',lambda:coarse_diagnostics(actions.A,actions.M0,actions.P,actions.PH,
                    actions.solve,e,projection,identity_check=False))
        identity_vector=projection['parallel'] if projection['status']=='PROJECTION_CLOSED' else pc
        if identity_vector is not None and np.linalg.norm(identity_vector)>0:
            save('range_identity_input',dict(vector=identity_vector,role='primal range(P) control',
                origin='closed projection' if projection['status']=='PROJECTION_CLOSED' else 'existing P(PH(e)); not best projection'))
            item('range_identity',lambda:coarse_identity_diagnostics(actions.A,actions.M0,actions.P,
                actions.PH,actions.solve,identity_vector))
        else:
            save('range_identity',dict(status='skipped',dependency='nonzero range(P) control unavailable'))
    finally:
        summary.update(logical_p4_rhs=policy.logical_rhs,external_MatSolve_calls=policy.external_solves,
                       reference_records=policy.records,timings=actions.timings)
    # V3 §8 has qualitative triggers, so retain the measured inputs without
    # inventing a numerical cutoff or treating cancellation as proof of dispersion.
    propagation=dict(eta_space=projection.get('eta_space'),projection_status=projection['status'],
        eta_G=None if direct is None else direct['unit_field_ratio'],
        cancellation_ratios={label:packets[label+'_identity']['component']['cancellation_ratio']
            for label in ('A2R160','LIGHT448','JOINT448')},
        trigger='PROPAGATION_SENSITIVITY_UNRESOLVED; cancellation and representation/response data require joint interpretation',
        implementation='src/modes/quadratic_beta_eigenproblem.py',
        implementation_limit='Existing cross-section beta QEP does not supply the required same-cell 3D Bloch transverse-branch control',
        status='UNRESOLVED_NO_QUALIFIED_CONTROL',small_eigenproblems_started=0)
    save('C4_decision',propagation)
    summary.update(status='DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS',
        fine_reference='UNAVAILABLE',C4=propagation)
