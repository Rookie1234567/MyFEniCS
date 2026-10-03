"""A single rank-deficient J -> O -> J direction, not a full-space PC."""
from pathlib import Path
from time import perf_counter
import gc
import hashlib
import numpy as np
from scipy.linalg import lu_solve, qr, lstsq, solve_triangular

from src.solvers.neural_fe_action_packet import file_hash
from src.solvers.joint_block_direction import pair
from src.solvers.block_residual_direction import EPS, relative, complex_value

FAMILY='FIXED_J_OUTER_J_RETURN_DIRECTION_DIAGNOSTIC'
NAMES=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')
OUTER_BLOCKS=(0,1,2,3,4,6)


def stream_array_hash(a,guard=lambda:None):
    """Hash canonical C-order bytes without a whole mmap/hash copy."""
    digest=hashlib.sha256()
    for start in range(0,len(a),64):
        guard();digest.update(np.ascontiguousarray(a[start:start+64]).tobytes())
    return digest.hexdigest()


class SelectedBundle:
    """One readonly A/LU/pivot bundle and a private f2py pivot workspace."""
    def __init__(self,item,allowed,*,kind,count=lambda k,n=1:None,guard=lambda:None):
        count('factor_readers');began=perf_counter();self.rows=np.asarray(item['rows'],np.int64)
        if self.rows.ndim!=1 or np.any(np.diff(self.rows)<=0):raise ValueError('canonical bundle row order')
        self.count,self.kind=count,kind;self.loaded=[];self.receipts=[];self.calls=0;self.RHS_columns=0;self.seconds=0.
        for key in ('matrix','LU','pivots'):
            receipt=item[key];path=Path(receipt['path']).resolve();guard()
            if not path.is_relative_to(allowed) or file_hash(path)!=receipt['sha256']:raise ValueError('factor container path/hash')
            value=np.load(path,mmap_mode='r',allow_pickle=False)
            expected=(len(self.rows),) if key=='pivots' else (len(self.rows),len(self.rows))
            if value.shape!=expected or list(value.shape)!=receipt['shape'] or value.flags.writeable:
                raise ValueError('factor member shape/readonly')
            if (key!='pivots' and value.dtype!=np.complex128) or (key=='pivots' and value.dtype.kind not in 'iu'):
                raise ValueError('fixed complex128 factor/pivot type')
            if stream_array_hash(value,guard)!=receipt['array_sha256']:raise ValueError('factor member hash')
            self.loaded.append(value)
            self.receipts.append(dict(key=key,path=str(path),container_sha256=receipt['sha256'],
                array_sha256=receipt['array_sha256'],file_bytes=path.stat().st_size,array_bytes=value.nbytes,
                container_stream_hash_reads=1,numeric_mmap_loads=1,array_hash_scans=1,readonly=True,
                hash_chunk_rows=64,full_hash_copy=False))
        self.A,self.LU,self.pivot_mmap=self.loaded
        self.pivots=np.array(self.pivot_mmap,copy=True)
        self.A1=float(np.linalg.norm(self.A,1));self.load_seconds=perf_counter()-began

    def solve(self,rhs):
        rhs=np.asarray(rhs,complex)
        if rhs.shape!=(len(self.rows),) or not np.isfinite(rhs).all():raise ValueError('one vector RHS required')
        self.count(self.kind+'_lu_solve');self.count('explicit_triangular_pass',2)
        began=perf_counter();out=lu_solve((self.LU,self.pivots),rhs,check_finite=False)
        self.seconds+=perf_counter()-began;self.calls+=1;self.RHS_columns+=1
        if not np.isfinite(out).all():raise ValueError('nonfinite readonly factor solve')
        return out

    def witnesses(self,seeds,action=None,adjoint=None,n=None):
        rows=[]
        for seed in seeds:
            rng=np.random.default_rng(seed);r=rng.standard_normal(len(self.rows))+1j*rng.standard_normal(len(self.rows))
            x=self.solve(r);err=float(np.linalg.norm(self.A@x-r))
            operand=self.A1*np.linalg.norm(x,1)+np.linalg.norm(r,1)
            row=dict(seed=seed,solve_relative=err/np.linalg.norm(r),solve_error_norm=err,
                rhs_norm=float(np.linalg.norm(r)),solve_operand_scale=float(operand),
                solve_operation_relative=relative(err,operand))
            if action is not None:
                full=np.zeros(n,complex);full[self.rows]=r
                row['original_principal_action']=pair(self.A@r,action(full)[self.rows])
                if adjoint is not None:row['original_adjoint_action']=pair(self.A.conj().T@r,adjoint(full)[self.rows])
            rows.append(row)
        good=all(x['solve_relative']<=1e-8 and x['solve_operation_relative']<=1e-12
                 and all(v['operation_relative']<=1e-10 for k,v in x.items() if k.startswith('original_')) for x in rows)
        return dict(qualified=bool(good),witnesses=rows,private_writable_pivot_bytes=self.pivots.nbytes,
            load_seconds=self.load_seconds,files=self.receipts,refactored=False)

    def close(self):
        # Close this process's mappings explicitly; RSS observations still do
        # not prove that the system's file cache has been reclaimed.
        for a in self.loaded:a._mmap.close()
        self.loaded=[];self.A=self.LU=self.pivot_mmap=None;gc.collect()


