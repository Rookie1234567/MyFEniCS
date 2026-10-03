"""One exact closed principal submatrix and offline extra-direction evidence.

Only the selected canonical rows are assembled. No global fine matrix,
reference field, iterative solve, shifted factor or learned parameter appears.
"""
import warnings
from time import perf_counter

import numpy as np
from scipy.linalg import (LinAlgWarning,get_lapack_funcs,lu_factor,lu_solve,
    qr,lstsq,solve_triangular)

from src.solvers.fixed_p3_ilu0 import expansions
from src.solvers.block_residual_direction import relative,complex_value,EPS
from src.solvers.neural_fe_action_packet import array_hash

FAMILY='FROZEN_JOINT_5_7_EXTRA_DIRECTION_DIAGNOSTIC'
FACTOR_STATUS='JOINT_5_7_DENSE_LU_PRESENT'
SEEDS=(422601,422602)


def selected_rows(groups):
    groups=np.asarray(groups)
    if groups.shape!=(18144,) or tuple(np.bincount(groups,minlength=8))!=(2913,2676,2289,2076,2439,2220,1863,1668):
        raise ValueError('fixed canonical eight-group inventory')
    ids=np.flatnonzero((groups==5)|(groups==7))
    if len(ids)!=3888:raise ValueError('fixed 3888-row union')
    return ids


def capacity(n,nt):
    one=n*n*16
    # Original packet/libraries allowance; A+LU plus factor/hash/LAPACK copies,
    # the two old diagonal matrices, port tensors and nine-column buffers.
    planned=3*2**30+5*one+(2220**2+1668**2)*16+nt*(40*4+9*8)*16
    return dict(rows=n,matrix_bytes=one,LU_bytes=one,pivots_upper_bytes=n*8,
        explicit_matrix_LU_bytes=2*one,simultaneous_planned_bytes=planned,
        qualified=bool(0<n<=3888 and planned<=8*2**30),derived_not_RSS=True)


def assemble_selected(packet,ids,C,port_solve,*,guard=lambda:None,event=lambda **kw:None):
    """Accumulate every cell pullback, including periodic duplicate entries."""
    ids=np.asarray(ids,np.int64);n=len(ids)
    if len(np.unique(ids))!=n or np.any(np.diff(ids)<=0) or np.any((ids<0)|(ids>=packet.nt)):
        raise ValueError('principal rows must be unique ascending canonical masters')
    began=perf_counter();guard();A=np.zeros((n,n),complex,order='F')
    F=np.zeros((packet.np,n),complex);position=np.full(packet.nt,-1,np.int64);position[ids]=np.arange(n)
    participating=0
    for cell,columns,E in expansions(packet):
        guard();take=np.flatnonzero(position[columns]>=0)
        if len(take):
            loc=position[columns[take]];EJ=E[:,take]
            A[np.ix_(loc,loc)]+=EJ.conj().T@packet.a['S'][packet.a['classes'][cell]]@EJ
            F[:,loc]-=packet.a['Dhat'][cell]@EJ;participating+=1
        if cell%64==0:event(event='selected_principal_cell',cell=cell)
    a=packet.a;take=position[a['dr']]>=0
    np.add.at(F,(a['dp'][take],position[a['dr'][take]]),-a['dv'][take])
    # One forty-dimensional block solve with a matrix RHS; RHS width is
    # reported separately, not hidden as a single-vector solve cost.
    Cj=C[ids];HinvF=port_solve(F);A-=Cj@HinvF
    if not np.isfinite(A).all():raise ValueError('nonfinite closed principal block')
    return A,dict(assembly_seconds=perf_counter()-began,all_cells_visited=packet.nc,
        contributing_cells=participating,rows_sha256=array_hash(ids),Cj_sha256=array_hash(Cj),
        Fj_sha256=array_hash(F),port_matrix_RHS_columns=n,shared_Floquet_contributions_merged=True,
        F_C_adjoint_assumed=False,global_fine_matrix=False,owner_cell_filter=False,
        separate_curl_mass_condensation=False)


