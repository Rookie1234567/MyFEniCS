"""Independent saved-matrix checks used by the workstation review CLI."""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy import sparse


def review_saved_p6_residual(run_directory):
    """Audit saved native residual vectors; this does not reapply the operator.

    A completed audit can report a numerical FAIL.  The old record's `passed`
    field is retained but never substitutes for this task's 1e-10 threshold.
    """
    root = Path(run_directory).resolve()
    record_path = root / "original_full_augmented_residual.json"
    record = json.loads(record_path.read_text())
    vector_path = (root / record["vectors_file"]).resolve()
    if not vector_path.is_relative_to(root):
        raise ValueError("residual vectors escape run directory")
    digest = hashlib.sha256()
    with vector_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != record["vectors_sha256"]:
        raise ValueError("saved residual archive hash mismatch")
    norms = {}
    with np.load(vector_path, allow_pickle=False) as arrays:
        if set(arrays.files) != set(record["saved_members"]):
            raise ValueError("saved residual member coverage mismatch")
        for name, expected in record["saved_members"].items():
            values = arrays[name]
            if (values.dtype != np.dtype("complex128")
                    or list(values.shape) != expected["shape"]
                    or not np.isfinite(values).all()):
                raise ValueError("invalid saved residual member: " + name)
            payload = hashlib.sha256(
                np.ascontiguousarray(values, dtype="<c16").view(np.uint8)
            ).hexdigest()
            if payload != expected["payload_sha256"]:
                raise ValueError("saved residual member hash mismatch: " + name)
            norms[name] = float(np.linalg.norm(values))
    if norms["rhs"] <= 0:
        raise ValueError("finite nonzero original RHS required")
    relative = float(np.hypot(norms["residual"], norms["auxiliary_residual"]) / norms["rhs"])
    if not np.isclose(relative, record["relative_residual"], rtol=1e-12, atol=0):
        raise ValueError("saved vector norms disagree with original record")
    return {
        "audit_completed": True,
        "scope": "hash and saved residual norm recomputation; no fresh FE/operator/factor",
        "source_record": str(record_path),
        "source_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "vectors_file": str(vector_path), "vectors_sha256": digest.hexdigest(),
        "member_norms": norms, "relative_residual": relative,
        "required_relative_residual": 1e-10,
        "numerical_pass": bool(relative <= 1e-10),
        "old_passed_field": record.get("passed"),
        "physical_qualification": "NOT_COMPLETED",
        "official": False,
    }


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
