"""Two finite fixed-trace physical solves over existing qualified kernels."""
import gc
import json
from pathlib import Path
import numpy as np
from scipy.linalg import lu_factor,lu_solve
from src.runners.task042_shared import write_json,_json_metadata
from . import trace_interior_scope as scope
from .trace_interior_restriction import TraceRestriction,RestrictedTraceFactor,sparse_projection,mixed_norms,dense_restricted_witness,projection_pattern_envelope
from .scattering_anchor import Journal,save_arrays,relative,condense,audit_original
from .scattering_anchor_checks import checked_arrays
from .phase_notch_hp import configured_setup
from .phase_explicit_accuracy import build_bundle,CoordinateFactor


def add_low_space(cfg,setup,journal):
    from dolfinx import fem,default_real_type
    from basix.ufl import element
    from .fixed_phase_fem import envelope_configuration
    from dataclasses import replace
    from src.constraints.floquet_3d import build_double_floquet_mpc
    with journal.measured('same_mesh_trace6_space_MPC'):
        V=fem.functionspace(setup['mesh'],element('N1curl',setup['mesh'].basix_cell(),6,dtype=default_real_type))
        low=replace(cfg,nedelec_degree=6,visualization_degree=6)
        f=build_double_floquet_mpc(V,setup['mesh_data'],envelope_configuration(low,setup['numerical_carrier']))
        setup['spaces'][6]=V;setup['floquets'][6]=f
    return f


def degree_qualification(q,folder,journal):
    from .phase_p_order_consistency import raw_direction_action
    from .hcurl_affine_phase_tensor import AffinePhaseReferenceTensor
    from .phase_deployment import quadrature_certificate
    spec=scope.case_spec('M6'+str(q));cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    low=add_low_space(cfg,setup,journal);high=setup['floquets'][q]
    with journal.measured('canonical_trace6_to_'+str(q)+'_sparse_mapping'):
        R=TraceRestriction(low,high)
    mapcheck=R.qualification();mapping=R.save(folder/'trace_restriction.npz')
    if R.R.shape!=(spec['trace'],32832):raise ValueError('actual mixed trace dimensions')
    V=setup['spaces'][q];el=V.element.basix_element;cert=quadrature_certificate(el,2*q+3)
    cells=[int(np.flatnonzero(geo['cell_tags']==tag)[0]) for tag in (cfg.tags.air,cfg.tags.substrate)]
    rng=np.random.default_rng(5900+q);coef=rng.normal(size=el.dim)+1j*rng.normal(size=el.dim)
    with journal.measured('narrow_p'+str(q)+'_phase_reference_qualification'):
        factory=AffinePhaseReferenceTensor(el,kappa=setup['numerical_carrier'],k0=cfg.k0,mu=cfg.mu_r,
            epsilon_by_tag={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating},q=2*q+3)
        rows=[]
        for c in cells:
            xyz=setup['mesh'].geometry.x[setup['mesh'].geometry.dofmap[c]];tag=int(geo['cell_tags'][c]);eps=factory.epsilon[tag]
            tensor,scale=factory.tensor(tag=tag,widths=xyz.max(axis=0)-xyz.min(axis=0),return_scale=True)
            a=tensor@coef;b,parts=raw_direction_action(el,xyz,coef,setup['numerical_carrier'],cfg.k0,eps,cfg.mu_r,16)
            op=np.linalg.norm(a-b)/max(scale*np.linalg.norm(coef),1e-30)
            rows.append(dict(cell=c,tag=tag,q31_vector=relative(a-b,b),operation_scaled=float(op),
                arrays=save_arrays(folder/f'raw_witness_{c}.npz',coefficient=coef,combined=a,independent_q31=b,**parts)))
        # Real one-cell full restriction vs high-interior Schur restriction.
        c=cells[0];xyz=setup['mesh'].geometry.x[setup['mesh'].geometry.dofmap[c]]
        A=factory.tensor(tag=int(geo['cell_tags'][c]),widths=xyz.max(axis=0)-xyz.min(axis=0))
        ii=np.asarray(el.entity_dofs[3][0],int);tt=R.bt;L=R.local[int(V.mesh.topology.get_cell_permutation_info()[c])]
        inv=lu_factor(A[np.ix_(ii,ii)]);ait=A[np.ix_(ii,tt)];ati=A[np.ix_(tt,ii)]
        schur=A[np.ix_(tt,tt)]-ati@lu_solve(inv,ait)
        projected=L.conj().T@schur@L
        direct_tt=L.conj().T@A[np.ix_(tt,tt)]@L
        direct_ti=L.conj().T@ati;direct_it=ait@L
        other=direct_tt-direct_ti@lu_solve(inv,direct_it)
        form_pair=relative(projected-other,projected)
    return dict(degree=q,actual_basis_dimension=int(el.dim),actual_local_interior=len(ii),trace_mapping=mapping,mapping_check=mapcheck,
        body_certificate=cert,raw_classes=rows,one_real_cell_schur_pair=form_pair,one_local_LU_qualification=1,
        pass_gate=mapcheck['pass_gate'] and cert['pass_gate'] and max(x['q31_vector'] for x in rows)<=1e-10
            and max(x['operation_scaled'] for x in rows)<=1e-12 and form_pair<=1e-10,
        new_complete_solves=0,new_global_factors=0)


