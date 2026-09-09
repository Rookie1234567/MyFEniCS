"""J1 controls-only dispatch contracts; no FE assembly or formal PDE run."""

import json
from pathlib import Path


def _args():
    from src.runners.physical_recursive_entry import build_parser

    return build_parser().parse_args([
        '--input', 'input/task39extra/original_13p5nm_p6h10_bounded_entity16_v7.dat',
        '--inventory', 'benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json',
        '--budget', 'benchmarks/artifacts/task39extra/v7_j1_controls/j1_budget.json',
        '--output', 'benchmarks/artifacts/task39extra/v7_j1_controls/future',
        '--source-sha', 'a' * 40,
        '--bounded-j1-controls',
    ])


def test_j1_contract_is_two_q_controls_and_not_old_campaign():
    from src.runners.physical_recursive_entry import selected_contract

    contract = selected_contract(_args())
    assert contract['labels'] == ['A2R160', 'LIGHT448']
    assert contract['setup_count'] == 1
    assert contract['complete_PC_calls'] == 2
    assert contract['I4_calls'] == 4
    assert contract['old_recursive_campaign'] == 'not_called'
    assert contract['forbidden_inputs'] == ['e', 'reference_y', 'old_PC_outputs']
    assert contract['one_apply_contraction_gate'] == 'not_applied'
    assert contract['j0_j1_controls_limit_seconds'] == 3600


def test_j1_dispatch_does_not_enter_six_rhs_campaign(monkeypatch, tmp_path):
    from src.runners import physical_bounded_j1
    from src.runners.physical_recursive_entry import dispatch_components

    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return {'status': 'J1_CONTROLS_FIXTURE', 'complete_pc_calls': 2, 'I4_calls': 4}

    def forbidden(*args, **kwargs):
        raise AssertionError('old six-RHS/three-PC campaign was entered')

    monkeypatch.setattr(physical_bounded_j1, 'run_j1_controls', fake)
    monkeypatch.setattr('src.runners.physical_recursive_controls.run_recursive_components', forbidden)
    args = _args()
    result = dispatch_components(
        args, object(), object(), tmp_path, sample=lambda: None,
        marker=lambda *_: None, source_sha={'head': 'a' * 40},
        input_path=Path(args.input),
    )
    assert result['complete_pc_calls'] == 2
    assert result['I4_calls'] == 4
    assert len(calls) == 1
    assert calls[0][1]['contract']['setup_count'] == 1


def test_b_projected_controls_keep_two_q_contract_and_use_5400_budget(monkeypatch, tmp_path):
    from src.runners import physical_bounded_j1
    from src.runners.physical_recursive_entry import dispatch_components, selected_contract

    args = __import__('src.runners.physical_recursive_entry', fromlist=['build_parser']).build_parser().parse_args([
        '--input', 'input/task39extra/original_13p5nm_p6h10_bounded_projected_seq2_16_v7.dat',
        '--inventory', 'benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json',
        '--budget', 'benchmarks/artifacts/task39extra/v7_j1_controls/j1_budget.json',
        '--output', str(tmp_path), '--source-sha', 'a' * 40,
        '--bounded-j1-controls', '--bounded-j1-route', 'PROJECTED_SEQ2_16',
    ])
    contract = selected_contract(args)
    assert contract['route'] == 'PROJECTED_SEQ2_16'
    assert contract['complete_PC_calls'] == 2
    assert contract['I4_calls'] == 4
    assert contract['controls_limit_seconds'] == 5400
    assert contract['finite_comparison']['qualification'].endswith('qualification')

    calls = []

    def fake(*call_args, **call_kwargs):
        calls.append((call_args, call_kwargs))
        return {'status': 'B_FINITE_COMPARISON_AND_CONTROLS_COMPLETED'}

    monkeypatch.setattr(physical_bounded_j1, 'run_j1_controls', fake)
    result = dispatch_components(
        args, object(), object(), tmp_path, sample=lambda: None,
        marker=lambda *_: None, source_sha={'head': 'a' * 40},
        input_path=Path(args.input),
    )
    assert result['status'] == 'B_FINITE_COMPARISON_AND_CONTROLS_COMPLETED'
    assert calls[0][1]['contract']['controls_limit_seconds'] == 5400


