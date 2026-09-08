"""Public dispatch and conditional flow checks; no full-size PDE."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

from src.io import load_and_resolve
from src.io.physical_balanced_profile import BALANCED_PROFILES
from src.io.physical_intermediate_profile import profile_facts
from src.runners.physical_balanced_budget import launch_balanced_workflow, SCHEMA
from src.io.input_loader import InputError


def original(identity):
    return load_and_resolve(Path('input/task39extra')/f'original_13p5nm_p6h10_{identity}.dat')


@pytest.mark.parametrize('identity',BALANCED_PROFILES)
def test_public_dispatch_and_frozen_models(identity,monkeypatch,tmp_path):
    from scripts.run_case import main
    spec=original(identity)
    assert spec.physical_model_sha256=='9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
    facts=profile_facts(identity)
    assert facts['outer']['live_KSP'] and facts['resources']['batch_limit_seconds']==43200
    assert facts['resources']['independent_p1_factors']==int(identity=='balanced_s6_p4_v5')
    seen=[]
    monkeypatch.setattr('src.runners.physical_balanced_budget.launch_balanced_workflow',
        lambda s,b:seen.append((s,b)) or dict(result_classification='worker_exit0'))
    assert main([str(spec.source_path),'--batch-budget-ledger',str(tmp_path/'budget.json')])==0
    assert seen[0][0].solver['preconditioner']==identity
    notch=load_and_resolve(Path('input/task39extra')/f'nonseparable_13p5nm_p6h10_{identity}.dat')
    assert notch.physical_model_sha256!=spec.physical_model_sha256


def test_unique_notch_then_next_original_after_numerical_stop(monkeypatch,tmp_path):
    path=tmp_path/'budget.json'
    path.write_text(json.dumps(dict(schema=SCHEMA,limit_seconds=43200,attempts=[
        dict(kind='E0_reserve',elapsed_seconds=600),dict(kind='E1',elapsed_seconds=1138.4734064556703)])))
    calls=[]
    def launch(spec):
        calls.append(spec)
        root=tmp_path/f'run{len(calls)}';root.mkdir()
        notch=bool(spec.geometry.get('cell_notch'))
        status='ITERATION_BUDGET_EXHAUSTED' if notch else 'BALANCED_OUTPUT_PASS'
        (root/'physical_intermediate_summary.json').write_text(json.dumps(dict(status=status,
            checker=dict(classification=status,independent_output_gates_passed=not notch))))
        return dict(result_classification='worker_exit0' if not notch else 'worker_exit_nonzero',run_directory=str(root),
                    resource_authority=dict(classification='COMPLETED' if not notch else 'WORKER_FAILED'))
    monkeypatch.setattr('src.runners.task038_launcher.launch_specification',launch)
    launch_balanced_workflow(original(BALANCED_PROFILES[0]),path)
    launch_balanced_workflow(original(BALANCED_PROFILES[1]),path)
    assert len(calls)==3 and sum(bool(s.geometry.get('cell_notch')) for s in calls)==1
    with pytest.raises(InputError):launch_balanced_workflow(original(BALANCED_PROFILES[1]),path)


def test_screen_raw_recompute_and_no_invented_trend():
    from benchmarks.physical_intermediate_checker import recompute_balanced_screen
    rows=[dict(iteration=i,explicit_true_residual=r,solve_seconds=100) for i,r in [(64,1.),(96,.6),(128,.4)]]
    solve=dict(screen_enabled=True,screen=dict(iteration=128,passed=True))
    assert recompute_balanced_screen(solve,rows)['matches']
    rows[1]['explicit_true_residual']=1.1
    assert not recompute_balanced_screen(solve,rows)['matches']
    assert not recompute_balanced_screen(solve,rows[-1:])['matches']
    assert recompute_balanced_screen(dict(screen_enabled=False,screen=None),rows)['matches']


def test_checker_accepts_final_refinement_and_retains_initial_miss():
    from benchmarks.physical_intermediate_checker import recompute_p4_decisions
    decisions=[dict(logical_rhs=1,refinement_steps=i,original_rhs_norm=2.,
        true_residual_norm=2*r,final_true_residual=r,external_solves=i+1)
        for i,r in enumerate([1e-5,1e-12])]
    pcs=[dict(p4_counts=dict(C=1,MatSolve=2))]
    assert recompute_p4_decisions(decisions,pcs)['passed']
    assert decisions[0]['final_true_residual']>1e-10
    decisions[-1]['true_residual_norm']=1e-3
    assert not recompute_p4_decisions(decisions,pcs)['passed']


def test_zero_rhs_decision_does_not_invent_matsolve():
    from benchmarks.physical_intermediate_checker import recompute_p4_decisions
    decisions=[dict(logical_rhs=1,refinement_steps=0,original_rhs_norm=0.,
        true_residual_norm=0.,final_true_residual=0.,external_solves=0),
        dict(logical_rhs=2,refinement_steps=0,original_rhs_norm=2.,
        true_residual_norm=2e-12,final_true_residual=1e-12,external_solves=1)]
    facts=recompute_p4_decisions(decisions,[dict(p4_counts=dict(C=2,MatSolve=1))])
    assert facts['passed'] and facts['MatSolve']==1 and facts['refinements']==0


def test_screen_negative_never_masks_correctness_errors():
    from benchmarks.physical_intermediate_checker import balanced_output_classification
    summary=dict(status='SCREEN_BUDGET_NO_QUALIFIED_PROGRESS')
    expected=['fine residual 0.5 exceeds 1e-6','official outputs unavailable']
    assert balanced_output_classification(summary,expected,expected)==summary['status']
    for error in ('native A4 final residual or accounting gate failed','raw/reported true residual mismatch'):
        assert balanced_output_classification(summary,expected+[error],expected)=='CORRECTNESS_OR_EVIDENCE_BLOCKED'


def test_limited_notch_stops_unused_originals_even_without_reference(monkeypatch,tmp_path):
    path=tmp_path/'budget.json'
    path.write_text(json.dumps(dict(schema=SCHEMA,limit_seconds=43200,attempts=[])))
    calls=[]
    def launch(spec):
        calls.append(spec);root=tmp_path/f'run{len(calls)}';root.mkdir()
        status='BALANCED_OUTPUT_AUTHORITY_LIMITED' if spec.geometry.get('cell_notch') else 'BALANCED_OUTPUT_PASS'
        (root/'physical_intermediate_summary.json').write_text(json.dumps(dict(status=status,
            checker=dict(classification=status,independent_output_gates_passed=True))))
        return dict(result_classification='worker_exit0',run_directory=str(root),
                    resource_authority=dict(classification='COMPLETED'))
    monkeypatch.setattr('src.runners.task038_launcher.launch_specification',launch)
    monkeypatch.setattr('src.runners.physical_balanced_budget.conditional_reference',
        lambda *_:dict(status='REFERENCE_AUTHORITY_LIMITED',reason='capacity not admitted'))
    launch_balanced_workflow(original(BALANCED_PROFILES[0]),path)
    budget=json.loads(path.read_text());notch=budget['attempts'][1]
    assert notch['qualified'] and not notch['reference_qualified']
    with pytest.raises(InputError,match='campaign complete'):
        launch_balanced_workflow(original(BALANCED_PROFILES[1]),path)
    assert len(calls)==2
    budget['attempts'][0]['parent_classification']=None
    path.write_text(json.dumps(budget))
    with pytest.raises(InputError,match='parent resource/correctness'):
        launch_balanced_workflow(original(BALANCED_PROFILES[1]),path)


def test_limited_authority_never_masks_physics_failure():
    from benchmarks.physical_intermediate_checker import balanced_output_classification
    summary=dict(status='RESIDUAL_PASS',matched_reference=dict(status='REFERENCE_AUTHORITY_LIMITED'))
    assert balanced_output_classification(summary,[])=='BALANCED_OUTPUT_AUTHORITY_LIMITED'
    assert balanced_output_classification(summary,['volume energy failed'])=='NUMERICAL_OR_OUTPUT_FAIL'
    summary['matched_reference']['status']='MATCHED_REFERENCE_PASS'
    assert balanced_output_classification(summary,[])=='BALANCED_OUTPUT_PASS'


@pytest.mark.parametrize('identity',BALANCED_PROFILES)
def test_public_launcher_bal_s_keeps_cooperative_guard(identity,monkeypatch,tmp_path):
    from dataclasses import replace
    from src.runners.task038_launcher import launch_specification
    spec=replace(original(identity),expected_output_parent=tmp_path/'run')
    monkeypatch.setattr('src.runners.task038_launcher._physical_source_gate',lambda *_:dict(source_sha='a'*40))
    seen=[]
    def guard(command,directory,**kw):
        seen.append(kw)
        return dict(leader_exit_code=0,classification='COMPLETED',
            job_swap_activity='zero_supported_by_zero_global_activity',launch_envelope={},memory_scope='tiny')
    monkeypatch.setattr('benchmarks.subreaper_watchdog.supervise',guard)
    result=launch_specification(spec,source_sha='a'*40)
    assert result['result_classification']=='worker_exit0'
    assert seen[0]['cooperative_performance_stop'] and seen[0]['timebase_guard']
    assert seen[0]['timebase_policy']=='conservative_realtime' and seen[0]['solve_seconds']==7200
    assert 10700<seen[0]['wall_seconds']<=10800


def test_actual_modal_schema_all_channels_and_absolute_totals(tmp_path):
    from src.runners.physical_balanced_output import compare_modal_files,compare_power_totals
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    rows=[dict(side='top',m=0,n=n,polarization='s',R=.1,T=0) for n in (0,1)]
    amps=[dict(**{k:v for k,v in r.items() if k not in ('R','T')},
               outgoing_amplitude=[1.,2.],outgoing_amplitude_at_boundary=[2.,-1.]) for r in rows]
    for root in (a,b):
        (root/'dtn_port_diffraction_orders_3d.json').write_text(json.dumps(dict(orders=rows)))
        (root/'dtn_auxiliary_amplitudes_3d.json').write_text(json.dumps(amps))
    assert compare_modal_files(a,b)['amplitude_relative_difference']==0
    amps[1]['outgoing_amplitude_at_boundary'][0]+=1
    (a/'dtn_auxiliary_amplitudes_3d.json').write_text(json.dumps(amps))
    assert compare_modal_files(a,b)['amplitude_relative_difference']>1e-4
    out=dict(port_metrics=dict(R_total=0.,T_total=1.,A_balance=0.),volume_metrics=dict(A_volume_total=0.))
    assert compare_power_totals(out,out)['total_absolute_differences']==dict(R=0,T=0,A=0,A_volume=0)


def test_midpoint_notch_preserves_other_materials():
    from src.geometry.cell_notch import apply_cell_notch
    cfg=SimpleNamespace(cell_notch='positive_x_middle_y_z40_80',period_y=25.,tags=SimpleNamespace(grating=3,air=1))
    xyz=np.array([[2,0,50],[-2,0,50],[2,8,50],[2,0,80],[2,0,50]],float)
    np.testing.assert_array_equal(apply_cell_notch(xyz,np.array([3,3,3,3,2]),cfg),[1,3,3,3,2])


@pytest.mark.parametrize('identity',BALANCED_PROFILES)
def test_formal_owned_adapter_scalar_policy(identity,monkeypatch):
    from src.test.test_371_physical_reference_completion import problem
    from src.solvers.physical_balanced_runtime import install_balanced_pc
    with problem([0.]) as (reference,rhs,calls,packets):
        carrier=reference.diagnostic_refinement_v4.carrier_action
        smoother=SimpleNamespace(last_apply_facts={})
        def smooth(x):
            smoother.last_apply_facts=dict(apply_count=1,matrix_mult_count=2)
            return x.copy()
        smoother.apply=smooth
        bundle=dict(actions=dict(physical={4:dict(dtn_action=carrier)},volume_quadrature_metadata=[],
            transfers={(6,4):SimpleNamespace(apply_primal=lambda x:x.copy(),apply_adjoint=lambda x:x.copy())}),
            fine=dict(physical_action=reference.action,mode_sha256='tiny'),
            positive=dict(h6=smoother,upper_cycle=smoother))
        def attach(b,cfg,**kw):
            assert kw['light']==(identity!='balanced_s6_p4_v5')
            reference.diagnostic_refinement_v4=kw['diagnostic_refinement_v4'];b['reference_factor']=reference
        monkeypatch.setattr('src.solvers.fullspace_physical_intermediate_runtime.attach_physical_reference',attach)
        logs=[]
        apply,policy=install_balanced_pc(bundle,None,identity,sample=lambda:None,marker=lambda *_:None,
            save=lambda n,f:packets.append((n,f)),append=lambda n,f:logs.append((n,f)))
        z=apply(rhs)
        try:
            assert policy.records==[] and policy.logical_rhs<=7
            assert all('_decision_' in n for n,_ in packets)
            assert logs[0][1]['p4_counts']['C']==policy.logical_rhs
            assert logs[0][1]['smoother_facts']
        finally:z.destroy()
