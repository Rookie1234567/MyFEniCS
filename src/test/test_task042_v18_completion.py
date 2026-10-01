"""Actual V18 dat/stage/BarAction chain and durable GMRES return boundaries."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.gmres_cycle_commit import close_point,cycle_commit
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
from src.solvers.resumable_trace_gmres import correction_cycle
from src.solvers.stable_head_varpro import PortBlocks


class SmallPacket:
    """Dense matrices only in this bounded non-Hermitian 40-port fixture."""
    def __init__(self,S,rhs):
        self.S=np.asarray(S);self.nt=len(S)-40;self.np=40;self.size=len(S)
        self.a=dict(Hhat=self.S[-40:,-40:],b=np.asarray(rhs),masters=np.arange(self.nt))
        self.bnorm=float(np.linalg.norm(rhs));self.counts=dict(S=0,SH=0,audit=0)
        self.costs=dict(S=0.,SH=0.,audit=0.)
    def apply(self,x,adjoint=False):
        if np.shape(x)!=(self.size,):raise ValueError('fixture full-z shape')
        self.counts['SH' if adjoint else 'S']+=1
        return (self.S.conj().T if adjoint else self.S)@x
    def audit(self,z):
        self.counts['audit']+=1;r=self.a['b']-self.apply(z);relative=float(np.linalg.norm(r)/self.bnorm)
        return dict(schur_relative=relative,native_relative=relative,augmented_relative=relative,
            original_total_augmented_relative=relative,port_full_rhs_relative=float(np.linalg.norm(r[-40:])/self.bnorm),
            port_operation_relative=1e-16,recovery_relative=0.,schur_original_identity_operation_relative=1e-16,
            slave_storage_max=0.,field_norm=float(np.linalg.norm(z)),strict_pass=relative<=1e-6)
    def recover(self,z):return np.r_[2*z[:self.nt],3*z[-40:]]+(2+3j)


def small_problem(nt=12):
    rng=np.random.default_rng(421801);n=nt+40
    S=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+30*np.eye(n)
    z=rng.normal(size=n)+1j*rng.normal(size=n);packet=SmallPacket(S,S@z)
    return packet,BarAction(PortBlocks(packet,S[:,-40:])),z


def test_genuine_close_full_state_and_duplicate_caller_negative():
    packet,bar,exact=small_problem();t=exact[:packet.nt];b=packet.a['b']
    arrays,identity=close_point(bar,t,b)
    assert arrays['trace'].shape==(12,) and arrays['port'].shape==(40,) and arrays['z'].shape==(52,)
    np.testing.assert_allclose(arrays['z'],exact,atol=1e-14)
    assert identity<1e-14 and packet.audit(arrays['z'])['schur_relative']<1e-14
    assert np.linalg.norm(b[-40:])>1 and np.linalg.norm(t)>1
    original_close=bar.close;before=packet.counts['S']
    bar.close=lambda t,rhs:np.r_[t,original_close(t,rhs)]
    with pytest.raises(ValueError,match='full z'):close_point(bar,t,b)
    # Only legitimate close's one original action happened; invalid concatenated
    # z was rejected before the downstream full original action.
    assert packet.counts['S']==before+1
    with pytest.raises(ValueError,match='inventory'):close_point(bar,t[:,None],b)
    with pytest.raises(ValueError,match='nonfinite'):close_point(bar,t*np.nan,b)


def test_info_callback_zero_rhs_and_fixed_physical_denominator():
    rng=np.random.default_rng(421802)
    diagonal=np.geomspace(1e-8,1,100)*(1+.2j);rhs=rng.normal(size=100)+1j*rng.normal(size=100)
    calls=[];actual,record=correction_cycle(lambda x:diagonal*x,np.zeros(100,complex),rhs,np.linalg.norm(rhs),lambda v,k:calls.append(k))
    assert record['info']==1 and record['inner_iterations']==64 and calls==list(range(1,65))
    assert record['relative_tolerance']==0 and record['absolute_tolerance']==1e-8*np.linalg.norm(rhs)
    assert np.linalg.norm(rhs-diagonal*actual)<np.linalg.norm(rhs)
    actual,record=correction_cycle(lambda x:(2+3j)*x,np.zeros(100,complex),rhs,np.linalg.norm(rhs))
    assert record['info']==0 and record['inner_iterations']==1
    exact=rhs/(2+3j)
    actual,record=correction_cycle(lambda x:(2+3j)*x,exact,(2+3j)*exact,100.)
    assert record['zero_rhs'] and record['inner_iterations']==0
    np.testing.assert_array_equal(actual,exact)
    with pytest.raises(ValueError,match='restart'):correction_cycle(lambda x:x,exact,rhs,100,restart=128)
    with pytest.raises(ValueError,match='dimensional'):correction_cycle(lambda x:x,exact[:,None],rhs,100)


@pytest.mark.parametrize('boundary',['after_proposed','before_close','after_closed','before_audit','after_audit'])
def test_return_survives_close_audit_writer_failures_no_arnoldi_replay(tmp_path,monkeypatch,boundary):
    packet,bar,_=small_problem();rhs=packet.a['b'];counts=[]
    def fail(where):
        if where==boundary:raise RuntimeError('injected '+where)
    identity=dict(operator='nonHermitian-small',source='a'*40)
    with pytest.raises(RuntimeError,match='injected'):
        cycle_commit(bar,np.zeros(packet.nt,complex),rhs,tmp_path,identity,dict(cycle=1),packet.audit,returned=lambda i:counts.append(i['inner_iterations']),fault=fail)
    assert len(counts)==1 and counts[0]>0
    assert not (tmp_path/'commit.json').exists()
    from src.solvers import gmres_cycle_commit as core
    def forbidden(*a,**k):raise AssertionError('repeated Arnoldi after durable return')
    monkeypatch.setattr(core,'correction_cycle',forbidden)
    row=cycle_commit(bar,np.zeros(packet.nt,complex),rhs,tmp_path,identity,dict(cycle=1),packet.audit)
    assert row['returned_boundary_resumed'] and row['committed'] and not row['audit_pending']
    assert row['inner']['inner_iterations']==counts[0]
    with np.load(row['state']['path']) as a:
        assert np.array_equal(a['z'][:packet.nt],a['trace']) and np.array_equal(a['z'][packet.nt:],a['port'])
        assert packet.audit(a['z'])['schur_relative']<1e-8


def test_atomic_writer_failure_and_nonfinite_hash_rollback(tmp_path,monkeypatch):
    packet,bar,_=small_problem();rhs=packet.a['b'];save=RollingCheckpoint.save
    def fail(self,arrays,metadata,**kwargs):
        if metadata['phase']=='CLOSED_AUDIT_PENDING':raise OSError('writer failed after returned state')
        return save(self,arrays,metadata,**kwargs)
    monkeypatch.setattr(RollingCheckpoint,'save',fail)
    with pytest.raises(OSError,match='writer'):cycle_commit(bar,np.zeros(packet.nt,complex),rhs,tmp_path,{},dict(cycle=1),packet.audit)
    monkeypatch.setattr(RollingCheckpoint,'save',save)
    row=cycle_commit(bar,np.zeros(packet.nt,complex),rhs,tmp_path,{},dict(cycle=1),packet.audit)
    store=RollingCheckpoint(tmp_path/'numeric',row['identity']);manifest,arrays,_=store.read()
    store.save(dict(trace=arrays['trace']*np.nan),dict(phase='bad'))
    kept,values,errors=store.read();assert kept['generation']==manifest['generation'] and errors
    store.save(dict(trace=arrays['trace']),dict(phase='half'),interrupt_after='arrays_partial')
    assert store.read()[0]['generation']==manifest['generation']
    with pytest.raises(ValueError,match='identity'):RollingCheckpoint(store.directory,dict(wrong=True)).read()


def test_two_cycle_independent_reader(tmp_path):
    packet,bar,_=small_problem(80);rhs=packet.a['b'];identity=dict(operator='independent-reader')
    first=cycle_commit(bar,np.zeros(packet.nt,complex),rhs,tmp_path/'first',identity,dict(cycle=1),packet.audit)
    with np.load(first['state']['path']) as a:t=np.array(a['trace'])
    uninterrupted=cycle_commit(bar,t,rhs,tmp_path/'whole',identity,dict(cycle=2),packet.audit)
    np.savez(tmp_path/'problem.npz',S=packet.S,rhs=rhs,trace=t)
    code='''import numpy as np,sys
from pathlib import Path
from src.test.test_task042_v18_completion import SmallPacket
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.gmres_cycle_commit import cycle_commit
p=Path(sys.argv[1]);a=np.load(p/'problem.npz');pkt=SmallPacket(a['S'],a['rhs']);bar=BarAction(PortBlocks(pkt,a['S'][:,-40:]))
cycle_commit(bar,a['trace'],a['rhs'],p/'reader',dict(operator='independent-reader'),dict(cycle=2),pkt.audit)
'''
    subprocess.run([sys.executable,'-c',code,str(tmp_path)],check=True)
    reader=json.loads((tmp_path/'reader/commit.json').read_text())
    with np.load(uninterrupted['state']['path']) as whole,np.load(reader['state']['path']) as separate:
        for key in whole.files:np.testing.assert_array_equal(whole[key],separate[key])
    assert uninterrupted['inner']['inner_iterations']==reader['inner']['inner_iterations']


def isolate_window(tmp_path,monkeypatch):
    from src.solvers import residual_completion_window as w
    for name,filename in [('LEDGER_PATH','ledger.json'),('BUDGET_PATH','budget.json'),('JOURNAL_PATH','journal.jsonl'),('WINDOW_PATH','window.json')]:
        monkeypatch.setattr(w,name,tmp_path/filename)
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=20000,total_remaining_seconds=21800))
    w.WINDOW_PATH.write_text('{}');w.freeze_route_budget()
    return w


FILES=['gmres_preflight','gmres64_gpoly','gmres64_gnn','gmres256_gpoly','gmres256_gnn','continue_gpoly','continue_gnn','verify']


def test_all_actual_dat_schema_registration_and_ref_barrier(tmp_path,monkeypatch):
    from src.io import gmres_residual_completion as io
    from src.io.task042_profile import TASK042_PROFILES
    from src.io.input_loader import InputError
    isolate_window(tmp_path,monkeypatch);monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'artifacts')
    cases=[io.load_residual_completion('input/task042_neural_coarse_inverse/v18_'+f+'.dat') for f in FILES]
    expected=[('F0',None),('G64','GPOLY'),('G64','GNN'),('G256','GPOLY'),('G256','GNN'),('R','GPOLY'),('R','GNN'),('V',None)]
    for spec,(algorithm,library) in zip(cases,expected):
        assert (spec.derived['algorithm'],spec.derived['library'])==(algorithm,library)
        assert TASK042_PROFILES[spec.solver['preconditioner']]==spec.derived['stage']
        assert spec.execution['mpi_size']==1 and spec.execution['terminate_memory_gib']==16
    assert len({s.physical_model_sha256 for s in cases})==1
    raw=Path('input/task042_neural_coarse_inverse/v18_gmres64_gnn.dat').read_text()
    wrong=tmp_path/'wrong.dat';wrong.write_text(raw.replace('library = "GNN"','library = "GPOLY"'))
    with pytest.raises(InputError,match='differs'):io.load_residual_completion(wrong)
    io.ARTIFACT_ROOT.mkdir();(io.ARTIFACT_ROOT/'FROZEN.json').write_text('{}')
    with pytest.raises(InputError,match='queue frozen'):io.load_residual_completion('input/task042_neural_coarse_inverse/v18_gmres64_gnn.dat')
    assert io.load_residual_completion('input/task042_neural_coarse_inverse/v18_verify.dat')


def test_real_dat_to_actual_stage_gmres_close_save_audit(tmp_path,monkeypatch):
    from src.io import gmres_residual_completion as io
    from src.runners import orthonormal_trace_reprofile as adapter
    from src.runners.gmres_residual_completion import CompletionStage,execute_stage
    from src.solvers import gmres_residual_completion as core
    w=isolate_window(tmp_path,monkeypatch)
    spec=io.load_residual_completion('input/task042_neural_coarse_inverse/v18_gmres64_gpoly.dat')
    packet,bar,_=small_problem();t=np.ones(packet.nt,complex)*(1+.3j)
    arrays,_=close_point(bar,t,packet.a['b']);old=tmp_path/'benchmarks/artifacts/task042/v17';old.mkdir(parents=True)
    np.savez(old/'start.npz',**arrays);state=dict(path=str(old/'start.npz'),sha256=file_hash(old/'start.npz'),z_sha256=array_hash(arrays['z']))
    own=json.loads(io.PLAN_PATH.read_text());own['initial_states']['GPOLY']['state']=state
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(own))
    monkeypatch.setattr(io,'ROOT',tmp_path);monkeypatch.setattr(io,'PLAN_PATH',plan)
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'benchmarks/artifacts/task042/v18')
    monkeypatch.setattr(adapter,'original_packet',lambda fe:packet)
    monkeypatch.setattr(CompletionStage,'sample',lambda self:dict(rss_bytes=1000000,swap_bytes=0))
    monkeypatch.setattr(core,'ports_for',lambda stage:bar.ports)
    pre=dict(libraries={'GPOLY':dict(qualified=True,original_equation_gate=dict(rho=1,status='ORIGINAL_EQUATION_FAILED'),repeated_action_full_b_difference=0)})
    read=io.read_result;monkeypatch.setattr(io,'read_result',lambda name:(pre,None) if name=='PREFLIGHT' else read(name))
    directory=tmp_path/'test_actual_chain';directory.mkdir();(directory/'source_sha.txt').write_text('a'*40)
    stage=CompletionStage(spec,directory);result=execute_stage(stage);stage.finish(result)
    stored,_=read('G64_GPOLY');assert stored['status']=='ORIGINAL_EQUATION_PASS'
    final=stored['final'];assert final['state']['z_sha256']
    with np.load(final['state']['path']) as a:
        assert a['z'].shape==(packet.nt+40,) and a['port'].shape==(40,)
        assert packet.audit(a['z'])['schur_relative']<=1e-6
    assert stored['new_Arnoldi_iterations']==sum(r['inner']['inner_iterations'] for r in stored['cycles'])
    assert w.ledger()['active']['family']=='GPOLY' and w.ledger()['active']['algorithm']=='G64'


def test_explicit_library_kill_accounting_and_budget_never_refresh(tmp_path,monkeypatch):
    w=isolate_window(tmp_path,monkeypatch);first=w.freeze_route_budget()
    assert first['uniform_route_wall_seconds']==9550
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=25000))
    assert w.freeze_route_budget()==first
    summary=dict(stage='V18-G256_GNN',classification='RESOURCE_CONTROLLED_STOP',leader_exit_code=-9,descendants_cleared=True,
        sampled_process_tree_rss_peak_bytes=100,sampled_process_tree_swap_peak_bytes=0)
    row=w.settle_run('before_loading',summary,30)
    assert row['routes']['GNN']['actions_upper']==272 and row['routes']['GNN']['arnoldi_upper']['G256']==256
    assert row['routes']['GNN']['G_wall_seconds']==30 and row['routes']['GPOLY']['wall_seconds']==0
    assert row['actions_upper']==272 and row['runs'][-1]['actions_lower']==0


def test_compensation_epoch_uses_full_close_not_duplicate_port():
    from src.test.test_task042_v16_augmented import problem
    from src.solvers.resumable_trace_study import physical_point
    op,_,rhs=problem(True);op.bar.packet.a['b']=rhs
    base=np.ones(op.bar.n,complex)*(1+2j);y=np.ones(op.bar.n,complex)
    # This is the same affine correction-epoch restore used by original R.
    from types import SimpleNamespace
    point=physical_point(op,SimpleNamespace(values=dict(x=y)),rhs,base)
    assert point['z'].shape==(op.bar.n+40,) and point['port'].shape==(40,)
    np.testing.assert_array_equal(point['z'][:op.bar.n],point['trace'])
    np.testing.assert_array_equal(point['z'][op.bar.n:],point['port'])
