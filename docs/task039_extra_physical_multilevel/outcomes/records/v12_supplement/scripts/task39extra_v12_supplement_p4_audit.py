"""Recount saved V12 p4 evidence without invoking any PDE operator."""
import hashlib
import json
from pathlib import Path
import numpy as np

root = Path('/home/shenjh/Projects/MyFEniCSx_task37_extra')
records = root / 'benchmarks/artifacts/task39extra/v12_supplement/7d9df5e19d324776588aaa9efc4996cc3fe36d8e/o1_full_physical_controls/records'
errors, rows = [], []
checks = 0

def check(name, value):
    global checks
    checks += 1
    if not value:
        errors.append(name)

def close(name, actual, expected):
    check(name, bool(np.isclose(actual, expected, rtol=1e-11, atol=1e-14)))

for path in sorted(records.glob('*_bare_B4_I4.json')):
    d = json.loads(path.read_text())
    stem = d['stem']
    packet = Path(d['arrays']['path'])
    check(stem + ':packet_hash', hashlib.sha256(packet.read_bytes()).hexdigest() == d['arrays']['sha256'])
    with np.load(packet) as arrays:
        def arr(key):
            return arrays[d[key]['array_key']]
        rhs, ref = arr('rhs_values'), arr('reference_values')
        rhsnorm = np.linalg.norm(rhs)
        check(stem + ':finite', all(np.isfinite(arrays[k]).all() for k in arrays))
        close(stem + ':rhs_norm', rhsnorm, d['rhs']['norm'])
        for prefix, applied, residual, reported in (
            ('bare', 'bare_applied_values', 'bare_residual_values', d['bare_B4']['true_residual_ratio']),
            ('I4', 'I4_applied_values', 'I4_residual_values', d['I4_true_residual_ratio']),
            ('reference', 'reference_A4y_values', 'reference_residual_values', d['reference_residual_ratio']),
        ):
            check(stem + ':' + prefix + '_explicit_difference', np.array_equal(rhs - arr(applied), arr(residual)))
            close(stem + ':' + prefix + '_rho', np.linalg.norm(arr(residual))/rhsnorm, reported)
        check(stem + ':field_error', np.array_equal(ref - arr('I4_solution_values'), arr('error_values')))
        identity = arr('A4_error_values') - (arr('I4_residual_values') - arr('reference_residual_values'))
        scale = np.linalg.norm(arr('reference_A4y_values')) + np.linalg.norm(arr('I4_applied_values')) + rhsnorm
        close(stem + ':identity_raw', np.linalg.norm(identity), d['A4_error_identity_raw_norm'])
        close(stem + ':identity_scale', scale, d['A4_error_identity_scale'])
        close(stem + ':identity', np.linalg.norm(identity)/scale, d['A4_error_identity_relative'])
        check(stem + ':identity_limit', np.linalg.norm(identity)/scale <= 1e-10)
        energy = d['cell_energies']['I4_error']
        for metric, key in [('L2', 'mass'), ('scaled_curl', 'curl')]:
            sq = float(np.sum(arrays[energy[key]['array_key']]))
            close(stem + ':' + metric + '_cell_sum', sq, d['field'][metric]['error_squared'])
            close(stem + ':' + metric + '_ratio', np.sqrt(sq/d['field'][metric]['reference_squared']), d['field'][metric]['relative'])
        f = d['I4']
        check(stem + ':four_steps', f['B4_calls'] == f['iterations'] == f['max_it'] == f['restart'] == 4)
        check(stem + ':zero_and_legal', f['zero_start'] and f['legal_direction_count'] == 4)
        check(stem + ':single_ksp_lifetime', f['ksp_create_count'] == f['ksp_destroy_count'] == f['ksp_solve_count'] == 1)
        check(stem + ':call_count', d['cost']['delta']['I4_calls'] == 1 and d['cost']['delta']['B4_calls'] == 5 and d['cost']['delta']['MD_local_solves'] == 210)
        rows.append({'stem': stem, 'json_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'npz_sha256': d['arrays']['sha256'], 'I4_rho': d['I4_true_residual_ratio'], 'I4_L2': d['field']['L2']['relative'], 'I4_scaled_curl': d['field']['scaled_curl']['relative'], 'bare_rho': d['bare_B4']['true_residual_ratio'], 'bare_L2': d['bare_B4']['field']['L2']['relative'], 'bare_scaled_curl': d['bare_B4']['field']['scaled_curl']['relative'], 'I4_seconds': f['seconds'], 'bare_seconds': d['bare_B4']['seconds'], 'evaluation_seconds': d['evaluation_seconds'], 'A4_error_identity_relative': d['A4_error_identity_relative']})
result = {'scope': 'Saved vector arithmetic and cell-energy recount only; no new operator application, no independent FE quadrature, no outer-PC PASS', 'source': '7d9df5e19d324776588aaa9efc4996cc3fe36d8e', 'records': str(records), 'completed_p4_records': len(rows), 'completed_I4_calls_lower_bound': len(rows), 'completed_B4_calls_lower_bound': 5*len(rows), 'completed_MD_local_solves_lower_bound': 210*len(rows), 'checks': checks, 'errors': errors, 'status': 'SAVED_RECORDS_CONSISTENT' if not errors else 'INCONSISTENT', 'rows': rows}
Path('/tmp/task39extra-v12-supplement-p4-supervisor-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(bool(errors))
