"""Macro-local r2 response deployed on the original p6 trace and all ports."""
import gc
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json
from .scattering_anchor import relative,save_arrays
from .subcell_response_kernel import MacroLayout,MacroResponse,transform
from .subcell_macro_response import factory,blocks_for
from .trace_interior_restriction import trace_constraints,mixed_norms


class MacroMap:
    def __init__(self,low,high,coarse_geometry,fine_geometry,journal):
        self.low,self.high=low,high;V=low.mpc.function_space;W=high.mpc.function_space
        V.mesh.topology.create_entity_permutations();W.mesh.topology.create_entity_permutations()
        self.constraints=trace_constraints(low);self.nt=self.constraints.active_rows
        from .phase_notch_hp_fields import mesh_bounds,parents_at
        self.bounds=mesh_bounds(V);parent=parents_at(self.bounds,fine_geometry['cell_centers'])
        self.layouts=[];self.data=[];self.transforms=[];lift_cache={};transform_cache={};interpolation_cache={}
        from .hcurl_assembly_time_condensation import _cell_trace_expansion
        ip=np.asarray(V.element.basix_element.entity_dofs[3][0],int);tt=np.setdiff1d(np.arange(V.element.space_dimension),ip)
        for c in range(len(self.bounds)):
            cells=np.flatnonzero(parent==c)
            if len(cells)!=8 or len(set(fine_geometry['cell_tags'][cells]))!=1 or fine_geometry['cell_tags'][cells[0]]!=coarse_geometry['cell_tags'][c]:raise ValueError('macro children/material exact inventory')
            layout=MacroLayout.build(W,cells,self.bounds[c],interpolation_cache=interpolation_cache)
            if [len(layout.native_rows),len(layout.boundary),len(layout.inside)]!=[6084,1728,756]:raise ValueError('r2 actual local inventory')
            if layout.key in lift_cache:layout.lift=lift_cache[layout.key]
            else:layout.lift.setflags(write=False);lift_cache[layout.key]=layout.lift
            self.layouts.append(layout);self.data.append(_cell_trace_expansion(V.dofmap.cell_dofs(c)[tt],self.constraints))
            p=int(V.mesh.topology.get_cell_permutation_info()[c])
            if p not in transform_cache:transform_cache[p]=sparse.csr_matrix(transform(V,c)[np.ix_(tt,tt)].T)
            self.transforms.append(transform_cache[p])
        self.ninternal=160*4356;self.nmixed=self.ninternal+self.nt
        self.internal_offsets=np.r_[0,np.cumsum([len(l.native_rows)-len(l.boundary) for l in self.layouts])]
        n=W.dofmap.index_map.size_local;slaves=np.asarray(high.mpc.slaves,int);assigned=np.zeros(n,bool);assigned[slaves]=True
        rr=[];cc=[];vv=[];shared=[];offset=0;rng=np.random.default_rng(60024);t=rng.normal(size=self.nt)+1j*rng.normal(size=self.nt);known=np.zeros(n,complex)
        for layout,(ids,E,_),Tp in zip(self.layouts,self.data,self.transforms,strict=True):
            interior=np.setdiff1d(np.arange(len(layout.native_rows)),layout.boundary);ar=layout.native_rows[interior]
            if len(interior)!=4356 or assigned[ar].any():raise ValueError('macro internal unique ownership')
            rr.append(ar);cc.append(offset+np.arange(len(interior)));vv.append(np.ones(len(interior),complex));assigned[ar]=True;offset+=len(interior)
            M=sparse.csr_matrix(layout.lift)@Tp@E
            values=M@t[ids]
            for j,row in enumerate(layout.native_rows[layout.boundary]):
                if row in slaves:continue
                if assigned[row]:shared.append(abs(known[row]-values[j])/max(np.linalg.norm(M.getrow(j).data)*np.linalg.norm(t[ids]),1e-30));continue
                assigned[row]=True;known[row]=values[j];r=M.getrow(j)
                rr.append(np.full(len(r.indices),row,int));cc.append(self.ninternal+ids[r.indices]);vv.append(r.data.copy())
        if not assigned.all() or offset!=self.ninternal:raise ValueError('macro J canonical active inventory incomplete')
        self.J=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(n,self.nmixed)).tocsr();self.J.sum_duplicates();self.J.sort_indices()
        self.JH=self.J.conj().T.tocsr();self.internal_rows=np.concatenate([l.native_rows[np.setdiff1d(np.arange(len(l.native_rows)),l.boundary)] for l in self.layouts])
        masters=np.setdiff1d(np.arange(n),slaves);self.high_native_rows=np.setdiff1d(masters,self.internal_rows);self.slaves=slaves
        x=rng.normal(size=self.nmixed)+1j*rng.normal(size=self.nmixed);y=rng.normal(size=n)+1j*rng.normal(size=n)
        dual=abs(np.vdot(y,self.J@x)-np.vdot(self.JH@y,x))/max(np.linalg.norm(y)*np.linalg.norm(self.J@x),1e-30)
        self.check=dict(shared_operation_max=max(shared,default=0.),dual_operation=float(dual),shape=list(self.J.shape),nnz=self.J.nnz,
            mixed_FE=self.nmixed,ambient_FE=len(masters),internal=self.ninternal,trace=self.nt,actual_local_complete=6084,second_stage=756,
            csr_primal_dual_bytes=sum(a.nbytes for M in (self.J,self.JH) for a in (M.data,M.indices,M.indptr)),unique_owner=True,full_field_never_projected_to_macro=True,
            physical_tangential_operation_max=max(l.tangential_operation for l in self.layouts))
        self.check['pass_gate']=self.nt==32832 and len(masters)==834048 and max(self.check['shared_operation_max'],self.check['physical_tangential_operation_max'])<=1e-10 and dual<=1e-12
        journal.event('macro_full_primal_dual_inventory',**self.check)
        if not self.check['pass_gate']:raise ValueError('macro field mapping interface not trustworthy')
    def pull_native(self,x):return self.JH@np.asarray(x)
    def save(self,path):return save_arrays(path,J_indptr=self.J.indptr,J_indices=self.J.indices,J_data=self.J.data,J_shape=np.asarray(self.J.shape),
        internal_rows=self.internal_rows,high_native_rows=self.high_native_rows,slaves=self.slaves)


