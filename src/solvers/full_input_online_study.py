"""V35 one cold trajectory, qualified fixed PC, original return audit."""
import copy
from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.class_batch_action import ClassBatchAction
from src.solvers.fixed_p3_ilu0 import direct_C
from src.solvers.full_input_online import FullInputPC, continue_after_cycle
from src.solvers.gmres_cycle_commit import close_point, cycle_commit
from src.solvers.joint_block_direction import pair, selected_rows
from src.solvers.local_block_readiness import local_readiness
from src.solvers.local_block_study import mapping
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.return_block_direction import SelectedBundle, OUTER_BLOCKS
from src.solvers.stable_head_varpro import PortBlocks
from src.runners.orthonormal_trace_reprofile import atomic_arrays


def make_bars(stage):
    packet = stage.packet
    C = np.column_stack([direct_C(packet, np.eye(40, dtype=complex)[:,j]) for j in range(40)])
    stage.pc_count('port_factors')
    old = BarAction(PortBlocks(packet, np.vstack((C, packet.a['Hhat']))))
    fast = ClassBatchAction(packet)
    raw = fast.apply
    def apply(value, adjoint=False):
        stage.guard(); stage.reserve('actions')
        result = raw(value, adjoint=adjoint)
        stage.counts['actions'] += 1; stage.durable()
        return result
    fast.apply = apply
    solve = old.solve_port
    def port(rhs, adjoint=False):
        stage.pc_count('port_solves')
        stage.pc_count('port_rhs_columns', 1 if np.ndim(rhs)==1 else np.shape(rhs)[1])
        return solve(rhs, adjoint=adjoint)
    old.solve_port = port
    # One Hhat factor, immutable data, separately counted matrix actions. The
    # original packet/recover/uncondensed/audit never dispatches to fast.
    new = copy.copy(old); new.packet = fast; new.costs = dict(S=0., SH=0., port_solve=0.)
    return old, new, fast


