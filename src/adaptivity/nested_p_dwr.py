"""Signed same-trace nested-p DWR identities for Task035d.

The enriched and coarse operators in this module use exactly the same global
trace-plus-auxiliary coordinates.  Cross-trace p-enrichment needs a separately
qualified primal prolongation and is intentionally outside this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


_AMPLITUDE_QUANTITIES = {"amplitude_real", "amplitude_imag"}
_GOAL_QUANTITIES = {*_AMPLITUDE_QUANTITIES, "power"}


def _complex_vector(
    values: np.ndarray,
    *,
    name: str,
) -> np.ndarray:
    vector = np.asarray(values, dtype=np.complex128)
    if vector.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional vector")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} contains non-finite values")
    return vector


def _complex_matrix(
    values: np.ndarray,
    *,
    name: str,
) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.complex128)
    if matrix.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional matrix")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} contains non-finite values")
    return matrix


def affine_channel_value(
    row: np.ndarray,
    offset: complex,
    state: np.ndarray,
) -> complex:
    """Evaluate the no-hidden-conjugation row functional ``row @ x + c``."""

    functional_row = _complex_vector(row, name="channel row")
    vector = _complex_vector(state, name="channel state")
    if functional_row.shape != vector.shape:
        raise ValueError("channel row and state have different sizes")
    value = complex(functional_row @ vector + complex(offset))
    if not np.isfinite(value):
        raise ValueError("affine channel value is non-finite")
    return value


def affine_goal_gradient(
    row: np.ndarray,
    *,
    quantity: str,
    value_a: complex | None = None,
    value_b: complex | None = None,
    weight: float | None = None,
) -> np.ndarray:
    """Return ``g`` for ``dJ=Re(g^H dx)`` on one affine complex channel."""

    functional_row = _complex_vector(row, name="channel row")
    if quantity not in _GOAL_QUANTITIES:
        raise ValueError(f"unsupported affine goal quantity {quantity!r}")
    if quantity == "amplitude_real":
        scalar = 1.0 + 0.0j
    elif quantity == "amplitude_imag":
        scalar = 0.0 + 1.0j
    else:
        if value_a is None or value_b is None or weight is None:
            raise ValueError(
                "power gradient requires both endpoint values and a weight"
            )
        if not np.isfinite(complex(value_a)) or not np.isfinite(
            complex(value_b)
        ):
            raise ValueError("power endpoint channel values are non-finite")
        if not np.isfinite(float(weight)) or float(weight) < 0.0:
            raise ValueError("power weight must be finite and non-negative")
        midpoint = 0.5 * (complex(value_a) + complex(value_b))
        scalar = 2.0 * float(weight) * midpoint
    gradient = np.ascontiguousarray(
        scalar * np.conj(functional_row)
    )
    gradient.setflags(write=False)
    return gradient


def unit_channel_goal_scalar(
    *,
    quantity: str,
    coordinate_scale: complex,
    boundary_phase: complex = 1.0 + 0.0j,
    power_weight: float | None = None,
    outgoing_a: complex | None = None,
    outgoing_b: complex | None = None,
) -> complex:
    """Scale one solver-coordinate unit adjoint into a real channel goal."""

    if quantity not in _GOAL_QUANTITIES:
        raise ValueError(f"unsupported unit-channel quantity {quantity!r}")
    scale = complex(coordinate_scale)
    if not np.isfinite(scale) or abs(scale) <= 0.0:
        raise ValueError("auxiliary coordinate scale is invalid")
    if quantity == "amplitude_real":
        return complex(np.conj(boundary_phase) / np.conj(scale))
    if quantity == "amplitude_imag":
        return complex(1j * np.conj(boundary_phase) / np.conj(scale))
    if (
        power_weight is None
        or outgoing_a is None
        or outgoing_b is None
    ):
        raise ValueError(
            "power unit scalar requires weight and both outgoing amplitudes"
        )
    weight = float(power_weight)
    if not np.isfinite(weight) or weight < 0.0:
        raise ValueError("power weight must be finite and non-negative")
    midpoint = 0.5 * (complex(outgoing_a) + complex(outgoing_b))
    return complex(2.0 * weight * midpoint / np.conj(scale))


def scaled_unit_adjoint_pairing(
    unit_pairing: complex,
    goal_scalar: complex,
) -> complex:
    """Return ``(gamma*z0)^H r = conj(gamma)*(z0^H r)``."""

    value = np.conj(complex(goal_scalar)) * complex(unit_pairing)
    if not np.isfinite(value):
        raise ValueError("scaled unit-adjoint pairing is non-finite")
    return complex(value)


@dataclass(frozen=True)
class CellSchurDeltaResidual:
    """One cell's signed A-minus-B condensed residual contribution."""

    local_trace: np.ndarray
    local_residual: np.ndarray
    global_residual: np.ndarray


