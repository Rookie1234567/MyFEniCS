"""Thin V69 adapters around the existing tetra solve and output chain."""
import gc
import json
from pathlib import Path

import numpy as np
from scipy import sparse

from src.runners.task042_shared import write_json
from . import exact_tetra_scope as scope
from . import independent_tetra_reference as core
from .scattering_anchor import Journal,relative,save_arrays
from .p6_completion_study import setup_identity
from .tetra_body_checkpoint import load_checkpoint,file_digest,body_fingerprint
from .tetra_coefficient_action import CoefficientFullAction
from .exact_tetra_condensation import tetra_interiors,build_checkpoint,ExactRecovery,port_schur_preallocation


def prepared_provider(s,folder,journal):
    """Qualified V67 body; a new mode inventory gets new boundary objects."""
    from .durable_l5_study import qualification
    from .durable_l5_scope import prepared_parent
    from .independent_tetra_study import load_boundary
    parent=prepared_parent('SOLVE_COMPLETE');qualified,qr=qualification()
    identity,_=setup_identity(s)
    with journal.measured('read_only_qualified_v67_p5_K_checked_reopen'):
        K,m,owners=load_checkpoint(parent['checkpoint'],identity,allow_mode_change=s['spec']['complete_modes']==1188)
    if body_fingerprint(identity)!=body_fingerprint(m['identity']):raise ValueError('V69 body fingerprint')
    if s['spec']['complete_modes']==828:
        with journal.measured('same_p5_q47_q63_readonly_consume'):
            b=load_boundary(s,parent['boundary_arrays'],parent['mode_sha256'],'q47')
            oracle=load_boundary(s,parent['boundary_arrays'],parent['mode_sha256'],'q63')
    else:
        b=core.boundary(s,47,journal,folder);oracle=core.boundary(s,63,journal,folder)
    result=dict(K=K,form=m['form'],boundary=b,oracle=oracle,owners=owners,
                checkpoint=parent['checkpoint'],qualification=qr)
    if s['spec']['complete_modes']==828:
        receipt=scope.plan_record()['original_pairs'];p=Path(receipt['path'])
        if file_digest(p)!=receipt['sha256']:raise ValueError('parent action pair hash')
        old=json.loads(p.read_text())
        if old['arrays']!=qualified['arrays'] or old['errors']!=qualified['errors']:raise ValueError('parent qualified pair binding')
        result['reuse_original_pairs']=old
    return result


def full_objects(s,prepared):
    C,D,H=core.boundary_matrices(s,prepared['boundary'])
    A=sparse.bmat([[prepared['K'],C],[-D,sparse.diags(H)]],format='csr')
    return A,core.rhs_vector(s,prepared['boundary'])


def reduction_identity(s,prepared):
    identity,_=setup_identity(s)
    return dict(body=body_fingerprint(identity),full_identity=identity,
                parent_checkpoint=prepared['checkpoint'],mode_sha256=prepared['boundary']['digest'],
                boundary_arrays=prepared['boundary']['arrays'],oracle_arrays=prepared['oracle']['arrays'],
                partition='actual_Basix_entity3_native_to_compact_MPC_unique_owner')


