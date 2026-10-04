"""Read-only reuse of the qualified NumPy-1.26 SciPy binary stack in ML.

Only scipy (and the pure threadpool inspection tool) can use this finder.
The FE site directory is never exposed, and PETSc/MPI remain absent in ML.
No package installation, ABI upgrade or environment modification occurs.
"""

import ctypes
import importlib.abc
import importlib.machinery
import os
import sys
from pathlib import Path

import numpy as np


class ExistingSparseStack(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] != "scipy":
            return None
        return importlib.machinery.PathFinder.find_spec(
            fullname, path if path is not None else ["/usr/lib/python3/dist-packages"]
        )


if os.environ.get("TASK042_ENV_MODE") == "ml":
    if np.__version__ != "1.26.4" or os.environ.get("LD_LIBRARY_PATH"):
        raise RuntimeError("qualified isolated ML NumPy/loader identity")
    sys.meta_path.append(ExistingSparseStack())

from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import LinearOperator, gmres

__all__ = ["LinearOperator", "coo_matrix", "csr_matrix", "gmres"]


def loaded_math_threads():
    """Inspect already-loaded pools without a missing optional package.

    No FE runtime or new native library prefix is loaded. This is the same
    read-only OpenBLAS query used by the qualified historical runner, extended
    to the already-loaded Torch OpenMP runtime.
    """
    pools = []
    paths = sorted(
        {
            line.split()[-1]
            for line in Path("/proc/self/maps").read_text().splitlines()
            if line.split()[-1].startswith("/")
            and any(n in line for n in ("openblas", "libgomp", "libiomp"))
        }
    )
    for path in paths:
        library = ctypes.CDLL(path)
        names = (
            "openblas_get_num_threads",
            "openblas_get_num_threads64_",
            "scipy_openblas_get_num_threads",
            "scipy_openblas_get_num_threads64_",
            "omp_get_max_threads",
        )
        for name in names:
            if hasattr(library, name):
                function = getattr(library, name)
                function.restype = ctypes.c_int
                count = int(function())
                if count != 1:
                    raise RuntimeError("actual loaded BLAS/OpenMP threads exceed one")
                pools.append({"path": path, "symbol": name, "threads": count})
                break
        else:
            raise RuntimeError("loaded math pool cannot be verified")
    if not pools:
        raise RuntimeError("no verifiable loaded native math pools")
    return pools
