"""Thin V60 queue over the qualified phase, local LU and saved-field kernels."""
import gc
import numpy as np
from src.runners.task042_shared import write_json,_json_metadata
from . import local_subcell_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .trace_interior_study import add_low_space,mixed_audit,independent_complete
from .trace_interior_restriction import TraceRestriction,dense_restricted_witness
from .local_trace_assembly import local_condense,cell_data,exact_graph
from .phase_notch_hp import configured_setup
from .phase_explicit_accuracy import build_bundle,CoordinateFactor


def preflight(folder,journal):
    spec=scope.case_spec('C67');cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    low=add_low_space(cfg,setup,journal)
    with journal.measured('new_entity_support_trace_mapping'):
        R=TraceRestriction(low,setup['floquets'][7],entity_support=True)
    checks=R.qualification();mapping=R.save(folder/'entity_trace_mapping.npz')
    from .scattering_anchor_checks import checked_arrays
    parent=scope.parent('M67');old=checked_arrays(parent['trace_mapping'])
    from scipy import sparse
    previous=sparse.csr_matrix((old['R_data'],old['R_indices'],old['R_indptr']),shape=tuple(old['R_shape']))
    delta=relative((R.R-previous).data,previous.data)
    rng=np.random.default_rng(60017);t=rng.normal(size=32832)+1j*rng.normal(size=32832)
    witness=save_arrays(folder/'old_new_trace_support_pair.npz',low_trace=t,new_high_trace=R.R@t,old_high_trace=previous@t)
    small=dense_restricted_witness(6001)
    smallpass=max(small[k] for k in ('recovery','mixed','lift_invariance'))<=1e-10 and small['ambient']>1e-3
    return dict(status='COMPLETED',role='PREFLIGHT',pass_gate=checks['pass_gate'] and smallpass,
        degrees={'7':dict(pass_gate=checks['pass_gate'],mapping_check=checks)},trace_mapping=mapping,
        old_stored_support_difference=delta,old_mapping_parent=parent['trace_mapping']['sha256'],trace_witness=witness,
        small=small,new_global_factors=0,new_complete_solves=0,geometry=save_arrays(folder/'geometry.npz',**geo))


def local_capacity(R,journal):
    data=cell_data(R);low=R.low.mpc.function_space;mesh=low.mesh
    # Actual macro low trace graph; face support is its entity closure.
    import basix
    boundary=set();ref=basix.cell.geometry(basix.CellType.hexahedron)
    for c,(ar,_,p) in enumerate(R.rows):
        xyz=mesh.geometry.x[mesh.geometry.dofmap[c]]
        for z in (0.,1.):
            physical=xyz[:,2].min() if z==0 else xyz[:,2].max()
            if physical not in (mesh.geometry.x[:,2].min(),mesh.geometry.x[:,2].max()):continue
            face=next(i for i,vs in enumerate(basix.cell.topology(basix.CellType.hexahedron)[2]) if np.all(ref[vs,2]==z))
            for r in low.dofmap.cell_dofs(c)[low.element.basix_element.entity_closure_dofs[2][face]]:
                boundary.update(map(int,R.low_constraints.expansion_by_original[int(r)][0]))
    _,graph=exact_graph(data,32832,boundary)
    components=dict(low_matrix_four_index_value_copies=graph['actual_topology_nnz_envelope']*24*4,
        high_cell_LU_original_schur_recovery_plan=4*2**30,boundary_pair_and_low_map=2*2**30,
        mesh_compiler_allocator_reserve=2*2**30,evaluation_workspace=2*2**30)
    planned=sum(components.values());journal.allocation('local_assembly_total_envelope',dict(workspace_bytes=planned))
    return dict(admitted=graph['actual_topology_nnz_envelope']<=34360848 and planned<=64*2**30,
        planning_limit_bytes=64*2**30,planned_simultaneous_bytes=planned,components=components,graph=graph,
        rows=33660,native=R.nhigh,trace=32832,ambient_trace=R.R.shape[0],internal=len(R.internal_rows),
        no_global_high_schur=True,measured_nnz=None)


