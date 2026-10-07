"""Thin V57 queue: shared continuous tests, phase provider, two real solves."""
import hashlib
import json
import gc
from pathlib import Path
from time import perf_counter
import numpy as np
from src.runners.task042_shared import write_json
from . import common_weak_phase_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .phase_notch_hp import restore_record,solve_case,configured_setup
from .phase_saved_closure import compare_pair,independent_state


def common_study(folder,journal,roles=('R6','T6','R7','H7')):
    from .common_continuous_weak import design,evaluate
    from .fixed_phase_fem import carrier
    from .phase_explicit_accuracy import configuration
    initial_cfg=configuration('NOTCH',6,'ORIGINAL')
    definition=design(scope.plan_record()['physical_descriptor']['geometry'],carrier(initial_cfg))
    write_json(scope.ARTIFACT/'common_design.json',definition)
    record=scope.parent('R6');cfg,setup,geo,field=restore_record(record,journal,scope=scope)
    if not np.array_equal(definition['kappa'],carrier(cfg)):raise ValueError('frozen continuous design kappa')
    control=evaluate(record,(cfg,setup,geo,field),definition,folder/'analytic_flat_control',journal,scope=scope,analytic_control=True)
    write_json(folder/'analytic_control.json',control)
    if not control['analytic_control_pass'] or not control['nonzero_perturbation_detected']:
        return dict(status='DIAGNOSTIC_CONTROL_FAILED',role='D',design=definition,analytic_control=control,states={},
            full_field_accuracy_certificate=False,new_complete_solves=0,new_factor_count=0)
    rows={}
    for role in roles:
        r=scope.parent(role);restored=(cfg,setup,geo,field) if role=='R6' else restore_record(r,journal,scope=scope)
        result=evaluate(r,restored,definition,folder/role,journal,scope=scope)
        rows[role]=result;write_json(folder/'completed_weak_states.json',dict(rows=rows,control=control,design=definition))
        if role!='R6':del restored;gc.collect()
    return dict(status='COMPLETED',role='D',design=definition,analytic_control=control,states=rows,
        full_field_accuracy_certificate=False,new_complete_solves=0,new_factor_count=0)


