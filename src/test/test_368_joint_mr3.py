"""One bounded algebra batch for frozen three-direction joint acceptance."""
from types import SimpleNamespace
import tracemalloc

import numpy as np
import pytest

from src.solvers.physical_joint_mr import JointMR3, CUTOFF, MAX_BYTES
from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner


@pytest.mark.parametrize('case',['complex','rank1','rank2','near','zero_columns','zero_rhs','scales','short'])
def test_normalized_QR_small_SVD_matches_three_column_reference(case):
    rng=np.random.default_rng(3903);n=2 if case=='short' else 11
    w=rng.normal(size=(n,3))+1j*rng.normal(size=(n,3))
    q=rng.normal(size=n)+1j*rng.normal(size=n)
    if case=='rank1':w[:,1]=2j*w[:,0];w[:,2]=-3*w[:,0]
    if case=='rank2':w[:,2]=w[:,0]+.3j*w[:,1]
    if case=='near':w[:,2]=w[:,0]+.3j*w[:,1]+1e-14*w[:,2]
    if case=='zero_columns':w[:]=0
    if case=='zero_rhs':q[:]=0
    if case=='scales':w[:,0]*=1e120;w[:,1]*=1e-120
    original=q.copy();work=JointMR3(q)
    for i in range(3):work.capture(w[:,i],w[:,i])
    candidate,facts=work.candidate(q)
    if np.any(w):
        from scipy.linalg import norm
        scaled=w/np.array([norm(w[:,i]) for i in range(3)])
        expected=scaled@np.linalg.lstsq(scaled,q,rcond=CUTOFF)[0]
        np.testing.assert_allclose(candidate,expected,atol=1e-11,rtol=1e-11)
        assert facts['QR_shares_W'] and facts['Q_shares_QR']
    else:np.testing.assert_array_equal(candidate,np.zeros_like(q))
    if case=='rank1':assert facts['rank']==1
    if case in ('rank2','near','short'):assert facts['rank']==2
    np.testing.assert_array_equal(q,original)
    assert facts['workspace_bound_bytes']<=MAX_BYTES
    work.close();assert work.d is None and work.w is None


def make_pc(joint, *, fourth_nonfinite=False):
    class AlgebraSolution(np.ndarray):
        def destroy(self):
            pass  # NumPy-owned fixture, matching the reference solution protocol.
    rng=np.random.default_rng(137)
    a=np.diag(np.linspace(1,4,12)).astype(complex)+.2*(rng.normal(size=(12,12))+1j*rng.normal(size=(12,12)))
    selected=np.array([1,4,8]);h=np.linspace(.15,.7,12)
    observed={'a':[],'h':[],'p4':[]}
    def action(x,y):
        observed['a'].append(x.copy());y[:]=a@x
        if fourth_nonfinite and len(observed['a'])==4:y[0]=np.nan
    def positive(x,y):observed['h'].append(x.copy());y[:]=h*x
    def primal(x):
        y=np.zeros(12,dtype=complex);y[selected]=x;return y
    def solve(x):
        observed['p4'].append(x.copy())
        return dict(final_solution=np.linalg.solve(a[np.ix_(selected,selected)],x).view(AlgebraSolution),diagnostic_only=True,
            factor_solve_calls=1,explicit_action_count=1)
    pc=PhysicalIntermediatePreconditioner(SimpleNamespace(apply=action),SimpleNamespace(apply=positive),
        SimpleNamespace(apply_adjoint=lambda x:x[selected].copy(),apply_primal=primal),
        SimpleNamespace(solver_identity='exact_augmented_A4_reference',solve_intermediate=solve),
        positive_identity='H6',outer_max_it=2048,joint_mr=joint)
    return pc,a,observed


def test_joint_keeps_old_direction_generation_and_uses_only_one_extra_action():
    q=np.arange(12,dtype=complex)+1+2j;before=q.copy()
    old,a,old_calls=make_pc(False);seq=old.apply(q)
    new,_,new_calls=make_pc(True);joint=new.apply(q)
    for key in ('h','p4'):
        for x,y in zip(old_calls[key],new_calls[key],strict=True):np.testing.assert_array_equal(x,y)
    for x,y in zip(old_calls['a'],new_calls['a'][:3],strict=True):np.testing.assert_array_equal(x,y)
    assert len(new_calls['a'])==4 and len(new_calls['h'])==2 and len(new_calls['p4'])==1
    assert np.linalg.norm(q-a@joint)<=np.linalg.norm(q-a@seq)+1e-10*np.linalg.norm(q)
    assert new.last_apply_facts['joint_mr3']['extra_A6_count']==1
    np.testing.assert_array_equal(q,before)


