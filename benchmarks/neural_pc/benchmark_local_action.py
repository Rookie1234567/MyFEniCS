from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import time

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator
from src.solvers.local_slab_solver import ScipyCsrAction


class _PetscCsrAction:
    def __init__(self, operator) -> None:
        from petsc4py import PETSc

        self._matrix = PETSc.Mat().createAIJ(
            size=operator.shape,
            csr=(
                np.asarray(operator.indptr, dtype=PETSc.IntType),
                np.asarray(operator.indices, dtype=PETSc.IntType),
                operator.values,
            ),
            comm=PETSc.COMM_SELF,
        )
        self._source = self._matrix.createVecRight()
        self._target = self._matrix.createVecLeft()

    def action(self, vector: np.ndarray) -> np.ndarray:
        self._source.getArray()[:] = vector
        self._matrix.mult(self._source, self._target)
        return np.asarray(self._target.getArray(readonly=True), dtype=np.complex128).copy()

    def destroy(self) -> None:
        self._target.destroy()
        self._source.destroy()
        self._matrix.destroy()


def _stats(samples: list[float]) -> dict[str, float]:
    values = np.asarray(samples)
    return {
        "mean_s": float(values.mean()),
        "median_s": float(np.median(values)),
        "p95_s": float(np.quantile(values, 0.95)),
    }


def _timed(action, vectors: np.ndarray, repeats: int) -> tuple[dict[str, float], np.ndarray]:
    output = action(vectors[0])
    elapsed: list[float] = []
    for index in range(repeats):
        started = time.perf_counter()
        output = action(vectors[index % len(vectors)])
        elapsed.append(time.perf_counter() - started)
    return _stats(elapsed), output


def benchmark(directory: Path, repeats: int, seed: int) -> dict[str, object]:
    operator = load_operator(directory)
    rng = np.random.default_rng(seed)
    vectors = rng.standard_normal((16, operator.shape[1])) + 1j * rng.standard_normal(
        (16, operator.shape[1])
    )
    build_started = time.perf_counter()
    scipy_action = ScipyCsrAction(operator)
    scipy_build = time.perf_counter() - build_started
    build_started = time.perf_counter()
    petsc_action = _PetscCsrAction(operator)
    petsc_build = time.perf_counter() - build_started
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    python_stats, _ = _timed(operator.action, vectors, repeats)
    scipy_stats, scipy_output = _timed(scipy_action.action, vectors, repeats)
    petsc_stats, petsc_output = _timed(petsc_action.action, vectors, repeats)
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    final_reference = operator.action(vectors[(repeats - 1) % 16])
    error = float(
        np.linalg.norm(scipy_output - final_reference)
        / max(np.linalg.norm(final_reference), 1e-300)
    )
    petsc_error = float(
        np.linalg.norm(petsc_output - final_reference)
        / max(np.linalg.norm(final_reference), 1e-300)
    )
    petsc_action.destroy()
    return {
        "directory": str(directory),
        "slab_id": operator.metadata.get("slab_id"),
        "shape": list(operator.shape),
        "nnz": int(operator.values.size),
        "threads": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "python_row": python_stats,
        "scipy_csr": {**scipy_stats, "build_s": scipy_build, "storage_bytes": scipy_action.storage_bytes},
        "petsc_owner_matmult": {**petsc_stats, "build_s": petsc_build},
        "relative_error": error,
        "petsc_relative_error": petsc_error,
        "peak_rss_growth_kib": int(after - before),
        "mean_ratio": scipy_stats["mean_s"] / python_stats["mean_s"],
        "p95_ratio": scipy_stats["p95_s"] / python_stats["p95_s"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", nargs="+")
    parser.add_argument("--repeats", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results = [benchmark(Path(path), args.repeats, args.seed) for path in args.directories]
    payload = {"identity": "para091_local_action_microbenchmark", "results": results}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
