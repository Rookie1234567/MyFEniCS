"""Small G2 dispatch/lifecycle/evidence fixtures, no FE assembly."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.io import load_and_resolve
from src.io.physical_recursive_profile import RECURSIVE_LO, RECURSIVE_HI, RECURSIVE_PROFILES
from src.io.physical_intermediate_profile import profile_facts


def spec(identity=RECURSIVE_LO,model='original'):
    return load_and_resolve(Path('input/task39extra')/f'{model}_13p5nm_p6h10_{identity}.dat')


@pytest.mark.parametrize('identity',RECURSIVE_PROFILES)
def test_profiles_preserve_physics_and_old_contract(identity):
    current=spec(identity);old=spec('balanced_h6_p4_v5')
    assert current.physical_model_sha256==old.physical_model_sha256
    assert spec(identity,'nonseparable').physical_model_sha256==spec('balanced_h6_p4_v5','nonseparable').physical_model_sha256
    p=current.as_jsonable()['derived']['physical_intermediate_profile']
    assert p==profile_facts(identity)
    assert p['resources']['solve_seconds']==10800 and p['resources']['workflow_seconds']==14400
    assert not p['reference_only'] and p['resources']['reference_p4_factors']==0
    assert p['physical_levels']==[6,4,2] and p['intermediate']['restart']==16
    assert profile_facts('balanced_h6_p4_v5')['resources']['solve_seconds']==7200


def test_launcher_cold_cache_and_global_guard(monkeypatch,tmp_path):
    from dataclasses import replace
    from src.runners.task038_launcher import launch_specification
    monkeypatch.setattr('src.runners.task038_launcher._physical_source_gate',lambda *_:dict(source_sha='a'*40))
    seen=[]
    def guard(command,directory,**kw):
        seen.append(kw)
        assert not list(Path(kw['worker_environment']['XDG_CACHE_HOME']).iterdir())
        return dict(leader_exit_code=0,classification='COMPLETED',job_swap_activity='zero_supported_by_zero_global_activity',launch_envelope={},memory_scope='fixture')
    monkeypatch.setattr('benchmarks.subreaper_watchdog.supervise',guard)
    launch_specification(replace(spec(),expected_output_parent=tmp_path/'run'),source_sha='a'*40)
    k=seen[0]
    assert k['solve_seconds']==10800 and 14300<k['wall_seconds']<=14400
    assert k['stop_on_global_swap'] and k['hard_stop_immediate'] and k['cooperative_performance_stop']
    assert k['timebase_policy']=='conservative_realtime'


def test_budget_unique_lo_and_hi_locked(monkeypatch,tmp_path):
    from src.runners.physical_recursive_budget import launch_recursive_workflow
    from src.io.input_loader import InputError
    path=tmp_path/'budget.json'
    budget=dict(G0_G1_limit_seconds=5400,batch_limit_seconds=43200,old_V5_budget='not reused',batch_remaining=40000,charged_including_reserve=3200)
    path.write_text(json.dumps(budget));calls=[]
    monkeypatch.setattr('src.runners.task038_launcher.launch_specification',lambda s:calls.append(s) or dict(result_classification='WORKER_FAILED',run_directory='fixture'))
    for item in (spec(RECURSIVE_HI),spec(RECURSIVE_LO,'nonseparable')):
        with pytest.raises(InputError,match='only original LO'):launch_recursive_workflow(item,path)
    launch_recursive_workflow(spec(),path)
    with pytest.raises(InputError,match='already reserved'):launch_recursive_workflow(spec(),path)
    current=json.loads(path.read_text())
    assert len(calls)==1 and current['g2_attempts'][0]['status']=='WORKER_FAILED'
    assert current['batch_remaining']+current['charged_including_reserve']==43200


def test_recursive_release_preserves_fine_and_is_idempotent(monkeypatch):
    from src.solvers.physical_recursive_coarse import release_recursive_physical_solver_stack,destroy_recursive_physical_solver
    calls=[]
    def obj(name):return SimpleNamespace(destroy=lambda:calls.append(name))
    bundle=dict(fine=object(),levels=object(),pc=object(),I4=object(),B4=object(),
        inexact_ledger=obj('ledger'),p2_inverse=obj('factor'),p2_matrix=obj('matrix'),
        h4_setup=dict(smoother=obj('h4'),shell=obj('h4shell')),
        positive=dict(h6=obj('h6'),p6_shell=obj('h6shell')),actions=object())
    monkeypatch.setattr('src.solvers.fullspace_physical_intermediate_runtime.destroy_physical_intermediate_actions',lambda _:calls.append('actions'))
    monkeypatch.setattr('src.solvers.fullspace_same_mesh_hcurl_pmg_physical.destroy_same_mesh_physical_action',lambda _:calls.append('fine'))
    release_recursive_physical_solver_stack(bundle);release_recursive_physical_solver_stack(bundle)
    assert bundle['fine'] is not None and 'pc' not in bundle and 'fine' not in calls
    assert len(calls)==len(set(calls))==8
    destroy_recursive_physical_solver(bundle)
    assert calls[-1]=='fine' and not bundle


def evidence_fixture():
    ident=dict(source_sha='a'*40,physical_model_sha256='b'*64,mode_sha256='c'*64,rhs_sha256='d'*64)
    facts=dict(target=1e-4,A4_matvec=24,explicit_A4=5,B4_calls=23,p2_counts=dict(logical=46,MatSolve=46,MatSolve_attempted=46,refinement=0,A2_true=46),rhs_norm=2.,eps_norm=1.,final_true_residual=.5,restart=16,max_it=64,iterations=23,zero_start=True,status='INNER_INEXACT_AT_CAP',ksp_create_count=1,ksp_solve_count=1,ksp_destroy_count=1)
    pair=[dict(rhs_norm=2.,applied_norm=1.,inner=dict(facts)) for _ in range(2)]
    audit=dict(operation_scale=6.,closure_norm=6e-13,closure_relative=1e-13)
    counts=dict(I4=2,A4_matvec=48,explicit_A4=10,B4=46,H4=46,H4_positive=92,H6=1,H6_positive=2)
    ac=dict(audits=1,extra_A6=1,extra_PH=1,extra_A6_seconds=.1,extra_PH_seconds=.01,audit_seconds=.2)
    p2=dict(logical=92,MatSolve=92,MatSolve_attempted=92,refinement=0,A2_true=92)
    pc=dict(recursive_counts=counts,audit_costs=ac,apply_count=1,identity=ident,inexact_balance=dict(calls=pair,operation_scale=6.,audit=audit),p2_counts=p2)
    inner=[dict(identity=ident,**facts) for _ in range(2)]
    summary=dict(profile=profile_facts(RECURSIVE_LO),recursive_identity=ident,solve=dict(pc_apply_count=1,restart=32,max_it=2048,zero_start=True),
        recursive_solve=dict(inexact_audit={k:2*v for k,v in ac.items()},counts=counts,p2_counts=p2,
        storage=profile_facts(RECURSIVE_LO)['storage'],bottom=dict(rows=7326,derived_matrix_plus_reported_factor_budget_bytes=341069688)))
    return [pc],inner,[dict(last_PC=1,audit=audit,costs=ac)],summary


def test_checker_allows_inexact_and_rejects_corruption():
    from benchmarks.physical_recursive_checker import recompute_recursive
    rows=evidence_fixture();r=recompute_recursive(*rows)
    assert r['passed'] and r['inner_target_reached']==0
    bad=copy.deepcopy(rows);bad[3]['recursive_solve']['counts']['A4_matvec']+=1
    assert not recompute_recursive(*bad)['passed']
    bad=copy.deepcopy(rows);bad[1][0]['eps_norm']=.1
    assert not recompute_recursive(*bad)['passed']
    bad=copy.deepcopy(rows);bad[0][0]['inexact_balance'].pop('audit')
    assert not recompute_recursive(*bad)['passed']
    bad=copy.deepcopy(rows);bad[3]['recursive_solve']['inexact_audit']['extra_A6']=1
    assert not recompute_recursive(*bad)['passed']


def test_worker_dispatch_never_builds_reference(monkeypatch,tmp_path):
    from src.runners.physical_intermediate import run_physical_intermediate
    class ReachedRecursive(Exception):pass
    def recursive(*a,**k):raise ReachedRecursive()
    def forbidden(*a,**k):pytest.fail('old reference builder entered')
    monkeypatch.setattr('src.runners.physical_recursive_runtime.build_formal_recursive',recursive)
    monkeypatch.setattr('src.solvers.fullspace_physical_intermediate_runtime.build_physical_intermediate_solver',forbidden)
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PARENT_PID',str(os.getppid()))
    monkeypatch.setenv('PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES','10000000000')
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PHASE_PATH',str(tmp_path/'phase.json'))
    monkeypatch.setenv('PHYSICAL_TIMEBASE_GUARD','1')
    monkeypatch.setenv('PHYSICAL_TIMEBASE_POLICY','conservative_realtime')
    with pytest.raises(ReachedRecursive):run_physical_intermediate(spec().as_jsonable(),tmp_path,source_sha='a'*40)


def test_i4_performance_stop_returns_finite_safe_state():
    import numpy as np
    from petsc4py import PETSc
    from src.solvers.physical_recursive_coarse import solve_physical_i4
    x=PETSc.Vec().createSeq(3);x.set(1)
    result=None
    try:
        result=solve_physical_i4(x,lambda v:v.copy(),lambda v:v.copy(),target=1e-4,
            sample=lambda:None,save=lambda *_:pytest.fail('unexpected failure packet'),stop_requested=lambda:True)
        assert result['facts']['iterations']==0 and result['facts']['status']=='INNER_INEXACT_AT_CAP'
        assert result['facts']['final_true_residual']==1 and np.all(result['solution'].array==0)
    finally:
        if result:
            for k in ('solution','applied','residual'):result[k].destroy()
        x.destroy()


def test_frozen_rhs_bridge_rejects_permutation():
    import numpy as np
    from src.runners.physical_recursive_runtime import compare_native_rhs
    mapping=dict(indices=np.arange(3));rhs=np.array([1,2,3],complex)
    assert compare_native_rhs(mapping,mapping,rhs,rhs)['rhs_relative_difference']==0
    with pytest.raises(ValueError,match='RHS differs'):
        compare_native_rhs(mapping,mapping,rhs,rhs[::-1])
    with pytest.raises(ValueError,match='native-map'):
        compare_native_rhs(mapping,dict(indices=np.array([0,2,1])),rhs,rhs)
