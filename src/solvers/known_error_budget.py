"""Same-discrete error budget on existing FE/port integrals, not a solver."""
import hashlib
import json
from pathlib import Path
import numpy as np

from src.runners.task042_shared import write_json
from . import known_error_scope as scope
from .scattering_anchor import Journal,save_arrays,array_hash
from .scattering_anchor_checks import checked_arrays
from .actual_error_diagnostics import error_identity,cell_energy_summary
from .physical_error_diagnostics import component_diagnostics


def partition_budget(per, tags, centers, volumes, bounds):
    """Whole owned-cell bins on four preregistered geometric z intervals."""
    per=np.asarray(per)
    if per.ndim!=3 or per.shape[1:]!=(len(tags),3) or np.any(per<0) or not np.isfinite(per).all():
        raise ValueError('nonnegative complete error-cell inventory')
    edges=np.linspace(float(bounds[0]),float(bounds[1]),5)
    labels=np.clip(np.searchsorted(edges,np.asarray(centers)[:,2],side='right')-1,0,3)
    total=per.sum(axis=1);volume=float(np.sum(volumes))
    def groups(labels,keys):
        out=[]
        for key in keys:
            mask=labels==key;squared=per[:,mask].sum(axis=1)
            out.append(dict(label=int(key),cells=int(np.sum(mask)),volume=float(np.sum(volumes[mask])),
                volume_fraction=float(np.sum(volumes[mask])/volume),squared=squared,
                fractions=np.divide(squared,total,out=np.zeros_like(total),where=total!=0)))
        reconstructed=sum(np.asarray(x['squared']) for x in out)
        defect=float(np.max(np.abs(reconstructed-total)/np.maximum(total,np.finfo(float).tiny)))
        if defect>1e-10 or sum(x['cells'] for x in out)!=len(tags):
            raise ValueError('owned-cell partition closure')
        return dict(rows=out,closure=defect)
    # Reuse the existing owned-cell energy convention as an additional check.
    inherited=cell_energy_summary(dict(mass=per[0,:,0],curl=per[0,:,2],
        material_tags=tags,cell_centers=centers),float(total[0,0]),float(total[0,2]))
    return dict(materials=groups(np.asarray(tags),np.unique(tags)),height=groups(labels,range(4)),
        total_squared=total,total_volume=volume,z_edges=edges,
        region_rule='each whole cell once by saved centroid; fixed equal-height/equal-geometric-volume bins; actual cell volumes reported, no plane clipping',
        inherited_owned_cell_closure=inherited['global_relative_defects'])


def term_budget(error,curl,mass,boundary,expected):
    with np.errstate(over='ignore',divide='ignore'):
        facts=component_diagnostics(dict(curl=lambda x:curl,mass=lambda x:mass,DtN=lambda x:boundary),error)
    scale=sum(facts['norms'].values());defect=float(np.linalg.norm(facts['sum_vector']-expected)/max(scale,np.finfo(float).tiny))
    facts['closure_operation_scaled']=defect
    if facts['sum_norm']==0:facts['cancellation_ratio']=None
    elif not np.isfinite(facts['cancellation_ratio']):raise ValueError('nonfinite component norm')
    if defect>1e-10:raise ValueError('uncondensed term sum identity')
    return facts


def load_parents():
    p=scope.plan_record();ref=scope.checked_json(p['reference']);cand=scope.checked_json(p['candidate'])
    if (ref['physical']!=cand['physical'] or ref['mode_sha256']!=cand['mode_sha256']
        or ref['boundary_arrays']!=cand['boundary_arrays']):raise ValueError('same physics/mode/reference-plane identity')
    for key in ('degree','cells','independent','rows','complete_modes','mesh_override'):
        if ref['spec'][key]!=cand['spec'][key]:raise ValueError('same discrete '+key)
    if (ref['spec']['degree'],ref['spec']['cells'],ref['spec']['independent'],ref['spec']['complete_modes'])!=(5,25576,1943745,828):
        raise ValueError('frozen p5/full-FE/828 inventory')
    return ref,cand


