"""Independent saved-matrix checks used by the workstation review CLI."""
from pathlib import Path

import numpy as np
from scipy import sparse


def review_saved_n2_pair(pair_map_path, pair_l_path, original_operator, *, in_process_relative):
    """Recompute the saved N=2 local-to-global operator identity, if available."""
    map_path, local_path = Path(pair_map_path), Path(pair_l_path)
    missing = [path.name for path in (map_path, local_path) if not path.is_file()]
    if missing:
        return {
            "status": "NOT_RECOMPUTABLE_MISSING_SAVED_LOCAL_MATRICES",
            "missing_files": missing,
            "in_process_n2_operator_relative": in_process_relative,
            "independent_operator_relative": None,
        }

    pair_map = sparse.load_npz(map_path).tocsr()
    local = sparse.load_npz(local_path).tocsr()
    expected = original_operator.tocsr(copy=True)
    difference = (pair_map.T @ local @ pair_map - expected).tocsr()
    difference.sum_duplicates()
    difference.eliminate_zeros()
    expected.eliminate_zeros()
    relative = float(
        np.linalg.norm(difference.data)
        / max(np.linalg.norm(expected.data), np.finfo(float).tiny)
    )
    if not np.isfinite(relative) or relative >= 1e-12:
        raise AssertionError(
            f"independently recomputed N=2 local operator mismatch: {relative}"
        )
    return {
        "status": "INDEPENDENT_N2_LOCAL_MATRIX_RECOMPUTATION_PASS",
        "missing_files": [],
        "in_process_n2_operator_relative": in_process_relative,
        "independent_operator_relative": relative,
    }