def preflight(folder,journal):
    s=core.make_setup(scope.case_spec('PREFLIGHT'),scope.physical_for('PREFLIGHT'),journal)
    cells=tetra_interiors(s);prepared=prepared_provider(s,folder,journal);A,rhs=full_objects(s,prepared)
    if A.shape!=(1944573,1944573) or len(np.concatenate(cells))!=767280:raise ValueError('actual full/retained dimensions')
    # Exactly two real cells, selected geometrically before inspecting errors.
    centers=s['geometry']['cell_centers']
    ids=sorted(range(len(cells)),key=lambda c:tuple(centers[c]))
    selected=[ids[0],ids[-1]];errors=[];records=[]
    with journal.measured('two_actual_tetra_local_elimination_pairs'):
        AT=A.T.tocsr()
        for c in selected:
            i=np.sort(cells[c]);others=np.setdiff1d(np.unique(np.r_[A[i].indices,AT[i].indices]),i)
            rows=np.r_[i,others];small=A[rows][:,rows].tocsr();br=rhs[rows]
            rec=build_checkpoint(small,br,(np.arange(30,dtype=np.int64),),folder/f'cell{c}',
                identity=dict(cell=c,original_rows=rows.tolist()),source=journal.source_state)
            service=ExactRecovery(rec);rng=np.random.default_rng(6900+c)
            r=rng.normal(size=len(rows))+1j*rng.normal(size=len(rows))
            t=rng.normal(size=len(others))+1j*rng.normal(size=len(others))
            x=service.recover(t,r);actual=r-small@x;predicted=service.lift_residual(service.condense_rhs(r)-service.apply_trace(t))
            err=relative(actual-predicted,small@x);errors.append(err)
            records.append(dict(cell=c,original_interior=i.tolist(),retained_count=len(others),operation_error=err,
                recovery_calls=service.calls,checkpoint=rec))
            del service,small
        del AT
    arrays=save_arrays(folder/'interior_partition.npz',interiors=np.vstack(cells),masters=s['masters'])
    result=dict(status='COMPLETED',pass_gate=max(errors)<=1e-10,actual_full_rows=A.shape[0],
        actual_retained_rows=A.shape[0]-767280,actual_internal=767280,partition=arrays,
        actual_cell_pairs=records,body_checkpoint=prepared['checkpoint'],new_body_builds=0,new_numeric_factors=0,
        new_complete_solves=0,actual_local_LU_attempts=2,source=journal.source_state,timings=journal.timings)
    write_json(folder/'preflight_scientific_result.json',result)
    del A,rhs,prepared,s;gc.collect()
    # The finite diagnostic is independent of the solver admission.
    try:
        from src.postprocessing.saved_interface_diagnosis import diagnose
        result['saved_field_diagnosis']=diagnose(folder/'diagnosis',journal,maximum_seconds=2700)
    except Exception as exc:
        result['saved_field_diagnosis']=dict(status='PARTIAL',reason=repr(exc),solver_gate_unaffected=True)
        write_json(folder/'diagnosis_failure.json',result['saved_field_diagnosis'])
    return result


def make_reduction(s,A,rhs,folder,journal,state,b,oracle,*,path=None):
    cells=tetra_interiors(s);identity,_=setup_identity(s)
    parent=scope.plan_record()['prepared_parent']
    rid=dict(body=body_fingerprint(identity),full_identity=identity,parent_checkpoint=parent,
             mode_sha256=b['digest'],boundary_arrays=b['arrays'],oracle_arrays=oracle['arrays'],
             partition='actual_Basix_entity3_native_to_compact_MPC_unique_owner')
    path=folder/'exact_condensed' if path is None else Path(path)
    C,D,H=core.boundary_matrices(s,b)
    with journal.measured('exact_port_Schur_support_capacity_plan'):
        extra,preallocation=port_schur_preallocation(s,C,D,cells)
    write_json(folder/'port_schur_preallocation.json',preallocation)
    # Copies of original/transpose/retained operators and reserved AIJ payload
    # are all bounded before allocation. Numeric still has its own symbolic Gate.
    # Current RSS already includes the read-only K, augmented CSR and setup.
    # Six further full-CSR payloads conservatively cover PETSc input, the
    # retained submatrix/new AIJ, transpose construction and transient copies.
    added=6*(A.data.nbytes+A.indices.nbytes+A.indptr.nbytes)+preallocation['extra_AIJ_payload_upper_bytes']
    journal.allocation('exact_condensed_forming',dict(matrix_payload_bytes=added,workspace_bytes=2*2**30))
    journal.event('exact_condensed_forming_capacity',planned_added_matrix_upper_bytes=added,
                  workspace_bytes=2*2**30,preallocation=preallocation,admitted=True)
    with journal.measured('exact_cell_elimination_and_atomic_recovery_checkpoint'):
        receipt=build_checkpoint(A,rhs,cells,path,identity=rid,source=state,journal=journal,preallocation_extra=extra)
    del extra
    if A.shape[0]-767280>scope.plan_record()['reduced_row_cap']:raise ValueError('actual retained row capacity')
    service=ExactRecovery(receipt,identity=rid);service.receipt=receipt
    # One complete recovered vector, independent q15 body/q63 boundary.
    rng=np.random.default_rng(6907);t=rng.normal(size=len(service.retained))+1j*rng.normal(size=len(service.retained))
    t[-len(H):]/=np.maximum(np.abs(H),1.)
    witness_rhs=rhs.copy();witness_rhs[:s['P'].shape[1]]+=np.sin(np.arange(s['P'].shape[1])*.173)*1e-3
    x=service.recover(t,witness_rhs);red=service.condense_rhs(witness_rhs)-service.apply_trace(t)
    with journal.measured('full_recovered_public_Basix_original_witness'):
        original=CoefficientFullAction(s,oracle,15)(x);journal.calls['A']+=1
    residual=witness_rhs-original;prediction=service.lift_residual(red)
    error=relative(residual-prediction,original)
    production_error=relative(A@x-original,original)
    n=s['P'].shape[1]
    body_error=relative((residual-prediction)[:n],original[:n])
    port_scale=np.abs(D@x[:n])+np.abs(H*x[n:])+np.abs(witness_rhs[n:])
    port_error=relative((residual-prediction)[n:],port_scale)
    body_production_error=relative((A@x-original)[:n],original[:n])
    raw=save_arrays(folder/'recovered_original_witness.npz',retained=t,full=x,rhs=witness_rhs,
                    original_action=original,original_residual=residual,condensed_residual_lift=prediction)
    maximum=max(error,production_error,body_error,port_error,body_production_error)
    verified=dict(status='ORIGINAL_REDUCTION_VERIFIED' if maximum<=1e-10 else 'FAILED',
        pass_gate=maximum<=1e-10,checkpoint=receipt,operation_error=error,
        production_original_error=production_error,arrays=raw,full_space_rows=A.shape[0],retained_rows=len(t),
        body_operation_error=body_error,port_operation_error=port_error,body_production_original_error=body_production_error,
        internal_recovery_identity=service.last_identity,
        local_LU_count=service.manifest['local_LU_count'],service_calls=service.calls,source=state)
    write_json(folder/'reduction_qualification.json',verified)
    if not verified['pass_gate']:raise ValueError('complete independent recovered-vector reduction gate')
    return service,verified


