"""MPI1 component evidence for retained and streaming Woodbury storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task034_wsl_resources import resource_authority_sample
from src.solvers.hybrid_local_dtn_woodbury import (
    create_research_exact_side_lu_action,
)

ROWS = 64
MODES = 32
RHS_COUNT = 4
FIXTURE_SEED = 5395


def _array_sha256(values: np.ndarray) -> str:
    payload = np.ascontiguousarray(values, dtype=np.complex128).view(np.uint8)
    return hashlib.sha256(payload.tobytes()).hexdigest()


def _pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _pairs(values: np.ndarray) -> list[list[float]]:
    return [_pair(complex(value)) for value in np.asarray(values).ravel()]


def _matrix_from_dense(values: np.ndarray, comm: MPI.Comm) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(values.shape, comm=comm)
    matrix.setUp()
    first, last = (int(value) for value in matrix.getOwnershipRange())
    columns = np.arange(values.shape[1], dtype=PETSc.IntType)
    for row in range(first, last):
        matrix.setValues(row, columns, values[row])
    matrix.assemble()
    return matrix


def _synthetic_fixture() -> dict[str, Any]:
    rng = np.random.default_rng(FIXTURE_SEED)
    f_diag = 2.0 + 0.01 * np.arange(ROWS) + 0.04j
    h_diag = 3.0 + 0.02 * np.arange(MODES) + 0.03j
    F = np.diag(np.asarray(f_diag, dtype=np.complex128))
    H = np.diag(np.asarray(h_diag, dtype=np.complex128))
    C = 0.004 * (
        rng.standard_normal((ROWS, MODES)) + 1j * rng.standard_normal((ROWS, MODES))
    )
    D = 0.004 * (
        rng.standard_normal((MODES, ROWS)) + 1j * rng.standard_normal((MODES, ROWS))
    )
    rhs = rng.standard_normal((RHS_COUNT, ROWS)) + 1j * rng.standard_normal(
        (RHS_COUNT, ROWS)
    )
    return {
        "F": F,
        "C": C,
        "D": D,
        "H": H,
        "rhs": np.asarray(rhs, dtype=np.complex128),
    }


def _batch_size(value: str) -> int | None:
    if value == "retained":
        return None
    batch = int(value)
    if batch not in (8, 16, 32):
        raise ValueError("batch-size must be retained, 8, 16, or 32")
    return batch


def _vector_from_values(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    return vector


def _run_case(case: str, output: str, audit_source_sha: str) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError(f"This component requires MPI1, got {comm.size}")
    batch = _batch_size(case)
    fixture = _synthetic_fixture()
    effective = fixture["F"] - fixture["C"] @ np.linalg.solve(
        fixture["H"], fixture["D"]
    )
    matrices = {
        name: _matrix_from_dense(fixture[name], comm) for name in ("F", "C", "D", "H")
    }
    components = SimpleNamespace(**matrices)
    action = None
    destroyed: set[str] = set()
    rhs_results: list[dict[str, Any]] = []
    setup_started = time.perf_counter()
    try:
        action = create_research_exact_side_lu_action(
            matrices["F"],
            components,
            factor_solver_type="mumps",
            qualification_scope="task039_v5_streaming_component_mpi1",
            explicit_opt_in=True,
            factor_only_storage=True,
            streaming_w_batch_size=batch,
        )
        operator = action.operator
        if operator is None:
            raise RuntimeError("factor-only action did not retain an operator")
        for index, rhs in enumerate(fixture["rhs"]):
            source = _vector_from_values(operator, rhs)
            target = operator.createVecLeft()
            try:
                action.apply(source, target)
                actual = np.asarray(
                    target.getArray(readonly=True), dtype=np.complex128
                ).copy()
                reference = np.linalg.solve(effective, rhs)
                error = float(np.linalg.norm(actual - reference)) / max(
                    float(np.linalg.norm(reference)), 1.0e-30
                )
                rhs_results.append(
                    {
                        "index": index,
                        "relative_error": error,
                        "output_real_imag": _pairs(actual),
                    }
                )
            finally:
                target.destroy()
                source.destroy()
        pre_destroy = action.diagnostics
        woodbury = pre_destroy["woodbury"]
        action.destroy()
        post_destroy = action.diagnostics
        for name in ("F", "H", "D"):
            matrices[name].destroy()
            destroyed.add(name)
        if batch is None:
            matrices["C"].destroy()
            destroyed.add("C")
        matrices_released = {name: True for name in ("F", "H", "D")}
        matrices_released["C"] = (
            True
            if batch is None
            else bool(post_destroy["woodbury"]["C_action_released"])
        )
        current = resource_authority_sample(os.getpid())
        usage = resource.getrusage(resource.RUSAGE_SELF)
        elapsed = float(time.perf_counter() - setup_started)
        result = {
            "schema": "task039.v5-5-streaming-woodbury-component.v1",
            "status": "completed",
            "execution": {
                "mpi_world_size": 1,
                "storage_case": case,
                "streaming_w_batch_size": batch,
                "process_tree_scope": "single_process_mpi1_no_children",
                "audit_source_sha": audit_source_sha,
            },
            "fixture": {
                "seed": FIXTURE_SEED,
                "rows": ROWS,
                "modes": MODES,
                "rhs_count": RHS_COUNT,
                "dtype": "complex128",
                "matrix_sha256": {
                    name: _array_sha256(fixture[name]) for name in ("F", "C", "D", "H")
                },
                "rhs_sha256": _array_sha256(fixture["rhs"]),
            },
            "rhs_results": rhs_results,
            "max_relative_error": max(item["relative_error"] for item in rhs_results),
            "woodbury": {
                "K_rank": woodbury["K_rank"],
                "K_condition_number": woodbury["K_condition_number"],
                "K_shape": woodbury["K_shape"],
                "K_nbytes": woodbury["K_nbytes"],
                "LU_shape": woodbury["LU_shape"],
                "LU_nbytes": woodbury["LU_nbytes"],
                "W_resident": woodbury["W_resident"],
                "W_local_shape": woodbury["W_local_shape"],
                "W_local_nbytes": woodbury["W_local_nbytes"],
                "batch_peak_bytes": woodbury["streaming_w_batch_peak_bytes"],
                "batch_local_peak_bytes": woodbury[
                    "streaming_w_batch_local_peak_bytes"
                ],
                "batch_peak_scope": woodbury["streaming_w_batch_peak_scope"],
                "setup_seconds": woodbury["setup_seconds"],
                "apply_seconds": woodbury["apply_seconds"],
            },
            "counts": {
                "setup_factor_solves": woodbury["setup_factor_solve_count"],
                "setup_D_applies": woodbury["setup_d_apply_count"],
                "apply_base_factor_solves": woodbury["apply_base_solve_count"],
                "apply_D": woodbury["apply_D_count"],
                "apply_C": woodbury["apply_C_count"],
                "factor_total_solves": pre_destroy["local_direct_solve_count"],
            },
            "destroy": {
                "factor_count_after_destroy": post_destroy["direct_factor_count"],
                "action_destroyed": post_destroy["destroyed"],
                "C_action_released": post_destroy["woodbury"]["C_action_released"],
                "matrices_released": matrices_released,
                "ownership": {
                    "by_action": ["C"] if batch is not None else [],
                    "by_caller": ["F", "H", "D"] + ([] if batch is not None else ["C"]),
                },
            },
            "resources": {
                "ru_maxrss_bytes": int(usage.ru_maxrss) * 1024,
                "ru_maxrss_mib": float(usage.ru_maxrss) / 1024.0,
                "ru_maxrss_scope": "Linux RUSAGE_SELF lifetime peak; MPI1 process-tree",
                "current_authority": current,
                "current_rss_bytes": current["process_tree"]["rss_bytes"],
                "current_swap_bytes": current["process_tree"]["swap_bytes"],
            },
            "internal_wall_seconds": elapsed,
            "gates": {
                "relative_error_le_1e-10": max(
                    item["relative_error"] for item in rhs_results
                )
                <= 1.0e-10,
                "finite_outputs": all(
                    np.all(
                        np.isfinite(
                            np.asarray(item["output_real_imag"], dtype=np.float64)
                        )
                    )
                    for item in rhs_results
                ),
            },
        }
    finally:
        if action is not None and not action.diagnostics["destroyed"]:
            action.destroy()
        for name, matrix in matrices.items():
            if name == "C" and components.C is None:
                continue
            if name not in destroyed:
                matrix.destroy()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size", choices=("retained", "8", "16", "32"), required=True
    )
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--audit-source-sha", required=True)
    args = parser.parse_args()
    _run_case(args.batch_size, args.output, args.audit_source_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
