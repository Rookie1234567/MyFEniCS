"""Pure admission arithmetic: frozen metadata only, no host admission or FE."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.task042_admission_receipt import compare_thread_rate_policy, replay
from src.runners.task042_shared import cpu_exclusions, spare_cores


TIMING = dict(sample_interval_seconds=1., ticks_per_second=100)
TOPOLOGY = [dict(cpu=i, core=i // 2, socket=0, siblings=[i, i ^ 1])
            for i in range(6)]


def neighbor(*, name='desktop', affinity=None, cpu=0):
    return [dict(name=name, threads=[dict(tid=100, cpu=cpu,
                  affinity=list(range(48)) if affinity is None else affinity)])]


@pytest.mark.parametrize('name', ['gnome-shell', 'python', 'metrology'])
def test_brief_activity_is_rate_based_without_name_whitelist(name):
    rows = neighbor(name=name)
    assert spare_cores(TOPOLOGY, rows, {}, {100: 5}, **TIMING) == list(range(6))
    assert spare_cores(TOPOLOGY, rows, {}, {100: 6}, **TIMING) == [2, 3, 4, 5]
    assert spare_cores(TOPOLOGY, rows, {}, {100: 8},
                       sample_interval_seconds=2., ticks_per_second=100) == list(range(6))


def test_busy_cpu_and_unlisted_smt_sibling_stay_protected():
    assert spare_cores(TOPOLOGY, [], {1: .050001}, {}, **TIMING) == [2, 3, 4, 5]
    assert spare_cores(TOPOLOGY, [], {1: .05}, {}, **TIMING) == list(range(6))
    assert spare_cores([TOPOLOGY[0]], [], {1: .9}, {}, **TIMING) == []


def test_sleeping_narrow_loader_affinity_is_still_reserved():
    assert spare_cores(TOPOLOGY, neighbor(affinity=[1, 2]), {}, {100: 0},
                       **TIMING) == [4, 5]


@pytest.mark.parametrize('delta', [None, -1, float('nan'), float('inf')])
def test_unknown_or_invalid_wide_activity_still_fails_closed(delta):
    deltas = {} if delta is None else {100: delta}
    assert spare_cores(TOPOLOGY, neighbor(), {}, deltas, **TIMING) == [2, 3, 4, 5]


def test_sustained_worker_last_cpu_blocks_its_whole_physical_core():
    rows = neighbor(name='python', cpu=4)
    assert spare_cores(TOPOLOGY, rows, {4: .01}, {100: 90}, **TIMING) == [0, 1, 2, 3]
    decisions = cpu_exclusions(TOPOLOGY, rows, {4: .01}, {100: 90}, **TIMING)
    assert decisions[5]['excluded_siblings'] == {'4': ['sustained_wide_thread:100']}


@pytest.mark.parametrize('interval,hz', [(0, 100), (-1, 100), (float('nan'), 100),
                                      (1, 0), (1, None), (None, 100), (True, 100)])
def test_incomplete_or_invalid_timing_is_rejected(interval, hz):
    with pytest.raises(ValueError, match='positive finite timing'):
        spare_cores(TOPOLOGY, [], {}, {}, sample_interval_seconds=interval,
                    ticks_per_second=hz)


def test_legacy_snapshot_policy_is_not_silently_reinterpreted():
    assert spare_cores(TOPOLOGY, neighbor(), {}, {100: 1}) == [2, 3, 4, 5]
    assert spare_cores(TOPOLOGY, neighbor(), {}, {}) == [2, 3, 4, 5]


@pytest.mark.parametrize('suffix,sha,expected', [
    ('01', '78d40c8e3d5f3c9925941026563f3de3ae44ff56330c3d2b4cee826bbd3671ba',
     [12, 14, 25, 26, 35, 36, 37, 38, 42, 45, 47]),
    ('02', 'adf32a946c78548f07fe6c217852160d4986a94dbcf8a2dfcb2353a075b185fd',
     [5, 8, 10, 13, 16, 23, 35, 36, 38, 39, 41, 43, 45]),
])
def test_frozen_snapshots_old_rejection_and_new_rate_policy(suffix, sha, expected):
    root = Path(__file__).resolve().parents[2]
    path = root / f'tmp/task042/v79/aux_pre_focused{suffix}/admission.json'
    if not path.exists():
        pytest.skip('Local frozen Task042 CPU metadata is not shipped with Git')
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha
    receipt = json.loads(data)
    original = deepcopy(receipt)
    assert replay(receipt)['candidate_cpus'] == []
    # Linux clock tick ABI verified on the same boot; never infer from CPU names.
    report = compare_thread_rate_policy(receipt, ticks_per_second=100)
    assert report['revised_candidates'] == expected
    assert not set(expected) & set(range(27, 35))
    assert report['live_admission_performed'] is False
    assert all(value == 'NOT_CHECKED' for key, value in
               report['other_resource_gates'].items() if key != 'CPU_SMT')
    assert receipt == original and path.read_bytes() == data


def test_replay_rejects_unknown_policy():
    receipt = dict(cpu_busy_fractions={}, thread_delta_ticks={}, cpu_ticks_before={},
                   cpu_ticks_after={}, thread_ticks_before={}, thread_ticks_after={},
                   topology=[], neighbor_processes=[], allowed_cpus=[],
                   sample_interval_seconds=1., thread_activity_policy='skip_workers')
    with pytest.raises(ValueError, match='unknown CPU thread activity policy'):
        replay(receipt)
