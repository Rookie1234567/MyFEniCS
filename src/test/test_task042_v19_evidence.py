"""Budget and stored-status counterexamples for the V19 read-only checker."""
import copy
import numpy as np
import pytest
from src.io.post_lsqr_polish_check import caps,state_check
from src.solvers.neural_fe_action_packet import array_hash,file_hash

def safe_ledger():
    r=dict(wall_seconds=2300.,actions_upper=19400,new_updates=63)
    return dict(closed=True,active=None,actions_upper=79900,audits_upper=299,new_A_columns=0,
        image_QR=0,field_states=10,reentries=0,cooldown_seconds=0.,repairs=[],
        routes={**{a+'_'+f:copy.deepcopy(r) for a in ('P','L') for f in ('GPOLY','GNN')},
                **{f:dict(reentries=0) for f in ('GPOLY','GNN')}})

@pytest.mark.parametrize('key,value',[('actions_upper',80001),('audits_upper',301),('new_A_columns',1),
    ('image_QR',1),('field_states',13),('reentries',4),('cooldown_seconds',float('nan')),('closed',False),('active',dict(live=True))])
def test_batch_cap_and_closed_status(key,value):
    ledger=safe_ledger();budget=dict(uniform_route_wall_seconds=2382)
    assert caps(ledger,budget);ledger[key]=value;assert not caps(ledger,budget)

@pytest.mark.parametrize('key,value',[('wall_seconds',2383.),('wall_seconds',float('nan')),('actions_upper',19501),
    ('new_updates',65),('new_updates',-1)])
def test_method_library_budget(key,value):
    ledger=safe_ledger();ledger['routes']['L_GNN'][key]=value
    assert not caps(ledger,dict(uniform_route_wall_seconds=2382))

def test_physical_saved_vector_not_callback_or_fake_status(tmp_path):
    trace=np.full(18144,1+2j);port=np.full(40,3-1j);z=np.r_[trace,port];residual=np.full(18184,1e-4+1e-5j)
    path=tmp_path/'state.npz';np.savez(path,trace=trace,port=port,z=z,residual=residual)
    row=dict(state=dict(path=str(path),sha256=file_hash(path),z_sha256=array_hash(z)),
        audit=dict(schur_relative=np.linalg.norm(residual)/10))
    checked,arrays=state_check(row,10.);assert checked['Q_U_R_GK_loaded'] is False
    row['audit']['schur_relative']=0.
    with pytest.raises(ValueError,match='saved Schur'):state_check(row,10.)
    row.pop('audit');z[0]+=1.;np.savez(path,trace=trace,port=port,z=z,residual=residual)
    with pytest.raises(ValueError,match='file hash'):state_check(row,10.)
    row['state']['sha256']=file_hash(path);row['state'].pop('z_sha256')
    with pytest.raises(ValueError,match='composition'):state_check(row,10.)
