"""Saved-array checks only, after the one-run queue has been frozen."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from benchmarks.collect_task042_joint_direction import read_result,verify_cached,compact_physical_identity
from src.test.task042_campaign_fixture import isolated_v26_schema


@pytest.fixture
def actual():return read_result()[0]


@pytest.mark.parametrize('mutation',['empty','one','duplicate','label','state_swap','failed_gate','missing_gate','nonfinite','negative','missing_rank','missing_recombination','over_cap'])
def test_frozen_two_sample_checker_rejects_incomplete_or_untrusted_records(actual,mutation):
    v=deepcopy(actual);row=v['rows'][0]
    if mutation=='empty':v['rows']=[]
    elif mutation=='one':v['rows']=[row]
    elif mutation=='duplicate':v['rows']=[row,row]
    elif mutation=='label':row['name']='OTHER'
    elif mutation=='state_swap':row['input_state']=v['rows'][1]['input_state']
    elif mutation=='failed_gate':row['gates']['control']=False
    elif mutation=='missing_gate':del row['gates']['control']
    elif mutation=='nonfinite':row['eta9']=float('nan')
    elif mutation=='negative':row['eta9']=-1
    elif mutation=='missing_rank':del row['rank']
    elif mutation=='missing_recombination':del row['independent_recombination']
    else:v['budget_counts']['actions']=65
    with pytest.raises((ValueError,KeyError)):verify_cached(v)


def test_actual_saved_vectors_recompute_negative_decision_without_raw_status(actual):
    actual['status']='NOT_TRUSTED';actual['rows'].reverse()
    checked=verify_cached(actual)
    assert checked['status']=='CHECKED' and checked['decision']=='FIXED_JOINT_DIRECTION_INSUFFICIENT'
    assert all(x['no_new_action'] and x['no_new_decomposition'] and x['no_factor_reader'] for x in checked['rows'])
    assert all(x['g']>=.95 for x in checked['rows'])


def test_one_run_loader_refuses_a_closed_campaign(isolated_v26_schema):
    from src.io.joint_block_diagnostic import load_joint_diagnostic
    from src.io.input_loader import InputError
    isolated_v26_schema.book['closed']=True
    isolated_v26_schema.save()
    path=Path(__file__).resolve().parents[2]/'input/task042_neural_coarse_inverse/v26_joint_block_diagnostic.dat'
    with pytest.raises(InputError,match='closed'):load_joint_diagnostic(path)


def test_compact_inventory_preserves_all_mode_keys_without_copying_vectors(actual):
    _,index=read_result()
    original=deepcopy(actual['physical_identity'])
    compact=compact_physical_identity(actual,index)
    assert compact['total_channels']==len(compact['channel_keys'])==40
    assert compact['source_record']==dict(index,json_pointer='/physical_identity')
    assert compact['mode_manifest_sha256']==original['mode_manifest_sha256']
    assert compact['material']==original['material']
    assert 'modes' not in compact['recipe'] and 'full_channel_inventory' not in compact
    assert compact['channel_keys']==[{k:r[k] for k in ('mode_index','side','m','n','polarization')} for r in original['full_channel_inventory']]
    assert actual['physical_identity']==original
    assert len(json.dumps(compact))<10000
