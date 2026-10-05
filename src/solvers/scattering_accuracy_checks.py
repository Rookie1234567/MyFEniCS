"""Independent byte-bound full-port checker; no FE or PDE action is built."""
import numpy as np
from .scattering_anchor_checks import checked_arrays


def norm_pair(x,y):
    x=np.asarray(x);y=np.asarray(y)
    scale=max(float(np.max(np.abs(x),initial=0)),float(np.max(np.abs(y),initial=0)))
    if scale==0:return dict(relative=None,absolute=0.,operation_scaled=0.,zero_reference=True,pass_gate=True)
    delta=float(np.linalg.norm((x-y)/scale));den=float(np.linalg.norm(y/scale));xn=float(np.linalg.norm(x/scale))
    absolute=delta*scale
    return dict(relative=delta/den if den else None,absolute=absolute,
        operation_scaled=delta/max(xn,den),zero_reference=den==0,
        pass_gate=(absolute<=1e-12 if den==0 else delta/den<=1e-11) and delta/max(xn,den)<=1e-10)


def packed_pair(a,b):
    rows=[]
    for i in range(532):
        sa=slice(a['offsets'][i],a['offsets'][i+1]);sb=slice(b['offsets'][i],b['offsets'][i+1])
        rr=np.union1d(a['rows'][sa],b['rows'][sb]);r={}
        for label in ('C','D'):
            x=np.zeros(len(rr),complex);y=x.copy()
            x[np.searchsorted(rr,a['rows'][sa])]=a[label][sa];y[np.searchsorted(rr,b['rows'][sb])]=b[label][sb]
            r[label]=norm_pair(x,y)
        r.update(index=i,H_equal=bool(a['H'][i]==b['H'][i]));r['pass_gate']=r['H_equal'] and all(r[k]['pass_gate'] for k in ('C','D'))
        rows.append(r)
    return dict(rows=rows,pass_gate=all(r['pass_gate'] for r in rows),
        max_relative=max((r[k]['relative'] or 0) for r in rows for k in ('C','D')))


def packed_action(a,x,adjoint=False):
    out=np.zeros_like(x)
    for i in range(532):
        sl=slice(a['offsets'][i],a['offsets'][i+1]);ids=a['rows'][sl]
        if adjoint:values=np.conj(a['D'][sl])*np.vdot(a['C'][sl],x[ids])/np.conj(a['H'][i])
        else:values=a['C'][sl]*np.dot(a['D'][sl],x[ids])/a['H'][i]
        np.add.at(out,ids,values)
    return out


def check_boundary(record):
    rows=[]
    if [r['degree'] for r in record['rows']]!=[4,5]:raise ValueError('exact two degree inventory')
    for r in record['rows']:
        if not r.get('preserve_all_nonzero_rows'):raise ValueError('previous shared-pruning run is not full inventory authority')
        arrays={k:checked_arrays(v) for k,v in r['arrays'].items()};w=checked_arrays(r['witness'])
        for a in arrays.values():
            if len(a['offsets'])!=533 or a['offsets'][0]!=0 or a['offsets'][-1]!=len(a['rows']) or np.any(np.diff(a['offsets'])<0):raise ValueError('complete532 packed offsets')
            if a['C'].shape!=a['D'].shape or a['H'].shape!=(532,) or not np.all(np.isfinite(a['H'])) or np.any(a['H']<=0):raise ValueError('packed values/H')
            if np.any(a['rows']<0) or np.any(a['rows']>=len(w['input'])):raise ValueError('canonical native row range')
        high=packed_pair(arrays['q47'],arrays['q63']);old=packed_pair(arrays['original'],arrays['q63']);untrimmed=packed_pair(arrays['original_untrimmed'],arrays['q63'])
        witnesses={}
        for k,label in (('q47','47'),('q63','63'),('original','_old')):
            for direction in ('forward','adjoint'):
                recomputed=packed_action(arrays[k],w['input'],adjoint=direction=='adjoint')
                witnesses[k+'_'+direction]=norm_pair(recomputed,w[direction+label])
        incident=norm_pair(arrays['q47']['incident_traction'],arrays['q63']['incident_traction'])
        rows.append(dict(degree=r['degree'],mode_sha256=r['mode_sha256'],high=high,legacy=old,original_untrimmed=untrimmed,
            witnesses=witnesses,incident=incident,pass_gate=high['pass_gate'] and incident['pass_gate'] and all(v['pass_gate'] for v in witnesses.values())))
    return dict(status='INDEPENDENT_FULL_532_CHECK',rows=rows,pass_gate=all(r['pass_gate'] for r in rows),
        relative_scale='nonzero reference with pre-scaling, no1e-30 floor; exact zero uses1e-12 absolute',
        scientific_A_calls=0,source_parent=record['source_sha'])