def preflight(folder,journal):
    small=dense_restricted_witness();write_json(folder/'complex_block_witness.json',small)
    if max(small[k] for k in ('recovery','lift_invariance','mixed'))>1e-10 or small['ambient']<=1e-3:raise ValueError('restricted complex block algebra')
    degrees={}
    for q in (7,8):
        d=folder/('p'+str(q));d.mkdir()
        degrees[str(q)]=degree_qualification(q,d,journal);write_json(folder/'qualification_progress.json',dict(degrees=degrees))
        gc.collect()
    return dict(status='COMPLETED',role='PREFLIGHT',degrees=degrees,small=small,pass_gate=all(v['pass_gate'] for v in degrees.values()),
        new_complete_solves=0,new_global_factors=0)


def mixed_audit(bundle,rhs,u,port,R,journal):
    ambient,v=audit_original(bundle,rhs,u,port,journal);norms=mixed_norms(v,rhs.array,R)
    norms.update(identity=ambient['identity'],slave_zero=ambient['slave_zero'])
    v.update(mixed_residual=R.pull_native(v['residual']),mixed_augmented_top=R.pull_native(v['augmented_residual']),mixed_rhs=R.pull_native(rhs.array))
    return norms,v,ambient


def independent_complete(result,cfg,setup,geo,bundle,rhs,u,port,R,folder,journal):
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from .phase_saved_uncondensed import uncondensed_vectors,saved_audit
    from .phase_deployment import fixed_output
    field=restore_p0_full_field(setup['floquets'][cfg.nedelec_degree],u)
    fixed_output(result,field,cfg,bundle['kappa'],folder,journal)
    vals=uncondensed_vectors(field,cfg,bundle['kappa'],setup['floquets'][cfg.nedelec_degree].mpc,setup['mesh_data'],folder/'independent_volume',journal,
        q=2*cfg.nedelec_degree+3,identity=dict(parent_npz_sha256=result['arrays']['sha256'],own_degree_qualification=scope.stage('PREFLIGHT')['degrees'][str(cfg.nedelec_degree)]['pass_gate']))
    ind=setup['boundary_provider'].bundle(63);d=folder/'independent_original';d.mkdir(exist_ok=True)
    high=saved_audit(checked_arrays(result['arrays']),setup,cfg,field,vals,ind,d,journal)
    h=checked_arrays(high['arrays']);vec={'residual':h['residual'],'augmented_residual':h['augmented_top'],
        'port_residual':h['port_residual'],'projected':h['projected']}
    norms=mixed_norms(vec,h['rhs'],R);norms.update(identity=high['original_audit']['identity'],slave_zero=high['original_audit']['slave_zero'])
    mapped=save_arrays(d/'mixed_original_vectors.npz',mixed_residual=R.pull_native(h['residual']),mixed_augmented_top=R.pull_native(h['augmented_top']),
        mixed_rhs=R.pull_native(h['rhs']),ambient_residual=h['residual'],port_residual=h['port_residual'],projected=h['projected'])
    eq=all(norms[k]<=1e-6 for k in ('true','native','augmented','port')) and norms['identity']<=1e-10 and norms['slave_zero']
    result['independent']=dict(audit_path='PUBLIC_BASIX_HIGH_BODY_Q63_BOUNDARY_HERMITIAN_MIXED_PULLBACK',original_audit=norms,
        ambient_original=high,arrays=mapped,equation_pass=eq,recovery_pass=high['recovery_pass'],
        direct_internal_target_pass=max(norms[k] for k in ('true','native','augmented','port'))<=1e-10,NOT_A_FULL_AMBIENT_SOLUTION=True)
    result.update(deployment_complete=eq and high['recovery_pass'],boundary_provider=dict(folder=str(setup['boundary_provider'].folder),
        generated=dict(setup['boundary_provider'].generated),loads=dict(setup['boundary_provider'].loads)),
        deployment_includes=['mesh/MPC','q47/q63','15reference/raw','local LU/high Schur','sparse restriction','low factor','solve/recover/refine',
            'mixed independent original','full physical E/H/curl/240/modes/power/absorption','provenance/IO/cleanup'],research_comparisons_in_this_process=False)
    write_json(folder/'completed_deployment_state.json',result)
    return result


