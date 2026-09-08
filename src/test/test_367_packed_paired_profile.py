"""V2 shared-setup schedule, raw comparison, and independent budget contracts."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.io.physical_intermediate_profile import PACKED_PROFILE
from src.runners.physical_pc_profile import paired_schedule


def test_packed_dat_and_schedule():
    from src.io import load_and_resolve
    from src.io.physical_intermediate_profile import FAST_PROFILE, profile_facts
    old = load_and_resolve('input/task39extra/original_13p5nm_p6h10_a2r_equivalent_fast.dat')
    new = load_and_resolve('input/task39extra/original_13p5nm_p6h10_a2r_packed_equivalent_v2.dat')
    assert old.input_sha256 != new.input_sha256
    assert old.physical_model_sha256 == new.physical_model_sha256
    assert new.solver['preconditioner'] == PACKED_PROFILE
    assert 'contiguous' not in profile_facts(FAST_PROFILE)['backend']['B6']
    for available, count in [(True,14),(False,10)]:
        s=paired_schedule(available)
        assert len(s)==count and sum(w for _,w,_ in s)==2
        assert {n for n,_,_ in s} == ({'physical_rhs','random_complex','checkpoint576_residual'} if available else {'physical_rhs','random_complex'})
        assert all(s[i][:2]==s[i+1][:2] and s[i][2]=='original' and s[i+1][2]=='packed' for i in range(0,count,2))


def test_v2_budget_is_separate_once_and_grace_inside_2400(tmp_path, monkeypatch):
    from src.io import load_and_resolve
    from src.io.input_loader import InputError
    from src.runners import physical_profile_budget as budget, task038_launcher
    monkeypatch.setattr(budget,'verified_checkpoint',lambda *a,**kw: (_ for _ in ()).throw(FileNotFoundError()))
    seen=[]
    def launch(spec, *, pc_profile):
        seen.append(pc_profile)
        assert pc_profile['complete_pc_limit']==14 and pc_profile['random_seed']==3902
        assert pc_profile['performance_grace_included_seconds']==60
        assert pc_profile['batch_limit_seconds']==2400 and not pc_profile['checkpoint_available']
        return dict(result_classification='worker_exit0',run_directory='fake')
    monkeypatch.setattr(task038_launcher,'launch_specification',launch)
    spec=load_and_resolve('input/task39extra/original_13p5nm_p6h10_a2r_packed_equivalent_v2.dat')
    p=tmp_path/'budget.json'
    p.write_text(json.dumps(dict(schema='task39extra.review-v1-compute-budget.v1',limit_seconds=36000,attempts=[])))
    with pytest.raises(InputError,match='separate V2'):budget.launch_profile(spec,tmp_path,p,variant=PACKED_PROFILE)
    p.unlink()
    budget.launch_profile(spec,tmp_path,p,variant=PACKED_PROFILE)
    b=json.loads(p.read_text());assert b['attempts'][0]['reserved_seconds']==2400
    with pytest.raises(InputError,match='already reserved'):budget.launch_profile(spec,tmp_path,p,variant=PACKED_PROFILE)
    assert len(seen)==1


@pytest.mark.parametrize('bad', [None,'S6','action','hash','ownership','p4','schedule','repeat_raw'])
def test_paired_checker_recomputes_raw(tmp_path,bad):
    from src.runners.physical_pc_comparison import compare_paired_profile
    p=tmp_path/'pc_profile';p.mkdir()
    state=dict(config=dict(variant=PACKED_PROFILE,checkpoint_available=True),completed=14,active_apply=None,captures=[],same_input_checks=[])
    def save(name, value=1.):
        path=p/name;path.parent.mkdir(exist_ok=True)
        np.save(path,np.array([value,2j],dtype=np.complex128))
        item=dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),shape=[2],ownership_range=[0,2]);state['captures'].append(item);return item
    for n in ['physical_rhs','checkpoint576_residual','random_complex']:
        for role in ['B6','curl','material_mass','A6']:
            c=dict(name=n+'_'+role)
            for label in ['original','fast']:c[label]=save('same_input_'+c['name']+'_'+label+'.npy',2. if bad=='action' and label=='fast' else 1.)
            state['same_input_checks'].append(c)
    rows=[];pcs=[]
    for i,(n,w,backend) in enumerate(paired_schedule(),1):
        for role in ['S6_01.npy','S6_02.npy','PC_output.npy','PC_A6_output.npy',*(f'A6_{j:02d}.npy' for j in range(1,5))]:
            # Hash remains valid and the worker falsely reports repeat passed.
            changed = (bad=='S6' and i==2 and role=='S6_01.npy') or (bad=='repeat_raw' and i==5 and role=='A6_02.npy')
            save(f'apply_{i:02d}/'+role,2. if changed else 1.)
        row=dict(index=i,input=n,warmup=w,backend=backend,input_unchanged=True,output_finite=True,output_slave_zero=True,
            timing_delta={'PC':dict(inclusive_seconds=2. if backend=='original' else 1.)})
        if i in [5,6,9,10,13,14]:row['repeat_comparison']={'array':{'passed':True}}
        rows.append(row);pcs.append(dict(intermediate=dict(factor_solve_calls=1,explicit_action_count=1,rhs_norm=1.,true_residual_norm=1e-3 if bad=='p4' else 1e-12)))
    if bad=='schedule':rows[0]['backend']='packed'
    if bad=='hash':state['captures'][0]['sha256']='0'*64
    if bad=='ownership':state['captures'][0]['ownership_range']=[1,3]
    (p/'state.json').write_text(json.dumps(state))
    for name,records in [('profile_applies.jsonl',rows),('pc_applies.jsonl',pcs)]:
        (tmp_path/name).write_text(''.join(json.dumps(r)+'\n' for r in records))
    if bad in ['hash','ownership','p4','schedule','repeat_raw']:
        with pytest.raises(ValueError):compare_paired_profile(tmp_path)
    else:
        r=compare_paired_profile(tmp_path)
        assert r['passed'] is (bad is None)
        assert r['speed_gate_passed'] is (bad is None)
        assert r['ratio']==.5


def test_timing_only_instruments_selected_physical_backend():
    from src.solvers.physical_pc_timing import instrument_reference_pc
    def obj(**kw):return SimpleNamespace(**kw)
    old_b6=obj(_mpc=object(),_local_kernel=None)
    new_b6=obj(_mpc=object(),_local_kernel=obj())
    fine=obj(); fast=obj()
    p=dict(p6_shell=obj(action=old_b6),upper_cycle=obj(p63_transfer=obj()),
        lower_cycle=obj(fine_matrix=obj(),coarse_matrix=obj(),coarse_solver=obj(),smoother=obj(),owner_transfer=obj()))
    bundle=dict(positive=p,pc=obj(fine_action=fine),actions={'transfers':{(6,4):obj()}},
        reference_factor=obj(factor=obj(),action=obj()),fine=dict(physical_action=fine,volume_action=obj(),dtn_action=obj()),
        equivalent_fast=dict(physical_action=fast,volume_action=obj(component_actions={}),b6=new_b6))
    class Timer:
        def __init__(self):self.wrapped=[]
        def wrap(self,owner,*args,**kw):self.wrapped.append(owner)
        def replace(self,*args):pass
    for selected in [False,True,False]:
        bundle['pc'].fine_action=fast if selected else fine
        p['p6_shell'].action=new_b6 if selected else old_b6
        timer=Timer();instrument_reference_pc(bundle,timer,lambda *a:None)
        assert any(o is fast for o in timer.wrapped) is selected


def test_speed_gate_uses_median_of_paired_ratios(tmp_path):
    from src.runners.physical_pc_comparison import compare_paired_profile
    test_paired_checker_recomputes_raw(tmp_path,None)
    path=tmp_path/'profile_applies.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    for i,(old,new) in enumerate(zip([1,10,100,1,10,100],[.1,9,10,.1,9,10],strict=True)):
        rows[2+2*i]['timing_delta']['PC']['inclusive_seconds']=old
        rows[3+2*i]['timing_delta']['PC']['inclusive_seconds']=new
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=compare_paired_profile(tmp_path)
    assert result['ratio']==pytest.approx(.1)
    assert result['ratio_of_medians_diagnostic']==pytest.approx(.9)
    assert result['speed_gate_passed']


def test_paired_parent_manifest_and_worker_cooperative_registration(tmp_path,monkeypatch):
    import time
    from src.io import load_and_resolve
    from src.runners import task038_launcher as launcher
    from src.runners.physical_intermediate import WorkflowLedger
    from src.runners.physical_pc_profile import PACKED_CHECKPOINT_SOLUTION_SHA
    from benchmarks import subreaper_watchdog
    spec=load_and_resolve('input/task39extra/original_13p5nm_p6h10_a2r_packed_equivalent_v2.dat')
    run=tmp_path/'run';run.mkdir()
    monkeypatch.setattr(launcher,'_timestamp_directory',lambda *a:run)
    monkeypatch.setattr(launcher,'_physical_source_gate',lambda *a:{'source_sha':'a'*40})
    def supervise(*a,**kw):
        config=json.loads(kw['worker_environment']['PHYSICAL_PC_PROFILE'])
        assert config['schedule']==[list(r) for r in paired_schedule()]
        assert config['checkpoint_solution_sha256']==PACKED_CHECKPOINT_SOLUTION_SHA
        assert kw['cooperative_performance_stop'] and kw['hard_stop_immediate']
        assert kw['grace_seconds']==60 and 2330<kw['wall_seconds']<=2340
        assert kw['solve_seconds'] is None
        assert not list(Path(config['cache_home']).iterdir())
        ledger=WorkflowLedger(run,run/'workflow_phase.json',cooperative_performance_stop=True)
        ledger.defer_performance_stop=True;ledger.set_phase('profile');ledger.stop_signal=15
        ledger.marker('pc_safe_progress',{})
        assert json.loads((run/'workflow_phase.json').read_text())['application_worker']==ledger.application_worker
        ledger.phase='setup'
        with pytest.raises(InterruptedError):ledger.marker('setup_stop',{})
        return dict(leader_exit_code=0,classification='COMPLETED',launch_envelope={},memory_scope='test',job_swap_activity='zero_supported_by_zero_global_activity')
    monkeypatch.setattr(subreaper_watchdog,'supervise',supervise)
    launcher.launch_specification(spec,source_sha='a'*40,pc_profile=dict(
        variant=PACKED_PROFILE,complete_pc_limit=14,batch_limit_seconds=2400,
        deadline_monotonic=time.monotonic()+2340,checkpoint_available=True,checkpoint=str(tmp_path)))
