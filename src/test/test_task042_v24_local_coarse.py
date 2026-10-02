"""Principal assembly, singular combination, physical right-PC and IO gates."""
import json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.linalg import qr
from scipy.sparse import csr_matrix

from src.solvers.local_block_coarse import (ROWS,capacity,assemble_blocks,
    factor_blocks,LocalBlocks,LocalCoarse,composite_overlap)
from src.solvers.p1_image_minres import ImageMinres,ImageMinresPC,TAU
from src.solvers.neural_fe_action_packet import ActionPacket,array_hash
from src.solvers.fixed_p3_ilu0 import direct_C
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.gmres_cycle_commit import cycle_commit
from src.test.test_task042_v22_p1_trace import dense_case
from src.io import local_block_pair as io


def local(A,count=lambda k,n=1:None):
    ids=[np.flatnonzero(np.arange(len(A))%8==i) for i in range(8)]
    matrices=[np.asfortranarray(A[np.ix_(r,r)]) for r in ids]
    factors,checks=factor_blocks(matrices,count=count)
    assert all(x['qualified'] for x in checks)
    return LocalBlocks(len(A),ids,matrices,factors,count=count)


def test_complete_shared_cell_and_complex_Floquet_principal_assembly():
    rng=np.random.default_rng(422401);n=16;nc=9;lt=4;p=40
    S=rng.normal(size=(2,lt,lt))+1j*rng.normal(size=(2,lt,lt))+4*np.eye(lt)
    e_rows=[];e_ids=[];e_vals=[];Es=[]
    for cell in range(nc):
        E=np.zeros((lt,n),complex)
        for j in range(lt):
            row=(cell+j)%n;v=np.exp(.31j*(cell+j))
            # Repeated slave/master contribution must be summed, not assigned.
            for weight in (.7,.3):e_rows.append(cell*lt+j);e_ids.append(row);e_vals.append(weight*v)
            E[j,row]=v
        E[0,(cell+7)%n]=.2-.4j;e_rows.append(cell*lt);e_ids.append((cell+7)%n);e_vals.append(.2-.4j)
        Es.append(E)
    arrays=dict(S=S,classes=np.arange(nc)%2,tdofs=np.zeros((nc,lt),int),idofs=np.zeros((nc,0),int),masters=np.arange(n),full_rows=np.array(n),
        Hp=np.eye(p,dtype=complex),Hhat=np.eye(p,dtype=complex)*(3+.2j),b=np.ones(n+p,complex),
        Bhat=(rng.normal(size=(nc,lt,p))+1j*rng.normal(size=(nc,lt,p)))*.03,
        Dhat=(rng.normal(size=(nc,p,lt))+1j*rng.normal(size=(nc,p,lt)))*.04,
        erows=np.array(e_rows),eids=np.array(e_ids),evals=np.array(e_vals),
        br=np.array([0,0]),bp=np.array([2,2]),bv=np.array([.1+.2j,.3-.1j]),dr=np.array([2,2]),dp=np.array([3,3]),dv=np.array([.2-.3j,.1+.1j]))
    packet=ActionPacket(arrays)
    C=np.column_stack([direct_C(packet,np.eye(p,dtype=complex)[:,j]) for j in range(p)])
    bar=BarAction(SimpleNamespace(packet=packet,H=arrays['Hhat'],C=C))
    group=np.arange(n)%8;ids,matrices,receipt=assemble_blocks(packet,group)
    explicit=np.column_stack([bar.apply(np.eye(n,dtype=complex)[:,j]) for j in range(n)])
    assert np.linalg.norm(C-np.column_stack([bar.packet.apply(np.r_[np.zeros(n),np.eye(p)[:,j]])[:n] for j in range(p)]))<1e-12
    for r,A in zip(ids,matrices):np.testing.assert_allclose(A,explicit[np.ix_(r,r)],atol=1e-12)
    K=sum(E.conj().T@S[cell%2]@E for cell,E in enumerate(Es))
    assert np.linalg.norm(K-K.T)>1
    assert receipt['shared_contributions_merged'] and not receipt['global_fine_K_or_A_constructed']


