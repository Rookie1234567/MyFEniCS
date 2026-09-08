"""One focused complex-algebra/interface batch, no FE or new numerical case."""
import numpy as np
import pytest
from petsc4py import PETSc
from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
from src.solvers.physical_balanced_fgmres import BalancedScreen, run_balanced_fgmres
from src.solvers.physical_reference_diagnostics import DiagnosticRefinementV4, ReferenceAccuracyRejected
from src.test.test_371_physical_reference_completion import problem


def operators(n=9):
    rng=np.random.default_rng(37)
    a=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))+3*np.eye(n)
    p=rng.normal(size=(n,2))+1j*rng.normal(size=(n,2))
    C=p@np.linalg.solve(p.conj().T@a@p,p.conj().T)
    return a,p,C


@pytest.mark.parametrize('route',['BAL_H','BAL_S','PROJ_K6'])
def test_complex_roles_definition_and_live_vectors(route):
    a,p,c=operators();q=np.arange(9)+1j;original=q.copy();s=np.diag(np.linspace(.2,.8,9))
    pc=PhysicalBalancedCoupling(lambda x:a@x,lambda x:c@x,lambda x:s@x,
                                lambda x:p.conj().T@x,route=route)
    z=pc.apply(q);facts=pc.last_apply_facts
    np.testing.assert_array_equal(q,original)
    assert facts['peak_new_fine_vectors']<=32 and facts['live_after_cleanup']==0
    np.testing.assert_allclose(p.conj().T@(q-a@z),0,atol=1e-10)
    if route!='PROJ_K6':
        expected=c@q+(np.eye(9)-c@a)@s@(np.eye(9)-a@c)@q
        np.testing.assert_allclose(z,expected,rtol=1e-12,atol=1e-12)
        assert facts['counts']['C']==2 and facts['counts']['A_structure']==2
    else:
        steps=len(facts['inner']);assert steps<=6
        assert facts['counts']['C']==1+steps
        assert facts['counts']['A_structure']==1+2*steps
        assert facts['counts']['A_inner_true']==steps
        rc=q-a@c@q
        assert np.linalg.norm(rc-a@(z-c@q))/np.linalg.norm(rc)==pytest.approx(facts['inner'][-1]['true_relative'])
    v=p@np.array([1+2j,3-1j])
    np.testing.assert_allclose(pc.apply(a@v),v,rtol=1e-10,atol=1e-10)
    np.testing.assert_allclose((np.eye(9)-c@a)@p,0,atol=1e-12)
    np.testing.assert_allclose(a@(np.eye(9)-c@a),(np.eye(9)-a@c)@a,atol=1e-12)


def test_projected_zero_saturation_and_borrowed_rejection():
    a=np.diag([1.,2.,3.]).astype(complex);c=np.diag([1.,0,0])
    pc=PhysicalBalancedCoupling(lambda x:a@x,lambda x:c@x,lambda x:0*x,
                                lambda x:x[:1].copy(),route='PROJ_K6')
    assert np.linalg.norm(pc.apply(np.zeros(3,complex)))==0
    assert pc.last_apply_facts['status']=='INNER_ZERO_RESIDUAL'
    z=pc.apply(np.ones(3,complex))
    assert pc.last_apply_facts['status']=='INNER_TARGET_NOT_REACHED'
    assert pc.last_apply_facts['saturation_without_target'] and len(pc.last_apply_facts['inner'])==1
    assert np.isfinite(z).all()
    bad=PhysicalBalancedCoupling(lambda x:x,lambda x:x,lambda x:x,lambda x:x,route='BAL_H')
    with pytest.raises(TypeError):bad.apply(np.ones(3,complex))
    assert bad.last_apply_facts['live_after_cleanup']==0


def test_screen_boundaries_and_no_fake_checkpoints():
    s=BalancedScreen()
    assert s.inspect(31,.02,1799) is None
    assert not s.inspect(31,.02,1800)['passed']
    s=BalancedScreen()
    for it,r in [(64,1.),(96,.6)]:assert s.inspect(it,r,10) is None
    assert s.inspect(128,.4,11)['passed']
    assert s.inspect(256,.9,1801)['passed']  # exactly one screen
    s=BalancedScreen();assert s.inspect(1,.01,1800)['passed']


def test_formal_reference_scalar_success_and_full_refusal():
    for error in (0.,.1):
        with problem([error]) as (reference,rhs,calls,packets):
            old=reference.diagnostic_refinement_v4
            policy=DiagnosticRefinementV4(lambda n,f:packets.append((n,f)),old.carrier_action,
                old.control,old.identity,logical_limit=55,solve_limit=165,capture_success_vectors=False,
                retain_records=False,replay_first_failure=False,verify_first_actions=False)
            reference.diagnostic_refinement_v4=policy
            if error:
                with pytest.raises(ReferenceAccuracyRejected):reference.solve_intermediate(rhs)
                assert len(calls)==3 and packets[-1][0].endswith('_failure')
                assert 'g' in packets[-1][1] and 'actions' in packets[-1][1]
            else:
                for _ in range(11):reference.solve_intermediate(rhs)['final_solution'].destroy()
                assert len(calls)==11 and all('_decision_' in n for n,_ in packets)
                assert not policy.records and policy.last_record['reconstructed_failure_status'] is None


