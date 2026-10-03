"""Strict same-live-carrier proof transaction; raw JIT identities stay intact.

Shared discrete inputs are compared separately from each exact compiler
artifact identity. Numerical equivalence still requires all-column/full-field
controls, and every rebuilt carrier independently needs the literal oracle.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import numpy as np

EXPECTED_GATES = (
    'loaded_kernel_provenance_and_constant_restoration',
    'compiled_primary_literal_same_gauss',
    'all532_raw_coefficient_H_equivalence',
    'every_mode_full_DOF_rank_one_bound',
    'five_state_actual_action_recovery_output_components',
    'physical_FE_RHS_literal_oracle',
    'incident_and_nonzero_port_RHS_transforms',
    'unchanged_live_carrier_digest',
)


def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()


def validate_fresh_c1_receipt_profile(receipt, *, expected_degree):
    """Verify explicit fresh profile/actual native inventories in a saved proof."""
    from .dtn_boundary_plane_qualification import fresh_c1_degree_profile
    expected = fresh_c1_degree_profile(expected_degree)
    actual = receipt.get('fresh_c1_actual_inventory', {})
    counts = ('cell_count','local_space_dimension','local_interior_rows','local_trace_rows',
              'storage_rows','independent_rows','interior_rows','independent_trace_rows','native_slave_rows')
    context = receipt['raw_discrete_context']
    if (receipt.get('fresh_fixture_c1') is not True or receipt.get('fresh_c1_profile') != expected
            or actual.get('classification') != 'actual_runtime_gated'
            or any(actual.get(name) != expected[name] for name in counts)
            or actual.get('actual_primary_compiled_gauss_verified') is not True
            or actual.get('native_MPC') != context['MPC']
            or receipt.get('element_degree') != expected_degree
            or receipt.get('local_space_dimension') != expected['local_space_dimension']
            or receipt.get('primary_facet_points') != expected['primary_facet_points']
            or receipt.get('quadrature_degree') != expected['quadrature_degree']
            or receipt.get('physical_generator_manifest_sha256') != expected['physical_generator_manifest_sha256']):
        raise ValueError('fresh C1 saved actual FE/native MPC/physical profile is incomplete or detached')
    native = context['MPC']
    if (set(native) != {'slaves','masters','coefficients','offsets'}
            or native['slaves']['shape'] != [expected['native_slave_rows']]
            or native['slaves']['dtype'] != 'int32' or native['masters']['dtype'] != 'int32'
            or native['offsets']['dtype'] != 'int32' or native['coefficients']['dtype'] != 'complex128'
            or len(native['masters']['shape']) != 1 or native['masters']['shape'][0] <= 0
            or native['masters']['shape'] != native['coefficients']['shape']
            or len(native['offsets']['shape']) != 1
            or native['offsets']['shape'][0] < expected['storage_rows']+1
            or any(len(value.get('sha256','')) != 64 for value in native.values())):
        raise ValueError('fresh C1 exact native MPC signature inventory differs')
    abi = context['ABI']
    if (not str(abi['dolfinx']).startswith('0.10.') or abi['dolfinx_mpc'] != '0.10.5'
            or tuple(abi['PETSc']) != (3,25,6) or abi['scalar'] != 'complex128' or abi['integer'] != 'int32'):
        raise ValueError('fresh C1 saved actual ABI differs from the admitted recovered runtime')
    primary = receipt['primary_compiled_gauss']
    if set(primary) != {'top/0','top/1','bottom/0','bottom/1'}:
        raise ValueError('fresh C1 requires all four actual primary compiled Gauss records')
    for record in primary.values():
        if len(record['rules']) != 1:
            raise ValueError('fresh C1 requires one actual compiled Gauss rule per component')
        rule = record['rules'][0]
        points = expected['primary_facet_points']
        if (rule['degree'] != expected['quadrature_degree']
                or rule['facet_cell'] != 'quadrilateral' or rule['integral_type'] != 'exterior_facet'
                or rule['points']['shape'] != [points,2] or rule['weights']['shape'] != [points]
                or rule['points']['dtype'] != 'float64' or rule['weights']['dtype'] != 'float64'):
            raise ValueError('fresh C1 saved actual compiled Gauss nodes/weights differ from its degree profile')
    return True


def validate_live_receipt(receipt, *, physical_manifest, ordered_keys, identity=None, expected_degree=2,
                          fresh_fixture_c1=False):
    from .fullspace_dtn_action import _jsonable, _canonical_json_bytes
    receipt=_jsonable(receipt)
    identity=_jsonable(identity) if identity is not None else None
    if type(fresh_fixture_c1) is not bool:
        raise TypeError('fresh C1 opt-in must be an explicit bool')
    if fresh_fixture_c1:
        validate_fresh_c1_receipt_profile(receipt,expected_degree=expected_degree)
    keys=[list(key) for key in ordered_keys]
    i=receipt['identity']
    if (receipt.get('status')!='PASS_COMPONENT_ONLY' or receipt.get('full_case_pass') is not True
        or receipt.get('PDE_solved') is not False or receipt.get('official_results') is not False
        or receipt.get('completed_gates')!=list(EXPECTED_GATES) or receipt.get('mode_count')!=532
        or (expected_degree not in (2,4) and not (fresh_fixture_c1 and expected_degree==6))
        or receipt.get('degree')!=expected_degree or receipt.get('azimuth_deg')!=5.0
        or receipt.get('seed')!=4053202 or receipt.get('tolerance')!=1e-10
        or i['physical_generator_manifest_sha256']!=physical_manifest
        or i['mode_count']!=532 or [list(k) for k in i['ordered_mode_keys']]!=keys
        or receipt.get('carrier_digest_before')!=i['carrier_numeric_sha256']
        or receipt.get('carrier_digest_after')!=i['carrier_numeric_sha256']):
        raise ValueError('same-live component proof identity/gate inventory incomplete')
    if identity is not None:
        normalized=json.loads(json.dumps(identity))
        if json.loads(json.dumps(i))!=normalized:
            raise ValueError('component receipt is not bound to this exact current carrier')
    for field in ('physical_generator_manifest_sha256','assembly_mode_manifest_sha256','assembly_context_sha256'):
        if receipt.get(field)!=i[field]:raise ValueError('live receipt top-level raw identity detached')
    context=receipt['raw_discrete_context']
    qdegree=27 if fresh_fixture_c1 and expected_degree==6 else {2:19,4:23}[expected_degree]
    if (context['element_degree']!=expected_degree
            or context['gauss']['degree']!=qdegree):
        raise ValueError('live receipt actual degree/Gauss profile differs')
    context_sha=hashlib.sha256(_canonical_json_bytes(context)).hexdigest()
    if context_sha!=i['assembly_context_sha256']:
        raise ValueError('exact raw context canonical hash differs')
    primary=receipt['primary_compiled_gauss']
    if primary!=context['gauss']['compiled_forms_verified']:
        raise ValueError('primary kernels detached from exact raw context')
    oracle=receipt['independent_oracle_compiled_gauss']
    expected_oracle={f'{g}/{side}/{component}' for g in ('global_z','boundary_plane')
                     for side in ('top','bottom') for component in (0,1)}
    if set(oracle)!=expected_oracle:
        raise ValueError('eight independent literal Gauss identities required')
    for gauge in ('global_z','boundary_plane'):
        for name in ('top/0','top/1','bottom/0','bottom/1'):
            if oracle[gauge+'/'+name]['rules']!=primary[name]['rules']:
                raise ValueError('primary and independent literal Gauss nodes/weights/rules differ')
    if receipt['incident_literal_gauss']['rules']!=primary['top/0']['rules']:
        raise ValueError('independent incident Gauss proof differs')
    rows=receipt.get('per_mode',[])
    if len(rows)!=532 or [list(r['key']) for r in rows]!=keys or [r['index'] for r in rows]!=list(range(532)):
        raise ValueError('all532 per-mode proof rows are required and ordered')
    for row in rows:
        if row['new_C_entries']<=0 or row['new_D_entries']<=0:
            raise ValueError('same-live component lost a physical contribution')
        values=[row['equivalence'][k] for k in ('raw_C_equivalence','raw_D_equivalence',
            'raw_H_equivalence','per_mode_raw_action_equivalence')]
        values += [row['new_stored_relative_operator_bound'],row['power_operation_scaled_defect']]
        for field in (row['production_recovery_operation_scaled_defects']['new_stored'],
                      row['raw_recovery_operation_scaled_defects']):
            if len(field)!=5:raise ValueError('five-state per-mode recovery inventory incomplete')
            values+=field
        if any(not np.isfinite(v) or not 0<=v<=1e-10 for v in values):
            raise ValueError('same-live per-mode component gate failed')
    outputs=receipt.get('output_component_gates',[])
    if (len(outputs)!=5 or [v['arbitrary_state_column'] for v in outputs]!=list(range(5))
        or any(v.get('status')!='representable_global_output' or v.get('mode_count')!=532
               or v.get('global_output_component_consistency_checked') is not True
               or v.get('official_results') is not False for v in outputs)):
        raise ValueError('complete required same-live output component gates missing')
    for name in ('raw_vs_centered_action_defect','new_stored_vs_raw_action_defect','physical_FE_RHS_literal_raw_defect'):
        v=receipt[name]
        if not np.isfinite(v) or not 0<=v<=1e-10:raise ValueError('same-live aggregate/RHS gate failed')
    gauss=receipt['primary_compiled_gauss']
    if set(gauss)!={'top/0','top/1','bottom/0','bottom/1'}:
        raise ValueError('four exact loaded primary kernels required')
    for record in gauss.values():
        if len(record['rules'])!=1:
            raise ValueError('one actual quadrilateral Gauss rule per component required')
        rule=record['rules'][0]
        points=196 if fresh_fixture_c1 and expected_degree==6 else {2:100,4:144}[expected_degree]
        if (rule['degree']!=qdegree
                or rule['points']['shape']!=[points,2] or rule['weights']['shape']!=[points]):
            raise ValueError('actual compiled Gauss point/weight inventory differs from degree profile')
        kernel=record['loaded_kernel']
        if (kernel.get('restoration_exact') is not True or kernel.get('numerical_assembly_during_probe') is not False
            or kernel.get('num_constants')!=3 or [v['role'] for v in kernel['constant_roles']]!=['alpha','gamma','kz']
            or sorted(v['packed_slot'] for v in kernel['constant_roles'])!=[0,1,2]):
            raise ValueError('same-live loaded-kernel constant contract incomplete')
    return True


def shared_discrete_contract(raw_context):
    # Enumerate every noncompiler discrete field, reject unfamiliar top-level
    # fields so future identity extensions cannot silently escape comparison.
    names=('schema','source_sha256','mesh','cell_dofmap_sha256','orientation','basix_coefficients',
           'MPC','config_sha256','ABI','element_degree','element_map_type','needs_dof_transformations')
    if set(raw_context)!=set(names)|{'gauss'}:
        raise ValueError('unrecognized full discrete context requires reviewed comparison')
    result={k:raw_context[k] for k in names}
    gauss=raw_context['gauss']
    result['gauss_discrete_contract']={k:gauss[k] for k in ('degree','rule','facet_cell')}
    compiled=gauss['compiled_forms_verified']
    if set(compiled)!={'top/0','top/1','bottom/0','bottom/1'}:
        raise ValueError('four actual Gauss identities required')
    result['gauss_discrete_contract']['actual_rules']={k:compiled[k]['rules'] for k in sorted(compiled)}
    return result


def qualify_live_identity(bundle, *, record_path, allocation_gate, event, fresh_fixture_c1=False):
    from .fullspace_dtn_action import _jsonable
    from .dtn_boundary_plane_qualification import qualify_boundary_plane_bundle, carrier_numeric_identity
    from .y_orbit_centered_evidence import COMPONENT_IDENTITY
    from src.common.modes_3d import outgoing_port_modes_3d
    carrier=bundle['dtn_action'].carrier
    physical=COMPONENT_IDENTITY['physical_generator_manifest_sha256']
    keys=[(j,str(m.side),int(m.m),int(m.n),str(m.polarization))
          for j,m in enumerate(outgoing_port_modes_3d(bundle['cfg']))]
    before=carrier_numeric_identity(carrier)
    event('same_live_component_before_qualification',{'identity':_jsonable(before),
          'raw_discrete_context':_jsonable(carrier.assembly_context)})
    allocation_gate('same_live_literal_component_oracle',{'matrix_payload_bytes':16<<20,
        'workspace_bytes':128<<20,'named_small_oracle_allowance_not_peak_bound':True,
        'no_factor_or_full_dense_matrix':True})
    receipt=qualify_boundary_plane_bundle(bundle,record_path=record_path,
         expected_physical_manifest=physical,expected_ordered_keys=keys,fresh_fixture_c1=fresh_fixture_c1)
    after=carrier_numeric_identity(carrier)
    if bundle['dtn_action'].carrier is not carrier or before!=after:
        raise ValueError('the qualified live carrier object or numeric state changed')
    validate_live_receipt(receipt,physical_manifest=physical,ordered_keys=keys,identity=after,
                          expected_degree=int(bundle['degree']),fresh_fixture_c1=fresh_fixture_c1)
    if receipt['qualification_source_sha256'] != file_sha(Path(__file__).with_name('dtn_boundary_plane_qualification.py')):
        raise ValueError('same-process qualification numerical source identity differs')
    stored=json.loads(Path(record_path).read_text())
    validate_live_receipt(stored,physical_manifest=physical,ordered_keys=keys,identity=after,
                          expected_degree=int(bundle['degree']),fresh_fixture_c1=fresh_fixture_c1)
    if _jsonable(receipt)!=stored:raise ValueError('written receipt differs from exact live transaction')
    context=_jsonable(carrier.assembly_context)
    shared=shared_discrete_contract(context)
    event('same_live_component_pass_before_factor',{'identity':_jsonable(after),'receipt_sha256':file_sha(record_path)})
    return {**_jsonable(after),'dtn_phase_gauge':'boundary_plane','empty_C':0,'empty_D':0,
        'actual_context':context,'shared_discrete_contract':shared,
        'actual_mode_keys':[list(e.mode_key) for e in carrier.entries],
        'all_532_contributions_nonempty':True,'cutoffs_unchanged':True,
        'live_component_receipt':{'filename':Path(record_path).name,'sha256':file_sha(record_path)},
        'same_live_component_required':True,'historical_a054_is_raw_context_authority':False}


def require_live_carrier_unchanged(bundle, identity, *, event, boundary, expected_carrier):
    from .dtn_boundary_plane_qualification import carrier_numeric_identity
    if bundle['dtn_action'].carrier is not expected_carrier:
        raise ValueError('qualified carrier object replaced at '+boundary)
    actual=carrier_numeric_identity(bundle['dtn_action'].carrier)
    expected={k:identity[k] for k in actual}
    if json.loads(json.dumps(actual))!=json.loads(json.dumps(expected)):
        raise ValueError('exact live qualified carrier changed at '+boundary)
    event('qualified_live_carrier_unchanged',{'boundary':boundary,'carrier_numeric_sha256':actual['carrier_numeric_sha256']})


def load_bound_live_receipt(directory, identity, *, worker_source=None, expected_degree=2,
                            fresh_fixture_c1=False):
    directory=Path(directory).resolve();descriptor=identity['live_component_receipt']
    path=(directory/descriptor['filename']).resolve()
    if not path.is_relative_to(directory) or file_sha(path)!=descriptor['sha256']:
        raise ValueError('same-live receipt file binding differs')
    receipt=json.loads(path.read_text())
    if worker_source is not None and receipt['qualification_source_sha256'] != worker_source['files_sha256']['src/solvers/dtn_boundary_plane_qualification.py']:
        raise ValueError('live qualification numerical source differs from worker source')
    if worker_source is not None:
        from .y_orbit_centered_evidence import COMPONENT_SOURCE_FILES
        expected_paths={Path(path).name:path for path in COMPONENT_SOURCE_FILES}
        expected_paths['dtn_boundary_plane_qualification.py']='src/solvers/dtn_boundary_plane_qualification.py'
        raw_sources=receipt['raw_discrete_context']['source_sha256']
        if set(raw_sources)!=set(expected_paths):
            raise ValueError('unreviewed numerical source context inventory')
        for basename,digest in raw_sources.items():
            if digest!=worker_source['files_sha256'][expected_paths[basename]]:
                raise ValueError('raw numerical context source differs from worker source: '+basename)
    expected={k:identity[k] for k in receipt['identity']}
    validate_live_receipt(receipt,physical_manifest=identity['physical_generator_manifest_sha256'],
                          ordered_keys=identity['actual_mode_keys'],identity=expected,expected_degree=expected_degree,
                          fresh_fixture_c1=fresh_fixture_c1)
    if receipt['raw_discrete_context']!=identity['actual_context']:
        raise ValueError('fresh raw context was replaced in the saved proof')
    if shared_discrete_contract(receipt['raw_discrete_context'])!=identity['shared_discrete_contract']:
        raise ValueError('fixed comparison contract differs from raw context')
    return receipt
