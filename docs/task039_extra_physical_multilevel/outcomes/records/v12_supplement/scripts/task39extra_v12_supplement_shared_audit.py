"""Independently recount stored shared-input vectors and framework selection."""
import hashlib
import json
from pathlib import Path

import numpy as np

RECORDS = Path('/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task39extra/v12_supplement/7d9df5e19d324776588aaa9efc4996cc3fe36d8e/o1_full_physical_controls/records')
errors, rows = [], []
checks = 0


def check(name, value):
    global checks
    checks += 1
    if not value:
        errors.append(name)


def close(name, actual, expected):
    check(name, bool(np.isclose(actual, expected, rtol=1e-10, atol=1e-13)))


for path in sorted(RECORDS.glob('*_shared_zc_s_t.json')):
    d = json.loads(path.read_text())
    label = d['name']
    packet = Path(d['arrays']['path'])
    check(label + ':hash', hashlib.sha256(packet.read_bytes()).hexdigest() == d['arrays']['sha256'])
    with np.load(packet) as arrays:
        def a(item):
            return arrays[item['array_key']]
        q, zc, smooth, feedback = [a(d[key]) for key in ('q_values', 'zc_values', 's_values', 't_values')]
        check(label + ':finite', all(np.isfinite(arrays[key]).all() for key in arrays))
        check(label + ':ONE_formula', np.array_equal(zc + smooth, a(d['ONE_C']['z_values'])))
        check(label + ':BAL_formula', np.array_equal(zc + smooth - feedback, a(d['BAL_H']['z_values'])))
        check(label + ':unchanged_q', d['input_unchanged'])
        check(label + ':q_e_native_bridge', d['q_bridge_relative'] <= d['q_bridge_limit'] == 1e-10)
        check(label + ':two_I4', d['shared_I4_calls'] == d['cost']['delta']['I4_calls'] == 2)
        check(label + ':new_B4_count', d['cost']['delta']['B4_calls'] == 8)
        check(label + ':MD_local_count', d['cost']['delta']['MD_local_solves'] == 336)
        result = {'name': label, 'record_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'packet_sha256': d['arrays']['sha256'], 'cost': d['cost']['delta']}
        for framework, second in [('BAL_H', 'eps2_values'), ('ONE_C', 'g2_values')]:
            f = d[framework]
            rho = float(np.linalg.norm(q - a(f['Az_values'])) / np.linalg.norm(q))
            close(label + ':' + framework + ':rho', rho, f['true_residual_ratio'])
            difference = a(d['eps1_values']) - a(d[second])
            close(label + ':' + framework + ':eps_difference_norm', np.linalg.norm(difference), f['inexact_balance']['difference_norm'])
            audit = f['audit']
            close(label + ':' + framework + ':closure_recount', audit['closure_norm'] / audit['operation_scale'], audit['closure_relative'])
            check(label + ':' + framework + ':closure_limit', audit['closure_relative'] <= 1e-8)
            close(label + ':' + framework + ':actual_defect_norm', audit['actual_defect_norm'], np.linalg.norm(difference))
            for metric, energy in [('L2', 'mass'), ('scaled_curl', 'curl')]:
                energy_sum = np.sum(a(d['cell_energies'][framework][energy]))
                close(label + ':' + framework + ':' + metric + ':energy', energy_sum, f['field'][metric]['error_squared'])
                close(label + ':' + framework + ':' + metric + ':relative', np.sqrt(energy_sum / f['field'][metric]['reference_squared']), f['field'][metric]['relative'])
            for call in f['inexact_balance']['calls']:
                inner = call['inner']
                check(label + ':' + framework + ':I4_policy', inner['B4_calls'] == inner['iterations'] == inner['max_it'] == inner['restart'] == 4 and inner['zero_start'])
            result[framework] = {'rho': rho, 'L2': f['field']['L2']['relative'],
                                 'scaled_curl': f['field']['scaled_curl']['relative'],
                                 'seconds': f['total_seconds'], 'closure': audit['closure_relative']}
        rows.append(result)

decision = json.loads((RECORDS / 'framework_decision.json').read_text())
check('three_nonzero_shared_samples', len(rows) == decision['valid_matched_samples'] == 3)
ratios = {key: [r['ONE_C'][key] / r['BAL_H'][key] for r in rows] for key in ('rho', 'L2', 'scaled_curl')}
geometric = {key: float(np.exp(np.mean(np.log(values)))) for key, values in ratios.items()}
time_ratio = sum(r['ONE_C']['seconds'] for r in rows) / sum(r['BAL_H']['seconds'] for r in rows)
choose_one = geometric['L2'] <= .8 and max(ratios['L2']) <= 1.1 and geometric['scaled_curl'] <= 1.1 and geometric['rho'] <= 1 and time_ratio <= .8
check('selection_recount', decision['selected_framework'] == ('ONE_C' if choose_one else 'BAL_H'))
for key, reported in [('L2', 'field'), ('rho', 'residual'), ('scaled_curl', 'scaled_curl')]:
    close('geomean:' + key, geometric[key], decision['geometric_means'][reported])
close('time_ratio', time_ratio, decision['time_totals']['ONE_over_BAL'])
result = {'scope': 'saved vector arithmetic, cell-energy sums, scalar closure and selection recount; no new PDE or independent FE quadrature',
          'source_sha': '7d9df5e19d324776588aaa9efc4996cc3fe36d8e', 'checks': checks, 'errors': errors,
          'rows': rows, 'geometric_ONE_over_BAL': geometric, 'time_ONE_over_BAL': time_ratio,
          'recomputed_selection': 'ONE_C' if choose_one else 'BAL_H'}
Path('/tmp/task39extra-v12-supplement-shared-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'checks': checks, 'errors': errors, 'geometric': geometric, 'time_ratio': time_ratio, 'selection': result['recomputed_selection']}))
raise SystemExit(bool(errors))
