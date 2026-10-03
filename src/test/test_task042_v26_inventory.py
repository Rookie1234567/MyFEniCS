"""No operator calls: reject mutated metadata before touching cached arrays."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.collect_task042_block_direction import fixed_inventory,check_arrays
from src.io.block_direction_diagnostic import PLAN_PATH,NAMES
from src.solvers.block_residual_direction import decision


@pytest.fixture
def actual():
    root=Path(__file__).resolve().parents[2]
    index=json.loads((root/'benchmarks/artifacts/task042/v25/DIAGNOSTIC.json').read_text())
    return json.loads(Path(index['path']).read_text())


@pytest.mark.parametrize('kind',['empty','one','duplicate','label','swap_content','wrong_container',
    'wrong_member','wrong_path','failed_gate','missing_gate','nan','negative','missing_rank',
    'missing_recombination','wrong_recombination','false_stationarity'])
def test_inventory_rejects_review_counterexamples_and_unbound_evidence(actual,kind):
    v=deepcopy(actual);r=v['rows'][1]
    if kind=='empty':v['rows']=[]
    elif kind=='one':v['rows']=[r]
    elif kind=='duplicate':v['rows']=[r,r]
    elif kind=='label':r['name']='V24-LZ-FAKE'
    elif kind=='swap_content':r['input_state']=v['rows'][2]['input_state']
    elif kind=='wrong_container':r['input_state']['sha256']='bad'
    elif kind=='wrong_member':r['input_state']['trace_sha256']='bad'
    elif kind=='wrong_path':r['input_state']['path']='/tmp/not_a_state.npz'
    elif kind=='failed_gate':r['gates']['qr']=False
    elif kind=='missing_gate':del r['gates']['qr']
    elif kind=='nan':r['eta8']=float('nan')
    elif kind=='negative':r['eta8']=-1
    elif kind=='missing_rank':del r['rank']
    elif kind=='missing_recombination':del r['independent_recombination']
    elif kind=='wrong_recombination':del r['independent_recombination']['best']
    else:r['stationarity_operation_relative']=1.
    with pytest.raises((ValueError,KeyError,AssertionError)):fixed_inventory(v)


def test_fixed_inventory_accepts_true_three_states_and_sorts_by_identity(actual):
    v=deepcopy(actual);v['rows'].reverse()
    assert tuple(x['name'] for x in fixed_inventory(v))==NAMES
    checked=check_arrays(v)
    assert checked['status']=='CHECKED' and checked['decision']=='EIGHT_DIRECTIONS_WEAK'
    assert tuple(x['name'] for x in checked['rows'])==NAMES
    assert all(x['no_new_action'] and x['no_new_decomposition'] for x in checked['rows'])


def test_future_decision_cannot_infer_a_pair_from_list_tail(actual):
    for rows in ([],[actual['rows'][1]],[actual['rows'][1],actual['rows'][1]],
                 [actual['rows'][0],actual['rows'][1],actual['rows'][1]]):
        assert decision(rows)=='NUMERICALLY_UNRESOLVED'
    assert decision(list(reversed(actual['rows'])))=='EIGHT_DIRECTIONS_WEAK'


def test_plan_parent_cannot_be_swapped_while_state_label_is_preserved(actual):
    plan=json.loads(PLAN_PATH.read_text())
    plan['states'][1]['parent_result']=plan['states'][2]['parent_result']
    with pytest.raises(ValueError,match='parent/state'):fixed_inventory(actual,plan)
