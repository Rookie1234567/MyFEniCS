"""Posterior matched-reference checks, called only after solver-stack release."""
import hashlib
import json
from pathlib import Path
import numpy as np


def compare_balanced_output(fine, solution, outputs, directory, payload, *, marker, sample):
    from .physical_intermediate import _atomic_json
    if payload['geometry'].get('cell_notch'):
        return dict(status='REFERENCE_AUTHORITY_LIMITED',
                    reason='conditional notch direct reference requires separate capacity gate')
    from .actual_error_diagnosis import checked_json
    from .physical_diagnostic_completion import load_packet
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_error_diagnostics import metric_square
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import recover_p0_outputs
    binding = json.loads(Path('input/task39extra/actual_error_evidence.json').read_text())
    audit = checked_json(binding['reference_audit'], binding['reference_audit_sha256'])
    hashes = {x['path']:x['sha256'] for x in audit['artifact_hashes']}
    source = Path(binding['reference_root'])/'reference_full_residual.json'
    checked_json(source, hashes[str(source)])
    ref = load_packet(source)
    if (ref['identity']['original_physical_sha256'] != payload['provenance']['physical_model_sha256'] or
            ref['identity']['mode_sha256'] != fine['mode_sha256']):
        raise ValueError('posterior reference physical/mode identity mismatch')
    if np.linalg.norm(ref['b']-ref['ax'])/np.linalg.norm(ref['b']) > 1e-10:
        raise ValueError('posterior reference raw residual gate failed')
    from src.solvers.condensed_fine_reference import native_map_arrays
    map_path=Path(binding['reference_root'])/'reference_native_map.json'
    checked_json(map_path,hashes[str(map_path)])
    reference_map=load_packet(map_path)
    current_map=native_map_arrays(fine['setup']['spaces'][6],fine['setup']['floquets'][6])
    if any(not np.array_equal(value,reference_map[key]) for key,value in current_map.items()):
        raise ValueError('posterior native map identity mismatch')
    marker('posterior_reference_started', {})
    sample()
    metric = LosslessFEMetric(fine['setup'], 6, fine['cfg'].k0, ref['quadrature'])
    try:
        indices = metric.mass.indices
        x = ref['x_ref'][indices]; delta = solution.array[indices]-x
        field_norms = {name:dict(absolute_error_norm=float(np.sqrt(metric_square(action,delta))),
                                reference_norm=float(np.sqrt(metric_square(action,x))))
                       for name,action in [('L2',metric.mass),('scaled_curl',metric.curl)]}
        field = {name:v['absolute_error_norm']/v['reference_norm'] for name,v in field_norms.items()}
    finally:
        metric.destroy()
    # One output recovery from the existing saved reference, never a refactor.
    cache = Path('benchmarks/artifacts/task39extra/v5_balanced/reference_output')
    manifest = cache/'binding.json'
    reference_hash = hashes[str(source)]
    output_identity = hashlib.sha256(json.dumps(payload['output'],sort_keys=True).encode()).hexdigest()
    if not manifest.exists():
        cache.mkdir(parents=True, exist_ok=False)
        vector = solution.duplicate()
        try:
            vector.array[:] = ref['x_ref']
            ref_output = recover_p0_outputs(fine, vector, cache, export_all_port_modes=True)
            files = {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in cache.iterdir() if f.is_file()}
            _atomic_json(manifest, dict(reference_sha256=reference_hash, output_identity_sha256=output_identity, outputs=ref_output, files=files))
        finally:
            vector.destroy()
    saved = json.loads(manifest.read_text())
    if saved['reference_sha256'] != reference_hash or saved.get('output_identity_sha256') != output_identity:
        raise ValueError('posterior reference output binding mismatch')
    for name,digest in saved['files'].items():
        if hashlib.sha256((cache/name).read_bytes()).hexdigest() != digest:
            raise ValueError('posterior reference output hash mismatch')
    comparisons = compare_modal_files(Path(directory)/'numerical_output', cache)
    comparisons.update(compare_power_totals(outputs,saved['outputs']))
    facts = dict(status='MATCHED_REFERENCE_PASS' if max(field.values()) <= 1e-4 and
                 comparisons['power_max_absolute_difference'] <= 1e-6 and
                 comparisons['amplitude_relative_difference'] <= 1e-4 and
                 max(comparisons['total_absolute_differences'].values()) <= 1e-5 else 'MATCHED_REFERENCE_FAIL',
                 field_relative=field, field_norms=field_norms, field_limit=1e-4, reference_sha256=reference_hash,
                 reference_output_binding=str(manifest), **comparisons)
    _atomic_json(Path(directory)/'matched_reference.json', facts)
    return facts


