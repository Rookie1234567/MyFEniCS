"""Import/path qualification only. Never creates a mesh, form, factor or GPU context."""

import argparse
import importlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHES = (
    "TMPDIR",
    "TMP",
    "TEMP",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "FFCX_CACHE_DIR",
    "PYTHONPYCACHEPREFIX",
    "MPLCONFIGDIR",
    "TORCH_HOME",
    "HF_HOME",
    "HUGGINGFACE_HUB_CACHE",
    "TRANSFORMERS_CACHE",
    "TRITON_CACHE_DIR",
    "CUDA_CACHE_PATH",
    "NUMBA_CACHE_DIR",
    "PIP_CACHE_DIR",
    "UV_CACHE_DIR",
    "RUFF_CACHE_DIR",
    "TASK042_RESULTS_ROOT",
    "TASK042_ARTIFACT_ROOT",
)
THREADS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("preflight output must stay in NN-Lab")
    if os.environ.get("TASK042_ACTIVATION") != "1":
        raise ValueError("source the Task042 activation first")
    mode = os.environ["TASK042_ENV_MODE"]
    expected_venv = ROOT / (".venv-ml" if mode == "ml" else ".venv")
    if Path(sys.prefix) != expected_venv or Path.cwd().resolve() != ROOT:
        raise ValueError("Python/cwd does not belong to the new worktree")
    if any(os.environ.get(key) != "1" for key in THREADS):
        raise ValueError("all math thread limits must equal one")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("F0 does not allow a visible GPU")
    caches = {}
    for key in CACHES:
        path = Path(os.environ[key])
        if not path.resolve().is_relative_to(ROOT) or not path.is_dir():
            raise ValueError(f"cache/output path not isolated: {key}")
        caches[key] = str(path)
    record = {
        "schema": "task042.environment.v1",
        "utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "python": sys.executable,
        "prefix": sys.prefix,
        "python_version": sys.version,
        "host": platform.node(),
        "kernel": platform.release(),
        "cwd": str(ROOT),
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], text=True
        ),
        "affinity": sorted(os.sched_getaffinity(0)),
        "caches": caches,
        "threads": {key: os.environ[key] for key in THREADS},
        "modules": {},
        "fe_jit": False,
        "gpu_context": False,
    }
    names = ["numpy", "src", "src.solvers.coarse_inverse_protocol"]
    if mode == "fe":
        names += [
            "scipy",
            "basix",
            "ufl",
            "ffcx",
            "mpi4py",
            "petsc4py",
            "dolfinx",
            "dolfinx_mpc",
            "setuptools",
            "cffi",
            "pyvista",
            "src.solvers.dtn_port_3d",
            "src.runners.task042_experiment",
        ]
    elif mode == "ml":
        names += ["torch"]
    for name in names:
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if name.startswith("src") and not path.is_relative_to(ROOT):
            raise ValueError("src import escaped NN-Lab")
        record["modules"][name] = {
            "path": str(path),
            "version": getattr(module, "__version__", None),
        }
    if mode == "fe":
        import numpy as np
        from dolfinx import jit
        from mpi4py import MPI
        from petsc4py import PETSc

        if PETSc.ScalarType != np.complex128 or PETSc.IntType != np.int64:
            raise ValueError("expected qualified complex128/int64 stack")
        if MPI.COMM_WORLD.size != 1:
            raise ValueError("Task042 first round requires MPI1")
        jit_cache = Path(jit.get_options()["cache_dir"]).resolve()
        if not jit_cache.is_relative_to(ROOT):
            raise ValueError("actual DOLFINx JIT cache escaped NN-Lab")
        record["abi"] = {
            "scalar": str(np.dtype(PETSc.ScalarType)),
            "integer": str(np.dtype(PETSc.IntType)),
            "mpi_size": MPI.COMM_WORLD.size,
            "petsc_version": list(PETSc.Sys.getVersion()),
            "mpi_library": MPI.Get_library_version(),
            "jit_cache": str(jit_cache),
        }
    if mode == "ml":
        import torch

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        if torch.cuda.is_initialized() or torch.version.cuda is not None:
            raise ValueError("F0 ML qualification uses CPU-only Torch")
        record["ml"] = {
            "torch_version": torch.__version__,
            "cuda_build": torch.version.cuda,
            "default_dtype": str(torch.get_default_dtype()),
            "candidate_dtype": "float64 real/imag; no model created",
        }
    libraries = sorted(
        {
            line.split()[-1]
            for line in Path("/proc/self/maps").read_text().splitlines()
            if "/" in line
            and any(
                key in line
                for key in (
                    "petsc",
                    "dolfin",
                    "basix",
                    "libmpi",
                    "blas",
                    "libtorch",
                    "libcuda",
                )
            )
        }
    )
    record["loaded_libraries"] = libraries
    if mode != "fe" and any(
        "libpetsc" in p or "libdolfin" in p or "libmpi." in p for p in libraries
    ):
        raise ValueError("FE dynamic libraries leaked into pure/ML environment")
    record["status"] = "IMPORT_PATH_ABI_PASS" if mode == "fe" else "IMPORT_PATH_PASS"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    print(json.dumps({"status": record["status"], "mode": mode, "output": str(output)}))


if __name__ == "__main__":
    main()
