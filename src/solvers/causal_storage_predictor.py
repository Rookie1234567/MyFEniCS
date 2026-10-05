"""Small causal predictor training; NumPy-only deployment is separate."""
import numpy as np

from src.solvers.lossless_vector_bank import causal_features


def positions(vectors, blocks):
    """One dataset streamed from 16 vectors; no generating field parameters."""
    xx, yy = [], []
    for v in vectors:
        for b in blocks:
            values = v[np.asarray(b['rows'])]
            for m in range(1, values.shape[1]):
                previous = np.zeros((len(values),4),complex)
                take = min(m,4)
                previous[:,-take:] = values[:,m-take:m]
                x,scale,raw = causal_features(previous,b['kind'],b['axis'],m,values.shape[1])
                y = np.ascontiguousarray(values[:,m]/scale).view(np.float64).reshape(-1,2)
                xx.append(x[~raw]); yy.append(y[~raw])
    return np.concatenate(xx),np.concatenate(yy)


def model(kind, seed):
    import torch
    torch.manual_seed(seed)
    layers = [torch.nn.Linear(12,2)] if kind == 'LIN' else [torch.nn.Linear(12,32),torch.nn.Tanh(),torch.nn.Linear(32,32),torch.nn.Tanh(),torch.nn.Linear(32,2)]
    return torch.nn.Sequential(*layers).double()


def export(net):
    return [p.detach().cpu().numpy().copy() for p in net.parameters()]


def gradient_gate(net, x, y, seed):
    import torch
    rng = np.random.default_rng(seed)
    x,y = torch.as_tensor(x[:64]),torch.as_tensor(y[:64])
    theta = torch.nn.utils.parameters_to_vector(net.parameters()).detach().clone()
    def assign(v):
        torch.nn.utils.vector_to_parameters(v.clone(),net.parameters())
    def value():
        return (net(x)-y).square().sum(dim=1).mean()
    net.zero_grad(); v=value(); v.backward()
    gradient = torch.cat([p.grad.reshape(-1) for p in net.parameters()]).detach()
    rows=[]
    for index in range(3):
        d=torch.as_tensor(rng.normal(size=len(theta)));d/=torch.linalg.norm(d)
        analytic=float(torch.dot(gradient,d))
        for h in (1e-3,3e-4,1e-4):
            assign(theta+h*d);plus=float(value().detach())
            assign(theta-h*d);minus=float(value().detach())
            numeric=(plus-minus)/(2*h)
            relative=abs(numeric-analytic)/max(1.,abs(analytic))
            rows.append({'direction':index,'h':h,'analytic':analytic,'central':numeric,'operational_error':relative})
    assign(theta)
    passed=all(r['operational_error']<=1e-6 for r in rows) and float(torch.linalg.norm(gradient))>0
    return {'passed':passed,'checks':rows,'gradient_norm':float(torch.linalg.norm(gradient)), 'fixed_scale':1.,'gate':1e-6}
