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
