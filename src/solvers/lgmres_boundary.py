"""V19 explicit single-boundary LGMRES with transactional own directions.

This driver carries x and ordered (v, None) between single SciPy calls. It
does not claim equality with the adaptive tolerances of one long call.
"""
import inspect
import json
from pathlib import Path

import numpy as np
import scipy
from scipy.sparse.linalg import LinearOperator, lgmres

from src.runners.autonomous_neural_head import original_gate
from src.runners.task042_shared import write_json
from src.solvers.gmres_cycle_commit import close_point
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint


class BoundaryCheckpoint(RollingCheckpoint):
    schema = 'task042.lgmres-boundary.v19'


def directions_array(directions, n):
    if len(directions) > 3:
        raise ValueError('LGMRES direction capacity exceeded')
    for v, av in directions:
        if av is not None or np.shape(v) != (n,) or not np.isfinite(v).all():
            raise ValueError('LGMRES ordered direction/Av contract differs')
    return np.stack([v for v, _ in directions]) if directions else np.empty((0, n), complex)


def signature_record(inner_m=256):
    params = inspect.signature(lgmres).parameters
    key = 'rtol' if 'rtol' in params else 'tol'
    return dict(method='BOUNDARY_DRIVEN_LGMRES256_K3', scipy_version=scipy.__version__,
                relative_keyword=key, relative_tolerance=0., inner_m=inner_m,
                outer_k=3, maxiter=1, M=None, prepend_outer_v=False,
                store_outer_Av=False, callback_semantics='outer state; not Arnoldi',
                internal_Arnoldi_iterations=None, long_call_bitwise_equivalence_claimed=False)


def boundary_call(action, rb, x, directions, physical_bnorm, *, inner_m=256):
    """Copy caller state because SciPy mutates outer_v and potentially x0."""
    rb, x = np.asarray(rb), np.asarray(x)
    if x.ndim != 1 or rb.shape != x.shape or not np.isfinite(rb).all() or not np.isfinite(x).all():
        raise ValueError('LGMRES fixed RHS/x inventory or finite check failed')
    inventory = directions_array(directions, len(x))
    trial = [(v.copy(), None) for v in inventory]
    x_trial = x.copy(); count = 0; callbacks = 0
    def apply(v):
        nonlocal count
        count += 1
        return action(v)
    def callback(_):
        nonlocal callbacks
        callbacks += 1
    record = signature_record(inner_m)
    operator = LinearOperator((len(x), len(x)), matvec=apply, dtype=np.complex128)
    result, info = lgmres(operator, rb, x0=x_trial, outer_v=trial,
        inner_m=inner_m, outer_k=3, M=None, maxiter=1, callback=callback,
        prepend_outer_v=False, store_outer_Av=False,
        atol=1e-8*physical_bnorm, **{record['relative_keyword']: 0.})
    result = np.asarray(result)
    if result.shape != x.shape or not np.isfinite(result).all():
        raise ValueError('nonfinite LGMRES returned correction')
    directions_array(trial, len(x))
    record.update(info=int(info), actual_bar_actions=count, outer_callback_count=callbacks,
                  absolute_tolerance=1e-8*physical_bnorm,
                  returned_update=not np.array_equal(result, x),
                  direction_count=len(trial), zero_correction_rhs=bool(np.linalg.norm(rb)==0))
    return result.copy(), trial, record


def boundary_commit(bar, base, rb, x, directions, rhs, directory, identity,
                    metadata, audit, *, inner_m=256, returned=None,
                    io_begin=None, io_done=None, fault=None):
    """Return -> durable x/t/directions -> close -> audit -> commit marker."""
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    base, rb, x, rhs = map(np.asarray, (base, rb, x, rhs))
    inventory = directions_array(directions, bar.n)
    if base.shape != (bar.n,) or rb.shape != base.shape or x.shape != base.shape:
        raise ValueError('LGMRES parent/correction shape differs')
    contract = dict(identity, type='BOUNDARY_DRIVEN_LGMRES256_K3', version=1,
        inner_m=inner_m, outer_k=3, Av=None, parent_trace_sha256=array_hash(base),
        fixed_rb_sha256=array_hash(rb), physical_rhs_sha256=array_hash(rhs),
        prior_x_sha256=array_hash(x), prior_directions_sha256=array_hash(inventory))
    store = BoundaryCheckpoint(directory/'numeric', contract)
    resumed = any(store.directory.glob('slot*.commit.json'))
    def save(arrays, values):
        began = io_begin() if io_begin else None
        saved = store.save(arrays, values)
        if io_done: io_done(began, saved['path'])
    if not resumed:
        write_json(directory/'started.json', dict(identity=contract, metadata=metadata,
            phase='STARTED_NOT_RETURNED', reserve_original_actions=320))
        correction, proposed_dirs, inner = boundary_call(bar.apply, rb, x, directions,
                                                       np.linalg.norm(rhs), inner_m=inner_m)
        if returned: returned(inner)
        arrays = dict(x=correction, trace=base+correction,
                      outer_directions=directions_array(proposed_dirs, bar.n))
        values = dict(metadata, phase='LGMRES_RETURNED_UNAUDITED', inner=inner,
                      audit_pending=True, outer_Av_type='None; recompute original action')
        save(arrays, values)
        if fault: fault('after_proposed')
    manifest, arrays, errors = store.read(); values = manifest['metadata']
    if not np.array_equal(arrays['trace'], base+arrays['x']):
        raise ValueError('LGMRES base+x was mixed or duplicated')
    directions_array([(v, None) for v in arrays['outer_directions']], bar.n)
    if values['phase']=='LGMRES_RETURNED_UNAUDITED':
        if fault: fault('before_close')
        closed, relative = close_point(bar, arrays['trace'], rhs)
        correction_residual = rb-bar.apply(arrays['x'])
        correction_identity = float(np.linalg.norm(closed['residual'][:bar.n]-correction_residual)/np.linalg.norm(rhs))
        if correction_identity>1e-8:
            raise ValueError('fixed correction RHS/original residual identity failed')
        arrays.update(closed)
        values.update(phase='CLOSED_AUDIT_PENDING', original_residual_identity_relative=relative,
                      fixed_correction_identity_relative=correction_identity)
        save(arrays, values)
        if fault: fault('after_closed')
    if values['phase']!='AUDITED':
        if fault: fault('before_audit')
        original = audit(arrays['z'])
        if max(original['recovery_relative'], original['schur_original_identity_operation_relative'])>1e-10 or original['slave_storage_max']!=0:
            raise ValueError('LGMRES original recovery/MPC identity failed')
        values.update(phase='AUDITED', audit_pending=False, audit=original,
                      original_equation_gate=original_gate(original))
        save(arrays, values)
        if fault: fault('after_audit')
    manifest, arrays, errors = store.read()
    state_path = store.directory/('slot'+str(manifest['generation']%2)+'.npz')
    state = dict(path=str(state_path), sha256=file_hash(state_path),
                 **{k+'_sha256':array_hash(v) for k,v in arrays.items()})
    row = dict(manifest['metadata'], identity=contract, state=state,
        returned_boundary_resumed=bool(resumed), generation=manifest['generation'],
        generation_errors=errors, committed=True,
        direction_inventory=dict(count=len(arrays['outer_directions']), ordered=True,
            array_sha256=array_hash(arrays['outer_directions']), Av=None))
    write_json(directory/'commit.json', row)
    return row
