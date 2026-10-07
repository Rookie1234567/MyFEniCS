"""Two-level local H(curl) response; no global micro-interface matrix.

Child and macro-interior solves keep the original affine particular load.
Only the r2 response has 432 input columns. The r4 diagnostic solves two
vectors and never constructs a boundary response library.
"""
from dataclasses import dataclass
import hashlib
import numpy as np
from scipy import sparse
from scipy.linalg import lu_factor,lu_solve
from scipy.linalg.lapack import get_lapack_funcs
from .scattering_anchor import relative,save_arrays,array_hash
from .hcurl_affine_phase_tensor import axis_widths


def transform(V,c):
    p=V.mesh.topology.get_cell_permutation_info()[c:c+1]
    T=np.eye(V.element.space_dimension);V.element.T_apply(T.ravel(),p,len(T))
    return T


def child_interpolation(element,offset,scale,rows=None):
    """Covariant pullback from a parent reference hex to an affine child."""
    points=np.asarray(offset)+element.points*np.asarray(scale)
    values=element.tabulate(0,points)[0]*np.asarray(scale)[None,None,:]
    matrix=element.interpolation_matrix if rows is None else element.interpolation_matrix[np.asarray(rows)]
    return sparse.csr_matrix(matrix)@np.ascontiguousarray(values.transpose(2,0,1)).reshape(-1,element.dim)


def parent_entity_mask(element,lo,hi,macro_lo,macro_hi):
    """Support follows macro-face/edge closure, never a floating drop."""
    import basix
    ref=basix.cell.geometry(basix.CellType.hexahedron);top=basix.cell.topology(basix.CellType.hexahedron)
    vertices=lo+ref*(hi-lo);mask=np.ones((element.dim,element.dim),bool)
    for d in (1,2):
        for entity,rows in enumerate(element.entity_dofs[d]):
            coords=vertices[top[d][entity]]
            sides=[(a,v) for a in range(3) for v in (0.,1.) if np.all(coords[:,a]==(macro_lo[a] if v==0 else macro_hi[a]))]
            if not sides:continue
            allowed=set(range(element.dim))
            for a,v in sides:
                f=next(j for j,vs in enumerate(top[2]) if np.all(ref[vs,a]==v))
                allowed.intersection_update(element.entity_closure_dofs[2][f])
            mask[rows,:]=False;mask[np.ix_(rows,sorted(allowed))]=True
    return mask


def physical_trace_witness(V,c,needed,M,witness,bounds):
    """Independent physical tangential values, not an interpolation dot test."""
    el=V.element.basix_element;xyz=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]]
    a,z=xyz.min(axis=0),xyz.max(axis=0);lo,hi=np.asarray(bounds);h=z-a;mh=hi-lo
    tt=np.setdiff1d(np.arange(el.dim),el.entity_dofs[3][0]);parent=np.zeros(el.dim,complex);parent[tt]=witness
    native=np.zeros(el.dim,complex);native[needed]=M@witness;co=transform(V,int(c)).T@native
    maximum=0.
    for axis in range(3):
        for side in (0.,1.):
            if (a[axis] if side==0 else z[axis])!=(lo[axis] if side==0 else hi[axis]):continue
            free=[j for j in range(3) if j!=axis];pp=np.zeros((4,3));pp[:,axis]=side
            pp[:,free[0]]=[.23,.23,.71,.71];pp[:,free[1]]=[.29,.73,.29,.73]
            points=a+pp*h;reference=(points-lo)/mh
            child=np.einsum('qjc,j->qc',el.tabulate(0,pp)[0],co)/h
            old=np.einsum('qjc,j->qc',el.tabulate(0,reference)[0],parent)/mh
            normal=np.eye(3)[axis];delta=np.cross(child-old,normal);scale=np.linalg.norm(np.cross(old,normal))+np.linalg.norm(np.cross(child,normal))
            maximum=max(maximum,float(np.linalg.norm(delta)/max(scale,1e-30)))
    return maximum


