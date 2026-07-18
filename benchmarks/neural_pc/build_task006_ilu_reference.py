from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator
from src.solvers.local_slab_solver import ScipyCsrAction


def _build_one(
    directory: Path,
    output: Path,
    *,
    split_name: str,
) -> dict[str, Any]:
    from petsc4py import PETSc

    operator = load_operator(directory)
    with np.load(directory / "samples.npz", allow_pickle=False) as payload:
        split = payload["split"].astype(str)
        rhs = np.asarray(payload["rhs"][split == split_name], dtype=np.complex128)
    if rhs.size == 0:
        raise ValueError(f"slab dataset has no {split_name} samples")
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
    ksp.setUp()
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    correction = np.empty_like(rhs)
    started = time.perf_counter()
    for index, row in enumerate(rhs):
        source.getArray()[:] = row
        target.set(0.0)
        ksp.solve(source, target)
        correction[index] = target.getArray(readonly=True)
    solve_s = time.perf_counter() - started
    residual = rhs - ScipyCsrAction(operator).action_many(correction)
    rho = np.linalg.norm(residual, axis=1) / np.maximum(
        np.linalg.norm(rhs, axis=1), np.finfo(float).tiny
    )
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "reference.npz", rho=rho, correction=correction)
    result = {
        "schema": "myfenics.task006.ilu_reference.v1",
        "slab": int(operator.metadata["slab_id"]),
        "split": split_name,
        "sample_count": int(rhs.shape[0]),
        "operator_fingerprint": operator.fingerprint,
        "rho_min": float(np.min(rho)),
        "rho_median": float(np.median(rho)),
        "rho_p95": float(np.quantile(rho, 0.95)),
        "rho_max": float(np.max(rho)),
        "solve_s": solve_s,
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
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "holdout"), required=True)
    parser.add_argument("--slabs", default="0,5,9,15")
    args = parser.parse_args()
    slabs = tuple(int(value) for value in args.slabs.split(","))
    rows = [
        _build_one(
            args.dataset_root / f"slab_{slab:03d}",
            args.output_root / f"slab_{slab:03d}",
            split_name=args.split,
        )
        for slab in slabs
    ]
    summary = {
        "schema": "myfenics.task006.ilu_reference.summary.v1",
        "split": args.split,
        "slabs": list(slabs),
        "rows": rows,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
