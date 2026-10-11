"""Bounded, restartable local Galerkin summation, without a fine matrix.

Each deterministic cell block has one atomic receipt. Port terms live in a
separate block. A completed base is consumed instead of its constituent blocks.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy import sparse

from src.runners.task042_shared import write_json
from .bounded_trace_pc import csr_save, csr_load
from .scattering_anchor import save_arrays, relative
from .scattering_anchor_checks import checked_arrays


def packed_cell(service, Z, record):
    cell, _, ids, E, key = record
    z = Z[ids].tocsr()
    columns = np.unique(z.indices)
    d = E @ z[:, columns].toarray()
    return int(cell), columns, np.asarray(d), service.cache[key]['schur']


def local_products(packed, *, batched=False, workspace_limit=2*2**30):
    """Different cells retain their own d, S and global column mapping."""
    if not batched:
        return [(c, cols, d.conj().T @ S @ d) for c, cols, d, S in packed]
    groups = {}
    for row in packed:
        groups.setdefault((row[2].shape, row[3].shape), []).append(row)
    result = []
    for group in groups.values():
        for start in range(0, len(group), 32):
            chunk = group[start:start+32]
            payload = sum(d.nbytes+S.nbytes for _, _, d, S in chunk)
            if 4*payload > workspace_limit:
                raise MemoryError('bounded exact Galerkin batch workspace')
            d = np.stack([r[2] for r in chunk])
            S = np.stack([r[3] for r in chunk])
            values = np.matmul(d.conj().swapaxes(-1,-2), np.matmul(S,d))
            result.extend((r[0],r[1],v) for r,v in zip(chunk,values,strict=True))
    return sorted(result, key=lambda r:r[0])


def contributions_csr(products, size):
    rr=[];cc=[];vv=[]
    for _, cols, values in products:
        if not len(cols): continue
        rr.append(np.repeat(cols,len(cols)))
        cc.append(np.tile(cols,len(cols)))
        vv.append(values.ravel())
    if not vv: return sparse.csr_matrix((size,size),dtype=np.complex128)
    A=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(size,size)).tocsr()
    A.sum_duplicates();A.sort_indices()
    return A


def port_base(service, Z, left, right):
    n0=Z.shape[1]
    C=(Z.conj().T@service.Ctilde)@sparse.diags(right[service.nt:])
    D=sparse.diags(left[service.nt:])@(service.Dtilde@Z)
    H=sparse.csr_matrix(left[service.nt:,None]*service.Htilde*right[None,service.nt:])
    return sparse.bmat([[sparse.csr_matrix((n0,n0),dtype=complex),C],[D,H]],format='csr')


def checked_block(path, identity, cell_ids):
    row=json.loads(Path(path).read_text())
    if row['identity']!=identity or row['cell_ids']!=list(map(int,cell_ids)):
        raise ValueError('Galerkin block input/coverage identity')
    a=checked_arrays(row['matrix'])
    if not np.array_equal(a['cell_ids'],cell_ids):
        raise ValueError('Galerkin exact member coverage')
    if not np.isfinite(a['data']).all(): raise ValueError('Galerkin block nonfinite')
    A=sparse.csr_matrix((a['data'],a['indices'],a['indptr']),shape=tuple(a['shape']))
    return row,A


def paired_products(service,Z,records,folder,journal):
    """One fixed <=64-cell pair; no timing-driven parameter search."""
    if len(records)>64: raise ValueError('fixed Galerkin pairing cap')
    start=time.perf_counter();packed=[packed_cell(service,Z,r) for r in records]
    extraction=time.perf_counter()-start
    start=time.perf_counter();original=local_products(packed)
    original_seconds=time.perf_counter()-start
    start=time.perf_counter();batch=local_products(packed,batched=True)
    batch_seconds=time.perf_counter()-start
    errors=[]
    for a,b in zip(original,batch,strict=True):
        if a[0]!=b[0] or not np.array_equal(a[1],b[1]):raise ValueError('batched cell map mismatch')
        delta=b[2]-a[2]
        errors.append(dict(cell=a[0],columns=len(a[1]),relative=relative(delta,a[2]),
            operation_scaled=relative(delta,np.abs(a[2])+np.abs(b[2]))))
    passed=all(max(r['relative'],r['operation_scaled'])<=1e-10 for r in errors)
    row=dict(pass_gate=passed,errors=errors,extraction_seconds=extraction,
        original_multiply_seconds=original_seconds,batch_multiply_seconds=batch_seconds,
        selected='batch' if passed and batch_seconds<original_seconds else 'original',
        parameter_search=False,new_global_actions=0)
    write_json(Path(folder)/'fixed_batch_pair.json',row)
    journal.event('fixed_batched_Galerkin_pair',**row)
    return row


def durable_base(service,Z,left,right,folder,journal,*,identity,require_live,
                 batched=False,block_cells=256):
    if not 1<=block_cells<=256:raise ValueError('deterministic cell block cap')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cells=sorted(service.cell_records,key=lambda r:r[0]);ids=[int(r[0]) for r in cells]
    if ids!=list(range(service.manifest['cells'])):raise ValueError('exact all-cell inventory')
    ip=folder/'identity.json'
    if ip.exists() and json.loads(ip.read_text())!=identity:raise ValueError('base checkpoint identity changed')
    if not ip.exists():write_json(ip,identity)
    manifest_path=folder/'manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        if manifest['identity']!=identity or manifest['cell_ids']!=ids or manifest['port_aggregations']!=1:
            raise ValueError('completed base coverage/identity')
        start=time.perf_counter();A=csr_load(manifest['matrix'])
        journal.event('completed_base_checkpoint_read',seconds=time.perf_counter()-start)
        return A,manifest
    size=Z.shape[1]+service.m;A=sparse.csr_matrix((size,size),dtype=np.complex128)
    blocks=[];new_count=0;reused_count=0;timings=dict(extract=0.,multiply=0.,assemble=0.,write=0.,read=0.)
    for start in range(0,len(cells),block_cells):
        require_live();block=cells[start:start+block_cells];blockids=np.array([r[0] for r in block],np.int64)
        rp=folder/f'block{start//block_cells:04d}.json'
        if rp.exists():
            began=time.perf_counter();row,B=checked_block(rp,identity,blockids)
            timings['read']+=time.perf_counter()-began;reused_count+=1
        else:
            began=time.perf_counter();packed=[packed_cell(service,Z,r) for r in block]
            timings['extract']+=time.perf_counter()-began
            began=time.perf_counter();products=local_products(packed,batched=batched)
            timings['multiply']+=time.perf_counter()-began
            began=time.perf_counter();B=contributions_csr(products,size)
            timings['assemble']+=time.perf_counter()-began
            began=time.perf_counter();receipt=csr_save(rp.with_suffix('.npz'),B,cell_ids=blockids)
            row=dict(identity=identity,cell_ids=blockids.tolist(),matrix=receipt,
                zero_cells=[c for c,cols,_,_ in packed if not len(cols)],
                method='exact_batch' if batched else 'exact_cell',port_aggregations=0)
            write_json(rp,row);timings['write']+=time.perf_counter()-began;new_count+=1
            del packed,products
        A=A+B;blocks.append(dict(path=str(rp),sha256=hashlib.sha256(rp.read_bytes()).hexdigest(),matrix=row['matrix']))
        journal.event('durable_FE_base_block_committed',completed=len(blocks),cells=start+len(block),
            new_blocks=new_count,reused_blocks=reused_count,timings=timings)
    pp=folder/'port.json'
    if pp.exists():
        port,P=checked_block(pp,identity,np.empty(0,np.int64))
        if port['port_aggregations']!=1:raise ValueError('base port multiplicity')
    else:
        began=time.perf_counter();P=port_base(service,Z,left,right)
        timings['assemble']+=time.perf_counter()-began
        receipt=csr_save(folder/'port.npz',P,cell_ids=np.empty(0,np.int64))
        port=dict(identity=identity,cell_ids=[],matrix=receipt,port_aggregations=1)
        write_json(pp,port)
    A=A+P
    matrix=csr_save(folder/'base_complete.npz',A)
    manifest=dict(identity=identity,cell_ids=ids,blocks=blocks,port=port,matrix=matrix,
        port_aggregations=1,new_blocks=new_count,reused_blocks=reused_count,timings=timings,
        whole_base_or_blocks_exclusive=True,global_fine_matrix_formations=0)
    # Final committed base is independently reopened before consumption.
    reopened=csr_load(matrix)
    if relative(reopened.data-A.data,A.data)>0:raise ValueError('base atomic readback changed')
    write_json(manifest_path,manifest)
    return reopened,manifest
