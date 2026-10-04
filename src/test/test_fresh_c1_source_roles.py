"""Actual saved C1a source-role admission; no FE, JIT, factor or solve."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from src.solvers.fresh_c1_contract import validate_component_source_roles, validate_component_packets
from src.test.test_fresh_c1_pipeline_contract import _packets

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'benchmarks/artifacts/task40extra_dot_parallel_cloud/fresh_C1_same80_p6_component_attempt4_library_20261004T12'
REPORT_SHA='10d86ec26af7402178d1c840599559006cc6b2d0c04a223fbd013dd6a2dda235'
CHECKER_SHA='cbde5fbfd5c31474a78afb9c5dabe20d8e1e10e84f1f1c5499faaeb88c3cf5a1'

@pytest.fixture
def packets():
    if not (RUN/'independent_checker.json').is_file():pytest.skip('actual C1a Library packet must be materialized')
    report=json.loads((RUN/'probe_report.json').read_text())
    checker=json.loads((RUN/'independent_checker.json').read_text())
    current=deepcopy(checker['checker_source']);current['head']='b'*40
    for path in ('src/solvers/fresh_c1_contract.py','benchmarks/run_y_orbit_sparse_probe.py',
                 'src/test/test_fresh_c1_source_roles.py'):
        current['files_sha256'][path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    return report,checker,current

def bind(report,checker,current):
    return validate_component_source_roles(report,checker,current,root=ROOT,
        report_sha256=REPORT_SHA,checker_sha256=CHECKER_SHA)

def test_actual_saved_producer_checker_consumer_and_all_Git_bytes(packets):
    report,checker,current=packets;roles=bind(*packets)
    assert roles['producer']['head']=='a580c72a357006d2ce8cacc600b7391b89d6506d'
    assert roles['saved_checker']['head']=='164154279180356905956ed6e405f9406ba863f9'
    assert roles['binding']['metadata_seams_only_AST_verified']
    assert roles['binding']['all_other_source_config_input_hashes_match']

@pytest.mark.parametrize('bad',['producer_head','checker_head','dirty','other_branch','numeric_hash',
    'removed_path','detached_checker_source','detached_old_binding','changed_historical_bytes'])
def test_role_bridge_rejects_unreviewed_or_detached_sources(packets,bad):
    report,checker,current=deepcopy(packets)
    if bad=='producer_head':report['source']['head']='c'*40
    elif bad=='checker_head':checker['checker_source']['head']='c'*40
    elif bad=='dirty':current['dirty']=' M changed'
    elif bad=='other_branch':current['branch']='main'
    elif bad=='numeric_hash':current['files_sha256']['src/solvers/y_orbit_sparse_probe.py']='f'*64
    elif bad=='removed_path':del current['files_sha256']['src/solvers/y_orbit_sparse_probe.py']
    elif bad=='detached_checker_source':checker['source']=current
    elif bad=='detached_old_binding':checker['worker_dependency_binding']['worker_head']='c'*40
    else:report['source']['files_sha256']['src/solvers/y_orbit_sparse_probe.py']='f'*64
    with pytest.raises((ValueError,RuntimeError)):bind(report,checker,current)

@pytest.mark.parametrize('r,c',[('wrong',CHECKER_SHA),(REPORT_SHA,'wrong')])
def test_exact_immutable_report_checker_hashes_required(packets,r,c):
    with pytest.raises(ValueError):validate_component_source_roles(*packets,root=ROOT,
        report_sha256=r,checker_sha256=c)

def test_same_source_contract_preserved_and_distinct_checker_role_bound():
    report,checker,kwargs=_packets()
    assert validate_component_packets(report,checker,**kwargs)['component_checker_bound']
    expected={'head':'checker'};checker['checker_source']=expected
    assert validate_component_packets(report,checker,expected_checker_source=expected,**kwargs)['component_checker_bound']
    checker['checker_source']={'head':'wrong'}
    with pytest.raises(ValueError):validate_component_packets(report,checker,expected_checker_source=expected,**kwargs)
