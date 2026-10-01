"""Actual BarAction/40-port L boundaries, serialization, and real dat wiring."""
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest
from src.test.test_task042_v18_completion import SmallPacket,small_problem
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.gmres_cycle_commit import close_point
from src.solvers.lgmres_boundary import boundary_call,boundary_commit,BoundaryCheckpoint
from src.solvers.neural_fe_action_packet import array_hash,file_hash


def test_multiboundary_nonhermitian_forty_port_no_mutation_or_double_base(tmp_path):
    packet,bar,exact=small_problem(80);rhs=packet.a['b'];base=exact[:80]*.3
    rb=bar.reduced_rhs(rhs)-bar.apply(base);x=np.zeros(80,complex);directions=[];rows=[]
    for j in range(5):
        old_x=x.copy();old_dirs=[v.copy() for v,_ in directions]
        row=boundary_commit(bar,base,rb,x,directions,rhs,tmp_path/str(j),
            dict(operator='nonHermitian',library='GPOLY'),dict(cycle=j+1),packet.audit,inner_m=3)
        np.testing.assert_array_equal(x,old_x)
        for (v,_),old in zip(directions,old_dirs):np.testing.assert_array_equal(v,old)
        with np.load(row['state']['path']) as a:
            x=a['x'].copy();directions=[(v.copy(),None) for v in a['outer_directions']]
            np.testing.assert_array_equal(a['trace'],base+x)
            assert a['port'].shape==(40,) and a['z'].shape==(120,)
        assert row['fixed_correction_identity_relative']<1e-13
        assert row['inner']['internal_Arnoldi_iterations'] is None
        assert row['inner']['actual_bar_actions']<=3+3+1
        assert row['direction_inventory']['count']==min(j+1,3)
        rows.append(row)
    assert rows[0]['inner']['info']==1 and rows[0]['inner']['returned_update']
    assert rows[-1]['original_equation_gate']['rho']<rows[0]['original_equation_gate']['rho']
    with pytest.raises(ValueError,match='correction RHS'):
        boundary_commit(bar,base,rb+rhs[:80],np.zeros(80,complex),[],rhs,tmp_path/'mixed',{}, {},packet.audit,inner_m=3)
    with pytest.raises(ValueError,match='identity'):
        boundary_commit(bar,base*2,rb,old_x,[(v,None) for v in old_dirs],rhs,tmp_path/'4',
            dict(operator='nonHermitian',library='GPOLY'),{},packet.audit,inner_m=3)


@pytest.mark.parametrize('where',['after_proposed','before_close','after_closed','before_audit','after_audit'])
def test_return_saved_before_close_audit_and_no_replay(tmp_path,monkeypatch,where):
    from src.solvers import lgmres_boundary as adapter
    packet,bar,_=small_problem(40);base=np.ones(40,complex)*(1+.3j);rhs=packet.a['b']
    rb=bar.reduced_rhs(rhs)-bar.apply(base);x=np.zeros(40,complex)
    def fault(boundary):
        if boundary==where:raise RuntimeError('injected '+where)
    with pytest.raises(RuntimeError,match='injected'):
        boundary_commit(bar,base,rb,x,[],rhs,tmp_path,{}, {},packet.audit,inner_m=3,fault=fault)
    def forbidden(*a,**kw):raise AssertionError('returned L call replayed')
    monkeypatch.setattr(adapter,'boundary_call',forbidden)
    row=boundary_commit(bar,base,rb,x,[],rhs,tmp_path,{}, {},packet.audit,inner_m=3)
    assert row['returned_boundary_resumed'] and row['committed'] and not row['audit_pending']


def test_mutating_failure_zero_rhs_no_update_and_nonfinite(tmp_path,monkeypatch):
    from src.solvers import lgmres_boundary as adapter
    x=np.ones(20,complex);v=np.ones(20,complex)/np.sqrt(20);directions=[(v,None)]
    def evil(*args,**kwargs):
        kwargs['x0'][:]=100;kwargs['outer_v'][0][0][:]=200;kwargs['outer_v'].clear()
        raise RuntimeError('failed trial')
    with monkeypatch.context() as m:
        m.setattr(adapter,'lgmres',evil)
        with pytest.raises(RuntimeError):boundary_call(lambda t:2*t,x,x,directions,100.,inner_m=3)
    np.testing.assert_array_equal(x,np.ones(20));np.testing.assert_array_equal(v,np.ones(20)/np.sqrt(20))
    value,kept,row=boundary_call(lambda t:2*t,np.zeros(20,complex),np.zeros(20,complex),[],100.,inner_m=3)
    assert row['zero_correction_rhs'] and row['info']==0 and not row['returned_update'] and not kept
    with pytest.raises(ValueError,match='finite'):boundary_call(lambda t:t,x*np.nan,x,[],100.)
    with pytest.raises(ValueError,match='Av'):boundary_call(lambda t:t,x,x,[(v,v)],100.)
    with pytest.raises(ValueError,match='capacity'):boundary_call(lambda t:t,x,x,[(v,None)]*4,100.)


