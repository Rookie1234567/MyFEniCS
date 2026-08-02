"""Task036 R1a full-interface discrete-Bloch feasibility fixture.

This runner reuses the existing one-cell local factor setup.  The augmented
sparse polynomial is the actual solver path; batched Schur action is used only
to verify its eliminated residual.  It is a feasibility fixture, not a B1
capacity or production propagation solver.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from slepc4py import SLEPc

from benchmarks.run_task036_transfer_optimal_port_capacity import (
    _build_d1_local_factor_setup,
)
from src.solvers.one_cell_discrete_bloch import (
    bloch_polynomial_action,
    build_augmented_bloch_polynomial,
)


ROOT = Path(__file__).resolve().parents[1]


def _git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _groups(values: list[complex], *, reciprocal: bool) -> list[dict[str, Any]]:
    groups = []
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            metric = (
                abs(values[left] * values[right] - 1.0)
                if reciprocal
                else abs(values[left] - values[right])
            )
            scale = max(
                1.0,
                abs(values[left] * values[right]) if reciprocal else abs(values[left]),
                abs(values[right]),
            )
            if metric / scale <= 1.0e-6:
                groups.append(
                    {
                        "indices": [left, right],
                        "relative_error": float(metric / scale),
                    }
                )
    return groups


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--nev", type=int, default=2)
    parser.add_argument("--max-it", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise SystemExit("R1a feasibility fixture is fixed to MPI1.")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise SystemExit("R1a feasibility fixture requires PETSc complex128.")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise SystemExit("R1a feasibility fixture requires PETSc int32.")
    if args.nev < 1 or args.max_it < 1:
        raise SystemExit("nev and max-it must be positive.")
    source_sha = _git("rev-parse", "HEAD")
    if source_sha != args.verified_clean_sha:
        raise SystemExit(f"Source SHA {source_sha} != {args.verified_clean_sha}.")
    dirty = _git(
        "status", "--short", "--untracked-files=all", "--", "src", "benchmarks"
    )

    started = time.perf_counter()
    work_parent = args.work_dir.resolve()
    work_parent.mkdir(parents=True, exist_ok=True)
    work_dir = tempfile.TemporaryDirectory(prefix="task036-r1a-", dir=work_parent)
    setup: dict[str, Any] | None = None
    action = None
    augmented = None
    pep = None
    vector = None
    try:
        setup = _build_d1_local_factor_setup(
            work_dir,
            endpoint_comms=(MPI.COMM_NULL, MPI.COMM_NULL),
        )
        action = setup["cell_action"]
        if action.left_rows != 1200 or action.right_rows != 1200:
            raise RuntimeError(
                "Full-interface endpoint rows are not exactly 1200+1200."
            )
        augmented = build_augmented_bloch_polynomial(action)
        if augmented.state_rows != 3240:
            raise RuntimeError(
                f"Unexpected augmented state rows: {augmented.state_rows}."
            )

        pep = SLEPc.PEP().create(comm=PETSc.COMM_WORLD)
        pep.setOperators([augmented.K0, augmented.K1, augmented.K2])
        pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
        pep.setType(SLEPc.PEP.Type.TOAR)
        pep.setDimensions(nev=args.nev)
        pep.setTarget(1.0)
        pep.setWhichEigenpairs(SLEPc.PEP.Which.TARGET_MAGNITUDE)
        pep.setTolerances(tol=1.0e-8, max_it=args.max_it)
        spectral_transform = pep.getST()
        spectral_transform.setType(SLEPc.ST.Type.SINVERT)
        ksp = spectral_transform.getKSP()
        ksp.setType(PETSc.KSP.Type.PREONLY)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.LU)
        pc.setFactorSolverType("mumps")
        pep.solve()

        converged = int(pep.getConverged())
        vector = augmented.K0.createVecRight()
        candidates = []
        multipliers: list[complex] = []

        def sparse_apply(operator: PETSc.Mat, values: np.ndarray) -> np.ndarray:
            input_vector = operator.createVecRight()
            output_vector = operator.createVecLeft()
            try:
                input_vector.array[:] = values
                operator.mult(input_vector, output_vector)
                return np.asarray(output_vector.array, dtype=np.complex128).copy()
            finally:
                output_vector.destroy()
                input_vector.destroy()

        def matrix_record(operator: PETSc.Mat) -> dict[str, Any]:
            info = operator.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
            return {
                "type": str(operator.getType()),
                "shape": [int(value) for value in operator.getSize()],
                "nnz": int(info.get("nz_used", 0.0)),
                "memory_bytes": int(info.get("memory", 0.0)),
            }

        for index in range(converged):
            multiplier = complex(pep.getEigenpair(index, vector))
            state = np.asarray(vector.array, dtype=np.complex128).copy()
            K0_state = sparse_apply(augmented.K0, state)
            K1_state = sparse_apply(augmented.K1, state)
            K2_state = sparse_apply(augmented.K2, state)
            full_residual = K0_state + multiplier * K1_state + multiplier**2 * K2_state
            full_scale = (
                np.linalg.norm(K0_state)
                + abs(multiplier) * np.linalg.norm(K1_state)
                + abs(multiplier) ** 2 * np.linalg.norm(K2_state)
            )
            values = state[: action.left_rows].reshape(action.left_rows, 1)
            k0, k1, k2 = bloch_polynomial_action(action, values)
            schur_residual = k0[:, 0] + multiplier * k1[:, 0] + multiplier**2 * k2[:, 0]
            schur_scale = (
                np.linalg.norm(k0)
                + abs(multiplier) * np.linalg.norm(k1)
                + abs(multiplier) ** 2 * np.linalg.norm(k2)
            )
            multipliers.append(multiplier)
            candidates.append(
                {
                    "lambda": _complex_pair(multiplier),
                    "full_augmented_relative_residual": float(
                        np.linalg.norm(full_residual) / max(full_scale, 1.0e-30)
                    ),
                    "schur_polynomial_relative_residual": float(
                        np.linalg.norm(schur_residual) / max(schur_scale, 1.0e-30)
                    ),
                    "endpoint_vector_norm_fraction": float(
                        np.linalg.norm(values) / max(np.linalg.norm(state), 1.0e-30)
                    ),
                    "slepc_relative_error": float(
                        pep.computeError(index, SLEPc.PEP.ErrorType.RELATIVE)
                    ),
                }
            )

        max_residual = max(
            (
                max(
                    item["full_augmented_relative_residual"],
                    item["schur_polynomial_relative_residual"],
                )
                for item in candidates
            ),
            default=float("inf"),
        )
        payload = {
            "schema_version": "task036.r1a-full-interface-bloch.v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": (
                "r1a_fixture_complete"
                if candidates and max_residual <= 1.0e-7
                else "r1a_fixture_no_qualified_candidate"
            ),
            "capacity_claim": "not_run",
            "source": {
                "sha": source_sha,
                "branch": _git("branch", "--show-current"),
                "petsc_int_type": str(np.dtype(PETSc.IntType)),
                "clean_src_benchmarks": not bool(dirty),
                "working_tree_status": dirty,
            },
            "solver": {
                "type": "SLEPc.PEP/TOAR with sparse augmented coefficients",
                "st_type": str(spectral_transform.getType()),
                "ksp_type": str(ksp.getType()),
                "pc_type": str(pc.getType()),
                "factor_solver_type": pc.getFactorSolverType(),
                "nev": int(args.nev),
                "max_it": int(args.max_it),
                "converged": converged,
                "iteration_number": int(pep.getIterationNumber()),
                "convergence_reason": int(pep.getConvergedReason()),
            },
            "polynomial": {
                "equation": "S_RL + lambda*(S_RR + S_LL) + lambda^2*S_LR",
                "candidates": candidates,
                "reciprocal_groups": _groups(multipliers, reciprocal=True),
                "near_degenerate_groups": _groups(multipliers, reciprocal=False),
            },
            "objects": {
                "state_rows": int(augmented.state_rows),
                "endpoint_rows": [int(action.left_rows), int(action.right_rows)],
                "interior_rows": int(action.interior_rows),
                "interior_matrix_nnz": int(action.interior_matrix_nnz),
                "sparse_polynomial_matrices": [
                    matrix_record(operator)
                    for operator in (augmented.K0, augmented.K1, augmented.K2)
                ],
                "resident_dense_interface_square_formed": bool(
                    augmented.dense_interface_square_formed
                ),
                "resident_full_interface_square_shape": None,
                "resident_transfer_matrix": False,
            },
            "timing_seconds": {"wall": float(time.perf_counter() - started)},
            "resource": {
                "ru_maxrss_kib": int(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                ),
                "rss_scope": "MPI1 process lifetime peak; not process-tree sampler",
                "swap": "not measured by this fixture",
            },
        }
        if comm.rank == 0:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    finally:
        if vector is not None:
            vector.destroy()
        if pep is not None:
            pep.destroy()
        if augmented is not None:
            augmented.destroy()
        if action is not None:
            action.destroy()
        if setup is not None:
            setup["condensed"].destroy()
            mpc = setup["one_cell_floquet"].mpc
            if hasattr(mpc, "destroy"):
                mpc.destroy()
        work_dir.cleanup()


if __name__ == "__main__":
    main()
