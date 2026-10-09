"""Atomic, unscaled CSR checkpoint with streamed bytes and explicit identity.

Assembly and independent mathematical verification are different receipts.
The original sealed ASSEMBLED_NOT_YET_ORACLE_VERIFIED manifest is immutable.
"""
import hashlib
import json
import os
from pathlib import Path
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json


def file_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*2**20),b''):h.update(block)
    return h.hexdigest()


def member_digest(array):
    a=np.asarray(array)
    if not a.flags.c_contiguous or a.dtype.hasobject:raise ValueError('checkpoint array must be contiguous numeric')
    h=hashlib.sha256(a.dtype.str.encode()+str(a.shape).encode())
    raw=memoryview(a).cast('B')
    for i in range(0,len(raw),8*2**20):h.update(raw[i:i+8*2**20])
    return h.hexdigest()


def save_checkpoint(path,K,identity,arrays,*,form,source,boundary):
    path=Path(path)
    if path.exists():raise FileExistsError('sealed body checkpoint already exists; reload it')
    partial=path.with_name(path.name+'.partial')
    partial.mkdir(parents=True,exist_ok=False)
    K=K.tocsr(copy=False)
    payload=dict(data=K.data,indices=K.indices,indptr=K.indptr,shape=np.asarray(K.shape,np.int64),**arrays)
    members={}
    for name,value in payload.items():
        a=np.asarray(value)
        if not a.flags.c_contiguous:a=np.ascontiguousarray(a)
        p=partial/(name+'.npy')
        with p.open('wb') as f:np.save(f,a,allow_pickle=False);f.flush();os.fsync(f.fileno())
        members[name]=dict(file=p.name,sha256=file_digest(p),array_sha256=member_digest(a),shape=list(a.shape),dtype=str(a.dtype),bytes=p.stat().st_size)
    manifest=dict(schema='Task042-unscaled-tetra-body-CSR-v1',status='ASSEMBLED_NOT_YET_ORACLE_VERIFIED',
        unscaled=True,static_condensation=False,identity=identity,form=form,source=source,boundary=boundary,
        nnz=K.nnz,shape=list(K.shape),members=members,bytes=sum(m['bytes'] for m in members.values()))
    write_json(partial/'manifest.json',manifest)
    digest=file_digest(partial/'manifest.json')
    with (partial/'COMMIT').open('w') as f:f.write(digest+'\n');f.flush();os.fsync(f.fileno())
    fd=os.open(partial,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    os.replace(partial,path)
    fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    return dict(path=str(path/'manifest.json'),sha256=digest,status=manifest['status'],bytes=manifest['bytes'],nnz=K.nnz)


def body_fingerprint(identity):
    """Exact body identity; mode inventory and its augmented row count are separate.

    Actual geometry/tags/MPC/basis arrays, material, carrier, degree and body
    quadrature remain bound. This is not permission to skip a manifest check.
    """
    body=dict(identity)
    physical=identity['physical']
    body['physical']={k:physical[k] for k in ('geometry','materials','incidence')}
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def load_checkpoint(receipt,identity,*,allow_mode_change=False):
    p=Path(receipt['path']);root=p.parent
    if root.name.endswith('.partial') or not (root/'COMMIT').is_file():raise ValueError('uncommitted body checkpoint')
    sha=file_digest(p)
    if sha!=receipt['sha256'] or (root/'COMMIT').read_text().strip()!=sha:raise ValueError('body checkpoint manifest hash')
    m=json.loads(p.read_text())
    same=m['identity']==identity
    if not same and allow_mode_change:
        same=body_fingerprint(m['identity'])==body_fingerprint(identity)
    if not same or m.get('unscaled') is not True or m.get('static_condensation') is not False:
        raise ValueError('body checkpoint mathematical identity')
    arrays={}
    for name,item in m['members'].items():
        q=root/item['file']
        if q.parent!=root or file_digest(q)!=item['sha256']:raise ValueError('body checkpoint file hash')
        a=np.load(q,mmap_mode='r',allow_pickle=False)
        if list(a.shape)!=item['shape'] or str(a.dtype)!=item['dtype'] or member_digest(a)!=item['array_sha256']:
            raise ValueError('body checkpoint member hash/shape/dtype')
        arrays[name]=a
    shape=tuple(int(v) for v in arrays['shape'])
    K=sparse.csr_matrix((arrays['data'],arrays['indices'],arrays['indptr']),shape=shape,copy=False)
    if K.nnz!=m['nnz'] or list(shape)!=m['shape']:raise ValueError('body checkpoint CSR inventory')
    return K,m,arrays


def qualification_receipt(receipt,errors,arrays,source,path):
    if len(errors)!=2 or not all(np.isfinite(e) and e<=1e-10 for e in errors):raise ValueError('two original action witnesses required')
    # A separate new receipt never changes the original assembled manifest.
    value=dict(status='ORIGINAL_ACTION_VERIFIED',checkpoint=receipt,errors=errors,arrays=arrays,source=source)
    write_json(path,value)
    return dict(path=str(path),sha256=file_digest(path))
