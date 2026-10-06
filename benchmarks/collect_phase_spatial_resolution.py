"""V55 incremental settlement. Reuse audits, never recompute old FE integrals."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import phase_spatial_resolution_scope as scope
from benchmarks.collect_phase_notch_hp import measured_timeline,sampling_receipt,documents


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_receipt(path):
    """Describe an existing packet; never rewrite a producer's arrays."""
    from src.solvers.scattering_anchor import array_hash
    path=Path(path)
    with np.load(path,allow_pickle=False) as saved:
        members={n:dict(shape=list(saved[n].shape),dtype=str(saved[n].dtype),sha256=array_hash(saved[n])) for n in saved.files}
    return dict(path=str(path),sha256=digest(path),members=members)


def partial_saved_checks():
    """Useful saved-vector evidence after an original FE resource stop.

    This does not build a new oracle, integrate fields, or grant the missing
    fresh audit/energy/mesh-increment gates.
    """
    from benchmarks.check_phase_p_order_dtn import saved_original_volume_audit
    from src.solvers.phase_notch_hp_modes import keyed_modes
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    contract_path=scope.window.TMP/'partial_saved_inventory.json';contract=json.loads(contract_path.read_text())
    for key in ('minimal','failed_output'):
        item=contract[key]
        if digest(item['path'])!=item['sha256']:raise ValueError('partial producer record changed')
    r=json.loads(Path(contract['minimal']['path']).read_text());failed=json.loads(Path(contract['failed_output']['path']).read_text())
    if failed['status']!='FAILED' or r['case_spec']!=scope.case_spec('H7'):raise ValueError('partial producer classification/spec')
    output_folder=Path(contract['failed_output']['path']).parent
    rec=array_receipt(output_folder/'recovery.npz');fields=array_receipt(output_folder/'fields.npz')
    for name,receipt in (('recovery',rec),('fields',fields)):
        if receipt['sha256']!=contract[name+'_sha256']:raise ValueError('frozen partial '+name+' changed')
    record=r|dict(recovery_arrays=rec,output=dict(fields=fields))
    checked=saved_original_volume_audit(record)
    power_path=output_folder/'port_power.json';power=json.loads(power_path.read_text())
    if digest(power_path)!=contract['power_sha256']:raise ValueError('frozen partial mode output changed')
    keyed_modes(power,828)
    from src.solvers.scattering_anchor_checks import checked_arrays
    state=checked_arrays(r['arrays'])
    coordinate=max(abs(complex(*o['auxiliary_amplitude_total_projection'])-state['port'][o['auxiliary_index']])
                   /max(abs(state['port'][o['auxiliary_index']]),1e-30) for o in power['orders'])
    if coordinate>1e-10:raise ValueError('saved complete828 port coordinates')
    result=dict(status='PARTIAL_SAVED_VECTOR_AUDIT',role='H7',minimal=contract['minimal'],failed_output=contract['failed_output'],
        solve_source_sha=r['source']['source_sha'],postprocessing_source_sha=failed['source_sha'],
        arrays=r['arrays'],recovery_arrays=rec,fields=fields,saved_original_check=checked,
        mode_count=828,mode_power_path=str(power_path),mode_power_sha256=digest(power_path),port_coordinate_relative=coordinate,
        R_total=power['R_total'],T_total=power['T_total'],A_balance=power['A_balance'],R00_s=power['R00_s'],R00_p=power['R00_p'],R00_total=power['R00_total'],
        A_volume='not_run',independent_new_FE_verify='not_run',field_increment='not_run',full_physics_qualified=False,
        new_FE_calls=0,new_factor_count=0,new_complete_solves=0,
        scope='recompute existing original q47 vectors and independent saved q63 carrier; not a fresh FE audit or accuracy test')
    write_json(folder/'partial_saved_checks_v55.json',result)
    print(json.dumps(dict(status=result['status'],saved_vector_pass=checked['recalculated']['pass_gate'],full_physics_qualified=False)))


