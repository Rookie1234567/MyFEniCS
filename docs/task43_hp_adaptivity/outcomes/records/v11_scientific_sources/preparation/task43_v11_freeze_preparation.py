from pathlib import Path
import ast,datetime,hashlib,json,subprocess,time,shutil
R=Path('/home/fenics/Projects/NN-Lab-V2'); P=R/'benchmarks/artifacts/task43/v11_science'
D=R/'docs/task43_hp_adaptivity/outcomes/records/v11_scientific_sources'
C=R/'docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json'
start=time.perf_counter()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
c=json.loads(C.read_text());checks={};sources=[]
allowed=c['actual_endpoint_rules']['source_change_allowlist']
for name in allowed:
 p=R/name;tree=ast.parse(p.read_text(),filename=name)
 sources.append({'path':name,'sha256':sha(p),'bytes':p.stat().st_size,'AST_parse':'passed_not_imported'})
 if name.startswith('src/test/'):
  names={x.name for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
  checks['all_eight_frozen_selectors_defined']=len(c['phases']['P1']['test_selectors'])==8 and all(s.split('::')[1] in names for s in c['phases']['P1']['test_selectors'])
checks['frozen_authority']=c['authority']['execution_start_head']=='70e2cfdcc3e5a7c3be5e8b714076420e3eac1129'
checks['branch']=subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip()=='task43_hp_adaptivity'
checks['fixed_environment']=c['model_settings']['worker_affinity_cpu_list']==[1] and c['model_settings']['mpi_size']==1 and set(c['model_settings']['threads'].values())=={1} and len(c['model_settings']['threads'])==6
inputs=[]
for item in c['inputs']:
 p=R/item['path'];actual=sha(p);inputs.append({**item,'actual_sha256':actual,'match':actual==item['sha256']})
checks['all_input_hashes_match']=all(x['match'] for x in inputs)
checks['input_roles_unique']=len({x['role'] for x in inputs})==len(inputs)
limits={'P2':(840,900,8589934592),'P3':(6900,7200,34359738368),'P4':(6900,7200,34359738368),'P5':(1740,1800,8589934592)}
checks['phase_budgets']=all(tuple(c['phases'][k][x] for x in ('work_seconds','whole_watchdog_seconds','rss_cap_bytes'))==v for k,v in limits.items())
checks['P1_budgets']=all(tuple(c['phases']['P1'][k][x] for x in ('work_seconds','whole_watchdog_seconds','rss_cap_bytes'))==(270,300,8589934592) for k in ('focused_attempt1','focused_recovery1'))
roots=[c['phases']['P1'][n]['root'] for n in ('focused_attempt1','focused_recovery1')]+[c['phases'][k]['root'] for k in limits]
checks['all_six_runtime_roots_absent']=all(not (P/n).exists() for n in roots)
checks['normal_one_extra_zero']=c['hard_gates']['normal_correction_count']==1 and c['hard_gates']['extra_correction_count']==0
checks['scientific_thresholds']=c['fixed_h_diagnostic_thresholds']['epsilon_J']==0.12716416232413652 and c['fixed_h_diagnostic_thresholds']['epsilon_G']==9.088158796603444e-6
checks['fixed_q_orders']=c['quadrature_response_thresholds']['orders']==[8,10]
shells=[]
(D/'launch').mkdir(exist_ok=True)
for p in sorted((P/'launch').glob('*.sh')):
 check=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True)
 shells.append({'path':str(p),'sha256':sha(p),'syntax_exit_code':check.returncode,'stdout':check.stdout,'stderr':check.stderr})
 q=D/'launch'/p.name
 if q.exists():raise RuntimeError('existing launch archive '+str(q))
 shutil.copyfile(p,q)
checks['five_unique_shells_prepared_no_recovery']=len(shells)==5 and not (P/'launch/focused_recovery1.sh').exists()
checks['shell_syntax']=all(x['syntax_exit_code']==0 for x in shells)
shutil.copyfile(P/'preparation/launch_source_paths.json',D/'preparation/launch_source_paths.json')
record={'schema':'task43.v11.root-p0-freeze-static-check.v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authority_head':c['authority']['execution_start_head'],'precommit_actual_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'contract_sha256':sha(C),'source':sources,'inputs':inputs,'checks':checks,'launch_shells':shells,'measured_static_seconds':time.perf_counter()-start,'dynamic_execution':'NOT_RUN; first launch will bind actual implementation commit','root_code_review':'Reviewed existing default branches, fixed-only CLI, primary persistence before sampling, actual raw-vector scopes, dedicated pending reader and common-partition physical comparison; P1 must establish runtime evidence.','run_slots_consumed':0}
p=D/'preparation/root_p0_freeze_static_check.json'
with p.open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'path':str(p),'checks':checks,'measured_static_seconds':record['measured_static_seconds']},ensure_ascii=False,indent=2))
if not all(checks.values()):raise SystemExit(1)
