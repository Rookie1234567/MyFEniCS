"""Same-space complex MR, independent oracle and actual V23 stage contracts."""
import json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from src.test.test_task042_v22_p1_trace import dense_case
from src.solvers.p1_image_minres import ImageMinres,ImageMinresPC,decompose,build_image,TAU
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.gmres_cycle_commit import cycle_commit
from src.io import p1_image_minres as io


def example():
    packet,bar,z,A,T,coarse,_=dense_case()
    W=A@T;U,R,D,checks=decompose(W,T,coarse.Ac)
    image=ImageMinres(T,U,R);body=ImageMinresPC(image,bar.apply)
    return packet,bar,z,A,T,coarse,image,body,checks


def test_nonhermitian_nonmutual_40_ports_MR_optimality_balance_and_right_cycle(tmp_path):
    packet,bar,z,A,T,G,J,B,row=example()
    assert row['image_qualified'] and row['full_space_PC_safe']
    assert np.linalg.norm(A-A.conj().T)>1
    assert np.linalg.norm(packet.S[:14,-40:]-packet.S[-40:,:14].conj().T)>1
    np.testing.assert_allclose(J.apply(A@(T@np.ones(4))),T@np.ones(4),atol=1e-12)
    explicit=np.column_stack([B.apply(np.eye(14,dtype=complex)[:,j]) for j in range(14)])
    assert np.linalg.matrix_rank(explicit)==14
    np.testing.assert_allclose(J.U.conj().T@A@explicit,J.U.conj().T,atol=1e-12)
    r=bar.reduced_rhs(packet.a['b']);g=T@G.solve(T.conj().T@r);j=J.apply(r)
    assert np.linalg.norm(r-A@j)<=np.linalg.norm(r-A@g)+1e-12
    np.testing.assert_allclose(J.U.conj().T@(r-A@j),0,atol=1e-12)
    # Wrong transpose, swapping the trace and image bases, or losing the
    # full-space term must be detected rather than satisfying the oracle.
    wrong=T@np.linalg.solve(J.R,J.U.T@r)
    assert np.linalg.norm(wrong-j)>1e-3
    base=.37*z[:14]
    row=cycle_commit(bar,base,packet.a['b'],tmp_path/'cycle',{'test':'V23-right-original-bar'}, {},packet.audit,
        restart=256,preconditioner=B.apply,residual_action=bar.apply)
    with np.load(row['state']['path']) as f:
        assert f['z'].shape==(54,) and f['port'].shape==(40,)
        assert packet.audit(f['z'])['schur_relative']<1e-8
        np.testing.assert_array_equal(f['trace'],base+f['By'])
        assert np.linalg.norm(f['y']-f['By'])>1e-3
        assert np.linalg.norm(f['z']-z)/np.linalg.norm(z)<1e-7


def test_full_rank_A_and_W_do_not_make_MR_fullspace_PC_safe():
    A=np.array([[0,1],[1,0]],complex);T=csr_matrix([[1],[0]],dtype=complex)
    W=A@T;U,R,D,row=decompose(W,T,np.zeros((1,1),complex))
    assert np.linalg.matrix_rank(A)==2 and np.linalg.matrix_rank(W)==1
    assert row['image_qualified'] and not row['full_space_PC_safe']
    assert row['D_safety']['ratio']==0
    J=ImageMinres(T,U,R);B=ImageMinresPC(J,lambda x:A@x)
    actual=np.column_stack([B.apply(np.eye(2,dtype=complex)[:,j]) for j in range(2)])
    assert np.linalg.matrix_rank(actual)==1
    np.testing.assert_array_equal(B.apply(np.array([1,0],complex)),np.zeros(2,complex))


def test_fixed_once_image_columns_zero_complex_linearity_and_no_repeated_U_copy():
    packet,bar,z,A,T,G,J,B,_=example();charged={};seen=[]
    def count(k,n=1):charged[k]=charged.get(k,0)+n
    def act(x):seen.append(x.copy());return A@x
    W,receipt=build_image(T,act,count=count)
    np.testing.assert_allclose(W,A@T,atol=0)
    assert charged=={'image_builds':1,'image_columns':4} and len(seen)==4
    assert receipt['capacity']['qualified']
    np.testing.assert_array_equal(J.apply(np.zeros(14,complex)),np.zeros(14,complex))
    x=z[:14];a=.2+.9j
    np.testing.assert_allclose(B.apply(a*x),a*B.apply(x),atol=1e-12)
    before=J.U
    for _ in range(3):J.adjoint_image(x)
    assert J.U is before and J.U.flags.f_contiguous
    with pytest.raises(ValueError,match='tau'):ImageMinresPC(J,bar.apply,tau=1.)


