"""External C2a chunked selected top/x launcher; imports and preflight do no FE work.

This file is orchestration only. The original target core/reference stay frozen;
reviewed external native helper and runner implement only the selected experiment. A future --run needs independent launch authorization and exact real
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
CANONICAL_REFERENCE = ROOT/'src/solvers/target_higher_quadrature_reference.py'
CANONICAL_REFERENCE_SHA = 'cace8b9b472b9f8b7187f4cde1d028219041483a29cfc1981f9e6801c661737a'
REFERENCE = STAGE/'chunked_native/target_higher_quadrature_reference_mass_v2.py'
CORE_SHA = '748e925d42b0da1e27240b10d47bf586173ced8ee44a93cd78ea4368a6dbae24'
REFERENCE_SHA = 'a0af0fc4838f08af3236c926e383ff84a09ee69c0965c19693a2950a6de44094'
SUMMARY_SHA = '8b4d457080388eed9548f54bf536551c0ea40d99fdb13b9bbdf96780110583b9'
METADATA_RESULT_SHA = 'd430c7556a196c0050fcc61d15b3285f370ddc6b00486ac2190908f31d961dde'
ARCHIVE_SHA = '4c3deb139b5eb8c164c1873144685f45869c7f63b971fa05b7e969d8b0b09023'
INVENTORY_LAUNCHER_SHA = '0d5b129d5ff09abc31c2be15d4eb00427ce23790354862ff9e8d533ee5634afd'
SCHEMA = 'task40extra.chunked-selected-surface-launcher.v1'
CHUNKED_HELPER = STAGE/'chunked_native/target_chunked_surface_vector_mass_v2.py'
CHUNKED_RUNNER = STAGE/'chunked_native/run_chunked_surface_cost_mass_v2.py'
CHUNKED_SHA = 'dff5871b767ed25ecd1500e0433cdc914773c013a46521d4c2bc3a4b0a37bef8'
RUNNER_SHA = '3705674a56b9f4e7afe0b5ff77215ee5180cd397d39e20f1f70423d888ea7683'


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
    require(file_sha256(CORE) == CORE_SHA and file_sha256(REFERENCE) == REFERENCE_SHA and
            file_sha256(CANONICAL_REFERENCE) == CANONICAL_REFERENCE_SHA,
            'frozen numerical core/reference differs')
    require(file_sha256(STAGE/'launch_target_inventory.py') == INVENTORY_LAUNCHER_SHA,
            'metadata supervisor source differs')
    relative, running = ROOT/PYTHON, Path(environment['python'])
    require(relative.resolve() == running.resolve() and file_sha256(relative) == file_sha256(running),
            'relative child interpreter differs from qualified parent interpreter')
    require((relative.stat().st_dev, relative.stat().st_ino) ==
            (running.stat().st_dev, running.stat().st_ino), 'interpreter inode differs')
    require(file_sha256(CHUNKED_HELPER) == CHUNKED_SHA and file_sha256(CHUNKED_RUNNER) == RUNNER_SHA, 'external chunked helper/runner differs')
    return source, environment


def code_identity():
    return {'launcher_sha256': file_sha256(__file__), 'core_sha256': file_sha256(CORE),
            'reference_sha256': file_sha256(REFERENCE),
            'canonical_reference_sha256': file_sha256(CANONICAL_REFERENCE),
            'inventory_launcher_sha256': file_sha256(STAGE/'launch_target_inventory.py'),
            'chunked_helper_sha256': file_sha256(CHUNKED_HELPER),
            'chunked_runner_sha256': file_sha256(CHUNKED_RUNNER)}


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
             'reference_sha256': CANONICAL_REFERENCE_SHA, 'worker_summary_sha256': SUMMARY_SHA,
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
    require(record.get('status') == 'CHUNKED_SELECTED_TOP_X_COMPLETE', 'chunked selected component incomplete')
    require(record.get('scope_is_partial') is True, 'partial qualification scope missing')
    for key in ('carrier_constructed', 'dense_H_constructed', 'qualified_full_C_D_or_allmode_or_outputs'):
        require(record.get(key) is False, 'forbidden scope flag: '+key)
    for key in ('volume_form_calls', 'factor_calls', 'PDE_calls'):
        require(record.get(key) == 0, 'forbidden operation: '+key)
    require(record.get('selected_original_mode_indices') == packet['selected_original_mode_indices'], 'selected inventory differs')
    for key, saved in (('physical_manifest_sha256', 'original_physical_manifest_sha256'),
                       ('ordered_keys_sha256', 'ordered_keys_sha256'), ('config_sha256', 'config_sha256')):
        require(record.get(key) == packet[saved], 'chunked metadata identity differs: '+key)
    require(record.get('actual_reference_source_path') == str(REFERENCE.resolve()) and
            record.get('actual_reference_source_sha256') == REFERENCE_SHA, 'reference identity differs')
    require(record.get('actual_chunked_source_path') == str(CHUNKED_HELPER.resolve()) and
            record.get('actual_chunked_source_sha256') == CHUNKED_SHA, 'chunked provider identity differs')
    require(record.get('actual_runner_source_path') == str(CHUNKED_RUNNER.resolve()) and
            record.get('actual_runner_source_sha256') == RUNNER_SHA, 'external runner identity differs')
    native = record.get('native_discrete_identity', {})
    require(native and record.get('actual_native_storage_rows') == 13224, 'actual native fixture row count differs')
    mechanism = record.get('mechanism_comparisons', [])
    require(len(mechanism) == 6 and [x.get('original_mode_index') for x in mechanism] == packet['selected_original_mode_indices'], 'mechanism mode coverage differs')
    require(record.get('mechanism_passed') is True and all(x.get('passed') is True for x in mechanism), 'mechanism raw/mask equivalence failed')
    identity = record.get('mechanism_compiled_gauss_loaded_binary_Constant_pack', {})
    require(identity.get('loaded_kernel') and identity.get('rules') and all(x.get('degree') == 27 and
            x.get('points', {}).get('shape', [None])[0] == 196 and
            x.get('weights', {}).get('shape') == [196] and x.get('compiled_weight_tables_verified', 0) > 0
            for x in identity['rules']), 'mechanism loaded degree27 Gauss proof missing')
    loaded=identity['loaded_kernel']
    require(loaded.get('restoration_exact') is True and loaded.get('num_constants')==3 and
            [x.get('role') for x in loaded.get('constant_roles',[])]==['alpha','gamma','kz'] and
            loaded.get('numerical_assembly_during_probe') is False, 'mechanism loaded Constant-pack/restoration identity differs')
    target = record.get('target_chunked_record', {})
    require(target.get('quadrature_degree') == 160, 'original target quadrature changed')
    require(target.get('owned_workspace_admission_maximum_bytes', 1<<62) <= 128<<20, 'owned helper workspace bound exceeded')
    require(target.get('actual_nodes_per_facet') == 6561 and target.get('native_rows') == 13224 and
            target.get('default_gauss_points_weights_byte_equal') is True and
            target.get('basis_values_unthresholded') is True and target.get('FFCx_byte_equivalence_claimed') is False and
            target.get('mesh_space_form_JIT_factor_PDE_creation_calls') == 0 and
            target.get('selected_original_mode_indices') == packet['selected_original_mode_indices'], 'target native/rule/provider scope differs')
    selected_components=target.get('selected_components',[])
    require(len(selected_components)==6 and [x.get('original_mode_key') for x in selected_components]==packet['selected_original_keys'] and
            all(x.get('exact_slave_zero') is True and x.get('existing_mask_equals_own_raw_unchanged_cutoff') is True for x in selected_components),
            'target complete raw/native slave/mask coverage missing')
    reference = record.get('independent_reference', {})
    require(reference.get('reference_convergence_pass') is True and reference.get('reference_increments') == [8,16] and
            reference.get('primary_degree') == 160 and reference.get('operation_rtol') == 1e-10 and
            reference.get('no_numerical_denominator_floor') is True and
            reference.get('selected_indices') == packet['selected_original_mode_indices'] and
            reference.get('build_mesh_space_form_mode_carrier_factor_PDE_calls') == 0, 'higher reference failed or scope changed')
    require(len(reference.get('convergence_metrics', [])) == 18 and all(x.get('passed') is True for x in reference['convergence_metrics']), 'reference convergence coverage failed')
    rules = reference.get('rules', [])
    require(len(rules) == 2 and [x.get('degree') for x in rules] == [168,176] and
            [x.get('actual_nodes_per_facet') for x in rules] == [7225,7921] and
            all(x.get('actual_total_geometric_points') == 6*x['actual_nodes_per_facet'] and
                x.get('three_states_nonzero_actual_top_x_trace') == [True,True,True] and
                x.get('field_point_evaluations')==18*x['actual_nodes_per_facet'] and
                x.get('distinct_phase_tuples')==3 for x in rules) and len(reference.get('facet_rectangles',[]))==6, 'higher rule/native coverage changed')
    native_reference=reference.get('state_identity',{})
    require(native_reference.get('slave_slots_zero') is True and native_reference.get('constraint_equations_checked',0)>0 and
            native_reference.get('master_state_sha256') and native_reference.get('global_numbering_sha256') and
            native_reference.get('cell_dof_order_sha256'), 'reference actual native/slave/ordering identities missing')
    for mass in [target.get('unit_mass_metric',{})]+[x.get('unit_mass_metric',{}) for x in rules]:
        require(mass.get('passed') is True and mass.get('absolute_limit')==1e-12 and
                mass.get('finite_weights') is True and mass.get('positive_weights') is True and
                mass.get('finite_mass') is True and mass.get('weights_normalized') is False and
                mass.get('construction_error_theorem_claimed') is False, 'auxiliary constant-function accuracy failed or policy changed')
    for policy in [target.get('unit_mass_policy',{})]+[x.get('unit_mass_policy',{}) for x in rules]:
        require(policy.get('absolute_limit')==1e-12 and policy.get('fraction_of_unchanged_1e_minus10_action_budget')==0.01 and
                policy.get('weights_normalized') is False and policy.get('construction_error_theorem_claimed') is False and
                policy.get('independent_official_SciPy_witness_sha256')=='257f62d2dfd98afe804a1451c9c18f170df7dbcad7b15e0ff127c6b65146a774', 'auxiliary policy/witness identity differs')
    comparison = record.get('raw_vs_public_eval_reference', {})
    require(comparison.get('passed') is True and comparison.get('relative_limit') == 1e-10 and
            comparison.get('exact_zero_rule') is True and all(all(row) for row in comparison.get('entry_passed',[])), 'target integral action comparison failed')


def descriptor_items(value):
    if isinstance(value, dict):
        if {'path','bytes','sha256'} <= value.keys():
            yield value
        else:
            for item in value.values(): yield from descriptor_items(item)
    elif isinstance(value, (tuple,list)):
        for item in value: yield from descriptor_items(item)


def check_saved_artifacts(record, output_dir):
    descriptors = []
    for key in ('mechanism_compiled_artifacts', 'state_artifacts', 'contraction_artifacts',
                'mechanism_chunked_artifacts', 'target_chunked_artifacts'):
        require(record.get(key), 'required saved artifact group missing: '+key)
        descriptors.extend(descriptor_items(record[key]))
    for item in record.get('mechanism_comparisons',[]):
        require(item.get('row_difference_artifacts'), 'mask row difference witnesses missing')
        descriptors.extend(descriptor_items(item['row_difference_artifacts']))
    for item in record.get('mechanism_ffcx_components',[]):
        require(item.get('artifacts'), 'FFCx mechanism raw arrays missing')
        descriptors.extend(descriptor_items(item['artifacts']))
    require(len(record.get('mechanism_ffcx_components',[])) == 6, 'all six FFCx mechanisms required')
    seen = set()
    for descriptor in descriptors:
        path = Path(descriptor['path']).resolve()
        require(path.is_relative_to(output_dir.resolve()) and path.is_file() and
                path.stat().st_size == descriptor['bytes'] and file_sha256(path) == descriptor['sha256'],
                'persisted chunked/mechanism member differs')
        seen.add(str(path))
    return len(seen)


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


def verify_saved_mechanism(record, packet, output_dir, allocation_gate):
    import numpy as np
    rows = record['actual_native_storage_rows']
    require(rows == 13224, 'saved raw replay requires actual fixed native rows')
    allocation_gate('saved_complete_mechanism_arrays_before_header_and_mmap',
                    {'predicted_total_bytes': 64<<20,
                     'predicted_buffer_bytes': {'bounded_mapped_arrays_scalar_metrics_and_header_IO':64<<20}})
    def load(descriptor, shape, dtype):
        path=Path(descriptor['path']).resolve(); expected=np.dtype(dtype)
        require(path.is_relative_to(output_dir.resolve()) and path.is_file() and
                path.stat().st_size==descriptor['bytes'] and file_sha256(path)==descriptor['sha256'],
                'saved mechanism member hash/path differs')
        with path.open('rb') as stream:
            version=np.lib.format.read_magic(stream)
            require(version in ((1,0),(2,0)), 'unsupported NPY header version')
            reader=np.lib.format.read_array_header_1_0 if version==(1,0) else np.lib.format.read_array_header_2_0
            actual_shape,fortran,actual_dtype=reader(stream,max_header_size=10000)
            require(tuple(actual_shape)==tuple(shape) and actual_dtype==expected and not fortran and
                    not actual_dtype.hasobject and stream.tell()+int(np.prod(shape))*expected.itemsize==path.stat().st_size,
                    'saved mechanism NPY header/shape/dtype/size differs before mmap')
        value=np.load(path,mmap_mode='r',allow_pickle=False)
        require(np.isfinite(value).all(), 'nonfinite saved mechanism array')
        return value
    candidates=record['mechanism_chunked_artifacts']
    new_fe=load(candidates['b_FE'],(6,rows),np.complex128)
    new_mpc=load(candidates['raw_MPC'],(6,rows),np.complex128)
    new_masked=load(candidates['masked_full'],(6,rows),np.complex128)
    def compare(left,right):
        def stable_norm(magnitudes):
            maximum=float(np.max(magnitudes,initial=0.0))
            return 0.0 if maximum==0 else maximum*float(np.sqrt(np.sum((magnitudes/maximum)**2)))
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            error=stable_norm(np.abs(left-right));l=stable_norm(np.abs(left));r=stable_norm(np.abs(right))
        require(all(math.isfinite(x) and x>=0 for x in (error,l,r)), 'nonfinite fullraw norm')
        passed=(error==0 if l==0 else error<=1e-11*l) and (error==0 if r==0 else error<=1e-11*r)
        return {'error_l2':error,'left_norm_l2':l,'right_norm_l2':r,'relative_limit':1e-11,'passed':bool(passed)}
    def mask_identity(raw,full):
        cutoff=max(1e-30,1e-13*float(np.max(np.abs(raw),initial=0.0)))
        selected=np.abs(raw)>cutoff
        require(np.array_equal(full[selected],raw[selected]) and np.all(full[~selected]==0),
                'saved own mask changed cutoff/raw coefficients')
        return {'cutoff':cutoff,'selected_rows':int(np.count_nonzero(selected))}
    result=[]
    for i,component in enumerate(record['mechanism_ffcx_components']):
        require(component['original_mode_index']==packet['selected_original_mode_indices'][i], 'FFCx mechanism original index differs')
        artifacts=component['artifacts']; old_fe=load(artifacts['b_FE'],(rows,),np.complex128)
        old_mpc=load(artifacts['raw_MPC'],(rows,),np.complex128)
        old_masked=load(artifacts['masked_full'],(rows,),np.complex128)
        checks={'b_FE':compare(old_fe,new_fe[i]),'raw_MPC':compare(old_mpc,new_mpc[i]),
                'masked_full':compare(old_masked,new_masked[i])}
        require(all(x['passed'] for x in checks.values()), 'saved fullraw FE/MPC/masked mechanism equivalence failed')
        checks['FFCx_own_mask']=mask_identity(old_mpc,old_masked)
        checks['chunked_own_mask']=mask_identity(new_mpc[i],new_masked[i])
        result.append({'original_mode_index':component['original_mode_index'],'checks':checks})
        del old_fe,old_mpc,old_masked
    del new_fe,new_mpc,new_masked
    return {'passed':True,'complete_native_vectors_replayed':18,'comparisons':result,
            'scope':'mechanism degree27 equivalence only; not target accuracy'}


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
        from src.solvers.target_auto_surface_cost import jsonable
        import importlib.util
        def load_external(name, path):
            spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module
        runner=load_external('frozen_chunked_surface_runner',CHUNKED_RUNNER)
        helper=load_external('frozen_chunked_surface_helper',CHUNKED_HELPER)
        run_reference=load_external('frozen_active_mass_reference',REFERENCE).run_reference
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

        output, cache = run/'surface', run/'mechanism_jit_cache'
        require(not output.exists() and not cache.exists(), 'fresh output/JIT cache required')
        event({'stage': 'all_external_metadata_source_ABI_resource_gates_bound_before_mesh',
               'metadata': metadata, 'code': code})
        produced = runner.run_chunked_surface_stage(repo_root=ROOT, metadata_dir=METADATA_RUN/'metadata', metadata_seal=seal,
                                     output_dir=output, cache_dir=cache, allocation_gate=gate, event=event,
                                     chunked_helper=helper.assemble_chunked_top_x, reference_helper=run_reference)
        record = produced['record']
        verify_surface_record(record, packet)
        require(file_sha256(output/'surface_record.json') == produced['surface_record']['sha256'],
                'surface terminal packet hash differs')
        saved_members = check_saved_artifacts(record, output)
        saved_mechanism = verify_saved_mechanism(record, packet, output, gate)
        saved_actions = verify_saved_actions(record, packet, output, gate)
        require(source_and_environment() == (source, environment) and code_identity() == code,
                'post-child source/ABI/wrapper/core/reference changed')
        result.update(status='CHUNKED_SELECTED_TOP_X_CHILD_PASS', passed=True,
                      metadata=metadata, surface_record=produced['surface_record'],
                      saved_members_hash_verified=saved_members, saved_only_action_checks=saved_actions,
                      saved_only_mechanism_checks=saved_mechanism,
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
            require(result.get('passed') is True and result.get('status') == 'CHUNKED_SELECTED_TOP_X_CHILD_PASS' and
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
            saved_mechanism = verify_saved_mechanism(record, packet, run/'surface', saved_gate)
            saved_actions = verify_saved_actions(record, packet, run/'surface', saved_gate)
            require(source_and_environment() == (preflight['source'], preflight['environment']) and
                    code_identity() == preflight['code'], 'final post-check source/ABI/code changed')
            terminal.update(passed=True, status='CHUNKED_SELECTED_TOP_X_RESOURCE_SOURCE_PASS',
                            surface_record=result['surface_record'], saved_only_action_checks=saved_actions,
                            saved_only_mechanism_checks=saved_mechanism,
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