def assemble_macro(matrix_map,responses,carrier,journal):
    from petsc4py import PETSc
    from .local_trace_assembly import exact_graph
    nt=matrix_map.nt;ports=len(carrier.entries);border=set();entries=[]
    for e in carrier.entries:
        fields=[]
        for rows,values in ((e.coupling_rows,e.coupling_values),(e.projection_rows,e.projection_values)):
            v=np.zeros(matrix_map.J.shape[0],complex);v[rows]=values
            # C is a dual column; D is a primal row. They are not assumed mutual.
            low=matrix_map.pull_native(v) if len(fields)==0 else np.conj(matrix_map.pull_native(np.conj(v)))
            if np.any(low[:matrix_map.ninternal]!=0):raise ValueError('physical port touches macro interior; topology boundary qualification failed')
            low=low[matrix_map.ninternal:];ids=np.flatnonzero(low!=0);border.update(map(int,ids));fields.append((ids,low[ids]))
        entries.append(fields)
    counts,graph=exact_graph(matrix_map.data,nt,border,ports)
    if graph['actual_topology_nnz_envelope']>34360848:raise ValueError('macro original trace graph exceeds mathematical bound')
    journal.allocation('macro_low_global_matrix_copies',dict(workspace_bytes=4*graph['actual_topology_nnz_envelope']*24))
    matrix=PETSc.Mat().createAIJ(size=(nt+ports,nt+ports),nnz=counts,comm=PETSc.COMM_SELF);matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,True)
    with journal.measured('macro_direct_original_trace_global_assembly'):
        for response,(ids,E,_),Tp in zip(responses,matrix_map.data,matrix_map.transforms,strict=True):
            Ec=Tp@E;block=Ec.conj().T@(response.low_schur@Ec)
            matrix.setValues(ids,ids,np.ascontiguousarray(block),addv=PETSc.InsertMode.ADD_VALUES)
        for p,(e,fields) in enumerate(zip(carrier.entries,entries,strict=True)):
            (cr,cv),(dr,dv)=fields
            matrix.setValues(cr,[nt+p],np.ascontiguousarray(cv),addv=PETSc.InsertMode.ADD_VALUES)
            matrix.setValues([nt+p],dr,np.ascontiguousarray(-dv),addv=PETSc.InsertMode.ADD_VALUES)
            matrix.setValue(nt+p,nt+p,e.normalization_h,addv=PETSc.InsertMode.ADD_VALUES)
        matrix.assemble()
    graph.update(measured_nnz=int(matrix.getInfo()['nz_used']),global_micro_schur=False,global_micro_factor=False)
    journal.event('macro_original_trace_matrix_inventory',**graph);return matrix,graph


