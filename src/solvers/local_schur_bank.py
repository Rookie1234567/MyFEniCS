"""Hash-bound local Schur bank: one readonly block per exact class.

This interface applies saved local matrices without reloading local factors,
building a global matrix, or recovering the full interior field.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays,array_hash
from .scattering_anchor_checks import checked_arrays


def schur_member(receipt):
    p=Path(receipt['path'])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('local Schur class file identity')
    with np.load(p,allow_pickle=False) as pack:
        S=np.array(pack['macro_schur'],copy=True)
    member=receipt['members']['macro_schur']
    if list(S.shape)!=member['shape'] or str(S.dtype)!=member['dtype'] or array_hash(S)!=member['sha256']:raise ValueError('local Schur member identity')
    if S.shape[0]!=S.shape[1] or S.dtype!=np.complex128 or not np.all(np.isfinite(S)):raise ValueError('local Schur complete finite block')
    S.setflags(write=False);return S


class SavedLocalSchurAction:
    def __init__(self,manifest,*,source_sha,manifest_sha256,trace_rows,cell_count):
        path=Path(manifest)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest_sha256:raise ValueError('local Schur manifest identity')
        record=json.loads(path.read_text())
        if record['source_sha']!=source_sha or len(source_sha)!=40:raise ValueError('local Schur live consumer producer binding')
        if record['trace_rows']!=trace_rows or record['cell_count']!=cell_count:raise ValueError('local Schur live dimensions')
        if [r['cell'] for r in record['cells']]!=list(range(cell_count)):raise ValueError('local Schur canonical cell inventory')
        self.nt=record['trace_rows'];self.rows=[];self.blocks={};self.calls=0
        for row in record['cells']:
            cls=row['class'];receipt=record['classes'][cls]
            if cls not in self.blocks:self.blocks[cls]=schur_member(receipt)
            a=checked_arrays(row['map']);ids=a['active_rows'];shape=tuple(a['shape'])
            E=sparse.csr_matrix((a['data'],a['indices'],a['indptr']),shape=shape)
            if len(np.unique(ids))!=len(ids) or len(ids)!=shape[1] or np.any(ids<0) or np.any(ids>=self.nt) or shape[0]!=len(self.blocks[cls]):raise ValueError('local Schur cell map inventory')
            for value in (E.data,E.indices,E.indptr,ids):value.setflags(write=False)
            self.rows.append((ids,E,cls))
        if len(self.rows)!=record['cell_count']:raise ValueError('local Schur complete cell inventory')
        self.owner_payload_bytes=sum(x.nbytes for x in self.blocks.values())+sum(sum(v.nbytes for v in (E.data,E.indices,E.indptr,ids)) for ids,E,cls in self.rows)
    def apply(self,t):
        t=np.asarray(t)
        if t.shape!=(self.nt,) or not np.all(np.isfinite(t)):raise ValueError('local Schur complete trace vector')
        result=np.zeros(self.nt,complex)
        for ids,E,cls in self.rows:np.add.at(result,ids,E.conj().T@(self.blocks[cls]@(E@t[ids])))
        self.calls+=1;return result


def save_bank(mapping,class_packets,responses,folder,source_sha):
    folder=Path(folder);folder.mkdir();classes={};rows=[]
    for c,(response,(ids,E,_),T) in enumerate(zip(responses,mapping.data,mapping.transforms,strict=True)):
        packet=class_packets[id(response)];key=packet['sha256'];classes[key]=packet
        Ec=sparse.csr_matrix(T@E);Ec.sum_duplicates();Ec.sort_indices()
        receipt=save_arrays(folder/(str(c)+'.npz'),active_rows=np.asarray(ids),shape=np.asarray(Ec.shape),data=Ec.data,indices=Ec.indices,indptr=Ec.indptr)
        rows.append(dict(cell=c,map=receipt,**{'class':key}))
    manifest=folder/'manifest.json'
    write_json(manifest,dict(schema='local-schur-bank.v1',source_sha=source_sha,trace_rows=mapping.nt,cell_count=len(rows),classes=classes,cells=rows,
        factor_reload=False,global_matrix=False,conjugate_dual=True,scope='body only; DtN/port remain the separate original interface'))
    return dict(path=str(manifest),sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),source_sha=source_sha)