def cell_schur_delta_residual(
    *,
    global_size: int,
    rows: np.ndarray,
    expansion: np.ndarray,
    schur_a: np.ndarray,
    schur_b: np.ndarray,
    rhs_a: np.ndarray,
    rhs_b: np.ndarray,
    state_b: np.ndarray,
) -> CellSchurDeltaResidual:
    """Build ``C^H[(fA-fB)-(SA-SB) C xB]`` with ADD semantics."""

    size = int(global_size)
    if size <= 0:
        raise ValueError("global residual size must be positive")
    selected_rows = np.asarray(rows, dtype=np.int64)
    if (
        selected_rows.ndim != 1
        or np.any(selected_rows < 0)
        or np.any(selected_rows >= size)
    ):
        raise ValueError("cell independent rows are invalid")
    constraint = _complex_matrix(expansion, name="cell expansion")
    if constraint.shape[1] != len(selected_rows):
        raise ValueError(
            "cell expansion columns do not match independent rows"
        )
    local_size = int(constraint.shape[0])
    enriched = _complex_matrix(schur_a, name="enriched cell Schur")
    coarse = _complex_matrix(schur_b, name="coarse cell Schur")
    if enriched.shape != (local_size, local_size) or coarse.shape != (
        local_size,
        local_size,
    ):
        raise ValueError("cell Schur matrices have the wrong shape")
    condensed_rhs_a = _complex_vector(rhs_a, name="enriched cell RHS")
    condensed_rhs_b = _complex_vector(rhs_b, name="coarse cell RHS")
    if condensed_rhs_a.shape != (local_size,) or condensed_rhs_b.shape != (
        local_size,
    ):
        raise ValueError("cell condensed RHS has the wrong shape")
    coarse_state = _complex_vector(state_b, name="coarse state")
    if coarse_state.shape != (size,):
        raise ValueError("coarse state has the wrong global size")

    local_trace = np.ascontiguousarray(
        constraint @ coarse_state[selected_rows]
    )
    local_residual = np.ascontiguousarray(
        condensed_rhs_a
        - condensed_rhs_b
        - (enriched - coarse) @ local_trace
    )
    reduced = np.ascontiguousarray(
        constraint.conj().T @ local_residual
    )
    global_residual = np.zeros(size, dtype=np.complex128)
    np.add.at(global_residual, selected_rows, reduced)
    for values in (local_trace, local_residual, global_residual):
        values.setflags(write=False)
    return CellSchurDeltaResidual(
        local_trace=local_trace,
        local_residual=local_residual,
        global_residual=global_residual,
    )


