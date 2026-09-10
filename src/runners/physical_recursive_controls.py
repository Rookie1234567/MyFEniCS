"""Thin G1 adapter for saved V5 calibration packets; no reference rebuilding."""
import hashlib
import json
from pathlib import Path
import numpy as np


def load_recursive_calibration(inventory_path):
    """Load only the six audited g/y arrays; independent measurement data."""
    from .physical_diagnostic_completion import load_packet
    inventory = json.loads(Path(inventory_path).read_text())
    rows = inventory['six_calibration_rhs']
    if len(rows) != 6:
        raise ValueError('G1 requires exactly six frozen RHS')
    result = []
    for row in rows:
        for key, hash_key in [('input_json','input_sha256'), ('reference_packet','reference_packet_sha256')]:
            if hashlib.sha256(Path(row[key]).read_bytes()).hexdigest() != row[hash_key]:
                raise ValueError('calibration identity mismatch')
        source, reference = load_packet(Path(row['input_json'])), load_packet(Path(row['reference_packet']))
        if not np.array_equal(source['g'], reference['g']):
            raise ValueError('reference RHS differs')
        map_path=Path(row['input_json']).parent/'native_constraint_map_p4.json'
        if hashlib.sha256(map_path.read_bytes()).hexdigest() != inventory['checked_file_hashes'][str(map_path)]:
            raise ValueError('frozen native map hash mismatch')
        result.append(dict(identity=row, rhs=source['g'], reference_y=reference['y'],reference_A4y=reference['A4y'],
            reference_map=load_packet(Path(row['input_json']).parent/'native_constraint_map_p4.json')))
    return result


def load_recursive_balanced_inputs(inventory_path):
    """Load the three audited p6 ``e/q`` packets and native maps.

    This is the shared G0 loader for the V10 control.  It verifies the same
    E1 audit and packet hashes used by the existing recursive component
    runner, but does not load any saved solve output or reference field.
    """
    from .physical_diagnostic_completion import load_packet

    inventory_path = Path(inventory_path)
    inventory = json.loads(inventory_path.read_text())
    rows = inventory.get('six_calibration_rhs', ())
    if len(rows) != 6:
        raise ValueError('G0 inventory must contain exactly six calibration rows')
    root = Path(rows[0]['input_json']).parent
    audit_path = root.parent / 'e1_audit.json'
    if hashlib.sha256(audit_path.read_bytes()).hexdigest() != inventory['e1_audit_sha256']:
        raise ValueError('E1 audit identity mismatch')
    audit = json.loads(audit_path.read_text())
    hashes = {item['path']: item['sha256'] for item in audit['raw_hashes']}

    def checked_packet(name):
        path = root / (name + '.json')
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path)]:
            raise ValueError('frozen packet identity mismatch')
        return load_packet(path)

    inputs = {
        name: checked_packet(name + '_balanced_input')
        for name in ('A2R160', 'LIGHT448', 'JOINT448')
    }
    maps = {
        6: checked_packet('native_constraint_map_p6'),
        4: checked_packet('native_constraint_map_p4'),
    }
    for name, packet in inputs.items():
        if 'e' not in packet or 'q' not in packet or packet['e'].shape != packet['q'].shape:
            raise ValueError(f'{name} balanced input must contain matching e/q arrays')
        if not np.isfinite(packet['e']).all() or not np.isfinite(packet['q']).all():
            raise ValueError(f'{name} balanced input contains non-finite values')
    return {
        'inventory': inventory, 'root': root, 'inputs': inputs, 'maps': maps,
        'e1_audit_sha256': inventory['e1_audit_sha256'],
    }


def verify_recursive_map(bundle, degree, reference):
    from src.solvers.condensed_fine_reference import native_map_arrays
    current = native_map_arrays(bundle['levels']['spaces'][degree], bundle['levels']['floquets'][degree])
    if any(key not in reference or not np.array_equal(value, reference[key]) for key,value in current.items()):
        raise ValueError('fresh calibration map differs from saved native map')
    return current


