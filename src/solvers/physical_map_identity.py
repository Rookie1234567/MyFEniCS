"""Hash-bound comparison for saved native MPC/mesh map packets.

Saved diagnostic packets contain both numerical arrays and packet metadata.
The latter may grow between reviews (for example an ``arrays`` archive
descriptor or a provenance note), while the numerical map must remain exactly
the same.  This module keeps that distinction explicit and also checks the
master/slave layout so a numerically shaped but semantically inverted packet
cannot pass by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

import numpy as np


NATIVE_MAP_ARRAY_KEYS = (
    "dofmap",
    "geometry",
    "geometry_dofmap",
    "permutations",
    "slaves",
    "masters",
    "coefficients",
    "offsets",
    "independent_indices",
)

NATIVE_MAP_SEMANTICS = {
    "dofmap": "primal_cell_to_global_dof_rows",
    "geometry": "primal_mesh_geometry_coordinates",
    "geometry_dofmap": "primal_cell_to_geometry_rows",
    "permutations": "primal_cell_orientation_permutation_info",
    "slaves": "primal_mpc_slave_rows",
    "masters": "primal_mpc_master_rows",
    "coefficients": "primal_mpc_slave_to_master_coefficients",
    "offsets": "primal_mpc_slave_csr_offsets",
    "independent_indices": "primal_unconstrained_rows",
    "dual_projection": "dual_is_conjugate_transpose_of_primal_mpc",
}


def _array_identity(value: Any) -> tuple[np.ndarray, dict[str, Any]]:
    array = np.ascontiguousarray(np.asarray(value))
    facts = {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
    }
    return array, facts


def _validate_mpc_layout(arrays: Mapping[str, np.ndarray], *, label: str) -> None:
    slaves = arrays["slaves"]
    masters = arrays["masters"]
    coefficients = arrays["coefficients"]
    offsets = arrays["offsets"]
    independent = arrays["independent_indices"]
    for name, value in (
        ("slaves", slaves),
        ("masters", masters),
        ("offsets", offsets),
        ("independent_indices", independent),
    ):
        if value.ndim != 1 or not np.issubdtype(value.dtype, np.integer):
            raise ValueError(f"{label} {name} is not a one-dimensional integer array")
    if coefficients.ndim != 1 or not np.issubdtype(coefficients.dtype, np.number):
        raise ValueError(f"{label} coefficients is not a one-dimensional numeric array")
    if not np.all(np.isfinite(coefficients)):
        raise ValueError(f"{label} coefficients contain non-finite values")
    if len(masters) != len(coefficients):
        raise ValueError(f"{label} masters/coefficients length differs")
    if len(offsets) == 0 or int(offsets[0]) != 0 or int(offsets[-1]) != len(masters):
        raise ValueError(f"{label} MPC offsets do not delimit the master array")
    if np.any(np.diff(offsets) < 0):
        raise ValueError(f"{label} MPC offsets are not monotone")
    if len(np.unique(slaves)) != len(slaves):
        raise ValueError(f"{label} contains duplicate MPC slave rows")
    if np.intersect1d(slaves, masters).size:
        raise ValueError(f"{label} master/slave rows overlap")
    if len(np.unique(independent)) != len(independent):
        raise ValueError(f"{label} contains duplicate independent rows")
    if np.intersect1d(slaves, independent).size:
        raise ValueError(f"{label} independent rows include an MPC slave")
    row_count = len(offsets) - 1
    for name, value in (("slaves", slaves), ("masters", masters), ("independent_indices", independent)):
        if value.size and (np.min(value) < 0 or np.max(value) >= row_count):
            raise ValueError(f"{label} {name} contains a row outside the primal map")


def compare_native_map_identity(
    current: Mapping[str, Any], saved_packet: Mapping[str, Any], *, context: str = "native map"
) -> dict[str, Any]:
    """Compare the numerical map and its semantics, ignoring packet metadata.

    Equality is stricter than ``np.array_equal`` alone: shape, dtype and a
    contiguous-byte SHA-256 are recorded for every numeric array.  The
    master/slave layout is checked directly; the primal/dual relation is
    covered by the focused complex-map regression rather than guessed from
    packet metadata or free-form semantic strings.
    """

    if not isinstance(current, Mapping) or not isinstance(saved_packet, Mapping):
        raise TypeError(f"{context} comparison requires mapping packets")
    keys = tuple(NATIVE_MAP_ARRAY_KEYS)
    current_map = current
    saved_map = saved_packet
    missing_current = [key for key in keys if key not in current_map]
    missing_saved = [key for key in keys if key not in saved_map]
    if missing_current or missing_saved:
        raise ValueError(
            f"{context} numeric map fields are incomplete: "
            f"current_missing={missing_current}, saved_missing={missing_saved}"
        )
    unexpected_saved_arrays = sorted(
        str(key)
        for key, value in saved_map.items()
        if isinstance(value, np.ndarray) and str(key) not in keys
    )
    if unexpected_saved_arrays:
        raise ValueError(
            f"{context} saved packet contains unverified numeric arrays: "
            f"{unexpected_saved_arrays}"
        )
    current_arrays: dict[str, np.ndarray] = {}
    saved_arrays: dict[str, np.ndarray] = {}
    array_facts: dict[str, Any] = {}
    for key in keys:
        current_array, current_facts = _array_identity(current_map[key])
        saved_array, saved_facts = _array_identity(saved_map[key])
        current_arrays[key] = current_array
        saved_arrays[key] = saved_array
        if current_facts != saved_facts or not np.array_equal(current_array, saved_array):
            raise ValueError(
                f"{context} numeric field {key!r} differs: "
                f"current={current_facts}, saved={saved_facts}"
            )
        array_facts[key] = {"current": current_facts, "saved": saved_facts}

    _validate_mpc_layout(current_arrays, label=f"current {context}")
    _validate_mpc_layout(saved_arrays, label=f"saved {context}")

    return {
        "schema": "task039extra.native-map-identity.v1",
        "status": "PASS",
        "numeric_keys": list(keys),
        "array_facts": array_facts,
        "semantic_contract": dict(NATIVE_MAP_SEMANTICS),
        "master_slave_layout_checked": True,
        "primal_map_arrays_checked": True,
        "dual_projection_contract": (
            "project_unconstrained_mpc_dual applies the conjugate-transpose C^H "
            "of the checked primal MPC map; verified by the focused complex-map test"
        ),
        "metadata_keys_ignored": sorted(
            set(str(key) for key in saved_packet.keys()) - set(keys)
        ),
    }


__all__ = ["NATIVE_MAP_ARRAY_KEYS", "NATIVE_MAP_SEMANTICS", "compare_native_map_identity"]
