"""Fixed owner-packet runtime for the custom h6 -> h3star -> h1star grid.

The middle level is a topology-only nested subgrid: it is not a standard
polynomial p3 space.  This module reuses the established S5 level and owner
route machinery; it adds no smoother, KSP, factor, or physical action.
"""

from __future__ import annotations

import copy
from types import MappingProxyType, SimpleNamespace
from typing import Any

import numpy as np

from .fullspace_lor_memory_hierarchy_runtime import (
    S5_BATCH_CELL_CAP,
    _OwnerPacketTransfer,
    _S5Level,
    _build_level6,
)
from .fullspace_lor_nested_hmg import (
    C2_PAIRS,
    C2_LEVELS,
    H1STAR_GLL_INDICES,
    H3STAR_GLL_INDICES,
    H6_GLL_INDICES,
    build_nested_lor_edge_hmg,
)
from .fullspace_lor_transfer import _gll_nodes


NESTED_HMG_RUNTIME_SCHEMA = "task038.nested-lor-edge-hmg.runtime.v1"
NESTED_HMG_LEVELS = C2_LEVELS
NESTED_HMG_PAIRS = C2_PAIRS
NESTED_HMG_BATCH_CELL_CAP = S5_BATCH_CELL_CAP


def _nested_indices(level_key: str) -> tuple[int, ...]:
    if level_key == "h6":
        return H6_GLL_INDICES
    if level_key == "h3star":
        return H3STAR_GLL_INDICES
    if level_key == "h1star":
        return H1STAR_GLL_INDICES
    raise ValueError(f"unsupported custom nested level: {level_key}")


def _nested_nodes(level_key: str) -> np.ndarray:
    nodes = np.asarray(_gll_nodes(6), dtype=np.float64)[list(_nested_indices(level_key))]
    nodes = nodes.copy()
    nodes.setflags(write=False)
    return nodes


def _nested_axis(parent_axis: np.ndarray, level_key: str) -> np.ndarray:
    """Use fixed p6 GLL indices on every parent interval."""

    parent_axis = np.asarray(parent_axis, dtype=np.float64)
    p6_nodes = np.asarray(_gll_nodes(6), dtype=np.float64)
    indices = _nested_indices(level_key)
    values: list[float] = [float(parent_axis[0])]
    for left, right in zip(parent_axis[:-1], parent_axis[1:], strict=True):
        for index in indices[1:]:
            local = float(p6_nodes[index])
            values.append(float(right) if index == 6 else float(left + (right - left) * local))
    result = np.asarray(values, dtype=np.float64)
    if result.size < 2 or not np.all(np.diff(result) > 0.0):
        raise ValueError("custom nested axis is not strictly ordered")
    return result


def _nested_axes(parent_axes: tuple[np.ndarray, np.ndarray, np.ndarray], level_key: str):
    if level_key not in NESTED_HMG_LEVELS:
        raise ValueError(f"unsupported custom nested level: {level_key}")
    return tuple(_nested_axis(axis, level_key) for axis in parent_axes)


class _TopologyOnlyNestedTransfer:
    """Minimal transfer-shaped metadata consumed by the canonical topology builder."""

    __slots__ = ("level_key", "subinterval_count", "edge_count", "nodes")

    def __init__(self, level_key: str) -> None:
        self.level_key = level_key
        self.nodes = _nested_nodes(level_key)
        self.subinterval_count = int(self.nodes.size - 1)
        self.edge_count = 3 * self.subinterval_count * (self.subinterval_count + 1) ** 2

    @property
    def degree(self) -> int:
        # The topology helper's legacy name means subinterval resolution here.
        return self.subinterval_count


def _stage4_parent_axes(foundation: Any):
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    plan = _stage4_axis_plan(foundation.cfg, foundation.high_mesh.comm.size)
    return tuple(
        np.asarray(axis, dtype=np.float64)
        for axis in (plan.x_values, plan.y_values, plan.z_values)
    )


def _build_level6_for_nested(foundation: Any):
    return _build_level6(
        foundation,
        allowed_levels=(6,),
        route_schema=NESTED_HMG_RUNTIME_SCHEMA,
    )


