"""V16 opt-in full-trace, doubly projected LSQR algebra.

Q spans trace coefficients; U spans their original equation images.  These
are deliberately separate objects.  Dense matrices are thin, never n by n.
"""

from time import perf_counter

import numpy as np
from scipy.linalg import lu_factor, lu_solve, solve_triangular
from scipy.linalg.blas import zgemv


FAMILY = "AUGMENTED_FULL_TRACE_LSQR"
LIMITS = dict(new_A_columns=6196, image_QR=2, original_audits=240, field_states=10)


class ThinBasis:
    """Owned Fortran blocks permit BLAS conjugate transpose without copies."""

    def __init__(self, n, blocks=()):
        self.n = n
        self.blocks = tuple(np.asfortranarray(b, dtype=np.complex128) for b in blocks)
        if any(b.ndim != 2 or b.shape[0] != n or not np.isfinite(b).all() for b in self.blocks):
            raise ValueError("nonfinite or incompatible canonical thin basis")
        self.widths = [b.shape[1] for b in self.blocks]
        self.shape = (n, sum(self.widths))

    def forward(self, c):
        if np.shape(c) != (self.shape[1],):
            raise ValueError("basis coefficient inventory differs")
        out = np.zeros(self.n, complex)
        start = 0
        for b, width in zip(self.blocks, self.widths):
            out += zgemv(1., b, c[start:start+width])
            start += width
        return out

    def adjoint(self, x):
        if np.shape(x) != (self.n,):
            raise ValueError("basis row inventory differs")
        return np.concatenate([zgemv(1., b, x, trans=2) for b in self.blocks]) if self.blocks else np.zeros(0, complex)

    def complement(self, x):
        return x - self.forward(self.adjoint(x))

    def column(self, j):
        for b, width in zip(self.blocks, self.widths):
            if j < width:
                return b[:, j]
            j -= width
        raise IndexError(j)

    def orthogonality(self):
        # Only r by r products; not a full-trace projector.
        total = 0.
        for i, a in enumerate(self.blocks):
            for j, b in enumerate(self.blocks):
                gram = a.conj().T @ b
                if i == j:
                    gram -= np.eye(a.shape[1])
                total += float(np.linalg.norm(gram)**2)
        return total**.5 / max(1., self.shape[1]**.5)


class BarAction:
    """Exact Hhat closure; one original S or SH per homogeneous action."""

    def __init__(self, ports):
        self.ports = ports
        self.packet = ports.packet
        self.n = self.packet.nt
        self.factor = lu_factor(ports.H)
        self.C = np.asfortranarray(ports.C)
        self.costs = dict(S=0., SH=0., port_solve=0.)

    def solve_port(self, rhs, adjoint=False):
        began = perf_counter()
        value = lu_solve(self.factor, rhs, trans=2 if adjoint else 0)
        self.costs['port_solve'] += perf_counter()-began
        return value

    def apply(self, t):
        began = perf_counter()
        original = self.packet.apply(np.r_[t, np.zeros(self.packet.np, complex)])
        self.costs['S'] += perf_counter()-began
        return original[:self.n] - zgemv(1., self.C, self.solve_port(original[self.n:]))

    def adjoint(self, r):
        dual = self.solve_port(zgemv(1., self.C, r, trans=2), adjoint=True)
        began = perf_counter()
        value = self.packet.apply(np.r_[r, -dual], adjoint=True)[:self.n]
        self.costs['SH'] += perf_counter()-began
        return value

    def reduced_rhs(self, rhs):
        return rhs[:self.n] - zgemv(1., self.C, self.solve_port(rhs[self.n:]))

    def close(self, t, rhs):
        original = self.packet.apply(np.r_[t, np.zeros(self.packet.np, complex)])
        alpha = self.solve_port(rhs[self.n:] - original[self.n:])
        return np.r_[t, alpha]


