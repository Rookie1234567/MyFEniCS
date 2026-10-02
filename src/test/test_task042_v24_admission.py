"""Review21 section10: sealed common Gates and symmetric four-cycle dispatch."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from src.solvers.local_block_coarse import ROWS
from src.solvers.local_block_readiness import local_readiness,seal_local_ready
from src.io import local_block_pair as io
from src.runners import local_block_queue as queue
from src.solvers import local_block_study as core


def ready_fixture(rows=ROWS):
    """Small control-flow evidence fixture, not a claimed FE qualification."""
    plan=json.loads(io.PLAN_PATH.read_text());inventory=[];safety=[];blocks=[];offset=0
    for b,n in enumerate(rows):
        digest=f'{b+1:064x}';ids=list(range(offset,offset+n));offset+=n
        item=dict(block=b,rows=ids,matrix=dict(shape=[n,n],array_sha256=digest),
                  LU=dict(shape=[n,n],array_sha256=digest),pivots=dict(shape=[n],array_sha256=digest))
        inventory.append(item);blocks.append(dict(matrix_sha256=digest))
        safety.append(dict(block=b,rcond1_estimate=.01,gecon_info=0,partial_pivoting=True,
                           shift=None,drop=None,refinement=0,LU_sha256=digest,pivot_sha256=digest))
    pair=dict(operation_relative=0.)
    r=dict(status='LOCAL_BLOCK_SETUP_COMPLETE',partition=dict(canonical_rows=sum(rows),block_rows=list(rows),
           all_member_hashes_checked=True,all_rows_exactly_once=True,slave_added=0,
           physical_center_rule_recomputed=True,entity_count=2448 if sum(rows)==18144 else sum(rows),map=plan['map']),
           assembly=dict(shared_contributions_merged=True,owner_cells_not_used=True,all_ports=40,
                         global_fine_K_or_A_constructed=False,F_is_C_adjoint_assumed=False,separate_curl_mass_condensation=False,blocks=blocks),
           factor_safety=safety,block_inventory=inventory,block_inventory_sha256='fixture',
           local_checks=dict(witnesses=[dict(block=i//2,seed=422401+i,original_principal_action=pair,
                  solve_relative=0.,solve_operation_relative=0.) for i in range(16)],zero_exact=True,repeat=pair,complex_linearity=pair),
           old_new_S_SH_pairs=[dict(adjoint=False,**pair),dict(adjoint=True,**pair)],composite_qualified=True)
    assert seal_local_ready(r,rows=rows,expected_map=plan['map'])['qualified']
    return r


def queue_fixture(tmp_path,monkeypatch,result):
    own=tmp_path/'own';own.mkdir();(own/'SETUP.json').write_text('historical failed index')
    monkeypatch.setattr(io,'ARTIFACT_ROOT',own)
    monkeypatch.setattr(io,'read_result',lambda name:(result,own/'old-result.json'))
    events=[];calls=[]
    monkeypatch.setattr(queue.w,'journal',lambda event,**kw:events.append((event,kw)))
    def run(name,target=4):
        calls.append((name,target))
        return dict(status='ROUTE_COMPLETE',stop_reason='SLICE_TARGET_COMPLETE')
    monkeypatch.setattr(queue,'run',run)
    return calls,events


def test_four_qualified_routes_only_first_block_no_fifth_reader(tmp_path,monkeypatch):
    calls,events=queue_fixture(tmp_path,monkeypatch,ready_fixture())
    queue.solve()
    assert calls==[('LW',4),('LCW',4),('LZ',4),('LCZ',4)]
    assert events[-1][0]=='symmetric_first_blocks_complete'
    assert events[-1][1]['automatic_extension'] is False


@pytest.mark.parametrize('payload',[dict(status='FAILED',local_qualified=True,composite_qualified=False),
                                  'original_action_failed','changed_factor_hash'])
def test_failed_common_setup_queue_reentry_does_not_dispatch_or_rebuild(tmp_path,monkeypatch,payload):
    r=ready_fixture() if isinstance(payload,str) else payload
    if payload=='original_action_failed':r.update(status='FAILED');r['old_new_S_SH_pairs'][1]['operation_relative']=1e-2
    if payload=='changed_factor_hash':r['block_inventory'][0]['LU']['array_sha256']='corrupt'
    before=deepcopy(r);calls,events=queue_fixture(tmp_path,monkeypatch,r)
    ledger=dict(charged=dict(actions=411,local_factors=8,factor_readers=2),routes=dict(SETUP=dict(wall_seconds=100.)),active=None)
    saved=deepcopy(ledger);monkeypatch.setattr(queue.w,'ledger',lambda:ledger)
    queue.solve()
    assert not calls and ledger==saved and r==before
    assert events[-1][0]=='dependent_not_run' and not events[-1][1]['admission']['qualified']


def test_composite_failure_keeps_complete_public_local_gate(tmp_path,monkeypatch):
    r=ready_fixture();r.update(status='FAILED',composite_qualified=False,error='D_L/composite only')
    calls,events=queue_fixture(tmp_path,monkeypatch,r);queue.solve()
    assert calls==[('LW',4),('LZ',4)]
    assert local_readiness(r)['qualified']


@pytest.mark.parametrize('name',['LW','LZ','LCW','LCZ'])
def test_standalone_dat_rejects_failed_true_flag_before_factor_or_action(monkeypatch,name):
    old=dict(status='FAILED',local_qualified=True,composite_qualified=True)
    monkeypatch.setattr(io,'read_result',lambda stage:(old,None))
    def forbidden(*a,**kw):raise AssertionError('bad SETUP reached action or factor loader')
    monkeypatch.setattr(core,'bars',forbidden);monkeypatch.setattr(core,'load_local',forbidden)
    stage=SimpleNamespace(io=io,name=name,own_plan=json.loads(io.PLAN_PATH.read_text()))
    result=core.route(stage)
    assert result['status']=='NOT_RUN_PC_GATE' and not result['local_admission']['qualified']


def test_seal_requires_both_original_actions_and_rejects_raw_mutation():
    r=ready_fixture();del r['old_new_S_SH_pairs']
    with pytest.raises(ValueError,match='local-ready'):seal_local_ready(r)
    r=ready_fixture();r['factor_safety'][0]['rcond1_estimate']=1e-14
    assert not local_readiness(r)['qualified']


def test_standalone_schema_forbids_cycle_extension(tmp_path):
    path=tmp_path/'v24_no8.dat'
    original=io.ROOT/'input/task042_neural_coarse_inverse/v24_local_warm.dat'
    path.write_text(original.read_text().replace('target_cycles = 4','target_cycles = 8'))
    with pytest.raises(Exception,match='first four cycles'):io.load_local_block(path)