def evaluate_recursive_balanced(bundle, cfg, inputs, reference_map, *, save):
    """Three fresh complete BAL_H calls; old fields are independent metrics only.

    inputs contains exactly the hash-checked V5 balanced_input e/q packets.
    There is no reference solve, projection, or saved g2 in the PC path.
    """
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.fullspace_physical_intermediate import apply_owned
    if set(inputs) != {'A2R160','LIGHT448','JOINT448'}:
        raise ValueError('three frozen error inputs required')
    mapping = verify_recursive_map(bundle, 6, reference_map)
    indices = mapping['independent_indices']
    metric = LosslessFEMetric(bundle['levels'], 6, cfg.k0, bundle['actions']['volume_quadrature_metadata'])
    try:
        for name, item in inputs.items():
            q = level_vector(bundle['levels'], 6); z = az = None
            try:
                q.set(0); q.array[indices] = item['e']
                ae=apply_owned(bundle['fine']['physical_action'],q)
                bundle['counts']['evaluation_A6_identity']=bundle['counts'].get('evaluation_A6_identity',0)+1
                try:
                    if np.linalg.norm(ae.array[indices]-item['q'])/max(np.linalg.norm(item['q']),np.finfo(float).tiny)>1e-10:
                        raise ValueError('fresh A6e differs from frozen q')
                finally:ae.destroy()
                q.array[indices] = item['q']
                z = bundle['pc'].apply(q)
                az = apply_owned(bundle['fine']['physical_action'], z)
                bundle['counts']['evaluation_A6_output']=bundle['counts'].get('evaluation_A6_output',0)+1
                remaining = item['e']-z.array[indices]
                # Every G1 sample gets actual final identity, independent of formal periodic sampling.
                balance = bundle['inexact_ledger'].audit_last()
                save(name+'_recursive_balanced', dict(q=item['q'], z=z.array[indices].copy(),
                    Az=az.array[indices].copy(), remaining=remaining,
                    L2_squared=_metric_square(bundle,metric.mass, remaining),
                    scaled_curl_squared=_metric_square(bundle,metric.curl, remaining),
                    input_L2_squared=_metric_square(bundle,metric.mass,item['e']),
                    input_scaled_curl_squared=_metric_square(bundle,metric.curl,item['e']),
                    true_residual_ratio=float(np.linalg.norm(item['q']-az.array[indices])/np.linalg.norm(item['q'])),
                    stages=bundle['pc'].last_apply_facts, balance=balance,
                    costs=dict(bundle['counts']), p2_costs=dict(bundle['p2_inverse'].counts)))
            finally:
                q.destroy()
                if z is not None: z.destroy()
                if az is not None: az.destroy()
    finally:
        metric.destroy()


