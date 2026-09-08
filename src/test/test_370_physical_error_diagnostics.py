"""One small algebra batch plus a tiny FE mass/constraint check, no solve."""
import numpy as np
import pytest

from src.solvers.physical_error_diagnostics import (
    component_diagnostics,coarse_diagnostics,evaluate_residual_profiles,homogeneity_check,metric_square,project_error)


def test_complex_projection_coarse_response_and_unresolved_bound():
    p=np.array([[1,0],[1j,1],[0,2j]],complex)
    mass=np.diag([2.,3.,4.])
    a=np.array([[2,1j,3],[.5,2,0],[1j,0,4]],complex)
    m=lambda x:mass@x
    adj=lambda x:p.conj().T@x
    cmat=p.conj().T@mass@p
    e=np.array([1+2j,3-1j,.5j])
    before=e.copy()
    result=project_error(lambda x:p@x,adj,m,np.diag(cmat),e)
    expected=p@np.linalg.solve(cmat,p.conj().T@mass@e)
    np.testing.assert_allclose(result['parallel'],expected,rtol=1e-11,atol=1e-12)
    assert result['status']=='PROJECTION_CLOSED'
    coarse=coarse_diagnostics(lambda x:a@x,m,lambda x:p@x,adj,
        lambda x:np.linalg.solve(p.conj().T@a@p,x),e,result)
    assert coarse['decomposition_relative_defect']<1e-12
    assert coarse['coarse_identity_relative_field_error']<1e-12
    assert coarse['unit_field_ratio'] >= result['eta_space']-1e-12
    np.testing.assert_allclose(coarse['applied_direction'],a@coarse['dg'])
    assert coarse['unit_field_ratio']**2==pytest.approx(coarse['unit_remaining_energy']/coarse['original_error_energy'])
    exact=project_error(lambda x:p@x,adj,m,np.diag(cmat),p@np.array([2j,1]),max_it=256)
    assert exact['eta_space']<1e-11
    failed=project_error(lambda x:p@x,adj,m,np.diag(cmat),e,max_it=0)
    assert failed['status']=='PROJECTION_UNRESOLVED' and failed['interpretation'].endswith('upper bound only')
    np.testing.assert_array_equal(e,before)


def test_borrowed_components_and_dual_input_have_no_invented_field_error():
    work=np.empty(3,complex)
    def component(scale):
        def apply(x):
            work[:]=scale*x
            return work
        return apply
    x=np.array([1,2j,3+1j]); before=x.copy()
    result=component_diagnostics({'K':component(2),'mass':component(-1j)},x)
    np.testing.assert_allclose(result['gram'][0,1],np.vdot(2*x,-1j*x))
    result=evaluate_residual_profiles(lambda x:2*x,lambda x:3*x,x,{'exact':lambda q:q/2})
    assert result['profiles']['exact']['true_residual_ratio']==0
    assert result['profiles']['exact']['remaining_field_error']=='UNAVAILABLE_NO_REFERENCE'
    assert result['profiles']['exact']['correction_field_norm']==pytest.approx(np.sqrt(3)/2)
    np.testing.assert_allclose(result['profiles']['exact']['applied_direction'],result['normalized_q'])
    q=x/np.linalg.norm(x)
    assert homogeneity_check(q,{'exact':q/2},{'exact':lambda x:x/2})['exact']['relative_error']==0
    np.testing.assert_array_equal(x,before)
    with pytest.raises(ValueError):
        metric_square(lambda x:1j*x,x)
    with pytest.raises(ValueError):
        component_diagnostics({'bad':lambda x:np.full(3,np.nan)},x)


@pytest.mark.parametrize('kind,limit',[('diagnosis',7200),('reference',3600)])
def test_both_parents_enable_clock_guard(tmp_path,monkeypatch,kind,limit):
    from src.runners.physical_diagnosis import supervise_diagnosis
    from benchmarks import subreaper_watchdog
    from src.runners import task038_launcher
    monkeypatch.setattr(task038_launcher,'_physical_source_gate',lambda *args:{'source_sha':'a'*40})
    def supervise(command,directory,**kwargs):
        assert kwargs['timebase_guard'] is True and kwargs['hard_stop_immediate'] is True
        assert kwargs['wall_seconds']==limit
        return {}
    monkeypatch.setattr(subreaper_watchdog,'supervise',supervise)
    supervise_diagnosis(['reviewed_command'],tmp_path,phase_path=tmp_path/'phase',
                        expected_sha='a'*40,kind=kind,remaining_seconds=10000)


def test_tiny_lossless_fe_mass_diagonal_and_cell_energy():
    from dataclasses import replace
    from mpi4py import MPI
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.physical_error_metric import LosslessFEMetric,interpolate_known_error
    cfg=replace(target_stage4_config(degree=2,h_nm=100),
        period_x=20.,period_y=15.,grating_width_x=8.,grating_width_y=15.,
        grating_height=2.,z_min=-1.,z_max=3.,air_height=3.,substrate_thickness=1.,
        mesh_cell_type='hexahedron',mesh_spacing_mode='boundary_fitted',mesh_axis_cell_counts=(3,2,3),
        incident_theta_deg=74.,incident_phi_deg=17.,n_substrate=1.4+.05j,n_grating=.9+.02j)
    levels=_build_same_mesh_levels(cfg,MPI.COMM_WORLD,(2,))
    metric=LosslessFEMetric(levels,2,cfg.k0,({'quadrature_degree':6},{'quadrature_degree':6}))
    try:
        rng=np.random.default_rng(39)
        x=rng.normal(size=metric.mass.indices.size)+1j*rng.normal(size=metric.mass.indices.size)
        before=x.copy()
        energy=metric.cell_energies(x)
        assert sum(energy['mass'])==pytest.approx(metric_square(metric.mass,x),rel=1e-11)
        assert sum(energy['curl'])==pytest.approx(metric_square(metric.curl,x),rel=1e-11)
        diagonal=metric.diagonal()
        for i in [0,len(diagonal)//2,len(diagonal)-1]:
            unit=np.zeros_like(x);unit[i]=1
            assert diagonal[i]==pytest.approx(metric.mass(unit)[i].real,rel=1e-11)
        assert metric.actions['mass'].audit['slave_row_identity'] is False
        known=interpolate_known_error(levels['spaces'][2],levels['floquets'][2],cfg,metric.mass.indices)
        assert metric_square(metric.mass,known)>0
        np.testing.assert_array_equal(x,before)
    finally:
        metric.destroy()
        levels.clear()


def test_projection_budget_skips_actions_when_exhausted():
    from src.runners.physical_diagnosis import DiagnosticActions
    actions=DiagnosticActions.__new__(DiagnosticActions)
    actions.timebase_policy='strict'
    actions.projection_seconds=1800.
    result=actions.project(np.ones(2))
    assert result['status']=='PROJECTION_UNRESOLVED' and result['parallel'] is None