def collect():
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    states={r:scope.stage(r) for r in pointers};costs=[];sources={};identities=[];arrays=[];lifetimes=[]
    for run in scope.window.ledger()['runs']:
        directory=Path(run['folder']);manifest=json.loads((directory/'run_manifest.json').read_text());path=directory/('run_summary.json' if (directory/'run_summary.json').exists() else 'summary.json');summary=json.loads(path.read_text())
        worker=scope.ARTIFACT/directory.name;result=json.loads((worker/'result.json').read_text()) if (worker/'result.json').exists() else {}
        timings=measured_timeline(worker/'events.jsonl') if (worker/'events.jsonl').exists() else {}
        resources=sampling_receipt(directory/'supervision/resources.jsonl')
        costs.append(dict(role=run['role'],folder=run['folder'],source_sha=run['source_sha'],classification=summary['classification'],supervised_wall_seconds=run['elapsed_seconds'],
            dat_launch_lower_seconds=summary['launch_wall_seconds'],timings=timings,actual_calls=result.get('calls','unknown'),peak_bytes=run['peak_bytes'],swap_bytes=run['swap_bytes'],resources=resources,
            shared_workstation=True,cost_scope='exclusive intervals nested inside dat wall; do not add twice; cached increment not fresh cold N1'))
        sources[run['source_sha']]=manifest['implementation_hashes']
        if (directory/'resolved_config.json').exists():identities.append(dict(role=run['role'],source_sha=run['source_sha'],input_sha256=manifest['input_sha256'],resolved_sha256=digest(directory/'resolved_config.json'),physical_sha256=manifest['physical_sha256'],MPI_size=manifest['MPI_size'],cpu=manifest['cpu'],memory_budget=manifest.get('memory_budget'),verification_inventory=manifest.get('verification_inventory')))
        if (worker/'events.jsonl').exists():lifetimes.append(dict(role=run['role'],events=[r for r in map(json.loads,(worker/'events.jsonl').read_text().splitlines()) if 'saved' in r['event'] or 'released' in r['event']]))
    # Only newly produced V55 arrays; no historical whole-tree hashing.
    for p in scope.ARTIFACT.rglob('*.npz'):arrays.append(dict(path=str(p.relative_to(scope.ROOT)),bytes=p.stat().st_size,sha256=digest(p)))
    comparisons={p.stem:json.loads(p.read_text()) for p in (scope.ARTIFACT/'comparisons').glob('*.json')}
    independent={r:dict(rows=v.get('rows'),saved_checker=v.get('saved_checker'),pass_gate=v.get('pass_gate')) for r,v in states.items() if r=='Q0' or r.startswith('AUDIT_') or r=='VERIFY_COST'}
    write_json(out/'spatial_accuracy_checks_v55.json',dict(cases={r:v for r,v in states.items() if r in scope.SOLVES or r=='SETUP'},independent=independent,comparisons=comparisons,NN_training=0,NN20=False,target_qualified=False))
    write_json(out/'run_index_v55.json',dict(runs=scope.window.ledger()['runs'],pointers=pointers))
    write_json(out/'array_inventory_v55.json',dict(files=arrays))
    write_json(out/'physical_identity_bindings_v55.json',dict(runs=identities,parents=scope.plan_record()['parents'],canonical_material_path='input/materials/si_optical_constants_v1.json'))
    write_json(out/'object_lifetimes_v55.json',dict(routes=lifetimes))
    write_json(out/'resource_costs_v55.json',dict(costs=costs,charged_seconds=scope.window.charged_wall(),clock=scope.window.snapshot(),historical_loaded_known_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],historical_unknown='unknown; not zero',fresh_cold_N1='unknown; parent raw preparation and OS/JIT reuse are not free'))
    archive=scope.ARTIFACT/('raw_'+folder.name);archive.mkdir();items=[];seen=set()
    for root in [scope.window.TMP]+[Path(r['folder']) for r in scope.window.ledger()['runs']]+[scope.ARTIFACT]:
        for p in root.rglob('*'):
            if not p.is_file() or p in seen or p.is_relative_to(archive) or p.is_relative_to(out):continue
            seen.add(p)
            if p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.dat','.txt'):continue
            if p.is_relative_to(scope.window.TMP) and any(k in p.relative_to(scope.window.TMP).parts for k in ('edit','pycache','xdg','tmp','torch','uv','ruff')):continue
            h=digest(p);dest=archive/h
            if not dest.exists():shutil.copyfile(p,dest)
            items.append(dict(path=str(p.relative_to(scope.ROOT)),bytes=p.stat().st_size,sha256=h,archived=str(dest.relative_to(scope.ROOT))))
    write_json(out/'raw_archive_index_v55.json',dict(files=items))
    source_archive=scope.ARTIFACT/'source_archive';source_archive.mkdir(exist_ok=True);bindings=[]
    for sha,hashes in sources.items():
        for path,h in hashes.items():
            data=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',sha+':'+path],cwd=scope.ROOT)
            if hashlib.sha256(data).hexdigest()!=h:raise ValueError('V55 actual source bytes '+path)
            dest=source_archive/h
            if not dest.exists():dest.write_bytes(data)
            bindings.append(dict(source_sha=sha,path=path,sha256=h,archived=str(dest.relative_to(scope.ROOT))))
    write_json(out/'source_bindings_v55.json',dict(files=bindings,document_HEAD_is_not_run_source=True))
    print(json.dumps(dict(status='V55_COLLECTED',records=str(out))))


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:documents(scope=scope,review_name='review_report_v53.md',response_name='response_v55.md',outcome_name='spatial_resolution_audit_v55.md')
    elif sys.argv[1:]==['--partial']:partial_saved_checks()
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V55 collector arguments')