def operator_delta_residual(
    rhs_a: np.ndarray,
    rhs_b: np.ndarray,
    action_a_on_b: np.ndarray,
    action_b_on_b: np.ndarray,
) -> np.ndarray:
    """Return ``(bA-bB)-(KA-KB)xB`` for any operator component."""

    vectors = tuple(
        _complex_vector(values, name=name)
        for values, name in (
            (rhs_a, "enriched component RHS"),
            (rhs_b, "coarse component RHS"),
            (action_a_on_b, "enriched component action"),
            (action_b_on_b, "coarse component action"),
        )
    )
    if len({vector.shape for vector in vectors}) != 1:
        raise ValueError("operator-delta component vectors have different sizes")
    result = np.ascontiguousarray(
        vectors[0] - vectors[1] - (vectors[2] - vectors[3])
    )
    result.setflags(write=False)
    return result


def effective_enriched_residual(
    matrix_a: np.ndarray,
    rhs_a: np.ndarray,
    state_a: np.ndarray,
    state_b: np.ndarray,
) -> np.ndarray:
    """Return the residual difference ``rA(xB)-rA(xA)``."""

    matrix = _complex_matrix(matrix_a, name="enriched matrix")
    enriched_rhs = _complex_vector(rhs_a, name="enriched RHS")
    enriched_state = _complex_vector(state_a, name="enriched state")
    coarse_state = _complex_vector(state_b, name="coarse state")
    size = len(enriched_rhs)
    if matrix.shape != (size, size) or enriched_state.shape != (
        size,
    ) or coarse_state.shape != (size,):
        raise ValueError("effective residual arrays have incompatible shapes")
    result = np.ascontiguousarray(
        (enriched_rhs - matrix @ coarse_state)
        - (enriched_rhs - matrix @ enriched_state)
    )
    result.setflags(write=False)
    return result


def hermitian_adjoint(
    matrix_a: np.ndarray,
    gradient: np.ndarray,
) -> np.ndarray:
    """Solve the complex discrete adjoint ``A^H z=g``."""

    matrix = _complex_matrix(matrix_a, name="enriched matrix")
    goal_gradient = _complex_vector(gradient, name="goal gradient")
    if matrix.shape != (len(goal_gradient), len(goal_gradient)):
        raise ValueError("adjoint matrix and gradient sizes differ")
    adjoint = np.ascontiguousarray(
        np.linalg.solve(matrix.conj().T, goal_gradient)
    )
    adjoint.setflags(write=False)
    return adjoint


def complex_pairing(
    adjoint: np.ndarray,
    residual: np.ndarray,
) -> complex:
    """Return the Hermitian pairing ``z^H r``."""

    left = _complex_vector(adjoint, name="adjoint")
    right = _complex_vector(residual, name="residual")
    if left.shape != right.shape:
        raise ValueError("adjoint and residual sizes differ")
    return complex(np.vdot(left, right))


