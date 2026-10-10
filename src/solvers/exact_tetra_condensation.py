"""Exact assembled cell elimination with a sealed, streamed recovery service.

All retained columns, including nonzero interior/port coupling, are kept.
This is an assembled prototype, not a matrix-free or distributed factor.
"""
import gc
import json
import os
import warnings
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays
from .scattering_anchor_checks import checked_arrays
from .tetra_body_checkpoint import file_digest, member_digest


def tetra_interiors(setup):
    """Use actual Basix entity-3 DoFs and the live Hermitian MPC expansion."""
    V, P = setup['V'], setup['P']
    local = np.asarray(V.element.basix_element.entity_dofs[3][0], np.int64)
    if local.shape != (30,) or V.element.basix_element.dim != 140:
        raise ValueError('exact p5 tetra 30/140 identity')
    cells = []
    for c in range(setup['spec']['cells']):
        native = np.asarray(V.dofmap.cell_dofs(c))[local]
        rows = P[native].tocsr()
        if not np.all(np.diff(rows.indptr) == 1) or not np.array_equal(rows.data, np.ones(30)):
            raise ValueError('cell interior is not one owned independent unit moment')
        cells.append(rows.indices.astype(np.int64, copy=True))
    flat = np.concatenate(cells)
    if len(flat) != 767280 or len(np.unique(flat)) != len(flat):
        raise ValueError('unique p5 interior inventory')
    return tuple(cells)


def check_internal_graph(A, cells):
    """Exact structural test; stored zero entries do not imply coupling."""
    owner = np.full(A.shape[0], -1, np.int32)
    for c, interior in enumerate(cells):
        if np.any(owner[interior] != -1):
            raise ValueError('duplicate interior owner')
        owner[interior] = c
    zeros = 0
    for c, interior in enumerate(cells):
        for row in interior:
            start, end = A.indptr[row:row+2]
            cols, values = A.indices[start:end], A.data[start:end]
            other = (owner[cols] >= 0) & (owner[cols] != c)
            if np.any(other & (values != 0)):
                raise ValueError('interior coupling crosses cell blocks')
            zeros += int(np.count_nonzero(other))
    return dict(cells=len(cells),interior_rows=int(np.count_nonzero(owner >= 0)),
                cross_cell_structural_zeros=zeros,nonzero_cross_cell_couplings=0)


class RecoveryWriter:
    """One bounded batch of local factors and original non-Hermitian blocks."""
    def __init__(self, folder, journal=None, batch=64):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=False)
        self.journal=journal;self.batch=batch;self.pending=[];self.receipts=[];self.count=0

    def __call__(self, ii, it, ti, bi, interior, rows, cols):
        with warnings.catch_warnings():
            warnings.simplefilter('error',LinAlgWarning)
            lu,piv=lu_factor(ii,check_finite=True)
        solved=lu_solve((lu,piv),np.column_stack((it,bi)),check_finite=True)
        if not np.all(np.isfinite(solved)):
            raise ValueError('nonfinite cell solve')
        self.pending.append((interior.copy(),rows.copy(),cols.copy(),lu,piv,it.copy(),ti.copy(),ii.copy()))
        self.count+=1
        if len(self.pending)>=self.batch:self.flush()
        return solved

    def flush(self):
        if not self.pending:return
        payload={}
        for i,name in enumerate(('interior','rows','cols','lu','piv','it','ti','ii')):
            values=[np.asarray(x[i]).reshape(-1) for x in self.pending]
            payload[name]=np.concatenate(values)
            payload[name+'_offsets']=np.r_[0,np.cumsum([v.size for v in values])].astype(np.int64)
        q=self.folder/f'chunk_{len(self.receipts):04d}.npz'
        self.receipts.append(save_arrays(q,**payload))
        self.pending.clear()
        if self.journal:
            self.journal.event('exact_local_recovery_chunk_committed',cells_completed=self.count,
                               local_LU_count=self.count,chunk=self.receipts[-1])


def _write_array(folder,name,value):
    a=np.ascontiguousarray(value);p=folder/(name+'.npy')
    with p.open('wb') as f:np.save(f,a,allow_pickle=False);f.flush();os.fsync(f.fileno())
    return dict(file=p.name,sha256=file_digest(p),member_sha256=member_digest(a),
                shape=list(a.shape),dtype=str(a.dtype),bytes=p.stat().st_size)


