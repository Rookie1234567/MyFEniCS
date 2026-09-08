"""One focused V6 batch: algebra, owned bookkeeping, bounded PETSc, tiny FE."""
from contextlib import ExitStack
from dataclasses import replace
import inspect
import numpy as np
import pytest
from petsc4py import PETSc
from mpi4py import MPI
from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling, BalancedConstraintRejected
from src.solvers.physical_inexact_balance import InexactBalanceLedger
from src.solvers.physical_recursive_coarse import solve_physical_i4


@pytest.mark.parametrize('zero', [False, True])
def test_inexact_identity_owned_eps_and_exit_audit(zero):
    rng=np.random.default_rng(39); a=rng.normal(size=(9,9))+1j*rng.normal(size=(9,9))+6*np.eye(9)
    p=rng.normal(size=(9,3))+1j*rng.normal(size=(9,3)); ac=p.conj().T@a@p
    packets=[]; ledger=InexactBalanceLedger(lambda x:a@x, lambda x:p.conj().T@x,
        save=lambda *x:packets.append(x),every=32)
    buffer=np.empty(3,complex)
    def coarse(x):
        g=p.conj().T@x; y=.9*np.linalg.solve(ac,g); applied=ac@y
        buffer[:]=g-applied; ledger.record(g,applied,buffer,{'status':'finite'})
        return p@y
    pc=PhysicalBalancedCoupling(lambda x:a@x,coarse,lambda x:.03*x,
        lambda x:p.conj().T@x,route='BAL_H',inexact_ledger=ledger)
    q=np.zeros(9,complex) if zero else np.arange(9)+1j
    try:
        pc.apply(q); assert pc.last_apply_facts['inexact_balance']['actual_audit']=='PASS'
        z=pc.apply(q); assert pc.last_apply_facts['inexact_balance']['actual_audit']=='not_sampled'
        old=ledger.last['difference'].copy();buffer[:]=1e8
        ledger.audit_last();np.testing.assert_array_equal(ledger.last['difference'],old)
        assert ledger.audit_count==2 and ledger.A_count==2 and ledger.PH_count==2
        assert pc.last_apply_facts['counts']['C']==2
        if not zero:assert np.linalg.norm(p.conj().T@(q-a@z))>1e-5
    finally:ledger.destroy()
    assert not ledger.calls and ledger.last is None and not packets


def test_default_exact_rejects_and_inexact_miswire_saves():
    a=np.eye(3,dtype=complex);p=np.eye(3,dtype=complex)
    old=PhysicalBalancedCoupling(lambda x:a@x,lambda x:.9*x,lambda x:.1*x,
        lambda x:p@x,route='BAL_H')
    with pytest.raises(BalancedConstraintRejected):old.apply(np.ones(3,complex))
    packets=[]; ledger=InexactBalanceLedger(lambda x:2*x,lambda x:x.copy(),save=lambda *x:packets.append(x))
    def coarse(x):
        y=.9*x;ledger.record(x,y,x-y,{});return y
    pc=PhysicalBalancedCoupling(lambda x:x.copy(),coarse,lambda x:.1*x,
        lambda x:x.copy(),route='BAL_H',inexact_ledger=ledger)
    try:
        with pytest.raises(BalancedConstraintRejected):pc.apply(np.ones(3,complex))
        assert packets and pc.last_apply_facts['live_after_cleanup']==0
    finally:ledger.destroy()


def owned_diagonal(diagonal):
    def apply(x):
        y=x.copy();y.array[:]*=diagonal;return y
    return apply


@pytest.mark.parametrize('kind', ['solve','zero','time','cap','saturation'])
def test_inner_bounded_explicit_and_cleanup(kind):
    n=96;rhs=PETSc.Vec().createSeq(n,comm=PETSc.COMM_SELF);rhs.set(0 if kind=='zero' else 1+1j)
    diagonal=np.geomspace(1e-4,1,n)*(1+.3j)
    action=owned_diagonal(diagonal)
    pc=owned_diagonal(1/diagonal) if kind=='solve' else (lambda x:x.copy())
    if kind=='saturation':pc=owned_diagonal(np.zeros(n))
    packets=[]; original_rhs=rhs.array.copy()
    try:
        result=solve_physical_i4(rhs,action,pc,target=1e-6,sample=lambda:None,
            save=lambda *x:packets.append(x),clock=lambda:61. if kind=='time' else 0.)
        try:
            f=result['facts'];assert f['iterations']<=64
            np.testing.assert_array_equal(rhs.array,original_rhs)
            np.testing.assert_allclose(result['applied'].array,diagonal*result['solution'].array)
            np.testing.assert_allclose(result['residual'].array,rhs.array-result['applied'].array)
            assert f['ksp_create_count']==f['ksp_solve_count']==f['ksp_destroy_count']==1
            if kind in ('solve','zero'):assert f['status']=='INNER_TARGET_REACHED'
            else:assert f['status']=='INNER_INEXACT_AT_CAP'
            if kind=='time':assert f['iterations']==0
            assert not packets
        finally:
            for k in ('solution','applied','residual'):result[k].destroy()
    finally:rhs.destroy()


