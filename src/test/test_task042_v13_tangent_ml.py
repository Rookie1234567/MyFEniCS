"""Small independent hand-forward/complex backward witnesses, CPU ML only."""

import tempfile
from pathlib import Path

import numpy as np
import torch

from src.solvers.neural_trace_tangent import layerwise_envelopes,parameter_direction,moment_tangent,dot_pair
from src.solvers.neural_trace_torch import NeuralTrace
from src.solvers.neural_linear_head_torch import assign_head,build_head_mapping,head_coefficients
from src.solvers.neural_trace_checks import parameters,assign
from src.solvers.stable_head_varpro_torch import hidden_vector,set_hidden
from src.solvers.neural_trace_batched import BatchedMoments


def example():
    rng=np.random.default_rng(421403)
    model=NeuralTrace(np.array([[-1,1]]*3),.7)
    gamma=.01*(rng.normal(size=1560)+1j*rng.normal(size=1560));assign_head(model,gamma)
    d=rng.normal(size=8576);d/=np.linalg.norm(d)
    dg=.003*(rng.normal(size=1560)+1j*rng.normal(size=1560))
    x=torch.tensor(rng.normal(size=(6,3))*.2,dtype=torch.float64)
    return model,gamma,d,dg,x


def test_layerwise_joint_tangent_independent_backward_and_fd():
    model,gamma,d,dg,x=example();tangent_parameter=parameter_direction(d,dg)
    with torch.no_grad():
        value,tangent=layerwise_envelopes(model,x,tangent_parameter)
    assert torch.linalg.norm(value-model.envelopes(x)).item()<1e-14
    rng=np.random.default_rng(421404);q=torch.tensor(rng.normal(size=(6,48)),dtype=torch.float64)
    model.zero_grad();torch.sum(q*model.envelopes(x)).backward()
    grad=np.concatenate([p.grad.numpy().ravel() for p in model.parameters()])
    left=float(torch.sum(q*tangent));right=float(np.dot(grad,tangent_parameter))
    scale=max(np.linalg.norm(q.numpy())*np.linalg.norm(tangent.numpy()),np.linalg.norm(grad)*np.linalg.norm(tangent_parameter))
    assert abs(left-right)/scale<1e-12
    initial=parameters(model);h=1e-5
    with torch.no_grad():
        assign(model,initial+h*tangent_parameter);plus=model.envelopes(x).numpy().copy()
        assign(model,initial-h*tangent_parameter);minus=model.envelopes(x).numpy().copy()
    assert np.linalg.norm((plus-minus)/(2*h)-tangent.numpy())/np.linalg.norm(tangent.numpy())<1e-7
    assign(model,initial)


def test_full_moment_joint_tangent_and_complex_dual():
    model,gamma,d,dg,_=example();rng=np.random.default_rng(421405)
    packet=dict(active_rows=np.array(3),reference_points=rng.uniform(-.2,.2,size=(4,3)),
                interpolation=rng.normal(size=(3,12)),transforms=np.array([np.eye(3),np.diag([-1,1,-1])]),
                jacobians=np.array([np.diag([.2,.3,.4])]),origins=np.array([[.1,.05,-.1]]),
                owner_rows=np.array([[0,1,2]]),orientation_ids=np.array([1]))
    cache=BatchedMoments(model,packet)
    value,dt=moment_tangent(model,cache,d,dg)
    assert np.linalg.norm(value-cache.forward(model))/np.linalg.norm(value)<1e-13
    q=rng.normal(size=3)+1j*rng.normal(size=3)
    pair=dot_pair(q,dt,cache.vjp(model,q),parameter_direction(d,dg))
    assert pair['operation_relative']<1e-12
    _,fixed=moment_tangent(model,cache,d)
    with tempfile.TemporaryDirectory() as directory:
        P,_=build_head_mapping(model,cache,Path(directory)/'P.npy')
        assert np.linalg.norm(dt-fixed-P@dg)/(np.linalg.norm(fixed)+np.linalg.norm(P@dg))<1e-12
    hidden=hidden_vector(model);h=1e-4
    set_hidden(model,hidden+h*d);assign_head(model,gamma+h*dg);plus=cache.forward(model)
    assert np.linalg.norm(plus-value-h*dt)>1e-13 # actual nonlinear trial is not a linear-only vector
    set_hidden(model,hidden);assign_head(model,gamma)
    assert np.array_equal(head_coefficients(model),gamma)


def test_nonhermitian_nonzero_port_nonoptimal_head_loss_chain():
    model,gamma,d,dg,x=example();rng=np.random.default_rng(421406)
    with torch.no_grad():
        value,change=layerwise_envelopes(model,x,parameter_direction(d,dg))
    t=torch.complex(value.reshape(-1,2)[:,0],value.reshape(-1,2)[:,1]).numpy()
    dt=torch.complex(change.reshape(-1,2)[:,0],change.reshape(-1,2)[:,1]).numpy()
    n=len(t);K=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n));C=rng.normal(size=(n,3))+1j*rng.normal(size=(n,3))
    F=rng.normal(size=(3,n))+1j*rng.normal(size=(3,n));H=np.diag([2+.2j,3-.1j,4+.3j])
    bt=rng.normal(size=n)+1j*rng.normal(size=n);bp=rng.normal(size=3)+1j*rng.normal(size=3)
    bar=K-C@np.linalg.solve(H,F);rhs=bt-C@np.linalg.solve(H,bp);r=rhs-bar@t
    da=-np.linalg.solve(H,F@dt)
    assert np.linalg.norm(F@dt+H@da)<1e-12
    q=bar.conj().T@r
    model.zero_grad();out=model.envelopes(x).reshape(-1,2);trace=torch.complex(out[:,0],out[:,1])
    torch.real(torch.vdot(torch.as_tensor(q),trace)).backward()
    vjp=np.concatenate([p.grad.numpy().ravel() for p in model.parameters()])
    pair=dot_pair(q,dt,vjp,parameter_direction(d,dg))
    assert pair['operation_relative']<1e-10 and np.linalg.norm(bp)>0
    assert np.linalg.norm(vjp)>1e-3 # deliberately not a stationary output head


def test_real_hidden_rejects_complex_and_head_restores_after_clear():
    model,gamma,d,_,_=example();hidden=hidden_vector(model)
    try:
        parameter_direction(d.astype(complex))
    except ValueError:
        pass
    else:
        raise AssertionError('complex hidden direction silently accepted')
    set_hidden(model,hidden)
    assert not np.any(head_coefficients(model))
    assign_head(model,gamma)
    assert np.array_equal(head_coefficients(model),gamma)
