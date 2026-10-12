"""Algebraic endpoint contracts using fake stores; no FE or PDE runs."""

from copy import deepcopy

import numpy as np
import pytest

from src.runners.n0_full_dtn_endpoint import observe_full_dtn_endpoint


def _functional(row, coupling, projection):
    return {
        'coupling_rows': np.array([row], dtype=np.int64),
        'coupling_values': np.array([coupling], dtype=np.complex128),
        'projection_rows': np.array([row], dtype=np.int64),
        'projection_values': np.array([projection], dtype=np.complex128),
        'normalization_h': 2.0,
    }


class _Store:
    def __init__(self):
        self.entries = [_functional(0, 2.0, 1.0j), _functional(1, 1.0j, 2.0j)]
        self.reads = []
        self.complete = True
        self.fail = False

    def n0_parent_store_inventory_facts(self):
        return {'complete': self.complete, 'expected_mode_count': 2}

    def read_n0_parent_functional_for_endpoint(self, index):
        self.reads.append(index)
        if self.fail and index == 1:
            raise ValueError('payload hash differs')
        return deepcopy(self.entries[index])


def _call(store, **changes):
    kwargs = {
        'parent_store': store, 'active_entries': [deepcopy(store.entries[0])],
        'selected_parent_indices': [0],
        'storage_solution': np.array([2.0, 3.0j], dtype=np.complex128),
        'n0_residual': np.array([1.0, 2.0 + 1.0j], dtype=np.complex128),
        'native_rhs_norm': 4.0, 'iteration': 16, 'omitted_incident_rhs_zero': True,
    }
    kwargs.update(changes)
    before = kwargs['n0_residual'].copy()
    result = observe_full_dtn_endpoint(**kwargs)
    np.testing.assert_array_equal(kwargs['n0_residual'], before)
    return result


def test_endpoint_uses_dot_not_vdot_and_preserves_inputs():
    store = _Store()
    result = _call(store)
    # dot(2j,3j)/2=-3; C=j, so omitted action=-3j and r_full[1]=2+4j.
    assert result['A6_full_relative'] == pytest.approx(np.sqrt(21.0) / 4.0)
    assert result['omitted_dtn_action_norm'] == 3.0
    assert result['active_functionals_matched'] == 1
    assert result['omitted_functionals_applied'] == 1
    assert store.reads == [0, 1]
    assert result['new_FE_assembly_calls'] == result['new_factor_calls'] == 0


def test_endpoint_keeps_tiny_omitted_contribution_instead_of_subtracting_norms():
    store = _Store()
    store.entries[1]['coupling_values'][:] = 1e-30
    result = _call(store)
    assert result['omitted_dtn_action_norm'] == pytest.approx(3e-30, rel=1e-14, abs=0.0)


@pytest.mark.parametrize('failure', ['missing_store', 'inventory', 'rhs', 'payload', 'parity'])
def test_endpoint_unavailable_data_never_becomes_full_residual(failure):
    store = _Store()
    changes = {}
    if failure == 'missing_store':
        changes['parent_store'] = None
    elif failure == 'inventory':
        store.complete = False
    elif failure == 'rhs':
        changes['omitted_incident_rhs_zero'] = False
    elif failure == 'payload':
        store.fail = True
    else:
        changed = deepcopy(store.entries[0])
        changed['coupling_values'] += 1e-12
        changes['active_entries'] = [changed]
    result = _call(store, **changes)
    assert result['status'] == 'FULL_DTN_NOT_VERIFIED'
    assert result['A6_full_relative'] is None
    assert result['omitted_dtn_action_norm'] is None
    assert result['new_FE_assembly_calls'] == 0


def test_endpoint_nonfinite_omitted_projection_is_not_a_success():
    store = _Store()
    store.entries[1]['projection_values'][:] = np.nan
    result = _call(store)
    assert result['status'] == 'FULL_DTN_NOT_VERIFIED'
    assert result['A6_full_relative'] is None
