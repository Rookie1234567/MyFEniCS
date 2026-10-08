"""Saved complete-field recalculation; no FE, matrix, factor or solve."""
import json
from pathlib import Path
import numpy as np
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.phase_notch_hp_modes import compare_payloads

FIELDS=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')


def integral_metrics(values):
    if values.ndim!=3 or values.shape[1:]!=(6,3) or not len(values) or not np.isfinite(values).all() or np.any(values<0):
        raise ValueError('complete six-field physical integral inventory')
    sums=values.sum(axis=0)
    return sums, {name:float(np.sqrt(s[0])/max(np.sqrt(s[1]),1e-12)) for name,s in zip(FIELDS,sums,strict=True)}


def saved_pair(pair,first,second,*,expected_points):
    """Recompute the verdict using saved integrals, vectors and physical modes."""
    if pair['parent_array_sha256']!=[r['arrays']['sha256'] for r in (first,second)]:raise ValueError('frozen pair parent identity')
    a=checked_arrays(pair['arrays']);sums,fields=integral_metrics(a['per_cell_integrals'])
    if a['selected_points'].shape!=(240,3) or not np.array_equal(a['selected_points'],expected_points):raise ValueError('fixed physical selected inventory')
    selected={};components={}
    for j,name in enumerate(FIELDS):
        x,y=[a['selected_'+name+'_'+side] for side in ('first','second')]
        if x.shape!=(240,3) or y.shape!=x.shape or x.dtype!=np.complex128 or y.dtype!=np.complex128 or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError('full complex selected field inventory')
        selected[name]=float(np.linalg.norm(y-x)/max(np.linalg.norm(y),1e-30))
        e=np.sum(np.abs(y-x)**2,axis=0);components[name]=(e/max(e.sum(),1e-30)).tolist()
        if abs(fields[name]-pair['fields'][name]['relative'])>1e-12 or abs(selected[name]-pair['selected'][name])>1e-12:
            raise ValueError('declared field metric differs from actual saved vector/integral')
    rules=pair['quadrature_pair']
    if rules not in ([23,31],[23,31,39]):raise ValueError('fixed common quadrature inventory')
    if rules==[23,31]:previous=checked_arrays(pair['q23_arrays'])
    else:
        path=Path(pair['arrays']['path']).with_name('common_q31.json')
        previous=checked_arrays(json.loads(path.read_text())['arrays'])
    before,_=integral_metrics(previous['per_cell_integrals'])
    if previous['per_cell_integrals'].shape!=a['per_cell_integrals'].shape:raise ValueError('same common domain quadrature rows')
    qdef=float(np.max(np.abs(before[:,:2]-sums[:,:2])/np.maximum(sums[:,1,None],1e-24)))
    payloads=[json.loads(Path(r['mode_power_path'] if 'mode_power_path' in r else Path(r['output']['fields']['path']).with_name('port_power.json')).read_text()) for r in (first,second)]
    modes,vectors=compare_payloads(*payloads,828)
    stored_modes=checked_arrays(pair['modes']['arrays'])
    for name,value in vectors.items():
        if not np.array_equal(stored_modes[name],value):raise ValueError('complete saved physical mode vector pairing')
    powers={k:abs(first['output']['port_metrics'][k]-second['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
    powers['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
    energies=[abs(r['output']['volume_metrics'].get('energy_closure_error',r['output']['volume_metrics'].get('energy_closure_error_port_volume'))) for r in (first,second)]
    passed=max([*fields.values(),*selected.values()])<=1e-4 and qdef<=1e-10 and modes['outgoing_amplitude_at_boundary_relative']<=1e-4 and modes['mode_power_max_absolute']<=1e-6 and max(powers.values())<=1e-5 and max(energies)<=1e-5
    keys=json.loads(vectors['physical_keys_json_utf8'].tobytes().decode())
    worst={}
    for name in ('outgoing_amplitude_at_boundary','power'):
        delta=vectors[name+'_second']-vectors[name+'_first'];i=int(np.argmax(np.abs(delta)));d=delta[i]
        worst[name]=dict(physical_key=keys[i],absolute=float(abs(d)),difference=[float(np.real(d)),float(np.imag(d))])
    return dict(fields=fields,selected=selected,selected_component_error_fractions=components,quadrature_operation_scaled=qdef,
        mode_amplitude_relative=modes['outgoing_amplitude_at_boundary_relative'],mode_power_max_absolute=modes['mode_power_max_absolute'],
        power_differences=powers,energies=energies,worst_modes=worst,pass_gate=bool(passed),
        published_gate_matches_recalculation=bool(passed)==bool(pair['pass_gate']),
        classification='SPACE_INCREMENT_PASS' if passed else 'SPACE_INCREMENT_FAIL',
        full_integral_rows=len(a['per_cell_integrals']),parent_array_sha256=[first['arrays']['sha256'],second['arrays']['sha256']],
        new_FE_calls=0,new_factor=0,new_solve=0)


def material_regions(pair,second,notch,tag_names):
    """Frozen physical regions, with no error-dependent mask or new direction."""
    a=checked_arrays(pair['arrays']);v=checked_arrays(second['arrays']);values=a['per_cell_integrals']
    centers=v['cell_centers'];tags=v['cell_tags'];box=np.asarray(notch).reshape(3,2)
    if len(values)!=len(centers) or len(tags)!=len(centers):raise ValueError('new pair actual reference-cell region inventory')
    inside=np.all((centers>=box[:,0])&(centers<=box[:,1]),axis=1)
    masks={name:(tags==tag)&~inside for tag,name in tag_names.items()};masks['notch_air']=inside
    if not np.all(np.sum(list(masks.values()),axis=0)==1):raise ValueError('complete disjoint physical regions')
    whole=values.sum(axis=0);out={}
    for label,mask in masks.items():
        e=values[mask].sum(axis=0)
        out[label]=dict(cells=int(mask.sum()),error_squared={k:float(t[0]) for k,t in zip(FIELDS,e,strict=True)},
            fraction_of_global_error_squared={k:float(t[0]/max(s[0],1e-30)) for k,t,s in zip(FIELDS,e,whole,strict=True)})
    return dict(regions=out,physical_reference_cell_sha256=second['arrays']['sha256'],
        classification='post-frozen locality diagnosis, not an error bound or solver input')
