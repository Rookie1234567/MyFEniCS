"""At most 180 seconds, immutable old u/f: matrix versus accumulation effects."""

import json

import numpy as np

from benchmarks.check_boundary_witness import read_arrays
from src.solvers.isolated_ml_sparse import csr_matrix
from src.solvers.neighborhood_residual_scope import ROOT, parent
from src.solvers.neighborhood_residual_study import dereference, save


def decompose(folder, budget):
    from src.solvers.distributed_entity_volume import cell_transform
    from src.solvers.distributed_volume_study import element

    literal = read_arrays(dereference("bridge")["results"][0]["packets"][0]["numeric"])
    p = dereference("volume")["packets"][0]
    a = read_arrays(p["numeric"])
    el = element()
    ip = np.asarray(el.entity_dofs[3][0])
    base = ROOT / "benchmarks/artifacts/task042/v42/checkpoints"
    factory, native = [], []
    for i in range(6):
        factory.append(
            read_arrays(
                json.loads((base / f"class_{i}_tensor.json").read_text())["arrays"]
            )["raw"]
        )
        native.append(
            read_arrays(
                json.loads((base / f"class_{i}_native.json").read_text())["arrays"]
            )["raw_native"]
        )
    transforms = [
        cell_transform(el, int(info)) for info in literal["cell_permutations"]
    ]
    u = a["recovered"]

    def apply(kind):
        values = []
        for c, original in enumerate(u):
            i = int(p["metadata"]["class_ids"][c])
            t = transforms[c]
            raw = t.T @ original
            matrix = factory[i] if kind == "factory" else native[i]
            if kind == "delta":
                matrix = native[i] - factory[i]
            if kind == "extended":
                result = np.asarray(
                    matrix.astype(np.clongdouble) @ raw.astype(np.clongdouble),
                    np.complex128,
                )
            else:
                result = matrix @ raw
            values.append((t @ result)[ip])
        return np.asarray(values)

    results = {
        k: budget.call(lambda _, k=k: apply(k), u.ravel(), kind="A_saved_recovery_" + k)
        for k in ("factory", "native", "delta", "extended")
    }
    records = []
    for c in range(64):
        f = a["fi"][c]
        norm = float(np.linalg.norm(f))
        records.append(
            {
                "cell": c,
                "class": int(p["metadata"]["class_ids"][c]),
                "rhs_norm": norm,
                "factory_residual": float(
                    np.linalg.norm(results["factory"][c] - f) / norm
                ),
                "native_residual": float(
                    np.linalg.norm(results["native"][c] - f) / norm
                ),
                "matrix_difference_action": float(
                    np.linalg.norm(results["delta"][c]) / norm
                ),
                "extended_stored_binary64_residual": float(
                    np.linalg.norm(results["extended"][c] - f) / norm
                ),
                "native_accumulation_change": float(
                    np.linalg.norm(results["native"][c] - results["extended"][c]) / norm
                ),
                "split_identity_rounding": float(
                    np.linalg.norm(
                        results["native"][c]
                        - results["factory"][c]
                        - results["delta"][c]
                    )
                    / norm
                ),
            }
        )
    receipt = save(folder, "A_recovery_decomposition", **results, fi=a["fi"])
    # B uses the unchanged local oriented tensors and original assembled CSR.
    root = ROOT / "benchmarks/artifacts/task042/v40/checkpoints"
    geom = read_arrays(parent("Bgeometry")["arrays"])
    numbering = read_arrays(parent("B")["arrays"])
    system = parent("B")
    old = read_arrays(parent("Brecovery")["arrays"])
    csr = read_arrays(parent("Bcsr")["arrays"])
    matrix = csr_matrix(
        (csr["data"], csr["indices"], csr["indptr"]), shape=tuple(csr["shape"])
    )
    mats = [
        read_arrays(json.loads((root / (r["name"] + ".json")).read_text())["arrays"])[
            "original"
        ]
        for r in system["metadata"]["classes"]
    ]
    expanded = old["expanded"]
    local = np.zeros_like(old["u"])

    def local_apply(_):
        for c, rows in enumerate(geom["cell_dofs"]):
            np.add.at(
                local, rows, mats[int(numbering["cell_class"][c])] @ expanded[rows]
            )
        return local

    local = budget.call(
        local_apply, old["u"], key="B_actions", kind="B_saved_local_sum"
    )
    # Pull the literal conjugate MPC exactly as the original producer.
    pulled = np.zeros_like(local)
    for r, value in enumerate(local):
        lo, hi = geom["master_offsets"][r : r + 2]
        np.add.at(
            pulled,
            geom["master_rows"][lo:hi],
            geom["master_dual_coefficients"][lo:hi] * value,
        )
    ordinary = budget.call(
        matrix.__matmul__, old["u"], key="B_actions", kind="B_saved_CSR"
    )
    extended_matrix = matrix.astype(np.clongdouble)
    extended = budget.call(
        lambda v: np.asarray(extended_matrix @ v.astype(np.clongdouble), np.complex128),
        old["u"],
        key="B_actions",
        kind="B_saved_CSR_extended",
    )
    rhs = old["f"]
    ii = numbering["cell_interior"].ravel()
    den = float(np.linalg.norm(rhs[ii]))
    b_record = {
        "local_sum_residual": float(np.linalg.norm(pulled[ii] - rhs[ii]) / den),
        "original_CSR_residual": float(np.linalg.norm(ordinary[ii] - rhs[ii]) / den),
        "extended_binary64_CSR_residual": float(
            np.linalg.norm(extended[ii] - rhs[ii]) / den
        ),
        "local_CSR_action_difference": float(
            np.linalg.norm(pulled[ii] - ordinary[ii]) / den
        ),
        "CSR_accumulation_change": float(
            np.linalg.norm(ordinary[ii] - extended[ii]) / den
        ),
        "rhs_norm": den,
        "old_threshold": 1e-10,
    }
    return {
        "status": "SAVED_RECOVERY_ERROR_DECOMPOSED_NO_NEW_SOLVE",
        "A": records,
        "A_arrays": receipt,
        "B": b_record,
        "fixed_u_f": True,
        "new_LU_JIT_solve": 0,
        "old_FAIL_retained": True,
        "interpretation": "matrix differences and stored-matrix accumulation separated; not proof of unique cause; no integration precision added",
    }
