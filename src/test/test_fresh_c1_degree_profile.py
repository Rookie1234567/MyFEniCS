"""Synthetic metadata negatives only; never FE/JIT or fresh C1 qualification.

This staged test file has not been imported or executed. Full component
qualification still requires current literal532 and complete runtime evidence.
"""
import copy
import hashlib
import json

import pytest

from src.solvers.dtn_boundary_plane_qualification import (
    fresh_c1_degree_profile, _qualification_degree_profile,
)
from src.solvers.y_orbit_live_boundary_contract import validate_live_receipt
from src.test.test_y_orbit_live_boundary_contract import _receipt


def _fresh_receipt(degree=6):
    receipt, keys = _receipt()
    profile = fresh_c1_degree_profile(degree)
    points = profile['primary_facet_points']
    native = {name: {'shape': shape, 'dtype': dtype, 'sha256': 'a'*64}
              for name, shape, dtype in (
                  ('slaves', [profile['native_slave_rows']], 'int32'),
                  ('masters', [profile['native_slave_rows']], 'int32'),
                  ('coefficients', [profile['native_slave_rows']], 'complex128'),
                  ('offsets', [profile['storage_rows']+1], 'int32'))}
    receipt.update({'degree': degree, 'element_degree': degree,
                    'local_space_dimension': profile['local_space_dimension'],
                    'quadrature_degree': profile['quadrature_degree'], 'primary_facet_points': points,
                    'fresh_fixture_c1': True, 'fresh_c1_profile': profile,
                    'fresh_c1_actual_inventory': {
                        'classification': 'actual_runtime_gated',
                        **{name: profile[name] for name in (
                            'cell_count','local_space_dimension','local_interior_rows','local_trace_rows',
                            'storage_rows','independent_rows','interior_rows','independent_trace_rows','native_slave_rows')},
                        'native_MPC': copy.deepcopy(native), 'actual_primary_compiled_gauss_verified': True}})
    context = receipt['raw_discrete_context']
    context.update({'element_degree': degree, 'MPC': native,
                    'ABI': {'dolfinx': '0.10.0', 'dolfinx_mpc': '0.10.5', 'PETSc': [3,25,6],
                            'scalar': 'complex128', 'integer': 'int32'}})
    context['gauss']['degree'] = profile['quadrature_degree']
    for record in receipt['primary_compiled_gauss'].values():
        record['rules'] = [{'degree': profile['quadrature_degree'], 'facet_cell': 'quadrilateral',
                            'integral_type': 'exterior_facet',
                            'points': {'shape': [points,2], 'dtype': 'float64', 'sha256': 'b'*64},
                            'weights': {'shape': [points], 'dtype': 'float64', 'sha256': 'c'*64}}]
    context['gauss']['compiled_forms_verified'] = copy.deepcopy(receipt['primary_compiled_gauss'])
    receipt['independent_oracle_compiled_gauss'] = {
        gauge+'/'+name: {'rules': copy.deepcopy(record['rules'])}
        for gauge in ('global_z','boundary_plane')
        for name, record in receipt['primary_compiled_gauss'].items()}
    receipt['incident_literal_gauss'] = {'rules': copy.deepcopy(receipt['primary_compiled_gauss']['top/0']['rules'])}
    receipt['identity']['physical_generator_manifest_sha256'] = profile['physical_generator_manifest_sha256']
    receipt['physical_generator_manifest_sha256'] = profile['physical_generator_manifest_sha256']
    digest = hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    receipt['identity']['assembly_context_sha256'] = receipt['assembly_context_sha256'] = digest
    return receipt, keys


@pytest.mark.parametrize('degree,expected', [(4,(300,108,192,17204,15872,8640,7232,23,144)),
                                           (6,(882,450,432,55950,52992,36000,16992,27,196))])
