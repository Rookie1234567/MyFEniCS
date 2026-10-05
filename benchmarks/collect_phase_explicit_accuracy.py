"""V51 incremental evidence only: saved physical checks, disjoint cost/archive.

Does not solve, reassemble FE, or read/rehash old campaigns. Reuses generic
archive/hash/timing helpers; the new payload is the phase accuracy inventory.
"""
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers.phase_explicit_accuracy_scope import ROOT,ARTIFACT,STAGES,SOLVES,stage,window
from src.solvers.scattering_anchor_reporting import disjoint_timings
from benchmarks.collect_scattering_anchor import digest
from benchmarks.collect_scattering_accuracy import store
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.scattering_anchor import relative


def equations(a,r):
    av=[a[k] for k in ('true','native','augmented','port')]
    rv=[r[k] for k in ('operation_scaled_interior','max_cell_operation_scaled','master_storage_max_abs','split_action_identity_operation_scale')]
    return bool(all(np.isfinite(x) and 0<=x<=1e-6 for x in av) and np.isfinite(a['identity']) and 0<=a['identity']<=1e-10 and a['slave_zero'] and all(np.isfinite(x) and 0<=x<=1e-10 for x in rv) and r['slave_storage_zero'])


def integral_pair(p):
    if set(p['fields'])!=set(p['selected']) or set(p['fields'])!={'E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered'}:
        raise ValueError('complete phase physical pair inventory')
    sums={}
    for q,key in ((31,'arrays'),(23,'q23_arrays')):
        a=checked_arrays(p[key])['per_cell_integrals']
        totals=a.sum(axis=0)
        sums[q]=totals
        if a.shape[1:]!=(6,3) or not np.isfinite(a).all() or np.any(a<0):raise ValueError('raw physical squared integrals')
        if q==31:
            for name,t in zip(p['fields'],totals,strict=True):
                if not np.isclose(p['fields'][name]['relative'],np.sqrt(t[0]/t[1]),rtol=1e-12,atol=1e-15):
                    raise ValueError('reported physical integral norm differs from arrays')
    values=[r['relative'] for r in p['fields'].values()]+list(p['selected'].values())
    qdef=float(np.max(np.abs(sums[23][:,:2]-sums[31][:,:2])/np.maximum(sums[31][:,1,None],1e-24)))
    raw=checked_arrays(p['arrays'])
    for name,value in p['selected'].items():
        if 'selected_'+name+'_coarse' in raw:
            real=relative(raw['selected_'+name+'_coarse']-raw['selected_'+name+'_fine'],raw['selected_'+name+'_fine'])
            if not np.isclose(real,value,rtol=1e-10,atol=1e-15):raise ValueError('selected physical field norm differs from raw arrays')
    return bool(all(np.isfinite(x) and 0<=x<=1e-4 for x in values) and qdef<=1e-10 and p['modes']['mode_count']==532 and p['modes']['outgoing_amplitude_at_boundary_relative']<=1e-4 and p['modes']['mode_power_max_absolute']<=1e-6 and max(p['power_differences'].values())<=1e-5 and max(p['energies'])<=1e-5)


