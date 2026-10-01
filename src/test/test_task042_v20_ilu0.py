"""Exact constrained assembly, fixed no-fill, right PC and actual dat wiring."""
import json
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from src.test.test_neural_fe_action_packet import witness
from src.test.test_task042_v18_completion import small_problem
from src.solvers.fixed_p3_ilu0 import assemble_K,capacity,direct_C,direct_F,no_fill_reference,PortCorrected
from src.solvers.gmres_cycle_commit import cycle_commit


def test_original_constrained_assembly_phases_and_nonmutual_port_signs():
    packet,S,*_=witness();K,row=assemble_K(packet)
    np.testing.assert_allclose(K.toarray(),S[:2,:2],rtol=1e-14,atol=1e-14)
    assert row['qualified'] and row['retained_structural_zeros'] and row['nnz']==4
    x=np.array([.2+.7j,-1+.3j])
    np.testing.assert_allclose(direct_F(packet,x),S[2:,:2]@x)
    np.testing.assert_allclose(direct_C(packet,x),S[:2,2:]@x)
    assert np.linalg.norm(S[2:,:2]-S[:2,2:].conj().T)>1
    # A duplicate constraint contribution must be merged before both factors
    # of Ec^H Sc Ec; using only one or dropping the conjugate is wrong.
    a={k:v.copy() for k,v in packet.a.items()}
    for k in ('erows','eids'):a[k]=np.r_[a[k],a[k][0]]
    a['evals']=np.r_[a['evals'],.3+.2j]
    from src.solvers.neural_fe_action_packet import ActionPacket
    changed=ActionPacket(a);K2,_=assemble_K(changed)
    for j in range(2):
        e=np.eye(2,dtype=complex)[:,j]
        np.testing.assert_allclose(K2@e,changed.apply(np.r_[e,np.zeros(2) ])[:2])
    assert capacity(packet,np.int64)['csr_bytes_upper']>capacity(packet,np.int32)['csr_bytes_upper']


def test_port_correction_same_factor_nonhermitian_inverse_and_wrong_sign():
    rng=np.random.default_rng(422005);n=15
    rnd=lambda shape:rng.normal(size=shape)+1j*rng.normal(size=shape)
    M=rnd((n,n))+60*np.eye(n);C=rnd((n,40));F=rnd((40,n));H=rnd((40,40))+70*np.eye(40)
    class Body:
        def apply(self,r):return np.linalg.solve(M,r)
    corrected=PortCorrected(Body(),C,H,lambda x:F@x)
    r=rnd(n);answer=corrected.apply(r)
    expected=np.linalg.solve(M-C@np.linalg.solve(H,F),r)
    np.testing.assert_allclose(answer,expected,rtol=1e-12,atol=1e-13)
    u=np.linalg.solve(M,r)
    wrong=u-corrected.W@np.linalg.solve(corrected.J,F@u)
    assert np.linalg.norm(expected-wrong)>1e-5


@pytest.mark.parametrize('boundary',['after_proposed','before_close','after_closed','before_audit','after_audit'])
def test_right_pc_actual_trace_forty_port_transaction_and_no_replay(tmp_path,monkeypatch,boundary):
    packet,bar,exact=small_problem(20);rhs=packet.a['b'];base=exact[:20]*.2
    pc=lambda y:(.4+.2j)*y
    def fault(at):
        if at==boundary:raise RuntimeError('injected')
    with pytest.raises(RuntimeError):cycle_commit(bar,base,rhs,tmp_path,{},dict(cycle=1),packet.audit,restart=256,preconditioner=pc,fault=fault)
    from src.solvers import gmres_cycle_commit as core
    monkeypatch.setattr(core,'correction_cycle',lambda *a,**k:pytest.fail('returned Arnoldi replayed'))
    row=cycle_commit(bar,base,rhs,tmp_path,{},dict(cycle=1),packet.audit,restart=256,preconditioner=pc)
    with np.load(row['state']['path']) as f:
        np.testing.assert_allclose(f['trace'],base+f['By'])
        np.testing.assert_allclose(f['By'],pc(f['y']))
        np.testing.assert_allclose(f['z'],exact,rtol=1e-7,atol=1e-8)
        assert f['port'].shape==(40,) and np.linalg.norm(f['trace']-f['y'])>1
    assert row['returned_boundary_resumed'] and row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'
    assert row['inner']['preconditioner'] is None and row['inner']['relative_tolerance']==0


