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


def compare_full3d_sample_archives(candidate_directory, reference_directory):
    """Compare saved E/H grids with the direct field as reference."""
    candidate_directory=Path(candidate_directory)
    reference_directory=Path(reference_directory)
    archives=[];metadata=[]
    for directory in (candidate_directory,reference_directory):
        archive=directory/'full3d_reference_samples.npz'
        meta=json.loads((directory/'full3d_reference_samples.json').read_text())
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        if meta.get('archive')!=archive.name or meta.get('archive_sha256')!=digest:
            raise ValueError('same-coordinate E/H sample archive hash mismatch')
        metadata.append(meta)
        with np.load(archive,allow_pickle=False) as loaded:
            archives.append({key:np.array(loaded[key],copy=True) for key in loaded.files})
    candidate,reference=archives
    for name in ('x_nm','y_nm','z_nm','interface_z_nm'):
        if name not in candidate or name not in reference or not np.array_equal(candidate[name],reference[name]):
            raise ValueError('same-coordinate E/H sample grids differ: '+name)
    if metadata[0].get('interface_trace_sides')!=metadata[1].get('interface_trace_sides'):
        raise ValueError('same-coordinate E/H interface trace conventions differ')
    observables={
        'E':'E_V_per_m','H':'H_A_per_m',
        'E_t_interface':'E_t_interface_V_per_m',
        'H_t_interface':'H_t_interface_A_per_m',
    }
    relative={};absolute={};reference_norm={}
    for name,key in observables.items():
        left,right=candidate.get(key),reference.get(key)
        if left is None or right is None or left.shape!=right.shape:
            raise ValueError('same-coordinate sample observable is missing or has a different shape: '+key)
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError('same-coordinate sample observable is nonfinite: '+key)
        absolute[name]=float(np.linalg.norm(left-right))
        reference_norm[name]=float(np.linalg.norm(right))
        relative[name]=absolute[name]/max(reference_norm[name],np.finfo(float).tiny)
    return dict(candidate='G0_iterative',reference='G0_same_discrete_direct',
        sample_relative_differences=relative,sample_absolute_differences=absolute,
        sample_reference_norms=reference_norm,sample_relative_limit=1e-4,
        sample_grid_shape=metadata[1].get('array_shape_z_y_x_component'),
        sample_point_count=metadata[1].get('point_count'),
        candidate_archive_sha256=metadata[0]['archive_sha256'],
        reference_archive_sha256=metadata[1]['archive_sha256'])


def task40_energy_closure(output):
    port=output['port_metrics'];volume=output['volume_metrics']
    r=float(port['R_total']);t=float(port['T_total'])
    a_balance=float(port['A_balance']);a_volume=float(volume['A_volume_total'])
    return dict(R_plus_T_plus_A_balance_absolute=abs(r+t+a_balance-1.0),
        R_plus_T_plus_A_volume_absolute=abs(r+t+a_volume-1.0),
        A_balance_minus_A_volume_absolute=abs(a_balance-a_volume),limit=1e-5)


def task40_direct_reference_gate(field_relative,samples,modal,power,reference_energy,subject_energy):
    checks={
        'FE_L2':float(field_relative['L2'])<=1e-4,
        'FE_scaled_curl':float(field_relative['scaled_curl'])<=1e-4,
        'same_coordinate_EH':max(samples['sample_relative_differences'].values())<=1e-4,
        'modal_amplitude':float(modal['amplitude_relative_difference'])<=1e-4,
        'per_mode_power':float(modal['power_max_absolute_difference'])<=1e-6,
        'R_T_A_A_volume':max(power['total_absolute_differences'].values())<=1e-5,
        'direct_reference_energy_closure':max(
            reference_energy['R_plus_T_plus_A_balance_absolute'],
            reference_energy['R_plus_T_plus_A_volume_absolute'],
            reference_energy['A_balance_minus_A_volume_absolute'])<=1e-5,
        'G0_subject_energy_closure':max(
            subject_energy['R_plus_T_plus_A_balance_absolute'],
            subject_energy['R_plus_T_plus_A_volume_absolute'],
            subject_energy['A_balance_minus_A_volume_absolute'])<=1e-5,
    }
    return dict(status='MATCHED_REFERENCE_PASS' if all(checks.values()) else 'MATCHED_REFERENCE_FAIL',
        checks=checks,all_applicable_gates_passed=all(checks.values()))


def task40_reference_record_identity(subject_directory,reference_directory,
                                     subject_hashes,direct_identity):
    reference_keys=('source_sha','input_sha256','physical_sha256',
        'original_physical_sha256','normalized_physical_sections_sha256',
        'identity_difference','mode_sha256','expected_dimensions')
    return dict(comparison_roles=dict(subject='G0 iterative',
            reference='G0 same-discrete direct'),
        subject_run_directory=str(subject_directory),
        reference_run_directory=str(reference_directory),
        subject_hashes=subject_hashes,
        reference_identity={key:direct_identity[key] for key in reference_keys
            if key in direct_identity})


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


def compare_task40_direct_reference(native, solution, witness, directory,direct_identity):
    """Compare the direct solution with the frozen Task40 G0 discrete result."""
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import recover_p0_outputs
    from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_error_diagnostics import metric_square
    from src.solvers.condensed_fine_reference import (
        _native_vector_on_independent_rows, native_map_arrays,
    )
    from .physical_intermediate import _atomic_json

    quadrature, _ = fine_volume_quadrature_metadata(native['setup'],native['cfg'])
    metric = LosslessFEMetric(native['setup'],6,native['cfg'].k0,quadrature)
    try:
        mapping=native_map_arrays(native['setup']['spaces'][6],native['setup']['floquets'][6])
        candidate=_native_vector_on_independent_rows(
            witness['control']['x'],mapping,'G0 reference solution')
        x=solution.array[metric.mass.indices]
        delta=candidate-x
        field_norms={name:dict(absolute_error_norm=float(np.sqrt(metric_square(action,delta))),
            reference_norm=float(np.sqrt(metric_square(action,x))))
            for name,action in [('L2',metric.mass),('scaled_curl',metric.curl)]}
        field={name:value['absolute_error_norm']/value['reference_norm']
            for name,value in field_norms.items()}
    finally:
        metric.destroy()

    output_dir=Path(directory)/'numerical_output'
    output=recover_p0_outputs(native,solution,output_dir,export_all_port_modes=True)
    subject_dir=Path(witness['directory'])/'numerical_output'
    port=json.loads((subject_dir/'port_power.json').read_text())
    volume=json.loads((subject_dir/'volume_absorption.json').read_text())
    subject=dict(port_metrics=port,
        volume_metrics={'A_volume_total':volume['A_volume_total']})
    samples=compare_full3d_sample_archives(subject_dir,output_dir)
    modal=compare_modal_files(subject_dir,output_dir)
    power=compare_power_totals(subject,output)
    reference_energy=task40_energy_closure(output)
    subject_energy=task40_energy_closure(subject)
    gate=task40_direct_reference_gate(field,samples,modal,power,reference_energy,subject_energy)
    facts=dict(status=gate['status'],comparison_gates=gate,
        field_relative=field,field_norms=field_norms,field_limit=1e-4,
        sample_comparison=samples,subject_energy_closure=subject_energy,
        reference_energy_closure=reference_energy,
        subject_output=subject,reference_output=output,
        modal_comparison=modal,power_comparison=power)
    facts.update(task40_reference_record_identity(witness['directory'],directory,
        witness['evidence'],direct_identity))
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
