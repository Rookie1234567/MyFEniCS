"""Concrete S5 p6 -> p3 -> p1 owner-packet hierarchy extension."""

from __future__ import annotations

import copy
from types import MappingProxyType, SimpleNamespace
from typing import Any, Iterable, Mapping

import numpy as np

from .fullspace_lor_memory_hierarchy import (
    INTERLEVEL_BATCH_CELL_CAP,
    LocalInterlevelEdgeTransfer,
    build_local_interlevel_edge_transfer,
)

S5_SCHEMA = "task038.lor-memory-hierarchy.runtime.v1"
S5_LEVELS = (6, 3, 1)
S5_PAIRS = ((6, 3), (3, 1))
S5_BATCH_CELL_CAP = INTERLEVEL_BATCH_CELL_CAP
S5_CHEBYSHEV_LEVELS = (6, 3)
S5_FORBIDDEN_FACTS = ("global_high_order_aij", "global_transfer_matrix",
                      "numeric_allgather", "p1_global_direct_factor",
                      "p6_exact_factor", "hx_hierarchy_built",
                      "pcgamg_hierarchy_built", "physical_solve", "recovery")
S5_HIERARCHY_RUNTIME = "p6_to_p3_to_p1_fixed_owner_packet_hierarchy"


def _packet(packet: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    ids = np.asarray(packet[0], dtype=np.uint32)
    values = np.asarray(packet[1], dtype=np.complex128)
    if ids.ndim != 1 or values.shape != ids.shape or (
        ids.size and np.any(ids[1:] <= ids[:-1])
    ):
        raise ValueError("owner packet shape is not closed")
    if not np.all(np.isfinite(values)):
        raise ValueError("owner packet contains non-finite values")
    return ids, values


def _pull_unique_packet(topology: Any, packet):
    ids, values = _packet(packet)
    return topology.unique_edge_ids, topology.pull_owner_unique_values(ids, values)


def _destroy_owned(objects: Iterable[Any]) -> None:
    seen: set[int] = set()
    for obj in objects:
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        if hasattr(obj, "destroy"):
            obj.destroy()


def _matrix_facts(matrix: Any) -> dict[str, int | str]:
    from petsc4py import PETSc

    rows, cols = (int(value) for value in matrix.getSize())
    info = dict(matrix.getInfo())
    nnz = int(round(float(info.get("nz_used", info.get("nz_allocated", 0.0)))))
    index_bytes = (rows + 1 + nnz) * np.dtype(PETSc.IntType).itemsize
    numeric_bytes = nnz * np.dtype(PETSc.ScalarType).itemsize
    reported = int(info.get("memory", 0.0))
    return {
        "rows": rows, "cols": cols, "nnz": nnz,
        "index_bytes": int(index_bytes), "numeric_bytes": int(numeric_bytes),
        "petsc_reported_memory_bytes": reported,
        "petsc_overhead_bytes": max(reported - index_bytes - numeric_bytes, 0),
        "type": str(matrix.getType()),
    }


class _S5Level:
    def __init__(self, *, degree: int, matrix: Any, raw_space: Any,
                 raw_floquet: Any, parent_topology: Any, raw_topology: Any,
                 raw_map: Mapping[str, np.ndarray], raw_permutations: np.ndarray,
                 incidence_unique: np.ndarray, parent_space: Any = None,
                 parent_floquet: Any = None, owned_objects: Iterable[Any] = (),
                 foundation_owned: bool = False) -> None:
        self.degree, self.matrix = int(degree), matrix
        self.raw_space, self.raw_floquet = raw_space, raw_floquet
        self.parent_topology, self.raw_topology = parent_topology, raw_topology
        self.raw_map = raw_map
        self.raw_permutations = np.asarray(raw_permutations, dtype=np.int32)
        self.parent_space, self.parent_floquet = parent_space, parent_floquet
        self._owned_objects = tuple(owned_objects)
        self.foundation_owned, self._destroyed = bool(foundation_owned), False
        parent_cells = int(parent_topology.cell_edge_ids.shape[0])
        if not np.array_equal(parent_topology.owned_edge_ids, raw_topology.owned_edge_ids):
            raise ValueError("parent/raw owner inventories do not close")
        if self.raw_permutations.shape != (
            int(raw_space.mesh.topology.index_map(3).size_local), 12
        ):
            raise ValueError("raw p1 permutation inventory is not closed")
        if np.asarray(incidence_unique).shape != parent_topology.unique_edge_ids.shape:
            raise ValueError("parent incidence inventory is not closed")
        self.incidence_unique = np.asarray(incidence_unique, dtype=np.float64)
        facts = _matrix_facts(matrix)
        self.audit = MappingProxyType({
            "schema": S5_SCHEMA, "level": self.degree,
            "level_role": "foundation_lor_level6" if self.degree == 6 else f"refined_lor_level{self.degree}",
            "foundation_owned": self.foundation_owned,
            "parent_metadata_only": self.degree == 3,
            "parent_matrix_built": False,
            "parent_local_owned_rows": int(parent_topology.owned_edge_ids.size),
            "parent_local_unique_rows": int(parent_topology.unique_edge_ids.size),
            "parent_global_unique_rows": int(
                parent_topology.audit["global_unique_edge_count"]
            ),
            "raw_local_owned_rows": int(raw_topology.owned_edge_ids.size),
            "raw_local_unique_rows": int(raw_topology.unique_edge_ids.size),
            "raw_global_unique_rows": int(
                raw_topology.audit["global_unique_edge_count"]
            ),
            "parent_cell_count_local": parent_cells,
            "owner_route": "typed_complex128_alltoallv",
            "matrix": facts,
            "global_high_order_aij": False, "global_transfer_matrix": False,
            "numeric_allgather": False, "p1_global_direct_factor": False,
            "p6_exact_factor": False, "hx_hierarchy_built": False,
            "pcgamg_hierarchy_built": False, "physical_solve": False,
            "recovery": False,
            "retained_known_bytes": {
                "matrix_index_bytes": int(facts["index_bytes"]),
                "matrix_numeric_bytes": int(facts["numeric_bytes"]),
                "raw_map_bytes": int(sum(value.nbytes for value in raw_map.values())),
            },
        })
        if self.degree not in S5_LEVELS or any(
            self.audit[name] is not False for name in S5_FORBIDDEN_FACTS
        ):
            raise ValueError("S5 level or forbidden-object facts are not closed")

    @property
    def parent_block_count(self) -> int:
        return int(self.parent_topology.cell_edge_ids.shape[0])

    def _raw_to_parent(self, source: Any, *, dual: bool):
        if dual:
            from .fullspace_lor_edge_geometric_mg_global import _raw_dual_owner_packet

            packet = _raw_dual_owner_packet(
                self.raw_space, self.raw_floquet, self.raw_topology,
                source, self.raw_permutations,
            )
        else:
            from .fullspace_lor_memory_first_foundation import _route_low_to_owner

            packet = _route_low_to_owner(
                self.raw_space, self.raw_floquet, self.raw_topology,
                source, self.raw_permutations,
            )
        return _pull_unique_packet(self.parent_topology, packet)

    def primal_to_owner(self, source: Any):
        return self._raw_to_parent(source, dual=False)

    def dual_to_owner(self, source: Any):
        return self._raw_to_parent(source, dual=True)

    def expand_primal(self, packet, start: int, stop: int):
        _ids, values = _packet(packet)
        return self.parent_topology.cell_values_from_unique(values, start, stop)

    def expand_dual(self, packet, start: int, stop: int):
        _ids, values = _packet(packet)
        rows = np.asarray(
            self.parent_topology.cell_values_from_unique(values, start, stop),
            dtype=np.complex128,
        )
        positions = np.searchsorted(
            self.parent_topology.unique_edge_ids,
            self.parent_topology.cell_edge_ids[start:stop],
        )
        return rows / self.incidence_unique[positions]

    def route_primal_blocks(self, blocks):
        return self.parent_topology.route_owner_cell_chunks(blocks)

    def route_dual_blocks(self, blocks):
        return self.parent_topology.route_owner_cell_chunks_additive(blocks)

    def _parent_to_raw(self, packet):
        from .fullspace_lor_memory_first_foundation import _fill_raw_vector

        ids, values = _packet(packet)
        unique = self.raw_topology.pull_owner_unique_values(ids, values)
        target = self.matrix.createVecRight()
        _fill_raw_vector(target, unique, self.raw_map, self.raw_topology.unique_edge_ids)
        return target

    def owner_to_primal(self, packet):
        return self._parent_to_raw(packet)

    def owner_to_dual(self, packet):
        return self._parent_to_raw(packet)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if not self.foundation_owned:
            _destroy_owned(self._owned_objects)
        self._owned_objects = ()
        self.matrix = self.raw_space = self.raw_floquet = None
        self.parent_topology = self.raw_topology = None
        self.raw_map = self.parent_space = self.parent_floquet = None


class _OwnerPacketTransfer:
    def __init__(self, fine: _S5Level, coarse: _S5Level,
                 local_transfer: LocalInterlevelEdgeTransfer):
        pair = (fine.degree, coarse.degree)
        expected = (
            3 * fine.degree * (fine.degree + 1) ** 2,
            3 * coarse.degree * (coarse.degree + 1) ** 2,
        )
        if pair not in S5_PAIRS or fine.parent_block_count != coarse.parent_block_count:
            raise ValueError("S5 parent topology pair is not closed")
        if local_transfer.edge_shape != expected:
            raise ValueError("S5 local transfer shape is not closed")
        self.fine, self.coarse, self.local_transfer = fine, coarse, local_transfer
        self.primal_apply_count = self.adjoint_apply_count = 0
        edge = np.asarray(local_transfer.edge_transfer)
        node = np.asarray(local_transfer.node_transfer)
        self.audit = MappingProxyType({"pair": pair,
            "batch_cell_cap": S5_BATCH_CELL_CAP, "global_transfer_matrix": False,
            "numeric_allgather": False,
            "orientation_phase_scope": "owned by parent topology routes",
            "local_map": {
                "edge_rows": int(edge.shape[0]), "edge_cols": int(edge.shape[1]),
                "edge_exact_nnz": int(np.count_nonzero(edge)),
                "edge_numeric_bytes": int(edge.nbytes),
                "node_rows": int(node.shape[0]), "node_cols": int(node.shape[1]),
                "node_exact_nnz": int(np.count_nonzero(node)),
                "node_numeric_bytes": int(node.nbytes),
            },
            "local_transfer": dict(local_transfer.audit)})

    def apply_primal(self, source):
        packet = self.coarse.primal_to_owner(source)

        def blocks():
            for start in range(0, self.coarse.parent_block_count, S5_BATCH_CELL_CAP):
                stop = min(start + S5_BATCH_CELL_CAP, self.coarse.parent_block_count)
                rows = self.local_transfer.apply_primal_many(
                    self.coarse.expand_primal(packet, start, stop)
                )
                yield start, rows

        packet = self.fine.route_primal_blocks(blocks())
        self.primal_apply_count += 1
        return self.fine.owner_to_primal(packet)

    def apply_adjoint(self, source):
        packet = self.fine.dual_to_owner(source)

        def blocks():
            for start in range(0, self.fine.parent_block_count, S5_BATCH_CELL_CAP):
                stop = min(start + S5_BATCH_CELL_CAP, self.fine.parent_block_count)
                rows = self.local_transfer.apply_adjoint_many(
                    self.fine.expand_dual(packet, start, stop)
                )
                yield start, rows

        packet = self.coarse.route_dual_blocks(blocks())
        self.adjoint_apply_count += 1
        return self.coarse.owner_to_dual(packet)


class S5HierarchyExtension:
    def __init__(self, foundation, level6, level3, level1, transfer_63,
                 transfer_31, smoother6, smoother3):
        if level6.matrix is not foundation.low_matrix:
            raise ValueError("level6 must reuse foundation.low_matrix")
        self.foundation = foundation
        self.levels = {6: level6, 3: level3, 1: level1}
        self.transfers = {(6, 3): transfer_63, (3, 1): transfer_31}
        self.smoothers = {6: smoother6, 3: smoother3}
        self._smoother_apply_counts = {6: 0, 3: 0}
        self._destroyed = False
        self.audit = MappingProxyType({"schema": S5_SCHEMA, "levels": S5_LEVELS,
            "pairs": S5_PAIRS, "foundation_caller_owned": True,
            "global_high_order_aij": False, "global_transfer_matrix": False,
            "numeric_allgather": False, "p1_global_direct_factor": False,
            "p6_exact_factor": False, "hx_hierarchy_built": False,
            "pcgamg_hierarchy_built": False, "physical_solve": False,
            "recovery": False, "level1_smoother": False,
            "retains_per_apply_history": False})

    def apply_primal(self, pair, source):
        if self._destroyed:
            raise RuntimeError("S5 hierarchy has been destroyed")
        return self.transfers[tuple(pair)].apply_primal(source)

    def apply_adjoint(self, pair, source):
        if self._destroyed:
            raise RuntimeError("S5 hierarchy has been destroyed")
        return self.transfers[tuple(pair)].apply_adjoint(source)

    def apply_smoother(self, degree, source, target):
        degree = int(degree)
        if self._destroyed:
            raise RuntimeError("S5 hierarchy has been destroyed")
        if degree not in S5_CHEBYSHEV_LEVELS:
            raise ValueError("S5 smoother is available only on levels 6 and 3")
        facts = self.smoothers[degree].apply_into(source, target)
        self._smoother_apply_counts[degree] += 1
        result = dict(facts) if isinstance(facts, Mapping) else {}
        result.update({
            "degree": degree, "fixed_chebyshev_degree": 3,
            "fixed_power_steps": 10,
            "cumulative_apply_count": self._smoother_apply_counts[degree],
        })
        return result

    def retained_ledger(self, resource: Mapping[str, Any]):
        from .fullspace_lor_memory_first_foundation import (
            _retained_array_bytes, _topology_retained_arrays,
        )

        known = {}
        seen: set[int] = set()
        topology_aliases = {}
        for degree in (3, 1):
            level = self.levels[degree]
            prefix = f"level{degree}_"
            known.update({prefix + name: int(value) for name, value in
                          level.audit["retained_known_bytes"].items()})
            known.update({
                prefix + "raw_permutations_bytes": int(level.raw_permutations.nbytes),
                prefix + "incidence_unique_bytes": int(level.incidence_unique.nbytes),
                prefix + "parent_topology_retained_array_bytes": int(
                    _retained_array_bytes(_topology_retained_arrays(level.parent_topology), seen)),
                prefix + "raw_topology_retained_array_bytes": int(
                    _retained_array_bytes(_topology_retained_arrays(level.raw_topology), seen)),
            })
            topology_aliases[prefix + "parent_raw_topology_shared"] = (
                level.parent_topology is level.raw_topology)
        for pair, transfer in self.transfers.items():
            local_map = transfer.audit["local_map"]
            prefix = f"transfer_{pair[0]}_{pair[1]}_"
            known.update({prefix + "edge_bytes": int(local_map["edge_numeric_bytes"]),
                          prefix + "node_bytes": int(local_map["node_numeric_bytes"])})
        for degree, smoother in self.smoothers.items():
            vector = getattr(smoother, "_inv_sqrt", None)
            local = int(vector.getLocalSize()) if vector is not None else 0
            known[f"level{degree}_chebyshev_work_vector_bytes"] = 8 * local * 16
        total = int(sum(known.values()))
        rss = int(resource.get("process_tree", {}).get("rss_bytes", -1))
        return {
            "scope": "S5 lower levels/smoothers/maps; foundation ledger is separate",
            "known_bytes": known, "known_total_bytes": total,
            "topology_aliases": topology_aliases,
            "measured_process_tree_rss_bytes": rss,
            "unattributed_remainder_bytes": rss - total,
            "bounded_temporary_bytes": {
                "included_in_known_total": False, "batch_cell_cap": S5_BATCH_CELL_CAP,
            },
        }

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        _destroy_owned((self.smoothers[6], self.smoothers[3]))
        self.smoothers = {}
        self.transfers = {}
        self.levels[3].destroy()
        self.levels[1].destroy()
        self.levels[6] = None
        self.foundation = None


def _owner_multiplicity(topology):
    from .fullspace_lor_edge_geometric_mg_global import _owner_incidence_counts

    owner_ids, counts = _owner_incidence_counts(topology)
    incidence_unique = topology.pull_owner_unique_values(
        owner_ids, np.asarray(counts, dtype=np.complex128)
    ).real
    return np.asarray(incidence_unique, dtype=np.float64)


def _build_level(foundation, degree: int, parent_axes):
    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (_mark_boundary_facets, _mark_cells,
                                              _structured_hexa_mesh)
    from .fullspace_lor_memory_first_foundation import _canonical_raw_map
    from .fullspace_lor_native_hx_fixture import (_P1IdentityTransfer, _assemble_sparse,
                                                  _edge_records, _p1_transfer_local_indices,
                                                  _piecewise_positive_coefficients, _refined_axis)
    from .fullspace_lor_topology import build_canonical_lor_subedge_topology
    from .fullspace_lor_transfer import build_local_lor_transfer

    degree = int(degree)
    cfg, comm = foundation.cfg, foundation.high_mesh.comm
    if degree == 1:
        mesh = foundation.high_mesh
        facets, cells = foundation.high_data.facet_tags, foundation.high_data.cell_tags
        axes = parent_axes
    elif degree == 3:
        axes = tuple(_refined_axis(values, 3) for values in parent_axes)
        mesh = _structured_hexa_mesh(
            comm, *axes,
            preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
        )
        facets, _ = _mark_boundary_facets(mesh, cfg)
        cells = _mark_cells(mesh, cfg)
    else:
        raise ValueError("S5 lower degree is fixed at 3 or 1")
    data = SimpleNamespace(mesh=mesh, cell_tags=cells, facet_tags=facets)
    low_cfg = copy.deepcopy(cfg)
    low_cfg.nedelec_degree = low_cfg.visualization_degree = 1
    low_cfg.nedelec_trace_degree = low_cfg.nedelec_interior_degree = None
    low_cfg.case_name = f"{cfg.case_name}_s5_lor_p{degree}"
    raw_space = fem.functionspace(
        mesh, element("N1curl", mesh.basix_cell(), 1, dtype=np.float64)
    )
    raw_floquet = build_double_floquet_mpc(raw_space, data, low_cfg)
    permutations = np.asarray([
        _p1_transfer_local_indices(raw_space, cell)
        for cell in range(int(mesh.topology.index_map(3).size_local))
    ], dtype=np.int32)
    mu, mass, _ = _piecewise_positive_coefficients(mesh, cells, low_cfg)
    u, v = ufl.TrialFunction(raw_space), ufl.TestFunction(raw_space)
    matrix = _assemble_sparse(
        (mu * ufl.inner(ufl.curl(u), ufl.curl(v)) + mass * ufl.inner(u, v)) * ufl.dx,
        mpc=raw_floquet.mpc,
    )
    raw_topology = build_canonical_lor_subedge_topology(
        raw_space, raw_floquet, _P1IdentityTransfer()
    )
    node_space = fem.functionspace(
        mesh, element("Lagrange", mesh.basix_cell(), 1, dtype=default_real_type)
    )
    records, _ = _edge_records(raw_space, node_space)
    raw_map = _canonical_raw_map(
        raw_space, node_space, records, axes,
        owner_ids=raw_topology.owned_edge_ids,
        local_permutations=permutations,
        validate_local_owner_layout=False,
    )
    del node_space, records, mu, mass
    owned = [matrix, raw_floquet]
    if degree == 3:
        parent_data = SimpleNamespace(
            mesh=foundation.high_mesh,
            cell_tags=foundation.high_data.cell_tags,
            facet_tags=foundation.high_data.facet_tags,
        )
        parent_cfg = copy.deepcopy(cfg)
        parent_cfg.nedelec_degree = parent_cfg.visualization_degree = 3
        parent_cfg.nedelec_trace_degree = parent_cfg.nedelec_interior_degree = None
        parent_space = fem.functionspace(
            foundation.high_mesh,
            element("N1curl", foundation.high_mesh.basix_cell(), 3, dtype=default_real_type),
        )
        parent_floquet = build_double_floquet_mpc(parent_space, parent_data, parent_cfg)
        parent_topology = build_canonical_lor_subedge_topology(
            parent_space, parent_floquet, build_local_lor_transfer(3)
        )
        owned.append(parent_floquet)
    else:
        parent_space, parent_floquet, parent_topology = raw_space, raw_floquet, raw_topology
    return _S5Level(degree=degree, matrix=matrix, raw_space=raw_space,
        raw_floquet=raw_floquet, parent_topology=parent_topology,
        raw_topology=raw_topology, raw_map=raw_map,
        raw_permutations=permutations, incidence_unique=_owner_multiplicity(parent_topology),
        parent_space=parent_space, parent_floquet=parent_floquet, owned_objects=owned)


def _build_level6(foundation):
    return _S5Level(
        degree=6, matrix=foundation.low_matrix,
        raw_space=foundation.low_edge_space, raw_floquet=foundation.low_floquet,
        parent_topology=foundation.high_topology,
        raw_topology=foundation.low_topology, raw_map=foundation.low_raw_map,
        raw_permutations=foundation.low_p1_transfer_local_indices,
        incidence_unique=_owner_multiplicity(foundation.high_topology),
        owned_objects=(), foundation_owned=True,
    )


def build_s5_hierarchy_extension(foundation: Any) -> S5HierarchyExtension:
    if foundation is None or not hasattr(foundation, "low_matrix"):
        raise ValueError("S5 requires an already-built S2 foundation")
    cfg = foundation.cfg
    if (int(cfg.nedelec_degree), float(cfg.mesh_target_size), float(cfg.lambda0)) != (6, 10.0, 13.5):
        raise ValueError("S5 identity is fixed at p6/h10/13.5 nm")
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    plan = _stage4_axis_plan(cfg, foundation.high_mesh.comm.size)
    parent_axes = tuple(np.asarray(axis, dtype=np.float64)
                        for axis in (plan.x_values, plan.y_values, plan.z_values))
    level6 = _build_level6(foundation)
    level3 = level1 = smoother6 = smoother3 = None
    try:
        level3 = _build_level(foundation, 3, parent_axes)
        level1 = _build_level(foundation, 1, parent_axes)
        transfer_63 = _OwnerPacketTransfer(
            level6, level3, build_local_interlevel_edge_transfer(6, 3)
        )
        transfer_31 = _OwnerPacketTransfer(
            level3, level1, build_local_interlevel_edge_transfer(3, 1)
        )
        from .fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc

        smoother6 = FixedChebyshevJacobiPETSc(level6.matrix)
        smoother3 = FixedChebyshevJacobiPETSc(level3.matrix)
        return S5HierarchyExtension(
            foundation, level6, level3, level1,
            transfer_63, transfer_31, smoother6, smoother3,
        )
    except Exception:
        _destroy_owned((smoother6, smoother3))
        if level1 is not None:
            level1.destroy()
        if level3 is not None:
            level3.destroy()
        raise


__all__ = ["S5_BATCH_CELL_CAP", "S5_CHEBYSHEV_LEVELS", "S5_FORBIDDEN_FACTS",
           "S5_HIERARCHY_RUNTIME", "S5_LEVELS", "S5_PAIRS", "S5_SCHEMA",
           "S5HierarchyExtension", "build_s5_hierarchy_extension"]