def run_recursive_components(cfg, comm, inventory_path, directory, *, target, sample, marker):
    """G1 only: six saved RHS plus three fresh PC calls under caller watchdog.

    The caller supplies the qualified clean-source/resource/time gates. This
    function neither launches an outer solve nor constructs any reference LU.
    """
    from .physical_diagnosis_worker import save_packet
    from .physical_diagnostic_completion import load_packet
    from src.solvers.physical_recursive_coarse import build_recursive_physical_solver, destroy_recursive_physical_solver
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.fullspace_physical_intermediate import apply_owned
    inventory = json.loads(Path(inventory_path).read_text())
    root = Path(inventory['six_calibration_rhs'][0]['input_json']).parent
    audit_path = root.parent/'e1_audit.json'
    if hashlib.sha256(audit_path.read_bytes()).hexdigest() != inventory['e1_audit_sha256']:
        raise ValueError('E1 audit identity mismatch')
    audit = json.loads(audit_path.read_text()); hashes = {r['path']:r['sha256'] for r in audit['raw_hashes']}
    def checked_packet(name):
        path = root/(name+'.json')
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path)]:
            raise ValueError('frozen packet identity mismatch')
        return load_packet(path)
    inputs = {name:checked_packet(name+'_balanced_input') for name in ('A2R160','LIGHT448','JOINT448')}
    map6, map4 = checked_packet('native_constraint_map_p6'), checked_packet('native_constraint_map_p4')
    items = load_recursive_calibration(inventory_path)
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    save = lambda name, facts: save_packet(directory,name,facts)
    bundle = metric = None
    try:
        bundle = build_recursive_physical_solver(cfg,comm,target=target,sample=sample,marker=marker,save=save,audit_every=1)
        verify_recursive_map(bundle,6,map6);verify_recursive_map(bundle,4,map4)
        from src.solvers.fullspace_physical_intermediate_runtime import qualify_physical_intermediate_setup
        save('fresh_identity',qualify_physical_intermediate_setup(bundle,marker=marker,resource_sample=sample))
        metric = LosslessFEMetric(bundle['levels'],6,cfg.k0,bundle['actions']['volume_quadrature_metadata'])
        transfer = bundle['actions']['transfers'][(6,4)]
        for item in items:
            rhs=level_vector(bundle['levels'],4); reference=rhs.duplicate()
            result=error_fine=reference_fine=difference=None
            try:
                rhs.array[:]=item['rhs'];reference.array[:]=item['reference_y']
                native_reference=apply_owned(bundle['actions']['physical'][4]['physical_action'],reference)
                bundle['counts']['evaluation_A4_reference']=bundle['counts'].get('evaluation_A4_reference',0)+1
                try:
                    scale=max(np.linalg.norm(item['reference_A4y']),np.finfo(float).tiny)
                    if np.linalg.norm(native_reference.array-item['reference_A4y'])/scale > 1e-10:
                        raise ValueError('fresh A4 action differs from frozen calibration physics')
                finally:native_reference.destroy()
                result=bundle['I4'](rhs)
                reference_fine=transfer.apply_primal(reference)
                difference=result['solution'].copy();difference.axpy(-1,reference)
                error_fine=transfer.apply_primal(difference)
                bundle['counts']['evaluation_P64']=bundle['counts'].get('evaluation_P64',0)+2
                e=error_fine.array[map6['independent_indices']];y=reference_fine.array[map6['independent_indices']]
                values={}
                for label,action in [('L2',metric.mass),('scaled_curl',metric.curl)]:
                    absolute=_metric_square(bundle,action,e); baseline=_metric_square(bundle,action,y)
                    values[label]=dict(error_squared=absolute,reference_squared=baseline,
                        relative=float(np.sqrt(absolute/baseline)) if baseline else None)
                save(item['identity']['stem']+'_I4',dict(identity=item['identity'],facts=result['facts'],
                    solution=result['solution'].array.copy(),residual=result['residual'].array.copy(),
                    coarse_field_difference=values,costs=dict(bundle['counts']),p2_costs=dict(bundle['p2_inverse'].counts)))
            finally:
                rhs.destroy();reference.destroy()
                if difference is not None:difference.destroy()
                if error_fine is not None:error_fine.destroy()
                if reference_fine is not None:reference_fine.destroy()
                if result:
                    for key in ('solution','applied','residual'):result[key].destroy()
        metric.destroy();metric=None
        evaluate_recursive_balanced(bundle,cfg,inputs,map6,save=save)
        save('components_summary',dict(target=target,status='G1_COMPONENTS_COMPLETED',
            fixed_rhs_calls=6,full_PC_calls=3,costs=dict(bundle['counts']),p2_costs=dict(bundle['p2_inverse'].counts),
            p2_matrix=bundle['p2_matrix_facts'],bottom=bundle['p2_inverse'].bottom.audit,
            h6=bundle['positive']['light_facts'],h4=bundle['h4_setup']['light_facts'],
            storage=bundle['numerical_storage'],new_reference_factor=False))
    finally:
        if metric is not None:metric.destroy()
        if bundle is not None:destroy_recursive_physical_solver(bundle)


def _metric_square(bundle, action, vector):
    from src.solvers.physical_error_diagnostics import metric_square
    bundle['counts']['evaluation_metric_calls']=bundle['counts'].get('evaluation_metric_calls',0)+1
    return metric_square(action,vector)