def solve_c67(folder,journal):
    from .phase_tensor_checkpoint import RawTensorCheckpoint
    from .phase_reference_provider import PhaseReferenceProvider
    from .phase_explicit_accuracy_fields import physical_output
    from .scattering_anchor_checks import native_recovery_action_split_check
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    scope.require_stage('C67');spec=scope.case_spec('C67');cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    low=add_low_space(cfg,setup,journal);R=TraceRestriction(low,setup['floquets'][7],entity_support=True)
    mapping=R.save(folder/'entity_trace_mapping.npz');check=R.qualification()
    cap=local_capacity(R,journal);write_json(folder/'assembly_capacity.json',cap)
    if not cap['admitted'] or not check['pass_gate']:return dict(status='CAPACITY_OR_MAPPING_BLOCKED',capacity=cap,mapping_check=check)
    setup['boundary_provider']=scope.boundary_provider(cfg,setup,folder,journal)
    boundary=setup['boundary_provider'].generate_pair()
    if not boundary['pass_gate']:return dict(status='BOUNDARY_NOT_QUALIFIED',boundary=boundary)
    bundle=rhs=u=system=inverse=factor=None
    try:
        bundle,rhs=build_bundle(cfg,setup,journal)
        checkpoint=RawTensorCheckpoint(folder/'raw_tensor',bundle,journal,reader=PhaseReferenceProvider(bundle,journal))
        system,inverse=local_condense(bundle,R,journal,checkpoint);checkpoint.finish(setup,7)
        write_json(folder/'build_audit.json',system.build_audit)
        rng=np.random.default_rng(60018);action_rows=[]
        with journal.measured('two_fixed_local_body_action_pairs'):
            for j in range(2):
                t=rng.normal(size=32832)+1j*rng.normal(size=32832);x=system.matrix.createVecRight();y=x.duplicate();x.array[:]=np.r_[t,np.zeros(828)]
                system.matrix.mult(x,y);local=system.body_action(t);error=relative(local-y.array[:32832],local)
                action_rows.append(dict(relative=error,arrays=save_arrays(folder/f'local_action_pair_{j}.npz',input=t,local=local,assembled=y.array[:32832].copy())))
                x.destroy();y.destroy()
        if max(v['relative'] for v in action_rows)>1e-10:raise ValueError('local action versus assembled body')
        factor=CoordinateFactor(system.matrix,bundle,32832,journal,folder,symbolic_capacity=True,planning_limit_bytes=64*2**30);inverse.factor=factor
        low_returns=[]
        def persist_low(z,load,native_rhs):
            receipt=save_arrays(folder/f'returned_low_{len(low_returns)}.npz',trace_port=z,condensed_rhs=load,native_rhs=native_rhs)
            low_returns.append(receipt);write_json(folder/'returned_low_inventory.json',dict(arrays=low_returns,source=journal.source_state))
        inverse.state_callback=persist_low
        with journal.measured('local_restricted_physical_solve_and_high_recovery'):
            u=inverse.apply(rhs);port=inverse.last_port_solution.copy()
        lowtrace=inverse.last_low_solution[:32832].copy()
        early=save_arrays(folder/'returned_solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],
            low_trace=lowtrace,slaves=np.asarray(setup['floquets'][7].mpc.slaves),**geo)
        minimal=dict(status='AUDIT_PENDING',role='C67',case='NOTCH',degree=7,case_spec=spec,grid='1x1x2',source=journal.source_state,
            arrays=early,returned_arrays=early,trace_mapping=mapping,capacity=cap,boundary=boundary,mode_sha256=bundle['mode_sha256'])
        write_json(folder/'minimal_scientific_state.json',minimal)
        norms,vec,ambient=mixed_audit(bundle,rhs,u,port,R,journal);refinements=[]
        for _ in range(2):
            if max(norms[k] for k in ('true','native','augmented','port'))<=1e-10:break
            d=rhs.duplicate();d.array[:]=vec['residual']
            with journal.measured('fixed_mixed_refinement'):
                delta=inverse.apply(d);u.axpy(1,delta);port+=inverse.last_port_solution;lowtrace+=inverse.last_low_solution[:32832]
            delta.destroy();d.destroy();norms,vec,ambient=mixed_audit(bundle,rhs,u,port,R,journal);refinements.append(norms)
        arrays=save_arrays(folder/'solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],low_trace=lowtrace,
            slaves=np.asarray(setup['floquets'][7].mpc.slaves),**geo,**vec)
        minimal.update(arrays=arrays,original_audit=norms,fixed_refinements=refinements);write_json(folder/'minimal_scientific_state.json',minimal)
        inverse.factor=None;factor.destroy();factor=None;system.matrix.destroy();system.matrix=None;gc.collect()
        journal.event('local_low_matrix_factor_released_original_oracle_retained')
        _,rec,rv=native_recovery_action_split_check(bundle,u,rhs,port,vec,journal)
        output=physical_output(bundle,u,port,geo,folder,journal,volume_backend='direct_phase_quadrature')
        result=dict(status='COMPLETED',role='C67',case='NOTCH',case_spec=spec,degree=7,trace_degree=6,interior_degree=7,ambient_degree=7,grid='1x1x2',
            representation='ENTITY_SUPPORTED_LOCAL_TRACE6_INTERIOR7',arrays=arrays,returned_arrays=early,original_audit=norms,ambient_audit=ambient,
            recovery=rec,recovery_arrays=save_arrays(folder/'recovery.npz',**rv),output=output,trace_mapping=mapping,mapping_check=check,capacity=cap,
            build_audit=system.build_audit,boundary=boundary,mode_sha256=bundle['mode_sha256'],fixed_refinements=refinements,
            local_action_pairs=action_rows,equation_pass=max(norms[k] for k in ('true','native','augmented','port'))<=1e-6,
            direct_target_pass=max(norms[k] for k in ('true','native','augmented','port'))<=1e-10,
            local_global_factors='HIGH_LOCAL_INTERNAL_LU_AND_GLOBAL_LOW_TRACE_MUMPS_PRESENT; high global Schur absent',
            new_complete_solves=1,new_global_numeric_factors=1,NOT_A_FULL_AMBIENT_SOLUTION=True)
        result=independent_complete(result,cfg,setup,geo,bundle,rhs,u,port,R,folder,journal,live_scope=scope)
        result['deployment_includes']=['mesh/MPC','q47/q63','15reference/raw','local LU/restricted Schur','low trace assembly/factor',
            'solve/recover/refine','independent PUBLIC_BASIX/q63','full physical output/IO/cleanup']
        result.update(raw_tensor_checkpoint=checkpoint.record(),timings=journal.timings,calls=journal.calls)
        write_json(folder/'scientific_result.json',result);return result
    finally:
        if factor is not None:factor.destroy()
        if u is not None:u.destroy()
        if rhs is not None:rhs.destroy()
        if inverse is not None:inverse.destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V60 live memory binding')
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='C67':return solve_c67(folder,journal)
    if role in ('LOCAL_RESPONSE','H2'):
        from .subcell_macro_response import execute_stage
        return execute_stage(role,folder,journal,scope)
    if role=='VERIFY_COST':
        from benchmarks.collect_local_subcell import verify
        return verify(folder,journal)
    raise ValueError('V60 stage inventory')
