"""Fixed geometric RAS plus sparse physical trace Galerkin correction.

Every matrix is bounded local or coarse. No global fine matrix is formed,
and interpolation is by actual Nedelec moments on nested affine tetrahedra.
"""
import gc
import time
from pathlib import Path

import numpy as np
from scipy import sparse

from .scattering_anchor import relative, save_arrays
from .scattering_anchor_checks import checked_arrays


def csr_save(path, A, **extra):
    A=A.tocsr();A.sum_duplicates();A.sort_indices()
    return save_arrays(path,data=A.data,indices=A.indices.astype(np.int64),
                       indptr=A.indptr.astype(np.int64),shape=np.asarray(A.shape,np.int64),**extra)


def csr_load(receipt):
    a=checked_arrays(receipt)
    return sparse.csr_matrix((a['data'],a['indices'],a['indptr']),shape=tuple(a['shape']))


def entity_centers(setup,service):
    """Unique canonical master entity centers; never split a moment family."""
    import basix
    V=setup['V'];P=setup['P'];n=P.shape[0]
    native_to_trace=np.full(n,-1,np.int64)
    native_to_trace[setup['masters'][service.retained[:service.nt]]]=np.arange(service.nt)
    centers=np.full((service.nt,3),np.nan)
    vertices=basix.cell.topology(basix.CellType.tetrahedron)
    dofs=V.element.basix_element.entity_dofs
    for c in range(service.manifest['cells']):
        xyz=setup['mesh'].geometry.x[setup['mesh'].geometry.dofmap[c]]
        ids=V.dofmap.cell_dofs(c)
        for dim in (1,2):
            for entity,local in enumerate(dofs[dim]):
                rows=native_to_trace[ids[local]];rows=rows[rows>=0]
                if not len(rows):continue
                center=xyz[vertices[dim][entity]].mean(axis=0)
                centers[rows]=center
    if not np.isfinite(centers).all():raise ValueError('trace entity owner inventory')
    axes=setup['physical']['geometry']['axes_nm']
    for d,a in enumerate(('x','y')):
        # Periodic representatives, including a master chosen on the high side.
        lo,hi=axes[a][0],axes[a][-1]
        centers[centers[:,d]==hi,d]=lo
    return centers


def periodic_neighbors(setup):
    mesh=setup['mesh'];mesh.topology.create_connectivity(2,3)
    mesh.topology.create_connectivity(2,0)
    fc=mesh.topology.connectivity(2,3);fv=mesh.topology.connectivity(2,0)
    # Mesh geometry degree1; topology vertices and geometry nodes can differ.
    from dolfinx.mesh import entities_to_geometry
    facets=np.arange(mesh.topology.index_map(2).size_local,dtype=np.int32)
    geometry=entities_to_geometry(mesh,2,facets,False)
    adjacent=[set() for _ in range(setup['spec']['cells'])];periodic={}
    cfg=setup['cfg'];pairs=0
    for f in facets:
        cells=fc.links(int(f))
        if len(cells)==2:
            a,b=map(int,cells);adjacent[a].add(b);adjacent[b].add(a)
        elif len(cells)==1:
            xyz=mesh.geometry.x[geometry[f]].copy()
            for d,L in ((0,cfg.period_x),(1,cfg.period_y)):
                if np.all(xyz[:,d]==0) or np.all(xyz[:,d]==L):
                    xyz[:,d]=0
                    key=(d,tuple(sorted(map(tuple,xyz))))
                    if key in periodic:
                        a=periodic.pop(key);b=int(cells[0]);adjacent[a].add(b);adjacent[b].add(a);pairs+=1
                    else:periodic[key]=int(cells[0])
    if periodic:raise ValueError('exact periodic facet mate inventory incomplete')
    return adjacent,pairs


