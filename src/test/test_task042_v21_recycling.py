"""Independent action oracle, GCROT boundary semantics and deadline mutations."""
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pytest
from src.test.test_neural_fe_action_packet import witness
from src.test.test_task042_v18_completion import small_problem
from src.solvers.neural_fe_action_packet import ActionPacket
from src.solvers.class_batch_action import ClassBatchAction
from src.solvers import gcrot_boundary as gc


@pytest.mark.parametrize('cells,unique',[(1,True),(65,False),(67,True),(130,False)])
def test_class_batch_exact_complex_interleaved_singletons_tail_and_readonly(cells,unique):
    original,*_=witness();a={key:np.array(v) for key,v in original.a.items()}
    rng=np.random.default_rng(422101)
    nc=cells;classes=np.arange(nc) if unique else np.arange(nc)%3
    a['S']=rng.normal(size=(max(classes)+1,2,2))+1j*rng.normal(size=(max(classes)+1,2,2))
    a['classes']=classes
    for key in ('tdofs','idofs','Bhat','Dhat'):a[key]=np.repeat(a[key],nc,axis=0)
    erows=np.concatenate([a['erows']+2*j for j in range(nc)])
    a['eids']=np.tile(a['eids'],nc);a['evals']=np.tile(a['evals'],nc);a['erows']=erows
    for key in ('erows','eids'):a[key]=np.r_[a[key],a[key][0]]
    a['evals']=np.r_[a['evals'],.4-.7j]
    old=ActionPacket(a);new=ClassBatchAction(old)
    x=rng.normal(size=old.size)+1j*rng.normal(size=old.size);x.setflags(write=False)
    y=(1+.3j)*x[::-1];before={k:v.copy() for k,v in old.a.items()}
    for adj in (False,True):
        np.testing.assert_allclose(new.apply(x,adjoint=adj),old.apply(x,adjoint=adj),rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(new.apply((.7+.2j)*x+(-.3+.9j)*y,adjoint=adj),
            (.7+.2j)*new.apply(x,adjoint=adj)+(-.3+.9j)*new.apply(y,adjoint=adj),rtol=1e-12,atol=1e-12)
    left=np.vdot(y,new.apply(x));right=np.vdot(new.apply(y,adjoint=True),x)
    assert abs(left-right)/(abs(left)+abs(right))<1e-12
    for key,v in old.a.items():np.testing.assert_array_equal(v,before[key]);assert not v.flags.writeable
    assert not hasattr(new,'audit') and new.metadata['persistent_cache_bytes']<=32*2**20
    with pytest.raises(ValueError,match='shape'):new.apply(x[:-1])
    with pytest.raises(ValueError,match='finite'):new.apply(x*np.nan)
    np.testing.assert_array_equal(new.apply(np.zeros_like(x)),np.zeros_like(x))


def four_calls(bar,rb,x,CU):
    rows=[]
    for _ in range(4):x,CU,row=gc.boundary_call(bar.apply,rb,x,CU,bar.packet.bnorm,m=3,k=2);rows.append(row)
    return x,CU,rows


def test_four_calls_vs_two_independent_disk_read_two_nonzero_forty_port(tmp_path):
    packet,bar,exact=small_problem(80);base=exact[:80]*.3
    rb=bar.reduced_rhs(packet.a['b'])-bar.apply(base)
    full,CU,rows=four_calls(bar,rb,np.zeros(80,complex),[])
    x=np.zeros(80,complex);partial=[]
    for j in range(2):x,partial,row=gc.boundary_call(bar.apply,rb,x,partial,packet.bnorm,m=3,k=2)
    assert rows[0]['info']==1 and rows[0]['returned_update']
    assert rows[0]['internal_length_at_entry']==5 and rows[0]['internal_Arnoldi_iterations'] is None
    assert len(CU)==3 and CU[-1][0] is None
    np.savez(tmp_path/'input.npz',S=packet.S,b=packet.a['b'],rb=rb,x=x,**gc.pack_CU(partial,80,k=2))
    code='''import sys,numpy as np
from pathlib import Path
from src.test.test_task042_v18_completion import SmallPacket
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.gcrot_boundary import boundary_call,pack_CU,unpack_CU
p=Path(sys.argv[1]);a=np.load(p/'input.npz');packet=SmallPacket(a['S'],a['b']);bar=BarAction(PortBlocks(packet,a['S'][:,-40:]));x=a['x'];CU=unpack_CU(a,len(x),k=2)
for j in range(2):x,CU,row=boundary_call(bar.apply,a['rb'],x,CU,packet.bnorm,m=3,k=2)
np.savez(p/'output.npz',x=x,**pack_CU(CU,len(x),k=2))
'''
    subprocess.run([sys.executable,'-c',code,str(tmp_path)],check=True)
    with np.load(tmp_path/'output.npz') as f:
        for key,v in dict(x=full,**gc.pack_CU(CU,80,k=2)).items():np.testing.assert_allclose(f[key],v,rtol=1e-12,atol=1e-12)
    z=bar.close(base+full,packet.a['b']);assert np.linalg.norm(z[-40:])>0
    check=gc.recycle_check(bar.apply,CU,k=2)
    assert json.loads(json.dumps(check,allow_nan=False))['qualified'] is True
    bad=[(c+1 if c is not None else None,u) for c,u in CU]
    assert not gc.recycle_check(bar.apply,bad,k=2)['qualified']


@pytest.mark.parametrize('where',['after_returned','before_close','after_closed','before_audit'])
def test_return_before_close_audit_failure_only_completes_no_Arnoldi_replay(tmp_path,monkeypatch,where):
    packet,bar,exact=small_problem(40);base=exact[:40]*.2;rhs=packet.a['b']
    rb=bar.reduced_rhs(rhs)-bar.apply(base);x=np.zeros(40,complex)
    def fault(boundary):
        if boundary==where:raise RuntimeError('injected '+where)
    with pytest.raises(RuntimeError,match='injected'):
        gc.boundary_commit(bar,bar,base,rb,x,[],rhs,tmp_path,{}, {},packet.audit,m=3,k=2,fault=fault)
    monkeypatch.setattr(gc,'boundary_call',lambda *a,**k:pytest.fail('returned solve replayed'))
    row=gc.boundary_commit(bar,bar,base,rb,x,[],rhs,tmp_path,{}, {},packet.audit,m=3,k=2)
    assert row['returned_boundary_resumed'] and row['committed'] and not row['audit_pending']
    with np.load(row['state']['path']) as f:
        np.testing.assert_array_equal(f['trace'],base+f['x'])
        assert f['port'].shape==(40,) and f['z'].shape==(80,)


def test_gcrot_mutation_failure_zero_rhs_no_update_and_nonfinite(monkeypatch):
    x=np.ones(20,complex);u=x/np.linalg.norm(x);c=2*u;CU=[(c,u),(None,x.copy())]
    before=gc.pack_CU(CU,20)
    def evil(*args,**kw):
        kw['x0'][:]=100;kw['CU'][0][0][:]=200;kw['CU'][0][1][:]=300;kw['CU'].clear()
        raise RuntimeError('failed mutated trial')
    with monkeypatch.context() as m:
        m.setattr(gc,'gcrotmk',evil)
        with pytest.raises(RuntimeError):gc.boundary_call(lambda t:2*t,x,x,CU,100.)
    np.testing.assert_array_equal(x,np.ones(20))
    for key,v in gc.pack_CU(CU,20).items():np.testing.assert_array_equal(v,before[key])
    answer,kept,row=gc.boundary_call(lambda t:2*t,np.zeros(20,complex),np.zeros(20,complex),[],100.)
    assert row['zero_correction_rhs'] and row['info']==0 and not row['returned_update']
    with pytest.raises(ValueError,match='finite'):gc.boundary_call(lambda t:t,x*np.nan,x,[],100.)
    with pytest.raises(ValueError,match=r'k\+1'):gc.pack_CU([(None,u)]*34,20)
    with monkeypatch.context() as m:
        m.setattr(gc,'gcrotmk',lambda *a,**kw:(kw['x0']*np.nan,1))
        with pytest.raises(ValueError,match='nonfinite returned'):gc.boundary_call(lambda t:t,x,x,[],100.)


def test_half_write_kill_bad_hash_rollback_and_None_roundtrip(tmp_path):
    store=gc.RecycleCheckpoint(tmp_path/'store',dict(operator='small'))
    old=dict(x=np.ones(20,complex),**gc.pack_CU([(None,np.ones(20,complex))],20))
    first=store.save(old,dict(phase='AUDITED'))
    code='''import sys,os,signal,numpy as np
from src.solvers.gcrot_boundary import RecycleCheckpoint,pack_CU
s=RecycleCheckpoint(sys.argv[1],dict(operator='small'))
s.save(dict(x=np.ones(20,complex)*2,**pack_CU([(None,np.ones(20,complex)*2)],20)),dict(phase='TRIAL'),interrupt_after='arrays_partial')
os.kill(os.getpid(),signal.SIGKILL)
'''
    p=subprocess.run([sys.executable,'-c',code,str(store.directory)]);assert p.returncode==-9
    assert store.read()[0]['generation']==first['generation']
    second=store.save(old,dict(phase='AUDITED'));Path(second['path']).write_bytes(b'bad hash')
    manifest,arrays,errors=store.read();assert manifest['generation']==first['generation']
    assert gc.unpack_CU(arrays,20)[0][0] is None
    with pytest.raises(ValueError,match='no legal'):gc.RecycleCheckpoint(store.directory,dict(operator='wrong')).read()


def test_deadline_crossboot_expiration_refuses_stage_and_test_launch(tmp_path,monkeypatch):
    from src.solvers import exact_recycle_window as w
    row=dict(start_utc='2026-10-02T00:00:00+00:00',start_monotonic=100.,boot_id='A',heavy_limit_seconds=12600,total_limit_seconds=14400)
    epoch=datetime.fromisoformat(row['start_utc']).timestamp()
    same=w.evaluate_window(row,utc_seconds=epoch+5,monotonic=120,boot_id='A');assert same['elapsed_seconds']==20
    other=w.evaluate_window(row,utc_seconds=epoch+15000,monotonic=1e9,boot_id='B');assert other['elapsed_seconds']==15000
    assert not other['monotonic_same_boot'] and other['total_remaining_seconds']==0
    monkeypatch.setattr(w,'snapshot',lambda:other)
    for heavy in (False,True):
        with pytest.raises(RuntimeError,match='no new test/stage'):w.require_live(heavy=heavy)
    from src.io import exact_action_recycling as io
    from src.io.input_loader import InputError
    with pytest.raises(InputError,match='deadline'):io.load_recycling('input/task042_neural_coarse_inverse/v21_gcrot_gpoly.dat')


def test_six_real_inputs_registration_and_reference_barrier(tmp_path,monkeypatch):
    from src.io import exact_action_recycling as io
    from src.io.task042_profile import TASK042_PROFILES
    from src.io.input_loader import InputError
    from src.solvers import exact_recycle_window as w
    monkeypatch.setattr(w,'require_live',lambda **k:dict(heavy_remaining_seconds=12000))
    monkeypatch.setattr(w,'LEDGER_PATH',tmp_path/'ledger.json')
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'artifacts');io.ARTIFACT_ROOT.mkdir()
    for name,label in io.FILES.items():
        spec=io.load_recycling(f'input/task042_neural_coarse_inverse/v21_{label}.dat')
        assert TASK042_PROFILES[spec.solver['preconditioner']]=='V21-'+name
        assert spec.execution['mpi_size']==1 and spec.execution['terminate_memory_gib']==16
        assert spec.derived['environment_mode']==('fe' if name=='VERIFY' else 'pure')
    (io.ARTIFACT_ROOT/'FROZEN.json').write_text('{}')
    with pytest.raises(InputError,match='frozen'):io.load_recycling('input/task042_neural_coarse_inverse/v21_gcrot_zero.dat')
    assert io.load_recycling('input/task042_neural_coarse_inverse/v21_verify.dat')