@pytest.mark.parametrize('screen_enabled',[True,False])
def test_live_petsc_fgmres_once_and_complex_owned_actions(screen_enabled):
    n=160;diagonal=np.geomspace(.03,1,n)*(1+.2j)
    rhs=PETSc.Vec().createSeq(n,comm=PETSc.COMM_SELF);rhs.set(1+1j)
    def action(x):
        y=x.copy();y.array[:]*=diagonal;return y
    records=[];saved={};clock=[0.]
    def append(name,row):
        records.append((name,row))
        if name=='iterations.jsonl' and 1e-6<row['reported_relative']<=.005:
            clock[0]=1800.
    def checkpoint(iteration,solution,relative):
        assert iteration not in saved
        saved[iteration]=(solution.array.copy(),relative)
    try:
        result=run_balanced_fgmres(rhs,action,lambda x:x.copy(),checkpoint=checkpoint,
            append=append,seconds=lambda:clock[0],screen_enabled=screen_enabled)
        try:
            assert result['ksp_create_count']==result['ksp_solve_count']==result['ksp_destroy_count']==1
            if screen_enabled:
                assert result['screen']['passed'] and result['iterations']>result['screen']['iteration']
            else:assert result['screen'] is None
            np.testing.assert_allclose(saved[result['iterations']][0],result['final_solution'].array,rtol=1e-12,atol=1e-12)
            assert result['final_true_residual']<=1e-6
            np.testing.assert_allclose(result['final_solution'].array,(1+1j)/diagonal,rtol=2e-5)
        finally:result['final_solution'].destroy()
    finally:rhs.destroy()


@pytest.mark.parametrize('route',['BAL_H','BAL_S','PROJ_K6'])
def test_petsc_complex_vector_oracle_and_cleanup(route):
    a,p,c=operators();q=np.arange(9)+1j
    def callback(matrix):
        def apply(x):
            out=PETSc.Vec().createSeq(matrix.shape[0],comm=PETSc.COMM_SELF)
            out.array[:]=matrix@x.array
            return out
        return apply
    expected=PhysicalBalancedCoupling(lambda x:a@x,lambda x:c@x,lambda x:.3*x,
        lambda x:p.conj().T@x,route=route).apply(q)
    pc=PhysicalBalancedCoupling(callback(a),callback(c),callback(.3*np.eye(9)),callback(p.conj().T),route=route)
    rhs=PETSc.Vec().createSeq(9,comm=PETSc.COMM_SELF);rhs.array[:]=q
    try:
        z=pc.apply(rhs)
        try:np.testing.assert_allclose(z.array,expected,rtol=1e-10,atol=1e-10)
        finally:z.destroy()
        np.testing.assert_array_equal(rhs.array,q)
        assert pc.last_apply_facts['live_after_cleanup']==0
    finally:rhs.destroy()


def test_real_e1_inputs_load_without_fe():
    import json
    from pathlib import Path
    from src.runners.physical_diagnostic_completion import reuse_v3
    from src.runners.actual_error_diagnosis import load_actual_evidence
    from src.runners.physical_balanced_controls import load_balanced_inputs
    inventory=Path('docs/task039_extra_physical_multilevel/outcomes/records/nonconvergence_diagnosis_v3.json')
    inputs=load_actual_evidence('input/task39extra/actual_error_evidence.json',inventory,reuse_v3(json.loads(inventory.read_text())))
    samples=load_balanced_inputs(inputs)
    assert list(samples)==['A2R160','LIGHT448','JOINT448','V4_KNOWN']
    assert all(np.isfinite(v['e']).all() and np.isfinite(v['q']).all() for v in samples.values())


def test_new_policy_invalid_slave_input_saved_without_backsolve():
    with problem([0.]) as (reference,rhs,calls,packets):
        old=reference.diagnostic_refinement_v4
        reference.slaves=np.array([1],dtype=np.int32)
        reference.diagnostic_refinement_v4=DiagnosticRefinementV4(lambda n,f:packets.append((n,f)),
            old.carrier_action,old.control,old.identity,capture_success_vectors=False,
            replay_first_failure=False,verify_first_actions=False)
        with pytest.raises(ValueError,match='slave-zero'):reference.solve_intermediate(rhs)
        assert not calls and packets[-1][0].endswith('_invalid_input')
        np.testing.assert_array_equal(packets[-1][1]['g'],rhs.array)


def test_arnoldi_numeric_refusal_is_typed_and_cleans_vectors(monkeypatch):
    from src.solvers.physical_balanced_coupling import BalancedArnoldiRejected
    a,p,c=operators()
    pc=PhysicalBalancedCoupling(lambda x:a@x,lambda x:c@x,lambda x:.3*x,
                                lambda x:p.conj().T@x,route='PROJ_K6')
    def failed_svd(*args,**kwargs):raise np.linalg.LinAlgError('tiny injected SVD nonconvergence')
    monkeypatch.setattr(np.linalg,'lstsq',failed_svd)
    with pytest.raises(BalancedArnoldiRejected) as error:pc.apply(np.arange(9)+1j)
    assert 'hessenberg' in error.value.facts
    assert pc.apply_count==0 and pc.last_apply_facts['live_after_cleanup']==0
