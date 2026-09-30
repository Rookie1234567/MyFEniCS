"""Small non-Hermitian algebra and wrong-identity counterexamples; no FE."""
from types import MappingProxyType

import numpy as np
import pytest

from src.solvers.orthonormal_trace_reprofile import (
    OrthonormalTraceBasis, manufactured_witness, comparison_margin, ray_identity,
)
from src.solvers.stable_head_varpro import PortBlocks
from src.runners.task042_shared import write_json


class Packet:
    def __init__(self):
        rng=np.random.default_rng(421400)
        self.nt,self.np=24,40;self.size=64
        self.matrix=rng.normal(size=(64,64))+1j*rng.normal(size=(64,64))
        self.matrix+=30*np.eye(64)
        self.a=dict(Hhat=self.matrix[24:,24:],b=rng.normal(size=64)+1j*rng.normal(size=64))
        self.particular=rng.normal(size=71)+1j*rng.normal(size=71)
        self.recovery=rng.normal(size=(71,64))+1j*rng.normal(size=(71,64))
        self.counts=dict(S=0,SH=0)
    def apply(self,z,adjoint=False):
        self.counts['SH' if adjoint else 'S']+=1
        return (self.matrix.conj().T if adjoint else self.matrix)@z
    def recover(self,z):
        return self.particular+self.recovery@z


def basis(reverse=False,saved=None):
    packet=Packet();rng=np.random.default_rng(421402)
    P=(rng.normal(size=(24,5))+1j*rng.normal(size=(24,5))).astype(np.complex128)
    ports=PortBlocks(packet,packet.matrix[:,24:])
    b=OrthonormalTraceBasis(packet,P,ports,reverse_rows=reverse,saved_A=saved,expected_columns=5)
    return packet,P,b


def test_direct_Qc_nonhermitian_complete_ports_and_manufacture():
    packet,_,b=basis(); original=packet.a['b'].copy()
    rng=np.random.default_rng(421401)
    c=rng.normal(size=5)+1j*rng.normal(size=5)
    port=rng.normal(size=40)+1j*rng.normal(size=40)
    known=np.r_[b.Q@c,port]
    answer,rhs,row=manufactured_witness(b,known,'ORTHO-M1')
    assert row['qualified'] and np.linalg.norm(rhs[24:])>0
    assert np.array_equal(packet.a['b'],original)
    assert np.allclose(answer['trace'],b.Q@answer['c'])
    assert row['homogeneous_recovery_operation_relative']<1e-12
    wrong_rhs=rhs.copy();wrong_rhs[24:]=original[24:]
    wrong=b.solve(wrong_rhs)
    assert np.linalg.norm(wrong['z']-known)/np.linalg.norm(known)>1e-3


def test_reversed_Q_restores_canonical_order_and_same_space():
    packet,P,b=basis();reverse=OrthonormalTraceBasis(packet,P,b.ports,reverse_rows=True,expected_columns=5)
    x=b.solve(packet.a['b']);y=reverse.solve(packet.a['b'])
    assert np.linalg.norm(x['z']-y['z'])<1e-12
    assert reverse.decomposition()['reverse_row_QR']
    reverse.Q=reverse.Q[::-1].copy()  # Deliberately wrong physical row order.
    assert not reverse.solve(packet.a['b'])['numeric']['decoder_gate']


def test_old_A_different_Q_detected_and_rebuilt_once():
    packet,P,b=basis(); counts=[]
    wrong=OrthonormalTraceBasis(packet,P,b.ports,saved_A=-b.A,
        count=lambda key,n=1:counts.append((key,n)),expected_columns=5)
    assert wrong.saved_A_rejected and wrong.fresh_A_columns==5
    assert counts.count(('basis_evaluations',1))==2
    assert wrong.solve(packet.a['b'])['numeric']['decoder_gate']


def test_matching_cached_A_checks_three_columns_and_two_combinations():
    _,_,b=basis();packet,P,other=basis(saved=b.A)
    assert len(other.pairing)==5 and max(other.pairing)<1e-12
    assert other.fresh_A_columns==0
    assert other.solve(packet.a['b'])['numeric']['rank_A']==5


def test_rank_and_column_inventory_cannot_be_relaxed():
    packet,P,b=basis();P[:,1]=P[:,0]
    with pytest.raises(ValueError,match='rank'):
        OrthonormalTraceBasis(packet,P,b.ports,expected_columns=5)
    with pytest.raises(ValueError,match='inventory'):
        OrthonormalTraceBasis(packet,P,b.ports,expected_columns=4)


def test_margin_observed_basis_uncertainty_and_ray_identity():
    assert comparison_margin(dict(delta_i=1e-14),dict(delta_i=2e-14),3e-7)==pytest.approx(3e-5)
    p=np.arange(12,dtype=float);v=np.linspace(0,1,12)
    assert ray_identity(p,p+v,p+v/64,1/64)['consistent']
    assert not ray_identity(p,p+v,p+v/60,1/64)['consistent']


def test_numeric_and_physical_mapping_are_distinct_and_atomic(tmp_path):
    path=tmp_path/'record.json'
    write_json(path,dict(numeric=dict(Phi=.3),physical_identity=MappingProxyType({'Phi':'identity_label'})))
    import json
    row=json.loads(path.read_text())
    assert row['numeric']['Phi']==.3 and row['physical_identity']['Phi']=='identity_label'
    with pytest.raises(ValueError):
        write_json(path,dict(numeric=dict(Phi=float('nan'))))
    assert json.loads(path.read_text())==row


def test_reference_feedback_barrier_rejects_solver_records(tmp_path,monkeypatch):
    import src.io.orthonormal_trace_reprofile as module
    from src.solvers.neural_fe_action_packet import file_hash
    import json
    plan=tmp_path/'plan.json';plan.write_text('{}')
    result=tmp_path/'result.json';result.write_text(json.dumps(dict(
        plan_sha256=file_hash(plan),reference_arrays_read=True)))
    (tmp_path/'PROFILE.json').write_text(json.dumps(dict(path=str(result),sha256=file_hash(result))))
    monkeypatch.setattr(module,'V14_ROOT',tmp_path);monkeypatch.setattr(module,'PLAN_PATH',plan)
    with pytest.raises(ValueError,match='reference barrier'):
        module.read_result('PROFILE')


def test_port_inventory_is_complete():
    packet,_,b=basis()
    with pytest.raises(ValueError,match='forty'):
        PortBlocks(packet,b.ports.columns[:,:39])
