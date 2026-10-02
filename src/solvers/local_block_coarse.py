"""One opt-in full p3 principal-block LU set and its frozen MR combination.

The artificial block boundary affects the PC only.  All cells, periodic
pullbacks and forty port couplings remain in the original outer equation.
No global fine matrix, inverse, shifted factor, or normal equation is built.
"""
import warnings
from time import perf_counter

import numpy as np
from scipy.linalg import lu_factor, lu_solve, get_lapack_funcs, LinAlgWarning
from scipy.linalg.blas import zgemm
from scipy.sparse import coo_matrix

from src.solvers.fixed_p3_ilu0 import expansions, direct_C
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.p1_image_minres import rank_check

FAMILY = 'FIXED_LOCAL_BLOCK_AND_COARSE_PAIR'
FACTOR_STATUS = 'LOCAL8_DENSE_LU_PRESENT'
ROWS = (2913,2676,2289,2076,2439,2220,1863,1668)


def capacity(counts, n, coarse=1248):
    counts=np.asarray(counts,dtype=np.int64)
    one=int(sum(int(k)**2 for k in counts)*16)
    # Original packet/libraries 3GiB, two local sets, max-block LAPACK/hash
    # temporaries, reused U/R, one DL and small SVD workspace, two 32-column
    # buffers, 256-vector Krylov, C/F/port copies. Array plan is not RSS.
    workspace=3*int(max(counts))**2*16+coarse**2*16*8+n*(64+258+160)*16
    planned=3*2**30+2*one+n*8+n*coarse*16+coarse**2*16+workspace
    return dict(block_rows=counts.tolist(),matrix_bytes=one,LU_bytes=one,
        pivots_upper_bytes=n*8,explicit_matrices_LU_bytes=2*one,
        additional_workspace_upper_bytes=workspace,simultaneous_planned_bytes=planned,
        derived_not_RSS=True,qualified=bool(sum(counts)==n and len(counts)==8
        and np.all((counts>0)&(counts<=4096)) and 2*one<=2*2**30 and planned<=8*2**30))


def assemble_blocks(packet, group, *, guard=lambda:None,event=lambda *a,**k:None):
    """All Ec^H Sc Ec sub-contributions, then exact Hhat port closure."""
    group=np.asarray(group,dtype=np.int64)
    if group.shape!=(packet.nt,) or np.any((group<0)|(group>7)):raise ValueError('partition coverage')
    rows=[np.flatnonzero(group==b) for b in range(8)]
    plan=capacity([len(r) for r in rows],packet.nt)
    if not plan['qualified']:raise MemoryError('local block preallocation capacity')
    guard();began=perf_counter();matrices=[np.zeros((len(r),len(r)),complex,order='F') for r in rows]
    position=np.empty(packet.nt,np.int64)
    for r in rows:position[r]=np.arange(len(r))
    F=np.zeros((packet.np,packet.nt),complex)
    for cell,ids,E in expansions(packet):
        guard();local=E.conj().T@packet.a['S'][packet.a['classes'][cell]]@E
        F[:,ids]-=packet.a['Dhat'][cell]@E
        for b in np.unique(group[ids]):
            take=np.flatnonzero(group[ids]==b);loc=position[ids[take]]
            matrices[b][np.ix_(loc,loc)]+=local[np.ix_(take,take)]
        if cell%64==0:event('local_principal_cell',cell=cell)
    a=packet.a
    direct=coo_matrix((-a['dv'],(a['dp'],a['dr'])),shape=F.shape).tocsr()
    direct.sum_duplicates();F+=direct.toarray()
    C=np.column_stack([direct_C(packet,np.eye(packet.np,dtype=complex)[:,j]) for j in range(packet.np)])
    Hfactor=lu_factor(a['Hhat'],check_finite=False)
    blocks=[]
    for b,r in enumerate(rows):
        guard();Cb=C[r];Fb=F[:,r];matrices[b]-=Cb@lu_solve(Hfactor,Fb,check_finite=False)
        if not np.isfinite(matrices[b]).all():raise ValueError('nonfinite closed local block')
        blocks.append(dict(block=b,rows=len(r),matrix_sha256=array_hash(matrices[b]),
            Cb_sha256=array_hash(Cb),Fb_sha256=array_hash(Fb)))
    return rows,matrices,dict(capacity=plan,assembly_seconds=perf_counter()-began,blocks=blocks,
        Hhat_sha256=array_hash(a['Hhat']),global_fine_K_or_A_constructed=False,
        owner_cells_not_used=True,shared_contributions_merged=True,all_ports=packet.np,
        F_is_C_adjoint_assumed=False,separate_curl_mass_condensation=False)


