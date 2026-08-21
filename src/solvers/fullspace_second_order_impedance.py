"""Fixed second-order Taylor/local weak action for the two-slab shell.

The constants are fixed by the prescribed s/p Taylor coefficients.  This is
not an exact local DtN solve, a full-frequency claim, a modal truncation, or a
retained Schur/factor operator; applicability is determined by the contraction
Gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

import hashlib
import json
import numpy as np
import ufl
from dolfinx import fem
from petsc4py import PETSc

from .fullspace_mpc_action import build_fullspace_mpc_form_action


FIXED_SECOND_ORDER_LOCAL_IMPEDANCE = "fixed_second_order_local_impedance_v1"
FIXED_SECOND_ORDER_FORM = "per_facet_broken_tangential_derivative_action"
_MATERIAL_EQUALITY_TOLERANCE = 1.0e-13


@dataclass(frozen=True)
class SecondOrderImpedanceCoefficients:
    """The frozen coefficients for one neighboring refractive index."""

    refractive_index: complex
    y0: complex
    a_s: complex
    a_p: complex
    d: complex


def fixed_second_order_coefficients(
    k0: float,
    refractive_index: complex,
) -> SecondOrderImpedanceCoefficients:
    """Return the prescribed fixed second-order local-impedance constants."""

    n = complex(refractive_index)
    k0_value = float(k0)
    a_s = complex(1j * k0_value / (2.0 * n))
    a_p = complex(-1j * k0_value / (2.0 * n))
    return SecondOrderImpedanceCoefficients(
        refractive_index=n,
        y0=complex(-1j * k0_value * n),
        a_s=a_s,
        a_p=a_p,
        d=complex(a_p - a_s),
    )


def _complex_key(value: complex) -> tuple[float, float]:
    value = complex(value)
    return float(value.real), float(value.imag)


def _material_key(material: Any) -> tuple[float, ...]:
    return (
        *_complex_key(material.epsilon_r),
        *_complex_key(material.mu_r),
    )


def _pair_key(lower: Any, upper: Any) -> tuple[float, ...]:
    return (*_material_key(lower), *_material_key(upper))


def _pair_classification(lower: Any, upper: Any) -> str:
    return (
        "homogeneous"
        if np.isclose(
            lower.epsilon_r,
            upper.epsilon_r,
            rtol=0.0,
            atol=_MATERIAL_EQUALITY_TOLERANCE,
        )
        and np.isclose(
            lower.mu_r,
            upper.mu_r,
            rtol=0.0,
            atol=_MATERIAL_EQUALITY_TOLERANCE,
        )
        else "nonhomogeneous"
    )


def _json_key(key: tuple[float, ...]) -> list[float]:
    return [float(value) for value in key]


def _tangential_form_terms(
    u: Any,
    v: Any,
) -> tuple[Any, Any, Any]:
    """Return mass, broken tangential-gradient, and tangential-divergence terms."""

    u_plus = u("+")
    v_plus = v("+")
    u_t = ufl.as_vector((u_plus[0], u_plus[1]))
    v_t = ufl.as_vector((v_plus[0], v_plus[1]))
    grad_u = ufl.grad(u_plus)
    grad_v = ufl.grad(v_plus)
    grad_t_u = ufl.as_tensor(
        ((grad_u[0, 0], grad_u[0, 1]), (grad_u[1, 0], grad_u[1, 1]))
    )
    grad_t_v = ufl.as_tensor(
        ((grad_v[0, 0], grad_v[0, 1]), (grad_v[1, 0], grad_v[1, 1]))
    )
    div_t_u = grad_u[0, 0] + grad_u[1, 1]
    div_t_v = grad_v[0, 0] + grad_v[1, 1]
    return (
        ufl.inner(u_t, v_t),
        ufl.inner(grad_t_u, grad_t_v),
        div_t_u * ufl.conj(div_t_v),
    )


def _build_second_order_form(
    function_space: Any,
    topology: Any,
    direction: str,
    coefficients: Mapping[tuple[float, ...], SecondOrderImpedanceCoefficients],
    class_by_tag: Mapping[int, tuple[float, ...]],
) -> tuple[Any, tuple[Any, ...]]:
    if direction not in {"forward", "backward"}:
        raise ValueError("direction must be 'forward' or 'backward'")

    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    mass, grad_mass, div_mass = _tangential_form_terms(u, v)
    dS = ufl.Measure(
        "dS",
        domain=topology.mesh,
        subdomain_data=topology.interface_facet_tags,
    )
    constants: dict[tuple[float, ...], tuple[Any, Any, Any]] = {}
    form = 0
    for tag, _lower, _upper in topology.global_material_pairs:
        class_key = class_by_tag[int(tag)]
        if class_key not in constants:
            values = coefficients[class_key]
            constants[class_key] = (
                fem.Constant(topology.mesh, PETSc.ScalarType(values.y0)),
                fem.Constant(topology.mesh, PETSc.ScalarType(values.a_s)),
                fem.Constant(topology.mesh, PETSc.ScalarType(values.d)),
            )
        y0, a_s, d = constants[class_key]
        form += (
            y0 * mass
            + (a_s / float(topology.cfg.k0**2)) * grad_mass
            + (d / float(topology.cfg.k0**2)) * div_mass
        ) * dS(int(tag))
    return form, tuple(value for group in constants.values() for value in group)


class FixedSecondOrderLocalImpedance:
    """Owner-local fixed second-order impedance on real interface facets."""

    def __init__(
        self,
        function_space: Any,
        topology: Any,
        *,
        mpc: Any | None = None,
    ) -> None:
        self.topology = topology
        self.mpc = mpc
        self.function_space = mpc.function_space if mpc is not None else function_space
        self._destroyed = False
        self._class_by_tag: dict[int, tuple[float, ...]] = {}
        self._class_pairs: dict[tuple[float, ...], tuple[Any, Any, str]] = {}
        for tag, lower, upper in topology.global_material_pairs:
            key = _pair_key(lower, upper)
            self._class_pairs.setdefault(
                key,
                (lower, upper, _pair_classification(lower, upper)),
            )
            self._class_by_tag[int(tag)] = key

        self._coefficients_by_direction: dict[
            str, dict[tuple[float, ...], SecondOrderImpedanceCoefficients]
        ] = {}
        for direction in ("forward", "backward"):
            self._coefficients_by_direction[direction] = {
                key: fixed_second_order_coefficients(
                    topology.cfg.k0,
                    (pair[1] if direction == "forward" else pair[0]).refractive_index,
                )
                for key, pair in self._class_pairs.items()
            }

        self._actions: dict[str, Any] = {}
        self._form_constants: dict[str, tuple[Any, ...]] = {}
        for direction in ("forward", "backward"):
            form, constants = _build_second_order_form(
                self.function_space,
                topology,
                direction,
                self._coefficients_by_direction[direction],
                self._class_by_tag,
            )
            self._form_constants[direction] = constants
            self._actions[direction] = build_fullspace_mpc_form_action(
                form,
                self.function_space,
                mpc=mpc,
                slave_row_identity=False,
            )

        manifest = []
        for direction in ("forward", "backward"):
            for key, (lower, upper, classification) in sorted(
                self._class_pairs.items()
            ):
                coefficients = self._coefficients_by_direction[direction][key]
                manifest.append(
                    {
                        "class_key": _json_key(key),
                        "direction": direction,
                        "classification": classification,
                        "lower_material_tag": int(lower.tag),
                        "upper_material_tag": int(upper.tag),
                        "neighbor_side": (
                            "upper" if direction == "forward" else "lower"
                        ),
                        "neighbor_n": list(
                            _complex_key(coefficients.refractive_index)
                        ),
                        "y0": list(_complex_key(coefficients.y0)),
                        "a_s": list(_complex_key(coefficients.a_s)),
                        "a_p": list(_complex_key(coefficients.a_p)),
                        "d": list(_complex_key(coefficients.d)),
                    }
                )
        manifest_bytes = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        constant_scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
        constant_scalar_count = int(
            sum(len(constants) for constants in self._form_constants.values())
        )
        retained_numeric_payload_bytes = int(
            constant_scalar_count * constant_scalar_bytes
        )
        self._audit = {
            "schema": "task038.fullspace-fixed-second-order-impedance.v1",
            "candidate": "C",
            "transmission": FIXED_SECOND_ORDER_LOCAL_IMPEDANCE,
            "operator_name": "fixed_second_order_local_impedance",
            "exact_local_dtn": False,
            "formula": (
                "T2=y0*I+a_s*|kappa|^2/k0^2*I"
                "+d*kappa*kappa^T/k0^2"
            ),
            "weak_form": FIXED_SECOND_ORDER_FORM,
            "weak_form_support": "interface_facet_dS_material_pair_tags_only",
            "derivative_semantics": "per_facet_broken_tangential_derivative",
            "y0": "-i*k0*n_neighbor",
            "a_s": "+i*k0/(2*n_neighbor)",
            "a_p": "-i*k0/(2*n_neighbor)",
            "d": "a_p-a_s=-i*k0/n_neighbor",
            "forward_neighbor": "upper",
            "backward_neighbor": "lower",
            "class_count": len(self._class_pairs),
            "class_manifest": tuple(manifest),
            "class_manifest_serialized_bytes": len(manifest_bytes),
            "class_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "retained_numeric_payload": {
                "fem_constant_complex_scalar_count": constant_scalar_count,
                "fem_constant_complex_scalar_bytes": constant_scalar_bytes,
                "fem_constant_values_bytes": retained_numeric_payload_bytes,
                "a_p_storage": "derived_from_a_s_plus_d_not_retained_as_constant",
                "scaling": "O(material_pair_class_count)",
            },
            "retained_numeric_payload_bytes": retained_numeric_payload_bytes,
            "retained_numeric_payload_scaling": "O(material_pair_class_count)",
            "parameters_frozen_before_rho": True,
            "spectral_threshold": "not_used",
            "local_patch_range": "not_used",
            "local_krylov_steps": 0,
            "factor_count": 0,
            "per_cell_retained_tensor_count": 0,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "dense_interface_matrix_materialized": False,
            "growing_slab_factor_materialized": False,
            "numeric_allgather": False,
            "phase_application": (
                "finalized_floquet_mpc_once" if mpc is not None else "none"
            ),
            "slave_row_identity": False,
            "action_audits": {
                direction: dict(self._actions[direction].audit)
                for direction in ("forward", "backward")
            },
        }

    @property
    def audit(self) -> Mapping[str, object]:
        return MappingProxyType(dict(self._audit))

    def apply(self, source: Any, direction: str) -> Any:
        """Apply one directional class-reused facet action with owned output."""

        if self._destroyed:
            raise RuntimeError("fixed second-order impedance has been destroyed")
        if direction not in self._actions:
            raise ValueError("direction must be 'forward' or 'backward'")
        return self._actions[direction].apply(source).copy()

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        for action in self._actions.values():
            action.destroy()
        self._actions.clear()
        self._form_constants.clear()


__all__ = (
    "FIXED_SECOND_ORDER_FORM",
    "FIXED_SECOND_ORDER_LOCAL_IMPEDANCE",
    "FixedSecondOrderLocalImpedance",
    "SecondOrderImpedanceCoefficients",
    "fixed_second_order_coefficients",
)