class MacroInverse:
    def __init__(self,mapping,responses,factor,*,ports=828,state_callback=None):self.map=mapping;self.responses=responses;self.factor=factor;self.last_port_solution=None;self.last_trace=None;self.state_callback=state_callback;self.ports=ports
    def apply(self,rhs,port_rhs=None):
        from petsc4py import PETSc
        m=self.map;g=m.pull_native(rhs.array);t=g[m.ninternal:].copy()
        for c,(l,response,(ids,E,_),Tp) in enumerate(zip(m.layouts,self.responses,m.data,m.transforms,strict=True)):
            start,end=m.internal_offsets[c:c+2];f=np.zeros(len(l.native_rows),complex);interior=np.setdiff1d(np.arange(len(l.native_rows)),l.boundary);f[interior]=g[start:end]
            reduced,_=response.reduce(f);np.add.at(t,ids,E.conj().T@Tp.conj().T@reduced)
        pr=np.zeros(self.ports,complex) if port_rhs is None else np.asarray(port_rhs)
        if pr.shape!=(self.ports,):raise ValueError('complete macro port RHS inventory')
        b=PETSc.Vec().createSeq(m.nt+self.ports,comm=PETSc.COMM_SELF);z=b.duplicate();b.array[:]=np.r_[t,pr]
        try:
            self.factor.solve_repeated(b,z)
            if self.state_callback is not None:self.state_callback(z.array.copy(),b.array.copy(),rhs.array.copy())
            self.last_port_solution=z.array[m.nt:].copy();self.last_trace=z.array[:m.nt].copy()
            mixed=np.zeros(m.nmixed,complex);mixed[m.ninternal:]=self.last_trace
            for c,(l,response,(ids,E,_),Tp) in enumerate(zip(m.layouts,self.responses,m.data,m.transforms,strict=True)):
                start,end=m.internal_offsets[c:c+2];f=np.zeros(len(l.native_rows),complex);interior=np.setdiff1d(np.arange(len(l.native_rows)),l.boundary);f[interior]=g[start:end]
                local=response.recover(Tp@(E@self.last_trace[ids]),f);mixed[start:end]=local[interior]
            out=rhs.duplicate();out.array[:]=m.J@mixed;self.last_mixed=mixed;return out
        finally:b.destroy();z.destroy()