def tensor_setup(folder,journal):
    import basix
    from scipy.linalg import solve
    from .hcurl_affine_phase_tensor import AffinePhaseReferenceTensor,axis_widths
    from .phase_raw_tensor_reader import ReadonlyRawTensorProvider
    from .fixed_phase_fem import carrier
    from .hcurl_assembly_time_condensation import _cell_integral_kernels,_tabulate_raw_tensor_class
    from .common_3d_forms import _build_physical_volume_terms
    from dolfinx import fem
    import ufl
    result=[];fresh=[];recovery_count=0
    for degree,roles in ((6,('R6','T6')),(7,('R7','H7'))):
        resume=scope.window.TMP/'K_p6_resume.json'
        if degree==6 and resume.exists():
            previous,controls=consume_p6_setup_checkpoint(resume,folder,journal)
            result.append(previous);fresh.extend(controls);recovery_count=2
            write_json(folder/'p6_completed_qualification.json',previous)
            continue
        if degree==7 and (perf_counter()-journal.began>1500 or scope.window.available_at_boundary('K')<500):
            result.append(dict(degree=7,status='NOT_RUN_BUDGET',pass_gate=False));break
        r=scope.parent(roles[0]);cfg,setup,geo,field=restore_record(r,journal,scope=scope)
        element=basix.finite_element.FiniteElement(setup['spaces'][degree].element.basix_element)
        k=carrier(cfg);eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
        with journal.measured(f'p{degree}_cold_reference_complete_15_grams'):
            factory=AffinePhaseReferenceTensor(element,kappa=k,k0=cfg.k0,mu=cfg.mu_r,epsilon_by_tag=eps,q=2*degree+3)
        refs={};rows=[];entries=[];seen=set();recoveries=[]
        for role in roles:
            rr=scope.parent(role)
            if rr.get('raw_tensor_checkpoint'):
                manifest=rr['raw_tensor_checkpoint']
            else:
                receipt=rr.get('minimal_state_receipt');path=Path(receipt['path']).parent/'raw_tensor/manifest.json'
                manifest=json.loads(path.read_text())
            # Validate producer/material/basis contracts through the existing
            # reader for the explicitly frozen parent manifests when available.
            if role in ('R6','R7'):
                contracts=[scope.plan_record()['raw_tensor_parents']['p6_Z2' if degree==6 else 'p7']]
                provider=ReadonlyRawTensorProvider(contracts,dict(cfg=cfg,degree=degree,kappa=k),journal,scope.ROOT)
                refs[role]=provider.parents
            for entry in manifest['classes']:
                v=checked_arrays(entry['arrays']);h=axis_widths(v['coordinates']);key=(int(entry['tag']),tuple(h),int(entry['element_hash']))
                if key in seen:continue
                if entry['degree']!=degree or entry['element_hash']!=element.hash() or not np.array_equal(v['kappa'],k):raise ValueError('actual raw complete phase identity')
                seen.add(key);entries.append((entry,h));old=v['tensor']
                with journal.measured(f'p{degree}_complete_class_combination'):
                    new,scale=factory.tensor(tag=entry['tag'],widths=h,return_scale=True)
                delta=np.linalg.norm(new-old);rel=float(delta/max(np.linalg.norm(old),1e-300));op=float(delta/max(scale,1e-300))
                rng=np.random.default_rng(570600+len(rows));directions=rng.normal(size=(degree*0+element.dim,2))+1j*rng.normal(size=(element.dim,2))
                effects=[relative((new-old)@d,old@d) for d in directions.T]
                witness=save_arrays(folder/f'p{degree}_class{len(rows):03d}.npz',widths=h,coordinates=v['coordinates'],
                    directions=directions,old_action=old@directions,new_action=new@directions,new_tensor=new,
                    operation_scale=np.asarray(scale))
                row=dict(tag=entry['tag'],widths=h,raw_parent=entry['arrays'],relative_frobenius=rel,
                    operation_scaled=op,action_relative=effects,arrays=witness,pass_gate=rel<=1e-10 and op<=1e-12 and max(effects)<=1e-10)
                rows.append(row);write_json(folder/f'p{degree}_progress.json',dict(rows=rows,reference=factory.audit))
                if recovery_count<2:
                    # Actual persisted coefficients provide nonzero trace and
                    # internal load. Match this raw class to its actual cell.
                    layout=checked_arrays(manifest['cell_layout']);ids=np.flatnonzero(layout['cell_class_key_utf8']==entry['key'].encode())
                    if len(ids):
                        cell=int(ids[0]);full=checked_arrays(rr['arrays'])['u_storage'][layout['native_cell_dofs'][cell]]
                        T=np.eye(element.dim)
                        # Use that parent's actual native orientation, not the
                        # first mesh's cell index.
                        element.T_apply(T.ravel(),element.dim,int(layout['permutations'][cell]))
                        co=T.T@full;inside=np.asarray(element.entity_dofs[3][0],int);trace=np.setdiff1d(np.arange(element.dim),inside)
                        fi=(old@co)[inside];recover=solve(new[np.ix_(inside,inside)],fi-new[np.ix_(inside,trace)]@co[trace])
                        defect=relative(recover-co[inside],co[inside]);rec=save_arrays(folder/f'p{degree}_recovery{len(recoveries)}.npz',
                            actual_coefficients=co,internal_rhs=fi,recovered_internal=recover,internal_rows=inside,trace_rows=trace)
                        recoveries.append(dict(relative=defect,pass_gate=defect<=1e-10,arrays=rec,homogeneous_and_particular=True,
                            raw_class_index=len(rows)-1,raw_parent=entry['arrays'],combined_tensor=witness))
                        recovery_count+=1
                del new,old,v;gc.collect()
        if degree==6 and entries:
            # Only the two pre-registered geometric aspect extremes are timed.
            order=sorted(range(len(entries)),key=lambda i:(max(entries[i][1])/min(entries[i][1]),tuple(entries[i][1]),entries[i][0]['tag']))
            selected=list(dict.fromkeys((order[0],order[-1])))
            write_json(folder/'fresh_pair_design.json',dict(indices=selected,classes=[entries[i][0]['key'] for i in selected],selection='min/max exact aspect before original fresh calls'))
            V=setup['spaces'][degree];dx=ufl.Measure('dx',domain=setup['mesh'],subdomain_data=setup['mesh_data'].cell_tags)
            terms=_build_physical_volume_terms(cfg,ufl.TrialFunction(V),ufl.TestFunction(V),dx,phase_carrier=k)
            with journal.measured('fresh_control_original_form_compile_cache_identity'):
                form=fem.form(terms[0]+terms[1]);kernels=_cell_integral_kernels(form,sum_duplicate_cell_integrals=True)
            for index in selected:
                entry,h=entries[index];v=checked_arrays(entry['arrays'])
                start=perf_counter();old=_tabulate_raw_tensor_class(form,kernels,v['coordinates'],tag=entry['tag'],dimension=element.dim);old_seconds=perf_counter()-start
                start=perf_counter();new=factory.tensor(tag=entry['tag'],widths=h);new_seconds=perf_counter()-start
                fresh.append(dict(key=entry['key'],degree=6,old_fresh_kernel_seconds=old_seconds,new_combination_seconds=new_seconds,
                    reference_cold_seconds=factory.build_seconds,same_object_relative=relative(new-old,old),
                    cached_load_is_not_control=True))
                write_json(folder/'fresh_control_results.json',fresh)
        passed=bool(rows) and all(x['pass_gate'] for x in rows) and (degree==7 or len(recoveries)==2) and all(x['pass_gate'] for x in recoveries)
        result.append(dict(degree=degree,status='COMPLETED',pass_gate=passed,rows=rows,reference=factory.audit,recoveries=recoveries,
            recovery_status='COMPLETE_TWO_ACTUAL_P6_WITNESSES' if recoveries else 'NOT_RUN_GLOBAL_TWO_WITNESS_LIMIT',producer_validation=refs))
        write_json(folder/f'p{degree}_completed_qualification.json',result[-1])
        del factory,setup,field;gc.collect()
    return dict(status='COMPLETED',role='K',degrees=result,p6_pass=next(x['pass_gate'] for x in result if x['degree']==6),
        p7_pass=any(x.get('pass_gate') for x in result if x['degree']==7),fresh_control=fresh,new_complete_solves=0,new_global_factor_count=0)