def _build_nested_level(
    foundation: Any,
    level_key: str,
    parent_axes: tuple[np.ndarray, np.ndarray, np.ndarray],
):
    """Build only the fixed custom h3star or h1star raw level."""

    if level_key not in ("h3star", "h1star"):
        raise ValueError(f"unsupported custom nested level: {level_key}")
    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        _mark_boundary_facets,
        _mark_cells,
        _structured_hexa_mesh,
    )
    from .fullspace_lor_memory_first_foundation import _canonical_raw_map
    from .fullspace_lor_native_hx_fixture import (
        _assemble_sparse,
        _edge_records,
        _p1_transfer_local_indices,
        _piecewise_positive_coefficients,
    )
    from .fullspace_lor_topology import build_canonical_lor_subedge_topology

    cfg = foundation.cfg
    comm = foundation.high_mesh.comm
    axes = _nested_axes(parent_axes, level_key)
    if level_key == "h3star":
        mesh = _structured_hexa_mesh(
            comm,
            *axes,
            preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
        )
        facets, _ = _mark_boundary_facets(mesh, cfg)
        cells = _mark_cells(mesh, cfg)
    else:
        mesh = foundation.high_mesh
        facets, cells = foundation.high_data.facet_tags, foundation.high_data.cell_tags
    data = SimpleNamespace(mesh=mesh, cell_tags=cells, facet_tags=facets)
    low_cfg = copy.deepcopy(cfg)
    low_cfg.nedelec_degree = low_cfg.visualization_degree = 1
    low_cfg.nedelec_trace_degree = low_cfg.nedelec_interior_degree = None
    low_cfg.case_name = f"{cfg.case_name}_nested_{level_key}_lor_p1"
    raw_space = fem.functionspace(
        mesh,
        element("N1curl", mesh.basix_cell(), 1, dtype=np.float64),
    )
    raw_floquet = build_double_floquet_mpc(raw_space, data, low_cfg)
    permutations = np.asarray(
        [
            _p1_transfer_local_indices(raw_space, cell)
            for cell in range(int(mesh.topology.index_map(3).size_local))
        ],
        dtype=np.int32,
    )
    mu, mass, _ = _piecewise_positive_coefficients(mesh, cells, low_cfg)
    trial = ufl.TrialFunction(raw_space)
    test = ufl.TestFunction(raw_space)
    matrix = _assemble_sparse(
        (mu * ufl.inner(ufl.curl(trial), ufl.curl(test)) + mass * ufl.inner(trial, test))
        * ufl.dx,
        mpc=raw_floquet.mpc,
    )
    raw_topology = build_canonical_lor_subedge_topology(
        raw_space,
        raw_floquet,
        _TopologyOnlyNestedTransfer("h1star"),
    )
    node_space = fem.functionspace(
        mesh,
        element("Lagrange", mesh.basix_cell(), 1, dtype=default_real_type),
    )
    records, _ = _edge_records(raw_space, node_space)
    raw_map = _canonical_raw_map(
        raw_space,
        node_space,
        records,
        axes,
        owner_ids=raw_topology.owned_edge_ids,
        local_permutations=permutations,
        validate_local_owner_layout=False,
    )
    del node_space, records, mu, mass
    if level_key == "h3star":
        parent_space = foundation.high_space
        parent_floquet = foundation.high_floquet
        parent_topology = build_canonical_lor_subedge_topology(
            parent_space,
            parent_floquet,
            _TopologyOnlyNestedTransfer("h3star"),
        )
        degree = 3
        role = "custom_nested_h3star_metadata"
    else:
        parent_space, parent_floquet, parent_topology = (
            raw_space,
            raw_floquet,
            raw_topology,
        )
        degree = 1
        role = "custom_nested_h1star_lor_level"
    return _S5Level(
        degree=degree,
        matrix=matrix,
        raw_space=raw_space,
        raw_floquet=raw_floquet,
        parent_topology=parent_topology,
        raw_topology=raw_topology,
        raw_map=raw_map,
        raw_permutations=permutations,
        incidence_unique=_owner_multiplicity(parent_topology),
        parent_space=parent_space,
        parent_floquet=parent_floquet,
        owned_objects=(matrix, raw_floquet),
        allowed_levels=(degree,),
        route_schema=NESTED_HMG_RUNTIME_SCHEMA,
        level_key=level_key,
        level_role=role,
        subinterval_count=len(_nested_indices(level_key)) - 1,
    )


def _owner_multiplicity(topology: Any) -> np.ndarray:
    from .fullspace_lor_memory_hierarchy_runtime import _owner_multiplicity as s5_owner_multiplicity

    return s5_owner_multiplicity(topology)