def test_b_projected_controls_reserve_5400_in_same_batch_ledger(monkeypatch, tmp_path):
    from src.runners import physical_recursive_entry as entry

    budget_path = tmp_path / 'shared-budget.json'
    budget_path.write_text(json.dumps({
        'schema': entry.J1_BUDGET_SCHEMA,
        'limit_seconds': entry.J1_BATCH_LIMIT_SECONDS,
        'j0_j1_controls_limit_seconds': entry.J1_CONTROLS_LIMIT_SECONDS,
        'attempts': [
            {'kind': 'original', 'status': 'WORKER_FAILED', 'elapsed_seconds': 100.0},
            {'kind': 'B_preparation', 'budget_group': 'B_projected_controls',
             'status': 'COMPLETED', 'elapsed_seconds': 17.0},
        ],
    }))
    output = tmp_path / 'b-controls'
    args = __import__('src.runners.physical_recursive_entry', fromlist=['build_parser']).build_parser().parse_args([
        '--input', 'input/task39extra/original_13p5nm_p6h10_bounded_projected_seq2_16_v7.dat',
        '--inventory', 'benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json',
        '--budget', str(budget_path), '--output', str(output), '--source-sha', 'a' * 40,
        '--bounded-j1-controls', '--bounded-j1-route', 'PROJECTED_SEQ2_16',
    ])
    monkeypatch.setattr(entry, 'git_state', lambda expected: {'head': expected, 'clean': True})
    monkeypatch.setattr('benchmarks.subreaper_watchdog.supervise',
                        lambda *args, **kwargs: {'classification': 'COMPLETED',
                                                  'descendants_cleared': True})
    samples = iter([
        dict(monotonic=10.0, boottime=20.0, utc_ns=100_000_000_000),
        dict(monotonic=14.0, boottime=24.0, utc_ns=104_000_000_000),
    ])
    monkeypatch.setattr('src.runners.workflow_timebase.clock_sample', lambda: next(samples))
    result = entry._launch_j1_controls(args)
    assert result['classification'] == 'COMPLETED'
    budget = json.loads(budget_path.read_text())
    entry_row = budget['attempts'][-1]
    assert entry_row['kind'] == 'bounded_projected_controls'
    assert entry_row['budget_group'] == 'B_projected_controls'
    assert entry_row['controls_limit_seconds'] == 5400
    assert entry_row['elapsed_seconds'] == 4.0
    assert budget['b_projected_controls_charged_seconds'] == 21.0
    assert budget['b_projected_controls_remaining_seconds'] == 5379.0


def test_j1_budget_schema_is_separate_from_old_v6(tmp_path):
    from src.runners.physical_recursive_entry import (
        J1_BATCH_LIMIT_SECONDS,
        J1_BUDGET_SCHEMA,
        J1_CONTROLS_LIMIT_SECONDS,
        _j1_charge_seconds,
    )

    path = tmp_path / 'j1_budget.json'
    path.write_text(json.dumps({
        'schema': J1_BUDGET_SCHEMA,
        'limit_seconds': J1_BATCH_LIMIT_SECONDS,
        'j0_j1_controls_limit_seconds': J1_CONTROLS_LIMIT_SECONDS,
        'attempts': [
            {'kind': 'J0_focused_tests', 'budget_group': 'J0_J1_controls',
             'status': 'COMPLETED', 'elapsed_seconds': 94.29,
             'clock_qualification': 'single_process_wall; no dual-clock record'},
        ],
        'old_v6_ledger': 'independent',
    }))
    budget = json.loads(path.read_text())
    assert _j1_charge_seconds(budget) == 94.29
    assert budget['j0_j1_controls_limit_seconds'] == 3600
    assert budget['limit_seconds'] == 43200
