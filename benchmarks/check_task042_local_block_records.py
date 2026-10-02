"""Recompute V24 qualification from compact numerical fields, not status flags."""
import csv, hashlib, json, math, sys
from pathlib import Path
from src.solvers.local_block_readiness import local_readiness

def read(path): return json.loads(Path(path).read_text())
def bounded(values,tol):
    return all(math.isfinite(float(v)) and 0<=float(v)<=tol for v in values)
def equation(a):
    return bounded((a[k] for k in ('schur_relative','native_relative','augmented_relative',
        'original_total_augmented_relative','port_full_rhs_relative','port_operation_relative')),1e-6) and \
        bounded((a['recovery_relative'],a['schur_original_identity_operation_relative']),1e-10) and a['slave_storage_max']==0
def reference_equation(a):
    return equation(a) and bounded((a['independent_DOLFINx_total_native_relative'],),1e-6)
def complete(row,reference):
    c=row['comparison']
    return equation(row['audit']) and reference and \
        bounded((row['audit']['independent_DOLFINx_total_native_relative'],),1e-6) and \
        bounded(row['fields'].values(),1e-4) and bounded((c['ordered_complex_ports_relative'],),1e-4) and \
        bounded(c['power_absolute_differences'].values(),1e-5) and \
        bounded((c['max_channel_power_difference'],),1e-6) and bounded((c['energy_closure_absolute'],),1e-5)

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
        assert len(ports)==len(power)==40 and len({int(v['index']) for v in ports})==40
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
