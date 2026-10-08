"""Opt-in coefficient-first PUBLIC_BASIX affine Maxwell vector integral.

The trial coefficients are contracted before the small physical Piola maps.
The test functional is integrated in the reference basis and then transformed
back with the complex dual. No cell/global matrix or production tensor is read.
"""
import numpy as np


class ReferenceVectorIntegral:
    """One immutable p/q reference table, with bounded column workspaces."""

    def __init__(self, values, curls, weights):
        self.values = np.asarray(values)
        self.curls = np.asarray(curls)
        self.weights = np.asarray(weights)
        if (self.values.ndim != 3 or self.values.shape != self.curls.shape
                or self.values.shape[2] != 3 or self.weights.shape != self.values.shape[:1]):
            raise ValueError('reference vector integral table shapes')
        if any(not np.all(np.isfinite(a)) for a in (self.values,self.curls,self.weights)):
            raise ValueError('nonfinite reference integral table')
        # q/component rows and basis columns; copies exist only for this table.
        self.phi = np.ascontiguousarray(self.values.transpose(0,2,1).reshape(-1,self.values.shape[1]))
        self.psi = np.ascontiguousarray(self.curls.transpose(0,2,1).reshape(-1,self.values.shape[1]))
        self.phi_H = np.ascontiguousarray(self.phi.conj().T)
        self.psi_H = np.ascontiguousarray(self.psi.conj().T)

    def apply(self, coefficients, J, T, kappa, k0, epsilon, mu):
        c = np.asarray(coefficients)
        single = c.ndim == 1
        if single: c = c[:,None]
        if c.ndim != 2 or c.shape[0] != self.values.shape[1] or not 1 <= c.shape[1] <= 2:
            raise ValueError('one or two complete columns required')
        J = np.asarray(J)
        T = np.asarray(T)
        kappa = np.asarray(kappa)
        if J.shape != (3,3) or np.iscomplexobj(J) or kappa.shape != (3,) or np.iscomplexobj(kappa):
            raise ValueError('real affine geometry and real carrier required')
        if T.shape != (len(c),len(c)) or mu == 0:
            raise ValueError('orientation or material shape')
        det = float(np.linalg.det(J))
        if det == 0 or not np.isfinite(det): raise ValueError('degenerate affine geometry')
        F = np.linalg.inv(J)
        G = J.T/det
        chat = T.T @ c  # bilinear orientation on primal coefficients, not T^H
        shape = (len(self.weights),3,c.shape[1])
        uref = (self.phi @ chat).reshape(shape)
        cref = (self.psi @ chat).reshape(shape)
        U = np.einsum('qcb,cd->qdb',uref,F)
        W = np.einsum('qcb,cd->qdb',cref,G) + 1j*np.cross(kappa,U.transpose(0,2,1)).transpose(0,2,1)
        h = W/mu
        z = 1j*np.cross(kappa,h.transpose(0,2,1)).transpose(0,2,1) - k0**2*epsilon*U
        curl_test = np.einsum('qcb,cd->qdb',h,G.T)*self.weights[:,None,None]
        value_test = np.einsum('qcb,cd->qdb',z,F.T)*self.weights[:,None,None]
        rhat = abs(det)*(self.psi_H @ curl_test.reshape(-1,c.shape[1])
                        + self.phi_H @ value_test.reshape(-1,c.shape[1]))
        result = T.conj() @ rhat
        return result[:,0] if single else result