def test_nonmutual40_port_fullrank_LC_identities_right_update_and_pending_audit(tmp_path):
    packet,bar,z,A,T,*_=dense_case(n=16);counts={}
    def charge(k,n=1):counts[k]=counts.get(k,0)+n
    L=local(A,charge);U,R=qr(A@T,mode='economic');J=ImageMinres(T,U,R,count=charge)
    D,row=composite_overlap(L,J,count=charge);assert row['qualified'] and counts['DL_SVD']==1
    B=LocalCoarse(L,J,bar.apply)
    explicit=np.column_stack([B.apply(np.eye(16,dtype=complex)[:,j]) for j in range(16)])
    assert np.linalg.matrix_rank(explicit)==16
    np.testing.assert_allclose(U.conj().T@A@explicit,U.conj().T,atol=1e-12)
    np.testing.assert_allclose(B.apply(L.dop(T@np.ones(4))),T@np.linalg.solve(R,D@np.ones(4)),atol=1e-12)
    assert counts['local_triangular_pass']==2*counts['local_lu_solve'] and counts['local_lu_solve']==8*L.calls
    def fault(where):
        if where=='before_audit':raise RuntimeError('returned-audit failure')
    with pytest.raises(RuntimeError,match='returned-audit'):
        cycle_commit(bar,.37*z[:16],packet.a['b'],tmp_path/'cycle',{}, {},packet.audit,
            restart=256,preconditioner=B.apply,residual_action=bar.apply,fault=fault)
    calls=L.calls
    saved=cycle_commit(bar,.37*z[:16],packet.a['b'],tmp_path/'cycle',{}, {},packet.audit,
        restart=256,preconditioner=B.apply,residual_action=bar.apply)
    assert L.calls==calls and saved['returned_boundary_resumed']
    with np.load(saved['state']['path']) as f:
        assert f['z'].shape==(56,) and f['port'].shape==(40,)
        np.testing.assert_array_equal(f['trace'],.37*z[:16]+f['By'])
        assert packet.audit(f['z'])['schur_relative']<1e-6
        assert np.linalg.norm(f['y']-f['By'])>.001
        np.testing.assert_allclose(packet.recover(z)-packet.recover(f['z']),packet.recover(z-f['z'])-packet.recover(np.zeros(56,complex)),atol=1e-13)


def test_review_two_by_two_local_and_A_invertible_but_LC_singular():
    from scipy.linalg import lu_factor
    A=np.array([[1,-3],[1,1]],complex);T=csr_matrix(np.array([[1],[1]],complex)/np.sqrt(2))
    U=np.array([[-1],[1]],complex)/np.sqrt(2);R=np.array([[2]],complex)
    np.testing.assert_allclose(U@R,A@T,atol=1e-15)
    # The two-block counterexample is a small mathematical fixture; production
    # partition still requires exactly eight complete geometric groups.
    L=SimpleNamespace(n=2,dop=lambda x:x,apply=lambda x:x)
    J=ImageMinres(T,U,R);D,row=composite_overlap(L,J)
    assert np.linalg.det(A)!=0 and np.linalg.matrix_rank(A@T)==1
    assert not row['qualified'] and abs(D[0,0])<1e-15
    B=LocalCoarse(L,J,lambda x:A@x)
    np.testing.assert_allclose(B.apply(T.toarray()[:,0]),0,atol=1e-14)
    assert np.linalg.matrix_rank(np.column_stack([B.apply(np.eye(2)[:,j]) for j in range(2)]))==1


def test_tau_identity_special_case_matches_old_semantics():
    packet,bar,z,A,T,*_=dense_case(n=16);U,R=qr(A@T,mode='economic');J=ImageMinres(T,U,R)
    L=SimpleNamespace(apply=lambda x:TAU*x)
    new=LocalCoarse(L,J,bar.apply);old=ImageMinresPC(J,bar.apply)
    np.testing.assert_allclose(new.apply(z[:16]),old.apply(z[:16]),atol=1e-14)