def factor_once(A,*,count=lambda k,n=1:None,guard=lambda:None):
    guard();count('joint_LU_attempts');began=perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter('error',LinAlgWarning)
        LU,piv=lu_factor(A,overwrite_a=False,check_finite=False)
    factor_seconds=perf_counter()-began;count('gecon_calls');count('gecon_triangular_pass_upper',22)
    count('total_triangular_pass_upper',22);started=perf_counter()
    rcond,info=get_lapack_funcs('gecon',(LU,))(LU,float(np.linalg.norm(A,1)),norm='1')
    return (LU,piv),dict(factor_seconds=factor_seconds,gecon_seconds=perf_counter()-started,
        rcond1_estimate=float(rcond),gecon_info=int(info),qualified=bool(info==0 and np.isfinite(rcond) and rcond>=1e-12),
        LU_sha256=array_hash(LU),pivots_sha256=array_hash(piv),partial_pivoting=True,
        shift=None,drop=None,refinement=0,gecon_internal_passes='unknown; conservative upper22 charged')


class JointSolve:
    def __init__(self,n,ids,A,factor,*,count=lambda k,n=1:None):
        self.n,self.ids,self.A,self.count=n,np.asarray(ids,np.int64),A,count
        self.factor=(factor[0],np.array(factor[1],copy=True))
        if A.shape!=factor[0].shape or A.shape!=(len(ids),len(ids)) or self.factor[1].shape!=(len(ids),):
            raise ValueError('joint factor inventory')
        self.calls=0;self.seconds=0.
    def solve(self,r):
        r=np.asarray(r,dtype=complex)
        if r.shape!=(len(self.ids),) or not np.isfinite(r).all():raise ValueError('joint solve RHS')
        self.count('joint_lu_solve');self.count('explicit_triangular_pass',2);self.count('total_triangular_pass_upper',2)
        started=perf_counter();x=lu_solve(self.factor,r,check_finite=False);self.seconds+=perf_counter()-started;self.calls+=1
        if not np.isfinite(x).all():raise ValueError('nonfinite joint solve')
        return x
    def apply(self,r):
        out=np.zeros(self.n,complex);out[self.ids]=self.solve(np.asarray(r)[self.ids]);return out


def pair(x,y):
    err=float(np.linalg.norm(x-y));scale=float(np.linalg.norm(x)+np.linalg.norm(y))
    return dict(error_norm=err,operation_scale=scale,operation_relative=relative(err,scale))


def qualification(joint,action,adjoint):
    records=[];solutions=[];vectors=[]
    for seed in SEEDS:
        rng=np.random.default_rng(seed);w=rng.standard_normal(len(joint.ids))+1j*rng.standard_normal(len(joint.ids))
        full=np.zeros(joint.n,complex);full[joint.ids]=w
        x=joint.solve(w);vectors.append(w);solutions.append(x)
        err=float(np.linalg.norm(joint.A@x-w));op=float(np.linalg.norm(joint.A,1)*np.linalg.norm(x,1)+np.linalg.norm(w,1))
        records.append(dict(seed=seed,forward=pair(joint.A@w,action(full)[joint.ids]),
            adjoint=pair(joint.A.conj().T@w,adjoint(full)[joint.ids]),
            solve_relative=err/np.linalg.norm(w),solve_operation_relative=relative(err,op)))
    repeat=pair(joint.solve(vectors[0]),solutions[0]);a,b=.4+.7j,-.3+.5j
    linear=pair(joint.solve(a*vectors[0]+b*vectors[1]),a*solutions[0]+b*solutions[1])
    zero=bool(np.count_nonzero(joint.solve(np.zeros(len(joint.ids),complex)))==0)
    good=(zero and repeat['operation_relative']<=1e-10 and linear['operation_relative']<=1e-10
        and all(v['forward']['operation_relative']<=1e-10 and v['adjoint']['operation_relative']<=1e-10
            and v['solve_relative']<=1e-8 and v['solve_operation_relative']<=1e-12 for v in records))
    return dict(witnesses=records,repeat=repeat,complex_linearity=linear,zero_exact=zero,qualified=bool(good))