def signed_pairing(
    adjoint: np.ndarray,
    residual: np.ndarray,
) -> float:
    """Return the signed real DWR contribution ``Re(z^H r)``."""

    return float(np.real(complex_pairing(adjoint, residual)))


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def signed_dwr_partition_audit(
    *,
    actual_goal_delta: float,
    adjoint: np.ndarray,
    effective_residual: np.ndarray,
    component_residuals: Mapping[str, np.ndarray],
    vector_relative_tolerance: float = 2.0e-12,
    vector_absolute_tolerance: float = 2.0e-13,
    goal_relative_tolerance: float = 2.0e-12,
    goal_absolute_tolerance: float = 2.0e-13,
) -> dict[str, Any]:
    """Audit signed component closure without hiding unexplained residual."""

    z = _complex_vector(adjoint, name="adjoint")
    effective = _complex_vector(
        effective_residual,
        name="effective enriched residual",
    )
    if z.shape != effective.shape:
        raise ValueError("adjoint and effective residual sizes differ")
    if not component_residuals:
        raise ValueError("signed DWR audit requires named components")
    components: dict[str, np.ndarray] = {}
    for name, values in component_residuals.items():
        if not isinstance(name, str) or not name:
            raise ValueError("DWR component names must be non-empty strings")
        vector = _complex_vector(values, name=f"DWR component {name}")
        if vector.shape != effective.shape:
            raise ValueError(
                f"DWR component {name!r} has the wrong shape"
            )
        components[name] = vector

    component_sum = np.sum(
        np.stack(tuple(components.values())),
        axis=0,
    )
    unexplained = effective - component_sum
    effective_norm = float(np.linalg.norm(effective))
    component_norm_sum = float(
        sum(np.linalg.norm(vector) for vector in components.values())
    )
    vector_scale = max(effective_norm, component_norm_sum, 1.0)
    unexplained_norm = float(np.linalg.norm(unexplained))
    vector_limit = float(vector_absolute_tolerance) + float(
        vector_relative_tolerance
    ) * vector_scale
    vector_pass = unexplained_norm <= vector_limit

    global_complex = complex_pairing(z, effective)
    estimate = float(np.real(global_complex))
    actual = float(actual_goal_delta)
    if not np.isfinite(actual):
        raise ValueError("actual goal delta is non-finite")
    goal_error = float(estimate - actual)
    goal_scale = max(abs(estimate), abs(actual), 1.0)
    goal_limit = float(goal_absolute_tolerance) + float(
        goal_relative_tolerance
    ) * goal_scale
    goal_pass = abs(goal_error) <= goal_limit

    reports: dict[str, Any] = {}
    signed_sum = 0.0
    absolute_sum = 0.0
    complex_sum = 0.0 + 0.0j
    for name, vector in components.items():
        pairing = complex_pairing(z, vector)
        signed = float(np.real(pairing))
        reports[name] = {
            "complex_pairing": _complex_pair(pairing),
            "signed_real_contribution": signed,
            "absolute_marking_weight": abs(signed),
            "residual_norm": float(np.linalg.norm(vector)),
        }
        signed_sum += signed
        absolute_sum += abs(signed)
        complex_sum += pairing
    pairing_closure_error = complex(global_complex - complex_sum)
    passed = bool(vector_pass and goal_pass)
    return {
        "schema_version": "task035d.same-trace-signed-dwr.v1",
        "status": (
            "same_trace_signed_dwr_pass"
            if passed
            else "same_trace_signed_dwr_fail"
        ),
        "pass": passed,
        "actual_goal_delta": actual,
        "signed_dwr_estimate": estimate,
        "signed_goal_closure_error": goal_error,
        "goal_closure_limit": goal_limit,
        "goal_closure_pass": goal_pass,
        "global_complex_pairing": _complex_pair(global_complex),
        "component_complex_pairing_sum": _complex_pair(complex_sum),
        "component_pairing_closure_error": _complex_pair(
            pairing_closure_error
        ),
        "component_signed_sum": signed_sum,
        "component_absolute_marking_sum": absolute_sum,
        "absolute_sum_used_for_closure": False,
        "effective_residual_norm": effective_norm,
        "component_residual_norm_sum": component_norm_sum,
        "unexplained_residual_norm": unexplained_norm,
        "unexplained_residual_relative": (
            unexplained_norm / vector_scale
        ),
        "unexplained_residual_limit": vector_limit,
        "residual_partition_pass": vector_pass,
        "unexplained_residual_added_back_as_component": False,
        "components": reports,
        "complex_conjugation": (
            "Hermitian A^H, C^H, and np.vdot; never plain transpose"
        ),
        "effective_residual_definition": "rA(xB)-rA(xA)",
        "ordinary_default_changed": False,
    }


__all__ = [
    "CellSchurDeltaResidual",
    "affine_channel_value",
    "affine_goal_gradient",
    "cell_schur_delta_residual",
    "complex_pairing",
    "effective_enriched_residual",
    "hermitian_adjoint",
    "operator_delta_residual",
    "scaled_unit_adjoint_pairing",
    "signed_dwr_partition_audit",
    "signed_pairing",
    "unit_channel_goal_scalar",
]
