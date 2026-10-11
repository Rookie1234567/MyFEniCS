"""Opt-in Maxwell-harmonic transfer on the existing physical coarse skeleton.

Only macro principal matrices and the bounded coarse matrix are assembled.
The reverse map is the full complex dual, including interior/port lifts.
"""
import gc
import time
from pathlib import Path

import numpy as np
from scipy import sparse

from .bounded_trace_pc import csr_load, csr_save, coarse_galerkin, BoundedTwoLevelPC
from .scattering_anchor import relative, save_arrays
from .scattering_anchor_checks import checked_arrays
from src.runners.task042_shared import write_json


def entity_on_parent_boundary(vertices, parent_vertices, *, tolerance=2e-11):
    """Geometric face closure predicate, unrelated to numerical matrix drops."""
    J=(parent_vertices[1:]-parent_vertices[0]).T
    r=(vertices-parent_vertices[0])@np.linalg.inv(J).T
    bary=np.column_stack((1-r.sum(axis=1),r))
    if bary.min() < -tolerance or bary.max()>1+tolerance:
        raise ValueError('fine entity outside its exact recorded parent tetrahedron')
    return bool(np.any(np.all(np.abs(bary)<=tolerance,axis=0)))


def macro_partition(setup,service,parent_cells,parent_geometry):
    import basix
    if parent_cells.shape!=(service.manifest['cells'],):raise ValueError('fine-parent inventory')
    nparent=len(parent_geometry);owner=np.full(service.nt,-2,np.int32)
    skeleton=np.zeros(service.nt,bool);exterior=np.zeros(service.nt,bool)
    e=setup['V'].element.basix_element;top=basix.cell.topology(basix.CellType.tetrahedron)
    local_trace=np.setdiff1d(np.arange(e.dim),e.entity_dofs[3][0])
    local_inverse=np.full(e.dim,-1,np.int32);local_inverse[local_trace]=np.arange(len(local_trace))
    axes=setup['physical']['geometry']['axes_nm'];limits=np.array([[axes[a][0],axes[a][-1]] for a in ('x','y','z')])
    for c,_,ids,E,_ in service.cell_records:
        p=int(parent_cells[c])
        if not 0<=p<nparent:raise ValueError('recorded macro parent range')
        xyz=setup['mesh'].geometry.x[setup['mesh'].geometry.dofmap[c]]
        for dim in (1,2):
            for k,dofs in enumerate(e.entity_dofs[dim]):
                vertices=xyz[top[dim][k]]
                boundary=entity_on_parent_boundary(vertices,parent_geometry[p])
                outer=any(np.all(np.abs(vertices[:,d]-limits[d,side])<=2e-12)
                          for d in range(3) for side in range(2))
                # Apply the ACTUAL finalized cell expansion, including slaves.
                rows=np.unique(E[local_inverse[dofs]].indices);active=ids[rows]
                if boundary or outer:skeleton[active]=True
                for row in active:
                    if owner[row]==-2:owner[row]=p
                    elif owner[row]!=p:skeleton[row]=True
                exterior[active]|=outer
    if np.any(owner==-2):raise ValueError('macro partition missing canonical trace owner')
    owner[skeleton]=-1
    if np.any(exterior & ~skeleton):raise ValueError('physical boundary omitted from skeleton')
    interiors=[np.flatnonzero(owner==p) for p in range(nparent)]
    if max(map(len,interiors))>20000:raise MemoryError('macro J row cap')
    for c,_,ids,_,_ in service.cell_records:
        values=np.unique(owner[ids]);values=values[values>=0]
        if len(values)>1 or (len(values) and values[0]!=parent_cells[c]):
            raise ValueError('cell contribution connects distinct macro interiors')
    return owner,dict(skeleton_rows=int(skeleton.sum()),interior_rows=int((owner>=0).sum()),
        macro_count=nparent,maximum_J_rows=max(map(len,interiors)),empty_macros=sum(not len(v) for v in interiors),
        exterior_rows=int(exterior.sum()),physical_exterior_in_skeleton=True,partition_complete=True,
        no_cross_macro_J_cell_contribution=True,removed_cell_internal_rows=service.n-service.nt,
        parent_geometry_sha256=__import__('hashlib').sha256(parent_geometry.tobytes()).hexdigest())


