"""Fixed low tangential trace with all ambient cell interiors retained.

Restriction uses the Hermitian dual. Ambient residuals are deliberately
preserved: a restricted Galerkin solution need not solve the ambient space.
"""
import numpy as np
from scipy import sparse
from .scattering_anchor import relative, save_arrays


def dense_restricted_witness(seed=5906):
    """Non-Hermitian, nonzero interior/40-port load and complex trace lift."""
    rng=np.random.default_rng(seed); ni,nt,nl,np_=5,7,4,40
    n=ni+nt+np_;A=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+25*np.eye(n)
    b=rng.normal(size=n)+1j*rng.normal(size=n)
    R=rng.normal(size=(nt,nl))+1j*rng.normal(size=(nt,nl))
    J=sparse.block_diag((np.eye(ni),R,np.eye(np_))).toarray()
    x=np.linalg.solve(J.conj().T@A@J,J.conj().T@b);full=J@x
    ii=A[:ni,:ni];it=A[:ni,ni:];ti=A[ni:,:ni]
    S=A[ni:,ni:]-ti@np.linalg.solve(ii,it);f=b[ni:]-ti@np.linalg.solve(ii,b[:ni])
    Q=sparse.block_diag((R,np.eye(np_))).toarray()
    z=np.linalg.solve(Q.conj().T@S@Q,Q.conj().T@f)
    rec=np.r_[np.linalg.solve(ii,b[:ni]-it@(Q@z)),Q@z]
    # Changing the internal lift while retaining the complete internal space
    # is only a coordinate change, not a different restriction of that space.
    L=J.copy();L[:ni,ni:ni+nl]=rng.normal(size=(ni,nl))+1j*rng.normal(size=(ni,nl))
    lifted=L@np.linalg.solve(L.conj().T@A@L,L.conj().T@b)
    ambient=b-A@full;mixed=J.conj().T@ambient
    wrong=Q.T@S@Q
    return dict(recovery=relative(rec-full,full),lift_invariance=relative(lifted-full,full),
        mixed=relative(mixed,J.conj().T@b),ambient=relative(ambient,b),
        transpose_counterexample=relative(wrong-Q.conj().T@S@Q,Q.conj().T@S@Q),
        nonzero_internal_rhs=bool(np.linalg.norm(b[:ni])>0),nonzero_40port_rhs=bool(np.linalg.norm(b[-np_:])>0),
        non_mutual_C_D=True,NOT_A_FULL_AMBIENT_SOLUTION=True)


def trace_constraints(floquet):
    from .hcurl_assembly_time_condensation import _owned_trace_numbering,_trace_constraint_map
    V=floquet.mpc.function_space;ip=np.asarray(V.element.basix_element.entity_dofs[3][0],int)
    cells=V.mesh.topology.index_map(3).size_local
    inside=tuple(V.dofmap.cell_dofs(c)[ip].copy() for c in range(cells))
    rows,numbering,nt,_=_owned_trace_numbering(V,inside)
    return _trace_constraint_map(V,rows,numbering,nt,floquet.mpc)


