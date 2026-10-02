"""Eight-block non-Hermitian diagnosis, fixed inventory and hard budgets."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import lstsq

from src.solvers.block_residual_direction import diagnose,decision,block_response
from src.solvers.block_direction_window import CAPS,validate_increment
from src.solvers.exact_recycle_window import evaluate_window
from src.io import block_direction_diagnostic as io
from src.test.test_task042_v24_local_coarse import local
from src.test.test_task042_v22_p1_trace import dense_case


def test_nonhermitian_nonmutual_forty_port_homogeneous_residual_and_exact_ls():
    packet,bar,z,A,*_=dense_case(n=16)
    assert np.linalg.norm(A-A.conj().T)>1
    assert np.linalg.norm(packet.S[:16,-40:]-packet.S[-40:,:16].conj().T)>1
    rhs=packet.a['b'];t=.3*z[:16]
    closed=bar.close(t,rhs)
    r=bar.reduced_rhs(rhs)-bar.apply(t)
    np.testing.assert_allclose((rhs-packet.apply(closed))[:16],r,atol=1e-12)
    assert np.linalg.norm(closed[-40:])>0
    calls=[];counts={}
    def action(x):calls.append(x.copy());return bar.apply(x)
    def count(k,n=1):counts[k]=counts.get(k,0)+n
    L=local(A,count)
    before=counts.get('local_lu_solve',0)
    result,arrays=diagnose(r,L,action,bnorm=np.linalg.norm(rhs),count=count)
    assert result['trustworthy'] and result['rank']==8
    assert len(calls)==10 and counts['local_lu_solve']-before==8
    assert counts['thin_decompositions']==1
    assert result['eta8']<=result['eta1']<=min(1,result['eta_unit'])+1e-13
    expected=lstsq(arrays['images'],r,lapack_driver='gelsd',cond=1e-12)[0]
    np.testing.assert_allclose(arrays['images']@arrays['coefficients'],arrays['images']@expected,atol=1e-11)
    for j,ids in enumerate(L.rows):
        np.testing.assert_allclose(arrays['images'][ids,j],r[ids],atol=1e-12)
        other=np.setdiff1d(np.arange(16),ids)
        np.testing.assert_array_equal(arrays['directions'][other,j],0)
    assert result['independent_recombination']['best']['full_b_relative']<1e-12


def test_response_cross_terms_do_not_replace_coherent_sums():
    X=np.zeros((16,8),complex)
    X[:,0]=2+3j;X[:,1]=-2-3j
    rows=[np.flatnonzero(np.arange(16)%8==i) for i in range(8)]
    report=block_response(X,rows,np.ones(16))
    for item in report:
        assert item['coherent_sum_norm']==0 and item['cancellation_ratio']==0
        assert item['sum_individual_norm_sq']>0
        assert abs(item['sum_individual_norm_sq']+item['twice_real_cross_sum'])<1e-12
        assert len(item['complex_cross_products'])==8


@pytest.mark.parametrize('case',['zero_rhs','zero_columns','rank_deficient','below_operation_floor'])
def test_unresolved_cases_never_become_positive_coefficients(case):
    A=np.eye(16,dtype=complex);L=local(A);r=np.ones(16,complex)
    action=lambda x:x
    scale=None
    if case=='zero_rhs':r*=0
    if case=='zero_columns':action=lambda x:np.zeros_like(x)
    if case=='rank_deficient':action=lambda x:np.ones(16,complex)*np.sum(x)
    if case=='below_operation_floor':scale=lambda x:1e30
    result,_=diagnose(r,L,action,bnorm=1,operation_scale=scale)
    assert result['status']=='NUMERICALLY_UNRESOLVED' and not result['trustworthy']
    if case=='zero_rhs':assert result['eta8']==0
    if case in ('zero_columns','rank_deficient'):assert result['rank']<8


def test_wrong_diagonal_or_nonlinear_action_is_not_an_algorithm_negative():
    L=local(np.eye(16,dtype=complex));r=np.arange(16,dtype=complex)+1j
    result,_=diagnose(r,L,lambda x:2*x+x*x,bnorm=1)
    assert not result['gates']['diagonal'] and not result['gates']['recombination']
    assert not result['trustworthy']


@pytest.mark.parametrize('which',['signal','weak','mixed','unresolved'])
def test_predeclared_decision_uses_only_both_fixed_final_states(which):
    a=dict(trustworthy=True,eta8=.2,eta1=.8)
    b=dict(trustworthy=True,eta8=.95,eta1=.97)
    choices=dict(signal=([a,a],'BLOCK_DIRECTION_COMBINATION_SIGNAL'),weak=([b,b],'EIGHT_DIRECTIONS_WEAK'),
        mixed=([a,b],'STATE_DEPENDENT_INCONCLUSIVE'),unresolved=([dict(a,trustworthy=False),a],'NUMERICALLY_UNRESOLVED'))
    rows,want=choices[which]
    assert decision([dict(trustworthy=False),*rows])==want


def test_budget_and_real_utc_cannot_be_refreshed_or_hidden_by_new_boot():
    row=dict(start_utc='2026-10-02T23:01:15+00:00',start_monotonic=100,boot_id='old',heavy_limit_seconds=4500,total_limit_seconds=5400)
    from datetime import datetime
    start=datetime.fromisoformat(row['start_utc']).timestamp()
    x=evaluate_window(row,utc_seconds=start+4501,monotonic=99,boot_id='new')
    assert x['heavy_remaining_seconds']==0 and x['total_remaining_seconds']==899
    charge=dict.fromkeys(CAPS,0);done=deepcopy(charge);charge['actions']=63
    validate_increment(charge,done,'actions',1)
    with pytest.raises(RuntimeError,match='cap'):validate_increment(charge,done,'actions',2)
    done['local_lu_solve']=96
    with pytest.raises(RuntimeError,match='cap'):validate_increment(charge,done,'local_lu_solve')


def test_wrong_hash_and_reader_whitelist_no_forbidden_decode(tmp_path,monkeypatch):
    from src.solvers.neural_fe_action_packet import array_hash,file_hash
    root=tmp_path/'benchmarks/artifacts/task042/v24';root.mkdir(parents=True)
    z=np.arange(44,dtype=complex);values=dict(trace=z[:4],port=z[4:],z=z,residual=z*.1)
    path=root/'state.npz';np.savez(path,**values,outer_directions=np.ones((100,100)))
    item=dict(state=dict(path=str(path),sha256=file_hash(path),**{k+'_sha256':array_hash(v) for k,v in values.items()}))
    monkeypatch.setattr(io,'ROOT',tmp_path)
    p=SimpleNamespace(nt=4,np=40,size=44)
    actual=io.physical_state(item,p)
    assert set(actual)==set(values)
    item['state']['z_sha256']='bad'
    with pytest.raises(ValueError,match='member hash'):io.physical_state(item,p)
    manifest=root/'manifest.json';manifest.write_text('{}')
    with pytest.raises(ValueError,match='path/hash'):io.checked_json(dict(path=str(manifest),sha256='bad'),root)


def test_actual_one_run_schema_has_only_new_registered_diagnostic(monkeypatch,tmp_path):
    from src.solvers import block_direction_window as w
    monkeypatch.setattr(w,'require_live',lambda **kw:dict(heavy_remaining_seconds=3000))
    monkeypatch.setattr(w,'ledger',lambda:dict(closed=False,active=None,runs=[],actor_wall_seconds=0))
    path=io.ROOT/'input/task042_neural_coarse_inverse/v25_block_residual_diagnostic.dat'
    spec=io.load_block_diagnostic(path)
    assert spec.derived['stage']=='V25-DIAGNOSTIC' and spec.execution['timeout_seconds']==600
    wrong=tmp_path/'wrong.dat';wrong.write_text(path.read_text().replace('DIAGNOSTIC','VERIFY'))
    with pytest.raises(Exception,match='one diagnostic'):io.load_block_diagnostic(wrong)


def test_independent_deadline_stops_and_clears_all_own_descendants(tmp_path):
    import sys
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.task042_shared import shared_envelope
    command=[sys.executable,'-c',
        'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); time.sleep(60)']
    record=supervise(command,tmp_path/'deadline',wall_seconds=1,interval=.5,
        timebase_guard=True,hard_stop_immediate=True,rss_hard_limit_bytes=16*2**30,
        rss_warning_bytes=12*2**30,memory_envelope_provider=shared_envelope,
        include_pss=False,stop_on_global_swap=False)
    assert record['classification']!='COMPLETED'
    assert record['descendants_cleared'] and not record['remaining_child_pids']
    assert len(record['observed_child_pids'])>=2
    assert record['sampled_process_tree_swap_peak_bytes']==0
