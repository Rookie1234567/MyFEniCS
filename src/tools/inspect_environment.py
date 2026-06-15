from __future__ import annotations

import importlib.util

import numpy as np
from petsc4py import PETSc

import dolfinx


def _version(module_name: str) -> str:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return "NOT_INSTALLED"
    module = __import__(module_name)
    return str(getattr(module, "__version__", "unknown"))


def main() -> None:
    print(f"PETSc ScalarType = {PETSc.ScalarType}")
    print(f"is_complex = {np.issubdtype(PETSc.ScalarType, np.complexfloating)}")
    print(f"dolfinx = {getattr(dolfinx, '__version__', 'unknown')}")
    for module_name in ["dolfinx_mpc", "gmsh", "pyvista", "scipy", "matplotlib"]:
        print(f"{module_name} = {_version(module_name)}")


if __name__ == "__main__":
    main()

