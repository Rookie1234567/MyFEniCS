"""Boundary-driven SciPy GCROT with exact CU order/None and durable returns.

CU stores (c,u), c=A*u. The k+1 returned item with c=None is part of the
library contract. A boundary wrapper does not claim long-call equivalence.
"""
import inspect
from pathlib import Path
import numpy as np
from scipy import __version__ as scipy_version
from scipy.sparse.linalg import LinearOperator, gcrotmk
from src.runners.task042_shared import write_json
from src.runners.autonomous_neural_head import original_gate
from src.solvers.gmres_cycle_commit import close_point
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint


def pack_CU(CU, n, *, k=32):
    if len(CU)>k+1:raise ValueError('GCROT returned inventory exceeds k+1')
    cs=np.zeros((len(CU),n),dtype=complex);us=np.empty_like(cs)
    none=np.zeros(len(CU),dtype=np.uint8)
    for j,(c,u) in enumerate(CU):
        u=np.asarray(u)
        if u.shape!=(n,) or not np.isfinite(u).all():raise ValueError('GCROT invalid u')
        us[j]=u
        if c is None:none[j]=1
        else:
            c=np.asarray(c)
            if c.shape!=(n,) or not np.isfinite(c).all():raise ValueError('GCROT invalid c')
            cs[j]=c
    return dict(CU_c=cs,CU_u=us,CU_none=none)


def unpack_CU(arrays, n, *, k=32):
    cs,us,none=(arrays[key] for key in ('CU_c','CU_u','CU_none'))
    if cs.shape!=us.shape or us.ndim!=2 or us.shape[1]!=n or none.shape!=(len(us),):
        raise ValueError('GCROT CU shape/order inventory differs')
    if not np.isin(none,[0,1]).all():raise ValueError('GCROT invalid None mask')
    CU=[(None if none[j] else np.array(cs[j]),np.array(us[j])) for j in range(len(us))]
    pack_CU(CU,n,k=k)
    return CU


def boundary_call(action, rb, x, CU, bnorm, *, m=256, k=32):
    rb=np.asarray(rb);x=np.asarray(x)
    if rb.ndim!=1 or x.shape!=rb.shape or not np.isfinite(rb).all() or not np.isfinite(x).all():
        raise ValueError('GCROT fixed finite correction RHS/x required')
    if not np.isfinite(bnorm) or bnorm<=0:raise ValueError('GCROT physical b norm required')
    n=len(x);trial=unpack_CU(pack_CU(CU,n,k=k),n,k=k)
    calls=0;callbacks=0
    def apply(v):
        nonlocal calls
        calls+=1
        value=np.asarray(action(v))
        if value.shape!=(n,) or not np.isfinite(value).all():raise ValueError('GCROT nonfinite action')
        return value
    def callback(v):
        nonlocal callbacks
        callbacks+=1
    signature=inspect.signature(gcrotmk)
    kwargs=dict(x0=x.copy(),maxiter=1,M=None,callback=callback,m=m,k=k,
                CU=trial,discard_C=False,truncate='oldest',atol=1e-8*bnorm)
    tolerance='rtol' if 'rtol' in signature.parameters else 'tol'
    kwargs[tolerance]=0.
    answer,info=gcrotmk(LinearOperator((n,n),matvec=apply,dtype=np.complex128),rb,**kwargs)
    if answer.shape!=(n,) or not np.isfinite(answer).all():raise ValueError('GCROT nonfinite returned x')
    packed=pack_CU(trial,n,k=k)
    row=dict(method='BOUNDARY-GCROT256-K32',scipy_version=scipy_version,
        tolerance_parameter=tolerance,relative_tolerance=0.,absolute_tolerance=1e-8*bnorm,
        m=m,k=k,maxiter=1,preconditioner=None,truncate='oldest',discard_C=False,
        info=int(info),actual_bar_actions=calls,outer_callback_count=callbacks,
        internal_Arnoldi_iterations=None,internal_length_at_entry=m+max(k-len(CU),0),
        returned_update=bool(np.any(answer!=x)),CU_count=len(trial),
        CU_none_indices=np.flatnonzero(packed['CU_none']).tolist(),
        zero_correction_rhs=bool(not np.any(rb)),long_call_bitwise_equivalence_claimed=False)
    return answer.copy(),trial,row


