"""Run focused tests in the ML interpreter, borrowing pure pytest tooling only.

No FE site directory is added to sys.path. The allowlist cannot load PETSc,
MPI, NumPy, SciPy or any other native dependency from the FE environment.
"""

import importlib.abc
import importlib.machinery
import json
import os
import sys
from pathlib import Path


class PureTestTools(importlib.abc.MetaPathFinder):
    allowed = (
        "pytest",
        "_pytest",
        "pluggy",
        "iniconfig",
        "pygments",
        "py",
        "attr",
        "attrs",
    )

    def __init__(self, root):
        self.root = root

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in self.allowed:
            return None
        return importlib.machinery.PathFinder.find_spec(
            fullname,
            path
            if path is not None
            else [str(self.root), "/usr/lib/python3/dist-packages"],
        )


def main():
    import numpy
    import torch

    import src.solvers.isolated_ml_sparse  # noqa: F401
    from src.solvers.neighborhood_residual_models import configure_threads

    configure_threads()
    root = Path(__file__).resolve().parents[1]
    site = (
        root
        / ".venv/lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    sys.meta_path.append(PureTestTools(site))
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest

    print(
        json.dumps(
            {
                "testing_tool": pytest.__file__,
                "ML_executable": sys.executable,
                "Torch": torch.__file__,
                "NumPy": numpy.__file__,
                "borrowed_only": sorted(PureTestTools.allowed),
            }
        ),
        flush=True,
    )
    code = pytest.main(sys.argv[1:])
    if any(n in sys.modules for n in ("petsc4py", "mpi4py", "dolfinx")):
        raise RuntimeError("FE ABI entered ML tests")
    return code


if __name__ == "__main__":
    sys.exit(main())