class TraceRestriction:
    """Unique-row sparse interpolation including native orientation and MPC."""
    def __init__(self,low,high,*,low_constraints=None,high_constraints=None):
        from .phase_p_order_consistency import interpolation_operator
        self.low,self.high=low,high
        self.low_constraints=trace_constraints(low) if low_constraints is None else low_constraints
        self.high_constraints=trace_constraints(high) if high_constraints is None else high_constraints
        a,b=low.mpc.function_space,high.mpc.function_space
        if a.mesh is not b.mesh:raise ValueError('trace restriction requires one actual shared mesh')
        if a.mesh.comm.size!=1:raise ValueError('finite restricted factor MPI1 only')
        a.mesh.topology.create_entity_permutations();perms=a.mesh.topology.get_cell_permutation_info()
        I=interpolation_operator(a.element.basix_element,b.element.basix_element)
        ai=np.asarray(a.element.basix_element.entity_dofs[3][0],int);bi=np.asarray(b.element.basix_element.entity_dofs[3][0],int)
        self.at=np.setdiff1d(np.arange(a.element.space_dimension),ai)
        self.bt=np.setdiff1d(np.arange(b.element.space_dimension),bi)
        self.local={};self.rows=[];owner={};rr=[];cc=[];vv=[]
        hids={int(r):i for i,r in enumerate(self.high_constraints.owned_active_original_dofs)}
        for c,p in enumerate(perms):
            if int(p) not in self.local:
                Ts=[]
                for V in (a,b):
                    T=np.eye(V.element.space_dimension);V.element.T_apply(T.ravel(),perms[c:c+1],len(T))
                    if relative(T@T.T-np.eye(len(T)),np.eye(len(T)))>1e-12:raise ValueError('trace DOF transform inverse not qualified')
                    Ts.append(T)
                M=Ts[1]@I@Ts[0].T
                # Entity-defined trace selection, no numerical clipping.
                self.local[int(p)]=M[np.ix_(self.bt,self.at)]
                defect=np.linalg.norm(M[np.ix_(self.bt,ai)])
                if defect>1e-10*max(np.linalg.norm(M),1.):raise ValueError('low interior has nonzero high tangential trace')
            ar=a.dofmap.cell_dofs(c)[self.at];br=b.dofmap.cell_dofs(c)[self.bt]
            self.rows.append((ar.copy(),br.copy(),int(p)))
            M=self.local[int(p)]
            for j,h in enumerate(br):
                h=int(h)
                if h not in hids or h in owner:continue
                owner[h]=c;hid=hids[h]
                for col,l in enumerate(ar):
                    value=M[j,col]
                    if value==0:continue
                    ids,co=self.low_constraints.expansion_by_original[int(l)]
                    rr.extend([hid]*len(ids));cc.extend(map(int,ids));vv.extend(value*co)
        if set(owner)!=set(hids):raise ValueError('canonical high trace owner missing')
        self.R=sparse.coo_matrix((np.asarray(vv,complex),(rr,cc)),shape=(self.high_constraints.active_rows,self.low_constraints.active_rows)).tocsr()
        self.R.sum_duplicates();self.R.sort_indices()
        self.internal_rows=np.concatenate([b.dofmap.cell_dofs(c)[bi] for c in range(len(perms))])
        self.high_native_rows=np.asarray(self.high_constraints.owned_active_original_dofs,int)
        self.low_native_rows=np.asarray(self.low_constraints.owned_active_original_dofs,int)
        self.owner=np.asarray([owner[int(r)] for r in self.high_native_rows],int)
        self.nhigh=b.dofmap.index_map.size_local

    def pull_native(self,v):
        v=np.asarray(v)
        return np.r_[v[self.internal_rows],self.R.conj().T@v[self.high_native_rows]]

    def lift_trace(self,t):return self.R@np.asarray(t)

    def qualification(self,seed=5907):
        from .phase_p_order_consistency import interpolation_operator
        rng=np.random.default_rng(seed);t=rng.normal(size=self.R.shape[1])+1j*rng.normal(size=self.R.shape[1]);h=self.R@t
        shared=[]
        for ar,br,p in self.rows:
            src=np.array([np.dot(co,t[ids]) for r in ar for ids,co in [self.low_constraints.expansion_by_original[int(r)]]])
            ref=np.array([np.dot(co,h[ids]) for r in br for ids,co in [self.high_constraints.expansion_by_original[int(r)]]])
            shared.append(relative(self.local[p]@src-ref,ref))
        y=rng.normal(size=len(h))+1j*rng.normal(size=len(h));dual=abs(np.vdot(y,h)-np.vdot(self.R.conj().T@y,t))/max(np.linalg.norm(y)*np.linalg.norm(h),1e-30)
        # Face tangential values, rather than just an algebraic map pairing.
        # Ambient interior coefficients are zero here only because this is
        # a trace witness; their physical interior values are not compared.
        a=self.low.mpc.function_space;b=self.high.mpc.function_space
        trace_checks=[];rank_checks=[];seen=set()
        for c,(_,_,p) in enumerate(self.rows):
            if p in seen:continue
            seen.add(p);Ts=[]
            for V in (a,b):
                T=np.eye(V.element.space_dimension)
                V.element.T_apply(T.ravel(),np.asarray([p],np.uint32),len(T));Ts.append(T)
            xyz=a.mesh.geometry.x[a.mesh.geometry.dofmap[c]]
            import basix
            affine=np.linalg.lstsq(np.column_stack((basix.cell.geometry(basix.CellType.hexahedron),np.ones(8))),xyz,rcond=None)[0]
            inv=np.linalg.inv(affine[:3].T)
            source=rng.normal(size=len(self.at))+1j*rng.normal(size=len(self.at))
            ca=np.zeros(a.element.space_dimension,complex);ca[self.at]=source
            cb=np.zeros(b.element.space_dimension,complex);cb[self.bt]=self.local[p]@source
            ca=Ts[0].T@ca;cb=Ts[1].T@cb
            for axis in range(3):
                for side in (0.,1.):
                    pts=np.empty((9,3));pts[:,axis]=side
                    pts[:,[d for d in range(3) if d!=axis]]=np.stack(np.meshgrid([.19,.5,.81],[.19,.5,.81],indexing='ij'),axis=-1).reshape(9,2)
                    ea=np.einsum('qjc,j->qc',a.element.basix_element.tabulate(0,pts)[0],ca)@inv
                    eb=np.einsum('qjc,j->qc',b.element.basix_element.tabulate(0,pts)[0],cb)@inv
                    normal=inv.T[:,axis];normal/=np.linalg.norm(normal)
                    trace_checks.append(relative(np.cross(normal,ea-eb),np.cross(normal,ea)))
            # One complete edge and face, never a global spectrum or rank scan.
            M=Ts[1]@interpolation_operator(a.element.basix_element,b.element.basix_element)@Ts[0].T
            for dim in (1,2):
                lo=a.element.basix_element.entity_dofs[dim][0];hi=b.element.basix_element.entity_dofs[dim][0]
                values=np.linalg.svd(M[np.ix_(hi,lo)],compute_uv=False)
                rcond=float(values[-1]/values[0]);threshold=np.finfo(float).eps*max(len(hi),len(lo))
                rank_checks.append(dict(permutation=p,entity_dimension=dim,columns=len(lo),rcond=rcond,threshold=threshold,full_column_rank=rcond>threshold))
        return dict(shared_operation_max=max(shared),dual_operation=float(dual),tangential_field_operation_max=max(trace_checks),local_entity_rank=rank_checks,nnz=int(self.R.nnz),shape=list(self.R.shape),
            csr_bytes=sum(v.nbytes for v in (self.R.data,self.R.indices,self.R.indptr)),
            pass_gate=max(shared)<=1e-10 and dual<=1e-12 and max(trace_checks)<=1e-10 and all(x['full_column_rank'] for x in rank_checks),unique_owner=True,numerical_clipping=False)

    def save(self,path):
        return save_arrays(path,R_indptr=self.R.indptr,R_indices=self.R.indices,R_data=self.R.data,R_shape=np.asarray(self.R.shape),
            high_native_rows=self.high_native_rows,low_native_rows=self.low_native_rows,internal_rows=self.internal_rows,owner=self.owner)


