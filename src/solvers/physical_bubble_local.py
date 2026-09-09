"""Local-only harmonic bubble checks; no global matrix or solver integration."""
import numpy as np
from scipy.linalg import lu_factor, lu_solve, svd, svdvals


def harmonic_bubble_check(A,P,R,interior,*,retained_bubble_rank=6,save,sample=lambda:None):
    """Fixed nullity: never delete extra modes to make the physical LU pass."""
    A,P,R=(np.asarray(x,dtype=np.complex128) for x in (A,P,R))
    interior=np.asarray(interior,dtype=int);n,k=P.shape
    if A.shape!=(n,n) or R.shape!=(k,n):raise ValueError('local matrix shapes differ')
    I=np.eye(k,dtype=complex);rb=R[:,interior]
    rank_u,sigma,vh=svd(rb,full_matrices=True)
    rank=int(retained_bubble_rank);scale=max(float(sigma[0]),np.finfo(float).tiny)
    rank_gap=bool(sigma[rank-1]>1e-12*scale and (rank==len(sigma) or sigma[rank]<=1e-12*scale))
    Z=vh[rank:].conj().T;Q=np.zeros((n,Z.shape[1]),complex);Q[interior]=Z
    basis=dict(RP_relative=float(np.linalg.norm(R@P-I)/np.linalg.norm(I)),
        RQ_norm=float(np.linalg.norm(R@Q)),Q_orthogonality=float(np.linalg.norm(Q.conj().T@Q-np.eye(Q.shape[1]))),
        fixed_rank=rank,nullity=Q.shape[1],rank_gap_pass=rank_gap,rank_singular_values=sigma,
        rank_threshold=1e-12*scale,interior_only=bool(np.all(Q[np.setdiff1d(np.arange(n),interior)]==0)))
    save('bubble_basis',dict(P=P,R=R,Q=Q,facts=basis))
    if not(rank_gap and basis['RP_relative']<=1e-12 and basis['RQ_norm']<=1e-12 and basis['Q_orthogonality']<=1e-12 and basis['interior_only']):
        raise ValueError('fixed bubble basis gate failed')
    sample();D=Q.conj().T@A@Q;B=Q.conj().T@A@P;left=P.conj().T@A@Q
    ds=svdvals(D)
    save('bubble_D_pre_factor',dict(A=A,D=D,singular_values=ds,
        sigma_max=float(ds[0]),sigma_min=float(ds[-1]),kappa2=float(ds[0]/ds[-1]) if ds[-1] else None))
    if ds[-1]==0:raise ValueError('singular physical bubble D')
    sample();lu,piv=lu_factor(D);T=lu_solve((lu,piv),B)
    W=P-Q@T;S=W.conj().T@A@W;schur=P.conj().T@A@P-left@T
    residual=D@T-B;permuted=D.copy()
    for i,j in enumerate(piv):permuted[[i,j]]=permuted[[j,i]]
    L=np.tril(lu,-1)+np.eye(len(D));U=np.triu(lu)
    tiny=np.finfo(float).tiny
    normwise=float(np.linalg.norm(residual)/max(np.linalg.norm(B),tiny))
    backward=float(np.linalg.norm(residual)/max(np.linalg.norm(D)*np.linalg.norm(T)+np.linalg.norm(B),tiny))
    facts=dict(basis=basis,LU_rhs_columns=k,LU_normwise_residual=normwise,LU_backward_error=backward,
        factor_residual=float(np.linalg.norm(L@U-permuted)/np.linalg.norm(D)),
        sigma_max=float(ds[0]),sigma_min=float(ds[-1]),kappa2=float(ds[0]/ds[-1]),
        RW_relative=float(np.linalg.norm(R@W-I)/np.linalg.norm(I)),
        QHAW_participating_relative=float(np.linalg.norm(Q.conj().T@A@W)/max(np.linalg.norm(B)+np.linalg.norm(D@T),tiny)),
        Schur_relative=float(np.linalg.norm(S-schur)/max(np.linalg.norm(S),np.linalg.norm(schur),tiny)),
        dual='W^H, not R; not exact (P,Q) block inverse',shift=0,refinements=0,factorization='complex pivoted LU')
    retained=dict(A=A,P=P,R=R,Q=Q,D=D,T=T,W=W,S=S)
    scratch=dict(rb=rb,rank_u=rank_u,sigma=sigma,vh=vh,Z=Z,B=B,left=left,ds=ds,lu=lu,piv=piv,
        residual=residual,permuted=permuted,L=L,U=U,schur=schur,I=I)
    def backing(values):
        roots={}
        for v in values:
            while isinstance(v.base,np.ndarray):v=v.base
            roots[id(v)]=v.nbytes
        return roots
    retained_roots=backing(retained.values());scratch_roots=backing(scratch.values())
    facts['array_payload']=dict(retained={k:int(v.nbytes) for k,v in retained.items()},
        scratch={k:int(v.nbytes) for k,v in scratch.items()},
        retained_bytes=sum(retained_roots.values()),
        scratch_named_bytes=sum(n for key,n in scratch_roots.items() if key not in retained_roots),
        scope='unique backing storage of named ndarrays at checkpoint; not process RSS or hidden BLAS temporaries')
    passed=all(np.isfinite(facts[k]) and facts[k]<=1e-11 for k in
        ('LU_normwise_residual','LU_backward_error','factor_residual','RW_relative','QHAW_participating_relative','Schur_relative'))
    facts['status']='LOCAL_ALGEBRA_PASS' if passed else 'LOCAL_ALGEBRA_FAIL'
    save('bubble_harmonic',dict(**retained,facts=facts));sample()
    if not passed:raise ValueError('local harmonic algebra gate failed')
    return dict(**retained,facts=facts)
