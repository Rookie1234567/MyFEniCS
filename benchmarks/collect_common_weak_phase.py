"""V57 independent saved-array verdicts and compact incremental accounting."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import common_weak_phase_scope as scope
from src.solvers.scattering_anchor import relative,array_hash
from src.solvers.scattering_anchor_checks import checked_arrays


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def reproduction_check(pair):
    thresholds=dict(fields=1e-6,selected=1e-6,channels=1e-6,power=1e-8,mode_power=1e-9,q=1e-10)
    measures=dict(fields=max(x['relative'] for x in pair['fields'].values()),
        selected=max(pair['selected'].values()),channels=pair['modes']['outgoing_amplitude_at_boundary_relative'],
        power=max(pair['power_differences'].values()),mode_power=pair['modes']['mode_power_max_absolute'],
        q=pair['quadrature_operation_scaled'])
    return dict(measured=measures,limits=thresholds,pass_gate=all(np.isfinite(v) and v<=thresholds[k] for k,v in measures.items()))


def weak_check(r,*,frozen_scales=None):
    out=[]
    for row in r['rows']:
        v=checked_arrays(row['arrays']);terms=v['terms'];res=terms[6]-terms[:6].sum(axis=0)
        if terms.shape!=(7,24) or v['permode_DtN'].shape!=(828,24):raise ValueError('continuous full test/mode inventory')
        if relative(res-v['residual'],np.maximum(np.abs(terms).sum(axis=0),1e-300))>1e-12:raise ValueError('continuous complex residual sum')
        if relative(v['region_terms'].sum(axis=0)-terms[:5],terms[:5])>1e-12:raise ValueError('continuous material contribution sum')
        if relative(v['permode_DtN'].sum(axis=0)-terms[5],terms[5])>1e-12:raise ValueError('continuous 828 boundary sum')
        # The independently regrouped sum is checked above against the original
        # operation scale. Stored ratio must match its own saved residual; a
        # tiny cancellation result is not a floating-point operation scale.
        if not np.allclose(v['fixed_scaled'],np.abs(v['residual'])/v['fixed_scale'],rtol=1e-13,atol=1e-300):raise ValueError('common fixed scale')
        if not np.all(np.isfinite(v['fixed_scale'])) or np.any(v['fixed_scale']<=0):raise ValueError('nonpositive continuous scale')
        if frozen_scales is not None and row['q'] in frozen_scales and not np.allclose(v['fixed_scale'],frozen_scales[row['q']],rtol=1e-13,atol=0):raise ValueError('four candidates must share the frozen background scale')
        out.append(dict(q=row['q'],maximum_fixed_scaled=float(np.max(np.abs(res)/v['fixed_scale'])),
            maximum_absolute=float(np.max(np.abs(res))),maximum_operation_scaled=float(np.max(np.abs(res)/v['operation_scale'])),
            maximum_regrouping_operation_scaled=float(np.max(np.abs(res-v['residual'])/v['operation_scale'])),arrays_sha256=row['arrays']['sha256']))
    return out


def diagnostic_check(r):
    if r.get('status')!='COMPLETED' or set(r['states'])!={'R6','T6','R7','H7'} or len(r['design']['functions'])!=24:raise ValueError('complete frozen continuous study inventory')
    control=r['analytic_control'];scales={};control_rows=weak_check(control)
    for row in control['rows']:
        v=checked_arrays(row['arrays']);scales[row['q']]=v['fixed_scale']
        perturb=v['residual']-v['perturbation_terms'].sum(axis=0)
        if not np.allclose(perturb,v['perturbation_residual'],rtol=1e-13,atol=1e-25):raise ValueError('analytic nonzero perturbation balance')
        if np.max(np.abs(v['residual'])/v['fixed_scale'])>1e-10:raise ValueError('analytic FLAT formula control')
        if np.max(np.abs(v['perturbation_terms'].sum(axis=0)))<=1e-10*np.max(v['fixed_scale']):raise ValueError('zero-return diagnostic not detected')
    return dict(control=control_rows,states={key:weak_check(v,frozen_scales=scales) for key,v in r['states'].items()},
        quadratures={key:weak_quadrature_rows(v) for key,v in {'analytic_control':control,**r['states']}.items()},
        full_field_accuracy_certificate=False)


def local_recovery_check(matrix,v):
    i=v['internal_rows'];t=v['trace_rows'];co=v['actual_coefficients']
    inside=matrix[np.ix_(i,i)]@v['recovered_internal'];trace=matrix[np.ix_(i,t)]@co[t];rhs=v['internal_rhs']
    residual=inside+trace-rhs
    scale=sum(np.linalg.norm(x) for x in (inside,trace,rhs))
    operation=float(np.linalg.norm(residual)/max(scale,1e-300))
    defect=relative(v['recovered_internal']-co[i],co[i])
    return dict(relative=defect,residual_operation_scaled=operation,residual_absolute=float(np.linalg.norm(residual)),
        operation_scale=float(scale),rhs_norm=float(np.linalg.norm(rhs)),pass_gate=defect<=1e-10 and operation<=1e-10)


def tensor_check(k):
    out={}
    for degree in k['degrees']:
        if degree['status']!='COMPLETED':out[str(degree['degree'])]=dict(status=degree['status']);continue
        rows=[]
        for row in degree['rows']:
            new=checked_arrays(row['arrays']);old=checked_arrays(row['raw_parent'])['tensor'];delta=new['new_tensor']-old
            values=dict(relative=relative(delta,old),operation=float(np.linalg.norm(delta)/float(new['operation_scale'])),
                old_action=relative(old@new['directions']-new['old_action'],new['old_action']),
                new_action=relative(new['new_tensor']@new['directions']-new['new_action'],new['new_action']))
            values['pass_gate']=values['relative']<=1e-10 and values['operation']<=1e-12 and max(values['old_action'],values['new_action'])<=1e-12
            rows.append(values)
        recoveries=[]
        for rec in degree['recoveries']:
            v=checked_arrays(rec['arrays']);matrix=checked_arrays(rec['combined_tensor'])['new_tensor']
            recoveries.append(local_recovery_check(matrix,v))
        out[str(degree['degree'])]=dict(rows=rows,recoveries=recoveries,pass_gate=all(x['pass_gate'] for x in rows+recoveries))
    if sum(len(v.get('recoveries',[])) for v in out.values())>2:raise ValueError('two actual recovery witness limit')
    return out


def weak_quadrature_rows(r):
    """Recompute q differences from saved pre-cancellation operation scales."""
    qs=[row['q'] for row in r['rows']]
    if qs not in ([23,31],[23,31,39]):raise ValueError('continuous quadrature inventory')
    out=[];previous=None
    for row in r['rows']:
        v=checked_arrays(row['arrays'])
        if v['terms'].shape!=(7,24) or v['operation_scale'].shape!=(24,) or not np.isfinite(v['terms']).all():
            raise ValueError('complete finite weak parts')
        operation=v['operation_scale']
        if not np.isfinite(operation).all() or np.any(operation<=0):raise ValueError('positive integrated weak operation scale')
        delta=None if previous is None else float(np.max(np.abs(v['terms']-previous['terms']).sum(axis=0)/
            (operation+previous['operation_scale'])))
        out.append(dict(q=row['q'],operation_difference=delta,quadrature_pass=None if delta is None else delta<=1e-10))
        previous=v
    return out


def output_check(r):
    """Saved total-field absorption and fixed physical output; no FE action."""
    state=checked_arrays(r['arrays']);vm=r['output']['volume_metrics'];pm=r['output']['port_metrics']
    if vm['backend']!='direct_phase_quadrature' or vm['field_model_for_absorption']!='total_field':
        raise ValueError('V57 complete physical total-field output')
    if vm['q_pair']!=[23,31] or len(vm['all_rule_arrays'])!=2:raise ValueError('saved absorption quadrature inventory')
    nc=r['case_spec']['cells'];values=[];per_region={};k0=2*np.pi/.7
    if set(np.unique(state['cell_tags']))!={1,2,3} or {v['tag'] for v in vm['regions'].values()}!={2,3} or len(vm['regions'])!=2:
        raise ValueError('exact air/substrate/grating material inventory')
    for rec in vm['all_rule_arrays']:
        v=checked_arrays(rec);a=v['rows']
        if a.shape!=(nc,3) or not np.array_equal(v['cell_ids'],np.arange(nc)) or not np.array_equal(a[:,0],state['cell_tags']):
            raise ValueError('saved material/cell absorption inventory')
        if not np.isfinite(a).all() or np.any(a[:,1:]<0):raise ValueError('finite positive physical volume integrals')
        total=0.
        for name,region in vm['regions'].items():
            mask=a[:,0]==region['tag'];eps=complex(*region['epsilon_r_complex']);n=complex(*region['n_complex'])
            if abs(eps-n*n)>1e-15 or abs(eps.imag-region['Im_epsilon_r'])>1e-20:raise ValueError('canonical complex absorption sign')
            av=k0*.5*eps.imag*a[mask,1].sum()/vm['incident_power_code_units'];total+=av
            if rec==vm['all_rule_arrays'][-1]:
                if mask.sum()!=region['cell_count'] or not np.isclose(av,region['A_volume'],rtol=1e-12,atol=1e-15):
                    raise ValueError('actual absorbing region reduction')
                per_region[name]=float(av)
        values.append(float(total))
    qdef=max(abs(x-values[-1]) for x in values)/max(abs(values[-1]),1e-30)
    if abs(values[-1]-vm['A_volume_total'])>1e-13 or qdef>1e-10:raise ValueError('saved full absorption/q gate')
    energy=pm['R_total']+pm['T_total']+values[-1]-1
    if abs(energy-vm['energy_closure_error_port_volume'])>1e-13:raise ValueError('independent energy reduction')
    f=checked_arrays(r['output']['fixed_240'])
    if f['points'].shape!=(240,3) or any(f[n+'_'+k].shape!=(240,3) or not np.isfinite(f[n+'_'+k]).all()
        for n in ('E','H','curl') for k in ('total','scattered')):raise ValueError('complete fixed complex E/H/curl inventory')
    return dict(A_volume=values[-1],regions=per_region,q_pair=values,quadrature_operation=qdef,
        energy=float(energy),energy_pass=abs(energy)<=1e-5,selected_points=240,mode_count=r['case_spec']['complete_modes'])


def compact_science(stages,pointers):
    out={}
    if 'D' in stages:
        d=stages['D'];out['D']=dict(design=d['design'],analytic_control=d['analytic_control'],states=d['states'],
            result=pointers['D'],source_sha=d['source_sha'],full_field_accuracy_certificate=False)
    if 'K' in stages:
        k=stages['K'];out['K']=dict(result=pointers['K'],source_sha=k['source_sha'],
            original_qualification_parent=k.get('original_qualification_parent'),p6_pass=k['p6_pass'],p7_pass=k['p7_pass'],
            fresh_control=k['fresh_control'],degrees=[dict(degree=d['degree'],status=d['status'],pass_gate=d['pass_gate'],
                reference=d.get('reference'),actual_class_count=len(d.get('rows',[])),
                maximum_matrix_relative=max((r['relative_frobenius'] for r in d.get('rows',[])),default=None),
                maximum_operation_relative=max((r['operation_scaled'] for r in d.get('rows',[])),default=None),
                recoveries=d.get('recoveries',[]),recovery_status=d.get('recovery_status')) for d in k['degrees']])
    for role in scope.SOLVES:
        if role not in stages:continue
        r=stages[role]
        out[role]={k:r[k] for k in ('status','case_spec','degree','source_sha','solve_source_sha','arrays','returned_arrays',
            'original_audit','direct_target_pass','equation_pass','recovery','capacity','build_audit','fixed_refinements',
            'backend_reproduction_pass','comparisons','weak_balance','independent','raw_tensor_checkpoint') if k in r}
        # Keep the narrow raw manifest by hash rather than copying its old producer closure.
        if 'raw_tensor_checkpoint' in out[role]:
            raw=out[role].pop('raw_tensor_checkpoint');p=Path(r['arrays']['path']).parent/'raw_tensor/manifest.json'
            out[role]['raw_preparation']=dict(path=str(p.relative_to(scope.ROOT)),sha256=digest(p),
                classes=len(raw['classes']),stored_bytes=raw['stored_bytes'],readonly_reuse=raw['readonly_reuse'])
        out[role]['result']=pointers[role]
        out[role]['output']={k:r['output'][k] for k in ('fields','fixed_240','port_metrics','volume_metrics')}
    if 'VERIFY_COST' in stages:out['VERIFY_COST']=stages['VERIFY_COST']
    return dict(stages=out,NN_training=0,NN20=False,target_qualified=False,history_is_by_parent_pointer=True)


def archive_increment(folder,out,runs,sources,*,active_scope=scope):
    """Only the active increment and bound clean source, never a historical rescan."""
    scope=active_scope
    label=getattr(scope,'NAMESPACE','v57')
    archive=scope.ARTIFACT/('raw_'+folder.name);archive.mkdir(exist_ok=False);raw=[];seen=set()
    for root in [scope.window.TMP]+[Path(r['folder']) for r in runs]+[scope.ARTIFACT]:
        for p in root.rglob('*'):
            if not p.is_file() or p in seen or p.is_relative_to(archive) or p.is_relative_to(out):continue
            if p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.dat','.txt') and not (label=='v58' and p.name in ('stdout','stderr')):continue
            seen.add(p)
            if p.is_relative_to(scope.window.TMP) and any(n in p.relative_to(scope.window.TMP).parts
                for n in ('edit','pycache','xdg','torch','uv','ruff','source_archive')):continue
            # Freeze live log bytes first. A growing last auxiliary stream is a
            # snapshot here and is closed by the final settlement receipt.
            data=p.read_bytes();h=hashlib.sha256(data).hexdigest();dest=archive/h
            if not dest.exists():dest.write_bytes(data)
            raw.append(dict(path=str(p.relative_to(scope.ROOT)),bytes=len(data),sha256=h,archived=str(dest.relative_to(scope.ROOT)),
                byte_snapshot=True,final_auxiliary_tail_is_separate=True))
    write_json(out/f'raw_archive_index_{label}.json',dict(files=raw))
    source_archive=scope.ARTIFACT/'source_archive';source_archive.mkdir(exist_ok=True);rows=[]
    for sha,files in sources.items():
        for name,h in files.items():
            data=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',sha+':'+name],cwd=scope.ROOT)
            if hashlib.sha256(data).hexdigest()!=h:raise ValueError('real clean source mismatch '+name)
            dest=source_archive/h
            if not dest.exists():dest.write_bytes(data)
            rows.append(dict(source_sha=sha,path=name,sha256=h,archived=str(dest.relative_to(scope.ROOT))))
    write_json(out/f'source_bindings_{label}.json',dict(files=rows,document_HEAD_is_not_run_source=True))
    # JSON receipts bind full dtype/shape/member hashes. Audit only new arrays.
    inventory=[]
    for p in scope.ARTIFACT.rglob('*.npz'):
        with np.load(p,allow_pickle=False) as saved:
            members={}
            for n in saved.files:
                value=saved[n];members[n]=dict(shape=list(value.shape),dtype=str(value.dtype),sha256=array_hash(value))
        inventory.append(dict(path=str(p.relative_to(scope.ROOT)),bytes=p.stat().st_size,sha256=digest(p),members=members))
    write_json(out/f'array_inventory_{label}.json',dict(files=inventory))


def verify(folder,journal):
    from benchmarks.collect_phase_saved_closure import vector_check
    from benchmarks.collect_phase_notch_hp import saved_checks
    from benchmarks.collect_phase_explicit_accuracy import modal_recalculation
    freeze=scope.window.TMP/'scientific_queue_frozen.json';f=json.loads(freeze.read_text())
    if journal.source_state.get('verification_inventory',{}).get('sha256')!=hashlib.sha256(freeze.read_bytes()).hexdigest():raise ValueError('frozen V57 inventory identity')
    out={}
    d=scope.stage('D')
    frozen_scales={row['q']:checked_arrays(row['arrays'])['fixed_scale'] for row in d['analytic_control']['rows']}
    for role,item in f['completed_solves'].items():
        r=scope.stage(role)
        if item['array_sha256']!=r['arrays']['sha256']:raise ValueError('actual frozen solve changed')
        sub=Path(folder)/role;sub.mkdir(exist_ok=True)
        with journal.measured(role+'_independent_saved_checker'):
            vectors=vector_check(r['independent']['arrays'])
            states={role:r};states.update({x:scope.parent(x) for x in scope.plan_record()['comparison_partners'][role]})
            _,regions,gates=saved_checks(states,r['comparisons'],scope=scope)
            shim=SimpleNamespace(NAMESPACE='v57',window=scope.window,plan_record=scope.plan_record,stage=lambda _:r)
            modes=modal_recalculation(scope=shim,role_names=(role,),output_folder=sub)
            row=dict(original=vectors,regions=regions,gates=gates,modes=modes,complete_physical_output=output_check(r))
            if role=='B6':row['backend_reproduction']=reproduction_check(r['comparisons']['R6_B6'])
            if r.get('weak_balance'):
                row['weak_balance']=weak_check(r['weak_balance'],frozen_scales=frozen_scales)
                row['weak_quadratures']=weak_quadrature_rows(r['weak_balance'])
            out[role]=row;write_json(sub/'independent_checker.json',row)
    for role,fn in (('D',diagnostic_check),('K',tensor_check)):
        if (scope.ARTIFACT/(role+'.json')).exists():out[role]=fn(scope.stage(role))
    return dict(status='COMPLETED',role='VERIFY_COST',checks=out,new_FE_calls=0,new_factor_count=0,new_complete_solves=0)


def target_update(stages,costs):
    """Update measured preparation/scopes; reuse V56 scenarios by parent hash."""
    parent=scope.ROOT/'docs/task042_neural_coarse_inverse/outcomes/records/target_gap_final_v56.json'
    old=json.loads(parent.read_text());cases={}
    for role in scope.SOLVES:
        if role not in stages:continue
        r=stages[role];cost=next(c for c in costs if c['role']==role and c['classification']=='COMPLETED')
        spec=r['case_spec'];build=r['build_audit'];raw=r['raw_tensor_checkpoint']
        cases[role]=dict(case=spec,run_source_sha=r['source_sha'],solution_array_sha256=r['arrays']['sha256'],
            complete_physical_dat_with_research_audits_wall_seconds=cost['launch_seconds'],
            necessary_fresh_engine_cold_N1_seconds='unknown exact; this dat includes research comparison/weak consumers; disjoint necessary stages are measured below',
            cold_reference_seconds=raw['readonly_reuse']['reference']['total_build_seconds'],
            all_actual_raw_classes=len(raw['classes']),raw_combination_and_IO_provider_seconds=build['kernel_seconds_max'],
            local_schur_seconds=build['local_schur_seconds_max'],raw_saved_bytes=raw['stored_bytes'],
            actual_local_oriented_classes=build['retained_local_schur_class_count_local'],
            retained_local_Schur_LU_original_cache_bytes=build['retained_numeric_cache_bytes_local'],
            timing=cost['disjoint_timing'],sampled_tree_peak_bytes=cost['peak_bytes'],
            vector_scope=dict(full_independent_complex128_bytes=spec['independent']*16,
                trace_port_complex128_bytes=(spec['trace']+spec['complete_modes'])*16,interior_complex128_bytes=spec['internal']*16,
                hypothetical_34_trace_port_vectors_bytes=34*(spec['trace']+spec['complete_modes'])*16,
                hypothetical_34_full_vectors_bytes=34*spec['independent']*16,
                Krylov_actually_allocated=False,internal_restore_and_output_not_removed=True),
            cold_policy='new reference factory, raw combinations, condensation and new numeric factor for this case; retained OS/JIT hits, no factor reuse',
            matched_complete_old_cold_control='unknown; no end-to-end speed ratio granted')
    return dict(parent=dict(path=str(parent.relative_to(scope.ROOT)),sha256=digest(parent)),
        V56_scenarios_reused_without_new_layout=dict(count=len(old['bridge_scenarios']),new_mesh_mode_planning=0,
            scenario_not_accuracy_lower_bound=True,manual_inventory_not_required_physical_channel_proof=True),
        measured_preparation=cases,
        raw_sharing='exact p/basis/unrounded width/material/kappa classes share reference integration; not global factor sharing',
        streaming_DtN_interface=dict(input='canonical envelope boundary rows with Piola/orientation/MPC and physical reference plane',
            forward='iterate bounded mode/tile blocks, extract all modal integrals then scatter complete traction',
            adjoint='conjugate dual of the same extraction/scatter with all aliases retained',
            current_dense_row_by_mode_is_not_target_scalable=True,target_block_size_and_latency='unknown',
            reuse_scope='existing qualified interface only; no new dot boundary experiment'),
        action_contract=old['action_contract'],target_factor_fill='unknown',target_iteration_count='unknown',
        target_simultaneous_RSS='unknown',target_complete_cold_N1_seconds='unknown',
        accuracy=dict(B6_same_discrete_reproduction=stages.get('B6',{}).get('backend_reproduction_pass',False),
            Y6_main_increment=stages.get('Y6',{}).get('comparisons',{}).get('R6_Y6',{}).get('pass_gate',False),
            common_24_weak_witness_not_error_bound=True,cross_p_absolute_accuracy=False,continuum=False),
        required_next_solver='accurate phase Full3D original action with scalable iterative solver; no inherited reference-inverse step qualification',
        NN20=dict(trained=0,qualified=False,necessary_condition='f*V-H >= 0.2*T_best_non_neural at identical complete correctness; other resource compliant',
            complete_correctness_anchor_available=False,learning_object_selected=None),
        hours48_qualified=False,target_new_allocations=0)


def collect():
    from benchmarks.collect_phase_notch_hp import measured_timeline,sampling_receipt
    scope.window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    runs=scope.window.ledger()['runs'];costs=[];sources={};bindings=[]
    for run in runs:
        d=Path(run['folder']);manifest=json.loads((d/'run_manifest.json').read_text());sources[run['source_sha']]=manifest['implementation_hashes']
        sp=d/('run_summary.json' if (d/'run_summary.json').exists() else 'summary.json')
        if not sp.exists():sp=d/'launcher_failure.json'
        summary=json.loads(sp.read_text());worker=scope.ARTIFACT/d.name
        timing=measured_timeline(worker/'events.jsonl') if (worker/'events.jsonl').exists() else {}
        events=[json.loads(s) for s in (worker/'events.jsonl').read_text().splitlines()] if (worker/'events.jsonl').exists() else []
        lifecycle=[{k:v for k,v in e.items() if k!='clock'} for e in events if
            'released' in e['event'] or e['event'] in ('object_owner_snapshot','factor_present','h_numeric_capacity','finite_factor_numeric_admission')]
        costs.append(dict(role=run['role'],folder=str(d.relative_to(scope.ROOT)),source_sha=run['source_sha'],classification=run['classification'],
            supervised_seconds=run['elapsed_seconds'],launch_seconds=summary.get('launch_wall_seconds',run['elapsed_seconds']),
            peak_bytes=run['peak_bytes'],swap_bytes=run['swap_bytes'],
            resource_measurement_status=run.get('resource_measurement_status','measured sampled tree'),
            sampling=sampling_receipt(d/'supervision/resources.jsonl') if (d/'supervision/resources.jsonl').exists() else dict(status='NOT_MEASURED_NO_WORKER_STARTED'),
            disjoint_timing=timing,lifecycle=lifecycle,shared_workstation=True,
            symbolic_numeric_capacity=json.loads((worker/'h_symbolic_capacity.json').read_text())['plan']
                if (worker/'h_symbolic_capacity.json').exists() else None,
            actual_global_numeric_factors=sum(e['event']=='h_bounded_numeric_factor_end' for e in events),
            cost_policy='sum only exclusive timeline values; dat wall includes preparation, solve, output and original audit; failures retained'))
        if (d/'resolved_config.json').exists():bindings.append(dict(role=run['role'],source_sha=run['source_sha'],input_sha256=manifest['input_sha256'],
            physical_sha256=manifest['physical_sha256'],resolved_sha256=digest(d/'resolved_config.json'),mode='complete828',memory=manifest['memory_budget']))
    stages={r:scope.stage(r) for r in scope.STAGES if (scope.ARTIFACT/(r+'.json')).exists()}
    pointers={r:json.loads((scope.ARTIFACT/(r+'.json')).read_text()) for r in stages}
    values=dict(run_index_v57=dict(runs=runs,pointers=pointers),scientific_checks_v57=compact_science(stages,pointers),
        resource_costs_v57=dict(runs=costs,charged_lower_seconds=scope.window.charged_wall(),
            historical_lower_seconds=scope.plan_record()['historical_loaded_known_lower_seconds'],
            historical_unknown='preserved; no invented exact old bill',source_hashes=sources,bindings=bindings,clock=scope.window.snapshot(),
            final_auxiliary_tail='later final settlement receipt includes this collector and document checks',nominal_sampling_seconds=.5,
            sampled_peak_is_not_continuous_hard_peak=True,V56_correction=dict(T6_max_gap_seconds=9.56658,all_auxiliary_max_gap_seconds=12.975,old_records_unchanged=True)),
        target_gap_v57=target_update(stages,costs),
        physical_identity_bindings_v57=dict(physical=scope.plan_record()['physical_descriptor'],runs=bindings,
            frozen_saved_parents=scope.plan_record()['frozen_saved_stages'],raw_parent_hashes=scope.plan_record()['raw_tensor_parents']),
        repair_journal_v57=json.loads((scope.window.TMP/'repair_notes.json').read_text()),
        stage_verdicts_v57={role:dict(status=r['status'],source_sha=r.get('source_sha'),result=pointers[role]) for role,r in stages.items()})
    for name,value in values.items():write_json(out/(name+'.json'),value)
    archive_increment(folder,out,runs,sources)
    print(json.dumps(dict(status='V57_COMPACT_EVIDENCE_COLLECTED',records=str(out),increment_only=True)))


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:
        from benchmarks.collect_phase_notch_hp import documents
        documents(scope=scope,review_name='review_report_v55.md',response_name='response_v57.md',outcome_name='common_weak_phase_preparation_v57.md')
    elif not sys.argv[1:]:collect()
    else:raise ValueError('V57 collector arguments')