def sparse_projection(matrix,R,ports,journal):
    """Explicit P^H A P through sparse products; PETSc PtAP is not used."""
    from petsc4py import PETSc
    Q=sparse.block_diag((R,sparse.eye(ports,format='csr',dtype=complex)),format='csr')
    P=PETSc.Mat().createAIJ(size=Q.shape,csr=(Q.indptr.astype(PETSc.IntType),Q.indices.astype(PETSc.IntType),Q.data),comm=PETSc.COMM_SELF)
    H=PETSc.Mat();P.hermitianTranspose(H);mid=small=None
    try:
        with journal.measured('high_schur_sparse_hermitian_trace_projection'):
            mid=matrix.matMult(P);small=H.matMult(mid)
        journal.event('sparse_projection_inventory',high_shape=matrix.getSize(),high_nnz=int(matrix.getInfo()['nz_used']),
            intermediate_shape=mid.getSize(),intermediate_nnz=int(mid.getInfo()['nz_used']),low_shape=small.getSize(),low_nnz=int(small.getInfo()['nz_used']),
            Q_nnz=int(Q.nnz),Q_payload_bytes=Q.data.nbytes+Q.indices.nbytes+Q.indptr.nbytes,conjugate_dual=True,MatPtAP_used=False)
        return small
    except BaseException:
        if small is not None:small.destroy()
        raise
    finally:
        if mid is not None:mid.destroy()
        H.destroy();P.destroy()


