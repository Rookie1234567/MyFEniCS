"""Minimum original residual correction in a frozen p1-origin trace space.

The orthogonal columns U are images A T, not trace directions.  This is a
thin QR correction for a complex non-Hermitian problem, not MINRES Krylov.
"""
from time import perf_counter

import numpy as np
from scipy.linalg import qr, solve_triangular, svdvals
from scipy.linalg.blas import zgemv, zgemm
from scipy.sparse import csr_matrix

from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.augmented_trace_lsqr import operation_pair
from src.solvers.p1_trace_galerkin import sparse_payload

FAMILY = 'P1_IMAGE_MINRES_COMPARISON'
IMAGE_STATUS = 'GLOBAL_TALL_IMAGE_QR_PRESENT'
TAU = 0.13558083643793006


def capacity(T):
    n, r = T.shape
    tall, small = n*r*16, r*r*16
    # W/U, a LAPACK input/output copy, reconstruction, QR and both small SVD
    # workspaces overlap conservatively; the old packet/library allowance is
    # separate.  Array volume is deliberately NOT presented as tree RSS.
    workspace = 4*tall + 10*small + 4*sparse_payload(T) + 40*n*16
    whole = 3*2**30 + workspace
    return dict(rows=n, columns=r, U_bytes=tall, R_bytes=small,
        U_R_bytes=tall+small, new_workspace_planned_bytes=workspace,
        simultaneous_tree_planned_bytes=whole, derived_not_RSS=True,
        qualified=0<r<=2048 and workspace<=2*2**30 and whole<=8*2**30)


def rank_check(block):
    """One small singular-value check, no truncation or rank scan."""
    s=svdvals(block,check_finite=False)
    ratio=float(s[-1]/s[0]) if len(s) and s[0]>0 else 0.
    return dict(sigma_min=float(s[-1]),sigma_max=float(s[0]),ratio=ratio,
                fixed_threshold=1e-12,numerical_full_column_rank=ratio>=1e-12,
                meaning='small block safety; not the fine operator condition')


def build_image(T, action, *, count=lambda key,n=1:None,
                guard=lambda **kw:None, event=lambda *args,**kw:None):
    plan=capacity(T)
    if not plan['qualified']:raise MemoryError('frozen thin image workspace plan failed')
    count('image_builds');guard(large=True)
    began=perf_counter();W=np.empty(T.shape,dtype=np.complex128,order='F')
    columns=T.tocsc()
    for j in range(T.shape[1]):
        guard(extra_actions=1);count('image_columns')
        t=np.zeros(T.shape[0],complex)
        lo,hi=columns.indptr[j:j+2];t[columns.indices[lo:hi]]=columns.data[lo:hi]
        W[:,j]=action(t)
        if j%64==0:event('image_column_complete',column=j,total=T.shape[1])
    return W,dict(capacity=plan,original_action_columns=T.shape[1],
                  construction_seconds=perf_counter()-began)


def decompose(W, T, Ac, *, count=lambda key,n=1:None,
              guard=lambda **kw:None):
    """Exactly one economic nonpivoting Householder QR, one R/D SVD each."""
    guard(large=True);began=perf_counter();count('image_QR')
    U,R=qr(W,mode='economic',pivoting=False,overwrite_a=False,check_finite=False)
    qr_seconds=perf_counter()-began
    U=np.asfortranarray(U);R=np.asfortranarray(R)
    normW=float(np.linalg.norm(W));reconstruction=U@R
    relative=float(np.linalg.norm(reconstruction-W)/max(normW,1e-300))
    del reconstruction
    gram=zgemm(1.,U,U,trans_a=2);gram-=np.eye(R.shape[0])
    orth=float(np.linalg.norm(gram)/np.sqrt(R.shape[0]));del gram
    TH=T.conj().T.tocsr()
    projected=np.asarray(TH@W);projected_pair=operation_pair(projected,Ac)
    D=np.asfortranarray((TH@U).conj().T)
    overlap_pair=operation_pair(D.conj().T@R,Ac)
    count('R_SVD');started=perf_counter();rr=rank_check(R);R_SVD_seconds=perf_counter()-started
    count('D_SVD');started=perf_counter();dr=rank_check(D);D_SVD_seconds=perf_counter()-started
    row=dict(qr_policy='complex128 economic nonpivoting Householder; no truncation',
        QR_reconstruction_relative=relative,U_orthogonality_normalized_Frobenius=orth,
        TH_W_Ac=projected_pair,DH_R_Ac=overlap_pair,R_safety=rr,D_safety=dr,
        decomposition_seconds=perf_counter()-began,QR_seconds=qr_seconds,
        R_SVD_seconds=R_SVD_seconds,D_SVD_seconds=D_SVD_seconds,
        decomposition_subtimers_not_additive=True,U_sha256=array_hash(U),R_sha256=array_hash(R),
        D_sha256=array_hash(D),global_factor_status=IMAGE_STATUS,
        normal_equations=False,full_projector=False,small_SVD_only=True)
    row['image_qualified']=bool(max(relative,orth,projected_pair['operation_relative'])<=1e-10 and rr['numerical_full_column_rank'])
    row['full_space_PC_safe']=bool(row['image_qualified'] and overlap_pair['operation_relative']<=1e-10 and dr['numerical_full_column_rank'])
    return U,R,D,row


class ImageMinres:
    """Fixed T/UR; one R triangular solve per J call, no explicit inverse."""
    def __init__(self,T,U,R,*,count=lambda key,n=1:None):
        self.T=csr_matrix(T);self.U=np.asfortranarray(U,dtype=np.complex128)
        self.R=np.asfortranarray(R,dtype=np.complex128);self.count=count
        if self.U.shape!=T.shape or self.R.shape!=(T.shape[1],T.shape[1]):raise ValueError('image/canonical dimensions differ')
        if not np.isfinite(self.U).all() or not np.isfinite(self.R).all():raise ValueError('nonfinite image')
        self.calls=0;self.seconds=0.

    def adjoint_image(self,r):
        # BLAS consumes the read-only Fortran image directly.  No repeated
        # conjugated n-by-r matrix is allocated in the PC loop.
        return zgemv(1.,self.U,np.asarray(r,dtype=complex),trans=2)

    def coefficients(self,r):
        r=np.asarray(r,dtype=complex)
        if r.shape!=(self.T.shape[0],) or not np.isfinite(r).all():raise ValueError('MR RHS inventory/nonfinite')
        self.count('R_triangular');self.calls+=1;began=perf_counter()
        c=solve_triangular(self.R,self.adjoint_image(r),lower=False,check_finite=False)
        self.seconds+=perf_counter()-began
        if not np.isfinite(c).all():raise ValueError('MR correction nonfinite')
        return c

    def apply(self,r):return np.asarray(self.T@self.coefficients(r))


class ImageMinresPC:
    """Full-space tau identity plus the frozen image coarse correction."""
    def __init__(self,image,action,*,tau=TAU,count=lambda key,n=1:None):
        self.image,self.action,self.count=image,action,count
        self.tau=float(tau);self.calls=0;self.seconds=0.
        if self.tau!=TAU:raise ValueError('fixed V22 tau cannot be tuned')

    def apply(self,r):
        r=np.asarray(r,dtype=complex)
        if r.shape!=(self.image.T.shape[0],) or not np.isfinite(r).all():raise ValueError('full-space PC inventory')
        self.count('B_M');self.calls+=1;began=perf_counter()
        value=self.tau*r+self.image.apply(r-self.tau*self.action(r))
        self.seconds+=perf_counter()-began
        if not np.isfinite(value).all():raise ValueError('full-space PC nonfinite')
        return value
