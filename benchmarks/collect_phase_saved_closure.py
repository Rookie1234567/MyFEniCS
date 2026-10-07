"""V56 incremental saved-array checker, source/raw archive and exact costs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import phase_saved_closure_scope as scope
from src.solvers.scattering_anchor import relative
from src.solvers.scattering_anchor_checks import checked_arrays
from benchmarks.collect_phase_notch_hp import measured_timeline,sampling_receipt,documents


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def vector_check(receipt):
    v=checked_arrays(receipt)
    if any(not np.isfinite(x).all() for x in v.values()):raise ValueError('independent original vectors must be finite')
    b=v['rhs'];true=b-v['volume_action']-v['native_boundary_action']
    top=b-v['volume_action']-v['coupling_action'];pr=v['projected']-v['H']*v['port']
    defects=dict(saved_true=relative(true-v['residual'],np.maximum(np.abs(b),np.abs(b-v['residual']))),
        saved_top=relative(top-v['augmented_top'],np.maximum(np.abs(b),np.abs(b-v['residual']))),
        curl_mass=relative(v['volume_curl']+v['volume_mass']-v['volume_action'],np.maximum(np.abs(v['volume_curl']),np.abs(v['volume_mass']))),
        split=relative(v['volume_inside']+v['volume_trace']-v['volume_action'],np.maximum(np.abs(v['volume_inside']),np.abs(v['volume_trace']))),
        port_consistency=relative(pr-v['port_residual'],v['projected']))
    norms=dict(true=relative(true,b),native=relative(true,b),augmented=relative(top,b),port=relative(pr,v['projected']))
    ip=v['internal_rows'].reshape(len(v['internal_operation_scale']),-1)
    residual=b-v['volume_inside']-v['volume_trace']-v['coupling_action']
    numerators=np.linalg.norm(residual[ip],axis=1)
    scale=sum(np.linalg.norm(x[ip],axis=1) for x in (b,v['volume_inside'],v['volume_trace'],v['coupling_action']))
    inner=float(np.max(numerators/np.maximum(scale,1e-30)))
    if not np.allclose(scale,v['internal_operation_scale'],rtol=1e-13,atol=1e-30) or not np.array_equal(residual[v['internal_rows']],v['internal_residual']):raise ValueError('independent internal operation inventory')
    slave_zero=bool(np.all(v['u_storage'][v['slaves']]==0))
    return dict(norms=norms,identity_defects=defects,internal_operation_scaled_max=inner,slave_zero=slave_zero,
        direct_internal_target_pass=max(norms.values())<=1e-10,
        pass_gate=slave_zero and all(np.isfinite(x) and x<=1e-6 for x in norms.values()) and max(defects.values())<=1e-10 and inner<=1e-10)


def pair_checks(states,pairs):
    # The old V51 integral_pair has a fixed 532 inventory and old selected
    # array names. Reuse the qualified full inventory/regions checker instead.
    from benchmarks.collect_phase_notch_hp import saved_checks
    if any(p['modes']['mode_count']!=828 for p in pairs.values()):raise ValueError('V56 complete 828 comparison inventory')
    _,regions,gates=saved_checks(states,pairs,scope=scope)
    return dict(regions=regions,gates=gates)


def check_saved_stage(s,folder,journal):
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    rows={}
    with journal.measured('independent_saved_absorption_field_original_vector_recalculation'):
        for role,key in (('R7','R7_original_regression'),('H7','H7_independent')):
            rows[role]=vector_check(s[key]['arrays'])
        pairs=pair_checks(dict(H7=s['H7'],R7=scope.parent('R7'),R6=scope.parent('R6')),s['comparisons'])
        m=s['H7']['output']['volume_metrics'];a=checked_arrays(m['arrays'])['rows'];pinc=m['incident_power_code_units'];k0=2*np.pi/.7
        av=0.
        for region in m['regions'].values():
            selected=a[:,0]==region['tag'];actual=k0*.5*region['Im_epsilon_r']*a[selected,1].sum()/pinc
            if not np.isclose(actual,region['A_volume'],rtol=1e-12,atol=1e-15) or selected.sum()!=region['cell_count']:raise ValueError('saved absorption material inventory/formula')
            av+=actual
        if abs(av-m['A_volume_total'])>1e-13:raise ValueError('saved full absorption sum')
        field=checked_arrays(s['H7']['output']['fixed_240'])
        if field['points'].shape!=(240,3) or any(field[n+'_'+k].shape!=(240,3) for n in ('E','H','curl') for k in ('total','scattered')):raise ValueError('full fixed point E/H/curl inventory')
    shim=SimpleNamespace(NAMESPACE='v56',window=scope.window,plan_record=scope.plan_record,stage=lambda role:s['H7'] if role=='H7' else scope.parent(role))
    with journal.measured('independent_all828_complex_coordinate_and_power_recalculation'):
        modal=modal_recalculation(scope=shim,role_names=('H7',),output_folder=folder)
    result=dict(original_vectors=rows,pairs=pairs,H7_A_volume_recalculated=float(av),modal=modal,
        new_FE_calls=0,new_factor_count=0,new_complete_solves=0,
        equation_consumer_pass=all(r['pass_gate'] for r in rows.values()))
    write_json(folder/'independent_saved_checker.json',result);return result


def check_transverse_stage(t,folder,journal):
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    folder.mkdir(exist_ok=True)
    with journal.measured('independent_saved_T6_vector_field_and_power_recalculation'):
        original=vector_check(t['independent']['arrays'])
        pairs=pair_checks(dict(T6=t,R6=scope.parent('R6'),R7=scope.parent('R7')),t['comparisons'])
        points=checked_arrays(t['output']['fixed_240'])
        if points['points'].shape!=(240,3) or any(points[n+'_'+k].shape!=(240,3) for n in ('E','H','curl') for k in ('total','scattered')):raise ValueError('T6 fixed 240 inventory')
        shim=SimpleNamespace(NAMESPACE='v56',window=scope.window,plan_record=scope.plan_record,stage=lambda _:t)
        modal=modal_recalculation(scope=shim,role_names=('T6',),output_folder=folder)
    result=dict(original=original,pairs=pairs,modal=modal,new_FE_calls=0,new_factor_count=0,new_complete_solves=0)
    write_json(folder/'independent_saved_checker.json',result);return result


def compact_state(r):
    keys=('status','role','case_spec','degree','source_sha','solve_source_sha','arrays','returned_arrays','original_audit',
        'direct_target_pass','equation_pass','recovery','capacity','raw_tensor_manifest_receipt','fixed_refinements')
    result={k:r[k] for k in keys if k in r}
    result['output']={k:r['output'][k] for k in ('fields','fixed_240','port_metrics','volume_metrics') if k in r.get('output',{})}
    return result


def compact_science(stages):
    result={}
    if 'S' in stages:
        s=stages['S'];result['S']={k:s[k] for k in ('status','role','source_sha','comparisons','H7_independent','R7_original_regression',
            'complete_saved_closure','field_accuracy_pass','cross_p_diagnostic_pass','new_factor_count','new_complete_solves','new_raw_tensor_classes')}
        result['S'].update(H7=compact_state(s['H7']),R7_absorption={k:v for k,v in s['R7_absorption'].items() if k!='volume_result'},
            H7_few_point=s['H7_few_point'],parent_pointer=json.loads((scope.ARTIFACT/'S.json').read_text()))
    if 'T6' in stages:
        t=stages['T6'];result['T6']=compact_state(t)
        result['T6'].update({k:t[k] for k in ('comparisons','independent','raw_tensor_checkpoint','reason') if k in t})
    if 'VERIFY_COST' in stages:result['VERIFY_COST']=stages['VERIFY_COST']
    return dict(**result,NN_training=0,target_qualified=False,history_is_by_parent_pointer=True)


def collect():
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    runs=scope.window.ledger()['runs'];costs=[];bindings=[];sources={}
    for run in runs:
        directory=Path(run['folder']);manifest=json.loads((directory/'run_manifest.json').read_text())
        path=directory/('run_summary.json' if (directory/'run_summary.json').exists() else 'summary.json');summary=json.loads(path.read_text())
        worker=scope.ARTIFACT/directory.name
        timing=measured_timeline(worker/'events.jsonl') if (worker/'events.jsonl').exists() else {}
        costs.append(dict(role=run['role'],folder=run['folder'],source_sha=run['source_sha'],classification=run['classification'],
            supervised_seconds=run['elapsed_seconds'],launch_seconds=summary['launch_wall_seconds'],
            peak_bytes=run['peak_bytes'],swap_bytes=run['swap_bytes'],sampling=sampling_receipt(directory/'supervision/resources.jsonl'),
            disjoint_timing=timing,shared_workstation=True,cost_scope='nested stages excluded from double addition; unique dat wall authoritative'))
        sources[run['source_sha']]=manifest['implementation_hashes']
        if (directory/'resolved_config.json').exists():bindings.append(dict(role=run['role'],source_sha=run['source_sha'],input_sha256=manifest['input_sha256'],
            resolved_sha256=digest(directory/'resolved_config.json'),physical_sha256=manifest['physical_sha256'],mode='complete828',memory_budget=manifest['memory_budget']))
    stages={role:scope.stage(role) for role in scope.STAGES if (scope.ARTIFACT/(role+'.json')).exists()}
    write_json(out/'run_index_v56.json',dict(runs=runs,pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}))
    write_json(out/'scientific_checks_v56.json',compact_science(stages))
    write_json(out/'physical_identity_bindings_v56.json',dict(runs=bindings,parents=scope.plan_record()['parents'],H7=scope.plan_record()['saved_H7']))
    write_json(out/'resource_costs_v56.json',dict(costs=costs,charged_seconds=scope.window.charged_wall(),clock=scope.window.snapshot(),
        inherited_known_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],unknown_costs='unknown; not zero',fresh_N1='parent necessary prepare plus full consumer; not equal cached S increment'))
    array_inventory=[dict(path=str(p.relative_to(scope.ROOT)),bytes=p.stat().st_size,sha256=digest(p)) for p in scope.ARTIFACT.rglob('*.npz')]
    write_json(out/'array_inventory_v56.json',dict(files=array_inventory))
    archive=scope.ARTIFACT/('raw_'+folder.name);archive.mkdir();seen=set();raw=[]
    for root in [scope.window.TMP]+[Path(r['folder']) for r in runs]+[scope.ARTIFACT]:
        for p in root.rglob('*'):
            if not p.is_file() or p in seen or p.is_relative_to(archive) or p.is_relative_to(out) or p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.dat','.txt'):continue
            seen.add(p)
            if p.is_relative_to(scope.window.TMP) and any(n in p.relative_to(scope.window.TMP).parts for n in ('edit','pycache','xdg','tmp','torch','uv','ruff')):continue
            h=digest(p);dest=archive/h
            if not dest.exists():shutil.copyfile(p,dest)
            raw.append(dict(path=str(p.relative_to(scope.ROOT)),bytes=p.stat().st_size,sha256=h,archived=str(dest.relative_to(scope.ROOT))))
    write_json(out/'raw_archive_index_v56.json',dict(files=raw))
    source_archive=scope.ARTIFACT/'source_archive';source_archive.mkdir(exist_ok=True);rows=[]
    for sha,files in sources.items():
        for name,h in files.items():
            data=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',sha+':'+name],cwd=scope.ROOT)
            if hashlib.sha256(data).hexdigest()!=h:raise ValueError('real source snapshot mismatch '+name)
            dest=source_archive/h
            if not dest.exists():dest.write_bytes(data)
            rows.append(dict(source_sha=sha,path=name,sha256=h,archived=str(dest.relative_to(scope.ROOT))))
    write_json(out/'source_bindings_v56.json',dict(files=rows,document_HEAD_is_not_run_source=True))
    print(json.dumps(dict(status='V56_COLLECTED',records=str(out))))


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:documents(scope=scope,review_name='review_report_v54.md',response_name='response_v56.md',outcome_name='saved_field_closure_target_bridge_v56.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V56 collector arguments')
