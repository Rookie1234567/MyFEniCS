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
    result=[];fresh=[]
    for degree,roles in ((6,('R6','T6')),(7,('R7','H7'))):
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
                contracts=[scope.plan_record()['raw_tensor_parents']['p6_Z2' if degree==6 else 'p7_Z2']]
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
                if len(recoveries)<2:
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
                        recoveries.append(dict(relative=defect,pass_gate=defect<=1e-10,arrays=rec,homogeneous_and_particular=True))
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
        passed=bool(rows) and all(x['pass_gate'] for x in rows) and len(recoveries)==2 and all(x['pass_gate'] for x in recoveries)
        result.append(dict(degree=degree,status='COMPLETED',pass_gate=passed,rows=rows,reference=factory.audit,recoveries=recoveries,producer_validation=refs))
        del factory,setup,field;gc.collect()
    return dict(status='COMPLETED',role='K',degrees=result,p6_pass=next(x['pass_gate'] for x in result if x['degree']==6),
        p7_pass=any(x.get('pass_gate') for x in result if x['degree']==7),fresh_control=fresh,new_complete_solves=0,new_global_factor_count=0)


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
    if role=='Y6' and (scope.ARTIFACT/'common_design.json').exists():
        from .common_continuous_weak import evaluate
        definition=json.loads((scope.ARTIFACT/'common_design.json').read_text())
        r['weak_balance']=evaluate(r,b,definition,folder/'Y6_common_weak',journal,scope=scope)
    return r


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V57 resolved/live envelope')
    if role=='D':r=common_study(folder,journal)
    elif role=='K':r=tensor_setup(folder,journal)
    elif role in scope.SOLVES:r=solve_and_consume(role,folder,journal)
    elif role=='VERIFY_COST':
        from benchmarks.collect_common_weak_phase import verify
        r=verify(folder,journal)
    else:raise ValueError('V57 explicit stage')
    r.update(timings=journal.timings,calls=journal.calls,NN_training=0,target_qualified=False)
    write_json(folder/'minimum_scientific_results.json',r)
    return r
