from pathlib import Path
import json,hashlib,shutil,time
started=time.perf_counter();R=Path.cwd();B=R/'benchmarks/artifacts/task43/v11_science';P=B/'recovery_v15';r=B/'support/union_comparison_attempt1';d=R/'docs/task43_hp_adaptivity/outcomes/records/v15_bugfix_sources/P5'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p)}
x=read(P/'preparation/union_comparison_attempt1_root_terminal_observations.json');s=x['summary'];c=read(r/'comparison/v11_r9_h8_union_comparison.json');v=read(P/'preparation/P5_data_stdlib_recheck.json');b=read(R/'docs/task43_hp_adaptivity/outcomes/records/v15_h_saved_primary_recovery_binding.json')
assert s['classification']=='COMPLETED' and s['leader_exit_code']==0 and s['elapsed_seconds']<1800 and s['descendants_cleared'] and not s['remaining_child_pids']
assert x['launcher_exit']==x['watchdog_exit']=='0'
assert all(z['current']==z['expected']==z['snapshot'] for z in x['source_checks']) and all(z['current']==z['expected'] for z in x['input_checks'])
assert not x['trace_parse_anomalies'] and not x['signals']
assert len(x['setters'])==3 and all(z['classification']=='SUCCESS_CPU1' and z['result']==0 and '_SCOTCH' in ''.join(z['stack']) for z in x['setters'])
assert all('[1]' in z['raw'] for z in x['all_syscall_records'])
issues=x['resource_observations_requiring_classification'];assert len(issues)==3
for row,why,m in issues:
 assert row==1737 and why=='empty cmdline; classify by state/identity' and m['pid'] in (3346456,3346467,3346468) and m['state']=='Z' and m['rss_bytes']==m['swap_bytes']==0
assert all(not v['same_process_still_present'] for v in x['post_exit_host_proc_checks'])
e=c['runtime_environment'];i=c['worker_identity'];assert e['mpi_size']==1 and e['rank_affinity']==[[1]] and 'complex128' in e['petsc_scalar_type'] and 'int64' in e['petsc_int_type'] and e['v11_mumps_available'] and set(e['v11_math_threads'].values())=={'1'}
assert i['direct_watchdog_parent_verified'] and i['tracer_descends_from_watchdog'] and i['tracer_proc_status_verified'];assert all(t['cpu_list']==[1] for t in i['worker_tid_affinities'])
assert c['status']=='COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE' and c['classification']=='NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE'
assert c['candidate_terminal_status']=='FAILED' and c['source_identity_start']==c['source_identity_end'] and c['input_identity_start']==c['input_identity_end'] and c['v12_p2_p4_input_identity_start']==c['v12_p2_p4_input_identity_end']
for z in b['fixed_inputs'].values():assert sha(Path(z['path']))==z['sha256']
assert v['comparison']['sha256']==sha(r/'comparison/v11_r9_h8_union_comparison.json')
resources=[json.loads(line) for line in (r/'watchdog/resources.jsonl').read_text().splitlines()]
cpu={}
for row in resources:
 for m in row['members']:
  key=str(m['pid']);cpu[key]={'comm':m['comm'],'last_sampled_cpu_seconds':max(cpu.get(key,{}).get('last_sampled_cpu_seconds',0),m.get('cpu_seconds') or 0),'start_ticks':m['start_ticks']}