@dataclass
class MacroLayout:
    cells: np.ndarray
    native_rows: np.ndarray
    child_rows: tuple
    trace: np.ndarray
    boundary: np.ndarray
    inside: np.ndarray
    child_interiors: tuple
    child_traces: tuple
    lift: np.ndarray
    structural_zero_operation: float
    shared_boundary_operation: float
    tangential_operation: float
    key: str
    bounds: np.ndarray

    @classmethod
    def build(cls,V,cells,bounds,*,interpolation_cache=None):
        import basix
        el=V.element.basix_element;ii=np.asarray(el.entity_dofs[3][0],int);tt=np.setdiff1d(np.arange(el.dim),ii)
        mesh=V.mesh;mesh.topology.create_entity_permutations();cells=np.asarray(cells,int)
        centers=np.array([mesh.geometry.x[mesh.geometry.dofmap[c]].mean(axis=0) for c in cells]);cells=cells[np.lexsort(centers.T[::-1])]
        ids={};native=[];maps=[]
        for c in cells:
            local=[]
            for row in V.dofmap.cell_dofs(c):
                if int(row) not in ids:ids[int(row)]=len(native);native.append(int(row))
                local.append(ids[int(row)])
            maps.append(np.asarray(local,int))
        child_i=tuple(x[ii] for x in maps);child_t=tuple(x[tt] for x in maps)
        trace=np.setdiff1d(np.arange(len(native)),np.concatenate(child_i))
        bset=set();ref=basix.cell.geometry(basix.CellType.hexahedron);top=basix.cell.topology(basix.CellType.hexahedron)
        lo,hi=np.asarray(bounds);parent_t=tt;
        interpolation_cache={} if interpolation_cache is None else interpolation_cache;owners={};lift_rows={};all_checks=[];zero=[];tangent=[];rng=np.random.default_rng(60021)
        witness=rng.normal(size=len(tt))+1j*rng.normal(size=len(tt));signature=[]
        for c,m in zip(cells,maps,strict=True):
            x=mesh.geometry.x[mesh.geometry.dofmap[c]];a=x.min(axis=0);z=x.max(axis=0)
            needed=set()
            for axis in range(3):
                for side in (0.,1.):
                    if (a[axis] if side==0 else z[axis])!=(lo[axis] if side==0 else hi[axis]):continue
                    face=next(j for j,vs in enumerate(top[2]) if np.all(ref[vs,axis]==side))
                    needed.update(el.entity_closure_dofs[2][face])
            needed=np.asarray(sorted(needed),int)
            if len(needed):
                offset=(a-lo)/(hi-lo);scale=(z-a)/(hi-lo);perm=int(mesh.topology.get_cell_permutation_info()[c])
                cachekey=(int(el.hash()),offset.tobytes(),scale.tobytes(),perm,needed.tobytes())
                if cachekey not in interpolation_cache:
                    T=sparse.csr_matrix(transform(V,int(c)))[needed];refrows=np.unique(T.indices)
                    I=child_interpolation(el,offset,scale,rows=refrows);mask=parent_entity_mask(el,a,z,lo,hi)[refrows]
                    zz=float(np.linalg.norm(I[~mask])/max(np.linalg.norm(I),1e-30));I=np.where(mask,I,0.)
                    M=(T[:,refrows]@I)[:,parent_t];M.setflags(write=False)
                    physical=physical_trace_witness(V,c,needed,M,witness,bounds)
                    interpolation_cache[cachekey]=(M,zz,physical)
                    if sum(pair[0].nbytes for pair in interpolation_cache.values())>2*2**30:raise MemoryError('exact child interpolation workspace exceeds 2GiB')
                M,zz,physical=interpolation_cache[cachekey];zero.append(zz);tangent.append(physical)
                for j,k in enumerate(needed):
                    row=int(m[k]);bset.add(row);values=M[j]
                    if row in owners:all_checks.append(abs((values-lift_rows[row])@witness)/max(np.linalg.norm(values)*np.linalg.norm(witness),1e-30))
                    else:owners[row]=int(c);lift_rows[row]=values.copy()
            signature.append(dict(widths=axis_widths(x).tolist(),offset=((a-lo)/(hi-lo)).tolist(),permutation=int(mesh.topology.get_cell_permutation_info()[c]),mapping=m.tolist()))
        boundary=np.asarray(sorted(bset),int);inside=np.setdiff1d(trace,boundary)
        if len(set(np.concatenate(child_i)))!=len(np.concatenate(child_i)):raise ValueError('child internal ownership')
        lift=np.array([lift_rows[int(i)] for i in boundary]);norm=max(zero,default=0.);shared=max(all_checks,default=0.)
        tan=max(tangent,default=0.)
        if max(norm,shared,tan)>1e-10:raise ValueError('macro boundary support/shared/physical tangential mismatch')
        # Full precision bit identities, not rounded geometry/material classes.
        key=hashlib.sha256(repr(signature).encode()+np.asarray(hi-lo).tobytes()).hexdigest()
        return cls(cells,np.asarray(native,int),tuple(maps),trace,boundary,inside,child_i,child_t,lift,norm,shared,tan,key,np.asarray(bounds))