def geometric_patches(setup,service,*,row_cap=80000,count_cap=64):
    centers=entity_centers(setup,service)
    axes=setup['physical']['geometry']['axes_nm']
    cuts=[np.linspace(axes[a][0],axes[a][-1],v+1) for a,v in zip(('x','y','z'),(4,2,4))]
    neighbors,periodic=periodic_neighbors(setup)
    cell_centers=setup['geometry']['cell_centers'].copy()
    boxes=[(np.array([cuts[0][i],cuts[1][j],cuts[2][k]]),np.array([cuts[0][i+1],cuts[1][j+1],cuts[2][k+1]]))
           for i in range(4) for j in range(2) for k in range(4)]
    high=np.array([axes[a][-1] for a in ('x','y','z')]);out=[]

    def contains(x,lo,hi):
        return np.all((x>=lo)&((x<hi)|((hi==high)&(x==hi))),axis=1)

    pending=list(boxes)
    while pending:
        lo,hi=pending.pop(0);core=np.flatnonzero(contains(centers,lo,hi))
        core_cells=set(np.flatnonzero(contains(cell_centers,lo,hi)).tolist())
        halo=set(core_cells)
        for c in core_cells:halo.update(neighbors[c])
        ids=np.unique(np.concatenate([service.cell_records[c][2] for c in sorted(halo)])) if halo else np.empty(0,np.int64)
        if len(ids)>row_cap:
            if len(out)+len(pending)+2>count_cap:raise MemoryError('fixed patch split count/row capacity')
            d=int(np.argmax(hi-lo));mid=(lo[d]+hi[d])/2;h=hi.copy();h[d]=mid;l=lo.copy();l[d]=mid
            pending[0:0]=[(lo,h),(l,hi)];continue
        if not np.isin(core,ids).all():raise ValueError('geometric core writeback outside one-tet halo')
        out.append(dict(ids=ids,core=core,core_cells=np.array(sorted(core_cells),np.int32),
                        halo_cells=np.array(sorted(halo),np.int32),low=lo,high=hi))
    owners=np.zeros(service.nt,np.int16)
    for p in out:np.add.at(owners,p['core'],1)
    if not np.all(owners==1):raise ValueError('unique RAS core owner closure')
    return out,dict(initial_cores=32,patches=len(out),periodic_facet_pairs=periodic,
                    all_trace_writeback_once=True,maximum_rows=max(len(p['ids']) for p in out),
                    overlap_row_sum=sum(len(p['ids']) for p in out))