class ProjectedTraceOperator:
    def __init__(self, bar, Q, U=None, R=None):
        self.bar, self.Q = bar, Q
        self.U = U if U is not None else ThinBasis(bar.n)
        self.R = R if R is not None else np.empty((0, 0), complex)
        r = Q.shape[1]
        if self.U.shape != Q.shape or self.R.shape != (r, r):
            raise ValueError("trace Q and equation image U/R inventory differs")
        self.costs = dict(trace_projection=0., residual_projection=0., triangular_solve=0.)

    def pt(self, x):
        began = perf_counter(); result = self.Q.complement(x)
        self.costs['trace_projection'] += perf_counter()-began
        return result

    def pr(self, x):
        began = perf_counter(); result = self.U.complement(x)
        self.costs['residual_projection'] += perf_counter()-began
        return result

    def apply(self, y):
        return self.pr(self.bar.apply(self.pt(y)))

    def adjoint(self, r):
        return self.pt(self.bar.adjoint(self.pr(r)))

    def rhs(self, rhs):
        return self.pr(self.bar.reduced_rhs(rhs))

    def restore(self, y, rhs):
        v = self.pt(y)
        reduced = self.bar.reduced_rhs(rhs)
        remainder = reduced - self.bar.apply(v)
        began = perf_counter()
        c = solve_triangular(self.R, self.U.adjoint(remainder)) if self.Q.shape[1] else np.zeros(0, complex)
        self.costs['triangular_solve'] += perf_counter()-began
        qc = self.Q.forward(c)
        t = v + qc
        z = self.bar.close(t, rhs)
        return dict(y=np.array(y), v=v, c=c, trace=t, port=z[self.bar.n:], z=z,
                    Qc_norm=float(np.linalg.norm(qc)), complement_norm=float(np.linalg.norm(v)))


def operation_pair(a, b):
    difference = float(np.linalg.norm(a-b))
    return dict(absolute=difference, operation_relative=difference/max(np.linalg.norm(a)+np.linalg.norm(b), 1e-300))


def projected_checks(operator, rhs, seed=421601):
    """Two complex dot tests, both projector identities and actual residual."""
    rng = np.random.default_rng(seed)
    random = lambda n: rng.normal(size=n)+1j*rng.normal(size=n)
    n = operator.bar.n
    tests = []
    for _ in range(2):
        x, r = random(n), random(n)
        mx, mr = operator.apply(x), operator.adjoint(r)
        a, b = np.vdot(r, mx), np.vdot(mr, x)
        scale = np.linalg.norm(r)*np.linalg.norm(mx)+np.linalg.norm(mr)*np.linalg.norm(x)
        tests.append(dict(absolute=float(abs(a-b)), operation_relative=float(abs(a-b)/max(scale, 1e-300)),
                          input_norm=float(np.linalg.norm(x)), dual_norm=float(np.linalg.norm(r))))
    x = random(n)
    pt, pr = operator.pt(x), operator.pr(x)
    idem = dict(Pt=operation_pair(operator.pt(pt), pt), Pr=operation_pair(operator.pr(pr), pr))
    if operator.Q.shape[1]:
        coeff = random(operator.Q.shape[1])
        q, u = operator.Q.forward(coeff), operator.U.forward(coeff)
        annihilation = dict(Pt=float(np.linalg.norm(operator.pt(q))/np.linalg.norm(q)),
                            Pr=float(np.linalg.norm(operator.pr(u))/np.linalg.norm(u)))
    else:
        annihilation = dict(Pt=0., Pr=0.)
    point = operator.restore(pt, rhs)
    explicit = rhs-operator.bar.packet.apply(point['z'])
    projected = operator.rhs(rhs)-operator.apply(pt)
    identity = float(np.linalg.norm(explicit[:n]-projected)/max(np.linalg.norm(rhs), 1e-300))
    passed = (max(t['operation_relative'] for t in tests)<=1e-10
              and max(v['operation_relative'] for v in idem.values())<=1e-10
              and max(annihilation.values())<=1e-10 and identity<=1e-8)
    return dict(dot_tests=tests, idempotence=idem, annihilation=annihilation,
                original_residual_identity_relative=identity, qualified=passed)
