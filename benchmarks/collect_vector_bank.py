"""Compact storage receipts/costs collector. Metadata and hashes only, no arrays."""
import json
import os
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import file_hash
from src.solvers.vector_storage_scope import ARTIFACT, ROOT, guard_source, stage, window


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);source=guard_source(folder)
    out=folder/'records';out.mkdir(exist_ok=False)
    encoded=stage('ENCODE_EVALUATION');checked=stage('CHECK');analysis=stage('ANALYSIS')
    rows=[];necessity=[]
    for family,banks in encoded['banks'].items():
        raw=stage(f'CONSUME_{family}_RAW')
        for method,receipt in banks.items():
            r=stage(f'CONSUME_{family}_{method.replace(":","_")}')
            rows.append({'family':family,'method':method,'file_bytes':receipt['file_bytes'],
                         'encoding_seconds':receipt['encoding_seconds'],'load_seconds':r['load_seconds'],
                         'consume_seconds_including_all_decoding':r['consumer_seconds'],
                         'decoder_separate_seconds':'not instrumented separately; included in actual full consumer',
                         'objects':r['object_bytes'],'bank_sha256':receipt['sha256'],
                         'consumer_receipt':r['arrays'],'bit_identity':True})
        nn=stage(f'CONSUME_{family}_NN')
        necessity.append({'family':family,'NN_owned_resident_lower_bytes':nn['object_bytes']['resident_bank_bytes'],
                          'RAW_complete_upper_planning_bytes':raw['object_bytes']['complete_trace_bank_object_bytes'],
                          'NN_even_without_decoder_workspace_exceeds_80_percent_RAW':nn['object_bytes']['resident_bank_bytes']>.8*raw['object_bytes']['complete_trace_bank_object_bytes'],
                          'comparison_not_RSS':True})
    write_json(out/'candidate_comparison_v48.json',{'rows':rows,'strict_component_necessary':necessity,'timing_three_repeats':'NOT_RUN_COMPONENT_GATE','shared_workstation':True,'contention_comparison':'INCONCLUSIVE; no uncontended speedup claim'})
    trains={k:stage('TRAIN_'+k) for k in ('LIN','NN')}
    training=[]
    for k,r in trains.items():
        training.append({key:r[key] for key in ('kind','updates','parameter_count','parameter_change_norm','gradient_gate','Torch_threads','DataLoader_workers','selection') } |
                        {'selected_update':r['chosen']['update'],'selected_weights':r['chosen']['weights'],
                         'checkpoint_bytes':[{'update':c['update'],'bytes':c['validation_bank']['file_bytes']} for c in r['checkpoints']]})
    write_json(out/'model_training_v48.json',{'models':training,'heldout_after_freeze':True,'training_reference_parameters_read':False})
    write_json(out/'lossless_checker_v48.json',checked)
    groups=[]
    for family in encoded['banks']:
        for model in ('LIN','NN'):
            subset=[r for r in analysis['bit_diagnostics'] if r['family']==family and r['model']==model]
            summed={k:sum(r[k] for r in subset) for k in ('count','prediction_square_error','normalized_square_error','xor_bits','leading_zero_bits','sign_words_changed','exponent_words_changed','mantissa_words_changed')}
            groups.append({'family':family,'model':model,**summed,'all_direction_moment_groups':len(subset)})
    write_json(out/'prediction_bit_diagnostics_v48.json',{'aggregates':groups,'full_record':json.loads((ARTIFACT/'ANALYSIS.json').read_text()),'no_entropy_lower_bound_claim':True})
    write_json(out/'capacity_and_lifecycle_v48.json',{'necessary':analysis['necessary_conditions'],'actual_bank_populations':{'heldout':8,'migration':16},
              'lifetime':[{'phase':'prepare','resident':'one source collection and one candidate encode; not deployment'},{'phase':'train','resident':'train16 + validation4 source vectors, one-problem causal features, model/Adam/activations; no old A or FE'},{'phase':'consume','resident':'one deployed byte bank or RAW resident array, model/map/header, one decoded trace/current and bounded block; no original arrays/all-bank decode cache'},{'phase':'CHECK','resident':'original full coefficients/internal and one deployed bank plus independent outputs; correctness process cost charged'},{'phase':'target','resident':'internal recover, class/cache/factors, port/communication/audit and full engine identity unknown'}],
              'independent_full_vector_scenario':'add 28800*16*population raw internal bytes to each trace-bank object, all original internal bits retained',
              'complete_bank_byte_scope':'explicit Python-owned resident loads plus conservative decoder-workspace bound, not RSS; interpreter/allocator/library only in measured process-tree samples',
              'NN20':False,'qualified_full_engine':False})
    inventory=[]
    for p in ARTIFACT.rglob('*'):
        if p.is_file():
            inventory.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':file_hash(p)})
    write_json(out/'array_and_bank_inventory_v48.json',{'files':inventory,'no_arrays_numerically_read_by_collector':True})
    runs=window.ledger()['runs'];resource=[];maximum_gap=0.;peak=0;swap=0;sample_count=0
    for run in runs:
        path=Path(run['folder'])/'supervision/resources.jsonl'
        samples=[json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
        times=[s['elapsed_seconds'] for s in samples]
        gaps=[b-a for a,b in zip(times,times[1:])]
        maximum_gap=max(maximum_gap,max(gaps,default=0));sample_count+=len(samples)
        peak=max(peak,run['peak_bytes']);swap=max(swap,run['swap_bytes'])
        resource.append({'role':run['role'],'source_sha':run['source_sha'],'folder':run['folder'],'worker_seconds':run['elapsed_seconds'],'classification':run['classification'],'samples':len(samples),'max_sample_gap_seconds':max(gaps,default=0),'tree_sample_peak_bytes':run['peak_bytes'],'ownswap_bytes':run['swap_bytes'],'descendants_cleared':run['descendants_cleared']})
    write_json(out/'resource_costs_snapshot_v48.json',{'runs':resource,'charged_seconds_before_collector_settlement':window.charged_wall(),
              'known_prior_lower_seconds':88656.94151362307,'historical_unmeasured':'cold FE/CSR, unsupervised manual/Git/IO unknown',
              'sample_peak_bytes':peak,'ownswap_bytes':swap,'samples':sample_count,'max_actual_sample_gap_seconds':maximum_gap,
              'scope':'shared-workstation, sampled entire launcher/descendant tree; no delegated kernel cgroup hard limit claimed',
              'parent_consumer_costs_not_summed_with_nested_encoding_or_training_times':True,'all_new_A_AH_B_FE_MPI_GPU':0,
              'collector_not_yet_settled_in_this_snapshot':True,'final_fees_require_post_settlement_record':True})
    write_json(out/'run_index_v48.json',{'runs':[{k:r[k] for k in ('role','folder','source_sha','classification')} for r in runs],
              'pointers':{p.stem:json.loads(p.read_text()) for p in ARTIFACT.glob('*.json')},'collector_source':source})
    print(json.dumps({'compact_records':len(list(out.glob('*.json'))),'folder':str(out),'new_actions':0}),flush=True)


if __name__=='__main__':
    main()