def projection_pattern_envelope(Rmap,ports):
    """Count conservative cell support before a sparse triple product.

    Trace interpolation has tiny stored entries outside the ideal entity
    pattern. All stored entries count; a p6 stencil cannot bound this graph.
    Body blocks connect only the canonical high traces of their source cell.
    Ports are conservatively allowed to couple every trace and one another.
    """
    high,low=Rmap.R.shape;largest=0
    # Temporary integer incidence unions, no floating operator/projection.
    # At most (high+low)*ceil(low/8) bytes, released before sparse products.
    high_incidence=[0]*high;low_incidence=[0]*low
    for _,br,_ in Rmap.rows:
        ids=np.unique(np.concatenate([Rmap.high_constraints.expansion_by_original[int(r)][0] for r in br]))
        columns=np.unique(Rmap.R[ids].indices);n=len(columns)
        bits=sum(1<<int(c) for c in columns)
        for row in ids:high_incidence[int(row)]|=bits
        for row in columns:low_incidence[int(row)]|=bits
        largest=max(largest,n)
    mid=sum(x.bit_count() for x in high_incidence)
    small=sum(x.bit_count() for x in low_incidence)
    mid=min((high+ports)*(low+ports),mid+ports*(high+low)+ports*ports)
    small=min((low+ports)**2,small+2*ports*low+ports*ports)
    mapping_bytes=sum(x.nbytes for x in (Rmap.R.data,Rmap.R.indices,Rmap.R.indptr))
    # Existing high Schur is already in live RSS. Allow two copies of each
    # new product, and four mapping payloads (SciPy/PETSc primal and dual).
    workspace=2*(mid+small)*24+4*mapping_bytes
    return dict(intermediate_nnz_upper=int(mid),low_nnz_upper=int(small),
        cell_low_support_max=int(largest),all_stored_interpolation_entries_counted=True,
        index64_complex128_entry_bytes=24,product_payload_copies=2,mapping_payload_copies=4,
        workspace_bytes=int(workspace),pattern_workspace_upper_bytes=(high+low)*((low+7)//8+32),
        high_existing_in_live_RSS=True,
        no_numerical_clipping=True,no_dense_numeric_projection=True,
        bounded_integer_incidence_storage=True)


class RestrictedTraceFactor:
    """Restricted solve adapter; returns ambient trace for original recovery."""
    def __init__(self,R,ports,factor):
        self.R,self.ports,self.factor=R,ports,factor
        self.last_low_solution=None;self.last_low_rhs=None

    def solve_repeated(self,rhs,target):
        from petsc4py import PETSc
        h=self.R.shape[0];l=self.R.shape[1]
        f=np.r_[self.R.conj().T@rhs.array[:h],rhs.array[h:]]
        v=PETSc.Vec().createSeq(l+self.ports,comm=PETSc.COMM_SELF);x=v.duplicate();v.array[:]=f
        try:
            self.factor.solve_repeated(v,x)
            self.last_low_solution=x.array.copy();self.last_low_rhs=f.copy()
            target.array[:]=np.r_[self.R@x.array[:l],x.array[l:]]
        finally:v.destroy();x.destroy()

    def destroy(self):self.factor.destroy()


def mixed_norms(ambient,rhs,Rmap):
    """Pull all included weak rows, retaining the ambient defect separately."""
    den=max(np.linalg.norm(Rmap.pull_native(rhs)),1e-30)
    residual=Rmap.pull_native(ambient['residual']);top=Rmap.pull_native(ambient['augmented_residual'])
    pr=ambient['port_residual'];port_den=max(np.linalg.norm(ambient['projected']),1e-30)
    return dict(true=float(np.linalg.norm(residual)/den),native=float(np.linalg.norm(residual)/den),
        augmented=float(np.linalg.norm(top)/den),port=float(np.linalg.norm(pr)/port_den),mixed_rhs_norm=float(den),
        ambient_relative=float(np.linalg.norm(ambient['residual'])/max(np.linalg.norm(rhs),1e-30)),
        ambient_internal_norm=float(np.linalg.norm(ambient['residual'][Rmap.internal_rows])),
        ambient_trace_norm=float(np.linalg.norm(ambient['residual'][Rmap.high_native_rows])),
        NOT_A_FULL_AMBIENT_SOLUTION=True)
