"""Independent raw-output checks; never construct or invoke a PDE solver."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

_POSITIVE_APPLY_KEYS = ('s6_apply_count', 's3_apply_count')

_BOUNDED_I4_STATUSES = (
    'INNER_ZERO_RHS', 'INNER_TARGET_REACHED', 'INNER_APPROXIMATE_RETURN',
)
_BOUNDED_NEGATIVE_STATUSES = (
    'NORMAL_SCREEN_STOP', 'PROGRESS_INSUFFICIENT_AT_MID_BUDGET',
    'PERFORMANCE_CONTROLLED_STOP', 'ITERATION_BUDGET_EXHAUSTED',
    'CONTROLLED_STOP',
)


def _stable_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _finite_number(value, *, nonnegative=False) -> bool:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(result) and (not nonnegative or result >= 0.0))


def _bounded_i4_facts(row: dict) -> dict:
    facts = row.get('facts', row)
    return facts if isinstance(facts, dict) else {}


def recompute_bounded_i4(i4_rows, pc_rows, exit_rows=()) -> dict:
    """Recompute V7 I4, PC, H6, and inexact-audit accounting from JSONL.

    This deliberately does not use ``positive_setup`` or the solver's status.
    In particular, H6 is counted from the actual per-PC smoother count, and
    the two I4 calls are matched to their nested inexact-balance records.
    """
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    normalized = []
    timeout_streak = 0
    no_direction_streak = 0
    for index, row in enumerate(i4_rows, 1):
        facts = _bounded_i4_facts(row)
        require(row.get('call') == index, f'I4 call ordering mismatch at {index}')
        status = facts.get('status')
        require(status in _BOUNDED_I4_STATUSES, f'illegal I4 status at {index}: {status}')
        for key in ('target', 'rhs_norm', 'final_true_residual', 'seconds',
                    'actual_elapsed_seconds'):
            require(_finite_number(facts.get(key), nonnegative=True),
                    f'nonfinite/negative I4 {key} at {index}')
        require(facts.get('target') == 1e-4, f'I4 target is not 1e-4 at {index}')
        require(facts.get('restart') == 16 and facts.get('max_it') == 16,
                f'I4 16-step contract mismatch at {index}')
        require(facts.get('zero_start') is True, f'I4 is not zero-start at {index}')
        iterations = facts.get('iterations')
        legal = facts.get('legal_direction_count')
        require(isinstance(iterations, int) and 0 <= iterations <= 16,
                f'I4 iteration cap mismatch at {index}')
        require(isinstance(legal, int) and legal >= 0,
                f'I4 legal-direction count mismatch at {index}')
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4'):
            require(isinstance(facts.get(key), int) and facts[key] >= 0,
                    f'I4 {key} is not a nonnegative count at {index}')
        attempted = facts.get('attempted', {})
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4'):
            if attempted:
                require(attempted.get(key) == facts.get(key),
                        f'I4 attempted/completed {key} mismatch at {index}')
        timeout = facts.get('timeout_exceeded')
        require(isinstance(timeout, bool), f'I4 timeout flag is not boolean at {index}')
        if timeout:
            require(float(facts['seconds']) >= 30.0,
                    f'I4 hard-30 timeout is early at {index}')
        else:
            require(float(facts['seconds']) <= 30.0 + 1e-7,
                    f'I4 exceeded hard-30 without timeout at {index}')
        safe_return = facts.get('requested_safe_return')
        require(isinstance(safe_return, bool),
                f'I4 safe-return flag is not boolean at {index}')
        if status != 'INNER_ZERO_RHS':
            if float(facts['seconds']) >= 25.0:
                require(safe_return, f'I4 missed soft-25 safe-return flag at {index}')
            if safe_return and float(facts['seconds']) < 25.0:
                require(facts.get('stop_reason') == 'OUTER_SAFE_DEADLINE',
                        f'I4 early safe-return has no outer deadline at {index}')
            timeout_streak = timeout_streak + 1 if timeout else 0
            no_direction_streak = (no_direction_streak + 1
                                   if legal == 0 else 0)
        # Zero-RHS is legal but does not reset either consecutive-cost streak.
        admission = row.get('admission', {})
        if admission:
            require(admission.get('calls') == index,
                    f'I4 admission call count mismatch at {index}')
            require(admission.get('timeout_streak') == timeout_streak,
                    f'I4 timeout streak mismatch at {index}')
            require(admission.get('no_direction_streak') == no_direction_streak,
                    f'I4 no-direction streak mismatch at {index}')
        if status == 'INNER_ZERO_RHS':
            require(facts['rhs_norm'] == 0.0 and facts['final_true_residual'] == 0.0,
                    f'zero-RHS I4 has nonzero norm at {index}')
            require(iterations == facts['A4_matvec'] == facts['B4_calls'] == 0,
                    f'zero-RHS I4 invented work at {index}')
            require(facts['explicit_A4'] == 0,
                    f'zero-RHS I4 performed an explicit action at {index}')
        else:
            require(float(facts['rhs_norm']) > 0.0,
                    f'nonzero I4 has zero RHS at {index}')
            eps_norm = facts.get('eps_norm')
            require(_finite_number(eps_norm, nonnegative=True),
                    f'nonzero I4 has no finite eps_norm at {index}')
            relative = float(eps_norm) / float(facts['rhs_norm'])
            require(np.isclose(relative, float(facts['final_true_residual']),
                               rtol=0, atol=1e-12),
                    f'I4 eps_norm/rhs_norm relative mismatch at {index}')
            if status == 'INNER_TARGET_REACHED':
                require(relative <= 1e-4 + 1e-12,
                        f'target I4 returned above target at {index}')
            require(facts['A4_matvec'] <= iterations and facts['B4_calls'] <= iterations,
                    f'I4 work exceeds iteration count at {index}')
        normalized.append(facts)

    # Match the nested I4 scalar packets to the independently written I4 JSONL.
    nested = []
    for pc_index, row in enumerate(pc_rows, 1):
        calls = row.get('inexact_balance', {}).get('calls', [])
        require(len(calls) == 2, f'PC {pc_index} does not contain exactly two I4 calls')
        nested.extend(item.get('inner', {}) for item in calls)
    require(len(nested) == len(normalized), 'nested I4 count differs from raw I4 count')
    for index, (facts, inner) in enumerate(zip(normalized, nested), 1):
        for key in ('status', 'iterations', 'rhs_norm', 'eps_norm', 'final_true_residual',
                    'A4_matvec', 'B4_calls', 'explicit_A4', 'restart', 'max_it'):
            if key in inner:
                left, right = facts.get(key), inner.get(key)
                if isinstance(left, float) or isinstance(right, float):
                    require(np.isclose(float(left), float(right), rtol=0, atol=1e-12),
                            f'nested/raw I4 {key} mismatch at {index}')
                else:
                    require(left == right, f'nested/raw I4 {key} mismatch at {index}')
        if inner.get('status') != 'INNER_ZERO_RHS':
            require(_finite_number(inner.get('eps_norm'), nonnegative=True),
                    f'nested I4 eps_norm missing at {index}')
            nested_relative = float(inner['eps_norm']) / float(inner['rhs_norm'])
            require(np.isclose(nested_relative, float(inner['final_true_residual']),
                               rtol=0, atol=1e-12),
                    f'nested I4 eps_norm/rhs_norm mismatch at {index}')

    pc_facts = []
    h6_count = 0
    for index, row in enumerate(pc_rows, 1):
        require(row.get('apply_count') == index, f'PC apply ordering mismatch at {index}')
        require(row.get('route') == 'BAL_H', f'bounded PC route mismatch at {index}')
        require(row.get('status') == 'BALANCED_ACTION_COMPLETED',
                f'bounded PC status mismatch at {index}')
        counts = row.get('counts', {})
        expected_counts = dict(C=2, smoother=1, A_structure=2, A_inner_true=0,
                               PH_audit=0)
        for key, expected in expected_counts.items():
            require(counts.get(key) == expected,
                    f'bounded PC {key} count mismatch at {index}')
        h6_count += int(counts.get('smoother', 0))
        audit = row.get('inexact_balance', {})
        actual_audit = audit.get('actual_audit')
        audit_due = index == 1 or index % 32 == 0
        require(actual_audit == ('PASS' if audit_due else 'not_sampled'),
                f'inexact audit cadence mismatch at PC {index}')
        if actual_audit == 'PASS':
            closure = audit.get('audit', {})
            require(_finite_number(closure.get('closure_norm'), nonnegative=True) and
                    _finite_number(closure.get('operation_scale'), nonnegative=True) and
                    float(closure.get('operation_scale', 0.0)) > 0.0,
                    f'inexact closure scalars are invalid at PC {index}')
            if _finite_number(closure.get('closure_norm'), nonnegative=True) and \
                    _finite_number(closure.get('operation_scale'), nonnegative=True) and \
                    float(closure.get('operation_scale', 0.0)) > 0.0:
                relative = (float(closure['closure_norm']) /
                            float(closure['operation_scale']))
                require(_finite_number(closure.get('closure_relative'), nonnegative=True),
                        f'saved inexact closure ratio is invalid at PC {index}')
                if _finite_number(closure.get('closure_relative'), nonnegative=True):
                    require(np.isclose(relative, float(closure['closure_relative']),
                                       rtol=0, atol=1e-15),
                            f'saved inexact closure ratio differs at PC {index}')
                require(relative <= 1e-8, f'inexact closure failed at PC {index}')
        pc_facts.append(dict(apply_count=index, counts=dict(counts),
                             actual_audit=actual_audit))

    exit_rows = list(exit_rows or [])
    if exit_rows:
        require(len(exit_rows) == 1, 'bounded exit audit is not exactly one record')
        exit_row = exit_rows[-1]
        require(exit_row.get('last_PC') == len(pc_rows), 'exit audit last_PC mismatch')
        costs = exit_row.get('audit_costs', {})
        for key, value in costs.items():
            require(_finite_number(value, nonnegative=True),
                    f'negative/nonfinite exit audit cost {key}')
        closure = exit_row.get('audit', {})
        require(_finite_number(closure.get('closure_norm'), nonnegative=True) and
                _finite_number(closure.get('operation_scale'), nonnegative=True) and
                float(closure.get('operation_scale', 0.0)) > 0.0,
                'exit inexact closure scalars are invalid')
        if (_finite_number(closure.get('closure_norm'), nonnegative=True) and
                _finite_number(closure.get('operation_scale'), nonnegative=True) and
                float(closure.get('operation_scale', 0.0)) > 0.0):
            relative = float(closure['closure_norm']) / float(closure['operation_scale'])
            require(_finite_number(closure.get('closure_relative'), nonnegative=True),
                    'saved exit closure ratio is invalid')
            if _finite_number(closure.get('closure_relative'), nonnegative=True):
                require(np.isclose(relative, float(closure['closure_relative']),
                                   rtol=0, atol=1e-15),
                        'saved exit closure ratio differs from closure_norm/operation_scale')
            require(relative <= 1e-8, 'exit inexact closure failed')

    i4_totals = {
        key: sum(int(facts.get(key, 0)) for facts in normalized)
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4')
    }
    return dict(passed=not errors, errors=errors, i4_calls=len(normalized),
                i4_totals=i4_totals, completed_pc_count=len(pc_rows),
                actual_h6_applies=h6_count, pc=pc_facts,
                semantics=dict(I4='two independent calls per PC; target=1e-4; '
                               'restart=max_it=16; soft=25; hard=30; zero-start',
                               H6='one actual smoother apply per PC; positive_setup is not used'))


def recompute_bounded_screen(solve, rows):
    """Recompute the V7 8-step screen and its 128/1800/5400 gates."""
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(solve.get('screen_enabled') is True, 'V7 bounded screen is disabled')
    require(solve.get('screen_policy') == 'v7', 'bounded solve is not using V7 screen')
    require(solve.get('restart') == 32 and solve.get('max_it') == 2048,
            'bounded outer restart/max_it mismatch')
    require(solve.get('zero_start') is True, 'bounded outer solve is not zero-start')
    require(solve.get('ksp_create_count') == solve.get('ksp_solve_count') ==
            solve.get('ksp_destroy_count') == 1, 'bounded outer does not have one KSP lifecycle')
    require(solve.get('residual_interval') == 8 and solve.get('checkpoint_interval') == 32,
            'bounded outer cadence mismatch')
    history = [(0, 1.0)]
    screen = None
    mid = None
    nodes = []
    previous = (-1, -1.0)
    for row in rows:
        try:
            iteration = int(row['iteration'])
            relative = float(row['explicit_true_residual'])
            seconds = float(row['solve_seconds'])
        except (KeyError, TypeError, ValueError):
            errors.append('malformed V7 monitor row')
            continue
        require(iteration >= previous[0], 'V7 monitor iterations are not monotone')
        require(np.isfinite([relative, seconds]).all() and relative >= 0 and seconds >= 0,
                f'invalid V7 monitor scalar at iteration {iteration}')
        previous = (iteration, seconds)
        if iteration == 0:
            if not nodes:
                nodes.append((iteration, relative))
        elif iteration % 8 == 0 and (not nodes or nodes[-1][0] != iteration):
            nodes.append((iteration, relative))
            history = (history + [(iteration, relative)])[-3:]
        # The live solver checks the true residual immediately after the
        # snapshot, before either the investment screen or the 5400-second
        # continuation gate.  A late true pass therefore leaves mid_budget
        # unset even when the screen had already continued the KSP.
        if relative <= 1e-6:
            break
        if screen is None and (iteration >= 128 or seconds >= 1800):
            trend = (len(history) == 3 and history[1][0] - history[0][0] == 8 and
                     history[2][0] - history[1][0] == 8 and
                     0 < history[2][1] < history[1][1] < history[0][1] and
                     np.sqrt(history[2][1] / history[0][1]) <= .80)
            passed = relative <= 1e-2 or (iteration >= 16 and relative <= .30 and trend)
            screen = dict(status='SCREEN_CONTINUE_SAME_LIVE_KSP' if passed else
                          'NORMAL_SCREEN_STOP', passed=bool(passed), iteration=iteration,
                          true_relative=relative, solve_seconds=seconds,
                          checkpoints=list(history), policy='v7')
            if not passed:
                break
        if mid is None and seconds >= 5400:
            passed = relative <= 1e-3
            mid = dict(status='MID_BUDGET_CONTINUE' if passed else
                       'PROGRESS_INSUFFICIENT_AT_MID_BUDGET', passed=bool(passed),
                       iteration=iteration, true_relative=relative,
                       solve_seconds=seconds)
            if not passed:
                break

    saved = solve.get('screen')
    if screen is None:
        require(saved is None, 'saved V7 screen decision differs from recomputation')
    else:
        require(saved is not None, 'missing saved V7 screen decision')
        if saved is not None:
            for key in ('status', 'passed', 'iteration', 'policy'):
                require(saved.get(key) == screen.get(key),
                        f'saved V7 screen {key} differs from raw nodes')
            for key in ('true_relative', 'solve_seconds'):
                require(np.isclose(float(saved.get(key)), float(screen.get(key)),
                                   rtol=0, atol=1e-10),
                        f'saved V7 screen {key} differs from raw nodes')
            def normalized_checkpoints(value):
                return [(int(item[0]), float(item[1])) for item in (value or [])]
            saved_nodes = normalized_checkpoints(saved.get('checkpoints'))
            raw_nodes = normalized_checkpoints(screen.get('checkpoints'))
            require(len(saved_nodes) == len(raw_nodes) and all(
                left[0] == right[0] and np.isclose(left[1], right[1], rtol=0, atol=1e-12)
                for left, right in zip(saved_nodes, raw_nodes)),
                'saved V7 checkpoint history differs from raw 8-step nodes')
    require(solve.get('mid_budget') == mid,
            'saved V7 mid-budget decision differs from raw monitor')
    return dict(passed=not errors, errors=errors, nodes=nodes,
                recomputed_screen=screen, recomputed_mid_budget=mid)


def recompute_bounded_costs(i4_rows, pc_rows, exit_rows=(), setup_costs=None,
                            *, require_lifetime=False) -> dict:
    """Recompute cumulative V7 costs, subtracting setup exactly once."""
    errors = []
    missing = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    setup = setup_costs or {}
    zero_b4 = dict(applies=0, attempted=0, counts={}, operation_seconds={})
    setup_b4 = setup.get('B4', zero_b4)
    setup_i4 = setup.get('I4', {})
    setup_audit = setup.get('inexact_audit', {})
    setup_s = setup.get('S_action', {})
    setup_bottom = setup.get('bottom', {}).get('counts', setup.get('bottom', {}))

    def delta(total, baseline, key):
        if key not in total:
            return None
        value = float(total.get(key, 0)) - float(baseline.get(key, 0))
        require(value >= -1e-12, f'cumulative {key} regressed across setup boundary')
        return value

    i4_totals = {
        key: sum(int(_bounded_i4_facts(row).get(key, 0)) for row in i4_rows)
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4')
    }
    expected_b4 = dict(
        applies=i4_totals['B4_calls'], attempted=i4_totals['B4_calls'],
        counts=dict(A_inner_true=0, A_structure=2*i4_totals['B4_calls'],
                    C=2*i4_totals['B4_calls'], PH_audit=2*i4_totals['B4_calls'],
                    smoother=i4_totals['B4_calls']))
    per_pc_trace = [row.get('trace_counts', {}) for row in pc_rows]
    have_b4 = all('B4' in trace for trace in per_pc_trace)
    have_s = all('S_action' in trace for trace in per_pc_trace)
    have_audit = all('inexact_audit' in trace for trace in per_pc_trace)
    if require_lifetime:
        for present, name in ((have_b4, 'B4'), (have_s, 'S_action'),
                              (have_audit, 'inexact_audit')):
            if not present:
                missing.append(name)
        require(not missing, 'bounded per-PC lifetime counters are missing: '+','.join(missing))

    for name, present in (('B4', have_b4), ('S_action', have_s),
                          ('inexact_audit', have_audit)):
        if present:
            previous = None
            for trace in per_pc_trace:
                counter = trace[name]
                current = float(counter.get('applies', counter.get('calls',
                                  counter.get('audits', 0))))
                if previous is not None:
                    require(current >= previous, f'{name} lifetime counter regressed')
                previous = current

    exit_row = list(exit_rows or [])[-1] if exit_rows else None
    total = exit_row.get('total', {}) if exit_row else {}
    if total:
        b4 = total.get('B4', {})
        b4_applies = delta(b4, setup_b4, 'applies')
        b4_attempted = delta(b4, setup_b4, 'attempted')
        require(b4_applies == expected_b4['applies'], 'B4 apply total differs from I4 calls')
        require(b4_attempted == expected_b4['attempted'], 'B4 attempted total differs from I4 calls')
        for key, expected in expected_b4['counts'].items():
            require(delta(b4.get('counts', {}), setup_b4.get('counts', {}), key) == expected,
                    f'B4 {key} total differs from independent I4 accounting')
        if have_b4 and per_pc_trace:
            last_b4 = per_pc_trace[-1]['B4']
            for key in ('applies', 'attempted'):
                require(delta(b4, setup_b4, key) ==
                        delta(last_b4, setup_b4, key),
                        f'B4 terminal count differs from last PC lifetime snapshot: {key}')
            for key, value in b4.get('operation_seconds', {}).items():
                if key in last_b4.get('operation_seconds', {}):
                    require(np.isclose(
                        float(value) - float(setup_b4.get('operation_seconds', {}).get(key, 0.0)),
                        float(last_b4['operation_seconds'][key]) -
                        float(setup_b4.get('operation_seconds', {}).get(key, 0.0)),
                        rtol=0, atol=1e-10),
                        f'B4 terminal seconds differs from last PC snapshot: {key}')
        i4_total = total.get('I4', {})
        require(delta(i4_total, setup_i4, 'calls') == len(i4_rows),
                'I4 cumulative calls re-add setup or disagree with raw records')
        outer_total = delta(total, setup, 'outer_PC_applies')
        require(outer_total == len(pc_rows), 'outer PC cumulative count mismatch')
        bottom = total.get('bottom', {}).get('counts', {})
        if bottom:
            mat_solve = delta(bottom, setup_bottom, 'MatSolve')
            per_pc_bottom = [trace.get('bottom', {}) for trace in per_pc_trace]
            if all('MatSolve' in row for row in per_pc_bottom):
                require(float(per_pc_bottom[-1]['MatSolve']) - float(setup_bottom.get('MatSolve', 0))
                        == mat_solve, 'MatSolve setup-subtracted total disagrees with PC trace')
        s_total = total.get('S_action', {})
        if s_total:
            s_calls = delta(s_total, setup_s, 'calls')
            if have_s and per_pc_trace:
                last_s = per_pc_trace[-1]['S_action']
                require(s_calls == delta(last_s, setup_s, 'calls'),
                        'S_action terminal count differs from last PC snapshot')
                if 'seconds' in s_total and 'seconds' in last_s:
                    require(np.isclose(
                        float(s_total['seconds']) - float(setup_s.get('seconds', 0.0)),
                        float(last_s['seconds']) - float(setup_s.get('seconds', 0.0)),
                        rtol=0, atol=1e-10),
                        'S_action terminal seconds differs from last PC snapshot')
        audit_total = total.get('inexact_audit', {})
        if audit_total and (have_audit or require_lifetime):
            audits = delta(audit_total, setup_audit, 'audits')
            expected_audits = sum(row.get('inexact_balance', {}).get('actual_audit') == 'PASS'
                                  for row in pc_rows) + 1
            require(audits == expected_audits,
                    'inexact audit total does not equal PC audits plus one exit audit')
            exit_costs = (exit_row or {}).get('audit_costs', {})
            for key in ('audits', 'extra_A6', 'extra_PH'):
                if key in exit_costs:
                    total_delta = delta(audit_total, setup_audit, key)
                    expected_total = (expected_audits if key != 'audits' else expected_audits)
                    require(total_delta == expected_total,
                            f'inexact {key} total differs from independently counted audits')
                    require(float(exit_costs[key]) == 1.0,
                            f'exit audit {key} cost is not exactly one audit')
    else:
        missing.append('bounded_exit_audit.total')
        require(not require_lifetime, 'bounded exit cumulative counters are missing')

    return dict(passed=not errors, errors=errors, missing=missing,
                i4_totals=i4_totals, expected_b4=expected_b4,
                setup=setup, setup_counts_separate=True)


def recompute_projected_trace_costs(pc_rows, exit_rows=(), storage=None,
                                    setup_costs=None) -> dict:
    """Recompute full252 sequential-route work from raw lifetime counters.

    Route B keeps the generic BAL_H accounting, but every trace application
    additionally performs one complete current physical ``T`` action and one
    backsolve in each of the 252 restored patch factors.  All comparisons are
    deltas from the saved setup snapshot, so a finite prerequisite fixture is
    not mistaken for solve work and its counters are never assumed to start at
    zero.
    """
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def count(container, key, label):
        value = container.get(key) if isinstance(container, dict) else None
        valid = (isinstance(value, (int, np.integer)) and not isinstance(value, bool)
                 and value >= 0)
        require(valid, f'{label} {key} is missing or invalid')
        return int(value) if valid else None

    def scalar(container, key, label):
        value = container.get(key) if isinstance(container, dict) else None
        valid = (isinstance(value, (int, float, np.integer, np.floating))
                 and not isinstance(value, bool) and np.isfinite(value) and value >= 0)
        require(valid, f'{label} {key} is missing or invalid')
        return float(value) if valid else None

    projected = (storage or {}).get('projected') if isinstance(storage, dict) else None
    require(isinstance(projected, dict), 'projected trace setup identity is missing')
    if isinstance(projected, dict):
        require(projected.get('source_sha') == 'dcca0f5ea6b7ba9221b23dd210a3c06839cc47be',
                'projected trace source identity differs')
        require(projected.get('factor_count') == 252,
                'projected trace factor count is not 252')
        require(projected.get('factor_dimension') == 144,
                'projected trace factor dimension is not 144')
        require(projected.get('grouping') == 'structured_cell_coordinate_parity_(i+j+k)%2',
                'projected trace grouping identity differs')
        require(projected.get('group_counts') and
                sum(projected.get('group_counts', ())) == 252,
                'projected trace group counts do not cover 252 factors')
        require(projected.get('restored_factor_count') == 252,
                'projected trace did not restore exactly 252 factors')
        require(projected.get('setup_s_column_solves') == 0,
                'projected trace performed forbidden setup S-column solves')
        require(projected.get('no_saved_entity_lu_overlap') is True,
                'projected trace retained the old entity LU path')
        require(projected.get('formula') == 'M0 + M1 - M1*T*M0',
                'projected trace formula identity differs')

    setup = setup_costs if isinstance(setup_costs, dict) else {}
    setup_trace = setup.get('trace', {})
    setup_entities = setup_trace.get('counts', {}) if isinstance(setup_trace, dict) else {}
    setup_joint = setup_trace.get('joint', {}) if isinstance(setup_trace, dict) else {}
    setup_T = setup_trace.get('projected_T', {}) if isinstance(setup_trace, dict) else {}
    setup_B4 = setup.get('B4', {})
    setup_S = setup.get('S_action', {})
    setup_cached = setup.get('cached', {})
    setup_cached = (setup_cached.get('counts', {})
                    if isinstance(setup_cached, dict) and 'counts' in setup_cached
                    else setup_cached)
    setup_bottom = setup.get('bottom', {})
    setup_bottom = (setup_bottom.get('counts', {})
                    if isinstance(setup_bottom, dict) and 'counts' in setup_bottom
                    else setup_bottom)
    for container, label in ((setup_trace, 'projected setup trace'),
                             (setup_T, 'projected setup T'),
                             (setup_joint, 'projected setup joint'),
                             (setup_B4, 'projected setup B4'),
                             (setup_S, 'projected setup S'),
                             (setup_cached, 'projected setup cached A4'),
                             (setup_bottom, 'projected setup bottom')):
        require(isinstance(container, dict), f'{label} baseline is missing')
    for key in ('calls', 'F', 'FH', 'A4', 'CU'):
        count(setup_T, key, 'projected setup T')
    scalar(setup_T, 'seconds', 'projected setup T')
    # The setup trace is the only authoritative baseline for the inner
    # counters; the generic setup costs provide the B4 and coarse-S baselines.
    base_T = {key: count(setup_T, key, 'projected setup T')
              for key in ('calls', 'F', 'FH', 'A4', 'CU')}
    base_entities = {key: count(setup_entities, key, 'projected setup entity')
                     for key in ('HT', 'F', 'FH', 'E', 'EH', 'volume', 'volume_adjoint')}
    base_joint = {key: count(setup_joint, key, 'projected setup joint')
                  for key in ('applications', 'sequential_applications', 'T_started',
                              'T_completed', 'patch_apply_rhs', 'patch_MatSolve',
                              'group0_patch_apply_rhs', 'group1_patch_apply_rhs',
                              'patch_LU', 'restored_factors')}
    base_b4 = count(setup_B4, 'applies', 'projected setup B4')
    base_s = count(setup_S, 'calls', 'projected setup S')
    base_cached = {key: count(setup_cached, key, 'projected setup cached A4')
                   for key in ('started', 'completed')}
    base_bottom = {key: count(setup_bottom, key, 'projected setup bottom')
                   for key in ('MatSolve', 'refinement')}
    if (any(value is None for value in base_T.values()) or
            any(value is None for value in base_entities.values()) or
            any(value is None for value in base_joint.values()) or
            base_b4 is None or base_s is None or
            any(value is None for value in base_cached.values()) or
            any(value is None for value in base_bottom.values())):
        return dict(passed=False, errors=errors,
                    completed_pc_count=len(pc_rows), T_calls=0,
                    patch_backsolves=0, bottom_mat_solves=0, setup=projected)

    traces = [row.get('trace_counts', {}) for row in pc_rows]
    require(bool(traces), 'projected trace has no completed PC snapshots')
    previous = {}
    last = None
    for index, trace in enumerate(traces, 1):
        entities = trace.get('entities') if isinstance(trace, dict) else None
        joint = trace.get('joint') if isinstance(trace, dict) else None
        current = trace.get('projected_T') if isinstance(trace, dict) else None
        b4 = trace.get('B4') if isinstance(trace, dict) else None
        coarse = trace.get('S_action') if isinstance(trace, dict) else None
        cached = trace.get('cached') if isinstance(trace, dict) else None
        bottom = trace.get('bottom') if isinstance(trace, dict) else None
        if not isinstance(entities, dict):
            require(False, f'projected PC {index} entity counters missing')
        if not isinstance(joint, dict):
            require(False, f'projected PC {index} joint counters missing')
        if not isinstance(current, dict):
            require(False, f'projected PC {index} T counters missing')
            continue
        if not isinstance(b4, dict):
            require(False, f'projected PC {index} B4 counters missing')
            continue
        if not isinstance(coarse, dict):
            require(False, f'projected PC {index} S counters missing')
            continue
        if not isinstance(cached, dict):
            require(False, f'projected PC {index} cached A4 counters missing')
            continue
        if not isinstance(bottom, dict):
            require(False, f'projected PC {index} bottom counters missing')
            continue

        t_keys = ('calls', 'F', 'FH', 'A4', 'CU')
        t_values = {key: count(current, key, f'projected PC {index} T') for key in t_keys}
        seconds = scalar(current, 'seconds', f'projected PC {index} T')
        if any(value is None for value in t_values.values()) or seconds is None:
            continue
        if previous:
            for key in (*t_keys, 'seconds'):
                left = seconds if key == 'seconds' else t_values[key]
                right = previous[key]
                require(left >= right,
                        f'projected T lifetime counter regressed: {key} at PC {index}')
        previous = dict(t_values, seconds=seconds)

        b4_value = count(b4, 'applies', f'projected PC {index} B4')
        s_value = count(coarse, 'calls', f'projected PC {index} S')
        cached_values = {key: count(cached, key, f'projected PC {index} cached A4')
                         for key in ('started', 'completed')}
        bottom_values = {key: count(bottom, key, f'projected PC {index} bottom')
                         for key in ('MatSolve', 'refinement')}
        entity_values = {key: count(entities, key, f'projected PC {index} entity')
                         for key in ('HT', 'F', 'FH', 'E', 'EH', 'volume', 'volume_adjoint')}
        joint_values = {key: count(joint, key, f'projected PC {index} joint')
                        for key in ('applications', 'sequential_applications', 'T_started',
                                    'T_completed', 'patch_apply_rhs', 'patch_MatSolve',
                                    'group0_patch_apply_rhs', 'group1_patch_apply_rhs',
                                    'patch_LU', 'restored_factors')}
        if b4_value is None or s_value is None or any(value is None for value in cached_values.values()) or \
                any(value is None for value in bottom_values.values()) or \
                any(value is None for value in entity_values.values()) or \
                any(value is None for value in joint_values.values()):
            continue
        if last is not None:
            for key in joint_values:
                require(joint_values[key] >= last['joint'][key],
                        f'projected joint lifetime counter regressed: {key} at PC {index}')
        delta_t = {key: t_values[key] - base_T[key] for key in t_keys}
        delta_b4 = b4_value - base_b4
        delta_s = s_value - base_s
        delta_cached = {key: cached_values[key] - base_cached[key]
                        for key in cached_values}
        delta_bottom = {key: bottom_values[key] - base_bottom[key]
                        for key in bottom_values}
        delta_entities = {key: entity_values[key] - base_entities[key]
                          for key in entity_values}
        delta_joint = {key: joint_values[key] - base_joint[key]
                       for key in joint_values}
        require(all(value >= 0 for value in (*delta_t.values(), delta_b4, delta_s,
                                               *delta_bottom.values(),
                                               *delta_entities.values(), *delta_joint.values())),
                f'projected lifetime counter regressed across setup at PC {index}')
        calls = delta_t['calls']
        require(delta_b4 == calls and delta_entities['HT'] == calls,
                f'projected PC {index} B4/HT/T call deltas differ')
        require(delta_t['F'] == calls and delta_t['FH'] == calls and
                delta_t['A4'] == 2 * calls and delta_t['CU'] == calls,
                f'projected PC {index} T physical/coarse costs differ')
        require(delta_cached['started'] == delta_cached['completed'] ==
                3 * delta_b4 + 2 * calls,
                f'projected PC {index} cached A4 cost misses base or T actions')
        require(delta_joint['applications'] == calls and
                delta_joint['sequential_applications'] == calls and
                delta_joint['T_started'] == calls and delta_joint['T_completed'] == calls,
                f'projected PC {index} does not have one complete T per apply')
        require(delta_joint['group0_patch_apply_rhs'] + delta_joint['group1_patch_apply_rhs'] == 252 * calls and
                delta_joint['patch_apply_rhs'] == 252 * calls and
                delta_joint['patch_MatSolve'] == 252 * calls,
                f'projected PC {index} patch backsolve count differs from 252*T')
        require(joint_values['patch_LU'] == base_joint['patch_LU'] and
                joint_values['restored_factors'] == base_joint['restored_factors'] == 252,
                f'projected PC {index} refactored or lost restored factors')
        require(delta_entities['F'] == 2 * calls and delta_entities['FH'] == 2 * calls and
                delta_entities['E'] == 5 * calls and delta_entities['volume'] == 5 * calls and
                delta_entities['EH'] == 2 * calls and
                delta_entities['volume_adjoint'] == 2 * calls,
                f'projected PC {index} physical F/CU callback costs differ')
        # The two ordinary BAL_H C calls cost 2 logical S applications per
        # B4. T contributes one additional coarse/S feedback. A bottom
        # refinement performs one extra physical S action and is reported
        # separately; it is not a patch MatSolve.
        logical_s = delta_s - delta_bottom['refinement']
        require(logical_s == 2 * delta_b4 + delta_t['CU'] and
                delta_bottom['MatSolve'] == delta_s,
                f'projected PC {index} coarse S logical cost differs')
        last = dict(projected=t_values, joint=joint_values, entities=entity_values,
                    b4=b4_value, S=s_value, cached=cached_values,
                    bottom=bottom_values)

    terminal = list(exit_rows or [])[-1].get('total', {}) if exit_rows else {}
    terminal_trace = terminal.get('trace', {}) if isinstance(terminal, dict) else {}
    require(isinstance(terminal_trace, dict), 'projected terminal trace snapshot is missing')
    if isinstance(terminal_trace, dict) and last is not None:
        terminal_projected = terminal_trace.get('projected_T')
        terminal_joint = terminal_trace.get('joint')
        terminal_entities = terminal_trace.get('counts')
        terminal_b4 = terminal.get('B4', {}) if isinstance(terminal, dict) else {}
        terminal_s = terminal.get('S_action', {}) if isinstance(terminal, dict) else {}
        terminal_cached = terminal.get('cached', {}).get('counts', {}) \
            if isinstance(terminal, dict) else {}
        terminal_bottom = terminal.get('bottom', {}).get('counts', {}) \
            if isinstance(terminal, dict) else {}
        for key, value in last['projected'].items():
            actual = scalar(terminal_projected, key, 'projected terminal T')
            require(actual is not None and np.isclose(actual, float(value), rtol=0, atol=1e-10),
                    f'projected terminal T counter differs: {key}')
        for key, value in last['joint'].items():
            actual = count(terminal_joint, key, 'projected terminal joint')
            require(actual == value, f'projected terminal joint counter differs: {key}')
        for key, value in last['entities'].items():
            actual = count(terminal_entities, key, 'projected terminal entity')
            require(actual == value, f'projected terminal entity counter differs: {key}')
        require(count(terminal_b4, 'applies', 'projected terminal B4') == last['b4'],
                'projected terminal B4 counter differs')
        require(count(terminal_s, 'calls', 'projected terminal S') == last['S'],
                'projected terminal S counter differs')
        for key, value in last['cached'].items():
            actual = count(terminal_cached, key, 'projected terminal cached A4')
            require(actual == value, f'projected terminal cached A4 counter differs: {key}')
        for key, value in last['bottom'].items():
            actual = count(terminal_bottom, key, 'projected terminal bottom')
            require(actual == value, f'projected terminal bottom counter differs: {key}')

    setup_calls = base_T['calls']
    return dict(passed=not errors, errors=errors,
                completed_pc_count=len(pc_rows),
                T_calls=(last['projected']['calls'] - setup_calls) if last else 0,
                patch_backsolves=(last['joint']['patch_MatSolve'] - base_joint['patch_MatSolve'])
                if last else 0,
                bottom_mat_solves=(last['bottom']['MatSolve'] - base_bottom['MatSolve'])
                if last else 0,
                setup=projected)


def bounded_output_classification(summary, errors, expected_errors=()):
    """Classify bounded results without allowing schema errors to pass."""
    if not errors:
        if summary.get('status') == 'RESIDUAL_PASS':
            # Bounded V7 is a separate accounting path, but its successful
            # result remains consumed by the existing balanced output gate.
            return 'BALANCED_OUTPUT_PASS'
        if summary.get('status') in _BOUNDED_NEGATIVE_STATUSES:
            return summary['status']
        if summary.get('status') in ('BALANCED_OUTPUT_PASS',
                                     'BALANCED_OUTPUT_AUTHORITY_LIMITED'):
            return summary['status']
        return 'CORRECTNESS_OR_EVIDENCE_BLOCKED'
    if summary.get('status') in _BOUNDED_NEGATIVE_STATUSES:
        return (summary['status'] if all(error in expected_errors for error in errors)
                else 'CORRECTNESS_OR_EVIDENCE_BLOCKED')
    return 'NUMERICAL_OR_OUTPUT_FAIL'


def recompute_positive_apply_counts(pc_records: list[dict], cycles: list[dict]) -> dict:
    """Count recorded calls, not the sum of lifetime apply ordinals.

    Only completed PC records are covered; an interrupted PC has no inferred cost.
    This read-only audit does not change the historical ledger or solver verdict.
    """
    previous = {'s6': 0, 's3': 0}
    light = bool(pc_records and pc_records[0].get('positive_identity') == 'H6')
    keys = _POSITIVE_APPLY_KEYS + (('h6_apply_count', 'b6_action_count', 'positive_p1_apply_count') if light else ())
    h6_ordinal = 0
    per_pc = []
    for index, pc in enumerate(pc_records, 1):
        if pc['apply_count'] != index:
            raise ValueError('noncontiguous completed PC records')
        counts = {'s6_apply_count': 0, 's3_apply_count': 0}
        if light:
            if pc.get('positive_identity') != 'H6':
                raise ValueError('mixed positive identities in one run')
            counts.update(h6_apply_count=0, b6_action_count=0, positive_p1_apply_count=0)
        for direction in pc['direction_facts']:
            positive = direction.get('positive_cycle_facts')
            if positive is None:
                continue
            if light:
                if positive['apply_count'] != h6_ordinal+1 or positive['matrix_mult_count'] != 2:
                    raise ValueError('H6 ordinal or actual B6 count mismatch')
                h6_ordinal += 1
                counts['h6_apply_count'] += 1
                counts['b6_action_count'] += positive['matrix_mult_count']
                if 'lower_cycle_facts' in positive:
                    raise ValueError('H6 evidence unexpectedly contains a coarse cycle')
                continue
            for prefix, facts in (('s6', positive), ('s3', positive['lower_cycle_facts'])):
                ordinal = facts['apply_count']
                if ordinal != previous[prefix] + 1:
                    raise ValueError(f'noncontiguous {prefix} lifetime ordinal')
                previous[prefix] = ordinal
                counts[prefix + '_apply_count'] += 1
        if light and (counts['h6_apply_count'] != 2 or counts['b6_action_count'] != 4):
            raise ValueError('light PC did not execute two H6/four B6 calls')
        per_pc.append(counts)
    offset, corrected = 0, []
    for cycle in cycles:
        count = cycle['pc_apply_count']
        if count < 0 or offset + count > len(per_pc):
            raise ValueError('cycle exceeds completed PC records')
        selected = per_pc[offset:offset + count]
        values = {key: sum(row[key] for row in selected) for key in keys}
        corrected.append(dict(cycle_index=cycle['cycle_index'], end_iteration=cycle['end_iteration'],
            completed_pcs=count, recomputed=values,
            raw_reported={key: cycle['pc_costs'][key] for key in values}))
        offset += count
    return dict(scope='completed PC records only; partial PC costs unavailable', cycles=corrected,
        total={key: sum(row[key] for row in per_pc) for key in keys},
        completed_pc_count=len(per_pc), completed_pcs_after_last_cycle=len(per_pc)-offset,
        tail={key: sum(row[key] for row in per_pc[offset:]) for key in keys})


def recompute_p4_decisions(decisions, pc_rows):
    groups={};errors=[];external=0
    for row in decisions:
        logical=row['logical_rhs'];iteration=row['refinement_steps']
        group=groups.setdefault(logical,[])
        relative=row['true_residual_norm']/max(row['original_rhs_norm'],np.finfo(float).tiny)
        if (iteration!=len(group) or iteration>2 or row['external_solves']-external not in (0,1) or
                not np.isfinite(relative) or abs(relative-row['final_true_residual'])>1e-12):
            errors.append('decision ordering/norm/count mismatch')
        if group and (group[-1]['final_true_residual']<=1e-10 or
                      group[0]['original_rhs_norm']!=row['original_rhs_norm']):
            errors.append('refinement after pass or changed normalization')
        external=row['external_solves']
        group.append(row)
    if list(groups)!=list(range(1,len(groups)+1)):
        errors.append('noncontiguous logical RHS')
    if any(g[-1]['true_residual_norm']/max(g[-1]['original_rhs_norm'],np.finfo(float).tiny)>1e-10 for g in groups.values()):
        errors.append('final A4 residual missed')
    if external!=sum(r['p4_counts']['MatSolve'] for r in pc_rows) or len(groups)!=sum(r['p4_counts']['C'] for r in pc_rows):
        errors.append('PC/MatSolve totals differ')
    return dict(passed=not errors,errors=errors,logical_rhs=len(groups),MatSolve=external,
                refinements=len(decisions)-len(groups))


def recompute_balanced_screen(solve, rows):
    if not solve['screen_enabled']:
        return dict(matches=solve.get('screen') is None, enabled=False)
    history=[]; decision=None
    for row in rows:
        i=row['iteration']; r=row['explicit_true_residual']
        if i and i%32==0 and (not history or history[-1][0]!=i):
            history=(history+[(i,r)])[-3:]
        if i>=128 or row['solve_seconds']>=1800:
            if r<=1e-6 and solve.get('screen') is None:
                return dict(matches=True,converged_before_screen=True)
            trend=(len(history)==3 and history[1][0]-history[0][0]==32 and
                history[2][0]-history[1][0]==32 and 0<history[2][1]<history[1][1]<history[0][1]
                and np.sqrt(history[2][1]/history[0][1])<=.65)
            decision=dict(iteration=i,passed=bool(r<=1e-2 or trend));break
    saved=solve.get('screen')
    matches=(saved is None) if decision is None else (saved is not None and
        saved['iteration']==decision['iteration'] and saved['passed']==decision['passed'])
    return dict(matches=matches,recomputed=decision)


def balanced_output_classification(summary, errors, expected_errors=()):
    if not errors:
        return ('BALANCED_OUTPUT_AUTHORITY_LIMITED' if
            summary.get('matched_reference',{}).get('status')=='REFERENCE_AUTHORITY_LIMITED'
            else 'BALANCED_OUTPUT_PASS')
    if summary['status'] in ('SCREEN_BUDGET_NO_QUALIFIED_PROGRESS',
                            'PERFORMANCE_CONTROLLED_STOP','ITERATION_BUDGET_EXHAUSTED'):
        return summary['status'] if all(e in expected_errors for e in errors) else 'CORRECTNESS_OR_EVIDENCE_BLOCKED'
    return 'NUMERICAL_OR_OUTPUT_FAIL'


def check(directory: Path) -> dict:
    started = time.monotonic()
    summary = json.loads((directory / 'physical_intermediate_summary.json').read_text())
    errors, facts, expected_errors = [], {}, []
    controlled = summary['status'] in ('SCREEN_BUDGET_NO_QUALIFIED_PROGRESS',
        'PERFORMANCE_CONTROLLED_STOP', 'ITERATION_BUDGET_EXHAUSTED',
        *_BOUNDED_NEGATIVE_STATUSES)

    def require(condition, message, *, expected=False):
        if not condition:
            errors.append(message)
            if expected:
                expected_errors.append(message)

    def hashed_file(filename, digest):
        path = directory / filename
        require(path.is_relative_to(directory) and path.is_file(), f'missing artifact: {filename}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'artifact hash mismatch: {filename}')
        return path

    if 'recovery' in summary:
        recovery = summary['recovery']
        origin = Path(recovery['original_directory']).resolve()
        audit_path = Path(recovery['original_audit_path'])
        require(hashlib.sha256(audit_path.read_bytes()).hexdigest() == recovery['original_audit_sha256'],
                'recovery original audit hash mismatch')
        audit = json.loads(audit_path.read_text())
        require(Path(audit['run_directory']).resolve() == origin, 'recovery original path mismatch')
        old_path = origin/'physical_intermediate_summary.json'
        require(hashlib.sha256(old_path.read_bytes()).hexdigest() ==
                audit['artifact_sha256']['physical_intermediate_summary.json'], 'original summary hash mismatch')
        old = json.loads(old_path.read_text())
        require(summary['solve'] == old['solve'] and summary['source_sha'] == old['source_sha'] ==
                recovery['original_source_sha'], 'recovery changed original solve evidence')
        require(all(recovery[k] == 0 for k in ('new_factor_count','new_pc_count','new_ksp_count')),
                'recovery unexpectedly performed a new solve')
        for name in ('pc_applies.jsonl','p4_decisions.jsonl','monitor_residuals.jsonl'):
            require(hashlib.sha256((directory/name).read_bytes()).hexdigest() == audit['artifact_sha256'][name],
                    'recovery copied solve evidence differs: '+name)
        require(summary['final_solution_sha256'] == old['final_solution_sha256'], 'recovery solution identity changed')

    raw = summary['residual_arrays']
    from src.io.physical_balanced_profile import BALANCED_PROFILES, BOUNDED_PROFILES
    from src.io.physical_recursive_profile import RECURSIVE_PROFILES
    recursive = summary['profile']['identity'] in RECURSIVE_PROFILES
    bounded = summary['profile']['identity'] in BOUNDED_PROFILES
    balanced = recursive or summary['profile']['identity'] in BALANCED_PROFILES or bounded
    reference_only = summary['profile'].get('reference_only', False)
    if reference_only:
        ledger = summary['reference_pc_ledger']
        pc_rows = [json.loads(x) for x in hashed_file(ledger['filename'], ledger['sha256']).read_text().splitlines()]
        require(bool(pc_rows), 'missing reference PC solves')
        if balanced:
            decisions = [json.loads(x) for x in (directory/'p4_decisions.jsonl').read_text().splitlines()]
            facts['p4_decisions'] = recompute_p4_decisions(decisions,pc_rows)
            require(facts['p4_decisions']['passed'], 'native A4 final residual or accounting gate failed')
            facts['balanced_screen'] = recompute_balanced_screen(summary['solve'],
                [json.loads(x) for x in (directory/'monitor_residuals.jsonl').read_text().splitlines()])
            require(facts['balanced_screen']['matches'], 'screen decision differs from raw checkpoints')
            require(summary['solve']['ksp_create_count'] == summary['solve']['ksp_solve_count'] ==
                    summary['solve']['ksp_destroy_count'] == 1, 'not one live KSP')
        for row in ([] if balanced else pc_rows):
            inner = row['intermediate']
            numerator, denominator = inner['true_residual_norm'], inner['rhs_norm']
            relative = numerator / max(denominator, np.finfo(float).tiny)
            require(np.isfinite([numerator, denominator, relative]).all() and
                    min(numerator, denominator) >= 0 and relative <= 1e-10,
                    'original A4 reference residual gate failed')
            require(abs(relative-inner['final_true_residual']) <= 1e-12,
                    'reference norm/residual mismatch')
    if recursive:
        from src.io.physical_intermediate_profile import profile_facts
        require(summary['profile']==profile_facts(summary['profile']['identity']),'recursive resolved contract differs')
        from benchmarks.physical_recursive_checker import recompute_recursive
        rows={name:[json.loads(x) for x in hashed_file(name,digest).read_text().splitlines()]
              for name,digest in summary['recursive_evidence'].items()}
        facts['recursive']=recompute_recursive(rows['pc_applies.jsonl'],rows['recursive_inner.jsonl'],
            rows['recursive_exit_audit.jsonl'],summary)
        require(facts['recursive']['passed'],'recursive accounting/closure failed: '+str(facts['recursive']['errors']))
        facts['balanced_screen']=recompute_balanced_screen(summary['solve'],
            [json.loads(x) for x in (directory/'monitor_residuals.jsonl').read_text().splitlines()])
        require(facts['balanced_screen']['matches'],'screen differs from raw checkpoints')
        require(summary['solve']['ksp_create_count']==summary['solve']['ksp_solve_count']==
                summary['solve']['ksp_destroy_count']==1,'not one live KSP')
    if bounded:
        from src.io.physical_intermediate_profile import profile_facts

        require(summary['profile'] == profile_facts(summary['profile']['identity']),
                'bounded resolved contract differs')
        bounded_evidence = summary.get('bounded_evidence', {})
        evidence_files = bounded_evidence.get('files', bounded_evidence)
        required_names = tuple(bounded_evidence.get('required', (
            'bounded_i4.jsonl', 'pc_applies.jsonl', 'bounded_exit_audit.jsonl',
            'monitor_residuals.jsonl', 'iterations.jsonl')))

        def read_bounded_jsonl(name):
            entry = evidence_files.get(name, {})
            digest = entry.get('sha256') if isinstance(entry, dict) else entry
            require(bool(digest), f'bounded evidence binding missing: {name}')
            path = hashed_file(name, digest) if digest else directory / name
            if not path.is_file():
                return []
            return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

        rows = {name: read_bounded_jsonl(name) for name in required_names}
        # A normal or controlled bounded solve must have the full five-file
        # evidence set.  This is an evidence/schema gate, not a numerical gate.
        require(set(required_names) == {
            'bounded_i4.jsonl', 'pc_applies.jsonl', 'bounded_exit_audit.jsonl',
            'monitor_residuals.jsonl', 'iterations.jsonl'},
                'bounded evidence required-file set differs from V7 contract')
        facts['bounded_i4'] = recompute_bounded_i4(
            rows['bounded_i4.jsonl'], rows['pc_applies.jsonl'],
            rows['bounded_exit_audit.jsonl'])
        require(facts['bounded_i4']['passed'],
                'bounded I4/PC/H6/closure accounting failed: '+
                str(facts['bounded_i4']['errors']))
        call_policy = summary.get('bounded_setup', {}).get('actual_calls_per_PC', {})
        require(call_policy.get('I4') == 2 and call_policy.get('H6') == 1,
                'bounded call-policy metadata does not state I4=2/H6=1 per PC')
        require(facts['bounded_i4']['actual_h6_applies'] ==
                facts['bounded_i4']['completed_pc_count'],
                'actual H6 smoother count is not one per completed PC')
        facts['bounded_screen'] = recompute_bounded_screen(
            summary['solve'], rows['monitor_residuals.jsonl'])
        require(facts['bounded_screen']['passed'],
                'bounded V7 screen differs from raw nodes: '+
                str(facts['bounded_screen']['errors']))
        policy = summary.get('bounded_solve_policy', {})
        require(policy.get('solve_limit_seconds') == 10800,
                'bounded solve limit is not the required 10800 seconds')
        require(policy.get('outer_restart') == 32 and policy.get('outer_max_it') == 2048,
                'bounded solve policy does not bind restart32/max2048')
        setup_costs = summary.get('bounded_setup', {}).get('setup_costs',
                                                            summary.get('bounded_setup_costs'))
        require(isinstance(setup_costs, dict), 'bounded setup cost baseline is missing')
        facts['bounded_costs'] = recompute_bounded_costs(
            rows['bounded_i4.jsonl'], rows['pc_applies.jsonl'],
            rows['bounded_exit_audit.jsonl'], setup_costs,
            require_lifetime=True)
        require(facts['bounded_costs']['passed'],
                'bounded cumulative cost accounting failed: '+
                str(facts['bounded_costs']['errors']))
        storage = summary.get('bounded_setup', {}).get('trace_storage')
        from src.io.physical_balanced_profile import BOUNDED_PROJECTED_PROFILE
        projected_route = summary['profile']['identity'] == BOUNDED_PROJECTED_PROFILE
        route_fact = summary.get('bounded_setup', {}).get('route', {})
        if projected_route:
            require(isinstance(route_fact, dict) and
                    route_fact.get('route') == 'PROJECTED_SEQ2_16',
                    'projected profile does not bind PROJECTED_SEQ2_16 route')
            facts['bounded_projected_trace'] = recompute_projected_trace_costs(
                rows['pc_applies.jsonl'], rows['bounded_exit_audit.jsonl'], storage,
                setup_costs)
            require(facts['bounded_projected_trace']['passed'],
                    'projected full252/T accounting failed: ' +
                    str(facts['bounded_projected_trace']['errors']))
        elif isinstance(storage, dict) and storage.get('projected') is not None:
            require(False, 'non-projected bounded profile carries projected trace storage')
        iteration_rows = rows['iterations.jsonl']
        require(bool(iteration_rows), 'bounded iterations ledger is empty')
        if iteration_rows:
            values = [row.get('iteration') for row in iteration_rows]
            require(values == sorted(values), 'bounded iterations ledger is not monotone')
            require(values[-1] == summary['solve']['iterations'],
                    'bounded iterations ledger does not end at solve iteration')

        binding = summary.get('bounded_binding', {})
        require(isinstance(binding, dict) and isinstance(storage, dict),
                'bounded source/physical/mode/RHS/storage binding is missing')
        if isinstance(binding, dict) and isinstance(storage, dict):
            require(binding.get('source_sha') == summary.get('source_sha'),
                    'bounded source identity binding mismatch')
            require(binding.get('physical_model_sha256') == raw.get('physical_model_sha256'),
                    'bounded physical-model binding mismatch')
            require(binding.get('mode_sha256') == summary.get('mode_sha256'),
                    'bounded mode binding mismatch')
            require(binding.get('input_sha256') == raw.get('input_sha256'),
                    'bounded RHS input binding mismatch')
            require(binding.get('operator_identity_sha256') == raw.get('operator_identity_sha256'),
                    'bounded operator binding mismatch')
            require(binding.get('storage_sha256') == _stable_sha256(storage),
                    'bounded storage binding mismatch')
    with np.load(hashed_file(raw['filename'], raw['sha256']), allow_pickle=False) as arrays:
        rhs, action, solution = arrays['rhs'], arrays['action'], arrays['solution']
        require(rhs.shape == action.shape == solution.shape, 'incompatible raw vector shapes')
        if bounded:
            binding = summary.get('bounded_binding', {})
            rhs_sha = hashlib.sha256(rhs.tobytes()).hexdigest()
            require(binding.get('rhs_sha256') == rhs_sha,
                    'bounded RHS bytes identity differs')
            require(summary.get('rhs', {}).get('vector_sha256') == rhs_sha,
                    'bounded RHS summary hash differs')
        if recursive:
            require(hashlib.sha256(rhs.tobytes()).hexdigest()==summary['recursive_identity']['rhs_sha256'],
                    'recursive raw RHS identity differs')
        require(all(np.isfinite(v).all() for v in (rhs, action, solution)), 'nonfinite raw vectors')
        if 'recovery' in summary:
            require(hashlib.sha256(solution.tobytes()).hexdigest() == summary['final_solution_sha256'],
                    'recovery actual solution bytes hash mismatch')
            old_raw = old['residual_arrays']
            old_raw_path = (origin/old_raw['filename']).resolve()
            require(old_raw_path.is_relative_to(origin), 'recovery original raw path escapes origin')
            old_digest = hashlib.sha256(old_raw_path.read_bytes()).hexdigest()
            require(old_digest == old_raw['sha256'] == audit['artifact_sha256'][old_raw['filename']],
                    'recovery original residual arrays hash mismatch')
            with np.load(old_raw_path, allow_pickle=False) as old_arrays:
                differences = {}
                for name, value in (('rhs', rhs), ('action', action)):
                    prior = old_arrays[name]
                    difference = (float(np.linalg.norm(value-prior)/max(np.linalg.norm(prior),np.finfo(float).tiny))
                                  if value.shape == prior.shape else float('inf'))
                    differences[name] = difference
                    require(np.isfinite(difference) and difference <= 1e-10,
                            'recovery original '+name+' relative difference exceeds 1e-10')
                facts['recovery_original_array_differences'] = differences
        residual = np.linalg.norm(rhs-action)/max(np.linalg.norm(rhs), np.finfo(float).tiny)
        facts['full_explicit_true_relative_residual'] = float(residual)
        require(np.isfinite(residual) and residual <= 1e-6, f'fine residual {residual} exceeds 1e-6',
                expected=controlled and bool(np.isfinite(residual)))
        solve = summary['solve']
        require(abs(residual-solve['final_true_residual']) <= max(1e-12, .001*residual), 'raw/reported true residual mismatch')
        require(solve['reason'] >= 0 or solve['reason'] == -3, f'KSP breakdown reason {solve["reason"]}')
        for cycle in solve.get('cycles', []):
            reported = cycle['reported_final_residual']/max(np.linalg.norm(rhs), np.finfo(float).tiny)
            difference = abs(reported-cycle['explicit_true_residual'])
            require(np.isfinite(difference) and difference <= max(1e-10, .01*cycle['explicit_true_residual']),
                    f'reported/true norm mismatch at iteration {cycle["end_iteration"]}: {difference}')
    from src.io.physical_intermediate_profile import profile_facts
    resources = profile_facts(summary['profile']['identity'])['resources']
    light = summary['profile']['identity'] == 'p6smooth_p4ref_p6smooth_v1'
    stagnation = False
    if light:
        cycles = [json.loads(line) for line in (directory/'cycles.jsonl').read_text().splitlines()]
        require(bool(pc_rows) and all(row.get('positive_identity') == 'H6' for row in pc_rows),
                'LIGHT profile requires explicit H6 identity on every PC record')
        facts['light_pc_counts'] = recompute_positive_apply_counts(pc_rows, cycles)
        require(all(row['recomputed'] == row['raw_reported'] for row in facts['light_pc_counts']['cycles']),
                'raw cycle PC counts disagree with independently recomputed calls')
        require(all(row['direction_count'] == 3 and
                    sum(d['fine_action_count'] for d in row['direction_facts']) == 3
                    and row['intermediate']['factor_solve_calls'] == 1 for row in pc_rows),
                'light PC must have three original A6 MR actions and one A4 backsolve')
        require(summary['positive_setup']['positive_p3_p1_constructed'] is False,
                'unused positive coarse objects were constructed')
        if len(cycles) >= 5 and cycles[-1]['end_iteration'] >= 256:
            tail = list(zip(cycles[-5:-1], cycles[-4:]))
            stagnation = all(c['iterations'] == 32 and c['end_iteration']-c['start_iteration'] == 32
                and p['end_iteration'] == c['start_iteration'] and p['explicit_true_residual'] > 0
                and np.isfinite([p['explicit_true_residual'], c['explicit_true_residual']]).all()
                and c['explicit_true_residual']/p['explicit_true_residual'] >= .99 for p, c in tail)
        facts['stagnation_from_raw_cycles'] = bool(stagnation)
        if summary['status'] == 'STAGNATION_CONTROLLED_STOP':
            require(stagnation, 'claimed stagnation does not satisfy raw four-cycle rule')
        with np.load(directory/raw['filename'], allow_pickle=False) as arrays:
            require(hashlib.sha256(arrays['solution'].tobytes()).hexdigest() == summary['final_solution_sha256'],
                    'final solution hash mismatch before recovery')
    require(summary.get('solve_conservative_seconds', summary['solve_monotonic_seconds']) <= resources['solve_seconds'], 'solve budget exceeded', expected=summary['status']=='PERFORMANCE_CONTROLLED_STOP')
    require(summary.get('elapsed_conservative_seconds', summary['elapsed_monotonic_seconds']) <= resources['workflow_seconds'], 'workflow budget exceeded before checker', expected=summary['status']=='PERFORMANCE_CONTROLLED_STOP')
    require(summary['auxiliary_stack_released_before_recovery'] is True, 'auxiliary stack not released')
    output = summary.get('official_result')
    if output is None:
        require(False,'official outputs unavailable',expected=controlled)
    else:
        port, volume = output['port_metrics'], output['volume_metrics']
        r, t, a, av = port['R_total'], port['T_total'], port['A_balance'], volume['A_volume_total']
        facts['physics'] = dict(R=r, T=t, A=a, A_volume=av,
                               volume_energy_error=abs(r+t+av-1), absorption_difference=abs(a-av))
        require(np.isfinite([r, t, a, av]).all(), 'nonfinite R/T/A/A_volume')
        require(abs(r+t+av-1) <= 1e-5, f'independent volume energy error {abs(r+t+av-1)} exceeds 1e-5')
        require(abs(a-av) <= 1e-5, f'absorption difference {abs(a-av)} exceeds 1e-5')
        require(min(r, t, a, av) >= -1e-12, f'passivity sign error: {r,t,a,av}')
        modal = json.loads((directory / 'numerical_output/dtn_port_diffraction_orders_3d.json').read_text())
        rows = modal['orders']
        require(len(rows) == port['dtn_port_mode_count'], 'incomplete mode output')
        keys = [(row['side'], row['m'], row['n'], row['polarization']) for row in rows]
        require(len(keys) == len(set(keys)), 'duplicate mode keys')
        require(abs(sum(row['R'] for row in rows)-r) <= 1e-12, 'reflection channel sum mismatch')
        require(abs(sum(row['T'] for row in rows)-t) <= 1e-12, 'transmission channel sum mismatch')
        require(all(np.isfinite([row['R'], row['T'], row['power_ratio']]).all() and
                    min(row['R'], row['T']) >= -1e-12 for row in rows), 'nonfinite or negative channel power')
        amplitudes = json.loads((directory / 'numerical_output/dtn_auxiliary_amplitudes_3d.json').read_text())
        require(len(amplitudes) == len(rows), 'incomplete complex modal amplitudes')
        def finite_numbers(value):
            if isinstance(value, dict):
                return all(finite_numbers(v) for v in value.values())
            if isinstance(value, list):
                return all(finite_numbers(v) for v in value)
            return not isinstance(value, (int, float)) or bool(np.isfinite(value))
        require(finite_numbers(amplitudes), 'nonfinite complex modal amplitudes')
        exported = output['field_export']
        samples = Path(exported['full3d_reference_archive'])
        require(hashlib.sha256(samples.read_bytes()).hexdigest() == exported['full3d_reference_archive_sha256'],
                'E/H sample hash mismatch')
        with np.load(samples, allow_pickle=False) as arrays:
            e, h = arrays['E_V_per_m'], arrays['H_A_per_m']
            require(e.shape == h.shape and e.ndim == 4 and e.shape[-1] == 3, 'E/H sample shape mismatch')
            require(np.iscomplexobj(e) and np.iscomplexobj(h) and np.isfinite(e).all() and np.isfinite(h).all(),
                    'invalid complex E/H samples')
            require(all(np.isfinite(arrays[k]).all() for k in ('x_nm', 'y_nm', 'z_nm')), 'nonfinite sample coordinates')
        canonical = output['canonical_vector']
        hashed_file('numerical_output/' + canonical['filename'], canonical['file_sha256'])
        from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard

        packets = read_canonical_packet_shard(directory / 'numerical_output' / canonical['filename'])
        require(len(packets) == canonical['packet_count'] > 0, 'canonical packet count mismatch')
        require(all(np.isfinite(value) for _, value in packets), 'nonfinite canonical coefficients')
    if balanced and output is not None:
        matched = summary.get('matched_reference', {})
        require(matched.get('status') in (('MATCHED_REFERENCE_PASS',) if recursive or bounded else
            ('MATCHED_REFERENCE_PASS','REFERENCE_AUTHORITY_LIMITED')), 'matched reference failed')
        require(summary['rss_after_release'] < summary['rss_before_release'], 'RSS did not decrease before recovery')
    independent_output_gates_passed = not errors
    classification = ('REFERENCE_ONLY_PASS' if reference_only else 'DISCRETE_SOLVER_OUTPUT_PASS') if not errors else 'NUMERICAL_OR_OUTPUT_FAIL'
    if light and errors and summary['status'] == 'STAGNATION_CONTROLLED_STOP' and stagnation:
        classification = 'STAGNATION_CONTROLLED_STOP'
    elif light and errors and summary['status'] == 'ITERATION_BUDGET_EXHAUSTED' and summary['solve']['iterations'] == 2048:
        classification = 'ITERATION_BUDGET_EXHAUSTED'
    if bounded:
        classification = bounded_output_classification(summary, errors, expected_errors)
    elif balanced:
        classification = balanced_output_classification(summary,errors,expected_errors)
    return dict(classification=classification,
                reference_authority=summary.get('matched_reference',{}).get('status','PENDING_A4_not_compared'),
                independent_output_gates_passed=independent_output_gates_passed,
                gate_failures=errors, raw_facts=facts, checker_seconds=time.monotonic()-started,
                resource_authority='separate enclosing parent verdict required')


def main() -> int:
    directory = Path(sys.argv[1]).resolve()
    try:
        result = check(directory)
    except Exception as exc:
        result = dict(classification='EVIDENCE_INCOMPLETE', reference_authority='PENDING_A4_not_compared',
                      gate_failures=[f'{type(exc).__name__}: {exc}'])
    (directory / 'checker.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return 0 if result['classification'] in ('DISCRETE_SOLVER_OUTPUT_PASS', 'REFERENCE_ONLY_PASS',
        'BALANCED_OUTPUT_PASS', 'BALANCED_OUTPUT_AUTHORITY_LIMITED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