class HarmonicTransfer:
    """Sparse skeleton plus saved local lifts; full Hermitian reverse map."""
    def __init__(self, skeleton, lifts, ports, *, limit_bytes=8*2**30):
        self.skeleton=skeleton.tocsr();self.lifts=lifts;self.ports=ports
        self.shape=(skeleton.shape[0]+ports,skeleton.shape[1]+ports)
        self.payload_bytes=sum(a.nbytes for a in (skeleton.data,skeleton.indices,skeleton.indptr))
        self.payload_bytes+=sum(sum(a.nbytes for a in (v['rows'],v['columns'],v['values'])) for v in lifts)
        if self.payload_bytes>limit_bytes:raise MemoryError('harmonic lift/map resident cap')
        for v in lifts:
            if v['values'].shape!=(len(v['rows']),len(v['columns'])):raise ValueError('lift exact shape')
            for a in v.values():a.setflags(write=False)

    def prolong(self,w):
        if w.shape!=(self.shape[1],):raise ValueError('harmonic coarse vector shape')
        out=np.r_[self.skeleton@w[:self.skeleton.shape[1]],w[self.skeleton.shape[1]:]]
        for v in self.lifts:out[v['rows']]=v['values']@w[v['columns']]
        return out

    def restrict(self,r):
        if r.shape!=(self.shape[0],):raise ValueError('harmonic fine vector shape')
        out=np.r_[self.skeleton.conj().T@r[:self.skeleton.shape[0]],r[self.skeleton.shape[0]:]]
        for v in self.lifts:
            # Conjugate only a bounded local block, never the global tall map.
            np.add.at(out,v['columns'],v['values'].conj().T@r[v['rows']])
        return out

    @classmethod
    def load(cls,record):
        Z=csr_load(record['skeleton']);lifts=[]
        for row in record['macros']:
            if row['lift'] is not None:lifts.append(checked_arrays(row['lift']))
        return cls(Z,lifts,record['ports'])


def local_extension(F,AJQ,AQJ):
    """Small regression oracle only. Production uses bounded native MUMPS."""
    lift=-np.linalg.solve(F,AJQ)
    return lift,AQJ@lift


def macro_blocks(service,cell_indices,J,ZB,left,right):
    from petsc4py import PETSc
    rowmap=np.full(service.nt,-1,np.int64);rowmap[J]=np.arange(len(J))
    ccols=np.unique(np.concatenate([ZB[service.cell_records[c][2]].indices for c in cell_indices]))
    C=(service.Ctilde[J]@sparse.diags(right[service.nt:])).tocsr()
    D=(sparse.diags(left[service.nt:])@service.Dtilde[:,J]).tocsr()
    ports=np.union1d(C.indices,np.flatnonzero(np.diff(D.indptr)))
    columns=np.r_[ccols,ZB.shape[1]+ports].astype(np.int64)
    ahead=len(J)*len(columns)*32+len(J)**2*16
    if ahead>2*2**30:raise MemoryError('single macro matrix/cross workspace preallocation')
    AJQ=np.zeros((len(J),len(columns)),complex);AQJ=np.zeros((len(columns),len(J)),complex)
    AJQ[:,len(ccols):]=C[:,ports].toarray();AQJ[len(ccols):]=D[ports].toarray()
    parts=[];nnz=np.zeros(len(J),np.int64)
    for c in cell_indices:
        _,_,ids,E,key=service.cell_records[c];good=np.flatnonzero(rowmap[ids]>=0)
        if not len(good):continue
        rows=rowmap[ids[good]];np.add.at(nnz,rows,len(rows));parts.append((ids,E,key,good,rows))
    F=PETSc.Mat().createAIJ(size=(len(J),)*2,nnz=np.minimum(nnz,len(J)),comm=PETSc.COMM_SELF)
    F.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,True)
    try:
        for ids,E,key,good,rows in parts:
            ej=E[:,good].toarray();pb=E@ZB[ids][:,ccols].toarray();S=service.cache[key]['schur']
            F.setValues(rows,rows,ej.conj().T@S@ej,addv=PETSc.InsertMode.ADD_VALUES)
            AJQ[rows,:len(ccols)]+=ej.conj().T@S@pb
            AQJ[:len(ccols),rows]+=pb.conj().T@S@ej
        F.assemblyBegin();F.assemblyEnd();ptr,col,val=F.getValuesCSR()
        A=sparse.csr_matrix((val.copy(),col.copy(),ptr.copy()),shape=F.getSize())
    finally:F.destroy()
    return A,AJQ,AQJ,columns


