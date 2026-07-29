from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


SOURCE_SHA = "f1ba5627f163da54fa383b43be58fd38c0da7bc9"
NUMERICAL_ROOT = Path("/tmp/myfenics-task035e-selected-p-f1ba5627")
REFERENCE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
RAW_TENSOR_CACHE = Path(
    "/home/Projects/MyFEniCS/benchmarks/artifacts/task035e/"
    "formal_f1ba562_reference_blind_v28/runtime/tensor-cache"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise RuntimeError("Task035e fast sprint candidates require MPI8")
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified WSL activation is required")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("PETSc scalar type is not complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("PETSc integer type is not int32")

    plan = args.plan.resolve()
    run_dir = args.run_dir.resolve()
    if comm.rank == 0:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=NUMERICAL_ROOT,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=NUMERICAL_ROOT,
            text=True,
        ).strip()
        preflight = (
            head == SOURCE_SHA
            and not status
            and plan.is_file()
            and file_sha256(plan) == args.plan_sha256
            and not run_dir.exists()
        )
    else:
        preflight = None
    if not comm.bcast(preflight, root=0):
        raise RuntimeError("clean-source, plan, or immutable-output preflight failed")

    sys.path.insert(0, str(NUMERICAL_ROOT))
    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    base = target_stage4_config(degree=6, h_nm=20.0)
    cfg = replace(
        base,
        polarization_kind="s",
        custom_polarization=None,
        stage4_full3d_assembly_backend="assembly_time_variable_p_condensed",
        stage4_raw_tensor_cache_directory=str(RAW_TENSOR_CACHE),
        stage4_raw_tensor_cache_namespace=f"git-{SOURCE_SHA}",
        stage4_local_h_refinement_plan=str(plan),
        petsc_direct_solver_profile="default",
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=True,
        full3d_reference_plane_z=REFERENCE_PLANES_NM,
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    )
    result = run_stage4b_block_grating_3d_case(cfg, run_dir)
    if comm.rank == 0:
        print(
            {
                "status": result.get("case_status"),
                "official_result": result.get("official_result"),
                "elapsed_seconds": result.get("elapsed_seconds"),
            },
            flush=True,
        )


if __name__ == "__main__":
    main()