root_record={'schema':'task43.v15.p4-p5-joined-root-closeout.v1','status':'COMPLETE_SAVED_PRIMARY_DIAGNOSTIC_NOT_ACCEPTANCE','P4_original_status':'FAILED_SUMMARY_NUMPY_SERIALIZATION_AFTER_SOLVE','P4_original_source_head':b['source_head'],'P4_failed_closeout':b['failed_attempt_closeout'],'P4_raw_recheck':b['root_raw_recheck'],'P4_primary_unchanged':b['fixed_inputs'],'P5_source_head':x['source_head'],'P5_status':c['status'],'P5_comparison':ref(r/'comparison/v11_r9_h8_union_comparison.json'),'P5_actual_FE':c['actual_FE'],'P5_q8':c['q8_robustness_classification'],'P5_q10':c['q10_primary_classification'],'sampling_sensitivity':c['sampling_sensitivity'],'original_FAILED_not_rewritten':True,'new_formal_PDE':0,'official_result':False,'passed':False,'selection_transition_written':False,'continuation_all_false':True,'scientific_scope':'fixed seed8 action and fixed Y6_1 discrete reference; improvement below frozen significance threshold; not overall accuracy/continuum convergence','P5_summary':s,'resources_sample_count':len(resources),'sampled_cpu_seconds_by_pid':cpu,'root_raw_data_recheck':ref(P/'preparation/P5_data_stdlib_recheck.json'),'root_observations':ref(P/'preparation/union_comparison_attempt1_root_terminal_observations.json'),'source_count':len(x['source_checks']),'input_count':len(x['input_checks']),'trace_summary':{'files':len(x['traces']),'lines':sum(t['lines'] for t in x['traces']),'syscalls':len(x['all_syscall_records']),'setters':3,'setter_classification':'all three successful CPU1 SCOTCH calls, lines842/882/922; no failed, unfinished, unknown or nonCPU1 setter','signals':0,'unique_stack_frames':104,'new_stack_frames_compared_with_P4_and_h_validation_already_read':0,'all_final_syscall_lines_and_exit_tails_read':True},'empty_cmdline_classification':'row1737 known worker/tracer/orted identities are Z, zero RSS/swap; all final host PID/start_ticks absent; not an unexplained live process','cleanup':x['post_exit_host_proc_checks'],'limits':{'work_seconds':1740,'whole_seconds':1800,'rss_bytes':8589934592,'task_swap_bytes':0},'unmeasured':['continuous RSS/PSS high-water','shared JIT/global cache audit','independent rerun of MPI/mode physics','new background sampler; scattered reference norms use worker scalar evidence'],'root_closeout_static_seconds':time.perf_counter()-started}
p=P/'preparation/P5_joined_root_closeout.json'
with p.open('x') as f:json.dump(root_record,f,indent=2);f.write('\n')
d.mkdir()
for src in (p,P/'preparation/P5_data_stdlib_recheck.json',Path('/tmp/task43_v15_recheck_p5_data.py'),Path(__file__),r/'watchdog/summary.json',r/'snapshots/launch_manifest.json',r/'snapshots/launch.sh',r/'comparison/saved_primary_recovery/restoration_identity.json',r/'launcher_exit_code.txt',r/'watchdog_exit_code.txt'):
 shutil.copyfile(src,d/src.name)
(d/'v11_r9_h8_union_comparison.json').write_text(json.dumps(c,separators=(',',':'))+'\n')
frames=sorted({l for p in (r/'strace').glob('sched.*') for l in p.read_text().splitlines() if l.startswith(' > ')})
(d/'trace_resource_excerpt.json').write_text(json.dumps({'traces':x['traces'],'syscalls':x['all_syscall_records'],'setters':x['setters'],'signals':x['signals'],'unique_frames':frames,'resource_rows_first_peak_last':[x['resource_rows'][0],max(x['resource_rows'],key=lambda v:v['rss_bytes']),*x['resource_rows'][-5:]],'empty_cmdline_observations':issues,'cleanup':x['post_exit_host_proc_checks'],'original_resources':ref(r/'watchdog/resources.jsonl'),'original_trace_scope':'all raw traces remain ignored; index with SHA/line count/tails and all unique frames/events retained here'},indent=2)+'\n')
(d/'runtime_identity.json').write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps({'root_closeout':ref(p),'P5_head':x['source_head'],'classification':c['classification'],'source_count':len(x['source_checks']),'input_count':len(x['input_checks']),'counts':root_record['trace_summary'],'cpu_seconds':cpu},indent=2))
