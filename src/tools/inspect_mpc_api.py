from __future__ import annotations

import inspect

import dolfinx_mpc


def main() -> None:
    print(dolfinx_mpc)
    print("module public names:")
    print([name for name in dir(dolfinx_mpc) if not name.startswith("_")])
    print("MultiPointConstraint:")
    print(dolfinx_mpc.MultiPointConstraint)
    print("signature:")
    print(inspect.signature(dolfinx_mpc.MultiPointConstraint))
    print("methods:")
    print([name for name in dir(dolfinx_mpc.MultiPointConstraint) if not name.startswith("_")])
    for name in [
        "add_constraint",
        "add_constraint_from_mpc_data",
        "create_periodic_constraint_geometrical",
        "create_periodic_constraint_topological",
        "finalize",
        "backsubstitution",
    ]:
        method = getattr(dolfinx_mpc.MultiPointConstraint, name)
        print(f"{name}: {inspect.signature(method)}")
    print("LinearProblem.solve:")
    print(inspect.signature(dolfinx_mpc.LinearProblem.solve))


if __name__ == "__main__":
    main()
