"""One fixed saved-input enriched coarse/I4 component; no outer invocation."""
from pathlib import Path
import numpy as np


def run_bubble_component(cfg,comm,binding_path,directory,*,sample,marker):
    from .physical_diagnosis_worker import save_packet
    from .physical_recursive_controls import load_p4_failure_input,verify_recursive_map
    from src.solvers.physical_recursive_coarse import build_recursive_physical_solver,destroy_recursive_physical_solver,solve_physical_i4
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_error_diagnostics import metric_square
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda n,f:save_packet(directory,n,f)
    bundle=metric=result=None;vectors=[]
    counts=dict(source_A4=0,range_checks=0,Cg=0,I4_started=0,I4_completed=0,B4=0,A4_external=0)
    b4_operations={};b4_seconds={};setup_composed={}
    def keep(v):vectors.append(v);return v
    try:
        data=load_p4_failure_input(binding_path)
        bundle=build_recursive_physical_solver(cfg,comm,target=1e-4,sample=sample,marker=marker,save=save,bubble_enriched=True)
        setup_composed=dict(bundle['bubble'].counts)
        verify_recursive_map(bundle,4,data['map'])
        if bundle['fine']['mode_sha256']!=data['binding']['mode_sha256']:raise ValueError('mode identity differs')
        bubble=bundle['bubble'];transfer=bubble.transfer;bottom=bundle['p2_inverse']
        indices=data['map']['independent_indices']
        rhs=keep(level_vector(bundle['levels'],4));rhs.set(0);rhs.array[indices]=data['arrays']['g']
        def guard():
            sample()
            if bottom.counts['logical']>130 or bottom.counts['MatSolve_attempted']>390 or bubble.counts['composed_started']>392:
                raise RuntimeError('bubble p2/composed call budget exceeded')
        def A(x):
            guard();counts['A4_external']+=1
            if counts['A4_external']>220:raise RuntimeError('bubble external A4 cap220')
            return apply_owned(bundle['actions']['physical'][4]['physical_action'],x)
        def C(x):
            q=transfer.apply_adjoint(x);c=None
            try:c=bottom.apply(q);return transfer.apply_primal(c)
            finally:
                q.destroy()
                if c is not None:c.destroy()
        reference=keep(rhs.duplicate());reference.set(0);reference.array[indices]=data['arrays']['y']
        ay=A(reference);counts['source_A4']+=1
        try:error=float(np.linalg.norm(ay.array[indices]-data['arrays']['A4y'])/np.linalg.norm(data['arrays']['A4y']))
        finally:ay.destroy()
        save('bubble_source_bridge',dict(relative_error=error,limit=1e-10,native_map='exact',binding=data['binding']))
        if not np.isfinite(error) or error>1e-10:raise ValueError('original source action bridge failed')
        q=keep(level_vector(bundle['levels'],2));rng=np.random.default_rng(385)
        q.array[:]=rng.normal(size=q.getLocalSize())+1j*rng.normal(size=q.getLocalSize());q.array[transfer.coarse_slaves]=0
        w=transfer.apply_primal(q);aw=cw=None
        try:
            aw=A(w);cw=C(aw);counts['range_checks']+=1
            range_error=float(np.linalg.norm(cw.array-w.array)/w.norm())
            save('bubble_range_identity',dict(q=q.array.copy(),Wq=w.array.copy(),CW_A4_Wq=cw.array.copy(),
                relative=range_error,limit=1e-10,bottom_counts=dict(bottom.counts)))
            if not np.isfinite(range_error) or range_error>1e-10:raise ValueError('range W coarse identity failed')
        finally:
            for v in (w,aw,cw):
                if v is not None:v.destroy()
        metric=LosslessFEMetric(bundle['levels'],4,cfg.k0,bundle['actions']['volume_quadrature_metadata'])
        baselines={name:metric_square(action,data['arrays']['y']) for name,action in (('M0',metric.mass),('scaled_curl',metric.curl))}
        def fields(solution,name):
            error=data['arrays']['y']-solution.array[indices];values={}
            for key,action in (('M0',metric.mass),('scaled_curl',metric.curl)):
                sample();remaining=metric_square(action,error)
                values[key]=dict(remaining_energy=remaining,reference_energy=baselines[key],field_ratio=float(np.sqrt(remaining/baselines[key])))
            save(name,dict(fields=values,reference_role='measurement only'))
        c=C(rhs);ac=None;counts['Cg']+=1
        try:
            ac=A(c);eps=rhs.array-ac.array;relative=float(np.linalg.norm(eps)/rhs.norm())
            save('bubble_Cg',dict(rhs=rhs.array.copy(),solution=c.array.copy(),applied=ac.array.copy(),residual=eps,
                original_true_residual=relative,bottom_counts=dict(bottom.counts)))
            fields(c,'bubble_Cg_fields')
        finally:
            c.destroy()
            if ac is not None:ac.destroy()
        def B(x):
            guard()
            if counts['B4']>=64:raise RuntimeError('bubble B4 cap64')
            counts['B4']+=1
            try:return bundle['B4'].apply(x)
            finally:
                facts=bundle['B4'].last_apply_facts
                for k,v in facts['counts'].items():b4_operations[k]=b4_operations.get(k,0)+v
                for k,v in facts['operation_seconds'].items():b4_seconds[k]=b4_seconds.get(k,0.)+v
                save(f"bubble_B4_{counts['B4']:03d}",dict(count=counts['B4'],facts=facts,cumulative_operations=b4_operations,cumulative_seconds=b4_seconds))
        counts['I4_started']+=1
        result=solve_physical_i4(rhs,A,B,target=1e-4,sample=guard,save=save)
        counts['I4_completed']+=1
        facts=result['facts']
        validation=dict(input_unchanged=np.array_equal(rhs.array[indices],data['arrays']['g']),
            finite=all(np.isfinite(result[k].array).all() for k in ('solution','applied','residual')),
            slave_zero=all(np.all(result[k].array[transfer.fine_slaves]==0) for k in ('solution','applied','residual')),
            raw_true=float(np.linalg.norm(rhs.array-result['applied'].array)/rhs.norm()))
        validation['reported_match']=bool(np.isclose(validation['raw_true'],facts['final_true_residual'],rtol=1e-12,atol=1e-14))
        save('bubble_I4_result',dict(facts=facts,validation=validation,rhs=rhs.array.copy(),
            solution=result['solution'].array.copy(),applied=result['applied'].array.copy(),residual=result['residual'].array.copy()))
        if not all(validation[k] for k in ('input_unchanged','finite','slave_zero','reported_match')):raise ValueError('bubble I4 result validation failed')
        fields(result['solution'],'bubble_I4_fields')
        save('bubble_component_summary',dict(status='COMPONENT_COMPLETED',solver_target_reached=facts['final_true_residual']<=1e-4,
            I4=facts,counts=counts,bottom=bottom.bottom.audit,old_factor_count=0,p4_global_matrix=0,outer=0,G5_closed=False))
    finally:
        try:
            save('bubble_component_costs',dict(counts=counts,B4_operations=b4_operations,B4_seconds=b4_seconds,
                bottom_A2_true_semantics='legacy counter name: each check applies S=WH A4 W, not old native A2',
                original_A4_count_semantics='external + B4 A_structure + composed_started; attempted callbacks, completed flow gives actual count',
                original_A4_total_started=(counts['A4_external']+b4_operations.get('A_structure',0)
                    +bundle['bubble'].counts['composed_started']) if bundle is not None else None,
                setup_composed=setup_composed,
                setup_composed_semantics='one S assembly qualifier composed call; included in composed total and parent budget, never free',
                bottom=dict(bundle['p2_inverse'].counts) if bundle is not None else {},
                composed=dict(bundle['bubble'].counts) if bundle is not None else {},
                B4=bundle['B4'].apply_count if bundle is not None else 0,
                H4_positive=bundle['h4_setup']['smoother'].matrix_mult_count if bundle is not None else 0,
                metric={k:v.audit for k,v in metric.bridges.items()} if metric is not None else {},outer=0))
        finally:
            if result is not None:
                for k in ('solution','applied','residual'):result[k].destroy()
            if metric is not None:metric.destroy()
            for v in reversed(vectors):v.destroy()
            if bundle is not None:destroy_recursive_physical_solver(bundle)
