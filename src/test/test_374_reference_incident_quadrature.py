"""Reference-only RHS wiring and saved-array checks; no mesh or PDE."""
import inspect
from types import SimpleNamespace
import numpy as np
import pytest

from src.solvers.condensed_fine_reference import project_unconstrained_mpc_dual,pre_numeric_rhs_gate


@pytest.mark.parametrize('enabled',[False,True])
def test_incident_assembly_default_and_explicit_native_degree(monkeypatch,enabled):
    from src.solvers import dtn_port_3d as dtn
    form=object();calls=[]
    monkeypatch.setattr(dtn,'_incident_top_traction_form',lambda *args:form)
    monkeypatch.setattr(dtn,'_assemble_unconstrained_vector',lambda value,**kw:calls.append((value,kw)))
    options={'diagnostic_reference_incident_quadrature':True} if enabled else {}
    dtn._assemble_assembly_time_incident_traction(None,None,None,dtn_quadrature_degree=25,**options)
    assert calls==[(form,{'quadrature_degree':25} if enabled else {})]


@pytest.mark.parametrize('enabled',[False,True])
def test_public_wrapper_forwards_default_off_flag(monkeypatch,enabled):
    from src.solvers import solve_maxwell_3d_stage_4b_block_grating as stage
    from src.solvers.common_3d_case_flow import run_prepared_3d_case_flow
    from src.solvers.dtn_port_3d import solve_stage4_dtn_port_total_field
    flag='diagnostic_reference_incident_quadrature';seen={}
    for function in (stage.run_stage4b_block_grating_3d_case,run_prepared_3d_case_flow,solve_stage4_dtn_port_total_field):
        assert inspect.signature(function).parameters[flag].default is False
    monkeypatch.setattr(stage,'run_prepared_3d_case_flow',lambda *args,**kw:seen.update(kw))
    stage.run_stage4b_block_grating_3d_case(SimpleNamespace(stage_case='stage4_block_grating'),None,
        **({flag:True} if enabled else {}))
    assert seen[flag] is enabled


class _PassedIncidentQuadratureGuard(Exception):
    pass


def _p6_fixed_p_guard_config():
    from src.runners import pstddm_p6_convergence as p6
    from src.solvers.pstddm_material import derive_si_optical_identity

    return p6.build_p6_config(
        {"case_id": "p6_h10_direct_13p5_retry3", "h_nm": 10.0},
        derive_si_optical_identity(13.5),
    )


def _call_stage4_impl_until_guard(dtn, cfg, output, *, linear_solver_port=None):
    def stop_after_guard(_message):
        raise _PassedIncidentQuadratureGuard

    return dtn.solve_stage4_dtn_port_total_field(
        a=None,
        L=None,
        V=None,
        mesh_data=None,
        cfg=cfg,
        floquet_data=object(),
        petsc_options={},
        out_dir=output,
        log=stop_after_guard,
        started=0.0,
        linear_solver_port=linear_solver_port,
        diagnostic_reference_incident_quadrature=True,
    )


def test_p6_runner_reaches_fixed_p_direct_incident_quadrature_guard(monkeypatch, tmp_path):
    from src.runners import pstddm_p6_convergence as p6
    from src.solvers import solve_maxwell_3d_stage_4b_block_grating as stage
    from src.solvers import dtn_port_3d as dtn

    cfg = _p6_fixed_p_guard_config()
    observer = object()

    def prepared_flow(received_cfg, received_output, **kwargs):
        assert kwargs["diagnostic_reference_incident_quadrature"] is True
        assert kwargs["solution_observer"] is observer
        return _call_stage4_impl_until_guard(dtn, received_cfg, received_output)

    monkeypatch.setattr(stage, "run_prepared_3d_case_flow", prepared_flow)
    with pytest.raises(_PassedIncidentQuadratureGuard):
        p6._run_p6_stage4_solver(cfg, tmp_path, observer)