def consume_p6_setup_checkpoint(path,folder,journal):
    """Continue saved class comparisons and controls, preserving their costs.

    The controlled stop saved 40/58 classes and both local recovery witnesses.
    The same unpersisted reference table is rebuilt once as charged repair;
    only missing classes and unconsumed fresh controls are evaluated.
    """
    import basix
    import ufl
    from dolfinx import fem
    from .hcurl_affine_phase_tensor import axis_widths,AffinePhaseReferenceTensor
    from .phase_raw_tensor_reader import ReadonlyRawTensorProvider
    from .hcurl_assembly_time_condensation import _cell_integral_kernels,_tabulate_raw_tensor_class
    from .common_3d_forms import _build_physical_volume_terms
    from .fixed_phase_fem import carrier
    from benchmarks.collect_common_weak_phase import tensor_check
    frozen=json.loads(path.read_text());oldfolder=Path(frozen['folder'])
    progress=Path(frozen.get('progress_path',oldfolder/'p6_progress.json'));events=oldfolder/'events.jsonl'
    for name,p in (('progress',progress),('events',events)):
        if hashlib.sha256(p.read_bytes()).hexdigest()!=frozen[name+'_sha256']:raise ValueError('partial setup checkpoint changed')
    old=json.loads(progress.read_text());rows=old['rows'];cfg,setup,_,field=restore_record(scope.parent('R6'),journal,scope=scope)
    k=carrier(cfg);element=basix.finite_element.FiniteElement(setup['spaces'][6].element.basix_element)
    identity=ReadonlyRawTensorProvider([scope.plan_record()['raw_tensor_parents']['p6_Z2']],dict(cfg=cfg,degree=6,kappa=k),journal,scope.ROOT)
    expected=set();entries={}
    for role in ('R6','T6'):
        r=scope.parent(role);manifest=r['raw_tensor_checkpoint']
        for e in manifest['classes']:
            a=checked_arrays(e['arrays'])
            if e['degree']!=6 or e['element_hash']!=element.hash() or not np.array_equal(a['kappa'],k):raise ValueError('saved p6 identity')
            key=(e['tag'],tuple(axis_widths(a['coordinates'])));expected.add(key);entries[key]=e
    covered={(r['tag'],tuple(r['widths'])) for r in rows};factory=None
    if not covered.issubset(expected):raise ValueError('saved setup class inventory contains another case')
    if expected!=covered:
        # The controlled stop left 18 classes unprocessed. Rebuild the same
        # reference set once as charged repair work, not a new representation.
        # Prior completed comparisons and the two actual LUs are not replayed.
        with journal.measured('repair_missing_reference_table_rebuild'):
            factory=AffinePhaseReferenceTensor(element,kappa=k,k0=cfg.k0,mu=cfg.mu_r,
                epsilon_by_tag={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating},q=15)
        old['reference']['charged_repair_rebuild']=factory.audit
        for key,e in entries.items():
            if key in covered:continue
            v=checked_arrays(e['arrays']);h=axis_widths(v['coordinates']);oldtensor=v['tensor']
            with journal.measured('p6_complete_missing_class_combination'):
                new,scale=factory.tensor(tag=e['tag'],widths=h,return_scale=True)
            rng=np.random.default_rng(570600+len(rows));directions=rng.normal(size=(element.dim,2))+1j*rng.normal(size=(element.dim,2))
            delta=np.linalg.norm(new-oldtensor);rel=float(delta/np.linalg.norm(oldtensor));op=float(delta/scale)
            effects=[relative((new-oldtensor)@d,oldtensor@d) for d in directions.T]
            witness=save_arrays(folder/f'p6_missing_class{len(rows):03d}.npz',widths=h,coordinates=v['coordinates'],
                directions=directions,old_action=oldtensor@directions,new_action=new@directions,new_tensor=new,operation_scale=np.asarray(scale))
            rows.append(dict(tag=e['tag'],widths=h,raw_parent=e['arrays'],relative_frobenius=rel,operation_scaled=op,
                action_relative=effects,arrays=witness,pass_gate=rel<=1e-10 and op<=1e-12 and max(effects)<=1e-10))
            write_json(folder/'p6_partial_qualification.json',dict(rows=rows,reference=old['reference']))
        covered={(r['tag'],tuple(r['widths'])) for r in rows}
    if expected!=covered:raise ValueError('complete actual p6 class coverage')
    recoveries=[]
    for witness in frozen['recoveries']:
        v=checked_arrays(witness);matches=[]
        for i,row in enumerate(rows):
            oldtensor=checked_arrays(row['raw_parent'])['tensor'];inside=v['internal_rows'];co=v['actual_coefficients']
            if relative((oldtensor@co)[inside]-v['internal_rhs'],v['internal_rhs'])<=1e-13:matches.append(i)
        if not matches:raise ValueError('saved actual recovery cannot bind to raw class')
        i=matches[0];defect=relative(v['recovered_internal']-v['actual_coefficients'][v['internal_rows']],v['actual_coefficients'][v['internal_rows']])
        recoveries.append(dict(arrays=witness,relative=defect,pass_gate=defect<=1e-10,raw_class_index=i,
            raw_parent=rows[i]['raw_parent'],combined_tensor=rows[i]['arrays'],homogeneous_and_particular=True))
    result=dict(degree=6,status='COMPLETED',rows=rows,reference=old['reference'],recoveries=recoveries,
        producer_validation=identity.parents,setup_checkpoint=frozen,recovery_status='REUSED_TWO_ACTUAL_WITNESSES_NO_NEW_LOCAL_LU')
    result['pass_gate']=tensor_check({'degrees':[result]})['6']['pass_gate'] and len(recoveries)==2
    measured=frozen.get('combination_seconds')
    if measured is None:
        cumulative=[json.loads(line)['seconds'] for line in events.read_text().splitlines()
            if json.loads(line)['event']=='p6_complete_class_combination_end']
        measured=list(np.diff([0.,*cumulative]))
    if len(measured)!=len(json.loads(progress.read_text())['rows']):raise ValueError('saved fresh combination timing inventory')
    order=sorted(range(len(rows)),key=lambda i:(max(rows[i]['widths'])/min(rows[i]['widths']),tuple(rows[i]['widths']),rows[i]['tag']))
    selected=list(dict.fromkeys((order[0],order[-1])))
    write_json(folder/'fresh_pair_design.json',dict(indices=selected,selection='same predetermined min/max aspect; earlier fresh combination retained, no table rebuild'))
    V=setup['spaces'][6];dx=ufl.Measure('dx',domain=setup['mesh'],subdomain_data=setup['mesh_data'].cell_tags)
    terms=_build_physical_volume_terms(cfg,ufl.TrialFunction(V),ufl.TestFunction(V),dx,phase_carrier=k)
    with journal.measured('fresh_control_original_form_compile_cache_identity'):
        form=fem.form(terms[0]+terms[1]);kernels=_cell_integral_kernels(form,sum_duplicate_cell_integrals=True)
    fresh=list(frozen.get('fresh_controls_consumed',[]));consumed={x['class_index'] for x in fresh}
    for index in selected:
        if index in consumed:continue
        row=rows[index];v=checked_arrays(row['raw_parent'])
        if factory is not None:
            with journal.measured('fresh_new_fixed_p6_class_combination'):
                began=perf_counter();new=factory.tensor(tag=row['tag'],widths=row['widths']);newseconds=perf_counter()-began
        else:
            new=checked_arrays(row['arrays'])['new_tensor'];newseconds=measured[index]
        with journal.measured('fresh_original_fixed_p6_class'):
            start=perf_counter();oldtensor=_tabulate_raw_tensor_class(form,kernels,v['coordinates'],tag=row['tag'],dimension=element.dim);seconds=perf_counter()-start
        # Save returned matrices before formatting any derivative JSON record.
        control_arrays=save_arrays(folder/f'fresh_pair_{index:03d}.npz',old_tensor=oldtensor,new_tensor=new,coordinates=v['coordinates'])
        fresh.append(dict(degree=6,class_index=index,arrays=control_arrays,key=str(row['tag'])+str(row['widths']),old_fresh_kernel_seconds=seconds,
            new_combination_seconds=newseconds,reference_cold_seconds=old['reference']['total_build_seconds'],
            same_object_relative=relative(new-oldtensor,oldtensor),cached_load_is_not_control=True,
            timing_design='same-object fixed pair; reference repair rebuild and earlier construction both charged; no end-to-end speed ratio',
            new_combination_source_sha=frozen['source_sha']))
        write_json(folder/'fresh_control_results.json',fresh)
    del setup,field
    return result,fresh


