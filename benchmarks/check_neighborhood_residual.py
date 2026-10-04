"""Independent frozen-array checker; never trusts solver status or online loss."""

import numpy as np


def require_inventory(rows):
    required = {(i, r) for i in range(8) for r in ("R0", "R-LIN", "R-NN")}
    actual = [(r["sample"], r["route"]) for r in rows if r["split"] == "heldout"]
    if (
        len(rows) != len(required)
        or len(actual) != len(required)
        or set(actual) != required
    ):
        raise ValueError("complete distinct eight-RHS / three-route frozen inventory")
    return True


def require_frozen_input(arrays, expected_rhs, independent, slaves):
    """Check live DATA identity and every native row before numerical decisions."""
    expected_rhs = np.asarray(expected_rhs)
    if expected_rhs.ndim != 1:
        raise ValueError("frozen RHS must be one complete native vector")
    indices = [np.asarray(independent), np.asarray(slaves)]
    if any(a.ndim != 1 or a.dtype.kind not in "iu" for a in indices):
        raise ValueError("integer independent/slave row inventory")
    if not np.array_equal(
        np.sort(np.concatenate(indices)), np.arange(expected_rhs.size)
    ):
        raise ValueError("complete independent/slave row coverage, without duplicates")
    for name in ("rhs", "initial", "initial_residual", "z", "residual"):
        a = np.asarray(arrays[name])
        if a.shape != expected_rhs.shape or not np.isfinite(a).all():
            raise ValueError("finite complete frozen vector: " + name)
    if not np.array_equal(arrays["rhs"], expected_rhs):
        raise ValueError("saved candidate RHS differs from frozen DATA inventory")
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
