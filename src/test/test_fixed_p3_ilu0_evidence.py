"""Mutation checks for the post-run reader, without another FE computation."""
from copy import deepcopy
import numpy as np
import pytest
from src.io.fixed_p3_ilu0_check import capacity_gate, campaign_gate, pc_gate, port_gate, right_state
from src.solvers.neural_fe_action_packet import array_hash


def test_right_variable_is_not_physical_trace():
    previous = np.array([1+2j, 3-4j]); y = np.array([2j, -1j]); By = 2*y
    arrays = dict(y=y, By=By, trace=previous+By)
    row = dict(identity=dict(parent_trace_sha256=array_hash(previous), pc_kind='B0'),
               state=dict(y_sha256=array_hash(y), By_sha256=array_hash(By)), right_variable_is_trace=False)
    right_state(row, arrays, previous)
    with pytest.raises(ValueError, match='plus By'): right_state(row, dict(arrays, trace=previous+y), previous)
    with pytest.raises(ValueError, match='previous physical'): right_state(row, arrays, previous+1)
    with pytest.raises(ValueError, match='array hash'): right_state(row, dict(arrays, By=By+1), previous)


def test_native_ilu_configuration_is_checked_not_name():
    effective = dict(specification=dict(type='ilu', levels=0, ordering='natural', shift='NONE', communicator='COMM_SELF',
        matrix='seqaij', out_of_place=True, drop=None, diagonal_rescue=False), effective_type='ilu', effective_matrix_type='seqaij',
        scalar='complex128', integer='int64', effective_Levels=0, effective_ShiftType=0, external_options_applied=False)
    row = dict(effective=effective, repeat=dict(operation_relative=0), complex_linearity=dict(operation_relative=1e-14))
    assert pc_gate(row)
    for key, value in [('levels', 1), ('ordering', 'rcm'), ('shift', 'NONZERO'), ('drop', 1e-4)]:
        bad=deepcopy(row); bad['effective']['specification'][key]=value; assert not pc_gate(bad)
    bad=deepcopy(row); bad['complex_linearity']['operation_relative']=float('nan'); assert not pc_gate(bad)
    bad=deepcopy(row); bad['cross_process_pairs']=[dict(operation_relative=2e-10)]; assert not pc_gate(bad)


def test_capacity_and_port_are_independent_of_claimed_status():
    c=dict(contribution_nnz_upper=100, csr_bytes_upper=1000, factor_explicit_payload_upper_bytes=2000,
           simultaneous_planning_upper_bytes=3000, qualified=True)
    assert capacity_gate(c)
    assert not capacity_gate(dict(c, simultaneous_planning_upper_bytes=9*2**30))
    p=dict(cond2=2e6, solve_operation_relative=1e-16, W_payload_bytes=18144*40*16,
           H_is_Hhat=True, F_is_C_adjoint_assumed=False)
    assert port_gate(p)
    assert not port_gate(dict(p, cond2=2e10))
    assert not port_gate(dict(p, F_is_C_adjoint_assumed=True))


def test_campaign_counter_and_wall_limits_do_not_reset():
    l=dict(active=None, closed=True, charged=dict(actions=3193, audits=23, B0=2124, F=1080,
           K_assemblies=1, factor_setups=3, field_states=5), reentries=0, cooldown_seconds=0, repairs=[],
           routes=dict(P0=dict(wall_seconds=281)))
    assert campaign_gate(l)
    for key,value in [('actions',35001), ('factor_setups',6), ('audits',121)]:
        bad=deepcopy(l); bad['charged'][key]=value; assert not campaign_gate(bad)
    assert not campaign_gate(dict(l, active={'stage':'P0'}))
    assert not campaign_gate(dict(l, routes=dict(P0=dict(wall_seconds=1201))))
