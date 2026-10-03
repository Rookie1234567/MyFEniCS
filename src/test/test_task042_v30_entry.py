"""Precise entry/directory/error regressions; synthetic packets only."""
import json
import pytest
from benchmarks.collect_task042_return_direction import collect
from benchmarks.task042_v29_cached_analysis import cpu_reasons,cost_ledger,checked_batch
from benchmarks.task042_v29_light_checks import layout,compiled_sources
from src.test.task042_return_fixture import complete_packet
import src.test.test_task042_v29_checker as checker


def test_real_compilation_instead_of_ast_only():
    assert all(row['status']=='COMPILED_IN_MEMORY' for row in compiled_sources())


def test_collector_creates_fresh_nested_destination(tmp_path):
    args,_,_=complete_packet(tmp_path)
    args['records']=tmp_path/'fresh'/'nested'/'records'
    assert not args['records'].exists()
    assert collect(**args)['status']=='CHECKED'
    assert len(list(args['records'].glob('*.json')))==3


def test_negative_catalog_has_exact_semantic_gates():
    assert len(checker.EXPECTED_GATES)==32
    assert all(kind in (ValueError,KeyError) and message for kind,message in checker.EXPECTED_GATES.values())


def test_io_error_cannot_satisfy_a_data_mutation_gate(tmp_path,monkeypatch):
    original=checker.collect;calls=0
    missing=tmp_path/'deliberately_missing.json'
    def interrupted(**args):
        nonlocal calls
        calls+=1
        if calls==2:raise FileNotFoundError(2,'named IO test only',str(missing))
        return original(**args)
    monkeypatch.setattr(checker,'collect',interrupted)
    with pytest.raises(FileNotFoundError) as caught:
        checker.test_full_chain_rejects_incomplete_or_inconsistent_evidence(tmp_path,'zero_consumption')
    assert caught.value.filename==str(missing) and calls==2


def test_compiled_cpu_schema_and_lf_fresh_directory(tmp_path):
    output=tmp_path/'new'/'cpu'
    cpu_reasons(output,batch='v30')
    result=json.loads((output/'cpu_exclusions_v30.json').read_text())
    assert result['batch']=='v30'
    assert [x['snapshot_label'] for x in result['snapshots']]==['accepted','rejected']
    assert [x['candidates'] for x in result['snapshots']]==[[11,22,26],[]]
    assert all(isinstance(x['snapshot'],dict) and x['snapshot']['sha256'] for x in result['snapshots'])
    assert all(b'\r' not in p.read_bytes() for p in output.glob('*.csv'))
    assert not list(output.glob('*v29*'))


def test_cost_module_whole_function_and_namespace(tmp_path):
    output=tmp_path/'new'/'cost'
    cost_ledger(output,batch='v30')
    result=json.loads((output/'complete_cost_ledger_v30.json').read_text())
    assert result['batch']=='v30' and result['neural_threshold']==.20
    assert not result['complete_baseline_qualified'] and result['neural_increment']=='NOT_DEMONSTRATED'
    assert result['lifecycle']['stored_A_LU_unique_bytes']==1591420032
    assert not list(output.glob('*v29*'))


def test_explicit_namespace_preserves_default():
    assert layout('v29')[1].name=='v29' and layout('v30')[1].name=='v30'
    with pytest.raises(ValueError,match='authorized v29/v30'):
        checked_batch('v31')
