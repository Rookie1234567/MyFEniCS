"""Read existing raw results for a bounded DD4 comparison; perform no PDE."""
import hashlib
import json
from pathlib import Path

REPO = Path('/home/shenjh/Projects/MyFEniCSx_task37_extra')
RECORDS = REPO / 'docs/task039_extra_physical_multilevel/outcomes/records'
OUT = Path('/tmp/task39extra-v12-supplement-history.json')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


v5 = read(RECORDS / 'balanced_coupling_v5.json')
v7a = read(RECORDS / 'bounded_inexact_outer_a_original_v7.json')
v7b = read(RECORDS / 'bounded_inexact_outer_b_original_v7.json')
v8 = read(RECORDS / 'recycled_p4_outer_v8.json')
v9 = read(RECORDS / 'equal_work_recycled_p4_v9.json')
specs = [
    ('V5_exact_p4_BAL_H', v5['models'][0]['solve_root'],
     v8['evidence']['v5_exact_p4_raw_hashes']),
    ('V7_entity16_BAL_H', v7a['run_directory'],
     v8['evidence']['v7_a_raw_hashes']),
    ('V7_projected_seq2_16', v7b['run']['run_directory'], v7b['raw_evidence']),
    ('V8_entity_GCROT8', v8['k2_original']['run_root'],
     v8['evidence']['k2_artifact_hashes']),
    ('V9_entity_GCROT8_new16', v9['l2_original']['artifact_root'],
     v9['l2_original']['raw_file_sha256']),
]
rows = []
errors = []
for label, dirname, expected in specs:
    root = REPO / dirname
    summary = read(root / 'physical_intermediate_summary.json')
    run = read(root / 'run_summary.json')
    authority = run['resource_authority']
    physical = (root / 'physical_model_sha256.txt').read_text().strip()
    mode = summary['mode_sha256']
    if physical != '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f':
        errors.append(f'{label}: physical identity mismatch')
    if mode != 'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2':
        errors.append(f'{label}: mode identity mismatch')
    bindings = {}
    for name in ('monitor_residuals.jsonl', 'iterations.jsonl', 'pc_applies.jsonl',
                 'physical_intermediate_summary.json', 'run_summary.json',
                 'stages.jsonl', 'physical_model_sha256.txt', 'source_sha.txt'):
        path = root / name
        digest = sha(path)
        binding = {'path': str(path.relative_to(REPO)), 'sha256': digest,
                   'prior_expected_sha256': expected.get(name)}
        if expected.get(name) is not None:
            binding['matches_previous_evidence'] = expected[name] == digest
            if not binding['matches_previous_evidence']:
                errors.append(f'{label}: changed raw {name}')
        bindings[name] = binding
    raw_nodes = [json.loads(line) for line in (root / 'monitor_residuals.jsonl').read_text().splitlines()]
    # Keep the earliest saved live solution for duplicate restart-boundary nodes.
    unique = {}
    for node in raw_nodes:
        unique.setdefault(int(node['iteration']), node)
    nodes = [unique[n] for n in sorted(unique)]
    starts = []
    for line in (root / 'stages.jsonl').read_text().splitlines():
        stage = json.loads(line)
        if stage.get('stage') == 'solve_started':
            starts.append({key: stage.get(key) for key in
                           ('stage', 'workflow_clock_interval', 'phase_clock_interval')})
    if len(starts) != 1:
        errors.append(f'{label}: expected exactly one solve start, found {len(starts)}')
    setup = starts[0]['workflow_clock_interval'] if len(starts) == 1 else None
    pc_rows = [json.loads(line) for line in (root / 'pc_applies.jsonl').read_text().splitlines()]
    prefixes = {}
    for count in (24, 32, 40, 48, 56, 64):
        selected = [item for item in pc_rows if int(item['apply_count']) <= count]
        if len(selected) != count:
            continue
        last = selected[-1]
        op_seconds = {}
        for item in selected:
            for key, value in item.get('operation_seconds', {}).items():
                op_seconds[key] = op_seconds.get(key, 0.0) + value
        prefixes[str(count)] = {
            'outer_pc_calls': count,
            'per_PC_operation_seconds_sum': op_seconds,
            'operation_seconds_scope': 'sum of stored PC operation timers; excludes outer A6/orthogonalization, setup and diagnostics; timer scopes may overlap',
            'last_cumulative_trace_counts': last.get('trace_counts'),
            'p4_counts_summed_over_PC_records': {
                key: sum(item.get('p4_counts', {}).get(key, 0) for item in selected)
                for key in last.get('p4_counts', {})
            },
        }
    solve = summary['solve']
    rows.append({
        'label': label, 'source_sha': summary['source_sha'],
        'physical_model_sha256': physical, 'mode_sha256': mode,
        'profile': summary['profile'], 'raw_bindings': bindings,
        'node_time_scope': 'historical recorded solve_seconds, conservative_realtime; no interpolation or conversion from monotonic',
        'nodes_through_64': [item for item in nodes if item['iteration'] <= 64],
        'all_actual_nodes': nodes,
        'duplicate_node_policy': 'earliest raw record at a given iteration; duplicates preserved in raw files',
        'setup_to_solve_start': setup,
        'prefix_counts_and_operation_costs': prefixes,
        'terminal': {key: solve.get(key) for key in
                     ('iterations', 'final_true_residual', 'pc_apply_count', 'matvec_count',
                      'explicit_action_count', 'restart', 'max_it', 'zero_start')},
        'cost': {key: summary.get(key) for key in ('elapsed_conservative_seconds',
                 'elapsed_monotonic_seconds', 'solve_conservative_seconds', 'solve_monotonic_seconds')},
        'parent_workflow_clock_interval': run.get('workflow_clock_interval'),
        'resource': {key: authority.get(key) for key in
                     ('sampled_process_tree_rss_peak_bytes', 'sampled_process_tree_swap_peak_bytes',
                      'global_swap_activity', 'memory_scope', 'descendants_cleared', 'remaining_child_pids')},
        'official_result_in_raw_worker_summary': summary.get('official_result'),
        'historical_status': summary['status'],
    })
result = {'schema': 'task39extra.v12.supplement.historical-comparison.v1',
          'classification': 'derived_read_only_raw_evidence_audit',
          'new_PDE_runs': 0, 'errors': errors, 'historical_cases': rows,
          'comparison_boundary': 'same frozen original physical A6 and modes; different PCs, inner work and source versions. Same iteration is not equal work. Use common actual nodes and explicit time scopes. V5 later recovered official output separately; original worker failed only output recovery.'}
OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'output': str(OUT), 'sha256': sha(OUT), 'errors': errors,
                  'cases': [{'label': r['label'], 'nodes': [(n['iteration'], n['explicit_true_residual'], n.get('solve_seconds')) for n in r['nodes_through_64']],
                             'setup_seconds': r['setup_to_solve_start']['budget_seconds']} for r in rows]}, indent=2))
assert not errors, errors
