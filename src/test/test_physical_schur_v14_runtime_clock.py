"""The whole PC timer must not reset the single outer solve deadline."""

import json
import pytest

from src.io.physical_intermediate_profile import SCHUR_PROFILE, profile_facts
from src.runners import workflow_timebase
from src.runners.physical_p4_schur_v14 import V14ResourceStop, _V14Runtime


def _runtime(tmp_path, monkeypatch):
    now = [0.]
    monkeypatch.setattr(workflow_timebase, 'clock_sample', lambda: {
        'monotonic': now[0], 'boottime': now[0], 'utc_ns': int(now[0]*1e9)})
    ledger = tmp_path/'ledger.json'
    ledger.write_text(json.dumps({'batch_identity': 'review_v14', 'stages': {
        'Q4_ORIGINAL': {'attempts': [{
            'source_sha': 'a'*40, 'status': 'RESERVED',
            'workflow_clock_start': workflow_timebase.clock_sample(),
            'reserved_seconds': 14400.,
        }]}}}))
    monkeypatch.setenv('PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH', str(ledger))
    monkeypatch.setenv('PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX', '0')
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PHASE_PATH', str(tmp_path/'phase.json'))
    monkeypatch.setenv('PHYSICAL_TIMEBASE_GUARD', '1')
    runtime = _V14Runtime(tmp_path, 'Q4_ORIGINAL', profile_facts(SCHUR_PROFILE),
                          root=tmp_path, source_sha='a'*40)
    return runtime, now


def test_soft_stop_waits_for_complete_pc_and_preserves_solve_anchor(tmp_path, monkeypatch):
    runtime, now = _runtime(tmp_path, monkeypatch)
    now[0] = 10.
    runtime.set_phase('solve')
    anchor = json.loads(runtime.phase_path.read_text())['phase_started_clock']
    runtime.begin_pc(1)
    now[0] = 35.5
    runtime.marker('local_solve_started')
    assert not runtime.pc_soft_stop_requested
    assert not runtime.stop_requested
    active = json.loads(runtime.phase_path.read_text())
    assert active['phase_started_clock'] == anchor
    assert active['active_pc']['started_clock'] == anchor
    now[0] = 36.
    facts = runtime.finish_pc()
    assert facts['clock_interval']['budget_seconds'] == 26.
    assert runtime.pc_soft_stop_requested and not runtime.stop_requested
    ended = json.loads(runtime.phase_path.read_text())
    assert ended['active_pc'] is None
    assert ended['phase_started_clock'] == anchor


def test_next_pc_has_new_timer_but_same_outer_solve_start(tmp_path, monkeypatch):
    runtime, now = _runtime(tmp_path, monkeypatch)
    runtime.set_phase('solve')
    for sequence in (1, 2):
        now[0] = sequence*5.
        runtime.begin_pc(sequence)
        phase = json.loads(runtime.phase_path.read_text())
        assert phase['phase_started_clock']['monotonic'] == 0.
        assert phase['active_pc']['started_clock']['monotonic'] == sequence*5.
        assert phase['active_pc']['sequence'] == sequence
        now[0] += 1.
        assert runtime.finish_pc()['clock_interval']['budget_seconds'] == 1.
    assert not runtime.pc_soft_stop_requested


def test_failed_pc_is_disarmed_without_reporting_completed_soft_stop(tmp_path, monkeypatch):
    runtime, now = _runtime(tmp_path, monkeypatch)
    runtime.begin_pc(1)
    now[0] = 26.
    facts = runtime.finish_pc(completed=False)
    assert not facts['completed'] and not facts['soft_stop_requested']
    assert json.loads(runtime.phase_path.read_text())['active_pc'] is None


def test_completed_pc_cannot_escape_hard_gate_between_parent_samples(tmp_path, monkeypatch):
    runtime, now = _runtime(tmp_path, monkeypatch)
    runtime.begin_pc(1)
    now[0] = 30.
    with pytest.raises(V14ResourceStop, match='PC_TIME_CONTROLLED_STOP') as stopped:
        runtime.finish_pc()
    assert stopped.value.classification == 'PC_TIME_CONTROLLED_STOP'
    assert json.loads(runtime.phase_path.read_text())['active_pc'] is None
    event = json.loads(runtime.events_path.read_text().splitlines()[-1])
    assert event['facts']['completed'] and event['facts']['hard_limit_exceeded']


def test_field_checkpoint_does_not_reset_single_ksp_deadline(tmp_path, monkeypatch):
    runtime, now = _runtime(tmp_path, monkeypatch)
    runtime.set_phase('solve')  # A setup solve must not establish the KSP start.
    now[0] = 10.
    runtime.begin_outer_solve()
    runtime.begin_pc(1)
    now[0] = 11.
    runtime.finish_pc()
    now[0] = 12.
    runtime.set_phase('metric')
    phase = json.loads(runtime.phase_path.read_text())
    assert phase['phase'] == 'solve' and phase['solve_subphase'] == 'metric'
    assert phase['phase_started_clock']['monotonic'] == 10.
    now[0] = 13.
    runtime.begin_pc(2)
    assert json.loads(runtime.phase_path.read_text())['phase_started_clock']['monotonic'] == 10.
    now[0] = 14.
    runtime.finish_pc()
    runtime.finish_outer_solve()
    runtime.set_phase('postprocess')
    assert json.loads(runtime.phase_path.read_text())['phase'] == 'postprocess'


def test_workflow_prediction_does_not_refund_a_recorded_utc_jump(tmp_path, monkeypatch):
    runtime, _now = _runtime(tmp_path, monkeypatch)
    sample = dict(monotonic=10., boottime=10., utc_ns=20_000_000_000)
    monkeypatch.setattr(workflow_timebase, 'clock_sample', lambda: dict(sample))
    assert runtime.workflow_clock_interval()['budget_seconds'] == 20.
    sample.update(monotonic=11., boottime=11., utc_ns=11_000_000_000)
    assert runtime.workflow_clock_interval()['budget_seconds'] == 21.