def run(stage):
    packet, own = stage.packet, stage.own_plan
    if (packet.nt, packet.np, packet.size) != (18144,40,18184):
        raise ValueError('V35 complete canonical row/port inventory')
    if array_hash(packet.a['masters']) != own['canonical_master_sha256'] or array_hash(packet.a['b']) != own['b_sha256']:
        raise ValueError('V35 canonical master/RHS mismatch')
    root = stage.io.ROOT/'benchmarks/artifacts/task042'
    setup = stage.io.checked_json(own['local_setup'], root/'v24')
    ready = local_readiness(setup, expected_map=own['map'])
    prior = stage.io.checked_json(own['joint_setup'], root/'v26')
    if (not ready['qualified'] or setup['source_sha'] != own['upstream_source_sha']
            or prior['source_sha'] != own['v26_source_sha']
            or setup['operator_packet']['sha256'] != own['action_sha256']
            or prior['operator_packet']['sha256'] != own['action_sha256']
            or not prior['factor_safety']['qualified'] or prior['factor_safety']['rcond1_estimate'] < 1e-12):
        raise ValueError('V35 original local/joint evidence is unsafe')
    groups, mapcheck = mapping(stage)
    ids = selected_rows(groups)
    if array_hash(ids) != own['joint_rows_sha256']:
        raise ValueError('V35 J order differs')
    factors = [dict(rows=ids.tolist(), matrix=prior['matrix'], **prior['factor_inventory'])]
    factors += [setup['block_inventory'][b] for b in OUTER_BLOCKS]
    load_bytes = sum(sum(np.prod(item[k]['shape'])* (4 if k=='pivots' else 16)
                         for k in ('matrix','LU','pivots')) for item in factors)
    maximum = max(len(item['rows'])**2*16 for item in factors)
    planned = int(load_bytes + 2*maximum + 3*2**30 + packet.nt*257*16)
    capacity = dict(qualified=planned<=8*2**30, simultaneous_planned_bytes=planned,
        factor_array_bytes=int(load_bytes), largest_matrix_bytes=maximum,
        packet_libraries_workspace_allowance=3*2**30, hash_norm_copy_reserve=2*maximum,
        krylov_basis_upper_bytes=packet.nt*257*16, derived_not_RSS=True)
    write_json(stage.artifact/'capacity_before_reads.json', capacity)
    if not capacity['qualified']:
        raise MemoryError('V35 planning cap')
    stage.meta.update(factor_status='READONLY_SEVEN_REGION_DENSE_LU_PRESENT',
        simultaneous_planned_bytes=planned, new_solver_states=1,
        arbitrary_RHS_PC=True, old5_7_LU_read=False, warm_arrays_read=False,
        cached_direction_arrays_read=False, selected_old_outer_LU_blocks=list(OUTER_BLOCKS))
    result = dict(status='PENDING', capacity=capacity, map_check=mapcheck,
        factor_readiness=ready, factor_reloads=[], cycles=[],
        backend='EXACT_CLASS_BATCH64', cold_start='ZERO_TRACE_FROM_FROZEN_OPERATOR',
        reference_arrays_read=False, queue_frozen=False,
        operator_identity={k:own[k] for k in ('action_sha256','physical_sha256','mode_sha256',
                                            'canonical_master_sha256','b_sha256')})
    stage.partial_result = result
    old, new, fast = make_bars(stage)
    bundles = []
    stage.fast = fast
    try:
        pairs = []
        for seed in (423501,423502):
            rng = np.random.default_rng(seed)
            w = rng.normal(size=packet.size)+1j*rng.normal(size=packet.size)
            # Record the scale, then use the full physical-b denominator. No
            # manufactured RHS is substituted for physical b.
            scale = packet.bnorm / np.linalg.norm(packet.apply(w))
            w *= scale
            for adjoint in (False, True):
                a, b = packet.apply(w,adjoint=adjoint), fast.apply(w,adjoint=adjoint)
                row = dict(seed=seed, adjoint=adjoint, input_scale=float(scale),
                           full_b_relative=float(np.linalg.norm(a-b)/packet.bnorm), **pair(a,b))
                pairs.append(row)
        for adjoint in (False,True):
            a,b = packet.apply(packet.a['b'],adjoint=adjoint), fast.apply(packet.a['b'],adjoint=adjoint)
            pairs.append(dict(seed='PHYSICAL_RHS',adjoint=adjoint,
                full_b_relative=float(np.linalg.norm(a-b)/packet.bnorm),**pair(a,b)))
        result['old_new_S_SH_pairs'] = pairs
        if any(p['operation_relative']>1e-10 or p['full_b_relative']>1e-11 for p in pairs):
            result['backend'] = 'ORIGINAL'; new = old
            # A backend mismatch is isolated. Original oracle is still trusted.
        for i, item in enumerate(factors):
            label = 'J' if i==0 else OUTER_BLOCKS[i-1]
            bundle = SelectedBundle(item, root/('v26' if i==0 else 'v24'),
                kind='joint' if i==0 else 'outer', count=stage.pc_count, guard=stage.guard)
            bundles.append(bundle)
            check = bundle.witnesses((422601+2*i,422602+2*i),old.apply,old.adjoint,packet.nt)
            result['factor_reloads'].append(dict(block=label, rows_sha256=array_hash(bundle.rows),
                                                 row_count=len(bundle.rows), **check))
            write_json(stage.artifact/'reload_progress.json', result)
            if not check['qualified']:
                result.update(status='FACTOR_RELOAD_UNSAFE', queue_frozen=True)
                return result
        pc = FullInputPC(packet.nt, bundles[0], bundles[1:], new.apply, count=stage.pc_count)
        r, s = [np.random.default_rng(seed).normal(size=packet.nt) +
                1j*np.random.default_rng(seed+1).normal(size=packet.nt) for seed in (423511,423513)]
        q, v = pc(r), pc(s)
        repeat = pair(pc(r),q)
        linear = pair(pc((.4+.7j)*r+(-.3+.5j)*s),(.4+.7j)*q+(-.3+.5j)*v)
        zero = bool(np.count_nonzero(pc(np.zeros(packet.nt,complex)))==0)
        jrows = []
        for x, y in ((r,q),(s,v)):
            image = old.apply(y)
            # Keep pre-cancellation scales. This is not a convergence claim.
            jrows.append(dict(**pair(image[ids],x[ids]),
                rhs_J_norm=float(np.linalg.norm(x[ids])),
                image_J_norm=float(np.linalg.norm(image[ids])),
                full_input_norm=float(np.linalg.norm(x)),
                full_correction_norm=float(np.linalg.norm(y))))
        checks = dict(zero_exact=zero, repeat=repeat, complex_linearity=linear,
            J_balance=jrows, seeds=[423511,423513], support_rows=mapcheck['block_rows'],
            qualified=bool(zero and max(repeat['operation_relative'],linear['operation_relative'],
                                       *(p['operation_relative'] for p in jrows))<=1e-10))
        result['PC_qualification'] = checks
        write_json(stage.artifact/'pc_qualification.json', checks)
        if not checks['qualified']:
            result.update(status='PC_NUMERICALLY_UNRESOLVED',queue_frozen=True)
            return result
        return solve_trajectory(stage,old,new,fast,pc,bundles,result)

    finally:
        for row, bundle in zip(result['factor_reloads'],bundles):
            row.update(solve_calls=bundle.calls,solve_seconds=bundle.seconds,
                       RHS_columns=bundle.RHS_columns,triangular_passes=2*bundle.calls)
        for bundle in bundles:
            bundle.close()


