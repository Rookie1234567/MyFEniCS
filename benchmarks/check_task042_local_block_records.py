"""Recompute V24 qualification from compact numerical fields, not status flags."""
import csv, hashlib, json, math, sys
from pathlib import Path
from src.solvers.local_block_readiness import local_readiness

FIELD_METRICS = ('full_FE_L2_relative', 'full_FE_scaled_curl_relative',
    'scattered_FE_L2_relative', 'scattered_scaled_curl_relative',
    'selected_E_relative', 'selected_H_relative')
POWER_METRICS = ('R_total', 'T_total', 'A_balance', 'A_volume')

def read(path): return json.loads(Path(path).read_text())
def bounded(values,tol):
    try:
        return all(math.isfinite(float(v)) and 0<=float(v)<=tol for v in values)
    except (TypeError, ValueError, KeyError):
        return False
def required(values,keys,tol):
    return isinstance(values,dict) and all(k in values for k in keys) and bounded((values[k] for k in keys),tol)
def equation(a):
    return bounded((a[k] for k in ('schur_relative','native_relative','augmented_relative',
        'original_total_augmented_relative','port_full_rhs_relative','port_operation_relative')),1e-6) and \
        bounded((a['recovery_relative'],a['schur_original_identity_operation_relative']),1e-10) and a['slave_storage_max']==0
def reference_equation(a):
    return equation(a) and bounded((a['independent_DOLFINx_total_native_relative'],),1e-6)
def complete(row,reference):
    try:
        c=row['comparison']
        return equation(row['audit']) and bool(reference) and \
            bounded((row['audit']['independent_DOLFINx_total_native_relative'],),1e-6) and \
            required(row['fields'],FIELD_METRICS,1e-4) and bounded((c['ordered_complex_ports_relative'],),1e-4) and \
            required(c['power_absolute_differences'],POWER_METRICS,1e-5) and \
            bounded((c['max_channel_power_difference'],),1e-6) and bounded((c['energy_closure_absolute'],),1e-5)
    except (KeyError,TypeError,ValueError):
        return False

def channels_valid(ports,powers,expected,planes):
    """Require every original mode, polarization and reference plane, separately."""
    try:
        if len(expected)!=40 or len(ports)!=40 or len(powers)!=40:return False
        for rows in (ports,powers):
            if {int(v['index']) for v in rows}!=set(range(40)):return False
            for v in rows:
                mode=expected[int(v['index'])]
                if rows is ports and json.loads(v['original_key'])!=mode:return False
                if (v['side'],int(v['m']),int(v['n']),v['polarization'])!=(mode['side'],mode['m'],mode['n'],mode['polarization']):return False
                if float(v['reference_plane_z'])!=planes[mode['side']]:return False
        return True
    except (KeyError,TypeError,ValueError):return False

def check(root):
    root=Path(root);part=read(root/'partition_v24.json');block=read(root/'block_action_v24.json');factors=read(root/'local_factor_safety_v24.json')
    # The complete canonical map remains in an ignored, hash-bound artifact.
    # Missing raw evidence is an explicit failure, never invented row data.
    pointer=factors['raw_SETUP'];path=Path(pointer['path'])
    data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==pointer['sha256'], 'raw SETUP hash differs'
    raw=json.loads(data)
    assert raw['partition']==part and raw['factor_safety']==factors['factors']
    assert raw['local_ready_evidence']==block['local_ready_evidence']
    ready=local_readiness(raw)
    assert ready['qualified'],ready
    comp=read(root/'composite_overlap_v24.json');over=comp['overlap'];checks=comp['checks'];safety=over['safety']
    composite=bool(math.isfinite(safety['ratio']) and safety['ratio']>=1e-12 and over['whole_overlap_resolved'] and
        safety['sigma_max']>over['whole_overlap_roundoff_floor'] and
        bounded((x['operation_relative'] for x in comp['reused_image_pairs']),1e-10) and
        bounded((x[k]['operation_relative'] for x in checks['witnesses'] for k in ('coarse_balance','LC_Dop_T')),1e-8) and
        bounded((checks['repeat']['operation_relative'],checks['complex_linearity']['operation_relative']),1e-10))
    assert composite==comp['qualified']
    gate=read(root/'qualification_and_dispatch_v24.json');fields=read(root/'field_checks_v24.json')
    reference_pass=reference_equation(fields['reference_audit'])
    assert bounded((fields['reference_audit']['independent_DOLFINx_total_native_relative'],),1e-6)==fields['reference_native_pass']
    candidates=list(csv.DictReader((root/'candidate_comparison_v24.csv').open()));passed=0
    for row in candidates:
        r=fields['rows'][row['state']];actual=complete(r,reference_pass)
        assert actual==(row['strict_qualified']=='True')
        assert equation(r['audit'])==(row['equation_qualified']=='True')
        assert actual==gate['gates'][row['state']]['complete_same_discrete']
        for col,key in [('Schur','schur_relative'),('native','native_relative'),('augmented','augmented_relative'),('port_full','port_full_rhs_relative')]:
            assert float(row[col])==r['audit'][key]
        passed+=actual
    assert passed==gate['passed'] and len(candidates)==gate['states']
    channels=list(csv.DictReader((root/'field_channels_v24.csv').open()));powers=list(csv.DictReader((root/'per_channel_power_v24.csv').open()))
    for row in candidates:
        name=row['state'];ports=[v for v in channels if v['state']==name];power=[v for v in powers if v['state']==name]
        assert channels_valid(ports,power,raw['physical_identity']['full_channel_inventory'],dict(top=1.225,bottom=-0.175)), 'mode/polarization/reference-plane inventory differs'
        for v in ports:
            assert abs((float(v['total_real'])-float(v['reference_total_real']))-float(v['error_real']))<=1e-14
            assert abs((float(v['total_imag'])-float(v['reference_total_imag']))-float(v['error_imag']))<=1e-14
        for v in power: assert abs(abs(float(v['power'])-float(v['reference_power']))-float(v['power_absolute_difference']))<=1e-14
        maximum=max(abs(float(v['power'])-float(v['reference_power'])) for v in power)
        assert abs(maximum-float(row['max_channel_power_difference']))<=1e-12
    costs=read(root/'resource_costs_v24.json')
    assert costs['own_swap_peak_bytes']==0 and costs['simultaneous_sampled_tree_peak_bytes']<16*2**30
    assert costs['storage']['artifacts']['logical_bytes']<=2*2**30
    assert all(costs['charged'][k]<=v for k,v in costs['limits'].items())
    assert costs['total_triangular_conservative_upper']<=costs['limits']['local_triangular_pass']
    assert costs['total_R_triangular_including_fixed_identity_witnesses']<=costs['limits']['R_triangular']
    assert costs['charged']['factor_readers']<=5 and costs['charged']['local_factors']==8
    cycles=list(csv.DictReader((root/'cycle_history_v24.csv').open()))
    for route in ('LW','LCW','LZ','LCZ'):
        rows=[r for r in cycles if r['route']==route]
        assert len(rows)<=4 and [int(r['cycle']) for r in rows]==list(range(1,len(rows)+1))
    assert gate['neural_20percent_increment']=='NOT_DEMONSTRATED'
    return dict(local_qualified=ready['qualified'],composite_qualified=composite,states=len(candidates),passed=passed,
        first_four_only=True,raw_fields_recomputed=True,neural_20percent_increment='NOT_DEMONSTRATED',all_limits_pass=True)

if __name__=='__main__': print(json.dumps(check(Path(sys.argv[1]))))
