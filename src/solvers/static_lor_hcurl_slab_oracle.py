"""Physical-material one-slab trace oracle on the direct child-cell LOR proxy.

This research-only path uses the configured affine volume coefficients and the
fixed D1b diagonal shift.  It excludes the DtN surface block and does not form
or retain a literal p6 local Galerkin matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from types import MappingProxyType
from typing import Iterable, Mapping

import numpy as np

from src.common.config_3d import SimulationConfig3D

from .hcurl_affine_isotropic_tensor import AffineIsotropicMaxwellTensorSpec
from .static_lor_h1_hierarchy import build_lor_h1_hierarchy
from .static_lor_h1_vcycle import build_lor_h1_vcycle
from .static_lor_hcurl_hx import build_lor_hcurl_hx
from .static_lor_hcurl_transfer import (
    AffineLORParentTopology,
    OwnerLocalLORTransfer,
)
from .static_lor_hcurl_proxy import build_shifted_lor_proxy
from .static_lor_hcurl_vcycle import (
    LORHcurlVCycle,
    build_lor_hcurl_vcycle,
)
from .static_lor_hcurl_auxiliary import build_lor_hcurl_auxiliary_space


def _complex_pair(value: complex) -> list[float]:
    scalar = complex(value)
    return [float(scalar.real), float(scalar.imag)]


def _physical_spec(
    topologies: tuple[AffineLORParentTopology, ...],
    cfg: SimulationConfig3D,
) -> tuple[AffineIsotropicMaxwellTensorSpec, tuple[int, ...]]:
    present_tags = tuple(sorted({int(topology.material_tag) for topology in topologies}))
    mass_by_tag: dict[int, complex] = {}
    for tag in present_tags:
        if tag == int(cfg.tags.air):
            epsilon = cfg.eps_air
        elif tag == int(cfg.tags.substrate):
            epsilon = cfg.eps_substrate
        elif tag == int(cfg.tags.grating):
            epsilon = cfg.eps_grating
        else:
            raise NotImplementedError(
                "physical LOR oracle does not support PML or unknown material tags"
            )
        mass_by_tag[tag] = -cfg.k0**2 * complex(epsilon)
    return (
        AffineIsotropicMaxwellTensorSpec(
            curl_coefficient=1.0 / complex(cfg.mu_r),
            mass_coefficient_by_tag=mass_by_tag,
        ),
        present_tags,
    )


@dataclass(frozen=True)
class OwnerLocalLORHcurlSlabOracle:
    """Stateless trace-tail action backed by one factor-free LOR-HX cycle."""

    transfer: OwnerLocalLORTransfer
    hcurl_vcycle: LORHcurlVCycle
    audit: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))

    def _apply_trace(self, rhs_t: np.ndarray, two: bool) -> np.ndarray:
        values = np.asarray(rhs_t, dtype=np.complex128)
        trace_rows = int(self.transfer.audit["trace_rows"])
        if values.shape != (trace_rows,):
            raise ValueError("trace RHS has the wrong owner-row count")
        full_rhs = np.zeros(
            int(self.transfer.audit["full_rows"]),
            dtype=np.complex128,
        )
        trace_offset = int(self.transfer.audit["trace_offset"])
        full_rhs[trace_offset:] = values
        active_rhs = self.transfer.apply_adjoint(full_rhs)
        active_correction = (
            self.hcurl_vcycle.apply_two(active_rhs)
            if two
            else self.hcurl_vcycle.apply_one(active_rhs)
        )
        full_correction = self.transfer.apply(active_correction)
        return np.array(
            full_correction[trace_offset:],
            dtype=np.complex128,
            copy=True,
        )

    def apply_one_trace(self, rhs_t: np.ndarray) -> np.ndarray:
        """Apply one fixed trace-lifted LOR-HX cycle."""

        return self._apply_trace(rhs_t, False)

    def apply_two_trace(self, rhs_t: np.ndarray) -> np.ndarray:
        """Apply two stationary LOR-HX cycles to one lifted trace RHS."""

        return self._apply_trace(rhs_t, True)


def build_physical_lor_hcurl_slab_oracle(
    transfer: OwnerLocalLORTransfer,
    parent_topologies: Iterable[AffineLORParentTopology],
    cfg: SimulationConfig3D,
) -> OwnerLocalLORHcurlSlabOracle:
    """Build the physical-material one-slab volume-proxy trace oracle."""

    started = perf_counter()
    if cfg.stage4_boundary_model != "dtn_port":
        raise ValueError("physical LOR oracle requires stage4_boundary_model=dtn_port")
    if float(cfg.divergence_penalty) != 0.0:
        raise ValueError("physical LOR oracle requires divergence_penalty=0")

    topologies = tuple(
        sorted(parent_topologies, key=lambda topology: topology.canonical_cell_id)
    )
    if not topologies:
        raise ValueError("at least one parent topology is required")
    parent_ids = tuple(int(topology.canonical_cell_id) for topology in topologies)
    if parent_ids != tuple(int(value) for value in transfer.audit["parent_ids"]):
        raise ValueError("parent IDs do not match the owner-local transfer")
    if parent_ids != tuple(int(value) for value in transfer.edge_space.parent_ids):
        raise ValueError("parent IDs do not match the LOR edge space")

    spec, present_tags = _physical_spec(topologies, cfg)
    proxy = build_shifted_lor_proxy(topologies, transfer.edge_space, spec)
    auxiliary = build_lor_hcurl_auxiliary_space(topologies, transfer.edge_space)
    hx = build_lor_hcurl_hx(proxy, auxiliary)
    hierarchy = build_lor_h1_hierarchy(hx.scalar_operator, hx.vector_operator)
    h1_vcycle = build_lor_h1_vcycle(hierarchy)
    hcurl_vcycle = build_lor_hcurl_vcycle(hx, h1_vcycle)

    transfer_payload = int(
        transfer.audit["retained_numeric_payload_lower_bound_bytes"]
    )
    hcurl_payload = int(
        hcurl_vcycle.audit["retained_numeric_payload_lower_bound_bytes"]
    )
    mass_coefficients = {
        str(tag): _complex_pair(value)
        for tag, value in spec.mass_coefficient_by_tag.items()
    }
    audit = {
        "definition": "physical affine volume proxy plus fixed D1b LOR shift",
        "present_material_tags": list(present_tags),
        "curl_coefficient": _complex_pair(spec.curl_coefficient),
        "mass_coefficient_by_tag": mass_coefficients,
        "volume_proxy_only": True,
        "dtn_surface_in_proxy": False,
        "literal_p6_shift_galerkin": False,
        "shift_rule": (
            "diag <- diag - 1j*0.1*max(abs(diag), 1e-12*max(abs(diag)))"
        ),
        "shift_fraction": 0.1,
        "shift_floor_relative": 1.0e-12,
        "full_rows": int(transfer.audit["full_rows"]),
        "interior_rows": int(transfer.audit["interior_rows"]),
        "trace_rows": int(transfer.audit["trace_rows"]),
        "active_lor_rows": len(transfer.edge_space.active_edge_keys),
        "zero_interior_trace_lift": True,
        "transfer_retained_numeric_payload_lower_bound_bytes": transfer_payload,
        "d2c_retained_numeric_payload_lower_bound_bytes": hcurl_payload,
        "retained_numeric_payload_lower_bound_bytes": transfer_payload + hcurl_payload,
        "factor_count": int(hcurl_vcycle.audit["factor_count"]),
        "coarsest_factor_count": int(
            hcurl_vcycle.audit["coarsest_factor_count"]
        ),
        "fine_p6_trace_factor_count": 0,
        "fine_p6_full_factor_count": 0,
        "large_lor_factor_count": 0,
        "fine_intermediate_factor_count": 0,
        "coarsest_only": True,
        "parent_topologies_retained": False,
        "persistent_full_rhs": False,
        "persistent_lor_rhs": False,
        "global_dense": False,
        "exact_outer_changed": False,
        "contraction_not_evaluated": True,
        "build_seconds": float(perf_counter() - started),
    }
    return OwnerLocalLORHcurlSlabOracle(transfer, hcurl_vcycle, audit)


__all__ = (
    "OwnerLocalLORHcurlSlabOracle",
    "build_physical_lor_hcurl_slab_oracle",
)
