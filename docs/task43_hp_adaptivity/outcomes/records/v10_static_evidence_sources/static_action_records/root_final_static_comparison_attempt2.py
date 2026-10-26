"""Static comparison of saved V10 derivations and hash-bound V9 input text only."""
import datetime
import hashlib
import json
from pathlib import Path

root = Path('/home/fenics/Projects/NN-Lab-V2')
art = root / 'benchmarks/artifacts/task43/v10_static_correction'
dest = root / 'docs/task43_hp_adaptivity/outcomes/records/v10_static_evidence_sources/corrected'
def read(p):
    return json.loads(p.read_text())
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
independent = read(art / 'root_independent_accounting.json')
corrected = read(dest / 'direct_needed_edge_map_corrected.json')
diff = read(dest / 'direct_needed_edge_field_diff.json')
expected = {(e['parent'], e['needed_soname']): e for e in independent['edges']}
actual = {(e['parent'], e['needed_soname']): e for e in corrected['edges']}
assert len(corrected['edges']) == len(actual) == len(expected) == 61
assert actual.keys() == expected.keys()
for key, e in expected.items():
    assert {f: actual[key][f] for f in e if f != 'raw_lines'} == {f: e[f] for f in e if f != 'raw_lines'}, key
    assert [actual[key]['source_line_start'], actual[key]['source_line_end']] == e['raw_lines'], key
for d, line_range in zip(diff['entries'], [[781,795], [829,844], [885,904]]):
    assert d['v1_json_lines'] == line_range, d['v1_json_lines']
    k = (d['key']['parent'], d['key']['needed_soname'])
    own = next(x for x in independent['field_differences'] if tuple(x['key']) == k)
    assert d['raw_stdout_lines'] == own['raw_lines']
    assert d['changed_fields'] == {f: {'v1': v['old'], 'corrected': v['corrected']} for f,v in own['changes'].items()}
objects = {}
for e in actual.values():
    identity = {f:e[f] for f in ('resolved_sha256','build_id','resolved_soname','needed_by_resolved_object','package_owner_line','package')}
    assert e['realpath'] not in objects or objects[e['realpath']] == identity
    objects[e['realpath']] = identity
assert objects == corrected['resolved_objects_by_realpath'] and len(objects) == 24
old_manifest = read(root/'docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/root_s1_review.json')['raw_manifest']
names = ['activation_mca.stdout','collect_activation_mca.sh','login_selector_env.stdout','record_login_selector_env.sh',
         'inspect_mca_override_files.stdout','inspect_mca_override_files.sh','inspect_sysconfdir_ownership.stdout',
         'inspect_sysconfdir_ownership.sh','mca_param_paths.stdout','inspect_mca_param_paths.sh',
         'mca_registry_strings.stdout','inspect_mca_registry_strings.sh','login_sources.stdout','inspect_login_mca_sources.sh']
verified = {}
for name in names:
    rel = 'benchmarks/artifacts/task43/v9_resume_preparation/raw/' + name
    h = sha(root/rel)
    assert h == old_manifest[rel], rel
    verified[rel] = h
transport = [e for e in corrected['edges'] if e['needed_soname'] in ('libmpi.so.40','libpmix.so.2','libpsm2.so.2','libpsm_infinipath.so.1','libmca_common_ofi.so.10','libfabric.so.1')]
result = {
    'schema':'task43.v10.root-final-static-comparison.v1',
    'derived_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'corrected_map_sha256':sha(dest/'direct_needed_edge_map_corrected.json'),
    'field_diff_sha256':sha(dest/'direct_needed_edge_field_diff.json'),
    'independent_accounting_sha256':sha(art/'root_independent_accounting.json'),
    'all_61_edges_all_original_fields_match_independent_package_terminated_parse':True,
    'three_legacy_line_ranges_match':True,
    'three_entries_twelve_field_changes_match':True,
    'unique_realpaths':len(objects),
    'one_identity_per_realpath':True,
    'verified_saved_input_files':verified,
    'transport_bindings':transport,
    'scope':'saved text and derived JSON only; no current installed object or runtime inspection',
}
with (art/'root_final_static_comparison_attempt2.json').open('x') as f:
    json.dump(result,f,ensure_ascii=False,indent=2)
    f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('verified_saved_input_files','transport_bindings')},indent=2))