def known_error(folder,journal,state):
    from . import independent_tetra_reference as core
    from .independent_tetra_study import load_boundary
    from .tetra_coefficient_action import CoefficientFullAction
    from .tetra_polynomial_difference import numerator
    ref,cand=load_parents();plan=scope.plan_record()
    # Main artifacts are loaded once; no factor, local packet matrix or old S.
    with journal.measured('checked_saved_reference_candidate_and_original_vectors'):
        vr=checked_arrays(ref['arrays']);vj=checked_arrays(cand['arrays'])
        ar=checked_arrays(ref['audit']['arrays']);aj=checked_arrays(cand['audit']['arrays'])
    for key in ('rhs','masters','slaves','P_data','P_indices','P_indptr','geometry_x','geometry_dofmap','cell_centers','cell_tags','regular_tags','original_parent_cell','kappa'):
        if not np.array_equal(vr[key],vj[key]):raise ValueError('saved exact numbering/geometry/RHS '+key)
    if not np.array_equal(ar['rhs'],aj['rhs']):raise ValueError('same q63 continuous load')
    if not np.array_equal(ar['x'],vr['x']) or not np.array_equal(aj['x'],vj['x']):raise ValueError('original residual x binding')
    s=core.make_setup(scope.case_spec('KNOWN_ERROR'),ref['physical'],journal)
    for key in s['geometry']:
        if not np.array_equal(s['geometry'][key],vr[key]):raise ValueError('live native geometry '+key)
    for name,value in [('P_data',s['P'].data),('P_indices',s['P'].indices),('P_indptr',s['P'].indptr),('masters',s['masters'])]:
        if not np.array_equal(value,vr[name]):raise ValueError('live MPC numbering '+name)
    if not np.array_equal(s['P']@vr['u_independent'],vr['u_native']) or not np.array_equal(s['P']@vj['u_independent'],vj['u_native']):
        raise ValueError('saved native field and independent coefficient identity')
    packet=scope.checked_json(plan['packet_manifest']);ident=packet['identity']['full_identity']
    s['mesh'].topology.create_entity_permutations()
    if (array_hash(s['V'].element.basix_element.coefficient_matrix)!=ident['arrays']['basis_coefficients']
        or array_hash(s['mesh'].topology.get_cell_permutation_info())!=ident['arrays']['cell_permutations']):
        raise ValueError('live Basix basis/orientation identity')
    # Complete 32-step coefficients are optional. This is read-only trajectory
    # consumption, never a reconstruction from a trace plus another particular.
    candidates=[(128,vj['u_independent'],aj['residual'])];optional=dict(status='NOT_AVAILABLE')
    if plan.get('snapshot32') is not None:
        try:
            a32=checked_arrays(plan['snapshot32'])
            if a32['full'].shape!=vj['x'].shape or not np.array_equal(a32['rhs'],aj['rhs']):raise ValueError('32-step saved full-field/RHS identity')
            candidates.append((32,a32['full'][:len(vj['u_independent'])],a32['residual']))
            optional=dict(status='CONSUMED_COMPLETE_SAVED_COEFFICIENTS',arrays=plan['snapshot32'])
        except (FileNotFoundError,ValueError,KeyError) as error:
            optional=dict(status='ASSET_BLOCKED_OPTIONAL',reason=str(error))
    errors=np.column_stack([vr['u_independent']-x[1] for x in candidates]);n=len(errors)
    identity_arrays=save_arrays(folder/'coefficient_error.npz',error=errors,reference=vr['u_independent'],
        candidate=vj['u_independent'],kappa=vr['kappa'],original_rhs=aj['rhs'])
    write_json(folder/'identity_complete.json',dict(status='COMPLETED',reference=plan['reference'],candidate=plan['candidate'],
        full_FE=n,native=s['P'].shape[0],modes=828,geometry_MPC_basis_RHS_all_checked=True,optional32=optional,
        independent_subtraction_before_native_P=True,zero_RHS_recovery_used=False,arrays=identity_arrays))
    # Save the principal field evidence first; decomposition is an independent
    # auxiliary result and cannot erase already committed numerator blocks.
    zero=core.restore_field(s,np.zeros(n,complex));deltas=[core.restore_field(s,errors[:,j]) for j in range(len(candidates))]
    q=2*s['V'].element.basix_element.embedded_superdegree+3
    if q!=13:raise ValueError('actual p5 polynomial quadrature certificate')
    per,parents,_=numerator(zero,deltas[0],s['cfg'],s['kappa'],journal,folder/'numerator',q,
        parent_hashes=[ref['arrays']['sha256'],cand['arrays']['sha256'],optional.get('arrays',{}).get('sha256')],
        spot=False,coefficient_first=True,additional_pairs=[(zero,d) for d in deltas[1:]])
    per=per.reshape(len(per),len(candidates),3).transpose(1,0,2)
    norms=[]
    for row in ref['output']['integrals']:
        if row['q'] not in (23,31):raise ValueError('fixed saved norm inventory')
        a=checked_arrays(row['arrays'])
        if 'per_cell_total_squared' not in a:raise ValueError('missing saved norm; do not integrate again')
        norms.append(dict(q=row['q'],total=a['per_cell_total_squared'].sum(axis=0),
            scattered=a['per_cell_analytic_squared'][:,:,0].sum(axis=0),arrays=row['arrays']))
    if [r['q'] for r in norms]!=[23,31]:raise ValueError('saved q23/q31 inventory')
    volumes=np.array([abs(np.linalg.det((s['mesh'].geometry.x[rows][1:]-s['mesh'].geometry.x[rows][0]).T))/6
                      for rows in s['mesh'].geometry.dofmap])
    z=s['mesh'].geometry.x[:,2];partition=partition_budget(per,vr['cell_tags'],vr['cell_centers'],volumes,(z.min(),z.max()))
    rows=[]
    for j,(iteration,_,_) in enumerate(candidates):
        sums=per[j].sum(axis=0);curl_norm=float(np.sqrt(sums[2]));e_norm=float(np.sqrt(sums[0]))
        fields={}
        for kind in ('total','scattered'):
            fields[kind]={key:dict(difference_squared=float(sums[k]),reference_squared=float(norms[-1][kind][k]),
                relative=float(np.sqrt(sums[k])/max(np.sqrt(norms[-1][kind][k]),1e-12))) for k,key in enumerate(('E','H','curl'))}
        rows.append(dict(iteration=iteration,fields=fields,chi=curl_norm/(s['cfg'].k0*e_norm) if e_norm else None,
            curl_norm=curl_norm,E_norm=e_norm,absolute_only_zero_denominator=e_norm==0))
    field_arrays=save_arrays(folder/'field_error_cells.npz',per_cell_squared=per,cell_volumes=volumes,
        material_tags=vr['cell_tags'],cell_centers=vr['cell_centers'],iterations=np.array([r[0] for r in candidates]))
    field_result=dict(status='COMPLETED',rows=rows,partition=partition,arrays=field_arrays,
        numerator_q=q,numerator_traversals=1,norms=norms,failed_candidate_denominators_recomputed=False,
        physical_error_not_coefficient_norm=True,reference_is_not_continuum_truth=True)
    write_json(folder/'field_error_complete.json',field_result)
    scope.window.require_live()
    decomposition=None
    try:
        b=load_boundary(s,ref['boundary_arrays'],ref['mode_sha256'],'q63')
        action=CoefficientFullAction(s,b,15);parts={};count=len(candidates)
        counter=scope.window.TMP/'action_counts.json'
        previous=json.loads(counter.read_text()) if counter.exists() else dict(started=0,completed=0)
        if previous['started']+count>8:raise RuntimeError('V79 original action column quota')
        previous['started']+=count;write_json(counter,previous)
        with journal.measured('q15_complete_error_columns_and_uncondensed_curl_mass_split'):
            body=action.body(errors,diagnostic=lambda x:parts.update(x))
        previous['completed']+=count;write_json(counter,previous);journal.calls['A']+=count
        boundary=action.C@((action.D@errors)/action.H[:,None]);closed_action=body+boundary
        qr=ar['residual'][:n]-action.C@(ar['residual'][n:]/action.H)
        closed_rhs=ar['rhs'][:n]-action.C@(ar['rhs'][n:]/action.H)
        identities=[];residuals=[]
        for j,(_,coefficients,residual) in enumerate(candidates):
            qi=residual[:n]-action.C@(residual[n:]/action.H);residuals.append(qi)
            result=error_identity(lambda e,j=j:closed_action[:,j],vr['u_independent'],coefficients,
                qi,qr,closed_rhs-qr,closed_rhs-qi)
            check={k:v for k,v in result.items() if k not in ('e','q','residual_difference','closure_vector')}
            check['iteration']=candidates[j][0];identities.append(check)
            if check['closure_relative_to_operations']>1e-10:raise ValueError('closed original error identity')
        terms=term_budget(errors[:,0],parts['curl'][:,0],parts['mass'][:,0],boundary[:,0],closed_action[:,0])
        receipt=save_arrays(folder/'closed_error_terms.npz',errors=errors,closed_action=closed_action,
            q_reference=qr,q_candidates=np.column_stack(residuals),curl=parts['curl'][:,0],mass=parts['mass'][:,0],
            DtN=boundary[:,0],sum_vector=terms['sum_vector'],gram=terms['gram'])
        decomposition=dict(status='COMPLETED',identities=identities,arrays=receipt,
            terms={k:v for k,v in terms.items() if k not in ('vectors','sum_vector','gram')},
            gram_real=terms['gram'].real,gram_imag=terms['gram'].imag,
            original_body_columns=count,term_columns_share_same_traversal=True,diagnostic_only=True,
            dual_norms_are_basis_dependent=True,reference_residual_not_zeroed=True)
        write_json(folder/'decomposition_complete.json',decomposition)
    except (ValueError,RuntimeError,KeyError) as error:
        decomposition=dict(status='PARTIAL_OR_ISOLATED',reason=str(error),field_evidence_preserved=True)
        write_json(folder/'decomposition_failure.json',decomposition)
    result=dict(status='COMPLETED',field_error=field_result,decomposition=decomposition,
        optional32=optional,reference=plan['reference'],candidate=plan['candidate'],
        arrays=identity_arrays,source=state,timings=journal.timings,
        new_numeric_factors=0,new_complete_solves=0,global_fine_K_reads=0,global_fine_S_reads=0,
        reference_consumed_for_diagnosis=True,future_selection_is_not_blind=True,official_RTA=False)
    write_json(folder/'known_error_budget.json',result)
    return result


