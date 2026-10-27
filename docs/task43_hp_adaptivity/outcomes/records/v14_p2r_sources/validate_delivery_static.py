"""Static delivery checks only; no native or project imports."""
import ast,hashlib,json,re,subprocess,time
from pathlib import Path
start=time.perf_counter();R=Path('/home/fenics/Projects/NN-Lab-V2');D=R/'docs/task43_hp_adaptivity';E=D/'outcomes/records/v14_p2r_sources'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks={};fail=[]
for f in [D/'outcomes/records/v14_p2r_budget_extension_results_v1.json',*E.rglob('*.json')]:j(f)
checks['json_files']=1+len(list(E.rglob('*.json')))
for row in j(E/'copies_index.json'):
 if sha(R/row['original'])!=row['sha256'] or sha(R/row['copy'])!=row['sha256']:fail.append(row['original'])
checks['copied_originals']=len(j(E/'copies_index.json'))
for row in j(E/'raw_index.json'):
 if sha(R/row['path'])!=row['sha256']:fail.append(row['path'])
checks['raw_index_files']=len(j(E/'raw_index.json'))
for row in j(E/'preparation/local_static_fix_validation.json')['files']:
 if sha(R/row['path'])!=row['sha256']:fail.append(row['path'])
# AST was already checked on these exact bytes; do not re-execute any fixture.
checks['final_fix_hashes_match_prior_AST']=not fail
for k,v in j(E/'plan_output/A2_saved_primary_q_response.json')['substage_checkpoint_refs'].items():
 if sha(Path(v['path']))!=v['sha256']:fail.append('checkpoint '+k)
checks['A2_substage_hashes']=4
s=j(E/'plan_output/actual_authority_before_fe_gate.json')['space_authority_detail']; bad=[]
for k,v in s['leaf_parent_degree_inheritance_by_root'].items():
 if s['leaf_inheritance_by_root'][k]['degree_counts']!={f"p{v['parent_degree']}":v['leaf_count']}:bad.append(k)
checks['actual_parent_inheritance']={'roots':len(s['leaf_parent_degree_inheritance_by_root']),'leaves':sum(v['leaf_count'] for v in s['leaf_parent_degree_inheritance_by_root'].values()),'bad_roots':bad};fail.extend(bad)
contract=j(D/'outcomes/records/v11_scientific_restart_contract.json');base=R/contract['artifact_prefix'];downstream=['formal/A1_q_attempt3','formal/R9_H8_attempt1','support/union_comparison_attempt1'];checks['downstream_roots_absent']={str(base/x):not (base/x).exists() for x in downstream}
if not all(checks['downstream_roots_absent'].values()):fail.append('unexpected downstream root')
checks['failed_P2_success_products_absent']={x:not Path(x).exists() for k,x in j(D/'outcomes/records/v12_execution_recovery_manifest.json')['p2_sources']['P2R'].items() if k in ['audit_path','bundle_path']}
if not all(checks['failed_P2_success_products_absent'].values()):fail.append('unexpected P2 pass product')
files=[D/'response_v14.md',D/'README.md',D/'outcomes/summary.md',D/'outcomes/selective_merge_manifest.md',R/'docs/development_model_registry.md',R/'docs/development_progress.md']
# Check only this delivery's response and newly inserted current section, not immutable history.
links=[]
for p in files:
 text=p.read_text()
 if p.name not in ['response_v14.md','README.md']:text=text.split('## V13')[0].split('## Task43 V13')[0]
 for target in re.findall(r'\]\(([^)]+)\)',text):
  if target.startswith(('https:','http:','#')):continue
  path=(p.parent/target.split('#')[0]).resolve();links.append(str(path))
  if not path.exists():fail.append('missing link '+str(path))
checks['local_links']=len(links)
diff=subprocess.run(['git','diff','--check'],cwd=R,text=True,capture_output=True);checks['git_diff_check_exit']=diff.returncode
if diff.returncode:fail.append(diff.stdout+diff.stderr)
patch=subprocess.check_output(['git','diff','--','benchmarks/task43_hp_adaptivity/round1_candidates.py','src/test/test_task43_v11_scientific_restart.py'],cwd=R)
(E/'static_fix.diff').write_bytes(patch)
record=dict(status='PASS' if not fail else 'FAIL',checks=checks,failures=fail,elapsed_seconds=time.perf_counter()-start,scope='stdlib JSON/hash/link/format and saved-record arithmetic; no project/native call or fixture execution')
(E/'delivery_static_validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False,indent=2))
raise SystemExit(bool(fail))
