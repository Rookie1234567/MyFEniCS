"""One non-FE fixture for mutually exclusive single-component dispatch."""
import pytest
from src.runners import physical_recursive_entry as entry
from src.runners import physical_recursive_controls as controls


def test_projected_contract_mutual_exclusion_and_dispatch(monkeypatch,tmp_path):
    argv=['--input','original.dat','--inventory','binding.json','--output',str(tmp_path),
          '--budget','budget.json','--source-sha','a'*40]
    parser=entry.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(argv+['--projected-p4-component','--p4-failure-diagnostic'])
    args=parser.parse_args(argv+['--projected-p4-component'])
    contract=entry.selected_contract(args)
    assert contract['workflow_seconds']==900
    assert contract['I4']['seconds']==60 and contract['I4']['target']==1e-4
    assert contract['I4_calls']==1 and contract['old_I4_calls']==contract['outer_calls']==0
    assert contract['A4_inner_limit']==150 and contract['p2_logical_limit']==65
    calls=[]
    def new(*args,**kwargs):calls.append((args,kwargs));return 'new-component'
    def forbidden(*args,**kwargs):raise AssertionError('old components dispatched')
    monkeypatch.setattr(controls,'run_projected_p4_component',new)
    monkeypatch.setattr(controls,'run_recursive_components',forbidden)
    monkeypatch.setattr(controls,'run_p4_failure_diagnostic',forbidden)
    assert entry.dispatch_components(args,None,None,tmp_path,sample=lambda:None,marker=lambda *a:None)=='new-component'
    assert len(calls)==1 and calls[0][0][2]=='binding.json'
    assert entry.selected_contract(parser.parse_args(argv))['fixed_I4_calls']==6
