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
