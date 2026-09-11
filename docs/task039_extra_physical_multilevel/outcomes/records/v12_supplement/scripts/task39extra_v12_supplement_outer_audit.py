"""Read-only audit of bounded V12 outer records and saved solution shards."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('runs', nargs='+', type=Path)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--engineering-run', type=Path)
args = parser.parse_args()
errors = []
checks = 0
hashes = {}
audits = []
prefix = {}


def check(ok, message):
    global checks
    checks += 1
    if not ok:
        errors.append(message)


def read(path):
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


def close(actual, expected):
    return bool(np.isclose(actual, expected, rtol=1e-11, atol=1e-14))


for run in args.runs:
    records = run / 'records'
    summary = read(records / 'outer_summary.json')
    terminal = read(run / 'terminal.json')
    rhs_packet = read(records / 'physical_rhs.json')
    rhs_path = Path(rhs_packet['arrays']['path'])
    hashes[str(rhs_path)] = hashlib.sha256(rhs_path.read_bytes()).hexdigest()
    check(hashes[str(rhs_path)] == rhs_packet['arrays']['sha256'], f'{run}: physical rhs packet hash')
    with np.load(rhs_path, allow_pickle=False) as archive:
        rhs = archive[rhs_packet['rhs']['array_key']]
        rhs_array_hash = hashlib.sha256(rhs.tobytes()).hexdigest()
    candidate = summary['candidates'][0]
    restart = candidate['restart']
    tag = f'R{restart}'
    calls = candidate['outer_pc_calls']
    delta = candidate['cost_delta']
    i4 = candidate['outer_i4_call_records']
    check(candidate['framework'] == 'BAL_H', f'{tag}: framework')
    check(restart in (32, 64), f'{tag}: restart')
    check(candidate['iterations'] <= 64, f'{tag}: outer bound')
    check(len(i4) == 2 * calls == delta['I4_calls'], f'{tag}: I4 count')
    check(sum(x['B4_calls'] for x in i4) == delta['B4_calls'], f'{tag}: B4 count')
    check(delta['MD_local_solves'] == 42 * delta['B4_calls'], f'{tag}: MD solve count')
    check(delta['MD_calls'] == delta['B4_calls'], f'{tag}: MD call count')
    check(delta['B4_C'] == 2 * delta['B4_calls'], f'{tag}: C_U count')
    check(delta['H6_apply_count'] == calls, f'{tag}: H6 count')
    balance = candidate['outer_balance_ledger']
    last = balance['last_summary']
    audit = last['audit']
    scale = sum(call['rhs_norm'] + call['applied_norm'] for call in last['calls'])
    check(last['identity'] == 'eps1-eps2' and last['iteration'] == calls, f'{tag}: balance identity')
    check(close(scale, audit['operation_scale']), f'{tag}: closure operation scale')
    check(close(audit['closure_norm'] / scale, audit['closure_relative']), f'{tag}: closure ratio')
    check(close(audit['actual_defect_norm'] / scale, audit['defect_scaled']), f'{tag}: scaled defect')
    check(audit['closure_relative'] <= 1e-8, f'{tag}: closure bound')
    check(balance['audit_count'] == balance['A_count'] == balance['PH_count'] == 1 + calls // 32,
          f'{tag}: sampled balance audit counts')
    for key, before in candidate['cost_start'].items():
        check(close(candidate['cost_end'][key] - before, delta[key]), f'{tag}: cost delta {key}')
    for j, facts in enumerate(i4):
        label = f'{tag}/I4/{j + 1}'
        check(facts['B4_calls'] <= 4 and facts['iterations'] <= 4, f'{label}: 4-step cap')
        check(facts['max_it'] == 4 and facts['restart'] == 4, f'{label}: settings')
        check(facts['zero_start'], f'{label}: zero start')
        check(all(facts[k] == 1 for k in ('ksp_create_count', 'ksp_solve_count', 'ksp_destroy_count')),
              f'{label}: single KSP')
        check(facts['explicit_uses_separate_action'], f'{label}: native A4 explicit')
        check(close(facts['eps_norm'] / facts['rhs_norm'], facts['final_true_residual']),
              f'{label}: epsilon norm quotient')
        check(facts['seconds'] < 30 and not facts['timeout_exceeded'], f'{label}: hard time')
        check((facts['final_true_residual'] <= 1e-4) == (facts['status'] == 'INNER_TARGET_REACHED'),
              f'{label}: quality label')
    nodes = []
    unique = {}
    for row in candidate['node_records']:
        iteration = row['iteration']
        check(row['outer_pc_calls'] == iteration, f'{tag}/{iteration}: outer calls')
        check(row['elapsed_seconds_conservative'] >= row['elapsed_seconds_monotonic'] - 1e-8,
              f'{tag}/{iteration}: timebase ordering')
        if iteration in unique:
            check(row['solution_sha256'] == unique[iteration]['solution_sha256'] and
                  close(row['true_residual'], unique[iteration]['true_residual']),
                  f'{tag}/{iteration}: duplicate agrees')
            continue
        unique[iteration] = row
        if iteration not in range(8, 65, 8):
            continue
        directory = records / 'checkpoints' / f'restart_{restart}_periodic_nodes' / f'iteration_{iteration:08d}'
        manifest = read(directory / 'manifest.json')
        check(manifest['source_sha'] == summary['source_sha'], f'{tag}/{iteration}: source binding')
        for key in ('input_identity_sha256', 'operator_identity_sha256', 'physical_model_sha256'):
            check(manifest[key] == row[key], f'{tag}/{iteration}: {key}')
        shard = manifest['ranks'][0]['solution']
        shard_path = directory / shard['relative_path']
        hashes[str(shard_path)] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        check(hashes[str(shard_path)] == shard['sha256'], f'{tag}/{iteration}: shard hash')
        solution = np.load(shard_path, allow_pickle=False)
        check(solution.dtype == np.complex128 and solution.shape == (173802,), f'{tag}/{iteration}: shape/dtype')
        check(hashlib.sha256(solution.tobytes()).hexdigest() == row['solution_sha256'], f'{tag}/{iteration}: solution hash')
        check(close(np.linalg.norm(solution), row['solution_norm']), f'{tag}/{iteration}: solution norm')
        check(close(manifest['explicit_true_residual'], row['true_residual']), f'{tag}/{iteration}: residual binding')
        if iteration <= 32:
            prefix[(restart, iteration)] = (solution.copy(), row['true_residual'])
        field = row.get('reference_field')
        if iteration >= 32:
            check(field['status'] == 'REFERENCE_FIELD_AVAILABLE', f'{tag}/{iteration}: field available')
            for key in ('L2', 'scaled_curl'):
                check(close(field[key]['absolute_error_norm'] / field[key]['reference_norm'], field[key]['relative']),
                      f'{tag}/{iteration}: {key} norm quotient')
            check(close(max(field[key]['relative'] for key in ('L2', 'scaled_curl')), field['max_relative']),
                  f'{tag}/{iteration}: max field')
        nodes.append({key: row[key] for key in ('iteration', 'true_residual', 'solution_sha256',
                     'elapsed_seconds_monotonic', 'elapsed_seconds_conservative', 'cost', 'outer_pc_calls')}
                     | {'reference_field': field,
                        'reference_field_elapsed_seconds_monotonic': row.get('reference_field_elapsed_seconds')})
    check(close(candidate['final_true_residual'], unique[candidate['iterations']]['true_residual']),
          f'{tag}: final residual binding')
    if candidate['final_true_residual'] > 1e-6:
        check(not summary.get('official_result'), f'{tag}: no official output without original A6 gate')
    audits.append({
        'run': str(run), 'source_sha': summary['source_sha'], 'restart': restart,
        'physical_model_sha256': summary['physical_model_sha256'],
        'operator_identity_sha256': summary['operator_identity']['sha256'],
        'mode_sha256': rhs_packet['facts']['mode_manifest_sha256'],
        'physical_rhs_array_sha256': rhs_array_hash,
        'workflow_status': terminal['classification'], 'candidate_status': candidate['status'],
        'iterations': candidate['iterations'], 'final_true_residual': candidate['final_true_residual'],
        'nodes': nodes, 'outer_pc_calls': calls, 'cost_delta': delta,
        'outer_pc_total_counts': candidate['outer_pc_total_counts'],
        'outer_pc_total_operation_seconds': candidate['outer_pc_total_operation_seconds'],
        'operation_seconds_clock': 'perf_counter monotonic for outer PC and stack operation times; nested costs must not be added to parents',
        'outer_balance_ledger': candidate['outer_balance_ledger'],
        'outer_balance_scope': 'recomputed final saved scalar closure and counted audits; prior sampled closure scalars and success vectors are not persisted',
        'I4': {'calls': len(i4), 'target_reached': sum(x['final_true_residual'] <= 1e-4 for x in i4),
               'residual_min': min(x['final_true_residual'] for x in i4),
               'residual_max': max(x['final_true_residual'] for x in i4),
               'seconds_total': sum(x['seconds'] for x in i4),
               'seconds_max': max(x['seconds'] for x in i4),
               'seconds_clock': 'ClockBudget conservative_realtime; not interchangeable with parent operation perf_counter intervals',
               'B4_calls_total': sum(x['B4_calls'] for x in i4)},
        'outer_monotonic_seconds': candidate['elapsed_seconds_monotonic'],
        'outer_conservative_seconds': candidate['elapsed_seconds_conservative'],
        'workflow_conservative_seconds': terminal['workflow_clock_interval']['budget_seconds'],
        'stage_times': summary['stage_times'],
        'field_scope': 'norm arithmetic checked from recorded FE metrics; no new FE assembly or operator application',
        'residual_scope': 'native explicit residual provenance and checkpoint agreement; no replay A6 application',
    })

prefix_comparison = []
if len(audits) == 2:
    for key in ('source_sha', 'physical_model_sha256', 'operator_identity_sha256', 'mode_sha256', 'physical_rhs_array_sha256'):
        check(audits[0][key] == audits[1][key], f'paired identity: {key}')
for iteration in (8, 16, 24, 32):
    if (32, iteration) not in prefix or (64, iteration) not in prefix:
        continue
    x32, rho32 = prefix[(32, iteration)]
    x64, rho64 = prefix[(64, iteration)]
    difference = float(np.linalg.norm(x64 - x32) / max(np.linalg.norm(x32), 1e-300))
    check(difference <= 1e-11 and close(rho32, rho64), f'paired/{iteration}: common prefix')
    prefix_comparison.append({'iteration': iteration, 'relative_solution_difference': difference,
                              'residual_R32': rho32, 'residual_R64': rho64,
                              'bitwise_equal': bool(np.array_equal(x32, x64))})

result = {'scope': 'read-only raw records, counts, hashes and saved solution audit',
          'new_PDE_runs': 0, 'checks': checks, 'errors': errors,
          'runs': audits, 'prefix_comparison': prefix_comparison, 'hashes': hashes}
if args.engineering_run:
    earlier = []
    for iteration in (8, 16, 24):
        directory = args.engineering_run / 'records/checkpoints/restart_32_periodic_nodes' / f'iteration_{iteration:08d}'
        manifest = read(directory / 'manifest.json')
        shard = manifest['ranks'][0]['solution']
        shard_path = directory / shard['relative_path']
        hashes[str(shard_path)] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        check(hashes[str(shard_path)] == shard['sha256'], f'engineering/{iteration}: shard hash')
        solution = np.load(shard_path, allow_pickle=False)
        current, rho = prefix[(32, iteration)]
        exact = bool(np.array_equal(solution, current))
        check(exact and close(manifest['explicit_true_residual'], rho), f'engineering/{iteration}: repaired prefix')
        earlier.append({'iteration': iteration, 'bitwise_equal': exact,
                        'residual_before': manifest['explicit_true_residual'], 'residual_after': rho})
    result['engineering_failure_prefix_comparison'] = earlier
    result['checks'] = checks
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'checks': checks, 'errors': errors, 'runs': len(audits), 'prefix_comparison': prefix_comparison}))
raise SystemExit(bool(errors))