class RecycleCheckpoint(RollingCheckpoint):
    schema='task042.gcrot-boundary.v21'


def boundary_commit(solver_bar, oracle_bar, base, rb, x, CU, rhs, directory,
                    identity, metadata, audit, *, m=256,k=32,returned=None,fault=None):
    """Solve using frozen backend, close and audit exclusively with old oracle."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    n=len(base)
    previous=pack_CU(CU,n,k=k)
    contract=dict(identity,algorithm='BOUNDARY-GCROT256-K32',m=m,k=k,
        base_trace_sha256=array_hash(base),fixed_rhs_sha256=array_hash(rb),
        physical_rhs_sha256=array_hash(rhs),previous_x_sha256=array_hash(x),
        previous_CU_hashes={key:array_hash(v) for key,v in previous.items()})
    store=RecycleCheckpoint(directory/'numeric',contract)
    resumed=any(store.directory.glob('slot*.commit.json'))
    if resumed:manifest,arrays,errors=store.read()
    else:
        write_json(directory/'started.json',dict(identity=contract,phase='NOT_RETURNED',metadata=metadata))
        answer,trial,inner=boundary_call(solver_bar.apply,rb,x,CU,oracle_bar.packet.bnorm,m=m,k=k)
        if returned:returned(inner)
        arrays=dict(x=answer,trace=base+answer,**pack_CU(trial,n,k=k))
        values=dict(metadata,phase='GCROT_RETURNED_UNAUDITED',inner=inner,audit_pending=True)
        store.save(arrays,values)
        if fault:fault('after_returned')
        manifest,arrays,errors=store.read()
    values=manifest['metadata'];unpack_CU(arrays,n,k=k)
    if values['phase']=='GCROT_RETURNED_UNAUDITED':
        if fault:fault('before_close')
        fields,difference=close_point(oracle_bar,arrays['trace'],rhs)
        predicted=rb-oracle_bar.apply(arrays['x'])
        fixed_difference=float(np.linalg.norm(fields['residual'][:n]-predicted)/oracle_bar.packet.bnorm)
        if fixed_difference>1e-10:raise ValueError('GCROT fixed rb/base identity failed')
        arrays.update(fields)
        values=dict(values,phase='CLOSED_AUDIT_PENDING',original_residual_identity_relative=difference,
                    fixed_correction_identity_relative=fixed_difference)
        store.save(arrays,values)
        if fault:fault('after_closed')
    if values['phase']!='AUDITED':
        if fault:fault('before_audit')
        original=audit(arrays['z'])
        if max(original['recovery_relative'],original['schur_original_identity_operation_relative'])>1e-10 or original['slave_storage_max']!=0:
            raise ValueError('GCROT original recovery/MPC failed')
        values=dict(values,phase='AUDITED',audit_pending=False,audit=original,original_equation_gate=original_gate(original))
        store.save(arrays,values)
    manifest,arrays,errors=store.read()
    path=store.directory/('slot'+str(manifest['generation']%2)+'.npz')
    row=dict(manifest['metadata'],identity=contract,
        state=dict(path=str(path),sha256=file_hash(path),**{key+'_sha256':array_hash(v) for key,v in arrays.items()}),
        returned_boundary_resumed=resumed,generation=manifest['generation'],generation_errors=errors,committed=True)
    write_json(directory/'commit.json',row)
    return row


def recycle_check(action,CU, *, k=32):
    pairs=[];cs=[]
    for j,(c,u) in enumerate(CU):
        if c is None:continue
        actual=action(u)
        denominator=max(np.linalg.norm(actual)+np.linalg.norm(c),np.finfo(float).tiny)
        pairs.append(dict(index=j,operation_relative=float(np.linalg.norm(actual-c)/denominator)))
        cs.append(c)
    gram=np.array(cs).conj()@np.array(cs).T if cs else np.zeros((0,0))
    defect=float(np.linalg.norm(gram-np.eye(len(cs))))
    qualified=bool(all(row['operation_relative']<=1e-10 for row in pairs) and np.isfinite(defect))
    return dict(pairs=pairs,C_orthogonality_Frobenius=defect,None_indices=[j for j,(c,u) in enumerate(CU) if c is None],
                inventory=len(CU),finite=True,qualified=qualified,orthogonality_is_diagnostic=True)
