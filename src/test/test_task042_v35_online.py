"""Bounded synthetic V35 PC, actual one-run adapter, return and cache checks."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import lu_factor,lu_solve

from src.solvers.full_input_online import FullInputPC,continue_after_cycle
from src.solvers.full_input_online_window import OnlineWindow,CAPS
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash
from src.test.test_task042_v18_completion import small_problem,SmallPacket
from benchmarks.check_full_input_online import check


class Bundle:
    def __init__(self,A,rows):
        self.rows=np.asarray(rows);self.factor=lu_factor(A[np.ix_(rows,rows)])
        self.receipts=[];self.calls=0
    def solve(self,r):
        self.calls+=1
        return lu_solve(self.factor,r)


def pc_for(A,count=lambda *a:None):
    n=len(A);joint=Bundle(A,[n-2,n-1])
    outer=[Bundle(A,[j]) for j in range(n-2)]
    return FullInputPC(n,joint,outer,lambda x:A@x,count=count),[joint,*outer]


def test_noncommuting_complex_explicit_block_product_and_actual_calls():
    rng=np.random.default_rng(423501);n=8
    A=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+8*np.eye(n)
    pc,blocks=pc_for(A);BJ=np.zeros((n,n),complex);LO=BJ.copy()
    for block in blocks:
        inverse=np.column_stack([block.solve(v) for v in np.eye(len(block.rows))])
        (BJ if block is blocks[0] else LO)[np.ix_(block.rows,block.rows)]=inverse
    expected=BJ+(np.eye(n)-BJ@A)@LO@(np.eye(n)-A@BJ)
    for rows in (np.arange(n),blocks[0].rows,np.arange(n-2)):
        r=np.zeros(n,complex);r[rows]=rng.normal(size=len(rows))+1j*rng.normal(size=len(rows))
        r.setflags(write=False);before=r.copy();counts=[b.calls for b in blocks]
        np.testing.assert_allclose(pc(r),expected@r,rtol=1e-12,atol=1e-12)
        np.testing.assert_array_equal(before,r)
        assert [b.calls-old for b,old in zip(blocks,counts)]==[2,1,1,1,1,1,1]
    r=rng.normal(size=n)+1j*rng.normal(size=n);s=r[::-1]
    np.testing.assert_allclose(pc((.4+.7j)*r+(-.3+.5j)*s),(.4+.7j)*pc(r)+(-.3+.5j)*pc(s),atol=1e-12)
    np.testing.assert_array_equal(pc(r),pc(r))
    counts=[b.calls for b in blocks]
    np.testing.assert_array_equal(pc(np.zeros(n,complex)),np.zeros(n,complex))
    assert [b.calls for b in blocks]==counts and pc.zero_calls==1
    with pytest.raises(ValueError,match='finite'):pc(np.full(n,np.nan))
    with pytest.raises(ValueError,match='cover'):FullInputPC(n,blocks[0],blocks[:-1],lambda x:A@x)


def test_single_step_amplification_does_not_imply_gmres_failure():
    from src.solvers.resumable_trace_gmres import correction_cycle
    A=np.array([[1,2],[3,1]],complex)
    joint=Bundle(A,[0]);outer=Bundle(A,[1]);pc=FullInputPC(2,joint,[outer],lambda x:A@x)
    r=np.array([0,1],complex)
    assert np.linalg.norm(r-A@pc(r))==6
    y,info=correction_cycle(lambda y:A@pc(y),np.zeros(2,complex),r,1.,restart=256)
    assert info['info']==0
    np.testing.assert_allclose(A@pc(y),r,atol=1e-12)


def isolated_window(tmp_path):
    tmp_path.mkdir(parents=True,exist_ok=True)
    w=OnlineWindow(tmp_path)
    w.snapshot=lambda:dict(heavy_remaining_seconds=80000.,total_remaining_seconds=85000.)
    return w


def test_paid_probe_WAIT_failed_consumption_and_closed_fixture(tmp_path,monkeypatch):
    from src.solvers import full_input_online_window as module
    w=isolated_window(tmp_path);clock=[100.]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    def refused(**kwargs):
        clock[0]+=1.2;write_json(kwargs['receipt_path'],dict(gates=dict(CPU_SMT='FAIL')))
        raise RuntimeError('no audited core')
    with pytest.raises(RuntimeError,match='audited'):w.admission(refused,receipt_path=tmp_path/'receipt.json')
    assert w.probe_wall()==pytest.approx(1.2)
    with pytest.raises(RuntimeError,match='backoff'):w.require_retry_ready()
    clock[0]+=120;w.require_retry_ready()
    book=w.ledger();counts=dict.fromkeys(CAPS,0);counts['actions']=3
    book['active']=dict(directory=str(tmp_path/'actor'),source_sha='a'*40,completed=counts,upper=dict(counts,actions=4))
    write_json(w.LEDGER_PATH,book);(tmp_path/'actor').mkdir()
    summary=dict(stage='V35-ONLINE',classification='WORKER_FAILED',leader_exit_code=1,elapsed_seconds=2.,
        source_state=dict(source_sha='a'*40),descendants_cleared=True,
        sampled_process_tree_rss_peak_bytes=100,sampled_process_tree_swap_peak_bytes=0)
    settled=w.settle_run(tmp_path/'actor',summary,3.)
    assert settled['charged']['actions']==4 and settled['runs'][0]['completed']['actions']==3
    assert w.charged_wall()==pytest.approx(3.2)
    w.validate_increment(settled['charged'],dict.fromkeys(CAPS,0),'actions',2196)
    with pytest.raises(RuntimeError,match='cap'):w.validate_increment(settled['charged'],counts,'actions',2200)
    settled['closed']=True;write_json(w.LEDGER_PATH,settled)
    with pytest.raises(RuntimeError,match='closed'):w.require_retry_ready()
    # This fixture owns no actual V24-V34 files or clocks.
    w.snapshot=lambda:dict(heavy_remaining_seconds=0.,total_remaining_seconds=0.)
    with pytest.raises(RuntimeError,match='deadline'):w.require_live()


def test_original_uncondensed_audit_reuses_only_original_Hp():
    from src.test.test_neural_fe_action_packet import witness
    packet,*_=witness();z=np.array([1+.3j,.4-.2j,.1+.7j,.2-.3j])
    old=packet.audit(z);factor=lu_factor(packet.a['Hp']);calls=[]
    def solve(rhs):
        calls.append(1);return lu_solve(factor,rhs)
    reused=packet.audit(z,port_solver=solve)
    assert len(calls)==2
    for key in old:
        if isinstance(old[key],bool):assert reused[key]==old[key]
        else:np.testing.assert_allclose(reused[key],old[key],rtol=1e-13,atol=1e-13)


def actual_synthetic_chain(tmp_path,monkeypatch):
    from src.io import full_input_online as io
    from src.runners import full_input_online as runner,orthonormal_trace_reprofile as old
    from src.solvers import full_input_online_study as study
    from src.io.task042_profile import TASK042_PROFILES
    w=isolated_window(tmp_path/'window')
    hooks=SimpleNamespace(**{k:getattr(w,k) for k in ('ledger','snapshot','require_live','validate_increment',
        'journal','charged_wall','auxiliary_wall','actor_timeout')},CAPS=CAPS,LEDGER_PATH=w.LEDGER_PATH,
        require_qualification=lambda:dict(status='PASSED'))
    monkeypatch.setattr(io,'window',hooks);monkeypatch.setattr(runner,'window',hooks)
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'artifacts')
    spec=io.load_online('input/task042_neural_coarse_inverse/v35_online_cold.dat')
    assert TASK042_PROFILES[spec.solver['preconditioner']]=='V35-ONLINE'
    assert spec.execution['mpi_size']==1 and spec.execution['terminate_memory_gib']==16
    packet,bar,exact=small_problem(8)
    class Auditable(SmallPacket):
        def audit(self,z,port_solver=None):
            if port_solver is not None:
                port_solver(self.a['b'][-40:]);port_solver(self.a['b'][-40:])
            return super().audit(z)
    packet.__class__=Auditable;packet.a['Hp']=packet.a['Hhat']
    own=json.loads(io.PLAN_PATH.read_text());own['b_sha256']=array_hash(packet.a['b'])
    plan=tmp_path/'plan.json';write_json(plan,own)
    monkeypatch.setattr(io,'PLAN_PATH',plan)
    monkeypatch.setattr(old,'original_packet',lambda fe:packet)
    monkeypatch.setattr(runner.OnlineStage,'sample',lambda self:dict(rss_bytes=100,swap_bytes=0))
    monkeypatch.setattr(runner.OnlineStage,'guard',lambda self,**kw:None)
    def synthetic_run(stage):
        A=np.column_stack([bar.apply(v) for v in np.eye(8)])
        pc,bundles=pc_for(A,stage.pc_count)
        fast=SimpleNamespace(counts=dict(S=0,SH=0),costs=dict(S=0.,SH=0.))
        return study.solve_trajectory(stage,bar,bar,fast,pc,bundles,
            dict(status='PENDING',cycles=[],backend='ORIGINAL',queue_frozen=False))
    monkeypatch.setattr(study,'run',synthetic_run)
    directory=tmp_path/'one_run';directory.mkdir();(directory/'source_sha.txt').write_text('a'*40)
    stage=runner.OnlineStage(spec,directory)
    result=runner.execute_stage(stage);stage.finish(result)
    # The real launcher settles/clears active before another stage is loaded.
    # Exercise that boundary in our own fixture rather than bypassing the guard.
    w.settle_run(directory,dict(stage='V35-ONLINE',classification='COMPLETED',
        leader_exit_code=0,elapsed_seconds=.1,source_state=dict(source_sha='a'*40),
        sampled_process_tree_rss_peak_bytes=100,sampled_process_tree_swap_peak_bytes=0,
        descendants_cleared=True),.2)
    stored,_=io.read_result('ONLINE')
    checked=check(stored,packet.a['b'],root=tmp_path/'artifacts',nt=8)
    assert checked['status']=='CHECKED' and stored['status']=='ORIGINAL_EQUATION_PASS'
    assert stored['initial_state'] and stored['cold_port_norm']>0
    with np.load(stored['final']['state']['path']) as state:
        np.testing.assert_allclose(state['z'],exact,rtol=1e-8,atol=1e-8)
    return stored,packet,io


def test_actual_dat_kernel_runner_return_checkpoint_independent_checker(tmp_path,monkeypatch):
    record,packet,io=actual_synthetic_chain(tmp_path,monkeypatch)
    assert record['budget_counts']['cycles']==1 and 0<record['budget_counts']['arnoldi']<=8
    assert record['budget_counts']['port_factors']==1
    assert record['budget_counts']['pc_apply']>1
    assert len(record['final']['state']['z_sha256'])==64
    assert io.load_online('input/task042_neural_coarse_inverse/v35_verify.dat').derived['stage']=='V35-VERIFY'
    with pytest.raises(Exception,match='cannot repeat'):io.load_online('input/task042_neural_coarse_inverse/v35_online_cold.dat')


@pytest.mark.parametrize('bad',['hash','member','gate','audit_pending','inventory','status'])
def test_independent_checker_rejects_hash_inventory_and_fakepass(tmp_path,monkeypatch,bad):
    record,packet,io=actual_synthetic_chain(tmp_path,monkeypatch)
    corrupted=deepcopy(record);row=corrupted['cycles'][0]
    if bad=='hash':row['state']['sha256']='0'*64
    elif bad=='member':row['state']['z_sha256']='0'*64
    elif bad=='gate':row['original_equation_gate']['status']='FAKE_PASS'
    elif bad=='audit_pending':row['audit_pending']=True
    elif bad=='inventory':corrupted['cycles']=[]
    elif bad=='status':corrupted['status']='SAME_DISCRETE_QUALIFIED'
    with pytest.raises(ValueError):check(corrupted,packet.a['b'],root=tmp_path/'artifacts',nt=8)


def test_prescribed_second_cycle_gate_uses_full_equation_and_physical_b():
    packet,_,_=small_problem();audit=packet.audit(np.zeros(packet.size,complex))
    audit['schur_relative']=.02
    assert continue_after_cycle(audit,1)==(False,'ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT')
    audit['schur_relative']=.009
    assert continue_after_cycle(audit,1)==(True,'SECOND_CYCLE_ADMITTED')
    assert continue_after_cycle(audit,2)==(False,'ONLINE_BLOCK_PC_NOT_QUALIFIED')


def test_real_watchdog_timeout_clears_only_own_complete_descendant_tree(tmp_path):
    import sys
    from benchmarks.subreaper_watchdog import supervise
    result=supervise([sys.executable,'-c',
        'import subprocess,time; subprocess.Popen(["sleep","30"]); time.sleep(30)'],
        tmp_path/'watchdog',wall_seconds=1.,interval=.1,timebase_guard=True,
        hard_stop_immediate=True,include_pss=False,rss_hard_limit_bytes=2*2**30,
        rss_warning_bytes=2**30,stop_on_global_swap=False)
    assert result['classification']=='PERFORMANCE_CONTROLLED_STOP'
    assert result['descendants_cleared'] and not result['remaining_child_pids']
    assert len(result['observed_child_pids'])>=2