def decision_export(folder,journal,state):
    result=scope.stage('KNOWN_ERROR');field=result['field_error'];mechanism=result['decomposition']
    # One measured error and at most one earlier trajectory point do not
    # identify a unique propagation or gradient-space mechanism.
    card=dict(status='INSUFFICIENT_CAUSAL_EVIDENCE',new_method_implementation_authorized=False,
        hypothesis='A representative family of independently chosen physical errors must reproduce the measured curl scale and cancellation before a propagation/scale-specific candidate is selected.',
        evidence=dict(field_rows=field['rows'],mechanism_status=mechanism['status'],terms=mechanism.get('terms')),
        missing=['independent error directions and propagation symbols','measured complete cold prefix','same-correctness candidate cost'],
        future_falsification='Reject a proposed mechanism if its claimed range misses these measured scales or does not reduce new original-RHS residuals and true errors at a cost competitive with the inexpensive control.',
        previous_PC_trials='CLOSED',reference_has_been_consumed=True,automatic_next_batch=False)
    contract=dict(schema='task042.same-discrete-error-consumer.v79',physical_sha256=state['physical_sha256'],
        model='0.7nm scaled NOTCH 25576tet/p5/828',reference=result['reference'],candidate=result['candidate'],
        error_arrays=result['arrays'],field_arrays=field['arrays'],decomposition_arrays=mechanism.get('arrays'),
        closed_operator='K + C H^-1 D, q15 PUBLIC_BASIX plus exact q63/828 boundary',
        original_action_entry='src.solvers.tetra_coefficient_action.CoefficientFullAction',
        identity_requirements=['same mesh/basis/numbering/P/MPC/carrier/material/modes/RHS/scales'],
        no_cross_grid_substitution=True,reference_formal_pass=True,reference_direct_1e10_pass=False,
        candidate_equation_pass=False,continuum_accuracy=False,target_2TB48h=False,NN20=False,
        parent_packet_only_cold_seconds=None,known_history_lower_seconds=scope.plan_record()['history_known_lower_seconds'])
    write_json(folder/'next_method_admission_card.json',card)
    write_json(folder/'reference_consumer_contract.json',contract)
    out=dict(status='COMPLETED',decision=card,contract=contract,source=state,
        new_complete_solves=0,new_numeric_factors=0,new_body_actions=0,timings=journal.timings)
    write_json(folder/'decision_export.json',out);return out


def execute(role,folder,state):
    if state['memory_budget']!=scope.memory_budget(role):raise ValueError('V79 live resolved memory')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if role=='KNOWN_ERROR':return known_error(folder,journal,state)
    if role=='EXPORT':return decision_export(folder,journal,state)
    raise ValueError('V79 explicit saved-data role')
