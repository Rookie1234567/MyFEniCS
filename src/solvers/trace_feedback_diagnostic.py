"""Two frozen residual transfers using already-owned factors; no PC selection."""
import time
import numpy as np

from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .bounded_trace_pc import csr_load,restrict


def transfers(pc,bhat,action,folder,scope):
    start=time.monotonic();inputs=[('physical_RHS',bhat)];rows=[];missing=None
    parent=scope.checked_json(scope.plan_record()['prior_failed_candidate'])
    # Only the failed retained residual is permitted here; not a new initial value.
    try:
        a=checked_arrays(parent['retained_returned'])
        if not np.array_equal(a['scaled_rhs'],bhat):raise ValueError('V72 failed residual RHS identity')
        inputs.append(('V72_failed_residual',bhat-action(a['scaled_retained'])))
        del a
    except (OSError,KeyError) as exc:missing=repr(exc)
    E0=csr_load(scope.parent_preparation()['coarse_matrix'])
    for name,r in inputs:
        if time.monotonic()-start>=1800:break
        coarse=[]
        def C(v):
            z=pc.coarse_apply(v);w=pc.last_coarse
            defect=E0@w['solution']-w['rhs']
            coarse.append(dict(absolute=float(np.linalg.norm(defect)),relative=relative(defect,w['rhs']),
                rhs_norm=float(np.linalg.norm(w['rhs']))))
            return z
        zc=C(r);Azc=pc.original_apply(zc);rc=r-Azc
        v=pc.local_apply(rc);Av=pc.original_apply(v);feedback=C(Av);Af=pc.original_apply(feedback)
        m1=r-Azc-Av;m2=m1+Af
        zrhs=restrict(pc.Z,r);z1=restrict(pc.Z,m1);z2=restrict(pc.Z,m2)
        scale=sum(float(np.linalg.norm(restrict(pc.Z,x))) for x in (r,Azc,Av,Af))
        fixed=float(np.linalg.norm(z2))/max(scale,1e-300)
        denom=np.vdot(Av,Av);alpha=0j if denom==0 else np.vdot(Av,rc)/denom
        rec=save_arrays(folder/(name+'_transfer.npz'),r=r,Cr=zc,Azc=Azc,rc=rc,Brc=v,ABrc=Av,
            C_ABrc=feedback,A_C_ABrc=Af,M1_residual=m1,M2_residual=m2,
            coarse_rhs=zrhs,coarse_M1=z1,coarse_M2=z2)
        scores={k:dict(absolute=float(np.linalg.norm(x)),original_RHS_scaled=relative(x,bhat),
            operation_scaled=float(np.linalg.norm(x))/max(sum(np.linalg.norm(y) for y in (r,Azc,Av,Af)),1e-300))
            for k,x in [('r',r),('rc',rc),('M1',m1),('M2',m2)]}
        rows.append(dict(input=name,arrays=rec,scores=scores,coarse_solves=coarse,
            coarse_balance_absolute=float(np.linalg.norm(z2)),coarse_balance_operation_scale=scale,
            coarse_balance_operation_scaled=fixed,balanced_pass=fixed<=1e-8 and all(x['relative']<=1e-8 for x in coarse),
            diagnostic_optimal_scalar=[float(alpha.real),float(alpha.imag)],
            diagnostic_only_optimal_residual=relative(rc-alpha*Av,bhat)))
        write_json(folder/'residual_transfer_progress.json',dict(rows=rows,elapsed_seconds=time.monotonic()-start,missing=missing))
    result=dict(rows=rows,missing=missing,elapsed_seconds=time.monotonic()-start,maximum_seconds=1800,
        pass_gate=bool(rows and all(r['balanced_pass'] for r in rows)),
        diagnostic_only=True,formal_PC_scalars_unchanged=True)
    write_json(folder/'residual_transfers.json',result)
    write_json(scope.window.TMP/'balanced_qualification.json',dict(pass_gate=result['pass_gate'],
        source=scope.plan_record()['review_commit'],rows=[dict(input=r['input'],coarse_balance_operation_scaled=r['coarse_balance_operation_scaled'],
            coarse_balance_absolute=r['coarse_balance_absolute'],coarse_solves=r['coarse_solves']) for r in rows]))
    return result