def load_p4_failure_input(binding_path):
    """Exactly the first frozen A2R160 g1; do not load the other five RHS."""
    from .physical_diagnostic_completion import load_packet
    binding=json.loads(Path(binding_path).read_text())
    if binding['sample']!='A2R160_BAL_H_p4_01' or binding['candidate_source']!='2edcf84888a7e989246b0fae28bc4555b61fc48d':
        raise ValueError('only frozen first A2R160 g1 is admitted')
    packets={}
    for name,item in binding['packets'].items():
        path=Path(item['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('p4 diagnostic input hash mismatch: '+name)
        packets[name]=load_packet(path)
    if packets['candidate_manifest']['source']['head']!=binding['candidate_source']:
        raise ValueError('candidate source manifest differs')
    g=packets['input']['g'];ref=packets['reference'];old=packets['candidate']
    if not np.array_equal(g,ref['g']):raise ValueError('reference g differs')
    indices=packets['map']['independent_indices'];slaves=np.setdiff1d(np.arange(g.size),indices)
    arrays=dict(g=g,y=ref['y'],A4y=ref['A4y'],c=old['solution'],eps=old['residual'])
    if any(a.shape!=g.shape or not np.isfinite(a).all() or np.any(a[slaves]!=0) for a in arrays.values()):
        raise ValueError('frozen input finite/slave/primal-dual contract differs')
    scale=float(np.linalg.norm(g[indices]))
    if scale<=0:raise ValueError('nonzero frozen g required')
    return dict(binding=binding,map=packets['map'],scale=scale,
        arrays={k:np.array(a[indices]/scale,copy=True) for k,a in arrays.items()})


def measure_p4_failure(data, *, A, P, PH, M, curl, diagonal, solve2, H4, B4,
                       sample, save, projection_seconds, components=None, b4_facts=lambda: {}):
    """Fixed array orchestration. All numerical diagnostics use existing helpers."""
    from src.solvers.physical_error_diagnostics import (project_error,coarse_diagnostics,
        coarse_identity_diagnostics,correction_diagnostics,component_diagnostics,metric_square,ProjectionLimit)
    a=data['arrays'];g,y,c,eps=a['g'],a['y'],a['c'],a['eps']
    before={k:v.copy() for k,v in a.items()}
    ay,ac=A(y),A(c)
    errors=dict(A4y_saved=float(np.linalg.norm(ay-a['A4y'])/max(np.linalg.norm(a['A4y']),np.finfo(float).tiny)),
        A4y_g=float(np.linalg.norm(ay-g)/np.linalg.norm(g)),
        A4c_saved=float(np.linalg.norm(ac-(g-eps))/max(np.linalg.norm(g-eps),np.finfo(float).tiny)))
    save('input_bridge',dict(binding=data['binding'],normalization=data['scale'],errors=errors,
        coordinates='independent; common ||g|| scaling',vectors=a))
    if max(errors.values())>1e-10:raise ValueError('frozen p4 physical bridge differs')
    def projection_checkpoint():
        sample()
        if projection_seconds()>=600:raise ProjectionLimit('600s cumulative projection allowance')
    # Diagonal and CG share one clock. A timeout during diagonal leaves the zero
    # approximation; it cannot establish a best representation or space failure.
    projection_seconds(start=True)
    try:
        diag=diagonal(checkpoint=projection_checkpoint)
        projection=project_error(P,PH,M,diag,y,rtol=1e-10,max_it=256,checkpoint=projection_checkpoint)
    except ProjectionLimit:
        e2=metric_square(M,y)
        projection=dict(status='PROJECTION_UNRESOLVED',parallel=np.zeros_like(y),perpendicular=y.copy(),
            coarse=None,error_energy=e2,parallel_energy=0.,perpendicular_energy=e2,
            iterations=0,exit_reason='local_projection_time_limit_during_diagonal',interpretation='approximation upper bound only')
    projection['conservative_seconds']=projection_seconds()
    if projection['conservative_seconds']>600:
        projection.update(status='PROJECTION_UNRESOLVED',interpretation='approximation upper bound only')
    save('p2_projection',projection)
    def norms(x):return dict(M0_squared=metric_square(M,x),scaled_curl_squared=metric_square(curl,x))
    save('field_norms',dict(y=norms(y),old_error=norms(y-c),parallel=norms(projection['parallel']),
        perpendicular=norms(projection['perpendicular']),projection_status=projection['status']))
    coarse=coarse_diagnostics(A,M,P,PH,solve2,y,projection,identity_check=False,saved_q=g)
    coarse['scaled_curl']=correction_diagnostics(A,curl,y,g,coarse['dg'],
        saved_applied_direction=coarse['applied_direction'])
    save('C42_on_g',coarse)
    range_vector=projection['parallel']
    identity=(coarse_identity_diagnostics(A,M,P,PH,solve2,range_vector)
        if np.linalg.norm(range_vector) else dict(status='NOT_APPLICABLE_ZERO_RANGE'))
    save('range_identity',identity)
    if identity.get('coarse_identity_relative_field_error',0)>1e-8:
        raise ValueError('range identity exceeds 1e-8')
    aperp=A(projection['perpendicular'])
    if components is not None:
        component=component_diagnostics(components,projection['perpendicular'])
        component['sum_relative_error']=float(np.linalg.norm(component['sum_vector']-aperp)/max(np.linalg.norm(aperp),np.finfo(float).tiny))
        save('perpendicular_components',component)
        if component['sum_relative_error']>1e-10:
            raise ValueError('p4 component sum differs from A4 perpendicular')
    if projection['status']=='PROJECTION_CLOSED':
        left=PH(A(projection['parallel']));right=PH(aperp);whole=PH(g)
        n1,n2=float(np.linalg.norm(left)),float(np.linalg.norm(right))
        decomposition=dict(parallel_dual=left,perpendicular_dual=right,total_dual=whole,
            parallel_dual_norm=n1,perpendicular_dual_norm=n2,
            complex_angle=np.vdot(left,right)/(n1*n2) if n1*n2 else None,
            sum_over_parts=float(np.linalg.norm(left+right)/max(n1+n2,np.finfo(float).tiny)),
            closure_relative=float(np.linalg.norm(left+right-whole)/max(n1+n2,np.finfo(float).tiny)),
            response_vs_best_projection=norms(coarse['dg']-projection['parallel']),
            norm_role='dual coefficient Euclidean, not field energy')
        save('coarse_decomposition',decomposition)
        if decomposition['closure_relative']>1e-8:
            raise ValueError('coarse component closure exceeds 1e-8')
        if coarse['decomposition_relative_defect']>1e-8:
            raise ValueError('coarse energy decomposition exceeds 1e-8')
    else:save('coarse_decomposition',dict(status='NOT_QUALIFIED_PROJECTION_UNRESOLVED'))
    def correction(name,e,q,z):
        az=A(z)
        mass=correction_diagnostics(A,M,e,q,z,saved_applied_direction=az)
        curled=correction_diagnostics(A,curl,e,q,z,saved_applied_direction=az)
        save(name,dict(direction=z,applied=az,M0=mass,scaled_curl=curled,
            MR_role='diagnostic only; not applied to PC',
            B4_facts=b4_facts() if name.startswith('B4_') else None))
    correction('H4_on_perpendicular',projection['perpendicular'],aperp,H4(aperp))
    correction('B4_on_g',y,g,B4(g))
    correction('B4_on_old_eps',y-c,eps,B4(eps))
    unchanged=all(np.array_equal(v,before[k]) for k,v in a.items())
    if not unchanged:raise ValueError('diagnostic changed a frozen input')
    return dict(status='P4_FAILURE_DIAGNOSTIC_COMPLETED',projection_status=projection['status'],
        input_unchanged=unchanged,I4_calls=0,outer_calls=0,H4_standalone=1,B4_calls=2,
        new_reference_factor=False)


def run_p4_failure_diagnostic(cfg, comm, binding_path, directory, *, sample, marker):
    """One p4 hard input, one p2 mass projection; no I4 or outer invocation."""
    from types import SimpleNamespace
    from .physical_diagnosis_worker import save_packet
    from .workflow_timebase import ClockBudget,clock_sample,CONSERVATIVE_REALTIME
    from src.solvers.physical_recursive_coarse import build_recursive_physical_solver,destroy_recursive_physical_solver
    from src.solvers.physical_error_metric import LosslessFEMetric,SerialAction
    from src.solvers.fullspace_physical_intermediate import apply_owned
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda n,f:save_packet(directory,n,f)
    data=load_p4_failure_input(binding_path)
    bundle=None;metrics=[];bridges=[];counts=dict(A4_started=0,A4_completed=0)
    try:
        bundle=build_recursive_physical_solver(cfg,comm,target=1e-4,sample=sample,marker=marker,save=save)
        actual_mode=bundle['fine']['mode_sha256']
        save('mode_identity',dict(actual=actual_mode,expected=data['binding']['mode_sha256']))
        if actual_mode!=data['binding']['mode_sha256']:raise ValueError('fresh mode identity differs')
        verify_recursive_map(bundle,4,data['map']);levels=bundle['levels']
        positive_baseline=bundle['h4_setup']['smoother'].matrix_mult_count
        # This local proxy counts the same native action inside B4 as well as
        # explicit diagnostic calls; restore it before destroying the bundle.
        physical=bundle['actions']['physical'][4];original=physical['physical_action']
        def limited_A4(x,z):
            sample()
            if counts['A4_started']>=40:raise RuntimeError('diagnostic A4 limit40')
            counts['A4_started']+=1;apply_owned(original,x,z);counts['A4_completed']+=1
        physical['physical_action']=SimpleNamespace(apply=limited_A4)
        def bridge(action,source=4,target=4,result='target'):
            obj=SerialAction(levels['spaces'][source],levels['floquets'][source],action,result=result,
                target_space=levels['spaces'][target],target_floquet=levels['floquets'][target])
            bridges.append(obj);return obj
        A=bridge(limited_A4);transfer=bundle['actions']['transfers'][(4,2)]
        P=bridge(transfer.apply_primal,2,4,'owned');PH=bridge(transfer.apply_adjoint,4,2,'owned')
        def bottom(x):
            if bundle['p2_inverse'].counts['logical']>=12:raise RuntimeError('diagnostic p2 limit12')
            return bundle['p2_inverse'].apply(x)
        solve2=bridge(bottom,2,2,'owned')
        def standalone_h4(x):
            counts['H4_standalone_started']=counts.get('H4_standalone_started',0)+1
            value=bundle['h4_setup']['smoother'].apply(x)
            counts['H4_standalone_completed']=counts.get('H4_standalone_completed',0)+1
            counts['H4_standalone_positive']=bundle['h4_setup']['smoother'].last_apply_facts['matrix_mult_count']
            return value
        H4=bridge(standalone_h4,result='owned')
        def balanced(x):
            if bundle['p2_inverse'].counts['logical']+2>12:raise RuntimeError('diagnostic p2 limit12')
            counts['B4_started']=counts.get('B4_started',0)+1
            try:
                value=bundle['B4'].apply(x)
                counts['B4_completed']=counts.get('B4_completed',0)+1
                return value
            finally:
                save('B4_cost_'+str(counts['B4_started']),bundle['B4'].last_apply_facts)
        B4=bridge(balanced,result='owned')
        quadrature=bundle['actions']['volume_quadrature_metadata']
        for degree in (4,2):
            marker('lossless_metric_started',dict(degree=degree))
            metrics.append(LosslessFEMetric(levels,degree,cfg.k0,quadrature))
        components={name:bridge(action.apply,result='borrowed') for name,action in physical['volume_action'].component_actions.items()}
        components['dtn']=bridge(physical['dtn_action'].apply)
        def diagonal(checkpoint):
            checkpoint();v=PH(data['arrays']['g']);v=v/np.linalg.norm(v)
            native=metrics[1].mass(v);composed=PH(metrics[0].mass(P(v)))
            error=float(np.linalg.norm(native-composed)/max(np.linalg.norm(native),np.finfo(float).tiny))
            save('p2_mass_identity',dict(relative_error=error,limit=1e-10,diagonal='exact constrained unweighted M0'))
            if error>1e-10:raise ValueError('p2 native mass differs from PH M4 P')
            return metrics[1].diagonal(checkpoint=checkpoint)
        clock=None
        def projection_seconds(start=False):
            nonlocal clock
            if start:clock=ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
            return clock.update(clock_sample())['budget_seconds']
        result=measure_p4_failure(data,A=A,P=P,PH=PH,M=metrics[0].mass,curl=metrics[0].curl,
            diagonal=diagonal,solve2=solve2,H4=H4,B4=B4,sample=sample,save=save,
            projection_seconds=projection_seconds,components=components,
            b4_facts=lambda:bundle['B4'].last_apply_facts)
        result.update(counts=counts,p2_counts=bundle['p2_inverse'].counts,
            metrics=[m.audit for m in metrics],bridges=[b.audit for b in bridges],
            bottom=bundle['p2_inverse'].bottom.audit,storage=bundle['numerical_storage'])
        save('diagnostic_summary',result);return result
    finally:
        for obj in reversed(bridges):obj.destroy()
        for obj in reversed(metrics):obj.destroy()
        if bundle is not None:
            if 'original' in locals():bundle['actions']['physical'][4]['physical_action']=original
            try:
                save('terminal_costs',dict(counts=counts,p2_counts=bundle['p2_inverse'].counts if 'p2_inverse' in bundle else {},
                    bundle_counts=dict(bundle['counts']),bridges=[b.audit for b in bridges],
                    H4_positive_measurement=bundle['h4_setup']['smoother'].matrix_mult_count-positive_baseline if 'positive_baseline' in locals() else 0,
                    H4_positive_including_setup=bundle['h4_setup']['smoother'].matrix_mult_count,
                    metrics=[dict(audit=m.audit,mass=m.mass.audit,curl=m.curl.audit) for m in metrics],
                    components={k:v.audit for k,v in components.items()} if 'components' in locals() else {},
                    last_B4_facts=bundle['B4'].last_apply_facts,
                    I4_calls=bundle['counts']['I4'],outer_calls=bundle['pc'].apply_count if 'pc' in bundle else 0))
            finally:destroy_recursive_physical_solver(bundle)


def evaluate_projected_p4_component(bundle, cfg, binding_path, *, sample, save):
    """One saved g1 I4 only; caller owns unchanged setup and parent watchdog.

    No new projection or B4 baseline. The frozen reference y is used only after
    the solve for field-error measurements, never passed to the new mechanism.
    """
    import time
    from src.solvers.physical_projected_complement import solve_projected_p4_complement
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.physical_error_diagnostics import metric_square
    data=load_p4_failure_input(binding_path)
    verify_recursive_map(bundle,4,data['map'])
    if bundle['fine']['mode_sha256']!=data['binding']['mode_sha256']:
        raise ValueError('projected component mode identity differs')
    transfer=bundle['actions']['transfers'][(4,2)]
    bottom=bundle['p2_inverse'];smoother=bundle['h4_setup']['smoother']
    counts_before=dict(bottom.counts);positive_before=smoother.matrix_mult_count
    rhs=level_vector(bundle['levels'],4);rhs.set(0)
    indices=data['map']['independent_indices'];rhs.array[indices]=data['arrays']['g']
    result=metric=None
    calls=dict(A4_inner_started=0,A4_inner_completed=0,A4_identity_started=0,A4_identity_completed=0,
        H4_started=0,H4_completed=0,I4_started=0,I4_completed=0,A4_identity_seconds=0.)
    source_rhs=rhs.array.copy()
    slaves=np.setdiff1d(np.arange(rhs.getLocalSize()),indices)
    def native(x):return apply_owned(bundle['actions']['physical'][4]['physical_action'],x)
    def A(x):
        sample()
        if calls['A4_inner_started']>=150:raise RuntimeError('projected inner A4 cap150')
        calls['A4_inner_started']+=1;value=native(x);calls['A4_inner_completed']+=1;return value
    def H(x):
        sample()
        if calls['H4_started']>=64 or smoother.matrix_mult_count-positive_before+2>128:
            raise RuntimeError('projected H4/positive cap')
        calls['H4_started']+=1;value=smoother.apply(x);calls['H4_completed']+=1;return value
    def C(x):
        sample()
        if bottom.counts['logical']-counts_before['logical']>=65:raise RuntimeError('projected p2 cap65')
        q=transfer.apply_adjoint(x);value=None
        try:
            value=bottom.apply(q);return transfer.apply_primal(value)
        finally:
            q.destroy()
            if value is not None:value.destroy()
    try:
        reference=rhs.duplicate();reference.set(0);reference.array[indices]=data['arrays']['y'];ay=None
        try:
            sample();calls['A4_identity_started']+=1;start=time.perf_counter()
            try:ay=native(reference);calls['A4_identity_completed']+=1
            finally:calls['A4_identity_seconds']+=time.perf_counter()-start
            error=float(np.linalg.norm(ay.array[indices]-data['arrays']['A4y'])/np.linalg.norm(data['arrays']['A4y']))
            save('projected_source_bridge',dict(relative_error=error,limit=1e-10,
                mode_sha256=bundle['fine']['mode_sha256'],native_map='exact',costs=dict(calls)))
            if not np.isfinite(error) or error>1e-10:raise ValueError('projected source A4 bridge failed')
        finally:
            reference.destroy()
            if ay is not None:ay.destroy()
        calls['I4_started']+=1
        result=solve_projected_p4_complement(rhs,A,C,H,sample=sample,save=save)
        calls['I4_completed']+=1
        vectors=[rhs]+[result[k] for k in ('solution','applied','residual')]
        validation=dict(input_unchanged=np.array_equal(rhs.array,source_rhs),
            finite=all(np.isfinite(v.array).all() for v in vectors),
            slave_zero=all(np.all(v.array[slaves]==0) for v in vectors))
        original_norm=float(np.linalg.norm(source_rhs))
        raw_eps=source_rhs-result['applied'].array
        recomputed=float(np.linalg.norm(raw_eps)/original_norm)
        validation.update(original_rhs_norm=original_norm,recomputed_true=recomputed,
            normalization_matches=bool(np.isclose(result['facts']['rhs_norm'],original_norm,rtol=1e-12,atol=0)),
            residual_matches=bool(np.allclose(raw_eps,result['residual'].array,rtol=1e-12,atol=1e-14)),
            reported_true_matches=bool(np.isclose(recomputed,result['facts']['final_true_residual'],rtol=1e-12,atol=1e-14)))
        valid=all(validation[k] for k in ('input_unchanged','finite','slave_zero','normalization_matches','residual_matches','reported_true_matches'))
        validation['status']='PASS' if valid else 'FAIL'
        save('projected_result_validation',validation)
        if not valid:
            save('projected_result_rejected',dict(validation=validation,facts=result['facts'],
                solution=result['solution'].array.copy(),applied=result['applied'].array.copy(),residual=result['residual'].array.copy()))
            raise ValueError('projected result finite/slave/input/residual gate failed')
        result['facts']['p2_counts']={k:v-counts_before[k] for k,v in bottom.counts.items()}
        result['facts']['H4_positive_count']=smoother.matrix_mult_count-positive_before
        # Persist terminal solve evidence before any separate metric setup.
        save('projected_p4_result',dict(binding=data['binding'],normalization=data['scale'],facts=result['facts'],
            solution=result['solution'].array.copy(),residual=result['residual'].array.copy(),
            applied=result['applied'].array.copy(),input_unchanged=np.array_equal(rhs.array[indices],data['arrays']['g'])))
        metric=LosslessFEMetric(bundle['levels'],4,cfg.k0,bundle['actions']['volume_quadrature_metadata'])
        error=data['arrays']['y']-result['solution'].array[indices]
        fields={}
        for name,action in [('M0',metric.mass),('scaled_curl',metric.curl)]:
            sample();remaining=metric_square(action,error);baseline=metric_square(action,data['arrays']['y'])
            fields[name]=dict(remaining_energy=remaining,reference_energy=baseline,
                field_ratio=float(np.sqrt(remaining/baseline)))
        save('projected_p4_field_error',dict(fields=fields,reference_role='measurement only',
            projection_calls=0,B4_baseline_calls=0,outer_calls=0))
        return result['facts']
    finally:
        try:
            save('projected_p4_component_costs',dict(p2_counts={k:v-counts_before[k] for k,v in bottom.counts.items()},
                H4_positive_count=smoother.matrix_mult_count-positive_before,calls=dict(calls),
                old_I4_calls=bundle['counts']['I4'],projection_calls=0,B4_baseline_calls=bundle['B4'].apply_count,
                metric_calls={k:v.audit for k,v in metric.bridges.items()} if metric is not None else {},outer_calls=0))
        finally:
            if metric is not None:metric.destroy()
            if result is not None:
                for key in ('solution','applied','residual'):result[key].destroy()
            rhs.destroy()



def run_projected_p4_component(cfg,comm,binding_path,directory,*,sample,marker):
    """Same cold setup, exactly one new I4, no old components or outer solve."""
    from .physical_diagnosis_worker import save_packet
    from src.solvers.physical_recursive_coarse import build_recursive_physical_solver,destroy_recursive_physical_solver
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda n,f:save_packet(directory,n,f)
    bundle=None
    try:
        bundle=build_recursive_physical_solver(cfg,comm,target=1e-4,sample=sample,marker=marker,save=save)
        marker('projected_p4_component_started',{})
        facts=evaluate_projected_p4_component(bundle,cfg,binding_path,sample=sample,save=save)
        save('projected_component_summary',dict(status='COMPONENT_COMPLETED',I4=facts,
            solver_target_reached=facts['final_true_residual']<=1e-4,
            bottom=bundle['p2_inverse'].bottom.audit,storage=bundle['numerical_storage'],
            I4_calls=1,old_I4_calls=bundle['counts']['I4'],outer_calls=bundle['pc'].apply_count,
            projection_calls=0,B4_baseline_calls=bundle['B4'].apply_count))
    finally:
        if bundle is not None:destroy_recursive_physical_solver(bundle)
