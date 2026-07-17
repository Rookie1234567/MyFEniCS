from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import time
from typing import Any

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator
from src.solvers.local_slab_solver import ScipyCsrAction


SCHEMA = "myfenics.task005.representative_ilu_holdout.v1"


def _stats(values: np.ndarray) -> dict[str, float]:
    samples = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(samples)),
        "median": float(np.median(samples)),
        "p95": float(np.quantile(samples, 0.95)),
        "max": float(np.max(samples)),
    }


def _vmstat() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines():
        key, value = line.split()
        if key in {"pswpin", "pswpout"}:
            values[key] = int(value)
    return values


def _load_holdout(directory: Path) -> np.ndarray:
    with np.load(directory / "samples.npz", allow_pickle=False) as payload:
        split = payload["split"].astype(str)
        rhs = np.asarray(payload["rhs"], dtype=np.complex128)
    selected = rhs[split == "holdout"]
    if selected.shape[0] != 256:
        raise ValueError(f"{directory} requires exactly 256 holdout RHS")
    return selected


def _build_one(directory: Path, output: Path) -> dict[str, Any]:
    from petsc4py import PETSc

    operator = load_operator(directory)
    rhs = _load_holdout(directory)
    matrix = PETSc.Mat().createAIJ(
        size=operator.shape,
        csr=(
            np.asarray(operator.indptr, dtype=PETSc.IntType),
            np.asarray(operator.indices, dtype=PETSc.IntType),
            np.asarray(operator.values, dtype=PETSc.ScalarType),
        ),
        comm=PETSc.COMM_SELF,
    )
    ksp = PETSc.KSP().create(PETSc.COMM_SELF)
    ksp.setOperators(matrix)
    ksp.setType("preonly")
    pc = ksp.getPC()
    pc.setType("ilu")
    pc.setFactorLevels(0)
    pc.setFactorOrdering("rcm")
    before_swap = _vmstat()
    setup_started = time.perf_counter()
    ksp.setUp()
    setup_s = time.perf_counter() - setup_started
    factor_nnz = int(pc.getFactorMatrix().getInfo()["nz_used"])
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    correction = np.empty_like(rhs)
    elapsed = np.empty(rhs.shape[0], dtype=np.float64)
    for index, row in enumerate(rhs):
        source.getArray()[:] = row
        target.set(0.0)
        started = time.perf_counter()
        ksp.solve(source, target)
        elapsed[index] = time.perf_counter() - started
        correction[index] = target.getArray(readonly=True)
    action = ScipyCsrAction(operator)
    residual = rhs - action.action_many(correction)
    rho = np.linalg.norm(residual, axis=1) / np.maximum(
        np.linalg.norm(rhs, axis=1), np.finfo(float).tiny
    )
    after_swap = _vmstat()
    if not np.all(np.isfinite(correction)) or not np.all(np.isfinite(rho)):
        raise RuntimeError("PETSc ILU holdout result contains NaN or Inf")
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "holdout.npz", rho=rho)
    result = {
        "schema": SCHEMA,
        "slab": int(operator.metadata["slab_id"]),
        "operator_fingerprint": operator.fingerprint,
        "sample_count": int(rhs.shape[0]),
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "pc_type": "ilu",
        "factor_levels": 0,
        "factor_ordering": "rcm",
        "matrix_nnz": int(operator.values.size),
        "factor_nnz": factor_nnz,
        "setup_s": setup_s,
        "solve_s": _stats(elapsed),
        "rho": _stats(rho),
        "peak_rss_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        ),
        "swap_in_pages": after_swap["pswpin"] - before_swap["pswpin"],
        "swap_out_pages": after_swap["pswpout"] - before_swap["pswpout"],
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    target.destroy()
    source.destroy()
    ksp.destroy()
    matrix.destroy()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--slabs", default="0,5,9,15")
    args = parser.parse_args()
    root = Path(args.dataset_root)
    output = Path(args.output_root)
    slabs = [int(value) for value in args.slabs.split(",")]
    rows = [
        _build_one(root / f"slab_{slab:03d}", output / f"slab_{slab:03d}")
        for slab in slabs
    ]
    summary = {
        "schema": "myfenics.task005.representative_ilu_holdout.summary.v1",
        "slabs": slabs,
        "all_finite": True,
        "rows": rows,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
