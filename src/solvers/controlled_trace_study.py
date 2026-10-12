"""Thin V76 strategy queue on the existing packet, FGMRES and field tail."""
import gc
import json
import time

import numpy as np

from src.runners.task042_shared import write_json
from . import controlled_trace_scope as scope
from . import bounded_trace_study as common
from .scattering_anchor import Journal, relative, save_arrays
from .scattering_anchor_checks import checked_arrays
from .trace_residual_minimization import trace_diagonal, effect_gate, ResidualMinimizedPC


class SimplePC:
    def __init__(self, inverse=None):
        self.inverse = inverse
        self.calls = dict(apply=0, local_triangular=0, coarse_triangular=0)
        self.seconds = dict(local=0., coarse=0.)

    def __call__(self, vector):
        self.calls['apply'] += 1
        return vector.copy() if self.inverse is None else self.inverse * vector

    def destroy(self):
        self.inverse = None


def precheck(folder, journal):
    s, b, oracle, a, rhs, left, right = common.setup_service('PRECHECK', journal, scope=scope)
    ref = checked_arrays(scope.plan_record()['prepared_parent']['retained_action_witness'])
    out = common.action_charge('Q_saved_action_pair',
        lambda: a.apply_trace(ref['inputs'][:, 0]), scope=scope)
    operation = relative(out - ref['outputs'][:, 0], ref['outputs'][:, 0])
    pair = save_arrays(folder/'hot_pair.npz', input=ref['inputs'][:, 0],
        actual=out, expected=ref['outputs'][:, 0])
    with journal.measured('true_complex_diagonal_exact_entity_MPC_pullback'):
        diagonal, inverse, zeros = trace_diagonal(a, left, right)
    reduced = a.condense_rhs(rhs)
    bhat = left * reduced
    chosen = (int(np.argmax(np.abs(bhat[:a.nt]))), a.nt)
    rows = []
    for row in chosen:
        v = np.zeros_like(diagonal); v[row] = 1
        y = common.action_charge('Q_diagonal_component',
            lambda: left*a.apply_trace(right*v), scope=scope)
        error = float(abs(y[row]-diagonal[row])/max(abs(y[row])+abs(diagonal[row]), 1e-300))
        rows.append(dict(row=row, operation_scaled=error,
            arrays=save_arrays(folder/f'diagonal_component_{row}.npz', input=v, action=y)))
    rng = np.random.default_rng(7601)
    witness = rng.normal(size=len(diagonal))+1j*rng.normal(size=len(diagonal))
    arrays = save_arrays(folder/'complex_diagonal.npz', diagonal=diagonal,
        inverse=inverse, witness=witness, diagonal_action=diagonal*witness,
        left=left, right=right)
    passed = operation <= 1e-10 and all(row['operation_scaled'] <= 1e-10 for row in rows)
    result = dict(status='COMPLETED', pass_gate=passed, hot_action_pair=dict(error=operation, arrays=pair),
        diagonal=arrays, diagonal_checks=rows, exact_zero_diagonals=zeros,
        actual_rows=len(diagonal), physical_rhs=save_arrays(folder/'physical_rhs.npz',
            full_rhs=rhs, reduced_rhs=reduced, bhat=bhat, left=left, right=right),
        local_numeric_count=0, coarse_numeric_count=0, new_complete_solves=0,
        global_fine_K_reads=0, global_fine_S_reads=0,
        source=journal.source_state, timings=journal.timings)
    write_json(folder/'controlled_precheck.json', result)
    a.release_hot()
    if not passed:
        raise ValueError('V76 original/true diagonal qualification')
    return result


def iteration_options(role, strategy, consumed, scope, explicit=None):
    """Explicit scheduling overrides, with historical entry semantics unchanged."""
    options = dict(restart=128, max_it=32 if role in ('B0', 'BJ') else 256-consumed,
        residual_interval=256,
        evaluation_iterations=(0, 1, 16, 32, 64, 128) if strategy=='SMR' else (0, 32, 64, 128),
        retained_observation_iterations=(16,) if strategy!='SMR' else (),
        effect_check=lambda row: getattr(scope,'effect_check',effect_gate)(
            row['iteration'], row['true'], row['schur_true_relative_residual']))
    if explicit is not None:
        if set(explicit) != set(options):
            raise ValueError('complete explicit retained scheduling policy')
        options.update(explicit)
    return options