def test_inner_nonfinite_saved_before_rejection():
    rhs=PETSc.Vec().createSeq(4,comm=PETSc.COMM_SELF);rhs.set(1)
    packets=[]
    try:
        with pytest.raises((FloatingPointError, PETSc.Error)):
            solve_physical_i4(rhs,owned_diagonal(np.nan),lambda x:x.copy(),target=1e-4,
                sample=lambda:None,save=lambda *x:packets.append(x))
        assert packets and packets[-1][1]['rhs'].shape==(4,)
        assert all(k in packets[-1][1] for k in ('A4_matvec','B4_calls','explicit_A4','iterations','conservative_seconds'))
    finally:rhs.destroy()


def test_global_swap_opt_in_and_default_compatible():
    from benchmarks.subreaper_watchdog import global_swap_stop, supervise, stop_signal
    import signal
    baseline=dict(pswpin_pages=1281,pswpout_pages=2335)
    assert global_swap_stop(baseline,baseline,enabled=True) is None
    changed=dict(baseline,pswpout_pages=2336)
    assert global_swap_stop(baseline,changed) is None
    assert global_swap_stop(baseline,changed,enabled=True)=='GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED'
    assert inspect.signature(supervise).parameters['stop_on_global_swap'].default is False
    assert stop_signal('GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED',hard_stop_immediate=True,
        elapsed=0,grace_seconds=60)==signal.SIGKILL


def test_bottom_cap_default_unchanged_before_factor():
    from src.solvers.fullspace_bounded_mumps import BoundedP1Factor
    m=PETSc.Mat().createAIJ([8200,8200],nnz=1,comm=PETSc.COMM_SELF)
    try:
        for pilot in (False,True):
            with pytest.raises(ValueError,match='BOTTOM_SCALE_LIMIT' if pilot else '4096'):
                BoundedP1Factor(m,label='test',resource_sample=lambda:None,marker=lambda *x:None,
                    physical_p2_pilot=pilot)
        assert inspect.signature(BoundedP1Factor).parameters['physical_p2_pilot'].default is False
    finally:m.destroy()


def test_tiny_physical_recursive_builder_and_galerkin():
    from src.common.config_3d import target_stage4_config
    from src.solvers.physical_recursive_coarse import build_recursive_physical_solver, destroy_recursive_physical_solver
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector, owned_slave_indices
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from benchmarks.subreaper_watchdog import memory_envelope
    import os
    cfg=replace(target_stage4_config(degree=6,h_nm=100),period_x=20.,period_y=15.,
        grating_width_x=8.,grating_width_y=15.,grating_height=2.,z_min=-1.,z_max=3.,
        air_height=3.,substrate_thickness=1.,mesh_cell_type='hexahedron',
        mesh_spacing_mode='boundary_fitted',mesh_axis_cell_counts=(3,2,3),
        incident_theta_deg=74.,incident_phi_deg=17.,n_substrate=1.4+.05j,n_grating=.9+.02j)
    def sample():
        env=memory_envelope();r=process_tree_snapshot(os.getpid(),'tiny_g1',None)
        r['launch_cap_bytes']=min(12_000_000_000,r['rss_bytes']+env['effective_available_bytes']-env['reserve_bytes'])
        assert r['all_status_readable'] and r['swap_bytes']==0
        assert env['effective_available_bytes']>=env['reserve_bytes']
        return r
    packets=[];bundle=None
    try:
        bundle=build_recursive_physical_solver(cfg,MPI.COMM_WORLD,target=1e-4,sample=sample,
            marker=lambda name,f:print(name,flush=True),save=lambda *x:packets.append(x),audit_every=1)
        assert set(bundle['levels']['spaces'])=={6,4,2}
        assert not bundle['actions']['mass'] and not bundle['actions']['shifted']
        assert bundle['p2_matrix'].getSize()[0]<=8192
        assert bundle['p2_inverse'].bottom.audit['derived_matrix_plus_reported_factor_budget_bytes']<=512*1024**2
        rng=np.random.default_rng(395)
        with ExitStack() as resources:
            def own(x):resources.callback(x.destroy);return x
            def vector(p):
                x=own(level_vector(bundle['levels'],p));x.array[:]=rng.normal(size=x.getLocalSize())+1j*rng.normal(size=x.getLocalSize())
                x.array[owned_slave_indices(bundle['levels']['spaces'][p],bundle['levels']['floquets'][p])]=0
                return x
            for upper,lower in [(6,4),(4,2)]:
                t=bundle['actions']['transfers'][(upper,lower)];x,y=vector(lower),vector(upper)
                px,phy=own(t.apply_primal(x)),own(t.apply_adjoint(y))
                assert abs(np.vdot(px.array,y.array)-np.vdot(x.array,phy.array))<=1e-10*max(abs(np.vdot(px.array,y.array)),1)
                native=own(apply_owned(bundle['actions']['physical'][lower]['physical_action'],x))
                ap=own(apply_owned(bundle['actions']['physical'][upper]['physical_action'],px));projected=own(t.apply_adjoint(ap))
                projected.axpy(-1,native);assert projected.norm()/native.norm()<=1e-10
            rhs=vector(2);rhs_before=rhs.array.copy();y=own(bundle['p2_inverse'].apply(rhs))
            np.testing.assert_array_equal(rhs.array,rhs_before)
            assert np.max(np.abs(y.array[owned_slave_indices(bundle['levels']['spaces'][2],bundle['levels']['floquets'][2])]),initial=0)==0
            assert bundle['p2_inverse'].last_facts['counts']['logical']==1
            assert bundle['p2_inverse'].last_facts['relative']<=1e-10
            # One full new PC checks eps identity with actual FE operators.
            q=vector(6);q_before=q.array.copy();z=own(bundle['pc'].apply(q))
            np.testing.assert_array_equal(q.array,q_before)
            assert np.max(np.abs(z.array[owned_slave_indices(bundle['levels']['spaces'][6],bundle['levels']['floquets'][6])]),initial=0)==0
            assert bundle['pc'].last_apply_facts['inexact_balance']['actual_audit']=='PASS'
            assert bundle['counts']['I4']==2
            bundle['inexact_ledger'].audit_last()
    finally:
        if bundle is not None:destroy_recursive_physical_solver(bundle)


