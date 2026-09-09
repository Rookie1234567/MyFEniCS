"""Independent V7 bounded evidence checks; no FE assembly or PDE launch."""

import copy
import json
from pathlib import Path

import pytest


J1_ROOT = (Path(__file__).resolve().parents[2] / 'benchmarks' / 'artifacts' /
           'task39extra' / 'v7_j1_controls' /
           '874190e92e0f0639515715dd830cd275562c151f' / 'controls')


def _rows(root, name):
    return [json.loads(line) for line in (root / name).read_text().splitlines()
            if line.strip()]


@pytest.mark.skipif(not (J1_ROOT / 'bounded_i4.jsonl').is_file(),
                    reason='ignored J1 runtime artifacts are not present')
def test_real_j1_records_use_actual_one_h6_per_pc_and_separate_costs():
    from benchmarks.physical_intermediate_checker import (
        recompute_bounded_costs, recompute_bounded_i4,
    )

    i4 = _rows(J1_ROOT, 'bounded_i4.jsonl')
    pcs = _rows(J1_ROOT, 'pc_applies.jsonl')
    exits = _rows(J1_ROOT, 'bounded_exit_audit.jsonl')
    facts = recompute_bounded_i4(i4, pcs, exits)
    assert facts['passed'], facts['errors']
    assert facts['i4_calls'] == 4
    assert facts['completed_pc_count'] == 2
    assert facts['actual_h6_applies'] == 2  # one actual H6 smoother per PC
    costs = recompute_bounded_costs(i4, pcs, exits)
    assert costs['passed'], costs['errors']
    assert costs['i4_totals']['B4_calls'] == 64


def _inner(status='INNER_APPROXIMATE_RETURN', *, rhs_norm=2.0,
           residual=0.2, iterations=16, work=None):
    work = iterations if work is None else work
    return dict(status=status, target=1e-4, rhs_norm=rhs_norm,
                eps_norm=rhs_norm * residual, final_true_residual=residual,
                iterations=iterations,
                reason=-3, restart=16, max_it=16, zero_start=True,
                seconds=4.0, actual_elapsed_seconds=4.0,
                requested_safe_return=False, timeout_exceeded=False,
                stop_reason='MAX_IT', legal_direction_count=work,
                A4_matvec=work, B4_calls=work, explicit_A4=0 if work == 0 else 3,
                attempted=dict(A4_matvec=work, B4_calls=work,
                               explicit_A4=0 if work == 0 else 3))


def _pc(index, first, second, *, audited):
    audit = dict(actual_audit='PASS' if audited else 'not_sampled')
    if audited:
        audit['audit'] = dict(closure_norm=1e-12, operation_scale=1.0,
                              closure_relative=1e-12)
    return dict(apply_count=index, route='BAL_H', status='BALANCED_ACTION_COMPLETED',
                counts=dict(C=2, smoother=1, A_structure=2, A_inner_true=0,
                            PH_audit=0),
                inexact_balance={**audit, 'calls': [
                    dict(inner=copy.deepcopy(first)), dict(inner=copy.deepcopy(second))
                ]})


def test_fake_i4_accepts_target_approximate_and_zero_rhs_but_rejects_contract_mutation():
    from benchmarks.physical_intermediate_checker import recompute_bounded_i4

    zero = _inner('INNER_ZERO_RHS', rhs_norm=0.0, residual=0.0, iterations=0, work=0)
    target = _inner('INNER_TARGET_REACHED', rhs_norm=2.0, residual=5e-5,
                    iterations=2, work=2)
    pcs = [_pc(1, zero, target, audited=True)]
    exits = [dict(last_PC=1, audit_costs=dict(audits=1),
                  audit=dict(closure_norm=1e-12, operation_scale=1.0,
                             closure_relative=1e-12))]
    facts = recompute_bounded_i4([
        dict(call=1, facts=copy.deepcopy(zero)),
        dict(call=2, facts=copy.deepcopy(target)),
    ], pcs, exits)
    assert facts['passed'], facts['errors']
    assert facts['i4_totals']['B4_calls'] == 2

    broken_norm_i4 = [dict(call=1, facts=copy.deepcopy(zero)),
                      dict(call=2, facts=copy.deepcopy(target))]
    broken_norm_i4[1]['facts']['eps_norm'] *= 2
    failed_norm = recompute_bounded_i4(broken_norm_i4, pcs, exits)
    assert not failed_norm['passed']

    broken_pc = copy.deepcopy(pcs)
    broken_pc[0]['inexact_balance']['audit']['closure_norm'] = .1
    failed_closure = recompute_bounded_i4([
        dict(call=1, facts=copy.deepcopy(zero)),
        dict(call=2, facts=copy.deepcopy(target)),
    ], broken_pc, exits)
    assert not failed_closure['passed']

    broken = copy.deepcopy(target)
    broken['max_it'] = 15
    failed = recompute_bounded_i4([
        dict(call=1, facts=copy.deepcopy(zero)),
        dict(call=2, facts=broken),
    ], pcs, exits)
    assert not failed['passed']


def test_fake_v7_screen_recomputes_true_8_step_nodes_and_mid_budget_gate():
    from benchmarks.physical_intermediate_checker import recompute_bounded_screen

    rows = [dict(iteration=i, explicit_true_residual=1.0 / (i / 8),
                 solve_seconds=100.0) for i in range(8, 120, 8)]
    rows += [dict(iteration=120, explicit_true_residual=.04, solve_seconds=100.0),
             dict(iteration=128, explicit_true_residual=.02, solve_seconds=1800.0),
             dict(iteration=136, explicit_true_residual=.0005, solve_seconds=5400.0)]
    solve = dict(screen_enabled=True, screen_policy='v7', restart=32, max_it=2048,
                 zero_start=True, residual_interval=8, checkpoint_interval=32,
                 ksp_create_count=1, ksp_solve_count=1, ksp_destroy_count=1,
                 screen=dict(status='SCREEN_CONTINUE_SAME_LIVE_KSP', passed=True,
                             iteration=128, true_relative=.02, solve_seconds=1800.0,
                             checkpoints=[[112, 1.0 / 14], [120, .04], [128, .02]],
                             policy='v7'),
                 mid_budget=dict(status='MID_BUDGET_CONTINUE', passed=True,
                                 iteration=136, true_relative=.0005,
                                 solve_seconds=5400.0))
    facts = recompute_bounded_screen(solve, rows)
    assert facts['passed'], facts['errors']
    assert facts['nodes'][-3:] == [(120, .04), (128, .02), (136, .0005)]
    converged = copy.deepcopy(solve)
    converged['mid_budget'] = None
    converged_rows = copy.deepcopy(rows)
    converged_rows[-1]['explicit_true_residual'] = 1e-7
    late_pass = recompute_bounded_screen(converged, converged_rows)
    assert late_pass['passed'], late_pass['errors']
    assert late_pass['recomputed_mid_budget'] is None
    solve['ksp_create_count'] = 2
    rejected = recompute_bounded_screen(solve, rows)
    assert not rejected['passed']
