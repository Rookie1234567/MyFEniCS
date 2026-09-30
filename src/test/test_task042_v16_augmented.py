"""Small non-Hermitian witnesses, outside-Q solutions and negative controls."""
import numpy as np
import pytest
from scipy.linalg import qr

from src.solvers.augmented_trace_lsqr import BarAction, ProjectedTraceOperator, ThinBasis, projected_checks
from src.solvers.bounded_complex_lsqr import lsqr_steps
from src.solvers.stable_head_varpro import PortBlocks, homogeneous_recovery_pair


class Packet:
    def __init__(self, S):
        self.S, self.nt, self.np, self.size = S, S.shape[0]-40, 40, S.shape[0]
        self.a = dict(Hhat=S[self.nt:,self.nt:])
        self.particular = np.ones(self.size, complex)*(2+3j)
        self.counts = dict(S=0, SH=0)
    def apply(self, x, adjoint=False):
        self.counts['SH' if adjoint else 'S']+=1
        return (self.S.conj().T if adjoint else self.S)@x
    def recover(self, x):
        return self.particular+np.r_[x[:self.nt]*2, x[self.nt:]*3]


def problem(nonempty):
    rng=np.random.default_rng(421601)
    S=rng.normal(size=(52,52))+1j*rng.normal(size=(52,52));S+=40*np.eye(52)
    packet=Packet(S);ports=PortBlocks(packet,S[:,-40:]);bar=BarAction(ports)
    q=qr(rng.normal(size=(12,3))+1j*rng.normal(size=(12,3)),mode='economic')[0] if nonempty else np.empty((12,0),complex)
    Q=ThinBasis(12,[q] if nonempty else [])
    A=np.column_stack([bar.apply(q[:,j]) for j in range(3)]) if nonempty else np.empty((12,0),complex)
    U,R=qr(A,mode='economic')
    op=ProjectedTraceOperator(bar,Q,ThinBasis(12,[U] if nonempty else []),R)
    exact=rng.normal(size=52)+1j*rng.normal(size=52);rhs=packet.apply(exact)
    return op,exact,rhs


@pytest.mark.parametrize('nonempty',[False,True])
def test_small_full_space_and_ports(nonempty):
    op, exact, rhs=problem(nonempty)
    assert np.linalg.norm(op.pt(exact[:12]))>.1
    assert np.linalg.norm(rhs[12:])>1
    assert projected_checks(op,rhs)['qualified']
    y=np.zeros(12,complex)
    for k,y,_ in lsqr_steps(op.apply,op.adjoint,op.rhs(rhs)):
        if k>=80 or np.linalg.norm(op.apply(y)-op.rhs(rhs))<1e-12:break
    point=op.restore(y,rhs)
    assert np.linalg.norm(point['z']-exact)/np.linalg.norm(exact)<1e-10
    assert np.linalg.norm(op.bar.packet.apply(point['z'])-rhs)/np.linalg.norm(rhs)<1e-10
    assert homogeneous_recovery_pair(op.bar.packet,exact,point['z'])<1e-10
    r=np.arange(12)+1j*np.arange(12)[::-1]
    before=op.bar.packet.counts['SH'];actual=op.bar.adjoint(r)
    assert op.bar.packet.counts['SH']==before+1
    assert np.allclose(actual,op.bar.ports.adjoint(r),atol=1e-11)


