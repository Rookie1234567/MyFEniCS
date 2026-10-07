"""Canonical shared-face enrichment of the V60 micro field mapping.

The internal space and old macro interpolation are unchanged. Each new
coefficient belongs to one periodic canonical face, never to a cell copy.
"""
from dataclasses import replace
import numpy as np
from scipy import sparse
from .subcell_macro_deployment import MacroMap
from .subcell_response_kernel import transform
from .trace_interior_restriction import trace_constraints
from .face_trace_basis import face_rows,physical_gram,mass_complement,signature
from .scattering_anchor import save_arrays,relative
from src.runners.task042_shared import write_json


class FaceEnrichedMap(MacroMap):
    def __init__(self,low,high,coarse_geometry,fine_geometry,journal,*,axes,folder=None):
        axes=tuple(axes)
        if axes not in ((0,),(0,1)):raise ValueError('fixed FX/FXY axes only')
        super().__init__(low,high,coarse_geometry,fine_geometry,journal)
        oldcheck=dict(self.check);self.original_layouts=self.layouts
        del self.J,self.JH
        V=low.mpc.function_space;W=high.mpc.function_space;hc=trace_constraints(high)
        import basix
        ref=basix.cell.geometry(basix.CellType.hexahedron);top=basix.cell.topology(basix.CellType.hexahedron)
        self.faces=[];self.face_index={};self.axes=axes;newlayouts=[];newdata=[];newT=[];paired=[];blocks={};grams={}
        el=V.element.basix_element;tt=np.setdiff1d(np.arange(el.dim),el.entity_dofs[3][0]);where={int(r):i for i,r in enumerate(tt)}
        for c,(layout,(ids,E,owner),Tp) in enumerate(zip(self.original_layouts,self.data,self.transforms,strict=True)):
            local=[];extra=[];bc={int(r):i for i,r in enumerate(layout.boundary)}
            original=sparse.csr_matrix(layout.lift)@Tp@E
            for axis in axes:
                for side in (0,1):
                    selected,childfaces=face_rows(W,layout,axis,side)
                    masters=[];co=[]
                    for r in layout.native_rows[selected]:
                        active,values=hc.expansion_by_original[int(r)]
                        if len(active)!=1 or len(values)!=1 or values[0]==0:raise ValueError('face row must have one nonzero canonical periodic representative')
                        masters.append(int(active[0]));co.append(complex(values[0]))
                    order=np.argsort(masters);selected=selected[order];masters=np.asarray(masters,int)[order];co=np.asarray(co)[order]
                    if len(np.unique(masters))!=264:raise ValueError('face canonical duplicate')
                    face=next(j for j,vs in enumerate(top[2]) if np.all(ref[vs,axis]==side))
                    rawrows=V.dofmap.cell_dofs(c)[el.entity_dofs[2][face]]
                    oldids=[]
                    for r in rawrows:
                        active,_=self.constraints.expansion_by_original[int(r)]
                        if len(active)!=1:raise ValueError('old face canonical representative')
                        oldids.append(int(active[0]))
                    oldids=np.asarray(sorted(oldids),int)
                    if len(np.unique(oldids))!=60:raise ValueError('old face 60-column inventory')
                    pos={int(r):j for j,r in enumerate(ids)}
                    Pf=original[[bc[int(r)] for r in selected]][:,[pos[int(i)] for i in oldids]].toarray()/co[:,None]
                    key=(axis,tuple(masters))
                    if key not in self.face_index:
                        # The Gram cache key includes the actual row ordering,
                        # geometry bits and orientation, not rounded classes.
                        gs=[]
                        for fc,lr,fe in childfaces:
                            xyz=W.mesh.geometry.x[W.mesh.geometry.dofmap[fc]]
                            gs.extend((xyz.max(axis=0)-xyz.min(axis=0),np.asarray([int(W.mesh.topology.get_cell_permutation_info()[fc]),fe]),
                                np.asarray([np.flatnonzero(selected==int(v))[0] if int(v) in selected else -1 for v in lr],int)))
                        gkey=signature(*gs,co)
                        if gkey not in grams:grams[gkey]=physical_gram(W,layout,axis,selected,childfaces,co)
                        G=grams[gkey];bkey=signature(Pf,G)
                        if bkey not in blocks:
                            Z,check=mass_complement(Pf,G);receipt=None
                            if folder is not None:
                                d=folder/'face_basis';d.mkdir(exist_ok=True)
                                receipt=save_arrays(d/(bkey+'.npz'),original=Pf,mass=G,complement=Z)
                            blocks[bkey]=(Z,check,receipt)
                        Z,check,receipt=blocks[bkey];index=len(self.faces);self.face_index[key]=index
                        self.faces.append(dict(index=index,axis=axis,master_micro_ids=masters,old_macro_ids=oldids,P=Pf,Z=Z,G=G,
                            area=float(np.prod((layout.bounds[1]-layout.bounds[0])[[a for a in range(3) if a!=axis]])),
                            owner_cell=c,owner_side=side,basis_hash=bkey,arrays=receipt,qualification=check))
                    f=self.faces[self.face_index[key]]
                    if not np.array_equal(f['old_macro_ids'],oldids):raise ValueError('shared/periodic old face identity')
                    paired.append(relative(Pf-f['P'],np.abs(Pf)+np.abs(f['P'])))
                    # Structural support is exactly the 264 internal face
                    # moments. Floquet coefficients are applied here once.
                    rows=np.asarray([bc[int(r)] for r in selected]);values=co[:,None]*f['Z']
                    lift=sparse.coo_matrix((values.ravel(),(np.repeat(rows,204),np.tile(np.arange(204),264))),shape=(1728,204)).tocsr()
                    local.append(lift);extra.append(32832+204*f['index']+np.arange(204))
            lift=sparse.hstack((sparse.csr_matrix(layout.lift),*local),format='csr')
            newlayouts.append(replace(layout,lift=lift,key=signature(np.frombuffer(layout.key.encode(),np.uint8),lift.data,lift.indices,lift.indptr)))
            newdata.append((np.r_[ids,*extra],sparse.block_diag((E,*[sparse.eye(204,format='csr') for _ in local]),format='csr'),owner))
            newT.append(sparse.block_diag((Tp,*[sparse.eye(204,format='csr') for _ in local]),format='csr'))
        self.layouts,self.data,self.transforms=newlayouts,newdata,newT
        self.nt=32832+204*len(self.faces);self.nmixed=self.ninternal+self.nt
        if len(self.faces)!=160*len(axes) or self.nt!=(65472 if axes==(0,) else 98112):raise ValueError('actual independent face/mixed inventory')
        self._build_mapping(journal)
        self.check.update(old_space=oldcheck,face_axes=list(axes),face_count=len(self.faces),face_micro=264,face_original=60,face_complement=204,
            basis_unique_blocks=len(blocks),mass_unique_blocks=len(grams),shared_periodic_face_operation=max(paired,default=0.),
            basis_max_operation=max(max(f['qualification'][k] for k in ('mass_cross_operation','mass_orthogonality','QR_reconstruction')) for f in self.faces),
            original_columns_retained=True,new_macro_local_columns=self.layouts[0].lift.shape[1],old_space_replayed=False)
        self.check['pass_gate']=self.check['pass_gate'] and max(paired,default=0.)<=1e-10
        if not self.check['pass_gate']:raise ValueError('face enriched canonical mapping not qualified')
        if folder is not None:
            arr=save_arrays(folder/'face_inventory.npz',axis=np.asarray([f['axis'] for f in self.faces]),owner_cell=np.asarray([f['owner_cell'] for f in self.faces]),
                owner_side=np.asarray([f['owner_side'] for f in self.faces]),canonical_micro_ids=np.asarray([f['master_micro_ids'] for f in self.faces]),
                old_macro_ids=np.asarray([f['old_macro_ids'] for f in self.faces]),area=np.asarray([f['area'] for f in self.faces]))
            self.face_receipt=dict(arrays=arr,bases={k:dict(arrays=v[2],qualification=v[1]) for k,v in blocks.items()},mapping_check=self.check)
            write_json(folder/'face_inventory.json',self.face_receipt)
        journal.event('face_enrichment_primal_dual_qualified',**self.check)

    def _build_mapping(self,journal):
        W=self.high.mpc.function_space;n=W.dofmap.index_map.size_local
        assigned=np.zeros(n,bool);assigned[self.slaves]=True;slave_set=set(map(int,self.slaves))
        rr=[];cc=[];vv=[];shared=[];offset=0;rng=np.random.default_rng(61024)
        t=rng.normal(size=self.nt)+1j*rng.normal(size=self.nt);known=np.zeros(n,complex)
        for layout,(ids,E,_),Tp in zip(self.layouts,self.data,self.transforms,strict=True):
            interior=np.setdiff1d(np.arange(len(layout.native_rows)),layout.boundary);ar=layout.native_rows[interior]
            if len(interior)!=4356 or assigned[ar].any():raise ValueError('new mapping internal owner changed')
            rr.append(ar);cc.append(offset+np.arange(len(ar)));vv.append(np.ones(len(ar),complex));assigned[ar]=True;offset+=len(ar)
            M=layout.lift@Tp@E;values=M@t[ids]
            for j,row in enumerate(layout.native_rows[layout.boundary]):
                if int(row) in slave_set:continue
                r=M.getrow(j)
                if assigned[row]:shared.append(abs(known[row]-values[j])/max(np.linalg.norm(r.data)*np.linalg.norm(t[ids]),1e-30));continue
                assigned[row]=True;known[row]=values[j];rr.append(np.full(len(r.indices),row,int));cc.append(self.ninternal+ids[r.indices]);vv.append(r.data.copy())
        if not assigned.all() or offset!=self.ninternal:raise ValueError('face J unique row coverage')
        self.J=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(n,self.nmixed)).tocsr();self.J.sum_duplicates();self.J.sort_indices()
        self.JH=self.J.conj().T.tocsr();y=rng.normal(size=n)+1j*rng.normal(size=n);x=rng.normal(size=self.nmixed)+1j*rng.normal(size=self.nmixed)
        dual=abs(np.vdot(y,self.J@x)-np.vdot(self.JH@y,x))/max(np.linalg.norm(y)*np.linalg.norm(self.J@x),1e-30)
        self.check=dict(shared_operation_max=max(shared,default=0.),dual_operation=float(dual),shape=list(self.J.shape),nnz=self.J.nnz,
            mixed_FE=self.nmixed,ambient_FE=n-len(self.slaves),internal=self.ninternal,trace=self.nt,
            csr_primal_dual_bytes=sum(a.nbytes for m in (self.J,self.JH) for a in (m.data,m.indices,m.indptr)),
            unique_owner=True,full_field_never_projected_to_macro=True,pass_gate=max(shared,default=0.)<=1e-10 and dual<=1e-12)

    def saved_face_defects(self,residual,folder,*,parent):
        r=self.pull_native(residual)[self.ninternal+32832:].reshape(len(self.faces),204)
        packet=save_arrays(folder/'saved_H2_face_defects.npz',complex_defects=r,absolute=np.linalg.norm(r,axis=1),
            area=np.asarray([f['area'] for f in self.faces]),axis=np.asarray([f['axis'] for f in self.faces]))
        return dict(arrays=packet,parent=parent,faces=len(self.faces),norm=float(np.linalg.norm(r)),
            mass_orthonormal_dual=True,global_shared_periodic_assembled_before_norm=True,NOT_A_FULL_HCURL_ERROR_BOUND=True)

    def pull_port(self,rows,values,*,dual=True):
        # Original carrier vectors have exact sparse z-boundary support.
        # Select their native rows first, avoiding repeated whole-map scans.
        sub=self.J[np.asarray(rows,int)]
        return (sub.conj().T if dual else sub.T)@np.asarray(values)

    def face_trace_witness(self):
        """Actual physical tangents for both selected and zero other faces."""
        import basix
        W=self.high.mpc.function_space;el=W.element.basix_element;ref=basix.cell.geometry(basix.CellType.hexahedron);top=basix.cell.topology(basix.CellType.hexahedron)
        rng=np.random.default_rng(61026);worst=0.;nonzero=0.;checked=0
        for layout in self.layouts[:2]:
            z=rng.normal(size=layout.lift.shape[1]-432)+1j*rng.normal(size=layout.lift.shape[1]-432)
            u=np.zeros(len(layout.native_rows),complex);u[layout.boundary]=layout.lift[:,432:]@z
            for c,rows in zip(layout.cells,layout.child_rows,strict=True):
                xyz=W.mesh.geometry.x[W.mesh.geometry.dofmap[c]];lo=xyz.min(axis=0);hi=xyz.max(axis=0);h=hi-lo;co=transform(W,int(c)).T@u[rows]
                for axis in range(3):
                    for side in (0,1):
                        if (lo[axis] if side==0 else hi[axis])!=(layout.bounds[0,axis] if side==0 else layout.bounds[1,axis]):continue
                        face=next(j for j,vs in enumerate(top[2]) if np.all(ref[vs,axis]==side));free=[j for j in range(3) if j!=axis]
                        pp=np.zeros((4,3));pp[:,axis]=side;pp[:,free[0]]=[.21,.21,.69,.69];pp[:,free[1]]=[.27,.71,.27,.71]
                        b=el.tabulate(0,pp)[0]/h;val=np.einsum('qjc,j->qc',b,co)[:,free]
                        if axis not in self.axes:worst=max(worst,float(np.linalg.norm(val)/max(np.linalg.norm(np.abs(b[:,:,free]))*np.linalg.norm(co),1e-30)))
                        else:nonzero=max(nonzero,float(np.linalg.norm(val)))
                        # DOFs on the macro perimeter must be structurally
                        # zero; tangential point values on edge are independent.
                        for other in free:
                            for v in (0,1):
                                plane=lo[other] if v==0 else hi[other]
                                if plane not in layout.bounds[:,other]:continue
                                edgepp=pp.copy();edgepp[:,other]=v;direction=next(j for j in free if j!=other)
                                ev=np.einsum('qjc,j->qc',el.tabulate(0,edgepp)[0]/h,co)[:,direction]
                                worst=max(worst,float(np.linalg.norm(ev)/max(np.linalg.norm(el.tabulate(0,edgepp)[0]/h)*np.linalg.norm(co),1e-30)));checked+=1
        return dict(z_and_other_unreleased_tangential_operation=worst,nonzero_selected_face=nonzero,perimeter_witnesses=checked,
            pass_gate=worst<=1e-10 and nonzero>1e-8)