def extra_direction(r,directions,images,cached_c,joint,action,*,bnorm,old_scales,
                    operation_scale=None,count=lambda k,n=1:None,guard=lambda:None):
    """One QR / <=9-coordinate GELSD workflow, using the saved old eight images."""
    began=perf_counter();r=np.asarray(r,complex);n=len(r);guard()
    if directions.shape!=images.shape or images.shape!=(n,8) or np.shape(cached_c)!=(8,):raise ValueError('old eight inventory')
    if not all(np.isfinite(v).all() for v in (r,directions,images,cached_c)) or not bnorm>0:raise ValueError('nonfinite diagnosis')
    qj=joint.apply(r);vj=action(qj);q57=directions[:,5]+directions[:,7];v57=images[:,5]+images[:,7]
    control=pair(action(q57),v57);rnorm=float(np.linalg.norm(r));norms=np.linalg.norm(images,axis=0);vnorm=float(np.linalg.norm(vj))
    if np.any(norms==0):raise ValueError('old zero columns cannot be a qualified baseline')
    new_scale=float(operation_scale(qj) if operation_scale else vnorm)
    W=np.column_stack((images/norms,vj/vnorm)) if vnorm else images/norms
    count('thin_decompositions');started=perf_counter();Q,R=qr(W,mode='economic',pivoting=False,check_finite=False)
    beta,_,rank,svals=lstsq(R,Q.conj().T@r,cond=1e-12,lapack_driver='gelsd',check_finite=False)
    c8=solve_triangular(R[:8,:8],Q[:,:8].conj().T@r,check_finite=False)/norms
    decomposition_seconds=perf_counter()-started
    e8=r-images@c8;eta8=relative(float(np.linalg.norm(e8)),rnorm)
    h=vj-Q[:,:8]@(Q[:,:8].conj().T@vj);hnorm=float(np.linalg.norm(h))
    resolved=bool(vnorm>0 and hnorm>64*EPS*new_scale and hnorm/vnorm>1e-12 and rank==9)
    coef=np.r_[c8,0j]
    if resolved:coef=np.r_[beta[:8]/norms,beta[8]/vnorm]
    residual=r-images@coef[:8]-coef[8]*vj;eta9=relative(float(np.linalg.norm(residual)),rnorm)
    actual=action(directions@coef[:8]+coef[8]*qj);difference=float(np.linalg.norm(actual-(r-residual)))
    op=float(np.dot(np.abs(coef[:8]),old_scales)+abs(coef[8])*new_scale)
    scale=float(np.linalg.norm(W)*(rnorm+np.linalg.norm(r-residual)))
    station=relative(float(np.linalg.norm(W.conj().T@residual)),scale)
    qr_error=float(np.linalg.norm(Q@R-W)/np.linalg.norm(W));ortho=float(np.linalg.norm(Q.conj().T@Q-np.eye(Q.shape[1]))/np.sqrt(Q.shape[1]))
    cached_error=float(np.linalg.norm(images@(c8-cached_c)))/bnorm
    g=None if eta8==0 else eta9/eta8
    ej_norm=float(np.linalg.norm(e8));inner=np.vdot(h,e8)
    support=np.zeros(n,bool);support[joint.ids]=True
    local_err=float(np.linalg.norm(joint.A@qj[joint.ids]-r[joint.ids]));local_scale=float(np.linalg.norm(joint.A,1)*np.linalg.norm(qj[joint.ids],1)+np.linalg.norm(r[joint.ids],1))
    local_relative=relative(local_err,float(np.linalg.norm(r[joint.ids])))
    local_operation=relative(local_err,local_scale)
    gates=dict(cached_eta8_identity=cached_error<=1e-11,control=control['operation_relative']<=1e-10,
        QR=qr_error<=1e-10 and ortho<=1e-10,stationarity=station is not None and station<=1e-8,
        recombination=difference/bnorm<=1e-11 and relative(difference,op) is not None and relative(difference,op)<=1e-10,
        local_solve=local_relative is not None and local_relative<=1e-8 and local_operation is not None and local_operation<=1e-12,
        outside_J_zero=bool(np.count_nonzero(qj[~support])==0),inequality=eta9<=eta8+1e-10)
    trustworthy=bool(all(gates.values()) and rnorm>0)
    status='DIAGNOSTIC_COMPLETE' if trustworthy and resolved else 'REDUNDANT_OR_UNRESOLVED' if trustworthy else 'NUMERICALLY_UNRESOLVED'
    metrics=dict(status=status,trustworthy=trustworthy,new_direction_resolved=resolved,gates=gates,
        eta8=eta8,eta9=eta9,g=g,rank=int(rank),singular_values=svals.tolist(),rank_threshold=1e-12,driver='gelsd',
        coefficients=[complex_value(z) for z in coef],residual_norm=rnorm,full_b_norm=bnorm,
        h_norm=hnorm,vj_norm=vnorm,h_over_vj=relative(hnorm,vnorm),h_operation_scale=new_scale,h_roundoff_floor=64*EPS*new_scale,
        h_e8_inner=complex_value(inner),h_e8_coherence=relative(float(abs(inner)),hnorm*ej_norm),
        conditional_squared_fraction_removed=None if g is None else 1-g*g,
        additional_squared_fraction_of_original_r=eta8*eta8-eta9*eta9,norm_reduction_relative_to_e8=None if g is None else 1-g,
        joint_response_leakage_outside_J=relative(float(np.linalg.norm(vj[~support])),vnorm),
        old57_response_leakage_outside_J=relative(float(np.linalg.norm(v57[~support])),float(np.linalg.norm(v57))),
        same_support_direction_difference=pair(qj,q57),same_support_response_difference=pair(vj,v57),old57_original_action=control,
        regions={name:dict(old_e8_norm=float(np.linalg.norm(e8[mask])),new_e9_norm=float(np.linalg.norm(residual[mask])),
            original_r_norm=float(np.linalg.norm(r[mask]))) for name,mask in [('inside_J',support),('outside_J',~support)]},
        QR_relative=qr_error,orthogonality_relative=ortho,stationarity_operation_relative=station,
        old_cached_response_difference_full_b_relative=cached_error,local_solve_relative=relative(local_err,float(np.linalg.norm(r[joint.ids]))),
        independent_recombination=dict(full_b_relative=difference/bnorm,current_r_relative=relative(difference,rnorm),operation_relative=relative(difference,op)),
        decomposition_seconds=decomposition_seconds,diagnostic_seconds=perf_counter()-began,new_solver_state=False)
    return metrics,dict(joint_direction=qj,joint_image=vj,innovation=h,coefficients=coef,old_e8=e8,diagnostic_residual=r-actual)


def decision(rows):
    names=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')
    if len(rows)!=2 or {x.get('name') for x in rows}!=set(names):return 'NUMERICALLY_UNRESOLVED'
    if not all(x['trustworthy'] for x in rows):return 'NUMERICALLY_UNRESOLVED'
    if all(x['new_direction_resolved'] and x['g'] is not None and x['g']<=.75 for x in rows):return 'JOINT_EXTRA_DIRECTION_SIGNAL'
    if all(not x['new_direction_resolved'] or x['g']>=.95 for x in rows):return 'FIXED_JOINT_DIRECTION_INSUFFICIENT'
    return 'STATE_DEPENDENT_INCONCLUSIVE'