def prepare(folder,journal,state):
    scope.require_stage('PREPARE_C5')
    s=core.make_setup(scope.case_spec('PREPARE_C5'),scope.physical_for('PREPARE_C5'),journal)
    prepared=prepared_provider(s,folder,journal);A,rhs=full_objects(s,prepared)
    journal.owners('source_CSR_augmented_before_condensation',dict(K=prepared['K'],A=A))
    service,qualified=make_reduction(s,A,rhs,folder,journal,state,prepared['boundary'],prepared['oracle'])
    return dict(status='COMPLETED',pass_gate=True,checkpoint=service.receipt,qualification=qualified,
        body_checkpoint=prepared['checkpoint'],source=state,timings=journal.timings,
        actual_full_rows=A.shape[0],actual_retained_rows=len(service.retained),nnz=service.matrix.nnz,
        bytes=service.manifest['bytes'],local_LU_count=service.manifest['local_LU_count'],
        new_body_builds=0,new_numeric_factors=0,new_complete_solves=0)


def system_adapter(s,A,rhs,folder,journal,state,b,oracle):
    if state['stage']=='V69-C5':
        r=scope.stage('PREPARE_C5');service=ExactRecovery(r['checkpoint']);service.receipt=r['checkpoint']
        expected,_=setup_identity(s)
        if service.manifest['identity']['full_identity']!=expected or service.manifest['identity']['boundary_arrays']!=b['arrays']:
            raise ValueError('C5 same full mathematical input')
        discrepancy=relative(service.condense_rhs(rhs)-service.arrays['rhs'],service.arrays['rhs'])
        if discrepancy>1e-12:raise ValueError('C5 checkpoint arbitrary RHS identity')
        journal.event('sealed_condensed_reloaded',checkpoint=r['checkpoint'],rhs_operation=discrepancy)
        return service
    service,qualified=make_reduction(s,A,rhs,folder,journal,state,b,oracle)
    return service


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V69 resolved/live memory mismatch')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='PREPARE_C5':return prepare(folder,journal,state)
    if role in scope.SOLVES:
        from .independent_tetra_study import solve
        method=scope.method_for(role)
        return solve(role,folder,journal,state,scope_module=scope,prepared_provider=prepared_provider,
                     action_factory=lambda s,b:CoefficientFullAction(s,b,15),
                     system_adapter=system_adapter if method['static_condensation'] else None)
    if role=='VERIFY_COST':
        from benchmarks.collect_exact_tetra import verify
        return verify(folder,journal)
    raise ValueError('V69 one-run stage inventory')