class NestedHmgHierarchyExtension:
    """String-keyed h6/h3star/h1star owner-packet extension."""

    def __init__(self, foundation: Any, level6: Any, h3star: Any, h1star: Any,
                 transfer_63: Any, transfer_31: Any) -> None:
        if level6.matrix is not foundation.low_matrix:
            raise ValueError("nested hmg level h6 must reuse foundation.low_matrix")
        self.foundation = foundation
        self.levels = {"h6": level6, "h3star": h3star, "h1star": h1star}
        self.transfers = {
            ("h6", "h3star"): transfer_63,
            ("h3star", "h1star"): transfer_31,
        }
        self._destroyed = False
        self.audit = MappingProxyType({
            "schema": NESTED_HMG_RUNTIME_SCHEMA,
            "levels": NESTED_HMG_LEVELS,
            "pairs": NESTED_HMG_PAIRS,
            "foundation_caller_owned": True,
            "h3star_standard_polynomial_space": False,
            "global_high_order_aij": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "smoother_built": False,
            "ksp_created": False,
            "factor_built": False,
            "physical_solve": False,
            "recovery": False,
            "retains_per_apply_history": False,
        })

    def pair_levels(self, pair: tuple[str, str]):
        key = tuple(pair)
        if key not in self.transfers:
            raise ValueError(f"unsupported nested HMG pair: {key}")
        transfer = self.transfers[key]
        return transfer.fine, transfer.coarse

    def apply_primal_into(self, pair: tuple[str, str], source: Any, target: Any):
        key = tuple(pair)
        self.pair_levels(key)
        return self.transfers[key].apply_primal_into(source, target)

    def apply_adjoint_into(self, pair: tuple[str, str], source: Any, target: Any):
        key = tuple(pair)
        self.pair_levels(key)
        return self.transfers[key].apply_adjoint_into(source, target)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        for level_key in ("h3star", "h1star", "h6"):
            level = self.levels.get(level_key)
            if level is not None:
                level.destroy()
        self.levels = {}
        self.transfers = {}
        self.foundation = None


def build_nested_hmg_extension_from_foundation(
    foundation: Any,
) -> NestedHmgHierarchyExtension:
    """Extend one existing p6/h10 foundation without rebuilding it."""

    if foundation is None or not hasattr(foundation, "low_matrix"):
        raise ValueError("nested HMG requires an already-built S2 foundation")
    cfg = foundation.cfg
    if (
        int(cfg.nedelec_degree),
        float(cfg.mesh_target_size),
        float(cfg.lambda0),
    ) != (6, 10.0, 13.5):
        raise ValueError("nested HMG identity is fixed at p6/h10/13.5 nm")
    parent_axes = _stage4_parent_axes(foundation)
    level6 = _build_level6_for_nested(foundation)
    h3star = h1star = None
    try:
        h3star = _build_nested_level(foundation, "h3star", parent_axes)
        h1star = _build_nested_level(foundation, "h1star", parent_axes)
        local = build_nested_lor_edge_hmg()
        transfer_63 = _OwnerPacketTransfer(
            level6,
            h3star,
            local.h6_to_h3star,
            allowed_pairs=NESTED_HMG_PAIRS,
            route_schema=NESTED_HMG_RUNTIME_SCHEMA,
            pair_key=NESTED_HMG_PAIRS[0],
        )
        transfer_31 = _OwnerPacketTransfer(
            h3star,
            h1star,
            local.h3star_to_h1star,
            allowed_pairs=NESTED_HMG_PAIRS,
            route_schema=NESTED_HMG_RUNTIME_SCHEMA,
            pair_key=NESTED_HMG_PAIRS[1],
        )
        return NestedHmgHierarchyExtension(
            foundation, level6, h3star, h1star, transfer_63, transfer_31
        )
    except Exception:
        if h1star is not None:
            h1star.destroy()
        if h3star is not None:
            h3star.destroy()
        level6.destroy()
        raise


__all__ = [
    "NESTED_HMG_BATCH_CELL_CAP",
    "NESTED_HMG_LEVELS",
    "NESTED_HMG_PAIRS",
    "NESTED_HMG_RUNTIME_SCHEMA",
    "NestedHmgHierarchyExtension",
    "_TopologyOnlyNestedTransfer",
    "_nested_axes",
    "_nested_axis",
    "_nested_indices",
    "_nested_nodes",
    "build_nested_hmg_extension_from_foundation",
]