def factor_blocks(matrices, *,count=lambda k,n=1:None,guard=lambda:None):
    factors=[];checks=[]
    for b,A in enumerate(matrices):
        guard();count('local_factors');began=perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter('error',LinAlgWarning)
            LU,piv=lu_factor(A,overwrite_a=False,check_finite=False)
        factor_seconds=perf_counter()-began
        gecon=get_lapack_funcs('gecon',(LU,));started=perf_counter()
        rcond,info=gecon(LU,float(np.linalg.norm(A,1)),norm='1')
        checks.append(dict(block=b,rcond1_estimate=float(rcond),gecon_info=int(info),
            factor_seconds=factor_seconds,gecon_seconds=perf_counter()-started,
            LU_sha256=array_hash(LU),pivot_sha256=array_hash(piv),
            qualified=bool(info==0 and np.isfinite(rcond) and rcond>=1e-12),
            gecon_internal_solve_count='unknown; not measured',
            gecon_internal_triangular_pass_upper=22,partial_pivoting=True,
            shift=None,drop=None,refinement=0))
        factors.append((LU,piv))
    return factors,checks


class LocalBlocks:
    def __init__(self,n,rows,matrices,factors,*,count=lambda k,n=1:None):
        self.n,self.rows,self.matrices,self.count=n,rows,matrices,count
        # SciPy's installed f2py GETRS wrapper temporarily converts zero-based
        # pivots in place. Immutable mmap factors remain shared, but this small
        # integer ABI workspace must be private/writable, once per reader.
        self.factors=[(lu,np.array(piv,copy=True)) for lu,piv in factors]
        flat=np.concatenate(rows)
        if len(rows)!=8 or not np.array_equal(np.sort(flat),np.arange(n)):raise ValueError('local partition missing/duplicate')
        for ids,A,(LU,piv) in zip(rows,matrices,self.factors,strict=True):
            if A.shape!=LU.shape or A.shape!=(len(ids),len(ids)) or piv.shape!=(len(ids),):raise ValueError('local matrix/LU inventory')
        self.calls=0;self.seconds=0.;self.solve_seconds=0.;self.dop_calls=0

    def apply(self,r):
        r=np.asarray(r,dtype=complex)
        if r.shape!=(self.n,) or not np.isfinite(r).all():raise ValueError('local RHS')
        self.count('L8');self.calls+=1;began=perf_counter();out=np.empty_like(r)
        for ids,factor in zip(self.rows,self.factors,strict=True):
            self.count('local_lu_solve');self.count('local_triangular_pass',2);start=perf_counter()
            out[ids]=lu_solve(factor,r[ids],check_finite=False)
            self.solve_seconds+=perf_counter()-start
        self.seconds+=perf_counter()-began
        if not np.isfinite(out).all():raise ValueError('local solve nonfinite')
        return out

    def dop(self,x):
        x=np.asarray(x,dtype=complex)
        if x.shape[0]!=self.n or x.ndim not in (1,2):raise ValueError('block multiply inventory')
        self.dop_calls+=1;out=np.empty_like(x)
        for ids,A in zip(self.rows,self.matrices,strict=True):out[ids]=A@x[ids]
        return out


def composite_overlap(local,image,*,count=lambda k,n=1:None,guard=lambda:None):
    """Exactly one DL/SVD, <=32 trace columns per temporary. No fine projector."""
    began=perf_counter();T=image.T;n,q=T.shape;D=np.empty((q,q),complex,order='F');product_sq=0.
    for start in range(0,q,32):
        guard();X=np.asarray(T[:,start:start+32].toarray(),order='F')
        DX=np.asfortranarray(local.dop(X))
        product_sq+=float(np.linalg.norm(DX)**2)
        D[:,start:start+32]=zgemm(1.,image.U,DX,trans_a=2)
        del X,DX
    count('DL_SVD');started=perf_counter();check=rank_check(D)
    # For the exact-zero counterexample even a 1x1 roundoff remnant has a
    # singular-value *ratio* of one. A wholly unresolved contraction cannot
    # qualify as an invertible overlap. Keep the required ratio gate unchanged
    # and separately reject this loss of numerical identity; no rank is cut.
    product_scale=float(np.linalg.norm(image.U)*np.sqrt(product_sq))
    floor=64*np.finfo(float).eps*product_scale
    resolved=bool(check['sigma_max']>floor)
    return D,dict(safety=check,build_seconds=started-began,SVD_seconds=perf_counter()-started,
        D_L_sha256=array_hash(D),column_buffer_max=32,known_old_overlap_not_reused=True,
        product_operation_scale=product_scale,whole_overlap_roundoff_floor=floor,
        whole_overlap_resolved=resolved,ratio_threshold_unchanged=True,
        qualified=bool(check['numerical_full_column_rank'] and resolved))


class LocalCoarse:
    def __init__(self,local,image,action):
        self.local,self.image,self.action=local,image,action;self.calls=0;self.seconds=0.
    def apply(self,r):
        began=perf_counter();self.calls+=1;u=self.local.apply(r)
        result=u+self.image.apply(r-self.action(u));self.seconds+=perf_counter()-began
        if not np.isfinite(result).all():raise ValueError('LC nonfinite')
        return result
