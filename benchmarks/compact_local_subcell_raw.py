"""One bounded, byte-exact archive dedup; never changes a failed packet."""
import hashlib
import json
import os
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers import local_subcell_scope as scope


def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(256*1024),b''):h.update(block)
    return h.hexdigest()


def link_identical_copy(keeper,copy):
    keeper,copy=Path(keeper),Path(copy)
    if copy.is_symlink():raise ValueError('one archive transaction per original copy')
    a,b=keeper.stat(),copy.stat()
    if a.st_size!=b.st_size:raise ValueError('archive unequal sizes')
    ha,hb=file_hash(keeper),file_hash(copy)
    if ha!=hb:raise ValueError('archive unequal byte hashes')
    tmp=copy.with_name('.'+copy.name+'.readonly-link')
    if tmp.exists() or tmp.is_symlink():raise ValueError('archive pending transaction already exists')
    tmp.symlink_to(os.path.relpath(keeper,copy.parent))
    if file_hash(tmp)!=hb:raise ValueError('archive link bytes differ')
    os.replace(tmp,copy)
    if file_hash(copy)!=hb or keeper.stat().st_ino!=a.st_ino:raise ValueError('archive commit identity')
    return dict(keeper=str(keeper),copy=str(copy),sha256=hb,bytes=a.st_size,
        keeper_inode_unchanged=a.st_ino,original_copy_inode=b.st_ino,
        original_copy_mtime_ns=b.st_mtime_ns,failed_file_unchanged=True,
        copy_readonly_reference=True,scope='same V60 only; after scientific producer exit')


def main():
    scope.window.guard_worker_parent()
    if scope.window.ledger()['active']['role']!='archive':raise ValueError('archive-only consumer')
    old=scope.ARTIFACT/'task042_v60_local_trace6_interior7_20261007T170956335399Z/phase_reference_raw'
    new=scope.ARTIFACT/'task042_v60_local_trace6_interior7_20261007T173429559910Z/phase_reference_raw'
    out=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);rows=[];rejected=[]
    files=sorted(new.glob('*.npz'))
    if len(files)!=26:raise ValueError('frozen C67 26 raw-class inventory')
    for p in files:
        q=old/p.name
        if not q.is_file():rejected.append(dict(path=str(p),reason='no old counterpart'));continue
        try:r=link_identical_copy(q,p)
        except ValueError as e:rejected.append(dict(path=str(p),reason=str(e)));continue
        rows.append(r)
        write_json(out/'archive_receipt.json',dict(rows=rows,rejected=rejected,
            no_scientific_bytes_changed=True,no_failed_file_changed=True,
            source=os.environ.get('TASK042_PREPARATION_SCOPE')))
    print(json.dumps(dict(status='BYTE_IDENTICAL_SUCCESS_COPIES_ARCHIVED',copies=len(rows),
        normalized_filename_bytes_released=sum(x['bytes'] for x in rows),rejected=len(rejected))))


if __name__=='__main__':main()