@pytest.mark.parametrize('role',['IMAGE_SETUP','ZERO'])
def test_forbidden_roles_reject_before_any_NPZ_open(monkeypatch,role):
    def trap(*a,**kw):raise AssertionError('forbidden NPZ was opened')
    monkeypatch.setattr(np,'load',trap)
    with pytest.raises(ValueError,match='forbids'):
        io.physical_state({'state':{'path':'/does/not/exist'}},role=role,nt=3,np_=40,size=43)


def test_warm_whitelist_and_cold_returned_only(tmp_path,monkeypatch):
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    monkeypatch.setattr(io,'ROOT',tmp_path);monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'benchmarks/artifacts/task042/v23')
    root=tmp_path/'benchmarks/artifacts/task042/v21';root.mkdir(parents=True)
    t=np.ones(5,complex);port=np.ones(40,complex);z=np.r_[t,port]
    state=atomic_arrays(root/'warm.npz',trace=t,port=port,z=z,residual=z*.1,x=z,CU_u=z)
    real=np.load;decoded=[]
    class Reader:
        def __enter__(self):self.f=real(state['path']);self.files=self.f.files;return self
        def __exit__(self,*a):self.f.close()
        def __getitem__(self,key):
            decoded.append(key)
            if key not in ('trace','port','z','residual'):raise AssertionError('old workspace decoded')
            return self.f[key]
    monkeypatch.setattr(np,'load',lambda *a,**kw:Reader())
    result=io.physical_state(dict(state=state),role='WARM',nt=5,np_=40,size=45)
    assert decoded==['trace','port','z','residual'] and np.array_equal(result['z'],z)
    decoded.clear()
    with pytest.raises(ValueError,match='cold'):io.physical_state(dict(state=state),role='OWN_ZERO',nt=5,np_=40,size=45)
    assert decoded==[]


def test_five_real_dat_schema_stage_driver_and_reference_barrier(tmp_path,monkeypatch):
    from src.io.task042_profile import TASK042_PROFILES
    from src.solvers import p1_image_window as w
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'not-frozen')
    monkeypatch.setattr(w,'require_live',lambda **kw:dict(heavy_remaining_seconds=12600))
    monkeypatch.setattr(w,'ledger',lambda:dict(routes={}))
    child='''import runpy,sys
from pathlib import Path
from src.io import p1_image_minres as io
from src.solvers import p1_image_window as w
io.ARTIFACT_ROOT=Path(sys.argv[1])/'not-frozen'
w.require_live=lambda **kw:dict(heavy_remaining_seconds=12600)
w.ledger=lambda:dict(routes={})
sys.argv=['scripts/run_case.py',sys.argv[2],'--validate-only']
runpy.run_path('scripts/run_case.py',run_name='__main__')
'''
    for name,file in io.FILES.items():
        path=io.ROOT/f'input/task042_neural_coarse_inverse/v23_{file}.dat';spec=io.load_image_minres(path)
        assert spec.derived['stage']=='V23-'+name and TASK042_PROFILES[spec.solver['preconditioner']]=='V23-'+name
        r=subprocess.run([sys.executable,'-c',child,str(tmp_path),str(path)],text=True,capture_output=True)
        assert r.returncode==0,r.stderr
        assert json.loads(r.stdout)['stage']=='V23-'+name
    bad=tmp_path/'bad.dat';bad.write_text(path.read_text().replace('"VERIFY"','"FAKE"'))
    with pytest.raises(Exception,match='unregistered'):io.load_image_minres(bad)
    io.ARTIFACT_ROOT.mkdir();(io.ARTIFACT_ROOT/'FROZEN.json').write_text('{}')
    with pytest.raises(Exception,match='barrier'):io.load_image_minres(io.ROOT/'input/task042_neural_coarse_inverse/v23_p1_image_mr_warm.dat')