def compare_modal_files(current, reference):
    def key(row):
        return row['side'], row['m'], row['n'], row['polarization']
    def read(root, filename, orders=False):
        data = json.loads((root/filename).read_text())
        rows = data['orders'] if orders else data
        values = {key(x):x for x in rows}
        if len(values) != len(rows):
            raise ValueError('duplicate modal keys')
        return values
    a = read(current,'dtn_port_diffraction_orders_3d.json',True)
    b = read(reference,'dtn_port_diffraction_orders_3d.json',True)
    c = read(current,'dtn_auxiliary_amplitudes_3d.json')
    d = read(reference,'dtn_auxiliary_amplitudes_3d.json')
    if a.keys() != b.keys() or a.keys() != c.keys() or a.keys() != d.keys():
        raise ValueError('full observable mode inventory mismatch')
    def number(value):
        if isinstance(value,dict):
            return complex(value['real'],value['imag'])
        return complex(*value) if isinstance(value,list) else complex(value)
    keys = sorted(a)
    x = np.array([number(c[k]['outgoing_amplitude_at_boundary']) for k in keys])
    y = np.array([number(d[k]['outgoing_amplitude_at_boundary']) for k in keys])
    return dict(mode_count=len(keys), phase_fitting=False,amplitude_convention='outgoing_amplitude_at_boundary',
        power_max_absolute_difference=max(abs(a[k][v]-b[k][v]) for k in keys for v in ('R','T')),
        amplitude_relative_difference=float(np.linalg.norm(x-y)/max(np.linalg.norm(y),np.finfo(float).tiny)),
        power_limit=1e-6, amplitude_limit=1e-4)


def compare_notch_reference(native, solution, witness, directory):
    """After the conditional reference LU release, compare all saved outputs."""
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import recover_p0_outputs
    from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_error_diagnostics import metric_square
    from .physical_intermediate import _atomic_json
    quadrature, _ = fine_volume_quadrature_metadata(native['setup'], native['cfg'])
    metric = LosslessFEMetric(native['setup'], 6, native['cfg'].k0, quadrature)
    try:
        x = solution.array[metric.mass.indices]
        delta = witness['control']['x']-x
        field_norms = {name:dict(absolute_error_norm=float(np.sqrt(metric_square(action,delta))),
                                reference_norm=float(np.sqrt(metric_square(action,x))))
                       for name,action in [('L2',metric.mass),('scaled_curl',metric.curl)]}
        field = {name:v['absolute_error_norm']/v['reference_norm'] for name,v in field_norms.items()}
    finally:
        metric.destroy()
    output = recover_p0_outputs(native, solution, Path(directory)/'numerical_output', export_all_port_modes=True)
    comparisons = compare_modal_files(Path(witness['directory'])/'numerical_output',Path(directory)/'numerical_output')
    candidate = json.loads((Path(witness['directory'])/'physical_intermediate_summary.json').read_text())['official_result']
    comparisons.update(compare_power_totals(candidate,output))
    facts = dict(status='MATCHED_REFERENCE_PASS' if max(field.values()) <= 1e-4 and
        comparisons['power_max_absolute_difference'] <= 1e-6 and
        comparisons['amplitude_relative_difference'] <= 1e-4 and
        max(comparisons['total_absolute_differences'].values()) <= 1e-5 else 'MATCHED_REFERENCE_FAIL',
        field_relative=field, field_norms=field_norms, reference_output=output, **comparisons)
    _atomic_json(Path(directory)/'matched_reference.json',facts)
    return facts


def compare_power_totals(current, reference):
    def values(output):
        p=output['port_metrics']
        return dict(R=p['R_total'],T=p['T_total'],A=p['A_balance'],
                    A_volume=output['volume_metrics']['A_volume_total'])
    a,b=values(current),values(reference)
    return dict(total_absolute_differences={k:abs(a[k]-b[k]) for k in a},
                total_current=a,total_reference=b,total_absolute_limit=1e-5)
