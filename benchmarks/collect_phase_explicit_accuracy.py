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
import re
import sys
import time
from urllib.parse import unquote
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
    store(out,'physical_error_regions_v51',region_comparisons(stages))
    store(out,'next_scale_capacity_v51',scale_bridge(stages))
    store(out,'necessary_NN_cost_conditions_v51',cost_opportunity(costs))
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


def documents():
    """Check final new text/prefixes, preserving all immutable history bytes."""
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])
    task=ROOT/'docs/task042_neural_coarse_inverse';protected=[];targets=[]
    authority='97ca0d4e2d90f7479a757e66d43061b7d54bf3aa'
    for name in ('docs/task042_neural_coarse_inverse/README.md','docs/task042_neural_coarse_inverse/outcomes/summary.md',
                 'docs/task042_neural_coarse_inverse/outcomes/test_summary.md','docs/task042_neural_coarse_inverse/outcomes/changed_files.md',
                 'docs/development_progress.md','docs/development_model_registry.md'):
        old=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',authority+':'+name],cwd=ROOT)
        new=(ROOT/name).read_bytes()
        if not new.endswith(old):raise ValueError('old history suffix changed '+name)
        protected.append(dict(path=name,bytes=len(old),sha256=hashlib.sha256(old).hexdigest()))
        targets.append((ROOT/name,new[:-len(old)].decode()))
    targets += [(p,p.read_text()) for p in (task/'review_report_v49.md',task/'response_v51.md',task/'outcomes/phase_explicit_full3d_accuracy_v51.md')]
    checked=[]
    for p,body in targets:
        width=None;inside=False;tables=[];links=[]
        if '$$' in body or '\\[' in body:raise ValueError('unsupported new display math')
        for i,line in enumerate(body.splitlines(),1):
            if line.startswith('```'):inside=not inside;continue
            if inside:continue
            if line.startswith('|'):
                count=len(re.split(r'(?<!\\)\|',line))-2
                if width is None:tables.append(dict(line=i,columns=count));width=count
                if width!=count:raise ValueError('table width '+str(p)+':'+str(i))
            else:width=None
            for target in re.findall(r'\]\(([^)]+)\)',line):
                if target.startswith(('http','app:','#')):continue
                if not (p.parent/unquote(target.split('#')[0])).exists():raise ValueError('missing link '+target)
                links.append(target)
        if inside:raise ValueError('unclosed math/code fence '+str(p))
        checked.append(dict(path=str(p.relative_to(ROOT)),sha256=digest(p),checked_scope='new prefix or new full authority/result',tables=tables,links=links))
    changed=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','diff','--name-only',authority,'HEAD'],cwd=ROOT,text=True).splitlines()
    source=[n for n in changed if n.endswith('.py')]
    for n in source:compile((ROOT/n).read_bytes(),n,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_26_documentation_contract'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82',*source],
        ['git','-c','gc.auto=0','-c','maintenance.auto=false','diff','--check']]
    rows=[]
    for i,c in enumerate(commands):
        begin=time.monotonic();r=subprocess.run(c,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=c,returncode=r.returncode,seconds=time.monotonic()-begin))
        if r.returncode:raise RuntimeError('final relevant documentation/source test')
    write_json(folder/'documentation_checks.json',dict(status='PASSED_LOCAL',checked_actual_delivery_bytes=checked,
        old_history_suffixes=protected,commands=rows,compiled_changed_source=source,GitHub_visual='NOT_VERIFIED_CACHE_MISS',CI='NOT_RUN'))
    print(json.dumps(dict(status='PASSED_LOCAL',documentation_tests=15)),flush=True)
