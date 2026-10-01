"""Counterexamples for the reader: budgets, closed shape and saved-status lies."""
import copy

import numpy as np
import pytest

from src.io.gmres_residual_completion_check import caps, close_qualified
from src.io.resumable_trace_evidence_check import frozen_state
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def closed_ledger():
    route = dict(wall_seconds=9999., G_wall_seconds=1799., actions_upper=27999,
                 new_updates=10300, arnoldi_upper=dict(G64=1024, G256=2048),
                 reentries=0, correction_restarts=0)
    return dict(active=None, closed=True, actions_upper=65999, audits_upper=511,
                new_A_columns=0, image_QR=0, field_states=8, reentries=0,
                cooldown_seconds=0., repairs=[], routes={k:copy.deepcopy(route) for k in ('GPOLY','GNN')})


@pytest.mark.parametrize('key,value', [('actions_upper',66001), ('actions_upper',-1),
    ('audits_upper',513), ('field_states',13), ('cooldown_seconds',float('nan')),
    ('active',{'live':True}), ('closed',False)])
def test_reader_rejects_unsafe_campaign(key,value):
    item=closed_ledger();budget=dict(uniform_route_wall_seconds=10000,GMRES_total_ceiling_seconds=1800)
    assert caps(item,budget)
    item[key]=value
    assert not caps(item,budget)


@pytest.mark.parametrize('key,value', [('wall_seconds',10001.), ('G_wall_seconds',1801.),
    ('wall_seconds',float('nan')), ('actions_upper',-1), ('new_updates',10301), ('reentries',3)])
def test_reader_rejects_library_overrun(key,value):
    item=closed_ledger();item['routes']['GPOLY'][key]=value
    assert not caps(item,dict(uniform_route_wall_seconds=10000,GMRES_total_ceiling_seconds=1800))


def test_close_qualification_uses_full_shapes_and_independent_numbers():
    row=dict(shape=dict(trace=18144,port=40,z=18184),original_closed_identity_relative=1e-12,
             saved_vs_original_residual_full_b_relative=1e-12,port_difference_operation_relative=1e-14,
             audit=dict(port_operation_relative=1e-14,recovery_relative=1e-13,
                        schur_original_identity_operation_relative=1e-13,slave_storage_max=0.))
    assert close_qualified(row)
    duplicate=copy.deepcopy(row);duplicate['shape']['z']=36328
    assert not close_qualified(duplicate)
    row['audit']['port_operation_relative']=1e-9
    assert not close_qualified(row)


def test_frozen_vector_rejects_hash_composition_and_residual_status_lies(tmp_path):
    trace=np.ones(18144,dtype=np.complex128)*(1+2j);port=np.ones(40,dtype=np.complex128)*(3-1j)
    z=np.r_[trace,port];residual=np.ones(18184,dtype=np.complex128)*1e-4
    path=tmp_path/'state.npz';np.savez(path,trace=trace,port=port,z=z,residual=residual)
    source=dict(state=dict(path=str(path),sha256=file_hash(path),z_sha256=array_hash(z)),
                audit=dict(schur_relative=np.linalg.norm(residual)/10.))
    assert frozen_state(source,10.)['actual_z_composition']
    source['audit']['schur_relative']=0.
    with pytest.raises(ValueError,match='saved Schur'):frozen_state(source,10.)
    source.pop('audit');z[0]+=1.;np.savez(path,trace=trace,port=port,z=z,residual=residual)
    with pytest.raises(ValueError,match='file hash'):frozen_state(source,10.)
    source['state']['sha256']=file_hash(path);source['state'].pop('z_sha256')
    with pytest.raises(ValueError,match='composition'):frozen_state(source,10.)