@pytest.mark.parametrize('name,label',[('C','gcrot_gpoly'),('B','lgmres_control')])
def test_real_dat_to_stage_gcrot_close_save_old_audit(tmp_path,monkeypatch,name,label):
    from src.io import exact_action_recycling as io
    from src.solvers import exact_recycle_window as w
    from src.solvers import exact_action_recycle_study as study
    from src.runners import orthonormal_trace_reprofile as old
    from src.runners.exact_action_recycling import RecycleStage
    from src.runners.task042_shared import write_json
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    for key,file in [('LEDGER_PATH','ledger.json'),('JOURNAL_PATH','journal.jsonl')]:monkeypatch.setattr(w,key,tmp_path/file)
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800))
    spec=io.load_recycling(f'input/task042_neural_coarse_inverse/v21_{label}.dat')
    packet,bar,exact=small_problem(12);packet.costs=dict(S=0.,SH=0.)
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'artifacts');io.ARTIFACT_ROOT.mkdir()
    parent=atomic_arrays(io.ARTIFACT_ROOT/'parent.npz',**close_point_for_test(bar,exact[:12]*.2,packet.a['b']))
    plan=dict(initial_states={'GPOLY':dict(state=parent)},action_sha256='a'*64,physical_sha256='b'*64)
    path=tmp_path/'plan.json';write_json(path,plan);monkeypatch.setattr(io,'PLAN_PATH',path)
    write_json(io.ARTIFACT_ROOT/'BACKEND_CHOICE.json',dict(selected_backend='OLD_ACTION',repeated_old_action_difference_full_b=0))
    monkeypatch.setattr(old,'original_packet',lambda fe:packet);monkeypatch.setattr(old,'own_sample',lambda d:dict(rss_bytes=1000,swap_bytes=0))
    monkeypatch.setattr(study,'ports_for',lambda stage:bar.ports)
    directory=tmp_path/'run';directory.mkdir();(directory/'source_sha.txt').write_text('c'*40)
    stage=RecycleStage(spec,directory);result=study.route(stage);stage.finish(result)
    stored,_=io.read_result(name);assert stored['first_pass_cycle']==1
    with np.load(stored['final']['state']['path']) as f:
        assert f['port'].shape==(40,) and f['z'].shape==(52,)
        np.testing.assert_allclose(f['z'],exact,rtol=1e-7,atol=1e-8)
    assert stored['Q_U_R_loaded'] is False and not stored['global_p3_incomplete_factor_constructed']


