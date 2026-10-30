"""One sparse PETSc trace/aux checkpoint before factor admission; no dense A."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import time

FAILED_CHECKPOINT_ROOTS=[]


def _sha(path):
    h=sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def _record(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file():raise RuntimeError('regular checkpoint file required')
    return {'file':p.name,'bytes':p.stat().st_size,'sha256':_sha(p)}


def _verify_matrix(path,rows,nnz,matrix):
    import numpy as np
    expected=16+4*rows+20*nnz
    if path.stat().st_size!=expected:raise RuntimeError('PETSc I32/C128 matrix file length')
    digest=sha256(np.asarray([rows,rows],dtype='<i8').tobytes());zeros=0;maxrow=0
    with path.open('rb') as cols,path.open('rb') as vals:
        if struct.unpack('>4i',cols.read(16))!=(1211216,rows,rows,nnz):raise RuntimeError('matrix binary header')
        counts=np.frombuffer(cols.read(4*rows),dtype='>i4')
        if np.any(counts<0) or int(counts.astype(np.int64).sum())!=nnz:raise RuntimeError('matrix row counts')
        vals.seek(16+4*rows+4*nnz)
        for row,count in enumerate(counts):
            n=int(count);maxrow=max(maxrow,n)
            c=np.frombuffer(cols.read(4*n),dtype='>i4');v=np.frombuffer(vals.read(16*n),dtype='>c16')
            if len(c)!=n or len(v)!=n or not np.isfinite(v).all() or np.any(c<0) or np.any(c>=rows) or (n>1 and np.any(c[1:]<=c[:-1])):
                raise RuntimeError('matrix finite/sorted/column range readback')
            # petsc4py 3.25.6 getRow copies out and internally calls
            # MatRestoreRow; there is no Python restoreRow method to guess.
            live_cols,live_values=matrix.getRow(row)
            if not np.array_equal(c,live_cols) or v.astype('<c16').tobytes()!=np.asarray(live_values,dtype='<c16').tobytes():
                raise RuntimeError('binary matrix row differs from the actual live operator')
            zeros+=int(np.count_nonzero(v==0))
            digest.update(np.asarray([row,n],dtype='<i8').tobytes());digest.update(c.astype('<i4').tobytes());digest.update(v.astype('<c16').tobytes())
    return {'rows':rows,'cols':rows,'stored_nnz':nnz,'max_row_nnz':maxrow,'stored_zeros':zeros,
            'canonical_row_sha256':digest.hexdigest(),'every_row_bitwise_equal_to_live_matrix':True,'encoding':'shape,row/count i8; col i4; values c128; little endian',
            'scope':'independent trace plus DtN auxiliary Schur matrix, NOT the uncondensed original FE operator'}


def save_pre_factor_checkpoint(matrix,b,directory,*,admit,disk_reserve_bytes=2**31):
    from petsc4py import PETSc
    import numpy as np
    from ..common.strict_json import atomic_json
    directory=Path(directory);started=time.monotonic()
    if matrix.getComm().getSize()!=1 or np.dtype(PETSc.IntType)!=np.dtype('int32') or np.dtype(PETSc.ScalarType)!=np.dtype('complex128'):
        raise RuntimeError('checkpoint requires actual MPI1/I32/C128')
    rows,columns=matrix.getSize();raw_nz=matrix.getInfo()['nz_used'];nnz=int(raw_nz)
    if rows!=columns or b.getSize()!=rows or nnz!=raw_nz or nnz<0:raise RuntimeError('checkpoint shape/nnz')
    if type(disk_reserve_bytes) is not int or disk_reserve_bytes<2**30:raise ValueError('checkpoint disk reserve')
    if not directory.is_absolute() or directory.parent.resolve(strict=True)!=directory.parent or directory.exists():
        raise RuntimeError('fresh canonical checkpoint directory required')
    temporary=directory.with_name(directory.name+'.building');temporary.mkdir(exist_ok=False)
    predicted=16+4*rows+20*nnz+8+16*rows+2**20
    free=shutil.disk_usage(temporary).free
    facts={'schema':'sparse-prefactor-checkpoint.v1','predicted_file_bytes':predicted,'disk_free_before':free,
           'disk_reserve_bytes':disk_reserve_bytes,'numeric_calls':0,'passed':False}
    atomic_json(temporary/'admission.json',facts)
    if free<predicted+disk_reserve_bytes:raise RuntimeError('checkpoint disk admission')
    admit('pre_factor_binary_checkpoint',32*2**20,estimate_basis='PETSc streaming binary viewer, two row buffers and SHA readback; sparse, no full matrix copy')
    for obj,name in ((matrix,'condensed_A.petsc'),(b,'condensed_b.petsc')):
        target=temporary/name;viewer=None;primary=None
        try:
            viewer=PETSc.Viewer().createBinary(str(target),mode='w',comm=matrix.getComm());obj.view(viewer)
        except BaseException as exc:primary=exc;raise
        finally:
            if viewer is not None:
                try:viewer.destroy()
                except BaseException as cleanup:
                    FAILED_CHECKPOINT_ROOTS.append((viewer,matrix,b))
                    if primary is not None:primary.add_note('binary viewer cleanup: '+repr(cleanup))
                    else:raise
        with target.open('rb') as f:os.fsync(f.fileno())
    matfacts=_verify_matrix(temporary/'condensed_A.petsc',rows,nnz,matrix)
    with (temporary/'condensed_b.petsc').open('rb') as f:
        if struct.unpack('>2i',f.read(8))!=(1211214,rows):raise RuntimeError('vector binary header')
        bv=np.frombuffer(f.read(),dtype='>c16')
    if len(bv)!=rows or not np.isfinite(bv).all():raise RuntimeError('vector complete finite payload')
    original=np.asarray(b.getArray(readonly=True))
    if bv.astype('<c16').tobytes()!=np.asarray(original,dtype='<c16').tobytes():raise RuntimeError('vector binary readback differs from current b')
    allowed={'admission.json','condensed_A.petsc','condensed_b.petsc','condensed_A.petsc.info','condensed_b.petsc.info'}
    if any(p.name not in allowed for p in temporary.iterdir()):raise RuntimeError('unexpected binary sidecar')
    files=[_record(p) for p in sorted(temporary.iterdir())]
    facts.update(passed=True,matrix=matfacts,b_payload_sha256=sha256(bv.astype('<c16').tobytes()).hexdigest(),
                 files=files,actual_bytes=sum(r['bytes'] for r in files),elapsed_seconds=time.monotonic()-started,
                 restore_scope='diagnostic/future explicit consumer only; does not bypass local recovery, source identities, or original UFL residual')
    atomic_json(temporary/'manifest.json',facts)
    fd=os.open(temporary,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    if directory.exists():raise RuntimeError('checkpoint destination appeared')
    temporary.rename(directory)
    fd=os.open(directory.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {**facts,'directory':str(directory),'manifest_sha256':_sha(directory/'manifest.json')}
