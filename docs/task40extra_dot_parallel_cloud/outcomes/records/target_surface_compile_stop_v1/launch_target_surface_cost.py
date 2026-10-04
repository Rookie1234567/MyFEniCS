"""External C2a selected top/x launcher; imports and preflight do no FE work.

This file is orchestration only. Numerical work is exclusively the two frozen
src APIs. A future --run needs independent launch authorization and exact real
Library receipt/seal hashes. Every failed/partial packet is retained in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import traceback
import zipfile

ROOT = Path('/workspace/scratch/9c465670b46b/task40extra_cloud/repo')
STAGE = Path(__file__).resolve().parent
HEAD = '6dba8257053c6b2e474b7808b708a745f202733b'
TREE = '63313e3f820418dc7394deced09d3db9068c6e52'
PYTHON = '../complex_env_recovery/bin/python'
CAP = 3 << 30
RESERVE = 128 << 20
WALL = 4500
METADATA_WALL = 60
METADATA_RUN = ROOT/'benchmarks/artifacts/task40extra_dot_parallel_cloud/target_AUTO_ordered_inventory_attempt1'
CORE = ROOT/'src/solvers/target_auto_surface_cost.py'
REFERENCE = ROOT/'src/solvers/target_higher_quadrature_reference.py'
CORE_SHA = '748e925d42b0da1e27240b10d47bf586173ced8ee44a93cd78ea4368a6dbae24'
REFERENCE_SHA = 'cace8b9b472b9f8b7187f4cde1d028219041483a29cfc1981f9e6801c661737a'
SUMMARY_SHA = '8b4d457080388eed9548f54bf536551c0ea40d99fdb13b9bbdf96780110583b9'
METADATA_RESULT_SHA = 'd430c7556a196c0050fcc61d15b3285f370ddc6b00486ac2190908f31d961dde'
ARCHIVE_SHA = '4c3deb139b5eb8c164c1873144685f45869c7f63b971fa05b7e969d8b0b09023'
INVENTORY_LAUNCHER_SHA = '0d5b129d5ff09abc31c2be15d4eb00427ce23790354862ff9e8d533ee5634afd'
SCHEMA = 'task40extra.selected-surface-launcher.v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def save_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    temporary.replace(path)


def byte_count(value, name):
    require(type(value) is int and value >= 0, name+' must be a nonnegative integer')
    return value


def allocation_bytes(facts):
    """Count both frozen allocation schemas; their totals alias, not add.

    Reference requested_bytes and live_named_bytes both include its workspace
    items. Use the greatest declared bound, also checking all item totals.
    Retained bytes may already occur in RSS; counting them again is conservative.
    Unknown/missing schemas fail closed and cannot become a zero-byte request.
    """
    require(isinstance(facts, dict), 'allocation facts must be a mapping')
    bounds = []
    if 'predicted_total_bytes' in facts:
        total = byte_count(facts['predicted_total_bytes'], 'predicted_total_bytes')
        buffers = facts.get('predicted_buffer_bytes')
        require(isinstance(buffers, dict) and bool(buffers), 'producer buffer declarations required')
        declared = sum(byte_count(v, k) for k, v in buffers.items())
        require(total >= declared, 'producer total understates declared buffers')
        bounds.extend((total, declared))
    if 'requested_bytes' in facts or 'live_named_bytes' in facts:
        # Both required: the reviewed reference emits both on every boundary.
        requested = byte_count(facts.get('requested_bytes'), 'requested_bytes')
        live = byte_count(facts.get('live_named_bytes'), 'live_named_bytes')
        items = facts.get('items')
        require(isinstance(items, list) and bool(items), 'reference allocation items required')
        declared = sum(byte_count(item.get('bytes'), 'reference item bytes') for item in items)
        workspace = byte_count(facts.get('workspace_estimate_bytes'), 'workspace_estimate_bytes')
        require(requested >= declared and live >= declared and workspace <= declared,
                'reference total understates items or workspace')
        bounds.extend((requested, live, declared))
    require(bool(bounds), 'unsupported allocation schema; no implicit zero-byte admission')
    return max(bounds)


def require_summary(summary, source, wall):
    require(summary.get('classification') == 'COMPLETED' and summary.get('leader_exit_code') == 0,
            'worker is not COMPLETED/exit0')
    require(summary.get('source_state') == source, 'worker source differs')
    for key in ('descendants_cleared', 'process_tree_all_status_readable',
                'process_tree_all_identity_complete', 'process_tree_swap_gate_enforced',
                'global_swap_gate_enforced', 'time_gate_evaluated'):
        require(summary.get(key) is True, 'worker resource gate missing/failed: '+key)
    require(summary.get('remaining_child_pids') == [] and
            summary.get('process_tree_identity_coverage') == 'complete' and
            summary.get('observed_child_identity_coverage') == 'complete',
            'worker child identities/cleanup incomplete')
    require(summary.get('sampled_process_tree_swap_peak_bytes') == 0,
            'worker process tree swap is not zero')
    require(summary.get('global_swap_activity', {}).get('delta') ==
            {'pswpin_pages': 0, 'pswpout_pages': 0}, 'global swap activity unresolved')
    require(summary.get('job_swap_activity') == 'zero_supported_by_zero_global_activity',
            'zero-swap attribution missing')
    rss = summary.get('sampled_process_tree_rss_peak_bytes')
    require(type(rss) is int and 0 < rss < CAP, 'worker simultaneous RSS outside 3GiB')
    elapsed = summary.get('elapsed_seconds')
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= wall,
            'worker elapsed time outside budget')
    require(summary.get('time_reference_seconds', {}).get('workflow') == wall and
            summary.get('time_policy') == 'enforce' and summary.get('timebase_policy') == 'strict' and
            summary.get('time_end_observation', {}).get('passed') is True and
            summary.get('time_exceeded') == {'workflow': False, 'solve': False, 'active_pc': False},
            'worker timebase/budget policy differs or failed')
    interval = summary.get('workflow_clock_interval', {})
    budget = interval.get('budget_seconds')
    require(type(budget) in (int, float) and math.isfinite(budget) and 0 <= budget <= wall,
            'strict clock budget missing/outside limit')
    require(summary.get('launch_envelope', {}).get('tree_cap_bytes') == CAP and
            summary.get('launch_envelope', {}).get('launch_cap_bytes') == CAP,
            'worker supervised cap differs from 3GiB')


def source_and_environment():
    sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
    from benchmarks.run_real_p4_probe import source_facts, environment_facts
    source, environment = source_facts(HEAD), environment_facts()
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT,
                                    text=True).strip() == TREE, 'source tree differs')
    require(file_sha256(CORE) == CORE_SHA and file_sha256(REFERENCE) == REFERENCE_SHA,
            'frozen numerical core/reference differs')
    require(file_sha256(STAGE/'launch_target_inventory.py') == INVENTORY_LAUNCHER_SHA,
            'metadata supervisor source differs')
    relative, running = ROOT/PYTHON, Path(environment['python'])
    require(relative.resolve() == running.resolve() and file_sha256(relative) == file_sha256(running),
            'relative child interpreter differs from qualified parent interpreter')
    require((relative.stat().st_dev, relative.stat().st_ino) ==
            (running.stat().st_dev, running.stat().st_ino), 'interpreter inode differs')
    return source, environment


def code_identity():
    return {'launcher_sha256': file_sha256(__file__), 'core_sha256': file_sha256(CORE),
            'reference_sha256': file_sha256(REFERENCE),
            'inventory_launcher_sha256': file_sha256(STAGE/'launch_target_inventory.py')}


def verify_archive(archive, manifest_path, metadata_run):
    """Stream all actual Library readback members, including preserved failures."""
    manifest = read_json(manifest_path)
    require(manifest.get('schema') == 'task40extra.complete-metadata-archive.v1' and
            manifest.get('source') == HEAD, 'metadata member manifest source/schema differs')
    members = manifest.get('members')
    require(isinstance(members, list) and len(members) == 9, 'complete nine original files required')
    paths = [m['path'] for m in members]
    require(len(set(paths)) == len(paths), 'duplicate metadata manifest member')
    total = 0
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        require(len(names) == len(set(names)) == 10 and set(names) == set(paths)|{'member_manifest.json'},
                'readback archive member set differs from complete metadata manifest')
        require(hashlib.sha256(zipped.read('member_manifest.json')).hexdigest() == file_sha256(manifest_path),
                'readback embedded member manifest differs')
        for item in members:
            relative = PurePosixPath(item['path'])
            require(not relative.is_absolute() and '..' not in relative.parts and
                    str(relative) == item['path'], 'unsafe/noncanonical archive member')
            local = (metadata_run/str(relative)).resolve()
            require(local.is_relative_to(metadata_run.resolve()), 'metadata member escapes worker directory')
            expected = byte_count(item['bytes'], 'metadata member bytes')
            require(local.is_file() and local.stat().st_size == expected and
                    file_sha256(local) == item['sha256'], 'original worker member differs: '+str(relative))
            digest, count = hashlib.sha256(), 0
            with zipped.open(item['path']) as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b''):
                    digest.update(chunk)
                    count += len(chunk)
            require(count == expected and digest.hexdigest() == item['sha256'],
                    'Library readback member bytes differ: '+str(relative))
            total += count
    require(total == manifest.get('total_bytes'), 'metadata total bytes differs')
    return {'archive_members_verified': 10, 'original_members_verified': 9,
            'original_bytes_verified': total, 'archive_sha256': file_sha256(archive),
            'member_manifest_sha256': file_sha256(manifest_path)}


def verify_metadata(args, source, environment):
    receipt_path, seal_path = args.metadata_library_receipt.resolve(), args.metadata_seal.resolve()
    require(file_sha256(receipt_path) == args.metadata_library_receipt_sha256,
            'real Library receipt differs from exact CLI hash')
    require(file_sha256(seal_path) == args.metadata_seal_sha256,
            'supplemental metadata seal differs from exact CLI hash')
    receipt, seal = read_json(receipt_path), read_json(seal_path)
    require(receipt.get('status') == 'FRESH_LIBRARY_READBACK_ALL_HASHES_PASS' and
            receipt.get('library_file_id') and receipt.get('file_id'), 'real complete Library readback receipt required')
    fixed = {'source_head': HEAD, 'source_tree': TREE, 'core_sha256': CORE_SHA,
             'reference_sha256': REFERENCE_SHA, 'worker_summary_sha256': SUMMARY_SHA,
             'worker_result_sha256': METADATA_RESULT_SHA, 'archive_sha256': ARCHIVE_SHA,
             'library_receipt_sha256': args.metadata_library_receipt_sha256,
             'library_file_id': receipt['library_file_id'], 'library_readback_verified': True}
    for key, expected in fixed.items():
        require(seal.get(key) == expected, 'supplemental seal binding differs/missing: '+key)
    require(type(seal.get('library_version')) is int and seal['library_version'] >= 0,
            'exact nonnegative Library version required')
    if 'current_version_number' in receipt:
        require(receipt['current_version_number'] == seal['library_version'], 'Library receipt version differs')
    require(receipt.get('sha256') == ARCHIVE_SHA and receipt.get('members_verified') == 10 and
            receipt.get('metadata', {}).get('source') == HEAD,
            'complete Library receipt archive/member/source identity differs')
    archive, manifest = Path(seal['archive_readback_path']).resolve(), Path(seal['member_manifest_path']).resolve()
    require(file_sha256(archive) == ARCHIVE_SHA and archive.stat().st_size == 4893317,
            'actual metadata Library full readback archive differs')
    require(os.getxattr(archive, 'user.library-file-id').decode() == seal['library_file_id'] and
            int(os.getxattr(archive, 'user.library-file-version').decode()) == seal['library_version'],
            'actual Library readback file identity/version differs')
    require(file_sha256(manifest) == seal.get('member_manifest_sha256'), 'member manifest hash differs')
    require(receipt.get('member_records') == read_json(manifest)['members'] and
            receipt.get('uncompressed_bytes') == 37626630,
            'real Library receipt full member records/bytes differ')
    summary_path, result_path = METADATA_RUN/'summary.json', METADATA_RUN/'metadata_result.json'
    require(file_sha256(summary_path) == SUMMARY_SHA and file_sha256(result_path) == METADATA_RESULT_SHA,
            'completed metadata worker summary/result differs')
    summary, result = read_json(summary_path), read_json(result_path)
    require_summary(summary, source, METADATA_WALL)
    require(result.get('passed') is True and result.get('resource_and_source_pass') is True and
            result.get('status') == 'METADATA_COMPLETE_SURFACE_NOT_RUN' and result.get('source') == source and
            result.get('environment') == environment and
            result.get('watchdog_receipt') == {'path': 'summary.json', 'sha256': SUMMARY_SHA},
            'metadata worker ABI/source/result/resource linkage differs')
    verified = verify_archive(archive, manifest, METADATA_RUN)
    from src.solvers.target_auto_surface_cost import validate_metadata_seal
    packet = validate_metadata_seal(metadata_dir=METADATA_RUN/'metadata', seal=seal)
    require(result.get('metadata_packet', {}).get('sha256') == seal['metadata_packet_sha256'],
            'metadata result packet binding differs')
    require(packet.get('fresh_mode_count') == 32060 and packet.get('max_abs_m') == 142 and
            packet.get('max_abs_n') == 35 and packet.get('quadrature_degree_from_complete_inventory') == 160,
            'frozen AUTO inventory count/order/degree differs')
    require(len(packet.get('selected_original_mode_indices', [])) == 6 and
            len(packet.get('selection_reasons', [])) == 3,
            'actual sealed six-mode/three-tuple selection differs')
    require(packet.get('mesh_calls') == packet.get('form_calls') == packet.get('jit_calls') == 0 and
            packet.get('carrier_constructed') is False and packet.get('dense_H_constructed') is False,
            'sealed metadata exceeds metadata-only scope')
    require(packet.get('sources', {}).get('staged_capsule_sha256') == CORE_SHA and
            all(source['files_sha256'].get(k) == v for k, v in
                packet['sources']['production_source_sha256'].items()), 'metadata source hashes differ')
    return seal, packet, {'receipt_path': str(receipt_path), 'receipt_sha256': args.metadata_library_receipt_sha256,
                         'seal_path': str(seal_path), 'seal_sha256': args.metadata_seal_sha256,
                         'worker_summary_sha256': SUMMARY_SHA, **verified}


def verify_surface_record(record, packet):
    require(record.get('status') == 'SELECTED_TOP_X_COMPONENT_COMPLETE' and
            record.get('scope_is_partial') is True, 'selected surface component not complete')
    for key in ('carrier_constructed', 'dense_H_constructed', 'qualified_full_C_D_or_allmode_or_outputs'):
        require(record.get(key) is False, 'surface scope flag differs: '+key)
    for key in ('volume_form_calls', 'factor_calls', 'PDE_calls'):
        require(record.get(key) == 0, 'forbidden surface operation: '+key)
    require(record.get('actual_reference_source_path') == str(REFERENCE.resolve()) and
            record.get('actual_reference_source_sha256') == REFERENCE_SHA, 'actual reference helper source differs')
    require(record.get('selected_original_mode_indices') == packet['selected_original_mode_indices'],
            'selected original indices differ')
    for key, saved in (('physical_manifest_sha256', 'original_physical_manifest_sha256'),
                       ('ordered_keys_sha256', 'ordered_keys_sha256'), ('config_sha256', 'config_sha256')):
        require(record.get(key) == packet[saved], 'surface metadata identity differs: '+key)
    comparison = record.get('raw_vs_public_eval_reference', {})
    require(comparison.get('passed') is True and comparison.get('relative_limit') == 1e-10 and
            comparison.get('exact_zero_rule') is True and comparison.get('entry_passed') and
            all(all(row) for row in comparison['entry_passed']), 'primary action comparison failed')
    reference = record.get('independent_reference', {})
    require(reference.get('reference_convergence_pass') is True and
            reference.get('reference_increments') == [8, 16] and reference.get('primary_degree') == 160 and
            reference.get('operation_rtol') == 1e-10 and reference.get('no_numerical_denominator_floor') is True and
            reference.get('build_mesh_space_form_mode_carrier_factor_PDE_calls') == 0,
            'public eval reference convergence/scope failed')
    require(reference.get('selected_indices') == packet['selected_original_mode_indices'] and
            len(reference.get('convergence_metrics', [])) == 3*len(packet['selected_original_mode_indices']) and
            all(row.get('passed') is True for row in reference['convergence_metrics']),
            'reference convergence coverage differs')
    rules = reference.get('rules', [])
    expected_nodes = [((r['degree']+2)//2)**2 for r in rules]
    require(len(rules) == 2 and [r.get('degree') for r in rules] == [168, 176] and
            [r.get('actual_nodes_per_facet') for r in rules] == expected_nodes == [7225, 7921] and
            all(r.get('actual_total_geometric_points') == 6*r['actual_nodes_per_facet'] and
                r.get('field_point_evaluations') == 18*r['actual_nodes_per_facet'] and
                r.get('distinct_phase_tuples') == len(packet['selection_reasons']) and
                r.get('three_states_nonzero_actual_top_x_trace') == [True, True, True] for r in rules) and
            len(reference.get('facet_rectangles', [])) == 6,
            'actual higher quadrature rule/native state checks differ')
    native = reference.get('state_identity', {})
    require(native.get('slave_slots_zero') is True and native.get('constraint_equations_checked', 0) > 0 and
            native.get('master_state_sha256') and native.get('global_numbering_sha256') and
            native.get('cell_dof_order_sha256'), 'native/MPC reference identity missing')
    require(record.get('fixture_complete') is True and record.get('native_discrete_identity') and
            record.get('primary_compiled_gauss_loaded_binary_Constant_pack') and
            record.get('primary_compiled_artifacts'), 'native/compiled-Gauss primary identity missing')
    primary_rules = record['primary_compiled_gauss_loaded_binary_Constant_pack'].get('rules', [])
    loaded_kernel = record['primary_compiled_gauss_loaded_binary_Constant_pack'].get('loaded_kernel', {})
    primary_nodes = ((packet['quadrature_degree_from_complete_inventory']+2)//2)**2
    require(primary_rules and primary_nodes == 6561 and
            all(r.get('degree') == 160 and r.get('points', {}).get('shape', [None])[0] == primary_nodes and
                r.get('weights', {}).get('shape') == [primary_nodes] and
                r.get('compiled_weight_tables_verified', 0) > 0 for r in primary_rules),
            'actual primary compiled quadrature rule count/identity differs')
    require(loaded_kernel.get('restoration_exact') is True and loaded_kernel.get('num_constants') == 3 and
            loaded_kernel.get('numerical_assembly_during_probe') is False and
            {r.get('role') for r in loaded_kernel.get('constant_roles', [])} == {'alpha', 'gamma', 'kz'},
            'actual primary loaded binary/Constant pack identity differs')
    components = record.get('selected_components', [])
    require(len(components) == len(packet['selected_original_mode_indices']) and
            [c.get('original_mode_index') for c in components] == packet['selected_original_mode_indices'] and
            all(c.get('existing_mask_equals_raw_unchanged_cutoff') is True for c in components),
            'raw/mask selected component coverage failed')
    require([c.get('original_mode_key') for c in components] == packet['selected_original_keys'],
            'raw/mask original key identity differs')


def check_saved_artifacts(record, output_dir):
    """Verify persisted primary/native/raw/masked/reference member descriptors."""
    descriptors = [*record['primary_compiled_artifacts'].values(), *record['state_artifacts'].values(),
                   *record['contraction_artifacts'].values()]
    for component in record['selected_components']:
        descriptors.extend(component['artifacts'].values())
    for descriptor in descriptors:
        path = Path(descriptor['path']).resolve()
        require(path.is_relative_to(output_dir.resolve()) and path.is_file() and
                path.stat().st_size == descriptor['bytes'] and file_sha256(path) == descriptor['sha256'],
                'persisted surface member path/bytes/hash differs')
    return len(descriptors)


def verify_saved_actions(record, packet, output_dir, gate):
    """Tiny saved-only recheck; no FE calls and no change to recorded values."""
    gate('saved_only_6x3_action_comparison', {
        'predicted_total_bytes': 1 << 20,
        'predicted_buffer_bytes': {'saved_scalar_arrays_differences_JSON_workspace': 1 << 20}})
    import numpy as np
    from src.solvers.target_auto_surface_cost import reference_action_gate, jsonable
    from src.solvers.target_higher_quadrature_reference import operation_scaled_difference
    arrays = {}
    names = ('primary_raw_contractions', 'contractions_degree_plus8',
             'contractions_degree_plus16', 'operation_scales_degree_plus16')
    shape = (len(packet['selected_original_mode_indices']), 3)
    for name in names:
        descriptor = record['contraction_artifacts'][name]
        path = Path(descriptor['path']).resolve()
        require(path.is_relative_to(output_dir.resolve()) and file_sha256(path) == descriptor['sha256'],
                'saved scalar action member hash/path differs')
        expected_dtype = np.dtype(np.float64) if name.startswith('operation_scales') else np.dtype(np.complex128)
        require(path.stat().st_size == descriptor['bytes'] and path.stat().st_size < (1 << 20),
                'saved scalar action exact file bytes exceed admitted bound')
        with path.open('rb') as stream:
            version = np.lib.format.read_magic(stream)
            require(version in ((1, 0), (2, 0)), 'unsupported scalar NPY header version')
            reader = (np.lib.format.read_array_header_1_0 if version == (1, 0)
                      else np.lib.format.read_array_header_2_0)
            header_shape, fortran, dtype = reader(stream, max_header_size=4096)
            require(header_shape == shape and fortran is False and dtype == expected_dtype and
                    dtype.isnative and not dtype.hasobject and
                    stream.tell()+shape[0]*shape[1]*dtype.itemsize == path.stat().st_size,
                    'saved scalar NPY header shape/dtype/layout/payload differs before load')
        value = np.load(path, allow_pickle=False)
        require(value.shape == shape and np.isfinite(value).all() and
                value.dtype == expected_dtype,
                'saved scalar action shape/dtype/finite identity differs')
        arrays[name] = value
    scales = arrays['operation_scales_degree_plus16']
    primary = reference_action_gate(arrays['primary_raw_contractions'], arrays['contractions_degree_plus16'], scales)
    require(primary['passed'] and jsonable(primary) == record['raw_vs_public_eval_reference'],
            'saved primary/public-eval action comparison differs or fails')
    convergence = []
    for j, index in enumerate(packet['selected_original_mode_indices']):
        for k in range(3):
            metric = operation_scaled_difference(arrays['contractions_degree_plus8'][j, k],
                                                 arrays['contractions_degree_plus16'][j, k], scales[j, k])
            convergence.append({'selected_mode_index': j, 'inventory_index': index, 'state_index': k, **metric})
    require(all(m['passed'] for m in convergence) and
            convergence == record['independent_reference']['convergence_metrics'],
            'saved +8/+16 reference convergence differs or fails')
    return {'passed': True, 'comparison_entries': shape[0]*shape[1], 'relative_limit': 1e-10,
            'exact_zero_rule': True, 'primary_comparison_recomputed': True,
            'reference_convergence_recomputed': True, 'saved_original_values_unchanged': True,
            'FE_mesh_form_JIT_assembly_calls': 0}


def runtime_preflight(args):
    require(Path.cwd().resolve() == ROOT, 'launcher requires the frozen repository cwd')
    run = args.run_directory.resolve()
    artifacts = ROOT/'benchmarks/artifacts/task40extra_dot_parallel_cloud'
    require(run.is_relative_to(artifacts) and run != artifacts and not run.exists() and
            not METADATA_RUN.is_relative_to(run), 'fresh separate ignored surface run directory required')
    source, environment = source_and_environment()
    code = code_identity()
    from benchmarks.subreaper_watchdog import memory_envelope
    envelope = memory_envelope()
    require(envelope['launch_cap_bytes'] >= CAP+RESERVE and shutil.disk_usage(ROOT).free >= 2 << 30,
            'fresh physical headroom or disk reserve insufficient')
    child = subprocess.run([PYTHON, '-c', 'import json; from benchmarks.run_real_p4_probe import environment_facts; print("ENV="+json.dumps(environment_facts()))'],
                           cwd=ROOT, text=True, capture_output=True)
    rows = [row for row in child.stdout.splitlines() if row.startswith('ENV=')]
    require(child.returncode == 0 and len(rows) == 1 and json.loads(rows[0][4:]) == environment,
            'parent/relative child environment equality failed')
    seal, packet, metadata = verify_metadata(args, source, environment)
    require(source_and_environment() == (source, environment) and code_identity() == code,
            'preflight source/ABI/wrapper/core/reference changed')
    return {'schema': SCHEMA, 'status': 'SOURCE_ABI_METADATA_LIBRARY_RESOURCE_PREFLIGHT_ONLY_PASS',
            'source': source, 'source_tree': TREE, 'environment': environment, 'code': code,
            'metadata': metadata, 'metadata_seal': seal, 'memory_envelope': envelope,
            'run_directory': str(run), 'parent_child_environment_equal': True,
            'policy': {'whole_tree_cap_bytes': CAP, 'allocation_reserve_bytes': RESERVE, 'wall_seconds': WALL,
                       'MPI': 1, 'threads': 1, 'zero_swap': True, 'immediate_stop': True,
                       'strict_timebase': True, 'global_swap_gate': True},
            'mode_generation_mesh_form_JIT_assembly_carrier_H_qspace_volume_factor_PDE_calls': 0,
            'surface_executed': False}, packet


def child_run(args):
    run = args.run_directory.resolve()
    result = {'schema': SCHEMA, 'status': 'SURFACE_CHILD_FAILED_OR_PARTIAL', 'passed': False}
    try:
        require(Path.cwd().resolve() == ROOT, 'child cwd differs')
        parent = int(os.environ.get('PHYSICAL_WATCHDOG_PARENT_PID', '0'))
        require(parent == os.getppid() and parent > 0 and
                int(os.environ.get('PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES', '0')) == CAP,
                'child lacks exact whole-tree watchdog parent/cap')
        source, environment = source_and_environment()
        code = code_identity()
        preflight_path = Path(os.environ['TARGET_SURFACE_PREFLIGHT_PATH'])
        require(file_sha256(preflight_path) == os.environ['TARGET_SURFACE_PREFLIGHT_SHA256'],
                'parent preflight file changed')
        shutil.copyfile(preflight_path, run/'launch_preflight.json')
        admitted = read_json(run/'launch_preflight.json')
        require(admitted['source'] == source and admitted['environment'] == environment and
                admitted['code'] == code, 'source/parent/child environment/code equality failed')
        result.update(source=source, environment=environment, code=code)
        from src.solvers.target_auto_surface_cost import run_surface_stage, jsonable
        from src.solvers.target_higher_quadrature_reference import run_reference
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        seal, packet, metadata = verify_metadata(args, source, environment)
        require(metadata == admitted['metadata'] and seal == admitted['metadata_seal'],
                'metadata receipt/seal changed between parent and child')
        require(source_and_environment() == (source, environment) and code_identity() == code,
                'source/ABI/code changed before mesh entry')

        def event(record):
            converted = jsonable(record)
            with (run/'surface_events.jsonl').open('a') as stream:
                stream.write(json.dumps({'monotonic': time.monotonic(), 'record': converted},
                                        sort_keys=True, allow_nan=False)+'\n')
            save_json(run/'phase.json', {'phase': converted.get('stage', converted.get('kind', 'surface')),
                                        'application_worker': {'pid': os.getpid()},
                                        'last_event_monotonic': time.monotonic()})

        def gate(label, facts):
            payload = allocation_bytes(facts)
            sample = process_tree_snapshot(parent, label, None, pss_sampling_policy='disabled_by_profile')
            require(sample['all_status_readable'] and sample['identity_complete'] and sample['swap_bytes'] == 0,
                    'allocation tree identities/readability/zeroSwap failed')
            rss = byte_count(sample['rss_bytes'], 'measured tree RSS')
            total = rss+payload+RESERVE
            event({'stage': 'launcher_allocation_gate', 'label': label, 'predicted_additional_bytes': payload,
                   'measured_current_whole_tree_RSS_bytes': rss, 'reserve_bytes': RESERVE,
                   'admission_total_bytes': total, 'cap_bytes': CAP, 'passed': total < CAP, 'facts': facts})
            if total >= CAP:
                raise MemoryError('measured whole-tree RSS + declared allocation + 128MiB reserve reaches 3GiB')
            return True

        output, cache = run/'surface', run/'primary_jit_cache'
        require(not output.exists() and not cache.exists(), 'fresh output/JIT cache required')
        event({'stage': 'all_external_metadata_source_ABI_resource_gates_bound_before_mesh',
               'metadata': metadata, 'code': code})
        produced = run_surface_stage(repo_root=ROOT, metadata_dir=METADATA_RUN/'metadata', metadata_seal=seal,
                                     output_dir=output, cache_dir=cache, allocation_gate=gate, event=event,
                                     reference_helper=run_reference)
        record = produced['record']
        verify_surface_record(record, packet)
        require(file_sha256(output/'surface_record.json') == produced['surface_record']['sha256'],
                'surface terminal packet hash differs')
        saved_members = check_saved_artifacts(record, output)
        saved_actions = verify_saved_actions(record, packet, output, gate)
        require(source_and_environment() == (source, environment) and code_identity() == code,
                'post-child source/ABI/wrapper/core/reference changed')
        result.update(status='SELECTED_TOP_X_SURFACE_CHILD_PASS', passed=True,
                      metadata=metadata, surface_record=produced['surface_record'],
                      saved_members_hash_verified=saved_members, saved_only_action_checks=saved_actions,
                      scope='selected top/x component only')
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        traceback.print_exc()
    save_json(run/'launcher_child_result.json', result)
    return 0 if result['passed'] else 2


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=('preflight', 'run'), required=True)
    p.add_argument('--metadata-library-receipt', type=Path, required=True)
    p.add_argument('--metadata-library-receipt-sha256', required=True)
    p.add_argument('--metadata-seal', type=Path, required=True)
    p.add_argument('--metadata-seal-sha256', required=True)
    p.add_argument('--run-directory', type=Path, required=True)
    p.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.child:
        require(args.stage == 'run', 'child accepts only admitted run stage')
        return child_run(args)
    timestamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())+'_'+str(os.getpid())
    diagnostic = STAGE/('surface_launcher_preflight_'+timestamp+'.json')
    try:
        preflight, packet = runtime_preflight(args)
        save_json(diagnostic, preflight)
        if args.stage == 'preflight':
            print(json.dumps({'status': preflight['status'], 'receipt_path': str(diagnostic),
                              'receipt_sha256': file_sha256(diagnostic), 'surface_executed': False}))
            return 0
        from benchmarks.subreaper_watchdog import supervise
        run = args.run_directory.resolve()
        # supervise owns fresh run-directory creation; child verifies/copies
        # the exact parent preflight before any numerical API call.
        command = [PYTHON, str(Path(__file__).resolve()), '--stage', 'run', '--child',
                   '--metadata-library-receipt', str(args.metadata_library_receipt.resolve()),
                   '--metadata-library-receipt-sha256', args.metadata_library_receipt_sha256,
                   '--metadata-seal', str(args.metadata_seal.resolve()),
                   '--metadata-seal-sha256', args.metadata_seal_sha256,
                   '--run-directory', str(run)]
        # The manifest is passed through the environment using a read-only
        # parent-owned file. No numerical data or credentials are serialized.
        summary = supervise(command, run, wall_seconds=WALL, interval=.25, grace_seconds=2,
                            source_state=preflight['source'], phase_path=run/'phase.json', tree_cap_bytes=CAP,
                            hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
                            pss_sampling_policy='disabled_by_profile',
                            worker_environment={'TARGET_SURFACE_PREFLIGHT_PATH': str(diagnostic),
                                                'TARGET_SURFACE_PREFLIGHT_SHA256': file_sha256(diagnostic)})
        terminal = {'schema': SCHEMA, 'passed': False, 'status': 'SURFACE_LAUNCH_FAILED_OR_PARTIAL',
                    'preflight': {'path': str(diagnostic), 'sha256': file_sha256(diagnostic)},
                    'watchdog_receipt': {'path': 'summary.json', 'sha256': file_sha256(run/'summary.json')},
                    'scope': 'selected top/x component only; no target/full-C-D/PDE qualification'}
        try:
            require_summary(summary, preflight['source'], WALL)
            require(source_and_environment() == (preflight['source'], preflight['environment']) and
                    code_identity() == preflight['code'], 'post-supervision source/ABI/code changed')
            result = read_json(run/'launcher_child_result.json')
            require(result.get('passed') is True and result.get('status') == 'SELECTED_TOP_X_SURFACE_CHILD_PASS' and
                    result.get('source') == preflight['source'] and result.get('environment') == preflight['environment'] and
                    result.get('code') == preflight['code'], 'child result/identity gates failed')
            record = read_json(run/'surface/surface_record.json')
            verify_surface_record(record, packet)
            require(file_sha256(run/'surface/surface_record.json') == result['surface_record']['sha256'],
                    'post-supervision terminal surface hash differs')
            def saved_gate(label, facts):
                from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
                sample = process_tree_snapshot(os.getpid(), label, None, pss_sampling_policy='disabled_by_profile')
                require(sample['all_status_readable'] and sample['identity_complete'] and sample['swap_bytes'] == 0,
                        'saved-only parent tree readability/identity/zeroSwap failed')
                payload = allocation_bytes(facts)
                require(sample['rss_bytes']+payload+RESERVE < CAP, 'saved-only comparison exceeds 3GiB reserve policy')
                save_json(run/'saved_only_parent_allocation.json', {'label': label,
                    'current_tree_RSS_bytes': sample['rss_bytes'], 'predicted_additional_bytes': payload,
                    'cap_bytes': CAP, 'reserve_bytes': RESERVE})
                return True
            saved_actions = verify_saved_actions(record, packet, run/'surface', saved_gate)
            require(source_and_environment() == (preflight['source'], preflight['environment']) and
                    code_identity() == preflight['code'], 'final post-check source/ABI/code changed')
            terminal.update(passed=True, status='SELECTED_TOP_X_SURFACE_RESOURCE_SOURCE_PASS',
                            surface_record=result['surface_record'], saved_only_action_checks=saved_actions,
                            child_result_sha256=file_sha256(run/'launcher_child_result.json'))
        except BaseException as error:
            terminal.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        save_json(run/'launcher_terminal_result.json', terminal)
        print(json.dumps({'status': terminal['status'], 'passed': terminal['passed'],
                          'seconds': summary.get('elapsed_seconds'),
                          'whole_tree_RSS_peak_bytes': summary.get('sampled_process_tree_rss_peak_bytes')}))
        return 0 if terminal['passed'] else 2
    except BaseException as error:
        save_json(STAGE/('surface_launcher_failure_'+timestamp+'.json'),
                  {'schema': SCHEMA, 'passed': False, 'stage': args.stage, 'run_directory': str(args.run_directory),
                   'error_type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc(),
                   'partial_evidence_retained': True})
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
