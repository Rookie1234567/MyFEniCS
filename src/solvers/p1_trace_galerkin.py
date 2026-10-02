"""Bounded p1-origin TRACE Galerkin coarse correction of the original p3 A.

T is a genuine FE interpolation restricted to trace, not a rediscretized p1
operator. Only n1-square Ac is materialized; no fine matrix or inverse exists.
"""
from time import perf_counter
import warnings

import numpy as np
from scipy.linalg import lu_factor, lu_solve, get_lapack_funcs, eigvalsh
from scipy.sparse import csr_matrix, coo_matrix

from src.solvers.fixed_p3_ilu0 import expansions, direct_C
from src.solvers.neural_fe_action_packet import array_hash

FACTOR_STATUS = 'GLOBAL_BOUNDED_TRACE_GALERKIN_FACTOR_PRESENT'


def sparse_payload(T):
    return int(T.data.nbytes + T.indices.nbytes + T.indptr.nbytes)


def normalize_transfer(T0):
    T0 = csr_matrix(T0, dtype=np.complex128)
    T0.sum_duplicates(); T0.sort_indices()
    n1 = T0.shape[1]
    if not 0 < n1 <= 2048 or sparse_payload(T0) > 128*2**20:
        raise MemoryError('p1 trace inventory/capacity exceeds the frozen limit')
    norms = np.sqrt(np.asarray(abs(T0).power(2).sum(axis=0)).ravel())
    if np.any(norms == 0) or not np.isfinite(norms).all():
        raise ValueError('zero/nonfinite p1 trace column; no deletion allowed')
    T = T0.multiply(1/norms).tocsr(); T.sort_indices()
    gram = (T.conj().T @ T).toarray()
    values = eigvalsh(gram, check_finite=False)
    rank = int(np.count_nonzero(values > 1e-12*values[-1]))
    row = dict(n1=n1, fine_rows=T.shape[0], trace_nnz=T.nnz,
        trace_payload_bytes=sparse_payload(T), column_norm_range=[float(norms.min()),float(norms.max())],
        normalization='nonzero Euclidean column norm only; no clipping or entry deletion',
        Gram_eigen_range=[float(values[0]),float(values[-1])], numerical_rank=rank,
        rank_threshold_relative=1e-12, full_column_rank=rank==n1,
        data_sha256=array_hash(T.data), indices_sha256=array_hash(T.indices), indptr_sha256=array_hash(T.indptr))
    if rank != n1 or sparse_payload(T) > 128*2**20:
        raise ValueError('p1 trace columns are not safely independent')
    return T, norms, row


def capacity(n1, Tbytes):
    explicit = 2*n1*n1*16 + n1*8
    workspace = 8*n1*n1*16 + 40*n1*16*4 + 108*n1*16
    total = 3*2**30 + Tbytes*3 + workspace + 18144*600*16
    return dict(n1=n1, matrix_and_LU_explicit_upper_bytes=explicit,
        new_workspace_upper_bytes=workspace, simultaneous_planned_bytes=total,
        qualified=0<n1<=2048 and Tbytes<=128*2**20 and explicit<=256*2**20
        and workspace<=2**30 and total<=8*2**30,
        memory_values_are_derived_not_RSS=True)


def assemble_coarse(packet, T, *, guard=lambda:None, event=lambda **kw:None):
    """All original cell Schur contributions and exact Floquet expansion.

Only locally supported T columns enter each cell product. No global fine K.
    """
    began=perf_counter(); n1=T.shape[1]; plan=capacity(n1,sparse_payload(T))
    if not plan['qualified']:raise MemoryError('bounded trace coarse capacity failed')
    Kc=np.zeros((n1,n1),np.complex128); Fc=np.zeros((packet.np,n1),np.complex128)
    max_support=0
    for cell,ids,E in expansions(packet):
        guard(); sub=T[ids]; columns=np.unique(sub.indices)
        local=E @ sub[:,columns].toarray(); max_support=max(max_support,len(columns))
        schur=packet.a['S'][packet.a['classes'][cell]]
        Kc[np.ix_(columns,columns)] += local.conj().T @ schur @ local
        Fc[:,columns] -= packet.a['Dhat'][cell] @ local
        if cell%64==0:event(event='p1_trace_coarse_cell',cell=cell,local_p1_columns=len(columns))
    a=packet.a
    direct=coo_matrix((-a['dv'],(a['dp'],a['dr'])),shape=(packet.np,packet.nt)).tocsr()
    direct.sum_duplicates(); Fc += direct @ T
    C=np.column_stack([direct_C(packet,np.eye(packet.np,dtype=complex)[:,j]) for j in range(packet.np)])
    Cc=np.asarray(T.conj().T @ C)
    from scipy.linalg import solve
    Ac=Kc-Cc @ solve(a['Hhat'],Fc,assume_a='gen',check_finite=False)
    if not np.isfinite(Ac).all():raise ValueError('nonfinite original projected coarse operator')
    return Ac,dict(plan,assembly_seconds=perf_counter()-began,max_local_p1_support=max_support,
        duplicate_contributions_merged=True, coarse_formula='T^H K T - T^H C Hhat^-1 F T',
        Ac_sha256=array_hash(Ac),Cc_sha256=array_hash(Cc),Fc_sha256=array_hash(Fc),
        global_fine_matrix_constructed=False, separate_curl_mass_condensation=False)


