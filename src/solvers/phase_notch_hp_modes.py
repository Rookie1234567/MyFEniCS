"""Physical-key mode comparisons and actual old-field 828 projections.

"""
import json
from pathlib import Path
import numpy as np
from .scattering_anchor import relative,save_arrays
from .scattering_anchor_checks import checked_arrays


AMPLITUDES=('auxiliary_amplitude_total_projection','outgoing_amplitude','outgoing_amplitude_at_boundary')


def finite_mode_ranges(count):
    """The three preregistered finite inventories; never silently downgrade."""
    try:return {532:(9,3),828:(11,4),1188:(13,5)}[count]
    except (KeyError,TypeError) as error:raise ValueError('unknown finite mode inventory') from error


def keyed_modes(payload,expected):
    rows=payload['orders'];planes=payload['reference_planes']
    if len(rows)!=expected:raise ValueError('full finite inventory count')
    indexed={}
    for row in rows:
        side=row['side'];key=(side,int(row['m']),int(row['n']),row['polarization'],float(planes[side+'_z']))
        if side not in ('top','bottom') or row['polarization'] not in ('s','p') or key in indexed:raise ValueError('physical mode key duplication')
        indexed[key]=row
    m,n=finite_mode_ranges(expected)
    full={(side,i,j,pol,float(planes[side+'_z'])) for side in ('top','bottom') for i in range(-m,m+1) for j in range(-n,n+1) for pol in ('s','p')}
    if set(indexed)!=full:raise ValueError('manual complete physical mode key inventory')
    return indexed


def compare_payloads(first,second,expected):
    if first['reference_planes']!=second['reference_planes']:raise ValueError('physical mode reference planes changed')
    a,b=keyed_modes(first,expected),keyed_modes(second,expected);keys=sorted(a);out={};vectors={}
    for name in AMPLITUDES:
        x=np.asarray([complex(*a[k][name]) for k in keys]);y=np.asarray([complex(*b[k][name]) for k in keys])
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):raise ValueError('nonfinite mode complex vector')
        vectors[name+'_first']=x;vectors[name+'_second']=y
        out[name+'_relative']=relative(y-x,x);out[name+'_max_absolute']=float(np.max(np.abs(y-x)))
    x=np.asarray([a[k]['power_ratio'] for k in keys]);y=np.asarray([b[k]['power_ratio'] for k in keys])
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):raise ValueError('nonfinite individual mode power')
    out.update(mode_count=expected,mode_power_max_absolute=float(np.max(np.abs(y-x))),
        pairing='side,m,n,polarization,physical reference plane; independent of auxiliary index')
    vectors.update(power_first=x,power_second=y,physical_keys_json_utf8=np.frombuffer(json.dumps(keys).encode(),np.uint8))
    if expected in (828,1188):
        old=532 if expected==828 else 828;m,n=finite_mode_ranges(old)
        common=np.asarray([abs(k[1])<=m and abs(k[2])<=n for k in keys]);added=~common
        if common.sum()!=old or added.sum()!=expected-old:raise ValueError('finite inventory partition')
        out['partitions']={}
        for label,mask in ((f'common{old}',common),(f'added{expected-old}',added)):
            raw=vectors['outgoing_amplitude_at_boundary_first'];candidate=vectors['outgoing_amplitude_at_boundary_second']
            out['partitions'][label]=dict(count=int(mask.sum()),physical_amplitude_relative=relative(candidate[mask]-raw[mask],raw[mask]),
                physical_amplitude_difference_norm=float(np.linalg.norm(candidate[mask]-raw[mask])),reference_norm=float(np.linalg.norm(raw[mask])),
                power_max_absolute=float(np.max(np.abs(y[mask]-x[mask]))))
    return out,vectors


def mode_comparison(first,second,folder):
    payloads=[json.loads(Path(r.get('mode_power_path',Path(r['output']['fields']['path']).with_name('port_power.json'))).read_text()) for r in (first,second)]
    counts=[len(x['orders']) for x in payloads]
    if counts[0]!=counts[1]:raise ValueError('project both fields to one complete finite inventory before comparison')
    r,v=compare_payloads(*payloads,counts[0]);r['arrays']=save_arrays(Path(folder)/'physical_mode_comparison.npz',**v)
    return r


def project_saved_parent(parent,bundle,geometry,folder,journal):
    """Project an unchanged 532 solution onto all 828 actual surface functionals."""
    from petsc4py import PETSc
    from .dtn_port_3d import _port_power_metrics,_write_port_outputs
    cfg=bundle['cfg'];values=checked_arrays(parent['arrays'])
    new_count=len(bundle['modes']);old_count=parent['case_spec']['complete_modes']
    if (old_count,new_count) not in ((532,828),(828,1188)):raise ValueError('conditional finite mode projection identity')
    for key in geometry:
        if not np.array_equal(geometry[key],values[key]):raise ValueError('mode projection same mesh '+key)
    if not np.array_equal(values['kappa'],bundle['kappa']):raise ValueError('mode projection physical carrier')
    sub=Path(folder)/f'parent_projected{new_count}';sub.mkdir(exist_ok=False)
    source=PETSc.Vec().createSeq(len(values['u_storage']),comm=PETSc.COMM_SELF);source.array[:]=values['u_storage']
    try:
        with journal.measured(f'parent_actual_all{new_count}_surface_projection'):
            port=bundle['dtn_action'].recover_auxiliary(source)
            pm=_port_power_metrics(cfg,list(bundle['modes']),port,list(bundle['incident_projections']))
            _write_port_outputs(sub,cfg,list(bundle['modes']),port,list(bundle['incident_projections']),pm,bundle['setup']['mesh'].comm)
        journal.calls['port_recovery']=journal.calls.get('port_recovery',0)+1
    finally:source.destroy()
    receipt=save_arrays(sub/'projected_ports.npz',port=port)
    old=json.loads(Path(parent['output']['fields']['path']).with_name('port_power.json').read_text())
    new=json.loads((sub/'port_power.json').read_text());oi=keyed_modes(old,old_count);ni=keyed_modes(new,new_count)
    x=np.asarray([complex(*oi[k]['outgoing_amplitude_at_boundary']) for k in sorted(oi)])
    y=np.asarray([complex(*ni[k]['outgoing_amplitude_at_boundary']) for k in sorted(oi)])
    defect=relative(y-x,x)
    if defect>1e-10:raise ValueError('common532 physical projection consistency')
    added=[k for k in ni if k not in oi]
    extra=np.asarray([complex(*ni[k]['outgoing_amplitude_at_boundary']) for k in sorted(added)])
    # The fields and volume absorption remain the original immutable parent;
    # only the diagnostic boundary inventory and powers have been recomputed.
    projected=dict(parent);projected['output']=dict(parent['output'],port_metrics=pm)
    projected['mode_power_path']=str(sub/'port_power.json')
    projected['finite_mode_projection']=dict(parent_array_sha256=parent['arrays']['sha256'],arrays=receipt,
        original_published_532_unchanged=True,common532_operation_relative=defect,added296_actual_projection_norm=float(np.linalg.norm(extra)),
        original_count=old_count,added_count=new_count-old_count,common_operation_relative=defect,
        added_actual_projection_norm=float(np.linalg.norm(extra)),count=new_count,source=journal.source_state)
    return projected
