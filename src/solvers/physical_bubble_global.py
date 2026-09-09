"""Research-only cell bubble enrichment of the existing p2 auxiliary space."""
import hashlib
import json
import time
import numpy as np


def constrained_cell_correction(delta, targets, coefficients):
    """Compress existing MPC links and form E^H delta E, including complex phases."""
    valid=targets>=0
    rows=np.unique(targets[valid])
    E=np.zeros((len(targets),len(rows)),complex)
    i,j=np.nonzero(valid)
    np.add.at(E,(i,np.searchsorted(rows,targets[valid])),coefficients[valid])
    return rows,E.conj().T@delta@E


class BubbleEnrichedSpace:
    """Stream exact classes, then borrow the existing owner/MPC operations for W/WH.

    Full W storage avoids a second interior-only MPI framework. Local D/LU/A
    live for one class only; the retained W and delta-S cache is explicitly
    included in the same 512 MiB bottom-factor policy.
    """
    def __init__(self,levels,cfg,actions,*,sample,marker,save):
        import basix
        from .fullspace_same_mesh_hcurl_pmg import _n1e,_dof_transform,build_same_mesh_hcurl_transfer
        from .fullspace_same_mesh_hcurl_pmg_runtime import SameMeshHcurlOwnerTransfer
        from .fullspace_physical_intermediate_runtime import AlgebraicOwnerTransfer
        from .fullspace_v17_p3_oracle import compile_physical_diagnostic_volume
        from .hcurl_assembly_time_condensation import _cell_integral_kernels,_tabulate_raw_tensor_class
        from .physical_bubble_local import harmonic_bubble_check,trace_checks,fixed_bubble_basis
        from .hcurl_affine_isotropic_tensor import AffineIsotropicMaxwellTensorSpec,AffineIsotropicMaxwellTensorFactory
        self.owner=None;self.classes={};self.cells={};self.sample=sample;self.save=save
        self.levels=levels;self.carrier=actions['physical'][2]['dtn_action'].carrier
        self.action=actions['physical'][4]['physical_action'];self.composed_action=self
        self.counts=dict(composed_started=0,composed_completed=0,composed_seconds=0.)
        mesh=levels['mesh'];space=levels['spaces'][4];tags=levels['mesh_data'].cell_tags
        if mesh.comm.size!=1:raise ValueError('bubble component is MPI1 only')
        e4,e2=_n1e(4),_n1e(2)
        if any(levels['spaces'][p].element.basix_element.hash()!=e.hash() for p,e in ((4,e4),(2,e2))):
            raise ValueError('actual FFCx/transfer element identity differs')
        quadrature=actions['volume_quadrature_metadata']
        compiled=compile_physical_diagnostic_volume(levels,cfg,4,volume_quadrature_metadata=quadrature)
        kernels=_cell_integral_kernels(compiled)
        mesh.topology.create_entity_permutations();infos=mesh.topology.get_cell_permutation_info()
        cell_tags=dict(zip(tags.indices.tolist(),tags.values.tolist()))
        material={cfg.tags.air:cfg.eps_r,cfg.tags.substrate:cfg.substrate_index**2,cfg.tags.grating:cfg.grating_index**2}
        P0=basix.compute_interpolation_operator(e2,e4).astype(complex)
        R0=basix.compute_interpolation_operator(e4,e2).astype(complex)
        ncell=mesh.topology.index_map(mesh.topology.dim).size_local
        if quadrature[0]!=quadrature[1] or quadrature[0]['quadrature_rule']!='default':
            raise ValueError('factory requires frozen common default quadrature')
        factory=AffineIsotropicMaxwellTensorFactory(e4,AffineIsotropicMaxwellTensorSpec(
            curl_coefficient=1/complex(cfg.mu_r),mass_coefficient_by_tag={int(t):-cfg.k0**2*complex(e) for t,e in material.items()},
            quadrature_degree=quadrature[0]['quadrature_degree']))
        orientations={}
        # Exact affine J, not absolute origin: translation does not alter a
        # constant-coefficient cell integral. Never round/merge nearby J values.
        for cell in range(ncell):
            sample();xyz=np.asarray(mesh.geometry.x[mesh.geometry.dofmap[cell]],float)
            tag=int(cell_tags[cell]);info=int(infos[cell]);eps=complex(material[tag])
            widths=xyz.max(axis=0)-xyz.min(axis=0)
            J=np.column_stack([xyz[1]-xyz[0],xyz[2]-xyz[0],xyz[4]-xyz[0]])
            if not np.allclose(J,np.diag(widths),rtol=0,atol=1e-12) or np.any(widths<=0):
                raise ValueError('actual cell is not positive axis-aligned affine')
            key=dict(J=[v.hex() for v in J.ravel()],widths=[v.hex() for v in widths],tag=tag,eps=[eps.real.hex(),eps.imag.hex()],
                mu=[complex(cfg.mu_r).real.hex(),complex(cfg.mu_r).imag.hex()],k0=float(cfg.k0).hex(),
                quadrature=quadrature,orientation=info,element_hashes=[int(e4.hash()),int(e2.hash())])
            digest=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()
            self.cells[cell]=digest
            if digest in self.classes:continue
            prefix=f'bubble_class_{len(self.classes):03d}'
            save(prefix+'_identity',dict(cell=cell,key=key,sha256=digest))
            if info not in orientations:
                tf,tc=_dof_transform(e4,info),_dof_transform(e2,info)
                if max(np.linalg.norm(tf.T@tf-np.eye(300)),np.linalg.norm(tc.T@tc-np.eye(54)))>1e-12:
                    raise ValueError('nonorthogonal actual orientation')
                P=tf@P0@tc.T;R=tc@R0@tf.T
                basis=fixed_bubble_basis(P,R,e4.entity_dofs[3][0])
                trace=trace_checks(e4,tf.T@basis[0],tf.T@P,widths)
                save(f'bubble_orientation_{info}',dict(P=P,R=R,Q=basis[0],basis=basis[1],trace_Q=trace))
                if max(trace.values())>1e-12:raise ValueError('orientation bubble basis trace failed')
                orientations[info]=(tf,P,R,basis)
            tf,P,R,basis=orientations[info]
            raw=_tabulate_raw_tensor_class(compiled,kernels,np.ascontiguousarray(xyz.ravel()),tag=tag,dimension=300)
            gram=factory.tensor(tag=tag,widths=tuple(widths))
            tensor_error=float(np.linalg.norm(raw-gram)/max(np.linalg.norm(raw),np.finfo(float).tiny))
            save(prefix+'_tensor_bridge',dict(FFCx_A=raw,Gram_A=gram,relative=tensor_error,limit=1e-10,
                actual_cell=cell,coordinates=xyz))
            if not np.isfinite(tensor_error) or tensor_error>1e-10:raise ValueError('class FFCx/Gram tensor gate failed')
            A=tf@gram@tf.T
            result=harmonic_bubble_check(A,P,R,e4.entity_dofs[3][0],basis_cache=basis,
                save=lambda n,f:save(prefix+'_'+n,f),sample=sample)
            boundary=float(np.linalg.norm((result['W']-P)[:192])/np.linalg.norm(P))
            save(prefix+'_trace',dict(boundary_dof=boundary,orientation_Q_trace_qualified=True))
            if not np.isfinite(boundary) or boundary>1e-12:raise ValueError('cell boundary coefficients changed')
            W=result['W'];delta=result['S']-P.conj().T@A@P
            W.setflags(write=False);delta.setflags(write=False)
            self.classes[digest]=dict(W=W,delta=delta,cell_info=info)
            save(prefix+'_retained',dict(W=W,delta=delta,bytes=W.nbytes+delta.nbytes))
            del result,A,raw,gram
            marker('bubble_class_complete',dict(cell=cell,sha256=digest,classes=len(self.classes)))
        orientation_count=len(orientations)
        del orientations,factory,compiled,kernels,tf,P,R,basis
        self.retained_bytes=sum(v['W'].nbytes+v['delta'].nbytes for v in self.classes.values())
        # Account small owner metadata/temporary local expansion with a visible
        # policy reserve, separately from exact numerical-cache bytes.
        self.retained_bytes+=4*1024**2
        save('bubble_classes_complete',dict(cells=ncell,classes=len(self.classes),
            orientation_count=orientation_count,retained_budget_bytes=self.retained_bytes,metadata_workspace_reserve_bytes=4*1024**2,
            reserve_scope="derived policy, not allocator bound; parent RSS authoritative",
            p4_global_matrix=0,local_LU_retained=0,full_A_retained=0,retained_p2_bubble=6))
        def provider(cell,info,base):
            item=self.classes[self.cells[cell]]
            if item['cell_info']!=info:raise ValueError('owner cell orientation differs')
            if np.linalg.norm((item['W']-base)[:192])>1e-12*np.linalg.norm(base):
                raise ValueError('owner trace rows differ from original P42')
            return item['W']
        self.owner=SameMeshHcurlOwnerTransfer(space,levels['floquets'][4],levels['spaces'][2],levels['floquets'][2],
            build_same_mesh_hcurl_transfer(4,2),cell_matrix_provider=provider)
        self.transfer=AlgebraicOwnerTransfer(self.owner)
        save('bubble_owner_storage',dict(base_polynomial_cache=dict(self.owner.audit),
            new_W_classes=len(self.classes),new_W_bytes=sum(v['W'].nbytes for v in self.classes.values()),
            delta_S_bytes=sum(v['delta'].nbytes for v in self.classes.values()),
            old_polynomial_derham_qualification_applies_to_W=False))

    def insert_volume(self,volume,space,mpc):
        from petsc4py import PETSc
        from .fullspace_same_mesh_hcurl_pmg_p6 import _cell_expansion_workspace,_fill_cell_expansion
        imap=mpc.function_space.dofmap.index_map
        storage=imap.size_local+imap.num_ghosts
        _,mask,targets,coefficients=_cell_expansion_workspace(mpc,storage,54)
        before=int(volume.getInfo()['nz_allocated'])
        for cell,digest in self.cells.items():
            self.sample();dofs=space.dofmap.cell_dofs(cell)
            _fill_cell_expansion(dofs,mpc,storage,mask,targets,coefficients)
            local,delta=constrained_cell_correction(self.classes[digest]['delta'],targets,coefficients)
            global_rows=imap.local_to_global(local.astype(np.int32)).astype(PETSc.IntType)
            volume.setValues(global_rows,global_rows,delta,addv=PETSc.InsertMode.ADD_VALUES)
        volume.assemble()
        self.save('bubble_cell_insertion',dict(cells=len(self.cells),allocated_before=before,
            allocated_after=int(volume.getInfo()['nz_allocated']),MPC='existing links E^H delta E',new_pattern=False))

    def qualify_matrix(self,matrix):
        from .fullspace_physical_intermediate_runtime import level_vector
        from .fullspace_physical_intermediate import apply_owned
        rng=np.random.default_rng(384)
        q=level_vector(self.levels,2);z=level_vector(self.levels,4)
        w=dual=composed=aug=image=None
        try:
            for v,slaves in ((q,self.transfer.coarse_slaves),(z,self.transfer.fine_slaves)):
                v.array[:]=rng.normal(size=v.getLocalSize())+1j*rng.normal(size=v.getLocalSize())
                v.array[slaves]=0
            w=self.transfer.apply_primal(q);dual=self.transfer.apply_adjoint(z)
            left=w.dot(z);right=q.dot(dual)
            dot_error=float(abs(left-right)/max(abs(left)+abs(right),np.finfo(float).tiny))
            self.save('bubble_global_adjoint',dict(left=left,right=right,relative=dot_error,limit=1e-11,
                owner=dict(self.owner.audit),primal_facts=self.owner.last_apply_facts))
            if not np.isfinite(dot_error) or dot_error>1e-11:raise ValueError('global W/WH adjoint gate failed')
            composed=apply_owned(self,q)
            aug=matrix.createVecRight();image=aug.duplicate();aug.set(0);n=q.getLocalSize()
            aug.array[:n]=q.array
            for j,item in enumerate(self.carrier.entries):
                aug.array[n+j]=np.dot(item.projection_values,q.array[item.projection_rows])/item.normalization_h
            matrix.mult(aug,image)
            error=float(np.linalg.norm(image.array[:n]-composed.array)/max(composed.norm(),np.finfo(float).tiny))
            port=float(np.linalg.norm(image.array[n:])/max(composed.norm(),np.finfo(float).tiny))
            self.save('bubble_S_assembly_identity',dict(q=q.array.copy(),assembled=image.array.copy(),
                composed=composed.array.copy(),relative=error,port_relative=port,limit=1e-10,port_rows=len(self.carrier.entries),
                composed_costs=dict(self.counts),cost_role='setup qualifier included in total composed calls and parent budget'))
            if not np.isfinite(error+port) or max(error,port)>1e-10:raise ValueError('assembled S versus WH A4 W failed')
        finally:
            for v in (q,z,w,dual,composed,aug,image):
                if v is not None:v.destroy()

    def apply_into(self,source,target):
        from .fullspace_physical_intermediate import apply_owned
        self.sample();self.counts['composed_started']+=1;start=time.perf_counter()
        w=a=q=None
        try:
            w=self.transfer.apply_primal(source);a=apply_owned(self.action,w)
            q=self.transfer.apply_adjoint(a);q.copy(target)
            self.counts['composed_completed']+=1
        finally:
            self.counts['composed_seconds']+=time.perf_counter()-start
            for value in (w,a,q):
                if value is not None:value.destroy()

    def destroy(self):
        if self.owner is not None:self.owner.destroy();self.owner=None
        self.classes.clear();self.cells.clear()
