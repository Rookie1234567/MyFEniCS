"""Read-only reuse of the qualified NumPy-1.26 SciPy binary stack in ML.

Only scipy (and the pure threadpool inspection tool) can use this finder.
The FE site directory is never exposed, and PETSc/MPI remain absent in ML.
No package installation, ABI upgrade or environment modification occurs.
"""

import importlib.abc
import importlib.machinery
import os
import sys

import numpy as np


class ExistingSparseStack(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in ("scipy", "threadpoolctl"):
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