def test_independent_reader_next_boundary_and_wrong_library_operator_parent(tmp_path):
    packet,bar,_=small_problem(60);rhs=packet.a['b'];base=np.ones(60,complex)*.1
    rb=bar.reduced_rhs(rhs)-bar.apply(base);identity=dict(operator='small',library='GNN',parent_hash='a'*64)
    first=boundary_commit(bar,base,rb,np.zeros(60,complex),[],rhs,tmp_path/'first',identity,{},packet.audit,inner_m=3)
    with np.load(first['state']['path']) as a:x=a['x'].copy();dirs=[(v.copy(),None) for v in a['outer_directions']]
    second=boundary_commit(bar,base,rb,x,dirs,rhs,tmp_path/'whole',identity,{},packet.audit,inner_m=3)
    np.savez(tmp_path/'problem.npz',S=packet.S,rhs=rhs,base=base,rb=rb,x=x,dirs=np.stack([v for v,_ in dirs]))
    code='''import sys,json,numpy as np
from pathlib import Path
from src.test.test_task042_v18_completion import SmallPacket
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.lgmres_boundary import boundary_commit
p=Path(sys.argv[1]);a=np.load(p/'problem.npz');pkt=SmallPacket(a['S'],a['rhs']);bar=BarAction(PortBlocks(pkt,a['S'][:,-40:]))
boundary_commit(bar,a['base'],a['rb'],a['x'],[(v,None) for v in a['dirs']],a['rhs'],p/'reader',dict(operator='small',library='GNN',parent_hash='a'*64),{},pkt.audit,inner_m=3)
'''
    subprocess.run([sys.executable,'-c',code,str(tmp_path)],check=True)
    reader=json.loads((tmp_path/'reader/commit.json').read_text())
    with np.load(second['state']['path']) as a,np.load(reader['state']['path']) as b:
        for k in a.files:np.testing.assert_array_equal(a[k],b[k])
    for key,value in [('operator','wrong'),('library','GPOLY'),('parent_hash','b'*64)]:
        with pytest.raises(ValueError,match='identity'):
            boundary_commit(bar,base,rb,x,dirs,rhs,tmp_path/'whole',dict(identity,**{key:value}),{},packet.audit,inner_m=3)


def test_atomic_half_write_kill_hash_and_rollback(tmp_path):
    store=BoundaryCheckpoint(tmp_path/'store',dict(identity='known'))
    first=store.save(dict(x=np.ones(20,complex)),dict(phase='COMMITTED'))
    code='''import sys,os,signal,numpy as np
from src.solvers.lgmres_boundary import BoundaryCheckpoint
s=BoundaryCheckpoint(sys.argv[1],dict(identity='known'))
s.save(dict(x=np.ones(20,complex)*2),dict(phase='TRIAL'),interrupt_after='arrays_partial')
os.kill(os.getpid(),signal.SIGKILL)
'''
    result=subprocess.run([sys.executable,'-c',code,str(store.directory)])
    assert result.returncode==-9 and store.read()[0]['generation']==first['generation']
    second=store.save(dict(x=np.ones(20,complex)*3),dict(phase='COMMITTED'))
    Path(second['path']).write_bytes(b'bad hash')
    assert store.read()[0]['generation']==first['generation']


def isolate_window(tmp_path,monkeypatch):
    from src.solvers import post_lsqr_window as w
    for name,file in [('WINDOW_PATH','window.json'),('BUDGET_PATH','budget.json'),('LEDGER_PATH','ledger.json'),('JOURNAL_PATH','journal.jsonl')]:monkeypatch.setattr(w,name,tmp_path/file)
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=12000,total_remaining_seconds=13800))
    w.WINDOW_PATH.write_text('{}');w.freeze_route_budget();return w


FILES=['preflight','g256_gpoly','g256_gnn','lgmres_gpoly','lgmres_gnn','verify']


