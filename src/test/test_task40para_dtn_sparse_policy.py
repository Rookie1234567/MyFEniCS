from __future__ import annotations

import numpy as np
import pytest

from src.solvers.dtn_port_3d import (
    _combine_owned_entries,
    _vec_nonzero_owned_entries,
)
from src.solvers.dtn_sparse_policy import (
    LEGACY_DTN_SPARSE_CUTOFF_POLICY,
    SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
)


class _SerialComm:
    def allreduce(self, value, op=None):
        return value


class _PetscComm:
    def tompi4py(self):
        return _SerialComm()


class _Vec:
    def __init__(self, values, *, first_row=0):
        self.values = np.asarray(values, dtype=np.complex128)
        self.first_row = int(first_row)

    def getOwnershipRange(self):
        return self.first_row, self.first_row + self.values.size

    def getArray(self, readonly=True):
        assert readonly is True
        return self.values

    def getComm(self):
        return _PetscComm()


def _entries(rows, values):
    return np.asarray(rows, dtype=np.int64), np.asarray(values, dtype=np.complex128)


def test_legacy_default_retains_absolute_floor_and_task40_is_explicit_opt_in():
    values = np.asarray([2.0e-31 + 0.0j, 4.0e-44 - 1.0e-44j])
    legacy_rows, legacy_values = _vec_nonzero_owned_entries(_Vec(values))
    candidate_rows, candidate_values = _vec_nonzero_owned_entries(
        _Vec(values),
        relative_tol=1.0e-13,
        sparse_cutoff_policy=SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
    )

    assert LEGACY_DTN_SPARSE_CUTOFF_POLICY == "absolute_floor_relative_v1"
    assert legacy_rows.size == legacy_values.size == 0
    np.testing.assert_array_equal(candidate_rows, [0, 1])
    np.testing.assert_array_equal(candidate_values, values)


def test_component_extraction_rowset_is_invariant_under_safe_complex_scaling():
    values = np.asarray([2.0e-31 + 0.0j, 4.0e-44 - 1.0e-44j, 0.25e-44j])
    scale = 1.0e30 * (0.6 + 0.8j)
    kwargs = {
        "relative_tol": 1.0e-13,
        "sparse_cutoff_policy": SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
        "support": np.asarray([0, 1, 2], dtype=np.int32),
    }
    low_rows, low_values = _vec_nonzero_owned_entries(_Vec(values), **kwargs)
    high_rows, high_values = _vec_nonzero_owned_entries(_Vec(values * scale), **kwargs)

    np.testing.assert_array_equal(low_rows, [0, 1])
    np.testing.assert_array_equal(high_rows, low_rows)
    np.testing.assert_allclose(high_values, low_values * scale, rtol=2.0e-15, atol=0.0)


@pytest.mark.parametrize(
    "coefficients",
    [
        (0.6 + 0.8j, -0.3 + 0.4j),  # projection combination before conjugation
        (-0.2 + 0.7j, 0.5 - 0.1j),  # nonconjugated coupling combination
    ],
)
def test_component_merge_rowset_is_scale_homogeneous_for_projection_and_coupling(
    coefficients,
):
    components = (
        _entries([2, 5], [2.0e-31 + 1.0e-31j, 4.0e-44 + 0.0j]),
        _entries([2, 3], [-1.0e-31 + 0.5e-31j, 4.0e-44j]),
    )
    scale = 1.0e30 * (0.6 + 0.8j)
    scaled = tuple((rows, values * scale) for rows, values in components)
    common = {
        "comm": _SerialComm(),
        "relative_tol": 1.0e-13,
        "sparse_cutoff_policy": SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
    }
    low_rows, low_values = _combine_owned_entries(
        components, coefficients, **common
    )
    high_rows, high_values = _combine_owned_entries(
        scaled, coefficients, **common
    )

    np.testing.assert_array_equal(high_rows, low_rows)
    np.testing.assert_allclose(high_values, low_values * scale, rtol=3.0e-15, atol=0.0)


def test_zero_component_and_merge_are_explicitly_empty():
    policy = SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY
    rows, values = _vec_nonzero_owned_entries(
        _Vec([0j, 0j]), sparse_cutoff_policy=policy
    )
    assert rows.size == values.size == 0
    rows, values = _combine_owned_entries(
        (_entries([0], [0j]), _entries([], [])),
        (1.0 + 0j, 0.5j),
        comm=_SerialComm(),
        sparse_cutoff_policy=policy,
    )
    assert rows.size == values.size == 0


@pytest.mark.parametrize(
    "values",
    [
        [complex(np.nan, 0.0)],
        [complex(np.inf, 0.0)],
        [complex(1.7e308, 1.7e308)],
    ],
)
def test_component_extraction_rejects_nonfinite_and_overflowed_magnitudes(values):
    with pytest.raises(FloatingPointError):
        _vec_nonzero_owned_entries(
            _Vec(values),
            sparse_cutoff_policy=SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
        )


@pytest.mark.parametrize(
    ("components", "coefficients"),
    [
        ((_entries([0], [complex(np.nan, 0.0)]), _entries([], [])), (1.0, 0.0)),
        ((_entries([0], [1.0]), _entries([], [])), (complex(np.inf, 0.0), 0.0)),
        ((_entries([0], [1.0e-300]), _entries([], [])), (1.0e-300, 0.0)),
    ],
)
def test_merge_rejects_nonfinite_values_coefficients_and_product_underflow(
    components, coefficients
):
    with pytest.raises(FloatingPointError):
        _combine_owned_entries(
            components,
            coefficients,
            comm=_SerialComm(),
            sparse_cutoff_policy=SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
        )


def test_candidate_rejects_invalid_relative_tolerance():
    with pytest.raises(ValueError, match="relative_tol"):
        _vec_nonzero_owned_entries(
            _Vec([1.0]),
            relative_tol=0.0,
            sparse_cutoff_policy=SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
        )