def vector_audit(raw,state,boundary,degree):
    """Recompute gates from saved independent actions, not their status fields."""
    if any(not np.isfinite(v).all() for v in list(raw.values())+list(boundary.values())):raise ValueError('saved audit arrays must be finite')
    b=raw['rhs'];u=raw['u_storage'];alpha=raw['port'];projection=[];Cpr=np.zeros_like(b);Ca=np.zeros_like(b)
    if len(boundary['offsets'])!=len(alpha)+1 or np.any(boundary['H']==0):raise ValueError('saved complete port inventory')
    for j,(l,h) in enumerate(zip(boundary['offsets'][:-1],boundary['offsets'][1:])):
        rows=boundary['rows'][l:h];C=boundary['C'][l:h];D=boundary['D'][l:h]
        projection.append(np.dot(D,u[rows]));np.add.at(Ca,rows,C*alpha[j]);np.add.at(Cpr,rows,C*raw['port_residual'][j]/boundary['H'][j])
    pr=np.asarray(projection)-boundary['H']*alpha
    defects=dict(port_functional=relative(np.asarray(projection)-raw['projected'],raw['projected']),
        coupling=relative(Ca-raw['coupling_action'],raw['coupling_action']),
        augmented_identity=relative(b-raw['volume_action']-raw['coupling_action']-raw['augmented_residual'],b),
        port_identity=relative(pr-raw['port_residual'],raw['projected']))
    rebuilt=raw['augmented_residual']-Cpr
    a=dict(true=relative(raw['residual'],b),native=relative(raw['residual'],b),augmented=relative(raw['augmented_residual'],b),
        port=relative(raw['port_residual'],raw['projected']),identity=relative(raw['residual']-rebuilt,np.maximum(np.abs(b),np.abs(b-raw['residual']))),slave_zero=bool(np.all(u[state['slaves']]==0)))
    ip=raw['interior_rows'].reshape(-1,3*degree*(degree-1)**2)
    vi,vt=raw['interior_only_volume_action'],raw['trace_only_volume_action'];residual=b-vi-vt-raw['coupling_action']
    numerator=np.linalg.norm(residual[ip],axis=1);denom=sum(np.linalg.norm(x[ip],axis=1) for x in (b,vi,vt,raw['coupling_action']))
    independent=np.setdiff1d(np.arange(len(u)),state['slaves'])
    r=dict(operation_scaled_interior=float(np.linalg.norm(numerator)/max(np.linalg.norm(denom),1e-30)),max_cell_operation_scaled=float(np.max(numerator/np.maximum(denom,1e-30))),
        master_storage_max_abs=float(np.max(np.abs(raw['recovered_native_full'][independent]-u[independent]),initial=0)),slave_storage_zero=bool(np.all(u[state['slaves']]==0)),
        split_action_identity_operation_scale=relative(vi+vt-raw['volume_action'],np.maximum(np.abs(vi),np.abs(vt))))
    return dict(audit=a,recovery=r,structural_defects=defects,pass_gate=equations(a,r) and all(np.isfinite(x) and 0<=x<=1e-10 for x in defects.values()))


def physics_check(stages):
    checks=[];boundary_cache={}
    for row in stages['VERIFY_COST']['rows']:
        original=stages[row['role']];v=checked_arrays(original['arrays'])
        if not np.array_equal(v['u_storage'][v['slaves']],np.zeros(len(v['slaves']),complex)):
            raise ValueError('full canonical slave storage')
        field=checked_arrays(original['output']['fields'])
        if field['envelope_native_full'].ndim!=1 or not np.isfinite(field['envelope_native_full']).all():
            raise ValueError('full physical field authority')
        power=json.loads(Path(original['output']['fields']['path']).with_name('port_power.json').read_text())
        keys=[(o['side'],o['m'],o['n'],o['polarization']) for o in power['orders']]
        expected={(s,m,n,p) for s in ('top','bottom') for m in range(-9,10) for n in range(-3,4) for p in ('s','p')}
        if len(keys)!=532 or set(keys)!=expected:raise ValueError('complete actual532 modes')
        receipt=original['boundary']['arrays'][1]
        if receipt['sha256'] not in boundary_cache:boundary_cache[receipt['sha256']]=checked_arrays(receipt)
        checked=vector_audit(checked_arrays(row['arrays']),v,boundary_cache[receipt['sha256']],original['degree'])
        eq=checked['pass_gate']
        checks.append(dict(role=row['role'],equation_pass=eq,audit=row['audit'],recovery=row['recovery'],independent_saved_vector_recalculation=checked,mode_count=len(keys),power=row['power'],volume=row['volume'],parent_array_sha256=original['arrays']['sha256']))
    pairs=[dict(kind=x['kind'],pass_gate=integral_pair(x['comparison']),comparison=x['comparison']) for x in stages['VERIFY_COST']['pairs']]
    flats=[r for r in stages.values() if r.get('case')=='FLAT' and r.get('analytic')]
    flat_pass=False
    for r in flats:
        a=r['analytic'];f=a['complete_physics'];error=[z['relative'] for z in a['fields'].values()]+list(f['selected_fields_relative'].values())
        good=all(np.isfinite(x) and x<=1e-4 for x in error) and a['quadrature_operation_scaled']<=1e-10 and f['absolute_power_differences']['maximum_single_mode_power']<=1e-6 and max(f['absolute_power_differences'][k] for k in ('R_total','T_total','A_balance','A_volume','energy'))<=1e-5 and r['analytic_weak']['relative']<=1e-10
        flat_pass|=bool(good and next(x['equation_pass'] for x in checks if x['role']==r['role']))
    anchor=flat_pass and any(p['pass_gate'] for p in pairs)
    return dict(rows=checks,pairs=pairs,flat_pass=flat_pass,finite_anchor=anchor,
        verdict='ACCURACY_ANCHOR_ON_FIXED_532' if anchor else 'FLAT_PASS_NOTCH_NOT_QUALIFIED' if flat_pass else 'NO_ACCURACY_ANCHOR',
        target_qualified=False,continuum_qualified=False,mode_truncation_qualified=False,NN20=False,NN_training=0)


