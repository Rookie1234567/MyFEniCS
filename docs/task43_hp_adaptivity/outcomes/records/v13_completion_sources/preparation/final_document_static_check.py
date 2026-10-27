"""Read only final documents and saved evidence; never import project/native modules."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

start = time.monotonic()
repo = Path('/home/fenics/Projects/NN-Lab-V2')
base = repo / 'docs/task43_hp_adaptivity/outcomes/records'
sources = base / 'v13_completion_sources'
report = sources / 'preparation/final_document_static_check.json'
assert not report.exists(), 'immutable check record already exists'
checks = []
errors = []

def check(name, ok, detail):
    checks.append({'name': name, 'pass': bool(ok), 'detail': detail})
    if not ok:
        errors.append(name)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()

machine = base / 'v13_minimal_completion_and_scientific_results_v1.json'
j = json.loads(machine.read_text())
for name, expected in j['source_sha256'].items():
    actual = sha(repo / name)
    check('frozen_source:' + name, actual == expected, actual)
for name in ['original_contract', 'original_recovery_manifest']:
    entry = j['authority'][name]
    check(name, sha(repo / entry['path']) == entry['sha256'], entry)
check('branch', git('branch', '--show-current') == 'task43_hp_adaptivity', git('branch', '--show-current'))
check('run_HEAD_not_relabelled', j['run_heads'] == {'S1_completion': '7546c7bdb91b2c07c0344c41d418e8a0808ea6a6', 'D1': 'd8cba4f1377b526101c37213d5bc8e88db23effc'}, j['run_heads'])
changed = git('diff', '--name-only', '37f3376be410657fbaec86b0412086745419c506').splitlines()
allowed = set(j['source_sha256']) | {'docs/README.md', 'docs/development_model_registry.md', 'docs/development_progress.md', 'docs/task43_hp_adaptivity/README.md', 'docs/task43_hp_adaptivity/outcomes/summary.md', 'docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md'}
check('tracked_scope_and_history_unchanged', all(n in allowed or n.startswith('docs/task43_hp_adaptivity/outcomes/records/v13_completion_sources/') for n in changed), changed)
parsed = []
for path in sorted(sources.rglob('*.json')) + [machine]:
    json.loads(path.read_text())
    parsed.append(str(path.relative_to(repo)))
check('JSON_read', True, {'count': len(parsed), 'paths': parsed})
refs = []
skipped = []
def refs_walk(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get('path'), str) and isinstance(obj.get('sha256'), str):
            path = Path(obj['path'])
            if not path.is_absolute():
                path = repo / path
            if path.is_file() and path.stat().st_size <= 2_000_000:
                actual = sha(path)
                check('light_reference_hash:' + str(path), actual == obj['sha256'], actual)
                refs.append(str(path))
            else:
                skipped.append({'path': str(path), 'reason': 'large or nonlocal historical raw reference; not reverified in document check'})
        for value in obj.values():
            refs_walk(value)
    elif isinstance(obj, list):
        for value in obj:
            refs_walk(value)
refs_walk(j)
xml_path = repo / j['validation']['junit']['path']
cases = ET.parse(xml_path).findall('.//testcase')
check('saved_JUnit_12_pass', len(cases) == 12 and all(not list(c) for c in cases), {'case_count': len(cases), 'names': [c.attrib.get('name') for c in cases]})
for rel, count, peak in [('support/s1_completion_attempt1/resource_member_samples.json', 37, 313585664), ('support/authority_profile_attempt1/resource_rows.json', 769, 1302609920)]:
    data = json.loads((sources / rel).read_text())
    rows = [dict(zip(data['columns'], row)) for row in data['rows']]
    valid = len(rows) == count == data['row_count']
    for row in rows:
        members = [dict(zip(data['members_columns'], m)) for m in row['members']]
        valid &= sum(m['rss_bytes'] for m in members) == row['rss_bytes']
        valid &= sum(m['swap_bytes'] for m in members) == row['swap_bytes'] == 0
        valid &= all(m['affinity'] == [1] for m in members)
        valid &= row['rss_bytes'] <= row['launch_cap_bytes'] and row['available_bytes'] >= row['reserve_bytes']
    valid &= max(r['rss_bytes'] for r in rows) == peak
    check('compact_resource_arithmetic:' + rel, valid, {'rows': len(rows), 'peak': peak})
roots = ['recovery_v12/support/space_and_saved_primary_attempt2', 'formal/A1_q_attempt3', 'formal/R9_H8_attempt1', 'support/union_comparison_attempt1']
for rel in roots:
    p = repo / 'benchmarks/artifacts/task43/v11_science' / rel
    check('unlaunched_root_absent:' + rel, not p.exists(), str(p))
md_paths = [repo / name for name in allowed if name.endswith('.md')] + [repo / 'docs/task43_hp_adaptivity/response_v13.md']
links = []
for path in sorted(md_paths):
    if path.name == 'response_v13.md':
        text = path.read_text()
    else:
        diff = git('diff', '--unified=0', '--', str(path.relative_to(repo)))
        text = '\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        dest = (path.parent / target.split('#')[0]).resolve()
        links.append({'from': str(path.relative_to(repo)), 'target': target, 'exists': dest.exists()})
check('new_or_changed_markdown_links', all(item['exists'] for item in links), links)
proc = subprocess.run(['git', 'diff', '--check'], cwd=repo, text=True, capture_output=True)
check('git_diff_check', proc.returncode == 0, {'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr})
result = {'schema': 'task43.v13.final-document-static-check.v1', 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'command': 'python3 /tmp/task43_v13_final_static_check.py', 'script_sha256': sha(Path(__file__)), 'head': git('rev-parse', 'HEAD'), 'checks': checks, 'errors': errors, 'skipped_large_raw_rehash': skipped, 'source_and_test_bytes_unchanged': not any(x.startswith('frozen_source') for x in errors), 'new_driver_native_pytest_PDE_count': 0, 'measured_seconds': time.monotonic() - start, 'scope': 'stdlib-only JSON/hash/XML/link/resource arithmetic; no terminal-audit replay, native import or test execution'}
report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'report': str(report), 'checks': len(checks), 'errors': errors, 'seconds': result['measured_seconds'], 'skipped': skipped}, ensure_ascii=False))
raise SystemExit(bool(errors))
