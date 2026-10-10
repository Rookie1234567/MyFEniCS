"""Cell-formed tetra Schur packets, independent of any global body matrix.

Each packet keeps the actual non-Hermitian interior blocks and the sparse
Hermitian MPC expansion. A local-only reader can apply or recover arbitrary
retained vectors without loading the separately sealed global Schur matrix.
"""
import gc
import json
import os
import warnings
from collections import OrderedDict
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

from src.runners.task042_shared import write_json
from .scattering_anchor import relative, save_arrays
from .scattering_anchor_checks import checked_arrays
from .tetra_body_checkpoint import file_digest, member_digest
from .exact_tetra_condensation import _write_array, tetra_interiors


def local_elimination(raw, interior):
    """Full complex raw tensor first; no adjoint assumption on off-diagonals."""
    i=np.asarray(interior,np.int64)
    t=np.setdiff1d(np.arange(len(raw)),i)
    ii=raw[np.ix_(i,i)];it=raw[np.ix_(i,t)];ti=raw[np.ix_(t,i)]
    with warnings.catch_warnings():
        warnings.simplefilter('error',LinAlgWarning)
        lu,piv=lu_factor(ii,check_finite=True)
    response=lu_solve((lu,piv),it,check_finite=True)
    if not np.isfinite(response).all():raise ValueError('nonfinite local interior response')
    return dict(ii=ii,it=it,ti=ti,lu=lu,piv=piv,schur=raw[np.ix_(t,t)]-ti@response)


def partition(setup):
    cells=tetra_interiors(setup);n=setup['P'].shape[1];m=setup['spec']['complete_modes']
    interior=np.vstack(cells);retained=np.setdiff1d(np.arange(n+m,dtype=np.int64),interior.ravel())
    mapping=np.full(n+m,-1,np.int64);mapping[retained]=np.arange(len(retained))
    loc_i=np.asarray(setup['V'].element.basix_element.entity_dofs[3][0],np.int64)
    loc_t=np.setdiff1d(np.arange(140),loc_i)
    active=[];expansions=[]
    for c in range(len(cells)):
        native=np.asarray(setup['V'].dofmap.cell_dofs(c))[loc_t]
        rows=setup['P'][native].tocsr();compact=mapping[rows.indices]
        if np.any(compact<0):raise ValueError('trace expansion contains a cell interior')
        ids=np.unique(compact);E=sparse.csr_matrix((rows.data,np.searchsorted(ids,compact),rows.indptr),shape=(110,len(ids)))
        if not E.nnz or np.any(ids>=len(retained)-m):raise ValueError('actual MPC trace support')
        active.append(ids);expansions.append(E)
    return interior,retained,tuple(active),tuple(expansions),loc_i


