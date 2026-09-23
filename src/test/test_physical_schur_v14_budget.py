"""V14 batch costs survive failed launches, source changes and hard stops."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.input_loader import InputError
from src.runners import task038_launcher as launcher


def _clock(seconds):
    return dict(monotonic=seconds, boottime=seconds, utc_ns=int(seconds * 1e9))


def _reserve(tmp_path, stage='Q1_FULL_DIRECT', source='a' * 40):
    directory = tmp_path / f'{stage}_{source[0]}'
    directory.mkdir(exist_ok=True)
    return launcher._reserve_v14_shared_budget(
        tmp_path, directory, stage=stage, source_sha=source,
        stage_budget={'workflow_seconds': 600}, workflow_clock_start=_clock(0),
    )


def _settle(lease, seconds, authority=None):
    launcher._settle_v14_shared_budget(
        lease, status='WORKER_FAILED', authority=authority,
        parent_interval={'budget_seconds': seconds}, parent_clock_end=_clock(seconds),
    )


def _ledger(lease):
    return json.loads(Path(lease['path']).read_text())


def test_overrun_and_failed_parent_are_charged_without_clipping(tmp_path):
    lease = _reserve(tmp_path)
    _settle(lease, 650)
    ledger = _ledger(lease)
    assert ledger['elapsed_seconds'] == 650
    attempt = ledger['stages']['Q1_FULL_DIRECT']['attempts'][0]
    assert attempt['reservation_exceeded_seconds'] == 50
    assert attempt['watchdog_classification'] is None
    with pytest.raises(InputError, match='already settled'):
        _settle(lease, 650)


def test_unsettled_attempt_blocks_other_stages_and_source_refresh(tmp_path):
    lease = _reserve(tmp_path)
    with pytest.raises(InputError, match='unsettled'):
        _reserve(tmp_path, 'Q2_SCHUR_DIRECT', 'b' * 40)
    _settle(lease, 43150)
    next_lease = _reserve(tmp_path, 'Q2_SCHUR_DIRECT', 'b' * 40)
    assert next_lease['reserved_seconds'] == 50
    assert next_lease['elapsed_before_seconds'] == 43150


def test_batch_allows_only_one_evidenced_bug_replay(tmp_path):
    lease = _reserve(tmp_path)
    _settle(lease, 10)
    with pytest.raises(InputError, match='cannot replay the same source'):
        _reserve(tmp_path)
    with pytest.raises(InputError, match='implementation_bug_replay.json'):
        _reserve(tmp_path, source='b' * 40)
    previous = _ledger(lease)['stages']['Q1_FULL_DIRECT']['attempts'][0]
    evidence = dict(classification='IMPLEMENTATION_BUG', stage='Q1_FULL_DIRECT',
                    failed_source_sha='a' * 40, fixed_source_sha='b' * 40,
                    bug_and_fix='Synthetic fixture: corrected an invalid callback argument.')
    (Path(previous['run_directory']) / 'implementation_bug_replay.json').write_text(json.dumps(evidence))
    replay = _reserve(tmp_path, source='b' * 40)
    _settle(replay, 20)
    second_stage = _reserve(tmp_path, 'Q2_SCHUR_DIRECT', 'b' * 40)
    _settle(second_stage, 5)
    with pytest.raises(InputError, match='entire batch'):
        _reserve(tmp_path, 'Q2_SCHUR_DIRECT', 'c' * 40)
    ledger = _ledger(lease)
    assert ledger['unique_bug_replay_count'] == 1
    assert ledger['elapsed_seconds'] == 35
    assert len(ledger['stages']['Q1_FULL_DIRECT']['attempts']) == 2


def test_q6_incomplete_finalization_has_one_narrow_refresh_without_bug_debit(tmp_path):
    old_directory = tmp_path / 'old_q6'
    old_directory.mkdir()
    (old_directory / 'watchdog').mkdir()
    (old_directory / 'q6_decision.json').write_text(json.dumps({
        'status': 'Q6_EVIDENCE_INCOMPLETE',
        'result_classification': 'EVIDENCE_INCOMPLETE',
        'stage_pass': False,
        'official_result': False,
        'new_pde_actions': 0,
    }))
    (old_directory / 'run_summary.json').write_text(json.dumps({'exit_status': 4}))
    (old_directory / 'watchdog' / 'summary.json').write_text(json.dumps({
        'classification': 'WORKER_FAILED', 'leader_exit_code': 4,
    }))
    ledger_path = launcher._v14_shared_ledger_path(tmp_path)
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(json.dumps({
        'schema': 'task039extra.v14.shared-workflow-ledger.v1',
        'batch_identity': 'review_v14', 'total_budget_seconds': 43200.0,
        'elapsed_seconds': 10.0, 'unique_bug_replay_count': 0,
        'policy_debits': [], 'stages': {'Q6_FINALIZE': {
            'active_attempt': None,
            'attempts': [{
                'attempt': 1, 'source_sha': 'a' * 40,
                'run_directory': str(old_directory), 'status': 'WORKER_FAILED',
                'watchdog_classification': 'WORKER_FAILED',
                'reserved_seconds': 100.0,
                'settled_seconds': 3.0,
            }],
        }},
    }))
    with pytest.raises(InputError, match='implementation_bug_replay.json'):
        launcher._reserve_v14_shared_budget(
            tmp_path, tmp_path / 'default_q6', source_sha='b' * 40,
            stage='Q6_FINALIZE', stage_budget={'workflow_seconds': 43200.0},
            workflow_clock_start=_clock(20),
        )
    lease = launcher._reserve_v14_shared_budget(
        tmp_path, tmp_path / 'new_q6', source_sha='b' * 40,
        stage='Q6_FINALIZE', stage_budget={'workflow_seconds': 43200.0},
        workflow_clock_start=_clock(20), time_policy='observe_only',
    )
    assert lease['authorized_q6_refresh'] is True
    assert lease['refresh_id'] == launcher.V16_Q6_REFRESH_ID
    assert lease['replay'] is False
    assert _ledger(lease)['unique_bug_replay_count'] == 0
    _settle(lease, 4)
    with pytest.raises(InputError, match='exhausted'):
        launcher._reserve_v14_shared_budget(
            tmp_path, tmp_path / 'third_q6', source_sha='c' * 40,
            stage='Q6_FINALIZE', stage_budget={'workflow_seconds': 43200.0},
            workflow_clock_start=_clock(30),
        )


def test_watchdog_utc_excursions_and_parent_prefix_suffix_are_all_charged(tmp_path):
    lease = _reserve(tmp_path)
    authority = dict(clock_start=_clock(2), clock_end=_clock(8), elapsed_seconds=6,
                     workflow_clock_interval={'budget_seconds': 20},
                     classification='RESOURCE_CONTROLLED_STOP', first_SIGKILL={'timestamp_ns': 1})
    _settle(lease, 10, authority)
    ledger = _ledger(lease)
    assert ledger['elapsed_seconds'] == 24  # parent prefix 2 + supervised 20 + save/cleanup 2
    assert ledger['stages']['Q1_FULL_DIRECT']['attempts'][0]['hard_kill_included']


def test_preflight_exception_is_settled_by_launcher_without_starting_worker(tmp_path, monkeypatch):
    ledger_path = tmp_path / 'batch' / 'shared.json'
    monkeypatch.setattr(launcher, '_v14_shared_ledger_path', lambda _root: ledger_path)
    spec = SimpleNamespace(solver={'preconditioner': 'physical_p4_schur_v14', 'stage': 'Q0_CORE'},
                           expected_output_parent=tmp_path / 'runs', execution={})
    def fail_source(*_args):
        raise InputError('synthetic preflight failure')
    monkeypatch.setattr(launcher, '_physical_source_gate', fail_source)
    with pytest.raises(InputError, match='synthetic preflight failure'):
        launcher.launch_specification(spec, source_sha='a' * 40)
    ledger = json.loads(ledger_path.read_text())
    stage = ledger['stages']['Q0_CORE']
    assert stage['active_attempt'] is None
    assert stage['attempts'][0]['status'] == 'PARENT_PREFLIGHT_OR_MONITORING_FAILURE'
    assert ledger['elapsed_seconds'] > 0


def test_launcher_subtracts_preflight_and_charges_final_evidence_saves(tmp_path, monkeypatch):
    from benchmarks import subreaper_watchdog
    from src.runners import workflow_timebase

    previous = _reserve(tmp_path, 'Q1_FULL_DIRECT')
    _settle(previous, 43100)
    ledger_path = Path(previous['path'])
    monkeypatch.setattr(launcher, '_v14_shared_ledger_path', lambda _root: ledger_path)
    now = [0.0]
    monkeypatch.setattr(workflow_timebase, 'clock_sample', lambda: _clock(now[0]))
    def source_gate(*_args):
        now[0] += 3
        return {'source_sha': 'b' * 40}
    def bootstrap(*_args, **_kwargs):
        now[0] += 1
        return {'run_id': 'synthetic'}, 'c' * 64
    def supervise(*_args, **kwargs):
        assert kwargs['wall_seconds'] == 96  # remaining 100 minus parent preflight 4
        assert kwargs['solve_seconds'] == 96
        assert kwargs['active_pc_seconds'] == 30
        start = _clock(now[0])
        now[0] += 6
        return dict(leader_exit_code=0, classification='COMPLETED',
                    job_swap_activity='zero_supported_by_zero_global_activity',
                    launch_envelope={}, memory_scope='synthetic', elapsed_seconds=6,
                    clock_start=start, clock_end=_clock(now[0]),
                    workflow_clock_interval={'budget_seconds': 6})
    original_write = launcher._write_json
    def saved(path, payload):
        original_write(path, payload)
        now[0] += 2
    monkeypatch.setattr(launcher, '_physical_source_gate', source_gate)
    monkeypatch.setattr(launcher, '_write_bootstrap', bootstrap)
    monkeypatch.setattr(launcher, '_write_json', saved)
    monkeypatch.setattr(launcher, 'build_execution_plan',
                        lambda *_args, **_kwargs: SimpleNamespace(adapter_available=True, argv=['synthetic']))
    monkeypatch.setattr(subreaper_watchdog, 'supervise', supervise)
    spec = SimpleNamespace(solver={'preconditioner': 'physical_p4_schur_v14', 'stage': 'Q0_CORE'},
                           expected_output_parent=tmp_path / 'runs', method={'kind': 'full3d_iterative'},
                           execution=dict(warning_memory_gib=7, terminate_memory_gib=8, memory_limit_gb=8))
    launcher.launch_specification(spec, source_sha='b' * 40, monotonic=lambda: now[0])
    ledger = json.loads(ledger_path.read_text())
    assert ledger['elapsed_seconds'] == 43117
    assert ledger['stages']['Q0_CORE']['attempts'][0]['settled_seconds'] == 17
