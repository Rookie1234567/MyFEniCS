"""Static F1 closeout: JSON scalar/table arithmetic and file/NPY byte identities only."""
import hashlib
import json
import math
from pathlib import Path
import time

started=time.monotonic()
repo=Path('/home/fenics/Projects/NN-Lab-V2')
root=repo/'benchmarks/artifacts/task43/v21_r10_h67/formal/R10_H67_attempt1'
def load(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
m=load(root/'run_manifest.json')
b=load(root/'root_primary_byte_readback.json')
raw=load(root/'run/primary_raw_vector_audit.json')
t=load(root/'run/v21_f1_terminal.json')
life=load(root/'root_lifecycle_readback.json')
pre=load(root/'run/pre_validation_checkpoint.json')
modal=load(root/'run/solve/dtn_port_diffraction_orders_3d.json')
checks={}
checks['42_primary_arrays_byte_hashes_match']=len(b['members'])==42 and not b['issues']
checks['terminal_and_audit_bind_exact_primary']=t['primary_packet']['npz_sha256']==raw['identity']['primary_packet']['npz_sha256']==b['sha256']
checks['prevalidation_file_hash_matches']=sha(Path(pre['npz_path']))==pre['npz_sha256']
checks['all_11_recovered_prevalidation_arrays_match_primary']=len(pre['arrays'])==11 and all(b['embedded_record']['arrays'].get('recovered_'+key)==value for key,value in pre['arrays'].items())
sources={rel:sha(repo/rel) for rel in m['sources']}
inputs={role:sha(Path(item['path'])) for role,item in m['inputs'].items()}
checks['post_exit_56_current_sources_equal_launch']=len(sources)==56 and all(sources[rel]==entry['sha256'] for rel,entry in m['sources'].items())
checks['post_exit_20_inputs_equal_launch']=len(inputs)==20 and all(inputs[role]==entry['sha256'] for role,entry in m['inputs'].items())
space_products=load(root/'root_release.json')['products']
checks['S_products_unchanged_after_F']=all(sha(Path(v['path']))==v['sha256'] for v in space_products.values())
norms={}
for name,limit in [('independent_A6',1e-8),('full_active_transformed',1e-8),('returned_condensed',1e-9)]:
    value=raw['audit'][name]
    quotient=value['residual_norm']/value['rhs_norm']
    checks[name+'_reported_quotient_consistent']=math.isclose(quotient,value['relative_residual'],rel_tol=1e-14,abs_tol=0)
    norms[name]={**value,'root_scalar_quotient':quotient,'limit':limit,'numerical_gate_pass':0<=quotient<=limit}
normal=raw['audit']['normal_correction']
checks['normal_strict_decrease']=0<=normal['after_relative_residual']<normal['before_relative_residual']
identity=b['embedded_record']['identity']
checks['normal_once_extra_zero']=identity['normal_correction_count']==1 and identity['extra_correction_count']==0
keys=[[x['side'],x['m'],x['n'],x['polarization']] for x in modal['orders']]
checks['612_modal_inventory_matches_primary']=len(keys)==612 and len({tuple(k) for k in keys})==612 and keys==identity['ordered_mode_keys']
checks['612_saved_power_and_complex_amplitudes_finite']=all(math.isfinite(v) for row in modal['orders'] for v in [row['power_ratio'],*row['outgoing_amplitude_at_boundary']])
power={}
for side,key in [('top','R_total'),('bottom','T_total')]:
    total=math.fsum(row['power_ratio'] for row in modal['orders'] if row['side']==side)
    stored=modal['metrics'][key]
    checks[key+'_612_table_sum']=math.isclose(total,stored,rel_tol=1e-12,abs_tol=1e-14)
    power[key]={'saved':stored,'root_table_sum':total,'difference':total-stored}
resource_lines=(root/'watchdog/resources.jsonl').read_text().splitlines()
window=[{'line':n,'sample':json.loads(resource_lines[n-1])} for n in range(6896,6905)]
checks['single_vanished_is_worker_exit_race']=life['vanished_samples_for_manual_classification']==[[6900,[3766301]]] and all([p['pid'] for p in entry['sample']['members']]==[3766298] for entry in window if entry['line']>=6901)
checks['lifecycle_no_unclassified_issue']=not life['issues']
checks['observed_failure_not_termination']=life['worker_exit_code']==1 and life['outer']['watchdog_exit_code']==2 and life['outer']['supervisor_exit_code']==2 and life['outer']['received_signal'] is None
checks['failed_terminal_never_qualified']=t['status']=='FAILED_OR_INCOMPLETE' and t['official_result'] is False and t['endpoint_record'] is None
result={
 'schema':'task43.v21.root_F1_numerical_stop.v1',
 'method':'Root reads all trace/resource rows, all primary member bytes and metadata, and independently divides saved scalar norms/sums all 612 saved modal rows. No native import, field-array norm re-execution, operator, sampling or scientific comparison outside monitored workflow.',
 'decision':'STOP_DYNAMIC_CHAIN_INDEPENDENT_A6_NUMERICAL_HARD_GATE',
 'checks':checks,'engineering_evidence_checks_all_true':all(checks.values()),
 'numerical_gates':norms,'normal_correction':normal,
 'only_failed_raw_gate':[k for k,v in raw['gates'].items() if v is False],
 'primary_npz':{'path':b['path'],'sha256':b['sha256'],'array_count':42,'qualified':False},
 'recovered_prevalidation_binding':{'arrays':11,'npz_sha256':pre['npz_sha256']},
 'source_end_scope':{'worker_success_end_snapshot':'NOT_REACHED_AFTER_NUMERICAL_FAILURE','post_exit_current_sources':sources,'post_exit_current_inputs':inputs,'replacement_of_worker_end':False},
 'partial_nonofficial_modal_observations':{'status':'MEASURED_BEFORE_A6_REJECTION_NOT_QUALIFIED_ENDPOINT','row_count':612,'aggregate_checks':power,'R00_s':modal['metrics']['R00_s'],'R00_p':modal['metrics']['R00_p'],'Av':'NOT_REACHED','energy_closure':'NOT_REACHED','J_G_q8_q10':'NOT_RUN'},
 'exit_race_classification':{'resource_line':6900,'pid':3766301,'start_ticks':318082594,'worker_trace_exit1_epoch':1793260640.532312,'orted_trace_exit0_epoch':1793260640.566704,'following_four_samples':'watchdog only; worker/tracer/orted absent','scope':'known exit race, not unclassified affinity or resource loss','raw_window':window},
 'cache_scope':'watchdog empty cache metadata stamp; no specific shared cache path monitored, so shared-cache stability is NOT_VERIFIED',
 'missing_scientific_products':['qualified primary endpoint','material Av q15 and actual form audit','energy closure','C common partition','q8/q10 J/G and response','benefit per added FE'],
 'next_stage':{'C':'NOT_RUN_BLOCKED_BY_NUMERICAL_GATE','F2':'NOT_ALLOWED_FOR_NUMERICAL_FAILURE','E1':'NOT_ALLOWED_FOR_NUMERICAL_FAILURE','E2':'NOT_ALLOWED_FOR_NUMERICAL_FAILURE'},
 'cause_boundary':'A6 scalar quotient genuinely exceeds the frozen limit; not a regex/display error. The physical/numerical cause of disagreement with the small condensed residual remains UNKNOWN; no component/parameter diagnosis was run.',
 'readback_seconds':time.monotonic()-started,
}
with (root/'root_numerical_stop.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'decision':result['decision'],'checks':checks,'norms':norms,'partial_power':power,'seconds':result['readback_seconds']},indent=2))