def iterate(role, folder, journal, state, *, scope=scope, pc_factory=None, strategy=None, iteration_policy=None):
    from petsc4py import PETSc
    from .tetra_coefficient_action import CoefficientFullAction
    from .physical_retained_fgmres import run_retained_fgmres
    from .bounded_trace_pc import csr_load, BoundedTwoLevelPC
    scope.require_stage(role)
    s, b, oracle, a, full_rhs, left, right = common.setup_service(role, journal, scope=scope)
    reduced = a.condense_rhs(full_rhs); bhat = left * reduced
    rhs_receipt = save_arrays(folder/'physical_RHS.npz', full_rhs=full_rhs,
        reduced_rhs=reduced, bhat=bhat, left=left, right=right)
    independent = CoefficientFullAction(s, oracle, 15)
    def original(kind, v):
        return common.action_charge(kind, lambda: left*a.apply_trace(right*v), scope=scope)
    pc = None; numeric_count = 0
    strategy = role if strategy is None else strategy
    initial = None; consumed = 0
    if role == 'PROMOTED':
        decision = json.loads((scope.window.TMP/'route_decision.json').read_text())
        prior = scope.stage(decision['promoted_role'])
        values = checked_arrays(prior['retained_returned'])
        for key, target in [('scaled_rhs', bhat), ('left', left), ('right', right)]:
            if not np.array_equal(values[key], target):
                raise ValueError('promoted same RHS and coordinate identity')
        initial = values['scaled_retained']; consumed = prior['iteration']['cumulative_iterations']
        strategy = decision['promoted_role']
    if pc_factory is not None:
        pc, numeric_count = pc_factory(folder=folder,journal=journal,state=state,
            setup=s,boundary=b,packet=a,full_rhs=full_rhs,left=left,right=right,
            scaled_rhs=bhat,original=original)
    elif strategy in ('B0', 'BJ'):
        inverse = None
        if strategy == 'BJ':
            diag = checked_arrays(scope.stage('PRECHECK')['diagonal'])
            if not np.array_equal(diag['left'], left) or not np.array_equal(diag['right'], right):
                raise ValueError('Jacobi scale identity')
            inverse = diag['inverse']
        pc = SimplePC(inverse)
    elif strategy == 'SMR':
        from .reused_trace_admission import future_workspace
        prep = scope.parent_preparation()
        old = scope.checked_json(scope.plan_record()['reuse_qualification'])
        if not old['preparation_checks']['mathematics_pass']:
            raise ValueError('old immutable coarse/owner mathematics')
        Z = csr_load(prep['Z']); pa = checked_arrays(prep['patch_arrays'])
        patches = [{k: pa[f'{j}_{k}'] for k in ('ids', 'core')}
                   for j in range(prep['patch_inventory']['patches'])]
        workspace = future_workspace(len(bhat), len(full_rhs), s['P'].shape[0],
            max(r['rows'] for r in prep['analysis']), max(r['nnz'] for r in prep['analysis']),
            restart=128, minimum_bytes=12*2**30)
        remaining = scope.window.snapshot()['heavy_remaining_seconds']
        decision = dict(remaining_seconds=remaining, numeric_upper_seconds=3600,
            acceptance_reserve_seconds=4500, first_block_upper_seconds=1800,
            admitted=remaining >= 3600+4500+1800, workspace=workspace)
        write_json(folder/'pre_PC_numeric_forecast.json', decision)
        if not decision['admitted']:
            raise RuntimeError('SMR numeric/first block/full acceptance time reserve')
        local, coarse = common.numeric_factors(prep, journal, scope=scope,
            folder=folder, workspace=workspace, clock_root=folder)
        # Establish ownership immediately; all later qualification is protected.
        base = BoundedTwoLevelPC(Z, patches, local, coarse,
            lambda v: original('I_PC_original', v))
        try:
            def log_pc(row):
                with (folder/'SMR_calls.jsonl').open('a') as f:
                    f.write(json.dumps(row, allow_nan=False)+'\n'); f.flush()
            pc = ResidualMinimizedPC(base, lambda v: original('I_PC_original', v), log_pc,
                witness=lambda i,v,D,W,z: save_arrays(folder/f'SMR_directions_{i}.npz',
                    input=v, directions=D, images=W, correction=z))
        except BaseException:
            base.destroy(); raise
        numeric_count = len(local)+1
    else:
        raise ValueError('explicit controlled PC strategy')
    evaluations = []; counter = 0
    def evaluate(target, residual):
        nonlocal counter
        t = right*target.array; full = a.recover(t, full_rhs)
        aud, res, original_rhs = common.action_charge('I_public_original',
            lambda: independent.audit(full, full_rhs, journal), scope=scope)
        defect = a.lift_residual(residual.array/left)-res
        scale = a.identity_operation_scale(t, full, original_rhs)
        aud.update(recovery_identity=a.last_identity['maximum_cell_operation_scaled'],
            Schur_original_identity=float(np.linalg.norm(defect)/max(scale, 1e-300)))
        raw = save_arrays(folder/f'original_snapshot_{counter:02d}.npz',
            trace=t, full=full, rhs=original_rhs, residual=res)
        counter += 1; evaluations.append(dict(audit=aud, arrays=raw))
        write_json(folder/'original_monitor_progress.json', dict(rows=evaluations))
        return aud
    def append(name, row):
        with (folder/name).open('a') as f:
            f.write(json.dumps(row, allow_nan=False)+'\n'); f.flush()
    def save(iteration, vector):
        rec = save_arrays(folder/f'retained_{iteration:04d}.npz',
            scaled_retained=vector.array.copy(), trace=right*vector.array,
            bhat=bhat, left=left, right=right)
        write_json(folder/'latest_retained.json', dict(iteration=iteration,
            arrays=rec, RHS=rhs_receipt, local_packet=a.receipt, source=state))
    def vec_operation(operation):
        def perform(v):
            out = v.duplicate()
            try:
                out.array[:] = operation(v.array)
                return out
            except BaseException:
                out.destroy(); raise
        return perform
    start = time.monotonic()
    rhs = None
    try:
        if strategy == 'SMR':
            with journal.measured('SMR_two_live_input_witnesses'):
                first = pc(bhat); normalized = bhat/np.linalg.norm(bhat)
                second = pc(normalized)
            error = relative(second-first/np.linalg.norm(bhat), first/np.linalg.norm(bhat))
            if error > 1e-10:
                raise ValueError('SMR real-input complex homogeneity')
            write_json(folder/'live_PC_qualification.json', dict(pass_gate=True,
                nonlinearity_expected=True, additive_linearity_gate_applied=False,
                homogeneity_error=error, arrays=save_arrays(folder/'SMR_input_witness.npz',
                    rhs=bhat, correction=first, arnoldi_input=normalized, arnoldi_correction=second)))
        rhs = PETSc.Vec().createSeq(len(bhat), comm=PETSc.COMM_SELF); rhs.array[:] = bhat
        policy = dict(original_key='true',
            physical_limits=dict(true=1e-6, native=1e-6, augmented=1e-6, port=1e-6),
            identity_limits=dict(MPC_identity=1e-10, rhs_q47_q63=1e-10,
                recovery_identity=1e-10, Schur_original_identity=1e-10))
        scheduling = iteration_options(role, strategy, consumed, scope, iteration_policy)
        scope.begin_ksp(role, state)
        result = run_retained_fgmres(rhs,
            vec_operation(lambda v: original('I_outer_scaled_trace', v)), vec_operation(pc),
            evaluate=evaluate, checkpoint=lambda i, v, row: write_json(folder/'latest_original_gate.json', row),
            append=append, seconds=lambda: time.monotonic()-start,
            save_retained=save, **scheduling,
            initial_vector=initial, iterations_consumed=consumed,
            true_action=vec_operation(lambda v: original('I_explicit_true_scaled_trace', v)),
            candidate_rtol=1e-11, retained_tolerance=1e-11, evaluation_policy=policy,
            audit_identity=dict(directory=str(folder), route=role, strategy=strategy,
                source_sha=state['source_sha'], packet_sha256=a.receipt['sha256'], RHS=rhs_receipt),
            resource_sample=scope.window.require_live,
            stop_requested=lambda: scope.ksp_seconds()+time.monotonic()-start >= scope.plan_record()['iteration_seconds']
                or scope.window.snapshot()['heavy_remaining_seconds'] <= 4500
                or common.actions_started(scope) >= scope.plan_record()['action_limit']-40)
        final = result.pop('final_solution'); values = final.array.copy(); final.destroy()
        t = right*values
        returned = save_arrays(folder/'retained_returned.npz', scaled_retained=values,
            trace_port=t, rhs=reduced, scaled_rhs=bhat, left=left, right=right)
        pending = dict(status='RECOVERY_PENDING', retained_returned=returned, RHS=rhs_receipt,
            local_packet=a.receipt, source=state, spec=s['spec'], physical=s['physical'],
            boundary_arrays=scope.plan_record()['prepared_parent']['boundary_arrays'],
            mode_sha256=b['digest'], iteration=result, strategy=strategy,
            new_complete_solves=1, new_numeric_factors=numeric_count)
        write_json(folder/'retained_audit_pending.json', pending)
        scope.freeze_candidate(role, returned, state)
    finally:
        if rhs is not None: rhs.destroy()
        before = journal.event('controlled_PC_before_release')['RSS_bytes']
        pc_calls = dict(pc.calls); pc_seconds = dict(pc.seconds)
        pc.destroy(); pc = None; gc.collect()
        after = journal.event('controlled_PC_released')['RSS_bytes']
        write_json(folder/'factor_release_lifecycle.json', dict(before_RSS_bytes=before,
            after_RSS_bytes=after, RSS_decreased=after<before, numeric_count=numeric_count,
            local_numeric_count=38 if numeric_count else 0, coarse_numeric_count=1 if numeric_count else 0,
            global_fine_factor_count=0))
    x, pending = common.finish_retained_recovery(folder, journal, state, s=s, b=b,
        independent=independent, a=a, full_rhs=full_rhs, t=t, pending=pending,
        pc_calls=pc_calls, pc_seconds=pc_seconds, scope=scope)
    a = independent = None; gc.collect()
    return common.finish_retained_fields(folder, journal, state, s, b, x, pending, fail_fast=True)