def solve_h2(folder,journal,scope):
    from .phase_notch_hp import configured_setup
    from .phase_explicit_accuracy import build_bundle,CoordinateFactor
    from .scattering_anchor import audit_original
    from .phase_explicit_accuracy_fields import physical_output
    from .phase_deployment import fixed_output
    from .phase_saved_uncondensed import uncondensed_vectors,saved_audit
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field,destroy_same_mesh_physical_action
    from .phase_boundary_checkpoint import StudyBoundaryProvider
    from .scattering_anchor_checks import checked_arrays
    scope.require_stage('H2');spec=scope.case_spec('H2');cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    macrospec=dict(spec,splits=[1,1,2],cells=160,independent=104832,trace=32832,internal=72000,rows=33660)
    mcfg,macro,mgeo=configured_setup(macrospec,journal,scope=scope)
    mapping=MacroMap(macro['floquets'][6],setup['floquets'][6],mgeo,geo,journal);mapreceipt=mapping.save(folder/'macro_mapping.npz')
    journal.allocation('r2_class_cache_and_sparse_macro_map',dict(workspace_bytes=8*2**30+mapping.check['csr_primal_dual_bytes']))
    raw_factory=factory(setup['spaces'][6],cfg,journal);childcache={};cache={};responses=[];class_packets={};W=setup['spaces'][6]
    for c,l in enumerate(mapping.layouts):
        tag=int(mgeo['cell_tags'][c]);blocks=blocks_for(W,l,tag,raw_factory,childcache,journal);key=(l.key,tag)
        if key not in cache:
            cache[key]=MacroResponse(l,blocks,journal,response=True)
            current=sum(r.bytes() for r in cache.values())+sum(b.bytes() for b in childcache.values())
            if current>8*2**30:raise MemoryError('r2 exact class cache exceeds 8GiB; no per-cell duplicate library allowed')
            d=folder/'local_response_packets';d.mkdir(exist_ok=True)
            packet=save_arrays(d/(str(c)+'.npz'),macro_schur=cache[key].low_schur,inner_from_trace=cache[key].X,boundary_lift=l.lift,second_factor=cache[key].factor[0],second_pivots=cache[key].factor[1],
                second_trace_to_inside_data=cache[key].Sib.data,second_trace_to_inside_indices=cache[key].Sib.indices,second_trace_to_inside_indptr=cache[key].Sib.indptr,
                second_inside_to_trace_data=cache[key].Sbi.data,second_inside_to_trace_indices=cache[key].Sbi.indices,second_inside_to_trace_indptr=cache[key].Sbi.indptr,
                child_rows=np.asarray(l.child_rows),child_interiors=np.asarray(l.child_interiors),child_traces=np.asarray(l.child_traces),macro_boundary=l.boundary,macro_inside=l.inside,macro_trace=l.trace)
            class_packets[id(cache[key])]=packet
            write_json(d/(str(c)+'.json'),dict(key=l.key,tag=tag,capacity=cache[key].capacity,local_factor_backward=cache[key].backward,cache_bytes=current))
        responses.append(cache[key]);journal.event('macro_local_response_committed',cell=c,classes=len(cache),child_classes=len(childcache))
    if len(responses)!=160:raise ValueError('macro response inventory')
    setup['boundary_provider']=StudyBoundaryProvider(cfg,setup,folder,journal,entity_face_support=True);boundary=setup['boundary_provider'].generate_pair()
    if not boundary['pass_gate']:return dict(status='BOUNDARY_NOT_QUALIFIED',role='H2',boundary=boundary)
    bundle=rhs=u=factor=matrix=None
    try:
        bundle,rhs=build_bundle(cfg,setup,journal);matrix,graph=assemble_macro(mapping,responses,bundle['dtn_action'].carrier,journal)
        from .local_schur_bank import save_bank,SavedLocalSchurAction
        bank=save_bank(mapping,class_packets,responses,folder/'local_schur_bank',journal.source_state['source_sha'])
        action_pairs=[]
        with journal.measured('saved_local_schur_reload_two_actual_body_actions'):
            action=SavedLocalSchurAction(bank['path'],source_sha=bank['source_sha'],manifest_sha256=bank['sha256'],trace_rows=32832,cell_count=160)
            from petsc4py import PETSc
            rng=np.random.default_rng(60030);x=matrix.createVecRight();y=x.duplicate()
            try:
                for j in range(2):
                    t=rng.normal(size=32832)+1j*rng.normal(size=32832);x.array[:]=np.r_[t,np.zeros(828)];matrix.mult(x,y)
                    local=action.apply(t);error=relative(local-y.array[:32832],y.array[:32832])
                    action_pairs.append(dict(relative=error,arrays=save_arrays(folder/f'saved_local_action_pair_{j}.npz',input=t,local=local,assembled=y.array[:32832].copy())))
                bank.update(readonly_loaded_owner_payload_bytes=action.owner_payload_bytes,qualified_actions=action.calls)
            finally:x.destroy();y.destroy()
            del action
        if max(r['relative'] for r in action_pairs)>1e-10:raise ValueError('saved local action differs from actual assembled body')
        if scope.numeric_factor_attempts()>=3:raise RuntimeError('V60 no fourth global numeric factor, including any post flag')
        factor=CoordinateFactor(matrix,bundle,32832,journal,folder,symbolic_capacity=True,planning_limit_bytes=64*2**30)
        low_returns=[]
        def persist_low(z,load,native_rhs):
            receipt=save_arrays(folder/f'returned_low_{len(low_returns)}.npz',trace_port=z,condensed_rhs=load,native_rhs=native_rhs)
            low_returns.append(receipt);write_json(folder/'returned_low_inventory.json',dict(arrays=low_returns,source=journal.source_state,macro_map=mapreceipt))
        inverse=MacroInverse(mapping,responses,factor,state_callback=persist_low)
        with journal.measured('macro_restricted_global_solve_all_microfield_recovery'):u=inverse.apply(rhs);port=inverse.last_port_solution.copy()
        lowtrace=inverse.last_trace.copy()
        early=save_arrays(folder/'returned_solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),low_trace=inverse.last_trace,kappa=bundle['kappa'],slaves=mapping.slaves,**geo)
        minimal=dict(status='AUDIT_PENDING',role='H2',case='NOTCH',degree=6,case_spec=spec,source=journal.source_state,returned_arrays=early,arrays=early,trace_mapping=mapreceipt,boundary=boundary,graph=graph)
        write_json(folder/'minimal_scientific_state.json',minimal)
        def audit():
            ambient,v=audit_original(bundle,rhs,u,port,journal);norm=mixed_norms(v,rhs.array,mapping);norm.update(identity=ambient['identity'],slave_zero=ambient['slave_zero']);return norm,v,ambient
        norms,vec,ambient=audit();refinements=[]
        for _ in range(2):
            if max(norms[k] for k in ('true','native','augmented','port'))<=1e-10:break
            d=rhs.duplicate();d.array[:]=vec['residual'];delta=inverse.apply(d);u.axpy(1,delta);port+=inverse.last_port_solution;lowtrace+=inverse.last_trace;delta.destroy();d.destroy()
            norms,vec,ambient=audit();refinements.append(norms)
        arrays=save_arrays(folder/'solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),kappa=bundle['kappa'],low_trace=lowtrace,slaves=mapping.slaves,**geo,**vec)
        minimal.update(arrays=arrays,original_audit=norms,ambient_audit=ambient);write_json(folder/'minimal_scientific_state.json',minimal)
        factor.destroy();factor=None;matrix.destroy();matrix=None;inverse.factor=None;gc.collect();journal.event('global_factor_low_matrix_released_complete_microfield_retained')
        output=physical_output(bundle,u,port,geo,folder,journal,volume_backend='direct_phase_quadrature')
        result=dict(status='COMPLETED',role='H2',case='NOTCH',degree=6,case_spec=spec,grid='2x2x4',representation='MACRO_TRACE6_ALL_R2_P6_MICRO_INTERIORS',arrays=arrays,returned_arrays=early,
            original_audit=norms,ambient_audit=ambient,trace_mapping=mapreceipt,mapping_check=mapping.check,boundary=boundary,output=output,mode_sha256=bundle['mode_sha256'],
            new_complete_solves=1,new_global_numeric_factors=1,graph=graph,local_response_classes=len(cache),child_local_classes=len(childcache),
            local_schur_bank=bank,local_body_action_pairs=action_pairs,cache_payload_bytes=sum(r.bytes() for r in cache.values())+sum(b.bytes() for b in childcache.values()),fixed_refinements=refinements,
            local_global_factors='R2_CHILD_INTERNAL_AND_MACRO_INTERNAL_LOCAL_LU_PLUS_GLOBAL_MACRO_TRACE_MUMPS_PRESENT; no global micro Schur',
            NOT_A_FULL_AMBIENT_SOLUTION=True,source=journal.source_state)
        field=restore_p0_full_field(setup['floquets'][6],u)
        from .phase_tangential_audit import audit_tangential
        result['tangential_check']=audit_tangential(field,bundle,folder,'H2',journal)
        fixed_output(result,field,cfg,bundle['kappa'],folder,journal)
        vals=uncondensed_vectors(field,cfg,bundle['kappa'],setup['floquets'][6].mpc,setup['mesh_data'],folder/'independent_volume',journal,q=15,
            identity=dict(parent_npz_sha256=arrays['sha256'],original_polynomial_body_q15_qualified=True,macro_map=mapreceipt['sha256']))
        ind=setup['boundary_provider'].bundle(63);d=folder/'independent_original';d.mkdir();high=saved_audit(checked_arrays(arrays),setup,cfg,field,vals,ind,d,journal)
        h=checked_arrays(high['arrays']);iv=dict(residual=h['residual'],augmented_residual=h['augmented_top'],port_residual=h['port_residual'],projected=h['projected'])
        mixed=mixed_norms(iv,h['rhs'],mapping);mixed.update(identity=high['original_audit']['identity'],slave_zero=high['original_audit']['slave_zero'])
        mr=save_arrays(d/'macro_mixed_original.npz',mixed_residual=mapping.pull_native(h['residual']),mixed_augmented=mapping.pull_native(h['augmented_top']),mixed_rhs=mapping.pull_native(h['rhs']),ambient_residual=h['residual'])
        passed=max(mixed[k] for k in ('true','native','augmented','port'))<=1e-6 and mixed['identity']<=1e-10 and mixed['slave_zero']
        # Included macro-internal rows use identity: their independent full
        # residual is therefore checked, in addition to child affine recovery.
        recs=[]
        for c in range(160):
            start,end=mapping.internal_offsets[c:c+2];rows=mapping.internal_rows[start:end]
            recs.append(float(np.linalg.norm(h['residual'][rows])/max(np.linalg.norm(h['volume_curl'][rows])+np.linalg.norm(h['volume_mass'][rows]),1e-30)))
        rec=max(recs)
        result['independent']=dict(audit_path='PUBLIC_BASIX_ALL_R2_MICRO_BODY_Q15_Q63_HERMITIAN_MACRO_PULLBACK',original_audit=mixed,ambient_original=high,arrays=mr,equation_pass=passed,recovery_pass=rec<=1e-10 and high['recovery_pass'],macro_internal_operation_scaled=rec,macro_internal_operation_by_cell=recs,
            direct_internal_target_pass=max(mixed[k] for k in ('true','native','augmented','port'))<=1e-10,NOT_A_FULL_AMBIENT_SOLUTION=True)
        result.update(deployment_complete=passed and result['independent']['recovery_pass'] and result['tangential_check']['pass_gate'],equation_pass=passed,capacity=dict(rows=33660,mixed=729792,ambient=834048,class_cache_limit=8*2**30),timings=journal.timings,calls=journal.calls)
        write_json(folder/'completed_deployment_state.json',result);return result
    finally:
        if factor is not None:factor.destroy()
        if matrix is not None:matrix.destroy()
        if u is not None:u.destroy()
        if rhs is not None:rhs.destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)