class ChildBlock:
    @classmethod
    def from_checkpoint(cls,a,el):
        """Reuse a complete saved factor; no new LU or tensor construction."""
        obj=cls.__new__(cls);obj.ii=np.asarray(el.entity_dofs[3][0],int);obj.tt=np.setdiff1d(np.arange(el.dim),obj.ii)
        raw=a['raw'];obj.lu=(a['interior_factor'],a['interior_pivots']);obj.Ati=a['trace_from_interior'];obj.X=a['interior_from_trace'];obj.S=a['child_schur']
        sizes={'raw':(el.dim,el.dim),'interior_factor':(len(obj.ii),len(obj.ii)),'interior_pivots':(len(obj.ii),),
            'trace_from_interior':(len(obj.tt),len(obj.ii)),'interior_from_trace':(len(obj.ii),len(obj.tt)),'child_schur':(len(obj.tt),len(obj.tt))}
        if any(a[k].shape!=shape or not np.isfinite(a[k]).all() for k,shape in sizes.items()) or any(a[k].dtype!=np.complex128 for k in sizes if k!='interior_pivots'):raise ValueError('saved child complete factor inventory')
        obj.scale=float(np.linalg.norm(raw));Aii=raw[np.ix_(obj.ii,obj.ii)]
        w=np.linspace(1,2,len(obj.ii))+1j*np.linspace(.1,.9,len(obj.ii));sol=lu_solve(obj.lu,w);defect=Aii@sol-w
        obj.rhs_relative_error=relative(defect,w);obj.backward_error=float(np.linalg.norm(defect)/max(np.linalg.norm(Aii)*np.linalg.norm(sol)+np.linalg.norm(w),1e-30))
        obj.rcond1,info=get_lapack_funcs('gecon',(obj.lu[0],))(obj.lu[0],np.linalg.norm(Aii,1))
        if info or not np.isfinite(obj.rcond1) or obj.rcond1<=0 or obj.backward_error>1e-10:raise ValueError('saved child factor qualification')
        for value in (obj.lu[0],obj.lu[1],obj.Ati,obj.X,obj.S):value.setflags(write=False)
        obj.raw=None;return obj

    def __init__(self,A,el):
        self.ii=np.asarray(el.entity_dofs[3][0],int);self.tt=np.setdiff1d(np.arange(el.dim),self.ii)
        self.lu=lu_factor(A[np.ix_(self.ii,self.ii)])
        self.Ati=np.ascontiguousarray(A[np.ix_(self.tt,self.ii)])
        self.X=lu_solve(self.lu,-A[np.ix_(self.ii,self.tt)])
        self.S=np.ascontiguousarray(A[np.ix_(self.tt,self.tt)]+self.Ati@self.X)
        self.scale=float(np.linalg.norm(A));self.raw=A
        w=np.linspace(1,2,len(self.ii))+1j*np.linspace(.1,.9,len(self.ii))
        Aii=A[np.ix_(self.ii,self.ii)];sol=lu_solve(self.lu,w);defect=Aii@sol-w
        self.rhs_relative_error=relative(defect,w)
        back=float(np.linalg.norm(defect)/max(np.linalg.norm(Aii)*np.linalg.norm(sol)+np.linalg.norm(w),1e-30))
        self.rcond1,info=get_lapack_funcs('gecon',(self.lu[0],))(self.lu[0],np.linalg.norm(Aii,1))
        if info or not np.isfinite(self.rcond1) or self.rcond1<=0:raise ValueError('child LU finite/zero-pivot qualification')
        if not np.isfinite(back) or back>1e-10:raise ValueError('local child LU backward error')
        self.backward_error=back
    def bytes(self):return sum(a.nbytes for a in (self.lu[0],self.lu[1],self.Ati,self.X,self.S,self.raw) if a is not None)