def execute(role, folder, state):
    if state.get('memory_budget') != scope.memory_budget(role):
        raise ValueError('V76 resolved/live role budget')
    journal = Journal(folder, window_scope=scope.window,
        planning_limit_bytes=scope.memory_budget(role)['planning_gib']*2**30)
    journal.source_state = state
    if role == 'PRECHECK': return precheck(folder, journal)
    if role in scope.SOLVES:
        if state.get('postprocessing_resume'):
            return consume_returned(role, folder, journal, state)
        return iterate(role, folder, journal, state)
    if role == 'VERIFY_COST':
        from benchmarks.collect_controlled_trace import verify
        return verify(folder, journal)
    raise ValueError('V76 explicit one-run role')


def consume_returned(role, folder, journal, state, *, scope=scope):
    """A legal returned vector is consumed without a factor or another KSP."""
    from .tetra_coefficient_action import CoefficientFullAction
    meta = scope.saved_json(state['postprocessing_resume'])
    if (meta['mode'] != 'RETURNED_VECTOR_ONLY' or meta['role'] != role
            or meta['new_KSP_solves'] != 0 or meta['new_numeric_factors'] != 0):
        raise ValueError('V76 returned-only protocol')
    p = scope.saved_json(meta['producer_pending'])
    if (p['physical'] != scope.physical_for(role)
            or p['local_packet']['sha256'] != scope.plan_record()['prepared_parent']['local_packet']['sha256']):
        raise ValueError('returned-only physical/packet identity')
    values = checked_arrays(p['retained_returned'])
    s, b, oracle, a, rhs, left, right = common.setup_service(role, journal, scope=scope)
    for name, expected in [('scaled_rhs', left*a.condense_rhs(rhs)), ('left', left), ('right', right)]:
        if not np.array_equal(values[name], expected):
            raise ValueError('returned-only fixed RHS and coordinate identity')
    t = right*values['scaled_retained']
    if not np.array_equal(t, values['trace_port']):
        raise ValueError('returned-only full trace/port')
    pending = dict(p, new_complete_solves=0, new_numeric_factors=0,
        prior_numeric_factors=p['new_numeric_factors'], iteration_source=p['source'],
        consumer_source=state, saved_returned_only=True)
    independent = CoefficientFullAction(s, oracle, 15)
    x, pending = common.finish_retained_recovery(folder, journal, state, s=s, b=b,
        independent=independent, a=a, full_rhs=rhs, t=t, pending=pending,
        pc_calls=p.get('pc_calls', {'unknown_after_return': True}),
        pc_seconds=p.get('pc_seconds', {'missing_after_return': None}), scope=scope)
    a = independent = None; gc.collect()
    return common.finish_retained_fields(folder, journal, state, s, b, x, pending, fail_fast=True)
