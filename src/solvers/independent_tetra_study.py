"""Thin fixed queue for complete uncondensed tetra Maxwell candidates."""
import gc
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json
from . import independent_tetra_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from . import independent_tetra_reference as core


def preflight(folder,journal):
    s=core.make_setup(scope.case_spec('T4'),scope.physical_for('T4'),journal)
    V=s['V'];ev=core.TetraEvaluator(V,0,s['kappa'],quadrature_tables=False)
    determinants=np.array([g[2] for g in ev.geometry]);vol=np.abs(determinants)/6
    ids=s['data'].cell_tags.values
    material={str(int(t)):float(vol[ids==t].sum()) for t in np.unique(ids)}
    full=float(np.prod([a[-1]-a[0] for a in [s['physical']['geometry']['axes_nm'][k] for k in ('x','y','z')]]))
    if abs(vol.sum()-full)>1e-12*full:raise ValueError('periodic tetra physical volume')
    cfg=s['cfg'];nc=V.dofmap.index_map.size_local
    # A polynomial periodic envelope has a known Piola/curl independent of
    # native cell direction and is interpolated by the public FE interface.
    from dolfinx import fem
    f=fem.Function(V);f.interpolate(lambda x:np.vstack((1+x[2],2+0*x[0],3+0*x[1])).astype(complex))
    witness=[]
    for c in (0,next((i for i,p in enumerate(ev.permutations) if p!=ev.permutations[0]),len(ev.geometry)-1)):
        J,o,_=ev.geometry[c];points=np.array([[.1,.2,.15],[.2,.1,.25]])@J.T+o
        actual=ev.at(f,c,points,cfg.k0)
        ue=np.column_stack((1+points[:,2],np.full(len(points),2),np.full(len(points),3)))
        curl=np.tile([0.,1.,0.],(len(points),1));known=ev.physical(points,ue,curl,cfg.k0)
        errors={k:relative(actual[k]-known[k],known[k]) for k in actual};witness.append(dict(cell=c,permutation=int(ev.permutations[c]),errors=errors))
        if max(errors.values())>1e-10:raise ValueError('actual tetra affine orientation field/curl')
    P=s['P'];rng=np.random.default_rng(6201);x=rng.normal(size=P.shape[1])+1j*rng.normal(size=P.shape[1]);y=rng.normal(size=P.shape[0])+1j*rng.normal(size=P.shape[0])
    dual=abs(np.vdot(P@x,y)-np.vdot(x,P.conj().T@y))/max(np.linalg.norm(P@x)*np.linalg.norm(y),1e-30)
    from .independent_tetra_fields import selected_points,evaluate_selected,tangential_check
    _,parents,evals=evaluate_selected(f,cfg,s['kappa'],selected_points(s['physical']))
    cap=core.assembly_capacity(s,journal)
    tangent=tangential_check(s,f,folder)
    arrays=save_arrays(folder/'preflight.npz',determinants=determinants,permutations=ev.permutations,selected_parents=parents,
        geometry_x=s['geometry']['geometry_x'],geometry_dofmap=s['geometry']['geometry_dofmap'],cell_tags=ids,masters=s['masters'],slaves=s['floquet'].mpc.slaves)
    return dict(status='COMPLETED',pass_gate=dual<=1e-12 and max(evals)<=1e-11 and cap['admitted'] and tangent['pass_gate'],
        family='FULL_UNCONDENSED_TETRA_N1CURL_PHASE_UFL',facts=dict(native=nc,independent=P.shape[1],cells=len(vol),local_dim=V.element.space_dimension),
        geometry_volume=full,material_volumes=material,Piola_direction=witness,complex_dual=dual,tangential=tangent,capacity=cap,arrays=arrays,
        new_numeric_factors=0,new_complete_solves=0,timings=journal.timings,source=journal.source_state)