def region_comparisons(stages):
    from src.solvers.phase_explicit_accuracy_scope import plan_record
    box=np.asarray(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
    rows=[]
    for p in stages['VERIFY_COST']['pairs']:
        fine=stages['NOTCH_P5' if p['kind']=='p4_p5' else 'NOTCH_HPROBE']
        state=checked_arrays(fine['arrays']);centers=state['cell_centers'];tags=state['cell_tags']
        notch=np.all((centers>box[:,0])&(centers<box[:,1]),axis=1)
        masks={'air_excluding_notch':(tags==1)&~notch,'notch_air':(tags==1)&notch,'substrate':tags==2,'Si_block':tags==3}
        if not np.all(sum(m.astype(int) for m in masks.values())==1):raise ValueError('non-overlapping actual region inventory')
        arrays=checked_arrays(p['comparison']['arrays']);cell=arrays['per_cell_integrals'];components=arrays['per_cell_component_error_squared']
        if cell.shape!=(len(centers),6,3) or components.shape!=cell.shape or not np.allclose(components.sum(axis=2),cell[:,:,0],rtol=1e-12,atol=1e-26):raise ValueError('complete regional physical integrals')
        regions={}
        for name,mask in masks.items():
            sums=cell[mask].sum(axis=0)
            regions[name]={'cell_count':int(mask.sum()),'fields':{k:{'error_L2_squared':float(s[0]),'reference_L2_squared':float(s[1]),'fraction_of_global_error_squared':float(s[0]/max(cell[:,j,0].sum(),1e-30))} for j,(k,s) in enumerate(zip(p['comparison']['fields'],sums,strict=True))}}
        rows.append({'kind':p['kind'],'regions':regions,'component_error_squared':{k:components[:,j,:].sum(axis=0).tolist() for j,k in enumerate(p['comparison']['fields'])},'parent_sha256':p['comparison']['arrays']['sha256'],'squared_sums_equal_global':True,'background_cancels_in_error':True,'not_a_unique_root_cause_claim':True})
    return {'rows':rows,'new_FE_or_solver_calls':0}


def scale_bridge(stages):
    """Visible storage interval, not an invented sparse-factor RSS prediction."""
    rows=[]
    for scale in (1,2,4):
        nx,ny,nz,p=4*scale,4*scale,10*scale,5;cells=nx*ny*nz
        trace=p*nx*ny*(3*nz+2)+2*p*(p-1)*nx*ny*(3*nz+1);internal=3*p*(p-1)**2*cells
        native=p*(nx*(ny+1)*(nz+1)+(nx+1)*ny*(nz+1)+(nx+1)*(ny+1)*nz)+2*p*(p-1)*(nx*ny*(nz+1)+nx*(ny+1)*nz+(nx+1)*ny*nz)+internal
        aliases=4*(18*scale+1)*(6*scale+1);condensed=trace+aliases;face_rows=2*nx*ny*p*p
        rows.append({'scale_relative_to_NH':scale,'cells':cells,'degree':p,'native':native,'trace':trace,'internal':internal,'independent':trace+internal,'manual_alias_design_estimate':aliases,'condensed_rows':condensed,'one_complete_complex_vector_bytes':16*(trace+internal),
            'C_plus_D_payload_interval_bytes':{'ideal_tangential_trace_stream_pair':32*face_rows,'no_clipping_boundary_cell_support_stream_upper':32*min(native,nx*ny*3*p*(p+1)**2),'full_no_clipping_boundary_cell_inventory_upper':32*min(native,nx*ny*3*p*(p+1)**2)*aliases,'all_native_dense_counterexample_not_required':32*native*aliases},
            'local_cache_no_dedup_conservative_upper_bytes':13996800*cells,'one_dense_condensed_payload_upper_bytes':16*condensed**2,
            'factor_fill':'unknown','sparse_factor_workspace':'unknown','simultaneous_RSS_prediction':'unknown; not admitted without calibrated symbolic bound','iterations':'unknown','mode_truncation_accuracy':'unknown',
            'status':'measured topology / derived payload' if scale==1 else 'predicted_not_run; same absolute cell widths and p, physical geometry scaled'})
    if any(rows[0][k]!=stages['NOTCH_HPROBE']['capacity'][k] for k in ('cells','native','trace','internal','independent')):raise ValueError('scale formula must recover measured NH topology')
    return {'rows':rows,'actual_NH_peak_is_a_sampled_tree_measurement_not_the_visible_payload_bound':True,'scalar_formula_scope':'connected structured periodic xy hex, canonical independent moments; no target dofmap allocated','future_manual_alias_ranges_are_a_capacity_design_not_qualified_AUTO_or_mode_convergence':True}


def cost_opportunity(costs):
    rows=[]
    for c in costs:
        if c['role'] not in ('FLAT_P4','NOTCH_P4','NOTCH_P5','NOTCH_HPROBE') or c['classification']!='COMPLETED':continue
        t=c['cold_N1_dat_launch_lower_seconds'];e=c['exclusive_seconds']
        if not any('factor' in k for k in e):continue  # saved-return postprocessing is not a new cold solve
        tail=sum(v for k,v in e.items() if k in ('global_finite_factor_setup','h_sparse_symbolic_capacity','h_bounded_numeric_factor','solve_and_affine_internal_recovery','fixed_refinement'))
        prep=sum(v for k,v in e.items() if k in ('JIT_full_Ckappa_and_complete532_carrier','condensation_local_factors','physical_incident_RHS'))
        rows.append({'role':c['role'],'measured_launch_lower_seconds':t,'factor_solve_tail_seconds':tail,'free_tail_optimistic_fraction':tail/t,'prepare_optimistic_replaceable_seconds':prep,'N1_extra_cost_ceiling_if_all_this_preparation_free':prep-.2*t,'necessary_time_inequality':'fV-H >= 0.2*T_B','strongest_matching_accurate_traditional_total':'unknown; this direct anchor is not a fastest-baseline claim','simultaneous_peak20':'not demonstrated; shared/opaque allocator ownership unknown','NN_training':0})
    return {'rows':rows,'only_necessary_optimistic_bounds':True,'data_teacher_training_loading_inference_cleanup_and_independent_audit_all_belong_to_H':True,'no_finite_micro_cost_extrapolation_to_target_48h':True,'NN20':False}


def expected_modal_count(record, scope):
    from src.solvers.phase_notch_hp_modes import finite_mode_ranges
    count=record['case_spec']['complete_modes'] if getattr(scope,'NAMESPACE',None) in ('v54','v55') else 532
    finite_mode_ranges(count)
    return count


def modal_recalculation(*, scope=None, role_names=('FLAT_P4','NOTCH_P4','NOTCH_P5','NOTCH_HPROBE'),output_folder=None):
    """Independent saved-mode flux/coordinate audit; no FE or original metric call."""
    if scope is None:
        from src.solvers import phase_explicit_accuracy_scope as scope
    scope.window.guard_worker_parent();folder=Path(output_folder) if output_folder is not None else Path(os.environ['TASK042_V36_AUX_DIRECTORY']);rows=[]
    axes=scope.plan_record()['physical_descriptor']['geometry']['axes_nm'];area=(axes['x'][-1]-axes['x'][0])*(axes['y'][-1]-axes['y'][0]);k0=2*np.pi/.7
    incident=area*.5*np.sin(np.deg2rad(1));complex_pair=lambda x:complex(*x)
    for role in role_names:
        r=scope.stage(role);v=checked_arrays(r['arrays']);path=Path(r['output']['fields']['path']).with_name('port_power.json');p=json.loads(path.read_text())
        expected=expected_modal_count(r,scope)
        if getattr(scope,'NAMESPACE',None) in ('v54','v55'):
            from src.solvers.phase_notch_hp_modes import keyed_modes
            keyed_modes(p,expected)
        maximum=0.;power_sum={'top':0.,'bottom':0.};normalization_defect=abs(p['incident_power_code_units']-incident)
        for o in p['orders']:
            a=complex_pair(o['alpha']);g=complex_pair(o['gamma']);beta=complex_pair(o['beta']);n=complex_pair(o['refractive_index']);sign=o['vertical_sign'];i=o['auxiliary_index'];kt=np.sqrt(abs(a)**2+abs(g)**2)
            s=np.asarray([-g/kt,a/kt,0],complex);k=np.asarray([a,g,sign*beta]);e=s if o['polarization']=='s' else np.cross(k/(k0*n),s)
            if o['polarization']=='p':e=e/np.linalg.norm(e)
            total=complex_pair(o['auxiliary_amplitude_total_projection']);inc=complex_pair(o['incident_projection']);out=total-inc if o['side']=='top' else total
            phase=complex_pair(o['boundary_phase']);boundary=out*phase;h=np.cross(k,e)/k0
            unit=area*max(float(sign*.5*np.real(np.cross(e,np.conj(h)))[2]),0.)
            power=unit*abs(boundary)**2;ratio=power/incident;power_sum[o['side']]+=ratio
            coordinate=max(abs(total-v['port'][i])/max(abs(total),abs(v['port'][i]),1e-30),abs(out-complex_pair(o['outgoing_amplitude']))/max(abs(out),1e-30),abs(boundary-complex_pair(o['outgoing_amplitude_at_boundary']))/max(abs(boundary),1e-30))
            maximum=max(maximum,coordinate,abs(power-o['modal_power_code_units'])/incident,abs(ratio-o['power_ratio']))
        totals=max(abs(power_sum['top']-p['R_total']),abs(power_sum['bottom']-p['T_total']),abs(1-sum(power_sum.values())-p['A_balance']))
        energy=abs(1-sum(power_sum.values())-r['output']['volume_metrics']['A_volume_total'])
        good=maximum<=1e-10 and totals<=1e-10 and normalization_defect<=1e-12 and energy<=1e-5
        rows.append(dict(role=role,parent_array_sha256=r['arrays']['sha256'],mode_json_sha256=digest(path),count=len(p['orders']),expected_mode_count=expected,max_operation_scaled_coordinate_and_power_defect=maximum,totals_defect=totals,incident_power_defect=normalization_defect,energy_from_all_actual_modes_and_volume=energy,recomputed_R=power_sum['top'],recomputed_T=power_sum['bottom'],pass_gate=good))
    if not all(x['pass_gate'] and x['count']==x['expected_mode_count'] for x in rows):raise ValueError('independent complete modal power/coordinate audit')
    if getattr(scope,'NAMESPACE',None) not in ('v54','v55'):
        for row in rows:row['energy_from_all532_and_volume']=row.pop('energy_from_all_actual_modes_and_volume')
    result=dict(rows=rows,new_FE_calls=0,original_power_function_calls=0,complete_inventory_checked=True)
    write_json(folder/'modal_power_recalculation.json',result)
    print(json.dumps(dict(status='PASSED_SAVED_COMPLETE_MODE_POWER' if getattr(scope,'NAMESPACE',None) in ('v54','v55') else 'PASSED_SAVED_ALL532_POWER',rows=len(rows))))
    return result


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:documents()
    elif sys.argv[1:]==['--modal']:modal_recalculation()
    elif not sys.argv[1:]:collect()
    else:raise ValueError('unknown collector argument')