def coarse_trace_embedding(fine,coarse,service,journal):
    """Basix integral interpolation with full affine Piola and native transforms."""
    from .independent_tetra_reference import TetraEvaluator
    from .independent_tetra_fields import locate
    V= fine['V']; W=coarse['V'];element=V.element.basix_element
    evf=TetraEvaluator(V,0,fine['kappa'],quadrature_tables=False)
    evc=TetraEvaluator(W,0,coarse['kappa'],quadrature_tables=False)
    if element.interpolation_nderivs!=0:raise ValueError('unexpected derivative moment interpolation')
    loc_t=np.setdiff1d(np.arange(140),element.entity_dofs[3][0])
    inverse={};owner=np.full(service.nt,-1,np.int32)
    native_to_trace=np.full(fine['P'].shape[0],-1,np.int64)
    native_to_trace[fine['masters'][service.retained[:service.nt]]]=np.arange(service.nt)
    rr=[];cc=[];vv=[];parents=[];samples=[]
    rng=np.random.default_rng(7102)
    cw=rng.normal(size=(coarse['P'].shape[1],2))+1j*rng.normal(size=(coarse['P'].shape[1],2))
    native_coarse=(coarse['P']@cw)[:,0]
    expected=np.empty((service.manifest['cells'],110,2),np.complex128)
    for c in range(service.manifest['cells']):
        J,o,_=evf.geometry[c];parent=int(locate(evc,fine['geometry']['cell_centers'][c:c+1])[0]);parents.append(parent)
        K,b,_=evc.geometry[parent];F=np.linalg.inv(K)
        points=element.points@J.T+o;refs=(points-b)@F.T
        if refs.min()<-1e-10 or refs.sum(axis=1).max()>1+1e-10:
            raise ValueError('fine cell not contained in actual original960tet parent')
        values=W.element.basix_element.tabulate(0,refs)[0]@F@J
        I=element.interpolation_matrix@values.transpose(2,0,1).reshape(-1,W.element.space_dimension)
        key=int(evf.permutations[c])
        if key not in inverse:inverse[key]=np.linalg.inv(evf.transform(c).T)
        T=inverse[key]@I@evc.transform(parent).T
        coarse_rows=W.dofmap.cell_dofs(parent);expansion=coarse['P'][coarse_rows].tocsr()
        local=sparse.csr_matrix(T[loc_t])@expansion
        expected[c]=local@cw
        native_rows=V.dofmap.cell_dofs(c)[loc_t];global_rows=native_to_trace[native_rows]
        selected=np.flatnonzero((global_rows>=0)&(owner[np.maximum(global_rows,0)]<0))
        for j in selected:
            row=int(global_rows[j]);a,z=local.indptr[j:j+2]
            rr.append(np.full(z-a,row,np.int64));cc.append(local.indices[a:z].copy());vv.append(local.data[a:z].copy());owner[row]=c
        # Field and curl witness on two fixed interior points, across real directions.
        if len(samples)<12 and (c<4 or int(evf.permutations[c]) not in [s['permutation'] for s in samples]):
            r=np.array([[.11,.17,.23],[.19,.13,.29]])
            actual=T@native_coarse[coarse_rows];coef=evf.transform(c).T@actual
            tab=element.tabulate(1,r);native=r@J.T+o
            tref=(native-b)@F.T;tabc=W.element.basix_element.tabulate(1,tref)
            low=evc.transform(parent).T@native_coarse[coarse_rows]
            a=tab[0].transpose(0,2,1)@coef;d=tabc[0].transpose(0,2,1)@low
            u=a@np.linalg.inv(J);v=d@F
            cf=(evf.curl_table(tab).transpose(0,2,1)@coef)@J.T/np.linalg.det(J)
            cl=(evc.curl_table(tabc).transpose(0,2,1)@low)@K.T/np.linalg.det(K)
            errors=dict(E=relative(u-v,v),curl=relative(cf-cl,cl))
            samples.append(dict(cell=c,parent=parent,permutation=int(evf.permutations[c]),errors=errors))
            if max(errors.values())>1e-10:raise ValueError('true moment/Piola/direction coarse field gate')
        if c%512==0:journal.event('coarse_true_moment_rows',cell=c,columns=coarse['P'].shape[1])
    if np.any(owner<0):raise ValueError('coarse trace row owner incomplete')
    Z=sparse.csr_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(service.nt,coarse['P'].shape[1]));Z.sum_duplicates()
    global_trace=Z@cw;shared_max=0.
    for c,_,ids,E,_ in service.cell_records:
        shared_max=max(shared_max,relative(E@global_trace[ids]-expected[c],expected[c]))
    if shared_max>1e-10:raise ValueError('shared/periodic true coarse trace pullback consistency')
    return Z,dict(independent_FE=coarse['P'].shape[1],with_ports=coarse['P'].shape[1]+service.m,
                  sparse_nnz=Z.nnz,parent_cells=np.asarray(parents,np.int32),witness=samples,
                  moment_interpolation=True,owner_once=True,dense_N_by_coarse=False,
                  shared_periodic_maximum=shared_max,shared_periodic_columns=2)


def local_principal(service,ids):
    """All cells contribute to the principal block, even outside patch halo."""
    from petsc4py import PETSc
    mapping=np.full(service.nt,-1,np.int64);mapping[ids]=np.arange(len(ids))
    parts=[];nnz=np.zeros(len(ids),np.int64)
    for c,i,active,E,key in service.cell_records:
        good=np.flatnonzero(mapping[active]>=0)
        if not len(good):continue
        rows=mapping[active[good]];np.add.at(nnz,rows,len(rows))
        parts.append((rows,E[:,good],key))
    nnz=np.minimum(nnz,len(ids))
    A=PETSc.Mat().createAIJ(size=(len(ids),)*2,nnz=nnz,comm=PETSc.COMM_SELF)
    A.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,True)
    for rows,E,key in parts:
        dense=E.toarray();A.setValues(rows,rows,dense.conj().T@service.cache[key]['schur']@dense,addv=PETSc.InsertMode.ADD_VALUES)
    A.assemblyBegin();A.assemblyEnd()
    ptr,col,val=A.getValuesCSR();result=sparse.csr_matrix((val.copy(),col.copy(),ptr.copy()),shape=A.getSize())
    A.destroy();return result