def test_exact_capacity_counts_and_no_unsafe_partition():
    plan=capacity(ROWS,18144)
    assert plan['matrix_bytes']==677215296 and plan['explicit_matrices_LU_bytes']==1354430592 and plan['qualified']
    assert not capacity([6000]+list(ROWS[1:]),18144)['qualified']
    with pytest.raises(ValueError,match='missing/duplicate'):LocalBlocks(8,[np.array([0])]*8,[np.eye(1)]*8,[(np.eye(1),np.array([0]))]*8)


@pytest.mark.parametrize('role',['SETUP','ZERO','OWN_ZERO_LZ','OWN_ZERO_LCZ'])
def test_role_forbids_parent_before_array_decode(tmp_path,monkeypatch,role):
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'own')
    def trap(*a,**kw):raise AssertionError('forbidden decode')
    monkeypatch.setattr(np,'load',trap)
    with pytest.raises(ValueError,match='forbids|cold'):
        io.physical_state(dict(state=dict(path=str(tmp_path/'warm.npz'))),role=role,nt=2,np_=40,size=42)


def test_all_six_real_schema_stages_public_driver_and_freeze(tmp_path,monkeypatch):
    from src.solvers import local_block_window as w
    from src.io.task042_profile import TASK042_PROFILES
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'not-frozen')
    monkeypatch.setattr(w,'require_live',lambda **kw:dict(heavy_remaining_seconds=12600))
    monkeypatch.setattr(w,'ledger',lambda:dict(routes={}))
    for name,file in io.FILES.items():
        path=io.ROOT/f'input/task042_neural_coarse_inverse/v24_{file}.dat';spec=io.load_local_block(path)
        assert spec.derived['stage']=='V24-'+name and TASK042_PROFILES[spec.solver['preconditioner']]=='V24-'+name
        child='''import sys,runpy
from pathlib import Path
from src.io import local_block_pair as io
from src.solvers import local_block_window as w
io.ARTIFACT_ROOT=Path(sys.argv[1])/'not-frozen'
w.require_live=lambda **kw:dict(heavy_remaining_seconds=12600)
w.ledger=lambda:dict(routes={})
sys.argv=['scripts/run_case.py',sys.argv[2],'--validate-only']
runpy.run_path('scripts/run_case.py',run_name='__main__')
'''
        r=subprocess.run([sys.executable,'-c',child,str(tmp_path),str(path)],text=True,capture_output=True)
        assert r.returncode==0,r.stderr
        assert json.loads(r.stdout)['stage']=='V24-'+name
    io.ARTIFACT_ROOT.mkdir();(io.ARTIFACT_ROOT/'FROZEN.json').write_text('{}')
    with pytest.raises(Exception,match='barrier'):io.load_local_block(io.ROOT/'input/task042_neural_coarse_inverse/v24_local_warm.dat')


def test_read_only_factor_reload_bad_hash_and_no_refactor(tmp_path):
    from src.solvers.local_block_study import load_local
    from src.solvers.p1_image_study import save_array
    packet,bar,z,A,T,*_=dense_case(n=16);L=local(A);inventory=[]
    root=tmp_path/'blocks';root.mkdir()
    for b,(r,M,(LU,piv)) in enumerate(zip(L.rows,L.matrices,L.factors)):
        inventory.append(dict(block=b,rows=r.tolist(),**{k:save_array(root/f'{b}_{k}.npy',v)
            for k,v in [('matrix',M),('LU',LU),('pivots',piv)]}))
    counts={}
    def count(k,n=1):counts[k]=counts.get(k,0)+n
    stage=SimpleNamespace(pc_count=count,io=SimpleNamespace(ARTIFACT_ROOT=tmp_path),meta={},source='a'*40,packet=packet)
    reader,checks=load_local(stage,dict(block_inventory=inventory))
    assert checks['qualified'] and not checks['refactored'] and len(checks['witnesses'])==16
    np.testing.assert_allclose(reader.apply(z[:16]),L.apply(z[:16]),atol=0)
    assert all(not x.flags.writeable for x in reader.matrices)
    inventory[0]['LU']['sha256']='bad'
    with pytest.raises(ValueError,match='file hash'):load_local(stage,dict(block_inventory=inventory))