def test_right_pc_zero_correction_does_not_force_zero_port(tmp_path):
    packet,bar,exact=small_problem();row=cycle_commit(bar,exact[:packet.nt],packet.a['b'],tmp_path,{},dict(cycle=1),packet.audit,restart=256,preconditioner=lambda x:x)
    assert row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'
    with np.load(row['state']['path']) as f:assert np.linalg.norm(f['port'])>1


def test_native_petsc_no_fill_complex_fixture(tmp_path):
    import os
    if os.environ.get('TASK042_ENV_MODE')!='fe':pytest.skip('native ILU fixture requires qualified FE activation')
    from src.solvers.fixed_p3_ilu0 import NativeILU0
    M=np.array([[4+1j,1,0,2],[2j,5-1j,1,0],[0,2,6+2j,1],[1,0,3j,7]],complex)
    pc=NativeILU0(csr_matrix(M),tmp_path/'view.txt')
    try:
        rng=np.random.default_rng(422000);r=rng.normal(size=4)+1j*rng.normal(size=4)
        np.testing.assert_allclose(pc.apply(r),no_fill_reference(M)(r),rtol=1e-13,atol=1e-14)
        assert pc.metadata['effective_Levels']==0 and pc.metadata['effective_ShiftType']==0
        assert 'matrix ordering: natural' in (tmp_path/'view.txt').read_text()
    finally:pc.destroy()


def test_independent_watchdog_deadline_clears_own_descendants(tmp_path):
    import sys,subprocess
    # PETSc/MPI can have helper children in the pytest process. The watchdog's
    # documented contract is a dedicated parent, so exercise an independent one.
    code='''import sys,json
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
r=supervise([sys.executable,'-c','import subprocess,time,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(20)"]); time.sleep(20)'],Path(sys.argv[1]),wall_seconds=1.,interval=.1,hard_stop_immediate=True,rss_hard_limit_bytes=2**30,rss_warning_bytes=2**29,include_pss=False,stop_on_global_swap=False)
print(json.dumps(r))
'''
    returned=subprocess.run([sys.executable,'-c',code,str(tmp_path/'deadline')],capture_output=True,text=True,check=True)
    result=json.loads(returned.stdout.splitlines()[-1])
    assert result['classification']!='COMPLETED' and result['descendants_cleared']
    assert len(result['observed_child_pids'])>=2 and not result['remaining_child_pids']


def isolate(tmp_path,monkeypatch):
    from src.solvers import fixed_p3_ilu0_window as w
    from src.io import fixed_p3_ilu0 as io
    for k,v in [('TMP',tmp_path),('WINDOW_PATH',tmp_path/'window.json'),('LEDGER_PATH',tmp_path/'ledger.json'),('JOURNAL_PATH',tmp_path/'journal.jsonl')]:monkeypatch.setattr(w,k,v)
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800))
    w.WINDOW_PATH.write_text('{}');monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'artifacts');io.ARTIFACT_ROOT.mkdir()
    return w,io


FILES=['capacity_setup','control_gpoly','ilu0_gpoly','ilu0_port_gpoly','transfer_gnn','zero_start','verify']


