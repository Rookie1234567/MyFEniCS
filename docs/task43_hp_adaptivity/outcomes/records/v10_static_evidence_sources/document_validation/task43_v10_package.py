"""Package existing static records; never execute archived programs."""
import datetime, hashlib, json, shutil
from decimal import Decimal
from pathlib import Path
root=Path('/home/fenics/Projects/NN-Lab-V2')
rel=Path('docs/task43_hp_adaptivity/outcomes/records')
src=root/rel/'v10_static_evidence_sources'
art=root/'benchmarks/artifacts/task43/v10_static_correction'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def ident(p): return {'path':str(p.relative_to(root)),'sha256':sha(p)}
draft=src/'v10_static_evidence_correction_v1.json'
shutil.copy2(draft,art/'agent_closeout_draft_path_and_command_errors.json')
obj=json.loads(draft.read_text())
review=src/'root_review';review.mkdir()
for p in [art/'root_independent_accounting.json',art/'root_final_static_comparison_attempt3.json',Path('/tmp/task43_v10_root_verify.py'),Path('/tmp/task43_v10_compare_final.py')]:
    shutil.copy2(p,review/p.name)
evidence=src/'static_action_records';evidence.mkdir()
for p in sorted(art.glob('root_*')):
    if p.is_file() and p.suffix in ('.time','.stderr','.stdout','.exit_code','.py'):
        shutil.copy2(p,evidence/p.name)
for n in range(1,5):
    sub=evidence/f'agent_parser_attempt{n}';sub.mkdir()
    for name in ('run.json','parser.stdout','parser.stderr'):
        shutil.copy2(art/f'agent_parser_attempt{n}'/name,sub/name)
for folder in ('input_context_build','input_context_build_attempt2'):
    sub=evidence/folder;sub.mkdir()
    for name in ('time','stdout','stderr','exit_code','started.txt','finished.txt'):
        p=art/folder/name
        if p.exists(): shutil.copy2(p,sub/name)
obj['derived_packaging_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
obj['identity'].update({'repository':'Rookie1234567/MyFEniCS','branch':'task43_hp_adaptivity','canonical_worktree':str(root),'reviewed_historical_delivery':'782c57fe4339fac2fe73fca2942b0d654024dda5','historical_actual_d3_run_head':'ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba','baseline_sha':'405e3aff42ac421a4c99315df1ed9b96941ecbe4'})
obj['corrected_derivation']['parser']['method']='EDGE/BRIDGE header separation of preserved text; PACKAGE line closes reported source-line range; not the historical generator'
run=json.loads((art/'agent_parser_attempt4/run.json').read_text())
obj['corrected_derivation']['derived_utc']=run['finished_utc']
obj['independent_root_review']['package_terminated_parse']['git_copy']=ident(review/'root_independent_accounting.json')
obj['independent_root_review']['package_terminated_parse']['script']=ident(review/'task43_v10_root_verify.py')
obj['independent_root_review']['package_terminated_parse']['elapsed_seconds_is_nested_not_added']=True
obj['independent_root_review']['final_comparison']['git_copy']=ident(review/'root_final_static_comparison_attempt3.json')
obj['independent_root_review']['final_comparison']['script']=ident(review/'task43_v10_compare_final.py')
obj['independent_root_review']['personal_read']='Root personally read raw lines 408-505 including all three EDGE/BRIDGE boundaries, the collector source, all three old/new four-field differences, final corrected spans, and activation/MCA input excerpts; then inspected independent set and all-field comparisons.'
obj['attempt_ledger']['auxiliary_read_error']={'command':'rg --files docs/task43_hp_adaptivity/outcomes/records/v10_static_evidence_sources && cat docs/task43_hp_adaptivity/outcomes/records/v10_static_evidence_sources/derived/accounting.json','exit_code':1,'elapsed_seconds':0.090485988,'timing_source':'exec tool wall_time_seconds; chunk 4b98e0','failure':'assumed accounting.json did not exist; rg listing succeeded, cat failed; subsequent actual map/diff reads succeeded','scope':'read-only bookkeeping error, no data generation or runtime'}
obj['attempt_ledger']['closeout_path_read_error']={'command':'cat docs/task43_hp_adaptivity/outcomes/records/v10_static_evidence_correction_v1.json','exit_code':1,'elapsed_seconds':0.156572441,'timing_source':'exec tool wall_time_seconds; chunk aa189a','failure':'agent draft was placed one directory too deep; root located existing file and moved corrected delivery to authorized path','scope':'read-only bookkeeping error'}
obj['attempt_ledger']['agent_draft_review_corrections']={'draft':ident(art/'agent_closeout_draft_path_and_command_errors.json'),'issues':['wrong closeout output directory','auxiliary read failure command incorrectly attributed to timing_ledger.json instead of actual derived/accounting.json','agent parser described as PACKAGE-delimited although implementation separates EDGE/BRIDGE headers'],'resolution':'root corrected these new draft metadata only; original draft retained ignored'}
obj['attempt_ledger']['static_evidence_archive']=[ident(p) for p in sorted(evidence.rglob('*')) if p.is_file()]
obj['timing']['closeout_path_read_error_seconds']=0.156572441
new=Decimal(str(obj['timing']['v10_recorded_sum_including_read_error_seconds']))+Decimal('0.156572441')
obj['timing']['v10_recorded_sum_including_read_error_seconds']=float(new)
obj['timing']['combined_recorded_sum_with_v8_v9_seconds']=float(Decimal('55.18740113839802')+new)
obj['timing']['not_measured']+=['root/agent source edits and manual content review, untimed JSON/hash packaging, Git preparation','agent final JSON/context read check had no separate saved timer; not new sanity or pytest']
obj['timing']['limits_seconds']={'single_static_action':60,'v10_new_measured':300,'historical_plus_v10_measured':600}
obj['timing']['closeout_additional_measured_actions']='Packaging, final document checks and GitHub rendering are added by root in final_document_validation; no nested times counted twice.'
obj['qualification'].update({'historical_d3_and_20_tests':'ACCEPTED_LIMITED_ENGINEERING_BY_FORMAL_V9_REVIEW; reused, not rerun','new_counts':dict.fromkeys(['support_driver','sanity','native_import','ABI_run','pytest','collect_only','PDE','formal_dispatch','READY'],0),'historical_quotas':{'formal':'5/6','A1':'2/2','A2':'3/3','sanity':'1/1','D3':'1/1','last_formal_slot':'SEALED'},'capabilities':{'space':'PARTIAL','selection':'PARTIAL','accuracy':'NOT_PASSED','equal_accuracy_whole_cost':'NOT_ESTABLISHED','iteration':'NOT_RUN / NOT_QUALIFIED'},'merge_approval':False,'locked':['A1/A2 q retry','A1_R','A2_R','B/C','fresh baseline','equal accuracy cost campaign','iteration','0.7 nm','NN/FTT']})
obj['unknowns']=['historical V1 JSON generator, exact invocation, source statement and generation time','historical full process mappings cannot be reconstructed from dependency capture','installed path strings/package evidence do not replace a build-time header or full runtime closure']
target=root/rel/'v10_static_evidence_correction_v1.json'
with target.open('x') as f: json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
draft.unlink()
print(json.dumps({'output':ident(target),'archived_action_files':len(obj['attempt_ledger']['static_evidence_archive']),'current_corrected_map_sha256':sha(src/'corrected/direct_needed_edge_map_corrected.json')},indent=2))
