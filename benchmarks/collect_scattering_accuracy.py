"""Scalar/hash-only collector; no operator, FE reconstruction or factor."""
import hashlib
import json
import os
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers.scattering_accuracy_scope import ROOT,ARTIFACT,STAGES,stage,window


def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def collect():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    rows=[]
    for role in STAGES:
        pointer=ARTIFACT/(role+'.json')
        if not pointer.exists():rows.append(dict(stage=role,status='not_run'));continue
        r=stage(role);rows.append(dict(stage=role,status=r['status'],source=r['source_sha'],worker_seconds=r['elapsed_worker_seconds'],
            pointer=json.loads(pointer.read_text())))
    write_json(out/'stage_index_v50.json',dict(rows=rows,window=window.snapshot(),old_ledgers_reopened=False))
    manifest=[]
    for base in (ROOT/'tmp/task042/v50',ARTIFACT):
        for p in sorted(base.rglob('*')):
            if not p.is_file():continue
            if p.is_relative_to(folder) and 'records' in p.relative_to(folder).parts:continue
            manifest.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=digest(p)))
    write_json(out/'raw_index_v50.json',dict(files=manifest,scope='V50 only; immutable older sources linked not copied'))
    print(json.dumps(dict(status='COMPLETED',records=str(out),stages=len(rows))))


if __name__=='__main__':collect()