def coarse_galerkin(service,Z,left,right):
    """Local Galerkin summation, without materializing Ahat*Z."""
    from petsc4py import PETSc
    n0=Z.shape[1];m=service.m
    A=PETSc.Mat().createAIJ(size=(n0+m,)*2,nnz=min(n0+m,1024),comm=PETSc.COMM_SELF)
    A.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,False)
    for _,_,ids,E,key in service.cell_records:
        z=Z[ids].tocsr();cols=np.unique(z.indices)
        if not len(cols):continue
        d=E@z[:,cols].toarray()
        A.setValues(cols,cols,d.conj().T@service.cache[key]['schur']@d,addv=PETSc.InsertMode.ADD_VALUES)
    C=(Z.conj().T@service.Ctilde).tocsr();D=(service.Dtilde@Z).tocsr()
    C=C@sparse.diags(right[service.nt:]);D=sparse.diags(left[service.nt:])@D
    for i in range(n0):
        a,z=C.indptr[i:i+2]
        if z>a:A.setValues([i],n0+C.indices[a:z],C.data[a:z],addv=PETSc.InsertMode.ADD_VALUES)
    for i in range(m):
        a,z=D.indptr[i:i+2]
        if z>a:A.setValues([n0+i],D.indices[a:z],D.data[a:z],addv=PETSc.InsertMode.ADD_VALUES)
    A.setValues(n0+np.arange(m),n0+np.arange(m),
                left[service.nt:,None]*service.Htilde*right[None,service.nt:],addv=PETSc.InsertMode.ADD_VALUES)
    A.assemblyBegin();A.assemblyEnd();ptr,col,val=A.getValuesCSR()
    result=sparse.csr_matrix((val.copy(),col.copy(),ptr.copy()),shape=A.getSize());A.destroy();return result


def prolong(Z,r):return np.r_[Z@r[:Z.shape[1]],r[Z.shape[1]:]]
def restrict(Z,r):return np.r_[Z.conj().T@r[:Z.shape[0]],r[Z.shape[0]:]]


class BoundedTwoLevelPC:
    def __init__(self,Z,patches,factors,coarse_factor,action):
        self.Z=Z;self.patches=patches;self.factors=factors;self.coarse=coarse_factor;self.action=action
        self.calls=dict(apply=0,local_triangular=0,coarse_triangular=0,internal_original_action=0)
        self.seconds=dict(local=0.,coarse=0.,original=0.)

    @staticmethod
    def solve(factor,x):
        from petsc4py import PETSc
        rhs=PETSc.Vec().createSeq(len(x),comm=PETSc.COMM_SELF);out=rhs.duplicate();rhs.array[:]=x
        try:factor.solve_repeated(rhs,out);return out.array.copy()
        finally:rhs.destroy();out.destroy()

    def __call__(self,r):
        r=np.asarray(r);self.calls['apply']+=1;began=time.perf_counter()
        z=prolong(self.Z,self.solve(self.coarse,restrict(self.Z,r)))
        self.calls['coarse_triangular']+=1;self.seconds['coarse']+=time.perf_counter()-began
        began=time.perf_counter();residual=r-self.action(z)
        self.calls['internal_original_action']+=1;self.seconds['original']+=time.perf_counter()-began
        began=time.perf_counter()
        for patch,factor in zip(self.patches,self.factors,strict=True):
            ids=patch['ids'];v=self.solve(factor,residual[ids]);core=patch['core']
            z[core]+=v[np.searchsorted(ids,core)];self.calls['local_triangular']+=1
        self.seconds['local']+=time.perf_counter()-began
        if not np.isfinite(z).all():raise FloatingPointError('fixed two-level PC nonfinite')
        return z

    def destroy(self):
        for f in self.factors:f.destroy()
        self.coarse.destroy();self.factors.clear();self.coarse=None;gc.collect()