def petsc_matrix(A):
    from petsc4py import PETSc
    A=A.tocsr();return PETSc.Mat().createAIJ(size=A.shape,csr=(A.indptr.astype(PETSc.IntType),A.indices.astype(PETSc.IntType),A.data),comm=PETSc.COMM_SELF)


def release_prepared_body(prepared):
    """Drop provider-owned matrix/mmap references after the original audit.

    Metadata and boundary receipts remain available for field output. Do not
    close a mmap explicitly: another live array view may still own it.
    """
    if prepared is not None:
        for name in ('K','owners'):
            prepared.pop(name,None)


def solve(role,folder,journal,state,*,scope_module=scope,prepared_provider=None,action_factory=None,system_adapter=None,retained_provider=None):
    scope=scope_module
    budget=scope.memory_budget(role) if hasattr(scope,"memory_budget") else scope.plan_record()["memory_budget"]
    from petsc4py import PETSc
    from .phase_explicit_accuracy_capacity import AnalyzedDirectFactor
    from .fixed_phase_fem import port_coordinate_scales
    from .dtn_port_3d import _mode_boundary_phase
    from .scattering_accuracy_boundary import carrier_pair
    from .independent_tetra_fields import complete_output
    resume=state.get('postprocessing_resume')
    if resume:
        record=json.loads(Path(resume['path']).read_text())
        if hashlib.sha256(Path(resume['path']).read_bytes()).hexdigest()!=resume['sha256']:raise ValueError('saved-only resume identity')
        old=json.loads(Path(record['pending']).read_text());a=checked(old['arrays'])
        s=core.make_setup(scope.case_spec(role),scope.physical_for(role),journal)
        if not np.array_equal(a['geometry_x'],s['geometry']['geometry_x']) or not np.array_equal(a['geometry_dofmap'],s['geometry']['geometry_dofmap']):raise ValueError('saved tetra geometry differs')
        b=load_boundary(s,old['boundary_arrays'],old['mode_sha256'])
        if not old.get('audit') or record.get('audit_recompute'):
            oracle=load_boundary(s,old['boundary_arrays'],old['mode_sha256'],q='q63')
            aud,res,orrhs=(core.audit(s,oracle,a['x'],a['rhs'],journal) if action_factory is None
                else action_factory(s,oracle).audit(a['x'],a['rhs'],journal))
            aud['arrays']=save_arrays(folder/'independent_original.npz',residual=res,rhs=orrhs,action=orrhs-res,x=a['x'])
            old.update(audit=aud,equation_pass=aud['pass_gate'])
        previous=record.get('completed_outputs')
        if previous:
            if hashlib.sha256(Path(previous['path']).read_bytes()).hexdigest()!=previous['sha256']:raise ValueError('unchanged completed outputs producer hash')
            result=json.loads(Path(previous['path']).read_text())
            if result['arrays']['sha256']!=old['arrays']['sha256']:raise ValueError('field outputs belong to different returned coefficients')
            checked(result['output']['fields']);output,accuracy=result['output'],result['accuracy']
        else:output,accuracy=complete_output(s,b,a['x'],folder,journal)
        return dict(old,status='COMPLETED',output=output,accuracy=accuracy,accuracy_pass=accuracy is not None and accuracy['pass_gate'] and old['equation_pass'],deployment_complete=True,
            new_numeric_factors=0,new_complete_solves=0,post_only=True,timings=journal.timings,postprocessing_source=state,
            original_producer=previous or resume)
    scope.require_stage(role)
    s=core.make_setup(scope.case_spec(role),scope.physical_for(role),journal)
    retained_input=retained_provider(s,folder,journal) if retained_provider is not None else None
    cap=retained_input['capacity'] if retained_input is not None else core.assembly_capacity(s,journal)
    if not cap['admitted']:return dict(status='CAPACITY_BLOCKED',capacity=cap,role=role)
    if retained_input is not None:
        prepared=None;b=retained_input['boundary'];oracle=retained_input['oracle']
    elif prepared_provider is None:
        b=core.boundary(s,47,journal,folder);oracle=core.boundary(s,63,journal,folder)
        prepared=None
    else:
        prepared=prepared_provider(s,folder,journal)
        K,form,b,oracle=tuple(prepared[k] for k in ('K','form','boundary','oracle'))
    pair=carrier_pair(b['carrier'],oracle['carrier'],b['identities'],expected_modes=s['spec']['complete_modes'])
    inc=relative(b['incident']-oracle['incident'],oracle['incident'])
    write_json(folder/'boundary_pair.json',dict(pair=pair,incident=inc))
    if not pair['pass'] or inc>1e-11:raise ValueError('complete fresh tetra q47/q63 boundary not qualified')
    if retained_input is not None:
        # This branch precedes both full-K assembly and full augmented bmat.
        recovery=retained_input['recovery'];A=recovery.matrix
        full_rhs=retained_input['full_rhs'];rhs=retained_input['rhs']
        form=retained_input['form'];H=recovery.H;n=s['P'].shape[1]
        journal.owners('assembly_time_retained_only',dict(S=A))
    else:
        if prepared_provider is None:K,form=core.production_body(s,journal)
        C,D,H=core.boundary_matrices(s,b);n=K.shape[0]
        A=sparse.bmat([[K,C],[-D,sparse.diags(H)]],format='csr');rhs=core.rhs_vector(s,b)
        journal.owners('production_full_sparse_and_boundary',dict(K=K,C=C,D=D,A=A))
    # Two nonzero complex vectors certify all interior/edge/face and all ports.
    rng=np.random.default_rng(6207);columns=[];errors=[]
    independent=action_factory(s,oracle) if action_factory is not None else None
    if retained_input is not None:
        q=retained_input['qualification']
        if not q['pass_gate']:raise ValueError('assembly-time retained original qualification')
        identity=q['arrays']
        write_json(folder/'original_operator_pairs.json',dict(q,reused=True))
    elif prepared is not None and 'reuse_original_pairs' in prepared:
        # Explicit opt-in provider has checked the original bytes, exact body
        # identity and unchanged numerical closure. Scope/log changes do not
        # demand another pair of costly full-space experiments.
        pairs=prepared['reuse_original_pairs'];errors=pairs['errors'];identity=pairs['arrays']
        if len(errors)!=2 or not all(np.isfinite(e) and e<=1e-10 for e in errors):
            raise ValueError('reused independent original action gate')
        journal.event('same_bytes_original_action_qualification_reused',
                      qualification=prepared['qualification'],new_full_body_actions=0)
        write_json(folder/'original_operator_pairs.json',dict(pairs,reused=True))
    else:
        with journal.measured('two_standard_UFL_PUBLIC_BASIX_operator_pairs'):
            inputs=[rng.normal(size=A.shape[0])+1j*rng.normal(size=A.shape[0]) for _ in range(2)]
            originals=independent(np.column_stack(inputs)) if independent is not None else None
            for i,z in enumerate(inputs):
                original=originals[:,i] if originals is not None else core.full_action(s,oracle,z,q=2*s['spec']['degree']+5)
                production=A@z
                err=relative(production-original,original);errors.append(err);columns.append((z,production,original))
                journal.calls['A']+=1
        identity=save_arrays(folder/'full_operator_witness.npz',**{f'{name}{i}':col[j] for i,col in enumerate(columns) for j,name in enumerate(('input','production','original'))})
        write_json(folder/'original_operator_pairs.json',dict(errors=errors,arrays=identity,form=form))
        if max(errors)>1e-10:raise ValueError('independent complete original action gate')
        if prepared is not None:
            from .tetra_body_checkpoint import qualification_receipt
            prepared['qualification']=qualification_receipt(prepared['checkpoint'],errors,identity,state,folder/'body_original_action_qualification.json')
    if retained_input is None:
        full_rhs=rhs;recovery=None
    if system_adapter is not None:
        recovery=system_adapter(s,A,rhs,folder,journal,state,b,oracle)
        A=recovery.matrix;rhs=recovery.condense_rhs(full_rhs)
        release_prepared_body(prepared)
        del K,C,D;gc.collect()
        journal.event('full_operator_and_prepared_owners_released_before_condensed_factor',
                      full_rows=len(full_rhs),retained_rows=A.shape[0])
    numerical_n=A.shape[0]-len(H)
    returned_nnz=A.nnz;returned_rows=A.shape[0]
    phases=[_mode_boundary_phase(m,s['cfg']) for m in b['modes']];left,right=port_coordinate_scales(numerical_n,H,phases)
    scaled=(sparse.diags(left)@A@sparse.diags(right)).tocsr();matrix=petsc_matrix(scaled)
    factor=None
    try:
        reserve=scope.plan_record().get('numeric_audit_output_reserve_seconds',6600 if scope.NAMESPACE=='v64' else 3000 if scope.NAMESPACE=='v63' else 1800)
        remaining=[scope.window.snapshot()['heavy_remaining_seconds'],scope.window.total-scope.window.charged_wall()]
        if hasattr(scope.window,'case_remaining'):remaining.append(scope.window.case_remaining(active=True))
        if min(remaining)<reserve:raise RuntimeError('full tetra cumulative audit/output/compare reserve before numeric')
        factor_options=dict(planning_limit_bytes=budget['planning_gib']*2**30)
        if hasattr(scope,'numeric_guard'):factor_options['numeric_guard']=lambda:scope.numeric_guard(role,journal)
        factor=AnalyzedDirectFactor(matrix,journal,folder,**factor_options)
        r=PETSc.Vec().createSeq(len(rhs),comm=PETSc.COMM_SELF);sol=r.duplicate();r.array[:]=left*rhs
        try:
            with journal.measured('full_uncondensed_tetra_direct_solve'):
                factor.solve_repeated(r,sol);x=right*sol.array.copy()
                for refinement in range(2):
                    res=rhs-A@x
                    if relative(res,rhs)<=1e-10:break
                    r.array[:]=left*res;factor.solve_repeated(r,sol);x+=right*sol.array
        finally:r.destroy();sol.destroy()
        reduced_true=relative(rhs-A@x,rhs)
        snapshot_residual=rhs-A@x
        if recovery is not None:
            # Returned retained coefficients are durable before reconstruction.
            retained_receipt=save_arrays(folder/'retained_returned.npz',trace_port=x,rhs=rhs,residual=snapshot_residual)
            write_json(folder/'retained_audit_pending.json',dict(status='RECOVERY_PENDING',arrays=retained_receipt,
                recovery_checkpoint=recovery.receipt,role=role,source=state))
            if retained_input is not None:
                # Returned coefficients are durable. Release opaque numeric
                # and all global Schur/scaling owners before full recovery.
                factor.destroy();factor=None;matrix.destroy();matrix=None
                del A,scaled;recovery.release_matrix();gc.collect()
                journal.event('assembly_time_global_factor_S_released_before_full_recovery')
            with journal.measured('exact_original_all_internal_recovery'):
                x=recovery.recover(x,full_rhs)
            snapshot_residual=recovery.lift_residual(snapshot_residual)
        # Commit the unique legal returned vector before ANY derived field.
        native=s['P']@x[:n]
        arrays=save_arrays(folder/'solution.npz',x=x,u_independent=x[:n],u_native=native,port=x[n:],rhs=full_rhs,residual=snapshot_residual,
            kappa=s['kappa'],masters=s['masters'],slaves=s['floquet'].mpc.slaves,P_data=s['P'].data,P_indices=s['P'].indices,P_indptr=s['P'].indptr,
            **s['geometry'])
        pending=dict(status='AUDIT_PENDING',role=role,arrays=arrays,source=state,spec=s['spec'],physical=s['physical'],form=form,
            mode_sha256=b['digest'],boundary_arrays={'q47':b['arrays'],'q63':oracle['arrays']},nnz=returned_nnz,capacity=cap,
            production_true=reduced_true,new_numeric_factors=1,new_complete_solves=1)
        if recovery is not None:
            pending.update(exact_condensation=True,condensed_checkpoint=recovery.receipt,
                condensed_true=reduced_true,full_rows=len(full_rhs),retained_rows=returned_rows,
                residual_snapshot_kind='exact algebraic lift of retained residual; original measured independently below',
                condensed_service_calls=recovery.calls,retained_returned=retained_receipt)
            pending['internal_recovery_identity']=recovery.last_identity
        if retained_input is not None:
            pending.update(assembly_time_tetra=True,local_packet=recovery.receipt,retained_checkpoint=recovery.matrix_receipt,
                producer_counters=retained_input['producer_counters'],prepared_start=True)
        if prepared is not None:pending.update(body_checkpoint=prepared['checkpoint'],body_qualification=prepared['qualification'],prepared_start=True)
        write_json(folder/'returned_audit_pending.json',pending)
        aud,res,orrhs=(core.audit(s,oracle,x,full_rhs,journal) if independent is None else independent.audit(x,full_rhs,journal))
        raw=save_arrays(folder/'independent_original.npz',residual=res,rhs=orrhs,action=orrhs-res,x=x)
        aud['arrays']=raw;pending.update(audit=aud,equation_pass=aud['pass_gate'],original_operator_witness=identity)
        write_json(folder/'returned_audit_pending.json',pending)
    finally:
        if factor is not None:factor.destroy()
        if matrix is not None:matrix.destroy()
    release_prepared_body(prepared)
    if retained_input is None:del A,scaled
    if retained_input is not None:
        recovery.release_cache();retained_input.clear()
    if recovery is None:del K,C,D
    else:del recovery
    gc.collect();journal.event('global_body_augmented_and_factor_released')
    output,accuracy=complete_output(s,b,x,folder,journal)
    result=dict(pending,status='COMPLETED',output=output,accuracy=accuracy,
        accuracy_pass=accuracy is not None and accuracy['pass_gate'] and aud['pass_gate'],deployment_complete=True,timings=journal.timings,calls=journal.calls)
    write_json(folder/'complete_scientific_result.json',result);return result