def test_fixed_p_external_assembled_incident_quadrature_reaches_guard(tmp_path):
    from src.solvers import dtn_port_3d as dtn

    cfg = _p6_fixed_p_guard_config()
    with pytest.raises(_PassedIncidentQuadratureGuard):
        _call_stage4_impl_until_guard(
            dtn, cfg, tmp_path, linear_solver_port=lambda _request: None,
        )


@pytest.mark.parametrize("backend_kind", ["variable_p", "nonassembled", "action_only"])
def test_incident_quadrature_guard_rejects_variable_or_unassembled_paths(
    monkeypatch, tmp_path, backend_kind,
):
    from dataclasses import replace
    from src.common.config_3d import (
        ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
        STANDARD_FULL_ASSEMBLY_BACKEND,
    )
    from src.solvers import dtn_port_3d as dtn

    cfg = _p6_fixed_p_guard_config()
    linear_solver_port = None
    if backend_kind == "variable_p":
        cfg = replace(
            cfg,
            stage4_full3d_assembly_backend=ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
        )
        linear_solver_port = lambda _request: None
        # This fixture isolates the incident-quadrature guard. The minimal p6
        # config intentionally lacks the geometry-bound variable-p degree plan,
        # so bypass only that earlier qualification gate while keeping backend
        # resolution and the real solver implementation active.
        monkeypatch.setattr(
            dtn,
            "qualify_stage4_full3d_assembly_backend",
            lambda _cfg, _audit: {"status": "fixture-qualified"},
        )
    elif backend_kind == "nonassembled":
        cfg = replace(
            cfg,
            stage4_full3d_assembly_backend=STANDARD_FULL_ASSEMBLY_BACKEND,
            stage4_cell_static_condensation=False,
            stage4_assembly_time_cell_static_condensation=False,
            stage4_floquet_slave_elimination=False,
        )
    else:
        linear_solver_port = dtn.Stage4NeverMaterializedLinearSolverPort(
            lambda _request: None,
        )

    with pytest.raises(ValueError, match="materialized fixed-p assembly-time"):
        _call_stage4_impl_until_guard(
            dtn, cfg, tmp_path, linear_solver_port=linear_solver_port,
        )


def example():
    mapping=dict(slaves=np.array([1,3]),masters=np.array([0,2]),offsets=np.array([0,0,1,1,2]),
                 coefficients=np.array([1j,np.exp(.3j)]),independent_indices=np.array([0,2]))
    value=np.array([1+2j,3-1j,2-1j,-2+1j])
    expected=np.array([value[0]-1j*value[1],0,value[2]+np.exp(-.3j)*value[3],0])
    return mapping,value,expected


def test_complex_phase_dual_projection_is_adjoint_and_input_unchanged():
    mapping,value,expected=example();before=value.copy()
    np.testing.assert_allclose(project_unconstrained_mpc_dual(value,mapping),expected,rtol=1e-15)
    np.testing.assert_array_equal(value,before)
    mapping['masters'][0]=1
    with pytest.raises(ValueError):project_unconstrained_mpc_dual(value,mapping)


@pytest.mark.parametrize('failure',[None,'rhs','degree','map'])
def test_pre_numeric_gate_saves_and_blocks_wrong_load(failure):
    mapping,value,expected=example();seen=[]
    witness=dict(map={k:v.copy() for k,v in mapping.items()},rhs={'b':expected[[0,2]].copy()},evidence={'tiny':True})
    if failure=='rhs':witness['rhs']['b'][0]+=.01
    if failure=='map':witness['map']['coefficients'][0]=1
    def run():return pre_numeric_rhs_gate(value,mapping,witness,None if failure=='degree' else 25,25,
        lambda name,facts:seen.append((name,facts)))
    if failure:
        with pytest.raises(ValueError):run()
        assert seen and seen[-1][1]['status']!='RHS_PASS'
    else:
        assert run()['status']=='RHS_PASS'
        np.testing.assert_allclose(seen[0][1]['projected_full_rhs'],expected)