def return_direction(qj,w,joint_solve,joint_rows,action,operation_scale=None):
    aw=action(w)
    ws=operation_scale(w) if operation_scale else float(np.linalg.norm(aw))
    back=np.zeros_like(w);back[joint_rows]=joint_solve(aw[joint_rows])
    d=-w+back;ad=action(d)
    ds=operation_scale(d) if operation_scale else float(np.linalg.norm(ad))
    aback=action(back)
    bs=operation_scale(back) if operation_scale else float(np.linalg.norm(aback))
    qret=qj+d;aret=action(qret)
    rs=operation_scale(qret) if operation_scale else float(np.linalg.norm(aret))
    return dict(w=w,aw=aw,feedback=back,direction=d,image=ad,feedback_image=aback,
                return_direction=qret,return_image=aret,
                action_operation_scales=dict(w=ws,d=ds,feedback=bs,qret=rs))


def extend_nine(r,Q9,W9,cached_c9,cached_e9,d,ad,action,*,bnorm,old_scales,new_scale,
                count=lambda k,n=1:None):
    """Exactly one <=10-column QR/GELSD workflow, including its 9-column baseline."""
    began=perf_counter();r=np.asarray(r,complex);n=len(r)
    if Q9.shape!=W9.shape or W9.shape!=(n,9) or np.shape(cached_c9)!=(9,):raise ValueError('nine direction inventory')
    if not bnorm>0 or not all(np.isfinite(a).all() for a in (r,Q9,W9,cached_c9,cached_e9,d,ad)):
        raise ValueError('nonfinite return diagnostic')
    rn=float(np.linalg.norm(r));norms=np.linalg.norm(W9,axis=0);an=float(np.linalg.norm(ad))
    if rn==0 or np.any(norms==0):raise ValueError('nonzero residual and qualified nine baseline required')
    W=np.column_stack((W9/norms,ad/an)) if an else W9/norms
    count('thin_decompositions');started=perf_counter()
    Z,R=qr(W,mode='economic',pivoting=False,check_finite=False)
    beta,_,rank,svals=lstsq(R,Z.conj().T@r,cond=1e-12,lapack_driver='gelsd',check_finite=False)
    c9=solve_triangular(R[:9,:9],Z[:,:9].conj().T@r,check_finite=False)/norms
    thin_seconds=perf_counter()-started;e9=r-W9@c9;eta9=float(np.linalg.norm(e9)/rn)
    h=ad-Z[:,:9]@(Z[:,:9].conj().T@ad);hn=float(np.linalg.norm(h));floor=64*EPS*new_scale
    # A certificate from the SAME existing QR, independent of the new beta.
    p9=solve_triangular(R[:9,:9],Z[:,:9].conj().T@ad,check_finite=False)/norms
    resolved=bool(an>0 and hn>floor and hn/an>1e-12 and rank==10)
    coef=np.r_[c9,0j]
    if resolved:coef=np.r_[beta[:9]/norms,beta[9]/an]
    thin=r-W9@coef[:9]-coef[9]*ad;actual=action(Q9@coef[:9]+coef[9]*d)
    e10=r-actual;eta10=float(np.linalg.norm(e10)/rn);err=float(np.linalg.norm(actual-(r-thin)))
    op=float(np.dot(abs(coef[:9]),old_scales)+abs(coef[9])*new_scale)
    qualified_W=W if resolved else W[:,:9]
    station=relative(float(np.linalg.norm(qualified_W.conj().T@thin)),float(np.linalg.norm(qualified_W)*(rn+np.linalg.norm(r-thin))))
    qr_error=float(np.linalg.norm(Z@R-W)/np.linalg.norm(W));orth=float(np.linalg.norm(Z.conj().T@Z-np.eye(Z.shape[1]))/np.sqrt(Z.shape[1]))
    baseline_diff=float(np.linalg.norm(W9@(c9-cached_c9))/bnorm)
    e9_diff=float(np.linalg.norm(e9-cached_e9)/bnorm)
    baseline_actual=action(Q9@c9);baseline_original=float(np.linalg.norm(baseline_actual-(r-e9))/bnorm)
    g=None if eta9==0 else eta10/eta9
    gates=dict(baseline_identity=max(baseline_diff,e9_diff,baseline_original)<=1e-11,
        QR=qr_error<=1e-10 and orth<=1e-10,stationarity=station<=1e-8,
        original_recombination=err/bnorm<=1e-11 and relative(err,op)<=1e-10,
        inequality=eta10<=eta9+1e-10)
    trustworthy=all(gates.values())
    metrics=dict(status='DIAGNOSTIC_COMPLETE' if trustworthy and resolved else 'REDUNDANT_OR_UNRESOLVED' if trustworthy else 'NUMERICALLY_UNRESOLVED',
        trustworthy=bool(trustworthy),new_direction_resolved=resolved,gates=gates,eta9=eta9,eta10=eta10,g10=g,
        rank=int(rank),rank_threshold=1e-12,driver='gelsd',singular_values=svals.tolist(),
        residual_norm=rn,full_b_norm=bnorm,h_norm=hn,ad_norm=an,h_over_ad=relative(hn,an),
        h_operation_scale=new_scale,h_roundoff_floor=floor,h_e9_inner=complex_value(np.vdot(h,e9)),
        h_e9_coherence=relative(float(abs(np.vdot(h,e9))),hn*np.linalg.norm(e9)),
        norm_reduction_relative_to_e9=None if g is None else 1-g,
        squared_fraction_removed_relative_to_e9=None if g is None else 1-g*g,
        old_cached_response_difference_full_b_relative=baseline_diff,old_e9_difference_full_b_relative=e9_diff,
        old_nine_original_response_full_b_relative=baseline_original,QR_relative=qr_error,orthogonality_relative=orth,
        stationarity_operation_relative=station,
        stationarity_scope='nine_plus_resolved_innovation' if resolved else 'qualified_nine_baseline',
        independent_recombination=dict(full_b_relative=err/bnorm,current_r_relative=err/rn,operation_relative=relative(err,op)),
        coefficients=[complex_value(x) for x in coef],decomposition_seconds=thin_seconds,
        diagnostic_seconds=perf_counter()-began,new_solver_state=False)
    return metrics,dict(direction=d,image=ad,innovation=h,projection_coefficients=p9,
        coefficients=coef,baseline_coefficients=c9,old_e9=e9,diagnostic_residual=e10,
        original_combination_image=actual,original_baseline_image=baseline_actual,
        thin_Q=Z,thin_R=R,input_residual=r)


def decision(rows):
    if len(rows)!=2 or {x.get('name') for x in rows}!=set(NAMES) or not all(x['trustworthy'] for x in rows):
        return 'NUMERICALLY_UNRESOLVED'
    if all(x['new_direction_resolved'] and x['g10'] is not None and x['g10']<=.75 for x in rows):return 'RETURN_EXTRA_DIRECTION_SIGNAL'
    if all(not x['new_direction_resolved'] for x in rows):return 'REDUNDANT_OR_UNRESOLVED'
    if all(x['g10'] is not None and x['g10']>=.95 for x in rows):return 'FIXED_RETURN_DIRECTION_INSUFFICIENT'
    return 'STATE_DEPENDENT_INCONCLUSIVE'