def close_point_for_test(bar,t,rhs):
    from src.solvers.gmres_cycle_commit import close_point
    return close_point(bar,t,rhs)[0]


def test_reader_counter_and_CU_contract_mutations():
    from copy import deepcopy
    from src.io.exact_recycle_check import limits,recycle_contract
    ledger=dict(active=None,closed=True,charged=dict(actions=1000,audits=5,field_states=2),
        reentries=0,cooldown_seconds=0,repairs=[],routes={'C':dict(actions=900,wall_seconds=100)})
    assert limits(ledger)
    for key,value in [('actions',100001),('audits',321),('field_states',13)]:
        bad=deepcopy(ledger);bad['charged'][key]=value;assert not limits(bad)
    assert not limits(dict(ledger,active={'pid':1}))
    assert not limits(dict(ledger,routes={'C':dict(actions=45001,wall_seconds=100)}))
    row=dict(m=256,k=32,maxiter=1,preconditioner=None,truncate='oldest',discard_C=False,
        relative_tolerance=0,internal_Arnoldi_iterations=None,CU_count=33,CU_none_indices=[32])
    assert recycle_contract(row)
    for key,value in [('m',128),('CU_count',34),('CU_none_indices',[33]),('preconditioner','ILU'),('internal_Arnoldi_iterations',256)]:
        assert not recycle_contract(dict(row,**{key:value}))