def saved_modal_effects(boundary,attribution):
    """Decompose the fixed old field's boundary change, not a new solve.

    Each complete mode is contracted before taking its norm. The sum retains
    cancellation across modes and is paired with the saved full residual.
    Both clipped and untrimmed old native inventories remain distinguishable.
    """
    from .scattering_anchor_scope import stage as old_stage
    from .scattering_accuracy import configuration
    from .fullspace_dtn_action import build_dynamic_mode_inventory
    from .dtn_port_3d import _incident_projection_onto_top_mode
    rows=[]
    for b,r in zip(boundary['rows'],attribution['saved_original_equation_rechecks'],strict=True):
        degree=b['degree'];cfg=configuration('NOTCH',degree)
        modes,identities,_=build_dynamic_mode_inventory(cfg)
        if len(modes)!=532 or r['degree']!=degree:raise ValueError('modal effect inventory')
        old=old_stage('REFERENCE_NOTCH' if degree==4 else 'REFERENCE_NOTCH_P5')
        state=checked_arrays(old['arrays']);new=checked_arrays(r['arrays47']);u=state['u_storage']
        packed={k:checked_arrays(b['arrays'][k]) for k in ('q47','original','original_untrimmed')}
        inc=np.asarray([_incident_projection_onto_top_mode(m,cfg) for m in modes]);totals={k:np.zeros_like(u) for k in packed}
        differences={k:np.zeros_like(u) for k in ('original','original_untrimmed')};per=[];diagonal={k:0. for k in differences}
        for i,identity in enumerate(identities):
            contributions={}
            for k,a in packed.items():
                sl=slice(a['offsets'][i],a['offsets'][i+1]);ids=a['rows'][sl]
                values=a['C'][sl]*(np.dot(a['D'][sl],u[ids])/a['H'][i]-inc[i])
                contributions[k]=(ids,values);np.add.at(totals[k],ids,values)
            row={k:identity[k] for k in ('mode_index','side','m','n','polarization')}
            for k in differences:
                delta=np.zeros_like(u)
                for factor,key in ((1,'q47'),(-1,k)):
                    ids,values=contributions[key];np.add.at(delta,ids,factor*values)
                np.add.at(differences[k],np.arange(len(u)),delta)
                n=float(np.linalg.norm(delta));diagonal[k]+=n*n
                j=int(np.argmax(np.abs(delta)))
                row[k+'_delta_norm']=n;row[k+'_largest_native_row']=j
                row[k+'_largest_native_value']=[float(delta[j].real),float(delta[j].imag)]
            per.append(row)
        # Residual = traction - V*u - C*(D*u/H - incident).
        predicted=packed['q47']['incident_traction']-packed['original']['incident_traction']-differences['original']
        actual=new['residual']-state['residual']
        operation_scale=np.linalg.norm(new['rhs'])+np.linalg.norm(state['rhs'])+np.linalg.norm(predicted)
        identity=float(np.linalg.norm(predicted-actual)/max(operation_scale,1e-300))
        if identity>1e-10:raise ValueError('saved old/new boundary residual decomposition identity')
        rows.append(dict(degree=degree,mode_count=532,per_mode=per,
            sum_change_norms={k:float(np.linalg.norm(v)) for k,v in differences.items()},
            diagonal_squared=diagonal,cross_squared={k:float(np.linalg.norm(differences[k])**2-diagonal[k]) for k in differences},
            old_new_residual_identity_operation_scaled=identity,
            parent_old_array=old['arrays']['sha256'],parent_new_array=r['arrays47']['sha256'],
            q47_parent= b['arrays']['q47']['sha256'],
            meaning='old clipped carrier and old untrimmed quadrature separated; all mode sums assembled before norms'))
    return dict(rows=rows,new_FE_volume_actions=0,new_PDE_solves=0)