class RefinedCoarse:
    """One fixed complex128 pivoted LU and EXACTLY one residual refinement."""
    def __init__(self, Ac, *, count=lambda key,n=1:None):
        self.Ac=np.asarray(Ac,dtype=np.complex128);self.count=count;self.calls=0;self.seconds=0.
        if self.Ac.ndim!=2 or self.Ac.shape[0]!=self.Ac.shape[1] or not np.isfinite(self.Ac).all():
            raise ValueError('invalid bounded coarse matrix')
        count('factor_setups'); began=perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter('error'); self.factor=lu_factor(self.Ac,check_finite=False)
        rcond,info=get_lapack_funcs('gecon',(self.factor[0],))(self.factor[0],np.linalg.norm(self.Ac,1))
        if info or not np.isfinite(rcond) or rcond<1e-12:raise ValueError('fixed coarse LU unsafe rcond1')
        self.metadata=dict(factor_status=FACTOR_STATUS,n1=len(self.Ac),rcond1_estimate=float(rcond),
            cond1_estimate=float(1/rcond),condition_is_estimate_not_fine_condition=True,
            factor_policy='complex128 LAPACK partial pivoting; no shift/drop/reordering; one fixed refinement',
            Ac_sha256=array_hash(self.Ac),LU_sha256=array_hash(self.factor[0]),pivot_sha256=array_hash(self.factor[1]),
            explicit_Ac_LU_pivot_bytes=int(self.Ac.nbytes+self.factor[0].nbytes+self.factor[1].nbytes),
            setup_seconds=perf_counter()-began,LU_call_counting='each lu_solve charged as two individual triangular passes')
        if self.metadata['explicit_Ac_LU_pivot_bytes']>256*2**20:raise MemoryError('coarse factor explicit payload cap')

    def solve(self,s):
        began=perf_counter();s=np.asarray(s,dtype=np.complex128)
        if s.shape!=(len(self.Ac),) or not np.isfinite(s).all():raise ValueError('coarse RHS inventory/nonfinite')
        self.count('coarse_triangular',4);self.calls+=1
        u0=lu_solve(self.factor,s,check_finite=False)
        value=u0+lu_solve(self.factor,s-self.Ac@u0,check_finite=False)
        self.seconds+=perf_counter()-began
        if not np.isfinite(value).all():raise ValueError('nonfinite fixed coarse correction')
        return value


class TraceGalerkinPC:
    def __init__(self,T,coarse,action,*,count=lambda key,n=1:None):
        self.T=csr_matrix(T);self.TH=self.T.conj().T.tocsr();self.coarse=coarse
        self.action=action;self.count=count;self.calls=0;self.seconds=0.
        self.tau=float(np.sqrt(T.shape[1])/np.linalg.norm(coarse.Ac,'fro'))
        if not 0<self.tau or not np.isfinite(self.tau):raise ValueError('fixed tau is nonpositive or nonfinite')

    def Q(self,r):return np.asarray(self.T @ self.coarse.solve(np.asarray(self.TH@r)))

    def apply(self,r):
        began=perf_counter();r=np.asarray(r,dtype=np.complex128)
        if r.shape!=(self.T.shape[0],) or not np.isfinite(r).all():raise ValueError('right PC input inventory')
        self.count('B');self.calls+=1
        value=self.tau*r+self.Q(r-self.tau*self.action(r))
        self.seconds+=perf_counter()-began
        if not np.isfinite(value).all():raise ValueError('nonfinite full-space right PC')
        return value
