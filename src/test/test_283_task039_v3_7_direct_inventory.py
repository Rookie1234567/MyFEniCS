from __future__ import annotations

import hashlib

import numpy as np
import pytest

from benchmarks.task039_hybrid_direct_identity import (
    IdentityCheckError,
    reconstruct_hash_bound_solution_vector,
)


def _bound_inventory(
    values: np.ndarray, layout: dict[str, object]
) -> dict[str, object]:
    payload = np.ascontiguousarray(values, dtype=np.complex128).tobytes(order="C")
    return {
        "mapping_status": "available",
        "row_mapping": {
            "layout": layout,
            "global_size": int(values.size),
            "solution_sha256": hashlib.sha256(payload).hexdigest(),
        },
    }


def test_direct_solution_reconstruction_is_hash_and_layout_bound():
    values = np.asarray([1.0 + 0.2j, -0.5 + 0.1j, 0.8 - 0.3j], dtype=np.complex128)
    layout = {"global_size": 3, "bottom": 1, "top": 1, "modal": 1}
    inventory = _bound_inventory(values, layout)
    actual = reconstruct_hash_bound_solution_vector(
        inventory,
        values,
        expected_layout=layout,
    )
    assert np.array_equal(actual, values)

    with pytest.raises(IdentityCheckError, match="hash"):
        reconstruct_hash_bound_solution_vector(
            inventory,
            values + 1.0,
            expected_layout=layout,
        )
    with pytest.raises(IdentityCheckError, match="layout"):
        reconstruct_hash_bound_solution_vector(
            inventory,
            values,
            expected_layout={**layout, "bottom": 2},
        )


def test_direct_solution_reconstruction_fails_closed_without_row_mapping():
    values = np.ones(3, dtype=np.complex128)
    with pytest.raises(IdentityCheckError, match="row map"):
        reconstruct_hash_bound_solution_vector(
            {"mapping_status": "not_available", "row_mapping": None},
            values,
            expected_layout={"global_size": 3},
        )
