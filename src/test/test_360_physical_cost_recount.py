"""Independent correction of lifetime ordinals across cycle boundaries."""

from copy import deepcopy
import json

import pytest

from benchmarks.physical_intermediate_checker import recompute_positive_apply_counts


def fixture_records():
    pcs = []
    for pc in range(1, 6):
        pcs.append(dict(apply_count=pc, direction_facts=[
            dict(positive_cycle_facts=dict(apply_count=n, lower_cycle_facts=dict(apply_count=n)))
            for n in (2*pc-1, 2*pc)]))
    cycles = [dict(cycle_index=i, end_iteration=2*(i+1), pc_apply_count=2,
                   pc_costs=dict(s6_apply_count=value, s3_apply_count=value))
              for i, value in enumerate((10, 26))]
    return pcs, cycles


def test_two_cycles_and_completed_tail_count_occurrences_without_mutation():
    pcs, cycles = fixture_records()
    saved = deepcopy((pcs, cycles))
    result = recompute_positive_apply_counts(pcs, cycles)
    assert [c['recomputed']['s6_apply_count'] for c in result['cycles']] == [4, 4]
    assert [c['raw_reported']['s6_apply_count'] for c in result['cycles']] == [10, 26]
    assert result['total'] == dict(s6_apply_count=10, s3_apply_count=10)
    assert result['tail'] == dict(s6_apply_count=2, s3_apply_count=2)
    assert result['completed_pcs_after_last_cycle'] == 1
    assert (pcs, cycles) == saved


def test_missing_lifetime_record_is_rejected():
    pcs, cycles = fixture_records()
    pcs[2]['direction_facts'][0]['positive_cycle_facts']['apply_count'] = 6
    with pytest.raises(ValueError, match='lifetime ordinal'):
        recompute_positive_apply_counts(pcs, cycles)


def test_future_ledger_counts_calls_across_cycles_preserving_per_call_counts(tmp_path):
    from src.runners.physical_intermediate import WorkflowLedger

    ledger = WorkflowLedger(tmp_path, tmp_path / 'phase.json')
    pcs, _ = fixture_records()
    for i, pc in enumerate(pcs[:4], 1):
        pc.update(intermediate={}, wall_seconds=2.)
        for direction in pc['direction_facts']:
            direction.update(stage='positive', wall_seconds=1.)
            positive = direction['positive_cycle_facts']
            positive.update(lower_cycle_count=1, p6_smoother_apply_count=2)
            positive['lower_cycle_facts'].update(p1_solve_count=1, smoother_apply_count=2)
        ledger.record_pc(pc)
        if i % 2 == 0:
            ledger.cycle(dict(end_iteration=i))
    rows = [json.loads(x) for x in (tmp_path / 'cycles.jsonl').read_text().splitlines()]
    for row in rows:
        counts = row['pc_costs']
        assert counts['s6_apply_count'] == counts['s3_apply_count'] == 4
        assert counts['s6_lower_cycle_count'] == counts['s3_p1_solve_count'] == 4
        assert counts['s6_p6_smoother_apply_count'] == counts['s3_smoother_apply_count'] == 8
