"""Focused tests for the H1R.1b rank-one direct action backend."""

from __future__ import annotations

import numpy as np
import pytest

from benchmarks.run_task037_extra_h1r import (
    _DenseCellPath,
    _build_single_cell,
)
from src.solvers.hcurl_rank_one_form_action import HcurlRankOneFormAction


def _relative_error(observed: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(observed - expected)
        / max(float(np.linalg.norm(expected)), 1.0e-30)
    )


@pytest.mark.parametrize("degree", [2, 3])
def test_rank_one_action_repacks_each_distinct_input(degree: int):
    context = _build_single_cell(degree)
    authority_path = _DenseCellPath(context, retabulate=False)
    authority_path.setup_cached_tensor()
    action = HcurlRankOneFormAction(context.form_ufl, context.function_space)
    try:
        first_input = context.local_input.copy()
        second_input = (
            0.31
            + 0.011 * np.arange(first_input.size, dtype=np.float64)
            + 1j * (0.47 - 0.006 * np.arange(first_input.size))
        ).astype(np.complex128)
        expected_first = authority_path.tensor @ first_input
        expected_second = authority_path.tensor @ second_input

        first = np.asarray(action.apply(first_input)).copy()
        second = np.asarray(action.apply(second_input)).copy()
        first_repeat = np.asarray(action.apply(first_input)).copy()

        assert np.array_equal(first_input, context.local_input)
        assert not np.array_equal(first_input, second_input)
        assert _relative_error(first, expected_first) <= 1.0e-11
        assert _relative_error(second, expected_second) <= 1.0e-11
        assert np.array_equal(first, first_repeat)
        assert np.all(np.isfinite(first))
        assert np.all(np.isfinite(second))

        audit = action.audit
        components = audit["retained_numeric_payload_components"]
        packed_shapes = audit["last_packed_coefficient_shapes"]
        packed_entries = audit["last_packed_coefficient_entry_count"]
        assert audit["form_rank"] == 1
        assert audit["coefficient_count"] == 1
        assert audit["kernel_output_local_rows"] == first_input.size
        assert audit["kernel_output_local_rows_semantics"] == (
            "local_storage_entries"
        )
        assert audit["local_storage_entries"] == (
            audit["local_owned_rows"] + audit["local_ghost_rows"]
        )
        assert audit["global_rows"] == audit["local_owned_rows"]
        assert audit["kernel_output_shape"] == [first_input.size]
        assert audit["apply_count"] == 3
        assert audit["retained_numeric_payload_total_bytes"] == sum(
            components.values()
        )
        assert audit["retained_payload_per_exact_class_bytes"] == (
            audit["retained_numeric_payload_total_bytes"]
        )
        assert audit["retained_payload_per_exact_class_bytes"] < 16 * 1024**2
        assert audit["global_matrix_materialized"] is False
        assert audit["dense_cell_tensor_materialized_per_apply"] is False
        assert audit["retained_dense_cell_tensor_count"] == 0
        assert audit["cell_tensor_scratch_count"] == 0
        assert audit["last_packed_coefficient_bytes"] > 0
        assert all(shape != [first_input.size, first_input.size]
                   for shape in packed_shapes)
        assert max(int(np.prod(shape)) for shape in packed_shapes) <= (
            first_input.size
        )
        assert packed_entries * np.dtype(np.complex128).itemsize == (
            audit["last_packed_coefficient_bytes"]
        )
        assert audit["per_apply_bounded_temporary_bytes"] == (
            audit["last_packed_coefficient_bytes"]
        )
        assert audit["per_apply_packed_coefficient_temporary"] is True
        assert audit["ordinary_default_changed"] is False
        assert not any(
            isinstance(value, np.ndarray) and value.ndim == 2
            for value in vars(action).values()
        )
    finally:
        action.destroy()
        del authority_path
        del context
