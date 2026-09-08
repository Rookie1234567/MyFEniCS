"""Statistics of matched-reference errors; existing callbacks own FE numerics."""
import numpy as np
from .physical_error_diagnostics import copied_apply,metric_square,correction_diagnostics


def error_identity(action,xref,xi,ri,rref,axref,axi):
    values=[np.asarray(v) for v in (xref,xi,ri,rref,axref,axi)]
    if any(v.shape!=values[0].shape or not np.isfinite(v).all() for v in values):
        raise ValueError('actual-error coordinates differ or are nonfinite')
    e=values[0]-values[1];q=copied_apply(action,e);difference=q-(ri-rref)
    scale=max(np.linalg.norm(axref)+np.linalg.norm(axi)+np.linalg.norm(q),np.finfo(float).tiny)
    return dict(e=e,q=q,residual_difference=ri-rref,closure_vector=difference,
        closure_relative_to_operations=float(np.linalg.norm(difference)/scale),operation_scale=float(scale),
        roles=dict(e='primal x_ref-x_i',q='dual A6e',residual_difference='r_i-r_ref'))


def saved_pc_error(mass,e,ri,rref,packet):
    if any(np.shape(v)!=np.shape(e) or not np.isfinite(v).all() for v in (e,ri,rref)):
        raise ValueError('invalid saved-PC error coordinates')
    scale=float(packet['normalization_scale'])
    if not np.isfinite(scale) or scale<=0:raise ValueError('invalid saved PC normalization')
    q=np.asarray(packet['normalized_q'])
    if (q.shape!=np.shape(e) or not np.isfinite(q).all() or
        np.linalg.norm(scale*q-ri)>1e-12*max(np.linalg.norm(ri),np.finfo(float).tiny)):
        raise ValueError('saved PC input does not match frozen actual residual')
    outputs={}
    for name,result in packet['profiles'].items():
        outputs[name]=correction_diagnostics(None,mass,np.asarray(e)/scale,q,result['correction'],
                                           saved_applied_direction=result['applied_direction'])
    return dict(normalization_scale=scale,normalized_error=np.asarray(e)/scale,
        normalized_old_residual=q,normalized_Ae=q-np.asarray(rref)/scale,
        reference_residual_gap=np.asarray(rref)/scale,profiles=outputs,
        new_PC_calls=0,new_A6_calls=0,MR_policy='analytic coefficient on saved q/z/Az; no PC rerun')


def cell_energy_summary(cells,global_mass,global_curl):
    """Partition owned-cell integrals, never count shared coefficients as energy."""
    mass=np.asarray(cells['mass']);curl=np.asarray(cells['curl'])
    tags=np.asarray(cells['material_tags']);z=np.asarray(cells['cell_centers'])[:,2]
    if mass.shape!=curl.shape or mass.shape!=tags.shape or len(z)!=len(mass):
        raise ValueError('cell energy shapes differ')
    if not np.isfinite(mass).all() or not np.isfinite(curl).all():raise ValueError('nonfinite cell energy')
    totals=dict(mass=float(mass.sum()),curl=float(curl.sum()))
    defects={name:abs(totals[name]-target)/max(abs(target),np.finfo(float).tiny)
             for name,target in [('mass',global_mass),('curl',global_curl)]}
    def groups(labels):
        return {str(key):dict(cells=int(np.sum(labels==key)),mass=float(mass[labels==key].sum()),
                            curl=float(curl[labels==key].sum())) for key in np.unique(labels)}
    return dict(totals=totals,global_relative_defects=defects,materials=groups(tags),
                height_layers=groups(z),partition_rule='owned cell integrals, exact saved centroid z layers')


def coarse_gap_closure(A4,PH,A6,projection,coarse_result,mass):
    """Expose the physical coarse response to the complementary error."""
    c=projection['coarse'];cg=coarse_result['coarse'];delta=c-cg
    gparallel=copied_apply(PH,copied_apply(A6,projection['parallel']))
    gperp=copied_apply(PH,copied_apply(A6,projection['perpendicular']))
    adelta=copied_apply(A4,delta);closure=adelta+gperp
    scale=max(np.linalg.norm(adelta)+np.linalg.norm(gparallel)+np.linalg.norm(gperp),np.finfo(float).tiny)
    gap=projection['parallel']-coarse_result['dg']
    gap_energy=metric_square(mass,gap);perp_energy=projection['perpendicular_energy']
    return dict(g_parallel=gparallel,g_perp=gperp,coarse_difference=delta,A4_coarse_difference=adelta,
        closure_vector=closure,closure_relative_to_operations=float(np.linalg.norm(closure)/scale),
        operation_scale=float(scale),coarse_response_gap_energy=gap_energy,
        gap_over_complement_field_ratio=float(np.sqrt(gap_energy/max(perp_energy,np.finfo(float).tiny))),
        projection_qualified=projection['status']=='PROJECTION_CLOSED',
        interpretation='A4(c-cG)+PH A6 e_perp; response amplification diagnostic, not a condition-number estimate')
