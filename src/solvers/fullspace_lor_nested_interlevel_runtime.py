"""Opt-in Route-B p6 -> p2 -> p1 owner-packet bridge.

This module deliberately does not add a solver or a smoother.  It extends one
already-built S2 foundation with the fixed nested levels and exposes pair
selection explicitly so a Route-B probe cannot accidentally use level 1 as
its coarse level.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import numpy as np

from .fullspace_lor_memory_hierarchy import build_local_interlevel_edge_transfer
from .fullspace_lor_memory_hierarchy_runtime import (
    ROUTE_B_LEVELS,
    ROUTE_B_PAIRS,
    ROUTE_B_SCHEMA,
    _OwnerPacketTransfer,
    _build_level,
    _build_level6,
)


class RouteBNestedHierarchyExtension:
    """Fixed level-6/2/1 owner-packet extension, with caller-owned foundation."""

    def __init__(self, foundation: Any, level6: Any, level2: Any, level1: Any,
                 transfer_62: Any, transfer_21: Any) -> None:
        if level6.degree != 6 or level2.degree != 2 or level1.degree != 1:
            raise ValueError("Route-B levels must be exactly 6, 2, and 1")
        if level6.matrix is not foundation.low_matrix:
            raise ValueError("Route-B level6 must reuse foundation.low_matrix")
        self.foundation = foundation
        self.levels = {6: level6, 2: level2, 1: level1}
        self.transfers = {(6, 2): transfer_62, (2, 1): transfer_21}
        self._destroyed = False
        self.audit = MappingProxyType({
            "schema": ROUTE_B_SCHEMA,
            "levels": ROUTE_B_LEVELS,
            "pairs": ROUTE_B_PAIRS,
            "foundation_caller_owned": True,
            "level1_raw_matrix_built": True,
            "global_high_order_aij": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "p1_global_direct_factor": False,
            "p6_exact_factor": False,
            "hx_hierarchy_built": False,
            "pcgamg_hierarchy_built": False,
            "smoother_built": False,
            "ksp_created": False,
            "physical_solve": False,
            "recovery": False,
            "retains_per_apply_history": False,
        })

    def pair_levels(self, pair: tuple[int, int]) -> tuple[Any, Any]:
        pair = tuple(int(value) for value in pair)
        if pair not in ROUTE_B_PAIRS:
            raise ValueError("Route-B pair must be (6, 2) or (2, 1)")
        return self.levels[pair[0]], self.levels[pair[1]]

    def apply_primal(self, pair: tuple[int, int], source: Any) -> Any:
        if self._destroyed:
            raise RuntimeError("Route-B hierarchy has been destroyed")
        pair = tuple(int(value) for value in pair)
        self.pair_levels(pair)
        return self.transfers[pair].apply_primal(source)

    def apply_adjoint(self, pair: tuple[int, int], source: Any) -> Any:
        if self._destroyed:
            raise RuntimeError("Route-B hierarchy has been destroyed")
        pair = tuple(int(value) for value in pair)
        self.pair_levels(pair)
        return self.transfers[pair].apply_adjoint(source)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        levels = self.levels
        self.transfers = {}
        levels[2].destroy()
        levels[1].destroy()
        levels[6].destroy()
        self.levels = {}
        self.foundation = None


def build_route_b_nested_hierarchy_extension(
    foundation: Any,
) -> RouteBNestedHierarchyExtension:
    """Build the fixed Route-B extension from one existing S2 foundation."""

    if foundation is None or not hasattr(foundation, "low_matrix"):
        raise ValueError("Route-B requires an already-built S2 foundation")
    cfg = foundation.cfg
    if (int(cfg.nedelec_degree), float(cfg.mesh_target_size), float(cfg.lambda0)) != (
        6, 10.0, 13.5
    ):
        raise ValueError("Route-B identity is fixed at p6/h10/13.5 nm")
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    plan = _stage4_axis_plan(cfg, foundation.high_mesh.comm.size)
    axes = tuple(
        np.asarray(axis, dtype=np.float64)
        for axis in (plan.x_values, plan.y_values, plan.z_values)
    )
    level6 = _build_level6(
        foundation, allowed_levels=ROUTE_B_LEVELS,
        route_schema=ROUTE_B_SCHEMA, validate_canonical_owner_identity=True,
    )
    level2 = level1 = None
    try:
        level2 = _build_level(
            foundation, 2, axes, allowed_levels=ROUTE_B_LEVELS,
            route_schema=ROUTE_B_SCHEMA, level_suffix="route_b",
            validate_canonical_owner_identity=True,
        )
        level1 = _build_level(
            foundation, 1, axes, allowed_levels=ROUTE_B_LEVELS,
            route_schema=ROUTE_B_SCHEMA, level_suffix="route_b",
            validate_canonical_owner_identity=True,
        )
        transfer_62 = _OwnerPacketTransfer(
            level6, level2, build_local_interlevel_edge_transfer(6, 2),
            allowed_pairs=ROUTE_B_PAIRS, route_schema=ROUTE_B_SCHEMA,
        )
        transfer_21 = _OwnerPacketTransfer(
            level2, level1, build_local_interlevel_edge_transfer(2, 1),
            allowed_pairs=ROUTE_B_PAIRS, route_schema=ROUTE_B_SCHEMA,
        )
        return RouteBNestedHierarchyExtension(
            foundation, level6, level2, level1, transfer_62, transfer_21,
        )
    except Exception:
        if level1 is not None:
            level1.destroy()
        if level2 is not None:
            level2.destroy()
        level6.destroy()
        raise


__all__ = [
    "RouteBNestedHierarchyExtension",
    "build_route_b_nested_hierarchy_extension",
]
