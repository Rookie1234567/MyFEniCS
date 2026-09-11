"""Recount inherited and new measured workflow debit without changing ledgers."""
import argparse
import hashlib
import json
import math
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('ledger', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
ledger = json.loads(args.ledger.read_text())
errors = []
hashes = {str(args.ledger): hashlib.sha256(args.ledger.read_bytes()).hexdigest()}
source = ledger['inherited_source_ledger']
old_path = Path(source['path'])
old = json.loads(old_path.read_text())
hashes[str(old_path)] = hashlib.sha256(old_path.read_bytes()).hexdigest()
if hashes[str(old_path)] != source['sha256']:
    errors.append('inherited original ledger hash changed')
for key in ('schema', 'profile', 'total_limit_seconds', 'o1_workflow_limit_seconds', 'o1_compute_limit_seconds'):
    if ledger[key] != old[key]:
        errors.append(f'inherited budget contract changed: {key}')
if ledger['total_limit_seconds'] != 10800:
    errors.append('formal cap changed')
for binding in ledger['inherited_evidence']:
    p = Path(binding['path'])
    hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    if hashes[str(p)] != binding['sha256']:
        errors.append(f'inherited failed evidence hash changed: {p}')
entries = ledger['attempts'] + ledger['inherited_engineering_attempts']
if len({entry['root'] for entry in entries}) != len(entries):
    errors.append('duplicate workflow root in total debit')
rows = []
for entry in entries:
    terminal_path = Path(entry['root']) / 'terminal.json'
    terminal = json.loads(terminal_path.read_text())
    hashes[str(terminal_path)] = hashlib.sha256(terminal_path.read_bytes()).hexdigest()
    actual = terminal['workflow_clock_interval']['budget_seconds']
    if not math.isclose(entry['actual_seconds'], actual, rel_tol=1e-12, abs_tol=1e-8):
        errors.append(f'workflow debit differs from terminal: {entry["root"]}')
    if entry['status'] != terminal['classification']:
        errors.append(f'workflow status differs from terminal: {entry["root"]}')
    if not terminal['descendants_cleared']:
        errors.append(f'descendants not cleared: {entry["root"]}')
    rows.append({'stage': entry['stage'], 'source_sha': entry['source'], 'root': entry['root'],
                 'classification': entry['status'], 'conservative_seconds': actual,
                 'monotonic_seconds': terminal['workflow_clock_interval']['elapsed_seconds']['monotonic']})
total = sum(row['conservative_seconds'] for row in rows)
if not math.isclose(total, ledger['charged_seconds'], rel_tol=1e-12, abs_tol=1e-8):
    errors.append('final total debit does not equal distinct actual workflow charges')
if total > ledger['total_limit_seconds']:
    errors.append('formal total cap exceeded')
if not math.isclose(ledger['total_limit_seconds'] - total, ledger['remaining_seconds'], rel_tol=1e-12, abs_tol=1e-8):
    errors.append('remaining debit inconsistent')
result = {'scope': 'formal conservative workflow debit, including prior engineering failure exactly once; excludes implementation activity',
          'errors': errors, 'new_PDE_runs': 0, 'rows': rows, 'conservative_total_seconds': total,
          'limit_seconds': ledger['total_limit_seconds'], 'remaining_seconds': ledger['total_limit_seconds'] - total,
          'observed_implementation_metadata': ledger['implementation_activity'], 'hashes': hashes}
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: result[key] for key in ('errors', 'conservative_total_seconds', 'limit_seconds', 'remaining_seconds')}))
raise SystemExit(bool(errors))
