"""Recount one completed run's raw watchdog samples without starting a solver."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('run', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
terminal_path = args.run / 'terminal.json'
sample_path = args.run / 'watchdog/resources.jsonl'
terminal = json.loads(terminal_path.read_text())
samples = [json.loads(line) for line in sample_path.read_text().splitlines()]
errors = []
for i, sample in enumerate(samples):
    envelope = sample['memory_envelope']
    if not sample['all_status_readable']:
        errors.append(f'{i}: unreadable process status')
    if sample['rss_bytes'] >= sample['launch_cap_bytes']:
        errors.append(f'{i}: RSS reaches launch cap')
    if envelope['effective_available_bytes'] < envelope['reserve_bytes']:
        errors.append(f'{i}: reserve crossed')
    if envelope['reserve_bytes'] < max(4 * 1024**3, .15 * envelope['effective_total_bytes']):
        errors.append(f'{i}: reserve below policy')
    if sample['launch_cap_bytes'] > 12000000000:
        errors.append(f'{i}: launch cap above policy')
    if sample['swap_bytes'] or sample.get('global_swap_stop_reason'):
        errors.append(f'{i}: swap evidence')
rss_peak = max(s['rss_bytes'] for s in samples)
if rss_peak != terminal['sampled_process_tree_rss_peak_bytes']:
    errors.append('terminal RSS peak differs from raw maximum')
if not terminal['descendants_cleared'] or terminal.get('remaining_child_pids'):
    errors.append('terminal descendants not cleared')
delta = {k: samples[-1]['global_swap_pages'][k] - samples[0]['global_swap_pages'][k]
         for k in ('pswpin_pages', 'pswpout_pages')}
if delta != terminal['global_swap_activity']['delta'] or any(delta.values()):
    errors.append('global swap delta differs from terminal or is nonzero')
result = {
    'scope': 'sampled simultaneous process-tree RSS/PSS and per-sample resource gates; excludes supervisor/test processes; not a continuous unsampled peak bound',
    'run': str(args.run), 'samples': len(samples), 'errors': errors,
    'rss_peak_bytes': rss_peak,
    'pss_peak_bytes': max(s['pss_bytes'] for s in samples if s['pss_bytes'] is not None),
    'pss_all_readable': all(s['pss_all_readable'] for s in samples),
    'pss_peak_scope': 'maximum of readable simultaneous process-tree PSS samples; missing samples retained separately',
    'pss_missing_samples': [
        {'sample_index': i, 'timestamp_ns': s['timestamp_ns'], 'rss_bytes': s['rss_bytes'],
         'pss_bytes': s['pss_bytes'], 'all_status_readable': s['all_status_readable']}
        for i, s in enumerate(samples) if s['pss_bytes'] is None or not s['pss_all_readable']
    ],
    'swap_peak_bytes': max(s['swap_bytes'] for s in samples),
    'global_swap_delta_pages': delta,
    'minimum_effective_available_bytes': min(s['memory_envelope']['effective_available_bytes'] for s in samples),
    'minimum_launch_cap_headroom_bytes': min(s['launch_cap_bytes'] - s['rss_bytes'] for s in samples),
    'cgroup_scope': 'recorded visible cgroup limits are part of each memory_envelope; RSS/PSS columns remain process-tree measurements',
    'classification': terminal['classification'],
    'descendants_cleared': terminal['descendants_cleared'],
    'charged_seconds': terminal['workflow_clock_interval']['budget_seconds'],
    'clock_interval': terminal['workflow_clock_interval'],
    'hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (terminal_path, sample_path)},
}
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k not in ('clock_interval', 'hashes')}))
raise SystemExit(bool(errors))
