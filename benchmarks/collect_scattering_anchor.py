"""Bounded compact collector for complete finite scattering anchors.

Reads only V49 parents and scalar records, independently checks their byte
identities and frozen criteria, and preserves raw logs/source versions. No FE
operator, factor, learned model or field integration is constructed here.
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.scattering_anchor_scope import ROOT,ARTIFACT,stage,window
from src.solvers.scattering_anchor_checks import complete_finite_gate


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(2**20),b''):h.update(block)
    return h.hexdigest()


def collect():
    window.guard_worker_parent()
    folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    if not folder.resolve().is_relative_to(window.TMP):raise ValueError('V49 collector namespace')
    out=folder/'records';out.mkdir(exist_ok=False)
    cost=stage('COST');verified=stage('VERIFY_P4')
    checks=[{'case':r['case'],**complete_finite_gate(r)} for r in verified['pairs']]
    if len(checks)!=2 or {r['case'] for r in checks}!={'REGULAR','NOTCH'}:raise ValueError('both finite physical cases required')
    if not all(r['FINITE_OBSERVABLE_PASS'] for r in checks):raise ValueError('finite physical criteria failed; recorded status cannot override numbers')
    write_json(out/'finite_independent_checks_v49.json',{'checks':checks,'parent':json.loads((ARTIFACT/'VERIFY_P4.json').read_text()),'no_new_science_actions':True})
    write_json(out/'cold_n1_costs_v49.json',{'routes':[{k:v for k,v in r.items() if k!='lifecycle_events'} for r in cost['routes']],
        'incremental_costs_not_total_research':True,'startup_unknowns_retained':True,'shared_workstation':True,'speedup_under_equal_cache_load':'INCONCLUSIVE'})
    write_json(out/'object_lifetimes_v49.json',{'routes':[{'stage':r['stage'],'source_sha':r['source_sha'],'events':r['lifecycle_events'],
        'sampled_tree_peak_bytes':r['process_tree_sampled_peak_bytes']} for r in cost['routes']],
        'visible_owner_bytes_are_lower_bounds_not_RSS':True,'opaque_factor_workspace_bytes':'unknown; included in independently sampled RSS'})
    controls=[]
    for case in ('REGULAR','NOTCH'):
        pair=[r for r in cost['routes'] if r['stage'] in ('REFERENCE_'+case,'ENGINE_'+case)]
        best_time=min(pair,key=lambda r:r['cold_N1_measured_dat_launch_lower_bound_seconds'])
        best_peak=min(pair,key=lambda r:r['process_tree_sampled_peak_bytes'])
        controls.append({'case':case,'best_observed_time_stage':best_time['stage'],
            'time_lower_bound_seconds':best_time['cold_N1_measured_dat_launch_lower_bound_seconds'],
            'best_observed_simultaneous_peak_stage':best_peak['stage'],'peak_bytes':best_peak['process_tree_sampled_peak_bytes'],
            'NN_required_peak_at_most_bytes':.8*best_peak['process_tree_sampled_peak_bytes'],
            'cache_load_equivalence':'INCONCLUSIVE; observed necessary controls, not uncontended speedup'})
    write_json(out/'opportunity_decision_v49.json',{'opportunities':cost['opportunity'],'best_non_neural_observed_controls':controls,'p_increment_accuracy_unsettled':True,
        'NN_NOT_TRAINED_THIS_BATCH':True,'NN20':'NOT_DEMONSTRATED','target_qualification':False,
        'single_future_object_only':'complete physical FE+DtN field coefficients avoiding condensation/factors; no teacher or training authorization',
        'prioritize_exact_sharing_for_deterministic_repeated_construction':True})
    write_json(out/'p_increment_v49.json',{'result':cost['p_increment'],'parent':json.loads((ARTIFACT/'COST.json').read_text()),
        'cross_degree_scattered_definition':'each degree uses its own original FE-interpolated layered background; differences include background representation error. Total E/curl give an unambiguous nonconvergence signal.',
        'continuum_convergence':False})
    write_json(out/'complete_physical_results_v49.json',{'p4':verified['pairs'],
        'powers':[{ 'stage':r['stage'],'port':stage(r['stage'])['output']['port_metrics'],'volume':stage(r['stage'])['output']['volume_metrics']} for r in cost['routes']],
        'equation_qualification':'COMPLETE_FINITE_EQUATION_PASS','observable_qualification':'FINITE_OBSERVABLE_PASS according to independently recomputed frozen criteria',
        'p_increment':'MEASURED_NOT_CONVERGED','TARGET_NOT_QUALIFIED':True,'NN_NOT_TRAINED_THIS_BATCH':True})
    runs=window.ledger()['runs'];resources=[];maxgap=0.;peak=0;swap=0;total_samples=0
    for r in runs:
        p=Path(r['folder'])/'supervision/resources.jsonl'
        samples=[json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
        times=[s['elapsed_seconds'] for s in samples];gap=max((b-a for a,b in zip(times,times[1:])),default=0.)
        maxgap=max(maxgap,gap);peak=max(peak,r['peak_bytes']);swap=max(swap,r['swap_bytes']);total_samples+=len(samples)
        resources.append({k:r[k] for k in ('role','source_sha','folder','classification','elapsed_seconds','peak_bytes','swap_bytes','descendants_cleared')} |
                         {'actual_max_sample_gap_seconds':gap,'sample_count':len(samples)})
    write_json(out/'resource_costs_snapshot_v49.json',{'runs':resources,'known_prior_lower_seconds':88875.68891642192,
        'charged_before_collector_settlement_seconds':window.charged_wall(),'sampled_tree_peak_bytes':peak,'own_swap_peak_bytes':swap,
        'actual_sample_max_gap_seconds':maxgap,'sample_count':total_samples,'scope':'shared-workstation; sampled whole launcher and all descendants; no continuous kernel cgroup hard-limit claim',
        'current_collector_and_final_documentation_not_yet_settled':True,'historical_unknowns_retained':True})
    pointers={p.stem:json.loads(p.read_text()) for p in ARTIFACT.glob('*.json')}
    write_json(out/'run_index_v49.json',{'runs':[{k:r[k] for k in ('role','folder','source_sha','classification')} for r in runs],
        'complete_stage_pointers':pointers,'minimum_package':str(window.TMP/'minimum_result_cost_package.json')})
    from src.io.scattering_anchor import load_scattering_anchor
    from src.solvers.scattering_anchor import configuration
    cases=[];cfg=configuration('REGULAR')
    for case in ('REGULAR','NOTCH'):
        parent=stage('REFERENCE_'+case)
        with np.load(parent['arrays']['path'],allow_pickle=False) as a:
            ids=np.flatnonzero(a['cell_tags']!=a['regular_tags'])
            cases.append({'case':case,'new_per_case_descriptor_sha256':load_scattering_anchor(ROOT/f'input/task042_neural_coarse_inverse/v49_reference_{case.lower()}.dat').physical_model_sha256,
                'immutable_original_manifest_sha256_scope':parent['physical_contract_sha256'],'source_sha':parent['source_sha'],
                'parent_npz_sha256':parent['arrays']['sha256'],'changed_cell_ids':ids.tolist(),'changed_cell_centers_nm':a['cell_centers'][ids].tolist(),
                'material_cell_counts':{str(int(v)):int(np.sum(a['cell_tags']==v)) for v in np.unique(a['cell_tags'])},
                'original_member_hashes':{k:parent['arrays']['members'][k] for k in ('geometry_x','geometry_dofmap','cell_centers','cell_tags','regular_tags')}})
    write_json(out/'physical_identity_bindings_v49.json',{'cases':cases,'tag_roles':{'air':cfg.tags.air,'substrate':cfg.tags.substrate,'Si_block':cfg.tags.grating},
        'errata':'early e184 reference manifests bound the full two-case inventory hash; independently audited arrays now bind actual per-case descriptors. Earlier 0 volume/factor counters were placeholders, not measured zeros.',
        'historical_raw_not_rewritten':True,'independent_geometry_RHS_field_pairing':'VERIFY_P4 exact geometry/material ordering and original RHS checks'})
    array_files=[]
    for p in ARTIFACT.rglob('*.npz'):
        array_files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':digest(p)})
    write_json(out/'array_inventory_v49.json',{'files':array_files,'member_hashes_are_bound_in_parent_results':True,
        'failed_arrays_preserved':True,'no_array_numbers_replayed_by_this_collector':True})
    archive=ARTIFACT/('raw_'+folder.name);archive.mkdir(exist_ok=False);items=[];seen=set()
    roots=[window.TMP]+[Path(r['folder']) for r in runs]+[ARTIFACT]
    for root in roots:
        for p in root.rglob('*'):
            if not p.is_file() or p.is_relative_to(archive) or p.is_relative_to(out) or p in seen:continue
            seen.add(p)
            if p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.txt','.dat','.py') or p.stat().st_size>8*2**20:continue
            # Avoid enumerating the isolated compiled/bytecode caches as raw
            # logs; their actual source and dependency inventories are separate.
            if any(x in p.parts for x in ('pycache','xdg','tmp','torch','uv','ruff')) and not p.is_relative_to(window.TMP):continue
            if p.is_relative_to(window.TMP) and any(x in p.relative_to(window.TMP).parts for x in ('pycache','xdg','tmp','torch','uv','ruff')):continue
            h=digest(p);target=archive/h
            if not target.exists():shutil.copyfile(p,target)
            items.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':h,'archived':str(target.relative_to(ROOT))})
    write_json(out/'raw_archive_index_v49.json',{'files':items,'unique_bytes':sum(p.stat().st_size for p in archive.iterdir()),
        'raw_stderr_policy':'supervisor retains worker stderr merged into unmodified supervision/worker.log; outer stderr is also preserved',
        'archive_excludes_large_scientific_NPZ_and_compiled_cache':True,'scope':'only new V49, not old Task042 campaigns'})
    versions={}
    for r in runs:
        mp=Path(r['folder'])/'run_manifest.json'
        if not mp.exists():continue
        manifest=json.loads(mp.read_text())
        for name,h in manifest['implementation_hashes'].items():
            versions[(r['source_sha'],name)]=h
    requests=sorted(versions)
    data=subprocess.run(['git','-c','gc.auto=0','-c','maintenance.auto=false','cat-file','--batch'],cwd=ROOT,
                        input=''.join(f'{sha}:{name}\n' for sha,name in requests).encode(),capture_output=True,check=True).stdout
    pos=0;source_rows=[]
    for sha,name in requests:
        end=data.index(b'\n',pos);header=data[pos:end].decode().split();pos=end+1
        if len(header)!=3 or header[1]!='blob':raise ValueError('Git-bound source missing '+sha+':'+name)
        n=int(header[2]);content=data[pos:pos+n];pos+=n+1;h=hashlib.sha256(content).hexdigest()
        if h!=versions[(sha,name)]:raise ValueError('run manifest does not match clean Git source '+name)
        target=archive/h
        if not target.exists():target.write_bytes(content)
        source_rows.append({'source_sha':sha,'path':name,'git_blob':header[0],'bytes':n,'sha256':h,'archived':str(target.relative_to(ROOT))})
    if pos!=len(data):raise ValueError('source batch inventory consumption')
    write_json(out/'source_bindings_v49.json',{'rows':source_rows,'clean_Git_vs_run_hashes_verified':True,'donor_is_not_runtime_source':True,
        'shared_archive_bytes_after_source_snapshots':sum(p.stat().st_size for p in archive.iterdir()),'raw_log_index_bytes_exclude_later_source_snapshots':True})
    print(json.dumps({'records':len(list(out.glob('*.json'))),'raw_files':len(items),'raw_unique_bytes':sum(p.stat().st_size for p in archive.iterdir()),'new_FE_A_AH_factor_training':0}),flush=True)


if __name__=='__main__':collect()
