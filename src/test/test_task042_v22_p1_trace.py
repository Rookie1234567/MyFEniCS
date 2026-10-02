"""Complex Galerkin/right-PC, role-reader, actual dispatch and stop regressions."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from src.solvers.p1_trace_galerkin import RefinedCoarse,TraceGalerkinPC,normalize_transfer,assemble_coarse
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.test.test_task042_v18_completion import small_problem
from src.test.test_neural_fe_action_packet import witness
from src.solvers.gmres_cycle_commit import cycle_commit
from src.io import p1_trace_galerkin as io


def dense_case(n=14):
    packet,bar,z=small_problem(n)
    A=np.column_stack([bar.apply(np.eye(n,dtype=complex)[:,j]) for j in range(n)])
    rng=np.random.default_rng(422201);T=rng.normal(size=(n,4))+1j*rng.normal(size=(n,4))
    T,norms,row=normalize_transfer(csr_matrix(T));Ac=T.conj().T@A@T
    coarse=RefinedCoarse(Ac);body=TraceGalerkinPC(T,coarse,bar.apply)
    return packet,bar,z,A,T,coarse,body


def test_complex_nonhermitian_nonadjoint_ports_full_space_right_balancing():
    packet,bar,z,A,T,coarse,B=dense_case()
    assert np.linalg.norm(A-A.conj().T)>1
    assert np.linalg.norm(packet.S[:14,-40:]-packet.S[-40:,:14].conj().T)>1
    explicit=np.column_stack([B.apply(np.eye(14,dtype=complex)[:,j]) for j in range(14)])
    np.testing.assert_allclose(T.conj().T@A@explicit,T.conj().T.toarray(),rtol=1e-11,atol=1e-11)
    assert np.linalg.matrix_rank(explicit)==14
    assert np.linalg.matrix_rank(np.column_stack([B.Q(np.eye(14)[:,j]) for j in range(14)]))==4
    x=z[:14];v=B.apply(x);np.testing.assert_allclose(B.apply((.2+.7j)*x),(.2+.7j)*v,rtol=1e-12,atol=1e-12)
    np.testing.assert_array_equal(coarse.solve(np.zeros(4,complex)),np.zeros(4,complex))
    assert np.linalg.norm(A@B.apply(x)-x)>1e-3  # not an accurate fine inverse
    wrong=(T.T@A@T).toarray() if hasattr(T.T@A@T,'toarray') else T.T@A@T
    assert np.linalg.norm(wrong-coarse.Ac)>1e-2


def test_local_original_schur_and_floquet_assembly_matches_original_action():
    p,*_=witness();T,_,_=normalize_transfer(csr_matrix([[1.+.2j],[.5-.3j]]))
    # witness has two canonical masters, complex duplicate expansion and ports
    from src.solvers.fixed_p3_ilu0 import direct_C
    from src.solvers.augmented_trace_lsqr import BarAction
    from types import SimpleNamespace
    C=np.column_stack([direct_C(p,np.eye(p.np,dtype=complex)[:,j]) for j in range(p.np)])
    bar=BarAction(SimpleNamespace(packet=p,H=p.a['Hhat'],C=C))
    Ac,receipt=assemble_coarse(p,T)
    np.testing.assert_allclose(Ac[:,0],T.conj().T@bar.apply(T[:,0].toarray().ravel()),rtol=1e-12,atol=1e-12)
    assert not receipt['global_fine_matrix_constructed']


def test_normalization_does_not_drop_tiny_entries_and_rejects_rank_and_capacity():
    a=csr_matrix([[1,0],[1e-20,1],[0,1e-22]],dtype=complex);T,norms,row=normalize_transfer(a)
    assert T.nnz==a.nnz and row['full_column_rank']
    with pytest.raises(ValueError,match='zero'):normalize_transfer(csr_matrix((3,2),dtype=complex))
    with pytest.raises(ValueError,match='independent'):normalize_transfer(csr_matrix(np.ones((3,2),complex)))
    with pytest.raises(MemoryError):normalize_transfer(csr_matrix(np.eye(2049,dtype=complex)))


def test_fixed_coarse_lu_one_refinement_and_individual_triangular_cost():
    count={};A=np.array([[2+1j,.4-.9j],[-.2+.3j,1-.8j]])
    def charge(key,n=1):count[key]=count.get(key,0)+n
    coarse=RefinedCoarse(A,count=charge);s=np.array([1+.7j,.3-.2j]);u=coarse.solve(s)
    np.testing.assert_allclose(A@u,s,rtol=1e-14,atol=1e-14)
    assert count==dict(factor_setups=1,coarse_triangular=4)
    with pytest.raises(ValueError,match='rcond'):RefinedCoarse(np.diag([1,1e-14]).astype(complex))


def test_offline_trace_projection_uses_homogeneous_recovery_and_complex_cross():
    from src.solvers.p1_trace_error_diagnostic import homogeneous_projection
    packet,bar,reference,A,T,coarse,B=dense_case()
    warm=bar.close(.41*reference[:packet.nt],packet.a['b'])
    values,row=homogeneous_projection(packet,bar,T,reference,warm)
    assert np.linalg.norm(packet.a['b'][-40:])>0
    assert np.linalg.norm(packet.recover(values['e'])-(packet.recover(reference)-packet.recover(warm)))>1
    np.testing.assert_allclose(values['Fe'],packet.recover(reference)-packet.recover(warm),atol=1e-13)
    np.testing.assert_allclose(values['Fe'],values['Fq']+values['Fc'],atol=1e-13)
    assert row['trace_Gram_stationarity']<1e-12
    assert row['operation_cross_sum_defect']<1e-12
    assert row['original_action_pair']['operation_relative']<1e-12
    assert not row['reference_feedback']


def test_zero_stage_role_rejects_parent_before_any_decompression(tmp_path,monkeypatch):
    from src.solvers.p1_trace_study import load_state
    def trap(*a,**kw):raise AssertionError('parent was opened')
    stage=SimpleNamespace(name='Z',artifact=tmp_path/'own-Z',
                          io=SimpleNamespace(ARTIFACT_ROOT=tmp_path/'v22',physical_state=trap))
    with pytest.raises(ValueError,match='cold actor'):
        load_state(stage,dict(state=dict(path=str(tmp_path/'v21/warm.npz'))))


def test_actual_right_cycle_return_close_save_audit_and_pending_recovery(tmp_path):
    packet,bar,z,A,T,coarse,B=dense_case()
    base=z[:14]*.37;identity={'test':'V22-real-BarAction'};audit_calls=[]
    def audit(x):audit_calls.append(x.copy());return packet.audit(x)
    def fault(where):
        if where=='before_audit':raise RuntimeError('injected after returned closed state')
    with pytest.raises(RuntimeError,match='injected'):
        cycle_commit(bar,base,packet.a['b'],tmp_path/'cycle',identity,{},audit,restart=256,
            preconditioner=B.apply,residual_action=bar.apply,fault=fault)
    before_B=B.calls
    row=cycle_commit(bar,base,packet.a['b'],tmp_path/'cycle',identity,{},audit,restart=256,
        preconditioner=B.apply,residual_action=bar.apply)
    assert B.calls==before_B and row['returned_boundary_resumed'] and len(audit_calls)==1
    with np.load(row['state']['path']) as f:
        # The real driver stops at the registered absolute 1e-8 full-b rule.
        assert packet.audit(f['z'])['schur_relative']<=1e-8
        assert np.linalg.norm(f['z']-z)/np.linalg.norm(z)<1e-7
        np.testing.assert_allclose(f['trace'],base+f['By'],rtol=0,atol=0)
        assert f['port'].shape==(40,) and np.linalg.norm(f['port'])>0
        assert np.linalg.norm(f['y']-f['By'])>1e-3
    assert row['inner']['callback_type']=='pr_norm' and row['inner']['info']==0


@pytest.mark.parametrize('trap_key',['x','CU_u','outer_directions'])
def test_warm_reader_white_list_and_zero_role_never_opens_parent(tmp_path,monkeypatch,trap_key):
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    monkeypatch.setattr(io,'ROOT',tmp_path)
    p=tmp_path/'benchmarks/artifacts/task042/v21';p.mkdir(parents=True)
    n=5;t=np.arange(n,dtype=complex);port=np.ones(40,complex);z=np.r_[t,port]
    state=atomic_arrays(p/'state.npz',trace=t,port=port,z=z,residual=z*.1,**{trap_key:np.ones(9)})
    real=np.load;decoded=[]
    class Trap:
        def __enter__(self):self.f=real(state['path']);self.files=self.f.files;return self
        def __exit__(self,*a):self.f.close()
        def __getitem__(self,key):
            decoded.append(key)
            if key not in ('trace','port','z','residual'):raise AssertionError('forbidden old directions decoded')
            return self.f[key]
    monkeypatch.setattr(np,'load',lambda *a,**k:Trap())
    result=io.physical_state(dict(state=state),role='WARM',nt=n,np_=40,size=n+40)
    assert decoded==['trace','port','z','residual'] and np.array_equal(result['z'],z)
    decoded.clear()
    with pytest.raises(ValueError,match='cold role'):io.physical_state(dict(state=state),role='ZERO',nt=n,np_=40,size=n+40)
    assert not decoded
    bad=dict(state,trace_sha256='bad')
    with pytest.raises(ValueError,match='member hash'):io.physical_state(dict(state=bad),role='WARM',nt=n,np_=40,size=n+40)


def test_six_actual_input_schema_and_registered_real_driver(tmp_path,monkeypatch):
    from src.io.task042_profile import TASK042_PROFILES
    from src.solvers import p1_trace_window as w
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'not-frozen')
    # A completed real campaign must remain frozen. Only this test process
    # and its validate-only child receive a separate, non-running fixture.
    monkeypatch.setattr(w,'require_live',lambda **kw:dict(heavy_remaining_seconds=12600))
    monkeypatch.setattr(w,'ledger',lambda:dict(routes={}))
    child='''import runpy,sys
from pathlib import Path
from src.io import p1_trace_galerkin as io
from src.solvers import p1_trace_window as w
io.ARTIFACT_ROOT=Path(sys.argv[1])/'not-frozen'
w.require_live=lambda **kw:dict(heavy_remaining_seconds=12600)
w.ledger=lambda:dict(routes={})
sys.argv=['scripts/run_case.py',sys.argv[2],'--validate-only']
runpy.run_path('scripts/run_case.py',run_name='__main__')
'''
    for stage,name in io.FILES.items():
        path=io.ROOT/f'input/task042_neural_coarse_inverse/v22_{name}.dat';spec=io.load_p1_trace(path)
        assert spec.derived['stage']=='V22-'+stage and TASK042_PROFILES[spec.solver['preconditioner']]=='V22-'+stage
        result=subprocess.run([sys.executable,'-c',child,str(tmp_path),str(path)],text=True,capture_output=True)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)['stage']=='V22-'+stage
    p=tmp_path/'bad.dat';p.write_text((io.ROOT/'input/task042_neural_coarse_inverse/v22_p1_coarse_warm.dat').read_text().replace('stage = "P"','stage = "FAKE"'))
    with pytest.raises(Exception,match='unregistered'):io.load_p1_trace(p)


def test_deadline_UTC_monotonic_boot_and_real_timeout_descendant_cleanup(tmp_path):
    from src.solvers.exact_recycle_window import evaluate_window
    from benchmarks.subreaper_watchdog import supervise
    window=dict(start_utc='2026-10-02T00:00:00+00:00',start_monotonic=100.,boot_id='a',heavy_limit_seconds=12600,total_limit_seconds=14400)
    from datetime import datetime
    origin=datetime.fromisoformat(window['start_utc']).timestamp()
    row=evaluate_window(window,utc_seconds=origin+14401,monotonic=101.,boot_id='a')
    assert row['total_remaining_seconds']==0
    row=evaluate_window(window,utc_seconds=origin+100,monotonic=20000.,boot_id='new')
    assert row['elapsed_seconds']==100 and not row['monotonic_same_boot']
    script='import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(20)"]); time.sleep(20)'
    result=supervise([sys.executable,'-c',script],tmp_path/'timeout',wall_seconds=.7,interval=.1,
        rss_hard_limit_bytes=2*2**30,rss_warning_bytes=2**30,include_pss=False)
    assert result['descendants_cleared'] and result['leader_exit_code']!=0


@pytest.mark.parametrize('role',['P','Z'])
def test_actual_dat_stage_pc_gmres_close_save_audit_and_cold_access(tmp_path,monkeypatch,role):
    from src.runners import orthonormal_trace_reprofile as adapter
    from src.runners.p1_trace_galerkin import P1Stage
    from src.solvers import p1_trace_study as core,p1_trace_window as w
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'benchmarks/artifacts/task042/v22')
    spec=io.load_p1_trace(io.ROOT/f'input/task042_neural_coarse_inverse/v22_{io.FILES[role]}.dat')
    for key,file in [('LEDGER_PATH','ledger.json'),('WINDOW_PATH','window.json'),('JOURNAL_PATH','journal.jsonl')]:
        monkeypatch.setattr(w,key,tmp_path/file)
    w.WINDOW_PATH.write_text('{}')
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800))
    monkeypatch.setattr(w,'require_live',lambda **kw:w.snapshot())
    packet,bar,exact,A,T,coarse,body=dense_case()
    base=.37*exact[:packet.nt]
    parent=tmp_path/'benchmarks/artifacts/task042/v21';parent.mkdir(parents=True)
    arrays,_=__import__('src.solvers.gmres_cycle_commit',fromlist=['close_point']).close_point(bar,base,packet.a['b'])
    own=json.loads(io.PLAN_PATH.read_text());own['initial_states']['GPOLY']['state']=atomic_arrays(parent/'start.npz',**arrays)
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(own))
    monkeypatch.setattr(io,'ROOT',tmp_path);monkeypatch.setattr(io,'PLAN_PATH',plan)
    monkeypatch.setattr(adapter,'original_packet',lambda fe:packet)
    monkeypatch.setattr(P1Stage,'sample',lambda self:dict(rss_bytes=1000000,swap_bytes=0))
    read=io.read_result
    pre=dict(warm=dict(qualified=True,old_fast_residual_full_b_difference=0),PC_qualified=True)
    monkeypatch.setattr(io,'read_result',lambda name:(pre,None) if name=='SETUP' else read(name))
    def test_bars(stage):
        stage.fast=SimpleNamespace(apply=packet.apply,counts=dict(S=0,SH=0));return bar,bar
    monkeypatch.setattr(core,'bars',test_bars)
    def test_PC(stage,setup,fast):
        return TraceGalerkinPC(T,RefinedCoarse(coarse.Ac,count=stage.pc_count),bar.apply,count=stage.pc_count)
    monkeypatch.setattr(core,'load_PC',test_PC)
    if role=='Z':
        original=io.physical_state
        def cold_guard(item,**kw):
            if Path(item['state']['path']).is_relative_to(parent):raise AssertionError('cold decoded old warm arrays')
            return original(item,**kw)
        monkeypatch.setattr(io,'physical_state',cold_guard)
    directory=tmp_path/f'actual_{role}';directory.mkdir();(directory/'source_sha.txt').write_text('a'*40)
    stage=P1Stage(spec,directory);result=core.route(stage);stage.finish(result)
    stored,_=read(role)
    assert stored['first_pass_cycle']==1 and stored['final']['committed']
    assert stored['aux_counts']['B']>0 and stored['aux_counts']['coarse_triangular']>0
    if role=='Z':assert stored['cold_parent_NPZ_decoded'] is False
    with np.load(stored['final']['state']['path']) as values:
        assert values['z'].shape==(packet.nt+40,) and values['port'].shape==(40,)
        assert packet.audit(values['z'])['schur_relative']<=1e-6
        # Affine particular recovery must cancel when constructing error fields.
        homogeneous=packet.recover(exact-values['z'])-packet.recover(np.zeros(packet.size,complex))
        np.testing.assert_allclose(homogeneous,packet.recover(exact)-packet.recover(values['z']),atol=1e-14)


def test_durable_kill_upper_and_global_limits_do_not_reset(tmp_path,monkeypatch):
    from src.solvers import p1_trace_window as w
    for key,file in [('LEDGER_PATH','ledger.json'),('WINDOW_PATH','window.json'),('JOURNAL_PATH','journal.jsonl')]:monkeypatch.setattr(w,key,tmp_path/file)
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800))
    row=w.ledger();done=dict.fromkeys(w.CAPS,0);done.update(actions=11,B=5,coarse_triangular=20)
    upper=dict(done,actions=611,B=305,coarse_triangular=1220)
    row['active']=dict(directory='owned',source_sha='a'*40,completed=done,upper=upper)
    w.LEDGER_PATH.write_text(json.dumps(row))
    summary=dict(stage='V22-P',classification='RESOURCE_CONTROLLED_STOP',leader_exit_code=-9,
        sampled_process_tree_rss_peak_bytes=100,sampled_process_tree_swap_peak_bytes=0,descendants_cleared=True)
    row=w.settle_run('owned',summary,17)
    assert row['charged']['actions']==611 and row['charged']['coarse_triangular']==1220
    assert row['routes']['P']['wall_seconds']==17 and row['active'] is None
    assert row['runs'][-1]['completed']['actions']==11 and not row['runs'][-1]['exact_counts']