class CoefficientBodyAction:
    """Native assembly and exact MPC Hermitian pullback, all cells retained."""

    def __init__(self, setup, q):
        from .independent_tetra_reference import TetraEvaluator
        self.s = setup
        self.q = int(q)
        self.ev = TetraEvaluator(setup['V'],q,setup['kappa'])
        self.reference = ReferenceVectorIntegral(self.ev.values,self.ev.curls,self.ev.weights)
        cfg = setup['cfg']
        self.materials = {cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
        self.last = None

    def cell(self, c, coefficients):
        cfg = self.s['cfg']
        return self.reference.apply(coefficients,self.ev.geometry[c][0],self.ev.transform(c),
            self.s['kappa'],cfg.k0,self.materials[int(self.s['data'].cell_tags.values[c])],cfg.mu_r)

    def __call__(self, coefficients):
        import time
        x = np.asarray(coefficients)
        single = x.ndim == 1
        if single: x = x[:,None]
        if x.ndim != 2 or x.shape[0] != self.s['P'].shape[1] or not 1 <= x.shape[1] <= 2:
            raise ValueError('full independent body column identity')
        began = time.perf_counter()
        native = self.s['P'] @ x
        out = np.zeros_like(native,dtype=np.complex128)
        for c in range(len(self.ev.geometry)):
            rows = self.s['V'].dofmap.cell_dofs(c)
            np.add.at(out,rows,self.cell(c,native[rows]))
        result = self.s['P'].conj().T @ out
        self.last = dict(seconds=time.perf_counter()-began,q=self.q,cells=len(self.ev.geometry),columns=x.shape[1],
            reference_table_bytes=sum(a.nbytes for a in (self.reference.values,self.reference.curls,self.reference.phi,self.reference.psi,self.reference.phi_H,self.reference.psi_H,self.reference.weights)),
            full_vector_workspace_bytes=native.nbytes+out.nbytes+result.nbytes,
            algorithm='COEFFICIENT_FIRST_PUBLIC_BASIX_VECTOR',production_matrix_reads=0)
        return result[:,0] if single else result


class CoefficientFullAction:
    """Original independent body and complete, independently integrated DtN."""

    def __init__(self,setup,boundary,q):
        from .independent_tetra_reference import boundary_matrices
        self.s=setup;self.boundary=boundary
        self.body=CoefficientBodyAction(setup,q)
        self.C,self.D,self.H=boundary_matrices(setup,boundary)
        self.n=setup['P'].shape[1]

    def __call__(self,x):
        x=np.asarray(x);single=x.ndim==1
        if single:x=x[:,None]
        if x.shape[0]!=self.n+len(self.H):raise ValueError('full FE plus complete port identity')
        result=np.vstack((self.body(x[:self.n])+self.C@x[self.n:],
            -self.D@x[:self.n]+self.H[:,None]*x[self.n:]))
        return result[:,0] if single else result

    def rhs(self):
        b=self.boundary
        return np.r_[b['incident'][self.s['masters']]+self.C@b['projections'],np.zeros(len(self.H),complex)]

    def audit(self,x,producer_rhs,journal):
        from .independent_tetra_reference import complete_residual_metrics
        from .scattering_anchor import relative
        with journal.measured('independent_COEFFICIENT_FIRST_PUBLIC_BASIX_body_q'+str(self.body.q)+'_triangle63'):
            b=self.rhs();r=b-self(x)
        metrics,closed,projected=complete_residual_metrics(self.C,self.D,self.H,x,b,r)
        identity=relative(producer_rhs-b,producer_rhs)
        field=self.s['P']@x[:self.n];mpc=self.s['floquet'].mpc
        coefficients,offsets=mpc.coefficients()
        defects=[field[slave]-np.dot(coefficients[offsets[slave]:offsets[slave+1]],field[mpc.masters.links(int(slave))]) for slave in mpc.slaves]
        constraint=float(np.linalg.norm(defects)/max(np.linalg.norm(field),1e-300))
        result=dict(**metrics,direct_target=max(metrics[k] for k in ('true','native','augmented','port'))<=1e-10,
            rhs_q47_q63=identity,MPC_identity=constraint,absolute_residual=float(np.linalg.norm(r)),original_rhs_norm=float(np.linalg.norm(b)),
            backend='PUBLIC_BASIX_COEFFICIENT_FIRST_Q'+str(self.body.q)+'_TRIANGLE63',body_consumption=self.body.last,
            closed_physical_residual_norm=float(np.linalg.norm(closed)),projected_port_norm=float(np.linalg.norm(projected)),
            pass_gate=max(metrics[k] for k in ('true','native','augmented','port'))<=1e-6 and identity<=1e-10 and constraint<=1e-10)
        journal.calls['A']+=1
        return result,r,b
