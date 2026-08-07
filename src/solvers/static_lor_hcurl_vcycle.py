"""One fixed factor-free LOR H(curl) action with paired H1 V-cycles.

The object here is a finest-edge action only.  It combines one edge Jacobi
step, the scalar and vector H1 V-cycles, and one edge Jacobi step.  It does
not change the exact outer operator and does not retain the D2a HX object.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from types import MappingProxyType
from typing import Mapping

import numpy as np
import scipy.sparse as sp

from .static_lor_h1_vcycle import LORH1VCycle
from .static_lor_hcurl_auxiliary import LORHcurlAuxiliarySpace
from .static_lor_hcurl_hx import LORHcurlHX


_EDGE_JACOBI_OMEGA = 0.5


def _auxiliary_payload(audit: Mapping[str, object]) -> tuple[int, dict[str, int]]:
    parent_bytes = int(
        sum(
            int(value)
            for value in audit["parent_vertex_expansion_csr_payload_bytes"]
        )
    )
    components = {
        "gradient_csr_payload_bytes": int(audit["gradient_csr_payload_bytes"]),
        "gradient_adjoint_csr_payload_bytes": int(
            audit["gradient_adjoint_csr_payload_bytes"]
        ),
        "vector_interpolation_csr_payload_bytes": int(
            audit["vector_interpolation_csr_payload_bytes"]
        ),
        "vector_interpolation_adjoint_csr_payload_bytes": int(
            audit["vector_interpolation_adjoint_csr_payload_bytes"]
        ),
        "parent_vertex_expansion_csr_payload_bytes": parent_bytes,
    }
    return sum(components.values()), components


def _h1_factor_payload(audit: Mapping[str, object]) -> int:
    scalar = audit["scalar_factor_inventory"]
    vector = audit["vector_factor_inventory"]
    return int(
        scalar["factor_payload_lower_bound_bytes"]
        + vector["factor_payload_lower_bound_bytes"]
    )


@dataclass(frozen=True)
class LORHcurlVCycle:
    """One or two fixed LOR-HX cycles with coarsest-only H1 factors."""

    _a: sp.csr_matrix
    _auxiliary: LORHcurlAuxiliarySpace
    _edge_inverse_diagonal: np.ndarray
    h1_vcycle: LORH1VCycle
    audit: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))

    @property
    def matrix(self) -> sp.csr_matrix:
        return self._a

    @property
    def auxiliary(self) -> LORHcurlAuxiliarySpace:
        return self._auxiliary

    @property
    def edge_inverse_diagonal(self) -> np.ndarray:
        return self._edge_inverse_diagonal

    def _check_rhs(self, rhs: np.ndarray) -> np.ndarray:
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self._a.shape[0],):
            raise ValueError("LOR H(curl) V-cycle RHS has the wrong edge count")
        return values

    def _apply_one_values(self, values: np.ndarray) -> np.ndarray:
        solution = _EDGE_JACOBI_OMEGA * self._edge_inverse_diagonal * values
        residual = values - self._a @ solution

        scalar_rhs = self._auxiliary.apply_gradient_adjoint(residual)
        solution += self._auxiliary.apply_gradient(
            self.h1_vcycle.apply_scalar(scalar_rhs)
        )

        residual = values - self._a @ solution
        vector_rhs = self._auxiliary.apply_vector_h1_adjoint(residual)
        solution += self._auxiliary.apply_vector_h1(
            self.h1_vcycle.apply_vector(vector_rhs)
        )

        residual = values - self._a @ solution
        solution += _EDGE_JACOBI_OMEGA * self._edge_inverse_diagonal * residual
        return solution

    def apply_one(self, rhs: np.ndarray) -> np.ndarray:
        """Apply exactly one fixed edge/H1/H1/edge cycle from zero."""

        return self._apply_one_values(self._check_rhs(rhs))

    def apply_two(self, rhs: np.ndarray) -> np.ndarray:
        """Apply exactly two stationary cycles, adding the second correction."""

        values = self._check_rhs(rhs)
        first = self._apply_one_values(values)
        second_rhs = values - self._a @ first
        return first + self._apply_one_values(second_rhs)


def build_lor_hcurl_vcycle(
    hx: LORHcurlHX,
    h1_vcycle: LORH1VCycle,
) -> LORHcurlVCycle:
    """Connect D2a finest maps to the paired coarsest-only H1 cycles."""

    scalar_operator = hx.scalar_operator
    vector_operator = hx.vector_operator
    hierarchy = h1_vcycle.hierarchy
    if hierarchy.scalar_operators[0] is not scalar_operator:
        raise ValueError("H1 scalar hierarchy does not reuse the HX operator")
    if hierarchy.vector_operators[0] is not vector_operator:
        raise ValueError("H1 vector hierarchy does not reuse the HX operator")

    started = perf_counter()
    auxiliary_payload_bytes, auxiliary_breakdown = _auxiliary_payload(
        hx.auxiliary.audit
    )
    hierarchy_payload_bytes = int(
        h1_vcycle.audit["hierarchy_payload_reference_bytes"]
    )
    h1_inverse_diagonal_bytes = int(h1_vcycle.audit["inverse_diagonal_bytes"])
    h1_factor_payload_bytes = _h1_factor_payload(h1_vcycle.audit)
    proxy_payload_bytes = int(
        hx.matrix.data.nbytes + hx.matrix.indices.nbytes + hx.matrix.indptr.nbytes
    )
    edge_inverse_bytes = int(hx.edge_inverse_diagonal.nbytes)
    retained_components = {
        "proxy_csr_payload_bytes": proxy_payload_bytes,
        "auxiliary_numeric_map_payload_bytes": auxiliary_payload_bytes,
        "h1_hierarchy_csr_payload_bytes": hierarchy_payload_bytes,
        "h1_inverse_diagonal_bytes": h1_inverse_diagonal_bytes,
        "h1_factor_payload_lower_bound_bytes": h1_factor_payload_bytes,
        "edge_inverse_diagonal_bytes": edge_inverse_bytes,
    }
    retained_payload = sum(retained_components.values())
    audit = {
        "definition": "edge pre -> scalar H1 V-cycle -> vector H1 V-cycle -> edge post",
        "order": "edge_pre_scalar_H1_V_cycle_vector_H1_V_cycle_edge_post",
        "one_cycle_semantics": "one fixed cycle from zero",
        "two_cycle_semantics": "first cycle plus one stationary residual correction",
        "edge_rows": int(hx.matrix.shape[0]),
        "scalar_rows": int(scalar_operator.shape[0]),
        "vector_rows": int(vector_operator.shape[0]),
        "h1_level_count": int(h1_vcycle.audit["level_count"]),
        "edge_jacobi_omega": _EDGE_JACOBI_OMEGA,
        "edge_inverse_diagonal_bytes": edge_inverse_bytes,
        "proxy_csr_payload_bytes": proxy_payload_bytes,
        "auxiliary_numeric_map_payload_bytes": auxiliary_payload_bytes,
        "auxiliary_numeric_map_payload_breakdown": auxiliary_breakdown,
        "h1_hierarchy_payload_reference_bytes": hierarchy_payload_bytes,
        "h1_inverse_diagonal_bytes": h1_inverse_diagonal_bytes,
        "h1_factor_payload_lower_bound_bytes": h1_factor_payload_bytes,
        "scalar_factor_inventory": dict(
            h1_vcycle.audit["scalar_factor_inventory"]
        ),
        "vector_factor_inventory": dict(
            h1_vcycle.audit["vector_factor_inventory"]
        ),
        "retained_numeric_payload_components": retained_components,
        "retained_numeric_payload_lower_bound_bytes": retained_payload,
        "factor_count": int(h1_vcycle.audit["factor_count"]),
        "coarsest_factor_count": int(h1_vcycle.audit["coarsest_factor_count"]),
        "fine_intermediate_factor_count": int(
            h1_vcycle.audit["fine_intermediate_factor_count"]
        ),
        "fine_p6_trace_factor_count": 0,
        "fine_p6_full_factor_count": 0,
        "large_lor_factor_count": 0,
        "coarsest_only": True,
        "restriction_retained": False,
        "explicit_action_retained": False,
        "large_factor": False,
        "global_dense": False,
        "literal_p6_galerkin": False,
        "retains_fine_hx_object": False,
        "unused_aux_jacobi_inverse_retained": False,
        "exact_outer_changed": False,
        "contraction_not_evaluated": True,
        "build_seconds": float(perf_counter() - started),
    }
    return LORHcurlVCycle(
        hx.matrix,
        hx.auxiliary,
        hx.edge_inverse_diagonal,
        h1_vcycle,
        audit,
    )


__all__ = ("LORHcurlVCycle", "build_lor_hcurl_vcycle")
