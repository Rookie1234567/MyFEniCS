"""Independent frozen-array checker; never trusts solver status or online loss."""

import numpy as np


def require_inventory(rows):
    required = {(i, r) for i in range(8) for r in ("R0", "R-LIN", "R-NN")}
    actual = [(r["sample"], r["route"]) for r in rows if r["split"] == "heldout"]
    if len(actual) != len(required) or set(actual) != required:
        raise ValueError("complete distinct eight-RHS / three-route frozen inventory")
    return True


def audit_state(matrix, z, rhs, error, independent, slaves, *, applied=None):
    rn, en = float(np.linalg.norm(rhs)), float(np.linalg.norm(error[independent]))
    residual = float(np.linalg.norm(rhs - (matrix @ z if applied is None else applied)))
    coefficient = float(np.linalg.norm(z[independent] - error[independent]))
    constraint = float(np.linalg.norm(z[slaves]))
    rho = residual / rn if rn else (0.0 if residual == 0 else None)
    eta = coefficient / en if en else (0.0 if coefficient == 0 else None)
    passed = (
        rho is not None
        and eta is not None
        and rho <= 1e-6
        and eta <= 1e-4
        and constraint == 0.0
    )
    return {
        "residual_numerator": residual,
        "rhs_norm": rn,
        "rho": rho,
        "coefficient_error_numerator": coefficient,
        "coefficient_reference_norm": en,
        "eta": eta,
        "slave_norm": constraint,
        "passed": passed,
        "numerical_gate": "finite algebra only; not full target physics",
    }