def test_explicit_safeguard_returns_stored_sequential_without_regeneration(monkeypatch):
    original=JointMR3.candidate
    def bad(self,q):
        _,facts=original(self,q);return np.full(q.shape,100+30j),facts
    q=np.arange(12,dtype=complex)+1j
    old,_,_=make_pc(False);seq=old.apply(q)
    monkeypatch.setattr(JointMR3,'candidate',bad)
    new,_,calls=make_pc(True);result=new.apply(q)
    np.testing.assert_array_equal(result,seq)
    facts=new.last_apply_facts['joint_mr3']
    assert facts['fallback_reason']=='explicit_joint_residual_safeguard'
    assert len(calls['h'])==2 and len(calls['p4'])==1 and len(calls['a'])==4


def test_small_svd_failure_falls_back_but_physical_nonfinite_propagates(monkeypatch):
    q=np.arange(12,dtype=complex)+1j
    bad,_,_=make_pc(True,fourth_nonfinite=True)
    with pytest.raises(RuntimeError,match='non-finite'):bad.apply(q)
    old,_,_=make_pc(False);seq=old.apply(q)
    def fail(*a,**kw):raise np.linalg.LinAlgError('tiny injected SVD failure')
    monkeypatch.setattr(np.linalg,'svd',fail)
    new,_,calls=make_pc(True);result=new.apply(q)
    np.testing.assert_array_equal(result,seq)
    assert new.last_apply_facts['joint_mr3']['fallback_reason']=='small_SVD_failed'
    assert len(calls['a'])==3 and len(calls['p4'])==1


def test_zero_and_nonfinite_input_and_workspace_lifetime():
    pc,_,calls=make_pc(True)
    q=np.zeros(12,dtype=complex);np.testing.assert_array_equal(pc.apply(q),q)
    assert not calls['a'] and not calls['h'] and not calls['p4']
    q[0]=np.nan
    with pytest.raises((ValueError,RuntimeError)):pc.apply(q)
    rng=np.random.default_rng(5);q=rng.normal(size=4096).astype(complex);w=rng.normal(size=(4096,3)).astype(complex)
    tracemalloc.start()
    work=JointMR3(q)
    for i in range(3):work.capture(w[:,i],w[:,i])
    _,facts=work.candidate(q)
    peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
    assert peak<facts['workspace_bound_bytes']
    assert 16*173802*16+65536<MAX_BYTES
    work.close()


def test_joint_dat_budget_and_cooperative_public_launcher(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from src.io import load_and_resolve
    from src.io.input_loader import InputError
    from src.io.physical_intermediate_profile import JOINT_PROFILE, profile_facts
    from src.runners import physical_profile_budget as budget,task038_launcher as launcher
    from benchmarks import subreaper_watchdog
    old=load_and_resolve('input/task39extra/original_13p5nm_p6h10_p6smooth_p4ref_p6smooth.dat')
    spec=load_and_resolve('input/task39extra/original_13p5nm_p6h10_light_p4ref_jointmr3_v2.dat')
    assert spec.input_sha256!=old.input_sha256 and spec.physical_model_sha256==old.physical_model_sha256
    facts=profile_facts(JOINT_PROFILE)
    assert facts['outer']['max_iterations']==2048 and facts['outer']['safe_snapshot_interval']==8
    assert facts['backend']['A6']=='original_split_form'
    path=tmp_path/'budget.json'
    previous=dict(kind='F1_paired_profile',elapsed_seconds=1096.5587070849724,status='worker_exit0')
    path.write_text(json.dumps(dict(schema='task39extra.review-v2-compute-budget.v1',limit_seconds=36000,attempts=[previous])))
    run=tmp_path/'run';run.mkdir()
    monkeypatch.setattr(launcher,'_timestamp_directory',lambda *a:run)
    monkeypatch.setattr(launcher,'_source_sha',lambda *a:'a'*40)
    monkeypatch.setattr(launcher,'_physical_source_gate',lambda *a:{'source_sha':'a'*40})
    def supervise(*a,**kw):
        reserved=json.loads(path.read_text())['attempts'][-1]
        assert reserved['kind']=='F3_full_workflow' and reserved['reserved_seconds']==10800
        assert kw['cooperative_performance_stop'] and kw['grace_seconds']==60 and kw['hard_stop_immediate']
        assert 10730<kw['wall_seconds']<=10740 and kw['solve_seconds']==7200
        assert set(kw['worker_environment'])=={'XDG_CACHE_HOME'}
        assert not list(Path(kw['worker_environment']['XDG_CACHE_HOME']).iterdir())
        return dict(leader_exit_code=0,classification='COMPLETED',launch_envelope={},memory_scope='test',job_swap_activity='zero_supported_by_zero_global_activity')
    monkeypatch.setattr(subreaper_watchdog,'supervise',supervise)
    budget.launch_light_workflow(spec,path)
    assert json.loads(path.read_text())['attempts'][0]==previous
    with pytest.raises(InputError,match='already reserved'):budget.launch_light_workflow(spec,path)