class MacroResponse:
    @classmethod
    def from_checkpoint(cls,layout,blocks,a,capacity):
        """Reload one trusted response and second LU without refactorization."""
        for name,actual in (('child_rows',np.asarray(layout.child_rows)),('child_interiors',np.asarray(layout.child_interiors)),
            ('child_traces',np.asarray(layout.child_traces)),('macro_boundary',layout.boundary),('macro_inside',layout.inside),('macro_trace',layout.trace),('boundary_lift',layout.lift)):
            if not np.array_equal(a[name],actual):raise ValueError('saved macro exact layout/trace pairing')
        obj=cls.__new__(cls);obj.layout=layout;obj.blocks=tuple(blocks);obj.response=True;obj.sparse_inner=False
        position={int(r):i for i,r in enumerate(layout.trace)};obj.bi=np.asarray([position[int(r)] for r in layout.boundary]);obj.ji=np.asarray([position[int(r)] for r in layout.inside])
        nb,ni=len(obj.bi),len(obj.ji);obj.factor=(a['second_factor'],a['second_pivots'])
        obj.Sib=sparse.csr_matrix((a['second_trace_to_inside_data'],a['second_trace_to_inside_indices'],a['second_trace_to_inside_indptr']),shape=(ni,nb))
        obj.Sbi=sparse.csr_matrix((a['second_inside_to_trace_data'],a['second_inside_to_trace_indices'],a['second_inside_to_trace_indptr']),shape=(nb,ni))
        obj.low_schur=a['macro_schur'];obj.X=None;obj.Sii=None;obj.Sbb=None;obj.capacity=dict(capacity)
        if obj.factor[0].shape!=(ni,ni) or obj.factor[1].shape!=(ni,) or obj.low_schur.shape!=(layout.lift.shape[1],)*2 or any(not np.isfinite(v).all() for v in (obj.factor[0],obj.low_schur,obj.Sib.data,obj.Sbi.data)):raise ValueError('saved macro finite complete inventory')
        obj.backward=capacity['factor_witness_operation_backward'];obj.rhs_relative=capacity['factor_witness_RHS_relative']
        if not np.isfinite(obj.backward) or obj.backward>1e-10:raise ValueError('saved macro factor qualification')
        for value in (obj.factor[0],obj.factor[1],obj.low_schur,obj.Sib.data,obj.Sbi.data):value.setflags(write=False)
        obj.solve=lambda rhs:lu_solve(obj.factor,rhs);return obj

    def __init__(self,layout,blocks,journal,*,response=True):
        self.layout=layout;self.blocks=tuple(blocks);self.response=response;columns=layout.lift.shape[1]
        contributions=sum(len(rows)**2 for rows in layout.child_traces)
        assembly_bound=contributions*(32+32+24)+layout.lift.nbytes
        limit=(8 if response else 16)*2**30
        if assembly_bound>limit:raise MemoryError('local Schur COO/CSR overlap exceeds fixed capacity before allocation')
        journal.allocation('macro_local_assembly_overlap',dict(workspace_bytes=assembly_bound))
        n=len(layout.trace);position={int(r):i for i,r in enumerate(layout.trace)};rr=[];cc=[];vv=[]
        with journal.measured('child_schur_macro_local_assembly'):
            for rows,B in zip(layout.child_traces,blocks,strict=True):
                ids=np.asarray([position[int(r)] for r in rows]);rr.append(np.repeat(ids,len(ids)));cc.append(np.tile(ids,len(ids)));vv.append(B.S.ravel())
            S=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(n,n)).tocsr();S.sum_duplicates();S.sort_indices()
        bi=np.array([position[int(r)] for r in layout.boundary]);ji=np.array([position[int(r)] for r in layout.inside])
        self.bi,self.ji=bi,ji;self.Sbb=S[bi][:,bi];self.Sbi=S[bi][:,ji];self.Sib=S[ji][:,bi]
        Sii=S[ji][:,ji];self.sparse_inner=not response
        if response and len(ji)>756:raise ValueError('global r2 macro second stage exceeds 756')
        if not response and len(ji)>9288:raise ValueError('one r4 sparse stage exceeds 9288')
        estimate=(sum(a.nbytes for a in (S.data,S.indices,S.indptr))+self.layout.lift.nbytes)
        if response:estimate+=3*len(ji)**2*16+2*len(ji)*columns*16
        else:estimate+=3*(len(ji)**2+len(ji))*24  # full triangular fill bound, not a dense allocation
        estimate+=assembly_bound
        self.capacity=dict(macro_rows=len(layout.native_rows),trace_rows=n,boundary_rows=len(bi),second_stage_rows=len(ji),matrix_nnz=int(S.nnz),planned_workspace_bytes=estimate,r4_full_response_library=False,
            assembly_overlap_bound_bytes=assembly_bound,sparse_factor_full_fill_payload_bound_bytes=None if response else (len(ji)**2+len(ji))*24,
            sparse_factor_workspace_assumption='three full-fill payloads; actual sparse factor and measured RSS reported separately',r4_dense_second_matrix_allocated=False)
        if estimate>(8 if response else 16)*2**30:raise MemoryError('macro response storage qualification')
        journal.allocation('macro_local_second_stage',dict(workspace_bytes=estimate))
        with journal.measured('macro_internal_microtrace_factor'):
            if response:self.factor=lu_factor(Sii.toarray());self.solve=lambda rhs:lu_solve(self.factor,rhs)
            else:
                from scipy.sparse.linalg import splu
                self.factor=splu(Sii.tocsc(),permc_spec='COLAMD');self.solve=self.factor.solve
        w=np.linspace(1,2,len(ji))+1j*np.linspace(.1,.9,len(ji))
        sol=self.solve(w);defect=Sii@sol-w;self.rhs_relative=relative(defect,w)
        self.backward=float(np.linalg.norm(defect)/max(np.linalg.norm(Sii.data)*np.linalg.norm(sol)+np.linalg.norm(w),1e-30))
        if not np.isfinite(self.backward) or self.backward>1e-10:raise ValueError('macro second-stage solve not qualified')
        self.low_schur=None;self.X=None
        if response:
            self.X=np.empty((len(ji),columns),complex);self.low_schur=np.empty((columns,columns),complex)
            with journal.measured('macro_432_response_bounded_16_columns'):
                for j in range(0,columns,16):
                    L=layout.lift[:,j:j+16];X=-self.solve(self.Sib@L);self.X[:,j:j+16]=X
                    self.low_schur[:,j:j+16]=layout.lift.conj().T@(self.Sbb@L+self.Sbi@X)
            self.low_schur.setflags(write=False)
        self.capacity['actual_second_factor_bytes']=self.factor[0].nbytes+self.factor[1].nbytes if response else sum(a.nbytes for mat in (self.factor.L,self.factor.U) for a in (mat.data,mat.indices,mat.indptr))
        self.capacity.update(factor_witness_RHS_relative=self.rhs_relative,factor_witness_operation_backward=self.backward,
            child_backward_max=max(b.backward_error for b in blocks),child_RHS_relative_max=max(b.rhs_relative_error for b in blocks),child_rcond1_min=min(b.rcond1 for b in blocks))
        self.Sii=Sii if not response else None
        if response:self.Sbb=None  # recover/reduce retain Sib/Sbi, never the obsolete full workspace
    def reduce(self,f):
        L=self.layout;f=np.asarray(f);ft=f[L.trace].copy();position={int(r):i for i,r in enumerate(L.trace)}
        for i,t,B in zip(L.child_interiors,L.child_traces,self.blocks,strict=True):
            ids=np.asarray([position[int(r)] for r in t]);np.add.at(ft,ids,-B.Ati@lu_solve(B.lu,f[i]))
        low=L.lift.conj().T@(ft[self.bi]-self.Sbi@self.solve(ft[self.ji]))
        return low,ft
    def recover(self,t,f):
        L=self.layout;low,ft=self.reduce(f);u=np.zeros(len(L.native_rows),complex)
        u[L.boundary]=L.lift@t
        u[L.inside]=self.solve(ft[self.ji]-self.Sib@u[L.boundary])
        for i,tt,B in zip(L.child_interiors,L.child_traces,self.blocks,strict=True):u[i]=B.X@u[tt]+lu_solve(B.lu,np.asarray(f)[i])
        return u
    def reaction(self,u,f):
        out=np.zeros(len(u),complex)
        for rows,B in zip(self.layout.child_rows,self.blocks,strict=True):np.add.at(out,rows,B.raw@u[rows])
        return self.layout.lift.conj().T@(out[self.layout.boundary]-np.asarray(f)[self.layout.boundary]),out-np.asarray(f)
    def bytes(self):
        mats=(self.Sbb,self.Sbi,self.Sib,self.Sii)
        result=sum(sum(x.nbytes for x in (m.data,m.indices,m.indptr)) for m in mats if m is not None)+self.layout.lift.nbytes
        result+=self.capacity['actual_second_factor_bytes']
        for a in (self.X,self.low_schur):
            if a is not None:result+=a.nbytes
        return result