@pytest.mark.parametrize('role',['M','Z'])
def test_actual_dat_stage_PC_GMRES_close_atomic_original_audit(tmp_path,monkeypatch,role):
    from src.runners import orthonormal_trace_reprofile as adapter
    from src.runners.p1_image_minres import ImageStage
    from src.solvers import p1_image_study as core,p1_image_window as w
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    from src.solvers.gmres_cycle_commit import close_point
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'benchmarks/artifacts/task042/v23');io.ARTIFACT_ROOT.mkdir(parents=True)
    for key,file in [('LEDGER_PATH','ledger.json'),('WINDOW_PATH','window.json'),('JOURNAL_PATH','journal.jsonl')]:monkeypatch.setattr(w,key,tmp_path/file)
    w.WINDOW_PATH.write_text('{}');monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800));monkeypatch.setattr(w,'require_live',lambda **kw:w.snapshot())
    spec=io.load_image_minres(io.ROOT/f'input/task042_neural_coarse_inverse/v23_{io.FILES[role]}.dat')
    packet,bar,exact,A,T,G,J,B,checks=example();parent=tmp_path/'benchmarks/artifacts/task042/v21';parent.mkdir(parents=True)
    base=.37*exact[:packet.nt];arrays,_=close_point(bar,base,packet.a['b'])
    own=json.loads(io.PLAN_PATH.read_text());own['initial_states']['GPOLY']['state']=atomic_arrays(parent/'start.npz',**arrays)
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(own));monkeypatch.setattr(io,'ROOT',tmp_path);monkeypatch.setattr(io,'PLAN_PATH',plan)
    monkeypatch.setattr(adapter,'original_packet',lambda fe:packet);monkeypatch.setattr(ImageStage,'sample',lambda self:dict(rss_bytes=1000000,swap_bytes=0))
    read=io.read_result;monkeypatch.setattr(io,'read_result',lambda name:({'PC_qualified':True,'T':own['T'],'U':{'sha256':'u'},'R':{'sha256':'r'}},None) if name=='SETUP' else read(name))
    def test_bars(stage):stage.fast=SimpleNamespace(apply=packet.apply,counts=dict(S=0,SH=0));return bar,bar
    monkeypatch.setattr(core,'bars',test_bars);monkeypatch.setattr(core,'load_image',lambda stage,s:(ImageMinres(T,J.U,J.R,count=stage.pc_count),G.Ac))
    directory=tmp_path/f'actual_{role}';directory.mkdir();(directory/'source_sha.txt').write_text('a'*40)
    stage=ImageStage(spec,directory);result=core.route(stage);stage.finish(result);stored,_=read(role)
    assert stored['first_pass_cycle']==1 and stored['final']['committed']
    assert stored['aux_counts']['B_M']>0 and stored['aux_counts']['R_triangular']>0
    if role=='Z':assert stored['cold_parent_NPZ_decoded'] is False
    with np.load(stored['final']['state']['path']) as f:
        assert f['z'].shape==(54,) and f['port'].shape==(40,)
        assert packet.audit(f['z'])['schur_relative']<1e-6
        homogeneous=packet.recover(exact-f['z'])-packet.recover(np.zeros(packet.size,complex))
        np.testing.assert_allclose(homogeneous,packet.recover(exact)-packet.recover(f['z']),atol=1e-14)


def test_returned_right_cycle_failure_reaudits_without_new_GMRES(tmp_path):
    packet,bar,z,A,T,G,J,B,_=example()
    def fault(where):
        if where=='before_audit':raise RuntimeError('audit injected')
    with pytest.raises(RuntimeError,match='injected'):
        cycle_commit(bar,.1*z[:14],packet.a['b'],tmp_path/'return',{}, {},packet.audit,restart=256,preconditioner=B.apply,fault=fault)
    calls=B.calls
    row=cycle_commit(bar,.1*z[:14],packet.a['b'],tmp_path/'return',{}, {},packet.audit,restart=256,preconditioner=B.apply)
    assert row['returned_boundary_resumed'] and B.calls==calls and not row['audit_pending']


def test_UTC_and_boot_deadline_and_durable_unknown_upper(tmp_path,monkeypatch):
    from src.solvers import p1_image_window as w
    from src.solvers.exact_recycle_window import evaluate_window
    from datetime import datetime
    frozen=dict(start_utc='2026-10-02T00:00:00+00:00',start_monotonic=100.,boot_id='a',heavy_limit_seconds=12600,total_limit_seconds=14400)
    utc=datetime.fromisoformat(frozen['start_utc']).timestamp()
    assert evaluate_window(frozen,utc_seconds=utc+14401,monotonic=101,boot_id='a')['total_remaining_seconds']==0
    assert not evaluate_window(frozen,utc_seconds=utc+1,monotonic=101,boot_id='b')['monotonic_same_boot']
    for key,file in [('LEDGER_PATH','ledger.json'),('WINDOW_PATH','window.json'),('JOURNAL_PATH','journal.jsonl')]:monkeypatch.setattr(w,key,tmp_path/file)
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800))
    row=w.ledger();done=dict.fromkeys(w.CAPS,0);done.update(actions=10,B_M=4,R_triangular=4)
    upper=dict(done,actions=610,B_M=304,R_triangular=304)
    row['active']=dict(directory='owned',source_sha='a'*40,completed=done,upper=upper);w.LEDGER_PATH.write_text(json.dumps(row))
    settled=w.settle_run('owned',dict(stage='V23-M',classification='RESOURCE_CONTROLLED_STOP',leader_exit_code=-9,sampled_process_tree_rss_peak_bytes=100,sampled_process_tree_swap_peak_bytes=0,descendants_cleared=True),17)
    assert settled['charged']['actions']==610 and settled['charged']['R_triangular']==304
    assert settled['routes']['M']['wall_seconds']==17 and settled['active'] is None