def checked(receipt):
    from .scattering_anchor_checks import checked_arrays
    return checked_arrays(receipt)


def load_boundary(s,receipts,digest,q='q47'):
    from .fullspace_dtn_action import build_dynamic_mode_inventory,FullspaceDtnCarrier,FullspaceDtnModeFunctional
    from .dtn_port_3d import _incident_projection_onto_top_mode
    a=checked(receipts[q]);modes,ids,h=build_dynamic_mode_inventory(s['cfg'])
    if h!=digest:raise ValueError('saved all828 identity')
    entries=[]
    for j,m in enumerate(modes):
        sl=slice(a['offsets'][j],a['offsets'][j+1]);rr=a['rows'][sl];c=a['C'][sl];d=a['D'][sl]
        entries.append(FullspaceDtnModeFunctional(mode_key=(j,m.side,m.m,m.n,m.polarization),coupling_rows=rr,coupling_values=c,
            projection_rows=rr,projection_values=d,normalization_h=a['H'][j],mode_identity=ids[j]))
    n=s['P'].shape[0];carrier=FullspaceDtnCarrier(entries,global_rows=n,ownership_range=(0,n),slave_rows=s['floquet'].mpc.slaves,batch_size=32,comm=s['mesh'].comm)
    return dict(carrier=carrier,modes=modes,identities=ids,digest=h,incident=a['incident_traction'],projections=np.array([_incident_projection_onto_top_mode(m,s['cfg']) for m in modes]),q=int(q[1:]),arrays=receipts[q])


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V62 live memory propagation')
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role in scope.SOLVES:return solve(role,folder,journal,state)
    if role=='VERIFY_COST':
        from benchmarks.collect_independent_tetra import verify
        return verify(folder,journal)
    raise ValueError('V62 one-run inventory')