def test_negative_controls_detect_missing_projection_wrong_adjoint_and_Q_U():
    op,_,rhs=problem(True);rng=np.random.default_rng(42)
    explicit=np.column_stack([op.apply(np.eye(12,dtype=complex)[:,j]) for j in range(12)])
    no_pt=np.column_stack([op.pr(op.bar.apply(np.eye(12,dtype=complex)[:,j])) for j in range(12)])
    # Pr eliminates A Q, so omitting Pt in the forward is algebraically
    # equivalent in exact arithmetic; the adjoint must nevertheless use Pt.
    assert np.allclose(explicit,no_pt,atol=1e-10)
    r=rng.normal(size=12)+1j*rng.normal(size=12)
    assert np.linalg.norm(op.bar.adjoint(op.pr(r))-op.adjoint(r))<1e-10
    # Detect omission in restoration rather than inventing a false counterexample.
    y=op.Q.forward(np.ones(3,complex))+op.pt(r)
    assert np.linalg.norm(y-op.pt(y))>.1
    assert np.linalg.norm(explicit.T@r-op.adjoint(r))>1
    mixed=ProjectedTraceOperator(op.bar,op.Q,op.Q,op.R)
    assert not projected_checks(mixed,rhs)['qualified']


def test_callback_exposes_completed_state_without_changing_legacy_recurrence():
    op,_,rhs=problem(False);f=op.rhs(rhs)
    old=lsqr_steps(op.apply,op.adjoint,f);states=[]
    new=lsqr_steps(op.apply,op.adjoint,f,state_callback=states.append)
    for _ in range(10):
        a,b=next(old),next(new)
        assert a[0]==b[0] and a[2]==b[2]
        assert np.array_equal(a[1],b[1])
        assert np.array_equal(states[-1]['x'],b[1])


def test_physical_rhs_identity_retains_fixed_denominator_and_nonzero_witness():
    op, _, rhs=problem(True)
    tiny_rhs=rhs*1e-9
    checks=projected_checks(op,tiny_rhs)
    assert checks['qualified']
    assert checks['residual_witness_scale']>0
    assert checks['residual_witness_complement_norm']>0
    assert checks['original_residual_identity_relative']<=1e-8


def test_supervisor_metadata_accepts_frozen_route_budget_without_strings():
    import json
    from types import MappingProxyType
    from src.runners.task042_shared import _json_metadata
    original=MappingProxyType(dict(route_budget=MappingProxyType(dict(uniform_route_wall_seconds=2700))))
    value=json.loads(json.dumps(_json_metadata(original),allow_nan=False))
    assert value=={'route_budget':{'uniform_route_wall_seconds':2700}}


def test_explicit_five_inputs_preserve_original_physics_and_reference_barrier(tmp_path,monkeypatch):
    from src.io import augmented_trace_lsqr as io
    from src.io.input_loader import InputError
    # Isolate both pre-VERIFY parsing and the deliberately closed queue from
    # the real batch's immutable post-reference marker.
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path)
    stages=['complement_preflight','closed_lsqr_zero','augmented_gpoly','augmented_gnn','verify']
    cases=[io.load_augmented_trace('input/task042_neural_coarse_inverse/v16_'+n+'.dat') for n in stages]
    assert len({c.physical_model_sha256 for c in cases})==1
    assert all(c.execution['mpi_size']==1 and c.execution['terminate_memory_gib']==16 for c in cases)
    assert [c.derived['environment_mode'] for c in cases]==['pure']*4+['fe']
    monkeypatch.setattr(io,'ARTIFACT_ROOT',tmp_path)
    (tmp_path/'VERIFY.json').write_text('{}')
    with pytest.raises(InputError,match='queue closed'):
        io.load_augmented_trace('input/task042_neural_coarse_inverse/v16_closed_lsqr_zero.dat')


def test_uniform_route_budget_freezes_once_and_never_refreshes(monkeypatch,tmp_path):
    from src.solvers import augmented_trace_window as w
    monkeypatch.setattr(w,'BUDGET_PATH',tmp_path/'route.json')
    monkeypatch.setattr(w,'JOURNAL_PATH',tmp_path/'journal.jsonl')
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=6600))
    first=w.freeze_route_budget()
    assert first['uniform_route_wall_seconds']==2000
    monkeypatch.setattr(w,'snapshot',lambda:dict(heavy_remaining_seconds=10000))
    assert w.freeze_route_budget()==first
