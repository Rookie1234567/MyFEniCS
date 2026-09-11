"""Verify durable R64 prefix against the completed R32 experiment."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('r32', type=Path)
parser.add_argument('r64', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
errors, rows, hashes = [], [], {}


def read(path):
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


def shard(directory):
    manifest = read(directory / 'manifest.json')
    binding = manifest['ranks'][0]['solution']
    path = directory / binding['relative_path']
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    if hashes[str(path)] != binding['sha256']:
        errors.append(f'solution shard hash: {directory}')
    return manifest, np.load(path, allow_pickle=False)


terminal = read(args.r64 / 'terminal.json')
if terminal['classification'] != 'USER_CONTROLLED_STOP' or not terminal['descendants_cleared']:
    errors.append('controlled stop or descendant cleanup not confirmed')
for path in sorted((args.r64 / 'records/checkpoints/restart_64_periodic_nodes').glob('*/manifest.json')):
    m64, x64 = shard(path.parent)
    iteration = m64['iteration']
    m32, x32 = shard(args.r32 / 'records/checkpoints/restart_32_periodic_nodes' / path.parent.name)
    for key in ('source_sha', 'operator_identity_sha256', 'physical_model_sha256'):
        if m32[key] != m64[key]:
            errors.append(f'{iteration}: {key} mismatch')
    difference = float(np.linalg.norm(x64 - x32) / np.linalg.norm(x32))
    if difference > 1e-11 or m32['explicit_true_residual'] != m64['explicit_true_residual']:
        errors.append(f'{iteration}: prefix differs')
    rows.append({'iteration': iteration, 'R32_true_residual': m32['explicit_true_residual'],
                 'R64_true_residual': m64['explicit_true_residual'],
                 'relative_solution_difference': difference,
                 'bitwise_equal': bool(np.array_equal(x32, x64))})
rhs_hashes = []
for run in (args.r32, args.r64):
    packet = read(run / 'records/physical_rhs.json')
    path = Path(packet['arrays']['path'])
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    if hashes[str(path)] != packet['arrays']['sha256']:
        errors.append(f'{run}: physical rhs archive hash')
    with np.load(path, allow_pickle=False) as data:
        rhs_hashes.append(hashlib.sha256(data[packet['rhs']['array_key']].tobytes()).hexdigest())
if rhs_hashes[0] != rhs_hashes[1]:
    errors.append('physical rhs arrays differ')
result = {'classification': 'USER_CONTROLLED_STOP', 'errors': errors, 'new_PDE_runs': 0,
          'last_saved_iteration': max(row['iteration'] for row in rows), 'prefix': rows,
          'physical_rhs_array_sha256': rhs_hashes[0],
          'workflow_conservative_seconds': terminal['workflow_clock_interval']['budget_seconds'],
          'candidate_summary_available': (args.r64 / 'records/outer_summary.json').exists(),
          'candidate_cost_and_I4_totals': 'not_available; termination occurred before final candidate serialization',
          'node_time': 'not_available in durable solution-only checkpoint manifests',
          'restart_selection': 'not_completed; prefix through 24 does not establish the required through-32 equality or a finite R64 outcome',
          'exclusion_basis': 'completed R32 64-step result and historical comparisons; stopping R64 is a user scope decision',
          'hashes': hashes}
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: result[key] for key in ('classification', 'errors', 'last_saved_iteration', 'prefix', 'workflow_conservative_seconds')}))
raise SystemExit(bool(errors))