def build_checkpoint(A, rhs, cells, path, *, identity, source, journal=None):
    """Reuse the qualified assembled H(curl) elimination, then seal the result."""
    from .hcurl_cell_static_condensation import build_explicit_cell_static_condensation
    from .independent_tetra_study import petsc_matrix
    path=Path(path)
    if path.exists():raise FileExistsError('sealed condensed checkpoint: reload instead')
    partial=path.with_name(path.name+'.partial');partial.mkdir(parents=True,exist_ok=False)
    graph=check_internal_graph(A,cells)
    writer=RecoveryWriter(partial/'recovery',journal)
    matrix=petsc_matrix(A);b=matrix.createVecRight();b.array[:]=rhs
    condensed=None
    try:
        condensed=build_explicit_cell_static_condensation(matrix,b,cells,cell_processor=writer)
        writer.flush()
        ip,ix,data=condensed.matrix.getValuesCSR()
        retained=condensed.owned_trace_original_dofs
        # PETSc owns these arrays until the sealed files have been written.
        members={k:_write_array(partial,k,v) for k,v in dict(data=data,indices=ix,indptr=ip,
            rhs=condensed.rhs.array,retained=retained).items()}
        m=dict(schema='exact-assembled-tetra-cell-condensation-v1',status='ASSEMBLED_NOT_YET_ORACLE_VERIFIED',
            identity=identity,source=source,unscaled=True,full_rows=A.shape[0],retained_rows=len(retained),
            nnz=int(len(data)),interior_graph=graph,local_LU_count=writer.count,
            members=members,recovery=[dict(r,path=str(path/'recovery'/Path(r['path']).name)) for r in writer.receipts],
            build_audit=condensed.build_audit,full_matrix_required_as_input=True,
            factor_free=False,resident_recovery_batch_cells=writer.batch,
            bytes=sum(x['bytes'] for x in members.values())+sum(Path(r['path']).stat().st_size for r in writer.receipts))
        write_json(partial/'manifest.json',m);digest=file_digest(partial/'manifest.json')
        with (partial/'COMMIT').open('w') as f:f.write(digest+'\n');f.flush();os.fsync(f.fileno())
        fd=os.open(partial,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
        os.replace(partial,path)
        fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
        return dict(path=str(path/'manifest.json'),sha256=digest,bytes=m['bytes'],nnz=m['nnz'])
    finally:
        if condensed is not None:condensed.destroy()
        b.destroy();matrix.destroy();gc.collect()


class ExactRecovery:
    """Arbitrary RHS/trace service; loads one saved factor chunk at a time."""
    def __init__(self, receipt, *, identity=None):
        self.receipt=receipt
        p=Path(receipt['path']);self.root=p.parent
        if self.root.name.endswith('.partial') or file_digest(p)!=receipt['sha256'] or (self.root/'COMMIT').read_text().strip()!=receipt['sha256']:
            raise ValueError('condensed manifest/COMMIT hash')
        self.manifest=json.loads(p.read_text())
        if identity is not None and self.manifest['identity']!=identity:raise ValueError('condensed mathematical identity')
        arrays={}
        for name,r in self.manifest['members'].items():
            q=self.root/r['file']
            if q.parent!=self.root or file_digest(q)!=r['sha256']:raise ValueError('condensed member file hash')
            a=np.load(q,mmap_mode='r',allow_pickle=False)
            if list(a.shape)!=r['shape'] or str(a.dtype)!=r['dtype'] or member_digest(a)!=r['member_sha256']:
                raise ValueError('condensed member shape/dtype/hash')
            arrays[name]=a
        self.arrays=arrays;self.retained=arrays['retained'];n=len(self.retained)
        self.matrix=sparse.csr_matrix((arrays['data'],arrays['indices'],arrays['indptr']),shape=(n,n),copy=False)
        self.mapping=np.full(self.manifest['full_rows'],-1,np.int64);self.mapping[self.retained]=np.arange(n)
        self.calls=dict(local_lu_solve=0,trace_action=0)

    def chunks(self):
        for receipt in self.manifest['recovery']:
            a=checked_arrays(receipt)
            for j in range(len(a['interior_offsets'])-1):
                def part(name):
                    return a[name][a[name+'_offsets'][j]:a[name+'_offsets'][j+1]]
                interior,rows,cols=part('interior'),part('rows'),part('cols');ni=len(interior)
                yield interior,rows,cols,part('lu').reshape(ni,ni),part('piv'),part('it').reshape(ni,len(cols)),part('ti').reshape(len(rows),ni),part('ii').reshape(ni,ni)

    def condense_rhs(self,full_rhs):
        r=np.asarray(full_rhs)
        if r.shape!=(self.manifest['full_rows'],):raise ValueError('full arbitrary RHS length')
        out=r[self.retained].copy()
        for i,rows,cols,lu,piv,it,ti,ii in self.chunks():
            out[self.mapping[rows]]-=ti@lu_solve((lu,piv),r[i]);self.calls['local_lu_solve']+=1
        return out

    def apply_trace(self,v):
        if np.asarray(v).shape!=(len(self.retained),):raise ValueError('retained vector length')
        self.calls['trace_action']+=1;return self.matrix@v

    def recover(self,trace_port,full_rhs):
        if np.asarray(trace_port).shape!=(len(self.retained),) or np.asarray(full_rhs).shape!=(self.manifest['full_rows'],):
            raise ValueError('recovery full/retained lengths')
        x=np.empty(self.manifest['full_rows'],np.complex128);x[self.retained]=trace_port
        maximum=0.
        from .scattering_anchor import relative
        for i,rows,cols,lu,piv,it,ti,ii in self.chunks():
            x[i]=lu_solve((lu,piv),full_rhs[i]-it@x[cols]);self.calls['local_lu_solve']+=1
            internal=ii@x[i];trace=it@x[cols]
            maximum=max(maximum,relative(full_rhs[i]-internal-trace,
                np.abs(full_rhs[i])+np.abs(internal)+np.abs(trace)))
        self.last_identity=dict(maximum_cell_operation_scaled=maximum,pass_gate=maximum<=1e-10,
                                original_Aii_retained=True,cells=self.manifest['local_LU_count'])
        if not self.last_identity['pass_gate']:raise ValueError('original local internal recovery identity')
        return x

    def lift_residual(self,r):
        out=np.zeros(self.manifest['full_rows'],np.complex128);out[self.retained]=r;return out