def test_fresh_same80_metadata_keeps_degree_specific_complete_inventory(degree,expected):
    profile = fresh_c1_degree_profile(degree)
    assert tuple(profile[name] for name in ('local_space_dimension','local_interior_rows','local_trace_rows',
        'storage_rows','independent_rows','interior_rows','independent_trace_rows',
        'quadrature_degree','primary_facet_points')) == expected
    assert profile['expected_inventory_classification'] == 'derived_not_measured'
    assert profile['nominal_gauss_points_require_actual_compiled_gate'] is True
    assert profile['mode_count'] == 532 and (profile['manual_M'],profile['manual_N']) == (9,3)
    assert (profile['action_recovery_limit'],profile['original_residual_limit'],profile['pure_algebra_limit']) == (1e-11,1e-10,1e-12)
    assert not profile['p6_full_chain_qualified'] and not profile['compact_p4_quotient_qualified']


@pytest.mark.parametrize('degree', [2,5,True,6.0,'6'])
def test_fresh_metadata_rejects_unreviewed_or_noninteger_profiles(degree):
    with pytest.raises(ValueError):
        fresh_c1_degree_profile(degree)


def test_legacy_degree6_call_still_fails_before_accessing_live_FE_objects():
    with pytest.raises(ValueError,match='degree 2 or 4'):
        _qualification_degree_profile({'degree': 6})


@pytest.mark.parametrize('degree', [4,6])
def test_explicit_fresh_receipt_retains_all532_proof_and_compiled_identity_gates(degree):
    receipt,keys = _fresh_receipt(degree)
    assert validate_live_receipt(receipt,physical_manifest=receipt['physical_generator_manifest_sha256'],
        ordered_keys=keys,identity=receipt['identity'],expected_degree=degree,fresh_fixture_c1=True)
    if degree == 6:
        with pytest.raises(ValueError):
            validate_live_receipt(receipt,physical_manifest=receipt['physical_generator_manifest_sha256'],
                ordered_keys=keys,expected_degree=degree)


@pytest.mark.parametrize('failure', ['lost_interior','lost_trace','detached_native','old_ABI',
    'nominal_only_Gauss','wrong_Gauss_dtype','wrong_physical_manifest','missing_mode','bad_numerical_bound'])
def test_fresh_p6_receipt_rejects_incomplete_actual_or_literal_evidence(failure):
    receipt,keys = _fresh_receipt()
    if failure == 'lost_interior': receipt['fresh_c1_actual_inventory']['interior_rows'] -= 1
    elif failure == 'lost_trace': receipt['fresh_c1_actual_inventory']['independent_trace_rows'] -= 1
    elif failure == 'detached_native': receipt['fresh_c1_actual_inventory']['native_MPC']['slaves']['sha256'] = 'd'*64
    elif failure == 'old_ABI': receipt['raw_discrete_context']['ABI']['PETSc'] = [3,21,4]
    elif failure == 'nominal_only_Gauss': receipt['primary_compiled_gauss']['bottom/1']['rules'][0]['points']['shape'] = [144,2]
    elif failure == 'wrong_Gauss_dtype': receipt['primary_compiled_gauss']['top/0']['rules'][0]['weights']['dtype'] = 'float32'
    elif failure == 'wrong_physical_manifest': receipt['physical_generator_manifest_sha256'] = 'another_physical_fixture'
    elif failure == 'missing_mode': receipt['per_mode'].pop()
    else: receipt['per_mode'][0]['equivalence']['raw_C_equivalence'] = 1e-8
    with pytest.raises(ValueError):
        validate_live_receipt(receipt,physical_manifest=receipt['physical_generator_manifest_sha256'],
            ordered_keys=keys,expected_degree=6,fresh_fixture_c1=True)


def test_historical_p2_receipt_remains_on_its_existing_contract():
    receipt,keys = _receipt()
    assert validate_live_receipt(receipt,physical_manifest='physical',ordered_keys=keys,identity=receipt['identity'])