def build_harmonic(service,Z0,owner,left,right,folder,journal,*,require_live,
                   base_provider=None,parent_folder=None,reuse_compatibility=None,
                   future_reserve_bytes=None):
    """Direct bounded coarse accumulation; no global fine skeleton matrix."""
    from .bounded_trace_study import symbolic
    from .independent_tetra_study import petsc_matrix
    from .fullspace_v17_p3_oracle import _MumpsFactor
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    import os
    folder=Path(folder);folder.mkdir(exist_ok=True)
    ZB=Z0.multiply((owner<0)[:,None]).tocsr();ZB.eliminate_zeros()
    if len(np.unique(ZB.indices))!=Z0.shape[1]:raise ValueError('p2 entity column coverage lost on skeleton')
    skeleton=csr_save(folder/'skeleton.npz',ZB)
    with journal.measured('skeleton_local_Galerkin_with_port_base_once'):
        base=(coarse_galerkin(service,ZB,left,right) if base_provider is None
              else base_provider(service,ZB,left,right))
    coarse=petsc_matrix(base)
    from petsc4py import PETSc
    coarse.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,False)
    del base;rows=[];lift_bytes=0;started=time.monotonic()
    reused_count=0;new_numeric_count=0;legacy_numeric_count=0;recomputed_count=0
    if parent_folder is not None:
        if reuse_compatibility is None or not reuse_compatibility.get('pass_gate'):
            raise ValueError('explicit mathematical compatibility required for parent lifts')
        parent_folder=Path(parent_folder)
    by_parent=[[] for _ in range(int(owner.max())+1)]
    # Every cell containing a J degree is assigned from the qualified partition.
    for c,_,ids,_,_ in service.cell_records:
        p=np.unique(owner[ids]);p=p[p>=0]
        if len(p):by_parent[int(p[0])].append(c)
    try:
        for macro,cells in enumerate(by_parent):
            require_live()
            J=np.flatnonzero(owner==macro);record_path=folder/f'macro{macro:04d}.json'
            from_parent=False
            if not record_path.exists() and parent_folder is not None and (parent_folder/record_path.name).exists():
                if macro not in reuse_compatibility['healthy_macro_ids']:
                    raise ValueError('parent macro absent from validated compatibility receipt')
                record_path=parent_folder/record_path.name;from_parent=True
            if record_path.exists():
                old=__import__('json').loads(record_path.read_text());a=checked_arrays(old['lift'])
                if not np.array_equal(a['rows'],J):raise ValueError('resumed macro row identity')
                correction=checked_arrays(old['correction']);coarse.setValues(a['columns'],a['columns'],correction['values'],addv=__import__('petsc4py').PETSc.InsertMode.ADD_VALUES)
                row=dict(old,reused_from=str(record_path),parent_producer_source=(reuse_compatibility['parent_producer_source'] if from_parent else None))
                rows.append(row);lift_bytes+=sum(x.nbytes for x in a.values())
                reused_count+=1
                if from_parent:legacy_numeric_count+=old.get('numeric_count',0)
                journal.event('healthy_harmonic_macro_reused',macro=macro,from_parent=from_parent,completed=len(rows),new_numeric_count=new_numeric_count)
                continue
            if not len(J):rows.append(dict(macro=macro,rows=0,lift=None));continue
            with journal.measured('macro_local_prepare_'+str(macro)):
                A,AJQ,AQJ,cols=macro_blocks(service,cells,J,ZB,left,right)
            info=symbolic(A,journal,'macro'+str(macro))
            sample=process_tree_snapshot(int(os.environ['TASK042_WATCHDOG_PARENT_PID']),'harmonic-macro-numeric',include_pss=False)
            workspace=A.data.nbytes+A.indices.nbytes+A.indptr.nbytes+AJQ.nbytes+AQJ.nbytes+AJQ.nbytes
            future=(max(workspace,2*2**30) if future_reserve_bytes is None
                    else max(future_reserve_bytes,AJQ.nbytes+16*len(J)*32))
            planned=sample['rss_bytes']+info['double_bytes']+future
            admitted=info['double_bytes']<=8*2**30 and planned<=96*2**30 and sample['swap_bytes']==0
            admission=dict(tree=sample,planned_simultaneous_bytes=planned,workspace_bytes=workspace,
                future_bytes=future,future_scope='future lift and bounded numeric/consumer reserve; resident matrices already in live RSS',
                double_symbolic_bytes=info['double_bytes'],admitted=admitted)
            write_json(folder/'current_macro_admission.json',dict(macro=macro,admission=admission,analysis=info))
            if not admitted:raise MemoryError('bounded harmonic macro numeric admission')
            matrix=petsc_matrix(A);factor=_MumpsFactor(matrix);lift=np.empty_like(AJQ)
            try:
                factor.symbolic(matrix)
                if max(int(factor.info()['infog'][str(k)]) for k in (16,17))!=info['estimate_mb']:raise ValueError('macro symbolic changed')
                factor.set_memory_limit_mb(2*info['estimate_mb'])
                with journal.measured('macro_numeric_'+str(macro)):factor.numeric(matrix)
                new_numeric_count+=1
                with journal.measured('macro_lift_columns_'+str(macro)):
                    for start in range(0,len(cols),16):
                        for j in range(start,min(start+16,len(cols))):lift[:,j]=-BoundedTwoLevelPC.solve(factor,AJQ[:,j])
                residual=A@lift+AJQ;op=abs(A)@abs(lift)+abs(AJQ)
                errors=dict(relative=relative(residual,AJQ),operation_scaled=relative(residual,op),
                    absolute=float(np.linalg.norm(residual)),operation_scale=float(np.linalg.norm(op)),
                    amplification=float(np.linalg.norm(lift)/max(np.linalg.norm(AJQ),1e-300)))
                if not np.isfinite(lift).all() or max(errors['relative'],errors['operation_scaled'])>1e-10:raise ValueError('actual harmonic macro solve residual')
                controls=factor.symbolic_memory_settings()
            finally:factor.destroy();matrix.destroy()
            current=sum(v.nbytes for v in (J,cols,lift));lift_bytes+=current
            if lift_bytes+ZB.data.nbytes+ZB.indices.nbytes+ZB.indptr.nbytes>8*2**30:raise MemoryError('saved harmonic lift aggregate cap')
            with journal.measured('macro_coarse_correction_'+str(macro)):
                correction=AQJ@lift
                from petsc4py import PETSc
                coarse.setValues(cols,cols,correction,addv=PETSc.InsertMode.ADD_VALUES)
            receipt=save_arrays(folder/f'lift{macro:04d}.npz',rows=J,columns=cols,values=lift)
            cor=save_arrays(folder/f'correction{macro:04d}.npz',values=correction)
            row=dict(macro=macro,rows=len(J),columns=len(cols),lift=receipt,correction=cor,analysis=info,
                admission=admission,errors=errors,controls=controls,numeric_count=1,triangular_calls=len(cols),factor_released=True,
                producer_source=getattr(journal,'source_state',{}).get('source_sha'))
            write_json(record_path,row);rows.append(row)
            write_json(folder/'progress.json',dict(completed=len(rows),saved_lift_bytes=lift_bytes,elapsed_seconds=time.monotonic()-started))
            del A,AJQ,AQJ,lift,correction;gc.collect()
        coarse.assemblyBegin();coarse.assemblyEnd();ptr,col,val=coarse.getValuesCSR()
        EH=sparse.csr_matrix((val.copy(),col.copy(),ptr.copy()),shape=coarse.getSize())
    finally:coarse.destroy()
    manifest=dict(skeleton=skeleton,macros=rows,ports=service.m,coarse_rows=EH.shape[0],p2_columns=Z0.shape[1],
        saved_lift_bytes=lift_bytes,port_base_aggregations=1,global_fine_K_or_S_formations=0,
        macro_numeric_count=sum(r.get('numeric_count',0) for r in rows),
        reused_count=reused_count,new_numeric_count=new_numeric_count,
        recomputed_count=recomputed_count,legacy_numeric_count=legacy_numeric_count)
    write_json(folder/'manifest.json',manifest)
    return manifest,EH