def _seal(folder,manifest):
    write_json(folder/'manifest.json',manifest);digest=file_digest(folder/'manifest.json')
    with (folder/'COMMIT').open('w') as f:f.write(digest+'\n');f.flush();os.fsync(f.fileno())
    fd=os.open(folder,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    return dict(path=str(folder/'manifest.json'),sha256=digest,bytes=manifest['bytes'])


def _read_manifest(receipt):
    p=Path(receipt['path']);root=p.parent
    if root.name.endswith('.partial') or file_digest(p)!=receipt['sha256'] or (root/'COMMIT').read_text().strip()!=receipt['sha256']:
        raise ValueError('cell packet manifest/COMMIT hash')
    return root,json.loads(p.read_text())


def _load_members(root,manifest):
    result={}
    for name,r in manifest['members'].items():
        p=root/r['file']
        if p.parent!=root or file_digest(p)!=r['sha256']:raise ValueError('cell packet member file hash')
        a=np.load(p,mmap_mode='r',allow_pickle=False)
        if list(a.shape)!=r['shape'] or str(a.dtype)!=r['dtype'] or member_digest(a)!=r['member_sha256']:
            raise ValueError('cell packet member identity')
        result[name]=a
    return result


class LocalTracePacket:
    """Loads local factors and boundary only: no global K or S code path."""
    def __init__(self,receipt,*,identity=None,cache_bytes=4*2**30):
        self.receipt=receipt;self.root,self.manifest=_read_manifest(receipt)
        if identity is not None and self.manifest['identity']!=identity:raise ValueError('cell packet live mathematical identity')
        a=self.arrays=_load_members(self.root,self.manifest)
        self.retained=a['retained'];self.full_rows=len(a['full_rhs']);self.n=self.manifest['full_FE_rows'];self.m=self.manifest['ports']
        self.nt=len(self.retained)-self.m
        self.C=sparse.csr_matrix((a['C_data'],a['C_indices'],a['C_indptr']),shape=(self.n,self.m),copy=False)
        self.DT=sparse.csr_matrix((a['DT_data'],a['DT_indices'],a['DT_indptr']),shape=(self.n,self.m),copy=False)
        self.H=a['H'];self.cache=OrderedDict();self.cache_bytes=cache_bytes;self.live_cache_bytes=0
        self.calls=dict(trace_action=0,local_lu_solve=0,global_K_reads=0,global_S_reads=0,global_FE_matrix_formations=0,factors=0,
                        class_reads=0,class_bytes_read=0,boundary_C=0,boundary_D=0)

    def local(self,key):
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        r=self.manifest['classes'][key];a=checked_arrays(r);size=sum(v.nbytes for v in a.values())
        self.calls['class_reads']+=1;self.calls['class_bytes_read']+=Path(r['path']).stat().st_size
        while self.cache and self.live_cache_bytes+size>self.cache_bytes:
            _,old=self.cache.popitem(last=False);self.live_cache_bytes-=sum(v.nbytes for v in old.values())
        if size>self.cache_bytes:raise MemoryError('one local class exceeds declared exact cache')
        self.cache[key]=a;self.live_cache_bytes+=size;return a

    def cells(self):
        for receipt in self.manifest['maps']:
            a=checked_arrays(receipt)
            for j,c in enumerate(a['cells']):
                def part(name):return a[name][a[name+'_offsets'][j]:a[name+'_offsets'][j+1]]
                ids=part('active');E=sparse.csr_matrix((part('E_data'),part('E_indices'),part('E_indptr')),shape=(110,len(ids)))
                yield int(c),a['interior'][j],ids,E,self.local(str(a['class_keys'][j]))

    def _interior_ports(self,i):
        # Sparse row reads preserve every stored contribution; no drop tolerance.
        Ci=self.C[i].tocsr();Di=self.DT[i].T.tocsr()
        ports=np.union1d(Ci.indices,Di.nonzero()[0])
        return ports,Ci[:,ports].toarray(),Di[ports].toarray()

    def solve_local(self,a,v):
        self.calls['local_lu_solve']+=1;return lu_solve((a['lu'],a['piv']),v)

    def condense_rhs(self,r):
        r=np.asarray(r)
        if r.shape!=(self.full_rows,):raise ValueError('cell packet full RHS length')
        out=r[self.retained].copy()
        for _,i,ids,E,a in self.cells():
            h=self.solve_local(a,r[i]);out[ids]-=E.conj().T@(a['ti']@h)
            ports,_,Di=self._interior_ports(i)
            if len(ports):out[self.nt+ports]+=Di@h
        return out

    def apply_trace(self,t):
        t=np.asarray(t)
        if t.shape!=(len(self.retained),):raise ValueError('cell packet trace/port length')
        self.calls['trace_action']+=1
        body=np.zeros(self.n,np.complex128);body[self.retained[:self.nt]]=t[:self.nt]
        out=np.zeros_like(t);out[:self.nt]=(self.C@t[self.nt:])[self.retained[:self.nt]]
        out[self.nt:]=-self.DT.T@body+self.H*t[self.nt:]
        self.calls['boundary_C']+=1;self.calls['boundary_D']+=1
        for _,i,ids,E,a in self.cells():
            v=E@t[ids];out[ids]+=E.conj().T@(a['schur']@v)
            ports,Ci,Di=self._interior_ports(i)
            if len(ports):
                extra=self.solve_local(a,Ci@t[self.nt+ports])
                out[ids]-=E.conj().T@(a['ti']@extra)
                out[self.nt+ports]+=Di@self.solve_local(a,a['it']@v+Ci@t[self.nt+ports])
        return out

    def recover(self,t,r):
        if np.asarray(t).shape!=(len(self.retained),) or np.asarray(r).shape!=(self.full_rows,):raise ValueError('packet recovery lengths')
        x=np.empty(self.full_rows,np.complex128);x[self.retained]=t;maximum=0.
        for _,i,ids,E,a in self.cells():
            trace=a['it']@(E@t[ids]);ports,Ci,_=self._interior_ports(i)
            coupling=Ci@t[self.nt+ports] if len(ports) else np.zeros(len(i),complex)
            x[i]=self.solve_local(a,r[i]-trace-coupling)
            internal=a['ii']@x[i]
            maximum=max(maximum,relative(r[i]-internal-trace-coupling,np.abs(r[i])+np.abs(internal)+np.abs(trace)+np.abs(coupling)))
        self.last_identity=dict(maximum_cell_operation_scaled=maximum,pass_gate=maximum<=1e-10,cells=self.manifest['cells'])
        if not self.last_identity['pass_gate']:raise ValueError('packet original internal recovery identity')
        return x

    def lift_residual(self,r):
        out=np.zeros(self.full_rows,np.complex128);out[self.retained]=r;return out

    def release_cache(self):self.cache.clear();self.live_cache_bytes=0;gc.collect()


class RetainedPacket(LocalTracePacket):
    """Explicit solver reader attaches the separately committed unscaled S."""
    def __init__(self,local_receipt,matrix_receipt,**kw):
        super().__init__(local_receipt,**kw)
        root,m=_read_manifest(matrix_receipt)
        if m['local_packet']!=local_receipt:raise ValueError('S/local packet dependency')
        a=self.matrix_arrays=_load_members(root,m)
        if not np.array_equal(a['retained'],self.retained):raise ValueError('S/packet retained order')
        self.matrix=sparse.csr_matrix((a['data'],a['indices'],a['indptr']),shape=(len(self.retained),)*2,copy=False)
        self.matrix_receipt=matrix_receipt;self.calls['global_S_reads']+=1

    def release_matrix(self):
        self.matrix=None;self.matrix_arrays.clear();gc.collect()


def build(setup,boundary,rhs,kernel,folder,journal,*,identity,source):
    """Local elimination and ADD assembly; never creates full body K or A."""
    from petsc4py import PETSc
    from . import independent_tetra_reference as core
    from .hcurl_assembly_time_condensation import _distributed_trace_preallocation
    folder=Path(folder);packet=folder/'local_packet';packet.mkdir(exist_ok=False)
    (packet/'classes').mkdir();(packet/'maps').mkdir()
    with journal.measured('actual_tetra_partition_and_support'):
        internal,retained,active,expansions,loc_i=partition(setup)
        C,D,H=core.boundary_matrices(setup,boundary);DT=D.T.tocsr();n=C.shape[0];m=len(H);nt=len(retained)-m
        owner=np.full(n,-1,np.int32)
        for c,i in enumerate(internal):owner[i]=c
        incident=np.unique(np.r_[C.nonzero()[0],D.nonzero()[1]])
        # All cells containing actual native boundary support; includes shared
        # entities and tiny interior couplings, and never assumes C == D^H.
        touched=set(incident.tolist());support_cells=np.asarray([c for c in range(len(internal))
            if any(int(v) in touched for v in setup['P'][setup['V'].dofmap.cell_dofs(c)].indices)],np.int64)
        d,o,graph=_distributed_trace_preallocation(setup['mesh'].comm,active,active_counts=(nt,),appended_global_rows=m,
            appended_support_owned_cell_groups=(support_cells,),appended_support_group_by_row=(0,)*m,dense_appended_block=True)
    journal.allocation('direct_retained_AIJ',dict(matrix_payload_bytes=int(d.sum())*24+len(d)*16+4*2**30,workspace_bytes=2*2**30))
    journal.event('actual_retained_graph_admission',graph=graph,preallocation_entries=int(d.sum()),full_K_formed=0,full_A_formed=0)
    S=PETSc.Mat().createAIJ(size=(len(retained),)*2,nnz=d,comm=PETSc.COMM_SELF)
    S.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,True)
    rows=retained[:nt];mapping=np.full(n,-1,np.int64);mapping[rows]=np.arange(nt)
    # Port entries and the global physical load are inserted exactly once.
    for j,row in enumerate(rows):
        a,z=C.indptr[row:row+2]
        for first in range(a,z,32):
            last=min(first+32,z)
            S.setValues([j],nt+C.indices[first:last],C.data[first:last],addv=PETSc.InsertMode.ADD_VALUES)
    for j in range(m):
        a,z=D.indptr[j: j+2];cols=mapping[D.indices[a:z]];good=cols>=0
        if good.any():S.setValues([nt+j],cols[good],-D.data[a:z][good],addv=PETSc.InsertMode.ADD_VALUES)
        S.setValue(nt+j,nt+j,H[j],addv=PETSc.InsertMode.ADD_VALUES)
    reduced_rhs=rhs[retained].copy();classes={};maps=[];pending=[];cache=OrderedDict();cache_size=0;cache_peak=0;lu_count=0

    def get_class(c):
        nonlocal cache_size,cache_peak,lu_count
        key=kernel.key(c)
        if key in cache:cache.move_to_end(key);return key,cache[key]
        if key in classes:a=checked_arrays(classes[key])
        else:
            a=local_elimination(kernel.tensor(c,translated=True),loc_i);lu_count+=1
            classes[key]=save_arrays(packet/'classes'/(key+'.npz'),**a)
        size=sum(v.nbytes for v in a.values())
        while cache and cache_size+size>4*2**30:
            _,old=cache.popitem(last=False);cache_size-=sum(v.nbytes for v in old.values())
        cache[key]=a;cache_size+=size;cache_peak=max(cache_peak,cache_size)
        return key,a

    def flush():
        if not pending:return
        payload={'cells':np.asarray([p[0] for p in pending],np.int64),'interior':np.vstack([p[1] for p in pending]),
                 'class_keys':np.asarray([p[4] for p in pending],dtype='U64')}
        for name,j in [('active',2),('E_data',3),('E_indices',3),('E_indptr',3)]:
            vals=[p[j] if name=='active' else getattr(p[3],name[2:]) for p in pending]
            payload[name]=np.concatenate(vals);payload[name+'_offsets']=np.r_[0,np.cumsum([len(v) for v in vals])].astype(np.int64)
        maps.append(save_arrays(packet/'maps'/f'chunk_{len(maps):04d}.npz',**payload));pending.clear()
        # This log marks packet cells, not a fictitious durable PETSc ADD state.
        write_json(packet/'progress.json',dict(packet_cells_complete=sum(len(checked_arrays(r)['cells']) for r in maps[-1:])+64*(len(maps)-1),
            last_map=maps[-1],global_matrix_checkpoint_complete=False,recovery_rule='replay sealed local cells once into new empty ADD matrix'))

    try:
        with journal.measured('cell_kernel_elimination_direct_retained_ADD'):
            for c,(i,ids,E) in enumerate(zip(internal,active,expansions)):
                key,a=get_class(c);dense=E.toarray()
                S.setValues(ids,ids,dense.conj().T@a['schur']@dense,addv=PETSc.InsertMode.ADD_VALUES)
                h=lu_solve((a['lu'],a['piv']),rhs[i]);reduced_rhs[ids]-=dense.conj().T@a['ti']@h
                Ci=C[i].tocsr();Di=DT[i].T.tocsr();ports=np.union1d(Ci.indices,Di.nonzero()[0])
                if len(ports):
                    ci=Ci[:,ports].toarray();di=Di[ports].toarray()
                    vi=lu_solve((a['lu'],a['piv']),a['it'])
                    S.setValues(nt+ports,ids,di@vi@dense,addv=PETSc.InsertMode.ADD_VALUES)
                    for first in range(0,len(ports),32):
                        last=min(first+32,len(ports));vc=lu_solve((a['lu'],a['piv']),ci[:,first:last])
                        S.setValues(ids,nt+ports[first:last],-dense.conj().T@a['ti']@vc,addv=PETSc.InsertMode.ADD_VALUES)
                        S.setValues(nt+ports,nt+ports[first:last],di@vc,addv=PETSc.InsertMode.ADD_VALUES)
                    reduced_rhs[nt+ports]+=di@h
                pending.append((c,i,ids,E,key))
                if len(pending)==64:flush()
                if (c+1)%512==0:journal.event('tetra_retained_cell_progress',completed=c+1,total=len(internal),classes=len(classes),cache_bytes=cache_size)
            flush()
            S.assemblyBegin(PETSc.Mat.AssemblyType.FINAL);S.assemblyEnd(PETSc.Mat.AssemblyType.FINAL)
        members={}
        arrays=dict(retained=retained,full_rhs=rhs,H=H,C_data=C.data,C_indices=C.indices,C_indptr=C.indptr,
                    DT_data=DT.data,DT_indices=DT.indices,DT_indptr=DT.indptr)
        for name,value in arrays.items():members[name]=_write_array(packet,name,value)
        pm=dict(schema='assembly-time-tetra-local-packet-v1',identity=identity,source=source,full_FE_rows=n,ports=m,cells=len(internal),
            full_rows=n+m,retained_rows=len(retained),members=members,classes=classes,maps=maps,kernel=kernel.identity,
            local_LU_count=lu_count,exact_cache_peak_bytes=cache_peak,cache_limit_bytes=4*2**30,cell_batch_max=64,
            port_column_batch_max=32,
            full_body_assemble_matrix=0,full_K_reads=0,full_A_materializations=0,old_recovery_reads=0,
            bytes=sum(r['bytes'] for r in members.values())+sum(Path(r['path']).stat().st_size for r in list(classes.values())+maps))
        local_receipt=_seal(packet,pm)
        matrix_dir=folder/'retained_S';matrix_dir.mkdir(exist_ok=False);ip,ix,values=S.getValuesCSR()
        matrix_members={name:_write_array(matrix_dir,name,a) for name,a in dict(data=values,indices=ix,indptr=ip,rhs=reduced_rhs,retained=retained).items()}
        sm=dict(schema='assembly-time-tetra-retained-S-v1',local_packet=local_receipt,identity=identity,source=source,members=matrix_members,
                nnz=len(values),rows=len(retained),unscaled=True,graph=graph,bytes=sum(r['bytes'] for r in matrix_members.values()))
        matrix_receipt=_seal(matrix_dir,sm)
        return local_receipt,matrix_receipt
    finally:S.destroy();cache.clear();gc.collect()