@pytest.mark.parametrize('errors',[(.1,0.),(.5,.5,.5)])
def test_bottom_refinement_limit_and_failure_packet(errors):
    from src.solvers.physical_recursive_coarse import PhysicalP2Inverse
    matrix=PETSc.Mat().createAIJ([3,3],nnz=1,comm=PETSc.COMM_SELF)
    for i in range(3):matrix.setValue(i,i,1)
    matrix.assemble()
    rhs=matrix.createVecRight();rhs.set(1+1j);packets=[];calls=[]
    class Bottom:
        def solve_lean(self,b):
            y=b.copy();y.scale(1-errors[min(len(calls),len(errors)-1)]);calls.append(1);return y,{}
    inverse=PhysicalP2Inverse.__new__(PhysicalP2Inverse)
    from types import SimpleNamespace
    inverse.bottom=Bottom();inverse.matrix=matrix
    inverse.action=SimpleNamespace(apply_into=lambda x,y:x.copy(y))
    inverse.slaves=np.array([],int);inverse.sample=lambda:None;inverse.save=lambda *x:packets.append(x)
    inverse.counts=dict(logical=0,MatSolve=0,refinement=0,A2_true=0);inverse.last_facts={}
    try:
        if len(errors)==2:
            y=inverse.apply(rhs)
            try:np.testing.assert_allclose(y.array,rhs.array)
            finally:y.destroy()
            assert inverse.last_facts['counts']['logical']==1 and len(calls)==2
        else:
            with pytest.raises(RuntimeError,match='two refinements'):inverse.apply(rhs)
            assert len(calls)==3 and packets[-1][0]=='bottom_failure'
            assert packets[-1][1]['solution'].shape==(3,)
        assert inverse.counts['refinement']==len(calls)-1
    finally:rhs.destroy();matrix.destroy()


def test_saved_calibration_hash_and_mapping_guard():
    from src.runners.physical_recursive_controls import load_recursive_calibration
    from pathlib import Path
    p=Path('benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json')
    if not p.exists():pytest.skip('local hash-bound historical packet not distributed in Git')
    items=load_recursive_calibration(p)
    assert len(items)==6 and {x['identity']['role'] for x in items}=={'g1','old_exact_path_g2'}
    for item in items:
        assert item['rhs'].shape==item['reference_y'].shape==(53084,)
        assert len(item['reference_map']['independent_indices'])==48960


@pytest.mark.parametrize('limit,screen,expected',[(7200,False,'PERFORMANCE_CONTROLLED_STOP'),
    (10800,False,'TRUE_RESIDUAL_PASS'),(10800,True,'SCREEN_BUDGET_NO_QUALIFIED_PROGRESS')])
def test_outer_real_stop_enum_and_explicit_limit(limit,screen,expected):
    from src.solvers.physical_balanced_fgmres import run_balanced_fgmres
    rhs=PETSc.Vec().createSeq(8,comm=PETSc.COMM_SELF);rhs.set(1+1j)
    try:
        r=run_balanced_fgmres(rhs,lambda x:x.copy(),lambda x:x.copy(),
            checkpoint=lambda *x:None,append=lambda *x:None,seconds=lambda:8000.,
            screen_enabled=screen,solve_limit_seconds=limit)
        try:
            assert r['status']==expected
            assert r['ksp_create_count']==r['ksp_solve_count']==r['ksp_destroy_count']==1
        finally:r['final_solution'].destroy()
    finally:rhs.destroy()