def solve_trajectory(stage, old, new, fast, pc, bundles, result):
    """Generic returned-cycle chain, also exercised by bounded synthetic tests."""
    packet, own = stage.packet, stage.own_plan
    rhs = packet.a['b']
    result['physical_rhs'] = atomic_arrays(stage.artifact/'physical_rhs.npz', b=rhs)
    trace = np.zeros(packet.nt,complex)
    start, identity = close_point(old,trace,rhs)
    result['initial_state'] = atomic_arrays(stage.artifact/'ZERO_TRACE.npz', **start)
    result['initial_schur_relative'] = float(np.linalg.norm(start['residual'])/packet.bnorm)
    result['cold_port_norm'] = float(np.linalg.norm(start['port']))
    class OracleClosed:
        packet = old.packet
        apply = staticmethod(new.apply)
        reduced_rhs = staticmethod(old.reduced_rhs)
        close = staticmethod(old.close)
    numerical_identity = dict(source_sha=stage.source, plan_sha256=file_hash(stage.io.PLAN_PATH),
        action_sha256=own['action_sha256'], b_sha256=own['b_sha256'], backend=result['backend'],
        factor_member_hashes=[[v['array_sha256'] for v in b.receipts] for b in bundles])
    for cycle in (1,2):
        stage.guard()
        stage.pc_count('cycles')
        began = perf_counter()
        before = stage.counts.copy()
        def callback(value, index):
            stage.pc_count('arnoldi')
            if index % 16 == 0:
                stage.event('arnoldi',cycle=cycle,inner=index,estimated_relative=value)
        row = cycle_commit(OracleClosed(),trace,rhs,stage.artifact/'cycles'/f'CYCLE_{cycle:04d}',
            numerical_identity,dict(cycle=cycle,source_sha=stage.source,
                reference_arrays_read=False,cold_start=True),stage.audit,restart=256,
            preconditioner=pc, residual_action=old.apply, callback=callback)
        with np.load(row['state']['path'],allow_pickle=False) as data:
            trace = np.array(data['trace'])
        row.update(cycle_inclusive_wall_seconds=perf_counter()-began,
                   count_increment={k:stage.counts[k]-before[k] for k in before})
        result['cycles'].append(row); result['final'] = row
        more, status = continue_after_cycle(row['audit'],cycle)
        result.update(status=status,queue_frozen=not more)
        write_json(stage.artifact/'partial_result.json', result)
        stage.event('cycle_complete',cycle=cycle,schur=row['audit']['schur_relative'],decision=status)
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and not (stage.artifact/'FIRST_EQUATION_PASS.json').exists():
            write_json(stage.artifact/'FIRST_EQUATION_PASS.json', row)
        if not more:
            break
    result.update(pc_apply_calls=pc.calls,pc_zero_calls=pc.zero_calls,
        pc_inclusive_seconds=pc.seconds,fast_action_counts=fast.counts,
        fast_action_costs_seconds=fast.costs,old_bar_nested_seconds=old.costs,
        new_bar_nested_seconds=new.costs,neural_increment='NOT_DEMONSTRATED')
    return result


def verify(stage):
    """One frozen candidate + existing REF7, only after the solve actor exits."""
    from src.io.neural_fe_continuation import read_index, V7_ROOT
    from src.runners.autonomous_neural_head import owned
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.solvers.local_trace_study import physical_qualification
    frozen,_ = stage.io.read_result('ONLINE')
    if frozen['status']!='ORIGINAL_EQUATION_PASS' or not frozen['queue_frozen']:
        raise ValueError('V35 reference boundary not frozen/pass')
    candidate = frozen['final']['state']
    p = Path(candidate['path']).resolve()
    if not p.is_relative_to(stage.io.ARTIFACT_ROOT) or file_hash(p)!=candidate['sha256']:
        raise ValueError('V35 frozen candidate path/hash')
    with np.load(p,allow_pickle=False) as data:
        z = np.array(data['z'])
    if array_hash(z)!=candidate['z_sha256']:
        raise ValueError('V35 frozen z member hash')
    ref,_ = read_index('blind_reference')
    receipt = ref['reference_state']
    with np.load(owned(receipt,V7_ROOT),allow_pickle=False) as data:
        reference = np.array(data['z'])
    if array_hash(reference)!=receipt['z_sha256']:
        raise ValueError('V35 existing reference member hash')
    stage.meta.update(reference_arrays_read=True,FE_field_validation=True,
                      frozen_candidate_sha256=candidate['sha256'])
    result,comparisons = independent_physics(stage.design,stage.packet,reference,{'ONLINE':z},
        stage.artifact,audit_function=stage.audit)
    qualification = physical_qualification(result['rows']['ONLINE'],
        comparisons['ONLINE'],result['reference_native_pass'])
    result['comparisons'] = comparisons
    result.update(status='SAME_DISCRETE_QUALIFIED' if qualification['status']=='SAME_DISCRETE_QUALIFIED'
        else 'SAME_DISCRETE_NOT_QUALIFIED',qualification=qualification,
        frozen_candidate=candidate,reference_state=receipt,queue_frozen=True,
        neural_gain='NOT_DEMONSTRATED')
    return result
