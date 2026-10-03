"""Focused residual identity, paid reentry and WAIT tests; no real payload reads."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import numpy as np
import pytest
from src.runners.task042_shared import write_json
from src.solvers.full_input_block_correction import CAPS, EXPECTED, VECTOR_KEYS
from src.solvers.full_input_block_v34_window import PaidDiagnosticWindow, CAMPAIGN_CAPS
from src.solvers.neural_fe_action_packet import file_hash


def window(folder):
    folder.mkdir(parents=True,exist_ok=True)
    w=PaidDiagnosticWindow(folder)
    w.snapshot=lambda:dict(heavy_remaining_seconds=80000.,total_remaining_seconds=85000.)
    return w


def test_actual_workflow_residual_identity_and_two_layer_checker(tmp_path,monkeypatch):
    from src.test.task042_v31_workflow_fixture import workflow
    from benchmarks.task042_full_input_checker import numeric,settled_campaign,collect
    from benchmarks.task042_return_certificates import state_certificate
    from benchmarks.collect_task042_return_direction import load_members
    result,checked,book=workflow(tmp_path,monkeypatch,batch='v34')
    assert checked['status']=='CHECKED' and book['charged']==EXPECTED
    assert len(checked['rows'])==2 and not list((tmp_path/'records').glob('*v33*'))
    plan=json.loads((tmp_path/'plan.json').read_text());row=result['rows'][0];item=plan['states'][0]
    art=tmp_path/'benchmarks/artifacts/task042';nt=18144
    setup=json.loads(Path(plan['local_setup']['path']).read_text());groups=np.empty(nt,np.int64)
    for b,p in enumerate(setup['block_inventory']):groups[p['rows']]=b
    ids=np.flatnonzero((groups==5)|(groups==7))
    a=load_members(row['diagnostic_arrays'],VECTOR_KEYS,art/'v34')
    state=load_members(item['state'],('trace','port','z','residual'),art/'v24')
    caches=[load_members(item[k],keys,art/ver) for k,keys,ver in (
        ('v25_arrays',('directions','images'),'v25'),
        ('v26_arrays',('joint_direction','joint_image'),'v26'),
        ('v32_arrays',('return_direction','return_image'),'v32'))]
    # The real workflow already has finite, nonzero rounding differences.
    assert not np.array_equal(a['input_residual'],state['residual'][:nt])
    for relative,valid in ((.99e-11,True),(1.01e-11,False)):
        old={k:v.copy() for k,v in state.items()};old['residual']=a['audited_full_residual'].copy()
        old['residual'][0]+=relative*row['full_b_norm']
        cert=deepcopy(row)
        for key,diff in (('saved_trace_residual_full_b_relative',a['input_residual']-old['residual'][:nt]),
                         ('saved_full_residual_full_b_relative',a['audited_full_residual']-old['residual'])):
            cert['identity'][key]=float(np.linalg.norm(diff)/row['full_b_norm'])
        if valid:
            recomputed=numeric(cert,a,old,*caches,groups,ids,nt)
            assert recomputed['rho_full']==checked['rows'][0]['rho_full']
        else:
            with pytest.raises(ValueError,match='state audit unsafe'):state_certificate(cert,a,old,nt)
    bad={k:v.copy() for k,v in state.items()};bad['residual'][0]=complex(float('nan'),0)
    with pytest.raises(ValueError,match='state nonfinite'):state_certificate(row,a,bad,nt)
    wrong=deepcopy(result);wrong['operator_identity']['action_sha256']='f'*64
    # Source corruption must fail before numerical interpretation, not be hidden
    # by the newly permitted finite residual tolerance.
    idx=json.loads((art/'v34/DIAGNOSTIC.json').read_text());original=Path(idx['path']).read_bytes()
    write_json(Path(idx['path']),wrong);write_json(art/'v34/DIAGNOSTIC.json',dict(path=idx['path'],sha256=file_hash(Path(idx['path']))))
    with pytest.raises(ValueError,match='operator identity'):
        collect(root=tmp_path,plan_path=tmp_path/'plan.json',artifact_root=art/'v34',records=tmp_path/'records',batch='v34')
    Path(idx['path']).write_bytes(original);write_json(art/'v34/DIAGNOSTIC.json',idx)
    assert settled_campaign(book,result,tmp_path)['counts']==EXPECTED
    # A failed consuming attempt remains charged and hash-bound; final successful
    # counts stay EXACTLY the predetermined inventory, never enlarged to match.
    failed_dir=tmp_path/'results/task042/failed';failed_dir.mkdir()
    upper=dict.fromkeys(CAPS,0);upper.update(actions=1,port_factors=1)
    active=dict(source_sha='e'*40,completed=dict(upper),upper=dict(upper))
    summary=dict(source_state=dict(source_sha='e'*40),classification='WORKER_FAILED',leader_exit_code=1,
        descendants_cleared=True,elapsed_seconds=1.25)
    write_json(failed_dir/'run_summary.json',summary);write_json(failed_dir/'settlement_counts.json',active)
    failed=dict(directory=str(failed_dir),source_sha='e'*40,classification='WORKER_FAILED',descendants_cleared=True,
        exact_counts=False,counts=upper,upper=upper,completed=dict.fromkeys(CAPS,0),actor_wall_seconds=1.25,
        summary_receipt=dict(path=str(failed_dir/'run_summary.json'),sha256=file_hash(failed_dir/'run_summary.json')),
        write_ahead_receipt=dict(path=str(failed_dir/'settlement_counts.json'),sha256=file_hash(failed_dir/'settlement_counts.json')))
    paid=deepcopy(book);paid['runs'].insert(0,failed);paid['actor_wall_seconds']+=1.25
    for k,v in upper.items():paid['charged'][k]+=v
    assert settled_campaign(paid,result,tmp_path)['counts']==EXPECTED
    for change in ('erase_failure_charge','wrong_source','bad_hash','tree_alive'):
        bad=deepcopy(paid)
        if change=='erase_failure_charge':bad['charged']=EXPECTED.copy()
        elif change=='wrong_source':bad['runs'][0]['source_sha']='f'*40
        elif change=='bad_hash':bad['runs'][0]['summary_receipt']['sha256']='0'*64
        else:bad['runs'][0]['descendants_cleared']=False
        with pytest.raises(ValueError,match='settlement|source|cleared'):settled_campaign(bad,result,tmp_path)
    shutil.rmtree(tmp_path)


def test_paid_entry_repair_preserves_attempt_and_campaign_caps(tmp_path):
    w=window(tmp_path);book=w.ledger()
    charge=dict.fromkeys(CAPS,0);charge.update(actions=6,factor_readers=1,port_factors=1)
    book.update(charged=charge,runs=[dict(classification='WORKER_FAILED',descendants_cleared=True)],actor_wall_seconds=5.)
    write_json(w.LEDGER_PATH,book)
    assert w.allow_entry_repair()
    w.validate_increment(charge,dict.fromkeys(CAPS,0),'factor_readers',1)
    with pytest.raises(RuntimeError,match='immutable cap'):w.validate_increment(charge,dict.fromkeys(CAPS,0),'factor_readers',2)
    with pytest.raises(RuntimeError,match='immutable cap'):w.validate_increment(dict(CAMPAIGN_CAPS),dict.fromkeys(CAPS,0),'actions')
    for change in ('closed','active','complete','not_cleared','no_actor_wall','no_reader_capacity'):
        bad=deepcopy(book)
        if change=='closed':bad['closed']=True
        elif change=='active':bad['active']={}
        elif change=='complete':bad['runs'][0]['classification']='COMPLETED'
        elif change=='not_cleared':bad['runs'][0]['descendants_cleared']=False
        elif change=='no_actor_wall':bad['actor_wall_seconds']=300.
        else:bad['charged']['factor_readers']=3
        write_json(w.LEDGER_PATH,bad);assert not w.allow_entry_repair()


def test_resource_wait_charges_probe_once_and_requires_backoff(tmp_path,monkeypatch):
    from src.solvers import full_input_block_v34_window as module
    w=window(tmp_path);clock=[100.]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    calls=[]
    def rejected(**kwargs):
        calls.append(1);clock[0]+=1.25
        write_json(kwargs['receipt_path'],dict(gates=dict(CPU_SMT='FAIL',MEMORY='NOT_CHECKED')))
        raise RuntimeError('No audited unoccupied physical core')
    with pytest.raises(RuntimeError,match='No audited'):
        w.admission(rejected,receipt_path=tmp_path/'admission001.json',source_sha='a'*40)
    assert w.probe_wall()==1.25 and w.auxiliary_wall()==w.carried_auxiliary_seconds+1.25
    assert not (tmp_path/'auxiliary_resource_rejection.json').exists()
    with pytest.raises(RuntimeError,match='backoff'):w.require_retry_ready()
    assert len(calls)==1
    clock[0]+=120
    def admitted(**kwargs):
        calls.append(1);clock[0]+=1.
        write_json(kwargs['receipt_path'],dict(gates=dict(CPU_SMT='PASS')))
        return dict(cpu=0)
    assert w.admission(admitted,receipt_path=tmp_path/'admission002.json')['cpu']==0
    assert w.probe_wall()==2.25 and len(calls)==2
    (tmp_path/'aux_pre_001').mkdir()
    write_json(tmp_path/'aux_pre_001/summary.json',dict(elapsed_seconds=3.))
    assert w.auxiliary_wall()==w.carried_auxiliary_seconds+5.25
    write_json(tmp_path/'probe_003.json',dict(elapsed_seconds=17.75))
    with pytest.raises(RuntimeError,match='20-second'):w.require_retry_ready()


def test_v34_namespace_storage_closed_and_consumed_reentry(tmp_path,monkeypatch):
    from src.io import full_input_block_v34 as io,full_input_block_v33 as old
    from src.io.input_loader import InputError
    from src.runners.diagnostic_storage import inventory
    from src.io.task042_profile import TASK042_PROFILES
    dat='input/task042_neural_coarse_inverse/v34_full_input_diagnostic.dat'
    assert old.load_return_diagnostic(dat) is None
    book=dict(closed=False,active=None,runs=[],actor_wall_seconds=0.)
    fake=SimpleNamespace(TMP=tmp_path,require_qualification=lambda:{},
        require_live=lambda **kw:dict(heavy_remaining_seconds=80000.),ledger=lambda:book,
        auxiliary_wall=lambda:161.20563597988803,actor_timeout=lambda *a:180.,allow_entry_repair=lambda:True)
    monkeypatch.setattr(io,'window',fake)
    spec=io.load_return_diagnostic(dat)
    assert spec.derived['stage']==TASK042_PROFILES['task042_v34_diagnostic']=='V34-DIAGNOSTIC'
    book['runs']=[dict(classification='WORKER_FAILED',counts=dict(actions=6))]
    assert io.load_return_diagnostic(dat).execution['timeout_seconds']==180.
    for closed,active in ((True,None),(False,{})):
        book.update(closed=closed,active=active)
        with pytest.raises(InputError,match='closed/active'):io.load_return_diagnostic(dat)
    for rel in ('tmp/task042/v34/a','tmp/task042/review_v31/a',
                'docs/task042_neural_coarse_inverse/outcomes/records/review_v31_test.json',
                'results/task042/task042_v34_diag/a'):
        path=tmp_path/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'12345')
    oldbytes=inventory(tmp_path,batch=33)['cumulative']['bytes']
    current=inventory(tmp_path,batch=34)
    assert current['new']['bytes']==10 and current['cumulative']['bytes']==oldbytes+15


def test_saved_analysis_partition_and_complex_cross_term_sign():
    from benchmarks.task042_full_input_checker import saved_direction_analysis
    groups=np.arange(8);r=np.arange(1,9).astype(complex)*(1+.3j)
    a=dict(input_residual=r,u=.2*r,k=.1j*r,qret=.3*r,au=.2*r,ak=.1j*r,
        aqret=.3*r,adelta=(.2-.1j)*r,aqfull=(.5-.1j)*r,aq0=.5*r)
    out=saved_direction_analysis(a,groups,np.array([5,7]))
    assert out['partition_rows']==8 and out['no_new_action'] and out['no_reference']
    for key,vector in (('input',r),('ret',r-a['aqret']),('full',r-a['aqfull']),('control',r-a['aq0'])):
        np.testing.assert_allclose(sum(x['norms'][key]**2 for x in out['regions']),np.linalg.norm(vector)**2,rtol=1e-13)
    for term in out['cross_terms'].values():
        assert term['recombination_absolute_error']<=1e-12*term['precancellation_norm_squared_scale']
    assert out['cross_terms']['outer_minus_feedback']['inner_product']['imag']>0
    assert out['cross_terms']['residual_after_return_minus_direct']['signed_twice_real']<0