@pytest.mark.parametrize('legacy',[False,True])
def test_fixed_parent_reader_does_not_decode_legacy_iterates_or_directions(tmp_path,monkeypatch,legacy):
    from types import SimpleNamespace
    from src.solvers import exact_action_recycle_study as study
    from src.runners.orthonormal_trace_reprofile import atomic_arrays
    artifact=tmp_path/'artifacts';artifact.mkdir()
    trace=np.array([1+2j,3-.5j,2j]);port=np.arange(40,dtype=np.complex128)*(1+.2j)
    physical=dict(trace=trace,port=port,z=np.r_[trace,port],residual=np.ones(43,complex))
    state=atomic_arrays(artifact/'parent.npz',**physical,x=trace*77,
        outer_directions=np.tile(trace,(3,1)),CU_c=trace[None,:],CU_u=trace[None,:],CU_none=np.array([True]))
    stage=SimpleNamespace(io=SimpleNamespace(ARTIFACT_ROOT=artifact,ROOT=tmp_path),
        packet=SimpleNamespace(nt=3,size=43))
    original=np.load;decoded=[]
    class PhysicalOnly:
        def __enter__(self):
            self.opened=original(state['path'],allow_pickle=False)
            self.files=self.opened.files
            return self
        def __exit__(self,*args):self.opened.close()
        def __getitem__(self,key):
            if key not in physical:pytest.fail('forbidden legacy vector decoded: '+key)
            decoded.append(key);return self.opened[key]
    monkeypatch.setattr(study.np,'load',lambda *args,**kwargs:PhysicalOnly())
    loaded=study.load_state(stage,dict(state=state),legacy=legacy)
    assert set(decoded)==set(physical) and set(loaded)==set(physical)
    for key,value in physical.items():np.testing.assert_array_equal(loaded[key],value)