@pytest.mark.parametrize('role',['LW','LCW','LZ','LCZ'])
def test_actual_dat_stage_local_right_cycle_close_save_original_audit(tmp_path,monkeypatch,role):
    from src.solvers import local_block_window as w,local_block_study as core
    from src.runners.local_block_pair import LocalStage
    from src.runners import orthonormal_trace_reprofile as adapter
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    from src.solvers.gmres_cycle_commit import close_point
    ownroot=tmp_path/'benchmarks/artifacts/task042/v24';ownroot.mkdir(parents=True)
    monkeypatch.setattr(io,'ARTIFACT_ROOT',ownroot)
    for key,file in [('LEDGER_PATH','ledger.json'),('WINDOW_PATH','window.json'),('JOURNAL_PATH','journal.jsonl')]:monkeypatch.setattr(w,key,tmp_path/file)
    w.WINDOW_PATH.write_text('{}');monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800));monkeypatch.setattr(w,'require_live',lambda **kw:w.snapshot())
    spec=io.load_local_block(io.ROOT/f'input/task042_neural_coarse_inverse/v24_{io.FILES[role]}.dat')
    packet,bar,z,A,T,*_=dense_case(n=16);U,R=qr(A@T,mode='economic')
    parent=tmp_path/'benchmarks/artifacts/task042/v21';parent.mkdir(parents=True)
    arrays,_=close_point(bar,.37*z[:16],packet.a['b'])
    own=json.loads(io.PLAN_PATH.read_text());own['initial_states']['GPOLY']['state']=atomic_arrays(parent/'warm.npz',**arrays)
    own['local_specification']['rows']=[2]*8
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(own));monkeypatch.setattr(io,'ROOT',tmp_path);monkeypatch.setattr(io,'PLAN_PATH',plan)
    monkeypatch.setattr(adapter,'original_packet',lambda fe:packet);monkeypatch.setattr(LocalStage,'sample',lambda self:dict(rss_bytes=1000000,swap_bytes=0))
    from src.test.test_task042_v24_admission import ready_fixture
    ready=ready_fixture(rows=(2,)*8)
    read=io.read_result;monkeypatch.setattr(io,'read_result',lambda name:(ready,None) if name=='SETUP' else read(name))
    def bars(stage):stage.fast=SimpleNamespace(apply=packet.apply,counts=dict(S=0,SH=0));return bar,bar
    monkeypatch.setattr(core,'bars',bars);monkeypatch.setattr(core,'load_local',lambda stage,setup:(local(A,stage.pc_count),dict(qualified=True,independent_process=True)))
    monkeypatch.setattr(core,'load_image',lambda stage:ImageMinres(T,U,R,count=stage.pc_count))
    directory=tmp_path/role;directory.mkdir();(directory/'source_sha.txt').write_text('a'*40)
    stage=LocalStage(spec,directory);result=core.route(stage);stage.finish(result);stored,_=read(role)
    assert stored['first_pass_cycle']==1 and stored['final']['committed']
    assert stored['aux_counts']['L8']>0 and stored['aux_counts']['local_lu_solve']==8*stored['aux_counts']['L8']
    assert stored['aux_counts']['local_triangular_pass']==2*stored['aux_counts']['local_lu_solve']
    if role.endswith('Z'):assert stored['cold_parent_NPZ_decoded'] is False
    if role.startswith('LC'):assert stored['aux_counts']['R_triangular']>0
    with np.load(stored['final']['state']['path']) as f:assert packet.audit(f['z'])['schur_relative']<1e-6