def solve_case(role,folder,journal):
    from .phase_notch_hp_capacity import assembly_capacity
    from .phase_tensor_checkpoint import RawTensorCheckpoint
    from .phase_reference_provider import PhaseReferenceProvider
    from .phase_explicit_accuracy_fields import physical_output
    from .scattering_anchor_checks import native_recovery_action_split_check
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    scope.require_stage(role);spec=scope.case_spec(role)
    cfg,setup,geo=configured_setup(spec,journal,scope=scope);low=add_low_space(cfg,setup,journal)
    cap=assembly_capacity(setup,cfg,journal,spec,planning_limit_bytes=64*2**30,sampled_stop_bytes=96*2**30,extra_workspace_bytes=2*2**30,row_cap=100000)
    write_json(folder/'assembly_capacity.json',cap)
    if not cap['admitted']:return dict(status='CAPACITY_BLOCKED',role=role,capacity=cap)
    bundle=rhs=system=inverse=u=factor=reduced=None
    try:
        setup['boundary_provider']=scope.boundary_provider(cfg,setup,folder,journal);boundary=setup['boundary_provider'].generate_pair()
        if not boundary['pass_gate']:return dict(status='BOUNDARY_NOT_QUALIFIED',role=role,boundary=boundary)
        bundle,rhs=build_bundle(cfg,setup,journal)
        checkpoint=RawTensorCheckpoint(folder/'raw_tensor',bundle,journal,reader=PhaseReferenceProvider(bundle,journal))
        system,inverse=condense(bundle,journal,expected=(cap['native'],spec['trace'],spec['internal']),raw_tensor_provider=checkpoint)
        checkpoint.finish(setup,spec['degree']);write_json(folder/'build_audit.json',system.build_audit)
        with journal.measured('actual_sparse_trace_restriction'):
            R=TraceRestriction(low,setup['floquets'][spec['degree']],high_constraints=system.trace_constraints)
        mapcheck=R.qualification();mapping=R.save(folder/'trace_restriction.npz')
        if not mapcheck['pass_gate'] or mapcheck['csr_bytes']>512*2**20:raise ValueError('case trace restriction not qualified')
        # Before allocation include high, low, product graph envelopes; a
        # low-trace stencil lives on the same cells, without global filling.
        lowcap=assembly_capacity(dict(setup,spaces={6:setup['spaces'][6]},floquets={6:low}),__import__('dataclasses').replace(cfg,nedelec_degree=6),journal,
            dict(independent=104832,trace=32832,internal=72000,cells=160,rows=33660,complete_modes=828),planning_limit_bytes=64*2**30,row_cap=100000)
        graph=projection_pattern_envelope(R,828)
        journal.event('restricted_projection_pattern_envelope',**graph)
        journal.allocation('restricted_sparse_projection',dict(workspace_bytes=graph['workspace_bytes']))
        reduced=sparse_projection(system.matrix,R.R,828,journal)
        if reduced.getSize()!=(33660,33660):raise ValueError('fixed trace6 global rows')
        # Keep independent uncondensed action and local recovery. The high
        # global matrix is neither factored nor needed beyond projection.
        system.matrix.destroy();system.matrix=None;gc.collect()
        factor=RestrictedTraceFactor(R.R,828,CoordinateFactor(reduced,bundle,32832,journal,folder,symbolic_capacity=True,planning_limit_bytes=64*2**30))
        inverse.factor=factor
        with journal.measured('restricted_physical_solve_and_all_high_internal_recovery'):
            u=inverse.apply(rhs);port=inverse.last_port_solution.copy()
        committed_low_trace=factor.last_low_solution[:32832].copy()
        early=save_arrays(folder/'returned_solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],
            low_trace=factor.last_low_solution[:32832],slaves=np.asarray(setup['floquets'][spec['degree']].mpc.slaves),**geo)
        minimal=dict(status='AUDIT_PENDING',role=role,case='NOTCH',degree=spec['degree'],case_spec=spec,grid='1x1x2',source=journal.source_state,
            arrays=early,returned_arrays=early,trace_mapping=mapping,capacity=cap,boundary=boundary,mode_sha256=bundle['mode_sha256'])
        write_json(folder/'minimal_scientific_state.json',minimal)
        norms,vec,ambient=mixed_audit(bundle,rhs,u,port,R,journal);refinements=[]
        for _ in range(2):
            if max(norms[k] for k in ('true','native','augmented','port'))<=1e-10:break
            d=rhs.duplicate();d.array[:]=vec['residual']
            with journal.measured('fixed_mixed_refinement'):
                delta=inverse.apply(d);u.axpy(1,delta);port+=inverse.last_port_solution
                committed_low_trace+=factor.last_low_solution[:32832]
            delta.destroy();d.destroy();norms,vec,ambient=mixed_audit(bundle,rhs,u,port,R,journal);refinements.append(norms)
        arrays=save_arrays(folder/'solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),low_trace=committed_low_trace,kappa=bundle['kappa'],
            slaves=np.asarray(setup['floquets'][spec['degree']].mpc.slaves),**geo,**vec)
        minimal.update(arrays=arrays,original_audit=norms,ambient_audit=ambient,fixed_refinements=refinements)
        write_json(folder/'minimal_scientific_state.json',minimal)
        inverse.factor=None;factor.destroy();factor=None;reduced.destroy();reduced=None;gc.collect()
        journal.event('low_factor_high_low_matrix_released_original_oracle_retained')
        _,recovery,rv=native_recovery_action_split_check(bundle,u,rhs,port,vec,journal)
        rec=save_arrays(folder/'recovery.npz',**rv);output=physical_output(bundle,u,port,geo,folder,journal,volume_backend='direct_phase_quadrature')
        eq=all(norms[k]<=1e-6 for k in ('true','native','augmented','port')) and norms['identity']<=1e-10 and norms['slave_zero']
        result=dict(status='COMPLETED',role=role,case='NOTCH',case_spec=spec,degree=spec['degree'],trace_degree=6,interior_degree=spec['degree'],ambient_degree=spec['degree'],grid='1x1x2',
            representation='FIXED_PHASE_TRACE6_ALL_AMBIENT_INTERIORS',arrays=arrays,returned_arrays=early,original_audit=norms,ambient_audit=ambient,
            recovery=recovery,recovery_arrays=rec,output=output,equation_pass=eq,direct_target_pass=max(norms[k] for k in ('true','native','augmented','port'))<=1e-10,
            trace_mapping=mapping,mapping_check=mapcheck,projection_graph_plan=graph,capacity=cap,build_audit=_json_metadata(system.build_audit),boundary=boundary,mode_sha256=bundle['mode_sha256'],
            fixed_refinements=refinements,local_global_factors='ambient local internal LU plus GLOBAL_LOW_TRACE_EXACT_MUMPS_FACTOR_PRESENT; no high global factor',
            NOT_A_FULL_AMBIENT_SOLUTION=True,new_complete_solves=1,new_global_numeric_factors=1)
        result=independent_complete(result,cfg,setup,geo,bundle,rhs,u,port,R,folder,journal)
        result.update(raw_tensor_checkpoint=checkpoint.record(),timings=journal.timings,calls=journal.calls)
        write_json(folder/'scientific_result.json',result);return result
    finally:
        if factor is not None:factor.destroy()
        if reduced is not None:reduced.destroy()
        if u is not None:u.destroy()
        if rhs is not None:rhs.destroy()
        if inverse is not None:inverse.destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V59 live memory binding')
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role in scope.SOLVES:return solve_case(role,folder,journal)
    if role=='VERIFY_COST':
        from benchmarks.collect_trace_interior import verify
        return verify(folder,journal)
    raise ValueError('V59 stage inventory')