def collect():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    pointers={p.stem:json.loads(p.read_text()) for p in ARTIFACT.glob('*.json')};stages={k:stage(k) for k in pointers if k in STAGES}
    checks=physics_check(stages);store(out,'phase_accuracy_checks_v51',checks)
    store(out,'stage_index_v51',dict(rows=[dict(role=k,status=stages[k]['status'],source=stages[k]['source_sha'],solve_source=stages[k].get('solve_source_sha',stages[k]['source_sha']),pointer=pointers[k]) if k in stages else dict(role=k,status='not_run',reason='FLAT_P5/ORDINARY_CONTROL: F4 passed; conditional stages otherwise not admitted') for k in STAGES],window=window.snapshot(),NN_training=0))
    resources=[];costs=[];identities=[];lifetimes=[];versions={};maxgap=0;peak=swap=0
    for r in window.ledger()['runs']:
        rd=Path(r['folder']);s=rd/('run_summary.json' if (rd/'run_summary.json').exists() else 'summary.json');summary=json.loads(s.read_text())
        logs=rd/'supervision/resources.jsonl';samples=[json.loads(x) for x in logs.read_text().splitlines()] if logs.exists() else []
        gap=max((b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(samples,samples[1:])),default=0);maxgap=max(maxgap,gap);peak=max(peak,r['peak_bytes']);swap=max(swap,r['swap_bytes'])
        resources.append({k:r[k] for k in ('role','source_sha','folder','classification','elapsed_seconds','peak_bytes','swap_bytes','descendants_cleared')}|dict(actual_max_sample_gap_seconds=gap,sample_count=len(samples),launch_wall_seconds=summary.get('launch_wall_seconds')))
        manifest=json.loads((rd/'run_manifest.json').read_text());versions.setdefault(r['source_sha'],manifest['implementation_hashes'])
        ad=ARTIFACT/rd.name
        if (ad/'events.jsonl').exists():
            events=[json.loads(x) for x in (ad/'events.jsonl').read_text().splitlines()];time=disjoint_timings(events)
            costs.append(dict(role=r['role'],source=r['source_sha'],folder=str(rd),classification=r['classification'],worker_or_supervised_seconds=r['elapsed_seconds'],cold_N1_dat_launch_lower_seconds=summary['launch_wall_seconds'],**time,failed_and_repaired_work_not_free=True,cache='same task namespace; OS/JIT not cleared; numeric factors are cold per case',unknown_preactivation_and_external_IO_not_zero=True))
            lifetimes.append(dict(role=r['role'],folder=str(ad),events=events,visible_numpy_owners_are_lower_payload_not_RSS=True))
        if (rd/'resolved_config.json').exists():
            resolved=json.loads((rd/'resolved_config.json').read_text())
            identities.append(dict(folder=str(rd),source=r['source_sha'],physical_sha256=manifest['physical_sha256'],input_sha256=manifest['input_sha256'],resolved_sha256=digest(rd/'resolved_config.json'),physical={k:resolved[k] for k in ('geometry','materials','incidence','discretization','boundary')},postprocessing_resume=manifest.get('postprocessing_resume')))
    store(out,'resource_costs_snapshot_v51',dict(runs=resources,known_prior_lower_seconds=96250.16526014329,charged_before_collector_settlement_seconds=window.charged_wall(),sampled_tree_peak_bytes=peak,own_swap_peak_bytes=swap,actual_max_sample_gap_seconds=maxgap,shared_workstation=True,sampled_not_cgroup=True,historical_unknowns_retained=True,current_collector_and_final_checks_not_yet_settled=True))
    store(out,'cold_n1_costs_v51',dict(routes=costs,postprocessing_source_and_original_failed_solve_charged_separately=True,setup_and_unique_VERIFY_separately_charged=True,performance='INCONCLUSIVE for no-contention speed; physical accuracy is independently evaluated'))
    store(out,'object_lifetimes_v51',dict(routes=lifetimes));store(out,'physical_identity_bindings_v51',dict(runs=identities,material_table_id='SI_OPTICAL_CONSTANTS_USER_20260929_V1',canonical_material_path='input/materials/si_optical_constants_v1.json'))
    store(out,'run_index_v51',dict(runs=[{k:r[k] for k in ('role','folder','source_sha','classification')} for r in window.ledger()['runs']],pointers=pointers,original_failed_returns_preserved=True))
    store(out,'repair_journal_v51',dict(rows=[json.loads(x) for x in (window.TMP/'repair_journal.jsonl').read_text().splitlines()],ordinary_bug_is_not_numerical_stagnation=True))
    source_archive=ARTIFACT/'source_archive';source_archive.mkdir(exist_ok=True);sources=[]
    for sha,hashes in versions.items():
        for path,h in hashes.items():
            data=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',sha+':'+path],cwd=ROOT)
            if hashlib.sha256(data).hexdigest()!=h:raise ValueError('formal source was not clean/bound '+path)
            dest=source_archive/h
            if not dest.exists():dest.write_bytes(data)
            sources.append(dict(source_sha=sha,path=path,sha256=h,archived=str(dest.relative_to(ROOT))))
    store(out,'source_bindings_v51',dict(files=sources,solve_and_documentation_HEAD_distinct=True))
    arrays=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=digest(p)) for p in ARTIFACT.rglob('*.npz')]
    store(out,'array_inventory_v51',dict(files=arrays,complete_member_shapes_hashes_in_parent_receipts=True))
    archive=ARTIFACT/('raw_'+folder.name);archive.mkdir();items=[];seen=set()
    for root in [window.TMP]+[Path(r['folder']) for r in window.ledger()['runs']]+[ARTIFACT]:
        for p in root.rglob('*'):
            if not p.is_file() or p.is_relative_to(archive) or p.is_relative_to(out) or p in seen:continue
            seen.add(p)
            if p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.txt','.dat') or p.stat().st_size>8*2**20:continue
            if p.is_relative_to(window.TMP) and any(s in p.relative_to(window.TMP).parts for s in ('edit','pycache','xdg','tmp','torch','uv','ruff')):continue
            h=digest(p);target=archive/h
            if not target.exists():shutil.copyfile(p,target)
            items.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=h,archived=str(target.relative_to(ROOT))))
    store(out,'raw_archive_index_v51',dict(files=items,scope='V51 incremental only; old campaigns not replayed or rehashed',scientific_arrays_JIT_referenced_not_copied=True))
    print(json.dumps(dict(status='V51_COLLECTED',records=str(out),verdict=checks['verdict'])))


if __name__=='__main__':collect()
