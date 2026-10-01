"""GMRES return boundary is durable before port closure or original audit.

The original BarAction.close contract is full z=[trace;port].  This module
owns only small cycle states.  It can finish a returned/audit-pending cycle
without repeating Arnoldi and never creates a vector from scalar callbacks.
"""
import json
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.runners.autonomous_neural_head import original_gate
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
from src.solvers.resumable_trace_gmres import correction_cycle


def close_point(bar, trace, rhs):
    trace=np.asarray(trace);rhs=np.asarray(rhs);packet=bar.packet
    if trace.shape!=(packet.nt,) or rhs.shape!=(packet.nt+packet.np,) or packet.np!=40:
        raise ValueError('GMRES trace/40-port/RHS inventory differs')
    if not np.isfinite(trace).all() or not np.isfinite(rhs).all():
        raise ValueError('GMRES nonfinite trace/RHS')
    z=np.asarray(bar.close(trace,rhs))
    if z.shape!=(packet.nt+packet.np,) or not np.array_equal(z[:packet.nt],trace):
        raise ValueError('BarAction.close must return full z with unchanged trace')
    port=z[packet.nt:]
    if port.shape!=(40,) or not np.isfinite(z).all():raise ValueError('invalid GMRES closed state')
    residual=rhs-packet.apply(z)
    reduced=bar.reduced_rhs(rhs)-bar.apply(trace)
    difference=float(np.linalg.norm(residual[:packet.nt]-reduced)/np.linalg.norm(rhs))
    if difference>1e-8:raise ValueError('GMRES original/closed residual identity differs')
    return dict(trace=np.array(trace),port=np.array(port),z=np.array(z),residual=residual),difference


def cycle_commit(bar, base, rhs, directory, identity, metadata, audit, *, restart=64,
                 callback=None, returned=None, io_begin=None, io_done=None, fault=None):
    """Actual cycle -> proposed -> closed audit-pending -> audited -> commit.

    fault is used only by bounded tests at these named return boundaries.
    'returned' lets the task ledger durably charge the exact callback count.
    A previously returned finite trace is read from its committed generation.
    """
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    base=np.asarray(base);rhs=np.asarray(rhs)
    if base.shape!=(bar.packet.nt,) or rhs.shape!=(bar.packet.nt+40,):
        raise ValueError('GMRES cycle base/RHS inventory differs')
    contract=dict(identity,algorithm='original-barS-GMRES-cycle-v18',restart=restart,
                  parent_trace_sha256=array_hash(base),rhs_sha256=array_hash(rhs))
    store=RollingCheckpoint(directory/'numeric',contract)
    committed=directory/'commit.json'
    resumed=False;prior=None;arrays=None;errors=[]
    if any(store.directory.glob('slot*.commit.json')):
        prior,arrays,errors=store.read();resumed=True
    else:
        write_json(directory/'started.json',dict(identity=contract,metadata=metadata,
            phase='STARTED_NOT_RETURNED',reserve_original_actions=restart+16))
        proposed,inner=correction_cycle(bar.apply,base,bar.reduced_rhs(rhs),
                                       float(np.linalg.norm(rhs)),callback,restart=restart)
        if returned is not None:returned(inner)
        values=dict(metadata,phase='GMRES_RETURNED_UNAUDITED',inner=inner,audit_pending=True,
                    proposed_trace_sha256=array_hash(proposed),original_actions_reserve=16)
        began=io_begin() if io_begin else None
        saved=store.save(dict(trace=proposed),values)
        if io_done:io_done(began,saved['path'])
        if fault:fault('after_proposed')
        prior,arrays,errors=store.read()
    values=prior['metadata'];inner=values['inner'];trace=arrays['trace']
    if inner['restart']!=restart or not 0<=inner['inner_iterations']<=restart:
        raise ValueError('returned GMRES counter/contract differs')
    if values['phase']=='GMRES_RETURNED_UNAUDITED':
        if fault:fault('before_close')
        arrays,identity_relative=close_point(bar,trace,rhs)
        values=dict(values,phase='CLOSED_AUDIT_PENDING',original_residual_identity_relative=identity_relative)
        began=io_begin() if io_begin else None
        saved=store.save(arrays,values)
        if io_done:io_done(began,saved['path'])
        if fault:fault('after_closed')
    else:
        if arrays['z'].shape!=(bar.packet.nt+40,) or arrays['port'].shape!=(40,) or not np.array_equal(arrays['z'][:bar.packet.nt],trace):
            raise ValueError('saved closed GMRES inventory differs')
        if not np.array_equal(arrays['port'],arrays['z'][bar.packet.nt:]):raise ValueError('saved port is not z tail')
    if values['phase']!='AUDITED':
        if fault:fault('before_audit')
        original=audit(arrays['z']);gate=original_gate(original)
        if max(original['recovery_relative'],original['schur_original_identity_operation_relative'])>1e-10 or original['slave_storage_max']!=0:
            raise ValueError('GMRES original recovery/MPC identity failed')
        values=dict(values,phase='AUDITED',audit_pending=False,audit=original,original_equation_gate=gate)
        began=io_begin() if io_begin else None
        saved=store.save(arrays,values)
        if io_done:io_done(began,saved['path'])
        if fault:fault('after_audit')
    manifest,arrays,errors=store.read()
    state_path=store.directory/('slot'+str(manifest['generation']%2)+'.npz')
    state=dict(path=str(state_path),sha256=file_hash(state_path),
               **{k+'_sha256':array_hash(v) for k,v in arrays.items()})
    row=dict(manifest['metadata'],identity=contract,state=state,returned_boundary_resumed=resumed,
             generation=manifest['generation'],generation_errors=errors,committed=True)
    write_json(committed,row)
    return row