def strict_reproduction(pair):
    # Preserve original spatial gates. The caller/checker additionally consumes
    # the raw actual pair metrics to apply the stricter backend thresholds.
    from benchmarks.collect_common_weak_phase import reproduction_check
    return reproduction_check(pair)


def solve_and_consume(role,folder,journal):
    r=solve_case(role,folder,journal,scope=scope);write_json(folder/'completed_before_comparisons.json',r)
    if not r.get('equation_pass'):return r
    b=restore_record(r,journal,scope=scope);pairs={}
    for old_role in scope.plan_record()['comparison_partners'][role]:
        old=scope.parent(old_role);a=restore_record(old,journal,scope=scope)
        pairs[old_role+'_'+role]=compare_pair(old,r,a,b,folder/(old_role+'_'+role),journal)
        r['comparisons']=pairs;write_json(folder/'comparison_progress.json',r)
        if old_role=='R6':
            points=checked_arrays(pairs[old_role+'_'+role]['arrays'])
            fixed=dict(points=points['selected_points'],parent_cells=points['selected_parent_second'],kappa=checked_arrays(r['arrays'])['kappa'])
            fixed.update({n+'_'+k:points['selected_'+n+'_'+k+'_second'] for n in ('E','H','curl') for k in ('total','scattered')})
            r['output']['fixed_240']=save_arrays(folder/'fixed_240_physical_fields.npz',**fixed)
    r['independent']=independent_state(r,b,folder/(role+'_original'),journal)
    if role=='B6':r['backend_reproduction_pass']=strict_reproduction(pairs['R6_B6'])['pass_gate'] and r['independent']['equation_pass'] and r['independent']['recovery_pass']
    if role=='Y6' and (scope.ARTIFACT/'D.json').exists():
        from .common_continuous_weak import evaluate
        d=scope.stage('D');definition=d['design']
        scales={x['q']:checked_arrays(x['arrays'])['fixed_scale'] for x in d['analytic_control']['rows']}
        r['weak_balance']=evaluate(r,b,definition,folder/'Y6_common_weak',journal,scope=scope,frozen_scales=scales)
        r['weak_balance']['design_parent']=json.loads((scope.ARTIFACT/'D.json').read_text())
    return r


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V57 resolved/live envelope')
    if role=='D':r=common_study(folder,journal)
    elif role=='K':
        repair=scope.window.TMP/'K_checker_resume.json'
        if repair.exists():
            from benchmarks.collect_common_weak_phase import tensor_check
            parent=json.loads(repair.read_text());path=Path(parent['path'])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=parent['sha256']:raise ValueError('frozen K checker input')
            r=json.loads(path.read_text())
            with journal.measured('saved_phase_tensor_independent_recovery_scale_recheck'):checks=tensor_check(r)
            r.update(original_qualification_parent=parent,independent_recheck=checks,
                p6_pass=checks['6']['pass_gate'],p7_pass=checks.get('7',{}).get('pass_gate',False),
                new_complete_solves=0,new_global_factor_count=0,new_reference_tables=0,new_local_LU=0)
            for d in r['degrees']:d['pass_gate']=checks[str(d['degree'])].get('pass_gate',False)
        else:r=tensor_setup(folder,journal)
    elif role in scope.SOLVES:r=solve_and_consume(role,folder,journal)
    elif role=='VERIFY_COST':
        from benchmarks.collect_common_weak_phase import verify
        r=verify(folder,journal)
    else:raise ValueError('V57 explicit stage')
    r.update(timings=journal.timings,calls=journal.calls,NN_training=0,target_qualified=False)
    write_json(folder/'minimum_scientific_results.json',r)
    return r