def test_six_real_dat_schema_stage_budget_and_reference_barrier(tmp_path,monkeypatch):
    from src.io import post_lsqr_polish as io
    from src.io.task042_profile import TASK042_PROFILES
    from src.io.input_loader import InputError
    w=isolate_window(tmp_path,monkeypatch);monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'artifacts')
    specs=[io.load_post_lsqr('input/task042_neural_coarse_inverse/v19_post_lsqr_'+f+'.dat') for f in FILES]
    for spec,route in zip(specs,[('C0',None),('P','GPOLY'),('P','GNN'),('L','GPOLY'),('L','GNN'),('V',None)]):
        assert (spec.derived['algorithm'],spec.derived['library'])==route
        assert TASK042_PROFILES[spec.solver['preconditioner']]==spec.derived['stage']
        assert spec.execution['mpi_size']==1 and spec.execution['terminate_memory_gib']==16
    before=w.freeze_route_budget();assert before['uniform_route_wall_seconds']==2700
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=30000))
    assert w.freeze_route_budget()==before
    wrong=tmp_path/'wrong.dat';wrong.write_text(Path('input/task042_neural_coarse_inverse/v19_post_lsqr_lgmres_gnn.dat').read_text().replace('library = "GNN"','library = "GPOLY"'))
    with pytest.raises(InputError,match='differs'):io.load_post_lsqr(wrong)
    io.ARTIFACT_ROOT.mkdir();(io.ARTIFACT_ROOT/'FROZEN.json').write_text('{}')
    with pytest.raises(InputError,match='frozen'):io.load_post_lsqr('input/task042_neural_coarse_inverse/v19_post_lsqr_lgmres_gnn.dat')
    assert io.load_post_lsqr('input/task042_neural_coarse_inverse/v19_post_lsqr_verify.dat')


@pytest.mark.parametrize('algorithm',['P','L'])
def test_actual_dat_stage_algorithm_full_save_original_audit(tmp_path,monkeypatch,algorithm):
    from src.io import post_lsqr_polish as io
    from src.runners import orthonormal_trace_reprofile as original_adapter
    from src.runners.gmres_residual_completion import CompletionStage
    from src.runners.post_lsqr_polish import execute_stage
    from src.solvers import post_lsqr_polish as core
    w=isolate_window(tmp_path,monkeypatch)
    spec=io.load_post_lsqr('input/task042_neural_coarse_inverse/v19_post_lsqr_'+('g256_gpoly' if algorithm=='P' else 'lgmres_gpoly')+'.dat')
    packet,bar,_=small_problem();t=np.ones(packet.nt,complex)*(1+.3j)
    arrays,_=close_point(bar,t,packet.a['b']);old=tmp_path/'benchmarks/artifacts/task042/v18';old.mkdir(parents=True)
    np.savez(old/'start.npz',**arrays)
    state=dict(path=str(old/'start.npz'),sha256=file_hash(old/'start.npz'),z_sha256=array_hash(arrays['z']))
    own=json.loads(io.PLAN_PATH.read_text());own['initial_states']['GPOLY']['state']=state
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(own))
    monkeypatch.setattr(io,'ROOT',tmp_path);monkeypatch.setattr(io,'PLAN_PATH',plan);monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path/'benchmarks/artifacts/task042/v19')
    monkeypatch.setattr(original_adapter,'original_packet',lambda fe:packet)
    monkeypatch.setattr(CompletionStage,'sample',lambda self:dict(rss_bytes=1000000,swap_bytes=0))
    monkeypatch.setattr(core,'ports_for',lambda stage:bar.ports)
    pre=dict(libraries={'GPOLY':dict(qualified=True,original_equation_gate=dict(rho=1,status='ORIGINAL_EQUATION_FAILED'),repeated_action_full_b_difference=0)})
    read=io.read_result;monkeypatch.setattr(io,'read_result',lambda name:(pre,None) if name=='PREFLIGHT' else read(name))
    if algorithm=='L':
        p8=io.ARTIFACT_ROOT/'P_GPOLY/cycles/CYCLE_0008';p8.mkdir(parents=True)
        (p8/'commit.json').write_text(json.dumps(dict(original_equation_gate=dict(status='ORIGINAL_EQUATION_FAILED'))))
    directory=tmp_path/'chain';directory.mkdir();(directory/'source_sha.txt').write_text('a'*40)
    stage=CompletionStage(spec,directory,io_module=io,window_module=w,batch='V19')
    result=execute_stage(stage);stage.finish(result);stored,_=read(algorithm+'_GPOLY')
    assert stored['status']=='ORIGINAL_EQUATION_PASS'
    with np.load(stored['final']['state']['path']) as a:
        assert a['port'].shape==(40,) and a['z'].shape==(packet.nt+40,)
        assert packet.audit(a['z'])['schur_relative']<1e-6
    assert w.ledger()['active']['algorithm']==algorithm and stored['Q_U_R_loaded'] is False


def test_per_method_library_kill_conservative_action_accounting(tmp_path,monkeypatch):
    w=isolate_window(tmp_path,monkeypatch)
    summary=dict(stage='V19-L_GNN',classification='RESOURCE_CONTROLLED_STOP',leader_exit_code=-9,descendants_cleared=True,
        sampled_process_tree_rss_peak_bytes=100,sampled_process_tree_swap_peak_bytes=0)
    row=w.settle_run('failed_before_loader',summary,30.)
    assert row['routes']['L_GNN']['actions_upper']==320 and row['routes']['P_GNN']['actions_upper']==0
    assert row['actions_upper']==320 and row['runs'][-1]['internal_Arnoldi_iterations'] is None