def test_seven_real_inputs_schema_stage_contract_reference_barrier(tmp_path,monkeypatch):
    w,io=isolate(tmp_path,monkeypatch)
    from src.io.task042_profile import TASK042_PROFILES
    from src.io.input_loader import InputError
    for label,name in zip(FILES,io.STAGES):
        spec=io.load_fixed_ilu0('input/task042_neural_coarse_inverse/v20_'+label+'.dat')
        assert spec.derived['stage']=='V20-'+name and spec.derived['environment_mode']=='fe'
        assert TASK042_PROFILES[spec.solver['preconditioner']]=='V20-'+name
        assert spec.execution['mpi_size']==1 and spec.execution['terminate_memory_gib']==16
    (io.ARTIFACT_ROOT/'FROZEN.json').write_text('{}')
    with pytest.raises(InputError,match='frozen'):io.load_fixed_ilu0('input/task042_neural_coarse_inverse/v20_zero_start.dat')
    assert io.load_fixed_ilu0('input/task042_neural_coarse_inverse/v20_verify.dat')


def test_dat_stage_pc_gmres_close_save_original_audit(tmp_path,monkeypatch):
    w,io=isolate(tmp_path,monkeypatch)
    from src.runners import orthonormal_trace_reprofile as old
    from src.runners.fixed_p3_ilu0 import ILUStage,execute_stage
    from src.solvers import fixed_p3_ilu0_study as study
    from src.runners.task042_shared import write_json
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    from src.solvers.stable_head_varpro import PortBlocks
    packet,bar,exact=small_problem(12)
    parent=atomic_arrays(io.ARTIFACT_ROOT/'old.npz',trace=exact[:12]*.3,port=exact[-40:]*.3,z=exact*.3,residual=packet.a['b']-packet.S@(exact*.3))
    plan=dict(initial_states={'GPOLY':dict(state=parent)},resident_upper_bytes=2**30)
    planpath=tmp_path/'plan.json';write_json(planpath,plan)
    # Parse the real dat first, then bind the bounded fixture identities.
    spec=io.load_fixed_ilu0('input/task042_neural_coarse_inverse/v20_ilu0_gpoly.dat')
    monkeypatch.setattr(io,'PLAN_PATH',planpath);monkeypatch.setattr(old,'original_packet',lambda fe:packet)
    monkeypatch.setattr(old,'own_sample',lambda d:dict(rss_bytes=1000))
    monkeypatch.setattr(study,'ports_for',lambda stage:PortBlocks(packet,packet.S[:,-40:]))
    K=csr_matrix(packet.S[:12,:12]);from scipy.sparse import save_npz
    save_npz(tmp_path/'K.npz',K)
    from src.solvers.neural_fe_action_packet import file_hash
    setup=dict(libraries={'GPOLY':dict(qualified=True,saved_residual_full_b_difference=0.)},PC_qualified=True,K=dict(path=str(tmp_path/'K.npz'),sha256=file_hash(tmp_path/'K.npz')))
    monkeypatch.setattr(io,'read_result',lambda name:(setup,None))
    class PC:
        metadata=dict(specification={'bounded_test':True});calls=0;seconds=0.
        def apply(self,x):self.calls+=1;return np.linalg.solve(K.toarray(),x)
        def destroy(self):pass
    monkeypatch.setattr(study,'make_body',lambda stage,K:PC())
    monkeypatch.setattr(study,'pc_qualification',lambda *a,**k:dict(qualified=True))
    stage_dir=tmp_path/'run';stage_dir.mkdir();(stage_dir/'source_sha.txt').write_text('a'*40)
    stage=ILUStage(spec,stage_dir);stage.own_plan.update(action_sha256='x',physical_sha256='y')
    result=execute_stage(stage)
    assert result['first_pass_cycle'] is not None and result['pc_kind']=='B0'
    with np.load(result['final']['state']['path']) as f:
        assert f['trace'].shape==(12,) and f['port'].shape==(40,) and f['z'].shape==(52,)
        np.testing.assert_allclose(f['z'],exact,rtol=1e-7,atol=1e-7)
